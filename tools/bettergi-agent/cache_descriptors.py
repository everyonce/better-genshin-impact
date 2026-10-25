"""Proposed full-model mode guard; no imports, calls or mode changes to numerical code."""
import hashlib
from pathlib import Path
import types

CACHE_SHA='44664e5747f36db32a86f4c3fd3dcf574af318cfba17f78ffcca9335aba755c9'
POLICY_SHA='e7ac2e87e18f64abf8dff7566d302f0325fc220627f51ee163a814de1a4c784a'
TRANSFORMER_SHA='fd9d6f654b01b0714b16e750cb142057ea24e0bed5747c46711b0f8012fee872'
MODULE_MAPS=('_parameters','_buffers','_modules','_backward_pre_hooks','_backward_hooks',
    '_forward_hooks','_forward_hooks_with_kwargs','_forward_hooks_always_called',
    '_forward_pre_hooks','_forward_pre_hooks_with_kwargs','_state_dict_hooks','_state_dict_pre_hooks',
    '_load_state_dict_pre_hooks','_load_state_dict_post_hooks')
BASE_CONFIG=('batch_size','device','dtype','num_kv_heads','embed_size_per_head','cache_shape')
ROLLING_CONFIG=('step_size','max_T','max_seq_len')


def require(value,message):
    """Fail closed without normalizing any model or cache state."""
    if not value:raise ValueError(message)


def _code(source,owner,method):
    """Compile pinned source without executing/importing it; extract the actual method code."""
    module=compile(source.read_bytes(),str(source),'exec',dont_inherit=True)
    cls=next(c for c in module.co_consts if isinstance(c,types.CodeType) and c.co_name==owner)
    return next(c for c in cls.co_consts if isinstance(c,types.CodeType) and c.co_name==method)


def _method(function,owner,name,source,sha,namespace):
    """File hash plus exact code/default/globals checks reject replaced class methods too."""
    source=Path(source).resolve()
    require(hashlib.sha256(source.read_bytes()).hexdigest()==sha,'descriptor_source_hash:'+owner)
    require(isinstance(function,types.FunctionType) and function.__globals__ is namespace
        and Path(function.__code__.co_filename).resolve()==source
        and function.__code__==_code(source,owner,name),'descriptor_method_changed:'+owner+'.'+name)


def _descriptor(cache,expected,torch,cache_module,rolling,device):
    """Only exact stock descriptors with empty registries and the fixed history41 geometry qualify."""
    require(type(cache) is expected,'descriptor_exact_class')
    values=vars(cache);config=BASE_CONFIG+(ROLLING_CONFIG if rolling else ())
    allowed=set(MODULE_MAPS)|{'training','_non_persistent_buffers_set','_is_full_backward_hook'}|set(config)
    require(set(values)==allowed,'descriptor_attributes_or_override')
    require(type(cache.training) is bool,'descriptor_training_type')
    require(all(isinstance(values[k],dict) and not values[k] for k in MODULE_MAPS)
        and type(values['_non_persistent_buffers_set']) is set and not values['_non_persistent_buffers_set']
        and values['_is_full_backward_hook'] is None,'descriptor_registered_state_or_hooks')
    # These inherited methods must not acquire behavior depending on mode or instance hooks.
    for name in ('train','eval','forward','__call__','_call_impl','_wrapped_call_impl'):
        require(getattr(expected,name) is getattr(torch.nn.Module,name),'descriptor_module_method:'+name)
    require(expected.__bases__==(cache_module.BaseKVCache,)
        and cache_module.BaseKVCache.__bases__==(torch.nn.Module,),'descriptor_base_class')
    require(cache_module.torch is torch,'descriptor_torch_namespace')
    # These descriptor classes define only three methods; added behavior is not an exemption.
    for owner in (cache_module.BaseKVCache,expected):
        require(set(vars(owner))=={'__module__','__doc__','__init__','init_state','update'},'descriptor_class_attributes')
    for owner,names in ((cache_module.BaseKVCache,('__init__',)),(expected,('__init__','init_state','update'))):
        for name in names:
            _method(getattr(owner,name),owner.__name__,name,cache_module.__file__,CACHE_SHA,vars(cache_module))
    require(expected.init_state.__defaults__==(None,) and expected.update.__defaults__==(None,),
        'descriptor_method_defaults')
    required=dict(batch_size=1,num_kv_heads=16 if rolling else 8,embed_size_per_head=64 if rolling else 128)
    if rolling:required.update(step_size=12,max_T=41,max_seq_len=492)
    require(all(type(getattr(cache,k)) is int and getattr(cache,k)==v for k,v in required.items()),'descriptor_integer_config')
    shape=(1,required['num_kv_heads'],0,required['embed_size_per_head'])
    require(type(cache.cache_shape) is tuple and all(type(n) is int for n in cache.cache_shape)
        and cache.cache_shape==shape and cache.dtype==torch.float16 and cache.device==device,'descriptor_shape_device_dtype')
    return dict(type=expected.__name__,identity=id(cache),training=cache.training,
        modeIndependentCacheDescriptor=True,config={**required,'cache_shape':list(shape),
        'device':str(cache.device),'dtype':str(cache.dtype)},sourceSha256=CACHE_SHA)


