"""Whole-token CUDA decode graph using Transformers' supported static hybrid cache.

The original multimodal model still handles every prefill. Only single-token
greedy decode is captured. First capture checks logits and every mutated cache
tensor against eager execution; the first two complete actions are also checked
against the original generate() path before this optimization is trusted.
"""
import torch
from transformers import StaticCache


class StaticGreedyDecode:
    """Retain stable cache buffers across independent, unpadded single-item prompts."""
    def __init__(self, model):
        self.model = model
        self.cache = None
        self.graph = None
        self.capacity = 0
        self.metadata = {'implementation': 'whole-token static-hybrid-cache CUDA graph',
                         'graphValidated': False, 'validatedActions': 0, 'decodeReplays': 0}

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
        """Return original-format token IDs, with the same greedy EOS/budget rules."""
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
        else:
            self.cache.reset()
        output = self.model(**inputs, past_key_values=self.cache, use_cache=True,
                            logits_to_keep=1, return_dict=True)
        logits = output.logits[:, -1, :]
        self.position.fill_(prompt_length)
        self.rope_delta.copy_(self.model.model.rope_deltas.reshape(()))
        if self.graph is not None and self.cache_pointers != [tensor.data_ptr() for tensor in self._cache_tensors()]:
            raise RuntimeError('Transformers replaced a captured cache buffer; refusing stale graph replay')
        streamer.put(inputs['input_ids'])
        generated = []
        for _ in range(max_new_tokens):
            token = logits.argmax(dim=-1).view(1, 1)
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
        if self.metadata['validatedActions'] < 2:
            # Expensive only during warmup. Exact token equality catches EOS,
            # positional, cache-reset, or generation-policy changes immediately.
            reference = self.model.generate(**inputs, do_sample=False, use_cache=True,
                                            max_new_tokens=max_new_tokens, eos_token_id=eos_token_id)
            torch.testing.assert_close(result, reference, rtol=0, atol=0)
            self.metadata['validatedActions'] += 1
        return result
