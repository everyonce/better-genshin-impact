"""Execute one supervised route using bounded BetterGI JSON missions; never replay a timed-out request."""
import argparse
import json
import math
import os
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = Path(os.environ.get('BETTERGI_PILOT_APP_DIR', REPO / 'artifacts/release-r8/BetterGI-English-win-x64'))
ROOT = APP / 'User/JsScript/ActOnePilot'
MAX_DEADLINE_MS = 90_000
MAX_SEGMENTS = 3


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('route', type=Path, help='JSON file containing objective and ordered waypoints')
    parser.add_argument('--session', required=True)
    parser.add_argument('--deadline-ms', type=int, default=MAX_DEADLINE_MS)
    parser.add_argument('--max-segments', type=int, default=MAX_SEGMENTS)
    parser.add_argument('--root', type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        outcome = run_route(args.root, read(args.route), args.session,
                            max_segments=args.max_segments, deadline_ms=args.deadline_ms)
    except (OSError, json.JSONDecodeError, RouteError) as exc:
        raise SystemExit(str(exc)) from exc
    if outcome != 'arrived':
        raise SystemExit(2)


if __name__ == '__main__':
    main()


