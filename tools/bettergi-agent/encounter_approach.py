"""Prepare and run one reviewed, movement-only approach through the existing RDP bridge.

Preparation is offline. The ordinary RDP worker never loads a model, attacks,
repairs a failed lease, or treats route arrival as melee range or combat success.
The existing scout and stationary-combat contracts remain separate and unchanged.
"""
import argparse
import ast
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid

from hybrid_navigation import HybridNavigation, yaw_error
from native_combat import validate_capability as validate_combat_capability, validate_frame as combat_frame
from native_ground_control import (CAPABILITY as GROUND_CAPABILITY, require_ground_frame,
                                   validate_capability as validate_ground_capability, verify_image_crops)
from navigation_profiles import SCOUT_PROFILE, allows_pose_scope, scout_scope, validate_capability
from observation_timing import observation_timestamp
from reviewed_scout_route import ReviewedScoutRoute, require_navigation_review_scene


ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / 'artifacts/live'
KIND = 'encounter-approach-v1'
REVIEW_KIND = 'encounter-approach-review-v1'
PROFILE = 'p2p-native-hamming-192-v1'
MODEL_ID = 'encounter-approach-native-v1'
MAX_REVIEW_SECONDS = 120
HOST_SECONDS = 40
MAX_RECORD_BYTES = 80 * 1024 * 1024


def policy():
    """Return a fresh closed declaration; callers cannot widen another run's limits."""
    return dict(version=1, maximumDistance=6, maximumSeconds=10, holdMs=50, maximumActions=80,
                maximumOutstanding=1, sourceFreshnessMs=150, maximumHealthFractionDrop=.02,
                minimumDispatchBudgetMs=200,
                maximumEnemyBarCandidates=4, allowedKeys=['W'], maximumHorizontalMouseDelta=350,
                verticalCameraAllowed=False, attacksAllowed=False, automaticRecovery=False,
                corridorHalfWidth=1, navigationCorridorHalfWidth=4, endpointRadius=2, maximumTargetAbsenceMs=750,
                navigationProfile=SCOUT_PROFILE, enemyIdentityVerified=False, meleeArrivalVerified=False)


def require(value, message):
    """Missing evidence is a terminal refusal, never an implicit fallback."""
    if not value:
        raise ValueError(message)


def finite(value):
    """Exclude booleans and nonfinite values from all clock/geometry contracts."""
    return type(value) in (int, float) and math.isfinite(value)


def canonical(value):
    """Freeze typed JSON for equality, immutable binding and artifact hashes."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(raw):
    """Identify original bytes independently of filenames and formatting."""
    return hashlib.sha256(raw).hexdigest()


def local_path(value, *, root=None, existing=True):
    """Constrain local evidence and refuse links/UNC substitution."""
    path = Path(value).absolute()
    require(not str(path).startswith(('\\\\', '//')) and path == path.resolve(strict=existing),
            'Expected an unlinked local path')
    if root is not None:
        require(path.is_relative_to(Path(root).resolve()), 'Evidence escaped its artifact root')
    return path


def read_bytes(path, maximum=16 * 1024 * 1024, *, allow_empty=False):
    """Read one bounded regular original file, without broad file-content scans."""
    path = local_path(path)
    with path.open('rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                (allow_empty or info.st_size > 0) and info.st_size <= maximum, 'Unbounded or linked evidence')
        raw = stream.read(info.st_size + 1)
    require(len(raw) == info.st_size, 'Evidence changed during reading')
    return raw


def document(path, maximum=16 * 1024 * 1024):
    """Parse bounded JSON while retaining the original byte digest."""
    raw = read_bytes(path, maximum)
    return json.loads(raw), digest(raw)


def exclusive_json(path, value):
    """Consume a plan or publish immutable evidence once, never overwrite a prior run."""
    raw = canonical(value)
    with Path(path).open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return digest(raw)


def validate_owner(owner):
    """Pin exactly one original primary and one separate RDP child."""
    require(isinstance(owner, dict) and set(owner) == {'root', 'child'}, 'Invalid original owner pair')
    for value in owner.values():
        require(isinstance(value, dict) and set(value) == {'processId', 'windowsSessionId', 'instanceNonce'}
                and all(type(value.get(k)) is int and value[k] > 0 for k in ('processId', 'windowsSessionId'))
                and isinstance(value.get('instanceNonce'), str) and value['instanceNonce'], 'Incomplete owner identity')
    require(owner['root']['processId'] != owner['child']['processId']
            and owner['root']['windowsSessionId'] != owner['child']['windowsSessionId'], 'RDP owner is not separate')


def route_geometry(value):
    """Keep the existing planner's two-unit endpoint regions disjoint inside the known local surface scope."""
    route = ReviewedScoutRoute.from_document(value)
    require(route.profile_id == SCOUT_PROFILE, 'Only the existing local combat-scout surface scope is supported')
    length = math.dist(*route.points)
    require(2 * policy()['endpointRadius'] < length <= policy()['maximumDistance'],
            'Route must be longer than the two endpoint radii and no longer than6 units')
    bounds, _ = scout_scope(route.profile_id)
    # The full admitted corridor, not only its centre line, must remain in the existing map scope.
    margin = policy()['corridorHalfWidth']
    require(all(bounds['minX'] + margin <= x <= bounds['maxX'] - margin and
                bounds['minY'] + margin <= y <= bounds['maxY'] - margin for x, y in route.points),
            'Reviewed corridor crosses the existing surface bounds')
    return route


def qualify_frame(frame, baseline, maximum_candidates, *, replay_pixels=False, capability=None):
    """Validate one immutable image's health, ground, pose and original150ms source age."""
    require(isinstance(frame, dict) and frame.get('type') == 'frame', 'Native frame unavailable')
    require(type(frame.get('frameId')) is int and frame['frameId'] > 0, 'Invalid native frame ID')
    source = frame.get('sourceFrame')
    require(isinstance(source, dict) and isinstance(source.get('captureEpoch'), str) and source['captureEpoch']
            and type(source.get('timestamp100ns')) is int and source['timestamp100ns'] > 0,
            'WGC source identity required')
    at = observation_timestamp(frame)
    require(frame.get('sourceTimestampKind') == 'wgc_reported_compositor_qpc'
            and finite(frame.get('serverNowMs')) and finite(frame.get('sourceFrameAgeMs'))
            and abs(frame['serverNowMs'] - at - frame['sourceFrameAgeMs']) <= .01
            and 0 <= frame['sourceFrameAgeMs'] <= 150, 'Native source stale or malformed')
    evidence = combat_frame(frame, capability)
    require(evidence is not None and evidence['state'] == 'valid', 'Health/target evidence unavailable')
    require(evidence['playerHealthColor'] == 'green', 'Health is red or ambiguous')
    require(baseline - evidence['playerHealthFractionEstimate'] <= .02 + 1e-12, 'Health loss exceeds2 percentage points')
    require(not evidence['redMaskOverloaded'] and len(evidence['enemyBarCandidates']) <= maximum_candidates,
            'Enemy candidate evidence exceeds the reviewed group')
    ground = require_ground_frame(frame, replay_pixels=replay_pixels)
    world, current = frame.get('frameWorldReadiness'), frame.get('worldReadiness')
    require(isinstance(world, dict) and isinstance(current, dict) and world.get('ready') is True
            and current.get('ready') is True and type(world.get('epoch')) is int
            and world['epoch'] == current.get('epoch') and world.get('sourceFrameId') == frame['frameId']
            and world.get('sourceFrame') == source, 'Frame-bound/current readiness is unavailable or changed')
    motion = frame.get('motionEvidence') or {}
    require(motion.get('status') == 'normal' and motion.get('spaceKeyMatched') is False,
            'Climbing, swimming, flying or unknown movement')
    pose = frame.get('navigationPose') or {}
    require(pose.get('state') == 'valid' and pose.get('frameId') == frame['frameId']
            and allows_pose_scope(pose, SCOUT_PROFILE) and pose.get('layerId') == 'MapBack_2'
            and all(finite(pose.get(k)) for k in ('x', 'y', 'yawDegrees', 'positionConfidence', 'yawConfidence'))
            and .99 <= pose['positionConfidence'] <= 1 and .2 <= pose['yawConfidence'] <= 1
            and 0 <= pose['yawDegrees'] < 360, 'Fresh qualified same-frame surface pose required')
    require(type(frame.get('droppedReceipts', 0)) is int and frame.get('droppedReceipts', 0) == 0,
            'Native terminal receipts were dropped')
    return evidence, ground, pose


