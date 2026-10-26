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
import tempfile
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


class NavigationResetError(ControlError):
    """Retain the authenticated terminal reset status when the operation or evidence read fails."""
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


class NavigationBaselineError(ControlError):
    """Retain the last verified baseline status and any pinned terminal evidence."""
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


class ReplacementError(ControlError):
    """Preserve the last bounded handoff phase without replaying an uncertain restart."""
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = dict(evidence)


COMMAND_FIELDS = {
    'status': set(), 'startChildSession': {'childStartupMode'}, 'minimizeChildSession': set(),
    'showChildSession': set(), 'cancelChildStart': set(), 'startChildGame': set(),
    'stopAutomationTasks': set(), 'restartApp': set(),
    'startAgentStream': {'enableInput', 'observationProfile', 'experimentalQueuedStepApplications'}, 'stopAgentStream': set(),
    'setCaptureMode': {'captureMode', 'readbackMode', 'sourceRetention', 'conversion', 'desktopDcSourcePolicy'},
    'startNavigationReset': {'targetYawDegrees', 'capturePolicy'},
    'navigationResetDiagnostics': {'navigationResetRunId'},
    'startNavigationBaseline': {'timingContract', 'capturePolicy', 'routeProfile', 'continuationFromRunId', 'shadowCapture'},
    'navigationBaselineResult': {'navigationBaselineRunId'},
    'launchChildCommand': {'executablePath', 'arguments', 'workingDirectory', 'childSessionId'},
}
MAX_MESSAGE = 8192
MAX_NAVIGATION_DIAGNOSTICS_RESPONSE = 32768
CAPTURE_MODES = ('BitBlt', 'DwmGetDxSharedSurface', 'WindowsGraphicsCapture',
                 'WindowsGraphicsCaptureHdr', 'WindowsGraphicsCaptureV2', 'DesktopDc')
READBACK_MODES = ('blocking', 'poll_single_v1')
SOURCE_RETENTIONS = ('disabled', 'hold-until-readback-v1')
CONVERSION_MODES = ('gpu', 'cpu')
DESKTOP_DC_SOURCE_POLICIES = ('observe-only', 'host-acquisition-v1')
# Explicit null is invalid; only an omitted helper argument preserves saved settings.
_CAPTURE_OPTION_UNSET = object()
SHADOW_CAPTURE_MODE = 'rgb192-capture-only-v1'
# The default retains the old wire shape so explicitly selected legacy runtimes remain usable.
LEGACY_OBSERVATION_PROFILE = 'legacy-area-640x360-v1'
OBSERVATION_PROFILES = (LEGACY_OBSERVATION_PROFILE, 'p2p-native-hamming-192-v1')


def _observation_profile(value):
    """Normalize an omitted profile without accepting aliases, coercions, or unknown encodings."""
    if value is None:
        return LEGACY_OBSERVATION_PROFILE
    if not isinstance(value, str) or value not in OBSERVATION_PROFILES:
        raise ControlError('Observation profile must be an exact supported profile name.')
    return value


def exchange(command, process_id, session_id, *, nonce=None, fields=None, api=None):
    """Send exactly one fresh request after authenticating its local pipe endpoint."""
    field_names = set(fields or {})
    if (command not in COMMAND_FIELDS
            or (field_names != COMMAND_FIELDS[command]
                and not (command == 'startNavigationReset' and field_names <= COMMAND_FIELDS[command])
                and not (command == 'startNavigationBaseline' and field_names <= COMMAND_FIELDS[command])
                and not (command == 'setCaptureMode' and 'captureMode' in field_names
                         and field_names <= COMMAND_FIELDS[command])
                and not (command == 'startChildSession' and not field_names)
                and not (command == 'startAgentStream' and 'enableInput' in field_names
                         and field_names <= COMMAND_FIELDS[command])
                and not (command == 'restartApp' and field_names == {'idleRestart'}))):
        raise ControlError('Unsupported command or command fields.')
    if command == 'startChildSession' and field_names and fields['childStartupMode'] not in ('controlEndpoint', 'gameRuntime'):
        raise ControlError('Child startup mode must be exactly controlEndpoint or gameRuntime.')
    if command == 'restartApp' and field_names:
        expected = fields['idleRestart']
        if (not isinstance(expected, dict)
                or type(expected.get('version')) is not int
                or not (expected['version'] == 1
                        and set(expected) == {'version', 'targetDirectory', 'exeSha256', 'dllSha256'}
                        or expected['version'] == 2
                        and set(expected) == {'version', 'targetDirectory', 'exeSha256', 'dllSha256', 'startupMode'}
                        and expected.get('startupMode') in ('controlEndpoint', 'gameRuntime'))
                or any(not isinstance(expected.get(key), str)
                       or re.fullmatch(r'[0-9a-fA-F]{64}', expected[key]) is None
                       for key in ('exeSha256', 'dllSha256'))):
            raise ControlError('Atomic idle restart requires exact target hashes and a supported version/startup intent.')
        try:
            local_absolute(expected['targetDirectory'])
        except (ValueError, TypeError) as error:
            raise ControlError('Atomic idle restart requires a local absolute target directory.') from error
    if command == 'startAgentStream' and type(fields['enableInput']) is not bool:
        raise ControlError('Agent input opt-in must be an explicit boolean.')
    if command == 'startAgentStream':
        _observation_profile(fields.get('observationProfile'))
        if 'experimentalQueuedStepApplications' in field_names:
            experimental = fields['experimentalQueuedStepApplications']
            if type(experimental) is not bool:
                raise ControlError('Experimental queued step applications require an explicit boolean.')
            if experimental and fields['enableInput'] is not True:
                raise ControlError('Experimental queued step applications require explicit input opt-in.')
    if command == 'setCaptureMode' and fields['captureMode'] not in CAPTURE_MODES:
        raise ControlError('Capture mode must be an exact supported backend name.')
    if command == 'setCaptureMode' and 'readbackMode' in field_names:
        _validate_capture_readback(fields['captureMode'], fields['readbackMode'])
    if command == 'setCaptureMode':
        for name, choices in (('sourceRetention', SOURCE_RETENTIONS), ('conversion', CONVERSION_MODES)):
            if name in field_names:
                _validate_capture_option(fields['captureMode'], name, fields[name], choices)
        if 'desktopDcSourcePolicy' in field_names:
            _validate_desktop_dc_policy(fields['captureMode'], fields['desktopDcSourcePolicy'])
    if command == 'startNavigationReset' and 'targetYawDegrees' in field_names:
        _validate_navigation_yaw(fields['targetYawDegrees'])
    if command == 'startNavigationBaseline' and 'shadowCapture' in field_names:
        if (fields['shadowCapture'] != SHADOW_CAPTURE_MODE
                or fields.get('timingContract') != 'v4' or fields.get('capturePolicy') != 'task_owned_timer'):
            raise ControlError('Shadow capture requires the exact selector, v4 and task_owned_timer.')
    if command == 'startNavigationBaseline' and 'routeProfile' in field_names:
        if fields['routeProfile'] not in ('mondstadt-city-leg-1-v1', 'mondstadt-city-two-legs-v1', 'mondstadt-city-reverse-two-legs-v1', 'mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1'):
            raise ControlError('Unsupported fixed baseline route profile.')
        if (fields['routeProfile'] in ('mondstadt-city-two-legs-v1', 'mondstadt-city-reverse-two-legs-v1', 'mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1')
                and (fields.get('timingContract') not in ('v4', 'v5') or fields.get('capturePolicy') != 'task_owned_timer')):
            raise ControlError('The two-leg route requires explicit v4 or v5 and task_owned_timer.')
    if command == 'startNavigationBaseline' and 'timingContract' in field_names:
        if not isinstance(fields['timingContract'], str) or fields['timingContract'] not in ('v1', 'v2', 'v3', 'v4', 'v5'):
            raise ControlError('Baseline timing contract must be exactly v1, v2, v3, v4 or v5.')
    if command in ('startNavigationBaseline', 'startNavigationReset') and 'capturePolicy' in field_names:
        if not isinstance(fields['capturePolicy'], str) or fields['capturePolicy'] not in ('shared', 'task_owned_timer'):
            raise ControlError('Navigation capture policy must be exactly shared or task_owned_timer.')
    if command == 'startNavigationBaseline':
        continuation_requested = (fields or {}).get('routeProfile') in ('mondstadt-city-reverse-two-legs-v1', 'mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1')
        predecessor = (fields or {}).get('continuationFromRunId')
        if continuation_requested:
            if (not isinstance(predecessor, str) or re.fullmatch(r'[0-9a-fA-F]{32}', predecessor) is None
                    or int(predecessor, 16) == 0):
                raise ControlError('Continuation requires the exact nonzero predecessor run ID.')
        elif 'continuationFromRunId' in field_names:
            raise ControlError('A predecessor run ID is valid only with an explicit fixed continuation selector.')
    if command in ('navigationResetDiagnostics', 'navigationBaselineResult'):
        run_id = fields['navigationResetRunId' if command == 'navigationResetDiagnostics' else 'navigationBaselineRunId']
        if (not isinstance(run_id, str) or re.fullmatch(r'[0-9a-fA-F]{32}', run_id) is None
                or run_id == '0' * 32):
            raise ControlError('Navigation evidence requires the exact nonzero 32-character run ID.')
    if type(process_id) is not int or process_id <= 0 or type(session_id) is not int or session_id < 0:
        raise ControlError('An exact positive process ID and nonnegative Windows session ID are required.')
    request = {'version': 1, 'requestId': str(uuid.uuid4()), 'createdAtUnixMs': int(time.time() * 1000),
               'command': command, **(fields or {})}
    if command != 'status':
        if not isinstance(nonce, str) or not 1 <= len(nonce) <= 128:
            raise ControlError('Pinned commands require the verified instance nonce.')
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
        response_limit = MAX_NAVIGATION_DIAGNOSTICS_RESPONSE if command in (
            'navigationResetDiagnostics', 'navigationBaselineResult') else MAX_MESSAGE
        if not 0 < size <= response_limit:
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
                                       'startNavigationReset', 'startNavigationBaseline') else 'Primary'
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


def _current_start_root(root):
    """Legacy hosts omit uiStatus; an explicit degraded snapshot never authorizes startup."""
    current = require_role(refresh(root), 'Primary')
    if current.get('uiStatus', 'current') != 'current' or current.get('automationState') == 'unresponsive':
        raise ControlError('Current root UI/lifecycle status is unavailable; no startup action was taken.')
    return current


def _startup_child_candidate(root, discovery):
    """An unavailable or conflicting endpoint is not evidence that a child is missing."""
    session = root.get('childSessionId')
    if any(type(item.get('windowsSessionId')) is not int or item['windowsSessionId'] <= 0
           or item['windowsSessionId'] == session or session is None
           for item in discovery.get('unavailable', [])):
        raise ControlError('A relevant child endpoint is unavailable; inspect status before recovery.')
    if type(session) is not int or session <= 0:
        return None
    children = [item for item in discovery['instances'] if item.get('windowsSessionId') == session]
    if any(item.get('instanceType') != 'ChildSession' for item in children):
        raise ControlError('A foreign BetterGI role occupies the target RDP session; recovery is not authorized by absence.')
    if len(children) > 1:
        raise ControlError('Multiple child endpoints exist in the target RDP session; recovery is ambiguous.')
    if not children:
        return None
    child = require_role(children[0], 'ChildSession')
    if (type(child.get('processId')) is not int or child['processId'] <= 0
            or child['processId'] == root['processId'] or session == root['windowsSessionId']):
        raise ControlError('The child process/session identity is invalid.')
    return child


def _startup_child(root, discovery):
    """Ordinary start requires the corrected backlink; legacy upgrade is a separate operation."""
    child = _startup_child_candidate(root, discovery)
    if child is None:
        return None
    if child.get('rootProcessId') != root['processId']:
        raise ControlError('The child does not advertise the verified root identity; legacy or conflicting children require explicit recovery.')
    if child.get('uiStatus', 'current') != 'current':
        raise ControlError('Current child UI/lifecycle status is unavailable; readiness cannot be verified.')
    return child


def _child_start_fields(root, mode, *, joining=False):
    """Endpoint-only intent never silently downgrades to an older primary's game startup."""
    if mode is None:
        return {}
    if mode not in ('controlEndpoint', 'gameRuntime'):
        raise ControlError('Child startup mode must be exactly controlEndpoint or gameRuntime.')
    supported = type(root.get('childStartupIntentVersion')) is int and root['childStartupIntentVersion'] == 1
    if mode == 'controlEndpoint':
        if not supported:
            raise ControlError('Host missing-child startup requires childStartupIntentVersion 1; the legacy primary was not changed or restarted.')
        if joining and root.get('childStartupMode') != mode:
            raise ControlError('Host cannot join an active game or unknown child startup intent.')
    # Game may join a controlEndpoint bootstrap and start the child game later.
    # Omitted intent preserves the legacy primary protocol for ordinary Game callers.
    return {'childStartupMode': mode} if supported else {}


