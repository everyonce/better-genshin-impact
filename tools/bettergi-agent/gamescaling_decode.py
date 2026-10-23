"""Whole-token CUDA decode graph using Transformers' supported static hybrid cache.

The original multimodal model handles prefills, optionally restoring a validated
text prefix. Only single-token decode is captured; token selection remains outside the graph. First capture checks logits and every mutated cache
tensor against eager execution; the first two complete actions are also checked
against the original generate() path before this optimization is trusted.
"""
import math
import time
import torch
from transformers import StaticCache
from transformers.generation.logits_process import TemperatureLogitsWarper, TopKLogitsWarper, TopPLogitsWarper


def sampling_options(mode='greedy', temperature=1.0, top_k=0, top_p=1.0):
    """Make sampling explicit, including disabling Transformers' default top-k=50.

    None preserves the existing greedy path and its generate() arguments exactly.
    The official client sends temperature=1.0; top-k/top-p are server defaults.
    """
    if mode not in ('greedy', 'sample'):
        raise ValueError('Sampling mode must be greedy or sample')
    if type(temperature) not in (int, float) or not math.isfinite(temperature) or temperature <= 0:
        raise ValueError('Sampling temperature must be finite and positive')
    if type(top_k) is not int or top_k < 0:
        raise ValueError('Sampling top-k must be a nonnegative integer; 0 disables filtering')
    if type(top_p) not in (int, float) or not math.isfinite(top_p) or not 0 < top_p <= 1:
        raise ValueError('Sampling top-p must be in (0,1]')
    if mode == 'greedy':
        if (temperature, top_k, top_p) != (1.0, 0, 1.0):
            raise ValueError('Temperature/top-k/top-p overrides require sampling mode sample')
        return None
    return dict(do_sample=True, temperature=float(temperature), top_k=top_k, top_p=float(top_p))


def select_token(logits, options=None):
    """Select from graph logits using the same FP32 warpers as HF generate()."""
    if options is None:
        return logits.argmax(dim=-1).view(-1, 1)
    scores = logits.to(dtype=torch.float32, copy=True)
    # These warpers do not inspect the prefix; repeated-token penalties are not
    # part of this preset. Keep the ordering used by Transformers generation.
    if options['temperature'] != 1.0:
        scores = TemperatureLogitsWarper(options['temperature'])(None, scores)
    if options['top_k']:
        scores = TopKLogitsWarper(options['top_k'])(None, scores)
    if options['top_p'] < 1.0:
        scores = TopPLogitsWarper(options['top_p'])(None, scores)
    return torch.multinomial(torch.softmax(scores, dim=-1), num_samples=1)


