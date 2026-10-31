"""Actual serialized scout-loop checks with inert transport, policy and recording."""
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
from hybrid_navigation import START, END
from hybrid_routes import SCOUT_GRASS_ROUTE, route_heading
from navigation_profiles import SCOUT_PROFILE
from observation_profiles import P2P_NATIVE
from p2p_executed_history import (MODE, ExecutedHistoryCadence, ExecutedHistoryRecorder, encode_controller_step,
                                  validate_executed_history_options, verify_completed_receipt)
from reviewed_scout_route import ReviewedScoutRoute
from scout_encounter_guard import ScoutEncounterGuard
import test_combat_trial_stream as trial
from test_hybrid_navigation import capability
from test_navigation_profiles import route_capability
from test_resident_goals import dormant_control
from test_scout_encounter_guard import binding, sample
from test_stream_client import CapturingRecorder


ROUTE = ReviewedScoutRoute(((-1135, 2267), (-1142, 2255)))


class HistoryRecorder(CapturingRecorder):
    """Mirror required terminal retention flags while keeping all bytes in memory."""
    dropped = dropped_events = dropped_observations = abandoned_frames = 0

    def __init__(self):
        """Track closure separately from queue admission for failure-path checks."""
        super().__init__()
        self.closed = False

    def close(self):
        """Return faithful lossless/closure accounting without starting an encoder."""
        self.closed = True
        return dict(complete=True, lossless=True, closed=True, workerRetired=True, error=None,
                    encodedFrames=len(self.frames), droppedFrames=self.dropped, droppedEvents=self.dropped_events,
                    droppedObservations=self.dropped_observations, abandonedFrames=self.abandoned_frames,
                    recordedObservations=len(self.frames), policyRgbEnabled=True,
                    policyRgbFrames=len(self.frames), policyRgbBytes=sum(len(pixels) for _, pixels in self.frames))


class HistoryPolicy:
    """Represent only transaction counters; real tensor parity is tested separately."""
    executed_history = execution_feedback = True
    observation_profile = P2P_NATIVE

    def __init__(self, during_predict=None):
        """Keep each inference, provisional label and completed native identity observable."""
        self.metadata = dict(synthetic=True, historyFrames=41, historyCommit=MODE, historyCommitMode=MODE)
        self.frames, self.before, self.images, self.commits = 0, 0, [], []
        self.pending, self.reset_count, self.during_predict = False, 0, during_predict

    def predict(self, image, size, **kwargs):
        """Alternate a model-compatible W with a raw no-op requiring native guidance."""
        if self.pending:raise AssertionError('A second prediction overtook a pending execution')
        self.before, self.frames, self.pending = self.frames, self.frames+1, True
        self.images.append(image)
        if self.during_predict:self.during_predict()
        keys = ['W'] if len(self.images) % 2 == 0 else []
        return dict(parseValid=True, fullActionMs=1, episodeStep=self.frames, validHistoryFrames=min(self.frames, 41),
                    steps=[dict(durationMs=50, keys=keys, mouseDx=0, mouseDy=0)])

    def prepare_executed_action(self, step):
        """Keep the exact commanded step pending, without permitting another inference."""
        if not self.pending:raise AssertionError('Missing transaction')
        self.selected = copy.deepcopy(step)
        return encode_controller_step(step)

    def finish_executed_action(self, receipt, request, accepted):
        """Use the production strict receipt checker on the inert native evidence."""
        verify_completed_receipt(receipt, request, accepted)
        if request['steps'][0] != self.selected:raise AssertionError('Changed selected action')
        self.pending = False
        self.commits.append(receipt['requestId'])

    def finish_action(self, accepted):
        """An admission can never promote a candidate in this mode."""
        if accepted:raise AssertionError('Admission was used as execution')
        self.frames, self.pending = self.before, False

    def executed_history_counters(self):
        """Expose the same twelve-token temporal accounting as the installed H41 model."""
        return dict(beforeFrames=self.before, afterFrames=self.frames, validFrames=min(self.frames, 41),
                    beforeIndex=self.before*12, afterIndex=self.frames*12,
                    beforeValidTokens=min(self.before, 41)*12, afterValidTokens=min(self.frames, 41)*12)

    def reset(self):
        """Retirement and endpoint cleanup discard history without losing test evidence."""
        self.frames, self.pending = 0, False
        self.reset_count += 1


