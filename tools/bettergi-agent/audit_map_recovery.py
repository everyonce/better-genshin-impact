"""Verify the interrupted R58 map opening and a separately owned, close-only R59 recovery."""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

from audit_hybrid_run import require
from audit_map_inspection import (JUNCTION, NATIVE_SIZE, g4_witness, junction_poses, known_map,
                                  map_scores, original_png, resumed_goal, source_ticks)
from audit_photo_handoff import audit_photo_handoff, bridge_clock, read
from landmark_recognizer import G4_SHA256, LandmarkRecognizer
from map_owner import load_map_owner
from observation_profiles import P2P_NATIVE, verify_hello
from patrol_photo_survey import require_qualified_observer


def digest(path):
    """Identify original on-disk bytes, preserving their encoding and newline convention."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_origin(value):
    """Stable byte representation hashed in the new, close-only native request."""
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def stopped_state(ctx, passive=False, origin='release:client_stop'):
    """The enabled lease must return a release; the read-only lease must have no input call at all."""
    tracked=ctx['trackedState']
    require(ctx['telemetryComplete'] is True and ctx['active'] is None and tracked['heldKeys']==[]
            and tracked['telemetryIncomplete'] is False, 'Terminal map control is not empty')
    if passive:
        require(ctx['events']==[] and ctx['lastSequence']==0 and ctx['lastInputEvent'] is None
                and tracked['releaseOutcome']=='not_requested', 'Passive stream issued a native input call')
    else:
        final=ctx['lastInputEvent']
        require(tracked['releaseOutcome']=='returned_unverified' and final['origin']==origin
                and final['call']['operation']=='releaseAll' and final['call']['stage']=='returned_unverified'
                and final['call']['error'] is None, 'Missing original tracked releaseAll')


def sole_pulse(n, action, key):
    """Join the only permitted menu pulse to every original native callback across the fenced interval."""
    initial,final=n['initialExecutionContext'],n['finalExecutionContext']
    stopped_state(initial,origin='release:client_release')
    stopped_state(final,origin='release:client_release')
    history=initial['events']
    require(0<len(history)==initial['lastSequence'] and history[-1]==initial['lastInputEvent']
            and all(e['sequence']==i and e.get('requestId') is None and e['origin'].startswith('release:')
                    and e['call']['operation']=='releaseAll' for i,e in enumerate(history,1)),
            'Unaccounted input preceded the fenced controller transaction')
    require(len(n['inputs'])==1 and n['ordinaryRequestsWhileFenced']==0, 'Unexpected normal or extra menu request')
    a=n['inputs'][0]
    require(a['action']==action and a['key']==key and a['outcome']=='released'
            and n['startedTicks']<a['requestedTicks']<a['releasedTicks']<=n['deadlineTicks'],
            'Missing one returned native menu pulse')
    seq=initial['lastSequence']
    events=[e for e in final['events'] if e['sequence']>seq]
    require(0<len(events)==final['lastSequence']-seq<=256 and len(events)%2==0
            and all(e['sequence']==i for i,e in enumerate(events,seq+1))
            and all(x['atMs']<=y['atMs'] for x,y in zip(events,events[1:])),
            'Truncated or regressing native input history')
    ops=[]
    ids=set()
    for start,end in zip(events[::2],events[1::2]):
        x,y=start['call'],end['call']
        op=x['operation']
        require(x['callId'] not in ids and x['stage']=='started' and y['stage']==('returned_unverified' if op=='releaseAll' else 'returned')
                and x['error'] is None and y['error'] is None and start.get('requestId') is None and end.get('requestId') is None
                and all(x[k]==y[k] for k in ('callId','operation','key','mouseDx','mouseDy')) and x['mouseDx']==x['mouseDy']==0
                and start['origin']==end['origin'] and start['origin']!='dispatch', 'Foreign, failed or duplicate input call')
        ids.add(x['callId'])
        if op=='releaseAll':
            continue
        require(start['origin']=='mapInspection' and x['key']==key and all(a['requestedTicks']-1<=
                n['originTicks']+round(e['atMs']*n['frequency']/1000)<=a['releasedTicks']+1 for e in (start,end)),
                'Native input belongs to another transaction')
        ops.append(op)
    require(ops==['keyDown','keyUp'] and final['lastInputEvent']==events[-1]
            and events[-1]['call']['operation']=='releaseAll', 'Expected exactly one key press and release')
    return a


def bounded_owner_job(folder, identity, run, *, passive):
    """Join the broker result, original job argv, process nonces, temperature stream and run terminal."""
    broker=read(folder/'broker.json')
    path=Path(broker['jobFile']).resolve(strict=True)
    require(path.parent==(folder/'jobs').resolve() and path.name==broker['jobId']+'.job.json', 'Broker references another job')
    job=read(path)
    r,c=identity['root'],identity['child']
    binds=[s.split('=',1)[1].split(':') for s in job['argv'] if s.startswith('--patrol-series-binding=')]
    require(len(binds)==1 and len(binds[0])==5 and binds[0][:4]==[str(r['processId']),r['instanceNonce'],str(c['processId']),c['instanceNonce']]
            and job['jobId']==broker['jobId'] and job['windowsSessionId']==broker['windowsSessionId']==run['windowsSessionId']==c['windowsSessionId']
            and broker['remoteDesktop'] is True and broker['timedOut'] is False and broker['success'] is passive
            and broker['returnCode']==int(not passive) and run['inputRequested'] is not passive and run['acceptedInputActions']==0,
            'Broker run does not belong to the original R58 Windows lease')
    start,end=(datetime.fromisoformat(broker[k]) for k in ('startedAtUtc','endedAtUtc'))
    temps=[json.loads(line) for line in (folder/'gpu.jsonl').read_bytes().splitlines()]
    ts=[datetime.fromisoformat(t['atUtc']) for t in temps]
    require(len(temps)>=2 and start<end and ts[0]<=start and abs((end-ts[-1]).total_seconds())<6
            and all(0<(b-a).total_seconds()<=6 for a,b in zip(ts,ts[1:]))
            and all(not t.get('error') and 0<t['temperatureC']<78 for t in temps), 'Thermal coverage missing for original map proof')
    return broker


def verify_failed_map_origin(failure_folder, passive_folder, owner_receipt, repo):
    """Prove one released R58 M, followed by a fresh positively identified map on a separate read-only lease."""
    f,p,o=(Path(path).resolve(strict=True) for path in (failure_folder,passive_folder,owner_receipt))
    require(all(path.is_relative_to((repo/'artifacts/live').resolve()) for path in (f,p,o)) and f!=p,
            'Origin must be the retained public evidence of two different SIREN jobs')
    owner=load_map_owner(o)
    lineage=read(o)
    require(lineage.get('kind')=='idle-map-child-replacement' and Path(lineage['prior']).name=='warm-launcher.json'
            and 'priorLineageSha256' not in lineage,'R58 origin requires its original verified replacement lineage')
    tx=read(f/'map-inspection/transaction.json')
    n=tx['inspection']
    fr=read(f/'patrol.json')
    warm=read(f/'warm-launcher.json')
    require(fr['status']=='failed' and fr['endReason']=='error' and tx['status']=='failed' and warm['status']=='stopped'
            and tx['identity']==warm['identity']==read(f/'map-required-owner.json')==owner and tx['runId']==fr['runId']
            and not (f/'STOP').exists() and not warm['verifiedHandoffs'] and read(f/'launcher.json')['stopReason'] is None,
            'Original failure or pinned owner changed')
    fb=bounded_owner_job(f,owner,fr,passive=False)
    fc=bridge_clock([{'hello':tx['hello']}])
    require(n['requestId']==tx['requestId'] and all(n[k]==v for k,v in fc.items()) and n['phase']=='failed'
            and n['reason']=='map_source_stale' and tx['error'].endswith('map_source_stale') and len(n['before'])==3
            and n['map']==[] and n['returned']==[] and tx['abort']['type']=='stopped' and not tx['abort']['receipts'],
            'Origin is not the proved pre-Escape source-staleness failure')
    junction_poses(n['before'])
    clocks=[source_ticks(row,fc['originTicks'],fc['frequency']) for row in n['before']]
    require(len({r['captureEpoch'] for r in n['before']})==1 and all(a['frameId']<b['frameId'] for a,b in zip(n['before'],n['before'][1:]))
            and n['startedTicks']<=min(clocks[0]) and n['deadlineTicks']-n['startedTicks']==12*fc['frequency']
            and all(min(b[i]-a[i] for i in (0,1))*1000>=80*fc['frequency'] for a,b in zip(clocks,clocks[1:])),
            'Original source poses do not establish a stationary junction')
    pulse=sole_pulse(n,'openMap','M')
    last=n['before'][-1]
    require(pulse['frameId']==last['frameId'] and clocks[-1][1]<=pulse['requestedTicks']
            and (pulse['requestedTicks']-min(clocks[-1]))*1000<=150*fc['frequency'], 'Stale pre-open R58 source')
    stopped_state(tx['abort']['executionContext'])
    ending=tx['abort']['executionContext']
    tail=[e for e in ending['events'] if e['sequence']>n['finalExecutionContext']['lastSequence']]
    require(len(tail)==2 and tail==ending['events'][-2:] and tail[-1]==ending['lastInputEvent']
            and [t['call']['stage'] for t in tail]==['started','returned_unverified']
            and all(t['call']['operation']=='releaseAll' and t['origin']=='release:client_stop' for t in tail),
            'Additional input after the original failure')
    img=f/'map-inspection'/f"native-{last['frameId']}.png"
    im=original_png(img,last['sha256'],NATIVE_SIZE)
    require(not known_map(map_scores(im,repo)) and len(tx['images'])==1 and tx['images'][0]['sha256']==last['sha256']
            and tx['images'][0]['frameId']==last['frameId'] and tx['images'][0]['requestId']==n['requestId'],
            'Initial native junction witness differs from its original image')
    head=LandmarkRecognizer.load(repo/'artifacts/agent/landmarks/gen-04.json')
    require(head.checkpoint_id==G4_SHA256,'R58 G4 digest changed')
    require_qualified_observer(repo/'artifacts/agent/landmarks/qualify-g4-fresh-10.json',head)
    release=tx['release']
    require(release['type']=='released' and release['executionContext']['lastInputEvent']==n['initialExecutionContext']['lastInputEvent'],
            'Pre-open junction release differs')
    g4=g4_witness(tx['g4']['before'],f/'map-inspection',head,n,'before',
                  dict(atMs=release['serverNowMs'],epoch=release['worldReadiness']['epoch']),verify_hello(tx['hello'],P2P_NATIVE,'open-p2p'))
    pr=read(p/'patrol.json')
    pb=bounded_owner_job(p,owner,pr,passive=True)
    sup=read(p/'supervision.json')
    part=read(p/'patrol-segments/00001.json')
    pc=bridge_clock([part])
    require(sup['identity']==owner and sup['runId']==pr['runId'] and sup['stopReason'] is None and sup['stopRequested'] is False
            and pr['status']=='completed' and pr['endReason']=='durationElapsed' and len(pr['segments'])==1
            and Path(pr['segments'][0]['report']).resolve()==(p/'patrol-segments/00001.json').resolve()
            and part['hello']['inputEnabled'] is False and part['decisions']==part['receipts']==[] and part['stop']['type']=='stopped'
            and pc['sessionId']!=fc['sessionId'] and pc['ownerEpoch']!=fc['ownerEpoch'] and pr['runId']!=fr['runId']
            and pc['frequency']==fc['frequency'] and pc['originTicks']>pulse['releasedTicks']
            and datetime.fromisoformat(fb['endedAtUtc'])<datetime.fromisoformat(pb['startedAtUtc']), 'Wrong or overlapping passive verifier')
    stopped_state(part['stop']['executionContext'],passive=True)
    source=read(p/'original-map-source.json')
    diag=part['readinessDiagnosticsBeforeStop']
    src=source['sourceFrame']
    mt=source_ticks(dict(frameId=source['frameId'],worldReadiness=source['worldReadiness'],captureEpoch=src['captureEpoch'],
                         timestamp100ns=src['timestamp100ns'],acquiredAtMs=src['acquiredAtMs']),pc['originTicks'],pc['frequency'])
    png=p/'original-map.png'
    im=original_png(png,source['imageSha256'],NATIVE_SIZE)
    scores=map_scores(im,repo)
    summary=read(p/'map-match.json')
    require(summary['matched'] is True and summary['sessionId']==pc['sessionId'] and summary['sha256']==source['imageSha256']
            and all(abs(scores[k]-summary['scores'][k])<1e-5 for k in scores),
            'Passive map result disagrees with the independent original pixel replay')
    frames=[json.loads(line) for line in (p/'recording/00001/frames.jsonl').read_bytes().splitlines()]
    # GraphicsCapture.Start generates this epoch for its single HWND-specific capture item and regenerates it on restart.
    require(src['captureEpoch']==last['captureEpoch'] and known_map(scores)
            and source['evidence']=='HudMissing' and not source['worldReadiness']['ready']
            and source['sourceTimestampKind']=='wgc_reported_compositor_qpc' and source['worldReadiness']['reason']=='world_hud_missing'
            and (source['sourceWidth'],source['sourceHeight'])==NATIVE_SIZE and min(mt)>pulse['releasedTicks']
            and 0<=source['worldReadiness']['checkedAtMs']-src['freshnessAtMs']<=150
            and Path(diag['directory']).resolve()==(repo/'artifacts/release-r58/BetterGI-English-win-x64/User/AgentDiagnostics'/pc['sessionId']).resolve()
            and diag['written']==diag['admitted']==1 and diag['failed']==diag['pending']==diag['dropped']==0
            and diag['bytesWritten']==png.stat().st_size+(p/'original-map-source.json').stat().st_size
            and frames and all(row['sourceFrame']['captureEpoch']==src['captureEpoch'] and row['inputAvailable'] is False for row in frames)
            and any(row['frameId']>=source['frameId'] and row['sourceFrame']['timestamp100ns']>=src['timestamp100ns'] for row in frames),
            'Passive pixels do not prove an original map on the later read-only stream')
    return dict(version=1,kind='released-r58-open-and-passive-map',failureFolder=str(f),passiveFolder=str(p),
                ownerReceipt=str(o),ownerSha256=digest(o),identity=owner,failureRunId=fr['runId'],passiveRunId=pr['runId'],
                inputSession=fc['sessionId'],passiveSession=pc['sessionId'],failureRequestId=n['requestId'],
                failureTransactionSha256=digest(f/'map-inspection/transaction.json'),passiveSourceSha256=digest(p/'original-map-source.json'),
                mapPngSha256=source['imageSha256'],mapScores={k:round(v,6) for k,v in scores.items()},
                openReleasedTicks=pulse['releasedTicks'],mapCapturedTicks=mt[0],junctionPose=last['navigationPose'],junctionG4=g4,
                captureEpoch=src['captureEpoch'],inputLeaseSoftwareReleased=True,passiveExit='input-disabled-empty',fullMapVisit=False)


def validate_native_recovery(inspection,hello,prior_sha):
    """Pre-walk guard for the close-only command. This checks native receipts without image IO or a model load."""
    try:
        n=inspection
        caps=hello['mapInspection']
        clock=bridge_clock([{'hello':hello}])
        hz,origin=clock['frequency'],clock['originTicks']
        require(type(prior_sha) is str and len(prior_sha)==64 and all(c in '0123456789abcdef' for c in prior_sha)
                and n['priorEvidenceSha256']==prior_sha and n['mode']=='recovery' and n['version']==caps['version']==caps['recoveryVersion']==1
                and hello['inputEnabled'] is True and caps['inputChannel']=='original-game-hwnd' and caps['wgcOnly'] is True
                and all(type(caps[k]) is int and caps[k]>0 and n[k]==caps[k] for k in ('gameProcessId','gameWindowHandle'))
                and n['phase']=='completed' and n.get('reason') in (None,'completed') and all(n[k]==v for k,v in clock.items())
                and n['startedTicks']>=origin>0 and hz>0 and n['deadlineTicks']-n['startedTicks']==12*hz
                and len(n['requestId'])==32 and all(c in '0123456789abcdef' for c in n['requestId'])
                and n['before']==[] and len(n['map'])==2 and len(n['returned'])==3 and n['pendingActions']==0,
                'Wrong recovery origin, owner, window, mode or terminal state')
        menu,world=n['map'],n['returned']
        rows=menu+world
        times=[source_ticks(r,origin,hz) for r in rows]
        require(all((r['width'],r['height'])==NATIVE_SIZE and r['captureEpoch']==rows[0]['captureEpoch'] for r in rows)
                and all(a['frameId']<b['frameId'] for a,b in zip(rows,rows[1:]))
                and all(a[0]<b[0] and a[1]<b[1] for a,b in zip(times,times[1:]))
                and (min(times[0])-n['startedTicks'])*1000>=80*hz and max(times[-1])<=n['deadlineTicks']
                and all(r['knownMap'] is True and r['worldReadiness']['ready'] is False
                        and r['worldReadiness']['reason']=='world_hud_missing' for r in menu),
                'Map recovery lacks fresh positive UI sources, or the stream changed')
        for i,spacing in ((0,30),(2,80),(3,80)):
            require(all((times[i+1][j]-times[i][j])*1000>=spacing*hz for j in (0,1)),
                    'Recovery source or acquisition clock did not advance')
        junction_poses(world)
        for row in (menu[-1],world[-1]):
            require(len(row['sha256'])==64 and all(c in '0123456789abcdef' for c in row['sha256']),
                    'Missing original recovery image identity')
        esc=sole_pulse(n,'closeMap','ESCAPE')
        require(esc['frameId']==menu[-1]['frameId'] and times[1][1]<=esc['requestedTicks']
                and (esc['requestedTicks']-min(times[1]))*1000<=150*hz and (min(times[2])-esc['releasedTicks'])*1000>=80*hz,
                'Escape lacks fresh trigger or later independent HUD response')
        rearm=n['finalReadiness']
        require(rearm['ready'] is False and rearm['reason']=='client_release' and rearm['epoch']>world[-1]['worldReadiness']['epoch']
                and world[-1]['acquiredAtMs']<=n['finalExecutionContext']['lastInputEvent']['atMs']<=n['finalReleaseAtMs']
                and origin+round(n['finalReleaseAtMs']*hz/1000)<=n['deadlineTicks'], 'Missing close-only release boundary')
        return rows
    except (KeyError,TypeError,OverflowError,IndexError) as exc:
        raise ValueError('Incomplete native recovery evidence') from exc


def verify_return_position(prior,rows):
    """The protected new game must return at the actual previous junction position and camera angle."""
    for row in rows:
        pose=row['navigationPose']
        require(pose['layerId']==prior['layerId'] and math.dist((pose['x'],pose['y']),(prior['x'],prior['y']))<=1.5
                and abs((pose['yawDegrees']-prior['yawDegrees']+180)%360-180)<=3,
                'Recovered HUD does not match the last original R58 junction pose')


def audit_recovery_visit(folder,owner_from,checkpoint,qualification,repo):
    """Replay the R58 source and separately owned R59 close, junction relocalization and subsequent walking."""
    folder=Path(folder).resolve(strict=True)
    directory=folder/'map-inspection'
    origin_path=folder/'map-recovery-origin.json'
    raw=origin_path.read_bytes()
    prior=json.loads(raw)
    actual=verify_failed_map_origin(prior['failureFolder'],prior['passiveFolder'],prior['ownerReceipt'],repo)
    require(raw==canonical_origin(actual),'The exact bytes sent to the new native controller do not match R58 evidence')
    sha=hashlib.sha256(raw).hexdigest()
    owner=load_map_owner(owner_from)
    lin=read(owner_from)
    require(Path(lin['prior']).resolve()==Path(actual['ownerReceipt']) and lin['priorLineageSha256']==actual['ownerSha256']
            and owner['root']==actual['identity']['root'] and owner['child']['windowsSessionId']==actual['identity']['child']['windowsSessionId']
            and owner['child']['processId']!=actual['identity']['child']['processId']
            and owner['child']['instanceNonce']!=actual['identity']['child']['instanceNonce'],'Recovery does not use the direct R59 replacement')
    warm=read(folder/'warm-launcher.json')
    run=read(folder/'patrol.json')
    tx=read(directory/'transaction.json')
    n=tx['inspection']
    require(tx['runId']==run['runId'] and tx['requestId']==n['requestId']!=actual['failureRequestId']
            and n['sessionId'] not in (actual['inputSession'],actual['passiveSession'])
            and n['gameProcessId']==lin['protectedGame']['processId'] and n['originTicks']>actual['mapCapturedTicks']
            and tx['identity']==warm['identity']==owner and not (folder/'STOP').exists() and not tx.get('abort') and not tx.get('error')
            and tx['status']=='returnedToJunction' and tx['mode']=='recovery' and tx['priorEvidenceSha256']==sha,
            'Recovery is stopped, from another game or linked to another run')
    first=read(Path(run['segments'][0]['report']))
    require(tx['hello']==first['hello'],'Recovery and walking used different original streams')
    validate_native_recovery(n,tx['hello'],sha)
    verify_return_position(actual['junctionPose'],n['returned'])
    initial=tx['release']
    require(initial['type']=='released' and initial['worldReadiness']['ready'] is False and initial['worldReadiness']['reason']=='client_release'
            and initial['executionContext']['lastInputEvent']==n['initialExecutionContext']['lastInputEvent']
            and not initial.get('droppedReceipts') and not any(r.get('requestId') for r in initial.get('receipts',[])), 'Missing initial release')
    require(len(tx['images'])==2 and set(tx['g4'])=={'returned'},'Missing R59 originals or fabricated pre-open junction')
    scores={}
    for group,meta in zip(('map','returned'),tx['images']):
        row=n[group][-1]
        path=directory/f"native-{row['frameId']}.png"
        require(meta['type']=='mapInspectionImage' and meta['requestId']==n['requestId'] and meta['frameId']==row['frameId']
                and meta['sha256']==row['sha256'] and meta['payloadBytes']==path.stat().st_size,'Wrong original R59 image')
        scores[group]=map_scores(original_png(path,row['sha256'],NATIVE_SIZE),repo)
        require(known_map(scores[group])==(group=='map'),'Recovered-map classification disagrees with the original PNG pixels')
    head=LandmarkRecognizer.load(checkpoint)
    require(head.checkpoint_id==G4_SHA256,'Wrong recovery landmark detector')
    require_qualified_observer(qualification,head)
    g4=g4_witness(tx['g4']['returned'],directory,head,n,'returned',dict(atMs=n['finalReleaseAtMs'],epoch=n['finalReadiness']['epoch']),
                  verify_hello(first['hello'],P2P_NATIVE,'open-p2p'))
    from destination_batch_sender import admitted_plans
    plan=read(folder/'photo-requests.json')
    route=audit_photo_handoff(folder/'patrol.json',folder/'patrol-recording',repository=repo,photo_root=folder/'station-photos',
                              requests=plan,landmark_checkpoint=checkpoint,qualification=qualification,
                              batch_plans=admitted_plans(folder) if warm.get('batchCount') else None)
    require(route['runId']==tx['runId'] and route['rootPid']==owner['root']['processId'] and route['childPid']==owner['child']['processId']
            and route['windowsSessionId']==owner['child']['windowsSessionId'],'Wrong owner on walking receipts')
    lamp=resumed_goal(route,n,g4)
    require(len(route['requests'])==2 and route['requests'][1]['start']=='west-lamp' and route['requests'][1]['destination']==JUNCTION
            and route['requests'][1]['complete'] is True and route['requests'][1]['photos']['decodedStation']==JUNCTION,
            'Separate recovery route did not finish its return to the junction')
    starts=[e for e in first['hybridNavigationEvents'] if e['type']=='hybridStartVerified']
    require(len(starts)==1 and starts[0]['station']==JUNCTION and starts[0]['toStation']=='west-lamp'
            and starts[0]['sourceEpoch']==g4['captureEpoch'] and len(starts[0]['samples'])==3
            and all(s['frameId']>=g4['frameId'] and n['originTicks']+round(s['atMs']*n['frequency']/1000)>=g4['capturedTicks']
                    for s in starts[0]['samples']), 'Walking did not restart at the newly proved return')
    for segment in run['segments']:
        part=read(Path(segment['report']))
        require(all(e['frameId']>=g4['frameId'] for e in [*part['decisions'],*part.get('navigationClimbActions',[])]),
                'Ordinary action proposed before the recovered junction')
    return dict(passed=True,scope='recovery-only-prior-map-to-junction-and-first-west-lamp',runId=run['runId'],requestId=n['requestId'],
                gameProcessId=n['gameProcessId'],gameWindowHandle=n['gameWindowHandle'],priorEvidenceSha256=sha,
                mapOpenCount=0,mapCloseCount=1,fullMapVisit=False,softwareReleaseVerified=True,physicalExecutionProven=False,
                knownMapFrame=n['map'][-1]['frameId'],nativeMarkerScores=scores,returned=g4,westLampFrame=lamp,routeLegs=route['verifiedLegs'])
