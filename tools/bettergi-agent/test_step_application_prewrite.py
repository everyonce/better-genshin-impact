"""New early-failure cases against actual H01/H02 Bridge AST and exact detached ledger."""
import json
from pathlib import Path
import struct
import types
import unittest
import step_application_test_fixtures as f
import step_application_protocol as p

HERE=Path(__file__).resolve().parent
OLD=HERE/'fixtures/step_application/legacy'


def old_bridge(reply,intake=None):
    """Use the exact prior method without importing either full stream module."""
    saved=f.HERE
    try:
        f.HERE=OLD
        return f.bridge(reply,intake)
    finally:f.HERE=saved


class PrewriteCorrectionCases(unittest.TestCase):
    """Only changed preparation/failure ordering and its immediate write boundary."""
    def assert_not_submitted(self,intake,transport,token):
        """A no-write local disposition retains exact token and zero published history."""
        self.assertEqual(transport.handle.sent,b'')
        self.assertIsNone(intake._action)
        row=intake.ledger._proposals['request']
        self.assertIs(row['token'],token);self.assertEqual(row['phase'],'not_submitted')
        self.assertFalse(intake.ledger.quarantined)
        snapshot=p.decode(intake.ledger.snapshot(cutoff_client_ns=3000),512*1024)
        self.assertEqual(snapshot['publicationCount'],0);self.assertEqual(snapshot['records'],[])
        self.assertEqual(snapshot['terminals'],[]);self.assertEqual(snapshot['acknowledgedThrough'],0)

    def witness(self,case):
        """Reproduce the root's old counterexample and require the corrected disposition."""
        evidence=json.loads((HERE/'fixtures/step_application/prewrite-counterexamples.json').read_bytes())
        expected=next(row for row in evidence['cases'] if row['case']==case)
        for old in (True,False):
            _,intake,wire,token=f.transaction()
            if case=='nonserializable_action_value':wire['steps'][0]['mouseDx']=object()
            else:wire['modelId']='x'*65536
            transport=old_bridge({},intake) if old else f.bridge({},intake)
            with self.assertRaises((TypeError,ValueError)) as caught:f.call(transport,wire)
            self.assertEqual(type(caught.exception).__name__,expected['exception'])
            self.assertEqual(str(caught.exception),expected['message'])
            if old:
                self.assertEqual(transport.handle.sent,b'');self.assertIsNotNone(intake._action)
                self.assertEqual(intake.ledger._proposals['request']['phase'],'proposed')
            else:self.assert_not_submitted(intake,transport,token)

    def test_nonserializable_original_witness_and_known_not_submitted(self):
        self.witness('nonserializable_action_value')

    def test_oversized_original_witness_and_known_not_submitted(self):
        self.witness('oversized_action_value')

    def test_envelope_duplicate_reserved_field_is_also_no_write(self):
        _,intake,_,token=f.transaction();transport=f.bridge({},intake)
        with self.assertRaises(TypeError):transport.request('action',version=1)
        self.assert_not_submitted(intake,transport,token)

    def test_missing_hello_field_is_classified_before_write(self):
        _,intake,wire,token=f.transaction();transport=f.bridge({},intake)
        del transport.hello['sessionId']
        with self.assertRaises(KeyError):f.call(transport,wire)
        self.assert_not_submitted(intake,transport,token)

    def test_both_active_serializations_are_locked_and_intake_still_returns(self):
        out,intake,wire,_=f.transaction();transport=f.bridge(f.response(out,wire),intake)
        observations=[]
        def dumps(*args,**kwargs):
            observations.append(transport.lock.locked())
            return json.dumps(*args,**kwargs)
        transport.request.__func__.__globals__['json']=types.SimpleNamespace(dumps=dumps,loads=json.loads)
        reply,_=f.call(transport,wire)
        self.assertEqual(reply['type'],'accepted');self.assertEqual(observations,[True,True])
        snapshot=p.decode(intake.ledger.snapshot(cutoff_client_ns=3000),512*1024)
        self.assertEqual(snapshot['acknowledgedThrough'],1);self.assertEqual(snapshot['publicationCount'],0)

    def test_legacy_bytes_and_prelock_failure_order_are_preserved(self):
        class ObservedLock:
            """New intake selection and serialization share one lock; legacy bytes/errors stay exact."""
            def __init__(self):self.entries=0
            def __enter__(self):self.entries+=1
            def __exit__(self,*args):return False
        wires=[]
        for factory in (old_bridge,f.bridge):
            transport=factory(dict(type='status',receipts=[]))
            self.assertEqual(transport.request('status'),(dict(type='status',receipts=[]),b''))
            wires.append(bytes(transport.handle.sent))
            for value,error in ((object(),TypeError),('x'*65536,ValueError)):
                transport=factory({});transport.lock=ObservedLock()
                with self.assertRaises(error):transport.request('action',modelId=value)
                self.assertEqual(transport.handle.sent,b'')
                self.assertEqual(transport.lock.entries,0 if factory is old_bridge else 1)
        self.assertEqual(wires[0],wires[1])
        body=json.dumps(dict(version=1,command='status',sessionId='session',ownerEpoch='owner',goalVersion=1),separators=(',',':')).encode()
        self.assertEqual(wires[1],struct.pack('<I',len(body))+body)

    def test_first_attempted_write_remains_unknown_not_local_rejection(self):
        _,intake,wire,token=f.transaction();transport=f.bridge({},intake,fail_write=True)
        with self.assertRaisesRegex(OSError,'partial_fake_write'):f.call(transport,wire)
        self.assertEqual(len(transport.handle.sent),2);self.assertTrue(intake.ledger.quarantined)
        self.assertEqual(intake.ledger._proposals['request']['phase'],'proposed')
        self.assertIs(intake.ledger._proposals['request']['token'],token)
        self.assertEqual(p.decode(intake.ledger.snapshot(cutoff_client_ns=3000),512*1024)['publicationCount'],0)


if __name__=='__main__':unittest.main()
