"""Replay one closed stale-source failure without converting it into a completed route."""
import hashlib
import json
import math
from pathlib import Path
import stat

from audit_hybrid_run import (evidence_bytes, evidence_document, require, verify_policy_reuse,
    verify_executed_history, verify_scout_goal_state, verify_scout_guard, verify_scout_review)
from audit_scout_obstacle import native_stop_contract
from hybrid_routes import camera_correction, route_heading
from native_ground_control import require_ground_frame, validate_frame as validate_ground_frame
from navigation_profiles import SCOUT_PROFILES, allows_pose_scope, validate_capability
from observation_timing import observation_timestamp
from policy_rgb_archive import (RGB192_BYTES, RECORDING_FORMAT, read_recording_jsonl, read_policy_rgb, recording_metadata)
from reviewed_scout_route import ReviewedScoutRoute


STALE_ERROR = 'Scout encounter guard: nativeSensorStale'
HISTORY_MODE = 'receipt-verified-executed-actions-v1'
SOURCE_NAMES = ('scout_session.py', 'audit_scout_obstacle.py', 'audit_hybrid_run.py',
    'resident_runtime.py', 'stream_client.py', 'scout_encounter_guard.py', 'hybrid_navigation.py',
    'reviewed_scout_route.py', 'run_patrol_series.py', 'run_rdp_patrol.py', 'bridge_transport.py',
    'policy_rgb_archive.py', 'episode_split.py', 'observation_timing.py', 'model_adapters.py',
    'native_combat.py', 'navigation_profiles.py', 'p2p_startup.py', 'p2p_temporal_cache.py',
    'audit_scout_source_gap.py', 'native_ground_control.py', 'capture_scout_scene.py', 'hybrid_routes.py',
    'p2p_executed_history.py', 'p2p_action_codec.py', 'p2p_loader.py', 'p2p_compat_attention.py',
    'p2p_sampling.py', 'p2p_rotary.py', 'p2p_executed_history_graph.py')


def recovery_policy():
    """Declare one reviewed weight-retention opportunity, with no input or retry authority."""
    return dict(version=1, maximumInspectedSourceGapRecoveries=1, error=STALE_ERROR,
        retain='policy-weights-and-immutable-configuration-only', automaticRequests=False,
        failedLegRemainsFailed=True, requireFreshGuard=True, requirePostCleanupReview=True,
        requireHistoryReset=True, sourceFreshnessMs=150, historyCommitMode=HISTORY_MODE,
        allowedActionHoldMs=[50,60], sameRouteRequiresFreshReview=True)


def source_contract():
    """Pin the finite runtime, recorder and independent proof dependencies for this opt-in."""
    root=Path(__file__).absolute().parent
    return {name:hashlib.sha256(evidence_bytes(root/name,2*1024*1024)).hexdigest() for name in SOURCE_NAMES}


