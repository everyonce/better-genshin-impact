"""Bounded offline audit of movement-only approach pixels, source deadlines and native terminal receipts."""
import argparse
import copy
import json
import math
from pathlib import Path

import encounter_approach as approach


def require(value, message):
    """Reject missing evidence instead of upgrading the worker's own success assertion."""
    if not value:
        raise ValueError(message)


def verify_episode_clocks(binding, claim, worker, episode):
    """Join the native episode to the original host/review window, never a newly resealed later clock."""
    for value, fields in ((claim, ('startedAtUnixNs', 'startedMonotonicNs', 'deadlineMonotonicNs')),
                          (worker, ('originalReviewDeadlineClientNs', 'leaseStartedMonotonicNs', 'leaseDeadlineMonotonicNs')),
                          (episode, ('startedAtClientNs', 'deadlineClientNs'))):
        require(all(type(value.get(key)) is int and value[key] > 0 for key in fields), 'Original episode clock witness missing')
    source_deadline = binding['reviewedFrame']['sourceFrame']['timestamp100ns'] * 100 + 120_000_000_000
    review_deadline = claim['startedMonotonicNs'] + binding['reviewedAtUnixNs'] + 120_000_000_000 - claim['startedAtUnixNs']
    expected_review = min(source_deadline, review_deadline)
    expected_lease = min(claim['deadlineMonotonicNs'], expected_review, worker['leaseStartedMonotonicNs'] + 10_000_000_000)
    require(claim['deadlineMonotonicNs'] == claim['startedMonotonicNs'] + 40_000_000_000
            and worker['originalReviewDeadlineClientNs'] == expected_review
            and worker['leaseDeadlineMonotonicNs'] == episode['deadlineClientNs'] == expected_lease
            and claim['startedMonotonicNs'] <= worker['leaseStartedMonotonicNs'] <= episode['startedAtClientNs']
            and episode['startedAtClientNs'] < episode['deadlineClientNs'],
            'Episode clock escaped its original host, source-review or ten-second lease window')


