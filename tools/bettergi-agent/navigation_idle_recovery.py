"""Optional, receipt-rearmed navigation history reset; never generates movement actions."""
import copy
import math

from observation_timing import observation_timestamp


GOAL_INTENTS = ('unspecified', 'stationary', 'ground-navigation')
MOTION_METHOD = 'native_key_tip_templates_v1'


def finite(value):
    """Server/client timing must remain finite numbers, without accepting JSON booleans."""
    return type(value) in (int, float) and math.isfinite(value)


def movement_step(step):
    """Receipt-confirmed directional input is evidence of dispatch, not proof of world displacement."""
    keys = set(step.get('keys', []))
    return ('W' in keys) != ('S' in keys) or ('A' in keys) != ('D' in keys)


def noop_steps(steps):
    """A no-op has neither held keys nor relative mouse movement in every interval."""
    return bool(steps) and all(not step.get('keys') and step.get('mouseDx', 0) == 0
                               and step.get('mouseDy', 0) == 0 for step in steps)


def fresh_frame(frame, now_ns, maximum_age_ms):
    """Use the immutable source anchor and conservative transport age already used for proposals."""
    try:
        anchor = observation_timestamp(frame)
        server_now, received_ns, rtt = (frame.get(name) for name in
                                       ('serverNowMs', 'clientReceivedNs', 'transportRoundTripMs'))
        if not all(finite(value) for value in (anchor, server_now, received_ns, rtt)) or rtt < 0:
            return False
        age = server_now - anchor + (now_ns - received_ns) / 1e6 + rtt
        return 0 <= age < maximum_age_ms
    except (ValueError, TypeError, KeyError):
        return False


def eligible_frame(frame, status, status_received_at, now_ns, maximum_age_ms, motion_capability):
    """Exclude unready/stale/flying evidence; negative normal recognition is not grounded proof."""
    if (not isinstance(frame, dict) or motion_capability.get('version') != 1
            or motion_capability.get('method') != MOTION_METHOD
            or motion_capability.get('sameFrame') is not True
            or motion_capability.get('normalIsGroundedProof') is not False):
        return False
    gate, payload = status.get('worldReadiness', {}), frame.get('frameWorldReadiness', {})
    motion = frame.get('motionEvidence', {})
    if (gate.get('ready') is not True or payload.get('ready') is not True
            or status.get('inputAvailable') is not True or gate.get('epoch') != payload.get('epoch')
            or frame.get('frameQuality') != 'usable'
            or not 0 <= now_ns / 1e9 - status_received_at <= .25
            or motion.get('method') != MOTION_METHOD
            or not ((motion.get('status') == 'normal' and motion.get('spaceKeyMatched') is False
                     and type(motion.get('xKeyMatched')) is bool)
                    or (motion.get('status') == 'climb' and motion.get('spaceKeyMatched') is True
                        and motion.get('xKeyMatched') is True))):
        return False
    return fresh_frame(frame, now_ns, maximum_age_ms)


