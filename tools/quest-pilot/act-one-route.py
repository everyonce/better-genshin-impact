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
# Leave capture time before another stationary observation; retirement alone cannot grant input.
STATIONARY_OBSERVATION_RESERVE_SECONDS = 1.0
PASSIVE_TERMINAL_SETTLEMENT_SECONDS = 1.0


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
    if 'startNear' in value:
        start = value['startNear']
        if (not isinstance(start, dict) or set(start) != {'map', 'x', 'y', 'radius'}
                or start.get('map') != 'Teyvat'
                or any(type(start.get(k)) not in (int, float) or not math.isfinite(start[k])
                       for k in ('x', 'y', 'radius')) or start['radius'] <= 0):
            raise RouteError('startNear requires exactly map Teyvat, finite x/y and a positive finite radius.')
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
    if 'startNear' in route:
        raise RouteError('startNear requires controller mode and a fresh account-bound world measurement.')
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

    def inventory_ready(self, source, *, at_ms=None):
        """Reuse the installed, input-free inventory predicate before native navigation."""
        check = self.command.subprocess.run(['node', '-e',
            "const g=require(process.argv[1]),o=JSON.parse(process.argv[2]);process.exit(g.worldInventoryClosePermission(o,Number(process.argv[3]),process.argv[4])?0:2);",
            str(self.root / 'world-inventory.js'), json.dumps(source),
            str(int(time.time() * 1000) if at_ms is None else at_ms), self.session],
            capture_output=True, text=True, encoding='utf-8', timeout=5)
        return check.returncode == 0

    def exploration_continuation(self, progress_path, expected_uid, now_ms):
        """Join one completed route to its still-current slot and original pause evidence.

        The old field is historical evidence evaluated at its actual B event,
        not a fresh observation. Native navigation still measures after opening.
        Missing or inconsistent evidence merely selects the ordinary bootstrap.
        """
        try:
            retained = []

            def saved(path):
                """Retain exact bytes through the one passive observation."""
                raw = path.read_bytes()
                retained.append((path, raw))
                return json.loads(raw.decode('utf-8-sig'))

            progress = saved(Path(progress_path))
            route = progress['route']
            objective, points = validate_route(route)
            if (progress.get('kind') != 'supervised-route-controller-v1' or progress.get('version') != 1
                    or progress.get('status') != 'arrived' or progress.get('pending') is not None
                    or progress.get('session') != self.session or progress.get('expectedUid') != expected_uid
                    or objective != EXPLORATION_OBJECTIVE or type(progress.get('nextWaypointIndex')) is not int
                    or progress['nextWaypointIndex'] != len(points)):
                return None
            record = progress['records'][-1]
            request, receipt, terminal = record['request'], record['receipt'], record['observation']
            slot = (self.root / 'request.json').read_bytes()
            if json.loads(slot.decode('utf-8-sig')) != request:
                return None
            if (request.get('session') != self.session or request.get('mission') != 'navigation'
                    or request.get('objective') != objective or request.get('requireMeasuredGround') is not True
                    or not isinstance(request.get('waypoints'), list) or not request['waypoints']
                    or request['waypoints'] != points[-len(request['waypoints']):]
                    or receipt.get('status') != 'completed'):
                return None
            if saved(self.command.request_receipt_path(self.root, self.session, request['id'])) != receipt:
                return None
            if saved(self.command.observation_path(self.root, self.session, receipt['frameId'])) != terminal:
                return None
            self.command.validate_terminal_receipt(request, receipt, terminal)
            result = receipt['details']['result']
            proof = result['pauseProof']
            if (result.get('status') != 'arrived' or result.get('localHandoff') is True
                    or type(result.get('nextWaypointIndex')) is not int
                    or result['nextWaypointIndex'] != len(request['waypoints'])
                    or result.get('pauseVerified') is not True or proof.get('verified') is not True
                    or proof.get('kind') != 'inventory' or proof.get('session') != self.session
                    or any(type(proof.get(k)) is not int for k in ('sourceFrameId', 'pauseFrameId', 'timestamp'))
                    or not request['expectedFrameId'] < proof['sourceFrameId'] < proof['pauseFrameId'] <= terminal['frameId']):
                return None
            field = saved(self.command.observation_path(self.root, self.session, proof['sourceFrameId']))
            paused = saved(self.command.observation_path(self.root, self.session, proof['pauseFrameId']))
            if (field.get('frameId') != proof['sourceFrameId'] or paused.get('frameId') != proof['pauseFrameId']
                    or field.get('session') != self.session or paused.get('session') != self.session):
                return None
            events = receipt['details']['inputEvents']
            keys = [e for e in events if e.get('type') == 'pauseProtectionKey']
            if len(keys) != 1:
                return None
            key = keys[0]
            input_keys = [e for e in events if e.get('type') in ('key', 'rotate', 'click', 'mouse')]
            if (not input_keys or input_keys[-1].get('type') != 'key'
                    or input_keys[-1].get('key') != 'VK_B' or input_keys[-1].get('durationMs') != 60
                    or input_keys[-1].get('frameId') != field['frameId']
                    or input_keys[-1].get('finishedAt') != key.get('finishedAt')
                    or type(input_keys[-1].get('startedAt')) is not int
                    or not key['startedAt'] <= input_keys[-1]['startedAt'] <= key['finishedAt']
                    or not any(e.get('type') == 'pauseProtectionVerified' and e.get('kind') == 'inventory'
                               and e.get('frameId') == proof['pauseFrameId'] for e in events)):
                return None
            if (key.get('key') != 'VK_B' or key.get('durationMs') != 60
                    or key.get('frameId') != field['frameId']
                    or any(type(key.get(k)) is not int for k in ('startedAt', 'finishedAt'))
                    or not field['timestamp'] <= key['startedAt'] <= key['finishedAt'] <= paused['timestamp']
                    or proof['timestamp'] != paused['timestamp']
                    or not paused['timestamp'] <= terminal['timestamp'] <= receipt['timestamp']
                    or not 0 <= now_ms - field['timestamp'] <= 600000
                    or field.get('fastSample') or field.get('mapPositionInherited')):
                return None
            require_fresh_source(field, self.session, key['startedAt'])
            if route_phase(field, expected_uid, [EXPLORATION_OBJECTIVE], allow_dialogue=False,
                           journal_resume=False, now_ms=key['startedAt']) != ('navigation', EXPLORATION_OBJECTIVE):
                return None
            # Recheck the original protected frames at their recorded times; only
            # the subsequent passive observation may authorize a new request.
            for observation in (paused, terminal):
                if (not source_account_matches(observation, expected_uid)
                        or not self.inventory_ready(observation, at_ms=observation['timestamp'])):
                    return None
            if (not isinstance(proof.get('evidence'), list) or not proof['evidence']
                    or any(row not in paused['ocr'] for row in proof['evidence'])
                    or self.current() != terminal or (self.root / 'request.json').read_bytes() != slot):
                return None
            self._owner(terminal['frameId'], idle=True)
            return dict(requestId=request['id'], sourceFrameId=field['frameId'],
                        pauseFrameId=paused['frameId'], terminalFrameId=terminal['frameId'],
                        requestBytes=slot, retained=retained)
        except (OSError, ValueError, RuntimeError, KeyError, IndexError, TypeError, AttributeError):
            return None

    def continuation_unchanged(self, witness):
        """Refuse reuse if any predecessor evidence changed during the passive refresh."""
        try:
            return all(path.read_bytes() == raw for path, raw in witness['retained'])
        except OSError:
            return False

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

    def execute(self, mission, source, fields, deadline, save_pending, *, expected_previous=None):
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
        if mission == 'questStep' and fields['step'] not in ('worldInventory', 'worldInventoryClose', 'actTwoNativeCombat', 'actTwoFieldCombat'):
            raise RouteError('Unsupported exploration inventory operation.')
        if mission == 'questStep' and fields['step'] != 'worldInventory' and not self.inventory_ready(source):
            raise RouteError('A recognized inventory is required before returning to the field.')
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
                    # Passive observations have no pending input to settle. Confirm the idle frame
                    # across polls while its ground scan is still fresh enough for the next decision.
                    settlement_seconds = max(0, min(5, deadline - time.monotonic()))
                    if mission == 'observe':
                        # Only this already-validated terminal observe receives read-only grace.
                        # The request, acquisition and subsequent input deadlines stay unchanged.
                        settlement_seconds = max(PASSIVE_TERMINAL_SETTLEMENT_SECONDS, settlement_seconds)
                    settled = self.command.wait_for_controller_quiescence(self.root, self.session, self.pid,
                        self.wts, frame, timeout_seconds=settlement_seconds,
                        stable_seconds=0.05 if mission == 'observe' else 0.4)
                    if not settled['controllerQuiescent']:
                        raise RouteError('Terminal request has no settled controller proof.')
                    self._owner()
                    if read(request_path) != request:
                        raise RouteError('Published request changed before retirement.')
                    self.command.validate_latest_observation(self.current(), self.session, frame)
                    self.pending = None
                    outcome = dict(request=request, receipt=receipt, observation=observed, cancelled=self.cancelled)
                    if expected_previous is not None:
                        outcome['predecessorMatched'] = previous == expected_previous
                    return outcome
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