def audit_recording(directory, binding, episode):
    """Audit input semantics independently of planner state; native delivery and melee range stay unproved."""
    directory = approach.local_path(directory)
    raw = approach.read_bytes(directory / 'events.jsonl', approach.MAX_RECORD_BYTES)
    require(raw.endswith(b'\n'), 'Recording lacks its final complete event')
    lines = raw.splitlines()
    require(0 < len(lines) <= 4096, 'Unexpected event count')
    events = [json.loads(line) for line in lines]
    require(events[0].get('type') == 'hello' and events[0].get('binding') == binding, 'Original bound hello is missing')
    hello = events[0]['value']
    require(hello.get('inputEnabled') is True and hello.get('supportsStartBeforeMs') is True
            and hello.get('observationProfile') == approach.PROFILE, 'Input lease contract changed')
    require(type(episode.get('startedAtClientNs')) is int and type(episode.get('deadlineClientNs')) is int,
            'Original controller clock bounds are missing')
    replay = approach.ApproachController(binding, hello, episode['startedAtClientNs'], deadline_ns=episode['deadlineClientNs'])
    replay_stop = None
    replay_outcome = None
    route = approach.route_geometry(binding['route'])
    start, end = route.points
    length = math.dist(start, end)
    direction = tuple((b - a) / length for a, b in zip(start, end))
    latest = None
    image_files, observations, proposed, accepted, receipts = {}, [], {}, {}, {}
    admissions, abandoned = {}, {}
    pending = None
    capture = None
    target_seen = None
    endpoint_events = []
    releases, stops = [], []

    def terminal(response):
        """A terminal receipt must name the exact accepted50ms action and original frame."""
        nonlocal pending
        require(response.get('droppedReceipts', 0) == 0, 'Dropped native receipt')
        for receipt in response.get('receipts', []):
            key = receipt.get('requestId')
            require(key in accepted and key not in receipts, 'Unknown or duplicate terminal receipt')
            request, admission = proposed[key]['request'], accepted[key]
            require(receipt.get('modelId') == approach.MODEL_ID and receipt.get('frameId') == request['frameId']
                    and receipt.get('acceptedAtMs') == admission['response']['acceptedAtMs']
                    and approach.finite(receipt.get('endedAtMs')) and receipt['endedAtMs'] >= receipt['acceptedAtMs'],
                    'Receipt source/admission identity or cancellation order differs')
            steps = receipt.get('appliedSteps')
            require(isinstance(steps, list) and len(steps) <= 1, 'Unexpected applied sequence')
            for applied in steps:
                expected = request['steps'][0]
                require(applied.get('index') == 0 and all(applied.get(key) == expected[key] for key in ('keys', 'mouseDx', 'mouseDy'))
                        and receipt['acceptedAtMs'] <= applied['startedAtMs'] < request['startBeforeMs']
                        and applied['startedAtMs'] <= receipt['endedAtMs'] <= request['expiresAtMs'] + 30,
                        'Applied input or source deadline differs')
            require(receipt.get('status') in ('completed', 'cancelled'), 'Unknown terminal status')
            if receipt['status'] == 'completed':
                require(receipt.get('reason') == 'horizon_complete' and len(steps) == 1
                        and receipt['endedAtMs'] >= receipt['acceptedAtMs'] + 50, 'Completed action has no exact applied horizon')
            receipts[key] = receipt
            if pending == key:
                pending = None

    for event in events[1:]:
        kind = event.get('type')
        if kind == 'observation':
            frame = event['frame']
            terminal(frame)
            require(replay_stop is None, 'Recorded another observation after a terminal approach guard')
            try:
                replay.intake_receipts(frame)
                replay_outcome = replay.observe(frame, event['clientReceivedNs'], event['roundTripMs'])
            except (ValueError, TypeError, KeyError, RuntimeError) as error:
                replay_stop = str(error)
                replay_outcome = None
            if frame.get('type') == 'frame':
                filename = f"frames/{frame['frameId']:08d}.rgb"
                require(event.get('rgbFile') == filename and frame.get('width') == frame.get('height') == 192
                        and frame.get('pixelFormat') == 'rgb24' and frame.get('payloadBytes') == 192 * 192 * 3,
                        'Frame geometry or image filename differs')
                if filename not in image_files:
                    pixels = approach.read_bytes(directory / filename, 192 * 192 * 3)
                    require(len(pixels) == 192 * 192 * 3, 'Incomplete raw RGB')
                    image_files[filename] = approach.digest(pixels)
                require(event.get('rgbSha256') == image_files[filename], 'Original raw RGB changed')
                evidence = frame.get('combatEvidence') or {}
                if evidence.get('state') == 'valid' and evidence.get('enemyBarCandidates'):
                    target_seen = frame['sourceFrame']['freshnessAtMs']
            latest = event
            observations.append(event)
        elif kind == 'navigation':
            require(replay_stop is None and event.get('outcome') == replay_outcome,
                    'Navigation continued after a terminal guard or its observation outcome changed')
            snapshot = replay.navigation.snapshot()
            require(all(event.get('snapshot', {}).get(key) == snapshot.get(key) for key in ('phase', 'completedLegs', 'routeId')),
                    'Recorded navigation phase differs from complete observation replay')
            expected_events = replay.navigation.drain_events()
            require([row.get('type') for row in event.get('events', [])] == [row.get('type') for row in expected_events],
                    'Navigation event sequence differs from native-planner replay')
            endpoint_events += [row for row in event.get('events', []) if row.get('type') == 'hybridEndpointVerified']
        elif kind == 'proposal':
            require(replay_stop is None and latest is not None and pending is None,
                    'Proposal after a terminal guard, without a current frame, or with outstanding input')
            frame = latest['frame']
            request = event['request']
            require(frame.get('type') == 'frame' and request.get('frameId') == frame['frameId'], 'Action did not use the latest complete observation')
            approach.qualify_frame(frame, binding['baselineHealthFraction'], binding['maximumEnemyBarCandidates'],
                                   replay_pixels=True, capability=binding['nativeCombatObservation'])
            source = frame['sourceFrame']
            require(capture is None or capture == source['captureEpoch'], 'Capture owner changed during actions')
            capture = source['captureEpoch']
            require(target_seen is not None and 0 <= source['freshnessAtMs'] - target_seen <= 750, 'Target absence exceeded the reviewed corridor allowance')
            pose = frame['navigationPose']
            px, py = pose['x'] - start[0], pose['y'] - start[1]
            along, cross = px * direction[0] + py * direction[1], abs(px * direction[1] - py * direction[0])
            require(-.35 <= along <= length and cross <= 1 and math.hypot(px, py) <= 6, 'Dispatch left the reviewed narrow surface corridor')
            require(set(request) == {'requestId', 'modelId', 'frameId', 'observedAtMs', 'startBeforeMs', 'expiresAtMs', 'steps'}
                    and request['requestId'] not in proposed and request['modelId'] == approach.MODEL_ID
                    and request['observedAtMs'] == frame['capturedAtMs']
                    and request['startBeforeMs'] == source['freshnessAtMs'] + 150
                    and request['expiresAtMs'] == source['freshnessAtMs'] + 200, 'Explicit original-source action bounds changed')
            steps = request['steps']
            require(isinstance(steps, list) and len(steps) == 1, 'Action is not one bounded step')
            step = steps[0]
            require(set(step) == {'keys', 'mouseDx', 'mouseDy', 'durationMs'} and step['keys'] in ([], ['W'])
                    and type(step['mouseDx']) is int and abs(step['mouseDx']) <= 350 and step['mouseDy'] == 0
                    and step['durationMs'] == 50 and not (step['keys'] and step['mouseDx']), 'Action contains unsupported input')
            proposed[request['requestId']] = dict(event, observation=copy.deepcopy(latest))
            pending = request['requestId']
            require(len(proposed) <= 80, 'Approach action cap exceeded')
            attempt = (episode.get('actionAttempts') or {}).get(pending) or {}
            prepared = attempt.get('preparedAtClientNs')
            require(attempt.get('request') == request and type(prepared) is int
                    and latest['clientReceivedNs'] <= prepared <= event['clientTimeNs'], 'Exact local proposal preparation is missing')
            selected = replay.next_action(prepared)
            require(selected is not None and {key: value for key, value in selected.items() if key != 'requestId'}
                    == {key: value for key, value in request.items() if key != 'requestId'}, 'Native planner would not dispatch the recorded action')
            generated = selected['requestId']
            replay.pending['request']['requestId'] = pending
            replay.attempts[pending] = replay.attempts.pop(generated)
        elif kind == 'admission':
            key = event.get('requestId')
            require(key == pending and key in proposed and key not in accepted and event.get('payloadBytes') == 0,
                    'Admission has no unique pending proposal')
            proposal = proposed[key]
            request, observation = proposal['request'], proposal['observation']
            dispatched = event.get('dispatchedAtClientNs')
            require(type(dispatched) is int and dispatched >= observation['clientReceivedNs'], 'Missing original client dispatch clock')
            require(type(episode.get('startedAtClientNs')) is int and type(episode.get('deadlineClientNs')) is int
                    and 0 < episode['deadlineClientNs'] - episode['startedAtClientNs'] <= 10_000_000_000
                    and episode['startedAtClientNs'] <= proposal['clientTimeNs'] <= dispatched < episode['deadlineClientNs'],
                    'Dispatch escaped the original ten-second lease')
            age = observation['frame']['sourceFrameAgeMs'] + observation['roundTripMs'] + (dispatched - observation['clientReceivedNs']) / 1e6
            require(0 <= age <= 150 and abs(age - event.get('sourceAgeAtDispatchMs', math.inf)) <= .001,
                    'Client dispatch exceeded150ms including RPC and post-observation work')
            response = event['response']
            require(response.get('requestId') == key and response.get('type') in ('accepted', 'rejected'), 'Unknown native admission outcome')
            require(key not in admissions and key not in abandoned, 'A proposal has contradictory admission/abandonment')
            admissions[key] = event
            replay.transmitting(dispatched)
            try:
                replay.admission(response, b'')
            except (ValueError, TypeError, KeyError, RuntimeError) as error:
                replay_stop = str(error)
            if response['type'] == 'accepted':
                require(observation['frame']['sourceFrame']['freshnessAtMs'] <= response['acceptedAtMs'] < request['startBeforeMs'],
                        'Native acceptance crossed the stricter start deadline')
                accepted[key] = event
            else:
                pending = None
        elif kind == 'proposalAbandoned':
            key = event.get('requestId')
            require(key == pending and key in proposed and key not in admissions and key not in abandoned
                    and event.get('transmissionAttempted') is False, 'Unsent proposal abandonment is ambiguous')
            expected = replay.abandon_prepared(event.get('reason'))
            require(expected == event, 'Abandonment did not precede every transmission attempt')
            abandoned[key] = event
            replay_stop = event['reason']
            pending = None
        elif kind in ('endpointRelease', 'release', 'stop'):
            response = event['response']
            require(event.get('payloadBytes') == 0 and response.get('type') == ('stopped' if kind == 'stop' else 'released'),
                    'Missing exact cleanup acknowledgement')
            terminal(response)
            if kind == 'endpointRelease':
                require(replay_stop is None, 'Endpoint handoff followed a terminal approach guard')
                replay.released(response, b'', endpoint=True)
            elif kind == 'release':
                replay.released(response, b'')
            else:
                replay.intake_receipts(response, final=True)
            if kind != 'stop':
                context = response.get('executionContext') or {}
                state = context.get('trackedState') or {}
                require(context.get('telemetryComplete') is True and context.get('active') is None
                        and state.get('heldKeys') == [] and state.get('telemetryIncomplete') is False
                        and state.get('releaseOutcome') == 'returned_unverified', 'Release did not report empty tracked input')
                releases.append(dict(event, precedingObservation=copy.deepcopy(latest)))
            else:
                stops.append(event)
        else:
            raise ValueError('Unknown approach journal event: ' + str(kind))
    require(len(stops) == 1 and events[-1]['type'] == 'stop' and any(row['type'] == 'release' for row in releases),
            'Final explicit release and stop are missing')
    require(set(accepted) == set(receipts), 'Accepted action lacks its original terminal receipt')
    require(pending is None and set(proposed) == set(admissions) | set(abandoned)
            and replay.pending is None, 'Proposal transmission/admission outcome remains unresolved')
    require(episode.get('actionAttempts') == replay.attempt_summary()
            and episode.get('actionResponses') == replay.action_responses
            and episode.get('actionProposals') == len(proposed)
            and episode.get('actionsAttempted') == len(admissions), 'Original local/send/admission accounting differs')
    require(episode.get('acceptedActions') == len(accepted) and episode.get('terminalReceipts') == len(receipts)
            and episode.get('recordedFrames') == len(image_files)
            and episode.get('receiptsComplete') is True and episode.get('releaseAcknowledged') is True
            and episode.get('stopAcknowledged') is True, 'Worker summary disagrees with original evidence')
    require({row['requestId']: row for row in episode['receipts']} == receipts, 'Worker terminal copies differ')
    if episode.get('status') == 'completed':
        require(replay_stop is None and replay.complete and len(endpoint_events) == 1 and len(releases) == 2
                and all(row['status'] == 'completed' for row in receipts.values())
                and episode.get('navigationVerified') is True and episode.get('navigation', {}).get('completedLegs') == 1,
                'Reported route completion lacks one verified, released endpoint')
        endpoint_release = next(row for row in releases if row['type'] == 'endpointRelease')
        arrival = endpoint_release['precedingObservation']['frame']
        arrival_pose = arrival['navigationPose']
        require(math.dist((arrival_pose['x'], arrival_pose['y']), end) <= 1.1,
                'Initial endpoint release was outside the native1.1-unit arrival radius')
        acknowledgement = endpoint_release['response']
        gate = acknowledgement.get('worldReadiness') or {}
        require(gate.get('ready') is False and gate.get('epoch') == arrival['frameWorldReadiness']['epoch'] + 1
                and (gate.get('sourceFrame') or {}).get('captureEpoch') == arrival['sourceFrame']['captureEpoch'],
                'Endpoint release changed source or lacked the next world epoch')
        samples = endpoint_events[0].get('samples')
        require(isinstance(samples, list) and len(samples) == 3, 'Endpoint lacks three original source samples')
        endpoint_frames = []
        for sample in samples:
            matching = [row['frame'] for row in observations if row['frame'].get('frameId') == sample.get('frameId')]
            require(matching, 'Endpoint sample has no retained native observation')
            frame = matching[0]
            approach.qualify_frame(frame, binding['baselineHealthFraction'], binding['maximumEnemyBarCandidates'],
                                   replay_pixels=True, capability=binding['nativeCombatObservation'])
            pose, source = frame['navigationPose'], frame['sourceFrame']
            require(source['captureEpoch'] == arrival['sourceFrame']['captureEpoch']
                    and source['freshnessAtMs'] > acknowledgement['serverNowMs']
                    and frame['frameWorldReadiness']['epoch'] == gate['epoch']
                    and sample == dict(frameId=frame['frameId'], atMs=source['freshnessAtMs'],
                                       x=pose['x'], y=pose['y'], yawDegrees=pose['yawDegrees'])
                    and math.dist((pose['x'], pose['y']), end) <= 2, 'Endpoint sample does not join the released original source')
            endpoint_frames.append(frame)
        for first, second in zip(endpoint_frames, endpoint_frames[1:]):
            require(first['frameId'] < second['frameId']
                    and first['sourceFrame']['timestamp100ns'] < second['sourceFrame']['timestamp100ns']
                    and second['sourceFrame']['freshnessAtMs'] - first['sourceFrame']['freshnessAtMs'] >= 80,
                    'Endpoint samples reused a source or were not separated')
        for first in samples:
            for second in samples:
                turn = abs((first['yawDegrees'] - second['yawDegrees'] + 180) % 360 - 180)
                require(math.dist((first['x'], first['y']), (second['x'], second['y'])) <= 1.5 and turn <= 3,
                        'Endpoint samples are not stationary')
    total = len(raw) + len(image_files) * 192 * 192 * 3
    require(total <= approach.MAX_RECORD_BYTES, 'Evidence exceeds the retained byte cap')
    require(episode.get('recordedBytes') == total and episode.get('recordEvents') == len(events),
            'Original recording accounting differs')
    return dict(version=1, kind='encounter-approach-audit-v1', status='verified', episodeStatus=episode['status'],
                acceptedActions=len(accepted), terminalReceipts=len(receipts), distinctRgbFrames=len(image_files),
                originalJournalSha256=approach.digest(raw), recordedBytes=total, endpointEvents=len(endpoint_events),
                physicalInputDeliveryVerified=False, enemyIdentityVerified=False, meleeArrivalVerified=False,
                combatSuccess=False, modelLoaded=False)


