"""Offline joins between the external producer, immutable request bytes and native resident admission."""
import hashlib
import json
import math
from pathlib import Path

from audit_hybrid_run import batch_edges, require
from hybrid_routes import PATROL_STATIONS
from observation_timing import observation_timestamp


def canonical_digest(doc):
    """Hash the sorted ASCII representation used by the resident for a parsed batch plan."""
    return hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()


def bounded_bytes(path,limit):
    """Read one local evidence record within its producer or consumer byte allowance."""
    with path.open('rb') as source:
        raw=source.read(limit+1)
    require(0<len(raw)<=limit,'Batch evidence record exceeds its byte allowance')
    return raw


def read_batches(folder, plans, initial_bytes, admission, run, stopped):
    """Match each external committed intent to its unique, untouched envelope and publication acknowledgement."""
    count, cap = admission.get('batchCount'), admission.get('maxLegs')
    require(type(count) is int and 2 <= count <= 12 and type(cap) is int and 2*count <= cap <= 96
            and 1 < len(plans) <= count and (stopped or len(plans) == count)
            and len(batch_edges(plans)) <= cap, 'Invalid queue batch count or total leg budget')
    stop_batch = admission.get('stopInBatch')
    require((type(stop_batch) is int and 2 <= stop_batch == len(plans)
             and admission.get('stopRule') == 'first-request-first-applied') if stopped
            else stop_batch is None and admission.get('stopRule') is None, 'Queue stop differs from its declared rule')
    ids = [r['id'] for p in plans for r in p['requests']]
    names = [r['name'] for p in plans for r in p['requests']]
    require(len(ids) == len(set(ids)) and len(names) == len(set(names)), 'Batch queue reused a request ID or name')
    queue = Path(folder)/'batches'
    files = set()
    batch = dict(batchOrdinal=1,batchSha256=hashlib.sha256(initial_bytes).hexdigest(),
                 batchPlanSha256=canonical_digest(plans[0]),firstRequestOrdinal=1,plan=plans[0])
    batches = [batch]
    for n in range(1,len(plans)+1):
        require(len(batch_edges(plans[:n])) + 2*(count-n) <= cap, 'Insufficient remaining budget for announced batches')
    for n,plan in enumerate(plans[1:],2):
        key = f'{n:05d}'
        packets = [key+suffix for suffix in ('.json','.intent.json','.publication.json')]
        files.update(packets)
        raw = bounded_bytes(queue/packets[0],16384)
        envelope = json.loads(raw)
        intent, published = (json.loads(bounded_bytes(queue/name,65536)) for name in packets[1:])
        common = ('version','runId','sessionId','ownerEpoch','batchOrdinal','previousSha256','witness')
        require(set(envelope) == {*common,'mode','plan'} and envelope.get('mode') == 'destination-batch'
                and set(intent) == {*common,'type','plan','batchSha256','observedAtMonotonicNs'}
                and set(published) == {*common,'type','batchSha256','observedAtMonotonicNs','publishedAtMonotonicNs','publicationQpc'}
                and intent['type'] == 'destinationBatchIntent' and published['type'] == 'destinationBatchPublished'
                and all(envelope[k] == intent[k] == published[k] for k in common)
                and type(envelope['version']) is int and envelope['version'] == 1 and envelope['runId'] == run['runId']
                and type(envelope['batchOrdinal']) is int and envelope['batchOrdinal'] == n
                and envelope['previousSha256'] == batch['batchSha256'] and envelope['plan'] == intent['plan'] == plan
                and set(plan) == {'version','mode','start','requests'}
                and all(set(r) == {'id','name','destination','targets'} for r in plan['requests'])
                and set(envelope['witness']) == {'batchOrdinal','requestId','nativeRequestId','frameId'}
                and type(envelope['witness']['batchOrdinal']) is int and envelope['witness']['batchOrdinal'] == n-1
                and type(envelope['witness']['frameId']) is int, 'External intent, publication or batch chain differs')
        expected = {**{k:intent[k] for k in common},'mode':'destination-batch','plan':intent['plan']}
        require(raw == json.dumps(expected,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8'),
                'Consumed envelope bytes differ from the independently committed sender intent')
        digest = hashlib.sha256(raw).hexdigest()
        observed = intent['observedAtMonotonicNs']
        require(digest == intent['batchSha256'] == published['batchSha256'] and type(observed) is int and observed > 0
                and published['observedAtMonotonicNs'] == observed and type(published['publishedAtMonotonicNs']) is int
                and published['publishedAtMonotonicNs'] >= observed, 'Consumed bytes or sender chronology differs')
        batch = dict(batchOrdinal=n,batchSha256=digest,batchPlanSha256=canonical_digest(plan),
                     firstRequestOrdinal=batch['firstRequestOrdinal']+len(batch['plan']['requests']),plan=plan,
                     bytes=len(raw),envelope=envelope,publication=published)
        batches.append(batch)
    require({p.name for p in queue.iterdir()} == files, 'Unaccounted or missing file in the batch inbox')
    return batches


def verify_batch_events(events, batches, groups, frames, clock, specs, stopped, decisions):
    """Prove staged successors used a real preceding software dispatch and were consumed only at the released handoff."""
    active_specs = {r['id'] for r in specs}
    by_id = {r['id']:(batch,n) for batch in batches for n,r in enumerate(batch['plan']['requests'],batch['firstRequestOrdinal'])}
    by_group = {r['id']:g for r,g in zip(specs,groups)}
    require((len(specs) < len(by_id)) if stopped else len(specs) == len(by_id),
            'Queue stop/completion differs from its declared request prefix')
    markers = [e for e in events if e.get('type','').startswith('warmBatch')]
    accepted = [b for b in batches[1:] if b['plan']['requests'][0]['id'] in active_specs]
    require(len(markers) == len(accepted) == len(batches)-1 and all(e['type'] == 'warmBatchAccepted' for e in markers),
            'Missing, duplicated or orphan resident batch admission')
    for e in events:
        if not e.get('type','').startswith(('warmPhoto','warmBatch')):
            continue
        owner = by_id.get(e.get('warmRequestId'))
        require(owner and (e.get('batchOrdinal'),e.get('batchSha256'),e.get('batchPlanSha256'),e.get('ordinal')) ==
                (owner[0]['batchOrdinal'],owner[0]['batchSha256'],owner[0]['batchPlanSha256'],owner[1]),
                'Lifecycle event has wrong request or batch scope')
    def ticks(ms):
        return clock['originTicks']+round(ms*clock['frequency']/1000)
    proofs = []
    for b in batches[1:]:
        env, pub = b['envelope'], b['publication']
        witness = env['witness']
        previous = batches[b['batchOrdinal']-2]
        prior_group = by_group.get(witness['requestId'])
        bracket = pub['publicationQpc']
        require(prior_group and by_id[witness['requestId']][0] == previous and env['sessionId'] == clock['sessionId']
                and env['ownerEpoch'] == clock['ownerEpoch'] and witness['nativeRequestId'] == prior_group[0]['nativeRequestId']
                and witness['frameId'] == prior_group[0]['frameId'] and isinstance(bracket,dict) and
                set(bracket) == {'clock','frequencyHz','beforeTicks','afterTicks'}
                and bracket['clock'] == 'windows-query-performance-counter' and bracket['frequencyHz'] == clock['frequency']
                and all(type(bracket[k]) is int for k in ('beforeTicks','afterTicks','frequencyHz'))
                and prior_group[0]['terminalEndTicks'] <= bracket['beforeTicks'] <= bracket['afterTicks'],
                'Publication did not follow an original receipt under its active predecessor lease')
        proof = dict(batchOrdinal=b['batchOrdinal'],previousSha256=env['previousSha256'],batchSha256=b['batchSha256'],
                     batchPlanSha256=b['batchPlanSha256'],bytes=b['bytes'],publicationWitness=witness,publicationQpc=bracket,
                     witnessToPublicationMs=[(bracket[k]-prior_group[0]['terminalEndTicks'])*1000/clock['frequency']
                                             for k in ('beforeTicks','afterTicks')])
        mark = markers[b['batchOrdinal']-2]
        pos = events.index(mark)
        require(0 < pos < len(events)-2, 'Batch acceptance lacks its request-release neighbors')
        done, switch, start = events[pos-1],events[pos+1],events[pos+2]
        old = previous['plan']['requests'][-1]['id']
        new = b['plan']['requests'][0]['id']
        fid = done['frameId']
        qpc = mark['consumedQpc']
        require(done['type'] == 'warmPhotoRequestCompleted' and switch['type'] == 'warmPhotoHandoff'
                and start['type'] == 'warmPhotoRequestStarted' and mark['warmRequestId'] == done['warmRequestId'] == old
                and switch['warmRequestId'] == old and switch['nextRequestId'] == start['warmRequestId'] == new
                and mark['frameId'] == switch['frameId'] == start['frameId'] == fid
                and mark['sourceEpoch'] == done['sourceEpoch'] and mark['completedLegs'] == done['completedLegs']
                and mark['release'] == done['release'] and mark['pendingActionIds'] == []
                and mark['lastAcceptedRequestId'] == done['lastAcceptedRequestId']
                and all(k in done and mark.get(k) == done[k] for k in
                        ('goalEmbeddingSha256','planSha256','name','targets','destination'))
                and all(mark.get(k) == done.get(k) for k in ('initialEndpointFrameId','retryOrdinal','firstConfirmedFrameId'))
                and mark['nextBatchOrdinal'] == b['batchOrdinal'] and mark['nextBatchSha256'] == b['batchSha256']
                and mark['nextBatchPlanSha256'] == b['batchPlanSha256'] and mark['nextBatchBytes'] == b['bytes']
                and mark['nextRequestId'] == new and mark['publicationWitness'] == witness
                and mark['runId'] == env['runId'] and mark['sessionId'] == clock['sessionId'] and mark['ownerEpoch'] == clock['ownerEpoch'],
                'Resident admission is not bound to the exact published bytes and released old-request boundary')
        require(isinstance(qpc,dict) and set(qpc) == {'clock','frequencyHz','ticks'}
                and qpc['clock'] == bracket['clock'] and qpc['frequencyHz'] == clock['frequency'] and type(qpc['ticks']) is int
                and bracket['afterTicks'] <= qpc['ticks'] <= ticks(by_group[new][0]['acceptedAtMs'])
                and ticks(done['release']['serverNowMs']) <= ticks(observation_timestamp(frames[fid])) <= qpc['ticks'],
                'Late publication, early consumption or premature successor input')
        admitted_at = mark.get('admissionFrameId')
        require(type(admitted_at) is int and fid <= admitted_at < by_group[new][0]['frameId'] and admitted_at in frames,
                'Successor admission lacks an original released source before new input')
        require(all(d['frameId'] > admitted_at and (d['acceptance'].get('type') != 'accepted'
                    or ticks(d['acceptance']['acceptedAtMs']) >= qpc['ticks'])
                    for d in decisions if d.get('warmRequestId') == new),
                'Successor proposed or admitted an action before the original batch admission')
        at = ticks(observation_timestamp(frames[admitted_at]))
        require(0 <= (qpc['ticks']-at)*1000/clock['frequency'] <= 150 and
                (qpc['ticks']-ticks(observation_timestamp(frames[fid])))*1000/clock['frequency'] <= 1000,
                'Successor release wait or admission freshness budget exceeded')
        pose = frames[fid]['navigationPose']
        station = previous['plan']['requests'][-1]['destination']
        for i,f in frames.items():
            if not fid <= i <= admitted_at:
                continue
            p,g,m,src=(f[k] for k in ('navigationPose','frameWorldReadiness','motionEvidence','sourceFrame'))
            require(f.get('inputAvailable') is True and g.get('ready') is True and g.get('sourceFrameId') == i
                    and g.get('sourceFrame') == src and src.get('captureEpoch') == done['sourceEpoch']
                    and g.get('epoch') == done['release']['readinessEpoch'] and p.get('frameId') == i
                    and p.get('state') == 'valid' and p.get('layerId') == 'City_102' and .99 <= p['positionConfidence'] <= 1
                    and .2 <= p['yawConfidence'] <= 1 and m.get('status') == 'normal' and m.get('spaceKeyMatched') is False
                    and math.dist((p['x'],p['y']),PATROL_STATIONS[station]) <= 2
                    and math.dist((p['x'],p['y']),(pose['x'],pose['y'])) <= 1.5
                    and abs((p['yawDegrees']-pose['yawDegrees']+180)%360-180) <= 3,
                    'Admission left the released destination or changed its source or readiness epoch')
        proofs.append(dict(proof,status='accepted',oldRequestId=old,newRequestId=new,boundaryFrameId=fid,
                      admissionFrameId=admitted_at,consumedQpc=qpc,
                      releasedBoundaryToReadMs=(qpc['ticks']-ticks(observation_timestamp(frames[fid])))*1000/clock['frequency'],
                      stagedBeforeRelease=bracket['afterTicks'] <= ticks(done['release']['serverNowMs'])))
    return proofs