def terminal_contract(run, part):
    """Require the exact stale guard failure and complete software cleanup, never physical delivery."""
    require(run.get('status')==part.get('status')=='failed' and run.get('error')==part.get('error')==STALE_ERROR
        and run.get('endReason')=='error' and part.get('endReason')=='scoutEncounterGuard'
        and part.get('streamError')==STALE_ERROR and part.get('scoutEncounterGuardTriggerRecorded') is True
        and run.get('evidenceComplete') is False and type(run.get('failedLeases')) is int and run['failedLeases']==1
        and run.get('connectionErrors')==[] and run.get('recordingBudgetExhausted') is False,
        'Not the single closed nativeSensorStale failure')
    forbidden=('unacknowledgedAction','unacknowledgedRecoveryAction','stopError','captureError',
        'recordingFinalizationError','navigationClimbHandleCloseError','executionContextFinalError','evidenceError',
        'scoutEncounterGuardError','combatTrialReleaseError')
    require(all(value.get(key) is None for value in (run,part) for key in forbidden),
        'Source gap has another failure or uncertain input outcome')
    require(part.get('episodeFailure')==dict(type='ScoutEncounterStop',transportOperation=None)
        and type(part.get('unappliedAcceptedActions')) is int and part['unappliedAcceptedActions']==0
        and type(part.get('serverDroppedReceipts')) is int and part['serverDroppedReceipts']==0
        and part.get('receiptHistoryResets',0)==0, 'Source gap has missing receipts or unsettled history')
    hold=part.get('actionHoldMs')
    require(type(hold) is int and hold in (50,60) and run.get('actionHoldMs')==hold
        and run.get('historyCommitMode')==part.get('historyCommitMode')==HISTORY_MODE
        and part.get('maxObservationAgeMs')==150 and part.get('decisionHz')==10
        and part.get('capturePollHz')==20 and part.get('inputRequested') is True
        and part.get('nativeInputEnabled') is True and set(part.get('effectiveInputKeys',[]))=={'W','A','S','D'},
        'Source-gap action limits or executed-history mode changed')
    require(not part.get('navigationClimbActions') and not part.get('navigationClimbRecovery')
        and (part.get('navigationIdleRecovery') or {}).get('enabled') is False
        and not part.get('navigationIdleRecoveryEvents') and part.get('controlTransitions')==[],
        'Source gap crossed recovery or control transitions')
    for value,label in ((run,'summary'),(part.get('initialGoalState'),'initial'),
        (part.get('finalGoalState'),'final'),(part.get('leaseInitialGoalState'),'lease initial')):
        verify_scout_goal_state(value,label)
        require(value.get('controlEpoch')==0,'Source gap crossed operator control')
    require(run.get('goalChanges')==part.get('goalChanges')==[],'Source gap contains a goal change')
    segment=part.get('segment') or {}; continuity=part.get('continuity') or {}
    require(segment.get('number')==1 and segment.get('leaseEnded') is True
        and type(segment.get('startedAtClientNs')) is int and type(segment.get('endedAtClientNs')) is int
        and 0<segment['endedAtClientNs']-segment['startedAtClientNs']<=35_000_000_000,
        'Source gap exceeded one closed 35-second lease')
    require(continuity.get('previousReport') is None and continuity.get('sameBridgeLease') is False
        and all(continuity.get(key)==[] for key in ('pendingProposals','pendingRecoveryActions','sourceFrames')),
        'Source gap retained pending work or another lease')
    recording=part.get('recording') or {};count=part.get('framesReceived')
    require(all(recording.get(key) is True for key in ('complete','lossless','closed','workerRetired','policyRgbEnabled'))
        and recording.get('error') is None and all(type(recording.get(key)) is int and recording[key]==0
        for key in ('droppedFrames','droppedEvents','droppedObservations','abandonedFrames')),
        'Source-gap recorder is open, lossy, failed or still running')
    require(type(count) is int and count>0 and recording.get('encodedFrames')==recording.get('policyRgbFrames')==count
        and recording.get('recordedObservations')==count and recording.get('policyRgbBytes')==count*RGB192_BYTES,
        'Source-gap recording/frame counters disagree')
    stop=part.get('stop') or {};context=stop.get('executionContext') or {};tracked=context.get('trackedState') or {}
    require(stop.get('type')=='stopped' and context.get('active') is None and context.get('telemetryComplete') is True
        and tracked.get('heldKeys')==[] and tracked.get('telemetryIncomplete') is False
        and tracked.get('releaseOutcome')=='returned_unverified' and context.get('physicalExecutionProven') is False,
        'Source-gap stop or release acknowledgement is unresolved')
    native_stop_contract(context)
    state=part.get('scoutEncounterGuardState') or {};trip=state.get('trip') or {}
    require(run.get('scoutEncounterGuardState')==state and state.get('state')=='tripped'
        and state.get('armed') is False and trip.get('reason')=='nativeSensorStale'
        and type(trip.get('clientReceivedNs')) is int and trip['clientReceivedNs']<=segment['endedAtClientNs'],
        'Source-gap guard was not retained and acknowledged released')


