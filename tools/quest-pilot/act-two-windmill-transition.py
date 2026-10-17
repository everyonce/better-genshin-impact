"""Replay only the observed lower windmill ascent through guarded BetterGI requests.

Stops before release for fresh visual landing review. Never replays balcony travel.
No raw input, no retries, no unpause after an uncertain terminal.
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time


def matches(observation, expected):
    h = observation.get('hud') or {}; m = observation.get('map') or {}
    hp = h.get('health') or {}; objective = [''.join(t.split()) for t in h.get('objectives', [])]
    height = next((int(t[6:-1]) for t in objective if t.startswith('Higher') and t.endswith('m') and t[6:-1].isdigit()), None)
    heading = m.get('cameraAngle')
    if (m.get('map') != 'Teyvat' or hp != dict(current=4015, max=4015)
            or not h.get('world') or h.get('enemyBars') != []
            or 'Lookforthelocationintheriddle' not in objective
            or h.get('climbing') != expected['climbing']
            or not expected['climbing'] and not h.get('groundControls')
            or height is None or abs(height-expected['height']) > 1
            or not isinstance(heading, (int, float))
            or abs((heading-expected['heading']+180) % 360-180) > 15
            or math.hypot(m.get('x', 0)-expected['x'], m.get('y', 0)-expected['y']) > .75):
        return False
    if expected.get('minimumArcHeight'):
        arc = h.get('climbStamina') or {}; boxes = arc.get('boxes') or []
        if (arc.get('source') != 'same-frame-yellow-arc' or not boxes
                or not isinstance(arc.get('pixels'), (int, float)) or arc['pixels'] < 180
                or max(b['y']+b['height'] for b in boxes)-min(b['y'] for b in boxes) < expected['minimumArcHeight']):
            return False
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--frame', type=int, required=True); p.add_argument('--witness', type=int, required=True)
    p.add_argument('--session', required=True); p.add_argument('--landing-reviewed', action='store_true')
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    root = Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
    read = lambda path: json.loads(path.read_text(encoding='utf-8-sig'))
    recipe = read(repo/'tools/quest-pilot/act-two-windmill-transition.json')
    phases = recipe['landing'] if a.landing_reviewed else recipe['ascent']
    report = dict(startedAt=int(time.time()*1000), session=a.session, phases=[], status='running', inputsOwnedBy='BetterGI RDP7')
    output = repo/'artifacts/act-two-windmill-transition-latest.json'
    start = time.monotonic(); frame, witness = a.frame, a.witness
    def save():
        report['elapsedMs'] = round((time.monotonic()-start)*1000)
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    def command(args):
        q = subprocess.run([sys.executable, *args], cwd=repo, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=95)
        if q.returncode:
            raise RuntimeError(q.stderr[-1000:] or q.stdout[-1000:])
        return json.loads(q.stdout.strip().splitlines()[-1])
    try:
        for phase in phases:
            state = read(root/'controller-status.json')
            o = read(root/'observations'/a.session/f'frame-{witness:04}.json')
            if (time.monotonic()-start > 180 or state['state'] != 'idle' or state.get('activeRequestId')
                    or state['frameId'] != frame or state['session'] != a.session
                    or o['session'] != a.session or not matches(o, phase['before'])):
                raise RuntimeError('Phase endpoint, health, reserve, controller or deadline changed; no retry')
            args = ['tools/quest-pilot/act-two-field-plan.py', '--frame', str(frame), '--witness', str(witness), '--mode', phase['mode'], '--actions', json.dumps(phase['actions'])]
            if phase.get('climbProbe'): args.append('--climb-probe')
            if phase['mode'] == 'releaseClimb': args.append('--landing-reviewed')
            command(args)
            q = command(['tools/quest-pilot/act-two-command-result.py', 'questStep', '--step', 'actTwoField', '--frame', str(frame), '--session', a.session, '--expected-windows-session-id', '7'])
            report['phases'].append(dict(name=phase['name'], receipt=q)); save()
            r = q.get('result') or {}; proof = r.get('pauseProof') or {}
            if (q.get('controllerState') != 'idle' or not r.get('pauseVerified')
                    or proof.get('session') != a.session or not proof.get('verified')
                    or r.get('actions') != len(phase['actions'])
                    or r.get('reason') != 'Bounded field batch ended; inspect outcome'
                    or not r.get('fieldFrameId')):
                raise RuntimeError('Unconfirmed phase outcome; inspect without replaying')
            frame, witness = q['frameId'], r['fieldFrameId']
            after = read(root/'observations'/a.session/f'frame-{witness:04}.json')
            if not matches(after, phase['after']) or phase['mode'] == 'releaseClimb' and r.get('groundSettled') is not True:
                raise RuntimeError('Expected endpoint or stable landing not verified; no continuation')
            print(json.dumps(dict(phase=phase['name'], frame=frame, witness=witness)), flush=True)
        report['status'] = 'landed-verified-pause' if a.landing_reviewed else 'fresh-visual-landing-review-required'
        report['frame'], report['witness'] = frame, witness
    except Exception as error:
        report.update(status='stopped', reason=str(error)); raise
    finally:
        save()


if __name__ == '__main__':
    main()
