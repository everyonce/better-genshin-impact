"""Selected-release orchestration using the existing authenticated control transport only."""
import json
import os
from pathlib import Path
import re
import time


# The audited first automation build predates uiStatus and the corrected child
# backlink. Its explicit taskRunning/lifecycle fields remain required. No other
# package receives missing-field compatibility just because it calls itself r1.
LEGACY_R1_SHA256 = '7f611984b27be839d1f3d9ee17c8b75383f6708367ff1533420c7d7bc4920a0d'


def _path(control, value):
    """Normalize a local path without permitting a network or relative release."""
    return os.path.normcase(str(control.local_absolute(str(value))).rstrip('\\/'))


def verified_package(control, directory, artifacts, expected=None):
    """Recheck bounded build metadata, portable files and both pinned binary hashes."""
    target = control.local_absolute(str(directory))
    if (target.name.lower() != 'bettergi-english-win-x64'
            or not re.fullmatch(r'release-r[0-9]+', target.parent.name)
            or _path(control, target.parent.parent) != _path(control, artifacts)):
        raise control.ControlError('The child package must be a numbered release in the pinned workspace.')
    control._no_links(target)
    path = target.parent / 'build-manifest.json'
    control._no_links(path)
    if path.stat().st_size > 65536:
        raise control.ControlError('The build manifest exceeds its size limit.')
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    if (type(manifest.get('version')) is not int or manifest['version'] != 1
            or _path(control, manifest.get('targetDirectory')) != _path(control, target)):
        raise control.ControlError('The build manifest does not identify this release.')
    package = control._portable_package(target)
    for key in ('exeSha256', 'dllSha256'):
        if (not isinstance(manifest.get(key), str)
                or manifest[key].lower() != package[key]
                or expected is not None and expected.get(key) != package[key]):
            raise control.ControlError('The selected release binary hash changed or does not match its build manifest.')
    if expected is not None and _path(control, expected['targetDirectory']) != _path(control, target):
        raise control.ControlError('The selected release directory changed.')
    return package


def _legacy(status):
    """Call only after this status has been bound to its verified on-disk package."""
    return (str(status.get('assemblySha256', '')).lower() == LEGACY_R1_SHA256
            and Path(status['appDirectory'].rstrip('\\/')).parent.name == 'release-r1')


def _current_ui(control, status):
    """An explicit degraded state always fails, including for the verified legacy build."""
    if status.get('uiStatus') == 'current' or 'uiStatus' not in status and _legacy(status):
        return
    raise control.ControlError('Current UI status is unavailable or unsupported; no readiness can be claimed.')


def _verified_status(control, status, artifacts):
    """Bind a reported assembly to the validated local release before compatibility checks."""
    package = verified_package(control, status['appDirectory'], artifacts)
    if str(status.get('assemblySha256', '')).lower() != package['dllSha256']:
        raise control.ControlError('The process assembly does not match its verified release.')
    _current_ui(control, status)
    return package


def _same_snapshot(control, current, pinned):
    """Keep process epoch and loaded assembly immutable throughout one operation."""
    if (any(current.get(key) != pinned.get(key) for key in
            ('processId', 'windowsSessionId', 'instanceNonce', 'instanceType'))
            or _path(control, current['appDirectory']) != _path(control, pinned['appDirectory'])
            or str(current.get('assemblySha256', '')).lower() != str(pinned.get('assemblySha256', '')).lower()):
        raise control.ControlError('The pinned process identity or package changed.')
    control.require_role(current, pinned['instanceType'])
    _current_ui(control, current)
    return current


def _read_root(control, root):
    """Read only the authenticated original primary, never substitute a discovered root."""
    current = _same_snapshot(control, control.refresh(root), root)
    if current.get('remoteDesktop') is not False or current.get('automationState') == 'unresponsive':
        raise control.ControlError('The pinned primary is not a current console host.')
    return current