def start_child(root, timeout, preserve_window=False, *, _candidate=None, _read_root=None,
                startup_mode=None, _before_dispatch=None):
    """Reuse a verified child or dispatch one recovery, never replay an uncertain request."""
    require_role(root, 'Primary')
    select_child = _candidate or _startup_child
    read_root = _read_root or _current_start_root
    active_states = ('connecting', 'launching_child')
    # A launch observed in progress belongs to this wait. Its completed dispatch
    # must not cause another launch within this same invocation.
    following_launch = root.get('automationState') in active_states
    dispatched = minimized = False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = read_root(root)
        child = select_child(current, discover())
        state = current.get('automationState', 'idle')
        if (following_launch or dispatched) and state in ('failed', 'connection_failed', 'cancelled'):
            raise ControlError(current.get('automationError') or 'Child start failed.')
        if child is not None and current.get('childConnectedState') == 1:
            # An explicit start restores background operation by default. The
            # preserve option leaves an existing shown window as the user chose it.
            if not preserve_window and current.get('childWindowMinimized') is not True:
                if not minimized:
                    minimized = True
                    mutate('minimizeChildSession', current)
            else:
                verified = read_root(root)
                if (verified.get('childConnectedState') == 1
                        and verified.get('childSessionId') == child['windowsSessionId']
                        and (preserve_window or verified.get('childWindowMinimized') is True)):
                    return {'root': verified, 'child': child, 'rootReady': True, 'childReady': True,
                            'gameReady': child.get('automationState') == 'game_ready' and child.get('runtimeRunning') is True,
                            'childStartDispatched': dispatched,
                            'windowPolicy': 'preserve_existing' if preserve_window else 'minimized'}
        elif state in active_states:
            _child_start_fields(current, startup_mode, joining=True)
            following_launch = True
        elif not dispatched and not following_launch:
            if state not in ('idle', 'child_launch_dispatched', 'failed', 'connection_failed', 'cancelled'):
                raise ControlError(f'Unknown child startup state {state!r}; no recovery was dispatched.')
            # child_launch_dispatched means a past dispatch completed, not that a
            # launch is still active forever. This new explicit request may recover
            # a missing child through the server's serialized, process-aware start.
            fields = _child_start_fields(current, startup_mode)
            if _before_dispatch is not None:
                _before_dispatch(current)
            dispatched = True
            try:
                mutate('startChildSession', current, **fields)
            except ControlError:
                observed = read_root(root)
                appeared = select_child(observed, discover())
                if appeared is None and observed.get('automationState') in active_states:
                    _child_start_fields(observed, startup_mode, joining=True)
                if (observed.get('automationState') not in active_states
                        and not (appeared is not None and observed.get('childConnectedState') == 1)):
                    # An old completed-dispatch string alone cannot acknowledge an
                    # ambiguous request. Do not send it again or claim success.
                    raise
        time.sleep(0.5)
    raise ControlError('Child readiness timed out. Inspect root status and its RDP window; start was not replayed.')


def _game_runtime_ready(status):
    """Runtime attachment can precede lifecycle completion; a failure always wins over attachment."""
    if status.get('automationState') in ('failed', 'connection_failed', 'cancelled'):
        raise ControlError(status.get('automationError') or 'Game startup failed or was cancelled.')
    return status.get('automationState') == 'game_ready' and status.get('runtimeRunning') is True


def _control_endpoint_ready(status):
    """A replacement endpoint may be idle without attaching or launching a game."""
    if status.get('automationState') in ('failed', 'connection_failed', 'cancelled'):
        raise ControlError(status.get('automationError') or 'Replacement lifecycle failed or was cancelled.')
    return (status.get('uiStatus') == 'current' and status.get('taskRunning') is False
            and status.get('automationState') in ('idle', 'stopped', 'game_ready')
            and type(status.get('runtimeRunning')) is bool)


def start_game(child, timeout):
    """Join automatic game startup instead of dispatching a competing lifecycle action."""
    require_role(child, 'ChildSession')
    if child.get('runtimeRunning') is True and _game_runtime_ready(child):
        return child
    if child.get('automationState') != 'starting_game':
        _dispatch_start_or_join('startChildGame', child, ('starting_game', 'game_ready'))
    return wait_status(child, _game_runtime_ready, timeout)


def start_agent(child, timeout, enable_input=False, observation_profile=LEGACY_OBSERVATION_PROFILE,
                *, experimental_queued_step_applications=False):
    """Start the fixed TaskRunner-owned stream; both server and client must opt into input."""
    require_role(child, 'ChildSession')
    if type(enable_input) is not bool:
        raise ControlError('Agent input opt-in must be an explicit boolean.')
    if type(experimental_queued_step_applications) is not bool:
        raise ControlError('Experimental queued step applications require an explicit boolean.')
    if experimental_queued_step_applications and not enable_input:
        raise ControlError('Experimental queued step applications require explicit input opt-in.')
    observation_profile = _observation_profile(observation_profile)
    source_policy = _controller_source_policy(child) if enable_input else None
    if not _game_runtime_ready(child):
        raise ControlError('Run start-game and wait for runtime readiness before starting the agent.')
    # Joining this same mode is harmless; changing permissions requires an explicit
    # stop followed by start. Never upgrade a running observation-only task.
    if child.get('agentStreamRunning') is True:
        # Status does not expose this session permission; never claim it was upgraded or joined.
        if experimental_queued_step_applications:
            raise ControlError('Stop the current agent before explicitly starting experimental queued step applications.')
        if child.get('agentInputEnabled') is not enable_input:
            raise ControlError('Stop the current agent before changing its input permission.')
        if child.get('agentObservationProfile', LEGACY_OBSERVATION_PROFILE) != observation_profile:
            raise ControlError('Stop the current agent before changing its observation profile.')
    else:
        fields = {'enableInput': enable_input}
        if observation_profile != LEGACY_OBSERVATION_PROFILE:
            fields['observationProfile'] = observation_profile
        # Omitted/false preserves the exact ordinary request and does not enable the channel.
        if experimental_queued_step_applications:
            fields['experimentalQueuedStepApplications'] = True
        mutate('startAgentStream', child, **fields)

    def ready(current):
        require_role(current, 'ChildSession')
        if enable_input:
            _controller_source_unchanged(current, child, source_policy)
        state = current.get('agentStreamState')
        if state in ('failed', 'rejected', 'stopped', 'completed'):
            raise ControlError(current.get('agentStreamError') or f'Agent stream ended before readiness: {state}.')
        if current.get('agentStreamRunning') is True and current.get('agentInputEnabled') is not enable_input:
            raise ControlError('The running agent has a different input permission.')
        if (current.get('agentStreamRunning') is True
                and current.get('agentObservationProfile', LEGACY_OBSERVATION_PROFILE) != observation_profile):
            raise ControlError('The running agent has a different observation profile.')
        return state == 'listening' and current.get('agentStreamRunning') is True

    return wait_status(child, ready, timeout)


def stop_agent(child, timeout):
    """Drain only the service-owned agent; retain the child game/runtime and unrelated tasks."""
    mutate('stopAgentStream', child)
    return wait_status(child, lambda state: state.get('agentStreamRunning') is False, timeout)


def _validate_capture_readback(mode, readback_mode):
    """Explicit readback options are exact strings and belong only to the V2 backend."""
    if (mode != 'WindowsGraphicsCaptureV2' or not isinstance(readback_mode, str)
            or readback_mode not in READBACK_MODES):
        raise ControlError('Readback mode must be blocking or poll_single_v1 with WindowsGraphicsCaptureV2.')


def _readback_capability(status):
    """Distinguish a legacy endpoint from the exact supported selection/status contract."""
    if 'readbackVersion' not in status:
        return False
    if type(status['readbackVersion']) is not int or status['readbackVersion'] != 1:
        raise ControlError('Unsupported capture readback capability version.')
    modes = status.get('readbackModes')
    if not isinstance(modes, list) or not modes or any(not isinstance(value, str) for value in modes):
        raise ControlError('Capture readback capabilities are missing or malformed.')
    return True


def _validate_capture_option(mode, name, value, choices):
    """Explicit capture options are exact strings for the V2 backend only."""
    if mode != 'WindowsGraphicsCaptureV2' or not isinstance(value, str) or value not in choices:
        raise ControlError(f'{name} must be an exact supported option with WindowsGraphicsCaptureV2.')


def _capture_options_capability(status):
    """Pin the supported option lists; omission alone identifies a legacy endpoint."""
    if 'captureOptionsVersion' not in status:
        return None
    if type(status['captureOptionsVersion']) is not int or status['captureOptionsVersion'] != 1:
        raise ControlError('Unsupported capture options capability version.')
    result = []
    for name in ('sourceRetentions', 'conversionModes'):
        values = status.get(name)
        if (not isinstance(values, list) or not values or any(not isinstance(value, str) for value in values)
                or len(set(values)) != len(values)):
            raise ControlError('Capture option capabilities are missing or malformed.')
        result.append(tuple(values))
    return tuple(result)


def _validate_desktop_dc_policy(mode, value):
    """Host acquisition is a distinct, explicit policy; never coerce a WGC option."""
    if mode != 'DesktopDc' or not isinstance(value, str) or value not in DESKTOP_DC_SOURCE_POLICIES:
        raise ControlError('Desktop DC source policy requires DesktopDc and an exact supported policy name.')


def _desktop_dc_capability(status):
    """Require the exact versioned host-source contract, leaving legacy endpoints usable."""
    if 'desktopDcSourcePolicyVersion' not in status:
        return None
    if (type(status['desktopDcSourcePolicyVersion']) is not int
            or status['desktopDcSourcePolicyVersion'] != 1
            or status.get('desktopDcSourcePolicies') != list(DESKTOP_DC_SOURCE_POLICIES)):
        raise ControlError('Unsupported or malformed desktop DC source policy capability.')
    return DESKTOP_DC_SOURCE_POLICIES


