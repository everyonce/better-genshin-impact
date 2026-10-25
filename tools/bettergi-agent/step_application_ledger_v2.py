"""Default-off v2 client ledger; ACK, software history and terminal settlement stay distinct.

Only detached wire facts are staged here. The inherited consume-once callback and
native ticket machinery remain unchanged and run outside the ledger lock. This
module is not a producer, queue scheduler, input executor or activation path.
"""
import hashlib
import threading

import step_application_protocol as p
import step_application_protocol_v2 as v2
from step_application_ledger import ClientLedger


class QueuedClientLedger(ClientLedger):
    """One confirmed channel with at most one unresolved published P and one pending Q."""
    def __init__(self, expected_config, enable_reply):
        """Confirm v2 exactly without presenting its wire bytes as a v1 enable response."""
        self._lock = threading.RLock()
        self._config = v2.configuration(expected_config)
        reply = p.decode(enable_reply, 8192)
        p.fields(reply, ('configuration', 'initialTracked', 'limits'))
        p.require(p.canonical(reply['configuration']) == self._config, 'enable_not_confirmed')
        p.require(p.canonical(reply['limits']) == p.canonical(p.LIMITS), 'negotiated_limits')
        p.tracked(reply['initialTracked'])
        p.require(reply['initialTracked']['complete'], 'unknown_initial_state')
        self._tracked = p.canonical(reply['initialTracked'])
        self._proposals = {}; self._records = {}; self._terminals = {}
        self._ack = self._server_ack = self._observed = self._generation = self._snapshot_cutoff = 0
        self._next_reserved = 1
        self._ticks = expected_config['sessionOriginTicks']
        self._quarantine = self._decision_scope = None
        self._publishing = self._closed_for_submission = self._authority_lost = False

    def proposal_link(self):
        """Return the exact latest published application, never an admitted or predicted one."""
        with self._lock:
            self._ready()
            p.require(not self._closed_for_submission, 'closed_for_submission')
            published = [row for row in self._proposals.values() if row['publishedGeneration'] is not None]
            if not published:
                return None
            latest = max(published, key=lambda row: row['publishedGeneration'])
            return v2.application_link(p.decode(self._records[latest['sequence']]['raw']))

    def propose(self, binding_bytes, token, *, request_bytes):
        """Bind typed queue linkage and only the three original source/deadline scalars."""
        with self._lock:
            self._ready()
            p.require(not self._closed_for_submission and token is not None, 'closed_or_private_token')
            bound = p.decode(binding_bytes, 3072); v2.binding(bound, p.decode(self._config))
            request = p.decode(request_bytes, 16384)
            p.require(v2.validate_submission(request) == request_bytes
                      and hashlib.sha256(request_bytes).hexdigest() == bound['submissionSha256'], 'proposal_request_bytes')
            p.require(v2.same(request['queueAfter'], bound['queueAfter'])
                      and v2.same(bound['queueAfter'], self.proposal_link()), 'proposal_predecessor')
            scope = p.canonical(dict(identity={k:v for k,v in bound['identity'].items() if k != 'frameId'},
                                     model=bound['model']))
            if self._decision_scope is not None and scope != self._decision_scope:
                self._poison('decision_or_model_epoch_changed')
                raise p.ProtocolError('decision_or_model_epoch_changed')
            p.require(self.proposal_capacity(), 'native_single_pending')
            request_id = bound['requestId']
            p.require(request_id not in self._proposals, 'request_reuse')
            times = {name:request[name] for name in ('observedAtMs', 'startBeforeMs', 'expiresAtMs')}
            self._decision_scope = scope
            self._proposals[request_id] = dict(binding=p.canonical(bound), token=token, phase='proposed',
                sequence=None, terminal=None, attempted=False, publishedGeneration=None,
                admission=None, sourceTimes=p.canonical(times, 256))

    def admission(self, request, token, *, accepted):
        """Only local proven non-submission uses this method; wire admission is whole-reply atomic."""
        p.require(accepted is False, 'v2_requires_atomic_admission')
        return super().admission(request, token, accepted=False)

    def proposal_capacity(self):
        """Closure stops new sampling without preventing final known publication or ACK."""
        with self._lock:
            self._ready()
            return not self._closed_for_submission and super().proposal_capacity()

    @property
    def closed_for_submission(self):
        """Closure is a sticky submission veto, separate from quarantined evidence authority."""
        with self._lock:
            return self._closed_for_submission

    def _lookup(self, sequence, staged):
        """Resolve actual retained/staged software evidence; never synthesize an ACKed row."""
        if sequence in staged:
            return staged[sequence]
        p.require(sequence in self._records, 'missing_linked_application')
        return p.decode(self._records[sequence]['raw'])

    def _admission_join(self, value, proposal, proposals, config):
        """Check fixed original schedules and deadlines, without any refreshed frame authority."""
        bound = p.decode(proposal['binding'])
        raw = v2.admission(value, config, bound)
        times = p.decode(proposal['sourceTimes'])
        start, end, admitted = (value[name] for name in ('scheduledStartMs', 'scheduledEndMs', 'admittedAtMs'))
        p.require(times['observedAtMs'] <= admitted <= start < times['startBeforeMs'] <= times['observedAtMs'] + 100
                  and end <= times['expiresAtMs'] <= times['observedAtMs'] + 150,
                  'admission_original_deadlines')
        previous = bound['queueAfter']
        if previous is not None:
            old = proposals.get(previous['requestId'])
            p.require(old is not None and old['publishedGeneration'] is not None
                      and old['sequence'] == previous['applicationSequence'] and old['admission'] is not None,
                      'queue_predecessor_unpublished')
            old_record = self._lookup(previous['applicationSequence'], {})
            p.require(v2.same(previous, v2.application_link(old_record)), 'queue_predecessor_link')
            old_admission = p.decode(old['admission']); old_times = p.decode(old['sourceTimes'])
            p.require(v2.same(start, old_admission['scheduledEndMs']) and start < old_times['expiresAtMs'],
                      'queue_boundary_or_predecessor_expiry')
        return raw

    def _application_join(self, row, proposals, staged):
        """Preserve application order and P/Q generations without waiting for Q history publication."""
        bound = row['binding']; previous = bound['queueAfter']
        proposal = proposals[bound['requestId']]
        p.require(proposal['admission'] is not None, 'application_schedule_missing')
        if previous is None:
            p.require(row['sequence'] == 1, 'initial_application_sequence')
            return
        old = self._lookup(previous['applicationSequence'], staged)
        p.require(v2.same(previous, v2.application_link(old)) and row['sequence'] == old['sequence'] + 1,
                  'successor_application_link')
        p.require(old['outcome'] == 'complete_returned' and old['evidenceComplete'] is True
                  and old['executionUncertain'] is False, 'predecessor_application_uncertain')
        p.require(v2.same(row['trackedBefore'], old['trackedAfter'])
                  and row['dispatchStartedTicks'] >= old['publicationTicks'], 'successor_application_chain')

    def _terminal_join(self, term, proposal, proposals, staged, terminals):
        """Join a terminal to actual Q software evidence, not to Q native-history publication."""
        sequence = proposal['sequence']
        matching = [n for n,row in staged.items() if row['binding']['requestId'] == term['binding']['requestId']]
        if matching:
            sequence = matching[0]
        p.require(term['applicationSequences'] == ([] if sequence is None else [sequence]), 'terminal_link')
        if sequence is not None:
            own = self._lookup(sequence, staged)
            p.require(term['publicationTicks'] >= own['publicationTicks'], 'terminal_publication_clock')
        if term['transition'] is None:
            return
        transition = term['transition']; successor = transition['successor']
        qrow = self._lookup(successor['applicationSequence'], staged)
        p.require(v2.same(successor, v2.application_link(qrow)) and sequence is not None
                  and qrow['sequence'] == sequence + 1
                  and v2.same(qrow['binding']['queueAfter'], v2.application_link(own)), 'handoff_pair_link')
        p.require(qrow['outcome'] == 'complete_returned' and qrow['evidenceComplete'] is True
                  and qrow['executionUncertain'] is False, 'handoff_successor_uncertain')
        qproposal = proposals[successor['requestId']]
        p.require(proposal['admission'] is not None and qproposal['admission'] is not None, 'handoff_schedule_missing')
        old_schedule = p.decode(proposal['admission']); new_schedule = p.decode(qproposal['admission'])
        old_times = p.decode(proposal['sourceTimes']); new_times = p.decode(qproposal['sourceTimes'])
        boundary = old_schedule['scheduledEndMs']; checked = transition['dispatchCheckedAtMs']
        p.require(v2.same(boundary, new_schedule['scheduledStartMs'])
                  and v2.same(transition['boundaryMs'], boundary)
                  and v2.same(transition['successorScheduledEndMs'], new_schedule['scheduledEndMs']), 'handoff_fixed_schedule')
        # P.startBeforeMs was consumed at P's dispatch and is intentionally absent here.
        p.require(boundary <= checked < new_schedule['scheduledEndMs']
                  and checked < new_times['startBeforeMs'] and checked < old_times['expiresAtMs']
                  and checked < new_times['expiresAtMs']
                  and checked <= term['legacyEndedAtMs'] < new_schedule['scheduledEndMs']
                  and term['legacyEndedAtMs'] < new_times['expiresAtMs']
                  and term['legacyEndedAtMs'] < old_times['expiresAtMs'], 'handoff_dispatch_deadline')
        p.require(transition['successorCallsReturnedTicks'] == qrow['callsReturnedTicks']
                  and term['publicationTicks'] >= qrow['publicationTicks'], 'handoff_software_return')

    def _legacy_join(self, receipts, terminals, proposals):
        """Reject co-present contradictions; drained legacy rows are never required authority."""
        p.require(type(receipts) is list and len(receipts) <= 256, 'legacy_receipt_count')
        fields = {'requestId','modelId','frameId','status','reason','acceptedAtMs','endedAtMs','appliedSteps'}
        for row in receipts:
            p.require(type(row) is dict and type(row.get('requestId')) is str, 'legacy_receipt_shape')
            request_id = row['requestId']; joined = terminals.get(request_id)
            if joined is None and request_id in self._terminals:
                joined = (p.decode(self._terminals[request_id]['raw'],4096), None)
            if joined is None: continue
            terminal = joined[0]; p.require(set(row) == fields, 'legacy_receipt_fields')
            proposal = proposals[request_id]; bound = p.decode(proposal['binding'],3072)
            schedule = p.decode(proposal['admission'],2048)
            for key in ('modelId','frameId'):
                p.require(v2.same(row[key], bound['identity'][key]), 'legacy_receipt_identity')
            for key in ('status','reason'):
                p.require(v2.same(row[key], terminal[key]), 'legacy_receipt_terminal')
            p.require(v2.same(row['endedAtMs'], terminal['legacyEndedAtMs']) and
                      v2.same(row['acceptedAtMs'], schedule['admittedAtMs']), 'legacy_receipt_clock')
            steps = row['appliedSteps']
            p.require(type(steps) is list and len(steps) <= 1, 'legacy_applied_steps')
            if terminal['status'] == 'completed': p.require(len(steps) == 1, 'legacy_complete_step')
            if steps:
                p.require(bool(terminal['applicationSequences']) and type(steps[0]) is dict and
                          set(steps[0]) == {'index','startedAtMs','keys','mouseDx','mouseDy'}, 'legacy_step_shape')
                step = steps[0]; expected = bound['step']
                p.require(type(step['index']) is int and step['index'] == 0, 'legacy_step_index')
                for key in ('keys','mouseDx','mouseDy'):
                    p.require(v2.same(step[key], expected[key]), 'legacy_step_operands')
                v2.elapsed(step['startedAtMs'])
                source = p.decode(proposal['sourceTimes'],256)
                p.require(schedule['scheduledStartMs'] <= step['startedAtMs'] < schedule['scheduledEndMs'] and
                          step['startedAtMs'] < source['startBeforeMs'], 'legacy_step_schedule')

    def ingest_reply(self, batch_bytes, terminal_bytes, *, observed_client_ns, admission=None, legacy_receipts=None):
        """Validate all reply facts in temporary tables before changing phase, facts, ACK or closure."""
        with self._lock:
            self._ready()
            try:
                p.integer(observed_client_ns, max(self._observed, self._snapshot_cutoff))
                config = p.decode(self._config); value = p.decode(batch_bytes)
                p.fields(value, ('version','channelId','acknowledgedThrough','nextReservedSequence',
                                 'authorityLost','unpublished','records','closedForSubmission'))
                p.require(type(value['version']) is int and value['version'] == 2
                          and value['channelId'] == config['channelId'], 'batch_channel')
                p.integer(value['acknowledgedThrough'], self._server_ack, self._ack)
                p.integer(value['nextReservedSequence'], self._next_reserved, p.OUTBOX_RECORDS + 1)
                p.integer(value['unpublished'], 0, 1)
                p.require(type(value['authorityLost']) is bool and type(value['closedForSubmission']) is bool, 'v2_batch_flags')
                p.require(not value['authorityLost'] or value['closedForSubmission'], 'v2_loss_must_close')
                rows = value['records']
                p.require(type(rows) is list and len(rows) <= p.BATCH_RECORDS, 'batch_count')
                finished = value['nextReservedSequence'] - 1 - value['unpublished']
                p.require(finished >= value['acknowledgedThrough'], 'batch_reserved_census')
                p.require(len(rows) == min(p.BATCH_RECORDS, finished-value['acknowledgedThrough']), 'batch_prefix_count')
                p.require(type(terminal_bytes) is list and len(terminal_bytes) <= p.BATCH_RECORDS, 'terminal_count')
                proposals = {key:dict(row) for key,row in self._proposals.items()}
                if admission is not None:
                    request_id, token, accepted, schedule = admission
                    proposal = proposals[request_id]
                    p.require(proposal['token'] is token and proposal['phase'] == 'proposed'
                              and type(accepted) is bool, 'admission')
                    if accepted:
                        proposal['admission'] = self._admission_join(schedule, proposal, proposals, config)
                        proposal['phase'] = 'admitted'
                    else:
                        p.require(schedule is None, 'rejected_admission_extension')
                        proposal['phase'] = 'not_submitted'
                p.require(value['nextReservedSequence']-1 <= sum(row['phase'] not in ('proposed','not_submitted')
                          for row in proposals.values()), 'reservation_without_local_admission')
                staged = {}; terminals = {}; next_sequence = self._ack + 1
                ticks, tracked = self._ticks, self._tracked
                for position,row in enumerate(rows):
                    raw = v2.validate_record(row, config); sequence = row['sequence']
                    p.require(sequence == value['acknowledgedThrough'] + position + 1
                              and sequence < value['nextReservedSequence'], 'batch_prefix_sequence')
                    if sequence in self._records:
                        p.require(raw == self._records[sequence]['raw'], 'conflicting_duplicate')
                        continue
                    p.require(sequence == next_sequence, 'missing_sequence'); next_sequence += 1
                    request_id = row['binding']['requestId']; proposal = proposals.get(request_id)
                    p.require(proposal is not None and proposal['phase'] == 'admitted'
                              and proposal['sequence'] is None, 'no_current_admission')
                    p.require(p.canonical(row['binding']) == proposal['binding'], 'proposal_binding')
                    p.require(not any(item['binding']['requestId'] == request_id for item in staged.values()), 'duplicate_step')
                    p.require(row['dispatchStartedTicks'] >= ticks, 'record_clock_regressed')
                    p.require(p.canonical(row['trackedBefore']) == tracked, 'client_tracked_chain')
                    self._application_join(row, proposals, staged)
                    staged[sequence] = row; ticks = row['publicationTicks']; tracked = p.canonical(row['trackedAfter'])
                if value['unpublished']:
                    staged_requests = {row['binding']['requestId'] for row in staged.values()}
                    p.require(sum(row['phase'] == 'admitted' and row['sequence'] is None and key not in staged_requests
                                  for key,row in proposals.items()) == 1, 'unpublished_without_pending_admission')
                seen_terminals = set()
                for encoded in terminal_bytes:
                    term = p.decode(encoded, 4096); raw = v2.validate_terminal(term, config)
                    request_id = term['binding']['requestId']
                    p.require(request_id not in seen_terminals, 'terminal_repeated_in_batch'); seen_terminals.add(request_id)
                    proposal = proposals.get(request_id)
                    p.require(proposal is not None and proposal['phase'] not in ('proposed','not_submitted'), 'terminal_without_admission')
                    p.require(p.canonical(term['binding']) == proposal['binding'], 'terminal_binding')
                    if request_id in self._terminals:
                        p.require(raw == self._terminals[request_id]['raw'], 'terminal_conflict')
                        continue
                    self._terminal_join(term, proposal, proposals, staged, terminals)
                    terminals[request_id] = (term, raw)
                self._legacy_join([] if legacy_receipts is None else legacy_receipts, terminals, proposals)
                # R may follow Q only after P's handoff publication, not before it.
                for row in staged.values():
                    previous = row['binding']['queueAfter']
                    if previous is None:
                        continue
                    predecessor = self._lookup(previous['applicationSequence'], staged)
                    older = predecessor['binding']['queueAfter']
                    if older is not None:
                        old_id = older['requestId']
                        old_term = terminals.get(old_id)
                        if old_term is None:
                            p.require(old_id in self._terminals, 'next_dispatch_before_handoff')
                            old_term = (p.decode(self._terminals[old_id]['raw']), self._terminals[old_id]['raw'])
                        p.require(old_term[0]['reason'] == 'horizon_handoff'
                                  and v2.same(old_term[0]['transition']['successor'], previous)
                                  and row['dispatchStartedTicks'] >= old_term[0]['publicationTicks'], 'next_dispatch_before_handoff')
                ordinary = any(term['transition'] is None for term,_ in terminals.values())
                p.require(not ordinary or value['closedForSubmission'], 'ordinary_terminal_must_close')
                # No admission, retained record, terminal, ACK or closure mutation precedes this point.
                self._proposals = proposals
                for sequence,row in staged.items():
                    proposal = proposals[row['binding']['requestId']]
                    disposition = 'validated_waiting_publication' if row['outcome'] == 'complete_returned' else 'quarantined_input_uncertainty'
                    self._records[sequence] = dict(raw=p.canonical(row), observedClientNs=observed_client_ns, disposition=disposition)
                    proposal['sequence'] = sequence; proposal['phase'] = 'application_reported'; self._ack = sequence
                    if row['outcome'] != 'complete_returned': self._poison('partial_or_unknown_application')
                for request_id,(term,raw) in terminals.items():
                    self._terminals[request_id] = dict(raw=raw, observedClientNs=observed_client_ns)
                    proposal = proposals[request_id]; proposal['terminal'] = term['status']
                    positive = (proposal['sequence'] is not None and term['status'] == 'completed'
                        and ((term['reason'] == 'horizon_handoff' and term['releaseOutcome'] == 'not_requested')
                             or (term['reason'] == 'horizon_complete' and term['releaseOutcome'] == 'returned_unverified')))
                    if not positive: self._poison('terminal_requires_quarantine')
                self._closed_for_submission |= value['closedForSubmission']
                self._authority_lost |= value['authorityLost']
                if self._authority_lost: self._poison('producer_authority_lost')
                self._tracked, self._ticks, self._observed = tracked, ticks, observed_client_ns
                self._server_ack = value['acknowledgedThrough']; self._next_reserved = value['nextReservedSequence']
                return self._ack
            except BaseException as error:
                self._poison(type(error).__name__, batch_bytes if type(batch_bytes) is bytes else b'')
                raise

    def ingest(self, batch_bytes, terminal_bytes, *, observed_client_ns):
        """Status/frame replies use the same whole-batch validator without inventing admission."""
        return self.ingest_reply(batch_bytes, terminal_bytes, observed_client_ns=observed_client_ns)

    def terminal_ready(self, request_id, token):
        """Reconciliation authority comes only from the already joined immutable terminal facts."""
        with self._lock:
            self._ready(); proposal = self._proposals[request_id]
            p.require(proposal['token'] is token and proposal['publishedGeneration'] is not None, 'terminal_native_owner')
            if request_id not in self._terminals:
                return False
            term = p.decode(self._terminals[request_id]['raw'], 4096)
            p.require(v2.validate_terminal(term, p.decode(self._config)) == self._terminals[request_id]['raw'], 'terminal_canonical')
            self._terminal_join(term, proposal, self._proposals, {}, {})
            p.require(term['status'] == 'completed' and
                ((term['reason'] == 'horizon_handoff' and term['releaseOutcome'] == 'not_requested') or
                 (term['reason'] == 'horizon_complete' and term['releaseOutcome'] == 'returned_unverified')),
                'terminal_not_reconciled')
            return True

    def _native_revision(self):
        """Tickets also bind immutable source schedules, queue links and sticky closure/loss."""
        # Frame each bounded item separately; 32 maximally escaped request IDs do
        # not create an oversized intermediate revision JSON array after input.
        header = dict(config=hashlib.sha256(self._config).hexdigest(), ack=self._ack,
            observed=self._observed, ticks=self._ticks, nextReserved=self._next_reserved,
            closedForSubmission=self._closed_for_submission, authorityLost=self._authority_lost)
        digest = hashlib.sha256(p.canonical(header, 2048))
        for name, rows in (('records', self._records), ('terminals', self._terminals)):
            for key,row in rows.items():
                digest.update(p.canonical((name, key, hashlib.sha256(row['raw']).hexdigest()), 2048))
        for key,row in self._proposals.items():
            digest.update(p.canonical(('admission', key, hashlib.sha256(row['binding']).hexdigest(),
                hashlib.sha256(row['sourceTimes']).hexdigest(),
                None if row['admission'] is None else hashlib.sha256(row['admission']).hexdigest()), 2048))
        return digest.digest()

    def submission_status(self, request, token):
        """Expose detached schedule/closure facts for the exact opaque token, even after failure."""
        with self._lock:
            row = super().submission_status(request, token)
            if row is not None:
                row.update(admission=self._proposals[request]['admission'],
                           sourceTimes=self._proposals[request]['sourceTimes'],
                           closedForSubmission=self._closed_for_submission, authorityLost=self._authority_lost)
            return row

    def snapshot(self, *, cutoff_client_ns):
        """Keep the existing 512 KiB census while retaining all v2 schedules and closure facts."""
        with self._lock:
            value = p.decode(super().snapshot(cutoff_client_ns=cutoff_client_ns), 512*1024)
            value.update(version=2, closedForSubmission=self._closed_for_submission, authorityLost=self._authority_lost,
                admissions=[dict(record=p.decode(row['admission'],2048), sourceTimes=p.decode(row['sourceTimes'],256))
                            for row in self._proposals.values() if row['admission'] is not None])
            return p.canonical(value, 512*1024)
