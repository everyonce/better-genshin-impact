"""Prepare and consume one reviewed, five-second combat experiment in ordinary RDP.

Preparation never creates a review or contacts the game. ``launch --plan PLAN``
consumes that immutable plan once; its worker loads once and calls run_episode
once. A failed or unknown start is never reconciled by another connection.
"""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from types import SimpleNamespace
import uuid

import resident_runtime as runtime
import run_rdp_patrol as patrol
import stream_client as client
from combat_trial_guard import bind_review, canonical, proposal_rejection, trial_policy
from episode_split import reserve_split, read_split
from map_owner import load_map_owner
from policy_rgb_archive import RGB192_BYTES
from scout_session import SessionWatch, owner_pair, idle_child


ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / 'artifacts/live'
AGENT = ROOT / 'artifacts/agent'
GOAL = AGENT / 'goals/combat-isolated-enemy-v1.json'
GOAL_SHA256 = '94974028715b13dd368bd6f29f20cdcbd017127e66093894ac749e65cfc4d8b9'
CHECKPOINT = AGENT / 'models/open-p2p-150M/150M/checkpoint-step=00500000.ckpt'
MODEL_SOURCE = AGENT / 'sources/open-p2p'
GPU_PYTHON = AGENT / 'envs/gamescaling/Scripts/python.exe'
HOST_SECONDS = 90
MAX_REVIEW_AGE_SECONDS = 120
MAX_RECORD_BYTES = 160 * 1024 * 1024
EVIDENCE_NAMES = ('review', 'plan', 'scene', 'sidecar', 'image', 'goal')


def model_settings():
    """Expose the immutable measured model/controller settings in the reviewable plan."""
    return dict(model='open-p2p', historyFrames=41, precision='float16', cudaGraph=True,
        fastStart=True, prewarm=True, executionFeedback=True, executionContext='off',
        decisionHz=10, captureFps=20, holdMs=100, sourceAgeMs=150, seconds=5,
        maximumActions=3, inputKeys=['LBUTTON'], navigation=False, reconnect=False)


def require(condition, message):
    """Reject incomplete authority before allocating a policy or an input lease."""
    if not condition:
        raise ValueError(message)


def digest(raw):
    """Hash original bytes without JSON normalization."""
    return hashlib.sha256(raw).hexdigest()


def local_path(value, *, root=None, existing=True):
    """Refuse links, UNC paths and paths outside the explicitly selected local tree."""
    path = Path(value).absolute()
    resolved = path.resolve(strict=existing)
    require(not str(path).startswith(('\\\\', '//')) and path == resolved,
            'Expected an unlinked local path')
    if root is not None:
        require(resolved.is_relative_to(Path(root).resolve()), 'Path is outside the permitted artifact tree')
    return resolved


def read_bytes(path, maximum=16 * 1024 * 1024, *, allow_empty=False):
    """Bound one read; only source manifests may retain an empty Python package file."""
    path = local_path(path)
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    require((allow_empty or len(raw) > 0) and len(raw) <= maximum, 'Evidence exceeds its bounded size')
    return raw


def document(path, maximum=16 * 1024 * 1024):
    """Keep parsed objects and exact original file hashes together."""
    raw = read_bytes(path, maximum)
    value = json.loads(raw)
    require(isinstance(value, dict), 'Expected a JSON object')
    return value, digest(raw)


def exclusive_json(path, value):
    """Make a claim or immutable artifact once, without replacing prior evidence."""
    raw = json.dumps(value, indent=2, allow_nan=False).encode('utf-8')
    with Path(path).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return digest(raw)


def file_sha(path):
    """Stream the exact pinned checkpoint without retaining its multi-gigabyte payload."""
    with local_path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def file_stamp(path):
    """Detect replacement of a checkpoint already verified before loading."""
    stat = local_path(path).stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]


def source_paths():
    """Enumerate only Python code in the agent, its broker and installed model source."""
    paths = list((ROOT / 'tools/bettergi-agent').glob('*.py'))
    paths += list((ROOT / 'tools/rdp-automation').glob('*.py'))
    paths += list(MODEL_SOURCE.rglob('*.py'))
    return sorted(local_path(path, root=ROOT) for path in paths if '__pycache__' not in path.parts)


