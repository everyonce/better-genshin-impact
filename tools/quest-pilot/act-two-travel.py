"""Compose verified map stages locally; never replay a pending request."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', required=True)
    parser.add_argument('--expected-windows-session-id', required=True, type=int)
    parser.add_argument('--destination', choices=['city', 'gate'], required=True)
    args = parser.parse_args()
    root = Path(os.environ['BETTERGI_PILOT_APP_DIR']) / 'User/JsScript/ActOnePilot'
    command = Path(__file__).with_name('act-one-command.py')
    started = time.monotonic()
    stages = [('actTwoWorldMap', None), ('actTwoMap', 'restoreCityZoom'), ('actTwoMap', 'translatedCityWaypoint' if args.destination == 'city' else 'translatedGateWaypoint'),
              ('actTwoMap', 'chooseWaypoint'), ('actTwoMap', 'teleport')]
    for step, action in stages:
        if time.monotonic() - started > 150:
            raise RuntimeError('Travel composition deadline exceeded; no further input sent.')
        state = read(root / 'controller-status.json')
        if state.get('session') != args.session or state.get('windowsSessionId') != args.expected_windows_session_id or state.get('state') != 'idle' or state.get('activeRequestId') or state.get('error'):
            raise RuntimeError('Controller changed or is not idle; no further input sent.')
        if action == 'restoreCityZoom':
            observation = read(root / 'observations' / args.session / f"frame-{state['frameId']}.json")
            labels = [r for r in observation.get('ocr', []) if r.get('text') == 'Mondstadt']
            if len(labels) == 1 and 119 <= labels[0].get('width', 0) <= 135:
                continue
        if action:
            plan = dict(session=args.session, frameId=state['frameId'], reviewed=True,
                        createdAt=int(time.time()*1000), action=action)
            pending = root / 'act-two-map-request.pending.json'
            pending.write_text(json.dumps(plan), encoding='utf-8')
            pending.replace(root / 'act-two-map-request.json')
        result = subprocess.run([sys.executable, str(command), 'questStep', '--step', step,
                                 '--session', args.session, '--frame', str(state['frameId']),
                                 '--expected-windows-session-id', str(args.expected_windows_session_id),
                                 '--wait-seconds', '45', '--compact'], capture_output=True, text=True, encoding='utf-8')
        if result.returncode:
            raise RuntimeError(result.stderr or 'Command failed; no retry sent.')
        messages = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
        submitted = next((m.get('submitted') for m in messages if m.get('submitted')), None)
        print(json.dumps({'step':step,'action':action,'request':submitted}),flush=True)
        if not submitted:
            raise RuntimeError('Missing request identifier; no further input sent.')
        # A command timeout is deliberately terminal for this composition. The
        # controller owns recovery; the caller inspects this exact receipt.
        if any(m.get('pending') for m in messages):
            raise RuntimeError(f'Request pending: {submitted}; inspect receipt, never replay.')
        receipt = read(root / 'receipts' / args.session / (submitted + '.json'))
        outcome = (receipt.get('details') or {}).get('result') or {}
        expected_status = ('completed', 'stopped') if action else ('completed',)
        if receipt.get('id') != submitted or receipt.get('session') != args.session or receipt.get('status') not in expected_status or (action and outcome.get('action') != action):
            raise RuntimeError('Stage failed; no further input sent.')
        observation = read(root / 'observations' / args.session / f"frame-{receipt['frameId']}.json")
        texts = [str(row.get('text', '')).strip() for row in observation.get('ocr', [])]
        if action == 'teleport':
            if not outcome.get('pauseVerified'):
                raise RuntimeError('Teleport did not verify a destination pause.')
        elif action == 'chooseWaypoint':
            if 'Teleport Waypoint' not in texts or 'Teleport' not in texts:
                raise RuntimeError('Unlocked waypoint panel was not observed.')
        elif action and action != 'restoreCityZoom':
            if 'Teleport Waypoint' not in texts:
                raise RuntimeError('Waypoint selection was not observed.')
        elif not observation.get('hud', {}).get('bigMap'):
            raise RuntimeError('World map was not observed.')
        final = read(root / 'controller-status.json')
        if final.get('state') != 'idle' or final.get('activeRequestId') or final.get('frameId') != receipt.get('frameId'):
            raise RuntimeError('Controller did not settle on the receipt frame.')
    print(json.dumps({'travelCompleted': args.destination, 'elapsedSeconds': round(time.monotonic()-started, 3)}))


if __name__ == '__main__':
    main()
