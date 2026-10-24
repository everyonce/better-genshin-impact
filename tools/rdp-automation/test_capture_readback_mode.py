"""Readback selection rejects ambiguous configuration without touching a desktop."""
import io
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
from test_rdp_control import FakePipe


class CaptureReadbackModeTests(unittest.TestCase):
    def setUp(self):
        self.child = {'processId': 123, 'windowsSessionId': 3, 'instanceNonce': 'child-epoch',
                      'instanceType': 'ChildSession', 'remoteDesktop': True, 'automationEnabled': True,
                      'runtimeRunning': True, 'automationState': 'game_ready', 'taskRunning': False,
                      'agentStreamRunning': False, 'captureMode': 'WindowsGraphicsCaptureV2',
                      'readbackVersion': 1, 'readbackModes': ['blocking', 'poll_single_v1'],
                      'configuredReadbackMode': 'blocking', 'effectiveReadbackMode': 'blocking'}

    def test_explicit_wire_is_nonce_bound_and_default_wire_remains_valid(self):
        api = FakePipe(self.child)
        api.session = 3
        for mode in control.READBACK_MODES:
            control.exchange('setCaptureMode', 123, 3, nonce='child-epoch',
                             fields={'captureMode': 'WindowsGraphicsCaptureV2', 'readbackMode': mode}, api=api)
            self.assertEqual(api.request['readbackMode'], mode)
            self.assertEqual(api.request['targetNonce'], 'child-epoch')
        control.exchange('setCaptureMode', 123, 3, nonce='child-epoch',
                         fields={'captureMode': 'WindowsGraphicsCaptureV2'}, api=api)
        self.assertNotIn('readbackMode', api.request)

    def test_null_aliases_numbers_non_v2_and_missing_backend_reject_at_wire_boundary(self):
        invalid = [{'captureMode': 'WindowsGraphicsCaptureV2', 'readbackMode': value}
                   for value in (None, True, 1, '', 'PollSingleV1', 'poll', {}, [])]
        invalid += [{'captureMode': 'BitBlt', 'readbackMode': value} for value in control.READBACK_MODES]
        invalid += [{'readbackMode': 'poll_single_v1'},
                    {'captureMode': 'WindowsGraphicsCaptureV2', 'readbackMode': 'poll_single_v1', 'extra': 1}]
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(control.ControlError):
                control.exchange('setCaptureMode', 123, 3, nonce='child-epoch', fields=fields)

    def test_readback_cannot_be_attached_to_unrelated_command(self):
        with self.assertRaises(control.ControlError):
            control.exchange('startChildGame', 123, 3, nonce='child-epoch', fields={'readbackMode': 'blocking'})

    def test_capability_unknown_version_or_missing_choice_rejects_before_mutation(self):
        variants = [{k: v for k, v in self.child.items() if not k.startswith('readback')},
                    *[{**self.child, 'readbackVersion': value} for value in (True, 0, 2, 1.0, None)],
                    *[{**self.child, 'readbackModes': value} for value in (None, 'poll_single_v1', [], [1], ['blocking'])]]
        for child in variants:
            with self.subTest(child=child), patch.object(control, 'mutate') as mutation:
                with self.assertRaises(control.ControlError):
                    control.set_capture_mode(child, 'WindowsGraphicsCaptureV2', 1, readback_mode='poll_single_v1')
                mutation.assert_not_called()

    def test_invalid_typed_selection_rejects_before_mutation(self):
        for mode, readback in [('BitBlt', 'blocking'), ('BitBlt', 'poll_single_v1'),
                              ('WindowsGraphicsCaptureV2', True), ('WindowsGraphicsCaptureV2', 'POLL_SINGLE_V1')]:
            with self.subTest(mode=mode, readback=readback), patch.object(control, 'mutate') as mutation:
                with self.assertRaises(control.ControlError):
                    control.set_capture_mode(self.child, mode, 1, readback_mode=readback)
                mutation.assert_not_called()

    def test_busy_child_rejects_new_option_without_stopping_runtime(self):
        for overrides in ({'taskRunning': True}, {'agentStreamRunning': True}):
            with self.subTest(overrides=overrides), patch.object(control, 'mutate') as mutation:
                with self.assertRaises(control.ControlError):
                    control.set_capture_mode({**self.child, **overrides}, 'WindowsGraphicsCaptureV2', 1,
                                             readback_mode='poll_single_v1')
                mutation.assert_not_called()

    def test_selection_waits_for_lifecycle_and_matches_actual_attachment(self):
        changing = {**self.child, 'automationState': 'changing_capture', 'taskRunning': True,
                    'configuredReadbackMode': 'poll_single_v1', 'effectiveReadbackMode': None}
        ready = {**self.child, 'configuredReadbackMode': 'poll_single_v1', 'effectiveReadbackMode': 'poll_single_v1'}
        with patch.object(control, 'mutate') as mutation, \
                patch.object(control, 'refresh', side_effect=[changing, ready]), patch.object(control.time, 'sleep'):
            self.assertEqual(control.set_capture_mode(self.child, 'WindowsGraphicsCaptureV2', 1,
                                                     readback_mode='poll_single_v1'), ready)
        mutation.assert_called_once_with('setCaptureMode', self.child, captureMode='WindowsGraphicsCaptureV2',
                                         readbackMode='poll_single_v1')

    def test_saved_mode_is_insufficient_without_matching_effective_mode(self):
        ready = {**self.child, 'configuredReadbackMode': 'poll_single_v1', 'effectiveReadbackMode': 'poll_single_v1'}
        variants = [{**ready, key: value} for key, value in (
            ('configuredReadbackMode', 'blocking'), ('effectiveReadbackMode', 'blocking'),
            ('effectiveReadbackMode', None), ('readbackVersion', 2), ('readbackModes', ['blocking']))]
        for current in variants:
            with self.subTest(current=current), patch.object(control, 'mutate') as mutation, \
                    patch.object(control, 'refresh', return_value=current):
                with self.assertRaises(control.ControlError):
                    control.set_capture_mode(self.child, 'WindowsGraphicsCaptureV2', 1, readback_mode='poll_single_v1')
                self.assertEqual(mutation.call_count, 1)

    def test_omission_selects_and_verifies_blocking_on_new_server(self):
        current = {**self.child, 'configuredReadbackMode': 'poll_single_v1', 'effectiveReadbackMode': 'poll_single_v1'}
        with patch.object(control, 'mutate') as mutation, patch.object(control, 'refresh', return_value=self.child):
            self.assertEqual(control.set_capture_mode(current, 'WindowsGraphicsCaptureV2', 1), self.child)
        mutation.assert_called_once_with('setCaptureMode', current, captureMode='WindowsGraphicsCaptureV2')

    def test_legacy_server_keeps_omitted_wire_and_existing_completion_checks(self):
        child = {k: v for k, v in self.child.items() if k not in
                 ('readbackVersion', 'readbackModes', 'configuredReadbackMode', 'effectiveReadbackMode')}
        with patch.object(control, 'mutate') as mutation, patch.object(control, 'refresh', return_value=child):
            self.assertEqual(control.set_capture_mode(child, 'WindowsGraphicsCaptureV2', 1), child)
        mutation.assert_called_once_with('setCaptureMode', child, captureMode='WindowsGraphicsCaptureV2')

    def test_other_backend_requires_no_effective_readback_and_resets_saved_default(self):
        ready = {**self.child, 'captureMode': 'BitBlt', 'effectiveReadbackMode': None}
        with patch.object(control, 'mutate') as mutation, patch.object(control, 'refresh', return_value=ready):
            self.assertEqual(control.set_capture_mode(self.child, 'BitBlt', 1), ready)
        mutation.assert_called_once_with('setCaptureMode', self.child, captureMode='BitBlt')

    def test_uncertain_ack_is_never_replayed_or_followed_by_success(self):
        with patch.object(control, 'mutate', side_effect=control.ControlError('uncertain acknowledgment')) as mutation, \
                patch.object(control, 'refresh') as refresh:
            with self.assertRaises(control.ControlError):
                control.set_capture_mode(self.child, 'WindowsGraphicsCaptureV2', 1, readback_mode='poll_single_v1')
        self.assertEqual(mutation.call_count, 1)
        refresh.assert_not_called()

    def test_cli_passes_explicit_mode_to_pinned_child(self):
        with patch.object(sys, 'argv', ['rdp_control.py', 'set-capture-mode', '--mode', 'WindowsGraphicsCaptureV2',
                                       '--readback-mode', 'poll_single_v1']), \
                patch.object(sys, 'stdout', io.StringIO()), \
                patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                patch.object(control, 'set_capture_mode', return_value=self.child) as switch:
            self.assertEqual(control.main(), 0)
        switch.assert_called_once_with(self.child, 'WindowsGraphicsCaptureV2', 120, readback_mode='poll_single_v1')


if __name__ == '__main__':
    unittest.main()
