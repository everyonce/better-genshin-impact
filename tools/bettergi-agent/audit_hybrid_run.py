"""Audit recorded fixed-route endpoint and software-input evidence; no game or GPU access."""
import argparse
import json
import math
from pathlib import Path
import statistics

from audit_camera_patrol import audit_camera, compare_patrols, yaw_reversals
from audit_destination_retries import RETRY, verify_retry_poses
from hybrid_routes import (COURTYARD_ROUTE, PATROL_STATIONS, STAIR_POST_ROUTE, STREET_PATROL_ROUTE,
                           camera_correction, route_heading, route_points)
from observation_timing import observation_timestamp


def require(condition, message):
    """Fail closed on incomplete evidence rather than inferring successful gameplay."""
    if not condition:
        raise ValueError(message)


# Derive the expected sequence independently of the planner's leg-advance logic.
PATROL_ORDER = ('stair-front', 'sidewalk-junction', 'west-lamp', 'sidewalk-junction', 'stair-front')


def destination_edges(plan):
    """Independently expand requests on the surveyed three-station line, including direction and ownership."""
    stations = PATROL_ORDER[:3]
    specs = plan.get('requests')
    require(plan.get('version') == 2 and plan.get('mode') == 'destinations' and plan.get('start') in stations
            and isinstance(specs, list) and 2 <= len(specs) <= 4
            and type(plan.get('confirmFirstArrival',False)) is bool, 'Invalid reviewed destination plan')
    edges = []
    here = stations.index(plan['start'])
    for ordinal, spec in enumerate(specs, 1):
        destination = spec.get('destination')
        require(destination in stations and spec.get('targets') == [destination] and 'circuits' not in spec,
                'Each request must name and photograph one reviewed destination')
        goal = stations.index(destination)
        require(goal != here, 'Destination request must require actual movement')
        step = 1 if goal > here else -1
        for index in range(here, goal, step):
            edges.append((stations[index], stations[index+step], ordinal, destination))
        here = goal
    return edges


