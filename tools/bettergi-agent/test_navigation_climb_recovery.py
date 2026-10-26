"""Inert clock/frame/receipt tests; no client, capture, model or native imports."""

import copy
import unittest

from navigation_climb_recovery import NavigationClimbRecovery, ORIGIN, MOTION_METHOD


def context(**changes):
    """Represent the exact caller-owned lease and resident control token."""
    value = dict(sessionId='session', ownerEpoch='owner', controlToken=(0, 0, None, 'run'),
                 goalIntent='ground-navigation', inputEnabled=True, xAuthorized=True, standardChannel=True)
    value.update(changes)
    return value


def hello():
    """A synthetic standard channel with independently advertised X permission."""
    return dict(sessionId='session', ownerEpoch='owner', inputEnabled=True, allowedKeys=['W', 'X'],
                supportsRelease=True, supportsStartBeforeMs=True,
                motionEvidence=dict(version=1, method=MOTION_METHOD, sameFrame=True, normalIsGroundedProof=False))


def policy(**changes):
    """Enable recovery only inside an inert fixture."""
    args = dict(enabled=True, input_requested=True, x_authorized=True)
    args.update(changes)
    return NavigationClimbRecovery(hello(), **args)


def frame(stamp, *, epoch=1, motion='climb', capture='a'*32):
    """Construct distinct source stamps with known earlier-of-reported/acquired freshness."""
    source = dict(captureEpoch=capture, timestamp100ns=int(stamp*10000), capturedAtMs=stamp,
                  acquiredAtMs=stamp+1, freshnessAtMs=stamp, freshnessClockKind='reported_compositor_qpc')
    ready = dict(ready=True, epoch=epoch, sourceFrameId=int(stamp), sourceCapturedAtMs=stamp+1)
    return dict(frameId=int(stamp), capturedAtMs=stamp+1, serverNowMs=stamp+10,
                clientReceivedNs=int((stamp+10)*1e6), transportRoundTripMs=1, frameQuality='usable',
                sourceFrame=source, inputAvailable=True, frameWorldReadiness=ready,
                worldReadiness=copy.deepcopy(ready), motionEvidence=dict(status=motion, method=MOTION_METHOD,
                spaceKeyMatched=motion in ('climb', 'fly'), xKeyMatched=motion == 'climb'))


def observe(value, pixels, *, ctx=None, now=None, current=None):
    """Advance fake time without sleeping or obtaining another image."""
    received = pixels['clientReceivedNs']
    return value.observe(pixels, current or pixels, ctx or context(), status_received_ns=received,
                         now_ns=received if now is None else now)


def ready(value):
    """Complete first confirmation, actual-release acknowledgment and reset acknowledgment."""
    assert observe(value, frame(1000)) is None
    assert observe(value, frame(1060))['kind'] == 'release'
    assert value.released(dict(type='released', serverNowMs=1100, worldReadiness=dict(epoch=2)),
                          context(), now_ns=1_110_000_000)['kind'] == 'reset_history'
    value.history_reset_done(context(), now_ns=1_111_000_000)
    pixels = frame(1160, epoch=2)
    assert observe(value, pixels)['kind'] == 'drop_ready'
    return pixels


def claimed(value):
    """Reserve but never write the exact one-step action."""
    pixels = ready(value)
    intent = value.claim_action(pixels, pixels, context(), 'drop-1',
                                status_received_ns=pixels['clientReceivedNs'], now_ns=1_171_000_000)
    return intent


def admitted(value):
    """Join a fake accepted response, still without an applied action."""
    claimed(value)
    value.admitted(dict(type='accepted', requestId='drop-1', receivedAtMs=1175, acceptedAtMs=1180),
                   context(), now_ns=1_181_000_000)


def terminal():
    """A standard controller terminal reports software dispatch, not physical execution."""
    return dict(requestId='drop-1', modelId=ORIGIN, frameId=1160, status='completed', reason='horizon_complete',
                acceptedAtMs=1180, endedAtMs=1285,
                appliedSteps=[dict(index=0, startedAtMs=1182, keys=['X'], mouseDx=0, mouseDy=0)])


