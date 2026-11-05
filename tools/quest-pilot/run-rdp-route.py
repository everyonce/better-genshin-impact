"""Run canonical route controllers once in an existing, minimized BetterGI RDP child."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
IDENTITY = ('processId', 'windowsSessionId', 'instanceNonce')


def require(value, message):
    """Fail explicitly; no failed or uncertain launch is retried."""
    if not value:
        raise RuntimeError(message)


def load(name, path):
    """Import an existing local helper without invoking its command entrypoint."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FILE_PROTOCOL = load('_rdp_route_files', Path(__file__).with_name('act-one-command.py'))


def helpers():
    """Reuse the established authenticated transport, broker, and route implementation."""
    folder = REPO / 'tools/rdp-automation'
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    return (load('_rdp_route_broker', folder / 'rdp_control.py'),
            load('_rdp_route_control', Path(__file__).with_name('controller-control.py')),
            load('_rdp_route_cli', Path(__file__).with_name('act-one-route.py')))


def read(path):
    """Read one retained JSON document, including existing UTF-8 BOM files."""
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    """Publish launcher evidence atomically in its private output directory."""
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    FILE_PROTOCOL.replace_pending(temporary, path)


def same_owner(actual, expected):
    """A reused PID alone cannot authorize a different process lifetime."""
    return (all(actual.get(key) == expected.get(key) for key in IDENTITY)
            and type(actual.get('processId')) is int and actual['processId'] > 0
            and type(actual.get('windowsSessionId')) is int
            and isinstance(actual.get('instanceNonce'), str) and bool(actual['instanceNonce']))


def select_owner(discovery, process_id=None, expected_owner=None):
    """Select one connected minimized pair; ambiguity never starts another instance."""
    require(not discovery.get('unavailable'), 'Discovery is incomplete; inspect unavailable endpoints first.')
    children = [x for x in discovery['instances'] if x.get('instanceType') == 'ChildSession'
                and x.get('remoteDesktop') is True
                and (process_id is None or x.get('processId') == process_id)]
    require(len(children) == 1, 'Select one existing RDP child with --process-id; never start or replace it here.')
    child = children[0]
    roots = [x for x in discovery['instances'] if x.get('instanceType') == 'Primary'
             and x.get('childSessionId') == child.get('windowsSessionId')
             and x.get('processId') == child.get('rootProcessId')]
    require(len(roots) == 1, 'The child has no unique authenticated current root.')
    owner = dict(root=roots[0], child=child)
    for role in ('root', 'child'):
        require(same_owner(owner[role], owner[role]), 'Native process identity is incomplete.')
        if expected_owner is not None:
            require(role in expected_owner and same_owner(owner[role], expected_owner[role]),
                    'The original root/child lifetime changed before route dispatch.')
    require(roots[0].get('automationEnabled') is True and roots[0].get('childConnectedState') == 1
            and roots[0].get('childWindowMinimized') is True, 'Existing RDP must be connected and minimized.')
    require(child.get('windowsSessionId', 0) > 1 and child.get('runtimeRunning') is True,
            'The existing RDP game runtime is not ready.')
    return owner


def validate_group(group):
    """Match native StartPilot's fixed group and disable autonomous startup or background gameplay."""
    projects = group.get('projects', [])
    require(group.get('name') == 'ActOneRun' and len(projects) == 1, 'ActOneRun must contain one project.')
    project = projects[0]
    require(project.get('folderName') == 'ActOnePilot' and project.get('type') == 'Javascript'
            and project.get('status') == 'Enabled' and project.get('runNum') == 1,
            'ActOneRun is not the single-run native pilot group.')
    require(project.get('jsScriptSettingsObject') == dict(enableInput=True, autoEnterGame=False),
            'Pilot settings must enable explicit missions and disable automatic game entry.')
    config = group.get('config', {})
    require(config.get('allowNonMainUiStart') is True and config.get('enableShellConfig', False) is False,
            'The group must allow its existing inventory entry without shell tasks.')
    pathing = config.get('pathingConfig', {})
    require(all(pathing.get(key) is False for key in
                ('enabled', 'jsScriptUseEnabled', 'autoRunEnabled', 'autoFightEnabled', 'autoEatEnabled')),
            'Unrelated automatic pathing, combat, or food use must be disabled.')


