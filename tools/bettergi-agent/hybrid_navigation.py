"""One input owner combining native courtyard localization with GPU policy proposals.

The fixed route is a repeatable qualification task, not general navigation.
Native poses and receipts establish progress; accepted commands alone do not.
"""
from collections import Counter, deque
import copy
import math
import time

from observation_timing import observation_timestamp
from hybrid_bypass import HybridBypass
from hybrid_routes import (COURTYARD_ROUTE, PATROL_SEGMENTS, PATROL_STATIONS, STREET_PATROL_ROUTE, SURVEY_ROUTES,
                           camera_correction, itinerary_legs, patrol_leg, route_heading, route_points, station_path)


PROFILE = COURTYARD_ROUTE
START, END = route_points(COURTYARD_ROUTE)
from navigation_profiles import validate_capability,allows_pose_scope,required_profile


def yaw_error(a, b):
    """Return the unsigned shortest heading difference."""
    return abs((a - b + 180) % 360 - 180)


def rejected_release_record(reply):
    """Retain the exact gate and the native software-release telemetry from a raced acknowledgement."""
    ctx = reply.get('executionContext') or {}
    return dict(rejectedReadiness=copy.deepcopy(reply.get('worldReadiness')),
                rejectedExecution={k:copy.deepcopy(ctx[k]) for k in
                    ('sampledAtMs','telemetryComplete','trackedState','active','lastInputEvent') if k in ctx})


