"""Desktop DC policy and lifecycle contracts using fake transport only."""
import io
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
from test_rdp_control import FakePipe


class DesktopDcCaptureTests(unittest.TestCase):
    """A selectable host snapshot must never inherit WGC source authority."""

    def setUp(self):
        """Pin an idle child and prohibit any accidental native pipe construction."""
        self.child = {
            'processId': 123, 'windowsSessionId': 3, 'instanceNonce': 'child-epoch',
            'instanceType': 'ChildSession', 'remoteDesktop': True, 'automationEnabled': True,
            'runtimeRunning': True, 'automationState': 'game_ready', 'taskRunning': False,
            'agentStreamRunning': False, 'captureMode': 'WindowsGraphicsCaptureV2',
            'readbackVersion': 1, 'readbackModes': ['blocking', 'poll_single_v1'],
            'configuredReadbackMode': 'poll_single_v1', 'effectiveReadbackMode': 'poll_single_v1',
            'captureOptionsVersion': 1, 'sourceRetentions': ['disabled', 'hold-until-readback-v1'],
            'conversionModes': ['gpu', 'cpu'], 'configuredSourceRetention': 'hold-until-readback-v1',
            'effectiveSourceRetention': 'hold-until-readback-v1', 'configuredConversion': 'cpu',
            'effectiveConversion': 'cpu', 'desktopDcSourcePolicyVersion': 1,
            'desktopDcSourcePolicies': ['observe-only', 'host-acquisition-v1'],
            'configuredDesktopDcSourcePolicy': 'observe-only', 'effectiveDesktopDcSourcePolicy': None,
        }
        forbidden = patch.object(control.transport, 'WinPipeApi', side_effect=AssertionError('Native transport forbidden'))
        forbidden.start()
        self.addCleanup(forbidden.stop)

    def selected(self, policy='host-acquisition-v1'):
        """Represent the exact completed Desktop DC attachment, retaining dormant WGC settings."""
        return {**self.child, 'captureMode': 'DesktopDc', 'configuredDesktopDcSourcePolicy': policy,
                'effectiveDesktopDcSourcePolicy': policy, 'effectiveReadbackMode': None,
                'effectiveSourceRetention': None, 'effectiveConversion': None}

    def changing(self, **values):
        """An accepted asynchronous change may still expose the prior settings."""
        return {**self.child, 'automationState': 'changing_capture', 'taskRunning': True, **values}

    def reject_before_mutation(self, child=None, mode='DesktopDc', **options):
        """Invalid choices must fail before any mutation or follow-up status read."""
        with patch.object(control, 'mutate') as mutation, patch.object(control, 'refresh') as refresh:
            with self.assertRaises(control.ControlError):
                control.set_capture_mode(self.child if child is None else child, mode, 1, **options)
            mutation.assert_not_called()
            refresh.assert_not_called()

    def test_exact_wire_names_and_omission_with_authenticated_nonce(self):
        for policy in (*control.DESKTOP_DC_SOURCE_POLICIES, control._CAPTURE_OPTION_UNSET):
            with self.subTest(policy=policy):
                api = FakePipe(self.child)
                api.session = 3
                fields = {'captureMode': 'DesktopDc'}
                if policy is not control._CAPTURE_OPTION_UNSET:
                    fields['desktopDcSourcePolicy'] = policy
                control.exchange('setCaptureMode', 123, 3, nonce='child-epoch', fields=fields, api=api)
                self.assertEqual(api.request['targetNonce'], 'child-epoch')
                self.assertEqual({key: api.request[key] for key in fields}, fields)
                self.assertEqual('desktopDcSourcePolicy' in api.request, policy is not control._CAPTURE_OPTION_UNSET)
                self.assertEqual(len(api.written), 1)

    def test_bad_policy_wrong_backend_and_unrelated_command_never_connect(self):
        invalid = [('setCaptureMode', {'captureMode': 'DesktopDc', 'desktopDcSourcePolicy': value})
                   for value in (None, True, False, 1, 1.0, [], {}, '', 'HostAcquisitionV1', 'host', 'disabled')]
        invalid += [('setCaptureMode', {'captureMode': mode, 'desktopDcSourcePolicy': 'observe-only'})
                    for mode in control.CAPTURE_MODES if mode != 'DesktopDc']
        invalid += [('status', {'desktopDcSourcePolicy': 'observe-only'}),
                    ('setCaptureMode', {'desktopDcSourcePolicy': 'observe-only'})]
        for command, fields in invalid:
            with self.subTest(command=command, fields=fields):
                api = FakePipe(self.child)
                api.session = 3
                with self.assertRaises(control.ControlError):
                    control.exchange(command, 123, 3, nonce='child-epoch', fields=fields, api=api)
                self.assertFalse(hasattr(api, 'pipe_name'))

    def test_wgc_options_cannot_be_used_as_desktop_options(self):
        for name, value in (('readbackMode', 'blocking'), ('sourceRetention', 'disabled'), ('conversion', 'cpu')):
            with self.subTest(name=name):
                api = FakePipe(self.child)
                with self.assertRaises(control.ControlError):
                    control.exchange('setCaptureMode', 123, 3, nonce='child-epoch', api=api,
                                     fields={'captureMode': 'DesktopDc', name: value})
                self.assertFalse(hasattr(api, 'pipe_name'))
        for options in ({'readback_mode': 'blocking'}, {'source_retention': 'disabled'}, {'conversion': 'cpu'}):
            self.reject_before_mutation(**options)

    def test_helper_null_alias_and_wrong_backend_are_rejected(self):
        for value in (None, True, 1, 1.0, [], {}, '', 'HostAcquisitionV1', 'host', 'disabled'):
            with self.subTest(value=value):
                self.reject_before_mutation(desktop_dc_source_policy=value)
        for mode in control.CAPTURE_MODES:
            if mode != 'DesktopDc':
                self.reject_before_mutation(mode=mode, desktop_dc_source_policy='observe-only')

    def test_desktop_requires_capability_even_when_policy_omitted(self):
        legacy = {key: value for key, value in self.child.items() if 'DesktopDc' not in key and not key.startswith('desktopDc')}
        self.reject_before_mutation(legacy)
        self.reject_before_mutation(legacy, desktop_dc_source_policy='observe-only')
        self.reject_before_mutation({**legacy, 'captureMode': 'DesktopDc'}, mode='BitBlt')

    def test_capability_version_and_exact_list_reject_before_mutation(self):
        for version in (None, False, True, 0, 2, 1.0, '1'):
            self.reject_before_mutation({**self.child, 'desktopDcSourcePolicyVersion': version})
        for values in (None, (), [], 'observe-only', ['observe-only'], [1],
                       ['host-acquisition-v1', 'observe-only'], ['observe-only', 'observe-only'],
                       ['observe-only', 'host-acquisition-v1', 'future']):
            self.reject_before_mutation({**self.child, 'desktopDcSourcePolicies': values})

    def test_invalid_saved_policy_or_dormant_wgc_values_reject(self):
        for value in (None, True, 1, [], {}, '', 'future'):
            self.reject_before_mutation({**self.child, 'configuredDesktopDcSourcePolicy': value})
        for key in ('readbackVersion', 'captureOptionsVersion', 'configuredReadbackMode',
                    'configuredConversion', 'configuredSourceRetention'):
            self.reject_before_mutation({k: v for k, v in self.child.items() if k != key})
        self.reject_before_mutation({**self.child, 'configuredReadbackMode': 'future',
                                    'readbackModes': ['blocking', 'poll_single_v1', 'future']})

    def test_explicit_policy_waits_for_actual_attachment_and_preserves_wgc(self):
        ready = self.selected()
        pending = self.changing(configuredDesktopDcSourcePolicy='host-acquisition-v1')
        with patch.object(control, 'mutate', return_value=self.changing()) as mutation, \
                patch.object(control, 'refresh', side_effect=[pending, ready]), patch.object(control.time, 'sleep'):
            self.assertEqual(control.set_capture_mode(self.child, 'DesktopDc', 1,
                                                     desktop_dc_source_policy='host-acquisition-v1'), ready)
        mutation.assert_called_once_with('setCaptureMode', self.child, captureMode='DesktopDc',
                                         desktopDcSourcePolicy='host-acquisition-v1')
        for field in ('configuredReadbackMode', 'configuredSourceRetention', 'configuredConversion'):
            self.assertEqual(ready[field], self.child[field])

    def test_omitted_policy_preserves_both_saved_choices_and_absent_wire(self):
        for policy in control.DESKTOP_DC_SOURCE_POLICIES:
            child = {**self.child, 'configuredDesktopDcSourcePolicy': policy}
            ready = self.selected(policy)
            with patch.object(control, 'mutate', return_value=ready) as mutation, \
                    patch.object(control, 'refresh', return_value=ready):
                self.assertEqual(control.set_capture_mode(child, 'DesktopDc', 1), ready)
            mutation.assert_called_once_with('setCaptureMode', child, captureMode='DesktopDc')

    def test_switch_away_retains_policy_and_legacy_readback_default(self):
        child = self.selected()
        for mode in ('BitBlt', 'WindowsGraphicsCaptureV2'):
            ready = {**self.child, 'captureMode': mode, 'configuredReadbackMode': 'blocking',
                     'configuredDesktopDcSourcePolicy': 'host-acquisition-v1'}
            for key, value in (('effectiveReadbackMode', 'blocking'),
                               ('effectiveSourceRetention', 'hold-until-readback-v1'), ('effectiveConversion', 'cpu')):
                ready[key] = value if mode == 'WindowsGraphicsCaptureV2' else None
            with patch.object(control, 'mutate', return_value=ready) as mutation, \
                    patch.object(control, 'refresh', return_value=ready):
                self.assertEqual(control.set_capture_mode(child, mode, 1), ready)
            mutation.assert_called_once_with('setCaptureMode', child, captureMode=mode)

    def test_ack_capability_policy_and_failure_are_checked_before_refresh(self):
        invalid = [None, {}, self.changing(desktopDcSourcePolicyVersion=1.0),
                   self.changing(desktopDcSourcePolicies=['observe-only']),
                   self.changing(configuredDesktopDcSourcePolicy='future'),
                   self.changing(effectiveDesktopDcSourcePolicy='future'),
                   self.changing(automationState='failed', automationError='attach failed'),
                   self.changing(agentStreamRunning=True), self.selected('observe-only')]
        for acknowledgment in invalid:
            with self.subTest(acknowledgment=acknowledgment), \
                    patch.object(control, 'mutate', return_value=acknowledgment) as mutation, \
                    patch.object(control, 'refresh') as refresh:
                with self.assertRaises(control.ControlError):
                    control.set_capture_mode(self.child, 'DesktopDc', 1, desktop_dc_source_policy='host-acquisition-v1')
                self.assertEqual(mutation.call_count, 1)
                refresh.assert_not_called()

    def test_producer_degraded_ack_and_poll_only_allow_bounded_read_only_wait(self):
        # ExternalControlStatusCollector.Unavailable returns its non-UI baseline,
        # not an old ready snapshot: configured/effective settings are absent.
        for state in ('timeout', 'cancelled', 'unavailable', 'failed'):
            degraded = {key: value for key, value in self.child.items()
                        if not key.startswith(('configured', 'effective'))}
            degraded.update(uiStatus=state, automationState='unresponsive', runtimeRunning=False,
                            taskRunning=True, captureMode='')
            with self.subTest(uiStatus=state), \
                    patch.object(control, 'mutate', return_value=degraded) as mutation, \
                    patch.object(control, 'refresh', side_effect=[degraded, self.selected()]) as refresh, \
                    patch.object(control.time, 'sleep'):
                self.assertEqual(control.set_capture_mode(self.child, 'DesktopDc', 1,
                                 desktop_dc_source_policy='host-acquisition-v1'), self.selected())
                self.assertEqual(mutation.call_count, 1)
                self.assertEqual(refresh.call_count, 2)

    def test_malformed_degraded_ack_cannot_hide_policy_or_authority(self):
        degraded = {key: value for key, value in self.child.items()
                    if not key.startswith(('configured', 'effective'))}
        degraded.update(uiStatus='timeout', automationState='unresponsive', runtimeRunning=False,
                        taskRunning=True, captureMode='')
        for key, value in (('runtimeRunning', True), ('taskRunning', False), ('captureMode', 'DesktopDc'),
                           ('uiStatus', 'current'), ('configuredDesktopDcSourcePolicy', 'host-acquisition-v1'),
                           ('effectiveReadbackMode', 'poll_single_v1'), ('desktopDcSourcePolicyVersion', 1.0),
                           ('agentStreamRunning', True)):
            with self.subTest(key=key), \
                    patch.object(control, 'mutate', return_value={**degraded, key: value}) as mutation, \
                    patch.object(control, 'refresh') as refresh:
                with self.assertRaises(control.ControlError):
                    control.set_capture_mode(self.child, 'DesktopDc', 1)
                self.assertEqual(mutation.call_count, 1)
                refresh.assert_not_called()

    def test_capability_changes_during_pending_or_terminal_stop_without_replay(self):
        for current in (self.changing(), self.selected()):
            for key, value in (('desktopDcSourcePolicyVersion', 2), ('desktopDcSourcePolicyVersion', 1.0),
                               ('desktopDcSourcePolicies', ['observe-only']), ('captureOptionsVersion', 2),
                               ('readbackVersion', True), ('readbackModes', ['blocking']),
                               ('configuredDesktopDcSourcePolicy', None), ('agentStreamRunning', True)):
                with self.subTest(phase=current['automationState'], key=key, value=value), \
                        patch.object(control, 'mutate', return_value=self.changing()) as mutation, \
                        patch.object(control, 'refresh', return_value={**current, key: value}) as refresh:
                    with self.assertRaises(control.ControlError):
                        control.set_capture_mode(self.child, 'DesktopDc', 1, desktop_dc_source_policy='host-acquisition-v1')
                    self.assertEqual(mutation.call_count, 1)
                    self.assertEqual(refresh.call_count, 1)

    def test_completed_selection_must_match_policy_and_all_wgc_fields(self):
        for key, value in (('captureMode', 'BitBlt'), ('configuredDesktopDcSourcePolicy', 'observe-only'),
                           ('effectiveDesktopDcSourcePolicy', None), ('effectiveDesktopDcSourcePolicy', 'observe-only'),
                           ('configuredReadbackMode', 'blocking'), ('effectiveReadbackMode', 'poll_single_v1'),
                           ('configuredSourceRetention', 'disabled'), ('effectiveSourceRetention', 'hold-until-readback-v1'),
                           ('configuredConversion', 'gpu'), ('effectiveConversion', 'cpu')):
            with self.subTest(key=key), patch.object(control, 'mutate', return_value=self.changing()) as mutation, \
                    patch.object(control, 'refresh', return_value={**self.selected(), key: value}):
                with self.assertRaises(control.ControlError):
                    control.set_capture_mode(self.child, 'DesktopDc', 1, desktop_dc_source_policy='host-acquisition-v1')
                self.assertEqual(mutation.call_count, 1)

    def test_uncertain_ack_and_timeout_never_replay(self):
        with patch.object(control, 'mutate', side_effect=control.ControlError('uncertain acknowledgment')) as mutation, \
                patch.object(control, 'refresh') as refresh:
            with self.assertRaises(control.ControlError):
                control.set_capture_mode(self.child, 'DesktopDc', 1)
            mutation.assert_called_once()
            refresh.assert_not_called()
        with patch.object(control, 'mutate', return_value=self.changing()) as mutation, \
                patch.object(control, 'refresh', return_value=self.changing()), \
                patch.object(control.time, 'monotonic', side_effect=[0, 2]):
            with self.assertRaisesRegex(control.ControlError, 'Timed out'):
                control.set_capture_mode(self.child, 'DesktopDc', 1)
            mutation.assert_called_once()

    def test_existing_role_idle_and_nonce_guards_remain(self):
        for key, value in (('instanceType', 'Primary'), ('remoteDesktop', False), ('automationEnabled', False),
                           ('taskRunning', True), ('agentStreamRunning', True)):
            self.reject_before_mutation({**self.child, key: value})
        api = FakePipe({**self.selected(), 'instanceNonce': 'changed'})
        api.session = 3
        with self.assertRaises(control.ControlError):
            control.exchange('setCaptureMode', 123, 3, nonce='child-epoch', fields={'captureMode': 'DesktopDc'}, api=api)
        self.assertEqual(len(api.written), 1)

    def test_cli_supplied_policy_and_omitted_call_shape(self):
        for policy in (None, *control.DESKTOP_DC_SOURCE_POLICIES):
            argv = ['rdp_control.py', 'set-capture-mode', '--mode', 'DesktopDc']
            options = {}
            if policy is not None:
                argv += ['--desktop-dc-source-policy', policy]
                options['desktop_dc_source_policy'] = policy
            with patch.object(sys, 'argv', argv), patch.object(sys, 'stdout', io.StringIO()), \
                    patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                    patch.object(control, 'set_capture_mode', return_value=self.selected()) as switch:
                self.assertEqual(control.main(), 0)
            switch.assert_called_once_with(self.child, 'DesktopDc', 120, **options)

    def test_cli_invalid_alias_never_discovers(self):
        with patch.object(sys, 'argv', ['rdp_control.py', 'set-capture-mode', '--mode', 'DesktopDc',
                                       '--desktop-dc-source-policy', 'host']), \
                patch.object(sys, 'stderr', io.StringIO()), patch.object(control, 'discover') as discover:
            with self.assertRaises(SystemExit):
                control.main()
            discover.assert_not_called()


if __name__ == '__main__':
    unittest.main()