def bind_review(review, native_plan, scene, sidecar, image, *, expected_owner=None):
    """Bind an explicit clear-corridor review to original passive source pixels, never create that review."""
    require(review.get('kind') == REVIEW_KIND and canonical(review.get('policy')) == canonical(policy()),
            'A separate fixed encounter-approach review is required')
    require(type(review.get('reviewedAtUnixNs')) is int and review['reviewedAtUnixNs'] > 0,
            'The original visual review time is required')
    owner = review.get('owner')
    validate_owner(owner)
    require(expected_owner is None or owner == expected_owner, 'Reviewed owner differs from original lineage')
    require(native_plan.get('owner') == owner and native_plan.get('enableInput') is False
            and native_plan.get('modelLoaded') is False and scene.get('status') == 'completed'
            and scene.get('inputEnabled') is False and scene.get('modelLoaded') is False
            and scene.get('ownerIdleMinimizedAfter') is True, 'Original passive capture/cleanup is incomplete')
    require_navigation_review_scene(native_plan, scene)
    require(review.get('clearSurfaceCorridor') is True and review.get('fenceOpeningReviewed') is True
            and isinstance(review.get('inspectionNote'), str) and review['inspectionNote'].strip()
            and review.get('attacksAllowed') is False, 'Clear movement corridor and fence opening must be reviewed')
    hp, maximum, count = (review.get(k) for k in ('inspectedHealth', 'inspectedMaximumHealth', 'inspectedVisibleEnemyCount'))
    require(type(hp) is int and type(maximum) is int and 0 < hp <= maximum
            and type(count) is int and 1 <= count <= 4, 'Invalid reviewed health or enemy-group count')
    route = route_geometry(review.get('route'))
    require(native_plan.get('navigationProfile') == route.profile_id and
            isinstance(native_plan.get('anchor'), list) and len(native_plan['anchor']) == 2
            and all(finite(x) for x in native_plan['anchor'])
            and math.dist(native_plan['anchor'], route.points[0]) <= .35, 'Capture anchor and route start differ')
    combat_capability = validate_combat_capability(scene.get('nativeCombatObservation'))
    validate_ground_capability(scene.get('nativeGroundControlObservation'))
    validate_capability(scene.get('capability'), route.profile_id)
    name = review.get('imageName')
    require(isinstance(name, str) and Path(name).name == name and name.endswith('.png')
            and scene.get('selectedImageName') == name
            and sidecar.get('imageSha256') == review.get('imageSha256') == scene.get('selectedImageSha256') == digest(image),
            'Reviewed PNG is not the original selected image')
    observed = [x for x in scene.get('observations', []) if x.get('frameId') == sidecar.get('frameId')]
    require(observed and scene.get('qualifiedImageFrameId') == sidecar.get('frameId'), 'Selected native image has no original observation')
    selected = observed[0]
    immutable = ('frameId', 'capturedAtMs', 'sourceFrame', 'sourceTimestampKind', 'sourceWidth', 'sourceHeight',
                 'frameWorldReadiness', 'combatEvidence', 'groundControlEvidence', 'navigationPose', 'motionEvidence')
    require(all(all(row.get(key) == selected.get(key) for key in immutable) for row in observed),
            'Repeated selected-frame immutable evidence differs')
    require(all(x.get('sourceFrame') == sidecar.get('sourceFrame') == selected.get('sourceFrame') for x in observed)
            and sidecar.get('worldReadiness') == selected.get('frameWorldReadiness')
            and sidecar.get('capturedAtMs') == selected.get('capturedAtMs')
            and sidecar.get('sourceTimestampKind') == selected.get('sourceTimestampKind')
            and sidecar.get('freshnessContractVersion') == 2 and sidecar.get('evidence') == 'WorldHud'
            and sidecar.get('sourceWidth') == 1920 and sidecar.get('sourceHeight') == 1080,
            'Reviewed image/source/readiness join differs')
    samples = scene.get('stableSamples')
    require(isinstance(samples, list) and len(samples) == 3, 'Three stable passive source samples required')
    for frame in [selected] + samples:
        require(frame in scene.get('observations', []) and (frame.get('executionContext') or {}).get('lastSequence') == 0,
                'Passive review contains input or synthetic observations')
        evidence, _, pose = qualify_frame(frame, hp / maximum, count, replay_pixels=True, capability=combat_capability)
        require(1 <= len(evidence['enemyBarCandidates']) <= count
                and math.dist((pose['x'], pose['y']), route.points[0]) <= .35, 'Reviewed start/group differs')
    for a, b in zip(samples, samples[1:]):
        x, y = a['sourceFrame'], b['sourceFrame']
        require(x['captureEpoch'] == y['captureEpoch'] and x['timestamp100ns'] < y['timestamp100ns']
                and a['frameId'] < b['frameId'] and 80 <= y['freshnessAtMs'] - x['freshnessAtMs'] <= 250
                and a['frameWorldReadiness']['epoch'] == b['frameWorldReadiness']['epoch']
                and math.dist(tuple(a['navigationPose'][k] for k in ('x', 'y')),
                              tuple(b['navigationPose'][k] for k in ('x', 'y'))) <= .35
                and yaw_error(a['navigationPose']['yawDegrees'], b['navigationPose']['yawDegrees']) <= 3,
                'Review sources are not distinct and stationary')
    # Decode only during offline preparation; this also proves original ground crops came from the reviewed PNG.
    from PIL import Image
    with Image.open(io.BytesIO(image)) as picture:
        require(picture.format == 'PNG' and picture.size == (1920, 1080), 'Original full-resolution PNG required')
        picture.load()
        rgb = picture.convert('RGB')
        import base64
        for crop in selected['groundControlEvidence']['crops']:
            require(rgb.crop((crop['x'], crop['y'], crop['x'] + crop['width'], crop['y'] + crop['height'])).tobytes()
                    == base64.b64decode(crop['rgbBase64'], validate=True), 'Ground-control crops differ from reviewed pixels')
    return dict(version=1, kind=KIND, policy=policy(), owner=copy.deepcopy(owner), route=route.document(),
                baselineHealthFraction=hp / maximum, inspectedHealth=hp, inspectedMaximumHealth=maximum,
                maximumEnemyBarCandidates=count, nativeCombatObservation=combat_capability,
                reviewedAtUnixNs=review['reviewedAtUnixNs'],
                nativeGroundControlObservation=copy.deepcopy(GROUND_CAPABILITY),
                navigationCapability=copy.deepcopy(scene['capability']), reviewedFrame=copy.deepcopy(selected),
                reviewSha256=digest(canonical(review)), imageSha256=digest(image))


def recent_review(review, binding, *, now_ns=None, qpc_ns=None):
    """Use original review and acquisition clocks, never a copied file's modification time."""
    now_ns = time.time_ns() if now_ns is None else now_ns
    qpc_ns = time.perf_counter_ns() if qpc_ns is None else qpc_ns
    stamp = review.get('reviewedAtUnixNs')
    source = binding['reviewedFrame']['sourceFrame']['timestamp100ns']
    require(type(stamp) is int and 0 <= now_ns - stamp <= MAX_REVIEW_SECONDS * 1_000_000_000
            and 0 <= qpc_ns - source * 100 <= MAX_REVIEW_SECONDS * 1_000_000_000,
            'Reviewed corridor/source is stale or future-dated')


def original_review_deadline(binding, *, client_ns=None, wall_ns=None):
    """Map the two original expiries once, conservatively; later setup work cannot renew either one."""
    client_ns = time.perf_counter_ns() if client_ns is None else client_ns
    wall_ns = time.time_ns() if wall_ns is None else wall_ns
    wall_expiry = binding['reviewedAtUnixNs'] + MAX_REVIEW_SECONDS * 1_000_000_000
    source_expiry = binding['reviewedFrame']['sourceFrame']['timestamp100ns'] * 100 + MAX_REVIEW_SECONDS * 1_000_000_000
    return min(source_expiry, client_ns + wall_expiry - wall_ns)


