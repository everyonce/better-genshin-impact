"""Reconstruct one map visit and its first subsequent walking goal from the original native evidence."""
import argparse
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from audit_hybrid_run import require
from audit_photo_handoff import audit_photo_handoff, bridge_clock, read
from hybrid_routes import PATROL_STATIONS
from landmark_recognizer import G4_SHA256, LandmarkRecognizer
from map_owner import load_map_owner
from observation_profiles import P2P_NATIVE, verify_frame, verify_hello
from observation_timing import observation_timestamp
from patrol_photo_survey import require_qualified_observer


JUNCTION = 'sidewalk-junction'
LAMP = 'west-lamp'
NATIVE_SIZE = (1920,1080)
# Native QuickTeleport Recognition.json ROIs and SHA-256 of the reviewed templates at the observed SIREN resolution.
MAP_ASSETS = {
    'MapCloseButton': ((1813,19,1871,77),'523c4a02acd67bd45c5d5fbf4eee2d0b3e264408ef98197cf47d0c7c70f05b4a'),
    'MapScaleButton': ((30,440,70,640),'18ec1ca976a1359de9967acf41828bb96795c9ac93a5cd198502746160cf6a7b'),
    'MapSettingsButton': ((25,990,83,1052),'dadfbe3595324a16a0a0f5479170c7ba58ac33b341164596d45ddb62a7ad74d3'),
}


def original_png(path, digest, size):
    """Read bounded PNG bytes once, verify their native digest and decode at original dimensions."""
    require(path.is_file() and 0 < path.stat().st_size <= 16*1024*1024, 'Missing or oversized retained PNG')
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, 'Retained PNG digest differs')
    with Image.open(BytesIO(raw)) as image:
        require(image.format == 'PNG' and (size is None or image.size == size), 'Wrong source image format or geometry')
        return image.convert('RGB')


def map_scores(image, repository):
    """Replay grayscale normalized template correlation, including the native non-black scale-button mask."""
    require(image.size == NATIVE_SIZE, 'Original 1920x1080 map pixels required')
    scores = {}
    directory = repository/'BetterGenshinImpact/GameTask/QuickTeleport/Assets/1920x1080'
    for name,(roi,digest) in MAP_ASSETS.items():
        tile = original_png(directory/(name+'.png'),digest,None)
        mask = np.any(np.asarray(tile) != 0,axis=2) if name == 'MapScaleButton' else np.ones((tile.height,tile.width),bool)
        gray = np.asarray(tile.convert('L'),dtype=np.float64)
        sample = gray[mask]
        sample -= sample.mean()
        area = np.asarray(image.crop(roi).convert('L'),dtype=np.float64)
        windows = np.lib.stride_tricks.sliding_window_view(area,gray.shape)[...,mask]
        windows -= windows.mean(axis=-1,keepdims=True)
        denominator = np.sqrt(np.sum(windows*windows,axis=-1)*np.sum(sample*sample))
        corr = np.divide(np.einsum('...i,i->...',windows,sample),denominator,
                         out=np.zeros_like(denominator),where=denominator>0)
        scores[name] = float(corr.max())
    return scores


def known_map(scores):
    """Apply the production map-or-settings plus close-button predicate to independent pixel scores."""
    return scores['MapCloseButton'] >= .8 and max(scores['MapScaleButton'],scores['MapSettingsButton']) >= .8


def source_ticks(frame, origin, hz):
    """Join WGC and acquisition evidence to native QPC without using filesystem timestamps."""
    source = frame['worldReadiness']['sourceFrame']
    require(source['captureEpoch'] == frame['captureEpoch'] and source['timestamp100ns'] == frame['timestamp100ns']
            and source['acquiredAtMs'] == frame['acquiredAtMs'] and frame['worldReadiness']['sourceFrameId'] == frame['frameId'],
            'World or UI result belongs to another source')
    captured = round(source['timestamp100ns']*hz / 10_000_000)
    acquired = origin+round(frame['acquiredAtMs']*hz/1000)
    require('freshnessAtMs' in source and 'freshnessClockKind' in source
            and observation_timestamp({'sourceFrame':source})==min(source['capturedAtMs'],source['acquiredAtMs'])
            and min(captured,acquired)>0
            and abs(captured-origin-round(source['capturedAtMs']*hz/1000)) <= 1, 'Inconsistent WGC source clock')
    return captured,acquired


