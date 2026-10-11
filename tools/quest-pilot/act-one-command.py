"""Submit one bounded mission to the BetterGI RDP controller; never replay on timeout."""
import argparse
import json
import os
import re
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = Path(os.environ.get('BETTERGI_PILOT_APP_DIR', REPO / 'artifacts/release-r8/BetterGI-English-win-x64'))
ROOT = APP / 'User/JsScript/ActOnePilot'
HEARTBEAT_MAX_AGE_MS = 5000


class ProcessAccessDenied(RuntimeError):
    """OpenProcess was denied; a separately verified named-pipe status may confirm liveness."""


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def atomic(path, value):
    pending = path.with_suffix('.pending.json')
    pending.write_text(json.dumps(value), encoding='utf-8')
    os.replace(pending, path)


def verify_windows_process(process_id, windows_session_id):
    """Confirm the BetterGI process is still alive in the expected RDP session."""
    if os.name != 'nt':
        raise RuntimeError('Cannot verify the BetterGI PID outside Windows; run this command on the RDP host.')
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                   ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, process_id)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        error = ctypes.get_last_error()
        if error == 5:  # ERROR_ACCESS_DENIED: elevated child can deny the caller's query handle.
            raise ProcessAccessDenied(f'Access denied querying BetterGI process {process_id}.')
        raise RuntimeError(f'BetterGI process {process_id} is not accessible or has exited; inspect the RDP session.')
    try:
        actual_session = wintypes.DWORD()
        if not kernel32.ProcessIdToSessionId(process_id, ctypes.byref(actual_session)):
            raise RuntimeError(f'Could not verify Windows session for BetterGI process {process_id}.')
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value != 259:
            raise RuntimeError(f'BetterGI process {process_id} is no longer running.')
        image = ctypes.create_unicode_buffer(32768)
        image_length = wintypes.DWORD(len(image))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(image_length)):
            raise RuntimeError(f'Could not verify executable for BetterGI process {process_id}.')
        if Path(image.value).name.casefold() != 'bettergi.exe':
            raise RuntimeError(f'Heartbeat PID {process_id} belongs to {Path(image.value).name}, not BetterGI.exe.')
        if actual_session.value != windows_session_id:
            raise RuntimeError(f'BetterGI process {process_id} is in Windows session {actual_session.value}, not {windows_session_id}.')
    finally:
        kernel32.CloseHandle(handle)


