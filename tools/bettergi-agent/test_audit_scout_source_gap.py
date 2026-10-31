"""Inert source-gap proof tests; the optional real regression never changes its retained evidence."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import audit_scout_source_gap as audit
from hybrid_routes import SCOUT_GRASS_ROUTE,route_points,route_heading
from navigation_profiles import SCOUT_PROFILE
from reviewed_scout_route import ReviewedScoutRoute


ROOT=Path(__file__).resolve().parents[2]
REAL=ROOT/'artifacts/live/2026-10-30-endurance/warm-scout-guarded-camp-20/session/legs/0d0e995b4f35436883508ab0322e141d'


def write(path, value):
    """Publish only a temporary test document and return the bytes actually written."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(value,sort_keys=True).encode();path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def terminal_fixture():
    """Provide a minimal closed boundary; it is not a full native-prefix qualification."""
    goal=dict(controlEpoch=0,policyGoalVersion=0,appliedGoalRequestId=None,goalRequestId=None,
        goalRequestStatus=None,goalError=None,goalIntent='ground-navigation')
    state=dict(state='tripped',armed=False,trip=dict(reason='nativeSensorStale',clientReceivedNs=300))
    calls=[]
    for index,stage in enumerate(('started','returned_unverified')):
        calls.append(dict(sequence=index+1,atMs=200+index*.1,origin='release:client_stop',
            call=dict(callId=1,operation='releaseAll',stage=stage,key=None,mouseDx=0,mouseDy=0,error=None)))
    context=dict(active=None,telemetryComplete=True,physicalExecutionProven=False,evictedEvents=0,
        firstSequence=1,lastSequence=2,events=calls,lastInputEvent=copy.deepcopy(calls[-1]),sampledAtMs=201,
        trackedState=dict(heldKeys=[],telemetryIncomplete=False,releaseOutcome='returned_unverified'))
    recording=dict(complete=True,lossless=True,closed=True,workerRetired=True,policyRgbEnabled=True,error=None,
        droppedFrames=0,droppedEvents=0,droppedObservations=0,abandonedFrames=0,
        encodedFrames=2,policyRgbFrames=2,recordedObservations=2,policyRgbBytes=2*audit.RGB192_BYTES)
    run=dict(goal,status='failed',error=audit.STALE_ERROR,endReason='error',evidenceComplete=False,
        failedLeases=1,connectionErrors=[],recordingBudgetExhausted=False,actionHoldMs=50,
        historyCommitMode=audit.HISTORY_MODE,goalChanges=[],scoutEncounterGuardState=copy.deepcopy(state))
    part=dict(status='failed',error=audit.STALE_ERROR,streamError=audit.STALE_ERROR,endReason='scoutEncounterGuard',
        scoutEncounterGuardTriggerRecorded=True,episodeFailure=dict(type='ScoutEncounterStop',transportOperation=None),
        unappliedAcceptedActions=0,serverDroppedReceipts=0,actionHoldMs=50,historyCommitMode=audit.HISTORY_MODE,
        maxObservationAgeMs=150,decisionHz=10,capturePollHz=20,inputRequested=True,nativeInputEnabled=True,
        effectiveInputKeys=['W','A','S','D'],navigationIdleRecovery=dict(enabled=False),controlTransitions=[],goalChanges=[],
        initialGoalState=copy.deepcopy(goal),finalGoalState=copy.deepcopy(goal),leaseInitialGoalState=copy.deepcopy(goal),
        segment=dict(number=1,leaseEnded=True,startedAtClientNs=1,endedAtClientNs=1_000_000_001),
        continuity=dict(previousReport=None,sameBridgeLease=False,pendingProposals=[],pendingRecoveryActions=[],sourceFrames=[]),
        recording=recording,framesReceived=2,stop=dict(type='stopped',executionContext=context,receipts=[]),
        scoutEncounterGuardState=state)
    return run,part


