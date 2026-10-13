"""Verify the live installed controller and produce the next exact build-retirement plan.

No gameplay input or deletion. Apply the plan through apply-storage-cleanup.ps1
only with its separately approved SHA-256. Keep active roots and one rollback.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import time


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def retirement_plan(repository, installed, protected):
    cleanup = load('cleanup', 'storage-cleanup.py')
    witness = installed / 'BetterGI.dll'
    witness_hash = cleanup.digest(witness)
    candidates = []
    for source in (repository / 'artifacts').iterdir():
        if not source.is_dir() or not re.fullmatch(r'(?:release(?:-r\d+)?|r\d+-native-publish|BetterGI-English-win-x64)', source.name):
            continue
        if any(source == item or source.is_relative_to(item) or item.is_relative_to(source) for item in protected):
            continue
        for path in cleanup.regular_tree(source):
            if any(part.lower() in ('user', 'log', 'logs', 'observations', 'reports', 'receipts') for part in path.relative_to(source).parts):
                continue
            candidates.append(dict(kind='superseded-build', path=str(path), bytes=path.stat().st_size,
                                   sha256=cleanup.digest(path), preserved=str(witness),
                                   preservedBytes=witness.stat().st_size, preservedSha256=witness_hash))
    return dict(version=1, mode='plan-only', files=len(candidates), bytes=sum(x['bytes'] for x in candidates),
                candidates=candidates, preservation='Active runtimes, explicit rollback, all User/log/evidence are excluded. Successor witness proves installed build identity, not byte equivalence. Separate exact approval is required.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--process-id', type=int, required=True)
    parser.add_argument('--windows-session-id', type=int, required=True)
    parser.add_argument('--app-directory', type=Path, required=True)
    parser.add_argument('--expected-dll-sha256', required=True)
    parser.add_argument('--protect', type=Path, action='append', required=True)
    parser.add_argument('--cleanup-manifest', type=Path, help='Reuse an already reviewed exact candidate set')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    app = args.app_directory.resolve(strict=True)
    if not app.is_relative_to(root / 'artifacts'):
        raise SystemExit('Installed runtime must be under repository artifacts')
    control = load('control', 'controller-control.py')
    cleanup = load('cleanup', 'storage-cleanup.py')
    status = control.run('status', args.process_id, args.windows_session_id)
    if (Path(status.get('appDirectory', '')).resolve() != app or status.get('captureStorageVersion') != 1
            or status.get('pilotState') != 'idle' or status.get('serviceOwnsPilot') is not True
            or status.get('heartbeatFresh') is not True or status.get('activeRequestId') is not None):
        raise SystemExit('Live idle owned controller with native retention is required')
    if cleanup.digest(app / 'BetterGI.dll').lower() != args.expected_dll_sha256.lower():
        raise SystemExit('Installed DLL differs from the validated build')
    observation = json.loads((app / 'User/JsScript/ActOnePilot/observation.json').read_text(encoding='utf-8-sig'))
    age = time.time() * 1000 - observation['timestamp']
    if observation['session'] != status['scriptSession'] or observation['frameId'] != status['frameId'] or not 0 <= age <= 30000:
        raise SystemExit('A fresh screenshot observation is required; heartbeat alone is insufficient')
    protected = [app] + [p.resolve(strict=True) for p in args.protect]
    record = dict(verifiedAtUnixMs=int(time.time()*1000), status=status, dllSha256=args.expected_dll_sha256,
                  screenshotTimestamp=observation['timestamp'], gamePauseVerified=False,
                  protectedDirectories=list(map(str, protected)))
    (root / 'artifacts/runtime-installation-verified.json').write_text(json.dumps(record, indent=2))
    plan = retirement_plan(root, app, protected)
    output = root / 'artifacts/retention-superseded-build-candidates.json'
    if args.cleanup_manifest:
        output = args.cleanup_manifest.resolve(strict=True)
        approved_plan = json.loads(output.read_text(encoding='utf-8-sig'))
        identity = lambda row: (str(Path(row['path']).resolve()).lower(), row['bytes'], row['sha256'].lower())
        if sorted(map(identity, approved_plan['candidates'])) != sorted(map(identity, plan['candidates'])):
            raise SystemExit('Previously reviewed retirement candidates differ from the verified current inventory')
    else:
        output.write_text(json.dumps(plan, indent=2))
    checkpoint_path = app / 'User/ExternalControl/retention-checkpoint.json'
    checkpoint = json.loads(checkpoint_path.read_text(encoding='utf-8-sig'))
    if checkpoint.get('dllSha256', '').lower() != args.expected_dll_sha256.lower():
        raise SystemExit('Runtime startup checkpoint differs from the validated build')
    checkpoint.update(state='cleanup-approval-required' if plan['files'] else 'completed',
                      verifiedAtUnixMs=record['verifiedAtUnixMs'], cleanupManifest=str(output),
                      cleanupManifestSha256=cleanup.digest(output))
    temporary = checkpoint_path.with_suffix('.verified.tmp')
    temporary.write_text(json.dumps(checkpoint, indent=2))
    temporary.replace(checkpoint_path)
    print(json.dumps(dict(verified=True, retirementFiles=plan['files'], retirementBytes=plan['bytes'],
                          manifest=str(output), manifestSha256=cleanup.digest(output))))