def query_verified_service_status(process_id, windows_session_id):
    """Read status through the PID/session/SID-verified local control pipe."""
    import importlib.util
    control_path = Path(__file__).with_name('controller-control.py')
    spec = importlib.util.spec_from_file_location('act_one_controller_control', control_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run('status', process_id, windows_session_id)


def require_live_controller(root, requested_session, requested_frame, expected_windows_session_id, *, now_ms=None,
                            process_verifier=verify_windows_process,
                            service_status_query=query_verified_service_status, allow_active=False,
                            allow_faulted=False):
    """Fail closed unless the current heartbeat matches the frame and explicitly allowed state."""
    heartbeat = None
    last_error = None
    for attempt in range(3):
        try:
            heartbeat = read(root / 'controller-status.json')
            break
        except (OSError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.05)
    if heartbeat is None:
        raise RuntimeError('Controller heartbeat is missing or invalid. Update and start the supervised ActOnePilot before submitting missions.') from last_error
    if not isinstance(heartbeat, dict) or heartbeat.get('version') != 1:
        raise RuntimeError('Controller heartbeat schema is unsupported. Update the ActOnePilot package before submitting missions.')
    process_id = heartbeat.get('processId')
    windows_session_id = heartbeat.get('windowsSessionId')
    heartbeat_at = heartbeat.get('heartbeatAt')
    if (isinstance(process_id, bool) or not isinstance(process_id, int) or process_id <= 0
            or isinstance(windows_session_id, bool) or not isinstance(windows_session_id, int)
            or isinstance(heartbeat_at, bool) or not isinstance(heartbeat_at, int)):
        raise RuntimeError('Controller heartbeat lacks a valid process ID, Windows session, or timestamp.')
    if (isinstance(expected_windows_session_id, bool) or not isinstance(expected_windows_session_id, int)
            or expected_windows_session_id <= 1 or windows_session_id != expected_windows_session_id):
        raise RuntimeError(f'ActOnePilot heartbeat targets Windows session {windows_session_id}, not the explicitly pinned RDP child session above 1 ({expected_windows_session_id}).')
    if heartbeat.get('remoteDesktop') is not True:
        raise RuntimeError('ActOnePilot heartbeat does not prove a remote-desktop child session.')
    injected_now_ms = now_ms
    now_ms = int(time.time() * 1000) if injected_now_ms is None else injected_now_ms
    age = now_ms - heartbeat_at
    if age < 0 or age > HEARTBEAT_MAX_AGE_MS:
        raise RuntimeError(f'Controller heartbeat is stale ({age} ms). Check the BetterGI child in RDP session {windows_session_id}.')
    state = heartbeat.get('state')
    allowed_states = ('idle', 'starting', 'running') if allow_active else ('idle',)
    if allow_faulted:
        allowed_states += ('faulted',)
    if state not in allowed_states:
        if state in ('stopped', 'faulted'):
            raise RuntimeError(f'ActOnePilot is {state}. Use controller-control.py status/start after inspecting the RDP session; no mission was submitted.')
        raise RuntimeError(f'ActOnePilot is {state!r}, not idle. Wait for its current mission to finish; no mission was submitted.')
    live_session = heartbeat.get('session')
    if not isinstance(live_session, str) or not live_session:
        raise RuntimeError('Controller heartbeat has no live script session; update or restart ActOnePilot.')
    if live_session != requested_session:
        raise RuntimeError('Controller session changed. Inspect the latest observation and submit against its session/frame.')
    heartbeat_frame = heartbeat.get('frameId')
    if not allow_active and (isinstance(heartbeat_frame, bool) or not isinstance(heartbeat_frame, int) or heartbeat_frame != requested_frame):
        raise RuntimeError('Controller frame changed. Inspect the latest observation and submit against its current frame.')
    if allow_active:
        # Cancellation intentionally ignores frame churn: it targets the same
        # owned script session, even while that session is producing captures.
        try:
            status = service_status_query(process_id, windows_session_id)
        except Exception as status_error:
            raise RuntimeError('Verified child service status is unavailable; cancellation was not requested.') from status_error
        status_at = status.get('heartbeatAtUnixMs') if isinstance(status, dict) else None
        status_age = now_ms - status_at if isinstance(status_at, int) and not isinstance(status_at, bool) else None
        if (not isinstance(status, dict)
                or status.get('processId') != process_id
                or status.get('windowsSessionId') != windows_session_id
                or status.get('instanceType') != 'ChildSession'
                or status.get('remoteDesktop') is not True
                or status.get('serviceOwnsPilot') is not True
                or status.get('scriptSession') != live_session
                or status.get('scriptState') != state
                or status.get('pilotState') not in allowed_states
                or status_age is None or status_age < 0 or status_age > HEARTBEAT_MAX_AGE_MS):
            raise RuntimeError('Verified child service status did not confirm the same fresh owned script session; cancellation was not requested.')
        try:
            process_verifier(process_id, windows_session_id)
        except ProcessAccessDenied:
            # The exact PID/session/SID-authenticated status pipe above is the
            # fallback liveness proof for elevated child processes.
            pass
        return heartbeat
    try:
        process_verifier(process_id, windows_session_id)
    except ProcessAccessDenied as exc:
        try:
            status = service_status_query(process_id, windows_session_id)
        except Exception as status_error:
            raise RuntimeError(f'{exc} Verified controller status is unavailable; no mission was submitted.') from status_error
        status_at = status.get('heartbeatAtUnixMs') if isinstance(status, dict) else None
        current_ms = int(time.time() * 1000) if injected_now_ms is None else injected_now_ms
        status_age = current_ms - status_at if isinstance(status_at, int) and not isinstance(status_at, bool) else None
        if (not isinstance(status, dict)
                or status.get('processId') != process_id
                or status.get('windowsSessionId') != windows_session_id
                or status.get('instanceType') != 'ChildSession'
                or status.get('remoteDesktop') is not True
                or status.get('scriptSession') != live_session
                or status.get('frameId') != heartbeat_frame
                or status.get('scriptState') != state
                or status.get('pilotState') != state
                or (allow_faulted and status.get('serviceOwnsPilot') is not True)
                or status_age is None or status_age < 0 or status_age > HEARTBEAT_MAX_AGE_MS):
            expected = 'faulted' if state == 'faulted' else 'idle'
            raise RuntimeError(f'Access to the BetterGI process was denied and verified service status did not confirm the same fresh {expected} PID/session/frame; no mission was submitted.') from exc
    return heartbeat


def validate_terminal_receipt(request, receipt, observation):
    """Validate the complete request/receipt/observation provenance chain."""
    if receipt.get('id') != request.get('id'):
        raise RuntimeError('Terminal receipt ID does not match the submitted request.')
    if receipt.get('session') != request.get('session') or receipt.get('mission') != request.get('mission'):
        raise RuntimeError('Matching receipt has the wrong session or mission; inspect controller status. No retry was sent.')
    if receipt.get('status') not in ('completed', 'failed', 'rejected', 'stopped'):
        raise RuntimeError('Matching receipt has an unknown terminal status; inspect controller status. No retry was sent.')
    frame_id = receipt.get('frameId')
    if (isinstance(frame_id, bool) or not isinstance(frame_id, int)
            or observation.get('session') != request.get('session')
            or observation.get('frameId') != frame_id):
        raise RuntimeError('Terminal receipt and current observation do not match this session/frame; inspect status. No retry was sent.')
    return frame_id


def request_receipt_path(root, session, request_id):
    """Return the immutable receipt path after rejecting path-like identifiers."""
    if not isinstance(session, str) or not re.fullmatch(r'[a-z0-9]+-[a-z0-9]*', session):
        raise RuntimeError('Controller session is not a valid generated session identifier.')
    if not isinstance(request_id, str) or not re.fullmatch(r'mission-[0-9a-f]{32}', request_id):
        raise RuntimeError('Request ID is not a valid generated mission identifier.')
    return root / 'receipts' / session / (request_id + '.json')


def observation_path(root, session, frame_id):
    if not isinstance(session, str) or not re.fullmatch(r'[a-z0-9]+-[a-z0-9]*', session):
        raise RuntimeError('Controller session is not a valid generated session identifier.')
    if (not isinstance(frame_id, int) or isinstance(frame_id, bool) or frame_id < 0):
        raise RuntimeError('Terminal receipt has an invalid observation frame; no retry was sent.')
    return root / 'observations' / session / ('frame-' + str(frame_id).zfill(4) + '.json')


def validate_latest_observation(latest, session, mission_frame):
    """Allow later internal safety frames without substituting them for the mission result."""
    latest_frame = latest.get('frameId') if isinstance(latest, dict) else None
    if (not isinstance(latest, dict) or latest.get('session') != session
            or isinstance(latest_frame, bool) or not isinstance(latest_frame, int)
            or latest_frame < mission_frame):
        raise RuntimeError('Latest observation is not from the same session at or after this request result; inspect status. No retry was sent.')
    return latest_frame


def wait_for_controller_quiescence(root, session, process_id, windows_session_id, mission_frame,
                                   *, timeout_seconds=5, stable_seconds=0.4):
    """Wait separately for this controller to settle after the immutable request receipt."""
    deadline = time.monotonic() + timeout_seconds
    quiet_since = None
    quiet_frame = None
    last_state = 'unknown'
    while time.monotonic() < deadline:
        try:
            heartbeat = read(root / 'controller-status.json')
            latest = read(root / 'observation.json')
        except (OSError, json.JSONDecodeError):
            heartbeat, latest = None, None
        now_ms = int(time.time() * 1000)
        heartbeat_at = heartbeat.get('heartbeatAt') if isinstance(heartbeat, dict) else None
        frame_id = heartbeat.get('frameId') if isinstance(heartbeat, dict) else None
        valid_identity = (isinstance(heartbeat, dict)
                          and heartbeat.get('version') == 1
                          and heartbeat.get('processId') == process_id
                          and heartbeat.get('windowsSessionId') == windows_session_id
                          and heartbeat.get('remoteDesktop') is True
                          and heartbeat.get('session') == session
                          and isinstance(heartbeat_at, int) and not isinstance(heartbeat_at, bool)
                          and 0 <= now_ms - heartbeat_at <= HEARTBEAT_MAX_AGE_MS
                          and isinstance(frame_id, int) and not isinstance(frame_id, bool)
                          and frame_id >= mission_frame)
        try:
            latest_frame = validate_latest_observation(latest, session, mission_frame)
        except RuntimeError:
            valid_identity = False
            latest_frame = None
        state = heartbeat.get('state') if isinstance(heartbeat, dict) else 'unknown'
        active_request = heartbeat.get('activeRequestId') if isinstance(heartbeat, dict) else None
        request_idle = active_request is None or active_request == ''
        stable_frame = frame_id == latest_frame
        if valid_identity and request_idle and stable_frame and state in ('idle', 'faulted', 'stopped'):
            last_state = state
            if quiet_since is None or frame_id != quiet_frame:
                quiet_since = time.monotonic()
                quiet_frame = frame_id
            if time.monotonic() - quiet_since >= stable_seconds:
                return {'controllerState': state, 'controllerQuiescent': True,
                        'latestFrameId': latest_frame}
        else:
            quiet_since = None
            quiet_frame = None
            if isinstance(state, str):
                last_state = state
        time.sleep(0.1)
    return {'controllerState': last_state, 'controllerQuiescent': False}


def compact_ocr(rows):
    """Drop UID text and numeric account-ID rows from the HUD's bottom-right UID area."""
    rows = rows if isinstance(rows, list) else []
    uid_rows = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        text = str(row.get('text', '')).strip()
        if re.fullmatch(r'(?:UID|UD|U1D|ID)\s*:?\s*(?:\d{6,})?', text, re.IGNORECASE):
            uid_rows.append((index, row))
            continue
        x, y = row.get('x'), row.get('y')
        bottom_right_uid_area = (isinstance(x, (int, float)) and isinstance(y, (int, float))
                                 and x >= 1650 and y >= 1040)
        if bottom_right_uid_area and re.fullmatch(r'(?:(?:UID|UD|U1D|ID)\s*)?:?\s*\d{6,}',
                                                   text, re.IGNORECASE):
            uid_rows.append((index, row))

    excluded = {index for index, _ in uid_rows}
    for _, uid in uid_rows:
        uid_x = uid.get('x')
        uid_y = uid.get('y')
        uid_width = uid.get('width', 0)
        if not all(isinstance(value, (int, float)) for value in (uid_x, uid_y, uid_width)):
            continue
        for index, row in enumerate(rows):
            if index in excluded or not isinstance(row, dict):
                continue
            if not re.fullmatch(r'\d{6,}', str(row.get('text', '')).strip()):
                continue
            x, y = row.get('x'), row.get('y')
            if not all(isinstance(value, (int, float)) for value in (x, y)):
                continue
            gap = x - (uid_x + uid_width)
            if -4 <= gap <= 40 and abs(y - uid_y) <= 8:
                excluded.add(index)

    return [row for index, row in enumerate(rows) if index not in excluded]


def compact_terminal(submitted_id, receipt, observation, screenshot):
    details = receipt.get('details') if isinstance(receipt.get('details'), dict) else {}
    return {
        'submittedId': submitted_id,
        'terminalId': receipt.get('id'),
        'status': receipt.get('status'),
        'reason': details.get('reason'),
        'result': details.get('result'),
        'elapsedMs': details.get('elapsedMs'),
        'session': observation.get('session'),
        'frameId': observation.get('frameId'),
        'screenshot': screenshot,
        'hud': observation.get('hud'),
        'ocr': compact_ocr(observation.get('ocr')),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mission', choices=['observe', 'stop', 'keyPress', 'look', 'navigation', 'dialogue', 'combat', 'recover', 'questStep', 'cancel'])
    parser.add_argument('--session', required=True)
    parser.add_argument('--expected-windows-session-id', required=True, type=int,
                        help='explicitly pin the exact verified BetterGI RDP child session')
    parser.add_argument('--frame', type=int)
    parser.add_argument('--key')
    parser.add_argument('--dx', type=int, help='bounded camera-look delta (-250..250, excluding zero)')
    parser.add_argument('--route', type=Path)
    parser.add_argument('--objective')
    parser.add_argument('--step')
    parser.add_argument('--deadline-ms', type=int, default=60000)
    parser.add_argument('--wait-seconds', type=int, default=15)
    parser.add_argument('--compact', action='store_true',
                        help='print a compact terminal receipt and filtered latest observation')
    args = parser.parse_args()
    if args.mission == 'cancel':
        try:
            require_live_controller(ROOT, args.session, None, args.expected_windows_session_id,
                                    allow_active=True, allow_faulted=True)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        atomic(ROOT / 'stop.json', {'session': args.session, 'createdAt': int(time.time() * 1000)})
        print('Cancellation requested; inspect terminal receipt before issuing another mission.')
        return
    observation = read(ROOT / 'observation.json')
    if observation['session'] != args.session or observation['frameId'] != args.frame:
        raise SystemExit('Session/frame changed: inspect the current observation.')
    try:
        fault_recovery_command = (args.mission in ('observe', 'stop', 'recover')
                                  or (args.mission == 'questStep' and args.step == 'wolfPause'))
        controller_heartbeat = require_live_controller(ROOT, args.session, args.frame,
                                                       args.expected_windows_session_id,
                                                       allow_faulted=fault_recovery_command)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    request = dict(session=args.session, expectedFrameId=args.frame,
                   id='mission-' + uuid.uuid4().hex, createdAt=int(time.time() * 1000), mission=args.mission)
    if args.mission == 'keyPress':
        request['key'] = args.key
    if args.mission == 'look':
        if args.dx is None or args.dx == 0 or not -250 <= args.dx <= 250:
            raise SystemExit('--dx must be a nonzero integer from -250 through 250')
        request['dx'] = args.dx
    if args.mission == 'combat':
        request['objective'] = args.objective
        request['deadlineMs'] = args.deadline_ms
    if args.mission == 'questStep':
        if not args.step or not re.fullmatch(r'[a-z][A-Za-z0-9]{0,39}', args.step):
            raise SystemExit('--step must start lowercase and contain at most 40 ASCII letters/digits')
        request['step'] = args.step
    if args.mission == 'navigation':
        if not args.route:
            raise SystemExit('--route is required')
        route = read(args.route)
        request['waypoints'] = route['waypoints']
        request['objective'] = route['objective']
        request['deadlineMs'] = args.deadline_ms
    atomic(ROOT / 'request.json', request)
    print(json.dumps({'submitted': request['id'], 'session': args.session}), flush=True)
    deadline = time.monotonic() + args.wait_seconds
    while time.monotonic() < deadline:
        time.sleep(.2)
        try:
            receipt = read(request_receipt_path(ROOT, request['session'], request['id']))
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if not isinstance(receipt, dict):
            raise SystemExit('Request-specific receipt is not an object; inspect status. No retry was sent.')
        if receipt.get('id') == request['id']:
            if receipt.get('status') in ('started', 'running'):
                if (receipt.get('session') != request['session']
                        or receipt.get('mission') != request['mission']):
                    raise SystemExit('Matching receipt has the wrong session or mission; inspect controller status. No retry was sent.')
                continue
            try:
                mission_observation = read(observation_path(ROOT, request['session'], receipt.get('frameId')))
                latest = read(ROOT / 'observation.json')
            except (FileNotFoundError, json.JSONDecodeError, RuntimeError) as exc:
                raise SystemExit(f'Request receipt lacks a readable immutable observation; inspect status. No retry was sent. ({exc})') from exc
            try:
                mission_frame = validate_terminal_receipt(request, receipt, mission_observation)
                latest_frame = validate_latest_observation(latest, request['session'], mission_frame)
            except RuntimeError as exc:
                raise SystemExit(str(exc)) from exc
            settled = wait_for_controller_quiescence(
                ROOT, request['session'], controller_heartbeat['processId'],
                controller_heartbeat['windowsSessionId'], mission_frame)
            if settled.get('controllerQuiescent'):
                try:
                    latest = read(ROOT / 'observation.json')
                    latest_frame = validate_latest_observation(latest, request['session'], mission_frame)
                    settled['latestFrameId'] = latest_frame
                except (OSError, json.JSONDecodeError, RuntimeError) as exc:
                    raise SystemExit(f'Latest observation changed or became unreadable while the controller settled; inspect status. No retry was sent. ({exc})') from exc
            screenshot = str(ROOT / mission_observation['screenshotPath'])
            if args.compact:
                terminal = compact_terminal(request['id'], receipt, mission_observation, screenshot)
                terminal['latestFrameId'] = latest_frame
                terminal['controllerState'] = settled['controllerState']
                terminal['controllerQuiescent'] = settled['controllerQuiescent']
                print(json.dumps(terminal))
            else:
                print(json.dumps(receipt))
                print(json.dumps({'session': mission_observation['session'], 'frameId': mission_frame,
                                  'latestFrameId': latest_frame, 'screenshot': screenshot,
                                  'observation': mission_observation,
                                  'controllerState': settled['controllerState'],
                                  'controllerQuiescent': settled['controllerQuiescent']}))
            return
    print(json.dumps({'pending': request['id'],
                      'receiptPath': str(request_receipt_path(ROOT, request['session'], request['id'])),
                      'instruction': 'Poll this request receipt and current process. Do not replay or restart on timeout.'}))


if __name__ == '__main__':
    main()
