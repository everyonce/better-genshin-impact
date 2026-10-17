"""Refresh one regional map witness, close it, and verify pause. Never retries."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--frame', type=int, required=True)
p.add_argument('--session', required=True)
a = p.parse_args()
root = Path(os.environ['BETTERGI_PILOT_APP_DIR']) / 'User/JsScript/ActOnePilot'
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))

def command(step, frame):
    s = read(root / 'controller-status.json')
    if s['session'] != a.session or s['frameId'] != frame or s['state'] != 'idle' or s.get('activeRequestId'):
        raise RuntimeError('Controller changed; no input submitted')
    q = subprocess.run([sys.executable, 'tools/quest-pilot/act-two-command-result.py',
        'questStep', '--step', step, '--frame', str(frame), '--session', a.session,
        '--expected-windows-session-id', '7'], capture_output=True, text=True, encoding='utf-8', timeout=95)
    if q.returncode:
        raise RuntimeError(q.stdout[-2000:] + q.stderr[-1000:])
    r = json.loads(q.stdout.strip())
    if r['controllerState'] != 'idle' or r['frameId'] <= frame or r['status'] not in ['completed', 'stopped']:
        raise RuntimeError('Unexpected or uncertain terminal; inspect without replay')
    return r

opened = command('actTwoWorldMap', a.frame)
map_frame = opened['frameId']
map_path = root / 'observations' / a.session / f'frame-{map_frame}.json'
node = shutil.which('node')
if not node:
    raise RuntimeError('Node unavailable; map left open for inspection')
check = subprocess.run([node, '-e', "const fs=require('fs'),g=require(process.argv[1]),o=JSON.parse(fs.readFileSync(process.argv[2],'utf8').replace(/^\\uFEFF/,''));if(!g.regionalMap(o,Date.now(),process.argv[3]))process.exit(2);",
    str((root / 'act-two-field.js').resolve()), str(map_path.resolve()), a.session], timeout=5)
if check.returncode:
    raise RuntimeError('Fresh map does not match the regional guard; left open for inspection')
closed = command('actTwoMapClose', map_frame)
result = closed['result']
proof = result.get('pauseProof') or {}
if not result.get('pauseVerified') or not proof.get('verified') or proof.get('session') != a.session:
    raise RuntimeError('Fresh pause unverified; inspect before more input')
world_frame = proof['sourceFrameId']
world = read(root / 'observations' / a.session / f'frame-{world_frame}.json')
if world['session'] != a.session or world_frame <= map_frame or not world['hud']['world']:
    raise RuntimeError('Fresh world witness unavailable')
report = dict(mapFrame=map_frame, worldFrame=world_frame, controllerFrame=closed['frameId'],
              session=a.session, health=world['hud']['health'], objectives=world['hud']['objectives'],
              receipts=[opened['terminalId'], closed['terminalId']], pauseVerified=True)
Path('artifacts/act-two-regional-map-latest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
