"""Discover and operate explicitly enabled BetterGI RDP automation instances."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import sys
import time
import uuid

from child_runner import atomic_json, local_absolute, MAX_JOB_BYTES, validate_job

# Reuse the established overlapped I/O and Windows PID/session/SID verification.
# The old quest-only command allowlist remains unchanged and independently usable.
_transport_path = Path(__file__).resolve().parents[1] / 'quest-pilot' / 'controller-control.py'
_spec = importlib.util.spec_from_file_location('bettergi_quest_pipe_transport', _transport_path)
transport = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(transport)
ControlError = transport.ControlError
COMMAND_FIELDS = {
    'status': set(), 'startChildSession': set(), 'minimizeChildSession': set(),
    'showChildSession': set(), 'cancelChildStart': set(), 'startChildGame': set(),
    'stopAutomationTasks': set(), 'restartApp': set(),
    'startAgentStream': {'enableInput'}, 'stopAgentStream': set(),
    'setCaptureMode': {'captureMode'},
    'startNavigationReset': {'targetYawDegrees'},
    'launchChildCommand': {'executablePath', 'arguments', 'workingDirectory', 'childSessionId'},
}
MAX_MESSAGE = 8192
CAPTURE_MODES = ('BitBlt', 'DwmGetDxSharedSurface', 'WindowsGraphicsCapture',
                 'WindowsGraphicsCaptureHdr', 'WindowsGraphicsCaptureV2')


def exchange(command, process_id, session_id, *, nonce=None, fields=None, api=None):
    """Send exactly one fresh request after authenticating its local pipe endpoint."""
    field_names = set(fields or {})
    if (command not in COMMAND_FIELDS
            or (field_names != COMMAND_FIELDS[command]
                and not (command == 'startNavigationReset' and not field_names))):
        raise ControlError('Unsupported command or command fields.')
    if command == 'startAgentStream' and type(fields['enableInput']) is not bool:
        raise ControlError('Agent input opt-in must be an explicit boolean.')
    if command == 'setCaptureMode' and fields['captureMode'] not in CAPTURE_MODES:
        raise ControlError('Capture mode must be an exact supported backend name.')
    if command == 'startNavigationReset' and 'targetYawDegrees' in field_names:
        _validate_navigation_yaw(fields['targetYawDegrees'])
    if type(process_id) is not int or process_id <= 0 or type(session_id) is not int or session_id < 0:
        raise ControlError('An exact positive process ID and nonnegative Windows session ID are required.')
    request = {'version': 1, 'requestId': str(uuid.uuid4()), 'createdAtUnixMs': int(time.time() * 1000),
               'command': command, **(fields or {})}
    if command != 'status':
        if not isinstance(nonce, str) or not 1 <= len(nonce) <= 128:
            raise ControlError('Mutations require the verified instance nonce.')
        request.update(targetProcessId=process_id, targetWindowsSessionId=session_id, targetNonce=nonce)
    elif nonce is not None:
        raise ControlError('Read-only status does not accept target fields.')
    payload = json.dumps(request, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(payload) > MAX_MESSAGE:
        raise ControlError('The control request exceeds 8192 UTF-8 bytes.')
    api = transport.WinPipeApi() if api is None else api
    sid_hash = hashlib.sha256(api.current_user_sid().encode('utf-8')).hexdigest()[:16].upper()
    pipe_name = f'\\\\.\\pipe\\BetterGI.ExternalControl.{sid_hash}.{session_id}.{process_id}'
    handle = api.connect(pipe_name)
    try:
        if api.server_pid(handle) != process_id or api.server_session(handle) != session_id:
            raise ControlError('The pipe server PID or Windows session does not match the pinned target.')
        api.verify_same_user(handle)
        api.write(handle, struct.pack('<I', len(payload)) + payload)
        size = struct.unpack('<I', transport.read_exact(api, handle, 4))[0]
        if not 0 < size <= MAX_MESSAGE:
            raise ControlError('The control response exceeds the protocol size limit.')
        try:
            response = json.loads(transport.read_exact(api, handle, size).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ControlError('The control response is not valid UTF-8 JSON.') from error
    finally:
        api.close(handle)
    if (not isinstance(response, dict) or response.get('version') != 1
            or response.get('requestId') != request['requestId']):
        raise ControlError('The control response version or request ID does not match.')
    if response.get('success') is not True:
        raise ControlError(f"{response.get('errorCode', 'unknown')}: {response.get('message', 'Command failed.')}")
    status = response.get('status')
    if (not isinstance(status, dict) or status.get('processId') != process_id
            or status.get('windowsSessionId') != session_id):
        raise ControlError('The response identifies a different process or Windows session.')
    if command != 'status' and status.get('instanceNonce') != nonce:
        raise ControlError('The process instance changed during the command; do not replay the mutation.')
    return status


def discover(*, names=None, exchange_fn=exchange, user_sid=None):
    """Probe only this user's advertised control pipes, with a bounded discovery window."""
    if user_sid is None:
        user_sid = transport.WinPipeApi().current_user_sid()
    sid_hash = hashlib.sha256(user_sid.encode('utf-8')).hexdigest()[:16].upper()
    pattern = re.compile(r'^BetterGI\.ExternalControl\.' + sid_hash + r'\.(\d+)\.(\d+)$')
    names = os.listdir('\\\\.\\pipe\\') if names is None else names
    deadline = time.monotonic() + 15
    found, unavailable = [], []
    candidates = sorted(name for name in names if pattern.fullmatch(name))[:32]
    for name in candidates:
        if time.monotonic() >= deadline:
            unavailable.append({'error': 'Discovery reached its time limit; specify the exact PID/session.'})
            break
        match = pattern.fullmatch(name)
        session_id, process_id = map(int, match.groups())
        try:
            found.append(exchange_fn('status', process_id, session_id))
        except (ControlError, OSError) as error:
            unavailable.append({'processId': process_id, 'windowsSessionId': session_id, 'error': str(error)})
    return {'instances': found, 'unavailable': unavailable}


