"""Actual loader/constructor ASTs plus inert owned-stream, admission and inverse regressions."""
import ast
import copy
import dataclasses
import hashlib
import json
from pathlib import Path
import stat
from types import SimpleNamespace as NS
import unittest

import checkpoint_load_scope as c
from _checkpoint_load_fixtures import Api, Harness, scope, contract, CHECKPOINT, SOURCE

HERE = Path(__file__).resolve().parent


class LoadCases(unittest.TestCase):
    """Exercise actual optional constructor/loader ordering using one in-memory stream."""
    def success(self, **kwargs):
        api=Api();s=scope(api);h=Harness(api,s);a=h.construct(**kwargs)
        return api,s,h,a

    def test_same_stream_strict_and_close_after_complete_adapter(self):
        api,s,h,a=self.success()
        self.assertIs(h.loads[0][0],api.stream)
        self.assertEqual(h.loads[0][1],dict(map_location='cpu',weights_only=True,mmap=False))
        self.assertEqual(h.lifecycle,['model_init','torch_load','strict','to','eval','rotary','decoder_cache','temporal_cache','reset','goal'])
        self.assertEqual(api.events.count('open'),1);self.assertEqual(api.stream.closes,1)
        self.assertTrue(api.stream.closed);self.assertEqual(api.closed_raw,[]);self.assertEqual(api.closed_fds,[])
        receipt=s.receipt_for(a,contract(s));self.assertIs(receipt.model,h.model)
        self.assertTrue(a.metadata['checkpointLoad']['verifiedLoad'])

    def test_legacy_omitted_scope_keeps_original_load_kwargs(self):
        api=Api();h=Harness(api,legacy=True);a=h.construct()
        self.assertEqual(h.loads,[(CHECKPOINT,dict(map_location='cpu',weights_only=True))])
        self.assertEqual(api.events,[]);self.assertNotIn('checkpointLoad',a.metadata)

    def test_default_runtime_barrier_before_api(self):
        api=Api()
        with self.assertRaisesRegex(ValueError,'activation_unavailable'):scope(api,inert=False)
        self.assertEqual(api.events,[])

    def test_multichunk_buffer_bound_and_eof(self):
        api=Api(b'a'*(c.BUFFER_BYTES+17));s=scope(api);Harness(api,s).construct()
        self.assertEqual(api.stream.read_sizes,[c.BUFFER_BYTES,17,1])

    def test_wrong_digest_never_calls_torch(self):
        api=Api();s=scope(api,sha256='0'*64);h=Harness(api,s)
        with self.assertRaisesRegex(ValueError,'checkpoint_hash'):h.construct()
        self.assertEqual(h.loads,[]);self.assertTrue(api.stream.closed);self.assertIsNone(s._receipt)

    def test_wrong_declared_size(self):
        api=Api();s=scope(api,size=len(api.data)+1);h=Harness(api,s)
        with self.assertRaisesRegex(ValueError,'opened_file_shape'):h.construct()
        self.assertEqual(h.loads,[]);self.assertEqual(api.stream.closes,1)

    def test_nonregular_opened_object(self):
        api=Api();api.mode=stat.S_IFDIR;s=scope(api);h=Harness(api,s)
        with self.assertRaisesRegex(ValueError,'opened_file_shape'):h.construct()
        self.assertEqual(h.loads,[])

    def test_short_data_despite_size_metadata(self):
        api=Api();api.size+=1;s=scope(api,size=api.size);h=Harness(api,s)
        with self.assertRaisesRegex(ValueError,'checkpoint_short_read'):h.construct()
        self.assertEqual(h.loads,[])

    def test_extra_data_despite_size_metadata(self):
        api=Api();api.size-=1;s=scope(api,size=api.size);h=Harness(api,s)
        with self.assertRaisesRegex(ValueError,'checkpoint_extra_bytes'):h.construct()
        self.assertEqual(h.loads,[])

    def test_wrong_config_or_compatibility_rejects_before_model(self):
        for field in ('config_sha256','compatibility_sha256'):
            with self.subTest(field=field):
                api=Api();s=scope(api,**{field:'0'*64});h=Harness(api,s)
                with self.assertRaises(ValueError):h.construct()
                self.assertIsNone(s._model);self.assertEqual(api.events,[])

    def test_partial_model_initializer_retained(self):
        api=Api();s=scope(api);h=Harness(api,s,failure='model_init')
        with self.assertRaisesRegex(LookupError,'model_init'):h.construct()
        self.assertIs(s._model,h.model);self.assertIs(s._adapter,h.adapter)
        self.assertIsNone(s._receipt);self.assertEqual(api.events,[])

    def test_partial_post_load_constructor_stages_retained(self):
        for stage in ('torch_load','strict','to','reset','goal'):
            with self.subTest(stage=stage):
                api=Api();s=scope(api);h=Harness(api,s,failure=stage)
                with self.assertRaisesRegex(LookupError,stage):h.construct()
                self.assertIs(s._model,h.model);self.assertIs(s._adapter,h.adapter)
                self.assertIsNone(s._receipt);self.assertEqual(api.stream.closes,1)
                self.assertEqual(s.status()['primaryError'],'LookupError')

    def test_expired_deadline_before_native_open(self):
        api=Api();s=scope(api,clock=lambda:101);h=Harness(api,s)
        with self.assertRaisesRegex(ValueError,'deadline_expired'):h.construct()
        self.assertEqual(api.events,[]);self.assertIs(s._adapter,h.adapter)

    def test_deadline_expires_during_hash(self):
        api=Api(b'x'*(c.BUFFER_BYTES+1));ticks=iter([1,1,1,1,101])
        s=scope(api,clock=lambda:next(ticks));h=Harness(api,s)
        with self.assertRaisesRegex(ValueError,'deadline_expired'):h.construct()
        self.assertEqual(h.loads,[]);self.assertEqual(api.stream.closes,1)

    def test_requested_options_fail_before_model(self):
        for values in ({'history':True},{'history':42},{'dtype':'float32'},{'cuda_graph':True},
                       {'fast_start':True},{'execution_feedback':True},{'p2p_mouse_sampling':None},
                       {'observation_profile':'legacy-area-640x360-v1'}):
            with self.subTest(values=values):
                api=Api();s=scope(api);h=Harness(api,s)
                with self.assertRaisesRegex(ValueError,'requested_native_profile'):h.construct(**values)
                self.assertEqual(api.events,[]);self.assertIsNone(s._receipt)

    def test_wrong_source_or_checkpoint_no_fallback(self):
        for values in ({'source':'D:/other/source'},{'checkpoint':'D:/other/checkpoint'}):
            with self.subTest(values=values):
                api=Api();s=scope(api);h=Harness(api,s)
                with self.assertRaises(ValueError):h.construct(**values)
                self.assertEqual(api.events,[])

    def test_local_path_only(self):
        for path in ('relative.ckpt','\\\\server\\share\\checkpoint','\\\\?\\D:\\checkpoint'):
            with self.subTest(path=path),self.assertRaises(ValueError):scope(Api(),checkpoint=path)


