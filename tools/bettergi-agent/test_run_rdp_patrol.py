"""Exercise the monitored patrol launcher without invoking the GPU, game, or broker."""
import json
from concurrent.futures import Future
from pathlib import Path
from queue import SimpleQueue
import tempfile
import time
from threading import Event
import unittest
from unittest.mock import Mock, patch

import run_rdp_patrol as patrol
from stream_client import parse_arguments


class PatrolLauncherTests(unittest.TestCase):
    """Keep session selection, addressed stops and evidence qualification independently testable."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.run_id = 'a'*32
        self.root = dict(instanceType='Primary', automationEnabled=True, processId=101, windowsSessionId=1,
                         instanceNonce='host', uiStatus='current', childSessionId=7, childConnectedState=1,
                         childWindowMinimized=True)
        self.child = dict(instanceType='ChildSession', automationEnabled=True, processId=202, windowsSessionId=7,
                          instanceNonce='child', remoteDesktop=True, uiStatus='current', runtimeRunning=True,
                          automationState='game_ready', taskRunning=False, agentStreamRunning=False)
        self.discovery = dict(instances=[self.root, self.child], unavailable=[])
        self.api = Mock(wraps=patrol.control_module())
        self.api.discover.return_value = self.discovery

    def publish(self, run_id):
        """Simulate the two files a resident creates before loading its model."""
        patrol.atomic_json(self.folder/'patrol.json.status.json', {'version': 1, 'runId': run_id})
        patrol.atomic_json(self.folder/'patrol.json.control.json', {'version': 1, 'runId': run_id, 'command': 'run'})

    def test_a_single_declared_extension_leg_keeps_the_original_timing_and_input_guards(self):
        args=patrol.options(['--route','mondstadt-stair-post-v1','--legs','1','--remember-hybrid-bypass'])
        command=patrol.patrol_argv(args,7,self.folder)
        import time
        binding=f"--patrol-series-binding=101:{'a'*32}:202:{'b'*32}:{time.monotonic_ns()+120_000_000_000}"
        parsed=parse_arguments(command[5:]+[binding])
        self.assertEqual((parsed.hybrid_route,parsed.hybrid_legs),('mondstadt-stair-post-v1',1))
        self.assertTrue(parsed.remember_hybrid_bypass)
        self.assertEqual((parsed.max_observation_age_ms,parsed.action_hold_ms,parsed.decision_hz),(150,100,10))
        self.assertEqual(parsed.record_max_mib,160)
        for extra in (['--hybrid-legs','5'],['--max-observation-age-ms','151'],['--action-hold-ms','101']):
            with self.subTest(extra=extra),self.assertRaises(SystemExit):parse_arguments(command[5:]+[binding]+extra)

    def test_route_extensions_require_explicit_bounds_and_keep_existing_photo_permissions(self):
        for arguments in (['--route','mondstadt-stair-post-v1'],['--legs','5'],
                          ['--route','mondstadt-street-extension-12-v1','--legs','1'],
                          ['--remember-hybrid-bypass'],['--route','mondstadt-stair-post-v1','--legs','1','--camera-calibration','unused']):
            with self.subTest(arguments=arguments),self.assertRaises(SystemExit):patrol.options(arguments)

    def test_executed_history_command_selects_short_hold_without_climb_recovery(self):
        """The explicit experiment keeps all observation and input limits while serializing feedback."""
        from hybrid_routes import SCOUT_GRASS_ROUTE
        from navigation_profiles import SCOUT_PROFILE
        from reviewed_scout_route import ReviewedScoutRoute
        spec=ReviewedScoutRoute(((-1135,2267),(-1135,2280)))
        geometry=self.folder/'reviewed-route.json'
        geometry.write_text(json.dumps(spec.document()),encoding='utf-8')
        for hold in (50,60):
            with self.subTest(hold=hold):
                args=patrol.options(['--route',SCOUT_GRASS_ROUTE,'--legs','1','--navigation-profile',SCOUT_PROFILE,
                    '--seconds','35','--retain-policy-rgb','--native-combat-observation'])
                args.p2p_executed_history,args.action_hold_ms=True,hold
                command=patrol.patrol_argv(args,7,self.folder)
                self.assertIn('--p2p-executed-history',command)
                self.assertNotIn('--navigation-climb-recovery',command)
                route_index=command.index('--hybrid-route')
                command[route_index:route_index+2]=['--reviewed-scout-route',str(geometry)]
                binding=f"--patrol-series-binding=101:{'a'*32}:202:{'b'*32}:{time.monotonic_ns()+120_000_000_000}"
                parsed=parse_arguments(command[5:]+[binding])
                self.assertTrue(parsed.p2p_executed_history)
                self.assertFalse(parsed.navigation_climb_recovery)
                self.assertEqual((parsed.action_hold_ms,parsed.max_observation_age_ms,parsed.decision_hz),(hold,150,10))
                self.assertEqual((parsed.history,parsed.fps,parsed.hybrid_legs),(41,20,1))

    def test_argv_builder_rejects_undeclared_or_incompatible_short_holds(self):
        """The internal scout mode cannot silently alter ordinary patrol timing."""
        for enabled,hold in ((False,50),(False,60),(True,100),(True,True),('true',50)):
            args=patrol.options([])
            args.p2p_executed_history,args.action_hold_ms=enabled,hold
            with self.subTest(enabled=enabled,hold=hold),self.assertRaises(ValueError):
                patrol.patrol_argv(args,7,self.folder)

    def test_discover_requires_one_current_minimized_and_idle_authenticated_pair(self):
        self.assertEqual(patrol.ready_session(self.api), (self.root, self.child))
        for record, key, bad in [
                (self.root, 'childWindowMinimized', False), (self.root, 'uiStatus', 'cached'),
                (self.root, 'windowsSessionId', 7), (self.root, 'instanceNonce', ''), (self.root, 'childSessionId', 9),
                (self.child, 'automationState', 'starting'), (self.child, 'uiStatus', 'unavailable'),
                (self.child, 'taskRunning', True), (self.child, 'agentStreamRunning', True),
                (self.child, 'rootProcessId', 303), (self.child, 'remoteDesktop', False),
                (self.child, 'automationEnabled', False), (self.discovery, 'unavailable', ['unresponsive']),
                (self.discovery, 'instances', [self.root, self.child, self.child.copy()])]:
            with self.subTest(key=key), patch.dict(record, {key: bad}), self.assertRaises(Exception):
                patrol.ready_session(self.api)

    def test_generated_command_uses_supported_flags_and_only_addressed_session(self):
        args = patrol.options(['--circuits', '2', '--steering-shadow', str(self.folder/'head.json'),
                               '--landmark-shadow', str(self.folder/'landmark.json'),
                               '--camera-calibration', str(self.folder/'calibration.json')])
        argv = patrol.patrol_argv(args, 7, self.folder)
        self.assertLessEqual(len(argv), 65)
        self.assertIn('--steering-shadow=' + str(self.folder/'head.json'), argv)
        self.assertIn('--landmark-shadow=' + str(self.folder/'landmark.json'), argv)
        self.assertIn('--camera-calibration=' + str(self.folder/'calibration.json'), argv)
        parsed = parse_arguments(argv[5:])
        self.assertEqual((parsed.hybrid_route, parsed.hybrid_legs, parsed.rdp_session_id),
                         (patrol.STREET_PATROL_ROUTE, 8, 7))
        self.assertEqual(parsed.landmark_shadow, str(self.folder/'landmark.json'))
        self.assertEqual(parsed.record_dir, str(self.folder/'patrol-recording'))
        self.assertEqual(parsed.record_max_mib, 160)
        self.assertTrue(parsed.enable_input and parsed.resident and parsed.cuda_graph)
        self.assertFalse(any(a.startswith(('--steering-shadow', '--landmark-shadow', '--camera-calibration')) for a in
                             patrol.patrol_argv(patrol.options([]), 7, self.folder)))
        maximum = patrol.options(['--circuits', '32', '--seconds', '600'])
        self.assertEqual(parse_arguments(patrol.patrol_argv(maximum, 7, self.folder)[5:]).hybrid_legs, 128)

    def test_invalid_or_replaced_control_authority_cannot_be_stopped(self):
        self.publish(self.run_id)
        self.assertEqual(patrol.pin_resident(self.folder), self.run_id)
        self.publish('b'*32)
        with self.assertRaises(ValueError):
            patrol.pin_resident(self.folder, self.run_id)
        with self.assertRaises(ValueError):
            patrol.stop_resident(self.folder, self.run_id)
        self.assertEqual(json.loads((self.folder/'patrol.json.control.json').read_text())['command'], 'run')

    def test_status_sharing_violation_only_retried_on_initial_pin(self):
        self.publish(self.run_id)
        status = json.dumps({'version': 1, 'runId': self.run_id})
        with patch.object(Path, 'read_text', side_effect=[PermissionError(13, 'busy'), status]) as read, \
                patch.object(patrol.time, 'sleep') as delay:
            self.assertEqual(patrol.pin_resident(self.folder), self.run_id)
            self.assertEqual(patrol.pin_resident(self.folder, self.run_id), self.run_id)
            self.assertEqual(read.call_count, 2)
            delay.assert_called_once()
        with patch.object(Path, 'read_text', side_effect=PermissionError(13, 'busy')) as read, \
                patch.object(patrol.time, 'sleep'), self.assertRaises(PermissionError):
            patrol.pin_resident(self.folder)
        self.assertEqual(read.call_count, 5)
        with patch.object(Path, 'read_text', return_value='{') as read, self.assertRaises(ValueError):
            patrol.pin_resident(self.folder)
        read.assert_called_once()

    def test_native_qpc_brackets_only_an_actual_addressed_write(self):
        self.publish(self.run_id)
        evidence = {}
        path = self.folder/'patrol.json.control.json'
        observed_commands = []
        def sample():
            observed_commands.append(patrol.addressed_control(path,self.run_id)['command'])
            return (10_000_000, 300 + len(observed_commands))
        with patch.object(patrol,'native_qpc_sample',side_effect=sample):
            self.assertTrue(patrol.stop_resident(self.folder,self.run_id,timing=evidence))
            self.assertFalse(patrol.stop_resident(self.folder,self.run_id,timing={}))
        self.assertEqual(observed_commands,['run','stop'])
        self.assertEqual(evidence['addressedStopQpc'],dict(clock='windows-query-performance-counter',
            frequencyHz=10_000_000,beforeTicks=301,afterTicks=302))

    def test_unavailable_or_inconsistent_clock_never_prevents_stop(self):
        for samples in ([None], [(10, 20), None], [(10, 20), (11, 21)], [(10, 20), (10, 19)]):
            self.publish(self.run_id)
            evidence = {}
            with self.subTest(samples=samples), patch.object(patrol,'native_qpc_sample',side_effect=samples):
                self.assertTrue(patrol.stop_resident(self.folder,self.run_id,timing=evidence))
                self.assertEqual(evidence,{})
                self.assertEqual(patrol.addressed_control(self.folder/'patrol.json.control.json',self.run_id)['command'],'stop')

    def test_retry_sharing_on_control_preserves_uuid_and_fails_immediately_on_invalid_content(self):
        doc = {'version': 1, 'runId': self.run_id, 'command': 'pause'}
        with patch.object(patrol, 'read_control_document', side_effect=[
                (None, '[WinError 32] sharing violation'), (doc, None)]) as read, patch.object(patrol.time, 'sleep'):
            self.assertEqual(patrol.addressed_control(self.folder/'control', self.run_id), doc)
            self.assertEqual(read.call_args_list[0], read.call_args_list[1])
        with patch.object(patrol, 'read_control_document', return_value=(None, 'Expected this run ID')) as read, \
                self.assertRaises(ValueError):
            patrol.addressed_control(self.folder/'control', self.run_id)
        read.assert_called_once()

    def test_monitor_preserves_operator_pause_and_stop_while_status_is_unreadable(self):
        self.publish(self.run_id)
        for command in ('pause', 'stop'):
            path = self.folder/'patrol.json.control.json'
            patrol.atomic_json(path, {'version': 1, 'runId': self.run_id, 'command': command})
            state = dict(stopReason=None, runId=self.run_id, stopRequested=False)
            future = Mock()
            future.done.side_effect = [False, True]
            with self.subTest(command=command), patch.object(Path, 'read_text', side_effect=PermissionError(13, 'busy')), \
                    patch.object(patrol, 'log_sample', return_value={'temperatureC': 60}), \
                    patch.object(patrol, 'wait'), patch.object(patrol, 'atomic_json') as write:
                patrol.supervise(future, self.folder, 'uninvoked', float('inf'), state)
                self.assertIsNone(state['stopReason'])
                self.assertFalse(state['stopRequested'])
                if command == 'stop':
                    patrol.stop_resident(self.folder, self.run_id)
                write.assert_not_called()
            self.assertEqual(json.loads(path.read_text())['command'], command)

    def test_initial_identity_fault_never_addresses_a_replacement(self):
        self.publish(self.run_id)
        patrol.atomic_json(self.folder/'patrol.json.status.json', {'version': 1, 'runId': 'b'*32})
        future = Mock()
        future.done.side_effect = [False, False, True]
        state = dict(stopReason=None, runId=None, stopRequested=False)
        with patch.object(patrol, 'log_sample', return_value={'temperatureC': 59}), \
                patch.object(patrol, 'wait', side_effect=lambda *a, **kw: self.publish('b'*32)):
            patrol.supervise(future, self.folder, 'uninvoked', float('inf'), state)
        self.assertEqual(state['stopReason'], 'invalidResidentControl')
        self.assertIsNone(state['runId'])
        self.assertFalse(state['stopRequested'])
        self.assertEqual(json.loads((self.folder/'patrol.json.control.json').read_text())['command'], 'run')

    def test_telemetry_sampling_rejects_empty_multiple_or_invalid_gpu_rows(self):
        for row in ['', 'N/A, 0, 1, 20', '77, 0, nan, 20', '77, 0, 1, inf', '0, 0, 1, 20', '78,0,1,12\n60,0,1,12']:
            with self.subTest(row=row), patch.object(patrol.subprocess, 'run', return_value=Mock(stdout=row)):
                self.assertIn('error', patrol.log_sample(self.folder, 'uninvoked'))
        with patch.object(patrol.subprocess, 'run', return_value=Mock(stdout='75, 98, 990, 42.0\n')):
            self.assertEqual(patrol.log_sample(self.folder, 'uninvoked')['temperatureC'], 75)
        self.assertEqual(len((self.folder/'gpu.jsonl').read_text().splitlines()), 7)

    def test_hot_and_missing_telemetry_refuse_dispatch(self):
        for sample, reason in [({'temperatureC': 78}, 'temperatureLimit'), ({'error': 'missing'}, 'telemetryLost')]:
            args = patrol.options([])
            existing = self.folder/'existing'
            existing.touch()
            for name in ('gpu_python', 'runner_python', 'ffmpeg', 'nvidia_smi', 'goal_embedding', 'checkpoint'):
                setattr(args, name, existing)
            args.source = self.folder
            with self.subTest(sample=sample), patch.object(patrol, 'control_module', return_value=self.api), \
                    patch.object(patrol, 'log_sample', return_value=sample), self.assertRaises(RuntimeError):
                patrol.run(args, self.folder)
            self.api.run_command.assert_not_called()
            self.assertEqual(json.loads((self.folder/'launcher.json').read_text())['stopReason'], reason)

    def test_operator_marker_reaches_resident_while_gpu_query_is_pending(self):
        self.publish(self.run_id)
        started, released = Event(), Event()
        broker = Future()
        state = dict(stopReason=None, runId=self.run_id, stopRequested=False)
        series = Mock(stop_observation=None)
        series.stop_reason.side_effect = lambda: 'seriesOperatorStop' if started.is_set() else None

        def sample(*_):
            started.set()
            return {'temperatureC':60} if released.wait(2) else {'error':'GPU query outlasted the stop'}

        original_stop = patrol.stop_resident
        def finish(folder, run_id, *, timing=None):
            written = original_stop(folder, run_id, timing=timing)
            released.set()
            broker.set_result(None)
            return written

        with patch.object(patrol, 'log_sample', side_effect=sample), patch.object(patrol, 'stop_resident', side_effect=finish), \
                patch.object(patrol, 'native_qpc_sample', side_effect=[(10_000_000, 60), (10_000_000, 72)]):
            patrol.supervise(broker, self.folder, None, float('inf'), state, series)
        self.assertEqual(state['stopReason'], 'seriesOperatorStop')
        self.assertEqual((state['addressedStopQpc']['beforeTicks'], state['addressedStopQpc']['afterTicks']), (60, 72))
        self.assertNotIn('telemetryError', state)
        self.assertEqual(patrol.addressed_control(self.folder/'patrol.json.control.json', self.run_id)['command'], 'stop')

    def test_stalled_gpu_monitor_stops_the_original_resident(self):
        self.publish(self.run_id)
        state = dict(stopReason=None, runId=self.run_id, stopRequested=False)
        broker = Mock()
        broker.done.side_effect = [False, True]
        with patch.object(patrol.time, 'monotonic', side_effect=[1,1+patrol.MAX_GPU_SAMPLE_AGE_SECONDS]), \
                patch.object(patrol, 'wait'):
            patrol.supervise_control(broker,Future(),SimpleQueue(),self.folder,float('inf'),state,None)
        self.assertEqual((state['stopReason'],state['stopRequested']), ('telemetryLost',True))
        self.assertEqual(patrol.addressed_control(self.folder/'patrol.json.control.json',self.run_id)['command'], 'stop')

    def test_hot_startup_during_load_and_missing_telemetry_latch_until_resident_id_exists(self):
        for trigger, expected in [({'temperatureC': 78}, 'temperatureLimit'), ({'error': 'timeout'}, 'telemetryLost'),
                                  ({'temperatureC': 60}, 'wallTimeLimit')]:
            state = dict(stopReason=None, runId=None, stopRequested=False)
            self.folder.joinpath('patrol.json.status.json').unlink(missing_ok=True)
            future = Mock()
            future.done.side_effect = [False, False, True]
            with self.subTest(expected=expected), patch.object(patrol, 'log_sample', side_effect=[trigger, {'temperatureC': 60}]), \
                    patch.object(patrol.time, 'monotonic', return_value=10), \
                    patch.object(patrol, 'wait') as wait:
                # The safety condition hits on poll one, while the runner is still starting.
                wait.side_effect = lambda *args, **kwargs: self.publish(self.run_id) if not state['runId'] else None
                patrol.supervise(future, self.folder, 'uninvoked', 10 if expected == 'wallTimeLimit' else 30, state)
            doc = json.loads((self.folder/'patrol.json.control.json').read_text())
            self.assertEqual((doc['runId'], doc['command'], state['stopReason'], state['stopRequested']),
                             (self.run_id, 'stop', expected, True))

    def test_clean_broker_exit_requires_independent_circuit_audit(self):
        args = patrol.options(['--circuits', '2'])
        binary = self.folder/'existing'
        binary.touch()
        for name in ('gpu_python', 'runner_python', 'ffmpeg', 'nvidia_smi', 'goal_embedding', 'checkpoint'):
            setattr(args, name, binary)
        args.source = self.folder
        args.camera_calibration = binary
        args.steering_shadow = self.folder/'steering.json'
        args.steering_shadow.touch()
        args.landmark_shadow = self.folder/'landmark.json'
        args.landmark_shadow.touch()
        self.publish(self.run_id)
        patrol.atomic_json(self.folder/'patrol.json', {'runId': self.run_id, 'endReason': 'hybridLegLimit'})
        self.api.run_command.return_value = {'success': True, 'returnCode': 0, 'timedOut': False}
        with patch.object(patrol, 'control_module', return_value=self.api), \
                patch.object(patrol, 'log_sample', return_value={'temperatureC': 55}), \
                patch('audit_hybrid_run.audit', autospec=True, return_value={'verifiedCircuits': 2}) as audit:
            patrol.run(args, self.folder)
        self.api.run_command.assert_called_once()
        self.assertEqual((audit.call_args.kwargs['minimum_circuits'], audit.call_args.kwargs['minimum_legs']), (2, 8))
        self.assertEqual((audit.call_args.kwargs['camera_checkpoint'], audit.call_args.kwargs['minimum_calibrated_actions']),
                         (binary.resolve(), 1))
        self.assertEqual(audit.call_args.kwargs['shadow_checkpoint'], args.steering_shadow.resolve())
        self.assertEqual(audit.call_args.kwargs['landmark_checkpoint'], args.landmark_shadow.resolve())
        self.assertEqual(audit.call_args.kwargs['ffmpeg'], str(args.ffmpeg.resolve()))
        self.assertTrue(json.loads((self.folder/'launcher.json').read_text())['verified'])
        self.assertTrue((self.folder/'broker.json').exists() and (self.folder/'audit.json').exists())


if __name__ == '__main__':
    unittest.main()