def require_role(status, role):
    """Bind mutations to an explicitly enabled primary host or an actual RDP child."""
    if status.get('automationEnabled') is not True:
        raise ControlError('Restart this BetterGI instance with --automation to enable these hooks.')
    if status.get('instanceType') != role:
        raise ControlError(f'This command requires a {role} BetterGI instance.')
    if role == 'ChildSession' and status.get('remoteDesktop') is not True:
        raise ControlError('The target child is not running in an actual RDP session.')
    if not isinstance(status.get('instanceNonce'), str) or not status['instanceNonce']:
        raise ControlError('The target did not publish a valid instance nonce.')
    return status


def mutate(command, status, **fields):
    """Pin the mutation to the exact status identity; never retry an uncertain outcome."""
    role = 'ChildSession' if command in ('stopAutomationTasks', 'restartApp', 'startChildGame',
                                       'startAgentStream', 'stopAgentStream', 'setCaptureMode',
                                       'startNavigationReset') else 'Primary'
    require_role(status, role)
    return exchange(command, status['processId'], status['windowsSessionId'],
                    nonce=status['instanceNonce'], fields=fields)


def refresh(status):
    """Read a pinned process and reject nonce changes while waiting for an operation."""
    current = exchange('status', status['processId'], status['windowsSessionId'])
    if current.get('instanceNonce') != status['instanceNonce']:
        raise ControlError('The pinned BetterGI process instance changed while waiting.')
    return current


def wait_status(status, predicate, timeout):
    """Poll read-only status after a single accepted mutation, without resending it."""
    deadline = time.monotonic() + timeout
    while True:
        current = refresh(status)
        if predicate(current):
            return current
        if current.get('automationState') in ('failed', 'connection_failed', 'cancelled'):
            raise ControlError(current.get('automationError') or 'The automation operation failed.')
        if time.monotonic() >= deadline:
            raise ControlError('Timed out waiting for readiness; query status before retrying any mutation.')
        time.sleep(0.5)


def _dispatch_start_or_join(command, status, active_states):
    """Resolve an automatic-start race through status, without replaying a mutation."""
    try:
        mutate(command, status)
    except ControlError:
        # Automatic startup can begin between the initial read and our dispatch.
        # A fresh, same-nonce state is evidence to join it, including when the
        # request was accepted but its response was lost. Other failures propagate.
        current = refresh(status)
        require_role(current, 'Primary' if command == 'startChildSession' else 'ChildSession')
        if current.get('automationState') not in active_states:
            raise