def group_template(token):
    """Use the fixed native name, with an ownership label only on a newly created file."""
    # Native PathingPartyConfig defaults enable several behaviors, so every override is explicit.
    config = dict(allowNonMainUiStart=True, enableShellConfig=False,
                  pathingConfig=dict(enabled=False, jsScriptUseEnabled=False, autoRunEnabled=False,
                                     autoFightEnabled=False, autoEatEnabled=False))
    return dict(name='ActOneRun', index=0, config=config, projects=[
        dict(name='ActOnePilot route ' + token, folderName='ActOnePilot', type='Javascript',
             status='Enabled', schedule='Daily', runNum=1,
             jsScriptSettingsObject=dict(enableInput=True, autoEnterGame=False))])


def route_argv(config, session, route, progress, previous_progress=None):
    """Forward the original route and explicit controller options, without translating gameplay policy."""
    child = config['owner']['child']
    argv = [sys.executable, '-B', str(Path(__file__).with_name('act-one-route.py')), route,
            '--controller', '--session', session, '--app-dir', child['appDirectory'],
            '--process-id', str(child['processId']), '--expected-windows-session-id', str(child['windowsSessionId']),
            '--expected-uid', config['expectedUid'], '--progress', progress,
            '--deadline-ms', str(config['deadlineMs']), '--max-segments', str(config['maxSegments'])]
    for key, option in [('allowFieldCombat', '--allow-field-combat'), ('allowDialogue', '--allow-dialogue')]:
        if config[key]:
            argv.append(option)
    for objective in config['continueObjectives']:
        argv.extend(['--continue-objective', objective])
    for stop in config['stopFiles']:
        argv.extend(['--stop-file', stop])
    if previous_progress is not None:
        # The canonical controller validates this optional shortcut and otherwise bootstraps normally.
        argv.extend(['--continue-from-progress', str(previous_progress)])
    return argv


def execute_route(argv, output, timeout, *, on_progress=None):
    """Retain canonical stdout/stderr and wait for this exact CLI process, without replay."""
    with (output / 'stdout.log').open('xb') as stdout, (output / 'stderr.log').open('xb') as stderr:
        child = subprocess.Popen(argv, cwd=REPO, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            if on_progress is None:
                return child.wait(timeout=timeout)
            deadline = time.monotonic() + timeout
            while True:
                remaining = max(0, deadline - time.monotonic())
                try:
                    return child.wait(timeout=min(remaining, 1))
                except subprocess.TimeoutExpired:
                    if time.monotonic() >= deadline:
                        raise
                    on_progress()
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=5)
            raise RuntimeError('Canonical route CLI exceeded its deadline; its known process was retired, never replayed.')
        except BaseException:
            child.terminate()
            child.wait(timeout=5)
            raise


def foreground_game(app, windows_session_id):
    """Pin the actual RDP foreground game using supported OS identity, not an absent discovery field."""
    import ctypes
    from ctypes import wintypes
    from child_runner import process_identity
    configured = read(app / 'User/config.json').get('genshinStartConfig', {}).get('installPath')
    require(isinstance(configured, str) and bool(configured), 'The installed game executable is not configured.')
    executable = Path(configured).resolve()
    require(executable.name.lower() in ('genshinimpact.exe', 'yuanshen.exe'), 'Configured image is not Genshin.')
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    hwnd, pid = user.GetForegroundWindow(), wintypes.DWORD()
    require(hwnd and user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)), 'RDP has no foreground game window.')
    game = process_identity(pid.value)
    require(game['windowsSessionId'] == windows_session_id and Path(game['executable']).resolve() == executable,
            'RDP foreground process is not the configured game in this session.')
    return dict(game, hwnd=int(hwnd))


