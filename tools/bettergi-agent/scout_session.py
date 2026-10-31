"""Keep one Open P2P policy in an ordinary RDP worker between explicit, reviewed scouting legs.

Run with ``run --directory NEW_DIRECTORY --owner-from SEALED_LINEAGE``. While its
session.json says awaitingReview, use ``submit --session DIRECTORY --review JSON``.
The review must use a fresh passive capture made after the advertised reviewAfterUnixNs.
``stop --session DIRECTORY`` is terminal, including while no input lease is open.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
import time
import uuid

import resident_runtime as runtime
import run_rdp_patrol as patrol
import stream_client as client
from hybrid_routes import SCOUT_GRASS_ROUTE, SCOUT_GROVE_ROUTE, SCOUT_ROUTES, route_points
from hybrid_navigation import yaw_error
from resident_runtime import OPEN_P2P_SHA256
from map_owner import load_map_owner
from navigation_profiles import SCOUT_PROFILE, allows_pose_scope, required_profile
from run_patrol_series import SeriesGuard
from reviewed_scout_route import ReviewedScoutRoute,reviewed_route_policy


ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT/'artifacts/live'
PER_LEG_FIELDS = frozenset(('pipe','output','record_dir','control_file','seconds','segment_seconds',
    'record_max_mib','patrol_series_binding','hybrid_route','navigation_profile','reviewed_scout_route'))
REQUEST_FIELDS = frozenset(('version','sessionId','requestId','afterRequestId','routeId','navigationProfile',
    'maximumLegs','modelConfigurationSha256','reviewFile','reviewSha256','nativePlanSha256',
    'nativeResultSha256','imageSha256','imageMetadataSha256'))


def require(value, message):
    """Refuse incomplete authority or evidence before opening any input lease."""
    if not value:
        raise ValueError(message)


def canonical_sha(value):
    """Fingerprint the exact immutable configuration independently of JSON whitespace."""
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def file_sha(path):
    """Hash one named local file without loading a model or scanning a directory tree."""
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def live_path(path, *, existing=True):
    """Keep session commands and review evidence in the workspace's local live artifact tree."""
    path=Path(path).absolute()
    resolved=path.resolve(strict=existing)
    require(path==resolved and resolved.is_relative_to(LIVE.resolve()),'Expected an unlinked local live artifact path')
    return resolved


def read_json(path, maximum=1024*1024):
    """Bound command/evidence reads and reject non-object documents."""
    path=live_path(path)
    with path.open('rb') as stream:
        raw=stream.read(maximum+1)
    require(0<len(raw)<=maximum,'JSON evidence exceeds its bounded size')
    value=json.loads(raw.decode('utf-8-sig'))
    require(isinstance(value,dict),'Expected a JSON object')
    return value,hashlib.sha256(raw).hexdigest()


def immutable_arguments(args):
    """Only route, output and bounded lease bookkeeping may vary between cached-policy calls."""
    return {key:str(value) if isinstance(value,Path) else value
            for key,value in vars(args).items() if key not in PER_LEG_FIELDS}


def model_contract(args):
    """Pin the deployed Open P2P bytes, instruction bytes and non-leg arguments before loading."""
    checkpoint,goal=Path(args.checkpoint).resolve(strict=True),Path(args.goal_embedding).resolve(strict=True)
    checkpoint_sha=file_sha(checkpoint)
    require(checkpoint_sha==OPEN_P2P_SHA256,'The scout session requires the exact deployed Open P2P checkpoint')
    return dict(arguments=immutable_arguments(args),checkpointSha256=checkpoint_sha,goalSha256=file_sha(goal))


def file_stamp(path):
    """Detect replacement or edits of the large already-hashed checkpoint without rehashing it per leg."""
    status=Path(path).stat()
    return status.st_dev,status.st_ino,status.st_size,status.st_mtime_ns


def owner_pair(lifecycle, owner):
    """Verify the original pair while permitting independent passive work between leases."""
    discovery=lifecycle.discover()
    require(not discovery.get('unavailable') and len(discovery['instances'])==2,'Incomplete or ambiguous scout ownership')
    roles={entry['instanceType']:entry for entry in discovery['instances']}
    root,child=roles['Primary'],roles['ChildSession']
    actual={role:{key:value[key] for key in ('processId','windowsSessionId','instanceNonce')}
            for role,value in (('root',root),('child',child))}
    require(actual==owner,'The original scout owner changed')
    lifecycle.require_role(child,'ChildSession')
    lifecycle._require_connected_root(root,child)
    require(root.get('uiStatus')=='current' and root.get('childWindowMinimized') is True
            and child.get('runtimeRunning') is True and child.get('automationState')=='game_ready',
            'The original minimized game runtime is unavailable')
    return root,child


