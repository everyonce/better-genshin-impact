"""Independently reconstruct the external scheduler, its terminal envelope, and the released native ownership boundary."""
from collections import Counter
import hashlib
from itertools import product
import json

from audit_hybrid_run import require
from audit_warm_batches import bounded_bytes, verify_settled_wait
from observation_timing import observation_timestamp

STATIONS=('stair-front','sidewalk-junction','west-lamp')
APPROACHES=('stair-front>sidewalk-junction','sidewalk-junction>stair-front',
            'sidewalk-junction>west-lamp','west-lamp>sidewalk-junction')


def route_stats(origin, destinations):
    """Count physical graph edges and terminal approaches without importing the producer's planner."""
    legs=0
    used=Counter(dict.fromkeys(APPROACHES,0))
    for dest in destinations:
        i,j=STATIONS.index(origin),STATIONS.index(dest)
        require(i!=j,'Consecutive duplicate destination')
        legs+=abs(i-j)
        used[STATIONS[j-(1 if i<j else -1)]+'>'+dest]+=1
        origin=dest
    return legs,used


def best_destinations(origin, budget, requested, verified, approaches, fid):
    """Rank every feasible destination sequence using the public rule and a camera-frame tie break."""
    rotated=STATIONS[fid%3:]+STATIONS[:fid%3]
    for count in (4,3,2):
        candidates=[]
        for seq in product(rotated,repeat=count):
            if any(a==b for a,b in zip((origin,*seq),seq)):
                continue
            legs,app=route_stats(origin,seq)
            if legs<=budget:
                counts=Counter(seq)
                score=tuple(sum((before[k]+added[k])**2 for k in before) for before,added in
                            ((requested,counts),(verified,counts),(approaches,app)))
                candidates.append((score+(-legs,tuple(rotated.index(s) for s in seq)),seq))
        if candidates:
            return list(min(candidates)[1])
    return []