def run_worker(config, *, control, rdp, execute=execute_route, game_probe=foreground_game,
               monotonic=time.monotonic, sleep=time.sleep):
    """Own one pilot lifetime and run serial route legs; failures retain their original evidence."""
    output, progress = Path(config['output']), Path(config['progress'])
    expected = config['owner']['child']
    app = Path(expected['appDirectory']).resolve()
    pilot = app / 'User/JsScript/ActOnePilot'
    lease = pilot / '.rdp-route-launcher.lock'
    lease_bytes = json.dumps(dict(launchId=config['launchId'], output=str(output))).encode()
    group_path = app / 'User/ScriptGroup/ActOneRun.json'
    group_owned = False
    lease_owned = False
    archive = None
    start_attempted = False
    chain_owned = False
    session = None
    game = None
    state = dict(status='failed', exitCode=2, progress=str(progress), legs=[], pilotRetired=False,
                 cleanupErrors=[], groupCreated=False, owner=config['owner'])

    def record():
        """Keep a single durable worker result, plus a multi-leg summary when requested."""
        save(output / 'worker-result.json', state)
        if chain_owned:
            save(progress, dict(kind='rdp-route-chain-v1', **state))

    def status():
        """Keep the discovered native lifetime and application unchanged."""
        current = control.run('status', expected['processId'], expected['windowsSessionId'])
        require(same_owner(current, expected)
                and Path(current.get('appDirectory', '')).resolve() == app, 'Child lifetime or application changed.')
        return current

    def check_game():
        """Recheck exact game lifetime and foreground HWND before new gameplay work."""
        current = game_probe(app, expected['windowsSessionId'])
        require(game is not None and all(current.get(key) == game.get(key) for key in
                ('processId', 'windowsSessionId', 'executable', 'startedFileTime', 'hwnd')),
                'Game lifetime or foreground window changed.')

    def not_stopped():
        """Honor caller and native STOP before starting a new leg or native task."""
        require(not any(Path(p).exists() for p in config['stopFiles']), 'STOP prevents route launch.')

    def idle(current):
        """An active or stopping task is never adopted by this launcher."""
        return current.get('serviceOwnsPilot') is False and current.get('taskRunning') is False

    def mutate(command):
        """Use the originally selected nonce, not a newly discovered replacement process."""
        return control.exchange(dict(command=command, targetProcessId=expected['processId'],
            targetWindowsSessionId=expected['windowsSessionId'], targetNonce=expected['instanceNonce']),
            expected['processId'], expected['windowsSessionId'])

    def request_owned(current):
        """Cancel only this launch's recorded requests; never overwrite or delete native protocol files."""
        path = pilot / 'request.json'
        if not path.exists():
            return current.get('activeRequestId') in (None, '')
        request = read(path)
        if request.get('session') != session:
            return current.get('activeRequestId') in (None, '')
        known = []
        for leg in state['legs']:
            if Path(leg['progress']).exists():
                value = read(leg['progress'])
                known += [row['request'] for row in value.get('records', [])]
                if value.get('pending'):
                    known.append(value['pending'])
        return request in known and current.get('activeRequestId') in (None, '', request['id'])

    try:
        require(not progress.exists(), 'Existing progress is never resumed or replayed.')
        verify_split_routes(config)
        if len(config['routes']) > 1:
            with progress.open('x', encoding='utf-8') as stream:
                json.dump(dict(kind='rdp-route-chain-v1', **state), stream)
            chain_owned = True
        require(not (pilot / '.route-controller.lock').exists(), 'An unresolved canonical route lease already exists.')
        root_expected = config['owner']['root']
        root = rdp.exchange('status', root_expected['processId'], root_expected['windowsSessionId'])
        select_owner(dict(instances=[root, status()], unavailable=[]), expected_owner=config['owner'])
        game = state['game'] = game_probe(app, expected['windowsSessionId'])
        not_stopped()
        with lease.open('xb') as stream:
            stream.write(lease_bytes)
        lease_owned = True
        # A fresh retired heartbeat can outlive its task; only read status while its native five-second fence clears.
        deadline = monotonic() + 10
        while True:
            current = status()
            require(idle(current), 'Existing work is active or stopping; no pilot was started.')
            stamp = current.get('heartbeatAtUnixMs')
            recent = (current.get('scriptState') in ('starting', 'running', 'idle')
                      and type(stamp) is int and int(time.time() * 1000) - stamp <= 5000)
            if not recent:
                break
            require(monotonic() < deadline, 'Existing heartbeat stayed active; no start was attempted.')
            not_stopped()
            sleep(.2)
        prior_session = current.get('scriptSession')
        if group_path.exists():
            validate_group(read(group_path))
            state['groupReused'] = True
        else:
            group_path.parent.mkdir(parents=True, exist_ok=True)
            with group_path.open('x', encoding='utf-8') as stream:
                json.dump(group_template(config['launchId']), stream)
            group_owned = state['groupCreated'] = True
        save(output / 'group-before.json', read(group_path))
        not_stopped()
        require(idle(status()), 'Another task appeared before startPilot.')
        check_game()
        start_attempted = True
        record()
        state['startAcknowledgement'] = mutate('startPilot')
        deadline = monotonic() + 30
        while monotonic() < deadline:
            current = status()
            if (current.get('serviceOwnsPilot') is True and current.get('heartbeatFresh') is True
                    and current.get('scriptSession') not in (None, '', prior_session)
                    and current.get('scriptState') == current.get('pilotState') == 'idle'
                    and current.get('activeRequestId') in (None, '')):
                session = state['session'] = current['scriptSession']
                break
            sleep(.2)
        require(session is not None, 'Pilot start did not establish a new owned idle session; do not retry.')
        if config.get('saveEncounterFrames'):
            try:
                evidence = load('_rdp_encounter_evidence', Path(__file__).with_name('encounter_evidence.py'))
                archive = evidence.EncounterArchive(pilot, output, FILE_PROTOCOL, save)
                state['encounterEvidence'] = archive.summary
            except Exception as exc:
                state['encounterEvidence'] = dict(error=str(exc))
        previous_progress = None
        for index, route in enumerate(config['routes']):
            not_stopped()
            current = status()
            root = rdp.exchange('status', root_expected['processId'], root_expected['windowsSessionId'])
            select_owner(dict(instances=[root, current], unavailable=[]), expected_owner=config['owner'])
            check_game()
            require(current.get('serviceOwnsPilot') is True and current.get('scriptSession') == session,
                    'Owned pilot session changed before the next route.')
            route_path = Path(route['path'])
            require(hashlib.sha256(route_path.read_bytes()).hexdigest() == route['sha256'], 'Route snapshot changed.')
            leg_dir = output / ('leg-%03d' % (index + 1))
            leg_dir.mkdir()
            leg_progress = progress if len(config['routes']) == 1 else leg_dir / 'progress.json'
            leg = dict(route=route, progress=str(leg_progress), status='running')
            state['legs'].append(leg)
            record()
            argv = route_argv(config, session, str(route_path), str(leg_progress), previous_progress)
            leg['command'] = argv
            # Read only this leg's published progress and receipt-selected captures during the wait.
            poll = (lambda: archive.poll(leg_progress, session, index + 1)) if archive else None
            try:
                options = {'on_progress': poll} if poll else {}
                leg['exitCode'] = execute(argv, leg_dir, config['deadlineMs'] / 1000 + 20, **options)
            finally:
                if poll:
                    poll()
            result = read(leg_progress)
            leg['status'] = result.get('status')
            require(leg['exitCode'] == 0 and result.get('status') == 'arrived'
                    and result.get('session') == session and result.get('pending') is None
                    and result.get('nextWaypointIndex') == len(read(route_path)['waypoints']),
                    'Canonical route did not verify arrival; no following leg was started.')
            previous_progress = leg_progress
        state.update(status='arrived', exitCode=0)
    except Exception as error:
        state['error'] = str(error)
    finally:
        # Never stop a task on the strength of PID alone or an uncertain start acknowledgement.
        try:
            current = status()
            if session is not None:
                require(current.get('scriptSession') == session, 'Cleanup found another script session.')
                require(request_owned(current), 'Cleanup found an unrecorded request; unrelated work was left untouched.')
                if current.get('serviceOwnsPilot') is True:
                    try:
                        state['stopAcknowledgement'] = mutate('stopPilot')
                    except Exception as stop_error:
                        # The task may already have retired, or only its ACK was lost.
                        # Preserve this diagnostic and read back the exact session; never resend STOP.
                        state['stopError'] = str(stop_error)
                deadline = monotonic() + 20
                while not idle(current) and monotonic() < deadline:
                    sleep(.2)
                    current = status()
                    require(current.get('scriptSession') == session, 'Script session changed during retirement.')
                require(idle(current), 'Owned pilot retirement is unresolved.')
                state['pilotRetired'] = True
            elif not start_attempted:
                require(idle(current), 'Another task appeared during pre-start cleanup.')
            else:
                raise RuntimeError('Start outcome remains unresolved; lease and group were retained.')
            state['ownerAfter'] = current
            if group_owned:
                group = read(group_path)
                save(output / 'group-after.json', group)
                validate_group(group)
                require(group['projects'][0].get('name') == 'ActOnePilot route ' + config['launchId'],
                        'Created group ownership label changed; file was retained.')
                group_path.unlink()
                state['groupRemoved'] = True
            if lease_owned and not (pilot / '.route-controller.lock').exists():
                require(lease.read_bytes() == lease_bytes, 'Launcher lease changed; it was retained.')
                lease.unlink()
                state['leaseRemoved'] = True
        except Exception as cleanup_error:
            state['cleanupErrors'].append(str(cleanup_error))
        if state['cleanupErrors'] or not state['pilotRetired']:
            state.update(status='failed', exitCode=2)
        record()
    return state


