"""Pure, default-off climb-drop policy used by the serial live-client integration.

Integration contract (stream_client.ClimbRecoveryStream):
* Keep one instance for this bounded authenticated lease. On a clean reconnect,
  pass its attempts as initial_attempts; never reconnect while blocks_model is
  true. Preserve its cooldown_until_ns in the resident handoff as well. Check
  the actual Bridge handle/hello and resident token before every call/write.
* Route through the serial policy thread after goal/control processing, before
  predict. Continue ordinary frame/receipt ingestion while blocks_model is true.
  Do not call hold() merely to wait: it releases/reset state prematurely.
* X needs separate explicit recovery authorization AND the original hello's X
  capability. Keep the model's WASD/SHIFT allowlist unchanged. This class never
  grants permission and never writes to a transport or calls model/native code.
* A release intent uses the existing guarded Bridge.request('release'). Join its
  returned receipt batch normally, then call released(). A reset_history intent
  means discard queued frames and reset the settled model (no pending proposal),
  then call history_reset_done(). Reset failure must call fail().
* drop_ready is not permission to write. Under receive/control serialization,
  recheck current identity/source and call claim_action with a fresh unique ID.
  Send ONLY intent['arguments'] through the existing standard action protocol;
  record the enclosing recovery origin separately. Never predict/finish_action
  or label the recovery request as a model proposal. Admission and terminal
  receipt are separate callbacks; receipt batches can arrive before admission
  processing, so queue them until admitted() has joined the response.
* No model proposal/release is emitted while awaiting a terminal receipt. After
  successful completion, cleanup release + reset + fresh exit evidence are
  mandatory. Receipt endedAtMs is PRE-release; release ack is our later barrier,
  not physical release proof. Pause/stop/timeout/failure may interrupt immediately
  using ordinary best-effort cleanup; never wait out this policy to obey stop.
* Preserve all receipts in the normal recorder. Route our modelId separately
  from model feedback/no-op recovery; receipt loss or unknown dispatch calls
  fail(), which never re-arms. The caller executes required cleanup once and
  retains its error separately. Convert recovery I/O failures into terminal
  resident errors after recording/cleanup; do not use the transport reconnect
  path to re-arm an unresolved lease. Timeouts require observe() heartbeats.

This first policy is for the standard terminal-receipt channel, not queued v2.
Two distinct climb observations >=60ms apart; a 100ms X step; <=150ms source
age at dispatch; <=250ms source-relative expiry; max two attempts per instance,
>=750ms after successful cleanup/reset before a same-incident retry. Starting
a separate incident retains the >=5s release-based cooldown. Exit is two fresh
native 'normal' observations >=60ms
apart after acknowledged release; it is NOT proof of groundedness or success.
All timings are conservative prototype bounds, not measured recovery efficacy.
"""

import copy
import math

from observation_timing import observation_timestamp


ORIGIN = 'navigation-climb-drop-v1'
MOTION_METHOD = 'native_key_tip_templates_v1'
MAX_AGE_MS = 150
SETTLE_MS = 60
CONFIRM_GAP_MS = 250
COOLDOWN_NS = 5_000_000_000
INCIDENT_RETRY_NS = 750_000_000


def _finite(value):
    """Do not accept Boolean, string or nonfinite clocks."""
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _text(value):
    """Keep retained opaque identities small, nonempty and printable."""
    return type(value) is str and 0 < len(value) <= 128 and all(ord(c) >= 32 for c in value)