def set_capture_mode(child, mode, timeout, readback_mode=None, *,
                     source_retention=_CAPTURE_OPTION_UNSET, conversion=_CAPTURE_OPTION_UNSET,
                     desktop_dc_source_policy=_CAPTURE_OPTION_UNSET):
    """Reattach an idle child once, then verify configured and actual capture modes."""
    require_role(child, 'ChildSession')
    if mode not in CAPTURE_MODES:
        raise ControlError('Capture mode must be an exact supported backend name.')
    if readback_mode is not None:
        _validate_capture_readback(mode, readback_mode)
    if desktop_dc_source_policy is not _CAPTURE_OPTION_UNSET:
        _validate_desktop_dc_policy(mode, desktop_dc_source_policy)
    desktop_capability = _desktop_dc_capability(child)
    if desktop_capability is None and (mode == 'DesktopDc' or child.get('captureMode') == 'DesktopDc'):
        raise ControlError('This child does not advertise desktop DC source policies; update it first.')
    saved_desktop_policy = child.get('configuredDesktopDcSourcePolicy')
    requested_desktop_policy = (saved_desktop_policy if desktop_dc_source_policy is _CAPTURE_OPTION_UNSET
                                else desktop_dc_source_policy)
    if desktop_capability is not None and saved_desktop_policy not in desktop_capability:
        raise ControlError('The saved desktop DC source policy is missing or unsupported.')
    options = (('sourceRetention', source_retention, SOURCE_RETENTIONS, 'configuredSourceRetention', 'effectiveSourceRetention'),
               ('conversion', conversion, CONVERSION_MODES, 'configuredConversion', 'effectiveConversion'))
    for name, value, choices, _, _ in options:
        if value is not _CAPTURE_OPTION_UNSET:
            _validate_capture_option(mode, name, value, choices)
    option_capability = _capture_options_capability(child)
    expected_options = {}
    for index, (name, value, choices, configured, effective) in enumerate(options):
        if option_capability is None:
            if value is not _CAPTURE_OPTION_UNSET:
                raise ControlError('This child does not advertise capture options; update it first.')
        else:
            saved = child.get(configured)
            if not isinstance(saved, str) or saved not in choices or saved not in option_capability[index]:
                raise ControlError('The saved capture option is missing, malformed or not advertised.')
            requested_option = saved if value is _CAPTURE_OPTION_UNSET else value
            if requested_option not in option_capability[index]:
                raise ControlError('The requested capture option is not advertised by this child.')
            expected_options[configured] = requested_option
            expected_options[effective] = requested_option if mode == 'WindowsGraphicsCaptureV2' else None
    capable = _readback_capability(child)
    # Desktop DC leaves all dormant WGC selections intact. Legacy backends retain
    # their existing omitted-readback => blocking behavior.
    requested = (child.get('configuredReadbackMode') if mode == 'DesktopDc'
                 else 'blocking' if readback_mode is None else readback_mode)
    if mode == 'DesktopDc' and (not capable or option_capability is None):
        raise ControlError('Desktop DC requires the saved WGC option capabilities for reattachment verification.')
    if mode == 'DesktopDc' and requested not in READBACK_MODES:
        raise ControlError('The saved WGC readback mode is missing or unsupported.')
    if readback_mode is not None and not capable:
        raise ControlError('This child does not advertise capture readback selection; update it first.')
    if capable and requested not in child['readbackModes']:
        raise ControlError('The requested readback mode is not advertised by this child.')
    if child.get('taskRunning') is not False or child.get('agentStreamRunning') is True:
        raise ControlError('Stop active tasks and wait for lifecycle completion before changing capture mode.')
    fields = {'captureMode': mode}
    if readback_mode is not None:
        fields['readbackMode'] = readback_mode
    for name, value, _, _, _ in options:
        if value is not _CAPTURE_OPTION_UNSET:
            fields[name] = value
    if desktop_dc_source_policy is not _CAPTURE_OPTION_UNSET:
        fields['desktopDcSourcePolicy'] = desktop_dc_source_policy
    # Omitted selectors stay absent on the wire; only Desktop DC preserves dormant readback.
    # An uncertain acknowledgment is surfaced by mutate; this function never retries it.
    def ready(current):
        require_role(current, 'ChildSession')
        if option_capability is not None and _capture_options_capability(current) != option_capability:
            raise ControlError('Capture option capabilities changed during reattachment.')
        if desktop_capability is not None:
            if _desktop_dc_capability(current) != desktop_capability:
                raise ControlError('Desktop DC source policy capabilities changed during reattachment.')
            if capable and (not _readback_capability(current) or current.get('readbackModes') != child['readbackModes']):
                raise ControlError('Capture readback capabilities changed during reattachment.')
            # ExternalControlStatusCollector omits UI-derived settings when its
            # bounded read fails. This exact degraded shape permits only further
            # read-only polling, never readiness or a second mutation.
            if current.get('automationState') == 'unresponsive':
                setting_fields = ('configuredDesktopDcSourcePolicy', 'effectiveDesktopDcSourcePolicy',
                                  'configuredReadbackMode', 'effectiveReadbackMode',
                                  'configuredSourceRetention', 'effectiveSourceRetention',
                                  'configuredConversion', 'effectiveConversion')
                if (current.get('uiStatus') not in ('timeout', 'cancelled', 'unavailable', 'failed')
                        or current.get('runtimeRunning') is not False or current.get('taskRunning') is not True
                        or current.get('captureMode') != '' or current.get('agentStreamRunning') is True
                        or any(current.get(name) is not None for name in setting_fields)):
                    raise ControlError('Malformed unavailable capture status during reattachment.')
                return False
            # Acknowledgment and in-progress status may precede configuration or
            # attachment, but may not introduce a third policy or a running agent.
            if (current.get('configuredDesktopDcSourcePolicy') not in (saved_desktop_policy, requested_desktop_policy)
                    or current.get('effectiveDesktopDcSourcePolicy') not in (None, saved_desktop_policy, requested_desktop_policy)
                    or current.get('agentStreamRunning') is True):
                raise ControlError('Desktop DC source policy changed unexpectedly during reattachment.')
        if not _game_runtime_ready(current) or current.get('taskRunning') is not False:
            return False
        if current.get('captureMode') != mode:
            raise ControlError('Capture reattachment completed with a different selected backend.')
        if capable:
            if not _readback_capability(current) or requested not in current['readbackModes']:
                raise ControlError('Capture readback capabilities changed during reattachment.')
            if current.get('configuredReadbackMode') != requested:
                raise ControlError('Capture reattachment completed with a different saved readback mode.')
            expected = requested if mode == 'WindowsGraphicsCaptureV2' else None
            if current.get('effectiveReadbackMode') != expected:
                raise ControlError('Capture reattachment completed without the expected attached readback mode.')
        if option_capability is not None:
            if current.get('agentStreamRunning') is True:
                raise ControlError('An agent started before capture reattachment completed.')
            for name, expected in expected_options.items():
                if current.get(name) != expected:
                    raise ControlError('Capture reattachment completed with a different saved or effective capture option.')
        if desktop_capability is not None:
            expected = requested_desktop_policy if mode == 'DesktopDc' else None
            if (current.get('configuredDesktopDcSourcePolicy') != requested_desktop_policy
                    or current.get('effectiveDesktopDcSourcePolicy') != expected):
                raise ControlError('Capture reattachment completed with a different saved or effective desktop DC policy.')
        return True

    acknowledgment = mutate('setCaptureMode', child, **fields)
    if desktop_capability is not None:
        # Validate the actual acknowledgment too; a bad/uncertain reply never
        # triggers another mutation, even if a later status could look healthy.
        if not isinstance(acknowledgment, dict):
            raise ControlError('Capture reattachment acknowledgment did not include status.')
        ready(acknowledgment)
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


def _navigation_reset_diagnostics(terminal):
    """Fetch evidence once, retaining the original terminal result if the pinned read cannot be verified."""
    result = terminal['navigationReset']
    version = result.get('verificationDiagnosticsVersion')
    if 'verificationDiagnosticsVersion' not in result:
        return terminal
    try:
        if type(version) is not int or version != 1:
            raise ControlError('Unsupported navigation-reset diagnostics version.')
        response = exchange('navigationResetDiagnostics', terminal['processId'], terminal['windowsSessionId'],
                            nonce=terminal['instanceNonce'], fields={'navigationResetRunId': result['runId']})
        require_role(response, 'ChildSession')
        if any(response.get(key) != terminal.get(key)
               for key in ('processId', 'windowsSessionId', 'instanceNonce')):
            raise ControlError('The pinned navigation-reset process instance changed during diagnostics.')
        diagnostic_result = response.get('navigationReset')
        if (not isinstance(diagnostic_result, dict)
                or type(diagnostic_result.get('verificationDiagnosticsVersion')) is not int
                or diagnostic_result.get('verificationDiagnosticsVersion') != 1
                or {key: value for key, value in diagnostic_result.items() if key != 'verificationDiagnostics'}
                != {key: value for key, value in result.items() if key != 'verificationDiagnostics'}):
            raise ControlError('Navigation-reset diagnostics do not match the pinned terminal result.')
        diagnostics = diagnostic_result.get('verificationDiagnostics')
        if not isinstance(diagnostics, list) or len(diagnostics) > 15:
            raise ControlError('Navigation-reset diagnostics must contain at most fifteen observations.')
        for attempt, observation in enumerate(diagnostics, 1):
            if (not isinstance(observation, dict) or type(observation.get('attempt')) is not int
                    or observation['attempt'] != attempt or not isinstance(observation.get('sample'), dict)
                    or not isinstance(observation.get('reason'), str) or not observation['reason']):
                raise ControlError('Navigation-reset diagnostics contain an invalid observation.')
        # Only diagnostics are merged: current runtime/UI changes must not replace
        # the terminal operation snapshot that the polling path actually verified.
        return {**terminal, 'navigationReset': {**result, 'verificationDiagnostics': diagnostics}}
    except (ControlError, OSError, ValueError) as error:
        raise NavigationResetError('Navigation-reset diagnostics could not be verified: ' + str(error), terminal) from error


def reset_navigation(child, yaw_degrees, timeout, capture_policy='shared'):
    """Start the fixed navigation reset once and await that exact server-owned run."""
    require_role(child, 'ChildSession')
    _validate_navigation_yaw(yaw_degrees)
    source_policy = _controller_source_policy(child)
    if not _game_runtime_ready(child):
        raise ControlError('Run start-game and wait for runtime readiness before resetting navigation.')
    if child.get('taskRunning') is not False or child.get('agentStreamRunning') is not False:
        raise ControlError('Stop the agent and all active tasks before resetting navigation.')
    previous = child.get('navigationReset')
    if isinstance(previous, dict) and previous.get('state') == 'running':
        raise ControlError('A navigation reset is already running; query its status instead of starting another.')
    if not isinstance(capture_policy, str) or capture_policy not in ('shared', 'task_owned_timer'):
        raise ControlError('Reset capture policy must be exactly shared or task_owned_timer.')
    capture_policies = previous.get('capturePolicies') if isinstance(previous, dict) else None
    if isinstance(previous, dict) and 'capturePolicies' in previous and (
            not isinstance(capture_policies, list) or any(not isinstance(value, str) for value in capture_policies)
            or capture_policy not in capture_policies):
        raise ControlError('This child does not advertise the requested reset capture policy.')
    if capture_policy != 'shared' and capture_policies is None:
        raise ControlError('This child does not advertise post-teleport timer capture isolation; upgrade before requesting it.')
    fields = {'targetYawDegrees': yaw_degrees}
    if capture_policies is not None:
        fields['capturePolicy'] = capture_policy

    # A lost start response is ambiguous. Unlike startup joins, this operation
    # must never infer ownership from a later run or resend movement work.
    admitted = mutate('startNavigationReset', child, **fields)
    operation = admitted.get('navigationReset')
    run_id = operation.get('runId') if isinstance(operation, dict) else None
    # Idle status has no top-level game identity. Only this admitted owner can bind a host reset.
    game_pid = operation.get('gameProcessId') if isinstance(operation, dict) else None
    if source_policy is not None and (type(game_pid) is not int or game_pid <= 0):
        raise ControlError('Host navigation reset did not return a positive game owner; do not replay the start.')
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
        _controller_source_unchanged(current, child, source_policy, result)
        if source_policy is not None and (type(result.get('gameProcessId')) is not int
                or result['gameProcessId'] != game_pid):
            raise ControlError('The admitted host navigation-reset game owner changed; do not replay the request.')
        state = result.get('state')
        if state not in ('running', 'completed', 'failed', 'cancelled'):
            raise ControlError(f'Navigation reset has an unexpected state: {state}.')
        if (result.get('profileId') != 'mondstadt-city-10'
                or _validate_navigation_yaw(result.get('targetYawDegrees')) != yaw_degrees):
            raise ControlError('Navigation reset reports a different profile or target yaw.')
        if capture_policies is not None and (result.get('capturePolicy') != capture_policy
                or result.get('capturePolicies') != capture_policies):
            raise NavigationResetError('The selected reset capture policy changed while waiting.', current)
        if capture_policies is None and result.get('capturePolicy', 'shared') != 'shared':
            raise NavigationResetError('The legacy reset did not retain shared capture.', current)
        if state in ('failed', 'cancelled'):
            if (type(result.get('verificationDiagnosticsVersion')) is int
                    and result['verificationDiagnosticsVersion'] == 1 and current.get('taskRunning') is not False):
                # The terminal owner snapshot can become visible just before its
                # cleanup task completes. Wait before the one diagnostics fetch.
                return False
            terminal = _navigation_reset_diagnostics(current)
            raise NavigationResetError(result.get('error') or f'Navigation reset {state}.', terminal)
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
        if source_policy is not None:
            _host_pose_sequence(samples)
        if current.get('agentStreamRunning') is not False:
            raise ControlError('An agent stream is active or unknown while the navigation reset completes.')
        return _game_runtime_ready(current) and current.get('taskRunning') is False

    if completed(admitted):
        return _navigation_reset_diagnostics(admitted)
    return _navigation_reset_diagnostics(wait_status(child, completed, timeout))


def _baseline_finite(value):
    """Reject booleans, nonfinite values and oversized JSON integers without coercion."""
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _controller_source_policy(status):
    """Admit host control only through the exact active DesktopDc policy contract."""
    if status.get('captureMode') != 'DesktopDc':
        return None
    if (_desktop_dc_capability(status) is None
            or status.get('configuredDesktopDcSourcePolicy') != 'host-acquisition-v1'
            or status.get('effectiveDesktopDcSourcePolicy') != 'host-acquisition-v1'
            or any(status.get(key) is not None for key in
                   ('effectiveReadbackMode', 'effectiveSourceRetention', 'effectiveConversion'))):
        raise ControlError('DesktopDc control requires the exact active host-acquisition-v1 policy.')
    return 'host-acquisition-v1'