def ground_scan_matches(source, now_ms, state, count, *, candidate_count=None, max_age_ms=1000):
    """Match the requested count to native evidence from this exact, still-fresh ground frame."""
    hud = source['hud']
    scan = hud.get('enemyBarObservation')
    stamp = hud.get('captureStamp')
    if not isinstance(scan, dict) or not isinstance(stamp, dict):
        return False
    captured_at = stamp.get('capturedAt')
    return (stamp.get('source') == 'game-capture-start' and type(captured_at) is int
            and captured_at <= source['timestamp'] <= now_ms and now_ms - captured_at <= max_age_ms
            and stamp.get('session') == scan.get('session') == source['session']
            and type(stamp.get('frameId')) is int and type(scan.get('frameId')) is int
            and stamp['frameId'] == scan['frameId'] == source['frameId']
            and type(scan.get('capturedAt')) is int and scan['capturedAt'] == captured_at
            and type(scan.get('version')) is int and scan['version'] == 1
            and scan.get('kind') == 'normal-ground-enemy-observation-v1' and scan.get('state') == state
            and type(scan.get('candidateCount')) is int
            and scan['candidateCount'] == (count if candidate_count is None else candidate_count)
            and type(scan.get('acceptedCount')) is int and scan['acceptedCount'] == count
            and isinstance(hud.get('enemyBars'), list) and len(hud['enemyBars']) == count)


