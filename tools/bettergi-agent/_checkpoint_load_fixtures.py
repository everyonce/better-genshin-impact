"""In-memory APIs and actual AST-selected constructor/loader; no numerical/native import."""
import ast
import builtins
import hashlib
import io
from pathlib import Path
import stat
from types import SimpleNamespace as NS

import checkpoint_load_scope as c

HERE = Path(__file__).resolve().parent
CHECKPOINT = 'D:/fixture/checkpoint.ckpt'
SOURCE = 'D:/fixture/source'
CONFIG_BYTES = b'pinned configuration bytes\n'
MANIFEST = {'precision':'float16', 'upstream':SOURCE, 'changes':[]}


class Stream(io.BytesIO):
    """Track stream identity, bounded reads, close attempts and partial failures."""
    def __init__(self, api, data):
        super().__init__(data); self.api=api; self.read_sizes=[]; self.closes=0

    def readinto(self, view):
        self.api.step('read'); self.read_sizes.append(len(view))
        return super().readinto(view)

    def seek(self, *args):
        self.api.step('seek'); return super().seek(*args)

    def close(self):
        self.closes+=1; self.api.step('close_stream'); super().close()

    def __del__(self):
        """Inert handles have no OS resource; avoid destructor retries obscuring explicit counts."""
        pass


class Api:
    """Own exactly one fake raw handle, descriptor or stream, with injectable stage failures."""
    def __init__(self, data=b'checkpoint', failure=None):
        self.data=data; self.failure=failure; self.events=[]; self.stream=None
        self.size=len(data); self.mode=stat.S_IFREG; self.closed_raw=[]; self.closed_fds=[]
        self.extra_failure=None

    def step(self, name):
        self.events.append(name)
        if name in (self.failure, self.extra_failure):raise OSError(name)

    def open_handle(self, path):
        self.step('open'); self.path=path; return 17

    def to_fd(self, handle):
        assert handle==17; self.step('transfer'); return 29

    def binary(self, fd):
        assert fd==29; self.step('binary')

    def to_stream(self, fd):
        assert fd==29; self.step('stream'); self.stream=Stream(self,self.data); return self.stream

    def info(self, stream):
        assert stream is self.stream; self.step('info'); return NS(st_size=self.size,st_mode=self.mode)

    def close_handle(self, handle):
        self.closed_raw.append(handle); self.step('close_handle')

    def close_fd(self, fd):
        self.closed_fds.append(fd); self.step('close_fd')


def scope(api, **kwargs):
    """Construct inert provenance inputs; no historical actual checkpoint is opened."""
    values=dict(checkpoint=CHECKPOINT, size=len(api.data), sha256=hashlib.sha256(api.data).hexdigest(),
                source=SOURCE, config_sha256=hashlib.sha256(CONFIG_BYTES).hexdigest(),
                compatibility_sha256=hashlib.sha256(c.canonical(MANIFEST)).hexdigest(),
                deadline=100, clock=lambda:1, inert=True, api=api)
    values.update(kwargs)
    return c.CheckpointLoadScope(**values)


