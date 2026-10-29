"""One bridge lease's observed, reversible passage around the surveyed stair post."""
from collections import deque
import math

from hybrid_routes import STAIR_POST_ROUTE, camera_correction, route_heading


def observed_point(nav):
    """Keep the source evidence for each taught or visited waypoint."""
    pose = nav.last_pose
    return dict(frameId=pose['frameId'], atMs=nav.last_at, x=pose['x'], y=pose['y'])


def xy(point):
    """Read a world position without modifying the original observation."""
    return point['x'], point['y']


def heading_delta(target, origin):
    """Signed shortest clockwise motion in BetterGI's yaw plane."""
    return (target-origin+180) % 360 - 180


class HybridBypass:
    """Learn at most one three-point passage and steer through it in either direction."""

    def __init__(self, route_id):
        if route_id != STAIR_POST_ROUTE:
            raise ValueError('Bypass memory requires the surveyed stair-post route')
        self.contact = None
        self.trigger_kind = None
        self.points = []
        self.learned = None
        self.replay = ()
        self.index = 0
        self.active_leg = None
        self.invalidated_leg = None
        self.previous = None
        self.world_epoch = None
        self.release_epoch = None
        self.awaiting_release_frame = False
        self.suspension = None
        self.recent_receipts = deque(maxlen=12)

    def _event(self, nav, name, **values):
        """Use the ordinary navigation event sink and controller/source clocks."""
        nav.events.append(dict(type='hybridBypass' + name, routeId=nav.route_id,
                               sourceEpoch=nav.source_epoch, target=nav.target_name,
                               completedLegs=nav.legs, **observed_point(nav), **values))

    def invalidate(self, nav, reason):
        """Discard incomplete evidence and remove a previously learned passage."""
        if self.contact or self.learned:
            self._event(nav, 'Invalidated', reason=reason)
        if self.active_leg == nav.legs:
            # A climb interrupt can clear the replay before its X proof arrives.
            # This partial traversal cannot teach an endpoint-to-endpoint path.
            self.invalidated_leg = nav.legs
        self.contact = self.learned = self.active_leg = None
        self.previous = None
        self.release_epoch = None
        self.awaiting_release_frame = False
        self.suspension = None
        self.points = []
        self.replay = ()
        self.index = 0

    def stalled(self, nav, trigger_kind='stationaryForward'):
        """A stall aiming at a cached corner cannot teach a fresh direct-route passage."""
        # Preserve the trigger observation as the continuity anchor after clearing
        # an earlier path. A gap immediately after contact must still veto teaching.
        previous = self.previous
        self.invalidate(nav, 'newStall')
        self.previous = previous
        if self.invalidated_leg != nav.legs and nav.recovery_attempts == 1:
            self.contact = observed_point(nav)
            self.trigger_kind = trigger_kind

    def recovery_point(self, nav, stage):
        """The recovery controller calls each stage only after its receipt and pose gates."""
        if self.contact and len(self.points) == stage:
            self.points.append(observed_point(nav))

    def _advance(self, point, goal):
        """Project a measured position onto the contact-to-endpoint axis."""
        cx, cy = xy(self.contact)
        length = math.dist((cx, cy), goal)
        return ((point['x'] - cx) * (goal[0] - cx) + (point['y'] - cy) * (goal[1] - cy)) / length

    def released(self, nav, response):
        """Bracket only a finished passage with its own acknowledged release generation."""
        if not (self.learned or self.contact and len(self.points) == 3):
            return
        gate = response.get('worldReadiness') or {}
        epoch = gate.get('epoch')
        if (nav.phase != 'releaseRequired' or type(self.world_epoch) is not int or type(epoch) is not int
                or epoch != self.world_epoch + 1 or gate.get('ready') is not False
                or gate.get('reason') != 'client_release'
                or (gate.get('sourceFrame') or {}).get('captureEpoch') != nav.source_epoch
                or not 0 <= response['serverNowMs'] - nav.last_at <= 500):
            self.invalidate(nav, 'endpointReleaseUnbound')
            return
        self.release_epoch = epoch
        self.awaiting_release_frame = True

    def suspend_stale(self, nav):
        """Freeze only a committed, actively traversed passage. Its waypoint cannot advance."""
        if (not self.learned or self.contact or nav.phase != 'walking' or self.active_leg != nav.legs
                or self.suspension or self.previous is None or type(self.world_epoch) is not int):
            return False
        waypoint = self.waypoint or nav.target
        self.suspension = dict(anchor=observed_point(nav), target=nav.target_name, leg=nav.legs,
            capture=nav.source_epoch, samples=[], lastSource=self.previous,
            facts=dict(yawDegrees=nav.last_pose['yawDegrees'], waypoint=dict(x=waypoint[0], y=waypoint[1]),
                       bypassPointIndex=self.index, previousWorldEpoch=self.world_epoch))
        return True

    def _camera_receipt(self, response, action):
        """Join the exact accepted waypoint correction to a terminal, pure-camera software step."""
        if not action:
            return None
        held = self.suspension
        anchor, facts = held['anchor'], held['facts']
        request = action.get('requestId')
        if (not request or action.get('modelId') != 'hybrid-native' or action.get('reason') != 'nativeHeading'
                or action.get('frameId') != anchor['frameId'] or action.get('observedAtMs') != anchor['atMs']
                or action.get('sourceEpoch') != held['capture'] or action.get('target') != held['target']
                or action.get('completedLegs') != held['leg']
                or action.get('bypassPointIndex') != (facts['bypassPointIndex'] if facts['bypassPointIndex'] < 3 else None)):
            return None
        desired = route_heading(anchor, xy(facts['waypoint']))
        dx = camera_correction(facts['yawDegrees'], desired)
        step = action.get('step') or {}
        if (not dx or step.get('mouseDx') != dx or step.get('mouseDy') != 0 or step.get('keys') != []
                or step.get('mouseButtons') or step.get('buttons')):
            return None
        match = None
        for receipt in (*self.recent_receipts, *(response.get('receipts') or [])):
            steps = receipt.get('appliedSteps') or []
            if receipt.get('requestId') != request:
                # An additional actual step after the source frame breaks the attribution.
                if any(s['startedAtMs'] >= anchor['atMs'] for s in steps):
                    return None
                continue
            if (receipt.get('modelId') != 'hybrid-native' or receipt.get('frameId') != anchor['frameId']
                    or receipt.get('status') != 'completed' or receipt.get('acceptedAtMs') != action.get('acceptedAtMs')
                    or len(steps) != 1 or steps[0].get('keys') != [] or steps[0].get('mouseDx') != dx
                    or steps[0].get('mouseDy') != 0 or steps[0].get('mouseButtons') or steps[0].get('buttons')):
                return None
            begin, end = steps[0].get('startedAtMs'), receipt.get('endedAtMs')
            accepted = receipt.get('acceptedAtMs')
            if (not all(type(v) in (int, float) for v in (accepted, begin, end))
                    or not anchor['atMs'] <= accepted <= begin <= anchor['atMs']+150
                    or not begin < end <= response['serverNowMs'] <= end+250):
                return None
            match = dict(requestId=request, frameId=anchor['frameId'], mouseDx=dx, startedAtMs=begin, endedAtMs=end)
        return match

    def acknowledge_stale_hold(self, nav, response, last_action=None):
        """Bind the pause to the actual input owner's synchronous release and new readiness epoch."""
        if not self.suspension:
            return
        facts = self.suspension['facts']
        gate = response.get('worldReadiness') or {}
        stamp = response.get('serverNowMs')
        if ('releaseAtMs' in facts or response.get('type') != 'released' or gate.get('ready') is not False
                or gate.get('reason') != 'client_release' or type(gate.get('epoch')) is not int
                or gate['epoch'] != facts['previousWorldEpoch'] + 1
                or (gate.get('sourceFrame') or {}).get('captureEpoch') != self.suspension['capture']
                or type(stamp) not in (float, int) or not 0 <= stamp-nav.last_at <= 500):
            self.invalidate(nav, 'staleHoldReleaseUnbound')
            return
        facts.update(releaseEpoch=gate['epoch'], releaseAtMs=stamp)
        camera = self._camera_receipt(response, last_action)
        if camera:
            facts['cameraReceipt'] = camera
        self._event(nav, 'Suspended', **facts)

    def rebind(self, nav, frame):
        """Consume a held frame without dispatch; restore the same waypoint only from stable evidence."""
        held = self.suspension
        facts, anchor = held['facts'], held['anchor']
        gate = frame.get('frameWorldReadiness') or {}
        source = frame['sourceFrame'].get('timestamp100ns')
        pose = nav.last_pose
        previous = held['lastSource']
        if ('releaseAtMs' not in facts or nav.last_at > facts['releaseAtMs'] + 1500
                or nav.source_epoch != held['capture'] or nav.legs != held['leg'] or nav.target_name != held['target']
                or self.index != facts['bypassPointIndex'] or nav.phase != 'walking' or type(source) is not int
                or (nav.last_at <= previous[0] or pose['frameId'] <= previous[1] or source <= previous[2])):
            self.invalidate(nav, 'staleHoldContinuityLost')
            return
        held['lastSource'] = (nav.last_at, pose['frameId'], source)
        if nav.last_at < facts['releaseAtMs']:
            return  # An in-flight pre-release payload cannot supply a post-release sample.
        if (gate.get('epoch') != facts['releaseEpoch'] or gate.get('ready') is not True
                or (gate.get('sourceFrame') or {}).get('captureEpoch') != held['capture']):
            self.invalidate(nav, 'staleHoldWorldChanged')
            return
        if nav.last_at < facts['releaseAtMs'] + 80:
            return
        # Only permit residual travel toward the interrupted waypoint as a final hold drains.
        wx, wy = facts['waypoint']['x']-anchor['x'], facts['waypoint']['y']-anchor['y']
        length = math.hypot(wx, wy)
        dx, dy = pose['x']-anchor['x'], pose['y']-anchor['y']
        yaw_change = heading_delta(pose['yawDegrees'], facts['yawDegrees'])
        camera = facts.get('cameraReceipt')
        toward = heading_delta(route_heading(anchor, xy(facts['waypoint'])), facts['yawDegrees'])
        # During a pure camera correction the avatar must have stayed in place. Only
        # a bounded turn in the applied direction toward this exact waypoint is explainable.
        camera_settled = (camera and math.hypot(dx, dy) <= .35 and yaw_change*camera['mouseDx'] > 0
                          and yaw_change*toward > 0 and abs(yaw_change) <= min(75, abs(toward)+3))
        if (length == 0 or math.hypot(dx, dy) > 2 or (dx*wx + dy*wy)/length < -.45
                or abs(dx*wy - dy*wx)/length > .75 or abs(yaw_change) > 12 and not camera_settled):
            self.invalidate(nav, 'staleHoldPoseDeparted')
            return
        samples = held['samples']
        point = dict(**observed_point(nav), yawDegrees=pose['yawDegrees'])
        if samples and (nav.last_at - samples[-1]['atMs'] > 250 or any(
                math.dist(xy(point), xy(old)) > .35 or abs((point['yawDegrees']-old['yawDegrees']+180)%360-180) > 3
                for old in samples)):
            self.invalidate(nav, 'staleHoldPoseUnstable')
            return
        if not samples or nav.last_at - samples[-1]['atMs'] >= 80:
            samples.append(point)
        if len(samples) == 3:
            self._event(nav, 'Rebound', **facts, samples=samples)
            self.world_epoch, self.previous = facts['releaseEpoch'], held['lastSource']
            self.suspension = None

    def release_wait(self, nav, frame, gate_name):
        """Allow the expected readiness transition before the first requalified pose."""
        if self.suspension and 'releaseAtMs' in self.suspension['facts']:
            facts = self.suspension['facts']
            # An additional gate closure after re-entry sampling begins is a new interruption.
            if self.suspension['samples']:
                return False
            epoch, released, limit = facts['releaseEpoch'], facts['releaseAtMs'], 1500
        elif self.awaiting_release_frame and nav.phase == 'verifying':
            epoch, released, limit = self.release_epoch, nav.release_at, 1000
        else:
            return False
        gate = frame.get(gate_name) or {}
        now = frame.get('serverNowMs')
        if (type(now) not in (float, int) or not 0 <= now - released <= limit
                or gate.get('epoch') != epoch
                or (gate.get('sourceFrame') or {}).get('captureEpoch') != nav.source_epoch
                or (frame.get('sourceFrame') or {}).get('captureEpoch', nav.source_epoch) != nav.source_epoch):
            return False
        if gate.get('ready') is True:
            return (gate.get('reason') == 'world_ready' and (frame.get('inputAvailable') is True
                    or gate_name == 'worldReadiness' and self.release_wait(nav, frame, 'frameWorldReadiness')))
        return gate.get('ready') is False and gate.get('reason') in (
            'client_release', 'world_observation_invalidated', 'world_confirming')

    def observe(self, nav, frame):
        """Only called after the normal motion, source, pose, and corridor checks."""
        source = frame['sourceFrame'].get('timestamp100ns')
        current = (nav.last_at, nav.last_pose['frameId'], source)
        gate = frame.get('frameWorldReadiness') or {}
        self.world_epoch = gate.get('epoch')
        release_gap = False
        if self.release_epoch is not None:
            if (self.world_epoch != self.release_epoch or gate.get('ready') is not True
                    or (gate.get('sourceFrame') or {}).get('captureEpoch') != nav.source_epoch):
                self.invalidate(nav, 'endpointReadinessChanged')
            elif self.awaiting_release_frame:
                release_gap = 0 <= nav.last_at - nav.release_at <= 1000
                if not release_gap:
                    self.invalidate(nav, 'endpointReconfirmationLate')
                self.awaiting_release_frame = False
        if (type(source) is not int or self.previous and (nav.last_at <= self.previous[0]
                or not release_gap and nav.last_at - self.previous[0] > 250
                or current[1] <= self.previous[1] or source <= self.previous[2])):
            self.invalidate(nav, 'sourceDiscontinuity')
        self.previous = current if type(source) is int else None
        if nav.phase != 'walking':
            return
        point = observed_point(nav)
        if self.contact and len(self.points) == 2:
            cleared = self.points[1]
            advance = self._advance(point, nav.target)
            if (advance >= 1.5 and advance - self._advance(cleared, nav.target) >= 1
                    and nav._held_ms('W', cleared['atMs'], nav.last_at) >= 80):
                self.points.append(point)
        if not self.learned:
            return
        direction, points = self.learned
        if self.active_leg != nav.legs:
            self.active_leg = nav.legs
            self.replay = points if direction == nav.target_name else points[::-1]
            self.index = 0
            self._event(nav, 'Started', points=list(self.replay))
        if self.index < len(self.replay) and math.dist(xy(point), xy(self.replay[self.index])) <= .65:
            self._event(nav, 'PointReached', bypassPointIndex=self.index)
            self.index += 1
            nav.stall_samples.clear()

    @property
    def waypoint(self):
        """Steering target for the next decision; endpoint verification remains separate."""
        if self.index < len(self.replay):
            return xy(self.replay[self.index])
        return None

    def endpoint(self, nav):
        """Commit only after the normal release and three verified endpoint observations."""
        if self.contact and len(self.points) == 3 and min(self._advance(p, nav.target) for p in nav.samples) >= 1.5:
            self.learned = (nav.target_name, tuple(self.points))
            self._event(nav, 'Learned', triggerKind=self.trigger_kind, contact=self.contact, points=self.points)
        self.contact = None
        self.points = []
        self.replay = ()
        self.index = 0
        self.release_epoch = None
        self.awaiting_release_frame = False
