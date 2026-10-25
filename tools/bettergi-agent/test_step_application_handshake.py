"""INERT_ONLY: actual Bridge AST and detached intake over owned in-memory handles.

Prepared source, not an execution receipt. No stream module, pipe, native owner,
model, process or session is imported/opened. Lock schedules are deterministic
fake schedules, not a claim of concurrent stress coverage.
"""
import ast
import copy
import io
import json
from pathlib import Path
import re
import struct
import types
import unittest

import step_application_protocol as p
import step_application_protocol_v2 as v2
import step_application_test_fixtures as old
from step_application_transport import StepApplicationIntake

# Historical Bridge fixture root; executable method bodies remain exact.
HERE = Path(__file__).resolve().parent/'fixtures/step_application/handshake_h01'
SOURCE = Path(__file__).resolve().parent/'stream_client.py'
BUILD = 'a'*64


def hello():
    """Synthetic opted hello with the producer's distinct elapsed/QPC clock fields."""
    return dict(version=1,type='hello',sessionId='session',ownerEpoch='owner',goalVersion=1,
        inputEnabled=True,clockFrequency=1000,allowedKeys=sorted(p.ALLOWED),
        inputTelemetry=dict(version=1,sessionOriginAtStopwatchTicks=12345,stopwatchFrequency=10000000),
        stepApplicationsAvailable=dict(version=2,mode=v2.MODE))


def enabled():
    """Synthetic exact fresh-channel reply; this is never a runtime qualification fixture."""
    cfg=dict(version=2,mode=v2.MODE,sessionId='session',ownerEpoch='owner',channelId='channel',
        backendId='win32-sendinput',backendEpoch='backend',buildSha256=BUILD,clockKind='windows_qpc',
        sessionOriginTicks=12345,clockFrequency=10000000,allowedKeys=sorted(p.ALLOWED-{'SHIFT','CONTROL','ESC'}))
    return dict(type='stepApplicationsEnabled',serverNowMs=1.25,
        stepApplicationConfirmation=dict(configuration=cfg,initialTracked=dict(keys=[],generation=0,complete=True),limits=dict(p.LIMITS)),
        stepApplications=dict(version=2,channelId='channel',acknowledgedThrough=0,nextReservedSequence=1,
            authorityLost=False,closedForSubmission=False,unpublished=0,records=[]),stepApplicationTerminals=[])


def packet(value):
    """Serialize only a synthetic wire packet, accepting raw bytes for duplicate-field tests."""
    raw=value if type(value) is bytes else p.canonical(value,4*1024*1024)
    return struct.pack('<I',len(raw))+raw


class Gate:
    """Single deterministic lock owner; an entry hook models a completed waiter predecessor."""
    def __init__(self):
        self.held=False;self.before_enter=None

    def __enter__(self):
        callback=self.before_enter;self.before_enter=None
        if callback is not None:callback()
        assert not self.held,'unexpected nested Bridge lock'
        self.held=True
        return self

    def __exit__(self,*unused):
        assert self.held
        self.held=False


class MemoryPipe:
    """Bounded fake handle; never delegates to any operating-system handle."""
    def __init__(self,data):
        self.data=io.BytesIO(data);self.sent=bytearray();self.close_calls=0;self.closed=False
        self.fail_write=False;self.chunk=None;self.close_error=None;self.on_read=None;self.on_write=None

    def read(self,size):
        if self.closed:raise ValueError('closed fake pipe')
        if self.on_read is not None:self.on_read()
        return self.data.read(size)

    def write(self,data):
        if self.closed:raise ValueError('closed fake pipe')
        if self.on_write is not None:self.on_write()
        if self.fail_write:
            self.sent.extend(data[:2]);raise OSError('fake partial write')
        take=len(data) if self.chunk is None else min(len(data),self.chunk)
        self.sent.extend(data[:take]);assert len(self.sent)<=131072
        return take

    def close(self):
        self.close_calls+=1
        if self.close_error is not None:raise self.close_error
        self.closed=True

    def requests(self):
        """Decode complete fake writes with the real strict detached parser."""
        result=[];data=bytes(self.sent)
        while data:
            size=struct.unpack('<I',data[:4])[0];result.append(p.decode(data[4:4+size],65536));data=data[4+size:]
        return result