def snapshot_sources(folder):
    """Retain exact source bytes, including the worker entry point, before any launch."""
    result = {}
    for path in source_paths():
        relative = path.relative_to(ROOT).as_posix()
        raw = read_bytes(path, allow_empty=True)
        target = folder / 'source-snapshot' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(raw)
        result[relative] = digest(raw)
    require('tools/bettergi-agent/combat_trial.py' in result, 'Worker entry source is missing')
    return result


def verify_sources(folder, sources):
    """Require the current inventory and archived bytes to remain exactly the planned source."""
    require(isinstance(sources, dict) and set(sources) == {
        path.relative_to(ROOT).as_posix() for path in source_paths()}, 'Source inventory changed')
    for name, expected in sources.items():
        current = local_path(ROOT / name, root=ROOT)
        archived = local_path(folder / 'source-snapshot' / name, root=folder)
        require(digest(read_bytes(current, allow_empty=True)) == expected
                == digest(read_bytes(archived, allow_empty=True)), 'Source bytes changed: ' + name)


def recent_review(binding, review, maximum, *, now_ns=None, qpc_ns=None):
    """Check both human review time and the original compositor capture, not file modification time."""
    now_ns = time.time_ns() if now_ns is None else now_ns
    qpc_ns = time.perf_counter_ns() if qpc_ns is None else qpc_ns
    require(type(maximum) is int and 1 <= maximum <= MAX_REVIEW_AGE_SECONDS, 'Invalid review age bound')
    reviewed = review.get('reviewedAtUnixNs')
    captured = binding['reviewedFrame']['sourceFrame']['timestamp100ns']
    require(type(reviewed) is int and 0 <= now_ns - reviewed <= maximum * 1_000_000_000,
            'Combat review is stale or future-dated')
    require(type(captured) is int and captured > 0 and 0 <= qpc_ns - captured * 100 <= maximum * 1_000_000_000,
            'Native reviewed scene is stale or future-dated')


def installed_resources():
    """Use existing runtimes only; this launcher never installs packages or changes elevation."""
    return dict(gpuPython=str(GPU_PYTHON.resolve()), runnerPython=str(Path(sys.executable).resolve()),
        ffmpeg=str(Path(shutil.which('ffmpeg') or 'C:/programs/ffmpeg.exe').resolve()),
        nvidiaSmi=str(Path(shutil.which('nvidia-smi') or 'C:/Windows/System32/nvidia-smi.exe').resolve()),
        checkpoint=str(CHECKPOINT.resolve()), modelSource=str(MODEL_SOURCE.resolve()), goal=str(GOAL.resolve()))


def prepare(folder, owner_file, evidence, *, maximum_review_age=MAX_REVIEW_AGE_SECONDS):
    """Freeze a separately authored visual review, its originals and the installed source."""
    folder = local_path(folder, root=LIVE, existing=False)
    require(not folder.exists(), 'A combat plan requires a fresh directory')
    owner_file = local_path(owner_file, root=LIVE)
    owner = load_map_owner(owner_file)
    require(set(evidence) == set(EVIDENCE_NAMES) - {'goal'}, 'Specify all five original review/native files')
    paths = {name: local_path(path, root=LIVE) for name, path in evidence.items()}
    paths['goal'] = local_path(GOAL, root=ROOT)
    blobs = {name: read_bytes(path) for name, path in paths.items()}
    require(digest(blobs['goal']) == GOAL_SHA256, 'The installed fixed combat goal differs')
    binding = bind_review(*(blobs[name] for name in EVIDENCE_NAMES))
    require(binding['owner'] == owner, 'Review differs from the original sealed owner')
    recent_review(binding, json.loads(blobs['review']), maximum_review_age)
    resources = installed_resources()
    for name, value in resources.items():
        path = local_path(value)
        require(path.is_dir() if name == 'modelSource' else path.is_file(), 'Missing installed resource: ' + name)
    require(file_sha(CHECKPOINT) == runtime.OPEN_P2P_SHA256, 'Installed Open P2P checkpoint differs')
    folder.mkdir(parents=True, exist_ok=False)
    retained = folder / 'review-evidence'
    retained.mkdir()
    records = {}
    for name, raw in blobs.items():
        target = retained / (name + ('.png' if name == 'image' else '.json'))
        with target.open('xb') as stream:
            stream.write(raw)
        records[name] = dict(path=str(paths[name]), retained=str(target), sha256=digest(raw))
    plan = dict(version=1, kind='combat-trial-plan-v1', runId=uuid.uuid4().hex, directory=str(folder),
        createdAtUnixNs=time.time_ns(), owner=owner, ownerFile=str(owner_file), ownerSha256=digest(read_bytes(owner_file)),
        maximumReviewAgeSeconds=maximum_review_age, maximumHostSeconds=HOST_SECONDS,
        recordingMaximumBytes=MAX_RECORD_BYTES, policy=trial_policy(), modelConfiguration=model_settings(), binding=binding,
        evidence=records, resources=resources, checkpointSha256=runtime.OPEN_P2P_SHA256,
        checkpointStamp=file_stamp(CHECKPOINT), sourceFiles=snapshot_sources(folder))
    verify_sources(folder, plan['sourceFiles'])
    exclusive_json(folder / 'plan.json', plan)
    return plan