def idle_child(child):
    """A busy passive observer is not an owner replacement, but cannot share a new input lease."""
    return (child.get('taskRunning') is False and child.get('agentStreamRunning') is False
            and child.get('pilotState') in ('idle','completed','failed','cancelled'))


def require_ordinary(session):
    """Use the existing runner's native token check; the worker must not run elevated or on the console."""
    runtime.control_module()
    from child_runner import require_ordinary_rdp,windows_identity
    require_ordinary_rdp(windows_identity(),session)


class SessionWatch:
    """Keep identity, thermal and terminal stop supervision alive during model loading and idle review."""
    def __init__(self, folder, settings, owner, lifecycle):
        self.folder,self.settings=folder,settings
        self.series=SeriesGuard(folder/'STOP',settings.seconds)
        self.series.required_identity=copy.deepcopy(owner)
        self.series.admit(lifecycle,*owner_pair(lifecycle,owner))
        self.reason=None
        self.last_sample=time.monotonic()
        self.active=None
        self.run_id=None
        self._lock=threading.Lock()
        self._finished=threading.Event()
        self._threads=[]

    def start(self):
        """Require one healthy sample before loading and then monitor without blocking inference."""
        self._sample()
        self.check()
        for target,name in ((self._thermal,'scout-temperature'),(self._monitor,'scout-stop')):
            worker=threading.Thread(target=target,name=name,daemon=True)
            self._threads.append(worker)
            worker.start()

    def latch(self, reason):
        """Cooling, deletion of STOP, or a later healthy status never clear a terminal reason."""
        with self._lock:
            self.reason=self.reason or reason

    def _sample(self):
        """Reuse the existing bounded NVIDIA sampler and its unchanged 78 C cutoff."""
        try:
            sample=patrol.log_sample(self.folder,self.settings.nvidia_smi)
            if 'error' in sample:self.latch('telemetryLost')
            elif sample['temperatureC']>=patrol.STOP_C:self.latch('temperatureLimit')
            else:self.last_sample=time.monotonic()
        except Exception:
            self.latch('telemetryLost')

    def _thermal(self):
        """Keep thermal samples independent of command delivery and slow endpoint refreshes."""
        while not self._finished.wait(patrol.POLL_SECONDS):
            self._sample()

    def _monitor(self):
        """Deliver a stop only to the currently bound leg, including a stop received during its startup."""
        while not self._finished.wait(patrol.CONTROL_POLL_SECONDS):
            reason=self.series.stop_reason()
            if reason:self.latch(reason)
            if time.monotonic()-self.last_sample>=patrol.MAX_GPU_SAMPLE_AGE_SECONDS:self.latch('telemetryLost')
            with self._lock:
                try:
                    if self.active is not None:
                        self.run_id=patrol.pin_resident(self.active,self.run_id)
                        if self.run_id:
                            command=patrol.addressed_control(self.active/'patrol.json.control.json',self.run_id)
                            if command['command']=='stop':self.reason=self.reason or 'operatorStop'
                            if self.reason and command['command']!='stop':patrol.stop_resident(self.active,self.run_id)
                except Exception:
                    self.reason=self.reason or 'invalidResidentControl'

    def check(self):
        """Check the same terminal conditions synchronously at every admission boundary."""
        reason=self.series.stop_reason()
        if reason:self.latch(reason)
        if time.monotonic()-self.last_sample>=patrol.MAX_GPU_SAMPLE_AGE_SECONDS:self.latch('telemetryLost')
        if self.reason:raise RuntimeError(self.reason)

    def activate(self, folder):
        """Bind a fresh leg directory; an earlier control file can never stop a later occupant."""
        with self._lock:
            require(self.active is None,'A scout leg is already active')
            self.active,self.run_id=folder,None

    def deactivate(self):
        """Retire the addressed leg only after its synchronous resident call has returned."""
        with self._lock:
            self.active,self.run_id=None,None

    def binding(self):
        """Reuse the exact original owner and non-extending series deadline on each leg."""
        return self.series.binding()

    def close(self):
        """Retire owned monitoring threads without touching a passive observer or restarting a job."""
        self._finished.set()
        self.series.finished.set()
        for worker in self._threads:worker.join(timeout=patrol.GPU_QUERY_TIMEOUT_SECONDS+1)
        require(not any(worker.is_alive() for worker in self._threads),'Scout monitor cleanup is unresolved')


