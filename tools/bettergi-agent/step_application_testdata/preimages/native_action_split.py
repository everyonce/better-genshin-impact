"""Source-derived eager proposal/commit functions; no numerical import or installation.

The original functions remain untouched. A later numerical qualification must
compare these separate calls with the original complete call at every geometry.
"""
import ast
import builtins
import copy
import hashlib
import sys
import types
from pathlib import Path

SOURCE_HASHES = ('c2a424ab10b6dd52c3707b1a19a90db515172ef2bc2f65c4ded96b52a14802e0',
                 '2c6f49e6143364de81f56aa8102d2efa15fd56d5afbb363d01f6e44ab85527e6')
LOADER_SHA = '48e5ee7e6e8df3cad584ce4d22b1a17d2984c1e65278e0a768702edcec02eb3a'
ADAPTED_STAGE_SHA = '530f911d644ccfbad532d5ba36e6cf013269b0002708b1a9e543a5fea08ebf62'
STAGE_NAMES = ('_init_action_mapping', '_keyboard_mouse_action_sampler',
               'online_kv_cache_predict', 'action_in_to_tokens')


def _codes(code):
    """Inspect compiled constants; no trainer module or numerical body is executed."""
    for child in code.co_consts:
        if isinstance(child, types.CodeType):
            yield child
            yield from _codes(child)


def _defaults(node):
    """The pinned four methods have only literal positional defaults and no keyword defaults."""
    require(not node.args.kwonlyargs, 'stage_keyword_defaults')
    values = tuple(ast.literal_eval(n) for n in node.args.defaults)
    return values or None


def _same_defaults(actual, expected):
    """Do not let Python bool/integer equality hide a changed invocation default."""
    return (actual is None and expected is None) or (type(actual) is tuple and type(expected) is tuple
        and len(actual) == len(expected)
        and all(type(a) is type(b) and a == b for a, b in zip(actual, expected)))


def _stage_guard(binding):
    """Retain exact extracted methods and their shared globals across proposal and commit."""
    model, loader, load_fn, load_code, scope, globals_rows, methods = binding
    require(loader.load_model is load_fn and load_fn.__code__ is load_code, 'loader_method_drift')
    require(set(scope) == {name for name, _ in globals_rows} | set(STAGE_NAMES), 'stage_namespace_keys')
    require(all(scope[name] is value for name, value in globals_rows), 'stage_namespace_drift')
    for name, fn, code, defaults in methods:
        require(name not in vars(model) and getattr(type(model), name) is fn
                and scope[name] is fn and fn.__globals__ is scope and fn.__code__ is code
                and fn.__closure__ is None and fn.__kwdefaults__ is None
                and _same_defaults(fn.__defaults__, defaults), 'stage_method_drift:' + name)


