"""Compose at most three reviewed field transitions through existing guarded missions.

No raw input and no retries. A missing/mismatched receipt stops the chain.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def next_checkpoint(receipt, submitted, session, frame, observation):
    result = receipt.get('result') or {}
    proof = result.get('pauseProof') or {}
    hud = observation.get('hud') or {}
    hp = hud.get('health') or {}
    if (receipt.get('submittedId') != submitted or receipt.get('terminalId') != submitted
            or receipt.get('session') != session or receipt.get('frameId', 0) <= frame
            or receipt.get('status') not in ('stopped', 'completed')
            or not result.get('pauseVerified') or not proof.get('verified')
            or proof.get('session') != session or observation.get('session') != session
            or observation.get('frameId') != result.get('fieldFrameId')
            or not hud.get('world') or hp.get('max') != 4015 or hp.get('current', 0) < 3614
            or hud.get('enemyBars') != []
            or not any(''.join(t.split()) == 'Gototheexampoint' for t in hud.get('objectives', []))):
        raise ValueError('Fresh terminal, pause, identity, health or quest evidence changed')
    return receipt['frameId'], observation['frameId']


def main():
    parser = argparse.ArgumentParser()
    for name in ('frame', 'witness'):
        parser.add_argument('--'+name, type=int, required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--segment', type=Path, required=True)
    a = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    root = Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
    read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
    segment = read(a.segment)
    batches = segment['batches']
    if not 1 <= len(batches) <= 3:
        raise ValueError('Chain must contain one to three reviewed transitions')
    start = time.monotonic()
    report = dict(startedAt=int(time.time()*1000), session=a.session, batches=[], status='running')
    output = repo/'artifacts/act-two-field-chain-latest.json'
    def save():
        report['elapsedMs'] = round((time.monotonic()-start)*1000)
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    def command(args):
        result = subprocess.run([sys.executable, *args], cwd=repo, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=45)
        if result.returncode:
            raise RuntimeError(result.stderr[-1000:] or result.stdout[-1000:])
        return [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    frame, witness = a.frame, a.witness
    try:
        for batch in batches:
            state = read(root/'controller-status.json')
            if state['session'] != a.session or state['frameId'] != frame or state['state'] != 'idle' or time.monotonic()-start > 60:
                raise RuntimeError('Controller changed or chain deadline reached')
            mode, actions = batch['mode'], batch['actions']
            if mode not in ('actions', 'climb', 'releaseClimb') or not 1 <= len(actions) <= 4:
                raise ValueError('Unsupported transition')
            args = ['tools/quest-pilot/act-two-field-plan.py','--frame',str(frame),'--witness',str(witness),
                    '--mode',mode,'--actions',json.dumps(actions)]
            if batch.get('climbProbe'):
                args.append('--climb-probe')
            if batch.get('landingReviewed'):
                args.append('--landing-reviewed')
            command(args)
            results = command(['tools/quest-pilot/act-one-command.py','questStep','--step','actTwoField',
                               '--frame',str(frame),'--session',a.session,'--expected-windows-session-id','7',
                               '--compact','--wait-seconds','35'])
            submitted = next(item['submitted'] for item in results if 'submitted' in item)
            receipt = next(item for item in results if 'terminalId' in item)
            report['batches'].append(receipt)
            save()
            result = receipt.get('result') or {}
            field = result.get('fieldFrameId')
            if not field:
                raise RuntimeError('No verified field result; inspect without replaying')
            observation = read(root/'observations'/a.session/f'frame-{field:04}.json')
            frame, witness = next_checkpoint(receipt, submitted, a.session, frame, observation)
            if result.get('reason') != 'Bounded field batch ended; inspect outcome' or result.get('actions') != len(actions):
                raise RuntimeError('Transition stopped early; inspect without replaying')
            hud = observation['hud']
            expected = batch.get('after')
            if expected == 'ground' and (hud.get('climbing') or not hud.get('groundControls')):
                raise RuntimeError('Expected landing not yet verified')
            if expected == 'climb' and not hud.get('climbing'):
                raise RuntimeError('Expected climb changed; no further input')
            print(json.dumps(dict(batch=len(report['batches']), frame=frame, witness=witness)), flush=True)
        report['status'] = 'checkpoint-required'
    except Exception as error:
        report.update(status='stopped', reason=str(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