def leg_arguments(settings, owner, route, folder, binding, remaining_mib, reviewed_route=None):
    """Reuse the validated patrol argument builder and preserve its default Open P2P behavior."""
    options=patrol.options(['--route',SCOUT_GRASS_ROUTE if reviewed_route is not None else route,'--legs','1','--navigation-profile',SCOUT_PROFILE,'--seconds','35',
        '--source',str(settings.source),'--checkpoint',str(settings.checkpoint),
        '--goal-embedding',str(settings.goal_embedding),'--ffmpeg',str(settings.ffmpeg),
        '--native-combat-observation','--retain-policy-rgb'])
    argv=patrol.patrol_argv(options,owner['child']['windowsSessionId'],folder)[5:]
    if reviewed_route is not None:
        require(route==reviewed_route.route_id,'Explicit scout route identity changed')
        runtime.atomic_json(folder/'reviewed-route.json',reviewed_route.document())
        index=argv.index('--hybrid-route')
        argv[index:index+2]=['--reviewed-scout-route',str(folder/'reviewed-route.json')]
    if binding:argv.append('--patrol-series-binding='+binding)
    args=client.parse_arguments(argv)
    args.patrol_series_binding=runtime.parse_series_binding(binding) if binding else None
    args.record_max_mib=remaining_mib
    return args


def qualify_review_frame(frame, anchor):
    """Require the existing scout's same-source, grounded-looking, fresh pose at the reviewed start."""
    pose,world,source=frame.get('navigationPose') or {},frame.get('frameWorldReadiness') or {},frame.get('sourceFrame') or {}
    require(pose.get('state')=='valid' and pose.get('frameId')==frame.get('frameId')
            and allows_pose_scope(pose,SCOUT_PROFILE),'Reviewed pose is invalid or outside the scout scope')
    require(.99<=pose.get('positionConfidence',0)<=1 and .2<=pose.get('yawConfidence',0)<=1
            and type(pose.get('yawDegrees')) in (int,float) and math.isfinite(pose['yawDegrees']),
            'Reviewed pose confidence or heading is invalid')
    require(world.get('ready') is True and world.get('sourceFrameId')==frame['frameId']
            and world.get('sourceFrame')==source and (frame.get('worldReadiness') or {}).get('ready') is True,
            'Reviewed pose and world readiness do not share the same source frame')
    motion=frame.get('motionEvidence') or {}
    require(motion.get('status')=='normal' and motion.get('spaceKeyMatched') is False
            and 0<=frame.get('sourceFrameAgeMs',999)<=150,'Reviewed frame is airborne, climbing or stale')
    require((frame.get('executionContext') or {}).get('lastSequence')==0,'Passive scene contains input history')
    require(isinstance(source.get('captureEpoch'),str) and source['captureEpoch']
            and type(source.get('timestamp100ns')) is int and source['timestamp100ns']>0
            and type(source.get('freshnessAtMs')) in (int,float) and math.isfinite(source['freshnessAtMs']),
            'Reviewed source provenance is incomplete')
    require(math.dist((pose['x'],pose['y']),anchor)<=2,'Reviewed pose differs from the frozen route start')


