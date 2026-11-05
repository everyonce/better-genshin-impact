"""Inert launcher tests: no named pipe, RDP, game, or native input is invoked."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


def load(path, name):
    """Load the implementation without entering its CLI."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launcher = load(Path(__file__).with_name('run-rdp-route.py'), '_test_launcher')


class Fixture:
    """Keep real files and complete worker control flow behind inert status and route boundaries."""
    def __init__(self, root, count=1):
        self.root = root
        self.app = root / 'app'
        self.pilot = self.app / 'User/JsScript/ActOnePilot'
        self.pilot.mkdir(parents=True)
        self.output = root / 'out'
        self.output.mkdir()
        self.child = dict(processId=20, windowsSessionId=3, instanceNonce='child-nonce',
            instanceType='ChildSession', remoteDesktop=True, rootProcessId=10,
            runtimeRunning=True, taskRunning=False, serviceOwnsPilot=False,
            scriptSession='old', scriptState='stopped', pilotState='stopped',
            heartbeatFresh=False, heartbeatAtUnixMs=None, activeRequestId=None, appDirectory=str(self.app))
        self.parent = dict(processId=10, windowsSessionId=1, instanceNonce='root-nonce',
            instanceType='Primary', automationEnabled=True, childSessionId=3,
            childConnectedState=1, childWindowMinimized=True)
        self.owner = dict(root=copy.deepcopy(self.parent), child=copy.deepcopy(self.child))
        self.commands = []
        self.calls = []
        self.fail_start = False
        self.foreign_request = False
        self.route_status = 'arrived'
        self.on_route = None
        self.clock = 0
        self.game = dict(processId=30, windowsSessionId=3, executable='game.exe', startedFileTime=123, hwnd=40)
        self.config = dict(version=1, launchId='owned-token', owner=self.owner, output=str(self.output),
            progress=str(root / 'progress.json'), routes=[], expectedUid='123456789', node='node',
            allowFieldCombat=True, allowDialogue=True, deadlineMs=1000, maxSegments=1,
            continueObjectives=['Next objective'], stopFiles=[str(root / 'STOP')])
        for index in range(count):
            route = self.output / f'route-{index}.json'
            route.write_text(json.dumps(dict(objective='Explore for Adventure Rank',
                waypoints=[dict(map='Teyvat', x=index, y=2)], customEvidence={'kept': True})), encoding='utf-8')
            self.config['routes'].append(dict(path=str(route), sha256=hashlib.sha256(route.read_bytes()).hexdigest()))

    def run(self, *args):
        """Return an authenticated-looking status only to the isolated worker under test."""
        return copy.deepcopy(self.child)

    def exchange(self, request, *args):
        """Simulate exact service ownership without dispatching any command."""
        if isinstance(request, str):
            return copy.deepcopy(self.parent)
        self.commands.append(request['command'])
        assert request['targetNonce'] == 'child-nonce'
        if request['command'] == 'startPilot':
            self.child.update(serviceOwnsPilot=True, taskRunning=True, scriptSession='new-owned',
                              heartbeatFresh=True, scriptState='idle', pilotState='idle')
            if self.fail_start:
                raise RuntimeError('uncertain start transport')
        else:
            self.child.update(serviceOwnsPilot=False, taskRunning=False, heartbeatFresh=False,
                              scriptState='stopped', pilotState='stopped')
        return copy.deepcopy(self.child)

    def execute(self, argv, output, timeout):
        """Retain native-shaped canonical progress for the real worker to join."""
        self.calls.append(argv)
        session = argv[argv.index('--session') + 1]
        progress = Path(argv[argv.index('--progress') + 1])
        request = dict(id='own-' + str(len(self.calls)), session=session, mission='navigation')
        written = dict(request, id='foreign') if self.foreign_request else request
        (self.pilot / 'request.json').write_text(json.dumps(written))
        report = dict(status=self.route_status, session=session, nextWaypointIndex=1,
                      pending=request if self.route_status == 'pending' else None,
                      records=[] if self.route_status == 'pending' else [dict(request=request)])
        progress.write_text(json.dumps(report))
        if self.route_status == 'pending':
            (self.pilot / '.route-controller.lock').write_text('canonical unresolved lease')
        if self.on_route:
            self.on_route()
        return 0 if self.route_status == 'arrived' else 2

    def sleep(self, seconds):
        """Advance only the fake cleanup clock."""
        self.clock += seconds

    def worker(self):
        """Execute production lifecycle code with all live boundaries replaced."""
        return launcher.run_worker(self.config, control=self, rdp=self, execute=self.execute,
                                   game_probe=lambda *unused: copy.deepcopy(self.game),
                                   monotonic=lambda: self.clock, sleep=self.sleep)


