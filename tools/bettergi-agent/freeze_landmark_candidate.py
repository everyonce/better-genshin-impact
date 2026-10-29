"""Extend a qualified frozen landmark template set using exact native-labeled PNG arrivals from specified leases."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path

from PIL import Image

from audit_hybrid_run import require
from hybrid_routes import PATROL_STATIONS, STREET_PATROL_ROUTE
from landmark_recognizer import LandmarkRecognizer, signature
from observation_timing import observation_timestamp
from patrol_landmarks import indexed_frames
from patrol_photo_survey import require_qualified_observer
from run_rdp_patrol import native_qpc_sample
from train_steering import distinct


def sha(raw):
    """Hash the exact bytes independently of filenames or copy times."""
    return hashlib.sha256(raw).hexdigest()


def encoded(doc):
    """Use stable, finite JSON bytes for this freeze and its source manifest."""
    return json.dumps(doc, sort_keys=True, separators=(',',':'), allow_nan=False).encode('utf-8')


def original_rgb(path, png_hash, rgb_hash):
    """Hash and decode a single immutable read; the PNG and live RGB must match their original records."""
    raw = path.read_bytes()
    require(sha(raw) == png_hash, 'Original station PNG file hash differs')
    with Image.open(io.BytesIO(raw)) as image:
        require(image.format=='PNG' and image.mode=='RGB' and image.size==(192,192), 'Original RGB192 PNG required')
        rgb = image.tobytes()
    require(sha(rgb) == rgb_hash, 'Station pixels differ from the live RGB hash')
    return rgb


def source_views(path, head, diagnostic):
    """Join physical arrivals to native observations, original release, submitted journal and lossless RGB."""
    path = path.resolve()
    folder, run = path.parent, json.loads(path.read_bytes())
    if diagnostic:
        require(run['status'] == 'failed', 'Expected a failed diagnostic lease')
    else:
        passed = json.loads((folder/'handoff-audit.json').read_bytes())
        require(run['status'] == 'completed' and passed['passed'] is True and passed['runId'] == run['runId'],
                'Training success case lacks an independent successful handoff audit')
    events, journal, frames, indexes, parts, leases = [], [], {}, {}, [], set()
    for entry in run['segments']:
        num = entry['number']
        part_path = folder/'patrol-segments'/f'{num:05d}.json'
        part_bytes = part_path.read_bytes()
        part = json.loads(part_bytes)
        require(Path(entry['report']).resolve() == part_path and part['residentRunId'] == run['runId']
                and part['hybridNavigation']['routeId'] == STREET_PATROL_ROUTE, 'Unbound station segment')
        directory = folder/'patrol-recording'/f'{num:05d}'
        index, _ = indexed_frames(directory,part)
        for fid,f in index.items():
            require(fid not in frames, 'Repeated source frame')
            frames[fid], indexes[fid] = f,(num,f['videoFrameIndex'])
        parts.append(dict(segment=num,reportSha256=sha(part_bytes),eventsSha256=sha((directory/'events.jsonl').read_bytes()),
                          observationsSha256=sha((directory/'observations.jsonl').read_bytes())))
        events.extend(part['hybridNavigationEvents'])
        journal.extend(map(json.loads,(directory/'events.jsonl').read_bytes().splitlines()))
        leases.add((part['hello']['sessionId'],part['hello']['ownerEpoch']))
    require(len(leases)==1 and len({f['sourceFrame']['captureEpoch'] for f in frames.values()}) == 1,
            'One capture and owner required per training lease')
    epoch = next(iter(frames.values()))['sourceFrame']['captureEpoch']
    kinds = ('hybridEndpointVerified','hybridDestinationPhotoRetry')
    markers = [e for e in events if e['type'] in kinds]
    require(markers == [e for e in journal if e.get('type') in kinds], 'Station journal differs from resident report')
    origins, source_rows, templates = {}, [], []
    for event in markers:
        selected = event.get('photoSurveyVisit') or {}
        if selected.get('outcome') not in ('collected','classificationMiss','confirmationPending'):
            continue
        station = event['station']
        fid = event['samples'][-1]['frameId']
        source = frames[fid]['sourceFrame']
        require(station in PATROL_STATIONS and event['toStation'] == event['requestedDestination'] == station
                and event['sourceEpoch'] == source['captureEpoch'] == epoch, 'Station identity differs')
        releases = [e['warmRelease'] for e in journal if e.get('warmRequestId') == event['warmRequestId']
                    and e.get('reason') == 'hybridEndpoint' and e.get('warmRelease',{}).get('serverNowMs') == event['releaseAtMs']]
        require(len(releases)==1, 'Missing unique release acknowledgement')
        rel = releases[0]
        require(rel['type']=='released' and rel['readinessReady'] is False and rel['readinessReason']=='client_release'
                and rel['policyHistoryReset'] is True and rel['captureEpoch']==epoch and rel['readinessEpoch']==event['releaseEpoch']
                and rel['arrivalFrameId']==event['arrivalFrameId'], 'Unbound release proof')
        arrival = frames[event['arrivalFrameId']]
        require(arrival['sourceFrame']['captureEpoch'] == epoch and arrival['frameWorldReadiness']['ready'] is True
                and rel['readinessEpoch'] == arrival['frameWorldReadiness']['epoch']+1
                and math.dist((arrival['navigationPose']['x'],arrival['navigationPose']['y']),PATROL_STATIONS[station]) <= 1.1,
                'Arrival outside native station threshold or release generation')
        samples = event['samples']
        require(len(samples)==3 and samples[0]['atMs'] >= rel['serverNowMs']+80, 'Missing settled observations')
        for i,s in enumerate(samples):
            f = frames[s['frameId']]
            pose,gate = f['navigationPose'],f['frameWorldReadiness']
            xy = (pose['x'],pose['y'])
            require(pose['state']=='valid' and pose['layerId']=='City_102' and pose['frameId']==s['frameId']==f['frameId']
                    and .99 <= pose['positionConfidence'] <= 1 and .2 <= pose['yawConfidence'] <= 1
                    and xy==(s['x'],s['y']) and pose['yawDegrees']==s['yawDegrees'] and math.dist(xy,PATROL_STATIONS[station])<=2
                    and f['motionEvidence']['status']=='normal' and f['motionEvidence']['spaceKeyMatched'] is False
                    and gate['sourceFrame']==f['sourceFrame'] and gate['sourceFrameId']==s['frameId']
                    and gate['epoch']==event['releaseEpoch'] and gate['ready'] is True and observation_timestamp(f)==s['atMs']
                    and f['sourceFrame']['captureEpoch']==epoch, 'Invalid native source or station geometry')
            require(all(s['frameId']>old['frameId'] and s['atMs']-old['atMs']>=80 and
                        math.dist(xy,(old['x'],old['y']))<=1.5 and abs((s['yawDegrees']-old['yawDegrees']+180)%360-180)<=3
                        for old in samples[:i]), 'Unstable or repeated endpoint sample')
        visual = event['visualStation']
        survey_dir = folder/'station-photos'/event['warmRequestId']
        require(selected in json.loads((survey_dir/'manifest.json').read_bytes())['journal'], 'Survey manifest differs')
        name = selected.get('file',selected.get('retryEvidenceFile'))
        expected = ('' if selected['outcome']=='collected' else 'retry-evidence/') + f'{station}-frame-{fid}.png'
        require(name==expected, 'Unexpected original PNG path')
        png = survey_dir/name
        png_hash = selected.get('pngSha256',selected.get('retryEvidencePngSha256'))
        rgb_hash = visual['rgbSha256']
        rgb = original_rgb(png,png_hash,rgb_hash)
        require(rgb_hash==selected['liveRgbSha256'] and head.checkpoint_id==visual['checkpointId']
                and head.predict(rgb)==visual['prediction'] and fid==selected['frameId']==visual['frameId']
                and selected['station']==station and selected['sourceTimestamp100ns']==source['timestamp100ns'],
                'PNG, original journal pixels, or frozen incumbent score differ')
        evidence = dict(frameId=fid,segment=indexes[fid][0],videoFrameIndex=indexes[fid][1],captureEpoch=epoch,
                        sourceTimestamp100ns=source['timestamp100ns'],rgbSha256=rgb_hash,pngSha256=png_hash)
        row = dict(**evidence,runId=run['runId'],warmRequestId=event['warmRequestId'],type=event['type'],
                   station=station,pngPath=str(png),release=rel,samples=samples,prediction=visual['prediction'],
                   training=event['type']=='hybridEndpointVerified')
        if row['training']:
            origins[fid] = row
            templates.append(dict(runId=run['runId'],station=station,evidence=evidence,signature=signature(rgb).tolist()))
        else:
            original = origins[event['initialEndpointFrameId']]
            require(original['release']==rel and original['station']==station
                    and 0<samples[-1]['atMs']-original['samples'][-1]['atMs']<=1500, 'Unbound diagnostic retry')
        source_rows.append(row)
    require(templates, 'No original station photos available')
    stamps = [f['sourceFrame']['timestamp100ns'] for f in frames.values()]
    meta = dict(path=str(path),runId=run['runId'],lease=list(leases.pop()),captureEpoch=epoch,
                sourceInterval100ns=[min(stamps),max(stamps)],evidenceSha256=sha(encoded(source_rows)),
                uniqueImages=len(templates),scope='native station photos from '+('failed diagnostic lease' if diagnostic else 'audited lease'))
    return meta,templates,dict(run=meta,originalManifestSha256=sha(path.read_bytes()),segments=parts,photos=source_rows)


def main():
    """Freeze a candidate without access to any unseen or future qualification images."""
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('incumbent','qualification','audited-run','diagnostic-run','out-dir'):
        p.add_argument('--'+flag,type=Path,required=True)
    args = p.parse_args()
    head = LandmarkRecognizer.load(args.incumbent)
    require_qualified_observer(args.qualification,head)
    data = dict(head.data,prototypes=list(head.data['prototypes']),trainingRuns=list(head.data['trainingRuns']))
    sources = []
    for path,diag in ((args.audited_run,False),(args.diagnostic_run,True)):
        meta,prototypes,manifest = source_views(path,head,diag)
        data['trainingRuns'].append(meta)
        data['prototypes'].extend(prototypes)
        sources.append(manifest)
    distinct(data['trainingRuns'])
    manifest_raw = encoded(dict(version=1,incumbentSha256=head.checkpoint_id,sources=sources))
    data.update(parentCheckpointSha256=head.checkpoint_id,augmentationManifestSha256=sha(manifest_raw))
    LandmarkRecognizer(data)
    raw = encoded(data)
    qpc = native_qpc_sample()
    require(qpc is not None,'Windows QPC required before holdout')
    freeze = dict(version=1,checkpointSha256=sha(raw),incumbentSha256=head.checkpoint_id,sourceManifestSha256=sha(manifest_raw),
                  frozenAtUtc=datetime.now(timezone.utc).isoformat(),freezeQpc=dict(clock='windows-query-performance-counter',
                  frequencyHz=qpc[0],ticks=qpc[1]),inheritedPrototypes=len(head.labels),totalPrototypes=len(data['prototypes']),
                  holdout=dict(route=STREET_PATROL_ROUTE,circuits=10,uniquePerClassMinimum=10,newLeaseAfterFreeze=True,
                               predeclaredRuns=1,noPerClassRegression=True,strictNetImprovement=True))
    args.out_dir.mkdir(parents=True,exist_ok=False)
    for name,content in (('source-manifest.json',manifest_raw),('gen-05.json',raw),('freeze.json',encoded(freeze))):
        with (args.out_dir/name).open('xb') as stream:
            stream.write(content)
    print(json.dumps(freeze))


if __name__=='__main__':
    main()
