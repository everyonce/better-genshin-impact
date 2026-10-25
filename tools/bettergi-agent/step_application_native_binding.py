"""Default-off eager coordinator; no factory, activation, continuous scheduling or rearm."""
import hashlib
import math
import time

from native_history_feedback import FeedbackError, require
from step_application_history_owner import StepApplicationHistoryOwner
from step_application_transport import StepApplicationIntake, validate_submission
import step_application_protocol as p

AVAILABLE = False
METADATA_BYTES = 65536


class StepApplicationNativeBinding:
    """Serialize inert/worker operations on the original owner thread, outside transport locks.

    This isolated constructor requires explicit inert selection. It is not a
    loaded-checkpoint attestation or a production authentication/activation path.
    Those unavailable bindings must be implemented and qualified separately.
    """
    def __init__(self, owner, bridge, intake, model_contract, *, inert=False, clock_ns=None):
        require(inert is True and type(owner) is StepApplicationHistoryOwner
                and type(intake) is StepApplicationIntake, 'native_application_installation_unavailable')
        require(getattr(bridge, '_step_application_intake', None) is intake, 'bridge_intake_identity')
        self.owner, self.bridge, self.intake = owner, bridge, intake
        self._handle = bridge.handle
        self._hello = self._hello_bytes()
        self._model = p.canonical(model_contract, 512)
        self._clock = time.perf_counter_ns if clock_ns is None else clock_ns
        self._pending = None
        self._settled = []
        self._failure = None
        self._last_error = None
        self._last_disposition = None
        owner.attach(intake, bridge, model_contract)

    def _hello_bytes(self):
        """Bind typed hello session/owner/goal to the confirmed channel, never a replacement lease."""
        value = {name:self.bridge.hello[name] for name in ('sessionId','ownerEpoch','goalVersion')}
        require(all(type(value[name]) is str and value[name] == self.intake.config[name]
                    for name in ('sessionId','ownerEpoch')), 'bridge_hello_identity')
        require(type(value['goalVersion']) is int and value['goalVersion'] == 1, 'bridge_goal')
        return p.canonical(value, 2048)

    def _guard(self):
        """Every operation remains on the same owner thread, Bridge, handle and intake."""
        self.owner._thread_check()
        try:
            require(self.bridge.handle is self._handle
                and getattr(self.bridge, '_step_application_intake', None) is self.intake
                and self._hello_bytes() == self._hello, 'connection_replaced')
            require(self._failure is None and not self.intake.ledger.quarantined, 'coordinator_quarantined')
        except BaseException as error:
            self._quarantine('connection_or_channel', error)

    def _quarantine(self, stage, error):
        """Preserve primary versus cleanup failure and retain the actual native stage."""
        if self._failure is None:
            self._failure = dict(stage=stage[:64], type=type(error).__name__[:64],
                                 message=str(error)[:512], cleanupError=None)
        return self.owner.quarantine(stage, error)

    def _operation(self, token):
        """Exact object tokens protect successor operations from stale/equal-looking tokens."""
        require(self._pending is not None and self._pending['proposal'].token is token, 'coordinator_token')
        return self._pending

    def propose(self, image, decision_identity, *, cutoff_client_ns, source_size=None,
                observation_profile='p2p-native-hamming-192-v1'):
        """Retain one native proposal; record its original knowledge cutoff without backfilling."""
        self._guard()
        require(self._pending is None and len(self._settled) < 32, 'coordinator_pending_or_capacity')
        self.owner.reconcile()
        p.identity(decision_identity)
        p.integer(cutoff_client_ns)
        snapshot = self.intake.ledger.snapshot(cutoff_client_ns=cutoff_client_ns)
        try:
            started = self._clock()
            proposal = self.owner.propose(image, decision_identity, source_size, observation_profile)
            self._pending = dict(proposal=proposal, identity=p.canonical(decision_identity, 2048),
                cutoff=cutoff_client_ns, contextDigest=hashlib.sha256(snapshot).hexdigest(),
                proposalWallNs=None, request=None, wire=None, transportStarted=False,
                mirrored=False, publishing=False, digest=None, ledgerGeneration=None)
            returned = self._clock()
            require(type(started) is int and type(returned) is int and returned >= started, 'proposal_clock')
            self._pending['proposalWallNs'] = returned-started
            return proposal
        except BaseException as error:
            return self._quarantine('proposal_boundary', error)

    def bind(self, token, request):
        """Preserve original model output and bind both owners before any transport invocation."""
        self._guard(); operation = self._operation(token)
        require(operation['request'] is None, 'single_native_binding')
        origin = p.decode(operation['identity'])
        try:
            raw = validate_submission(request)
            require(request['requestId'] == self.owner.submission_id(token), 'request_id_not_native')
            # Validate a detached mapping before the native owner's guarded bind.
            p.make_binding(origin, request, operation['proposal'].result['steps'], p.decode(self._model))
            self.owner.bind_submission(token, request, origin, self.bridge)
            operation['request'] = raw
            wire = self.intake.propose(request, origin, operation['proposal'].result['steps'],
                                       p.decode(self._model), token)
            operation['wire'] = p.canonical(wire, 65536)
            return p.decode(operation['wire'], 65536)
        except BaseException as error:
            # No Bridge method has been invoked; no exception-type inference is used.
            self._last_error = dict(stage='bind', type=type(error).__name__[:64], message=str(error)[:512])
            try:
                require(operation['transportStarted'] is False, 'prewrite_abort_after_transport')
                if self.owner._submission is None:
                    self._last_disposition = self.owner.not_submitted(token, origin)
                else:
                    request_id = p.decode(operation['request'])['requestId']
                    proof = self.intake.abort_prewrite_registration(request_id, token)
                    self._last_disposition = self.owner.cancel_unwritten_bound(token, proof, origin, self.bridge)
                self._settled.append(token); self._pending = None
            except BaseException as cleanup:
                self._failure = dict(stage='bind', type=type(error).__name__[:64], message=str(error)[:512],
                    cleanupError=dict(type=type(cleanup).__name__[:64], message=str(cleanup)[:512]))
                self.intake.ledger.uncertain('bind_cleanup_failed')
                if self.owner.status['phase'] != 'poisoned':
                    try:self.owner.quarantine('bind_cleanup_failed', cleanup)
                    except BaseException:pass
            raise

    def not_submitted(self, token):
        """Local cancellation is safe only before transport entry, including registered bindings."""
        self._guard(); operation = self._operation(token)
        require(operation['transportStarted'] is False, 'transport_may_have_written')
        origin = p.decode(operation['identity'])
        if operation['request'] is None:
            result = self.owner.not_submitted(token, origin)
        else:
            request = p.decode(operation['request'])
            proof = self.intake.abort_prewrite_registration(request['requestId'], token)
            result = self.owner.cancel_unwritten_bound(token, proof, origin, self.bridge)
        self._last_disposition = result
        self._settled.append(token); self._pending = None
        return result

    def dispatch(self, token, *, current_server_ms):
        """One dispatch only; preserve 50 ms computation and 100/150 ms source/start limits."""
        self._guard(); operation = self._operation(token)
        require(operation['wire'] is not None and operation['transportStarted'] is False, 'dispatch_once')
        request = p.decode(operation['request'])
        require(type(current_server_ms) in (int, float) and math.isfinite(current_server_ms), 'source_clock')
        observed = request['observedAtMs']; deadline = request.get('startBeforeMs')
        eligible = (operation['proposalWallNs'] < 50_000_000 and deadline is not None
            and observed <= current_server_ms < deadline <= observed+100
            and deadline <= request['expiresAtMs'] <= observed+150)
        if not eligible:
            return self.not_submitted(token)
        wire = p.decode(operation['wire'], 65536)
        operation['transportStarted'] = True
        try:
            response, pixels = self.bridge.request(wire['command'], **{key:value for key,value in wire.items()
                if key not in {'version','command','sessionId','ownerEpoch','goalVersion'}})
            require(pixels == b'', 'action_payload_not_empty')
        except BaseException as error:
            # The exact retained disposition, not the exception or a zero write count, controls rollback.
            self._last_error = dict(stage='dispatch', type=type(error).__name__[:64], message=str(error)[:512])
            proof = self.intake.submission_disposition(request['requestId'], token)
            if proof.status == 'known_not_submitted' and proof.write_attempted is False:
                try:
                    self._last_disposition = self.owner.cancel_unwritten_bound(token, proof,
                        p.decode(operation['identity']), self.bridge)
                    self._settled.append(token); self._pending = None
                except BaseException as cleanup:
                    self._failure = dict(stage='dispatch', type=type(error).__name__[:64], message=str(error)[:512],
                        cleanupError=dict(type=type(cleanup).__name__[:64], message=str(cleanup)[:512]))
                    self.intake.ledger.uncertain('dispatch_cleanup_failed')
                raise
            return self._quarantine('dispatch_unknown', error)
        return self.pump(token, current_identity=p.decode(operation['identity']))

    def pump(self, token, *, current_identity):
        """Reconcile the whole batch, mirror its admission, then publish exactly once outside locks."""
        if any(token is old for old in self._settled):
            return None
        operation = self._operation(token)
        try:
            self._guard()
            require(not operation['publishing'], 'publication_reentrant')
            require(p.canonical(current_identity, 2048) == operation['identity'], 'publication_origin_changed')
            self.owner.reconcile()
            request = p.decode(operation['request'])
            proof = self.intake.submission_disposition(request['requestId'], token)
            require(proof.status in ('accepted', 'rejected'), 'application_admission_unknown')
            if not operation['mirrored']:
                result = self.owner.admission_from_disposition(token, proof, current_identity, self.bridge)
                operation['mirrored'] = True
                if result is not None:
                    self._last_disposition = result
                    self._settled.append(token); self._pending = None
                    return result
            status = self.intake.ledger.submission_status(request['requestId'], token)
            if status['sequence'] is None or self.owner._unresolved is not None:
                return None
            ticket = self.intake.ledger.publication_ticket(status['sequence'], token)
            operation['publishing'] = True
            def commit(exact_token, raw):
                """The ledger's callback is the sole route to the retained numerical second pass."""
                operation['digest'] = self.owner.stage_application(exact_token, raw, current_identity,
                                                                  self.bridge, ticket)
                return operation['digest']
            generation = self.intake.ledger.publish(ticket.sequence, token, commit)
            operation['ledgerGeneration'] = generation
            result = self.owner.finish_publication(token, generation, operation['digest'],
                                                   current_identity, self.bridge, ticket)
            self.owner.reconcile()
            self._last_disposition = result
            self._settled.append(token); self._pending = None
            return result
        except BaseException as error:
            return self._quarantine('publication_or_reconciliation', error)

    def ingest_returned(self, *, current_identity=None):
        """After an external serialized status/frame response, inspect facts with no model callback in I/O."""
        try:
            self._guard()
            self.owner.reconcile()
            if self._pending is None:
                return None
            require(current_identity is not None, 'current_identity_required')
            return self.pump(self._pending['proposal'].token, current_identity=current_identity)
        except BaseException as error:
            return self._quarantine('intake_reconciliation', error)

    def observe(self, *, current_identity=None):
        """One serialized status observation; transport failure is immediately terminal for the owner."""
        try:
            self._guard()
            response, pixels = self.bridge.request('status')
            require(pixels == b'', 'status_payload_not_empty')
            return self.ingest_returned(current_identity=current_identity)
        except BaseException as error:
            return self._quarantine('status_observation', error)

    def metadata(self):
        """Bound detached stage/cutoff evidence; request payloads and numerical resources stay private."""
        row = self._pending
        pending = None if row is None else dict(sequence=row['proposal'].token.sequence,
            cutoffClientNs=row['cutoff'], decisionContextSha256=row['contextDigest'],
            proposalWallNs=row['proposalWallNs'], transportStarted=row['transportStarted'],
            mirrored=row['mirrored'], publishing=row['publishing'], ledgerGeneration=row['ledgerGeneration'])
        return p.canonical(dict(version=1, pending=pending, settledCount=len(self._settled), failure=self._failure,
            lastError=self._last_error,
            owner=p.decode(self.owner.metadata(), METADATA_BYTES), activationAvailable=False,
            loadedCheckpointAttestationAvailable=False, continuousControlAvailable=False), METADATA_BYTES)

    def install(self):
        """No CLI, bridge slot replacement or unavailable producer opt-in is supplied."""
        raise FeedbackError('native_application_installation_unavailable')
