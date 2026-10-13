"""Read-only bounded migration of historical ActOnePilot PNGs. Never deletes."""
import argparse
import hashlib
import json
from pathlib import Path
import re

TAIL_BYTES = 512 * 1024 * 1024
EVIDENCE_COUNT = 32
EVIDENCE_BYTES = 64 * 1024 * 1024


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def plan(root, latest=256, external_references=(), tail_bytes=TAIL_BYTES,
         evidence_count=EVIDENCE_COUNT, evidence_bytes=EVIDENCE_BYTES):
    root = root.resolve(strict=True)
    captures, reports, references = [], [], []
    external_frames, terminal_frames = set(), {}
    for reference in external_references:
        text = reference.read_text(encoding='utf-8-sig').replace('\\', '/')
        matches = re.findall(r'([A-Za-z0-9_-]+)/+frame-(\d+)\.png', text)
        if matches:
            external_frames.update((session, int(frame)) for session, frame in matches)
            references.append(dict(path=str(reference), sha256=digest(reference)))
    for path in root.rglob('*'):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError(f'Reparse point rejected: {path}')
    report_root = root / 'reports'
    if report_root.exists():
        for report in sorted(report_root.iterdir()):
            if report.suffix not in ('.json', '.jsonl'):
                continue
            text = report.read_text(encoding='utf-8-sig')
            # Invalid reports stop planning rather than exempting an unlimited tree.
            data = [json.loads(line) for line in text.splitlines() if line.strip()] if report.suffix == '.jsonl' else json.loads(text)
            if isinstance(data, dict):
                # Explicit sidecar regression/operation witness, not a scene heuristic.
                if isinstance(data.get('frameId'), int) and isinstance(data.get('session'), str):
                    external_frames.add((data['session'], data['frameId']))
                data = [data]
            if not isinstance(data, list):
                raise ValueError(f'Unexpected report shape: {report}')
            reports.append(dict(path=str(report), bytes=report.stat().st_size, sha256=digest(report)))
            for row in data:
                if not isinstance(row, dict):
                    continue
                status, mission = row.get('status'), row.get('mission')
                if status != 'failed' and not (status == 'completed' and mission == 'questStep'):
                    continue
                details = row.get('details') or {}
                result = details.get('result') or {}
                step = result.get('step', '') if isinstance(result, dict) else ''
                key = f'{mission}:{step}:{status}'
                identity = (row.get('session', report.stem), row.get('frameId'))
                terminal_frames.setdefault(identity, set()).add(key)
    for png in sorted((root / 'observations').rglob('*.png')):
        child = png.relative_to(root / 'observations')
        match = re.fullmatch(r'frame-(\d+)\.png', png.name)
        session = child.parts[0] if len(child.parts) == 2 else ''
        frame = int(match[1]) if match else None
        identity = (session, frame)
        row = dict(path=str(png), frame=frame, session=session,
                   bytes=png.stat().st_size, sha256=digest(png), reasons=[],
                   timestamp=png.stat().st_mtime_ns // 1000000)
        if identity in external_frames:
            row['reasons'].append('concrete-external-validation-reference')
        keys = set(terminal_frames.get(identity, ()))
        try:
            if not session or frame is None:
                raise ValueError('Nonstandard capture path')
            data = json.loads(png.with_suffix('.json').read_text(encoding='utf-8-sig'))
            if data['session'] != session or data['frameId'] != frame:
                raise ValueError('Mismatched metadata')
            row['timestamp'] = data['timestamp']
            text = ' '.join(str(r.get('text', '')) for r in data.get('ocr', [])).lower()
            # One newest example per outcome/quest, rather than each OCR transition.
            objectives = (data.get('hud') or {}).get('objectives', [])
            objective = re.sub(r'\b\d+(?:\.\d+)?\s*m\b', '', ' '.join(map(str, objectives))).strip().lower()
            for marker in ('quest completed', 'challenge completed', 'challenge failed', 'you died', 'achievement unlocked'):
                if marker in text:
                    keys.add(f'ocr:{marker}:{objective}')
        except (ValueError, KeyError, TypeError, OSError):
            row['reasons'].append('unknown-image-needs-review')
        row['evidenceKeys'] = sorted(keys)
        captures.append(row)
    newest = sorted(captures, key=lambda r: (r['timestamp'], r['path']), reverse=True)
    tail_used = 0
    # Contiguous recent tail: stop at the first byte/count boundary.
    for row in newest[:latest]:
        if tail_used + row['bytes'] > tail_bytes:
            break
        row['reasons'].append('bounded-recent-tail')
        tail_used += row['bytes']
    indispensable = [r for r in newest if any(reason != 'bounded-recent-tail' for reason in r['reasons'])]
    evidence_used = sum(r['bytes'] for r in indispensable)
    if len(indispensable) > evidence_count or evidence_used > evidence_bytes:
        raise ValueError(f'Concrete/unknown evidence exceeds cap: {len(indispensable)} images, {evidence_used} bytes. Review exact references before proposing deletion.')
    selected = len(indispensable)
    seen_keys, seen_hashes = set(), set()
    for row in newest:
        keys = set(row['evidenceKeys'])
        # Identical PNGs and repeated semantic outcomes need only one representative.
        if not keys or keys <= seen_keys or row['sha256'] in seen_hashes:
            continue
        if row['reasons']:
            row['reasons'].append('representative:' + ','.join(sorted(keys - seen_keys)))
        elif selected < evidence_count and evidence_used + row['bytes'] <= evidence_bytes:
            row['reasons'].append('representative:' + ','.join(sorted(keys - seen_keys)))
            selected += 1
            evidence_used += row['bytes']
        else:
            continue
        seen_keys.update(keys)
        seen_hashes.add(row['sha256'])
    retained = [r for r in captures if r['reasons']]
    candidates = [r for r in captures if not r['reasons']]
    return dict(version=1, mode='historical-plan-only', root=str(root),
                limits=dict(recentFrames=latest, recentBytes=tail_bytes, evidenceFrames=evidence_count,
                            evidenceBytes=evidence_bytes, totalFrames=latest+evidence_count,
                            totalBytes=tail_bytes+evidence_bytes),
                files=len(candidates), bytes=sum(r['bytes'] for r in candidates),
                retainedFiles=len(retained), retainedBytes=sum(r['bytes'] for r in retained),
                preservation='All observation JSON/reports/settings/logs remain. Keep only bounded recent tail and representative/concretely referenced evidence. Exact approval required; no files changed.',
                candidates=candidates, retained=retained, reports=reports, references=references)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repository', type=Path)
    args = parser.parse_args()
    references = []
    if args.repository:
        for base, recursive in ((args.repository/'artifacts', False), (args.repository/'Docs', True), (args.repository/'tools/quest-pilot', True)):
            paths = base.rglob('*') if recursive else base.iterdir()
            references.extend(path for path in paths if path.is_file() and path.suffix in ('.json', '.md')
                              and not path.name.startswith('retention-'))
    result = plan(args.root, external_references=references)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('candidates', 'retained', 'reports', 'references')}))
    print('manifestSha256=' + digest(args.output))
