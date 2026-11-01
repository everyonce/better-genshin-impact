"""Pure authority and state machine for one reviewed, three-pulse combat experiment.

This module performs no I/O. A caller must hold ``intake_lock`` across source intake,
the final prepare/write/admission transaction, and release/acknowledgement. It must
journal returned events, retain a stopped observation's pixels before reader failure,
and attempt release in a finally path even when validation or recording fails.
It does not confer scout authority, prove enemy identity, or evaluate damage/kills.
"""
import copy
import hashlib
import json
import threading
from collections import OrderedDict
from types import MappingProxyType

from native_combat import finite, scene_capability, validate_capability, validate_frame


MODEL = 'open-p2p'
KIND = 'reviewed-combat-trial-v1'
REVIEW_KIND = 'combat-trial-review-v1'
PROFILE = 'p2p-native-hamming-192-v1'
SINGLE_SCOPE = 'single-enemy-v1'
GROUP_SCOPE = 'reviewed-group-up-to-three-v1'
FOUR_SCOPE = 'reviewed-group-up-to-four-v1'
# A separately reviewed policy permits one released freshness interruption, never an action retry.
STALE_RECOVERY_MODE = 'released-source-stale-once-v1'
STALE_RELEASE_REASON = 'sourceStaleReacquisition'


def stale_recovery_policy():
    """Return the fixed opt-in descriptor without widening any attack or lifetime bound."""
    return dict(kind=STALE_RECOVERY_MODE, maximumRecoveries=1, confirmationSources=2,
                postReleaseDelayMs=60, resetsDeadlines=False, reacquisitionResetsHistory=False,
                existingAcceptanceGapHistoryResetMs=500)


def source_stale_recovery_enabled(value):
    """Require an exact explicit descriptor; null, tunable values and older scopes cannot opt in."""
    policy = value.get('policy') if isinstance(value, dict) else None
    require(isinstance(policy, dict), 'Missing combat policy')
    if 'sourceStaleRecoveryPolicy' not in policy:
        return False
    require(combat_scope(value) == FOUR_SCOPE
            and canonical(policy['sourceStaleRecoveryPolicy']) == canonical(stale_recovery_policy()),
            'Invalid explicit combat stale-source recovery policy')
    return True


def validated_trial_policy(value):
    """Join the named scope and optional recovery to every unchanged fixed policy field."""
    result = trial_policy(combat_scope(value), source_stale_recovery=source_stale_recovery_enabled(value))
    require(canonical(value.get('policy')) == canonical(result), 'Combat policy differs from its fixed bounds')
    return result

# Only these named reviewed experiments exist; a request cannot tune a numeric cap.
SCOPE_MAXIMUMS = MappingProxyType({SINGLE_SCOPE: 1, GROUP_SCOPE: 3, FOUR_SCOPE: 4})


def scope_maximum(scope):
    """Resolve one fixed reviewed scope, never a caller-selected arbitrary enemy count."""
    require(type(scope) is str and scope in SCOPE_MAXIMUMS, 'Unknown combat scope')
    return SCOPE_MAXIMUMS[scope]


def scope_fields(scope):
    """Declare only the named opt-in; omitted fields preserve the original single-enemy bytes."""
    maximum = scope_maximum(scope)
    return {} if scope == SINGLE_SCOPE else dict(combatScope=scope, maximumEnemyBarCandidates=maximum)


def combat_scope(value):
    """Reject partial or tunable scope declarations instead of inferring authority from target counts."""
    require(isinstance(value, dict), 'Missing combat scope document')
    if not any(key in value for key in ('combatScope', 'maximumEnemyBarCandidates')):
        return SINGLE_SCOPE
    scope = value.get('combatScope')
    require(type(scope) is str and scope in SCOPE_MAXIMUMS and scope != SINGLE_SCOPE
            and type(value.get('maximumEnemyBarCandidates')) is int
            and value['maximumEnemyBarCandidates'] == scope_maximum(scope), 'Invalid explicit combat scope or maximum')
    return scope


def inspected_count(value, scope):
    """Bind the separately inspected visible count; native candidate count never grants the opt-in."""
    count = value.get('inspectedVisibleEnemyCount')
    maximum = scope_maximum(scope)
    if scope != SINGLE_SCOPE:
        require(type(count) is int and 1 <= count <= maximum,
                'Group combat requires an inspected visible enemy count of 1..' + str(maximum))
    else:
        require(count is None or type(count) is int and count == 1, 'Single-enemy review cannot declare a visible group')
    return count


def trial_policy(scope=SINGLE_SCOPE, *, source_stale_recovery=False):
    """Return a named fixed scope; both earlier policies remain byte-for-byte unchanged."""
    result = dict(version=1, maximumSeconds=5, maximumActions=3, maximumSourceAgeMs=150,
                minimumHoldMs=33, maximumHoldMs=100, stopTemperatureC=78,
                healthFractionDrop=0.08, admissionSources=2, postActionDelayMs=60,
                allowedKeys=['LBUTTON'], maximumOutstandingActions=1,
                requireSingleEnemyBarCandidate=True, retryAllowed=False,
                renewAllowed=False, goalFrozen=True, enemyIdentityVerified=False,
                damageVerified=False, killVerified=False)
    if scope_fields(scope):
        result.update(version=2, requireSingleEnemyBarCandidate=False, minimumEnemyBarCandidates=1,
                      **scope_fields(scope))
    require(type(source_stale_recovery) is bool, 'Combat recovery opt-in must be boolean')
    if source_stale_recovery:
        require(scope == FOUR_SCOPE, 'Combat stale-source recovery requires the reviewed four-enemy scope')
        result.update(version=3, sourceStaleRecoveryPolicy=stale_recovery_policy())
    return result


