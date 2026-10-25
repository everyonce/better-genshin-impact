"""Unrun v2 wire/ledger/real eager-owner composition cases; no numerical or native imports."""
import copy
import hashlib
import unittest
from pathlib import Path

import step_application_protocol as p
import step_application_protocol_v2 as v2
import step_application_transport as transport
from _step_application_v2_fixtures import QueuedFixture, configuration_v2, confirmation
from step_application_test_fixtures import transaction, response
from native_history_feedback import FeedbackError

CAPACITY_OUTPUT = None
SHARED = Path(__file__).resolve().parent/'fixtures/step_application/queued_v2'


def shared(name):
    """Read only the copied, source-pinned synthetic C# wire fixture."""
    return p.decode((SHARED/name).read_bytes(), 65536)


def shared_pending_q():
    """Reach the wire-only shared P-published/Q-proposed seam; callback is explicitly inert."""
    config = shared('configuration-v2.json'); intake = transport.StepApplicationIntake(config,confirmation(config))
    wires = {}; tokens = {}
    for key in ('p','q'):
        expected = shared('request-'+key+'-v2.json'); bound = expected['stepApplication']['binding']; token = object()
        request = {name:value for name,value in expected.items() if name not in v2.EXTENSIONS}
        wire = intake.propose(request,bound['identity'],request['steps'],bound['model'],token)
        p.require(v2.same(wire,expected),'shared_request_bytes')
        wires[key] = wire; tokens[key] = token
        if key == 'p':
            batch = dict(version=2,channelId=config['channelId'],acknowledgedThrough=0,nextReservedSequence=2,
                authorityLost=False,closedForSubmission=False,unpublished=0,records=[shared('application-p-v2.json')])
            intake.receive(wire,dict(type='accepted',requestId='p',stepApplicationAdmission=shared('admission-p-v2.json'),
                stepApplications=batch,stepApplicationTerminals=[]),observed_client_ns=1)
            intake.ledger.publish(1,token,lambda *_:b'p'*32)
    return intake,wires,tokens


class V2ProtocolTests(unittest.TestCase):
    """Exact closed grammar, canonical bytes, explicit version and complete coverage checks."""
    def test_v1_round_trip_remains_ordinary(self):
        """The existing v1 configuration and reply do not enter the v2 ledger."""
        out, intake, wire, token = transaction()
        original = response(out, wire)
        intake.receive(wire, original, observed_client_ns=1)
        self.assertEqual(intake._ack, 1)
        self.assertEqual(intake.protocol.VERSION, 1)
        self.assertNotIn('queueAfter', wire)

    def test_explicit_negotiation_and_mixed_version_rejected(self):
        """A matching version alone cannot replace exact mode/configuration confirmation."""
        config = configuration_v2()
        for value in (False, 1, 3, '2'):
            changed = dict(config, version=value)
            with self.subTest(value=value), self.assertRaises(p.ProtocolError):
                transport.StepApplicationIntake(changed, confirmation(config))
        config['mode'] = p.MODE
        with self.assertRaises(p.ProtocolError):
            transport.StepApplicationIntake(config, confirmation(config))

    def test_queue_after_required_and_typed(self):
        """Null is initial authority; absence, falsy stand-ins and malformed links are not."""
        fixture = QueuedFixture(); fixture.propose()
        self.assertEqual(v2.validate_submission(fixture.request), p.canonical(fixture.request))
        missing = dict(fixture.request); del missing['queueAfter']
        with self.assertRaises(p.ProtocolError): v2.validate_submission(missing)
        for wrong in (False, 0, {}, [], '', {'requestId':'p','applicationSequence':True,'submissionSha256':'a'*64}):
            with self.subTest(wrong=wrong), self.assertRaises(p.ProtocolError):
                v2.validate_submission(dict(fixture.request, queueAfter=wrong))

    def test_queue_link_is_hashed_and_detached(self):
        """The actual canonical request digest includes the retained queue predecessor."""
        fixture = QueuedFixture(); fixture.published_p_pending_q()
        bound = fixture.wire['stepApplication']['binding']
        self.assertEqual(bound['submissionSha256'], hashlib.sha256(p.canonical(fixture.request)).hexdigest())
        changed = copy.deepcopy(fixture.wire); changed['queueAfter']['applicationSequence'] = 3
        with self.assertRaises(p.ProtocolError): v2.validate_envelope(changed)
        self.assertEqual(fixture.intake.ledger.submission_status(fixture.request['requestId'], fixture.proposal.token)['binding'],
                         p.canonical(bound))

    def test_v1_rejects_any_queue_presence(self):
        """Even null queueAfter does not silently upgrade a v1 action."""
        _, _, wire, _ = transaction()
        raw = {k:v for k,v in wire.items() if k not in transport.EXTENSIONS}
        with self.assertRaises(p.ProtocolError): transport.validate_submission(dict(raw, queueAfter=None))

    def test_original_call_coverage_still_required(self):
        """A v2 label never authorizes a missing backend call or changed tracked generation."""
        fixture = QueuedFixture(); fixture.propose(); fixture.schedule(); row = fixture.application()
        for mutate in (lambda r:r.update(calls=[]), lambda r:r['trackedAfter'].update(generation=0),
                       lambda r:r.update(backendAfter='other'), lambda r:r.update(version=1)):
            bad = copy.deepcopy(row); mutate(bad)
            with self.assertRaises(p.ProtocolError): v2.validate_record(bad, fixture.intake.config)

    def test_v2_ordinary_terminal_requires_explicit_null(self):
        """An ordinary release cannot be mislabeled as an implicit no-release handoff."""
        fixture = QueuedFixture(); fixture.propose(); fixture.schedule(); fixture.application()
        term = fixture.terminal(); del term['transition']
        with self.assertRaises(p.ProtocolError): v2.validate_terminal(term, fixture.intake.config)
        term = fixture.terminal(); term['reason'] = 'horizon_handoff'
        with self.assertRaises(p.ProtocolError): v2.validate_terminal(term, fixture.intake.config)