class StaticGreedyDecode:
    """Retain stable cache buffers across independent, unpadded single-item prompts."""
    def __init__(self, model, sampling=None, prefix_cache=False):
        self.model = model
        self.sampling = None if sampling is None else dict(sampling)
        self.cache = None
        self.graph = None
        self.capacity = 0
        self.prefix = None
        if prefix_cache:
            from gamescaling_prefix import InvariantTextPrefix
            self.prefix = InvariantTextPrefix(model)
        self.metadata = {'implementation': 'whole-token static-hybrid-cache CUDA graph',
                         'graphValidated': False, 'validatedActions': 0, 'decodeReplays': 0,
                         'tokenSelection': 'greedy' if sampling is None else 'sample',
                         'sampling': self.sampling,
                         'actionValidation': 'exact greedy tokens' if sampling is None else 'exact sampled tokens with restored CUDA RNG'}
        if self.prefix is not None:
            self.metadata['prefixCache'] = self.prefix.metadata

    def _needs_action_validation(self):
        """A rebuilt prefix/cache needs fresh checks even after the graph was validated."""
        return self.metadata['validatedActions'] < 2 or (
            self.prefix is not None
            and self.prefix.metadata['validatedActions'] < self.prefix.validation_actions)

    def _validate_action(self, inputs, result, max_new_tokens, eos_token_id, rng_before):
        """Compare the full original generation and preserve the caller's sampling RNG."""
        if not self._needs_action_validation():
            return 0.0
        torch.cuda.synchronize(inputs['input_ids'].device)
        started = time.perf_counter_ns()
        if self.sampling is None:
            reference = self.model.generate(**inputs, do_sample=False, use_cache=True,
                                            max_new_tokens=max_new_tokens, eos_token_id=eos_token_id)
        else:
            if rng_before is None:
                raise RuntimeError('Sampled action validation requires the pre-generation CUDA RNG state')
            rng_after = torch.cuda.get_rng_state(inputs['input_ids'].device)
            try:
                torch.cuda.set_rng_state(rng_before, inputs['input_ids'].device)
                reference = self.model.generate(**inputs, **self.sampling, use_cache=True,
                                                max_new_tokens=max_new_tokens, eos_token_id=eos_token_id)
            finally:
                torch.cuda.set_rng_state(rng_after, inputs['input_ids'].device)
        if self.prefix is None:
            torch.testing.assert_close(result, reference, rtol=0, atol=0)
        else:
            self.prefix.confirm_action(result, reference)
        self.metadata['validatedActions'] += 1
        torch.cuda.synchronize(inputs['input_ids'].device)
        elapsed = (time.perf_counter_ns()-started)/1e6
        if self.prefix is not None:
            self.prefix.metadata['totalActionValidationMs'] += elapsed
        return elapsed

    def _cache_tensors(self):
        """Enumerate every numerical state that the supported hybrid cache mutates."""
        result = []
        for layer in self.cache.layers:
            for name in ('keys', 'values', 'cumulative_length', 'conv_states', 'recurrent_states'):
                value = getattr(layer, name, None)
                values = value.values() if isinstance(value, dict) else [value]
                result.extend(item for item in values if isinstance(item, torch.Tensor))
        return result

    def _decode(self):
        """Run exactly one cached text token with explicit device-side positions/mask."""
        positions = (self.position + self.rope_delta).view(1, 1, 1).expand(3, 1, 1)
        mask = (self.cache_indices <= self.position).view(1, 1, 1, -1)
        output = self.model.model.language_model(
            input_ids=self.token, position_ids=positions,
            attention_mask={'full_attention': mask, 'linear_attention': None},
            past_key_values=self.cache, use_cache=True, return_dict=True)
        logits = self.model.lm_head(output.last_hidden_state[:, -1, :])
        self.position.add_(1)
        return logits

    def _capture(self):
        """Warm/capture without consuming any real generation state twice."""
        live = self._cache_tensors() + [self.position]
        saved = [tensor.clone() for tensor in live]

        def restore():
            for target, value in zip(live, saved):
                target.copy_(value)

        stream = torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            for _ in range(2):
                restore()
                reference_logits = self._decode()
            reference_state = [tensor.clone() for tensor in live]
        torch.cuda.current_stream().wait_stream(stream)
        torch.cuda.synchronize()
        restore()
        self.graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(self.graph, stream=stream):
            self.logits = self._decode()
        restore()
        self.graph.replay()
        torch.cuda.synchronize()
        torch.testing.assert_close(self.logits, reference_logits, rtol=1e-3, atol=1e-3)
        for actual, expected in zip(live, reference_state):
            torch.testing.assert_close(actual, expected, rtol=1e-3, atol=1e-3)
        restore()
        self.cache_pointers = [tensor.data_ptr() for tensor in self._cache_tensors()]
        self.metadata['graphValidated'] = True

    def generate(self, inputs, max_new_tokens, eos_token_id, streamer):
        """Return original-format IDs with explicit selection and shared EOS/budget rules."""
        if inputs['input_ids'].shape[0] != 1 or not bool((inputs['attention_mask'] == 1).all()):
            raise ValueError('The decode graph supports one unpadded prompt at a time')
        prompt_length = inputs['input_ids'].shape[1]
        required = prompt_length + max_new_tokens
        if self.cache is None or required > self.capacity:
            self.capacity = ((required + 255) // 256) * 256
            self.cache = StaticCache(config=self.model.config, max_cache_len=self.capacity)
            self.graph = None
            self.metadata['graphValidated'] = False
            self.token = torch.empty((1, 1), dtype=torch.long, device='cuda')
            self.position = torch.zeros((), dtype=torch.long, device='cuda')
            self.rope_delta = torch.zeros((), dtype=torch.long, device='cuda')
            self.cache_indices = torch.arange(self.capacity, device='cuda')
        elif self.prefix is None:
            self.cache.reset()
        # Replay and eager validation must see the same random draws. Validation
        # must not consume an additional sequence from the caller's generator.
        # A new prefix can be discovered during prefill. Preserve RNG whenever
        # prefix reuse is enabled, even if prior actions already passed checks.
        validate_sampling = self.sampling is not None and (self.prefix is not None or self._needs_action_validation())
        rng_before = torch.cuda.get_rng_state(inputs['input_ids'].device) if validate_sampling else None
        if self.prefix is None:
            output = self.model(**inputs, past_key_values=self.cache, use_cache=True,
                                logits_to_keep=1, return_dict=True)
        else:
            output = self.prefix.prefill(inputs, self.cache)
        logits = output.logits[:, -1, :]
        self.position.fill_(prompt_length)
        self.rope_delta.copy_(self.model.model.rope_deltas.reshape(()))
        if self.graph is not None and self.cache_pointers != [tensor.data_ptr() for tensor in self._cache_tensors()]:
            raise RuntimeError('Transformers replaced a captured cache buffer; refusing stale graph replay')
        streamer.put(inputs['input_ids'])
        generated = []
        for _ in range(max_new_tokens):
            token = select_token(logits, self.sampling)
            token_cpu = token.cpu()
            streamer.put(token_cpu)
            generated.append(token)
            if token_cpu.item() in eos_token_id:
                break
            self.token.copy_(token)
            if self.graph is None:
                self._capture()
            self.graph.replay()
            self.metadata['decodeReplays'] += 1
            logits = self.logits
        streamer.end()
        result = torch.cat([inputs['input_ids']] + generated, dim=1)
        # Expensive startup/rebuild check, never a silent fallback. No proposal
        # leaves the adapter until original-path complete token equality passes.
        validation_ms = self._validate_action(inputs, result, max_new_tokens, eos_token_id, rng_before)
        if self.prefix is not None:
            self.prefix.metadata['lastRun']['actionValidationMs'] = validation_ms
            self.prefix.metadata['lastRun']['validatedActions'] = self.prefix.metadata['validatedActions']
        return result