def review_evidence(path, manifest, after_ns):
    """Bind one explicit visual review to its unchanged, input-disabled native endpoint and image."""
    review,review_sha=read_json(path,16384)
    route=review.get('routeId')
    spec=None
    if 'routeSpec' in review:
        require(manifest.get('reviewedScoutRoutePolicy')==reviewed_route_policy(),'This worker did not authorize reviewed geometry')
        spec=ReviewedScoutRoute.from_document(review['routeSpec'])
        require(route==spec.route_id and review.get('points')==spec.document()['points']
                and review.get('routeSpecSha256',spec.sha256)==spec.sha256,'Reviewed scout geometry or identity changed')
        points=spec.points
    else:
        require(route in manifest['routes'] and review.get('points')==manifest['routes'][route],
                'The reviewed route is not in this worker\'s frozen scout registry')
        require('routeSpecSha256' not in review,'Reviewed geometry digest has no specification')
        points=manifest['routes'][route]
    require(review.get('attacksAllowed') is False and type(review.get('maximumLegs')) is int
            and review['maximumLegs']==1,'A scout review cannot authorize attacks or multiple legs')
    require(type(review.get('inspectedHealth')) is int and type(review.get('inspectedMaximumHealth')) is int
            and 0<review['inspectedHealth']<=review['inspectedMaximumHealth']
            and isinstance(review.get('visualReview'),str) and review['visualReview'].strip(),'Missing explicit scene/health review')
    endpoint=live_path(review['nativeEndpoint'])
    plan,plan_sha=read_json(endpoint/'plan.json')
    result,result_sha=read_json(endpoint/'result.json',4*1024*1024)
    require(plan.get('owner')==manifest['owner'] and plan.get('enableInput') is False
            and plan.get('modelLoaded') is False and plan.get('navigationProfile')==SCOUT_PROFILE,
            'The native review belongs to another owner or input scope')
    require(result.get('status')=='completed' and result.get('inputEnabled') is False
            and result.get('modelLoaded') is False and result.get('ownerIdleMinimizedAfter') is True
            and len(result.get('stableSamples',[]))==3 and not result.get('error'), 'The passive endpoint did not complete cleanly')
    samples=result['stableSamples']
    for frame in samples:
        require(frame in result.get('observations',[]),'Stable scene sample is not an original native observation')
        qualify_review_frame(frame,points[0])
    for before,after in zip(samples,samples[1:]):
        a,b=before['sourceFrame'],after['sourceFrame']
        p,q=before['navigationPose'],after['navigationPose']
        require(a['captureEpoch']==b['captureEpoch'] and a['timestamp100ns']<b['timestamp100ns']
                and before['frameId']<after['frameId'] and 80<=b['freshnessAtMs']-a['freshnessAtMs']<=250
                and before['frameWorldReadiness']['epoch']==after['frameWorldReadiness']['epoch']
                and math.dist((p['x'],p['y']),(q['x'],q['y']))<=.35 and yaw_error(p['yawDegrees'],q['yawDegrees'])<=3,
                'Reviewed native scene is not stationary in one source/world epoch')
    name=review.get('imageName')
    require(isinstance(name,str) and Path(name).name==name and name.endswith('.png'),'Invalid reviewed image name')
    image=live_path(endpoint/name)
    require(0<image.stat().st_size<=16*1024*1024,'Reviewed image exceeds its bounded size')
    metadata,metadata_sha=read_json(image.with_suffix('.json'),65536)
    require(metadata.get('imageSha256')==review.get('imageSha256')==file_sha(image),'Reviewed image bytes changed')
    joined=[frame for frame in result.get('observations',[]) if frame.get('frameId')==metadata.get('frameId')]
    require(joined and all(frame.get('sourceFrame')==metadata.get('sourceFrame') for frame in joined),
            'The reviewed image is not joined to its original native source')
    # Repeated polls may age the same pixels, but cannot change their immutable recognition/source evidence.
    fields=('frameId','sourceFrame','navigationPose','frameWorldReadiness','motionEvidence')
    identity={key:joined[0].get(key) for key in fields}
    require(all({key:frame.get(key) for key in fields}==identity for frame in joined),
            'Repeated image polls contain conflicting source or recognition evidence')
    qualified=[]
    for frame in joined:
        try:qualify_review_frame(frame,points[0])
        except (ValueError,KeyError,TypeError):continue
        qualified.append(frame)
    require(qualified,'The reviewed image has no fresh qualified world-readiness observation')
    selected=min(qualified,key=lambda frame:frame['sourceFrameAgeMs'])
    require(selected['sourceFrame']['captureEpoch']==samples[0]['sourceFrame']['captureEpoch']
            and selected['frameWorldReadiness']['epoch']==samples[0]['frameWorldReadiness']['epoch'],
            'Reviewed image belongs to another source/world epoch')
    require(min((endpoint/'result.json').stat().st_mtime_ns,image.with_suffix('.json').stat().st_mtime_ns)>=after_ns,
            'A fresh native scene is required after the previous leg or worker startup')
    evidence=dict(routeId=route,reviewSha256=review_sha,nativePlanSha256=plan_sha,nativeResultSha256=result_sha,
                  imageSha256=review['imageSha256'],imageMetadataSha256=metadata_sha)
    if spec is not None:evidence.update(routeSpec=spec.document(),routeSpecSha256=spec.sha256)
    return evidence


