"""Agent start/stop contract tests with synthetic peers and no game/input actions."""
import io
import json
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
from test_rdp_control import FakePipe


class AgentCommandTests(unittest.TestCase):
    def setUp(self):
        self.child = {'processId': 123, 'windowsSessionId': 3, 'instanceNonce': 'child-epoch',
                      'instanceType': 'ChildSession', 'remoteDesktop': True, 'automationEnabled': True,
                      'runtimeRunning': True, 'automationState': 'game_ready', 'agentStreamState': 'idle',
                      'agentStreamRunning': False, 'agentInputEnabled': False}

    def test_default_is_observation_and_waits_for_actual_listening(self):
        ready = {**self.child, 'agentStreamState': 'listening', 'agentStreamRunning': True}
        with patch.object(control, 'mutate') as mutation, patch.object(control, 'refresh', return_value=ready):
            self.assertEqual(control.start_agent(self.child, 1), ready)
        mutation.assert_called_once_with('startAgentStream', self.child, enableInput=False)

    def test_console_wrong_role_missing_runtime_and_input_coercion_rejected(self):
        for child in ({**self.child, 'remoteDesktop': False}, {**self.child, 'instanceType': 'Primary'},
                      {**self.child, 'automationEnabled': False}, {**self.child, 'runtimeRunning': False},
                      {**self.child, 'automationState': 'starting_game'}):
            with self.subTest(child=child), patch.object(control, 'mutate') as mutation:
                with self.assertRaises(control.ControlError):
                    control.start_agent(child, 1)
                mutation.assert_not_called()
        with self.assertRaises(control.ControlError):
            control.start_agent(self.child, 1, 'false')

    def test_join_never_upgrades_running_permissions(self):
        running = {**self.child, 'agentStreamState': 'listening', 'agentStreamRunning': True}
        with patch.object(control, 'mutate') as mutation, patch.object(control, 'refresh', return_value=running):
            self.assertEqual(control.start_agent(running, 1), running)
            with self.assertRaisesRegex(control.ControlError, 'before changing'):
                control.start_agent(running, 1, True)
        mutation.assert_not_called()

    def test_task_rejection_reports_error_without_retrying_mutation(self):
        rejected = {**self.child, 'agentStreamState': 'rejected', 'agentStreamError': 'TaskRunner is busy'}
        with patch.object(control, 'mutate') as mutation, patch.object(control, 'refresh', return_value=rejected):
            with self.assertRaisesRegex(control.ControlError, 'TaskRunner is busy'):
                control.start_agent(self.child, 1)
        self.assertEqual(mutation.call_count, 1)

    def test_explicit_boolean_and_exact_target_on_wire(self):
        api = FakePipe(self.child)
        api.session = 3
        control.exchange('startAgentStream', 123, 3, nonce='child-epoch', fields={'enableInput': True}, api=api)
        self.assertIs(api.request['enableInput'], True)
        self.assertEqual(api.request['targetNonce'], 'child-epoch')
        self.assertEqual(api.request['targetWindowsSessionId'], 3)
        for fields in ({'enableInput': 1}, {'enableInput': 'true'}, {'enableInput': False, 'pipeName': 'other'}):
            with self.assertRaises(control.ControlError):
                control.exchange('startAgentStream', 123, 3, nonce='child-epoch', fields=fields, api=api)

    def test_cli_selects_child_and_requires_flag_for_input(self):
        for flag in ([], ['--enable-input']):
            output = io.StringIO()
            with patch.object(sys, 'argv', ['rdp_control.py', 'start-agent', *flag]), \
                    patch.object(sys, 'stdout', output), \
                    patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                    patch.object(control, 'start_agent', return_value=self.child) as start:
                self.assertEqual(control.main(), 0)
            start.assert_called_once_with(self.child, 120, bool(flag), control.LEGACY_OBSERVATION_PROFILE)
            self.assertEqual(json.loads(output.getvalue()), self.child)

    def test_explicit_profile_is_transmitted_and_must_be_verified_at_listening(self):
        profile = 'p2p-native-hamming-192-v1'
        ready = {**self.child, 'agentStreamState': 'listening', 'agentStreamRunning': True,
                 'agentObservationProfile': profile}
        with patch.object(control, 'mutate') as mutation, patch.object(control, 'refresh', return_value=ready):
            self.assertEqual(control.start_agent(self.child, 1, observation_profile=profile), ready)
        mutation.assert_called_once_with('startAgentStream', self.child, enableInput=False, observationProfile=profile)
        for returned in (None, control.LEGACY_OBSERVATION_PROFILE, 'unknown'):
            mismatch = {**ready, 'agentObservationProfile': returned}
            with self.subTest(returned=returned), patch.object(control, 'mutate') as mutation, \
                    patch.object(control, 'refresh', return_value=mismatch):
                with self.assertRaisesRegex(control.ControlError, 'different observation profile'):
                    control.start_agent(self.child, 1, observation_profile=profile)
                self.assertEqual(mutation.call_count, 1)

    def test_profile_join_is_exact_and_never_reconfigures_a_running_stream(self):
        profile = 'p2p-native-hamming-192-v1'
        running = {**self.child, 'agentStreamState': 'listening', 'agentStreamRunning': True,
                   'agentObservationProfile': profile}
        with patch.object(control, 'mutate') as mutation, patch.object(control, 'refresh', return_value=running):
            self.assertEqual(control.start_agent(running, 1, observation_profile=profile), running)
            with self.assertRaisesRegex(control.ControlError, 'before changing its observation profile'):
                control.start_agent(running, 1)
        mutation.assert_not_called()
        # A pre-profile server is explicitly legacy; it cannot confirm the opt-in encoding.
        del running['agentObservationProfile']
        with patch.object(control, 'mutate') as mutation:
            with self.assertRaises(control.ControlError):
                control.start_agent(running, 1, observation_profile=profile)
        mutation.assert_not_called()

    def test_profile_wire_validation_precedes_connection_and_keeps_null_legacy(self):
        for profile in control.OBSERVATION_PROFILES + (None,):
            api = FakePipe(self.child)
            api.session = 3
            control.exchange('startAgentStream', 123, 3, nonce='child-epoch',
                             fields={'enableInput': False, 'observationProfile': profile}, api=api)
            self.assertEqual(api.request['observationProfile'], profile)
        for profile in ('', 'P2P-NATIVE-HAMMING-192-V1', 'unknown', 1, True, {}):
            api = FakePipe(self.child)
            with self.subTest(profile=profile), self.assertRaises(control.ControlError):
                control.exchange('startAgentStream', 123, 3, nonce='child-epoch',
                                 fields={'enableInput': False, 'observationProfile': profile}, api=api)
            self.assertEqual(api.written, [])
        for command in ('status', 'stopAgentStream', 'startChildSession'):
            with self.subTest(command=command), self.assertRaises(control.ControlError):
                control.exchange(command, 123, 3, nonce='child-epoch',
                                 fields={'observationProfile': None}, api=FakePipe(self.child))

    def test_cli_forwards_only_an_explicit_known_profile(self):
        profile = 'p2p-native-hamming-192-v1'
        with patch.object(sys, 'argv', ['rdp_control.py', 'start-agent', '--observation-profile', profile]), \
                patch.object(sys, 'stdout', io.StringIO()), \
                patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                patch.object(control, 'start_agent', return_value=self.child) as start:
            self.assertEqual(control.main(), 0)
        start.assert_called_once_with(self.child, 120, False, profile)
        with patch.object(sys, 'argv', ['rdp_control.py', 'start-agent', '--observation-profile', 'unknown']), \
                patch.object(sys, 'stderr', io.StringIO()), patch.object(control, 'discover') as discovery:
            with self.assertRaises(SystemExit):
                control.main()
        discovery.assert_not_called()

    def test_stop_uses_scoped_agent_command_and_waits_for_cleanup(self):
        with patch.object(control, 'mutate') as mutation, patch.object(control, 'refresh', return_value=self.child):
            control.stop_agent(self.child, 1)
        mutation.assert_called_once_with('stopAgentStream', self.child)


if __name__ == '__main__':
    unittest.main()
