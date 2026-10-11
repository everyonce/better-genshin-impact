"""Read or explicitly start/stop the supervised ActOnePilot in one BetterGI RDP child."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import struct
import time
import uuid

MAX_MESSAGE = 8192
PIPE_PREFIX = 'BetterGI.ExternalControl'
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
READ_CONTROL = 0x00020000
TOKEN_QUERY = 0x0008
TOKEN_USER = 1
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_IO_PENDING = 997
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
FILE_FLAG_OVERLAPPED = 0x40000000
IO_TIMEOUT_SECONDS = 6.0


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ('Internal', ctypes.c_size_t),
        ('InternalHigh', ctypes.c_size_t),
        ('Offset', wintypes.DWORD),
        ('OffsetHigh', wintypes.DWORD),
        ('hEvent', wintypes.HANDLE),
    ]


class ControlError(RuntimeError):
    pass


class WinPipeApi:
    """Small ctypes wrapper; kept separate so protocol tests do not need Windows."""
    def __init__(self, *, kernel32=None, advapi32=None, get_last_error=None):
        if (kernel32 is None or advapi32 is None) and os.name != 'nt':
            raise ControlError('Controller control is available only on the Windows RDP host.')
        self.kernel32 = kernel32 or ctypes.WinDLL('kernel32', use_last_error=True)
        self.advapi32 = advapi32 or ctypes.WinDLL('advapi32', use_last_error=True)
        self._get_last_error = get_last_error or ctypes.get_last_error
        self.deadline = time.monotonic() + IO_TIMEOUT_SECONDS
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL

    @staticmethod
    def error(prefix):
        return ControlError(f'{prefix} (Windows error {ctypes.get_last_error()}).')

    def connect(self, pipe_name):
        self.kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        self.kernel32.WaitNamedPipeW.restype = wintypes.BOOL
        wait_ms = min(2000, self._remaining_ms())
        if wait_ms <= 0 or not self.kernel32.WaitNamedPipeW(pipe_name, wait_ms):
            raise self.error(f'Control pipe unavailable: {pipe_name}')
        self.kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                              wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self.kernel32.CreateFileW.restype = wintypes.HANDLE
        handle = self.kernel32.CreateFileW(pipe_name, 0xC0000000 | READ_CONTROL, 0, None, 3, FILE_FLAG_OVERLAPPED, None)
        if handle == wintypes.HANDLE(-1).value:
            raise self.error(f'Could not open control pipe: {pipe_name}')
        return handle

    def server_pid(self, handle):
        pid = wintypes.ULONG()
        self.kernel32.GetNamedPipeServerProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
        self.kernel32.GetNamedPipeServerProcessId.restype = wintypes.BOOL
        if not self.kernel32.GetNamedPipeServerProcessId(handle, ctypes.byref(pid)):
            raise self.error('Could not identify the named-pipe server process')
        return pid.value

    def server_session(self, handle):
        session = wintypes.DWORD()
        self.kernel32.GetNamedPipeServerSessionId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
        self.kernel32.GetNamedPipeServerSessionId.restype = wintypes.BOOL
        if not self.kernel32.GetNamedPipeServerSessionId(handle, ctypes.byref(session)):
            raise self.error('Could not identify the named-pipe server Windows session')
        return session.value

    def _user_sid(self, process_handle):
        token = wintypes.HANDLE()
        self.advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        self.advapi32.OpenProcessToken.restype = wintypes.BOOL
        self.advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
                                                       wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        self.advapi32.GetTokenInformation.restype = wintypes.BOOL
        if not self.advapi32.OpenProcessToken(process_handle, TOKEN_QUERY, ctypes.byref(token)):
            raise self.error('Could not open process token for SID verification')
        try:
            needed = wintypes.DWORD()
            self.advapi32.GetTokenInformation(token, TOKEN_USER, None, 0, ctypes.byref(needed))
            if needed.value == 0 or ctypes.get_last_error() != ERROR_INSUFFICIENT_BUFFER:
                raise self.error('Could not size process-token SID query')
            storage = ctypes.create_string_buffer(needed.value)
            if not self.advapi32.GetTokenInformation(token, TOKEN_USER, storage, needed, ctypes.byref(needed)):
                raise self.error('Could not read process-token SID')
            sid_pointer = ctypes.cast(storage, ctypes.POINTER(ctypes.c_void_p))[0]
            return sid_pointer, storage
        finally:
            self.kernel32.CloseHandle(token)

    def verify_same_user(self, pipe_handle):
        self.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        current = self.kernel32.GetCurrentProcess()
        current_sid, current_storage = self._user_sid(current)
        owner_sid = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        self.advapi32.GetSecurityInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD,
                                                  ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
                                                  ctypes.c_void_p, ctypes.c_void_p,
                                                  ctypes.POINTER(ctypes.c_void_p)]
        self.advapi32.GetSecurityInfo.restype = wintypes.DWORD
        # SE_KERNEL_OBJECT=6, OWNER_SECURITY_INFORMATION=1. The connected pipe
        # handle has READ_CONTROL; the returned descriptor owns the SID storage.
        result = self.advapi32.GetSecurityInfo(pipe_handle, 6, 1, ctypes.byref(owner_sid),
                                               None, None, None, ctypes.byref(descriptor))
        if result != 0:
            raise ControlError(f'Could not verify control-pipe owner SID (Windows error {result}).')
        try:
            self.advapi32.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            self.advapi32.EqualSid.restype = wintypes.BOOL
            if not self.advapi32.EqualSid(current_sid, owner_sid):
                raise ControlError('Control-pipe server belongs to a different Windows user.')
        finally:
            self.kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
            self.kernel32.LocalFree.restype = wintypes.HLOCAL
            self.kernel32.LocalFree(descriptor)

    def current_user_sid(self):
        self.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        sid_pointer, _storage = self._user_sid(self.kernel32.GetCurrentProcess())
        string_sid = wintypes.LPWSTR()
        self.advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        self.advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
        if not self.advapi32.ConvertSidToStringSidW(sid_pointer, ctypes.byref(string_sid)):
            raise self.error('Could not format current Windows user SID')
        try:
            return string_sid.value
        finally:
            self.kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
            self.kernel32.LocalFree.restype = wintypes.HLOCAL
            self.kernel32.LocalFree(string_sid)

    def _remaining_ms(self):
        return max(0, int((self.deadline - time.monotonic()) * 1000))

    def _perform_overlapped(self, handle, operation, buffer, size):
        self.kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel32.CreateEventW.restype = wintypes.HANDLE
        event = self.kernel32.CreateEventW(None, True, False, None)
        if not event:
            raise self.error('Could not create a named-pipe I/O event')
        try:
            overlapped = OVERLAPPED()
            overlapped.hEvent = event
            count = wintypes.DWORD()
            function = getattr(self.kernel32, operation)
            if operation == 'ReadFile':
                function.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                     ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED)]
            else:
                function.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                                     ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED)]
            function.restype = wintypes.BOOL
            completed = function(handle, buffer, size, ctypes.byref(count), ctypes.byref(overlapped))
            if completed:
                return count.value
            if self._get_last_error() != ERROR_IO_PENDING:
                raise self.error(f'{operation} failed')

            self.kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.kernel32.WaitForSingleObject.restype = wintypes.DWORD
            wait_result = self.kernel32.WaitForSingleObject(event, self._remaining_ms())
            if wait_result != WAIT_OBJECT_0:
                self.kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED)]
                self.kernel32.CancelIoEx.restype = wintypes.BOOL
                self.kernel32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED),
                                                               ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
                self.kernel32.GetOverlappedResult.restype = wintypes.BOOL
                self.kernel32.CancelIoEx(handle, ctypes.byref(overlapped))
                # Drain the canceled operation before closing its event or pipe handle.
                self.kernel32.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(count), True)
                if wait_result == WAIT_TIMEOUT:
                    raise ControlError('Named-pipe I/O timed out after 6 seconds. The command outcome may be unknown; query status before any mutation. No retry was sent.')
                raise self.error('Waiting for named-pipe I/O failed; the operation was canceled and drained.')
            self.kernel32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED),
                                                           ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
            self.kernel32.GetOverlappedResult.restype = wintypes.BOOL
            if not self.kernel32.GetOverlappedResult(handle, ctypes.byref(overlapped), ctypes.byref(count), False):
                raise self.error(f'{operation} did not complete successfully')
            return count.value
        finally:
            self.kernel32.CloseHandle(event)

    def write(self, handle, data):
        buffer = ctypes.create_string_buffer(data)
        count = self._perform_overlapped(handle, 'WriteFile', buffer, len(data))
        if count != len(data):
            raise ControlError('Control-pipe request was only partially written; command was not resent.')

    def read(self, handle, size):
        buffer = ctypes.create_string_buffer(size)
        count = self._perform_overlapped(handle, 'ReadFile', buffer, size)
        return buffer.raw[:count]

    def close(self, handle):
        self.kernel32.CloseHandle(handle)


def read_exact(api, handle, size):
    chunks = []
    remaining = size
    while remaining:
        chunk = api.read(handle, remaining)
        if not chunk:
            raise ControlError('Control pipe closed before the complete response arrived.')
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def exchange(request, process_id, windows_session_id, *, api=None, clock_ms=None):
    """Send one framed request after verifying pipe PID, WTS session, and user SID."""
    command = request.get('command') if isinstance(request, dict) else None
    if command not in ('status', 'startPilot', 'stopPilot', 'restartApp'):
        raise ControlError('Only status, startPilot, stopPilot, and restartApp are supported.')
    if process_id <= 0 or windows_session_id != 5:
        raise ControlError('Specify a positive BetterGI PID and the required RDP Windows session 5.')
    allowed_fields = {'command'}
    if command != 'status':
        allowed_fields.update(('targetProcessId', 'targetWindowsSessionId', 'targetNonce'))
    if any(key not in allowed_fields | {'version', 'requestId', 'createdAtUnixMs'} for key in request):
        raise ControlError('Control request contains unsupported fields; executable paths and arguments are not accepted.')
    if command == 'status':
        if any(key in request for key in ('targetProcessId', 'targetWindowsSessionId', 'targetNonce')):
            raise ControlError('Status is read-only and does not accept target fields.')
    elif (request.get('targetProcessId') != process_id
          or request.get('targetWindowsSessionId') != windows_session_id
          or not isinstance(request.get('targetNonce'), str)
          or not request['targetNonce']):
        raise ControlError('Mutating command requires the exact target PID, RDP session, and instance nonce.')
    api = WinPipeApi() if api is None else api
    user_sid = api.current_user_sid()
    sid_hash = hashlib.sha256(user_sid.encode('utf-8')).hexdigest()[:16].upper()
    pipe_name = f'\\\\.\\pipe\\{PIPE_PREFIX}.{sid_hash}.{windows_session_id}.{process_id}'
    request = dict(request)
    request.setdefault('version', 1)
    request.setdefault('requestId', str(uuid.uuid4()))
    request.setdefault('createdAtUnixMs', int(time.time() * 1000) if clock_ms is None else clock_ms)
    payload = json.dumps(request, separators=(',', ':')).encode('utf-8')
    if len(payload) > MAX_MESSAGE:
        raise ControlError('Control request exceeds 8192 bytes.')
    handle = api.connect(pipe_name)
    try:
        server_pid = api.server_pid(handle)
        if server_pid != process_id:
            raise ControlError(f'Pipe server PID {server_pid} does not match requested BetterGI PID {process_id}.')
        server_session = api.server_session(handle)
        if server_session != windows_session_id:
            raise ControlError(f'Pipe server is in Windows session {server_session}, not requested session {windows_session_id}.')
        api.verify_same_user(handle)
        api.write(handle, struct.pack('<I', len(payload)) + payload)
        size = struct.unpack('<I', read_exact(api, handle, 4))[0]
        if size <= 0 or size > MAX_MESSAGE:
            raise ControlError('Control response exceeds 8192 bytes.')
        try:
            response = json.loads(read_exact(api, handle, size).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ControlError('Control server returned invalid JSON.') from exc
    finally:
        api.close(handle)
    if not isinstance(response, dict) or response.get('version') != 1 or response.get('requestId') != request['requestId']:
        raise ControlError('Control response version or request ID does not match.')
    if response.get('success') is not True:
        code = response.get('errorCode', 'unknown')
        message = response.get('message', 'Control command failed.')
        raise ControlError(f'{code}: {message}')
    status = response.get('status')
    if not isinstance(status, dict):
        raise ControlError('Control response has no status object.')
    if status.get('processId') != process_id or status.get('windowsSessionId') != windows_session_id:
        raise ControlError('Control response identifies a different BetterGI process or Windows session.')
    return status


def run(command, process_id, windows_session_id, *, api=None):
    if command not in ('status', 'startPilot', 'stopPilot', 'restartApp'):
        raise ControlError('Only status, startPilot, stopPilot, and restartApp are supported.')
    if command == 'status':
        return exchange({'command': command}, process_id, windows_session_id, api=api)
    status = exchange({'command': 'status'}, process_id, windows_session_id, api=api)
    if (status.get('instanceType') != 'ChildSession' or status.get('remoteDesktop') is not True
            or not isinstance(status.get('instanceNonce'), str) or not status['instanceNonce']):
        raise ControlError('Target is not a verified BetterGI RDP child with a valid instance nonce.')
    if command == 'stopPilot' and status.get('serviceOwnsPilot') is not True:
        raise ControlError('The supervised service does not own the active pilot; it will not stop unrelated work.')
    return exchange({'command': command, 'targetProcessId': process_id,
                     'targetWindowsSessionId': windows_session_id,
                     'targetNonce': status['instanceNonce']},
                    process_id, windows_session_id, api=api)


def format_result(command, status):
    if command == 'restartApp':
        return {
            'accepted': status.get('pilotState') == 'restarting',
            'state': 'handoff_pending',
            'message': 'The replacement launch was accepted; readiness of the new BetterGI instance has not been verified.',
            'status': status,
        }
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'startPilot', 'stopPilot', 'restartApp'])
    parser.add_argument('--process-id', required=True, type=int,
                        help='exact BetterGI child PID in the RDP session')
    parser.add_argument('--windows-session-id', required=True, type=int,
                        help='exact Windows RDP session ID; ActOnePilot requires 5')
    args = parser.parse_args()
    if args.process_id <= 0 or args.windows_session_id != 5:
        raise SystemExit('Specify the live BetterGI PID and required RDP Windows session 5 explicitly.')
    try:
        status = run(args.command, args.process_id, args.windows_session_id)
    except ControlError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(format_result(args.command, status), sort_keys=True))


if __name__ == '__main__':
    main()
