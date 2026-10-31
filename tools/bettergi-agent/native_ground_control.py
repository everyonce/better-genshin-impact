"""Exact native ground-control layout negotiation and retained tiny-pixel replay; never physical footing."""
import base64
import copy
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from native_combat import finite,require

CAPABILITY=dict(version=1,method='native_ground_control_layout_v1',sameFrame=True,readOnly=True,
    requiresWgcSourceIdentity=True,sourceWidth=1920,sourceHeight=1080,cropFormat='rgb24',
    eRegion=dict(x=1660,y=1014,width=75,height=42),qRegion=dict(x=1775,y=1014,width=80,height=42),
    swimRegion=dict(x=1819,y=1028,width=9,height=7),swimMinimumPixels=4,maximumCropBytes=19530,
    requiresBothKeycaps=True,authorizesInput=False,physicallyGrounded=False)

# Fixed keycap masks retain distinguishable glyphs; '+' ignores antialias/corner pixels.
# These are code-sized masks from dry frame24, not an asset directory or an OCR model.
E_PATTERN=(
 '+............................+', '+.............................', '..............................',
 '..............................', '..........+++++++++...........', '..........##########..........',
 '...........###+++++#..........', '...........###................', '...........###................',
 '...........###................', '...........########...........', '...........########...........',
 '...........###................', '...........###................', '...........###................',
 '...........###................', '...........#########..........', '..........+#########..........',
 '..............................', '..............................', '..............................',
 '..............................', '..............................', '+.............................', '++..........................++')
Q_PATTERN=(
 '+............................+', '+.............................', '..............................',
 '..............................', '.............++++.............', '...........+#######...........',
 '..........####..+###..........', '.........+###....+###.........', '.........###+.....###.........',
 '.........###......###+........', '........+###......####........', '........+###......####........',
 '.........###......####........', '.........###......###+........', '.........####.....###.........',
 '..........###+...###+.........', '..........+####+####..........', '............+#####+...........',
 '...............####...........', '................###+..........', '.................###+.........',
 '..............................', '..............................', '+............................+', '++..........................++')


SOURCE_NAMES=('native_ground_control.py','scout_encounter_guard.py','scout_session.py','stream_client.py',
              'hybrid_navigation.py','reviewed_scout_route.py','resident_runtime.py',
              'capture_scout_scene.py','audit_hybrid_run.py')


def source_contract():
    """Pin this gate and existing worker/dispatch/replay boundaries without altering old source registries."""
    root=Path(__file__).absolute().parent
    return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in SOURCE_NAMES}


def policy():
    """Declare this new gate separately, preserving every historical motion/combat guard descriptor."""
    return dict(version=1,method=CAPABILITY['method'],sourceFreshnessMs=150,requiredForScoutInput=True,
        requirePostReleaseGroundControls=True,stopOnSwimHint=True,stopOnMissingWhileArmed=True,
        nativeGateRequired=True,physicallyGrounded=False)


def validate_capability(value):
    """The first version supports only the inspected fixed RDP layout and exact crop bounds."""
    require(json.dumps(value,sort_keys=True,allow_nan=False)==json.dumps(CAPABILITY,sort_keys=True),
            'Native ground-control capability changed or is unavailable')
    return copy.deepcopy(CAPABILITY)


def negotiate(bridge):
    """Enable one irreversible revocation-only gate on the existing authenticated lease."""
    contract=validate_capability(bridge.hello.get('groundControlObservation'))
    reply,payload=bridge.request('requireGroundControlLayout')
    require(isinstance(reply,dict) and reply.get('type')=='groundControlLayout'
            and reply.get('requiredForInput') is True and payload==b'',
            'Native ground-control input gate was not acknowledged')
    validate_capability(reply.get('capability'))
    return contract,copy.deepcopy(reply)


@lru_cache(maxsize=4)
def _pattern_masks(pattern,width):
    """Precompute the two immutable glyph masks in the crop's original pixel-stride coordinates."""
    dark=sum(1<<(y*width+x) for y,row in enumerate(pattern) for x,value in enumerate(row) if value=='#')
    light=sum(1<<(y*width+x) for y,row in enumerate(pattern) for x,value in enumerate(row) if value=='.')
    return dark,light,dark.bit_count(),light.bit_count()


