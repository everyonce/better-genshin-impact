"""Run a bounded, temperature-monitored Mondstadt patrol in an existing minimized BetterGI RDP window."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
import json
import math
import os
from queue import Empty, SimpleQueue
from pathlib import Path
import re
import shutil
import subprocess
import sys
from threading import Event
import time
import uuid

from hybrid_routes import PATROL_STATIONS, STREET_PATROL_ROUTE, itinerary_legs
from resident_runtime import atomic_json, control_module, read_control_document, select_child


ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / 'artifacts' / 'agent'
STOP_C = 78
POLL_SECONDS = 2
CONTROL_POLL_SECONDS = .05
GPU_QUERY_TIMEOUT_SECONDS = 3
MAX_GPU_SAMPLE_AGE_SECONDS = POLL_SECONDS + GPU_QUERY_TIMEOUT_SECONDS + 1


def options(argv=None, parser=None, *, warm=False):
    """All model assets and executables must already be installed on this host."""
    p = parser if parser is not None else argparse.ArgumentParser(description=__doc__)
    if not warm:
        p.add_argument('--circuits', type=int, default=1, help='Number of A-B-C-B-A circuits (1 to 32)')
    p.add_argument('--seconds', type=int, default=180, help='Wall time limit including model loading (15 to 600)')
    p.add_argument('--evidence-root', type=Path, default=ROOT/'artifacts/live/patrol')
    p.add_argument('--gpu-python', type=Path, default=AGENT/'envs/gamescaling/Scripts/python.exe')
    p.add_argument('--runner-python', type=Path, default=Path(sys.executable))
    p.add_argument('--source', type=Path, default=AGENT/'sources/open-p2p')
    p.add_argument('--checkpoint', type=Path, default=AGENT/'models/open-p2p-150M/150M/checkpoint-step=00500000.ckpt')
    p.add_argument('--goal-embedding', type=Path, default=AGENT/'goals/ground-street-walk.json')
    p.add_argument('--ffmpeg', type=Path, default=Path(shutil.which('ffmpeg') or 'C:/programs/ffmpeg.exe'))
    p.add_argument('--nvidia-smi', type=Path, default=Path(shutil.which('nvidia-smi') or
                   Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/nvidia-smi.exe'))
    p.add_argument('--steering-shadow', type=Path, help='Observe and audit predictions from this steering checkpoint')
    p.add_argument('--landmark-shadow', type=Path, help='Observe station predictions and audit recorded frames against them')
    if not warm:
        p.add_argument('--retain-station-rgb',action='store_true',
                       help='Record one lossless RGB source for every settled station in the fixed patrol')
    if warm:
        p.set_defaults(photo_station=[])
    else:
        p.add_argument('--photo-station', choices=PATROL_STATIONS, action='append', default=[],
                       help='Collect a verified photo at this station during the patrol')
    p.add_argument('--photo-qualification', type=Path, help='Sealed qualification for the photo observer')
    p.add_argument('--camera-calibration', type=Path, help='Use and independently audit this local camera checkpoint')
    args = p.parse_args(argv)
    if getattr(args,'retain_station_rgb',False) and (not args.landmark_shadow or args.photo_station):
        p.error('--retain-station-rgb requires --landmark-shadow without photo objectives')
    if (warm or args.photo_station or args.photo_qualification) and not (
            (warm or args.photo_station) and args.photo_qualification and args.landmark_shadow):
        p.error('Photo stations require both --landmark-shadow and --photo-qualification')
    if not (15 <= args.seconds <= 600 and (warm or 1 <= args.circuits <= 32)):
        p.error('Set --circuits between 1 and 32 and --seconds between 15 and 600.')
    return args


def ready_session(lifecycle):
    """Choose exactly one authenticated primary connected to a minimized, idle game session."""
    discovery = lifecycle.discover()
    if discovery['unavailable']:
        raise RuntimeError('Incomplete BetterGI discovery. No patrol was started.')
    items = discovery['instances']
    roots = [s for s in items if s.get('instanceType') == 'Primary' and s.get('childConnectedState') == 1]
    if len(roots) != 1:
        raise RuntimeError('Expected exactly one connected BetterGI primary.')
    root = roots[0]
    lifecycle.require_role(root, 'Primary')
    if root.get('uiStatus') != 'current' or root.get('childWindowMinimized') is not True:
        raise RuntimeError('Minimize the existing BetterGI Virtual Desktop window before starting a patrol.')
    child = select_child(items, root.get('childSessionId'))
    if not child:
        raise RuntimeError('The attached RDP session has no enabled BetterGI child.')
    lifecycle.require_role(child, 'ChildSession')
    lifecycle._require_connected_root(root, child)
    if (child.get('rootProcessId') not in (None, root['processId']) or child.get('uiStatus') != 'current'
            or child.get('automationState') != 'game_ready' or child.get('runtimeRunning') is not True
            or child.get('taskRunning') is not False or child.get('agentStreamRunning') is not False):
        raise RuntimeError('The RDP child must have a ready game and no active task or agent stream.')
    return root, child


def patrol_argv(args, session, folder):
    """Use the same resident, observation profile and input owner as the audited street patrol."""
    command = [str(args.gpu_python.resolve()), '-B', '-X', 'utf8', str(Path(__file__).with_name('stream_client.py').resolve()),
               '--model=open-p2p', '--source', str(args.source.resolve()), '--checkpoint', str(args.checkpoint.resolve()),
               '--history=41', '--cuda-graph', '--p2p-fast-start', '--p2p-prewarm',
               '--goal-embedding', str(args.goal_embedding.resolve()), '--goal-intent=ground-navigation',
               '--hybrid-navigation', '--navigation-climb-recovery', '--hybrid-route', STREET_PATROL_ROUTE,
               '--hybrid-legs', str(getattr(args, 'destination_legs', args.circuits*4)), '--fps=20', '--decision-hz=10',
               '--max-observation-age-ms=150', '--action-hold-ms=100', '--enable-input', '--resident',
               '--rdp-session-id', str(session), '--observation-profile=p2p-native-hamming-192-v1',
               '--seconds', str(args.seconds), '--segment-seconds', str(min(30, args.seconds)),
               '--preview', '--record-max-mib=160', '--record-dir', str(folder/'patrol-recording'),
               '--ffmpeg', str(args.ffmpeg.resolve()), '--output', str(folder/'patrol.json')]
    if args.steering_shadow:
        command.append('--steering-shadow=' + str(args.steering_shadow.resolve()))
    if args.landmark_shadow:
        command.append('--landmark-shadow=' + str(args.landmark_shadow.resolve()))
    if getattr(args,'retain_station_rgb',False):
        command.append('--retain-station-rgb')
    if args.photo_station:
        command.extend(['--photo-directory', str(folder/'station-photos'),
                        '--photo-qualification', str(args.photo_qualification.resolve())])
        for station in args.photo_station:
            command.extend(['--photo-station', station])
    if getattr(args, 'warm_photo_plan', None):
        command.extend(['--warm-photo-plan=' + str(args.warm_photo_plan),
                        '--photo-directory=' + str(folder/'station-photos'),
                        '--photo-qualification=' + str(args.photo_qualification.resolve())])
        if getattr(args, 'inspect_junction_map', False):
            command.append('--inspect-junction-map')
        if getattr(args, 'recover_junction_map', False):
            command.append('--recover-junction-map')
        if getattr(args, 'batches', None):
            command.append('--warm-batch-count=' + str(args.batches))
            if getattr(args,'open_queue',False):
                command.append('--warm-open-queue')
    if args.camera_calibration:
        command.append('--camera-calibration=' + str(args.camera_calibration.resolve()))
    return command


def sample_gpu(executable):
    """Sample the local first NVIDIA GPU without opening a console or invoking a shell."""
    result = subprocess.run([str(executable), '--id=0', '--query-gpu=temperature.gpu,utilization.gpu,memory.used,power.draw',
                             '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=GPU_QUERY_TIMEOUT_SECONDS, check=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    temp, utilization, memory, power = map(float, result.stdout.strip().split(','))
    if not (0 < temp <= 130 and 0 <= utilization <= 100 and memory >= 0 and power >= 0
            and all(map(math.isfinite, (temp, utilization, memory, power)))):
        raise ValueError('Invalid NVIDIA telemetry')
    return dict(temperatureC=temp, utilizationPct=utilization, memoryMiB=memory, powerW=power)


def log_sample(folder, executable):
    """Persist each sample or sampling failure before the next control decision."""
    sample = {'atUtc': datetime.now(timezone.utc).isoformat()}
    try:
        sample.update(sample_gpu(executable))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        sample['error'] = str(exc)
    with (folder/'gpu.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(sample) + '\n')
    return sample


def addressed_control(path, run_id):
    """Validate the bound document, retrying only Windows sharing errors returned by the resident reader."""
    for attempt in range(5):
        doc, error = read_control_document(path, run_id)
        if not error:
            return doc
        # The shared reader returns a diagnostic string for both OS and schema
        # errors. Only these specific OS error codes authorize another read.
        if attempt == 4 or not error.startswith(('[Errno 13]', '[WinError 5]', '[WinError 32]', '[WinError 33]')):
            raise ValueError(error)
        time.sleep(.025)


def pin_resident(folder, run_id=None):
    """Pin the status UUID once; thereafter validate only the private addressed control file."""
    if run_id is None:
        status_path = folder/'patrol.json.status.json'
        # The resident replaces its status many times a second. A Windows sharing
        # violation can briefly deny the initial open; content errors are final.
        for attempt in range(5):
            try:
                status = json.loads(status_path.read_text(encoding='utf-8-sig'))
                break
            except FileNotFoundError:
                return None
            except PermissionError as exc:
                if attempt == 4 or (exc.errno != 13 and getattr(exc, 'winerror', None) not in (5, 32, 33)):
                    raise
                time.sleep(.025)
        if not isinstance(status, dict) or status.get('version') != 1:
            raise ValueError('Invalid resident status document')
        run_id = status.get('runId')
        if not isinstance(run_id, str) or not re.fullmatch('[0-9a-f]{32}', run_id):
            raise ValueError('Invalid resident identity')
    addressed_control(folder/'patrol.json.control.json', run_id)
    return run_id


def native_qpc_sample():
    """Read Windows QPC ticks and frequency; timing is optional for delivering a stop."""
    if os.name != 'nt':
        return None
    import ctypes
    try:
        kernel = ctypes.WinDLL('kernel32')
        frequency, ticks = ctypes.c_int64(), ctypes.c_int64()
        if (kernel.QueryPerformanceFrequency(ctypes.byref(frequency)) and frequency.value > 0
                and kernel.QueryPerformanceCounter(ctypes.byref(ticks))):
            return frequency.value, ticks.value
    except (AttributeError, OSError):
        pass
    return None


def stop_resident(folder, run_id, *, timing=None):
    """Address only this run's private control file and preserve its existing fields."""
    path = folder/'patrol.json.control.json'
    doc = addressed_control(path, run_id)
    if doc['command'] != 'stop':
        before = native_qpc_sample() if timing is not None else None
        atomic_json(path, {**doc, 'command': 'stop'})
        if before is not None:
            after = native_qpc_sample()
            if after is not None and after[0] == before[0] and after[1] >= before[1]:
                timing['addressedStopQpc'] = dict(clock='windows-query-performance-counter',
                    frequencyHz=before[0], beforeTicks=before[1], afterTicks=after[1])
        return True
    return False


