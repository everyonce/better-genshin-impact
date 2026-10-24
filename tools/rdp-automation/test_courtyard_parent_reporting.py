"""Focused parent-report projection checks; execute uses fake client and process boundaries."""
import ast
from contextlib import redirect_stdout
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load_parent():
    """Compile actual parent/read functions without importing transport or an executing client."""
    evidence_path = Path(os.environ.get('COURTYARD_EVIDENCE_SOURCE', str(HERE/'courtyard_evidence.py')))
    namespace = dict(Path=Path,hashlib=hashlib,json=json,math=math,re=re,os=os,sys=sys,
        HERE=HERE,WORKER_SECONDS=270,MAX_FILE_BYTES=256*1024,MAX_FILES=48,MAX_TOTAL_BYTES=8*1024*1024)
    groups = [(evidence_path,{'require','read','pin'}),
        (HERE/'courtyard_sequence.py',{'publish','error_record','broker_diagnostics','worker_error_diagnostics',
            'worker_diagnostics','require_broker_retired','execute'})]
    for path,names in groups:
        nodes = [x for x in ast.parse(path.read_text(encoding='utf8')).body if isinstance(x,ast.FunctionDef) and x.name in names]
        if {x.name for x in nodes} != names:
            raise AssertionError('Actual source function set changed.')
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
    return namespace