def _idle(control, status):
    """Require explicit idle evidence; missing task/lifecycle fields are never idle."""
    _current_ui(control, status)
    if (status.get('taskRunning') is not False
            or status.get('automationState') not in ('idle', 'game_ready', 'stopped', 'failed', 'cancelled')
            or status.get('agentStreamRunning', False) is not False
            or status.get('pilotState') not in ('idle', 'completed', 'failed', 'cancelled')):
        raise control.ControlError('The child is busy or its idle state is unknown; no task was stopped.')
    return status


def require_idle_restart(control, status):
    """Automatic replacement requires the server's atomic, request-bound contract."""
    if type(status.get('idleRestartVersion')) is not int or status['idleRestartVersion'] != 1:
        raise control.ControlError(
            'This child lacks atomic idle-restart v1; automatic replacement was not attempted. '
            'Perform one controlled explicit hot-replace after stopping work, then retry the shortcut.')


def _connected_root(control, root, child, pinned_root):
    """The independently authenticated legacy fallback must be this invocation's primary."""
    _same_snapshot(control, root, pinned_root)
    return control._require_connected_root(root, child)


def prepare_idle_replacement(control, child, root, pinned_root, pinned_package):
    """Shared pre-dispatch checks for the optional idle-only hot-replace path."""
    if not isinstance(pinned_root, dict) or not isinstance(pinned_package, dict):
        raise control.ControlError('Idle-only replacement requires a pinned primary and package.')
    artifacts = Path(pinned_package['targetDirectory']).parent.parent
    verified_package(control, pinned_package['targetDirectory'], artifacts, pinned_package)
    _verified_status(control, child, artifacts)
    _connected_root(control, root, child, pinned_root)
    current = _same_snapshot(control, control.refresh(child), child)
    require_idle_restart(control, current)
    if current.get('rootProcessId') != root['processId'] and not (
            current.get('rootProcessId') is None and _legacy(current)):
        raise control.ControlError('The child does not belong to the pinned primary.')
    return _idle(control, current)


def replacement_candidate(control, previous, root, discovery, pinned_root, package):
    """Ignore only the known retiring process; other ambiguity remains a hard failure."""
    _connected_root(control, root, previous, pinned_root)
    remaining = {'instances': [item for item in discovery['instances']
                               if item.get('processId') != previous['processId']],
                 'unavailable': [item for item in discovery.get('unavailable', [])
                                 if not (item.get('processId') == previous['processId']
                                         and item.get('windowsSessionId') == previous['windowsSessionId'])]}
    child = control._startup_child(root, remaining)
    if child is None:
        return None
    if (child.get('instanceNonce') == previous['instanceNonce']
            or _path(control, child['appDirectory']) != _path(control, package['targetDirectory'])
            or str(child.get('assemblySha256', '')).lower() != package['dllSha256']):
        raise control.ControlError('A different child appeared after replacement; selected readiness is not verified.')
    return child


def _target_settings(control, source, target):
    """Retain existing target settings; stage only when the selected copy has none."""
    config = Path(target) / 'User/config.json'
    if not config.exists():
        control.stage_configuration(str(source), str(target))
    control._no_links(config)
    if not config.is_file() or not 0 < config.stat().st_size <= 16 * 1024 * 1024:
        raise control.ControlError('The selected release has no bounded local configuration.')