def monitor_temperature(folder, executable, finished, completed_samples):
    """Keep the existing GPU cadence while allowing a stop to be delivered during a slow NVIDIA query."""
    while not finished.is_set():
        try:
            sample = log_sample(folder, executable)
        except OSError as exc:
            return 'telemetryLost', str(exc)
        if 'error' in sample:
            return 'telemetryLost', sample['error']
        if sample['temperatureC'] >= STOP_C:
            return 'temperatureLimit', None
        completed_samples.put(time.monotonic())
        finished.wait(POLL_SECONDS)
    return None, None


def supervise_control(future, thermal, completed_samples, folder, deadline, state, series):
    """Quickly deliver latched stops to the original resident, even while its GPU sample is pending."""
    next_control_check = 0
    last_sample = time.monotonic()
    while not future.done():
        try:
            now = time.monotonic()
            try:
                while True:
                    last_sample = completed_samples.get_nowait()
            except Empty:
                pass
            if thermal.done():
                state['stopReason'] = state['stopReason'] or thermal.result()[0]
            if now - last_sample >= MAX_GPU_SAMPLE_AGE_SECONDS:
                state['stopReason'] = state['stopReason'] or 'telemetryLost'
            if now >= deadline:
                state['stopReason'] = state['stopReason'] or 'wallTimeLimit'
            if series is not None and not state['stopReason']:
                state['stopReason'] = series.stop_reason()
            try:
                # After a failed initial identity check, a later occupant of these
                # paths must never inherit the first job's stop authority.
                if (not state['runId'] or state['stopReason'] or now >= next_control_check) and (
                        state['runId'] or 'controlError' not in state):
                    state['runId'] = pin_resident(folder, state['runId'])
                    next_control_check = now + POLL_SECONDS
                if state['runId'] and state['stopReason'] and not state['stopRequested']:
                    # Capture the actual write even when the marker producer has not finished its observation record.
                    state['stopCommandPublished'] = stop_resident(folder, state['runId'], timing=state)
                    state['stopRequested'] = True
                    state['stopRequestedAtMonotonicNs'] = time.monotonic_ns()
            except (OSError, ValueError, KeyError) as exc:
                state.update(stopReason=state['stopReason'] or 'invalidResidentControl', controlError=str(exc))
            wait((future,), timeout=CONTROL_POLL_SECONDS)
        except KeyboardInterrupt:
            state['stopReason'] = state['stopReason'] or 'interrupted'


