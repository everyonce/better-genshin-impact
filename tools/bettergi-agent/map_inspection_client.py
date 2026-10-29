"""Inspect the junction map once, on the already owned navigation stream, before walking."""
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from PIL import Image

from hybrid_routes import PATROL_STATIONS
from observation_profiles import verify_frame
from observation_timing import observation_timestamp


def require(condition, message):
    """An incomplete UI transition can never start a walking policy."""
    if not condition:
        raise ValueError(message)


def junction_sample(frame, pixels, observer, after_ms, epoch, readiness_epoch):
    """Gate the original RGB192 G4 image on a fresh native world pose at the named junction."""
    pose, motion = frame.get('navigationPose') or {}, frame.get('motionEvidence') or {}
    source = frame.get('sourceFrame') or {}
    world, captured = frame.get('worldReadiness') or {}, frame.get('frameWorldReadiness') or {}
    if not (frame.get('inputAvailable') is True and world.get('ready') is True and captured.get('ready') is True
            and world.get('epoch') == captured.get('epoch') == readiness_epoch
            and captured.get('sourceFrameId') == frame['frameId'] and captured.get('sourceFrame') == source
            and pose.get('state') == 'valid' and pose.get('frameId') == frame['frameId'] and pose.get('layerId') == 'City_102'
            and motion.get('status') == 'normal' and motion.get('spaceKeyMatched') is False
            and source.get('captureEpoch') and (epoch is None or source['captureEpoch'] == epoch)
            and 0.99 <= pose['positionConfidence'] <= 1 and .2 <= pose['yawConfidence'] <= 1
            and math.dist((pose['x'],pose['y']), PATROL_STATIONS['sidewalk-junction']) <= 2
            and math.isfinite(pose['yawDegrees'])):
        return False
    stamp = observation_timestamp(frame)
    return (after_ms + 80 <= stamp <= frame['serverNowMs'] <= stamp + 150
            and observer.predict(pixels)['station'] == 'sidewalk-junction')


def stationary(frame, previous):
    """Every admitted source must remain in the same settled world pose and capture generation."""
    a,b = frame['navigationPose'],previous['navigationPose']
    return (frame['sourceFrame']['captureEpoch'] == previous['sourceFrame']['captureEpoch']
            and frame['worldReadiness']['epoch'] == previous['worldReadiness']['epoch']
            and frame['sourceFrame']['timestamp100ns'] > previous['sourceFrame']['timestamp100ns']
            and math.dist((a['x'],a['y']),(b['x'],b['y'])) <= 1.5
            and abs((a['yawDegrees']-b['yawDegrees']+180)%360-180) <= 3)


def collect_junction(bridge, folder, label, observer, contract, after_ms, epoch, readiness_epoch, check, deadline, anchor_pose=None):
    """Collect three separated positive poses, keeping the actual wire pixels of the final G4 photo."""
    samples = []
    while time.monotonic() < deadline:
        check()
        frame,pixels = bridge.request('frame')
        if frame.get('type') == 'frame':
            verify_frame(frame,pixels,contract)
            require((frame.get('sourceWidth'),frame.get('sourceHeight'))==(1920,1080),
                    'Map pixel replay requires the surveyed 1920x1080 source geometry')
            require(not frame.get('droppedReceipts') and not any(r.get('requestId') for r in frame.get('receipts',[])),
                    'Unexpected ordinary action receipt during map inspection')
            pose=frame.get('navigationPose') or {}
            if not junction_sample(frame,pixels,observer,after_ms,epoch,readiness_epoch):
                samples.clear()
            elif anchor_pose and (math.dist((pose['x'],pose['y']),(anchor_pose['x'],anchor_pose['y']))>1.5
                    or abs((pose['yawDegrees']-anchor_pose['yawDegrees']+180)%360-180)>3):
                raise ValueError('Post-map G4 observation moved away from the native returned pose')
            elif not samples or frame['frameId'] > samples[-1]['frameId']:
                if samples and not all(stationary(frame,other) for other in samples):
                    samples.clear()
                if not samples or observation_timestamp(frame)-observation_timestamp(samples[-1]) >= 80:
                    samples.append(frame)
                if len(samples) == 3:
                    image = folder/(label+'.png')
                    with image.open('xb') as out:
                        Image.frombytes('RGB',(192,192),pixels).save(out,'PNG')
                    return dict(frame=frame,samples=samples,png=image.name,sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                                rgbSha256=hashlib.sha256(pixels).hexdigest())
        time.sleep(.025)
    raise ValueError('Timed out waiting for three fresh G4 junction observations: '+label)


