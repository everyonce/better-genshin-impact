"""CPU-only goal handoff tests with synthetic frames and no Windows/game/GPU access."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import control_resident
import resident_runtime as runtime
import stream_client as client
from test_stream_client import CapturingRecorder, FakePolicy, ScriptedBridge


def document(path, request_id='a' * 32, command='run'):
    """Create a valid run-bound request; tests explicitly advance the monitor state."""
    return {'version': 1, 'runId': 'c' * 32, 'command': command,
            'goalRequestId': request_id, 'goalEmbedding': str(Path(path).resolve())}


def dormant_control(directory):
    """Suppress only the monitor thread so concurrent-policy transitions are deterministic."""
    with patch.object(runtime.threading, 'Thread'):
        return runtime.ResidentControl(Path(directory)/'control.json', Path(directory)/'status.json', 'c' * 32)


class GoalControlTests(unittest.TestCase):
    def test_cli_goal_preserves_pause_and_plain_commands_preserve_request_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'control.json'
            runtime.atomic_json(path, {'version': 1, 'runId': 'c' * 32, 'command': 'pause'})
            def command(*arguments):
                with patch.object(sys, 'argv', ['control_resident.py', '--file', str(path), *arguments]), \
                        redirect_stdout(io.StringIO()):
                    control_resident.main()
                return json.loads(path.read_text())
            first = command('--goal-embedding', str(Path(directory)/'goal.json'))
            self.assertEqual(first['command'], 'pause')
            self.assertEqual(first['runId'], 'c' * 32)
            self.assertEqual(len(first['goalRequestId']), 32)
            resumed = command('--command', 'run')
            self.assertEqual(resumed['goalRequestId'], first['goalRequestId'])
            second = command('--goal-embedding', first['goalEmbedding'])
            self.assertNotEqual(second['goalRequestId'], first['goalRequestId'])
            command('--command', 'stop')
            with self.assertRaisesRegex(ValueError, 'Stop is terminal'):
                command('--goal-embedding', first['goalEmbedding'])

    def test_partial_relative_or_reused_goal_identity_cannot_authorize_old_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            control = dormant_control(directory)
            valid = document(Path(directory)/'goal.json')
            for change in ({'goalRequestId': None}, {'goalEmbedding': 'relative.json'}, {'runId': 'foreign'}):
                control.path.write_text(json.dumps(dict(valid, **change)))
                parsed, error = runtime.read_control_document(control.path, control.run_id)
                self.assertIsNone(parsed)
                self.assertTrue(error)
                control._observe(parsed, error)
                self.assertEqual(control.snapshot()[0], 'pause')
            policy = SimpleNamespace(metadata={'goal': {'instruction': 'first'}}, set_goal=Mock())
            control._observe(valid, None)
            runtime.apply_pending_goal(control, policy, lambda: None)
            control._observe(dict(valid, goalEmbedding=str(Path(directory)/'other.json')), None)
            self.assertEqual(control.snapshot()[0], 'pause')
            self.assertIn('cannot change', control.goal_state()['goalError'])
            fresh = document(Path(directory)/'other.json', 'b' * 32)
            control._observe(fresh, None)
            runtime.apply_pending_goal(control, policy, lambda: None)
            control._observe(valid, None)
            self.assertIn('cannot be replayed', control.goal_state()['goalError'])
            self.assertEqual(control.snapshot()[0], 'pause')

    def test_release_precedes_goal_and_applied_metadata_is_an_immutable_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            control = dormant_control(directory)
            order = []
            metadata = {'instruction': 'walk along the street', 'provenance': {'encoder': 'original'}}
            policy = SimpleNamespace(metadata={'goal': metadata}, set_goal=lambda path: order.append('set_goal'))
            control._observe(document(Path(directory)/'goal.json'), None)
            old_token = control.prediction_token()
            event = runtime.apply_pending_goal(control, policy, lambda: order.append('release'))
            self.assertEqual(order, ['release', 'set_goal'])
            self.assertEqual(control.snapshot(), ('run', None))
            self.assertEqual(event['policyGoalVersion'], 1)
            self.assertEqual(control.goal_state()['appliedGoalRequestId'], 'a' * 32)
            self.assertNotEqual(old_token, control.prediction_token())
            metadata['provenance']['encoder'] = 'changed later'
            event['goalMetadata']['instruction'] = 'mutated report'
            self.assertEqual(control.goal_state()['goalMetadata']['provenance']['encoder'], 'original')
            self.assertEqual(control.goal_events()[0]['goalMetadata']['instruction'], 'walk along the street')

    def test_invalid_goal_latches_pause_until_a_fresh_valid_request(self):
        with tempfile.TemporaryDirectory() as directory:
            control = dormant_control(directory)
            goal = document(Path(directory)/'goal.json')
            policy = SimpleNamespace(metadata={'goal': {'instruction': 'new'}},
                                     set_goal=Mock(side_effect=[ValueError('Invalid embedding'), None]))
            control._observe(goal, None)
            event = runtime.apply_pending_goal(control, policy, lambda: None)
            self.assertEqual(event['status'], 'failed')
            control._observe(dict(goal, command='run'), None)
            self.assertEqual(control.snapshot(), ('pause', 'Invalid embedding'))
            self.assertIsNone(runtime.apply_pending_goal(control, policy, lambda: None))
            control._observe(dict(goal, goalRequestId='b' * 32), None)
            runtime.apply_pending_goal(control, policy, lambda: None)
            self.assertEqual(control.snapshot(), ('run', None))
            self.assertEqual(control.goal_state()['policyGoalVersion'], 1)

    def test_unsupported_policy_releases_then_fails_closed_without_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            control = dormant_control(directory)
            control._observe(document(Path(directory)/'goal.json'), None)
            release = Mock()
            event = runtime.apply_pending_goal(control, None, release)
            release.assert_called_once()
            self.assertEqual(event['status'], 'failed')
            self.assertIn('does not support', control.snapshot()[1])
            self.assertEqual(control.snapshot()[0], 'pause')

    def test_release_failure_does_not_mutate_goal(self):
        with tempfile.TemporaryDirectory() as directory:
            control = dormant_control(directory)
            control._observe(document(Path(directory)/'goal.json'), None)
            policy = SimpleNamespace(set_goal=Mock())
            with self.assertRaisesRegex(OSError, 'release failed'):
                runtime.apply_pending_goal(control, policy, Mock(side_effect=OSError('release failed')))
            policy.set_goal.assert_not_called()
            self.assertEqual(control.snapshot(), ('pause', 'release failed'))

    def test_new_request_during_application_stays_pending_and_stop_is_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            control = dormant_control(directory)
            first, second = document(Path(directory)/'first.json'), document(Path(directory)/'second.json', 'b' * 32)
            policy = SimpleNamespace(metadata={'goal': {'instruction': 'first'}},
                                     set_goal=lambda path: control._observe(second, None))
            control._observe(first, None)
            event = runtime.apply_pending_goal(control, policy, lambda: None)
            self.assertTrue(event['superseded'])
            self.assertEqual(control.goal_state()['goalRequestStatus'], 'pending')
            self.assertEqual(control.snapshot()[0], 'pause')
            policy.set_goal = lambda path: control._observe(dict(second, command='stop'), None)
            runtime.apply_pending_goal(control, policy, lambda: None)
            control._observe(dict(first, command='run'), None)
            self.assertEqual(control.snapshot()[0], 'stop')
            self.assertIsNone(runtime.apply_pending_goal(control, policy, lambda: None))

    def test_status_write_failure_cannot_unlatch_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            control = dormant_control(directory)
            stopped = {'version': 1, 'runId': control.run_id, 'command': 'stop'}
            with patch.object(runtime, 'read_control_document', return_value=(stopped, None)), \
                    patch.object(runtime, 'atomic_json', side_effect=OSError('disk unavailable')), \
                    patch.object(control._closing, 'wait', side_effect=lambda _: control._closing.set()):
                control._monitor()
            self.assertEqual(control.snapshot()[0], 'stop')


class GoalEpisodeTests(unittest.TestCase):
    def run_synthetic(self, directory, control, policy, bridge, recorder):
        """Exercise the real episode loop with a memory pipe and CPU policy mock."""
        output = Path(directory)/'episode.json'
        argv = ['stream_client.py', '--seconds', '.3', '--fps', '100', '--decision-hz', '100',
                '--model', 'open-p2p', '--source', 'synthetic', '--checkpoint', 'synthetic',
                '--enable-input', '--max-input-actions', '2', '--output', str(output),
                '--record-dir', str(Path(directory)/'recording')]
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, 'argv', argv))
            stack.enter_context(patch.dict(sys.modules, {'PIL': SimpleNamespace(
                Image=SimpleNamespace(frombytes=lambda mode, shape, pixels: pixels))}))
            stack.enter_context(patch.object(client, 'Bridge', return_value=bridge))
            stack.enter_context(patch.object(client, 'AsyncVideoRecorder', return_value=recorder))
            stack.enter_context(redirect_stdout(io.StringIO()))
            code = client.run_episode(client.parse_arguments(), policy, control)
        return code, json.loads(output.read_text())

    def test_inflight_old_goal_is_rejected_then_released_and_new_goal_is_attributable(self):
        with tempfile.TemporaryDirectory() as directory:
            control = dormant_control(directory)
            order = []
            goal = document(Path(directory)/'new.json')
            class Policy(FakePolicy):
                execution_feedback = True
                def __init__(self):
                    super().__init__()
                    self.metadata = {'goal': {'instruction': 'old goal'}}
                    self.pending = False
                def predict(self, image, size):
                    result = super().predict(image, size)
                    self.pending = True
                    if len(self.images) == 2:
                        control._observe(goal, None)
                    return result
                def finish_action(self, accepted):
                    self.pending = False
                    order.append(('feedback', accepted))
                def reset(self):
                    order.append(('reset', self.pending))
                def set_goal(self, path):
                    if self.pending:
                        raise AssertionError('A prediction transaction was still pending')
                    order.append(('goal', path))
                    self.metadata['goal']['instruction'] = 'new goal'
            class Bridge(ScriptedBridge):
                def request(self, command, **kwargs):
                    if command == 'release':
                        self.commands.append(command)
                        order.append(('release', None))
                        return {'type': 'released', 'receipts': []}, b''
                    return super().request(command, **kwargs)
            policy, recorder = Policy(), CapturingRecorder()
            bridge = Bridge([bytes(range(12))])
            bridge.hello['supportsRelease'] = True
            code, report = self.run_synthetic(directory, control, policy, bridge, recorder)
            self.assertEqual(code, 0)
            self.assertEqual(report['endReason'], 'maxInputActions')
            self.assertEqual([item['policyGoalVersion'] for item in report['decisions']], [0, 0, 1])
            self.assertEqual(report['decisions'][1]['acceptance']['reason'], 'residentControlEpochChanged')
            self.assertFalse(report['decisions'][1]['historyCommitted'])
            self.assertEqual(report['decisions'][2]['appliedGoalRequestId'], goal['goalRequestId'])
            self.assertLess(order.index(('feedback', False)), order.index(('release', None)))
            self.assertLess(order.index(('release', None)), order.index(('goal', goal['goalEmbedding'])))
            self.assertEqual(report['policyMetadata']['goal']['instruction'], 'old goal')
            self.assertEqual(report['finalGoalState']['goalMetadata']['instruction'], 'new goal')
            self.assertEqual(bridge.commands.count('action'), 2)
            self.assertEqual(bridge.commands[-1], 'stop')
            proposals = [event for event in recorder.events if event.get('type') == 'proposal']
            self.assertEqual([event['policyGoalVersion'] for event in proposals], [0, 0, 1])
            self.assertEqual(len([event for event in recorder.events if event.get('type') == 'policyGoalChange']), 1)
            self.assertEqual(recorder.events[0]['policyMetadata']['goal']['instruction'], 'old goal')

    def test_bad_goal_keeps_capture_evidence_but_cannot_fall_back_to_old_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            control = dormant_control(directory)
            control._observe(document(Path(directory)/'invalid.json'), None)
            policy = FakePolicy()
            policy.reset = Mock()
            policy.set_goal = Mock(side_effect=ValueError('Invalid goal vector'))
            class Bridge(ScriptedBridge):
                def request(self, command, **kwargs):
                    if command == 'release':
                        self.commands.append(command)
                        return {'type': 'released', 'receipts': []}, b''
                    return super().request(command, **kwargs)
            bridge, recorder = Bridge([bytes(range(12))]), CapturingRecorder()
            bridge.hello['supportsRelease'] = True
            code, report = self.run_synthetic(directory, control, policy, bridge, recorder)
            self.assertEqual(code, 1)
            self.assertEqual(report['status'], 'failed')
            self.assertIn('Invalid goal vector', report['error'])
            self.assertGreater(len(recorder.frames), 1)
            self.assertEqual(policy.images, [])
            self.assertNotIn('action', bridge.commands)
            self.assertEqual(bridge.commands[-1], 'stop')


if __name__ == '__main__':
    unittest.main()
