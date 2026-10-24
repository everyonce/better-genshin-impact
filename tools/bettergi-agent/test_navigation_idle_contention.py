"""Deterministic idle-window regressions and sanitized r13 timing replay; no game or GPU access."""
import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from navigation_idle_recovery import RecoverySuperseded, capture_context
import stream_client as client
from test_navigation_idle_recovery import CAPABILITY, frame, proposal, recovery, released


def missed(reason='observationTooOld', kind='notSubmitted', keys=()):
    """Keep rejected policy intent intact instead of manufacturing a replacement no-op."""
    value = proposal(keys)
    value['acceptance'] = {'type': kind, 'reason': reason}
    return value


def expired(request_id):
    """A matched server deadline receipt proves this accepted no-op dispatched no input."""
    return {'requestId': request_id, 'status': 'cancelled', 'reason': 'start_deadline_expired',
            'modelId': 'open-p2p', 'appliedSteps': []}


class ContentionRecoveryTests(unittest.TestCase):
    def test_pre_dispatch_supersession_preserves_latch_attempts_and_pending_receipts(self):
        value = recovery()
        value.proposal(proposal(['W'], 'movement'), frame(), 0, True)
        event = None
        for index in range(6):
            event = value.proposal(proposal(request_id=str(index)), frame(), index*.2, True)
        before = (dict(value.pending_noops), dict(value.pending_movement))
        reset, discard = Mock(), Mock()
        result = value.execute(event, Mock(side_effect=RecoverySuperseded()), reset, discard, lambda: True)
        self.assertEqual(result['outcome'], 'supersededBeforeRelease')
        self.assertEqual((value.attempts, value.resets, value.armed), (0, 0, True))
        self.assertEqual((value.pending_noops, value.pending_movement), before)
        self.assertIsNone(value.started)
        reset.assert_not_called()
        discard.assert_not_called()

    def test_episode_rechecks_context_after_waiting_for_an_inflight_capture_poll(self):
        begin, capture_holds_lock, allow_transition = threading.Event(), threading.Event(), threading.Event()
        value, checked, waited = recovery(), [], []
        original_execute, native_lock = value.execute, threading.Lock

        class ObservedLock:
            """Let the blocked producer finish only once recovery reaches its occupied ingestion lock."""
            def __init__(self):
                self.lock = native_lock()

            def __enter__(self):
                if sys._getframe(1).f_code.co_name == 'release_for_recovery' and self.lock.locked():
                    waited.append(True)
                    allow_transition.set()
                self.lock.acquire()
                return self

            def __exit__(self, *args):
                self.lock.release()

        def lock_factory():
            # Only run_episode's direct ingestion lock; Thread/Event/LatestFrame locks remain native.
            return ObservedLock() if sys._getframe(1).f_code.co_name == 'run_episode' else native_lock()

        def execute(*args):
            before = (dict(value.pending_noops), dict(value.pending_movement))
            begin.set()
            if not capture_holds_lock.wait(1):
                raise AssertionError('Synthetic poll did not acquire the ingestion lock')
            outcome = original_execute(*args)
            checked.append((outcome, before, (dict(value.pending_noops), dict(value.pending_movement))))
            return outcome
        value.execute = execute

        class FakeBridge:
            """Publish a new native generation while a valid idle trigger waits for frame ingestion."""
            def __init__(self):
                self.hello = {'sessionId': 'test', 'inputEnabled': True, 'allowedKeys': ['W'],
                              'supportsRelease': True, 'motionEvidence': CAPABILITY,
                              'worldReadiness': {'version': 1, 'requiredForInput': True}}
                self.handle = SimpleNamespace(close=lambda: None)
                self.start, self.count, self.releases, self.changed = time.perf_counter(), 0, 0, False

            def request(self, command, **kwargs):
                if command == 'stop':
                    return {'type': 'stopped', 'receipts': []}, b''
                if command == 'action':
                    return {'type': 'accepted', 'requestId': kwargs['requestId']}, b''
                if command == 'release':
                    self.releases += 1
                    return released(), b''
                if begin.is_set() and not self.changed:
                    capture_holds_lock.set()
                    if not allow_transition.wait(1):
                        raise AssertionError('Recovery did not reach the occupied ingestion lock')
                    self.changed = True
                self.count += 1
                stamp = 1000 + (time.perf_counter()-self.start)*1000
                item = frame(stamp-3, epoch=7)
                item['sourceFrame']['captureEpoch'] = 'native-b' if self.changed else 'native-a'
                item.update(type='frame', frameId=self.count, width=2, height=2,
                            pixelFormat='rgb24', sourceWidth=2, sourceHeight=2, receipts=[])
                return item, bytes(range(12))

        class FakePolicy:
            """Seed a sustained idle window, then use the real proposal/recovery transaction."""
            execution_feedback = True
            metadata = {'synthetic': True}
            seeded = False

            def predict(self, image, size):
                if not self.seeded:
                    self.seeded = True
                    now = time.perf_counter()
                    value.proposal(proposal(['W'], 'movement'), frame(), now-1.3, True)
                    for index in range(6):
                        value.proposal(proposal(request_id=f'seed-{index}'), frame(), now-1.1+index*.2, True)
                return dict(parseValid=True, fullActionMs=0, steps=proposal()['steps'])

            def finish_action(self, accepted):
                pass

            def reset(self):
                pass

        with tempfile.TemporaryDirectory() as directory:
            args = client.parse_arguments(['--model', 'open-p2p', '--source', 'fake', '--checkpoint', 'fake',
                '--cuda-graph', '--p2p-fast-start', '--p2p-execution-feedback', '--enable-input',
                '--goal-intent', 'ground-navigation', '--navigation-idle-reset-seconds', '1',
                '--seconds', '2', '--max-input-actions', '2', '--fps', '100', '--decision-hz', '100',
                '--soft-cadence', '--output', str(Path(directory)/'report.json')])
            bridge = FakeBridge()
            with patch.object(client, 'Bridge', return_value=bridge), \
                    patch.object(client, 'NavigationIdleRecovery', return_value=value), \
                    patch.object(client.threading, 'Lock', new=lock_factory), \
                    patch.dict(sys.modules, {'PIL': SimpleNamespace(Image=SimpleNamespace(frombytes=lambda *args: args[2]))}), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(client.run_episode(args, FakePolicy()), 0)
        self.assertEqual(waited, [True])
        self.assertEqual(len(checked), 1)
        self.assertEqual(checked[0][0]['outcome'], 'supersededBeforeRelease')
        self.assertEqual(checked[0][1], checked[0][2])
        self.assertEqual((bridge.releases, value.attempts, value.resets, value.armed), (0, 0, 0, True))

    def test_episode_latches_transitions_that_disappear_while_prediction_is_running(self):
        for transition in ('cached-world-block', 'source-generation', 'fly-and-back'):
            with self.subTest(transition=transition), tempfile.TemporaryDirectory() as directory:
                begin, published_again = threading.Event(), threading.Event()
                value, checked = recovery(), []
                original_proposal = value.proposal

                def inspect(*args, **kwargs):
                    result = original_proposal(*args, **kwargs)
                    if args[0]['acceptance'].get('reason') == 'unappliedActionHistory':
                        checked.append((value.started, kwargs['latest_eligible']))
                    return result
                value.proposal = inspect

                class FakeBridge:
                    """Hide a hard transition behind a later ready frame plus a matching timing receipt."""
                    def __init__(self):
                        self.hello = {'sessionId': 'test', 'inputEnabled': True, 'allowedKeys': ['W'],
                                      'supportsRelease': True, 'motionEvidence': CAPABILITY,
                                      'worldReadiness': {'version': 1, 'requiredForInput': True}}
                        self.handle = SimpleNamespace(close=lambda: None)
                        self.start, self.stage = time.perf_counter(), 0

                    def request(self, command, **kwargs):
                        stamp = 1000 + (time.perf_counter()-self.start)*1000
                        if command == 'stop':
                            return {'type': 'stopped', 'receipts': []}, b''
                        if command == 'action':
                            return {'type': 'rejected', 'reason': 'start_deadline_expired'}, b''
                        if command == 'release':
                            return {'type': 'released', 'serverNowMs': stamp, 'receipts': [],
                                    'worldReadiness': {'ready': False, 'epoch': 8}}, b''
                        if begin.is_set():
                            self.stage += 1
                        if self.stage >= 3:
                            published_again.set()  # The preceding ready payload has already been ingested.
                        item = frame(stamp-3, epoch=7)
                        item['sourceFrame']['captureEpoch'] = 'native-a'
                        item.update(type='frame', frameId=max(1, self.stage+1), width=2, height=2,
                                    pixelFormat='rgb24', sourceWidth=2, sourceHeight=2, receipts=[])
                        if self.stage == 1:
                            if transition == 'cached-world-block':
                                item.update(frameId=1, worldReadiness={'ready': False, 'epoch': 8})
                            elif transition == 'source-generation':
                                item['sourceFrame']['captureEpoch'] = 'native-b'
                            else:
                                item['motionEvidence'].update(status='fly', spaceKeyMatched=True, xKeyMatched=False)
                        if self.stage == 2:
                            item['receipts'] = [expired('seed')]
                        return item, bytes(range(12))

                class FakePolicy:
                    """Keep inference on its serial thread while the real ingestion loop observes transitions."""
                    execution_feedback = True
                    metadata = {'synthetic': True}

                    def predict(self, image, size):
                        if not begin.is_set():
                            value.proposal(proposal(request_id='seed'), frame(), time.perf_counter()-.2, True)
                            begin.set()
                            if not published_again.wait(1):
                                raise AssertionError('Synthetic capture did not finish its transition')
                        return dict(parseValid=True, fullActionMs=0, steps=proposal()['steps'])

                    def finish_action(self, accepted):
                        pass

                    def reset(self):
                        pass

                args = client.parse_arguments(['--model', 'open-p2p', '--source', 'fake', '--checkpoint', 'fake',
                    '--cuda-graph', '--p2p-fast-start', '--p2p-execution-feedback', '--enable-input',
                    '--goal-intent', 'ground-navigation', '--navigation-idle-reset-seconds', '1',
                    '--seconds', '.3', '--fps', '100', '--decision-hz', '100', '--soft-cadence',
                    '--output', str(Path(directory)/'report.json')])
                with patch.object(client, 'Bridge', return_value=FakeBridge()), \
                        patch.object(client, 'NavigationIdleRecovery', return_value=value), \
                        patch.dict(sys.modules, {'PIL': SimpleNamespace(Image=SimpleNamespace(frombytes=lambda *args: args[2]))}), \
                        redirect_stdout(io.StringIO()):
                    self.assertEqual(client.run_episode(args, FakePolicy()), 0)
                self.assertTrue(checked)
                self.assertEqual(checked[0], (None, False))
                self.assertEqual(value.attempts, 0)

    def test_capture_context_preserves_clock_mode_but_distinguishes_hard_discontinuities(self):
        before = frame(epoch=7)
        before['sourceFrame']['captureEpoch'] = 'native-a'
        same = frame(stamp=1100, epoch=7)
        same['sourceFrame']['captureEpoch'] = 'native-a'
        same['sourceFrame']['freshnessClockKind'] = 'reported_compositor_qpc'
        self.assertEqual(capture_context(before), capture_context(same))
        for change in ({'worldReadiness': {'ready': False, 'epoch': 8}},
                       {'worldReadiness': {'ready': True, 'epoch': 8}},
                       {'inputAvailable': False}, {'sourceFrame': None},
                       {'sourceFrame': {'captureEpoch': 'native-b'}},
                       {'motionEvidence': {'status': 'climb'}}, {'motionEvidence': {'status': 'fly'}}):
            # The same payload/frameId may accompany a newer current readiness snapshot.
            self.assertNotEqual(capture_context(before), capture_context(dict(before, **change)))

    def test_short_timing_holes_preserve_but_never_start_renew_or_trigger_a_window(self):
        value = recovery()
        self.assertIsNone(value.proposal(missed(), frame(), 0, False, latest_eligible=True))
        self.assertIsNone(value.started)
        for now in (0, .25, .5, .75):
            value.proposal(proposal(), frame(), now, True)
        self.assertIsNone(value.proposal(missed(), frame(), 1.05, False, latest_eligible=True))
        self.assertEqual(value.last_noop, .75)
        self.assertEqual(value.noops, 4)
        self.assertEqual(value.attempts, 0)
        trigger = value.proposal(proposal(), frame(), 1.1, True, latest_eligible=True)
        self.assertIsNotNone(trigger)
        self.assertEqual(trigger['acceptedNoops'], 5)
        self.assertAlmostEqual(trigger['noopSeconds'], 1.1)
        self.assertEqual(value.snapshot()['preservedTimingGapCounts'], {'observationTooOld': 1})

    def test_timing_holes_require_independent_evidence_and_recent_accepted_noops(self):
        for now, latest in ((.25, False), (.501, True), (float('nan'), True), (float('inf'), True)):
            value = recovery()
            value.proposal(proposal(), frame(), 0, True)
            value.proposal(missed(), frame(), now, False, latest_eligible=latest)
            self.assertIsNone(value.started)
        value = recovery()
        value.proposal(proposal(), frame(), 0, True)
        for now in (.2, .4, .5):
            value.proposal(missed(), frame(), now, False, latest_eligible=True)
            self.assertEqual(value.started, 0)
        value.proposal(missed(), frame(), .51, False, latest_eligible=True)
        self.assertIsNone(value.started)  # Repeated gaps never renew the acceptance clock.

    def test_unknown_rejections_and_meaningful_policy_intent_still_break_context(self):
        for result in (missed('trialKeyNotAllowed'), missed('worldChangedDuringPrediction'),
                       missed('unappliedActionHistory'), missed(keys=['LBUTTON']), proposal(dx=1),
                       missed('start_deadline_expired', 'notSubmitted')):
            value = recovery()
            value.proposal(proposal(), frame(), 0, True)
            value.proposal(result, frame(), .2, False, latest_eligible=True)
            self.assertIsNone(value.started)
        value = recovery()
        value.proposal(proposal(), frame(), 0, True)
        value.proposal(missed('start_deadline_expired', 'rejected'), frame(), .2, False, latest_eligible=True)
        self.assertEqual(value.started, 0)

    def test_zero_step_noop_expiry_must_match_current_goal_and_exact_receipt_kind(self):
        value = recovery()
        value.proposal(proposal(request_id='known'), frame(), 0, True)
        receipt = expired('known')
        self.assertTrue(value.matched_noop_expiries([receipt]))
        for items in ([], [expired('unknown')], [dict(receipt, status='replaced')],
                      [dict(receipt, reason='client_release')], [dict(receipt, appliedSteps=None)],
                      [dict(receipt, appliedSteps=[{'keys': [], 'startedAtMs': 1}])],
                      [receipt, expired('unknown')]):
            self.assertFalse(value.matched_noop_expiries(items))
        value.history_reset(True, .2, True)
        self.assertEqual(value.started, 0)
        value.proposal(missed('unappliedActionHistory'), frame(), .3, False,
                       latest_eligible=True, matched_noop_expiries=True)
        self.assertEqual(value.started, 0)
        value.receipt(receipt)
        self.assertFalse(value.matched_noop_expiries([receipt]))
        value.set_goal(1, 'changed', 'ground-navigation')
        self.assertFalse(value.matched_noop_expiries([receipt]))
        self.assertIsNone(value.started)

    def test_unmatched_movement_expiry_or_ineligible_evidence_keeps_history_reset_hard(self):
        value = recovery()
        value.proposal(proposal(['W'], 'movement'), frame(), 0, True)
        value.proposal(proposal(request_id='noop'), frame(), .1, True)
        self.assertFalse(value.matched_noop_expiries([expired('movement')]))
        value.history_reset(False, .2, True)
        self.assertIsNone(value.started)
        for now, latest in ((.3, False), (1.0, True)):
            value = recovery()
            value.proposal(proposal(), frame(), 0, True)
            value.history_reset(True, now, latest)
            self.assertIsNone(value.started)

    def test_hard_capture_control_and_goal_interrupts_cannot_be_bridged(self):
        for reason in ('ineligibleCapture', 'worldTransition', 'userPause', 'controlError',
                       'goalChanged', 'acceptanceGapHistoryReset'):
            value = recovery()
            value.proposal(proposal(), frame(), 0, True)
            value.proposal(missed(), frame(), .1, False, latest_eligible=True)
            value.interrupt(reason)
            value.proposal(missed(), frame(), .2, False, latest_eligible=True)
            self.assertIsNone(value.started)
            self.assertEqual(value.snapshot()['lastWindow']['endedBy'], reason)

    def test_pending_noop_ledger_and_diagnostic_cardinality_are_bounded(self):
        value = recovery(120)
        for index in range(300):
            value.proposal(proposal(request_id=str(index)), frame(), index*.01, True)
        self.assertEqual(len(value.pending_noops), 128)
        self.assertFalse(value.matched_noop_expiries([expired('0')]))
        for index in range(300):
            value.interrupt('external_reason_' + str(index))
        state = value.snapshot()
        self.assertLessEqual(len(state['interruptionCounts']), 17)
        self.assertIn('other', state['interruptionCounts'])
        self.assertAlmostEqual(state['maximumWindowSeconds'], 2.99)
        self.assertEqual(state['windowSeconds'], 0)

    def test_r13_replay_survives_only_timing_noops_and_triggers_once_in_second_run(self):
        fixture = json.loads((Path(__file__).parent/'fixtures/navigation_idle_r13.json').read_text())
        self.assertEqual(len(fixture['decisions']), 215)
        expiry_before = fixture['noopExpiryBeforeDecision']
        tolerant, strict = recovery(8), recovery(8)
        triggers = []
        for frame_id, offset_ms, accepted, reason, keys in fixture['decisions']:
            now = offset_ms / 1000
            result = proposal(keys, f'r13-{frame_id}')
            result['acceptance'].update(type=accepted, reason=reason)
            image = dict(frame(), frameId=frame_id)
            receipt = expired(f'r13-{expiry_before[str(frame_id)]}') if str(frame_id) in expiry_before else None
            matched = tolerant.matched_noop_expiries([receipt]) if receipt else False
            event = tolerant.proposal(result, image, now, accepted == 'accepted',
                latest_eligible=True, matched_noop_expiries=matched)
            self.assertIsNone(strict.proposal(result, image, now, accepted == 'accepted'))
            if receipt:
                tolerant.history_reset(matched, now, True)
                strict.history_reset(False, now, True)
                tolerant.receipt(receipt)
                strict.receipt(receipt)
            if frame_id == 817:
                self.assertEqual(keys, ['LBUTTON'])  # Blocked meaningful intent still starts a new window.
                self.assertIsNone(tolerant.started)
            if event:
                triggers.append((frame_id, event))
                outcome = tolerant.execute(event, released, Mock(), Mock(), lambda: True)
                self.assertEqual(outcome['outcome'], 'reset')
        self.assertEqual(len(triggers), 1)
        self.assertTrue(819 < triggers[0][0] < 1068)
        self.assertGreaterEqual(triggers[0][1]['noopSeconds'], 8)
        self.assertLess(strict.maximum_window_seconds, 3.6)
        self.assertEqual((tolerant.attempts, tolerant.resets), (1, 1))
        self.assertFalse(tolerant.armed)
        self.assertGreater(tolerant.snapshot()['preservedTimingGapCounts']['noopReceiptHistoryReset'], 0)


if __name__ == '__main__':
    unittest.main()
