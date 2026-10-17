"""Replay one reviewed route segment through existing guarded BetterGI missions.

No raw input, retries, or historical frame reuse. Every batch requires a fresh
successful receipt, full health, matching heading and verified inventory pause.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--frame', type=int, required=True)
p.add_argument('--witness', type=int, required=True)
p.add_argument('--map', type=int, required=True)
p.add_argument('--session', required=True)
p.add_argument('--segment', type=Path, help='Locally reviewed finite segment JSON with startHeading and batches')
a = p.parse_args()
repo = Path(__file__).resolve().parents[2]
root = Path(os.environ['BETTERGI_PILOT_APP_DIR']) / 'User/JsScript/ActOnePilot'
out = repo / 'artifacts/act-two-reviewed-replay-latest.json'
started = time.time()
report = dict(startedAt=started, session=a.session, startFrame=a.frame, batches=[])

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def observed_heading(observation):
    # Regional observation deliberately skips unreliable fog-map coordinates.
    value = observation.get('hud', {}).get('compassAngle')
    if value is None:
        value = (observation.get('map') or {}).get('cameraAngle')
    if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value < 360:
        raise RuntimeError('Fresh compass heading unavailable')
    return value

def save():
    report['elapsedSeconds'] = round(time.time() - started, 3)
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')

def command(args, timeout):
    r = subprocess.run([sys.executable, *args], cwd=repo, capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if r.returncode:
        raise RuntimeError(r.stderr[-1500:] or r.stdout[-1500:])

try:
    segment = read(a.segment) if a.segment else dict(startHeading=28, batches=[
        dict(actions=[dict(type='look', dx=dx, dy=0)] + [dict(type='key', key='VK_W', ms=800) for _ in range(moves)], heading=expected)
        for dx, moves, expected in [(700, 0, 97), (-350, 3, 68.5), (-90, 5, 59), (300, 5, 89.5)]])
    if not 1 <= len(segment['batches']) <= 12:
        raise RuntimeError('Segment must contain 1..12 reviewed batches')
    first = read(root / 'observations' / a.session / f'frame-{a.witness:04}.json')
    if abs((observed_heading(first) - segment['startHeading'] + 180) % 360 - 180) > 4:
        raise RuntimeError('Reviewed starting heading changed')
    frame, witness = a.frame, a.witness
    for batch in segment['batches']:
        state = read(root / 'controller-status.json')
        if state['session'] != a.session or state['frameId'] != frame or state['state'] != 'idle':
            raise RuntimeError('Controller ownership/frame changed')
        actions, expected = batch['actions'], batch['heading']
        if not actions or any(x.get('type') != 'look' and not (x.get('type') == 'key' and x.get('key') in ['VK_W', 'VK_A', 'VK_S', 'VK_D']) for x in actions):
            raise RuntimeError('Replay supports only bounded reviewed ground movement')
        command(['tools/quest-pilot/act-two-field-plan.py', '--frame', str(frame), '--witness', str(witness),
                 '--region-map-witness', str(a.map), '--visual-position-reviewed', '--mode', 'actions',
                 '--actions', json.dumps(actions)], 10)
        command(['tools/quest-pilot/act-one-command.py', 'questStep', '--step', 'actTwoField',
                 '--frame', str(frame), '--session', a.session, '--expected-windows-session-id', '7',
                 '--compact', '--wait-seconds', '40'], 50)
        receipt = read(root / 'receipt.json')
        result = receipt.get('details', {}).get('result', {})
        report['batches'].append(dict(receipt=receipt['id'], result=result))
        save()
        if (receipt['session'] != a.session or receipt['frameId'] <= frame
                or result.get('reason') != 'Bounded field batch ended; inspect outcome'
                or result.get('actions') != len(actions) or not result.get('pauseVerified')):
            raise RuntimeError('Batch outcome changed; inspect saved receipt without retrying')
        observation = read(root / 'observations' / a.session / f"frame-{result['fieldFrameId']:04}.json")
        hud = observation['hud']
        heading = observed_heading(observation)
        if (hud.get('health') not in [dict(current=n, max=n) for n in [2635,4015]] or hud.get('climbing')
                or not hud.get('world') or hud.get('enemyBars') or hud.get('objectives')
                or abs((heading - expected + 180) % 360 - 180) > 8):
            raise RuntimeError('Fresh health, heading or field conditions changed')
        frame, witness = receipt['frameId'], result['fieldFrameId']
        print(json.dumps(dict(batch=len(report['batches']), frame=frame, witness=witness, heading=heading)), flush=True)
    report['status'] = 'checkpoint-required'
except Exception as error:
    report['status'] = 'stopped'
    report['reason'] = str(error)
    save()
    raise
save()
