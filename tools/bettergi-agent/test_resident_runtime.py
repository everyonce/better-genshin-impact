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
            args = SimpleNamespace(output=str(output), rdp_session_id=3, control_file=None,
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
                    raise EOFError('simulated hot replacement')
                return 0
            lifecycle = SimpleNamespace(discover=lambda: {'instances': [child()]},
                                        start_agent=lambda entry, timeout, enable_input: entry)
            with patch.object(runtime, 'require_current_rdp'), patch.object(runtime, 'control_module', return_value=lifecycle):
                self.assertEqual(runtime.run_resident(args, load, episode), 0)
            result = json.loads(output.read_text())
            self.assertEqual(counts, {'loads': 1, 'resets': 2, 'segments': 2})
            self.assertEqual(result['endReason'], 'maxInputActions')
            self.assertEqual(result['acceptedInputActions'], 2)
            self.assertEqual(len(result['segments']), 2)
            self.assertEqual(result['segments'][0]['error'], 'simulated hot replacement')


if __name__ == '__main__':
    unittest.main()
