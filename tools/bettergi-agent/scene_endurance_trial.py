"""A separate single-use 600-second scene-observer experiment; never a default observer promotion."""
import json
from pathlib import Path
import time

from destination_batch_sender import admitted_plans,qualification_goals
from destination_queue_policy import BALANCED
from gpu_landmark_observer import FORMAT as SCENE_FORMAT
from scene_photo_trial import CHECKPOINT,bind_claim,bounded_bytes,digest,prerequisites,require,validate_context
from warm_photo_requests import validate_plan

FORMAT='bettergi-scene-endurance-trial-v1'
SCOPE='bounded-endurance-experiment'
REVIEW_SHA256='3b8f2e199d2941f7f68eb70d9f4e0b3c61cf456b5b2518706b3a60c21641f8b9'


def reviewed_owner(comparison):
    """Bind both the prior qualification and the independently replayed four-photo trial."""
    comparison=Path(comparison).resolve()
    identity=prerequisites(comparison)
    raw=bounded_bytes(comparison/'promotion-review.json',128*1024)
    require(digest(raw)==REVIEW_SHA256,'Scene endurance review changed or is missing')
    review=json.loads(raw)
    trial=Path(review['trial']).resolve()
    require(trial.is_relative_to(Path(__file__).resolve().parents[2]/'artifacts'),'Unbound predecessor trial')
    for name,sha in review['evidenceSha256'].items():
        require(digest(bounded_bytes(trial/name,2*1024*1024))==sha,'Reviewed photo-trial evidence changed')
    require(review['currentState']['identity']==identity and review['independentReplayExact'] is True,
        'Endurance predecessor has a different owner or lacks independent replay')
    return identity,trial/'warm-launcher.json'


def queue_artifacts(folder,comparison):
    """Reconstruct the exact 600/900-second limits and original owner instead of trusting permit flags."""
    identity,predecessor=reviewed_owner(comparison)
    plan_raw=bounded_bytes(folder/'photo-requests.json',16384)
    policy_raw=bounded_bytes(folder/'queue-policy.json',16384)
    owner_raw=bounded_bytes(folder/'required-owner.json',65536)
    plan,policy,owner=map(json.loads,(plan_raw,policy_raw,owner_raw))
    validate_plan(plan)
    require(set(plan)=={'version','mode','start','requests'} and plan['version']==2 and plan['mode']=='destinations'
        and plan['start']=='stair-front' and [r['destination'] for r in plan['requests']]==
        [station for _,station in qualification_goals('stair-front',1,0)],'Changed initial endurance itinerary')
    require(owner['status']=='completed' and owner['identity']==identity and owner_raw==bounded_bytes(predecessor,65536),
        'Endurance trial must descend from the reviewed four-photo lease')
    expected=dict(version=1,mode=BALANCED,targetGameplaySeconds=600,goalsPerBatch=4,maxBatches=40,maxLegs=256,
        initialPlanSha256=digest(plan_raw),requiredOwnerManifestSha256=digest(owner_raw),queueLimitsProfile='endurance-v1')
    require(policy==expected,'Changed scene endurance policy or bounds')
    return identity,plan,dict(planSha256=digest(plan_raw),queuePolicySha256=digest(policy_raw),ownerManifestSha256=digest(owner_raw))


def issue(path,comparison,identity,deadline_ns,goal_path):
    """Issue after the ordinary supervisor freezes its policy, before its sole RDP worker starts."""
    path,comparison=Path(path).resolve(),Path(comparison).resolve()
    original,plan,hashes=queue_artifacts(path.parent,comparison)
    require(original==identity,'Scene endurance owner changed before admission')
    now=time.monotonic_ns()
    require(now<deadline_ns<=now+900_000_000_000,'Scene endurance deadline exceeds its reviewed cap')
    root,child=identity['root'],identity['child']
    permit=dict(format=FORMAT,checkpointId=CHECKPOINT,comparison=str(comparison),identity=identity,
        evidenceDirectory=str(path.parent),issuedAtMonotonicNs=now,**hashes,
        goalEmbedding=dict(path=str(Path(goal_path).resolve()),sha256=digest(bounded_bytes(goal_path,128*1024))),
        binding=[root['processId'],root['instanceNonce'],child['processId'],child['instanceNonce'],deadline_ns])
    with path.open('x',encoding='utf-8') as stream:
        json.dump(permit,stream,indent=2,allow_nan=False)
    return permit


def validate_queue_context(args,permit,folder):
    """Retain the common policy/input bounds and require the explicit endurance queue mode."""
    validate_context(args,permit,folder,queue=True)
    identity,plan,hashes=queue_artifacts(folder,permit['comparison'])
    require(identity==permit['identity'] and all(permit[key]==value for key,value in hashes.items()),
        'Scene endurance artifacts changed after issue')


def admit(path,head,execution_context=None):
    """Authenticate one bounded queue and reuse the same exclusive addressed-run claim as the short trial."""
    path=Path(path).resolve()
    folder=path.parent
    permit=json.loads(bounded_bytes(path,65536))
    identity,plan,hashes=queue_artifacts(folder,permit['comparison'])
    root,child=identity['root'],identity['child']
    require(permit['format']==FORMAT and head.data['format']==SCENE_FORMAT
        and head.checkpoint_id==permit['checkpointId']==CHECKPOINT and permit['identity']==identity,
        'Wrong scene endurance observer or owner')
    require(Path(permit['evidenceDirectory']).resolve()==folder and permit['binding'][:4]==
        [root['processId'],root['instanceNonce'],child['processId'],child['instanceNonce']]
        and type(permit['issuedAtMonotonicNs']) is int and type(permit['binding'][4]) is int
        and 0<permit['binding'][4]-permit['issuedAtMonotonicNs']<=900_000_000_000
        and all(permit[key]==value for key,value in hashes.items()),'Copied or widened scene endurance permission')
    # A live permit covers the fixed publisher policy. Offline replay also binds every actual committed request ID.
    plans=[plan] if execution_context is not None else admitted_plans(folder)
    ids=[r['id'] for p in plans for r in p['requests']]
    return bind_claim(path,head,permit,execution_context,validate_queue_context,ids,SCOPE)


def require_queue_admission(head):
    """The short-trial claim and a bare shadow checkpoint never authorize an open queue."""
    from scene_photo_trial import require_admission
    admission=require_admission(head)
    require(admission.get('scope')==SCOPE,'Scene observer has no reviewed endurance trial admission')