class HistoryBridge(trial.TrialBridge):
    """Provide exact completed navigation receipts and a separately verified endpoint."""
    def __init__(self, *, bad_receipt=None, reject_first=False, hold_terminal=False, transform=None):
        """Reuse the inert native clock and source format; no bridge or OS input exists."""
        super().__init__(hold_terminal=hold_terminal)
        self.bad_receipt, self.reject_first, self.user_transform = bad_receipt, reject_first, transform
        self.hello.update(navigationGuidance=capability(), navigationProfiles=[SCOUT_PROFILE],
                          allowedKeys=['W', 'A', 'S', 'D'])
        self.terminal_returned = False

    def request(self, command, **arguments):
        """Advance to the endpoint only after three fully completed inert actions."""
        if command == 'enableNavigationGuidance':
            self.commands.append(command)
            return dict(type='navigationGuidance', enabled=True, capability=route_capability(SCOUT_GRASS_ROUTE)), b''
        if command == 'action' and self.reject_first:
            self.reject_first = False
            self.commands.append(command)
            return dict(type='rejected', requestId=arguments['requestId'], reason='synthetic_refusal'), b''
        row, pixels = super().request(command, **arguments)
        if command == 'action':
            selected = arguments['steps'][0]
            self.pending['appliedSteps'][0].update(keys=selected['keys'][:], mouseDx=selected['mouseDx'], mouseDy=selected['mouseDy'])
        if command == 'frame':
            # A returned native frame cannot have a host acquisition timestamp
            # later than this poll's server clock (the shared combat toy adds 2ms).
            row['capturedAtMs'] = row['serverNowMs']
            point = ROUTE.points[1] if len(self.completed) >= 3 else ROUTE.points[0]
            pose = dict(state='valid', frameId=row['frameId'], x=point[0], y=point[1],
                yawDegrees=route_heading(dict(zip(('x', 'y'), point)), ROUTE.points[1]) if point != ROUTE.points[1] else 30.,
                positionConfidence=.996, yawConfidence=.6, layerId='MapBack_2', mouseToStart=0, mouseToEnd=0,
                headingToStartDegrees=int(route_heading(dict(zip(('x', 'y'), point)), START)),
                headingToEndDegrees=int(route_heading(dict(zip(('x', 'y'), point)), END)))
            row.update(navigationPose=pose, motionEvidence=dict(status='normal', spaceKeyMatched=False))
            if 'combatEvidence' in row:
                row['combatEvidence'].update(enemyBarCandidates=[], playerHealthFractionEstimate=.9)
            if row.get('receipts'):
                self.terminal_returned = True
                if self.bad_receipt:
                    row['receipts'] = self.bad_receipt(copy.deepcopy(row['receipts']))
            if self.user_transform:row = self.user_transform(row)
        return row, pixels


def inert_arguments(folder, seconds=2., hold=50):
    """Reuse existing parser defaults, then bind explicit in-memory reviewed scout authority."""
    args = trial.CombatTrialStreamTests().arguments(folder, seconds=seconds)
    del args.combat_trial_binding
    del args.combat_trial_owner
    args.expected_process_id = args.expected_session_id = None
    args.p2p_executed_history, args.resident = True, True
    args.hybrid_navigation = args.navigation_guidance = True
    args.hybrid_route, args.reviewed_scout_route = ROUTE.route_id, ROUTE
    args.navigation_profile, args.hybrid_legs = SCOUT_PROFILE, 1
    args.history, args.action_hold_ms, args.input_keys = 41, hold, 'W,A,S,D'
    args.goal_intent, args.patrol_series_binding, args.max_input_actions = 'ground-navigation', ('inert', 'owner'), None
    return args


