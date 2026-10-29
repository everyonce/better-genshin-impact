"""Independent camera-selection joins and like-for-like comparisons of verified patrol legs."""
from collections import Counter
import json
import math
from pathlib import Path
import statistics

from camera_response import CameraCalibration, require
from hybrid_routes import PATROL_STATIONS, STREET_PATROL_ROUTE, camera_correction, route_heading
from observation_timing import observation_timestamp


def yaw_reversals(frames):
    """Count observed changes of turn direction after 5° net yaw, resetting across capture/ready gaps."""
    previous, anchor, direction, count = None, None, 0, 0
    for f in frames:
        p = f.get('navigationPose') or {}
        gate = f.get('frameWorldReadiness') or {}
        now = observation_timestamp(f)
        if (p.get('state') != 'valid' or p.get('frameId') != f['frameId'] or p.get('layerId') != 'City_102'
                or gate.get('ready') is not True or (f.get('motionEvidence') or {}).get('status') != 'normal'
                or not .2 <= p.get('yawConfidence', 0) <= 1):
            previous = None
            continue
        yaw, epoch = p['yawDegrees'], gate.get('epoch')
        if previous is None or now-previous[0] > 250 or previous[1] != epoch:
            anchor, direction = yaw, 0
        change = (yaw-anchor+180)%360-180
        if abs(change) >= 5:
            sign = 1 if change > 0 else -1
            count += int(bool(direction and direction != sign))
            direction, anchor = sign, yaw
        previous = now, epoch
    return count