class LauncherTests(unittest.TestCase):
    """Exercise ownership, single-use evidence, option propagation, and serial leg boundaries."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_single_leg_owns_start_stop_and_keeps_exact_progress(self):
        f = Fixture(self.root)
        result = f.worker()
        self.assertEqual(result['status'], 'arrived', result)
        self.assertEqual(f.commands, ['startPilot', 'stopPilot'])
        self.assertEqual(f.calls[0][f.calls[0].index('--progress') + 1], f.config['progress'])
        self.assertTrue(result['pilotRetired'])
        self.assertTrue(result['groupRemoved'])
        self.assertTrue(result['leaseRemoved'])
        self.assertTrue((f.pilot / 'request.json').exists())

    def test_serial_routes_use_one_pilot_and_separate_original_route_progress(self):
        f = Fixture(self.root, 2)
        result = f.worker()
        self.assertEqual(result['status'], 'arrived', result)
        self.assertEqual(f.commands, ['startPilot', 'stopPilot'])
        self.assertEqual(len(f.calls), 2)
        self.assertNotEqual(result['legs'][0]['progress'], result['legs'][1]['progress'])
        self.assertEqual(launcher.read(f.config['progress'])['kind'], 'rdp-route-chain-v1')
        self.assertNotIn('--continue-from-progress', f.calls[0])
        self.assertEqual(f.calls[1][f.calls[1].index('--continue-from-progress') + 1],
                         result['legs'][0]['progress'])

    def test_failed_leg_never_advances_and_keeps_primary_result(self):
        f = Fixture(self.root, 2)
        f.route_status = 'stopped'
        result = f.worker()
        self.assertEqual(len(f.calls), 1)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['legs'][0]['status'], 'stopped')
        self.assertTrue(result['pilotRetired'])

    def test_pending_leg_retires_only_its_session_and_retains_both_leases(self):
        f = Fixture(self.root, 2)
        f.route_status = 'pending'
        result = f.worker()
        self.assertEqual(len(f.calls), 1)
        self.assertTrue(result['pilotRetired'])
        self.assertTrue((f.pilot / '.route-controller.lock').exists())
        self.assertTrue((f.pilot / '.rdp-route-launcher.lock').exists())

    def test_uncertain_start_is_not_replayed_or_adopted(self):
        f = Fixture(self.root)
        f.fail_start = True
        result = f.worker()
        self.assertEqual(f.commands, ['startPilot'])
        self.assertFalse(result['pilotRetired'])
        self.assertFalse(f.calls)
        self.assertTrue((f.pilot / '.rdp-route-launcher.lock').exists())

    def test_foreign_request_is_never_stopped_or_deleted(self):
        f = Fixture(self.root)
        f.foreign_request = True
        result = f.worker()
        self.assertEqual(f.commands, ['startPilot'])
        self.assertFalse(result['pilotRetired'])
        self.assertEqual(launcher.read(f.pilot / 'request.json')['id'], 'foreign')

    def test_existing_group_is_validated_reused_and_never_removed(self):
        f = Fixture(self.root)
        path = f.app / 'User/ScriptGroup/ActOneRun.json'
        path.parent.mkdir(parents=True)
        original = json.dumps(launcher.group_template('preexisting')).encode()
        path.write_bytes(original)
        result = f.worker()
        self.assertEqual(result['status'], 'arrived', result)
        self.assertEqual(path.read_bytes(), original)
        self.assertNotIn('groupRemoved', result)

    def test_group_mismatch_and_active_task_refuse_before_start(self):
        for mode in ('group', 'active'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                f = Fixture(Path(directory))
                if mode == 'active':
                    f.child['taskRunning'] = True
                else:
                    path = f.app / 'User/ScriptGroup/ActOneRun.json'
                    path.parent.mkdir(parents=True)
                    path.write_text(json.dumps(dict(name='ActOneRun', projects=[])))
                result = f.worker()
                self.assertEqual(result['status'], 'failed')
                self.assertFalse(f.commands)

    def test_stop_before_start_or_second_route_never_dispatches_later_work(self):
        f = Fixture(self.root, 2)
        f.on_route = lambda: Path(f.config['stopFiles'][0]).touch()
        result = f.worker()
        self.assertEqual(len(f.calls), 1)
        self.assertTrue(result['pilotRetired'])
        self.assertIn('STOP', result['error'])

    def test_existing_chain_progress_is_not_overwritten(self):
        f = Fixture(self.root, 2)
        path = Path(f.config['progress'])
        path.write_bytes(b'original')
        result = f.worker()
        self.assertEqual(path.read_bytes(), b'original')
        self.assertFalse(f.commands)
        self.assertEqual(result['status'], 'failed')

    def test_replaced_owner_and_unminimized_or_ambiguous_pair_refuse(self):
        f = Fixture(self.root)
        for change in ('nonce', 'minimized', 'duplicate'):
            with self.subTest(change=change):
                root, child = copy.deepcopy(f.parent), copy.deepcopy(f.child)
                if change == 'nonce':
                    child['instanceNonce'] = 'replacement'
                if change == 'minimized':
                    root['childWindowMinimized'] = False
                rows = [root, child, copy.deepcopy(child)] if change == 'duplicate' else [root, child]
                with self.assertRaises(RuntimeError):
                    launcher.select_owner(dict(instances=rows, unavailable=[]), expected_owner=f.owner)

    def test_original_route_and_all_controller_options_are_forwarded(self):
        f = Fixture(self.root)
        argv = launcher.route_argv(f.config, 'new-owned', f.config['routes'][0]['path'], f.config['progress'])
        for option in ('--controller', '--allow-field-combat', '--allow-dialogue', '--continue-objective', '--stop-file'):
            self.assertIn(option, argv)
        self.assertEqual(launcher.read(argv[3])['customEvidence'], dict(kept=True))
        self.assertEqual(argv[argv.index('--expected-uid') + 1], '123456789')

    def canonical(self):
        """Read the actual canonical parser, with a mirror override for pre-integration qualification."""
        path = Path(os.environ.get('BETTERGI_ROUTE_TEST_CLI', Path.cwd() / 'tools/quest-pilot/act-one-route.py'))
        return load(path, '_canonical_route_for_launcher')

    def console(self, f, broker):
        """Use real document preparation with an inert, single-call broker boundary."""
        node = self.root / 'node.exe'
        node.touch()
        args = launcher.parse_args(['--route', f.config['routes'][0]['path'], '--progress', str(self.root / 'console.json'),
                                    '--expected-uid', '123456789', '--node', str(node)])
        rdp = SimpleNamespace(discover=lambda: dict(instances=[f.parent, f.child], unavailable=[]), run_command=broker)
        return args, (rdp, None, self.canonical())

    def test_console_copies_original_bytes_and_joins_worker_retirement(self):
        f = Fixture(self.root)
        source = Path(f.config['routes'][0]['path'])
        original = source.read_bytes()
        def broker(root, argv, work_dir, python_exe, timeout, job_dir, output_limit):
            self.assertIsInstance(work_dir, str)
            self.assertIsInstance(job_dir, str)
            """Run only the inert worker fixture behind the public console admission."""
            f.config = launcher.read(argv[-2])
            self.assertEqual(Path(f.config['routes'][0]['path']).read_bytes(), original)
            result = f.worker()
            return dict(returnCode=result['exitCode'], timedOut=False)
        boundary = mock.Mock(side_effect=broker)
        args, dependencies = self.console(f, boundary)
        result = launcher.run(args, expected_owner=f.owner, dependencies=dependencies)
        self.assertEqual(result['status'], 'arrived', result)
        self.assertTrue(result['pilotRetired'])
        self.assertEqual(source.read_bytes(), original)
        boundary.assert_called_once()

    def test_console_expected_owner_mismatch_refuses_before_broker(self):
        f = Fixture(self.root)
        boundary = mock.Mock()
        args, dependencies = self.console(f, boundary)
        f.child['instanceNonce'] = 'new-child'
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            launcher.run(args, expected_owner=f.owner, dependencies=dependencies)
        boundary.assert_not_called()
        self.assertFalse((self.root / 'console.rdp').exists())

    def test_uncertain_broker_is_called_once_and_failed_evidence_survives(self):
        f = Fixture(self.root)
        boundary = mock.Mock(side_effect=RuntimeError('uncertain broker retirement'))
        args, dependencies = self.console(f, boundary)
        result = launcher.run(args, expected_owner=f.owner, dependencies=dependencies)
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['pilotRetired'])
        self.assertEqual(result['error'], 'uncertain broker retirement')
        self.assertEqual(launcher.read(result['launcherResult']), result)
        self.assertTrue((self.root / 'console.rdp/launch.json').is_file())
        boundary.assert_called_once()

    def test_actual_canonical_parser_receives_flags_and_previous_progress(self):
        f = Fixture(self.root)
        cli = self.canonical()
        previous = self.root / 'previous.json'
        argv = launcher.route_argv(f.config, 'new-owned', f.config['routes'][0]['path'], f.config['progress'], previous)
        pilot = SimpleNamespace(close=mock.Mock())
        report = dict(status='arrived', nextWaypointIndex=1)
        with mock.patch.object(cli, 'GuardedPilot', return_value=pilot), \
                mock.patch.object(cli, 'run_controller', return_value=report) as run, \
                mock.patch('sys.argv', argv[2:]), contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(cli.main())
        options = run.call_args.kwargs
        self.assertTrue(options['allow_dialogue'])
        self.assertTrue(options['allow_field_combat'])
        self.assertEqual(options['continue_from_progress'], previous)
        self.assertEqual(options['continuation_objectives'], ['Next objective'])
        pilot.close.assert_called_once()

    def test_native_group_defaults_cannot_enable_unrelated_actions(self):
        group = launcher.group_template('owned')
        launcher.validate_group(group)
        for key in ('enabled', 'jsScriptUseEnabled', 'autoRunEnabled', 'autoFightEnabled', 'autoEatEnabled'):
            with self.subTest(key=key):
                unsafe = copy.deepcopy(group)
                del unsafe['config']['pathingConfig'][key]
                with self.assertRaisesRegex(RuntimeError, 'Unrelated'):
                    launcher.validate_group(unsafe)

    def test_replaced_game_or_foreground_refuses_next_leg_but_retires_owned_pilot(self):
        for key, value in [('startedFileTime', 124), ('hwnd', 41)]:
            with self.subTest(key=key):
                f = Fixture(self.root / key, 2)
                f.on_route = lambda: f.game.update({key: value})
                result = f.worker()
                self.assertEqual(len(f.calls), 1)
                self.assertEqual(result['status'], 'failed')
                self.assertIn('Game lifetime or foreground', result['error'])
                self.assertTrue(result['pilotRetired'])
                self.assertEqual(f.commands, ['startPilot', 'stopPilot'])

    def test_game_probe_uses_installed_path_and_os_session_lifetime(self):
        import ctypes
        f = Fixture(self.root)
        executable = self.root / 'GenshinImpact.exe'
        executable.touch()
        launcher.save(f.app / 'User/config.json', dict(genshinStartConfig=dict(installPath=str(executable))))
        game = dict(processId=30, windowsSessionId=3, executable=str(executable.resolve()), startedFileTime=123)
        user = SimpleNamespace(GetForegroundWindow=mock.Mock(return_value=40),
                               GetWindowThreadProcessId=mock.Mock())
        def window_pid(hwnd, pid):
            """Set the actual ctypes output parameter without calling Windows."""
            self.assertEqual(hwnd, 40)
            pid._obj.value = 30
            return 1
        user.GetWindowThreadProcessId.side_effect = window_pid
        identity = mock.Mock(side_effect=lambda unused: copy.deepcopy(game))
        with mock.patch.object(ctypes, 'WinDLL', return_value=user), \
                mock.patch.dict('sys.modules', child_runner=SimpleNamespace(process_identity=identity)):
            self.assertEqual(launcher.foreground_game(f.app, 3), dict(game, hwnd=40))
            game['windowsSessionId'] = 4
            with self.assertRaisesRegex(RuntimeError, 'configured game'):
                launcher.foreground_game(f.app, 3)
            game.update(windowsSessionId=3, executable=str(self.root / 'foreign.exe'))
            with self.assertRaisesRegex(RuntimeError, 'configured game'):
                launcher.foreground_game(f.app, 3)

    def test_cli_timeout_retires_only_its_process_and_never_replays(self):
        child = mock.Mock()
        child.wait.side_effect = [launcher.subprocess.TimeoutExpired('canonical', 1), 0]
        with mock.patch.object(launcher.subprocess, 'Popen', return_value=child) as start:
            with self.assertRaisesRegex(RuntimeError, 'never replayed'):
                launcher.execute_route(['canonical'], self.root, 1)
        start.assert_called_once()
        child.terminate.assert_called_once()

    def test_stop_error_still_confirms_known_retirement_and_preserves_route_outcome(self):
        for route_status in ('arrived', 'stopped'):
            for error in ('lost stop acknowledgement', 'not_owned: task already retired'):
                with self.subTest(route_status=route_status, error=error):
                    f = Fixture(self.root / (route_status + str(len(list(self.root.iterdir())))))
                    f.route_status = route_status
                    exchange = f.exchange
                    def retire_without_ack(request, *args):
                        """Retire the exact owned task, then lose/refuse its reply."""
                        value = exchange(request, *args)
                        if isinstance(request, dict) and request['command'] == 'stopPilot':
                            raise RuntimeError(error)
                        return value
                    f.exchange = retire_without_ack
                    result = f.worker()
                    self.assertTrue(result['pilotRetired'], result)
                    self.assertTrue(result['groupRemoved'])
                    self.assertTrue(result['leaseRemoved'])
                    self.assertEqual(result['stopError'], error)
                    self.assertEqual(result['cleanupErrors'], [])
                    self.assertEqual(f.commands, ['startPilot', 'stopPilot'])
                    self.assertEqual(result['status'], 'arrived' if route_status == 'arrived' else 'failed')
                    if route_status == 'stopped':
                        self.assertIn('Canonical route did not verify arrival', result['error'])

    def test_stop_error_never_accepts_a_replacement_session(self):
        f = Fixture(self.root)
        f.route_status = 'stopped'
        exchange = f.exchange
        def changed_session(request, *args):
            """The readback must refuse a new task after a failed stop reply."""
            value = exchange(request, *args)
            if isinstance(request, dict) and request['command'] == 'stopPilot':
                f.child.update(scriptSession='foreign', serviceOwnsPilot=True, taskRunning=True)
                raise RuntimeError('lost stop acknowledgement')
            return value
        f.exchange = changed_session
        result = f.worker()
        self.assertFalse(result['pilotRetired'])
        self.assertIn('Canonical route did not verify arrival', result['error'])
        self.assertEqual(result['cleanupErrors'], ['Script session changed during retirement.'])
        self.assertEqual(f.commands, ['startPilot', 'stopPilot'])
        self.assertTrue((f.app / 'User/ScriptGroup/ActOneRun.json').exists())
        self.assertTrue((f.pilot / '.rdp-route-launcher.lock').exists())

    def test_stop_error_leaves_unresolved_session_reserved_after_one_bounded_poll(self):
        f = Fixture(self.root)
        f.route_status = 'stopped'
        exchange = f.exchange
        def not_cancelled(request, *args):
            """A transport failure grants no retirement when the owned task remains active."""
            if isinstance(request, dict) and request['command'] == 'stopPilot':
                f.commands.append('stopPilot')
                raise RuntimeError('stop transport failed')
            return exchange(request, *args)
        f.exchange = not_cancelled
        result = f.worker()
        self.assertFalse(result['pilotRetired'])
        self.assertIn('Canonical route did not verify arrival', result['error'])
        self.assertEqual(result['cleanupErrors'], ['Owned pilot retirement is unresolved.'])
        self.assertEqual(f.commands, ['startPilot', 'stopPilot'])
        self.assertGreaterEqual(f.clock, 20)
        self.assertLess(f.clock, 20.3)
        self.assertTrue((f.pilot / '.rdp-route-launcher.lock').exists())


if __name__ == '__main__':
    unittest.main()
