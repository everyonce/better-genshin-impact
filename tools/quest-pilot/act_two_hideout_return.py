"""One reviewed return segment at a time; no distance-only route resumption."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def walk(n, ms):
    return [dict(type='key', key='VK_W', ms=ms) for _ in range(n)]


# Actual successful 02:31-02:54 third return. Bounds are stop conditions,
# not permission to identify a location from quest distance alone.
SEGMENTS = [
    dict(name='waypoint-road', source=[2596, 2607], heading=[25, 31], distance=[166, 170],
         exitHeading=[169, 177], exitDistance=[156, 162],
         actions=[dict(type='look', dx=750, dy=0), dict(type='look', dx=750, dy=150)] + walk(5, 600)),
    dict(name='road-before-bend', source=[2607, 2619], heading=[169, 177], distance=[156, 162],
         exitHeading=[169, 177], exitDistance=[133, 139], actions=walk(8, 800)),
    dict(name='first-bend', source=[2619, 2631], heading=[169, 177], distance=[133, 139],
         exitHeading=[139, 147], exitDistance=[104, 114],
         actions=[dict(type='look', dx=-300, dy=0)] + walk(7, 800)),
    dict(name='hold-bend-heading', source=[2631, 2641], heading=[139, 147], distance=[104, 114],
         exitHeading=[139, 147], exitDistance=[83, 93], actions=walk(6, 800)),
]

# Replace the unverified historical tail with the actual fifth-return ground
# transitions. Keep the camera-only inspections as separate review boundaries.
recorded = json.loads((Path(__file__).with_name('routes') / 'act-two-hideout-fifth-return.json').read_text(encoding='utf-8'))
for row in recorded['segments'][5:13]:
    entry, end = row['entry'], row['exit']
    distance = lambda state: int(re.search(r'(\d+)m', state['objectives'][-1]).group(1))
    SEGMENTS.append(dict(name='reviewed-' + row['receipt'][8:16],
        source=[entry['frame'], end['frame']], heading=[entry['heading']-4, entry['heading']+4],
        distance=[distance(entry)-4, distance(entry)+4],
        exitHeading=[end['heading']-4, end['heading']+4], exitDistance=[distance(end)-4, distance(end)+4],
        actions=row['actualActions'], requiredLandmarks=row['landmarks']))


def checkpoint(observation, heading_bounds, distance_bounds):
    h = observation.get('hud', {})
    if (not h.get('world') or not h.get('groundControls') or h.get('climbing')
            or h.get('flying') or h.get('swimming') or h.get('enemyBars')
            or h.get('health') != dict(current=4015, max=4015)):
        raise ValueError('Full-health grounded Kaeya without threats required')
    objectives = h.get('objectives', [])
    if "Enter Raptor's Hideout" not in objectives:
        raise ValueError('Exact hideout objective required')
    distances = [int(m.group(1)) for text in objectives
                 if (m := re.fullmatch(r'(?:Higher\s*)?(\d+)m', text.strip()))]
    if len(distances) != 1 or not distance_bounds[0] <= distances[0] <= distance_bounds[1]:
        raise ValueError('Route distance checkpoint mismatch; no timing adjustment or skip')
    # Fogged map coordinates/angles must never override the native compass.
    heading = h.get('compassAngle')
    if not isinstance(heading, (int, float)) or not heading_bounds[0] <= heading <= heading_bounds[1]:
        raise ValueError('Native camera heading mismatch')


def validate_entry(observation, segment, review, previous, now):
    if len(review.strip()) < 60 or not all(token in review.lower() for token in ['ground', 'left', 'right']):
        raise ValueError('Describe fresh ground corridor and landmarks on left and right')
    if not 0 <= now - observation.get('timestamp', 0) <= 120000:
        raise ValueError('Fresh terrain observation required (120 seconds)')
    spec = SEGMENTS[segment]
    checkpoint(observation, spec['heading'], spec['distance'])
    if segment and (not previous or previous.get('segment') != segment - 1
                    or previous.get('session') != observation.get('session')
                    or previous.get('worldFrame') != observation.get('frameId')
                    or previous.get('exitPassed') is not True):
        raise ValueError('Missing verified immediate predecessor; no partial road reuse')
    return spec


def finish_first_road(observation, previous, review, now):
    """One correction at the visible signpost, never a repeated forward loop."""
    if (not previous or previous.get('segment') != 1 or previous.get('exitPassed') is not False
            or previous.get('completionStep') or previous.get('worldFrame') != observation.get('frameId')
            or previous.get('session') != observation.get('session')
            or 'signpost' not in review.lower() or len(review) < 60
            or not 0 <= now - observation.get('timestamp', 0) <= 120000):
        raise ValueError('One fresh signpost correction after segment1 only')
    checkpoint(observation, [169, 177], [140, 145])
    return dict(SEGMENTS[1], actions=walk(2, 600))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frame', type=int, required=True)
    p.add_argument('--witness', type=int, required=True)
    p.add_argument('--map', type=int, required=True)
    p.add_argument('--session', required=True)
    p.add_argument('--segment', type=int, choices=range(len(SEGMENTS)), required=True)
    p.add_argument('--landmark-review', required=True)
    p.add_argument('--validate-only', action='store_true')
    p.add_argument('--finish-first-road', action='store_true')
    a = p.parse_args()
    root = Path(os.environ['BETTERGI_PILOT_APP_DIR']) / 'User/JsScript/ActOnePilot'
    read = lambda path: json.loads(path.read_text(encoding='utf-8-sig'))
    observation = lambda frame: read(root / 'observations' / a.session / f'frame-{frame:04}.json')
    state = read(root / 'controller-status.json')
    if (state['session'] != a.session or state['frameId'] != a.frame or state['state'] != 'idle'
            or state.get('activeRequestId') or state.get('windowsSessionId') != 7):
        raise ValueError('Controller/session changed; no input')
    history = Path('artifacts/act-two-hideout-return-segment-latest.json')
    previous = read(history) if history.exists() else None
    if a.finish_first_road:
        if a.segment != 1:
            raise ValueError('Completion step belongs to segment1 only')
        spec = finish_first_road(observation(a.witness), previous, a.landmark_review, time.time() * 1000)
    else:
        spec = validate_entry(observation(a.witness), a.segment, a.landmark_review, previous, time.time() * 1000)
    command = [sys.executable, 'tools/quest-pilot/act-two-field-plan.py', '--frame', str(a.frame),
               '--witness', str(a.witness), '--region-map-witness', str(a.map),
               '--visual-position-reviewed', '--actions', json.dumps(spec['actions'])]
    if a.validate_only:
        command.append('--validate-only')
    subprocess.run(command, check=True, timeout=20)
    if a.validate_only:
        return
    result = subprocess.run([sys.executable, 'tools/quest-pilot/act-two-command-result.py', 'questStep',
        '--step', 'actTwoField', '--frame', str(a.frame), '--session', a.session,
        '--expected-windows-session-id', '7'], capture_output=True, text=True, encoding='utf-8', timeout=95)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    terminal = json.loads(result.stdout)
    value = terminal['result']
    proof = value.get('pauseProof') or {}
    report = dict(segment=a.segment, name=spec['name'], session=a.session, entryFrame=a.witness,
                  landmarkReview=a.landmark_review, terminal=terminal, exitPassed=False,
                  completionStep=a.finish_first_road)
    try:
        if (terminal['controllerState'] != 'idle' or not value.get('pauseVerified')
                or not proof.get('verified') or value.get('actions') != len(spec['actions'])
                or value.get('reason') != 'Bounded field batch ended; inspect outcome'):
            raise ValueError('Segment did not finish with verified pause')
        report['worldFrame'] = proof['sourceFrameId']
        checkpoint(observation(report['worldFrame']), spec['exitHeading'], spec['exitDistance'])
        report['exitPassed'] = True
    finally:
        history.write_text(json.dumps(report, indent=2), encoding='utf-8')
        with Path('artifacts/act-two-hideout-return-segments.jsonl').open('a', encoding='utf-8') as ledger:
            ledger.write(json.dumps(report) + '\n')
        print(json.dumps(report))
    # Always return for fresh landmark review. Never turn solely on the distance.


if __name__ == '__main__':
    main()
