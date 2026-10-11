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


def compact_ocr(rows):
    """Drop the UID label and a separate adjacent numeric account-ID OCR row."""
    rows = rows if isinstance(rows, list) else []
    uid_rows = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        text = str(row.get('text', '')).strip()
        match = re.fullmatch(r'UID\s*:?\s*(\d{6,})?', text, re.IGNORECASE)
        if match:
            uid_rows.append((index, row))

    excluded = {index for index, _ in uid_rows}
    for _, uid in uid_rows:
        uid_x = uid.get('x')
        uid_y = uid.get('y')
        uid_width = uid.get('width', 0)
        if not all(isinstance(value, (int, float)) for value in (uid_x, uid_y, uid_width)):
            continue
        for index, row in enumerate(rows):
            if index in excluded or not isinstance(row, dict):
                continue
            if not re.fullmatch(r'\d{6,}', str(row.get('text', '')).strip()):
                continue
            x, y = row.get('x'), row.get('y')
            if not all(isinstance(value, (int, float)) for value in (x, y)):
                continue
            gap = x - (uid_x + uid_width)
            if -4 <= gap <= 40 and abs(y - uid_y) <= 8:
                excluded.add(index)

    return [row for index, row in enumerate(rows) if index not in excluded]


def compact_terminal(submitted_id, receipt, observation, screenshot):
    details = receipt.get('details') if isinstance(receipt.get('details'), dict) else {}
    return {
        'submittedId': submitted_id,
        'terminalId': receipt.get('id'),
        'status': receipt.get('status'),
        'reason': details.get('reason'),
        'result': details.get('result'),
        'elapsedMs': details.get('elapsedMs'),
        'session': observation.get('session'),
        'frameId': observation.get('frameId'),
        'screenshot': screenshot,
        'hud': observation.get('hud'),
        'ocr': compact_ocr(observation.get('ocr')),
    }


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
    parser.add_argument('--compact', action='store_true',
                        help='print a compact terminal receipt and filtered latest observation')
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
            latest = read(ROOT / 'observation.json')
            screenshot = str(ROOT / latest['screenshotPath'])
            if args.compact:
                print(json.dumps(compact_terminal(request['id'], receipt, latest, screenshot)))
            else:
                print(json.dumps(receipt))
                print(json.dumps({'session': latest['session'], 'frameId': latest['frameId'],
                                  'screenshot': screenshot, 'observation': latest}))
            return
    print(json.dumps({'pending': request['id'], 'receiptPath': str(ROOT / 'receipt.json'),
                      'instruction': 'Poll this receipt and current process. Do not replay or restart on timeout.'}))


if __name__ == '__main__':
    main()
