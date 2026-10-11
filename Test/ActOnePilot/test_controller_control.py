import importlib.util
import hashlib
import json
import struct
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'tools' / 'quest-pilot' / 'controller-control.py'
spec = importlib.util.spec_from_file_location('controller_control', SCRIPT)
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class FakePipeApi:
    def __init__(self, *, pid=1234, session=5, statuses=None):
        self.pid = pid
        self.session = session
        self.statuses = list(statuses or [])
        self.handle = object()
        self.pipe_name = None
        self.requests = []
        self.response = b''
        self.same_user_checks = []
        self.closed = []

    def current_user_sid(self):
        return 'S-1-5-21-100-200-300-1001'

    def connect(self, name):
        self.pipe_name = name
        return self.handle

    def server_pid(self, _handle):
        return self.pid

    def server_session(self, _handle):
        return self.session

    def verify_same_user(self, handle):
        self.same_user_checks.append(handle)

    def write(self, _handle, data):
        size = struct.unpack('<I', data[:4])[0]
        request = json.loads(data[4:4 + size])
        self.requests.append(request)
        status = self.statuses.pop(0) if self.statuses else {
            'processId': 1234, 'windowsSessionId': 5, 'instanceType': 'ChildSession',
            'remoteDesktop': True, 'pipeName': self.pipe_name, 'instanceNonce': 'nonce-1',
            'pilotState': 'idle', 'serviceOwnsPilot': True,
        }
        response = {'version': 1, 'requestId': request['requestId'], 'success': True, 'status': status}
        payload = json.dumps(response, separators=(',', ':')).encode()
        self.response = struct.pack('<I', len(payload)) + payload

    def read(self, _handle, size):
        result, self.response = self.response[:min(size, 3)], self.response[min(size, 3):]
        return result

    def close(self, handle):
        self.closed.append(handle)


class FakeFunction:
    def __init__(self, result=None, on_call=None):
        self.argtypes = None
        self.restype = None
        self.result = result
        self.on_call = on_call
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.on_call(*args) if self.on_call else self.result


class FakeKernel32:
    def __init__(self, *, wait_result=control.WAIT_TIMEOUT):
        self.CreateEventW = FakeFunction(77)
        self.CloseHandle = FakeFunction(True)
        self.WriteFile = FakeFunction(False)
        self.ReadFile = FakeFunction(False)
        self.WaitForSingleObject = FakeFunction(wait_result)
        self.CancelIoEx = FakeFunction(True)
        self.GetOverlappedResult = FakeFunction(True)


