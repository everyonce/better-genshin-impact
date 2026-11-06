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
GPU_SETUP_SECONDS = 120


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


def route_argv(config, session, route, progress, previous_progress=None, *, continuous_ground=None):
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
    if continuous_ground:
        argv.extend(['--continuous-ground',continuous_ground])
    return argv


def continuous_mode(config, index, current):
    """Keep the world open only across two consecutive ordinary exploration legs of this owned pilot."""
    def ordinary(route):
        return route.get('objective')=='Explore for Adventure Rank' and not route.get('talkTo') and not route.get('resumeNamedDialogue')
    if not config.get('continuous') or not ordinary(current):
        return None
    if index+1<len(config['routes']):
        following=config['routes'][index+1]
        data=Path(following['path']).read_bytes()
        require(hashlib.sha256(data).hexdigest()==following['sha256'],'Successor route snapshot changed before world handoff.')
        next_route=json.loads(data.decode('utf-8-sig'))
        if ordinary(next_route) and not next_route.get('teleportTo'):
            return 'world'
    return 'park'


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


class GpuRouteAdviser:
    """Own one optional image-only adviser and its exact session-scoped native config."""

    def __init__(self, output, pilot, identity, goal_embedding=None):
        self.goal_embedding = goal_embedding
        self.output = output / 'gpu-adviser'
        self.pilot = pilot
        self.identity = identity
        self.config_path = pilot / 'gpu-adviser-config.json'
        self.config_bytes = None
        self.process = None
        self.job = None
        self.created_output = False
        self.summary = dict(status='starting', output=str(self.output))
        if goal_embedding is not None:
            self.summary['goalEmbedding'] = goal_embedding

    def start(self, runtime):
        """Publish a complete config without replacing another launch, then resume this exact process in a job."""
        from child_runner import CommandJob
        python = REPO / 'artifacts/agent/envs/gamescaling/Scripts/python.exe'
        script = Path(__file__).with_name('gpu_adviser.py')
        require(python.is_file() and script.is_file(), 'Installed GPU environment or adviser script is unavailable.')
        self.output.mkdir()
        self.created_output = True
        data = json.dumps(dict(version=1, **self.identity), separators=(',', ':')).encode()
        pending = self.config_path.with_name('gpu-adviser-' + uuid.uuid4().hex + '.tmp')
        with pending.open('xb') as stream:
            stream.write(data)
        try:
            if os.name == 'nt':
                os.rename(pending, self.config_path)  # Windows rename is atomic and refuses an existing destination.
            else:
                os.link(pending, self.config_path)
            self.config_bytes = data
        finally:
            pending.unlink(missing_ok=True)
        ident = self.identity
        argv = [str(python), '-B', str(script), '--pilot-dir', str(self.pilot), '--session', ident['session'],
                '--process-id', str(ident['processId']), '--windows-session-id', str(ident['windowsSessionId']),
                '--game-process-id', str(ident['gameProcessId']), '--output', str(self.output),
                '--launcher-pid', str(os.getpid()), '--max-runtime-seconds', str(runtime)]
        if self.goal_embedding is not None:
            snapshot = self.output.parent / 'gpu-goal-embedding.json'
            with snapshot.open('rb') as stream:
                chosen_bytes = stream.read(131073)
            require(len(chosen_bytes) <= 131072 and hashlib.sha256(chosen_bytes).hexdigest() == self.goal_embedding['sha256'],
                    'GPU goal embedding snapshot changed after launch.')
            argv.extend(['--goal-embedding', str(snapshot)])
        self.job = CommandJob()
        with (self.output / 'stdout.log').open('xb') as stdout, (self.output / 'stderr.log').open('xb') as stderr:
            self.process = subprocess.Popen(argv, cwd=REPO, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                           creationflags=subprocess.CREATE_NO_WINDOW | 0x4)
        try:
            self.job.assign_and_resume(self.process)
        except BaseException:
            self.process.terminate()  # The suspended child has not been allowed to spawn descendants.
            raise
        self.summary['processId'] = self.process.pid

    def matches(self, doc):
        """The supervisor and native pilot have two independent sequences; pin their actual owners."""
        return isinstance(doc, dict) and all(doc.get(k) == self.identity[k]
            for k in ('session', 'processId', 'windowsSessionId', 'gameProcessId'))

    def ready(self):
        """Require GPU weights and the same native pilot's published fresh frame-stream capability."""
        self.check_alive()
        native_path, ready_path = self.pilot / 'controller-status.json', self.output / 'ready.json'
        try:
            native = read(native_path)
        except (ValueError, OSError):
            return False  # Legacy file protocol can be between truncate and write.
        if not isinstance(native, dict) or any(native.get(k) != self.identity[k] for k in ('session', 'processId', 'windowsSessionId')):
            return False
        require(not native.get('gpuAdviserError'), 'Native frame stream failed: ' + str(native.get('gpuAdviserError')))
        stamp = native.get('heartbeatAt')
        if (native.get('gpuAdviserFrameStream') is not True or type(stamp) is not int
                or not 0 <= int(time.time()*1000)-stamp <= 5000 or not ready_path.is_file()):
            return False
        ready = read(ready_path)
        require(self.matches(ready) and ready.get('ready') is True and ready.get('modelLoaded') is True
                and ready.get('model') == 'open-p2p-150M', 'GPU readiness does not match the pinned model and native owner.')
        if self.goal_embedding is not None:
            require(isinstance(ready.get('goalEmbedding'), str) and Path(ready['goalEmbedding']).resolve() ==
                    (self.output.parent/'gpu-goal-embedding.json').resolve(), 'GPU readiness reports another goal embedding.')
        self.summary.update(status='running', ready=ready)
        return True

    def check_alive(self):
        """Poll the original process handle without blocking on inference."""
        code = self.process.poll()
        if code is not None:
            self.summary['earlyExit'] = code
            raise RuntimeError('GPU adviser exited before the route ended (code ' + str(code) + ').')

    def finish(self):
        """Retire this job and report native-validated images independently from route arrival."""
        try:
            if self.created_output:
                try:
                    (self.output / 'STOP').touch(exist_ok=True)
                except OSError as exc:
                    self.summary['stopSignalError'] = str(exc)  # The job still owns all its children.
            if self.process is not None:
                try:
                    self.process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    self.summary['forcedRetirement'] = True
                finally:
                    if self.job is not None:
                        self.job.close()
                        self.job = None
                self.summary['exitCode'] = self.process.wait(timeout=5)
            terminal_path = self.output / 'terminal.json'
            try:
                terminal = read(terminal_path) if self.created_output and terminal_path.is_file() else None
            except (OSError, ValueError) as exc:
                terminal = None
                self.summary['terminalError'] = str(exc)
            self.summary['terminal'] = terminal
            counts = terminal.get('counts') if isinstance(terminal, dict) else None
            accepted = counts.get('accepted') if isinstance(counts, dict) else None
            verified = ('ready' in self.summary and self.matches(terminal) and terminal.get('status') == 'stopped'
                        and terminal.get('modelLoaded') is True and terminal.get('validNativeFrameSeen') is True
                        and type(accepted) is int and accepted > 0
                        and self.summary.get('exitCode') == 0 and 'earlyExit' not in self.summary
                        and not self.summary.get('forcedRetirement') and 'stopSignalError' not in self.summary)
            self.summary['status'] = 'verified' if verified else 'unverified'
            return verified
        finally:
            if self.job is not None:
                self.job.close()
            if self.config_bytes is not None:
                require(self.config_path.read_bytes() == self.config_bytes, 'GPU config changed during cleanup; it was retained.')
                self.config_path.unlink()


