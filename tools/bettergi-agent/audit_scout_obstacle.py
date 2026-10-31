"""Independently validate a closed failed scout prefix; never certify route completion."""
import hashlib
import json
import math
from pathlib import Path
import stat

from audit_hybrid_run import (evidence_bytes, evidence_document, require, verify_policy_reuse,
                             verify_scout_goal_state, verify_scout_guard, verify_scout_review)
from hybrid_routes import camera_correction, route_heading, route_points
from navigation_profiles import SCOUT_PROFILE, SCOUT_PROFILES, allows_pose_scope, validate_capability
from observation_timing import observation_timestamp
from policy_rgb_archive import RGB192_BYTES
from reviewed_scout_route import ReviewedScoutRoute


OBSTACLE_ERROR = 'hybrid_navigation:survey_obstacle_requires_inspection'
SOURCE_FILES = ('scout_session.py', 'audit_scout_obstacle.py', 'audit_hybrid_run.py',
    'resident_runtime.py', 'stream_client.py', 'scout_encounter_guard.py', 'hybrid_navigation.py',
    'reviewed_scout_route.py', 'run_patrol_series.py', 'run_rdp_patrol.py', 'bridge_transport.py',
    'policy_rgb_archive.py', 'episode_split.py', 'observation_timing.py', 'model_adapters.py',
    'native_combat.py', 'navigation_profiles.py', 'p2p_startup.py', 'p2p_temporal_cache.py')


def recovery_policy():
    """Declare the sole opt-in failure and finite inspection allowance without input authority."""
    return dict(version=1, maximumInspectedObstacleRecoveries=1, error=OBSTACLE_ERROR,
        retain='policy-weights-and-immutable-configuration-only', automaticRequests=False,
        failedLegRemainsFailed=True, requireFreshGuard=True, requirePostCleanupReview=True)


def source_contract():
    """Pin the bounded Python paths that establish this optional failed-prefix/cleanup contract."""
    root=Path(__file__).absolute().parent
    return {name:hashlib.sha256(evidence_bytes(root/name,2*1024*1024)).hexdigest() for name in SOURCE_FILES}