def _controller_source_unchanged(current, child, policy, operation=None):
    """Keep source authority fixed; native polling loops pin the admitted owner game separately."""
    if _controller_source_policy(current) != policy:
        raise ControlError('The controller source policy changed while waiting; do not replay the request.')
    if operation is not None and operation.get('sourcePolicy') != policy:
        raise ControlError('The native owner does not retain the selected source policy.')
    if policy is not None and operation is not None:
        if (type(operation.get('gameProcessId')) is not int or operation['gameProcessId'] <= 0
                or operation.get('readbackMode') is not None):
            raise ControlError('Host native evidence lacks a positive game owner or claims a WGC readback selection.')


def _host_pose_source(sample):
    """Validate the raw STJ host record without inventing a WGC/render timestamp."""
    host = sample.get('hostSnapshot') if isinstance(sample, dict) else None
    names = ('CaptureEpoch', 'SnapshotId', 'StartedAtStopwatchTicks', 'CompletedAtStopwatchTicks', 'ClockFrequency')
    if (not isinstance(host, dict) or set(host) != set(names)
            or sample.get('sourceKind') != 'host-acquisition-v1'
            or any(key in sample for key in ('sourceTimestamp100ns', 'acquiredAtStopwatchTicks'))
            or not isinstance(sample.get('sourceEpoch'), str)
            or re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', sample['sourceEpoch']) is None
            or sample['sourceEpoch'].replace('-', '') == '0' * 32
            or host['CaptureEpoch'] != sample['sourceEpoch']
            or any(type(host.get(key)) is not int or not 0 < host[key] <= 2**63 - 1 for key in names[1:])
            or host['CompletedAtStopwatchTicks'] < host['StartedAtStopwatchTicks']):
        raise ControlError('Native host pose has invalid, mixed or unbound snapshot evidence.')
    return host


def _host_pose_sequence(samples):
    """Check successful distinct snapshots; native numerical/age gates remain server-owned."""
    previous = None
    for sample in samples:
        current = _host_pose_source(sample)
        if previous is not None and (current['CaptureEpoch'] != previous['CaptureEpoch']
                or current['ClockFrequency'] != previous['ClockFrequency']
                or any(current[key] <= previous[key] for key in
                       ('SnapshotId', 'StartedAtStopwatchTicks', 'CompletedAtStopwatchTicks'))):
            raise ControlError('Successful native host snapshots changed identity or did not strictly advance.')
        previous = current


def _baseline_pose(sample, source_policy=None):
    """Validate finite source-tagged evidence; the server owns its numerical acceptance gates."""
    numeric = ('x', 'y', 'yawDegrees', 'positionConfidence', 'yawConfidence', 'sourceAgeMs',
               'targetHeadingDegrees', 'distanceToEnd', 'projection', 'crossTrack')
    if (not isinstance(sample, dict)
            or any(not _baseline_finite(sample.get(key)) for key in numeric)
            or any(not isinstance(sample.get(key), str) or not sample[key]
                   for key in ('capturedAtUtc', 'sourceEpoch', 'layerId'))
            or source_policy is None and any(type(sample.get(key)) is not int or sample[key] < 0
                   for key in ('sourceTimestamp100ns', 'acquiredAtStopwatchTicks'))):
        raise ControlError('Navigation baseline contains an invalid source-tagged pose.')
    if source_policy == 'host-acquisition-v1':
        _host_pose_source(sample)
    elif source_policy is not None or sample.get('hostSnapshot') is not None or sample.get('sourceKind') is not None:
        raise ControlError('A WGC pose cannot carry host source authority.')
    motion = sample.get('motion')
    if (not isinstance(motion, dict) or motion.get('status') != 'normal'
            or motion.get('method') != 'native_key_tip_templates_v1'
            or motion.get('spaceKeyMatched') is not False or type(motion.get('xKeyMatched')) is not bool
            or not _baseline_finite(motion.get('recognitionMs')) or motion['recognitionMs'] < 0):
        raise ControlError('Navigation baseline pose lacks its declared native normal-motion evidence.')


def _navigation_baseline_result(terminal, *, host_continuation=False):
    """Read a single pinned result, merging only evidence after exact compact-status equality."""
    operation = terminal['navigationBaseline']
    try:
        source_policy = _controller_source_policy(terminal)
        _controller_source_unchanged(terminal, terminal, source_policy, operation)
        response = exchange('navigationBaselineResult', terminal['processId'], terminal['windowsSessionId'],
                            nonce=terminal['instanceNonce'], fields={'navigationBaselineRunId': operation['runId']})
        require_role(response, 'ChildSession')
        if any(response.get(key) != terminal.get(key) for key in ('processId', 'windowsSessionId', 'instanceNonce')):
            raise ControlError('The pinned navigation-baseline instance changed during result retrieval.')
        if host_continuation:
            _baseline_host_identity(response, terminal)
        full = response.get('navigationBaseline')
        if (not isinstance(full, dict)
                or type(full.get('resultVersion')) is not int or full['resultVersion'] != 1
                or type(full.get('observationCount')) is not int or type(full.get('evidenceComplete')) is not bool
                or {key: value for key, value in full.items() if key != 'result'}
                != {key: value for key, value in operation.items() if key != 'result'}):
            raise ControlError('Navigation-baseline evidence does not match the pinned terminal result.')
        result = full.get('result')
        if (not isinstance(result, dict) or type(result.get('verified')) is not bool
                or not isinstance(result.get('phase'), str) or not result['phase']
                or not _baseline_finite(result.get('elapsedMs')) or result['elapsedMs'] < 0
                or type(result.get('observationCount')) is not int
                or result['observationCount'] != operation['observationCount']
                or any(result.get(key) is not None and not isinstance(result[key], str)
                       for key in ('error', 'inputReleaseError'))):
            raise ControlError('Navigation baseline has an invalid terminal result summary.')
        if result.get('sourcePolicy') != source_policy:
            raise ControlError('The full baseline result has a different source policy.')
        samples, verification = result.get('samples'), result.get('verificationSamples')
        if (not isinstance(samples, list) or len(samples) not in (0, 3)
                or not isinstance(verification, list) or len(verification) > 3):
            raise ControlError('Navigation baseline has an invalid final-pose count.')
        for sample in [*samples, *verification]:
            _baseline_pose(sample, source_policy)
        if result.get('initialSample') is not None:
            _baseline_pose(result['initialSample'], source_policy)
        evidence = result.get('evidence')
        if evidence is not None:
            if (not isinstance(evidence, dict) or evidence.get('sourcePolicy') != source_policy
                    or source_policy is not None and evidence.get('readbackMode') is not None):
                raise ControlError('The baseline artifact evidence has a different source policy.')
            if not isinstance(evidence, dict) or type(evidence.get('complete')) is not bool:
                raise ControlError('Navigation baseline has an invalid evidence summary.')
            for stem in ('journal', 'initialImage', 'finalImage'):
                path, digest = evidence.get(stem + 'Path'), evidence.get(stem + 'Sha256')
                if (path is not None and (not isinstance(path, str) or not path)
                        or digest is not None and (not isinstance(digest, str)
                            or re.fullmatch(r'[0-9a-fA-F]{64}', digest) is None)):
                    raise ControlError('Navigation baseline has an invalid artifact reference or hash.')
        if operation['state'] == 'completed':
            if (result['verified'] is not True or operation.get('error') is not None
                    or result.get('error') is not None or result.get('inputReleaseError') is not None
                    or operation['evidenceComplete'] is not True or not evidence or evidence['complete'] is not True
                    or len(samples) != 3 or verification != samples or result.get('initialSample') is None
                    or any(not evidence.get(stem + 'Path') or not evidence.get(stem + 'Sha256')
                           for stem in ('journal', 'initialImage', 'finalImage'))):
                raise ControlError('Completed baseline lacks verified final poses, successful release, or complete evidence.')
            if source_policy is not None:
                _host_pose_sequence([result['initialSample'], *samples])
        # Runtime/UI fields may change after completion. Preserve the exact terminal
        # operation that was polled; do not replace it with an unrelated later status.
        return {**terminal, 'navigationBaseline': {**operation, 'result': result}}
    except (ControlError, OSError, ValueError, KeyError) as error:
        raise NavigationBaselineError('Navigation-baseline result could not be verified: ' + str(error), terminal) from error


def _baseline_fixed_two_leg_result(result, *, reverse=False):
    """Check fixed asset identities; numerical route acceptance remains server-owned."""
    legs, waypoint = result.get('legs'), result.get('waypoint')
    expected = ((3, 2), (2, 1)) if reverse else ((1, 2), (2, 3))
    if (result.get('routeVersion') != 1 or type(result.get('routeVersion')) is not int
            or not isinstance(legs, list) or len(legs) != 2
            or not isinstance(waypoint, dict) or waypoint.get('outcome') != 'completed'
            or waypoint.get('error') is not None or not isinstance(waypoint.get('samples'), list)
            or len(waypoint['samples']) != 3 or not isinstance(waypoint.get('anchor'), dict)):
        raise ControlError('Fixed two-leg result lacks its completed checkpoint and distinct next-leg anchor.')
    for index, (leg, assets) in enumerate(zip(legs, expected), 1):
        if (not isinstance(leg, dict) or leg.get('outcome') != 'completed' or leg.get('error') is not None
                or any(type(leg.get(key)) is not int for key in ('legIndex', 'startPointId', 'endPointId'))
                or (leg['legIndex'], leg['startPointId'], leg['endPointId']) != (index, *assets)):
            raise ControlError('Fixed two-leg result has a different asset order or incomplete leg.')
    for sample in [*waypoint['samples'], waypoint['anchor']]:
        _baseline_pose(sample)


def _baseline_allows_predecessor(requested, predecessor):
    """Fixed courtyard direction pairs; old two-leg reverse admission is unchanged."""
    if requested == 'mondstadt-city-reverse-two-legs-v1':
        return predecessor == 'mondstadt-city-two-legs-v1'
    if requested == 'mondstadt-city-courtyard-return-v1':
        return predecessor in ('mondstadt-city-leg-1-v1', 'mondstadt-city-courtyard-forward-v1')
    return requested == 'mondstadt-city-courtyard-forward-v1' and predecessor == 'mondstadt-city-courtyard-return-v1'


def _baseline_fixed_courtyard_result(result):
    """One fixed upper-level segment, no waypoint; numerical acceptance remains server-owned."""
    expected = (2, 1) if result.get('profileId') == 'mondstadt-city-courtyard-return-v1' else (1, 2)
    legs = result.get('legs')
    if (type(result.get('routeVersion')) is not int or result['routeVersion'] != 1
            or not isinstance(legs, list) or len(legs) != 1 or result.get('waypoint') is not None):
        raise ControlError('Courtyard continuation lacks its one fixed leg and no-waypoint shape.')
    leg = legs[0]
    if (not isinstance(leg, dict) or leg.get('outcome') != 'completed' or leg.get('error') is not None
            or any(type(leg.get(k)) is not int for k in ('legIndex', 'startPointId', 'endPointId'))
            or (leg['legIndex'], leg['startPointId'], leg['endPointId']) != (1, *expected)):
        raise ControlError('Courtyard continuation has the wrong asset order or incomplete leg.')
    if any(sample.get('legIndex') != 1 for sample in [result['initialSample'], *result['samples']]):
        raise ControlError('Courtyard continuation has an inconsistent pose leg identity.')


def _baseline_fixed_route_result(result):
    """Check the exact predecessor route shape without recursively loading ancestors."""
    profile = result.get('profileId')
    if profile == 'mondstadt-city-leg-1-v1':
        if result.get('routeVersion') is not None or result.get('legs') != [] or result.get('waypoint') is not None:
            raise ControlError('The ordinary short prerequisite has a different route shape.')
    elif profile in ('mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1'):
        _baseline_fixed_courtyard_result(result)
    else:
        _baseline_fixed_two_leg_result(result, reverse=profile == 'mondstadt-city-reverse-two-legs-v1')