class V2LedgerTests(unittest.TestCase):
    """Whole-reply mutation boundary, contiguous ACK and all predecessor/terminal joins."""
    def test_conflicting_header_clock_and_null_receipts_are_atomic(self):
        """Co-present header clocks and legacy container shape cannot contradict staged admission."""
        for defect in ('clock','receipts'):
            with self.subTest(defect=defect):
                fixture=QueuedFixture(); fixture.propose(); schedule=fixture.schedule()
                response=dict(type='accepted',requestId=fixture.request['requestId'],
                    stepApplicationAdmission=schedule,stepApplications=fixture.batch(unpublished=1),
                    stepApplicationTerminals=[])
                if defect=='clock': response['acceptedAtMs']=schedule['admittedAtMs']+1.0
                else: response['receipts']=None
                fixture.reply(response)
                with self.assertRaises((p.ProtocolError,FeedbackError)):
                    fixture.coordinator.dispatch(fixture.proposal.token,current_server_ms=10.0)
                self.assertEqual(fixture.intake._ack,0)
                self.assertEqual(fixture.intake.ledger.submission_status(fixture.request['requestId'],
                    fixture.proposal.token)['phase'],'proposed')

    def test_malformed_accepted_admission_does_not_mutate_phase_or_ack(self):
        """Malformed accepted is uncertainty, never admitted or known rejection."""
        fixture = QueuedFixture(); fixture.propose()
        with self.assertRaises((p.ProtocolError, FeedbackError)):
            fixture.dispatch(applied=True, mutate=lambda r:r['stepApplicationAdmission'].update(scheduledEndMs=61.0))
        row = fixture.intake.ledger.submission_status(fixture.request['requestId'], fixture.proposal.token)
        self.assertEqual((row['phase'], row['sequence'], row['admission']), ('proposed', None, None))
        self.assertEqual((fixture.intake._ack, fixture.runtime.commits), (0, 0))
        self.assertEqual(fixture.intake.submission_disposition(fixture.request['requestId'], fixture.proposal.token).status, 'unknown')
        self.assertTrue(fixture.owner._leased)

    def test_bad_terminal_rejects_same_reply_admission_and_record(self):
        """A later validation failure cannot leave accepted admission or partial ACK behind."""
        fixture = QueuedFixture(); fixture.propose()
        def wrong(response):
            term = fixture.terminal(); term['binding'] = dict(term['binding'], requestId='foreign')
            response['stepApplicationTerminals'] = [term]
            response['stepApplications']['closedForSubmission'] = True
        with self.assertRaises((p.ProtocolError, FeedbackError)): fixture.dispatch(applied=True, mutate=wrong)
        self.assertEqual(fixture.intake.ledger._records, {})
        self.assertEqual(fixture.intake.ledger._terminals, {})
        self.assertEqual(fixture.intake.ledger._ack, 0)
        self.assertEqual(fixture.runtime.commits, 0)

    def test_missing_admission_is_not_known_rejection(self):
        """The optional field is required on accepted v2 and absent on rejected v2."""
        fixture = QueuedFixture(); fixture.propose()
        with self.assertRaises((p.ProtocolError, FeedbackError)):
            fixture.dispatch(mutate=lambda r:r.pop('stepApplicationAdmission'))
        self.assertTrue(fixture.intake.ledger.quarantined)
        self.assertEqual(fixture.runtime.restores, 0)

    def test_queue_before_history_publication_cannot_sample(self):
        """Admission/application ACK is not native history publication."""
        fixture = QueuedFixture(); fixture.propose(); fixture.dispatch(applied=False)
        with self.assertRaises(FeedbackError): fixture.coordinator.propose(object(), fixture.identity, cutoff_client_ns=3000)
        self.assertEqual(fixture.runtime.prepares, 1)

    def test_queued_admission_has_no_reserved_application(self):
        """Q remains pending while its accepted schedule is waiting for the fixed boundary."""
        fixture = QueuedFixture(); fixture.published_p_pending_q()
        row = fixture.intake.ledger.submission_status(fixture.request['requestId'], fixture.proposal.token)
        self.assertIsNone(row['sequence'])
        self.assertEqual(fixture.intake.ledger._next_reserved, 2)
        self.assertEqual((fixture.runtime.commits, fixture.runtime.restores), (1, 0))
        self.assertTrue(fixture.owner._leased)

    def test_q_software_without_p_terminal_waits(self):
        """ACK may advance to Q while history remains P and Q retains its original lease."""
        fixture = QueuedFixture(); fixture.published_p_pending_q(); fixture.application()
        self.assertIsNone(fixture.status())
        self.assertEqual((fixture.intake._ack, fixture.runtime.commits, fixture.adapter.steps_seen), (2, 1, 1))
        self.assertTrue(fixture.owner._leased)

    def test_handoff_missing_q_evidence_rejects_whole_batch(self):
        """A terminal cannot substitute a link or server ACK for absent retained Q software facts."""
        fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q(); successor = fixture.application()
        term = fixture.handoff(predecessor, successor)
        with self.assertRaises(p.ProtocolError):
            fixture.status(terms=[term], mutate=lambda r:r['stepApplications'].update(records=[], nextReservedSequence=2))
        self.assertNotIn(predecessor['binding']['requestId'], fixture.intake.ledger._terminals)
        self.assertEqual(fixture.runtime.commits, 1)

    def test_handoff_can_join_already_acked_q_without_cycle(self):
        """Q's retained software row suffices after ACK; Q history has not yet been published."""
        fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q(); successor = fixture.application()
        fixture.status()
        self.assertEqual(fixture.runtime.commits, 1)
        result = fixture.status(terms=[fixture.handoff(predecessor, successor)])
        self.assertIsNotNone(result)
        self.assertEqual((fixture.runtime.commits, fixture.runtime.restores, fixture.adapter.steps_seen), (2, 0, 2))

    def test_typed_duplicate_is_conflict(self):
        """Equal-looking Boolean integers cannot be treated as duplicate evidence."""
        fixture = QueuedFixture(); fixture.propose(); fixture.dispatch(applied=True)
        batch = fixture.batch(ack=0); batch['records'] = copy.deepcopy(batch['records'])
        batch['records'][0]['binding']['stepIndex'] = False
        with self.assertRaises(p.ProtocolError):
            fixture.intake.ledger.ingest(p.canonical(batch), [], observed_client_ns=3000)
        self.assertEqual(fixture.runtime.commits, 1)

    def test_exact_duplicate_does_not_publish_twice(self):
        """Valid retransmission is ACKable but never another native callback."""
        fixture = QueuedFixture(); fixture.propose(); fixture.dispatch(applied=True)
        for _ in range(2):
            fixture.intake.ledger.ingest(p.canonical(fixture.batch(ack=0)), [], observed_client_ns=3000)
        self.assertEqual((fixture.runtime.commits, fixture.intake.ledger._ack), (1, 1))

    def test_zero_and_unpublished_prefix_boundaries(self):
        """No record may disappear behind an altered finished/reserved census."""
        fixture = QueuedFixture()
        fixture.intake.ledger.ingest(p.canonical(fixture.batch()), [], observed_client_ns=0)
        fixture.propose(); schedule = fixture.schedule()
        response = dict(type='accepted', requestId=fixture.request['requestId'], stepApplicationAdmission=schedule,
                        stepApplications=fixture.batch(unpublished=1), stepApplicationTerminals=[])
        fixture.intake.receive(fixture.wire, response, observed_client_ns=3000)
        bad = fixture.batch(unpublished=0); bad['nextReservedSequence'] = 2
        with self.assertRaises(p.ProtocolError): fixture.intake.ledger.ingest(p.canonical(bad), [], observed_client_ns=3000)

    def test_truncated_first_window_is_rejected(self):
        """A reported completed prefix cannot silently lose a tail row."""
        fixture = QueuedFixture(); fixture.propose(); fixture.schedule(); fixture.application()
        response = dict(type='accepted', requestId=fixture.request['requestId'],
            stepApplicationAdmission=fixture.admissions[fixture.request['requestId']],
            stepApplications=fixture.batch(), stepApplicationTerminals=[])
        response['stepApplications']['records'] = []
        with self.assertRaises(p.ProtocolError): fixture.intake.receive(fixture.wire,response,observed_client_ns=3000)
        self.assertEqual(fixture.intake.ledger._ack, 0)

    def test_bad_handoff_variants_preserve_q_and_do_not_commit(self):
        """Typed links, fixed boundary, actual Q return and release kind are independent joins."""
        mutations = [lambda t:t['transition']['successor'].update(applicationSequence=1),
            lambda t:t['transition'].update(boundaryMs=61.0),
            lambda t:t['transition'].update(successorScheduledEndMs=111.0),
            lambda t:t['transition'].update(successorCallsReturnedTicks=99999),
            lambda t:t.update(releaseOutcome='returned_unverified'),
            lambda t:t.update(publicationTicks=1000)]
        for mutate in mutations:
            fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q(); successor = fixture.application()
            term = fixture.handoff(predecessor, successor); mutate(term)
            with self.subTest(mutate=mutate), self.assertRaises(p.ProtocolError): fixture.status(terms=[term])
            self.assertEqual(fixture.runtime.commits, 1)
            self.assertTrue(fixture.owner._leased)

    def test_terminal_conflict_quarantines_after_publication(self):
        """A late contradiction never rewinds an already published native history."""
        fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q(); successor = fixture.application()
        term = fixture.handoff(predecessor, successor); fixture.status(terms=[term])
        bad = copy.deepcopy(term); bad['legacyEndedAtMs'] += 1.0
        with self.assertRaises(p.ProtocolError): fixture.status(terms=[bad])
        self.assertEqual((fixture.runtime.commits, fixture.runtime.restores), (2, 0))
        self.assertTrue(fixture.intake.ledger.quarantined)

    def test_completion_cannot_cross_still_active_p_expiry(self):
        """P's first-start deadline is consumed, but its expiry remains authoritative through Q completion."""
        fixture = QueuedFixture(); fixture.propose(start_before=70.0,expires=80.0)
        fixture.dispatch(applied=True); predecessor = fixture.rows[0]
        fixture.identity['frameId'] = 2; fixture.propose(observed=20.0)
        fixture.dispatch(admitted=30.0); successor = fixture.application()
        term = fixture.handoff(predecessor,successor)
        term.update(legacyEndedAtMs=80.0,publicationTicks=1081)
        with self.assertRaises(p.ProtocolError): fixture.status(terms=[term])
        self.assertEqual(fixture.intake._ack,1)
        self.assertEqual(fixture.runtime.commits,1)

    def test_closed_final_application_can_publish_and_reconcile(self):
        """Closed with known complete evidence is not uncertainty; it forbids only new submissions."""
        fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q(); successor = fixture.application()
        fixture.status(terms=[fixture.handoff(predecessor, successor), fixture.terminal(successor)], closed=True)
        self.assertEqual(fixture.adapter.steps_seen, 2)
        self.assertIsNone(fixture.owner._unresolved)
        self.assertFalse(fixture.intake.ledger.quarantined)
        self.assertFalse(fixture.intake.ledger.proposal_capacity())
        self.assertFalse(fixture.owner._leased)

    def test_closed_flag_never_reopens_from_old_open_batch(self):
        """A repeated open flag cannot grant a new proposal after sticky closure."""
        fixture = QueuedFixture(); fixture.propose(); fixture.dispatch(applied=True)
        fixture.status(terms=[fixture.terminal()], closed=True)
        fixture.intake.ledger.ingest(p.canonical(fixture.batch(closed=False)), [], observed_client_ns=3000)
        self.assertTrue(fixture.intake.ledger._closed_for_submission)
        self.assertFalse(fixture.intake.ledger.proposal_capacity())

    def test_admitted_undispatched_cancellation_is_not_rollback(self):
        """Accepted Q without application is retained uncertainty, never known-not-submitted."""
        fixture = QueuedFixture(); fixture.published_p_pending_q()
        term = dict(version=2, channelId='channel', binding=fixture.wire['stepApplication']['binding'],
            applicationSequences=[], status='cancelled', reason='stop', publicationTicks=1060,
            legacyEndedAtMs=60.0, releaseOutcome='returned_unverified', transition=None)
        with self.assertRaises((p.ProtocolError, FeedbackError)): fixture.status(terms=[term], closed=True)
        self.assertEqual((fixture.runtime.commits, fixture.runtime.restores), (1, 0))
        self.assertTrue(fixture.owner._leased)


    def test_co_present_legacy_handoff_and_final_match(self):
        """Legacy joins are checked when present; later drained-row retransmission remains valid."""
        fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q()
        successor = fixture.application(); handoff = fixture.handoff(predecessor, successor)
        fixture.status(terms=[handoff], mutate=lambda reply: reply.update(receipts=[fixture.legacy(handoff)]))
        fixture.status(terms=[handoff])
        final = fixture.terminal(successor)
        fixture.status(terms=[final], closed=True, mutate=lambda reply: reply.update(receipts=[fixture.legacy(final)]))
        self.assertEqual(fixture.runtime.commits, 2)
        self.assertFalse(fixture.intake.ledger.quarantined)

    def test_four_record_window_defers_fifth_without_inventing_tail(self):
        """A full duplicate prefix may hide Q; advancing ACK exposes its real row and P terminal."""
        fixture = QueuedFixture()
        def old_ack(reply):
            """Model a server which has not yet processed the transmitted ACK, never a regressed ACK."""
            reply['stepApplications'] = fixture.batch(ack=0)
        for index in range(4):
            fixture.identity['frameId'] = index+1
            observed = 0.0 if index == 0 else 20.0+50*(index-1)
            fixture.propose(observed=observed)
            if index == 0: fixture.dispatch(applied=True, mutate=old_ack)
            else:
                fixture.dispatch(admitted=observed+10, mutate=old_ack)
                predecessor = fixture.rows[-1]; successor = fixture.application()
                fixture.status(terms=[fixture.handoff(predecessor, successor)], mutate=old_ack)
        fixture.identity['frameId'] = 5; fixture.propose(observed=170.0)
        fixture.dispatch(admitted=180.0, mutate=old_ack)
        predecessor = fixture.rows[-1]; successor = fixture.application()
        fixture.status(mutate=old_ack)
        self.assertEqual((fixture.intake._ack, fixture.runtime.commits), (4, 4))
        fixture.status(terms=[fixture.handoff(predecessor, successor)])
        self.assertEqual((fixture.intake._ack, fixture.runtime.commits), (5, 5))

    def test_delayed_reply_finalizes_whole_chain_in_order(self):
        """Q application plus P handoff and Q final release can settle without a third proposal."""
        fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q(); successor = fixture.application()
        fixture.status(terms=[fixture.handoff(predecessor, successor),fixture.terminal(successor)], closed=True)
        self.assertEqual((fixture.runtime.prepares,fixture.runtime.commits), (2,2))
        self.assertIsNone(fixture.owner._unresolved)
        self.assertFalse(fixture.owner._leased)
        self.assertFalse(fixture.intake.ledger.proposal_capacity())

    def test_legacy_contradictions_veto_entire_staged_reply(self):
        """Wrong reason, typed index, operands, identity or original clocks cannot advance Q ACK."""
        changes = (
            lambda row: row.update(reason='horizon_complete'),
            lambda row: row.update(frameId=True),
            lambda row: row.update(acceptedAtMs=999.0),
            lambda row: row.update(endedAtMs=999.0),
            lambda row: row['appliedSteps'][0].update(index=False),
            lambda row: row['appliedSteps'][0].update(mouseDx=1),
        )
        for change in changes:
            fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q()
            successor = fixture.application(); handoff = fixture.handoff(predecessor, successor)
            row = fixture.legacy(handoff); change(row)
            pending_before = fixture.owner._pending
            self.assertIsNotNone(pending_before)
            with self.subTest(change=change), self.assertRaises(p.ProtocolError):
                fixture.status(terms=[handoff], mutate=lambda reply: reply.update(receipts=[row]))
            self.assertEqual(fixture.intake._ack, 1)
            self.assertEqual(fixture.runtime.commits, 1)
            self.assertTrue(fixture.intake.ledger.quarantined)
            self.assertIs(fixture.owner._pending,pending_before)


