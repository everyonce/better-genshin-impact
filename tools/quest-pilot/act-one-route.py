"""Execute one supervised route using bounded BetterGI JSON missions; never replay a timed-out request."""
import argparse
import importlib.util
import json
import math
import os
import re
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = Path(os.environ.get('BETTERGI_PILOT_APP_DIR', REPO / 'artifacts/release-r8/BetterGI-English-win-x64'))
ROOT = APP / 'User/JsScript/ActOnePilot'
MAX_DEADLINE_MS = 90_000
MAX_SEGMENTS = 3
EXPLORATION_OBJECTIVE = 'Explore for Adventure Rank'


class RouteError(RuntimeError):
    """The on-disk route protocol is missing or ambiguous; stop rather than retry."""


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def atomic(path, value):
    pending = path.with_suffix('.pending.json')
    pending.write_text(json.dumps(value, separators=(',', ':')), encoding='utf-8')
    os.replace(pending, path)


def ensure_no_outstanding_request(root):
    request_path = root / 'request.json'
    if not request_path.exists():
        return
    try:
        previous = read(request_path)
        receipt = read(root / 'receipt.json')
    except (OSError, json.JSONDecodeError) as exc:
        raise RouteError('An existing request has no verifiable terminal receipt; refusing to overwrite it.') from exc
    if not isinstance(previous, dict) or not isinstance(receipt, dict):
        raise RouteError('Existing request/receipt state is ambiguous; refusing to overwrite it.')
    if (not isinstance(previous.get('id'), str) or not previous['id']
            or not isinstance(previous.get('session'), str) or not previous['session']
            or receipt.get('id') != previous.get('id')
            or receipt.get('session') != previous.get('session')
            or receipt.get('mission') != previous.get('mission')
            or receipt.get('status') not in ('completed', 'failed', 'rejected', 'stopped')):
        raise RouteError('An existing request is still pending or lacks its matching terminal receipt; refusing to overwrite it.')

def validate_route(value):
    if not isinstance(value, dict) or not isinstance(value.get('objective'), str) or not value['objective'].strip() or len(value['objective']) > 200:
        raise RouteError('Route must contain a non-empty objective.')
    waypoints = value.get('waypoints')
    if not isinstance(waypoints, list) or not waypoints or len(waypoints) > 10:
        raise RouteError('Route must contain waypoints.')
    for point in waypoints:
        if (not isinstance(point, dict) or point.get('map') != 'Teyvat'
                or isinstance(point.get('x'), bool) or not isinstance(point.get('x'), (int, float)) or not math.isfinite(point.get('x'))
                or isinstance(point.get('y'), bool) or not isinstance(point.get('y'), (int, float)) or not math.isfinite(point.get('y'))):
            raise RouteError('Every waypoint must have numeric x/y and map Teyvat.')
        if set(point) != {'map', 'x', 'y'}:
            raise RouteError('Waypoint fields must be exactly map, x, and y.')
    return value['objective'], waypoints


def current_observation(root, session):
    try:
        observation = read(root / 'observation.json')
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise RouteError('Current observation is unavailable or invalid.') from exc
    if (not isinstance(observation, dict) or observation.get('session') != session
            or isinstance(observation.get('frameId'), bool) or not isinstance(observation.get('frameId'), int)):
        raise RouteError('Current observation session/frame is invalid; inspect status before continuing.')
    return observation


def make_request(session, frame_id, objective, waypoints, deadline_ms):
    return {
        'session': session,
        'expectedFrameId': frame_id,
        'id': 'route-' + uuid.uuid4().hex,
        'createdAt': int(time.time() * 1000),
        'mission': 'navigation',
        'objective': objective,
        'waypoints': waypoints,
        'deadlineMs': deadline_ms,
    }


def wait_for_terminal(root, request, wait_seconds, *, monotonic=time.monotonic, sleep=time.sleep, poll_interval=0.2):
    end = monotonic() + wait_seconds
    while monotonic() < end:
        try:
            receipt = read(root / 'receipt.json')
        except (FileNotFoundError, json.JSONDecodeError):
            receipt = None
        if isinstance(receipt, dict) and receipt.get('id') == request['id']:
            if receipt.get('session') != request['session'] or receipt.get('mission') != 'navigation':
                raise RouteError('Matching receipt has the wrong session or mission; route stopped.')
            if receipt.get('status') in ('started', 'running'):
                pass
            elif receipt.get('status') not in ('completed', 'failed', 'rejected', 'stopped'):
                raise RouteError('Matching receipt has an unknown terminal status; route stopped.')
            else:
                details = receipt.get('details')
                result = details.get('result') if isinstance(details, dict) else None
                if (not isinstance(result, dict) or isinstance(receipt.get('frameId'), bool)
                        or not isinstance(receipt.get('frameId'), int)):
                    raise RouteError('Terminal receipt lacks a navigation result/frame; route stopped.')
                latest = current_observation(root, request['session'])
                if latest['frameId'] != receipt['frameId']:
                    raise RouteError('Terminal receipt is stale relative to the current observation; route stopped.')
                return receipt
        sleep(poll_interval)
    return None