def roles(model):
    """Resolve exact two owners; class membership alone never grants a mode exception."""
    policy=model.bc_transformer
    decoder=policy.action_decoder
    trunk=policy._transformer
    return policy,decoder,trunk,decoder.kv_cache,trunk.kv_cache


def signature(model):
    """Untimed preservation token includes actual modes, methods/config, owners and every alias."""
    policy,decoder,trunk,accum,rolling=roles(model)
    rows=[]
    for owner,cache in ((decoder,accum),(trunk,rolling)):
        keys=BASE_CONFIG+(ROLLING_CONFIG if cache is rolling else ())
        rows.append((id(owner),id(cache),cache.training,tuple(getattr(cache,k) for k in keys),
            tuple((getattr(type(cache),k),getattr(getattr(type(cache),k),'__defaults__',None),vars(cache).get(k)) for k in
                ('__init__','init_state','update','train','eval','forward','__call__','_call_impl','_wrapped_call_impl')),
            tuple(id(layer.self_attention.kv_cache) for layer in owner.transformer_layers),
            tuple((key,tuple(getattr(cache,key).items())) for key in MODULE_MAPS),
            tuple(sorted(vars(cache))),frozenset(cache._non_persistent_buffers_set),cache._is_full_backward_hook))
    return tuple(rows)


def qualify_model(model,torch,cache_module,transformer_module,policy_module):
    """All computational modules remain eval; only the exact proven descriptor identities differ."""
    policy,decoder,trunk,accum,rolling=roles(model)
    require(accum is not rolling and policy.kv_cache is rolling,'descriptor_owner_identity')
    require(type(policy) is policy_module.PolicyCausalTransformer
        and type(trunk) is transformer_module.Transformer,'descriptor_parent_class')
    require(type(policy.config.n_steps) is int and policy.config.n_steps==41
        and policy.config.model_type=='dense' and type(policy.step_size) is int and policy.step_size==12,
        'descriptor_policy_config')
    for owner,name,module,sha in ((policy_module.PolicyCausalTransformer,'setup_kv_cache',policy_module,POLICY_SHA),
        (transformer_module.Transformer,'init_kv_cache_state',transformer_module,TRANSFORMER_SHA),
        (transformer_module.SelfAttention,'forward',transformer_module,TRANSFORMER_SHA)):
        _method(getattr(owner,name),owner.__name__,name,module.__file__,sha,vars(module))
    require(all(key not in vars(owner) for owner in (policy,trunk) for key in ('setup_kv_cache','init_kv_cache_state')),
        'descriptor_parent_override')
    paths={id(accum):{'bc_transformer.action_decoder.kv_cache'},
        id(rolling):{'bc_transformer._transformer.kv_cache'}}
    for owner,cache,count,prefix in ((decoder,accum,3,'bc_transformer.action_decoder'),
        (trunk,rolling,10,'bc_transformer._transformer')):
        layers=list(owner.transformer_layers)
        require(len(layers)==count and all(type(layer) is transformer_module.TransformerSelfAttentionLayer
            and type(layer.self_attention) is transformer_module.SelfAttention
            and layer.self_attention.kv_cache is cache for layer in layers),'descriptor_shared_attention_owner')
        paths[id(cache)].update(f'{prefix}.transformer_layers.{i}.self_attention.kv_cache' for i in range(count))
    records=[_descriptor(accum,cache_module.AccumulatingKVCache,torch,cache_module,False,decoder.pos_tokens.device),
        _descriptor(rolling,cache_module.RollingStepKVCache,torch,cache_module,True,torch.device('cuda'))]
    all_rows=list(model.named_modules(remove_duplicate=False))
    for cache in (accum,rolling):
        actual=[name for name,module in all_rows if module is cache]
        require(len(actual)==len(paths[id(cache)]) and set(actual)==paths[id(cache)],'descriptor_alias_paths')
    seen=set()
    for name,module in all_rows:
        if id(module) in seen:continue
        seen.add(id(module))
        require(not isinstance(module,cache_module.BaseKVCache) or module is accum or module is rolling,
            'unowned_cache_descriptor:'+name)
        require(module is accum or module is rolling or module.training is False,'computational_module_not_eval:'+name)
        require(not any(value for key,value in vars(module).items() if '_hooks' in key),'model_hooks:'+name)
    require(not any(value for key,value in vars(torch.nn.modules.module).items() if key.startswith('_global') and '_hooks' in key),
        'global_model_hooks')
    for record in records:record['aliasPaths']=sorted(paths[record['identity']])
    return dict(schema='v15-exact-cache-mode-qualification-proposal-v1',cacheDescriptors=records,
        computationalModulesVerified=len(seen)-2,computationalModulesTrainingFalse=True,
        modeChanged=False,executionReady=False)