class V2OwnerTests(unittest.TestCase):
    """The actual unchanged prepare/commit bodies remain controlled by original token and RNG ownership."""
    def test_handoff_reconciles_p_under_pending_q_rng(self):
        """No P RNG restoration or extra sampler/decoder call may occur at the no-cycle boundary."""
        fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q()
        pending_rng = fixture.runtime.rng; pending = fixture.owner._prepared
        successor = fixture.application(); fixture.status(terms=[fixture.handoff(predecessor, successor)])
        self.assertEqual(fixture.runtime.rng, pending_rng)
        self.assertEqual((fixture.runtime.prepares, fixture.runtime.commits, fixture.runtime.restores), (2, 2, 0))
        self.assertIs(fixture.owner._unresolved['prepared'], pending)

    def test_consumed_p_start_deadline_is_not_rechecked(self):
        """P's old start cutoff cannot invalidate a healthy later fixed-boundary handoff."""
        fixture = QueuedFixture(); fixture.propose(start_before=20.0); fixture.dispatch(applied=True)
        predecessor = fixture.rows[0]; fixture.identity['frameId'] = 2
        fixture.propose(observed=20.0); fixture.dispatch(admitted=30.0); successor = fixture.application()
        fixture.status(terms=[fixture.handoff(predecessor, successor)])
        self.assertEqual(fixture.runtime.commits, 2)

    def test_q_rng_mutation_poison_retains_owner(self):
        """A Q software receipt cannot replace the pending Q numerical checkpoint."""
        fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q(); successor = fixture.application()
        fixture.runtime.rng = (999, 999)
        with self.assertRaises(FeedbackError): fixture.status(terms=[fixture.handoff(predecessor, successor)])
        self.assertEqual(fixture.runtime.commits, 1)
        self.assertTrue(fixture.owner._leased)
        self.assertIsNotNone(fixture.owner._prepared)

    def test_commit_failure_retains_partial_owners_and_no_retry(self):
        """Failure after the actual second pass retains the pending owner and exact returned resources."""
        fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q(); successor = fixture.application()
        fixture.runtime.malformed_return = True
        with self.assertRaises(FeedbackError): fixture.status(terms=[fixture.handoff(predecessor, successor)])
        self.assertEqual(fixture.runtime.commits, 2)
        self.assertIsNotNone(fixture.owner._publication['returned'])
        self.assertTrue(fixture.owner._leased)
        self.assertTrue(fixture.intake.ledger.quarantined)

    def test_ticket_revision_binds_schedule_and_closed_flag(self):
        """Changes during commit poison the operation before final history publication can complete."""
        fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q(); successor = fixture.application()
        fixture.runtime.commit_hook = lambda:setattr(fixture.intake.ledger, '_closed_for_submission', True)
        with self.assertRaises(FeedbackError): fixture.status(terms=[fixture.handoff(predecessor, successor)])
        self.assertEqual(fixture.runtime.commits, 2)
        self.assertTrue(fixture.owner._leased)
        self.assertIsNotNone(fixture.owner._publication['returned'])

    def test_original_deadlines_and_compute_gate_still_cancel_only_unwritten(self):
        """The coordinator retains strict 50 ms proposal and 100 ms source-start boundaries."""
        fixture = QueuedFixture(); fixture.propose()
        fixture.coordinator._pending['proposalWallNs'] = 50_000_000
        result = fixture.coordinator.dispatch(fixture.proposal.token, current_server_ms=10.0)
        self.assertFalse(result.committed)
        self.assertEqual((fixture.runtime.restores, len(fixture.bridge.handle.sent)), (1, 0))

    def test_known_rejected_q_restores_only_q_and_keeps_p(self):
        """An entirely valid rejected reply retains P while rolling back Q's original checkpoint once."""
        fixture = QueuedFixture(); fixture.propose(); fixture.dispatch(applied=True)
        predecessor = fixture.owner._unresolved
        fixture.identity['frameId'] = 2; fixture.propose(observed=20.0)
        fixture.reply(dict(type='rejected',requestId=fixture.request['requestId'],
                           stepApplications=fixture.batch(),stepApplicationTerminals=[]))
        result = fixture.coordinator.dispatch(fixture.proposal.token,current_server_ms=30.0)
        self.assertFalse(result.committed)
        self.assertEqual((fixture.runtime.commits,fixture.runtime.restores), (1,1))
        self.assertIs(fixture.owner._unresolved,predecessor)
        self.assertIsNone(fixture.owner._pending)

    def test_no_third_proposal_while_q_is_pending(self):
        """An admitted Q occupies the only native pending slot even before its software application."""
        fixture = QueuedFixture(); fixture.published_p_pending_q()
        fixture.identity['frameId'] = 3
        with self.assertRaises(FeedbackError): fixture.propose(observed=70.0)
        self.assertEqual(fixture.runtime.prepares,2)

    def test_foreign_connection_or_fixed_epoch_does_not_sample_again(self):
        """No new channel, backend or decision identity adopts the existing committed history."""
        fixture = QueuedFixture(); fixture.propose(); fixture.dispatch(applied=True)
        fixture.identity['controlEpoch'] += 1
        with self.assertRaises(FeedbackError): fixture.propose(observed=20.0)
        self.assertEqual(fixture.runtime.prepares, 1)

    def test_all_installation_barriers_still_closed(self):
        """Neither negotiated bytes nor an inert composition opens a production activation path."""
        fixture = QueuedFixture()
        self.assertFalse(transport.AVAILABLE)
        with self.assertRaises(p.ProtocolError): fixture.intake.install(fixture.bridge)
        with self.assertRaises(FeedbackError): fixture.coordinator.install()

    def test_publication_callback_has_no_ledger_or_bridge_lock(self):
        """The real second pass cannot run inside either transport or ledger critical section."""
        fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q(); successor = fixture.application()
        observed = []
        def check():
            """Observe only lock ownership at the existing fake runtime commit seam."""
            observed.append((fixture.bridge.lock.locked(), fixture.intake.ledger._lock._is_owned()))
        fixture.runtime.commit_hook = check
        fixture.status(terms=[fixture.handoff(predecessor, successor)])
        self.assertEqual(observed, [(False, False)])

    def test_successor_of_q_requires_earlier_handoff_clock(self):
        """R dispatch before P's handoff publication is rejected although Q software already exists."""
        fixture = QueuedFixture(); predecessor = fixture.published_p_pending_q(); successor = fixture.application()
        term = fixture.handoff(predecessor, successor)
        # A delayed publication is still before Q's end but later than forged R dispatch.
        term['publicationTicks'] = 1109
        fixture.status(terms=[term])
        fixture.identity['frameId'] = 3; fixture.propose(observed=70.0); fixture.dispatch(admitted=80.0)
        later = fixture.application(); later['dispatchStartedTicks'] = 1108
        for call in later['calls']:
            call['startedTicks'] = max(call['startedTicks'], 1108)
        with self.assertRaises(p.ProtocolError): fixture.status()
        self.assertEqual(fixture.runtime.commits, 2)