def run_route(root, route, session, *, max_segments=MAX_SEGMENTS, deadline_ms=MAX_DEADLINE_MS,
              monotonic=time.monotonic, sleep=time.sleep, emit=print):
    if not isinstance(session, str) or not session:
        raise RouteError('Session is required.')
    if isinstance(max_segments, bool) or not isinstance(max_segments, int) or not 1 <= max_segments <= MAX_SEGMENTS:
        raise RouteError(f'max-segments must be from 1 to {MAX_SEGMENTS}.')
    if isinstance(deadline_ms, bool) or not isinstance(deadline_ms, int) or not 1000 <= deadline_ms <= MAX_DEADLINE_MS:
        raise RouteError(f'deadline-ms must be from 1000 to {MAX_DEADLINE_MS}.')
    objective, original_waypoints = validate_route(route)
    next_index = 0
    for segment_number in range(1, max_segments + 1):
        ensure_no_outstanding_request(root)
        observation = current_observation(root, session)
        remaining = original_waypoints[next_index:]
        if not remaining:
            emit(json.dumps({'status': 'arrived', 'nextWaypointIndex': next_index, 'segments': segment_number - 1}))
            return 'arrived'
        request = make_request(session, observation['frameId'], objective, remaining, deadline_ms)
        atomic(root / 'request.json', request)
        emit(json.dumps({'submitted': request['id'], 'session': session, 'segment': segment_number,
                         'waypointStart': next_index, 'waypointCount': len(remaining)}))
        receipt = wait_for_terminal(root, request, deadline_ms / 1000 + 15, monotonic=monotonic, sleep=sleep)
        if receipt is None:
            emit(json.dumps({'pending': request['id'], 'session': session, 'receiptPath': str(root / 'receipt.json'),
                             'instruction': 'Wait for this receipt and inspect the current observation. Do not replay this segment.'}))
            return 'pending'
        result = receipt['details']['result']
        if receipt['status'] == 'completed' and result.get('status') == 'arrived':
            if result.get('nextWaypointIndex') != len(remaining):
                emit(json.dumps({'stopped': request['id'], 'reason': 'arrival waypoint checkpoint is inconsistent'}))
                return 'stopped'
            emit(json.dumps({'status': 'arrived', 'receipt': receipt['id'], 'nextWaypointIndex': len(original_waypoints)}))
            return 'arrived'
        if (receipt['status'] == 'failed' and result.get('status') == 'stopped'
                and result.get('reason') == 'Navigation deadline reached'):
            checkpoint = result.get('nextWaypointIndex')
            if (isinstance(checkpoint, bool) or not isinstance(checkpoint, int)
                    or checkpoint < 0 or checkpoint >= len(remaining)):
                emit(json.dumps({'stopped': request['id'], 'reason': 'deadline checkpoint is invalid'}))
                return 'stopped'
            next_index += checkpoint
            emit(json.dumps({'resumeAtWaypoint': next_index, 'receipt': receipt['id']}))
            continue
        emit(json.dumps({'stopped': request['id'], 'stopReason': result.get('reason'),
                         'reason': 'Only a terminal navigation deadline may resume; inspect this result.'}))
        return 'stopped'
    emit(json.dumps({'stopped': True, 'reason': 'maximum route segments reached', 'nextWaypointIndex': next_index,
                     'instruction': 'Inspect the latest receipt and observation before approving another route segment.'}))
    return 'stopped'