def canonical(value):
    """Encode a finite JSON value with type-sensitive equality and stable digests."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    """Hash retained bytes without reading or rewriting their original representation."""
    return hashlib.sha256(value).hexdigest()


def require(condition, message):
    """Reject malformed authority or evidence before any action can be prepared."""
    if not condition:
        raise ValueError(message)


def retained(value):
    """Preserve malformed trigger data as serializable evidence, including nonfinite values."""
    if isinstance(value, dict):
        return {str(key): retained(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [retained(item) for item in value]
    if value is None or type(value) in (str, bool, int) or finite(value):
        return value
    return repr(value)


def sensor_frame(frame, *, source_stale_recovery=False):
    """Retain source, readiness and HUD proof without copying policy pixels or unrelated telemetry."""
    keys = ('type', 'frameId', 'capturedAtMs', 'sourceWidth', 'sourceHeight', 'sourceFrame',
            'sourceTimestampKind', 'sourceFrameAgeMs', 'serverNowMs', 'droppedReceipts', 'combatEvidence', 'frameWorldReadiness',
            'worldReadiness', 'inputAvailable')
    if source_stale_recovery:
        keys += ('receipts', 'executionContext')
    return retained({key: frame[key] for key in keys if key in frame}) if isinstance(frame, dict) else retained(frame)


def validate_owner(owner):
    """Require the exact root/child process, Windows session and instance identities."""
    require(isinstance(owner, dict) and set(owner) == {'root', 'child'}, 'Missing combat owner')
    for item in owner.values():
        require(isinstance(item, dict) and set(item) == {'processId', 'windowsSessionId', 'instanceNonce'}
                and type(item['processId']) is int and item['processId'] > 0
                and type(item['windowsSessionId']) is int and item['windowsSessionId'] >= 0
                and isinstance(item['instanceNonce'], str) and bool(item['instanceNonce']), 'Invalid combat owner')
    require(owner['root']['processId'] != owner['child']['processId']
            and owner['root']['windowsSessionId'] != owner['child']['windowsSessionId'], 'Combat owner is not an RDP child')


def health_reason(evidence, baseline, maximum_candidates=1):
    """Classify valid hazards before readiness checks, including while explicitly released."""
    if evidence['playerHealthColor'] != 'green':
        return 'redOrAmbiguousHealth'
    if evidence['playerHealthFractionEstimate'] <= baseline - 0.08:
        return 'healthFractionDrop'
    if evidence['redMaskOverloaded'] or len(evidence['enemyBarCandidates']) > maximum_candidates:
        return 'ambiguousTarget'
    return None


def bind_review(review_bytes, plan_bytes, scene_bytes, sidecar_bytes, image_bytes, goal_bytes):
    """Join reviewed native pixels to exact observations, independently of decimated stable samples.

    The caller supplies the original retained bytes. Hashes are computed here, so a
    changed parsed object cannot silently keep a previous file's digest. Fresh live
    admission remains mandatory: this historical review never acts as a live frame.
    """
    blobs = (review_bytes, plan_bytes, scene_bytes, sidecar_bytes, image_bytes, goal_bytes)
    require(all(type(blob) is bytes and 0 < len(blob) <= 16 * 1024 * 1024 for blob in blobs), 'Invalid combat review bytes')
    review, plan, scene, sidecar, goal = [json.loads(blob) for blob in
                                       (review_bytes, plan_bytes, scene_bytes, sidecar_bytes, goal_bytes)]
    require(all(isinstance(item, dict) for item in (review, plan, scene, sidecar, goal)), 'Invalid combat review objects')
    scope = combat_scope(review)
    maximum_candidates = scope_maximum(scope)
    visible_count = inspected_count(review, scope)
    require(review.get('kind') == REVIEW_KIND and review.get('sceneLabel') == 'enemy-visible'
            and review.get('attacksAllowed') == ['LBUTTON']
            and canonical(review.get('policy')) == canonical(validated_trial_policy(review)), 'Missing separate bounded combat authority')
    note = review.get('inspectionNote')
    require(isinstance(note, str) and 20 <= len(note.strip()) <= 2000, 'Combat review needs an inspection note')
    hp, maximum = review.get('inspectedHealth'), review.get('inspectedMaximumHealth')
    require(type(hp) is int and type(maximum) is int and 0 < hp <= maximum, 'Invalid inspected combat health')
    owner = review.get('owner')
    validate_owner(owner)
    require(canonical(plan.get('owner')) == canonical(owner) and plan.get('enableInput') is False
            and plan.get('modelLoaded') is False and scene.get('status') == 'completed'
            and scene.get('inputEnabled') is False and scene.get('modelLoaded') is False
            and scene.get('ownerIdleMinimizedAfter') is True, 'Combat review is not a completed passive owner-bound scene')
    require(review.get('imageName') == scene.get('selectedImageName')
            and isinstance(review.get('imageName'), str) and bool(review['imageName'])
            and digest(image_bytes) == review.get('imageSha256') == scene.get('selectedImageSha256') == sidecar.get('imageSha256')
            and digest(goal_bytes) == review.get('goalSha256'), 'Combat review image or frozen goal differs')
    frame_id = sidecar.get('frameId')
    require(type(frame_id) is int and frame_id > 0 and scene.get('qualifiedImageFrameId') == frame_id
            and isinstance(scene.get('observations'), list), 'Missing selected combat observation')
    rows = [row for row in scene['observations'] if isinstance(row, dict) and row.get('frameId') == frame_id]
    require(bool(rows), 'Selected combat image has no exact observation')
    frame = rows[0]
    fields = ('frameId', 'capturedAtMs', 'sourceWidth', 'sourceHeight', 'sourceFrame', 'sourceTimestampKind')
    # Poll envelopes may repeat one retained image with newer age/receipt telemetry.
    # Every copy must still describe the same pixels, readiness and HUD evidence.
    for row in rows:
        require(all(canonical(row.get(key)) == canonical(frame.get(key)) for key in (*fields, 'frameWorldReadiness'))
                and canonical(CombatTrialGuard._evidence_identity(row)) == canonical(CombatTrialGuard._evidence_identity(frame)),
                'Selected combat observation has contradictory repeated-source evidence')
    require(all(canonical(frame.get(key)) == canonical(sidecar.get(key)) for key in fields)
            and sidecar.get('freshnessContractVersion') == 2 and sidecar.get('evidence') == 'WorldHud'
            and canonical(sidecar.get('worldReadiness')) == canonical(frame.get('frameWorldReadiness')),
            'Selected combat sidecar differs from its observation')
    require(image_bytes[:8] == b'\x89PNG\r\n\x1a\n' and image_bytes[12:16] == b'IHDR'
            and int.from_bytes(image_bytes[16:20], 'big') == frame['sourceWidth']
            and int.from_bytes(image_bytes[20:24], 'big') == frame['sourceHeight'], 'Combat PNG geometry differs')
    evidence = validate_frame(frame,scene_capability(scene))
    require(evidence is not None and evidence['state'] == 'valid'
            and health_reason(evidence, hp / maximum, maximum_candidates) is None
            and 1 <= len(evidence['enemyBarCandidates']) <= (visible_count or 1),
            'Reviewed combat scene lacks healthy, unambiguous native target evidence')
    require(frame.get('sourceTimestampKind') == 'wgc_reported_compositor_qpc'
            and finite(frame.get('sourceFrameAgeMs')) and 0 <= frame['sourceFrameAgeMs'] < 150
            and frame.get('inputAvailable') is True and frame.get('frameWorldReadiness', {}).get('ready') is True,
            'Reviewed combat image lacks fresh world evidence')
    binding = dict(kind=KIND, policy=validated_trial_policy(review), owner=owner, inspectedHealth=hp,
                   inspectedMaximumHealth=maximum, baselineHealthFraction=hp / maximum,
                   reviewedFrame=sensor_frame(frame), imageName=review['imageName'], **scope_fields(scope))
    if visible_count is not None:
        binding['inspectedVisibleEnemyCount'] = visible_count
    for name, blob in zip(('review', 'plan', 'scene', 'sidecar', 'image', 'goal'), blobs):
        binding[name + 'Sha256'] = digest(blob)
    return copy.deepcopy(binding)


def validate_binding(binding):
    """Reject scout reuse, changed bounds and incomplete combat provenance at construction."""
    scope = combat_scope(binding)
    visible_count = inspected_count(binding, scope)
    maximum_candidates = scope_maximum(scope)
    require(binding.get('kind') == KIND
            and canonical(binding.get('policy')) == canonical(validated_trial_policy(binding)), 'Invalid combat trial binding')
    validate_owner(binding.get('owner'))
    hp, maximum = binding.get('inspectedHealth'), binding.get('inspectedMaximumHealth')
    require(type(hp) is int and type(maximum) is int and 0 < hp <= maximum
            and finite(binding.get('baselineHealthFraction')) and binding['baselineHealthFraction'] == hp / maximum,
            'Combat baseline differs from reviewed health')
    for name in ('review', 'plan', 'scene', 'sidecar', 'image', 'goal'):
        value = binding.get(name + 'Sha256')
        require(isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'Missing combat provenance hash')
    frame = binding.get('reviewedFrame')
    require(isinstance(frame, dict), 'Missing reviewed combat frame')
    evidence = validate_frame(frame)
    require(evidence is not None and evidence['state'] == 'valid'
            and health_reason(evidence, hp / maximum, maximum_candidates) is None
            and 1 <= len(evidence['enemyBarCandidates']) <= (visible_count or 1), 'Invalid reviewed combat target or health')


def proposal_rejection(proposal):
    """Accept an unchanged single normal-attack step; never project mixed actions into attacks."""
    if not isinstance(proposal, dict) or proposal.get('parseValid') is not True or proposal.get('scrollUnsupported', False) is not False:
        return 'invalidProposal'
    steps = proposal.get('steps')
    if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], dict):
        return 'notOneStep'
    step = steps[0]
    if set(step) != {'keys', 'mouseDx', 'mouseDy', 'durationMs'} or step['keys'] != ['LBUTTON']:
        return 'notPureNormalAttack'
    if any(type(step[key]) is not int or step[key] != 0 for key in ('mouseDx', 'mouseDy')):
        return 'cameraMovement'
    if type(step['durationMs']) is not int or not 33 <= step['durationMs'] <= 100:
        return 'holdOutsideBounds'
    return None


class CombatTrialStop(RuntimeError):
    """A terminal trial latch; its retained trigger must be saved before reader failure."""


class CombatTrialGuard:
    """Gate one lease, one outstanding attack and all terminal/post-release evidence."""

    def __init__(self, binding, owner, hello, started_ns):
        """Pin separate reviewed authority and the authenticated native lease before intake starts."""
        validate_binding(binding)
        require(type(started_ns) is int and started_ns >= 0, 'Invalid combat start clock')
        self.intake_lock = threading.RLock()
        self._binding = copy.deepcopy(binding)
        self._maximum_candidates = scope_maximum(combat_scope(binding))
        self._native_capability=validate_capability(hello.get('combatObservation') if isinstance(hello,dict) else None)
        validate_frame(self._binding['reviewedFrame'],self._native_capability)
        self._sha = digest(canonical(binding))
        self._hello = self._identity(owner, hello)
        self._started = started_ns
        self._deadline = started_ns + 5_000_000_000
        self._phase, self._reason = 'awaitingEvidence', 'awaitingFreshTarget'
        self._trip = self._last = self._release = self._pending = None
        self._armed = self._target_confirmed = self._eligible = False
        self._sources, self._accepted = 0, 0
        self._last_frame_id = 0
        self._world_epoch = None
        self._completed, self._requests = [], set()
        self._stale_recovery_enabled = source_stale_recovery_enabled(binding)
        self._stale_recovery = dict(policy=stale_recovery_policy(), used=0, pending=None, completed=[], existingHistoryResets=[])
        self._frames = OrderedDict()

    def _identity(self, owner, hello):
        """Bind the current authenticated child and native session without accepting a new owner."""
        require(canonical(owner) == canonical(self._binding['owner']), 'Combat owner changed')
        require(isinstance(hello, dict) and hello.get('inputEnabled') is True
                and hello.get('supportsRelease') is True and hello.get('supportsStartBeforeMs') is True
                and hello.get('observationProfile') == PROFILE and type(hello.get('goalVersion')) is int
                and hello['goalVersion'] == 1 and 'LBUTTON' in hello.get('allowedKeys', []), 'Invalid combat input lease')
        validate_capability(hello.get('combatObservation'),self._native_capability)
        require(all(isinstance(hello.get(key), str) and bool(hello[key]) for key in ('sessionId', 'ownerEpoch')), 'Missing combat lease identity')
        return {key: hello[key] for key in ('sessionId', 'ownerEpoch', 'goalVersion')}

    def snapshot(self):
        """Return detached terminal accounting; completion is not a damage or kill claim."""
        with self.intake_lock:
            result = dict(bindingSha256=self._sha, phase=self._phase, reason=self._reason,
                armed=self._armed, evidenceReady=self._eligible, startedNs=self._started, deadlineNs=self._deadline,
                lease=self._hello, acceptedActions=self._accepted, completedActions=len(self._completed),
                confirmationSources=self._sources, pending=self._pending, completed=self._completed,
                lastObservation=self._last, lastRelease=self._release, trip=self._trip,
                trialComplete=self._phase == 'complete', enemyIdentityVerified=False,
                damageVerified=False, killVerified=False)
            if self._stale_recovery_enabled:
                result['sourceStaleRecovery'] = self._stale_recovery
            return copy.deepcopy(result)

    def _event(self, kind, now_ns, **data):
        """Attach the immutable authority digest and current state to replayable evidence."""
        return dict(type='combatTrial' + kind, bindingSha256=self._sha, clientTimeNs=now_ns,
                    **retained(data), state=self.snapshot())

    def _stop(self, reason, now_ns, **trigger):
        """Latch the first cause and its metadata before callers can fail or attempt cleanup."""
        if self._trip is None:
            self._trip = dict(reason=reason, clientTimeNs=now_ns, **retained(trigger))
        self._phase, self._reason = 'stopped', self._trip['reason']
        self._eligible = False

    def fail(self, reason, now_ns, **trigger):
        """Retain transport, thermal, control or recording failures without retry authority."""
        with self.intake_lock:
            self._stop(reason, now_ns, **trigger)
            return self._event('Stop', now_ns, trigger=self._trip)

    def tick(self, now_ns):
        """End a noncompleted trial at its original deadline, including an unfinished final pulse."""
        with self.intake_lock:
            if type(now_ns) is not int or now_ns < self._started:
                self._stop('invalidClientClock', now_ns)
            elif now_ns >= self._deadline and self._phase not in ('complete', 'stopped'):
                self._stop('trialDeadline', now_ns, pending=self._pending)
            return self.snapshot()

    def _live(self, now_ns):
        """Recheck the latch under the intake lock immediately before any dispatch boundary."""
        self.tick(now_ns)
        if self._trip is not None:
            raise CombatTrialStop('Combat trial stopped: ' + self._trip['reason'])

    @staticmethod
    def _evidence_identity(frame):
        """Exclude only poll latency and recognition duration from immutable pixel evidence."""
        evidence = copy.deepcopy(frame['combatEvidence'])
        evidence.pop('frameId', None)
        evidence.pop('recognitionMs', None)
        return dict(sourceFrame=frame['sourceFrame'], evidence=evidence,
                    sourceWidth=frame['sourceWidth'], sourceHeight=frame['sourceHeight'])

    @staticmethod
    def _age(observation, now_ns):
        """Use the first receipt time plus full measured transport cost, never refresh a cached source."""
        return observation['ageAtReceiptMs'] + (now_ns - observation['clientTimeNs']) / 1e6 + observation['roundTripMs']

    def _stale_source_transition(self, frame, now_ns):
        """Latch one proven, released source-age interruption; never adopt an unexplained epoch."""
        if not self._stale_recovery_enabled:
            return
        current, gate = frame.get('worldReadiness'), frame.get('frameWorldReadiness')
        if not isinstance(current, dict) or not isinstance(gate, dict):
            require(self._stale_recovery['pending'] is None, 'Combat reacquisition lost native readiness evidence')
            return
        pending = self._stale_recovery['pending']
        if pending is not None or current.get('reason') == 'world_observation_stale':
            require(frame.get('receipts') == [], 'Combat stale-source observation contains an unexpected receipt')
            context = frame.get('executionContext')
            if context is not None:
                require(isinstance(context, dict) and context.get('active', 'missing') is None
                        and (context.get('trackedState') or {}).get('heldKeys') == []
                        and context.get('telemetryComplete') is True and context.get('evictedEvents') == 0,
                        'Combat stale-source observation contradicts drained input accounting')
        if pending is not None:
            trigger_source = pending['trigger']['frame']['sourceFrame']
            source = frame.get('sourceFrame') or {}
            require(source.get('captureEpoch') == trigger_source['captureEpoch']
                    and (current.get('sourceFrame') or {}).get('captureEpoch') == trigger_source['captureEpoch']
                    and type(source.get('timestamp100ns')) is int
                    and source['timestamp100ns'] >= trigger_source['timestamp100ns']
                    and finite(source.get('freshnessAtMs'))
                    and source['freshnessAtMs'] >= trigger_source['freshnessAtMs'],
                    'Combat reacquisition changed its original capture source')
            expected = (pending['release']['response']['worldReadiness']['epoch'] if pending.get('release')
                        else pending['trigger']['frame']['worldReadiness']['epoch'])
            require(current.get('epoch') == expected, 'Combat reacquisition epoch changed without its release')
            require(type(frame.get('inputAvailable')) is bool, 'Combat reacquisition input availability is unknown')
            # A later native availability sample can expose focus loss before either readiness snapshot updates.
            if current.get('ready') is True and gate.get('ready') is True and gate.get('epoch') == expected:
                require(frame['inputAvailable'], 'Combat reacquisition lost input availability despite positive readiness')
            # Native confirmation and our own acknowledged release carry no input authority.
            allowed = ('world_ready', 'world_confirming', 'client_release', 'world_observation_invalidated') if pending.get('release') else (
                'world_observation_stale', 'world_confirming', 'world_ready')
            require(current.get('reason') in allowed, 'Combat reacquisition encountered a non-stale interruption')
            evidence = frame.get('combatEvidence')
            require(isinstance(evidence, dict) and (evidence.get('state') == 'valid' or (
                evidence.get('state') == 'unavailable' and evidence.get('reason') == 'world_not_ready'
                and gate.get('ready') is False and gate.get('reason') in
                    ('world_confirming', 'client_release', 'world_observation_invalidated')
                and gate.get('epoch') == expected)), 'Combat reacquisition lost known native HUD evidence')
            for waiting_gate in (current, gate):
                if waiting_gate.get('reason') == 'world_observation_invalidated':
                    require(pending.get('release') is not None, 'Combat invalidation preceded its owned release')
                    barrier = pending['release']['response']['serverNowMs']
                    waiting_source = waiting_gate.get('sourceFrame') or {}
                    require(waiting_gate.get('ready') is False and waiting_gate.get('epoch') == expected
                            and waiting_source.get('captureEpoch') == trigger_source['captureEpoch']
                            and finite(waiting_source.get('freshnessAtMs')) and waiting_source['freshnessAtMs'] <= barrier,
                            'Combat invalidated observation is not from the acknowledged release barrier')
            return
        if current.get('reason') != 'world_observation_stale':
            return
        # An armed/pending pulse retains the original terminal unavailable-evidence behavior.
        if self._armed:
            return
        require(self._pending is None, 'Combat source-stale interruption has an undrained pulse')
        require(self._stale_recovery['used'] == 0, 'Combat source-stale reacquisition was already consumed')
        require(self._phase == 'ready' and 0 < len(self._completed) == self._accepted < 3
                and self._release is not None and self._last is not None,
                'Combat source-stale reacquisition requires a fully drained pulse')
        prior_context = self._release['response'].get('executionContext') or {}
        prior_tracked = prior_context.get('trackedState') or {}
        require(prior_context.get('active', 'missing') is None and prior_context.get('telemetryComplete') is True
                and prior_context.get('evictedEvents') == 0 and prior_tracked.get('heldKeys') == []
                and prior_tracked.get('releaseOutcome') == 'returned_unverified'
                and prior_tracked.get('telemetryIncomplete') is False,
                'Combat prior release does not prove drained software input state')
        source = frame.get('sourceFrame') or {}
        prior = self._last['frame']
        age, now = frame.get('sourceFrameAgeMs'), frame.get('serverNowMs')
        checked = current.get('checkedAtMs')
        require(frame.get('frameId') == prior['frameId'] and frame.get('capturedAtMs') == prior['capturedAtMs']
                and canonical(self._evidence_identity(frame)) == canonical(self._evidence_identity(prior))
                and frame.get('sourceTimestampKind') == 'wgc_reported_compositor_qpc'
                and gate.get('ready') is True and gate.get('reason') == 'world_ready'
                and type(gate.get('epoch')) is int and gate['epoch'] == self._world_epoch and gate.get('sourceFrameId') == frame['frameId']
                and gate.get('sourceFrame') == source
                and current.get('ready') is False and frame.get('inputAvailable') is False
                and type(current.get('epoch')) is int and current['epoch'] == self._world_epoch + 1
                and current.get('sourceFrameId') == frame['frameId'] and current.get('sourceFrame') == source
                and all(finite(value) for value in (age, now, checked)) and age > 150
                and abs(now - source['freshnessAtMs'] - age) <= .01
                and source['freshnessAtMs'] + 150 < checked <= now,
                'Combat stale-source trigger differs from the last admitted source')
        self._stale_recovery['used'] = 1
        self._stale_recovery['pending'] = dict(trigger=dict(frame=sensor_frame(frame, source_stale_recovery=True), clientTimeNs=now_ns),
                                               acceptedActions=self._accepted, requested=None, release=None, sources=[])
        self._phase, self._reason = 'awaitingStaleRelease', 'releasedSourceStale'
        self._eligible = False
        self._sources = 0

    def request_stale_release(self, owner, hello, now_ns):
        """Journal the exact lease/owner check before this one safety release can be sent."""
        with self.intake_lock:
            self._live(now_ns)
            try:
                require(self._identity(owner, hello) == self._hello, 'Combat reacquisition lease or owner changed')
                pending = self._stale_recovery['pending'] if self._stale_recovery_enabled else None
                require(self._phase == 'awaitingStaleRelease' and pending is not None
                        and pending['requested'] is None and not self._armed and self._pending is None,
                        'Combat reacquisition release is missing, repeated or out of phase')
                pending['requested'] = dict(owner=retained(owner), lease=copy.deepcopy(self._hello), clientTimeNs=now_ns)
            except (ValueError, TypeError, KeyError) as error:
                self._stop('invalidReacquisitionReleaseRequest', now_ns, validationError=str(error))
            return self._event('ReacquisitionRequest', now_ns, owner=retained(owner),
                               lease={key: hello.get(key) for key in ('sessionId', 'ownerEpoch', 'goalVersion')}
                               if isinstance(hello, dict) else retained(hello))

    def record_existing_history_reset(self, last_accepted_ns, now_ns):
        """Record the existing 500 ms heuristic without changing its timer or adding a recovery reset."""
        with self.intake_lock:
            require(self._stale_recovery_enabled and type(last_accepted_ns) is int
                    and type(now_ns) is int and now_ns - last_accepted_ns > 500_000_000
                    and self._completed and self._completed[-1]['admissionClientNs'] <= last_accepted_ns <= now_ns,
                    'Combat history reset lacks its original acceptance-gap clock')
            resets = self._stale_recovery['existingHistoryResets']
            require(not resets or resets[-1]['acceptedActions'] < self._accepted,
                    'Combat acceptance-gap history reset was repeated')
            resets.append(dict(lastAcceptedAtClientNs=last_accepted_ns, clientTimeNs=now_ns,
                acceptedActions=self._accepted, reason='acceptanceGapHistoryReset',
                afterReacquisition=bool(self._stale_recovery['completed'] and
                    self._stale_recovery['completed'][-1]['acceptedActions'] == self._accepted)))
            return self._event('HistoryGapReset', now_ns, lastAcceptedAtClientNs=last_accepted_ns,
                               reason='acceptanceGapHistoryReset')

    def _validate_stale_release(self, response, now_ns, reason):
        """Require this requested release's exact epoch, clock, source and empty software input state."""
        pending = self._stale_recovery['pending']
        require(pending is not None and pending['requested'] is not None
                and reason == STALE_RELEASE_REASON and self._phase == 'awaitingStaleRelease'
                and pending['requested']['clientTimeNs'] <= now_ns,
                'Combat reacquisition lacks its owned release request')
        trigger = pending['trigger']['frame']
        gate, context = response.get('worldReadiness') or {}, response.get('executionContext') or {}
        source, old_source = gate.get('sourceFrame') or {}, trigger['sourceFrame']
        tracked = context.get('trackedState') or {}
        require(gate.get('reason') == 'client_release'
                and gate.get('epoch') == trigger['worldReadiness']['epoch'] + 1
                and response['serverNowMs'] >= trigger['serverNowMs']
                and type(gate.get('sourceFrameId')) is int and gate['sourceFrameId'] >= trigger['frameId']
                and finite(gate.get('sourceCapturedAtMs'))
                and trigger['capturedAtMs'] <= gate['sourceCapturedAtMs'] <= response['serverNowMs']
                and finite(gate.get('checkedAtMs'))
                and trigger['serverNowMs'] <= gate['checkedAtMs'] <= response['serverNowMs']
                and source.get('captureEpoch') == old_source['captureEpoch']
                and type(source.get('timestamp100ns')) is int and source['timestamp100ns'] >= old_source['timestamp100ns']
                and finite(source.get('freshnessAtMs'))
                and old_source['freshnessAtMs'] <= source['freshnessAtMs'] <= response['serverNowMs']
                and response.get('receipts') == [] and type(response.get('droppedReceipts')) is int
                and response['droppedReceipts'] == 0 and context.get('telemetryComplete') is True
                and context.get('active', 'missing') is None and tracked.get('heldKeys') == []
                and tracked.get('telemetryIncomplete') is False and tracked.get('releaseOutcome') == 'returned_unverified'
                and context.get('evictedEvents') == 0,
                'Combat reacquisition release source, epoch or input state differs')


    def observe(self, frame, received_ns, *, round_trip_ms):
        """Latch hazards before publication and return trigger metadata without throwing it away."""
        with self.intake_lock:
            self.tick(received_ns)
            raw = sensor_frame(frame, source_stale_recovery=self._stale_recovery_enabled)
            if self._trip is not None or self._phase == 'complete':
                return self._event('Observation', received_ns, frame=raw, roundTripMs=round_trip_ms)
            self._eligible = False
            try:
                require(isinstance(frame, dict), 'Malformed combat frame')
                require(type(frame.get('droppedReceipts', 0)) is int and frame.get('droppedReceipts', 0) == 0,
                        'Combat input receipts were lost or unavailable')
                evidence = validate_frame(frame,self._native_capability)
                require(finite(round_trip_ms) and round_trip_ms >= 0, 'Invalid combat transport measurement')
                if evidence is not None and evidence['state'] == 'valid':
                    reason = health_reason(evidence, self._binding['baselineHealthFraction'], self._maximum_candidates)
                    if reason:
                        self._stop(reason, received_ns, frame=raw)
                    elif not evidence['enemyBarCandidates'] and self._target_confirmed:
                        self._stop('targetLost', received_ns, frame=raw)
                if self._trip is None:
                    self._stale_source_transition(frame, received_ns)
                available = evidence is not None and evidence['state'] == 'valid'
                gate, current = frame.get('frameWorldReadiness'), frame.get('worldReadiness')
                available = (available and isinstance(gate, dict) and isinstance(current, dict)
                    and gate.get('ready') is True and current.get('ready') is True
                    and frame.get('inputAvailable') is True)
                age = frame.get('sourceFrameAgeMs')
                available = available and finite(age) and 0 <= age and age + round_trip_ms < 150
                if not available:
                    if self._stale_recovery_enabled and self._stale_recovery['pending'] is not None:
                        self._stale_recovery['pending']['sources'] = []
                    if self._armed:
                        self._stop('armedEvidenceUnavailable', received_ns, frame=raw)
                    elif self._trip is None:
                        self._reason = 'awaitingFreshTarget'
                        self._sources = 0
                    return self._event('Observation', received_ns, frame=raw, roundTripMs=round_trip_ms)
                source = frame['sourceFrame']
                require(frame['frameId'] >= self._last_frame_id, 'Combat frame id moved backwards')
                self._last_frame_id = frame['frameId']
                require(frame.get('sourceTimestampKind') == 'wgc_reported_compositor_qpc'
                        and finite(frame.get('serverNowMs'))
                        and abs(frame['serverNowMs'] - source['freshnessAtMs'] - age) <= 0.01
                        and finite(frame.get('capturedAtMs')) and type(gate.get('epoch')) is int
                        and gate['epoch'] >= 0 and gate['epoch'] == current.get('epoch')
                        and gate.get('sourceFrameId') == frame['frameId']
                        and gate.get('sourceFrame') == source
                        and (current.get('sourceFrame') or {}).get('captureEpoch') == source['captureEpoch'],
                        'Combat readiness/source join differs')
                if self._phase == 'awaitingStaleRelease':
                    require(gate['epoch'] == self._stale_recovery['pending']['trigger']['frame']['worldReadiness']['epoch'],
                            'Combat epoch changed before the owned reacquisition release')
                else:
                    if self._world_epoch is not None:
                        require(gate['epoch'] == self._world_epoch, 'Combat world epoch changed without acknowledged release')
                    self._world_epoch = gate['epoch']
                if self._last is not None:
                    prior = self._last['frame']['sourceFrame']
                    require(source['captureEpoch'] == prior['captureEpoch'] and source['timestamp100ns'] >= prior['timestamp100ns']
                            and source['freshnessAtMs'] >= prior['freshnessAtMs'], 'Combat capture identity or clock changed')
                    if source['timestamp100ns'] == prior['timestamp100ns']:
                        require(canonical(self._evidence_identity(frame)) == canonical(self._evidence_identity(self._last['frame'])),
                                'Combat cached-source evidence changed')
                distinct = self._last is None or source['timestamp100ns'] != self._last['frame']['sourceFrame']['timestamp100ns']
                observation = dict(frame=raw, clientTimeNs=received_ns, ageAtReceiptMs=age, roundTripMs=round_trip_ms)
                if frame['frameId'] in self._frames:
                    previous = self._frames[frame['frameId']]
                    require(canonical(self._evidence_identity(frame)) == canonical(self._evidence_identity(previous['frame']))
                            and frame['capturedAtMs'] == previous['frame']['capturedAtMs'], 'Combat frame id was reused')
                else:
                    self._frames[frame['frameId']] = observation
                    if len(self._frames) > 16:
                        self._frames.popitem(last=False)
                if distinct:
                    self._last = observation
                if self._trip is not None:
                    return self._event('Observation', received_ns, frame=raw, roundTripMs=round_trip_ms)
                target = 1 <= len(evidence['enemyBarCandidates']) <= self._maximum_candidates
                after_release = self._release is None or source['freshnessAtMs'] >= self._release['response']['serverNowMs'] + 60
                self._eligible = target and after_release
                if self._phase == 'awaitingStaleRelease':
                    self._eligible = False
                    self._reason = 'awaitingOwnedStaleRelease'
                elif self._phase == 'awaitingStaleEvidence':
                    self._eligible = False
                    pending = self._stale_recovery['pending']
                    if not target or not after_release:
                        pending['sources'] = []
                    elif distinct:
                        pending['sources'].append(dict(frame=raw, clientTimeNs=received_ns))
                    self._sources = len(pending['sources'])
                    if self._sources == 2:
                        self._stale_recovery['completed'].append(copy.deepcopy(pending))
                        self._stale_recovery['pending'] = None
                        self._phase, self._reason = 'ready', 'freshSourceReacquired'
                        self._eligible = True
                elif not target or not after_release:
                    self._sources = 0
                    self._reason = 'awaitingFreshTarget' if not target else 'awaitingPostReleaseFrame'
                elif self._phase == 'awaitingPostFrame' and distinct:
                    self._pending['postFrame'] = raw
                    self._completed.append(self._pending)
                    self._pending = None
                    self._phase = 'complete' if len(self._completed) == 3 else 'ready'
                    self._reason = 'boundedTrialDrained' if self._phase == 'complete' else 'freshPostActionTarget'
                elif self._phase == 'awaitingEvidence' and distinct:
                    self._sources += 1
                    if self._sources >= 2:
                        self._target_confirmed = True
                        self._phase, self._reason = 'ready', 'freshTargetConfirmed'
            except (ValueError, TypeError, KeyError, OverflowError) as error:
                self._stop('invalidNativeEvidence', received_ns, frame=raw, validationError=str(error))
            return self._event('Observation', received_ns, frame=raw, roundTripMs=round_trip_ms)

    def prepare_action(self, frame, proposal, request_id, now_ns, *, owner, hello):
        """Reserve one exact pulse before transmission; refusal never edits a policy proposal."""
        with self.intake_lock:
            self._live(now_ns)
            refused_proposal = ({key: proposal[key] for key in ('parseValid', 'scrollUnsupported', 'steps') if key in proposal}
                                if isinstance(proposal, dict) else proposal)
            refusal_proof = dict(frame=sensor_frame(frame), requestId=request_id, proposal=refused_proposal,
                                 transmissionAttempted=False)
            try:
                require(self._identity(owner, hello) == self._hello, 'Combat native lease changed')
            except (ValueError, TypeError) as error:
                self._stop('ownerOrLeaseChanged', now_ns, validationError=str(error))
                self._live(now_ns)
            reason = proposal_rejection(proposal)
            if self._phase != 'ready' or not self._eligible:
                reason = 'awaitingTerminalOrEvidence'
            if reason:
                return self._event('LocalRefusal', now_ns, reason=reason, **refusal_proof)
            record = self._frames.get(frame.get('frameId')) if isinstance(frame, dict) else None
            try:
                require(record is not None and canonical(self._evidence_identity(frame)) == canonical(self._evidence_identity(record['frame']))
                        and frame.get('capturedAtMs') == record['frame']['capturedAtMs'], 'Unobserved or changed combat source')
                require(isinstance(request_id, str) and bool(request_id) and request_id not in self._requests, 'Repeated combat request id')
            except (ValueError, TypeError, KeyError) as error:
                self._stop('invalidDispatchSource', now_ns, frame=sensor_frame(frame), validationError=str(error))
                self._live(now_ns)
            selected_evidence = record['frame']['combatEvidence']
            if (selected_evidence['state'] != 'valid'
                    or not 1 <= len(selected_evidence['enemyBarCandidates']) <= self._maximum_candidates
                    or health_reason(selected_evidence, self._binding['baselineHealthFraction'], self._maximum_candidates) is not None):
                return self._event('LocalRefusal', now_ns, reason='sourceTargetUnconfirmed', **refusal_proof)
            if any(not 0 <= self._age(item, now_ns) < 150 for item in (record, self._last)):
                return self._event('LocalRefusal', now_ns, reason='staleCombatSource', **refusal_proof)
            if self._release is not None and frame['sourceFrame']['freshnessAtMs'] < self._release['response']['serverNowMs'] + 60:
                return self._event('LocalRefusal', now_ns, reason='preReleaseCombatSource', **refusal_proof)
            source_at = frame['sourceFrame']['freshnessAtMs']
            step = copy.deepcopy(proposal['steps'][0])
            arguments = dict(requestId=request_id, frameId=frame['frameId'], observedAtMs=frame['capturedAtMs'],
                modelId=MODEL, steps=[step], startBeforeMs=source_at + 150, expiresAtMs=source_at + 150 + step['durationMs'])
            self._requests.add(request_id)
            self._pending = dict(arguments=arguments, frame=sensor_frame(frame), dispatchClientNs=now_ns,
                                 admission=None, receipt=None, release=None, postFrame=None)
            self._armed = True
            self._phase, self._reason = 'awaitingAdmission', 'actionReserved'
            return self._event('Dispatch', now_ns, arguments=arguments)

    def admission(self, response, payload_bytes, now_ns):
        """Bind the exact acceptance; rejection or an uncertain result ends this trial without replay."""
        with self.intake_lock:
            self.tick(now_ns)
            expected = self._pending is not None and self._pending['admission'] is None
            if expected:
                self._pending['admission'] = retained(response)
            action = self._pending['arguments'] if self._pending else {}
            valid = (expected and isinstance(response, dict) and type(payload_bytes) is int and payload_bytes == 0
                and response.get('type') == 'accepted' and response.get('requestId') == action.get('requestId')
                and finite(response.get('receivedAtMs')) and finite(response.get('acceptedAtMs'))
                and self._pending['frame']['sourceFrame']['freshnessAtMs'] <= response['receivedAtMs'] <= response['acceptedAtMs'] < action['startBeforeMs'])
            if not valid:
                self._stop('invalidActionAdmission', now_ns, response=retained(response), payloadBytes=payload_bytes)
            else:
                self._accepted += 1
                if self._stale_recovery_enabled:
                    self._pending['admissionClientNs'] = now_ns
                if self._trip is None:
                    self._phase, self._reason = 'awaitingTerminal', 'actionAccepted'
            return self._event('Admission', now_ns, response=retained(response), payloadBytes=payload_bytes)

    def receipt(self, receipt, now_ns):
        """Require one exact completed pulse before allowing release and post-action drain."""
        with self.intake_lock:
            self.tick(now_ns)
            action = self._pending['arguments'] if self._pending else {}
            expected_receipt = self._pending is not None and self._pending['admission'] is not None and self._pending['receipt'] is None
            if self._pending is not None and self._pending['receipt'] is None:
                self._pending['receipt'] = retained(receipt)
            try:
                require(expected_receipt and isinstance(receipt, dict)
                    and receipt.get('requestId') == action.get('requestId') and receipt.get('frameId') == action.get('frameId')
                    and receipt.get('modelId') == MODEL and receipt.get('status') == 'completed'
                    and receipt.get('reason') == 'horizon_complete', 'Unowned or incomplete combat receipt')
                steps = receipt.get('appliedSteps')
                require(isinstance(steps, list) and len(steps) == 1 and isinstance(steps[0], dict), 'Combat receipt step count differs')
                step, expected = steps[0], action['steps'][0]
                require(type(step.get('index')) is int and step['index'] == 0 and step.get('keys') == expected['keys']
                    and all(type(step.get(key)) is int and step[key] == 0 for key in ('mouseDx', 'mouseDy')), 'Combat receipt action differs')
                start, end, accepted = step.get('startedAtMs'), receipt.get('endedAtMs'), receipt.get('acceptedAtMs')
                require(all(finite(value) for value in (start, end, accepted))
                    and accepted == self._pending['admission']['acceptedAtMs']
                    and accepted <= start < action['startBeforeMs'] and end >= accepted + expected['durationMs']
                    and 0 < end - start <= expected['durationMs'] + 50 and end <= action['expiresAtMs'], 'Combat receipt timing differs')
                if self._trip is None:
                    self._phase, self._reason = 'awaitingRelease', 'terminalPulseRecorded'
            except (ValueError, TypeError, KeyError) as error:
                self._stop('invalidActionReceipt', now_ns, receipt=retained(receipt), validationError=str(error))
            return self._event('Receipt', now_ns, receipt=retained(receipt))

    def acknowledge_release(self, response, payload_bytes, now_ns, reason):
        """Disarm after an exact acknowledgement without clearing a trip or skipping final drain."""
        with self.intake_lock:
            self.tick(now_ns)
            gate = response.get('worldReadiness') if isinstance(response, dict) else None
            valid = (isinstance(response, dict) and response.get('type') == 'released'
                and type(payload_bytes) is int and payload_bytes == 0
                and finite(response.get('serverNowMs')) and isinstance(gate, dict) and gate.get('ready') is False
                and type(gate.get('epoch')) is int and gate['epoch'] >= 0)
            previous_times = [item for item in (
                self._last['frame']['sourceFrame']['freshnessAtMs'] if self._last else None,
                self._release['response']['serverNowMs'] if self._release else None,
                (self._pending.get('receipt') or {}).get('endedAtMs') if self._pending else None) if finite(item)]
            valid = valid and all(response['serverNowMs'] >= value for value in previous_times)
            valid = valid and (self._world_epoch is None or gate['epoch'] > self._world_epoch)
            if valid and self._trip is None and (reason == STALE_RELEASE_REASON or self._phase == 'awaitingStaleRelease'):
                try:
                    require(self._stale_recovery_enabled, 'Undeclared combat stale-source recovery')
                    self._validate_stale_release(response, now_ns, reason)
                except (ValueError, TypeError, KeyError) as error:
                    self._stop('invalidReacquisitionReleaseAcknowledgement', now_ns,
                               response=retained(response), validationError=str(error))
                    valid = False
            if not valid:
                self._stop('invalidReleaseAcknowledgement', now_ns, response=retained(response), payloadBytes=payload_bytes)
            else:
                self._armed = False
                self._eligible = False
                self._world_epoch = gate['epoch']
                self._release = dict(response=copy.deepcopy(response), payloadBytes=payload_bytes,
                                     clientTimeNs=now_ns, reason=reason)
                self._sources = 0
                if self._trip is None:
                    if self._phase == 'awaitingStaleRelease':
                        self._stale_recovery['pending']['release'] = copy.deepcopy(self._release)
                        self._stale_recovery['pending']['sources'] = []
                        self._phase, self._reason = 'awaitingStaleEvidence', 'awaitingPostReleaseSources'
                    elif self._phase == 'awaitingRelease':
                        self._pending['release'] = copy.deepcopy(self._release)
                        self._phase, self._reason = 'awaitingPostFrame', 'awaitingPostReleaseFrame'
                    elif self._phase == 'awaitingEvidence':
                        self._reason = 'awaitingPostReleaseFrame'
                    elif self._phase != 'complete':
                        self._stop('releaseBeforeTerminal', now_ns, response=response)
            return self._event('Release', now_ns, response=retained(response), payloadBytes=payload_bytes, reason=reason)
