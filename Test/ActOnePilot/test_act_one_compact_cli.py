import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / 'tools/quest-pilot/act-one-command.py'
spec = importlib.util.spec_from_file_location('act_one_command', CLI)
command = importlib.util.module_from_spec(spec)
spec.loader.exec_module(command)


class CompactCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'User/JsScript/ActOnePilot'
        self.root.mkdir(parents=True)
        self.old_root = command.ROOT
        command.ROOT = self.root
        self.addCleanup(setattr, command, 'ROOT', self.old_root)
        self.observation = {
            'session': 'session-a', 'frameId': 9, 'screenshotPath': 'observations/session-a/frame-0009.png',
            'hud': {'world': True, 'health': {'current': 100, 'max': 100}},
            'ocr': [
                {'text': 'Go to the gate', 'x': 30, 'y': 100, 'width': 150, 'height': 20},
                {'text': 'UID:', 'x': 1688, 'y': 1054, 'width': 41, 'height': 17},
                {'text': '123456789', 'x': 1726, 'y': 1052, 'width': 135, 'height': 23},
                {'text': 'UD:234567890', 'x': 1680, 'y': 1052, 'width': 120, 'height': 20},
                {'text': ':345678901', 'x': 1680, 'y': 1052, 'width': 110, 'height': 20},
                {'text': '456789012', 'x': 1730, 'y': 1052, 'width': 120, 'height': 20},
                {'text': '123456', 'x': 30, 'y': 200, 'width': 60, 'height': 20},
            ],
        }
        (self.root / 'observation.json').write_text(json.dumps(self.observation), encoding='utf-8')
        self.write_heartbeat()

    def write_heartbeat(self, **overrides):
        heartbeat = {'version': 1, 'processId': 456, 'windowsSessionId': 5,
                     'session': 'session-a', 'state': 'idle', 'heartbeatAt': 10000, 'frameId': 9}
        heartbeat.update(overrides)
        (self.root / 'controller-status.json').write_text(json.dumps(heartbeat), encoding='utf-8')

    def run_cli(self, argv, *, sleep=None):
        output = io.StringIO()
        with mock.patch('sys.argv', ['act-one-command.py', *argv]), \
                mock.patch.object(command, 'require_live_controller', return_value={}), \
                contextlib.redirect_stdout(output):
            if sleep is None:
                command.main()
            else:
                with mock.patch.object(command.time, 'sleep', side_effect=sleep):
                    command.main()
        return output.getvalue()

    def test_compact_terminal_keeps_result_and_fresh_frame_without_event_or_uid_dump(self):
        def complete(_seconds):
            request = json.loads((self.root / 'request.json').read_text(encoding='utf-8'))
            receipt = {'id': request['id'], 'session': 'session-a', 'mission': 'observe', 'status': 'completed',
                       'frameId': 10, 'details': {'elapsedMs': 321, 'result': {'status': 'observed'},
                                                'inputEvents': [{'type': 'rotate', 'dx': -750}]}}
            latest = dict(self.observation, frameId=10,
                          screenshotPath='observations/session-a/frame-0010.png')
            (self.root / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
            (self.root / 'observation.json').write_text(json.dumps(latest), encoding='utf-8')

        output = self.run_cli(['observe', '--session', 'session-a', '--frame', '9', '--compact', '--wait-seconds', '2'], sleep=complete)
        lines = [json.loads(line) for line in output.splitlines()]
        self.assertEqual(len(lines), 2)
        request = json.loads((self.root / 'request.json').read_text(encoding='utf-8'))
        compact = lines[-1]
        self.assertEqual(compact['submittedId'], request['id'])
        self.assertEqual(compact['terminalId'], request['id'])
        self.assertEqual(compact['status'], 'completed')
        self.assertEqual(compact['result'], {'status': 'observed'})
        self.assertEqual(compact['elapsedMs'], 321)
        self.assertEqual(compact['session'], 'session-a')
        self.assertEqual(compact['frameId'], 10)
        self.assertTrue(compact['screenshot'].endswith('frame-0010.png'))
        self.assertEqual(compact['hud'], self.observation['hud'])
        self.assertEqual(compact['ocr'], [self.observation['ocr'][0], self.observation['ocr'][-1]])
        self.assertNotIn('inputEvents', compact)
        self.assertNotIn('observation', compact)

    def test_pending_output_never_replays_or_changes_request(self):
        output = self.run_cli(['observe', '--session', 'session-a', '--frame', '9', '--compact', '--wait-seconds', '0'])
        lines = [json.loads(line) for line in output.splitlines()]
        request = json.loads((self.root / 'request.json').read_text(encoding='utf-8'))
        self.assertEqual(lines[0]['submitted'], request['id'])
        self.assertEqual(lines[1]['pending'], request['id'])
        self.assertIn('Do not replay', lines[1]['instruction'])
        self.assertEqual(request['expectedFrameId'], 9)

    def test_missing_heartbeat_fails_before_request_write_but_cancel_remains_available(self):
        (self.root / 'controller-status.json').unlink()
        with mock.patch('sys.argv', ['act-one-command.py', 'observe', '--session', 'session-a', '--frame', '9']), \
                mock.patch.object(command.time, 'sleep', return_value=None):
            with self.assertRaisesRegex(SystemExit, 'heartbeat is missing or invalid'):
                command.main()
        self.assertFalse((self.root / 'request.json').exists())
        with mock.patch('sys.argv', ['act-one-command.py', 'cancel', '--session', 'session-a']), \
                contextlib.redirect_stdout(io.StringIO()):
            command.main()
        self.assertTrue((self.root / 'stop.json').exists())

    def test_heartbeat_gates_staleness_state_session_frame_and_pid_session(self):
        verifier = mock.Mock()
        good = command.require_live_controller(self.root, 'session-a', 9, now_ms=10000, process_verifier=verifier)
        self.assertEqual(good['processId'], 456)
        verifier.assert_called_once_with(456, 5)
        for patch, message in [
            ({'heartbeatAt': 4999}, 'stale'),
            ({'heartbeatAt': 10001}, 'stale'),
            ({'state': 'running'}, 'not idle'),
            ({'state': 'stopped'}, 'stopped'),
            ({'state': 'faulted'}, 'faulted'),
            ({'session': 'old'}, 'session changed'),
            ({'frameId': 8}, 'frame changed'),
            ({'windowsSessionId': 7}, 'RDP session 5'),
        ]:
            self.write_heartbeat(**patch)
            with self.assertRaisesRegex(RuntimeError, message):
                command.require_live_controller(self.root, 'session-a', 9, now_ms=10000, process_verifier=verifier)

    def test_access_denied_requires_matching_fresh_service_status_before_accepting(self):
        verifier = mock.Mock(side_effect=command.ProcessAccessDenied('denied'))
        status = {'processId': 456, 'windowsSessionId': 5, 'scriptSession': 'session-a',
                  'frameId': 9, 'scriptState': 'idle', 'pilotState': 'idle', 'heartbeatAtUnixMs': 10000}
        query = mock.Mock(return_value=status)
        result = command.require_live_controller(self.root, 'session-a', 9, now_ms=10000,
                                                 process_verifier=verifier, service_status_query=query)
        self.assertEqual(result['processId'], 456)
        query.assert_called_once_with(456, 5)

        for patch in [
            {'processId': 999}, {'windowsSessionId': 2}, {'scriptSession': 'old'},
            {'frameId': 8}, {'scriptState': 'running'}, {'pilotState': 'faulted'},
            {'heartbeatAtUnixMs': 4999}, {'heartbeatAtUnixMs': 10001},
        ]:
            with self.subTest(patch=patch):
                bad_query = mock.Mock(return_value={**status, **patch})
                with self.assertRaisesRegex(RuntimeError, 'service status did not confirm'):
                    command.require_live_controller(self.root, 'session-a', 9, now_ms=10000,
                                                    process_verifier=verifier,
                                                    service_status_query=bad_query)

    def test_only_access_denied_uses_service_status_fallback(self):
        verifier = mock.Mock(side_effect=RuntimeError('process exited'))
        query = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, 'process exited'):
            command.require_live_controller(self.root, 'session-a', 9, now_ms=10000,
                                            process_verifier=verifier, service_status_query=query)
        query.assert_not_called()

    def test_service_heartbeat_freshness_uses_time_after_status_roundtrip(self):
        verifier = mock.Mock(side_effect=command.ProcessAccessDenied('denied'))
        status = {'processId': 456, 'windowsSessionId': 5, 'scriptSession': 'session-a',
                  'frameId': 9, 'scriptState': 'idle', 'pilotState': 'idle',
                  'heartbeatAtUnixMs': 10100}
        query = mock.Mock(return_value=status)
        with mock.patch.object(command.time, 'time', side_effect=[10.0, 10.1]):
            result = command.require_live_controller(self.root, 'session-a', 9,
                                                     process_verifier=verifier,
                                                     service_status_query=query)
        self.assertEqual(result['processId'], 456)
        query.assert_called_once_with(456, 5)

    def test_terminal_receipt_requires_id_session_mission_and_current_frame_match(self):
        request = {'id': 'r1', 'session': 's1', 'mission': 'observe'}
        receipt = {'id': 'r1', 'session': 's1', 'mission': 'observe', 'status': 'completed', 'frameId': 2}
        observation = {'session': 's1', 'frameId': 2}
        self.assertEqual(command.validate_terminal_receipt(request, receipt, observation), 2)
        for bad_receipt, bad_observation in [
            ({**receipt, 'id': 'old'}, observation),
            ({**receipt, 'session': 'old'}, observation),
            ({**receipt, 'mission': 'combat'}, observation),
            ({**receipt, 'status': 'started'}, observation),
            ({**receipt, 'frameId': True}, observation),
            (receipt, {'session': 'old', 'frameId': 2}),
            (receipt, {'session': 's1', 'frameId': 3}),
        ]:
            with self.assertRaises(RuntimeError):
                command.validate_terminal_receipt(request, bad_receipt, bad_observation)


if __name__ == '__main__':
    unittest.main()