class GuardedPilot:
    """Dispatch serial missions through the existing authenticated pilot protocol.

    This client never starts a pilot, logs into the game, loads a model, or takes
    over an unresolved request. A pending request leaves the exclusive lock held.
    """

    def __init__(self, app, session, process_id, windows_session_id, stop_paths=()):
        """Pin the already-running native lifetime before acquiring a local lease."""
        script = Path(__file__).with_name('act-one-command.py')
        spec = importlib.util.spec_from_file_location('_route_guarded_command', script)
        self.command = importlib.util.module_from_spec(spec)
        self.command._VERIFIED_APP_DIRECTORY = str(app)
        exec(compile(script.read_bytes(), str(script), 'exec'), self.command.__dict__)
        self.root = Path(app).resolve() / 'User/JsScript/ActOnePilot'
        self.session, self.pid, self.wts = session, process_id, windows_session_id
        self.stop_paths = tuple(Path(p) for p in stop_paths)
        self.pending = None
        self.nonce = None
        self.cancelled = False
        self.owner_status = self._owner()
        self.lock = self.root / '.route-controller.lock'
        self.lock_bytes = json.dumps(dict(session=session, processId=process_id,
            windowsSessionId=windows_session_id, controllerId=uuid.uuid4().hex)).encode()
        with self.lock.open('xb') as stream:
            stream.write(self.lock_bytes)

    def _owner(self, frame=None, *, idle=False):
        """Always use the PID/session/SID-verified native pipe, including elevated children."""
        status = self.command.query_verified_service_status(self.pid, self.wts)
        now = int(time.time() * 1000)
        stamp = status.get('heartbeatAtUnixMs') if isinstance(status, dict) else None
        if (not isinstance(status, dict) or status.get('processId') != self.pid
                or status.get('windowsSessionId') != self.wts
                or status.get('instanceType') != 'ChildSession' or status.get('remoteDesktop') is not True
                or status.get('scriptSession') != self.session or status.get('serviceOwnsPilot') is not True
                or status.get('heartbeatFresh') is not True or type(stamp) is not int
                or not 0 <= now - stamp <= 5000
                or Path(status.get('appDirectory', '')).resolve() != self.root.parents[2]):
            raise RouteError('Authenticated pilot owner changed or is unavailable.')
        nonce = status.get('instanceNonce')
        if not isinstance(nonce, str) or re.fullmatch('[a-f0-9]{32}', nonce) is None:
            raise RouteError('Native pilot lifetime nonce is unavailable.')
        if self.nonce is not None and nonce != self.nonce:
            raise RouteError('Native pilot lifetime changed.')
        self.nonce = nonce
        if idle and (status.get('scriptState') != 'idle' or status.get('pilotState') != 'idle'
                or status.get('activeRequestId') not in (None, '') or status.get('frameId') != frame):
            raise RouteError('The exact pilot is not idle at the selected frame.')
        return status

    def stopped(self):
        """Observe caller STOP files and the existing session-specific pilot cancel."""
        if any(path.exists() for path in self.stop_paths):
            return True
        path = self.root / 'stop.json'
        return path.exists() and read(path).get('session') == self.session

    def current(self):
        """Read the latest source and join its immutable session/frame document."""
        value = current_observation(self.root, self.session)
        immutable = read(self.command.observation_path(self.root, self.session, value['frameId']))
        if value != immutable:
            raise RouteError('Latest source differs from its immutable frame.')
        return value

    def _admit(self, source, *, passive=False):
        """Recheck owner, source, existing request and STOP immediately before publication."""
        if self.stopped():
            raise RouteError('Operator STOP prevents a new mission.')
        if self.current() != source:
            raise RouteError('Source changed before mission publication.')
        heartbeat = self.command.require_live_controller(self.root, self.session, source['frameId'], self.wts)
        if heartbeat['processId'] != self.pid:
            raise RouteError('Pilot heartbeat belongs to another process.')
        self._owner(source['frameId'], idle=True)
        if not passive:
            require_fresh_source(source, self.session, int(time.time() * 1000))

    def _cancel_owned(self):
        """Cancel only this exact published request; an unknown/foreign request is never stopped."""
        if self.cancelled or self.pending is None:
            return
        self._owner()
        if read(self.root / 'request.json') != self.pending:
            raise RouteError('Cannot cancel a substituted or foreign request.')
        heartbeat = self.command.require_live_controller(self.root, self.session, None, self.wts,
            allow_active=True, allow_faulted=True)
        if heartbeat['processId'] != self.pid:
            raise RouteError('Cannot cancel another pilot process.')
        self.command.atomic(self.root / 'stop.json', dict(session=self.session, createdAt=int(time.time() * 1000)))
        self.cancelled = True

    def inventory_ready(self, source):
        """Reuse the installed, input-free inventory predicate before native navigation."""
        check = self.command.subprocess.run(['node', '-e',
            "const g=require(process.argv[1]),o=JSON.parse(process.argv[2]);process.exit(g.worldInventoryClosePermission(o,Number(process.argv[3]),process.argv[4])?0:2);",
            str(self.root / 'world-inventory.js'), json.dumps(source), str(int(time.time() * 1000)), self.session],
            capture_output=True, text=True, encoding='utf-8', timeout=5)
        return check.returncode == 0

    def validate_route(self, route, deadline_ms):
        """Keep the existing command's finite route admission before any pause or request."""
        self.command.validate_navigation_plan(route, min(45000, deadline_ms))

    def _prepare_exploration(self, request):
        """Use the existing native safety inspector and exact request-bound sidecar."""
        witness = None
        for frame in range(request['expectedFrameId'] - 1, max(0, request['expectedFrameId'] - 150), -1):
            path = self.command.observation_path(self.root, self.session, frame)
            if path.exists():
                value = read(path)
                if value.get('hud', {}).get('world') and value.get('map'):
                    witness = value
                    break
        if witness is None:
            raise RouteError('Recent grounded exploration witness is unavailable.')
        safety = dict(reviewed=True, requestId=request['id'], session=self.session,
            frameId=request['expectedFrameId'], createdAt=request['createdAt'],
            witnessFrameId=witness['frameId'],
            route=dict(objective=request['objective'], waypoints=request['waypoints']))
        check = self.command.subprocess.run(['node', '-e',
            "const g=require(process.argv[1]),p=JSON.parse(process.argv[2]),w=JSON.parse(process.argv[3]);const reason=g.inspect(w,p.route,p.createdAt,p.session);if(reason){console.error(reason);process.exit(2);}",
            str(self.root / 'navigation-safety.js'), json.dumps(safety), json.dumps(witness)],
            capture_output=True, text=True, encoding='utf-8', timeout=5)
        if check.returncode:
            raise RouteError(check.stderr.strip() or 'Native exploration safety preflight refused.')
        self.command.atomic(self.root / 'navigation-safety-request.json', safety)

    def deadline_resume(self, route, start, receipt, request):
        """Validate an inventory-paused checkpoint with the existing command helper."""
        progress = dict(session=self.session, requestId=request['id'], startIndex=start,
                        routeHash=self.command.navigation_route_hash(route))
        return self.command.resume_navigation_route(route, progress, receipt, request, self.session)

    def execute(self, mission, source, fields, deadline, save_pending):
        """Publish once, retain the original ID, and wait for its exact terminal receipt."""
        if self.pending is not None:
            raise RouteError('A prior request is unresolved; it cannot be replayed.')
        if mission not in ('observe', 'navigation', 'combat', 'dialogue', 'keyPress', 'questStep'):
            raise RouteError('Unsupported route-controller mission.')
        expected_fields = {'observe': set(), 'dialogue': set(), 'keyPress': {'key'},
                           'combat': {'objective', 'deadlineMs'},
                           'navigation': {'objective', 'waypoints', 'deadlineMs'}, 'questStep': {'step'}}
        if mission == 'navigation' and fields.get('objective') == EXPLORATION_OBJECTIVE:
            expected_fields['navigation'].add('requireMeasuredGround')
            if fields.get('requireMeasuredGround', True) is not True:
                raise RouteError('Exploration requires a measured ground scan.')
            fields = dict(fields, requireMeasuredGround=True)
        if set(fields) != expected_fields[mission]:
            raise RouteError('Unexpected route-controller mission fields.')
        if mission == 'keyPress' and fields != {'key': 'VK_ESCAPE'}:
            raise RouteError('Only the fixed Journal-close operation is available.')
        if mission == 'questStep' and fields != {'step': 'worldInventory'}:
            raise RouteError('Only the existing exploration inventory-pause operation is available.')
        if mission == 'navigation':
            self.command.validate_navigation_plan(fields, fields['deadlineMs'])
        self._admit(source, passive=mission == 'observe')
        heartbeat = read(self.root / 'controller-status.json')
        maintenance = self.command.maintain_receipts_for_controller(self.root, heartbeat)
        if maintenance.get('status') == 'archived' and mission != 'observe':
            raise RouteError('Receipt maintenance requires a new passive observation.')
        # The request slot must already have a matching terminal receipt. Never
        # overwrite a prepared/unacknowledged command from any caller.
        request_path = self.root / 'request.json'
        previous = request_path.read_bytes() if request_path.exists() else None
        if previous is not None:
            prior = json.loads(previous.decode('utf-8-sig'))
            prior_receipt = read(self.command.request_receipt_path(self.root, prior.get('session'), prior.get('id')))
            prior_source = read(self.command.observation_path(self.root, prior['session'], prior_receipt.get('frameId')))
            self.command.validate_terminal_receipt(prior, prior_receipt, prior_source)
        request = dict(id='mission-' + uuid.uuid4().hex, session=self.session,
            expectedFrameId=source['frameId'], createdAt=int(time.time() * 1000), mission=mission, **fields)
        if mission == 'navigation' and fields['objective'] == EXPLORATION_OBJECTIVE:
            if not self.inventory_ready(source):
                raise RouteError('Exploration requires the existing native inventory entry.')
            self._prepare_exploration(request)

        def before_replace():
            """Keep the selected source and prior slot exact through atomic publication."""
            if time.monotonic() >= deadline:
                raise RouteError('Original controller deadline expired before publication.')
            current = request_path.read_bytes() if request_path.exists() else None
            if current != previous:
                raise RouteError('Another request appeared before publication.')
            self._admit(source, passive=mission == 'observe')
            if time.monotonic() >= deadline:
                raise RouteError('Original controller deadline expired during admission.')

        save_pending(request)
        # Retain uncertainty even if a filesystem error follows the actual rename.
        self.pending = request
        self.command.atomic(request_path, request, before_replace=before_replace)
        while time.monotonic() < deadline:
            if self.stopped():
                self._cancel_owned()
            path = self.command.request_receipt_path(self.root, self.session, request['id'])
            try:
                receipt = read(path)
            except (FileNotFoundError, json.JSONDecodeError):
                receipt = None
            if receipt is not None:
                if (not isinstance(receipt, dict) or receipt.get('id') != request['id']
                        or receipt.get('session') != self.session or receipt.get('mission') != mission):
                    raise RouteError('Request-specific receipt identity differs.')
                if receipt.get('status') not in ('started', 'running'):
                    observed = read(self.command.observation_path(self.root, self.session, receipt.get('frameId')))
                    frame = self.command.validate_terminal_receipt(request, receipt, observed)
                    settled = self.command.wait_for_controller_quiescence(self.root, self.session, self.pid,
                        self.wts, frame, timeout_seconds=max(0, min(5, deadline - time.monotonic())))
                    if not settled['controllerQuiescent']:
                        raise RouteError('Terminal request has no settled controller proof.')
                    self._owner()
                    if read(request_path) != request:
                        raise RouteError('Published request changed before retirement.')
                    self.command.validate_latest_observation(self.current(), self.session, frame)
                    self.pending = None
                    return dict(request=request, receipt=receipt, observation=observed, cancelled=self.cancelled)
            time.sleep(min(.1, max(0, deadline - time.monotonic())))
        self._cancel_owned()
        raise RouteError('Original deadline expired; terminal outcome is unresolved, do not replay.')

    def close(self):
        """Release only our known-retired lease; unresolved ownership stays visibly reserved."""
        if self.pending is None and self.lock.read_bytes() == self.lock_bytes:
            self.lock.unlink()


