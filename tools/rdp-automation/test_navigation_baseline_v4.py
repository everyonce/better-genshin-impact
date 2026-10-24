"""Synthetic opt-in v4 admission/evidence tests. No pipe, game, reset or input calls."""
import copy
import io
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
import test_navigation_baseline as fixtures
from test_rdp_control import FakePipe


class NavigationBaselineV4Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.NavigationBaselineTests()
        self.fixture.setUp()

    def capable(self, status, contract='v4'):
        status = copy.deepcopy(status)
        operation = status['navigationBaseline']
        operation.update(timingContracts=['v1', 'v2', 'v3', 'v4'], timingContract=contract,
                         controllerMethod=f'native-fixed-leg-feedback-{contract}')
        if 'result' in operation:
            operation['result'].update(timingContract=contract, controllerMethod=f'native-fixed-leg-feedback-{contract}')
        return status

    def test_v4_refuses_unknown_capability_before_start(self):
        for supported in (None, ['v1', 'v2', 'v3'], [], 'v4', [True, 'v4']):
            child = self.capable(self.fixture.child)
            if supported is None:
                child['navigationBaseline'].pop('timingContracts')
            else:
                child['navigationBaseline']['timingContracts'] = supported
            with self.subTest(supported=supported), patch.object(control, 'mutate') as mutation:
                with self.assertRaises(control.ControlError):
                    control.run_navigation_baseline(child, 45, 'v4')
                mutation.assert_not_called()

    def test_v4_failed_recovery_keeps_pinned_result_and_starts_only_once(self):
        child = self.capable(self.fixture.child, 'v1')
        terminal, full = (self.capable(value) for value in self.fixture.result('failed'))
        for value in (terminal, full):
            value['navigationBaseline']['error'] = 'recovery_poll_limit_exceeded'
        full['navigationBaseline']['result']['error'] = 'recovery_poll_limit_exceeded'
        with patch.object(control, 'mutate', return_value=terminal) as mutation, \
                patch.object(control, 'exchange', return_value=full) as query, patch.object(control, 'refresh') as refresh:
            with self.assertRaises(control.NavigationBaselineError) as failure:
                control.run_navigation_baseline(child, 45, 'v4')
        self.assertEqual(full, failure.exception.status)
        mutation.assert_called_once_with('startNavigationBaseline', child, timingContract='v4')
        query.assert_called_once(); refresh.assert_not_called()

    def test_v4_success_does_not_relax_owner_or_result_identity(self):
        child = self.capable(self.fixture.child, 'v1')
        terminal, full = (self.capable(value) for value in self.fixture.result())
        for mismatch in ('admission', 'result'):
            bad_terminal, bad_full = copy.deepcopy(terminal), copy.deepcopy(full)
            operation = bad_terminal['navigationBaseline'] if mismatch == 'admission' else bad_full['navigationBaseline']['result']
            operation.update(timingContract='v3', controllerMethod='native-fixed-leg-feedback-v3')
            with self.subTest(mismatch=mismatch), patch.object(control, 'mutate', return_value=bad_terminal) as mutation, \
                    patch.object(control, 'exchange', return_value=bad_full):
                with self.assertRaises(control.NavigationBaselineError):
                    control.run_navigation_baseline(child, 45, 'v4')
                mutation.assert_called_once()

    def test_uncertain_start_is_not_replayed(self):
        child = self.capable(self.fixture.child)
        with patch.object(control, 'mutate', side_effect=OSError('lost acknowledgement')) as mutation:
            with self.assertRaises(OSError):
                control.run_navigation_baseline(child, 45, 'v4')
        mutation.assert_called_once()

    def test_wire_v4_is_start_only_and_literal(self):
        api = FakePipe(self.fixture.status()); api.session = 3
        control.exchange('startNavigationBaseline', 123, 3, nonce='child-epoch', fields={'timingContract': 'v4'}, api=api)
        self.assertEqual('v4', api.request['timingContract'])
        for command, selector in [('status', 'v4'), ('startNavigationBaseline', 'V4'), ('startNavigationBaseline', 'v5')]:
            api = FakePipe(self.fixture.child)
            with self.subTest(command=command, selector=selector), self.assertRaises(control.ControlError):
                control.exchange(command, 123, 3, nonce='child-epoch', fields={'timingContract': selector}, api=api)
            self.assertFalse(hasattr(api, 'pipe_name'))

    def test_cli_v4_is_explicit_and_capture_policy_remains_independent(self):
        with patch.object(sys, 'argv', ['rdp_control.py', 'run-navigation-baseline', '--timing-contract', 'v4',
                                       '--capture-policy', 'task_owned_timer']), patch.object(sys, 'stdout', io.StringIO()), \
                patch.object(control, 'discover', return_value={'instances': [self.fixture.child]}), \
                patch.object(control, 'run_navigation_baseline', return_value={}) as run:
            self.assertEqual(0, control.main())
        run.assert_called_once_with(self.fixture.child, 45, 'v4', 'task_owned_timer')


if __name__ == '__main__':
    unittest.main()
