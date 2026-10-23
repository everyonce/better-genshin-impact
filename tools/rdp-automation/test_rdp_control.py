"""Protocol, target identity and hot-replacement ordering tests; no desktop actions."""
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import rdp_control as control


class FakePipe:
    """An in-memory framed peer with configurable authenticated identity."""
    def __init__(self, status=None):
        self.status = status or {'processId': 123, 'windowsSessionId': 2, 'instanceNonce': 'instance-a',
                                 'instanceType': 'Primary', 'automationEnabled': True}
        self.written = []
        self.pending = b''
        self.closed = False
        self.pid = 123
        self.session = 2

    def current_user_sid(self):
        return 'S-1-5-21-123'

    def connect(self, name):
        self.pipe_name = name
        return 1

    def server_pid(self, handle):
        return self.pid

    def server_session(self, handle):
        return self.session

    def verify_same_user(self, handle):
        pass

    def write(self, handle, data):
        self.written.append(data)
        self.request = json.loads(data[4:].decode('utf-8'))
        response = json.dumps({'version': 1, 'requestId': self.request['requestId'],
                               'success': True, 'status': self.status}).encode('utf-8')
        self.pending = struct.pack('<I', len(response)) + response

    def read(self, handle, count):
        chunk, self.pending = self.pending[:min(count, 7)], self.pending[min(count, 7):]
        return chunk

    def close(self, handle):
        self.closed = True