def rows(path):
    """Read one bounded, unlinked journal and retain its exact byte digest."""
    raw=evidence_bytes(path,32*1024*1024)
    result=[json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    require(result and all(isinstance(row,dict) for row in result),'Missing or invalid original journal')
    return result,hashlib.sha256(raw).hexdigest()


def terminal_contract(run, part):
    """Accept only the original geometric failure with acknowledged stop and closed, lossless evidence."""
    require(run.get('status')==part.get('status')=='failed' and run.get('error')==part.get('error')==OBSTACLE_ERROR
        and run.get('endReason')==part.get('endReason')=='error' and run.get('evidenceComplete') is False
        and run.get('failedLeases')==1 and run.get('connectionErrors')==[]
        and run.get('recordingBudgetExhausted') is False,'Not the single closed geometric failure')
    forbidden=('unacknowledgedAction','unacknowledgedRecoveryAction','streamError','stopError','captureError',
        'recordingFinalizationError','navigationClimbHandleCloseError','executionContextFinalError','evidenceError',
        'scoutEncounterGuardRelease','scoutEncounterGuardError','combatTrialReleaseError')
    require(not any(value.get(key) for value in (run,part) for key in forbidden),'Additional failure or uncertain input outcome')
    require(part.get('episodeFailure')==dict(type='RuntimeError',transportOperation=None)
        and part.get('unappliedAcceptedActions')==0 and part.get('serverDroppedReceipts')==0,
        'Failed prefix contains a transport, unapplied-action or missing-receipt outcome')
    require(part.get('inputRequested') is True and part.get('nativeInputEnabled') is True
        and part.get('actionHoldMs')==100 and part.get('maxObservationAgeMs')==150
        and part.get('decisionHz')==10 and part.get('capturePollHz')==20
        and set(part.get('effectiveInputKeys',[]))=={'W','A','S','D'},'Scout action limits changed')
    require(part.get('navigationClimbActions')==[],'First inspected recovery experiment excludes climb-drop inputs')
    require((part.get('navigationIdleRecovery') or {}).get('enabled') is False
        and not part.get('navigationIdleRecoveryEvents'),'Idle recovery changed the failed prefix')
    for value,label in ((run,'summary'),(part.get('initialGoalState'),'initial'),
        (part.get('finalGoalState'),'final'),(part.get('leaseInitialGoalState'),'lease initial')):
        verify_scout_goal_state(value,label)
        require(value['controlEpoch']==0,'Pause or operator control changed the failed prefix')
    require(part.get('goalChanges')==[],'Failed prefix contains a goal request')
    segment=part.get('segment') or {}
    require(segment.get('number')==1 and segment.get('leaseEnded') is True
        and type(segment.get('startedAtClientNs')) is int and type(segment.get('endedAtClientNs')) is int
        and 0<segment['endedAtClientNs']-segment['startedAtClientNs']<=35_000_000_000,
        'Failed scout exceeded one closed 35-second lease')
    continuity=part.get('continuity') or {}
    require(continuity.get('previousReport') is None and continuity.get('sameBridgeLease') is False
        and all(continuity.get(key)==[] for key in ('pendingProposals','pendingRecoveryActions','sourceFrames')),
        'Failed scout retained pending work or another segment')
    recording=part.get('recording') or {}
    require(all(recording.get(key) is True for key in ('complete','lossless','closed','workerRetired','policyRgbEnabled'))
        and recording.get('error') is None
        and all(type(recording.get(key)) is int and recording[key]==0 for key in
            ('droppedFrames','droppedEvents','droppedObservations','abandonedFrames')),
        'Recorder is open, lossy, failed or still running')
    count=part.get('framesReceived')
    require(type(count) is int and count>0 and recording.get('encodedFrames')==recording.get('policyRgbFrames')==count
        and recording.get('recordedObservations')==count and recording.get('policyRgbBytes')==count*RGB192_BYTES,
        'Failed prefix recording/frame counters disagree')
    stop=part.get('stop') or {}
    context=stop.get('executionContext') or {}
    tracked=context.get('trackedState') or {}
    require(stop.get('type')=='stopped' and context.get('active') is None and context.get('telemetryComplete') is True
        and tracked.get('heldKeys')==[] and tracked.get('telemetryIncomplete') is False
        and tracked.get('releaseOutcome')=='returned_unverified','Original stop/release acknowledgement is unresolved')
    # The native release reports software return only. Never turn it into physical-input proof.
    require(context.get('physicalExecutionProven') is False,'Unexpected physical-input assertion')
    native_stop_contract(context)


def native_stop_contract(context):
    """Require a complete native call journal ending in the exact acknowledged software release."""
    events=context.get('events')
    require(isinstance(events,list) and len(events)>=2 and context.get('evictedEvents')==0
        and context.get('firstSequence')==1 and context.get('lastSequence')==len(events)
        and [event.get('sequence') for event in events]==list(range(1,len(events)+1))
        and context.get('lastInputEvent')==events[-1],'Native stop call journal is missing, evicted or contradictory')
    pending={};closed=set();previous=-1
    for event in events:
        call=event.get('call') or {};identity=call.get('callId');at=event.get('atMs')
        require(type(identity) is int and identity>0 and type(at) in (int,float) and math.isfinite(at)
            and previous<=at<=context.get('sampledAtMs',-1) and call.get('error') is None
            and call.get('operation') in ('releaseAll','keyDown','keyUp','mouseMove'),
            'Native stop contains a failed, unknown or out-of-order call')
        previous=at
        if call.get('stage')=='started':
            require(identity not in pending and identity not in closed,'Duplicate native call start')
            pending[identity]=event
        else:
            started=pending.pop(identity,None)
            require(started is not None and call.get('stage')==('returned_unverified' if call['operation']=='releaseAll' else 'returned')
                and all(value==event.get(key) for key,value in started.items() if key not in ('sequence','atMs','call'))
                and {key:value for key,value in started['call'].items() if key!='stage'}==
                    {key:value for key,value in call.items() if key!='stage'},
                'Native call lacks its exact successful software-return pair')
            closed.add(identity)
    require(not pending,'Native stop leaves an unresolved call')
    first,last=events[-2:]
    require(first.get('origin')==last.get('origin')=='release:client_stop'
        and first['call'].get('stage')=='started' and last['call'].get('stage')=='returned_unverified'
        and first['call'].get('callId')==last['call'].get('callId')
        and first['call'].get('operation')==last['call'].get('operation')=='releaseAll',
        'Native stop lacks its final owned release pair')


def input_contract(part, frames, events, points, profile=SCOUT_PROFILE):
    """Join every proposal/admission/terminal receipt and independently verify the native selection."""
    decisions=part.get('decisions') or []
    for event in events:
        require(event.get('type') not in ('goalChanged','goalChange','goalApplied','goalRequest')
            and not (event.get('type')=='controlTransition' and event.get('reason') in
                ('userPause','userStop','controlError','goalChange','goalChangeFailed')),
            'Retained journal contains an operator or goal interruption')
        if event.get('type')=='episodeStart':
            verify_scout_goal_state(event.get('goalState'),'original episode start')
    proposals=[row for row in events if row.get('type')=='proposal']
    terminals=[row for row in events if 'appliedSteps' in row and 'requestId' in row]
    receipts=part.get('receipts') or []
    require(decisions and len(decisions)==len(proposals) and terminals==receipts,
        'Original proposal/terminal journal does not match the failed report')
    accepted={}
    joins=('frameId','steps','acceptance','hybridNavigation','observationTimestampMs','startBeforeMs',
        'controlEpoch','policyGoalVersion','appliedGoalRequestId','goalIntent','rawPolicySteps')
    for decision,proposal in zip(decisions,proposals):
        require(all(decision.get(key)==proposal.get(key) for key in joins),'Failed-prefix proposal changed')
        verify_scout_goal_state(decision,'failed decision',decision=True)
        require(decision['controlEpoch']==0,'Failed decision crossed operator control')
        ack=decision.get('acceptance') or {}
        if ack.get('type')!='accepted':
            require(ack.get('type')=='notSubmitted' and ack.get('reason')=='observationTooOld'
                and decision.get('historyCommitted') is False,'Unresolved or rejected scout proposal')
            continue
        identity=ack.get('requestId')
        require(isinstance(identity,str) and identity not in accepted,'Duplicate accepted scout input')
        accepted[identity]=decision
        frame=frames.get(decision.get('frameId')) or {}
        pose,gate=frame.get('navigationPose') or {},frame.get('frameWorldReadiness') or {}
        h=decision.get('hybridNavigation') or {}
        require(h.get('pose')==pose and pose.get('state')=='valid' and pose.get('frameId')==frame.get('frameId')
            and allows_pose_scope(pose,profile) and .99<=pose.get('positionConfidence',0)<=1
            and .2<=pose.get('yawConfidence',0)<=1 and gate.get('ready') is True
            and gate.get('sourceFrameId')==frame['frameId'] and gate.get('sourceFrame')==frame.get('sourceFrame')
            and (frame.get('motionEvidence') or {}).get('status')=='normal'
            and (frame.get('motionEvidence') or {}).get('spaceKeyMatched') is False,
            'Accepted input lacks its qualified original native pose')
        require(decision.get('nativeCombatEvidence')==frame.get('combatEvidence'),'Native combat/source decision join changed')
        at=observation_timestamp(frame)
        require(decision.get('observationTimestampMs')==at and decision.get('startBeforeMs')==at+150
            and 0<=decision.get('estimatedObservationAgeMs',999)<=150,'Accepted input source deadline changed')
        heading=route_heading(pose,points[1])
        error=abs((heading-pose['yawDegrees']+180)%360-180)
        reason=h.get('reason')
        step=h.get('step') or {}
        require(h.get('target')=='end' and h.get('completedLegs')==0 and decision.get('steps')==[step]
            and step.get('durationMs')==100 and step.get('mouseDy')==0,'Scout selection changed its target or 100-ms hold')
        if reason=='nativeHeading':
            require(error>5 and h.get('owner')=='hybrid-native' and step.get('keys')==[]
                and step.get('mouseDx')==max(-350,min(350,int(camera_correction(pose['yawDegrees'],heading)))),
                'Native heading selection differs from independent route geometry')
        else:
            require(error<=5 and step.get('keys')==['W'] and abs(step.get('mouseDx',999))<=3
                and (reason,h.get('owner')) in (('modelIdleOrOffRoute','hybrid-native'),('modelRouteCompatible','open-p2p')),
                'Forward selection differs from the reviewed route')
    by_id={receipt.get('requestId'):receipt for receipt in receipts}
    require(len(by_id)==len(receipts)==len(accepted)==part.get('acceptedInputActions') and set(by_id)==set(accepted),
        'Accepted input lacks exactly one terminal receipt')
    require(all(before['acceptedAtMs']<after['acceptedAtMs'] and before['endedAtMs']<=after['acceptedAtMs']
        for before,after in zip(receipts,receipts[1:])),'Native action intervals overlap or admission order changed')
    dispatches=[event.get('requestId') for event in events if event.get('type')=='scoutEncounterGuardDispatch']
    require(len(dispatches)==len(set(dispatches))==len(accepted) and set(dispatches)==set(accepted),
            'Guarded dispatch has missing or uncertain admission/terminal evidence')
    ages=[]
    for identity,decision in accepted.items():
        receipt=by_id[identity];ack=decision['acceptance'];step=decision['steps'][0]
        applied=receipt.get('appliedSteps') or []
        require(receipt.get('frameId')==decision['frameId'] and receipt.get('modelId')==decision['hybridNavigation']['owner']
            and receipt.get('acceptedAtMs')==ack.get('acceptedAtMs') and len(applied)==1
            and applied[0].get('index')==0 and all(applied[0].get(key)==step[key] for key in ('keys','mouseDx','mouseDy')),
            'Terminal receipt differs from its accepted action')
        at=decision['observationTimestampMs'];begin=applied[0]['startedAtMs'];end=receipt['endedAtMs']
        require(at<=ack['acceptedAtMs']<=begin<at+150 and begin<end<at+700,
            'Terminal receipt is late or crossed the source/expiry bound')
        outcome=(receipt.get('status'),receipt.get('reason'))
        require(outcome in (('completed','horizon_complete'),('replaced','newer_proposal'),('cancelled','client_stop')),
            'Unexpected terminal action outcome')
        if outcome==('cancelled','client_stop'):
            require(receipt==receipts[-1] and receipt in part['stop'].get('receipts',[]),
                'Cancelled input lacks the exact final owned stop receipt')
        ages.append(begin-at)
    require(accepted,'Empty prefix cannot authorize inspected obstacle recovery')
    context=part['stop']['executionContext']
    release_at=context['events'][-2]['atMs']
    require(all(receipt['endedAtMs']<=release_at for receipt in receipts)
        and all(receipt in receipts for receipt in part['stop'].get('receipts',[])),
        'Native stop conflicts with terminal action receipts')
    for event in context['events']:
        call=event['call']
        if call['operation']=='releaseAll':continue
        decision=accepted.get(event.get('requestId')) or {};step=(decision.get('steps') or [{}])[0]
        require(event.get('origin')=='dispatch' and event.get('frameId')==decision.get('frameId')
            and event.get('modelId')==(decision.get('hybridNavigation') or {}).get('owner')
            and event.get('stepIndex')==0,'Native call has no exact admitted controller action')
        receipt=by_id[event['requestId']]
        require(receipt['appliedSteps'][0]['startedAtMs']<=event['atMs']<=receipt['endedAtMs']
            and (call['stage']!='started' or decision['observationTimestampMs']<=event['atMs']<decision['startBeforeMs']),
            'Native call started stale or outside its admitted terminal interval')
        if call['operation']=='mouseMove':
            require(call.get('mouseDx')==step.get('mouseDx') and call.get('mouseDy')==step.get('mouseDy'),
                'Native mouse call differs from its admitted action')
        else:
            require(call.get('key') in ('W','A','S','D')
                and (call['key'] in step.get('keys',[]))==(call['operation']=='keyDown'),
                'Native key call differs from its admitted action')
    return dict(acceptedActions=len(accepted),maximumDispatchAgeMs=max(ages),terminalReceipts=len(receipts))


def stationary_stop_contract(part, frames, points):
    """Independently prove the observed stationary-forward cause without running controller code."""
    final=part['hybridNavigation']['lastPose']
    ordered=[frames[decision['frameId']] for decision in part['decisions']]+[frames[final['frameId']]]
    tail=[]
    for frame in reversed(ordered):
        pose=frame.get('navigationPose') or {}
        if (pose.get('state')!='valid' or math.dist((pose['x'],pose['y']),(final['x'],final['y']))>.5
                or abs((pose['yawDegrees']-final['yawDegrees']+180)%360-180)>5
                or abs((route_heading(pose,points[1])-pose['yawDegrees']+180)%360-180)>5):break
        if tail and not (0<observation_timestamp(tail[-1])-observation_timestamp(frame)<=250
                and frame['frameId']<tail[-1]['frameId']
                and frame['sourceFrame']['timestamp100ns']<tail[-1]['sourceFrame']['timestamp100ns']):break
        tail.append(frame)
    end=observation_timestamp(ordered[-1])
    require(tail and end-observation_timestamp(tail[-1])>=2000,
            'Geometric stop lacks two continuous seconds of stationary aligned decision sources')
    intervals=[]
    for receipt in part['receipts']:
        step=receipt['appliedSteps'][0]
        if step['keys']==['W'] and abs(step['mouseDx'])<=3 and step['mouseDy']==0:
            intervals.append((step['startedAtMs'],receipt['endedAtMs']))
    cursor=end-2000;held=0.0
    for start,finish in sorted(intervals):
        held+=max(0,min(finish,end)-max(cursor,start))
        cursor=max(cursor,finish)
    require(held>=600,'Geometric stop lacks 600 ms of terminal-receipt-backed forward input')
    return dict(stationaryWindowMs=end-observation_timestamp(tail[-1]),confirmedForwardMs=held)


def audit_failed_prefix(folder, request):
    """Replay immutable evidence without rewriting failure flags or invoking live/GPU interfaces."""
    folder=Path(folder).absolute()
    run,run_sha=evidence_document(folder/'patrol.json',4*1024*1024)
    reuse=verify_policy_reuse(run,folder/'patrol.json',Path(str(folder/'patrol.json')+'.reuse.json'))
    original,request_sha=evidence_document(reuse['requestFile'],16384)
    require(original==request and request_sha==reuse['requestSha256'],'Failed-prefix request changed')
    entries=run.get('segments') or []
    require(len(entries)==1 and entries[0].get('number')==1
        and Path(entries[0]['report']).absolute()==folder/'patrol-segments/00001.json',
        'Failed prefix has another segment or uncertain start')
    part,part_sha=evidence_document(entries[0]['report'],16*1024*1024)
    require(part.get('residentRunId')==run['runId'] and entries[0].get('exitCode')==1
        and entries[0].get('acceptedInputActions')==run.get('acceptedInputActions')==part.get('acceptedInputActions'),
        'Failed lease identity or admission accounting changed')
    terminal_contract(run,part)
    control,_=evidence_document(folder/'patrol.json.control.json',16384)
    require(control==dict(version=1,runId=run['runId'],command='run'),'Stop, pause or goal change in original control')
    record=folder/'patrol-recording/00001'
    observed,observed_sha=rows(record/'observations.jsonl')
    video,video_sha=rows(record/'frames.jsonl')
    events,event_sha=rows(record/'events.jsonl')
    frames={frame.get('frameId'):frame for frame in observed}
    require(len(frames)==len(observed)==len(video)==part['framesReceived'],'Missing or duplicated native/RGB frame')
    epochs={(frame.get('sourceFrame') or {}).get('captureEpoch') for frame in observed}
    require(len(epochs)==1 and next(iter(epochs)) and all(a['frameId']<b['frameId'] for a,b in zip(observed,observed[1:])),
            'Failed prefix changed native capture identity or original frame order')
    recorded,recorded_sha=evidence_document(record/'recording.json')
    require(all(recorded.get(key)==value for key,value in part['recording'].items() if key!='workerRetired'),
        'Original recorder finalization differs from segment evidence')
    total=0
    for path in record.iterdir():
        info=path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and path.resolve(strict=True)==path
            and 0<=info.st_size<=160*1024*1024,'Closed recording contains linked or unexpected files')
        if path.name!='recording.json':total+=info.st_size
    require(0<total<=160*1024*1024 and total==run.get('recordedBytes')==part['recording'].get('recordedBytes'),
        'Closed recording bytes differ from original accounting')
    files={}
    for index,frame in enumerate(video):
        source=frames.get(frame.get('frameId')) or {}
        require({key:value for key,value in source.items() if key!='videoQueueAccepted'}==
                {key:value for key,value in frame.items() if key not in ('policyRgb','videoPtsSeconds','videoFrameIndex')}
            and source.get('videoQueueAccepted') is True and frame.get('videoFrameIndex')==index,
            'Retained RGB/native source join changed')
        reference=frame.get('policyRgb') or {}
        name=reference.get('file')
        require(name==f"policy-{index:08d}-frame-{frame['frameId']:012d}.rgb" and name not in files
            and (reference.get('width'),reference.get('height'),reference.get('bytes'),reference.get('format'))==(192,192,RGB192_BYTES,'rgb24'),
            'Invalid exact policy RGB identity')
        raw=evidence_bytes(record/name,RGB192_BYTES)
        require(len(raw)==RGB192_BYTES and hashlib.sha256(raw).hexdigest()==reference.get('sha256'),'Retained RGB bytes changed')
        files[name]=reference['sha256']
    require(all(frame.get('droppedReceipts')==0 for frame in observed),'Native observation reports dropped receipts')
    guard=verify_scout_guard(run,[part],frames,entries,folder/'patrol-recording',reuse)
    require(guard is not None,'Unprotected historical scout cannot retain a policy after failure')
    spec=ReviewedScoutRoute.from_document(request['routeSpec']) if 'routeSpec' in request else None
    points=spec.points if spec is not None else route_points(request['routeId'])
    navigation=part.get('hybridNavigation') or {}
    profile=request.get('navigationProfile')
    require(profile in SCOUT_PROFILES and navigation.get('profileId')==profile,
            'Failed prefix changed its explicit scout localization scope')
    validate_capability(part.get('navigationGuidance') or {},profile)
    starts=[row for row in part.get('hybridNavigationEvents',[]) if row.get('type')=='hybridStartVerified']
    require(len(starts)==1 and navigation.get('routeId')==starts[0].get('routeId')==request['routeId']
        and navigation.get('phase')=='failed' and navigation.get('completedLegs')==0
        and navigation.get('failure')=='survey_obstacle_requires_inspection'
        and not any(row.get('type')=='hybridEndpointVerified' for row in part['hybridNavigationEvents']),
        'Failed geometry was replaced or relabelled as completed')
    final=navigation.get('lastPose') or {}
    require(final and frames.get(final.get('frameId'),{}).get('navigationPose')==final,
        'Obstacle stop lacks its exact original native pose')
    samples=starts[0].get('samples') or []
    require(len(samples)==3,'Failed route did not establish its original start')
    for sample in samples:
        frame=frames.get(sample.get('frameId')) or {};pose=frame.get('navigationPose') or {}
        require(all(pose.get(key)==sample.get(key) for key in ('x','y','yawDegrees'))
            and observation_timestamp(frame)==sample.get('atMs')
            and math.dist((pose['x'],pose['y']),points[0])<=2,'Failed route start/source changed')
    inputs=input_contract(part,frames,events,points,profile)
    require(max(decision['frameId'] for decision in part['decisions'])<final['frameId'],
        'New input was proposed at or after the geometric stop')
    stalled=stationary_stop_contract(part,frames,points)
    return dict(version=1,scope='closed-failed-scout-prefix-only',prefixVerified=True,passed=False,
        routeCompleted=False,runId=run['runId'],requestId=request['requestId'],routeId=request['routeId'],
        residentManifestSha256=run_sha,partSha256=part_sha,requestSha256=request_sha,
        observationsSha256=observed_sha,framesSha256=video_sha,eventsSha256=event_sha,
        recordingSha256=recorded_sha,rgbFiles=files,guard=guard,**inputs,**stalled,
        bridgeStopAcknowledged=True,physicalInputDeliveryVerified=False,originalEvidenceComplete=False)