def junction_poses(frames):
    """Require the same surveyed pose and world-readiness tests as the walking endpoint."""
    poses = []
    for frame in frames:
        pose = frame['navigationPose']
        state = frame['worldReadiness']
        motion = frame['motionEvidence']
        require(state['ready'] is True and state['reason']=='world_ready' and state['epoch']==frames[0]['worldReadiness']['epoch']
                and frame.get('knownMap') is False and motion['status']=='normal' and motion['spaceKeyMatched'] is False
                and pose['state']=='valid' and pose['frameId']==frame['frameId'] and pose['layerId']=='City_102'
                and .99<=pose['positionConfidence']<=1 and .2<=pose['yawConfidence']<=1
                and math.dist((pose['x'],pose['y']),PATROL_STATIONS[JUNCTION])<=2,
                'Fresh world HUD and qualified junction pose required')
        for older in poses:
            require(math.dist((pose['x'],pose['y']),(older['x'],older['y']))<=1.5
                    and abs((pose['yawDegrees']-older['yawDegrees']+180)%360-180)<=3, 'Junction pose did not settle')
        poses.append(pose)


def verify_native(proof, clock):
    """Join source, input and control boundaries for exactly one completed inspection."""
    require(proof['version']==1 and proof['phase']=='completed' and proof.get('reason') in (None,'completed')
            and len(proof['requestId'])==32 and all(proof[k]==clock[k] for k in ('originTicks','frequency','sessionId','ownerEpoch')),
            'Missing completed native map inspection in the original controller lease')
    origin,hz=clock['originTicks'],clock['frequency']
    require(type(hz) is int and hz>0 and 0 < origin <= proof['startedTicks']
            and proof['deadlineTicks']-proof['startedTicks']==12*hz, 'Invalid native inspection clock')
    before,opened,returned=(proof[k] for k in ('before','map','returned'))
    require([len(g) for g in (before,opened,returned)]==[3,2,3], 'Map transition requires three/two/three original sources')
    rows=[*before,*opened,*returned]
    times=[source_ticks(row,origin,hz) for row in rows]
    require(all((r['width'],r['height'])==NATIVE_SIZE and r['captureEpoch']==rows[0]['captureEpoch'] for r in rows)
            and all(a['frameId']<b['frameId'] for a,b in zip(rows,rows[1:]))
            and all(x[0]<y[0] and x[1]<y[1] for x,y in zip(times,times[1:]))
            and proof['startedTicks'] <= min(times[0]) and times[-1][1] <= proof['deadlineTicks'], 'Repeated, stale or foreign map sequence')
    for group in (before,returned):
        junction_poses(group)
        for left,right in zip(group,group[1:]):
            require((right['timestamp100ns']-left['timestamp100ns']) >= 800_000, 'Settled source poses less than 80ms apart')
            require(right['acquiredAtMs']-left['acquiredAtMs'] >= 80, 'Settled acquisition clocks too close')
    for later in returned:
        pa,pb=before[-1]['navigationPose'],later['navigationPose']
        require(math.dist((pa['x'],pa['y']),(pb['x'],pb['y']))<=1.5
                and abs((pa['yawDegrees']-pb['yawDegrees']+180)%360-180)<=3,'World returned at a different junction pose')
    require(all(row['knownMap'] is True and row['worldReadiness']['ready'] is False
                and row['worldReadiness']['reason']=='world_hud_missing' for row in opened)
            and opened[1]['timestamp100ns']-opened[0]['timestamp100ns']>=300_000
            and opened[1]['acquiredAtMs']-opened[0]['acquiredAtMs']>=30
            and before[-1]['worldReadiness']['epoch'] < returned[0]['worldReadiness']['epoch'],
            'Map did not revoke ordinary world authority and reestablish it')
    actions=proof['inputs']
    require([a['action'] for a in actions]==['openMap','closeMap'] and [a['key'] for a in actions]==['M','ESCAPE'],
            'Expected exactly one open and one close')
    for a,trigger,next_frame in zip(actions,(before[-1],opened[-1]),(opened[0],returned[0])):
        src=source_ticks(trigger,origin,hz)
        response=source_ticks(next_frame,origin,hz)
        require(a['frameId']==trigger['frameId'] and a['outcome']=='released' and a['key']
                and src[1] <= a['requestedTicks'] <= a['releasedTicks'] <= proof['deadlineTicks']
                and (a['requestedTicks']-min(src))*1000 <= 150*hz and
                (min(response)-a['releasedTicks'])*1000 >= 80*hz,
                'Map key receipt lacks a fresh trigger, native release or post-release response')
    return rows


