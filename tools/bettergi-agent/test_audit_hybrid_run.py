"""Tampered local evidence must not become a verified gameplay result."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from audit_hybrid_run import (EXECUTED_HISTORY_MODE,EXECUTED_HISTORY_SOURCE_NAMES,audit,audit_bypasses,audit_rebind,
                              verify_executed_history,verify_policy_reuse)
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

    def test_explicit_cached_scout_still_requires_independent_route_and_input_evidence(self):
        """Opt-in zero-load accounting cannot skip a single original endpoint/source/receipt check."""
        from hybrid_routes import SCOUT_GRASS_ROUTE
        from navigation_profiles import SCOUT_PROFILE
        from test_navigation_profiles import route_capability
        for corrupt in (False,True):
            with self.subTest(corrupt=corrupt),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve()/'session'/'legs'/('e'*32)
                root.mkdir(parents=True)
                def setup(run,part,frames):
                    """Move the existing independent trace onto one registered scout edge."""
                    start,goal=route_points(SCOUT_GRASS_ROUTE)
                    part['hybridNavigation'].update(routeId=SCOUT_GRASS_ROUTE,profileId=SCOUT_PROFILE)
                    part['navigationGuidance']=route_capability(SCOUT_GRASS_ROUTE)
                    part['hybridNavigationEvents'][0]['routeId']=SCOUT_GRASS_ROUTE
                    for number,frame in enumerate(frames):
                        frame['navigationPose'].update(x=(start if number==0 else goal)[0],
                            y=(start if number==0 else goal)[1],layerId='MapBack_2')
                    for sample,frame in zip(part['hybridNavigationEvents'][-1]['samples'],frames[1:]):
                        sample.update({key:frame['navigationPose'][key] for key in ('x','y','yawDegrees')})
                    CachedPolicyAuditTests.proof(root/'run.json',run,part=part)
                    if corrupt:part['receipts'].clear()
                if corrupt:
                    with self.assertRaises(ValueError):
                        self.fixture(root,setup,policy_reuse_proof=Path(str(root/'run.json')+'.reuse.json'))
                else:
                    result=self.fixture(root,setup,policy_reuse_proof=Path(str(root/'run.json')+'.reuse.json'))
                    self.assertEqual((result['modelLoads'],result['verifiedLegs']),(0,1))
                    self.assertEqual(result['policyReuse']['runId'],'9'*32)

    def test_cached_parts_and_decisions_cannot_hide_goal_changes_and_plain_pause_remains_valid(self):
        """Inspect every original goal snapshot and decision, while retaining the original leg deadline."""
        fields=dict(policyGoalVersion=1,appliedGoalRequestId='applied',goalRequestId='pending',
                    goalRequestStatus='pending',goalError='failed',goalIntent='combat')
        cases=[(location,key,value,False) for location in ('initialGoalState','finalGoalState','leaseInitialGoalState') for key,value in fields.items()]
        cases += [(location,'snapshot',None,True) for location in ('initialGoalState','finalGoalState','leaseInitialGoalState')]
        cases += [('decision',key,value,False) for key,value in fields.items()]
        cases += [('decision',key,None,True) for key in ('policyGoalVersion','appliedGoalRequestId','goalIntent','controlEpoch')]
        cases += [('part','goalChanges',[dict(status='pending')],False),('part','goalChanges',None,True),
                  ('pause',None,None,False),('deadline',None,None,False)]
        for location,key,value,remove in cases:
            with self.subTest(location=location,key=key,remove=remove),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve()/'session'/'legs'/('e'*32);root.mkdir(parents=True)
                def setup(run,part,frames):
                    """Mutate goal evidence only after creating a fully source-bound successful scout trace."""
                    CachedPolicyAuditTests.scout_trace(root,run,part,frames)
                    if location=='pause':
                        run['controlEpoch']=2;part['finalGoalState']['controlEpoch']=2
                        part['decisions'][0]['controlEpoch']=2
                        part['controlTransitions']=[dict(type='controlTransition',state='held',reason='operatorPause',clientTimeNs=100),
                                                    dict(type='controlTransition',state='running',reason='explicitRun',clientTimeNs=200)]
                    elif location=='deadline':
                        for frame,sample in zip(frames[1:],part['hybridNavigationEvents'][-1]['samples']):
                            frame['capturedAtMs']+=35000;frame['sourceFrame']['capturedAtMs']+=35000;sample['atMs']+=35000
                    elif remove and key=='snapshot':part.pop(location)
                    else:
                        target=part['decisions'][0] if location=='decision' else part if location=='part' else part[location]
                        if remove:target.pop(key,None)
                        else:target[key]=value
                kwargs=dict(policy_reuse_proof=Path(str(root/'run.json')+'.reuse.json'))
                if location=='pause':self.assertTrue(self.fixture(root,setup,**kwargs)['passed'])
                else:
                    with self.assertRaises(ValueError):self.fixture(root,setup,**kwargs)

    def test_explicit_geometry_is_independently_replayed_with_original_source_and_input_checks(self):
        """A rehashed proof cannot replace the reviewed route, its directed start, endpoint or receipts."""
        from reviewed_scout_route import ReviewedScoutRoute
        from hybrid_routes import SCOUT_GRASS_ROUTE
        from navigation_profiles import SCOUT_PROFILE
        from test_navigation_profiles import route_capability
        spec=ReviewedScoutRoute(((-1135,2267),(-1142,2255)))
        other=ReviewedScoutRoute(((-1135,2267),(-1140,2253)))
        for corrupt in (None,'explicit','missing','controller','start','endpoint','reverse','receipt','proof','request','authority','review'):
            with self.subTest(corrupt=corrupt),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve()/'session'/'legs'/('e'*32)
                root.mkdir(parents=True)
                def setup(run,part,frames):
                    """Record one custom edge without registering or mutating any global route table."""
                    geometry=dict(routeId=spec.route_id,routeSpec=spec.document(),routeSpecSha256=spec.sha256)
                    part['hybridNavigation'].update(profileId=SCOUT_PROFILE,**copy.deepcopy(geometry))
                    part['navigationGuidance']=route_capability(SCOUT_GRASS_ROUTE)
                    part['hybridNavigationEvents'][0].update(copy.deepcopy(geometry))
                    for index,frame in enumerate(frames):
                        point=spec.points[0 if index==0 else 1]
                        frame['navigationPose'].update(x=point[0],y=point[1],layerId='MapBack_2')
                    if corrupt=='start':frames[0]['navigationPose']['x']+=4
                    if corrupt=='endpoint':
                        for frame in frames[1:]:frame['navigationPose']['x']+=4
                    for sample,frame in zip(part['hybridNavigationEvents'][-1]['samples'],frames[1:]):
                        sample.update({key:frame['navigationPose'][key] for key in ('x','y','yawDegrees')})
                    if corrupt=='reverse':part['hybridNavigationEvents'][0]['target']='start'
                    if corrupt=='controller':part['hybridNavigation']['routeSpec']=other.document()
                    if corrupt=='receipt':part['receipts'].clear()
                    proof,reuse=CachedPolicyAuditTests.proof(root/'run.json',run,reviewed_scout_route=spec,part=part)
                    if corrupt=='proof':reuse['routeSpec']=other.document()
                    if corrupt=='request':
                        path=Path(reuse['requestFile'])
                        request=json.loads(path.read_bytes())
                        request['routeSpec']=other.document()
                        reuse['requestSha256']=CachedPolicyAuditTests.write(path,request)
                    if corrupt=='authority':
                        path=Path(reuse['sessionProof'])
                        session=json.loads(path.read_bytes())
                        del session['reviewedScoutRoutePolicy']
                        reuse['sessionProofSha256']=CachedPolicyAuditTests.write(path,session)
                    if corrupt=='review':
                        request=json.loads(Path(reuse['requestFile']).read_bytes())
                        path=Path(request['reviewFile'])
                        review=json.loads(path.read_bytes())
                        review['routeSpec']=other.document()
                        CachedPolicyAuditTests.write(path,review)
                    if corrupt in ('proof','request','authority'):
                        run.update(policyReuse=copy.deepcopy(reuse),policyReuseSha256=CachedPolicyAuditTests.write(proof,reuse))
                args=dict(policy_reuse_proof=Path(str(root/'run.json')+'.reuse.json'),
                          reviewed_scout_route=None if corrupt=='missing' else other if corrupt=='explicit' else spec)
                if corrupt:
                    with self.assertRaises(ValueError):self.fixture(root,setup,**args)
                else:
                    result=self.fixture(root,setup,**args)
                    self.assertEqual((result['modelLoads'],result['verifiedLegs'],result['controllerLeases']),(0,1,1))
                    self.assertEqual(result['routeSpecSha256'],spec.sha256)
                    self.assertEqual(result['routeSpec'],spec.document())

    @staticmethod
    def patrol_run(run, part, frames, legs=8, itinerary=None):
        """Make independent source frames, applied events and release barriers for two circuits."""
        route = itinerary[0] if itinerary else ('stair-front','sidewalk-junction','west-lamp','sidewalk-junction','stair-front')
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
            if itinerary:
                ordinal, goal = itinerary[1][i]
                return dict(fromStation=route[i],toStation=route[i+1],segmentIndex=i,destinationOrdinal=ordinal,
                            requestedDestination=goal,navigationMode='itinerary')
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
            if itinerary and leg['requestedDestination'] == leg['toStation']:
                events.append(dict(type='hybridDestinationVerified',routeId=STREET_PATROL_ROUTE, sourceEpoch='epoch',
                                   frameId=stable[-1]['frameId'], atMs=began, station=leg['toStation'],
                                   completedLegs=i+1,**leg))
            elif not itinerary and (i+1)%4 == 0:
                events.append(dict(type='hybridCircuitVerified', routeId=STREET_PATROL_ROUTE, sourceEpoch='epoch',
                                   frameId=stable[-1]['frameId'], atMs=began, station=route[0],
                                   completedLegs=i+1, completedCircuits=(i+1)//4))
        part.update(hybridNavigation=dict(routeId=STREET_PATROL_ROUTE, completedLegs=legs, completedCircuits=legs//4),
                    model='open-p2p', residentRunId='gpu-run', policyMetadata=dict(graphCaptureValidated=True),
                    serverDroppedReceipts=0, hybridNavigationEvents=events, receipts=receipts,
                    decisions=decisions, controlTransitions=transitions)
        run.update(runId='gpu-run', acceptedInputActions=legs)
        if itinerary:
            part['hybridNavigation'].pop('completedCircuits')
            part['hybridNavigation'].update(navigationMode='itinerary',phase='complete',
                    completedDestinations=sum(e['type'] == 'hybridDestinationVerified' for e in events))
            run['endReason'] = 'hybridLegLimit'

    def test_directed_navigation_forks_and_rejects_filler_or_stationary_transit(self):
        a,b,c = 'stair-front','sidewalk-junction','west-lamp'
        # Begin at B, turn toward A, and later take B's other exit toward C.
        plan = dict(version=2,mode='destinations',start=b,requests=[dict(destination=s,targets=[s]) for s in (a,c,b)])
        itinerary = ([b,a,b,c,b],[(1,a),(2,c),(2,c),(3,b)])
        for change in ('none','prefix','replaceWithCircuit','switchLabel','wrongStart','missMarker','surplusEdge',
                       'falseTransit','backdateArrival','wrongOwner','reuseBoundary','stopAfterComplete','partialClaim'):
            def setup(run,part,frames):
                self.patrol_run(run,part,frames,2 if change in ('prefix','partialClaim') else 4,itinerary)
                events=part['hybridNavigationEvents']
                ends=[e for e in events if e['type']=='hybridEndpointVerified']
                destination=next(e for e in events if e['type']=='hybridDestinationVerified')
                if change=='replaceWithCircuit':
                    self.patrol_run(run,part,frames,4)
                elif change=='switchLabel':
                    ends[1]['requestedDestination']=b
                elif change=='wrongStart':
                    events[0]['station']=c
                elif change=='missMarker':
                    events.remove(destination)
                elif change=='surplusEdge':
                    events.append(ends[-1])
                elif change=='falseTransit':
                    row=part['decisions'][0]
                    first=frames[row['frameId']-1]['navigationPose']
                    frames[row['frameId']]['navigationPose'].update(x=first['x'],y=first['y'])
                elif change=='backdateArrival':
                    ends[0]['releaseAtMs']=ends[0]['samples'][0]['atMs']
                elif change=='wrongOwner':
                    part['decisions'][1]['hybridNavigation']['destinationOrdinal']=1
                elif change=='reuseBoundary':
                    destination['frameId']-=1
                elif change in ('prefix','stopAfterComplete'):
                    run['endReason']='userStop'
                    part['hybridNavigation']['phase']='walking'
            with self.subTest(change=change), tempfile.TemporaryDirectory() as root:
                if change in ('none','prefix'):
                    result=self.fixture(Path(root),setup,destination_plan=plan)
                    expected=itinerary[0][:3 if change=='prefix' else 5]
                    self.assertEqual([(leg['fromStation'],leg['toStation']) for leg in result['directedLegs']],
                                     list(zip(expected,expected[1:])))
                    self.assertEqual(result['verifiedCircuits'],0)
                else:
                    with self.assertRaises(ValueError):
                        self.fixture(Path(root),setup,destination_plan=plan)

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


class CachedPolicyAuditTests(unittest.TestCase):
    """Prove zero-load claims only through the original immutable one-load session and fresh run."""
    @staticmethod
    def write(path, document):
        """Persist exact proof bytes and return their digest for tamper-evident links."""
        path.parent.mkdir(parents=True,exist_ok=True)
        raw=json.dumps(document,sort_keys=True).encode()
        path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def goal_state(epoch=0):
        """Describe an unchanged ground goal while permitting an ordinary pause/resume epoch."""
        return dict(controlEpoch=epoch,policyGoalVersion=0,appliedGoalRequestId=None,goalRequestId=None,
                    goalRequestStatus=None,goalError=None,goalIntent='ground-navigation')

    @classmethod
    def scout_trace(cls, root, run, part, frames):
        """Bind the general endpoint fixture to a real scout scope and a complete cached review chain."""
        from hybrid_routes import SCOUT_GRASS_ROUTE
        from navigation_profiles import SCOUT_PROFILE
        from test_navigation_profiles import route_capability
        start,goal=route_points(SCOUT_GRASS_ROUTE)
        part['hybridNavigation'].update(routeId=SCOUT_GRASS_ROUTE,profileId=SCOUT_PROFILE)
        part['navigationGuidance']=route_capability(SCOUT_GRASS_ROUTE)
        part['hybridNavigationEvents'][0]['routeId']=SCOUT_GRASS_ROUTE
        for index,frame in enumerate(frames):
            point=start if index==0 else goal
            frame['navigationPose'].update(x=point[0],y=point[1],layerId='MapBack_2')
        for sample,frame in zip(part['hybridNavigationEvents'][-1]['samples'],frames[1:]):
            sample.update({key:frame['navigationPose'][key] for key in ('x','y','yawDegrees')})
        return cls.proof(root/'run.json',run,part=part)

    @classmethod
    def reviewed_scene(cls, session_dir, owner, route_id, points, spec=None):
        """Produce independently readable native/image fixtures instead of mocking the admission verifier."""
        folder=session_dir/'native-review'
        folder.mkdir(parents=True,exist_ok=True)
        frames=[]
        for number in (1,2,3):
            source=dict(captureEpoch='native-review-source',timestamp100ns=number*1_000_000,freshnessAtMs=number*100)
            frames.append(dict(frameId=number,sourceFrame=source,sourceFrameAgeMs=40,
                navigationPose=dict(state='valid',frameId=number,x=points[0][0],y=points[0][1],layerId='MapBack_2',
                    positionConfidence=.999,yawConfidence=.8,yawDegrees=47),
                worldReadiness=dict(ready=True),frameWorldReadiness=dict(ready=True,sourceFrameId=number,sourceFrame=source,epoch=1),
                motionEvidence=dict(status='normal',spaceKeyMatched=False),executionContext=dict(lastSequence=0)))
        plan=dict(owner=owner,enableInput=False,modelLoaded=False,navigationProfile='mondstadt-combat-scout-v1')
        result=dict(status='completed',inputEnabled=False,modelLoaded=False,ownerIdleMinimizedAfter=True,
                    observations=copy.deepcopy(frames),stableSamples=copy.deepcopy(frames))
        image=folder/'01-frame-000000000002.png'
        image.write_bytes(b'\x89PNG\r\n\x1a\nsynthetic reviewed pixels')
        image_sha=hashlib.sha256(image.read_bytes()).hexdigest()
        metadata=dict(frameId=2,sourceFrame=frames[1]['sourceFrame'],imageSha256=image_sha)
        review=dict(routeId=route_id,points=[list(point) for point in points],nativeEndpoint=str(folder),imageName=image.name,
                    imageSha256=image_sha,attacksAllowed=False,maximumLegs=1,inspectedHealth=2354,
                    inspectedMaximumHealth=2764,visualReview='Synthetic clear ground at the directed start')
        if spec is not None:review.update(routeSpec=spec.document(),routeSpecSha256=spec.sha256)
        review_path=session_dir/'review.json'
        return dict(reviewFile=str(review_path),reviewSha256=cls.write(review_path,review),
            nativePlanSha256=cls.write(folder/'plan.json',plan),nativeResultSha256=cls.write(folder/'result.json',result),
            imageSha256=image_sha,imageMetadataSha256=cls.write(image.with_suffix('.json'),metadata))

    @classmethod
    def proof(cls, run_path, run, settings_changes=None, checkpoint_sha=None, reviewed_scout_route=None, part=None):
        """Construct only local synthetic evidence; no checkpoint or GPU resource is opened."""
        from hybrid_routes import SCOUT_GRASS_ROUTE
        from resident_runtime import OPEN_P2P_SHA256
        checkpoint_sha=checkpoint_sha or OPEN_P2P_SHA256
        session_dir=run_path.parent.parent.parent
        owner=dict(root=dict(processId=11,windowsSessionId=1,instanceNonce='a'*32),
                   child=dict(processId=22,windowsSessionId=3,instanceNonce='b'*32))
        worker=dict(processId=33,windowsSessionId=3)
        settings=dict(model='open-p2p',history=41,cuda_graph=True,p2p_fast_start=True,
            goal_intent='ground-navigation',observation_profile='p2p-native-hamming-192-v1',
            max_observation_age_ms=150,action_hold_ms=100,hybrid_legs=1)
        settings.update(settings_changes or {})
        configuration=dict(arguments=settings,checkpointSha256=checkpoint_sha,goalSha256='f'*64)
        fingerprint=hashlib.sha256(json.dumps(configuration,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        session=dict(version=1,kind='scout-policy-session',sessionId='c'*32,worker=worker,owner=owner,
            configuration=configuration,modelConfigurationSha256=fingerprint,checkpointSha256=checkpoint_sha,
            modelLoads=1,modelLoadSeconds=17.5)
        if reviewed_scout_route is not None:
            from reviewed_scout_route import reviewed_route_policy
            session['reviewedScoutRoutePolicy']=reviewed_route_policy()
        source=session_dir/'policy-proof.json'
        source_sha=cls.write(source,session)
        cls.write(session_dir/'manifest.json',dict(version=1,sessionId=session['sessionId'],owner=owner,worker=worker,
            configuration=configuration,modelConfigurationSha256=fingerprint,stopTemperatureC=78,
            sourceFreshnessMs=150,actionHoldMs=100,legDeadlineSeconds=35))
        request=dict(version=1,sessionId='c'*32,requestId='e'*32,modelConfigurationSha256=fingerprint,
            maximumLegs=1,navigationProfile='mondstadt-combat-scout-v1',routeId=SCOUT_GRASS_ROUTE)
        if reviewed_scout_route is not None:
            request.update(routeId=reviewed_scout_route.route_id,routeSpec=reviewed_scout_route.document(),
                           routeSpecSha256=reviewed_scout_route.sha256)
        points=reviewed_scout_route.points if reviewed_scout_route is not None else route_points(SCOUT_GRASS_ROUTE)
        request.update(cls.reviewed_scene(session_dir,owner,request['routeId'],points,reviewed_scout_route))
        request_path=session_dir/'requests'/('e'*32+'.json')
        request_sha=cls.write(request_path,request)
        reuse=dict(version=1,sessionId='c'*32,runId='9'*32,worker=worker,owner=owner,
            modelConfigurationSha256=fingerprint,sessionProof=str(source),sessionProofSha256=source_sha,
            requestId='e'*32,requestFile=str(request_path),requestSha256=request_sha,
            routeId=SCOUT_GRASS_ROUTE,navigationProfile='mondstadt-combat-scout-v1')
        if reviewed_scout_route is not None:
            reuse.update({key:request[key] for key in ('routeId','routeSpec','routeSpecSha256')})
        proof_path=Path(str(run_path)+'.reuse.json')
        digest=cls.write(proof_path,reuse)
        run.update(runId='9'*32,windowsSessionId=3,modelLoads=0,modelLoadSeconds=0.0,
            observationProfile='p2p-native-hamming-192-v1',policyReuse=copy.deepcopy(reuse),policyReuseSha256=digest,
            endReason='hybridLegLimit')
        run.update(cls.goal_state(),goalChanges=[])
        if part is not None:
            part.update(initialGoalState=cls.goal_state(),finalGoalState=cls.goal_state(),leaseInitialGoalState=cls.goal_state(),goalChanges=[])
            for decision in part.get('decisions',[]):
                decision.update(controlEpoch=0,policyGoalVersion=0,appliedGoalRequestId=None,goalIntent='ground-navigation')
        run.setdefault('segments',[{}])
        for segment in run['segments']:segment.update(processId=22,instanceNonce='b'*32)
        return proof_path,reuse

    @classmethod
    def executed_proof(cls,path,run,hold=50):
        """Seal the opt-in mode and selected hold through every original session/request document."""
        from scout_encounter_guard import binding_from_review,guard_policy
        from p2p_executed_history import executed_history_policy
        proof,reuse=cls.proof(path,run,dict(p2p_executed_history=True,action_hold_ms=hold,
            p2p_execution_feedback=True,navigation_climb_recovery=False,native_combat_observation=True))
        source=Path(reuse['sessionProof'])
        session=json.loads(source.read_bytes())
        manifest_path=source.parent/'manifest.json'
        manifest=json.loads(manifest_path.read_bytes())
        request_path=Path(reuse['requestFile'])
        request=json.loads(request_path.read_bytes())
        review=json.loads(Path(request['reviewFile']).read_bytes())
        binding=binding_from_review(review,request['reviewSha256'])
        snapshot=source.parent.parent/'source-snapshot'
        snapshot.mkdir(exist_ok=True)
        hashes={}
        for name in EXECUTED_HISTORY_SOURCE_NAMES:
            raw=('# synthetic archived '+name+'\n').encode()
            (snapshot/name).write_bytes(raw)
            hashes[name]=hashlib.sha256(raw).hexdigest()
        configuration=session['configuration']
        configuration.update(executedHistorySourceSha256=hashes,executedHistoryPolicy=executed_history_policy(hold))
        fingerprint=hashlib.sha256(json.dumps(configuration,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        manifest['configuration']=copy.deepcopy(configuration)
        for document in (manifest,session,request,reuse):
            document.update(historyCommitMode=EXECUTED_HISTORY_MODE,actionHoldMs=hold,modelConfigurationSha256=fingerprint)
        run.update(historyCommitMode=EXECUTED_HISTORY_MODE,actionHoldMs=hold)
        for document in (manifest,session):document['scoutEncounterGuardPolicy']=guard_policy()
        for document in (request,reuse,run):document['scoutEncounterGuard']=copy.deepcopy(binding)
        cls.write(manifest_path,manifest)
        reuse['sessionProofSha256']=cls.write(source,session)
        cls.reseal_request(run,proof,reuse,request)
        return proof,reuse

    def test_executed_history_requires_original_source_bytes_and_exact_policy_descriptor(self):
        """A rehashed proof cannot omit a dependency, change the receipt policy or substitute an archive."""
        for mutation in ('changed-file','missing-file','missing-pin','descriptor','manifest-configuration'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as directory:
                run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                proof,reuse=self.executed_proof(path,run)
                source=Path(reuse['sessionProof']);session=json.loads(source.read_bytes())
                manifest_path=source.parent/'manifest.json';manifest=json.loads(manifest_path.read_bytes())
                request=json.loads(Path(reuse['requestFile']).read_bytes())
                target=source.parent.parent/'source-snapshot'/'p2p_executed_history.py'
                if mutation=='changed-file':target.write_bytes(target.read_bytes()+b'# replaced\n')
                elif mutation=='missing-file':target.unlink()
                elif mutation=='missing-pin':session['configuration']['executedHistorySourceSha256'].pop(target.name)
                elif mutation=='descriptor':session['configuration']['executedHistoryPolicy']['requiredReceiptStatus']='replaced'
                else:manifest['configuration']['goalSha256']='0'*64
                if mutation in ('missing-pin','descriptor'):
                    fingerprint=hashlib.sha256(json.dumps(session['configuration'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
                    for document in (manifest,session,request,reuse):document['modelConfigurationSha256']=fingerprint
                    manifest['configuration']=copy.deepcopy(session['configuration'])
                self.write(manifest_path,manifest)
                reuse['sessionProofSha256']=self.write(source,session)
                self.reseal_request(run,proof,reuse,request)
                with self.assertRaises((ValueError,OSError)):verify_policy_reuse(run,path,proof)

    def test_resident_summary_must_retain_the_exact_declared_mode_and_integer_hold(self):
        """New summary fields are claims about the original worker, not independent timing overrides."""
        for key,value in (('historyCommitMode','accepted-proposals-only'),('historyCommitMode',None),
                          ('actionHoldMs',60),('actionHoldMs',100),('actionHoldMs',50.0),('actionHoldMs',True),
                          ('actionHoldMs',None)):
            with self.subTest(key=key,value=value),tempfile.TemporaryDirectory() as directory:
                run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                proof,reuse=self.executed_proof(path,run)
                if value is None:run.pop(key)
                else:run[key]=value
                with self.assertRaisesRegex(ValueError,'Resident summary executed-history'):
                    verify_policy_reuse(run,path,proof)

    def test_executed_history_mode_and_hold_are_bound_across_the_original_chain(self):
        """Neither a self-consistent short hold nor a stripped declaration can select historical replay."""
        for hold in (50,60):
            for selected in (None,'manifest','session','request','reuse'):
                for mutation in ('mode','hold','missing') if selected else ('none',):
                    with self.subTest(hold=hold,selected=selected,mutation=mutation),tempfile.TemporaryDirectory() as directory:
                        run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                        proof,reuse=self.executed_proof(path,run,hold)
                        source=Path(reuse['sessionProof'])
                        targets=dict(manifest=source.parent/'manifest.json',session=source,
                                     request=Path(reuse['requestFile']),reuse=proof)
                        if selected:
                            document=json.loads(targets[selected].read_bytes())
                            if mutation=='mode':document['historyCommitMode']='accepted-proposals-only'
                            elif mutation=='hold':document['actionHoldMs']=60 if hold==50 else 50
                            else:document.pop('historyCommitMode')
                            self.write(targets[selected],document)
                            if selected=='reuse':reuse=document
                            reuse['sessionProofSha256']=hashlib.sha256(source.read_bytes()).hexdigest()
                            reuse['requestSha256']=hashlib.sha256(Path(reuse['requestFile']).read_bytes()).hexdigest()
                            run.update(policyReuse=copy.deepcopy(reuse),policyReuseSha256=self.write(proof,reuse))
                            with self.assertRaisesRegex(ValueError,'mode or hold differs'):verify_policy_reuse(run,path,proof)
                        else:
                            self.assertEqual(verify_policy_reuse(run,path,proof)['actionHoldMs'],hold)

    def test_executed_history_proof_cannot_keep_recovery_authority(self):
        """A fresh successor or hidden recovery declaration cannot retain the opted-in policy."""
        for selected,key in (('manifest','inspectedObstacleRecoveryPolicy'),('session','recoverySourceSha256'),
                             ('request','obstacleRecovery'),('reuse','inspectedObstacleRecovery')):
            with self.subTest(selected=selected,key=key),tempfile.TemporaryDirectory() as directory:
                run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                proof,reuse=self.executed_proof(path,run)
                source=Path(reuse['sessionProof'])
                targets=dict(manifest=source.parent/'manifest.json',session=source,request=Path(reuse['requestFile']),reuse=proof)
                document=json.loads(targets[selected].read_bytes());document[key]={}
                self.write(targets[selected],document)
                if selected=='reuse':reuse=document
                reuse['sessionProofSha256']=hashlib.sha256(source.read_bytes()).hexdigest()
                reuse['requestSha256']=hashlib.sha256(Path(reuse['requestFile']).read_bytes()).hexdigest()
                run.update(policyReuse=copy.deepcopy(reuse),policyReuseSha256=self.write(proof,reuse))
                with self.assertRaisesRegex(ValueError,'recovery authority'):verify_policy_reuse(run,path,proof)

    def test_short_hold_without_the_mode_and_undeclared_mode_remnants_are_rejected(self):
        """The ordinary cached contract still accepts100ms and never acquires a new mode implicitly."""
        for settings in ({},{'p2p_executed_history':False},{'action_hold_ms':50},
                         {'p2p_executed_history':True},{'p2p_executed_history':1,'action_hold_ms':50}):
            with self.subTest(settings=settings),tempfile.TemporaryDirectory() as directory:
                run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                proof,reuse=self.proof(path,run,settings)
                if settings.get('action_hold_ms',100)!=100 or settings.get('p2p_executed_history',False):
                    with self.assertRaises(ValueError):verify_policy_reuse(run,path,proof)
                else:self.assertEqual(verify_policy_reuse(run,path,proof)['runId'],'9'*32)
        for selected in ('manifest','session','request','reuse'):
            with self.subTest(undeclared=selected),tempfile.TemporaryDirectory() as directory:
                run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                proof,reuse=self.proof(path,run)
                source=Path(reuse['sessionProof'])
                targets=dict(manifest=source.parent/'manifest.json',session=source,request=Path(reuse['requestFile']),reuse=proof)
                document=json.loads(targets[selected].read_bytes());document['historyCommitMode']=EXECUTED_HISTORY_MODE
                self.write(targets[selected],document)
                if selected=='reuse':reuse=document
                reuse['sessionProofSha256']=hashlib.sha256(source.read_bytes()).hexdigest()
                reuse['requestSha256']=hashlib.sha256(Path(reuse['requestFile']).read_bytes()).hexdigest()
                run.update(policyReuse=copy.deepcopy(reuse),policyReuseSha256=self.write(proof,reuse))
                with self.assertRaisesRegex(ValueError,'undeclared executed-history'):verify_policy_reuse(run,path,proof)

    def test_zero_load_requires_explicit_matching_proof(self):
        """Ordinary audits retain their original one-load contract unchanged."""
        self.assertIsNone(verify_policy_reuse(dict(modelLoads=1),'unused',None))
        with self.assertRaises(ValueError):verify_policy_reuse(dict(modelLoads=0),'unused',None)
        with tempfile.TemporaryDirectory() as directory:
            run={}
            path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
            proof,_=self.proof(path,run)
            self.assertEqual(verify_policy_reuse(run,path,proof)['runId'],'9'*32)
            proof.unlink()
            with self.assertRaises((ValueError,OSError)):verify_policy_reuse(run,path,proof)

    def test_guard_declaration_cannot_disagree_with_the_original_session_manifest(self):
        """Removing either declaration cannot downgrade guarded evidence to historical semantics."""
        from scout_encounter_guard import guard_policy
        for declared_in in ('manifest','proof'):
            with self.subTest(declared_in=declared_in),tempfile.TemporaryDirectory() as directory:
                run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                proof,reuse=self.proof(path,run)
                source=Path(reuse['sessionProof'])
                selected=source.parent/'manifest.json' if declared_in=='manifest' else source
                document=json.loads(selected.read_bytes());document['scoutEncounterGuardPolicy']=guard_policy()
                self.write(selected,document)
                reuse['sessionProofSha256']=hashlib.sha256(source.read_bytes()).hexdigest()
                run.update(policyReuse=copy.deepcopy(reuse),policyReuseSha256=self.write(proof,reuse))
                with self.assertRaisesRegex(ValueError,'declaration differs from the original session manifest'):
                    verify_policy_reuse(run,path,proof)

    def test_historical_reuse_rejects_guard_remnants_anywhere_in_the_original_chain(self):
        """A terminal trip or release record is never compatible with an undeclared historical guard."""
        for location in ('manifest','session','request','reuse','run'):
            for field in ('scoutEncounterGuardState','scoutEncounterGuardRelease'):
                with self.subTest(location=location,field=field),tempfile.TemporaryDirectory() as directory:
                    run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                    proof,reuse=self.proof(path,run);source=Path(reuse['sessionProof'])
                    manifest_path=source.parent/'manifest.json';request_path=Path(reuse['requestFile'])
                    manifest=json.loads(manifest_path.read_bytes());session=json.loads(source.read_bytes())
                    request=json.loads(request_path.read_bytes())
                    target=dict(manifest=manifest,session=session,request=request,reuse=reuse,run=run)[location]
                    target[field]=dict(trip=dict(reason='enemyBarCandidate'))
                    self.write(manifest_path,manifest)
                    reuse.update(sessionProofSha256=self.write(source,session),requestSha256=self.write(request_path,request))
                    run.update(policyReuse=copy.deepcopy(reuse),policyReuseSha256=self.write(proof,reuse))
                    with self.assertRaisesRegex(ValueError,'undeclared encounter guard'):
                        verify_policy_reuse(run,path,proof)

    def test_original_manifest_is_required_and_bound_even_for_historical_reuse(self):
        """Historical acceptance still requires the original worker manifest and matching session identity."""
        for change in ('missing','sessionId','modelConfigurationSha256'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                proof,reuse=self.proof(path,run);manifest=Path(reuse['sessionProof']).parent/'manifest.json'
                if change=='missing':manifest.unlink()
                else:
                    document=json.loads(manifest.read_bytes());document[change]='changed';self.write(manifest,document)
                with self.assertRaises((ValueError,OSError)):verify_policy_reuse(run,path,proof)

    @classmethod
    def reseal_request(cls, run, proof_path, reuse, request):
        """Rehash a test mutation so semantic validation, rather than a stale outer digest, must reject it."""
        reuse['requestSha256']=cls.write(Path(reuse['requestFile']),request)
        run.update(policyReuse=copy.deepcopy(reuse),policyReuseSha256=cls.write(proof_path,reuse))

    def test_fixed_and_custom_proofs_reopen_every_original_review_artifact(self):
        """Removing or changing a nested artifact invalidates an otherwise unchanged reuse chain."""
        from reviewed_scout_route import ReviewedScoutRoute
        for spec in (None,ReviewedScoutRoute(((-1135,2267),(-1142,2255)))):
            for selected in ('review','plan','result','image','metadata'):
                for remove in (False,True):
                    with self.subTest(custom=spec is not None,file=selected,remove=remove),tempfile.TemporaryDirectory() as directory:
                        run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                        proof,reuse=self.proof(path,run,reviewed_scout_route=spec)
                        request=json.loads(Path(reuse['requestFile']).read_bytes());review_path=Path(request['reviewFile'])
                        review=json.loads(review_path.read_bytes());folder=Path(review['nativeEndpoint']);image=folder/review['imageName']
                        target=dict(review=review_path,plan=folder/'plan.json',result=folder/'result.json',image=image,metadata=image.with_suffix('.json'))[selected]
                        verify_policy_reuse(run,path,proof)
                        if remove:target.unlink()
                        else:target.write_bytes(target.read_bytes()+b'\n')
                        with self.assertRaises((ValueError,OSError)):verify_policy_reuse(run,path,proof)

    def test_rehashed_native_review_must_still_prove_owner_scope_and_stable_start(self):
        """A freshly hashed false passive review cannot authorize another owner, pose, motion or source."""
        cases=('owner','plan-input','plan-model','profile','result-input','result-status','cleanup','missing-sample',
               'start','scope','confidence','stale','motion','space','input-history','gap','yaw','world-source',
               'missing-world-epoch','image-source','duplicate-poll')
        for case in cases:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as directory:
                run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                proof,reuse=self.proof(path,run);request=json.loads(Path(reuse['requestFile']).read_bytes())
                review=json.loads(Path(request['reviewFile']).read_bytes());folder=Path(review['nativeEndpoint'])
                plan=json.loads((folder/'plan.json').read_bytes());result=json.loads((folder/'result.json').read_bytes())
                metadata_path=(folder/review['imageName']).with_suffix('.json');metadata=json.loads(metadata_path.read_bytes())
                if case=='owner':plan['owner']['child']['instanceNonce']='8'*32
                if case=='plan-input':plan['enableInput']=True
                if case=='plan-model':plan['modelLoaded']=True
                if case=='profile':plan['navigationProfile']='other'
                if case=='result-input':result['inputEnabled']=True
                if case=='result-status':result['status']='failed'
                if case=='cleanup':result['ownerIdleMinimizedAfter']=False
                if case=='missing-sample':result['observations'].pop(0)
                for frames in (result['stableSamples'],result['observations']):
                    for frame in frames:
                        if case=='missing-world-epoch':frame['frameWorldReadiness'].pop('epoch')
                        if frame['frameId']!=3:continue
                        pose=frame['navigationPose']
                        if case=='start':pose['x']+=5
                        if case=='scope':pose['layerId']='Unknown'
                        if case=='confidence':pose['positionConfidence']=.98
                        if case=='stale':frame['sourceFrameAgeMs']=151
                        if case=='motion':frame['motionEvidence']['status']='climbing'
                        if case=='space':frame['motionEvidence']['spaceKeyMatched']=True
                        if case=='input-history':frame['executionContext']['lastSequence']=1
                        if case=='gap':
                            frame['sourceFrame']['freshnessAtMs']=251
                            frame['frameWorldReadiness']['sourceFrame']['freshnessAtMs']=251
                        if case=='yaw':pose['yawDegrees']+=4
                        if case=='world-source':frame['frameWorldReadiness']['sourceFrameId']=99
                if case=='image-source':metadata['sourceFrame']['captureEpoch']='other'
                if case=='duplicate-poll':
                    poll=copy.deepcopy(result['observations'][1]);poll['navigationPose']['x']+=.1
                    result['observations'].append(poll)
                request.update(nativePlanSha256=self.write(folder/'plan.json',plan),nativeResultSha256=self.write(folder/'result.json',result),
                               imageMetadataSha256=self.write(metadata_path,metadata))
                self.reseal_request(run,proof,reuse,request)
                with self.assertRaises(ValueError):verify_policy_reuse(run,path,proof)

    def test_rehashed_oversized_image_metadata_is_refused_before_json_decoding(self):
        """A valid nested hash cannot authorize an unbounded metadata read."""
        with tempfile.TemporaryDirectory() as directory:
            run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
            proof,reuse=self.proof(path,run);request=json.loads(Path(reuse['requestFile']).read_bytes())
            review=json.loads(Path(request['reviewFile']).read_bytes())
            metadata_path=(Path(review['nativeEndpoint'])/review['imageName']).with_suffix('.json')
            metadata=json.loads(metadata_path.read_bytes());metadata['padding']='x'*65536
            request['imageMetadataSha256']=self.write(metadata_path,metadata)
            self.reseal_request(run,proof,reuse,request)
            with self.assertRaisesRegex(ValueError,'bounded size'):verify_policy_reuse(run,path,proof)

    def test_image_join_requires_a_fresh_qualified_poll_but_accepts_identical_repeated_polls(self):
        """Retain real repeated polling without allowing an unqualified PNG to borrow other stable samples."""
        for qualified in (False,True):
            with self.subTest(qualified=qualified),tempfile.TemporaryDirectory() as directory:
                run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                proof,reuse=self.proof(path,run);request=json.loads(Path(reuse['requestFile']).read_bytes())
                review=json.loads(Path(request['reviewFile']).read_bytes());folder=Path(review['nativeEndpoint'])
                result=json.loads((folder/'result.json').read_bytes());poll=copy.deepcopy(result['observations'][1])
                if qualified:
                    poll['sourceFrameAgeMs']=200
                else:
                    poll.update(frameId=4,sourceFrameAgeMs=151)
                    poll['navigationPose']['frameId']=4
                    poll['frameWorldReadiness']['sourceFrameId']=4
                    metadata_path=(folder/review['imageName']).with_suffix('.json')
                    metadata=json.loads(metadata_path.read_bytes());metadata['frameId']=4
                    request['imageMetadataSha256']=self.write(metadata_path,metadata)
                result['observations'].append(poll)
                request['nativeResultSha256']=self.write(folder/'result.json',result)
                self.reseal_request(run,proof,reuse,request)
                if qualified:self.assertEqual(verify_policy_reuse(run,path,proof)['runId'],run['runId'])
                else:
                    with self.assertRaisesRegex(ValueError,'qualified fresh'):verify_policy_reuse(run,path,proof)

    def test_cached_resident_goal_request_history_cannot_be_hidden_by_version_zero(self):
        """Pending, rejected and applied changes are all disallowed for the frozen cached policy."""
        changes=dict(policyGoalVersion=1,appliedGoalRequestId='applied',goalRequestId='pending',goalRequestStatus='pending',
                     goalError='encoder failed',goalIntent='combat',goalChanges=[dict(status='requested')])
        for field,value in changes.items():
            for remove in (False,True):
                with self.subTest(field=field,remove=remove),tempfile.TemporaryDirectory() as directory:
                    run={};path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json';proof,_=self.proof(path,run)
                    if remove:run.pop(field)
                    else:run[field]=value
                    with self.assertRaises(ValueError):verify_policy_reuse(run,path,proof)

    def test_replayed_or_mismatched_run_session_worker_owner_request_is_rejected(self):
        """Rehashing an altered per-run proof cannot sever its original session/request bindings."""
        changes={
            'run':lambda reuse:reuse.update(runId='8'*32),
            'session':lambda reuse:reuse.update(sessionId='8'*32),
            'worker':lambda reuse:reuse['worker'].update(processId=44),
            'child':lambda reuse:reuse['owner']['child'].update(instanceNonce='8'*32),
            'configuration':lambda reuse:reuse.update(modelConfigurationSha256='8'*64),
            'request':lambda reuse:reuse.update(requestSha256='8'*64),
            'route':lambda reuse:reuse.update(routeId='other-route'),
        }
        for name,change in changes.items():
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                run={}
                path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                proof,reuse=self.proof(path,run)
                change(reuse)
                run.update(policyReuse=copy.deepcopy(reuse),policyReuseSha256=self.write(proof,reuse))
                with self.assertRaises(ValueError):verify_policy_reuse(run,path,proof)

    def test_self_consistent_proof_cannot_change_policy_sampling_or_input_limits(self):
        """Even fully rehashed documents must still describe the reviewed Open P2P configuration."""
        for change in (dict(history=42),dict(action_hold_ms=101),dict(max_observation_age_ms=151),dict(hybrid_legs=2)):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                run={}
                path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
                proof,_=self.proof(path,run,change)
                with self.assertRaises(ValueError):verify_policy_reuse(run,path,proof)

    def test_landmark_checkpoint_cannot_be_a_cached_open_p2p_policy(self):
        """Reject the prior wrong model pin even when every proof hash is internally consistent."""
        from landmark_recognizer import G4_SHA256
        with tempfile.TemporaryDirectory() as directory:
            run={}
            path=Path(directory).resolve()/'session'/'legs'/('e'*32)/'run.json'
            proof,_=self.proof(path,run,checkpoint_sha=G4_SHA256)
            with self.assertRaisesRegex(ValueError,'Open P2P checkpoint changed'):
                verify_policy_reuse(run,path,proof)


class ExecutedHistoryAuditTests(unittest.TestCase):
    """Replay a serialized executed-action history without loading weights or opening native endpoints."""
    @staticmethod
    def trace(hold=50,count=3):
        """Retain one refused prediction followed by real-shaped native/model completed receipts."""
        from p2p_executed_history import encode_controller_step,executed_history_policy
        frames={}
        part=dict(historyCommitMode=EXECUTED_HISTORY_MODE,
            policyMetadata=dict(historyFrames=41,historyCommit=EXECUTED_HISTORY_MODE,historyCommitMode=EXECUTED_HISTORY_MODE),
            proposalJournal=dict(version=3,historyCommitMode=EXECUTED_HISTORY_MODE),
            executedHistoryPolicy=executed_history_policy(hold),serverDroppedReceipts=0,
            recording=dict(complete=True,lossless=True,closed=True,workerRetired=True,error=None,
                           droppedFrames=0,droppedEvents=0,droppedObservations=0,abandonedFrames=0),
            hello=dict(sessionId='lease',ownerEpoch='owner',goalVersion=1),
            decisions=[],receipts=[],executedHistoryEvents=[])
        rows=[dict(type='episodeStart',sessionId='lease',historyCommitMode=EXECUTED_HISTORY_MODE,
                   executedHistoryPolicy=executed_history_policy(hold),proposalJournal=copy.deepcopy(part['proposalJournal']))]
        previous=None
        committed=0
        for index in range(count):
            frame_id=index+1;observed=100+index*200
            source=dict(captureEpoch='pixels',timestamp100ns=observed*10000,capturedAtMs=observed,
                        acquiredAtMs=observed+3,freshnessAtMs=observed,freshnessClockKind='reported_compositor_qpc')
            frames[frame_id]=dict(frameId=frame_id,capturedAtMs=observed+3,sourceFrame=source)
            model='hybrid-native' if index%2 else 'open-p2p'
            step=dict(keys=['W'] if index%2 else [],durationMs=hold,mouseDx=0 if index%2 else 3,mouseDy=0)
            accepted=index>0
            acceptance=(dict(type='accepted',requestId='action-'+str(index),acceptedAtMs=observed+10)
                        if accepted else dict(type='notSubmitted',reason='staleObservation'))
            request=acceptance.get('requestId')
            arguments=receipt=None
            if accepted:
                arguments=dict(version=1,command='action',**part['hello'],requestId=request,frameId=frame_id,
                    modelId=model,observedAtMs=observed+3,startBeforeMs=observed+150,expiresAtMs=observed+700,steps=[step])
                receipt=dict(requestId=request,frameId=frame_id,modelId=model,status='completed',reason='horizon_complete',
                    acceptedAtMs=observed+10,endedAtMs=observed+hold+15,
                    appliedSteps=[dict(index=0,startedAtMs=observed+12,keys=step['keys'],mouseDx=step['mouseDx'],mouseDy=0)])
                part['receipts'].append(copy.deepcopy(receipt));rows.append(copy.deepcopy(receipt))
            history=dict(beforeFrames=committed,afterFrames=committed+int(accepted),validFrames=min(committed+int(accepted),41),
                beforeIndex=committed*12,afterIndex=(committed+int(accepted))*12,
                beforeValidTokens=min(committed,41)*12,afterValidTokens=min(committed+int(accepted),41)*12)
            event=dict(type='p2pExecutedHistory',version=1,historyCommitMode=EXECUTED_HISTORY_MODE,
                outcome='committed' if accepted else 'rejected',requestId=request,frameId=frame_id,modelId=model,
                sourceFrame=copy.deepcopy(source),observationTimestampMs=observed,step=copy.deepcopy(step),
                encodedAction=encode_controller_step(step),acceptance=copy.deepcopy(acceptance),receipt=copy.deepcopy(receipt),
                arguments=copy.deepcopy(arguments),previousReceipt=copy.deepcopy(previous),history=history,error=None,
                clientTimeNs=1_000_000*(index+1))
            decision=dict(frameId=frame_id,observationTimestampMs=observed,steps=[copy.deepcopy(step)],
                acceptance=copy.deepcopy(acceptance),hybridNavigation=dict(owner=model),historyCommitted=accepted,
                rawPolicySteps=[dict(keys=['SPACE'],durationMs=100,mouseDx=0,mouseDy=0)],executedHistory=copy.deepcopy(event),
                executedHistoryPredecessor=copy.deepcopy(previous))
            proposal=dict(type='proposal',proposalJournalVersion=3,historyCommitMode=EXECUTED_HISTORY_MODE,
                frameId=frame_id,observationTimestampMs=observed,hybridNavigation=copy.deepcopy(decision['hybridNavigation']),
                rawPolicySteps=copy.deepcopy(decision['rawPolicySteps']),
                observedAtMs=observed+3,model=model,steps=[copy.deepcopy(step)],acceptance=copy.deepcopy(acceptance),
                historyCommitted=accepted,startBeforeMs=observed+150 if accepted else None,
                executedHistoryPredecessor=copy.deepcopy(previous))
            part['decisions'].append(decision);part['executedHistoryEvents'].append(copy.deepcopy(event))
            rows.extend([proposal,copy.deepcopy(event)])
            if accepted:
                committed+=1;previous=dict(requestId=request,endedAtMs=receipt['endedAtMs'])
        return dict(acceptedInputActions=committed),part,frames,rows,dict(historyCommitMode=EXECUTED_HISTORY_MODE,actionHoldMs=hold)

    @staticmethod
    def replace_event(part,rows,index,change):
        """Reapply a semantic mutation to all retained copies, defeating simple outer equality checks."""
        event=copy.deepcopy(part['executedHistoryEvents'][index]);change(event)
        part['executedHistoryEvents'][index]=copy.deepcopy(event)
        part['decisions'][index]['executedHistory']=copy.deepcopy(event)
        ordinal=[number for number,row in enumerate(rows) if row.get('type')=='p2pExecutedHistory'][index]
        rows[ordinal]=copy.deepcopy(event)

    def replay(self,trace):
        """Use the real bounded JSONL reader instead of passing an in-memory journal shortcut."""
        run,part,frames,rows,reuse=trace
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();recording=root/'00001';recording.mkdir()
            (recording/'events.jsonl').write_text('\n'.join(json.dumps(row) for row in rows),encoding='utf-8')
            return verify_executed_history(run,[part],frames,[dict(number=1)],root,reuse)

    def test_native_and_policy_selections_commit_only_completed_steps_with_bounded_history(self):
        """A refused prediction rolls back; native corrections and model choices share the actual-action history."""
        for hold,count in ((50,3),(60,3),(50,44)):
            with self.subTest(hold=hold,count=count):
                result=self.replay(self.trace(hold,count))
                self.assertEqual(result['committedActions'],count-1)
                self.assertEqual(result['rejectedPredictions'],1)
                self.assertEqual(result['finalHistoryFrames'],count-1)
                self.assertEqual(result['finalValidHistoryFrames'],min(count-1,41))
                self.assertFalse(result['physicalInputDeliveryVerified'])

    def test_actual_stream_loop_journal_replays_native_and_model_commits(self):
        """Join the production stream/controller loop using only inert policy, recorder and native boundaries."""
        from test_p2p_executed_history_stream import inert_arguments,run_fixture
        from test_stream_client import CapturingRecorder

        class RetainedRecorder(CapturingRecorder):
            """Report accurate closure of the synchronous in-memory fixture, which has no writer thread."""
            def close(self):
                """All stored records remain present and no simulated queue can drop them."""
                return dict(super().close(),lossless=True,closed=True,workerRetired=True,
                    droppedFrames=0,droppedEvents=0,droppedObservations=0,abandonedFrames=0)

        for hold in (50,60):
            with self.subTest(hold=hold),tempfile.TemporaryDirectory() as directory:
                root=Path(directory).resolve()
                code,part,recorder,bridge,policy=run_fixture(root,recorder=RetainedRecorder(),args=inert_arguments(root,hold=hold))
                self.assertEqual((code,part['status']),(0,'completed'))
                record=root/'independent-history-recording'/'00001';record.mkdir(parents=True)
                (record/'events.jsonl').write_text('\n'.join(json.dumps(row) for row in recorder.events),encoding='utf-8')
                frames={metadata['frameId']:metadata for metadata,pixels in recorder.frames}
                result=verify_executed_history(part,[part],frames,[dict(number=1)],record.parent,
                    dict(historyCommitMode=EXECUTED_HISTORY_MODE,actionHoldMs=hold))
                self.assertEqual((result['committedActions'],result['finalHistoryFrames']),(3,3))
                self.assertEqual(len(policy.commits),3)

    def test_explicit_server_rejection_rolls_back_without_a_terminal_receipt(self):
        """A bound rejection is distinct from admission and leaves the next prediction's cache empty."""
        trace=self.trace();run,part,frames,rows,reuse=trace
        acceptance=dict(type='rejected',requestId='rejected-0',reason='focusNotReady')
        step=part['decisions'][0]['steps'][0]
        arguments=dict(version=1,command='action',**part['hello'],requestId='rejected-0',frameId=1,modelId='open-p2p',
            observedAtMs=103,startBeforeMs=250,expiresAtMs=800,steps=[copy.deepcopy(step)])
        part['decisions'][0]['acceptance']=copy.deepcopy(acceptance)
        proposal=[row for row in rows if row.get('type')=='proposal'][0]
        proposal.update(acceptance=copy.deepcopy(acceptance),startBeforeMs=250)
        self.replace_event(part,rows,0,lambda event:event.update(acceptance=copy.deepcopy(acceptance),
            requestId='rejected-0',arguments=copy.deepcopy(arguments)))
        result=self.replay(trace)
        self.assertEqual((result['committedActions'],result['rejectedPredictions']),(2,1))

    def test_missing_duplicate_reordered_and_contradictory_journal_rows_are_rejected(self):
        """A report cannot invent a terminal receipt or a history commit that its original journal lacks."""
        for mutation in ('missing-event','duplicate-event','missing-receipt','duplicate-receipt','late-receipt','report-only','receipt-only'):
            with self.subTest(mutation=mutation):
                trace=self.trace();run,part,frames,rows,reuse=trace
                receipt_index=next(i for i,row in enumerate(rows) if 'appliedSteps' in row)
                if mutation=='missing-event':rows.pop()
                elif mutation=='duplicate-event':rows.append(copy.deepcopy(rows[-1]))
                elif mutation=='missing-receipt':rows.pop(receipt_index)
                elif mutation=='duplicate-receipt':rows.append(copy.deepcopy(rows[receipt_index]))
                elif mutation=='late-receipt':rows.append(rows.pop(receipt_index))
                elif mutation=='report-only':part['executedHistoryEvents'][1]['step']['mouseDx']=2
                else:part['receipts'][0]['endedAtMs']+=1
                with self.assertRaises(ValueError):self.replay(trace)

    def test_replaced_cancelled_empty_and_mismatched_receipts_cannot_be_committed(self):
        """Rehash-equivalent copies still need a positive completed single-step native interval."""
        for mutation in ('replaced','cancelled','reason','empty','extra-step','index','keys','mouse','frame','model',
                         'admission','late-start','zero-interval','expired','unknown-request'):
            with self.subTest(mutation=mutation):
                trace=self.trace();run,part,frames,rows,reuse=trace
                receipt=copy.deepcopy(part['receipts'][0])
                if mutation in ('replaced','cancelled'):receipt['status']=mutation
                elif mutation=='reason':receipt['reason']='client_stop'
                elif mutation=='empty':receipt['appliedSteps']=[]
                elif mutation=='extra-step':receipt['appliedSteps']*=2
                elif mutation=='index':receipt['appliedSteps'][0]['index']=1
                elif mutation=='keys':receipt['appliedSteps'][0]['keys']=['SPACE']
                elif mutation=='mouse':receipt['appliedSteps'][0]['mouseDx']=1
                elif mutation=='frame':receipt['frameId']=1
                elif mutation=='model':receipt['modelId']='open-p2p'
                elif mutation=='admission':receipt['acceptedAtMs']-=1
                elif mutation=='late-start':receipt['appliedSteps'][0]['startedAtMs']=451
                elif mutation=='zero-interval':receipt['endedAtMs']=receipt['appliedSteps'][0]['startedAtMs']
                elif mutation=='expired':receipt['endedAtMs']=1000
                else:receipt['requestId']='unsubmitted'
                part['receipts'][0]=copy.deepcopy(receipt)
                index=next(i for i,row in enumerate(rows) if 'appliedSteps' in row)
                rows[index]=copy.deepcopy(receipt)
                self.replace_event(part,rows,1,lambda event:event.update(receipt=copy.deepcopy(receipt)))
                with self.assertRaises(ValueError):self.replay(trace)

    def test_host_capture_and_commanded_horizon_bound_the_terminal_interval(self):
        """Consistent evidence cannot admit a future host frame or finish before the commanded horizon."""
        for hold in (50,60):
            for mutation in ('exact-boundary','future-host-frame','short-horizon'):
                with self.subTest(hold=hold,mutation=mutation):
                    trace=self.trace(hold);run,part,frames,rows,reuse=trace
                    # Use the final action so a changed terminal does not merely
                    # fail the independent successor/predecessor equality check.
                    receipt=copy.deepcopy(part['receipts'][-1])
                    accepted=receipt['acceptedAtMs']
                    receipt['endedAtMs']=accepted+hold-(.001 if mutation=='short-horizon' else 0)
                    host_at=accepted+(1 if mutation=='future-host-frame' else 0)
                    frames[3]['capturedAtMs']=host_at
                    proposals=[row for row in rows if row.get('type')=='proposal']
                    proposals[-1]['observedAtMs']=host_at
                    part['receipts'][-1]=copy.deepcopy(receipt)
                    index=next(i for i,row in enumerate(rows) if row.get('requestId')==receipt['requestId']
                               and 'appliedSteps' in row)
                    rows[index]=copy.deepcopy(receipt)
                    def update_event(event):
                        """Keep every original envelope/event copy consistent with the selected mutation."""
                        event['arguments']['observedAtMs']=host_at
                        event['receipt']=copy.deepcopy(receipt)
                    self.replace_event(part,rows,2,update_event)
                    if mutation=='exact-boundary':
                        self.assertEqual(self.replay(trace)['committedActions'],2)
                    else:
                        with self.assertRaisesRegex(ValueError,'positive terminal interval'):
                            self.replay(trace)

    def test_prediction_sources_must_follow_the_last_completed_interval(self):
        """New poll/frame labels alone cannot replace a genuinely newer post-terminal native source."""
        for mutation in ('clock','raw-timestamp','capture-epoch','wrong-source','predecessor'):
            with self.subTest(mutation=mutation):
                trace=self.trace();run,part,frames,rows,reuse=trace
                proposal=[row for row in rows if row.get('type')=='proposal'][2]
                if mutation=='predecessor':
                    predecessor=dict(requestId='different',endedAtMs=part['receipts'][0]['endedAtMs'])
                    proposal['executedHistoryPredecessor']=predecessor
                    part['decisions'][2]['executedHistoryPredecessor']=copy.deepcopy(predecessor)
                    self.replace_event(part,rows,2,lambda event:event.update(previousReceipt=predecessor))
                else:
                    if mutation=='clock':
                        frames[3]['sourceFrame']['freshnessAtMs']=part['receipts'][0]['endedAtMs']
                        frames[3]['sourceFrame']['capturedAtMs']=part['receipts'][0]['endedAtMs']
                    elif mutation=='raw-timestamp':frames[3]['sourceFrame']['timestamp100ns']=frames[2]['sourceFrame']['timestamp100ns']
                    elif mutation=='capture-epoch':frames[3]['sourceFrame']['captureEpoch']='another'
                    else:frames[3]['sourceFrame']['timestamp100ns']+=1
                    if mutation!='wrong-source':
                        observed=frames[3]['sourceFrame']['freshnessAtMs']
                        part['decisions'][2]['observationTimestampMs']=proposal['observationTimestampMs']=observed
                        self.replace_event(part,rows,2,lambda event:event.update(sourceFrame=copy.deepcopy(frames[3]['sourceFrame']),
                                                                              observationTimestampMs=observed))
                with self.assertRaises(ValueError):self.replay(trace)

    def test_wrong_mode_hold_codec_envelope_and_cache_state_are_rejected(self):
        """History labels must represent the chosen controller action and preserve its settled cache state."""
        for mutation in ('mode','hold','codec','envelope','expiry','deadline','native-reset','refusal-advance','false-commit','climb'):
            with self.subTest(mutation=mutation):
                trace=self.trace();run,part,frames,rows,reuse=trace
                if mutation=='mode':part['policyMetadata']['historyCommitMode']='accepted-proposals-only'
                elif mutation=='hold':reuse['actionHoldMs']=60
                elif mutation=='climb':part['navigationClimbActions']=[dict(keys=['X'])]
                elif mutation=='false-commit':
                    part['decisions'][1]['historyCommitted']=False
                    [row for row in rows if row.get('type')=='proposal'][1]['historyCommitted']=False
                else:
                    def change(event):
                        """Mutate every copy of one claimed history transaction identically."""
                        if mutation=='codec':event['encodedAction']['keys']=[1,0,0,0]
                        elif mutation=='envelope':event['arguments']['sessionId']='another'
                        elif mutation=='expiry':event['arguments']['expiresAtMs']+=1
                        elif mutation=='deadline':event['arguments']['startBeforeMs']+=1
                        elif mutation=='native-reset':event['history'].update(afterFrames=0,afterIndex=0,afterValidTokens=0,validFrames=0)
                        else:event['history'].update(afterFrames=1,afterIndex=12,afterValidTokens=12,validFrames=1)
                    self.replace_event(part,rows,0 if mutation=='refusal-advance' else 1,change)
                with self.assertRaises(ValueError):self.replay(trace)

    def test_policy_declarations_and_terminal_retention_cannot_be_downgraded(self):
        """A completed receipt trace cannot conceal its altered policy or an incomplete original recording."""
        for mutation in ('descriptor','episode-start','server-drops','recorder-drops','not-closed','not-lossless','not-retired'):
            with self.subTest(mutation=mutation):
                trace=self.trace();run,part,frames,rows,reuse=trace
                if mutation=='descriptor':part['executedHistoryPolicy']['requiredReceiptStatus']='accepted'
                elif mutation=='episode-start':rows[0]['historyCommitMode']='accepted-proposals-only'
                elif mutation=='server-drops':part['serverDroppedReceipts']=1
                elif mutation=='recorder-drops':part['recording']['droppedObservations']=1
                else:part['recording'][{'not-closed':'closed','not-lossless':'lossless','not-retired':'workerRetired'}[mutation]]=False
                with self.assertRaises(ValueError):self.replay(trace)

    def test_legacy_history_replay_is_unchanged_but_new_event_downgrades_are_refused(self):
        """Ordinary100ms evidence stays outside this opt-in contract, including absent early journals."""
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(verify_executed_history({},[dict(proposalJournal=dict(version=2,
                historyCommitMode='accepted-proposals-only'))],{},[dict(number=1)],Path(directory),None))
        for mutation in ('part','journal','metadata'):
            with self.subTest(mutation=mutation):
                run,part,frames,rows,reuse=self.trace()
                if mutation=='part':part={'executedHistoryEvents':[]};rows=[]
                elif mutation=='journal':part={};rows=[dict(type='p2pExecutedHistory')]
                else:part={'policyMetadata':{'historyCommitMode':EXECUTED_HISTORY_MODE}};rows=[]
                with self.assertRaises(ValueError):self.replay((run,part,frames,rows,None))