def validate_claim(claim, run_id, plan_sha):
    """Keep the consumed host's original wall/QPC pair and fixed forty-second window exact."""
    require(isinstance(claim, dict) and set(claim) == {'runId', 'planSha256', 'hostProcessId', 'startedAtUnixNs',
                                                     'startedMonotonicNs', 'deadlineMonotonicNs'}
            and claim['runId'] == run_id and claim['planSha256'] == plan_sha
            and all(type(claim.get(key)) is int and claim[key] > 0 for key in
                    ('hostProcessId', 'startedAtUnixNs', 'startedMonotonicNs', 'deadlineMonotonicNs'))
            and claim['deadlineMonotonicNs'] == claim['startedMonotonicNs'] + HOST_SECONDS * 1_000_000_000,
            'Consumed host claim changed its original identity or absolute clocks')


class ApproachController:
    """One serial movement owner with a fresh native planner and immutable reviewed limits."""

    def __init__(self, binding, hello, started_ns, *, deadline_ns=None):
        """A new phase starts with no prior action/history and cannot inherit a tripped guard."""
        require(canonical(binding.get('policy')) == canonical(policy()), 'Approach policy changed')
        require(hello.get('inputEnabled') is True and hello.get('supportsRelease') is True
                and hello.get('supportsStartBeforeMs') is True and hello.get('observationProfile') == PROFILE
                and 'W' in hello.get('allowedKeys', []) and hello.get('sessionId') and hello.get('ownerEpoch')
                and hello.get('goalVersion') == 1, 'Unsupported ordinary native input lease')
        require(not hello.get('stepApplications'), 'Queued input is not supported by this approach')
        self.binding = copy.deepcopy(binding)
        self.hello = copy.deepcopy(hello)
        route = route_geometry(binding['route'])
        self.navigation = HybridNavigation(binding['navigationCapability'], route.route_id,
            navigation_profile=route.profile_id, reviewed_scout_route=route, action_hold_ms=50,
            require_ground_controls=True)
        self.started_ns = started_ns
        self.deadline_ns = min(started_ns + 10_000_000_000, deadline_ns or started_ns + 10_000_000_000)
        self.source_epoch = None
        self.world_epoch = None
        self.last = None
        self.last_distinct = None
        self.target_seen_at = None
        self.armed = False
        self.after_release = None
        self.pending = None
        self.accepted = {}
        self.action_responses = {}
        self.attempts = {}
        self.receipts = {}
        self.actions = 0
        self.trip = None
        self.complete = False

    def fail(self, reason):
        """Latch the first failure permanently; later healthy frames cannot resume this lease."""
        self.trip = self.trip or str(reason)
        raise RuntimeError(self.trip)

    def check(self, now_ns):
        """Bound every wait path as well as dispatch; there is no automatic renewal."""
        if self.trip:
            raise RuntimeError(self.trip)
        if now_ns >= self.deadline_ns:
            self.fail('approach_deadline')

    def observe(self, frame, received_ns, round_trip_ms):
        """Inspect all polls, including unchanged frames; only distinct complete frames advance navigation."""
        try:
            return self._observe(frame, received_ns, round_trip_ms)
        except (ValueError, TypeError, KeyError, RuntimeError) as error:
            self.fail(str(error))

    def _observe(self, frame, received_ns, round_trip_ms):
        """Validate one observation beneath the public terminal-failure latch."""
        self.check(received_ns)
        require(finite(round_trip_ms) and round_trip_ms >= 0, 'Invalid transport measurement')
        if frame.get('type') != 'frame':
            if self.armed:
                self.fail('armed_native_frame_unavailable')
            return 'waitingForNativeFrame'
        # Explicit release/bootstrap may briefly close native readiness, but valid hazards still win.
        evidence = combat_frame(frame, self.binding['nativeCombatObservation'])
        if evidence is not None and evidence['state'] == 'valid':
            if evidence['playerHealthColor'] != 'green' or self.binding['baselineHealthFraction'] - evidence['playerHealthFractionEstimate'] > .02 + 1e-12:
                self.fail('health_stop')
            if evidence['redMaskOverloaded'] or len(evidence['enemyBarCandidates']) > self.binding['maximumEnemyBarCandidates']:
                self.fail('enemy_evidence_stop')
        if not self.armed and ((frame.get('worldReadiness') or {}).get('ready') is not True
                              or frame.get('inputAvailable') is not True):
            return 'waitingForReadiness'
        try:
            evidence, _, pose = qualify_frame(frame, self.binding['baselineHealthFraction'], self.binding['maximumEnemyBarCandidates'],
                                              capability=self.binding['nativeCombatObservation'])
            require(frame.get('inputAvailable') is True and frame['sourceFrameAgeMs'] + round_trip_ms <= 150,
                    'Latest native input/source unavailable')
        except (ValueError, TypeError, KeyError) as error:
            self.fail(str(error))
        source = frame['sourceFrame']
        if self.source_epoch is not None and source['captureEpoch'] != self.source_epoch:
            self.fail('capture_epoch_changed')
        self.source_epoch = source['captureEpoch']
        world_epoch = frame['frameWorldReadiness']['epoch']
        if self.world_epoch is not None and world_epoch != self.world_epoch:
            self.fail('world_epoch_changed_without_release')
        self.world_epoch = world_epoch
        start, end = route_geometry(self.binding['route']).points
        length = math.dist(start, end)
        dx, dy = end[0] - start[0], end[1] - start[1]
        px, py = pose['x'] - start[0], pose['y'] - start[1]
        projection, cross = (px * dx + py * dy) / length, abs(px * dy - py * dx) / length
        if cross > 1 or not -.35 <= projection <= length or math.hypot(px, py) > 6:
            self.fail('outside_reviewed_approach_corridor')
        if self.last_distinct is None:
            reviewed_pose = self.binding['reviewedFrame']['navigationPose']
            if math.hypot(px, py) > .35 or yaw_error(pose['yawDegrees'], reviewed_pose['yawDegrees']) > 3:
                self.fail('reviewed_start_changed')
        if self.last_distinct is not None:
            old = self.last_distinct
            if frame['frameId'] < old['frameId'] or source['timestamp100ns'] < old['sourceFrame']['timestamp100ns']:
                self.fail('native_source_regressed')
            if frame['frameId'] == old['frameId']:
                keys = ('sourceFrame', 'navigationPose', 'combatEvidence', 'groundControlEvidence', 'frameWorldReadiness', 'motionEvidence')
                if any(frame.get(key) != old.get(key) for key in keys):
                    self.fail('repeated_source_evidence_changed')
                self.last = (copy.deepcopy(frame), received_ns, round_trip_ms)
                return 'duplicatePose'
            if source['timestamp100ns'] <= old['sourceFrame']['timestamp100ns']:
                self.fail('new_frame_reused_old_source')
        if evidence['enemyBarCandidates']:
            self.target_seen_at = source['freshnessAtMs']
        elif self.target_seen_at is None or source['freshnessAtMs'] - self.target_seen_at > 750:
            self.fail('target_absence_deadline')
        if self.after_release is not None and source['freshnessAtMs'] <= self.after_release:
            return 'waitingAfterRelease'
        self.last = (copy.deepcopy(frame), received_ns, round_trip_ms)
        self.last_distinct = copy.deepcopy(frame)
        try:
            outcome = self.navigation.prepare(frame)
        except (ValueError, RuntimeError) as error:
            self.fail(str(error))
        if self.navigation.legs >= 1:
            self.complete = True
            return 'endpointVerified'
        if self.navigation.phase == 'walking':
            self.armed = True
        return outcome

    def next_action(self, now_ns):
        """Choose only native horizontal correction or W; recheck age after all recording/other work."""
        self.check(now_ns)
        if self.complete or self.pending is not None or not self.armed or self.navigation.phase != 'walking':
            return None
        if self.deadline_ns - now_ns < 200_000_000:
            self.fail('approach_dispatch_budget')
        frame, received, rtt = self.last
        require(now_ns >= received, 'Client clock regressed')
        if frame['sourceFrameAgeMs'] + rtt + (now_ns - received) / 1e6 > 150:
            self.fail('dispatch_source_stale')
        if self.actions >= 80:
            self.fail('action_limit')
        try:
            selection = self.navigation.choose(frame, dict(parseValid=False, steps=[]))
        except (ValueError, RuntimeError) as error:
            self.fail(str(error))
        step = selection['step']
        require(step['keys'] in ([], ['W']) and type(step['mouseDx']) is int and abs(step['mouseDx']) <= 350
                and step['mouseDy'] == 0 and step['durationMs'] == 50
                and not (step['keys'] and step['mouseDx']), 'Planner attempted an unsupported approach action')
        source_at = observation_timestamp(frame)
        request_id = uuid.uuid4().hex
        # The native default start-age ceiling is500ms; the explicit tighter deadline is mandatory here.
        request = dict(requestId=request_id, modelId=MODEL_ID, frameId=frame['frameId'],
                       observedAtMs=frame['capturedAtMs'], startBeforeMs=source_at + 150,
                       expiresAtMs=source_at + 200, steps=[copy.deepcopy(step)])
        self.pending = dict(request=copy.deepcopy(request), selection=copy.deepcopy(selection), frame=copy.deepcopy(frame),
                            preparedAtClientNs=now_ns, receivedAtClientNs=received, roundTripMs=rtt,
                            transmissionAttempted=False, state='prepared', accepted=None)
        self.attempts[request_id] = self.pending
        self.actions += 1
        return copy.deepcopy(request)

    def transmitting(self, now_ns):
        """Mark the exact point after final checks and immediately before the only native action call."""
        self.check(now_ns)
        require(self.pending is not None and not self.pending['transmissionAttempted'], 'Unexpected second transmission')
        value = self.pending
        age = value['frame']['sourceFrameAgeMs'] + value['roundTripMs'] + (now_ns - value['receivedAtClientNs']) / 1e6
        require(now_ns >= value['preparedAtClientNs'] and 0 <= age <= 150, 'Source expired before native transmission')
        value.update(transmissionAttempted=True, transmittedAtClientNs=now_ns, sourceAgeAtDispatchMs=age,
                     state='transmitted_outcome_unknown')
        return age

    def abandon_prepared(self, reason):
        """Distinguish a never-sent local proposal from an action whose native outcome is unknown."""
        if self.pending is None or self.pending['transmissionAttempted']:
            return None
        value = self.pending
        value.update(state='abandoned_before_transmission', abandonmentReason=str(reason))
        self.pending = None
        return dict(type='proposalAbandoned', requestId=value['request']['requestId'],
                    transmissionAttempted=False, reason=str(reason))

    def attempt_summary(self):
        """Keep bounded exact send-state accounting even if later disk writes cannot complete."""
        fields = ('preparedAtClientNs', 'transmissionAttempted', 'transmittedAtClientNs', 'sourceAgeAtDispatchMs',
                  'state', 'abandonmentReason')
        return {key: dict(request=copy.deepcopy(value['request']),
                          **{name: copy.deepcopy(value[name]) for name in fields if name in value})
                for key, value in self.attempts.items()}

    def admission(self, response, payload):
        """Unknown/rejected outcomes stop; only one acknowledged action may await a terminal receipt."""
        require(self.pending is not None and self.pending['accepted'] is None, 'Unexpected action response')
        require(self.pending['transmissionAttempted'] is True, 'An untransmitted proposal cannot have native admission')
        request = self.pending['request']
        self.action_responses[request['requestId']] = dict(response=copy.deepcopy(response), payloadBytes=len(payload),
                                                          payloadSha256=digest(payload))
        if response.get('requestId') == request['requestId'] and response.get('type') == 'rejected' and not payload:
            self.pending['state'] = 'rejected'
            self.pending = None
            self.fail('action_rejected:' + str(response.get('reason')))
        if response.get('type') != 'accepted' or response.get('requestId') != request['requestId']:
            self.fail('action_not_accepted')
        # Preserve known acceptance before validating its timing or touching fallible storage.
        self.pending['accepted'] = copy.deepcopy(response)
        self.pending['state'] = 'accepted'
        self.accepted[request['requestId']] = copy.deepcopy(self.pending)
        at = response.get('acceptedAtMs')
        require(not payload and finite(at) and observation_timestamp(self.pending['frame']) <= at < request['startBeforeMs'],
                'Native acceptance crossed its source deadline')

    def intake_receipts(self, response, *, final=False):
        """Join every exact terminal result once and retain real applied holds for stall detection."""
        require(type(response.get('droppedReceipts', 0)) is int and response.get('droppedReceipts', 0) == 0,
                'Native receipts were dropped')
        require(isinstance(response.get('receipts', []), list), 'Invalid receipt envelope')
        for receipt in response.get('receipts', []):
            identity = receipt.get('requestId')
            require(identity in self.accepted and identity not in self.receipts, 'Unknown or duplicate terminal receipt')
            submitted = self.accepted[identity]
            request, accepted = submitted['request'], submitted['accepted']
            require(receipt.get('modelId') == MODEL_ID and receipt.get('frameId') == request['frameId']
                    and receipt.get('acceptedAtMs') == accepted['acceptedAtMs'] and finite(receipt.get('endedAtMs')),
                    'Terminal action identity differs')
            require(receipt['endedAtMs'] >= receipt['acceptedAtMs'], 'Terminal receipt predates acceptance')
            steps = receipt.get('appliedSteps')
            require(isinstance(steps, list) and len(steps) <= 1, 'Unexpected native applied sequence')
            if steps:
                applied, expected = steps[0], request['steps'][0]
                require(applied.get('index') == 0 and all(applied.get(k) == expected[k] for k in ('keys', 'mouseDx', 'mouseDy'))
                        and finite(applied.get('startedAtMs'))
                        and accepted['acceptedAtMs'] <= applied['startedAtMs'] < request['startBeforeMs']
                        and applied['startedAtMs'] <= receipt['endedAtMs'] <= request['expiresAtMs'] + 30,
                        'Applied native input differs or missed its bound')
            completed = receipt.get('status') == 'completed' and receipt.get('reason') == 'horizon_complete' and len(steps) == 1
            require(completed or receipt.get('status') == 'cancelled', 'Action ended without a recognized terminal result')
            require(not completed or receipt['endedAtMs'] >= receipt['acceptedAtMs'] + 50,
                    'Completed action lacks its full accepted-time horizon')
            self.receipts[identity] = copy.deepcopy(receipt)
            self.attempts[identity]['state'] = receipt['status']
            self.navigation.receipt(receipt)
            if self.pending and self.pending['request']['requestId'] == identity:
                self.pending = None
            if not completed and not final:
                self.fail('action_cancelled_before_complete_horizon')

    def released(self, response, payload, *, endpoint=False):
        """Acknowledge released held state and require wholly new source evidence before endpoint verification."""
        require(not payload and response.get('type') == 'released' and finite(response.get('serverNowMs')),
                'Release was not acknowledged')
        context = response.get('executionContext') or {}
        tracked = context.get('trackedState') or {}
        require(context.get('active') is None and context.get('telemetryComplete') is True
                and tracked.get('heldKeys') == [] and type(tracked.get('executionUncertain')) is bool
                and tracked.get('telemetryIncomplete') is False and tracked.get('releaseOutcome') == 'returned_unverified',
                'Native release/held-state proof missing')
        self.intake_receipts(response, final=not endpoint)
        require(self.pending is None, 'Release lacks the pending terminal receipt')
        self.armed = False
        self.world_epoch = None
        self.after_release = response['serverNowMs']
        if endpoint:
            require(self.navigation.phase == 'releaseRequired', 'Unexpected endpoint release')
            gate = response.get('worldReadiness') or {}
            require(gate.get('ready') is False and type(gate.get('epoch')) is int
                    and gate['epoch'] == self.last_distinct['frameWorldReadiness']['epoch'] + 1
                    and (gate.get('sourceFrame') or {}).get('captureEpoch') == self.source_epoch,
                    'Endpoint release lacks the original capture and exact next world epoch')
            self.world_epoch = gate['epoch']
            self.navigation.released(response)


