"""Verify the photographed prefix of a failed destination queue without converting it to a successful finish."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

from audit_hybrid_run import audit, batch_edges, require
from audit_open_queue import finish_packet, verify_decision, verify_policy
from audit_photo_handoff import (attribute_actions,authority_parts,bridge_clock,check_plan,directed_broker,directed_controls,
                                lifecycle,photo_proofs,read,terminal_release)
from audit_warm_batches import read_batches,verify_batch_events
from landmark_recognizer import G4_SHA256, LandmarkRecognizer
from observation_timing import observation_timestamp
from patrol_photo_survey import require_qualified_observer
from destination_queue_limits import queue_limits


def starvation_outcome(stage,deadline,clock,groups_by_request,previous):
    """Separate no publisher from a late, deadline-straddling or timely but unconsumed envelope."""
    if not stage:
        return 'missing-successor'
    require(len(stage)==1,'More than one unconsumed slot')
    slot=stage[0];env=slot['envelope'];wit=env['witness']
    group=groups_by_request.get(wit.get('requestId')) or []
    q=slot['publication']['publicationQpc']
    require(group and wit['requestId'] in {r['id'] for r in previous['plan']['requests']} and
            wit==dict(requestId=wit['requestId'],batchOrdinal=previous['batchOrdinal'],frameId=group[0]['frameId'],
                      nativeRequestId=group[0]['nativeRequestId'])
            and (env['sessionId'],env['ownerEpoch'])==(clock['sessionId'],clock['ownerEpoch'])
            and q['clock']=='windows-query-performance-counter' and q['frequencyHz']==clock['frequency'] and
            all(type(q[k]) is int for k in ('beforeTicks','afterTicks')) and
            group[0]['terminalEndTicks']<=q['beforeTicks']<=q['afterTicks'],'Unbound publication for the unconsumed slot')
    if q['beforeTicks']>deadline:
        return 'late-successor'
    return 'published-unconsumed' if q['afterTicks']<=deadline else 'publication-crossed-deadline'


def audit_failure(folder,checkpoint,qualification,repo):
    """Report genuine photo refusal or input-free starvation from original receipts, sources and sender publications."""
    folder=Path(folder).resolve()
    runpath=folder/'patrol.json'; rec=folder/'patrol-recording'
    run,supervisor,admission=(read(folder/p) for p in ('patrol.json','launcher.json','warm-launcher.json'))
    error=run.get('error') or ''
    photo=error=='Destination photo remained unverified after three stationary retries'
    timeout=error in ('No qualified destination batch within the 1000 ms released boundary',
                      'No qualified open-queue decision within the 1000 ms released boundary',
                      'Open-queue decision missed the native 1000 ms released boundary','hybrid_navigation:destination_batch_deadline')
    require((photo or timeout) and run['endReason']=='error' and run['status']=='failed' and run['failedLeases']==1 and
            supervisor['runId']==run['runId'] and supervisor['verified'] is False and supervisor['stopRequested'] is False
            and run['windowsSessionId']==supervisor['windowsSessionId'] and not (folder/'STOP').exists(),
            'Only explicit native photo refusal or released queue starvation can receive a verified failed prefix')
    raw=(folder/'photo-requests.json').read_bytes()
    plans=[json.loads(raw)]
    finish=False
    for path in sorted((folder/'batches').glob('*.intent.json')):
        intent=read(path)
        require(not finish,'A publication follows a staged terminal decision')
        if intent.get('kind')=='finish':
            finish=True
        else:
            plans.append(intent['plan'])
    for plan in plans:
        check_plan(plan)
    require(admission['planSha256']==hashlib.sha256(raw).hexdigest(),'Original initial plan changed')
    published=read_batches(folder,plans,raw,admission,run,False,failed=True,has_finish=finish)
    opened=admission.get('openQueue') is True
    parts,events,decisions,recovery,receipts,frames=authority_parts(run,rec,repo,True,True)
    clock=bridge_clock(parts)
    require(not any(e['type']=='warmQueueFinished' for e in events),'Failed run recorded a successful finish')
    accepted=1+sum(e['type']=='warmBatchAccepted' for e in events)
    require(accepted<=len(plans)<=accepted+1 and not(finish and len(plans)!=accepted),'Unexpected staged or orphan successor')
    admitted=published[:accepted];current=plans[:accepted]
    edges=batch_edges(current,max_batches=queue_limits(admission.get('queueLimitsProfile')).batches)
    broker,shadow=directed_broker(folder,run,supervisor,edges,checkpoint,qualification,admission['batchCount'],
                                  admission['maxLegs'],opened,failed=True)
    from weighted_landmark_recognizer import load_landmark_shadow
    head=load_landmark_shadow(checkpoint)
    require_qualified_observer(qualification,head)
    from patrol_photo_survey import require_open_queue_photo_authority
    require_open_queue_photo_authority(head)
    physical=audit(runpath,rec,repository=repo,landmark_checkpoint=checkpoint,destination_plan=plans[0],destination_batches=current,
                   shadow_checkpoint=shadow,failure_prefix=True)
    require(not physical['passed'],'Failure prefix cannot receive a passed physical audit')
    specs=[r for p in current for r in p['requests']]
    count=sum(e['type']=='warmPhotoRequestStarted' for e in events)
    require(0<count<=len(specs) and (photo or count==len(specs)),'Starved before the last request or unexpected active goal')
    specs=specs[:count]
    selected=[e for e in events if e['type'] not in ('warmBatchAccepted','warmQueueStarved')]
    starts,completed=lifecycle(selected,parts,specs,run['runId'],admission['planSha256'],clock,photo,edges,
                               plans[0].get('confirmFirstArrival',False),failed_photo=photo)
    groups,handoffs=attribute_actions(decisions,recovery,receipts,frames,specs,starts,completed,clock)
    proofs=photo_proofs(folder/'station-photos',physical,events,specs,starts,head,completed,plans[0].get('confirmFirstArrival',False))
    require({p.name for p in (folder/'station-photos').iterdir() if p.is_dir()}=={s['id'] for s in specs}
            and len(completed)==len(specs)-int(photo),'Unexpected open photo request or missing manifest')
    admissions=verify_batch_events(events,admitted,groups,frames,clock,specs,photo,[*decisions,*recovery],failed=True)
    end=terminal_release(parts,groups)
    boundary=next(e for e in reversed(events) if e['type']=='hybridEndpointVerified')
    fid=boundary['samples'][-1]['frameId']
    require(all(d['frameId']<fid for d in [*decisions,*recovery]) and all(r['endedAtMs']<=boundary['releaseAtMs']
            for r in receipts.values()),'Proposal or native action followed the last qualified released physical boundary')
    stage=published[accepted:] if not finish else [finish_packet(folder,admitted[-1],run['runId'])]
    decision_frame=fid if photo else completed[-1]['frameId']
    deadline=clock['originTicks']+round((observation_timestamp(frames[decision_frame])+1000)*clock['frequency']/1000)
    reason='failed-natural-photo' if photo else starvation_outcome(stage,deadline,clock,
            {r['id']:g for r,g in zip(specs,groups)},admitted[-1])
    if photo:
        retries=physical['stationaryPhotoRetries']
        attempts=proofs[-1]['retryEvidence']
        require(len(retries)>=1 and len(attempts)==4 and all(r['outcome']=='classificationMiss' for r in attempts)
                and retries[-1]['originalFrameId']==fid and attempts[0]['frameId']==fid
                and not proofs[-1]['complete'],'Three stationary misses and the original wrong image were not proven')
    else:
        require(decision_frame>=fid and end-observation_timestamp(frames[decision_frame])>=1000,
                'Missing qualified terminal endpoint or released timeout interval')
    policy_decisions=[]
    if opened:
        policy,digest=verify_policy(folder,admission,parts,run['runId'])
        for i,slot in enumerate([*admitted[1:],*stage],1):
            doc=read(folder/'batches'/f"{slot['batchOrdinal']:05d}.decision.json")
            policy_decisions.append(verify_decision(doc,slot,admitted[:i],groups,policy,digest,clock))
        marks=[e for e in events if e['type']=='warmQueueStarved']
        if timeout:
            require(len(marks)==1 and events[-1]==marks[0] and events[-2]==completed[-1],
                    'Missing original starvation marker after the final released completion')
            mark=marks[0];q=mark['failedQpc']
            require(mark['decisionOrdinal']==accepted+1 and all(mark[k]==completed[-1][k] for k in
                    ('frameId','sourceEpoch','release','lastAcceptedRequestId','ordinal','batchSha256','warmRequestId','pendingActionIds'))
                    and q['clock']=='windows-query-performance-counter' and q['frequencyHz']==clock['frequency']
                    and deadline<=q['ticks']
                    <=clock['originTicks']+round(end*clock['frequency']/1000),'Invalid native starvation deadline or owner proof')
        else:
            require(not marks,'Photo refusal was reclassified as queue starvation')
    budgets=directed_controls(run,supervisor,parts,events,decisions,recovery,receipts,frames,edges,clock,failed=True)
    temps=[json.loads(l) for l in (folder/'gpu.jsonl').read_text().splitlines()]
    times=[datetime.fromisoformat(t['atUtc']) for t in temps]
    require(len(temps)>=2 and all(not t.get('error') and 0<t['temperatureC']<78 for t in temps)
            and times[0]<=datetime.fromisoformat(broker['startedAtUtc']) and
            abs((datetime.fromisoformat(broker['endedAtUtc'])-times[-1]).total_seconds())<6
            and all(0<(b-a).total_seconds()<=6 for a,b in zip(times,times[1:])), 'Incomplete failure thermal evidence')
    return dict(passed=False,status=reason,verifiedPrefix=True,originalError=error,runId=run['runId'],clock=clock,
                verifiedPhysicalLegs=physical['verifiedLegs'],completedRequestIds=[r['warmRequestId'] for r in completed],
                uncompletedRequestId=specs[-1]['id'] if photo else None,provenPhotos=proofs,admittedBatches=len(admitted),
                stagedUnadmittedSlots=[x['batchOrdinal'] for x in stage],admissions=admissions,policyDecisions=policy_decisions,
                handoffs=handoffs,appliedActions=sum(map(len,groups)),proposalsAfterReleasedBoundary=0,terminalReleaseAtMs=end,
                peakGpuTemperatureC=max(t['temperatureC'] for t in temps),budgets=budgets)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('folder','checkpoint','qualification','out'):
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    output=audit_failure(a.folder,a.checkpoint,a.qualification,Path(__file__).resolve().parents[2])
    with a.out.open('x',encoding='utf-8') as f:
        json.dump(output,f,indent=2,allow_nan=False)
    print(output['status'],a.out)
