"""Actual stream-loop combat tests using only an in-memory pipe, CPU policy and recorder."""
import copy
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import stream_client as client
from combat_trial_guard import CombatTrialStop
from native_combat import CAPABILITY
from test_combat_trial_guard import HELLO, OWNER, PROFILE, binding, frame, proposal, review_parts
from test_resident_goals import dormant_control
from test_stream_client import CapturingRecorder


class TrialPolicy:
    """Predict unchanged normal attacks without tensors, CUDA or a real image decoder."""
    observation_profile = PROFILE
    execution_feedback = True

    def __init__(self, during_predict=None, proposed=None):
        """Retain proposed/committed history and permit deterministic inference races."""
        self.metadata = dict(synthetic=True)
        self.images, self.feedback = [], []
        self.during_predict, self.proposed = during_predict, proposed
        self.combat_trial_goal_sha256 = binding()['goalSha256']

    def predict(self, image, size, **kwargs):
        """Return a raw50ms attack; the explicit stream100ms hold remains separately journaled."""
        self.images.append(image)
        if self.during_predict:
            self.during_predict()
        return dict(copy.deepcopy(self.proposed if self.proposed is not None else proposal(50)), fullActionMs=1)

    def finish_action(self, accepted):
        """Track whether the existing policy transaction committed a real native admission."""
        self.feedback.append(accepted)

    def reset(self):
        """No model cache exists in this inert fixture."""


