"""One guarded stationary camera inspection; preserve the measured position, never retry."""
import argparse, json, subprocess, sys
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--dx', type=int, required=True)
p.add_argument('--dy', type=int, default=0)
a = p.parse_args()
if not -750 <= a.dx <= 750 or not -500 <= a.dy <= 500 or not (a.dx or a.dy):
    raise SystemExit('One bounded nonzero camera turn required')
path = Path('artifacts/act-two-chart-position-latest.json')
c = json.loads(path.read_text(encoding='utf-8-sig'))
frame, session = c['controllerFrame'], c['session']
witness = c['steps'][-1]['result']['pauseProof']['sourceFrameId']
plan = [sys.executable, 'tools/quest-pilot/act-two-field-plan.py', '--frame', str(frame),
        '--witness', str(witness), '--mode', 'actions', '--region-map-witness',
        str(c['positionEvidence']['frameId']), '--visual-position-reviewed', '--actions',
        json.dumps([dict(type='look', dx=a.dx, dy=a.dy)])]
subprocess.run(plan, check=True, stdout=subprocess.DEVNULL, timeout=10)
r = subprocess.run([sys.executable, 'tools/quest-pilot/act-two-command-result.py', 'questStep',
    '--step', 'actTwoField', '--frame', str(frame), '--session', session,
    '--expected-windows-session-id', '7'], check=True, capture_output=True, text=True,
    encoding='utf-8', timeout=95)
t = json.loads(r.stdout.strip())
v = t.get('result') or {}
if (t.get('controllerState') != 'idle' or not v.get('pauseVerified')
        or v.get('actions') != 1 or v.get('health') != dict(current=4015, max=4015)):
    raise SystemExit('Camera inspection stopped/changed; inspect exact terminal, no follow-up')
c['steps'].append(t)
c['controllerFrame'] = t['frameId']
c['lastCameraOnlyRefresh'] = dict(terminalId=t['terminalId'], movementInputs=0,
    fieldFrame=v.get('fieldFrameId'), positionEvidenceNotRecaptured=True)
path.write_text(json.dumps(c, indent=2), encoding='utf-8')
print(json.dumps(c['lastCameraOnlyRefresh'] | dict(controllerFrame=t['frameId'], pauseVerified=True)))
