"""Single-use, four-goal photo trial for the specifically qualified G10 observer; never an open-queue promotion."""
import hashlib
import json
import os
from pathlib import Path
import re
import time

from gpu_landmark_observer import FORMAT as SCENE_FORMAT
from hybrid_routes import STREET_PATROL_ROUTE,itinerary_legs
from warm_photo_requests import validate_plan

# These exact reviewed artifacts passed the retained-data and two prospective lease gates.
CHECKPOINT='0fc8f53a6e859a57b4b419a89a1575079b6af159ccfcdc7e4afd38dc9a08d277'
EVIDENCE={
    'g10-shadow.json':CHECKPOINT,
    'prospective-plan.json':'9df3a4f2cd1359d5434a3a6468fe200327e4c7877059cd2ac0c16957e209d012',
    'prospective-result.json':'d234461d400ff40faf4d70411dab4ca3cb3e2ee6d6ff9ab4db908e2c677f1cf9',
    'graph-parity.json':'2cfd903f326967b4ec45bdea6fdfaf3debad8981d9928a49262dcca9d89c6ada',
    'frozen-result/results.json':'36bfa4e73c564b271a2d33b9f3d761b09007d7b31d13c03ce843b885a3beae90',
}
DESTINATIONS=['west-lamp','stair-front','west-lamp','stair-front']
FORMAT='bettergi-scene-photo-trial-v1'


def require(ok,message):
    """Refuse trial admission before allocating the policy or acquiring input."""
    if not ok:
        raise ValueError(message)


def digest(raw):
    """Bind exact plan, permit and prerequisite bytes."""
    return hashlib.sha256(raw).hexdigest()


def bounded_bytes(path,maximum):
    """Reject oversized control evidence before reading it into memory."""
    with Path(path).open('rb') as stream:
        raw=stream.read(maximum+1)
    require(len(raw)<=maximum,'Oversized scene trial artifact')
    return raw


def prerequisites(comparison):
    """Accept only the independently audited frozen G10 result, not an arbitrary passed flag."""
    comparison=Path(comparison).resolve()
    require(comparison.is_relative_to(Path(__file__).resolve().parents[2]/'artifacts'),'Unbound trial prerequisites')
    for name,sha in EVIDENCE.items():
        require(digest(bounded_bytes(comparison/name,2*1024*1024))==sha,'Qualified scene evidence changed: '+name)
    return json.loads((comparison/'prospective-plan.json').read_bytes())['identity']


def check_plan(plan):
    """The exception is confined to two lamp/stair returns on the surveyed graph."""
    validate_plan(plan)
    require(set(plan)=={'version','mode','start','requests'} and plan['version']==2 and plan['mode']=='destinations'
        and plan['start']=='stair-front' and [r['destination'] for r in plan['requests']]==DESTINATIONS
        and len(itinerary_legs(plan['start'],DESTINATIONS))==8,'Scene trial requires exactly the four declared goals')


def validate_context(args,permit,folder,*,queue=False):
    """Pin the runtime to one owner, output folder, plan, freshness bound and short closed itinerary."""
    require(Path(args.output).resolve()==folder/'patrol.json' and Path(args.photo_directory).resolve()==folder/'station-photos'
        and Path(args.warm_photo_plan).resolve()==folder/'photo-requests.json','Scene trial output or plan changed')
    require(args.model=='open-p2p' and args.resident and args.enable_input and args.hybrid_navigation
        and args.hybrid_route==STREET_PATROL_ROUTE and args.hybrid_legs==(256 if queue else 8) and args.seconds==(900 if queue else 90)
        and args.fps==20 and args.decision_hz==10 and args.max_observation_age_ms==150 and args.action_hold_ms==100
        and args.rdp_session_id==permit['identity']['child']['windowsSessionId']
        and list(args.patrol_series_binding)==permit['binding'],'Scene trial owner or runtime limits changed')
    require(not args.control_file or Path(args.control_file).resolve()==Path(str(folder/'patrol.json')+'.control.json'),
        'Scene trial control file changed')
    require(args.goal_intent=='ground-navigation' and args.history==41 and args.cuda_graph
        and args.p2p_fast_start and args.p2p_prewarm and args.observation_profile=='p2p-native-hamming-192-v1'
        and Path(args.goal_embedding).resolve()==Path(permit['goalEmbedding']['path'])
        and digest(bounded_bytes(args.goal_embedding,128*1024))==permit['goalEmbedding']['sha256'],
        'Scene trial policy or instruction changed')
    require(not any(getattr(args,name,False) for name in ('photo_station','inspect_junction_map','recover_junction_map')),
        'Scene trial cannot authorize another goal mode')
    if queue:
        require(args.warm_open_queue is True and args.warm_endurance is True and args.warm_batch_count==40,
            'Scene endurance trial requires its exact queue profile')
    else:
        require(not any(getattr(args,name,False) for name in ('warm_open_queue','warm_endurance','warm_batch_count')),
            'Scene trial cannot authorize another goal mode')