class TrialBridge:
    """Simulate real-time native100ms terminal receipts and release readiness resets."""
    def __init__(self, transform=None, hold_terminal=False):
        """Start one native clock and never create another connection or owner."""
        self.origin = time.perf_counter()
        self.hello = copy.deepcopy(HELLO)
        self.hello.update(widthLimit=192, heightLimit=192,
            observationPreprocessing=dict(source='native_capture', resize='fir-5.1.4-interpolation-hamming',
                pixelFormat='rgb24', preserveAspectRatio=False),
            worldReadiness=dict(version=1, requiredForInput=True))
        self.handle = SimpleNamespace(close=Mock())
        self.commands, self.actions, self.completed = [], [], []
        self.count, self.epoch = 0, 0
        self.pending, self.last_release = None, None
        self.transform, self.hold_terminal = transform, hold_terminal
        self.released = threading.Event()
        self.pixels = bytes(range(256)) * (192 * 192 * 3 // 256)

    def now(self):
        """Use one monotonic native session clock for every source, acknowledgement and receipt."""
        return 1000 + (time.perf_counter() - self.origin) * 1000

    def terminal(self, *, cancel=False):
        """Deliver at most one original receipt for the one outstanding action."""
        if self.pending is None or not cancel and (self.hold_terminal or self.now() < self.pending['endedAtMs']):
            return []
        receipt, self.pending = self.pending, None
        receipt = copy.deepcopy(receipt)
        if cancel:
            receipt.update(status='cancelled', reason='release', endedAtMs=self.now())
        else:
            receipt['endedAtMs'] = self.now()
            self.completed.append(receipt['requestId'])
        return [receipt]

    def request(self, command, **arguments):
        """Expose only the existing standard frame/action/release/stop/HUD operations."""
        self.commands.append(command)
        now = self.now()
        if command == 'enableCombatObservation':
            return dict(type='combatObservation', enabled=True, capability=CAPABILITY), b''
        if command == 'action':
            if self.pending is not None:
                raise AssertionError('A combat action superseded an outstanding action')
            self.actions.append(copy.deepcopy(arguments))
            self.pending = dict(requestId=arguments['requestId'], frameId=arguments['frameId'], modelId=arguments['modelId'],
                status='completed', reason='horizon_complete', acceptedAtMs=now,
                endedAtMs=now + arguments['steps'][0]['durationMs'],
                appliedSteps=[dict(index=0, keys=['LBUTTON'], mouseDx=0, mouseDy=0, startedAtMs=now + .1)])
            return dict(type='accepted', requestId=arguments['requestId'], receivedAtMs=now, acceptedAtMs=now), b''
        if command == 'release':
            self.released.set()
            self.epoch += 1
            self.last_release = now
            return dict(type='released', serverNowMs=self.now(), worldReadiness=dict(ready=False, epoch=self.epoch),
                        receipts=self.terminal(cancel=True), droppedReceipts=0), b''
        if command == 'stop':
            return dict(type='stopped', receipts=self.terminal(cancel=True), droppedReceipts=0), b''
        if command != 'frame':
            raise AssertionError('Unexpected native operation: ' + command)
        self.count += 1
        row = frame(self.count, now - 1, epoch=self.epoch, age=1)
        row.update(observationProfile=PROFILE, width=192, height=192, pixelFormat='rgb24',
                   payloadBytes=len(self.pixels), receipts=self.terminal())
        if self.last_release is not None and now < self.last_release + 25:
            row.pop('combatEvidence')
            row['frameWorldReadiness']['ready'] = row['worldReadiness']['ready'] = False
            row['inputAvailable'] = False
        if self.transform:
            row = self.transform(row)
        return row, self.pixels


class CombatTrialStreamTests(unittest.TestCase):
    def arguments(self, folder, *, seconds=1.5):
        """Build the same explicit single-lease scope as the worker without any live prerequisites."""
        goal = Path(folder) / 'goal.json'
        goal.write_bytes(review_parts()[5])
        args = client.parse_arguments(['--model', 'open-p2p', '--source', 'inert', '--checkpoint', 'inert',
            '--observation-profile', PROFILE, '--goal-embedding', str(goal), '--goal-intent', 'stationary',
            '--cuda-graph', '--p2p-fast-start', '--p2p-prewarm', '--p2p-execution-feedback',
            '--soft-cadence', '--fresh-frame-at-decision', '--require-world-ready',
            '--enable-input', '--native-combat-observation', '--input-keys', 'LBUTTON',
            '--max-input-actions', '3', '--action-hold-ms', '100', '--max-observation-age-ms', '150',
            '--fps', '100', '--decision-hz', '100', '--seconds', str(seconds),
            '--record-dir', str(Path(folder) / 'recording'), '--retain-policy-rgb', '--record-max-mib', '160',
            '--output', str(Path(folder) / 'run.json')])
        args.combat_trial_binding = binding()
        args.combat_trial_owner = copy.deepcopy(OWNER)
        args.expected_process_id, args.expected_session_id = 22, 3
        return args

    def run_inert(self, folder, bridge, policy, recorder, *, seconds=1.5, control=None, args=None):
        """Run all real stream admission/intake/dispatch logic while replacing only external resources."""
        args = self.arguments(folder, seconds=seconds) if args is None else args
        control = dormant_control(folder, frozen_goal=True) if control is None else control
        control.set_initial_goal(dict(instruction='fixed combat'), 'stationary')
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {'PIL': SimpleNamespace(
                Image=SimpleNamespace(frombytes=lambda mode, shape, pixels: pixels))}))
            stack.enter_context(patch.object(client, 'Bridge', return_value=bridge))
            stack.enter_context(patch.object(client, 'AsyncVideoRecorder', return_value=recorder))
            verified = stack.enter_context(patch('resident_runtime.verify_bridge_identity'))
            stack.enter_context(redirect_stdout(io.StringIO()))
            result = client.run_episode(args, policy, control)
            verified.assert_called_once_with(bridge.handle, 22, 3)
            return result

    def test_three_actions_drain_without_fourth_dispatch_or_final_hold_cancellation(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge, policy, recorder = TrialBridge(), TrialPolicy(), CapturingRecorder()
            control = dormant_control(folder, frozen_goal=True)
            control.guarded_submit = Mock(wraps=control.guarded_submit)
            self.assertEqual(self.run_inert(folder, bridge, policy, recorder, control=control), 0)
            self.assertEqual(control.guarded_submit.call_count, 3)
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(len(bridge.actions), 3)
            self.assertEqual(len(bridge.completed), 3)
            self.assertEqual(policy.feedback, [True, True, True])
            self.assertEqual(report['endReason'], 'combatTrialComplete')
            self.assertTrue(report['combatTrialGuardState']['trialComplete'])
            self.assertEqual(report['combatTrialGuardState']['completedActions'], 3)
            for item in report['combatTrialGuardState']['completed']:
                self.assertEqual(item['arguments']['steps'], proposal()['steps'])
                self.assertEqual(item['receipt']['status'], 'completed')
                self.assertGreaterEqual(item['postFrame']['sourceFrame']['freshnessAtMs'], item['release']['response']['serverNowMs'] + 60)
            self.assertEqual(bridge.commands[-1], 'stop')
            self.assertTrue(recorder.frames)

    def test_missing_startup_hud_and_zero_raw_attack_proposals_remain_inconclusive(self):
        for missing in (True, False):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as folder:
                def transform(row):
                    """Omit only startup sensor data while preserving all native source contracts."""
                    if missing:
                        row.pop('combatEvidence', None)
                    return row
                proposed = proposal()
                proposed['steps'][0]['keys'] = []
                bridge, policy = TrialBridge(transform), TrialPolicy(proposed=proposed)
                self.assertEqual(self.run_inert(folder, bridge, policy, CapturingRecorder(), seconds=.12), 1)
                report = json.loads((Path(folder) / 'run.json').read_bytes())
                self.assertEqual(bridge.actions, [])
                self.assertFalse(report['combatTrialGuardState']['trialComplete'])
                self.assertEqual(report['acceptedInputActions'], 0)
                self.assertIn('release', bridge.commands)

    def test_new_health_hazard_during_inference_preserves_rgb_and_prevents_action(self):
        with tempfile.TemporaryDirectory() as folder:
            entered = threading.Event()
            def transform(row):
                """Trip only after the CPU policy has selected an older healthy observation."""
                if entered.is_set():
                    row['combatEvidence']['playerHealthFractionEstimate'] = .81
                return row
            bridge = TrialBridge(transform)
            def during_predict():
                """Wait for the independent producer to latch and release during inference."""
                entered.set()
                self.assertTrue(bridge.released.wait(2))
            policy, recorder = TrialPolicy(during_predict), CapturingRecorder()
            with self.assertRaises(CombatTrialStop):
                self.run_inert(folder, bridge, policy, recorder)
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(bridge.actions, [])
            self.assertEqual(report['combatTrialGuardState']['trip']['reason'], 'healthFractionDrop')
            trigger = report['combatTrialGuardState']['trip']['frame']
            saved = [(row, pixels) for row, pixels in recorder.frames if row['frameId'] == trigger['frameId']]
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0][1], bridge.pixels)
            self.assertEqual(saved[0][0]['sourceFrame'], trigger['sourceFrame'])
            self.assertTrue(report['combatTrialTriggerRecorded'])

    def test_recording_failure_after_acceptance_releases_and_retains_known_action_count(self):
        with tempfile.TemporaryDirectory() as folder:
            class FailingRecorder(CapturingRecorder):
                """Reject the admission journal once native input has actually been acknowledged."""
                def event(self, event):
                    if event.get('type') == 'combatTrialAdmission':
                        self.error = 'inert disk failure'
                        return False
                    return super().event(event)
            bridge, recorder = TrialBridge(), FailingRecorder()
            with self.assertRaisesRegex(RuntimeError, 'journal retention'):
                self.run_inert(folder, bridge, TrialPolicy(), recorder)
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(len(bridge.actions), 1)
            self.assertEqual(report['acceptedInputActions'], 1)
            self.assertFalse(report['combatTrialGuardState']['trialComplete'])
            self.assertFalse(report['combatTrialGuardState']['armed'])
            self.assertIn('release', bridge.commands)
            self.assertIsNone(bridge.pending)

    def test_last_pending_receipt_never_counts_as_completed(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = TrialBridge(hold_terminal=True)
            self.assertEqual(self.run_inert(folder, bridge, TrialPolicy(), CapturingRecorder(), seconds=.17), 1)
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(len(bridge.actions), 1)
            self.assertEqual(report['combatTrialGuardState']['completedActions'], 0)
            self.assertFalse(report['combatTrialGuardState']['trialComplete'])
            self.assertEqual(report['combatTrialGuardState']['pending']['receipt']['status'], 'cancelled')
            self.assertIsNone(bridge.pending)

    def test_frozen_control_token_refuses_a_result_after_pause_during_inference(self):
        with tempfile.TemporaryDirectory() as folder:
            control = dormant_control(folder, frozen_goal=True)
            def during_predict():
                """Invalidate the control token before the final guarded native-write callback."""
                with control._lock:
                    control._command, control._epoch = 'pause', control._epoch + 1
            bridge = TrialBridge()
            self.assertEqual(self.run_inert(folder, bridge, TrialPolicy(during_predict), CapturingRecorder(), control=control), 1)
            self.assertEqual(bridge.actions, [])
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertFalse(report['combatTrialGuardState']['trialComplete'])
            self.assertEqual(report['combatTrialGuardState']['trip']['reason'], 'userPause')

    def test_stripped_binding_or_changed_frozen_goal_is_rejected_before_bridge_open(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.arguments(folder)
            control = dormant_control(folder, frozen_goal=True)
            policy = TrialPolicy()
            for name, value in [('resident', True), ('action_hold_ms', 101), ('max_input_actions', 4),
                                ('navigation_climb_recovery', True), ('retain_policy_rgb', False)]:
                with self.subTest(name=name), patch.object(client, 'Bridge') as bridge:
                    changed = copy.copy(args)
                    setattr(changed, name, value)
                    with self.assertRaises(ValueError):
                        client.run_episode(changed, policy, control)
                    bridge.assert_not_called()
            policy.combat_trial_goal_sha256 = '0' * 64
            with patch.object(client, 'Bridge') as bridge, self.assertRaises(ValueError):
                client.run_episode(args, policy, control)
            bridge.assert_not_called()

    def test_rgb_recording_refusal_releases_before_any_policy_input(self):
        with tempfile.TemporaryDirectory() as folder:
            class RefusingRecorder(CapturingRecorder):
                """Lose a policy RGB frame without claiming the journal itself failed."""
                def put(self, metadata, pixels):
                    return False
            bridge = TrialBridge()
            with self.assertRaisesRegex(RuntimeError, 'RGB retention'):
                self.run_inert(folder, bridge, TrialPolicy(), RefusingRecorder())
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(bridge.actions, [])
            self.assertIn('release', bridge.commands)
            self.assertFalse(report['combatTrialGuardState']['trialComplete'])

    def test_successful_put_with_retention_loss_counter_stops_and_releases(self):
        for counter in ('dropped', 'dropped_events', 'dropped_observations', 'abandoned_frames'):
            with self.subTest(counter=counter), tempfile.TemporaryDirectory() as folder:
                class EvictingRecorder(CapturingRecorder):
                    """A worker reports an eviction while the current RGB enqueue still succeeds."""
                    def put(self, metadata, pixels):
                        accepted = super().put(metadata, pixels)
                        setattr(self, counter, 1)
                        return accepted
                bridge, recorder = TrialBridge(), EvictingRecorder()
                with self.assertRaisesRegex(RuntimeError, 'RGB retention failed.*' + counter):
                    self.run_inert(folder, bridge, TrialPolicy(), recorder)
                report = json.loads((Path(folder) / 'run.json').read_bytes())
                self.assertIsNone(recorder.error)
                self.assertTrue(recorder.frames)
                self.assertEqual(bridge.actions, [])
                self.assertIn('release', bridge.commands)
                self.assertFalse(report['combatTrialGuardState']['trialComplete'])

    def test_late_unobserved_goal_request_invalidates_otherwise_drained_trial(self):
        with tempfile.TemporaryDirectory() as folder:
            control = dormant_control(folder, frozen_goal=True)
            class LateGoalBridge(TrialBridge):
                """Write a replacement goal after the last decision without running the control monitor."""
                def request(self, command, **arguments):
                    response = super().request(command, **arguments)
                    if command == 'stop':
                        value = json.loads(control.path.read_bytes())
                        value.update(goalRequestId='late', goalEmbedding='other.json')
                        control.path.write_text(json.dumps(value), encoding='utf-8')
                    return response
            bridge = LateGoalBridge()
            self.assertEqual(self.run_inert(folder, bridge, TrialPolicy(), CapturingRecorder(), control=control), 1)
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(report['acceptedInputActions'], 3)
            self.assertEqual(report['combatTrialGuardState']['completedActions'], 3)
            self.assertEqual(report['combatTrialGuardState']['trip']['reason'], 'goalMutation')
            self.assertFalse(report['combatTrialGuardState']['trialComplete'])

    def test_unacknowledged_send_keeps_terminal_evidence_and_never_retries(self):
        with tempfile.TemporaryDirectory() as folder:
            class LostReplyBridge(TrialBridge):
                """Accept exactly one action, then simulate losing its action acknowledgement."""
                def request(self, command, **arguments):
                    response = super().request(command, **arguments)
                    if command == 'action':
                        raise OSError('inert lost action acknowledgement')
                    return response
            bridge = LostReplyBridge()
            with self.assertRaisesRegex(OSError, 'lost action acknowledgement'):
                self.run_inert(folder, bridge, TrialPolicy(), CapturingRecorder())
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(len(bridge.actions), 1)
            self.assertIsNone(bridge.pending)
            self.assertIn('unacknowledgedAction', report)
            self.assertEqual(report['combatTrialGuardState']['pending']['receipt']['status'], 'cancelled')
            self.assertFalse(report['combatTrialGuardState']['trialComplete'])

    def test_initial_journal_failure_closes_recorder_and_releases_before_main_loop(self):
        with tempfile.TemporaryDirectory() as folder:
            class InitialFailureRecorder(CapturingRecorder):
                """Fail before producer creation while an encoder resource already exists."""
                def event(self, event):
                    if event.get('type') == 'episodeStart':
                        raise RuntimeError('inert initial journal failure')
                    return super().event(event)
            bridge, recorder = TrialBridge(), InitialFailureRecorder()
            recorder.close = Mock(wraps=recorder.close)
            with self.assertRaisesRegex(RuntimeError, 'inert initial journal failure'):
                self.run_inert(folder, bridge, TrialPolicy(), recorder)
            recorder.close.assert_called_once()
            bridge.handle.close.assert_called_once()
            self.assertEqual(bridge.actions, [])
            self.assertEqual(bridge.commands, ['enableCombatObservation', 'release'])
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(report['error'], 'inert initial journal failure')
            self.assertEqual(report['combatTrialCleanupErrors'], [])
            self.assertFalse(report['combatTrialGuardState']['armed'])

    def test_initial_failure_preserves_original_and_each_cleanup_error(self):
        with tempfile.TemporaryDirectory() as folder:
            class InitialFailureRecorder(CapturingRecorder):
                """Make both initial journaling and later encoder cleanup fail independently."""
                def event(self, event):
                    raise RuntimeError('original journal error')
                def close(self):
                    raise RuntimeError('encoder cleanup error')
            class ReleaseFailureBridge(TrialBridge):
                """Reject release while leaving handle closure separately observable."""
                def request(self, command, **arguments):
                    if command == 'release':
                        self.commands.append(command)
                        raise RuntimeError('release cleanup error')
                    return super().request(command, **arguments)
            bridge, recorder = ReleaseFailureBridge(), InitialFailureRecorder()
            recorder.close = Mock(wraps=recorder.close)
            with self.assertRaisesRegex(RuntimeError, '^original journal error$') as caught:
                self.run_inert(folder, bridge, TrialPolicy(), recorder)
            recorder.close.assert_called_once()
            bridge.handle.close.assert_called_once()
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(report['error'], 'original journal error')
            self.assertEqual([item['operation'] for item in report['combatTrialCleanupErrors']], ['release', 'recorder'])
            self.assertEqual(caught.exception.combat_trial_cleanup_errors, report['combatTrialCleanupErrors'])
            self.assertEqual(len(caught.exception.__notes__), 2)

    def test_setup_failure_after_recorder_creation_closes_original_recorder(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge, recorder = TrialBridge(), CapturingRecorder()
            recorder.close = Mock(wraps=recorder.close)
            with patch.object(client, 'CombatTrialRecorder', side_effect=RuntimeError('inert wrapper setup failure')):
                with self.assertRaisesRegex(RuntimeError, 'inert wrapper setup failure'):
                    self.run_inert(folder, bridge, TrialPolicy(), recorder)
            recorder.close.assert_called_once()
            bridge.handle.close.assert_called_once()
            self.assertIn('release', bridge.commands)
            self.assertEqual(bridge.actions, [])

    def test_reader_start_failure_closes_encoder_and_releases_before_inference(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge, recorder = TrialBridge(), CapturingRecorder()
            recorder.close = Mock(wraps=recorder.close)
            control = dormant_control(folder, frozen_goal=True)
            failed_reader = SimpleNamespace(start=Mock(side_effect=RuntimeError('inert reader start failure')))
            with patch.object(client.threading, 'Thread', return_value=failed_reader):
                with self.assertRaisesRegex(RuntimeError, 'inert reader start failure'):
                    self.run_inert(folder, bridge, TrialPolicy(), recorder, control=control)
            recorder.close.assert_called_once()
            bridge.handle.close.assert_called_once()
            self.assertIn('release', bridge.commands)
            self.assertEqual(bridge.actions, [])


if __name__ == '__main__':
    unittest.main()
