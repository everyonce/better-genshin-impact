"""Explicit opposite-direction CLI transactions over fake, immutable terminal reports."""
import copy
import io
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
import test_navigation_endpoint_continuation as old
from test_rdp_control import FakePipe

FORWARD = 'mondstadt-city-courtyard-forward-v1'
RETURN = 'mondstadt-city-courtyard-return-v1'


class CourtyardContinuationTests(unittest.TestCase):
    def setUp(self):
        self.seed = old.EndpointContinuationTests(); self.seed.setUp()
        self.configure(self.short(), RETURN, 'd' * 32)

    def short(self):
        previous = copy.deepcopy(self.seed.prior_full)
        previous['navigationBaseline'].update(profileId=old.OLD)
        previous['navigationBaseline']['result'].update(profileId=old.OLD, routeVersion=None, legs=[], waypoint=None)
        return previous

    def configure(self, previous, requested, next_id):
        """A prior full result is the sole predecessor; no unretained ancestor is fabricated."""
        self.requested = requested
        self.prior = copy.deepcopy(previous)
        self.child = copy.deepcopy(previous); self.child['navigationBaseline'].pop('result', None)
        self.predecessor = self.child['navigationBaseline']['runId']
        self.terminal = copy.deepcopy(self.child)
        operation = self.terminal['navigationBaseline']
        previous_result = self.prior['navigationBaseline']['result']
        source = previous_result['samples'][-1]
        link = copy.deepcopy(self.seed.link)
        link.update(predecessorRunId=self.predecessor, predecessorProfileId=previous_result['profileId'],
                    predecessorEvidence=copy.deepcopy(previous_result['evidence']),
                    predecessorFinalSource=dict(CaptureEpoch=source['sourceEpoch'], SourceTimestamp100ns=source['sourceTimestamp100ns'],
                                                AcquiredAtStopwatchTicks=source['acquiredAtStopwatchTicks']))
        operation.update(runId=next_id, profileId=requested, continuation=link)
        self.full = copy.deepcopy(self.terminal)
        measured = copy.deepcopy(previous_result)
        measured.update(profileId=requested, continuation=copy.deepcopy(link), legs=[dict(legIndex=1, startPointId=2 if requested == RETURN else 1, endPointId=1 if requested == RETURN else 2, outcome='completed')], waypoint=None, routeVersion=1)
        self.full['navigationBaseline']['result'] = measured
        for pose in [measured['initialSample'], *measured['samples'], *measured['verificationSamples']]: pose['legIndex'] = 1
        for status in (self.prior, self.child, self.terminal, self.full):
            status['navigationBaseline']['routeProfiles'] = [old.OLD, old.FORWARD, old.REVERSE, RETURN, FORWARD]
            status['navigationBaseline'].update(shadowCaptureVersion=1, shadowCaptureModes=[control.SHADOW_CAPTURE_MODE])

    def invoke(self, shadow=None, lost=False):
        events = []
        def read(*args, **kwargs):
            run = kwargs['fields']['navigationBaselineRunId']; events.append(('read', run))
            return self.prior if run == self.predecessor else self.full
        def start(*args, **kwargs):
            events.append(('start', kwargs))
            if lost: raise control.ControlError('lost acknowledgement')
            return self.terminal
        with patch.object(control, 'exchange', side_effect=read), patch.object(control, 'mutate', side_effect=start) as mutation, \
                patch.object(control, 'refresh', return_value=self.terminal), patch.object(control, 'reset_navigation') as reset, \
                patch.object(control, 'set_capture_mode') as mode, patch.object(control.time, 'sleep'):
            try:
                return control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer',
                    route_profile=self.requested, continuation_from_run_id=self.predecessor, shadow_capture=shadow)
            finally:
                self.events = events; self.starts = mutation.call_count
                reset.assert_not_called(); mode.assert_not_called()

    def test_short_return_forward_return_are_separate_one_shot_transactions(self):
        previous = self.invoke()
        for profile, run_id in ((FORWARD, 'e' * 32), (RETURN, 'f' * 32)):
            self.assertEqual(self.starts, 1)
            self.assertEqual([row[0] for row in self.events], ['read', 'start', 'read'])
            self.configure(previous, profile, run_id)
            previous = self.invoke()
            self.assertEqual(previous['navigationBaseline']['result']['waypoint'], None)
            self.assertEqual(len(previous['navigationBaseline']['result']['legs']), 1)
        self.assertEqual(self.starts, 1)

    def test_missing_new_advertisement_refuses_before_predecessor_read(self):
        self.child['navigationBaseline']['routeProfiles'].remove(RETURN)
        with self.assertRaises(control.ControlError): self.invoke()
        self.assertEqual(self.events, [])

    def test_direction_pairs_reject_wrong_completed_predecessor_before_mutation(self):
        for requested, wrong in ((RETURN, RETURN), (RETURN, old.FORWARD), (RETURN, old.REVERSE),
                                 (FORWARD, old.OLD), (FORWARD, old.FORWARD), (FORWARD, FORWARD), (old.REVERSE, FORWARD)):
            self.setUp(); self.requested = requested; self.child['navigationBaseline']['profileId'] = wrong
            with self.subTest(requested=requested, wrong=wrong), self.assertRaises(control.ControlError): self.invoke()
            self.assertEqual(self.starts, 0)

    def test_latest_exact_completed_reverse_remains_required(self):
        for key, value in [('runId', 'e' * 32), ('state', 'failed'), ('state', 'running'), ('endpointContinuationVersion', True)]:
            self.setUp(); self.child['navigationBaseline'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(control.ControlError): self.invoke()
            self.assertEqual(self.starts, 0)

    def test_prior_own_link_must_match_its_compact_proof(self):
        self.configure(self.invoke(), FORWARD, "e" * 32)
        self.prior['navigationBaseline']['result']['continuation']['runtimeIdentity'] = 'e' * 32
        with self.assertRaises(control.ControlError): self.invoke()
        self.assertEqual(self.starts, 0)

    def test_prior_claimed_direction_must_be_a_valid_pair(self):
        self.configure(self.invoke(), FORWARD, "e" * 32)
        for row in (self.child, self.prior): row['navigationBaseline']['continuation']['predecessorProfileId'] = old.REVERSE
        self.prior['navigationBaseline']['result']['continuation']['predecessorProfileId'] = old.REVERSE
        with self.assertRaises(control.ControlError): self.invoke()
        self.assertEqual(self.starts, 0)

    def test_wrong_current_asset_order_is_rejected_after_one_start(self):
        self.full['navigationBaseline']['result']['legs'][0]['startPointId'] = 3
        with self.assertRaises(control.NavigationBaselineError): self.invoke()
        self.assertEqual(self.starts, 1)

    def test_new_link_must_name_actual_reverse_predecessor(self):
        for row in (self.terminal, self.full): row['navigationBaseline']['continuation']['predecessorProfileId'] = old.FORWARD
        self.full['navigationBaseline']['result']['continuation']['predecessorProfileId'] = old.FORWARD
        with self.assertRaises(control.NavigationBaselineError): self.invoke()
        self.assertEqual(self.starts, 1)

    def test_same_child_cannot_hide_changed_server_runtime_or_process_start(self):
        for key, value in [('runtimeIdentity', 'e' * 32), ('gameStartedAtUtcTicks', 123), ('captureType', 'other')]:
            self.setUp(); self.configure(self.invoke(), FORWARD, 'e' * 32)
            for row in (self.terminal, self.full): row['navigationBaseline']['continuation'][key] = value
            self.full['navigationBaseline']['result']['continuation'][key] = value
            with self.subTest(key=key), self.assertRaises(control.NavigationBaselineError): self.invoke()
            self.assertEqual(self.starts, 1)

    def test_selected_predecessor_needs_archive_for_either_next_selector(self):
        for summary in ('missing', None, {'mode': control.SHADOW_CAPTURE_MODE, 'workerRetired': False}):
            for next_shadow in (None, control.SHADOW_CAPTURE_MODE):
                self.setUp()
                for row in (self.child, self.prior): row['navigationBaseline']['shadowCapture'] = control.SHADOW_CAPTURE_MODE
                if summary != 'missing': self.prior['navigationBaseline']['result']['evidence']['shadowCapture'] = summary
                with self.subTest(summary=summary, next=next_shadow), self.assertRaises(control.ControlError): self.invoke(next_shadow)
                self.assertEqual(self.starts, 0)

    def test_unselected_predecessor_rejects_unexpected_archive(self):
        self.prior['navigationBaseline']['result']['evidence']['shadowCapture'] = {'workerRetired': True}
        with self.assertRaises(control.ControlError): self.invoke()
        self.assertEqual(self.starts, 0)

    def test_lost_ack_is_one_mutation_and_no_reconciliation_retry(self):
        with self.assertRaisesRegex(control.ControlError, 'lost acknowledgement'): self.invoke(lost=True)
        self.assertEqual(self.starts, 1)
        self.assertEqual([event[0] for event in self.events], ['read', 'start'])

    def test_wire_requires_exact_new_selector_contract_before_connect(self):
        good = dict(routeProfile=RETURN, timingContract='v4', capturePolicy='task_owned_timer', continuationFromRunId=self.predecessor)
        for fields in [{**good, 'continuationFromRunId': value} for value in (None, True, '', '0' * 32)] + [
                {**good, 'timingContract': 'v3'}, {**good, 'capturePolicy': 'shared'}]:
            api = FakePipe(self.child)
            with self.subTest(fields=fields), self.assertRaises(control.ControlError):
                control.exchange('startNavigationBaseline', 123, 3, nonce='child-epoch', fields=fields, api=api)
            self.assertFalse(hasattr(api, 'pipe_name'))
        api = FakePipe(self.terminal); api.session = 3
        control.exchange('startNavigationBaseline', 123, 3, nonce='child-epoch', fields=good, api=api)
        self.assertEqual(api.request['routeProfile'], RETURN)

    def test_cli_uses_named_direction_and_predecessor(self):
        with patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                patch.object(control, 'run_navigation_baseline', return_value={}) as run, patch('sys.stdout', new_callable=io.StringIO), \
                patch.object(sys, 'argv', ['rdp_control.py', 'run-navigation-baseline', '--route-profile', RETURN,
                    '--continuation-from-run-id', self.predecessor, '--timing-contract', 'v4', '--capture-policy', 'task_owned_timer']):
            self.assertEqual(control.main(), 0)
        run.assert_called_once_with(self.child, 45, 'v4', 'task_owned_timer', route_profile=RETURN, continuation_from_run_id=self.predecessor)

    def test_one_leg_shape_rejects_midpoint_second_leg_and_wrong_pose_index(self):
        for field, value in [('waypoint', self.seed.waypoint()), ('legs', self.seed.legs(True))]:
            self.setUp(); self.full['navigationBaseline']['result'][field] = value
            with self.subTest(field=field), self.assertRaises(control.NavigationBaselineError): self.invoke()
            self.assertEqual(self.starts, 1)
        self.setUp(); self.full['navigationBaseline']['result']['samples'][-1]['legIndex'] = 2
        with self.assertRaises(control.NavigationBaselineError): self.invoke()
        self.assertEqual(self.starts, 1)

    def test_ordinary_short_preserves_legacy_result_shape(self):
        for key, value in [('routeVersion', 1), ('legs', self.seed.legs(False)), ('waypoint', self.seed.waypoint())]:
            self.setUp(); self.prior['navigationBaseline']['result'][key] = value
            with self.subTest(key=key), self.assertRaises(control.ControlError): self.invoke()
            self.assertEqual(self.starts, 0)

    def test_failed_result_retains_partial_one_leg_and_never_replays(self):
        for row in (self.full, self.terminal): row['navigationBaseline'].update(state='failed', error='Climb')
        self.full['navigationBaseline']['result'].update(verified=False, error='Climb', samples=[])
        self.full['navigationBaseline']['result']['legs'][0]['outcome'] = 'failed'
        with self.assertRaises(control.NavigationBaselineError) as caught: self.invoke()
        self.assertEqual(self.starts, 1)
        self.assertEqual(caught.exception.status['navigationBaseline']['result']['legs'][0]['outcome'], 'failed')


if __name__ == '__main__': unittest.main()