class CleanupCases(unittest.TestCase):
    """Every ownership transfer failure closes only its current layer, once."""
    def test_open_failure_no_close(self):
        api=Api(failure='open');s=scope(api);h=Harness(api,s)
        with self.assertRaisesRegex(OSError,'open'):h.construct()
        self.assertEqual(api.events,['open']);self.assertIsNone(s._receipt)

    def test_transfer_failure_closes_raw_only(self):
        api=Api(failure='transfer');s=scope(api);h=Harness(api,s)
        with self.assertRaisesRegex(OSError,'transfer'):h.construct()
        self.assertEqual(api.closed_raw,[17]);self.assertEqual(api.closed_fds,[])

    def test_binary_or_stream_failure_closes_fd_only(self):
        for stage in ('binary','stream'):
            with self.subTest(stage=stage):
                api=Api(failure=stage);s=scope(api);h=Harness(api,s)
                with self.assertRaisesRegex(OSError,stage):h.construct()
                self.assertEqual(api.closed_raw,[]);self.assertEqual(api.closed_fds,[29])

    def test_info_read_seek_failure_closes_stream_only(self):
        for stage in ('info','read','seek'):
            with self.subTest(stage=stage):
                api=Api(failure=stage);s=scope(api);h=Harness(api,s)
                with self.assertRaisesRegex(OSError,stage):h.construct()
                self.assertEqual(api.closed_raw,[]);self.assertEqual(api.closed_fds,[])
                self.assertEqual(api.stream.closes,1)

    def test_close_failure_no_receipt_no_second_attempt(self):
        api=Api(failure='close_stream');s=scope(api);h=Harness(api,s)
        with self.assertRaisesRegex(OSError,'close_stream'):h.construct()
        self.assertEqual(api.stream.closes,1);self.assertIs(s._stream,api.stream)
        self.assertIsNone(s._receipt);self.assertNotIn('checkpointLoad',h.adapter.metadata)

    def test_primary_and_cleanup_errors_are_separate(self):
        api=Api(failure='close_stream');s=scope(api);h=Harness(api,s,failure='strict')
        with self.assertRaisesRegex(LookupError,'strict') as caught:h.construct()
        self.assertIs(s._primary,caught.exception);self.assertIsInstance(s._cleanup,OSError)
        self.assertEqual(api.stream.closes,1);self.assertIn('checkpoint cleanup failed: OSError',caught.exception.__notes__)
        self.assertIs(s._model,h.model);self.assertIsNone(s._receipt)

    def test_failed_raw_or_fd_close_retains_current_owner(self):
        for stage,close,owner in [('transfer','close_handle','handle'),('binary','close_fd','fd')]:
            with self.subTest(stage=stage):
                api=Api(failure=stage);api.extra_failure=close;s=scope(api);h=Harness(api,s)
                with self.assertRaisesRegex(OSError,stage):h.construct()
                self.assertEqual(s.status()['ownerRetained'],owner)
                self.assertIsInstance(s._cleanup,OSError)