def require_fresh_source(source, session, now_ms):
    """Use the normal pilot's original 1000 ms publication clock, never a refreshed timestamp."""
    stamp = source.get('timestamp')
    if (source.get('session') != session or type(source.get('frameId')) is not int or source['frameId'] < 1
            or type(stamp) not in (int, float) or not math.isfinite(stamp) or not 0 <= now_ms - stamp <= 1000
            or not isinstance(source.get('hud'), dict) or not isinstance(source.get('ocr'), list)):
        raise RouteError('Fresh same-session native source is required.')


def source_account_matches(source, expected_uid):
    """Reject conflicting or duplicate numeric account evidence in the native UID region."""
    matches = []
    for row in source['ocr']:
        if not isinstance(row, dict) or not isinstance(row.get('text'), str):
            return False
        if (type(row.get('x')) in (int, float) and row['x'] > 1600
                and type(row.get('y')) in (int, float) and row['y'] > 1020):
            match = re.fullmatch(r'(?:UID)?[: ]*([0-9]{9,10})', row['text'].strip())
            if match:
                matches.append(match.group(1))
    return matches == [expected_uid]


def ground_scan_is_clear(source, now_ms):
    """Accept a measured empty scan only from this capture and within its input freshness window."""
    hud = source['hud']
    scan = hud.get('enemyBarObservation')
    stamp = hud.get('captureStamp')
    if not isinstance(scan, dict) or not isinstance(stamp, dict):
        return False
    captured_at = stamp.get('capturedAt')
    return (stamp.get('source') == 'game-capture-start' and type(captured_at) is int
            and captured_at <= source['timestamp'] <= now_ms and now_ms - captured_at <= 1000
            and stamp.get('session') == scan.get('session') == source['session']
            and type(stamp.get('frameId')) is int and type(scan.get('frameId')) is int
            and stamp['frameId'] == scan['frameId'] == source['frameId']
            and type(scan.get('capturedAt')) is int and scan['capturedAt'] == captured_at
            and type(scan.get('version')) is int and scan['version'] == 1
            and scan.get('kind') == 'normal-ground-enemy-observation-v1' and scan.get('state') == 'clear'
            and type(scan.get('candidateCount')) is int and scan['candidateCount'] == 0
            and type(scan.get('acceptedCount')) is int and scan['acceptedCount'] == 0
            and hud.get('enemyBars') == [])


