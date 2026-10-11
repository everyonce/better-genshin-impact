import contextlib
import importlib.util
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / 'tools/quest-pilot/act-one-command.py'
spec = importlib.util.spec_from_file_location('act_one_command_faulted_gate', CLI)
command = importlib.util.module_from_spec(spec)
spec.loader.exec_module(command)


class FaultedCommandGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'ActOnePilot'
        self.root.mkdir()
        self.old_root = command.ROOT
        command.ROOT = self.root
        self.addCleanup(setattr, command, 'ROOT', self.old_root)
        self.heartbeat = {'version': 1, 'processId': 456, 'windowsSessionId': 6,
                          'remoteDesktop': True, 'session': 'session-a',
                          'state': 'faulted', 'heartbeatAt': 10000, 'frameId': 9}
        self.write_heartbeat()
        (self.root / 'observation.json').write_text(
            json.dumps({'session': 'session-a', 'frameId': 9}), encoding='utf-8')

    def write_heartbeat(self, **patch):
        (self.root / 'controller-status.json').write_text(
            json.dumps({**self.heartbeat, **patch}), encoding='utf-8')

    def test_faulted_state_requires_explicit_allow_and_keeps_frame_session_process_proofs(self):
        verifier = mock.Mock()
        accepted = command.require_live_controller(
            self.root, 'session-a', 9, 6, now_ms=10000,
            process_verifier=verifier, allow_faulted=True)
        self.assertEqual(accepted['state'], 'faulted')
        verifier.assert_called_once_with(456, 6)
        with self.assertRaisesRegex(RuntimeError, 'faulted'):
            command.require_live_controller(
                self.root, 'session-a', 9, 6, now_ms=10000,
                process_verifier=mock.Mock())
        for patch, expected_session, expected_frame in [
                ({'heartbeatAt': 4000}, 6, 9),
                ({'session': 'other'}, 6, 9),
                ({'windowsSessionId': 7}, 6, 9),
                ({}, 6, 8)]:
            with self.subTest(patch=patch, expected_session=expected_session,
                              expected_frame=expected_frame):
                self.write_heartbeat(**patch)
                with self.assertRaises(RuntimeError):
                    command.require_live_controller(
                        self.root, 'session-a', expected_frame, expected_session,
                        now_ms=10000, process_verifier=mock.Mock(), allow_faulted=True)

    def test_access_denied_fallback_accepts_only_matching_fresh_owned_faulted_status(self):
        verifier = mock.Mock(side_effect=command.ProcessAccessDenied('denied'))
        status = {'processId': 456, 'windowsSessionId': 6, 'instanceType': 'ChildSession',
                  'remoteDesktop': True, 'serviceOwnsPilot': True,
                  'scriptSession': 'session-a', 'frameId': 9,
                  'scriptState': 'faulted', 'pilotState': 'faulted',
                  'heartbeatAtUnixMs': 10000}
        query = mock.Mock(return_value=status)
        result = command.require_live_controller(
            self.root, 'session-a', 9, 6, now_ms=10000,
            process_verifier=verifier, service_status_query=query, allow_faulted=True)
        self.assertEqual(result['processId'], 456)
        query.assert_called_once_with(456, 6)
        for patch in ({'processId': 999}, {'windowsSessionId': 7},
                      {'scriptSession': 'other'}, {'frameId': 8},
                      {'scriptState': 'idle'}, {'pilotState': 'idle'},
                      {'serviceOwnsPilot': False}, {'heartbeatAtUnixMs': 4999}):
            with self.subTest(patch=patch):
                with self.assertRaisesRegex(RuntimeError, 'service status did not confirm'):
                    command.require_live_controller(
                        self.root, 'session-a', 9, 6, now_ms=10000,
                        process_verifier=verifier,
                        service_status_query=mock.Mock(return_value={**status, **patch}),
                        allow_faulted=True)

    def test_cli_faulted_exception_is_only_the_recovery_allowlist(self):
        eligible = [
            ['observe'], ['stop'], ['recover'], ['questStep', '--step', 'wolfPause'],
            ['cancel'],
        ]
        ineligible = [
            ['keyPress', '--key', 'W'], ['look', '--dx', '5'], ['dialogue'],
            ['combat', '--objective', 'anything'], ['questStep', '--step', 'wolfContinue'],
        ]
        for case, expected in [(eligible, True), (ineligible, False)]:
            for mission_args in case:
                with self.subTest(mission=mission_args[0]):
                    checked = mock.Mock(return_value={})
                    argv = [*mission_args, '--session', 'session-a',
                            '--expected-windows-session-id', '6', '--frame', '9',
                            '--wait-seconds', '0']
                    with mock.patch('sys.argv', ['act-one-command.py', *argv]), \
                         mock.patch.object(command, 'require_live_controller', checked), \
                         contextlib.redirect_stdout(io.StringIO()):
                        command.main()
                    self.assertEqual(checked.call_args.kwargs['allow_faulted'], expected)


if __name__ == '__main__':
    unittest.main()
