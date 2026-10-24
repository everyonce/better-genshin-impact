"""Mocked startup recovery only: no named pipes, applications or RDP operations."""
import contextlib
import io
import itertools
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
from test_rdp_control import FakePipe


class StartRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = {'processId': 123, 'windowsSessionId': 2, 'instanceNonce': 'root',
                     'instanceType': 'Primary', 'automationEnabled': True, 'uiStatus': 'current',
                     'automationState': 'child_launch_dispatched', 'childSessionId': 3,
                     'childConnectedState': 1, 'childWindowMinimized': True}
        self.child = {'processId': 456, 'windowsSessionId': 3, 'instanceNonce': 'child',
                      'instanceType': 'ChildSession', 'automationEnabled': True, 'remoteDesktop': True,
                      'rootProcessId': 123, 'runtimeRunning': False, 'automationState': 'starting_game'}

    def arrange(self, roots=None, discoveries=None, mutation_error=None):
        """Repeat the last state and use a finite virtual deadline, never real transport."""
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        roots = roots or [self.root]
        discoveries = discoveries or [{'instances': [self.child], 'unavailable': []}]
        stack.enter_context(patch.object(control, 'refresh', side_effect=itertools.chain(roots, itertools.repeat(roots[-1]))))
        stack.enter_context(patch.object(control, 'discover', side_effect=itertools.chain(discoveries, itertools.repeat(discoveries[-1]))))
        stack.enter_context(patch.object(control.time, 'monotonic', side_effect=itertools.count(0, .1)))
        stack.enter_context(patch.object(control.time, 'sleep'))
        return stack.enter_context(patch.object(control, 'mutate', side_effect=mutation_error))

    def test_completed_dispatch_with_missing_child_recovers_once(self):
        mutation = self.arrange(discoveries=[{'instances': []}, {'instances': []}, {'instances': [self.child]}])
        result = control.start_child(self.root, 1)
        mutation.assert_called_once_with('startChildSession', self.root)
        self.assertTrue(result['childStartDispatched'])
        self.assertTrue(result['rootReady'])
        self.assertTrue(result['childReady'])
        self.assertFalse(result['gameReady'])
        self.assertEqual(result['child']['processId'], 456)

    def test_existing_ready_child_reuses_without_start_and_reports_game_readiness(self):
        ready = {**self.child, 'runtimeRunning': True, 'automationState': 'game_ready'}
        mutation = self.arrange(discoveries=[{'instances': [ready]}])
        result = control.start_child(self.root, 1)
        mutation.assert_not_called()
        self.assertFalse(result['childStartDispatched'])
        self.assertTrue(result['gameReady'])

    def test_partial_runtime_attachment_is_not_reported_as_game_ready(self):
        mutation = self.arrange(discoveries=[{'instances': [{**self.child, 'runtimeRunning': True}]}])
        self.assertFalse(control.start_child(self.root, 1)['gameReady'])
        mutation.assert_not_called()

    def test_joined_active_launch_is_not_redispatched_after_completed_dispatch(self):
        active = {**self.root, 'automationState': 'launching_child'}
        mutation = self.arrange(roots=[active, self.root], discoveries=[{'instances': []}])
        with self.assertRaisesRegex(control.ControlError, 'timed out'):
            control.start_child(active, 1)
        mutation.assert_not_called()

    def test_active_launch_observed_in_initial_status_is_joined_after_poll_advances(self):
        active = {**self.root, 'automationState': 'connecting'}
        mutation = self.arrange(discoveries=[{'instances': []}, {'instances': [self.child]}])
        control.start_child(active, 1)
        mutation.assert_not_called()

    def test_joined_launch_failure_is_reported_without_recovery_replay(self):
        active = {**self.root, 'automationState': 'connecting'}
        failed = {**self.root, 'automationState': 'failed', 'automationError': 'authentication failed'}
        mutation = self.arrange(roots=[failed], discoveries=[{'instances': []}])
        with self.assertRaisesRegex(control.ControlError, 'authentication failed'):
            control.start_child(active, 1)
        mutation.assert_not_called()

    def test_ambiguous_ack_with_old_completed_state_does_not_replay(self):
        mutation = self.arrange(discoveries=[{'instances': []}], mutation_error=control.ControlError('response lost'))
        with self.assertRaisesRegex(control.ControlError, 'response lost'):
            control.start_child(self.root, 1)
        mutation.assert_called_once_with('startChildSession', self.root)

    def test_lost_ack_can_join_fresh_active_state_then_verified_child(self):
        active = {**self.root, 'automationState': 'launching_child'}
        mutation = self.arrange(roots=[self.root, active, self.root],
                                discoveries=[{'instances': []}, {'instances': []}, {'instances': [self.child]}],
                                mutation_error=control.ControlError('response lost'))
        result = control.start_child(self.root, 1)
        mutation.assert_called_once()
        self.assertTrue(result['childReady'])

    def test_unavailable_conflicting_and_legacy_children_never_authorize_recovery(self):
        cases = [({'instances': [], 'unavailable': [{'windowsSessionId': 3}]}, 'unavailable'),
                 ({'instances': [], 'unavailable': [{'error': 'Discovery reached its time limit'}]}, 'unavailable'),
                 ({'instances': [self.child, self.child]}, 'Multiple'),
                 ({'instances': [{**self.child, 'rootProcessId': 999}]}, 'root identity'),
                 ({'instances': [{**self.child, 'instanceType': 'Normal'}]}, 'foreign'),
                 ({'instances': [{**self.child, 'rootProcessId': None}]}, 'legacy'),
                 ({'instances': [{**self.child, 'remoteDesktop': False}]}, 'actual RDP'),
                 ({'instances': [{**self.child, 'uiStatus': 'timeout'}]}, 'unavailable')]
        for discovery, reason in cases:
            with self.subTest(reason=reason), contextlib.ExitStack() as scope:
                scope.enter_context(patch.object(control, 'refresh', return_value=self.root))
                scope.enter_context(patch.object(control, 'discover', return_value=discovery))
                mutation = scope.enter_context(patch.object(control, 'mutate'))
                with self.assertRaisesRegex(control.ControlError, reason):
                    control.start_child(self.root, 1)
                mutation.assert_not_called()

    def test_degraded_root_status_never_authorizes_start(self):
        degraded = {**self.root, 'uiStatus': 'timeout', 'automationState': 'unresponsive'}
        mutation = self.arrange(roots=[degraded])
        with self.assertRaisesRegex(control.ControlError, 'unavailable'):
            control.start_child(self.root, 1)
        mutation.assert_not_called()

    def test_changed_root_nonce_is_rejected_by_real_refresh_logic(self):
        with patch.object(control, 'exchange', return_value={**self.root, 'instanceNonce': 'replacement'}), \
                patch.object(control, 'mutate') as mutation:
            with self.assertRaisesRegex(control.ControlError, 'instance changed'):
                control.start_child(self.root, 1)
            mutation.assert_not_called()

    def test_default_reuse_minimizes_once_and_waits_for_confirmation(self):
        shown = {**self.root, 'childWindowMinimized': False}
        mutation = self.arrange(roots=[shown, shown, self.root])
        result = control.start_child(shown, 1)
        mutation.assert_called_once_with('minimizeChildSession', shown)
        self.assertEqual(result['windowPolicy'], 'minimized')
        self.assertTrue(result['root']['childWindowMinimized'])

    def test_preserve_window_reuses_shown_child_without_any_mutation(self):
        shown = {**self.root, 'childWindowMinimized': False}
        mutation = self.arrange(roots=[shown])
        result = control.start_child(shown, 1, preserve_window=True)
        mutation.assert_not_called()
        self.assertFalse(result['root']['childWindowMinimized'])
        self.assertEqual(result['windowPolicy'], 'preserve_existing')

    def test_cli_preserve_option_is_forwarded_and_default_is_minimized(self):
        for extra, expected in (([], False), (['--preserve-window'], True)):
            with self.subTest(expected=expected), patch.object(sys, 'argv', ['rdp_control.py', 'start',
                    '--process-id', '123', '--windows-session-id', '2', *extra]), \
                    patch.object(control, 'exchange', return_value=self.root), \
                    patch.object(control, 'start_child', return_value={'childReady': True}) as start, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(control.main(), 0)
                start.assert_called_once_with(self.root, 120, expected)

    def test_endpoint_only_missing_child_refuses_old_or_malformed_capability_without_mutation(self):
        for capability in (None, 0, True, '1', 2):
            with self.subTest(capability=capability):
                self.root['childStartupIntentVersion'] = capability
                mutation = self.arrange(discoveries=[{'instances': []}])
                with self.assertRaisesRegex(control.ControlError, 'childStartupIntentVersion 1'):
                    control.start_child(self.root, 1, startup_mode='controlEndpoint')
                mutation.assert_not_called()

    def test_endpoint_dispatch_binds_intent_once_and_lost_ack_does_not_replay(self):
        self.root.update(childStartupIntentVersion=1, childStartupMode='controlEndpoint')
        active = {**self.root, 'automationState': 'connecting'}
        mutation = self.arrange(roots=[self.root, active, self.root],
                                discoveries=[{'instances': []}, {'instances': []}, {'instances': [self.child]}],
                                mutation_error=control.ControlError('response lost'))
        result = control.start_child(self.root, 1, startup_mode='controlEndpoint')
        mutation.assert_called_once_with('startChildSession', self.root, childStartupMode='controlEndpoint')
        self.assertTrue(result['childReady'])

    def test_game_joins_active_endpoint_bootstrap_without_dispatch(self):
        active = {**self.root, 'childStartupIntentVersion': 1, 'childStartupMode': 'controlEndpoint',
                  'automationState': 'connecting'}
        mutation = self.arrange(roots=[active, self.root], discoveries=[{'instances': []}, {'instances': [self.child]}])
        result = control.start_child(active, 1, startup_mode='gameRuntime')
        self.assertTrue(result['childReady'])
        mutation.assert_not_called()

    def test_host_refuses_active_game_or_unknown_intent_without_mutation(self):
        for mode in ('gameRuntime', None, 'unknown'):
            with self.subTest(mode=mode):
                active = {**self.root, 'childStartupIntentVersion': 1, 'childStartupMode': mode,
                          'automationState': 'connecting'}
                mutation = self.arrange(roots=[active], discoveries=[{'instances': []}])
                with self.assertRaisesRegex(control.ControlError, 'cannot join'):
                    control.start_child(active, 1, startup_mode='controlEndpoint')
                mutation.assert_not_called()

    def test_existing_child_reuse_needs_no_startup_capability(self):
        mutation = self.arrange()
        self.assertTrue(control.start_child(self.root, 1, startup_mode='controlEndpoint')['childReady'])
        mutation.assert_not_called()

    def test_child_start_wire_is_strict_and_omission_stays_legacy(self):
        for mode in ('controlEndpoint', 'gameRuntime'):
            api = FakePipe()
            control.exchange('startChildSession', 123, 2, nonce='instance-a', api=api,
                             fields={'childStartupMode': mode})
            self.assertEqual(api.request['childStartupMode'], mode)
            self.assertEqual(api.request['targetNonce'], 'instance-a')
        api = FakePipe()
        control.exchange('startChildSession', 123, 2, nonce='instance-a', api=api)
        self.assertNotIn('childStartupMode', api.request)
        for mode in (None, True, 1, [], 'ControlEndpoint', 'unknown'):
            api = FakePipe()
            with self.subTest(mode=mode), self.assertRaises(control.ControlError):
                control.exchange('startChildSession', 123, 2, nonce='instance-a', api=api,
                                 fields={'childStartupMode': mode})
            self.assertEqual(api.written, [])
        for command in ('status', 'startChildGame', 'minimizeChildSession'):
            api = FakePipe()
            with self.subTest(command=command), self.assertRaises(control.ControlError):
                control.exchange(command, 123, 2, nonce='instance-a', api=api,
                                 fields={'childStartupMode': 'controlEndpoint'})
            self.assertEqual(api.written, [])


if __name__ == '__main__':
    unittest.main()
