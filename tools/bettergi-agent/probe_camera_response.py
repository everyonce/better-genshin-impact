"""Identify isolated camera responses from live BetterGI poses in the existing RDP game."""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import sys
import time
import uuid

from hybrid_navigation import HybridNavigation
from hybrid_routes import PATROL_STATIONS
from navigation_idle_recovery import fresh_frame
from navigation_profiles import COURTYARD_PROFILE, NAVIGATION_PROFILES, allows_pose_scope
from observation_profiles import P2P_NATIVE, verify_frame, verify_hello
from observation_timing import observation_timestamp
from resident_runtime import atomic_json, control_module, require_current_rdp, verify_bridge_identity
from run_rdp_patrol import ready_session
from stream_client import Bridge, action_response_accepted, rgb_frame_quality


MODEL = 'camera-response-probe-v1'
# A vertical survey is one small relative shift, not a measured absolute pitch.
MAX_PITCH_MOUSE_UNITS = 80
STATION = PATROL_STATIONS['stair-front']
SEQUENCES = {
    'train': (75, -220, 30, -125, 220, -30, 125, -75, -125, 30, -75, 220, -30, 125, -220, 75),
    'holdout': (-95, 170, -45, 95, -170, 45),
}


def require(condition, message):
    """Stop before any further dispatch when the isolated camera experiment loses its gates."""
    if not condition:
        raise ValueError(message)


def stable(rows):
    """Use circular yaw distance so a 359.5-to-0.5 degree wrap remains stationary."""
    first = rows[0]['navigationPose']['yawDegrees']
    offsets = [(r['navigationPose']['yawDegrees'] - first + 180) % 360 - 180 for r in rows]
    return max(offsets) - min(offsets) <= 2


def qualified(row, profile=COURTYARD_PROFILE):
    """Require normal same-frame pose, both scoped readiness gates and a fresh native WGC source."""
    pose, source = row.get('navigationPose') or {}, row.get('sourceFrame') or {}
    gate, current = row.get('frameWorldReadiness') or {}, row.get('worldReadiness') or {}
    values = [pose.get(k) for k in ('x', 'y', 'yawDegrees', 'positionConfidence', 'yawConfidence')]
    return (HybridNavigation.latest_pose_usable(row) and row.get('frameQuality') == 'usable'
            and row.get('sourceTimestampKind') == 'wgc_reported_compositor_qpc'
            and row.get('motionEvidence', {}).get('xKeyMatched') is False
            and row.get('inputAvailable') is True and all(type(v) in (int, float) and math.isfinite(v) for v in values)
            and allows_pose_scope(pose, profile) and .99 <= values[3] <= 1 and .2 <= values[4] <= 1
            and 0 <= values[2] < 360 and isinstance(source.get('captureEpoch'), str) and source['captureEpoch']
            and type(source.get('timestamp100ns')) is int and source['timestamp100ns'] > 0
            and gate.get('ready') is True and current.get('ready') is True and type(gate.get('epoch')) is int
            and gate.get('epoch') == current.get('epoch') and gate.get('sourceFrameId') == row['frameId']
            and gate.get('sourceFrame') == source and (current.get('sourceFrame') or {}).get('captureEpoch') == source['captureEpoch']
            and fresh_frame(row, time.perf_counter_ns(), 150))


