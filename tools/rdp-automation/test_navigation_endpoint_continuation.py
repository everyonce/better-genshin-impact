"""Synthetic endpoint proofs only; no pipe, process, SDK, image or input is opened."""
import copy
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rdp_control as control
import test_navigation_baseline as fixtures
from test_rdp_control import FakePipe

FORWARD = 'mondstadt-city-two-legs-v1'
REVERSE = 'mondstadt-city-reverse-two-legs-v1'
OLD = 'mondstadt-city-leg-1-v1'


class EndpointContinuationTests(unittest.TestCase):
    """The predecessor read is not admission; the one server start owns that transition."""
    def setUp(self):
        self.fixture = fixtures.NavigationBaselineTests()
        self.fixture.setUp()
        self.predecessor = self.fixture.RUN
        self.run = 'b' * 32
        self.capabilities = dict(routeVersion=1, routeProfiles=[OLD, FORWARD, REVERSE],
            endpointContinuationVersion=1, timingContracts=['v1', 'v2', 'v3', 'v4'],
            capturePolicies=['shared', 'task_owned_timer'], timingContract='v4',
            capturePolicy='task_owned_timer', controllerMethod='native-fixed-leg-feedback-v4')
        self.child, self.prior_full = self.fixture.result()
        for row in (self.child, self.prior_full):
            row.update(captureMode='WindowsGraphicsCaptureV2', readbackVersion=1,
                readbackModes=['blocking', 'poll_single_v1'], effectiveReadbackMode='poll_single_v1')
            row['navigationBaseline'].update(self.capabilities, profileId=FORWARD)
        prior = self.prior_full['navigationBaseline']['result']
        prior.update(profileId=FORWARD, routeVersion=1, timingContract='v4', capturePolicy='task_owned_timer',
            controllerMethod='native-fixed-leg-feedback-v4', legs=self.legs(False), waypoint=self.waypoint())
        prior['evidence']['readbackMode'] = 'poll_single_v1'
        source = prior['samples'][-1]
        self.link = dict(version=1, predecessorRunId=self.predecessor, predecessorProfileId=FORWARD,
            predecessorEvidence=copy.deepcopy(prior['evidence']),
            predecessorFinalSource=dict(CaptureEpoch=source['sourceEpoch'],
                SourceTimestamp100ns=source['sourceTimestamp100ns'],
                AcquiredAtStopwatchTicks=source['acquiredAtStopwatchTicks']),
            predecessorCleanupReturnedAtTicks=9999999, runtimeIdentity='c' * 32,
            childProcessId=123, childNonce='child-epoch', windowsSessionId=3, gameProcessId=456,
            gameStartedAtUtcTicks=638982123456789012, captureType='Fischless.GameCapture.Graphics.GraphicsCaptureV2',
            readbackMode='poll_single_v1', physicalInputAcknowledged=False)
        self.terminal = copy.deepcopy(self.child)
        self.terminal['navigationBaseline'].update(runId=self.run, profileId=REVERSE, continuation=copy.deepcopy(self.link))
        self.full = copy.deepcopy(self.terminal)
        self.full['navigationBaseline']['result'] = copy.deepcopy(prior)
        self.full['navigationBaseline']['result'].update(profileId=REVERSE, continuation=copy.deepcopy(self.link), legs=self.legs(True))

    def legs(self, reverse):
        pairs = [(3, 2), (2, 1)] if reverse else [(1, 2), (2, 3)]
        return [dict(legIndex=i, startPointId=a, endPointId=b, outcome='completed')
                for i, (a, b) in enumerate(pairs, 1)]

    def waypoint(self):
        return dict(outcome='completed', error=None, samples=[self.fixture.pose(i + 3) for i in range(3)],
                    anchor=self.fixture.pose(6))

    def invoke(self, *, child=None, predecessor=None, initial=None, full=None, refresh=None):
        events = []
        def read(*args, **kwargs):
            events.append(('read', kwargs['fields']['navigationBaselineRunId']))
            return self.prior_full if kwargs['fields']['navigationBaselineRunId'] == self.predecessor else (full or self.full)
        def start(*args, **kwargs):
            events.append(('start', kwargs))
            return initial or self.terminal
        with patch.object(control, 'exchange', side_effect=read) as query, patch.object(control, 'mutate', side_effect=start) as mutate, \
                patch.object(control, 'refresh', return_value=refresh or self.terminal), \
                patch.object(control.time, 'sleep'), patch.object(control, 'reset_navigation') as reset, \
                patch.object(control, 'set_capture_mode') as mode:
            try:
                return control.run_navigation_baseline(child or self.child, 45, 'v4', 'task_owned_timer',
                    REVERSE, self.predecessor if predecessor is None else predecessor)
            finally:
                reset.assert_not_called(); mode.assert_not_called()
                self.events = events
                self.start_count, self.query_count = mutate.call_count, query.call_count

    def test_success_reads_exact_predecessor_then_starts_once_and_fetches_new_result(self):
        self.assertEqual(self.invoke(), self.full)
        self.assertEqual(self.events, [('read', self.predecessor), ('start', dict(timingContract='v4',
            capturePolicy='task_owned_timer', routeProfile=REVERSE, continuationFromRunId=self.predecessor)), ('read', self.run)])

    def test_capability_and_latest_completed_forward_are_required_before_mutation(self):
        for key, value in [('endpointContinuationVersion', None), ('endpointContinuationVersion', True),
                           ('state', 'failed'), ('state', 'running'), ('profileId', REVERSE), ('runId', 'd' * 32)]:
            child = copy.deepcopy(self.child); child['navigationBaseline'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(control.ControlError): self.invoke(child=child)
            self.assertEqual(self.start_count, 0)

    def test_predecessor_id_is_required_exact_nonzero_n_form(self):
        for value in ['', '0' * 32, 'g' * 32, 'a' * 32, True, 2, '01234567-89ab-cdef-0123-456789abcdef']:
            with self.subTest(value=value), self.assertRaises(control.ControlError): self.invoke(predecessor=value)
            self.assertEqual(self.start_count, 0)
        with patch.object(control, 'mutate') as start, self.assertRaises(control.ControlError):
            control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer', REVERSE)
        start.assert_not_called()

    def test_forward_result_requires_complete_original_asset_order_and_checkpoint(self):
        original = copy.deepcopy(self.prior_full)
        for change in [dict(legs=self.legs(True)), dict(waypoint=None), dict(verified=False),
                       dict(inputReleaseError='failed'), dict(continuation=self.link), dict(profileId=REVERSE)]:
            self.prior_full = copy.deepcopy(original); self.prior_full['navigationBaseline']['result'].update(change)
            with self.subTest(change=change), self.assertRaises(control.ControlError): self.invoke()
            self.assertEqual(self.start_count, 0)

    def test_predecessor_result_read_failure_does_not_start_or_retry(self):
        with patch.object(control, 'exchange', side_effect=OSError('lost result')) as read, \
                patch.object(control, 'mutate') as start, self.assertRaises(control.ControlError):
            control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer', REVERSE, self.predecessor)
        read.assert_called_once(); start.assert_not_called()

    def test_lost_start_acknowledgment_is_not_replayed_or_followed_by_reset(self):
        with patch.object(control, 'exchange', return_value=self.prior_full) as read, \
                patch.object(control, 'mutate', side_effect=control.ControlError('uncertain')) as start, \
                patch.object(control, 'refresh') as refresh, self.assertRaises(control.ControlError):
            control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer', REVERSE, self.predecessor)
        start.assert_called_once(); read.assert_called_once(); refresh.assert_not_called()

    def test_changed_admitted_identity_or_source_is_not_accepted(self):
        changes = [('predecessorRunId', 'd' * 32), ('predecessorProfileId', REVERSE), ('childProcessId', 999),
            ('childNonce', 'other'), ('windowsSessionId', 4), ('gameProcessId', 789), ('readbackMode', 'blocking'),
            ('physicalInputAcknowledged', True), ('runtimeIdentity', '0' * 32), ('gameStartedAtUtcTicks', 0),
            ('predecessorCleanupReturnedAtTicks', 0), ('predecessorEvidence', {}), ('predecessorFinalSource', {})]
        for key, value in changes:
            bad = copy.deepcopy(self.terminal); bad['navigationBaseline']['continuation'][key] = value
            with self.subTest(key=key), self.assertRaises(control.NavigationBaselineError): self.invoke(initial=bad)
            self.assertEqual(self.start_count, 1); self.assertEqual(self.query_count, 1)

    def test_source_wire_case_is_not_silently_normalized(self):
        bad = copy.deepcopy(self.terminal)
        bad['navigationBaseline']['continuation']['predecessorFinalSource'] = dict(captureEpoch='x', sourceTimestamp100ns=1, acquiredAtStopwatchTicks=1)
        with self.assertRaises(control.NavigationBaselineError): self.invoke(initial=bad)

    def test_changed_link_during_polling_fails_without_result_fetch(self):
        running = copy.deepcopy(self.terminal); running['taskRunning'] = True
        running['navigationBaseline'].update(state='running', evidenceComplete=False)
        changed = copy.deepcopy(self.terminal); changed['navigationBaseline']['continuation']['runtimeIdentity'] = 'e' * 32
        with self.assertRaises(control.NavigationBaselineError): self.invoke(initial=running, refresh=changed)
        self.assertEqual(self.start_count, 1); self.assertEqual(self.query_count, 1)

    def test_result_cannot_change_link_after_terminal_snapshot(self):
        bad = copy.deepcopy(self.full); bad['navigationBaseline']['result']['continuation']['runtimeIdentity'] = 'e' * 32
        with self.assertRaises(control.NavigationBaselineError): self.invoke(full=bad)
        self.assertEqual(self.start_count, 1)

    def test_changed_mode_stops_without_reconfiguration(self):
        bad = copy.deepcopy(self.terminal); bad['effectiveReadbackMode'] = 'blocking'
        with self.assertRaises(control.NavigationBaselineError): self.invoke(initial=bad)

    def test_partial_failed_reverse_is_retained_but_not_success(self):
        terminal, full = copy.deepcopy(self.terminal), copy.deepcopy(self.full)
        for value in (terminal, full): value['navigationBaseline'].update(state='failed', error='initial_source_failed')
        full['navigationBaseline']['result'].update(verified=False, error='initial_source_failed', samples=[], legs=[], waypoint=None)
        with self.assertRaises(control.NavigationBaselineError) as error: self.invoke(initial=terminal, full=full)
        self.assertEqual(error.exception.status['navigationBaseline']['result']['continuation'], self.link)
        self.assertEqual(self.start_count, 1)

    def test_completed_reverse_requires_reverse_asset_order(self):
        bad = copy.deepcopy(self.full); bad['navigationBaseline']['result']['legs'] = self.legs(False)
        with self.assertRaises(control.NavigationBaselineError): self.invoke(full=bad)

    def test_predecessor_field_is_forbidden_on_both_forward_selectors(self):
        for route in (OLD, FORWARD):
            with patch.object(control, 'mutate') as start, self.subTest(route=route), self.assertRaises(control.ControlError):
                control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer', route, self.predecessor)
            start.assert_not_called()

    def test_wire_requires_reverse_v4_owned_and_exact_predecessor_before_connect(self):
        good = dict(routeProfile=REVERSE, timingContract='v4', capturePolicy='task_owned_timer', continuationFromRunId=self.predecessor)
        cases = [{**good, 'continuationFromRunId': value} for value in (None, True, '', '0' * 32, 'z' * 32)]
        cases += [{k: v for k, v in good.items() if k != 'continuationFromRunId'},
                  {**good, 'timingContract': 'v3'}, {**good, 'capturePolicy': 'shared'},
                  {**good, 'routeProfile': OLD}, {**good, 'routeProfile': FORWARD}]
        for fields in cases:
            api = FakePipe(self.child)
            with self.subTest(fields=fields), self.assertRaises(control.ControlError):
                control.exchange('startNavigationBaseline', 123, 3, nonce='child-epoch', fields=fields, api=api)
            self.assertFalse(hasattr(api, 'pipe_name'))
        api = FakePipe(self.terminal); api.session = 3
        control.exchange('startNavigationBaseline', 123, 3, nonce='child-epoch', fields=good, api=api)
        self.assertEqual(api.request['continuationFromRunId'], self.predecessor)

    def test_cli_passes_exact_selector_and_predecessor_without_a_reset_command(self):
        with patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                patch.object(control, 'run_navigation_baseline', return_value={}) as run, patch('sys.stdout', new_callable=io.StringIO), \
                patch.object(sys, 'argv', ['rdp_control.py', 'run-navigation-baseline', '--route-profile', REVERSE,
                    '--continuation-from-run-id', self.predecessor, '--timing-contract', 'v4', '--capture-policy', 'task_owned_timer']):
            self.assertEqual(control.main(), 0)
        run.assert_called_once_with(self.child, 45, 'v4', 'task_owned_timer', route_profile=REVERSE, continuation_from_run_id=self.predecessor)

    def test_previous_reverse_can_select_legacy_without_link_but_cannot_reverse_again(self):
        child = copy.deepcopy(self.child); child['navigationBaseline']['profileId'] = REVERSE
        with self.assertRaises(control.ControlError): self.invoke(child=child)
        self.assertEqual(self.start_count, 0)
        terminal, full = self.fixture.result()
        with patch.object(control, 'mutate', return_value=terminal) as start, patch.object(control, 'exchange', return_value=full):
            # Omitted legacy host capabilities exercise unchanged default wire shape.
            legacy = copy.deepcopy(self.fixture.child); legacy['navigationBaseline']['profileId'] = REVERSE
            control.run_navigation_baseline(legacy, 45)
        self.assertNotIn('routeProfile', start.call_args.kwargs)
        self.assertNotIn('continuationFromRunId', start.call_args.kwargs)


class HostEndpointFloorTests(unittest.TestCase):
    """Typed host floors never inherit WGC timestamps or unknown/boolean raw-clock fields."""

    def test_host_floor_rejects_wgc_mixed_and_wrong_converter_shapes(self):
        import test_navigation_courtyard_cycle as courtyard
        fx = courtyard.HostCourtyardFixture()
        original = fx.full['navigationBaseline']['result']['continuation']['predecessorFinalSource']
        values = [dict(CaptureEpoch=original['hostSnapshot']['CaptureEpoch'], SourceTimestamp100ns=1, AcquiredAtStopwatchTicks=1),
                  {**original, 'SourceTimestamp100ns': 1}, {**original, 'kind': 'wgc'},
                  dict(sourceKind=original['kind'], hostSnapshot=original['hostSnapshot'])]
        for value in values:
            with self.subTest(value=value), self.assertRaises(control.ControlError):
                control._baseline_host_floor(value)

    def test_host_raw_floor_requires_exact_positive_clock_integers(self):
        import test_navigation_courtyard_cycle as courtyard
        fx = courtyard.HostCourtyardFixture()
        floor = fx.full['navigationBaseline']['result']['continuation']['predecessorFinalSource']
        for key in ('SnapshotId', 'StartedAtStopwatchTicks', 'CompletedAtStopwatchTicks', 'ClockFrequency'):
            for value in (True, 1.0, 0, -1, 2**63):
                bad = copy.deepcopy(floor); bad['hostSnapshot'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(control.ControlError):
                    control._baseline_host_floor(bad)

    def test_host_latest_predecessor_lineage_keeps_earlier_floor_and_runtime(self):
        import test_navigation_courtyard_cycle as courtyard
        for key, value in [('runtimeIdentity', 'e' * 32), ('gameStartedAtUtcTicks', 123),
                           ('childAssemblySha256', 'e' * 64)]:
            fx = courtyard.HostCourtyardFixture(); fx.configure(fx.invoke(), courtyard.FORWARD, 'e' * 32)
            fx.full['navigationBaseline']['result']['continuation'][key] = value
            with self.subTest(key=key), self.assertRaises(control.NavigationBaselineError): fx.invoke()
            self.assertEqual(1, fx.starts)


if __name__ == '__main__':
    unittest.main()