def _baseline_host_identity(current, child):
    """Pin the observable host policy/build/path; binary verification remains the server/helper's job."""
    for status in (child, current):
        operation = status.get('navigationBaseline')
        digest, directory = status.get('assemblySha256'), status.get('appDirectory')
        if (not isinstance(operation, dict) or _controller_source_policy(status) != 'host-acquisition-v1'
                or type(operation.get('hostEndpointContinuationVersion')) is not int
                or operation['hostEndpointContinuationVersion'] != 1
                or type(operation.get('endpointContinuationVersion')) is not int
                or operation['endpointContinuationVersion'] != 2
                or not isinstance(digest, str) or re.fullmatch(r'[0-9a-fA-F]{64}', digest) is None
                or not isinstance(directory, str) or not directory
                or operation.get('sourcePolicy') != 'host-acquisition-v1'
                or operation.get('readbackMode') is not None or operation.get('shadowCapture') is not None):
            raise ControlError('Host continuation requires its exact policy, build and compact capability.')
        reference = operation.get('continuation')
        if reference is not None and (not isinstance(reference, dict)
                or set(reference) != {'version', 'predecessorRunId', 'predecessorProfileId'}
                or type(reference.get('version')) is not int or reference['version'] != 2):
            raise ControlError('Host continuation requires the exact typed compact reference2.')
        _controller_source_unchanged(status, child, 'host-acquisition-v1', operation)
    if (current['assemblySha256'].lower() != child['assemblySha256'].lower()
            or current['appDirectory'] != child['appDirectory']):
        raise ControlError('The host continuation build or application path changed.')


def _baseline_host_floor(source):
    """Read the actual typed-link converter shape without manufacturing WGC clocks."""
    if (not isinstance(source, dict) or set(source) != {'kind', 'hostSnapshot'}
            or source['kind'] != 'host-acquisition-v1' or not isinstance(source['hostSnapshot'], dict)):
        raise ControlError('Host continuation lacks a typed host acquisition floor.')
    host = source['hostSnapshot']
    return _host_pose_source(dict(sourceKind=source['kind'], sourceEpoch=host.get('CaptureEpoch'), hostSnapshot=host))


def _baseline_host_start_after_floor(result, floor):
    """A successful continued start must strictly advance the retained host snapshot in both clocks."""
    start = _host_pose_source(result.get('initialSample'))
    if (any(start[key] != floor[key] for key in ('CaptureEpoch', 'ClockFrequency'))
            or any(start[key] <= floor[key] for key in
                   ('SnapshotId', 'StartedAtStopwatchTicks', 'CompletedAtStopwatchTicks'))):
        raise ControlError('The continued host start did not strictly advance the predecessor source floor.')


def _baseline_continuation_projection(link, capability_version, host_capability=None):
    """Project WGC full1 or advertised host full2 to the existing exact compact reference2."""
    if type(capability_version) is not int or capability_version not in (1, 2):
        raise ControlError('Unsupported endpoint-continuation status contract.')
    expected_full = 2 if host_capability is not None else 1
    if host_capability is not None and (type(host_capability) is not int or host_capability != 1 or capability_version != 2):
        raise ControlError('Unsupported host endpoint-continuation contract.')
    if link is None:
        return None
    if not isinstance(link, dict) or type(link.get('version')) is not int or link['version'] != expected_full:
        raise ControlError('The dedicated continuation proof has a different full-link version.')
    if capability_version == 1:
        return link
    return dict(version=2, predecessorRunId=link.get('predecessorRunId'),
                predecessorProfileId=link.get('predecessorProfileId'))


def _baseline_continuation_identity(link, child, current):
    """Observable identity joins; runtime and exact process-start values remain server claims."""
    operation = current.get('navigationBaseline')
    host = _controller_source_policy(child) is not None
    if host:
        _baseline_host_identity(current, child)
    if (not isinstance(link, dict) or not isinstance(operation, dict)
            or type(link.get('version')) is not int or link['version'] != (2 if host else 1)
            or link.get('physicalInputAcknowledged') is not False
            or link.get('childNonce') != child['instanceNonce']
            or any(type(link.get(key)) is not int or link[key] <= 0 for key in
                   ('childProcessId', 'windowsSessionId', 'gameProcessId',
                    'gameStartedAtUtcTicks', 'predecessorCleanupReturnedAtTicks'))
            or link['childProcessId'] != child['processId'] or link['windowsSessionId'] != child['windowsSessionId']
            or link['gameProcessId'] != child['navigationBaseline']['gameProcessId']
            or operation.get('gameProcessId') != link['gameProcessId']
            or link.get('readbackMode') != child.get('effectiveReadbackMode')
            or current.get('effectiveReadbackMode') != child.get('effectiveReadbackMode')
            or current.get('captureMode') != child.get('captureMode')
            or not isinstance(link.get('captureType'), str) or not link['captureType']
            or len(link['captureType']) > 512):
        raise ControlError('Continuation proof does not match the pinned child, game and mode.')
    if host:
        evidence = link.get('predecessorEvidence')
        if (link.get('sourcePolicy') != 'host-acquisition-v1'
                or link.get('captureType') != 'Fischless.GameCapture.DesktopDc.DesktopDcCapture'
                or link.get('childAssemblySha256') != child['assemblySha256'].lower()
                or not isinstance(evidence, dict) or evidence.get('complete') is not True
                or evidence.get('sourcePolicy') != 'host-acquisition-v1'
                or evidence.get('readbackMode') is not None or evidence.get('shadowCapture') is not None):
            raise ControlError('Host continuation proof changed its typed source, build or evidence policy.')
        _baseline_host_floor(link.get('predecessorFinalSource'))
    try:
        runtime_identity = uuid.UUID(link['runtimeIdentity'])
        if runtime_identity.int == 0:
            raise ValueError('empty runtime identity')
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ControlError('Continuation proof lacks its server runtime identity.') from error


def _baseline_continuation_preflight(child, predecessor, *, requested_profile='mondstadt-city-reverse-two-legs-v1', timing_contract='v4'):
    """Read the exact opposite-direction predecessor before the one mutation; never reserve it client-side."""
    if timing_contract not in ('v4', 'v5'):
        raise ControlError('Continuation requires explicit v4 or v5.')
    old = child['navigationBaseline']
    host = _controller_source_policy(child) is not None
    if host:
        _baseline_host_identity(child, child)
        if requested_profile not in ('mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1'):
            raise ControlError('Host continuation supports only the fixed courtyard direction pair.')
    if (not isinstance(predecessor, str) or re.fullmatch(r'[0-9a-fA-F]{32}', predecessor) is None
            or int(predecessor, 16) == 0 or old.get('runId') != predecessor
            or old.get('state') != 'completed' or not _baseline_allows_predecessor(requested_profile, old.get('profileId'))
            or type(old.get('endpointContinuationVersion')) is not int or old['endpointContinuationVersion'] not in (1, 2)
            or old.get('timingContract') != timing_contract or old.get('capturePolicy') != 'task_owned_timer'
            or not host and (not _readback_capability(child)
                or child.get('effectiveReadbackMode') not in ('blocking', 'poll_single_v1'))):
        raise ControlError('Continuation requires the exact completed opposite-direction predecessor and advertised capability.')
    for selected in (requested_profile, old.get('profileId')):
        if selected in ('mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1') and selected not in (old.get('routeProfiles') or []):
            raise ControlError('This child does not advertise the exact courtyard continuation.')
    prior_status = _navigation_baseline_result(child, host_continuation=True) if host else _navigation_baseline_result(child)
    prior = prior_status['navigationBaseline']['result']
    if (prior.get('profileId') != old['profileId'] or prior.get('timingContract') != timing_contract
            or prior.get('capturePolicy') != 'task_owned_timer'
            or prior['evidence'].get('readbackMode') != child.get('effectiveReadbackMode')
            or _baseline_continuation_projection(prior.get('continuation'), old['endpointContinuationVersion'],
                old.get('hostEndpointContinuationVersion') if host else None) != old.get('continuation')):
        raise ControlError('Predecessor result profile, mode or provenance is incompatible with continuation.')
    lineage = prior.get('continuation')
    if prior['profileId'] in ('mondstadt-city-leg-1-v1', 'mondstadt-city-two-legs-v1'):
        if lineage is not None:
            raise ControlError('The ordinary first forward result must not claim continuation provenance.')
    else:
        _baseline_continuation_identity(lineage, child, child)
        if host:
            _baseline_host_start_after_floor(prior, _baseline_host_floor(lineage['predecessorFinalSource']))
        ancestor = lineage.get('predecessorRunId')
        if (not _baseline_allows_predecessor(prior['profileId'], lineage.get('predecessorProfileId'))
                or not isinstance(ancestor, str) or re.fullmatch(r'[0-9a-fA-F]{32}', ancestor) is None
                or int(ancestor, 16) == 0 or ancestor == predecessor):
            raise ControlError('The retained continuation predecessor has incompatible provenance.')
        # Only the latest retained result is fetched. Its earlier link is a bounded
        # server claim, not a recursively verified history or physical acknowledgment.
    _baseline_fixed_route_result(prior)
    # Native route verification is independent of archive retirement. A CLI continuation
    # cannot treat a completed native owner as a successful selected capture predecessor.
    archive = prior['evidence'].get('shadowCapture')
    if old.get('shadowCapture') is not None:
        if (old['shadowCapture'] != SHADOW_CAPTURE_MODE or type(old.get('shadowCaptureVersion')) is not int
                or old['shadowCaptureVersion'] != 1 or old.get('shadowCaptureModes') != [SHADOW_CAPTURE_MODE]):
            raise ControlError('The predecessor selected an unsupported shadow archive contract.')
        _require_shadow_capture(archive, prior['evidence'])
    elif archive is not None:
        raise ControlError('The predecessor has archive evidence without the matching selected capture mode.')
    return prior


def _baseline_continuation_full_link(link, current, child, predecessor_result, predecessor_id):
    """Validate the complete immutable proof, including all predecessor evidence and source identity."""
    operation = current.get('navigationBaseline')
    _baseline_continuation_identity(link, child, current)
    final = predecessor_result['samples'][-1]
    host = _controller_source_policy(child) is not None
    # GameCaptureSourceInfo retains PascalCase on the wire; journal fields differ.
    expected_source = {'kind': 'host-acquisition-v1', 'hostSnapshot': _host_pose_source(final)} if host else {
                       'CaptureEpoch': final['sourceEpoch'],
                       'SourceTimestamp100ns': final['sourceTimestamp100ns'],
                       'AcquiredAtStopwatchTicks': final['acquiredAtStopwatchTicks']}
    if (link.get('predecessorRunId') != predecessor_id
            or link.get('predecessorProfileId') != predecessor_result['profileId']
            or not _baseline_allows_predecessor(operation.get('profileId'), predecessor_result['profileId'])
            or link.get('predecessorEvidence') != predecessor_result['evidence']
            or link.get('predecessorFinalSource') != expected_source):
        raise ControlError('Continuation proof does not match the pinned predecessor result.')
    previous_link = predecessor_result.get('continuation')
    if previous_link is not None and any(link.get(key) != previous_link.get(key) for key in
            (('runtimeIdentity', 'gameStartedAtUtcTicks', 'captureType', 'readbackMode', 'sourcePolicy', 'childAssemblySha256')
             if host else ('runtimeIdentity', 'gameStartedAtUtcTicks', 'captureType', 'readbackMode'))):
        raise ControlError('The continuation chain changed its retained runtime, game start or capture identity.')
    if host and operation.get('state') == 'completed' and isinstance(operation.get('result'), dict):
        _baseline_host_start_after_floor(operation['result'], expected_source['hostSnapshot'])
    return link


def _baseline_continuation_link(current, child, predecessor_result, predecessor_id):
    """Pin status identity while the server owns admission; full proof is checked on terminal retrieval."""
    operation = current.get('navigationBaseline')
    version = child['navigationBaseline'].get('endpointContinuationVersion')
    host = _controller_source_policy(child) is not None
    if host:
        _baseline_host_identity(current, child)
    if (not isinstance(operation, dict) or type(operation.get('endpointContinuationVersion')) is not int
            or operation['endpointContinuationVersion'] != version):
        raise ControlError('The endpoint-continuation status contract changed while waiting.')
    link = operation.get('continuation')
    if version == 1:
        return _baseline_continuation_full_link(link, current, child, predecessor_result, predecessor_id)
    # Preserve all identity joins already observable in compact status. The full
    # runtime/source proof is intentionally unavailable until terminal retrieval.
    if (operation.get('gameProcessId') != child['navigationBaseline']['gameProcessId']
            or current.get('effectiveReadbackMode') != child.get('effectiveReadbackMode')
            or current.get('captureMode') != child.get('captureMode')):
        raise ControlError('The continuation status changed its pinned game or capture mode.')
    expected = _baseline_continuation_projection(dict(version=2 if host else 1, predecessorRunId=predecessor_id,
        predecessorProfileId=predecessor_result['profileId']), version, 1 if host else None)
    if (not isinstance(link, dict) or type(link.get('version')) is not int or link != expected
            or not _baseline_allows_predecessor(operation.get('profileId'), predecessor_result['profileId'])):
        raise ControlError('The continuation reference does not match the exact predecessor.')
    return link