def warm_recovery_capture(bridge, contract, after_ms, check, deadline):
    """Wait for the new recognizer to publish two fresh HUD-missing WGC frames before starting the native timer."""
    previous = None
    while time.monotonic() < deadline:
        check()
        frame, pixels = bridge.request('frame')
        if frame.get('type') == 'frame':
            verify_frame(frame, pixels, contract)
            source = frame.get('sourceFrame') or {}
            world = frame.get('frameWorldReadiness') or {}
            pose = frame.get('navigationPose') or {}
            require(not frame.get('droppedReceipts') and not any(r.get('requestId') for r in frame.get('receipts', [])),
                    'Unexpected ordinary action during recovery warmup')
            require((frame.get('sourceWidth'), frame.get('sourceHeight')) == (1920, 1080), 'Unexpected recovery geometry')
            stamp = observation_timestamp(frame)
            if (source.get('captureEpoch') and world.get('ready') is False and world.get('reason') == 'world_hud_missing'
                    and world.get('sourceFrameId') == frame['frameId'] and world.get('sourceFrame') == source
                    and pose.get('frameId') == frame['frameId'] and pose.get('reason') == 'world_not_ready'
                    and after_ms + 80 <= stamp <= frame['serverNowMs'] <= stamp + 150):
                if previous is None:
                    previous = frame
                else:
                    require(previous['sourceFrame']['captureEpoch'] == source['captureEpoch'], 'Recovery capture epoch changed')
                    if (frame['frameId'] > previous['frameId'] and source['timestamp100ns'] > previous['sourceFrame']['timestamp100ns']
                            and stamp >= observation_timestamp(previous) + 30):
                        return [previous, frame]
            else:
                previous = None
        time.sleep(.025)
    raise ValueError('Cold recovery stream did not produce two fresh navigation observations')


def retain_images(bridge, folder, proof, record, check):
    """Retrieve only the original PNGs actually retained by this terminal operation, including a failed prefix."""
    saved={row['frameId'] for row in record['images']}
    for phase in ('before','map','returned'):
        rows=proof.get(phase) or []
        if not rows or not rows[-1].get('sha256') or rows[-1]['frameId'] in saved:
            continue
        check()
        row=rows[-1]
        header,data=bridge.request('mapInspectionImage',requestId=proof['requestId'],frameId=row['frameId'])
        require(header.get('type')=='mapInspectionImage' and header.get('requestId')==proof['requestId']
                and header.get('frameId')==row['frameId'] and header.get('payloadBytes')==len(data)
                and hashlib.sha256(data).hexdigest()==header.get('sha256')==row['sha256'],'Original map image changed')
        with (folder/f"native-{row['frameId']}.png").open('xb') as out:
            out.write(data)
        record['images'].append(header)