def load_plan(path):
    """Read only a fresh-plan namespace with the fixed finite trial bounds."""
    path = local_path(path, root=LIVE)
    plan, sha = document(path, 2 * 1024 * 1024)
    require(path.name == 'plan.json' and plan.get('directory') == str(path.parent)
        and plan.get('version') == 1 and plan.get('kind') == 'combat-trial-plan-v1'
        and isinstance(plan.get('runId'), str) and re.fullmatch('[0-9a-f]{32}', plan['runId'])
        and plan.get('maximumHostSeconds') == HOST_SECONDS and plan.get('recordingMaximumBytes') == MAX_RECORD_BYTES
        and canonical(plan.get('policy')) == canonical(trial_policy())
        and canonical(plan.get('modelConfiguration')) == canonical(model_settings()), 'Invalid fixed combat plan')
    return plan, sha


def verify_plan(plan, folder):
    """Reopen original and retained evidence before loading and again before the only lease."""
    require(plan['owner'] == load_map_owner(plan['ownerFile'])
        and digest(read_bytes(plan['ownerFile'])) == plan['ownerSha256'], 'Original owner evidence changed')
    resources = plan['resources']
    expected = dict(gpuPython=GPU_PYTHON, checkpoint=CHECKPOINT, modelSource=MODEL_SOURCE, goal=GOAL)
    require(all(resources.get(key) == str(path.resolve()) for key, path in expected.items()), 'Installed model/runtime paths changed')
    require(plan['checkpointSha256'] == runtime.OPEN_P2P_SHA256
        and file_stamp(CHECKPOINT) == plan['checkpointStamp'], 'Installed checkpoint changed')
    require(set(plan['evidence']) == set(EVIDENCE_NAMES), 'Incomplete original evidence')
    blobs = {}
    for name, item in plan['evidence'].items():
        original = local_path(item['path'], root=ROOT if name == 'goal' else LIVE)
        archived = local_path(item['retained'], root=folder / 'review-evidence')
        raw, retained = read_bytes(original), read_bytes(archived)
        require(raw == retained and digest(raw) == item['sha256'], 'Original or retained ' + name + ' changed')
        blobs[name] = raw
    require(plan['evidence']['goal']['path'] == str(GOAL.resolve()) and digest(blobs['goal']) == GOAL_SHA256,
            'Fixed combat goal changed')
    binding = bind_review(*(blobs[name] for name in EVIDENCE_NAMES))
    require(canonical(binding) == canonical(plan['binding']) and binding['owner'] == plan['owner'], 'Combat review binding changed')
    recent_review(binding, json.loads(blobs['review']), plan['maximumReviewAgeSeconds'])
    verify_sources(folder, plan['sourceFiles'])
    return binding


def ordinary_identity(session):
    """Record the worker's native token and reject elevated or non-RDP execution."""
    runtime.control_module()
    from child_runner import require_ordinary_rdp, windows_identity
    identity = windows_identity()
    require_ordinary_rdp(identity, session)
    require(identity['integrityRid'] == 8192, 'Combat worker requires the ordinary medium-integrity token')
    return dict(identity, processId=os.getpid(), parentProcessId=os.getppid())


def require_idle(lifecycle, owner):
    """Admit only the sealed, minimized, idle original pair."""
    root, child = owner_pair(lifecycle, owner)
    require(idle_child(child), 'Original child is busy; combat trial refused')
    return root, child