def start_child(root, timeout):
    """Join an automatic connection or request one, then verify the child endpoint."""
    require_role(root, 'Primary')
    if root.get('automationState') not in ('connecting', 'launching_child', 'child_launch_dispatched'):
        _dispatch_start_or_join('startChildSession', root, ('connecting', 'launching_child', 'child_launch_dispatched'))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = refresh(root)
        if current.get('automationState') in ('failed', 'connection_failed', 'cancelled'):
            raise ControlError(current.get('automationError') or 'Child start failed.')
        session = current.get('childSessionId')
        if type(session) is int and session > 0 and current.get('childConnectedState') == 1:
            children = [item for item in discover()['instances']
                        if item.get('windowsSessionId') == session
                        and item.get('instanceType') == 'ChildSession'
                        and item.get('rootProcessId') == root['processId']]
            if len(children) == 1:
                return {'root': current, 'child': require_role(children[0], 'ChildSession')}
        time.sleep(0.5)
    raise ControlError('Child readiness timed out. Inspect root status and its RDP window; start was not replayed.')


def _game_runtime_ready(status):
    """Runtime attachment can precede lifecycle completion; a failure always wins over attachment."""
    if status.get('automationState') in ('failed', 'connection_failed', 'cancelled'):
        raise ControlError(status.get('automationError') or 'Game startup failed or was cancelled.')
    return status.get('automationState') == 'game_ready' and status.get('runtimeRunning') is True


def start_game(child, timeout):
    """Join automatic game startup instead of dispatching a competing lifecycle action."""
    require_role(child, 'ChildSession')
    if child.get('runtimeRunning') is True and _game_runtime_ready(child):
        return child
    if child.get('automationState') != 'starting_game':
        _dispatch_start_or_join('startChildGame', child, ('starting_game', 'game_ready'))
    return wait_status(child, _game_runtime_ready, timeout)


def start_agent(child, timeout, enable_input=False):
    """Start the fixed TaskRunner-owned stream; both server and client must opt into input."""
    require_role(child, 'ChildSession')
    if type(enable_input) is not bool:
        raise ControlError('Agent input opt-in must be an explicit boolean.')
    if not _game_runtime_ready(child):
        raise ControlError('Run start-game and wait for runtime readiness before starting the agent.')
    # Joining this same mode is harmless; changing permissions requires an explicit
    # stop followed by start. Never upgrade a running observation-only task.
    if child.get('agentStreamRunning') is True:
        if child.get('agentInputEnabled') is not enable_input:
            raise ControlError('Stop the current agent before changing its input permission.')
    else:
        mutate('startAgentStream', child, enableInput=enable_input)

    def ready(current):
        require_role(current, 'ChildSession')
        state = current.get('agentStreamState')
        if state in ('failed', 'rejected', 'stopped', 'completed'):
            raise ControlError(current.get('agentStreamError') or f'Agent stream ended before readiness: {state}.')
        if current.get('agentStreamRunning') is True and current.get('agentInputEnabled') is not enable_input:
            raise ControlError('The running agent has a different input permission.')
        return state == 'listening' and current.get('agentStreamRunning') is True

    return wait_status(child, ready, timeout)


def stop_agent(child, timeout):
    """Drain only the service-owned agent; retain the child game/runtime and unrelated tasks."""
    mutate('stopAgentStream', child)
    return wait_status(child, lambda state: state.get('agentStreamRunning') is False, timeout)


def set_capture_mode(child, mode, timeout):
    """Change one backend on an idle RDP child and await complete runtime reattachment."""
    require_role(child, 'ChildSession')
    if mode not in CAPTURE_MODES:
        raise ControlError('Capture mode must be an exact supported backend name.')
    if child.get('taskRunning') is not False or child.get('agentStreamRunning') is True:
        raise ControlError('Stop active tasks and wait for lifecycle completion before changing capture mode.')
    mutate('setCaptureMode', child, captureMode=mode)

    def ready(current):
        require_role(current, 'ChildSession')
        if not _game_runtime_ready(current):
            return False
        if current.get('captureMode') != mode:
            raise ControlError('Capture reattachment completed with a different selected backend.')
        return current.get('taskRunning') is False

    return wait_status(child, ready, timeout)


