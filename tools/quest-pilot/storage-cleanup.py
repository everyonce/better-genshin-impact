"""Read-only inventory of byte-identical, non-user build files. Never deletes data."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular_tree(root):
    # Refuse junctions/symlinks rather than following them outside the inventory.
    for path in root.rglob('*'):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError(f'Reparse point requires manual review: {path}')
        if path.is_file():
            yield path


def plan(repository):
    root = repository.resolve(strict=True)
    artifacts = root / 'artifacts'
    keep = artifacts / 'release-r15' / 'BetterGI-English-win-x64'
    candidates = []
    for relative in ['r15-native-publish', 'release-r13/BetterGI-English-win-x64',
                     'release/BetterGI-English-win-x64', 'BetterGI-English-win-x64']:
        source = artifacts / relative
        if not source.is_dir():
            continue
        for path in regular_tree(source):
            child = path.relative_to(source)
            if child.parts[0].lower() in ('user', 'log', 'logs'):
                continue
            preserved = keep / child
            if not preserved.is_file() or preserved.is_symlink():
                continue
            if path.stat().st_size != preserved.stat().st_size:
                continue
            value = digest(path)
            if value == digest(preserved):
                candidates.append(dict(path=str(path), bytes=path.stat().st_size,
                                       sha256=value, preserved=str(preserved)))
    return dict(version=1, mode='plan-only', bytes=sum(x['bytes'] for x in candidates),
                files=len(candidates), candidates=candidates,
                preservation='All User and log directories excluded. Every candidate has a SHA-256-identical copy in active r15. No deletion authorized by this manifest.')


def generated_plan(repository):
    root = repository.resolve(strict=True)
    current = root / 'BetterGenshinImpact/bin/x64/Debug/net8.0-windows10.0.22621.0'
    installed = root / 'artifacts/release-r15/BetterGI-English-win-x64'
    test_in_use = root / 'Test/BetterGenshinImpact.EnglishTest'
    sources = list((root / 'Test').glob('*/bin/**/BetterGI.dll'))
    sources += list((root / 'BetterGenshinImpact/bin').glob('**/BetterGI.dll'))
    candidates = []
    seen = set()
    for assembly in sources:
        source = assembly.parent
        if source == current or source.is_relative_to(test_in_use):
            continue
        for path in regular_tree(source):
            if path in seen or path.is_relative_to(current):
                continue
            seen.add(path)
            child = path.relative_to(source)
            if any(p.lower() in ('user', 'log', 'logs', 'observations', 'reports', 'receipts') for p in child.parts):
                continue
            for keeper in (current, installed):
                preserved = keeper / child
                if preserved.is_file() and path.stat().st_size == preserved.stat().st_size:
                    value = digest(path)
                    if value == digest(preserved):
                        candidates.append(dict(path=str(path), bytes=path.stat().st_size,
                                               sha256=value, preserved=str(preserved)))
                        break
    return dict(version=1, mode='plan-only', files=len(candidates),
                bytes=sum(x['bytes'] for x in candidates), candidates=candidates,
                preservation='Only exact duplicate generated bin files. Current application output, English test output in use, active r14/r15, all User/log/evidence and unique test assemblies preserved. Requires separate exact approval.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--generated-outputs', action='store_true')
    args = parser.parse_args()
    result = generated_plan(args.repository) if args.generated_outputs else plan(args.repository)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'candidates'}))