def make_watch(folder, plan, claim, lifecycle, control=None):
    """Reuse supervision only; no scout route, request or input authority is attached."""
    remaining = (claim['deadlineMonotonicNs'] - time.monotonic_ns()) / 1e9
    require(0 < remaining <= HOST_SECONDS, 'Combat host/loading deadline expired')
    settings = SimpleNamespace(seconds=remaining, nvidia_smi=plan['resources']['nvidiaSmi'])
    watch = SessionWatch(folder, settings, plan['owner'], lifecycle)
    watch.series.stop_file = Path(plan['directory']) / 'STOP'
    watch.series.deadline_ns = min(watch.series.deadline_ns, claim['deadlineMonotonicNs'])
    if control is not None:
        # Bind the known UUID before starting monitor threads; never adopt a UUID
        # read from a substituted status file or create a new input lease here.
        watch.activate(Path(plan['directory']))
        watch.run_id = plan['runId']
    return watch


def exact_control(control, run_id):
    """A pause, malformed command or attempted goal change ends this one-shot experiment."""
    value, error = runtime.read_control_document(control.path, run_id)
    require(not error and value == dict(version=1, runId=run_id, command='run'), 'Combat control or frozen goal changed')
    require(control.snapshot() == ('run', None), 'Combat control is no longer running')
    state = control.goal_state()
    require(state['policyGoalVersion'] == 0 and all(state.get(key) is None for key in
        ('goalRequestId', 'appliedGoalRequestId', 'goalRequestStatus', 'goalError')), 'Combat goal state changed')


def episode_arguments(plan):
    """Build the exact measured H41 model settings and one unsegmented input lease."""
    folder, resources = Path(plan['directory']), plan['resources']
    args = client.parse_arguments(['--model=open-p2p', '--source', resources['modelSource'],
        '--checkpoint', resources['checkpoint'], '--goal-embedding', resources['goal'], '--goal-intent=stationary',
        '--history=41', '--cuda-graph', '--p2p-fast-start', '--p2p-prewarm', '--p2p-execution-feedback',
        '--soft-cadence', '--fps=20', '--decision-hz=10', '--seconds=5', '--action-hold-ms=100',
        '--max-observation-age-ms=150', '--enable-input', '--input-keys=LBUTTON', '--max-input-actions=3',
        '--native-combat-observation', '--require-world-ready', '--observation-profile=p2p-native-hamming-192-v1',
        '--retain-policy-rgb', '--record-max-mib=160', '--record-dir', str(folder / 'recording'),
        '--ffmpeg', resources['ffmpeg'], '--output', str(folder / 'native-episode.json')])
    args.combat_trial_binding = copy.deepcopy(plan['binding'])
    args.combat_trial_owner = copy.deepcopy(plan['owner'])
    args.expected_process_id = plan['owner']['child']['processId']
    args.expected_session_id = plan['owner']['child']['windowsSessionId']
    return args


def validate_loaded_policy(policy):
    """Require actual FP16 H41 graph preparation and settled, receipt-backed history."""
    metadata = getattr(policy, 'metadata', {})
    preparation = metadata.get('startupGraphPreparation', {})
    require(policy is not None and getattr(policy, 'execution_feedback', False) is True
        and metadata.get('precision') == 'float16' and metadata.get('historyFrames') == 41
        and metadata.get('cudaGraph') is True and metadata.get('graphCaptureValidated') is True
        and metadata.get('historyCommit') == 'accepted-proposals-only'
        and preparation.get('graphPrepared') is True and preparation.get('controllerActionsEmitted') == 0
        and preparation.get('historyFramesAfterPreparation') == 0
        and getattr(policy, '_pending_feedback', None) is False,
        'Loaded policy differs from the fixed prewarmed FP16 H41 configuration')


def await_idle(lifecycle, owner, seconds=5):
    """Observe retirement only; never stop an unknown listener or reconnect to its pipe."""
    deadline = time.monotonic() + seconds
    while True:
        _, child = owner_pair(lifecycle, owner)
        if idle_child(child):
            return True
        if time.monotonic() >= deadline:
            raise RuntimeError('Original child cleanup remains unresolved')
        time.sleep(.05)


def recorded_bytes(folder):
    """Account all retained flat recording files, including failed or unpublished episodes."""
    directory = folder / 'recording'
    if not directory.exists():
        return 0
    total = 0
    for path in directory.iterdir():
        path = local_path(path, root=directory)
        require(path.is_file(), 'Unexpected nested recording artifact')
        total += path.stat().st_size
    return total


