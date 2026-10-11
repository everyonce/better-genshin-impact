"""Submit one bounded mission to the BetterGI RDP controller; never replay on timeout."""
import argparse
import json
import os
import re
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = Path(os.environ.get('BETTERGI_PILOT_APP_DIR', REPO / 'artifacts/release-r8/BetterGI-English-win-x64'))
ROOT = APP / 'User/JsScript/ActOnePilot'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def atomic(path, value):
    pending = path.with_suffix('.pending.json')
    pending.write_text(json.dumps(value), encoding='utf-8')
    os.replace(pending, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mission', choices=['observe', 'stop', 'keyPress', 'look', 'navigation', 'dialogue', 'combat', 'recover', 'questStep', 'cancel'])
    parser.add_argument('--session', required=True)
    parser.add_argument('--frame', type=int)
    parser.add_argument('--key')
    parser.add_argument('--dx', type=int, help='bounded camera-look delta (-250..250, excluding zero)')
    parser.add_argument('--route', type=Path)
    parser.add_argument('--objective')
    parser.add_argument('--step')
    parser.add_argument('--deadline-ms', type=int, default=60000)
    parser.add_argument('--wait-seconds', type=int, default=15)
    args = parser.parse_args()
    if args.mission == 'cancel':
        atomic(ROOT / 'stop.json', {'session': args.session, 'createdAt': int(time.time() * 1000)})
        print('Cancellation requested; inspect terminal receipt before issuing another mission.')
        return
    observation = read(ROOT / 'observation.json')
    if observation['session'] != args.session or observation['frameId'] != args.frame:
        raise SystemExit('Session/frame changed: inspect the current observation.')
    request = dict(session=args.session, expectedFrameId=args.frame,
                   id='mission-' + uuid.uuid4().hex, createdAt=int(time.time() * 1000), mission=args.mission)
    if args.mission == 'keyPress':
        request['key'] = args.key
    if args.mission == 'look':
        if args.dx is None or args.dx == 0 or not -250 <= args.dx <= 250:
            raise SystemExit('--dx must be a nonzero integer from -250 through 250')
        request['dx'] = args.dx
    if args.mission == 'combat':
        request['objective'] = args.objective
        request['deadlineMs'] = args.deadline_ms
    if args.mission == 'questStep':
        if not args.step or not re.fullmatch(r'[a-z][A-Za-z0-9]{0,39}', args.step):
            raise SystemExit('--step must start lowercase and contain at most 40 ASCII letters/digits')
        request['step'] = args.step
    if args.mission == 'navigation':
        if not args.route:
            raise SystemExit('--route is required')
        route = read(args.route)
        request['waypoints'] = route['waypoints']
        request['objective'] = route['objective']
        request['deadlineMs'] = args.deadline_ms
    atomic(ROOT / 'request.json', request)
    print(json.dumps({'submitted': request['id'], 'session': args.session}), flush=True)
    deadline = time.monotonic() + args.wait_seconds
    while time.monotonic() < deadline:
        time.sleep(.2)
        try:
            receipt = read(ROOT / 'receipt.json')
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if receipt.get('id') == request['id'] and receipt.get('status') not in ('started', 'running'):
            print(json.dumps(receipt))
            latest = read(ROOT / 'observation.json')
            print(json.dumps({'session': latest['session'], 'frameId': latest['frameId'],
                              'screenshot': str(ROOT / latest['screenshotPath']),
                              'observation': latest}))
            return
    print(json.dumps({'pending': request['id'], 'receiptPath': str(ROOT / 'receipt.json'),
                      'instruction': 'Poll this receipt and current process. Do not replay or restart on timeout.'}))


if __name__ == '__main__':
    main()