def _loader_stage(model, loader, policy_module, source_root, pinned_source):
    """Qualify the real inference loader's detached namespace, never import its trainer.

    The loader compiles four AST definitions from its adapted Stage3 copy with
    the ORIGINAL upstream filename. Only init_action_mapping changes under the
    pinned FP16 source adaptation; online prediction/sampling/embedding bodies
    must remain identical to the original source.
    """
    loader_path = Path(loader.__file__)
    loader_raw = loader_path.read_bytes()
    require(hashlib.sha256(loader_raw).hexdigest() == LOADER_SHA, 'loader_source')
    load_fn = loader.load_model
    compiled_loader = compile(loader_raw, str(loader_path), 'exec', dont_inherit=True)
    load_codes = [n for n in _codes(compiled_loader) if n.co_qualname == 'load_model']
    require(len(load_codes) == 1 and isinstance(load_fn, types.FunctionType)
            and load_fn.__globals__ is vars(loader) and load_fn.__code__ == load_codes[0]
            and load_fn.__code__.co_filename == str(loader_path), 'loader_code')
    original_path = Path(source_root) / 'elefant/policy_model/stage3_finetune.py'
    require(original_path.read_bytes() == pinned_source, 'original_stage_source')
    adapted_path = Path(policy_module.__file__).with_name('stage3_finetune.py')
    adapted_raw = adapted_path.read_bytes()
    require(hashlib.sha256(adapted_raw).hexdigest() == ADAPTED_STAGE_SHA, 'adapted_stage_source')
    # Match exactly the pinned loader's replacement at this file. Normalize only
    # platform text newlines, as Path.read_text does before prepare_source writes.
    original_text = pinned_source.decode('utf-8').replace('\r\n', '\n')
    adapted_text = adapted_raw.decode('utf-8').replace('\r\n', '\n')
    require(adapted_text == original_text.replace('torch.bfloat16', 'torch.float16'), 'stage_adaptation')
    tree = ast.parse(adapted_text)
    trainers = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PolicyModelTrainer']
    require(len(trainers) == 1, 'stage_trainer_definition')
    nodes = [n for n in trainers[0].body if isinstance(n, ast.FunctionDef) and n.name in STAGE_NAMES]
    require(len(nodes) == 4 and {n.name for n in nodes} == set(STAGE_NAMES), 'stage_extraction_set')
    for node in nodes:
        if node.name != '_init_action_mapping':
            require(ast.dump(node) == ast.dump(method(pinned_source, node.name)), 'stage_body:' + node.name)
    compiled = compile(ast.Module(body=nodes, type_ignores=[]), str(original_path), 'exec', dont_inherit=True)
    expected_codes = {n.co_name: n for n in compiled.co_consts if isinstance(n, types.CodeType)}
    require(set(expected_codes) == set(STAGE_NAMES), 'extracted_code_set')
    fn = getattr(type(model), 'online_kv_cache_predict')
    require(isinstance(fn, types.FunctionType), 'stage_function')
    scope = fn.__globals__
    # All modules already belong to the constructed model. No numerical import,
    # trainer import, package discovery, or function call occurs in this check.
    torch = sys.modules.get('torch'); typing = sys.modules.get('typing')
    cache = sys.modules.get('elefant.policy_model.kv_cache')
    mapping = sys.modules.get('elefant.data.action_mapping')
    utility = sys.modules.get('elefant.torch')
    require(all(isinstance(m, types.ModuleType) for m in (torch, typing, cache, mapping, utility)),
            'loader_dependency_modules')
    expected_globals = {'torch': torch, 'nn': torch.nn, 'StructuredAction': mapping.StructuredAction,
        'Optional': typing.Optional, 'List': typing.List, 'KVCacheState': cache.KVCacheState,
        'eager_assert': utility.eager_assert, '_sample_from_logits_gpu': utility._sample_from_logits_gpu,
        '__builtins__': vars(builtins)}
    methods = []
    for node in nodes:
        live = getattr(type(model), node.name)
        require(isinstance(live, types.FunctionType) and live.__code__ == expected_codes[node.name]
                and all(code.co_filename == str(original_path) for code in (live.__code__, *_codes(live.__code__))),
                'extracted_stage_code:' + node.name)
        methods.append((node.name, live, live.__code__, _defaults(node)))
    binding = (model, loader, load_fn, load_fn.__code__, scope, tuple(expected_globals.items()), tuple(methods))
    _stage_guard(binding)
    qualification = {'kind': 'pinned-loader-detached-four-method-namespace',
        'loaderSha256': LOADER_SHA, 'originalStageSha256': SOURCE_HASHES[1],
        'adaptedStageSha256': ADAPTED_STAGE_SHA, 'originalFilename': str(original_path),
        'adaptedPath': str(adapted_path), 'methodNames': list(STAGE_NAMES),
        'trainerImportedByQualification': False}
    return next(n for n in nodes if n.name == 'online_kv_cache_predict'), scope, binding, qualification


def require(ok, message):
    """Reject an unexpected source seam before building executable functions."""
    if not ok:
        raise ValueError(message)


def method(source, name):
    """Read one uniquely named method without importing its module."""
    tree = ast.parse(source)
    found = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    require(len(found) == 1, 'unique_native_method:' + name)
    return found[0]


def _plain(node):
    """Annotations are definition metadata, not part of either numerical body."""
    node = copy.deepcopy(node)
    for item in ast.walk(node):
        if isinstance(item, ast.arg):
            item.annotation = None
        if isinstance(item, ast.FunctionDef):
            item.returns = None
    return node


def split_nodes(original):
    """Split only immediately before the original sampled-action embedding call."""
    original = _plain(original)
    boundary = [i for i, n in enumerate(original.body) if isinstance(n, ast.Assign)
                and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id == 'action_embeddings_in']
    # The first assignment embeds IDs; the second only reshapes that result.
    require(len(boundary) == 2, 'native_embedding_assignments')
    cut = boundary[0]
    require(ast.dump(original.body[cut].value) == ast.dump(ast.parse(
        'action_in_to_tokens_fn(sampled_action_reshaped)', mode='eval').body), 'native_split_boundary')
    names = ('sampled_action', 'sampled_action_reshaped', 'B', 'text_tokens_embed_with_pos',
             'img_tokens_with_pos', 'batch_thinking_pos_tokens', 'batch_action_out_token',
             'input_pos', 'kv_cache_state', 'should_grow_cache', 'action_in_to_tokens_fn')
    prepared = copy.deepcopy(original)
    prepared.name = '_prepare_native_action'
    prepared.body = copy.deepcopy(original.body[:cut]) + [ast.Return(
        value=ast.Tuple(elts=[ast.Name(id=n, ctx=ast.Load()) for n in names], ctx=ast.Load()))]
    commit = ast.FunctionDef(name='_commit_native_action', args=ast.arguments(
        posonlyargs=[], args=[ast.arg(arg='self'), ast.arg(arg='prepared')],
        kwonlyargs=[], kw_defaults=[], defaults=[]), decorator_list=[], body=[
        ast.Assign(targets=[ast.Tuple(elts=[ast.Name(id=n, ctx=ast.Store()) for n in names],
                                    ctx=ast.Store())], value=ast.Name(id='prepared', ctx=ast.Load()))
    ] + copy.deepcopy(original.body[cut:]))
    return ast.fix_missing_locations(prepared), ast.fix_missing_locations(commit)