def validate_request(path, manifest, after_id, after_ns):
    """Consume only a single fresh request for this session, configuration and prior completed leg."""
    request,digest=read_json(path,16384)
    fields=REQUEST_FIELDS|{'routeSpec','routeSpecSha256'} if 'routeSpec' in request else REQUEST_FIELDS
    require(set(request)==fields and request['version']==1 and request['sessionId']==manifest['sessionId'],
            'Unexpected scout request schema or session')
    require(isinstance(request['requestId'],str) and re.fullmatch('[a-f0-9]{32}',request['requestId'])
            and path.stem==request['requestId'], 'Invalid scout request identity')
    require(request['afterRequestId']==after_id and request['modelConfigurationSha256']==manifest['modelConfigurationSha256']
            and request['navigationProfile']==SCOUT_PROFILE and type(request['maximumLegs']) is int
            and request['maximumLegs']==1,'The request changed its predecessor, model or navigation scope')
    evidence=review_evidence(request['reviewFile'],manifest,after_ns)
    require(('routeSpec' in request)==('routeSpec' in evidence),'Request geometry is absent from the fresh review')
    require(all(request[key]==value for key,value in evidence.items()),'The reviewed request evidence changed')
    return request,digest


def submit(directory, review):
    """Publish one explicit immutable request; this function never generates another destination."""
    directory=live_path(directory)
    manifest,_=read_json(directory/'manifest.json')
    state,_=read_json(directory/'session.json')
    require(state.get('sessionId')==manifest['sessionId'] and state.get('state')=='awaitingReview'
            and not (directory/'STOP').exists(),'The scout worker is not waiting for a reviewed request')
    request=dict(version=1,sessionId=manifest['sessionId'],requestId=uuid.uuid4().hex,
        afterRequestId=state['afterRequestId'],navigationProfile=SCOUT_PROFILE,maximumLegs=1,
        modelConfigurationSha256=manifest['modelConfigurationSha256'],reviewFile=str(live_path(review)),
        **review_evidence(review,manifest,state['reviewAfterUnixNs']))
    require(not any(path.stem not in state['seenRequestIds'] for path in (directory/'requests').glob('*.json')),
            'A scout request is already pending')
    path=directory/'requests'/(request['requestId']+'.json')
    runtime.atomic_json(path,request)
    return dict(requestId=request['requestId'],requestFile=str(path))


def audit_leg(folder, request):
    """Require the unchanged independent route/source/input audit plus the opt-in cached-policy proof."""
    from audit_hybrid_run import audit
    report=audit(folder/'patrol.json',folder/'patrol-recording',repository=ROOT,minimum_legs=1,
                 policy_reuse_proof=Path(str(folder/'patrol.json')+'.reuse.json'),
                 reviewed_scout_route=ReviewedScoutRoute.from_document(request['routeSpec']) if 'routeSpec' in request else None)
    require(report.get('passed') is True and report.get('verifiedLegs')==1
            and report.get('routeId')==request['routeId'] and report.get('controllerLeases')==1,
            'The reviewed scout leg failed its independent audit')
    runtime.atomic_json(folder/'audit.json',report)
    return report


def account_leg(row, terminal_state=None, reason=None):
    """Retain the actual resident outcome even when execution or subsequent verification raises."""
    if terminal_state is not None and row['state']=='running':row['state']=terminal_state
    if reason is not None and row['state']!='verified':row['reason']=str(reason)
    try:
        report,digest=read_json(Path(row['directory'])/'patrol.json',4*1024*1024)
        require(isinstance(report,dict) and re.fullmatch('[a-f0-9]{32}',str(report.get('runId',''))),
                'Resident accounting lacks an original run identity')
        row.update(runId=report['runId'],residentStatus=report.get('status'),endReason=report.get('endReason'),
            residentError=report.get('error'),residentManifestSha256=digest,evidenceComplete=report.get('evidenceComplete'),
            failedLeases=report.get('failedLeases'),modelLoads=report.get('modelLoads'),
            modelReused=report.get('modelLoads')==0 and (report.get('policyReuse') or {}).get('runId')==report['runId']
                and (report.get('policyReuse') or {}).get('requestId')==row['requestId'])
        size=report.get('recordedBytes')
        require(type(size) is int and size>=0,'Resident recording byte accounting is unavailable')
        row['recordedBytes']=size
        require(report.get('status') in ('completed','failed'),'Resident manifest did not reach a terminal state')
        if row['state']!='verified' and report['status']=='failed':row['state']='failed'
        row.pop('accountingError',None)
    except (OSError,ValueError,TypeError,AttributeError) as error:
        # An absent/unpublished manifest is unknown evidence, never an asserted zero-byte successful run.
        row.setdefault('recordedBytes',None)
        row.update(state='failed',accountingError=str(error))


