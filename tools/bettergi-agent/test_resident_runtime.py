"""CPU tests for resident run ownership, commands, and model reuse after interruption."""
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import resident_runtime as runtime


def child(**changes):
    """Create a synthetic authenticated lifecycle status without a live Windows process."""
    return dict(windowsSessionId=3, instanceType='ChildSession', remoteDesktop=True,
                automationEnabled=True, processId=123, instanceNonce='instance',
                runtimeRunning=True, automationState='game_ready', taskRunning=False,
                agentPipeName='BetterGI.Agent.test', **changes)


class ResidentTests(unittest.TestCase):
    def test_verified_hybrid_leg_limit_does_not_start_another_lease(self):
        with tempfile.TemporaryDirectory() as root:
            args = SimpleNamespace(output=str(Path(root)/'resident.json'), model='observe', rdp_session_id=3,
                control_file=None, seconds=3, reconnect_timeout=2, enable_input=True,
                segment_seconds=1, record_dir=None, max_input_actions=None)
            starts = []
            lifecycle = SimpleNamespace(discover=lambda: {'instances': [child()]},
                start_agent=lambda entry, *unused, **kwargs: starts.append(entry) or entry)

            def episode(segment, policy, control):
                runtime.atomic_json(segment.output, dict(endReason='hybridLegLimit',
                    framesReceived=30, acceptedInputActions=10))
                return 0

            with patch.object(runtime, 'require_current_rdp'), patch.object(runtime, 'control_module', return_value=lifecycle):
                self.assertEqual(runtime.run_resident(args, lambda _: None, episode), 0)
            summary = json.loads(Path(args.output).read_text())
            self.assertEqual(len(starts), 1)
            self.assertEqual(summary['endReason'], 'hybridLegLimit')
            self.assertEqual(summary['status'], 'completed')

    def test_healthy_file_rolls_do_not_rediscover_restart_or_reset_policy(self):
        import stream_client as client
        from test_stream_segments import ContinuousBridge, ContinuousPolicy
        from contextlib import redirect_stdout
        import io
        with tempfile.TemporaryDirectory() as root:
            args = client.parse_arguments(['--seconds', '2', '--segment-seconds', '.07', '--fps', '100',
                '--decision-hz', '10', '--enable-input', '--max-input-actions', '4', '--model', 'open-p2p',
                '--source', 'synthetic', '--checkpoint', 'synthetic', '--output', str(Path(root)/'run.json')])
            args.rdp_session_id = 3
            counts = {'starts': 0, 'discoveries': 0, 'loads': 0}
            policy = ContinuousPolicy()
            def discover():
                counts['discoveries'] += 1
                return {'instances': [child()]}
            def start(entry, *unused, **kwargs):
                counts['starts'] += 1
                return entry
            def load(_):
                counts['loads'] += 1
                return policy
            lifecycle = SimpleNamespace(discover=discover, start_agent=start)
            bridge = ContinuousBridge('synthetic')
            with patch.object(runtime, 'require_current_rdp'), patch.object(runtime, 'control_module', return_value=lifecycle), \
                    patch.object(runtime, 'verify_bridge_identity'), patch.object(client, 'Bridge', return_value=bridge), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(runtime.run_resident(args, load, client.run_episode), 0)
            summary = json.loads(Path(args.output).read_text())
            self.assertEqual(counts, {'starts': 1, 'discoveries': 1, 'loads': 1})
            self.assertEqual(policy.resets, 1)  # Only initial lease setup; never file rotation.
            self.assertEqual(summary['acceptedInputActions'], 4)
            self.assertEqual(summary['endReason'], 'maxInputActions')
            self.assertGreaterEqual(len(summary['segments']), 3)
            self.assertTrue(all(item['processId'] == 123 for item in summary['segments']))

    def test_lost_action_acknowledgement_is_terminal_without_another_start(self):
        with tempfile.TemporaryDirectory() as root:
            args = SimpleNamespace(output=str(Path(root)/'resident.json'), model='observe', rdp_session_id=3,
                control_file=None, seconds=3, reconnect_timeout=2, enable_input=True,
                segment_seconds=1, record_dir=None, max_input_actions=2)
            starts = []
            lifecycle = SimpleNamespace(discover=lambda: {'instances': [child()]},
                start_agent=lambda entry, *unused, **kwargs: starts.append(entry) or entry)
            def episode(segment, policy, control):
                runtime.atomic_json(segment.lease_output, {'segments': [{'number': 1, 'report': segment.output,
                    'acceptedInputActions': 0, 'exitCode': 1}], 'acceptedInputActions': 0, 'framesReceived': 1,
                    'recordedBytes': 0, 'recordingBudgetExhausted': False, 'endReason': 'error',
                    'unacknowledgedAction': 'original-request'})
                raise EOFError('lost action response')
            with patch.object(runtime, 'require_current_rdp'), patch.object(runtime, 'control_module', return_value=lifecycle):
                with self.assertRaisesRegex(RuntimeError, 'without replay'):
                    runtime.run_resident(args, lambda _: None, episode)
            self.assertEqual(len(starts), 1)
            summary = json.loads(Path(args.output).read_text())
            self.assertEqual(summary['status'], 'failed')
            self.assertIn('original-request', summary['error'])

    def test_failed_final_lease_is_not_reported_as_success_at_action_cap(self):
        for failure in ('stopError', 'streamError', 'captureError', 'recordingError'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as root:
                args = SimpleNamespace(output=str(Path(root)/'resident.json'), model='observe', rdp_session_id=3,
                    control_file=None, seconds=3, reconnect_timeout=2, enable_input=True,
                    segment_seconds=1, record_dir=None, max_input_actions=2)
                starts = []
                lifecycle = SimpleNamespace(discover=lambda: {'instances': [child()]},
                    start_agent=lambda entry, *unused, **kwargs: starts.append(entry) or entry)
                def episode(segment, policy, control):
                    runtime.atomic_json(segment.lease_output, {'status': 'failed', 'segments': [{'number': 1,
                        'report': segment.output, 'acceptedInputActions': 2, 'exitCode': 1, 'error': failure}],
                        'acceptedInputActions': 2, 'framesReceived': 1, 'recordedBytes': 0,
                        'recordingBudgetExhausted': False, 'endReason': 'maxInputActions'})
                    return 1
                with patch.object(runtime, 'require_current_rdp'), patch.object(runtime, 'control_module', return_value=lifecycle):
                    self.assertEqual(runtime.run_resident(args, lambda _: None, episode), 1)
                summary = json.loads(Path(args.output).read_text())
                self.assertEqual(len(starts), 1)
                self.assertEqual(summary['status'], 'failed')
                self.assertFalse(summary['evidenceComplete'])
                self.assertEqual(summary['failedLeases'], 1)
                self.assertEqual(summary['segments'][0]['error'], failure)
                self.assertEqual(summary['endReason'], 'maxInputActions')

    def test_manifest_failure_after_healthy_rollovers_is_fatal_with_full_action_total(self):
        import stream_client as client
        from test_stream_segments import ContinuousBridge, ContinuousPolicy
        from contextlib import redirect_stdout
        import io
        with tempfile.TemporaryDirectory() as root:
            args = client.parse_arguments(['--seconds', '2', '--segment-seconds', '.07', '--fps', '100',
                '--decision-hz', '10', '--enable-input', '--max-input-actions', '4', '--model', 'open-p2p',
                '--source', 'synthetic', '--checkpoint', 'synthetic', '--output', str(Path(root)/'run.json')])
            args.rdp_session_id = 3
            starts = []
            lifecycle = SimpleNamespace(discover=lambda: {'instances': [child()]},
                start_agent=lambda entry, *unused, **kwargs: starts.append(entry) or entry)
            bridge = ContinuousBridge('synthetic')
            original = Path.write_text
            def write(path, *args, **kwargs):
                if path.name == 'lease-00001.tmp':
                    raise OSError('synthetic manifest publication failure')
                return original(path, *args, **kwargs)
            with patch.object(runtime, 'require_current_rdp'), patch.object(runtime, 'control_module', return_value=lifecycle), \
                    patch.object(runtime, 'verify_bridge_identity'), patch.object(client, 'Bridge', return_value=bridge), \
                    patch.object(Path, 'write_text', write), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, 'Cannot publish lease manifest'):
                    runtime.run_resident(args, lambda _: ContinuousPolicy(), client.run_episode)
            summary = json.loads(Path(args.output).read_text())
            self.assertEqual(len(starts), 1)
            self.assertEqual(summary['acceptedInputActions'], 4)
            self.assertEqual(summary['status'], 'failed')
            self.assertGreaterEqual(len(summary['segments']), 3)
            self.assertLess(summary['segments'][0]['acceptedInputActions'], 4)

    def test_lost_start_acknowledgement_joins_verified_listener_without_replaying_start(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)/'resident.json'
            args = SimpleNamespace(output=str(output), model='observe', rdp_session_id=3, control_file=None,
                                   seconds=3, reconnect_timeout=2, enable_input=True,
                                   segment_seconds=1, record_dir=None, max_input_actions=1)
            counts = {'starts': 0}
            class LostAcknowledgement(Exception):
                pass
            def discover():
                state = child()
                if counts['starts']:
                    state.update(taskRunning=True, agentStreamState='listening', agentStreamRunning=True,
                                 agentInputEnabled=True)
                return {'instances': [state]}
            def start(*args, **kwargs):
                counts['starts'] += 1
                raise LostAcknowledgement('simulated lost response')
            def episode(segment, policy, control):
                runtime.atomic_json(segment.output, {'framesReceived': 1, 'acceptedInputActions': 1})
                return 0
            lifecycle = SimpleNamespace(discover=discover, start_agent=start, ControlError=LostAcknowledgement)
            with patch.object(runtime, 'require_current_rdp'), patch.object(runtime, 'control_module', return_value=lifecycle):
                runtime.run_resident(args, lambda _: None, episode)
            result = json.loads(output.read_text())
            self.assertEqual(counts['starts'], 1)
            self.assertEqual(result['acceptedInputActions'], 1)
            self.assertEqual(result['connectionErrors'], ['simulated lost response'])

    def test_child_selection_never_falls_back_to_console_or_another_session(self):
        expected = child()
        console = dict(expected, windowsSessionId=2, instanceType='Primary', remoteDesktop=False)
        unrelated = dict(expected, windowsSessionId=4)
        self.assertIs(runtime.select_child([console, unrelated, expected], 3), expected)
        self.assertIsNone(runtime.select_child([console, unrelated], 3))
        with self.assertRaisesRegex(RuntimeError, 'Multiple'):
            runtime.select_child([expected, dict(expected, processId=456)], 3)

    def test_missing_invalid_and_foreign_commands_pause(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'control.json'
            self.assertEqual(runtime.read_command(path, 'run')[0], 'pause')
            for payload in ('{', '[]', 'x'*2049, '{"version":1,"runId":"other","command":"run"}'):
                path.write_text(payload)
                command, error = runtime.read_command(path, 'run')
                self.assertEqual(command, 'pause')
                self.assertTrue(error)
            runtime.atomic_json(path, {'version': 1, 'runId': 'run', 'command': 'run'})
            self.assertEqual(runtime.read_command(path, 'run'), ('run', None))

    def test_stop_is_latched_and_existing_authority_file_is_not_reused(self):
        with tempfile.TemporaryDirectory() as root:
            path, status = Path(root)/'control.json', Path(root)/'status.json'
            control = runtime.ResidentControl(path, status, 'run')
            try:
                with self.assertRaises(FileExistsError):
                    runtime.ResidentControl(path, status, 'different')
                runtime.atomic_json(path, {'version': 1, 'runId': 'run', 'command': 'stop'})
                deadline = time.monotonic()+2
                while control.snapshot()[0] != 'stop' and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(control.snapshot()[0], 'stop')
                runtime.atomic_json(path, {'version': 1, 'runId': 'run', 'command': 'run'})
                time.sleep(.15)
                self.assertEqual(control.snapshot()[0], 'stop')
            finally:
                control.close()
            self.assertFalse(control.worker.is_alive())

    def test_reconnect_reuses_model_but_resets_history_and_honors_global_action_cap(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)/'resident.json'
            args = SimpleNamespace(output=str(output), model='observe', rdp_session_id=3, control_file=None,
                                   seconds=3, reconnect_timeout=1, enable_input=True,
                                   segment_seconds=1, record_dir=None, max_input_actions=2)
            counts = {'loads': 0, 'resets': 0, 'segments': 0}
            def reset():
                counts['resets'] += 1
            policy = SimpleNamespace(reset=reset)
            def load(_):
                counts['loads'] += 1
                return policy
            def episode(segment, actual_policy, control):
                self.assertIs(actual_policy, policy)
                self.assertEqual(segment.expected_process_id, 123)
                counts['segments'] += 1
                self.assertEqual(segment.max_input_actions, 3-counts['segments'])
                runtime.atomic_json(segment.output, {'framesReceived': 3, 'acceptedInputActions': 1,
                    'endReason': 'streamError' if counts['segments'] == 1 else 'maxInputActions'})
                if counts['segments'] == 1:
                    from bridge_transport import pipe_eof
                    raise pipe_eof('simulated hot replacement')
                return 0
            lifecycle = SimpleNamespace(discover=lambda: {'instances': [child()]},
                                        start_agent=lambda entry, timeout, enable_input, observation_profile: entry)
            with patch.object(runtime, 'require_current_rdp'), patch.object(runtime, 'control_module', return_value=lifecycle):
                self.assertEqual(runtime.run_resident(args, load, episode), 1)
            result = json.loads(output.read_text())
            self.assertEqual(counts, {'loads': 1, 'resets': 2, 'segments': 2})
            self.assertEqual(result['endReason'], 'maxInputActions')
            self.assertEqual(result['acceptedInputActions'], 2)
            self.assertEqual(len(result['segments']), 2)
            self.assertEqual(result['segments'][0]['error'], 'simulated hot replacement')
            self.assertFalse(result['evidenceComplete'])
            self.assertEqual(result['failedLeases'], 1)


if __name__ == '__main__':
    unittest.main()