def execution_interval(proof):
    """Match all native calls in the no-walking window to the two menu pulses or input release."""
    first,last=proof['initialExecutionContext'],proof['finalExecutionContext']
    for ctx in (first,last):
        require(ctx['telemetryComplete'] is True and ctx['active'] is None and ctx['trackedState']['heldKeys']==[]
                and ctx['trackedState']['telemetryIncomplete'] is False and ctx['trackedState']['releaseOutcome']=='returned_unverified'
                and ctx['lastInputEvent']['call']['operation']=='releaseAll'
                and ctx['lastInputEvent']['call']['stage']=='returned_unverified' and ctx['lastInputEvent']['call']['error'] is None,
                'Unresolved native inputs at map boundary')
    begin=first['lastSequence'] or 0
    events=[e for e in last['events'] if e['sequence']>begin]
    require(proof['pendingActions']==0 and type(proof.get('ordinaryRequestsWhileFenced')) is int
            and proof['ordinaryRequestsWhileFenced']==0 and last['trackedState']['releaseOutcome']=='returned_unverified'
            and 0<len(events)==last['lastSequence']-begin<=256 and all(e['sequence']==i for i,e in enumerate(events,begin+1))
            and events[-1]==last['lastInputEvent'], 'Native input interval is incomplete')
    operations=[]
    require(len(events)%2==0 and all(a['atMs']<=b['atMs'] for a,b in zip(events,events[1:])), 'Broken native call timeline')
    for start,end in zip(events[::2],events[1::2]):
        a,b=start['call'],end['call']
        op=a['operation']
        require(a['stage']=='started' and b['stage']==('returned_unverified' if op=='releaseAll' else 'returned')
                and a['error'] is None and b['error'] is None and
                all(a[k]==b[k] for k in ('callId','operation','key','mouseDx','mouseDy'))
                and a['mouseDx']==a['mouseDy']==0 and start['origin']==end['origin']
                and start.get('requestId') in (None,proof['requestId']) and end.get('requestId')==start.get('requestId')
                and start['origin']!='dispatch', 'Unexpected walking, mouse or failed call during map inspection')
        if op!='releaseAll':
            require(start['origin']=='mapInspection', 'Wrong native owner for map key dispatch')
            operations.append((op,a['key'],start['atMs'],end['atMs']))
    require(events[-1]['call']['operation']=='releaseAll' and len(operations)==4, 'Missing release or extra key during map visit')
    rearm=proof['finalReadiness']
    require(rearm['ready'] is False and rearm['epoch']>proof['returned'][-1]['worldReadiness']['epoch']
            and rearm['reason']=='client_release' and last['lastInputEvent']['origin']=='release:client_release'
            and proof['returned'][-1]['acquiredAtMs']<=last['lastInputEvent']['atMs']<=proof['finalReleaseAtMs']
            and proof['originTicks']+round(proof['finalReleaseAtMs']*proof['frequency']/1000)<=proof['deadlineTicks'],
            'Missing final software release or rearm boundary')
    for n,action in enumerate(proof['inputs']):
        down,up=operations[2*n:2*n+2]
        key=action['key'].removeprefix('VK_')
        key='ESCAPE' if key=='ESC' else key
        require(down[:2]==('keyDown',key) and up[:2]==('keyUp',key), 'Mapped key does not match the two original pulse receipts')
        since=lambda ms: proof['originTicks'] + round(ms*proof['frequency']/1000)
        require(action['requestedTicks']-1<=since(down[2])<=since(up[3])<=action['releasedTicks']+1,
                'Input calls fall outside their native pulse clock')