def match_crop(data,crop,pattern,expected_x):
    """Replay the bounded glyph/rectangle search offline; runtime admission validates native counts and hashes."""
    dark_pattern,light_pattern,dark_count,light_count=_pattern_masks(tuple(pattern),crop['width'])
    # Cache threshold masks once; no image library or model is needed for replay.
    dark=light=0
    for index,(r,g,b) in enumerate(zip(data[::3],data[1::3],data[2::3])):
        if r<150 and g<150 and b<150:dark|=1<<index
        if r>=205 and g>=205 and b>=205 and max(r,g,b)-min(r,g,b)<=40:light|=1<<index
    best,score=None,-1
    for y in range(1024,1031):
        for x in range(expected_x-3,expected_x+4):
            start=(y-crop['y'])*crop['width']+x-crop['x']
            # Intersection counts exactly the same pixels as the original point sums.
            d=((dark>>start)&dark_pattern).bit_count()
            l=((light>>start)&light_pattern).bit_count()
            value=min(d/dark_count/.90,l/light_count/.97)
            if value>score:
                score=value
                best=dict(matched=d*100>=90*dark_count and l*100>=97*light_count,
                    x=x,y=y,width=30,height=25,darkMatches=d,darkExpected=dark_count,
                    lightMatches=l,lightExpected=light_count)
    return best


def swim_pixels(data,crop):
    """Reuse the exact existing native-script yellow swim-control hint, without inferring absence means land."""
    count=0
    for y in range(1028,1035):
        for x in range(1819,1828):
            i=((y-crop['y'])*crop['width']+x-crop['x'])*3
            r,g,b=data[i:i+3]
            count+=242<=r<=255 and 223<=g<=233 and 39<=b<=44
    return count


def validate_frame(frame, *, replay_pixels=False):
    """Bind exact source, native layout, tiny bytes, geometry and internally consistent positive/negative fields."""
    evidence=frame.get('groundControlEvidence')
    if evidence is None:return None
    require(isinstance(evidence,dict) and type(evidence.get('version')) is int and evidence['version']==1
            and evidence.get('method')==CAPABILITY['method'] and evidence.get('authorizesInput') is False
            and evidence.get('physicallyGrounded') is False,'Invalid native ground-control evidence contract')
    require(type(evidence.get('frameId')) is int and evidence['frameId']>0
            and evidence['frameId']==frame.get('frameId') and evidence.get('sourceFrame')==frame.get('sourceFrame')
            and all(type(evidence.get(k)) is int and evidence[k]>0 and evidence[k]==frame.get(k)
                    for k in ('sourceWidth','sourceHeight')),'Ground-control evidence source or geometry changed')
    require(evidence.get('state') in ('valid','unavailable') and finite(evidence.get('recognitionMs'))
            and evidence['recognitionMs']>=0 and type(evidence.get('reason')) is str,
            'Invalid native ground-control recognition state')
    require(type(evidence.get('groundControlsConfirmed')) is bool
            and type(evidence.get('swimHintPixels')) is int and 0<=evidence['swimHintPixels']<=63
            and isinstance(evidence.get('crops'),list),'Invalid bounded ground-control measurements')
    if evidence['state']=='unavailable':
        require(evidence['reason'] in ('unsupported_geometry','source_identity_missing','world_not_ready','recognition_failed')
                and not evidence['groundControlsConfirmed'] and evidence['swimHintPixels']==0
                and all(evidence.get(k) is None for k in ('spaceKeyMatched','xKeyMatched','eKey','qKey'))
                and not evidence['crops'],'Unavailable ground-control evidence retained positive fields')
        return evidence
    source=evidence['sourceFrame']
    require((evidence['sourceWidth'],evidence['sourceHeight'])==(1920,1080)
            and isinstance(source,dict) and type(source.get('captureEpoch')) is str and source['captureEpoch']
            and type(source.get('timestamp100ns')) is int and source['timestamp100ns']>0
            and all(finite(source.get(k)) for k in ('capturedAtMs','acquiredAtMs','freshnessAtMs'))
            and source['freshnessAtMs']==min(source['capturedAtMs'],source['acquiredAtMs'])
            and source.get('freshnessClockKind')==('reported_compositor_qpc'
                if source['capturedAtMs']<=source['acquiredAtMs'] else 'first_acquisition_qpc'),
            'Valid ground-control evidence lacks the fixed geometry and immutable WGC source')
    require(len(evidence['crops'])==2 and all(evidence.get(k) is None or type(evidence[k]) is bool
            for k in ('spaceKeyMatched','xKeyMatched')),'Invalid ground-control crop or motion evidence')
    decoded=[]
    for crop,name,key,pattern,anchor in zip(evidence['crops'],('eRegion','qRegion'),('eKey','qKey'),
                                           (E_PATTERN,Q_PATTERN),(1684,1804)):
        region=CAPABILITY[name]
        require(isinstance(crop,dict) and set(crop)==set(region)|{'format','rgbBase64','sha256'}
                and all(type(crop.get(k)) is int and crop[k]==v for k,v in region.items())
                and crop.get('format')=='rgb24' and type(crop.get('rgbBase64')) is str
                and len(crop['rgbBase64'])==region['width']*region['height']*4,
                'Ground-control inline crop bounds changed')
        data=base64.b64decode(crop['rgbBase64'],validate=True)
        require(len(data)==region['width']*region['height']*3
                and hashlib.sha256(data).hexdigest()==crop.get('sha256'),'Ground-control crop bytes or hash changed')
        decoded.append(data)
        match=evidence.get(key)
        require(isinstance(match,dict) and set(match)=={'matched','x','y','width','height','darkMatches','darkExpected','lightMatches','lightExpected'}
                and type(match.get('matched')) is bool and all(type(match.get(k)) is int for k in match if k!='matched')
                and anchor-3<=match['x']<=anchor+3 and 1024<=match['y']<=1030
                and match['width']==30 and match['height']==25
                and match['darkExpected']==sum(row.count('#') for row in pattern)
                and match['lightExpected']==sum(row.count('.') for row in pattern)
                and 0<=match['darkMatches']<=match['darkExpected'] and 0<=match['lightMatches']<=match['lightExpected']
                and match['matched']==(match['darkMatches']*100>=90*match['darkExpected']
                                      and match['lightMatches']*100>=97*match['lightExpected']),
                'Ground-control keycap geometry, glyph counts or decision changed')
        if replay_pixels:require(match==match_crop(data,crop,pattern,anchor),'Ground-control glyph does not replay from retained pixels')
    if replay_pixels:require(evidence['swimHintPixels']==swim_pixels(decoded[1],evidence['crops'][1]),
                             'Swim hint does not replay from retained pixels')
    confirmed=(evidence['eKey']['matched'] and evidence['qKey']['matched'] and evidence['swimHintPixels']<4
               and evidence['spaceKeyMatched'] is False and evidence['xKeyMatched'] is False)
    reason=('swim_control_hint' if evidence['swimHintPixels']>=4 else
            'ground_control_layout' if confirmed else 'ground_controls_unconfirmed')
    require(evidence['groundControlsConfirmed']==confirmed and evidence['reason']==reason,
            'Ground-control layout decision contradicts its raw evidence')
    return evidence