class EvidenceJournal:
    """Bounded original RGB and JSONL evidence; disk failures stop before another action."""

    def __init__(self, directory):
        """Create one append-only journal and unique frame directory for this attempt."""
        self.directory = Path(directory)
        self.directory.mkdir(exist_ok=False)
        (self.directory / 'frames').mkdir()
        self.stream = (self.directory / 'events.jsonl').open('xb')
        self.total = 0
        self.frames = {}
        self.count = 0

    def event(self, value):
        """Reserve finite storage before retaining a complete event."""
        raw = canonical(value) + b'\n'
        require(self.total + len(raw) <= MAX_RECORD_BYTES, 'Approach evidence budget exceeded')
        self.stream.write(raw)
        self.stream.flush()
        self.total += len(raw)
        self.count += 1

    def frame(self, metadata, pixels, received_ns, round_trip_ms):
        """Record repeated observation ages while writing each exact RGB payload only once."""
        value = copy.deepcopy(metadata)
        # Receipt semantics are retained; this run does not claim a complete low-level input journal.
        value.pop('executionContext', None)
        value['executionContextOmitted'] = True
        info = dict(type='observation', frame=value, clientReceivedNs=received_ns, roundTripMs=round_trip_ms)
        if metadata.get('type') == 'frame':
            require(metadata.get('width') == metadata.get('height') == 192 and metadata.get('pixelFormat') == 'rgb24'
                    and len(pixels) == metadata.get('payloadBytes') == 192 * 192 * 3, 'Native RGB contract differs')
            number = metadata['frameId']
            name = f'frames/{number:08d}.rgb'
            rgb_sha = digest(pixels)
            info.update(rgbFile=name, rgbSha256=rgb_sha)
            require(number not in self.frames or self.frames[number] == rgb_sha,
                    'Repeated native frame changed its exact RGB payload')
            if number not in self.frames:
                require(self.total + len(pixels) <= MAX_RECORD_BYTES, 'Approach evidence budget exceeded')
                with (self.directory / name).open('xb') as stream:
                    stream.write(pixels)
                self.total += len(pixels)
                self.frames[number] = rgb_sha
        else:
            require(not pixels, 'Unexpected pixels in non-frame reply')
        self.event(info)

    def close(self):
        """Close owned storage without modifying the native input owner."""
        self.stream.close()


