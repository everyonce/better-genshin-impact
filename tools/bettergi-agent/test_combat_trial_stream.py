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
from combat_trial_guard import CombatTrialStop, GROUP_SCOPE, FOUR_SCOPE
from native_combat import CAPABILITY
from test_combat_trial_guard import HELLO, OWNER, PROFILE, binding, frame, proposal, review_parts, group_review_parts
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
    def test_four_scope_real_stream_and_mismatched_three_policy_stamp(self):
        """Four candidates require matching prepared policy and request scope before any native operation."""
        def four_targets(row):
            """Preserve unavailable release frames and the native source metadata."""
            if 'combatEvidence' in row:
                row['combatEvidence']['enemyBarCandidates']=frame(candidates=4)['combatEvidence']['enemyBarCandidates']
            return row
        for changed in (None,'args','policy'):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as folder:
                args=self.arguments(folder);args.combat_trial_binding=binding(group_review_parts(4,4,scope=FOUR_SCOPE))
                policy=TrialPolicy()
                for authority in (args,policy):
                    authority.combat_trial_scope=FOUR_SCOPE;authority.combat_trial_maximum_enemy_candidates=4
                if changed:
                    authority=args if changed=='args' else policy
                    authority.combat_trial_scope=GROUP_SCOPE;authority.combat_trial_maximum_enemy_candidates=3
                bridge=TrialBridge(transform=four_targets)
                if changed:
                    with self.assertRaisesRegex(ValueError,'scope or maximum'):
                        self.run_inert(folder,bridge,policy,CapturingRecorder(),args=args)
                    self.assertEqual(bridge.commands,[])
                else:
                    self.assertEqual(self.run_inert(folder,bridge,policy,CapturingRecorder(),args=args),0)
                    self.assertEqual(len(bridge.actions),3)
                    self.assertTrue(all(action['steps']==proposal()['steps'] for action in bridge.actions))
    def test_group_scope_three_candidates_uses_same_real_loop_and_exact_pure_attacks(self):
        """Only a matching separately stamped opt-in reaches the ordinary three-pulse stream."""
        def group_targets(row):
            """Keep intentional post-release unavailable frames, changing only valid native counts."""
            if 'combatEvidence' in row:
                row['combatEvidence']['enemyBarCandidates']=frame(candidates=3)['combatEvidence']['enemyBarCandidates']
            return row
        with tempfile.TemporaryDirectory() as folder:
            args=self.arguments(folder);args.combat_trial_binding=binding(group_review_parts())
            policy=TrialPolicy()
            for authority in (args,policy):
                authority.combat_trial_scope=GROUP_SCOPE;authority.combat_trial_maximum_enemy_candidates=3
            bridge=TrialBridge(transform=group_targets)
            self.assertEqual(self.run_inert(folder,bridge,policy,CapturingRecorder(),args=args),0)
            self.assertEqual(len(bridge.actions),3)
            self.assertTrue(all(item['steps']==proposal()['steps'] for item in bridge.actions))

    def test_group_scope_missing_or_changed_worker_request_stamp_refuses_before_bridge(self):
        """The review alone cannot upgrade a default or differently prepared request/policy."""
        for target,field,value in (('args','combat_trial_scope',None),('policy','combat_trial_scope',None),
                ('args','combat_trial_maximum_enemy_candidates',4),('policy','combat_trial_maximum_enemy_candidates',True)):
            with self.subTest(target=target,field=field),tempfile.TemporaryDirectory() as folder:
                args=self.arguments(folder);args.combat_trial_binding=binding(group_review_parts())
                policy=TrialPolicy()
                for authority in (args,policy):
                    authority.combat_trial_scope=GROUP_SCOPE;authority.combat_trial_maximum_enemy_candidates=3
                setattr(args if target=='args' else policy,field,value)
                bridge=TrialBridge()
                with self.assertRaisesRegex(ValueError,'scope or maximum'):
                    self.run_inert(folder,bridge,policy,CapturingRecorder(),args=args)
                self.assertEqual(bridge.commands,[])

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

    def test_zero_attack_episode_retains_terminal_stop_before_release(self):
        """Replay the real no-eligible-proposal loop without inventing its terminal transition."""
        from audit_combat_trial import replay_events
        with tempfile.TemporaryDirectory() as folder:
            proposed = proposal()
            proposed['steps'][0]['keys'] = []
            bridge, recorder = TrialBridge(), CapturingRecorder()
            self.assertEqual(self.run_inert(folder, bridge, TrialPolicy(proposed=proposed), recorder, seconds=.12), 1)
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            stops = [row for row in recorder.events if row['type'] == 'combatTrialStop']
            self.assertEqual(len(stops), 1)
            self.assertEqual(stops[0], report['combatTrialTerminalStop'])
            self.assertEqual(stops[0]['trigger']['reason'], 'trialEndedBeforeDrain')
            self.assertLess(recorder.events.index(stops[0]), next(i for i,row in enumerate(recorder.events)
                if row['type'] == 'combatTrialRelease'))
            replay = replay_events(report['combatTrialGuard'], report['hello'], recorder.events)
            self.assertEqual(replay['state'], report['combatTrialGuardState'])
            self.assertFalse(replay['state']['trialComplete'])
            self.assertEqual(bridge.actions, [])
            with self.assertRaises(ValueError):
                replay_events(report['combatTrialGuard'], report['hello'],
                              [row for row in recorder.events if row['type'] != 'combatTrialStop'])

    def test_terminal_stop_journal_failure_still_releases_and_closes(self):
        """A failed new Stop write cannot interrupt the originally required release/stop cleanup."""
        class FailedStopRecorder(CapturingRecorder):
            """Refuse only the newly emitted terminal transition."""
            def event(self, row):
                """Leave all prior evidence intact while modelling a failed Stop journal write."""
                if row['type'] == 'combatTrialStop':
                    raise RuntimeError('synthetic terminal Stop write failed')
                return super().event(row)
        with tempfile.TemporaryDirectory() as folder:
            proposed = proposal()
            proposed['steps'][0]['keys'] = []
            bridge = TrialBridge()
            with self.assertRaisesRegex(RuntimeError, 'terminal Stop write failed'):
                self.run_inert(folder, bridge, TrialPolicy(proposed=proposed), FailedStopRecorder(), seconds=.12)
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['combatTrialTerminalStop']['trigger']['reason'], 'trialEndedBeforeDrain')
            self.assertIn('Stop write failed', report['combatTrialStopJournalError'])
            self.assertEqual(bridge.commands[-2:], ['release', 'stop'])
            bridge.handle.close.assert_called_once()
            self.assertEqual(bridge.actions, [])

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