class V2SharedWireTests(unittest.TestCase):
    """Exact synthetic producer-shaped bytes cross the Python wire validator; no C# execution claim."""
    def test_shared_handoff_admission_and_no_cycle(self):
        """Q software plus P terminal is valid before the inert Q publication callback runs."""
        intake,wires,tokens = shared_pending_q()
        intake.receive(wires['q'],shared('reply-handoff-v2.json'),observed_client_ns=2)
        self.assertEqual(intake._ack,2)
        self.assertIsNone(intake.ledger.submission_status('q',tokens['q'])['publishedGeneration'])
        self.assertTrue(intake.ledger.terminal_ready('p',tokens['p']))
        self.assertEqual(intake.ledger.publish(2,tokens['q'],lambda *_:b'q'*32),2)

    def test_shared_delayed_final_reply_closes_without_losing_final_publication(self):
        """A later frame joins both terminals after Q's earlier original queued admission."""
        intake,wires,tokens = shared_pending_q()
        handoff = shared('reply-handoff-v2.json')
        pending = copy.deepcopy(handoff)
        pending['receipts'] = []; pending['stepApplicationTerminals'] = []
        pending['stepApplications']['records'] = [shared('application-p-v2.json')]
        pending['stepApplications']['nextReservedSequence'] = 2
        intake.receive(wires['q'],pending,observed_client_ns=2)
        intake.receive({'command':'frame'},shared('reply-delayed-final-v2.json'),observed_client_ns=3)
        self.assertFalse(intake.ledger.quarantined)
        self.assertTrue(intake.ledger.closed_for_submission)
        self.assertEqual(intake.ledger.publish(2,tokens['q'],lambda *_:b'q'*32),2)
        self.assertTrue(intake.ledger.terminal_ready('q',tokens['q']))
        self.assertFalse(intake.ledger.proposal_capacity())

    def test_shared_legacy_contradiction_prevents_admission_and_ack(self):
        """The preserved same-request legacy reason conflict rejects the entire accepted Q reply."""
        intake,wires,tokens = shared_pending_q()
        with self.assertRaises(p.ProtocolError):
            intake.receive(wires['q'],shared('negative-legacy-contradiction-v2.json'),observed_client_ns=2)
        self.assertEqual(intake._ack,1)
        self.assertEqual(intake.ledger.submission_status('q',tokens['q'])['phase'],'proposed')
        self.assertTrue(intake.ledger.quarantined)


