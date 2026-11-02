"""One input-free, source-bound hold inside an explicitly reviewed scout batch."""
from copy import deepcopy
import math
import json

from native_combat import validate_frame
from native_ground_control import require_ground_frame, validate_frame as validate_ground_frame
from navigation_profiles import allows_pose_scope
from p2p_executed_history import verify_completed_receipt
from reviewed_scout_route import batch_source_hold_policy


RELEASE_REASON = 'batchIdleSourceHold'
EVENT_PREFIX = 'scoutBatchSourceHold'


def require(value, message):
    """Keep every ambiguous interruption terminal without granting another release attempt."""
    if not value:
        raise ValueError('Batch source hold: ' + message)


def number(value):
    """Reject booleans and nonfinite native clock values."""
    return type(value) in (int, float) and math.isfinite(value)


def immutable_frame(frame):
    """Separate original capture evidence from a later poll's mutable readiness and age."""
    return {key: deepcopy(frame.get(key)) for key in ('type', 'frameId', 'capturedAtMs',
        'sourceFrame', 'sourceTimestampKind', 'sourceWidth', 'sourceHeight', 'combatEvidence',
        'groundControlEvidence', 'navigationPose', 'motionEvidence', 'frameWorldReadiness')}


def retained_frame(frame):
    """Retain bounded native provenance, including known software-state contradictions."""
    return {key: deepcopy(frame[key]) for key in ('type', 'frameId', 'capturedAtMs',
        'sourceFrame', 'sourceTimestampKind', 'sourceWidth', 'sourceHeight', 'combatEvidence',
        'groundControlEvidence', 'navigationPose', 'frameWorldReadiness', 'worldReadiness',
        'sourceFrameAgeMs', 'serverNowMs', 'inputAvailable', 'motionEvidence', 'receipts',
        'droppedReceipts', 'executionContext') if key in frame}


