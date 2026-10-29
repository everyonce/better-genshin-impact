"""CPU-only composed recovery/stream/rollover tests; no live transport or model loads."""
import ast
import copy
from collections import OrderedDict, deque
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import stream_client as client
from stream_segments import StreamSegments
from test_navigation_climb_recovery import frame, hello


def resident_control_methods():
    """Use four exact pure method bodies without importing the operational resident module."""
    source = Path(__file__).with_name('resident_runtime.py').read_text(encoding='utf-8')
    owner = next(node for node in ast.parse(source).body
                 if isinstance(node, ast.ClassDef) and node.name == 'ResidentControl')
    names = {'guarded_submit', 'prediction_token', '_effective_command', '_observe'}
    methods = [node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in methods} == names
    owner.body = methods
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[owner], type_ignores=[])),
                 '<selected-resident-control-methods>', 'exec'), namespace)
    return namespace['ResidentControl']


ResidentMethods = resident_control_methods()


class Clock:
    """One deterministic monotonic clock shared by the fake server and serial client."""
    def __init__(self):
        self.ns = 1_000_000_000

    def seconds(self):
        return self.ns / 1e9

    def nanos(self):
        return self.ns

    def sleep_until(self, deadline, stopped):
        self.ns = max(self.ns, round(deadline*1e9))
        return not stopped.is_set()


class Control(ResidentMethods):
    """Inert resident identity; no monitor, status files or native session discovery."""
    run_id = 'synthetic-resident'
    def __init__(self):
        self._lock = threading.Lock()
        self._epoch, self._goal_version, self._applied_goal_id, self._command = 0, 0, None, 'run'
        self._goal_status = self._goal_request = self._goal_error = self._error = None
        self._seen_goals = {}
        self._goal_intent = 'ground-navigation'
        self.states = []

    @property
    def token(self):
        """Expose the real method's tuple for existing synthetic scenarios."""
        return self.prediction_token()

    @token.setter
    def token(self, value):
        """Change fake authority under the same plain lock as the real monitor."""
        with self._lock:
            self._epoch, self._goal_version, self._applied_goal_id, self._command = value

    @property
    def intent(self):
        """Keep existing fixtures readable without introducing a runtime policy."""
        return self._goal_intent

    @intent.setter
    def intent(self, value):
        """Assign only the fixture's inert goal classification."""
        self._goal_intent = value

    def snapshot(self):
        return self.token[3], None

    def goal_identity(self):
        return dict(policyGoalVersion=self.token[1], appliedGoalRequestId=self.token[2], goalIntent=self.intent)

    def goal_state(self):
        return dict(self.goal_identity(), goalError=None)

    def publish(self, **values):
        self.states.append(values)


class Policy:
    """Count reset/predict/feedback calls without importing any numerical code."""
    execution_feedback = True
    metadata = {'synthetic': True}
    def __init__(self, clock):
        self.clock, self.resets, self.predictions, self.feedback = clock, 0, [], []

    def reset(self):
        self.resets += 1

    def predict(self, image, size):
        self.predictions.append(self.clock.ns)
        return dict(parseValid=True, fullActionMs=0,
                    steps=[dict(keys=[], durationMs=50, mouseDx=0, mouseDy=0)])

    def finish_action(self, accepted):
        self.feedback.append(accepted)


