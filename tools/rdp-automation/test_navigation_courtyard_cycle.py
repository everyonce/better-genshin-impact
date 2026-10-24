"""Explicit opposite-direction CLI transactions over fake, immutable terminal reports."""
import copy
import io
import sys
import unittest
from unittest.mock import patch

import rdp_control as control
import test_navigation_endpoint_continuation as old
from test_rdp_control import FakePipe

FORWARD = 'mondstadt-city-courtyard-forward-v1'
RETURN = 'mondstadt-city-courtyard-return-v1'


class CourtyardContinuationTests(unittest.TestCase):
    def setUp(self):
        self.seed = old.EndpointContinuationTests(); self.seed.setUp()
        self.configure(self.short(), RETURN, 'd' * 32)

    def short(self):
        previous = copy.deepcopy(self.seed.prior_full)
        previous['navigationBaseline'].update(profileId=old.OLD)
        previous['navigationBaseline']['result'].update(profileId=old.OLD, routeVersion=None, legs=[], waypoint=None)
        return previous

    def configure(self, previous, requested, next_id):
        """A prior full result is the sole predecessor; no unretained ancestor is fabricated."""
        self.requested = requested
        self.prior = copy.deepcopy(previous)
        self.child = copy.deepcopy(previous); self.child['navigationBaseline'].pop('result', None)
        self.predecessor = self.child['navigationBaseline']['runId']
        self.terminal = copy.deepcopy(self.child)
        operation = self.terminal['navigationBaseline']
        previous_result = self.prior['navigationBaseline']['result']
        source = previous_result['samples'][-1]
        link = copy.deepcopy(self.seed.link)
        link.update(predecessorRunId=self.predecessor, predecessorProfileId=previous_result['profileId'],
                    predecessorEvidence=copy.deepcopy(previous_result['evidence']),
                    predecessorFinalSource=dict(CaptureEpoch=source['sourceEpoch'], SourceTimestamp100ns=source['sourceTimestamp100ns'],
                                                AcquiredAtStopwatchTicks=source['acquiredAtStopwatchTicks']))
        operation.update(runId=next_id, profileId=requested, continuation=link)
        self.full = copy.deepcopy(self.terminal)
        measured = copy.deepcopy(previous_result)
        measured.update(profileId=requested, continuation=copy.deepcopy(link), legs=[dict(legIndex=1, startPointId=2 if requested == RETURN else 1, endPointId=1 if requested == RETURN else 2, outcome='completed')], waypoint=None, routeVersion=1)
        self.full['navigationBaseline']['result'] = measured
        for pose in [measured['initialSample'], *measured['samples'], *measured['verificationSamples']]: pose['legIndex'] = 1
        for status in (self.prior, self.child, self.terminal, self.full):
            status['navigationBaseline']['routeProfiles'] = [old.OLD, old.FORWARD, old.REVERSE, RETURN, FORWARD]
            status['navigationBaseline'].update(shadowCaptureVersion=1, shadowCaptureModes=[control.SHADOW_CAPTURE_MODE])

    def invoke(self, shadow=None, lost=False):
        events = []
        def read(*args, **kwargs):
            run = kwargs['fields']['navigationBaselineRunId']; events.append(('read', run))
            return self.prior if run == self.predecessor else self.full
        def start(*args, **kwargs):
            events.append(('start', kwargs))
            if lost: raise control.ControlError('lost acknowledgement')
            return self.terminal
        with patch.object(control, 'exchange', side_effect=read), patch.object(control, 'mutate', side_effect=start) as mutation, \
                patch.object(control, 'refresh', return_value=self.terminal), patch.object(control, 'reset_navigation') as reset, \
                patch.object(control, 'set_capture_mode') as mode, patch.object(control.time, 'sleep'):
            try:
                return control.run_navigation_baseline(self.child, 45, 'v4', 'task_owned_timer',
                    route_profile=self.requested, continuation_from_run_id=self.predecessor, shadow_capture=shadow)
            finally:
                self.events = events; self.starts = mutation.call_count
                reset.assert_not_called(); mode.assert_not_called()

    def test_short_return_forward_return_are_separate_one_shot_transactions(self):
        previous = self.invoke()
        for profile, run_id in ((FORWARD, 'e' * 32), (RETURN, 'f' * 32)):
            self.assertEqual(self.starts, 1)
            self.assertEqual([row[0] for row in self.events], ['read', 'start', 'read'])
            self.configure(previous, profile, run_id)
            previous = self.invoke()
            self.assertEqual(previous['navigationBaseline']['result']['waypoint'], None)
            self.assertEqual(len(previous['navigationBaseline']['result']['legs']), 1)
        self.assertEqual(self.starts, 1)

    def test_missing_new_advertisement_refuses_before_predecessor_read(self):
        self.child['navigationBaseline']['routeProfiles'].remove(RETURN)
        with self.assertRaises(control.ControlError): self.invoke()
        self.assertEqual(self.events, [])

    def test_direction_pairs_reject_wrong_completed_predecessor_before_mutation(self):
        for requested, wrong in ((RETURN, RETURN), (RETURN, old.FORWARD), (RETURN, old.REVERSE),
                                 (FORWARD, old.OLD), (FORWARD, old.FORWARD), (FORWARD, FORWARD), (old.REVERSE, FORWARD)):
            self.setUp(); self.requested = requested; self.child['navigationBaseline']['profileId'] = wrong
            with self.subTest(requested=requested, wrong=wrong), self.assertRaises(control.ControlError): self.invoke()
            self.assertEqual(self.starts, 0)

    def test_latest_exact_completed_reverse_remains_required(self):
        for key, value in [('runId', 'e' * 32), ('state', 'failed'), ('state', 'running'), ('endpointContinuationVersion', True)]:
            self.setUp(); self.child['navigationBaseline'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(control.ControlError): self.invoke()
            self.assertEqual(self.starts, 0)

    def test_prior_own_link_must_match_its_compact_proof(self):
        self.configure(self.invoke(), FORWARD, "e" * 32)
        self.prior['navigationBaseline']['result']['continuation']['runtimeIdentity'] = 'e' * 32
        with self.assertRaises(control.ControlError): self.invoke()
        self.assertEqual(self.starts, 0)

    def test_prior_claimed_direction_must_be_a_valid_pair(self):
        self.configure(self.invoke(), FORWARD, "e" * 32)
        for row in (self.child, self.prior): row['navigationBaseline']['continuation']['predecessorProfileId'] = old.REVERSE
        self.prior['navigationBaseline']['result']['continuation']['predecessorProfileId'] = old.REVERSE
        with self.assertRaises(control.ControlError): self.invoke()
        self.assertEqual(self.starts, 0)

    def test_wrong_current_asset_order_is_rejected_after_one_start(self):
        self.full['navigationBaseline']['result']['legs'][0]['startPointId'] = 3
        with self.assertRaises(control.NavigationBaselineError): self.invoke()
        self.assertEqual(self.starts, 1)

    def test_new_link_must_name_actual_reverse_predecessor(self):
        for row in (self.terminal, self.full): row['navigationBaseline']['continuation']['predecessorProfileId'] = old.FORWARD
        self.full['navigationBaseline']['result']['continuation']['predecessorProfileId'] = old.FORWARD
        with self.assertRaises(control.NavigationBaselineError): self.invoke()
        self.assertEqual(self.starts, 1)

    def test_same_child_cannot_hide_changed_server_runtime_or_process_start(self):
        for key, value in [('runtimeIdentity', 'e' * 32), ('gameStartedAtUtcTicks', 123), ('captureType', 'other')]:
            self.setUp(); self.configure(self.invoke(), FORWARD, 'e' * 32)
            for row in (self.terminal, self.full): row['navigationBaseline']['continuation'][key] = value
            self.full['navigationBaseline']['result']['continuation'][key] = value
            with self.subTest(key=key), self.assertRaises(control.NavigationBaselineError): self.invoke()
            self.assertEqual(self.starts, 1)

    def test_selected_predecessor_needs_archive_for_either_next_selector(self):
        for summary in ('missing', None, {'mode': control.SHADOW_CAPTURE_MODE, 'workerRetired': False}):
            for next_shadow in (None, control.SHADOW_CAPTURE_MODE):
                self.setUp()
                for row in (self.child, self.prior): row['navigationBaseline']['shadowCapture'] = control.SHADOW_CAPTURE_MODE
                if summary != 'missing': self.prior['navigationBaseline']['result']['evidence']['shadowCapture'] = summary
                with self.subTest(summary=summary, next=next_shadow), self.assertRaises(control.ControlError): self.invoke(next_shadow)
                self.assertEqual(self.starts, 0)

    def test_unselected_predecessor_rejects_unexpected_archive(self):
        self.prior['navigationBaseline']['result']['evidence']['shadowCapture'] = {'workerRetired': True}
        with self.assertRaises(control.ControlError): self.invoke()
        self.assertEqual(self.starts, 0)

    def test_lost_ack_is_one_mutation_and_no_reconciliation_retry(self):
        with self.assertRaisesRegex(control.ControlError, 'lost acknowledgement'): self.invoke(lost=True)
        self.assertEqual(self.starts, 1)
        self.assertEqual([event[0] for event in self.events], ['read', 'start'])

    def test_wire_requires_exact_new_selector_contract_before_connect(self):
        good = dict(routeProfile=RETURN, timingContract='v4', capturePolicy='task_owned_timer', continuationFromRunId=self.predecessor)
        for fields in [{**good, 'continuationFromRunId': value} for value in (None, True, '', '0' * 32)] + [
                {**good, 'timingContract': 'v3'}, {**good, 'capturePolicy': 'shared'}]:
            api = FakePipe(self.child)
            with self.subTest(fields=fields), self.assertRaises(control.ControlError):
                control.exchange('startNavigationBaseline', 123, 3, nonce='child-epoch', fields=fields, api=api)
            self.assertFalse(hasattr(api, 'pipe_name'))
        api = FakePipe(self.terminal); api.session = 3
        control.exchange('startNavigationBaseline', 123, 3, nonce='child-epoch', fields=good, api=api)
        self.assertEqual(api.request['routeProfile'], RETURN)

    def test_cli_uses_named_direction_and_predecessor(self):
        with patch.object(control, 'discover', return_value={'instances': [self.child]}), \
                patch.object(control, 'run_navigation_baseline', return_value={}) as run, patch('sys.stdout', new_callable=io.StringIO), \
                patch.object(sys, 'argv', ['rdp_control.py', 'run-navigation-baseline', '--route-profile', RETURN,
                    '--continuation-from-run-id', self.predecessor, '--timing-contract', 'v4', '--capture-policy', 'task_owned_timer']):
            self.assertEqual(control.main(), 0)
        run.assert_called_once_with(self.child, 45, 'v4', 'task_owned_timer', route_profile=RETURN, continuation_from_run_id=self.predecessor)

    def test_one_leg_shape_rejects_midpoint_second_leg_and_wrong_pose_index(self):
        for field, value in [('waypoint', self.seed.waypoint()), ('legs', self.seed.legs(True))]:
            self.setUp(); self.full['navigationBaseline']['result'][field] = value
            with self.subTest(field=field), self.assertRaises(control.NavigationBaselineError): self.invoke()
            self.assertEqual(self.starts, 1)
        self.setUp(); self.full['navigationBaseline']['result']['samples'][-1]['legIndex'] = 2
        with self.assertRaises(control.NavigationBaselineError): self.invoke()
        self.assertEqual(self.starts, 1)

    def test_ordinary_short_preserves_legacy_result_shape(self):
        for key, value in [('routeVersion', 1), ('legs', self.seed.legs(False)), ('waypoint', self.seed.waypoint())]:
            self.setUp(); self.prior['navigationBaseline']['result'][key] = value
            with self.subTest(key=key), self.assertRaises(control.ControlError): self.invoke()
            self.assertEqual(self.starts, 0)

    def test_failed_result_retains_partial_one_leg_and_never_replays(self):
        for row in (self.full, self.terminal): row['navigationBaseline'].update(state='failed', error='Climb')
        self.full['navigationBaseline']['result'].update(verified=False, error='Climb', samples=[])
        self.full['navigationBaseline']['result']['legs'][0]['outcome'] = 'failed'
        with self.assertRaises(control.NavigationBaselineError) as caught: self.invoke()
        self.assertEqual(self.starts, 1)
        self.assertEqual(caught.exception.status['navigationBaseline']['result']['legs'][0]['outcome'], 'failed')


class HostCourtyardFixture:
    """Fake host lifecycle over the recorded DTO; only listed policy/owner/identity values are synthetic."""

    def __init__(self):
        import test_navigation_desktop_dc as desktop
        self.desktop = desktop.DesktopNativeControlTests()
        self.recorded = desktop.RECORDED_R41_CHILD_STATUS
        self.wgc = CourtyardContinuationTests(); self.wgc.setUp()
        short = self.status(self.wgc.short())
        self.encode_result(short['navigationBaseline']['result'], 1)
        self.configure(short, RETURN, 'd' * 32)

    def status(self, prototype):
        """Keep actual top-level field names/build/path while adding the proposed host owner capability."""
        status = self.desktop.host(self.recorded)
        operation = copy.deepcopy(prototype['navigationBaseline'])
        operation.update(sourcePolicy=self.desktop.POLICY, readbackMode=None,
                         endpointContinuationVersion=2, hostEndpointContinuationVersion=1,
                         timingContract='v4', controllerMethod='native-fixed-leg-feedback-v4',
                         capturePolicy='task_owned_timer', gameProcessId=456,
                         windowsSessionId=status['windowsSessionId'], shadowCapture=None,
                         routeProfiles=[old.OLD, old.FORWARD, old.REVERSE, RETURN, FORWARD])
        status['navigationBaseline'] = operation
        return status

    def encode_result(self, result, first):
        """Explicitly synthetic increasing raw host acquisitions; no WGC timestamps survive."""
        result.update(sourcePolicy=self.desktop.POLICY, timingContract='v4',
                      capturePolicy='task_owned_timer', controllerMethod='native-fixed-leg-feedback-v4')
        result['evidence'].update(sourcePolicy=self.desktop.POLICY, readbackMode=None)
        result['initialSample'] = self.desktop.pose(result['initialSample'], first)
        result['samples'] = [self.desktop.pose(value, first + 9 + index)
                             for index, value in enumerate(result['samples'])]
        for value in [result['initialSample'], *result['samples']]:
            value['legIndex'] = 1
        result['verificationSamples'] = copy.deepcopy(result['samples'])

    def configure(self, previous, requested, next_id):
        """Retain only the immediately preceding result and make one separately admitted synthetic run."""
        self.requested, self.prior = requested, copy.deepcopy(previous)
        self.child = copy.deepcopy(previous); self.child['navigationBaseline'].pop('result', None)
        self.predecessor = self.child['navigationBaseline']['runId']
        prior = self.prior['navigationBaseline']['result']
        final = prior['samples'][-1]['hostSnapshot']
        link = copy.deepcopy(self.wgc.seed.link)
        link.update(version=2, sourcePolicy=self.desktop.POLICY, readbackMode=None,
                    captureType='Fischless.GameCapture.DesktopDc.DesktopDcCapture',
                    childAssemblySha256=self.child['assemblySha256'].lower(),
                    childProcessId=self.child['processId'], windowsSessionId=self.child['windowsSessionId'],
                    childNonce=self.child['instanceNonce'], gameProcessId=456,
                    predecessorRunId=self.predecessor, predecessorProfileId=prior['profileId'],
                    predecessorCleanupReturnedAtTicks=final['CompletedAtStopwatchTicks'] + 100,
                    predecessorEvidence=copy.deepcopy(prior['evidence']),
                    predecessorFinalSource=dict(kind=self.desktop.POLICY, hostSnapshot=copy.deepcopy(final)))
        self.terminal = copy.deepcopy(self.child)
        self.terminal['navigationBaseline'].update(runId=next_id, profileId=requested,
            continuation=dict(version=2, predecessorRunId=self.predecessor, predecessorProfileId=prior['profileId']))
        self.full = copy.deepcopy(self.terminal)
        measured = copy.deepcopy(prior)
        measured.update(profileId=requested, continuation=link, routeVersion=1, waypoint=None,
            legs=[dict(legIndex=1, startPointId=2 if requested == RETURN else 1,
                       endPointId=1 if requested == RETURN else 2, outcome='completed')])
        self.encode_result(measured, final['SnapshotId'] + 1)
        for value in [measured['initialSample'], *measured['samples'], *measured['verificationSamples']]:
            value['legIndex'] = 1
        self.full['navigationBaseline']['result'] = measured

    def invoke(self, **options):
        """Reuse the existing one-mutation fake transport without creating a pipe or subprocess."""
        return CourtyardContinuationTests.invoke(self, **options)


class HostCourtyardContinuationTests(unittest.TestCase):
    """Host full2/compact2 transactions retain typed evidence and exact immediate-predecessor identity."""

    def setUp(self):
        self.fx = HostCourtyardFixture()
        for guard in (patch.object(control.transport, 'WinPipeApi', side_effect=AssertionError('No native pipe')),
                      patch('subprocess.Popen', side_effect=AssertionError('No subprocess'))):
            guard.start(); self.addCleanup(guard.stop)

    def test_short_return_forward_return_keep_raw_host_proof_and_one_mutation_each(self):
        result = self.fx.invoke()
        for profile, run_id in ((FORWARD, 'e' * 32), (RETURN, 'f' * 32)):
            self.assertEqual(1, self.fx.starts)
            self.assertEqual(['read', 'start', 'read'], [row[0] for row in self.fx.events])
            self.assertEqual(2, result['navigationBaseline']['result']['continuation']['version'])
            self.assertEqual(3, len(result['navigationBaseline']['continuation']))
            self.assertNotIn('sourceTimestamp100ns', result['navigationBaseline']['result']['initialSample'])
            self.fx.configure(result, profile, run_id)
            result = self.fx.invoke()
        self.assertEqual(1, self.fx.starts)

    def test_recorded_dto_identity_is_used_without_invented_top_level_game_pid(self):
        self.assertNotIn('gameProcessId', self.fx.child)
        self.assertNotIn('role', self.fx.child)
        self.assertEqual(self.fx.recorded['appDirectory'], self.fx.child['appDirectory'])
        self.assertEqual(self.fx.recorded['assemblySha256'], self.fx.child['assemblySha256'])
        self.assertEqual('ChildSession', self.fx.child['instanceType'])
        self.fx.invoke()

    def test_exact_host_capability_is_required_before_any_read_or_mutation(self):
        for value in (None, False, True, 0, 2, 1.0, '1'):
            fx = HostCourtyardFixture(); fx.child['navigationBaseline']['hostEndpointContinuationVersion'] = value
            with self.subTest(value=value), self.assertRaises(control.ControlError): fx.invoke()
            self.assertEqual([], fx.events)

    def test_host_never_uses_full_status1_or_missing_build_identity(self):
        for target, key, value in [('owner', 'endpointContinuationVersion', 1),
                                   ('top', 'assemblySha256', None), ('top', 'appDirectory', '')]:
            fx = HostCourtyardFixture()
            (fx.child['navigationBaseline'] if target == 'owner' else fx.child)[key] = value
            with self.subTest(key=key), self.assertRaises(control.ControlError): fx.invoke()
            self.assertEqual(0, fx.starts)

    def test_predecessor_result_response_cannot_hide_changed_build_path_or_policy(self):
        for key, value in [('assemblySha256', 'e' * 64), ('appDirectory', 'D:/other/'),
                           ('effectiveDesktopDcSourcePolicy', 'observe-only')]:
            fx = HostCourtyardFixture(); fx.prior[key] = value
            with self.subTest(key=key), self.assertRaises(control.ControlError): fx.invoke()
            self.assertEqual(0, fx.starts)

    def test_admitted_and_later_status_preserve_build_path_policy_and_capability(self):
        for later in (False, True):
            for target, key, value in [('top', 'assemblySha256', 'e' * 64), ('top', 'appDirectory', 'D:/other/'),
                                     ('top', 'effectiveDesktopDcSourcePolicy', 'observe-only'),
                                     ('owner', 'hostEndpointContinuationVersion', 1.0)]:
                fx = HostCourtyardFixture()
                changed = copy.deepcopy(fx.terminal)
                (changed['navigationBaseline'] if target == 'owner' else changed)[key] = value
                if later:
                    running = copy.deepcopy(fx.terminal)
                    running['navigationBaseline']['state'] = 'running'; running['taskRunning'] = True
                    fx.terminal = running
                    with patch.object(control, 'refresh', return_value=changed), \
                            patch.object(control, 'exchange', return_value=fx.prior), \
                            patch.object(control, 'mutate', return_value=running) as mutate, patch.object(control.time, 'sleep'):
                        with self.subTest(key=key, later=later), self.assertRaises(control.NavigationBaselineError):
                            control.run_navigation_baseline(fx.child, 45, 'v4', 'task_owned_timer',
                                route_profile=RETURN, continuation_from_run_id=fx.predecessor)
                        mutate.assert_called_once()
                else:
                    fx.terminal = changed
                    with self.subTest(key=key, later=later), self.assertRaises(control.NavigationBaselineError): fx.invoke()
                    self.assertEqual(1, fx.starts)

    def test_terminal_result_response_preserves_build_even_with_equal_owner(self):
        for key, value in [('assemblySha256', 'e' * 64), ('appDirectory', 'D:/other/')]:
            fx = HostCourtyardFixture(); fx.full[key] = value
            with self.subTest(key=key), self.assertRaises(control.NavigationBaselineError): fx.invoke()
            self.assertEqual(1, fx.starts)

    def test_full_host_link_rejects_wgc_or_changed_build_policy_readback_and_capture_type(self):
        for key, value in [('version', 1), ('version', 2.0), ('sourcePolicy', None),
                           ('childAssemblySha256', 'e' * 64), ('readbackMode', 'blocking'),
                           ('captureType', 'Fischless.GameCapture.Graphics.GraphicsCaptureV2'),
                           ('physicalInputAcknowledged', True)]:
            fx = HostCourtyardFixture(); fx.full['navigationBaseline']['result']['continuation'][key] = value
            with self.subTest(key=key), self.assertRaises(control.NavigationBaselineError): fx.invoke()
            self.assertEqual(1, fx.starts)

    def test_typed_floor_must_match_exact_predecessor_acquisition(self):
        for key, value in [('SnapshotId', 99), ('StartedAtStopwatchTicks', 99), ('ClockFrequency', 1),
                           ('CaptureEpoch', '11234567-89ab-cdef-0123-456789abcdef')]:
            fx = HostCourtyardFixture()
            fx.full['navigationBaseline']['result']['continuation']['predecessorFinalSource']['hostSnapshot'][key] = value
            with self.subTest(key=key), self.assertRaises(control.NavigationBaselineError): fx.invoke()
            self.assertEqual(1, fx.starts)

    def test_start_strictly_advances_id_and_both_clocks_in_same_epoch_frequency(self):
        for key in ('SnapshotId', 'StartedAtStopwatchTicks', 'CompletedAtStopwatchTicks', 'CaptureEpoch', 'ClockFrequency'):
            fx = HostCourtyardFixture(); result = fx.full['navigationBaseline']['result']
            floor = fx.prior['navigationBaseline']['result']['samples'][-1]['hostSnapshot']
            if key == 'CaptureEpoch':
                result['initialSample']['sourceEpoch'] = '11234567-89ab-cdef-0123-456789abcdef'
                value = result['initialSample']['sourceEpoch']
            elif key == 'ClockFrequency': value = floor[key] + 1
            else: value = floor[key]
            result['initialSample']['hostSnapshot'][key] = value
            with self.subTest(key=key), self.assertRaises(control.NavigationBaselineError): fx.invoke()
            self.assertEqual(1, fx.starts)

    def test_host_multileg_shadow_and_wrong_pair_never_mutate(self):
        for profile, shadow in [(old.FORWARD, None), (old.REVERSE, None), (RETURN, control.SHADOW_CAPTURE_MODE), (FORWARD, None)]:
            fx = HostCourtyardFixture(); fx.requested = profile
            with self.subTest(profile=profile, shadow=shadow), self.assertRaises(control.ControlError): fx.invoke(shadow=shadow)
            self.assertEqual(0, fx.starts)

    def test_failed_start_retains_guard_failure_and_no_pose_without_replay(self):
        for row in (self.fx.terminal, self.fx.full):
            row['navigationBaseline'].update(state='failed', phase='preparing', error='predecessor_source_floor_not_advanced')
        self.fx.full['navigationBaseline']['result'].update(verified=False, error='predecessor_source_floor_not_advanced',
            initialSample=None, samples=[], verificationSamples=[], legs=[])
        with self.assertRaises(control.NavigationBaselineError) as caught: self.fx.invoke()
        self.assertEqual(1, self.fx.starts)
        self.assertIsNone(caught.exception.status['navigationBaseline']['result']['initialSample'])

    def test_lost_ack_never_retries_or_reconciles(self):
        with self.assertRaisesRegex(control.ControlError, 'lost acknowledgement'): self.fx.invoke(lost=True)
        self.assertEqual(1, self.fx.starts)
        self.assertEqual(['read', 'start'], [row[0] for row in self.fx.events])


if __name__ == '__main__': unittest.main()
