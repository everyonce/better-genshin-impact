"""Prepare and consume one reviewed, five-second combat experiment in ordinary RDP.

Preparation never creates a review or contacts the game. ``launch --plan PLAN``
preserves the original one-shot path. ``prepare-paused`` and ``launch-prepared``
instead load without input while inventory is proved paused; ``record-resume``
and ``arm`` bind a later host-captured scene to that same waiting worker. Both
paths call run_episode once. Failed starts never reconnect or renew the deadline.
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
PREPARATION_KIND = 'combat-trial-paused-preparation-v1'
MAX_PAUSE_PROOF_AGE_SECONDS = 30
PREPARATION_MARKERS = ('preparation.json', 'prepared.json', 'RESUME-REQUESTED.json', 'RESUMED.json',
                       'ARM-REQUESTED.json', 'ARM.json', 'ARM-CONSUMED.json', 'pause-evidence', 'resume-evidence')


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


def publish_once(path, value):
    """Publish a complete immutable handoff atomically, without overwriting a prior record."""
    path = local_path(path, root=LIVE, existing=False)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        sha = exclusive_json(temporary, value)
        # Windows rename is atomic and refuses an existing target. POSIX rename
        # overwrites, so its equivalent exclusive publication uses a hard link.
        if os.name == 'nt':
            os.rename(temporary, path)
        else:
            os.link(temporary, path)
        return sha
    finally:
        temporary.unlink(missing_ok=True)


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


def prepare(folder, owner_file, evidence, *, maximum_review_age=MAX_REVIEW_AGE_SECONDS, _prepared=None):
    """Freeze a separately authored visual review, its originals and the installed source."""
    folder = local_path(folder, root=LIVE, existing=False)
    require(not folder.exists() if _prepared is None else folder == Path(_prepared['preparation']['directory'])
        and folder.is_dir() and not (folder / 'plan.json').exists(), 'A combat plan requires a fresh namespace')
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
    if _prepared is None:
        folder.mkdir(parents=True, exist_ok=False)
    retained = folder / 'review-evidence'
    retained.mkdir()
    records = {}
    for name, raw in blobs.items():
        target = retained / (name + ('.png' if name == 'image' else '.json'))
        with target.open('xb') as stream:
            stream.write(raw)
        records[name] = dict(path=str(paths[name]), retained=str(target), sha256=digest(raw))
    plan = dict(version=1, kind='combat-trial-plan-v1', runId=uuid.uuid4().hex if _prepared is None else _prepared['preparation']['runId'], directory=str(folder),
        createdAtUnixNs=time.time_ns(), owner=owner, ownerFile=str(owner_file), ownerSha256=digest(read_bytes(owner_file)),
        maximumReviewAgeSeconds=maximum_review_age, maximumHostSeconds=HOST_SECONDS,
        recordingMaximumBytes=MAX_RECORD_BYTES, policy=trial_policy(), modelConfiguration=model_settings(), binding=binding,
        evidence=records, resources=resources, checkpointSha256=runtime.OPEN_P2P_SHA256,
        checkpointStamp=file_stamp(CHECKPOINT), sourceFiles=snapshot_sources(folder) if _prepared is None else copy.deepcopy(_prepared['preparation']['sourceFiles']))
    if _prepared is not None:
        plan['preparedPolicy'] = prepared_link(_prepared)
    verify_sources(folder, plan['sourceFiles'])
    exclusive_json(folder / 'plan.json', plan)
    return plan


def retain_ui_proof(folder, source, owner, operation):
    """Archive every native UI dependency before publishing a preparation or resume record."""
    from combat_pause_proof import inspect_transition
    source = local_path(source, root=LIVE)
    proof = inspect_transition(source, owner, operation, root=ROOT)
    archive = folder / (operation + '-evidence')
    archive.mkdir(exist_ok=False)
    retained = {}
    for index, (name, sha) in enumerate(sorted(proof['files'].items())):
        raw = read_bytes(name)
        require(digest(raw) == sha, 'UI proof changed before archival')
        target = archive / (str(index).zfill(4) + '-' + Path(name).name)
        with target.open('xb') as stream:
            stream.write(raw)
        retained[name] = str(target)
    return dict(directory=str(source), proof=proof, retained=retained)


def verify_ui_proof(record, owner, operation, folder, *, originals=True):
    """Replay the original proof or its frozen archive without relying on summary booleans."""
    from combat_pause_proof import inspect_transition
    require(isinstance(record, dict) and set(record) == {'directory', 'proof', 'retained'}
        and set(record['retained']) == set(record['proof']['files']), 'Incomplete retained UI proof')
    def reader(path):
        """Require exact archived bytes and, during live admission, the unchanged originals."""
        name = str(path)
        require(name in record['retained'], 'UI proof introduced another source')
        archived = local_path(record['retained'][name], root=folder / (operation + '-evidence'))
        raw = read_bytes(archived)
        require(digest(raw) == record['proof']['files'][name]
            and (not originals or read_bytes(local_path(name, root=ROOT / 'artifacts')) == raw), 'UI proof source changed')
        return raw
    actual = inspect_transition(record['directory'], owner, operation, root=ROOT, read_file=reader)
    require(canonical(actual) == canonical(record['proof']), 'Retained UI proof no longer replays')
    return actual


def prepare_paused(folder, owner_file, pause_from):
    """Freeze a positive inventory pause and model resources, granting no input authority."""
    from combat_pause_proof import inspect_transition
    folder = local_path(folder, root=LIVE, existing=False)
    require(not folder.exists(), 'Preparation requires a fresh directory')
    owner_file, pause_from = local_path(owner_file, root=LIVE), local_path(pause_from, root=LIVE)
    owner = load_map_owner(owner_file)
    witness = inspect_transition(pause_from, owner, 'pause', root=ROOT)
    checked = time.time_ns()
    require(0 <= checked - witness['terminalTimestampUnixMs'] * 1_000_000 <= MAX_PAUSE_PROOF_AGE_SECONDS * 1_000_000_000,
            'Inventory pause witness is stale or future-dated')
    require(witness['cleanupAcknowledgedAtUnixNs'] <= checked, 'Inventory pause cleanup is future-dated')
    resources = installed_resources()
    for name, value in resources.items():
        path = local_path(value)
        require(path.is_dir() if name == 'modelSource' else path.is_file(), 'Missing installed resource: ' + name)
    require(digest(read_bytes(GOAL)) == GOAL_SHA256 and file_sha(CHECKPOINT) == runtime.OPEN_P2P_SHA256,
            'Prepared model or combat goal differs')
    folder.mkdir(parents=True, exist_ok=False)
    preparation = dict(version=1, kind=PREPARATION_KIND, runId=uuid.uuid4().hex, directory=str(folder),
        createdAtUnixNs=checked, owner=owner, ownerFile=str(owner_file), ownerSha256=digest(read_bytes(owner_file)),
        inputEnabled=False, attacksAllowed=False, maximumHostSeconds=HOST_SECONDS,
        maximumPauseProofAgeSeconds=MAX_PAUSE_PROOF_AGE_SECONDS, modelConfiguration=model_settings(),
        goalSha256=GOAL_SHA256, resources=resources, checkpointSha256=runtime.OPEN_P2P_SHA256,
        checkpointStamp=file_stamp(CHECKPOINT), sourceFiles=snapshot_sources(folder),
        pause=retain_ui_proof(folder, pause_from, owner, 'pause'))
    verify_preparation(preparation, folder, recent_pause=True)
    exclusive_json(folder / 'preparation.json', preparation)
    return preparation


def load_preparation(path):
    """A paused preparation cannot be parsed as an armed combat plan."""
    path = local_path(path, root=LIVE)
    value, sha = document(path, 2 * 1024 * 1024)
    require(path.name == 'preparation.json' and value.get('directory') == str(path.parent)
        and value.get('version') == 1 and value.get('kind') == PREPARATION_KIND
        and isinstance(value.get('runId'), str) and re.fullmatch('[a-f0-9]{32}', value['runId'])
        and value.get('inputEnabled') is False and value.get('attacksAllowed') is False
        and value.get('maximumHostSeconds') == HOST_SECONDS
        and value.get('maximumPauseProofAgeSeconds') == MAX_PAUSE_PROOF_AGE_SECONDS
        and 'binding' not in value and 'policy' not in value
        and canonical(value.get('modelConfiguration')) == canonical(model_settings()), 'Invalid zero-input preparation')
    return value, sha


def verify_preparation(preparation, folder, *, recent_pause=False, originals=True):
    """Keep source, owner, goal and pause evidence immutable throughout preparation."""
    require(preparation['owner'] == load_map_owner(preparation['ownerFile'])
        and digest(read_bytes(preparation['ownerFile'])) == preparation['ownerSha256'], 'Prepared owner evidence changed')
    expected = dict(gpuPython=GPU_PYTHON, checkpoint=CHECKPOINT, modelSource=MODEL_SOURCE, goal=GOAL)
    require(all(preparation['resources'].get(key) == str(path.resolve()) for key, path in expected.items())
        and preparation['checkpointSha256'] == runtime.OPEN_P2P_SHA256
        and file_stamp(CHECKPOINT) == preparation['checkpointStamp']
        and digest(read_bytes(GOAL)) == preparation['goalSha256'] == GOAL_SHA256, 'Prepared model or goal changed')
    proof = verify_ui_proof(preparation['pause'], preparation['owner'], 'pause', folder, originals=originals)
    if recent_pause:
        require(0 <= time.time_ns() - proof['terminalTimestampUnixMs'] * 1_000_000 <= MAX_PAUSE_PROOF_AGE_SECONDS * 1_000_000_000,
                'Inventory pause is no longer recent enough for loading')
    verify_sources(folder, preparation['sourceFiles'])
    return proof


def ready_preparation(path, *, require_waiting=True):
    """Read an actually published worker witness, never an operator-declared loaded model."""
    preparation, sha = load_preparation(path)
    folder = Path(preparation['directory'])
    ready, ready_sha = document(folder / 'prepared.json')
    claim, _ = document(folder / 'CONSUMED.json', 4096)
    worker, _ = document(folder / 'WORKER-CONSUMED.json', 4096)
    require(ready.get('version') == 1 and ready.get('kind') == 'combat-prepared-policy-v1'
        and ready.get('state') == 'preparedPaused' and ready.get('inputEnabled') is False
        and ready.get('runId') == preparation['runId'] and ready.get('preparationSha256') == sha
        and ready.get('owner') == preparation['owner'] and ready.get('goalSha256') == preparation['goalSha256']
        and ready.get('sourceFilesSha256') == digest(canonical(preparation['sourceFiles']))
        and ready.get('modelConfigurationSha256') == digest(canonical(model_settings()))
        and ready.get('hostClaim') == claim and claim.get('planSha256') == sha
        and worker == dict(runId=preparation['runId'], planSha256=sha,
            processId=ready.get('worker', {}).get('processId'), parentProcessId=ready.get('worker', {}).get('parentProcessId')),
        'Prepared worker identity or authority changed')
    require(type(ready.get('preparedAtUnixNs')) is int and type(ready.get('preparedAtClientNs')) is int
        and ready['preparedAtUnixNs'] >= preparation['createdAtUnixNs'] and ready['preparedAtClientNs'] > 0
        and ready.get('modelLoads') == 1, 'Prepared model timing or load witness changed')
    if require_waiting:
        status, _ = document(folder / 'patrol.json.status.json')
        command, error = runtime.read_control_document(folder / 'patrol.json.control.json', preparation['runId'])
        require(not (folder / 'STOP').exists() and not (folder / 'patrol.json').exists()
            and not (folder / 'ARM-CONSUMED.json').exists()
            and status.get('state') == 'preparedPaused' and status.get('runId') == preparation['runId']
            and status.get('worker') == ready['worker'] and status.get('preparedSha256') == ready_sha
            and not error and command == dict(version=1, runId=preparation['runId'], command='run')
            and time.monotonic_ns() < claim['deadlineMonotonicNs'], 'Worker is not awaiting its one combat arm')
    return dict(preparation=preparation, preparationSha256=sha, ready=ready, readySha256=ready_sha)


def record_resume(preparation_path, resume_from):
    """After one native inventory Escape, publish a QPC floor before host scene capture."""
    bundle = ready_preparation(preparation_path)
    preparation, ready = bundle['preparation'], bundle['ready']
    folder = Path(preparation['directory'])
    require(not (folder / 'RESUMED.json').exists() and not (folder / 'ARM-REQUESTED.json').exists(), 'Resume was already recorded')
    exclusive_json(folder / 'RESUME-REQUESTED.json', dict(runId=preparation['runId'], preparedSha256=bundle['readySha256']))
    try:
        verify_preparation(preparation, folder)
        record = retain_ui_proof(folder, resume_from, preparation['owner'], 'resume')
        proof = record['proof']
        require(proof['transition']['requestCreatedAtUnixMs'] * 1_000_000 >= ready['preparedAtUnixNs']
            and proof['sourceFiles'] == preparation['pause']['proof']['sourceFiles']
            and proof['cleanupAcknowledgedAtUnixNs'] <= time.time_ns()
            and 0 <= time.time_ns() - proof['terminalTimestampUnixMs'] * 1_000_000 <= MAX_PAUSE_PROOF_AGE_SECONDS * 1_000_000_000,
            'Resume preceded preparation or changed the native controller')
        require(ready_preparation(preparation_path)['readySha256'] == bundle['readySha256'], 'Prepared worker changed during resume')
        resumed = dict(version=1, kind='combat-preparation-resumed-v1', runId=preparation['runId'],
            preparationSha256=bundle['preparationSha256'], preparedSha256=bundle['readySha256'],
            worker=ready['worker'], owner=preparation['owner'], inputEnabled=False, resume=record,
            resumedAtClientNs=time.perf_counter_ns(), resumedAtUnixNs=time.time_ns())
        publish_once(folder / 'RESUMED.json', resumed)
        return resumed
    except BaseException:
        request_stop(folder, preparation, 'resumeProofRejected')
        raise


def prepared_link(bundle):
    """Identify the immutable preparation, actual worker and separately consumed resume."""
    folder = Path(bundle['preparation']['directory'])
    return dict(kind='paused-prepared-combat-authority-v1', preparationFile=str(folder / 'preparation.json'),
        preparationSha256=bundle['preparationSha256'], preparedSha256=bundle['readySha256'],
        resumedSha256=bundle['resumedSha256'], worker=bundle['ready']['worker'], armRequestId=bundle['armRequestId'])


def verify_prepared_plan(plan, folder, *, originals=True):
    """Bind fresh post-resume review/source evidence to exactly one prepared worker."""
    link = plan.get('preparedPolicy')
    require(isinstance(link, dict), 'Prepared combat authority missing')
    bundle = ready_preparation(folder / 'preparation.json', require_waiting=False)
    preparation, ready = bundle['preparation'], bundle['ready']
    resumed, resumed_sha = document(folder / 'RESUMED.json')
    bundle.update(resumedSha256=resumed_sha, armRequestId=link.get('armRequestId'))
    require(link == prepared_link(bundle) and re.fullmatch('[a-f0-9]{32}', link.get('armRequestId', ''))
        and plan['runId'] == preparation['runId'] and plan['owner'] == preparation['owner']
        and plan['ownerFile'] == preparation['ownerFile'] and plan['ownerSha256'] == preparation['ownerSha256']
        and plan['sourceFiles'] == preparation['sourceFiles'] and plan['resources'] == preparation['resources']
        and plan['checkpointStamp'] == preparation['checkpointStamp']
        and plan['checkpointSha256'] == preparation['checkpointSha256']
        and plan['binding']['goalSha256'] == preparation['goalSha256']
        and resumed.get('version') == 1 and resumed.get('kind') == 'combat-preparation-resumed-v1'
        and resumed.get('runId') == plan['runId'] and resumed.get('worker') == ready['worker']
        and resumed.get('owner') == preparation['owner'] and resumed.get('inputEnabled') is False
        and resumed.get('preparationSha256') == bundle['preparationSha256']
        and resumed.get('preparedSha256') == bundle['readySha256'], 'Prepared/resumed combat binding changed')
    proof = verify_ui_proof(resumed['resume'], preparation['owner'], 'resume', folder, originals=originals)
    require(proof['sourceFiles'] == preparation['pause']['proof']['sourceFiles']
        and proof['transition']['requestCreatedAtUnixMs'] * 1_000_000 >= ready['preparedAtUnixNs']
        and type(resumed.get('resumedAtClientNs')) is int and resumed['resumedAtClientNs'] > ready['preparedAtClientNs']
        and type(resumed.get('resumedAtUnixNs')) is int
        and resumed['resumedAtUnixNs'] >= proof['cleanupAcknowledgedAtUnixNs'], 'Resume phase or source clock changed')
    review, _ = document(plan['evidence']['review']['retained'])
    # The canonical passive collector does not declare a plan-creation clock.
    # Its actual compositor timestamp proves post-resume capture directly.
    require(type(review.get('reviewedAtUnixNs')) is int
        and review['reviewedAtUnixNs'] >= resumed['resumedAtUnixNs']
        and plan['binding']['reviewedFrame']['sourceFrame']['timestamp100ns'] * 100 > resumed['resumedAtClientNs'],
        'Combat scene/review was captured before the recorded resume')
    return bundle, resumed


def arm_prepared(preparation_path, evidence, *, maximum_review_age=MAX_REVIEW_AGE_SECONDS):
    """Publish one fresh combat authority after loading, resume and independent visual review."""
    bundle = ready_preparation(preparation_path)
    preparation = bundle['preparation']
    folder = Path(preparation['directory'])
    resumed, resumed_sha = document(folder / 'RESUMED.json')
    request_id = uuid.uuid4().hex
    exclusive_json(folder / 'ARM-REQUESTED.json', dict(runId=preparation['runId'], requestId=request_id,
        preparationSha256=bundle['preparationSha256'], preparedSha256=bundle['readySha256']))
    try:
        verify_preparation(preparation, folder)
        bundle.update(resumedSha256=resumed_sha, armRequestId=request_id)
        plan = prepare(folder, preparation['ownerFile'], evidence, maximum_review_age=maximum_review_age, _prepared=bundle)
        verify_prepared_plan(plan, folder)
        require(ready_preparation(preparation_path)['readySha256'] == bundle['readySha256'], 'Worker left the prepared phase')
        arm = dict(version=1, kind='combat-preparation-arm-v1', runId=preparation['runId'], requestId=request_id,
            preparationSha256=bundle['preparationSha256'], preparedSha256=bundle['readySha256'],
            resumedSha256=resumed_sha, worker=bundle['ready']['worker'], planSha256=digest(read_bytes(folder / 'plan.json')),
            createdAtUnixNs=time.time_ns(), createdAtClientNs=time.perf_counter_ns())
        publish_once(folder / 'ARM.json', arm)
        return plan
    except BaseException:
        request_stop(folder, preparation, 'combatArmRejected')
        raise


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
    require(('preparedPolicy' in plan) == any((path.parent / name).exists() for name in PREPARATION_MARKERS),
            'Combat plan stripped or invented its paused preparation declaration')
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
    if 'preparedPolicy' in plan:
        preparation, _ = load_preparation(folder / 'preparation.json')
        verify_preparation(preparation, folder)
        verify_prepared_plan(plan, folder)
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
    if 'binding' in plan:
        args.combat_trial_binding = copy.deepcopy(plan['binding'])
        args.combat_trial_owner = copy.deepcopy(plan['owner'])
    else:
        require(plan.get('kind') == PREPARATION_KIND and plan.get('inputEnabled') is False,
                'Only a zero-input preparation may load without combat authority')
        args.enable_input, args.input_keys, args.max_input_actions = False, '', 0
    args.expected_process_id = plan['owner']['child']['processId']
    args.expected_session_id = plan['owner']['child']['windowsSessionId']
    return args


def await_prepared_arm(preparation, preparation_sha, policy, identity, claim, control, watch, callback=None, *, model_preparation):
    """Wait under the original deadline, without a listener, until one exact arm is consumed."""
    folder = Path(preparation['directory'])
    require(not any((folder / name).exists() for name in ('prepared.json', 'RESUMED.json', 'ARM.json',
        'ARM-CONSUMED.json', 'ARM-REQUESTED.json', 'RESUME-REQUESTED.json')), 'A handoff appeared before model readiness')
    ready = dict(version=1, kind='combat-prepared-policy-v1', runId=preparation['runId'],
        preparationSha256=preparation_sha, state='preparedPaused', inputEnabled=False, owner=preparation['owner'],
        worker=identity, hostClaim=claim, modelLoads=1, goalSha256=preparation['goalSha256'],
        sourceFilesSha256=digest(canonical(preparation['sourceFiles'])),
        modelConfigurationSha256=digest(canonical(model_settings())), policyMetadata=copy.deepcopy(policy.metadata),
        modelPreparation=copy.deepcopy(model_preparation),
        preparedAtUnixNs=time.time_ns(), preparedAtClientNs=time.perf_counter_ns())
    ready_sha = publish_once(folder / 'prepared.json', ready)
    control.publish(state='preparedPaused', inputEnabled=False, worker=identity, modelLoads=1,
                    preparationSha256=preparation_sha, preparedSha256=ready_sha)
    # ResidentControl writes asynchronously. Do not announce a handoff until its
    # actual owner-bound status acknowledges this immutable readiness record.
    while True:
        watch.check()
        exact_control(control, preparation['runId'])
        try:
            status, _ = document(folder / 'patrol.json.status.json')
        except FileNotFoundError:
            status = {}
        if (status.get('state') == 'preparedPaused' and status.get('runId') == preparation['runId']
                and status.get('preparedSha256') == ready_sha and status.get('worker') == identity):
            break
        time.sleep(patrol.CONTROL_POLL_SECONDS)
    if callback is not None:
        callback(copy.deepcopy(ready))
    while True:
        watch.check()
        exact_control(control, preparation['runId'])
        require(digest(read_bytes(folder / 'preparation.json')) == preparation_sha
            and digest(read_bytes(folder / 'prepared.json')) == ready_sha, 'Prepared authority changed while waiting')
        if (folder / 'ARM.json').exists():
            arm, arm_sha = document(folder / 'ARM.json', 16384)
            exclusive_json(folder / 'ARM-CONSUMED.json', dict(runId=preparation['runId'], armSha256=arm_sha,
                preparationSha256=preparation_sha, preparedSha256=ready_sha, worker=identity))
            plan, plan_sha = load_plan(folder / 'plan.json')
            request, _ = document(folder / 'ARM-REQUESTED.json', 4096)
            resumed, resumed_sha = document(folder / 'RESUMED.json')
            require(arm == dict(version=1, kind='combat-preparation-arm-v1', runId=preparation['runId'],
                requestId=plan.get('preparedPolicy', {}).get('armRequestId'), preparationSha256=preparation_sha,
                preparedSha256=ready_sha, resumedSha256=resumed_sha, worker=identity, planSha256=plan_sha,
                createdAtUnixNs=arm.get('createdAtUnixNs'), createdAtClientNs=arm.get('createdAtClientNs'))
                and request == dict(runId=preparation['runId'], requestId=arm['requestId'],
                    preparationSha256=preparation_sha, preparedSha256=ready_sha)
                and type(arm.get('createdAtUnixNs')) is int and resumed['resumedAtUnixNs'] <= arm['createdAtUnixNs'] <= time.time_ns()
                and type(arm.get('createdAtClientNs')) is int and resumed['resumedAtClientNs'] < arm['createdAtClientNs'] <= time.perf_counter_ns(),
                'Combat arm changed worker, phase, source or plan identity')
            verify_plan(plan, folder)
            watch.check()
            exact_control(control, preparation['runId'])
            return plan, plan_sha, arm_sha
        time.sleep(patrol.CONTROL_POLL_SECONDS)


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


def run_worker(plan_path, *, lifecycle=None, loader=None, episode=None, identity_reader=None, watch_factory=None,
               paused_preparation=False, prepared_callback=None):
    """Own one prewarm/start/episode attempt and preserve every terminal failure without retry."""
    plan, plan_sha = (load_preparation if paused_preparation else load_plan)(plan_path)
    preparation, preparation_sha = (copy.deepcopy(plan), plan_sha) if paused_preparation else (None, None)
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
    if paused_preparation:
        report.update(kind='combat-trial-prepared-wrapper-v1', preparationSha256=preparation_sha,
                      preparedPolicy=None, armSha256=None, inputEnabledBeforeArm=False)
    control = watch = policy = None
    native_error = None
    try:
        report['worker'] = (identity_reader or ordinary_identity)(plan['owner']['child']['windowsSessionId'])
        identity = report['worker']
        require(identity['windowsSessionId'] == plan['owner']['child']['windowsSessionId']
            and identity['remoteDesktop'] is True and identity['elevated'] is False and identity['integrityRid'] == 8192
            and identity['processId'] == os.getpid() and identity['parentProcessId'] == os.getppid(),
            'Worker is not the original ordinary RDP session')
        if paused_preparation:
            require(not any((folder / name).exists() for name in ('prepared.json', 'RESUMED.json', 'ARM.json',
                'ARM-CONSUMED.json', 'ARM-REQUESTED.json', 'RESUME-REQUESTED.json')), 'Preparation was armed before worker admission')
            verify_preparation(plan, folder, recent_pause=True)
        else:
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
        if paused_preparation:
            loading_started = time.time_ns()
            require(0 <= loading_started - preparation['pause']['proof']['terminalTimestampUnixMs'] * 1_000_000
                <= MAX_PAUSE_PROOF_AGE_SECONDS * 1_000_000_000, 'Inventory pause expired before model loading')
            report['modelPreparation'] = dict(startedAtUnixNs=loading_started, inputEnabled=False)
        control.publish(state='loading', worker=identity, modelLoads=0, modelLoadAttempts=1)
        report['modelLoadAttempts'] = 1
        began = time.perf_counter_ns()
        try:
            policy = (loader or client.load_policy)(args)
        finally:
            report.update(modelLoads=int(policy is not None), modelLoadSeconds=(time.perf_counter_ns() - began) / 1e9)
            if paused_preparation:
                report['modelPreparation'].update(finishedAtUnixNs=time.time_ns(), modelLoadSeconds=report['modelLoadSeconds'])
        validate_loaded_policy(policy)
        if paused_preparation:
            verify_preparation(plan, folder)
            watch.check()
            exact_control(control, plan['runId'])
            report['policyMetadata'] = copy.deepcopy(policy.metadata)
            report['phase'] = 'preparedPaused'
            plan, plan_sha, arm_sha = await_prepared_arm(preparation, preparation_sha, policy, identity,
                claim, control, watch, prepared_callback, model_preparation=report['modelPreparation'])
            report.update(planSha256=plan_sha, preparedPolicy=copy.deepcopy(plan['preparedPolicy']), armSha256=arm_sha)
            args = episode_arguments(plan)
        else:
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
        _, child = require_idle(lifecycle, plan['owner'])
        watch.check()
        exact_control(control, plan['runId'])
        # Include listener creation in the five-second lease budget, and never
        # extend the host's original loading/operation deadline.
        args.lease_deadline = min(claim['deadlineMonotonicNs'] / 1e9, time.monotonic() + 5)
        report['leaseDeadlineMonotonicNs'] = int(args.lease_deadline * 1e9)
        report.update(phase='starting', nativeStartAttempted=True, nativeStartOutcome='unresolved')
        control.publish(state='starting', modelLoads=1, inputEnabled=True)
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


def launch(plan_path, *, lifecycle=None, watch_factory=None, paused_preparation=False):
    """Consume and supervise one ordinary RDP command; unknown broker outcomes stay unresolved."""
    plan, plan_sha = (load_preparation if paused_preparation else load_plan)(plan_path)
    folder = Path(plan['directory'])
    if paused_preparation:
        verify_preparation(plan, folder, recent_pause=True)
    else:
        verify_plan(plan, folder)
    require(not (folder / 'STOP').exists(), 'This combat plan was stopped')
    started = time.monotonic_ns()
    claim = dict(runId=plan['runId'], planSha256=plan_sha, hostProcessId=os.getpid(),
        startedAtUnixNs=time.time_ns(), startedMonotonicNs=started, deadlineMonotonicNs=started + HOST_SECONDS * 1_000_000_000)
    exclusive_json(folder / 'CONSUMED.json', claim)
    result = dict(status='unresolved', runId=plan['runId'], planSha256=plan_sha, hostClaim=claim, launchAttempts=0)
    if paused_preparation:
        result.update(kind='combat-preparation-launch-v1', preparationSha256=plan_sha)
    watch = None
    try:
        lifecycle = lifecycle or runtime.control_module()
        root, _ = require_idle(lifecycle, plan['owner'])
        supervision = folder / 'host-supervision'
        supervision.mkdir(exist_ok=False)
        watch = (watch_factory or make_watch)(supervision, plan, claim, lifecycle)
        watch.start()
        if paused_preparation:
            verify_preparation(plan, folder, recent_pause=True)
        else:
            verify_plan(plan, folder)
        watch.check()
        command = [plan['resources']['gpuPython'], '-B', '-X', 'utf8', str(ROOT / 'tools/bettergi-agent/combat_trial.py'),
                   'worker-prepared' if paused_preparation else 'worker',
                   '--preparation' if paused_preparation else '--plan', str(Path(plan_path).resolve())]
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
        require(terminal.get('runId') == plan['runId']
            and terminal.get('preparationSha256' if paused_preparation else 'planSha256') == plan_sha
            and terminal.get('worker', {}).get('parentProcessId') == broker.get('runnerProcessId')
            and worker_claim == dict(runId=plan['runId'], planSha256=plan_sha,
                processId=terminal['worker']['processId'], parentProcessId=terminal['worker']['parentProcessId'])
            and finish.get('status') == 'completed' and finish.get('manifestSha256') == terminal_sha
            and read_split(folder, plan['runId']) == finish.get('datasetSplit'), 'Terminal worker/accounting identity differs')
        require_idle(lifecycle, plan['owner'])
        result.update(status=terminal['status'], terminalManifestSha256=terminal_sha,
                      worker=terminal['worker'], ownerIdleMinimizedAfter=True)
        if paused_preparation:
            result['planSha256'] = terminal.get('planSha256')
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
    paused_parser = commands.add_parser('prepare-paused')
    paused_parser.add_argument('--directory', type=Path, required=True)
    paused_parser.add_argument('--owner-from', type=Path, required=True)
    paused_parser.add_argument('--pause-from', type=Path, required=True)
    for name in ('launch-prepared', 'worker-prepared', 'stop-prepared', 'record-resume', 'arm'):
        command_parser = commands.add_parser(name)
        command_parser.add_argument('--preparation', type=Path, required=True)
        if name == 'record-resume':
            command_parser.add_argument('--resume-from', type=Path, required=True)
        if name == 'arm':
            for evidence_name in EVIDENCE_NAMES[:-1]:
                command_parser.add_argument('--' + ('native-plan' if evidence_name == 'plan' else
                    'native-scene' if evidence_name == 'scene' else evidence_name), dest=evidence_name, type=Path, required=True)
            command_parser.add_argument('--maximum-review-age-seconds', type=int, default=MAX_REVIEW_AGE_SECONDS)
    for name in ('launch', 'worker', 'stop'):
        commands.add_parser(name).add_argument('--plan', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'prepare-paused':
        preparation = prepare_paused(args.directory, args.owner_from, args.pause_from)
        print(json.dumps(dict(preparation=str(args.directory / 'preparation.json'), runId=preparation['runId'], inputEnabled=False)))
        return 0
    if args.command == 'record-resume':
        resumed = record_resume(args.preparation, args.resume_from)
        print(json.dumps(dict(resumed=str(args.preparation.parent / 'RESUMED.json'), resumedAtClientNs=resumed['resumedAtClientNs'])))
        return 0
    if args.command == 'arm':
        plan = arm_prepared(args.preparation, {name: getattr(args, name) for name in EVIDENCE_NAMES[:-1]},
                            maximum_review_age=args.maximum_review_age_seconds)
        print(json.dumps(dict(plan=str(args.preparation.parent / 'plan.json'), runId=plan['runId'], armed=True)))
        return 0
    if args.command in ('launch-prepared', 'worker-prepared', 'stop-prepared'):
        if args.command == 'stop-prepared':
            preparation, _ = load_preparation(args.preparation)
            request_stop(Path(preparation['directory']), preparation, 'operatorStop')
            return 0
        operation = launch if args.command == 'launch-prepared' else run_worker
        return operation(args.preparation, paused_preparation=True)
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
