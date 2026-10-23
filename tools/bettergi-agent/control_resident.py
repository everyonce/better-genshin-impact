"""Pause, resume, stop, or change the goal of an existing run-bound resident agent."""
import argparse
import json
from pathlib import Path
import uuid

from resident_runtime import atomic_json, read_command
from navigation_idle_recovery import GOAL_INTENTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', required=True)
    parser.add_argument('--command', choices=('run', 'pause', 'stop'))
    parser.add_argument('--goal-embedding', help='Validated Open P2P embedding JSON; retain the current command unless overridden')
    parser.add_argument('--goal-intent', choices=GOAL_INTENTS,
                        help='Intent of this new goal; omitted new goals are unspecified and exempt from idle recovery')
    args = parser.parse_args()
    if args.command is None and args.goal_embedding is None:
        parser.error('Supply --command or --goal-embedding')
    if args.command == 'stop' and args.goal_embedding is not None:
        parser.error('A stop cannot also request a new goal')
    if args.goal_intent is not None and args.goal_embedding is None:
        parser.error('goal-intent requires a new goal-embedding request')
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
    command = args.command or previous['command']
    if previous['command'] == 'stop' and (command != 'stop' or args.goal_embedding is not None):
        raise ValueError('Stop is terminal; start a new resident run to resume')
    # Preserve an outstanding goal across pause/run writes; never silently cancel it.
    document = {key: previous[key] for key in ('goalRequestId', 'goalEmbedding', 'goalIntent') if key in previous}
    document.update(version=1, runId=run_id, command=command)
    if args.goal_embedding is not None:
        document.update(goalRequestId=uuid.uuid4().hex, goalEmbedding=str(Path(args.goal_embedding).resolve()),
                        goalIntent=args.goal_intent or 'unspecified')
    if len(json.dumps(document, indent=2, allow_nan=False).encode('utf-8')) > 2048:
        raise ValueError('The goal command would exceed 2048 bytes')
    atomic_json(path, document)
    print(json.dumps({'runId': run_id, 'requested': command, 'file': str(path.resolve()),
                      'goalRequestId': document.get('goalRequestId'), 'goalEmbedding': document.get('goalEmbedding'),
                      'goalIntent': document.get('goalIntent')}))


if __name__ == '__main__':
    main()