def run_navigation_baseline(child, timeout, timing_contract='v1', capture_policy='shared',
                            route_profile='mondstadt-city-leg-1-v1', continuation_from_run_id=None, shadow_capture=None):
    """Execute only the fixed native leg once, waiting for that run's full cleanup and evidence."""
    require_role(child, 'ChildSession')
    source_policy = _controller_source_policy(child)
    if source_policy is not None and (timing_contract not in ('v4', 'v5') or capture_policy != 'task_owned_timer'
            or route_profile not in ('mondstadt-city-leg-1-v1', 'mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1')
            or shadow_capture is not None):
        raise ControlError('DesktopDc supports the explicit v4/v5 owned ordinary short or advertised fixed courtyard continuation without shadow capture.')
    if not _game_runtime_ready(child):
        raise ControlError('Run start-game and wait for runtime readiness before the navigation baseline.')
    if child.get('taskRunning') is not False or child.get('agentStreamRunning') is not False:
        raise ControlError('Stop the agent and all active tasks before the navigation baseline.')
    previous = child.get('navigationBaseline')
    if (not isinstance(previous, dict) or type(previous.get('resultVersion')) is not int
            or previous['resultVersion'] != 1 or previous.get('profileId') not in
            ('mondstadt-city-leg-1-v1', 'mondstadt-city-two-legs-v1', 'mondstadt-city-reverse-two-legs-v1', 'mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1')):
        raise ControlError('This child does not advertise the supported fixed navigation-baseline result contract.')
    if previous.get('state') not in ('idle', 'completed', 'failed', 'cancelled'):
        raise ControlError('A navigation baseline is active or unknown; query status before another mutation.')
    if not isinstance(timing_contract, str) or timing_contract not in ('v1', 'v2', 'v3', 'v4', 'v5'):
        raise ControlError('Baseline timing contract must be exactly v1, v2, v3, v4 or v5.')
    contracts = previous.get('timingContracts')
    if 'timingContracts' in previous and (not isinstance(contracts, list)
            or any(not isinstance(value, str) for value in contracts) or timing_contract not in contracts):
        raise ControlError('This child does not advertise the requested baseline timing contract.')
    if timing_contract != 'v1' and contracts is None:
        raise ControlError(f'This child does not advertise baseline timing {timing_contract}; upgrade before requesting it.')
    # Omit the additive selector for an old v1 host, which rejects unknown request members.
    fields = {'timingContract': timing_contract} if contracts is not None else {}
    if not isinstance(capture_policy, str) or capture_policy not in ('shared', 'task_owned_timer'):
        raise ControlError('Baseline capture policy must be exactly shared or task_owned_timer.')
    capture_policies = previous.get('capturePolicies')
    if 'capturePolicies' in previous and (not isinstance(capture_policies, list)
            or any(not isinstance(value, str) for value in capture_policies) or capture_policy not in capture_policies):
        raise ControlError('This child does not advertise the requested baseline capture policy.')
    if capture_policy != 'shared' and capture_policies is None:
        raise ControlError('This child does not advertise owned timer capture; upgrade before requesting it.')
    if capture_policies is not None:
        fields['capturePolicy'] = capture_policy
    if route_profile not in ('mondstadt-city-leg-1-v1', 'mondstadt-city-two-legs-v1', 'mondstadt-city-reverse-two-legs-v1', 'mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1'):
        raise ControlError('Unsupported fixed baseline route profile.')
    routes = previous.get('routeProfiles')
    if 'routeProfiles' in previous or 'routeVersion' in previous:
        if (type(previous.get('routeVersion')) is not int or previous['routeVersion'] != 1
                or not isinstance(routes, list) or any(not isinstance(value, str) for value in routes)
                or route_profile not in routes):
            raise ControlError('This child does not advertise the requested route profile.')
    if route_profile in ('mondstadt-city-two-legs-v1', 'mondstadt-city-reverse-two-legs-v1', 'mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1'):
        if routes is None or timing_contract not in ('v4', 'v5') or capture_policy != 'task_owned_timer':
            raise ControlError('The two-leg route requires routeVersion1, explicit v4 or v5 and task_owned_timer before starting.')
        fields['routeProfile'] = route_profile
    if shadow_capture is not None:
        if (shadow_capture != SHADOW_CAPTURE_MODE or timing_contract != 'v4' or capture_policy != 'task_owned_timer'
                or type(previous.get('shadowCaptureVersion')) is not int or previous['shadowCaptureVersion'] != 1
                or previous.get('shadowCaptureModes') != [SHADOW_CAPTURE_MODE]):
            raise ControlError('Shadow capture requires exact capability1, v4 and task_owned_timer before starting.')
        fields['shadowCapture'] = shadow_capture
    # Default old profile is omitted even on a capable host; server omission is explicitly the old route.
    expected_controller = f'native-fixed-leg-feedback-{timing_contract}'
    reset = child.get('navigationReset')
    if isinstance(reset, dict) and reset.get('state') == 'running':
        raise ControlError('Wait for the navigation reset to finish before starting the baseline.')
    if not _baseline_finite(timeout) or not 1 <= timeout <= 3600:
        raise ControlError('Baseline timeout must be finite and between 1 and 3600 seconds.')

    # A lost response may already have started movement. Never retry or join a
    # later discovered run; only this response can establish the new run identity.
    # Read-only predecessor retrieval precedes exactly one mutation. The server owns
    # the atomic retained-owner/runtime comparison; a client snapshot cannot reserve it.
    predecessor_result = None
    if route_profile in ('mondstadt-city-reverse-two-legs-v1', 'mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1'):
        predecessor_result = _baseline_continuation_preflight(child, continuation_from_run_id, requested_profile=route_profile, timing_contract=timing_contract)
        fields['continuationFromRunId'] = continuation_from_run_id
    elif continuation_from_run_id is not None:
        raise ControlError('A predecessor run ID is valid only with an explicit fixed continuation selector.')
    admitted = mutate('startNavigationBaseline', child, **fields)
    operation = admitted.get('navigationBaseline')
    run_id = operation.get('runId') if isinstance(operation, dict) else None
    game_pid = operation.get('gameProcessId') if isinstance(operation, dict) else None
    if (not isinstance(run_id, str) or re.fullmatch(r'[0-9a-fA-F]{32}', run_id) is None
            or run_id == '0' * 32 or run_id == previous.get('runId')):
        raise NavigationBaselineError('Navigation baseline did not return a new valid run ID; do not replay the start.', child)
    continuation = None
    current, last_verified = admitted, child
    deadline = time.monotonic() + timeout
    try:
        while True:
            require_role(current, 'ChildSession')
            if any(current.get(key) != child.get(key) for key in ('processId', 'windowsSessionId', 'instanceNonce')):
                raise ControlError('The pinned navigation-baseline instance changed while waiting.')
            operation = current.get('navigationBaseline')
            if (not isinstance(operation, dict) or operation.get('runId') != run_id
                    or operation.get('state') not in ('running', 'completed', 'failed', 'cancelled')
                    or operation.get('profileId') != route_profile
                    or type(operation.get('resultVersion')) is not int or operation['resultVersion'] != 1
                    or type(game_pid) is not int or game_pid <= 0 or operation.get('gameProcessId') != game_pid
                    or operation.get('windowsSessionId') != child['windowsSessionId']
                    or not isinstance(operation.get('phase'), str) or not operation['phase']
                    or operation.get('error') is not None and not isinstance(operation['error'], str)
                    or type(operation.get('observationCount')) is not int or operation['observationCount'] < 0
                    or type(operation.get('evidenceComplete')) is not bool):
                raise ControlError('Navigation-baseline run, profile, or result contract changed while waiting.')
            _controller_source_unchanged(current, child, source_policy, operation)
            if contracts is not None and (operation.get('timingContract') != timing_contract
                    or operation.get('controllerMethod') != expected_controller
                    or operation.get('timingContracts') != contracts):
                raise ControlError('The selected baseline timing contract changed while waiting.')
            if contracts is None and (operation.get('timingContract', 'v1') != 'v1'
                    or operation.get('controllerMethod', expected_controller) != expected_controller):
                raise ControlError('The legacy baseline did not retain timing v1.')
            if capture_policies is not None and (operation.get('capturePolicy') != capture_policy
                    or operation.get('capturePolicies') != capture_policies):
                raise ControlError('The selected baseline capture policy changed while waiting.')
            if capture_policies is None and operation.get('capturePolicy', 'shared') != 'shared':
                raise ControlError('The legacy baseline did not retain shared capture.')
            if routes is not None and (type(operation.get('routeVersion')) is not int
                    or operation['routeVersion'] != 1 or operation.get('routeProfiles') != routes):
                raise ControlError('The fixed route capability changed while waiting.')
            if predecessor_result is not None:
                observed = _baseline_continuation_link(current, child, predecessor_result, continuation_from_run_id)
                if continuation is None:
                    # Snapshot nested values so a reused/mutated decoded dictionary cannot change the pin.
                    continuation = json.loads(json.dumps(observed, allow_nan=False))
                elif observed != continuation:
                    raise ControlError('The admitted continuation proof changed; do not replay the request.')
            if operation.get('shadowCapture') != shadow_capture:
                raise ControlError('The pinned shadow-capture selection changed while waiting.')
            if shadow_capture is not None and (type(operation.get('shadowCaptureVersion')) is not int
                    or operation['shadowCaptureVersion'] != 1 or operation.get('shadowCaptureModes') != [SHADOW_CAPTURE_MODE]):
                raise ControlError('The shadow-capture capability changed while waiting.')
            last_verified = current
            if operation['state'] != 'running' and current.get('taskRunning') is False:
                terminal = (_navigation_baseline_result(current, host_continuation=True)
                    if source_policy is not None and predecessor_result is not None else _navigation_baseline_result(current))
                measured = terminal['navigationBaseline']['result']
                if ((contracts is not None or 'timingContract' in measured or 'controllerMethod' in measured)
                        and (measured.get('timingContract') != timing_contract
                             or measured.get('controllerMethod') != expected_controller)):
                    raise NavigationBaselineError('The baseline result has a different timing contract.', terminal)
                if ((capture_policies is not None or 'capturePolicy' in measured)
                        and measured.get('capturePolicy') != capture_policy):
                    raise NavigationBaselineError('The baseline result has a different capture policy.', terminal)
                if measured.get('profileId', 'mondstadt-city-leg-1-v1') != route_profile:
                    raise NavigationBaselineError('The baseline result has a different route profile.', terminal)
                if route_profile in ('mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1'):
                    legs = measured.get('legs')
                    if (type(measured.get('routeVersion')) is not int or measured['routeVersion'] != 1
                            or not isinstance(legs, list) or len(legs) > 1
                            or any(not isinstance(leg, dict) for leg in legs) or measured.get('waypoint') is not None):
                        raise NavigationBaselineError('Courtyard result exceeds its fixed one-leg shape.', terminal)
                if route_profile in ('mondstadt-city-two-legs-v1', 'mondstadt-city-reverse-two-legs-v1'):
                    if type(measured.get('routeVersion')) is not int or measured['routeVersion'] != 1:
                        raise NavigationBaselineError('The two-leg result lacks its exact version.', terminal)
                    legs, waypoint = measured.get('legs'), measured.get('waypoint')
                    if (not isinstance(legs, list) or len(legs) > 2 or any(not isinstance(leg, dict) for leg in legs)
                            or (waypoint is not None and not isinstance(waypoint, dict))):
                        raise NavigationBaselineError('The two-leg result exceeds its bounded shape.', terminal)
                    if operation['state'] == 'completed':
                        if (len(legs) != 2 or any(leg.get('outcome') != 'completed' for leg in legs)
                                or [leg.get('legIndex') for leg in legs] != [1, 2]
                                or not waypoint or waypoint.get('outcome') != 'completed' or waypoint.get('error') is not None
                                or not isinstance(waypoint.get('samples'), list) or len(waypoint['samples']) != 3
                                or not isinstance(waypoint.get('anchor'), dict)):
                            raise NavigationBaselineError('The two-leg result lacks its verified waypoint/leg outcomes.', terminal)
                        for pose in [*waypoint['samples'], waypoint['anchor']]:
                            _baseline_pose(pose)
                if predecessor_result is not None:
                    full_link = measured.get('continuation')
                    try:
                        _baseline_continuation_full_link(full_link, terminal, child, predecessor_result, continuation_from_run_id)
                        if _baseline_continuation_projection(full_link, previous['endpointContinuationVersion'],
                                previous.get('hostEndpointContinuationVersion') if source_policy is not None else None) != continuation:
                            raise ControlError('The full result does not retain the admitted continuation reference.')
                    except ControlError as error:
                        raise NavigationBaselineError(str(error), terminal) from error
                    if operation['state'] == 'completed':
                        _baseline_fixed_route_result(measured)
                if operation['state'] != 'completed':
                    raise NavigationBaselineError(operation.get('error') or f"Navigation baseline {operation['state']}.", terminal)
                archive = (measured.get('evidence') or {}).get('shadowCapture')
                if shadow_capture is not None:
                    try:
                        _require_shadow_capture(archive, measured['evidence'])
                    except ControlError as error:
                        raise NavigationBaselineError(str(error), terminal) from error
                elif archive is not None:
                    raise NavigationBaselineError('Unexpected shadow archive on a default baseline.', terminal)
                if current.get('agentStreamRunning') is not False:
                    raise NavigationBaselineError('Agent activity is active or unknown at baseline completion.', terminal)
                return terminal
            if time.monotonic() >= deadline:
                raise ControlError('Timed out waiting for the baseline and cleanup; query status before further action. No cancellation was sent.')
            time.sleep(0.1)
            current = refresh(child)
    except NavigationBaselineError:
        raise
    except (ControlError, OSError, ValueError, KeyError) as error:
        raise NavigationBaselineError(str(error), last_verified) from error