def frame_contract(observed, video, events, part, record):
    """Join indexed RGB and native crops, permitting only the exact duplicate final stale trigger."""
    require(len(observed)==len(video)==part['framesReceived'] and observed,'Source-gap frames are missing')
    frames={};files={};epoch=None;previous=None;crops=0;stored_rgb_bytes=0
    trigger=(part['scoutEncounterGuardState']['trip'])
    first_input=min(d['frameId'] for d in part['decisions'] if d.get('acceptance',{}).get('type')=='accepted')
    baseline=part['scoutEncounterGuard']['baselineHealthFraction']
    # Poll timing/readiness is sampled again when the same immutable image becomes the retained trigger.
    polling={'sourceFrameAgeMs','reportedSourceFrameAgeMs','serverNowMs','clientReceivedNs',
        'transportRoundTripMs','readback','frameQuality','videoQueueAccepted',
        'worldReadiness','inputAvailable','motionEvidence'}
    for index,(frame,row) in enumerate(zip(observed,video)):
        require(isinstance(frame,dict) and isinstance(row,dict) and frame.get('type')=='frame'
            and type(frame.get('frameId')) is int and frame['frameId']>0
            and frame.get('videoQueueAccepted') is True and row.get('videoFrameIndex')==index
            and {k:v for k,v in frame.items() if k!='videoQueueAccepted'}==
                {k:v for k,v in row.items() if k not in ('policyRgb','videoPtsSeconds','videoFrameIndex')},
            'Source-gap RGB/native source metadata changed')
        source=frame.get('sourceFrame') or {};identity=frame['frameId']
        require(type(source.get('timestamp100ns')) is int and source['timestamp100ns']>0
            and isinstance(source.get('captureEpoch'),str) and source['captureEpoch'], 'Invalid source identity')
        if epoch is None:epoch=source['captureEpoch']
        require(source['captureEpoch']==epoch and frame.get('droppedReceipts')==0,'Source epoch changed or receipts dropped')
        if identity in frames:
            require(index==len(video)-1 and previous is not None and identity==previous['frameId']
                and trigger['frame']['frameId']==identity and frame['clientReceivedNs']==trigger['clientReceivedNs']
                and {k:v for k,v in frame.items() if k not in polling}==
                    {k:v for k,v in frames[identity].items() if k not in polling},
                'Conflicting or nonterminal duplicate source')
        else:
            require(previous is None or identity>previous['frameId'] and
                source['timestamp100ns']>previous['sourceFrame']['timestamp100ns'], 'Source chronology changed')
            frames[identity]=frame
        raw=read_policy_rgb(record,row.get('policyRgb'),index=index,frame_id=identity,recording=part['recording'])
        name=row['policyRgb']['file'];require(name not in files,'Repeated RGB archive name')
        files[name]=hashlib.sha256(raw).hexdigest()
        stored_rgb_bytes+=row['policyRgb'].get('storedBytes',row['policyRgb']['bytes'])
        if previous is not None and identity==previous['frameId']:
            require(files[name]==files[video[index-1]['policyRgb']['file']], 'Duplicate trigger pixels changed')
        ground=validate_ground_frame(frame,replay_pixels=True);crops+=len((ground or {}).get('crops',[]))
        combat=frame.get('combatEvidence') or {}
        if combat.get('state')=='valid':
            require(combat.get('playerHealthColor')=='green' and not combat.get('enemyBarCandidates')
                and combat.get('redMaskOverloaded') is False and combat.get('playerHealthFractionEstimate',-1)>=baseline,
                'Source-gap trace contains enemy, ambiguous health or health loss')
        if identity>=first_input:
            require_ground_frame(frame,replay_pixels=True)
            current=frame.get('worldReadiness') or {};captured=frame.get('frameWorldReadiness') or {}
            ready=current.get('ready') is True and frame.get('inputAvailable') is True
            # Native expiry may run before the next Python poll. Its derived unknown motion
            # cannot overwrite the retained positive pixels, or authorize any further input.
            expired=(index==len(video)-1 and current.get('ready') is False
                and current.get('reason')=='world_observation_stale' and frame.get('inputAvailable') is False
                and current.get('sourceFrameId')==identity and current.get('sourceFrame')==source
                and type(captured.get('epoch')) is int and type(current.get('epoch')) is int
                and current['epoch']==captured['epoch']+1
                and source['freshnessAtMs']+150<=current.get('checkedAtMs',-1)<=frame['serverNowMs']
                and (frame.get('motionEvidence') or {}).get('status')=='unknown'
                and (frame.get('motionEvidence') or {}).get('reason')=='world_not_ready')
            require(combat.get('state')=='valid' and captured.get('ready') is True and (ready or expired),
                'Source-gap trace lost an additional native readiness or health gate')
        previous=frame
    final=observed[-1]
    require(final['frameId']==trigger['frame']['frameId'] and final['clientReceivedNs']==trigger['clientReceivedNs']
        and type(final.get('sourceFrameAgeMs')) in (int,float) and math.isfinite(final['sourceFrameAgeMs'])
        and final['sourceFrameAgeMs']>150 and math.isclose(final['serverNowMs']-final['sourceFrame']['freshnessAtMs'],
            final['sourceFrameAgeMs'],rel_tol=0,abs_tol=1e-6),
        'Source-gap trigger is missing or was not natively stale')
    for event in events:
        require(event.get('type') not in ('goalChanged','goalChange','goalApplied','goalRequest','controlTransition'),
            'Source-gap journal contains another goal/control interruption')
    releases=[event for event in events if event.get('type')=='scoutEncounterGuardRelease']
    require(releases and part.get('scoutEncounterGuardRelease')==releases[0].get('response')
        and all((event.get('response') or {}).get('droppedReceipts')==0 for event in releases),
        'Source-gap trip release differs from its original acknowledgement')
    if part['recording'].get('recordingFormat')==RECORDING_FORMAT:
        require(stored_rgb_bytes==part['recording'].get('policyRgbStoredBytes'),
            'Source-gap stored RGB aggregate differs from its original seal')
    return frames,files,crops


