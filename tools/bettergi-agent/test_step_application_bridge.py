"""Actual Bridge AST plus immutable H02 ledger; only in-memory wire and software fixtures."""
import copy
import hashlib
import json
import struct
import unittest
import step_application_protocol as p
from step_application_transport import StepApplicationIntake,validate_submission,validate_envelope,parse_header
from step_application_test_fixtures import transaction,response,bridge,call,maximal_packets,configuration,HERE


class BridgeCases(unittest.TestCase):
    """Exercise substantive admission, transport failure, ordering and bounded reply behavior."""
    def test_legacy_ordinary_bridge_is_byte_compatible(self):
        transport=bridge(dict(type='status',receipts=[]));actual=transport.request('status')
        self.assertEqual(actual,(dict(type='status',receipts=[]),b''))
        expected=json.dumps(dict(version=1,command='status',sessionId='session',ownerEpoch='owner',goalVersion=1),separators=(',',':')).encode()
        self.assertEqual(transport.handle.sent,struct.pack('<I',len(expected))+expected)

    def test_production_installation_is_unconditionally_blocked(self):
        _,intake,_,_=transaction()
        with self.assertRaisesRegex(p.ProtocolError,'native_owner_unavailable'):intake.install(object())

    def test_actual_bridge_admission_batch_terminal_and_ack(self):
        out,intake,wire,_=transaction();reply=response(out,wire);transport=bridge(reply,intake)
        actual,_=call(transport,wire);self.assertEqual(actual,reply)
        snapshot=p.decode(intake.ledger.snapshot(cutoff_client_ns=3000),512*1024)
        self.assertEqual(snapshot['acknowledgedThrough'],1);self.assertEqual(snapshot['publicationCount'],0)
        self.assertEqual(snapshot['records'][0]['observedClientNs'],3000)
        ack=intake.prepare(dict(version=1,command='status',sessionId='session',ownerEpoch='owner',goalVersion=1))['stepApplicationsAck']
        self.assertEqual(ack,dict(version=1,channelId='channel',through=1,terminalRequestIds=['request']))

    def test_inherited_or_noop_evaluation_is_not_fabricated_mouse(self):
        out,intake,wire,_=transaction(key_list=[]);reply=response(out,wire);call(bridge(reply,intake),wire)
        row=reply['stepApplications']['records'][0]
        self.assertEqual(row['calls'],[]);self.assertEqual(row['heldEvaluation'],'returned')
        self.assertFalse(intake.ledger.quarantined)

    def test_mouse_failure_retained_but_never_published(self):
        out,intake,wire,_=transaction(delta=(1,2));reply=response(out,wire,failed=True,terminal=False)
        call(bridge(reply,intake),wire)
        snap=p.decode(intake.ledger.snapshot(cutoff_client_ns=3000),512*1024)
        self.assertTrue(intake.ledger.quarantined);self.assertEqual(snap['publicationCount'],0)
        self.assertEqual(snap['records'][0]['record']['calls'][-1]['stage'],'failed')

    def test_partial_write_is_unknown_and_no_retry(self):
        _,intake,wire,_=transaction();transport=bridge({},intake,fail_write=True)
        with self.assertRaisesRegex(OSError,'partial_fake_write'):call(transport,wire)
        self.assertEqual(len(transport.handle.sent),2);self.assertTrue(intake.ledger.quarantined)

    def test_local_prewrite_mismatch_is_known_not_submitted(self):
        _,intake,wire,token=transaction();bad=copy.deepcopy(wire);bad['steps'][0]['mouseDx']=1
        transport=bridge({},intake)
        with self.assertRaisesRegex(p.ProtocolError,'transport_action_binding'):call(transport,bad)
        self.assertEqual(transport.handle.sent,b'');self.assertFalse(intake.ledger.quarantined)
        self.assertEqual(intake.ledger._proposals['request']['phase'],'not_submitted')

    def test_wrong_admission_id_quarantines(self):
        out,intake,wire,_=transaction();reply=response(out,wire);reply['requestId']='foreign'
        with self.assertRaisesRegex(p.ProtocolError,'transport_admission'):call(bridge(reply,intake),wire)
        self.assertTrue(intake.ledger.quarantined);self.assertEqual(intake._ack,0)

    def test_missing_tail_cannot_be_acked_through_real_bridge(self):
        out,intake,wire,_=transaction();reply=response(out,wire);reply['stepApplications']['nextReservedSequence']=3
        with self.assertRaisesRegex(p.ProtocolError,'batch_prefix_count'):call(bridge(reply,intake),wire)
        self.assertTrue(intake.ledger.quarantined);self.assertEqual(intake._ack,0);self.assertEqual(intake._terminal_ack,[])

    def test_terminal_conflict_blocks_all_ack(self):
        out,intake,wire,_=transaction();reply=response(out,wire)
        reply['stepApplicationTerminals'].append(copy.deepcopy(reply['stepApplicationTerminals'][0]))
        reply['stepApplicationTerminals'][1]['status']='cancelled'
        with self.assertRaisesRegex(p.ProtocolError,'terminal_repeated'):call(bridge(reply,intake),wire)
        self.assertEqual(intake._ack,0);self.assertEqual(intake._terminal_ack,[])

    def test_unknown_terminal_cannot_be_acked(self):
        out,intake,wire,_=transaction();reply=response(out,wire)
        reply['stepApplicationTerminals'][0]['binding']['requestId']='foreign'
        with self.assertRaises(p.ProtocolError):call(bridge(reply,intake),wire)
        self.assertEqual(intake._terminal_ack,[])

    def test_identical_retransmission_is_retained_once(self):
        out,intake,wire,_=transaction();reply=response(out,wire);call(bridge(reply,intake),wire)
        poll={k:v for k,v in reply.items() if k!='requestId'};poll['type']='status'
        bridge(poll,intake).request('status')
        snap=p.decode(intake.ledger.snapshot(cutoff_client_ns=3000),512*1024)
        self.assertEqual(len(snap['records']),1);self.assertEqual(len(snap['terminals']),1);self.assertEqual(snap['publicationCount'],0)

    def test_confirmed_rejection_is_not_application(self):
        out,intake,wire,_=transaction();reply=dict(type='rejected',requestId='request',stepApplications=p.decode(out.batch()),stepApplicationTerminals=[])
        call(bridge(reply,intake),wire)
        self.assertEqual(intake.ledger._proposals['request']['phase'],'not_submitted');self.assertEqual(intake._ack,0)

    def test_duplicate_json_field_rejected_by_actual_active_parser(self):
        _,intake,_,_=transaction();transport=bridge({},intake,raw=b'{"type":"status","type":"accepted"}')
        with self.assertRaisesRegex(p.ProtocolError,'duplicate_field'):transport.request('status')
        self.assertTrue(intake.ledger.quarantined)

    def test_boolean_payload_length_rejected(self):
        _,intake,_,_=transaction();transport=bridge(dict(type='status',payloadBytes=True),intake)
        with self.assertRaisesRegex(ValueError,'image packet'):transport.request('status')

    def test_complete_rgb_payload_consumed_before_knowledge_stamp(self):
        out,intake,wire,_=transaction();reply=response(out,wire);reply['payloadBytes']=3
        _,pixels=call(bridge(reply,intake,pixels=b'RGB'),wire);self.assertEqual(pixels,b'RGB')
        self.assertEqual(intake.ledger._observed,3000)

    def test_truncated_rgb_quarantines_without_ack(self):
        out,intake,wire,_=transaction();reply=response(out,wire);reply['payloadBytes']=3
        with self.assertRaises(EOFError):call(bridge(reply,intake,pixels=b'R'),wire)
        self.assertTrue(intake.ledger.quarantined);self.assertEqual(intake._ack,0)

    def test_quarantine_does_not_block_existing_cleanup_transport(self):
        _,intake,_,_=transaction();intake.ledger.uncertain('fixture')
        transport=bridge(dict(type='released'),intake);self.assertEqual(transport.request('release')[0]['type'],'released')
        self.assertNotIn('stepApplicationsAck',json.loads(transport.handle.sent[4:]))

    def test_lease_change_is_rejected_before_write(self):
        _,intake,_,_=transaction();transport=bridge({},intake);transport.hello['ownerEpoch']='other'
        with self.assertRaisesRegex(p.ProtocolError,'transport_lease'):transport.request('status')
        self.assertEqual(transport.handle.sent,b'')

    def test_foreign_ack_is_never_forwarded(self):
        _,intake,wire,_=transaction();wire['stepApplicationsAck']={}
        transport=bridge({},intake)
        with self.assertRaisesRegex(p.ProtocolError,'caller_ack'):call(transport,wire)
        self.assertEqual(transport.handle.sent,b'')

    def test_snapshot_is_not_affected_by_later_caller_mutation(self):
        out,intake,wire,_=transaction();reply=response(out,wire);call(bridge(reply,intake),wire)
        before=intake.ledger.snapshot(cutoff_client_ns=3000);reply['stepApplications']['records'].clear()
        self.assertEqual(intake.ledger.snapshot(cutoff_client_ns=3000),before)

    def test_action_envelope_preserves_exact_original_hash(self):
        _,_,wire,_=transaction();raw=validate_envelope(wire)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),wire['stepApplication']['binding']['submissionSha256'])
        self.assertIn(b'"observedAtMs":0.0',raw)

    def test_unknown_submission_field_is_rejected(self):
        _,_,wire,_=transaction();raw=p.decode(wire['stepApplication']['submissionJson'].encode())
        raw['invented']=1
        with self.assertRaisesRegex(p.ProtocolError,'submission_fields'):validate_submission(raw)

    def test_typed_numeric_rewrite_is_rejected(self):
        _,_,wire,_=transaction();wire['observedAtMs']=0
        with self.assertRaisesRegex(p.ProtocolError,'submission_wire_mismatch'):validate_envelope(wire)

    def test_alias_and_reserved_policy_not_normalized(self):
        for keys in (['SHIFT'],['CONTROL'],['ESC'],['LCONTROL','ESCAPE']):
            with self.subTest(keys=keys),self.assertRaises(p.ProtocolError):transaction(key_list=keys)

    def test_noncanonical_submission_string_rejected(self):
        _,_,wire,_=transaction();wire['stepApplication']['submissionJson']=' '+wire['stepApplication']['submissionJson']
        with self.assertRaisesRegex(p.ProtocolError,'submission_not_canonical'):validate_envelope(wire)

    def test_duplicate_or_nonfinite_whole_header_rejected(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}'):
            with self.subTest(raw=raw),self.assertRaises((p.ProtocolError,ValueError)):parse_header(raw)

    def test_real_combined_reply_and_extended_request_fit_bounds(self):
        raw,request,capacity=maximal_packets();value=parse_header(raw)
        self.assertEqual(len(value['stepApplicationTerminals']),4)
        self.assertEqual(len(value['receipts']),256)
        self.assertLess(capacity['withHeadroom'],4*1024*1024);self.assertLess(len(request),65536)
        for terminal in value['stepApplicationTerminals']:p.validate_terminal(terminal,configuration())

    def test_final_wire_bound_is_enforced(self):
        with self.assertRaisesRegex(p.ProtocolError,'wire_bytes'):parse_header(b' '*((4*1024*1024)+1))

    def test_actual_inherited_key_uses_complete_zero_call_marker(self):
        from step_application_ledger import Outbox
        _,_,template,_=transaction(key_list=['W']);bound=template['stepApplication']['binding']
        cfg=configuration();out=Outbox();initial=dict(keys=['W'],generation=0,complete=True)
        intake=StepApplicationIntake(cfg,out.enable(cfg,initial,idle=True))
        original=p.decode(template['stepApplication']['submissionJson'].encode())
        wire=intake.propose(original,bound['identity'],[bound['step']],bound['model'],object())
        ticket=out.reserve(p.canonical(bound))
        record=dict(dispatchStartedTicks=1100,heldReturnedTicks=1101,callsReturnedTicks=1102,publicationTicks=1103,
            trackedBefore=initial,trackedAfter=dict(keys=['W'],generation=1,complete=True),backendBefore='backend',backendAfter='backend',
            heldEvaluation='returned',calls=[],outcome='complete_returned',evidenceComplete=True,executionUncertain=False)
        out.finish(ticket,record)
        reply=dict(type='accepted',requestId='request',stepApplications=p.decode(out.batch()),stepApplicationTerminals=[])
        call(bridge(reply,intake),wire)
        self.assertEqual(intake._ack,1);self.assertFalse(intake.ledger.quarantined)
        snapshot=p.decode(intake.ledger.snapshot(cutoff_client_ns=3000),512*1024)
        self.assertEqual(snapshot['records'][0]['record']['calls'],[])

    def test_terminal_before_application_is_retained_without_false_commit(self):
        out,intake,wire,_=transaction()
        term=dict(version=1,channelId='channel',binding=wire['stepApplication']['binding'],applicationSequences=[],
                  status='cancelled',reason='start_deadline_expired',publicationTicks=1200,legacyEndedAtMs=40.0,releaseOutcome='returned_unverified')
        call(bridge(dict(type='accepted',requestId='request',stepApplications=p.decode(out.batch()),stepApplicationTerminals=[term]),intake),wire)
        snapshot=p.decode(intake.ledger.snapshot(cutoff_client_ns=3000),512*1024)
        self.assertTrue(intake.ledger.quarantined);self.assertEqual(snapshot['publicationCount'],0)
        self.assertEqual(len(snapshot['terminals']),1);self.assertEqual(intake._ack,0)
        cleanup=intake.prepare(dict(version=1,command='release',sessionId='session',ownerEpoch='owner',goalVersion=1))
        self.assertNotIn('stepApplicationsAck',cleanup)

    def test_grammar_caps_cover_extended_request_and_combined_reply(self):
        _,_,capacity=maximal_packets()
        self.assertEqual(capacity['requestGrammarUpperBoundBytes'],56578)
        self.assertLess(capacity['requestGrammarUpperBoundBytes'],capacity['requestCap'])
        self.assertLess(capacity['combinedWithMaxTerminalCapsAndHeadroom'],capacity['headerCap'])

    def test_maximum_request_retains_real_canonical_object_and_ack_fields(self):
        _,raw,capacity=maximal_packets();wire=p.decode(raw,65536)
        validate_envelope(wire)
        self.assertEqual(len(wire['steps'][0]['keys']),6);self.assertEqual(len(wire['stepApplicationsAck']['terminalRequestIds']),4)
        self.assertIn('startBeforeMs',wire);self.assertLessEqual(capacity['requestBindingBytes'],3072)
        self.assertEqual(len(wire['sessionId'].encode('utf8')),128)


if __name__=='__main__':unittest.main()