def run_episode(bridge, binding, directory, *, clock=time.perf_counter_ns, sleep=time.sleep,
                check=lambda: None, deadline_ns=None):
    """Run the pure planner through an injected bridge; fixtures use no Windows/model/input."""
    controller = ApproachController(binding, bridge.hello, clock(), deadline_ns=deadline_ns)
    journal = EvidenceJournal(directory)
    report = dict(version=1, kind=KIND, status='failed', navigationVerified=False, meleeArrivalVerified=False,
                  combatSuccess=False, modelLoaded=False, attacksAllowed=False, releaseAcknowledged=False,
                  stopAcknowledged=False, receiptsComplete=False, error=None,
                  startedAtClientNs=controller.started_ns, deadlineClientNs=controller.deadline_ns)
    try:
        journal.event(dict(type='hello', value=bridge.hello, binding=copy.deepcopy(binding)))
        while True:
            check()
            controller.check(clock())
            started = clock()
            frame, pixels = bridge.request('frame')
            arrived = clock()
            rtt = (arrived - started) / 1e6
            # A native RPC drains terminal receipts once. Retain them before any fallible disk operation.
            intake_error = None
            try:
                controller.intake_receipts(frame)
            except BaseException as error:
                intake_error = error
            try:
                journal.frame(frame, pixels, arrived, rtt)
            except BaseException as error:
                if intake_error is not None:
                    report['terminalFrameRecordingError'] = str(error)
                    raise intake_error
                raise
            if intake_error is not None:
                raise intake_error
            outcome = controller.observe(frame, arrived, rtt)
            journal.event(dict(type='navigation', outcome=outcome, snapshot=controller.navigation.snapshot(),
                               events=controller.navigation.drain_events(), clientTimeNs=clock()))
            if controller.complete:
                report.update(status='completed', navigationVerified=True)
                break
            if outcome == 'releaseRequired' and controller.pending is None:
                response, payload = bridge.request('release')
                journal.event(dict(type='endpointRelease', response=response, payloadBytes=len(payload)))
                controller.released(response, payload, endpoint=True)
                continue
            if outcome is None and controller.pending is None:
                check()
                request = controller.next_action(clock())
                if request:
                    journal.event(dict(type='proposal', request=request, frameId=frame['frameId'],
                                       selection=copy.deepcopy(controller.pending['selection']), clientTimeNs=clock()))
                    # Recheck after synchronous evidence storage, immediately before transmission.
                    check()
                    controller.check(clock())
                    dispatched = clock()
                    fresh = controller.transmitting(dispatched)
                    response, payload = bridge.request('action', **request)
                    admission_error = None
                    try:
                        controller.admission(response, payload)
                    except BaseException as error:
                        admission_error = error
                    try:
                        journal.event(dict(type='admission', requestId=request['requestId'], response=response,
                                           payloadBytes=len(payload), clientTimeNs=clock(), dispatchedAtClientNs=dispatched,
                                           sourceAgeAtDispatchMs=fresh))
                    except BaseException as error:
                        if admission_error is not None:
                            report['admissionRecordingError'] = str(error)
                            raise admission_error
                        raise
                    if admission_error is not None:
                        raise admission_error
            sleep(.015)
    except BaseException as error:
        report.update(status='failed', error=str(error) or type(error).__name__)
    finally:
        abandoned = controller.abandon_prepared(report.get('error') or 'episode_finished_before_transmission')
        if abandoned is not None:
            try:
                journal.event(abandoned)
            except BaseException as error:
                report.update(status='failed', abandonmentRecordingError=str(error))
        # Release and stop are attempted even if the journal, clock, observation or proposal path failed.
        for command in ('release', 'stop'):
            try:
                response, payload = bridge.request(command)
                report[command] = copy.deepcopy(response)
                if command == 'release':
                    controller.released(response, payload)
                    report['releaseAcknowledged'] = True
                else:
                    require(response.get('type') == 'stopped' and not payload, 'Stop was not acknowledged')
                    controller.intake_receipts(response, final=True)
                    report['stopAcknowledged'] = True
                try:
                    journal.event(dict(type=command, response=response, payloadBytes=len(payload)))
                except BaseException as error:
                    report.update(status='failed', evidenceError=str(error))
            except BaseException as error:
                report.update(status='failed', **{command + 'Error': str(error)})
        report.update(actionProposals=controller.actions,
                      actionsAttempted=sum(row['transmissionAttempted'] for row in controller.attempts.values()),
                      actionAttempts=controller.attempt_summary(), acceptedActions=len(controller.accepted),
                      terminalReceipts=len(controller.receipts), receipts=list(controller.receipts.values()),
                      actionResponses=copy.deepcopy(controller.action_responses), endedAtClientNs=clock(),
                      receiptsComplete=controller.pending is None and set(controller.accepted) == set(controller.receipts),
                      navigation=controller.navigation.snapshot(), recordedFrames=len(journal.frames),
                      recordedBytes=journal.total, recordEvents=journal.count,
                      physicalInputDeliveryVerified=False, nativeInputJournalComplete=False)
        if not report['receiptsComplete'] or not report['releaseAcknowledged'] or not report['stopAcknowledged']:
            report['status'] = 'failed'
        try:
            journal.close()
        except BaseException as error:
            report.update(status='failed', recordingCloseError=str(error))
            if report['error'] is None:
                report['error'] = 'recording_close_failed:' + str(error)
    return report


