"""One input owner combining native courtyard localization with GPU policy proposals.

The fixed route is a repeatable qualification task, not general navigation.
Native poses and receipts establish progress; accepted commands alone do not.
"""
from collections import Counter, deque
import copy
import math

from observation_timing import observation_timestamp
from hybrid_bypass import HybridBypass
from hybrid_routes import (COURTYARD_ROUTE, PATROL_SEGMENTS, PATROL_STATIONS, STREET_PATROL_ROUTE,
                           camera_correction, patrol_leg, route_heading, route_points)


PROFILE = COURTYARD_ROUTE
START, END = route_points(COURTYARD_ROUTE)


def yaw_error(a, b):
    """Return the unsigned shortest heading difference."""
    return abs((a - b + 180) % 360 - 180)


class HybridNavigation:
    """Serial planner; the existing bridge remains the sole input/freshness owner."""

    def __init__(self, capability, route_id=COURTYARD_ROUTE, remember_bypass=False):
        expected = dict(version=1, profileId=PROFILE, sameFrame=True, readOnly=True)
        if any(capability.get(k) != v for k, v in expected.items()):
            raise ValueError('The bridge does not advertise same-frame hybrid navigation')
        if tuple(capability.get('start', {}).get(k) for k in ('x', 'y')) != START or tuple(
                capability.get('end', {}).get(k) for k in ('x', 'y')) != END:
            raise ValueError('The fixed courtyard geometry differs')
        self.route_id = route_id
        self.start, self.end = route_points(route_id)
        self.bypass = HybridBypass(route_id) if remember_bypass else None
        self.phase = 'admitting'
        self.target = self.end
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
        self.stall_samples = deque(maxlen=128)
        self.recovery_attempts = 0
        self.total_recoveries = 0
        self.recovery_started = None
        self.first_recovery_side = 'A'
        self.recovery_direction = None
        self.sidestep_origin = None
        self.recovery_commands = 0
        self.last_pose = None
        self.last_at = None
        self.pending_climb_exit = None
        self.leg_started = None
        self.failure = None
        self.segment = {}
        self.arrival_frame = self.arrival_epoch = self.release_epoch = None
        if route_id == STREET_PATROL_ROUTE:
            self._set_patrol_leg()

    def _set_patrol_leg(self):
        """Update all corridor and steering geometry together, after the preceding station verifies."""
        origin, destination = patrol_leg(self.legs)
        self.start, self.end = PATROL_STATIONS[origin], PATROL_STATIONS[destination]
        self.target_name, self.target = destination, self.end
        self.segment = dict(fromStation=origin, toStation=destination, segmentIndex=self.legs % len(PATROL_SEGMENTS),
                            circuit=self.legs // len(PATROL_SEGMENTS) + 1)

    def snapshot(self):
        """Return scalar progress without exposing mutable internal collections."""
        result = dict(profileId=PROFILE, routeId=self.route_id, rememberBypass=self.bypass is not None,
                    phase=self.phase, target=self.target_name,
                    completedLegs=self.legs, selections=dict(self.selections),
                    recoveryAttempts=self.total_recoveries, failure=self.failure,
                    lastPose=copy.deepcopy(self.last_pose))
        if self.segment:
            result.update(completedCircuits=self.legs // len(PATROL_SEGMENTS), **self.segment)
        return result

    def drain_events(self):
        """Transfer sparse verified endpoint/recovery events to the evidence writer."""
        events, self.events = self.events, []
        return events

    def recovery_side(self, target, attempt):
        """Use the open pavement on surveyed street routes in both directions."""
        if self.segment:
            # Preserve the surveyed road side on B-C and reverse the strafe on the return.
            return 'A' if target == 'sidewalk-junction' else 'D'
        if self.route_id != COURTYARD_ROUTE:
            return 'A' if target == 'end' else 'D'
        return self.first_recovery_side if attempt == 1 else {'A': 'D', 'D': 'A'}[self.first_recovery_side]

    @staticmethod
    def latest_pose_usable(frame):
        """A newer unavailable pose or climb hint must invalidate an older proposed correction."""
        pose, motion = frame.get('navigationPose') or {}, frame.get('motionEvidence') or {}
        return (pose.get('state') == 'valid' and pose.get('frameId') == frame.get('frameId')
                and motion.get('status') == 'normal' and motion.get('spaceKeyMatched') is False)

    def interrupt(self, reason):
        """Require fresh confirmation after interruption without inventing completed legs."""
        self.samples.clear()
        self.stall_samples.clear()
        if self.bypass and not (reason == 'hybridStalePose' and self.bypass.suspend_stale(self)):
            self.bypass.invalidate(self, reason)
        # hold() releases input. A temporary pose gap must not skip an in-flight
        # escape and aim straight back at contact. Keep its confirmed work and
        # original deadline; only a fresh qualified pose can advance the stage.
        if self.phase != 'recovering':
            self.movements.clear()
        if self.phase == 'releaseRequired':
            self.phase = 'walking' if self.leg_started is not None else 'admitting'
        if self.phase != 'verifying':
            self.release_at = None

    def receipt(self, receipt):
        """Retain exact terminal holds; chorded or off-axis actions cannot count as walking."""
        identity = receipt.get('requestId')
        if not identity or identity in self.receipt_ids:
            return
        self.receipt_ids.append(identity)
        if self.bypass:
            self.bypass.recent_receipts.append(receipt)
        steps = receipt.get('appliedSteps', [])
        for i, step in enumerate(steps):
            keys = step.get('keys', [])
            begin = step['startedAtMs']
            end = steps[i + 1]['startedAtMs'] if i + 1 < len(steps) else receipt['endedAtMs']
            if end > begin and len(keys) == 1 and keys[0] in ('W', 'A', 'S', 'D'):
                if step.get('mouseDy', 0) == 0 and abs(step.get('mouseDx', 0)) <= (3 if keys == ['W'] else 0):
                    self.movements.append((begin, end, keys[0]))

    def _held_ms(self, key, since, until):
        """Count the union of confirmed intervals inside the source-clock window."""
        total, cursor = 0, since
        for begin, end, _ in sorted(row for row in self.movements if row[2] == key and row[1] > since):
            if begin >= until:
                break
            total += max(0, min(end, until) - max(cursor, begin))
            cursor = max(cursor, end)
        return total

    def _stalled(self, frame, pose, at):
        """Require two contiguous seconds of aligned, stationary decision observations."""
        point = (pose['x'], pose['y'])
        stamp = frame['sourceFrame'].get('timestamp100ns')
        samples = self.stall_samples
        if (type(stamp) is not int or samples and
                (at <= samples[-1][0] or stamp <= samples[-1][1] or pose['frameId'] <= samples[-1][2])):
            samples.clear()
            return False
        if samples and at - samples[-1][0] > 250:
            samples.clear()
        # Drop earlier movement while keeping the most recent continuous cluster.
        while len(samples) >= 2 and samples[1][0] <= at - 2000:
            samples.popleft()
        while any(math.dist(old[3], point) > .5 or yaw_error(old[4], pose['yawDegrees']) > 5 for old in samples):
            samples.popleft()
        samples.append((at, stamp, pose['frameId'], point, pose['yawDegrees']))
        if at - samples[0][0] < 2000:
            return False
        movement = self._held_ms('W', at - 2000, at)
        if movement < 600:
            return False
        self._begin_recovery('stationaryForward')
        self.recovery_commands = 1  # The triggering decision proposes the first S.
        self.events.append(dict(type='hybridObstacleRecovery', atMs=at, frameId=pose['frameId'],
                                attempt=self.recovery_attempts, movementMs=movement,
                                displacement=max(math.dist(old[3], point) for old in samples)))
        samples.clear()
        return True

    def latch_climb_exit(self, evidence):
        """Reserve the next qualified decision for escape after an applied X and confirmed normal exit."""
        if self.phase not in ('walking', 'recovering') or self.leg_started is None:
            return
        if (evidence['sourceEpoch'] != self.source_epoch or self.last_pose is None
                or evidence['resumeFrameId'] <= self.last_pose['frameId']):
            self._fail('climb_exit_source_mismatch')
        self.pending_climb_exit = dict(climbExit=copy.deepcopy(evidence), preClimbFrameId=self.last_pose['frameId'])
        self.phase = 'awaitingClimbPose'

    def _begin_recovery(self, trigger_kind):
        """Share the finite retreat and sidestep budget across distinct obstacle triggers."""
        if self.recovery_attempts >= 2:
            self._fail('obstacle_recovery_exhausted')
        self.recovery_attempts += 1
        self.total_recoveries += 1
        self.recovery_direction = self.recovery_side(self.target_name, self.recovery_attempts)
        self.recovery_started, self.phase = self.last_at, 'recovering'
        self.sidestep_origin = None
        self.recovery_commands = 0
        if self.bypass:
            self.bypass.stalled(self, trigger_kind)

    def _recovery_step(self, pose, at):
        """Retreat and move laterally clear before re-aiming. Deadlines only stop input."""
        if at - self.recovery_started > 3500:
            self._fail('obstacle_recovery_deadline')
        if self.sidestep_origin is None:
            if self._held_ms('S', self.recovery_started, at) < 200:
                # Missing/delayed receipts can hide already dispatched movement.
                # Cap proposed holds as well as confirmed time, even under load.
                if self.recovery_commands >= 4:
                    return 'obstacleAwaitReceipt', []
                self.recovery_commands += 1
                return 'obstacleRetreat', ['S']
            self.sidestep_origin = (at, pose['x'], pose['y'], math.radians(pose['yawDegrees']))
            if self.bypass:
                self.bypass.recovery_point(self, 0)
            self.recovery_commands = 0
        since, x, y, yaw = self.sidestep_origin
        side_ms = self._held_ms(self.recovery_direction, since, at)
        # Map axes are the negatives of image axes. Project A/D displacement
        # perpendicular to the camera heading captured when sidestepping began.
        right = (pose['x'] - x) * math.sin(yaw) - (pose['y'] - y) * math.cos(yaw)
        clearance = right if self.recovery_direction == 'D' else -right
        if side_ms >= 200 and clearance >= 1.5:
            if self.bypass:
                self.bypass.recovery_point(self, 1)
            self.phase = 'walking'
            self.stall_samples.clear()
            return None
        if side_ms >= 850:
            self._fail('obstacle_lateral_clearance_unverified')
        if self.recovery_commands >= 11:
            return 'obstacleAwaitReceipt', []
        self.recovery_commands += 1
        return 'obstacleSidestep', [self.recovery_direction]

    def released(self, response):
        """Endpoint samples must follow an acknowledged release and its response barrier."""
        stamp = response.get('serverNowMs')
        if response.get('type') != 'released' or type(stamp) not in (int, float) or not math.isfinite(stamp):
            raise RuntimeError('Hybrid endpoint release was not acknowledged')
        # The existing bridge stamps serverNowMs after releasing and snapshotting
        # its readiness gate; releasedAtMs is an evidence-event field, not wire data.
        if self.bypass:
            self.bypass.released(self, response)
        if self.segment:
            gate = response.get('worldReadiness') or {}
            epoch = gate.get('epoch')
            if (self.phase != 'releaseRequired' or type(self.arrival_epoch) is not int or type(epoch) is not int
                    or epoch != self.arrival_epoch + 1 or gate.get('ready') is not False
                    or gate.get('reason') != 'client_release'
                    or (gate.get('sourceFrame') or {}).get('captureEpoch') != self.source_epoch):
                self._fail('patrol_release_unbound')
            self.release_epoch = epoch
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
        if self.bypass:
            self.bypass.invalidate(self, reason)
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
        at = observation_timestamp(frame)
        if self.pending_climb_exit:
            exit_proof = self.pending_climb_exit['climbExit']
            if (pose['frameId'] <= exit_proof['resumeFrameId'] or at <= exit_proof['resumeAtMs']
                    or source.get('timestamp100ns', 0) <= exit_proof['resumeSourceId']):
                return 'waitingAfterClimbResume'
            if (frame.get('frameWorldReadiness') or {}).get('epoch') != exit_proof['resumeWorldEpoch']:
                self._fail('climb_resume_world_epoch_changed')
        if self.last_frame_id is not None and pose['frameId'] <= self.last_frame_id:
            return 'duplicatePose'
        self.last_frame_id = pose['frameId']
        if self.last_at is not None and at <= self.last_at:
            if self.bypass:
                self.bypass.invalidate(self, 'sourceNotIncreasing')
            return 'sourceNotIncreasing'
        self.last_at, self.last_pose = at, copy.deepcopy(pose)
        x, y = pose['x'], pose['y']
        length = math.dist(self.start, self.end)
        dx, dy = self.end[0] - self.start[0], self.end[1] - self.start[1]
        offset_x, offset_y = x - self.start[0], y - self.start[1]
        projection = (offset_x * dx + offset_y * dy) / length
        cross = abs(offset_x * dy - offset_y * dx) / length
        if cross > 4 or projection < -3 or projection > length + 3:
            self._fail('outside_fixed_' + self.route_id.split('-')[1] + '_corridor')
        if self.route_id != COURTYARD_ROUTE:
            # Native bearings are integer-truncated in the image plane. A mismatch
            # far from an anchor means this map's axes cannot guide the new route.
            for anchor, key in ((START, 'headingToStartDegrees'), (END, 'headingToEndDegrees')):
                if math.dist((x, y), anchor) > 2 and yaw_error(route_heading(pose, anchor), pose[key]) > 1.1:
                    self._fail('native_bearing_mismatch')
        if self.phase == 'admitting':
            allowed_starts = (self.start,) if self.segment else (self.start, self.end)
            near = min(math.hypot(x - p[0], y - p[1]) for p in allowed_starts)
            if near > 2:
                self._fail('verified_endpoint_start_required')
            if not self._sample(pose, at):
                return 'confirmingStart'
            admission = {}
            if self.segment:
                admission = dict(sourceEpoch=epoch, station=self.segment['fromStation'],
                                 samples=copy.deepcopy(self.samples), **self.segment)
            else:
                self.target_name = 'end' if math.hypot(x - self.start[0], y - self.start[1]) <= 2 else 'start'
                self.target = self.end if self.target_name == 'end' else self.start
            self.phase = 'walking'
            self.leg_started = at
            self.samples.clear()
            self.events.append(dict(type='hybridStartVerified', routeId=self.route_id,
                                    frameId=pose['frameId'], atMs=at, target=self.target_name, **admission))
        if at - self.leg_started > 35000:
            self._fail('leg_progress_deadline')
        if self.bypass:
            if self.bypass.suspension:
                self.bypass.rebind(self, frame)
                return 'confirmingBypassReentry'
            self.bypass.observe(self, frame)
        if self.pending_climb_exit:
            # The same source, world, normal-motion and corridor checks now cover
            # this fresh post-drop position. Dispatch recovery before another W.
            self._begin_recovery('climbDrop')
            self.events.append(dict(type='hybridClimbRecovery', routeId=self.route_id, sourceEpoch=epoch,
                frameId=pose['frameId'], atMs=at, attempt=self.recovery_attempts, completedLegs=self.legs,
                target=self.target_name, **self.pending_climb_exit))
            self.pending_climb_exit = None
            return None
        distance = math.hypot(x - self.target[0], y - self.target[1])
        if self.phase == 'verifying':
            if at < self.release_at + 80:
                return 'waitingAfterRelease'
            if self.segment:
                gate = frame.get('frameWorldReadiness') or {}
                if (gate.get('epoch') != self.release_epoch or gate.get('ready') is not True
                        or (gate.get('sourceFrame') or {}).get('captureEpoch') != epoch):
                    self._fail('patrol_endpoint_readiness_changed')
            if distance > 2:
                self._fail('endpoint_moved_after_release')
            if not self._sample(pose, at):
                return 'verifyingEndpoint'
            self.legs += 1
            self.events.append(dict(type='hybridEndpointVerified', completedLegs=self.legs,
                endpoint=self.target_name, sourceEpoch=epoch, releaseAtMs=self.release_at,
                samples=copy.deepcopy(self.samples), legElapsedMs=at - self.leg_started))
            if self.bypass:
                if self.bypass.release_epoch is not None:
                    self.events[-1]['releaseEpoch'] = self.bypass.release_epoch
                self.bypass.endpoint(self)
            if self.segment:
                self.events[-1].update(routeId=self.route_id, station=self.target_name, arrivalFrameId=self.arrival_frame,
                                       releaseEpoch=self.release_epoch, **self.segment)
                if self.legs % len(PATROL_SEGMENTS) == 0:
                    self.events.append(dict(type='hybridCircuitVerified', routeId=self.route_id, sourceEpoch=epoch,
                        atMs=at, frameId=pose['frameId'], station=self.target_name, completedLegs=self.legs,
                        completedCircuits=self.legs // len(PATROL_SEGMENTS)))
                self._set_patrol_leg()
            else:
                self.target_name = 'start' if self.target_name == 'end' else 'end'
                self.target = self.start if self.target_name == 'start' else self.end
            self.phase, self.leg_started = 'walking', at
            self.samples.clear()
            self.stall_samples.clear()
            self.recovery_attempts = 0
            self.movements.clear()
            return 'endpointVerified'
        if distance <= 1.1 and (not self.bypass or self.bypass.waypoint is None):
            if self.segment:
                self.arrival_frame = pose['frameId']
                self.arrival_epoch = (frame.get('frameWorldReadiness') or {}).get('epoch')
            self.phase = 'releaseRequired'
            return 'releaseRequired'
        return None

    def choose(self, frame, proposal):
        """Accept route-compatible model walking; otherwise use measured native correction."""
        if self.bypass and self.bypass.suspension:
            raise RuntimeError('A suspended bypass cannot select an input before re-entry confirmation')
        pose, at = self.last_pose, self.last_at
        waypoint = self.bypass.waypoint if self.bypass else None
        steering = waypoint or self.target
        point_index = self.bypass.index if waypoint else None
        if self.route_id == COURTYARD_ROUTE:
            heading = pose['headingToStartDegrees' if self.target_name == 'start' else 'headingToEndDegrees']
            correction = pose['mouseToStart' if self.target_name == 'start' else 'mouseToEnd']
        else:
            heading = route_heading(pose, steering)
            correction = camera_correction(pose['yawDegrees'], heading)
        error = yaw_error(pose['yawDegrees'], heading)
        owner, reason, keys, dx = 'hybrid-native', 'nativeHeading', [], max(-350, min(350, int(correction)))
        if self.phase == 'recovering':
            recovery = self._recovery_step(pose, at)
            if recovery:
                reason, keys = recovery
                dx = 0
        if self.phase == 'walking' and error <= 5:
            dx, keys, reason = 0, ['W'], 'modelIdleOrOffRoute'
            steps = proposal.get('steps', [])
            if (proposal.get('parseValid') and len(steps) == 1 and set(steps[0].get('keys', [])) == {'W'}
                    and abs(steps[0].get('mouseDx', 0)) <= 3 and steps[0].get('mouseDy', 0) == 0):
                owner, reason = 'open-p2p', 'modelRouteCompatible'
                dx = steps[0].get('mouseDx', 0)
            if self._stalled(frame, pose, at):
                owner, reason, keys, dx = 'hybrid-native', 'obstacleRetreat', ['S'], 0
        elif self.phase == 'walking':
            self.stall_samples.clear()
        self.selections[reason] += 1
        step = dict(durationMs=100, keys=keys, mouseDx=dx, mouseDy=0)
        selection = dict(owner=owner, reason=reason, target=self.target_name, pose=copy.deepcopy(pose),
                         completedLegs=self.legs, modelSteps=copy.deepcopy(proposal.get('steps', [])), step=step, **self.segment)
        if self.bypass:
            selection['steeringPoint'] = dict(x=steering[0], y=steering[1], kind='bypass' if waypoint else 'endpoint')
            if waypoint:
                selection['bypassPointIndex'] = point_index
        return selection
