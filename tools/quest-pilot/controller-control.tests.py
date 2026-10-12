"""Focused tests for the controller CLI's restart preflight ordering."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch


MODULE_PATH = Path(__file__).with_name('controller-control.py')
SPEC = importlib.util.spec_from_file_location('controller_control', MODULE_PATH)
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


class RestartPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Path(self.temp.name)
        self.manifest = self.app.joinpath(*control.RESTART_MANIFEST)
        self.manifest.parent.mkdir(parents=True)
        self.target = str(self.app / 'release-r12' / 'BetterGI-English-win-x64')
        self.status = {'processId': 123, 'windowsSessionId': 5, 'instanceType': 'ChildSession',
                       'remoteDesktop': True, 'instanceNonce': 'nonce'}
        self.write_manifest({'version': 1, 'targetDirectory': self.target,
                             'exeSha256': 'a' * 64, 'dllSha256': 'b' * 64})

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self, value):
        self.manifest.write_text(json.dumps(value), encoding='utf-8')

    def test_preflight_passes_exact_target_without_shell(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '', ''))
        control.preflight_restart(123, 5, process_dir=self.app, status=self.status, runner=runner)
        args, kwargs = runner.call_args
        self.assertEqual(args[0][-2:], ['-AppDirectory', self.target])
        self.assertFalse(kwargs['shell'])
        self.assertEqual(kwargs['timeout'], 30)

    def test_missing_invalid_or_unavailable_preflight_fails_closed(self):
        self.manifest.unlink()
        with self.assertRaisesRegex(control.ControlError, 'restart was not dispatched'):
            control.preflight_restart(123, 5, process_dir=self.app, status=self.status)
        self.write_manifest({'version': 1, 'targetDirectory': 'relative/path'})
        with self.assertRaisesRegex(control.ControlError, 'restart was not dispatched'):
            control.preflight_restart(123, 5, process_dir=self.app, status=self.status)
        self.write_manifest({'version': 1, 'targetDirectory': self.target})
        runner = Mock(return_value=subprocess.CompletedProcess([], 1, '', 'sensitive detail'))
        with self.assertRaisesRegex(control.ControlError, 'restart was not dispatched'):
            control.preflight_restart(123, 5, process_dir=self.app, status=self.status, runner=runner)
        self.assertNotIn('sensitive detail', str(runner.call_args))

    def test_windows_powershell_utf8_bom_manifest_is_supported(self):
        self.manifest.write_text(json.dumps({'version': 1, 'targetDirectory': self.target}), encoding='utf-8-sig')
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '', ''))
        control.preflight_restart(123, 5, process_dir=self.app, status=self.status, runner=runner)
        self.assertEqual(runner.call_args.args[0][-1], self.target)

    def test_explicit_directory_is_read_only_fallback_bound_to_verified_status(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '', ''))
        original = control.process_directory
        try:
            control.process_directory = Mock(side_effect=control.ControlError('access denied'))
            control.preflight_restart(123, 5, app_directory=self.app, status=self.status, runner=runner)
            self.assertEqual(runner.call_args.args[0][-1], self.target)
            with self.assertRaisesRegex(control.ControlError, 'restart was not dispatched'):
                control.preflight_restart(999, 5, app_directory=self.app, status=self.status, runner=runner)
        finally:
            control.process_directory = original

    def test_user_root_environment_path_is_fallback_when_process_query_fails(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '', ''))
        with patch.dict('os.environ', {'BETTERGI_PILOT_APP_DIR': str(self.app)}):
            with patch.object(control, 'process_directory', side_effect=control.ControlError('access denied')):
                control.preflight_restart(123, 5, status=self.status, runner=runner)
        self.assertEqual(runner.call_args.args[0][-1], self.target)

    def test_restart_preflight_occurs_after_status_and_before_mutation(self):
        calls = []
        def fake_exchange(request, process_id, session_id, **kwargs):
            calls.append(request['command'])
            if request['command'] == 'status':
                return {'instanceNonce': 'nonce', 'processId': 123, 'windowsSessionId': 5,
                        'instanceType': 'ChildSession', 'remoteDesktop': True}
            return {'pilotState': 'restarting'}

        original_exchange = control.exchange
        original_preflight = control.preflight_restart
        try:
            control.exchange = fake_exchange
            control.preflight_restart = lambda pid, session, **kwargs: calls.append('preflight')
            result = control.run('restartApp', 123, 5)
        finally:
            control.exchange = original_exchange
            control.preflight_restart = original_preflight
        self.assertEqual(calls, ['status', 'preflight', 'restartApp'])
        self.assertEqual(result['pilotState'], 'restarting')

    def test_preflight_failure_prevents_restart_mutation(self):
        calls = []
        def fake_exchange(request, process_id, session_id, **kwargs):
            calls.append(request['command'])
            return {'instanceNonce': 'nonce'}

        original_exchange = control.exchange
        original_preflight = control.preflight_restart
        try:
            control.exchange = fake_exchange
            def fail(_pid, _session, **_kwargs):
                raise control.ControlError('preflight failed')
            control.preflight_restart = fail
            with self.assertRaisesRegex(control.ControlError, 'preflight failed'):
                control.run('restartApp', 123, 5)
        finally:
            control.exchange = original_exchange
            control.preflight_restart = original_preflight
        self.assertEqual(calls, ['status'])


if __name__ == '__main__':
    unittest.main()