def inspect_before_navigation(bridge, args, policy, control, profile):
    """Drive only the fixed native transaction and leave no ordinary proposals or stale model history across it."""
    from audit_map_inspection import validate_native_transaction
    from landmark_recognizer import G4_SHA256
    root = Path(args.warm_photo_plan).parent
    folder = root/'map-inspection'
    folder.mkdir(exist_ok=False)
    hello = bridge.hello
    identity=json.loads((root/'map-required-owner.json').read_bytes())
    recovery=getattr(args,'recover_junction_map',False)
    record = dict(version=1,mode='recovery' if recovery else 'inspection',runId=control.run_id,
                  identity=identity,hello=hello,g4={},images=[],status='failed')
    token = control.prediction_token()
    deadline = min(time.monotonic()+30,args.lease_deadline)

    def check():
        """Observe the existing addressed operator, thermal and ownership stop and the local bounded deadline."""
        require(time.monotonic() < deadline and not (root/'STOP').exists() and control.prediction_token()==token
                and control.snapshot()==('run',None),'Map inspection interrupted by its deadline or owner control')

    try:
        require((hello.get('mapInspection') or {}).get('version')==1 and hello['inputEnabled'] is True
                and policy.landmark_shadow.checkpoint_id == G4_SHA256 and profile['profile']=='p2p-native-hamming-192-v1',
                'This visit requires the native map capability, qualified G4 and RGB192')
        cap=hello['mapInspection']
        if cap.get('recoveryVersion')==1 or recovery:
            game=json.loads((root/'map-required-game.json').read_bytes())
            require(game['windowsSessionId']==identity['child']['windowsSessionId'] and game['processId']==cap['gameProcessId']
                    and type(cap.get('gameWindowHandle')) is int and cap['gameWindowHandle']>0,
                    'Map operation does not own the game retained across child replacement')
            record['protectedGame']=game
        check()
        released,empty=bridge.request('release')
        require(not empty and released.get('type')=='released' and not released.get('droppedReceipts')
                and not any(r.get('requestId') for r in released.get('receipts',[])), 'Missing clean initial release')
        record['release']=released
        if recovery:
            require(hello['mapInspection'].get('recoveryVersion')==1,'Missing native one-shot recovery capability')
            origin=(root/'map-recovery-origin.json').read_bytes()
            require(0<len(origin)<=65536,'Missing bounded interrupted-map evidence')
            record['priorEvidenceSha256']=hashlib.sha256(origin).hexdigest()
            record['warmCapture']=warm_recovery_capture(bridge,profile,released['serverNowMs'],check,min(deadline,time.monotonic()+15))
        else:
            before=collect_junction(bridge,folder,'before',policy.landmark_shadow,profile,released['serverNowMs'],None,
                                    released['worldReadiness']['epoch'],check,min(deadline,time.monotonic()+8))
            record['g4']['before']=before
        request_id=uuid.uuid4().hex
        record['requestId']=request_id
        check()
        command='recoverJunctionMap' if recovery else 'inspectJunctionMap'
        extra={'priorEvidenceSha256':record['priorEvidenceSha256']} if recovery else {}
        allowed,response=control.guarded_submit(token,lambda:bridge.request(command,requestId=request_id,**extra))
        require(allowed and response[0].get('type')=='mapInspectionStarted' and not response[1]
                and response[0].get('requestId')==request_id,'Native map inspection refused or not acknowledged')
        while True:
            check()
            status,empty=bridge.request('mapInspectionStatus',requestId=request_id)
            require(not empty and status.get('type')=='mapInspection','Missing native map inspection status')
            inspection=status['inspection']
            require(inspection['requestId']==request_id and all(inspection[k]==hello[k] for k in ('sessionId','ownerEpoch')),
                    'Map inspection changed its lease or request identity')
            if 'protectedGame' in record:
                require(all(inspection[k]==cap[k] for k in ('gameProcessId','gameWindowHandle')),
                        'Map operation lost its original game process or window')
            record['inspection']=inspection
            if inspection['phase']=='completed':
                break
            permitted=('awaitRecoveryMap','awaitWorld') if recovery else ('awaitJunction','awaitMap','awaitWorld')
            require(inspection['phase'] in permitted, 'Native map inspection ended: '+str(inspection.get('reason')))
            time.sleep(.025)
        if recovery:
            from audit_map_recovery import validate_native_recovery, verify_return_position
            validate_native_recovery(inspection,hello,record['priorEvidenceSha256'])
            verify_return_position(json.loads(origin)['junctionPose'],inspection['returned'])
        else:
            validate_native_transaction(inspection,hello)
        retain_images(bridge,folder,inspection,record,check)
        require(len(record['images'])==(2 if recovery else 3),'Missing original map operation images')
        after=inspection['returned'][-1]
        if not recovery:
            require(before['frame']['sourceFrame']['captureEpoch']==after['captureEpoch'], 'Map capture generation changed')
        record['g4']['returned']=collect_junction(bridge,folder,'returned',policy.landmark_shadow,profile,
                                                  inspection['finalReleaseAtMs'],after['captureEpoch'],
                                                  inspection['finalReadiness']['epoch'],check,deadline,after['navigationPose'])
        check()
        policy.reset()
        record['status']='returnedToJunction'
    except Exception as exc:
        record['error']=str(exc)
        terminal=record.get('inspection') or {}
        if terminal.get('phase') in ('failed','completed') and not (root/'STOP').exists() and control.snapshot()==('run',None):
            try:
                retain_images(bridge,folder,terminal,record,check)
            except Exception as image_error:
                record['imageError']=str(image_error)
        # The native operation is one-shot. Closing this lease never retries its map or Escape input.
        try:
            record['abort']=bridge.request('stop')[0]
        except Exception as stop_error:
            record['stopError']=str(stop_error)
        raise
    finally:
        with (folder/'transaction.json').open('x',encoding='utf-8') as out:
            json.dump(record,out,indent=2,allow_nan=False)
    return dict(requestId=request_id,returnedFrame=record['g4']['returned']['frame']['frameId'])
