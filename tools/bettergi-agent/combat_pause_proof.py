"""Read retained native inventory transitions; never issue UI or gameplay commands."""
from collections import OrderedDict
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
from threading import Lock


CORE_REVISIONS = frozenset(('main.js', 'engine.js', 'bgi.js', 'mission.js', 'combat.js', 'recovery.js'))

# Retain only bounded digest/revision metadata, never script bytes, paths or timestamps.
_REVISION_CACHE_LIMIT = 128
_revision_cache = OrderedDict()
_revision_cache_lock = Lock()


def require(value, message):
    """Reject incomplete native UI provenance before it can qualify model preparation."""
    if not value:
        raise ValueError(message)


def number(value):
    """Accept finite JSON numbers without treating booleans as timestamps."""
    return type(value) in (int, float) and math.isfinite(value)


def _uncached_revision(raw):
    """Replay the native pilot's FNV-1a hash over JavaScript UTF-16 code units."""
    encoded = raw.decode('utf-8-sig').encode('utf-16-le')
    value = 2166136261
    for index in range(0, len(encoded), 2):
        value = ((value ^ int.from_bytes(encoded[index:index + 2], 'little')) * 16777619) & 0xffffffff
    return format(value, 'x')


def revision(raw):
    """Reuse a content-identical FNV result without skipping fresh source reads or SHA checks."""
    if type(raw) is not bytes:
        # Preserve the existing decoder behavior for mutable or otherwise unusual callers.
        return _uncached_revision(raw)
    key = hashlib.sha256(raw).digest()
    with _revision_cache_lock:
        cached = _revision_cache.get(key)
        if cached is not None:
            _revision_cache.move_to_end(key)
            return cached
    # Decode and hash outside the lock; concurrent misses may safely calculate the same result.
    value = _uncached_revision(raw)
    with _revision_cache_lock:
        _revision_cache[key] = value
        _revision_cache.move_to_end(key)
        if len(_revision_cache) > _REVISION_CACHE_LIMIT:
            _revision_cache.popitem(last=False)
    return value


def inventory_visible(observation):
    """Apply the existing exact ordinary-inventory anchors without manufacturing fresh time."""
    hud, rows = observation.get('hud') or {}, observation.get('ocr') or []
    require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows), 'Malformed inventory OCR')
    if observation.get('map') is not None or any(hud.get(key) is not False for key in
            ('world', 'dialogueReady', 'choice', 'journal', 'bigMap', 'climbing', 'auto')):
        return False
    categories = ('Food', 'Weapons', 'Artifacts', 'Character Development Items', 'Materials',
                  'Gadgets', 'Quest', 'Precious Items', 'Furnishings')
    text = lambda row: str(row.get('text', '')).strip()
    def box(row, x0, x1, y0, y1, w0, w1, h0=None, h1=None):
        """Use the native gate's same positive geometry constraints."""
        return (all(number(row.get(key)) for key in ('x', 'y', 'width', 'height'))
            and x0 <= row['x'] <= x1 and y0 <= row['y'] <= y1 and w0 <= row['width'] <= w1
            and (h0 is None or h0 <= row['height'] <= h1))
    headers = [row for row in rows if text(row) in categories and box(row, 100, 250, 15, 70, 50, 180, 20, 55)]
    capacity = [row for row in rows if box(row, 1450, 1810, 15, 75, 180, 360)
        and (re.fullmatch(r'Inventory capacity\s+\d+/\d+', text(row), re.I)
             or len(headers) == 1 and re.fullmatch(re.escape(text(headers[0])) + r' \d+/\d+', text(row)))]
    titles = [row for row in rows if 5 <= len(text(row)) <= 80 and box(row, 1280, 1810, 95, 190, 180, 500, 25, 70)]
    return (len(headers) == len(capacity) == len(titles) == 1
        and not any(text(row) in ('Confirm', 'Cancel', 'Amount to use') for row in rows))


