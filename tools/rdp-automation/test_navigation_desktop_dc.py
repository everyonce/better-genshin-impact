"""Exact native DesktopDc policy and raw-source joins; no pipe or process creation."""
import copy
import json
import unittest
from unittest.mock import patch

import rdp_control as control
import test_navigation_baseline as baseline_fixtures
import test_navigation_reset as reset_fixtures


# Exact closed R41 child status; source fixture SHA256 dd4c5e9c2e3a516ded141bce1d4d6fa56316674ecb96157018e29435cd07ac4b.
# This is recorded DTO data, not current runtime authority. Selection is changed only inside fake cases.
RECORDED_R41_CHILD_STATUS = json.loads(r'''
{
  "childStartupIntentVersion": 0,
  "childStartupMode": null,
  "idleRestartVersion": 2,
  "navigationBaseline": {
    "shadowCaptureVersion": 1,
    "shadowCaptureModes": [
      "rgb192-capture-only-v1"
    ],
    "readbackMode": null,
    "capturePolicies": [
      "shared",
      "task_owned_timer"
    ],
    "capturePolicy": "shared",
    "timingContracts": [
      "v1",
      "v2",
      "v3",
      "v4"
    ],
    "timingContract": "v1",
    "controllerMethod": "native-fixed-leg-feedback-v1",
    "runId": null,
    "state": "idle",
    "phase": "idle",
    "error": null,
    "profileId": "mondstadt-city-leg-1-v1",
    "routeVersion": 1,
    "routeProfiles": [
      "mondstadt-city-leg-1-v1",
      "mondstadt-city-two-legs-v1",
      "mondstadt-city-reverse-two-legs-v1",
      "mondstadt-city-courtyard-return-v1",
      "mondstadt-city-courtyard-forward-v1"
    ],
    "endpointContinuationVersion": 2,
    "gameProcessId": 0,
    "windowsSessionId": 0,
    "startedAtUtc": null,
    "finishedAtUtc": null,
    "observationCount": 0,
    "evidenceComplete": false,
    "resultVersion": 1
  },
  "navigationReset": {
    "readbackMode": null,
    "capturePolicies": [
      "shared",
      "task_owned_timer"
    ],
    "capturePolicy": "shared",
    "runId": null,
    "state": "idle",
    "phase": "idle",
    "error": null,
    "profileId": "mondstadt-city-10",
    "targetYawDegrees": 0,
    "gameProcessId": 0,
    "windowsSessionId": 0,
    "startedAtUtc": null,
    "finishedAtUtc": null,
    "samples": [],
    "verificationDiagnosticsVersion": 1
  },
  "uiStatus": "current",
  "agentStreamState": "idle",
  "agentStreamError": null,
  "agentStreamRunning": false,
  "agentInputEnabled": false,
  "agentObservationProfile": "legacy-area-640x360-v1",
  "agentPipeName": "BetterGI.Agent.local",
  "automationEnabled": true,
  "appVersion": "0.66.2-alpha.4",
  "assemblySha256": "664764B33BC413A0233994B813E86C37518B1826ADA05DD48A6DDEF8238E41E9",
  "childSessionId": null,
  "childConnectedState": 0,
  "childWindowMinimized": false,
  "automationState": "game_ready",
  "automationError": null,
  "taskRunning": false,
  "runtimeRunning": true,
  "captureMode": "WindowsGraphicsCaptureV2",
  "readbackVersion": 1,
  "readbackModes": [
    "blocking",
    "poll_single_v1"
  ],
  "configuredReadbackMode": "poll_single_v1",
  "effectiveReadbackMode": "poll_single_v1",
  "captureOptionsVersion": 1,
  "sourceRetentions": [
    "disabled",
    "hold-until-readback-v1"
  ],
  "conversionModes": [
    "gpu",
    "cpu"
  ],
  "configuredSourceRetention": "disabled",
  "effectiveSourceRetention": "disabled",
  "configuredConversion": "cpu",
  "effectiveConversion": "cpu",
  "desktopDcSourcePolicyVersion": 1,
  "desktopDcSourcePolicies": [
    "observe-only",
    "host-acquisition-v1"
  ],
  "configuredDesktopDcSourcePolicy": "observe-only",
  "appDirectory": "D:\\work\\genshin-auto\\artifacts\\release-r41\\BetterGI-English-win-x64\\",
  "captureStorageVersion": 1,
  "processId": 31552,
  "windowsSessionId": 3,
  "instanceType": "ChildSession",
  "remoteDesktop": true,
  "pipeName": "BetterGI.ExternalControl.DC8465355EE156CA.3.31552",
  "instanceNonce": "56beceea9cc9489f88fd5a5b5cf74598",
  "pilotState": "idle",
  "serviceOwnsPilot": false,
  "heartbeatFresh": false,
  "rootProcessId": 28072,
  "recoveryLauncherInstalled": false
}
''')


