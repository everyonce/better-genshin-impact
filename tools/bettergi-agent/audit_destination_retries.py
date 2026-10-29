"""Independently verify bounded stationary photo retries using original source frames and exact failed RGBs."""
import hashlib
import math
from pathlib import Path

from hybrid_routes import PATROL_STATIONS
from observation_timing import observation_timestamp


RETRY = 'hybridDestinationPhotoRetry'


def verify_retry_poses(events, frames, parts, receipts, confirm_first=False):
    """Join each retry to a unique original arrival and a continuous released, stationary capture interval."""
    from audit_hybrid_run import require
    endpoints = {e['samples'][-1]['frameId']:e for e in events if e['type'] == 'hybridEndpointVerified'}
    attempts = {}
    for index,event in enumerate(events):
        if event['type'] != RETRY:
            continue
        original = event.get('initialEndpointFrameId')
        endpoint = endpoints.get(original)
        require(endpoint is not None and index > 0, 'Photo retry has no original verified endpoint')
        history = attempts.setdefault(original,[])
        ordinal = len(history)+1
        anchor = history[-1] if history else endpoint
        previous = events[index-1]
        trigger = (anchor.get('photoSurveyVisit') or {}).get('outcome')
        require(((history and previous == anchor) or (not history and index >= 2 and events[index-2] == endpoint
                and previous['type'] == 'hybridDestinationVerified' and previous['frameId'] == original))
                and (trigger == 'classificationMiss' or trigger == 'confirmationPending'
                     and confirm_first and endpoint.get('destinationOrdinal') == 1)
                and 1 <= ordinal <= 3 and event.get('retryOrdinal') == ordinal,
                'Photo retry lacks an immediately preceding miss or exceeded its attempt budget')
        binding = ('routeId','sourceEpoch','releaseAtMs','releaseEpoch','arrivalFrameId','completedLegs','station',
                   'navigationMode','segmentIndex','destinationOrdinal','requestedDestination','fromStation','toStation','warmRequestId')
        require(all(k in endpoint and event.get(k) == endpoint[k] for k in binding)
                and endpoint['station'] == endpoint['requestedDestination'] == endpoint['toStation']
                and event['navigationMode'] == 'itinerary', 'Photo retry changed its released station, leg or request')
        samples = event.get('samples') or []
        require(len(samples) == 3 and event.get('frameId') == samples[-1]['frameId'] and event.get('atMs') == samples[-1]['atMs']
                and 0 < event['atMs']-endpoint['samples'][-1]['atMs'] <= 1500, 'Photo retry frame or deadline differs')
        reference = endpoint['samples'] + [s for h in history for s in h['samples']]
        for s in samples:
            f = frames.get(s['frameId']) or {}
            p = f.get('navigationPose') or {}
            prior = reference[-1]
            require(s['frameId'] > prior['frameId'] and s['atMs']-prior['atMs'] >= 80
                    and f.get('frameId') == p.get('frameId') == s['frameId'] and s['atMs'] == observation_timestamp(f)
                    and all(s[k] == p[k] for k in ('x','y','yawDegrees'))
                    and all(math.dist((s['x'],s['y']),(old['x'],old['y'])) <= 1.5
                            and abs((s['yawDegrees']-old['yawDegrees']+180)%360-180) <= 3 for old in reference),
                    'Photo retry reused old poses or changed position or heading')
            reference.append(s)
        prior_tick = frames[anchor['samples'][-1]['frameId']]['sourceFrame']['timestamp100ns']
        for f in sorted(frames.values(),key=lambda f:f['frameId']):
            if not anchor['samples'][-1]['frameId'] < f['frameId'] <= event['frameId']:
                continue
            p, gate, motion, src = (f[k] for k in ('navigationPose','frameWorldReadiness','motionEvidence','sourceFrame'))
            require(p.get('state') == 'valid' and p.get('frameId') == f['frameId'] and p.get('layerId') == 'City_102'
                    and .99 <= p['positionConfidence'] <= 1 and .2 <= p['yawConfidence'] <= 1
                    and math.dist((p['x'],p['y']),PATROL_STATIONS[event['station']]) <= 2
                    and all(math.dist((p['x'],p['y']),(s['x'],s['y'])) <= 1.5
                            and abs((p['yawDegrees']-s['yawDegrees']+180)%360-180) <= 3 for s in endpoint['samples'])
                    and src.get('captureEpoch') == event['sourceEpoch'] and src['timestamp100ns'] > prior_tick
                    and f.get('inputAvailable') is True
                    and gate.get('sourceFrame') == src and gate.get('sourceFrameId') == f['frameId'] and gate.get('ready') is True
                    and gate.get('epoch') == event['releaseEpoch'] and motion.get('status') == 'normal'
                    and motion.get('spaceKeyMatched') is False, 'Photo retry left its stationary ready release interval')
            prior_tick = src['timestamp100ns']
        lower = endpoint['releaseAtMs']
        require(not any(lower < r['acceptedAtMs'] <= event['atMs'] or lower < r['endedAtMs'] <= event['atMs']
                        or any(lower <= s['startedAtMs'] <= event['atMs'] for s in r['appliedSteps'])
                        for r in receipts.values())
                and not any(original < d['frameId'] <= event['frameId'] for p in parts
                            for d in [*p['decisions'],*p.get('navigationClimbActions',[])])
                and not any(original < (t.get('frameId') or 0) <= event['frameId'] and t.get('state')=='held'
                            for p in parts for t in p.get('controlTransitions',[])),
                'Photo retry contains intervening input, proposal or a second release')
        history.append(event)
    return attempts


def verify_retry_images(directory, visits, sources, head, confirm_first=False):
    """Hash every retained retry trigger and reproduce its actual agreement or miss."""
    from audit_hybrid_run import require
    from PIL import Image
    witnessed = []
    source = {s['frameId']:s for s in sources}
    for row in visits:
        reason = row.get('outcome')
        if reason not in ('classificationMiss','confirmationPending'):
            require('retryEvidenceFile' not in row and 'retryEvidencePngSha256' not in row,
                    'Photo retry evidence requires a real classification miss')
            continue
        s = source[row['frameId']]
        expected = f"retry-evidence/{row['station']}-frame-{row['frameId']}.png"
        require(row.get('retryEvidenceFile') == expected, 'Missing original image for a destination classification miss')
        path = Path(directory)/expected
        require(hashlib.sha256(path.read_bytes()).hexdigest() == row.get('retryEvidencePngSha256'),
                'Failed destination PNG digest differs')
        with Image.open(path) as im:
            require(im.format == 'PNG' and im.mode == 'RGB' and im.size == (192,192) and getattr(im,'n_frames',1) == 1,
                    'Failed destination evidence must be one original-size RGB PNG')
            raw = im.tobytes()
        agrees = s['native'] == s['live']
        require(s['native'] == row['station'] and (not agrees if reason=='classificationMiss' else confirm_first and agrees)
                and hashlib.sha256(raw).hexdigest() == s['liveRgbSha256']
                and head.predict(raw) == dict(station=s['live'],squaredDistance=s['liveSquaredDistance']),
                'Failed destination image does not reproduce the original frozen classifier miss')
        witnessed.append(dict(frameId=row['frameId'],outcome=reason,predicted=s['live'],expected=s['native'],path=str(path.resolve()),
                              pngSha256=row['retryEvidencePngSha256']))
    require({p.name for p in (Path(directory)/'retry-evidence').glob('*.png')} ==
            {Path(w['path']).name for w in witnessed}, 'Unattributed failed destination images')
    return witnessed