class NavigationIdleRecovery:
    """Serial-policy-thread state, retained across resident leases; one reset until movement is issued."""
    def __init__(self, threshold_seconds=None):
        if threshold_seconds is not None and (not finite(threshold_seconds) or not 1 <= threshold_seconds <= 120):
            raise ValueError('Navigation idle reset must be disabled or between 1 and 120 seconds')
        self.threshold = threshold_seconds
        self.armed = True
        self.goal = None
        self.intent = 'unspecified'
        self.lease = None
        self.barrier = None
        self.release_at = None
        self.pending_movement = {}
        self.started = self.last_noop = None
        self.noops = 0
        self.attempts = self.resets = 0
        self.post_reset_noops = 0
        self.reason = 'disabled' if threshold_seconds is None else 'awaitingNavigationIntent'

    def begin_lease(self, session_id):
        """Clock barriers and pending receipts are lease-local; the one-reset latch is run-local."""
        if self.lease != session_id:
            self.lease = session_id
            self.barrier = self.release_at = None
            self.pending_movement.clear()
            self.interrupt('newBridgeLease')

    def set_goal(self, version, request_id, intent):
        """New goals never inherit navigation intent or pending movement from an earlier version."""
        if intent not in GOAL_INTENTS:
            raise ValueError('Unknown goal intent')
        key = (version, request_id, intent)
        if key != self.goal:
            self.goal, self.intent = key, intent
            self.pending_movement.clear()
            self.interrupt('goalChanged')

    def interrupt(self, reason):
        """Break a sustained no-op streak without rearming a previous recovery attempt."""
        self.started = self.last_noop = None
        self.noops = 0
        self.reason = reason if self.threshold is not None else 'disabled'

    def snapshot(self):
        """Expose bounds and latch state without reporting negative recognition as ground truth."""
        return {'enabled': self.threshold is not None, 'thresholdSeconds': self.threshold,
                'armed': self.armed, 'goalIntent': self.intent,
                'policyGoalVersion': self.goal[0] if self.goal else None,
                'acceptedNoops': self.noops, 'attempts': self.attempts, 'resets': self.resets,
                'postResetAcceptedNoops': self.post_reset_noops,
                'reason': self.reason, 'awaitingFreshFrame': self.barrier is not None,
                'motionGate': 'normal or confirmed climb; excludes fly/unknown; not grounded proof'}

    def proposal(self, result, frame, now, eligible):
        """Only a continuous fresh accepted no-op run can claim an idle-history reset."""
        if self.threshold is None:
            return None
        acceptance = result.get('acceptance', {})
        accepted = acceptance.get('type') == 'accepted'
        request_id = acceptance.get('requestId')
        steps = result.get('steps', [])
        if (accepted and eligible and isinstance(request_id, str) and request_id
                and any(movement_step(step) for step in steps)):
            self.pending_movement[request_id] = self.goal
            while len(self.pending_movement) > 128:
                del self.pending_movement[next(iter(self.pending_movement))]
        if (self.intent != 'ground-navigation' or not eligible or not accepted or not noop_steps(steps)):
            self.interrupt('notEligibleAcceptedNavigationNoop')
            return None
        if not self.armed:
            self.post_reset_noops += 1
            self.interrupt('awaitingReceiptConfirmedMovement')
            return None
        # An acceptance gap cannot count as continuous all-ready no-op behavior.
        if self.last_noop is None or not 0 <= now - self.last_noop <= .5:
            self.started, self.noops = now, 0
        self.last_noop = now
        self.noops += 1
        self.reason = 'observingAcceptedNoops'
        if now - self.started < self.threshold:
            return None
        return {'type': 'navigationIdleRecovery', 'reason': 'sustainedAcceptedNavigationNoops',
                'policyGoalVersion': self.goal[0], 'appliedGoalRequestId': self.goal[1],
                'goalIntent': self.intent, 'frameId': frame['frameId'],
                'observationTimestampMs': observation_timestamp(frame),
                'noopSeconds': now - self.started, 'acceptedNoops': self.noops,
                'motionEvidence': copy.deepcopy(frame.get('motionEvidence'))}

    def receipt(self, receipt):
        """Rearm only from matched, post-reset movement actually dispatched under the current goal."""
        candidate = self.pending_movement.pop(receipt.get('requestId'), None)
        if self.armed or candidate is None or candidate != self.goal:
            return None
        for step in receipt.get('appliedSteps', []):
            started = step.get('startedAtMs')
            if (finite(started) and started >= 0 and (self.release_at is None or started > self.release_at)
                    and movement_step(step)):
                self.armed = True
                self.interrupt('receiptConfirmedMovement')
                return {'type': 'navigationIdleRearmed', 'requestId': receipt['requestId'],
                        'policyGoalVersion': self.goal[0], 'appliedGoalRequestId': self.goal[1],
                        'startedAtMs': started, 'keys': list(step.get('keys', [])),
                        'postResetAcceptedNoops': self.post_reset_noops,
                        'releaseToMovementDispatchMs': started-self.release_at if self.release_at is not None else None,
                        'meaning': 'directional input was issued; world displacement is not established'}
        return None

    def allows_frame(self, frame, status, fresh=True):
        """A post-release source and reconfirmed matching world epoch are required before any inference."""
        if self.barrier is None:
            return True
        cutoff, epoch = self.barrier
        payload, gate = frame.get('frameWorldReadiness', {}), status.get('worldReadiness', {})
        current_epoch = payload.get('epoch')
        if (fresh and payload.get('ready') is True and gate.get('ready') is True
                and status.get('inputAvailable') is True and type(current_epoch) is int
                and current_epoch >= epoch and current_epoch == gate.get('epoch')
                and observation_timestamp(frame) > cutoff):
            self.barrier = None
            return True
        return False

    def execute(self, trigger, release_input, reset_history, discard_frames, still_current):
        """One acknowledged release/reset transaction; pending control always wins and failures stay latched."""
        event = dict(trigger)
        if not still_current():
            self.interrupt('controlOrWorldChangedBeforeRecovery')
            return dict(event, outcome='supersededBeforeRelease')
        self.armed = False
        self.attempts += 1
        self.post_reset_noops = 0
        self.pending_movement.clear()
        self.interrupt('resettingHistory')
        try:
            released = release_input()
            epoch = released.get('worldReadiness', {}).get('epoch')
            stamp = released.get('serverNowMs')
            if (released.get('type') != 'released' or not finite(stamp) or stamp < 0
                    or type(epoch) is not int or epoch < 0):
                raise RuntimeError('Navigation recovery requires a timed, acknowledged bridge release')
            self.release_at = stamp
            self.barrier = (stamp, epoch)
            event.update(releasedAtMs=stamp, readinessEpoch=epoch)
            discard_frames()
        except Exception as error:
            self.reason = 'releaseFailed'
            return dict(event, outcome='releaseFailed', error=str(error))
        if not still_current():
            self.reason = 'controlChangedAfterRelease'
            return dict(event, outcome='supersededAfterRelease')
        try:
            reset_history()
            self.resets += 1
            self.reason = 'awaitingFreshWorldAfterReset'
            return dict(event, outcome='reset')
        except Exception as error:
            self.reason = 'resetFailed'
            return dict(event, outcome='resetFailed', error=str(error))