def audit_camera(parts, entries, recordings, frames, route, checkpoint):
    """Join each changed selection to original source pose, checkpoint, proposal journal and terminal receipt."""
    decisions = [d for p in parts for d in p.get('decisions', [])]
    def selected(d):
        return 'cameraCalibration' in d or (d.get('hybridNavigation') or {}).get('owner') == 'calibrated-camera'
    if not checkpoint and not any(selected(d) for d in decisions):
        require(not any(r.get('modelId') == 'calibrated-camera' for p in parts for r in p.get('receipts', [])),
                'Camera receipt has no calibrated selection')
        return dict(selected=0, accepted=0, applied=0, checkpointId=None)
    require(route == STREET_PATROL_ROUTE and checkpoint, 'Calibrated camera requires the patrol route and its checkpoint')
    calibration = CameraCalibration.load(checkpoint)
    receipts = [r for p in parts for r in p.get('receipts', [])]
    by_id = {r['requestId']: r for r in receipts}
    require(len(receipts) == len(by_id), 'Duplicate camera-trial terminal receipt')
    journal_terminals, journal_proposals, journal_accepted = {}, {}, {}
    for entry in entries:
        with (Path(recordings)/f"{entry['number']:05d}"/'events.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                e = json.loads(line)
                if e.get('type') == 'proposal' and (e.get('acceptance') or {}).get('type') == 'accepted':
                    rid = e['acceptance']['requestId']
                    require(rid not in journal_accepted, 'Duplicate accepted journal request')
                    journal_accepted[rid] = e
                if e.get('type') == 'proposal' and ('cameraCalibration' in e or
                        (e.get('hybridNavigation') or {}).get('owner') == 'calibrated-camera'):
                    require(e['frameId'] not in journal_proposals, 'Duplicate calibrated source proposal')
                    journal_proposals[e['frameId']] = e
                elif 'requestId' in e and 'appliedSteps' in e:
                    require(e['requestId'] not in journal_terminals, 'Duplicate journal terminal receipt')
                    journal_terminals[e['requestId']] = e
    last = None
    seen, totals = set(), Counter()
    for d in decisions:
        h, ack = d['hybridNavigation'], d.get('acceptance') or {}
        accepted = ack.get('type') == 'accepted'
        if selected(d):
            m, f = d.get('cameraCalibration') or {}, frames[d['frameId']]
            j = journal_proposals.pop(d['frameId'], {})
            require(all(k in j and j[k] == d.get(k) for k in ('cameraCalibration','hybridNavigation','acceptance','steps',
                    'observationTimestampMs','startBeforeMs')) and j.get('model') == 'calibrated-camera',
                    'Calibrated selection differs from its original proposal journal')
            p, gate = f['navigationPose'], f['frameWorldReadiness']
            t = observation_timestamp(f)
            require(h.get('owner') == 'calibrated-camera' and h.get('reason') == 'calibratedHeading'
                    and m.get('selected') is True and m.get('checkpointId') == calibration.checkpoint_id
                    and h['pose'] == p and p['state'] == 'valid' and p['frameId'] == f['frameId']
                    and p['layerId'] == 'City_102' and .99 <= p['positionConfidence'] <= 1 and .2 <= p['yawConfidence'] <= 1
                    and f.get('inputAvailable') is True and gate.get('ready') is True and gate.get('sourceFrameId') == f['frameId']
                    and gate.get('sourceFrame') == f['sourceFrame'] and f['motionEvidence']['status'] == 'normal'
                    and f['motionEvidence']['spaceKeyMatched'] is False
                    and d['observationTimestampMs'] == t and (d.get('startBeforeMs') == t+150
                    or ack.get('type') == 'notSubmitted' and d.get('startBeforeMs') is None),
                    'Calibrated turn lacks fresh world pose, source deadline or checkpoint provenance')
            target = h['toStation']
            require(h['target'] == target and target in PATROL_STATIONS, 'Wrong calibrated station target')
            heading = route_heading(p, PATROL_STATIONS[target])
            error = (heading-p['yawDegrees']+180)%360-180
            native = camera_correction(p['yawDegrees'], heading)
            gap = None
            if last is not None:
                previous = by_id.get(last[0])
                require(previous and journal_terminals.get(last[0]) == previous, 'Previous mouse lacks a unique journal terminal')
                gap = t-max(previous['endedAtMs'], last[1]+150)
            require('previousMouseRequestId' in m and m['previousMouseRequestId'] == (last[0] if last else None)
                    and 'msSinceLastMouse' in m and (m['msSinceLastMouse'] is None if gap is None else
                    isinstance(m['msSinceLastMouse'], (int,float)) and abs(m['msSinceLastMouse']-gap) < .001)
                    and (gap is None or gap >= calibration.data['settleGuardMs']), 'Wrong preceding mouse action or settle interval')
            dx = m.get('proposedMouseDx')
            cap = calibration.data['maxMouseDx']
            expected = max(-cap, min(cap, round(error/calibration.data['degreesPerCount'])))
            require(type(dx) is int and 5 < abs(error) <= 180 and abs(m['errorDegrees']-error) < .001
                    and m['nativeMouseDx'] == native and dx == expected and dx != native and dx*native > 0
                    and 1 <= abs(dx) <= 250 and type(m['elapsedUs']) in (int,float) and math.isfinite(m['elapsedUs'])
                    and m['elapsedUs'] >= 0, 'Changed camera pulse is inconsistent with its native correction or fitted gain')
            step = dict(keys=[], mouseDx=dx, mouseDy=0, durationMs=100)
            require(h.get('step') == step and d['steps'] == [step], 'Calibrated selection is not one pure horizontal turn')
            totals['selected'] += 1
            if accepted:
                rid = ack['requestId']
                r = by_id.get(rid, {})
                require(rid not in seen and r and r == journal_terminals.get(rid) and r['frameId'] == f['frameId']
                        and r['modelId'] == 'calibrated-camera' and ack['acceptedAtMs'] == r['acceptedAtMs']
                        and r['status'] in ('completed','cancelled','replaced','expired'), 'Wrong calibrated terminal attribution')
                seen.add(rid)
                totals['accepted'] += 1
                applied = r['appliedSteps']
                if applied:
                    s = applied[0]
                    require(len(applied) == 1 and s.get('keys') == [] and s['mouseDx'] == dx and s['mouseDy'] == 0 and
                            not s.get('buttons') and not s.get('mouseButtons') and r['acceptedAtMs'] <= s['startedAtMs'] and
                            t <= s['startedAtMs'] < t+150 and s['startedAtMs'] <= r['endedAtMs'],
                            'Calibrated receipt differs from the commanded pulse or missed its deadline')
                    totals['applied'] += 1
        if accepted:
            rid = ack['requestId']
            j = journal_accepted.pop(rid, {})
            require(j and all(j[k] == d[k] for k in ('frameId','acceptance','steps','observationTimestampMs')),
                    'Prior accepted mouse history differs from the journal')
            if any(s.get('mouseDx') or s.get('mouseDy') for s in j['steps']):
                last = rid, j['observationTimestampMs']
    require(not journal_accepted and not journal_proposals and seen == {k for k,r in by_id.items() if r.get('modelId') == 'calibrated-camera'},
            'Unattributed camera selection or receipt')
    return dict(selected=totals['selected'], accepted=totals['accepted'], applied=totals['applied'],
                checkpointId=calibration.checkpoint_id)


def compare_patrols(baseline, candidate):
    """Pair full circuits by ordinal and summarize each of their four directed legs separately."""
    require(baseline['routeId'] == candidate['routeId'] == STREET_PATROL_ROUTE, 'Comparison requires the same patrol')
    n = min(baseline['verifiedCircuits'], candidate['verifiedCircuits'])
    require(n and baseline['cameraCalibration']['selected'] == 0, 'Comparison requires full circuits and an uncalibrated baseline')
    def metrics(legs):
        return dict(medianLegMs=statistics.median(l['elapsedMs'] for l in legs),
                    totalLegMs=sum(l['elapsedMs'] for l in legs), appliedActions=sum(l['appliedActions'] for l in legs),
                    yawReversals=sum(l['yawReversals'] for l in legs),
                    commandReversals=sum(l['commandReversals'] for l in legs))
    result = []
    for i in range(4):
        a, b = [[c['legs'][i] for c in run['patrolCircuits'][:n]] for run in (baseline,candidate)]
        result.append(dict(fromStation=a[0]['fromStation'], toStation=a[0]['toStation'], baseline=metrics(a), candidate=metrics(b)))
    overall = [metrics([l for c in run['patrolCircuits'][:n] for l in c['legs']]) for run in (baseline,candidate)]
    return dict(pairedCircuits=n, directedLegs=result, baseline=overall[0], candidate=overall[1],
                yawReversalDefinition='Measured native yaw changes direction after 5 degrees of accumulated turn within a ready interval. Gaps over 250 ms reset the comparison.',
                commandReversalDefinition='Sign change between successive applied nonzero horizontal mouse pulses within one directed leg.')
