"""Retain one bounded, input-disabled native scene in an explicitly selected scout scope."""
import argparse,hashlib,json,math,shutil,subprocess,sys,time,traceback
from pathlib import Path

repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'tools/bettergi-agent'))
from run_rdp_patrol import ready_session,control_module
from map_owner import load_map_owner
from resident_runtime import verify_bridge_identity,atomic_json
from stream_client import Bridge
from observation_profiles import P2P_NATIVE
from navigation_profiles import SCOUT_PROFILE,SCOUT_PROFILES,validate_capability,allows_pose_scope
from native_combat import negotiate,validate_frame
from hybrid_navigation import yaw_error


def require(value,message):
    """A missing source or stopped observation is never silently retried."""
    if not value:raise RuntimeError(message)


def main():
    """Open one passive lease and preserve native evidence even when qualification fails."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--anchor',nargs=2,type=float,required=True)
    parser.add_argument('--owner-from',type=Path,required=True)
    parser.add_argument('--navigation-profile',choices=SCOUT_PROFILES,default=SCOUT_PROFILE)
    args=parser.parse_args()
    output=args.output.absolute()
    require(output==output.resolve() and output.is_relative_to((repo/'artifacts/live').resolve()),
        'Expected an unlinked local live-artifact destination')
    require(all(math.isfinite(value) for value in args.anchor),'Invalid expected endpoint')
    require(allows_pose_scope(dict(x=args.anchor[0],y=args.anchor[1],layerId='MapBack_2'),args.navigation_profile),
        'Expected endpoint is outside the selected scout scope')
    output.mkdir(parents=True,exist_ok=False)
    helper=Path(__file__).read_bytes()
    (output/'capture-helper.py').write_bytes(helper)
    owner=load_map_owner(args.owner_from)
    lifecycle=control_module()
    report=dict(status='failed',inputEnabled=False,modelLoaded=False,observations=[],stableSamples=[],gpu=[])
    atomic_json(output/'plan.json',dict(owner=owner,enableInput=False,modelLoaded=False,
        navigationProfile=args.navigation_profile,anchor=args.anchor,maximumObservationSeconds=30,
        sourceFreshnessMs=150,stopTemperatureC=78,captureHelperSha256=hashlib.sha256(helper).hexdigest(),
        modelLoadScope='this-capture-helper-only'))

    def check_owner():
        root,child=ready_session(lifecycle)
        actual={role:{key:state[key] for key in ('windowsSessionId','processId','instanceNonce')}
                for role,state in (('root',root),('child',child))}
        require(actual==owner,'Original minimized idle owner changed')
        return child

    def temperature():
        value=float(subprocess.check_output(['nvidia-smi','--query-gpu=temperature.gpu','--format=csv,noheader,nounits'],
            text=True,timeout=3).strip())
        require(math.isfinite(value) and value<78,'Thermal stop')
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
        armed=False
        qualified={}
        deadline=time.monotonic()+30
        next_temperature=time.monotonic()+2
        samples=[]
        while time.monotonic()<deadline:
            require(not (output/'STOP').exists() and not (output.parent/'STOP').exists(),'Operator stop')
            if time.monotonic()>=next_temperature:temperature();next_temperature=time.monotonic()+2
            frame,_=bridge.request('frame')
            if frame.get('type')=='frame':
                report['observations'].append(frame)
                require(frame['executionContext']['lastSequence']==0,'Unexpected native input history')
                combat=validate_frame(frame)
                pose=frame.get('navigationPose') or {}
                world=frame.get('frameWorldReadiness') or {}
                motion=frame.get('motionEvidence') or {}
                valid=(pose.get('state')=='valid' and pose.get('frameId')==frame['frameId']
                    and allows_pose_scope(pose,args.navigation_profile) and .99<=pose['positionConfidence']<=1
                    and .2<=pose['yawConfidence']<=1 and world.get('ready') is True
                    and world.get('sourceFrameId')==frame['frameId'] and frame['worldReadiness']['ready'] is True
                    and motion.get('status')=='normal' and motion.get('spaceKeyMatched') is False
                    and 0<=frame.get('sourceFrameAgeMs',999)<=150 and combat and combat['state']=='valid')
                if valid:
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
                    check_owner()
                    report['ownerIdleMinimizedAfter']=True
                finally:atomic_json(output/'result.json',report)
    print(json.dumps(dict(status=report['status'],inputEnabled=False,ownerIdleMinimizedAfter=True,
        nativeImages=[str(path) for path in output.glob('*.png')],selectedImageName=report.get('selectedImageName'),
        nativePose=report['stableSamples'][-1]['navigationPose'] if report.get('stableSamples') else None,
        peakGpuTemperatureC=max(row['temperatureC'] for row in report['gpu']))),flush=True)


if __name__=='__main__':main()