class Bridge:
    """Simulate exact response/receipt shapes; reject an early normal release while X is pending."""
    def __init__(self, clock):
        self.clock = clock
        self.hello = hello()
        self.hello.update(worldReadiness=dict(version=1, requiredForInput=True), goalVersion=1, version=1)
        self.closed = False
        self.handle = SimpleNamespace(close=lambda: setattr(self, 'closed', True))
        self.epoch, self.calls, self.pending, self.applied = 1, [], None, False
        self.action_error, self.release_error, self.drop_receipts = None, None, False
        self.premature = 0

    def terminal(self):
        """Emit once after the fake horizon; this is synthetic software application only."""
        if self.pending is None or self.clock.ns/1e6 < self.pending[1]+100:
            return []
        args, started = self.pending
        self.pending, self.applied = None, True
        return [dict(requestId=args['requestId'], modelId=args['modelId'], frameId=args['frameId'],
            status='completed', reason='horizon_complete', acceptedAtMs=started, endedAtMs=started+100,
            appliedSteps=[dict(index=0, startedAtMs=started, keys=['X'], mouseDx=0, mouseDy=0)])]

    def request(self, command, **arguments):
        self.calls.append((command, copy.deepcopy(arguments), self.clock.ns))
        now = self.clock.ns/1e6
        if command == 'release':
            if self.release_error:
                raise self.release_error
            if self.pending and now < self.pending[1]+100:
                self.premature += 1
            self.epoch += 1
            return dict(type='released', serverNowMs=now, worldReadiness=dict(epoch=self.epoch, ready=False),
                        receipts=[]), b''
        if command == 'action':
            if self.action_error:
                raise self.action_error
            if arguments['modelId'] == 'navigation-climb-drop-v1':
                self.pending = (copy.deepcopy(arguments), now)
            return dict(type='accepted', requestId=arguments['requestId'], receivedAtMs=now, acceptedAtMs=now), b''
        if command == 'stop':
            return dict(type='stopped', receipts=[]), b''
        assert command == 'frame', command
        receipts = self.terminal()
        item = frame(now-10, epoch=self.epoch, motion='normal' if self.applied else 'climb')
        item.update(type='frame', width=2, height=2, sourceWidth=2, sourceHeight=2, pixelFormat='rgb24',
                    receipts=[] if self.drop_receipts else receipts, droppedReceipts=int(self.drop_receipts))
        return item, bytes(range(12))


def arguments(output='unused.json', **changes):
    """Use the real option validator with fake model paths that are never opened."""
    value = client.parse_arguments(['--model','open-p2p','--source','fake','--checkpoint','fake',
        '--resident','--rdp-session-id','3','--cuda-graph','--p2p-fast-start','--enable-input',
        '--goal-intent','ground-navigation','--navigation-climb-recovery','--input-keys','W',
        '--seconds','2','--max-input-actions','1','--output',output])
    value.navigation_progress = False
    for key, item in changes.items():
        setattr(value, key, item)
    return value


class Fixture:
    """Run the real stream coordinator against inert callbacks under one fake clock."""
    def __init__(self, control=None):
        self.clock, self.control, self.report = Clock(), control or Control(), {}
        self.bridge, self.policy = Bridge(self.clock), Policy(self.clock)
        self.collected, self.cleared, self.releases = [], [], []
        self.value = client.ClimbRecoveryStream(arguments(), self.bridge, self.policy, self.control,
            self.report, None, collect=self.collected.append, reset=self.policy.reset,
            clear=lambda: self.cleared.append(True), released=self.releases.append)

    def tick(self, stamp, motion='climb', receipts=(), dropped=0, mutate=None):
        self.clock.ns = round((stamp+10)*1e6)
        item = frame(stamp, epoch=self.bridge.epoch, motion=motion)
        if mutate:
            mutate(item)
        with patch.object(client.time, 'perf_counter_ns', self.clock.nanos):
            return self.value.tick(item, item, self.clock.ns, receipts, dropped)

    def action(self):
        self.tick(1000)
        self.tick(1060)
        self.tick(1130)
        assert self.value.helper.phase == 'await_terminal'


