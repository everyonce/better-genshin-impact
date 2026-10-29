"""Independently verify bounded stationary photo retries using original source frames and exact failed RGBs."""
import hashlib
import math
from pathlib import Path

from hybrid_routes import PATROL_STATIONS
from observation_timing import observation_timestamp


RETRY = 'hybridDestinationPhotoRetry'
RELEASE_REJECTED = 'hybridEndpointReleaseRejected'
RELEASE_RETRY = 'hybridEndpointReleaseRetryReady'


def verify_release_order(trace, endpoints):
    """Check cross-type order in the original journal, which the separate summary arrays cannot prove."""
    from audit_hybrid_run import require
    for end in endpoints:
        if end['type'] != 'hybridEndpointVerified' or 'firstArrivalFrameId' not in end:
            continue
        first, second = end['firstArrivalFrameId'],end['arrivalFrameId']
        expected=[('held',first),(RELEASE_REJECTED,first),(RELEASE_RETRY,second),('held',second),
                  ('hybridEndpointVerified',second)]
        require([t for t in trace if t in expected]==expected, 'Original rejected/retried release journal order differs')


def verify_release_reissues(events,frames,parts,receipts):
    """Require a real rejected R57 readback, stopped input and an independently acknowledged fresh release."""
    from audit_hybrid_run import require
    rejected = [e for e in events if e['type']==RELEASE_REJECTED]
    ready = [e for e in events if e['type']==RELEASE_RETRY]
    ends = [e for e in events if e['type']=='hybridEndpointVerified' and 'firstArrivalFrameId' in e]
    require(len(rejected)==len(ready)==len(ends), 'Endpoint release retry is unpaired or repeated')
    transitions = [t for p in parts for t in p['controlTransitions'] if t.get('state')=='held'
                   and t.get('reason')=='hybridEndpoint']
    anomalous = [t['frameId'] for t in transitions if 'warmRelease' in t
                 and t['warmRelease'].get('readinessReason') != 'client_release']
    require(anomalous == [e['firstArrivalFrameId'] for e in rejected], 'Unreported or fabricated rejected release')
    proposals = [d for p in parts for d in [*p['decisions'],*p.get('navigationClimbActions',[])]]
    proofs=[]
    for bad, retry, end in zip(rejected,ready,ends):
        first, second = bad['firstArrivalFrameId'], end['arrivalFrameId']
        require(events.index(bad) < events.index(retry) < events.index(end) and first < second
                and end['firstArrivalFrameId']==retry['firstArrivalFrameId']==first and retry['retryArrivalFrameId']==second
                and end['completedLegs']==bad['completedLegs']+1 and retry['completedLegs']==bad['completedLegs'],
                'Retry did not belong to one originally failed arrival on the same edge')
        binding = ('routeId','station','sourceEpoch','navigationMode','segmentIndex','fromStation','toStation',
                   'destinationOrdinal','requestedDestination','warmRequestId')
        require(all(k in end and bad.get(k)==retry.get(k)==end[k] for k in binding),
                'Release retry changed its request, target or capture')
        original,accepted = ([t for t in transitions if t['frameId']==f] for f in (first,second))
        require(len(original)==len(accepted)==1 and original[0]['warmRequestId']==accepted[0]['warmRequestId']==end['warmRequestId'],
                'Release retry lacks two owned held transitions')
        rejected_ack, accepted_ack = original[0]['warmRelease'], accepted[0]['warmRelease']
        gate,x = bad['rejectedReadiness'],bad['rejectedExecution']
        last, tracked = x['lastInputEvent'],x['trackedState']
        before, after = bad['arrivalEpoch'],end['releaseEpoch']
        at = bad['rejectedAtMs']
        require(original[0].get('rejectedReadiness')==gate and original[0].get('rejectedExecution')==x
                and rejected_ack['type']=='released' and rejected_ack['policyHistoryReset'] is True
                and rejected_ack['arrivalFrameId']==first and rejected_ack['serverNowMs']==at
                and rejected_ack['readinessEpoch']==gate['epoch']==before+1 and gate['epoch']+1==after
                and rejected_ack['captureEpoch']==gate['sourceFrame']['captureEpoch']==end['sourceEpoch']
                and gate['ready'] is False and rejected_ack['readinessReady'] is False
                and rejected_ack['readinessReason']==gate['reason']=='world_observation_invalidated'
                and x.get('telemetryComplete') is True and 'active' in x and x['active'] is None and tracked.get('heldKeys')==[]
                and tracked.get('telemetryIncomplete') is False and tracked.get('releaseOutcome')=='returned_unverified'
                and last.get('origin')=='release:client_release' and last['call'].get('operation')=='releaseAll'
                and last['call'].get('stage')=='returned_unverified' and last['call'].get('error') is None
                and observation_timestamp(frames[first]) <= last['atMs'] <= x['sampledAtMs'] <= at+.001,
                'Rejected R57 readback lacks its original stale gate and acknowledged empty software state')
        require(accepted_ack['type']=='released' and accepted_ack['arrivalFrameId']==second
                and accepted_ack['readinessReason']=='client_release' and accepted_ack['readinessReady'] is False
                and accepted_ack['serverNowMs']==end['releaseAtMs'] and accepted_ack['captureEpoch']==end['sourceEpoch']
                and accepted_ack['readinessEpoch']==after and accepted_ack.get('policyHistoryReset') is True,
                'Retry never earned a genuine second client_release acknowledgement')
        samples=retry['samples']
        require(len(samples)==2 and first<samples[0]['frameId']<samples[1]['frameId']==second
                and at<samples[0]['atMs'] and samples[1]['atMs']-samples[0]['atMs']>=80
                and samples[1]['atMs'] <= end['releaseAtMs'] <= at+650,
                'Second release lacks two distinct fresh post-rejection poses inside the wait budget')
        origin=frames[first]['navigationPose']
        for fid in (first,*[s['frameId'] for s in samples]):
            f=frames[fid]
            p,g,src,m=(f[k] for k in ('navigationPose','frameWorldReadiness','sourceFrame','motionEvidence'))
            require(f['frameId']==p['frameId']==g['sourceFrameId']==fid and p['state']=='valid' and p['layerId']=='City_102'
                    and .99<=p['positionConfidence']<=1 and .2<=p['yawConfidence']<=1 and g.get('ready') is True
                    and g['sourceFrame']==src and g['epoch']==(before if fid==first else before+1)
                    and f['inputAvailable'] is True and src['captureEpoch']==end['sourceEpoch']
                    and m['status']=='normal' and m['spaceKeyMatched'] is False
                    and math.dist((p['x'],p['y']),PATROL_STATIONS[end['station']])<=1.1
                    and math.dist((p['x'],p['y']),(origin['x'],origin['y']))<=1.5
                    and abs((p['yawDegrees']-origin['yawDegrees']+180)%360-180)<=3,
                    'Release retry source does not prove fresh stationary poses at the original target')
        for s in samples:
            f=frames[s['frameId']]
            require(s['atMs']==observation_timestamp(f) and all(s[k]==f['navigationPose'][k] for k in ('x','y','yawDegrees')),
                    'Release retry pose differs from its original ready source')
        require(observation_timestamp(frames[first]) <= at and
                not any(first <= d['frameId'] <= second for d in proposals)
                and not any(at < r['acceptedAtMs'] <= end['releaseAtMs'] or at < r['endedAtMs'] <= end['releaseAtMs']
                            or any(at <= s['startedAtMs'] <= end['releaseAtMs'] for s in r['appliedSteps'])
                            for r in receipts.values())
                and not any(first<t['frameId']<second for t in transitions), 'New input or another release during retry hold')
        proofs.append(dict(firstArrivalFrameId=first,retryArrivalFrameId=second,rejectedEpoch=before+1,
                           acceptedEpoch=after,station=end['station'],rejectedAtMs=at,acceptedReleaseAtMs=end['releaseAtMs']))
    return proofs


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