def input_contract(part, frames, events, points, profile):
    """Independently join accepted route selections to all completed receipts and native calls."""
    decisions=part.get('decisions') or [];receipts=part.get('receipts') or []
    accepted={};hold=part['actionHoldMs'];trip=part['scoutEncounterGuardState']['trip']
    for decision in decisions:
        verify_scout_goal_state(decision,'source-gap decision',decision=True)
        require(decision.get('controlEpoch')==0,'Source-gap decision crossed control epochs')
        ack=decision.get('acceptance') or {}
        if ack.get('type')!='accepted':
            require(ack.get('type')=='notSubmitted' and ack.get('reason')=='observationTooOld'
                and decision.get('historyCommitted') is False,'Source gap has another rejected/unknown action')
            continue
        rid=ack.get('requestId');require(isinstance(rid,str) and rid not in accepted,'Duplicate source-gap admission')
        accepted[rid]=decision;frame=frames.get(decision.get('frameId')) or {};pose=frame.get('navigationPose') or {}
        h=decision.get('hybridNavigation') or {};step=h.get('step') or {};gate=frame.get('frameWorldReadiness') or {}
        require(h.get('pose')==pose and pose.get('state')=='valid' and pose.get('frameId')==frame.get('frameId')
            and allows_pose_scope(pose,profile) and .99<=pose.get('positionConfidence',0)<=1
            and .2<=pose.get('yawConfidence',0)<=1 and gate.get('ready') is True
            and gate.get('sourceFrameId')==frame['frameId'] and gate.get('sourceFrame')==frame['sourceFrame']
            and (frame.get('motionEvidence') or {}).get('status')=='normal'
            and (frame.get('motionEvidence') or {}).get('spaceKeyMatched') is False
            and decision.get('nativeCombatEvidence')==frame.get('combatEvidence'),
            'Source-gap input lost its qualified native pose/source')
        require(h.get('target')=='end' and h.get('completedLegs')==0 and decision.get('steps')==[step]
            and step.get('durationMs')==hold and step.get('mouseDy')==0, 'Source-gap selected target/hold changed')
        heading=route_heading(pose,points[1]);error=abs((heading-pose['yawDegrees']+180)%360-180)
        if h.get('reason')=='nativeHeading':
            require(error>5 and h.get('owner')=='hybrid-native' and step.get('keys')==[]
                and step.get('mouseDx')==max(-350,min(350,int(camera_correction(pose['yawDegrees'],heading)))),
                'Source-gap native heading differs from reviewed geometry')
        else:
            require(error<=5 and step.get('keys')==['W'] and abs(step.get('mouseDx',999))<=3
                and (h.get('reason'),h.get('owner')) in (('modelIdleOrOffRoute','hybrid-native'),('modelRouteCompatible','open-p2p')),
                'Source-gap forward selection differs from reviewed geometry')
    terminal={r.get('requestId'):r for r in receipts}
    dispatches=[e for e in events if e.get('type')=='scoutEncounterGuardDispatch']
    require(accepted and type(part.get('acceptedInputActions')) is int
        and len(terminal)==len(receipts)==len(accepted)==part['acceptedInputActions']
        and set(terminal)==set(accepted) and len(dispatches)==len(accepted)
        and {e.get('requestId') for e in dispatches}==set(accepted), 'Source gap lacks a full admission/receipt bijection')
    require(all(e['marker']['clientDispatchNs']<trip['clientReceivedNs'] for e in dispatches), 'Input after stale trigger')
    for rid,r in terminal.items():
        d=accepted[rid];step=d['steps'][0];applied=r.get('appliedSteps') or []
        require(r.get('status')=='completed' and r.get('reason')=='horizon_complete' and len(applied)==1
            and r.get('frameId')==d['frameId'] and r.get('modelId')==d['hybridNavigation']['owner']
            and r.get('acceptedAtMs')==d['acceptance'].get('acceptedAtMs') and applied[0].get('index')==0
            and all(applied[0].get(k)==step[k] for k in ('keys','mouseDx','mouseDy')),
            'Source gap has a missing, replaced, late or changed terminal receipt')
    context=part['stop']['executionContext'];native={rid:[] for rid in accepted};ages=[];horizons={}
    for event in context['events']:
        call=event['call']
        if call['operation']=='releaseAll':
            require(event.get('origin') in ('release:horizon_complete','release:client_release','release:client_stop'),
                'Source-gap native release has another failure cause')
            if event['origin']=='release:horizon_complete':
                rid=event.get('requestId');receipt=terminal.get(rid) or {}
                require(event.get('frameId')==receipt.get('frameId') and event.get('modelId')==receipt.get('modelId')
                    and event.get('stepIndex')==0 and receipt.get('endedAtMs',math.inf)<=event['atMs'],
                    'Source-gap horizon release has no exact completed receipt')
                horizons.setdefault(rid,[]).append(event)
            continue
        rid=event.get('requestId');d=accepted.get(rid) or {};step=(d.get('steps') or [{}])[0];r=terminal.get(rid) or {}
        require(event.get('origin')=='dispatch' and event.get('frameId')==d.get('frameId')
            and event.get('modelId')==(d.get('hybridNavigation') or {}).get('owner') and event.get('stepIndex')==0,
            'Unknown native dispatch in source-gap prefix')
        require(r['appliedSteps'][0]['startedAtMs']<=event['atMs']<=r['endedAtMs']
            and (call['stage']!='started' or observation_timestamp(frames[d['frameId']])<=event['atMs']<d['startBeforeMs']),
            'Source-gap native call is stale or outside its terminal interval')
        require(call['operation'] in ('keyDown','mouseMove'), 'Unexpected native key release or operation')
        if call['operation']=='keyDown':require(call.get('key') in step['keys'] and call['key'] in ('W','A','S','D'), 'Changed native key')
        else:require(all(call.get(k)==step[k] for k in ('mouseDx','mouseDy')), 'Changed native mouse delta')
        if call['stage']=='started':native[rid].append(call);ages.append(event['atMs']-observation_timestamp(frames[d['frameId']]))
    for rid,calls in native.items():
        step=accepted[rid]['steps'][0]
        require(len(calls)==len(step['keys'])+int(bool(step['mouseDx'] or step['mouseDy']))
            and sorted(c['key'] for c in calls if c['operation']=='keyDown')==sorted(step['keys']),
            'Source gap lost or duplicated a native dispatch call')
    require(set(horizons)==set(terminal) and all(len(rows)==2 for rows in horizons.values()),
        'Source gap lacks exactly one native horizon release per completed action')
    for index,receipt in enumerate(receipts):
        boundary=receipts[index+1]['acceptedAtMs'] if index+1<len(receipts) else context['events'][-2]['atMs']
        require(horizons[receipt['requestId']][-1]['atMs']<=boundary,
            'Source-gap native release overlaps another admission or final stop')
    require(all(r['endedAtMs']<=context['events'][-2]['atMs'] for r in receipts)
        and all(r in receipts for r in part['stop'].get('receipts',[])), 'Source-gap final stop conflicts with receipts')
    return dict(acceptedActions=len(accepted),terminalReceipts=len(receipts),maximumDispatchAgeMs=max(ages))