class Harness:
    """Execute complete actual function ASTs with source-shaped inert imports and file nodes."""
    def __init__(self, api, load_scope=None, failure=None, legacy=False):
        self.api, self.scope, self.failure = api, load_scope, failure
        self.loads=[]; self.strict=[]; self.lifecycle=[]; self.model=None
        h=self
        class Dtype:
            def __str__(self):return 'torch.float16'
        class Edge:
            def to(self, value):return self
        class BaseModel:
            def __init__(self, config, *args, **kwargs):
                h.model=self; h.lifecycle.append('model_init')
                if h.failure=='model_init':raise LookupError('model_init')
                self.action_mapping=NS(_mouse_delta_x_edges=Edge(),_mouse_delta_y_edges=Edge())
                self.bc_transformer=NS(action_decoder=NS(_setup_kv_cache_state=lambda:h.lifecycle.append('decoder_cache')),
                                       setup_kv_cache=lambda *a,**k:h.lifecycle.append('temporal_cache'))
            def load_state_dict(self, state, *, strict):
                h.strict.append((self,state,strict)); h.lifecycle.append('strict')
                if h.failure=='strict':raise LookupError('strict')
                assert state=={'weight':'actual-from-stream'} and strict is True
            def to(self, **kwargs):
                h.lifecycle.append('to')
                if h.failure=='to':raise LookupError('to')
                return self
            def eval(self):h.lifecycle.append('eval');return self
            def parameters(self):return [NS(numel=lambda:1)]
        def load(stream, **kwargs):
            h.loads.append((stream,kwargs));h.lifecycle.append('torch_load')
            if h.failure=='torch_load':raise LookupError('torch_load')
            if not legacy:
                assert stream is api.stream and stream.tell()==0 and not stream.closed
                assert stream.read()==api.data
            return {'state_dict':{'weight':'actual-from-stream'}}
        h.torch=NS(nn=NS(),float16=Dtype(),device=lambda name:name,load=load)
        def config(data):
            return NS(shared=NS(n_seq_timesteps=data['shared']['n_seq_timesteps']),
                      policy_model=NS(n_transformer_layers=10,attention_history_len=data['policy_model']['attention_history_len'],top_p=1),
                      inference=NS(mouse_sampling_approach='mean'))
        def yaml_load(raw):
            assert raw==CONFIG_BYTES.decode()
            return {'shared':{},'policy_model':{'n_transformer_layers':10}}
        stage = ('class PolicyModelTrainer:\n'
                 '    def _init_action_mapping(self): pass\n'
                 '    def _keyboard_mouse_action_sampler(self): pass\n'
                 '    def online_kv_cache_predict(self): pass\n'
                 '    def action_in_to_tokens(self): pass\n')
        class FakePath:
            def __init__(self, path):self.path=str(path)
            def __truediv__(self, other):return FakePath(self.path+'/'+other)
            def __str__(self):return self.path
            def read_text(self, **kwargs):return stage if self.path.endswith('stage3_finetune.py') else CONFIG_BYTES.decode()
            def read_bytes(self):return CONFIG_BYTES
        modules={
            'torch':h.torch,'yaml':NS(safe_load=yaml_load),
            'elefant.policy_model.model_free':NS(ModelFreePolicy=BaseModel),
            'elefant.policy_model.config':NS(LightningPolicyConfig=NS(model_validate=config)),
            'elefant.policy_model.kv_cache':NS(KVCacheState=object),
            'elefant.data.action_mapping':NS(StructuredAction=object),
            'elefant.torch':NS(eager_assert=object(),_sample_from_logits_gpu=object()),
            'p2p_rotary':NS(restore_rotary_precision=lambda model:h.lifecycle.append('rotary')),
            'observation_profiles':NS(validate_model_profile=lambda value,model:value,
                p2p_preprocessing=lambda value:{'observationProfile':value}),
            'p2p_action_codec':NS(resolve_mouse_sampling=lambda checkpoint,override,fallback:
                (override if override else fallback,'explicit-override' if override else 'upstream-config-fallback'))}
        original=builtins.__import__
        def imports(name,*args,**kwargs):
            if name in modules:return modules[name]
            return original(name,*args,**kwargs)
        env=dict(__builtins__={**vars(builtins),'__import__':imports},ast=ast,Path=FakePath,
                 sys=NS(path=[]),prepare_source=lambda *args:MANIFEST,torch=h.torch)
        tree=ast.parse((HERE/'p2p_loader.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='load_model')
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual:p2p_loader.py','exec'),env)
        modules['p2p_loader']=NS(load_model=env['load_model'])
        tree=ast.parse((HERE/'model_adapters.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='OpenP2PAdapter')
        cls.body=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__']
        exec(compile(ast.Module(body=[cls],type_ignores=[]),'actual:model_adapters.py','exec'),env)
        self.adapter_type=env['OpenP2PAdapter']
        def reset(adapter):
            h.lifecycle.append('reset')
            if not legacy:assert api.stream is not None and not api.stream.closed
            if h.failure=='reset':raise LookupError('reset')
        def set_goal(adapter, path):
            h.lifecycle.append('goal')
            if not legacy:assert not api.stream.closed
            if h.failure=='goal':raise LookupError('goal')
        self.adapter_type.reset=reset;self.adapter_type.set_goal=set_goal
        self.adapter=self.adapter_type.__new__(self.adapter_type)

    def construct(self, **kwargs):
        """Call the real optional constructor and loader body, retaining outer partial ownership."""
        values=dict(checkpoint=CHECKPOINT,source=SOURCE,cache_root='D:/fixture/cache',history=41,
                    dtype='float16',cuda_graph=False,fast_start=False,execution_feedback=False,
                    p2p_mouse_sampling='truncated_normal',observation_profile=c.PROFILE,
                    goal_embedding='D:/fixture/goal.json',checkpoint_scope=self.scope)
        values.update(kwargs)
        self.adapter_type.__init__(self.adapter,**values)
        return self.adapter


def contract(scope):
    """Return the unchanged owner's three-field declared model contract for receipt admission."""
    return dict(checkpointSha256=scope.sha256,profile=c.PROFILE,mapping=c.MAPPING)
