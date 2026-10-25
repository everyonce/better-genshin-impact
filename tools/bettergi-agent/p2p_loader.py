"""Load official Open P2P weights through a documented Windows/Turing port.

The official MIT-licensed source stays intact. A generated copy under artifacts
removes training-only imports and changes BF16/FlexAttention to FP16/SDPA.
The checkpoint must match every model parameter; random-weight fallback is forbidden.
"""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys


def prepare_source(source: Path, destination: Path, dtype: str):
    """Create an auditable model-only copy of a previously downloaded repository."""
    source = source.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source / 'elefant', destination / 'elefant', dirs_exist_ok=True)
    shutil.copy2(source / 'LICENSE', destination / 'UPSTREAM-LICENSE')
    modifications = []

    def write(relative, content):
        path = destination / relative
        old = path.read_bytes() if path.exists() else b''
        path.write_text(content, encoding='utf-8')
        modifications.append({'path': relative, 'originalSha256': hashlib.sha256(old).hexdigest(),
                              'adaptedSha256': hashlib.sha256(path.read_bytes()).hexdigest()})

    # Import the original augmentation configuration without its video/Rust loader.
    tree = ast.parse((source / 'elefant/data/video_proto_dataset.py').read_text(encoding='utf-8'))
    config_class = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                        and node.name == 'RandAugmentationConfig')
    write('elefant/data/__init__.py',
          'from typing import *\nimport pydantic\nfrom elefant.config import ConfigBase\n'
          'from elefant.data.action_mapping import *\n' + ast.unparse(config_class) + '\n')
    write('elefant/im_tokenizer/__init__.py',
          'from elefant.im_tokenizer.base_tokenizer import ImageBaseTokenizer\n'
          'from elefant.im_tokenizer.config import ImageTokenizerConfig\n'
          'from elefant.im_tokenizer.conv_tokenizer import ConvTokenizer\n'
          'def get_tokenizer(config, embed_dim, frame_height, frame_width):\n'
          '    if config.type != "conv": raise ValueError("This adapter supports released convolutional policies only")\n'
          '    return ConvTokenizer(config, frame_height, frame_width, embed_dim)\n')
    write('elefant/text_tokenizer/__init__.py',
          '"""Inference without text uses the learned no-text embedding."""\n')
    # All EfficientNet parameters are present in the checkpoint: do not download
    # an unrelated ImageNet initialization before strictly loading those weights.
    conv = 'elefant/im_tokenizer/conv_tokenizer.py'
    write(conv, (destination / conv).read_text(encoding='utf-8').replace('weights="IMAGENET1K_V1"', 'weights=None'))
    model = 'elefant/policy_model/model_free.py'
    write(model, (destination / model).read_text(encoding='utf-8')
          .replace('import lightning as pl', '')
          .replace('pl.LightningModule', 'torch.nn.Module'))
    for path in (destination / 'elefant/policy_model').glob('*.py'):
        original = path.read_text(encoding='utf-8')
        adapted = original.replace('torch.bfloat16', 'torch.' + dtype)
        adapted = adapted.replace('from torch.nn.attention import flex_attention as fa',
                                   'import p2p_compat_attention as fa')
        # Numerically identical diagnostic constants allocated on-device; a
        # host-to-device tensor literal would invalidate CUDA graph capture.
        adapted = adapted.replace('torch.tensor([1.0])', 'torch.ones(1)')
        adapted = adapted.replace('torch.tensor([1.0], device=x_device)', 'torch.ones(1, device=x_device)')
        if adapted != original:
            write(path.relative_to(destination).as_posix(), adapted)
    # Avoid both FP16 position overflow and a recurring cache-limit reset. The
    # replacement evaluates the same FP32 trigonometric formula on-device.
    rotary = 'elefant/policy_model/pos_embed.py'
    rotary_source = (destination / rotary).read_text(encoding='utf-8')
    cached_lookup = 'self.cache[:seq_len] if input_pos is None else self.cache[input_pos]'
    if cached_lookup not in rotary_source:
        raise RuntimeError('Upstream rotary implementation changed; adapter requires review')
    write(rotary, 'from p2p_rotary import rotary_values\n' + rotary_source.replace(
        cached_lookup, 'rotary_values(self.theta, seq_len, input_pos)'))
    manifest = {'upstream': str(source), 'precision': dtype,
                'changes': modifications,
                'scope': 'Inference-only compatibility path: original architecture and weights, exact dense mask, no compilation; optional upstream goal embeddings are supplied separately.'}
    (destination / 'compatibility-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def load_model(source, checkpoint, cache_root, history=200, dtype='float16', checkpoint_scope=None):
    """Build the upstream network and load tensor-only checkpoint contents strictly."""
    if checkpoint_scope is not None:
        checkpoint_scope.begin_loader(source, checkpoint, history, dtype)
    import torch
    import yaml
    adapted = Path(cache_root) / ('open-p2p-native-' + dtype)
    manifest = prepare_source(Path(source), adapted, dtype)
    sys.path.insert(0, str(adapted))
    from elefant.policy_model.model_free import ModelFreePolicy
    from elefant.policy_model.config import LightningPolicyConfig
    from elefant.policy_model.kv_cache import KVCacheState
    from elefant.data.action_mapping import StructuredAction
    from elefant.torch import eager_assert, _sample_from_logits_gpu
    from typing import Optional, List

    # Reuse only the four upstream inference methods. Avoid importing the trainer,
    # data module, telemetry, Unix transport, and gated text encoder.
    original = ast.parse((adapted / 'elefant/policy_model/stage3_finetune.py').read_text(encoding='utf-8'))
    trainer = next(node for node in original.body if isinstance(node, ast.ClassDef) and node.name == 'PolicyModelTrainer')
    names = {'_init_action_mapping', '_keyboard_mouse_action_sampler',
             'online_kv_cache_predict', 'action_in_to_tokens'}
    methods = [node for node in trainer.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in methods} != names:
        raise RuntimeError('Upstream inference methods changed; adapter requires review')
    namespace = dict(torch=torch, nn=torch.nn, StructuredAction=StructuredAction,
                     Optional=Optional, List=List, KVCacheState=KVCacheState,
                     eager_assert=eager_assert, _sample_from_logits_gpu=_sample_from_logits_gpu)
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(Path(source) / 'elefant/policy_model/stage3_finetune.py'), 'exec'), namespace)

    class NativePolicy(ModelFreePolicy):
        """Original inference layers without Lightning's training lifecycle."""
        def __init__(self, config):
            super().__init__(config, 'stage3_finetune', inference_mode=True)
            self._init_action_mapping()
            self.top_p = config.policy_model.top_p

        def _get_transformer_mask_fn(self):
            return None

    for name in names:
        setattr(NativePolicy, name, namespace[name])
    if checkpoint_scope is None:
        config_data = yaml.safe_load((Path(source) / 'config/policy_model/150M.yaml').read_text(encoding='utf-8'))
    else:
        # Verify the exact YAML bytes consumed, independently from checkpoint tensors.
        config_bytes = (Path(source) / 'config/policy_model/150M.yaml').read_bytes()
        checkpoint_scope.check_source(config_bytes, manifest)
        config_data = yaml.safe_load(config_bytes.decode('utf-8'))
    config_data['shared']['n_seq_timesteps'] = history
    config_data['policy_model']['attention_history_len'] = [history] * config_data['policy_model']['n_transformer_layers']
    config = LightningPolicyConfig.model_validate(config_data)
    if checkpoint_scope is None:
        model = NativePolicy(config)
        state = torch.load(checkpoint, map_location='cpu', weights_only=True)
        state = state.get('state_dict', state)
        model.load_state_dict(state, strict=True)
    else:
        # Keep even a constructor-partial model and the same verified read stream.
        model = checkpoint_scope.construct_model(NativePolicy, config)
        state = checkpoint_scope.load(torch, checkpoint, model)
    model.to(device='cuda', dtype=getattr(torch, dtype)).eval()
    from p2p_rotary import restore_rotary_precision
    restore_rotary_precision(model)
    model.action_mapping._mouse_delta_x_edges = model.action_mapping._mouse_delta_x_edges.to('cuda')
    model.action_mapping._mouse_delta_y_edges = model.action_mapping._mouse_delta_y_edges.to('cuda')
    # Cache modules store device/dtype as ordinary attributes, so rebuild them
    # after moving parameters; otherwise they still allocate CPU cache states.
    model.bc_transformer.action_decoder._setup_kv_cache_state()
    model.bc_transformer.setup_kv_cache(1, torch.device('cuda'), dtype=getattr(torch, dtype))
    return model, config, manifest
