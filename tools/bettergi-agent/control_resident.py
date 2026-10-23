"""Pause, resume, or stop an existing resident agent through its run-bound local command file."""
import argparse
import json
from pathlib import Path

from resident_runtime import atomic_json, read_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', required=True)
    parser.add_argument('--command', required=True, choices=('run', 'pause', 'stop'))
    args = parser.parse_args()
    path = Path(args.file)
    # A controller must address an already-created run; it cannot create a new authority file.
    with path.open('rb') as stream:
        payload = stream.read(2049)
    if len(payload) > 2048:
        raise ValueError('Control file exceeds 2048 bytes')
    previous = json.loads(payload)
    run_id = previous.get('runId') if isinstance(previous, dict) else None
    if not isinstance(run_id, str) or len(run_id) != 32 or read_command(path, run_id)[1]:
        raise ValueError('The existing file does not identify a valid resident run')
    if previous['command'] == 'stop' and args.command != 'stop':
        raise ValueError('Stop is terminal; start a new resident run to resume')
    atomic_json(path, {'version': 1, 'runId': run_id, 'command': args.command})
    print(json.dumps({'runId': run_id, 'requested': args.command, 'file': str(path.resolve())}))


if __name__ == '__main__':
    main()
