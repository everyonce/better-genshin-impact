"""Fixed two-leg protocol tests; synthetic peers only, no pipe, process, or game operations."""
import copy
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

# The isolated candidate imports unchanged transport dependencies from the checkout.
ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'BetterGenshinImpact.sln').is_file())
sys.path.insert(0, str(ROOT / 'tools' / 'rdp-automation'))
spec = importlib.util.spec_from_file_location('r31_control', Path(__file__).with_name('rdp_control.py'))
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)
import test_navigation_baseline as fixtures

OLD, NEW = 'mondstadt-city-leg-1-v1', 'mondstadt-city-two-legs-v1'


class TwoLegTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.NavigationBaselineTests()
        self.fixture.setUp()
        self.child = self.fixture.child
        self.capabilities = {'routeVersion': 1, 'routeProfiles': [OLD, NEW],
                             'timingContracts': ['v1', 'v2', 'v3', 'v4'],
                             'capturePolicies': ['shared', 'task_owned_timer']}
        self.child['navigationBaseline'].update(self.capabilities)

    def result(self, state='completed'):
        terminal, full = self.fixture.result(state)
        for value in (terminal, full):
            value['navigationBaseline'].update(self.capabilities)
            value['navigationBaseline'].update(profileId=NEW, timingContract='v4',
                capturePolicy='task_owned_timer', controllerMethod='native-fixed-leg-feedback-v4')
        result = full['navigationBaseline']['result']
        result.update(profileId=NEW, routeVersion=1, timingContract='v4', capturePolicy='task_owned_timer',
                      controllerMethod='native-fixed-leg-feedback-v4',
                      legs=[{'legIndex': index, 'outcome': 'completed'} for index in (1, 2)],
                      waypoint={'outcome': 'completed', 'error': None,
                                'samples': [self.fixture.pose(index) for index in (1, 2, 3)],
                                'anchor': self.fixture.pose(4)})
        return terminal, full

    def run_case(self, terminal, full):
        with patch.object(control, 'mutate', return_value=terminal) as start, \
                patch.object(control, 'exchange', return_value=full) as read:
            output = control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer', NEW)
        start.assert_called_once_with('startNavigationBaseline', self.child, timingContract='v4',
                                     capturePolicy='task_owned_timer', routeProfile=NEW)
        read.assert_called_once()
        return output

    def test_exact_capable_one_start_one_result(self):
        terminal, full = self.result()
        self.assertEqual(NEW, self.run_case(terminal, full)['navigationBaseline']['result']['profileId'])

    def test_unsupported_capability_or_contract_never_mutates(self):
        for changes, timing, capture in [({'routeVersion': None}, 'v4', 'task_owned_timer'),
                ({'routeVersion': True}, 'v4', 'task_owned_timer'), ({'routeProfiles': [OLD]}, 'v4', 'task_owned_timer'),
                ({}, 'v3', 'task_owned_timer'), ({}, 'v4', 'shared')]:
            child = copy.deepcopy(self.child); child['navigationBaseline'].update(changes)
            with self.subTest(changes=changes, timing=timing, capture=capture), patch.object(control, 'mutate') as start:
                with self.assertRaises(control.ControlError):
                    control.run_navigation_baseline(child, 45, timing, capture, NEW)
                start.assert_not_called()

    def test_unknown_start_is_never_replayed(self):
        with patch.object(control, 'mutate', side_effect=control.ControlError('unknown outcome')) as start:
            with self.assertRaises(control.ControlError):
                control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer', NEW)
        start.assert_called_once()

    def test_wrong_admission_profile_fails_without_result_read(self):
        terminal, full = self.result(); terminal['navigationBaseline']['profileId'] = OLD
        with patch.object(control, 'mutate', return_value=terminal), patch.object(control, 'exchange') as read:
            with self.assertRaises(control.NavigationBaselineError):
                control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer', NEW)
            read.assert_not_called()

    def test_full_result_profile_must_match(self):
        terminal, full = self.result(); full['navigationBaseline']['result']['profileId'] = OLD
        with self.assertRaises(control.NavigationBaselineError): self.run_case(terminal, full)

    def test_partial_leg_or_waypoint_cannot_be_success(self):
        for field, value in [('legs', []), ('legs', [{'legIndex': 1, 'outcome': 'completed'}]),
                             ('waypoint', None), ('waypoint', {'outcome': 'failed'})]:
            terminal, full = self.result(); full['navigationBaseline']['result'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(control.NavigationBaselineError):
                self.run_case(terminal, full)

    def test_failed_second_leg_preserves_result_and_never_reports_success(self):
        terminal, full = self.result('failed')
        full['navigationBaseline']['result']['waypoint']['outcome'] = 'failed'
        with self.assertRaises(control.NavigationBaselineError) as error:
            self.run_case(terminal, full)
        self.assertEqual('failed', error.exception.status['navigationBaseline']['result']['waypoint']['outcome'])

    def test_legacy_default_omits_new_wire_selector(self):
        self.fixture.setUp(); child = self.fixture.child
        terminal, full = self.fixture.result()
        with patch.object(control, 'mutate', return_value=terminal) as start, patch.object(control, 'exchange', return_value=full):
            control.run_navigation_baseline(child, 45)
        start.assert_called_once_with('startNavigationBaseline', child)

    def test_cli_supplies_only_explicit_new_fixed_profile(self):
        _, full = self.result()
        with patch.object(sys, 'argv', ['rdp_control.py', 'run-navigation-baseline',
                '--timing-contract', 'v4', '--capture-policy', 'task_owned_timer', '--route-profile', NEW]), \
                patch.object(sys, 'stdout', io.StringIO()), \
                patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                patch.object(control, 'run_navigation_baseline', return_value=full) as run:
            self.assertEqual(0, control.main())
        run.assert_called_once_with(self.child, 45, 'v4', 'task_owned_timer', NEW)

    def test_capable_previous_new_run_can_start_explicit_old_default(self):
        self.child['navigationBaseline']['profileId'] = NEW
        terminal, full = self.fixture.result()
        for value in (terminal, full):
            value['navigationBaseline'].update(self.capabilities)
            value['navigationBaseline'].update(timingContract='v4', capturePolicy='task_owned_timer',
                                               controllerMethod='native-fixed-leg-feedback-v4')
        full['navigationBaseline']['result'].update(timingContract='v4', capturePolicy='task_owned_timer',
                                                    controllerMethod='native-fixed-leg-feedback-v4')
        with patch.object(control, 'mutate', return_value=terminal) as start, patch.object(control, 'exchange', return_value=full):
            control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer')
        self.assertNotIn('routeProfile', start.call_args.kwargs)


if __name__ == '__main__':
    unittest.main()