def inspection_game_target(inspection, hello):
    """Join R59's game-window input target to the stream that supplied the native source and walking frames."""
    caps=hello['mapInspection']
    require(inspection.get('mode','inspection')=='inspection' and inspection.get('priorEvidenceSha256') is None,
            'An ordinary map visit cannot be replaced by recovery evidence')
    if 'recoveryVersion' not in caps:
        require(not any(k in inspection or k in caps for k in ('gameProcessId','gameWindowHandle')),
                'Incomplete game identity on the map stream')
        return None
    require(caps['recoveryVersion']==1 and caps.get('inputChannel')=='original-game-hwnd' and caps.get('wgcOnly') is True
            and inspection.get('mode')=='inspection' and 'priorEvidenceSha256' in inspection
            and all(type(caps.get(k)) is int and type(inspection.get(k)) is int and caps[k]==inspection[k]>0
                    for k in ('gameProcessId','gameWindowHandle')), 'Wrong native game process or window on normal map input')
    return {'gameProcessId':caps['gameProcessId'],'gameWindowHandle':caps['gameWindowHandle']}


def inspection_game_lineage(tx, walking_hello, lineage, pinned_game):
    """Bind the normal R59 menu visit to the protected game lifetime from the recomputed replacement lineage."""
    require(tx['hello']['mapInspection']==walking_hello['mapInspection'],'Walking hello refers to a different game window')
    target=inspection_game_target(tx['inspection'],walking_hello)
    game=lineage.get('protectedGame')
    if game is None:
        require(target is None and 'priorLineageSha256' not in lineage and not tx.get('protectedGame') and pinned_game is None,
                'Map visit omitted the protected R59 game lifetime')
    else:
        require(target is not None and pinned_game==tx.get('protectedGame')==game and 'priorLineageSha256' in lineage
                and tx.get('mode')=='inspection' and tx.get('priorEvidenceSha256') is None
                and game['windowsSessionId']==tx['identity']['child']['windowsSessionId']
                and target['gameProcessId']==game['processId'], 'Normal map inputs did not target the game retained across R59 replacement')
    return target


def validate_native_transaction(inspection, hello):
    """Run the small, no-file pre-walk guard directly on the original native map receipt and hello."""
    try:
        require(hello.get('inputEnabled') is True and (hello.get('mapInspection') or {}).get('version')==1,
                'Native lease did not advertise bounded map inspection')
        inspection_game_target(inspection,hello)
        rows=verify_native(inspection,bridge_clock([{'hello':hello}]))
        execution_interval(inspection)
        for group in ('before','map','returned'):
            sha=inspection[group][-1]['sha256']
            require(len(sha)==64 and all(c in '0123456789abcdef' for c in sha), 'Missing native capture digest')
        return rows
    except (KeyError,TypeError,OverflowError,IndexError) as exc:
        raise ValueError('Incomplete native inspection receipt') from exc


