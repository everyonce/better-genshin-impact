"""Classify verified stationary re-observations from a sealed directed lease using original PNGs and native receipts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from audit_destination_retries import verify_retry_poses
from audit_hybrid_run import require
from audit_photo_handoff import (attribute_actions, authority_parts, batch_edges, bridge_clock, check_plan,
                                destination_edges, endpoint_release, lifecycle, read)
from destination_batch_sender import admitted_plans
from freeze_landmark_candidate import source_views
from landmark_recognizer import LandmarkRecognizer
from patrol_photo_survey import require_qualified_observer


ROOT = Path(__file__).resolve().parents[2]


def outcome(images,qualified,completed,switch,planned):
    """Only an unplanned original miss, real agreement, and verified next dispatch can credit a recovery."""
    require(2<=len(images)<=4,'Retry chains require one original and one to three new images')
    observed = [i['outcome'] for i in images]
    for image in images:
        agrees = image['predicted']==image['native']
        require(image['outcome'] in ('classificationMiss','confirmationPending','collected') and
                agrees is (image['outcome']!='classificationMiss'),'Image outcome disagrees with original RGB replay')
    require('collected' not in observed[:-1] and ('confirmationPending' not in observed or planned),
            'Unexpected completion or undeclared confirmation')
    if observed[-1]!='collected':
        require(not completed and switch is None,'Unresolved image has a completion or handoff')
        return 'exhaustedMisses' if observed==['classificationMiss']*4 else 'unresolvedStationaryViews'
    require(completed,'Collected retry has no native completion')
    if switch is not None:
        require(switch['boundaryFrameId']==images[-1]['frameId'] and 0<switch['dispatchGapMs']<1000,
                'Successor handoff does not follow the accepted original within one second')
    if planned:
        require('confirmationPending' in observed,'Planned confirmation has no matched preceding image')
        return 'plannedConfirmation' if observed[0]=='confirmationPending' else 'plannedConfirmationAfterMiss'
    require(observed[0]=='classificationMiss','No genuine original miss')
    return 'naturalRecoveryWithHandoff' if qualified and switch is not None else 'correctedImageWithoutQualifiedHandoff'


def summarize(run_path,checkpoint,qualification,repository=ROOT):
    """Rebuild the release and picture chains without decoding video or awarding a failed lease gameplay credit."""
    run_path = Path(run_path).resolve()
    folder = run_path.parent
    raw = run_path.read_bytes()
    run = json.loads(raw)
    plans = admitted_plans(folder)
    plan = plans[0]
    require(plan['version']==2 and run['status'] in ('completed','failed'),'Sealed directed run required')
    head = LandmarkRecognizer.load(checkpoint)
    require_qualified_observer(qualification,head)
    specs = [s for p in plans for s in check_plan(p)]
    supervisor = read(folder/'launcher.json')
    admission = read(folder/'warm-launcher.json')
    plan_sha = hashlib.sha256((folder/'photo-requests.json').read_bytes()).hexdigest()
    require(admission['planSha256']==plan_sha and supervisor['runId']==run['runId']
            and supervisor['windowsSessionId']==run['windowsSessionId'] and
            all(p['processId']==supervisor['childPid'] for p in run['segments']),'Changed declared lease or addressed child')
    planned = plan.get('confirmFirstArrival') is True
    queued = bool(admission.get('batchCount'))
    parts,events,decisions,recov,receipts,frames = authority_parts(run,folder/'patrol-recording',repository,True,queued)
    clock = bridge_clock(parts)
    require(all(p['residentRunId']==run['runId'] for p in parts),'Foreign segment run')
    retry_chains = verify_retry_poses(events,frames,parts,receipts,planned)
    # The existing source verifier authenticates PNG bytes, the live RGB digest and its frozen class, all native
    # poses, the release, and the exact frame-index link. It does not decode H.264 or consult its classifier result.
    qualified = run['status']=='completed'
    _,_,verified = source_views(run_path,head,diagnostic=not qualified)
    photos = {p['frameId']:p for p in verified['photos']}
    done = [e for e in events if e['type']=='warmPhotoRequestCompleted']
    switches = {}
    if qualified:
        sealed = read(folder/'handoff-audit.json')
        require(sealed['passed'] is True and sealed['status']=='qualified' and sealed['runId']==run['runId']
                and run.get('endReason')=='hybridLegLimit' and run['evidenceComplete'] is True,'Successful handoff seal required')
        edges = batch_edges(plans) if queued else destination_edges(plan)
        lifecycle_events = [e for e in events if e['type']!='warmBatchAccepted']
        boundaries,completions = lifecycle(lifecycle_events,parts,specs,run['runId'],plan_sha,clock,False,edges,planned)
        _,replayed = attribute_actions(decisions,recov,receipts,frames,specs,boundaries,completions,clock)
        require(replayed==sealed['handoffs'],'Handoff seal and original native receipts differ')
        switches = {s['oldRequestId']:s for s in replayed}
    rows = []
    for original,retries in retry_chains.items():
        endpoint, = [e for e in events if e['type']=='hybridEndpointVerified' and e['samples'][-1]['frameId']==original]
        owner = endpoint['warmRequestId']
        release = endpoint_release(endpoint,parts,owner)
        images = []
        for event in (endpoint,*retries):
            fid = event['samples'][-1]['frameId']
            photo = photos[fid]
            require(photo['release']==release and photo['warmRequestId']==owner and photo['station']==endpoint['station'],
                    'Retry image crosses release, station or request')
            images.append(dict(frameId=fid,sourceTimestamp100ns=photo['sourceTimestamp100ns'],outcome=event['photoSurveyVisit']['outcome'],
                               native=photo['station'],predicted=photo['prediction']['station'],originalRgbSha256=photo['rgbSha256'],
                               originalPngSha256=photo['pngSha256']))
        completed = [e for e in done if e['warmRequestId']==owner]
        require(len(completed)<=1 and all(e['frameId']==images[-1]['frameId'] and e['release']==release for e in completed),
                'Unbound retry completion')
        switch = switches.get(owner)
        result = outcome(images,qualified,bool(completed),switch,planned and owner==specs[0]['id'])
        rows.append(dict(outcome=result,requestId=owner,station=endpoint['station'],originalFrameId=original,
                         releaseEpoch=endpoint['releaseEpoch'],sourceEpoch=endpoint['sourceEpoch'],retryCount=len(retries),
                         stationaryElapsedMs=retries[-1]['atMs']-endpoint['samples'][-1]['atMs'],
                         verifiedHandoff=switch,views=images))
    counts = dict(Counter(r['outcome'] for r in rows))
    return dict(format='bettergi-stationary-photo-outcomes-v1',runId=run['runId'],runSha256=hashlib.sha256(raw).hexdigest(),
                qualifiedRun=qualified,runStatus=run['status'],checkpointSha256=head.checkpoint_id,
                originalImageDomain='lossless source RGB',controllerLease=[clock['sessionId'],clock['ownerEpoch']],
                creditedNaturalRecoveries=counts.get('naturalRecoveryWithHandoff',0),counts=counts,chains=rows)


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('run','checkpoint','qualification'):
        parser.add_argument('--'+flag,type=Path,required=True)
    parser.add_argument('--output',type=Path,help='Create an exclusive report outside the original source folder')
    args = parser.parse_args()
    result = summarize(args.run,args.checkpoint,args.qualification)
    if args.output:
        require(not args.output.resolve().is_relative_to(args.run.resolve().parent),'Keep original evidence untouched')
        with args.output.open('x',encoding='utf-8') as stream:
            json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps(dict(runStatus=result['runStatus'],creditedNaturalRecoveries=result['creditedNaturalRecoveries'],counts=result['counts'])))
