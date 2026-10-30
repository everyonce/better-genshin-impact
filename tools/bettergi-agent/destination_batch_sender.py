"""Publish one addressed, immutable destination batch after the live predecessor has applied input."""
import hashlib
import json
import os
import re
import time
import uuid

from hybrid_routes import itinerary_legs
from destination_queue_policy import choose
from destination_queue_limits import queue_limits
import run_rdp_patrol as patrol
from warm_photo_requests import validate_plan


def read_json(path):
    """Read a bounded local control document without accepting an oversized payload."""
    with path.open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('Oversized destination batch document')
    return json.loads(raw)


def encode(value):
    """Freeze a deterministic UTF-8 payload before committing its digest."""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')


def exclusive_bytes(path, raw, clock=None):
    """Publish complete bytes by no-replace hard link on the same NTFS volume."""
    staging = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        with staging.open('xb') as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        before = clock() if clock else None
        if clock and before is None:
            raise ValueError('Windows QPC unavailable for batch publication')
        os.link(staging, path)
        if clock:
            after = clock()
            if not after or before[0] != after[0] or before[1] > after[1]:
                raise ValueError('Windows QPC changed at batch publication')
            return dict(clock='windows-query-performance-counter', frequencyHz=before[0],
                        beforeTicks=before[1], afterTicks=after[1])
    finally:
        staging.unlink(missing_ok=True)


def create_plan(start, destinations):
    """Assign fresh request identities only after a sender has an eligible lease witness."""
    plan = dict(version=2, mode='destinations', start=start, requests=[
        dict(id=uuid.uuid4().hex, name=name, destination=station, targets=[station]) for name, station in destinations])
    validate_plan(plan)
    return plan


def qualification_goals(start, batch, witness_frame):
    """Generate four requests totaling exactly seven surveyed legs from any predecessor station."""
    a, b, c = 'stair-front', 'sidewalk-junction', 'west-lamp'
    if start == b:
        first, other = (a,c) if witness_frame % 2 else (c,a)
        path = (first,other,first,other)
    else:
        far = c if start == a else a
        path = (far,start,far,b)
    return [(f'b{batch:02d}-g{i:02d}-{s}', s) for i,s in enumerate(path,1)]


def admitted_plans(folder):
    """Read operator commitments in sequence, separately from the files received by the resident."""
    summary = read_json(folder/'warm-launcher.json')
    limits = queue_limits(summary.get('queueLimitsProfile'))
    count = summary.get('batchCount')
    if type(count) is not int or not 2 <= count <= limits.batches:
        raise ValueError('Invalid declared batch count for committed plan history')
    plans = [read_json(folder/'photo-requests.json')]
    for ordinal in range(2,count+2):
        path = folder/'batches'/f'{ordinal:05d}.intent.json'
        if not path.exists():
            break
        intent = read_json(path)
        if intent.get('kind')=='finish':
            break
        plans.append(intent['plan'])
    return plans


def witness_for(folder, status, plans):
    """Bind the observed applied software receipt to the addressed run, batch and request, independent of polling time."""
    batch = status.get('batchOrdinal')
    if type(batch) is not int or not 1 <= batch <= len(plans) or status.get('version') != 1:
        raise ValueError('Invalid active destination batch')
    applied = status.get('activeFirstAppliedRequestId')
    if applied is None:
        return None
    run_id = status['runId']
    if (not isinstance(run_id,str) or not re.fullmatch('[a-f0-9]{32}',run_id)
            or not isinstance(applied,str) or not re.fullmatch('[a-f0-9]{32}',applied)
            or type(status.get('activeFirstAppliedFrameId')) is not int or status['activeFirstAppliedFrameId'] < 1
            or not all(isinstance(status.get(k),str) and status[k] for k in ('sessionId','ownerEpoch'))
            or patrol.pin_resident(folder) != run_id
            or patrol.addressed_control(folder/'patrol.json.control.json', run_id)['command'] != 'run'):
        raise ValueError('Applied witness does not belong to an active addressed resident')
    prev = folder/'photo-requests.json' if batch == 1 else folder/'batches'/f'{batch:05d}.json'
    digest = hashlib.sha256(prev.read_bytes()).hexdigest()
    local = status['activeOrdinal'] - sum(len(p['requests']) for p in plans[:batch-1]) - 1
    requests = plans[batch-1]['requests']
    if (status.get('batchSha256') != digest or not 0 <= local < len(requests)
            or status.get('activeRequestId') != requests[local]['id']):
        raise ValueError('Applied witness differs from its previously published batch')
    return dict(batchOrdinal=batch,requestId=requests[local]['id'],nativeRequestId=applied,
                frameId=status['activeFirstAppliedFrameId'])


