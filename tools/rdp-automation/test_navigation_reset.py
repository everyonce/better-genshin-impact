"""Fixed navigation-reset protocol and polling tests; all peers are synthetic."""
import io
import json
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
from test_rdp_control import FakePipe


class NavigationResetTests(unittest.TestCase):
    def setUp(self):
        self.child = {'processId': 123, 'windowsSessionId': 3, 'instanceNonce': 'child-epoch',
                      'instanceType': 'ChildSession', 'remoteDesktop': True, 'automationEnabled': True,
                      'runtimeRunning': True, 'automationState': 'game_ready', 'taskRunning': False,
                      'agentStreamRunning': False, 'navigationReset': {'runId': None, 'state': 'idle'}}

    def status(self, state='running', run_id='new-run', **fields):
        """Build an isolated server operation with additive result fields retained."""
        operation = {'runId': run_id, 'state': state, 'phase': state, 'error': None,
                     'profileId': 'mondstadt-city-10', 'targetYawDegrees': 0.0,
                     'samples': [{'x': 100.0, 'y': 200.0, 'yawDegrees': 0.0,
                                  'capturedAtUtc': '2026-10-23T23:00:00Z', 'sourceFrameId': index}
                                 for index in range(3)] if state == 'completed' else [], **fields}
        return {**self.child, 'taskRunning': state == 'running', 'navigationReset': operation}

    def test_wire_allows_optional_yaw_and_pins_identity(self):
        for fields in ({}, {'targetYawDegrees': 0}, {'targetYawDegrees': 359.999}):
            with self.subTest(fields=fields):
                api = FakePipe(self.child)
                api.session = 3
                control.exchange('startNavigationReset', 123, 3, nonce='child-epoch', fields=fields, api=api)
                self.assertEqual(api.request['targetNonce'], 'child-epoch')
                self.assertEqual(api.request['targetProcessId'], 123)
                self.assertEqual(api.request['targetWindowsSessionId'], 3)
                self.assertEqual(api.request.get('targetYawDegrees'), fields.get('targetYawDegrees'))

    def test_invalid_yaw_or_extra_fields_never_connect(self):
        invalid = [True, False, None, '0', -0.01, 360, 10 ** 400,
                   float('nan'), float('inf'), -float('inf')]
        for fields in [*({'targetYawDegrees': value} for value in invalid),
                       {'targetYawDegrees': 0, 'profileId': 'other'}, {'runId': 'chosen'}]:
            with self.subTest(fields=fields):
                api = FakePipe(self.child)
                with self.assertRaises(control.ControlError):
                    control.exchange('startNavigationReset', 123, 3, nonce='child-epoch', fields=fields, api=api)
                self.assertFalse(hasattr(api, 'pipe_name'))

    def test_preflight_rejects_busy_or_unready_non_rdp_targets(self):
        overrides = [{'instanceType': 'Primary'}, {'remoteDesktop': False}, {'automationEnabled': False},
                     {'instanceNonce': ''}, {'runtimeRunning': False}, {'automationState': 'starting_game'},
                     {'automationState': 'failed'}, {'taskRunning': True}, {'taskRunning': None},
                     {'agentStreamRunning': True}, {'agentStreamRunning': None},
                     {'navigationReset': {'runId': 'other', 'state': 'running'}}]
        for changed in overrides:
            with self.subTest(changed=changed), patch.object(control, 'mutate') as mutation:
                with self.assertRaises(control.ControlError):
                    control.reset_navigation({**self.child, **changed}, 0, 1)
                mutation.assert_not_called()

    def test_single_start_waits_for_server_result_and_cleanup(self):
        admitted = self.status()
        result = self.status('completed')
        before_cleanup = {**result, 'taskRunning': True}
        with patch.object(control, 'mutate', return_value=admitted) as mutation, \
                patch.object(control, 'refresh', side_effect=[admitted, before_cleanup, result]) as refresh, \
                patch.object(control.time, 'sleep'):
            self.assertEqual(control.reset_navigation(self.child, 0, 1), result)
        mutation.assert_called_once_with('startNavigationReset', self.child, targetYawDegrees=0)
        self.assertEqual(refresh.call_count, 3)
        self.assertIn('sourceFrameId', result['navigationReset']['samples'][0])

    def test_completed_admission_can_return_without_extra_poll(self):
        result = self.status('completed', targetYawDegrees=123.5)
        with patch.object(control, 'mutate', return_value=result), patch.object(control, 'refresh') as refresh:
            self.assertEqual(control.reset_navigation(self.child, 123.5, 1), result)
        refresh.assert_not_called()

    def test_prior_completed_run_does_not_prevent_a_new_unique_run(self):
        previous = self.status('completed', run_id='old-run')
        completed = self.status('completed')
        with patch.object(control, 'mutate', return_value=completed) as mutation:
            self.assertEqual(control.reset_navigation(previous, 0, 1), completed)
        self.assertEqual(mutation.call_count, 1)

    def test_admission_requires_new_run_id_and_running_or_completed_state(self):
        previous = self.status('completed', run_id='old-run')
        for response in (self.child, self.status(run_id=''), self.status(run_id='old-run'),
                         self.status('idle'), {**self.child, 'navigationReset': None}):
            with self.subTest(response=response), patch.object(control, 'mutate', return_value=response) as mutation, \
                    patch.object(control, 'refresh') as refresh:
                with self.assertRaises(control.ControlError):
                    control.reset_navigation(previous, 0, 1)
                mutation.assert_called_once()
                refresh.assert_not_called()

    def test_poll_fails_closed_on_failure_cancel_idle_replacement_or_wrong_profile(self):
        responses = [self.status('failed', error='local match failed'), self.status('cancelled'),
                     self.status('idle'), self.status('completed', run_id='replacement'),
                     self.status('completed', profileId='different'),
                     self.status('completed', targetYawDegrees=90)]
        for response in responses:
            with self.subTest(response=response), patch.object(control, 'mutate', return_value=self.status()) as mutation, \
                    patch.object(control, 'refresh', return_value=response):
                with self.assertRaises(control.ControlError):
                    control.reset_navigation(self.child, 0, 1)
                mutation.assert_called_once()

    def test_same_run_id_cannot_cross_process_session_or_nonce(self):
        for changes in ({'processId': 456}, {'windowsSessionId': 4}, {'instanceNonce': 'restarted'}):
            response = {**self.status('completed'), **changes}
            with self.subTest(changes=changes), patch.object(control, 'mutate', return_value=self.status()), \
                    patch.object(control, 'exchange', return_value=response):
                with self.assertRaisesRegex(control.ControlError, 'instance changed'):
                    control.reset_navigation(self.child, 0, 1)

    def test_completed_requires_three_finite_server_observations(self):
        samples = self.status('completed')['navigationReset']['samples']
        invalid = [None, [], samples[:2], samples + samples[:1],
                   [{**samples[0], 'x': float('nan')}, *samples[1:]],
                   [{**samples[0], 'y': True}, *samples[1:]],
                   [{**samples[0], 'yawDegrees': '0'}, *samples[1:]],
                   [{**samples[0], 'capturedAtUtc': None}, *samples[1:]]]
        for value in invalid:
            with self.subTest(value=value), patch.object(control, 'mutate', return_value=self.status()), \
                    patch.object(control, 'refresh', return_value=self.status('completed', samples=value)):
                with self.assertRaises(control.ControlError):
                    control.reset_navigation(self.child, 0, 1)

    def test_ambiguous_start_failure_is_not_replayed_or_joined(self):
        for error in (control.ControlError('response timed out'), OSError('pipe closed')):
            with self.subTest(error=error), patch.object(control, 'mutate', side_effect=error) as mutation, \
                    patch.object(control, 'refresh') as refresh:
                with self.assertRaises(type(error)):
                    control.reset_navigation(self.child, 0, 1)
                mutation.assert_called_once()
                refresh.assert_not_called()

    def test_timeout_does_not_restart_or_cancel_server_work(self):
        with patch.object(control, 'mutate', return_value=self.status()) as mutation, \
                patch.object(control, 'refresh', return_value=self.status()), \
                patch.object(control.time, 'monotonic', side_effect=[0.0, 2.0]):
            with self.assertRaisesRegex(control.ControlError, 'Timed out'):
                control.reset_navigation(self.child, 0, 1)
        mutation.assert_called_once_with('startNavigationReset', self.child, targetYawDegrees=0)

    def test_cli_selects_child_default_yaw_and_preserves_final_result(self):
        root = {**self.child, 'instanceType': 'Primary'}
        for arguments, yaw in (([], 0.0), (['--yaw-degrees', '123.5'], 123.5)):
            output = io.StringIO()
            result = self.status('completed', targetYawDegrees=yaw)
            with self.subTest(arguments=arguments), \
                    patch.object(sys, 'argv', ['rdp_control.py', 'reset-navigation', *arguments]), \
                    patch.object(sys, 'stdout', output), \
                    patch.object(control, 'discover', return_value={'instances': [root, self.child]}), \
                    patch.object(control, 'reset_navigation', return_value=result) as reset:
                self.assertEqual(control.main(), 0)
            reset.assert_called_once_with(self.child, yaw, 120)
            self.assertEqual(json.loads(output.getvalue()), result)

    def test_cli_rejects_invalid_yaw_before_any_target_lookup(self):
        for value in ('nan', 'inf', '-inf', '-1', '360', 'text'):
            with self.subTest(value=value), \
                    patch.object(sys, 'argv', ['rdp_control.py', 'reset-navigation', '--yaw-degrees=' + value]), \
                    patch.object(sys, 'stderr', io.StringIO()), \
                    patch.object(control, 'discover') as discovery, patch.object(control, 'exchange') as exchange:
                with self.assertRaises(SystemExit) as result:
                    control.main()
                self.assertEqual(result.exception.code, 2)
                discovery.assert_not_called()
                exchange.assert_not_called()


if __name__ == '__main__':
    unittest.main()
