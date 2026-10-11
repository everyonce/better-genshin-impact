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
        heartbeat = {'version': 1, 'processId': 456, 'windowsSessionId': 6, 'remoteDesktop': True,
                     'session': 'session-a', 'state': 'idle', 'heartbeatAt': 10000, 'frameId': 9}
        heartbeat.update(overrides)
        (self.root / 'controller-status.json').write_text(json.dumps(heartbeat), encoding='utf-8')

    def run_cli(self, argv, *, sleep=None):
        output = io.StringIO()
        with mock.patch('sys.argv', ['act-one-command.py', *argv]), \
                mock.patch.object(command, 'require_live_controller', return_value={
                    'processId': 456, 'windowsSessionId': 6}), \
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
            mission_observation = dict(self.observation, frameId=10,
                                       screenshotPath='observations/session-a/frame-0010.png')
            latest = dict(self.observation, frameId=11,
                          screenshotPath='observations/session-a/frame-0011.png')
            observation_dir = self.root / 'observations/session-a'
            observation_dir.mkdir(parents=True, exist_ok=True)
            (observation_dir / 'frame-0010.json').write_text(json.dumps(mission_observation), encoding='utf-8')
            receipt_dir = self.root / 'receipts/session-a'
            receipt_dir.mkdir(parents=True, exist_ok=True)
            (receipt_dir / (request['id'] + '.json')).write_text(json.dumps(receipt), encoding='utf-8')
            # Simulate an automatic internal pause overwriting the shared latest receipt.
            (self.root / 'receipt.json').write_text(json.dumps({'id': 'idle-safety-wolfPause-session-a-1',
                'session': 'session-a', 'mission': 'questStep', 'status': 'stopped', 'frameId': 10}), encoding='utf-8')
            (self.root / 'observation.json').write_text(json.dumps(latest), encoding='utf-8')
            self.write_heartbeat(state='idle', frameId=11, heartbeatAt=int(time.time() * 1000))

        output = self.run_cli(['observe', '--session', 'session-a', '--expected-windows-session-id', '6', '--frame', '9', '--compact', '--wait-seconds', '2'], sleep=complete)
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
        self.assertEqual(compact['latestFrameId'], 11)
        self.assertTrue(compact['screenshot'].endswith('frame-0010.png'))
        self.assertEqual(compact['hud'], self.observation['hud'])
        self.assertEqual(compact['ocr'], [self.observation['ocr'][0], self.observation['ocr'][-1]])
        self.assertNotIn('inputEvents', compact)
        self.assertNotIn('observation', compact)

    def test_pending_output_never_replays_or_changes_request(self):
        output = self.run_cli(['observe', '--session', 'session-a', '--expected-windows-session-id', '6', '--frame', '9', '--compact', '--wait-seconds', '0'])
        lines = [json.loads(line) for line in output.splitlines()]
        request = json.loads((self.root / 'request.json').read_text(encoding='utf-8'))
        self.assertEqual(lines[0]['submitted'], request['id'])
        self.assertEqual(lines[1]['pending'], request['id'])
        self.assertIn(request['id'], lines[1]['receiptPath'])
        self.assertIn('Do not replay', lines[1]['instruction'])
        self.assertEqual(request['expectedFrameId'], 9)

    def test_missing_heartbeat_fails_before_request_write_but_cancel_remains_available(self):
        (self.root / 'controller-status.json').unlink()
        with mock.patch('sys.argv', ['act-one-command.py', 'observe', '--session', 'session-a', '--expected-windows-session-id', '6', '--frame', '9']), \
                mock.patch.object(command.time, 'sleep', return_value=None):
            with self.assertRaisesRegex(SystemExit, 'heartbeat is missing or invalid'):
                command.main()
        self.assertFalse((self.root / 'request.json').exists())
        with mock.patch('sys.argv', ['act-one-command.py', 'cancel', '--session', 'session-a', '--expected-windows-session-id', '6']), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, 'heartbeat is missing or invalid'):
                command.main()
        self.write_heartbeat(state='running')
        service_status = {'processId':456,'windowsSessionId':6,'instanceType':'ChildSession',
                          'remoteDesktop':True,'serviceOwnsPilot':True,'scriptSession':'session-a',
                          'scriptState':'running','pilotState':'running','frameId':12,'heartbeatAtUnixMs':10000}
        real_check = command.require_live_controller
        def checked_cancel(root, session, frame, expected_session, *, allow_active=False, allow_faulted=False):
            return real_check(root, session, frame, expected_session, now_ms=10000,
                              process_verifier=mock.Mock(), service_status_query=mock.Mock(return_value=service_status),
                              allow_active=allow_active, allow_faulted=allow_faulted)
        with mock.patch('sys.argv', ['act-one-command.py', 'cancel', '--session', 'session-a', '--expected-windows-session-id', '6']), \
                mock.patch.object(command, 'require_live_controller', side_effect=checked_cancel), contextlib.redirect_stdout(io.StringIO()):
            command.main()
        self.assertTrue((self.root / 'stop.json').exists())

    def test_active_cancel_ignores_frame_churn_but_requires_fresh_pinned_owned_rdp_session(self):
        self.write_heartbeat(state='running', frameId=20)
        good_status = {'processId':456,'windowsSessionId':6,'instanceType':'ChildSession',
                       'remoteDesktop':True,'serviceOwnsPilot':True,'scriptSession':'session-a',
                       'scriptState':'running','pilotState':'running','frameId':21,'heartbeatAtUnixMs':10000}
        accepted = command.require_live_controller(self.root, 'session-a', None, 6, now_ms=10000,
                                                   process_verifier=mock.Mock(),
                                                   service_status_query=mock.Mock(return_value=good_status),
                                                   allow_active=True)
        self.assertEqual(accepted['session'], 'session-a')
        for heartbeat_patch, expected_session, status_patch in [
            ({}, 5, {}),
            ({}, 1, {}),
            ({'remoteDesktop':False}, 6, {}),
            ({'heartbeatAt':4999}, 6, {}),
            ({}, 6, {'scriptSession':'other'}),
            ({}, 6, {'remoteDesktop':False}),
            ({}, 6, {'serviceOwnsPilot':False}),
            ({}, 6, {'heartbeatAtUnixMs':4999}),
        ]:
            with self.subTest(heartbeat=heartbeat_patch, status=status_patch):
                self.write_heartbeat(state='running', frameId=20, **heartbeat_patch)
                with self.assertRaises(RuntimeError):
                    command.require_live_controller(self.root, 'session-a', None, expected_session, now_ms=10000,
                                                    process_verifier=mock.Mock(),
                                                    service_status_query=mock.Mock(return_value={**good_status, **status_patch}),
                                                    allow_active=True)

    def test_heartbeat_gates_staleness_state_session_frame_and_pid_session(self):
        verifier = mock.Mock()
        good = command.require_live_controller(self.root, 'session-a', 9, 6, now_ms=10000, process_verifier=verifier)
        self.assertEqual(good['processId'], 456)
        verifier.assert_called_once_with(456, 6)
        for patch, message in [
            ({'heartbeatAt': 4999}, 'stale'),
            ({'heartbeatAt': 10001}, 'stale'),
            ({'state': 'running'}, 'not idle'),
            ({'state': 'stopped'}, 'stopped'),
            ({'state': 'faulted'}, 'faulted'),
            ({'session': 'old'}, 'session changed'),
            ({'frameId': 8}, 'frame changed'),
            ({'windowsSessionId': 7}, 'explicitly pinned RDP child session'),
            ({'remoteDesktop': False}, 'does not prove a remote-desktop'),
        ]:
            self.write_heartbeat(**patch)
            with self.assertRaisesRegex(RuntimeError, message):
                command.require_live_controller(self.root, 'session-a', 9, 6, now_ms=10000, process_verifier=verifier)

    def test_access_denied_requires_matching_fresh_service_status_before_accepting(self):
        verifier = mock.Mock(side_effect=command.ProcessAccessDenied('denied'))
        status = {'processId': 456, 'windowsSessionId': 6, 'instanceType':'ChildSession', 'remoteDesktop':True, 'scriptSession': 'session-a',
                  'frameId': 9, 'scriptState': 'idle', 'pilotState': 'idle', 'heartbeatAtUnixMs': 10000}
        query = mock.Mock(return_value=status)
        result = command.require_live_controller(self.root, 'session-a', 9, 6, now_ms=10000,
                                                 process_verifier=verifier, service_status_query=query)
        self.assertEqual(result['processId'], 456)
        query.assert_called_once_with(456, 6)

        for patch in [
            {'processId': 999}, {'windowsSessionId': 2}, {'scriptSession': 'old'},
            {'frameId': 8}, {'scriptState': 'running'}, {'pilotState': 'faulted'},
            {'heartbeatAtUnixMs': 4999}, {'heartbeatAtUnixMs': 10001},
        ]:
            with self.subTest(patch=patch):
                bad_query = mock.Mock(return_value={**status, **patch})
                with self.assertRaisesRegex(RuntimeError, 'service status did not confirm'):
                    command.require_live_controller(self.root, 'session-a', 9, 6, now_ms=10000,
                                                    process_verifier=verifier,
                                                    service_status_query=bad_query)

    def test_only_access_denied_uses_service_status_fallback(self):
        verifier = mock.Mock(side_effect=RuntimeError('process exited'))
        query = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, 'process exited'):
            command.require_live_controller(self.root, 'session-a', 9, 6, now_ms=10000,
                                            process_verifier=verifier, service_status_query=query)
        query.assert_not_called()

    def test_service_heartbeat_freshness_uses_time_after_status_roundtrip(self):
        verifier = mock.Mock(side_effect=command.ProcessAccessDenied('denied'))
        status = {'processId': 456, 'windowsSessionId': 6, 'instanceType':'ChildSession', 'remoteDesktop':True, 'scriptSession': 'session-a',
                  'frameId': 9, 'scriptState': 'idle', 'pilotState': 'idle',
                  'heartbeatAtUnixMs': 10100}
        query = mock.Mock(return_value=status)
        with mock.patch.object(command.time, 'time', side_effect=[10.0, 10.1]):
            result = command.require_live_controller(self.root, 'session-a', 9, 6,
                                                     process_verifier=verifier,
                                                     service_status_query=query)
        self.assertEqual(result['processId'], 456)
        query.assert_called_once_with(456, 6)

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


class ControllerQuiescenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_state(self, state, active_request, frame):
        heartbeat = {'version': 1, 'processId': 456, 'windowsSessionId': 6,
                     'remoteDesktop': True, 'session': 'session-a', 'state': state,
                     'heartbeatAt': int(time.time() * 1000), 'frameId': frame,
                     'activeRequestId': active_request}
        observation = {'session': 'session-a', 'frameId': frame}
        (self.root / 'controller-status.json').write_text(json.dumps(heartbeat), encoding='utf-8')
        (self.root / 'observation.json').write_text(json.dumps(observation), encoding='utf-8')

    def test_faulted_internal_request_is_busy_until_same_controller_settles_at_final_frame(self):
        states = [
            ('faulted', 'idle-safety-wolfPause-session-a-5', 30),
            ('faulted', None, 31),
            ('idle', None, 32),
            ('idle', None, 32),
        ]
        self.write_state(*states[0])
        real_sleep = time.sleep

        def advance(_seconds):
            if states:
                self.write_state(*states.pop(0))
            real_sleep(0.1)

        with mock.patch.object(command.time, 'sleep', side_effect=advance):
            result = command.wait_for_controller_quiescence(
                self.root, 'session-a', 456, 6, 30, timeout_seconds=2, stable_seconds=0.15)
        self.assertTrue(result['controllerQuiescent'])
        self.assertEqual(result['controllerState'], 'idle')
        self.assertEqual(result['latestFrameId'], 32)

    def test_faulted_idle_remains_available_for_recovery_but_faulted_active_does_not_settle(self):
        self.write_state('faulted', None, 40)
        result = command.wait_for_controller_quiescence(
            self.root, 'session-a', 456, 6, 40, timeout_seconds=1, stable_seconds=0.08)
        self.assertTrue(result['controllerQuiescent'])
        self.assertEqual(result['controllerState'], 'faulted')

        self.write_state('faulted', 'idle-safety-wolfPause-session-a-6', 41)
        result = command.wait_for_controller_quiescence(
            self.root, 'session-a', 456, 6, 41, timeout_seconds=0.25, stable_seconds=0.05)
        self.assertFalse(result['controllerQuiescent'])
        self.assertEqual(result['controllerState'], 'faulted')


if __name__ == '__main__':
    unittest.main()
