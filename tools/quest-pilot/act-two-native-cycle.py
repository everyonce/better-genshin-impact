"""Run at most three already guarded native rotations, preserving every receipt.

Stops on a refused/uncertain command, missing pause, low health, changed session,
completed counter or two rotations without a confirmed counter increment.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def counter(observation):
    for value in observation.get('hud', {}).get('objectives', []):
        match = re.fullmatch(r'Defeatallopponents([0-7])/7', ''.join(value.split()))
        if match:
            return int(match[1])
    return None


def continuation_reason(result, observation, baseline, unchanged):
    if not result.get('nativeReturned') or not result.get('pauseVerified'):
        return 'Native rotation or verified pause missing'
    hud = observation.get('hud', {})
    hp = hud.get('health') or {}
    if (not hud.get('world') or hud.get('climbing') or not hud.get('groundControls')
            or hp.get('max') != baseline['max'] or hp.get('current', 0) < baseline['max'] * .7
            or baseline['current'] - hp.get('current', 0) > baseline['max'] * .15):
        return 'Health or field state changed'
    if counter(observation) == 7:
        return 'Encounter counter completed'
    if unchanged >= 2:
        return 'Two rotations without a confirmed counter increment; inspect target/range'
    if counter(observation) is None and not hud.get('enemyBars'):
        return 'No current encounter counter or targets; inspect completion'
    return None


def main():
    parser = argparse.ArgumentParser()
    for key in ['frame', 'witness', 'map']:
        parser.add_argument('--' + key, type=int, required=True)
    parser.add_argument('--session', required=True)
    a = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    root = Path(os.environ['BETTERGI_PILOT_APP_DIR']) / 'User/JsScript/ActOnePilot'
    read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
    observation = read(root / 'observations' / a.session / f'frame-{a.witness:04}.json')
    baseline = observation['hud']['health']
    frame, witness, unchanged = a.frame, a.witness, 0
    started = time.time()
    report = dict(session=a.session, startFrame=frame, startedAt=started, rotations=[])
    output = repo / f'artifacts/act-two-native-cycle-{frame}.json'

    def save():
        report['elapsedSeconds'] = round(time.time() - started, 3)
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')

    def run(args, timeout):
        value = subprocess.run([sys.executable, *args], cwd=repo, capture_output=True,
                               text=True, encoding='utf-8', errors='replace', timeout=timeout)
        if value.returncode:
            raise RuntimeError(value.stderr[-1500:] or value.stdout[-1500:])

    try:
        if counter(observation) not in range(7):
            raise RuntimeError('Fresh active Ley Line counter required')
        for _ in range(3):
            state = read(root / 'controller-status.json')
            if state['state'] != 'idle' or state['frameId'] != frame or state['session'] != a.session:
                raise RuntimeError('Controller frame/session changed')
            run(['tools/quest-pilot/act-two-field-plan.py', '--frame', str(frame), '--witness', str(witness),
                 '--region-map-witness', str(a.map), '--visual-position-reviewed', '--mode', 'combat',
                 '--enemy-level', '13', '--native-combat', '--actions', '[]'], 10)
            run(['tools/quest-pilot/act-one-command.py', 'questStep', '--step', 'actTwoField', '--frame', str(frame),
                 '--session', a.session, '--expected-windows-session-id', '7', '--compact', '--wait-seconds', '30'], 40)
            receipt = read(root / 'receipt.json')
            result = receipt.get('details', {}).get('result') or {}
            report['rotations'].append(dict(receipt=receipt['id'], result=result))
            save()
            if receipt['session'] != a.session or receipt['frameId'] <= frame or not result.get('fieldFrameId'):
                raise RuntimeError('Receipt identity/outcome changed; no retry')
            observation = read(root / 'observations' / a.session / f"frame-{result['fieldFrameId']:04}.json")
            unchanged = 0 if (result.get('killsConfirmed') or 0) > 0 else unchanged + 1
            reason = continuation_reason(result, observation, baseline, unchanged)
            print(json.dumps(dict(rotation=len(report['rotations']), frame=receipt['frameId'],
                                  counter=counter(observation), health=observation['hud'].get('health'), stop=reason)), flush=True)
            if reason:
                report['reason'] = reason
                break
            frame, witness = receipt['frameId'], result['fieldFrameId']
        report['status'] = 'stopped-at-bounded-checkpoint'
    except Exception as error:
        report.update(status='stopped', reason=str(error))
        save()
        raise
    save()


if __name__ == '__main__':
    main()
