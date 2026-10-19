"""One guarded, four-view stationary wall survey; never retries or moves the avatar."""
import json
import os
import subprocess
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
root = Path(os.environ['BETTERGI_PILOT_APP_DIR']) / 'User/JsScript/ActOnePilot'
session = 'mvf7ifnp-30yiczwdy7v'
start_frame = 290
read = lambda path: json.loads(path.read_text(encoding='utf-8-sig'))


def state_at(frame):
    state = read(root / 'controller-status.json')
    if (state.get('session') != session or state.get('windowsSessionId') != 7
            or state.get('processId') != 11256 or state.get('state') != 'idle'
            or state.get('activeRequestId') or state.get('frameId') != frame):
        raise RuntimeError('Owned controller changed; no input submitted')
    return state


def command(step, frame):
    state_at(frame)
    proc = subprocess.run([sys.executable, 'tools/quest-pilot/act-two-command-result.py',
        'questStep', '--step', step, '--frame', str(frame), '--session', session,
        '--expected-windows-session-id', '7'], cwd=repo, capture_output=True,
        text=True, encoding='utf-8', timeout=95)
    if proc.returncode:
        raise RuntimeError(proc.stdout[-2500:] + proc.stderr[-1000:])
    result = json.loads(proc.stdout.strip())
    if result.get('controllerState') != 'idle' or result.get('frameId', 0) <= frame:
        raise RuntimeError('No quiescent terminal; inspect without replay')
    return result


def field(frame):
    return read(root / 'observations' / session / f'frame-{frame:04}.json')


def safe_field(obs):
    hud = obs.get('hud') or {}
    pose = obs.get('map') or {}
    hp = hud.get('health') or {}
    return (obs.get('session') == session and hud.get('world') is True
            and hud.get('groundControls') is True and not hud.get('climbing')
            and not hud.get('enemyBars') and hp == {'current': 4015, 'max': 4015}
            and pose.get('map') == 'Teyvat'
            and (pose.get('x', 999) + 839.9453125)**2
                + (pose.get('y', 999) - 2237.001953125)**2 <= 1
            and any(''.join(t.split()) == 'Lookforthelocationintheriddle'
                    for t in hud.get('objectives', [])))


def main():
    state_at(start_frame)
    pause = field(start_frame)
    if not any(row.get('text') == 'Inventory capacity 19/2600' for row in pause.get('ocr', [])):
        raise RuntimeError('Expected verified Inventory menu is absent')
    pre = command('actTwoFieldInspect', start_frame)
    pre_result = pre.get('result') or {}
    proof = pre_result.get('pauseProof') or {}
    if (not pre_result.get('pauseVerified') or not proof.get('verified')
            or proof.get('session') != session):
        raise RuntimeError('Fresh inspection did not restore Inventory pause')
    witness_id = pre_result.get('fieldFrameId')
    witness = field(witness_id)
    if not safe_field(witness):
        raise RuntimeError('Fresh position, health, ground, threat or objective changed')
    actions = [dict(type='look', dx=dx, dy=0) for dx in (-750, 750, 750, -750)]
    state_at(pre['frameId'])
    plan = subprocess.run([sys.executable, 'tools/quest-pilot/act-two-field-plan.py',
        '--frame', str(pre['frameId']), '--witness', str(witness_id),
        '--mode', 'actions', '--actions', json.dumps(actions)], cwd=repo,
        capture_output=True, text=True, encoding='utf-8', timeout=15)
    if plan.returncode:
        raise RuntimeError('Survey plan refused before camera input: ' + plan.stdout + plan.stderr)
    sweep = command('actTwoField', pre['frameId'])
    result = sweep.get('result') or {}
    end_proof = result.get('pauseProof') or {}
    end = field(result.get('fieldFrameId')) if result.get('fieldFrameId') else None
    if (not result.get('pauseVerified') or not end_proof.get('verified')
            or end_proof.get('session') != session or result.get('actions') != 4
            or not end or not safe_field(end)):
        raise RuntimeError('Survey stopped or changed; inspect terminal, no further input')
    views = []
    for path in sorted((root / 'observations' / session).glob('frame-*.json')):
        obs = read(path)
        if (witness_id <= obs.get('frameId', -1) <= end['frameId']
                and safe_field(obs)):
            views.append(dict(frame=obs['frameId'], cameraAngle=(obs.get('map') or {}).get('cameraAngle'),
                              screenshot=str(path.with_suffix('.png'))))
    report = dict(session=session, preflight=pre['terminalId'], sweep=sweep['terminalId'],
                  controllerFrame=sweep['frameId'], fieldFrame=end['frameId'],
                  pauseFrame=end_proof.get('pauseFrameId'), pauseVerified=True,
                  health=end['hud']['health'], position=end['map'],
                  actions=4, movementActions=0, views=views)
    (repo / 'artifacts/act-two-house-stationary-survey.json').write_text(
        json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