def supervise(future, folder, executable, deadline, state, series=None):
    """Join the last thermal sample before a completed job can earn route credit."""
    finished = Event()
    completed_samples = SimpleQueue()
    with ThreadPoolExecutor(max_workers=1) as pool:
        thermal = pool.submit(monitor_temperature, folder, executable, finished, completed_samples)
        try:
            supervise_control(future, thermal, completed_samples, folder, deadline, state, series)
        finally:
            finished.set()
        reason, error = thermal.result()
        state['stopReason'] = state['stopReason'] or reason
        if error:
            state['telemetryError'] = error


def run(args, folder, *, series=None):
    """Dispatch a single bounded child job and retain the broker, GPU and independently audited route evidence."""
    for resource in (args.gpu_python, args.runner_python, args.ffmpeg, args.nvidia_smi, args.goal_embedding,
                     args.checkpoint, args.steering_shadow, args.landmark_shadow, args.camera_calibration):
        if resource is not None and not resource.is_file():
            raise RuntimeError(f'Missing local file: {resource}')
    if not args.source.is_dir():
        raise RuntimeError(f'Missing local model source: {args.source}')
    lifecycle = control_module()
    root, child = ready_session(lifecycle)
    session = child['windowsSessionId']
    state = dict(windowsSessionId=session, rootPid=root['processId'], childPid=child['processId'],
                 circuits=args.circuits, wallTimeLimitSeconds=args.seconds, stopAtC=STOP_C,
                 runId=None, stopReason=None, stopRequested=False, verified=False)
    try:
        if series is not None:
            series.admit(lifecycle, root, child)
        sample = log_sample(folder, args.nvidia_smi)
        if 'error' in sample or sample['temperatureC'] >= STOP_C:
            state['stopReason'] = 'telemetryLost' if 'error' in sample else 'temperatureLimit'
            raise RuntimeError('GPU startup check refused this patrol. See gpu.jsonl.')
        command = patrol_argv(args, session, folder)
        deadline = time.monotonic() + args.seconds
        broker_timeout = args.seconds + 30
        if series is not None:
            state['stopReason'] = series.stop_reason()
            if state['stopReason']:
                raise RuntimeError(state['stopReason'])
            deadline = min(deadline, series.deadline_ns/1e9)
            broker_timeout = min(broker_timeout, max(1, math.ceil(series.deadline_ns/1e9 - time.monotonic())))
            command.append('--patrol-series-binding=' + series.binding())
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lifecycle.run_command, root, command, str(ROOT), str(args.runner_python.resolve()),
                                 broker_timeout, str(folder/'jobs'), 65536)
            supervise(future, folder, args.nvidia_smi, deadline, state, series)
            result = future.result()
        atomic_json(folder/'broker.json', result)
        if state['runId'] or 'controlError' not in state:
            state['runId'] = pin_resident(folder, state['runId'])
        if state['stopReason'] or not result.get('success') or result.get('returnCode') != 0 or result.get('timedOut'):
            raise RuntimeError('Patrol stopped or broker failed. Inspect launcher.json and broker.json.')
        output = folder/'patrol.json'
        report = json.loads(output.read_text(encoding='utf-8-sig'))
        expected_end = 'destinationQueueFinished' if getattr(args,'open_queue',False) else 'hybridLegLimit'
        if not state['runId'] or report.get('runId') != state['runId'] or report.get('endReason') != expected_end:
            raise RuntimeError('The addressed resident did not finish the requested legs.')
        from audit_hybrid_run import audit
        checkpoints = {}
        if args.camera_calibration:
            checkpoints.update(camera_checkpoint=args.camera_calibration.resolve(), minimum_calibrated_actions=1)
        if args.steering_shadow:
            checkpoints['shadow_checkpoint'] = args.steering_shadow.resolve()
        if args.landmark_shadow:
            checkpoints.update(landmark_checkpoint=args.landmark_shadow.resolve(), ffmpeg=str(args.ffmpeg.resolve()))
        if getattr(args, 'destination_legs', None):
            checkpoints['destination_plan'] = args.plan
        minimum_legs = getattr(args, 'destination_legs', 4*args.circuits)
        if getattr(args, 'warm_photo_plan', None) and getattr(args, 'batches', None):
            from destination_batch_sender import admitted_plans
            plans = admitted_plans(folder)
            if (not 1<=len(plans)<=args.batches or not getattr(args,'open_queue',False) and len(plans)!=args.batches):
                raise RuntimeError('The resident ended before every external batch was published')
            checkpoints['destination_batches'] = plans
            minimum_legs = sum(len(itinerary_legs(p['start'],[r['destination'] for r in p['requests']])) for p in plans)
        evidence = audit(output, folder/'patrol-recording', repository=ROOT, minimum_legs=minimum_legs,
                         minimum_circuits=args.circuits, **checkpoints)
        atomic_json(folder/'audit.json', evidence)
        if getattr(args,'retain_station_rgb',False):
            from landmark_shadow_sources import verify_archive
            originals = verify_archive(output,folder/'patrol-recording',args.landmark_shadow,evidence,ROOT)
            atomic_json(folder/'station-rgb-audit.json', originals)
        if args.photo_station:
            from patrol_photo_survey import verify_photo_survey
            survey = verify_photo_survey(folder/'station-photos', output, folder/'patrol-recording',
                                         repository=ROOT, landmark_checkpoint=args.landmark_shadow.resolve(),
                                         authenticated_report=evidence)
            atomic_json(folder/'photo-audit.json', survey)
            if not survey.get('complete') or set(survey['targets']) != set(args.photo_station):
                raise RuntimeError('The named photo objective is incomplete. See photo-audit.json.')
        state['verified'] = True
    finally:
        atomic_json(folder/'launcher.json', state)


def main():
    """Give each attempt a fresh directory, including refused and incomplete attempts."""
    args = options()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder = args.evidence_root.resolve() / f'{stamp}-{uuid.uuid4().hex[:12]}'
    folder.mkdir(parents=True, exist_ok=False)
    print(f'Patrol evidence: {folder}', flush=True)
    try:
        run(args, folder)
    except Exception as exc:
        atomic_json(folder/'error.json', {'error': str(exc)})
        print(str(exc), file=sys.stderr)
        return 1
    print(f'Verified {args.circuits} circuit(s).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