def ground_scan_is_clear(source, now_ms):
    """Keep ordinary exploration restricted to a measured empty field."""
    return ground_scan_matches(source, now_ms, 'clear', 0)


def unanchored_ground_scan(source, expected_uid, now_ms):
    """Allow passive reacquisition only when unanchored red fragments are the sole refusal."""
    if (source.get('fastSample') or source.get('mapPositionInherited')
            or route_phase(source, expected_uid, [EXPLORATION_OBJECTIVE], allow_dialogue=False,
                           journal_resume=False, now_ms=now_ms) !=
               ('wait', 'Exploration requires a fresh enemy scan showing clear ground')):
        return False
    scan = source['hud'].get('enemyBarObservation')
    count = scan.get('candidateCount') if isinstance(scan, dict) else None
    return (type(count) is int and 1 <= count <= 64
            and scan.get('reason') == 'unanchored_bar_shaped_components'
            and ground_scan_matches(source, now_ms, 'ambiguous', 0, candidate_count=count))


def route_phase(source, expected_uid, objectives, *, allow_dialogue, journal_resume, now_ms=None,
                allow_field_combat=False):
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
        now_ms = int(time.time() * 1000) if now_ms is None else now_ms
        # A positive field scan only requests an inventory pause. The native combat action
        # measures the target, health, and controls again after reopening the world.
        if (allow_field_combat and not any(text.strip() for text in visible_objectives)
                and hp['current'] >= hp['max'] * .85 and 1 <= len(bars) <= 3
                and ground_scan_matches(source, now_ms, 'threat', len(bars), max_age_ms=2000)):
            return 'fieldCombat', None
        if bars or any(re.fullmatch(r'Defeatallopponents[0-9]+/[0-9]+', re.sub(r'\s', '', x)) for x in visible_objectives):
            return 'wait', 'Exploration requires zero visible threat'
        if hp['current'] < hp['max'] * .85:
            return 'wait', 'Existing generic exploration requires at least 85% health'
        if not ground_scan_is_clear(source, now_ms):
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


