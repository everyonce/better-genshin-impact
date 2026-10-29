"""Collect lossless model-input photos at native-verified street stations without owning game input."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image

from hybrid_routes import PATROL_STATIONS, STREET_PATROL_ROUTE
from observation_timing import observation_timestamp
from resident_runtime import atomic_json


def require(ok, message):
    """Reject missing provenance before producing a verified photo."""
    if not ok:
        raise ValueError(message)


def digest(raw):
    """Hash exact file or RGB bytes."""
    return hashlib.sha256(raw).hexdigest()


def require_qualified_observer(qualification_path, checkpoint_id):
    """Recompute the promotion result from its hash-bound paired evaluation before enabling capture."""
    from qualify_landmarks import qualify
    path = Path(qualification_path)
    saved = json.loads(path.read_bytes())
    evaluated = path.parent/Path(saved['evaluation'])
    raw = evaluated.read_bytes()
    require(digest(raw) == saved['evaluationSha256'] and saved['challengerSha256'] == checkpoint_id,
            'Photo observer qualification or checkpoint digest differs')
    result = qualify(json.loads(raw),saved['incumbentSha256'],checkpoint_id)
    require(result == {k:v for k,v in saved.items() if k not in ('evaluation','evaluationSha256')}
            and result['route'] == STREET_PATROL_ROUTE and result['recommendation'] == 'use-challenger-as-observer',
            'Observer lacks a recomputed promotion for the surveyed route')
    return result


def validated_targets(targets):
    """Restrict file names and objectives to unique, reviewed station names."""
    require(isinstance(targets,(list,tuple)) and targets and all(isinstance(t,str) and t in PATROL_STATIONS for t in targets)
            and len(set(targets)) == len(targets), 'Requested photos must name unique registered stations')
    return list(targets)


def outcome(station, predicted, targets, collected):
    """Only a matching prediction of an outstanding native station yields its photo."""
    if station not in targets:
        return 'unrequested'
    if station in collected:
        return 'alreadyCollected'
    return 'collected' if station == predicted else 'classificationMiss'


class PatrolPhotoSurvey:
    """Store images from verified arrivals. The collector receives frames and has no input or navigation API."""
    def __init__(self, output, targets, checkpoint_id):
        """Create a fresh evidence directory without overwriting an earlier survey."""
        self.targets = validated_targets(targets)
        require(isinstance(checkpoint_id,str) and len(checkpoint_id)==64 and
                all(c in '0123456789abcdef' for c in checkpoint_id), 'Expected frozen landmark checkpoint SHA-256')
        self.output, self.checkpoint_id = Path(output), checkpoint_id
        self.output.mkdir(parents=True,exist_ok=False)
        self.journal, self.collected, self.used_rgb = [], {}, set()
        self.seen_sources, self.seen_frames = set(), set()
        self._save()

    def snapshot(self):
        """Return a small progress record suitable for the existing status channel."""
        missing = [s for s in self.targets if s not in self.collected]
        return dict(targets=list(self.targets), collected=list(self.collected), missing=missing, complete=not missing,
                    manifest=str((self.output/'manifest.json').resolve()))

    def _save(self):
        """Publish journal entries and completion together, after any associated PNG is written."""
        progress = self.snapshot()
        progress.pop('manifest')
        data = dict(format='bettergi-patrol-photo-survey-v1',routeId=STREET_PATROL_ROUTE,
                    checkpointId=self.checkpoint_id, **progress, journal=self.journal)
        atomic_json(self.output/'manifest.json',data)

    def observe(self, event, frame, rgb):
        """Consider the original RGB only for this native-verified start or final stable arrival."""
        if event.get('type') not in ('hybridStartVerified','hybridEndpointVerified') or len(self.collected)==len(self.targets):
            return None
        sample = (event.get('samples') or [{}])[-1]
        visual = event.get('visualStation') or {}
        prediction = visual.get('prediction') or {}
        source = (frame or {}).get('sourceFrame') or {}
        pose = (frame or {}).get('navigationPose') or {}
        station, fid = event.get('station'), sample.get('frameId')
        identity = source.get('captureEpoch'),source.get('timestamp100ns')
        exact = (isinstance(frame,dict) and type(fid) is int and station in PATROL_STATIONS and
                 event.get('routeId') == STREET_PATROL_ROUTE and identity[0] and identity[0] == event.get('sourceEpoch')
                 and type(identity[1]) is int and visual.get('checkpointId') == self.checkpoint_id
                 and frame.get('frameId') == fid == visual.get('frameId') == pose.get('frameId')
                 and (event['type'] != 'hybridStartVerified' or event.get('frameId') == fid)
                 and frame.get('width') == frame.get('height') == 192 and frame.get('pixelFormat') == 'rgb24'
                 and pose.get('state') == 'valid' and pose.get('layerId') == 'City_102'
                 and all(k in pose and k in sample and sample[k]==pose[k] for k in ('x','y','yawDegrees'))
                 and observation_timestamp(frame) == sample.get('atMs') and math.dist((pose['x'],pose['y']),PATROL_STATIONS[station]) <= 2
                 and frame.get('frameWorldReadiness',{}).get('ready') is True and prediction.get('station') in PATROL_STATIONS
                 and isinstance(rgb,(bytes,bytearray,memoryview)) and len(rgb)==192*192*3)
        if exact and (fid in self.seen_frames or identity in self.seen_sources):
            return None
        if exact:
            gate = frame['frameWorldReadiness']
            distance = prediction.get('squaredDistance')
            exact = (len(event['samples'])==3 and (event['type']=='hybridStartVerified' and station=='stair-front'
                     or event['type']=='hybridEndpointVerified' and event.get('endpoint')==station)
                     and gate.get('sourceFrameId')==fid and gate.get('sourceFrame')==source
                     and frame.get('inputAvailable') is True and (frame.get('motionEvidence') or {}).get('status')=='normal'
                     and frame['motionEvidence'].get('spaceKeyMatched') is False
                     and .99 <= pose.get('positionConfidence',0) <= 1 and .2 <= pose.get('yawConfidence',0) <= 1
                     and type(distance) in (float,int) and math.isfinite(distance) and distance >= 0)
        row = dict(station=station, predictedStation=prediction.get('station'), frameId=fid, sourceEpoch=identity[0],
                   sourceTimestamp100ns=identity[1], atMs=sample.get('atMs'), liveRgbSha256=visual.get('rgbSha256'))
        raw_hash = digest(rgb) if exact else None
        if not exact or raw_hash != visual.get('rgbSha256'):
            row['outcome'] = 'sourceMismatch'
        else:
            self.seen_frames.add(fid)
            self.seen_sources.add(identity)
            row['outcome'] = outcome(station, prediction['station'], self.targets, self.collected)
            if row['outcome'] == 'collected' and raw_hash in self.used_rgb:
                row['outcome'] = 'duplicateImage'
            if row['outcome'] == 'collected':
                filename = f'{station}-frame-{fid}.png'
                photo = self.output/filename
                with photo.open('xb') as out:
                    Image.frombytes('RGB',(192,192),bytes(rgb)).save(out,'PNG',compress_level=1)
                row.update(file=filename,pngSha256=digest(photo.read_bytes()),x=pose['x'],y=pose['y'],
                           yawDegrees=pose['yawDegrees'])
                self.collected[station]=fid
                self.used_rgb.add(raw_hash)
        self.journal.append(row)
        self._save()
        return dict(row)


def verify_photo_survey(output, run_path, recordings, *, repository, landmark_checkpoint, authenticated_report=None):
    """Re-audit the sealed patrol and verify every saved PNG against the live RGB digest and frozen classifier."""
    from audit_hybrid_run import audit
    from landmark_recognizer import LandmarkRecognizer
    report = audit(run_path,recordings,repository=repository,landmark_checkpoint=landmark_checkpoint)
    if authenticated_report is not None:
        cached = authenticated_report if isinstance(authenticated_report,dict) else json.loads(Path(authenticated_report).read_bytes())
        require(all(cached.get(k)==report[k] for k in ('passed','routeId','verifiedLegs','verifiedCircuits','landmarkShadow')),
                'Supplied patrol audit differs from its sealed source')
    output = Path(output)
    manifest = json.loads((output/'manifest.json').read_bytes())
    head = LandmarkRecognizer.load(landmark_checkpoint)
    require(manifest['format']=='bettergi-patrol-photo-survey-v1' and manifest['routeId']==report['routeId']==STREET_PATROL_ROUTE
            and manifest['checkpointId']==report['landmarkShadow']['checkpointId']==head.checkpoint_id, 'Different photo route or checkpoint')
    targets = validated_targets(manifest['targets'])
    sources = report['landmarkShadow']['sources']
    run = json.loads(Path(run_path).read_bytes())
    poses, original_visits = {}, []
    for e in run['segments']:
        part = json.loads((Path(repository)/e['report']).read_bytes())
        for event in part['hybridNavigationEvents']:
            if event['type'] in ('hybridStartVerified','hybridEndpointVerified'):
                p=event['samples'][-1]
                poses[p['frameId']]=p
                if event.get('photoSurveyVisit') is not None:
                    original_visits.append(event['photoSurveyVisit'])
    require(original_visits == manifest['journal'], 'Photo manifest differs from the original survey event journal')
    return verify_photos(output,manifest,targets,sources,poses,head)


def verify_photos(output, manifest, targets, sources, poses, head):
    """Replay the survey journal against the authenticated station sequence through completion."""
    rows, collected, files, hashes = manifest['journal'], [], set(), set()
    used = 0
    for i,s in enumerate(sources):
        if len(collected)==len(targets):
            break
        require(i<len(rows), 'Survey omitted a verified station before completion')
        row = rows[i]
        used += 1
        p=poses[s['frameId']]
        require(all(row.get(k)==s[v] for k,v in (('station','native'),('predictedStation','live'),('frameId','frameId'),
                ('sourceEpoch','sourceEpoch'),('sourceTimestamp100ns','sourceTimestamp100ns'),('liveRgbSha256','liveRgbSha256')))
                and row['atMs']==p['atMs'], 'Photo journal differs from native/visual observation')
        expected=outcome(s['native'],s['live'],targets,collected)
        require(row['outcome']==expected, 'Unverified omission, duplicate or photo claim')
        if expected!='collected':
            require('file' not in row and 'pngSha256' not in row, 'Unverified station has a photo')
            continue
        filename = f"{s['native']}-frame-{s['frameId']}.png"
        require(row['file']==filename and all(row[k]==p[k] for k in ('x','y','yawDegrees'))
                and s['liveRgbSha256'] not in hashes, 'Photo filename, native pose or unique image identity differs')
        path=output/filename
        require(digest(path.read_bytes())==row['pngSha256'], 'Saved PNG digest differs')
        with Image.open(path) as image:
            require(image.format=='PNG' and image.mode=='RGB' and image.size==(192,192) and getattr(image,'n_frames',1)==1,
                    'Saved photo is not one original-size RGB PNG')
            pixels=image.tobytes()
        require(digest(pixels)==s['liveRgbSha256'] and head.predict(pixels)==
                dict(station=s['live'],squaredDistance=s['liveSquaredDistance']), 'Photo pixels or frozen prediction differ')
        hashes.add(s['liveRgbSha256'])
        files.add(filename)
        collected.append(s['native'])
    missing = [s for s in targets if s not in collected]
    require(len(rows)==used and set(p.name for p in output.glob('*.png'))==files and manifest['collected']==collected
            and manifest['missing']==missing and manifest['complete'] is (not missing), 'Photo manifest completeness or file inventory differs')
    return dict(verified=True,complete=not missing,targets=targets,collected=collected,missing=missing,
                collectedPhotos=len(files),classificationMisses=sum(r['outcome']=='classificationMiss' for r in rows),
                observedStations=len(rows),checkpointId=head.checkpoint_id,manifest=str((output/'manifest.json').resolve()))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('output','run','recordings','landmark-checkpoint'):
        parser.add_argument('--'+flag,required=True)
    parser.add_argument('--repository',default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument('--authenticated-report')
    args=vars(parser.parse_args())
    args['run_path']=args.pop('run')
    print(json.dumps(verify_photo_survey(**args),indent=2))