class BatchSourceHold:
    """Classify before guard observation; an owned release disarms, never clears a trip.

    All methods run under the existing receive/intake lock. This class never takes
    ResidentControl's lock, performs IO, changes model history or owns game input.
    """
    def __init__(self, descriptor, profile, route_sha, lease, guard_binding):
        """Bind the explicit policy and original lease without creating mutable run authority."""
        require(json.dumps(descriptor,sort_keys=True,allow_nan=False)==json.dumps(batch_source_hold_policy(),sort_keys=True), 'undeclared policy')
        self.descriptor, self.profile, self.route_sha = deepcopy(descriptor), profile, route_sha
        self.lease = {key: deepcopy(lease.get(key)) for key in ('sessionId', 'ownerEpoch', 'goalVersion')}
        require(all(value is not None for value in self.lease.values()), 'missing native lease identity')
        self.binding = deepcopy(guard_binding)
        self.used, self.phase, self.inflight = 0, 'idle', False
        self.selection_barrier = False
        self.last = self.trigger = self.release = self.runtime = None
        self.sources = []

    @property
    def waiting(self):
        """Fence inference, waypoint progression and input until both fresh sources qualify."""
        return self.phase in ('awaitingRelease', 'awaitingSources')

    def snapshot(self):
        """Publish compact evidence without copying prior RGB or every receipt into each state."""
        return dict(policy=deepcopy(self.descriptor), used=self.used, phase=self.phase,
                    predictionInFlight=self.inflight, postReleaseSelectionRequired=self.selection_barrier,
                    triggerFrameId=None if self.trigger is None else self.trigger['frame']['frameId'],
                    releaseServerNowMs=None if self.release is None else self.release['response']['serverNowMs'],
                    sourceFrameIds=[row['frame']['frameId'] for row in self.sources])

    def _event(self, name, now_ns, **values):
        """Use a separate journal namespace; no generic hold or endpoint reset is synthesized."""
        return dict(type=EVENT_PREFIX+name, clientTimeNs=now_ns, **deepcopy(values), state=self.snapshot())

    def selected_after_release(self, frame):
        """Discard pre-hold selections even if the reader completed both confirmations during preparation."""
        if self.waiting:return False
        if self.phase != 'complete':return True
        last=self.sources[-1]['frame'];source=frame.get('sourceFrame') or {}
        gate=frame.get('frameWorldReadiness') or {}
        return (frame.get('frameId',-1)>=last['frameId']
                and source.get('captureEpoch')==last['sourceFrame']['captureEpoch']
                and source.get('timestamp100ns',-1)>=last['sourceFrame']['timestamp100ns']
                and source.get('freshnessAtMs',-1)>=last['sourceFrame']['freshnessAtMs']
                and gate.get('ready') is True
                and (not self.selection_barrier or gate.get('epoch')==self.release['response']['worldReadiness']['epoch']))

    def begin_prediction(self, frame=None):
        """Reserve before model/candidate work under intake; a concurrent stale poll stays terminal."""
        require(not self.waiting and not self.inflight, 'prediction crossed an active hold or transaction')
        require(self.selected_after_release(frame or {}), 'prediction selected pre-confirmation pixels')
        self.inflight = True
        # This serial selection or a fully verified endpoint retires the ACK-epoch fence.
        # Immutable source floors and the one-hold budget remain through later endpoint releases.
        self.selection_barrier = False

    def verified_endpoint(self, endpoint, transition, frame, now_ns):
        """Retire only the old ACK epoch after the existing controller fully verifies its released waypoint."""
        if not self.selection_barrier:return None
        require(self.phase == 'complete' and self.used == 1 and not self.inflight,
                'endpoint crossed an unfinished hold or prediction')
        marker = transition.get('executedHistoryReset') or {}
        release = marker.get('release') or {};gate = release.get('worldReadiness') or {}
        last = self.sources[-1]['frame'];floor = last['sourceFrame'];source = frame.get('sourceFrame') or {}
        predecessor = {key:self.runtime['predecessor'][key] for key in ('requestId','endedAtMs')}
        expected_epoch = self.release['response']['worldReadiness']['epoch']+1
        require(endpoint.get('type') == 'hybridEndpointVerified'
                and endpoint.get('routeSpecSha256') == self.route_sha
                and endpoint.get('completedLegs') == self.runtime['completedLegs']+1
                and endpoint.get('endpoint') == self.runtime['targetName']
                and endpoint.get('sourceEpoch') == floor['captureEpoch']
                and type(endpoint.get('arrivalFrameId')) is int and endpoint['arrivalFrameId'] >= last['frameId']
                and transition.get('type') == 'controlTransition' and transition.get('state') == 'held'
                and transition.get('reason') == 'hybridEndpoint' and marker.get('version') == 1
                and marker.get('routeSpecSha256') == self.route_sha
                and marker.get('endpointOrdinal') == endpoint['completedLegs']
                and marker.get('arrivalFrameId') == endpoint['arrivalFrameId']
                and marker.get('previousReceipt') == predecessor and marker.get('before') == self.runtime['history']
                and all((marker.get('after') or {}).get(key) == 0
                        for key in ('afterFrames','afterIndex','afterValidTokens','validFrames')),
                'endpoint is not the original settled waypoint/reset')
        released_source = gate.get('sourceFrame') or {}
        require(release.get('type') == 'released' and release.get('droppedReceipts') == 0 and release.get('receipts') == []
                and number(release.get('serverNowMs')) and release['serverNowMs'] == endpoint.get('releaseAtMs')
                and predecessor['endedAtMs'] <= release['serverNowMs']
                and gate.get('epoch') == endpoint.get('releaseEpoch') == expected_epoch
                and gate.get('ready') is False and gate.get('reason') == 'client_release'
                and type(gate.get('sourceFrameId')) is int and gate['sourceFrameId'] >= endpoint['arrivalFrameId']
                and released_source.get('captureEpoch') == floor['captureEpoch']
                and released_source.get('timestamp100ns',-1) >= floor['timestamp100ns']
                and floor['freshnessAtMs'] <= released_source.get('freshnessAtMs',-1) <= release['serverNowMs'],
                'endpoint lost its exact next release/source barrier')
        self._healthy(frame)
        samples = endpoint.get('samples') or []
        require(len(samples) == 3 and samples[-1].get('frameId') == frame.get('frameId')
                and frame['frameId'] >= last['frameId'] and source.get('captureEpoch') == floor['captureEpoch']
                and source.get('timestamp100ns',-1) >= floor['timestamp100ns']
                and source.get('freshnessAtMs',-1) >= floor['freshnessAtMs']
                and source['freshnessAtMs'] > release['serverNowMs']
                and frame['frameWorldReadiness']['epoch'] == expected_epoch
                and type(transition.get('clientTimeNs')) is int
                and self.sources[-1]['clientTimeNs'] <= transition['clientTimeNs'] <= now_ns,
                'endpoint lacks its exact post-release settled source')
        # No history, clock, source floor or hold budget changes here. The ordinary
        # endpoint proof now owns the next epoch; arbitrary phase changes do not.
        self.selection_barrier = False
        return self._event('Endpoint', now_ns, endpoint=endpoint, transition=transition, frame=retained_frame(frame))

    def finish_prediction(self):
        """Release the reservation only after feedback and its original journal are settled."""
        require(self.inflight, 'prediction transaction was not reserved')
        self.inflight = False

    def _healthy(self, frame, round_trip_ms=0):
        """Reapply the existing source, HUD, ground, pose and motion constraints to new pixels."""
        evidence = validate_frame(frame, self.binding.get('nativeCombatObservation'))
        require(evidence is not None and evidence['state'] == 'valid'
                and evidence['playerHealthColor'] == 'green' and not evidence['redMaskOverloaded']
                and not evidence['enemyBarCandidates']
                and self.binding['baselineHealthFraction']-evidence['playerHealthFractionEstimate'] < .08-1e-12,
                'health or enemy gate changed')
        require_ground_frame(frame)
        source, gate, current = frame.get('sourceFrame') or {}, frame.get('frameWorldReadiness') or {}, frame.get('worldReadiness') or {}
        pose, motion = frame.get('navigationPose') or {}, frame.get('motionEvidence') or {}
        age = frame.get('sourceFrameAgeMs')
        require(number(age) and number(round_trip_ms) and 0 <= age and 0 <= round_trip_ms
                and age+round_trip_ms < 150 and gate.get('ready') is True and current.get('ready') is True
                and frame.get('inputAvailable') is True and gate.get('epoch') == current.get('epoch')
                and gate.get('sourceFrameId') == frame.get('frameId') and gate.get('sourceFrame') == source,
                'fresh same-source readiness is unavailable')
        require(pose.get('state') == 'valid' and pose.get('frameId') == frame.get('frameId')
                and allows_pose_scope(pose, self.profile) and .99 <= pose.get('positionConfidence', 0) <= 1
                and .2 <= pose.get('yawConfidence', 0) <= 1 and motion.get('status') == 'normal'
                and motion.get('spaceKeyMatched') is False, 'fresh grounded navigation source is unavailable')

    def remember_healthy(self, frame, now_ns, round_trip_ms, guard_state):
        """Retain an actually admitted poll, not a later mutation of a cached source."""
        if guard_state.get('state') != 'ready' or self.waiting:
            return
        try:
            self._healthy(frame, round_trip_ms)
        except (ValueError, TypeError, KeyError):
            return
        self.last = dict(frame=retained_frame(frame), clientTimeNs=now_ns, roundTripMs=round_trip_ms)

    def _live(self, runtime, now_ns, *, unchanged=False):
        """Preserve original batch, leg and accepted-history clocks, including all waiting time."""
        require(type(now_ns) is int and runtime.get('lease') == self.lease
                and runtime.get('routeSpecSha256') == self.route_sha and runtime.get('phase') == 'walking',
                'lease, route or controller phase changed')
        require(all(type(runtime.get(key)) is int and now_ns < runtime[key]
                    for key in ('deadlineClientNs', 'legDeadlineClientNs')),
                'original batch or leg deadline expired')
        accepted_ns = runtime.get('lastAcceptedClientNs')
        require(type(accepted_ns) is int and 0 <= now_ns-accepted_ns <= 500_000_000,
                'original 500ms executed-history acceptance gap expired')
        if unchanged:
            require(runtime == self.runtime, 'history, target, accounting or original clocks changed during hold')

    def observe(self, frame, now_ns, runtime, round_trip_ms=0):
        """Classify the exact stale repeat before the ordinary guard can latch a terminal trip."""
        if self.waiting:
            self._live(runtime, now_ns, unchanged=True)
            require(self.phase == 'awaitingSources' and self.release is not None, 'observation overtook release acknowledgement')
            current, gate, source = frame.get('worldReadiness'), frame.get('frameWorldReadiness'), frame.get('sourceFrame') or {}
            require(isinstance(current, dict) and isinstance(gate, dict), 'native readiness disappeared')
            expected = self.release['response']['worldReadiness']['epoch']
            original = self.trigger['frame']['sourceFrame']
            require(current.get('epoch') == expected and source.get('captureEpoch') == original['captureEpoch']
                    and type(source.get('timestamp100ns')) is int and source['timestamp100ns'] >= original['timestamp100ns']
                    and number(source.get('freshnessAtMs')) and source['freshnessAtMs'] >= original['freshnessAtMs']
                    and type(frame.get('inputAvailable')) is bool,
                    'unknown source, epoch or input availability during hold')
            require(current.get('reason') in ('world_ready', 'world_confirming', 'client_release', 'world_observation_invalidated'),
                    'non-owned readiness interruption')
            positive = current.get('ready') is True and gate.get('ready') is True and gate.get('epoch') == expected
            require(frame['inputAvailable'] is positive, 'input availability contradicts native readiness')
            self._empty_context(frame)
            evidence = validate_frame(frame, self.binding.get('nativeCombatObservation')) or {}
            ground = validate_ground_frame(frame) or {}
            if evidence.get('state') == 'valid':
                require(evidence['playerHealthColor'] == 'green' and not evidence['redMaskOverloaded']
                        and self.binding['baselineHealthFraction']-evidence['playerHealthFractionEstimate'] < .08-1e-12
                        and evidence['enemyBarCandidates'] == [], 'observed health or enemy interruption')
            require(ground.get('state') == 'valid' or (ground.get('state') == 'unavailable'
                    and ground.get('reason') == 'world_not_ready' and gate.get('ready') is False
                    and gate.get('epoch') == expected and gate.get('reason') in
                        ('world_confirming','client_release','world_observation_invalidated')),
                    'unknown ground interruption during hold')
            if ground.get('state') == 'valid':require_ground_frame(frame)
            require(evidence.get('state') == 'valid' or (evidence.get('state') == 'unavailable'
                    and evidence.get('reason') == 'world_not_ready' and gate.get('ready') is False
                    and gate.get('epoch') == expected and gate.get('reason') in
                        ('world_confirming', 'client_release', 'world_observation_invalidated')),
                    'unknown HUD interruption during hold')
            for item in (current, gate):
                if item.get('reason') == 'world_observation_invalidated':
                    invalid = item.get('sourceFrame') or {}
                    require(item.get('ready') is False and item.get('epoch') == expected
                            and invalid.get('captureEpoch') == original['captureEpoch']
                            and number(invalid.get('freshnessAtMs'))
                            and invalid['freshnessAtMs'] <= self.release['response']['serverNowMs'],
                            'invalidation is not from the owned release barrier')
            qualified = False
            if (current.get('ready') is True and gate.get('ready') is True and gate.get('epoch') == expected
                    and source['freshnessAtMs'] >= self.release['response']['serverNowMs']+60):
                self._healthy(frame, round_trip_ms)
                before = self.sources[-1]['frame'] if self.sources else self.trigger['frame']
                if (frame['frameId'] > before['frameId'] and source['timestamp100ns'] > before['sourceFrame']['timestamp100ns']
                        and source['freshnessAtMs'] > before['sourceFrame']['freshnessAtMs']):
                    self.sources.append(dict(frame=retained_frame(frame), clientTimeNs=now_ns))
                    qualified = True
                    if len(self.sources) == 2:
                        self.phase = 'complete'
                        self.selection_barrier = True
            return self._event('Observation', now_ns, frame=retained_frame(frame), runtime=runtime,
                               roundTripMs=round_trip_ms, qualified=qualified)
        current = frame.get('worldReadiness') or {}
        if current.get('reason') != 'world_observation_stale' or self.used or self.last is None:
            return None
        # A prediction/candidate/accepted input race retains the existing terminal guard path.
        if (self.inflight or runtime is None or runtime.get('pendingFeedback') is not False
                or runtime.get('pendingCandidate') is not False or runtime.get('unacknowledgedInput') is not False
                or runtime.get('phase') != 'walking' or runtime.get('settled') is None):
            return None
        self._live(runtime, now_ns)
        settled = runtime['settled']
        require(settled.get('outcome') == 'committed' and settled.get('error') is None
                and settled.get('history') == runtime.get('history')
                and all(type(runtime.get(key)) is int for key in ('acceptedActions','terminalReceipts','historyCommits'))
                and 0 < runtime.get('acceptedActions', 0) == runtime.get('terminalReceipts') == runtime.get('historyCommits'),
                'predecessor input/history is not fully settled')
        receipt = verify_completed_receipt(settled['receipt'], settled['arguments'], settled['acceptance'])
        require(settled.get('requestId') == receipt['requestId']
                and settled.get('clientTimeNs', math.inf) <= now_ns
                and runtime.get('predecessor') == dict(requestId=receipt['requestId'], frameId=receipt['frameId'],
                    endedAtMs=receipt['endedAtMs'], sourceFrame=settled['sourceFrame']),
                'settled history predecessor differs')
        repeated, previous = immutable_frame(frame), immutable_frame(self.last['frame'])
        if repeated['motionEvidence'] != previous['motionEvidence']:
            # AgentStreamSession.MotionForReadiness masks cached motion whenever
            # current readiness expires. Only that exact no-input projection is
            # permitted here; retain the original positive same-capture evidence.
            projected = dict(status='unknown', reason='world_not_ready', method='native_key_tip_templates_v1',
                             recognitionMs=0, spaceKeyMatched=None, xKeyMatched=None)
            require(repeated['motionEvidence'] == projected
                    and number(repeated['motionEvidence'].get('recognitionMs')),
                    'stale repeat changed native motion beyond its readiness projection')
            repeated['motionEvidence'] = deepcopy(previous['motionEvidence'])
        require(repeated == previous, 'stale repeat changed immutable capture evidence')
        gate, source = frame.get('frameWorldReadiness') or {}, frame.get('sourceFrame') or {}
        age, server_now, checked = frame.get('sourceFrameAgeMs'), frame.get('serverNowMs'), current.get('checkedAtMs')
        require(type(gate.get('epoch')) is int and gate.get('ready') is True and gate.get('reason') == 'world_ready'
                and current.get('ready') is False and frame.get('inputAvailable') is False
                and type(current.get('epoch')) is int and current['epoch'] == gate['epoch']+1
                and current.get('sourceFrameId') == frame.get('frameId') and current.get('sourceFrame') == source
                and all(number(value) for value in (age, server_now, checked)) and age > 150
                and abs(server_now-source['freshnessAtMs']-age) <= .01
                and source['freshnessAtMs']+150 <= checked <= server_now,
                'not the exact repeated world-observation expiry')
        self._empty_context(frame)
        self.used, self.phase = 1, 'awaitingRelease'
        self.runtime = deepcopy(runtime)
        self.trigger = dict(frame=retained_frame(frame), clientTimeNs=now_ns)
        return self._event('Trigger', now_ns, frame=retained_frame(frame), previous=self.last,
                           runtime=runtime, roundTripMs=round_trip_ms)

    @staticmethod
    def _empty_context(frame):
        """Known foreign/active input or receipt contradictions cannot disappear behind a later ACK."""
        require(frame.get('receipts') == [] and frame.get('droppedReceipts') == 0, 'unexpected receipt or receipt loss')
        context = frame.get('executionContext')
        if context is not None:
            require(isinstance(context, dict) and context.get('active', 'missing') is None
                    and context.get('telemetryComplete') is True and context.get('evictedEvents') == 0
                    and (context.get('trackedState') or {}).get('heldKeys') == []
                    and (context.get('trackedState') or {}).get('telemetryIncomplete') is False
                    and (context.get('trackedState') or {}).get('releaseOutcome') == 'returned_unverified', 'observed native input is not idle')

    def acknowledge_release(self, response, payload_bytes, now_ns, runtime):
        """Accept one exact release; software uncertainty remains explicit, never physical-delivery proof."""
        require(self.phase == 'awaitingRelease' and self.release is None, 'missing or repeated release request')
        self._live(runtime, now_ns, unchanged=True)
        trigger = self.trigger['frame']
        gate = response.get('worldReadiness') or {}
        context, source = response.get('executionContext') or {}, gate.get('sourceFrame') or {}
        tracked = context.get('trackedState') or {}
        require(response.get('type') == 'released' and payload_bytes == 0 and response.get('droppedReceipts') == 0
                and response.get('receipts') == []
                and ('inputAvailable' not in response or response['inputAvailable'] is False)
                and number(response.get('serverNowMs')) and response['serverNowMs'] >= trigger['serverNowMs']
                and gate.get('ready') is False and gate.get('reason') == 'client_release'
                and type(gate.get('epoch')) is int and gate['epoch'] == trigger['worldReadiness']['epoch']+1
                and type(gate.get('sourceFrameId')) is int and gate['sourceFrameId'] >= trigger['frameId']
                and source.get('captureEpoch') == trigger['sourceFrame']['captureEpoch']
                and type(source.get('timestamp100ns')) is int and source['timestamp100ns'] >= trigger['sourceFrame']['timestamp100ns']
                and number(source.get('freshnessAtMs')) and trigger['sourceFrame']['freshnessAtMs'] <= source['freshnessAtMs'] <= response['serverNowMs']
                and context.get('active', 'missing') is None and context.get('telemetryComplete') is True
                and context.get('evictedEvents') == 0 and tracked.get('heldKeys') == []
                and tracked.get('telemetryIncomplete') is False and tracked.get('releaseOutcome') == 'returned_unverified'
                and self.runtime['settled']['receipt']['endedAtMs'] <= response['serverNowMs'],
                'release ACK does not join exact epoch/source/drained software input')
        self.release = dict(response=deepcopy(response), payloadBytes=payload_bytes, clientTimeNs=now_ns)
        self.phase = 'awaitingSources'
        return self._event('Release', now_ns, response=response, payloadBytes=payload_bytes, runtime=runtime)

    def tick(self, now_ns, runtime):
        """Waiting never freezes the original acceptance, leg or total lease deadline."""
        if self.waiting:
            self._live(runtime, now_ns, unchanged=True)