def account_session(state):
    """Sum each retained run exactly once and distinguish unknown accounting from an empty recording."""
    state['recordedBytes']=sum(row['recordedBytes'] for row in state['legs'] if type(row.get('recordedBytes')) is int)
    state['recordedBytesComplete']=all(type(row.get('recordedBytes')) is int and not row.get('accountingError') for row in state['legs'])


def run_session(settings, *, lifecycle=None, loader=None, runner=None, watch_factory=SessionWatch, auditor=audit_leg):
    """Load once, run only reviewed one-leg requests, and remain bridge-free between successful runs."""
    owner=load_map_owner(settings.owner_from)
    require_ordinary(owner['child']['windowsSessionId'])
    lifecycle=lifecycle or runtime.control_module()
    owner_pair(lifecycle,owner)
    directory=live_path(settings.directory,existing=False)
    directory.mkdir(parents=True,exist_ok=False)
    (directory/'requests').mkdir()
    started_ns=time.time_ns()
    session_id=uuid.uuid4().hex
    routes=settings.routes or [SCOUT_GRASS_ROUTE,SCOUT_GROVE_ROUTE]
    require(routes and len(set(routes))==len(routes) and all(route in SCOUT_ROUTES and required_profile(route)==SCOUT_PROFILE
            for route in routes),'Only explicitly registered scout routes may enter a worker')
    base=leg_arguments(settings,owner,routes[0],directory/'bootstrap',None,settings.record_max_mib)
    configuration=model_contract(base)
    checkpoint_stamp=file_stamp(base.checkpoint)
    manifest=dict(version=1,sessionId=session_id,owner=owner,worker=dict(processId=os.getpid(),windowsSessionId=owner['child']['windowsSessionId']),
        routes={route:[list(point) for point in route_points(route)] for route in routes},
        modelConfigurationSha256=canonical_sha(configuration),configuration=configuration,
        stopTemperatureC=78,sourceFreshnessMs=150,actionHoldMs=100,legDeadlineSeconds=35,sessionSeconds=settings.seconds)
    if getattr(settings,'allow_reviewed_routes',False):manifest['reviewedScoutRoutePolicy']=reviewed_route_policy()
    runtime.atomic_json(directory/'manifest.json',manifest)
    state=dict(version=1,sessionId=session_id,state='loading',modelLoads=0,modelLoadSeconds=0.0,
        afterRequestId=None,reviewAfterUnixNs=started_ns,seenRequestIds=[],legs=[],recordedBytes=0,recordedBytesComplete=True)
    watch=None
    policy=None

    def publish():
        """Expose small session evidence without copying images, checkpoints or inference state."""
        runtime.atomic_json(directory/'session.json',state)

    def verify_configuration(args):
        """A cached object never silently accepts changed model, sampling, goal or safety settings."""
        require(immutable_arguments(args)==configuration['arguments'],'Cached model configuration changed')
        spec=getattr(args,'reviewed_scout_route',None)
        route_allowed=(args.hybrid_route in manifest['routes'] if spec is None else
                       manifest.get('reviewedScoutRoutePolicy')==reviewed_route_policy() and args.hybrid_route==spec.route_id)
        require(args.navigation_profile==SCOUT_PROFILE and route_allowed and args.seconds==35,
                'Cached scout scope or leg deadline changed')
        require(file_stamp(args.checkpoint)==checkpoint_stamp and file_sha(args.goal_embedding)==configuration['goalSha256'],
                'Cached checkpoint or instruction bytes changed')

    try:
        publish()
        watch=watch_factory(directory,settings,owner,lifecycle)
        watch.start()
        began=time.monotonic()
        policy=(loader or client.load_policy)(base)
        state.update(modelLoads=int(policy is not None),modelLoadSeconds=time.monotonic()-began)
        require(policy is not None and callable(getattr(policy,'reset',None)) and callable(getattr(policy,'set_goal',None)),
                'A resettable, goal-conditioned Open P2P policy is required')
        verify_configuration(base)
        watch.check()
        proof=dict(version=1,kind='scout-policy-session',sessionId=session_id,worker=manifest['worker'],owner=owner,
                   modelConfigurationSha256=manifest['modelConfigurationSha256'],configuration=configuration,
                   checkpointSha256=OPEN_P2P_SHA256,modelLoads=1,modelLoadSeconds=state['modelLoadSeconds'])
        if 'reviewedScoutRoutePolicy' in manifest:proof['reviewedScoutRoutePolicy']=manifest['reviewedScoutRoutePolicy']
        runtime.atomic_json(directory/'policy-proof.json',proof)
        proof_sha=file_sha(directory/'policy-proof.json')
        state['state']='awaitingReview'
        publish()
        while True:
            watch.check()
            pending=sorted(path for path in (directory/'requests').glob('*.json') if path.stem not in state['seenRequestIds'])
            require(len(pending)<=1 and len(state['seenRequestIds'])<64,'Only one fresh scout request may be pending')
            if not pending:
                time.sleep(patrol.CONTROL_POLL_SECONDS)
                continue
            path=pending[0]
            request,request_sha=validate_request(path,manifest,state['afterRequestId'],state['reviewAfterUnixNs'])
            state['seenRequestIds'].append(request['requestId'])
            _,child=owner_pair(lifecycle,owner)
            if not idle_child(child):
                # Passive inspection is allowed; a refused request is never retried automatically when it ends.
                state['lastRefusal']=dict(requestId=request['requestId'],reason='childBusy')
                publish()
                continue
            remaining=settings.record_max_mib-math.ceil(state['recordedBytes']/(2**20))
            require(remaining>=1,'Scout session recording budget exhausted')
            folder=directory/'legs'/request['requestId']
            folder.mkdir(parents=True,exist_ok=False)
            spec=ReviewedScoutRoute.from_document(request['routeSpec']) if 'routeSpec' in request else None
            args=leg_arguments(settings,owner,request['routeId'],folder,watch.binding(),remaining,spec)
            verify_configuration(args)
            watch.check()
            require(not getattr(policy,'_pending_feedback',False),'Previous model action history is unresolved')
            policy.set_goal(args.goal_embedding)  # Existing adapter reset retains weights and its validated CUDA graph.
            row=dict(requestId=request['requestId'],requestSha256=request_sha,routeId=request['routeId'],directory=str(folder),state='running')
            state['legs'].append(row)
            state['state']='running'
            publish()
            reuse=dict(version=1,sessionId=session_id,worker=manifest['worker'],owner=owner,
                modelConfigurationSha256=manifest['modelConfigurationSha256'],sessionProof=str(directory/'policy-proof.json'),
                sessionProofSha256=proof_sha,requestId=request['requestId'],requestFile=str(path),requestSha256=request_sha,
                routeId=request['routeId'],navigationProfile=SCOUT_PROFILE)
            if spec is not None:reuse.update(routeSpec=spec.document(),routeSpecSha256=spec.sha256)

            def cached(current):
                """Keep the existing injected-loader seam while checking authority immediately before lease creation."""
                verify_configuration(current)
                require(current.hybrid_route==request['routeId'],'Cached policy belongs to another reviewed route')
                require(getattr(current,'reviewed_scout_route',None)==spec,'Cached policy geometry differs from its reviewed request')
                watch.check()
                return policy

            watch.activate(folder)
            try:
                code=(runner or runtime.run_resident)(args,cached,client.run_episode,policy_reuse=reuse)
            finally:
                watch.deactivate()
            watch.check()
            report,_=read_json(folder/'patrol.json',4*1024*1024)
            require(code==0 and report.get('status')=='completed' and report.get('endReason')=='hybridLegLimit'
                    and report.get('evidenceComplete') is True and report.get('failedLeases')==0
                    and report.get('modelLoads')==0 and report.get('modelLoadSeconds')==0,
                    'The scout leg failed or has unresolved evidence')
            finished_control=patrol.addressed_control(folder/'patrol.json.control.json',report['runId'])
            require(finished_control['command']=='run'
                    and not any(key in finished_control for key in ('goalRequestId','goalEmbedding','goalIntent')),
                    'Operator stop, pause or goal request ended the addressed scout leg')
            auditor(folder,request)
            _,child=owner_pair(lifecycle,owner)
            require(idle_child(child),'Scout cleanup did not release the original child')
            watch.check()
            row.update(state='verified',runId=report['runId'],modelLoads=0,modelReused=True)
            account_leg(row)
            require(not row.get('accountingError'),'The verified scout leg has unresolved resident accounting')
            account_session(state)
            state.update(state='awaitingReview',afterRequestId=request['requestId'],reviewAfterUnixNs=time.time_ns())
            publish()
    except Exception as error:
        state.update(state='stopped' if watch and watch.reason else 'failed',reason=str(error))
        return 1
    finally:
        if watch is not None:
            try:watch.close()
            except Exception as error:state.update(state='failed',reason='Monitor cleanup failed: '+str(error))
        if state['state'] not in ('failed','stopped'):
            state.update(state='failed',reason='Worker retired without a terminal session state')
        for row in state['legs']:
            account_leg(row,state['state'],state.get('reason'))
        account_session(state)
        publish()


