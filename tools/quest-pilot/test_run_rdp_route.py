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

    def execute(self, argv, output, timeout, *, on_progress=None):
        """Retain native-shaped canonical progress for the real worker to join."""
        self.calls.append(argv)
        session = argv[argv.index('--session') + 1]
        progress = Path(argv[argv.index('--progress') + 1])
        request = dict(id='own-' + str(len(self.calls)), session=session, mission='navigation')
        written = dict(request, id='foreign') if self.foreign_request else request
        (self.pilot / 'request.json').write_text(json.dumps(written))
        count = len(launcher.read(argv[3])['waypoints'])
        report = dict(status=self.route_status, session=session, nextWaypointIndex=count,
                      pending=request if self.route_status == 'pending' else None,
                      records=[] if self.route_status == 'pending' else [dict(request=request)])
        progress.write_text(json.dumps(report))
        if self.route_status == 'pending':
            (self.pilot / '.route-controller.lock').write_text('canonical unresolved lease')
        if self.on_route:
            self.on_route()
        if on_progress:
            on_progress()
        return 0 if self.route_status == 'arrived' else 2

    def sleep(self, seconds):
        """Advance only the fake cleanup clock."""
        self.clock += seconds

    def worker(self, **options):
        """Execute production lifecycle code with all live boundaries replaced."""
        return launcher.run_worker(self.config, control=self, rdp=self, execute=self.execute,
                                   game_probe=lambda *unused: copy.deepcopy(self.game),
                                   monotonic=lambda: self.clock, sleep=self.sleep, **options)