def input_fixture(hold=50):
    """Construct one receipt-backed native W selection without a game or retained recording."""
    _,part=terminal_fixture();points=route_points(SCOUT_GRASS_ROUTE);identity='c'*32
    source=dict(captureEpoch='source',timestamp100ns=1000000,capturedAtMs=100,acquiredAtMs=100,
        freshnessAtMs=100,freshnessClockKind='reported_compositor_qpc')
    pose=dict(state='valid',frameId=1,x=points[0][0],y=points[0][1],layerId='MapBack_2',
        yawDegrees=route_heading(dict(x=points[0][0],y=points[0][1]),points[1]),positionConfidence=.999,yawConfidence=.8)
    frame=dict(frameId=1,sourceFrame=source,navigationPose=pose,combatEvidence=None,
        frameWorldReadiness=dict(ready=True,epoch=1,sourceFrameId=1,sourceFrame=source),
        motionEvidence=dict(status='normal',spaceKeyMatched=False))
    step=dict(keys=['W'],mouseDx=0,mouseDy=0,durationMs=hold)
    decision=dict(frameId=1,controlEpoch=0,policyGoalVersion=0,appliedGoalRequestId=None,goalIntent='ground-navigation',
        acceptance=dict(type='accepted',requestId=identity,acceptedAtMs=120),steps=[step],startBeforeMs=250,
        nativeCombatEvidence=None,hybridNavigation=dict(pose=pose,step=step,target='end',completedLegs=0,
            reason='modelRouteCompatible',owner='open-p2p'))
    receipt=dict(requestId=identity,frameId=1,modelId='open-p2p',acceptedAtMs=120,endedAtMs=125+hold,
        status='completed',reason='horizon_complete',appliedSteps=[dict(index=0,startedAtMs=121,keys=['W'],mouseDx=0,mouseDy=0)])
    calls=[]
    for number,operation,origin,at in ((1,'keyDown','dispatch',121.1),
        (2,'releaseAll','release:horizon_complete',125.1+hold),(3,'releaseAll','release:client_stop',200)):
        for offset,stage in enumerate(('started','returned' if number==1 else 'returned_unverified')):
            calls.append(dict(sequence=len(calls)+1,atMs=at+offset*.1,requestId=identity if number<3 else None,
                frameId=1 if number<3 else None,modelId='open-p2p' if number<3 else None,stepIndex=0 if number<3 else None,
                origin=origin,call=dict(callId=number,operation=operation,stage=stage,key='W' if number==1 else None,
                    mouseDx=0,mouseDy=0,error=None)))
    part.update(actionHoldMs=hold,acceptedInputActions=1,decisions=[decision],receipts=[receipt])
    part['stop']['executionContext'].update(events=calls,lastSequence=len(calls),lastInputEvent=copy.deepcopy(calls[-1]))
    events=[dict(type='scoutEncounterGuardDispatch',requestId=identity,marker=dict(clientDispatchNs=200))]
    return part,{1:frame},events,points


