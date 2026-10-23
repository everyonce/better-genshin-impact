"""Opt-in, history-free Qwen3.5 text-prefix reuse with explicit parity checks.

The prefix ends BEFORE vision_start. Each fresh image keeps the full prompt's
multimodal positions. Hybrid state includes Python flags as well as tensors;
restoration preserves live storage addresses used by the decode CUDA graph.
This helper is not enabled by importing it, and never loads model weights.
"""
import time

import torch
from transformers import StaticCache
from transformers.cache_utils import LinearAttentionLayer, StaticLayer


def _copy_state(value):
    """Clone numerical state and immutable metadata; reject unknown mutable types."""
    if isinstance(value, torch.Tensor):
        return value.detach().clone()
    if isinstance(value, dict):
        return {key: _copy_state(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool, type(None), torch.dtype, torch.device)):
        return value
    raise TypeError(f'Unsupported cache state type: {type(value).__name__}')


def _tensors(value, path=''):
    """Enumerate all tensors, including dictionaries of recurrent/conv states."""
    if isinstance(value, torch.Tensor):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _tensors(item, f'{path}.{key}')


def _restore(live, saved):
    """Copy tensors in place and restore scalar flags into existing dictionaries."""
    if isinstance(saved, torch.Tensor):
        live.copy_(saved)
        return live
    if isinstance(saved, dict):
        if not isinstance(live, dict) or live.keys() != saved.keys():
            raise RuntimeError('Hybrid cache state structure changed')
        for key in saved:
            live[key] = _restore(live[key], saved[key])
        return live
    return saved


def _state_comparison(actual, expected, path='', rtol=1e-3, atol=1e-3, differences=None):
    """Check numerical tolerance plus exact non-tensor state; report actual deltas."""
    differences = [] if differences is None else differences
    if isinstance(expected, torch.Tensor):
        if actual.shape != expected.shape or actual.dtype != expected.dtype or actual.device != expected.device:
            raise AssertionError(f'Cache tensor layout differs: {path}')
        delta = float((actual.float() - expected.float()).abs().max().item()) if actual.numel() else 0.0
        if not torch.equal(actual, expected):
            differences.append({'state': path, 'maxAbsDelta': delta})
        # Counts/indices are exact state, not floating-point approximations.
        tolerance = (rtol, atol) if expected.is_floating_point() or expected.is_complex() else (0, 0)
        torch.testing.assert_close(actual, expected, rtol=tolerance[0], atol=tolerance[1],
                                   msg=lambda message: f'{path}: {message}')
    elif isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise AssertionError(f'Cache state structure differs: {path}')
        for key in expected:
            _state_comparison(actual[key], expected[key], f'{path}.{key}', rtol, atol, differences)
    elif type(actual) is not type(expected) or actual != expected:
        raise AssertionError(f'Cache metadata differs: {path}: {actual!r} != {expected!r}')
    return differences