def inspect_transition(folder, owner, operation, *, root, read_file=None):
    """Join exact helper artifacts, native originals, one input and released original ownership.

    A supplied reader supports replay from an immutable archive. Legacy UI times
    remain wall-clock diagnostics; this function makes no physical-delivery claim.
    """
    require(operation in ('pause', 'resume', 'verify'), 'Unknown inventory transition')
    root, folder = Path(root).resolve(), Path(folder).absolute()
    require(folder == folder.resolve() and folder.is_relative_to(root / 'artifacts'), 'UI proof is outside artifacts')
    files = {}
    def read(path):
        """Retain every exact dependency and reject changed bytes within one validation."""
        path = Path(path).absolute()
        require(path == path.resolve() and path.is_relative_to(root / 'artifacts'), 'UI proof source escaped artifacts')
        if read_file is not None:
            raw = read_file(path)
        else:
            with path.open('rb') as stream:
                info = os.fstat(stream.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                    and 0 < info.st_size <= 16 * 1024 * 1024, 'Invalid bounded UI evidence')
                raw = stream.read(info.st_size + 1)
            require(len(raw) == info.st_size, 'UI evidence changed size while reading')
        require(type(raw) is bytes and 0 < len(raw) <= 16 * 1024 * 1024, 'Invalid bounded UI evidence')
        sha = hashlib.sha256(raw).hexdigest()
        require(str(path) not in files or files[str(path)] == sha, 'UI evidence changed during validation')
        files[str(path)] = sha
        return raw
    def document(path):
        """Decode only retained JSON objects."""
        value = json.loads(read(path))
        require(isinstance(value, dict), 'Expected UI evidence object')
        return value
    plan, report = document(folder / 'plan.json'), document(folder / 'result.json')
    cleanup = document(folder / 'owner-after-stop.json')
    require(plan.get('owner') == owner and report.get('status') == 'completed' and report.get('modelLoaded') is False
        and report.get('ownerIdleMinimizedAfter') is True and report.get('temporaryGroupRemoved') is True
        and report.get('ownTerminalRequestRemoved') is True
        and not any(report.get(key) for key in ('error', 'cleanupError', 'failureCaptureError'))
        and all(plan.get(key) is False for key in ('modelLoaded', 'autoEnterGame', 'walkingAllowed', 'attacksAllowed')),
        'UI transition did not retain a clean input-limited owner')
    session = report.get('scriptSession')
    require(isinstance(session, str) and re.fullmatch(r'[A-Za-z0-9-]{1,100}', session), 'Invalid UI script session')
    for role in ('root', 'child'):
        status = cleanup.get(role) or {}
        require(all(status.get(key) == value for key, value in owner[role].items()), 'UI cleanup owner changed')
        require(all(status.get(key) is False for key in ('taskRunning', 'agentStreamRunning', 'serviceOwnsPilot')),
                'UI cleanup retained active or unknown ownership')
    parent, child = cleanup['root'], cleanup['child']
    require(parent.get('uiStatus') == 'current' and parent.get('childWindowMinimized') is True
        and parent.get('childConnectedState') == 1 and parent.get('childSessionId') == owner['child']['windowsSessionId']
        and child.get('rootProcessId') == owner['root']['processId'] and child.get('scriptSession') == session
        and child.get('runtimeRunning') is True and child.get('automationState') == 'game_ready'
        and child.get('pilotState') in ('idle', 'completed', 'failed', 'cancelled', 'stopped', 'faulted'),
        'UI transition did not retire in the original minimized runtime')
    app = Path(child['appDirectory']).absolute()
    require(app == app.resolve() and app.is_relative_to(root / 'artifacts') and app.name == 'BetterGI-English-win-x64',
            'UI proof application directory changed')
    pilot = app / 'User/JsScript/ActOnePilot'
    sources = plan.get('sourceFiles')
    require(isinstance(sources, dict) and 9 <= len(sources) <= 128
        and CORE_REVISIONS | {'world-inventory.js', 'manifest.json', 'settings.json'} <= set(sources), 'Incomplete native UI sources')
    revisions = {}
    for name, sha in sources.items():
        require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', name), 'Invalid UI source name')
        archived = read(folder / 'source-snapshot' / name)
        require(hashlib.sha256(archived).hexdigest() == sha and read(pilot / name) == archived, 'Native UI source bytes changed')
        if name.endswith('.js'):
            revisions[name] = revision(archived)
    group_raw = read(folder / 'group.json')
    require(hashlib.sha256(group_raw).hexdigest() == plan.get('groupSha256'), 'UI group hash changed')
    group, after_group = json.loads(group_raw), document(folder / 'group-after-stop.json')
    after_group['index'] = group.get('index')
    require(after_group == group, 'UI group changed during cleanup')
    pathing = group.get('config', {}).get('pathingConfig', {})
    require(all(pathing.get(key) is False for key in ('enabled', 'autoPickEnabled', 'autoSkipEnabled',
        'autoRunEnabled', 'autoFightEnabled', 'jsScriptUseEnabled', 'soloTaskUseFightEnabled')),
        'UI proof enabled unrelated automation')
    projects = group.get('projects')
    require(isinstance(projects, list) and len(projects) == 1 and projects[0].get('folderName') == 'ActOnePilot'
        and projects[0].get('type') == 'Javascript' and projects[0].get('runNum') == 1
        and projects[0].get('jsScriptSettingsObject') == dict(enableInput=operation != 'verify', autoEnterGame=False),
        'UI group authority changed')
    if operation == 'verify':
        require(plan.get('allowedPilotOperations') == ['observe']
            and type(plan.get('maximumObservationRequests')) is int and plan['maximumObservationRequests'] == 1
            and plan.get('inputEnabled') is False, 'Passive inventory verification acquired input authority')
        require(pathing.get('autoEatEnabled', False) is False
            and group.get('config', {}).get('enableShellConfig', False) is False,
            'Passive inventory group enabled unrelated automation')
    controls = report.get('controls')
    require(isinstance(controls, list) and [row.get('command') for row in controls] == ['startPilot', 'stopPilot'],
            'UI lifecycle was repeated or not retired')
    for row in controls:
        require(type(row.get('receivedAtUnixNs')) is int and row['receivedAtUnixNs'] > 0
            and all((row.get('status') or {}).get(key) == value for key, value in owner['child'].items())
            and row['status'].get('agentStreamRunning') is False, 'UI lifecycle identity changed')
    require(controls[0]['receivedAtUnixNs'] < controls[1]['receivedAtUnixNs']
        and controls[1]['status'].get('scriptSession') == session, 'UI stop did not identify the original script')
    observations, by_frame = report.get('observations'), {}
    require(isinstance(observations, list) and 2 <= len(observations) <= 16, 'Incomplete retained UI observations')
    for row in observations:
        label = row.get('label')
        require(isinstance(label, str) and re.fullmatch(r'[A-Za-z0-9-]{1,100}', label), 'Invalid UI observation label')
        raw, image = read(folder / (label + '.json')), read(folder / (label + '.png'))
        observation = json.loads(raw)
        require(hashlib.sha256(raw).hexdigest() == row.get('jsonSha256')
            and hashlib.sha256(image).hexdigest() == row.get('imageSha256')
            and observation.get('session') == session and type(observation.get('frameId')) is int
            and type(row.get('frameId')) is int
            and observation['frameId'] == row.get('frameId') and observation['frameId'] > 0
            and number(observation.get('timestamp')), 'UI image/observation identity changed')
        native = pilot / 'observations' / session / ('frame-' + str(observation['frameId']).zfill(4))
        source = Path(row['source']).absolute()
        declared = Path(observation['screenshotPath'])
        declared = declared if declared.is_absolute() else pilot / declared
        require(source == native.with_suffix('.png') and declared.absolute() == source
            and read(source) == image and document(native.with_suffix('.json')) == observation,
            'Retained UI image is detached from its original native frame')
        from PIL import Image
        with Image.open(io.BytesIO(image)) as decoded:
            require(decoded.format == 'PNG' and decoded.size == (1920, 1080), 'UI proof is not an original full-size PNG')
            decoded.verify()
        previous = by_frame.setdefault(observation['frameId'], observation)
        require(previous == observation, 'Repeated UI frame changed')
    requests, transition = report.get('requests'), None
    require(isinstance(requests, list) and 1 <= len(requests) <= 13, 'UI transition requests missing')
    expected_step = 'worldInventory' if operation == 'pause' else 'worldInventoryClose'
    ids, last_receipt = set(), 0
    for item in requests:
        request, receipt = item['request'], item['receipt']
        identifier = request.get('id')
        require(isinstance(identifier, str) and re.fullmatch(r'[A-Za-z0-9-]{1,100}', identifier)
            and identifier not in ids and request.get('session') == receipt.get('session') == session
            and type(request.get('expectedFrameId')) is int and type(receipt.get('frameId')) is int
            and receipt.get('id') == identifier and receipt.get('status') == 'completed'
            and request.get('mission') == receipt.get('mission') and request.get('mission') in ('observe', 'questStep')
            and document(folder / (identifier + '.request.json')) == request
            and document(folder / (identifier + '.receipt.json')) == receipt, 'Native UI request/receipt changed')
        ids.add(identifier)
        before, after = by_frame.get(request.get('expectedFrameId')), by_frame.get(receipt.get('frameId'))
        require(before is not None and after is not None and number(request.get('createdAt'))
            and number(receipt.get('timestamp')) and request['createdAt'] >= last_receipt
            and 0 <= request['createdAt'] - before['timestamp'] <= 1000
            and 0 <= receipt['timestamp'] - after['timestamp'] <= 1000
            and receipt['timestamp'] >= request['createdAt'] and after['frameId'] > before['frameId'],
            'Native UI frame freshness or ordering changed')
        last_receipt = receipt['timestamp']
        details = receipt.get('details') or {}
        events = details.get('inputEvents')
        require(isinstance(events, list) and events and events[0].get('type') == 'controllerRevision'
            and set(events[0]) == {'type', 'files', 'startedAt'}, 'Missing native controller revision')
        names = CORE_REVISIONS | ({'world-inventory.js'} if request.get('step') == 'worldInventoryClose' else set())
        require(events[0]['files'] == {name: revisions[name] for name in names}
            and request['createdAt'] <= events[0]['startedAt'] <= receipt['timestamp'], 'Native controller revision differs')
        if request['mission'] == 'observe':
            require('step' not in request and len(events) == 1, 'Observation contained input')
            continue
        result = details.get('result') or {}
        require(transition is None and request.get('step') == expected_step and result.get('step') == expected_step
            and result.get('status') == 'completed' and type(result.get('frameId')) is int
            and before['frameId'] < result['frameId'] <= after['frameId'], 'UI transition was repeated or changed')
        expected_types = ['controllerRevision', 'key'] if operation == 'pause' else ['controllerRevision', 'worldInventoryClose', 'key']
        require([event.get('type') for event in events] == expected_types, 'Unexpected UI input ledger')
        key = events[-1]
        require(key.get('key') == ('VK_B' if operation == 'pause' else 'VK_ESCAPE') and key.get('durationMs') == 60
            and all(number(event.get(field)) for event in events[1:] for field in ('startedAt', 'finishedAt'))
            and all(events[0]['startedAt'] <= event['startedAt'] <= event['finishedAt'] <= receipt['timestamp'] for event in events[1:]),
            'UI transition did not retain exactly one bounded key')
        if operation == 'pause':
            require(before.get('hud', {}).get('world') is True and result.get('pausedInventory') is True, 'Native pause was not confirmed')
            input_frame_id = None
        else:
            # The native mission captures a new inventory frame after accepting
            # the host request. Its event names that exact frame, which may not
            # be one of the helper's two decimated before/after observations.
            input_frame_id = events[1].get('frameId')
            require(type(input_frame_id) is int and before['frameId'] <= input_frame_id < result['frameId']
                and key.get('frameId') == input_frame_id, 'Inventory Escape source changed')
            if input_frame_id not in by_frame:
                native = pilot / 'observations' / session / ('frame-' + str(input_frame_id).zfill(4))
                current, pixels = document(native.with_suffix('.json')), read(native.with_suffix('.png'))
                declared = Path(current.get('screenshotPath', ''))
                declared = declared if declared.is_absolute() else pilot / declared
                require(current.get('session') == session and current.get('frameId') == input_frame_id
                    and number(current.get('timestamp')) and declared.absolute() == native.with_suffix('.png'),
                    'Native inventory input frame is detached from its exact image')
                from PIL import Image
                with Image.open(io.BytesIO(pixels)) as decoded:
                    require(decoded.format == 'PNG' and decoded.size == (1920, 1080), 'Inventory input image is not full-size PNG')
                    decoded.verify()
                by_frame[input_frame_id] = current
            input_frame = by_frame[input_frame_id]
            require(inventory_visible(before) and inventory_visible(input_frame)
                and 0 <= events[1]['startedAt'] - input_frame['timestamp'] <= 1000
                and 0 <= key['startedAt'] - input_frame['timestamp'] <= 1000
                and events[1]['startedAt'] <= key['startedAt'] <= key['finishedAt'] <= events[1]['finishedAt'], 'Inventory Escape source changed')
        transition = dict(requestId=identifier, requestCreatedAtUnixMs=request['createdAt'],
            inputFinishedAtUnixMs=key['finishedAt'], receiptAtUnixMs=receipt['timestamp'],
            requestSourceFrameId=before['frameId'], inputSourceFrameId=input_frame_id)
    require((transition is not None if operation != 'verify' else transition is None and len(requests) == 1
        and requests[0]['request']['mission'] == 'observe')
        and controls[1]['receivedAtUnixNs'] >= last_receipt * 1_000_000, 'UI cleanup preceded its terminal receipt')
    terminal = by_frame[max(by_frame)]
    if operation == 'verify':
        require(report.get('inventoryVerified') is True and report.get('inputEnabled') is False
            and report.get('pilotStartAttempted') is True and report.get('pilotStartOutcome') == 'confirmed'
            and len(observations) == 2 and all(inventory_visible(value) for value in by_frame.values())
            and report.get('pauseFrameId') == terminal['frameId'] and inventory_visible(terminal),
            'Terminal passive inventory verification is not positive')
    elif operation == 'pause':
        require(report.get('pauseVerified') is True and report.get('pauseFrameId') == terminal['frameId']
            and inventory_visible(terminal), 'Terminal inventory pause is not positive')
    else:
        legacy_close_only = plan.get('closeInventoryOnly') is True and type(plan.get('maximumSelections')) is int and plan['maximumSelections'] == 0
        dedicated_close_only = (plan.get('allowedPilotOperations') == ['observe', 'worldInventoryClose']
            and type(plan.get('maximumInventoryCloseRequests')) is int and plan['maximumInventoryCloseRequests'] == 1)
        require((legacy_close_only or dedicated_close_only)
            and terminal.get('hud', {}).get('world') is True, 'Resume did not return a positively observed world')
    return dict(version=1, kind='native-inventory-observation-proof-v1' if operation == 'verify'
        else 'native-inventory-transition-proof-v1', operation=operation, owner=owner,
        scriptSession=session, terminalFrameId=terminal['frameId'], terminalTimestampUnixMs=terminal['timestamp'],
        cleanupAcknowledgedAtUnixNs=controls[1]['receivedAtUnixNs'], sourceFiles=sources, transition=transition,
        files=files, physicalInputDeliveryVerified=False)