class ReceiptCases(unittest.TestCase):
    """Receipt/model/profile and frozen owner admission; detached metadata cannot confer authority."""
    def fixture(self):
        api=Api();s=scope(api);h=Harness(api,s);a=h.construct();return api,s,h,a

    def test_metadata_detached_and_receipt_frozen(self):
        api,s,h,a=self.fixture();r=s.receipt_for(a,contract(s));out=r.metadata();out['checkpointSha256']='f'*64
        self.assertEqual(r.checkpoint_sha256,s.sha256)
        with self.assertRaises(dataclasses.FrozenInstanceError):r.model=object()
        self.assertLess(len(c.canonical(r.metadata())),c.METADATA_BYTES)

    def test_wrong_adapter_model_config_identity(self):
        for field in ('adapter','model','config'):
            with self.subTest(field=field):
                api,s,h,a=self.fixture()
                target=copy.copy(a) if field=='adapter' else a
                if field!='adapter':setattr(a,field,object())
                with self.assertRaises(ValueError):s.receipt_for(target,contract(s))

    def test_wrong_contract_hash_profile_mapping(self):
        api,s,h,a=self.fixture()
        for field,value in [('checkpointSha256','a'*64),('profile','legacy'),('mapping','wrong')]:
            value_contract=contract(s);value_contract[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):s.receipt_for(a,value_contract)

    def test_actual_resolved_options_mutation_rejected(self):
        for field,value in [('mouse_sampling','mean'),('observation_profile','legacy'),
                            ('use_cuda_graph',True),('graph',object()),('dtype','float32')]:
            with self.subTest(field=field):
                api,s,h,a=self.fixture();setattr(a,field,value)
                with self.assertRaises(ValueError):s.receipt_for(a,contract(s))

    def test_actual_config_manifest_mutation_rejected(self):
        api,s,h,a=self.fixture();a.config.policy_model.n_transformer_layers=0;a.config.policy_model.attention_history_len=[]
        with self.assertRaises(ValueError):s.receipt_for(a,contract(s))
        api,s,h,a=self.fixture();a.metadata['compatibility']=dict(changed=True)
        with self.assertRaises(ValueError):s.receipt_for(a,contract(s))

    def test_fake_metadata_without_receipt_is_rejected(self):
        api=Api();s=scope(api);a=NS(metadata={'checkpointLoad':{'verifiedLoad':True}})
        with self.assertRaisesRegex(ValueError,'receipt_unavailable'):s.receipt_for(a,contract(s))

    def test_scope_is_single_use(self):
        api,s,h,a=self.fixture()
        with self.assertRaisesRegex(ValueError,'scope_single_use'):h.construct()
        self.assertEqual(api.events.count('open'),1);self.assertIsNone(s._receipt)

    def test_actual_frozen_coordinator_admission(self):
        from step_application_history_owner import StepApplicationHistoryOwner
        from step_application_transport import StepApplicationIntake
        from step_application_ledger import Outbox
        import step_application_protocol as p
        api,s,h,a=self.fixture()
        runtime=NS(qualify=lambda a:None,guard=lambda a:('inert',))
        owner=StepApplicationHistoryOwner(a,runtime,inert=True)
        cfg=dict(version=1,mode=p.MODE,sessionId='session',ownerEpoch='owner',channelId='channel',backendId='win32-sendinput',
                 backendEpoch='backend',buildSha256='a'*64,clockKind='windows_qpc',sessionOriginTicks=1000,clockFrequency=1000,
                 allowedKeys=sorted(p.ALLOWED-{'SHIFT','CONTROL','ESC'}))
        out=Outbox();intake=StepApplicationIntake(cfg,out.enable(cfg,dict(keys=[],generation=0,complete=True),idle=True))
        bridge=NS(_step_application_intake=intake,handle=object(),hello=dict(sessionId='session',ownerEpoch='owner',goalVersion=1))
        with self.assertRaisesRegex(ValueError,'activation_unavailable'):c.bind_loaded_owner(s,owner,bridge,intake,contract(s))
        bad=contract(s);bad['checkpointSha256']='0'*64
        with self.assertRaises(ValueError):c.bind_loaded_owner(s,owner,bridge,intake,bad,inert=True)
        self.assertIsNone(owner._channel)
        binding=c.bind_loaded_owner(s,owner,bridge,intake,contract(s),inert=True)
        self.assertIs(binding._checkpoint_load_receipt,s._receipt);self.assertIs(owner._channel,intake)