class DesktopNativeControlTests(unittest.TestCase):
    """Use source-shaped status dictionaries while forbidding live transport globally."""

    POLICY = 'host-acquisition-v1'
    EPOCH = '01234567-89ab-cdef-0123-456789abcdef'

    def setUp(self):
        for guard in (patch.object(control.transport, 'WinPipeApi', side_effect=AssertionError('No native transport')),
                      patch('subprocess.Popen', side_effect=AssertionError('No child processes'))):
            guard.start()
            self.addCleanup(guard.stop)
        self.base = baseline_fixtures.NavigationBaselineTests()
        self.base.setUp()
        self.reset = reset_fixtures.NavigationResetTests()
        self.reset.setUp()

    def host(self, status, policy=POLICY):
        """Add the exact top-level capability/effective-selection producer fields."""
        status = copy.deepcopy(status)
        status.update(captureMode='DesktopDc',
                      desktopDcSourcePolicyVersion=1,
                      desktopDcSourcePolicies=['observe-only', self.POLICY],
                      configuredDesktopDcSourcePolicy=policy, effectiveDesktopDcSourcePolicy=policy)
        for key in ('effectiveReadbackMode', 'effectiveSourceRetention', 'effectiveConversion'):
            status.pop(key, None)
        for name in ('navigationReset', 'navigationBaseline'):
            if name not in status:
                continue
            operation = status[name]
            operation.update(capturePolicy='task_owned_timer', capturePolicies=['shared', 'task_owned_timer'])
            if operation.get('state') != 'idle':
                operation.update(sourcePolicy=policy, readbackMode=None, gameProcessId=456)
            if name == 'navigationBaseline':
                operation.update(timingContract='v4', timingContracts=['v1', 'v2', 'v3', 'v4'],
                                 controllerMethod='native-fixed-leg-feedback-v4')
        return status

    def pose(self, sample, number):
        """Native STJ preserves PascalCase raw library fields and omits WGC clocks."""
        sample = copy.deepcopy(sample)
        for key in ('sourceTimestamp100ns', 'acquiredAtStopwatchTicks'):
            sample.pop(key, None)
        sample.update(sourceEpoch=self.EPOCH, sourceKind=self.POLICY,
                      hostSnapshot={'CaptureEpoch': self.EPOCH, 'SnapshotId': number,
                                    'StartedAtStopwatchTicks': number * 1_000_000,
                                    'CompletedAtStopwatchTicks': number * 1_000_000 + 1000,
                                    'ClockFrequency': 10_000_000})
        return sample

    def baseline(self, state='completed'):
        """Build matching compact/full host short results, retaining failed evidence."""
        terminal, full = (self.host(value) for value in self.base.result(state))
        result = full['navigationBaseline']['result']
        result.update(sourcePolicy=self.POLICY, capturePolicy='task_owned_timer', timingContract='v4',
                      controllerMethod='native-fixed-leg-feedback-v4')
        result['evidence']['sourcePolicy'] = self.POLICY
        if result['initialSample'] is not None:
            result['initialSample'] = self.pose(result['initialSample'], 1)
        result['samples'] = [self.pose(value, index + 10) for index, value in enumerate(result['samples'])]
        result['verificationSamples'] = copy.deepcopy(result['samples'])
        return terminal, full

    def run_baseline(self, child=None, **options):
        """Call the ordinary host seed using the explicit existing selectors."""
        return control.run_navigation_baseline(child or self.host(self.base.child), 1, 'v4',
                                               'task_owned_timer', **options)

    def test_old_host_short_does_not_require_the_additive_continuation_capability(self):
        """The new branch must not change the original R44 ordinary-short wire or admission."""
        terminal, full = self.baseline()
        self.assertNotIn('hostEndpointContinuationVersion', terminal['navigationBaseline'])
        with patch.object(control, 'mutate', return_value=terminal) as mutate, \
                patch.object(control, 'exchange', return_value=full):
            self.assertEqual(full, self.run_baseline())
        mutate.assert_called_once_with('startNavigationBaseline', self.host(self.base.child),
                                      timingContract='v4', capturePolicy='task_owned_timer')

    def test_exact_saved_status_has_game_identity_only_inside_idle_owners(self):
        """Exercise the real top-level DTO, including zero-valued previous idle owners."""
        raw = copy.deepcopy(RECORDED_R41_CHILD_STATUS)
        self.assertNotIn('gameProcessId', raw)
        self.assertNotIn('genshinProcessId', raw)
        self.assertEqual(raw['navigationReset']['gameProcessId'], 0)
        self.assertEqual(raw['navigationBaseline']['gameProcessId'], 0)
        self.assertIsNone(control._controller_source_policy(raw))
        child = self.host(raw)
        self.assertEqual(control._controller_source_policy(child), self.POLICY)
        listening = {**child, 'agentStreamState': 'listening', 'agentStreamRunning': True, 'agentInputEnabled': True}
        with patch.object(control, 'mutate') as mutate, patch.object(control, 'refresh', return_value=listening):
            self.assertEqual(control.start_agent(child, 1, True), listening)
        mutate.assert_called_once_with('startAgentStream', child, enableInput=True)

    def test_host_reset_admitted_game_must_be_exact_positive_integer(self):
        """A malformed accepted owner is terminal locally and never causes a retry or fetch."""
        for value in (None, False, True, 0, -1, 456.0, '456'):
            admitted = self.host(self.reset.status('running'))
            admitted['navigationReset']['gameProcessId'] = value
            with self.subTest(value=value), patch.object(control, 'mutate', return_value=admitted) as mutate, \
                    patch.object(control, 'refresh') as refresh, patch.object(control, 'exchange') as fetch:
                with self.assertRaises(control.ControlError):
                    control.reset_navigation(self.host(self.reset.child), 0, 1, capture_policy='task_owned_timer')
                mutate.assert_called_once(); refresh.assert_not_called(); fetch.assert_not_called()

    def test_host_reset_pins_new_admitted_game_without_using_idle_owner(self):
        """The exact actual idle DTO can admit a new positive owner and then complete it."""
        child = self.host(RECORDED_R41_CHILD_STATUS)
        admitted = self.host(self.reset.status('running'))
        terminal = self.host(self.reset.status('completed'))
        for value in (admitted, terminal):
            for key in ('processId', 'windowsSessionId', 'instanceNonce'):
                value[key] = child[key]
        terminal['navigationReset']['samples'] = [self.pose(value, index + 1)
            for index, value in enumerate(terminal['navigationReset']['samples'])]
        with patch.object(control, 'mutate', return_value=admitted) as mutate, \
                patch.object(control, 'refresh', return_value=terminal) as refresh:
            self.assertEqual(control.reset_navigation(child, 0, 1, capture_policy='task_owned_timer'), terminal)
        mutate.assert_called_once(); refresh.assert_called_once()

    def test_host_reset_changed_game_after_admission_rejects_running_and_terminal(self):
        """Every returned owner must preserve the admitted integer PID before failure/diagnostic handling."""
        for state in ('running', 'completed', 'failed', 'cancelled'):
            for value in (457, 456.0, None, 0, True):
                admitted = self.host(self.reset.status('running'))
                current = self.host(self.reset.status(state))
                current['navigationReset']['gameProcessId'] = value
                with self.subTest(state=state, value=value), patch.object(control, 'mutate', return_value=admitted) as mutate, \
                        patch.object(control, 'refresh', return_value=current) as refresh, patch.object(control, 'exchange') as fetch:
                    with self.assertRaises(control.ControlError):
                        control.reset_navigation(self.host(self.reset.child), 0, 1, capture_policy='task_owned_timer')
                    mutate.assert_called_once(); refresh.assert_called_once(); fetch.assert_not_called()

    def test_host_baseline_keeps_existing_admitted_game_pin(self):
        """Removing the nonexistent top-level field preserves the existing baseline owner binding."""
        for state in ('running', 'completed', 'failed'):
            admitted = self.host(self.base.status('running'))
            current = self.host(self.base.status(state))
            current['navigationBaseline']['gameProcessId'] = 457
            with self.subTest(state=state), patch.object(control, 'mutate', return_value=admitted) as mutate, \
                    patch.object(control, 'refresh', return_value=current) as refresh, patch.object(control, 'exchange') as fetch:
                with self.assertRaises(control.NavigationBaselineError):
                    self.run_baseline()
                mutate.assert_called_once(); refresh.assert_called_once(); fetch.assert_not_called()

    def test_short_success_raw_host_source_one_start_one_result(self):
        terminal, full = self.baseline()
        with patch.object(control, 'mutate', return_value=terminal) as mutate, \
                patch.object(control, 'exchange', return_value=full) as fetch, patch.object(control, 'refresh') as refresh:
            self.assertEqual(self.run_baseline(), full)
        self.assertEqual(mutate.call_count, 1)
        self.assertEqual(fetch.call_count, 1)
        refresh.assert_not_called()

    def test_explicit_null_effective_wgc_fields_are_compatible(self):
        child = self.host(self.base.child)
        child.update(effectiveReadbackMode=None, effectiveSourceRetention=None, effectiveConversion=None)
        self.assertEqual(control._controller_source_policy(child), self.POLICY)

    def test_reset_success_retains_three_distinct_host_snapshots(self):
        child = self.host(self.reset.child)
        terminal = self.host(self.reset.status('completed'))
        terminal['navigationReset']['samples'] = [self.pose(value, index + 1)
            for index, value in enumerate(terminal['navigationReset']['samples'])]
        with patch.object(control, 'mutate', return_value=terminal) as mutate, patch.object(control, 'refresh') as refresh:
            result = control.reset_navigation(child, 0, 1, capture_policy='task_owned_timer')
        self.assertEqual(result, terminal)
        mutate.assert_called_once()
        refresh.assert_not_called()

    def test_observe_only_denies_all_input_entrypoints_before_mutation(self):
        for action in ('baseline', 'reset', 'agent'):
            child = self.host(self.base.child if action == 'baseline' else self.reset.child, 'observe-only')
            with self.subTest(action=action), patch.object(control, 'mutate') as mutate:
                with self.assertRaises(control.ControlError):
                    if action == 'baseline':
                        self.run_baseline(child)
                    elif action == 'reset':
                        control.reset_navigation(child, 0, 1)
                    else:
                        control.start_agent(child, 1, True)
                mutate.assert_not_called()

    def test_passive_agent_observe_only_still_allowed(self):
        child = self.host(self.reset.child, 'observe-only')
        listening = {**child, 'agentStreamState': 'listening', 'agentStreamRunning': True, 'agentInputEnabled': False}
        with patch.object(control, 'mutate') as mutate, patch.object(control, 'refresh', return_value=listening):
            self.assertEqual(control.start_agent(child, 1, False), listening)
        mutate.assert_called_once_with('startAgentStream', child, enableInput=False)

    def test_host_input_agent_pins_selection_without_invented_game_field(self):
        child = self.host(self.reset.child)
        listening = {**child, 'agentStreamState': 'listening', 'agentStreamRunning': True, 'agentInputEnabled': True}
        with patch.object(control, 'mutate') as mutate, patch.object(control, 'refresh', return_value=listening):
            self.assertEqual(control.start_agent(child, 1, True), listening)
        mutate.assert_called_once()
        for field, value in (('effectiveDesktopDcSourcePolicy', 'observe-only'), ('captureMode', 'WindowsGraphicsCapture')):
            with self.subTest(field=field), patch.object(control, 'mutate') as mutate, \
                    patch.object(control, 'refresh', return_value={**listening, field: value}):
                with self.assertRaises(control.ControlError):
                    control.start_agent(child, 1, True)
                mutate.assert_called_once()

    def test_nonordinary_routes_shadow_and_predecessor_rejected_before_query_or_start(self):
        choices = [{'route_profile': value} for value in ('mondstadt-city-two-legs-v1',
            'mondstadt-city-reverse-two-legs-v1', 'mondstadt-city-courtyard-return-v1', 'mondstadt-city-courtyard-forward-v1')]
        choices += [{'shadow_capture': 'rgb192-capture-only-v1'}, {'continuation_from_run_id': self.base.RUN}]
        for options in choices:
            with self.subTest(options=options), patch.object(control, 'mutate') as mutate, patch.object(control, 'exchange') as query:
                with self.assertRaises(control.ControlError):
                    self.run_baseline(**options)
                mutate.assert_not_called()
                query.assert_not_called()

    def test_legacy_timing_or_shared_capture_rejected_for_host(self):
        for timing, capture in (('v1', 'task_owned_timer'), ('v4', 'shared')):
            with self.subTest(timing=timing, capture=capture), patch.object(control, 'mutate') as mutate:
                with self.assertRaises(control.ControlError):
                    control.run_navigation_baseline(self.host(self.base.child), 1, timing, capture)
                mutate.assert_not_called()

    def test_invalid_policy_capabilities_and_effective_options_reject_before_start(self):
        changes = [('desktopDcSourcePolicyVersion', 1.0), ('desktopDcSourcePolicyVersion', True),
                   ('desktopDcSourcePolicies', [self.POLICY, 'observe-only']),
                   ('configuredDesktopDcSourcePolicy', 'observe-only'), ('effectiveDesktopDcSourcePolicy', None),
                   ('effectiveReadbackMode', 'poll_single_v1'), ('effectiveSourceRetention', 'disabled'),
                   ('effectiveConversion', 'cpu')]
        for key, value in changes:
            child = self.host(self.base.child); child[key] = value
            with self.subTest(key=key, value=value), patch.object(control, 'mutate') as mutate:
                with self.assertRaises(control.ControlError):
                    self.run_baseline(child)
                mutate.assert_not_called()

    def test_running_or_terminal_policy_change_stops_without_refetch_or_replay(self):
        for state in ('running', 'completed'):
            for scope, key, value in (('status', 'configuredDesktopDcSourcePolicy', 'observe-only'),
                                      ('owner', 'gameProcessId', True), ('owner', 'sourcePolicy', None),
                                      ('owner', 'readbackMode', 'blocking')):
                current = self.host(self.base.status(state))
                (current if scope == 'status' else current['navigationBaseline'])[key] = value
                with self.subTest(state=state, key=key), patch.object(control, 'mutate', return_value=current) as mutate, \
                        patch.object(control, 'exchange') as fetch, patch.object(control, 'refresh') as refresh:
                    with self.assertRaises(control.NavigationBaselineError):
                        self.run_baseline()
                    mutate.assert_called_once(); fetch.assert_not_called(); refresh.assert_not_called()

    def test_reset_empty_failure_retains_selected_policy_and_terminal_reason(self):
        terminal = self.host(self.reset.status('failed', error='preparation_readiness_timeout'))
        with patch.object(control, 'mutate', return_value=terminal) as mutate:
            with self.assertRaises(control.NavigationResetError) as failure:
                control.reset_navigation(self.host(self.reset.child), 0, 1, capture_policy='task_owned_timer')
        self.assertEqual(failure.exception.status, terminal)
        self.assertEqual(terminal['navigationReset']['samples'], [])
        mutate.assert_called_once()

    def test_reset_missing_owner_policy_rejected_without_replay(self):
        terminal = self.host(self.reset.status('failed'))
        terminal['navigationReset'].pop('sourcePolicy')
        with patch.object(control, 'mutate', return_value=terminal) as mutate:
            with self.assertRaises(control.ControlError):
                control.reset_navigation(self.host(self.reset.child), 0, 1, capture_policy='task_owned_timer')
        mutate.assert_called_once()

    def test_short_failed_result_retained_without_success_or_repeat(self):
        terminal, full = self.baseline('failed')
        with patch.object(control, 'mutate', return_value=terminal) as mutate, patch.object(control, 'exchange', return_value=full):
            with self.assertRaises(control.NavigationBaselineError) as failure:
                self.run_baseline()
        self.assertEqual(failure.exception.status, full)
        mutate.assert_called_once()

    def test_full_result_and_artifact_policy_cannot_downgrade(self):
        for target in ('result', 'evidence'):
            terminal, full = self.baseline()
            value = full['navigationBaseline']['result']
            if target == 'evidence':
                value = value['evidence']
            value.pop('sourcePolicy')
            with self.subTest(target=target), patch.object(control, 'mutate', return_value=terminal) as mutate, \
                    patch.object(control, 'exchange', return_value=full):
                with self.assertRaises(control.NavigationBaselineError):
                    self.run_baseline()
                mutate.assert_called_once()

    def test_host_full_evidence_cannot_claim_a_wgc_readback_mode(self):
        terminal, full = self.baseline()
        full['navigationBaseline']['result']['evidence']['readbackMode'] = 'poll_single_v1'
        with patch.object(control, 'mutate', return_value=terminal) as mutate, \
                patch.object(control, 'exchange', return_value=full):
            with self.assertRaises(control.NavigationBaselineError):
                self.run_baseline()
        mutate.assert_called_once()

    def test_raw_record_rejects_float_bool_bad_interval_epoch_and_casing(self):
        sample = self.pose(self.base.pose(1), 1)
        for key, value in (('SnapshotId', 1.0), ('SnapshotId', True), ('SnapshotId', 0),
                           ('StartedAtStopwatchTicks', -1), ('CompletedAtStopwatchTicks', 1),
                           ('ClockFrequency', 0), ('CaptureEpoch', 'other')):
            bad = copy.deepcopy(sample); bad['hostSnapshot'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(control.ControlError):
                control._baseline_pose(bad, self.POLICY)
        bad = copy.deepcopy(sample); bad['hostSnapshot']['snapshotId'] = bad['hostSnapshot'].pop('SnapshotId')
        with self.assertRaises(control.ControlError):
            control._baseline_pose(bad, self.POLICY)

    def test_no_mixed_wgc_clock_or_missing_kind_or_unselected_host(self):
        sample = self.pose(self.base.pose(1), 1)
        for key, value in (('sourceTimestamp100ns', None), ('acquiredAtStopwatchTicks', 1), ('sourceKind', None)):
            bad = {**sample, key: value}
            with self.subTest(key=key), self.assertRaises(control.ControlError):
                control._baseline_pose(bad, self.POLICY)
        with self.assertRaises(control.ControlError):
            control._baseline_pose(sample)

    def test_successful_sequence_requires_strict_raw_identity_advance(self):
        first = self.pose(self.base.pose(1), 1)
        second = self.pose(self.base.pose(2), 2)
        control._host_pose_sequence([first, second])
        for key in ('SnapshotId', 'StartedAtStopwatchTicks', 'CompletedAtStopwatchTicks', 'ClockFrequency'):
            bad = copy.deepcopy(second)
            bad['hostSnapshot'][key] = first['hostSnapshot'][key] if key != 'ClockFrequency' else 1
            with self.subTest(key=key), self.assertRaises(control.ControlError):
                control._host_pose_sequence([first, bad])


if __name__ == '__main__':
    unittest.main()
