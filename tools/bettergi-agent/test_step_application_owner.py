"""Focused inert publication, exact disposition and retained-owner boundary regressions."""
import copy
import dataclasses
import unittest

from _step_application_owner_fixtures import Fixture
from native_history_feedback import FeedbackError, ProposalToken
from step_application_history_owner import ApplicationSettlement, StepApplicationHistoryOwner
from step_application_native_binding import StepApplicationNativeBinding
import step_application_protocol as p


class OwnerCases(unittest.TestCase):
    """Each case owns a fresh fake runtime; no native/numerical module or live input exists."""
    def poisoned(self, f):
        self.assertEqual(f.owner.status['phase'], 'poisoned')
        self.assertTrue(f.intake.ledger.quarantined)
        self.assertIsNotNone(f.owner._snapshot)

    def test_success_one_claim_prepare_commit_and_bytes32(self):
        f=Fixture();old=f.adapter.state;f.propose()
        self.assertEqual((f.runtime.claims,f.runtime.prepares,f.runtime.commits),(1,1,0))
        self.assertIs(f.adapter.state,old)
        result=f.dispatch()
        self.assertIs(type(result),ApplicationSettlement);self.assertIs(type(result.digest),bytes)
        self.assertEqual(len(result.digest),32)
        self.assertEqual((f.runtime.claims,f.runtime.prepares,f.runtime.commits,f.runtime.releases),(1,1,1,1))
        self.assertEqual(f.adapter.steps_seen,1);self.assertIs(f.adapter.state,f.runtime.last_returned[1])
        self.assertEqual(f.runtime.rng,(18,31));self.assertIsNone(f.owner._unresolved)
        self.assertFalse(result.physical_hold_or_release_proven or result.game_effect_proven or result.horizon_completion_proven)

    def test_acceptance_and_ack_do_not_publish(self):
        f=Fixture();f.propose();old=f.adapter.state
        self.assertIsNone(f.dispatch(f.response(applied=False)))
        self.assertEqual(f.runtime.commits,0);self.assertIs(f.adapter.state,old)
        self.assertTrue(f.owner._leased);self.assertTrue(f.owner._accepted)

    def test_callback_keeps_lease_and_no_transport_lock(self):
        f=Fixture();f.propose()
        def check():
            self.assertTrue(f.owner._leased);self.assertFalse(f.bridge.lock.locked())
            self.assertFalse(f.intake.ledger._lock._is_owned())
            self.assertTrue(f.intake.ledger._publishing)
            self.assertEqual(f.runtime.releases,0)
        f.runtime.commit_hook=check;f.dispatch()

    def test_local_unbound_rollback_same_references_rng(self):
        f=Fixture();old=f.adapter.state;rng=f.runtime.rng;f.propose(bind=False)
        result=f.coordinator.not_submitted(f.proposal.token)
        self.assertFalse(result.committed);self.assertIs(f.adapter.state,old);self.assertEqual(f.runtime.rng,rng)
        self.assertEqual(f.runtime.restores,1);self.assertEqual(f.runtime.commits,0);self.assertEqual(f.bridge.handle.sent,b'')

    def test_local_bound_rollback_and_exact_retry(self):
        f=Fixture();f.propose();result=f.proposal.result;req=f.request['requestId']
        f.coordinator.not_submitted(f.proposal.token);f.propose()
        self.assertEqual(f.proposal.result,result);self.assertNotEqual(f.request['requestId'],req)
        self.assertEqual(f.runtime.rng,(18,31));self.assertEqual(f.runtime.prepares,2)

    def test_known_rejected_whole_reply_rolls_back(self):
        f=Fixture();old=f.adapter.state;f.propose();result=f.dispatch(f.response(applied=False,kind='rejected'))
        self.assertFalse(result.committed);self.assertIs(f.adapter.state,old);self.assertEqual(f.runtime.rng,(17,29))
        self.assertEqual(f.runtime.commits,0);self.assertFalse(f.owner._leased)

    def test_intake_failure_before_registration_is_unwritten(self):
        f=Fixture();f.propose(bind=False)
        def fail(*args):raise ValueError('construction')
        f.intake.propose=fail
        with self.assertRaisesRegex(ValueError,'construction'):f.coordinator.bind(f.proposal.token,f.request)
        self.assertEqual(f.owner.status['phase'],'ready');self.assertEqual(f.runtime.rng,(17,29))
        self.assertEqual(f.bridge.handle.sent,b'');self.assertIsNone(f.coordinator._pending)

    def test_intake_failure_after_registration_is_unwritten(self):
        f=Fixture();f.propose(bind=False);original=f.intake.propose
        def fail(*args):original(*args);raise ValueError('after_registration')
        f.intake.propose=fail
        with self.assertRaisesRegex(ValueError,'after_registration'):f.coordinator.bind(f.proposal.token,f.request)
        self.assertEqual(f.owner.status['phase'],'ready');self.assertEqual(f.runtime.restores,1)
        self.assertEqual(f.intake.ledger.submission_status(f.request['requestId'],f.proposal.token)['phase'],'not_submitted')

    def test_actual_bridge_prewrite_serialization_failure(self):
        f=Fixture();f.propose();original=f.intake.prepare
        def malformed(request):
            value=original(request);value['bad']=object();return value
        f.intake.prepare=malformed
        with self.assertRaises(TypeError):f.coordinator.dispatch(f.proposal.token,current_server_ms=20.)
        self.assertEqual(f.owner.status['phase'],'ready');self.assertEqual(f.bridge.handle.sent,b'')
        self.assertEqual(f.runtime.restores,1)

    def test_partial_write_never_rolls_back(self):
        f=Fixture();f.propose();f.bridge.handle.fail_write=True
        with self.assertRaises(FeedbackError):f.coordinator.dispatch(f.proposal.token,current_server_ms=20.)
        self.poisoned(f);self.assertEqual(len(f.bridge.handle.sent),2)
        self.assertEqual(f.runtime.restores,0);self.assertTrue(f.owner._leased)

    def test_lost_ack_never_replays(self):
        f=Fixture();f.propose();f.reply({},raw=b'')
        with self.assertRaises(FeedbackError):f.coordinator.dispatch(f.proposal.token,current_server_ms=20.)
        self.poisoned(f);sent=bytes(f.bridge.handle.sent)
        with self.assertRaises(FeedbackError):f.coordinator.dispatch(f.proposal.token,current_server_ms=20.)
        self.assertEqual(bytes(f.bridge.handle.sent),sent);self.assertEqual(f.runtime.commits,0)

    def test_wrong_request_id_raw_acceptance_unknown(self):
        f=Fixture();f.propose();reply=f.response();reply['requestId']='different'
        with self.assertRaises(FeedbackError):f.dispatch(reply)
        self.poisoned(f);self.assertEqual(f.runtime.commits,0)

    def test_rejected_reply_with_bad_batch_cannot_roll_back(self):
        f=Fixture();f.propose();reply=f.response(applied=False,kind='rejected')
        reply['stepApplications']['unknown']=True
        with self.assertRaises(FeedbackError):f.dispatch(reply)
        self.poisoned(f);self.assertEqual(f.runtime.restores,0)

    def test_bad_second_record_prevents_first_commit(self):
        f=Fixture();f.propose();reply=f.response(terminal=False)
        bad=copy.deepcopy(reply['stepApplications']['records'][0]);bad['sequence']=2;bad['bad']=True
        reply['stepApplications']['records'].append(bad);reply['stepApplications']['nextReservedSequence']=3
        with self.assertRaises(FeedbackError):f.dispatch(reply)
        self.poisoned(f);self.assertEqual(f.runtime.commits,0);self.assertEqual(f.intake.ledger._records,{})

    def test_malformed_commit_return_retained_before_unpack(self):
        f=Fixture();f.propose();f.runtime.malformed_return=True
        with self.assertRaises(FeedbackError):f.dispatch()
        self.poisoned(f);self.assertIs(f.owner._publication['returned'][0],f.runtime.last_returned[0])
        self.assertFalse(f.owner._publication['assigned']);self.assertTrue(f.owner._leased)

    def test_commit_return_retained_before_rng_validation(self):
        f=Fixture();old=f.adapter.state;f.propose()
        f.runtime.commit_hook=lambda:setattr(f.runtime,'rng',(99,99))
        with self.assertRaises(FeedbackError):f.dispatch()
        self.poisoned(f);self.assertIs(f.owner._publication['returned'],f.runtime.last_returned)
        self.assertIs(f.adapter.state,old);self.assertFalse(f.owner._publication['assigned'])

    def test_commit_assignment_then_validation_failure_retains_both(self):
        f=Fixture();old=f.adapter.state;f.propose()
        def fail():raise ValueError('history_validation')
        f.runtime.validate_hook=fail
        with self.assertRaises(FeedbackError):f.dispatch()
        self.poisoned(f);self.assertIs(f.owner._snapshot['state'],old)
        self.assertIs(f.adapter.state,f.runtime.last_returned[1]);self.assertTrue(f.owner._publication['assigned'])

    def test_post_commit_sync_failure_retains_return(self):
        f=Fixture();f.propose()
        def fail():raise ValueError('synchronize')
        f.runtime.sync_hook=fail
        with self.assertRaises(FeedbackError):f.dispatch()
        self.poisoned(f);self.assertIs(f.owner._publication['returned'],f.runtime.last_returned)
        self.assertEqual(f.runtime.releases,0)

    def test_ledger_uncertainty_after_callback_no_release(self):
        f=Fixture();f.propose();original=f.owner.stage_application
        def changed(*args):
            result=original(*args);self.assertEqual(f.owner.status['phase'],'publication_pending')
            f.intake.ledger.uncertain('after_callback');return result
        f.owner.stage_application=changed
        with self.assertRaises(FeedbackError):f.dispatch()
        self.poisoned(f);self.assertEqual(f.runtime.commits,1);self.assertEqual(f.runtime.releases,0)
        self.assertEqual(f.intake.ledger._records[1]['disposition'],'publication_unknown')

    def test_finalization_failure_preserves_published_ledger(self):
        f=Fixture();f.propose();original=f.intake.ledger.publish
        def changed(*args):
            result=original(*args);f.runtime.model_revision=1;return result
        f.intake.ledger.publish=changed
        with self.assertRaises(FeedbackError):f.dispatch()
        self.poisoned(f);self.assertEqual(f.coordinator._pending['ledgerGeneration'],1)
        self.assertEqual(f.intake.ledger._records[1]['disposition'],'published')
        self.assertTrue(f.owner._leased);self.assertIs(f.owner._publication['returned'],f.runtime.last_returned)

    def test_post_release_rng_drift_quarantines(self):
        f=Fixture();f.propose();f.runtime.release_hook=lambda:setattr(f.runtime,'rng',(900,901))
        with self.assertRaises(FeedbackError):f.dispatch()
        self.poisoned(f);self.assertFalse(f.owner._leased);self.assertIsNotNone(f.owner._publication)
        self.assertIsNotNone(f.owner._unresolved);self.assertEqual(f.runtime.releases,1)

    def test_next_claim_rng_drift_blocks_prepare(self):
        f=Fixture();f.propose();f.dispatch();f.runtime.rng=(999,999);f.identity['frameId']=2
        with self.assertRaises(FeedbackError):f.propose()
        self.assertEqual(f.owner.status['phase'],'poisoned');self.assertEqual(f.runtime.claims,2)
        self.assertEqual(f.runtime.prepares,1);self.assertTrue(f.owner._leased)

    def test_reentrant_publication_never_calls_commit_twice(self):
        f=Fixture();f.propose()
        def reenter():
            try:f.coordinator.pump(f.proposal.token,current_identity=f.identity)
            except FeedbackError:pass
        f.runtime.commit_hook=reenter
        with self.assertRaises(FeedbackError):f.dispatch()
        self.poisoned(f);self.assertEqual(f.runtime.commits,1);self.assertEqual(f.runtime.releases,0)

    def test_duplicate_result_not_exposed_twice(self):
        f=Fixture();f.propose();token=f.proposal.token;f.dispatch()
        self.assertIsNone(f.coordinator.pump(token,current_identity=f.identity))
        self.assertEqual((f.runtime.commits,f.runtime.releases),(1,1))

    def test_one_unreconciled_and_successor_waits_for_terminal(self):
        f=Fixture();f.propose();f.dispatch(f.response(terminal=False));first=copy.deepcopy(f.last_row)
        retained=f.owner._unresolved;f.identity['frameId']=2;f.propose();f.dispatch(f.response(terminal=False))
        self.assertEqual(f.runtime.commits,1);self.assertIs(f.owner._unresolved,retained);self.assertTrue(f.owner._leased)
        with self.assertRaises(FeedbackError):f.propose()
        result=f.status(terminals=[f.terminal(first)])
        self.assertIs(type(result),ApplicationSettlement);self.assertEqual(f.runtime.commits,2)
        self.assertEqual(f.adapter.steps_seen,2);self.assertIsNot(f.owner._unresolved,retained)

    def test_whole_batch_prior_terminal_and_successor_application(self):
        f=Fixture();f.propose();f.dispatch(f.response(terminal=False));first=copy.deepcopy(f.last_row)
        f.identity['frameId']=2;f.propose();reply=f.response(terminal=False)
        reply['stepApplicationTerminals']=[f.terminal(first)]
        result=f.dispatch(reply)
        self.assertEqual(result.publication_generation,2);self.assertEqual(f.runtime.commits,2)

    def test_late_terminal_contradiction_no_rollback(self):
        f=Fixture();f.propose();f.dispatch();state=f.adapter.state;rng=f.runtime.rng
        terminal=f.terminal();terminal['status']='cancelled';terminal['reason']='cancelled'
        with self.assertRaises(Exception):f.status(terminals=[terminal])
        # The actual Bridge quarantines immediately; owner-thread intake must mirror it.
        with self.assertRaises(FeedbackError):f.coordinator.ingest_returned()
        self.assertEqual(f.owner.status['phase'],'poisoned');self.assertIs(f.adapter.state,state)
        self.assertEqual(f.runtime.rng,rng);self.assertEqual(f.runtime.restores,0)

    def test_late_contradiction_retains_pending_successor_and_original(self):
        f=Fixture();f.propose();f.dispatch(f.response(terminal=False));first=f.last_row
        f.identity['frameId']=2;f.propose();prepared=f.owner._prepared;unresolved=f.owner._unresolved
        term=f.terminal(first);term['status']='cancelled';term['reason']='cancelled'
        with self.assertRaises(Exception):f.status(terminals=[term])
        with self.assertRaises(FeedbackError):f.coordinator.ingest_returned(current_identity=f.identity)
        self.poisoned(f);self.assertIs(f.owner._prepared,prepared);self.assertIs(f.owner._unresolved,unresolved)

    def test_exact_token_connection_origin_and_disposition(self):
        for kind in ('token','connection','origin','proof'):
            with self.subTest(kind=kind):
                f=Fixture();f.propose();token=f.proposal.token
                if kind=='token':
                    other=ProposalToken(token.owner,token.generation,token.sequence)
                    with self.assertRaises(FeedbackError):f.coordinator.not_submitted(other)
                elif kind=='connection':
                    f.bridge.handle=object()
                    with self.assertRaises(FeedbackError):f.coordinator.not_submitted(token)
                elif kind=='origin':
                    changed=dict(f.identity,readinessEpoch=2)
                    with self.assertRaises(FeedbackError):f.coordinator.pump(token,current_identity=changed)
                else:
                    proof=f.intake.abort_prewrite_registration(f.request['requestId'],token)
                    with self.assertRaises(FeedbackError):f.owner.cancel_unwritten_bound(token,
                        dataclasses.replace(proof),f.identity,f.bridge)
                self.assertEqual(f.runtime.commits,0)

    def test_model_and_epoch_drift_before_next_proposal(self):
        for kind in ('model','epoch'):
            with self.subTest(kind=kind):
                f=Fixture();f.propose();f.dispatch();f.identity['frameId']=2
                if kind=='model':f.runtime.model_revision+=1
                else:f.identity['controlEpoch']+=1
                with self.assertRaises(FeedbackError):f.propose()
                self.assertEqual(f.runtime.prepares,1)

    def test_no_bypass_admission_receipt_boolean_reset_goal(self):
        f=Fixture();f.propose()
        for method,args in [(f.owner.admission,()),(f.owner.receipt,()),(f.owner.settle,()),
                            (f.owner.reset,()),(f.owner.set_goal,('anything',))]:
            with self.subTest(method=method.__name__):
                with self.assertRaises(FeedbackError):method(*args)
        self.assertEqual(f.runtime.commits,0);self.assertTrue(f.owner._leased)

    def test_close_requires_terminal_then_healthy_close(self):
        f=Fixture();f.propose();f.dispatch(f.response(terminal=False))
        with self.assertRaises(FeedbackError):f.owner.close()
        f.status(terminals=[f.terminal()]);f.owner.close()
        self.assertEqual(f.owner.status['phase'],'closed');self.assertFalse(f.owner._leased)

    def test_limits_reject_at_50ms_and_100ms_without_wire(self):
        for case in ('compute','source','expiry'):
            with self.subTest(case=case):
                f=Fixture();f.propose()
                now=20.
                if case=='compute':f.coordinator._pending['proposalWallNs']=50_000_000
                if case=='source':now=100.
                if case=='expiry':
                    request=p.decode(f.coordinator._pending['request']);request['expiresAtMs']=151.
                    f.coordinator._pending['request']=p.canonical(request)
                result=f.coordinator.dispatch(f.proposal.token,current_server_ms=now)
                self.assertFalse(result.committed);self.assertEqual(f.bridge.handle.sent,b'')
                self.assertEqual(f.runtime.restores,1)

    def test_proposal_clock_failure_retains_actual_proposal(self):
        f=Fixture();calls=[]
        def clock():
            calls.append(1)
            if len(calls)==2:raise OSError('clock')
            return 1
        f.coordinator._clock=clock
        with self.assertRaises(FeedbackError):f.propose()
        self.poisoned(f);self.assertIsNotNone(f.coordinator._pending)
        self.assertIsNotNone(f.owner._prepared);self.assertEqual(f.runtime.prepares,1)

    def test_foreign_prewrite_action_not_discarded(self):
        f=Fixture();f.propose(bind=False);other=object();f.intake._action=('foreign',other,b'wire')
        with self.assertRaises(Exception):f.coordinator.bind(f.proposal.token,f.request)
        self.poisoned(f);self.assertIs(f.intake._action[1],other);self.assertEqual(f.runtime.restores,0)

    def test_terminal_only_no_application_does_not_commit(self):
        f=Fixture();f.propose();reply=f.response();reply['stepApplications']['records']=[]
        with self.assertRaises(FeedbackError):f.dispatch(reply)
        self.poisoned(f);self.assertEqual(f.runtime.commits,0)

    def test_detached_result_and_whole_batch_ticket_revision(self):
        f=Fixture();f.propose();f.proposal.result['steps'][0]['keys'].clear()
        original=f.owner.stage_application
        def changed(*args):
            f.intake.ledger._observed+=1
            return original(*args)
        f.owner.stage_application=changed
        with self.assertRaises(FeedbackError):f.dispatch()
        self.poisoned(f);self.assertEqual(f.runtime.commits,0)

    def test_default_off_eager_only(self):
        f=Fixture()
        with self.assertRaises(FeedbackError):StepApplicationNativeBinding(f.owner,f.bridge,f.intake,f.model)
        with self.assertRaises(FeedbackError):f.coordinator.install()
        with self.assertRaises(p.ProtocolError):f.intake.install(f.bridge)
        f.adapter.use_cuda_graph=True
        with self.assertRaises(FeedbackError):StepApplicationHistoryOwner(f.adapter,f.runtime,inert=True)

    def test_32_unwritten_attempts_bounded_no_request_recycling(self):
        f=Fixture();ids=[]
        for _ in range(32):
            f.propose();ids.append(f.request['requestId']);f.coordinator.not_submitted(f.proposal.token)
        self.assertEqual(len(set(ids)),32);self.assertEqual(f.runtime.prepares,32)
        with self.assertRaises(FeedbackError):f.propose()
        self.assertLessEqual(len(f.coordinator.metadata()),65536)
        self.assertLessEqual(len(f.intake.disposition_metadata()),16384)
        self.assertEqual(len(f.owner._tombstones),32)

    def test_malformed_unbound_request_has_exact_local_disposition(self):
        for change in ('type','identity','transformed'):
            with self.subTest(change=change):
                f=Fixture();f.propose(bind=False)
                if change=='type':f.request['frameId']=True
                if change=='identity':f.request['modelId']='foreign'
                if change=='transformed':f.request['steps'][0]['keys']=[]
                with self.assertRaises(Exception):f.coordinator.bind(f.proposal.token,f.request)
                self.assertEqual(f.owner.status['phase'],'ready');self.assertEqual(f.runtime.restores,1)
                self.assertFalse(f.coordinator._last_disposition.committed)
                self.assertEqual(f.bridge.handle.sent,b'')

    def test_invalid_return_keeps_true_attempted_write_fact(self):
        f=Fixture();f.propose();reply=f.response();reply['requestId']='wrong'
        with self.assertRaises(FeedbackError):f.dispatch(reply)
        proof=f.intake.submission_disposition(f.request['requestId'],f.proposal.token)
        self.assertEqual(proof.status,'unknown');self.assertIs(proof.write_attempted,True)
        self.assertEqual(proof.observed_client_ns,3000)

    def test_final_ticket_failure_after_release_retains_both_stages(self):
        f=Fixture();f.propose()
        def fail(*args):raise ValueError('final_ticket')
        f.intake.ledger.complete_native_ticket=fail
        with self.assertRaises(FeedbackError):f.dispatch()
        self.poisoned(f);self.assertEqual(f.runtime.releases,1)
        self.assertFalse(f.owner._leased);self.assertEqual(f.owner._publication['ledgerGeneration'],1)
        self.assertFalse(f.owner._publication['ownerFinalized'])

    def test_wrong_callback_digest_retains_native_commit(self):
        f=Fixture();f.propose();original=f.owner.stage_application
        f.owner.stage_application=lambda *args:original(*args).hex()
        with self.assertRaises(FeedbackError):f.dispatch()
        self.poisoned(f);self.assertEqual(f.runtime.commits,1);self.assertEqual(f.runtime.releases,0)

    def test_rejected_successor_keeps_prior_unreconciled_owner(self):
        f=Fixture();f.propose();f.dispatch(f.response(terminal=False));old=f.owner._unresolved;state=f.adapter.state
        checkpoint=f.runtime.rng;f.identity['frameId']=2;f.propose()
        result=f.dispatch(f.response(applied=False,kind='rejected'))
        self.assertFalse(result.committed);self.assertIs(f.owner._unresolved,old)
        self.assertIs(f.adapter.state,state);self.assertEqual(f.runtime.rng,checkpoint)
        self.assertEqual(f.runtime.commits,1)

    def test_actual_noop_application_is_still_one_commit(self):
        f=Fixture();f.runtime.keys=[];f.propose();result=f.dispatch()
        self.assertIs(type(result),ApplicationSettlement);self.assertEqual(f.last_row['calls'],[])
        self.assertEqual(f.runtime.commits,1)

    def test_unknown_status_quarantines_pending_and_prior(self):
        f=Fixture();f.propose();f.dispatch(f.response(terminal=False));old=f.owner._unresolved
        f.identity['frameId']=2;f.propose();prepared=f.owner._prepared;f.reply({},raw=b'')
        with self.assertRaises(FeedbackError):f.coordinator.observe(current_identity=f.identity)
        self.poisoned(f);self.assertIs(f.owner._unresolved,old);self.assertIs(f.owner._prepared,prepared)

    def test_status_observation_reconciles_without_another_native_pass(self):
        f=Fixture();f.propose();f.dispatch(f.response(terminal=False))
        f.reply(dict(type='status',stepApplications=p.decode(f.out.batch()),stepApplicationTerminals=[f.terminal()]))
        self.assertIsNone(f.coordinator.observe());self.assertIsNone(f.owner._unresolved)
        self.assertEqual((f.runtime.prepares,f.runtime.commits),(1,1))

    def test_complete_maximum_count_and_failure_metadata_fixture(self):
        from _step_application_capacity_fixture import construct
        # The guarded runner retains capacity evidence in its owned attempt.
        # Direct portable use still owns and cleans its temporary fixture.
        import tempfile
        from pathlib import Path
        output=globals().get('CAPACITY_OUTPUT')
        if output is not None:
            result=construct(output)
        else:
            with tempfile.TemporaryDirectory() as temporary:
                result=construct(Path(temporary)/'capacity')
        self.assertEqual(result['actualMaximumApplicationCount'],32)
        self.assertTrue(result['unresolvedPlusPendingFixture'])
        self.assertTrue(all(row['bytes']<=row['cap'] for row in result['fixtures']))

    def test_primary_binding_error_and_cleanup_failure_are_separate(self):
        f=Fixture();f.propose(bind=False)
        def primary(*args):raise ValueError('binding_primary')
        def cleanup(*args):raise OSError('restore_cleanup')
        f.intake.propose=primary;f.runtime.restore_rng=cleanup
        with self.assertRaisesRegex(ValueError,'binding_primary'):f.coordinator.bind(f.proposal.token,f.request)
        self.poisoned(f);row=p.decode(f.coordinator.metadata())['failure']
        self.assertEqual(row['type'],'ValueError');self.assertIsNotNone(row['cleanupError'])
        self.assertTrue(f.owner._leased);self.assertEqual(f.bridge.handle.sent,b'')

    def test_release_error_retains_published_operation(self):
        f=Fixture();f.propose()
        def fail():raise OSError('release_uncertain')
        f.runtime.release_hook=fail
        with self.assertRaises(FeedbackError):f.dispatch()
        self.poisoned(f);self.assertIsNotNone(f.owner._publication);self.assertIsNotNone(f.owner._unresolved)
        self.assertEqual(f.intake.ledger._records[1]['publishedGeneration'],1)
        self.assertFalse(f.owner._publication['ownerFinalized'])

    def test_returned_binding_copy_cannot_change_wire_or_model_action(self):
        f=Fixture();f.propose();returned=p.decode(f.coordinator._pending['wire'],65536)
        returned['steps'][0]['keys'].clear();f.request['steps'][0]['keys'].clear()
        # Producer fixture uses the independently retained original wire, just as actual dispatch does.
        result=f.dispatch()
        self.assertIs(type(result),ApplicationSettlement)
        self.assertEqual(f.last_row['binding']['step']['keys'],['LBUTTON'])


if __name__ == '__main__':
    unittest.main()