def check_patrol_leg(row, completed, edges=None):
    """Bind source and target names to a particular traversal, including the two visits to B."""
    if edges is not None:
        require(0 <= completed < len(edges) and row.get('navigationMode') == 'itinerary'
                and row.get('segmentIndex') == completed
                and (row.get('fromStation'),row.get('toStation'),row.get('destinationOrdinal'),
                     row.get('requestedDestination')) == edges[completed], 'Directed edge or request differs from plan')
        return
    index = completed % 4
    require((row.get('segmentIndex'), row.get('circuit'), row.get('fromStation'), row.get('toStation')) ==
            (index, completed//4+1, PATROL_ORDER[index], PATROL_ORDER[index+1]), 'Patrol segment identity differs')


def audit_shadow(decisions, frames, receipts, entries, recordings, route, checkpoint, edges=None):
    """Reproduce archived shadow predictions directly from the named weights and original proposal inputs."""
    from steering_head import SteeringHead
    from train_steering import applied_label, steering_point
    head = SteeringHead.load(checkpoint)
    journal = {}
    for e in entries:
        with (Path(recordings)/f"{e['number']:05d}"/'events.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                if row.get('type') == 'proposal':
                    require(row['frameId'] not in journal, 'Duplicate shadow evaluation source')
                    journal[row['frameId']] = row
    elapsed, predictions, labelled, correct = [], 0, 0, 0
    for d in decisions:
        h, s, f = d['hybridNavigation'], d.get('steeringShadow') or {}, frames[d['frameId']]
        j = journal.pop(d['frameId'], {})
        require(s.get('checkpointId') == head.checkpoint_id and j.get('steeringShadow') == s
                and j.get('rawPolicySteps') == d.get('rawPolicySteps') and j.get('hybridNavigation') == h
                and j.get('model') == h.get('owner') and j.get('acceptance') == d.get('acceptance')
                and h.get('owner') in ('hybrid-native','open-p2p','calibrated-camera'),
                'Shadow result, source proposal, input ownership or checkpoint differs')
        point = steering_point(route, h, edges)
        require(point is not None and type(s.get('elapsedUs')) in (float,int) and math.isfinite(s['elapsedUs'])
                and s['elapsedUs'] >= 0, 'Missing shadow target or timing')
        prediction = head.predict(f, point, d.get('rawPolicySteps',h.get('modelSteps',[])))
        require('prediction' in s and s['prediction'] == prediction, 'Shadow score differs from exact checkpoint replay')
        elapsed.append(s['elapsedUs'])
        predictions += int(prediction is not None)
        label = applied_label(d, f, receipts.get((d.get('acceptance') or {}).get('requestId')))
        if label and prediction:
            labelled += 1
            correct += int(prediction['actionClass'] == label)
    require(not journal and elapsed, 'A shadow proposal is missing from the decision report')
    return dict(checkpointId=head.checkpoint_id, verifiedEvaluations=len(elapsed), classified=predictions,
                abstained=len(elapsed)-predictions, medianElapsedUs=statistics.median(elapsed),
                eligibleNativeLabels=labelled, nativeLabelMatches=correct)


def audit_patrol(start, endpoints, events, frames, parts, run, accepted, receipts, epoch, edges=None):
    """Require an actual arrival, release, traversal and software forward input for each directed leg."""
    require(run.get('runId') and all(p.get('residentRunId') == run['runId'] and p.get('model') == 'open-p2p'
            and p.get('policyMetadata', {}).get('graphCaptureValidated') is True
            and p.get('serverDroppedReceipts') == 0 for p in parts), 'Patrol lacks one resident GPU policy trial')
    ordered = sorted(frames.values(), key=lambda f: f['frameId'])
    require(all((f.get('sourceFrame') or {}).get('captureEpoch') == epoch for f in ordered)
            and all(a['sourceFrame']['timestamp100ns'] < b['sourceFrame']['timestamp100ns']
                    and observation_timestamp(a) < observation_timestamp(b) for a,b in zip(ordered, ordered[1:])),
            'Patrol recording changed capture generation or reused a source')
    check_patrol_leg(start, 0, edges)
    first, next_station = edges[0][:2] if edges is not None else PATROL_ORDER[:2]
    require(start.get('sourceEpoch') == epoch and start.get('station') == first and start.get('target') == next_station,
            'Patrol did not start at its reviewed admission station')
    samples = start.get('samples') or []
    require(len(samples) == 3 and samples[-1]['frameId'] == start['frameId'] and samples[-1]['atMs'] == start['atMs'],
            'Patrol admission lacks three source poses')
    for i, s in enumerate(samples):
        f = frames.get(s['frameId']) or {}
        p = f.get('navigationPose') or {}
        require(p.get('frameId') == s['frameId'] and p.get('state') == 'valid' and p.get('layerId') == 'City_102'
                and .99 <= p['positionConfidence'] <= 1 and .2 <= p['yawConfidence'] <= 1
                and (f.get('frameWorldReadiness') or {}).get('ready') is True
                and (f.get('motionEvidence') or {}).get('status') == 'normal'
                and f['motionEvidence'].get('spaceKeyMatched') is False and observation_timestamp(f) == s['atMs']
                and all(p[k] == s[k] for k in ('x','y','yawDegrees')) and math.dist((p['x'],p['y']), PATROL_STATIONS[first]) <= 2,
                'Unqualified or misplaced initial patrol sample')
        require(all(math.dist((s['x'],s['y']), (a['x'],a['y'])) <= 1.5 and
                    abs((s['yawDegrees']-a['yawDegrees']+180)%360-180) <= 3 for a in samples[:i])
                and (not i or s['frameId'] > samples[i-1]['frameId'] and s['atMs']-samples[i-1]['atMs'] >= 80),
                'Patrol admission samples are stale or unstable')
    held = {t['frameId'] for p in parts for t in p.get('controlTransitions', [])
            if t.get('state') == 'held' and t.get('reason') == 'hybridEndpoint'}
    walks = [[] for _ in endpoints]
    walk_sources = [[] for _ in endpoints]
    mouse_commands = [[] for _ in endpoints]
    applied_actions = [0 for _ in endpoints]
    require(all(request in accepted or r.get('modelId') == 'navigation-climb-drop-v1' for request,r in receipts.items()
                if r.get('appliedSteps')), 'Patrol includes unattributed input')
    for request, decision in accepted.items():
        selected = decision['hybridNavigation']
        leg = selected['completedLegs']
        require(type(leg) is int and 0 <= leg <= len(endpoints), 'Patrol decision belongs to an unknown leg')
        check_patrol_leg(selected, leg, edges)
        require(selected['target'] == selected['toStation'], 'Patrol decision steered toward another station')
        if leg == len(endpoints):
            continue  # No credit for work begun on an unfinished leg.
        lower = start['atMs'] if leg == 0 else endpoints[leg-1]['samples'][-1]['atMs']
        upper = endpoints[leg]['releaseAtMs']
        f = frames[decision['frameId']]
        p = f['navigationPose']
        require(lower <= observation_timestamp(f) < upper and p['state'] == 'valid' and p['frameId'] == f['frameId']
                and f['frameWorldReadiness']['ready'] is True, 'Patrol action is outside its active segment')
        steps = receipts[request].get('appliedSteps') or []
        applied_actions[leg] += int(bool(steps))
        for s in steps:
            if s.get('mouseDx'):
                mouse_commands[leg].append((s['startedAtMs'], 1 if s['mouseDx'] > 0 else -1))
            if s.get('keys') != ['W']:
                continue
            heading = route_heading(p, PATROL_STATIONS[selected['toStation']])
            require(s.get('mouseDy') == 0 and abs(s.get('mouseDx', 0)) <= 3 and
                    abs((p['yawDegrees']-heading+180)%360-180) <= 5,
                    'Applied patrol W was not aligned to the expected station')
            if receipts[request]['endedAtMs'] > s['startedAtMs']:
                walks[leg].append(s['startedAtMs'])
                if edges is not None:
                    walk_sources[leg].append((request, s['startedAtMs'], p['x'], p['y'], f['frameWorldReadiness']['epoch']))
    circuit_events = [e for e in events if e['type'] == 'hybridCircuitVerified']
    milestones = [e for e in events if e['type'] in (
        'hybridStartVerified','hybridEndpointVerified','hybridCircuitVerified','hybridDestinationVerified')]
    expected = [start]
    legs, circuits = [], []
    prior_at = start['atMs']
    for i, e in enumerate(endpoints):
        check_patrol_leg(e, i, edges)
        expected.append(e)
        station = edges[i][1] if edges is not None else PATROL_ORDER[i%4+1]
        require(e.get('routeId') == STREET_PATROL_ROUTE and e.get('station') == e['endpoint'] == station and walks[i],
                'Patrol station lacks a directed walk')
        arrival = frames.get(e.get('arrivalFrameId')) or {}
        pose = arrival.get('navigationPose') or {}
        gate = arrival.get('frameWorldReadiness') or {}
        require(e.get('arrivalFrameId') in held and pose.get('state') == 'valid' and pose.get('frameId') == arrival['frameId']
                and pose.get('layerId') == 'City_102' and .99 <= pose['positionConfidence'] <= 1
                and .2 <= pose['yawConfidence'] <= 1 and arrival['motionEvidence']['status'] == 'normal'
                and arrival['motionEvidence']['spaceKeyMatched'] is False
                and gate.get('ready') is True and type(gate.get('epoch')) is int and gate['epoch']+1 == e['releaseEpoch']
                and math.dist((pose['x'],pose['y']), PATROL_STATIONS[station]) <= 1.1
                and prior_at < observation_timestamp(arrival) <= e['releaseAtMs'], 'Unbound patrol arrival or release epoch')
        # A pair of stationary screenshots and an applied W could conceal a
        # jump between stations. Join a post-dispatch sample inside this leg.
        ax, ay = PATROL_STATIONS[e['fromStation']]
        bx, by = PATROL_STATIONS[station]
        length = math.hypot(bx-ax, by-ay)
        reaction_at, arrival_at = min(walks[i])+60, observation_timestamp(arrival)
        middle = None
        transit_action = None
        for f in ordered:
            if not reaction_at <= observation_timestamp(f) < arrival_at:
                continue
            p = f.get('navigationPose') or {}
            if (p.get('state') != 'valid' or p.get('frameId') != f['frameId'] or p.get('layerId') != 'City_102'
                    or not .99 <= p['positionConfidence'] <= 1 or f['frameWorldReadiness']['ready'] is not True
                    or f['motionEvidence']['status'] != 'normal' or f['motionEvidence']['spaceKeyMatched'] is not False):
                continue
            x, y = p['x']-ax, p['y']-ay
            if (.2 <= (x*(bx-ax)+y*(by-ay))/length**2 <= .8 and abs(x*(by-ay)-y*(bx-ax))/length <= 4):
                if edges is not None:
                    # The transit frame must show forward displacement from a recently applied W's own source.
                    transit_action = next((rid for rid, at, ox, oy, gate in reversed(walk_sources[i])
                            if gate == f['frameWorldReadiness']['epoch'] and 60 <= observation_timestamp(f)-at <= 1000
                            and ((p['x']-ox)*(bx-ax)+(p['y']-oy)*(by-ay))/length >= .1), None)
                    if transit_action is None:
                        continue
                middle = f['frameId']
                break
        require(middle, 'Missing post-dispatch position inside the active patrol leg')
        for s in e['samples']:
            f = frames[s['frameId']]
            require(f['frameWorldReadiness']['epoch'] == e['releaseEpoch'] and f['motionEvidence']['status'] == 'normal'
                    and f['motionEvidence']['spaceKeyMatched'] is False, 'Patrol station sample is outside its release epoch')
        end_at = e['samples'][-1]['atMs']
        require(0 < end_at-prior_at <= 35000 and abs(e['legElapsedMs']-(end_at-prior_at)) < .01,
                'Patrol leg elapsed time or deadline differs')
        require(not any(e['releaseAtMs'] <= s['startedAtMs'] <= end_at
                        for r in receipts.values() for s in r.get('appliedSteps', [])),
                'Patrol dispatched input before station verification finished')
        turns = [sign for _, sign in sorted(mouse_commands[i])]
        leg_frames = (f for f in ordered if prior_at <= observation_timestamp(f) <= arrival_at)
        helpers = [r for r in receipts.values() if r.get('modelId') == 'navigation-climb-drop-v1'
                   and r['appliedSteps'] and prior_at <= r['appliedSteps'][0]['startedAtMs'] < end_at]
        legs.append(dict(fromStation=e['fromStation'], toStation=station, inTransitFrameId=middle, arrivalFrameId=arrival['frameId'],
                         verifiedFrameId=e['samples'][-1]['frameId'], appliedForwardActions=len(walks[i]),
                         elapsedMs=end_at-prior_at, appliedActions=applied_actions[i]+len(helpers), yawReversals=yaw_reversals(leg_frames),
                         commandReversals=sum(a!=b for a,b in zip(turns,turns[1:]))))
        if edges is not None:
            _, _, ordinal, goal = edges[i]
            legs[-1].update(segmentIndex=i,destinationOrdinal=ordinal,requestedDestination=goal,
                            inTransitForwardRequestId=transit_action)
            if station == goal:
                marker = milestones[len(expected)] if len(milestones) > len(expected) else {}
                check_patrol_leg(marker, i, edges)
                require(marker.get('type') == 'hybridDestinationVerified' and marker.get('routeId') == STREET_PATROL_ROUTE
                        and marker.get('sourceEpoch') == epoch and marker.get('completedLegs') == i+1
                        and marker.get('destinationOrdinal') == ordinal and marker.get('requestedDestination') == goal
                        and marker.get('station') == station and marker.get('frameId') == legs[-1]['verifiedFrameId']
                        and marker.get('atMs') == end_at, 'Destination marker differs from its released endpoint')
                expected.append(marker)
        elif (i+1) % 4 == 0:
            number = (i+1)//4
            require(number <= len(circuit_events), 'No circuit completion at the return to A')
            c = circuit_events[number-1]
            require(c.get('station') == PATROL_ORDER[0] and c.get('routeId') == STREET_PATROL_ROUTE
                    and c.get('sourceEpoch') == epoch and c.get('completedLegs') == i+1
                    and c.get('completedCircuits') == number and c.get('atMs') == end_at
                    and c.get('frameId') == legs[-1]['verifiedFrameId'], 'Patrol circuit marker differs from final A arrival')
            expected.append(c)
            circuits.append(dict(circuit=number, endingFrameId=c['frameId'], legs=legs[-4:]))
        prior_at = end_at
    final = parts[-1]['hybridNavigation']
    if edges is not None:
        require(final.get('navigationMode') == 'itinerary' and final.get('completedCircuits',0) == 0
                and final.get('completedDestinations') == sum(e['type'] == 'hybridDestinationVerified' for e in expected)
                and ((final.get('phase') == 'complete') if run.get('endReason') == 'hybridLegLimit'
                     else final.get('phase') in ('walking','recovering','releaseRequired','verifying','awaitingClimbPose')),
                'Final directed request count, mode or phase differs')
    require(expected == milestones and (edges is not None or final.get('completedCircuits') == len(circuits)),
            'Patrol milestone sequence or final circuit count differs')
    return circuits, legs[len(circuits)*4:]


def verify_climb_exit(event, frames, actions, receipts, climb_events, epoch):
    """Independently join the native climb, X dispatch, cleanup barrier and two normal source frames."""
    exit_info = event['climbExit']
    attempt = exit_info['climbAttempt']
    action = actions.get(exit_info['dropRequestId']) or {}
    require(action.get('attempt') == attempt and action.get('frameId') == exit_info['dropFrameId'],
            'No matching accepted climb drop')
    receipt = receipts[action['requestId']]
    before = frames.get(event['preClimbFrameId']) or {}
    drop = frames[action['frameId']]
    normal = [frames.get(i) or {} for i in exit_info['exitFrameIds']]
    require(len(normal) == 2 and before and all(normal), 'Missing climb approach or normal exit frames')
    require(exit_info['sourceEpoch'] == event['sourceEpoch'] == epoch
            and all(f['sourceFrame']['captureEpoch'] == epoch for f in (before, drop, *normal))
            and before['navigationPose']['state'] == 'valid' and before['frameWorldReadiness']['ready'] is True
            and before['frameId'] < action['frameId'] < normal[0]['frameId'] < normal[1]['frameId'] < event['frameId'],
            'Climb episode source order or identity differs')
    batch = [e for e in climb_events if e.get('attempt') == attempt]
    releases = [e['response'] for e in batch if e.get('kind') == 'release_returned'
                and e['response'].get('type') == 'released' and e.get('payloadBytes') == 0]
    require(len(releases) == 2 and releases[1]['serverNowMs'] == exit_info['cleanupReleaseAtMs']
            and receipt['endedAtMs'] == exit_info['dropEndedAtMs'] <= releases[1]['serverNowMs']
            and any(e.get('kind') == 'resume' and e.get('climbExit') == exit_info for e in batch),
            'Missing cleanup release or recorded resume for the completed X')

    def hint(frame, state):
        motion = frame.get('motionEvidence') or {}
        return (frame['sourceFrame']['captureEpoch'] == epoch and frame['frameWorldReadiness']['ready'] is True
                and motion.get('method') == 'native_key_tip_templates_v1' and motion.get('status') == state
                and motion.get('spaceKeyMatched') is (state == 'climb') and motion.get('xKeyMatched') is (state == 'climb'))

    pre_release = releases[0]['serverNowMs']
    climb = [f for f in frames.values() if hint(f, 'climb') and
             pre_release-400 <= observation_timestamp(f) <= pre_release]
    require(any(60 <= observation_timestamp(b)-observation_timestamp(a) <= 250
                and a['sourceFrame']['timestamp100ns'] < b['sourceFrame']['timestamp100ns']
                and a['frameId'] < b['frameId'] and a['frameWorldReadiness']['epoch'] == b['frameWorldReadiness']['epoch']
                for a in climb for b in climb), 'No distinct native climb confirmation before release')
    require(hint(drop, 'climb') and observation_timestamp(drop) >= pre_release+60 and
            all(hint(f, 'normal') for f in normal) and observation_timestamp(normal[0]) >= releases[1]['serverNowMs']+60
            and 60 <= observation_timestamp(normal[1])-observation_timestamp(normal[0]) <= 250
            and normal[0]['sourceFrame']['timestamp100ns'] < normal[1]['sourceFrame']['timestamp100ns']
            and normal[1]['frameId'] == exit_info['resumeFrameId']
            and normal[1]['sourceFrame']['timestamp100ns'] == exit_info['resumeSourceId']
            and observation_timestamp(normal[1]) == exit_info['resumeAtMs'] < event['atMs']
            and normal[0]['frameWorldReadiness']['epoch'] == normal[1]['frameWorldReadiness']['epoch']
                == exit_info['resumeWorldEpoch'] >= releases[1]['worldReadiness']['epoch'],
            'Wrong climb X source or post-release normal frames')


def audit_passage(event, endpoint, leg_start, frames, accepted, receipts, route_id, goal,
                  climb_actions, climb_events, transitions):
    """Reconstruct a stalled approach and a passage from poses and executed steps."""
    at = event['atMs']
    climb = event['type'] == 'hybridClimbRecovery'
    result = dict(triggerAtMs=at, attempt=event['attempt'], verified=False,
                  triggerKind='climbDrop' if climb else 'stationaryForward')
    try:
        release = endpoint['releaseAtMs']
        target = endpoint['endpoint']
        leg = endpoint['completedLegs'] - 1
        since = at if climb else at-2000
        require(leg_start <= since <= at < release, 'Recovery window crosses a leg boundary')
        if climb:
            require(event['target'] == target and event['completedLegs'] == leg, 'Climb exit belongs to another leg')
            verify_climb_exit(event, frames, climb_actions, receipts, climb_events, endpoint['sourceEpoch'])
        rows = sorted((stamp, f['frameId'], f) for f in frames.values()
                      if at - 2250 <= (stamp := observation_timestamp(f)) <= endpoint['samples'][-1]['atMs'])
        # Use a continuous, distinct series of native observations around contact.
        # Neither a camera oscillation nor two samples at the same clock establish a stall.
        anchors = [i for i, (stamp, _, _) in enumerate(rows) if stamp <= since]
        require(anchors, 'Missing observation at the start of the stall')
        episode = rows[anchors[-1]:]
        stalled = [(stamp, fid, f) for stamp, fid, f in episode if stamp <= at]
        require(stalled[-1][0] == at and event.get('frameId', stalled[-1][1]) == stalled[-1][1],
                'Trigger has no matching source observation')
        contact_pose = stalled[-1][2]['navigationPose']
        contact = contact_pose['x'], contact_pose['y']
        arrivals = [stamp for stamp, _, f in episode if release-250 <= stamp <= release
                    and (p := f.get('navigationPose') or {}).get('state') == 'valid'
                    and f.get('frameWorldReadiness', {}).get('ready') is True
                    and math.dist((p['x'], p['y']), goal) <= 1.1]
        require(arrivals, 'No source pose within the arrival radius before endpoint release')
        release_frame = next((frames[e['frameId']] for e in transitions
                              if e.get('reason') == 'hybridEndpoint' and e.get('state') == 'held'
                              and e.get('frameId') in frames and observation_timestamp(frames[e['frameId']]) in arrivals),
                             None)
        arrival_epoch = release_frame['frameWorldReadiness'].get('epoch') if release_frame else None
        exit_epoch = frames[endpoint['samples'][0]['frameId']]['frameWorldReadiness'].get('epoch')
        first_restored = next((fid for stamp, fid, f in episode if release <= stamp <= release+1000
                               and (g := f.get('frameWorldReadiness') or {}).get('epoch') == exit_epoch
                               and g.get('ready') is True and (f.get('motionEvidence') or {}).get('status') == 'normal'
                               and (f.get('navigationPose') or {}).get('state') == 'valid'), None)
        require(not any(release <= step['startedAtMs'] <= endpoint['samples'][-1]['atMs']
                        for receipt in receipts.values() for step in receipt.get('appliedSteps', [])),
                'New software input occurred after release before endpoint verification')
        for index, (stamp, fid, frame) in enumerate(episode):
            pose = frame.get('navigationPose') or {}
            source = frame.get('sourceFrame') or {}
            motion = frame.get('motionEvidence') or {}
            gate = frame.get('frameWorldReadiness') or {}
            # A successful endpoint release itself invalidates the ready gate.
            # Limit that expected transition to the interval after measured arrival.
            live = frame.get('worldReadiness') or {}
            release_window = (release_frame and first_restored and release_frame['frameId'] < fid <= first_restored
                              and type(arrival_epoch) is int and exit_epoch == arrival_epoch+1
                              and endpoint.get('releaseEpoch', exit_epoch) == exit_epoch)
            reconfirming = (release_window
                            and ((gate.get('epoch') == exit_epoch and gate.get('ready') is False and gate.get('reason')
                                  in ('world_observation_invalidated', 'world_confirming', 'client_release')) or
                                 (gate.get('epoch') == exit_epoch-1 and gate.get('ready') is True
                                  and live.get('epoch') == exit_epoch and live.get('reason') == 'client_release')))
            require(source.get('captureEpoch') == endpoint['sourceEpoch'] and (reconfirming or
                    (gate.get('ready') is True and pose.get('state') == 'valid' and pose.get('frameId') == fid
                     and pose.get('layerId') == 'City_102' and .99 <= pose['positionConfidence'] <= 1
                     and .2 <= pose['yawConfidence'] <= 1 and motion.get('status') == 'normal'
                     and motion.get('spaceKeyMatched') is False)), 'Unqualified pose during obstacle passage')
            if index:
                prev_at, prev_fid, prev = episode[index-1]
                require(0 < stamp-prev_at <= (1000 if release_window else 250) and fid > prev_fid
                        and source['timestamp100ns'] > prev['sourceFrame']['timestamp100ns'],
                        'Passage observations are stale or discontinuous')
            if stamp <= at:
                require(math.dist(contact, (pose['x'], pose['y'])) <= .5,
                        'Character moved during the claimed stall')
        # Count the union of terminal software holds. A proposal, camera delta or
        # duplicated/overlapping hold must not inflate the evidence of blocked W.
        steps = []
        for request, decision in accepted.items():
            selection = decision['hybridNavigation']
            if (selection.get('completedLegs') != leg or selection.get('target') != target
                    or not stalled[0][0]-150 <= decision['observationTimestampMs'] < release):
                continue
            receipt = receipts[request]
            applied = receipt.get('appliedSteps') or []
            for i, step in enumerate(applied):
                begin = step['startedAtMs']
                end = applied[i+1]['startedAtMs'] if i+1 < len(applied) else receipt['endedAtMs']
                if (begin < end and len(step.get('keys', ())) == 1 and step.get('mouseDy', 0) == 0
                        and abs(step.get('mouseDx', 0)) <= (3 if step['keys'] == ['W'] else 0)):
                    steps.append((begin, end, step['keys'][0], selection['reason'], decision))
        covered, cursor = 0, at - 2000
        retreat_end = sidestep_end = side_origin = resumed = None
        for begin, end, key, reason, decision in sorted(steps, key=lambda s: s[0]):
            pose = frames[decision['frameId']]['navigationPose']
            if key == 'W' and reason in ('modelRouteCompatible', 'modelIdleOrOffRoute'):
                heading = (pose['headingToStartDegrees' if target == 'start' else 'headingToEndDegrees']
                           if route_id == COURTYARD_ROUTE else route_heading(pose, goal))
                if abs((pose['yawDegrees']-heading+180) % 360-180) <= 5:
                    covered += max(0, min(at, end) - max(cursor, begin))
                    cursor = max(cursor, end)
                    if resumed is None and sidestep_end is not None and sidestep_end <= begin < release:
                        resumed = begin, pose
            if (decision['observationTimestampMs'] >= at and begin >= at and end <= release
                    and decision['hybridNavigation']['owner'] == 'hybrid-native'):
                if key == 'S' and reason == 'obstacleRetreat':
                    retreat_end = end
                elif key in ('A', 'D') and reason == 'obstacleSidestep' and retreat_end is not None and begin >= retreat_end:
                    if side_origin is None:
                        side_origin = pose, key
                    sidestep_end = end
        require(climb or covered >= 600, 'Insufficient receipt-confirmed forward movement during stall')
        require(resumed is not None and resumed[0] + 80 <= release,
                'No applied retreat, sidestep and resumed forward movement')
        origin, side = side_origin
        resume_pose = resumed[1]
        # The native yaw uses inverted game-map axes. Check travel on the
        # commanded side against the pose before the first applied side hold.
        yaw = math.radians(origin['yawDegrees'])
        right = (resume_pose['x']-origin['x'])*math.sin(yaw) - (resume_pose['y']-origin['y'])*math.cos(yaw)
        clearance = right if side == 'D' else -right
        require(clearance >= 1, 'Native poses did not confirm motion toward the commanded side')
        # Measure signed displacement toward the outstanding endpoint. Lateral
        # displacement or a long retreat alone can have a large Euclidean norm.
        distance = math.dist(contact, goal)
        require(distance > 0, 'Contact coincides with the endpoint')
        dx, dy = (goal[0]-contact[0])/distance, (goal[1]-contact[1])/distance
        advance = min((s['x']-contact[0])*dx + (s['y']-contact[1])*dy for s in endpoint['samples'])
        require(advance >= 1.5, 'Verified endpoint did not clear the contact plane')
        require(advance - (resume_pose['x']-contact[0])*dx - (resume_pose['y']-contact[1])*dy >= 1,
                'Forward movement after the sidestep did not advance toward the endpoint')
        result.update(verified=True, contactFrameId=stalled[-1][1], contactPosition=list(contact),
                      measuredSideClearance=round(clearance, 3),
                      minimumForwardAdvance=round(advance, 3),
                      completedLegs=endpoint['completedLegs'])
        if climb:
            result.update(dropRequestId=event['climbExit']['dropRequestId'],
                          normalExitFrameIds=event['climbExit']['exitFrameIds'])
        else:
            result['stalledForwardHoldMs'] = round(covered, 2)
    except ValueError as error:
        result['reason'] = str(error)
    return result


def audit_rebind(suspended, rebound, joined, frames, receipts, transitions, decisions=()):
    """Check the release ACK, absence of input, and source-bound readmission to the same corner."""
    since = suspended['releaseAtMs']
    world = suspended['releaseEpoch']
    require(all(suspended[k] == rebound[k] for k in (
        'completedLegs', 'target', 'waypoint', 'bypassPointIndex', 'previousWorldEpoch', 'releaseEpoch', 'releaseAtMs')),
        'Rebind changed its suspended route or release')
    anchor = joined(suspended)
    require(suspended['yawDegrees'] == anchor['yawDegrees'] and 0 <= since-suspended['atMs'] <= 500
            and frames[suspended['frameId']]['frameWorldReadiness']['epoch'] == suspended['previousWorldEpoch']
            and world == suspended['previousWorldEpoch']+1, 'Rebind release is outside the anchor epoch or deadline')
    holds = [t for t in transitions if t.get('state') == 'held' and t.get('reason') == 'hybridStalePose'
             and (t.get('release') or {}).get('serverNowMs') == since]
    require(len(holds) == 1, 'No matching acknowledged stale-pose hold')
    ack = holds[0]['release']
    gate = ack.get('worldReadiness') or {}
    stale = frames.get(holds[0].get('frameId')) or {}
    require(ack.get('inputAvailable') is not True and gate.get('epoch') == world
            and gate.get('reason') == 'client_release' and gate.get('ready') is False
            and (gate.get('sourceFrame') or {}).get('captureEpoch') == suspended['sourceEpoch']
            and (stale.get('sourceFrame') or {}).get('captureEpoch') == suspended['sourceEpoch']
            and stale['frameId'] >= suspended['frameId'] and suspended['atMs'] <= observation_timestamp(stale) <= since
            and all(i in receipts and receipts[i]['endedAtMs'] <= since for i in ack['receiptIds']),
            'Wrong stale-pose release epoch, source or receipt')
    samples = rebound['samples']
    require(len(samples) == 3 and samples[-1]['frameId'] == rebound['frameId']
            and samples[-1]['atMs'] == rebound['atMs'] <= since+1500 and samples[0]['atMs'] >= since+80,
            'Rebind lacks three timely samples after release')
    require(not any(stale['frameId'] <= d['frameId'] <= rebound['frameId'] for d in decisions),
            'A policy proposal used a held or unconfirmed source frame')
    goal = suspended['waypoint']
    gx, gy = goal['x']-anchor['x'], goal['y']-anchor['y']
    distance = math.hypot(gx, gy)
    camera = suspended.get('cameraReceipt')
    require(camera == rebound.get('cameraReceipt'), 'Rebind changed its camera receipt')
    if camera:
        rid = camera['requestId']
        matched = [d for d in decisions if d.get('acceptance', {}).get('type') == 'accepted'
                   and d['acceptance']['requestId'] == rid]
        receipt = receipts.get(rid) or {}
        steps = receipt.get('appliedSteps') or []
        require(len(matched) == len(steps) == 1 and receipt.get('status') == 'completed'
                and receipt.get('modelId') == 'hybrid-native'
                and matched[0]['frameId'] == receipt['frameId'] == camera['frameId'] == suspended['frameId'],
                'Camera allowance has no matching native decision and terminal receipt')
        sel = matched[0]['hybridNavigation']
        retained = ack.get('lastAcceptedAction') or {}
        require(retained.get('requestId') == rid and retained.get('frameId') == suspended['frameId']
                and retained.get('observedAtMs') == matched[0]['observationTimestampMs'] == suspended['atMs']
                and retained.get('sourceEpoch') == suspended['sourceEpoch']
                and retained.get('acceptedAtMs') == matched[0]['acceptance']['acceptedAtMs'] == receipt['acceptedAtMs']
                and retained.get('modelId') == sel['owner'] == 'hybrid-native'
                and all(retained.get(k) == sel.get(k) for k in ('step','reason','target','completedLegs','bypassPointIndex'))
                and sel['reason'] == 'nativeHeading'
                and sel['completedLegs'] == suspended['completedLegs'] and sel['target'] == suspended['target']
                and all(sel['steeringPoint'][k] == goal[k] for k in ('x','y'))
                and sel['steeringPoint'].get('kind') == ('bypass' if suspended['bypassPointIndex'] < 3 else 'endpoint')
                and sel.get('bypassPointIndex', 3) == suspended['bypassPointIndex']
                and all(s['mouseDx'] == camera['mouseDx'] and s.get('keys') == [] and not s.get('mouseButtons')
                        and not s.get('buttons')
                        and s.get('mouseDy') == 0 for s in (sel['step'], steps[0]))
                and camera['mouseDx'] != 0 and camera['mouseDx'] == camera_correction(
                    anchor['yawDegrees'], route_heading(anchor, (goal['x'], goal['y'])))
                and steps[0]['startedAtMs'] == camera['startedAtMs']
                and 0 <= camera['startedAtMs']-suspended['atMs'] <= 150
                and camera['startedAtMs'] < camera['endedAtMs'] == receipt['endedAtMs'] <= since,
                'Camera allowance differs from its applied bounded correction')
        require(not any(suspended['atMs'] <= s['startedAtMs'] <= since
                        for key, other in receipts.items() if key != rid for s in other.get('appliedSteps', [])),
                'Other input followed the camera anchor before release')
    yaw_error = (route_heading(anchor, (goal['x'],goal['y']))-anchor['yawDegrees']+180)%360-180
    for f in frames.values():
        if not stale['frameId'] <= f['frameId'] <= rebound['frameId'] or observation_timestamp(f) < since:
            continue
        require(f['sourceFrame']['captureEpoch'] == suspended['sourceEpoch'], 'Capture changed while input was held')
        if f['frameId'] < samples[0]['frameId']:
            g = f['frameWorldReadiness']
            require(g['epoch'] == world and ((g.get('ready') is False and g.get('reason') in
                    ('client_release','world_observation_invalidated','world_confirming')) or
                    (g.get('ready') is True and (f.get('motionEvidence') or {}).get('status') == 'normal')),
                    'Unexpected gate or movement while awaiting rebind')
            continue
        # A hidden interruption between the selected stable samples voids re-entry.
        joined(dict(frameId=f['frameId'], atMs=observation_timestamp(f)))
        require(f['frameWorldReadiness']['epoch'] == world, 'World readiness changed during rebind')
    for i, s in enumerate(samples):
        p = joined(s)
        f = frames[s['frameId']]
        dx, dy = p['x']-anchor['x'], p['y']-anchor['y']
        turned = (p['yawDegrees']-anchor['yawDegrees']+180)%360-180
        camera_settled = (camera and math.hypot(dx, dy) <= .35 and abs(turned) <= 75
                          and turned*camera['mouseDx'] > 0 and turned*yaw_error > 0
                          and abs(turned) <= abs(yaw_error)+3)
        require(f['frameWorldReadiness']['epoch'] == world and p['yawDegrees'] == s['yawDegrees']
                and math.hypot(dx, dy) <= 2 and (abs(turned) <= 12 or camera_settled),
                'Rebind pose exceeds source, position or yaw bounds')
        if distance > 0:
            require(abs(dx*gy-dy*gx)/distance <= .75 and (dx*gx+dy*gy)/distance >= -.45,
                    'Rebind drifted away from the suspended approach')
        require(all(math.dist((s['x'], s['y']), (a['x'], a['y'])) <= .35 and
                    abs((s['yawDegrees']-a['yawDegrees']+180)%360-180) <= 3 for a in samples[:i]),
                'Rebind source poses are unstable')
        previous = samples[i-1] if i else suspended
        require(s['frameId'] > previous['frameId'] and f['sourceFrame']['timestamp100ns'] >
                frames[previous['frameId']]['sourceFrame']['timestamp100ns'] and
                (i == 0 or 80 <= s['atMs']-previous['atMs'] <= 250), 'Rebind reused a capture or missed cadence')
    for receipt in receipts.values():
        require(not since <= receipt.get('acceptedAtMs', -1) <= rebound['atMs'], 'An action was admitted during rebind')
        steps = receipt.get('appliedSteps') or []
        for i, step in enumerate(steps):
            begin = step['startedAtMs']
            end = steps[i+1]['startedAtMs'] if i+1 < len(steps) else receipt['endedAtMs']
            require(not (begin <= rebound['atMs'] and end > since) and not
                    (begin >= since and receipt['frameId'] <= rebound['frameId']),
                    'An input crossed the hold or used a source from before rebind completion')
    return dict(anchorFrameId=suspended['frameId'], heldFrameId=holds[0]['frameId'], releaseAtMs=since,
                releaseEpoch=world, confirmedFrameIds=[s['frameId'] for s in samples],
                cameraCorrectionRequestId=camera['requestId'] if camera else None,
                cameraAllowanceUsed=any(abs((s['yawDegrees']-anchor['yawDegrees']+180)%360-180) > 12 for s in samples))


def audit_bypasses(events, attempts, frames, accepted, receipts, route_id, epoch, transitions=(), decisions=()):
    """Join learned corner poses, actual holds and replay hits within one controller lease."""
    teachings, replays = [], []
    if not any(e['type'].startswith('hybridBypass') for e in events):
        return teachings, replays
    require(route_id == STAIR_POST_ROUTE, 'Bypass events are outside the reviewed stair route')
    goals = dict(zip(('start', 'end'), route_points(route_id)))

    def joined(point):
        """Require a real qualified pose matching the event clock and any claimed coordinates."""
        fid = point['frameId']
        frame = frames.get(fid) or {}
        pose = frame.get('navigationPose') or {}
        motion = frame.get('motionEvidence') or {}
        require((frame.get('sourceFrame') or {}).get('captureEpoch') == epoch and
                observation_timestamp(frame) == point['atMs'] and pose.get('frameId') == fid
                and pose.get('state') == 'valid' and pose.get('layerId') == 'City_102'
                and .99 <= pose['positionConfidence'] <= 1 and .2 <= pose['yawConfidence'] <= 1
                and frame.get('frameWorldReadiness', {}).get('ready') is True
                and motion.get('status') == 'normal' and motion.get('spaceKeyMatched') is False,
                'Bypass point has no matching qualified native frame')
        require(all(point[k] == pose[k] for k in ('x', 'y') if k in point), 'Bypass coordinates differ from source')
        return pose

    def held(leg, target, key, since, until, waypoint=None, index=None):
        """Measure the union of applied holds. For replay, independently check the commanded bearing."""
        spans = []
        for request, d in accepted.items():
            sel = d['hybridNavigation']
            if sel.get('completedLegs') != leg or sel.get('target') != target:
                continue
            if waypoint is not None:
                aim = sel.get('steeringPoint') or {}
                if sel.get('bypassPointIndex') != index or aim.get('kind') != 'bypass' or (
                        aim.get('x'), aim.get('y')) != waypoint:
                    continue
                pose = frames[d['frameId']]['navigationPose']
                if abs((pose['yawDegrees']-route_heading(pose, waypoint)+180) % 360-180) > 5:
                    continue
            applied = receipts[request].get('appliedSteps') or []
            for i, step in enumerate(applied):
                begin = step['startedAtMs']
                end = applied[i+1]['startedAtMs'] if i+1 < len(applied) else receipts[request]['endedAtMs']
                if (step.get('keys') == [key] and step.get('mouseDy', 0) == 0
                        and abs(step.get('mouseDx', 0)) <= (3 if key == 'W' else 0) and begin < end):
                    spans.append((begin, end))
        total, cursor = 0, since
        for begin, end in sorted(spans):
            total += max(0, min(end, until)-max(cursor, begin))
            cursor = max(cursor, end)
        return total

    # Only an independently audited obstacle passage can seed subsequent traversals.
    last_endpoint = teacher = active = None
    for e in events:
        kind = e['type']
        if kind == 'hybridEndpointVerified':
            if active:
                require(active['leg']+1 == e['completedLegs'] and active['target'] == e['endpoint']
                        and active['suspended'] is None and len(active['hits']) == 3
                        and max(active['at'], active['reboundAt']) < e['releaseAtMs'],
                        'Replay endpoint lacks its ordered waypoint hits')
                require(not any(active['began'] <= step['startedAtMs'] < e['releaseAtMs']
                                and set(step.get('keys', [])) & {'S', 'A', 'D', 'X'}
                                for receipt in receipts.values() for step in receipt.get('appliedSteps', [])),
                        'A recovery action occurred during the replay leg')
                replays.append(dict(completedLegs=e['completedLegs'], target=e['endpoint'],
                                    teachingLeg=teacher['completedLegs'], hitFrameIds=active['hits'],
                                    rebinds=active['rebinds']))
            last_endpoint, active = e, None
        elif kind in ('hybridObstacleRecovery', 'hybridClimbRecovery'):
            # An ordinary recovery wins the leg. It cannot earn a clean replay.
            active = None
        elif kind == 'hybridBypassInvalidated':
            active = teacher = None
        elif kind.startswith('hybridBypass'):
            require(e['routeId'] == route_id and e['sourceEpoch'] == epoch, 'Bypass source or route changed')
            pose = joined(e)
            target = e['target']
            require(target in goals, 'Unknown bypass target')
            if kind == 'hybridBypassLearned':
                contact = e['contact']
                require(last_endpoint and last_endpoint['completedLegs'] == e['completedLegs']
                        and last_endpoint['samples'][-1]['frameId'] == e['frameId']
                        and last_endpoint['endpoint'] == target
                        and any(a['verified'] and a['triggerKind'] == e['triggerKind']
                                and a['contactFrameId'] == contact['frameId']
                                and a['completedLegs'] == e['completedLegs'] for a in attempts),
                        'Bypass teaching has no independently verified stall passage')
                points = e['points']
                require(len(points) == 3, 'Teaching requires three recorded corners')
                trail = [contact, *points, e]
                require(all(a['frameId'] < b['frameId'] and a['atMs'] < b['atMs']
                            for a, b in zip(trail, trail[1:])), 'Taught corner order is invalid')
                c, p, q, r = [joined(point) for point in trail[:-1]]
                leg = e['completedLegs']-1
                yaw = math.radians(p['yawDegrees'])
                right = (q['x']-p['x'])*math.sin(yaw) - (q['y']-p['y'])*math.cos(yaw)
                side = 'D' if right > 0 else 'A'
                distance = math.dist((c['x'], c['y']), goals[target])
                dx, dy = (goals[target][0]-c['x'])/distance, (goals[target][1]-c['y'])/distance
                require(held(leg, target, 'S', contact['atMs'], points[0]['atMs']) >= 200
                        and held(leg, target, side, points[0]['atMs'], points[1]['atMs']) >= 200
                        and abs(right) >= 1.5 and held(leg, target, 'W', points[1]['atMs'], points[2]['atMs']) >= 80
                        and (r['x']-c['x'])*dx+(r['y']-c['y'])*dy >= 1.5
                        and (r['x']-q['x'])*dx+(r['y']-q['y'])*dy >= 1,
                        'Taught corners lack the required retreat, side clearance or resumed progress')
                teacher = e
                teachings.append(dict(completedLegs=e['completedLegs'], contactFrameId=contact['frameId'],
                                      waypointFrameIds=[p['frameId'] for p in points]))
            elif kind == 'hybridBypassStarted':
                require(teacher and active is None and last_endpoint
                        and last_endpoint['completedLegs'] == e['completedLegs']
                        and last_endpoint['endpoint'] != target
                        and last_endpoint['samples'][-1]['atMs'] <= e['atMs'], 'Replay has no valid teaching or start')
                expected = teacher['points'] if target == teacher['target'] else list(reversed(teacher['points']))
                require(e['points'] == expected, 'Replay points differ from the teaching traversal')
                active = dict(leg=e['completedLegs'], target=target, began=last_endpoint['samples'][-1]['atMs'],
                              at=e['atMs'], priorFrame=e['frameId'], points=expected, hits=[],
                              suspended=None, rebinds=[], reboundAt=-1)
            elif kind in ('hybridBypassSuspended', 'hybridBypassRebound'):
                require(active and teacher and active['leg'] == e['completedLegs'] and active['target'] == target
                        and len(active['hits']) == e['bypassPointIndex'], 'Bypass rebind has no active learned traversal')
                index = e['bypassPointIndex']
                desired = active['points'][index] if index < 3 else dict(zip(('x','y'), goals[target]))
                require(e['waypoint'] == {k:desired[k] for k in ('x','y')}, 'Rebind substituted a learned waypoint')
                if kind == 'hybridBypassSuspended':
                    require(active['suspended'] is None and e['frameId'] >= active['priorFrame'],
                            'Unexpected repeated or stale bypass suspension')
                    active['suspended'] = e
                else:
                    require(active['suspended'], 'Bypass rebound without a suspension')
                    active['rebinds'].append(audit_rebind(active['suspended'], e, joined, frames, receipts,
                                                          transitions, decisions))
                    active['reboundAt'] = e['atMs']
                    active['priorFrame'] = e['frameId']
                    active['suspended'] = None
            elif kind == 'hybridBypassPointReached':
                index = len(active['hits']) if active else -1
                require(active and active['suspended'] is None and e['completedLegs'] == active['leg'] and e['target'] == active['target']
                        and 0 <= index < 3 and index == e['bypassPointIndex'], 'Unordered replay waypoint hit')
                point = active['points'][index]
                aim = (point['x'], point['y'])
                require(math.dist((pose['x'], pose['y']), aim) <= .65, 'Replay missed the taught corner')
                require((index == 0 and e['frameId'] == active['priorFrame'] and e['atMs'] == active['at']) or
                        (e['atMs'] > active['at'] and e['frameId'] > active['priorFrame'] and
                         frames[e['frameId']]['sourceFrame']['timestamp100ns'] >
                         frames[active['priorFrame']]['sourceFrame']['timestamp100ns'] and
                         held(active['leg'], target, 'W', active['at'], e['atMs'], aim, index) > 0),
                        'Replay hit lacks applied forward input toward its taught corner')
                active['hits'].append(e['frameId'])
                active['at'] = e['atMs']
                active['priorFrame'] = e['frameId']
            else:
                raise ValueError('Unknown bypass event')
    return teachings, replays


def audit(run_path, recordings, *, repository, minimum_legs=1, minimum_obstacle_passages=0,
          minimum_climb_passages=0, minimum_bypass_replays=0, minimum_bypass_rebinds=0, minimum_circuits=0,
          camera_checkpoint=None, minimum_calibrated_actions=0, shadow_checkpoint=None,
          landmark_checkpoint=None, ffmpeg='ffmpeg', ffprobe='ffprobe', destination_plan=None):
    """Join endpoint samples to retained same-frame poses and actions to terminal receipts."""
    require(minimum_legs >= 1 and min(minimum_obstacle_passages, minimum_climb_passages,
                                      minimum_bypass_replays, minimum_bypass_rebinds, minimum_circuits,
                                      minimum_calibrated_actions) >= 0,
            'Require at least one route leg and nonnegative minimum passage counts')
    run = json.loads(Path(run_path).read_text(encoding='utf-8-sig'))
    if isinstance(destination_plan, (str, Path)):
        destination_plan = json.loads(Path(destination_plan).read_bytes())
    edges = destination_edges(destination_plan) if destination_plan is not None else None
    require(run.get('status') == 'completed' and run.get('evidenceComplete') is True,
            'Resident run did not finish with complete evidence')
    require(run.get('modelLoads') == 1 and run.get('inputRequested') is True,
            'Expected one resident GPU model and an input-enabled trial')
    parts, frames = [], {}
    for entry in run['segments']:
        part = json.loads((Path(repository)/entry['report']).read_text(encoding='utf-8-sig'))
        parts.append(part)
        recording = part.get('recording') or {}
        require(recording.get('complete') is True and recording.get('workerRetired') is True,
                'Recording is incomplete or its writer has not retired')
        require(not any(recording.get(k, 0) for k in
                ('droppedFrames', 'droppedEvents', 'abandonedFrames', 'droppedObservations')), 'Recording loss')
        path = Path(recordings)/f"{entry['number']:05d}"/'observations.jsonl'
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                if row.get('continuityContext'):
                    continue
                require(row['frameId'] not in frames, 'Duplicate original frame identity')
                frames[row['frameId']] = row
    require(bool(parts), 'No recorded segments')
    lease = tuple(parts[0]['hello'][k] for k in ('sessionId', 'ownerEpoch'))
    require(all(tuple(p['hello'][k] for k in ('sessionId', 'ownerEpoch')) == lease for p in parts),
            'More than one controller lease was used')
    require(all(p.get('status') == 'completed' for p in parts), 'A segment failed')
    events = [e for p in parts for e in p.get('hybridNavigationEvents', [])]
    if any(e['type'].startswith('hybridBypass') for e in events):
        require(all(p['hybridNavigation'].get('rememberBypass') is True for p in parts),
                'Bypass events lack an opt-in lease')
    starts = [e for e in events if e['type'] == 'hybridStartVerified']
    endpoints = [e for e in events if e['type'] == 'hybridEndpointVerified']
    require(len(starts) == 1, 'Expected one independently admitted starting endpoint')
    require(len(endpoints) >= minimum_legs, 'Insufficient verified route legs')
    route_id = starts[0].get('routeId', COURTYARD_ROUTE)
    require(all(p['hybridNavigation'].get('routeId', COURTYARD_ROUTE) == route_id for p in parts),
            'Fixed route changed within the run')
    start, end = route_points(route_id)
    patrol = route_id == STREET_PATROL_ROUTE
    if edges is not None:
        require(patrol and ((run.get('endReason') == 'hybridLegLimit' and len(endpoints) == len(edges))
                or (run.get('endReason') == 'userStop' and len(endpoints) < len(edges))),
                'Destination run has missing or surplus edges, or an unexpected stop')
        start = PATROL_STATIONS[edges[0][0]]
    goals = PATROL_STATIONS if patrol else dict(start=start, end=end)
    target = starts[0]['target']
    require(target in goals, 'Starting target is unknown')
    prior_frame, prior_at = starts[0]['frameId'], starts[0]['atMs']
    origin = frames.get(prior_frame) or {}
    pose = origin.get('navigationPose') or {}
    source_epoch = (origin.get('sourceFrame') or {}).get('captureEpoch')
    require(source_epoch and origin.get('frameWorldReadiness', {}).get('ready') is True
            and pose.get('state') == 'valid' and pose.get('frameId') == prior_frame
            and observation_timestamp(origin) == prior_at and pose.get('layerId') == 'City_102'
            and .99 <= pose['positionConfidence'] <= 1 and .2 <= pose['yawConfidence'] <= 1
            and math.dist((pose['x'], pose['y']), end if not patrol and target == 'start' else start) <= 2,
            'Admission frame does not match the reviewed starting endpoint')
    for count, endpoint in enumerate(endpoints, 1):
        if patrol:
            target = edges[count-1][1] if edges is not None else PATROL_ORDER[(count-1)%4+1]
        require(endpoint['completedLegs'] == count and endpoint['endpoint'] == target,
                'Endpoint count or alternating route order differs')
        target_point = goals[target]
        samples = endpoint['samples']
        require(len(samples) == 3, 'Endpoint lacks three distinct samples')
        require(endpoint['releaseAtMs'] >= prior_at, 'Endpoint release precedes prior verified progress')
        require(endpoint['sourceEpoch'] == source_epoch, 'Capture generation changed')
        for index, sample in enumerate(samples):
            require(sample['frameId'] > prior_frame and sample['atMs'] > prior_at, 'Source did not advance')
            require(sample['atMs'] >= endpoint['releaseAtMs'] + 80, 'Sample precedes the release barrier')
            if index:
                require(sample['atMs'] - samples[index-1]['atMs'] >= 80, 'Endpoint samples are too close')
            for older in samples[:index]:
                require(math.dist((sample['x'], sample['y']), (older['x'], older['y'])) <= 1.5
                        and abs((sample['yawDegrees']-older['yawDegrees']+180) % 360-180) <= 3,
                        'Endpoint samples are not stable')
            require(sample['frameId'] in frames, 'Endpoint source header is missing')
            frame = frames[sample['frameId']]
            pose = frame.get('navigationPose') or {}
            require(pose.get('state') == 'valid' and pose.get('frameId') == sample['frameId'], 'Invalid joined pose')
            require(all(pose[k] == sample[k] for k in ('x', 'y', 'yawDegrees')), 'Endpoint differs from source pose')
            require(frame['sourceFrame']['captureEpoch'] == source_epoch and
                    observation_timestamp(frame) == sample['atMs'], 'Endpoint source clock differs')
            require(math.dist((pose['x'], pose['y']), target_point) <= 2, 'Endpoint is outside its acceptance radius')
            require(pose['layerId'] == 'City_102' and .99 <= pose['positionConfidence'] <= 1
                    and .2 <= pose['yawConfidence'] <= 1, 'Unqualified native match')
            require(frame.get('frameWorldReadiness', {}).get('ready') is True, 'Endpoint is not a world frame')
            prior_frame, prior_at = sample['frameId'], sample['atMs']
        target = 'end' if target == 'start' else 'start'
    decisions = [d for p in parts for d in p.get('decisions', [])]
    accepted = {d['acceptance']['requestId']: d for d in decisions if d.get('acceptance', {}).get('type') == 'accepted'}
    receipts = {r['requestId']: r for p in parts for r in p.get('receipts', [])}
    climb_actions = {a['requestId']: a for p in parts for a in p.get('navigationClimbActions', [])
                     if a['acceptance'].get('type') == 'accepted'}
    climb_events = [e for p in parts for e in p.get('navigationClimbRecoveryEvents', [])]
    transitions = [e for p in parts for e in p.get('controlTransitions', [])]
    climb_ages = []
    for request, action in climb_actions.items():
        receipt = receipts.get(request) or {}
        applied = receipt.get('appliedSteps') or []
        frame = frames.get(action['frameId'])
        arguments = action['arguments']
        require(frame and len(applied) == 1 and receipt.get('frameId') == action['frameId']
                and receipt.get('modelId') == action['origin'] == 'navigation-climb-drop-v1'
                and arguments.get('modelId') == action['origin'] and arguments.get('frameId') == action['frameId']
                and arguments.get('requestId') == action['acceptance'].get('requestId') == request
                and receipt.get('acceptedAtMs') == action['acceptance']['acceptedAtMs'] <= applied[0]['startedAtMs']
                and receipt['status'] == 'completed' and receipt['reason'] == 'horizon_complete'
                and arguments['steps'] == [dict(keys=['X'], durationMs=100, mouseDx=0, mouseDy=0)]
                and applied[0].get('keys') == ['X'] and applied[0].get('mouseDx') == applied[0].get('mouseDy') == 0
                and applied[0]['startedAtMs'] < receipt['endedAtMs'] < arguments['expiresAtMs'],
                'Climb drop lacks its exact terminal X receipt')
        source_at = observation_timestamp(frame)
        age = applied[0]['startedAtMs']-source_at
        require(0 <= age < 150 and arguments['startBeforeMs'] == source_at+150
                and arguments['expiresAtMs'] == source_at+250 and applied[0]['startedAtMs'] < arguments['startBeforeMs'],
                'Climb drop exceeded its source deadline')
        climb_ages.append(age)
    require(len(accepted) == run['acceptedInputActions'], 'Accepted-action total differs')
    require(set(accepted) <= set(receipts), 'An accepted action has no terminal receipt')
    dispatch_ages = []
    for request, decision in accepted.items():
        receipt = receipts[request]
        require(decision['frameId'] in frames and
                observation_timestamp(frames[decision['frameId']]) == decision['observationTimestampMs'],
                'Action source clock differs from its recorded frame')
        require(receipt['frameId'] == decision['frameId'], 'Receipt joined to another source frame')
        require(receipt['modelId'] == decision['hybridNavigation']['owner'], 'Controller attribution differs')
        steps = receipt.get('appliedSteps') or []
        if steps:
            age = steps[0]['startedAtMs'] - decision['observationTimestampMs']
            require(0 <= age <= 150, 'First software input exceeded the source deadline')
            dispatch_ages.append(age)
    require(parts[-1]['hybridNavigation']['completedLegs'] == len(endpoints), 'Final leg total differs')
    circuits, partial = audit_patrol(starts[0], endpoints, events, frames, parts, run, accepted, receipts,
                                     source_epoch, edges) if patrol else ([], [])
    require(edges is not None or not any(e['type'] == RETRY for e in events), 'Photo retries require a directed route')
    retries = verify_retry_poses(events,frames,parts,receipts,destination_plan.get('confirmFirstArrival',False)) if edges is not None else {}
    cameras = audit_camera(parts, run['segments'], recordings, frames, route_id, camera_checkpoint)
    shadow = (audit_shadow(decisions, frames, receipts, run['segments'], recordings, route_id, shadow_checkpoint, edges)
              if shadow_checkpoint else None)
    landmarks = None
    if landmark_checkpoint:
        from audit_patrol_landmarks import audit_landmarks
        require(patrol, 'Visual station validation requires the street patrol')
        landmarks = audit_landmarks(run, parts, events, frames, recordings, source_epoch, landmark_checkpoint, ffmpeg, ffprobe)
    require(cameras['applied'] >= minimum_calibrated_actions, f"Only {cameras['applied']} verified calibrated actions")
    require(len(circuits) >= minimum_circuits, f'Only {len(circuits)} verified patrol circuits')
    attempts = []
    leg_start, pending = starts[0]['atMs'], []
    for event in events:
        if event['type'] in ('hybridObstacleRecovery', 'hybridClimbRecovery'):
            pending.append(event)
        elif event['type'] == 'hybridEndpointVerified':
            for earlier in pending[:-1]:
                attempts.append(dict(triggerAtMs=earlier['atMs'], attempt=earlier['attempt'], verified=False,
                                     triggerKind='climbDrop' if earlier['type'] == 'hybridClimbRecovery' else 'stationaryForward',
                                     reason='Another recovery preceded the verified endpoint'))
            if pending:
                attempts.append(audit_passage(pending[-1], event, leg_start, frames, accepted, receipts,
                                              route_id, goals[event['endpoint']], climb_actions, climb_events,
                                              transitions))
            leg_start, pending = event['samples'][-1]['atMs'], []
    attempts.extend(dict(triggerAtMs=e['atMs'], attempt=e['attempt'], verified=False,
                         triggerKind='climbDrop' if e['type'] == 'hybridClimbRecovery' else 'stationaryForward',
                         reason='No subsequent verified endpoint') for e in pending)
    passages = sum(a['verified'] and a['triggerKind'] == 'stationaryForward' for a in attempts)
    climb_passages = sum(a['verified'] and a['triggerKind'] == 'climbDrop' for a in attempts)
    require(passages >= minimum_obstacle_passages, f'Only {passages} verified stall passages: {attempts}')
    require(climb_passages >= minimum_climb_passages, f'Only {climb_passages} verified climb passages: {attempts}')
    teachings, replays = audit_bypasses(events, attempts, frames, accepted, receipts, route_id, source_epoch,
                                        transitions, decisions)
    require(len(replays) >= minimum_bypass_replays, f'Only {len(replays)} verified bypass replays')
    rebinds = sum(len(r['rebinds']) for r in replays)
    require(rebinds >= minimum_bypass_rebinds, f'Only {rebinds} verified bypass rebinds')
    return dict(version=1, passed=True, scope='directed-destination-endpoint-and-software-input-joins' if edges is not None
                else 'fixed-route-endpoint-and-software-input-joins', routeId=route_id,
                verifiedLegs=len(endpoints), controllerLeases=1, modelLoads=1,
                verifiedCircuits=len(circuits), patrolCircuits=circuits, partialPatrolLegs=[] if edges is not None else partial,
                **({'directedLegs':partial,'stationaryPhotoRetries':[dict(originalFrameId=fid,
                    frameIds=[e['frameId'] for e in attempts]) for fid,attempts in retries.items()]} if edges is not None else {}),
                cameraCalibration=cameras, steeringShadow=shadow, landmarkShadow=landmarks,
                verifiedRouteSeconds=(endpoints[-1]['samples'][-1]['atMs']-starts[0]['atMs'])/1000,
                sourceFrames=len(frames), acceptedActions=len(accepted), appliedActions=len(dispatch_ages),
                climbDropAppliedActions=len(climb_ages), totalAppliedActions=len(dispatch_ages)+len(climb_ages),
                maximumClimbDropDispatchAgeMs=max(climb_ages) if climb_ages else None,
                medianFirstSoftwareDispatchAgeMs=statistics.median(dispatch_ages) if dispatch_ages else None,
                maximumFirstSoftwareDispatchAgeMs=max(dispatch_ages) if dispatch_ages else None,
                obstacleAttempts=attempts, verifiedStallPassages=passages, verifiedClimbPassages=climb_passages,
                physicalContactVerified=False,
                bypassTeachings=teachings, bypassReplays=replays, verifiedBypassReplays=len(replays),
                verifiedBypassRebinds=rebinds,
                verifiedCameraRebinds=sum(b['cameraAllowanceUsed'] for r in replays for b in r['rebinds']),
                physicalInputDeliveryVerified=False, generalNavigationQualified=False)


def main():
    """Audit only explicitly supplied local evidence paths and save a small result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--recordings', required=True)
    parser.add_argument('--repository', default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument('--minimum-legs', type=int, default=1)
    parser.add_argument('--destination-plan', help='Verify the exact directed edges of this frozen destination plan')
    parser.add_argument('--minimum-circuits', type=int, default=0,
                        help='Require completed stair-front → junction → west-lamp → junction → stair-front circuits')
    parser.add_argument('--camera-checkpoint', help='Require exact local checkpoint bytes for a calibrated turn')
    parser.add_argument('--shadow-checkpoint', help='Recompute every shadow score from this exact checkpoint')
    parser.add_argument('--landmark-checkpoint', help='Join every live station classification and rescore its archived video frame')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--ffprobe', default='ffprobe')
    parser.add_argument('--minimum-calibrated-actions', type=int, default=0)
    parser.add_argument('--baseline-run', help='Compare against a separately sealed uncalibrated patrol')
    parser.add_argument('--baseline-recordings')
    parser.add_argument('--minimum-obstacle-passages', type=int, default=0,
                        help='Require receipt-backed stalls followed by recovery and forward endpoint passage')
    parser.add_argument('--minimum-bypass-replays', type=int, default=0,
                        help='Require complete traversals of learned corners without a new obstacle recovery')
    parser.add_argument('--minimum-bypass-rebinds', type=int, default=0,
                        help='Require verified stale-pose readmissions on completed bypass replay legs')
    parser.add_argument('--minimum-climb-passages', type=int, default=0,
                        help='Require independently verified X-drop exits, lateral clearance and endpoint passage')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if bool(args.baseline_run) != bool(args.baseline_recordings):
        parser.error('--baseline-run and --baseline-recordings must be supplied together')
    result = audit(args.run, args.recordings, repository=args.repository, minimum_legs=args.minimum_legs,
                   minimum_obstacle_passages=args.minimum_obstacle_passages,
                   minimum_circuits=args.minimum_circuits, destination_plan=args.destination_plan,
                   camera_checkpoint=args.camera_checkpoint, minimum_calibrated_actions=args.minimum_calibrated_actions,
                   shadow_checkpoint=args.shadow_checkpoint,
                   landmark_checkpoint=args.landmark_checkpoint, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe,
                   minimum_climb_passages=args.minimum_climb_passages,
                   minimum_bypass_rebinds=args.minimum_bypass_rebinds,
                   minimum_bypass_replays=args.minimum_bypass_replays)
    if args.baseline_run:
        baseline = audit(args.baseline_run, args.baseline_recordings, repository=args.repository, minimum_circuits=1)
        result['patrolComparison'] = compare_patrols(baseline, result)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
