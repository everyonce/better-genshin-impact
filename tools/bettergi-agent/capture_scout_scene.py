"""Retain one bounded, input-disabled native scene in an explicitly selected scout scope."""
import argparse,copy,hashlib,json,math,shutil,subprocess,sys,time,traceback,uuid
from pathlib import Path

repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'tools/bettergi-agent'))
from run_rdp_patrol import ready_session,control_module
from map_owner import load_map_owner
from combat_paused_file_admission import PausedAdmission,canonical,owner_inputs
from resident_runtime import verify_bridge_identity,atomic_json
from stream_client import Bridge
from observation_profiles import P2P_NATIVE
from navigation_profiles import SCOUT_PROFILE,SCOUT_PROFILES,validate_capability,allows_pose_scope
from native_combat import negotiate,validate_frame
from native_ground_control import (negotiate as negotiate_ground,policy as ground_policy,
                                  validate_frame as validate_ground_frame)
from hybrid_navigation import yaw_error
from reviewed_scout_route import CURRENT_SCENE_INSPECTION


def require(value,message):
    """A missing source or stopped observation is never silently retried."""
    if not value:raise RuntimeError(message)


# Only this interpreter can spend a prepared capture; no serialized ready record grants authority.
_PREPARED_CAPTURES = {}


def parse_args(argv=None):
    """Retain the standalone CLI while allowing one fixed caller to prepare before world exposure."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    location=parser.add_mutually_exclusive_group(required=True)
    location.add_argument('--anchor',nargs=2,type=float)
    location.add_argument('--inspect-current',action='store_true',
        help='Inspect the current stable scene without granting navigation-review authority')
    parser.add_argument('--require-single-enemy',action='store_true',
        help='Require exactly one native bar candidate; this does not establish enemy identity')
    parser.add_argument('--owner-from',type=Path,required=True)
    parser.add_argument('--navigation-profile',choices=SCOUT_PROFILES,default=SCOUT_PROFILE)
    return parser.parse_args(argv)


def _stop_paths(args,stop_paths):
    """Bind the existing capture stops plus an optional fixed outer stop without accepting commands."""
    paths=tuple(dict.fromkeys((args.output.absolute()/'STOP',args.output.absolute().parent/'STOP',
                              *(Path(path).absolute() for path in stop_paths))))
    require(len(paths)<=4 and all(path.name=='STOP' and path==path.resolve()
        and path.is_relative_to((repo/'artifacts/live').resolve()) for path in paths),'Invalid capture STOP paths')
    return paths


def _stopped(paths):
    """Observe STOP both before and after potentially blocking preparation or discovery."""
    require(not any(path.exists() for path in paths),'Operator stop')


def _context(state):
    """Bind the same arguments, owner and original run throughout the held-file lifetime."""
    args=state['args']
    return dict(runId=state['runId'],output=str(args.output.absolute()),ownerFrom=str(args.owner_from.absolute()),
        anchor=args.anchor,inspectCurrent=args.inspect_current,requireSingleEnemy=args.require_single_enemy,
        navigationProfile=args.navigation_profile,owner=state['owner'],stopPaths=[str(path) for path in state['stops']])


def _state(token,run_id):
    """Refuse foreign, retired or cross-run in-memory preparation instead of rebuilding it."""
    state=_PREPARED_CAPTURES.get(token)
    require(state is not None and state['runId']==run_id,'Missing, foreign or retired capture preparation')
    require(canonical(_context(state))==state['admission'].context,'Prepared capture context changed')
    return state


def prepare_capture(args,*,run_id,stop_paths=()):
    """Perform file-only setup once; no native discovery, GPU query, model or input occurs here."""
    args=copy.deepcopy(args)
    require(isinstance(run_id,str) and 0<len(run_id)<=128,'Invalid capture preparation run')
    require(type(args.inspect_current) is bool and type(args.require_single_enemy) is bool
        and (args.anchor is None)==args.inspect_current and args.navigation_profile in SCOUT_PROFILES,
        'Invalid direct capture options')
    stops=_stop_paths(args,stop_paths)
    _stopped(stops)
    output=args.output.absolute()
    require(output==output.resolve() and output.is_relative_to((repo/'artifacts/live').resolve()),
        'Expected an unlinked local live-artifact destination')
    if args.anchor is not None:
        require(all(math.isfinite(value) for value in args.anchor),'Invalid expected endpoint')
        require(allows_pose_scope(dict(x=args.anchor[0],y=args.anchor[1],layerId='MapBack_2'),args.navigation_profile),
            'Expected endpoint is outside the selected scout scope')
    output.mkdir(parents=True,exist_ok=False)
    helper=Path(__file__).read_bytes()
    (output/'capture-helper.py').write_bytes(helper)
    owner,pins,packages=owner_inputs(args.owner_from,repo/'artifacts',load_map_owner)
    lifecycle=control_module()
    inspection=(dict(inspectionMode=CURRENT_SCENE_INSPECTION,navigationReviewAllowed=False,
        enemyIdentityVerified=False) if args.inspect_current else {})
    candidate_filter=(dict(requireSingleEnemyBarCandidate=True,enemyIdentityVerified=False)
        if args.require_single_enemy else {})
    report=dict(status='failed',inputEnabled=False,modelLoaded=False,observations=[],stableSamples=[],gpu=[],
        **(inspection|candidate_filter))
    atomic_json(output/'plan.json',dict(owner=owner,enableInput=False,modelLoaded=False,
        navigationProfile=args.navigation_profile,maximumObservationSeconds=30,
        sourceFreshnessMs=150,stopTemperatureC=78,captureHelperSha256=hashlib.sha256(helper).hexdigest(),
        modelLoadScope='this-capture-helper-only',
        **({'scoutGroundControlPolicy':ground_policy()} if args.anchor is not None else {}),
        **(inspection|candidate_filter|({'anchor':args.anchor} if args.anchor is not None else {}))))

    pins=dict(pins)
    pins[str(Path(__file__).absolute())]=hashlib.sha256(helper).hexdigest()
    pins[str(output/'capture-helper.py')]=hashlib.sha256(helper).hexdigest()
    census=lambda:sorted(name for name in pins if Path(name).is_file())
    state=dict(args=args,output=output,owner=copy.deepcopy(owner),lifecycle=lifecycle,report=report,
               runId=run_id,stops=stops,pins=pins)
    evidence={}
    report['immutablePreparation']=evidence
    admission=PausedAdmission(_context(state),pins,(),census,sorted(pins),packages,evidence)
    state['admission']=admission
    token=object()
    _PREPARED_CAPTURES[token]=state
    try:
        # Close collection-to-validation races while all original owner files are held.
        require(load_map_owner(args.owner_from)==owner,'Held capture owner no longer replays')
        _stopped(stops)
    except BaseException as error:
        errors=close_prepared_capture(token)
        if errors:raise BaseExceptionGroup('Capture preparation and handle cleanup failed',[error,RuntimeError('; '.join(errors))])
        raise
    return token


def prepared_capture_owner(token,*,run_id,owner_file=None):
    """Recheck the continuously held original owner files without repeating semantic ancestry replay."""
    state=_state(token,run_id)
    require(owner_file is None or Path(owner_file).absolute()==state['args'].owner_from.absolute(),
        'Prepared capture belongs to another owner file')
    _stopped(state['stops'])
    admission=state['admission']
    require(not admission.closed,'Capture preparation is closed')
    require(admission.census()==admission.expected_census,'Capture owner file census changed')
    for original,choice in admission.packages.items():
        require(Path(original).exists() is choice['originalPresent'],'Historical package selection changed')
    admission.files.verify()
    require(admission.census()==admission.expected_census,'Capture owner file census changed')
    for original,choice in admission.packages.items():
        require(Path(original).exists() is choice['originalPresent'],'Historical package selection changed')
    _stopped(state['stops'])
    return copy.deepcopy(state['owner'])


def close_prepared_capture(token):
    """Always close the original handles; retained cleanup errors cannot look like completion."""
    state=_PREPARED_CAPTURES.pop(token,None)
    if state is None:return []
    errors=state['admission'].close()
    if errors:
        state['report'].update(status='unresolved',immutableHandleCleanupError='; '.join(errors))
    atomic_json(state['output']/'result.json',state['report'])
    return errors


def run_capture(token,*,run_id):
    """Spend one capture and close its files before returning immutable scene evidence."""
    state=_state(token,run_id)
    require(not state['admission'].consumed,'Capture preparation was already consumed')
    failure=None
    try:
        state['admission'].consume(lambda:_context(state),state['report']['immutablePreparation'],
            lambda:_stopped(state['stops']))
        _run_capture(state)
    except BaseException as error:
        failure=error
        state['report'].update(status='failed',error=str(error),traceback=traceback.format_exc())
        raise
    finally:
        errors=close_prepared_capture(token)
        if errors:
            cleanup=RuntimeError('Immutable capture handle cleanup failed: '+'; '.join(errors))
            if failure is not None:raise BaseExceptionGroup('Capture and handle cleanup failed',[failure,cleanup])
            raise cleanup
    return copy.deepcopy(state['report'])


def _run_capture(state):
    """Run the original input-disabled native lifecycle after fresh owner and STOP checks."""
    args,output,owner,lifecycle,report=(state[key] for key in ('args','output','owner','lifecycle','report'))
    check_stopped=lambda:_stopped(state['stops'])
    def check_owner(*,supervising=True):
        if supervising:check_stopped()
        root,child=ready_session(lifecycle)
        if supervising:check_stopped()
        actual={role:{key:state[key] for key in ('windowsSessionId','processId','instanceNonce')}
                for role,state in (('root',root),('child',child))}
        require(actual==owner,'Original minimized idle owner changed')
        return child

    def temperature():
        check_stopped()
        value=float(subprocess.check_output(['nvidia-smi','--query-gpu=temperature.gpu','--format=csv,noheader,nounits'],
            text=True,timeout=3).strip())
        require(math.isfinite(value) and value<78,'Thermal stop')
        check_stopped()
        report['gpu'].append(dict(clientNs=time.monotonic_ns(),temperatureC=value))

    bridge=None
    started=False
    child=check_owner()
    app=Path(child['appDirectory']).absolute()
    require(app==app.resolve(strict=True) and app.is_relative_to((repo/'artifacts').resolve())
        and app.name=='BetterGI-English-win-x64','Unexpected original child application directory')
    try:
        temperature()
        started=True
        child=lifecycle.start_agent(child,20,enable_input=False,observation_profile=P2P_NATIVE)
        bridge=Bridge(child['agentPipeName'])
        verify_bridge_identity(bridge.handle,child['processId'],child['windowsSessionId'])
        require(bridge.hello['inputEnabled'] is False,'Native input unexpectedly enabled')
        enabled,payload=bridge.request('enableNavigationGuidance',navigationProfile=args.navigation_profile)
        require(not payload and enabled.get('enabled') is True,'Scouting profile not enabled')
        validate_capability(enabled['capability'],args.navigation_profile)
        report['capability']=enabled['capability']
        report['nativeCombatObservation']=negotiate(bridge)
        if args.anchor is not None:
            report['nativeGroundControlObservation'],report['nativeGroundControlGate']=negotiate_ground(bridge)
        armed=False
        qualified={}
        deadline=time.monotonic()+30
        next_temperature=time.monotonic()+2
        samples=[]
        while time.monotonic()<deadline:
            check_stopped()
            if time.monotonic()>=next_temperature:temperature();next_temperature=time.monotonic()+2
            frame,_=bridge.request('frame')
            if frame.get('type')=='frame':
                report['observations'].append(frame)
                require(frame['executionContext']['lastSequence']==0,'Unexpected native input history')
                combat=validate_frame(frame,report['nativeCombatObservation'])
                ground=validate_ground_frame(frame) if args.anchor is not None else None
                require(ground is None or ground['reason']!='unsupported_geometry','Ground-control capture requires1920x1080')
                pose=frame.get('navigationPose') or {}
                world=frame.get('frameWorldReadiness') or {}
                motion=frame.get('motionEvidence') or {}
                valid=(pose.get('state')=='valid' and pose.get('frameId')==frame['frameId']
                    and allows_pose_scope(pose,args.navigation_profile) and .99<=pose['positionConfidence']<=1
                    and .2<=pose['yawConfidence']<=1 and world.get('ready') is True
                    and world.get('sourceFrameId')==frame['frameId'] and frame['worldReadiness']['ready'] is True
                    and motion.get('status')=='normal' and motion.get('spaceKeyMatched') is False
                    and 0<=frame.get('sourceFrameAgeMs',999)<=150 and combat and combat['state']=='valid'
                    and (args.anchor is None or ground and ground['state']=='valid' and ground['groundControlsConfirmed']))
                if valid and args.require_single_enemy:
                    valid=not combat['redMaskOverloaded'] and len(combat['enemyBarCandidates'])==1
                if valid:
                    if args.anchor is not None:
                        require(math.dist((pose['x'],pose['y']),args.anchor)<=2,'Current position differs from the expected endpoint')
                    qualified[frame['frameId']]=frame
                    if samples:
                        previous=samples[-1]
                        a,b=previous['sourceFrame'],frame['sourceFrame']
                        gap=b['freshnessAtMs']-a['freshnessAtMs']
                        if a['captureEpoch']!=b['captureEpoch'] or gap>250:samples=[]
                        elif gap<80 or b['timestamp100ns']<=a['timestamp100ns']:valid=False
                        elif (world['epoch']!=previous['frameWorldReadiness']['epoch']
                            or math.dist((pose['x'],pose['y']),(previous['navigationPose']['x'],previous['navigationPose']['y']))>.35
                            or yaw_error(pose['yawDegrees'],previous['navigationPose']['yawDegrees'])>3):samples=[]
                    if valid:samples=(samples+[frame])[-3:]
            status,_=bridge.request('status')
            report['diagnostics']=status['diagnostics']
            require(not report['diagnostics']['failed'] and not report['diagnostics']['dropped'],'Native evidence loss')
            if len(samples)==3 and not armed:
                # Arm only after localization, HUD and source freshness are stable.
                configured,payload=bridge.request('configureDiagnostics',recordReadinessTransitions=True)
                require(not payload and configured['diagnostics']['enabled'] is True,'Native diagnostics unavailable')
                report['diagnostics']=configured['diagnostics']
                report['snapshotArmedAfterFrameId']=samples[-1]['frameId']
                armed=True
            if armed and len(samples)==3 and report['diagnostics']['written'] and not report['diagnostics']['pending']:
                # Require the native PNG to have an exact qualified stream-observation join.
                native=Path(report['diagnostics']['directory']).resolve()
                require(native.is_relative_to(app),'Unexpected native diagnostic directory')
                for sidecar in sorted(native.glob('*.json')):
                    metadata=json.loads(sidecar.read_bytes())
                    observed=qualified.get(metadata.get('frameId'))
                    if (observed and observed['sourceFrame']==metadata.get('sourceFrame')
                            and metadata.get('worldReadiness',{}).get('ready') is True):
                        report.update(status='completed',stableSamples=samples,selectedImageName=sidecar.with_suffix('.png').name,
                            selectedImageSha256=metadata['imageSha256'],qualifiedImageFrameId=metadata['frameId'])
                        break
                if report['status']=='completed':break
            time.sleep(.015 if armed else .035)
        require(report['status']=='completed','No stationary native scene before the passive deadline')
    except BaseException as error:
        report.update(status='failed',error=str(error),traceback=traceback.format_exc())
        raise
    finally:
        try:
            if bridge is not None:bridge.handle.close()
        finally:
            try:
                if started:lifecycle.stop_agent(child,12)
            finally:
                try:
                    diagnostics=report.get('diagnostics') or {}
                    if diagnostics.get('directory'):
                        source=Path(diagnostics['directory']).resolve()
                        require(source.is_relative_to(app),'Unexpected native diagnostic directory')
                        if source.exists():
                            for path in source.iterdir():
                                if path.suffix in ('.png','.json'):shutil.copy2(path,output/path.name)
                    check_owner(supervising=False)
                    report['ownerIdleMinimizedAfter']=True
                finally:atomic_json(output/'result.json',report)
    print(json.dumps(dict(status=report['status'],inputEnabled=False,ownerIdleMinimizedAfter=True,
        nativeImages=[str(path) for path in output.glob('*.png')],selectedImageName=report.get('selectedImageName'),
        nativePose=report['stableSamples'][-1]['navigationPose'] if report.get('stableSamples') else None,
        peakGpuTemperatureC=max(row['temperatureC'] for row in report['gpu']))),flush=True)


def main():
    """Preserve the existing standalone command by immediately consuming its own preparation."""
    run_id=uuid.uuid4().hex
    token=prepare_capture(parse_args(),run_id=run_id)
    return run_capture(token,run_id=run_id)


if __name__=='__main__':main()