class HybridCacheSnapshot:
    """Snapshot the initialized Qwen3.5 static/linear cache, including all flags."""
    def __init__(self, cache):
        if type(cache) is not StaticCache or cache.offloading or cache.layer_class_to_replicate is not None:
            raise ValueError('Prefix reuse requires a non-offloaded StaticCache')
        if not cache.layers or any(type(layer) not in (StaticLayer, LinearAttentionLayer) for layer in cache.layers):
            raise ValueError('Only full-static and linear-attention layers are supported')
        for layer in cache.layers:
            if isinstance(layer, StaticLayer) and not layer.is_initialized:
                raise ValueError('The full-attention cache must be initialized before snapshotting')
            if isinstance(layer, LinearAttentionLayer) and (
                layer.record_past or not all(layer.is_conv_states_initialized.values())
                or not all(layer.is_recurrent_states_initialized.values())
            ):
                raise ValueError('Linear state must be initialized with record_past disabled')
        self.cache = cache
        self.layer_types = [type(layer) for layer in cache.layers]
        self.saved = [_copy_state(vars(layer)) for layer in cache.layers]
        self.layout = self._layout(cache)
        self.bytes = sum(tensor.numel()*tensor.element_size() for state in self.saved for _, tensor in _tensors(state))
        self.tensor_count = sum(1 for state in self.saved for _ in _tensors(state))

    @staticmethod
    def _layout(cache):
        """Record storage identity, not merely shapes, before any captured replay."""
        return [(index, path, value.data_ptr(), tuple(value.shape), value.dtype, value.device)
                for index, layer in enumerate(cache.layers) for path, value in _tensors(vars(layer))]

    def restore(self, cache):
        """Refuse changed buffers before copying any saved state into the cache."""
        if cache is not self.cache or [type(layer) for layer in cache.layers] != self.layer_types:
            raise RuntimeError('Prefix snapshot belongs to a different cache')
        if self._layout(cache) != self.layout:
            raise RuntimeError('Hybrid cache replaced a captured tensor; refusing prefix restore')
        for layer, state in zip(cache.layers, self.saved):
            if vars(layer).keys() != state.keys():
                raise RuntimeError('Hybrid cache attribute schema changed')
        for layer, state in zip(cache.layers, self.saved):
            _restore(vars(layer), state)

    def compare(self, cache, rtol=1e-3, atol=1e-3, differences=None):
        """Compare another initialized cache against this snapshot without mutation."""
        if [type(layer) for layer in cache.layers] != self.layer_types:
            raise AssertionError('Hybrid cache layer types differ')
        differences = [] if differences is None else differences
        for index, (layer, state) in enumerate(zip(cache.layers, self.saved)):
            _state_comparison(vars(layer), state, f'layer[{index}]', rtol, atol, differences)
        return differences