class NavigationClimbRecovery:
    """Serial pure state machine; outputs bounded intents, never executes them."""

    def __init__(self, hello, *, enabled=False, input_requested=False, x_authorized=False,
                 max_attempts=2, initial_attempts=0, initial_cooldown_until_ns=0):
        """Pin one authenticated hello; false/missing opt-ins cannot become active later."""
        if any(type(x) is not bool for x in (enabled, input_requested, x_authorized)):
            raise ValueError('boolean_options_required')
        if type(max_attempts) is not int or not 1 <= max_attempts <= 2:
            raise ValueError('attempt_bound')
        if type(initial_attempts) is not int or not 0 <= initial_attempts <= max_attempts:
            raise ValueError('initial_attempt_bound')
        if type(initial_cooldown_until_ns) is not int or initial_cooldown_until_ns < 0:
            raise ValueError('initial_cooldown_bound')
        self.phase = 'disabled'
        self.attempts = initial_attempts
        self.max_attempts = max_attempts
        self.failure = None
        self._cleanup_pending = False
        self._lease = (hello.get('sessionId'), hello.get('ownerEpoch'))
        self._token = None
        self._confirmation = None
        self._source = None
        self._last_ns = -1
        self._deadline = None
        self._cooldown = initial_cooldown_until_ns
        self._retry_after_ns = 0  # Only completed cleanup/reset arms this incident clock.
        self._barrier = None
        self._minimum_release_ms = 0
        self._release_epoch = -1
        self._after_reset = None
        self._request = None
        self._accepted = None
        self._receipt = None
        self._used_ids = set()  # At most max_attempts; never recycled in this lease.
        motion = hello.get('motionEvidence', {})
        if enabled:
            if (not input_requested or not x_authorized or hello.get('inputEnabled') is not True
                    or type(hello.get('allowedKeys')) is not list or 'X' not in hello['allowedKeys']
                    or hello.get('supportsRelease') is not True
                    or hello.get('supportsStartBeforeMs') is not True
                    or not all(_text(x) for x in self._lease)
                    or type(motion.get('version')) is not int or motion['version'] != 1 or motion.get('method') != MOTION_METHOD
                    or motion.get('sameFrame') is not True or motion.get('normalIsGroundedProof') is not False):
                raise ValueError('climb_recovery_capability_or_permission')
            self.phase = 'monitoring'

    @property
    def blocks_model(self):
        """A confirming climb also prevents another model proposal, without releasing early."""
        return self.phase not in ('disabled', 'monitoring') or self._confirmation is not None

    @property
    def cooldown_until_ns(self):
        """Expose the monotonic not-before boundary for a clean resident lease handoff."""
        return self._cooldown

    def _event(self, kind, **values):
        """Return detached scalar evidence; the caller owns recording and side effects."""
        return dict(kind=kind, origin=ORIGIN, attempt=self.attempts, **values)

    def fail(self, reason):
        """Latch the first failure; only its first notification requests external cleanup."""
        self._latch(reason)
        return self._hold()

    def _latch(self, reason):
        """Preserve failure evidence until the caller can consume its cleanup intent."""
        if self.failure is None:
            self.failure = str(reason)[:128]
            self._cleanup_pending = True
        self.phase = 'quarantined'

    def _hold(self):
        """Consume at most one cleanup intent; repeated polls retain the original error."""
        cleanup, self._cleanup_pending = self._cleanup_pending, False
        return self._event('hold', reason=self.failure, cleanupRequired=cleanup) if self.failure else None

    def _check(self, context, now_ns):
        """Validate the caller's original connection/control projection at every boundary."""
        if self.phase == 'disabled':
            return False
        if self.failure is not None:
            return False
        if type(now_ns) is not int or now_ns < 0 or now_ns < self._last_ns:
            self._latch('client_clock_regression')
            return False
        self._last_ns = now_ns
        if (context.get('sessionId'), context.get('ownerEpoch')) != self._lease:
            self._latch('connection_identity_changed')
            return False
        token = context.get('controlToken')
        valid = (isinstance(token, tuple) and len(token) == 4
                 and all(type(x) is int and x >= 0 for x in token[:2])
                 and (token[2] is None or _text(token[2])) and token[3] == 'run')
        if (not valid or context.get('goalIntent') != 'ground-navigation'
                or context.get('inputEnabled') is not True or context.get('xAuthorized') is not True
                or context.get('standardChannel') is not True
                or self._token is not None and token != self._token):
            if self.phase == 'monitoring' and self._token is None:
                self._confirmation = None
                return False
            self._latch('connection_control_or_permission_changed')
            return False
        if self._deadline is not None and now_ns >= self._deadline:
            self._latch('recovery_phase_timeout:' + self.phase)
            return False
        return True

    def _fresh(self, frame, current, status_received_ns, now_ns):
        """Use existing source-clock math and exact same-frame motion/readiness joins."""
        try:
            payload, gate = frame['frameWorldReadiness'], current['worldReadiness']
            motion = frame['motionEvidence']
            anchor = observation_timestamp(frame)
            source = frame.get('hostSnapshot') or frame.get('sourceFrame')
            source_id = source.get('snapshotId', source.get('timestamp100ns'))
            source_key = (source.get('captureEpoch'), source_id)
            age = frame['serverNowMs'] - anchor + (now_ns-frame['clientReceivedNs'])/1e6 + frame['transportRoundTripMs']
            if (not _finite(anchor) or not _finite(age) or age >= MAX_AGE_MS
                    or not _finite(frame['transportRoundTripMs'])
                    or type(frame['clientReceivedNs']) is not int or not 0 <= frame['clientReceivedNs'] <= now_ns
                    or type(status_received_ns) is not int or status_received_ns < 0
                    or not 0 <= now_ns-status_received_ns <= 250_000_000
                    or type(frame['frameId']) is not int or frame['frameId'] <= 0
                    or type(payload.get('epoch')) is not int or payload['epoch'] < 0
                    or payload.get('ready') is not True or gate.get('ready') is not True
                    or gate.get('epoch') != payload['epoch'] or current.get('inputAvailable') is not True
                    or frame.get('inputAvailable') is not True or frame.get('frameQuality') != 'usable'
                    or payload.get('sourceFrameId') != frame['frameId']
                    or payload.get('sourceCapturedAtMs') != frame['capturedAtMs']
                    or motion.get('method') != MOTION_METHOD or not _text(source_key[0])
                    or type(source_id) is not int or source_id <= 0):
                return None
            if motion.get('status') == 'climb' and motion.get('spaceKeyMatched') is True and motion.get('xKeyMatched') is True:
                kind = 'climb'
            elif motion.get('status') == 'normal' and motion.get('spaceKeyMatched') is False and type(motion.get('xKeyMatched')) is bool:
                kind = 'normal'
            else:
                return None
            return (anchor, payload['epoch'], source_key, frame['frameId'], kind)
        except (KeyError, TypeError, ValueError, AttributeError):
            return None

    def _confirmed(self, sample, token):
        """Require a new frame/source, stable epoch/token and 60..250ms source spacing."""
        prior = self._confirmation
        if prior is None:
            self._confirmation = (sample, token)
            return False
        old, old_token = prior
        same = (old_token == token and old[1] == sample[1] and old[2][0] == sample[2][0]
                and old[4] == sample[4] and 0 <= sample[0]-old[0] <= CONFIRM_GAP_MS)
        if not same:
            self._confirmation = (sample, token)
            return False
        confirmed = (sample[2][1] > old[2][1] and sample[3] > old[3] and sample[0]-old[0] >= SETTLE_MS)
        if confirmed:
            self._confirmation = (sample, token)
        return confirmed

    def _release(self, context, now_ns, *, cleanup=False):
        """Reserve once before the caller can write; never retry an uncertain release."""
        self._token = context['controlToken']
        if cleanup:
            self._minimum_release_ms = self._receipt['endedAtMs']
        elif self._confirmation is not None:
            sample = self._confirmation[0]
            self._minimum_release_ms, self._release_epoch = sample[0], sample[1]
        if not cleanup:
            self.attempts += 1
            self._cooldown = now_ns + COOLDOWN_NS
            self._request = self._accepted = self._receipt = None
        self._retry_after_ns = 0
        self.phase = 'await_cleanup' if cleanup else 'await_release'
        self._deadline = now_ns + 1_000_000_000
        self._confirmation = None
        return self._event('release', cleanup=cleanup)

    def observe(self, frame, current, context, *, status_received_ns, now_ns):
        """Advance only on retained fresh observations; wait states emit no input intent."""
        if not self._check(context, now_ns):
            return self._hold()
        if self.phase not in ('monitoring', 'await_drop_frame', 'drop_ready', 'await_exit'):
            return None
        sample = self._fresh(frame, current, status_received_ns, now_ns)
        if sample is None:
            if self.phase == 'monitoring' and self._confirmation is not None:
                return self.fail('climb_confirmation_evidence_lost')
            self._confirmation = None
            return None
        if self._source is not None and sample[2][0] != self._source:
            return self.fail('capture_epoch_changed')
        if self.phase != 'monitoring' and (sample[0] < self._barrier[0] + SETTLE_MS or sample[1] < self._barrier[1]):
            self._confirmation = None
            return None
        token = context['controlToken']
        if sample[4] == 'normal':
            if self.phase == 'monitoring':
                self._confirmation = None
                return None
            if self._confirmed(sample, token):
                self.phase = 'monitoring'
                self._deadline = self._token = self._confirmation = self._source = None
                self._retry_after_ns = 0
                return self._event('resume', meaning='fresh_normal_hints_not_grounded_proof')
            return None
        if self.phase in ('await_drop_frame', 'drop_ready'):
            self.phase = 'drop_ready'
            return self._event('drop_ready')
        if not self._confirmed(sample, token):
            return None
        # A completed X that still leaves climb hints may retry within this incident.
        # Separate incidents keep the original resident cooldown and lifetime budget.
        not_before = self._retry_after_ns if self.phase == 'await_exit' else self._cooldown
        if now_ns < not_before:
            return None
        if self.attempts >= self.max_attempts:
            return self.fail('attempt_budget_exhausted')
        self._source = sample[2][0]
        return self._release(context, now_ns)

    def released(self, response, context, *, now_ns):
        """Release acknowledgment is a post-call source barrier; it is not OS delivery proof."""
        if not self._check(context, now_ns):
            return self._hold()
        if self.phase not in ('await_release', 'await_cleanup'):
            return self.fail('unexpected_release_ack')
        if not isinstance(response, dict):
            return self.fail('invalid_release_ack')
        gate, stamp = response.get('worldReadiness', {}), response.get('serverNowMs')
        if (response.get('type') != 'released' or not _finite(stamp) or stamp < self._minimum_release_ms
                or not isinstance(gate, dict) or type(gate.get('epoch')) is not int
                or gate['epoch'] <= self._release_epoch):
            return self.fail('invalid_release_ack')
        if self._receipt is not None and stamp < self._receipt['endedAtMs']:
            return self.fail('release_before_terminal')
        self._barrier = (stamp, gate['epoch'])
        self._after_reset = 'await_exit' if self.phase == 'await_cleanup' else 'await_drop_frame'
        self.phase = 'await_reset'
        self._deadline = now_ns + 1_000_000_000
        return self._event('reset_history', discardFrames=True)

    def history_reset_done(self, context, *, now_ns):
        """Caller acknowledges the actual successful reset, never predicts to manufacture state."""
        if not self._check(context, now_ns):
            return self._hold()
        if self.phase != 'await_reset':
            return self.fail('unexpected_history_reset')
        self.phase = self._after_reset
        # This clock starts only after matching terminal, cleanup and actual reset.
        self._retry_after_ns = now_ns + INCIDENT_RETRY_NS if self.phase == 'await_exit' else 0
        self._deadline = now_ns + (7_000_000_000 if self.phase == 'await_exit' else 2_000_000_000)
        self._confirmation = None
        return None

    def claim_action(self, frame, current, context, request_id, *, status_received_ns, now_ns):
        """Recheck immediately before transport and retain exact arguments before any write."""
        if not self._check(context, now_ns):
            return self._hold()
        sample = self._fresh(frame, current, status_received_ns, now_ns)
        if (self.phase != 'drop_ready' or sample is None or sample[4] != 'climb'
                or sample[2][0] != self._source or sample[0] < self._barrier[0] + SETTLE_MS
                or sample[1] < self._barrier[1] or not _text(request_id) or request_id in self._used_ids):
            return self.fail('drop_prewrite_validation_failed')
        self._request = dict(requestId=request_id, modelId=ORIGIN, frameId=frame['frameId'],
                             observedAtMs=frame['capturedAtMs'], startBeforeMs=sample[0]+MAX_AGE_MS,
                             expiresAtMs=sample[0]+250,
                             steps=[dict(keys=['X'], durationMs=100, mouseDx=0, mouseDy=0)])
        self._release_epoch = sample[1]
        self._used_ids.add(request_id)
        self.phase = 'await_admission'
        self._deadline = now_ns + 1_000_000_000
        return self._event('action', arguments=copy.deepcopy(self._request))

    def admitted(self, response, context, *, now_ns, payload_bytes=0):
        """Acceptance is not application; refusal/unknown never silently retries this action."""
        if not self._check(context, now_ns):
            return self._hold()
        if not isinstance(response, dict):
            return self.fail('drop_rejected_or_unknown')
        if (self.phase == 'await_admission' and payload_bytes == 0 and response.get('type') == 'rejected'
                and response.get('requestId') == self._request['requestId']):
            return self.fail('drop_rejected')
        if (self.phase != 'await_admission' or payload_bytes != 0 or response.get('type') != 'accepted'
                or response.get('requestId') != self._request['requestId']
                or not _finite(response.get('acceptedAtMs'))
                or not _finite(response.get('receivedAtMs'))
                or response['receivedAtMs'] > response['acceptedAtMs']
                or not self._request['observedAtMs'] <= response['acceptedAtMs'] < self._request['startBeforeMs']):
            return self.fail('drop_rejected_or_unknown')
        self._accepted = response['acceptedAtMs']
        self.phase = 'await_terminal'
        self._deadline = now_ns + 1_000_000_000
        return None

    def receipt(self, value, context, *, now_ns, dropped_receipts=0):
        """Join the sole recovery receipt; unrelated model receipts keep their own pipeline."""
        if not self._check(context, now_ns):
            return self._hold()
        if type(dropped_receipts) is not int or dropped_receipts != 0:
            return self.fail('receipt_loss')
        if not isinstance(value, dict):
            return self.fail('malformed_receipt')
        if self._request is None or value.get('requestId') != self._request['requestId']:
            return None
        if self._receipt is not None:
            return None if value == self._receipt else self.fail('conflicting_recovery_receipt')
        steps = value.get('appliedSteps')
        if (set(value) != {'requestId', 'modelId', 'frameId', 'status', 'reason', 'acceptedAtMs', 'endedAtMs', 'appliedSteps'}
                or self.phase != 'await_terminal' or value.get('modelId') != ORIGIN
                or value.get('frameId') != self._request['frameId'] or value.get('status') != 'completed'
                or value.get('reason') != 'horizon_complete' or value.get('acceptedAtMs') != self._accepted
                or not _finite(value.get('endedAtMs')) or not isinstance(steps, list) or len(steps) != 1):
            return self.fail('recovery_terminal_mismatch')
        step = steps[0]
        if (not isinstance(step, dict) or set(step) != {'index', 'startedAtMs', 'keys', 'mouseDx', 'mouseDy'}
                or type(step.get('index')) is not int or step['index'] != 0
                or step.get('keys') != ['X'] or type(step.get('mouseDx')) is not int or step['mouseDx'] != 0
                or type(step.get('mouseDy')) is not int or step['mouseDy'] != 0 or not _finite(step.get('startedAtMs'))
                or not self._accepted <= step['startedAtMs'] < self._request['startBeforeMs']
                or not step['startedAtMs'] <= value['endedAtMs'] < self._request['expiresAtMs']):
            return self.fail('recovery_application_mismatch')
        self._receipt = copy.deepcopy(value)
        return self._release(context, now_ns, cleanup=True)
