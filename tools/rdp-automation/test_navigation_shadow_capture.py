"""Fake transport/terminal evidence tests; no endpoint or native process calls."""
import copy
import unittest
from unittest.mock import patch

import rdp_control as control
import test_navigation_baseline as baseline_fixtures
from test_rdp_control import FakePipe


class ShadowCaptureTests(unittest.TestCase):
    def setUp(self):
        self.base = baseline_fixtures.NavigationBaselineTests()
        self.base.setUp()
        self.child = copy.deepcopy(self.base.child)
        self.caps = dict(timingContracts=['v1', 'v4'], timingContract='v4',
                         controllerMethod='native-fixed-leg-feedback-v4',
                         capturePolicies=['shared', 'task_owned_timer'], capturePolicy='task_owned_timer',
                         shadowCaptureVersion=1, shadowCaptureModes=[control.SHADOW_CAPTURE_MODE])
        self.child['navigationBaseline'].update(self.caps)
        self.admitted = self.base.status()
        self.terminal, self.full = self.base.result()
        for value in (self.admitted, self.terminal, self.full):
            value['navigationBaseline'].update(self.caps, shadowCapture=control.SHADOW_CAPTURE_MODE)
        self.full['navigationBaseline']['result'].update(timingContract='v4', capturePolicy='task_owned_timer',
                                                        controllerMethod='native-fixed-leg-feedback-v4')
        self.archive = dict(mode=control.SHADOW_CAPTURE_MODE, complete=True, workerRetired=True, error=None,
                            framesSeen=5, framesAccepted=3, framesWritten=3, duplicateFrames=2,
                            framesRejected=0, offersIgnoredAfterStop=0, framesLost=0,
                            manifestPath=r'D:\synthetic\shadow\manifest.json', manifestSha256='b' * 64,
                            nativeJournalSha256='A' * 64)
        self.full['navigationBaseline']['result']['evidence']['shadowCapture'] = self.archive

    def run_shadow(self):
        return control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer',
                                               shadow_capture=control.SHADOW_CAPTURE_MODE)

    def test_exact_capability_before_any_mutation(self):
        for change in ({'shadowCaptureVersion': None}, {'shadowCaptureVersion': True},
                       {'shadowCaptureVersion': 2}, {'shadowCaptureModes': []}, {'shadowCaptureModes': None}):
            self.child['navigationBaseline'] = {**self.caps, **self.base.child['navigationBaseline'], **change}
            with self.subTest(change=change), patch.object(control, 'mutate') as mutation:
                with self.assertRaises(control.ControlError): self.run_shadow()
                mutation.assert_not_called()

    def test_wrong_timing_or_capture_policy_never_starts(self):
        for timing, policy, mode in [('v1', 'task_owned_timer', control.SHADOW_CAPTURE_MODE),
                                    ('v4', 'shared', control.SHADOW_CAPTURE_MODE), ('v4', 'task_owned_timer', 'other')]:
            with self.subTest(timing=timing, policy=policy, mode=mode), patch.object(control, 'mutate') as mutation:
                with self.assertRaises(control.ControlError):
                    control.run_navigation_baseline(self.child, 45, timing, policy, shadow_capture=mode)
                mutation.assert_not_called()

    def test_one_start_waits_cleanup_and_merges_exact_archive(self):
        with patch.object(control, 'mutate', return_value=self.admitted) as start, \
             patch.object(control, 'exchange', side_effect=[{**self.terminal, 'taskRunning': True}, self.terminal, self.full]) as query, patch.object(control.time, 'sleep'):
            result = self.run_shadow()
        self.assertEqual(start.call_count, 1)
        self.assertEqual(start.call_args.kwargs['shadowCapture'], control.SHADOW_CAPTURE_MODE)
        self.assertEqual([c.args[0] for c in query.call_args_list], ['status', 'status', 'navigationBaselineResult'])
        self.assertEqual(result['navigationBaseline']['result']['evidence']['shadowCapture'], self.archive)

    def test_lost_start_ack_is_not_replayed_or_queried(self):
        with patch.object(control, 'mutate', side_effect=control.ControlError('lost')) as start, \
             patch.object(control, 'exchange') as status:
            with self.assertRaises(control.ControlError): self.run_shadow()
        self.assertEqual(start.call_count, 1); status.assert_not_called()

    def test_archive_failure_retains_verified_native_result(self):
        for change in ({'complete': False}, {'workerRetired': False}, {'error': 'io_failure'},
                       {'framesWritten': 2, 'framesLost': 1}, {'manifestSha256': 'bad'},
                       {'nativeJournalSha256': 'c' * 64}, {'framesAccepted': True}, {'framesSeen': 6}):
            full = copy.deepcopy(self.full)
            full['navigationBaseline']['result']['evidence']['shadowCapture'].update(change)
            with self.subTest(change=change), patch.object(control, 'mutate', return_value=self.terminal), \
                 patch.object(control, 'exchange', return_value=full):
                with self.assertRaises(control.NavigationBaselineError) as caught: self.run_shadow()
                self.assertRegex(str(caught.exception), '[Ss]hadow')
                result = caught.exception.status['navigationBaseline']['result']
                self.assertTrue(result['verified'])
                self.assertEqual(result['evidence']['shadowCapture'], full['navigationBaseline']['result']['evidence']['shadowCapture'])

    def test_selection_cannot_change_in_terminal_query(self):
        full = copy.deepcopy(self.full); full['navigationBaseline']['shadowCapture'] = None
        with patch.object(control, 'mutate', return_value=self.terminal), patch.object(control, 'exchange', return_value=full):
            with self.assertRaisesRegex(control.NavigationBaselineError, 'pinned terminal'): self.run_shadow()

    def test_selection_cannot_change_during_wait(self):
        self.admitted['navigationBaseline']['shadowCapture'] = None
        with patch.object(control, 'mutate', return_value=self.admitted), patch.object(control, 'exchange') as status:
            with self.assertRaisesRegex(control.NavigationBaselineError, 'selection changed'): self.run_shadow()
        status.assert_not_called()

    def test_wire_explicit_null_unknown_and_wrong_dependencies_fail_before_pipe(self):
        for fields in ({'shadowCapture': None}, {'shadowCapture': 'other'},
                       {'shadowCapture': control.SHADOW_CAPTURE_MODE},
                       {'shadowCapture': control.SHADOW_CAPTURE_MODE, 'timingContract': 'v4', 'capturePolicy': 'shared'}):
            pipe = FakePipe(self.child)
            with self.subTest(fields=fields), self.assertRaises(control.ControlError):
                control.exchange('startNavigationBaseline', 123, 3, nonce='child-epoch', fields=fields, api=pipe)
            self.assertFalse(hasattr(pipe, 'pipe_name'))

    def test_default_legacy_request_stays_omitted(self):
        terminal, full = self.base.result()
        with patch.object(control, 'mutate', return_value=terminal) as start, patch.object(control, 'exchange', return_value=full):
            control.run_navigation_baseline(self.base.child, 45)
        self.assertNotIn('shadowCapture', start.call_args.kwargs)


if __name__ == '__main__': unittest.main()