class SourceGapBoundaryTests(unittest.TestCase):
    """Reject independent terminal errors before reading a recording or considering a successor."""
    def test_closed_boundary_keeps_failure_and_default_policy_is_one_shot(self):
        """Software cleanup permits examination only, not completion or automatic replay."""
        run,part=terminal_fixture();audit.terminal_contract(run,part)
        self.assertEqual(run['status'],'failed');self.assertFalse(run['evidenceComplete'])
        policy=audit.recovery_policy();self.assertEqual(policy['maximumInspectedSourceGapRecoveries'],1)
        self.assertFalse(policy['automaticRequests']);self.assertEqual(len(audit.SOURCE_NAMES),30)

    def test_terminal_errors_drops_pending_inputs_and_controls_refuse(self):
        """The right first error cannot hide lossy evidence, pending input or a separate stop."""
        changes=[('recording',key,False) for key in ('complete','lossless','closed','workerRetired')]
        changes += [('recording',key,1) for key in ('droppedFrames','droppedEvents','droppedObservations','abandonedFrames')]
        changes += [('finalGoalState','controlEpoch',1),('finalGoalState','goalRequestId','changed'),
            ('finalGoalState','policyGoalVersion',1),('continuity','pendingProposals',[{}]),
            ('segment','endedAtClientNs',35_000_000_002)]
        for parent,key,value in changes:
            run,part=terminal_fixture();part[parent][key]=value
            with self.subTest(parent=parent,key=key),self.assertRaises(ValueError):audit.terminal_contract(run,part)
        for key,value in (('error','seriesThermalStop'),('stopError','timeout'),('unacknowledgedAction',{}),
            ('unacknowledgedAction','unknown'),('serverDroppedReceipts',1),('unappliedAcceptedActions',1),
            ('controlTransitions',[dict(reason='userStop')]),('actionHoldMs',100),('historyCommitMode','predicted'),
            ('streamError','reader failed'),('navigationClimbActions',[{}]),('serverDroppedReceipts',False)):
            run,part=terminal_fixture();part[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):audit.terminal_contract(run,part)

    def test_stop_journal_cannot_hide_failure_eviction_or_a_held_key(self):
        """The final native software call must agree with its tracked release summary."""
        for change in ('held','active','failed','missing','evicted','trip','armed'):
            run,part=terminal_fixture();context=part['stop']['executionContext']
            if change=='held':context['trackedState']['heldKeys']=['W']
            if change=='active':context['active']={'requestId':'unknown'}
            if change=='failed':context['events'][-1]['call']['stage']='failed'
            if change=='missing':context['events'].pop(0)
            if change=='evicted':context['evictedEvents']=1
            if change=='trip':part['scoutEncounterGuardState']['trip']['reason']='enemyBarCandidate'
            if change=='armed':part['scoutEncounterGuardState']['armed']=True
            with self.subTest(change=change),self.assertRaises(ValueError):audit.terminal_contract(run,part)

    def test_50_and_60_ms_inputs_require_exact_native_completion_and_release(self):
        """The public input proof covers both allowed holds independently of optional live artifacts."""
        for hold in (50,60):
            part,frames,events,points=input_fixture(hold)
            result=audit.input_contract(part,frames,events,points,SCOUT_PROFILE)
            self.assertEqual((result['acceptedActions'],result['terminalReceipts']),(1,1))
            audit.native_stop_contract(part['stop']['executionContext'])

    def test_pure_receipt_native_dispatch_and_release_mutations_refuse(self):
        """Cancelled/replaced inputs and missing or late native calls never become completed history."""
        for change in ('missing','replaced','cancelled','attack','dispatch','release','stale','before','after'):
            part,frames,events,points=input_fixture()
            if change=='missing':part['receipts']=[]
            if change in ('replaced','cancelled'):part['receipts'][0]['status']=change
            if change=='attack':part['receipts'][0]['appliedSteps'][0]['keys']=['LBUTTON']
            if change=='dispatch':part['stop']['executionContext']['events']=part['stop']['executionContext']['events'][2:]
            if change=='release':part['stop']['executionContext']['events']=[e for e in part['stop']['executionContext']['events'] if e['origin']!='release:horizon_complete']
            if change in ('stale','before','after'):
                at={'stale':251,'before':119,'after':176}[change]
                for offset,event in enumerate(part['stop']['executionContext']['events'][:2]):event['atMs']=at+offset*.1
            with self.subTest(change=change),self.assertRaises(ValueError):
                audit.input_contract(part,frames,events,points,SCOUT_PROFILE)