class HybridNavigation:
    """Serial planner; the existing bridge remains the sole input/freshness owner."""

    def __init__(self, capability, route_id=COURTYARD_ROUTE, remember_bypass=False, *,
                 itinerary_destinations=None, itinerary_start='stair-front', stationary_photo_retries=False,
                 navigation_profile=PROFILE):
        validate_capability(capability,navigation_profile)
        if required_profile(route_id)!=navigation_profile:
            raise ValueError('Fixed route and explicit navigation profile differ')
        self.navigation_profile=navigation_profile
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
        # Bound admission and every walking leg even when source observations stop qualifying.
        self.leg_deadline_ns = time.perf_counter_ns() + 35_000_000_000
        self.failure = None
        self.segment = {}
        self.arrival_frame = self.arrival_epoch = self.release_epoch = None
        self.arrival_source_stamp = None
        self.release_retry = None
        self.destinations = ()
        self.completed_destinations = 0
        self.stationary_photo_retries = stationary_photo_retries
        self.photo_hold = None
        self.photo_resume_after = None
        if stationary_photo_retries and itinerary_destinations is None:
            raise ValueError('Stationary destination photos require a directed itinerary')
        if itinerary_destinations is not None:
            if route_id != STREET_PATROL_ROUTE or remember_bypass:
                raise ValueError('An itinerary requires the surveyed street route')
            # Validate all requests before admitting any input. Compute each live hop from its proven origin below.
            itinerary_legs(itinerary_start, itinerary_destinations)
            self.destinations = tuple(itinerary_destinations)
        if route_id == STREET_PATROL_ROUTE:
            self._set_patrol_leg(itinerary_start)

    def _set_patrol_leg(self, origin):
        """Update all corridor and steering geometry together, after the preceding station verifies."""
        if self.destinations:
            requested = self.destinations[self.completed_destinations]
            destination = station_path(origin, requested)[0]
            metadata = dict(navigationMode='itinerary', segmentIndex=self.legs,
                            destinationOrdinal=self.completed_destinations + 1, requestedDestination=requested)
        else:
            origin, destination = patrol_leg(self.legs)
            metadata = dict(segmentIndex=self.legs % len(PATROL_SEGMENTS), circuit=self.legs // len(PATROL_SEGMENTS) + 1)
        self.start, self.end = PATROL_STATIONS[origin], PATROL_STATIONS[destination]
        self.target_name, self.target = destination, self.end
        self.segment = dict(fromStation=origin, toStation=destination, **metadata)

    def snapshot(self):
        """Return scalar progress without exposing mutable internal collections."""
        result = dict(profileId=self.navigation_profile, routeId=self.route_id, rememberBypass=self.bypass is not None,
                    phase=self.phase, target=self.target_name,
                    completedLegs=self.legs, selections=dict(self.selections),
                    recoveryAttempts=self.total_recoveries, failure=self.failure,
                    lastPose=copy.deepcopy(self.last_pose))
        if self.destinations:
            result.update(completedDestinations=self.completed_destinations, **self.segment)
        elif self.segment:
            result.update(completedCircuits=self.legs // len(PATROL_SEGMENTS), **self.segment)
        return result

    def drain_events(self):
        """Transfer sparse verified endpoint/recovery events to the evidence writer."""
        events, self.events = self.events, []
        return events

    def retry_destination_photo(self):
        """After a classified miss, admit one more read-only attempt within the original release."""
        if self.phase != 'destinationPhotoDecision' or self.photo_hold is None:
            self._fail('destination_photo_result_unbound')
        if self.photo_hold['retryOrdinal'] >= 3:
            self._fail('destination_photo_attempts_exhausted')
        self.photo_hold['retryOrdinal'] += 1
        self.phase = 'awaitingDestinationPhoto'

    def finish_destination_photo(self, *, await_batch=False):
        """Let the warm owner advance only after the original or retried photo qualifies."""
        if self.phase != 'destinationPhotoDecision' or self.photo_hold is None:
            self._fail('destination_photo_result_unbound')
        if await_batch:
            if self.completed_destinations != len(self.destinations):
                self._fail('destination_batch_boundary_unbound')
            self.phase = 'awaitingDestinationBatch'
            return
        self.photo_hold = None
        self.photo_resume_after = self.last_frame_id
        if self.completed_destinations == len(self.destinations):
            self.phase = 'complete'
        else:
            self._set_patrol_leg(self.target_name)
            self.phase = 'walking'

    def finish_destination_queue(self):
        """Close an explicitly finished queue at its existing released endpoint without advancing another leg."""
        if self.phase != 'awaitingDestinationBatch' or not self.photo_hold or self.completed_destinations != len(self.destinations):
            self._fail('destination_batch_boundary_unbound')
        self.photo_hold = None
        self.phase = 'complete'

    def append_destination_batch(self, destinations):
        """Continue from the same released station after the resident authenticates new requests."""
        if self.phase != 'awaitingDestinationBatch' or not self.photo_hold:
            self._fail('destination_batch_boundary_unbound')
        itinerary_legs(self.target_name, destinations)
        self.destinations += tuple(destinations)
        self.photo_hold = None
        self.photo_resume_after = self.last_frame_id
        self._set_patrol_leg(self.target_name)
        # The verified endpoint already started this leg's clock. Keep waiting for the
        # batch or a qualified photo inside that budget, and require a newer input frame.
        self.phase = 'walking'

    def _observe_destination_photo(self, frame, pose, at, distance):
        """Stay within the released endpoint across every fresh sample, including earlier attempts."""
        hold, source = self.photo_hold, frame['sourceFrame']
        gate = frame.get('frameWorldReadiness') or {}
        stamp = source.get('timestamp100ns')
        if (self.phase not in ('awaitingDestinationPhoto', 'awaitingDestinationBatch')
                or type(stamp) is not int or stamp <= hold['lastStamp']
                or type(gate.get('epoch')) is not int or gate['epoch'] != self.release_epoch
                or gate.get('ready') is not True or gate.get('sourceFrameId') != pose['frameId']
                or gate.get('sourceFrame') != source):
            self._fail('destination_photo_source_or_release_changed')
        hold['lastStamp'] = stamp
        samples = hold['samples']
        if distance > 2 or any(math.hypot(pose['x'] - old['x'], pose['y'] - old['y']) > 1.5
                               or yaw_error(pose['yawDegrees'], old['yawDegrees']) > 3 for old in samples):
            self._fail('destination_photo_pose_moved')
        if self.phase == 'awaitingDestinationBatch':
            return 'batchEndpointStillVerified'
        if at - samples[-1]['atMs'] < 80:
            return 'waitingForDestinationPhoto'
        samples.append(dict(frameId=pose['frameId'], atMs=at, x=pose['x'], y=pose['y'], yawDegrees=pose['yawDegrees']))
        if len(samples) % 3:
            return 'waitingForDestinationPhoto'
        self.events.append(dict(type='hybridDestinationPhotoRetry', routeId=self.route_id, sourceEpoch=self.source_epoch,
            station=self.target_name, completedLegs=self.legs, releaseEpoch=self.release_epoch, releaseAtMs=self.release_at,
            arrivalFrameId=self.arrival_frame, initialEndpointFrameId=samples[2]['frameId'], retryOrdinal=hold['retryOrdinal'],
            atMs=at, frameId=pose['frameId'], samples=copy.deepcopy(samples[-3:]), **self.segment))
        self.phase = 'destinationPhotoDecision'
        return 'destinationPhotoRetry'

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
        if self.photo_hold is not None:
            self._fail('destination_photo_interrupted')
        if self.phase == 'awaitingEndpointReleaseRetry':
            self._fail('endpoint_release_retry_interrupted')
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
        if self.route_id in SURVEY_ROUTES:
            self._fail('survey_obstacle_requires_inspection')
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
                    or (gate.get('sourceFrame') or {}).get('captureEpoch') != self.source_epoch):
                self._fail('patrol_release_unbound')
            if (gate.get('reason') == 'world_observation_invalidated' and self.stationary_photo_retries
                    and self.release_retry is None):
                evidence = rejected_release_record(response)
                ctx = evidence['rejectedExecution']
                state, last = ctx.get('trackedState') or {}, ctx.get('lastInputEvent') or {}
                call = last.get('call') or {}
                if (type(self.arrival_source_stamp) is not int or ctx.get('telemetryComplete') is not True
                        or 'active' not in ctx or ctx['active'] is not None
                        or state.get('heldKeys') != [] or state.get('telemetryIncomplete') is not False
                        or state.get('releaseOutcome') != 'returned_unverified' or last.get('origin') != 'release:client_release'
                        or call.get('operation') != 'releaseAll' or call.get('stage') != 'returned_unverified'
                        or call.get('error') is not None or type(last.get('atMs')) not in (int,float)
                        or type(ctx.get('sampledAtMs')) not in (int,float)
                        or not self.last_at <= last['atMs'] <= ctx['sampledAtMs'] <= stamp+.001):
                    self._fail('patrol_release_unbound')
                record = dict(routeId=self.route_id, station=self.target_name, sourceEpoch=self.source_epoch,
                              firstArrivalFrameId=self.arrival_frame, arrivalEpoch=self.arrival_epoch, rejectedAtMs=stamp,
                              completedLegs=self.legs, **self.segment)
                self.events.append(dict(type='hybridEndpointReleaseRejected', **record, **evidence))
                self.release_retry = dict(record=record, epoch=epoch, samples=[], pose=self.last_pose,
                                          deadlineNs=time.perf_counter_ns()+650_000_000, lastStamp=self.arrival_source_stamp)
                self.phase = 'awaitingEndpointReleaseRetry'
                return
            if gate.get('reason') != 'client_release':
                self._fail('patrol_release_unbound')
            if self.release_retry and (stamp - self.release_retry['record']['rejectedAtMs'] > 650
                                       or time.perf_counter_ns() > self.release_retry['deadlineNs']):
                self._fail('endpoint_release_retry_deadline')
            self.release_epoch = epoch
        self.release_at = stamp
        self.phase = 'verifying'
        self.samples.clear()

    def permit_release_reconfirmation(self, gate):
        """Ignore ordinary reconfirmation only in the exact raced generation while control stays held."""
        return (self.phase == 'awaitingEndpointReleaseRetry' and gate.get('epoch') == self.release_retry['epoch']
                and (gate.get('sourceFrame') or {}).get('captureEpoch') == self.source_epoch
                and gate.get('reason') in ('world_observation_invalidated','world_confirming','world_ready'))

    def check_leg_deadline(self):
        """Expire on the client clock even in no-frame, pose-loss, paused and recovery wait paths."""
        now = time.perf_counter_ns()
        if self.phase != 'complete' and now > self.leg_deadline_ns:
            self.events.append(dict(type='hybridDeadlineExceeded', phase=self.phase, atClientNs=now,
                deadlineClientNs=self.leg_deadline_ns, deadlineSeconds=35,
                elapsedSeconds=(now-self.leg_deadline_ns)/1e9+35))
            self._fail('admission_pose_deadline' if self.leg_started is None else 'leg_progress_deadline')

    def _start_leg_clock(self, at):
        """Start both clocks at admission or a verified endpoint; interruptions never renew either."""
        self.leg_started = at
        self.leg_deadline_ns = time.perf_counter_ns() + 35_000_000_000

    def check_release_retry_time(self):
        """No missing capture or blocked poll may prolong the reacknowledgement window."""
        if self.phase == 'awaitingEndpointReleaseRetry' and time.perf_counter_ns() > self.release_retry['deadlineNs']:
            self._fail('endpoint_release_retry_deadline')

    def _prepare_release_retry(self, frame, pose, at, distance):
        """Require two independent post-refusal ready views of the original stationary arrival before one reissue."""
        retry, source = self.release_retry, frame['sourceFrame']
        gate, original = frame.get('frameWorldReadiness') or {}, retry['pose']
        stamp, samples = source.get('timestamp100ns'), retry['samples']
        if at <= retry['record']['rejectedAtMs']:
            return 'waitingForEndpointReleaseRetry'
        if (distance > 1.1 or math.hypot(pose['x']-original['x'],pose['y']-original['y']) > 1.5
                or yaw_error(pose['yawDegrees'],original['yawDegrees']) > 3 or frame.get('inputAvailable') is not True
                or not self.permit_release_reconfirmation(gate) or gate.get('ready') is not True
                or gate.get('sourceFrameId') != frame['frameId'] or gate.get('sourceFrame') != source or type(stamp) is not int):
            self._fail('endpoint_release_retry_source_or_pose_changed')
        if at - retry['record']['rejectedAtMs'] > 650:
            self._fail('endpoint_release_retry_deadline')
        if stamp <= retry['lastStamp']:
            self._fail('endpoint_release_retry_source_not_increasing')
        retry['lastStamp'] = stamp
        if any(math.hypot(pose['x']-s['x'],pose['y']-s['y']) > 1.5
               or yaw_error(pose['yawDegrees'],s['yawDegrees']) > 3 for s in samples):
            self._fail('endpoint_release_retry_source_or_pose_changed')
        if not samples or at - samples[-1]['atMs'] >= 80:
            samples.append(dict(frameId=pose['frameId'], atMs=at, x=pose['x'], y=pose['y'], yawDegrees=pose['yawDegrees']))
        if len(samples) < 2:
            return 'waitingForEndpointReleaseRetry'
        self.events.append(dict(type='hybridEndpointReleaseRetryReady', **retry['record'],
                                retryArrivalFrameId=pose['frameId'], samples=copy.deepcopy(samples)))
        self.arrival_frame, self.arrival_epoch = pose['frameId'], retry['epoch']
        self.phase = 'releaseRequired'
        return 'retryReleaseRequired'

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
        if self.phase == 'complete':
            return 'itineraryComplete'
        self.check_leg_deadline()
        self.check_release_retry_time()
        if self.photo_hold is not None:
            if self.phase == 'awaitingDestinationBatch':
                if observation_timestamp(frame) - self.photo_hold['samples'][-1]['atMs'] > 1000:
                    self._fail('destination_batch_deadline')
            elif observation_timestamp(frame) - self.photo_hold['samples'][2]['atMs'] > 1500:
                self._fail('destination_photo_deadline')
            if not self.latest_pose_usable(frame):
                self._fail('destination_photo_pose_unavailable')
        pose = frame.get('navigationPose') or {}
        if pose.get('state') != 'valid' or pose.get('frameId') != frame.get('frameId'):
            return 'poseUnavailable'
        fields = ('x', 'y', 'yawDegrees', 'positionConfidence', 'yawConfidence',
                  'headingToStartDegrees', 'headingToEndDegrees', 'mouseToStart', 'mouseToEnd')
        if any(type(pose.get(k)) not in (int, float) or not math.isfinite(pose[k]) for k in fields):
            self._fail('invalid_pose_numbers')
        if (not allows_pose_scope(pose,self.navigation_profile) or not .99 <= pose['positionConfidence'] <= 1
                or not .2 <= pose['yawConfidence'] <= 1 or not 0 <= pose['yawDegrees'] < 360):
            if self.photo_hold is not None:
                self._fail('destination_photo_pose_unqualified')
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
            if self.phase == 'awaitingEndpointReleaseRetry':
                return 'waitingForEndpointReleaseRetry'
            return 'waitingForDestinationPhoto' if self.photo_hold is not None else 'duplicatePose'
        self.last_frame_id = pose['frameId']
        if self.last_at is not None and at <= self.last_at:
            if self.photo_hold is not None:
                self._fail('destination_photo_source_not_increasing')
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
            admission = dict(sourceEpoch=epoch, samples=copy.deepcopy(self.samples))
            if self.segment:
                admission.update(station=self.segment['fromStation'], **self.segment)
            else:
                self.target_name = 'end' if math.hypot(x - self.start[0], y - self.start[1]) <= 2 else 'start'
                self.target = self.end if self.target_name == 'end' else self.start
            self.phase = 'walking'
            self._start_leg_clock(at)
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
        if self.phase == 'awaitingEndpointReleaseRetry':
            return self._prepare_release_retry(frame, pose, at, distance)
        if self.photo_hold is not None:
            return self._observe_destination_photo(frame, pose, at, distance)
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
            finished = False
            if self.segment:
                self.events[-1].update(routeId=self.route_id, station=self.target_name, arrivalFrameId=self.arrival_frame,
                                       releaseEpoch=self.release_epoch, **self.segment)
                if self.release_retry is not None:
                    self.events[-1]['firstArrivalFrameId'] = self.release_retry['record']['firstArrivalFrameId']
                    self.release_retry = None
                if self.destinations:
                    if self.target_name == self.segment['requestedDestination']:
                        self.completed_destinations += 1
                        self.events.append(dict(type='hybridDestinationVerified', routeId=self.route_id, sourceEpoch=epoch,
                            atMs=at, frameId=pose['frameId'], station=self.target_name, completedLegs=self.legs, **self.segment))
                        if self.stationary_photo_retries:
                            stamp = source.get('timestamp100ns')
                            if type(stamp) is not int:
                                self._fail('destination_photo_source_missing')
                            self.photo_hold = dict(retryOrdinal=0, lastStamp=stamp, samples=copy.deepcopy(self.samples))
                    finished = self.completed_destinations == len(self.destinations)
                elif self.legs % len(PATROL_SEGMENTS) == 0:
                    self.events.append(dict(type='hybridCircuitVerified', routeId=self.route_id, sourceEpoch=epoch,
                        atMs=at, frameId=pose['frameId'], station=self.target_name, completedLegs=self.legs,
                        completedCircuits=self.legs // len(PATROL_SEGMENTS)))
                if not finished and self.photo_hold is None:
                    self._set_patrol_leg(self.target_name)
            else:
                self.target_name = 'start' if self.target_name == 'end' else 'end'
                self.target = self.start if self.target_name == 'start' else self.end
            self.phase = 'complete' if finished else 'walking'
            self._start_leg_clock(at)
            if self.photo_hold is not None:
                self.phase = 'destinationPhotoDecision'
            self.samples.clear()
            self.stall_samples.clear()
            self.recovery_attempts = 0
            self.movements.clear()
            return 'endpointVerified'
        if distance <= 1.1 and (not self.bypass or self.bypass.waypoint is None):
            if self.segment:
                self.arrival_frame = pose['frameId']
                gate = frame.get('frameWorldReadiness') or {}
                self.arrival_epoch = gate.get('epoch')
                self.arrival_source_stamp = (source.get('timestamp100ns') if frame.get('inputAvailable') is True
                    and gate.get('ready') is True and gate.get('sourceFrameId') == self.arrival_frame
                    and gate.get('sourceFrame') == source else None)
            self.phase = 'releaseRequired'
            return 'releaseRequired'
        return None

    def choose(self, frame, proposal):
        """Accept route-compatible model walking; otherwise use measured native correction."""
        if self.destinations and self.phase not in ('walking', 'recovering'):
            raise RuntimeError('Itinerary input requires a verified active leg')
        if self.photo_resume_after is not None and (frame['frameId'] <= self.photo_resume_after
                                                     or frame['frameId'] != self.last_pose['frameId']):
            raise RuntimeError('Input after a station photo requires a newer navigable frame')
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
