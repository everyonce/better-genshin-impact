"""Eager software-application publication; no live installation or graph settlement."""
from dataclasses import dataclass
import hashlib
import json

from native_history_feedback import FeedbackError, ProposalToken, require
from receipt_history_owner import ReceiptHistoryOwner, ReceiptSettlement, identity
from receipt_history_runtime import ReceiptHistoryRuntime
import step_application_protocol as p

AVAILABLE = False
METADATA_BYTES = 65536


@dataclass(frozen=True)
class ApplicationSettlement:
    """Model history publication is neither physical execution nor a completed 50 ms hold."""
    owner: str
    generation: int
    sequence: int
    publication_generation: int
    application_sequence: int
    digest: bytes
    evidence_basis: str = 'software-step-application-v1'
    physical_hold_or_release_proven: bool = False
    game_effect_proven: bool = False
    horizon_completion_proven: bool = False


class StepApplicationHistoryOwner(ReceiptHistoryOwner):
    """Retain one pending operation and one published bundle awaiting an exact terminal.

    Direct construction is an isolated worker/inert seam. Production activation is
    unavailable. Real construction requires the accepted eager runtime exactly;
    explicit inert construction permits a pure fake runtime for lifecycle tests.
    """
    def __init__(self, adapter, runtime, *, inert=False):
        require(type(inert) is bool and (inert or type(runtime) is ReceiptHistoryRuntime), 'eager_runtime_type')
        require(adapter.use_cuda_graph is False and adapter.graph is None, 'eager_runtime_only')
        super().__init__(adapter, runtime)
        self._channel = None
        self._connection = None
        self._scope = None
        self._continuity = None
        self._publication = None
        self._unresolved = None
        self._tombstones = []
        self._inert = inert
        self._protocol = p

    def attach(self, intake, connection, model_contract):
        """Bind one exact confirmed channel and declared loaded-model contract; no activation."""
        self._ready()
        require(self._channel is None and connection is not None, 'owner_already_attached')
        p.fields(model_contract, ('checkpointSha256', 'profile', 'mapping'))
        p.digest(model_contract['checkpointSha256'])
        require(model_contract['profile'] == 'p2p-native-hamming-192-v1'
            and model_contract['mapping'] == 'native-raw-to-one-step-v1', 'native_model_contract')
        require(self._adapter.observation_profile == model_contract['profile']
            and self._adapter.mouse_sampling == 'truncated_normal', 'loaded_native_options')
        self._channel = intake
        self._connection = connection
        self._model_contract = p.canonical(model_contract, 512)
        self._protocol = p.for_configuration(intake.config)
        require(getattr(intake, 'protocol', p) is self._protocol, 'channel_protocol_changed')
        self._channel_config = self._protocol.configuration(intake.config)
        self._guard()

    def _channel_guard(self, connection):
        """An echoed label or replacement connection cannot become the bound channel."""
        require(self._channel is not None and connection is self._connection, 'bound_connection')
        require(self._protocol.configuration(self._channel.config) == self._channel_config
                and getattr(self._channel, 'protocol', p) is self._protocol, 'channel_configuration_changed')
        require(not self._channel.ledger.quarantined, 'application_channel_quarantined')

    def _verify_continuity(self):
        """Verify the retained original-lease checkpoint, never accept a fresh RNG baseline."""
        if self._continuity is not None:
            require(self._runtime.history_identity(self._adapter) == self._continuity['history'],
                    'completed_history_changed')
            self._runtime.verify_rng(self._continuity['rng'])

    def _claim(self):
        """Inherited proposal claims once; checkpoint validation runs before its snapshot/prepare."""
        super()._claim()
        try:
            self._verify_continuity()
        except BaseException as error:
            self._poison('next_claim_checkpoint', error)

    def propose(self, image, decision_identity, source_size=None, observation_profile=None):
        """Delegate inherited preparation once, preserving its native sampling and CPU decode."""
        self._ready()
        try:
            self._channel_guard(self._connection)
            require(len(self._tombstones) < 32, 'owner_attempt_capacity')
            require(self._channel.ledger.proposal_capacity(), 'channel_pending_or_capacity')
            origin = json.loads(identity(decision_identity))
            scope = p.canonical({key:value for key,value in origin.items() if key != 'frameId'})
            require(self._scope is None or self._scope == scope, 'decision_epoch_changed')
            self._scope = scope
            return super().propose(image, decision_identity, source_size, observation_profile)
        except BaseException as error:
            if self._phase == 'poisoned':
                raise
            self._poison('application_propose', error)

    def _finish(self, token, committed, reason):
        """Only known rejection/local cancellation uses this inherited discard callback."""
        require(not committed and self._publication is None, 'application_finish_bypass')
        checkpoint = dict(history=self._runtime.history_identity(self._adapter), rng=self._runtime.save_rng())
        self._runtime.verify_rng(checkpoint['rng'])
        self._continuity = checkpoint
        result = ReceiptSettlement(False, reason, token.generation, token.sequence,
            'local-not-submitted' if reason == 'local_not_submitted' else 'known-not-admitted')
        # Keep original pending/snapshot owners until release and its checkpoint check pass.
        self._release()
        self._verify_continuity()
        self._tombstone(token, reason)
        self._clear_pending()
        return result

    def _tombstone(self, token, outcome):
        """Keep only bounded anti-replay metadata after healthy resource reconciliation."""
        require(len(self._tombstones) < 32, 'owner_attempt_capacity')
        self._tombstones.append(dict(generation=token.generation, sequence=token.sequence, outcome=outcome))

    def _clear_pending(self):
        """Clear only after successful finalization; uncertain paths never call this helper."""
        self._pending = self._snapshot = self._prepared = self._candidate_guard = None
        self._origin = self._submission = self._post_proposal_rng = None
        self._accepted = False
        self._phase = 'ready'

    def cancel_unwritten_bound(self, token, proof, current_identity, connection):
        """Use exact retained H02 zero-write disposition; never erase binding to bypass checks."""
        self._token(token)
        try:
            self._channel_guard(connection)
            self._pending_guard(token, current_identity)
            require(self._submission is not None and connection is self._submission[1] and not self._accepted,
                    'bound_unwritten_only')
            request_id = json.loads(self._submission[0])['requestId']
            row = self._channel.verify_disposition(proof, token, request_id)
            require(proof.status == 'known_not_submitted' and proof.write_attempted is False
                and (row is None and proof.registered is False or
                     row is not None and row['phase'] == 'not_submitted' and row['sequence'] is None),
                'not_definitively_unwritten')
            return self._discard(token, 'local_not_submitted')
        except BaseException as error:
            self._poison('cancel_unwritten_bound', error)

    def not_submitted(self, token, current_identity):
        """Local cancellation cannot reopen a quarantined channel."""
        self._token(token)
        try:
            self._channel_guard(self._connection)
            return super().not_submitted(token, current_identity)
        except BaseException as error:
            if self._phase == 'poisoned':
                raise
            self._poison('application_not_submitted', error)

    def admission_from_disposition(self, token, proof, current_identity, connection):
        """Mirror admission only after complete response/batch validation has succeeded."""
        self._token(token)
        try:
            self._channel_guard(connection)
            request_id = self.submission_id(token)
            row = self._channel.verify_disposition(proof, token, request_id)
            require(proof.status in ('accepted', 'rejected') and proof.write_attempted is True
                and row is not None and not row['quarantined'], 'unvalidated_admission')
            return super().admission(token, dict(requestId=request_id, type=proof.status),
                                     current_identity, connection)
        except BaseException as error:
            if self._phase == 'poisoned':
                raise
            self._poison('application_admission', error)

    def admission(self, *args, **kwargs):
        """An arbitrary accepted/rejected dictionary is not whole-batch authority."""
        raise FeedbackError('use_validated_submission_disposition')

    def stage_application(self, token, raw_record, current_identity, connection, ticket):
        """Commit once outside ledger/transport locks, retaining every returned owner immediately."""
        self._token(token)
        try:
            self._channel_guard(connection)
            self._pending_guard(token, current_identity)
            ledger = self._channel.ledger
            ledger.validate_native_ticket(ticket)
            require(ticket.token is token and ticket.raw == raw_record and self._publication is None,
                    'application_ticket_once')
            require(self._accepted and self._submission is not None and connection is self._submission[1],
                    'application_without_admission')
            record = p.decode(raw_record, p.RECORD_BYTES)
            require(self._protocol.validate_record(record, self._channel.config) == raw_record, 'application_canonical')
            request = json.loads(self._submission[0])
            expected = self._protocol.make_binding(json.loads(self._origin), request, self._pending.result['steps'],
                                      p.decode(self._model_contract))
            require(p.canonical(record['binding']) == expected and record['outcome'] == 'complete_returned'
                and record['evidenceComplete'] is True and record['executionUncertain'] is False,
                'application_binding_or_outcome')
            require(self._unresolved is None, 'earlier_terminal_unresolved')
            operation = dict(token=token, ticket=ticket, raw=raw_record, snapshot=self._snapshot,
                prepared=self._prepared, commitStarted=True, returned=None, assigned=False,
                verified=False, ledgerGeneration=None, ownerFinalized=False, digest=None)
            self._publication = operation
            self._phase = 'committing_application'
            operation['returned'] = self._runtime.commit(self._adapter, self._prepared)
            ledger.validate_native_ticket(ticket)
            idx, state = operation['returned']
            self._runtime.verify_rng(self._post_proposal_rng)
            self._guard()
            require(self._runtime.history_identity(self._adapter) == self._candidate_guard,
                    'commit_changed_predecessor_owner')
            self._adapter.idx, self._adapter.state = idx, state
            self._adapter.steps_seen = self._snapshot['steps'] + 1
            operation['assigned'] = True
            self._runtime.validate_history(self._adapter)
            self._runtime.synchronize(); self._guard()
            operation['history'] = self._runtime.history_identity(self._adapter)
            operation['rng'] = self._runtime.save_rng()
            self._runtime.verify_rng(self._post_proposal_rng)
            self._runtime.verify_rng(operation['rng'])
            operation['verified'] = True
            ledger.validate_native_ticket(ticket)
            identity_record = dict(version=self._protocol.VERSION, owner=self._identity, generation=token.generation,
                sequence=token.sequence, applicationSequence=ticket.sequence,
                receiptSha256=hashlib.sha256(raw_record).hexdigest(),
                historyIdentity=operation['history'])
            operation['digest'] = hashlib.sha256(p.canonical(identity_record, METADATA_BYTES)).digest()
            self._phase = 'publication_pending'
            return operation['digest']
        except BaseException as error:
            self._poison('stage_application', error)

    def finish_publication(self, token, generation, digest, current_identity, connection, ticket):
        """After ledger publication, verify and finalize under the original lease, then expose once."""
        self._thread_check()
        try:
            operation = self._publication
            require(self._phase == 'publication_pending' and operation is not None and self._leased
                and token is operation['token'] and ticket is operation['ticket'] and digest == operation['digest'],
                'publication_finalization_once')
            self._channel_guard(connection)
            require(identity(current_identity) == self._origin, 'publication_identity_changed')
            self._channel.ledger.validate_native_ticket(ticket, published=True, generation=generation, digest=digest)
            operation['ledgerGeneration'] = generation
            self._guard()
            require(self._runtime.history_identity(self._adapter) == operation['history'], 'publication_history_changed')
            self._runtime.verify_rng(operation['rng'])
            self._continuity = dict(history=operation['history'], rng=operation['rng'])
            self._unresolved = operation
            result = ApplicationSettlement(self._identity, token.generation, token.sequence,
                                           generation, ticket.sequence, digest,
                                           evidence_basis=f'software-step-application-v{self._protocol.VERSION}')
            self._release()
            self._verify_continuity()
            self._channel.ledger.complete_native_ticket(ticket, generation, digest)
            operation['ownerFinalized'] = True
            self._tombstone(token, 'software_step_application_published')
            self._publication = None
            self._clear_pending()
            return result
        except BaseException as error:
            self._poison('finish_publication', error)

    def reconcile(self):
        """Late contradiction quarantines current continuity; it never rolls back published history."""
        self._thread_check()
        try:
            require(self._phase in ('ready', 'pending'), 'terminal_owner_phase')
            self._channel_guard(self._connection)
            operation = self._unresolved
            if operation is None:
                return False
            ticket = operation['ticket']
            row = self._channel.ledger.submission_status(ticket.request_id, ticket.token)
            require(row['publishedGeneration'] == operation['ledgerGeneration']
                and row['stateDigest'] == operation['digest'].hex(), 'published_ledger_changed')
            if row['terminal'] is None:
                return False
            terminal = p.decode(row['terminal'], 4096)
            if self._protocol.VERSION == 1:
                require(terminal['status'] == 'completed' and terminal['reason'] == 'horizon_complete'
                    and terminal['applicationSequences'] == [ticket.sequence]
                    and terminal['releaseOutcome'] == 'returned_unverified', 'terminal_not_reconciled')
            else:
                require(self._channel.ledger.terminal_ready(ticket.request_id, ticket.token),
                        'terminal_not_reconciled')
            self._guard()
            if self._pending is None:
                self._verify_continuity()
            else:
                self._pending_guard(self._pending.token, json.loads(self._origin))
            self._unresolved = None
            return True
        except BaseException as error:
            self._poison('terminal_reconciliation', error)

    def quarantine(self, stage, error):
        """Keep both publication stages and every uncertain resource; cleanup cannot heal them."""
        self._channel.ledger.uncertain(stage)
        if self._phase == 'poisoned':
            raise error
        self._poison(stage, error)

    def metadata(self):
        """Bound stage evidence without serializing tensors, original requests or RNG states."""
        def stages(operation):
            if operation is None:
                return None
            return dict(sequence=operation['ticket'].sequence,
                commitStarted=operation['commitStarted'], returnedOwnerRetained=operation['returned'] is not None,
                assigned=operation['assigned'], verified=operation['verified'],
                ledgerGeneration=operation['ledgerGeneration'], ownerFinalized=operation['ownerFinalized'])
        return p.canonical(dict(version=self._protocol.VERSION, status=self.status, leased=self._leased,
            publication=stages(self._publication), unresolved=stages(self._unresolved),
            tombstones=self._tombstones, activationAvailable=False, numericalQualified=False), METADATA_BYTES)

    def receipt(self, *args, **kwargs):
        """Terminal-only publication is not an alternate authority for this owner."""
        raise FeedbackError('use_validated_step_application')

    def settle(self, *args, **kwargs):
        """Admission or booleans cannot publish native history."""
        raise FeedbackError('use_validated_step_application')

    def reset(self):
        """Release/rearm and activation boundaries are deliberately outside this increment."""
        raise FeedbackError('step_application_reset_unavailable')

    def set_goal(self, path):
        """Goal/epoch changes require a separately reviewed idle channel lifecycle."""
        raise FeedbackError('step_application_goal_change_unavailable')

    def close(self):
        """Healthy close requires all terminal evidence reconciled and no pending publication."""
        self._ready()
        require(self._unresolved is None and self._publication is None, 'unreconciled_close')
        self._channel_guard(self._connection)
        return super().close()