class ClimbStreamTests(unittest.TestCase):
    def test_confirmed_drop_starts_hybrid_retreat_on_the_next_qualified_pose(self):
        from hybrid_navigation import HybridNavigation
        from test_hybrid_navigation import capability, frame as native_frame, proposal
        f = Fixture()
        nav = HybridNavigation(capability())
        f.value.drop_resumed = nav.latch_climb_exit

        def ground(stamp):
            item = frame(stamp, epoch=f.bridge.epoch, motion='normal')
            item['navigationPose'] = native_frame(stamp, stamp)['navigationPose']
            return item

        for stamp in (700, 800, 900):
            nav.prepare(ground(stamp))
        self.assertEqual(nav.phase, 'walking')
        f.action()
        f.clock.ns = 1_270_000_000
        f.tick(1260, receipts=f.bridge.terminal())
        f.tick(1330, 'normal')
        self.assertIsNone(nav.pending_climb_exit)
        f.tick(1390, 'normal')
        nav.interrupt('climbRecovery')  # The serial loop skips prediction on the resume tick.
        self.assertEqual(nav.prepare(ground(1390)), 'waitingAfterClimbResume')
        invalid = ground(1400)
        invalid['navigationPose']['state'] = 'unavailable'
        self.assertEqual(nav.prepare(invalid), 'poseUnavailable')
        self.assertEqual(nav.phase, 'awaitingClimbPose')
        next_frame = ground(1490)
        self.assertIsNone(nav.prepare(next_frame))
        selected = nav.choose(next_frame, proposal(['W']))
        self.assertEqual((selected['owner'], selected['reason'], selected['step']['keys']),
                         ('hybrid-native', 'obstacleRetreat', ['S']))
        events = nav.drain_events()
        self.assertEqual([event['type'] for event in events], ['hybridStartVerified', 'hybridClimbRecovery'])
        event = events[-1]
        self.assertEqual((event['frameId'], event['preClimbFrameId'], event['attempt']), (1490, 900, 1))
        proof = event['climbExit']
        self.assertEqual(proof, f.report['navigationClimbRecoveryEvents'][-1]['climbExit'])
        self.assertEqual(proof['exitFrameIds'], [1330, 1390])
        self.assertEqual(proof['dropRequestId'], f.report['navigationClimbActions'][0]['requestId'])
        self.assertEqual(proof['dropFrameId'], f.report['navigationClimbActions'][0]['frameId'])
        self.assertLessEqual(proof['dropEndedAtMs'], proof['cleanupReleaseAtMs'])
        self.assertGreater(proof['resumeAtMs'], proof['cleanupReleaseAtMs'])

    def test_normal_exit_before_an_x_was_applied_cannot_start_hybrid_escape(self):
        f = Fixture()
        resumes = []
        f.value.drop_resumed = resumes.append
        f.tick(1000)
        f.tick(1060)
        f.tick(1130, 'normal')
        f.tick(1190, 'normal')
        self.assertEqual(f.value.helper.phase, 'monitoring')
        self.assertEqual(resumes, [])
        self.assertNotIn('climbExit', f.report['navigationClimbRecoveryEvents'][-1])

    """Exercise the composed driver and actual run_episode control ordering."""
    def test_changed_token_before_guarded_submit_refuses_without_unknown_transmission(self):
        for document in (dict(command='pause'), dict(command='run', goalRequestId='a'*32,
                         goalEmbedding='D:/synthetic/new-goal.json', goalIntent='ground-navigation')):
            with self.subTest(document=document):
                f = Fixture(); f.tick(1000); f.tick(1060)
                original = f.control.guarded_submit
                def guarded(expected, submit):
                    f.control._observe(document, None)
                    return original(expected, submit)
                f.control.guarded_submit = guarded
                with self.assertRaises(RuntimeError):
                    f.tick(1130)
                self.assertFalse(any(call[0] == 'action' for call in f.bridge.calls))
                self.assertNotIn('unacknowledgedRecoveryAction', f.report)
                self.assertEqual(f.report['navigationClimbFailure']['reason'],
                                 'resident_control_changed_before_submit')
                refused = [row for row in f.report['navigationClimbRecoveryEvents']
                           if row.get('kind') == 'submission_refused']
                self.assertEqual(len(refused), 1)
                self.assertFalse(refused[0]['transmissionAttempted'])

    def test_actual_guard_orders_concurrent_control_change_after_owned_submit(self):
        control, order, result, errors = Control(), [], [], []
        token = control.prediction_token()
        entered, attempted, release, changed = [threading.Event() for _ in range(4)]
        def submit():
            order.append('submit_started'); entered.set()
            if not release.wait(2):
                raise RuntimeError('Synthetic submit was not released')
            order.append('submit_returned')
            return ('synthetic-accepted', b'')
        def sender():
            try:
                result.append(control.guarded_submit(token, submit))
            except BaseException as error:
                errors.append(error)
        def monitor():
            attempted.set()
            control._observe(dict(command='pause'), None)
            order.append('pause_committed'); changed.set()
        sending = threading.Thread(target=sender, daemon=True)
        changing = threading.Thread(target=monitor, daemon=True)
        sending.start()
        try:
            self.assertTrue(entered.wait(2))
            changing.start()
            self.assertTrue(attempted.wait(2))
            self.assertTrue(control._lock.locked())
            self.assertFalse(changed.is_set())
        finally:
            release.set(); sending.join(2)
            if changing.ident is not None:
                changing.join(2)
        self.assertFalse(sending.is_alive() or changing.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result, [(True, ('synthetic-accepted', b''))])
        self.assertEqual(order, ['submit_started', 'submit_returned', 'pause_committed'])
        self.assertEqual(control.prediction_token()[3], 'pause')

    def test_actual_guard_releases_plain_lock_on_submit_exception(self):
        control, expected = Control(), EOFError('synthetic bridge EOF')
        def submit():
            raise expected
        with self.assertRaises(EOFError) as raised:
            control.guarded_submit(control.prediction_token(), submit)
        self.assertIs(raised.exception, expected)
        self.assertTrue(control._lock.acquire(blocking=False))
        control._lock.release()
        control._observe(dict(command='pause'), None)
        self.assertEqual(control.guarded_submit(control.prediction_token(),
            lambda: self.fail('Paused token must not submit')), (False, None))

    def test_options_require_resident_p2p_input_feedback_and_context_off(self):
        value = arguments()
        self.assertEqual(value.input_keys, 'W')
        for key, bad in [('resident',False),('model','gamescaling'),('enable_input',False),
                         ('p2p_fast_start',False),('p2p_execution_feedback',False),('execution_context','record')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                client.validate_navigation_climb_options(arguments(**{key:bad}))
        client.validate_navigation_climb_options(SimpleNamespace(navigation_climb_recovery=False))

    def test_success_waits_for_terminal_and_never_predicts_or_commits_recovery(self):
        f = Fixture(); f.action()
        self.assertEqual(f.policy.resets, 1)
        f.tick(1190)
        self.assertEqual(len(f.releases), 1)
        f.clock.ns = 1_270_000_000
        receipt = f.bridge.terminal()
        f.tick(1260, receipts=receipt)
        self.assertEqual(len(f.releases), 2)
        self.assertEqual(f.policy.resets, 2)
        f.tick(1330, 'normal'); f.tick(1390, 'normal')
        self.assertFalse(f.value.helper.blocks_model)
        self.assertEqual(f.policy.predictions, [])
        self.assertEqual(f.policy.feedback, [])
        self.assertEqual(f.bridge.premature, 0)
        self.assertEqual(f.report['navigationClimbActions'][0]['arguments']['steps'][0]['keys'], ['X'])
        self.assertFalse(f.report['navigationClimbActions'][0]['modelHistoryCommitted'])
        self.assertNotIn('unacknowledgedRecoveryAction', f.report)
        kinds = [row.get('kind') for row in f.report['navigationClimbRecoveryEvents']]
        self.assertEqual(kinds.count('release_returned'), 2)
        self.assertEqual(kinds.count('history_reset_completed'), 2)

    def test_disproved_initial_hint_does_not_bind_the_next_goal_to_an_old_token(self):
        f = Fixture(); f.tick(1000); f.tick(1060, 'normal')
        self.assertFalse(f.value.helper.blocks_model)
        f.control.token = (1,1,'new-goal','run')
        f.tick(1120); f.tick(1180)
        self.assertEqual(f.value.helper.phase, 'await_drop_frame')
        self.assertEqual(f.value.token, f.control.token)

    def test_known_rejection_retains_reply_without_claiming_unknown_admission(self):
        f = Fixture(); f.tick(1000); f.tick(1060)
        original = f.bridge.request
        def request(command, **arguments):
            if command == 'action':
                return dict(type='rejected', requestId=arguments['requestId'], reason='start_deadline_expired'), b''
            return original(command, **arguments)
        f.bridge.request = request
        with self.assertRaises(RuntimeError):
            f.tick(1130)
        self.assertEqual(f.report['navigationClimbFailure']['reason'], 'drop_rejected')
        self.assertNotIn('unacknowledgedRecoveryAction', f.report)
        self.assertEqual(f.report['navigationClimbActions'][0]['acceptance']['type'], 'rejected')

    def test_unretired_reader_skips_another_pipe_request_and_keeps_cleanup_uncertain(self):
        f = Fixture(); f.action()
        before = len(f.bridge.calls)
        error = f.value.terminate('reader_not_retired', cleanup_allowed=False)
        f.value.terminate('second_cleanup_must_not_retry')
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(len(f.bridge.calls), before)
        self.assertFalse(f.report['navigationClimbFailureCleanup']['released'])
        self.assertEqual(f.report['navigationClimbFailure']['reason'], 'reader_not_retired')

    def test_stale_frame_after_release_cannot_dispatch_x(self):
        f = Fixture(); f.tick(1000); f.tick(1060)
        f.tick(1130, mutate=lambda v:v.update(serverNowMs=v['serverNowMs']+150))
        self.assertEqual(f.value.helper.phase, 'await_drop_frame')
        self.assertFalse(any(c[0] == 'action' for c in f.bridge.calls))

    def test_pause_and_goal_change_interrupt_without_new_x_and_cannot_reconnect(self):
        for token in [(1,0,None,'pause'),(1,1,'new-goal','run')]:
            f = Fixture(); f.tick(1000); f.control.token = token
            with self.subTest(token=token), self.assertRaises(RuntimeError):
                f.tick(1060)
            self.assertFalse(any(c[0]=='action' for c in f.bridge.calls))
            with self.assertRaisesRegex(RuntimeError, 'unresolved'):
                Fixture(control=f.control)

    def test_lost_receipt_holds_and_preserves_single_cleanup(self):
        f = Fixture(); f.action()
        with self.assertRaises(RuntimeError):
            f.tick(1200, dropped=1)
        count = len(f.bridge.calls)
        f.value.terminate('later_failure')
        self.assertEqual(len(f.bridge.calls), count)
        self.assertEqual(f.report['navigationClimbFailure']['reason'], 'receipt_loss')

    def test_disconnect_and_cleanup_failure_are_terminal_separate_and_unreplayed(self):
        f = Fixture(); f.tick(1000); f.tick(1060)
        f.bridge.action_error = EOFError('synthetic unknown X write')
        f.bridge.release_error = OSError('synthetic cleanup failed')
        with self.assertRaises(RuntimeError):
            f.tick(1130)
        self.assertEqual(f.report['navigationClimbFailure']['errorType'], 'EOFError')
        self.assertEqual(f.report['navigationClimbFailureCleanup']['errorType'], 'OSError')
        self.assertIn('unacknowledgedRecoveryAction', f.report)
        self.assertEqual(sum(c[0]=='action' for c in f.bridge.calls), 1)
        self.assertEqual(f.policy.feedback, [])

    def test_clean_reconnect_carries_budget_and_cooldown(self):
        f = Fixture(); f.action(); f.clock.ns = 1_270_000_000
        f.tick(1260, receipts=f.bridge.terminal()); f.tick(1330,'normal'); f.tick(1390,'normal')
        following = Fixture(control=f.control)
        self.assertEqual(following.value.helper.attempts, 1)
        self.assertEqual(following.value.helper.cooldown_until_ns, 6_070_000_000)
        following.tick(1500); following.tick(1560)
        self.assertFalse(any(c[0]=='release' for c in following.bridge.calls))

    def test_replaced_handle_never_receives_cleanup_release(self):
        f = Fixture(); f.tick(1000)
        f.bridge.handle = object()
        with self.assertRaises(RuntimeError):
            f.tick(1060)
        self.assertEqual(f.bridge.calls, [])
        self.assertFalse(f.report['navigationClimbFailureCleanup']['released'])

    def test_terminal_in_admission_reply_is_collected_after_recovery_action_record(self):
        f = Fixture(); events, pending = [], []
        f.value.recorder = SimpleNamespace(event=lambda row:events.append(row['type']))
        def collect(reply):
            if reply.get('receipts'):
                events.append('terminal_batch')
                pending.extend(reply['receipts'])
        f.value.collect = collect
        original = f.bridge.request
        def request(command, **arguments):
            reply, payload = original(command, **arguments)
            if command == 'action':
                f.clock.ns += 100_000_000
                reply['receipts'] = f.bridge.terminal()
            return reply, payload
        f.bridge.request = request
        f.action()
        self.assertLess(events.index('navigationClimbAction'), events.index('terminal_batch'))
        self.assertEqual(f.value.helper.phase, 'await_terminal')
        f.tick(1250, receipts=pending)
        self.assertEqual(f.value.helper.phase, 'await_exit')
        self.assertEqual(f.bridge.premature, 0)

    def test_unresolved_reconnect_fails_before_new_archive_worker_construction(self):
        f = Fixture(); f.tick(1000)
        following = Bridge(f.clock)
        args = arguments(); args.lease_output = 'unused-lease.json'
        with patch.object(client, 'Bridge', return_value=following), \
                patch.dict(sys.modules, {'PIL':SimpleNamespace(Image=object())}), \
                patch('stream_segments.StreamSegments') as archive:
            with self.assertRaisesRegex(RuntimeError, 'unresolved'):
                client.run_episode(args, f.policy, f.control)
        archive.assert_not_called()
        self.assertTrue(following.closed)

    def episode(self, folder, *, stop_after_action=False, disconnect=False, enabled=True):
        """Call actual run_episode; only transport, clock, producer and pixels are inert substitutions."""
        clock, control = Clock(), Control()
        bridge, policy = Bridge(clock), Policy(clock)
        args = arguments(str(Path(folder)/'report.json'))
        args.navigation_climb_recovery = enabled
        class NoProducer:
            def __init__(self, *args, **kwargs): pass
            def start(self): pass
            def join(self, **kwargs): pass
            def is_alive(self): return False
        def sleep(deadline, stopped):
            clock.sleep_until(deadline, stopped)
            if stop_after_action and bridge.pending:
                control.token = (1,0,None,'pause')
            if disconnect and bridge.pending:
                raise EOFError('synthetic receive disconnect')
            return not stopped.is_set()
        with ExitStack() as stack:
            stack.enter_context(patch.object(client,'Bridge',return_value=bridge))
            stack.enter_context(patch.object(client.threading,'Thread',NoProducer))
            stack.enter_context(patch.object(client.time,'perf_counter',clock.seconds))
            stack.enter_context(patch.object(client.time,'perf_counter_ns',clock.nanos))
            stack.enter_context(patch.object(client,'sleep_until',sleep))
            stack.enter_context(patch.dict(sys.modules, {'PIL':SimpleNamespace(Image=SimpleNamespace(frombytes=lambda *a:a[2])),
                'resident_runtime':SimpleNamespace(apply_pending_goal=lambda *a:None)}))
            stack.enter_context(redirect_stdout(io.StringIO()))
            if stop_after_action or disconnect:
                with self.assertRaises(RuntimeError):
                    client.run_episode(args, policy, control)
            else:
                self.assertEqual(client.run_episode(args, policy, control), 0)
        return json.loads(Path(args.output).read_text()), bridge, policy, control

    def test_real_episode_release_epochs_do_not_cancel_pending_x(self):
        with tempfile.TemporaryDirectory() as folder:
            report, bridge, policy, _ = self.episode(folder)
        self.assertEqual(bridge.premature, 0)
        self.assertEqual(sum(c[0]=='release' for c in bridge.calls), 2)
        self.assertEqual(len(report['navigationClimbActions']), 1)
        self.assertEqual(len(report['decisions']), 1)
        self.assertEqual(report['acceptedInputActions'], 1)
        self.assertEqual(len(policy.predictions), 1)
        self.assertEqual(policy.feedback, [True])
        self.assertGreater(policy.predictions[0], 1_500_000_000)
        self.assertEqual(policy.resets, 2)
        self.assertTrue(bridge.closed)

    def test_real_episode_pause_while_x_pending_is_terminal_and_records_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            report, bridge, policy, control = self.episode(folder, stop_after_action=True)
        self.assertEqual(policy.predictions, [])
        self.assertTrue(control.navigation_climb_recovery.blocks_model)
        self.assertEqual(report['navigationClimbFailure']['reason'], 'resident_control_changed')
        self.assertTrue(report['navigationClimbFailureCleanup']['released'])
        self.assertTrue(bridge.closed)

    def test_real_episode_disconnect_is_runtimeerror_after_stop_and_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            report, bridge, policy, _ = self.episode(folder, disconnect=True)
        self.assertEqual(report['navigationClimbFailure']['errorType'], 'EOFError')
        self.assertEqual(policy.feedback, [])
        self.assertTrue(any(c[0]=='stop' for c in bridge.calls))
        self.assertTrue(bridge.closed)

    def test_flag_omitted_preserves_ordinary_model_path_without_recovery_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            report, bridge, policy, _ = self.episode(folder, enabled=False)
        self.assertNotIn('navigationClimbActions', report)
        self.assertNotIn('navigationClimbRecoveryEvents', report)
        self.assertEqual(len(policy.predictions), 1)
        self.assertEqual(policy.feedback, [True])
        self.assertEqual(policy.resets, 0)
        self.assertFalse(any(c[0]=='release' for c in bridge.calls))

    def test_rollover_transfers_lists_and_joins_x_separately_from_model_proposals(self):
        f = Fixture(); f.action()
        archive = object.__new__(StreamSegments)
        archive.lock, archive.number = threading.RLock(), 1
        archive.pending, archive.headers, archive.early_receipts = OrderedDict(), OrderedDict(), deque(maxlen=256)
        archive.recorder, archive.record_parent, archive.retiring, archive._error = None, None, None, None
        archive.report_parent, archive.started, archive.submitted = Path('unused-reports'), 0, 0
        archive.wake, archive.args = threading.Event(), SimpleNamespace(segment_seconds=1)
        archive.counter_base = dict.fromkeys(StreamSegments.COUNTERS, 0)
        archive.quality_base = {'usableFrames':0}
        archive.context = archive._context(None)
        row = f.report['navigationClimbActions'][0]
        archive.put(frame(1130,epoch=2), b'')
        archive.event(row)
        report = dict(f.report, hello=f.bridge.hello, captureQuality={'check':'test','usableFrames':1},
                      **dict.fromkeys(StreamSegments.COUNTERS, 0))
        original = report['navigationClimbRecoveryEvents']
        archive.rotate(report, 1)
        self.assertIs(archive.retiring[0]['navigationClimbRecoveryEvents'], original)
        self.assertEqual(report['navigationClimbRecoveryEvents'], [])
        self.assertEqual(archive.context['pendingProposals'], [])
        self.assertEqual(archive.context['pendingRecoveryActions'][0]['requestId'], row['requestId'])
        self.assertFalse(archive.context['pendingRecoveryActions'][0]['modelHistoryCommitted'])
        f.clock.ns = 1_270_000_000
        archive.event(f.bridge.terminal()[0])
        self.assertEqual(archive.pending, {})



    def test_same_incident_second_x_waits_for_cleanup_then_resumes_only_after_exit(self):
        """Actual coordinator keeps the model blocked through both synthetic X receipts."""
        f = Fixture(); f.action(); f.clock.ns = 1_270_000_000
        f.tick(1260, receipts=f.bridge.terminal())
        self.assertEqual(f.value.helper.phase, 'await_exit')
        self.assertEqual(f.policy.resets, 2)
        f.tick(1950); f.tick(2009)
        self.assertEqual(len(f.releases), 2)
        f.tick(2010)  # Exactly 750 ms after successful cleanup/reset at 1270 ms.
        self.assertEqual(len(f.releases), 3)
        self.assertEqual(f.value.helper.attempts, 2)
        self.assertEqual(f.value.helper.phase, 'await_drop_frame')
        f.tick(2080)
        self.assertEqual(len(f.report['navigationClimbActions']), 2)
        self.assertEqual(f.value.helper.phase, 'await_terminal')
        f.clock.ns = 2_210_000_000
        f.tick(2200, receipts=f.bridge.terminal())
        self.assertEqual(len(f.releases), 4)
        self.assertEqual(f.policy.resets, 4)
        f.tick(2280, 'normal'); f.tick(2340, 'normal')
        self.assertFalse(f.value.helper.blocks_model)
        self.assertEqual([e['attempt'] for e in f.report['navigationClimbRecoveryEvents']
                          if e.get('kind') == 'resume'], [2])
        self.assertEqual(f.policy.predictions, [])
        self.assertEqual(f.policy.feedback, [])
        self.assertEqual(f.bridge.premature, 0)
        self.assertEqual(f.value.helper.cooldown_until_ns, 7_020_000_000)
        actions = f.report['navigationClimbActions']
        self.assertNotEqual(actions[0]['requestId'], actions[1]['requestId'])
        self.assertTrue(all(not a['modelHistoryCommitted'] for a in actions))

    def test_missing_terminal_never_arms_short_retry(self):
        """No second write occurs while the first action's terminal is still unknown."""
        f = Fixture(); f.action(); f.tick(1950); f.tick(2020)
        self.assertEqual(f.value.helper.phase, 'await_terminal')
        self.assertEqual(len(f.report['navigationClimbActions']), 1)
        self.assertEqual(len(f.releases), 1)
        with self.assertRaises(RuntimeError):
            f.tick(2190)
        self.assertEqual(f.value.helper.attempts, 1)
        self.assertEqual(len(f.report['navigationClimbActions']), 1)
        self.assertEqual(f.policy.predictions, [])

    def test_second_cleanup_wait_cannot_create_a_third_x(self):
        """Continued climb after two completed attempts ends in the existing hold path."""
        f = Fixture(); f.action(); f.clock.ns = 1_270_000_000
        f.tick(1260, receipts=f.bridge.terminal()); f.tick(1950); f.tick(2010); f.tick(2080)
        f.clock.ns = 2_210_000_000
        f.tick(2200, receipts=f.bridge.terminal())
        f.tick(2890)
        with self.assertRaises(RuntimeError):
            f.tick(2950)
        self.assertEqual(f.value.helper.failure, 'attempt_budget_exhausted')
        self.assertEqual(f.value.helper.attempts, 2)
        self.assertEqual(len(f.report['navigationClimbActions']), 2)
        self.assertTrue(f.value.helper.blocks_model)
        self.assertEqual(f.policy.predictions, [])
        self.assertEqual(f.policy.feedback, [])
        self.assertEqual(f.bridge.premature, 0)

    def test_normal_exit_uses_original_cooldown_for_later_stream_incident(self):
        """The stream's successful exit never converts the next incident to a short retry."""
        f = Fixture(); f.action(); f.clock.ns = 1_270_000_000
        f.tick(1260, receipts=f.bridge.terminal()); f.tick(1330, 'normal'); f.tick(1390, 'normal')
        f.tick(1950); f.tick(2010)
        self.assertEqual(f.value.helper.phase, 'monitoring')
        self.assertEqual(f.value.helper.attempts, 1)
        self.assertEqual(len(f.releases), 2)
        f.tick(5990); f.tick(6060)
        self.assertEqual(f.value.helper.attempts, 2)
        self.assertEqual(len(f.releases), 3)

if __name__ == '__main__':
    unittest.main()
