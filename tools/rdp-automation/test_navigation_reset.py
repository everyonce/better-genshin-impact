"""Fixed navigation-reset protocol and polling tests; all peers are synthetic."""
import io
import copy
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

    def diagnostic_status(self, state='completed', count=3):
        """Build a pinned terminal operation and its separately requested bounded evidence."""
        terminal = self.status(state, run_id='0123456789abcdef0123456789abcdef',
                               verificationDiagnosticsVersion=1, finishedAtUtc='2026-10-23T23:01:00Z')
        if state != 'completed':
            terminal['navigationReset']['error'] = 'pose_not_settled' if state == 'failed' else 'reset_cancelled'
        sample = self.status('completed')['navigationReset']['samples'][0]
        diagnostics = [{'attempt': index + 1, 'sample': {**sample, 'sourceFrameId': index},
                        'candidateCount': min(index + 1, 3), 'reason': 'position_spread_exceeded',
                        'maximumPositionSpread': 2.0, 'maximumYawSpreadDegrees': 0.0,
                        'minimumAcquisitionGapMs': 120.0, 'targetYawErrorDegrees': 0.0}
                       for index in range(count)]
        full = {**terminal, 'navigationReset': {**terminal['navigationReset'], 'verificationDiagnostics': diagnostics}}
        return terminal, full

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

    def test_diagnostics_wire_pins_run_and_allows_only_its_larger_response(self):
        terminal, full = self.diagnostic_status()
        full['testPadding'] = 'x' * 9000
        api = FakePipe(full)
        api.session = 3
        result = control.exchange('navigationResetDiagnostics', 123, 3, nonce='child-epoch',
                                  fields={'navigationResetRunId': terminal['navigationReset']['runId']}, api=api)
        self.assertEqual(result, full)
        self.assertEqual(api.request['targetNonce'], 'child-epoch')
        self.assertEqual(api.request['targetProcessId'], 123)
        self.assertEqual(api.request['targetWindowsSessionId'], 3)
        self.assertEqual(api.request['navigationResetRunId'], terminal['navigationReset']['runId'])
        self.assertLess(len(api.written[0]), control.MAX_MESSAGE)
        self.assertTrue(api.closed)
        api = FakePipe(full)
        api.session = 3
        with self.assertRaisesRegex(control.ControlError, 'size limit'):
            control.exchange('status', 123, 3, api=api)
        self.assertTrue(api.closed)

    def test_diagnostics_response_above_32k_is_rejected_and_pipe_closed(self):
        terminal, full = self.diagnostic_status()
        api = FakePipe({**full, 'testPadding': 'x' * 32768})
        api.session = 3
        with self.assertRaisesRegex(control.ControlError, 'size limit'):
            control.exchange('navigationResetDiagnostics', 123, 3, nonce='child-epoch',
                             fields={'navigationResetRunId': terminal['navigationReset']['runId']}, api=api)
        self.assertTrue(api.closed)

    def test_diagnostics_requires_exact_run_fields_and_nonce_before_connecting(self):
        valid = '0123456789abcdef0123456789abcdef'
        invalid = [None, True, 123, '', 'new-run', 'g' * 32, '0' * 31, '0' * 32, '0' * 33,
                   '01234567-89ab-cdef-0123-456789abcdef']
        cases = [(dict(navigationResetRunId=value), 'child-epoch') for value in invalid]
        cases += [({}, 'child-epoch'), ({'navigationResetRunId': valid, 'targetYawDegrees': 0}, 'child-epoch'),
                  ({'navigationResetRunId': valid}, None)]
        for fields, nonce in cases:
            with self.subTest(fields=fields, nonce=nonce):
                api = FakePipe(self.child)
                with self.assertRaises(control.ControlError):
                    control.exchange('navigationResetDiagnostics', 123, 3, nonce=nonce, fields=fields, api=api)
                self.assertFalse(hasattr(api, 'pipe_name'))

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

    def test_capable_completed_run_fetches_once_after_cleanup_and_merges_only_evidence(self):
        terminal, full = self.diagnostic_status()
        full = {**full, 'automationState': 'later_unrelated_status'}
        pending_cleanup = {**terminal, 'taskRunning': True}
        with patch.object(control, 'mutate', return_value=pending_cleanup) as mutation, \
                patch.object(control, 'refresh', return_value=terminal) as refresh, \
                patch.object(control, 'exchange', return_value=full) as exchange:
            result = control.reset_navigation(self.child, 0, 1)
        expected = {**terminal, 'navigationReset': full['navigationReset']}
        self.assertEqual(result, expected)
        self.assertEqual(result['automationState'], 'game_ready')
        mutation.assert_called_once()
        refresh.assert_called_once()
        exchange.assert_called_once_with('navigationResetDiagnostics', 123, 3, nonce='child-epoch',
                                         fields={'navigationResetRunId': terminal['navigationReset']['runId']})

    def test_legacy_terminal_results_never_fetch_diagnostics_and_failures_retain_status(self):
        for state in ('completed', 'failed', 'cancelled'):
            terminal = self.status(state, error=None if state == 'completed' else 'legacy failure')
            with self.subTest(state=state), patch.object(control, 'mutate', return_value=terminal), \
                    patch.object(control, 'exchange') as exchange:
                if state == 'completed':
                    self.assertEqual(control.reset_navigation(self.child, 0, 1), terminal)
                else:
                    with self.assertRaises(control.NavigationResetError) as failure:
                        control.reset_navigation(self.child, 0, 1)
                    self.assertEqual(failure.exception.status, terminal)
                exchange.assert_not_called()

    def test_failed_and_cancelled_runs_preserve_full_evidence_without_restarting(self):
        for state in ('failed', 'cancelled'):
            terminal, full = self.diagnostic_status(state, count=15)
            with self.subTest(state=state), patch.object(control, 'mutate', return_value=terminal) as mutation, \
                    patch.object(control, 'exchange', return_value=full) as exchange, \
                    patch.object(control, 'refresh') as refresh:
                with self.assertRaises(control.NavigationResetError) as failure:
                    control.reset_navigation(self.child, 0, 1)
                self.assertEqual(failure.exception.status, full)
                self.assertIn(terminal['navigationReset']['error'], str(failure.exception))
                mutation.assert_called_once()
                exchange.assert_called_once()
                refresh.assert_not_called()

    def test_failed_or_cancelled_diagnostics_wait_for_owner_cleanup_before_single_fetch(self):
        for state in ('failed', 'cancelled'):
            terminal, full = self.diagnostic_status(state, count=15)
            before_cleanup = {**terminal, 'taskRunning': True}
            with self.subTest(state=state), patch.object(control, 'mutate', return_value=before_cleanup) as mutation, \
                    patch.object(control, 'refresh', side_effect=[before_cleanup, terminal]) as refresh, \
                    patch.object(control, 'exchange', return_value=full) as exchange, \
                    patch.object(control.time, 'sleep'):
                with self.assertRaises(control.NavigationResetError) as failure:
                    control.reset_navigation(self.child, 0, 1)
                self.assertEqual(failure.exception.status, full)
                self.assertEqual(refresh.call_count, 2)
                exchange.assert_called_once()
                mutation.assert_called_once()

    def test_diagnostics_must_match_full_terminal_identity_and_result(self):
        terminal, full = self.diagnostic_status()
        changes = [{'processId': 456}, {'windowsSessionId': 4}, {'instanceNonce': 'new-instance'},
                   {'instanceType': 'Primary'}]
        replies = [{**full, **change} for change in changes]
        for field, value in [('runId', 'f' * 32), ('state', 'failed'), ('phase', 'other'),
                             ('error', 'changed'), ('targetYawDegrees', 90), ('samples', []),
                             ('profileId', 'other'), ('finishedAtUtc', '2026-10-23T23:02:00Z'),
                             ('verificationDiagnosticsVersion', 2), ('verificationDiagnosticsVersion', True)]:
            replies.append({**full, 'navigationReset': {**full['navigationReset'], field: value}})
        for reply in replies:
            with self.subTest(reply=reply), patch.object(control, 'mutate', return_value=terminal), \
                    patch.object(control, 'exchange', return_value=reply) as exchange:
                with self.assertRaises(control.NavigationResetError) as failure:
                    control.reset_navigation(self.child, 0, 1)
                self.assertEqual(failure.exception.status, terminal)
                self.assertNotIn('verificationDiagnostics', failure.exception.status['navigationReset'])
                exchange.assert_called_once()

    def test_diagnostics_cap_and_shape_are_validated_without_discarding_terminal_failure(self):
        terminal, full = self.diagnostic_status('failed', count=15)
        invalid = [None, {}, full['navigationReset']['verificationDiagnostics'] + [{}], [{}],
                   [{**full['navigationReset']['verificationDiagnostics'][0], 'attempt': True}],
                   [{**full['navigationReset']['verificationDiagnostics'][0], 'reason': ''}],
                   [{**full['navigationReset']['verificationDiagnostics'][0], 'sample': None}]]
        for diagnostics in invalid:
            reply = {**full, 'navigationReset': {**full['navigationReset'], 'verificationDiagnostics': diagnostics}}
            with self.subTest(diagnostics=diagnostics), patch.object(control, 'mutate', return_value=terminal), \
                    patch.object(control, 'exchange', return_value=reply):
                with self.assertRaises(control.NavigationResetError) as failure:
                    control.reset_navigation(self.child, 0, 1)
                self.assertEqual(failure.exception.status, terminal)

    def test_diagnostics_read_failure_or_unsupported_version_is_not_retried(self):
        for state in ('completed', 'failed'):
            terminal, _ = self.diagnostic_status(state)
            for error in (control.ControlError('timed out'), OSError('closed')):
                with self.subTest(state=state, error=error), \
                        patch.object(control, 'mutate', return_value=terminal) as mutation, \
                        patch.object(control, 'exchange', side_effect=error) as exchange:
                    with self.assertRaises(control.NavigationResetError) as failure:
                        control.reset_navigation(self.child, 0, 1)
                    self.assertEqual(failure.exception.status, terminal)
                    exchange.assert_called_once()
                    mutation.assert_called_once()
        for version in (None, True, 2, '1'):
            terminal, _ = self.diagnostic_status()
            terminal['navigationReset']['verificationDiagnosticsVersion'] = version
            with self.subTest(version=version), patch.object(control, 'mutate', return_value=terminal), \
                    patch.object(control, 'exchange') as exchange:
                with self.assertRaises(control.NavigationResetError):
                    control.reset_navigation(self.child, 0, 1)
                exchange.assert_not_called()

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
            reset.assert_called_once_with(self.child, yaw, 120, 'shared')
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

    def test_cli_failure_json_retains_typed_terminal_diagnostics(self):
        _, full = self.diagnostic_status('failed', count=15)
        output = io.StringIO()
        with patch.object(sys, 'argv', ['rdp_control.py', 'reset-navigation']), \
                patch.object(sys, 'stderr', output), \
                patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                patch.object(control, 'reset_navigation', side_effect=control.NavigationResetError('pose_not_settled', full)):
            self.assertEqual(control.main(), 1)
        result = json.loads(output.getvalue())
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'pose_not_settled')
        self.assertEqual(result['status'], full)

    def with_capture_policy(self, status, policy='task_owned_timer'):
        """Advertise a synthetic current peer while retaining the legacy fixtures unchanged."""
        status = copy.deepcopy(status)
        status['navigationReset'].update(capturePolicies=['shared', 'task_owned_timer'], capturePolicy=policy)
        return status

    def test_reset_capture_policy_requires_supported_capability_before_mutation(self):
        for invalid in (None, True, '', 'exclusive', 'TASK_OWNED_TIMER'):
            with self.subTest(invalid=invalid), patch.object(control, 'mutate') as mutation:
                with self.assertRaises(control.ControlError):
                    control.reset_navigation(self.child, 0, 1, invalid)
                mutation.assert_not_called()
        for capabilities in (None, [], ['shared'], 'task_owned_timer', [True, 'task_owned_timer']):
            child = self.with_capture_policy(self.child)
            child['navigationReset']['capturePolicies'] = capabilities
            with self.subTest(capabilities=capabilities), patch.object(control, 'mutate') as mutation:
                with self.assertRaises(control.ControlError):
                    control.reset_navigation(child, 0, 1, 'task_owned_timer')
                mutation.assert_not_called()
        with patch.object(control, 'mutate') as mutation, self.assertRaises(control.ControlError):
            control.reset_navigation(self.child, 0, 1, 'task_owned_timer')
        mutation.assert_not_called()

    def test_capable_reset_sends_selected_policy_once_and_preserves_terminal_evidence(self):
        for policy in ('shared', 'task_owned_timer'):
            for state in ('completed', 'failed', 'cancelled'):
                child = self.with_capture_policy(self.child, 'shared')
                terminal, full = (self.with_capture_policy(value, policy) for value in self.diagnostic_status(state))
                with self.subTest(policy=policy, state=state), \
                        patch.object(control, 'mutate', return_value=terminal) as mutation, \
                        patch.object(control, 'exchange', return_value=full) as exchange, \
                        patch.object(control, 'refresh') as refresh:
                    if state == 'completed':
                        self.assertEqual(control.reset_navigation(child, 0, 1, policy), full)
                    else:
                        with self.assertRaises(control.NavigationResetError) as failure:
                            control.reset_navigation(child, 0, 1, policy)
                        self.assertEqual(failure.exception.status, full)
                    mutation.assert_called_once_with('startNavigationReset', child, targetYawDegrees=0, capturePolicy=policy)
                    exchange.assert_called_once()
                    refresh.assert_not_called()

    def test_reset_policy_and_capability_cannot_change_after_admission(self):
        child = self.with_capture_policy(self.child, 'shared')
        terminal, full = (self.with_capture_policy(value) for value in self.diagnostic_status())
        admitted = {**self.with_capture_policy(self.status()),
                    'navigationReset': {**terminal['navigationReset'], 'state': 'running'}}
        for phase in ('admission', 'poll', 'diagnostics'):
            for field, value in (('capturePolicy', None), ('capturePolicy', 'shared'),
                                 ('capturePolicies', None), ('capturePolicies', ['task_owned_timer'])):
                bad = copy.deepcopy(full if phase == 'diagnostics' else terminal)
                if value is None:
                    bad['navigationReset'].pop(field)
                else:
                    bad['navigationReset'][field] = value
                with self.subTest(phase=phase, field=field, value=value), \
                        patch.object(control, 'mutate', return_value=bad if phase == 'admission' else admitted), \
                        patch.object(control, 'refresh', return_value=bad if phase == 'poll' else terminal), \
                        patch.object(control, 'exchange', return_value=bad if phase == 'diagnostics' else full) as exchange:
                    with self.assertRaises(control.NavigationResetError) as failure:
                        control.reset_navigation(child, 0, 1, 'task_owned_timer')
                    self.assertEqual(failure.exception.status, terminal if phase == 'diagnostics' else bad)
                    if phase != 'diagnostics':
                        exchange.assert_not_called()

    def test_legacy_reset_cannot_echo_an_unrequested_isolated_policy(self):
        terminal = self.status('completed', capturePolicy='task_owned_timer')
        with patch.object(control, 'mutate', return_value=terminal), patch.object(control, 'exchange') as exchange:
            with self.assertRaises(control.NavigationResetError) as failure:
                control.reset_navigation(self.child, 0, 1)
        self.assertEqual(failure.exception.status, terminal)
        exchange.assert_not_called()

    def test_reset_wire_capture_policy_accepts_only_supported_field_subsets(self):
        for fields in ({}, {'targetYawDegrees': 0}, {'capturePolicy': 'shared'},
                       {'capturePolicy': 'task_owned_timer'},
                       {'targetYawDegrees': 123.5, 'capturePolicy': 'task_owned_timer'}):
            api = FakePipe(self.child); api.session = 3
            control.exchange('startNavigationReset', 123, 3, nonce='child-epoch', fields=fields, api=api)
            for field, value in fields.items():
                self.assertEqual(api.request[field], value)
        for fields in ({'capturePolicy': None}, {'capturePolicy': True}, {'capturePolicy': 'exclusive'},
                       {'capturePolicy': 'shared', 'timingContract': 'v3'}):
            api = FakePipe(self.child)
            with self.subTest(fields=fields), self.assertRaises(control.ControlError):
                control.exchange('startNavigationReset', 123, 3, nonce='child-epoch', fields=fields, api=api)
            self.assertFalse(hasattr(api, 'pipe_name'))

    def test_cli_reset_capture_policy_is_explicit_and_invalid_values_never_discover(self):
        with patch.object(sys, 'argv', ['rdp_control.py', 'reset-navigation', '--capture-policy', 'task_owned_timer']), \
                patch.object(sys, 'stdout', io.StringIO()), \
                patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                patch.object(control, 'reset_navigation', return_value={}) as reset:
            self.assertEqual(control.main(), 0)
        reset.assert_called_once_with(self.child, 0.0, 120, 'task_owned_timer')
        with patch.object(sys, 'argv', ['rdp_control.py', 'reset-navigation', '--capture-policy', 'exclusive']), \
                patch.object(sys, 'stderr', io.StringIO()), patch.object(control, 'discover') as discover:
            with self.assertRaises(SystemExit) as failure:
                control.main()
        self.assertEqual(failure.exception.code, 2)
        discover.assert_not_called()


if __name__ == '__main__':
    unittest.main()