def run_fixture(folder, bridge=None, policy=None, recorder=None, *, control=None, args=None):
    """Expose the real loop and retained report/journal to the independent auditor tests."""
    bridge, policy, recorder = bridge or HistoryBridge(), policy or HistoryPolicy(), recorder or HistoryRecorder()
    control = control or dormant_control(folder, frozen_goal=True)
    control.set_initial_goal(dict(instruction='fixed scout'), 'ground-navigation')
    control.scout_encounter_guard = ScoutEncounterGuard(binding())
    args = args or inert_arguments(folder)
    with ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules, {'PIL': SimpleNamespace(
            Image=SimpleNamespace(frombytes=lambda mode, shape, pixels: pixels))}))
        stack.enter_context(patch.object(client, 'Bridge', return_value=bridge))
        stack.enter_context(patch.object(client, 'AsyncVideoRecorder', return_value=recorder))
        stack.enter_context(redirect_stdout(io.StringIO()))
        result = client.run_episode(args, policy, control)
    return result, json.loads((Path(folder)/'run.json').read_text(encoding='utf-8')), recorder, bridge, policy


def delay_post_terminal_source(bridge, policy, interrupt=None):
    """Repeat the last pre-terminal source twice, preserving its immutable fields and exact receipt."""
    state = dict(saved=None, active=False, repeats=[], mainPollsWhileWaiting=[])
    owner_thread, request = threading.get_ident(), bridge.request

    def transform(row):
        """Let only the normal background reader replace the temporarily repeated source."""
        if not bridge.terminal_returned:
            state['saved'] = copy.deepcopy(row)
        elif len(bridge.actions) == 1 and len(state['repeats']) < 2:
            current = row
            row = copy.deepcopy(state['saved'])
            row.update(receipts=copy.deepcopy(current.get('receipts', [])), serverNowMs=bridge.now())
            row['sourceFrameAgeMs'] = row['serverNowMs']-row['sourceFrame']['capturedAtMs']
            state['active'] = True
            state['repeats'].append((len(policy.images), len(bridge.actions)))
            if interrupt and len(state['repeats']) == 2:
                row = interrupt(row, current)
        else:
            state['active'] = False
        return row

    def observed_request(command, **arguments):
        """Expose accidental foreground frame polling during local-only source waits."""
        if command == 'frame' and state['active'] and threading.get_ident() == owner_thread:
            state['mainPollsWhileWaiting'].append(len(policy.images))
        return request(command, **arguments)

    bridge.user_transform, bridge.request = transform, observed_request
    return state


