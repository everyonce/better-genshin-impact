"""Combined mocked contract: exact predecessor plus passive archive, never native/controller execution."""
import copy
import io
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
import test_navigation_endpoint_continuation as reverse_fixtures
REVERSE = reverse_fixtures.REVERSE
import test_navigation_shadow_capture as shadow_fixtures
from test_rdp_control import FakePipe


class ContinuationShadowTests(unittest.TestCase):
    def setUp(self):
        self.reverse = reverse_fixtures.EndpointContinuationTests(); self.reverse.setUp()
        self.shadow = shadow_fixtures.ShadowCaptureTests(); self.shadow.setUp()
        self.child = copy.deepcopy(self.reverse.child)
        self.terminal = copy.deepcopy(self.reverse.terminal)
        self.full = copy.deepcopy(self.reverse.full)
        for row in (self.child, self.terminal, self.full, self.reverse.prior_full):
            row['navigationBaseline'].update(shadowCaptureVersion=1, shadowCaptureModes=[control.SHADOW_CAPTURE_MODE])
        for row in (self.terminal, self.full): row['navigationBaseline']['shadowCapture'] = control.SHADOW_CAPTURE_MODE
        self.full['navigationBaseline']['result']['evidence']['shadowCapture'] = copy.deepcopy(self.shadow.archive)

    def invoke(self):
        return control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer', route_profile=REVERSE,
            continuation_from_run_id=self.reverse.predecessor, shadow_capture=control.SHADOW_CAPTURE_MODE)

    def test_combined_start_is_once_and_waits_cleanup_with_both_exact_selections(self):
        busy = copy.deepcopy(self.terminal); busy['taskRunning'] = True
        with patch.object(control, 'exchange', side_effect=[self.reverse.prior_full, self.full]) as read, \
                patch.object(control, 'mutate', return_value=busy) as start, \
                patch.object(control, 'refresh', return_value=self.terminal) as refresh, patch.object(control.time, 'sleep'), \
                patch.object(control, 'reset_navigation') as reset, patch.object(control, 'set_capture_mode') as mode:
            self.assertEqual(self.invoke(), self.full)
        start.assert_called_once_with('startNavigationBaseline', self.child, timingContract='v4',
            capturePolicy='task_owned_timer', routeProfile=REVERSE, continuationFromRunId=self.reverse.predecessor,
            shadowCapture=control.SHADOW_CAPTURE_MODE)
        self.assertEqual(read.call_count, 2); refresh.assert_called_once(); reset.assert_not_called(); mode.assert_not_called()

    def test_each_capability_is_required_before_any_mutation(self):
        for key in ('shadowCaptureVersion', 'endpointContinuationVersion'):
            with self.subTest(key=key):
                self.setUp(); self.child['navigationBaseline'][key] = None
                with patch.object(control, 'exchange', return_value=self.reverse.prior_full), patch.object(control, 'mutate') as start:
                    with self.assertRaises(control.ControlError): self.invoke()
                    start.assert_not_called()

    def test_shadow_does_not_make_a_changed_predecessor_admissible(self):
        self.child['navigationBaseline']['runId'] = 'e' * 32
        with patch.object(control, 'exchange') as read, patch.object(control, 'mutate') as start:
            with self.assertRaises(control.ControlError): self.invoke()
        read.assert_not_called(); start.assert_not_called()

    def test_lost_combined_start_ack_does_not_retry_or_reset(self):
        with patch.object(control, 'exchange', return_value=self.reverse.prior_full) as read, \
                patch.object(control, 'mutate', side_effect=control.ControlError('uncertain')) as start, \
                patch.object(control, 'refresh') as refresh, patch.object(control, 'reset_navigation') as reset:
            with self.assertRaises(control.ControlError): self.invoke()
        read.assert_called_once(); start.assert_called_once(); refresh.assert_not_called(); reset.assert_not_called()

    def test_incomplete_archive_retains_verified_route_and_exact_continuation(self):
        archive = self.full['navigationBaseline']['result']['evidence']['shadowCapture']
        archive.update(complete=False, workerRetired=False, error='shadow_worker_retirement_timeout')
        with patch.object(control, 'exchange', side_effect=[self.reverse.prior_full, self.full]), \
                patch.object(control, 'mutate', return_value=self.terminal):
            with self.assertRaises(control.NavigationBaselineError) as failure: self.invoke()
        self.assertEqual(self.full, failure.exception.status)
        self.assertTrue(failure.exception.status['navigationBaseline']['result']['verified'])
        self.assertEqual(self.reverse.link, failure.exception.status['navigationBaseline']['result']['continuation'])

    def test_neither_echo_can_change_under_other_valid_selection(self):
        for which in ('shadow', 'continuation'):
            with self.subTest(which=which):
                self.setUp(); changed = copy.deepcopy(self.terminal)
                if which == 'shadow': changed['navigationBaseline']['shadowCapture'] = None
                else: changed['navigationBaseline']['continuation']['runtimeIdentity'] = 'e' * 32
                running = copy.deepcopy(self.terminal); running['taskRunning'] = True
                running['navigationBaseline']['state'] = 'running'
                with patch.object(control, 'exchange', return_value=self.reverse.prior_full), \
                        patch.object(control, 'mutate', return_value=running) as start, \
                        patch.object(control, 'refresh', return_value=changed), patch.object(control.time, 'sleep'):
                    with self.assertRaises(control.NavigationBaselineError): self.invoke()
                    start.assert_called_once()

    def test_unretired_predecessor_archive_blocks_both_next_selection_choices(self):
        for selected in (None, control.SHADOW_CAPTURE_MODE):
            with self.subTest(selected=selected):
                self.setUp()
                for row in (self.child, self.reverse.prior_full):
                    row['navigationBaseline']['shadowCapture'] = control.SHADOW_CAPTURE_MODE
                archive = copy.deepcopy(self.shadow.archive); archive.update(complete=False, workerRetired=False)
                self.reverse.prior_full['navigationBaseline']['result']['evidence']['shadowCapture'] = archive
                with patch.object(control, 'exchange', return_value=self.reverse.prior_full), patch.object(control, 'mutate') as start:
                    with self.assertRaises(control.ControlError):
                        control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer', route_profile=REVERSE,
                            continuation_from_run_id=self.reverse.predecessor, shadow_capture=selected)
                    start.assert_not_called()

    def test_selected_predecessor_requires_summary_and_omission_rejects_unexpected_archive(self):
        for selected in (None, control.SHADOW_CAPTURE_MODE):
            for defect in ('missing', 'null', 'unselected', 'unknown'):
                with self.subTest(selected=selected, defect=defect):
                    self.setUp()
                    prior = self.reverse.prior_full['navigationBaseline']['result']['evidence']
                    for row in (self.child, self.reverse.prior_full):
                        if defect != 'unselected': row['navigationBaseline']['shadowCapture'] = ('other' if defect == 'unknown' else control.SHADOW_CAPTURE_MODE)
                    if defect == 'null': prior['shadowCapture'] = None
                    elif defect in ('unselected', 'unknown'): prior['shadowCapture'] = copy.deepcopy(self.shadow.archive)
                    with patch.object(control, 'exchange', return_value=self.reverse.prior_full), patch.object(control, 'mutate') as start:
                        with self.assertRaises(control.ControlError):
                            control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer', route_profile=REVERSE,
                                continuation_from_run_id=self.reverse.predecessor, shadow_capture=selected)
                        start.assert_not_called()

    def test_complete_archived_predecessor_remains_eligible_and_is_joined(self):
        for row in (self.child, self.reverse.prior_full): row['navigationBaseline']['shadowCapture'] = control.SHADOW_CAPTURE_MODE
        evidence = self.reverse.prior_full['navigationBaseline']['result']['evidence']
        evidence['shadowCapture'] = copy.deepcopy(self.shadow.archive)
        for link in (self.terminal['navigationBaseline']['continuation'], self.full['navigationBaseline']['continuation'],
                     self.full['navigationBaseline']['result']['continuation']): link['predecessorEvidence'] = copy.deepcopy(evidence)
        with patch.object(control, 'exchange', side_effect=[self.reverse.prior_full, self.full]), \
                patch.object(control, 'mutate', return_value=self.terminal) as start:
            self.assertEqual(self.invoke(), self.full)
            start.assert_called_once()

    def test_actual_request_framing_retains_both_selectors_and_explicit_null_rejects(self):
        fields = dict(timingContract='v4', capturePolicy='task_owned_timer', routeProfile=REVERSE,
            continuationFromRunId=self.reverse.predecessor, shadowCapture=control.SHADOW_CAPTURE_MODE)
        api = FakePipe(self.terminal); api.session = 3
        control.exchange('startNavigationBaseline', 123, 3, nonce='child-epoch', fields=fields, api=api)
        self.assertEqual(self.reverse.predecessor, api.request['continuationFromRunId'])
        self.assertEqual(control.SHADOW_CAPTURE_MODE, api.request['shadowCapture'])
        for key in ('continuationFromRunId', 'shadowCapture'):
            with self.subTest(key=key), self.assertRaises(control.ControlError):
                control.exchange('startNavigationBaseline', 123, 3, nonce='child-epoch', fields={**fields, key: None}, api=FakePipe(self.terminal))

    def test_cli_binds_shared_optional_arguments_by_name(self):
        with patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                patch.object(control, 'run_navigation_baseline', return_value={}) as run, patch('sys.stdout', new_callable=io.StringIO), \
                patch.object(sys, 'argv', ['rdp_control.py', 'run-navigation-baseline', '--route-profile', REVERSE,
                    '--continuation-from-run-id', self.reverse.predecessor, '--shadow-capture', control.SHADOW_CAPTURE_MODE,
                    '--timing-contract', 'v4', '--capture-policy', 'task_owned_timer']):
            self.assertEqual(control.main(), 0)
        run.assert_called_once_with(self.child, 45, 'v4', 'task_owned_timer', route_profile=REVERSE,
            continuation_from_run_id=self.reverse.predecessor, shadow_capture=control.SHADOW_CAPTURE_MODE)


if __name__ == '__main__': unittest.main()