class SourceGapSuccessorTests(unittest.TestCase):
    """Exercise source-bound opt-in and cleanup freshness separately from the full prefix replay."""
    def setUp(self):
        """Build a temporary proof chain; expensive prefix/native-image replay are isolated seams."""
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name).resolve()
        self.failed_id='a'*32;self.folder=root/'session/legs'/self.failed_id
        self.owner=dict(root=dict(processId=1,windowsSessionId=1,instanceNonce='root'),
            child=dict(processId=2,windowsSessionId=3,instanceNonce='child'))
        self.spec=ReviewedScoutRoute.from_document(dict(version=1,profileId='mondstadt-combat-scout-v1',
            points=[[-1137.392578125,2196.7666015625],[-1138.5,2197.5]]))
        self.old=dict(sessionId='s'*32,requestId=self.failed_id,routeId=self.spec.route_id,routeSpec=self.spec.document(),
            reviewSha256='old-review',navigationProfile=self.spec.profile_id,modelConfigurationSha256='model',
            historyCommitMode=audit.HISTORY_MODE,actionHoldMs=50)
        request_file=root/'old-request.json';write(request_file,self.old)
        self.proof_path=root/'session/policy-proof.json';self.manifest_path=root/'session/manifest.json'
        failed=dict(policyReuse=dict(requestFile=str(request_file),sessionProof=str(self.proof_path)))
        manifest_sha=write(self.folder/'patrol.json',failed)
        self.prefix=dict(prefixVerified=True,passed=False,routeCompleted=False,failureReason=audit.STALE_ERROR,
            runId='run',requestId=self.failed_id,residentManifestSha256=manifest_sha)
        audit_path=self.folder/'failed-source-gap-audit.json';audit_sha=write(audit_path,self.prefix)
        pins={}
        for name in audit.SOURCE_NAMES:
            raw=name.encode();p=root/'source-snapshot'/name;p.parent.mkdir(exist_ok=True);p.write_bytes(raw)
            pins[name]=hashlib.sha256(raw).hexdigest()
        self.manifest=dict(sessionId=self.old['sessionId'],owner=self.owner,modelConfigurationSha256='model',
            navigationProfile=self.spec.profile_id,historyCommitMode=audit.HISTORY_MODE,actionHoldMs=50,
            inspectedSourceGapRecoveryPolicy=audit.recovery_policy(),sourceGapRecoverySourceSha256=pins)
        write(self.manifest_path,self.manifest);write(self.proof_path,self.manifest)
        endpoint=root/'new-scene';endpoint.mkdir();source=dict(timestamp100ns=2000,capturedAtMs=2,freshnessAtMs=2)
        write(endpoint/'result.json',dict(stableSamples=[dict(sourceFrame=source) for _ in range(3)]))
        write(endpoint/'image.json',dict(sourceFrame=source));write(endpoint/'plan.json',{})
        (endpoint/'image.png').write_bytes(b'inert');review_file=root/'review.json';write(review_file,{})
        self.review=dict(nativeEndpoint=str(endpoint),imageName='image.png')
        self.witness=dict(failedRequestId=self.failed_id,failedRunId='run',failedRouteId=self.old['routeId'],
            failedReviewSha256='old-review',failedManifestSha256=manifest_sha,
            failedRoutePoints=[list(p) for p in self.spec.points],prefixAuditFile=str(audit_path),prefixAuditSha256=audit_sha,
            cleanupAtUnixNs=1,cleanupAtMonotonicNs=100000,owner=self.owner,originalOwnerIdleMinimizedAfter=True,
            residentControlRetired=True,newPythonThreadsAlive=[],historyReset=True,failureReason=audit.STALE_ERROR,
            retainedState='policy-weights-and-immutable-configuration-only')
        self.request=dict(self.old,requestId='b'*32,afterRequestId=self.failed_id,reviewSha256='new-review',
            reviewFile=str(review_file),sourceGapRecovery=self.witness)

    def verify(self, request=None, witness=None):
        """Keep native admission/prefix implementations unmodified while isolating this witness contract."""
        with mock.patch.object(audit,'verify_scout_review',return_value=self.review), \
             mock.patch.object(audit,'audit_failed_prefix',return_value=self.prefix):
            return audit.verify_recovery_request(request or self.request,witness or self.witness,self.owner)

    def test_fresh_same_geometry_is_allowed_only_after_explicit_new_review(self):
        """A changed review, consumed request and post-cleanup source are required even for the same route."""
        self.assertEqual(self.verify()['freshReviewSha256'],'new-review')
        changed=copy.deepcopy(self.request);changed['reviewSha256']='old-review'
        with self.assertRaisesRegex(ValueError,'old review'):self.verify(changed)

    def test_missing_mismatched_or_stripped_opt_in_never_grants_authority(self):
        """A verified historical prefix alone cannot add recovery rights retroactively."""
        for field in ('inspectedSourceGapRecoveryPolicy','sourceGapRecoverySourceSha256'):
            changed=copy.deepcopy(self.manifest);changed.pop(field);write(self.manifest_path,changed)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'did not authorize'):self.verify()
            write(self.manifest_path,self.manifest)
        changed=copy.deepcopy(self.manifest);changed['inspectedSourceGapRecoveryPolicy']['maximumInspectedSourceGapRecoveries']=2
        write(self.proof_path,changed)
        with self.assertRaisesRegex(ValueError,'did not authorize'):self.verify()

    def test_cleanup_owner_source_clock_and_one_shot_mutations_refuse(self):
        """Neither a compositor lead nor a duplicated request may masquerade as post-cleanup work."""
        for change in ('duplicate','chain','threads','reset','owner','stale','reason','proof'):
            req=copy.deepcopy(self.request);w=req['sourceGapRecovery']
            if change=='duplicate':req['requestId']=self.failed_id
            if change=='chain':req['afterRequestId']=None
            if change=='threads':w['newPythonThreadsAlive']=['capture']
            if change=='reset':w['historyReset']=False
            if change=='owner':w['owner']['child']['processId']=99
            if change=='stale':w['cleanupAtMonotonicNs']=200001
            if change=='reason':w['failureReason']='other'
            if change=='proof':w['prefixAuditSha256']='bad'
            with self.subTest(change=change),self.assertRaises(ValueError):self.verify(req,w)
        endpoint=Path(self.review['nativeEndpoint']);source=dict(timestamp100ns=2000,capturedAtMs=2,freshnessAtMs=1.8)
        write(endpoint/'image.json',dict(sourceFrame=source))
        with self.assertRaisesRegex(ValueError,'predates completed cleanup'):self.verify()

    def test_second_recovery_and_changed_original_source_refuse(self):
        """A successor failure cannot recursively reopen the same allowance or substitute code."""
        old_path=Path(json.loads((self.folder/'patrol.json').read_bytes())['policyReuse']['requestFile'])
        changed=dict(self.old,sourceGapRecovery={});write(old_path,changed)
        with self.assertRaisesRegex(ValueError,'Second or recursive'):self.verify()
        write(old_path,self.old)
        archive=self.manifest_path.parent.parent/'source-snapshot/scout_session.py';archive.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'source archive changed'):self.verify()