def require_ground_frame(frame, *, replay_pixels=False):
    """Positive layout is mandatory at review, movement admission and every post-release endpoint sample."""
    evidence=validate_frame(frame,replay_pixels=replay_pixels)
    require(evidence is not None and evidence['state']=='valid' and evidence['groundControlsConfirmed'],
            'Positive native ground-control layout is required')
    return evidence


def verify_image_crops(path,frame):
    """Join the reviewed native PNG to the exact small inline regions, not merely to a matching source label."""
    from PIL import Image
    evidence=require_ground_frame(frame,replay_pixels=True)
    with Image.open(path) as original:
        require(original.size==(1920,1080),'Reviewed control-layout PNG has unsupported geometry')
        image=original.convert('RGB')
        for crop in evidence['crops']:
            x,y,w,h=(crop[key] for key in ('x','y','width','height'))
            require(image.crop((x,y,x+w,y+h)).tobytes()==base64.b64decode(crop['rgbBase64'],validate=True),
                    'Reviewed native PNG differs from its retained control-layout crop')


def scene_capability(scene,required=False):
    """Keep historical clean scenes unchanged; declared modern evidence cannot silently downgrade."""
    value=scene.get('nativeGroundControlObservation')
    rows=scene.get('observations',[])+scene.get('stableSamples',[])
    if value is None:
        require(not required and 'nativeGroundControlGate' not in scene
                and not any(row.get('groundControlEvidence') is not None for row in rows),
                'Native ground-control scene declaration is missing')
        return None
    contract=validate_capability(value)
    require(scene.get('nativeGroundControlGate',{}).get('type')=='groundControlLayout'
            and scene['nativeGroundControlGate'].get('requiredForInput') is True,
            'Passive scene did not retain the native ground-control gate acknowledgement')
    validate_capability(scene['nativeGroundControlGate'].get('capability'))
    require(any(validate_frame(row) is not None for row in rows if row.get('type')=='frame'),
            'Declared ground-control scene has no retained evidence')
    return contract