def source_files():
    """Follow bounded local imports and the broker's explicit dynamic transport, without drive/weight scans."""
    agent = Path(__file__).resolve().parent
    broker = ROOT / 'tools/rdp-automation'
    transport = ROOT / 'tools/quest-pilot'
    directories = (agent, broker, transport)
    pending = [Path(__file__).resolve(), agent / 'stream_client.py', agent / 'resident_runtime.py',
               agent / 'scout_session.py', agent / 'map_owner.py', agent / 'combat_process_identity.py',
               agent / 'capture_scout_scene.py', agent / 'audit_encounter_approach.py']
    pending += [path for path in broker.glob('*.py') if not path.name.startswith('test_')]
    # rdp_control executes this exact path through importlib; ordinary import ASTs cannot discover it.
    # Follow its local imports, but do not enumerate unrelated quest-pilot scripts.
    pending.append(transport / 'controller-control.py')
    found = set()
    while pending:
        path = pending.pop()
        if path in found:
            continue
        require(path.parent in directories, 'Python dependency escaped its bounded source directories')
        found.add(path)
        tree = ast.parse(read_bytes(path, 2 * 1024 * 1024).decode('utf-8-sig'))
        for node in ast.walk(tree):
            names = ([node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module else
                     [part.name.split('.')[0] for part in node.names] if isinstance(node, ast.Import) else [])
            for name in names:
                for directory in directories:
                    candidate = directory / (name + '.py')
                    if candidate.is_file():
                        pending.append(candidate)
    require(len(found) <= 150, 'Unexpected Python dependency expansion')
    return sorted(found)


def source_contract():
    """Pin the exact controller, ordinary transport and broker implementation without loading them."""
    return {str(path.relative_to(ROOT)): digest(read_bytes(path, 2 * 1024 * 1024)) for path in source_files()}


def runtime_contract(executable):
    """Use the existing ordinary base interpreter, not a model environment or new installer."""
    path = local_path(executable)
    require(path.name.lower() == 'python.exe' and not (path.parent.parent / 'pyvenv.cfg').exists(),
            'This model-free worker requires the direct base Python')
    background = path.with_name('pythonw.exe')
    return dict(version=1, kind='direct-python-v1', executable=str(path),
                files={str(p): digest(read_bytes(p, 4 * 1024 * 1024)) for p in (path, background)})


def original_owner(path):
    """Reuse the sealed RDP replacement lineage and its original loaded package identities."""
    from map_owner import load_map_owner
    owner_path = local_path(path, root=LIVE)
    owner = load_map_owner(owner_path)
    lineage, sha = document(owner_path)
    require(lineage.get('kind') == 'idle-map-child-replacement' and lineage.get('identity') == owner
            and isinstance(lineage.get('protectedGame'), dict), 'A sealed original game/child lineage is required')
    replacement, replacement_sha = document(owner_path.parent / 'ensure-child.json')
    require(replacement_sha == lineage.get('replacementSha256'), 'Original package replacement evidence changed')
    pins = {}
    for role in ('root', 'child'):
        value = replacement[role]
        require({key: value[key] for key in owner[role]} == owner[role], 'Original native identity differs')
        pins[role] = dict(assemblySha256=value['assemblySha256'].lower(), appDirectory=str(Path(value['appDirectory']).resolve()))
    return owner, dict(ownerFrom=str(owner_path), ownerFromSha256=sha, nativePackages=pins,
                      protectedGame=copy.deepcopy(lineage['protectedGame']))


def prepare(output, review_path, scene_directory, owner_from, executable):
    """Seal only already reviewed original evidence; this command never connects to BetterGI."""
    folder = local_path(output, root=LIVE, existing=False)
    require(not folder.exists(), 'Use a new approach attempt directory')
    review_path = local_path(review_path, root=LIVE)
    scene_directory = local_path(scene_directory, root=LIVE)
    review, _ = document(review_path, 65536)
    owner, pins = original_owner(owner_from)
    native_plan, _ = document(scene_directory / 'plan.json')
    scene, _ = document(scene_directory / 'result.json')
    image_name = review.get('imageName')
    require(isinstance(image_name, str) and Path(image_name).name == image_name and image_name.endswith('.png'),
            'Review must select one original PNG')
    sidecar_path = scene_directory / Path(image_name).with_suffix('.json')
    sidecar, _ = document(sidecar_path)
    image_path = scene_directory / image_name
    image = read_bytes(image_path)
    helper_path = scene_directory / 'capture-helper.py'
    require(digest(read_bytes(helper_path)) == native_plan.get('captureHelperSha256')
            == digest(read_bytes(Path(__file__).with_name('capture_scout_scene.py'))), 'Passive capture helper differs')
    binding = bind_review(review, native_plan, scene, sidecar, image, expected_owner=owner)
    recent_review(review, binding)
    runtime = runtime_contract(executable)
    sources = source_contract()
    originals = dict(review=review_path, nativePlan=scene_directory / 'plan.json', nativeScene=scene_directory / 'result.json',
                     imageSidecar=sidecar_path, image=image_path, captureHelper=helper_path)
    raw = {key: read_bytes(path) for key, path in originals.items()}
    require(all(json.loads(raw[key]) == expected for key, expected in
                (('review', review), ('nativePlan', native_plan), ('nativeScene', scene), ('imageSidecar', sidecar)))
            and raw['image'] == image and digest(raw['captureHelper']) == native_plan['captureHelperSha256'],
            'Original evidence changed while preparation was reading it')
    folder.mkdir(parents=True, exist_ok=False)
    evidence = folder / 'review-evidence'
    evidence.mkdir()
    files = {}
    for key, path in originals.items():
        name = key + ('.png' if key == 'image' else '.py' if key == 'captureHelper' else '.json')
        with (evidence / name).open('xb') as stream:
            stream.write(raw[key])
        files[key] = dict(original=str(path), copy='review-evidence/' + name, sha256=digest(raw[key]))
    source_dir = folder / 'sources'
    source_dir.mkdir()
    for relative, sha in sources.items():
        payload = read_bytes(ROOT / relative, 2 * 1024 * 1024)
        require(digest(payload) == sha, 'Source changed during preparation')
        target = source_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(payload)
    plan = dict(version=1, kind=KIND, runId=uuid.uuid4().hex, createdAtUnixNs=time.time_ns(),
                policy=policy(), owner=owner, originalOwner=pins, runtime=runtime, sourceContract=sources,
                evidence=files, binding=binding, maximumHostSeconds=HOST_SECONDS,
                inputEnabledOnlyInWorker=True, modelLoaded=False, preparationStartsInput=False, explicitLaunchRequired=True)
    recent_review(review, binding)
    exclusive_json(folder / 'plan.json', plan)
    return plan


def verify_plan(path, *, fresh=True, current_sources=True):
    """Rebind frozen raw originals and current installed controller/runtime before consuming authority."""
    path = local_path(path, root=LIVE)
    require(path.name == 'plan.json', 'Expected the sealed approach plan')
    folder = path.parent
    plan, sha = document(path)
    require(plan.get('version') == 1 and plan.get('kind') == KIND and re.fullmatch('[0-9a-f]{32}', plan.get('runId', ''))
            and plan.get('maximumHostSeconds') == HOST_SECONDS and plan.get('modelLoaded') is False
            and plan.get('preparationStartsInput') is False and plan.get('explicitLaunchRequired') is True
            and canonical(plan.get('policy')) == canonical(policy()),
            'Approach plan contract changed')
    files = plan.get('evidence')
    require(isinstance(files, dict) and set(files) == {'review', 'nativePlan', 'nativeScene', 'imageSidecar', 'image', 'captureHelper'},
            'Approach raw evidence set differs')
    raw = {}
    for key, item in files.items():
        copied = local_path(folder / item['copy'], root=folder / 'review-evidence')
        raw[key] = read_bytes(copied)
        require(digest(raw[key]) == item['sha256'], 'Archived review bytes changed')
        if current_sources:
            require(digest(read_bytes(local_path(item['original'], root=LIVE))) == item['sha256'], 'Original review bytes changed')
    parsed = {key: json.loads(value) for key, value in raw.items() if key not in ('image', 'captureHelper')}
    owner = plan['owner']
    binding = bind_review(parsed['review'], parsed['nativePlan'], parsed['nativeScene'], parsed['imageSidecar'],
                          raw['image'], expected_owner=owner)
    require(canonical(binding) == canonical(plan.get('binding'))
            and digest(raw['captureHelper']) == parsed['nativePlan']['captureHelperSha256'], 'Sealed binding differs from original raw proof')
    for relative, expected in plan['sourceContract'].items():
        saved = local_path(folder / 'sources' / relative, root=folder / 'sources')
        require(digest(read_bytes(saved, 2 * 1024 * 1024)) == expected, 'Archived source changed')
    if current_sources:
        current_owner, pins = original_owner(plan['originalOwner']['ownerFrom'])
        require(current_owner == owner and pins == plan['originalOwner'], 'Original owner lineage changed')
        require(source_contract() == plan['sourceContract'], 'Installed approach/broker source changed')
        require(runtime_contract(plan['runtime']['executable']) == plan['runtime'], 'Ordinary Python runtime changed')
    if fresh:
        recent_review(parsed['review'], binding)
    return plan, folder, sha


class OwnerDiscoveryError(ValueError):
    """Retain the first bounded ownership failure even when a caller records only its error string."""

    def __init__(self, message, diagnostics):
        """Keep exact compact discovery evidence without turning a failure into a retry."""
        self.diagnostics = copy.deepcopy(diagnostics)
        super().__init__(message + ' | ownership=' + json.dumps(self.diagnostics, separators=(',', ':')))


def retain_owner_failure(report, error, field='ownerDiscoveryFailure'):
    """Keep a structured first failure before an episode or wrapper reduces it to text."""
    if isinstance(error, OwnerDiscoveryError):
        report.setdefault(field, copy.deepcopy(error.diagnostics))


def owner_pair(lifecycle, plan, *, idle=False):
    """Read only the original owners, tolerating missing advertisements but never extra endpoints or failed reads."""
    from scout_session import validate_owner_discovery, idle_child
    started = time.perf_counter_ns()
    details = dict(phase='same_user_snapshot', startedAtClientNs=started, expected=copy.deepcopy(plan['owner']))
    try:
        sid = lifecycle.transport.WinPipeApi().current_user_sid()
        prefix = 'BetterGI.ExternalControl.' + hashlib.sha256(sid.encode('utf-8')).hexdigest()[:16].upper() + '.'
        pattern = re.compile('^' + re.escape(prefix) + r'(\d+)\.(\d+)$')
        expected = {prefix + str(value['windowsSessionId']) + '.' + str(value['processId'])
                    for value in plan['owner'].values()}
        require(len(expected) == 2, 'The original owner must identify two distinct endpoints')
        # The native single-client server disposes/recreates its pipe after each request. Seed only
        # the already pinned addresses, so a missing advertisement reaches the existing connect wait.
        advertised = set(name for name in os.listdir('\\\\.\\pipe\\') if pattern.fullmatch(name))
        extra = advertised - expected
        ordered = sorted(advertised)
        details.update(advertised=ordered[:32], advertisedCount=len(ordered), advertisedTruncated=len(ordered) > 32,
                       advertisedSha256=digest(('\n'.join(ordered)).encode('utf-8')),
                       seededMissing=sorted(expected - advertised), extra=sorted(extra)[:32], extraCount=len(extra))
        # Inspect the whole snapshot before discover's 32-candidate cap. An extra advertised endpoint
        # is terminal even if it would sort outside that cap; never contact or substitute that owner.
        require(not extra, 'Additional same-user control endpoints are advertised')
        details['phase'] = 'pinned_status_reads'
        discovery = lifecycle.discover(names=sorted(advertised | expected), user_sid=sid)
        fields = ('processId', 'windowsSessionId', 'instanceNonce', 'instanceType', 'assemblySha256', 'appDirectory',
                  'uiStatus', 'childSessionId', 'childConnectedState', 'childWindowMinimized', 'remoteDesktop',
                  'automationEnabled', 'runtimeRunning', 'automationState', 'taskRunning', 'agentStreamRunning',
                  'serviceOwnsPilot', 'pilotState')
        details['instances'] = [{key: (value[:512] if isinstance(value, str) else value)
                                 for key in fields if (value := state.get(key)) is not None}
                                for state in discovery.get('instances', [])[:32]]
        details['unavailable'] = copy.deepcopy(discovery.get('unavailable', []))
        details['phase'] = 'original_owner_validation'
        root, child = validate_owner_discovery(lifecycle, plan['owner'], discovery)
        for role, state in (('root', root), ('child', child)):
            pin = plan['originalOwner']['nativePackages'][role]
            require(state.get('assemblySha256', '').lower() == pin['assemblySha256']
                    and str(Path(state.get('appDirectory', '')).resolve()) == pin['appDirectory'], 'Original native package changed')
        require(not idle or idle_child(child), 'Original child is not idle and released')
        return root, child
    except Exception as error:
        details.update(elapsedMs=(time.perf_counter_ns() - started) / 1_000_000,
                       errorType=type(error).__name__, error=str(error)[:512])
        raise OwnerDiscoveryError(str(error), details) from error


def stop_requested(folder):
    """An existing local STOP or parent STOP always revokes this one attempt."""
    return (folder / 'STOP').exists() or (folder.parent / 'STOP').exists()


def ordinary_identity(session, contract):
    """Record the broker child with the same direct native creation/token witness used by combat."""
    from resident_runtime import control_module
    control_module()
    from child_runner import require_ordinary_rdp, windows_identity, process_identity
    identity = windows_identity()
    require_ordinary_rdp(identity, session)
    require(identity['integrityRid'] == 8192, 'Approach worker requires an ordinary medium-integrity RDP token')
    current = process_identity(os.getpid())
    require(current['parentProcessId'] == os.getppid() and current['windowsSessionId'] == session
            and Path(current['executable']) == Path(contract['executable']), 'Worker executable/session changed')
    return dict(identity, processId=os.getpid(), parentProcessId=os.getppid(), processIdentity=current)


def worker(plan_path):
    """One broker-owned worker may create one authenticated input lease; it never retries an unknown start."""
    from resident_runtime import control_module, verify_bridge_identity
    from stream_client import Bridge
    from native_combat import negotiate as negotiate_combat
    from native_ground_control import negotiate as negotiate_ground
    plan, folder, sha = verify_plan(plan_path)
    claim, _ = document(folder / 'CONSUMED.json')
    validate_claim(claim, plan['runId'], sha)
    require(claim['startedMonotonicNs'] <= time.perf_counter_ns() < claim['deadlineMonotonicNs'],
            'Missing or expired one-shot host claim')
    review_deadline = original_review_deadline(plan['binding'], client_ns=claim['startedMonotonicNs'],
                                              wall_ns=claim['startedAtUnixNs'])
    identity = ordinary_identity(plan['owner']['child']['windowsSessionId'], plan['runtime'])
    exclusive_json(folder / 'WORKER.json', dict(runId=plan['runId'], planSha256=sha, worker=identity))
    lifecycle = control_module()
    report = dict(version=1, kind=KIND, runId=plan['runId'], planSha256=sha, status='failed', worker=identity,
                  nativeStartAttempted=False, nativeStartOutcome='not_attempted', ownerIdleMinimizedAfter=False,
                  cleanupVerified=False, modelLoaded=False, episode=None, error=None)
    report['originalReviewDeadlineClientNs'] = review_deadline
    bridge = None
    owned_handle = None
    authenticated = False
    lease_deadline = None
    next_owner_check = 0

    def check():
        """Keep the operator stop, absolute host deadline and original minimized owner effective during waits."""
        nonlocal next_owner_check
        now = time.perf_counter_ns()
        require(not stop_requested(folder) and now < claim['deadlineMonotonicNs'], 'Operator or host deadline stop')
        if now >= next_owner_check:
            try:
                owner_pair(lifecycle, plan)
            except OwnerDiscoveryError as error:
                retain_owner_failure(report, error)
                raise
            next_owner_check = time.perf_counter_ns() + 250_000_000
        # Discovery is synchronous. A STOP or expiry during that call must win before any subsequent input/start.
        require(not stop_requested(folder) and time.perf_counter_ns() < claim['deadlineMonotonicNs']
                and time.perf_counter_ns() < review_deadline
                and time.time_ns() < plan['binding']['reviewedAtUnixNs'] + MAX_REVIEW_SECONDS * 1_000_000_000
                and (lease_deadline is None or time.perf_counter_ns() < lease_deadline),
                'Operator or host/lease deadline stop after owner discovery')

    try:
        _, child = owner_pair(lifecycle, plan, idle=True)
        check()
        # Include listener creation and all negotiations in the same ten-second input-lease budget.
        lease_started = time.perf_counter_ns()
        lease_deadline = min(claim['deadlineMonotonicNs'], review_deadline, lease_started + 10_000_000_000)
        check()
        report.update(nativeStartAttempted=True, nativeStartOutcome='unresolved', leaseStartedMonotonicNs=lease_started,
                      leaseDeadlineMonotonicNs=lease_deadline)
        started = lifecycle.start_agent(child, 5, enable_input=True, observation_profile=PROFILE)
        require({key: started[key] for key in ('processId', 'windowsSessionId', 'instanceNonce')} == plan['owner']['child'],
                'Listener was not created by the original child')
        report.update(nativeStartOutcome='confirmed', createdListener=copy.deepcopy(started))
        bridge = Bridge(started['agentPipeName'])
        owned_handle = bridge.handle
        verify_bridge_identity(owned_handle, child['processId'], child['windowsSessionId'])
        authenticated = True
        report['bridgeIdentityVerified'] = True
        game_binding = bridge.hello.get('mapInspection') or {}
        require(game_binding.get('gameProcessId') == plan['originalOwner']['protectedGame']['processId']
                and type(game_binding.get('gameWindowHandle')) is int and game_binding['gameWindowHandle'] > 0
                and game_binding.get('wgcOnly') is True and game_binding.get('maximumSourceAgeMs') == 150,
                'Native runtime no longer targets the original protected game process')
        report['nativeGameBinding'] = copy.deepcopy(game_binding)
        check()
        response, pixels = bridge.request('enableNavigationGuidance', navigationProfile=SCOUT_PROFILE)
        require(response.get('enabled') is True and not pixels, 'Native navigation was not enabled')
        validate_capability(response.get('capability'), SCOUT_PROFILE)
        require(response['capability'] == plan['binding']['navigationCapability'], 'Navigation capability changed since review')
        require(negotiate_combat(bridge) == plan['binding']['nativeCombatObservation'], 'Combat metadata changed since review')
        ground, _ = negotiate_ground(bridge)
        require(ground == plan['binding']['nativeGroundControlObservation'], 'Ground-control capability changed since review')
        check()
        report['episode'] = run_episode(bridge, plan['binding'], folder / 'recording', check=check, deadline_ns=lease_deadline)
        report['status'] = report['episode']['status']
    except BaseException as error:
        retain_owner_failure(report, error)
        report.update(status='failed', error=str(error) or type(error).__name__)
    finally:
        if bridge is not None and authenticated and report['episode'] is None:
            # Negotiation may fail before the episode owns cleanup; retire only this authenticated pipe.
            for command in ('release', 'stop'):
                try:
                    response, payload = bridge.request(command)
                    report['bootstrap' + command.title()] = response
                    require(not payload and response.get('type') == ('released' if command == 'release' else 'stopped'),
                            'Bootstrap cleanup was not acknowledged')
                except BaseException as error:
                    report['bootstrap' + command.title() + 'Error'] = str(error)
        if owned_handle is not None:
            # Bridge exposes a file handle, not close(); never send cleanup commands to an unverified peer.
            try:
                owned_handle.close()
                report['ownedHandleClosed'] = True
            except BaseException as error:
                report.update(status='failed', pipeCloseError=str(error))
        # Public stop_agent identifies an owner rather than our lease, so it is deliberately not called.
        try:
            deadline = min(claim['deadlineMonotonicNs'], time.perf_counter_ns() + 5_000_000_000)
            while True:
                from scout_session import idle_child
                _, child = owner_pair(lifecycle, plan)
                if idle_child(child):
                    report['ownerIdleMinimizedAfter'] = True
                    break
                require(time.perf_counter_ns() < deadline, 'Original child cleanup remains unresolved')
                time.sleep(.05)
        except BaseException as error:
            retain_owner_failure(report, error, 'ownerCleanupFailure')
            report.update(status='failed', cleanupError=str(error))
        episode = report.get('episode') or {}
        report['cleanupVerified'] = bool(report['ownerIdleMinimizedAfter'] and episode.get('releaseAcknowledged')
                                         and episode.get('stopAcknowledged') and episode.get('receiptsComplete')
                                         and report.get('ownedHandleClosed') is True and authenticated)
        if not report['cleanupVerified']:
            report['status'] = 'failed'
        exclusive_json(folder / 'worker-result.json', report)
    return report


def launch(plan_path):
    """Consume a reviewed plan once and broker one ordinary RDP worker; no live action occurs during prepare/verify."""
    from concurrent.futures import ThreadPoolExecutor
    from resident_runtime import control_module
    from combat_process_identity import verify_worker_broker
    plan, folder, sha = verify_plan(plan_path)
    lifecycle = control_module()
    root, _ = owner_pair(lifecycle, plan, idle=True)
    require(not stop_requested(folder), 'Operator STOP is present')
    started = time.perf_counter_ns()
    claim = dict(runId=plan['runId'], planSha256=sha, hostProcessId=os.getpid(), startedAtUnixNs=time.time_ns(),
                 startedMonotonicNs=started, deadlineMonotonicNs=started + HOST_SECONDS * 1_000_000_000)
    exclusive_json(folder / 'CONSUMED.json', claim)
    command = [plan['runtime']['executable'], '-B', '-X', 'utf8', str(Path(__file__).resolve()), 'worker', '--plan', str(Path(plan_path).resolve())]
    report = dict(version=1, kind=KIND, runId=plan['runId'], planSha256=sha, status='failed', command=command,
                  launchAttempts=1, broker=None, worker=None, cleanupVerified=False, ownerIdleMinimizedAfter=False, error=None)
    exclusive_json(folder / 'launch.json', dict(report, claim=claim))

    def request_stop(reason):
        """Stop the cooperative worker locally without affecting any other listener."""
        retain_owner_failure(report, reason)
        report.setdefault('stopReason', str(reason))
        try:
            with (folder / 'STOP').open('x', encoding='utf-8') as stream:
                stream.write(str(reason))
        except FileExistsError:
            pass

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lifecycle.run_command, root, command, str(ROOT), plan['runtime']['executable'],
                                 HOST_SECONDS, str(folder / 'jobs'), 262144)
            while not future.done():
                try:
                    require(not stop_requested(folder), 'Operator STOP')
                    require(time.perf_counter_ns() < claim['deadlineMonotonicNs'], 'Host deadline')
                    owner_pair(lifecycle, plan)
                except BaseException as error:
                    request_stop(error)
                time.sleep(.1)
            broker = future.result()
        report['broker'] = broker
        terminal, _ = document(folder / 'worker-result.json')
        report['worker'] = terminal
        require(terminal.get('runId') == plan['runId'] and terminal.get('planSha256') == sha, 'Worker result does not belong to this plan')
        identity = terminal['worker']
        require(broker.get('windowsSessionId') == plan['owner']['child']['windowsSessionId']
                and broker.get('remoteDesktop') is True and broker.get('elevated') is False
                and broker.get('integrityRid') == 8192 and broker.get('timedOut') is False
                and broker.get('outputIncomplete') is False, 'Broker execution was not ordinary, complete and bounded')
        verify_worker_broker(identity, broker, plan['runtime'])
        owner_pair(lifecycle, plan, idle=True)
        report['ownerIdleMinimizedAfter'] = True
        report['cleanupVerified'] = terminal.get('cleanupVerified') is True
        if (terminal.get('status') == 'completed' and report['cleanupVerified'] and broker.get('success') is True
                and broker.get('returnCode') == 0 and not report.get('stopReason')):
            report['status'] = 'completed'
    except BaseException as error:
        report['error'] = str(error) or type(error).__name__
        request_stop(error)
    exclusive_json(folder / 'result.json', report)
    return report


