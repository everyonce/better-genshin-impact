"""Fixed native baseline protocol and lifecycle tests; all peers and poses are synthetic."""
import copy
import io
import json
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
from test_rdp_control import FakePipe


class NavigationBaselineTests(unittest.TestCase):
    RUN = '0123456789abcdef0123456789abcdef'

    def setUp(self):
        self.child = {'processId': 123, 'windowsSessionId': 3, 'instanceNonce': 'child-epoch',
                      'instanceType': 'ChildSession', 'remoteDesktop': True, 'automationEnabled': True,
                      'runtimeRunning': True, 'automationState': 'game_ready', 'taskRunning': False,
                      'agentStreamRunning': False, 'navigationBaseline': {'runId': None, 'state': 'idle',
                          'profileId': 'mondstadt-city-leg-1-v1', 'resultVersion': 1}}

    def status(self, state='running', **changes):
        """Return the compact owner snapshot independently from the measured result."""
        operation = {'runId': self.RUN, 'state': state, 'phase': state, 'error': None,
                     'profileId': 'mondstadt-city-leg-1-v1', 'gameProcessId': 456, 'windowsSessionId': 3,
                     'startedAtUtc': '2026-10-23T23:00:00Z',
                     'finishedAtUtc': None if state == 'running' else '2026-10-23T23:00:10Z',
                     'observationCount': 6, 'evidenceComplete': state == 'completed', 'resultVersion': 1,
                     **changes}
        return {**self.child, 'taskRunning': state == 'running', 'navigationBaseline': operation}

    def pose(self, number):
        """Source-tagged finite data exercises shape checks, not numerical game recognition."""
        return {'x': -874.3, 'y': 2274.2, 'yawDegrees': 90.0, 'capturedAtUtc': '2026-10-23T23:00:09Z',
                'sourceEpoch': 'fedcba9876543210fedcba9876543210', 'sourceTimestamp100ns': 1000000 + number * 800000,
                'acquiredAtStopwatchTicks': 10000 + number * 800, 'positionConfidence': 0.999,
                'yawConfidence': 0.9, 'layerId': 'City_102', 'sourceAgeMs': 12.0,
                'targetHeadingDegrees': 90.0, 'distanceToEnd': 0.1, 'projection': 9.8, 'crossTrack': 0.1,
                'motion': {'status': 'normal', 'method': 'native_key_tip_templates_v1',
                           'spaceKeyMatched': False, 'xKeyMatched': False, 'recognitionMs': 1.0}}

    def result(self, state='completed', **changes):
        """Retain final poses and artifact references without creating or reading those files."""
        terminal = self.status(state)
        samples = [self.pose(index) for index in range(3)]
        evidence = {'complete': state == 'completed'}
        for stem in ('journal', 'initialImage', 'finalImage'):
            evidence.update({stem + 'Path': f'User/NavigationBaselines/{self.RUN}/{stem}.fixture',
                             stem + 'Sha256': 'a' * 64})
        result = {'verified': state == 'completed', 'phase': 'verify', 'error': None,
                  'initialSample': self.pose(0), 'samples': samples if state == 'completed' else [],
                  'verificationSamples': samples, 'observationCount': 6, 'evidence': evidence,
                  'elapsedMs': 10000.0, 'inputReleaseError': None, **changes}
        return terminal, {**terminal, 'navigationBaseline': {**terminal['navigationBaseline'], 'result': result}}

    def test_wire_start_has_no_parameters_and_pins_child(self):
        api = FakePipe(self.status())
        api.session = 3
        control.exchange('startNavigationBaseline', 123, 3, nonce='child-epoch', api=api)
        self.assertEqual(api.request['targetNonce'], 'child-epoch')
        self.assertEqual(api.request['targetWindowsSessionId'], 3)
        self.assertNotIn('navigationBaselineRunId', api.request)
        self.assertTrue(api.closed)
        for fields in ({'route': 'other'}, {'targetYawDegrees': 0}, {'navigationBaselineRunId': self.RUN}):
            api = FakePipe(self.child)
            with self.subTest(fields=fields), self.assertRaises(control.ControlError):
                control.exchange('startNavigationBaseline', 123, 3, nonce='child-epoch', fields=fields, api=api)
            self.assertFalse(hasattr(api, 'pipe_name'))

    def test_result_query_alone_allows_32k_and_preserves_8k_requests_status_and_start(self):
        _, full = self.result()
        full['testPadding'] = 'x' * 9000
        api = FakePipe(full)
        api.session = 3
        self.assertEqual(control.exchange('navigationBaselineResult', 123, 3, nonce='child-epoch',
            fields={'navigationBaselineRunId': self.RUN}, api=api), full)
        self.assertEqual(api.request['navigationBaselineRunId'], self.RUN)
        self.assertEqual(api.request['targetProcessId'], 123)
        self.assertEqual(api.request['targetNonce'], 'child-epoch')
        self.assertLess(len(api.written[0]), control.MAX_MESSAGE)
        for command in ('status', 'startNavigationBaseline'):
            api = FakePipe(full)
            api.session = 3
            with self.subTest(command=command), self.assertRaisesRegex(control.ControlError, 'size limit'):
                control.exchange(command, 123, 3, nonce=None if command == 'status' else 'child-epoch', api=api)
            self.assertTrue(api.closed)
        api = FakePipe({**full, 'testPadding': 'x' * 32768})
        api.session = 3
        with self.assertRaisesRegex(control.ControlError, 'size limit'):
            control.exchange('navigationBaselineResult', 123, 3, nonce='child-epoch',
                             fields={'navigationBaselineRunId': self.RUN}, api=api)
        self.assertTrue(api.closed)

    def test_result_query_requires_nonzero_guid_and_exact_fields_before_connect(self):
        invalid = [None, True, 1, '', 'new-run', '0' * 32, 'g' * 32, 'a' * 31, 'a' * 33,
                   '01234567-89ab-cdef-0123-456789abcdef']
        cases = [({'navigationBaselineRunId': value}, 'child-epoch') for value in invalid]
        cases += [({}, 'child-epoch'), ({'navigationBaselineRunId': self.RUN, 'route': 'x'}, 'child-epoch'),
                  ({'navigationBaselineRunId': self.RUN}, None)]
        for fields, nonce in cases:
            api = FakePipe(self.child)
            with self.subTest(fields=fields), self.assertRaises(control.ControlError):
                control.exchange('navigationBaselineResult', 123, 3, nonce=nonce, fields=fields, api=api)
            self.assertFalse(hasattr(api, 'pipe_name'))

    def test_preflight_rejects_unready_busy_unsupported_or_non_rdp_targets(self):
        changes = [{'instanceType': 'Primary'}, {'remoteDesktop': False}, {'automationEnabled': False},
                   {'instanceNonce': ''}, {'runtimeRunning': False}, {'automationState': 'starting_game'},
                   {'taskRunning': True}, {'taskRunning': None}, {'agentStreamRunning': True},
                   {'agentStreamRunning': None}, {'navigationBaseline': None},
                   {'navigationReset': {'state': 'running'}}]
        for field, value in (('state', 'running'), ('state', 'unknown'), ('resultVersion', True),
                             ('resultVersion', 2), ('profileId', 'other')):
            changes.append({'navigationBaseline': {**self.child['navigationBaseline'], field: value}})
        for change in changes:
            with self.subTest(change=change), patch.object(control, 'mutate') as mutation:
                with self.assertRaises(control.ControlError):
                    control.run_navigation_baseline({**self.child, **change}, 45)
                mutation.assert_not_called()

    def test_single_start_polls_same_run_through_cleanup_then_fetches_once(self):
        terminal, full = self.result()
        admitted = self.status()
        cleanup = {**terminal, 'taskRunning': True}
        full['automationState'] = 'unrelated-later-state'
        with patch.object(control, 'mutate', return_value=admitted) as mutation, \
                patch.object(control, 'refresh', side_effect=[cleanup, terminal]) as refresh, \
                patch.object(control, 'exchange', return_value=full) as fetch, patch.object(control.time, 'sleep'):
            result = control.run_navigation_baseline(self.child, 45)
        mutation.assert_called_once_with('startNavigationBaseline', self.child)
        self.assertEqual(refresh.call_count, 2)
        fetch.assert_called_once_with('navigationBaselineResult', 123, 3, nonce='child-epoch',
                                      fields={'navigationBaselineRunId': self.RUN})
        self.assertEqual(result, {**terminal, 'navigationBaseline': full['navigationBaseline']})
        self.assertEqual(result['automationState'], 'game_ready')

    def test_fast_terminal_response_fetches_without_extra_poll(self):
        terminal, full = self.result()
        with patch.object(control, 'mutate', return_value=terminal), \
                patch.object(control, 'exchange', return_value=full), patch.object(control, 'refresh') as refresh:
            self.assertEqual(control.run_navigation_baseline(self.child, 45), full)
        refresh.assert_not_called()

    def test_failed_cancelled_or_owner_cleanup_failure_retains_full_result(self):
        for state in ('failed', 'cancelled'):
            terminal, full = self.result(state)
            terminal['navigationBaseline']['error'] = 'owner_cleanup_failed'
            full['navigationBaseline']['error'] = 'owner_cleanup_failed'
            # A prior measured verification cannot override the owner's failed cleanup.
            full['navigationBaseline']['result']['verified'] = True
            full['navigationBaseline']['result']['inputReleaseError'] = 'synthetic release failure'
            pending = {**terminal, 'taskRunning': True}
            with self.subTest(state=state), patch.object(control, 'mutate', return_value=pending) as mutation, \
                    patch.object(control, 'refresh', return_value=terminal), \
                    patch.object(control, 'exchange', return_value=full) as fetch, patch.object(control.time, 'sleep'):
                with self.assertRaises(control.NavigationBaselineError) as failure:
                    control.run_navigation_baseline(self.child, 45)
                self.assertEqual(failure.exception.status, full)
                self.assertIn('owner_cleanup_failed', str(failure.exception))
                mutation.assert_called_once()
                fetch.assert_called_once()

    def test_early_failure_with_no_measurements_or_artifacts_retains_result(self):
        terminal, full = self.result('failed', initialSample=None, samples=[], verificationSamples=[], evidence=None)
        with patch.object(control, 'mutate', return_value=terminal), patch.object(control, 'exchange', return_value=full):
            with self.assertRaises(control.NavigationBaselineError) as failure:
                control.run_navigation_baseline(self.child, 45)
        self.assertEqual(failure.exception.status, full)

    def test_start_response_requires_new_nonzero_run_identity(self):
        previous = self.status('completed')
        for run_id in (None, '', '0' * 32, 'g' * 32, self.RUN):
            with self.subTest(run_id=run_id), patch.object(control, 'mutate', return_value=self.status(runId=run_id)) as mutation, \
                    patch.object(control, 'refresh') as refresh, patch.object(control, 'exchange') as fetch:
                with self.assertRaises(control.NavigationBaselineError):
                    control.run_navigation_baseline(previous, 45)
                mutation.assert_called_once()
                refresh.assert_not_called()
                fetch.assert_not_called()

    def test_poll_rejects_identity_run_profile_or_game_replacement(self):
        admitted = self.status()
        replies = [{**admitted, **changes} for changes in ({'processId': 789}, {'windowsSessionId': 4},
                   {'instanceNonce': 'changed'}, {'instanceType': 'Primary'}, {'remoteDesktop': False})]
        for key, value in (('runId', 'a' * 32), ('state', 'idle'), ('profileId', 'other'),
                           ('resultVersion', True), ('gameProcessId', 987), ('windowsSessionId', 4)):
            replies.append(self.status(**{key: value}))
        for reply in replies:
            with self.subTest(reply=reply), patch.object(control, 'mutate', return_value=admitted) as mutation, \
                    patch.object(control, 'refresh', return_value=reply), patch.object(control, 'exchange') as fetch, \
                    patch.object(control.time, 'sleep'):
                with self.assertRaises(control.NavigationBaselineError) as failure:
                    control.run_navigation_baseline(self.child, 45)
                self.assertEqual(failure.exception.status, admitted)
                mutation.assert_called_once()
                fetch.assert_not_called()

    def test_result_requires_exact_compact_and_process_identity(self):
        terminal, full = self.result()
        replies = [{**full, **change} for change in ({'processId': 789}, {'windowsSessionId': 4},
                   {'instanceNonce': 'changed'}, {'instanceType': 'Primary'})]
        for key, value in (('runId', 'a' * 32), ('state', 'failed'), ('phase', 'other'), ('error', 'changed'),
                           ('profileId', 'other'), ('resultVersion', True), ('observationCount', 7),
                           ('evidenceComplete', False), ('finishedAtUtc', 'changed')):
            replies.append({**full, 'navigationBaseline': {**full['navigationBaseline'], key: value}})
        for reply in replies:
            with self.subTest(reply=reply), patch.object(control, 'mutate', return_value=terminal), \
                    patch.object(control, 'exchange', return_value=reply) as fetch:
                with self.assertRaises(control.NavigationBaselineError) as failure:
                    control.run_navigation_baseline(self.child, 45)
                self.assertEqual(failure.exception.status, terminal)
                fetch.assert_called_once()

    def test_success_requires_complete_evidence_release_and_three_finite_source_poses(self):
        terminal, full = self.result()
        valid = full['navigationBaseline']['result']
        bad_results = [{**valid, **change} for change in ({'verified': False}, {'error': 'failed'},
                       {'inputReleaseError': 'failed'}, {'initialSample': None}, {'samples': []},
                       {'verificationSamples': []}, {'verificationSamples': valid['samples'] + [self.pose(3)]},
                       {'evidence': None}, {'elapsedMs': float('nan')}, {'elapsedMs': 10 ** 400},
                       {'observationCount': 7})]
        for key, value in (('x', float('nan')), ('y', True), ('yawDegrees', '0'), ('x', 10 ** 400),
                           ('sourceEpoch', ''), ('sourceTimestamp100ns', True), ('acquiredAtStopwatchTicks', -1),
                           ('motion', {'status': 'fly'}), ('layerId', '')):
            samples = copy.deepcopy(valid['samples'])
            samples[0][key] = value
            bad_results.append({**valid, 'samples': samples, 'verificationSamples': samples})
        for key, value in (('complete', False), ('journalPath', None), ('initialImageSha256', 'bad'),
                           ('finalImagePath', '')):
            bad_results.append({**valid, 'evidence': {**valid['evidence'], key: value}})
        for result in bad_results:
            reply = {**full, 'navigationBaseline': {**full['navigationBaseline'], 'result': result}}
            with self.subTest(result=result), patch.object(control, 'mutate', return_value=terminal), \
                    patch.object(control, 'exchange', return_value=reply):
                with self.assertRaises(control.NavigationBaselineError) as failure:
                    control.run_navigation_baseline(self.child, 45)
                self.assertEqual(failure.exception.status, terminal)

    def test_ambiguous_start_response_is_never_replayed_or_inferred(self):
        for error in (control.ControlError('timeout'), OSError('closed')):
            with self.subTest(error=error), patch.object(control, 'mutate', side_effect=error) as mutation, \
                    patch.object(control, 'refresh') as refresh, patch.object(control, 'exchange') as fetch:
                with self.assertRaises(type(error)):
                    control.run_navigation_baseline(self.child, 45)
                mutation.assert_called_once()
                refresh.assert_not_called()
                fetch.assert_not_called()

    def test_result_read_failure_keeps_terminal_status_and_is_not_retried(self):
        terminal, _ = self.result('failed')
        with patch.object(control, 'mutate', return_value=terminal) as mutation, \
                patch.object(control, 'exchange', side_effect=OSError('closed')) as fetch:
            with self.assertRaises(control.NavigationBaselineError) as failure:
                control.run_navigation_baseline(self.child, 45)
        self.assertEqual(failure.exception.status, terminal)
        mutation.assert_called_once()
        fetch.assert_called_once()

    def test_timeout_preserves_last_status_and_never_cancels_or_restarts(self):
        admitted = self.status()
        with patch.object(control, 'mutate', return_value=admitted) as mutation, \
                patch.object(control.time, 'monotonic', side_effect=[0, 46]), \
                patch.object(control, 'refresh') as refresh, patch.object(control, 'exchange') as fetch:
            with self.assertRaisesRegex(control.NavigationBaselineError, 'No cancellation was sent') as failure:
                control.run_navigation_baseline(self.child, 45)
        self.assertEqual(failure.exception.status, admitted)
        mutation.assert_called_once()
        refresh.assert_not_called()
        fetch.assert_not_called()

    def test_cli_default_selects_child_and_retains_success_or_failure_payload(self):
        _, full = self.result()
        for failed in (False, True):
            output = io.StringIO()
            with self.subTest(failed=failed), patch.object(sys, 'argv', ['rdp_control.py', 'run-navigation-baseline']), \
                    patch.object(sys, 'stdout' if not failed else 'stderr', output), \
                    patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                    patch.object(control, 'run_navigation_baseline',
                        side_effect=control.NavigationBaselineError('failed', full) if failed else None,
                        return_value=full) as run:
                self.assertEqual(control.main(), 1 if failed else 0)
            run.assert_called_once_with(self.child, 45)
            result = json.loads(output.getvalue())
            self.assertEqual(result['status'] if failed else result, full)

    def test_cli_rejects_arbitrary_route_or_reset_options_without_contact(self):
        for option in ('--route=other.json', '--yaw-degrees=90', '--reset'):
            with self.subTest(option=option), patch.object(sys, 'argv', ['rdp_control.py', 'run-navigation-baseline', option]), \
                    patch.object(sys, 'stderr', io.StringIO()), patch.object(control, 'discover') as discover:
                with self.assertRaises(SystemExit) as failure:
                    control.main()
                self.assertEqual(failure.exception.code, 2)
                discover.assert_not_called()


if __name__ == '__main__':
    unittest.main()