@unittest.skipUnless((REAL/'patrol.json').is_file(),'Optional retained worker20 regression is not in this checkout')
class RealSourceGapRegressionTests(unittest.TestCase):
    """Read the immutable live failure once, then test adverse in-memory copies of its evidence."""
    @classmethod
    def setUpClass(cls):
        """Load only the named failed leg, with no process, model or native pipe access."""
        cls.resident=json.loads((REAL/'patrol.json').read_bytes());cls.part=json.loads((REAL/'patrol-segments/00001.json').read_bytes())
        cls.request=json.loads(Path(cls.resident['policyReuse']['requestFile']).read_bytes())
        cls.observed,_=audit.read_recording_jsonl(REAL/'patrol-recording/00001','observations.jsonl')
        cls.video,_=audit.read_recording_jsonl(REAL/'patrol-recording/00001','frames.jsonl')
        cls.events,_=audit.read_recording_jsonl(REAL/'patrol-recording/00001','events.jsonl');cls.frames={}
        for frame in cls.observed:cls.frames.setdefault(frame['frameId'],frame)
        cls.spec=ReviewedScoutRoute.from_document(cls.request['routeSpec'])

    def test_full_original_failed_prefix_replays_without_inventing_recovery_authority(self):
        """The real lossless failure is eligible evidence, while its historical session had no opt-in."""
        before=(REAL/'patrol.json').read_bytes();result=audit.audit_failed_prefix(REAL,self.request)
        self.assertTrue(result['prefixVerified']);self.assertFalse(result['passed']);self.assertFalse(result['routeCompleted'])
        self.assertEqual((result['acceptedActions'],result['terminalReceipts'],len(result['rgbFiles'])),(51,51,168))
        self.assertEqual(result['groundCropsReplayed'],334);self.assertEqual(result['history']['finalValidHistoryFrames'],41)
        self.assertEqual((REAL/'patrol.json').read_bytes(),before)
        manifest=json.loads((REAL.parent.parent/'manifest.json').read_bytes())
        self.assertNotIn('inspectedSourceGapRecoveryPolicy',manifest)

    def test_missing_late_replaced_or_unmatched_native_calls_refuse(self):
        """Fresh receipt summaries cannot hide late backend calls or incomplete action settlement."""
        for change in ('missing','replaced','late','pre_admission','after_terminal','duplicate','unknown','release_missing'):
            part=copy.deepcopy(self.part);events=copy.deepcopy(self.events)
            if change=='missing':part['receipts'].pop()
            if change=='replaced':part['receipts'][-1]['status']='replaced'
            if change=='duplicate':part['receipts'].append(copy.deepcopy(part['receipts'][0]))
            if change=='unknown':part['stop']['executionContext']['events'][0]['requestId']='unknown'
            if change=='release_missing':
                part['stop']['executionContext']['events']=[e for e in part['stop']['executionContext']['events']
                    if not (e['origin']=='release:horizon_complete' and e['requestId']==part['receipts'][0]['requestId'])]
            if change in ('late','pre_admission','after_terminal'):
                first=part['receipts'][0];frame=self.frames[first['frameId']]
                at=(frame['sourceFrame']['freshnessAtMs']+151 if change=='late' else
                    first['acceptedAtMs']-1 if change=='pre_admission' else first['endedAtMs']+1)
                for offset,event in enumerate(part['stop']['executionContext']['events'][:2]):event['atMs']=at+offset*.1
            with self.subTest(change=change),self.assertRaises(ValueError):
                audit.input_contract(part,self.frames,events,self.spec.points,self.request['navigationProfile'])

    def test_real_frozen_goal_pending_threads_and_other_stop_reasons_refuse(self):
        """The known stale case does not excuse another error added to its original terminal report."""
        for change in ('goal','recorder','pending','thermal','control','guard'):
            part=copy.deepcopy(self.part)
            if change=='goal':part['finalGoalState']['goalRequestId']='late-goal'
            if change=='recorder':part['recording']['workerRetired']=False
            if change=='pending':part['continuity']['pendingProposals']=[{}]
            if change=='thermal':part['error']='seriesThermalStop'
            if change=='control':part['controlTransitions']=[dict(reason='userStop')]
            if change=='guard':part['scoutEncounterGuardState']['trip']['reason']='enemyBarCandidate'
            with self.subTest(change=change),self.assertRaises(ValueError):audit.terminal_contract(self.resident,part)

    def test_exact_duplicate_trigger_and_adverse_source_health_ground_readiness(self):
        """Replay two real trigger images while isolating the already-tested RGB file reader."""
        frames=copy.deepcopy(self.observed[-2:]);video=copy.deepcopy(self.video[-2:]);part=copy.deepcopy(self.part)
        part['framesReceived']=2
        for index,row in enumerate(video):row['videoFrameIndex']=index
        raw=(REAL/'patrol-recording/00001'/video[0]['policyRgb']['file']).read_bytes()
        def replay(observations, changed_part=None):
            """Keep complete inline crop replay; only immutable RGB file retrieval is substituted."""
            rows=[]
            for frame,original in zip(observations,video):
                rows.append(dict({k:v for k,v in frame.items() if k!='videoQueueAccepted'},
                    **{k:v for k,v in original.items() if k in ('policyRgb','videoFrameIndex','videoPtsSeconds')}))
            with mock.patch.object(audit,'read_policy_rgb',return_value=raw):
                return audit.frame_contract(observations,rows,self.events,changed_part or part,REAL/'patrol-recording/00001')
        self.assertEqual(replay(frames)[2],4)
        for change in ('epoch','health','enemy','crop','readiness','not_stale','duplicate_source'):
            changed=copy.deepcopy(frames)
            if change=='epoch':changed[-1]['sourceFrame']['captureEpoch']='different'
            if change=='health':changed[0]['combatEvidence']['playerHealthFractionEstimate']=.99
            if change=='enemy':changed[0]['combatEvidence']['enemyBarCandidates']=[dict(x=1)]
            if change=='crop':changed[0]['groundControlEvidence']['crops'][0]['rgbBase64']='AA=='
            if change=='readiness':changed[-1]['worldReadiness']['reason']='capture_unavailable'
            if change=='not_stale':changed[-1]['sourceFrameAgeMs']=150
            if change=='duplicate_source':changed[-1]['navigationPose']['x']+=1
            with self.subTest(change=change),self.assertRaises(ValueError):replay(changed)
        compressed=copy.deepcopy(part);compressed['recording'].update(recordingFormat=audit.RECORDING_FORMAT,
            policyRgbStoredBytes=2*audit.RGB192_BYTES+1)
        with self.assertRaisesRegex(ValueError,'stored RGB aggregate'):replay(frames,compressed)


if __name__=='__main__':unittest.main()