class V2CapacityTests(unittest.TestCase):
    """Complete retained serialized evidence is generated only under the owned inert attempt."""
    def test_shared_reservation_threshold_uses_admissible_scalars(self):
        """Actual queue requests meet grammar while unchanged reservation size reaches 8192/8193."""
        config=shared('reservation-configuration-v2.json'); v2.configuration(config)
        for predecessor_name,successor_name,witness_name,expected in (
                ('reservation-request-p-v2.json','reservation-request-q-v2.json','record-reservation-admitted-v2.json',8192),
                ('reservation-request-overflow-p-v2.json','reservation-request-overflow-v2.json','record-reservation-rejected-v2.json',8193)):
            predecessor=shared(predecessor_name); successor=shared(successor_name)
            v2.validate_envelope(predecessor); v2.validate_envelope(successor)
            bound=successor['stepApplication']['binding']; v2.binding(bound,config)
            self.assertEqual(bound['queueAfter']['submissionSha256'],predecessor['stepApplication']['binding']['submissionSha256'])
            # This fixture must satisfy the producer's separate admission budget too.
            kind = 'admitted' if expected == 8192 else 'overflow'
            for key,wire,state,admitted,start,size in (
                    ('p',predecessor,'active',130.0,130.0,445 if expected == 8192 else 446),
                    ('q',successor,'queued',140.0,180.0,951 if expected == 8192 else 952)):
                name = 'reservation-admission-'+kind+'-'+key+'-v2.json'
                actual = shared(name)
                expected_admission = dict(version=2,channelId=config['channelId'],requestId=wire['requestId'],
                    state=state,queueAfter=wire['queueAfter'],admittedAtMs=admitted,
                    scheduledStartMs=start,scheduledEndMs=start+50.0)
                self.assertTrue(v2.same(actual,expected_admission))
                raw = v2.admission(actual,config,wire['stepApplication']['binding'])
                self.assertEqual(raw,p.canonical(actual,1024))
                self.assertEqual(raw,(SHARED/name).read_bytes())
                self.assertEqual(len(raw),size)
            before=dict(keys=predecessor['steps'][0]['keys'],generation=1,complete=True)
            self.assertEqual(v2.reservation_byte_bound(bound,config,before,32),expected)
            row=shared(witness_name); self.assertEqual(len(p.canonical(row,65536)),expected)
            if expected==8192: self.assertEqual(len(p.canonical(row,p.RECORD_BYTES)),expected)
            else:
                with self.assertRaises(p.ProtocolError): p.canonical(row,p.RECORD_BYTES)

    def test_complete_32_slot_capacity_and_four_plus_four_reply(self):
        """Retain injected evidence or scope standalone evidence through every assertion."""
        from _step_application_v2_capacity import construct

        def check(output):
            """Validate all generated files while the caller still owns their directory."""
            result = construct(output)
            self.assertEqual((result['actualAttempts'], result['actualApplications'], result['actualTerminals']), (32,32,32))
            for row in result['files']:
                raw = (Path(output)/row['name']).read_bytes()
                self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (row['bytes'], row['sha256']))
                self.assertLessEqual(len(raw), row['cap'])
            self.assertLessEqual(result['combinedConservativeBytes'], 4*1024*1024)

        if CAPACITY_OUTPUT is not None:
            check(CAPACITY_OUTPUT)
        else:
            import tempfile
            # construct requires an absent child; the context owns cleanup on every exit.
            with tempfile.TemporaryDirectory() as temporary:
                check(Path(temporary)/'capacity')


if __name__ == '__main__':
    unittest.main()