class ParentReportingTests(unittest.TestCase):
    """Exercise only the parent outcome path, keeping the worker loop and native client unexecuted."""
    def setUp(self):
        """Create an exclusive fake batch and reject every real child-process launch."""
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.batch=Path(self.temp.name)/'batch';self.ns=load_parent()
        for name in ('Popen','check_output','run'):
            guard=patch.object(subprocess,name,side_effect=AssertionError('No process/native execution'))
            guard.start();self.addCleanup(guard.stop)
        self.binding=dict(child=dict(processId=20928,windowsSessionId=3,instanceNonce='a'*32),
            _bindingPin=dict(path='binding.json',sha256='b'*64,bytes=10))
        self.plan=dict(toolFiles=[],package=dict(path=str(HERE/'courtyard_sequence.py'),sha256='c'*64,bytes=1),
            legs=[dict(name='leg-01-return',direction='return'),dict(name='leg-02-forward',direction='forward')])
        self.broker=dict(success=False,returnCode=1,timedOut=False,windowsSessionId=3,remoteDesktop=True,
            outputIncomplete=False,stdoutTruncated=False,stderrTruncated=False)
        self.calls=0;self.flights=0;self.transport_error=None;self.raw=None
        self.result=self.worker_result()
        self.ns['evidence']=types.SimpleNamespace(load_client=lambda binding:types.SimpleNamespace(run_command=self.run_command))
        self.ns['current']=self.current;self.ns['latest']=lambda *args:None

    def current(self,*args,**kwargs):
        """Retain the existing one preflight and one postflight boundary under a fake source."""
        self.flights+=1
        return dict(root={},child=self.binding['child'],game={})

    def worker_result(self):
        """Match the actual producer's bounded rows, including a known failed second terminal."""
        failure=dict(type='RuntimeError',message='forward_lease_expired',messageTruncated=False)
        legs=[]
        for i,item in enumerate(self.plan['legs']):
            legs.append(dict(name=item['name'],action='courtyard-'+item['direction'],child=self.binding['child'],
                bindingSha256=self.binding['_bindingPin']['sha256'],supervisorPackage=self.plan['package'],
                success=i==0,error=None if i==0 else failure,mutationCalls=1,nativeTerminalObserved=True,
                nativeResult=dict(path=str((self.batch/'legs'/item['name']/'result.json').resolve()),bytes=123,sha256='d'*64)))
        return dict(schema='r45-courtyard-worker-result-v1',stopReason='failed_or_unknown',error=failure,
            nativeOwnerRetirementKnown=True,automaticReplay=False,legs=legs)

    def run_command(self,*args):
        """Publish fake worker output once; never invoke the supplied interpreter argv."""
        self.calls+=1
        if self.transport_error is not None:raise self.transport_error
        if self.raw is not None:(self.batch/'worker-result.json').write_bytes(self.raw)
        elif self.result is not None:(self.batch/'worker-result.json').write_text(json.dumps(self.result),encoding='utf8')
        return self.broker

    def run_parent(self):
        """Run the actual extracted parent function and inspect its exclusive final report."""
        with redirect_stdout(io.StringIO()):
            code=self.ns['execute'](types.SimpleNamespace(output_dir=self.batch),self.binding,{}, {},self.plan)
        final=json.loads((self.batch/'summary.json').read_bytes())
        self.assertEqual(self.calls,1);self.assertEqual(self.flights,2)
        self.assertFalse(final['automaticReplay']);self.assertTrue(final['nativeRetirementCannotBeInferredFromWorkerExit'])
        self.assertTrue(final['workerTerminalReportIsNotOsRetirement'])
        return code,final

    def test_known_nonzero_worker_failure_retains_broker_and_terminal_report(self):
        code,final=self.run_parent();d=final['diagnostics'];w=d['worker']
        self.assertEqual(code,1);self.assertFalse(final['success']);self.assertIn('forward_lease_expired',final['error']['message'])
        self.assertIs(d['broker']['timedOut'],False);self.assertEqual(d['broker']['returnCode'],1)
        self.assertEqual(w['successfulLegCount'],1);self.assertEqual(w['attemptedLegCount'],2)
        self.assertTrue(w['nativeOwnerRetirementReported']);self.assertTrue(w['lastLeg']['nativeTerminalReported'])
        self.assertEqual(w['lastLeg']['reportedNativeResult'],self.result['legs'][-1]['nativeResult'])
        self.assertIsNone(final['cleanupError']);self.assertTrue(final['fullRouteAuditsPending'])

    def test_timeout_never_reads_even_an_existing_worker_result(self):
        self.broker['timedOut']=True
        self.ns['read']=lambda *args:(_ for _ in ()).throw(AssertionError('Must not read a timed-out worker'))
        code,final=self.run_parent();d=final['diagnostics']
        self.assertEqual(code,1);self.assertTrue(d['broker']['timedOut']);self.assertIsNone(d['worker'])
        self.assertIn('native terminal is unknown',final['error']['message'])

    def test_transport_unknown_has_no_broker_or_native_retirement_claim(self):
        self.transport_error=RuntimeError('lost broker response')
        code,final=self.run_parent()
        self.assertEqual(code,1);self.assertIsNone(final['diagnostics']['broker']);self.assertIsNone(final['diagnostics']['worker'])
        self.assertFalse(final['workerProcessReturnRecorded']);self.assertEqual(final['error']['message'],'lost broker response')

    def test_malformed_json_keeps_useful_broker_facts(self):
        self.raw=b'{broken'
        code,final=self.run_parent();d=final['diagnostics']
        self.assertEqual(code,1);self.assertEqual(d['broker']['returnCode'],1);self.assertIs(d['broker']['timedOut'],False)
        self.assertIsNone(d['worker']);self.assertIsNotNone(d['workerReadError'])

    def test_oversized_worker_result_is_rejected_without_reading_payload(self):
        self.raw=b'x'*(self.ns['MAX_FILE_BYTES']+1)
        code,final=self.run_parent();d=final['diagnostics']
        self.assertEqual(code,1);self.assertIn('Oversized',d['workerReadError']['message']);self.assertIsNone(d['worker'])
        self.assertEqual(d['broker']['returnCode'],1)

    def test_zero_exit_missing_worker_result_remains_failure(self):
        self.result=None;self.broker.update(success=True,returnCode=0)
        code,final=self.run_parent()
        self.assertEqual(code,1);self.assertFalse(final['success']);self.assertIsNotNone(final['diagnostics']['workerReadError'])

    def test_uncertain_broker_preserves_facts_but_never_interprets_worker(self):
        self.broker['stdoutTruncated']=True
        self.ns['read']=lambda *args:(_ for _ in ()).throw(AssertionError('Must not read uncertain worker'))
        code,final=self.run_parent();d=final['diagnostics']
        self.assertEqual(code,1);self.assertTrue(d['broker']['stdoutTruncated']);self.assertIsNone(d['worker'])
        self.assertIsNone(d['workerReadError'])

    def test_nonobject_broker_still_publishes_failure(self):
        self.broker=[]
        code,final=self.run_parent()
        self.assertEqual(code,1);self.assertFalse(final['workerProcessReturnRecorded'])
        self.assertIsNone(final['diagnostics']['broker']);self.assertIsNone(final['diagnostics']['worker'])

    def test_unknown_native_terminal_is_reported_without_promotion(self):
        self.result['nativeOwnerRetirementKnown']=False;self.result['legs'][-1]['nativeTerminalObserved']=False
        code,final=self.run_parent()
        self.assertEqual(code,1);self.assertFalse(final['diagnostics']['worker']['nativeOwnerRetirementReported'])
        self.assertFalse(final['diagnostics']['worker']['lastLeg']['nativeTerminalReported'])

    def test_success_keeps_exit_and_acceptance_path(self):
        self.broker.update(success=True,returnCode=0);self.result.update(error=None,stopReason='leg_limit')
        self.result['legs'][-1].update(success=True,error=None)
        code,final=self.run_parent()
        self.assertEqual(code,0);self.assertTrue(final['success']);self.assertIsNone(final['error'])
        self.assertIsNone(final['cleanupError']);self.assertEqual(final['diagnostics']['worker']['successfulLegCount'],2)

    def test_zero_exit_does_not_promote_worker_error(self):
        self.broker.update(success=True,returnCode=0)
        code,final=self.run_parent()
        self.assertEqual(code,1);self.assertFalse(final['success']);self.assertIsNotNone(final['diagnostics']['worker']['error'])

    def test_contradictory_success_or_stop_records_cannot_pass_zero_exit(self):
        original=copy.deepcopy(self.result)
        changes=[lambda r:r.update(error=None),lambda r:r.update(stopReason='leg_limit'),
            lambda r:r['legs'][-1].update(success=True),lambda r:r['legs'][-1].update(error=None),
            lambda r:r['legs'][0].update(success=False,error=r['error']),
            lambda r:r['legs'][0].update(nativeTerminalObserved=False),
            lambda r:r['error'].update(message='different top-level error')]
        self.batch.mkdir()
        for change in changes:
            with self.subTest(change=change):
                value=json.loads(json.dumps(original));change(value)
                (self.batch/'worker-result.json').write_text(json.dumps(value),encoding='utf8')
                with self.assertRaises(RuntimeError):self.ns['worker_diagnostics'](self.batch,self.plan,self.binding)

    def test_partial_admission_cutoff_keeps_successful_terminal_without_claiming_all_legs(self):
        self.broker.update(success=True,returnCode=0)
        self.result.update(legs=self.result['legs'][:1],error=None,stopReason='admission_cutoff')
        code,final=self.run_parent();w=final['diagnostics']['worker']
        self.assertEqual(code,0);self.assertTrue(final['success']);self.assertEqual(w['attemptedLegCount'],1)
        self.assertEqual(w['stopReason'],'admission_cutoff');self.assertTrue(w['nativeOwnerRetirementReported'])

    def test_zero_exit_contradictory_terminal_fails_actual_parent(self):
        self.broker.update(success=True,returnCode=0);self.result['error']=None
        code,final=self.run_parent()
        self.assertEqual(code,1);self.assertFalse(final['success']);self.assertIsNone(final['diagnostics']['worker'])
        self.assertIsNotNone(final['diagnostics']['workerReadError']);self.assertEqual(final['diagnostics']['broker']['returnCode'],0)

    def test_zero_leg_cutoff_is_valid_but_does_not_claim_native_completion(self):
        self.broker.update(success=True,returnCode=0)
        self.result.update(legs=[],error=None,stopReason='admission_cutoff',nativeOwnerRetirementKnown=False)
        code,final=self.run_parent();w=final['diagnostics']['worker']
        self.assertEqual(code,1);self.assertFalse(final['success']);self.assertEqual(w['attemptedLegCount'],0)
        self.assertIsNone(w['lastLeg']);self.assertFalse(w['nativeOwnerRetirementReported'])
        self.assertIsNone(final['diagnostics']['workerReadError'])

    def test_leg_limit_and_cutoff_counts_match_actual_producer(self):
        self.batch.mkdir()
        self.result.update(error=None,stopReason='leg_limit')
        self.result['legs'][-1].update(success=True,error=None)
        for rows,reason in ((self.result['legs'][:1],'leg_limit'),(self.result['legs'],'admission_cutoff')):
            with self.subTest(reason=reason):
                value=copy.deepcopy(self.result);value.update(legs=rows,stopReason=reason)
                (self.batch/'worker-result.json').write_text(json.dumps(value),encoding='utf8')
                with self.assertRaises(RuntimeError):self.ns['worker_diagnostics'](self.batch,self.plan,self.binding)

    def test_schema_identity_and_projection_bounds(self):
        original=copy.deepcopy(self.result)
        changes=[lambda r:r.update(schema='unknown'),lambda r:r.update(legs=r['legs']*3),
            lambda r:r['legs'][-1].update(child={}),lambda r:r['error'].update(message='x'*4097),
            lambda r:r['legs'][-1]['nativeResult'].update(path=str(self.batch.parent/'outside.json')),
            lambda r:r['legs'][-1].update(mutationCalls=True)]
        self.batch.mkdir()
        for change in changes:
            with self.subTest(change=change):
                value=copy.deepcopy(original);change(value)
                (self.batch/'worker-result.json').write_text(json.dumps(value),encoding='utf8')
                with self.assertRaises(RuntimeError):self.ns['worker_diagnostics'](self.batch,self.plan,self.binding)

    def test_extra_worker_fields_are_not_echoed(self):
        self.result['arbitraryPayload']='secret-marker'*1000;self.result['legs'][-1]['arbitraryPayload']='secret-marker'
        _,final=self.run_parent()
        self.assertNotIn('secret-marker',json.dumps(final));self.assertLess(len(json.dumps(final)),16384)

    def test_actual_json_reader_rejects_duplicate_and_nonfinite_worker_fields(self):
        self.batch.mkdir()
        for raw in (b'{"x":1,"x":2}',b'{"x":1e999}',b'{"x":NaN}'):
            with self.subTest(raw=raw):
                (self.batch/'worker-result.json').write_bytes(raw)
                with self.assertRaises(RuntimeError):self.ns['worker_diagnostics'](self.batch,self.plan,self.binding)


if __name__=='__main__':unittest.main(verbosity=2)