def issue(path,comparison,plan_path,identity,deadline_ns,goal_path):
    """Create an explicit permit after the short plan is written and before any broker job starts."""
    path,plan_path=Path(path).resolve(),Path(plan_path).resolve()
    require(path.parent==plan_path.parent and plan_path.name=='photo-requests.json','Different trial plan directory')
    require(identity==prerequisites(comparison),'Scene trial requires the original qualified RDP pair')
    raw=bounded_bytes(plan_path,16384)
    check_plan(json.loads(raw))
    root,child=identity['root'],identity['child']
    now=time.monotonic_ns()
    require(now<deadline_ns<=now+90_000_000_000,'Trial deadline exceeds 90 seconds')
    permit=dict(format=FORMAT,checkpointId=CHECKPOINT,comparison=str(Path(comparison).resolve()),identity=identity,
        evidenceDirectory=str(path.parent),planSha256=digest(raw),issuedAtMonotonicNs=now,
        goalEmbedding=dict(path=str(Path(goal_path).resolve()),sha256=digest(bounded_bytes(goal_path,128*1024))),
        binding=[root['processId'],root['instanceNonce'],child['processId'],child['instanceNonce'],deadline_ns])
    with path.open('x',encoding='utf-8') as stream:
        json.dump(permit,stream,indent=2,allow_nan=False)
    return permit


def admit(path,head,execution_context=None):
    """Consume once at startup; offline replay verifies the same claim and saved resident identity."""
    path=Path(path).resolve()
    folder=path.parent
    raw=bounded_bytes(path,65536)
    permit=json.loads(raw)
    if permit.get('format')=='bettergi-scene-endurance-trial-v1':
        from scene_endurance_trial import admit as admit_endurance
        return admit_endurance(path,head,execution_context)
    require(permit['format']==FORMAT and head.data['format']==SCENE_FORMAT
        and head.checkpoint_id==permit['checkpointId']==CHECKPOINT,'Wrong scene photo trial or observer')
    require(permit['identity']==prerequisites(permit['comparison']),'Changed scene trial owner')
    root,child=permit['identity']['root'],permit['identity']['child']
    require(Path(permit['evidenceDirectory']).resolve()==folder and permit['binding'][:4]==
        [root['processId'],root['instanceNonce'],child['processId'],child['instanceNonce']]
        and type(permit['issuedAtMonotonicNs']) is int and type(permit['binding'][4]) is int
        and 0<permit['binding'][4]-permit['issuedAtMonotonicNs']<=90_000_000_000,
        'Copied, redirected or extended scene trial permit')
    plan_raw=bounded_bytes(folder/'photo-requests.json',16384)
    check_plan(json.loads(plan_raw))
    require(digest(plan_raw)==permit['planSha256'],'Scene trial plan bytes changed')
    return bind_claim(path,head,permit,execution_context,validate_context,
        [r['id'] for r in json.loads(plan_raw)['requests']],'four-goal-photo-trial')