class StaleRecoveryBridge(TrialBridge):
    """Publish one optional repeated-source interruption after the first fully drained attack."""

    def __init__(self, *, interrupt=False, bad_ack=False):
        """Keep one ordinary clock/lease and a bounded, deterministic source freeze."""
        super().__init__()
        self.interrupt, self.bad_ack = interrupt, bad_ack
        self.last_frame, self.frozen_frame = None, None
        self.stale_sent, self.reacquired = False, False
        self.first_accepted_at = None

    def request(self, command, **arguments):
        """Retain actual loop calls; repeated old pixels still expose native readiness changes."""
        if command == 'frame' and self.frozen_frame is not None and not self.reacquired:
            self.commands.append(command)
            now = self.now()
            row = copy.deepcopy(self.frozen_frame)
            row.update(serverNowMs=now, sourceFrameAgeMs=now - row['sourceFrame']['freshnessAtMs'], receipts=[])
            if row['sourceFrameAgeMs'] > 150:
                if not self.stale_sent:
                    self.epoch += 1
                    self.stale_sent = True
                row['worldReadiness'].update(ready=False, epoch=self.epoch, reason='world_observation_stale',
                    checkedAtMs=now)
                row['inputAvailable'] = False
            return row, self.pixels
        reply, pixels = super().request(command, **arguments)
        if command == 'action' and self.first_accepted_at is None:
            self.first_accepted_at = time.perf_counter()
        if command == 'release':
            if self.stale_sent and not self.reacquired:
                self.reacquired = True
                if self.bad_ack:
                    reply['worldReadiness']['epoch'] += 1
            prior = self.last_frame or frame()
            reply['worldReadiness'].update(reason='client_release', sourceFrameId=prior['frameId'],
                sourceFrame=copy.deepcopy(prior['sourceFrame']), sourceCapturedAtMs=prior['capturedAtMs'],
                checkedAtMs=reply['serverNowMs'])
            reply['executionContext'] = dict(telemetryComplete=True, active=None, evictedEvents=0,
                trackedState=dict(heldKeys=[], executionUncertain=True, releaseOutcome='returned_unverified', telemetryIncomplete=False))
        if command == 'frame':
            for name in ('frameWorldReadiness', 'worldReadiness'):
                reply[name].update(reason='world_ready' if reply[name]['ready'] else 'world_confirming',
                    sourceCapturedAtMs=reply['capturedAtMs'], checkedAtMs=reply['serverNowMs'])
            if 'combatEvidence' not in reply:
                evidence = frame(reply['frameId'], reply['sourceFrame']['freshnessAtMs'])['combatEvidence']
                evidence.update(state='unavailable', reason='world_not_ready', playerHealthColor='unknown',
                    playerHealthFractionEstimate=None, playerHealthMatchingPixels=0, enemyBarCandidates=[])
                reply['combatEvidence'] = evidence
            self.last_frame = copy.deepcopy(reply)
            if (self.interrupt and self.completed and self.last_release is not None
                    and self.now() >= self.last_release + 80 and self.frozen_frame is None):
                self.frozen_frame = copy.deepcopy(reply)
        return reply, pixels