def audit_failed_prefix(folder, request):
    """Read only the sealed failed leg; historical proof does not imply retention was authorized."""
    folder=Path(folder).absolute();run,run_sha=evidence_document(folder/'patrol.json',4*1024*1024)
    require('sourceGapRecovery' not in request and 'obstacleRecovery' not in request,
        'A successor failure cannot authorize a second source-gap recovery')
    reuse=verify_policy_reuse(run,folder/'patrol.json',folder/'patrol.json.reuse.json')
    original,request_sha=evidence_document(reuse['requestFile'],32768)
    require(original==request and request_sha==reuse['requestSha256'],'Original source-gap request changed')
    require('routeSpec' in request and request.get('historyCommitMode')==HISTORY_MODE
        and type(request.get('actionHoldMs')) is int and request['actionHoldMs'] in (50,60),
        'Source gap requires explicit reviewed geometry and executed history')
    spec=ReviewedScoutRoute.from_document(request['routeSpec']);profile=request.get('navigationProfile')
    require(profile in SCOUT_PROFILES and spec.profile_id==profile,'Source-gap scope changed')
    entries=run.get('segments') or []
    require(len(entries)==1 and entries[0].get('number')==1 and entries[0].get('exitCode')==1
        and Path(entries[0]['report']).absolute()==folder/'patrol-segments/00001.json', 'Source gap has another lease or uncertain start')
    part,part_sha=evidence_document(entries[0]['report'],16*1024*1024)
    require(part.get('residentRunId')==run.get('runId') and entries[0].get('acceptedInputActions')==
        run.get('acceptedInputActions')==part.get('acceptedInputActions'),'Source-gap run/admission identity changed')
    terminal_contract(run,part)
    control,_=evidence_document(folder/'patrol.json.control.json',16384)
    require(control==dict(version=1,runId=run['runId'],command='run'),'Source-gap original control was changed')
    record=folder/'patrol-recording/00001';recorded=recording_metadata(record,recording=part['recording'])
    require(all(recorded.get(k)==v for k,v in part['recording'].items() if k!='workerRetired'),
        'Source-gap recorder seal differs from terminal report')
    observed,observed_sha=read_recording_jsonl(record,'observations.jsonl')
    video,video_sha=read_recording_jsonl(record,'frames.jsonl');events,event_sha=read_recording_jsonl(record,'events.jsonl')
    frames,rgb,crops=frame_contract(observed,video,events,part,record)
    file_hashes={};total=0
    for index,path in enumerate(record.iterdir()):
        info=path.lstat()
        require(index<len(video)+16 and stat.S_ISREG(info.st_mode) and info.st_nlink==1 and path.resolve(strict=True)==path
            and 0<=info.st_size<=160*1024*1024,'Source-gap recording contains linked or unexpected files')
        if path.name!='recording.json':total+=info.st_size
        require(total<=160*1024*1024,'Source-gap recording exceeds its finite byte budget')
        if info.st_size:
            raw=evidence_bytes(path,160*1024*1024)
        else:
            # An empty ffmpeg log is valid; still read a bounded byte to reject a changed file.
            with path.open('rb') as stream:raw=stream.read(1)
            require(raw==b'','Source-gap empty recording file changed during replay')
        file_hashes[path.name]=hashlib.sha256(raw).hexdigest()
    require(0<total<=160*1024*1024 and total==run.get('recordedBytes')==part['recording'].get('recordedBytes'),
        'Source-gap closed directory bytes differ from original accounting')
    guard=verify_scout_guard(run,[part],frames,entries,folder/'patrol-recording',reuse,allow_stale_stop=True)
    require(guard is not None and guard.get('terminalReason')=='nativeSensorStale','Source-gap guard replay did not establish the exact trip')
    history=verify_executed_history(run,[part],frames,entries,folder/'patrol-recording',reuse)
    require(history is not None and history['committedActions']==part['acceptedInputActions'],'Missing executed-history proof')
    navigation=part.get('hybridNavigation') or {};starts=[e for e in part.get('hybridNavigationEvents',[]) if e.get('type')=='hybridStartVerified']
    validate_capability(part.get('navigationGuidance') or {},profile)
    require(len(starts)==1 and navigation.get('profileId')==profile and navigation.get('routeId')==request['routeId']
        and starts[0].get('routeId')==request['routeId'] and navigation.get('phase')=='walking'
        and navigation.get('target')=='end' and navigation.get('completedLegs')==0 and navigation.get('failure') is None
        and navigation.get('recoveryAttempts')==0 and navigation.get('requireGroundControls') is True
        and navigation.get('routeSpec')==request['routeSpec'] and not any(e.get('type')=='hybridEndpointVerified'
        for e in part.get('hybridNavigationEvents',[])), 'Source-gap route was replaced or relabelled complete')
    require(len(starts[0].get('samples',[]))==3,'Source-gap route lacks its reviewed start')
    for sample in starts[0]['samples']:
        frame=frames.get(sample.get('frameId')) or {};pose=frame.get('navigationPose') or {}
        require(all(pose.get(k)==sample.get(k) for k in ('x','y','yawDegrees'))
            and observation_timestamp(frame)==sample.get('atMs') and math.dist((pose['x'],pose['y']),spec.points[0])<=2,
            'Source-gap route start/source changed')
    inputs=input_contract(part,frames,events,spec.points,profile)
    return dict(version=1,scope='closed-failed-scout-source-gap-prefix-only',prefixVerified=True,passed=False,
        routeCompleted=False,failureReason=STALE_ERROR,runId=run['runId'],requestId=request['requestId'],routeId=request['routeId'],
        residentManifestSha256=run_sha,partSha256=part_sha,requestSha256=request_sha,
        observationsSha256=observed_sha,framesSha256=video_sha,eventsSha256=event_sha,
        recordingSha256=file_hashes['recording.json'],recordingFilesSha256=file_hashes,rgbFiles=rgb,
        groundCropsReplayed=crops,guard=guard,history=history,**inputs,bridgeStopAcknowledged=True,
        physicalInputDeliveryVerified=False,originalEvidenceComplete=False)