def g4_witness(snapshot, directory, head, inspection, group, release, profile):
    """Replay a wire RGB192 photo and bind its frame/pose to the same capture and native lease clock."""
    frame=snapshot['frame']
    img_name=snapshot['png']
    require(isinstance(img_name,str) and Path(img_name).name==img_name and img_name.endswith('.png'), 'Invalid junction photo basename')
    pix=original_png(directory/img_name,snapshot['sha256'],(192,192))
    verify_frame(frame,pix.tobytes(),profile)
    require(hashlib.sha256(pix.tobytes()).hexdigest()==snapshot['rgbSha256'] and head.predict(pix.tobytes())['station']==JUNCTION,
            'Exact G4 wire photo does not show the junction')
    anchor=inspection[group][0 if group=='before' else -1]
    orig,hz=inspection['originTicks'],inspection['frequency']
    samples=snapshot['samples']
    require(len(samples)==3 and frame==samples[-1], 'Missing original three-pose G4 witness')
    barrier=orig+round(release['atMs']*hz/1000)
    rows=[]
    previous=None
    for sample in samples:
        src=sample['sourceFrame']
        row=dict(frameId=sample['frameId'],captureEpoch=src['captureEpoch'],timestamp100ns=src['timestamp100ns'],
                 acquiredAtMs=src['acquiredAtMs'],worldReadiness=sample['frameWorldReadiness'],
                 navigationPose=sample['navigationPose'],motionEvidence=sample['motionEvidence'],knownMap=False)
        require(src['captureEpoch']==anchor['captureEpoch'] and sample.get('inputAvailable') is True
                and (sample['sourceWidth'],sample['sourceHeight'])==NATIVE_SIZE
                and sample['worldReadiness']['ready'] is True and row['worldReadiness']['sourceFrame']==src
                and row['worldReadiness']['epoch']==sample['worldReadiness']['epoch']==release['epoch']
                and not sample.get('droppedReceipts') and not any(r.get('requestId') for r in sample.get('receipts',[])),
                'G4 witness changed owner readiness or capture source')
        cap,acq=source_ticks(row,orig,hz)
        read_at=orig+round(sample['serverNowMs']*hz/1000)
        require(acq<=read_at and (read_at-min(cap,acq))*1000<=150*hz and
                (min(cap,acq)-barrier)*1000>=80*hz,'Stale G4 witness')
        if previous is not None:
            require(row['frameId']>rows[-1]['frameId'] and (cap-previous)*1000>=80*hz, 'G4 sources did not advance')
        rows.append(row)
        previous=cap
    junction_poses(rows)
    pa,pb=anchor['navigationPose'],row['navigationPose']
    require(math.dist((pa['x'],pa['y']),(pb['x'],pb['y']))<=1.5
            and abs((pa['yawDegrees']-pb['yawDegrees']+180)%360-180)<=3, 'G4 capture does not join the native settled pose')
    if group=='before':
        require(row['frameId']<=anchor['frameId'] and acq<=inspection['startedTicks']
                and (inspection['startedTicks']-min(cap,acq))*1000<=150*hz, 'Pre-open photo too old for the transaction')
    else:
        require(row['frameId']>=anchor['frameId'] and cap>=source_ticks(anchor,orig,hz)[0],
                'Post-map G4 witness precedes native return')
    return dict(frameId=row['frameId'],captureEpoch=src['captureEpoch'],capturedTicks=cap,sha256=snapshot['sha256'])


def resumed_goal(route, inspection, last):
    """Refuse to credit a world return until original normal input and the first requested west-lamp photo are proven."""
    require(route['passed'] is True and route['stopVerified'] is False and route['start']==JUNCTION and route['requests'],
            'Missing independently verified route from the junction')
    goal=route['requests'][0]
    require(all(inspection[k]==route['clock'][k] for k in ('sessionId','ownerEpoch','frequency','originTicks'))
            and goal['start']==JUNCTION and goal['destination']==LAMP and goal['plannedLegs']==goal['verifiedLegs']==1
            and goal['actions']>0 and goal['complete'] is True and goal['photos']['complete'] is True
            and goal['photos']['decodedStation']==LAMP and goal['photos']['checkpointId']==G4_SHA256
            and last['frameId']<=goal['first']['frameId']<goal['photos']['frameId']
            and goal['first']['firstDispatchTicks']>last['capturedTicks'], 'West-lamp goal was not achieved after the map returned')
    return goal['photos']['frameId']


