"""Inspect one heading or a bounded vertical camera shift in the existing minimized RDP session."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import threading
import time

from hybrid_routes import camera_correction
from map_owner import load_map_owner
from navigation_profiles import SURFACE_PROFILE, SCOUT_PROFILES, NORTH_SCOUT_PROFILE, allows_pose_scope, validate_capability
from observation_profiles import P2P_NATIVE
from probe_camera_response import Experiment, MAX_PITCH_MOUSE_UNITS, require, stable
from resident_runtime import atomic_json, control_module, verify_bridge_identity
from run_patrol_series import SeriesGuard
from run_rdp_patrol import MAX_GPU_SAMPLE_AGE_SECONDS, ROOT, STOP_C, ready_session, sample_gpu
from stream_client import Bridge


def turn_to(trial, heading):
    """Re-measure every correction and finish only after three settled, independent source frames."""
    require(type(heading) in (int, float) and math.isfinite(heading) and 0 <= heading < 360,
            'Heading must be between zero and 360 degrees')
    sensitivity = None
    corrections = 0
    while corrections <= 12:
        frame = trial.next()
        delta = (heading - frame['navigationPose']['yawDegrees'] + 180) % 360 - 180
        if abs(delta) <= 3:
            settled = [frame]
            while settled[-1]['sourceAtMs'] - settled[0]['sourceAtMs'] < 200 or len(settled) < 3:
                settled.append(trial.next())
            if stable(settled) and all(abs((heading-r['navigationPose']['yawDegrees']+180)%360-180) <= 3
                                       for r in settled):
                trial.report['settledFrameIds'] = [r['frameId'] for r in settled]
                trial.report['finalYawDegrees'] = settled[-1]['navigationPose']['yawDegrees']
                return
        elif corrections == 12:
            break
        else:
            # Use the first measured response to avoid a long tail of tiny fixed-gain turns.
            # Every pulse remains bounded and must settle before another source-bound correction.
            dx = (camera_correction(frame['navigationPose']['yawDegrees'], heading) if sensitivity is None
                  else max(-250, min(250, round(.75*delta/sensitivity))))
            response = trial.pulse(dx)
            change = (response['afterYawDegrees']-response['beforeYawDegrees']+180)%360-180
            measured = change/dx
            require(.02 <= measured <= .5, 'Camera response was absent, reversed or outside the bounded survey range')
            if abs(change) >= 1:
                sensitivity = measured if sensitivity is None else (sensitivity+measured)/2
            response['degreesPerMouseUnit'] = measured
            trial.report.setdefault('cameraResponseUpdates', []).append(response)
            corrections += 1
    raise RuntimeError('Camera did not settle within twelve bounded corrections')


def tilt_once(trial, delta):
    """Clear a camera obstruction with one relative vertical pulse; retain that absolute pitch is unmeasured."""
    require(type(delta) is int and 0 < abs(delta) <= MAX_PITCH_MOUSE_UNITS,
            'Vertical camera shift must be a nonzero integer bounded to 80')
    response = trial.pulse(0, dy=delta)
    yaw_change = (response['afterYawDegrees'] - response['beforeYawDegrees'] + 180) % 360 - 180
    require(abs(yaw_change) <= 3, 'Vertical camera shift unexpectedly changed compass heading')
    trial.report.update(verticalPulseResult=response, pitchAngleMeasured=False,
                        finalYawDegrees=response['afterYawDegrees'],
                        settledFrameIds=trial.report['actions'][-1]['settledFrameIds'])


class SurveyGuard:
    """Latch the existing identity/operator limits and fresh NVIDIA telemetry without delaying frame reads."""
    def __init__(self, folder, owner, lifecycle, root, child, report):
        self.series = SeriesGuard(folder/'STOP', 35)
        self.series.required_identity = owner
        self.report, self.reason, self.last_sample = report, None, None
        self.executable = Path(shutil.which('nvidia-smi') or 'C:/Windows/System32/nvidia-smi.exe')
        self.sample()
        self.check()
        self.series.admit(lifecycle, root, child)
        self.thread = threading.Thread(target=self.watch, daemon=True)
        self.thread.start()

    def sample(self):
        """Retain each valid sample and latch query failures or the established 78 C limit."""
        try:
            row = sample_gpu(self.executable)
            row['monotonicNs'] = time.monotonic_ns()
            self.report['gpuSamples'].append(row)
            self.last_sample = time.monotonic()
            if row['temperatureC'] >= STOP_C:
                self.reason = self.reason or 'temperatureLimit'
        except Exception as error:
            self.reason = self.reason or 'telemetryLost'
            self.report['telemetryError'] = str(error)

    def watch(self):
        """Keep telemetry sampling independent of source-frame and terminal-receipt intake."""
        while not self.series.finished.wait(.5):
            self.sample()
            if self.reason:
                return

    def check(self):
        """A stop stays latched even if the operator removes the file or a later sample recovers."""
        reason = self.series.stop_reason() or self.reason
        if self.last_sample is None or time.monotonic()-self.last_sample >= MAX_GPU_SAMPLE_AGE_SECONDS:
            self.reason = self.reason or 'telemetryLost'
            reason = reason or self.reason
        require(reason is None, reason or 'Camera survey stopped')

    def close(self):
        """Stop both monitors and retire the bounded telemetry query before sealing its evidence."""
        self.series.finished.set()
        self.thread.join(4)
        require(not self.thread.is_alive(), 'GPU telemetry worker did not retire')


def scene_anchor(scene, owner, profile=SURFACE_PROFILE):
    """Require an input-disabled native scene from the same sealed owner before live admission."""
    result = json.loads((scene/'result.json').read_bytes())
    plan = json.loads((scene/'plan.json').read_bytes())
    require(result.get('status') == 'completed' and result.get('inputEnabled') is False
            and result.get('ownerIdleMinimizedAfter') is True
            and plan.get('owner') == owner,
            'Expected a completed native scene from the original idle owner')
    # Northern camera admission must retain its explicit scene scope and exact native contract.
    if profile == NORTH_SCOUT_PROFILE:
        require(plan.get('navigationProfile') == profile, 'Northern scene profile differs')
        validate_capability(result.get('capability') or {}, profile)
    poses = [r['navigationPose'] for r in result['observations'] if (r.get('navigationPose') or {}).get('state') == 'valid']
    require(profile in (SURFACE_PROFILE,*SCOUT_PROFILES) and bool(poses) and allows_pose_scope(poses[-1], profile),
            'Scene lacks a scoped native position')
    return poses[-1]['x'], poses[-1]['y']


def run(args, folder, report):
    """Use one authenticated camera-only lease and an unconditional stop on its original owner."""
    owner = load_map_owner(args.owner_lineage)
    profile = getattr(args,'navigation_profile',SURFACE_PROFILE)
    anchor = scene_anchor(args.anchor_scene, owner, profile)
    lifecycle = control_module()
    root, child = ready_session(lifecycle)
    pitch_delta = getattr(args, 'pitch_delta', None)
    report.update(owner=owner, anchorPosition=anchor, requestedHeading=args.heading, requestedPitchDelta=pitch_delta,
                  sceneResultSha256=hashlib.sha256((args.anchor_scene/'result.json').read_bytes()).hexdigest())
    guard = SurveyGuard(folder, owner, lifecycle, root, child, report)
    listener = bridge = trial = None
    authenticated = start_attempted = False
    try:
        guard.check()
        start_attempted = True
        listener = lifecycle.start_agent(child, 20, enable_input=True, observation_profile=P2P_NATIVE)
        require(all(listener.get(k) == child[k] for k in ('processId', 'instanceNonce', 'windowsSessionId')),
                'Child changed while starting the camera lease')
        bridge = Bridge(listener['agentPipeName'])
        verify_bridge_identity(bridge.handle, child['processId'], child['windowsSessionId'])
        authenticated = True
        hello = bridge.hello
        report['hello'] = hello
        require(hello.get('inputEnabled') is True and hello.get('supportsStartBeforeMs') is True
                and hello.get('supportsRelease') is True, 'Camera timing capabilities are missing')
        config, payload = bridge.request('enableNavigationGuidance', navigationProfile=profile)
        require(config.get('enabled') is True and not payload, 'Surface guidance was not enabled')
        validate_capability(config['capability'], profile)
        trial = Experiment(bridge, report, station=anchor, profile=profile, seconds=35, stop_check=guard.check)
        trial.collect(config)
        if pitch_delta is None:
            turn_to(trial, args.heading)
        else:
            tilt_once(trial, pitch_delta)
        guard.check()
    finally:
        try:
            if authenticated:
                reply, payload = bridge.request('stop')
                report['stop'] = reply
                require(not payload and reply.get('type') == 'stopped', 'Missing camera stop acknowledgement')
                if trial:
                    trial.collect(reply)
        finally:
            try:
                if bridge:
                    bridge.handle.close()
            finally:
                try:
                    if start_attempted:
                        lifecycle.stop_agent(child, 12)
                finally:
                    guard.close()
    final_root, final_child = ready_session(lifecycle)
    actual = {role: {key: state[key] for key in ('processId', 'instanceNonce', 'windowsSessionId')}
              for role, state in (('root', final_root), ('child', final_child))}
    require(actual == owner, 'Owner changed after the camera survey')
    report['ownerIdleMinimizedAfter'] = True


def main():
    """Reserve local evidence exclusively and never retry or restart an unresolved camera survey."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner-lineage', type=Path, required=True)
    parser.add_argument('--anchor-scene', type=Path, required=True)
    direction = parser.add_mutually_exclusive_group(required=True)
    direction.add_argument('--heading', type=float)
    direction.add_argument('--pitch-delta', type=int,
                           help='One relative vertical mouse shift in [-80, 80], excluding zero; no pitch angle is inferred')
    parser.add_argument('--navigation-profile', choices=(SURFACE_PROFILE,*SCOUT_PROFILES),default=SURFACE_PROFILE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    live = (ROOT/'artifacts/live').resolve()
    for name in ('owner_lineage', 'anchor_scene', 'output'):
        path = getattr(args, name).resolve()
        if not path.is_relative_to(live):
            parser.error('Owner, native scene and evidence paths must be inside this workspace artifacts/live')
        setattr(args, name, path)
    if args.heading is not None and (not math.isfinite(args.heading) or not 0 <= args.heading < 360):
        parser.error('Use a finite compass heading in [0, 360).')
    if args.pitch_delta is not None and not 0 < abs(args.pitch_delta) <= MAX_PITCH_MOUSE_UNITS:
        parser.error('Use a nonzero integer vertical shift bounded to 80.')
    folder = args.output
    folder.mkdir(parents=True, exist_ok=False)
    archive = folder/'source-snapshot'
    archive.mkdir()
    sources = {}
    for source in Path(__file__).parent.glob('*.py'):
        raw = source.read_bytes()
        (archive/source.name).write_bytes(raw)
        sources[source.name] = hashlib.sha256(raw).hexdigest()
    kind = 'surface-camera-survey-v1' if args.pitch_delta is None else 'surface-camera-pitch-survey-v1'
    report = dict(status='running', kind=kind, observations=[], actions=[], receipts=[],
                  gpuSamples=[], sourceFiles=sources, movementAllowed=False, attacksAllowed=False,
                  physicalInputDeliveryVerified=False, split='diagnostic', fitPerformed=False,
                  stopTemperatureC=STOP_C, maximumSeconds=35, actionHoldMs=100, sourceFreshnessMs=150,
                  stopFile=str(folder/'STOP'), navigationProfile=args.navigation_profile)
    atomic_json(folder/'result.json', report)
    print(json.dumps(dict(evidenceDirectory=str(folder), stopFile=str(folder/'STOP'))), flush=True)
    try:
        run(args, folder, report)
        report['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as error:
        report['status'] = 'failed'
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        atomic_json(folder/'result.json', report)
    print(json.dumps(dict(status=report['status'], actions=len(report['actions']), finalYawDegrees=report.get('finalYawDegrees'),
                         ownerIdleMinimizedAfter=report.get('ownerIdleMinimizedAfter'), error=report.get('error'))))
    return int(report['status'] != 'completed')


if __name__ == '__main__':
    sys.exit(main())
