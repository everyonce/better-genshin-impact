"""Offline checks for SIREN batch continuity, cancellation, process pins and the global time limit."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import resident_runtime as runtime
import run_patrol_series as series
import run_rdp_patrol as patrol
from stream_client import parse_arguments


class SeriesTests(unittest.TestCase):
    """Use synthetic broker, resident and archive evidence. No test starts BetterGI or uses a GPU."""
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.args = series.options(['--batches', '3', '--circuits', '2', '--seconds', '60'])
        self.root = dict(processId=101, windowsSessionId=1, instanceNonce='a'*32, childWindowMinimized=True,
                         uiStatus='current', childSessionId=7, childConnectedState=1, instanceType='Primary')
        self.child = dict(processId=303, windowsSessionId=7, instanceNonce='b'*32, instanceType='ChildSession',
                          automationEnabled=True, remoteDesktop=True, runtimeRunning=True, automationState='game_ready',
                          taskRunning=False, agentStreamRunning=False, agentPipeName='unused')
        self.api = Mock()
        self.api.discover.return_value = {'instances': [self.root, self.child], 'unavailable': []}
        self.api.ControlError = RuntimeError
        self.api.start_agent.return_value = self.child
        host = patch.object(series.socket, 'gethostname', return_value='SIREN')
        host.start()
        self.addCleanup(host.stop)

    def publish(self, args, folder, *, series):
        """Simulate the files left by a successful independently audited two-circuit batch."""
        series.admit(self.api, self.root, self.child)
        rid = f'{int(folder.name[-2:]):032x}'
        patrol.atomic_json(folder/'launcher.json', dict(runId=rid, verified=True, stopReason=None, stopRequested=False))
        patrol.atomic_json(folder/'audit.json', dict(passed=True, verifiedLegs=8, verifiedCircuits=2,
                          routeId=patrol.STREET_PATROL_ROUTE, controllerLeases=1, partialPatrolLegs=[]))
        patrol.atomic_json(folder/'patrol.json.control.json', dict(version=1, runId=rid, command='run'))

    def test_three_independent_batches_have_distinct_outputs_and_cumulative_evidence(self):
        with patch.object(patrol, 'run', side_effect=self.publish) as run:
            summary = series.run_series(self.args, self.folder)
        self.assertEqual((summary['status'], summary['verifiedCircuits'], summary['verifiedLegs']),
                         ('completed', 6, 24))
        self.assertEqual(run.call_count, 3)
        self.assertEqual(len({r['runId'] for r in summary['batches']}), 3)
        self.assertEqual(json.loads((self.folder/'series.json').read_bytes()), summary)

    def test_wrong_host_preexisting_stop_and_expired_global_deadline_do_not_launch(self):
        for condition in ('host', 'stop', 'time'):
            folder = self.folder/condition
            folder.mkdir()
            if condition == 'stop':
                (folder/'STOP').touch()
            with self.subTest(condition=condition), patch.object(patrol, 'run') as run, \
                    patch.object(series.socket, 'gethostname', return_value='OTHER' if condition == 'host' else 'SIREN'), \
                    patch.object(time, 'monotonic_ns', side_effect=[1, 1801_000_000_001] if condition == 'time' else [1, 2]):
                result = series.run_series(self.args, folder)
                self.assertEqual(result['status'], 'stopped')
                run.assert_not_called()

    def test_failed_audit_thermal_telemetry_loss_and_stop_between_batches_never_launch_again(self):
        for cause in ('badAudit', 'temperatureLimit', 'telemetryLost', 'operatorStop', 'stopFile'):
            folder = self.folder/cause
            folder.mkdir()
            def work(*args, **kw):
                self.publish(*args, **kw)
                batch = args[1]
                if cause == 'badAudit':
                    patrol.atomic_json(batch/'audit.json', {'passed': False})
                elif cause == 'operatorStop':
                    patrol.stop_resident(batch, '1'.zfill(32))
                elif cause == 'stopFile':
                    (folder/'STOP').touch()
                else:
                    patrol.atomic_json(batch/'launcher.json', {'verified': False, 'stopReason': cause, 'stopRequested': True})
                    raise RuntimeError('Broker refused')
            with self.subTest(cause=cause), patch.object(patrol, 'run', side_effect=work) as run:
                result = series.run_series(self.args, folder)
                self.assertEqual(result['status'], 'stopped')
                self.assertEqual(run.call_count, 1)
                if cause in ('temperatureLimit', 'telemetryLost'):
                    self.assertEqual(result['reason'], cause)

    def test_previous_pair_must_match_on_first_admission(self):
        guard = series.SeriesGuard(self.folder/'STOP', 60)
        self.addCleanup(guard.finished.set)
        guard.required_identity = {role: {key: row[key] for key in ('processId', 'windowsSessionId', 'instanceNonce')}
                                   for role, row in (('root', self.root), ('child', self.child))}
        with self.assertRaisesRegex(RuntimeError, 'seriesIdentityChanged'):
            guard.admit(self.api, self.root, dict(self.child, instanceNonce='c'*32))
        self.assertIsNone(guard.identity)
        self.assertIsNone(guard.last_proof)

    def test_same_pid_but_different_nonce_and_lost_status_stop_the_series(self):
        guard = series.SeriesGuard(self.folder/'STOP', 1800)
        self.addCleanup(guard.finished.set)
        guard.admit(self.api, self.root, self.child)
        with self.assertRaises(RuntimeError):
            guard.admit(self.api, self.root, dict(self.child, instanceNonce='c'*32))
        guard = series.SeriesGuard(self.folder/'STOP', 1800)
        self.addCleanup(guard.finished.set)
        guard.admit(self.api, self.root, self.child)
        self.api.refresh.side_effect = RuntimeError('Nonce mismatch')
        with patch.object(guard.finished, 'wait', return_value=False):
            guard.watch_identity(self.api, self.root, self.child)
        self.assertEqual(guard.stop_reason(), 'seriesIdentityUnavailable')

    def test_new_stop_file_releases_only_pinned_control_with_existing_supervisor(self):
        rid = 'd'*32
        guard = series.SeriesGuard(self.folder/'STOP', 1800)
        guard.stop_file.touch()
        patrol.atomic_json(self.folder/'patrol.json.control.json', {'version': 1, 'runId': rid, 'command': 'run'})
        state = dict(runId=rid, stopReason=None, stopRequested=False)
        future = Mock()
        future.done.side_effect = [False, True]
        with patch.object(patrol, 'wait'), patch.object(patrol, 'log_sample', return_value={'temperatureC': 61}):
            patrol.supervise(future, self.folder, None, float('inf'), state, guard)
        self.assertEqual((state['stopReason'], state['stopRequested']), ('seriesOperatorStop', True))
        self.assertEqual(patrol.addressed_control(self.folder/'patrol.json.control.json', rid)['command'], 'stop')
        guard.stop_file.unlink()
        self.assertEqual(guard.stop_reason(), 'seriesOperatorStop')

    def test_expired_series_binding_does_not_even_load_policy(self):
        guard = series.SeriesGuard(self.folder/'STOP', 1800)
        guard.admit(self.api, self.root, self.child)
        self.addCleanup(guard.finished.set)
        guard.deadline_ns = time.monotonic_ns() - 1
        argv = patrol.patrol_argv(self.args, 7, self.folder) + ['--patrol-series-binding='+guard.binding()]
        args = parse_arguments(argv[5:])
        load, episode = Mock(), Mock()
        with patch.object(runtime, 'require_current_rdp'), self.assertRaisesRegex(RuntimeError, 'time bound'):
            runtime.run_resident(args, load, episode)
        load.assert_not_called()
        episode.assert_not_called()

    def test_resident_refuses_replaced_child_rejected_start_or_new_lease(self):
        for issue in ('replaced', 'rejected', 'lostLease'):
            folder = self.folder/issue
            folder.mkdir()
            guard = series.SeriesGuard(folder/'STOP', 1800)
            self.addCleanup(guard.finished.set)
            guard.admit(self.api, self.root, self.child)
            argv = patrol.patrol_argv(self.args, 7, folder) + ['--patrol-series-binding='+guard.binding()]
            self.assertLessEqual(len(argv), 65)
            args = parse_arguments(argv[5:])
            bad_child = dict(self.child, instanceNonce='c'*32) if issue == 'replaced' else self.child
            self.api.discover.return_value = dict(instances=[self.root, bad_child], unavailable=[])
            self.api.start_agent.reset_mock()
            self.api.start_agent.side_effect = RuntimeError('start rejected') if issue == 'rejected' else None
            episode = Mock(return_value=0)
            # This unit test invokes the production admission/reconnect logic with inert model and stream functions.
            with self.subTest(issue=issue), patch.object(runtime, 'control_module', return_value=self.api), \
                    patch.object(runtime, 'require_current_rdp'):
                with self.assertRaises(RuntimeError):
                    runtime.run_resident(args, lambda _: None, episode)
                self.assertEqual(json.loads(Path(args.output).read_bytes())['status'], 'failed')
                self.assertEqual(self.api.start_agent.call_count, 0 if issue == 'replaced' else 1)
                self.assertEqual(episode.call_count, int(issue == 'lostLease'))


if __name__ == '__main__':
    unittest.main()