def bind_claim(path,head,permit,execution_context,validator,request_ids,scope):
    """Share only the one-use run claim and saved-worker replay; each scenario validates its own immutable limits first."""
    path=Path(path).resolve()
    folder=path.parent
    raw=bounded_bytes(path,65536)
    require(json.loads(raw)==permit,'Scene trial permit changed during admission')
    claim_path=folder/'scene-photo-claim.json'
    if execution_context is not None:
        validator(execution_context,permit,folder)
        require(permit['issuedAtMonotonicNs']<=time.monotonic_ns()<permit['binding'][4], 'Scene trial permit expired')
        control=json.loads(bounded_bytes(Path(str(folder/'patrol.json')+'.control.json'),2048))
        require(control['version']==1 and control['command']=='run' and re.fullmatch('[a-f0-9]{32}',control['runId']),
            'Scene trial lacks its current addressed run command')
        claim=dict(permitSha256=digest(raw),checkpointId=CHECKPOINT,planSha256=permit['planSha256'],
            runId=control['runId'],workerProcessId=os.getpid(),claimedAtMonotonicNs=time.monotonic_ns())
        with claim_path.open('x',encoding='utf-8') as stream:
            json.dump(claim,stream,indent=2,allow_nan=False)
    else:
        claim=json.loads(bounded_bytes(claim_path,8192))
        resident=json.loads(bounded_bytes(folder/'patrol.json',1024*1024))
        require(resident['runId']==claim['runId'] and resident['windowsSessionId']==permit['identity']['child']['windowsSessionId'],
            'Photo replay differs from the single-use resident claim')
        jobs=list((folder/'jobs').glob('*.job.json'))
        require(len(jobs)==1,'Missing unique photo-trial job')
        from stream_client import parse_arguments
        argv=json.loads(bounded_bytes(jobs[0],65536))['argv']
        script=[i for i,value in enumerate(argv) if Path(value).name=='stream_client.py']
        require(len(script)==1,'Unexpected scene trial worker')
        try:
            context=parse_arguments(argv[script[0]+1:])
        except SystemExit as error:
            raise ValueError('Recorded scene-trial worker options are invalid') from error
        validator(context,permit,folder)
    require(claim['permitSha256']==digest(raw) and claim['checkpointId']==CHECKPOINT
        and claim['planSha256']==permit['planSha256']
        and permit['issuedAtMonotonicNs']<=claim['claimedAtMonotonicNs']<permit['binding'][4], 'Scene trial claim changed')
    head._scene_photo_admission=dict(folder=str(folder),permitSha256=digest(raw),runId=claim['runId'],
        claimSha256=digest(claim_path.read_bytes()),checkpointId=CHECKPOINT,requestIds=request_ids,scope=scope,
        planSha256=permit['planSha256'],queuePolicySha256=permit.get('queuePolicySha256'),
        ownerManifestSha256=permit.get('ownerManifestSha256'))
    return dict(route=STREET_PATROL_ROUTE,recommendation='bounded-photo-trial-only',**head._scene_photo_admission)


def require_admission(head,output=None):
    """A bare shadow observer or a different output folder never gains photograph authority."""
    admission=getattr(head,'_scene_photo_admission',None)
    require(isinstance(admission,dict) and admission.get('checkpointId')==head.checkpoint_id==CHECKPOINT,
        'Experimental landmark metrics are shadow-only without their single-use photo trial')
    if output is not None:
        output=Path(output).resolve()
        require(output.parent==Path(admission['folder'])/'station-photos' and output.name in admission['requestIds'],
            'Photo output is outside the admitted scene trial')
    return admission


def require_runtime_plan(head,directory,checkpoint_id,run_id,plan_sha,*,open_queue,batch_count,legs,limits_profile):
    """Recheck the consumed plan after model warm-up, before the controller may send its first action."""
    admission=require_admission(head)
    folder=Path(admission['folder'])
    require(Path(directory).resolve()==folder/'station-photos' and checkpoint_id==head.checkpoint_id
        and run_id==admission['runId'] and plan_sha==admission['planSha256'],
        'Resident photo plan differs from its consumed scene permission')
    if open_queue:
        from scene_endurance_trial import require_queue_admission
        require_queue_admission(head)
        require((batch_count,legs,limits_profile)==(40,256,'endurance-v1'), 'Changed runtime scene queue limits')
        for name,key in [('queue-policy.json','queuePolicySha256'),('required-owner.json','ownerManifestSha256')]:
            require(digest(bounded_bytes(folder/name,65536))==admission[key],
                'Scene queue evidence changed during model warm-up')
    else:
        require(admission['scope']=='four-goal-photo-trial' and batch_count is None and legs==8,
            'Changed runtime scene photo trial scope')
