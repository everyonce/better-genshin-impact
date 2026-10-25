"""Explicit v5 protocol/admission coverage using fake peers and terminal records."""
import copy
import io
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
import test_navigation_baseline as fixtures
from test_rdp_control import FakePipe


class NavigationBaselineV5Tests(unittest.TestCase):
    """Exercise the public client without a native transport or game process."""
    def setUp(self):
        """Reuse the existing native-baseline status and result fixture."""
        self.fixture=fixtures.NavigationBaselineTests();self.fixture.setUp()

    def capable(self,value,selected='v5'):
        """Describe a synthetic producer that explicitly advertises the new contract."""
        value=copy.deepcopy(value);owner=value['navigationBaseline']
        owner.update(timingContracts=['v1','v2','v3','v4','v5'],timingContract=selected,
                     controllerMethod='native-fixed-leg-feedback-'+selected)
        if 'result' in owner:
            owner['result'].update(timingContract=selected,controllerMethod='native-fixed-leg-feedback-'+selected)
        return value

    def test_requires_advertised_v5_before_any_mutation(self):
        """A stale producer must reject the selection before receiving a start."""
        child=self.capable(self.fixture.child,'v1')
        child['navigationBaseline']['timingContracts'].remove('v5')
        with patch.object(control,'mutate') as mutation:
            with self.assertRaises(control.ControlError):control.run_navigation_baseline(child,45,'v5')
            mutation.assert_not_called()

    def test_completed_v5_request_starts_exactly_once(self):
        """A matching terminal response completes without replaying the start."""
        child=self.capable(self.fixture.child,'v1')
        terminal,full=(self.capable(value) for value in self.fixture.result())
        with patch.object(control,'mutate',return_value=terminal) as mutation, \
             patch.object(control,'exchange',return_value=full):
            self.assertEqual(control.run_navigation_baseline(child,45,'v5'),full)
        mutation.assert_called_once_with('startNavigationBaseline',child,timingContract='v5')

    def test_downgraded_owner_or_result_stops_after_single_start(self):
        """Both admission and final evidence must retain the selected contract."""
        child=self.capable(self.fixture.child,'v1')
        for carrier in ('owner','result'):
            terminal,full=(self.capable(value) for value in self.fixture.result())
            target=terminal['navigationBaseline'] if carrier=='owner' else full['navigationBaseline']['result']
            target.update(timingContract='v4',controllerMethod='native-fixed-leg-feedback-v4')
            with self.subTest(carrier=carrier),patch.object(control,'mutate',return_value=terminal) as mutation, \
                 patch.object(control,'exchange',return_value=full):
                with self.assertRaises(control.ControlError):control.run_navigation_baseline(child,45,'v5')
                self.assertEqual(mutation.call_count,1)

    def test_v5_wire_selection_and_unknown_or_shadow_rejection(self):
        """Only the supported explicit combination may reach the fake pipe."""
        api=FakePipe()
        control.exchange('startNavigationBaseline',123,2,nonce='instance-a',fields=dict(
            timingContract='v5',capturePolicy='task_owned_timer',routeProfile='mondstadt-city-courtyard-return-v1',
            continuationFromRunId='a'*32),api=api)
        self.assertEqual(api.request['timingContract'],'v5');self.assertTrue(api.closed)
        for fields in (dict(timingContract='v6'),dict(timingContract='v5',capturePolicy='task_owned_timer',
                                                  shadowCapture=control.SHADOW_CAPTURE_MODE)):
            api=FakePipe()
            with self.assertRaises(control.ControlError):
                control.exchange('startNavigationBaseline',123,2,nonce='instance-a',fields=fields,api=api)
            self.assertEqual(api.written,[])

    def test_cli_requires_explicit_selection_and_preserves_v1_default(self):
        """Existing callers retain their default unless they select the new timing."""
        for selected in (None,'v4','v5'):
            argv=['rdp_control','run-navigation-baseline','--process-id','123','--windows-session-id','2']
            if selected:argv+=['--timing-contract',selected]
            with patch.object(sys,'argv',argv),patch.object(sys,'stdout',io.StringIO()), \
                 patch.object(control,'exchange',return_value={}), \
                 patch.object(control,'run_navigation_baseline',return_value={}) as run:
                self.assertEqual(control.main(),0)
            self.assertEqual(run.call_args.args[2],selected or 'v1')


if __name__=='__main__':unittest.main(verbosity=2)