class ControllerControlTests(unittest.TestCase):
    def test_recovery_commands_use_exact_verified_target_without_paths_or_arguments(self):
        for command in ('installRecoveryLauncher', 'restartHost', 'shutdownApp'):
            with self.subTest(command=command):
                api = FakePipeApi()
                control.run(command, 1234, 5, api=api)
                self.assertEqual([r['command'] for r in api.requests], ['status', command])
                self.assertEqual(api.requests[1]['targetNonce'], 'nonce-1')
                self.assertEqual(set(api.requests[1]), {
                    'command', 'targetProcessId', 'targetWindowsSessionId', 'targetNonce',
                    'version', 'requestId', 'createdAtUnixMs'})
                with self.assertRaisesRegex(control.ControlError, 'executable paths and arguments'):
                    control.exchange({'command': command, 'path': 'C:/untrusted.exe'}, 1234, 5, api=api)

    def test_host_recovery_acknowledgment_does_not_claim_readiness(self):
        result = control.format_result('restartHost', {'hostRecoveryState': 'launch_dispatched'})
        self.assertTrue(result['accepted'])
        self.assertEqual(result['state'], 'host_handoff_pending')
        self.assertIn('verify', result['message'])

    def test_status_uses_exact_child_pipe_and_sends_read_only_request(self):
        api = FakePipeApi()
        status = control.run('status', 1234, 5, api=api)
        expected_sid_hash = hashlib.sha256(api.current_user_sid().encode()).hexdigest()[:16].upper()
        self.assertEqual(api.pipe_name, rf'\\.\pipe\BetterGI.ExternalControl.{expected_sid_hash}.5.1234')
        self.assertEqual(api.requests[0]['command'], 'status')
        self.assertNotIn('targetNonce', api.requests[0])
        self.assertEqual(api.same_user_checks, [api.handle])
        self.assertEqual(status['processId'], 1234)

    def test_start_uses_nonce_from_fresh_target_status_and_only_named_operation(self):
        api = FakePipeApi()
        status = control.run('startPilot', 1234, 5, api=api)
        self.assertEqual([request['command'] for request in api.requests], ['status', 'startPilot'])
        self.assertEqual(api.requests[1]['targetProcessId'], 1234)
        self.assertEqual(api.requests[1]['targetWindowsSessionId'], 5)
        self.assertEqual(api.requests[1]['targetNonce'], 'nonce-1')
        self.assertTrue(status['serviceOwnsPilot'])

    def test_restart_app_forwards_verified_target_nonce_and_reports_handoff_pending(self):
        api = FakePipeApi(statuses=[
            {'processId': 1234, 'windowsSessionId': 5, 'instanceType': 'ChildSession',
             'remoteDesktop': True, 'instanceNonce': 'restart-nonce',
             'pilotState': 'idle', 'serviceOwnsPilot': False},
            {'processId': 1234, 'windowsSessionId': 5, 'instanceType': 'ChildSession',
             'remoteDesktop': True, 'instanceNonce': 'restart-nonce',
             'pilotState': 'restarting', 'serviceOwnsPilot': False},
        ])
        status = control.run('restartApp', 1234, 5, api=api)
        self.assertEqual([request['command'] for request in api.requests], ['status', 'restartApp'])
        self.assertEqual(api.requests[1]['targetProcessId'], 1234)
        self.assertEqual(api.requests[1]['targetWindowsSessionId'], 5)
        self.assertEqual(api.requests[1]['targetNonce'], 'restart-nonce')
        self.assertEqual(set(api.requests[1]), {
            'command', 'targetProcessId', 'targetWindowsSessionId', 'targetNonce',
            'version', 'requestId', 'createdAtUnixMs',
        })
        result = control.format_result('restartApp', status)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['state'], 'handoff_pending')
        self.assertIn('readiness', result['message'])
        self.assertEqual(result['status'], status)

    def test_restart_app_mutation_is_never_retried_after_transport_error(self):
        class RestartTimesOut(FakePipeApi):
            def write(self, handle, data):
                request = json.loads(data[4:4 + struct.unpack('<I', data[:4])[0]])
                super().write(handle, data)
                if request['command'] == 'restartApp':
                    raise control.ControlError('simulated transport timeout')

        api = RestartTimesOut()
        with self.assertRaisesRegex(control.ControlError, 'simulated transport timeout'):
            control.run('restartApp', 1234, 5, api=api)
        self.assertEqual([request['command'] for request in api.requests], ['status', 'restartApp'])

    def test_restart_app_rejects_path_and_argument_fields(self):
        with self.assertRaisesRegex(control.ControlError, 'executable paths and arguments'):
            control.exchange({'command': 'restartApp', 'targetProcessId': 1234,
                              'targetWindowsSessionId': 5, 'targetNonce': 'n',
                              'path': 'C:/untrusted/BetterGI.exe'}, 1234, 5, api=FakePipeApi())

    def test_stop_refuses_pilot_not_owned_by_supervisor(self):
        api = FakePipeApi(statuses=[{
            'processId': 1234, 'windowsSessionId': 5, 'instanceType': 'ChildSession',
            'remoteDesktop': True, 'instanceNonce': 'nonce-1', 'serviceOwnsPilot': False,
        }])
        with self.assertRaisesRegex(control.ControlError, 'will not stop unrelated work'):
            control.run('stopPilot', 1234, 5, api=api)
        self.assertEqual([request['command'] for request in api.requests], ['status'])

    def test_refuses_pipe_from_wrong_pid_session_or_user(self):
        with self.assertRaisesRegex(control.ControlError, 'server PID'):
            control.exchange({'command': 'status'}, 1234, 5, api=FakePipeApi(pid=9999))
        with self.assertRaisesRegex(control.ControlError, 'Windows session'):
            control.exchange({'command': 'status'}, 1234, 5, api=FakePipeApi(session=2))

        class WrongUser(FakePipeApi):
            def verify_same_user(self, _pid):
                raise control.ControlError('different Windows user')

        with self.assertRaisesRegex(control.ControlError, 'different Windows user'):
            control.exchange({'command': 'status'}, 1234, 5, api=WrongUser())

    def test_refuses_response_from_different_process_session_or_request(self):
        wrong_process = FakePipeApi(statuses=[{'processId': 8, 'windowsSessionId': 5}])
        with self.assertRaisesRegex(control.ControlError, 'different BetterGI process'):
            control.exchange({'command': 'status'}, 1234, 5, api=wrong_process)

        api = FakePipeApi()
        original_write = api.write

        def wrong_request_id(handle, data):
            original_write(handle, data)
            response_size = struct.unpack('<I', api.response[:4])[0]
            response = json.loads(api.response[4:4 + response_size])
            response['requestId'] = 'different'
            payload = json.dumps(response).encode()
            api.response = struct.pack('<I', len(payload)) + payload

        api.write = wrong_request_id
        with self.assertRaisesRegex(control.ControlError, 'request ID'):
            control.exchange({'command': 'status'}, 1234, 5, api=api)

    def test_mutations_reject_non_child_or_non_remote_desktop_target(self):
        api = FakePipeApi(statuses=[{
            'processId': 1234, 'windowsSessionId': 5, 'instanceType': 'Main',
            'remoteDesktop': False, 'instanceNonce': 'nonce-1', 'serviceOwnsPilot': True,
        }])
        with self.assertRaisesRegex(control.ControlError, 'not a verified BetterGI RDP child'):
            control.run('startPilot', 1234, 5, api=api)
        self.assertEqual(len(api.requests), 1)

    def test_no_arbitrary_pipe_operation_or_non_session_five_target(self):
        api = FakePipeApi()
        with self.assertRaisesRegex(control.ControlError, 'Only status'):
            control.run('restart', 1234, 5, api=api)
        with self.assertRaisesRegex(control.ControlError, 'session ID above 1'):
            control.run('status', 1234, 1, api=api)
        self.assertEqual(api.requests, [])

    def test_programmatic_target_ids_must_be_positive_integers(self):
        for process_id, session_id in [(True, 6), (1234, True), ('1234', 6), (1234, '6'), (0, 6), (1234, 0), (1234, 1)]:
            with self.subTest(process_id=process_id, session_id=session_id):
                api = FakePipeApi()
                with self.assertRaisesRegex(control.ControlError, 'session ID above 1'):
                    control.run('status', process_id, session_id, api=api)
                self.assertEqual(api.requests, [])

    def test_windows_close_handle_prototype_is_pointer_sized(self):
        kernel = FakeKernel32()
        native = control.WinPipeApi(kernel32=kernel, advapi32=object(), get_last_error=lambda: 0)
        self.assertEqual(kernel.CloseHandle.argtypes, [control.wintypes.HANDLE])
        self.assertEqual(kernel.CloseHandle.restype, control.wintypes.BOOL)
        native.close(0x123456789ABC)
        self.assertEqual(kernel.CloseHandle.calls[-1][0], 0x123456789ABC)

    def test_pipe_identity_uses_server_session_and_owner_sid_without_opening_server_process(self):
        kernel = FakeKernel32()
        kernel.GetNamedPipeServerSessionId = FakeFunction(True)
        kernel.GetCurrentProcess = FakeFunction(99)
        kernel.LocalFree = FakeFunction(None)
        advapi = type('FakeAdvapi', (), {'GetSecurityInfo': FakeFunction(5),
                                         'EqualSid': FakeFunction(True)})()
        native = control.WinPipeApi(kernel32=kernel, advapi32=advapi, get_last_error=lambda: 0)
        native.server_session(0x123456789ABC)
        self.assertEqual(kernel.GetNamedPipeServerSessionId.argtypes,
                         [control.wintypes.HANDLE, control.ctypes.POINTER(control.wintypes.ULONG)])
        native._user_sid = lambda _handle: (123, object())
        with self.assertRaisesRegex(control.ControlError, 'Could not verify control-pipe owner SID'):
            native.verify_same_user(0x123456789ABC)
        self.assertFalse(hasattr(kernel, 'OpenProcess'), 'pipe authentication must not open the elevated server process')

    def test_overlapped_pipe_reads_and_writes_cancel_at_deadline_without_retry(self):
        for operation in ('read', 'write'):
            with self.subTest(operation=operation):
                kernel = FakeKernel32(wait_result=control.WAIT_TIMEOUT)
                native = control.WinPipeApi(kernel32=kernel, advapi32=object(),
                                            get_last_error=lambda: control.ERROR_IO_PENDING)
                with self.assertRaisesRegex(control.ControlError, 'timed out after 6 seconds'):
                    if operation == 'read':
                        native.read(88, 16)
                    else:
                        native.write(88, b'one request')
                call_count = len(kernel.ReadFile.calls) if operation == 'read' else len(kernel.WriteFile.calls)
                self.assertEqual(call_count, 1, 'timed out transport must not retry the operation')
                self.assertEqual(len(kernel.CancelIoEx.calls), 1)
                self.assertGreaterEqual(kernel.WaitForSingleObject.calls[-1][1], 0)
                self.assertLessEqual(kernel.WaitForSingleObject.calls[-1][1], 6000)
                self.assertEqual(kernel.GetOverlappedResult.calls[-1][-1], True,
                                 'drain canceled overlapped I/O before releasing event handle')
                self.assertTrue(any(call[0] == 77 for call in kernel.CloseHandle.calls))


if __name__ == '__main__':
    unittest.main()
