"""Archive original native checkpoint RGB in the existing bounded evidence journal; no input ownership."""
import base64
import hashlib
import json
from pathlib import Path
import re

from hybrid_routes import STREET_PATROL_ROUTE
from observation_timing import observation_timestamp


KINDS = ('hybridStartVerified','hybridEndpointVerified')
RGB_BYTES = 192*192*3


def require(ok, message):
    """Treat a missing original or an ownership mismatch as incomplete shadow evidence."""
    if not ok:
        raise ValueError(message)


def header(native, frame, run_id, hello, child_pid, session):
    """Bind the settled native marker, visual input, original source clock and authenticated child lease."""
    sample = native['samples'][-1]
    fid, source, gate, pose = frame['frameId'],frame['sourceFrame'],frame['frameWorldReadiness'],frame['navigationPose']
    visual = native['visualStation']
    require(native['type'] in KINDS and native['routeId']==STREET_PATROL_ROUTE and 'navigationMode' not in native
            and sample['frameId']==visual['frameId']==pose['frameId']==gate['sourceFrameId']==fid
            and source['captureEpoch']==native['sourceEpoch'] and gate['sourceFrame']==source and gate['ready'] is True
            and pose['state']=='valid' and pose['layerId']=='City_102' and observation_timestamp(frame)==sample['atMs']
            and all(pose[k]==sample[k] for k in ('x','y','yawDegrees')) and
            (frame['width'],frame['height'],frame['pixelFormat'])==(192,192,'rgb24'), 'Invalid native RGB source binding')
    if native['type']=='hybridStartVerified':
        require(native['frameId']==fid, 'Wrong start frame for station RGB')
    else:
        require(gate['epoch']==native['releaseEpoch'] and sample['atMs']>=native['releaseAtMs']+80,
                'Wrong release generation for station RGB')
    require(type(child_pid) is int and child_pid>0 and type(session) is int and session>0 and
            all(isinstance(v,str) and re.fullmatch('[a-f0-9]{32}',v) for v in (run_id,hello['sessionId'],hello['ownerEpoch'])),
            'Missing resident binding')
    return dict(type='landmarkShadowSource',version=1,runId=run_id,sessionId=hello['sessionId'],ownerEpoch=hello['ownerEpoch'],
                childProcessId=child_pid,windowsSessionId=session,eventType=native['type'],routeId=STREET_PATROL_ROUTE,
                station=native['station'],frameId=fid,captureEpoch=source['captureEpoch'],sourceTimestamp100ns=source['timestamp100ns'],
                readinessEpoch=gate['epoch'],rgbSha256=visual['rgbSha256'],checkpointId=visual['checkpointId'])


def pack(native,frame,pixels,run_id,hello,child_pid,session):
    """Hand the recorder one immutable RGB24 row, selected by native arrival irrespective of prediction."""
    row = header(native,frame,run_id,hello,child_pid,session)
    require(len(pixels)==RGB_BYTES and hashlib.sha256(pixels).hexdigest()==row['rgbSha256'], 'Original RGB payload hash differs')
    return dict(**row,rgb24Base64=base64.b64encode(pixels).decode('ascii'))


def retain(recorder,native,frame,pixels,run_id,hello,child_pid,session):
    """A broken shadow binding invalidates its evidence only; navigation never consults this output."""
    try:
        row = pack(native,frame,pixels,run_id,hello,child_pid,session)
    except (KeyError,IndexError,TypeError,ValueError) as error:
        row = dict(type='landmarkShadowSourceRejected',error=str(error))
    recorder.event(row)


def replay(row,native,frame,head,run_id,hello,child_pid,session):
    """Independently check every retained byte and recompute its unmodified shadow prediction."""
    meta = header(native,frame,run_id,hello,child_pid,session)
    require(set(row)==set(meta)|{'rgb24Base64'} and all(row[k]==v for k,v in meta.items())
            and meta['checkpointId']==head.checkpoint_id, 'Shadow source identity mismatch')
    data = row['rgb24Base64']
    require(isinstance(data,str) and len(data)==4*(RGB_BYTES//3), 'Invalid RGB24 encoded length')
    raw = base64.b64decode(data,validate=True)
    require(len(raw)==RGB_BYTES and hashlib.sha256(raw).hexdigest()==meta['rgbSha256']
            and head.predict(raw)==native['visualStation']['prediction'], 'Original RGB hash or replay prediction differs')
    return meta


def verify_archive(run_path,recordings,checkpoint,route_audit,repository):
    """Require one original per physically verified marker on one completed, already audited full-circuit capture."""
    from weighted_landmark_recognizer import load_landmark_shadow
    run = json.loads(Path(run_path).read_bytes())
    head = load_landmark_shadow(checkpoint)
    visits = route_audit['landmarkShadow']['sources']
    require(run['status']=='completed' and run['evidenceComplete'] is True and route_audit['passed'] is True
            and route_audit['routeId']==STREET_PATROL_ROUTE and route_audit['controllerLeases']==1
            and len(visits)==1+4*route_audit['verifiedCircuits']==1+route_audit['verifiedLegs'], 'Full fixed patrol required')
    results = []
    for entry in run['segments']:
        segment = entry['number']
        part = json.loads((Path(repository)/entry['report']).read_bytes())
        require(part['residentRunId']==run['runId'], 'Foreign archive segment')
        folder = Path(recordings)/f'{segment:05d}'
        markers = [e for e in part.get('hybridNavigationEvents',[]) if e['type'] in KINDS]
        records,journal_markers = [],[]
        with (folder/'events.jsonl').open(encoding='utf-8') as stream:
            for row in map(json.loads,stream):
                kind = row.get('type')
                require(kind!='landmarkShadowSourceRejected', 'Station source was rejected at capture')
                if kind=='landmarkShadowSource':
                    records.append(row)
                elif kind in KINDS:
                    journal_markers.append(row)
        require(journal_markers==markers,'Native station journal differs from resident report')
        require(len(records)==len(markers), 'Missing or extra original station RGB')
        wanted = {r['frameId'] for r in records}
        with (folder/'observations.jsonl').open(encoding='utf-8') as stream:
            frames = {f['frameId']:f for f in map(json.loads,stream) if f['frameId'] in wanted and not f.get('continuityContext')}
        for row,native in zip(records,markers):
            ref = visits[len(results)]
            require((ref['segment'],ref['frameId'],ref['native'],ref['liveRgbSha256'])==
                    (segment,row['frameId'],row['station'],row['rgbSha256']), 'Landmark audit and retained source differ')
            require((ref['sourceTimestamp100ns'],ref['sourceEpoch'])==(row['sourceTimestamp100ns'],row['captureEpoch']),
                    'Native audit and retained source clock differ')
            result = replay(row,native,frames[row['frameId']],head,run['runId'],part['hello'],
                            entry['processId'],run['windowsSessionId'])
            results.append(dict(result,segment=segment,eventsFile=str(folder/'events.jsonl'),prediction=native['visualStation']['prediction']))
    require(len(results)==len(visits)==len({r['frameId'] for r in results}), 'Incomplete or duplicated station sources')
    return dict(format='bettergi-native-station-rgb-v1',passed=True,runId=run['runId'],checkpointId=head.checkpoint_id,
                routeId=STREET_PATROL_ROUTE,encoding='base64-rgb24-192x192',sourceCount=len(results),sources=results)