def bridge(reply=None, *, greeting=None, extra=b''):
    """Execute only the actual isolated Bridge class against fake constructor dependencies."""
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    node=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Bridge')
    pipe=MemoryPipe(packet(hello() if greeting is None else greeting)+packet(enabled() if reply is None else reply)+extra)
    gate=Gate()
    def opened(name,mode,*,buffering):
        assert name=='\\\\.\\pipe\\BetterGI.Agent.inert' and mode=='r+b' and buffering==0
        return pipe
    def clock():
        assert gate.held,'knowledge time outside Bridge lock'
        return 3000
    namespace=dict(os=types.SimpleNamespace(name='nt'),open=opened,re=re,struct=struct,json=json,
        threading=types.SimpleNamespace(Lock=lambda:gate),time=types.SimpleNamespace(perf_counter_ns=clock))
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),'exec'),namespace)
    instance=namespace['Bridge']('BetterGI.Agent.inert')
    return instance,pipe,gate,namespace


class HandshakeTests(unittest.TestCase):
    """Focused changed-seam cases; all evidence and handles are explicitly synthetic."""
    def enable(self,value):
        return value.enable_experimental_step_applications(reviewed_producer_build_sha256=BUILD)

    def refused(self,value,pipe,*,prewrite=False):
        with self.assertRaises((ValueError,RuntimeError,EOFError,OSError,KeyError,TypeError)):
            self.enable(value)
        self.assertIsNone(getattr(value,'_step_application_intake',None))
        self.assertTrue(value._experimental_enable_failed)
        self.assertEqual(pipe.close_calls,1)
        if prewrite:self.assertEqual(pipe.sent,b'')

    def test_complete_reply_installs_once_after_validation(self):
        value,pipe,gate,_=bridge();seen=[]
        pipe.on_read=lambda:seen.append((gate.held,getattr(value,'_step_application_intake',None)))
        intake=self.enable(value)
        self.assertIs(value._step_application_intake,intake)
        self.assertTrue(seen);self.assertTrue(all(held and intake is None for held,intake in seen))
        self.assertEqual(pipe.requests(),[dict(version=1,command='enableStepApplications',sessionId='session',ownerEpoch='owner',goalVersion=1)])
        self.assertFalse(intake.ledger.quarantined);self.assertFalse(intake.ledger.closed_for_submission)
        self.assertIsNone(intake._action);self.assertEqual(intake._ack,0);self.assertEqual(pipe.close_calls,0)
        with self.assertRaises(ValueError):intake.install(value)

    def test_nonzero_tracked_generation_rejects_not_fresh_input(self):
        reply=enabled();reply['stepApplicationConfirmation']['initialTracked']['generation']=7
        value,pipe,_,_=bridge(reply);self.refused(value,pipe)

    def test_partial_writes_keep_exact_five_field_request(self):
        value,pipe,_,_=bridge();pipe.chunk=3;self.enable(value)
        self.assertEqual(set(pipe.requests()[0]),{'version','command','sessionId','ownerEpoch','goalVersion'})

    def test_strict_original_hello_rejects_duplicate_field_before_write(self):
        raw=p.canonical(hello());raw=raw[:-1]+b',"version":1}'
        value,pipe,_,_=bridge(greeting=raw);self.refused(value,pipe,prewrite=True)

    def test_mutated_or_replaced_original_hello_refuses(self):
        for replacement in (False,True):
            with self.subTest(replacement=replacement):
                value,pipe,_,_=bridge()
                if replacement:value.hello=copy.deepcopy(value.hello)
                else:value.hello['sessionId']='other'
                self.refused(value,pipe,prewrite=True)

    def test_foreign_handle_is_never_cleanup_target(self):
        value,owned,_,_=bridge();foreign=MemoryPipe(b'');value.handle=foreign
        self.refused(value,owned,prewrite=True)
        self.assertEqual(foreign.close_calls,0);self.assertEqual(foreign.sent,b'')

    def test_handle_swap_after_write_still_closes_only_owned_handle(self):
        value,owned,_,_=bridge();foreign=MemoryPipe(b'')
        owned.on_write=lambda:setattr(value,'handle',foreign)
        self.refused(value,owned);self.assertEqual(foreign.close_calls,0)

    def test_missing_wrong_capability_or_disabled_input_refuses_prewrite(self):
        changes=[('stepApplicationsAvailable',None),('inputEnabled',False),('goalVersion',True),('version',True)]
        for key,replacement in changes:
            with self.subTest(key=key):
                greeting=hello();greeting[key]=replacement
                value,pipe,_,_=bridge(greeting=greeting);self.refused(value,pipe,prewrite=True)
        for capability in ({'version':1,'mode':v2.MODE},{'version':True,'mode':v2.MODE},{'version':2,'mode':'other'},
                           {'version':2,'mode':v2.MODE,'extra':1}):
            value,pipe,_,_=bridge(greeting={**hello(),'stepApplicationsAvailable':capability})
            self.refused(value,pipe,prewrite=True)

    def test_invalid_reviewed_build_hash_refuses_before_write(self):
        value,pipe,_,_=bridge()
        with self.assertRaises(ValueError):value.enable_experimental_step_applications(reviewed_producer_build_sha256='A'*64)
        self.assertEqual(pipe.sent,b'');self.assertEqual(pipe.close_calls,1)

    def test_confirmation_identity_and_clock_joins(self):
        for key,replacement in [('sessionId','other'),('ownerEpoch','other'),('buildSha256','b'*64),
                ('backendId','other'),('sessionOriginTicks',12346),('clockFrequency',1000),('allowedKeys',['A'])]:
            with self.subTest(key=key):
                reply=enabled();reply['stepApplicationConfirmation']['configuration'][key]=replacement
                value,pipe,_,_=bridge(reply);self.refused(value,pipe)

    def test_confirmation_schema_limits_and_tracking_are_strict(self):
        for kind in ('extra','limits','incomplete','held','typed_generation'):
            with self.subTest(kind=kind):
                reply=enabled();confirmation=reply['stepApplicationConfirmation']
                if kind=='extra':confirmation['extra']=1
                if kind=='limits':confirmation['limits']['recordBytes']=8193
                if kind=='incomplete':confirmation['initialTracked']['complete']=False
                if kind=='held':confirmation['initialTracked']['keys']=['W']
                if kind=='typed_generation':confirmation['initialTracked']['generation']=False
                value,pipe,_,_=bridge(reply);self.refused(value,pipe)

    def test_whole_reply_rejects_startup_close_unknown_or_nonempty_extensions(self):
        for key,replacement in [('closedForSubmission',True),('authorityLost',True),('unpublished',1),
                ('nextReservedSequence',2),('acknowledgedThrough',1),('records',[{}]),('version',True)]:
            with self.subTest(key=key):
                reply=enabled();reply['stepApplications'][key]=replacement
                value,pipe,_,_=bridge(reply);self.refused(value,pipe)
        reply=enabled();reply['stepApplicationTerminals']=[{}]
        value,pipe,_,_=bridge(reply);self.refused(value,pipe)

    def test_missing_extensions_and_extra_header_fields_refuse(self):
        for field in ('stepApplications','stepApplicationTerminals'):
            reply=enabled();del reply[field]
            value,pipe,_,_=bridge(reply);self.refused(value,pipe)
        reply=enabled();reply['extra']=0
        value,pipe,_,_=bridge(reply);self.refused(value,pipe)

    def test_strict_reply_rejects_duplicate_top_level_and_nested_fields(self):
        raw=p.canonical(enabled())
        for invalid in (raw[:-1]+b',"type":"stepApplicationsEnabled"}',
                        raw.replace(b'"version":2',b'"version":2,"version":2',1)):
            value,pipe,_,_=bridge(invalid);self.refused(value,pipe)

    def test_enable_never_reads_an_image_payload(self):
        reply=enabled();reply['payloadBytes']=32*1024*1024
        value,pipe,_,_=bridge(reply,extra=b'untouched_image_body');self.refused(value,pipe)
        self.assertEqual(pipe.data.read(),b'untouched_image_body')

    def test_bad_json_nan_elapsed_or_rejected_reply_closes(self):
        for reply in (b'{',b'{"serverNowMs":NaN}',{'type':'rejected','reason':'not_ready'},
                      {**enabled(),'serverNowMs':True},{**enabled(),'serverNowMs':-1}):
            value,pipe,_,_=bridge(reply);self.refused(value,pipe)

    def test_partial_write_failure_never_retries_or_installs(self):
        value,pipe,_,_=bridge();pipe.fail_write=True;self.refused(value,pipe)
        sent=bytes(pipe.sent)
        with self.assertRaises(RuntimeError):self.enable(value)
        with self.assertRaises(RuntimeError):value.request('status')
        self.assertEqual(bytes(pipe.sent),sent);self.assertEqual(pipe.close_calls,1)

    def test_missing_reply_never_retries(self):
        value,pipe,_,_=bridge();pipe.data=io.BytesIO(b'');self.refused(value,pipe)
        self.assertEqual(len(pipe.requests()),1)

    def test_header_bounds_fail_before_unbounded_read(self):
        for length in (0,4*1024*1024+1):
            value,pipe,_,_=bridge();pipe.data=io.BytesIO(struct.pack('<I',length))
            self.refused(value,pipe)

    def test_hello_mutation_during_reply_cannot_publish_an_intake(self):
        value,pipe,_,_=bridge()
        pipe.on_read=lambda:value.hello.update(ownerEpoch='mutated')
        self.refused(value,pipe)

    def test_bad_knowledge_clock_fails_whole_intake_before_install(self):
        value,pipe,_,namespace=bridge()
        namespace['time']=types.SimpleNamespace(perf_counter_ns=lambda:-1)
        self.refused(value,pipe)

    def test_repeat_after_success_closes_and_quarantines_original(self):
        value,pipe,_,_=bridge();intake=self.enable(value);sent=bytes(pipe.sent)
        with self.assertRaises(RuntimeError):self.enable(value)
        self.assertTrue(intake.ledger.quarantined);self.assertEqual(pipe.close_calls,1)
        self.assertEqual(pipe.sent,sent)

    def test_close_failure_preserves_original_negotiation_error(self):
        value,pipe,_,_=bridge({'type':'rejected'});cleanup=OSError('fake close');pipe.close_error=cleanup
        with self.assertRaises(ValueError) as caught:self.enable(value)
        self.assertIs(caught.exception,value._experimental_enable_error)
        self.assertIs(value._experimental_enable_close_error,cleanup);self.assertEqual(pipe.close_calls,1)
        self.assertTrue(any('close failed' in note for note in caught.exception.__notes__))

    def test_request_selects_intake_only_after_waiting_for_negotiation_lock(self):
        status=dict(type='status',stepApplications=enabled()['stepApplications'],stepApplicationTerminals=[])
        value,pipe,gate,_=bridge(extra=packet(status))
        gate.before_enter=lambda:self.enable(value)
        reply,pixels=value.request('status')
        self.assertEqual(reply,status);self.assertEqual(pixels,b'')
        first,second=pipe.requests();self.assertEqual(first['command'],'enableStepApplications')
        self.assertEqual(second['command'],'status');self.assertIn('stepApplicationsAck',second)
        self.assertIsNotNone(value._step_application_intake)

    def test_raw_hello_is_not_overwritten_by_later_status(self):
        value,pipe,_,_=bridge();original=value._hello_raw;value.request('status')
        self.assertEqual(value._hello_raw,original);self.assertEqual(len(pipe.requests()),1)

    def test_normal_legacy_request_and_duplicate_parsing_remain_unchanged(self):
        value,pipe,_,_=bridge(b'{"type":"status","x":1,"x":2}')
        reply,pixels=value.request('status')
        self.assertEqual(reply,dict(type='status',x=2));self.assertEqual(pixels,b'')
        self.assertEqual(pipe.requests(),[dict(version=1,command='status',sessionId='session',ownerEpoch='owner',goalVersion=1)])
        self.assertIsNone(getattr(value,'_step_application_intake',None))

    def test_existing_prewrite_action_failure_keeps_known_not_submitted(self):
        for invalid in (object(),'x'*65536):
            out,intake,wire,token=old.transaction();value=old.bridge({},intake)
            with self.assertRaises((ValueError,TypeError)):value.request('action',bad=invalid)
            self.assertEqual(value.handle.sent,b'');self.assertIsNone(intake._action)
            disposition=intake.submission_disposition('request',token)
            self.assertEqual(disposition.status,'known_not_submitted');self.assertFalse(disposition.write_attempted)

    def test_existing_partial_write_action_failure_stays_unknown(self):
        out,intake,wire,token=old.transaction();value=old.bridge({},intake,fail_write=True)
        with self.assertRaises(OSError):old.call(value,wire)
        self.assertTrue(value.handle.sent);self.assertTrue(intake.ledger.quarantined)
        self.assertEqual(intake.submission_disposition('request',token).status,'unknown')

    def test_no_normal_entrypoint_calls_experimental_enable(self):
        tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
        calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and
               isinstance(node.func,ast.Attribute) and node.func.attr=='enable_experimental_step_applications']
        self.assertEqual(calls,[])


if __name__=='__main__':
    unittest.main()
