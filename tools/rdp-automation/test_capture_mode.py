"""Typed capture backend switching with synthetic states and no desktop actions."""
import io
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
from test_rdp_control import FakePipe


class CaptureModeTests(unittest.TestCase):
    def setUp(self):
        self.child = {'processId': 123, 'windowsSessionId': 3, 'instanceNonce': 'child-epoch',
                      'instanceType': 'ChildSession', 'remoteDesktop': True, 'automationEnabled': True,
                      'runtimeRunning': True, 'automationState': 'game_ready', 'taskRunning': False,
                      'agentStreamRunning': False, 'captureMode': 'BitBlt'}

    def test_mode_is_exact_enum_name_and_wire_is_nonce_bound(self):
        api = FakePipe(self.child)
        api.session = 3
        for mode in control.CAPTURE_MODES:
            control.exchange('setCaptureMode', 123, 3, nonce='child-epoch', fields={'captureMode': mode}, api=api)
            self.assertEqual(api.request['captureMode'], mode)
            self.assertEqual(api.request['targetNonce'], 'child-epoch')
        for mode in ('windowsgraphicscapture', '1', 1, True, None, 'other'):
            with self.assertRaises(control.ControlError):
                control.exchange('setCaptureMode', 123, 3, nonce='child-epoch', fields={'captureMode': mode}, api=api)

    def test_busy_console_primary_and_missing_optin_rejected_before_mutation(self):
        for overrides in ({'taskRunning': True}, {'agentStreamRunning': True}, {'remoteDesktop': False},
                          {'instanceType': 'Primary'}, {'automationEnabled': False}, {'taskRunning': None}):
            with self.subTest(overrides=overrides), patch.object(control, 'mutate') as mutation:
                with self.assertRaises(control.ControlError):
                    control.set_capture_mode({**self.child, **overrides}, 'WindowsGraphicsCapture', 1)
                mutation.assert_not_called()

    def test_switch_waits_for_selected_backend_and_complete_lifecycle(self):
        changing = {**self.child, 'automationState': 'changing_capture', 'taskRunning': True}
        partial = {**changing, 'captureMode': 'WindowsGraphicsCapture', 'runtimeRunning': True}
        ready = {**partial, 'automationState': 'game_ready', 'taskRunning': False}
        with patch.object(control, 'mutate') as mutation, \
                patch.object(control, 'refresh', side_effect=[changing, partial, ready]) as refresh, \
                patch.object(control.time, 'sleep'):
            self.assertEqual(control.set_capture_mode(self.child, 'WindowsGraphicsCapture', 1), ready)
        mutation.assert_called_once_with('setCaptureMode', self.child, captureMode='WindowsGraphicsCapture')
        self.assertEqual(refresh.call_count, 3)

    def test_failed_start_and_mismatched_mode_never_report_success(self):
        for changed in ({**self.child, 'automationState': 'failed', 'automationError': 'WGC unavailable'}, self.child):
            with self.subTest(changed=changed), patch.object(control, 'mutate') as mutation, \
                    patch.object(control, 'refresh', return_value=changed):
                with self.assertRaises(control.ControlError):
                    control.set_capture_mode(self.child, 'WindowsGraphicsCapture', 1)
                self.assertEqual(mutation.call_count, 1)

    def test_cli_targets_child_and_requires_an_explicit_backend(self):
        with patch.object(sys, 'argv', ['rdp_control.py', 'set-capture-mode', '--mode', 'WindowsGraphicsCapture']), \
                patch.object(sys, 'stdout', io.StringIO()), \
                patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                patch.object(control, 'set_capture_mode', return_value=self.child) as switch:
            self.assertEqual(control.main(), 0)
        switch.assert_called_once_with(self.child, 'WindowsGraphicsCapture', 120)


if __name__ == '__main__':
    unittest.main()