class LauncherTests(unittest.TestCase):
    """Exercise ownership, single-use evidence, option propagation, and serial leg boundaries."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    @contextlib.contextmanager
    def gpu_fixture(self, fixture, *, accepted=3, model='open-p2p-150M', native_ready=True):
        """Exercise real publication, readiness and retirement with a pinned inert Windows process."""
        fixture.config['gpuAdviser'] = True
        repo = self.root / 'synthetic GPU install'
        python = repo / 'artifacts/agent/envs/gamescaling/Scripts/python.exe'
        script = repo / 'tools/quest-pilot/gpu_adviser.py'
        for path in (python,script):
            path.parent.mkdir(parents=True,exist_ok=True)
            path.touch()
        process, job = mock.Mock(pid=451), mock.Mock()
        process.poll.return_value = None
        identity = dict(session='new-owned',processId=20,windowsSessionId=3,gameProcessId=30)
        output = fixture.output / 'gpu-adviser'
        def spawn(argv, **kwargs):
            self.assertEqual(argv[:3],[str(python),'-B',str(script)])
            self.assertEqual(argv[argv.index('--launcher-pid')+1],str(os.getpid()))
            self.assertEqual(argv[argv.index('--pilot-dir')+1],str(fixture.pilot))
            self.assertEqual(launcher.read(fixture.pilot/'gpu-adviser-config.json'),
                             dict(version=1,expectedUid=fixture.config['expectedUid'],**identity))
            launcher.save(output/'ready.json', dict(ready=True,modelLoaded=True,model=model,**identity))
            launcher.save(fixture.pilot/'controller-status.json',dict(gpuAdviserFrameStream=native_ready,
                          heartbeatAt=int(launcher.time.time()*1000),**identity))
            return process
        def stop(*,timeout):
            self.assertTrue((output/'STOP').exists())
            launcher.save(output/'terminal.json',dict(status='stopped',modelLoaded=True,validNativeFrameSeen=accepted>0,
                          counts=dict(accepted=accepted),**identity))
            return 0
        process.wait.side_effect = stop
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(launcher,'REPO',repo))
            stack.enter_context(mock.patch.object(launcher,'__file__',str(script.with_name('run-rdp-route.py'))))
            stack.enter_context(mock.patch.dict('sys.modules',child_runner=SimpleNamespace(CommandJob=lambda:job)))
            stack.enter_context(mock.patch.object(launcher.subprocess,'CREATE_NO_WINDOW',0x08000000,create=True))
            spawned = stack.enter_context(mock.patch.object(launcher.subprocess,'Popen',side_effect=spawn))
            yield spawned,process,job

    def test_opt_in_reuses_one_adviser_across_legs_and_retires_it(self):
        f = Fixture(self.root,2)
        group = f.app/'User/ScriptGroup/ActOneRun.json'
        group.parent.mkdir(parents=True)
        group.write_text(json.dumps(launcher.group_template('already-existing')))
        original = group.read_bytes()
        with self.gpu_fixture(f) as (spawn,process,job):
            result = f.worker()
        self.assertEqual(result['status'],'arrived',result)
        self.assertEqual(result['gpuAdviser']['status'],'verified')
        self.assertEqual(result['gpuAdviser']['terminal']['counts']['accepted'],3)
        spawn.assert_called_once();job.assign_and_resume.assert_called_once_with(process);job.close.assert_called_once()
        self.assertEqual(len(f.calls),2)
        self.assertEqual(group.read_bytes(),original)
        self.assertFalse((f.pilot/'gpu-adviser-config.json').exists())
        self.assertTrue(result['leaseRemoved'])

    def test_live_worker_and_chain_publish_nonterminal_status_through_gpu_start_legs_and_retirement(self):
        f = Fixture(self.root,2)
        seen = []
        def inspect(phase,expected_leg_count):
            worker = launcher.read(f.output/'worker-result.json')
            chain = launcher.read(f.config['progress'])
            self.assertEqual(chain.pop('kind'),'rdp-route-chain-v1')
            self.assertEqual(worker,chain)
            self.assertEqual(worker['status'],phase)
            self.assertNotIn('exitCode',worker)
            self.assertEqual(len(worker['legs']),expected_leg_count)
            seen.append(phase)
            return worker
        exchange=f.exchange
        def during_native_command(request,*args):
            if isinstance(request,dict) and request['command']=='startPilot':
                inspect('starting',0)
            if isinstance(request,dict) and request['command']=='stopPilot':
                self.assertTrue(all(leg['status']=='arrived' for leg in inspect('retiring',2)['legs']))
            return exchange(request,*args)
        f.exchange=during_native_command
        def during_leg():
            self.assertEqual(inspect('running',len(f.calls))['gpuAdviser']['status'],'running')
        f.on_route=during_leg
        class WatchingAdviser(launcher.GpuRouteAdviser):
            def ready(adviser):
                inspect('starting',0)
                return super().ready()
        with self.gpu_fixture(f):
            result=f.worker(adviser_factory=WatchingAdviser)
        self.assertEqual(seen,['starting','starting','running','running','retiring'])
        self.assertEqual((result['status'],result['exitCode'],result['pilotRetired']),('arrived',0,True))
        self.assertEqual(launcher.read(f.output/'worker-result.json'),result)
        self.assertEqual(launcher.read(f.config['progress'])['exitCode'],0)

    def test_preflight_and_retirement_errors_publish_a_terminal_failed_status(self):
        for fail_at in ('preflight','retirement'):
            f=Fixture(self.root/fail_at,2)
            original=f.exchange
            observed=[]
            def fail_at_boundary(request,*args):
                preflight=fail_at=='preflight' and request=='status'
                retirement=fail_at=='retirement' and isinstance(request,dict) and request['command']=='stopPilot'
                if preflight or retirement:
                    snapshot=launcher.read(f.output/'worker-result.json')
                    observed.append(snapshot['status'])
                    self.assertNotIn('exitCode',snapshot)
                    raise RuntimeError('simulated '+fail_at+' failure')
                return original(request,*args)
            f.exchange=fail_at_boundary
            result=f.worker()
            self.assertEqual(observed,['starting' if fail_at=='preflight' else 'retiring'])
            self.assertEqual(len(f.calls),0 if fail_at=='preflight' else 2)
            for saved in (result,launcher.read(f.output/'worker-result.json'),launcher.read(f.config['progress'])):
                self.assertEqual((saved['status'],saved['exitCode']),('failed',2))
            if fail_at=='retirement':
                self.assertTrue(result['cleanupErrors'])
                self.assertEqual([leg['status'] for leg in result['legs']],['arrived','arrived'])

    def test_arrival_without_real_native_gpu_frames_remains_unverified(self):
        f = Fixture(self.root)
        with self.gpu_fixture(f,accepted=0):
            result = f.worker()
        self.assertEqual(result['status'],'gpu_unverified',result)
        self.assertEqual(result['canonicalStatus'],'arrived')
        self.assertEqual(launcher.read(f.config['progress'])['status'],'arrived')
        self.assertTrue(result['pilotRetired'])
        self.assertEqual(result['exitCode'],2)

    def test_opt_out_has_no_adviser_side_effects(self):
        f = Fixture(self.root)
        marker = f.pilot/'gpu-adviser-config.json'
        marker.write_bytes(b'older-session')
        adviser = mock.Mock(side_effect=AssertionError('disabled adviser opened'))
        self.assertEqual(f.worker(adviser_factory=adviser)['status'],'arrived')
        adviser.assert_not_called()
        self.assertEqual(marker.read_bytes(),b'older-session')
        self.assertFalse((f.output/'gpu-adviser').exists())

    def test_continuous_chain_keeps_only_ordinary_adjacent_legs_in_the_world(self):
        f=Fixture(self.root,4)
        f.config['continuous']=True
        for i,item in enumerate(f.config['routes']):
            path=Path(item['path']);route=launcher.read(path)
            route['objective']='Explore for Adventure Rank'
            if i==2:route['teleportTo']='mondstadt-city'
            if i==3:route['talkTo']='Cyrus'
            path.write_text(json.dumps(route));item['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        result=f.worker()
        self.assertEqual(result['status'],'arrived',result)
        modes=[argv[argv.index('--continuous-ground')+1] if '--continuous-ground' in argv else None for argv in f.calls]
        self.assertEqual(modes,['world','park','park',None])
        self.assertEqual(f.commands,['startPilot','stopPilot'])

    def test_forced_adviser_retirement_closes_its_job_and_cannot_certify_arrival(self):
        f = Fixture(self.root)
        with self.gpu_fixture(f) as (_,process,job):
            process.wait.side_effect = [launcher.subprocess.TimeoutExpired('adviser',12),0]
            result = f.worker()
        self.assertTrue(result['gpuAdviser']['forcedRetirement'])
        self.assertEqual(result['status'],'gpu_unverified')
        self.assertTrue((f.output/'gpu-adviser/STOP').is_file())
        self.assertEqual(process.wait.call_count,2)
        job.close.assert_called_once()
        self.assertTrue(result['pilotRetired'])

    def test_unready_gpu_never_submits_gameplay_and_retires_owned_work(self):
        f = Fixture(self.root)
        with self.gpu_fixture(f,model='wrong model'):
            result = f.worker()
        self.assertEqual(result['status'],'failed')
        self.assertEqual(f.calls,[])
        self.assertEqual(f.commands,['startPilot','stopPilot'])
        self.assertFalse((f.pilot/'gpu-adviser-config.json').exists())

    def test_adviser_exit_during_first_leg_keeps_its_receipt_and_prevents_the_next(self):
        f = Fixture(self.root,2)
        with self.gpu_fixture(f) as (_,process,_):
            f.on_route = lambda: setattr(process.poll,'return_value',3)
            result = f.worker()
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['gpuAdviser']['earlyExit'],3)
        self.assertEqual(result['legs'][0]['status'],'arrived')
        self.assertEqual(len(f.calls),1)
        self.assertTrue(result['pilotRetired'])

    def test_explicit_gpu_setup_never_overwrites_existing_config(self):
        f = Fixture(self.root)
        config = f.pilot/'gpu-adviser-config.json'
        config.write_bytes(b'existing')
        with self.gpu_fixture(f) as (spawn,_,_):
            result = f.worker()
        self.assertEqual(result['status'],'failed')
        self.assertEqual(f.calls,[])
        spawn.assert_not_called()
        self.assertEqual(config.read_bytes(),b'existing')

    def test_stop_while_waiting_for_native_readiness_retires_adviser_before_any_route(self):
        f = Fixture(self.root)
        original_sleep = f.sleep
        stop = self.root/'STOP'
        f.config['stopFiles'].append(str(stop))
        def stop_while_warming(seconds):
            stop.touch()
            original_sleep(seconds)
        f.sleep = stop_while_warming
        with self.gpu_fixture(f,native_ready=False) as (_,_,job):
            result = f.worker()
        self.assertEqual(f.calls,[])
        self.assertIn('STOP',result['error'])
        self.assertTrue(result['pilotRetired'])
        job.close.assert_called_once()

    def test_progress_writers_retry_same_bytes_while_reader_holds_destination(self):
        """A transient Windows reader must not abort a completed gameplay action."""
        route = load(Path(__file__).with_name('act-one-route.py'), '_test_route_files')
        real_replace = os.replace
        for writer in (route.atomic, launcher.save):
            with self.subTest(writer=writer):
                path = self.root / 'progress.json'
                path.write_text('{"status":"old"}', encoding='utf-8')
                attempts = []

                def busy_once(source, target):
                    attempts.append((source, target, source.read_bytes()))
                    if len(attempts) == 1:
                        self.assertEqual(launcher.read(target)['status'], 'old')
                        error = PermissionError('destination temporarily in use')
                        error.winerror = 5
                        raise error
                    return real_replace(source, target)

                with mock.patch.object(os, 'replace', side_effect=busy_once):
                    writer(path, {'status': 'arrived'})
                self.assertEqual(len(attempts), 2)
                self.assertEqual(attempts[0], attempts[1])
                self.assertEqual(launcher.read(path), {'status': 'arrived'})

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

    def test_city_to_cyrus_source_and_all_seventeen_points_run_in_order_on_one_pilot(self):
        fixture = Fixture(self.root)
        specimen = Path(launcher.__file__).with_name('routes') / 'mondstadt-city-to-cyrus.json'
        original = specimen.read_bytes()
        plan = json.loads(original)
        def broker(root, argv, work_dir, python_exe, timeout, job_dir, output_limit):
            fixture.config = launcher.read(argv[-2])
            retained = fixture.config['splitRoutes']
            self.assertEqual(len(retained), 1)
            self.assertEqual(Path(retained[0]['path']).read_bytes(), original)
            self.assertEqual(retained[0]['sha256'], hashlib.sha256(original).hexdigest())
            legs = [launcher.read(r['path']) for r in fixture.config['routes']]
            self.assertEqual([len(r['waypoints']) for r in legs], [4, 4, 4, 4, 1])
            self.assertEqual([point for r in legs for point in r['waypoints']], plan['waypoints'])
            self.assertEqual([r['teleportTo'] for r in legs if 'teleportTo' in r], ['mondstadt-city'])
            self.assertEqual([r for r in legs if 'startNear' in r], [legs[0]])
            self.assertEqual(legs[-1]['talkTo'], 'Cyrus')
            self.assertTrue(all('talkTo' not in r for r in legs[:-1]))
            result = fixture.worker()
            return dict(returnCode=result['exitCode'], timedOut=False)
        args, dependencies = self.console(fixture, broker)
        args.route = [specimen]
        result = launcher.run(args, expected_owner=fixture.owner, dependencies=dependencies)
        self.assertEqual(result['status'], 'arrived', result)
        self.assertEqual(fixture.commands, ['startPilot', 'stopPilot'])
        self.assertEqual(len(fixture.calls), 5)
        self.assertEqual({r[r.index('--session') + 1] for r in fixture.calls}, {'new-owned'})

    def test_mixed_sources_keep_short_bytes_and_verify_each_reference_to_a_long_source(self):
        fixture = Fixture(self.root)
        short = Path(fixture.config['routes'][0]['path'])
        short_bytes = short.read_bytes()
        long = self.root / 'large.json'
        value = launcher.read(short)
        value.update(waypoints=[dict(map='Teyvat', x=n, y=n+1) for n in range(9)],
                     teleportTo='mondstadt-city', talkTo='Cyrus')
        # Preserve the user's literal BOM, indentation, and CRLF in the long source snapshot.
        raw = b'\xef\xbb\xbf' + json.dumps(value, indent=3).replace('\n', '\r\n').encode()
        long.write_bytes(raw)
        output = self.root / 'mixed'
        routes, sources = launcher.snapshot_routes([short, long, short], output, self.canonical())
        self.assertEqual((sources[0]['firstLeg'], sources[0]['legCount']), (1,3))
        self.assertEqual(Path(sources[0]['path']).read_bytes(), raw)
        self.assertEqual([Path(routes[i]['path']).read_bytes() for i in (0,4)], [short_bytes,short_bytes])
        config = dict(routes=routes, splitRoutes=sources)
        launcher.verify_split_routes(config)
        legs = routes[1:4]
        self.assertEqual([r['firstWaypoint'] for r in legs], [0,4,8])
        # A self-consistent rewritten intermediate leg still disagrees with its pinned source.
        changed = launcher.read(legs[1]['path'])
        changed['waypoints'].reverse()
        payload = launcher.leg_bytes(changed)
        Path(legs[1]['path']).write_bytes(payload)
        legs[1]['sha256'] = hashlib.sha256(payload).hexdigest()
        with self.assertRaisesRegex(RuntimeError, 'archived waypoint sequence'):
            launcher.verify_split_routes(config)
        Path(sources[0]['path']).write_bytes(b'{}')
        with self.assertRaisesRegex(RuntimeError, 'Original exploration snapshot'):
            launcher.verify_split_routes(config)
        fixture.config.update(config)
        result = fixture.worker()
        self.assertIn('Original exploration snapshot', result['error'])
        self.assertEqual(fixture.commands, [])

    def test_non_exploration_route_retains_its_existing_waypoint_limit_and_original_bytes(self):
        fixture = Fixture(self.root)
        source = Path(fixture.config['routes'][0]['path'])
        route = launcher.read(source)
        route.update(objective='Talk to Kaeya', waypoints=[dict(map='Teyvat',x=n,y=2) for n in range(6)])
        data = json.dumps(route, indent=4).encode()
        source.write_bytes(data)
        routes, originals = launcher.snapshot_routes([source], self.root / 'quest', self.canonical())
        self.assertEqual((len(routes), originals), (1, []))
        self.assertEqual(Path(routes[0]['path']).read_bytes(), data)

    def test_review_all_legs_before_starting_and_keep_twenty_expanded_legs_as_the_limit(self):
        fixture = Fixture(self.root)
        source = Path(fixture.config['routes'][0]['path'])
        value = launcher.read(source)
        point = value['waypoints'][0]
        output = self.root / 'expanded'
        def plan(points):
            source.write_text(json.dumps(dict(value, waypoints=points)), encoding='utf-8')
        plan([point] * 41)
        with self.assertRaisesRegex(RuntimeError, 'twenty canonical route legs'):
            launcher.snapshot_routes([source,source], output, self.canonical())
        self.assertFalse(output.exists())
        plan([point] * 8 + [dict(point,x='bad')])
        with self.assertRaisesRegex(RuntimeError, 'numeric x/y'):
            launcher.snapshot_routes([source], output, self.canonical())
        self.assertFalse(output.exists())
        plan([point] * 80)
        routes, originals = launcher.snapshot_routes([source], output, self.canonical())
        self.assertEqual(len(routes),20)
        launcher.verify_split_routes(dict(routes=routes, splitRoutes=originals))

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

    def test_longer_leg_reaches_real_worker_with_bounded_broker_and_cleanup_windows(self):
        f = Fixture(self.root)
        original_execute = f.execute
        argv_and_timeout = []
        def capture(argv, output, timeout):
            argv_and_timeout.append((argv, timeout))
            return original_execute(argv, output, timeout)
        f.execute = capture
        def broker(root, argv, work_dir, python_exe, timeout, job_dir, output_limit):
            self.assertEqual(timeout, 251)  # Integral seconds rounded up, plus the existing 20+80.
            f.config = launcher.read(argv[-2])
            worker = f.worker()
            return dict(returnCode=worker['exitCode'], timedOut=False)
        args, deps = self.console(f, broker)
        self.assertEqual(args.deadline_ms, 90000)
        args.deadline_ms = 150001
        self.assertEqual(launcher.run(args, expected_owner=f.owner, dependencies=deps)['status'], 'arrived')
        argv, timeout = argv_and_timeout[0]
        self.assertEqual(argv[argv.index('--deadline-ms')+1], '150001')
        self.assertAlmostEqual(timeout, 170.001)

    def test_long_plan_exceeding_the_one_hour_broker_limit_creates_no_snapshot(self):
        f = Fixture(self.root)
        broker = mock.Mock()
        args, deps = self.console(f, broker)
        args.deadline_ms = 300000
        args.route = args.route * 12
        with self.assertRaisesRegex(RuntimeError, 'one-hour'):
            launcher.run(args, expected_owner=f.owner, dependencies=deps)
        self.assertFalse((args.progress.parent / (args.progress.stem + '.rdp')).exists())
        broker.assert_not_called()

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