class Experiment:
    """Own a single synchronous bridge, track every observed frame and admit just one outstanding pulse."""
    def __init__(self, bridge, report, *, station=STATION, profile=COURTYARD_PROFILE, seconds=65, stop_check=None):
        require(profile in NAVIGATION_PROFILES and len(station) == 2
                and all(type(v) in (int, float) and math.isfinite(v) for v in station)
                and type(seconds) in (int, float) and 0 < seconds <= 65, 'Invalid bounded camera scope')
        self.bridge, self.report = bridge, report
        self.station, self.profile, self.stop_check = tuple(station), profile, stop_check
        self.contract = verify_hello(bridge.hello, P2P_NATIVE, 'observe')
        self.anchor = self.previous = self.pending = self.applied = None
        self.deadline = time.monotonic() + seconds
        self.capture_id = self.world_id = None

    def collect(self, reply):
        """Keep original terminal receipts, including foreign or malformed receipts that fail this run."""
        receipts = reply.get('receipts', [])
        self.report['receipts'].extend(receipts)
        # Receipts can arrive on a repeated source frame that observations deliberately deduplicate.
        # Keep its complete metadata envelope before validation, including rejected or dropped evidence.
        if receipts or reply.get('droppedReceipts', 0):
            self.report.setdefault('receiptEnvelopes', []).append(copy.deepcopy(reply))
        require(reply.get('droppedReceipts', 0) == 0, 'The bridge lost input receipts')
        for r in receipts:
            a = self.pending
            require(a and not self.applied and r.get('requestId') == a['requestId'] and r.get('frameId') == a['frameId']
                    and r.get('modelId') == MODEL and r.get('status') == 'completed' and r.get('reason') == 'horizon_complete',
                    'Unowned, repeated, or incomplete camera receipt')
            steps = r.get('appliedSteps') or []
            require(len(steps) == 1 and steps[0].get('index') == 0 and steps[0].get('keys') == []
                    and steps[0].get('mouseDx') == a['mouseDx'] and steps[0].get('mouseDy') == a.get('mouseDy', 0),
                    'Terminal receipt did not apply exactly the requested camera step')
            start, end = steps[0]['startedAtMs'], r['endedAtMs']
            require(r['acceptedAtMs'] == a['accepted']['acceptedAtMs']
                    and a['sourceAtMs'] <= r['acceptedAtMs'] <= start < a['sourceAtMs'] + 150
                    and 85 <= end - start <= 250, 'Terminal receipt has unbound or late input timing')
            self.applied = r

    def next(self):
        """Poll all delivered metadata, reject changes on cached frames, and return only distinct source frames."""
        while time.monotonic() < self.deadline:
            if self.stop_check:
                self.stop_check()
            before = time.perf_counter_ns()
            frame, pixels = self.bridge.request('frame')
            arrived = time.perf_counter_ns()
            if frame.get('type') == 'frame':
                verify_frame(frame, pixels, self.contract)
                frame.update(clientReceivedNs=arrived, transportRoundTripMs=(arrived-before)/1e6,
                             frameQuality=rgb_frame_quality(pixels), sourceAtMs=observation_timestamp(frame))
                prior = self.previous
                distinct = prior is None or frame['frameId'] != prior['frameId']
                if distinct:
                    self.report['observations'].append(dict(frame))
                self.collect(frame)
                ok = qualified(frame, self.profile)
                if self.anchor is not None:
                    require(ok, 'Source, recognition, freshness or readiness lost during the pulse sequence')
                if ok:
                    pose, source = frame['navigationPose'], frame['sourceFrame']
                    point = (pose['x'], pose['y'])
                    require(math.dist(point, self.station) <= 2, 'Character left the declared camera station')
                    already_bound = self.anchor is not None
                    if not already_bound:
                        self.anchor = point
                        self.capture_id, self.world_id = source['captureEpoch'], frame['frameWorldReadiness']['epoch']
                        self.report.update(captureEpoch=self.capture_id, worldEpoch=self.world_id, anchorPosition=point)
                    require(source['captureEpoch'] == self.capture_id and frame['frameWorldReadiness']['epoch'] == self.world_id
                            and math.dist(point, self.anchor) <= .35, 'Capture epoch, readiness epoch or body position changed')
                    if already_bound and prior:
                        if distinct:
                            require(frame['frameId'] > prior['frameId'] and source['timestamp100ns'] > prior['sourceFrame']['timestamp100ns']
                                    and 0 < frame['sourceAtMs'] - prior['sourceAtMs'] <= 150, 'Source trajectory is discontinuous')
                        else:
                            require(source == prior['sourceFrame'], 'Repeated frame identity has a changed source')
                    self.previous = frame
                    if distinct:
                        return frame
                elif distinct:
                    self.previous = frame
            else:
                self.collect(frame)
                require(self.anchor is None and frame.get('type') == 'waiting', 'Source became unavailable')
            time.sleep(.006)
        raise TimeoutError('Camera experiment exceeded its wall-time bound')

    def pulse(self, dx, *, dy=0):
        """Bracket one fixed 100-ms single-axis shift with a stable baseline and exact terminal receipt."""
        require(type(dx) is int and type(dy) is int
                and ((0 < abs(dx) <= 250 and dy == 0)
                     or (dx == 0 and 0 < abs(dy) <= MAX_PITCH_MOUSE_UNITS)),
                'Camera pulses require one integer axis: horizontal at most 250 or vertical at most 80')
        pre = [self.next()]
        while pre[-1]['sourceAtMs'] - pre[0]['sourceAtMs'] < 500:
            pre.append(self.next())
        require(stable(pre), 'Camera moved in the pre-pulse baseline')
        frame = pre[-1]
        step = dict(keys=[], durationMs=100, mouseDx=dx, mouseDy=dy)
        rid = uuid.uuid4().hex
        at = frame['sourceAtMs']
        a = dict(requestId=rid, frameId=frame['frameId'], sourceAtMs=at, modelId=MODEL, mouseDx=dx, mouseDy=dy, step=step,
                 preFrameIds=[f['frameId'] for f in pre], postFrameIds=[], settledFrameIds=[])
        self.report['actions'].append(a)
        if self.stop_check:
            self.stop_check()
        require(fresh_frame(frame, time.perf_counter_ns(), 150), 'Dispatch frame became stale')
        self.pending, self.applied = a, None
        ack, payload = self.bridge.request('action', requestId=rid, frameId=frame['frameId'], modelId=MODEL,
                                          observedAtMs=frame['capturedAtMs'], startBeforeMs=at+150,
                                          expiresAtMs=at+250, steps=[step])
        a['accepted'] = ack
        self.collect(ack)
        require(action_response_accepted(ack, rid, payload), 'Camera pulse was rejected')
        end_samples = []
        while True:
            f = self.next()
            a['postFrameIds'].append(f['frameId'])
            require(f['sourceAtMs'] - at <= 3000, 'Camera pulse failed to settle or produce a terminal receipt')
            if not self.applied or f['sourceAtMs'] < self.applied['endedAtMs'] + 600:
                continue
            end_samples.append(f)
            if f['sourceAtMs'] >= self.applied['endedAtMs'] + 700 and len(end_samples) >= 3:
                # The middle frame must be independently measured, even at a high polling rate.
                three = [end_samples[0], end_samples[len(end_samples)//2], f]
                if f['sourceAtMs'] - three[0]['sourceAtMs'] >= 100 and stable(end_samples):
                    a['settledFrameIds'] = [v['frameId'] for v in three]
                    self.pending = None
                    return dict(beforeYawDegrees=pre[-1]['navigationPose']['yawDegrees'],
                                afterYawDegrees=f['navigationPose']['yawDegrees'], mouseDx=dx, mouseDy=dy,
                                beforeFrameId=pre[-1]['frameId'], afterFrameId=f['frameId'])
                if not stable(end_samples):
                    end_samples = [f]


def run(args, report):
    """Start only an authenticated idle child and issue every stop on its original verified pipe."""
    require_current_rdp(args.rdp_session_id)
    lifecycle = control_module()
    _, child = ready_session(lifecycle)
    require(child['windowsSessionId'] == args.rdp_session_id and child['instanceNonce'] == args.child_nonce,
            'Wrong RDP child identity')
    listener = lifecycle.start_agent(child, 15, enable_input=True, observation_profile=P2P_NATIVE)
    require((listener.get('processId'), listener.get('instanceNonce')) == (child['processId'], args.child_nonce),
            'Child changed during listener startup')
    bridge = Bridge(listener['agentPipeName'])
    authenticated = False
    trial = None
    try:
        verify_bridge_identity(bridge.handle, child['processId'], args.rdp_session_id)
        authenticated = True
        hello = bridge.hello
        report.update(hello=hello, windowsSessionId=args.rdp_session_id, childPid=child['processId'])
        require(hello.get('inputEnabled') is True and hello.get('supportsStartBeforeMs') is True
                and hello.get('supportsRelease') is True, 'Required camera input timing capabilities are missing')
        HybridNavigation(hello.get('navigationGuidance') or {})
        trial = Experiment(bridge, report)
        config, payload = bridge.request('enableNavigationGuidance')
        require(config.get('type') == 'navigationGuidance' and config.get('enabled') is True and not payload,
                'Same-frame navigation guidance was not enabled')
        trial.collect(config)
        for dx in SEQUENCES[args.sequence]:
            trial.pulse(dx)
    finally:
        try:
            if authenticated:
                reply, payload = bridge.request('stop')
                report['stop'] = reply
                require(not payload and reply.get('type') == 'stopped', 'Missing stop acknowledgement')
                if trial:
                    trial.collect(reply)
        finally:
            bridge.handle.close()


def main():
    """Refuse to replace prior evidence and publish a failed trace on every handled error."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rdp-session-id', type=int, required=True)
    parser.add_argument('--child-nonce', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sequence', choices=SEQUENCES, required=True)
    args = parser.parse_args()
    if args.rdp_session_id < 1 or not re.fullmatch('[0-9a-f]{32}', args.child_nonce):
        parser.error('Supply the current RDP session ID and authenticated 32-hex child nonce.')
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(version=1, kind='bettergi-camera-response', sequence=args.sequence, status='running',
                  expectedMouseDx=list(SEQUENCES[args.sequence]), observations=[], actions=[], receipts=[])
    with output.open('x', encoding='utf-8') as initial:
        json.dump(report, initial)
    try:
        run(args, report)
        report['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}')
    finally:
        atomic_json(output, report)
    print(json.dumps(dict(output=str(output), status=report['status'], pulses=len(report['actions']),
                          error=report.get('error'))))
    return int(report['status'] != 'completed')


if __name__ == '__main__':
    sys.exit(main())