def finish_packet(folder,batch,run_id):
    """Require all three external sender artifacts to reconstruct a single exact terminal message."""
    n=batch['batchOrdinal']+1
    pre=folder/'batches'/f'{n:05d}'
    raw=bounded_bytes(pre.with_suffix('.json'),16384)
    envelope=json.loads(raw)
    intent_raw,pub_raw=(bounded_bytes(pre.with_suffix(x),65536) for x in ('.intent.json','.publication.json'))
    intent,pub=json.loads(intent_raw),json.loads(pub_raw)
    common=('version','runId','sessionId','ownerEpoch','batchOrdinal','previousSha256','witness')
    require(set(envelope)=={*common,'mode','kind'} and envelope['kind']=='finish' and envelope['mode']=='destination-batch'
            and set(intent)=={*common,'kind','batchSha256','observedAtMonotonicNs','type','policyDecisionSha256'} and intent['kind']=='finish'
            and set(pub)=={*common,'batchSha256','observedAtMonotonicNs','publishedAtMonotonicNs','publicationQpc','type','policyDecisionSha256'}
            and intent['type']=='destinationBatchIntent' and pub['type']=='destinationBatchPublished'
            and all(envelope[k]==intent[k]==pub[k] for k in common) and type(envelope['version']) is int and envelope['version']==1
            and type(envelope['batchOrdinal']) is int and envelope['batchOrdinal']==n and envelope['runId']==run_id
            and envelope['previousSha256']==batch['batchSha256'] and type(pub['observedAtMonotonicNs']) is int and
            0<intent['observedAtMonotonicNs']==pub['observedAtMonotonicNs']<=pub['publishedAtMonotonicNs'],
            'Finish intent, addressed owner, slot, or publication chronology differs')
    expected=dict({k:intent[k] for k in common},mode='destination-batch',kind='finish')
    digest=hashlib.sha256(raw).hexdigest()
    require(intent['policyDecisionSha256']==pub['policyDecisionSha256']==hashlib.sha256(
            bounded_bytes(pre.with_suffix('.decision.json'),65536)).hexdigest(),'Finish policy bytes differ from immutable intent')
    require(raw==json.dumps(expected,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
            and digest==intent['batchSha256']==pub['batchSha256'],'Finish bytes differ from immutable external intent')
    return dict(batchOrdinal=n,batchSha256=digest,bytes=len(raw),envelope=envelope,publication=pub,
                intentSha256=hashlib.sha256(intent_raw).hexdigest(),publicationSha256=hashlib.sha256(pub_raw).hexdigest())


def verify_policy(folder,admission,parts,run_id):
    """Verify the prelaunch supervisor cap, objective, and reserved RDP process/nonce pairs."""
    raw=bounded_bytes(folder/'queue-policy.json',65536)
    policy=json.loads(raw)
    owner=bounded_bytes(folder/'required-owner.json',4*1024*1024)
    record=json.loads(owner)
    digest=hashlib.sha256(raw).hexdigest()
    planner=admission['planner']
    require(set(policy)=={'version','mode','targetGameplaySeconds','goalsPerBatch','maxBatches','maxLegs','initialPlanSha256','requiredOwnerManifestSha256'}
            and planner=={k:policy[k] for k in ('version','mode','targetGameplaySeconds','goalsPerBatch')}
            and policy['version']==1 and policy['goalsPerBatch']==4 and policy['mode'] in ('balanced-native-visits-v1','manual')
            and (type(policy['targetGameplaySeconds']) is int and policy['targetGameplaySeconds']>0
                 if policy['mode']!='manual' else policy['targetGameplaySeconds'] is None)
            and policy['maxBatches']==admission['batchCount'] and policy['maxLegs']==admission['maxLegs']
            and policy['initialPlanSha256']==admission['planSha256'] and digest==admission['queuePolicySha256']
            and hashlib.sha256(owner).hexdigest()==policy['requiredOwnerManifestSha256']==admission['requiredOwnerManifestSha256']
            and record.get('status') in ('completed','stopVerified'),'Open-queue policy or previous supervisor owner receipt differs')
    supervisor=json.loads((folder/'launcher.json').read_bytes())
    require(supervisor['runId']==run_id and supervisor['rootPid']==record['identity']['root']['processId']
            and supervisor['childPid']==record['identity']['child']['processId']
            and supervisor['windowsSessionId']==record['identity']['child']['windowsSessionId'],
            'Unexpected RDP owner for open queue')
    broker=json.loads((folder/'broker.json').read_bytes())
    argv=json.loads((folder/'jobs'/(broker['jobId']+'.job.json')).read_bytes())['argv']
    expected=':'.join(str(record['identity'][role][k]) for role in ('root','child') for k in ('processId','instanceNonce'))
    binding=[v.split('=',1)[1] if '=' in v else argv[i+1] for i,v in enumerate(argv) if v.split('=')[0]=='--patrol-series-binding']
    require(len(binding)==1 and binding[0].rsplit(':',1)[0]==expected and
            all(p['residentRunId']==run_id for p in parts),'Supervisor pin or native lease differs from owner promise')
    return policy,digest


def verify_decision(doc,slot,chain,groups,policy,policy_sha,clock):
    """Prove every scheduling choice used positive applied receipts on this lease and only prior completed requests."""
    env,pub=slot['envelope'],slot['publication']
    witness=env['witness']
    specs=[r for b in chain for r in b['plan']['requests']]
    by_id={r['id']:n for n,r in enumerate(specs)}
    n=by_id.get(witness.get('requestId'))
    require(set(witness)=={'batchOrdinal','requestId','nativeRequestId','frameId'} and n is not None and n<len(groups)
            and witness['batchOrdinal']==chain[-1]['batchOrdinal'] and witness['requestId'] in {r['id'] for r in chain[-1]['plan']['requests']},
            'Planner witness does not belong to the active predecessor batch')
    receipt,first=groups[n][0],groups[0][0]
    bracket=pub['publicationQpc']
    common=('version','runId','sessionId','ownerEpoch','batchOrdinal','previousSha256','witness')
    expected_fields={*common,'type','batchSha256','policySha256','observedAtMonotonicNs','gameplayClock','activeOrdinal',
                     'completedRequestIds','requestedCounts','verifiedCounts','approachCounts','usedLegs','predecessorEnd','selectedStations','reason'}
    require(set(doc)==expected_fields and all(doc[k]==env[k] for k in common) and doc['type']=='destinationQueueDecision'
            and doc['batchSha256']==slot['batchSha256'] and doc['policySha256']==policy_sha
            and doc['observedAtMonotonicNs']==pub['observedAtMonotonicNs'] and doc['activeOrdinal']==n+1
            and doc['completedRequestIds']==[r['id'] for r in specs[:n]] and
            (witness['nativeRequestId'],witness['frameId'])==(receipt['nativeRequestId'],receipt['frameId'])
            and doc['gameplayClock']==dict(frequencyHz=clock['frequency'],firstAppliedTicks=first['firstDispatchTicks'],
                    witnessAppliedTicks=receipt['firstDispatchTicks'],firstNativeRequestId=first['nativeRequestId'],firstFrameId=first['frameId'])
            and env['sessionId']==clock['sessionId'] and env['ownerEpoch']==clock['ownerEpoch']
            and set(bracket)=={'clock','frequencyHz','beforeTicks','afterTicks'} and bracket['clock']=='windows-query-performance-counter'
            and bracket['frequencyHz']==clock['frequency'] and all(type(bracket[k]) is int for k in ('beforeTicks','afterTicks'))
            and receipt['terminalEndTicks']<=bracket['beforeTicks']<=bracket['afterTicks'],
            'Policy state, addressed native receipt or gameplay clock differs')
    wanted=Counter(dict.fromkeys(STATIONS,0)); wanted.update(r['destination'] for r in specs)
    verified=Counter(dict.fromkeys(STATIONS,0)); verified.update(r['destination'] for r in specs[:n])
    dests=[r['destination'] for r in specs]
    legs,approaches=route_stats(chain[0]['plan']['start'],dests)
    left=policy['maxLegs']-legs
    require(doc['requestedCounts']==dict(wanted) and doc['verifiedCounts']==dict(verified)
            and doc['approachCounts']==dict(approaches) and doc['usedLegs']==legs and doc['predecessorEnd']==dests[-1],
            'Planner counts or physical graph budget differ from actual admitted goals')
    elapsed=(receipt['firstDispatchTicks']-first['firstDispatchTicks'])/clock['frequency']
    stopping=env.get('kind')=='finish'
    selected=[] if stopping else [r['destination'] for r in env['plan']['requests']]
    reason='operatorFinish' if stopping else 'manualDestinations'
    if policy['mode']=='balanced-native-visits-v1':
        expected=[]
        if elapsed>=policy['targetGameplaySeconds']:
            reason='gameplayTargetReached'
        elif len(chain)>=policy['maxBatches']:
            reason='batchLimitReached'
        else:
            expected=best_destinations(dests[-1],left,wanted,verified,approaches,witness['frameId'])
            reason='balancedVisits' if expected else 'legLimitReached'
        require(stopping==(not expected) and selected==expected,'Producer selected wrong route or closed for the wrong reason')
        if selected:
            require([r['name'] for r in env['plan']['requests']]==[f"open-{slot['batchOrdinal']:02d}-{i:02d}-{s}"
                    for i,s in enumerate(selected,1)],'Automatic goal names do not match selected targets')
    require(doc['reason']==reason and doc['selectedStations']==selected,'External open-queue decision reason or destinations differ')
    return dict(decisionOrdinal=slot['batchOrdinal'],reason=reason,elapsedGameplaySeconds=elapsed,witness=witness,
                selectedStations=selected,publicationQpc=bracket,policySha256=policy_sha)


def verify_open_queue(folder,admission,batches,parts,events,groups,frames,clock,terminal_release_ms,stopped):
    """Require an explicit, timely finish at the final verified endpoint, with no subsequent input."""
    run_id=parts[0]['residentRunId']
    policy,digest=verify_policy(folder,admission,parts,run_id)
    slots=list(batches[1:])
    if not stopped:
        slots.append(finish_packet(folder,batches[-1],run_id))
    decisions=[]
    for i,slot in enumerate(slots,1):
        decision_bytes=bounded_bytes(folder/'batches'/f"{slot['batchOrdinal']:05d}.decision.json",65536)
        doc=json.loads(decision_bytes)
        decisions.append(verify_decision(doc,slot,batches[:i],groups,policy,digest,clock))
        native=[e for e in events if e['type'] in ('warmQueueFinished','warmBatchAccepted')
                and (e.get('decisionOrdinal') or e.get('nextBatchOrdinal'))==slot['batchOrdinal']]
        require(len(native)==1 and native[0].get('policyDecisionSha256')==hashlib.sha256(decision_bytes).hexdigest(),
                'Resident accepted different policy decision bytes')
    markers=[e for e in events if e['type'].startswith('warmQueue')]
    if stopped:
        require(not markers,'Operator stop recorded a terminal completion')
        return dict(outcome='operator-stopped-prefix',decisions=decisions)
    finish=slots[-1]
    require(len(markers)==1 and markers[0]['type']=='warmQueueFinished' and events[-1]==markers[0]
            and len(events)>=2 and events[-2]['type']=='warmPhotoRequestCompleted','Finish was not the last released request boundary')
    mark=markers[0];done=events[-2]
    verify_terminal_boundary(mark,done,finish,batches[-1]['plan']['requests'][-1]['destination'],groups,
                             frames,clock,terminal_release_ms)
    return dict(outcome=decisions[-1]['reason'],decisions=decisions,finishedAtFrame=mark['admissionFrameId'],
                consumedQpc=mark['consumedQpc'],decisionSha256=finish['batchSha256'],finalInputReleaseMs=terminal_release_ms)


def verify_terminal_boundary(mark,done,finish,station,groups,frames,clock,terminal_release_ms):
    """Bind the finish to one exact qualified endpoint, the originating terminal bytes and the physical release."""
    qpc=mark['consumedQpc'];admitted=mark['admissionFrameId'];fid=done['frameId'];bracket=finish['publication']['publicationQpc']
    keys=('runId','sessionId','ownerEpoch','ordinal','warmRequestId','planSha256','goalEmbeddingSha256','batchOrdinal',
          'batchSha256','batchPlanSha256','name','targets','destination','frameId','sourceEpoch','completedLegs','release','lastAcceptedRequestId')
    require(all(mark[k]==done[k] for k in keys) and mark['pendingActionIds']==[] and
            all(mark.get(k)==done.get(k) for k in ('initialEndpointFrameId','retryOrdinal','firstConfirmedFrameId'))
            and mark['decisionOrdinal']==finish['batchOrdinal'] and mark['decisionSha256']==finish['batchSha256']
            and mark['intentSha256']==finish['intentSha256'] and mark['publicationSha256']==finish['publicationSha256']
            and mark['decisionBytes']==finish['bytes'] and mark['publicationWitness']==finish['envelope']['witness']
            and type(admitted) is int and fid<=admitted and admitted in frames and set(qpc)=={'clock','frequencyHz','ticks'}
            and qpc['clock']==bracket['clock'] and qpc['frequencyHz']==clock['frequency'] and type(qpc['ticks']) is int,
            'Native terminal finish does not match exact consumed bytes and final released endpoint')
    def ticks(ms):
        return clock['originTicks']+round(ms*clock['frequency']/1000)
    require(bracket['afterTicks']<=qpc['ticks']<=ticks(terminal_release_ms)
            and groups[-1][-1]['terminalEndTicks']<=ticks(done['release']['serverNowMs'])<=ticks(observation_timestamp(frames[fid]))<=qpc['ticks']
            and all(r['terminalEndTicks']<=qpc['ticks'] for g in groups for r in g),'Late or in-flight input at terminal finish')
    verify_settled_wait(done,fid,admitted,station,qpc,frames,clock)