def submit(folder, expected_batch, destinations=None, admit=None, *, finish=False):
    """Commit and deliver a single dynamically selected successor under an exclusive per-batch issuer claim."""
    summary = read_json(folder/'warm-launcher.json')
    limits = queue_limits(summary.get('queueLimitsProfile'))
    opened = summary.get('openQueue') is True
    if (summary.get('status') != 'running' or summary.get('computer','').split('.')[0].upper() != 'SIREN'
            or (folder/'STOP').exists()
            or not 2 <= expected_batch <= summary['batchCount']+int(opened) or summary['batchCount']>limits.batches
            or finish and (not opened or destinations is not None)
            or summary.get('stopInBatch') and expected_batch > summary['stopInBatch']):
        raise ValueError('Destination queue is closed or outside its published bounds')
    prefix = folder/'batches'/f'{expected_batch:05d}'
    if prefix.with_suffix('.intent.json').exists():
        raise ValueError('Destination slot already claimed')
    plans = admitted_plans(folder)
    if len(plans) != expected_batch-1:
        raise ValueError('Destination batch is already claimed or its predecessor is missing')
    try:
        status = read_json(folder/'station-photos'/'warm-status.json')
    except (FileNotFoundError,PermissionError):
        return None
    if status.get('batchOrdinal',0) < expected_batch-1:
        return None
    if status.get('complete') or status.get('batchOrdinal') != expected_batch-1:
        raise ValueError('Stale or completed destination lease')
    resident = read_json(folder/'patrol.json.status.json')
    if resident.get('runId') != status.get('runId') or resident.get('state') in ('completed','failed','stopped'):
        raise ValueError('Inactive or mismatched resident')
    witness = witness_for(folder, status, plans)
    if not witness:
        return None
    observed = time.monotonic_ns()
    if admit is not None:
        admit(folder, status)
    start = plans[-1]['requests'][-1]['destination']
    basis = None
    if opened:
        policy_raw = (folder/'queue-policy.json').read_bytes()
        policy = json.loads(policy_raw)
        if (hashlib.sha256(policy_raw).hexdigest()!=summary['queuePolicySha256'] or policy['maxLegs']!=summary['maxLegs']
                or policy.get('queueLimitsProfile')!=summary.get('queueLimitsProfile') or policy['maxLegs']>limits.legs
                or policy['mode']!=summary['planner']['mode'] or policy['targetGameplaySeconds']!=summary['planner']['targetGameplaySeconds']
                or policy['maxBatches']!=summary['batchCount'] or policy['initialPlanSha256']!=hashlib.sha256((folder/'photo-requests.json').read_bytes()).hexdigest()):
            raise ValueError('Open queue policy changed')
        # Read operator commitments only after the addressed resident has admitted this exact predecessor.
        for ordinal,prior in enumerate(plans[1:],2):
            stem = folder/'batches'/f'{ordinal:05d}'
            prior_raw = stem.with_suffix('.json').read_bytes()
            intent = read_json(stem.with_suffix('.intent.json'))
            if hashlib.sha256(prior_raw).hexdigest()!=intent['batchSha256'] or json.loads(prior_raw).get('plan')!=prior:
                raise ValueError('Open queue admitted plan differs from its original published intent')
        basis = choose(policy,plans,status,witness,expected_batch,destinations,finish)
        finish = not basis['selectedStations']
        if destinations is None and not finish:
            destinations = [(f'open-{expected_batch:02d}-{i:02d}-{s}',s) for i,s in enumerate(basis['selectedStations'],1)]
    if finish:
        content = dict(kind='finish')
    else:
        if destinations is None:
            destinations = qualification_goals(start, expected_batch, witness['frameId'])
        plan = create_plan(start, destinations)
        names = [r['name'] for p in (*plans,plan) for r in p['requests']]
        legs = sum(len(itinerary_legs(p['start'],[r['destination'] for r in p['requests']])) for p in (*plans,plan))
        reserve = 0 if opened else 2*(summary['batchCount']-expected_batch)
        if len(set(names)) != len(names) or legs+reserve > summary['maxLegs']:
            raise ValueError('Duplicate goal name or destination batch exceeds the authorized leg cap')
        content = dict(plan=plan)
    identity = {k:status[k] for k in ('runId','sessionId','ownerEpoch')}
    binding = dict(**identity,batchOrdinal=expected_batch,previousSha256=status['batchSha256'],witness=witness)
    payload = encode(dict(version=1, mode='destination-batch', **binding, **content))
    evidence = dict(version=1, **binding, batchSha256=hashlib.sha256(payload).hexdigest(), observedAtMonotonicNs=observed)
    if basis is not None:
        decision = encode(dict(type='destinationQueueDecision',**evidence,policySha256=summary['queuePolicySha256'],**basis))
        evidence['policyDecisionSha256'] = hashlib.sha256(decision).hexdigest()
    # The intent is the single-writer claim. A losing or interrupted sender can never overwrite a batch.
    exclusive_bytes(prefix.with_suffix('.intent.json'), encode(dict(**evidence,type='destinationBatchIntent',**content)))
    if basis is not None:
        exclusive_bytes(prefix.with_suffix('.decision.json'),decision)
    if (folder/'STOP').exists() or patrol.addressed_control(folder/'patrol.json.control.json',status['runId'])['command'] != 'run':
        raise ValueError('Stopped before destination batch publication')
    bracket = exclusive_bytes(prefix.with_suffix('.json'), payload, patrol.native_qpc_sample)
    exclusive_bytes(prefix.with_suffix('.publication.json'), encode(dict(**evidence,type='destinationBatchPublished',
                    publishedAtMonotonicNs=time.monotonic_ns(),publicationQpc=bracket)))
    return evidence