def stage_node(original):
    """Keep Stage3 normalization/sampler/full-cache selection and replace one call/return."""
    out = _plain(original)
    out.name = '_prepare_stage3_action'
    inner = [n for n in out.body if isinstance(n, ast.FunctionDef) and n.name == '_predict']
    require(len(inner) == 1, 'stage_inner_predict')
    body = inner[0].body
    matches = [(i, n) for i, n in enumerate(body) if isinstance(n, ast.Assign)
               and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute)
               and n.value.func.attr == 'online_forward']
    require(len(matches) == 1, 'stage_native_call')
    i, row = matches[0]
    require(i == len(body) - 2 and isinstance(body[-1], ast.Return), 'stage_tail_shape')
    require(ast.dump(row.targets[0]) == ast.dump(ast.parse(
        'sampled_action, idx, kv_cache_state = value').body[0].targets[0]), 'stage_return_names')
    call = copy.deepcopy(row.value)
    require(ast.dump(call.func.value) == ast.dump(ast.parse('self.bc_transformer', mode='eval').body),
            'stage_native_owner')
    call.args.insert(0, call.func.value)
    call.func = ast.Name(id='_split_prepare', ctx=ast.Load())
    inner[0].body = body[:i] + [ast.Return(value=call)]
    return ast.fix_missing_locations(out)


def compile_function(node, namespace, filename):
    """Compile only a function definition in a detached original namespace."""
    scope = dict(namespace)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 filename, 'exec', dont_inherit=True), scope)
    return scope[node.name]


def _live_method(instance, module, name, pinned_source):
    """Require the actual method, globals and file-compiled body, not just matching names."""
    require(name not in vars(instance), 'instance_override:' + name)
    fn = getattr(type(instance), name)
    require(isinstance(fn, types.FunctionType) and fn.__globals__ is vars(module), 'native_globals:' + name)
    live = Path(module.__file__).read_bytes()
    expected = method(live, name)
    require(ast.dump(expected) == ast.dump(method(pinned_source, name)), 'native_ast:' + name)
    compiled = compile(live, str(Path(module.__file__)), 'exec', dont_inherit=True)
    def codes(code):
        for child in code.co_consts:
            if isinstance(child, types.CodeType):
                yield child
                yield from codes(child)
    found = [c for c in codes(compiled) if c.co_name == name]
    require(len(found) == 1 and fn.__code__ == found[0], 'native_code:' + name)
    return expected, vars(module)


class NativeSplit:
    """Exclusive eager helper. No global method replacement or graph owner is created."""
    def __init__(self, model, policy_module, loader_module, policy_source, stage_source, *, source_root):
        require(tuple(hashlib.sha256(x).hexdigest() for x in (policy_source, stage_source)) == SOURCE_HASHES,
                'pinned_native_sources')
        policy, pg = _live_method(model.bc_transformer, policy_module, 'online_forward', policy_source)
        stage, sg, self._stage_binding, self.qualification = _loader_stage(
            model, loader_module, policy_module, source_root, stage_source)
        first, second = split_nodes(policy)
        self.prepare_native = compile_function(first, pg, '<isolated-native-proposal>')
        self.commit_native = compile_function(second, pg, '<isolated-native-commit>')
        self.prepare_stage = compile_function(stage_node(stage), dict(sg, _split_prepare=self.prepare_native),
                                              '<isolated-stage3-proposal>')
        self.model = model
        self._built = (self.prepare_native, self.commit_native, self.prepare_stage)
        self.methods = (type(model).online_kv_cache_predict, type(model.bc_transformer).online_forward)
        self.source_hashes = tuple(hashlib.sha256(x).hexdigest() for x in (policy_source, stage_source))

    def guard(self):
        """Reject changed methods/instance dispatch before every half of the operation."""
        _stage_guard(self._stage_binding)
        require(self._built == (self.prepare_native, self.commit_native, self.prepare_stage)
                and 'online_kv_cache_predict' not in vars(self.model)
                and 'online_forward' not in vars(self.model.bc_transformer)
                and self.methods == (type(self.model).online_kv_cache_predict,
                                     type(self.model.bc_transformer).online_forward), 'split_method_drift')

    def prepare(self, frame, idx, state, text):
        """Normalize once, sample once and retain the original prestate and prefixes."""
        self.guard()
        return self.prepare_stage(self.model, frame, idx, state, compile=False,
                                  sampling_temperature=1.0, text_tokens_embed=text, unif_rand=None)

    def commit(self, prepared):
        """Perform only the original second temporal pass; never encode or sample again."""
        self.guard()
        return self.commit_native(self.model.bc_transformer, prepared)