def awaiting_exit(value):
    """Close one fake action and both software cleanup/reset callbacks."""
    admitted(value)
    assert value.receipt(terminal(), context(), now_ns=1_290_000_000)['kind'] == 'release'
    value.released(dict(type='released', serverNowMs=1300, worldReadiness=dict(epoch=3)),
                   context(), now_ns=1_310_000_000)
    value.history_reset_done(context(), now_ns=1_311_000_000)


class NavigationClimbRecoveryTests(unittest.TestCase):
    """Exercise real policy transitions using only fabricated JSON and clocks."""

    def test_default_off_does_not_block_or_emit(self):
        value = NavigationClimbRecovery({})
        self.assertIsNone(observe(value, frame(1000)))
        self.assertFalse(value.blocks_model)
        self.assertEqual(value.attempts, 0)

    def test_opt_in_requires_both_input_permissions_and_native_capability(self):
        for option in ('input_requested', 'x_authorized'):
            with self.subTest(option=option), self.assertRaises(ValueError):
                policy(**{option: False})
        for key, bad in [('inputEnabled', False), ('allowedKeys', ['W']), ('supportsRelease', False),
                         ('supportsStartBeforeMs', False), ('ownerEpoch', '')]:
            h = hello(); h[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                NavigationClimbRecovery(h, enabled=True, input_requested=True, x_authorized=True)
        h = hello(); h['motionEvidence']['normalIsGroundedProof'] = True
        with self.assertRaises(ValueError):
            NavigationClimbRecovery(h, enabled=True, input_requested=True, x_authorized=True)

    def test_boolean_and_attempt_options_are_strict(self):
        for changes in ({'enabled': 1}, {'input_requested': 'yes'}, {'x_authorized': 1},
                        {'max_attempts': True}, {'max_attempts': 0}, {'max_attempts': 3},
                        {'initial_attempts': True}, {'initial_attempts': -1}, {'initial_attempts': 3},
                        {'max_attempts': 1, 'initial_attempts': 2},
                        {'initial_cooldown_until_ns': True}, {'initial_cooldown_until_ns': -1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                policy(**changes)

    def test_stationary_or_paused_or_queued_context_never_starts(self):
        for changes in ({'goalIntent': 'stationary'}, {'controlToken': (0, 0, None, 'pause')},
                        {'inputEnabled': False}, {'xAuthorized': False}, {'standardChannel': False}):
            value = policy()
            for stamp in (1000, 1060):
                self.assertIsNone(observe(value, frame(stamp), ctx=context(**changes)))
            self.assertEqual(value.attempts, 0)

    def test_30hz_confirmations_accumulate_from_first_not_last_frame(self):
        value = policy()
        self.assertIsNone(observe(value, frame(1000)))
        self.assertTrue(value.blocks_model)
        self.assertIsNone(observe(value, frame(1033)))
        self.assertEqual(observe(value, frame(1067))['kind'], 'release')
        self.assertEqual(value.attempts, 1)
        self.assertIsNone(observe(value, frame(1100)))

    def test_repeated_source_or_frame_does_not_confirm(self):
        for mutation in ('source', 'frame'):
            value = policy(); observe(value, frame(1000))
            f = frame(1060)
            if mutation == 'source':
                f['sourceFrame']['timestamp100ns'] = 1000*10000
            else:
                f['frameId'] = f['frameWorldReadiness']['sourceFrameId'] = 1000
            self.assertIsNone(observe(value, f))
            self.assertEqual(value.attempts, 0)

    def test_gaps_epoch_changes_and_goal_changes_restart_confirmation(self):
        for f, ctx in [(frame(1300), context()), (frame(1060, epoch=2), context()),
                       (frame(1060), context(controlToken=(0, 1, 'new', 'run')))]:
            value = policy(); observe(value, frame(1000))
            self.assertIsNone(observe(value, f, ctx=ctx))
            self.assertEqual(value.attempts, 0)

    def test_unready_blank_unknown_fly_and_bad_hint_do_not_confirm(self):
        for change in ('world', 'payload', 'blank', 'unknown', 'fly', 'hint', 'frameJoin'):
            value = policy(); f = frame(1000)
            if change == 'world': f['worldReadiness']['ready'] = False
            if change == 'payload': f['frameWorldReadiness']['ready'] = False
            if change == 'blank': f['frameQuality'] = 'allBlack'
            if change in ('unknown', 'fly'): f['motionEvidence']['status'] = change
            if change == 'hint': f['motionEvidence']['xKeyMatched'] = False
            if change == 'frameJoin': f['frameWorldReadiness']['sourceFrameId'] += 1
            self.assertIsNone(observe(value, f))
            self.assertFalse(value.blocks_model)

    def test_strict_150ms_source_age_and_current_status_age(self):
        value = policy(); f = frame(1000)
        self.assertIsNone(observe(value, f, now=1_149_000_000))  # 149 + 1ms RTT ==150.
        self.assertFalse(value.blocks_model)
        f = frame(1200)
        self.assertIsNone(value.observe(f, f, context(), now_ns=1_210_000_000, status_received_ns=900_000_000))
        self.assertFalse(value.blocks_model)

    def test_future_receipt_clock_and_false_source_anchor_rejected(self):
        for change in ('receipt', 'anchor'):
            value = policy(); f = frame(1000)
            if change == 'receipt': f['clientReceivedNs'] += 1
            else: f['sourceFrame']['freshnessAtMs'] += 1
            self.assertIsNone(observe(value, f, now=1_010_000_000))
            self.assertFalse(value.blocks_model)

    def test_release_needs_new_epoch_and_post_source_ack(self):
        for stamp, epoch in [(999, 2), (1100, 1), (1100, True)]:
            value = policy(); observe(value, frame(1000)); observe(value, frame(1060))
            result = value.released(dict(type='released', serverNowMs=stamp, worldReadiness=dict(epoch=epoch)),
                                    context(), now_ns=1_110_000_000)
            self.assertEqual(result['kind'], 'hold')
        value = policy(); observe(value, frame(1000)); observe(value, frame(1060))
        result = value.released(dict(type='released', serverNowMs=1100, worldReadiness=None),
                                context(), now_ns=1_110_000_000)
        self.assertEqual(result['reason'], 'invalid_release_ack')
        self.assertTrue(value.blocks_model)

    def test_reset_ack_and_post_release_settling_are_required(self):
        value = policy(); observe(value, frame(1000)); observe(value, frame(1060))
        value.released(dict(type='released', serverNowMs=1100, worldReadiness=dict(epoch=2)), context(), now_ns=1_110_000_000)
        self.assertIsNone(observe(value, frame(1160, epoch=2)))
        value.history_reset_done(context(), now_ns=1_171_000_000)
        self.assertIsNone(observe(value, frame(1159, epoch=2), now=1_172_000_000))
        self.assertEqual(observe(value, frame(1170, epoch=2))['kind'], 'drop_ready')

    def test_claimed_wire_action_is_distinct_bounded_and_detached(self):
        value = policy(); intent = claimed(value)
        args = intent['arguments']
        self.assertEqual(args['modelId'], ORIGIN)
        self.assertEqual(args['startBeforeMs'], 1310)
        self.assertEqual(args['expiresAtMs'], 1410)
        self.assertEqual(args['steps'], [dict(keys=['X'], durationMs=100, mouseDx=0, mouseDy=0)])
        args['steps'][0]['keys'].append('W')
        self.assertEqual(value._request['steps'][0]['keys'], ['X'])
        self.assertTrue(value.blocks_model)

    def test_claim_rechecks_freshness_before_write(self):
        value = policy(); f = ready(value)
        result = value.claim_action(f, f, context(), 'drop-1', status_received_ns=f['clientReceivedNs'], now_ns=1_309_000_000)
        self.assertEqual(result['reason'], 'drop_prewrite_validation_failed')
        self.assertIsNone(value._request)

    def test_no_duplicate_claim_or_prediction_while_inflight(self):
        value = policy(); claimed(value)
        self.assertIsNone(observe(value, frame(1200, epoch=2)))
        f = frame(1210, epoch=2)
        self.assertEqual(value.claim_action(f, f, context(), 'drop-2', status_received_ns=f['clientReceivedNs'],
                                           now_ns=1_220_000_000)['kind'], 'hold')
        self.assertTrue(value.blocks_model)

    def test_known_rejection_is_distinct_from_unknown_and_never_retries(self):
        for reply, reason in [(dict(type='rejected', requestId='drop-1'), 'drop_rejected'),
                              (dict(type='accepted', requestId='other'), 'drop_rejected_or_unknown')]:
            value = policy(); claimed(value)
            self.assertEqual(value.admitted(reply, context(), now_ns=1_180_000_000)['reason'], reason)
            self.assertEqual(value.attempts, 1)
            self.assertTrue(value.blocks_model)

    def test_waits_for_terminal_without_early_release(self):
        value = policy(); admitted(value)
        self.assertIsNone(observe(value, frame(1220, epoch=2)))
        self.assertEqual(value.phase, 'await_terminal')
        unrelated = terminal(); unrelated['requestId'] = 'model-proposal'
        self.assertIsNone(value.receipt(unrelated, context(), now_ns=1_250_000_000))
        self.assertEqual(value.phase, 'await_terminal')
        self.assertEqual(value.receipt(terminal(), context(), now_ns=1_290_000_000)['kind'], 'release')
        self.assertEqual(value.phase, 'await_cleanup')

    def test_terminal_exact_identity_status_application_and_deadline(self):
        for change in ('model', 'frame', 'cancelled', 'keys', 'mouse', 'lateStart', 'extra', 'boolIndex'):
            value = policy(); admitted(value); t = terminal()
            if change == 'model': t['modelId'] = 'open-p2p'
            if change == 'frame': t['frameId'] += 1
            if change == 'cancelled': t['status'] = 'cancelled'
            if change == 'keys': t['appliedSteps'][0]['keys'] = ['W']
            if change == 'mouse': t['appliedSteps'][0]['mouseDx'] = 1
            if change == 'lateStart': t['appliedSteps'][0]['startedAtMs'] = 1310
            if change == 'extra': t['opaque'] = 'not retained'
            if change == 'boolIndex': t['appliedSteps'][0]['index'] = False
            with self.subTest(change=change):
                self.assertEqual(value.receipt(t, context(), now_ns=1_290_000_000)['kind'], 'hold')

    def test_identical_terminal_duplicate_is_idempotent_conflict_quarantines(self):
        value = policy(); admitted(value); t = terminal()
        value.receipt(t, context(), now_ns=1_290_000_000)
        self.assertIsNone(value.receipt(copy.deepcopy(t), context(), now_ns=1_291_000_000))
        t['endedAtMs'] += 1
        self.assertEqual(value.receipt(t, context(), now_ns=1_292_000_000)['reason'], 'conflicting_recovery_receipt')

    def test_receipt_loss_never_resumes(self):
        value = policy(); admitted(value)
        self.assertEqual(value.receipt(terminal(), context(), now_ns=1_290_000_000, dropped_receipts=1)['reason'], 'receipt_loss')
        self.assertTrue(value.blocks_model)

    def test_exit_requires_two_fresh_post_cleanup_normals_not_ground_proof(self):
        value = policy(); awaiting_exit(value)
        self.assertIsNone(observe(value, frame(1359, epoch=3, motion='normal')))
        self.assertIsNone(observe(value, frame(1360, epoch=3, motion='normal')))
        self.assertTrue(value.blocks_model)
        result = observe(value, frame(1420, epoch=3, motion='normal'))
        self.assertEqual(result['meaning'], 'fresh_normal_hints_not_grounded_proof')
        self.assertFalse(value.blocks_model)

    def test_still_climbing_retries_only_after_cleanup_wait_and_new_confirmation(self):
        """An already confirmed pair cannot bypass the exact 750 ms lower bound."""
        for offset, expected in ((749_999_999, None), (750_000_000, 'release')):
            with self.subTest(offset=offset):
                value = policy(); awaiting_exit(value)
                self.assertIsNone(observe(value, frame(1980, epoch=3)))
                result = observe(value, frame(2040, epoch=3), now=1_311_000_000+offset)
                self.assertEqual(None if result is None else result['kind'], expected)
                self.assertEqual(value.attempts, 1 if expected is None else 2)
                self.assertTrue(value.blocks_model)

    def test_exhaustion_holds_instead_of_resuming_climb(self):
        value = policy(max_attempts=1); awaiting_exit(value)
        observe(value, frame(6100, epoch=3))
        result = observe(value, frame(6160, epoch=3))
        self.assertEqual(result['reason'], 'attempt_budget_exhausted')
        self.assertTrue(value.blocks_model)

    def test_changed_control_session_permission_and_source_quarantine(self):
        for changes in ({'sessionId': 'replacement'}, {'ownerEpoch': 'replacement'},
                        {'controlToken': (1, 0, None, 'pause')}, {'goalIntent': 'stationary'},
                        {'xAuthorized': False}, {'standardChannel': False}):
            value = policy(); admitted(value)
            self.assertEqual(observe(value, frame(1220, epoch=2), ctx=context(**changes))['kind'], 'hold')
            self.assertTrue(value.blocks_model)
        value = policy(); ready(value)
        self.assertEqual(observe(value, frame(1220, epoch=2, capture='b'*32))['reason'], 'capture_epoch_changed')

    def test_timeout_cleanup_once_and_first_failure_preserved(self):
        value = policy(); admitted(value)
        result = observe(value, frame(2190, epoch=2))
        self.assertTrue(result['cleanupRequired'])
        self.assertIn('await_terminal', result['reason'])
        second = value.fail('later_cleanup_failure')
        self.assertFalse(second['cleanupRequired'])
        self.assertEqual(second['reason'], result['reason'])
        self.assertFalse(observe(value, frame(2200, epoch=2))['cleanupRequired'])

    def test_reset_failure_and_unknown_dispatch_stay_latched(self):
        for phase in ('reset', 'dispatch'):
            value = policy()
            if phase == 'reset':
                observe(value, frame(1000)); observe(value, frame(1060))
            else:
                claimed(value)
            self.assertTrue(value.fail(phase + '_unknown')['cleanupRequired'])
            self.assertTrue(value.blocks_model)
            self.assertIsNotNone(value.failure)

    def test_clock_regression_quarantines_even_before_input(self):
        value = policy(); observe(value, frame(1000))
        self.assertEqual(observe(value, frame(1001), now=1_000_000_000)['reason'], 'client_clock_regression')
        self.assertEqual(observe(policy(), frame(1000), now=-1)['reason'], 'client_clock_regression')

    def test_lost_climb_confirmation_evidence_holds_instead_of_resuming(self):
        value = policy(); observe(value, frame(1000))
        result = observe(value, frame(1060, motion='unknown'))
        self.assertEqual(result['reason'], 'climb_confirmation_evidence_lost')
        self.assertTrue(value.blocks_model)

    def test_reconnect_inherits_attempt_count_without_rearming_exhausted_budget(self):
        value = policy(initial_attempts=1)
        awaiting_exit(value)
        self.assertEqual(value.attempts, 2)
        self.assertEqual(value.cooldown_until_ns, 6_070_000_000)
        observe(value, frame(1360, epoch=3, motion='normal'))
        observe(value, frame(1420, epoch=3, motion='normal'))
        self.assertFalse(value.blocks_model)
        following = policy(initial_attempts=value.attempts)
        observe(following, frame(7000))
        self.assertEqual(observe(following, frame(7060))['reason'], 'attempt_budget_exhausted')
        self.assertEqual(following.attempts, 2)
        self.assertTrue(following.blocks_model)

    def test_clean_reconnect_preserves_remaining_monotonic_cooldown(self):
        value = policy(initial_attempts=1, initial_cooldown_until_ns=6_070_000_000)
        observe(value, frame(5900))
        self.assertIsNone(observe(value, frame(5960)))
        self.assertTrue(value.blocks_model)
        self.assertEqual(value.attempts, 1)
        self.assertEqual(observe(value, frame(6060))['kind'], 'release')
        self.assertEqual(value.attempts, 2)



    def test_retry_clock_begins_at_delayed_cleanup_reset_not_terminal(self):
        """A slow cleanup/reset shifts the retry boundary without shortening its wait."""
        value = policy(); admitted(value)
        value.receipt(terminal(), context(), now_ns=1_290_000_000)
        value.released(dict(type='released', serverNowMs=1300, worldReadiness=dict(epoch=3)),
                       context(), now_ns=1_310_000_000)
        value.history_reset_done(context(), now_ns=1_610_000_000)
        observe(value, frame(2100, epoch=3))
        self.assertIsNone(observe(value, frame(2160, epoch=3)))
        self.assertEqual(value.attempts, 1)
        observe(value, frame(2290, epoch=3))
        self.assertEqual(observe(value, frame(2350, epoch=3))['kind'], 'release')
        self.assertEqual(value.attempts, 2)

    def test_retry_cannot_precede_terminal_cleanup_or_reset(self):
        """Elapsed time alone cannot leave any of the three prerequisite wait states."""
        for phase in ('await_terminal', 'await_cleanup', 'await_reset'):
            with self.subTest(phase=phase):
                value = policy(); admitted(value)
                if phase != 'await_terminal':
                    value.receipt(terminal(), context(), now_ns=1_290_000_000)
                if phase == 'await_reset':
                    value.released(dict(type='released', serverNowMs=1300, worldReadiness=dict(epoch=3)),
                                   context(), now_ns=1_310_000_000)
                self.assertIsNone(observe(value, frame(2020, epoch=3)))
                self.assertIsNone(observe(value, frame(2080, epoch=3)))
                self.assertEqual(value.phase, phase)
                self.assertEqual(value.attempts, 1)

    def test_retry_still_requires_distinct_fresh_source_and_unchanged_owner(self):
        """The shorter clock cannot authorize stale/repeated sources or changed control."""
        for defect in ('source', 'frame', 'stale', 'unknown', 'owner', 'goal', 'capture'):
            with self.subTest(defect=defect):
                value = policy(); awaiting_exit(value)
                observe(value, frame(1980, epoch=3))
                pixels, ctx = frame(2040, epoch=3), context()
                if defect == 'source': pixels['sourceFrame']['timestamp100ns'] = 1980*10000
                if defect == 'frame': pixels['frameId'] = pixels['frameWorldReadiness']['sourceFrameId'] = 1980
                if defect == 'stale': pixels['serverNowMs'] += 150
                if defect == 'unknown': pixels['motionEvidence']['status'] = 'unknown'
                if defect == 'owner': ctx['ownerEpoch'] = 'replacement'
                if defect == 'goal': ctx['controlToken'] = (0, 1, 'new-goal', 'run')
                if defect == 'capture': pixels['sourceFrame']['captureEpoch'] = 'b'*32
                result = observe(value, pixels, ctx=ctx, now=2_061_000_000)
                self.assertNotEqual(None if result is None else result['kind'], 'release')
                self.assertEqual(value.attempts, 1)
                self.assertTrue(value.blocks_model)

    def test_normal_exit_cancels_short_retry_and_preserves_separate_incident_cooldown(self):
        """A completed normal-hint exit returns to the original five-second boundary."""
        value = policy(); awaiting_exit(value)
        observe(value, frame(1360, epoch=3, motion='normal'))
        self.assertEqual(observe(value, frame(1420, epoch=3, motion='normal'))['kind'], 'resume')
        self.assertFalse(value.blocks_model)
        self.assertEqual(value.cooldown_until_ns, 6_070_000_000)
        observe(value, frame(1980, epoch=3))
        self.assertIsNone(observe(value, frame(2040, epoch=3), now=2_061_000_000))
        self.assertEqual(value.attempts, 1)
        observe(value, frame(5960, epoch=3))
        self.assertEqual(observe(value, frame(6060, epoch=3))['kind'], 'release')
        self.assertEqual(value.attempts, 2)

    def test_exhausted_resident_budget_fails_after_short_wait_without_third_attempt(self):
        """Inherited lifetime usage remains authoritative inside an unresolved incident."""
        value = policy(initial_attempts=1); awaiting_exit(value)
        observe(value, frame(1980, epoch=3))
        result = observe(value, frame(2040, epoch=3), now=2_061_000_000)
        self.assertEqual(result['reason'], 'attempt_budget_exhausted')
        self.assertEqual(value.attempts, 2)
        self.assertTrue(result['cleanupRequired'])
        self.assertTrue(value.blocks_model)
        self.assertFalse(observe(value, frame(2100, epoch=3))['cleanupRequired'])

if __name__ == '__main__':
    unittest.main()
