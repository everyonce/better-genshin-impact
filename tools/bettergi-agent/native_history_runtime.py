"""Deferred real-Torch operations; importing this file never imports numerical packages.

No executable harness is supplied. A later root-owned worker must supply the exact
loaded modules and independently exclude other default-generator consumers.
"""
import hashlib
import json
from pathlib import Path
import threading
import types
import cache_descriptors
from native_history_feedback import require, GRAPH_FIELDS

ADAPTER_SHA='7cfea2f95b94bebc0b3f8743dd3ba8cdab270a37eb31639af4243f37a6a6c7f2'
_GENERATOR_LOCK=threading.Lock()
_GENERATOR_OWNER=None


class TorchRuntime:
    """Concrete copies/RNG/drain operations with exact adapter and cache admission."""
    def __init__(self,torch,adapter_module,cache_module,transformer_module,policy_module,*,exclusive_process_rng):
        require(exclusive_process_rng is True,'exclusive_process_rng_required')
        self.torch=torch;self.adapter_module=adapter_module;self.cache_module=cache_module
        self.transformer_module=transformer_module;self.policy_module=policy_module
        self.device=torch.device('cuda',torch.cuda.current_device())

    def qualify(self,a):
        """Only the copied native adapter, original methods and narrowly qualified descriptors."""
        module=self.adapter_module;source=Path(module.__file__).resolve()
        require(source==Path(__file__).resolve().with_name('model_adapters.py')
            and hashlib.sha256(source.read_bytes()).hexdigest()==ADAPTER_SHA,'copied_adapter_source')
        require(type(a) is module.OpenP2PAdapter and module.torch is self.torch,'adapter_class_namespace')
        require(a.execution_feedback is False and a.temporal_cache is None and a._pending_feedback is False,
            'native_feedback_wrapper_only')
        code=compile(source.read_bytes(),str(source),'exec',dont_inherit=True)
        cls=next(n for n in code.co_consts if isinstance(n,types.CodeType) and n.co_name=='OpenP2PAdapter')
        for name in ('predict','_forward','_prepare_graph','reset','set_goal','_begin_history_transaction','finish_action'):
            method=getattr(type(a),name)
            expected=next(n for n in cls.co_consts if isinstance(n,types.CodeType) and n.co_name==name)
            require(name not in vars(a) and method.__code__==expected and method.__globals__ is vars(module),
                'adapter_method:'+name)
        require(a.dtype==self.torch.float16 and type(a.config.shared.n_seq_timesteps) is int
            and a.config.shared.n_seq_timesteps==41 and type(a.use_cuda_graph) is bool,'native_history41_fp16')
        self.qualification=cache_descriptors.qualify_model(a.model,self.torch,self.cache_module,
            self.transformer_module,self.policy_module)
        self.validate_history(a);self.guard(a)

    def guard(self,a):
        """Stable source/mode/storage metadata; no model call or tensor-value inspection."""
        t=self.torch
        require(t.get_default_dtype()==t.float32 and str(t.get_default_device())=='cpu'
            and not t.is_inference_mode_enabled() and t.is_grad_enabled()
            and not t.is_autocast_enabled('cuda') and not t.is_autocast_enabled('cpu'),'ordinary_cpu_caller_context')
        require(t.cuda.current_device()==self.device.index,'selected_device_changed')
        require(a.execution_feedback is False and a.temporal_cache is None and a._pending_feedback is False,'native_only')
        modules=[];masks=[]
        for name,m in a.model.named_modules():
            hooks=tuple((key,tuple(value.items())) for key,value in vars(m).items() if '_hooks' in key and isinstance(value,dict))
            require(not any(value for key,value in vars(m).items() if '_hooks' in key),'module_hooks:'+name)
            forward=getattr(m.forward,'__func__',m.forward)
            modules.append((name,id(m),type(m),m.training,forward,hooks))
            if type(m) in (self.policy_module.PolicyCausalTransformer,self.transformer_module.SelfAttention) or hasattr(m,'_mask_fn'):
                masks.append((name,self.attention_signature(m)))
        require(not any(v for k,v in vars(t.nn.modules.module).items() if k.startswith('_global') and '_hooks' in k),'global_hooks')
        stores=tuple((name,self.layout(value)) for name,value in list(a.model.named_parameters())+list(a.model.named_buffers()))
        methods=tuple((name,getattr(type(a),name),vars(a).get(name)) for name in
            ('predict','_forward','_prepare_graph','reset','set_goal','_begin_history_transaction','finish_action'))
        configuration=json.dumps(a.config.model_dump(mode='json'),sort_keys=True,allow_nan=False)
        mapping=a.model.action_mapping
        return (id(a),id(a.model),id(a.config),configuration,a.model.top_p,
            int(t.cuda.current_stream(self.device).cuda_stream),
            id(mapping),self.layout(mapping._mouse_delta_x_edges),self.layout(mapping._mouse_delta_y_edges),
            a.use_cuda_graph,a.observation_profile,a.mouse_sampling,a.dtype,
            self.layout(a.text),tuple(modules),tuple(masks),stores,methods,cache_descriptors.signature(a.model))

    def attention_signature(self,module):
        """Separate the policy mask factory from concrete attention mask owners.

        PolicyCausalTransformer has no attention-mask/scalar attributes. Every
        SelfAttention explicitly initializes both masks to None; stable_start is
        added only by precompute_decode_masks and remains absent in the decoder.
        """
        fields=('block_mask','_cached_decode_mask','stable_start','is_causal',
            'n_kv_sink_tokens','grouped_qa','input_dim','n_q_head','n_kv_head',
            'embed_size_per_head','dropout')
        values=vars(module)
        require('_mask_fn' in values,'mask_function_attribute_missing')
        if type(module) is self.policy_module.PolicyCausalTransformer:
            require(callable(module._mask_fn) and not any(name in values for name in fields),
                'policy_mask_factory_shape')
            return ('policy_mask_factory',module._mask_fn)
        require(type(module) is self.transformer_module.SelfAttention,'unsupported_mask_owner_class')
        require(all(name in values for name in fields if name!='stable_start'),
            'attention_attribute_missing')
        require(module._mask_fn is None or callable(module._mask_fn),'attention_mask_function_type')
        def mask(value):
            if value is None:return None
            require(type(value) is self.transformer_module.fa.DenseMask,'attention_mask_backend_type')
            return (id(value),type(value),value.mask_mod,value.BLOCK_SIZE,value.seq_lengths)
        return ('self_attention',module._mask_fn,mask(module.block_mask),mask(module._cached_decode_mask),
            ('stable_start' in vars(module),getattr(module,'stable_start',None)),
            module.is_causal,module.n_kv_sink_tokens,module.grouped_qa,module.input_dim,
            module.n_q_head,module.n_kv_head,module.embed_size_per_head,module.dropout)

    def claim(self,owner):
        """Cooperative process-wide exclusion; outside consumers remain an admission constraint."""
        global _GENERATOR_OWNER
        require(_GENERATOR_LOCK.acquire(blocking=False),'generator_owner_busy');_GENERATOR_OWNER=owner

    def release(self,owner):
        """Release only the actual lease holder after confirmed completion."""
        global _GENERATOR_OWNER
        require(_GENERATOR_OWNER==owner,'generator_owner_mismatch');_GENERATOR_OWNER=None;_GENERATOR_LOCK.release()

    def layout(self,tensor):
        """Object/pointer plus layout, without copying or coercing values."""
        require(self.torch.is_tensor(tensor),'tensor_required')
        return (id(tensor),tensor.data_ptr(),str(tensor.dtype),str(tensor.device),tuple(tensor.shape),tuple(tensor.stride()))

    def nbytes(self,tensor):
        """Logical clone bytes; range-overlap checks separately account for strides."""
        return tensor.numel()*tensor.element_size()

    def _state(self,state):
        """Preserve list, row and leaf identities; return order is layer then K/V."""
        require(type(state) is list and len(state)==10,'native_state_layers')
        rows=[]
        for item in state:
            require(type(item) is self.cache_module.KVCacheState,'native_state_type')
            rows.append((id(item),self.layout(item.k_cache),self.layout(item.v_cache)))
        return (id(state),tuple(rows))

    def validate_history(self,a):
        """No masked prefix or synthetic fixed-length state is admitted as growing history."""
        t=self.torch;self._state(a.state)
        require(type(a.steps_seen) is int and a.steps_seen>=0,'native_steps')
        require(tuple(a.idx.shape)==() and a.idx.dtype==t.int64 and a.idx.device==self.device,'native_index_layout')
        length=min(a.steps_seen,41)*12
        for row in a.state:
            for value in row:
                require(tuple(value.shape)==(1,16,length,64) and value.dtype==t.float16
                    and value.device==self.device and value.is_contiguous(),'native_state_geometry')
        if a.graph is not None:
            require(a.use_cuda_graph is True and length==492 and a.idx is a.static_idx and a.state is a.static_state,
                'bound_graph_logical_alias')
            self.graph_identity(a)

    def _leaves(self,value):
        """Graph output is the stock nested tuple/list of tensors; no arbitrary object traversal."""
        if self.torch.is_tensor(value):return [value]
        require(isinstance(value,(tuple,list)),'unsupported_graph_output')
        return [tensor for item in value for tensor in self._leaves(item)]

    def graph_tensors(self,a):
        """Independently back up input AND output state; do not assume they are value-equal."""
        return [a.static_frame,a.static_idx,a.static_uniform]+self._leaves(a.static_state)+self._leaves(a.graph_result)

    def graph_identity(self,a):
        """Reject overlap/alias ambiguity; copyback may mutate values but never storage owners."""
        require(a.graph is not None and type(a.graph_result) is tuple and len(a.graph_result)==3,'graph_owner_shape')
        require(a.idx is a.static_idx and a.state is a.static_state,'graph_logical_owner')
        require(a.metadata.get('graphCaptureValidated') is True,'graph_not_validated')
        values=self.graph_tensors(a);ranges=[]
        require(len({id(v) for v in values})==len(values),'graph_tensor_alias')
        for v in values:
            require(all(n>=0 for n in v.stride()),'negative_graph_stride')
            if v.numel():
                end=v.data_ptr()+(1+sum((n-1)*s for n,s in zip(v.shape,v.stride())))*v.element_size()
                require(not any(v.data_ptr()<hi and lo<end for lo,hi in ranges),'graph_storage_overlap')
                ranges.append((v.data_ptr(),end))
        return (id(a.graph),id(a.graph_result),self._state(a.static_state),self._state(a.graph_result[2]),
            tuple(self.layout(v) for v in values))

    def history_identity(self,a):
        """Settlement must still own the returned logical references and graph objects."""
        return (self.layout(a.idx),self._state(a.state),a.steps_seen,id(a.metadata),
            json.dumps(a.metadata,sort_keys=True,allow_nan=False),
            self.graph_identity(a) if a.graph is not None else None)

    def clone(self,tensor):
        """Detach/clone only under a temporary snapshot context."""
        with self.torch.inference_mode():return tensor.detach().clone()

    def copy(self,destination,source):
        """Restore without replacing captured storage."""
        with self.torch.inference_mode():destination.copy_(source)

    def save_rng(self):
        """Both states are independent CPU byte tensors returned by the stock APIs."""
        return (self.torch.get_rng_state(),self.torch.cuda.get_rng_state(self.device))

    def restore_rng(self,state):
        """Restore both generators only while the exact cooperative lease is held."""
        self.torch.set_rng_state(state[0]);self.torch.cuda.set_rng_state(state[1],self.device)

    def verify_rng(self,state):
        """Read back both generator byte states; no model/tensor arithmetic is replayed."""
        current=self.save_rng()
        require(all(self.torch.equal(a,b) for a,b in zip(current,state)),'rng_restore_not_confirmed')

    def synchronize(self):
        """Explicit feedback backup/restore/retirement barrier, outside the delegated prediction."""
        self.torch.cuda.synchronize(self.device)
