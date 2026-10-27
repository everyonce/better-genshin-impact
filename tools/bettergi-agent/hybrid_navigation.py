"""One input owner combining native courtyard localization with GPU policy proposals.

The fixed route is a repeatable qualification task, not general navigation.
Native poses and receipts establish progress; accepted commands alone do not.
"""
from collections import Counter, deque
import copy
import math

from observation_timing import observation_timestamp


PROFILE = 'mondstadt-courtyard-hybrid-v1'
START = (-867.7041015625, 2281.378173828125)
END = (-874.3662109375, 2274.179931640625)


def yaw_error(a, b):
    """Return the unsigned shortest heading difference."""
    return abs((a - b + 180) % 360 - 180)


class HybridNavigation:
    """Serial planner; the existing bridge remains the sole input/freshness owner."""

    def __init__(self, capability):
        expected = dict(version=1, profileId=PROFILE, sameFrame=True, readOnly=True)
        if any(capability.get(k) != v for k, v in expected.items()):
            raise ValueError('The bridge does not advertise same-frame hybrid navigation')
        if tuple(capability.get('start', {}).get(k) for k in ('x', 'y')) != START or tuple(
                capability.get('end', {}).get(k) for k in ('x', 'y')) != END:
            raise ValueError('The fixed courtyard geometry differs')
        self.phase = 'admitting'
        self.target = END
        self.target_name = 'end'
        self.samples = []
        self.last_frame_id = None
        self.source_epoch = None
        self.release_at = None
        self.legs = 0
        self.selections = Counter()
        self.events = []
        self.movements = deque(maxlen=512)
        self.receipt_ids = deque(maxlen=512)
        self.progress_anchor = None
        self.recovery_attempts = 0
        self.total_recoveries = 0
        self.recovery_started = None
        self.recovery_direction = 'A'
        self.last_pose = None
        self.last_at = None
        self.leg_started = None
        self.failure = None

    def snapshot(self):
        """Return scalar progress without exposing mutable internal collections."""
        return dict(profileId=PROFILE, phase=self.phase, target=self.target_name,
                    completedLegs=self.legs, selections=dict(self.selections),
                    recoveryAttempts=self.total_recoveries, failure=self.failure,
                    lastPose=copy.deepcopy(self.last_pose))

    def drain_events(self):
        """Transfer sparse verified endpoint/recovery events to the evidence writer."""
        events, self.events = self.events, []
        return events

    @staticmethod
    def latest_pose_usable(frame):
        """A newer unavailable pose or climb hint must invalidate an older proposed correction."""
        pose, motion = frame.get('navigationPose') or {}, frame.get('motionEvidence') or {}
        return (pose.get('state') == 'valid' and pose.get('frameId') == frame.get('frameId')
                and motion.get('status') == 'normal' and motion.get('spaceKeyMatched') is False)

    def interrupt(self, reason):
        """Require fresh confirmation after interruption without inventing completed legs."""
        self.samples.clear()
        self.progress_anchor = None
        self.movements.clear()
        if self.phase in ('recovering', 'releaseRequired'):
            self.phase = 'walking' if self.leg_started is not None else 'admitting'
        if self.phase != 'verifying':
            self.release_at = None

    def receipt(self, receipt):
        """Use only terminal applied movement intervals, deduplicated within this lease."""
        identity = receipt.get('requestId')
        if not identity or identity in self.receipt_ids:
            return
        self.receipt_ids.append(identity)
        steps = receipt.get('appliedSteps', [])
        for i, step in enumerate(steps):
            if set(step.get('keys', [])) & {'W', 'A', 'S', 'D'}:
                begin = step['startedAtMs']
                end = steps[i + 1]['startedAtMs'] if i + 1 < len(steps) else receipt['endedAtMs']
                if end > begin:
                    self.movements.append((begin, end))

    def released(self, response):
        """Endpoint samples must follow an acknowledged release and its response barrier."""
        stamp = response.get('serverNowMs')
        if response.get('type') != 'released' or type(stamp) not in (int, float) or not math.isfinite(stamp):
            raise RuntimeError('Hybrid endpoint release was not acknowledged')
        # The existing bridge stamps serverNowMs after releasing and snapshotting
        # its readiness gate; releasedAtMs is an evidence-event field, not wire data.
        self.release_at = stamp
        self.phase = 'verifying'
        self.samples.clear()

    def _sample(self, pose, at):
        """Retain three separated, stable, distinct observations rather than three polls of one frame."""
        if self.samples and at - self.samples[-1]['atMs'] < 80:
            return False
        row = dict(frameId=pose['frameId'], atMs=at, x=pose['x'], y=pose['y'], yawDegrees=pose['yawDegrees'])
        if any(math.hypot(row['x'] - old['x'], row['y'] - old['y']) > 1.5
               or yaw_error(row['yawDegrees'], old['yawDegrees']) > 3 for old in self.samples):
            self.samples.clear()
        self.samples.append(row)
        self.samples = self.samples[-3:]
        return len(self.samples) == 3

    def _fail(self, reason):
        """Terminal geometry/recovery errors cannot silently become successful route completion."""
        self.failure = reason
        self.phase = 'failed'
        raise RuntimeError('hybrid_navigation:' + reason)

    def prepare(self, frame):
        """Validate the exact source pose and advance read-only endpoint verification."""
        if self.failure:
            self._fail(self.failure)
        pose = frame.get('navigationPose') or {}
        if pose.get('state') != 'valid' or pose.get('frameId') != frame.get('frameId'):
            return 'poseUnavailable'
        fields = ('x', 'y', 'yawDegrees', 'positionConfidence', 'yawConfidence',
                  'headingToStartDegrees', 'headingToEndDegrees', 'mouseToStart', 'mouseToEnd')
        if any(type(pose.get(k)) not in (int, float) or not math.isfinite(pose[k]) for k in fields):
            self._fail('invalid_pose_numbers')
        if (pose.get('layerId') != 'City_102' or not .99 <= pose['positionConfidence'] <= 1
                or not .2 <= pose['yawConfidence'] <= 1 or not 0 <= pose['yawDegrees'] < 360):
            return 'poseUnqualified'
        motion = frame.get('motionEvidence') or {}
        if motion.get('status') != 'normal' or motion.get('spaceKeyMatched') is not False:
            return 'motionNotNormal'
        source = frame.get('sourceFrame') or {}
        epoch = source.get('captureEpoch')
        if not epoch:
            self._fail('wgc_source_required')
        if self.source_epoch is not None and epoch != self.source_epoch:
            self._fail('capture_generation_changed')
        self.source_epoch = epoch
        if self.last_frame_id is not None and pose['frameId'] <= self.last_frame_id:
            return 'duplicatePose'
        self.last_frame_id = pose['frameId']
        at = observation_timestamp(frame)
        if self.last_at is not None and at <= self.last_at:
            return 'sourceNotIncreasing'
        self.last_at, self.last_pose = at, copy.deepcopy(pose)
        x, y = pose['x'], pose['y']
        length = math.dist(START, END)
        projection = ((x - START[0]) * (END[0] - START[0]) + (y - START[1]) * (END[1] - START[1])) / length
        cross = abs((x - START[0]) * (END[1] - START[1]) - (y - START[1]) * (END[0] - START[0])) / length
        if cross > 4 or projection < -3 or projection > length + 3:
            self._fail('outside_fixed_courtyard_corridor')
        if self.phase == 'admitting':
            near = min(math.hypot(x - p[0], y - p[1]) for p in (START, END))
            if near > 2:
                self._fail('verified_endpoint_start_required')
            if not self._sample(pose, at):
                return 'confirmingStart'
            self.target_name = 'end' if math.hypot(x - START[0], y - START[1]) <= 2 else 'start'
            self.target = END if self.target_name == 'end' else START
            self.phase = 'walking'
            self.leg_started = at
            self.samples.clear()
            self.events.append(dict(type='hybridStartVerified', frameId=pose['frameId'], atMs=at, target=self.target_name))
        if at - self.leg_started > 35000:
            self._fail('leg_progress_deadline')
        distance = math.hypot(x - self.target[0], y - self.target[1])
        if self.phase == 'verifying':
            if at < self.release_at + 80:
                return 'waitingAfterRelease'
            if distance > 2:
                self._fail('endpoint_moved_after_release')
            if not self._sample(pose, at):
                return 'verifyingEndpoint'
            self.legs += 1
            self.events.append(dict(type='hybridEndpointVerified', completedLegs=self.legs,
                endpoint=self.target_name, sourceEpoch=epoch, releaseAtMs=self.release_at,
                samples=copy.deepcopy(self.samples), legElapsedMs=at - self.leg_started))
            self.target_name = 'start' if self.target_name == 'end' else 'end'
            self.target = START if self.target_name == 'start' else END
            self.phase, self.leg_started = 'walking', at
            self.samples.clear()
            self.progress_anchor = None
            self.recovery_attempts = 0
            self.movements.clear()
            return 'endpointVerified'
        if distance <= 1.1:
            self.phase = 'releaseRequired'
            return 'releaseRequired'
        return None

    def choose(self, frame, proposal):
        """Accept route-compatible model walking; otherwise use measured native correction."""
        pose, at = self.last_pose, self.last_at
        heading = pose['headingToStartDegrees' if self.target_name == 'start' else 'headingToEndDegrees']
        correction = pose['mouseToStart' if self.target_name == 'start' else 'mouseToEnd']
        error = yaw_error(pose['yawDegrees'], heading)
        owner, reason, keys, dx = 'hybrid-native', 'nativeHeading', [], max(-350, min(350, int(correction)))
        if self.phase == 'recovering':
            elapsed = at - self.recovery_started
            if elapsed < 250:
                keys, dx, reason = ['S'], 0, 'obstacleRetreat'
            elif elapsed < 550:
                keys, dx, reason = [self.recovery_direction], 0, 'obstacleSidestep'
            else:
                self.phase = 'walking'
                self.progress_anchor = None
        if self.phase == 'walking' and error <= 5:
            dx, keys, reason = 0, ['W'], 'modelIdleOrOffRoute'
            steps = proposal.get('steps', [])
            if (proposal.get('parseValid') and len(steps) == 1 and set(steps[0].get('keys', [])) == {'W'}
                    and abs(steps[0].get('mouseDx', 0)) <= 3 and steps[0].get('mouseDy', 0) == 0):
                owner, reason = 'open-p2p', 'modelRouteCompatible'
                dx = steps[0].get('mouseDx', 0)
            if self.progress_anchor is None:
                self.progress_anchor = (at, pose['x'], pose['y'])
            begin, x, y = self.progress_anchor
            if at - begin >= 2000:
                movement = sum(max(0, min(at, e) - max(begin, b)) for b, e in self.movements)
                displacement = math.hypot(pose['x'] - x, pose['y'] - y)
                if movement >= 600 and displacement < .5:
                    if self.recovery_attempts >= 2:
                        self._fail('obstacle_recovery_exhausted')
                    self.recovery_attempts += 1
                    self.total_recoveries += 1
                    self.recovery_direction = 'A' if self.recovery_attempts % 2 else 'D'
                    self.recovery_started, self.phase = at, 'recovering'
                    owner, reason, keys, dx = 'hybrid-native', 'obstacleRetreat', ['S'], 0
                    self.events.append(dict(type='hybridObstacleRecovery', atMs=at,
                        attempt=self.recovery_attempts, movementMs=movement, displacement=displacement))
                self.progress_anchor = (at, pose['x'], pose['y'])
        elif self.phase == 'walking':
            self.progress_anchor = None
        self.selections[reason] += 1
        step = dict(durationMs=100, keys=keys, mouseDx=dx, mouseDy=0)
        return dict(owner=owner, reason=reason, target=self.target_name, pose=copy.deepcopy(pose),
                    completedLegs=self.legs, modelSteps=copy.deepcopy(proposal.get('steps', [])), step=step)
