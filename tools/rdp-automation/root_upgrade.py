"""One opt-in root/idle-bootstrap retirement and inactive root-store handoff; no work is resumed."""
import ctypes
from datetime import datetime, timedelta, timezone
import uuid
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def validate_root_expectation(value, error=ValueError):
    """Reject partial/coerced/cross-command identities before opening any pipe."""
    fields = {'processId', 'windowsSessionId', 'startedFileTime', 'appDirectory', 'exeSha256', 'dllSha256'}
    if (type(value) is not dict or set(value) != fields
            or any(type(value[x]) is not int or not 0 < value[x] <= (2**63 - 1 if x == 'startedFileTime' else 2**31 - 1)
                   for x in ('processId', 'windowsSessionId', 'startedFileTime'))
            or not isinstance(value['appDirectory'], str) or not 1 <= len(value['appDirectory']) <= 512
            or not re.fullmatch(r'[A-Za-z]:[\\/].+', value['appDirectory'])
            or any(not isinstance(value[x], str) or not re.fullmatch('[0-9a-f]{64}', value[x])
                   for x in ('exeSha256', 'dllSha256'))):
        raise error('Root upgrade requires the complete exact native identity and lowercase package hashes.')


class OwnedProcess:
    """Retain a query/synchronize-only handle across retirement; never terminate or discover processes."""
    def __init__(self, pid):
        self.handle = None
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        specs = {
            'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
            'GetProcessTimes': ([wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4, wintypes.BOOL),
            'ProcessIdToSessionId': ([wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            'QueryFullProcessImageNameW': ([wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        }
        for name, (args, result) in specs.items():
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result
        handle = self.api.OpenProcess(0x1000 | 0x100000, False, pid)
        if not handle:
            raise OSError(ctypes.get_last_error(), 'Cannot own the exact process lifetime; no fallback is permitted.')
        self.handle = handle
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            session, capacity = wintypes.DWORD(), wintypes.DWORD(32768)
            image = ctypes.create_unicode_buffer(capacity.value)
            if (not self.api.GetProcessTimes(handle, *(ctypes.byref(t) for t in times))
                    or not self.api.ProcessIdToSessionId(pid, ctypes.byref(session))
                    or not self.api.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(capacity))):
                raise OSError(ctypes.get_last_error(), 'Native process identity is unavailable.')
            self.identity = {'processId': pid, 'windowsSessionId': session.value,
                             'startedFileTime': (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                             'executable': image.value}
            self.require_alive()
        except BaseException as error:
            try:
                self.close()
            except OSError as cleanup:
                error.add_note('Partial handle cleanup failed: ' + str(cleanup))
            raise

    def require_alive(self):
        """Check the owned lifetime, never a newly looked-up PID."""
        if self.handle is None or self.api.WaitForSingleObject(self.handle, 0) != 258:
            raise OSError('The retained process lifetime is no longer alive.')

    def wait_exit(self, seconds):
        """A signaled owned process is independent evidence of exit, including after its endpoint disappeared."""
        if self.handle is None or self.api.WaitForSingleObject(self.handle, min(300000, max(0, int(seconds * 1000)))) != 0:
            raise OSError('Exact process retirement was not confirmed within the bounded window.')

    def close(self):
        """Transfer the handle out before the sole close attempt, preserving at-most-once ownership."""
        handle, self.handle = self.handle, None
        if handle is not None and not self.api.CloseHandle(handle):
            raise OSError(ctypes.get_last_error(), 'Process handle close failed.')


def _launcher(target, timeout, output, phase, extra):
    """Run the existing bounded ordinary-token launcher; retain complete output on failure."""
    argv = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
            str(Path(__file__).with_name('start-host.ps1')), '-TargetDirectory', str(target),
            '-PythonExe', sys.executable, '-TimeoutSeconds', str(max(5, min(180, int(timeout)))), *extra]
    paths = [output / (phase + '-stdout.json'), output / (phase + '-stderr.txt')]
    with paths[0].open('xb') as stdout, paths[1].open('xb') as stderr:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                timeout=timeout, creationflags=0x08000000, check=False)
    if any(path.stat().st_size > 65536 for path in paths):
        raise ValueError('Launcher output exceeded its 64 KiB acceptance bound; full output is retained.')
    if result.returncode != 0 or paths[1].stat().st_size:
        raise ValueError('The existing host launcher failed; no automatic rollback or retry.')
    return json.loads(paths[0].read_text(encoding='utf-8-sig'))


def _verify_launcher(target, root_session, timeout, output):
    """Validate the actual fixed task/helper before retirement; never install or repair it here."""
    value = _launcher(target, timeout, output, 'approved-task-preflight', ['-ValidateApprovedTask'])
    if value.get('approvedTaskVerified') is not True or value.get('windowsSessionId') != root_session:
        raise ValueError('The original root session has no verified fixed approved launcher.')
    return value


def _write_startup_binding(control, target, package, root_session, game, remaining):
    """Publish only a bounded held-startup identity; no arbitrary arguments or settings enter the approved action."""
    control._no_links(target)
    for name in ('root-upgrade-startup.json', 'root-upgrade-startup.consumed.json', 'root-upgrade-startup.completed.json'):
        path = target / name
        if os.path.lexists(path):
            raise control.ControlError('An upgrade startup record already exists; preserve it and do not reuse this package.')
    now = datetime.now(timezone.utc)
    value = dict(version=1, nonce=uuid.uuid4().hex, targetDirectory=str(target), rootSessionId=root_session,
                 cloneSessionId=game['windowsSessionId'], gameProcessId=game['processId'],
                 gameStartedFileTime=game['startedFileTime'], exeSha256=package['exeSha256'], dllSha256=package['dllSha256'],
                 createdUtc=now.isoformat(), expiresUtc=(now + timedelta(seconds=min(300, remaining))).isoformat())
    raw = json.dumps(value, separators=(',', ':')).encode('utf-8')
    if len(raw) > 4096:
        raise control.ControlError('Startup binding exceeded 4 KiB.')
    path = target / 'root-upgrade-startup.json'
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def _launch_host(target, game, timeout, output):
    """Use the unchanged elevated fixed action; its new binary consumes the bounded package-local binding."""
    value = _launcher(target, timeout, output, 'launcher', ['-UseApprovedTask',
        '-UpgradeSessionId', str(game['windowsSessionId']), '-UpgradeGameProcessId', str(game['processId']),
        '-UpgradeGameStartedFileTime', str(game['startedFileTime'])])
    if value.get('rootReady') is not True or value.get('action') != 'launched':
        raise ValueError('A newly launched primary endpoint was not confirmed.')
    return value['root']


def _same(control, current, original):
    """Join authenticated status identity and native package origin without accepting a substituted endpoint."""
    for key in ('processId', 'windowsSessionId', 'instanceNonce', 'instanceType', 'appDirectory', 'assemblySha256'):
        if current.get(key) != original.get(key):
            raise control.ControlError('The selected process identity changed before upgrade.')
    return current


def _idle(control, status, *, child):
    """Require current explicit idle state; this does not prove legacy multi-file store coherence."""
    from child_reconciliation import _current_ui, _legacy, _verified_status
    control.require_role(status, 'ChildSession' if child else 'Primary')
    _current_ui(control, status)
    stream_idle = status.get('agentStreamRunning') is False
    if not child and 'agentStreamRunning' not in status and status.get('remoteDesktop') is False:
        # Only the verified R1 primary's old schema omits this field. Bind its
        # actual package before interpreting the omission; never synthesize status.
        directory = control.local_absolute(status['appDirectory'])
        _verified_status(control, status, directory.parent.parent)
        stream_idle = _legacy(status)
    if (status.get('taskRunning') is not False
            or status.get('runtimeRunning') is not False or not stream_idle
            or status.get('pilotState') not in ('idle', 'completed', 'failed', 'cancelled')
            or child and not control._control_endpoint_ready(status)):
        raise control.ControlError('Upgrade requires a current idle, detached endpoint; no task is stopped automatically.')
    return status


def _config_pin(control, directory):
    """Record only bounded file identity, never configuration values or credentials."""
    path = Path(directory) / 'User/config.json'
    control._no_links(path)
    if not path.is_file() or not 0 < path.stat().st_size <= 16 * 1024 * 1024:
        raise control.ControlError('A bounded original config.json is required.')
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': control._sha256(path)}


def _check_target_conflicts(control, source, target):
    """Refuse known inactive-target conflicts before retirement; this is not an active-store coherence claim."""
    source = Path(source)
    for relative in ('User/config.json', 'User/ExternalControl/enable-quest-control.json'):
        original, destination = source / relative, target / relative
        if original.is_file() and os.path.lexists(destination):
            control._no_links(original)
            control._no_links(destination)
            if (not destination.is_file() or original.stat().st_size > 16 * 1024 * 1024
                    or destination.stat().st_size > 16 * 1024 * 1024
                    or control._sha256(original) != control._sha256(destination)):
                raise control.ControlError(f'The inactive target has conflicting {relative}; no original process was retired.')
    if os.path.lexists(target / 'User/Pulonia'):
        # Reuse the existing bounded opaque inventory. Staging independently repeats it after actual retirement.
        if control._pulonia_inventory(source / 'User/Pulonia')[0] != control._pulonia_inventory(target / 'User/Pulonia')[0]:
            raise control.ControlError('The inactive target has conflicting User/Pulonia; no original process was retired.')


def upgrade_root_child(control, args, *, process_factory=OwnedProcess, launch=_launch_host, verify_launcher=_verify_launcher):
    """Retire an already upgraded bootstrap; stage the root's opaque files and start a held endpoint pair once."""
    from child_reconciliation import verified_package
    if (type(args.timeout) is not int or not 30 <= args.timeout <= 300
            or any(type(v) is not int or v <= 0 for v in (args.process_id, args.windows_session_id,
                                                          args.game_process_id, args.game_started_file_time))
            or not isinstance(args.instance_nonce, str) or not 1 <= len(args.instance_nonce) <= 128):
        raise control.ControlError('Upgrade requires exact fresh child/game identities and a 30..300 second bound.')
    deadline = time.monotonic() + args.timeout
    output = control.local_absolute(args.job_dir)
    control._no_links(output.parent)
    output_created = False
    evidence = {'version': 1, 'success': False, 'phase': 'preflight', 'retirementAttempted': False,
                'rootRetired': False, 'childRetired': False, 'schedulingHeld': False,
                'legacyStoreCoherenceVerified': False, 'configurationSelection': 'original-root', 'cleanupErrors': []}
    owners = []

    def remaining():
        """Every wait/launch/staging boundary consumes one finite transaction deadline."""
        value = deadline - time.monotonic()
        if value <= 0:
            raise control.ControlError('Upgrade deadline elapsed; retained evidence must be inspected before any new attempt.')
        return value

    def own(pid):
        """Retain each actual handle immediately after successful construction."""
        value = process_factory(pid)
        owners.append(value)
        return value

    try:
        child = _idle(control, control.exchange('status', args.process_id, args.windows_session_id), child=True)
        if child['instanceNonce'] != args.instance_nonce or child.get('rootUpgradeVersion') != 1:
            raise control.ControlError('The exact idle bootstrap must advertise root-upgrade v1; use existing endpoint-only hot-replace first.')
        root = _idle(control, control.resolve_child_root(child, strict_discovery=True), child=False)
        if root.get('childWindowMinimized') is not True:
            raise control.ControlError('The original root must already be minimized.')
        target = control.local_absolute(args.target_directory)
        artifacts = target.parent.parent
        for directory in (Path(root['appDirectory']), Path(child['appDirectory']), target):
            if output == directory or directory in output.parents or output in directory.parents:
                raise control.ControlError('Upgrade evidence must be separate from every participating package.')
        output.mkdir(exist_ok=False)
        output_created = True
        package = verified_package(control, target, artifacts)
        bootstrap = verified_package(control, child['appDirectory'], artifacts)
        original = verified_package(control, root['appDirectory'], artifacts)
        if root.get('assemblySha256', '').lower() != original['dllSha256'] or child.get('assemblySha256', '').lower() != bootstrap['dllSha256']:
            raise control.ControlError('Actual loaded endpoint assemblies differ from their verified package.')
        if (len({os.path.normcase(str(control.local_absolute(str(x)))) for x in (root['appDirectory'], child['appDirectory'], target)}) != 3
                or any(package[k] != bootstrap[k] for k in ('exeSha256', 'dllSha256'))):
            raise control.ControlError('Final and bootstrap must be distinct sibling packages with identical new binaries.')
        # Published User defaults are preserved; the existing stager rejects conflicting config/Pulonia.
        discovery = control.discover()
        if discovery.get('unavailable') or {x['processId'] for x in discovery['instances']} != {root['processId'], child['processId']}:
            raise control.ControlError('Only the selected root and bootstrap endpoints may participate; unresolved endpoints refuse upgrade.')
        root_owner, child_owner, game_owner = own(root['processId']), own(child['processId']), own(args.game_process_id)
        for status, owner in ((root, root_owner), (child, child_owner)):
            if (owner.identity['windowsSessionId'] != status['windowsSessionId']
                    or os.path.normcase(str(Path(owner.identity['executable']).parent)) != os.path.normcase(str(control.local_absolute(status['appDirectory'])))
                    or Path(owner.identity['executable']).name.lower() != 'bettergi.exe'):
                raise control.ControlError('Native process ownership differs from authenticated status.')
        game = game_owner.identity
        if (game['windowsSessionId'] != child['windowsSessionId'] or game['startedFileTime'] != args.game_started_file_time
                or Path(game['executable']).stem not in ('YuanShen', 'GenshinImpact')):
            raise control.ControlError('The protected original game lifetime is not exact.')
        root_config, child_config = _config_pin(control, root['appDirectory']), _config_pin(control, child['appDirectory'])
        _check_target_conflicts(control, root['appDirectory'], target)
        if any(os.path.lexists(target / name) for name in ('root-upgrade-startup.json', 'root-upgrade-startup.consumed.json', 'root-upgrade-startup.completed.json')):
            raise control.ControlError('The target already has startup history; select a fresh package.')
        evidence.update(rootBefore=root, childBefore=child, game=game, rootNative=root_owner.identity,
                        childNative=child_owner.identity, rootConfig=root_config, childConfig=child_config,
                        configurationsDiffer=root_config['sha256'] != child_config['sha256'], package=package)
        expected = {k: root_owner.identity[k] for k in ('processId', 'windowsSessionId', 'startedFileTime')}
        expected.update(appDirectory=original['targetDirectory'], exeSha256=original['exeSha256'], dllSha256=original['dllSha256'])
        validate_root_expectation(expected, control.ControlError)
        evidence['approvedTaskPreflight'] = verify_launcher(target, expected['windowsSessionId'], min(60, remaining()), output)
        _idle(control, _same(control, control.refresh(root), root), child=False)
        child = _idle(control, _same(control, control.refresh(child), child), child=True)
        game_owner.require_alive()
        remaining()
        evidence.update(phase='retirement', retirementAttempted=True)
        control.mutate('retireRootForUpgrade', child, rootUpgrade=expected)
        root_owner.wait_exit(remaining())
        evidence['rootRetired'] = True
        child_owner.wait_exit(remaining())
        evidence['childRetired'] = True
        game_owner.require_alive()
        remaining()
        evidence['phase'] = 'inactive_staging'
        staged = control.stage_configuration(root['appDirectory'], str(target), preserve_pulonia=True, source_quiescent=True)
        report = Path(staged['reportFile'])
        evidence['staging'] = {'path': str(report), 'bytes': report.stat().st_size, 'sha256': control._sha256(report)}
        if (_config_pin(control, root['appDirectory']) != root_config
                or _config_pin(control, child['appDirectory']) != child_config
                or _config_pin(control, target)['sha256'] != root_config['sha256']):
            raise control.ControlError('Original configuration bytes drifted or the final package did not preserve root selection.')
        # The standard root launcher rechecks the same package; no child-config staging follows this point.
        verified_package(control, target, artifacts, package)
        game_owner.require_alive()
        evidence['startupBinding'] = _write_startup_binding(control, target, package, expected['windowsSessionId'], game, remaining())
        evidence['phase'] = 'held_root_launch'
        new_root = launch(target, game, min(180, remaining()), output)
        evidence['rootAfter'] = new_root
        control.require_role(new_root, 'Primary')
        if (new_root.get('windowsSessionId') != expected['windowsSessionId']
                or new_root.get('processId') == root['processId'] or new_root.get('instanceNonce') == root['instanceNonce']
                or os.path.normcase(str(control.local_absolute(new_root['appDirectory']))) != os.path.normcase(str(target))
                or new_root.get('assemblySha256', '').lower() != package['dllSha256']):
            raise control.ControlError('The new root identity, session or final package was not confirmed.')
        if (new_root.get('puloniaSchedulingHeld') is not True or new_root.get('upgradeSessionId') != game['windowsSessionId']
                or new_root.get('upgradeGameProcessId') != game['processId']
                or new_root.get('upgradeGameStartedFileTime') != game['startedFileTime']):
            raise control.ControlError('The replacement root did not preserve its exact hold and existing lifetime binding.')
        evidence['phase'] = 'endpoint_child_launch'
        def selected_child(current_root, discovered):
            # Reuse the endpoint-only starter, but never its separate replacement/config-staging branch.
            selected = control._startup_child(current_root, discovered)
            if selected is not None and (os.path.normcase(str(control.local_absolute(selected['appDirectory']))) != os.path.normcase(str(target))
                                         or selected.get('assemblySha256', '').lower() != package['dllSha256']):
                raise control.ControlError('A foreign child appeared; no configuration staging or replacement is authorized.')
            return selected

        def held_root(_):
            current = _same(control, control.refresh(new_root), new_root)
            if current.get('puloniaSchedulingHeld') is not True:
                raise control.ControlError('The explicit scheduling hold is no longer present.')
            game_owner.require_alive()
            return current

        def before_child(_):
            verified_package(control, target, artifacts, package)
            held_root(None)

        final = control.start_child(new_root, remaining(), False, _candidate=selected_child,
                                    _read_root=held_root, startup_mode='controlEndpoint', _before_dispatch=before_child)
        evidence['pairAfter'] = final
        current_root = _same(control, control.refresh(final['root']), new_root)
        if (current_root.get('puloniaSchedulingHeld') is not True or current_root.get('childWindowMinimized') is not True
                or not control._control_endpoint_ready(final['child'])):
            raise control.ControlError('The held minimized root and endpoint-only child are not verified.')
        game_owner.require_alive()
        remaining()
        evidence.update(success=True, phase='complete_scheduling_held', schedulingHeld=True,
                        copyAndProcessHandoffVerified=True, workResumed=False)
    except (control.ControlError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        evidence['error'] = str(error)[:2048] or type(error).__name__
    finally:
        for owner in reversed(owners):
            try:
                owner.close()
            except OSError as error:
                evidence['cleanupErrors'].append(str(error)[:512])
                evidence['success'] = False
        encoded = json.dumps(evidence, ensure_ascii=True, allow_nan=False, indent=2).encode('utf-8')
        if len(encoded) > 65536:
            raise control.ControlError('Upgrade evidence exceeds 64 KiB; no success can be published.')
        if output_created:
            with (output / 'result.json').open('xb') as stream:
                stream.write(encoded)
    return evidence


def resume_root(control, root, nonce):
    """Separate explicit operation; the upgrade path never calls this or infers resume permission."""
    if root.get('instanceNonce') != nonce:
        raise control.ControlError('Resume requires the exact current root nonce.')
    root = _idle(control, _same(control, control.refresh(root), root), child=False)
    if root.get('puloniaSchedulingHeld') is not True:
        raise control.ControlError('This root is not held for explicit upgrade resume.')
    child = control._startup_child(root, control.discover())
    if child is None:
        raise control.ControlError('The final authenticated child is absent.')
    child = _idle(control, _same(control, control.refresh(child), child), child=True)
    if (child.get('appDirectory') != root.get('appDirectory')
            or child.get('assemblySha256') != root.get('assemblySha256')
            or child.get('windowsSessionId') != root.get('upgradeSessionId')):
        raise control.ControlError('The final child package/session does not match the held root.')
    result = control.mutate('resumeRootAfterUpgrade', root)
    current = _same(control, result, root)
    if current.get('puloniaSchedulingHeld') is not False:
        raise control.ControlError('Explicit resume was not confirmed; do not retry automatically.')
    return {'root': current, 'schedulingHeld': False, 'explicitResume': True,
            'legacyStoreCoherenceVerified': False}