def require_start_near(source, session, expected_uid, start, now_ms):
    """Bind an optional route start to the first eligible fresh world, never old progress."""
    require_fresh_source(source, session, now_ms)
    hud, position = source['hud'], source.get('map')
    if (not source_account_matches(source, expected_uid) or hud.get('world') is not True
            or hud.get('groundControls') is not True or hud.get('climbing')
            or not isinstance(position, dict) or position.get('map') != start['map']
            or any(type(position.get(k)) not in (int, float) or not math.isfinite(position[k]) for k in ('x', 'y'))):
        raise RouteError('startNear requires fresh same-account grounded world coordinates.')
    distance = math.hypot(position['x'] - start['x'], position['y'] - start['y'])
    if distance > start['radius']:
        raise RouteError('Fresh route start is outside startNear; no alternate movement was submitted.')
    return dict(session=session, frameId=source['frameId'], timestamp=source['timestamp'],
                position=dict(map=position['map'], x=position['x'], y=position['y']), distance=distance)


def positive_parking_field(source, session, expected_uid):
    """A known living field may request protection; threat/objective evidence grants no extra gameplay."""
    hud = source.get('hud', {})
    hp, position = hud.get('health'), source.get('map')
    return (source.get('session') == session and type(source.get('frameId')) is int
            and source['frameId'] > 0 and isinstance(source.get('ocr'), list)
            and source_account_matches(source, expected_uid)
            and not source.get('fastSample') and not source.get('mapPositionInherited')
            and hud.get('world') is True and hud.get('groundControls') is True
            and not any(hud.get(k) for k in ('loading', 'unknownHud', 'auto', 'climbing', 'swimming',
                                           'journal', 'bigMap', 'dialogueReady', 'choice', 'tutorialStep'))
            and isinstance(hp, dict) and type(hp.get('current')) is int and type(hp.get('max')) is int
            and 0 < hp['current'] <= hp['max']
            and isinstance(position, dict) and position.get('map') == 'Teyvat'
            and all(type(position.get(k)) in (int, float) and math.isfinite(position[k]) for k in ('x', 'y')))