class SerializedStreamTests(unittest.TestCase):
    """Exercise native/model selection, exact terminal feedback and capture concurrency."""
    def test_three_completed_actions_preserve_history_and_verify_endpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            control = dormant_control(folder, frozen_goal=True)
            control.guarded_submit = Mock(wraps=control.guarded_submit)
            result, report, recorder, bridge, policy = run_fixture(folder, control=control)
            self.assertEqual(result, 0)
            self.assertEqual(report['endReason'], 'hybridLegLimit')
            self.assertEqual(len(bridge.actions), 3)
            self.assertEqual(len(bridge.completed), 3)
            self.assertEqual(len(policy.images), 3)
            self.assertEqual(control.guarded_submit.call_count, 3)
            self.assertEqual([row['validHistoryFrames'] for row in report['decisions']], [1, 2, 3])
            self.assertEqual([row['modelId'] for row in report['executedHistoryEvents']],
                             ['hybrid-native', 'open-p2p', 'hybrid-native'])
            self.assertTrue(all(row['historyCommitted'] for row in report['decisions']))
            self.assertEqual(report['proposalJournal'], dict(version=3, historyCommitMode=MODE))
            self.assertIsNone(bridge.pending)
            for index, event in enumerate(report['executedHistoryEvents']):
                self.assertEqual(event['arguments']['command'], 'action')
                self.assertEqual(event['step']['durationMs'], 50)
                self.assertEqual(event['history']['afterFrames'], index+1)
                journal_index = next(i for i, row in enumerate(recorder.events) if row == event)
                proposal_index = next(i for i, row in enumerate(recorder.events)
                    if row.get('type') == 'proposal' and row['acceptance'].get('requestId') == event['requestId'])
                receipt_index = next(i for i, row in enumerate(recorder.events) if row == event['receipt'])
                self.assertLess(receipt_index, proposal_index)
                self.assertLess(proposal_index, journal_index)
                if index:self.assertGreater(event['observationTimestampMs'], report['executedHistoryEvents'][index-1]['receipt']['endedAtMs'])

    def test_scope_changes_fail_before_bridge_or_inference(self):
        with tempfile.TemporaryDirectory() as folder:
            args, policy = inert_arguments(folder), HistoryPolicy()
            control = dormant_control(folder, frozen_goal=True)
            control.scout_encounter_guard = ScoutEncounterGuard(binding())
            self.assertTrue(validate_executed_history_options(args, policy, control, require_bound=True))
            changes = dict(action_hold_ms=100, history=1, hybrid_legs=2, native_combat_observation=False,
                           retain_policy_rgb=False, navigation_climb_recovery=True, seconds=36,
                           allow_inspected_obstacle_recovery=True, p2p_executed_history=False)
            for key, value in changes.items():
                changed = copy.copy(args)
                setattr(changed, key, value)
                with self.subTest(key=key), self.assertRaises(ValueError), patch.object(client, 'Bridge') as bridge:
                    try:client.run_episode(changed, policy, control)
                    finally:bridge.assert_not_called()

    def test_server_rejection_rolls_back_without_discarding_later_history(self):
        with tempfile.TemporaryDirectory() as folder:
            _, report, _, bridge, _ = run_fixture(folder, bridge=HistoryBridge(reject_first=True))
            events = report['executedHistoryEvents']
            self.assertEqual(events[0]['outcome'], 'rejected')
            self.assertEqual(events[0]['history']['afterFrames'], 0)
            self.assertIsNone(events[0]['receipt'])
            self.assertIsNotNone(events[0]['arguments'])
            self.assertEqual([row['history']['afterFrames'] for row in events[1:]], [1, 2, 3])
            self.assertEqual(len(bridge.actions), 3)

    def test_noncompleted_or_inexact_receipt_retires_without_second_action(self):
        mutations = [lambda rows:[dict(rows[0], status='replaced', reason='newer_proposal')],
                     lambda rows:[dict(rows[0], appliedSteps=[])],
                     lambda rows:[dict(rows[0], appliedSteps=[dict(rows[0]['appliedSteps'][0], keys=['A'])])]]
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as folder:
                bridge, policy = HistoryBridge(bad_receipt=mutate), HistoryPolicy()
                with self.assertRaises(ValueError):run_fixture(folder, bridge=bridge, policy=policy)
                report = json.loads((Path(folder)/'run.json').read_text(encoding='utf-8'))
                self.assertEqual(len(bridge.actions), 1)
                self.assertEqual(report['executedHistoryEvents'][0]['outcome'], 'failed')
                self.assertEqual(report['status'], 'failed')
                self.assertFalse(policy.pending)
                self.assertTrue(bridge.released.is_set())

    def test_missing_receipt_cannot_extend_the_lease_or_infer_again(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge, policy = HistoryBridge(hold_terminal=True), HistoryPolicy()
            args = inert_arguments(folder, seconds=.25)
            with self.assertRaisesRegex(RuntimeError, 'lease ended'):
                run_fixture(folder, bridge, policy, args=args)
            self.assertEqual((len(bridge.actions), len(policy.images)), (1, 1))
            self.assertTrue(bridge.released.is_set())
            self.assertIsNone(bridge.pending)

    def test_sixty_ms_remains_explicit_and_does_not_repeat_mouse(self):
        with tempfile.TemporaryDirectory() as folder:
            _, report, _, bridge, _ = run_fixture(folder, args=inert_arguments(folder, hold=60))
            self.assertTrue(all(row['steps'][0]['durationMs'] == 60 for row in bridge.actions))
            self.assertTrue(all(row['rawPolicySteps'][0]['durationMs'] == 50 for row in report['decisions']))
            self.assertEqual(len(report['executedHistoryEvents']), 3)

    def test_prediction_start_clock_limits_both_holds_without_pending_overlap(self):
        for hold in (50, 60):
            with self.subTest(hold=hold), tempfile.TemporaryDirectory() as folder:
                bridge = HistoryBridge()
                policy = HistoryPolicy(lambda:self.assertIsNone(bridge.pending))
                args = inert_arguments(folder, hold=hold)
                args.decision_hz, args.fps = 10., 20.
                _, report, _, _, _ = run_fixture(folder, bridge, policy, args=args)
                starts = [row['frameTiming']['predictionStartedAtClientNs'] for row in report['decisions']]
                self.assertEqual(len(starts), 3)
                # This is a minimum interval, with no assertion about host wakeup latency.
                self.assertTrue(all(right-left >= 100_000_000-1 for left, right in zip(starts, starts[1:])))
                self.assertEqual(report['executedHistoryScheduling']['policy'], 'prediction-start-minimum-v1')
                self.assertEqual([row['history']['afterFrames'] for row in report['executedHistoryEvents']], [1, 2, 3])

    def test_source_waits_keep_the_permit_and_do_not_force_poll_the_pipe(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge, policy, trace = HistoryBridge(), HistoryPolicy(), []
            delayed = delay_post_terminal_source(bridge, policy)
            args = inert_arguments(folder)
            args.decision_hz, args.fps = 10., 20.
            advance = ExecutedHistoryCadence.advance

            def observed_advance(cadence, now):
                """Record scheduling arithmetic without mocking the clock or relaxing source admission."""
                advance(cadence, now)
                trace.append((now, cadence.next_at, len(policy.images), delayed['active']))

            with patch.object(ExecutedHistoryCadence, 'advance', observed_advance):
                _, report, _, _, _ = run_fixture(folder, bridge, policy, args=args)
            self.assertEqual(delayed['repeats'], [(1, 1), (1, 1)])
            self.assertEqual(delayed['mainPollsWhileWaiting'], [])
            start = report['decisions'][0]['frameTiming']['predictionStartedAtClientNs']/1e9
            overdue = [(now, next_at) for now, next_at, count, waiting in trace
                       if count == 1 and waiting and now >= start+.1]
            self.assertGreaterEqual(len(overdue), 2)
            for now, next_at in overdue:
                self.assertAlmostEqual(next_at, now+.005, places=7)
            events = report['executedHistoryEvents']
            self.assertEqual([row['history']['afterFrames'] for row in events], [1, 2, 3])
            for before, after in zip(events, events[1:]):
                self.assertGreater(after['observationTimestampMs'], before['receipt']['endedAtMs'])
                self.assertGreater(after['frameId'], before['frameId'])
                self.assertGreater(after['sourceFrame']['timestamp100ns'], before['sourceFrame']['timestamp100ns'])

    def test_source_waits_still_observe_stop_pause_hazard_and_recording_failure(self):
        for interruption in ('stop', 'pause', 'hazard', 'recording'):
            with self.subTest(interruption=interruption), tempfile.TemporaryDirectory() as folder:
                bridge, policy, triggered = HistoryBridge(), HistoryPolicy(), []
                control = dormant_control(folder, frozen_goal=True)

                class WaitingRecorder(HistoryRecorder):
                    """Reject a sensor event only after the first action has terminal evidence."""
                    def event(self, event):
                        """A source wait must retain the same strict recorder gate as inference."""
                        if interruption == 'recording' and triggered and event.get('type') == 'scoutEncounterGuardObservation':
                            return False
                        return super().event(event)

                def interrupt(row, current):
                    """Change authority or introduce fresh hazardous evidence while no source is eligible."""
                    triggered.append(True)
                    if interruption in ('stop', 'pause'):
                        with control._lock:
                            control._command, control._epoch = interruption, control._epoch+1
                    elif interruption == 'hazard':
                        row = current
                        row['combatEvidence']['enemyBarCandidates'] = sample(candidates=True)['combatEvidence']['enemyBarCandidates']
                    return row

                delayed = delay_post_terminal_source(bridge, policy, interrupt)
                args, recorder = inert_arguments(folder), WaitingRecorder()
                args.decision_hz, args.fps = 10., 20.
                if interruption == 'stop':
                    _, report, _, _, _ = run_fixture(folder, bridge, policy, recorder, control=control, args=args)
                    self.assertEqual(report['endReason'], 'userStop')
                else:
                    with self.assertRaises(Exception):
                        run_fixture(folder, bridge, policy, recorder, control=control, args=args)
                self.assertTrue(triggered)
                self.assertEqual((len(bridge.actions), len(policy.images), len(policy.commits)), (1, 1, 1))
                self.assertEqual(delayed['mainPollsWhileWaiting'], [])
                self.assertTrue(bridge.released.is_set())
                self.assertTrue(recorder.closed)

    def test_duplicate_and_unknown_receipts_cannot_authorize_another_prediction(self):
        for mutate in (lambda rows:rows+copy.deepcopy(rows),
                       lambda rows:[dict(rows[0], requestId='unknown')]):
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as folder:
                bridge, policy = HistoryBridge(bad_receipt=mutate), HistoryPolicy()
                with self.assertRaises(RuntimeError):run_fixture(folder, bridge, policy)
                report = json.loads((Path(folder)/'run.json').read_text(encoding='utf-8'))
                self.assertIn('unknown or duplicated', report['streamError'])
                self.assertEqual((len(bridge.actions), len(policy.images)), (1, 1))
                self.assertTrue(bridge.released.is_set())

    def test_reused_source_waits_after_terminal_without_reset_or_inference(self):
        with tempfile.TemporaryDirectory() as folder:
            saved, repeats = [], []
            bridge = HistoryBridge()
            def reuse(row):
                """Re-poll the same immutable source briefly after its action has completed."""
                if not bridge.terminal_returned or row.get('receipts'):
                    saved[:] = [copy.deepcopy(row)]
                elif len(repeats) < 2:
                    old = saved[0]
                    row = copy.deepcopy(old)
                    row['receipts'] = []
                    row['serverNowMs'] = bridge.now()
                    row['sourceFrameAgeMs'] = row['serverNowMs']-row['sourceFrame']['capturedAtMs']
                    repeats.append(len(bridge.actions))
                return row
            # Preserve the receipt-carrying source; repeat only subsequent polls.
            bridge.user_transform = reuse
            _, report, _, _, policy = run_fixture(folder, bridge)
            self.assertEqual(repeats, [1, 1])
            self.assertEqual(len(policy.images), 3)
            self.assertEqual([event['history']['afterFrames'] for event in report['executedHistoryEvents']], [1, 2, 3])

    def test_hazard_while_prediction_is_in_flight_prevents_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            entered = threading.Event()
            def hazard(row):
                """Publish a qualified candidate on the independent intake path."""
                if entered.is_set() and 'combatEvidence' in row:
                    row['combatEvidence']['enemyBarCandidates'] = sample(candidates=True)['combatEvidence']['enemyBarCandidates']
                return row
            bridge = HistoryBridge(transform=hazard)
            def during_predict():
                """Keep the CPU prediction open until the guard has released its owner."""
                entered.set()
                if not bridge.released.wait(2):raise AssertionError('Hazard did not release')
            policy = HistoryPolicy(during_predict)
            with self.assertRaises(Exception):run_fixture(folder, bridge, policy)
            self.assertEqual(bridge.actions, [])
            self.assertFalse(policy.pending)

    def test_hazard_while_candidate_is_in_flight_prevents_second_action(self):
        with tempfile.TemporaryDirectory() as folder:
            entered = threading.Event()
            def hazard(row):
                """Trip after the first action starts, while the corrected cache remains provisional."""
                if entered.is_set() and 'combatEvidence' in row:
                    row['combatEvidence']['enemyBarCandidates'] = sample(candidates=True)['combatEvidence']['enemyBarCandidates']
                return row
            bridge, policy = HistoryBridge(transform=hazard), HistoryPolicy()
            original = policy.prepare_executed_action
            def delayed(step):
                """Simulate GPU work that finishes only after a newer hazardous capture."""
                result = original(step)
                entered.set()
                if not bridge.released.wait(2):raise AssertionError('Hazard did not release')
                return result
            policy.prepare_executed_action = delayed
            with self.assertRaises(RuntimeError):run_fixture(folder, bridge, policy)
            self.assertEqual((len(bridge.actions), len(policy.images)), (1, 1))
            self.assertEqual(policy.commits, [])
            self.assertFalse(policy.pending)

    def test_pause_during_prediction_is_a_local_refusal_then_terminal(self):
        with tempfile.TemporaryDirectory() as folder:
            control = dormant_control(folder, frozen_goal=True)
            def pause():
                """Invalidate the frozen submission token without sending any bridge input."""
                with control._lock:
                    control._command, control._epoch = 'pause', control._epoch+1
            policy, bridge = HistoryPolicy(pause), HistoryBridge()
            with self.assertRaisesRegex(RuntimeError, 'interruption is terminal'):
                run_fixture(folder, bridge, policy, control=control)
            report = json.loads((Path(folder)/'run.json').read_text(encoding='utf-8'))
            self.assertEqual(bridge.actions, [])
            self.assertEqual(report['executedHistoryEvents'][0]['outcome'], 'rejected')
            self.assertIsNone(report['executedHistoryEvents'][0]['arguments'])

    def test_queue_eviction_is_terminal_even_when_put_returns_true(self):
        class EvictingRecorder(HistoryRecorder):
            """Expose a queue eviction without an encoder error or false enqueue return."""
            def event(self, event):
                """Lose evidence immediately after the first accepted proposal is retained."""
                result = super().event(event)
                if event.get('type') == 'proposal':self.dropped_events = 1
                return result
        with tempfile.TemporaryDirectory() as folder:
            bridge, recorder = HistoryBridge(), EvictingRecorder()
            with self.assertRaisesRegex(RuntimeError, 'retention failed'):
                run_fixture(folder, bridge, recorder=recorder)
            self.assertEqual(len(bridge.actions), 1)
            self.assertTrue(bridge.released.is_set())
            self.assertTrue(recorder.closed)
            self.assertEqual(bridge.commands[-1], 'stop')

    def test_false_enqueue_is_latched_even_without_an_error_or_loss_counter(self):
        recorder = HistoryRecorder()
        recorder.put = lambda metadata, pixels: False
        required = ExecutedHistoryRecorder(recorder)
        with self.assertRaises(RuntimeError):required.put({}, b'')
        recorder.put = lambda metadata, pixels: True
        with self.assertRaises(RuntimeError):required.check()

    def test_reader_recording_failure_cannot_overtake_an_inflight_prediction(self):
        with tempfile.TemporaryDirectory() as folder:
            entered, refused = threading.Event(), threading.Event()
            class RefusingRecorder(HistoryRecorder):
                """Return false without changing any optional encoder telemetry."""
                def put(self, metadata, pixels):
                    """Refuse the independently captured frame once inference is pending."""
                    if entered.is_set():
                        refused.set()
                        return False
                    return super().put(metadata, pixels)
            def during_predict():
                """Resume directly after the producer refused retention."""
                entered.set()
                if not refused.wait(2):raise AssertionError('Reader did not refuse retention')
            bridge, recorder, policy = HistoryBridge(), RefusingRecorder(), HistoryPolicy(during_predict)
            with self.assertRaises(RuntimeError):run_fixture(folder, bridge, policy, recorder)
            self.assertEqual(bridge.actions, [])
            self.assertTrue(recorder.closed)
            self.assertTrue(bridge.released.is_set())

    def test_initial_journal_failure_releases_closes_and_keeps_original_error(self):
        class InitialFailureRecorder(HistoryRecorder):
            """Fail before the main episode finally has begun."""
            def event(self, event):
                """Never admit an episode-start record."""
                raise RuntimeError('initial-history-journal-failure')
        with tempfile.TemporaryDirectory() as folder:
            bridge, recorder = HistoryBridge(), InitialFailureRecorder()
            with self.assertRaisesRegex(RuntimeError, 'initial-history-journal-failure'):
                run_fixture(folder, bridge, recorder=recorder)
            self.assertEqual(bridge.actions, [])
            self.assertTrue(bridge.released.is_set())
            self.assertTrue(recorder.closed)
            bridge.handle.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