def terminal_outcome(episode, binding):
    """Completion requires the guard's third receipt/release/post-frame drain and intact evidence."""
    guard = episode.get('combatTrialGuardState', {})
    require(canonical(episode.get('combatTrialGuard')) == canonical(binding), 'Native episode guard binding differs')
    completed = guard.get('completed', [])
    recording = episode.get('recording', {})
    frames = episode.get('framesReceived')
    # A quiet error field alone does not prove that the asynchronous writer
    # retired, or that its video, exact RGB and metadata queues drained losslessly.
    recording_verified = (isinstance(recording, dict) and recording.get('error') is None
        and all(recording.get(key) is True for key in ('complete', 'lossless', 'workerRetired'))
        and all(type(recording.get(key)) is int and recording[key] == 0 for key in
            ('droppedFrames', 'droppedEvents', 'droppedObservations', 'abandonedFrames'))
        and type(frames) is int and frames > 0 and recording.get('policyRgbEnabled') is True
        and all(type(recording.get(key)) is int and recording[key] > 0 for key in
            ('encodedFrames', 'recordedObservations', 'policyRgbFrames', 'policyRgbBytes'))
        and recording['encodedFrames'] == recording['policyRgbFrames'] == frames
        and recording['recordedObservations'] >= frames
        and recording['policyRgbBytes'] == frames * RGB192_BYTES)
    complete = (episode.get('status') == 'completed' and episode.get('endReason') == 'combatTrialComplete'
        and guard.get('phase') == 'complete' and guard.get('trialComplete') is True and guard.get('trip') is None
        and guard.get('acceptedActions') == guard.get('completedActions') == 3 and len(completed) == 3
        and episode.get('acceptedInputActions') == 3 and guard.get('pending') is None and guard.get('armed') is False
        and not any(episode.get(key) for key in ('error', 'streamError', 'stopError', 'unacknowledgedAction', 'recordingFinalizationError'))
        and recording_verified)
    if complete:
        require(all(all(key in row for key in ('arguments', 'frame', 'admission', 'receipt', 'release', 'postFrame')) for row in completed),
                'Completed combat pulses lack their retained drain evidence')
        return 'completed'
    eligible = sum(proposal_rejection(row) is None for row in episode.get('decisions', []))
    reason = (guard.get('trip') or {}).get('reason')
    evidence_error = any(episode.get(key) for key in ('streamError', 'stopError', 'unacknowledgedAction',
        'recordingFinalizationError', 'combatTrialReleaseError', 'captureError', 'episodeFailure'))
    if (guard.get('acceptedActions') == 0 and eligible == 0 and reason in ('trialEndedBeforeDrain', 'trialDeadline')
            and not evidence_error and recording_verified):
        return 'inconclusive'
    return 'failed'


