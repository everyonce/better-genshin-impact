"""Open the map, measure its centered position, then restore Inventory; no movement/retry."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--frame', type=int, required=True)
p.add_argument('--session', required=True)
p.add_argument('--fast', action='store_true', help='Opt-in one-request map capture/close/pause; legacy remains available')
a = p.parse_args()
root = Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
frame = a.frame
started = time.monotonic()
evidence = {'session': a.session, 'steps': [], 'movementInputs': 0}


def step(name):
    global frame
    state = json.loads((root/'controller-status.json').read_text(encoding='utf-8-sig'))
    if state['state'] != 'idle' or state.get('activeRequestId') or state['session'] != a.session or state['frameId'] != frame:
        raise SystemExit('Controller changed; inspect before further input')
    r = subprocess.run([sys.executable, 'tools/quest-pilot/act-two-command-result.py', 'questStep',
                        '--step', name, '--frame', str(frame), '--session', a.session,
                        '--expected-windows-session-id', '7'], capture_output=True, text=True, encoding='utf-8', timeout=95)
    if r.returncode:
        raise SystemExit(r.stdout+r.stderr)
    q = json.loads(r.stdout.strip())
    evidence['steps'].append(q)
    frame = q['frameId']
    if q['status'] == 'failed' or q['controllerState'] != 'idle':
        raise SystemExit('Charting stage failed; no retry: '+str(q))
    return q.get('result') or {}


if a.fast:
    plan={'reviewed':True,'session':a.session,'frameId':frame,'createdAt':round(time.time()*1000),'closeMapAndPause':True}
    (root/'act-two-chart-request.json').write_text(json.dumps(plan),encoding='utf-8')
opened = step('actTwoWorldMap')
if opened.get('menuOpened') is not True:
    raise SystemExit('Map not verified; no localization attempted')
map_frame=opened.get('mapFrameId',opened.get('frameId'))
if opened.get('chartCycle') is True:
    if opened.get('pauseVerified') is not True:raise SystemExit('Fast chart lacks verified Inventory; inspect current state')
else:
    closed=step('actTwoMapClose')
    if closed.get('pauseVerified') is not True:raise SystemExit('Charting ended without verified pause; inspect current state')
# Native matching only reads the retained map, so do it after verified pause.
pose_error=None
match_started=time.monotonic()
r=subprocess.run([sys.executable,'tools/quest-pilot/full_map_position.py','--frame',str(map_frame),'--session',a.session],capture_output=True,text=True,encoding='utf-8',timeout=30)
evidence['offlineLocalizationWallMs']=round((time.monotonic()-match_started)*1000)
evidence['fastCycle']=opened.get('chartCycle') is True
if r.returncode:pose_error=r.stderr.strip() or r.stdout.strip()
else:evidence['positionEvidence']=json.loads(r.stdout.strip())
evidence.update(controllerFrame=frame, pauseVerified=True, elapsedMs=round((time.monotonic()-started)*1000),
                localizationError=pose_error, navigationAuthorized=False)
Path('artifacts/act-two-chart-position-latest.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
print(json.dumps({'controllerFrame': frame, 'pauseVerified': True, 'elapsedMs': evidence['elapsedMs'],
                  'position': (evidence.get('positionEvidence') or {}).get('position'), 'localizationError': pose_error}))
if pose_error:
    raise SystemExit(2)