def settle_retired_route(pilot, owner, game, current, new_output):
    """Retire the exact prior leases when its child stopped and its outstanding request has a terminal receipt."""
    launcher_lock, route_lock = pilot/'.rdp-route-launcher.lock', pilot/'.route-controller.lock'
    if not launcher_lock.is_file():
        return None
    launcher_bytes = launcher_lock.read_bytes()
    marker = json.loads(launcher_bytes)
    previous = Path(marker['output']).resolve()
    require(previous.suffix == '.rdp' and previous != new_output and not previous.is_relative_to(pilot),
            'Previous launcher lease location is invalid.')
    launch, worker, console = (read(previous/name) for name in ('launch.json','worker-result.json','launcher-result.json'))
    require(launch['launchId'] == marker['launchId'] and Path(launch['output']).resolve() == previous
            and worker.get('pilotRetired') is True and console.get('pilotRetired') is True
            and worker.get('status') == console.get('status') == 'failed' and worker.get('cleanupErrors') == []
            and all(same_owner(launch['owner'][role], owner[role]) for role in ('root','child'))
            and same_owner(worker['ownerAfter'], owner['child']) and same_owner(current, owner['child']),
            'Previous route has no matching retired owner.')
    require(all(game[k] == worker['game'][k] for k in ('processId','windowsSessionId','startedFileTime','executable','hwnd'))
            and current.get('taskRunning') is False and current.get('serviceOwnsPilot') is False
            and current.get('activeRequestId') in (None,'') and current.get('scriptSession') == worker['session'],
            'Previous game or retired native session changed.')
    leg = read(previous/('leg-%03d' % len(worker['legs']))/'progress.json')
    req = leg.get('pending')
    require(isinstance(req,dict) and leg.get('session') == req.get('session') == worker['session'],
            'The retained request has a different session.')
    slot = read(pilot/'request.json')
    pending_receipt = FILE_PROTOCOL.request_receipt_path(pilot,req['session'],req['id'])
    staged = pilot/'request.pending.json'
    archived_staged = previous/'unpublished-request.json'
    unpublished = slot != req
    if unpublished:
        last = leg['records'][-1]
        stage_source = archived_staged if archived_staged.exists() else staged
        require(slot == last['request'] and slot.get('session') == req['session'] and not pending_receipt.exists()
                and stage_source.is_file() and read(stage_source) == req,
                'The current slot and retained staging file do not prove nonpublication.')
        receipt = read(FILE_PROTOCOL.request_receipt_path(pilot,slot['session'],slot['id']))
        require(receipt == last['receipt'] and receipt['frameId'] == req['expectedFrameId'],
                'The settled predecessor frame changed.')
    else:
        receipt = read(pending_receipt)
    observed = read(FILE_PROTOCOL.observation_path(pilot,req['session'],receipt['frameId']))
    frame = FILE_PROTOCOL.validate_terminal_receipt(slot,receipt,observed)
    heartbeat = read(pilot/'controller-status.json')
    require(heartbeat.get('session') == req['session'] and heartbeat.get('activeRequestId') in (None,'')
            and heartbeat.get('frameId',0) >= frame and heartbeat.get('state') in ('faulted','stopped','idle'),
            'The original native request remains active or uncertain.')
    # Preserve both markers beside their original job, under its still-owned launcher lease.
    # If an interruption occurred between renames, verify the already-archived first marker.
    retired_route, retired_launcher = previous/'retired-controller.lease', previous/'retired-launcher.lease'
    lock_source = retired_route if retired_route.exists() else route_lock
    route_bytes = lock_source.read_bytes()
    lock = json.loads(route_bytes)
    require(lock.get('session') == req['session'] and lock.get('processId') == current['processId']
            and lock.get('windowsSessionId') == current['windowsSessionId']
            and re.fullmatch('[0-9a-f]{32}',lock.get('controllerId','')) and not retired_launcher.exists(),
            'Previous canonical lease differs from the retired session.')
    require(launcher_lock.read_bytes() == launcher_bytes, 'The launcher lease changed during reconciliation.')
    if unpublished and stage_source == staged:
        require(read(staged) == req and read(pilot/'request.json') == slot and not pending_receipt.exists(),
                'The staged request changed before archival.')
        staged.rename(archived_staged)
    if lock_source == route_lock:
        require(route_lock.read_bytes() == route_bytes, 'Canonical lease changed during reconciliation.')
        route_lock.rename(retired_route)
    require(not route_lock.exists() and launcher_lock.read_bytes() == launcher_bytes,
            'A new owner appeared during reconciliation.')
    launcher_lock.rename(retired_launcher)
    return dict(sourceRun=str(previous), requestId=req['id'], frameId=frame, terminalStatus='unpublished' if unpublished else receipt['status'])