class SourceCases(unittest.TestCase):
    """Pin native-call arguments and prove the two optional seams reverse to complete preimages."""
    def test_windows_api_exact_source_without_execution(self):
        tree=ast.parse((HERE/'checkpoint_load_scope.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='_WindowsReadApi')
        fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='open_handle')
        call=next(n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='CreateFile')
        self.assertEqual([ast.literal_eval(n) for n in call.args[1:]],[0x80000000,1,0,3,0x80,0])
        self.assertEqual(len(call.keywords),0)
        self.assertNotIn('ctypes',ast.unparse(cls))

    def test_non_target_adapter_and_loader_functions_unchanged(self):
        for name,changed in [('p2p_loader.py',{'load_model'}),('model_adapters.py',{'OpenP2PAdapter.__init__'})]:
            def methods(path):
                rows={};tree=ast.parse(path.read_text(encoding='utf-8'))
                for node in tree.body:
                    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):rows[node.name]=ast.dump(node)
                    elif isinstance(node,ast.ClassDef):
                        for fn in node.body:
                            if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):rows[node.name+'.'+fn.name]=ast.dump(fn)
                return rows
            old,new=methods(HERE/'step_application_testdata/preimages'/name),methods(HERE/name)
            self.assertEqual(set(old),set(new))
            for key in old.keys()-changed:self.assertEqual(old[key],new[key],key)

    def test_bounded_receipt_and_error_metadata_witness(self):
        api=Api();s=scope(api,size=4*1024**3)
        # Size metadata alone has no receipt: only the inert successful small file is admitted.
        self.assertFalse(s.status()['receiptAvailable'])
        api=Api();s=scope(api);h=Harness(api,s);a=h.construct();r=s.receipt_for(a,contract(s))
        maximum=dataclasses.replace(r,checkpoint_bytes=4*1024**3,
            checkpoint_sha256='f'*64,config_sha256='f'*64,compatibility_sha256='f'*64)
        metadata=maximum.metadata();raw=c.canonical(metadata)
        failure=dict(s.status(),phase='failed',primaryError='E'*64,cleanupError='E'*64,
                     ownerRetained='stream',receiptAvailable=False)
        failure_raw=c.canonical(failure)
        self.assertLessEqual(len(raw),c.METADATA_BYTES);self.assertLessEqual(len(failure_raw),c.METADATA_BYTES)
        out=globals().get('CAPACITY_OUTPUT')
        if out is not None:
            out.mkdir(exist_ok=False)
            (out/'receipt-maximum.json').write_bytes(raw)
            (out/'failure-maximum.json').write_bytes(failure_raw)
            (out/'capacity.json').write_text(json.dumps(dict(schema='checkpoint-load-metadata-capacity-v1',
                successfulMetadataBytes=len(raw),failureMetadataBytes=len(failure_raw),perExportLimit=c.METADATA_BYTES,
                hashBufferBytes=c.BUFFER_BYTES,wholeCheckpointBuffer=False,totalProcessMemoryBoundedByThis=False,
                excluded=['CPU checkpoint tensors','model/CUDA allocations','source config/manifest objects',
                          'Python object overhead','torch serialization scratch','retained failure traceback']),indent=2)+'\n',encoding='utf-8')


