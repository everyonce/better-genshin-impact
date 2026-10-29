"""Authenticate live station observations and independently score their exact indexed H.264 frames."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from audit_hybrid_run import require
from hybrid_routes import STREET_PATROL_ROUTE
from landmark_recognizer import CLASSES, LandmarkRecognizer, decode
from observation_timing import observation_timestamp
from patrol_landmarks import indexed_frames


def live_views(events, frames, journal, checkpoint_id, epoch):
    """Join each unique verified start/terminal sample to its contemporaneous live evaluation."""
    require(events == journal, 'Station event and original station journal differ')
    rows, seen = [], set()
    for e in events:
        s = e['samples'][-1]
        fid = s['frameId']
        v = e.get('visualStation') or {}
        f = frames.get(fid) or {}
        p = v.get('prediction') or {}
        source = f.get('sourceFrame') or {}
        pose = f.get('navigationPose') or {}
        require(fid not in seen and (e['type'] != 'hybridStartVerified' or e['frameId'] == fid)
                and v.get('frameId') == fid == pose.get('frameId') == f.get('frameId')
                and pose.get('state') == 'valid' and source.get('captureEpoch') == e['sourceEpoch'] == epoch
                and type(source.get('timestamp100ns')) is int and observation_timestamp(f) == s['atMs']
                and all(pose[k] == s[k] for k in ('x','y','yawDegrees'))
                and f['width'] == f['height'] == 192 and f['pixelFormat'] == 'rgb24'
                and e['station'] in CLASSES and e.get('routeId') == STREET_PATROL_ROUTE,
                'Visual evaluation is not bound to its verified RGB192 source')
        distance, elapsed = p.get('squaredDistance'), v.get('elapsedUs')
        require(v.get('checkpointId') == checkpoint_id and isinstance(v.get('rgbSha256'), str)
                and re.fullmatch('[0-9a-f]{64}',v['rgbSha256']) and p.get('station') in CLASSES
                and type(distance) in (float,int) and math.isfinite(distance) and 0 <= distance <= 360*1.65**2+.001
                and type(elapsed) in (float,int) and math.isfinite(elapsed) and elapsed >= 0,
                'Invalid live station hash, checkpoint, distance, timing or class')
        seen.add(fid)
        rows.append(dict(frameId=fid, sourceTimestamp100ns=source['timestamp100ns'], sourceEpoch=epoch,
                         native=e['station'], live=p['station'], liveSquaredDistance=distance,
                         liveRgbSha256=v['rgbSha256'], elapsedUs=elapsed))
    require(rows, 'Missing station RGB evaluations')
    return rows


def audit_landmarks(run, parts, events, frames, recordings, epoch, checkpoint, ffmpeg, ffprobe):
    """Check holdout independence and compare the logged live class with offline H.264 reclassification."""
    head = LandmarkRecognizer.load(checkpoint)
    require(head.data.get('trainingRuns'), 'Landmark checkpoint omits its training runs')
    hello = parts[0]['hello']
    ticks = [f['sourceFrame']['timestamp100ns'] for f in frames.values()]
    for train in head.data['trainingRuns']:
        require(train['runId'] != run['runId'] and train['lease'] != [hello['sessionId'],hello['ownerEpoch']]
                and (train['captureEpoch'] != epoch or max(ticks) < train['sourceInterval100ns'][0]
                     or min(ticks) > train['sourceInterval100ns'][1]), 'Landmark evaluation overlaps its training evidence')
    kinds = ('hybridStartVerified','hybridEndpointVerified')
    journal = []
    for entry in run['segments']:
        with (Path(recordings)/f"{entry['number']:05d}"/'events.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                event = json.loads(line)
                if event.get('type') in kinds:
                    journal.append(event)
                else:
                    require('visualStation' not in event, 'Landmark evaluation on a different event')
    rows = live_views([e for e in events if e['type'] in kinds], frames, journal, head.checkpoint_id, epoch)
    for entry, part in zip(run['segments'],parts):
        directory = Path(recordings)/f"{entry['number']:05d}"
        indexed, count = indexed_frames(directory, part)
        present = [r for r in rows if r['frameId'] in indexed]
        if not present:
            continue
        pixels = decode(directory,[indexed[r['frameId']] for r in present],count,ffmpeg,ffprobe)
        for r in present:
            ref = indexed[r['frameId']]
            rgb = pixels[ref['videoFrameIndex']]
            prediction = head.predict(rgb)
            r.update(videoIndex=ref['videoFrameIndex'], segment=entry['number'], videoPtsSeconds=ref['videoPtsSeconds'],
                     decodedRgbSha256=hashlib.sha256(rgb.tobytes()).hexdigest(), decoded=prediction['station'],
                     decodedSquaredDistance=prediction['squaredDistance'])
    require(all('decoded' in r for r in rows), 'A live landmark has no corresponding encoded frame')
    def confusion(key):
        counts = Counter((r['native'],r[key]) for r in rows)
        return {s: {p:counts[s,p] for p in CLASSES} for s in CLASSES}
    return dict(checkpointId=head.checkpoint_id, evaluated=len(rows), liveCorrect=sum(r['live']==r['native'] for r in rows),
                decodedCorrect=sum(r['decoded']==r['native'] for r in rows), liveVsDecodedMatches=sum(r['live']==r['decoded'] for r in rows),
                liveClassConfusion=confusion('live'), decodedClassConfusion=confusion('decoded'),
                medianLiveElapsedUs=statistics.median(r['elapsedUs'] for r in rows),
                byteIdenticalDecodedFrames=sum(r['liveRgbSha256']==r['decodedRgbSha256'] for r in rows),
                pixelEvidence='The original proposal journal records the live RGB digest. Offline predictions use independently decoded lossy H.264 frames at the exact source indexes.',
                sources=rows)