def audit_plan(path):
    """Recheck immutable review/source/process joins without opening any live native endpoint."""
    from combat_process_identity import verify_worker_broker
    plan, folder, sha = approach.verify_plan(path, fresh=False)
    result, _ = approach.document(folder / 'result.json')
    worker, _ = approach.document(folder / 'worker-result.json')
    claim, _ = approach.document(folder / 'CONSUMED.json')
    launch, _ = approach.document(folder / 'launch.json')
    approach.validate_claim(claim, plan['runId'], sha)
    require(launch.get('claim') == claim and launch.get('runId') == plan['runId'] and launch.get('planSha256') == sha,
            'Original launch/consumption clocks differ')
    require(result.get('runId') == worker.get('runId') == claim.get('runId') == plan['runId']
            and result.get('planSha256') == worker.get('planSha256') == claim.get('planSha256') == sha
            and result.get('worker') == worker, 'Original process/result/claim joins differ')
    verify_worker_broker(worker['worker'], result['broker'], plan['runtime'])
    require(worker.get('cleanupVerified') is True and result.get('cleanupVerified') is True
            and worker.get('ownerIdleMinimizedAfter') is True and result.get('ownerIdleMinimizedAfter') is True,
            'Original minimized owner cleanup was not retained')
    verify_episode_clocks(plan['binding'], claim, worker, worker['episode'])
    report = audit_recording(folder / 'recording', plan['binding'], worker['episode'])
    report.update(runId=plan['runId'], planSha256=sha, brokerIdentityVerified=True, ownerIdleMinimizedAfter=True)
    return report


def main():
    """Emit an independent artifact only after all bounded offline checks finish."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit_plan(args.plan)
    destination = approach.local_path(args.output, root=Path(args.plan).resolve().parent, existing=False)
    approach.exclusive_json(destination, result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