class InvariantTextPrefix:
    """Reuse one invariant text prefix; validate numeric state and complete outputs."""
    def __init__(self, model, history_frames=0, validation_actions=2):
        if history_frames != 0:
            raise ValueError('Invariant text-prefix caching initially requires history=0')
        if model.config.model_type != 'qwen3_5' or model.training:
            raise ValueError('Prefix caching requires an eval-mode Qwen3.5 multimodal model')
        if validation_actions < 2:
            raise ValueError('At least two complete actions must be validated')
        self.model = model
        self.validation_actions = validation_actions
        self.snapshot = None
        self.prefix_ids = None
        self.metadata = {'implementation': 'invariant-text-prefix-static-hybrid-cache',
                         'historyFrames': 0, 'rtol': 1e-3, 'atol': 1e-3,
                         'bitwiseEquivalent': True, 'validatedPrefills': 0, 'validatedActions': 0,
                         'maxCacheAbsDelta': 0.0, 'maxLogitAbsDelta': 0.0,
                         'setupCount': 0, 'restoreCount': 0, 'snapshotBytes': 0,
                         'totalSetupMs': 0.0, 'totalRestoreMs': 0.0, 'totalValidationMs': 0.0,
                         'totalActionValidationMs': 0.0,
                         'timingScope': 'synchronized wall times; fullActionMs includes all work; setup/validation recur on rebuild',
                         'validationContract': 'cache/logits close at declared tolerance; complete generated tokens exact'}

    @staticmethod
    def _sync(tensor):
        """Only synchronize an already-used CUDA device; CPU tests never initialize CUDA."""
        if tensor.is_cuda:
            torch.cuda.synchronize(tensor.device)

    def _inspect(self, inputs):
        """Restrict the first implementation to one unpadded image and a text prefix."""
        required = {'input_ids', 'attention_mask', 'mm_token_type_ids', 'image_grid_thw', 'pixel_values'}
        if set(inputs) != required:
            raise ValueError(f'Unexpected multimodal input fields: {set(inputs) ^ required}')
        ids, mask, types = (inputs[key] for key in ('input_ids', 'attention_mask', 'mm_token_type_ids'))
        if ids.ndim != 2 or ids.shape[0] != 1 or mask.shape != ids.shape or types.shape != ids.shape:
            raise ValueError('Prefix caching requires a single prompt with matching masks')
        if not bool((mask == 1).all()) or inputs['image_grid_thw'].shape != (1, 3):
            raise ValueError('Prefix caching requires one image and no padding')
        cpu_ids = ids.detach().cpu()
        starts = (cpu_ids[0] == self.model.config.vision_start_token_id).nonzero().flatten().tolist()
        if len(starts) != 1 or starts[0] == 0:
            raise ValueError('Expected exactly one image following a nonempty text prefix')
        split = starts[0]
        grid = inputs['image_grid_thw'][0].detach().cpu().tolist()
        merge = self.model.config.vision_config.spatial_merge_size
        image_tokens = grid[0]*grid[1]*grid[2] // (merge*merge)
        if grid[0] != 1 or any(size <= 0 for size in grid) or grid[1] % merge or grid[2] % merge:
            raise ValueError('Unsupported image grid')
        sequence = cpu_ids[0].tolist()
        if (sequence[split+1:split+1+image_tokens] != [self.model.config.image_token_id]*image_tokens
            or split+1+image_tokens >= len(sequence)
            or sequence[split+1+image_tokens] != self.model.config.vision_end_token_id):
            raise ValueError('Image placeholders do not match the processor grid')
        expected_types = torch.zeros_like(types)
        expected_types[:, split+1:split+1+image_tokens] = 1
        if not torch.equal(types, expected_types):
            raise ValueError('Unexpected history, video, or modality-token layout')
        return split, cpu_ids[:, :split]

    def prefill(self, inputs, cache):
        """Restore prefix state and run the image suffix at its original positions."""
        anchor = inputs['input_ids']
        self._sync(anchor)
        started = time.perf_counter_ns()
        split, prefix_ids = self._inspect(inputs)
        self._sync(anchor)
        inspected = time.perf_counter_ns()
        positions, delta = self.model.model.get_rope_index(
            inputs['input_ids'], image_grid_thw=inputs['image_grid_thw'],
            attention_mask=inputs['attention_mask'], mm_token_type_ids=inputs['mm_token_type_ids'])
        self._sync(anchor)
        positioned = time.perf_counter_ns()
        rebuild_reason = ('first-prefix' if self.snapshot is None else
                          'cache-replaced' if self.snapshot.cache is not cache else
                          'prefix-changed' if not torch.equal(prefix_ids, self.prefix_ids) else None)
        setup_ms = restore_ms = snapshot_ms = 0.0
        if rebuild_reason is not None:
            setup_started = time.perf_counter_ns()
            cache.reset()
            self.model.model.language_model(
                input_ids=anchor[:, :split], position_ids=positions[:, :, :split],
                attention_mask=inputs['attention_mask'][:, :split],
                past_key_values=cache, use_cache=True, return_dict=True)
            self._sync(anchor)
            snapshot_started = time.perf_counter_ns()
            self.snapshot = HybridCacheSnapshot(cache)
            self._sync(anchor)
            snapshot_ms = (time.perf_counter_ns()-snapshot_started)/1e6
            setup_ms = (time.perf_counter_ns()-setup_started)/1e6
            self.prefix_ids = prefix_ids.clone()
            self.metadata.update(validatedPrefills=0, validatedActions=0, prefixTokens=split,
                                 snapshotBytes=self.snapshot.bytes, snapshotTensorCount=self.snapshot.tensor_count)
            self.metadata['setupCount'] += 1
            self.metadata['totalSetupMs'] += setup_ms
        else:
            restore_started = time.perf_counter_ns()
            self.snapshot.restore(cache)
            self._sync(anchor)
            restore_ms = (time.perf_counter_ns()-restore_started)/1e6
            self.metadata['restoreCount'] += 1
            self.metadata['totalRestoreMs'] += restore_ms
        suffix_started = time.perf_counter_ns()
        suffix = dict(inputs)
        for key in ('input_ids', 'mm_token_type_ids'):
            suffix[key] = inputs[key][:, split:]
        # Passing the full prompt's sliced positions avoids the ordinary cached
        # decoder's text-only position inference for a new image.
        self.model.model.rope_deltas = delta
        output = self.model(**suffix, position_ids=positions[:, :, split:],
                            past_key_values=cache, use_cache=True, logits_to_keep=1, return_dict=True)
        self._sync(anchor)
        suffix_ms = (time.perf_counter_ns()-suffix_started)/1e6
        validation_ms = 0.0
        if self.metadata['validatedPrefills'] < self.validation_actions:
            validation_started = time.perf_counter_ns()
            actual_state = HybridCacheSnapshot(cache)
            capacity = next(layer.max_cache_len for layer in cache.layers if type(layer) is StaticLayer)
            reference_cache = StaticCache(self.model.config, max_cache_len=capacity)
            reference = self.model(**inputs, past_key_values=reference_cache,
                                   use_cache=True, logits_to_keep=1, return_dict=True)
            logit_deltas, cache_deltas = [], []
            try:
                _state_comparison(output.logits, reference.logits, 'logits', differences=logit_deltas)
                actual_state.compare(reference_cache, differences=cache_deltas)
                self.metadata['validatedPrefills'] += 1
            except AssertionError as exc:
                self.metadata['validationError'] = str(exc)
                raise
            finally:
                # Failed parity must retain its measured difference/cost too;
                # otherwise an aborted report could misleadingly show zero deltas.
                self.metadata['maxLogitAbsDelta'] = max(self.metadata['maxLogitAbsDelta'],
                                                        max((item['maxAbsDelta'] for item in logit_deltas), default=0.0))
                self.metadata['maxCacheAbsDelta'] = max(self.metadata['maxCacheAbsDelta'],
                                                        max((item['maxAbsDelta'] for item in cache_deltas), default=0.0))
                self.metadata['bitwiseEquivalent'] &= not logit_deltas and not cache_deltas
                self._sync(anchor)
                validation_ms = (time.perf_counter_ns()-validation_started)/1e6
                self.metadata['totalValidationMs'] += validation_ms
                self.metadata['lastValidation'] = {'logitDifferences': logit_deltas,
                                                    'cacheDifferences': cache_deltas,
                                                    'validationMs': validation_ms}
        self.metadata['lastRun'] = {'inspectionMs': (inspected-started)/1e6,
                                    'positionMs': (positioned-inspected)/1e6,
                                    'setupMs': setup_ms, 'snapshotCopyMs': snapshot_ms,
                                    'restoreMs': restore_ms, 'validationMs': validation_ms,
                                    'suffixMs': suffix_ms, 'rebuildReason': rebuild_reason,
                                    'setupGeneration': self.metadata['setupCount'],
                                    'validatedPrefills': self.metadata['validatedPrefills'],
                                    'snapshotBytes': self.snapshot.bytes,
                                    'maxCacheAbsDelta': self.metadata['maxCacheAbsDelta'],
                                    'maxLogitAbsDelta': self.metadata['maxLogitAbsDelta'],
                                    'bitwiseEquivalent': self.metadata['bitwiseEquivalent'],
                                    'totalPrefillMs': (time.perf_counter_ns()-started)/1e6,
                                    'promptTokens': anchor.shape[-1], 'suffixTokens': anchor.shape[-1]-split}
        return output

    def confirm_action(self, actual, reference):
        """The decoder must supply original-path complete IDs, using paired RNG."""
        torch.testing.assert_close(actual, reference, rtol=0, atol=0)
        self.metadata['validatedActions'] += 1