class GapPolicy(TrialPolicy):
    """Refuse mixed/empty proposals until one ordinary acceptance gap exceeds 500 ms."""

    def __init__(self, bridge):
        """Count the unchanged reset operation without creating a model/history implementation."""
        super().__init__()
        self.bridge = bridge
        self.resets = 0

    def predict(self, image, size, **kwargs):
        """Only pure attacks outside the fixed first-gap window remain eligible."""
        row = super().predict(image, size, **kwargs)
        if self.bridge.first_accepted_at is not None and time.perf_counter() - self.bridge.first_accepted_at < .85:
            row['steps'][0]['keys'] = ['W', 'LBUTTON']
        return row

    def reset(self):
        """Observe the production heuristic instead of changing or suppressing it."""
        self.resets += 1


class CombatStaleRecoveryStreamTests(unittest.TestCase):
    """Run the actual reader, policy, release and action paths with a synthetic native bridge."""

    arguments = CombatTrialStreamTests.arguments
    run_inert = CombatTrialStreamTests.run_inert

    def recovery_arguments(self, folder, policy, *, enabled=True):
        """Stamp both armed arguments and the separately loaded policy from one explicit review."""
        from combat_trial_guard import trial_policy
        args = self.arguments(folder, seconds=2.5)
        parts = group_review_parts(4, 4, scope=FOUR_SCOPE)
        parts[0]['policy'] = trial_policy(FOUR_SCOPE, source_stale_recovery=enabled)
        args.combat_trial_binding = binding(parts)
        for authority in (args, policy):
            authority.combat_trial_scope = FOUR_SCOPE
            authority.combat_trial_maximum_enemy_candidates = 4
            if enabled:
                authority.combat_trial_source_stale_recovery_policy = copy.deepcopy(parts[0]['policy']['sourceStaleRecoveryPolicy'])
        return args

    def test_real_loop_reacquisition_and_healthy_gaps_keep_the_existing_history_reset(self):
        """A repeated stale source is never skipped; recovery adds no reset or new action budget."""
        from audit_combat_trial import replay_events
        for enabled, interrupt in ((True, True), (True, False), (False, False)):
            with self.subTest(enabled=enabled, interrupt=interrupt), tempfile.TemporaryDirectory() as folder:
                bridge, recorder = StaleRecoveryBridge(interrupt=interrupt), CapturingRecorder()
                policy = GapPolicy(bridge)
                args = self.recovery_arguments(folder, policy, enabled=enabled)
                result = self.run_inert(folder, bridge, policy, recorder, args=args)
                report = json.loads((Path(folder) / 'run.json').read_bytes())
                self.assertEqual(result, 0, report.get('error'))
                self.assertEqual(len(bridge.actions), 3)
                self.assertEqual(policy.feedback.count(True), 3)
                self.assertEqual(policy.resets, 1)
                final = replay_events(args.combat_trial_binding, bridge.hello, recorder.events)['state']
                self.assertEqual(final, report['combatTrialGuardState'])
                self.assertEqual(final['deadlineNs'] - final['startedNs'], 5_000_000_000)
                if enabled:
                    self.assertEqual(len(report['combatTrialHistoryGapResets']), 1)
                    state = final['sourceStaleRecovery']
                    self.assertEqual(state['used'], int(interrupt))
                    self.assertEqual(state['existingHistoryResets'][0]['afterReacquisition'], interrupt)
                    requests = report.get('combatTrialReacquisitionRequests', [])
                    self.assertEqual(len(requests), int(interrupt))
                    if interrupt:
                        completed = state['completed'][0]
                        self.assertEqual(len(completed['sources']), 2)
                        self.assertTrue(completed['release']['response']['executionContext']['trackedState']['executionUncertain'])
                else:
                    self.assertNotIn('sourceStaleRecovery', final)
                    self.assertNotIn('combatTrialHistoryGapResets', report)
                self.assertEqual(bridge.commands[-1], 'stop')

    def test_repeated_stale_poll_between_phase_check_and_generic_gate_only_waits(self):
        """Inject the reader transition exactly after main releases its first guard-phase lock."""
        import combat_trial_guard as guard_module
        main_thread = threading.get_ident()
        original_init = guard_module.CombatTrialGuard.__init__
        observed = []
        with tempfile.TemporaryDirectory() as folder:
            bridge, recorder = StaleRecoveryBridge(), CapturingRecorder()
            policy = GapPolicy(bridge)
            args = self.recovery_arguments(folder, policy)

            class ExitInjectionLock:
                """Release the real lock before allowing the actual polling thread to latch the stale source."""
                def __init__(self, lock, guard):
                    self.lock, self.guard, self.depth = lock, guard, threading.local()
                    self.fired = False

                def acquire(self, *values, **kwargs):
                    result = self.lock.acquire(*values, **kwargs)
                    if result:
                        self.depth.value = getattr(self.depth, 'value', 0) + 1
                    return result

                def release(self):
                    self.depth.value -= 1
                    self.lock.release()
                    if (not self.fired and threading.get_ident() == main_thread and self.depth.value == 0
                            and self.guard._phase == 'ready' and self.guard._accepted == 1
                            and len(self.guard._completed) == 1):
                        self.fired = True
                        bridge.frozen_frame = copy.deepcopy(bridge.last_frame)
                        deadline = time.monotonic() + 1
                        while self.guard._phase != 'awaitingStaleRelease' and time.monotonic() < deadline:
                            time.sleep(.005)
                        observed.append(self.guard._phase)

                def __enter__(self):
                    self.acquire()
                    return self

                def __exit__(self, *_error):
                    self.release()

            def install(guard, *values, **kwargs):
                """Instrument only this inert guard instance, leaving production lock behavior unchanged."""
                original_init(guard, *values, **kwargs)
                guard.intake_lock = ExitInjectionLock(guard.intake_lock, guard)

            with patch.object(guard_module.CombatTrialGuard, '__init__', install):
                result = self.run_inert(folder, bridge, policy, recorder, args=args)
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(observed, ['awaitingStaleRelease'])
            self.assertEqual(result, 0, report.get('error'))
            self.assertEqual(len(bridge.actions), 3)
            self.assertEqual(report['combatTrialGuardState']['sourceStaleRecovery']['used'], 1)

    def test_lost_reacquisition_reply_preserves_error_and_never_retries_input(self):
        """Native release may have happened, but an unreadable ACK cannot create renewed authority."""
        class LostReleaseBridge(StaleRecoveryBridge):
            def request(self, command, **arguments):
                lose = command == 'release' and self.stale_sent and not self.reacquired
                result = super().request(command, **arguments)
                if lose:
                    raise OSError('inert lost recovery acknowledgement')
                return result
        with tempfile.TemporaryDirectory() as folder:
            bridge, recorder = LostReleaseBridge(interrupt=True), CapturingRecorder()
            policy = GapPolicy(bridge); args = self.recovery_arguments(folder, policy)
            with self.assertRaisesRegex(OSError, 'lost recovery acknowledgement'):
                self.run_inert(folder, bridge, policy, recorder, args=args)
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(len(bridge.actions), 1)
            self.assertEqual(len(report['combatTrialReacquisitionRequests']), 1)
            self.assertEqual(report['error'], 'inert lost recovery acknowledgement')
            self.assertEqual(report['combatTrialGuardState']['sourceStaleRecovery']['completed'], [])
            self.assertEqual(report['stop']['type'], 'stopped')
            self.assertEqual(bridge.commands[-1], 'stop')
            self.assertTrue(any(row['reason'] == 'combatTrialTeardown' for row in report['combatTrialReleases']))

    def test_wrong_reacquisition_ack_stops_without_replaying_first_attack(self):
        """A foreign epoch cannot reach inference/action after the safety release."""
        with tempfile.TemporaryDirectory() as folder:
            bridge, recorder = StaleRecoveryBridge(interrupt=True, bad_ack=True), CapturingRecorder()
            policy = GapPolicy(bridge)
            args = self.recovery_arguments(folder, policy)
            with self.assertRaisesRegex(RuntimeError, 'release was not acknowledged'):
                self.run_inert(folder, bridge, policy, recorder, args=args)
            report = json.loads((Path(folder) / 'run.json').read_bytes())
            self.assertEqual(len(bridge.actions), 1)
            self.assertEqual(report['combatTrialGuardState']['trip']['reason'], 'invalidReacquisitionReleaseAcknowledgement')
            self.assertEqual(bridge.commands[-1], 'stop')

    def test_recovery_requires_matching_argument_and_loaded_policy_stamps_before_pipe(self):
        """A raw candidate count or a substituted/omitted mode cannot enable this reviewed-only path."""
        for target, mutation in (('args', 'omit'), ('policy', 'omit'), ('args', 'widen')):
            with self.subTest(target=target, mutation=mutation), tempfile.TemporaryDirectory() as folder:
                bridge, recorder = StaleRecoveryBridge(), CapturingRecorder()
                policy = GapPolicy(bridge)
                args = self.recovery_arguments(folder, policy)
                authority = args if target == 'args' else policy
                if mutation == 'omit':
                    del authority.combat_trial_source_stale_recovery_policy
                else:
                    authority.combat_trial_source_stale_recovery_policy['maximumRecoveries'] = 2
                with self.assertRaisesRegex(ValueError, 'separately reviewed policy'):
                    self.run_inert(folder, bridge, policy, recorder, args=args)
                self.assertEqual(bridge.commands, [])


if __name__ == '__main__':
    unittest.main()