def verify_recovery_request(request, witness, owner):
    """Bind a new post-cleanup review to one explicitly authorized, immutable failed prefix."""
    require(isinstance(witness,dict) and witness.get('owner')==owner
        and witness.get('originalOwnerIdleMinimizedAfter') is True and witness.get('residentControlRetired') is True
        and witness.get('newPythonThreadsAlive')==[] and witness.get('historyReset') is True
        and witness.get('failureReason')==STALE_ERROR and witness.get('retainedState')=='policy-weights-and-immutable-configuration-only'
        and all(type(witness.get(k)) is int and witness[k]>0 for k in ('cleanupAtUnixNs','cleanupAtMonotonicNs')),
        'Source-gap recovery lacks exact cleanup, reset or owner witness')
    require(request.get('sourceGapRecovery')==witness and 'obstacleRecovery' not in request
        and request.get('afterRequestId')==witness['failedRequestId'] and request.get('requestId')!=witness['failedRequestId']
        and 'routeSpec' in request and request.get('historyCommitMode')==HISTORY_MODE
        and type(request.get('actionHoldMs')) is int and request['actionHoldMs'] in (50,60),
        'Source-gap recovery is not a fresh chained reviewed request')
    path=Path(witness['prefixAuditFile']);proof,digest=evidence_document(path,4*1024*1024)
    require(path.name=='failed-source-gap-audit.json' and path.parent.name==witness['failedRequestId']
        and digest==witness['prefixAuditSha256'] and proof.get('prefixVerified') is True and proof.get('passed') is False
        and proof.get('routeCompleted') is False and proof.get('failureReason')==STALE_ERROR
        and proof.get('runId')==witness['failedRunId'] and proof.get('requestId')==witness['failedRequestId']
        and proof.get('residentManifestSha256')==witness['failedManifestSha256'],'Source-gap prefix proof changed')
    failed,digest=evidence_document(path.parent/'patrol.json',4*1024*1024)
    old,_=evidence_document(failed['policyReuse']['requestFile'],32768)
    require('sourceGapRecovery' not in old and 'obstacleRecovery' not in old,'Second or recursive source-gap recovery')
    session_path=Path(failed['policyReuse']['sessionProof']);session,_=evidence_document(session_path)
    manifest,_=evidence_document(session_path.parent/'manifest.json')
    pins=manifest.get('sourceGapRecoverySourceSha256')
    require(manifest.get('inspectedSourceGapRecoveryPolicy')==session.get('inspectedSourceGapRecoveryPolicy')==recovery_policy()
        and isinstance(pins,dict) and set(pins)==set(SOURCE_NAMES) and session.get('sourceGapRecoverySourceSha256')==pins
        and 'inspectedObstacleRecoveryPolicy' not in manifest and 'inspectedObstacleRecoveryPolicy' not in session
        and manifest.get('owner')==session.get('owner')==owner
        and request.get('sessionId')==old.get('sessionId')==manifest.get('sessionId')==session.get('sessionId')
        and request.get('modelConfigurationSha256')==old.get('modelConfigurationSha256')==manifest.get('modelConfigurationSha256')
        and request.get('navigationProfile')==old.get('navigationProfile')==manifest.get('navigationProfile')
        and request.get('historyCommitMode')==old.get('historyCommitMode')==manifest.get('historyCommitMode')==HISTORY_MODE
        and request.get('actionHoldMs')==old.get('actionHoldMs')==manifest.get('actionHoldMs'),
        'Original worker did not authorize this source-bound inspected source-gap recovery')
    for name,pin in pins.items():
        require(hashlib.sha256(evidence_bytes(session_path.parent.parent/'source-snapshot'/name,2*1024*1024)).hexdigest()==pin,
            'Original source-gap recovery source archive changed')
    old_spec=ReviewedScoutRoute.from_document(old['routeSpec'])
    require(witness.get('failedRouteId')==old['routeId'] and witness.get('failedReviewSha256')==old['reviewSha256']
        and witness.get('failedRoutePoints')==[list(p) for p in old_spec.points]
        and digest==witness['failedManifestSha256'] and audit_failed_prefix(path.parent,old)==proof,
        'Original failed source-gap prefix changed after inspection')
    spec=ReviewedScoutRoute.from_document(request['routeSpec'])
    review=verify_scout_review(request,owner,spec.points,spec)
    require(request['reviewSha256']!=old['reviewSha256'],'Source-gap recovery reused its old review')
    endpoint=Path(review['nativeEndpoint']);scene,_=evidence_document(endpoint/'result.json',4*1024*1024)
    metadata,_=evidence_document(endpoint/Path(review['imageName']).with_suffix('.json'),65536)
    sources=[sample['sourceFrame'] for sample in scene['stableSamples']]+[metadata['sourceFrame']]
    for source in sources:
        require(type(source.get('timestamp100ns')) is int and source['timestamp100ns']>0
            and all(type(source.get(k)) in (int,float) and math.isfinite(source[k])
                for k in ('capturedAtMs','freshnessAtMs')),
            'Source-gap recovery lacks the original source clock')
        # Reported compositor time can lead first acquisition. Map the declared freshness
        # clock back to the same absolute QPC domain rather than accepting that lead as new pixels.
        reported_ns=source['timestamp100ns']*100
        fresh_ns=reported_ns+(source['freshnessAtMs']-source['capturedAtMs'])*1_000_000
        require(min(reported_ns,fresh_ns)>witness['cleanupAtMonotonicNs'],
            'Source-gap recovery source predates completed cleanup')
    require(all(p.stat().st_mtime_ns>=witness['cleanupAtUnixNs'] for p in
        (Path(request['reviewFile']),endpoint/'plan.json',endpoint/'result.json',endpoint/review['imageName'],
         endpoint/Path(review['imageName']).with_suffix('.json'))), 'Source-gap recovery review predates completed cleanup')
    return dict(failedRequestId=witness['failedRequestId'],failedRunId=witness['failedRunId'],
        prefixAuditSha256=witness['prefixAuditSha256'],freshReviewSha256=request['reviewSha256'])