def options(argv=None):
    """Expose bounded local session, explicit submission and terminal stop commands."""
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_subparsers(dest='command',required=True)
    run=modes.add_parser('run')
    run.add_argument('--directory',type=Path,required=True)
    run.add_argument('--owner-from',type=Path,required=True)
    run.add_argument('--seconds',type=int,default=600)
    run.add_argument('--route',dest='routes',action='append',choices=SCOUT_ROUTES)
    run.add_argument('--allow-reviewed-routes',action='store_true',help='Allow fresh explicit two-point scout reviews within the existing scope')
    agent=ROOT/'artifacts/agent'
    run.add_argument('--checkpoint',type=Path,default=agent/'models/open-p2p-150M/150M/checkpoint-step=00500000.ckpt')
    run.add_argument('--source',type=Path,default=agent/'sources/open-p2p')
    run.add_argument('--goal-embedding',type=Path,default=agent/'goals/ground-street-walk.json')
    run.add_argument('--ffmpeg',type=Path,default=Path(shutil.which('ffmpeg') or 'C:/Programs/ffmpeg.exe'))
    run.add_argument('--nvidia-smi',type=Path,default=Path(shutil.which('nvidia-smi') or 'C:/Windows/System32/nvidia-smi.exe'))
    run.add_argument('--record-max-mib',type=int,default=160)
    send=modes.add_parser('submit')
    send.add_argument('--session',type=Path,required=True)
    send.add_argument('--review',type=Path,required=True)
    stop=modes.add_parser('stop')
    stop.add_argument('--session',type=Path,required=True)
    geometry=modes.add_parser('route-spec',help='Describe one explicit geometry without launching or submitting a leg')
    geometry.add_argument('--start',type=float,nargs=2,required=True)
    geometry.add_argument('--end',type=float,nargs=2,required=True)
    args=parser.parse_args(argv)
    if args.command=='run' and not (30<=args.seconds<=1800 and 1<=args.record_max_mib<=160):
        parser.error('Keep the session within 30-1800 seconds and 1-160 MiB')
    return args


def main():
    """Keep the worker inside its original bounded ordinary RDP command; never detach or restart it."""
    args=options()
    if args.command=='run':return run_session(args)
    if args.command=='route-spec':
        spec=ReviewedScoutRoute((args.start,args.end))
        print(json.dumps(dict(routeId=spec.route_id,points=spec.document()['points'],routeSpec=spec.document(),routeSpecSha256=spec.sha256)))
        return 0
    if args.command=='submit':print(json.dumps(submit(args.session,args.review)))
    else:
        directory=live_path(args.session)
        manifest,_=read_json(directory/'manifest.json')
        try:
            with (directory/'STOP').open('x',encoding='utf-8') as stream:json.dump({'sessionId':manifest['sessionId']},stream)
        except FileExistsError:pass
        print(json.dumps(dict(sessionId=manifest['sessionId'],stopRequested=True)))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