def _require_shadow_capture(archive, evidence):
    """Check bounded terminal archive claims; actual files/intent joins require the separate offline verifier."""
    if not isinstance(archive, dict) or archive.get('mode') != SHADOW_CAPTURE_MODE:
        raise ControlError('Selected shadow capture has no matching archive evidence.')
    names = ('framesSeen', 'framesAccepted', 'framesWritten', 'duplicateFrames',
             'framesRejected', 'offersIgnoredAfterStop', 'framesLost')
    if any(type(archive.get(key)) is not int or archive[key] < 0 for key in names):
        raise ControlError('Shadow archive counts are malformed.')
    seen, accepted, written, duplicates, rejected, ignored, lost = (archive[key] for key in names)
    if (seen > 4096 or accepted > 1024 or written > accepted
            or seen != accepted + duplicates + rejected + ignored or lost != accepted - written + rejected):
        raise ControlError('Shadow archive count bounds/joins failed.')
    if (type(archive.get('complete')) is not bool or type(archive.get('workerRetired')) is not bool
            or archive.get('error') is not None and (not isinstance(archive['error'], str) or len(archive['error']) > 256)):
        raise ControlError('Shadow archive completion evidence is malformed.')
    if not archive['complete'] or not archive['workerRetired'] or archive.get('error') is not None or lost or written == 0:
        raise ControlError('Shadow capture is incomplete; native route result is retained separately.')
    for key in ('manifestSha256', 'nativeJournalSha256'):
        if not isinstance(archive.get(key), str) or re.fullmatch(r'[0-9a-fA-F]{64}', archive[key]) is None:
            raise ControlError('Shadow archive digest is missing or malformed.')
    if archive['nativeJournalSha256'].lower() != evidence.get('journalSha256', '').lower():
        raise ControlError('Shadow archive refers to a different native journal.')
    try:
        local_absolute(archive['manifestPath'])
    except (ValueError, TypeError, KeyError) as error:
        raise ControlError('Shadow manifest must have a local absolute path.') from error


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
        attributes = item.lstat()
        if item.is_symlink() or getattr(attributes, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ControlError('Replacement paths must not contain filesystem links.')


def _sha256(path):
    """Hash staged binary bytes without loading them into the current process."""
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


# Root-store staging remains bounded even when a directory has only empty subdirectories.
PULONIA_ENTRY_LIMIT = 8192
PULONIA_FILE_LIMIT = 4096
PULONIA_FILE_BYTES = 16 * 1024 * 1024
PULONIA_TOTAL_BYTES = 256 * 1024 * 1024


def _pulonia_file(path, expected, destination=None):
    """Hash/copy one bounded owned stream; reject growth, replacement or mutation seen during the read."""
    _no_links(path)
    digest = hashlib.sha256()
    remaining = expected.st_size
    # The optional destination is an exclusively created file inside our private staging directory.
    with path.open('rb') as original:
        initial = os.fstat(original.fileno())
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
        if identity(initial) != identity(expected):
            raise ControlError('Pulonia source changed before a bounded read.')
        while remaining:
            chunk = original.read(min(65536, remaining))
            if not chunk:
                raise ControlError('Pulonia source shortened during a bounded read.')
            digest.update(chunk)
            if destination is not None:
                destination.write(chunk)
            remaining -= len(chunk)
        if original.read(1) or identity(os.fstat(original.fileno())) != identity(expected):
            raise ControlError('Pulonia source changed during a bounded read.')
    _no_links(path)
    if identity(path.lstat()) != identity(expected):
        raise ControlError('Pulonia source was replaced during a bounded read.')
    return digest.hexdigest()


def _pulonia_inventory(root):
    """Inspect opaque files without parsing/migrating state; this is not a snapshot of an active writer."""
    ancestor = root
    while not os.path.lexists(ancestor):
        ancestor = ancestor.parent
    _no_links(ancestor)
    if not os.path.lexists(root):
        return {'present': False, 'directories': [], 'files': [], 'totalBytes': 0}, {}
    _no_links(root)
    if not root.is_dir():
        raise ControlError('User/Pulonia must be a physical directory.')
    pending, directories, files, observed = [root], [], [], {}
    entries, total = 0, 0
    while pending:
        directory = pending.pop()
        _no_links(directory)
        with os.scandir(directory) as children:
            for child in children:
                entries += 1
                if entries > PULONIA_ENTRY_LIMIT:
                    raise ControlError('Pulonia staging exceeds the 8192-entry limit.')
                path = Path(child.path)
                _no_links(path)
                info = path.lstat()
                relative = path.relative_to(root).as_posix()
                if len(relative.encode('utf-8')) > 1024:
                    raise ControlError('A Pulonia relative path exceeds the 1024-byte limit.')
                if stat.S_ISDIR(info.st_mode):
                    directories.append(relative)
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    if len(files) >= PULONIA_FILE_LIMIT or info.st_size > PULONIA_FILE_BYTES:
                        raise ControlError('Pulonia staging exceeds the 4096-file or 16 MiB/file limit.')
                    total += info.st_size
                    if total > PULONIA_TOTAL_BYTES:
                        raise ControlError('Pulonia staging exceeds the 256 MiB total limit.')
                    files.append({'path': relative, 'bytes': info.st_size, 'sha256': _pulonia_file(path, info)})
                    observed[relative] = info
                else:
                    raise ControlError('Pulonia staging accepts only ordinary files and directories.')
    names = directories + [row['path'] for row in files]
    if len({name.casefold() for name in names}) != len(names):
        raise ControlError('Pulonia paths collide under case-insensitive comparison.')
    return {'present': True, 'directories': sorted(directories),
            'files': sorted(files, key=lambda row: row['path']), 'totalBytes': total}, observed


def _stage_pulonia(source, target, inventory, observed):
    """Publish one complete verified tree or retain an identical tree; never merge or replace another store."""
    if os.path.lexists(target):
        if _pulonia_inventory(target)[0] != inventory:
            raise ControlError('Target already has different User/Pulonia; select a fresh published release.')
        outcome = 'retained-identical'
    elif not inventory['present']:
        outcome = 'source-absent'
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        _no_links(target.parent)
        # Only this newly created private directory is cleaned on failure. Original and final stores are untouched.
        with tempfile.TemporaryDirectory(prefix='.pulonia-stage-', dir=target.parent) as temporary:
            staged = Path(temporary) / 'Pulonia'
            staged.mkdir()
            for relative in inventory['directories']:
                (staged / relative).mkdir(parents=True, exist_ok=True)
            for row in inventory['files']:
                destination = staged / row['path']
                with destination.open('xb') as replacement:
                    actual = _pulonia_file(source / row['path'], observed[row['path']], replacement)
                if actual != row['sha256']:
                    raise ControlError('Pulonia source bytes changed after preflight.')
            if _pulonia_inventory(staged)[0] != inventory or _pulonia_inventory(source)[0] != inventory:
                raise ControlError('Pulonia inventory changed; staged data was not published.')
            if os.path.lexists(target):
                raise ControlError('Target User/Pulonia appeared during staging; no store was replaced.')
            # Windows directory rename refuses an existing destination; the target must remain inactive/exclusive.
            staged.rename(target)
        outcome = 'copied'
    if _pulonia_inventory(source)[0] != inventory or _pulonia_inventory(target)[0] != inventory:
        raise ControlError('Pulonia final verification changed; do not launch the target or reuse an older staging report.')
    return {'version': 1, 'outcome': outcome, 'sourceQuiescentAsserted': True,
            'activeWriterSnapshotProven': False, **inventory}


def stage_configuration(source, target, *, preserve_pulonia=False, source_quiescent=False):
    """Copy settings/profiles; explicitly selected root upgrades preserve an already-quiescent opaque Pulonia store."""
    if type(preserve_pulonia) is not bool or type(source_quiescent) is not bool:
        raise ControlError('Pulonia staging options must be explicit booleans.')
    if preserve_pulonia != source_quiescent:
        raise ControlError('Root-store staging requires both preserve_pulonia and source_quiescent; quiescence is a technical prerequisite.')
    source = local_absolute(source)
    target = local_absolute(target)
    _no_links(source)
    _no_links(target)
    if source.resolve() == target.resolve() or not (target / 'BetterGI.exe').is_file():
        raise ControlError('Choose a different, already published BetterGI target directory.')
    pulonia = None
    if preserve_pulonia:
        if (not source.is_dir() or source.resolve().is_relative_to(target.resolve())
                or target.resolve().is_relative_to(source.resolve())):
            raise ControlError('Root-store staging requires distinct, non-nested installation directories.')
        pulonia, observed = _pulonia_inventory(source / 'User/Pulonia')
        if os.path.lexists(target / 'User/Pulonia') and _pulonia_inventory(target / 'User/Pulonia')[0] != pulonia:
            raise ControlError('Target already has different User/Pulonia; select a fresh published release.')
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
    if len(selected) + (len(pulonia['files']) if pulonia is not None else 0) > 4096:
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
    if pulonia is not None:
        report['pulonia'] = _stage_pulonia(source / 'User/Pulonia', target / 'User/Pulonia', pulonia, observed)
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
    return _portable_package(target)


def _portable_package(target):
    """Validate portable runtime files and hash app bytes without loading any executable."""
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


def resolve_child_root(child, *, strict_discovery=False):
    """Pin one independently discovered primary, including legacy children lacking rootProcessId."""
    discovery = discover()
    if strict_discovery and discovery.get('unavailable'):
        raise ControlError('Primary discovery is incomplete; legacy root resolution is not verified.')
    roots = [item for item in discovery['instances']
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


def hot_replace(child, target, timeout, *, idle_only=False, pinned_root=None, pinned_package=None, start_game=True):
    """Retain acknowledgement/readiness evidence on either successful or failed handoff."""
    evidence = {'phase': 'replacement_preflight', 'restartRequestAttempted': False,
                'restartAcknowledged': False, 'readinessPolls': 0,
                'previousProcessId': child.get('processId'), 'previousNonce': child.get('instanceNonce'),
                'targetDirectory': str(target)}
    try:
        result = _hot_replace(child, target, timeout, idle_only=idle_only, pinned_root=pinned_root,
                              pinned_package=pinned_package, start_game=start_game, evidence=evidence)
        return {**result, 'replacementEvidence': evidence}
    except (ControlError, OSError, ValueError, KeyError) as error:
        raise ReplacementError(str(error) or type(error).__name__, evidence) from error


def _hot_replace(child, target, timeout, *, idle_only, pinned_root, pinned_package, start_game, evidence):
    """Drain tasks, restart only this child, then verify replacement identity and assembly."""
    require_role(child, 'ChildSession')
    if type(start_game) is not bool or not start_game and not idle_only:
        raise ControlError('Endpoint-only replacement requires the capability-gated idle-only path.')
    idle_deadline = time.monotonic() + timeout if idle_only else None
    manifest = prepare_replacement(child['appDirectory'], target, require_opt_in=False)
    root = resolve_child_root(child, strict_discovery=True) if idle_only else resolve_child_root(child)
    if idle_only:
        # Shortcut upgrades must not interrupt a task that won the startup race.
        # Existing explicit hot-replace retains its deliberate stop/drain semantics.
        from child_reconciliation import prepare_idle_replacement, require_idle_restart
        require_idle_restart(sys.modules[__name__], child, start_game=start_game)
        idle = prepare_idle_replacement(sys.modules[__name__], child, root, pinned_root, pinned_package,
                                        start_game=start_game)
        if manifest != pinned_package:
            raise ControlError('The replacement package changed after selection.')
        enable_restart(child['appDirectory'], target)
    else:
        enable_restart(child['appDirectory'], target)
        evidence['phase'] = 'stop_request'
        mutate('stopAutomationTasks', child)
        evidence['phase'] = 'stop_readiness'
        idle = wait_status(child, lambda state: state.get('taskRunning') is False, timeout)
    evidence['phase'] = 'restart_manifest'
    _require_connected_root(refresh(root), child)
    manifest_path = Path(idle['appDirectory']) / 'User/ExternalControl/pending-restart.json'
    atomic_json(manifest_path, manifest)
    # Preflight completed before the stop; server independently rechecks both hashes.
    if idle_only:
        idle = prepare_idle_replacement(sys.modules[__name__], child, refresh(root), pinned_root, pinned_package,
                                        start_game=start_game)
        if time.monotonic() >= idle_deadline:
            raise ControlError('Idle replacement deadline expired before dispatch; restart was not sent.')
        # The on-disk manifest remains version one. Startup intent is request-bound,
        # not another shared file that a concurrent invocation could overwrite.
        expectation = dict(manifest)
        if idle['idleRestartVersion'] == 2:
            expectation.update(version=2, startupMode='gameRuntime' if start_game else 'controlEndpoint')
    evidence.update(phase='restart_request', restartRequestAttempted=True)
    mutate('restartApp', idle, **({'idleRestart': expectation} if idle_only else {}))
    evidence.update(phase='replacement_readiness', restartAcknowledged=True)
    deadline = idle_deadline if idle_only else time.monotonic() + timeout
    replacement_identity = None
    while time.monotonic() < deadline:
        # The host must remain the same process epoch and connected session across
        # the handoff. A missing legacy root ID never counts as matching another None.
        current_root = _require_connected_root(refresh(root), child)
        discovery = discover()
        evidence['readinessPolls'] += 1
        if idle_only and time.monotonic() >= deadline:
            evidence['lastPendingReason'] = 'The readiness deadline elapsed during the last bounded status poll.'
            break
        if idle_only:
            from child_reconciliation import replacement_candidate
            candidate, pending = replacement_candidate(sys.modules[__name__], child, current_root, discovery,
                                                       pinned_root, pinned_package)
            if candidate is not None:
                identity = (candidate['processId'], candidate['instanceNonce'])
                if replacement_identity is not None and identity != replacement_identity:
                    raise ControlError('The authenticated replacement process epoch changed while waiting.')
                replacement_identity = identity
                evidence['replacementProcessId'], evidence['replacementNonce'] = identity
            if pending:
                evidence['lastPendingReason'] = pending
                time.sleep(min(.5, max(0, deadline - time.monotonic())))
                continue
            candidates = [] if candidate is None else [candidate]
        else:
            candidates = discovery['instances']
        for candidate in candidates:
            if (candidate.get('windowsSessionId') == child['windowsSessionId']
                    and candidate.get('processId') != child['processId']
                    and candidate.get('instanceNonce') != child['instanceNonce']
                    and candidate.get('instanceType') == 'ChildSession'
                    and candidate.get('rootProcessId') == root['processId']
                    and os.path.normcase(candidate.get('appDirectory', '').rstrip('\\/'))
                    == os.path.normcase(str(Path(target)).rstrip('\\/'))
                    and candidate.get('assemblySha256', '').lower() == manifest['dllSha256']):
                require_role(candidate, 'ChildSession')
                ready = _game_runtime_ready(candidate) if start_game else _control_endpoint_ready(candidate)
                if ready and candidate.get('taskRunning') is False:
                    current_root = _require_connected_root(refresh(root), child)
                    if idle_only and time.monotonic() >= deadline:
                        evidence['lastPendingReason'] = 'The readiness deadline elapsed during final root verification.'
                        break
                    evidence['phase'] = 'replacement_ready'
                    return {'ready': True, 'previousProcessId': child['processId'],
                            'legacyRootResolution': child.get('rootProcessId') is None,
                            'manifest': manifest, 'root': current_root, 'child': candidate}
        time.sleep(0.5)
    detail = evidence.get('lastPendingReason', 'The requested lifecycle has not become ready.')
    raise ControlError('Replacement was dispatched but readiness was not verified; ' + detail
                       + ' Discover/status before further action; restart was not replayed.')


def main():
    """Expose explicit host/child operations with machine-readable JSON output."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('discover', help='list authenticated same-user automation/control instances')
    staging = sub.add_parser('stage-config', help='copy local settings and missing custom profiles into a published release')
    staging.add_argument('--source-directory', required=True)
    staging.add_argument('--target-directory', required=True)
    staging.add_argument('--preserve-pulonia', action='store_true',
                         help='preserve all opaque User/Pulonia data for a root-host upgrade; requires --source-quiescent')
    staging.add_argument('--source-quiescent', action='store_true',
                         help='assert all source-store writers are stopped/quiescent and target remains inactive/exclusive')
    for command in ('status', 'start', 'ensure-child', 'cancel-start', 'start-game', 'start-agent', 'stop-agent', 'set-capture-mode', 'reset-navigation', 'run-navigation-baseline', 'minimize', 'show', 'exec', 'hot-replace'):
        item = sub.add_parser(command)
        item.add_argument('--process-id', type=int)
        item.add_argument('--windows-session-id', type=int)
        item.add_argument('--timeout', type=int, default=45 if command == 'run-navigation-baseline' else 120)
        if command in ('start', 'ensure-child'):
            item.add_argument('--preserve-window', action='store_true',
                              help='preserve an existing shown RDP window when reusing its child')
        if command == 'ensure-child':
            item.add_argument('--instance-nonce', required=True)
            item.add_argument('--target-directory', required=True)
            item.add_argument('--exe-sha256', required=True)
            item.add_argument('--dll-sha256', required=True)
            item.add_argument('--start-game', action='store_true')
        if command == 'start-agent':
            item.add_argument('--enable-input', action='store_true', help='explicitly permit controller input in the RDP child')
            item.add_argument('--experimental-queued-step-applications', action='store_true',
                              help='explicit session permission for queued v2; requires --enable-input and a stopped stream')
            item.add_argument('--observation-profile', choices=OBSERVATION_PROFILES,
                              default=LEGACY_OBSERVATION_PROFILE,
                              help='fixed preprocessing profile; stop an existing stream before changing it')
        if command == 'set-capture-mode':
            item.add_argument('--mode', required=True, choices=CAPTURE_MODES)
            item.add_argument('--readback-mode', choices=READBACK_MODES,
                              help='explicit WGC V2 readback mode; omission reattaches with blocking')
            item.add_argument('--source-retention', choices=SOURCE_RETENTIONS,
                              help='explicit WGC V2 source ownership; omission preserves the saved setting')
            item.add_argument('--conversion', choices=CONVERSION_MODES,
                              help='explicit WGC V2 GPU/CPU conversion; omission preserves the saved setting')
            item.add_argument('--desktop-dc-source-policy', choices=DESKTOP_DC_SOURCE_POLICIES,
                              help='explicit DesktopDc source policy; omission preserves the saved setting')
        if command == 'reset-navigation':
            item.add_argument('--yaw-degrees', type=_parse_navigation_yaw, default=0.0,
                              help='fixed reset camera yaw in [0, 360); defaults to 0 degrees')
            item.add_argument('--capture-policy', choices=('shared', 'task_owned_timer'), default='shared',
                              help='shared is unchanged; task_owned_timer pauses timer capture only after teleport completes')
        if command == 'run-navigation-baseline':
            item.add_argument('--shadow-capture', choices=(SHADOW_CAPTURE_MODE,), default=None,
                              help='explicit capture-only RGB192 archive; requires v4/task_owned_timer')
            item.add_argument('--route-profile', choices=('mondstadt-city-leg-1-v1', 'mondstadt-city-two-legs-v1', 'mondstadt-city-reverse-two-legs-v1', 'mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1'),
                              default='mondstadt-city-leg-1-v1', help='Fixed route; two legs require explicit v4 or v5 and task_owned_timer.')
            item.add_argument('--continuation-from-run-id',
                              help='Required for an explicit continuation route: exact latest completed opposite-direction run ID.')
            item.add_argument('--timing-contract', choices=('v1', 'v2', 'v3', 'v4', 'v5'), default='v1',
                              help='v1 is unchanged; v2 permits the first W start up to 150ms; v3 permits each W start up to 150ms, with 100ms renewals and the source cap; v4 adds bounded release-and-freshness recovery; explicit v5 uses source-anchor+250ms expiry with unchanged 150ms dispatch freshness')
            item.add_argument('--capture-policy', choices=('shared', 'task_owned_timer'), default='shared',
                              help='shared is unchanged; task_owned_timer pauses this runtime timer capture during the task')
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
        if (args.command == 'start-agent' and args.experimental_queued_step_applications
                and not args.enable_input):
            raise ControlError('--experimental-queued-step-applications requires --enable-input.')
        if args.command == 'discover':
            result = discover()
        elif args.command == 'stage-config':
            options = ({'preserve_pulonia': args.preserve_pulonia, 'source_quiescent': args.source_quiescent}
                       if args.preserve_pulonia or args.source_quiescent else {})
            result = stage_configuration(args.source_directory, args.target_directory, **options)
        else:
            if not 1 <= args.timeout <= 3600:
                raise ControlError('--timeout must be between 1 and 3600 seconds.')
            if (args.process_id is None) != (args.windows_session_id is None):
                raise ControlError('Specify both --process-id and --windows-session-id.')
            if args.command == 'ensure-child' and args.process_id is None:
                raise ControlError('Selected-child startup requires the exact primary PID/session/nonce.')
            role = 'ChildSession' if args.command in ('hot-replace', 'start-game', 'start-agent', 'stop-agent', 'set-capture-mode', 'reset-navigation', 'run-navigation-baseline') else 'Primary'
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
                result = start_child(status, args.timeout, args.preserve_window)
            elif args.command == 'ensure-child':
                from child_reconciliation import ensure_child
                result = ensure_child(sys.modules[__name__], status, args.target_directory,
                                      args.exe_sha256, args.dll_sha256, args.instance_nonce,
                                      args.timeout, args.preserve_window, args.start_game)
            elif args.command == 'cancel-start':
                result = mutate('cancelChildStart', status)
            elif args.command == 'start-game':
                result = start_game(status, args.timeout)
            elif args.command == 'start-agent':
                if args.experimental_queued_step_applications:
                    result = start_agent(status, args.timeout, args.enable_input, args.observation_profile,
                                         experimental_queued_step_applications=True)
                else:
                    result = start_agent(status, args.timeout, args.enable_input, args.observation_profile)
            elif args.command == 'stop-agent':
                result = stop_agent(status, args.timeout)
            elif args.command == 'set-capture-mode':
                # Preserve legacy calls and wire omission; only explicit flags add keyword arguments.
                options = {name: value for name, value in (
                    ('readback_mode', args.readback_mode), ('source_retention', args.source_retention),
                    ('conversion', args.conversion),
                    ('desktop_dc_source_policy', args.desktop_dc_source_policy)) if value is not None}
                result = set_capture_mode(status, args.mode, args.timeout, **options)
            elif args.command == 'reset-navigation':
                result = reset_navigation(status, args.yaw_degrees, args.timeout, args.capture_policy)
            elif args.command == 'run-navigation-baseline':
                # Preserve the legacy call/default shape; only the new fixed route supplies its selector.
                baseline_args = (status, args.timeout, args.timing_contract, args.capture_policy)
                if args.shadow_capture is not None or args.continuation_from_run_id is not None or args.route_profile in ('mondstadt-city-reverse-two-legs-v1', 'mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1'):
                    options = dict(route_profile=args.route_profile)
                    if args.continuation_from_run_id is not None: options['continuation_from_run_id'] = args.continuation_from_run_id
                    if args.shadow_capture is not None: options['shadow_capture'] = args.shadow_capture
                    result = run_navigation_baseline(*baseline_args, **options)
                else:
                    result = (run_navigation_baseline(*baseline_args) if args.route_profile == 'mondstadt-city-leg-1-v1'
                              else run_navigation_baseline(*baseline_args, args.route_profile))
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
        failure = {'success': False, 'error': str(error)}
        if isinstance(error, (NavigationResetError, NavigationBaselineError)):
            failure['status'] = error.status
        if isinstance(error, ReplacementError):
            failure['replacementEvidence'] = error.evidence
        print(json.dumps(failure, ensure_ascii=True, allow_nan=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