def audit_map(folder, owner_from, checkpoint, qualification, repository):
    """Replay the native UI evidence, qualified junction images, ordinary walking and final photographed arrival."""
    directory=folder/'map-inspection'
    tx=read(directory/'transaction.json')
    native=tx['inspection']
    warm=read(folder/'warm-launcher.json')
    run=read(folder/'patrol.json')
    owner=load_map_owner(owner_from)
    require(tx['runId']==run['runId'] and tx['requestId']==native['requestId'] and tx['status']=='returnedToJunction'
            and not tx.get('abort') and not tx.get('error') and tx['identity']==warm['identity']==owner and not (folder/'STOP').exists(),
            'Wrong RDP owner, stopped run or substituted map transaction')
    head=LandmarkRecognizer.load(checkpoint)
    require(head.checkpoint_id==G4_SHA256,'Map inspection requires the qualified G4 observer')
    require_qualified_observer(qualification,head)
    first=read(Path(run['segments'][0]['report']))
    require(bridge_clock([{'hello':tx['hello']}])==bridge_clock([first]),'Inspection hello has another native owner')
    lineage=read(owner_from)
    game_record=folder/'map-required-game.json'
    target=inspection_game_lineage(tx,first['hello'],lineage,read(game_record) if game_record.is_file() else None)
    profile=verify_hello(first['hello'],P2P_NATIVE,'open-p2p')
    validate_native_transaction(native,first['hello'])
    scores={}
    require(len(tx['images'])==3,'Missing original native image responses')
    for name,meta in zip(('before','map','returned'),tx['images']):
        row=native[name][-1]
        path=directory/f"native-{row['frameId']}.png"
        require(meta['type']=='mapInspectionImage' and meta['requestId']==native['requestId']
                and meta['frameId']==row['frameId'] and meta['sha256']==row['sha256'] and path.is_file()
                and path.stat().st_size==meta['payloadBytes'],'Original image response is from another source or file')
        image=original_png(path,row['sha256'],NATIVE_SIZE)
        scores[name]=map_scores(image,repository)
        require(known_map(scores[name])==(name=='map'), 'Independent map and close markers disagree with UI transition')
    initial=tx['release']
    require(initial['type']=='released' and initial['executionContext']['lastInputEvent']==native['initialExecutionContext']['lastInputEvent']
            and initial['worldReadiness']['ready'] is False and initial['worldReadiness']['reason']=='client_release'
            and not initial.get('droppedReceipts') and not any(r.get('requestId') for r in initial.get('receipts',[])),
            'Initial G4 release is missing or belongs to another action')
    before=g4_witness(tx['g4']['before'],directory,head,native,'before',
                      dict(atMs=initial['serverNowMs'],epoch=initial['worldReadiness']['epoch']),profile)
    returned=g4_witness(tx['g4']['returned'],directory,head,native,'returned',
                        dict(atMs=native['finalReleaseAtMs'],epoch=native['finalReadiness']['epoch']),profile)
    plan=read(folder/'photo-requests.json')
    from destination_batch_sender import admitted_plans
    route=audit_photo_handoff(folder/'patrol.json',folder/'patrol-recording',repository=repository,
                              photo_root=folder/'station-photos',requests=plan,landmark_checkpoint=checkpoint,
                              qualification=qualification,batch_plans=admitted_plans(folder) if warm.get('batchCount') else None)
    require(route['runId']==tx['runId'] and route['rootPid']==owner['root']['processId']
            and route['childPid']==owner['child']['processId'] and route['windowsSessionId']==owner['child']['windowsSessionId'],
            'Walking receipts have another RDP owner')
    west=resumed_goal(route,native,returned)
    starts=[e for e in first['hybridNavigationEvents'] if e['type']=='hybridStartVerified']
    require(len(starts)==1 and starts[0]['sourceEpoch']==returned['captureEpoch'] and starts[0]['station']==JUNCTION
            and starts[0]['toStation']==LAMP and len(starts[0]['samples'])==3
            and all(s['frameId']>=returned['frameId'] and native['originTicks']+round(s['atMs']*native['frequency']/1000)
                    >=returned['capturedTicks'] for s in starts[0]['samples']),
            'Walking start does not join the returned world capture')
    # The original per-part policy/receipt/proposal journal must also be wholly newer than the map window.
    for s in run['segments']:
        part=read(Path(s['report']))
        proposals=[*part['decisions'],*part.get('navigationClimbActions',[])]
        require(all(p['frameId']>=returned['frameId'] for p in proposals), 'Ordinary proposal during map transaction')
    return dict(passed=True,scope='junction-world-map-return-and-first-west-lamp',runId=tx['runId'],
                requestId=native['requestId'],before=before,returned=returned,knownMapFrame=native['map'][-1]['frameId'],
                nativeMarkerScores=scores,westLampFrame=west,routeLegs=route['verifiedLegs'],
                softwareReleaseVerified=True,physicalExecutionProven=False,**(target or {}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('folder','owner-from','landmark-checkpoint','qualification','output'):
        parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args()
    report=audit_map(args.folder,args.owner_from,args.landmark_checkpoint,args.qualification,Path(__file__).resolve().parents[2])
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print(report['scope'],args.output)