def main():
    """Expose separate preparation, validation, explicit launch and broker-only worker commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_command = commands.add_parser('prepare', help='Offline: seal an already reviewed anchored passive capture')
    prepare_command.add_argument('--output', required=True)
    prepare_command.add_argument('--review', required=True)
    prepare_command.add_argument('--scene', required=True)
    prepare_command.add_argument('--owner-from', required=True)
    prepare_command.add_argument('--python', default=r'C:\Programs\Python\Python311\python.exe')
    for name in ('verify', 'launch', 'worker'):
        commands.add_parser(name).add_argument('--plan', required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.output, args.review, args.scene, args.owner_from, args.python)
        print(json.dumps(dict(status='prepared', runId=result['runId'], plan=str(Path(args.output).resolve() / 'plan.json'),
                              liveStarted=False, modelLoaded=False)))
        return 0
    if args.command == 'verify':
        result, _, sha = verify_plan(args.plan)
        print(json.dumps(dict(status='verified', runId=result['runId'], planSha256=sha, liveStarted=False)))
        return 0
    result = worker(args.plan) if args.command == 'worker' else launch(args.plan)
    print(json.dumps(dict(status=result['status'], runId=result['runId'], cleanupVerified=result['cleanupVerified'])))
    return 0 if result['status'] == 'completed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