def ensure_child(control, root, target, exe_hash, dll_hash, expected_nonce, timeout,
                 preserve_window=False, start_game=False):
    """Ensure one selected child without replacing the primary or cancelling active work."""
    deadline = time.monotonic() + timeout

    def remaining():
        """All polling and handoff stages share the original bounded deadline."""
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise control.ControlError('Selected-child readiness timed out; no mutation was replayed.')
        return seconds

    control.require_role(root, 'Primary')
    if not expected_nonce or root.get('instanceNonce') != expected_nonce:
        raise control.ControlError('The primary nonce no longer matches the approved wrapper.')
    if any(not isinstance(value, str) or re.fullmatch('[0-9a-fA-F]{64}', value) is None
           for value in (exe_hash, dll_hash)):
        raise control.ControlError('Both selected binary hashes must be explicit SHA256 values.')
    target = control.local_absolute(str(target))
    artifacts = target.parent.parent
    package = verified_package(control, target, artifacts, {
        'targetDirectory': str(target), 'exeSha256': exe_hash.lower(), 'dllSha256': dll_hash.lower()})
    _verified_status(control, root, artifacts)
    _read_root(control, root)

    def candidate(current_root, discovery):
        """Legacy identity is an internal upgrade candidate, never external readiness."""
        child = control._startup_child_candidate(current_root, discovery)
        if child is not None:
            _verified_status(control, child, artifacts)
            if child.get('rootProcessId') != root['processId'] and not (
                    child.get('rootProcessId') is None and _legacy(child)):
                raise control.ControlError('The child does not advertise the pinned root identity.')
        return child

    startup = control.start_child(root, remaining(), preserve_window, _candidate=candidate,
                                  _read_root=lambda _: _read_root(control, root))
    child = startup['child']
    replaced = False
    previous_pid = None
    if _path(control, child['appDirectory']) != _path(control, target):
        require_idle_restart(control, child)
        # Join only the automatic game-start lifecycle, not another running task.
        while child.get('automationState') == 'starting_game':
            remaining()
            time.sleep(min(.5, remaining()))
            child = _same_snapshot(control, control.refresh(child), child)
        _idle(control, child)
        resolved = control.resolve_child_root(child, strict_discovery=True)
        _connected_root(control, resolved, child, root)
        _target_settings(control, child['appDirectory'], target)
        result = control.hot_replace(child, str(target), remaining(), idle_only=True,
                                     pinned_root=root, pinned_package=package)
        previous_pid = child['processId']
        child, replaced = result['child'], True
    elif child.get('rootProcessId') != root['processId']:
        raise control.ControlError('A legacy child can only be upgraded to a different verified release, never reused as ready.')

    # One final authenticated discovery excludes a conflicting/replaced process.
    remaining()
    current_root = _read_root(control, root)
    _connected_root(control, current_root, child, root)
    current = control._startup_child(current_root, control.discover())
    if current is None:
        raise control.ControlError('The selected child disappeared before readiness.')
    child = _same_snapshot(control, current, child)
    _verified_status(control, child, artifacts)
    verified_package(control, target, artifacts, package)
    if (str(child.get('assemblySha256', '')).lower() != package['dllSha256']
            or _path(control, child['appDirectory']) != _path(control, target)):
        raise control.ControlError('The child does not match the pinned selected release.')
    if start_game:
        if (not (child.get('automationState') == 'game_ready' and child.get('runtimeRunning') is True)
                and child.get('automationState') != 'starting_game'):
            _idle(control, child)
        child = control.start_game(child, remaining())
        child = _same_snapshot(control, control.refresh(child), child)
        if not control._game_runtime_ready(child):
            raise control.ControlError('The game lifecycle changed before final readiness.')
    if replaced:
        _idle(control, child)
        if not control._game_runtime_ready(child):
            raise control.ControlError('The replacement game lifecycle did not finish.')
    current_root = _read_root(control, root)
    _connected_root(control, current_root, child, root)
    if not preserve_window and current_root.get('childWindowMinimized') is not True:
        raise control.ControlError('The RDP window is no longer verified minimized.')
    remaining()
    return {'success': True, 'rootReady': True, 'childReady': True,
            'gameReady': child.get('automationState') == 'game_ready' and child.get('runtimeRunning') is True,
            'readinessScope': 'game_runtime' if start_game else 'selected_child_control_endpoint',
            'root': current_root, 'child': child, 'selectedPackage': package,
            'childStartDispatched': startup['childStartDispatched'], 'childReplaced': replaced,
            'previousProcessId': previous_pid, 'windowPolicy': startup['windowPolicy']}