def verify_recovery_request(request, witness, owner):
    """Require a new review/source after cleanup and a different route before opening another lease."""
    require(witness.get('owner')==owner and witness.get('originalOwnerIdleMinimizedAfter') is True
        and witness.get('residentControlRetired') is True and witness.get('newPythonThreadsAlive')==[]
        and witness.get('retainedState')=='policy-weights-and-immutable-configuration-only'
        and all(type(witness.get(key)) is int and witness[key]>0 for key in ('cleanupAtUnixNs','cleanupAtMonotonicNs')),
        'Inspected recovery has no exact original cleanup/retirement witness')
    require(request.get('obstacleRecovery')==witness and request.get('afterRequestId')==witness['failedRequestId']
        and request.get('requestId')!=witness['failedRequestId'] and request.get('routeId')!=witness['failedRouteId'],
        'Inspected recovery must be a fresh chained request for a different route')
    spec=ReviewedScoutRoute.from_document(request['routeSpec']) if 'routeSpec' in request else None
    points=spec.points if spec is not None else route_points(request['routeId'])
    require([list(point) for point in points]!=witness['failedRoutePoints']
            and list(points[1])!=witness['failedRoutePoints'][1],
            'Inspected recovery cannot reissue the same blocked destination')
    review=verify_scout_review(request,owner,points,spec)
    require(request['reviewSha256']!=witness['failedReviewSha256'],'Inspected recovery reused the failed review')
    endpoint=Path(review['nativeEndpoint'])
    result,_=evidence_document(endpoint/'result.json',4*1024*1024)
    metadata,_=evidence_document(endpoint/Path(review['imageName']).with_suffix('.json'),65536)
    sources=[sample['sourceFrame'] for sample in result['stableSamples']]+[metadata['sourceFrame']]
    require(all(type(source.get('timestamp100ns')) is int and source['timestamp100ns']*100>witness['cleanupAtMonotonicNs']
        for source in sources),'Inspected recovery source predates completed cleanup')
    require(all(path.stat().st_mtime_ns>=witness['cleanupAtUnixNs'] for path in
        (Path(request['reviewFile']),endpoint/'result.json',endpoint/review['imageName'])),
        'Inspected recovery review was captured before completed cleanup')
    audit,digest=evidence_document(witness['prefixAuditFile'],4*1024*1024)
    require(digest==witness['prefixAuditSha256'] and audit.get('prefixVerified') is True
        and audit.get('passed') is False and audit.get('runId')==witness['failedRunId']
        and audit.get('requestId')==witness['failedRequestId']
        and audit.get('residentManifestSha256')==witness['failedManifestSha256'],'Inspected recovery prefix proof changed')
    failed_folder=Path(witness['prefixAuditFile']).parent
    failed_run,digest=evidence_document(failed_folder/'patrol.json',4*1024*1024)
    failed_request,_=evidence_document(failed_run['policyReuse']['requestFile'],16384)
    session_file=Path(failed_run['policyReuse']['sessionProof'])
    session,_=evidence_document(session_file)
    manifest,_=evidence_document(session_file.parent/'manifest.json')
    profile=manifest.get('navigationProfile',SCOUT_PROFILE)
    require(profile in SCOUT_PROFILES and session.get('navigationProfile',SCOUT_PROFILE)==profile
        and failed_request.get('navigationProfile')==request.get('navigationProfile')==profile,
        'Inspected recovery cannot change the original worker localization scope')
    require(manifest.get('inspectedObstacleRecoveryPolicy')==session.get('inspectedObstacleRecoveryPolicy')==recovery_policy()
        and manifest.get('recoverySourceSha256')==session.get('recoverySourceSha256')==source_contract()
        and request.get('sessionId')==failed_request.get('sessionId')==manifest.get('sessionId')
        and manifest.get('owner')==owner and failed_folder.name==witness['failedRequestId']
        and Path(witness['prefixAuditFile']).name=='failed-prefix-audit.json',
        'Original worker did not authorize this source-bound inspected recovery')
    failed_spec=ReviewedScoutRoute.from_document(failed_request['routeSpec']) if 'routeSpec' in failed_request else None
    old_points=failed_spec.points if failed_spec is not None else route_points(failed_request['routeId'])
    require(witness['failedRouteId']==failed_request['routeId'] and witness['failedReviewSha256']==failed_request['reviewSha256']
        and witness['failedRoutePoints']==[list(point) for point in old_points],
        'Inspected recovery substituted the original failed route or review')
    require(digest==witness['failedManifestSha256'] and audit_failed_prefix(failed_folder,failed_request)==audit,
        'Original failed prefix changed after inspection')
    return dict(failedRequestId=witness['failedRequestId'],failedRunId=witness['failedRunId'],
        prefixAuditSha256=witness['prefixAuditSha256'],freshReviewSha256=request['reviewSha256'])
