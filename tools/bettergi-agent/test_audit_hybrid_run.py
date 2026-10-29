"""Tampered local evidence must not become a verified gameplay result."""
import json
from pathlib import Path
import tempfile
import unittest

from audit_hybrid_run import audit, audit_bypasses, audit_rebind
from hybrid_navigation import START, END
from hybrid_routes import LAMPPOST_ROUTE, PATROL_STATIONS, STAIR_POST_ROUTE, STREET_PATROL_ROUTE, route_heading, route_points


class HybridAuditTests(unittest.TestCase):
    def fixture(self, root, change=None, minimum_obstacle_passages=0, **minimums):
        frames = []
        samples = []
        for number, at in enumerate((50, 200, 300, 400), 1):
            pose = dict(state='valid', frameId=number, x=END[0], y=END[1], yawDegrees=47,
                        layerId='City_102', positionConfidence=.999, yawConfidence=.6)
            if number == 1:
                pose.update(x=START[0], y=START[1])
            frames.append(dict(frameId=number, capturedAtMs=at, sourceFrame=dict(captureEpoch='epoch', capturedAtMs=at),
                               navigationPose=pose, frameWorldReadiness=dict(ready=True)))
            if number > 1:
                samples.append({k:pose[k] for k in ('frameId', 'x', 'y', 'yawDegrees')} | dict(atMs=at))
        endpoint = dict(type='hybridEndpointVerified', completedLegs=1, endpoint='end',
                        releaseAtMs=100, sourceEpoch='epoch', samples=samples)
        part = dict(status='completed', hello=dict(sessionId='session', ownerEpoch='owner'),
                    recording=dict(complete=True, workerRetired=True),
                    hybridNavigationEvents=[dict(type='hybridStartVerified', target='end', frameId=1, atMs=50), endpoint],
                    hybridNavigation=dict(completedLegs=1),
                    decisions=[dict(frameId=1, observationTimestampMs=50,
                                    acceptance=dict(type='accepted', requestId='action'),
                                    hybridNavigation=dict(owner='hybrid-native'))],
                    receipts=[dict(requestId='action', frameId=1, modelId='hybrid-native',
                                   appliedSteps=[dict(startedAtMs=75)])])
        run = dict(status='completed', evidenceComplete=True, modelLoads=1, inputRequested=True,
                   acceptedInputActions=1, segments=[dict(number=1, report='part.json')])
        if change:
            change(run, part, frames)
        recording = root/'recording'/'00001'
        recording.mkdir(parents=True)
        (recording/'observations.jsonl').write_text('\n'.join(json.dumps(v) for v in frames), encoding='utf-8')
        (root/'part.json').write_text(json.dumps(part), encoding='utf-8')
        (root/'run.json').write_text(json.dumps(run), encoding='utf-8')
        return audit(root/'run.json', root/'recording', repository=root,
                     minimum_obstacle_passages=minimum_obstacle_passages, **minimums)

    @staticmethod
    def patrol_run(run, part, frames, legs=8):
        """Make independent source frames, applied events and release barriers for two circuits."""
        route = ('stair-front','sidewalk-junction','west-lamp','sidewalk-junction','stair-front')
        epoch = 1
        frames.clear()
        def sample(at, point, heading=0):
            fid = len(frames)+1
            s = dict(frameId=fid, atMs=at, x=point[0], y=point[1], yawDegrees=heading)
            frames.append(dict(frameId=fid, sourceFrame=dict(captureEpoch='epoch', timestamp100ns=at*10000, capturedAtMs=at),
                               navigationPose=dict(**s, state='valid', layerId='City_102', positionConfidence=.999,
                                                   yawConfidence=.6), motionEvidence=dict(status='normal', spaceKeyMatched=False),
                               frameWorldReadiness=dict(ready=True, epoch=epoch)))
            return s
        def leg_info(i):
            return dict(fromStation=route[i%4], toStation=route[i%4+1], segmentIndex=i%4, circuit=i//4+1)
        admission = [sample(at, PATROL_STATIONS[route[0]]) for at in (100,200,300)]
        events = [dict(type='hybridStartVerified', target=route[1], station=route[0], routeId=STREET_PATROL_ROUTE,
                       sourceEpoch='epoch', frameId=admission[-1]['frameId'], atMs=300, samples=admission, **leg_info(0))]
        decisions, receipts, transitions = [], [], []
        began = 300
        for i in range(legs):
            leg = leg_info(i)
            origin, target = PATROL_STATIONS[leg['fromStation']], PATROL_STATIONS[leg['toStation']]
            midpoint = tuple((a+b)/2 for a,b in zip(origin,target))
            heading = route_heading(dict(x=midpoint[0], y=midpoint[1]), target)
            s = sample(began+100, midpoint, heading)
            request = str(i+1)
            selection = dict(owner='hybrid-native', completedLegs=i, target=leg['toStation'], **leg)
            decisions.append(dict(frameId=s['frameId'], observationTimestampMs=s['atMs'], hybridNavigation=selection,
                                  acceptance=dict(type='accepted', requestId=request)))
            receipts.append(dict(requestId=request, frameId=s['frameId'], modelId='hybrid-native', endedAtMs=s['atMs']+120,
                                 appliedSteps=[dict(keys=['W'], mouseDx=0, mouseDy=0, startedAtMs=s['atMs']+20)]))
            sample(began+250, tuple(.4*a+.6*b for a,b in zip(origin,target)), heading)
            arrival = sample(began+400, target, heading)
            transitions.append(dict(reason='hybridEndpoint', state='held', frameId=arrival['frameId']))
            epoch += 1
            release = arrival['atMs']+25
            stable = [sample(release+offset, target, heading) for offset in (100,200,300)]
            events.append(dict(type='hybridEndpointVerified', routeId=STREET_PATROL_ROUTE, sourceEpoch='epoch', **leg,
                               station=leg['toStation'], endpoint=leg['toStation'], releaseEpoch=epoch,
                               sourceFrameId=stable[-1]['frameId'], arrivalFrameId=arrival['frameId'], releaseAtMs=release,
                               samples=stable, legElapsedMs=stable[-1]['atMs']-began, completedLegs=i+1))
            began = stable[-1]['atMs']
            if (i+1)%4 == 0:
                events.append(dict(type='hybridCircuitVerified', routeId=STREET_PATROL_ROUTE, sourceEpoch='epoch',
                                   frameId=stable[-1]['frameId'], atMs=began, station=route[0],
                                   completedLegs=i+1, completedCircuits=(i+1)//4))
        part.update(hybridNavigation=dict(routeId=STREET_PATROL_ROUTE, completedLegs=legs, completedCircuits=legs//4),
                    model='open-p2p', residentRunId='gpu-run', policyMetadata=dict(graphCaptureValidated=True),
                    serverDroppedReceipts=0, hybridNavigationEvents=events, receipts=receipts,
                    decisions=decisions, controlTransitions=transitions)
        run.update(runId='gpu-run', acceptedInputActions=legs)

    def test_count_only_complete_four_leg_patrols(self):
        for count in (4,6,8):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as root:
                result = self.fixture(Path(root), lambda r,p,f: self.patrol_run(r,p,f,count), minimum_circuits=count//4)
                self.assertEqual(result['verifiedCircuits'], count//4)
                self.assertEqual(len(result['partialPatrolLegs']), count%4)
                self.assertEqual([s['toStation'] for s in result['patrolCircuits'][0]['legs']],
                                 ['sidewalk-junction','west-lamp','sidewalk-junction','stair-front'])
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, 'Only 1 verified patrol circuits'):
            self.fixture(Path(root), lambda r,p,f: self.patrol_run(r,p,f,7), minimum_circuits=2)

    def test_tampered_patrol_station_order_provenance_and_input_do_not_qualify(self):
        for name in ('skipB','swapBVisits','skipCircuitMarker','wrongCircuitFrame','falseStationCoordinates','noHold',
                     'wrongReleaseEpoch','noForward','noMidLegSource','wrongHeading','sourceSwitch','gpuRunSwitch','fakeClock','falseAdmission'):
            def changed(run, part, frames):
                self.patrol_run(run, part, frames)
                events = part['hybridNavigationEvents']
                if name == 'skipB':
                    events.pop(1)
                elif name == 'swapBVisits':
                    events[3]['fromStation'] = 'stair-front'
                elif name == 'skipCircuitMarker':
                    events.pop(5)
                elif name == 'wrongCircuitFrame':
                    events[5]['frameId'] -= 1
                elif name == 'falseStationCoordinates':
                    for s in events[2]['samples']:
                        s['x'] += 15
                        frames[s['frameId']-1]['navigationPose']['x'] += 15
                elif name == 'noHold':
                    part['controlTransitions'].pop(1)
                elif name == 'wrongReleaseEpoch':
                    events[2]['releaseEpoch'] += 1
                elif name == 'noForward':
                    part['receipts'][1]['appliedSteps'].clear()
                elif name == 'noMidLegSource':
                    frames[part['decisions'][1]['frameId']]['navigationPose']['state'] = 'unavailable'
                elif name == 'wrongHeading':
                    frames[part['decisions'][1]['frameId']-1]['navigationPose']['yawDegrees'] += 90
                elif name == 'sourceSwitch':
                    frames[3]['sourceFrame']['captureEpoch'] = 'other'
                elif name == 'gpuRunSwitch':
                    part['residentRunId'] = 'other'
                elif name == 'fakeClock':
                    events[2]['legElapsedMs'] += 50000
                else:
                    events[0]['samples'][0]['x'] += 15
            with self.subTest(name=name), tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
                self.fixture(Path(root), changed, minimum_circuits=2)

    def test_complete_joined_evidence_passes_without_claiming_physical_delivery(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.fixture(Path(root))
            self.assertEqual(result['verifiedLegs'], 1)
            self.assertEqual(result['verifiedStallPassages'], 0)
            self.assertFalse(result['physicalInputDeliveryVerified'])

    @staticmethod
    def stalled_run(run, part, frames):
        """Build a 2 s clustered W series, followed by a retreat, sidestep and route completion."""
        frames.clear()
        for i in range(37):
            at, fid = i*100, i+1
            distance_left = max(0, min(3, (3300-at)*.006))
            side_displacement = max(0, min((at-2500)/300, (3300-at)/500))*2.2
            pose = dict(state='valid', frameId=fid, x=END[0]-distance_left, y=END[1]+side_displacement,
                        yawDegrees=45, headingToEndDegrees=45, layerId='City_102',
                        positionConfidence=.999, yawConfidence=.6)
            if i == 0:
                pose.update(x=START[0], y=START[1])
            source = dict(captureEpoch='epoch', capturedAtMs=at, timestamp100ns=at*10000)
            frames.append(dict(frameId=fid, sourceFrame=source, navigationPose=pose,
                               motionEvidence=dict(status='normal', spaceKeyMatched=False),
                               frameWorldReadiness=dict(ready=True)))
        events = part['hybridNavigationEvents']
        events[0].update(atMs=0)
        events.insert(1, dict(type='hybridObstacleRecovery', atMs=2200, attempt=1))
        samples = [dict(frameId=f['frameId'], atMs=f['sourceFrame']['capturedAtMs'],
                        **{k: f['navigationPose'][k] for k in ('x', 'y', 'yawDegrees')}) for f in frames[-3:]]
        events[-1].update(releaseAtMs=3300, samples=samples)
        part['decisions'].clear()
        part['receipts'].clear()
        commands = [(at, 'W', 'modelRouteCompatible') for at in range(200, 1800, 200)]
        commands.extend(((2200, 'S', 'obstacleRetreat'), (2500, 'A', 'obstacleSidestep'),
                         (2800, 'W', 'modelIdleOrOffRoute')))
        for at, key, reason in commands:
            request, fid = str(at), at//100+1
            owner = 'open-p2p' if reason == 'modelRouteCompatible' else 'hybrid-native'
            selection = dict(owner=owner, reason=reason, completedLegs=0, target='end')
            part['decisions'].append(dict(frameId=fid, observationTimestampMs=at, hybridNavigation=selection,
                                          acceptance=dict(type='accepted', requestId=request)))
            part['receipts'].append(dict(requestId=request, frameId=fid, modelId=owner, endedAtMs=at+130,
                                         appliedSteps=[dict(keys=[key], startedAtMs=at+30)]))
        run['acceptedInputActions'] = len(commands)

    def test_independent_stall_passage_requires_pose_and_software_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.fixture(Path(root), self.stalled_run, minimum_obstacle_passages=1)
            self.assertEqual(result['verifiedStallPassages'], 1)
            self.assertEqual(result['obstacleAttempts'][0]['stalledForwardHoldMs'], 800)
            self.assertFalse(result['physicalContactVerified'])

    def test_only_the_expected_endpoint_release_can_interrupt_native_pose_evidence(self):
        def transition(run, part, frames):
            self.stalled_run(run, part, frames)
            for f in frames:
                f['frameWorldReadiness']['epoch'] = 1 if f['frameId'] <= 33 else 2
            part['controlTransitions'] = [dict(state='held', reason='hybridEndpoint', frameId=33)]
            frames[33]['frameWorldReadiness'].update(ready=False, reason='world_confirming')
            frames[33]['navigationPose']['state'] = 'unavailable'

        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(self.fixture(Path(root), transition, 1)['verifiedStallPassages'], 1)
        for name in ('noRelease', 'differentEpoch', 'worldLost', 'inputAfterRelease'):
            def changed(run, part, frames):
                transition(run, part, frames)
                if name == 'noRelease':
                    part['controlTransitions'].clear()
                elif name == 'differentEpoch':
                    frames[33]['frameWorldReadiness']['epoch'] = 4
                elif name == 'worldLost':
                    frames[33]['frameWorldReadiness']['reason'] = 'world_lost'
                else:
                    part['receipts'].append(dict(requestId='extra', appliedSteps=[dict(startedAtMs=3350)]))
            with self.subTest(name=name), tempfile.TemporaryDirectory() as root:
                self.assertEqual(self.fixture(Path(root), changed)['verifiedStallPassages'], 0)

    def test_reviewed_lamppost_target_uses_its_own_geometry_for_stall_and_endpoint(self):
        def lamppost(run, part, frames):
            self.stalled_run(run, part, frames)
            start, goal = route_points(LAMPPOST_ROUTE)
            events = part['hybridNavigationEvents']
            events[0]['routeId'] = part['hybridNavigation']['routeId'] = LAMPPOST_ROUTE
            for frame in frames:
                pose = frame['navigationPose']
                pose['x'] = goal[0] + (pose['x']-END[0])
                pose['y'] = goal[1] - (pose['y']-END[1])
                if frame is frames[0]:
                    pose['x'], pose['y'] = start
                pose['yawDegrees'] = route_heading(pose, goal)
                pose['headingToEndDegrees'] = (pose['yawDegrees']+90) % 360
            for sample, frame in zip(events[-1]['samples'], frames[-3:]):
                for key in ('x', 'y', 'yawDegrees'):
                    sample[key] = frame['navigationPose'][key]

        with tempfile.TemporaryDirectory() as root:
            result = self.fixture(Path(root), lamppost, minimum_obstacle_passages=1)
            self.assertEqual(result['routeId'], LAMPPOST_ROUTE)

    def test_route_cannot_be_changed_by_an_event_or_recorder(self):
        def mismatch(run, part, frames):
            part['hybridNavigationEvents'][0]['routeId'] = LAMPPOST_ROUTE

        def unknown(run, part, frames):
            part['hybridNavigationEvents'][0]['routeId'] = part['hybridNavigation']['routeId'] = 'custom-point'

        for change in (mismatch, unknown):
            with self.subTest(change=change.__name__), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ValueError):
                    self.fixture(Path(root), change)

    def test_climb_exit_must_join_native_hints_drop_release_and_forward_passage(self):
        def climb(run, part, frames):
            self.stalled_run(run, part, frames)
            for f in frames:
                f['motionEvidence'].update(method='native_key_tip_templates_v1', xKeyMatched=False)
                f['frameWorldReadiness']['epoch'] = 3 if f['frameId'] >= 17 else 1
            for f in frames[11:15]:
                f['motionEvidence'].update(status='climb', xKeyMatched=True, spaceKeyMatched=True)
            drop_id = 'climb-drop'
            proof = dict(climbAttempt=1, dropRequestId=drop_id, dropFrameId=15, dropEndedAtMs=1530,
                         cleanupReleaseAtMs=1560, exitFrameIds=[18, 19], resumeFrameId=19,
                         resumeAtMs=1800, resumeSourceId=18000000, sourceEpoch='epoch', resumeWorldEpoch=3)
            recovery = part['hybridNavigationEvents'][1]
            recovery.update(type='hybridClimbRecovery', frameId=23, sourceEpoch='epoch', target='end',
                            completedLegs=0, preClimbFrameId=10, climbExit=proof)
            action = dict(requestId=drop_id, frameId=15, origin='navigation-climb-drop-v1', attempt=1,
                          acceptance=dict(type='accepted', requestId=drop_id, acceptedAtMs=1420),
                          arguments=dict(steps=[dict(keys=['X'], durationMs=100, mouseDx=0, mouseDy=0)],
                                         requestId=drop_id, frameId=15, modelId='navigation-climb-drop-v1',
                                         startBeforeMs=1550, expiresAtMs=1650))
            part['navigationClimbActions'] = [action]
            part['receipts'].append(dict(requestId=drop_id, modelId=action['origin'], frameId=15,
                                         status='completed', reason='horizon_complete', acceptedAtMs=1420, endedAtMs=1530,
                                         appliedSteps=[dict(keys=['X'], startedAtMs=1430, mouseDx=0, mouseDy=0)]))
            part['navigationClimbRecoveryEvents'] = [
                dict(kind='release_returned', attempt=1, payloadBytes=0,
                     response=dict(type='released', serverNowMs=1300, worldReadiness=dict(epoch=2))),
                dict(kind='release_returned', attempt=1, payloadBytes=0,
                     response=dict(type='released', serverNowMs=1560, worldReadiness=dict(epoch=3))),
                dict(kind='resume', attempt=1, climbExit=proof)]

        with tempfile.TemporaryDirectory() as root:
            result = self.fixture(Path(root), climb)
            self.assertEqual(result['verifiedClimbPassages'], 1, result['obstacleAttempts'])
            self.assertEqual(result['verifiedStallPassages'], 0)
            self.assertEqual(result['totalAppliedActions'], result['appliedActions']+1)

        for mutation in ('repeatedExit', 'missingClimb', 'wrongRelease', 'replacedDrop'):
            def changed(run, part, frames):
                climb(run, part, frames)
                if mutation == 'repeatedExit':
                    part['hybridNavigationEvents'][1]['climbExit']['exitFrameIds'] = [19, 19]
                elif mutation == 'missingClimb':
                    for f in frames[11:14]:
                        f['motionEvidence']['status'] = 'unknown'
                elif mutation == 'wrongRelease':
                    part['navigationClimbRecoveryEvents'][1]['response']['serverNowMs'] = 1660
                else:
                    part['receipts'][-1]['frameId'] -= 1
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as root:
                if mutation == 'replacedDrop':
                    with self.assertRaisesRegex(ValueError, 'terminal X receipt'):
                        self.fixture(Path(root), changed)
                else:
                    self.assertEqual(self.fixture(Path(root), changed)['verifiedClimbPassages'], 0)

    def test_camera_retreat_or_unrelated_motion_does_not_count_as_passage(self):
        def camera_only(run, part, frames):
            for r in part['receipts'][:8]:
                r['appliedSteps'][0].update(keys=[], mouseDx=350)

        def stalled_after_sidestep(run, part, frames):
            part['receipts'][-1]['appliedSteps'].clear()

        def never_passed_contact(run, part, frames):
            for f in frames[1:30]:
                f['navigationPose']['x'] = END[0] - .2

        def advanced_before_resuming(run, part, frames):
            frames[28]['navigationPose'].update(x=END[0]-.2, y=END[1]+5)

        def no_lateral_clearance(run, part, frames):
            for frame in frames[1:]:
                frame['navigationPose']['y'] = END[1]

        def moved_during_stall(run, part, frames):
            frames[12]['navigationPose']['x'] -= 2

        def repeated_capture(run, part, frames):
            frames[9]['sourceFrame']['timestamp100ns'] = frames[8]['sourceFrame']['timestamp100ns']

        def interrupted_after_sidestep(run, part, frames):
            frames[31]['frameWorldReadiness']['ready'] = False

        for change in (camera_only, stalled_after_sidestep, never_passed_contact,
                       advanced_before_resuming, no_lateral_clearance, moved_during_stall,
                       repeated_capture, interrupted_after_sidestep):
            def changed(run, part, frames):
                self.stalled_run(run, part, frames)
                change(run, part, frames)
            with self.subTest(change=change.__name__), tempfile.TemporaryDirectory() as root:
                with self.assertRaisesRegex(ValueError, 'Only 0 verified stall passages'):
                    self.fixture(Path(root), changed, minimum_obstacle_passages=1)

    def test_missing_source_receipt_late_input_and_changed_pose_are_rejected(self):
        mutations = (
            lambda run, part, frames: frames.pop(),
            lambda run, part, frames: part['receipts'].clear(),
            lambda run, part, frames: part['receipts'][0]['appliedSteps'][0].update(startedAtMs=201),
            lambda run, part, frames: frames[-1]['navigationPose'].update(x=END[0]+1),
            lambda run, part, frames: part['hybridNavigationEvents'][-1].update(releaseAtMs=150),
            lambda run, part, frames: run.update(modelLoads=2),
            lambda run, part, frames: part['recording'].update(droppedFrames=1),
            lambda run, part, frames: part['receipts'][0].update(modelId='open-p2p'),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as root:
                with self.assertRaises(ValueError):
                    self.fixture(Path(root), mutate)


class BypassAuditTests(unittest.TestCase):
    def test_rebind_requires_own_release_three_stable_frames_and_no_intervening_input(self):
        def replay_hold(mutation=None):
            facts = dict(completedLegs=3, target='start', sourceEpoch='epoch', waypoint=dict(x=10, y=0),
                         bypassPointIndex=1, previousWorldEpoch=7, releaseEpoch=8, releaseAtMs=1000)
            anchor = dict(frameId=9, atMs=800, x=0, y=0, yawDegrees=0, **facts)
            samples = [dict(frameId=i, atMs=1100+n*100, x=.2+n*.05, y=.1, yawDegrees=1)
                       for n,i in enumerate((11,12,13))]
            rebound = dict(**samples[-1], **facts, samples=samples)
            frames = {}
            for point in [anchor, dict(frameId=10, atMs=880, x=.1, y=0, yawDegrees=0), *samples]:
                fid = point['frameId']
                frames[fid] = dict(frameId=fid, navigationPose=point, frameWorldReadiness=dict(epoch=7 if fid<=10 else 8),
                                   sourceFrame=dict(captureEpoch='epoch', capturedAtMs=point['atMs'],
                                                    timestamp100ns=point['atMs']*10000))
            holds = [dict(state='held', reason='hybridStalePose', frameId=10,
                          release=dict(serverNowMs=1000, worldReadiness=dict(ready=False, epoch=8, reason='client_release',
                                       sourceFrame=dict(captureEpoch='epoch')), receiptIds=['prior']))]
            receipts = dict(prior=dict(frameId=8, endedAtMs=999, acceptedAtMs=901, appliedSteps=[dict(startedAtMs=902)]))
            decisions = []
            if mutation and mutation.startswith('camera'):
                waypoint = dict(x=0, y=-10)
                anchor['waypoint'] = rebound['waypoint'] = waypoint
                camera = dict(requestId='camera', frameId=9, mouseDx=250, startedAtMs=915, endedAtMs=980)
                anchor['cameraReceipt'] = rebound['cameraReceipt'] = camera
                step = dict(keys=[], mouseDx=250, mouseDy=0)
                receipts['prior'] = dict(frameId=8, acceptedAtMs=715, endedAtMs=790, appliedSteps=[dict(startedAtMs=720)])
                receipts['camera'] = dict(frameId=9, modelId='hybrid-native', status='completed', acceptedAtMs=914, endedAtMs=980,
                                          appliedSteps=[dict(**step, startedAtMs=915)])
                decisions.append(dict(frameId=9, observationTimestampMs=800, acceptance=dict(type='accepted', requestId='camera', acceptedAtMs=914),
                                      hybridNavigation=dict(owner='hybrid-native', reason='nativeHeading', target='start',
                                          step=step, completedLegs=3, bypassPointIndex=1, steeringPoint=dict(kind='bypass', **waypoint))))
                holds[0]['release']['lastAcceptedAction'] = dict(requestId='camera', frameId=9, modelId='hybrid-native',
                    observedAtMs=800, sourceEpoch='epoch', acceptedAtMs=914, step=step, reason='nativeHeading',
                    target='start', completedLegs=3, bypassPointIndex=1)
                for s in samples:
                    s['yawDegrees'] = 63
                if mutation == 'cameraWrongDirection':
                    for s in samples:
                        s['yawDegrees'] = 297
                elif mutation == 'cameraKeys':
                    receipts['camera']['appliedSteps'][0]['keys'] = ['W']
                elif mutation == 'cameraDisplaced':
                    for s in samples:
                        s['y'] = -.6
                elif mutation == 'cameraExtra':
                    receipts['prior'].update(endedAtMs=925, appliedSteps=[dict(startedAtMs=905, mouseDx=2)])
                elif mutation == 'cameraOvershot':
                    anchor['waypoint']['x'] = -30
                elif mutation == 'cameraFakeFrame':
                    receipts['camera']['frameId'] = 8
                elif mutation == 'cameraWrongLastAccepted':
                    holds[0]['release']['lastAcceptedAction']['requestId'] = 'other'
                elif mutation == 'cameraTooFar':
                    for s in samples:
                        s['yawDegrees'] = 76
                elif mutation == 'cameraMissingProof':
                    del anchor['cameraReceipt'], rebound['cameraReceipt']
            elif mutation == 'wrongEpoch':
                holds[0]['release']['worldReadiness']['epoch'] = 10
            elif mutation == 'crossingInput':
                receipts['prior']['endedAtMs'] = 1001
            elif mutation == 'newInput':
                receipts['leak'] = dict(frameId=10, endedAtMs=1150, acceptedAtMs=1060, appliedSteps=[dict(startedAtMs=1060)])
            elif mutation == 'unappliedProposal':
                decisions.append(dict(frameId=12))
            elif mutation == 'lateStaleInput':
                receipts['stale'] = dict(frameId=12, endedAtMs=1500, acceptedAtMs=1400, appliedSteps=[dict(startedAtMs=1400)])
            elif mutation == 'tooFar':
                samples[0]['x'] = 2.2
            elif mutation == 'crossTrack':
                samples[1]['y'] = 1
            elif mutation == 'wrongTarget':
                rebound['waypoint'] = dict(x=9, y=2)
            elif mutation == 'repeatedCapture':
                frames[12]['sourceFrame']['timestamp100ns'] = frames[11]['sourceFrame']['timestamp100ns']
            elif mutation == 'wrongReadiness':
                frames[12]['frameWorldReadiness']['epoch'] = 9
            elif mutation == 'noReceipt':
                holds[0]['release']['receiptIds'] = ['missing']
            result = audit_rebind(anchor, rebound, lambda p: frames[p['frameId']]['navigationPose'], frames,
                                  receipts, holds, decisions)
            return result['confirmedFrameIds']
        self.assertEqual(replay_hold(), [11,12,13])
        self.assertEqual(replay_hold('cameraValid'), [11,12,13])
        for mutation in ('wrongEpoch','crossingInput','newInput','unappliedProposal','lateStaleInput','tooFar','crossTrack','wrongTarget',
                         'repeatedCapture','wrongReadiness','noReceipt','cameraWrongDirection','cameraKeys','cameraDisplaced',
                         'cameraExtra','cameraOvershot','cameraFakeFrame','cameraWrongLastAccepted','cameraTooFar','cameraMissingProof'):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                replay_hold(mutation)

    def replay(self, change=None):
        route = STAIR_POST_ROUTE
        start, goal = route_points(route)
        x, y = goal
        path = [(x,y+5), (x,y+6), (x-2,y+6), (x-2,y+3), goal, goal, (x-2,y+3), (x-2,y+6), (x,y+6), start]
        frames = {}
        points = []
        for fid, (px, py) in enumerate(path, 1):
            at = fid*300
            points.append(dict(frameId=fid, atMs=at, x=px, y=py))
            pose = dict(frameId=fid, state='valid', layerId='City_102', positionConfidence=.999,
                        yawConfidence=.6, yawDegrees=90, x=px, y=py)
            if 6 <= fid <= 8:
                pose['yawDegrees'] = route_heading(pose, path[fid])
            frames[fid] = dict(frameId=fid, navigationPose=pose, frameWorldReadiness=dict(ready=True),
                               motionEvidence=dict(status='normal', spaceKeyMatched=False),
                               sourceFrame=dict(captureEpoch='epoch', capturedAtMs=at, timestamp100ns=at*10000))

        def event(kind, fid, leg, target, **fields):
            return dict(type='hybridBypass'+kind, routeId=route, sourceEpoch='epoch', target=target,
                        completedLegs=leg, **points[fid-1], **fields)

        corner = points[1:4]
        events = [dict(type='hybridEndpointVerified', completedLegs=1, endpoint='end', samples=[points[4]]),
                  event('Learned', 5, 1, 'end', contact=points[0], triggerKind='stationaryForward', points=corner),
                  event('Started', 6, 1, 'start', points=corner[::-1])]
        events.extend(event('PointReached', fid, 1, 'start', bypassPointIndex=i) for i, fid in enumerate((7,8,9)))
        events.append(dict(type='hybridEndpointVerified', completedLegs=2, endpoint='start',
                           samples=[points[-1]], releaseAtMs=2900))
        attempts = [dict(verified=True, triggerKind='stationaryForward', contactFrameId=1, completedLegs=1)]
        accepted, receipts = {}, {}
        for fid, key in ((1,'S'), (2,'A'), (3,'W'), (6,'W'), (7,'W'), (8,'W')):
            replay = fid >= 6
            sel = dict(completedLegs=int(replay), target='start' if replay else 'end')
            if replay:
                aim = corner[::-1][fid-6]
                sel.update(bypassPointIndex=fid-6, steeringPoint=dict(x=aim['x'], y=aim['y'], kind='bypass'))
            accepted[fid] = dict(hybridNavigation=sel, frameId=fid)
            receipts[fid] = dict(appliedSteps=[dict(keys=[key], startedAtMs=fid*300+20)], endedAtMs=fid*300+260)
        if change:
            change(events, frames, receipts, attempts)
        return audit_bypasses(events, attempts, frames, accepted, receipts, route, 'epoch')

    def test_clean_return_replayed_all_three_taught_source_positions(self):
        teach, replay = self.replay()
        self.assertEqual(teach[0]['waypointFrameIds'], [2,3,4])
        self.assertEqual(replay[0]['hitFrameIds'], [7,8,9])

    def test_missing_teaching_or_spoofed_waypoint_hits_cannot_qualify(self):
        def false_teacher(events, frames, receipts, attempts):
            attempts[0]['verified'] = False

        def wrong_source(events, frames, receipts, attempts):
            events[1]['points'][0] = dict(events[1]['points'][0], x=100)

        def wrong_order(events, frames, receipts, attempts):
            events[2]['points'] = events[1]['points']

        def wrong_position(events, frames, receipts, attempts):
            events[3]['x'] += 1
            frames[7]['navigationPose']['x'] += 1

        def missing_hold(events, frames, receipts, attempts):
            receipts[2]['appliedSteps'].clear()

        def no_replay_walk(events, frames, receipts, attempts):
            receipts[7]['appliedSteps'].clear()

        def new_drop(events, frames, receipts, attempts):
            receipts['drop'] = dict(appliedSteps=[dict(keys=['X'], startedAtMs=2150)], endedAtMs=2250)

        for mutation in (false_teacher, wrong_source, wrong_order, wrong_position, missing_hold,
                         no_replay_walk, new_drop):
            with self.subTest(mutation=mutation.__name__), self.assertRaises(ValueError):
                self.replay(mutation)