def parse_args(argv=None):
    """One public command; repeated routes remain separate canonical controller legs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', action='append', type=Path, required=True)
    parser.add_argument('--progress', type=Path, required=True)
    parser.add_argument('--expected-uid', required=True)
    parser.add_argument('--allow-field-combat', action='store_true')
    parser.add_argument('--save-encounter-frames', action='store_true',
                        help='Retain a bounded set of native combat and named NPC capture pairs for replay.')
    parser.add_argument('--allow-dialogue', action='store_true')
    parser.add_argument('--continue-objective', action='append', default=[])
    parser.add_argument('--stop-file', action='append', type=Path, default=[])
    parser.add_argument('--deadline-ms', type=int, default=90000,
                        help='Per controller leg in milliseconds (1000–300000, default 90000).')
    parser.add_argument('--max-segments', type=int, default=3)
    parser.add_argument('--process-id', type=int, help='Disambiguate an already running child; never starts an application')
    parser.add_argument('--node', type=Path, help='Existing Node executable; defaults to Node on the console PATH')
    return parser.parse_args(argv)


def exploration_legs(route):
    """Cut only free exploration at its four-waypoint native limit, retaining the source order."""
    points = route.get('waypoints') if isinstance(route, dict) else None
    if (not isinstance(points, list) or len(points) <= 4
            or route.get('objective') != 'Explore for Adventure Rank'):
        return [route]
    require(len(points) <= 80, 'The expanded plan exceeds twenty canonical route legs.')
    legs = []
    for start in range(0, len(points), 4):
        leg = dict(route, waypoints=points[start:start + 4])
        if start:
            leg.pop('teleportTo', None)
            leg.pop('startNear', None)
        if start + 4 < len(points):
            leg.pop('talkTo', None)
        legs.append(leg)
    return legs


def leg_bytes(leg):
    """Give a derived leg a stable UTF-8 representation that the worker can verify independently."""
    return json.dumps(leg, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def snapshot_routes(sources, output, route_cli, *, broker_leg_limit=20):
    """Validate every input and the total leg count before creating evidence or starting the broker."""
    routes, originals, files = [], [], []
    for source_number, source in enumerate(sources, 1):
        data = source.read_bytes()
        require(len(data) <= 65536, 'Route JSON exceeds 64 KiB.')
        legs = exploration_legs(json.loads(data.decode('utf-8-sig')))
        require(len(routes) + len(legs) <= 20, 'The expanded plan exceeds twenty canonical route legs.')
        original = str(source.resolve())
        split = len(legs) > 1
        if split:
            saved = output / ('source-%03d.json' % source_number)
            originals.append(dict(path=str(saved), original=original, sha256=hashlib.sha256(data).hexdigest(),
                                  firstLeg=len(routes), legCount=len(legs)))
            files.append((saved, data))
        for index, leg in enumerate(legs):
            route_cli.validate_route(leg)
            path = output / ('route-%03d.json' % (len(routes) + 1))
            payload = leg_bytes(leg) if split else data
            record = dict(path=str(path), sha256=hashlib.sha256(payload).hexdigest(), original=original)
            if split:
                record.update(sourceSnapshot=str(saved), firstWaypoint=index * 4)
            files.append((path, payload))
            routes.append(record)
    require(len(routes) <= broker_leg_limit, 'Combined route deadlines exceed the one-hour RDP command limit.')
    output.mkdir(parents=True)
    for path, data in files:
        path.write_bytes(data)
    return routes, originals


def verify_split_routes(config):
    """Reconstruct every derived leg from the archived original before the worker takes ownership."""
    routes = config['routes']
    require(1 <= len(routes) <= 20, 'The expanded plan must have one to twenty canonical route legs.')
    verified = set()
    for original in config.get('splitRoutes', []):
        data = Path(original['path']).read_bytes()
        require(hashlib.sha256(data).hexdigest() == original['sha256'], 'Original exploration snapshot changed.')
        expected = exploration_legs(json.loads(data.decode('utf-8-sig')))
        first, count = original['firstLeg'], original['legCount']
        require(type(first) is int and type(count) is int and count == len(expected) > 1
                and 0 <= first <= len(routes) - count, 'Invalid exploration leg range.')
        for index, expected_leg in enumerate(expected):
            ordinal = first + index
            record = routes[ordinal]
            payload = leg_bytes(expected_leg)
            require(ordinal not in verified and record.get('original') == original['original']
                    and record.get('sourceSnapshot') == original['path'] and record.get('firstWaypoint') == index * 4
                    and hashlib.sha256(payload).hexdigest() == record['sha256']
                    and Path(record['path']).read_bytes() == payload,
                    'Exploration leg differs from the archived waypoint sequence.')
            verified.add(ordinal)
    require(verified == {i for i, r in enumerate(routes) if 'sourceSnapshot' in r},
            'A derived exploration leg has no corresponding original.')


def run(args, *, expected_owner=None, dependencies=None):
    """Console API also used by an opt-in caller retaining its original authenticated owner pair."""
    rdp, _, route_cli = helpers() if dependencies is None else dependencies
    require(1 <= len(args.route) <= 20 and 1000 <= args.deadline_ms <= route_cli.MAX_CONTROLLER_DEADLINE_MS
            and 1 <= args.max_segments <= route_cli.MAX_SEGMENTS and re.fullmatch(r'[0-9]{9,10}', args.expected_uid),
            'Use one to twenty routes, the canonical finite limits, and an explicit numeric account.')
    progress = args.progress.resolve()
    require(not progress.exists(), 'Existing progress is never replayed.')
    owner = select_owner(rdp.discover(), args.process_id, expected_owner)
    app = Path(owner['child']['appDirectory']).resolve()
    require(not progress.is_relative_to(app / 'User/JsScript/ActOnePilot'), 'Progress must be outside native protocol files.')
    node = args.node or shutil.which('node')
    require(node and Path(node).is_file() and Path(node).name.lower() == 'node.exe',
            'Provide an installed node.exe with --node.')
    output = progress.parent / (progress.stem + '.rdp')
    # Round up for the broker's integral timeout and retain the worker's existing cleanup allowances.
    leg_seconds = (args.deadline_ms + 999) // 1000 + 20
    setup_and_cleanup_seconds = 80
    broker_leg_limit = (3600 - setup_and_cleanup_seconds) // leg_seconds
    routes, originals = snapshot_routes(args.route, output, route_cli, broker_leg_limit=broker_leg_limit)
    config = dict(version=1, launchId=uuid.uuid4().hex, owner=owner, output=str(output), progress=str(progress),
                  routes=routes, splitRoutes=originals, expectedUid=args.expected_uid, node=str(Path(node).resolve()),
                  allowFieldCombat=args.allow_field_combat, allowDialogue=args.allow_dialogue,
                  saveEncounterFrames=args.save_encounter_frames,
                  deadlineMs=args.deadline_ms, maxSegments=args.max_segments, continueObjectives=args.continue_objective,
                  stopFiles=[str(p.resolve()) for p in [progress.parent / 'STOP', progress.with_suffix('.STOP'),
                             output / 'STOP', app / 'User/JsScript/ActOnePilot/STOP', *args.stop_file]])
    config_path = output / 'launch.json'
    save(config_path, config)
    digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
    argv = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker', str(config_path), digest]
    report = dict(status='failed', exitCode=2, progress=str(progress), workerResult=str(output / 'worker-result.json'),
                  launcherResult=str(output / 'launcher-result.json'), pilotRetired=False, owner=owner)
    try:
        budget = setup_and_cleanup_seconds + len(routes) * leg_seconds
        broker = rdp.run_command(owner['root'], argv, str(REPO), sys.executable, budget, str(output / 'jobs'), 1024 * 1024)
        save(output / 'broker-result.json', broker)
        worker = read(output / 'worker-result.json')
        report['pilotRetired'] = worker.get('pilotRetired') is True
        require(broker.get('returnCode') == 0 and broker.get('timedOut') is False
                and worker.get('exitCode') == 0 and worker.get('status') == 'arrived' and report['pilotRetired'],
                'Route or retirement failed; inspect the unchanged canonical progress and worker result.')
        report.update(status='arrived', exitCode=0)
    except Exception as error:
        report['error'] = str(error)
    save(output / 'launcher-result.json', report)
    return report


def main():
    """Only the existing ordinary RDP broker may invoke the private worker mode."""
    if len(sys.argv) == 4 and sys.argv[1] == '--worker':
        path = Path(sys.argv[2])
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == sys.argv[3], 'Launch document changed before worker admission.')
        config = json.loads(data)
        rdp, control, _ = helpers()
        from child_runner import windows_identity, require_ordinary_rdp
        identity = windows_identity()
        require_ordinary_rdp(identity, config['owner']['child']['windowsSessionId'])
        os.environ['PATH'] = str(Path(config['node']).parent) + os.pathsep + os.environ.get('PATH', '')
        result = run_worker(config, control=control, rdp=rdp)
    else:
        result = run(parse_args())
    print(json.dumps({key: value for key, value in result.items() if key != 'owner'}))
    return result['exitCode']


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
