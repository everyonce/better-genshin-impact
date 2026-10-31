"""Inert failed-prefix evidence tests; synthetic RGB/native journals never open a lease."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import audit_scout_obstacle as audit
from hybrid_routes import route_points,route_heading,SCOUT_GRASS_ROUTE,SCOUT_GROVE_ROUTE
from scout_encounter_guard import ScoutEncounterGuard,binding_from_review,guard_policy,sensor_frame
import test_audit_hybrid_run as shared
from test_scout_encounter_guard import sample


def write(path, value):
    """Publish synthetic objects with exact hashes used by the production independent reader."""
    return shared.CachedPolicyAuditTests.write(Path(path),value)


def fixture(root):
    """Build one original failed, guarded, closed prefix and its complete cached-review chain."""
    folder=Path(root)/'session/legs'/('e'*32)
    record=folder/'patrol-recording/00001';record.mkdir(parents=True)
    part_path=folder/'patrol-segments/00001.json'
    run=dict(status='failed',error=audit.OBSTACLE_ERROR,evidenceComplete=False,failedLeases=1,
        connectionErrors=[],recordingBudgetExhausted=False,recordedBytes=3000000,inputRequested=True,
        acceptedInputActions=21,segments=[dict(number=1,report=str(part_path),exitCode=1,acceptedInputActions=21)])
    part={}
    proof_path,reuse=shared.CachedPolicyAuditTests.proof(folder/'patrol.json',run,part=part,
        settings_changes=dict(native_combat_observation=True))
    request_path=Path(reuse['requestFile']);request=json.loads(request_path.read_bytes())
    review=json.loads(Path(request['reviewFile']).read_bytes())
    binding=binding_from_review(review,request['reviewSha256'])
    for path in (Path(reuse['sessionProof']),folder.parent.parent/'manifest.json'):
        document=json.loads(path.read_bytes());document.update(scoutEncounterGuardPolicy=guard_policy(),
            inspectedObstacleRecoveryPolicy=audit.recovery_policy(),recoverySourceSha256=audit.source_contract())
        write(path,document)
    request['scoutEncounterGuard']=binding;reuse['requestSha256']=write(request_path,request)
    reuse.update(scoutEncounterGuard=binding,sessionProofSha256=hashlib.sha256(Path(reuse['sessionProof']).read_bytes()).hexdigest())
    run.update(policyReuse=reuse,policyReuseSha256=write(proof_path,reuse),endReason='error',scoutEncounterGuard=binding)
    guard=ScoutEncounterGuard(binding)
    frames=[];video=[];events=[];decisions=[];receipts=[]
    start,end=route_points(SCOUT_GRASS_ROUTE)
    for index in range(1,26):
        frame=sample(index)
        pose=dict(state='valid',frameId=index,x=start[0],y=start[1],yawDegrees=route_heading(dict(x=start[0],y=start[1]),end),
            layerId='MapBack_2',positionConfidence=.999,yawConfidence=.8)
        frame.update(capturedAtMs=index*100,navigationPose=pose,droppedReceipts=0,videoQueueAccepted=True,
            frameWorldReadiness=dict(ready=True,epoch=1,sourceFrameId=index,sourceFrame=frame['sourceFrame']),
            motionEvidence=dict(status='normal',spaceKeyMatched=False),inputAvailable=True)
        frames.append(frame)
        events.append(guard.observe(frame,index*1_000_000))
        if 4<=index<=24:
            identity=f'{index:032x}';step=dict(keys=['W'],mouseDx=0,mouseDy=0,durationMs=100)
            marker=guard.check_dispatch(frame,index*1_000_000+1)
            events.append(dict(type='scoutEncounterGuardDispatch',requestId=identity,marker=marker,
                frame=sensor_frame(frame),state=guard.snapshot()))
            ack=dict(type='accepted',requestId=identity,acceptedAtMs=index*100+20)
            selected=dict(owner='open-p2p',reason='modelRouteCompatible',target='end',completedLegs=0,pose=copy.deepcopy(pose),
                step=copy.deepcopy(step),modelSteps=[copy.deepcopy(step)])
            decision=dict(frameId=index,steps=[step],acceptance=ack,hybridNavigation=selected,
                observationTimestampMs=index*100,startBeforeMs=index*100+150,controlEpoch=0,policyGoalVersion=0,
                appliedGoalRequestId=None,goalIntent='ground-navigation',rawPolicySteps=[copy.deepcopy(step)],
                nativeCombatEvidence=copy.deepcopy(frame['combatEvidence']),estimatedObservationAgeMs=20,
                scoutEncounterGuard=marker,historyCommitted=True)
            decisions.append(decision);events.append(dict(decision,type='proposal'))
            receipt=dict(requestId=identity,frameId=index,modelId='open-p2p',acceptedAtMs=ack['acceptedAtMs'],
                status='cancelled' if index==24 else 'completed',reason='client_stop' if index==24 else 'horizon_complete',
                endedAtMs=index*100+100,appliedSteps=[dict(index=0,startedAtMs=index*100+21,keys=['W'],mouseDx=0,mouseDy=0)])
            receipts.append(receipt);events.append(copy.deepcopy(receipt))
        raw=bytes([index])*audit.RGB192_BYTES;name=f'policy-{index-1:08d}-frame-{index:012d}.rgb';(record/name).write_bytes(raw)
        video.append(dict({key:value for key,value in frame.items() if key!='videoQueueAccepted'},
            videoFrameIndex=index-1,policyRgb=dict(file=name,format='rgb24',width=192,height=192,
            bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())))
    recording=dict(encodedFrames=25,policyRgbFrames=25,recordedObservations=25,policyRgbBytes=25*audit.RGB192_BYTES,
        policyRgbEnabled=True,complete=True,lossless=True,closed=True,workerRetired=True,error=None,
        droppedFrames=0,droppedEvents=0,droppedObservations=0,abandonedFrames=0,recordedBytes=3000000)
    start_samples=[dict(frameId=f['frameId'],atMs=f['capturedAtMs'],**{key:f['navigationPose'][key] for key in ('x','y','yawDegrees')})
        for f in frames[:3]]
    calls=[]
    for identity,number,operation,origin,at in ((1,4,'keyDown','dispatch',421),(2,24,'releaseAll','release:client_stop',2500.1)):
        for offset,stage in enumerate(('started','returned' if operation=='keyDown' else 'returned_unverified')):
            calls.append(dict(sequence=len(calls)+1,atMs=at+offset*.1,requestId=f'{number:032x}',modelId='open-p2p',
                frameId=number,stepIndex=0,origin=origin,call=dict(callId=identity,operation=operation,stage=stage,
                    key='W' if operation=='keyDown' else None,mouseDx=0,mouseDy=0,error=None)))
    part.update(status='failed',error=audit.OBSTACLE_ERROR,endReason='error',residentRunId=run['runId'],
        episodeFailure=dict(type='RuntimeError',transportOperation=None),unappliedAcceptedActions=0,serverDroppedReceipts=0,
        inputRequested=True,nativeInputEnabled=True,actionHoldMs=100,maxObservationAgeMs=150,decisionHz=10,capturePollHz=20,
        effectiveInputKeys=['W','A','S','D'],navigationClimbActions=[],navigationIdleRecovery=dict(enabled=False),navigationIdleRecoveryEvents=[],
        segment=dict(number=1,startedAtClientNs=1,endedAtClientNs=2_500_000_001,leaseEnded=True),
        continuity=dict(previousReport=None,sameBridgeLease=False,pendingProposals=[],pendingRecoveryActions=[],sourceFrames=[]),
        framesReceived=25,recording=recording,scoutEncounterGuard=binding,scoutEncounterGuardState=guard.snapshot(),
        acceptedInputActions=21,decisions=decisions,receipts=receipts,
        hybridNavigation=dict(routeId=SCOUT_GRASS_ROUTE,phase='failed',completedLegs=0,
            failure='survey_obstacle_requires_inspection',lastPose=frames[-1]['navigationPose']),
        hybridNavigationEvents=[dict(type='hybridStartVerified',routeId=SCOUT_GRASS_ROUTE,samples=start_samples)],
        stop=dict(type='stopped',receipts=[copy.deepcopy(receipts[-1])],executionContext=dict(active=None,telemetryComplete=True,
            sampledAtMs=2500.3,evictedEvents=0,firstSequence=1,lastSequence=len(calls),events=calls,lastInputEvent=copy.deepcopy(calls[-1]),
            physicalExecutionProven=False,trackedState=dict(heldKeys=[],telemetryIncomplete=False,releaseOutcome='returned_unverified'))))
    run['scoutEncounterGuardState']=guard.snapshot()
    write(part_path,part);write(folder/'patrol.json',run)
    write(folder/'patrol.json.control.json',dict(version=1,runId=run['runId'],command='run'))
    write(record/'recording.json',{key:value for key,value in recording.items() if key!='workerRetired'})
    for name,values in (('observations',frames),('frames',video),('events',events)):
        (record/(name+'.jsonl')).write_text(''.join(json.dumps(row)+'\n' for row in values),encoding='utf-8')
    size=sum(path.stat().st_size for path in record.iterdir() if path.name!='recording.json')
    run['recordedBytes']=recording['recordedBytes']=size
    write(part_path,part);write(folder/'patrol.json',run)
    write(record/'recording.json',{key:value for key,value in recording.items() if key!='workerRetired'})
    return folder,request,run,part,frames,events


class ObstaclePrefixTests(unittest.TestCase):
    """Reject incomplete or substituted evidence while preserving honest failed-route semantics."""
    def setUp(self):
        """Create fresh synthetic immutable artifacts for each mutation family."""
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.folder,self.request,self.run,self.part,self.frames,self.events=fixture(Path(self.temporary.name).resolve())

    def test_complete_failed_prefix_and_exact_stop_cancellation_remain_failed(self):
        """A valid retained policy is distinct from a verified route or physically proven input."""
        result=audit.audit_failed_prefix(self.folder,self.request)
        self.assertTrue(result['prefixVerified']);self.assertFalse(result['passed']);self.assertFalse(result['routeCompleted'])
        self.assertEqual((result['acceptedActions'],result['terminalReceipts'],len(result['rgbFiles'])),(21,21,25))
        self.assertGreaterEqual(result['confirmedForwardMs'],600)
        self.assertFalse(result['physicalInputDeliveryVerified'])

    def test_each_missing_late_changed_or_duplicate_terminal_is_rejected(self):
        """No late or uncertain accepted input can become eligible for model retention."""
        for name in ('missing','late','changed','duplicate','unresolved','stop_receipt'):
            part=copy.deepcopy(self.part);events=copy.deepcopy(self.events)
            if name=='missing':part['receipts'].pop()
            if name=='late':part['receipts'][0]['appliedSteps'][0]['startedAtMs']=550
            if name=='changed':part['receipts'][0]['appliedSteps'][0]['keys']=['LBUTTON']
            if name=='duplicate':part['receipts'].append(copy.deepcopy(part['receipts'][0]))
            if name=='unresolved':part['receipts'][0]['status']='expired'
            if name=='stop_receipt':part['stop']['receipts']=[]
            # Reseal the journal too: semantic input checks must reject self-consistent substitutions.
            events=[row for row in events if 'appliedSteps' not in row]+copy.deepcopy(part['receipts'])
            with self.subTest(name=name),self.assertRaises(ValueError):
                audit.input_contract(part,{row['frameId']:row for row in self.frames},events,route_points(SCOUT_GRASS_ROUTE))

    def test_open_dropped_thermal_goal_control_or_unknown_cleanup_never_qualifies(self):
        """Each independent terminal gate must remain closed even with the right error string."""
        changes=[('recording','complete',False),('recording','lossless',False),('recording','workerRetired',False),
            ('recording','droppedFrames',1),('recording','droppedEvents',1),('recording','droppedObservations',1),
            ('recording','abandonedFrames',1),('finalGoalState','controlEpoch',1),('finalGoalState','goalRequestId','changed')]
        for parent,key,value in changes:
            part=copy.deepcopy(self.part);part[parent][key]=value
            with self.subTest(parent=parent,key=key),self.assertRaises(ValueError):audit.terminal_contract(self.run,part)
        for key,value in (('stopError','timeout'),('unacknowledgedAction','unknown'),('streamError','reader alive'),
            ('error','seriesThermalStop'),('serverDroppedReceipts',1)):
            part=copy.deepcopy(self.part);part[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):audit.terminal_contract(self.run,part)

    def test_changed_rgb_native_source_or_guard_is_rejected_without_relabelling(self):
        """Original pixels and the still-armed failed guard remain independently replayed."""
        path=self.folder/'patrol-recording/00001/policy-00000000-frame-000000000001.rgb'
        path.write_bytes(b'x'*audit.RGB192_BYTES)
        with self.assertRaisesRegex(ValueError,'RGB bytes'):audit.audit_failed_prefix(self.folder,self.request)
        self.assertEqual(json.loads((self.folder/'patrol.json').read_bytes())['status'],'failed')

    def test_failure_label_without_stationary_receipt_backed_cause_is_rejected(self):
        """A known string alone is insufficient to qualify an unrelated failed prefix."""
        part=copy.deepcopy(self.part);part['decisions']=part['decisions'][-2:]
        with self.assertRaisesRegex(ValueError,'two continuous seconds'):
            audit.stationary_stop_contract(part,{row['frameId']:row for row in self.frames},route_points(SCOUT_GRASS_ROUTE))

    def test_fresh_successor_replays_the_original_prefix_and_rejects_stale_duplicate_or_changed_chain(self):
        """The independent successor gate reopens failed evidence and the new reviewed native sources."""
        prefix=audit.audit_failed_prefix(self.folder,self.request)
        audit_path=self.folder/'failed-prefix-audit.json';prefix_sha=write(audit_path,prefix)
        owner=self.run['policyReuse']['owner']
        evidence=shared.CachedPolicyAuditTests.reviewed_scene(self.folder.parent.parent/'successor',owner,
            SCOUT_GROVE_ROUTE,route_points(SCOUT_GROVE_ROUTE))
        review=json.loads(Path(evidence['reviewFile']).read_bytes())
        witness=dict(failedRequestId=self.request['requestId'],failedRunId=self.run['runId'],failedRouteId=self.request['routeId'],
            failedReviewSha256=self.request['reviewSha256'],failedManifestSha256=prefix['residentManifestSha256'],
            failedRoutePoints=[list(point) for point in route_points(SCOUT_GRASS_ROUTE)],
            prefixAuditFile=str(audit_path),prefixAuditSha256=prefix_sha,cleanupAtUnixNs=1,cleanupAtMonotonicNs=90_000_000,
            owner=owner,originalOwnerIdleMinimizedAfter=True,residentControlRetired=True,newPythonThreadsAlive=[],
            retainedState='policy-weights-and-immutable-configuration-only')
        request=dict(self.request,**evidence,requestId='f'*32,afterRequestId=self.request['requestId'],routeId=SCOUT_GROVE_ROUTE,
            obstacleRecovery=witness)
        request['scoutEncounterGuard']=binding_from_review(review,request['reviewSha256'])
        self.assertEqual(audit.verify_recovery_request(request,witness,owner)['failedRunId'],self.run['runId'])
        for name in ('missing_manifest_policy','missing_manifest_source','mismatched_policy','mismatched_source'):
            path=(self.folder.parent.parent/'manifest.json' if name.startswith('missing')
                  else Path(self.run['policyReuse']['sessionProof']))
            original=path.read_bytes();document=json.loads(original)
            if name=='missing_manifest_policy':document.pop('inspectedObstacleRecoveryPolicy')
            if name=='missing_manifest_source':document.pop('recoverySourceSha256')
            if name=='mismatched_policy':document['inspectedObstacleRecoveryPolicy']['maximumInspectedObstacleRecoveries']=2
            if name=='mismatched_source':document['recoverySourceSha256']['stream_client.py']='0'*64
            write(path,document)
            try:
                with self.subTest(name=name),self.assertRaisesRegex(ValueError,'Original worker did not authorize'):
                    audit.verify_recovery_request(request,witness,owner)
            finally:path.write_bytes(original)
        for name in ('duplicate','same_route','stale','wrong_predecessor','owner','missing_cleanup','proof'):
            changed=copy.deepcopy(request);expected=copy.deepcopy(witness)
            if name=='duplicate':changed['requestId']=self.request['requestId']
            if name=='same_route':changed['routeId']=self.request['routeId']
            if name=='stale':expected['cleanupAtMonotonicNs']=400_000_000
            if name=='wrong_predecessor':changed['afterRequestId']=None
            if name=='owner':expected['owner']['child']['processId']=99
            if name=='missing_cleanup':expected.pop('residentControlRetired')
            if name=='proof':expected['prefixAuditSha256']='0'*64
            changed['obstacleRecovery']=expected
            with self.subTest(name=name),self.assertRaises(ValueError):audit.verify_recovery_request(changed,expected,owner)
        original=self.folder/'patrol.json'
        document=json.loads(original.read_bytes());document['acceptedInputActions']+=1;write(original,document)
        with self.assertRaisesRegex(ValueError,'Original failed prefix changed'):
            audit.verify_recovery_request(request,witness,owner)

    def test_guard_dispatch_without_an_admission_and_receipt_is_unresolved(self):
        """A removed report field cannot hide a request that crossed the native dispatch boundary."""
        events=copy.deepcopy(self.events)
        extra=copy.deepcopy(next(row for row in events if row.get('type')=='scoutEncounterGuardDispatch'))
        extra['requestId']='unknown-native-outcome';events.append(extra)
        with self.assertRaisesRegex(ValueError,'uncertain admission'):
            audit.input_contract(self.part,{row['frameId']:row for row in self.frames},events,route_points(SCOUT_GRASS_ROUTE))

    def test_hidden_operator_or_goal_event_is_terminal_even_if_summary_is_clean(self):
        """Removing a summary field cannot hide an interruption retained in the original event journal."""
        for event in (dict(type='goalChange'),dict(type='controlTransition',reason='userPause')):
            with self.subTest(event=event),self.assertRaisesRegex(ValueError,'operator or goal interruption'):
                audit.input_contract(self.part,{row['frameId']:row for row in self.frames},self.events+[event],
                    route_points(SCOUT_GRASS_ROUTE))

    def test_changed_native_sensor_source_and_guard_state_are_rejected(self):
        """Pixels alone do not qualify an altered native intake or armed guard state."""
        path=self.folder/'patrol-segments/00001.json'
        changed=copy.deepcopy(self.part);changed['scoutEncounterGuardState']['armed']=False;write(path,changed)
        with self.assertRaisesRegex(ValueError,'guard state differs'):audit.audit_failed_prefix(self.folder,self.request)

    def test_native_release_failure_eviction_and_unknown_call_remain_terminal(self):
        """A reassuring tracked-state summary cannot override contradictory retained native calls."""
        for change in ('failed','missing_pair','evicted','unknown_dispatch'):
            part=copy.deepcopy(self.part);context=part['stop']['executionContext']
            if change=='failed':
                for event in (context['events'][-1],context['lastInputEvent']):
                    event['call'].update(stage='failed',error='retained release failure')
            if change=='missing_pair':context['events'].pop(-2)
            if change=='evicted':context['evictedEvents']=1
            if change=='unknown_dispatch':
                for event in context['events'][:2]:event['requestId']='unknown-input'
            with self.subTest(change=change),self.assertRaises(ValueError):
                audit.terminal_contract(self.run,part)
                audit.input_contract(part,{row['frameId']:row for row in self.frames},self.events,route_points(SCOUT_GRASS_ROUTE))

    def test_swapped_valid_rgb_references_cannot_reassign_original_source_pixels(self):
        """Both pixel hashes can be valid while their original frame/index assignments are wrong."""
        path=self.folder/'patrol-recording/00001/frames.jsonl'
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['policyRgb'],rows[1]['policyRgb']=rows[1]['policyRgb'],rows[0]['policyRgb']
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'policy RGB identity'):audit.audit_failed_prefix(self.folder,self.request)

    def test_native_dispatch_timing_cannot_hide_behind_an_earlier_fresh_receipt_start(self):
        """Native backend starts must be fresh and every call stays inside its exact applied interval."""
        part=copy.deepcopy(self.part);part['decisions']=part['decisions'][:1];part['receipts']=part['receipts'][:1]
        part['acceptedInputActions']=1;part['receipts'][0]['endedAtMs']=600
        identity=part['receipts'][0]['requestId'];part['stop']['receipts']=[]
        events=[copy.deepcopy(row) for row in self.events if
            row.get('type')=='proposal' and (row.get('acceptance') or {}).get('requestId')==identity
            or row.get('type')=='scoutEncounterGuardDispatch' and row.get('requestId')==identity]
        events.append(copy.deepcopy(part['receipts'][0]))
        context=part['stop']['executionContext']
        for index,event in enumerate(context['events'][2:]):event['atMs']=650+index*.1
        context['sampledAtMs']=651;context['lastInputEvent']=copy.deepcopy(context['events'][-1])
        frames={row['frameId']:row for row in self.frames}
        self.assertEqual(audit.input_contract(part,frames,events,route_points(SCOUT_GRASS_ROUTE))['acceptedActions'],1)
        for name,at in (('stale',551),('before_admission',419),('after_terminal',601)):
            changed=copy.deepcopy(part)
            for offset,event in enumerate(changed['stop']['executionContext']['events'][:2]):event['atMs']=at+offset*.1
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'Native call started stale'):
                audit.input_contract(changed,frames,events,route_points(SCOUT_GRASS_ROUTE))


if __name__=='__main__':unittest.main()
