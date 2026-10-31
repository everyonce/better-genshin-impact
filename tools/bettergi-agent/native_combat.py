"""Validate optional same-image native HUD metadata; this module never grants input authority."""
import copy
import math

METHOD='native_hud_color_components_v1'
CAPABILITY=dict(version=1,method=METHOD,sameFrame=True,readOnly=True,requiresWgcSourceIdentity=True,
    minWidth=1280,maxWidth=1920,maxHeight=1080,aspectRatio='16:9',referenceWidth=1920,referenceHeight=1080,
    healthRow=dict(x=808,y=1010,width=304),enemyRegion=dict(x=200,y=100,width=1400,height=800),
    maximumCandidates=16,healthFractionIsEstimate=True,authorizesInput=False,enemyIdentityVerified=False,killVerified=False)
# Keep the original public aliases byte-for-byte for R62 and archived v1 evidence.
METHOD_V2='native_hud_color_components_v2'
CAPABILITY_V2=dict(copy.deepcopy(CAPABILITY),version=2,method=METHOD_V2,
    enemyRegion=dict(x=200,y=100,width=1400,height=890),rejectsLowerBoundaryComponents=True)


def require(condition,message):
    """Fail the negotiated observation stream on malformed or substituted native evidence."""
    if not condition:raise ValueError(message)


def finite(value):
    """JSON booleans are not numeric recognition measurements."""
    return type(value) in (int,float) and math.isfinite(value)


def capability_for_version(version):
    """Resolve one explicit immutable contract without upgrading a historical version."""
    require(type(version) is int and version in (1,2),'Unknown native combat observation version')
    return copy.deepcopy(CAPABILITY if version==1 else CAPABILITY_V2)


def validate_capability(capability,expected=None):
    """Accept a known contract and, when supplied, bind it to the negotiated version."""
    require(isinstance(capability,dict),'Missing native combat observation capability')
    contract=capability_for_version(capability.get('version'))
    require(all(type(capability.get(key)) is type(value) and capability[key]==value
                for key,value in contract.items()),'Native combat observation contract differs')
    if expected is not None:
        require(contract==validate_capability(expected),'Native combat observation negotiation changed')
    return contract


def negotiate(bridge):
    """Enable pixels-only metadata on the existing authenticated lease, without changing input flags."""
    capability=validate_capability(bridge.hello.get('combatObservation'))
    reply,payload=bridge.request('enableCombatObservation')
    require(isinstance(reply,dict) and reply.get('type')=='combatObservation' and reply.get('enabled') is True
            and payload==b'','Native combat observation was not acknowledged')
    validate_capability(reply.get('capability'),capability)
    return capability


def scene_capability(scene):
    """A declared v2 scene must contain matching evidence; absent old declarations mean v1 only."""
    capability=validate_capability(scene.get('nativeCombatObservation',CAPABILITY))
    evidence=[validate_frame(row,capability) for row in scene.get('observations',[])
              if isinstance(row,dict) and row.get('combatEvidence') is not None]
    require(capability['version']==1 or bool(evidence),'Declared v2 scene lacks native evidence')
    return capability


def validate_frame(frame,capability=None):
    """Keep exact source joins and negative evidence intact; a pending first capture returns no evidence."""
    evidence=frame.get('combatEvidence')
    if evidence is None:return None
    require(isinstance(evidence,dict),'Malformed native combat evidence')
    contract=capability_for_version(evidence.get('version'))
    if capability is not None:
        validate_capability(contract,capability)
    require(evidence.get('method')==contract['method'],
            'Unknown native combat evidence version')
    require(all(evidence.get(key) is False for key in ('authorizesInput','enemyIdentityVerified','killVerified')),
            'Native color evidence attempted to claim input or target authority')
    require(type(evidence.get('frameId')) is int and evidence['frameId']>0 and evidence['frameId']==frame.get('frameId'),
            'Native combat evidence belongs to a different frame')
    require(evidence.get('sourceFrame')==frame.get('sourceFrame'),'Native combat source identity differs')
    for key in ('sourceWidth','sourceHeight'):
        require(type(evidence.get(key)) is int and evidence[key]>0 and evidence[key]==frame.get(key),
                'Native combat geometry differs from the source image')
    state=evidence.get('state')
    require(state in ('valid','unavailable') and type(evidence.get('reason')) is str and evidence['reason'],
            'Native combat evidence has no explicit state')
    require(finite(evidence.get('recognitionMs')) and evidence['recognitionMs']>=0,'Invalid native recognition duration')
    color=evidence.get('playerHealthColor')
    fraction=evidence.get('playerHealthFractionEstimate')
    count=evidence.get('playerHealthMatchingPixels')
    bars=evidence.get('enemyBarCandidates')
    overloaded=evidence.get('redMaskOverloaded')
    require(color in ('green','red','unknown') and type(count) is int and count>=0,'Invalid native health evidence')
    require(type(bars) is list and len(bars)<=16 and type(overloaded) is bool,'Unbounded native candidate evidence')
    require(fraction is None if color=='unknown' else finite(fraction) and 0<fraction<=1,
            'Invalid native health fraction estimate')
    if state=='unavailable':
        require(color=='unknown' and fraction is None and count==0 and not bars and not overloaded,
                'Unavailable native evidence retained positive fields')
        return evidence
    width,height=evidence['sourceWidth'],evidence['sourceHeight']
    require(isinstance(evidence.get('sourceFrame'),dict) and 1280<=width<=1920 and height<=1080
            and abs(width/height-16/9)<=.002,'Unsupported valid native capture')
    source=evidence['sourceFrame']
    require(type(source.get('captureEpoch')) is str and source['captureEpoch']
            and type(source.get('timestamp100ns')) is int and source['timestamp100ns']>0
            and all(finite(source.get(key)) for key in ('capturedAtMs','acquiredAtMs','freshnessAtMs')),
            'Valid native evidence has no complete WGC source identity')
    require(source['freshnessAtMs']==min(source['capturedAtMs'],source['acquiredAtMs'])
            and source.get('freshnessClockKind')==('reported_compositor_qpc'
                if source['capturedAtMs']<=source['acquiredAtMs'] else 'first_acquisition_qpc'),
            'Native evidence changed its immutable freshness anchor')
    scale=width/1920
    require(count<=round(1112*scale)-round(808*scale),'Health matching count exceeds its native row')
    require(color=='unknown' or count>=3,'Native health color lacks its matching prefix')
    require(evidence['reason']==('red_mask_overloaded' if overloaded else 'native_colors_analyzed')
            and (not overloaded or not bars),'Ambiguous red evidence retained a partial target set')
    region=contract['enemyRegion']
    left,top,region_width,region_height=(round(region[key]*scale) for key in ('x','y','width','height'))
    for bar in bars:
        require(isinstance(bar,dict) and all(type(bar.get(key)) is int for key in ('x','y','width','height','pixels')),
                'Malformed native red component')
        x,y,w,h,pixels=(bar[key] for key in ('x','y','width','height','pixels'))
        require(x>=left and y>=top and x+w<=left+region_width and y+h<=top+region_height
                and (contract['version']==1 or y+h<top+region_height)
                and 24*scale<=w<=320*scale and max(1,2*scale)<=h<=14*scale and w>=5*h
                and .7*w*h<=pixels<=w*h,'Native component escaped the declared color/geometry scope')
    return evidence