def run_worker(plan_path, *, lifecycle=None, loader=None, episode=None, identity_reader=None, watch_factory=None):
    """Own one prewarm/start/episode attempt and preserve every terminal failure without retry."""
    plan, plan_sha = load_plan(plan_path)
    folder = Path(plan['directory'])
    claim, _ = document(folder / 'CONSUMED.json', 4096)
    require(claim.get('runId') == plan['runId'] and claim.get('planSha256') == plan_sha, 'Missing exact host consumption claim')
    exclusive_json(folder / 'WORKER-CONSUMED.json', dict(runId=plan['runId'], planSha256=plan_sha,
        processId=os.getpid(), parentProcessId=os.getppid()))
    report = dict(version=1, kind='combat-trial-wrapper-v1', runId=plan['runId'], planSha256=plan_sha,
        owner=plan['owner'], hostClaim=claim, status='failed', phase='validating', modelLoads=0,
        modelLoadSeconds=0.0, modelLoadAttempts=0, nativeStartAttempted=False, nativeStartOutcome='notAttempted', episodeCalls=0,
        recordedBytes=0, recordedBytesComplete=False, cleanupVerified=False, combatSuccess=False,
        worker=dict(processId=os.getpid(), parentProcessId=os.getppid()), nativeEpisode=None,
        nativeEpisodeSha256=None, combatTrialGuardState=None, terminalGuardState=None,
        enemyIdentityVerified=False, damageVerified=False, killVerified=False)
    control = watch = policy = None
    native_error = None
    try:
        report['worker'] = (identity_reader or ordinary_identity)(plan['owner']['child']['windowsSessionId'])
        identity = report['worker']
        require(identity['windowsSessionId'] == plan['owner']['child']['windowsSessionId']
            and identity['remoteDesktop'] is True and identity['elevated'] is False and identity['integrityRid'] == 8192
            and identity['processId'] == os.getpid() and identity['parentProcessId'] == os.getppid(),
            'Worker is not the original ordinary RDP session')
        verify_plan(plan, folder)
        lifecycle = lifecycle or runtime.control_module()
        require_idle(lifecycle, plan['owner'])
        control = runtime.ResidentControl(folder / 'patrol.json.control.json', folder / 'patrol.json.status.json',
                                          plan['runId'], frozen_goal=True)
        control.set_initial_goal(dict(file=str(GOAL.resolve()), sha256=GOAL_SHA256), 'stationary')
        watch = (watch_factory or make_watch)(folder, plan, claim, lifecycle, control)
        watch.start()
        require(file_sha(CHECKPOINT) == runtime.OPEN_P2P_SHA256, 'Worker checkpoint bytes differ')
        watch.check()
        exact_control(control, plan['runId'])
        args = episode_arguments(plan)
        report['phase'] = 'loading'
        control.publish(state='loading', worker=identity, modelLoads=0, modelLoadAttempts=1)
        report['modelLoadAttempts'] = 1
        began = time.perf_counter_ns()
        try:
            policy = (loader or client.load_policy)(args)
        finally:
            report.update(modelLoads=int(policy is not None), modelLoadSeconds=(time.perf_counter_ns() - began) / 1e9)
        validate_loaded_policy(policy)
        verify_plan(plan, folder)
        watch.check()
        exact_control(control, plan['runId'])
        # This stamp is minted only after the original goal survived both sides
        # of loading; the stream checks it again before opening its pipe.
        policy.combat_trial_goal_sha256 = plan['binding']['goalSha256']
        report['policyMetadata'] = copy.deepcopy(policy.metadata)
        control.set_initial_goal(copy.deepcopy(policy.metadata.get('goal')), 'stationary')
        client.validate_combat_trial_options(args, policy, control)
        _, child = require_idle(lifecycle, plan['owner'])
        watch.check()
        exact_control(control, plan['runId'])
        verify_plan(plan, folder)
        # Include listener creation in the five-second lease budget, and never
        # extend the host's original loading/operation deadline.
        args.lease_deadline = min(claim['deadlineMonotonicNs'] / 1e9, time.monotonic() + 5)
        report['leaseDeadlineMonotonicNs'] = int(args.lease_deadline * 1e9)
        report.update(phase='starting', nativeStartAttempted=True, nativeStartOutcome='unresolved')
        control.publish(state='starting', modelLoads=1)
        started = lifecycle.start_agent(child, 5, enable_input=True, observation_profile=args.observation_profile)
        require({key: started[key] for key in ('processId', 'windowsSessionId', 'instanceNonce')} == plan['owner']['child'],
                'Created listener differs from the original child')
        report.update(nativeStartOutcome='confirmed', createdListener=copy.deepcopy(started), phase='running', episodeCalls=1)
        args.pipe = started['agentPipeName']
        report['episodeExitCode'] = (episode or client.run_episode)(args, policy, control)
    except BaseException as error:
        native_error = error
        report['error'] = str(error) or type(error).__name__
    finally:
        # Never call stop_agent here: its public API identifies the child but not
        # a particular lease. run_episode alone drains its own authenticated pipe.
        try:
            path = folder / 'native-episode.json'
            if path.exists():
                native, sha = document(path)
                report.update(nativeEpisode=native, nativeEpisodeSha256=sha,
                    combatTrialGuardState=native.get('combatTrialGuardState'),
                    acceptedInputActions=native.get('acceptedInputActions', 0))
                report['status'] = terminal_outcome(native, plan['binding']) if native_error is None else 'failed'
                if report['status'] == 'completed':
                    require(report.get('episodeExitCode') == 0, 'Native episode return code differs from completion')
            elif report['nativeStartAttempted']:
                report['status'] = 'unresolved'
            if control is not None:
                report['finalGoalState'] = control.goal_state()
                report['goalChanges'] = control.goal_events()
                if getattr(control, 'combat_trial_guard', None) is not None:
                    report['terminalGuardState'] = control.combat_trial_guard.snapshot()
                exact_control(control, plan['runId'])
            if watch is not None:
                watch.check()
        except BaseException as error:
            report.update(status='failed', finalizationError=str(error) or type(error).__name__)
        try:
            if lifecycle is not None:
                report['cleanupVerified'] = await_idle(lifecycle, plan['owner'])
                report['ownerIdleMinimizedAfter'] = True
        except BaseException as error:
            report.update(status='unresolved', cleanupError=str(error) or type(error).__name__)
        for resource in (watch, control):
            if resource is not None:
                try:
                    resource.close()
                except BaseException as error:
                    report.update(status='unresolved', monitorCleanupError=str(error) or type(error).__name__)
        if watch is not None:
            try:
                watch.check()
            except BaseException as error:
                report.update(status='failed', terminalSupervisionError=str(error) or type(error).__name__)
        if control is not None:
            report['finalGoalState'] = control.goal_state()
            report['goalChanges'] = control.goal_events()
            report['finalControlDocument'], report['finalControlReadError'] = runtime.read_control_document(control.path, plan['runId'])
            try:
                exact_control(control, plan['runId'])
            except BaseException as error:
                report.update(status='failed', terminalControlError=str(error) or type(error).__name__)
        try:
            report['recordedBytes'] = recorded_bytes(folder)
            report['recordedBytesComplete'] = True
            require(report['recordedBytes'] <= MAX_RECORD_BYTES, 'Recording exceeded its fixed budget')
        except BaseException as error:
            report.update(status='failed', accountingError=str(error) or type(error).__name__)
        if (report['nativeStartOutcome'] == 'unresolved' or report.get('cleanupError') or report.get('monitorCleanupError')
                or report['nativeStartAttempted'] and report['nativeEpisode'] is None):
            report['status'] = 'unresolved'
        report.update(phase='terminal', finishedAtUnixNs=time.time_ns())
        manifest_sha = exclusive_json(folder / 'patrol.json', report)
        finalization = dict(runId=plan['runId'], manifestSha256=manifest_sha, status='failed')
        try:
            split = reserve_split(folder, plan['runId'], 'diagnostic')
            require(split['sourceManifestSha256'] == manifest_sha, 'Diagnostic split changed the terminal source')
            finalization.update(status='completed', datasetSplit=split)
        except BaseException as error:
            finalization['error'] = str(error) or type(error).__name__
        exclusive_json(folder / 'finalization.json', finalization)
    return int(report['status'] != 'completed' or finalization['status'] != 'completed')


