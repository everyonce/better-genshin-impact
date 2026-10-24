"""CPU-only status/full-proof compatibility fixtures; no real endpoint is opened."""
import copy
import unittest
from unittest.mock import patch
import rdp_control as control
import test_navigation_endpoint_continuation as legacy
import test_navigation_courtyard_cycle as courtyard


def compact(status):
    """Independent fixture encoder for the exact three-field server reference."""
    owner = status['navigationBaseline']
    owner['endpointContinuationVersion'] = 2
    link = owner.get('continuation')
    if link is not None:
        owner['continuation'] = dict(version=2, predecessorRunId=link['predecessorRunId'],
                                     predecessorProfileId=link['predecessorProfileId'])


class ContinuationReferenceTests(unittest.TestCase):
    def setUp(self):
        self.fx = legacy.EndpointContinuationTests(); self.fx.setUp()
        for status in (self.fx.child, self.fx.prior_full, self.fx.terminal, self.fx.full): compact(status)

    def test_projection_is_exact_and_legacy_is_unmodified(self):
        link = self.fx.link
        self.assertIs(link, control._baseline_continuation_projection(link, 1))
        expected = dict(version=2, predecessorRunId=self.fx.predecessor, predecessorProfileId=legacy.FORWARD)
        self.assertEqual(expected, control._baseline_continuation_projection(link, 2))
        self.assertIsNone(control._baseline_continuation_projection(None, 2))

    def test_v2_retains_v1_full_result_and_single_mutation(self):
        result = self.fx.invoke()
        self.assertEqual(self.fx.full, result)
        self.assertEqual(2, result['navigationBaseline']['continuation']['version'])
        self.assertEqual(self.fx.link, result['navigationBaseline']['result']['continuation'])
        self.assertEqual(1, self.fx.start_count)
        self.assertEqual(2, self.fx.query_count)

    def test_legacy_full_link_server_still_passes(self):
        fx = legacy.EndpointContinuationTests(); fx.setUp()
        self.assertEqual(fx.full, fx.invoke())
        self.assertEqual(1, fx.start_count)

    def test_unknown_capability_fails_before_mutation(self):
        for value in (None, 0, 3, True, '2'):
            child = copy.deepcopy(self.fx.child); child['navigationBaseline']['endpointContinuationVersion'] = value
            with self.subTest(value=value), self.assertRaises(control.ControlError): self.fx.invoke(child=child)
            self.assertEqual(0, self.fx.start_count)

    def test_malformed_or_substituted_reference_is_never_full_proof(self):
        cases = [None, {}, dict(version=1, predecessorRunId=self.fx.predecessor, predecessorProfileId=legacy.FORWARD),
                 dict(version=2.0, predecessorRunId=self.fx.predecessor, predecessorProfileId=legacy.FORWARD),
                 dict(version=2, predecessorRunId='e' * 32, predecessorProfileId=legacy.FORWARD),
                 dict(version=2, predecessorRunId=self.fx.predecessor, predecessorProfileId=legacy.REVERSE),
                 {**self.fx.terminal['navigationBaseline']['continuation'], 'predecessorEvidence': {}}]
        for reference in cases:
            terminal = copy.deepcopy(self.fx.terminal); terminal['navigationBaseline']['continuation'] = reference
            with self.subTest(reference=reference), self.assertRaises(control.NavigationBaselineError): self.fx.invoke(initial=terminal)
            self.assertEqual(1, self.fx.start_count)
            self.assertEqual(1, self.fx.query_count)

    def test_capability_cannot_change_after_admission(self):
        terminal = copy.deepcopy(self.fx.terminal); terminal['navigationBaseline']['endpointContinuationVersion'] = 1
        with self.assertRaises(control.NavigationBaselineError): self.fx.invoke(initial=terminal)
        self.assertEqual(1, self.fx.start_count)

    def test_observable_game_and_modes_are_checked_before_pinning_running_or_terminal_reference(self):
        for state in ('running', 'completed'):
            for key, value in [('gameProcessId', 999), ('effectiveReadbackMode', 'blocking'), ('captureMode', 'BitBlt')]:
                changed = copy.deepcopy(self.fx.terminal); changed['navigationBaseline']['state'] = state
                target = changed['navigationBaseline'] if key == 'gameProcessId' else changed
                target[key] = value
                with self.subTest(state=state, key=key), self.assertRaises(control.NavigationBaselineError):
                    self.fx.invoke(initial=changed)
                self.assertEqual(1, self.fx.start_count)
                self.assertEqual(1, self.fx.query_count)

    def test_later_poll_cannot_change_observable_game_or_modes_after_valid_admission(self):
        admitted = copy.deepcopy(self.fx.terminal); admitted['navigationBaseline']['state'] = 'running'
        for key, value in [('gameProcessId', 999), ('effectiveReadbackMode', 'blocking'), ('captureMode', 'BitBlt')]:
            changed = copy.deepcopy(self.fx.terminal)
            target = changed['navigationBaseline'] if key == 'gameProcessId' else changed
            target[key] = value
            with self.subTest(key=key), self.assertRaises(control.NavigationBaselineError) as error:
                self.fx.invoke(initial=admitted, refresh=changed)
            self.assertEqual(admitted, error.exception.status)
            self.assertEqual(1, self.fx.start_count)
            self.assertEqual(1, self.fx.query_count)

    def test_dedicated_outer_reference_must_match_observed_owner(self):
        full = copy.deepcopy(self.fx.full); full['navigationBaseline']['continuation']['predecessorRunId'] = 'e' * 32
        with self.assertRaises(control.NavigationBaselineError): self.fx.invoke(full=full)
        self.assertEqual(1, self.fx.start_count)

    def test_compact_reference_cannot_replace_terminal_full_proof(self):
        full = copy.deepcopy(self.fx.full)
        full['navigationBaseline']['result']['continuation'] = copy.deepcopy(full['navigationBaseline']['continuation'])
        with self.assertRaises(control.NavigationBaselineError) as error: self.fx.invoke(full=full)
        self.assertEqual(full, error.exception.status)
        self.assertEqual(1, self.fx.start_count)

    def test_terminal_proof_identity_evidence_and_source_are_still_checked(self):
        for key, value in [('childNonce', 'foreign'), ('runtimeIdentity', 'bad'), ('predecessorEvidence', {}),
                           ('predecessorFinalSource', {}), ('physicalInputAcknowledged', True)]:
            full = copy.deepcopy(self.fx.full); full['navigationBaseline']['result']['continuation'][key] = value
            with self.subTest(key=key), self.assertRaises(control.NavigationBaselineError) as error: self.fx.invoke(full=full)
            self.assertEqual(full, error.exception.status)
            self.assertEqual(1, self.fx.start_count)

    def test_native_failure_retains_complete_terminal_proof(self):
        for row in (self.fx.terminal, self.fx.full):
            row['navigationBaseline'].update(state='failed', error='native_source_unavailable_or_stale')
        self.fx.full['navigationBaseline']['result'].update(verified=False, error='native_source_unavailable_or_stale')
        with self.assertRaises(control.NavigationBaselineError) as error: self.fx.invoke()
        self.assertEqual(self.fx.full, error.exception.status)
        self.assertEqual(self.fx.link, error.exception.status['navigationBaseline']['result']['continuation'])

    def test_read_only_predecessor_fetch_cannot_substitute_latest_owner(self):
        self.fx.prior_full['navigationBaseline']['runId'] = 'f' * 32
        with self.assertRaises(control.ControlError): self.fx.invoke()
        self.assertEqual(0, self.fx.start_count)

    def test_courtyard_v2_can_continue_latest_v2_owner_without_recursive_proof(self):
        fx = courtyard.CourtyardContinuationTests(); fx.setUp()
        for row in (fx.child, fx.prior, fx.terminal, fx.full): compact(row)
        returned = fx.invoke()
        fx.configure(returned, courtyard.FORWARD, 'e' * 32)
        # configure copies the prior compact owner; only the new owner still carries a full fixture link.
        for row in (fx.child, fx.prior, fx.terminal, fx.full): compact(row)
        result = fx.invoke()
        self.assertEqual(courtyard.FORWARD, result['navigationBaseline']['profileId'])
        self.assertEqual(returned['navigationBaseline']['runId'], result['navigationBaseline']['continuation']['predecessorRunId'])
        self.assertEqual(1, fx.starts)

    def test_courtyard_prior_reference_must_match_its_dedicated_link(self):
        fx = courtyard.CourtyardContinuationTests(); fx.setUp()
        returned = fx.invoke()
        fx.configure(returned, courtyard.FORWARD, 'e' * 32)
        for row in (fx.child, fx.prior, fx.terminal, fx.full): compact(row)
        fx.prior['navigationBaseline']['result']['continuation']['predecessorRunId'] = 'f' * 32
        with self.assertRaises(control.ControlError): fx.invoke()
        self.assertEqual(0, fx.starts)

    def test_v2_uncertain_mutation_is_not_replayed(self):
        fx = courtyard.CourtyardContinuationTests(); fx.setUp()
        for row in (fx.child, fx.prior, fx.terminal, fx.full): compact(row)
        with self.assertRaises(control.ControlError): fx.invoke(lost=True)
        self.assertEqual(1, fx.starts)

    def test_v2_selected_shadow_still_waits_cleanup_and_pins_full_proof(self):
        import test_navigation_continuation_shadow as shadow
        fx = shadow.ContinuationShadowTests(); fx.setUp()
        for row in (fx.child, fx.terminal, fx.full, fx.reverse.prior_full): compact(row)
        busy = copy.deepcopy(fx.terminal); busy['taskRunning'] = True
        with patch.object(control, 'exchange', side_effect=[fx.reverse.prior_full, fx.full]), \
                patch.object(control, 'mutate', return_value=busy) as start, \
                patch.object(control, 'refresh', return_value=fx.terminal), patch.object(control.time, 'sleep'):
            self.assertEqual(fx.full, fx.invoke())
        start.assert_called_once()

    def test_v2_incomplete_shadow_retains_terminal_link(self):
        import test_navigation_continuation_shadow as shadow
        fx = shadow.ContinuationShadowTests(); fx.setUp()
        for row in (fx.child, fx.terminal, fx.full, fx.reverse.prior_full): compact(row)
        fx.full['navigationBaseline']['result']['evidence']['shadowCapture']['workerRetired'] = False
        with patch.object(control, 'exchange', side_effect=[fx.reverse.prior_full, fx.full]), \
                patch.object(control, 'mutate', return_value=fx.terminal) as start:
            with self.assertRaises(control.NavigationBaselineError) as error: fx.invoke()
        self.assertEqual(fx.full, error.exception.status)
        start.assert_called_once()


if __name__ == '__main__': unittest.main()