def route_phase(source, expected_uid, objectives, *, allow_dialogue, journal_resume, now_ms=None):
    """Select a named existing operation; raw input proposals and unknown objectives are never accepted."""
    hud, rows = source['hud'], source['ocr']
    if any(not isinstance(row, dict) or not isinstance(row.get('text'), str) for row in rows):
        return 'wait', 'OCR evidence is malformed'
    if not source_account_matches(source, expected_uid) or any(hud.get(k) for k in ('loading', 'unknownHud', 'bigMap', 'climbing')):
        return 'wait', 'Account or scene is not positively recognized'
    if hud.get('journal') is True:
        known = any(row.get('text', '').strip() == 'Going Upon the Breeze' for row in rows)
        if journal_resume and known and not any(hud.get(k) for k in ('world', 'auto', 'dialogueReady', 'choice')):
            return 'closeJournal', None
        return 'wait', 'Journal has no completed-combat continuation authority'
    if hud.get('dialogueReady') is True or hud.get('choice') is True:
        if (allow_dialogue and hud.get('auto') is True and hud.get('world') is False
                and source.get('map') is None and hud.get('health') is None):
            return 'dialogue', None
        return 'wait', 'Dialogue is ambiguous or was not explicitly enabled'
    hp, position, bars = hud.get('health'), source.get('map'), hud.get('enemyBars')
    if (hud.get('world') is not True or hud.get('groundControls') is not True or hud.get('auto')
            or hud.get('lowHealth') or hud.get('tutorialStep') or not isinstance(hp, dict)
            or type(hp.get('current')) is not int or type(hp.get('max')) is not int
            or not 0 < hp['current'] <= hp['max'] or hp['current'] < hp['max'] * .6
            or not isinstance(position, dict) or position.get('map') != 'Teyvat'
            or any(type(position.get(k)) not in (int, float) or not math.isfinite(position[k]) for k in ('x', 'y'))
            or not isinstance(bars, list)):
        return 'wait', 'Safe ground, position and numeric health are not established'
    visible_objectives = hud.get('objectives')
    if not isinstance(visible_objectives, list) or any(not isinstance(x, str) for x in visible_objectives):
        return 'wait', 'Objective evidence is malformed'
    if objectives == [EXPLORATION_OBJECTIVE]:
        if bars or any(re.fullmatch(r'Defeatallopponents[0-9]+/[0-9]+', re.sub(r'\s', '', x)) for x in visible_objectives):
            return 'wait', 'Exploration requires zero visible threat'
        if hp['current'] < hp['max'] * .85:
            return 'wait', 'Existing generic exploration requires at least 85% health'
        if not ground_scan_is_clear(source, int(time.time() * 1000) if now_ms is None else now_ms):
            return 'wait', 'Exploration requires a fresh enemy scan showing clear ground'
        return 'navigation', EXPLORATION_OBJECTIVE
    matches = [name for name in objectives if name in visible_objectives]
    if len(matches) != 1:
        return 'wait', 'Current objective is missing, ambiguous or outside the approved continuation'
    objective = matches[0]
    if bars:
        if objective in ('Defeat the nearby hilichurls', 'Clear out the nearby hilichurl camp'):
            return 'combat', objective
        return 'wait', 'Enemy encounter has no supported combat objective'
    return 'navigation', objective