def request_stop(folder, plan, reason):
    """Latch only this consumed plan; never address a different UUID found in a status file."""
    path = folder / 'STOP'
    if not path.exists():
        try:
            exclusive_json(path, dict(runId=plan['runId'], reason=reason))
        except FileExistsError:
            pass
    control = folder / 'patrol.json.control.json'
    if control.exists():
        value, error = runtime.read_control_document(control, plan['runId'])
        if not error and value['command'] != 'stop':
            patrol.stop_resident(folder, plan['runId'])


def launch(plan_path, *, lifecycle=None, watch_factory=None):
    """Consume and supervise one ordinary RDP command; unknown broker outcomes stay unresolved."""
    plan, plan_sha = load_plan(plan_path)
    folder = Path(plan['directory'])
    verify_plan(plan, folder)
    require(not (folder / 'STOP').exists(), 'This combat plan was stopped')
    started = time.monotonic_ns()
    claim = dict(runId=plan['runId'], planSha256=plan_sha, hostProcessId=os.getpid(),
        startedAtUnixNs=time.time_ns(), startedMonotonicNs=started, deadlineMonotonicNs=started + HOST_SECONDS * 1_000_000_000)
    exclusive_json(folder / 'CONSUMED.json', claim)
    result = dict(status='unresolved', runId=plan['runId'], planSha256=plan_sha, hostClaim=claim, launchAttempts=0)
    watch = None
    try:
        lifecycle = lifecycle or runtime.control_module()
        root, _ = require_idle(lifecycle, plan['owner'])
        supervision = folder / 'host-supervision'
        supervision.mkdir(exist_ok=False)
        watch = (watch_factory or make_watch)(supervision, plan, claim, lifecycle)
        watch.start()
        verify_plan(plan, folder)
        watch.check()
        command = [plan['resources']['gpuPython'], '-B', '-X', 'utf8', str(ROOT / 'tools/bettergi-agent/combat_trial.py'),
                   'worker', '--plan', str(Path(plan_path).resolve())]
        result.update(command=command, launchAttempts=1)
        exclusive_json(folder / 'launch.json', result)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lifecycle.run_command, root, command, str(ROOT), plan['resources']['runnerPython'],
                                 HOST_SECONDS, str(folder / 'jobs'), 262144)
            try:
                while not future.done():
                    try:
                        watch.check()
                    except Exception as error:
                        result.setdefault('stopReason', str(error) or type(error).__name__)
                        request_stop(folder, plan, result['stopReason'])
                    time.sleep(patrol.CONTROL_POLL_SECONDS)
            except BaseException as error:
                # Publish stop before the executor waits for its owned broker;
                # a keyboard interruption must not leave model loading authorized.
                result.setdefault('stopReason', str(error) or type(error).__name__)
                request_stop(folder, plan, result['stopReason'])
            broker = future.result()
        exclusive_json(folder / 'broker.json', broker)
        result['broker'] = broker
        try:
            watch.check()
        except Exception as error:
            result.setdefault('stopReason', str(error) or type(error).__name__)
        require(broker.get('windowsSessionId') == plan['owner']['child']['windowsSessionId']
            and broker.get('remoteDesktop') is True and broker.get('elevated') is False and broker.get('integrityRid') == 8192
            and broker.get('timedOut') is False and broker.get('outputIncomplete') is False,
            'Ordinary RDP worker retirement is unresolved')
        terminal, terminal_sha = document(folder / 'patrol.json')
        finish, _ = document(folder / 'finalization.json', 16384)
        worker_claim, _ = document(folder / 'WORKER-CONSUMED.json', 4096)
        require(terminal.get('runId') == plan['runId'] and terminal.get('planSha256') == plan_sha
            and terminal.get('worker', {}).get('parentProcessId') == broker.get('runnerProcessId')
            and worker_claim == dict(runId=plan['runId'], planSha256=plan_sha,
                processId=terminal['worker']['processId'], parentProcessId=terminal['worker']['parentProcessId'])
            and finish.get('status') == 'completed' and finish.get('manifestSha256') == terminal_sha
            and read_split(folder, plan['runId']) == finish.get('datasetSplit'), 'Terminal worker/accounting identity differs')
        require_idle(lifecycle, plan['owner'])
        result.update(status=terminal['status'], terminalManifestSha256=terminal_sha,
                      worker=terminal['worker'], ownerIdleMinimizedAfter=True)
        if result.get('stopReason') and result['status'] != 'unresolved':
            result['status'] = 'stopped'
        if result['status'] == 'completed':
            require(broker.get('success') is True and broker.get('returnCode') == 0, 'Completed trial lacks successful broker retirement')
    except BaseException as error:
        result.update(status='unresolved', error=str(error) or type(error).__name__)
        request_stop(folder, plan, result['error'])
    finally:
        if watch is not None:
            try:
                watch.close()
            except BaseException as error:
                result.update(status='unresolved', monitorCleanupError=str(error) or type(error).__name__)
            try:
                watch.check()
            except BaseException as error:
                result.setdefault('stopReason', str(error) or type(error).__name__)
                if result['status'] != 'unresolved':
                    result['status'] = 'stopped'
        exclusive_json(folder / 'result.json', result)
    return int(result['status'] != 'completed')