def _validate_navigation_yaw(value):
    """Keep the fixed reset's camera target finite and explicitly normalized."""
    if type(value) not in (int, float) or not 0 <= value < 360 or not math.isfinite(value):
        raise ControlError('Navigation yaw must be a finite number from 0 inclusive to 360 exclusive.')
    return value


def _parse_navigation_yaw(value):
    """Reject invalid CLI values before discovering or contacting a child."""
    try:
        return _validate_navigation_yaw(float(value))
    except (ValueError, ControlError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def reset_navigation(child, yaw_degrees, timeout):
    """Start the fixed navigation reset once and await that exact server-owned run."""
    require_role(child, 'ChildSession')
    _validate_navigation_yaw(yaw_degrees)
    if not _game_runtime_ready(child):
        raise ControlError('Run start-game and wait for runtime readiness before resetting navigation.')
    if child.get('taskRunning') is not False or child.get('agentStreamRunning') is not False:
        raise ControlError('Stop the agent and all active tasks before resetting navigation.')
    previous = child.get('navigationReset')
    if isinstance(previous, dict) and previous.get('state') == 'running':
        raise ControlError('A navigation reset is already running; query its status instead of starting another.')

    # A lost start response is ambiguous. Unlike startup joins, this operation
    # must never infer ownership from a later run or resend movement work.
    admitted = mutate('startNavigationReset', child, targetYawDegrees=yaw_degrees)
    operation = admitted.get('navigationReset')
    run_id = operation.get('runId') if isinstance(operation, dict) else None
    if (not isinstance(run_id, str) or not run_id or len(run_id) > 128
            or (isinstance(previous, dict) and run_id == previous.get('runId'))):
        raise ControlError('Navigation reset did not return a new run ID; query status before any new mutation.')

    def completed(current):
        """Pin process, operation and profile while leaving numerical acceptance to the server."""
        require_role(current, 'ChildSession')
        if any(current.get(key) != child.get(key)
               for key in ('processId', 'windowsSessionId', 'instanceNonce')):
            raise ControlError('The pinned navigation-reset process instance changed while waiting.')
        result = current.get('navigationReset')
        if not isinstance(result, dict) or result.get('runId') != run_id:
            raise ControlError('The navigation-reset run was replaced or is no longer reported.')
        state = result.get('state')
        if state in ('failed', 'cancelled'):
            raise ControlError(result.get('error') or f'Navigation reset {state}.')
        if state not in ('running', 'completed'):
            raise ControlError(f'Navigation reset has an unexpected state: {state}.')
        if (result.get('profileId') != 'mondstadt-city-10'
                or _validate_navigation_yaw(result.get('targetYawDegrees')) != yaw_degrees):
            raise ControlError('Navigation reset reports a different profile or target yaw.')
        if state == 'running':
            return False
        # These are server-validated final observations, not a client estimate of
        # arrival. Preserve additive confidence/source fields in the full reply.
        samples = result.get('samples')
        if not isinstance(samples, list) or len(samples) != 3:
            raise ControlError('Completed navigation reset must report three final observations.')
        for sample in samples:
            if (not isinstance(sample, dict)
                    or any(type(sample.get(key)) not in (int, float)
                           or not math.isfinite(sample[key]) for key in ('x', 'y', 'yawDegrees'))
                    or not isinstance(sample.get('capturedAtUtc'), str) or not sample['capturedAtUtc']):
                raise ControlError('Completed navigation reset contains an invalid final observation.')
        if current.get('agentStreamRunning') is not False:
            raise ControlError('An agent stream is active or unknown while the navigation reset completes.')
        return _game_runtime_ready(current) and current.get('taskRunning') is False

    if completed(admitted):
        return admitted
    return wait_status(child, completed, timeout)


def background_python(executable):
    """Select the interpreter's windowless sibling so the runner cannot steal game focus."""
    executable = local_absolute(executable)
    if (not re.fullmatch(r'python(?:[0-9.]*)w?\.exe', executable.name, re.IGNORECASE)
            or not executable.is_file()):
        raise ControlError('--python must identify an existing local Python executable.')
    windowless = executable if executable.stem.lower().endswith('w') else executable.with_name('pythonw.exe')
    if not windowless.is_file():
        raise ControlError('A sibling pythonw.exe is required for the background runner; no visible-console fallback is used.')
    return windowless


def run_command(root, argv, work_dir, python_exe, timeout, job_dir, output_limit):
    """Launch the fixed ordinary-token runner and wait for its unique atomic result."""
    require_role(root, 'Primary')
    session = root.get('childSessionId')
    if type(session) is not int or session <= 0 or root.get('childConnectedState') != 1:
        raise ControlError('Start and connect the RDP child before running a command.')
    job_id = str(uuid.uuid4())
    job = {'version': 1, 'jobId': job_id, 'createdAtUnixMs': int(time.time() * 1000),
           'windowsSessionId': session, 'argv': argv, 'workingDirectory': str(local_absolute(work_dir)),
           'timeoutSeconds': timeout, 'maxOutputBytes': output_limit}
    validate_job(job, job_id)
    python_exe = background_python(python_exe)
    job_dir = local_absolute(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / (job_id + '.job.json')
    if len(json.dumps(job, ensure_ascii=False).encode('utf-8')) > MAX_JOB_BYTES:
        raise ControlError('The command job exceeds the size limit.')
    # UUID file names plus exclusive creation prevent accidental overwrite/replay.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(job, stream, ensure_ascii=False, allow_nan=False)
    launch_error = None
    try:
        mutate('launchChildCommand', root, executablePath=str(python_exe),
               arguments=[str(Path(__file__).with_name('child_runner.py').resolve()), '--job', str(path)],
               workingDirectory=str(Path(__file__).parent.resolve()), childSessionId=session)
    except (ControlError, OSError) as error:
        # An I/O failure can follow successful dispatch. The same job/result is
        # inspected; a second launch request is never sent automatically.
        launch_error = str(error)
    result_path = path.with_name(job_id + '.result.json')
    deadline = time.monotonic() + timeout + 30
    while time.monotonic() < deadline:
        if result_path.exists():
            if result_path.stat().st_size > 16 * output_limit + 65536:
                raise ControlError('Command result exceeds the bounded output size.')
            result = json.loads(result_path.read_text(encoding='utf-8'))
            if not isinstance(result, dict) or result.get('version') != 1 or result.get('jobId') != job_id:
                raise ControlError('The returned command result has the wrong job identity.')
            if 'windowsSessionId' in result and result['windowsSessionId'] != session:
                raise ControlError('The command result identifies a different Windows session.')
            return {'jobFile': str(path), 'resultFile': str(result_path), **result}
        time.sleep(0.2)
    suffix = f' Dispatch reported: {launch_error}' if launch_error else ''
    raise ControlError(f'Command result timed out; outcome is unknown. Inspect {path}; do not replay it.{suffix}')


def _no_links(path):
    """Match the restart server's requirement for a physical local staging tree."""
    for item in (path, *path.parents):
        attributes = item.stat()
        if item.is_symlink() or getattr(attributes, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ControlError('Replacement paths must not contain filesystem links.')


def _sha256(path):
    """Hash staged binary bytes without loading them into the current process."""
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stage_configuration(source, target):
    """Copy local settings and missing custom profiles without replacing shipped assets."""
    source = local_absolute(source)
    target = local_absolute(target)
    _no_links(source)
    _no_links(target)
    if source.resolve() == target.resolve() or not (target / 'BetterGI.exe').is_file():
        raise ControlError('Choose a different, already published BetterGI target directory.')
    selected = []
    for relative in ('User/config.json', 'User/ExternalControl/enable-quest-control.json'):
        candidate = source / relative
        if candidate.is_file():
            selected.append(candidate)
    # Preserve custom definitions only when the new package did not ship a file
    # with that name. JS/I18n, default assets, caches and recorded proof stay out.
    for directory in ('ScriptGroup', 'AutoFight', 'AutoGeniusInvokation', 'AutoPathing'):
        profile_root = source / 'User' / directory
        if profile_root.is_dir():
            _no_links(profile_root)
            selected.extend(item for item in profile_root.rglob('*')
                            if item.is_file() and item.suffix.lower() in ('.json', '.txt', '.yaml', '.yml'))
    if len(selected) > 4096:
        raise ControlError('Configuration staging exceeds the 4096-file limit.')
    copied, retained = [], []
    planned = []
    for path in selected:
        _no_links(path)
        relative = path.relative_to(source)
        destination = target / relative
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ControlError('A configuration/profile file exceeds the 16 MiB limit.')
        # Validate every existing target ancestor before creating any directory.
        ancestor = destination
        while not ancestor.exists():
            ancestor = ancestor.parent
        _no_links(ancestor)
        if destination.exists():
            if relative.as_posix() in ('User/config.json', 'User/ExternalControl/enable-quest-control.json'):
                if _sha256(path) != _sha256(destination):
                    raise ControlError(f'Target already has different {relative}; select a fresh published release.')
            retained.append(relative.as_posix())
        else:
            planned.append((path, destination, relative))
    for path, destination, relative in planned:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with path.open('rb') as original, destination.open('xb') as replacement:
            shutil.copyfileobj(original, replacement)
        copied.append(relative.as_posix())
    report = {'version': 1, 'sourceDirectory': str(source), 'targetDirectory': str(target),
              'copied': copied, 'retainedFromTarget': retained}
    report_path = target / 'configuration-staging.json'
    atomic_json(report_path, report)
    return {**report, 'reportFile': str(report_path)}


def prepare_replacement(current, target, *, require_opt_in=True):
    """Validate a sibling portable net10 release before stopping any active task."""
    current = local_absolute(current)
    target = local_absolute(target)
    expected_name = 'bettergi-english-win-x64'
    if (current.name.lower() != expected_name or target.name.lower() != expected_name
            or not re.fullmatch(r'release-r[0-9]+', current.parent.name)
            or not re.fullmatch(r'release-r[0-9]+', target.parent.name)
            or os.path.normcase(str(current.parent.parent)) != os.path.normcase(str(target.parent.parent))
            or os.path.normcase(str(current)) == os.path.normcase(str(target))):
        raise ControlError('Hot replacement requires a different sibling release-rN/BetterGI-English-win-x64 directory.')
    _no_links(current)
    _no_links(target)
    if require_opt_in:
        for directory in (current, target):
            marker = json.loads((directory / 'User/ExternalControl/enable-quest-control.json').read_text(encoding='utf-8-sig'))
            if marker.get('version') != 1 or marker.get('enabled') is not True or marker.get('allowAppRestart') is not True:
                raise ControlError('Both installations must enable external control and allowAppRestart.')
    options = json.loads((target / 'BetterGI.runtimeconfig.json').read_text(encoding='utf-8-sig'))['runtimeOptions']
    frameworks = options.get('includedFrameworks', [])
    if (options.get('tfm') != 'net10.0' or 'framework' in options or 'frameworks' in options
            or len(frameworks) != 3
            or {item.get('name') for item in frameworks} != {'Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App',
                                                           'Microsoft.AspNetCore.App'}
            or any(not re.fullmatch(r'10\.0\.\d+', item.get('version', '')) for item in frameworks)):
        raise ControlError('The replacement must be a self-contained .NET10 Windows Desktop build.')
    deps = json.loads((target / 'BetterGI.deps.json').read_text(encoding='utf-8-sig'))
    if deps.get('runtimeTarget', {}).get('name') != '.NETCoreApp,Version=v10.0/win-x64':
        raise ControlError('The replacement dependency manifest must target .NET10 win-x64.')
    for name in ('BetterGI.exe', 'BetterGI.dll', 'hostfxr.dll', 'hostpolicy.dll', 'coreclr.dll',
                 'System.Private.CoreLib.dll', 'PresentationFramework.dll'):
        file = target / name
        if not file.is_file() or file.stat().st_size == 0:
            raise ControlError(f'The portable replacement is missing {name}.')
        _no_links(file)
    return {'version': 1, 'targetDirectory': str(target),
            'exeSha256': _sha256(target / 'BetterGI.exe'), 'dllSha256': _sha256(target / 'BetterGI.dll')}


def enable_restart(current, target):
    """Provision the explicit hot-replace opt-in, preserving unrelated local fields."""
    planned = []
    for directory in (Path(current), Path(target)):
        path = directory / 'User/ExternalControl/enable-quest-control.json'
        ancestor = path
        while not ancestor.exists():
            ancestor = ancestor.parent
        _no_links(ancestor)
        marker = {}
        if path.exists():
            if path.stat().st_size > 4096:
                raise ControlError('Existing restart opt-in exceeds the size limit.')
            marker = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(marker, dict) or marker.get('version') != 1:
                raise ControlError('Existing restart opt-in has an unsupported format.')
        marker.update(version=1, enabled=True, allowAppRestart=True)
        if len(json.dumps(marker).encode('utf-8')) > 4096:
            raise ControlError('Updated restart opt-in exceeds the size limit.')
        planned.append((path, marker))
    for path, marker in planned:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(path, marker)


def _require_connected_root(root, child):
    """Require a distinct, authenticated primary still connected to this exact child session."""
    require_role(root, 'Primary')
    if (type(root.get('processId')) is not int or root['processId'] <= 0
            or type(root.get('windowsSessionId')) is not int or root['windowsSessionId'] < 0
            or root['windowsSessionId'] == child['windowsSessionId']
            or root.get('childSessionId') != child['windowsSessionId']
            or root.get('childConnectedState') != 1):
        raise ControlError('The pinned primary is not connected to this child Windows session.')
    return root


def resolve_child_root(child):
    """Pin one independently discovered primary, including legacy children lacking rootProcessId."""
    roots = [item for item in discover()['instances']
             if item.get('instanceType') == 'Primary' and item.get('automationEnabled') is True
             and item.get('childSessionId') == child['windowsSessionId']
             and item.get('childConnectedState') == 1]
    if len(roots) != 1:
        raise ControlError('Expected exactly one authenticated, connected automation primary for this child.')
    root = _require_connected_root(refresh(roots[0]), child)
    advertised = child.get('rootProcessId')
    if advertised is not None and (type(advertised) is not int or advertised != root['processId']):
        raise ControlError('The child advertises a different root process than its verified connected primary.')
    return root


def hot_replace(child, target, timeout):
    """Drain tasks, restart only this child, then verify replacement identity and assembly."""
    require_role(child, 'ChildSession')
    manifest = prepare_replacement(child['appDirectory'], target, require_opt_in=False)
    root = resolve_child_root(child)
    enable_restart(child['appDirectory'], target)
    mutate('stopAutomationTasks', child)
    idle = wait_status(child, lambda state: state.get('taskRunning') is False, timeout)
    _require_connected_root(refresh(root), child)
    manifest_path = Path(idle['appDirectory']) / 'User/ExternalControl/pending-restart.json'
    atomic_json(manifest_path, manifest)
    # Preflight completed before the stop; server independently rechecks both hashes.
    mutate('restartApp', idle)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # The host must remain the same process epoch and connected session across
        # the handoff. A missing legacy root ID never counts as matching another None.
        current_root = _require_connected_root(refresh(root), child)
        for candidate in discover()['instances']:
            if (candidate.get('windowsSessionId') == child['windowsSessionId']
                    and candidate.get('processId') != child['processId']
                    and candidate.get('instanceNonce') != child['instanceNonce']
                    and candidate.get('instanceType') == 'ChildSession'
                    and candidate.get('rootProcessId') == root['processId']
                    and os.path.normcase(candidate.get('appDirectory', '').rstrip('\\/'))
                    == os.path.normcase(str(Path(target)).rstrip('\\/'))
                    and candidate.get('assemblySha256', '').lower() == manifest['dllSha256']):
                require_role(candidate, 'ChildSession')
                if _game_runtime_ready(candidate) and candidate.get('taskRunning') is False:
                    current_root = _require_connected_root(refresh(root), child)
                    return {'ready': True, 'previousProcessId': child['processId'],
                            'legacyRootResolution': child.get('rootProcessId') is None,
                            'manifest': manifest, 'root': current_root, 'child': candidate}
        time.sleep(0.5)
    raise ControlError('Replacement was dispatched but readiness was not verified; discover/status before further action.')


def main():
    """Expose explicit host/child operations with machine-readable JSON output."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('discover', help='list authenticated same-user automation/control instances')
    staging = sub.add_parser('stage-config', help='copy local settings and missing custom profiles into a published release')
    staging.add_argument('--source-directory', required=True)
    staging.add_argument('--target-directory', required=True)
    for command in ('status', 'start', 'cancel-start', 'start-game', 'start-agent', 'stop-agent', 'set-capture-mode', 'reset-navigation', 'minimize', 'show', 'exec', 'hot-replace'):
        item = sub.add_parser(command)
        item.add_argument('--process-id', type=int)
        item.add_argument('--windows-session-id', type=int)
        item.add_argument('--timeout', type=int, default=120)
        if command == 'start-agent':
            item.add_argument('--enable-input', action='store_true', help='explicitly permit controller input in the RDP child')
        if command == 'set-capture-mode':
            item.add_argument('--mode', required=True, choices=CAPTURE_MODES)
        if command == 'reset-navigation':
            item.add_argument('--yaw-degrees', type=_parse_navigation_yaw, default=0.0,
                              help='fixed reset camera yaw in [0, 360); defaults to 0 degrees')
        if command == 'exec':
            item.add_argument('--python', default=sys.executable)
            item.add_argument('--work-dir', default=str(Path.cwd()))
            item.add_argument('--job-dir', default=str(Path(__file__).resolve().parents[2] / 'artifacts/rdp-automation/jobs'))
            item.add_argument('--output-limit', type=int, default=262144)
            item.add_argument('argv', nargs=argparse.REMAINDER)
        if command == 'hot-replace':
            item.add_argument('--target-directory', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'discover':
            result = discover()
        elif args.command == 'stage-config':
            result = stage_configuration(args.source_directory, args.target_directory)
        else:
            if not 1 <= args.timeout <= 3600:
                raise ControlError('--timeout must be between 1 and 3600 seconds.')
            if (args.process_id is None) != (args.windows_session_id is None):
                raise ControlError('Specify both --process-id and --windows-session-id.')
            role = 'ChildSession' if args.command in ('hot-replace', 'start-game', 'start-agent', 'stop-agent', 'set-capture-mode', 'reset-navigation') else 'Primary'
            if args.process_id is not None:
                status = exchange('status', args.process_id, args.windows_session_id)
            else:
                candidates = [item for item in discover()['instances']
                              if item.get('instanceType') == role and item.get('automationEnabled') is True]
                if len(candidates) != 1:
                    raise ControlError('Target discovery is ambiguous or empty; specify its exact PID and Windows session.')
                status = candidates[0]
            if args.command == 'status':
                result = status
            elif args.command == 'start':
                result = start_child(status, args.timeout)
            elif args.command == 'cancel-start':
                result = mutate('cancelChildStart', status)
            elif args.command == 'start-game':
                result = start_game(status, args.timeout)
            elif args.command == 'start-agent':
                result = start_agent(status, args.timeout, args.enable_input)
            elif args.command == 'stop-agent':
                result = stop_agent(status, args.timeout)
            elif args.command == 'set-capture-mode':
                result = set_capture_mode(status, args.mode, args.timeout)
            elif args.command == 'reset-navigation':
                result = reset_navigation(status, args.yaw_degrees, args.timeout)
            elif args.command in ('minimize', 'show'):
                mutate('minimizeChildSession' if args.command == 'minimize' else 'showChildSession', status)
                result = wait_status(status, lambda state: state.get('childWindowMinimized') is (args.command == 'minimize'), args.timeout)
            elif args.command == 'exec':
                argv = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
                result = run_command(status, argv, args.work_dir, args.python, args.timeout, args.job_dir, args.output_limit)
            else:
                result = hot_replace(status, args.target_directory, args.timeout)
        # Console pipes on Windows commonly use cp1252. ASCII JSON preserves all
        # Unicode paths through escapes; persisted job/report files remain UTF-8.
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 1 if result.get('success') is False else 0
    except (ControlError, OSError, ValueError, KeyError) as error:
        print(json.dumps({'success': False, 'error': str(error)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