class ProtocolTests(unittest.TestCase):
    def test_console_json_preserves_unicode_paths_with_cp1252_and_ascii_stdout(self):
        report = {'copied': ['User/AutoFight/\u4e2d\u6587\u914d\u7f6e.txt'], 'reportFile': 'D:/stage/\u914d\u7f6e.json'}
        arguments = ['rdp_control.py', 'stage-config', '--source-directory', 'D:/source',
                     '--target-directory', 'D:/target']
        for encoding in ('cp1252', 'ascii'):
            with self.subTest(encoding=encoding):
                buffer = io.BytesIO()
                output = io.TextIOWrapper(buffer, encoding=encoding, errors='strict')
                with patch.object(sys, 'argv', arguments), patch.object(sys, 'stdout', output):
                    with patch.object(control, 'stage_configuration', return_value=report) as staging:
                        self.assertEqual(control.main(), 0)
                output.flush()
                self.assertEqual(json.loads(buffer.getvalue().decode(encoding)), report)
                staging.assert_called_once_with('D:/source', 'D:/target')
                output.close()

    def test_runner_uses_windowless_python_and_refuses_console_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            console = Path(directory) / 'python.exe'
            windowless = Path(directory) / 'pythonw.exe'
            console.write_bytes(b'fixture')
            with self.assertRaisesRegex(control.ControlError, 'pythonw.exe is required'):
                control.background_python(str(console))
            windowless.write_bytes(b'fixture')
            self.assertEqual(control.background_python(str(console)), windowless)
            self.assertEqual(control.background_python(str(windowless)), windowless)

    def test_root_console_status_and_nonce_pinned_mutation(self):
        api = FakePipe()
        status = control.exchange('status', 123, 2, api=api)
        self.assertEqual(status['instanceType'], 'Primary')
        self.assertNotIn('targetNonce', api.request)
        self.assertTrue(api.closed)
        first_id = api.request['requestId']
        control.exchange('startChildSession', 123, 2, nonce='instance-a', api=api)
        self.assertEqual(api.request['targetNonce'], 'instance-a')
        self.assertNotEqual(api.request['requestId'], first_id)
        self.assertEqual(struct.unpack('<I', api.written[-1][:4])[0], len(api.written[-1]) - 4)

    def test_wrong_pipe_peer_rejected_before_any_write(self):
        for field, value in (('pid', 999), ('session', 4)):
            api = FakePipe()
            setattr(api, field, value)
            with self.assertRaisesRegex(control.ControlError, 'does not match'):
                control.exchange('status', 123, 2, api=api)
            self.assertEqual(api.written, [])
            self.assertTrue(api.closed)

    def test_changed_response_nonce_rejected(self):
        with self.assertRaisesRegex(control.ControlError, 'instance changed'):
            control.exchange('showChildSession', 123, 2, nonce='old-instance', api=FakePipe())

    def test_unknown_fields_or_oversize_requests_never_connect(self):
        api = FakePipe()
        with self.assertRaises(control.ControlError):
            control.exchange('startChildSession', 123, 2, nonce='instance-a', fields={'arguments': []}, api=api)
        with self.assertRaisesRegex(control.ControlError, '8192'):
            control.exchange('launchChildCommand', 123, 2, nonce='instance-a', api=api,
                             fields={'executablePath': 'C:\\Python\\python.exe', 'arguments': ['界' * 3000],
                                     'workingDirectory': 'D:\\work', 'childSessionId': 3})
        self.assertFalse(hasattr(api, 'pipe_name'))

    def test_discovery_probes_only_current_user_and_keeps_session_one(self):
        sid = 'S-1-5-21-123'
        sid_hash = hashlib.sha256(sid.encode()).hexdigest()[:16].upper()
        names = [f'BetterGI.ExternalControl.{sid_hash}.1.123', 'BetterGI.ExternalControl.OTHER.2.456', 'other']
        calls = []
        result = control.discover(names=names, user_sid=sid,
                                  exchange_fn=lambda *args: calls.append(args) or {'processId': args[1]})
        self.assertEqual(calls, [('status', 123, 1)])
        self.assertEqual(len(result['instances']), 1)

    def test_role_requires_optin_and_actual_remote_child(self):
        for status in ({'automationEnabled': False},
                       {'automationEnabled': True, 'instanceType': 'ChildSession', 'remoteDesktop': False,
                        'instanceNonce': 'a'}):
            with self.assertRaises(control.ControlError):
                control.require_role(status, 'ChildSession')

    def test_io_failure_is_never_retried(self):
        api = FakePipe()
        api.read = lambda *_: (_ for _ in ()).throw(control.ControlError('timed out'))
        with self.assertRaisesRegex(control.ControlError, 'timed out'):
            control.exchange('startChildSession', 123, 2, nonce='instance-a', api=api)
        self.assertEqual(len(api.written), 1)


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.root = {'processId': 123, 'windowsSessionId': 2, 'instanceNonce': 'root',
                     'instanceType': 'Primary', 'automationEnabled': True,
                     'childSessionId': 3, 'childConnectedState': 1}
        self.child = {'processId': 456, 'windowsSessionId': 3, 'instanceNonce': 'child',
                      'instanceType': 'ChildSession', 'automationEnabled': True,
                      'remoteDesktop': True, 'rootProcessId': 123, 'runtimeRunning': False}

    def test_root_start_joins_pending_automatic_start_without_mutation(self):
        for state in ('connecting', 'launching_child', 'child_launch_dispatched'):
            with self.subTest(state=state):
                root = {**self.root, 'automationState': state}
                with patch.object(control, 'mutate') as mutation, patch.object(control, 'refresh', return_value=root):
                    with patch.object(control, 'discover', return_value={'instances': [self.child]}):
                        self.assertEqual(control.start_child(root, 1)['child'], self.child)
                mutation.assert_not_called()

    def test_start_game_joins_pending_start_or_returns_running_runtime(self):
        ready = {**self.child, 'runtimeRunning': True}
        with patch.object(control, 'mutate') as mutation, patch.object(control, 'wait_status', return_value=ready) as wait:
            self.assertEqual(control.start_game({**self.child, 'automationState': 'starting_game'}, 1), ready)
            wait.assert_called_once()
            self.assertEqual(control.start_game(ready, 1), ready)
            wait.assert_called_once()
        mutation.assert_not_called()

    def test_idle_start_dispatches_once_and_failed_join_reports_error(self):
        with patch.object(control, 'mutate') as mutation, patch.object(control, 'wait_status', return_value=self.child):
            control.start_game({**self.child, 'automationState': 'idle'}, 1)
            mutation.assert_called_once_with('startChildGame', {**self.child, 'automationState': 'idle'})
        for state in ('failed', 'cancelled'):
            failed = {**self.child, 'automationState': state, 'automationError': 'startup did not complete'}
            with patch.object(control, 'mutate') as mutation, patch.object(control, 'refresh', return_value=failed):
                with self.assertRaisesRegex(control.ControlError, 'startup did not complete'):
                    control.start_game({**self.child, 'automationState': 'starting_game'}, 1)
            mutation.assert_not_called()

    def test_startup_beginning_between_status_and_dispatch_is_joined_without_replay(self):
        pending = {**self.child, 'automationState': 'starting_game'}
        ready = {**pending, 'automationState': 'game_ready', 'runtimeRunning': True}
        with patch.object(control, 'mutate', side_effect=control.ControlError('automation_command_failed: already active')) as mutation:
            with patch.object(control, 'refresh', side_effect=[pending, ready]):
                result = control.start_game({**self.child, 'automationState': 'idle'}, 1)
        self.assertEqual(result, ready)
        mutation.assert_called_once()

    def test_dispatch_error_without_verified_pending_start_is_not_swallowed(self):
        idle = {**self.child, 'automationState': 'idle'}
        with patch.object(control, 'mutate', side_effect=control.ControlError('disabled: rejected')) as mutation:
            with patch.object(control, 'refresh', return_value=idle):
                with self.assertRaisesRegex(control.ControlError, 'disabled: rejected'):
                    control.start_game(idle, 1)
        mutation.assert_called_once()


class ReplacementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.current = self.root / 'release-r1/BetterGI-English-win-x64'
        self.target = self.root / 'release-r2/BetterGI-English-win-x64'
        for directory in (self.current, self.target):
            marker = directory / 'User/ExternalControl/enable-quest-control.json'
            marker.parent.mkdir(parents=True)
            marker.write_text(json.dumps({'version': 1, 'enabled': True, 'allowAppRestart': True}))
        options = {'runtimeOptions': {'tfm': 'net10.0', 'includedFrameworks': [
            {'name': 'Microsoft.NETCore.App', 'version': '10.0.0'},
            {'name': 'Microsoft.WindowsDesktop.App', 'version': '10.0.0'},
            {'name': 'Microsoft.AspNetCore.App', 'version': '10.0.0'}]}}
        (self.target / 'BetterGI.runtimeconfig.json').write_text(json.dumps(options))
        (self.target / 'BetterGI.deps.json').write_text(json.dumps({'runtimeTarget': {'name': '.NETCoreApp,Version=v10.0/win-x64'}}))
        for name in ('BetterGI.exe', 'BetterGI.dll', 'hostfxr.dll', 'hostpolicy.dll', 'coreclr.dll',
                     'System.Private.CoreLib.dll', 'PresentationFramework.dll'):
            (self.target / name).write_bytes(b'synthetic-test-fixture')
        self.child = {'processId': 50, 'windowsSessionId': 3, 'rootProcessId': 20,
                      'instanceNonce': 'old', 'instanceType': 'ChildSession', 'remoteDesktop': True,
                      'automationEnabled': True, 'appDirectory': str(self.current)}

    def tearDown(self):
        self.temp.cleanup()

    def test_manifest_hashes_and_runtime_preflight(self):
        manifest = control.prepare_replacement(str(self.current), str(self.target))
        self.assertEqual(manifest['dllSha256'], hashlib.sha256(b'synthetic-test-fixture').hexdigest())
        (self.target / 'hostfxr.dll').unlink()
        with self.assertRaisesRegex(control.ControlError, 'hostfxr'):
            control.prepare_replacement(str(self.current), str(self.target))

    def test_staging_preserves_new_scripts_and_defaults_while_copying_custom_config(self):
        (self.current / 'User/config.json').write_text('{"privateSetting":"fixture-do-not-print"}')
        for directory in ('JsScript/NewFeature', 'I18n', 'AutoFight'):
            (self.current / 'User' / directory).mkdir(parents=True, exist_ok=True)
            (self.target / 'User' / directory).mkdir(parents=True, exist_ok=True)
        (self.current / 'User/JsScript/NewFeature/main.js').write_text('old-script')
        (self.target / 'User/JsScript/NewFeature/main.js').write_text('new-script')
        (self.current / 'User/I18n/messages.json').write_text('{}')
        (self.current / 'User/AutoFight/default.txt').write_text('old-default')
        (self.target / 'User/AutoFight/default.txt').write_text('new-default')
        (self.current / 'User/AutoFight/custom.txt').write_text('custom-profile')
        report = control.stage_configuration(str(self.current), str(self.target))
        self.assertEqual((self.target / 'User/JsScript/NewFeature/main.js').read_text(), 'new-script')
        self.assertEqual((self.target / 'User/AutoFight/default.txt').read_text(), 'new-default')
        self.assertEqual((self.target / 'User/AutoFight/custom.txt').read_text(), 'custom-profile')
        self.assertFalse((self.target / 'User/I18n/messages.json').exists())
        self.assertIn('User/config.json', report['copied'])
        self.assertNotIn('fixture-do-not-print', json.dumps(report))

    def test_staging_conflicting_main_config_does_not_overwrite(self):
        (self.current / 'User/config.json').write_text('{"value":1}')
        (self.target / 'User/config.json').write_text('{"value":2}')
        with self.assertRaisesRegex(control.ControlError, 'different'):
            control.stage_configuration(str(self.current), str(self.target))
        self.assertEqual(json.loads((self.target / 'User/config.json').read_text())['value'], 2)

    def test_hot_replace_optin_preserves_unrelated_settings(self):
        path = self.current / 'User/ExternalControl/enable-quest-control.json'
        path.write_text(json.dumps({'version': 1, 'enabled': False, 'allowAppRestart': False, 'custom': 'preserved'}))
        control.enable_restart(str(self.current), str(self.target))
        marker = json.loads(path.read_text())
        self.assertEqual(marker['custom'], 'preserved')
        self.assertTrue(marker['enabled'])
        self.assertTrue(marker['allowAppRestart'])

    def test_bad_preflight_never_stops_tasks(self):
        (self.target / 'BetterGI.runtimeconfig.json').write_text('{"runtimeOptions":{"tfm":"net8.0"}}')
        with patch.object(control, 'mutate') as mutation:
            with self.assertRaises(control.ControlError):
                control.hot_replace(self.child, str(self.target), 1)
        mutation.assert_not_called()

    def test_stop_then_idle_then_restart_and_verify_new_binary(self):
        manifest = control.prepare_replacement(str(self.current), str(self.target))
        ready = {**self.child, 'processId': 51, 'instanceNonce': 'new', 'taskRunning': False, 'runtimeRunning': True,
                 'appDirectory': str(self.target), 'assemblySha256': manifest['dllSha256']}
        sequence = []
        with patch.object(control, 'mutate', side_effect=lambda command, *_: sequence.append(command)):
            with patch.object(control, 'wait_status', side_effect=lambda *_: sequence.append('idle') or self.child):
                with patch.object(control, 'discover', return_value={'instances': [ready]}):
                    result = control.hot_replace(self.child, str(self.target), 1)
        self.assertEqual(sequence, ['stopAutomationTasks', 'idle', 'restartApp'])
        self.assertTrue(result['ready'])
        self.assertTrue((self.current / 'User/ExternalControl/pending-restart.json').is_file())

    def test_incorrect_binary_does_not_report_ready(self):
        bad = {**self.child, 'processId': 51, 'instanceNonce': 'new', 'taskRunning': False,
               'appDirectory': str(self.target), 'assemblySha256': '0' * 64}
        with patch.object(control, 'mutate'), patch.object(control, 'wait_status', return_value=self.child):
            with patch.object(control, 'discover', return_value={'instances': [bad]}):
                with patch.object(control.time, 'monotonic', side_effect=[0, 0, 2]), patch.object(control.time, 'sleep'):
                    with self.assertRaisesRegex(control.ControlError, 'readiness was not verified'):
                        control.hot_replace(self.child, str(self.target), 1)

    def test_matching_binary_with_failed_game_reattachment_is_not_ready(self):
        manifest = control.prepare_replacement(str(self.current), str(self.target))
        failed = {**self.child, 'processId': 51, 'instanceNonce': 'new', 'taskRunning': False,
                  'appDirectory': str(self.target), 'assemblySha256': manifest['dllSha256'],
                  'runtimeRunning': False, 'automationState': 'failed', 'automationError': 'Game window missing'}
        with patch.object(control, 'mutate'), patch.object(control, 'wait_status', return_value=self.child):
            with patch.object(control, 'discover', return_value={'instances': [failed]}):
                with self.assertRaisesRegex(control.ControlError, 'Game window missing'):
                    control.hot_replace(self.child, str(self.target), 1)


if __name__ == '__main__':
    unittest.main()