def main(argv=None):
    """Keep passive preparation, explicit launch, worker entry and terminal stop separate."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_parser = commands.add_parser('prepare')
    prepare_parser.add_argument('--directory', type=Path, required=True)
    prepare_parser.add_argument('--owner-from', type=Path, required=True)
    for name in EVIDENCE_NAMES[:-1]:
        prepare_parser.add_argument('--' + ('native-plan' if name == 'plan' else 'native-scene' if name == 'scene' else name),
                                    dest=name, type=Path, required=True)
    prepare_parser.add_argument('--maximum-review-age-seconds', type=int, default=MAX_REVIEW_AGE_SECONDS)
    for name in ('launch', 'worker', 'stop'):
        commands.add_parser(name).add_argument('--plan', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        plan = prepare(args.directory, args.owner_from, {name: getattr(args, name) for name in EVIDENCE_NAMES[:-1]},
                       maximum_review_age=args.maximum_review_age_seconds)
        print(json.dumps(dict(plan=str(args.directory / 'plan.json'), runId=plan['runId'])))
        return 0
    if args.command == 'stop':
        plan, _ = load_plan(args.plan)
        request_stop(Path(plan['directory']), plan, 'operatorStop')
        return 0
    return launch(args.plan) if args.command == 'launch' else run_worker(args.plan)


if __name__ == '__main__':
    raise SystemExit(main())