def run_controller(pilot, route, progress_path, expected_uid, *, allow_dialogue=False, allow_field_combat=False,
                   continuation_objectives=(), max_segments=MAX_SEGMENTS, deadline_ms=MAX_DEADLINE_MS,
                   continue_from_progress=None,
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
    start_near = route.get('startNear')
    if start_near is not None:
        state['route']['startNear'] = dict(start_near)
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

    inspect_after_encounter = False
    if allow_field_combat:
        state['fieldRotations'] = 0

    def protected_inventory(result):
        """Native pauses must identify this session's inventory before another action."""
        proof = result.get('pauseProof') if isinstance(result, dict) else None
        return (isinstance(proof, dict) and proof.get('kind') == 'inventory'
                and proof.get('session') == pilot.session and proof.get('verified') is True
                and result.get('pauseVerified') is True)

    def threat_checkpoint(result):
        """Keep completed waypoints while a protected field-scan interruption is reinspected."""
        return (allow_field_combat and objective == EXPLORATION_OBJECTIVE and protected_inventory(result)
                and result.get('status') == 'stopped' and result.get('reason') in (
                    'Enemy observed during exploration', 'Ground enemy scan did not establish clear ground')
                and type(result.get('nextWaypointIndex')) is int)

    def returned_rotation(result):
        """A completed software rotation permits fresh field inspection, never a kill claim."""
        return (protected_inventory(result) and result.get('nativeGroup') is False
                and result.get('nativeAttempted') is True and result.get('nativeReturned') is True
                and type(result.get('beforeFrameId')) is int and type(result.get('afterFrameId')) is int
                and result['beforeFrameId'] < result['afterFrameId'])

    def dispatch(mission, source, fields, *, allow_deadline_checkpoint=False, expected_previous=None,
                 observation_deadline=None):
        """Keep the original request/receipt result, including a failed native handoff."""
        options = {} if expected_previous is None else dict(expected_previous=expected_previous)
        active_deadline = deadline if observation_deadline is None else min(deadline, observation_deadline)
        outcome = pilot.execute(mission, source, fields, active_deadline, pending, **options)
        if expected_previous is not None:
            state['continuationSlotMatched'] = outcome.get('predecessorMatched') is True
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
            and (str(result.get('reason', '')).startswith('Navigation deadline reached') or
                 fields.get('requireMeasuredGround') is True and result.get('reason') ==
                 'Navigation stopped before movement to reserve incidental-climb recovery time')
            and type(result.get('nextWaypointIndex')) is int
            and 0 < result['nextWaypointIndex'] < len(fields['waypoints']))
        status = receipt.get('status')
        measured_threat = (mission == 'navigation' and status in ('stopped', 'failed') and threat_checkpoint(result)
                           and 0 <= result['nextWaypointIndex'] < len(fields['waypoints']))
        rotation = (mission == 'questStep' and fields['step'] == 'actTwoFieldCombat' and status == 'stopped'
                    and returned_rotation(result))
        if outcome.get('cancelled') or not (status == 'completed' or deadline_checkpoint or measured_threat or rotation):
            raise RouteError('Mission did not complete; original result retained without retry.')
        return result

    def protect_failed_exit():
        """One fresh observation and one existing inventory pause, within the original clock only."""
        protection = dict(kind='route-failure-inventory-protection-v1', status='notAttempted',
            protectionVerified=False, originalStatus=state['status'], originalReason=state.get('reason'),
            originalRecordCount=len(state['records']), startedAt=int(clock_ms()), maximumMilliseconds=8000)
        state['exitProtection'] = protection
        try:
            if pilot.stopped() or state['pending'] is not None or pilot.pending is not None:
                protection['reason'] = 'STOP or pending input prevents exit protection.'
                return
            if monotonic() >= deadline:
                protection['reason'] = 'Original route deadline already elapsed.'
                return
            prior_inputs = [r['request'] for r in state['records'] if r['request']['mission'] != 'observe']
            if prior_inputs and prior_inputs[-1].get('step') == 'worldInventory':
                protection['reason'] = 'Prior inventory preparation is not repeated.'
                return
            source = pilot.current()
            if not positive_parking_field(source, pilot.session, expected_uid):
                protection['reason'] = 'No positively recognized same-account living field.'
                return
            pilot._owner(source['frameId'], idle=True)
            park_deadline = min(deadline, monotonic() + 8)
            protection['status'] = 'observing'
            save()
            dispatch('observe', source, {}, observation_deadline=park_deadline)
            source = pilot.current()
            require_fresh_source(source, pilot.session, clock_ms())
            if (pilot.stopped() or monotonic() >= park_deadline
                    or not positive_parking_field(source, pilot.session, expected_uid)):
                raise RouteError('Refreshed field or original clock does not permit an inventory pause.')
            pilot._owner(source['frameId'], idle=True)
            protection.update(status='pausing', sourceFrameId=source['frameId'])
            save()
            result = dispatch('questStep', source, dict(step='worldInventory'), observation_deadline=park_deadline)
            terminal = pilot.current()
            require_fresh_source(terminal, pilot.session, clock_ms())
            if (not isinstance(result, dict) or result.get('pausedInventory') is not True
                    or not source_account_matches(terminal, expected_uid) or not pilot.inventory_ready(terminal)):
                raise RouteError('Exit protection has no fresh verified inventory terminal.')
            pilot._owner(terminal['frameId'], idle=True)
            protection.update(status='protected', protectionVerified=True, terminalFrameId=terminal['frameId'])
        except Exception as error:
            # Protection may fail independently. Never replace the route outcome or replay a request.
            protection.update(status='pending' if state['pending'] is not None else 'failed', reason=str(error))
        finally:
            protection['requestIds'] = [r['request']['id'] for r in state['records'][protection['originalRecordCount']:]]
            protection['finishedAt'] = int(clock_ms())

    try:
        while monotonic() < deadline:
            if pilot.stopped():
                raise RouteError('Operator STOP prevents further route input.')
            source = pilot.current()
            continuation = None
            # A new startNear requires a new world measurement. It cannot borrow
            # a prior route's position, even when the preceding pause is exact.
            if (not state['records'] and continue_from_progress is not None
                    and objective == EXPLORATION_OBJECTIVE and 'startNear' not in route):
                continuation = pilot.exploration_continuation(continue_from_progress, expected_uid, clock_ms())
            dispatch('observe', source, {}, expected_previous=continuation['requestBytes'] if continuation else None)
            source = pilot.current()
            now_ms = clock_ms()
            require_fresh_source(source, pilot.session, now_ms)
            if (continuation is not None and state.get('continuationSlotMatched') is True
                    and pilot.continuation_unchanged(continuation)
                    and source_account_matches(source, expected_uid) and pilot.inventory_ready(source)):
                inventory_navigation = EXPLORATION_OBJECTIVE
                state['continuedFromProgress'] = dict(path=str(continue_from_progress),
                    **{key: continuation[key] for key in ('requestId', 'sourceFrameId', 'pauseFrameId', 'terminalFrameId')})
            # Native travel ends in inventory. Open it once for a fresh field measurement before
            # navigation; a delayed transition must never turn into a second Escape.
            if (inventory_navigation is None and objective == EXPLORATION_OBJECTIVE
                    and (len(state['records']) == 1 or inspect_after_encounter)
                    and source['hud'].get('world') is False and source.get('map') is None
                    and source_account_matches(source, expected_uid) and pilot.inventory_ready(source)):
                dispatch('questStep', source, dict(step='worldInventoryClose'))
                inspect_after_encounter = False
                continue
            if inspect_after_encounter:
                raise RouteError('Encounter handoff did not settle in the expected inventory.')
            phase, value = route_phase(source, expected_uid, authorized_objectives,
                allow_dialogue=allow_dialogue, journal_resume=journal_resume, now_ms=now_ms,
                allow_field_combat=allow_field_combat)
            # One stationary retry window per controller, only at initial field
            # entry or after the existing Inventory-close transition. No keys,
            # camera changes or movement occur while the scan is ambiguous.
            new_world = (len(state['records']) == 1 or (len(state['records']) >= 2
                and state['records'][-2]['request'].get('step') == 'worldInventoryClose'))
            if (objective == EXPLORATION_OBJECTIVE and new_world and 'groundReacquisition' not in state
                    and unanchored_ground_scan(source, expected_uid, now_ms)):
                began = monotonic()
                scan_deadline = min(deadline, began + 2.0)
                scan = source['hud']['enemyBarObservation']
                samples = [dict(frameId=source['frameId'], capturedAt=scan['capturedAt'],
                                state=scan['state'], reason=scan['reason'])]
                state['groundReacquisition'] = dict(startedAt=int(now_ms), maximumFrames=4,
                    maximumMilliseconds=2000, frames=samples)
                while (len(samples) < 4
                       and scan_deadline - monotonic() >= STATIONARY_OBSERVATION_RESERVE_SECONDS):
                    if pilot.stopped():
                        raise RouteError('Operator STOP prevents stationary ground reacquisition.')
                    dispatch('observe', source, {}, observation_deadline=scan_deadline)
                    source = pilot.current()
                    now_ms = clock_ms()
                    require_fresh_source(source, pilot.session, now_ms)
                    scan = source['hud'].get('enemyBarObservation')
                    stamp = scan.get('capturedAt') if isinstance(scan, dict) else None
                    if (monotonic() >= scan_deadline or type(stamp) is not int
                            or source['frameId'] <= samples[-1]['frameId'] or stamp <= samples[-1]['capturedAt']):
                        phase, value = 'wait', 'Stationary reacquisition expired or did not produce a distinct capture'
                        break
                    samples.append(dict(frameId=source['frameId'], capturedAt=stamp,
                                        state=scan.get('state'), reason=scan.get('reason')))
                    phase, value = route_phase(source, expected_uid, authorized_objectives,
                        allow_dialogue=False, journal_resume=False, now_ms=now_ms,
                        allow_field_combat=allow_field_combat)
                    if phase == 'fieldCombat' or (phase == 'navigation' and value == EXPLORATION_OBJECTIVE):
                        break
                    if not unanchored_ground_scan(source, expected_uid, now_ms):
                        phase, value = 'wait', 'Stationary reacquisition found threat or other unsafe evidence'
                        break
                state['groundReacquisition']['elapsedMilliseconds'] = round((monotonic() - began) * 1000, 3)
                state['groundReacquisition']['measuredClear'] = phase == 'navigation' and value == EXPLORATION_OBJECTIVE
            paused_navigation = inventory_navigation is not None
            if paused_navigation:
                if not source_account_matches(source, expected_uid) or not pilot.inventory_ready(source):
                    raise RouteError('Owned exploration pause is not verified in the fresh source.')
                phase, value = 'navigation', inventory_navigation
            if phase == 'wait':
                state.update(status='waiting', reason=value)
                break
            # Inventory close may expose the field, but neither an inventory
            # checkpoint nor historical progress can authorize the starting pose.
            if start_near is not None and 'startNearVerified' not in state:
                if phase not in ('navigation', 'combat', 'fieldCombat') or paused_navigation:
                    state.update(status='waiting', reason='startNear needs a fresh eligible world before any route action')
                    break
                state['startNearVerified'] = require_start_near(source, pilot.session, expected_uid, start_near, now_ms)
                save()
            if phase in ('combat', 'dialogue') and phase == last_phase:
                state.update(status='waiting', reason='Completed phase has not cleared in fresh evidence')
                break
            if phase in ('combat', 'dialogue') and state['handoffs'] >= max_segments * 2:
                raise RouteError('Maximum encounter/dialogue handoffs reached.')
            remaining = int((deadline - monotonic()) * 1000)
            if phase == 'fieldCombat':
                pause = dispatch('questStep', source, dict(step='worldInventory'))
                if not isinstance(pause, dict) or pause.get('pausedInventory') is not True:
                    raise RouteError('Could not verify the inventory handoff to native combat.')
                if state['fieldRotations'] >= max_segments * 2:
                    state.update(status='waiting', reason='Field combat rotation limit reached')
                    break
                dispatch('observe', pilot.current(), {})
                paused = pilot.current()
                if not source_account_matches(paused, expected_uid) or not pilot.inventory_ready(paused):
                    raise RouteError('Native combat requires the expected account in inventory.')
                rotation = dispatch('questStep', paused, dict(step='actTwoFieldCombat'))
                if not returned_rotation(rotation):
                    raise RouteError('Native field rotation and its inventory pause were not established.')
                state['fieldRotations'] += 1
                inspect_after_encounter = True
                save()
                continue
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
                if threat_checkpoint(result):
                    # Inspect the actual encounter. Dispatch already preserved its native route cursor.
                    inspect_after_encounter = True
                    last_phase = 'navigation'
                    continue
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
        if state['status'] in ('waiting', 'stopped'):
            protect_failed_exit()
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
    parser.add_argument('--continue-from-progress', type=Path,
                        help='Reuse an exact completed exploration pause on the same pilot; otherwise refresh the field normally')
    parser.add_argument('--allow-field-combat', action='store_true',
                        help='Engage up to three measured enemies during exploration and resume from fresh field evidence')
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
                    allow_dialogue=args.allow_dialogue, allow_field_combat=args.allow_field_combat,
                    continuation_objectives=args.continue_objective,
                    continue_from_progress=args.continue_from_progress,
                    max_segments=args.max_segments, deadline_ms=args.deadline_ms)
            finally:
                pilot.close()
            print(json.dumps(dict(status=report['status'], nextWaypointIndex=report['nextWaypointIndex'],
                progress=str(args.progress), reason=report.get('reason'))))
            if report['status'] != 'arrived':
                raise SystemExit(2)
            return
        if args.continue_from_progress is not None:
            raise RouteError('--continue-from-progress requires controller mode.')
        outcome = run_route(args.root, read(args.route), args.session,
                            max_segments=args.max_segments, deadline_ms=args.deadline_ms)
    except (OSError, json.JSONDecodeError, RouteError) as exc:
        raise SystemExit(str(exc)) from exc
    if outcome != 'arrived':
        raise SystemExit(2)


if __name__ == '__main__':
    main()