def run_controller(pilot, route, progress_path, expected_uid, *, allow_dialogue=False,
                   continuation_objectives=(), max_segments=MAX_SEGMENTS, deadline_ms=MAX_DEADLINE_MS,
                   monotonic=time.monotonic, clock_ms=lambda: int(time.time() * 1000), emit=print):
    """Continue only settled missions; retain exact route progress through combat and dialogue.

    The one original outer deadline and finite mission counts survive all phase
    changes. A failed or unknown command is recorded and never retried.
    """
    objective, points = validate_route(route)
    pilot.validate_route(route, deadline_ms)
    if (type(deadline_ms) is not int or not 1000 <= deadline_ms <= MAX_DEADLINE_MS
            or type(max_segments) is not int or not 1 <= max_segments <= MAX_SEGMENTS
            or not isinstance(expected_uid, str) or re.fullmatch(r'[0-9]{9,10}', expected_uid) is None
            or len(continuation_objectives) > 4
            or any(not isinstance(x, str) or not 0 < len(x.strip()) <= 200 for x in continuation_objectives)
            or len(set((objective, *continuation_objectives))) != 1 + len(continuation_objectives)):
        raise RouteError('Invalid finite controller limits, account or continuation objectives.')
    # Keep one durable progress document, not a generated driver or authority chain.
    state = dict(version=1, kind='supervised-route-controller-v1', status='running', session=pilot.session,
        route=dict(objective=objective, waypoints=points), expectedUid=expected_uid,
        nextWaypointIndex=0, navigationRequests=0, handoffs=0, pending=None, records=[],
        originalDeadlineMs=deadline_ms, startedAt=int(clock_ms()))
    progress_path = Path(progress_path)
    with progress_path.open('x', encoding='utf-8') as stream:
        json.dump(state, stream)
    deadline = monotonic() + deadline_ms / 1000
    authorized_objectives = [objective]
    journal_resume, last_phase, inventory_navigation = False, None, None

    def save():
        """Persist progress and pending identity before and after each one-shot request."""
        atomic(progress_path, state)

    def pending(request):
        """A published or uncertain request prevents any later mission from replacing it."""
        state['pending'] = request
        save()

    def dispatch(mission, source, fields, *, allow_deadline_checkpoint=False):
        """Keep the original request/receipt result, including a failed native handoff."""
        outcome = pilot.execute(mission, source, fields, deadline, pending)
        request, receipt, observed = outcome['request'], outcome['receipt'], outcome['observation']
        if (request.get('session') != pilot.session or request.get('mission') != mission
                or request.get('expectedFrameId') != source['frameId']
                or any(request.get(k) != v for k, v in fields.items())
                or receipt.get('id') != request.get('id') or receipt.get('session') != pilot.session
                or receipt.get('mission') != mission or observed.get('session') != pilot.session
                or type(receipt.get('frameId')) is not int or receipt['frameId'] <= source['frameId']
                or observed.get('frameId') != receipt['frameId']):
            raise RouteError('Mission result does not join the original request and capture.')
        state['pending'] = None
        state['records'].append(dict(request=request, receipt=receipt, observation=observed))
        result = receipt.get('details', {}).get('result')
        if mission == 'navigation' and receipt.get('status') != 'completed' and isinstance(result, dict):
            # A failed mission is never resumed automatically. Its native cursor
            # still records waypoints completed before the failure for inspection.
            navigation = result.get('navigation') if result.get('localHandoff') is True else result
            cursor = navigation.get('nextWaypointIndex') if isinstance(navigation, dict) else None
            if (isinstance(navigation, dict) and navigation.get('status') == 'stopped'
                    and type(cursor) is int and 0 <= cursor < len(fields['waypoints'])):
                state['nextWaypointIndex'] += cursor
                state['checkpointFromFailedRequest'] = request['id']
        save()
        deadline_checkpoint = (allow_deadline_checkpoint and not outcome.get('cancelled')
            and receipt.get('status') in ('failed', 'stopped') and isinstance(result, dict)
            and result.get('status') == 'stopped' and result.get('localHandoff') is not True
            and str(result.get('reason', '')).startswith('Navigation deadline reached')
            and type(result.get('nextWaypointIndex')) is int
            and 0 < result['nextWaypointIndex'] < len(fields['waypoints']))
        if (outcome.get('cancelled') or receipt.get('status') != 'completed') and not deadline_checkpoint:
            raise RouteError('Mission did not complete; original result retained without retry.')
        return result

    try:
        while monotonic() < deadline:
            if pilot.stopped():
                raise RouteError('Operator STOP prevents further route input.')
            source = pilot.current()
            dispatch('observe', source, {})
            source = pilot.current()
            now_ms = clock_ms()
            require_fresh_source(source, pilot.session, now_ms)
            phase, value = route_phase(source, expected_uid, authorized_objectives,
                allow_dialogue=allow_dialogue, journal_resume=journal_resume, now_ms=now_ms)
            paused_navigation = inventory_navigation is not None
            if paused_navigation:
                if not source_account_matches(source, expected_uid) or not pilot.inventory_ready(source):
                    raise RouteError('Owned exploration pause is not verified in the fresh source.')
                phase, value = 'navigation', inventory_navigation
            if phase == 'wait':
                state.update(status='waiting', reason=value)
                break
            if phase in ('combat', 'dialogue') and phase == last_phase:
                state.update(status='waiting', reason='Completed phase has not cleared in fresh evidence')
                break
            if phase in ('combat', 'dialogue') and state['handoffs'] >= max_segments * 2:
                raise RouteError('Maximum encounter/dialogue handoffs reached.')
            remaining = int((deadline - monotonic()) * 1000)
            if phase == 'closeJournal':
                # Existing native combat protects with J. This exact guarded
                # Escape is a semantic continuation, never a user-supplied key.
                if remaining < 3000:
                    raise RouteError('Insufficient original deadline for Journal continuation.')
                dispatch('keyPress', source, dict(key='VK_ESCAPE'))
                journal_resume = False
                continue
            if phase == 'dialogue':
                # The existing dialogue mission has a fixed 60-second ceiling.
                if remaining < 65000:
                    raise RouteError('Insufficient original deadline for the existing dialogue mission.')
                result = dispatch('dialogue', source, {})
                if not isinstance(result, dict) or result.get('status') != 'completed':
                    raise RouteError('Dialogue completion is not established.')
                state['handoffs'] += 1
                authorized_objectives = [objective, *continuation_objectives]
                last_phase = 'dialogue'
                continue
            if phase == 'combat':
                if remaining < 6000:
                    raise RouteError('Insufficient original deadline for bounded combat.')
                result = dispatch('combat', source, dict(objective=value, deadlineMs=min(20000, remaining - 5000)))
                if not isinstance(result, dict) or result.get('status') != 'completed' or result.get('outcome') != 'objective_completed':
                    raise RouteError('Native combat objective completion is not established.')
                state['handoffs'] += 1
                authorized_objectives = [objective, *continuation_objectives]
                journal_resume, last_phase = True, 'combat'
                continue
            if state['nextWaypointIndex'] == len(points):
                state.update(status='arrived', reason='All native waypoint checkpoints are complete')
                break
            if state['navigationRequests'] >= max_segments:
                raise RouteError('Maximum route segments reached; retained progress requires inspection.')
            # A combat navigation request can add the existing native 20s local
            # handoff. Reserve it in the original outer clock before dispatch.
            reserve = 25000 if value in ('Defeat the nearby hilichurls', 'Clear out the nearby hilichurl camp') else 5000
            if reserve == 25000 and state['handoffs'] >= max_segments * 2:
                raise RouteError('No further native combat handoff is authorized.')
            if remaining < reserve + 1000:
                raise RouteError('Insufficient original deadline for navigation and its native handoff.')
            if value == EXPLORATION_OBJECTIVE and not paused_navigation:
                if remaining < 20000:
                    raise RouteError('Insufficient original deadline for exploration pause and navigation.')
                result = dispatch('questStep', source, dict(step='worldInventory'))
                if not isinstance(result, dict) or result.get('pausedInventory') is not True:
                    raise RouteError('Exploration inventory pause did not complete.')
                inventory_navigation = value
                continue
            inventory_navigation = None
            start = state['nextWaypointIndex']
            suffix = points[state['nextWaypointIndex']:]
            fields = dict(objective=value, waypoints=suffix, deadlineMs=min(45000, remaining - reserve))
            if value == EXPLORATION_OBJECTIVE:
                fields['requireMeasuredGround'] = True
            state['navigationRequests'] += 1
            result = dispatch('navigation', source, fields, allow_deadline_checkpoint=True)
            terminal = state['records'][-1]
            if terminal['receipt']['status'] != 'completed':
                if value == EXPLORATION_OBJECTIVE:
                    pilot.deadline_resume(dict(objective=value, waypoints=points), start,
                        terminal['receipt'], terminal['request'])
                    inventory_navigation = value
                last_phase = 'navigation'
                emit(json.dumps(dict(status='deadlineCheckpoint', nextWaypointIndex=state['nextWaypointIndex'],
                    requestId=terminal['request']['id'])))
                continue
            handoff = isinstance(result, dict) and result.get('localHandoff') is True
            navigation = result.get('navigation') if handoff else result
            cursor = navigation.get('nextWaypointIndex') if isinstance(navigation, dict) else None
            if type(cursor) is not int or not 0 <= cursor <= len(suffix):
                raise RouteError('Native navigation checkpoint is missing or inconsistent.')
            if handoff:
                if (result.get('status') != 'completed' or result.get('outcome') != 'objective_completed'
                        or navigation.get('status') != 'stopped' or navigation.get('reason') != 'Enemy acquired'
                        or cursor >= len(suffix)):
                    raise RouteError('Native local combat handoff is not a completed encounter.')
                state['handoffs'] += 1
                authorized_objectives = [objective, *continuation_objectives]
                journal_resume, last_phase = True, 'combat'
            elif navigation.get('status') != 'arrived' or cursor != len(suffix):
                raise RouteError('Navigation did not establish an arrival or supported handoff.')
            else:
                last_phase = 'navigation'
            state['nextWaypointIndex'] += cursor
            emit(json.dumps(dict(status='checkpoint', nextWaypointIndex=state['nextWaypointIndex'],
                nativeCombatHandoff=handoff, requestId=state['records'][-1]['request']['id'])))
            save()
            if not handoff:
                state.update(status='arrived', reason='All native waypoint checkpoints are complete')
                break
        else:
            raise RouteError('Original controller deadline reached.')
    except (OSError, ValueError, RuntimeError) as error:
        state.update(status='pending' if state['pending'] is not None else 'stopped', reason=str(error))
    finally:
        state['finishedAt'] = int(clock_ms())
        save()
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('route', type=Path, help='JSON file containing objective and ordered waypoints')
    parser.add_argument('--session', required=True)
    parser.add_argument('--deadline-ms', type=int, default=MAX_DEADLINE_MS)
    parser.add_argument('--max-segments', type=int, default=MAX_SEGMENTS)
    parser.add_argument('--root', type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument('--controller', action='store_true', help='Replan settled navigation/combat/dialogue phases from fresh evidence')
    parser.add_argument('--app-dir', type=Path, help='Exact already-running BetterGI application; controller mode never starts it')
    parser.add_argument('--process-id', type=int)
    parser.add_argument('--expected-windows-session-id', type=int)
    parser.add_argument('--expected-uid', help='Exact 9- or 10-digit game UID to retain across phases')
    parser.add_argument('--progress', type=Path, help='New progress JSON; an existing or pending run is never replayed')
    parser.add_argument('--allow-dialogue', action='store_true', help='Permit the existing bounded recognized-dialogue mission')
    parser.add_argument('--continue-objective', action='append', default=[], help='Explicit objective allowed after a completed encounter/dialogue')
    parser.add_argument('--stop-file', action='append', type=Path, default=[], help='Additional caller STOP file')
    args = parser.parse_args()
    try:
        if args.controller:
            if (args.app_dir is None or args.progress is None or args.progress.exists()
                    or type(args.process_id) is not int or args.process_id <= 0
                    or type(args.expected_windows_session_id) is not int or args.expected_windows_session_id <= 1
                    or args.expected_uid is None):
                raise RouteError('Controller mode requires explicit app/PID/RDP session/account and a new progress path.')
            if args.progress.resolve().is_relative_to((args.app_dir / 'User/JsScript/ActOnePilot').resolve()):
                raise RouteError('Progress must be outside the native pilot protocol directory.')
            stops = [args.progress.parent / 'STOP', args.progress.with_suffix('.STOP'),
                     args.app_dir / 'User/JsScript/ActOnePilot/STOP', *args.stop_file]
            pilot = GuardedPilot(args.app_dir, args.session, args.process_id, args.expected_windows_session_id, stops)
            try:
                report = run_controller(pilot, read(args.route), args.progress, args.expected_uid,
                    allow_dialogue=args.allow_dialogue, continuation_objectives=args.continue_objective,
                    max_segments=args.max_segments, deadline_ms=args.deadline_ms)
            finally:
                pilot.close()
            print(json.dumps(dict(status=report['status'], nextWaypointIndex=report['nextWaypointIndex'],
                progress=str(args.progress), reason=report.get('reason'))))
            if report['status'] != 'arrived':
                raise SystemExit(2)
            return
        outcome = run_route(args.root, read(args.route), args.session,
                            max_segments=args.max_segments, deadline_ms=args.deadline_ms)
    except (OSError, json.JSONDecodeError, RouteError) as exc:
        raise SystemExit(str(exc)) from exc
    if outcome != 'arrived':
        raise SystemExit(2)


if __name__ == '__main__':
    main()