def run_worker(config, *, control, rdp, execute=execute_route, game_probe=foreground_game,
               monotonic=time.monotonic, sleep=time.sleep, adviser_factory=GpuRouteAdviser):
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
    adviser = None
    start_attempted = False
    chain_owned = False
    session = None
    game = None
    state = dict(status='starting', progress=str(progress), legs=[], pilotRetired=False,
                 cleanupErrors=[], groupCreated=False, owner=config['owner'])
    terminal_status = 'failed'

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
        record()
        verify_split_routes(config)
        if len(config['routes']) > 1:
            with progress.open('x', encoding='utf-8') as stream:
                json.dump(dict(kind='rdp-route-chain-v1', **state), stream)
            chain_owned = True
        if lease.exists():
            retired = settle_retired_route(pilot, config['owner'], game_probe(app, expected['windowsSessionId']), status(), output)
            if retired:
                state['settledPriorRequest'] = retired
                record()
        require(not (pilot / '.route-controller.lock').exists(), 'An unresolved canonical route lease already exists.')
        root_expected = config['owner']['root']
        root = rdp.exchange('status', root_expected['processId'], root_expected['windowsSessionId'])
        select_owner(dict(instances=[root, status()], unavailable=[]), expected_owner=config['owner'])
        game = state['game'] = game_probe(app, expected['windowsSessionId'])
        if config.get('resumedDefeat'):
            prior_game = config['resumedDefeat']['game']
            require(all(game.get(k) == prior_game[k] for k in ('processId','windowsSessionId','startedFileTime','executable','hwnd')),
                    'The game lifetime changed since the confirmed defeat.')
            state['resumedDefeat'] = config['resumedDefeat']['evidence']
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
        if config.get('gpuAdviser'):
            check_game()
            not_stopped()
            identity = dict(session=session, processId=expected['processId'], windowsSessionId=expected['windowsSessionId'],
                            gameProcessId=game['processId'], expectedUid=config['expectedUid'])
            goal = config.get('gpuGoalEmbedding')
            adviser = adviser_factory(output, pilot, identity) if goal is None else adviser_factory(output, pilot, identity, goal)
            state['gpuAdviser'] = adviser.summary
            record()
            adviser.start(GPU_SETUP_SECONDS + 20 + len(config['routes']) * ((config['deadlineMs'] + 999)//1000 + 20))
            deadline = monotonic() + GPU_SETUP_SECONDS
            while True:
                not_stopped()
                if adviser.ready():
                    break
                require(monotonic() < deadline, 'GPU model and native frame stream did not both become ready.')
                sleep(.2)
            record()
        if config.get('saveEncounterFrames'):
            try:
                evidence = load('_rdp_encounter_evidence', Path(__file__).with_name('encounter_evidence.py'))
                archive = evidence.EncounterArchive(pilot, output, FILE_PROTOCOL, save)
                state['encounterEvidence'] = archive.summary
            except Exception as exc:
                state['encounterEvidence'] = dict(error=str(exc))
        state['status'] = 'running'
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
            mode = continuous_mode(config,index,read(route_path)) if config.get('continuous') else None
            argv = route_argv(config, session, str(route_path), str(leg_progress), previous_progress, continuous_ground=mode)
            leg['command'] = argv
            if adviser:
                adviser.check_alive()
            # Read only this leg's published progress and receipt-selected captures during the wait.
            def poll_progress():
                if archive:
                    archive.poll(leg_progress, session, index + 1)
                # Retain the canonical terminal receipt if the model dies mid-leg. Never start another leg.
                if adviser and 'earlyExit' not in adviser.summary:
                    try:
                        adviser.check_alive()
                    except RuntimeError:
                        pass
            poll = poll_progress if archive or adviser else None
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
            if adviser:
                adviser.check_alive()
        terminal_status = 'arrived'
    except Exception as error:
        state['error'] = str(error)
    finally:
        # Consumers can see the completed legs while native pilot / model retirement is still outstanding.
        state['status'] = 'retiring' if start_attempted else 'finishing'
        try:
            record()
        except Exception as exc:
            state['cleanupErrors'].append('Worker status publication: ' + str(exc))
        if adviser:
            try:
                if not adviser.finish() and terminal_status == 'arrived':
                    terminal_status = 'gpu_unverified'
                    state.update(canonicalStatus='arrived',
                                 error='GPU run has no verified successful adviser terminal; canonical route arrived.')
            except Exception as exc:
                state['cleanupErrors'].append('GPU adviser: ' + str(exc))
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
            terminal_status = 'failed'
        state.update(status=terminal_status, exitCode=0 if terminal_status == 'arrived' else 2)
        record()
    return state


def parse_args(argv=None):
    """One public command; repeated routes remain separate canonical controller legs."""
    parser = argparse.ArgumentParser(description=__doc__)
    plan = parser.add_mutually_exclusive_group(required=True)
    plan.add_argument('--route', action='append', type=Path)
    plan.add_argument('--resume-after-defeat', type=Path, metavar='RUN.rdp',
                      help='Continue remaining waypoints from a retired run with verified combat EXP and clear ground.')
    parser.add_argument('--progress', type=Path, required=True)
    parser.add_argument('--expected-uid', required=True)
    parser.add_argument('--allow-field-combat', action='store_true')
    parser.add_argument('--gpu-adviser', action='store_true', help='Run one local Open P2P GPU adviser during the owned route.')
    parser.add_argument('--gpu-goal-embedding', type=Path, metavar='FILE',
                        help='Use this local precomputed Open P2P goal with --gpu-adviser.')
    parser.add_argument('--continuous', action='store_true', help='Allow verified world handoffs between ordinary ground exploration legs.')
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


def archived_tower_defeat(directory, row, expected_uid, route_cli, receipt_bytes):
    """Recheck the retained native before, XP and clear frames when the live capture ring has expired."""
    req = row['request']
    result = (row['receipt'].get('details') or {}).get('result') or {}
    chunks = result.get('chunks') or []
    if len(chunks) != 1 or (result.get('gateTower') or {}).get('assessment') != 'defeat':
        return None
    if not (directory/'encounter-evidence.json').is_file():
        return None
    manifest = read(directory/'encounter-evidence.json')
    digest = hashlib.sha256(receipt_bytes).hexdigest()
    available = {e['frameId']:e for e in manifest['frames'] if e['session'] == req['session'] and
                 any(u.get('requestId') == req['id'] and u.get('receiptSha256') == digest for u in e['uses'])}
    end = result['pauseProof']['sourceFrameId']
    clear = end if end in available else result['afterFrameId']
    needed = {chunks[0]['beforeFrameId'],chunks[0]['afterFrameId'],clear}
    if not needed.issubset(available):
        return None
    frames = {}
    for number in needed:
        entry = available[number]
        stem = 'frame-%04d' % number
        for ext in ('json','png'):
            path = directory/'encounters'/req['session']/stem/(stem+'.'+ext)
            require(path.resolve() == path and (directory/entry[ext]).resolve() == path, 'Archived fight frame path changed.')
            data = path.read_bytes()
            require(hashlib.sha256(data).hexdigest() == entry[ext+'Sha256'], 'Archived fight capture hash changed.')
            if ext == 'json':
                frames[number] = json.loads(data)
    witness = route_cli.field_combat_feedback(row,expected_uid,frames.__getitem__,retained_clear_frame=clear)
    if witness and witness['measuredClear']:
        return witness,frames[clear]['map']
    return None


def resume_defeated_route(directory, expected_uid, route_cli):
    """Recover only pending waypoints after an independently witnessed defeat in the same game."""
    directory = Path(directory).resolve()
    pin = load('_retired_route_owner', Path(__file__).with_name('update-idle-pilot.py')).terminal_run(directory)
    launch, worker = read(directory / 'launch.json'), read(directory / 'worker-result.json')
    require(launch['expectedUid'] == expected_uid and worker['status'] == 'failed' and worker['legs'],
            'Continuation requires the retired incomplete route for this account.')
    index = len(worker['legs']) - 1
    require(0 <= index < len(launch['routes']) <= 20, 'Invalid interrupted route ordinal.')
    leg = read(directory / ('leg-%03d' % (index + 1)) / 'progress.json')
    require(leg.get('pending') is None and leg['records'] and leg['session'] == pin['session']
            and leg['status'] in ('waiting', 'stopped'), 'The previous leg has no settled interruption.')
    row = leg['records'][-1]
    req, receipt = row['request'], row['receipt']
    require(req.get('step') == 'actTwoFieldCombat' and req.get('session') == pin['session']
            and re.fullmatch(r'mission-[0-9a-f]{32}', req['id']), 'Last operation was not a bounded field encounter.')
    pilot = Path(pin['owner']['child']['appDirectory']) / 'User/JsScript/ActOnePilot'
    native_receipt = (pilot / 'receipts' / pin['session'] / (req['id'] + '.json')).read_bytes()
    require(receipt == json.loads(native_receipt), 'Saved combat receipt differs from the native receipt.')
    def frame(number):
        return read(pilot / 'observations' / pin['session'] / ('frame-%04d.json' % number))
    witness = route_cli.field_combat_feedback(row, expected_uid, frame)
    if witness and witness['measuredClear']:
        position = frame(witness['pauseSourceFrameId'])['map']
    else:
        retained = archived_tower_defeat(directory,row,expected_uid,route_cli,native_receipt)
        require(retained, 'Combat has no independently verified experience award and clear field.')
        witness,position = retained
    paths = []
    for ordinal, source in enumerate(launch['routes'][index:], index + 1):
        path = directory / ('route-%03d.json' % ordinal)
        require(path == Path(source['path']).resolve() and hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256'],
                'Archived route snapshot changed.')
        paths.append(path)
    first = read(paths[0])
    points, cursor = first['waypoints'], leg['nextWaypointIndex']
    require(first.get('objective') == route_cli.EXPLORATION_OBJECTIVE and points == leg['route']['waypoints']
            and type(cursor) is int and 0 <= cursor < len(points), 'No pending exploration waypoint in the interrupted leg.')
    first = dict(first, waypoints=points[cursor:], startNear=dict(map=position['map'], x=position['x'], y=position['y'], radius=4))
    first.pop('teleportTo', None)
    route_cli.validate_route(first)
    proof = dict(sourceRun=str(directory), sourceLeg=index+1, nextWaypointIndex=cursor, **witness)
    return first, paths[1:], proof, pin


def run(args, *, expected_owner=None, dependencies=None):
    """Console API also used by an opt-in caller retaining its original authenticated owner pair."""
    rdp, _, route_cli = helpers() if dependencies is None else dependencies
    recovered = None
    if getattr(args, 'resume_after_defeat', None):
        first, following, proof, pin = resume_defeated_route(args.resume_after_defeat, args.expected_uid, route_cli)
        remaining = args.progress.resolve().with_suffix('.remaining-route.json')
        require(not args.progress.exists() and not remaining.exists(), 'Provide a new output path for the continuation.')
        remaining.parent.mkdir(parents=True, exist_ok=True)
        with remaining.open('xb') as stream:
            stream.write(leg_bytes(first))
        args.route = [remaining, *following]
        expected_owner = pin['owner']
        recovered = dict(evidence=proof, game=pin['game'])
    require(1 <= len(args.route) <= 20 and 1000 <= args.deadline_ms <= route_cli.MAX_CONTROLLER_DEADLINE_MS
            and 1 <= args.max_segments <= route_cli.MAX_SEGMENTS and re.fullmatch(r'[0-9]{9,10}', args.expected_uid),
            'Use one to twenty routes, the canonical finite limits, and an explicit numeric account.')
    progress = args.progress.resolve()
    require(not progress.exists(), 'Existing progress is never replayed.')
    use_gpu = getattr(args, 'gpu_adviser', False)
    goal_file = getattr(args, 'gpu_goal_embedding', None)
    goal = None
    if goal_file is not None:
        require(use_gpu, '--gpu-goal-embedding requires --gpu-adviser.')
        path = goal_file.resolve()
        require(path.is_file(), 'GPU goal embedding file does not exist.')
        with path.open('rb') as stream:
            goal_bytes = stream.read(131073)  # Same 128 KiB limit as the installed model's goal reader.
        require(0 < len(goal_bytes) <= 131072, 'GPU goal embedding must contain at most 128 KiB of JSON.')
        document = json.loads(goal_bytes)
        instruction = document.get('instruction') if isinstance(document, dict) else None
        require(isinstance(instruction, str) and instruction.strip() and len(instruction) <= 2000,
                'GPU goal embedding is missing its instruction.')
        goal = dict(source=str(path), sha256=hashlib.sha256(goal_bytes).hexdigest(), instruction=instruction)
    owner = select_owner(rdp.discover(), args.process_id, expected_owner)
    app = Path(owner['child']['appDirectory']).resolve()
    require(not progress.is_relative_to(app / 'User/JsScript/ActOnePilot'), 'Progress must be outside native protocol files.')
    node = args.node or shutil.which('node')
    require(node and Path(node).is_file() and Path(node).name.lower() == 'node.exe',
            'Provide an installed node.exe with --node.')
    output = progress.parent / (progress.stem + '.rdp')
    # Round up for the broker's integral timeout and retain the worker's existing cleanup allowances.
    leg_seconds = (args.deadline_ms + 999) // 1000 + 20
    setup_and_cleanup_seconds = 80 + (GPU_SETUP_SECONDS + 17 if use_gpu else 0)
    broker_leg_limit = (3600 - setup_and_cleanup_seconds) // leg_seconds
    routes, originals = snapshot_routes(args.route, output, route_cli, broker_leg_limit=broker_leg_limit)
    config = dict(version=1, launchId=uuid.uuid4().hex, owner=owner, output=str(output), progress=str(progress),
                  routes=routes, splitRoutes=originals, expectedUid=args.expected_uid, node=str(Path(node).resolve()),
                  allowFieldCombat=args.allow_field_combat, allowDialogue=args.allow_dialogue,
                  saveEncounterFrames=args.save_encounter_frames, gpuAdviser=use_gpu, continuous=getattr(args,'continuous',False),
                  deadlineMs=args.deadline_ms, maxSegments=args.max_segments, continueObjectives=args.continue_objective,
                  stopFiles=[str(p.resolve()) for p in [progress.parent / 'STOP', progress.with_suffix('.STOP'),
                             output / 'STOP', app / 'User/JsScript/ActOnePilot/STOP', *args.stop_file]])
    if recovered is not None:
        config['resumedDefeat'] = recovered
    if goal is not None:
        # Capture the selected bytes once so moving or editing the original cannot change this run.
        (output/'gpu-goal-embedding.json').write_bytes(goal_bytes)
        config['gpuGoalEmbedding'] = goal
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
        if use_gpu:
            report['gpuAdviser'] = worker.get('gpuAdviser')
            if worker.get('status') == 'gpu_unverified':
                report.update(status='gpu_unverified', canonicalStatus=worker.get('canonicalStatus'))
        require(broker.get('returnCode') == 0 and broker.get('timedOut') is False
                and worker.get('exitCode') == 0 and worker.get('status') == 'arrived' and report['pilotRetired'],
                worker.get('error') or 'Route or retirement failed; inspect the unchanged canonical progress and worker result.')
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