class ReceiptJoinCases(unittest.TestCase):
    """Completed receipts remain authority after ordinary scope-field reassignment."""
    fixture = ReceiptCases.fixture

    def reject_changed(self, field, value, *, rewrite_manifest=False):
        """Keep the real successful inert load and require rejection before any new owner admission."""
        api,s,h,a=self.fixture();receipt=s._receipt;events=list(api.events)
        if rewrite_manifest:
            a.metadata['compatibility']={'changed':True}
            value=hashlib.sha256(c.canonical(a.metadata['compatibility'])).hexdigest()
        setattr(s,field,value)
        with self.assertRaisesRegex(ValueError,'receipt_scope_binding_changed'):
            s.receipt_for(a,contract(s))
        self.assertIs(s._receipt,receipt);self.assertEqual(api.events,events)
        self.assertEqual(s._phase,'complete');self.assertEqual(api.stream.closes,1)

    def test_checkpoint_hash_reassignment_cannot_replace_receipt(self):
        self.reject_changed('sha256','f'*64)

    def test_checkpoint_size_or_equal_float_reassignment_rejected(self):
        for value in (11,10.0):
            with self.subTest(value=value):self.reject_changed('size',value)

    def test_source_reassignment_rejected(self):
        self.reject_changed('source','d:/other/source')

    def test_config_hash_reassignment_rejected(self):
        self.reject_changed('config_sha256','f'*64)

    def test_manifest_and_expected_hash_reassignment_rejected(self):
        # The mutable returned manifest and expected hash agree; the original receipt still must win.
        self.reject_changed('compatibility_sha256',None,rewrite_manifest=True)

    def test_inert_status_or_equal_integer_reassignment_rejected(self):
        for value in (False,1):
            with self.subTest(value=value):self.reject_changed('_inert',value)

    def test_mutated_hash_cannot_reach_coordinator_attach(self):
        api,s,h,a=self.fixture();owner=NS(_adapter=a,_channel=None);s.sha256='e'*64
        with self.assertRaisesRegex(ValueError,'receipt_scope_binding_changed'):
            c.bind_loaded_owner(s,owner,object(),object(),contract(s),inert=True)
        self.assertIsNone(owner._channel);self.assertEqual(len(h.loads),1);self.assertEqual(len(h.strict),1)

    def test_unchanged_receipt_and_detached_admission_contract(self):
        import step_application_native_binding as binding_module
        api,s,h,a=self.fixture();receipt=s._receipt;supplied=contract(s);events=list(api.events)
        self.assertIs(s.receipt_for(a,supplied),receipt)
        received=[];original=binding_module.StepApplicationNativeBinding
        def construction(owner,bridge,intake,admitted,*,inert):
            received.append(admitted);return NS()
        binding_module.StepApplicationNativeBinding=construction
        try:bound=c.bind_loaded_owner(s,NS(_adapter=a),object(),object(),supplied,inert=True)
        finally:binding_module.StepApplicationNativeBinding=original
        self.assertIs(bound._checkpoint_load_receipt,receipt)
        self.assertEqual(received,[supplied]);self.assertIsNot(received[0],supplied)
        supplied['checkpointSha256']='f'*64
        self.assertEqual(received[0]['checkpointSha256'],receipt.checkpoint_sha256)
        self.assertEqual(api.events,events);self.assertEqual(len(h.loads),1);self.assertEqual(len(h.strict),1)
