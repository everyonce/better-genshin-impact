"""Fixed-capacity temporal history with explicitly masked unused entries.

The learned model, real RoPE positions, and rolling update remain unchanged.
Only policy-transformer caches are padded; action-decoder caches are untouched.
"""
from contextlib import contextmanager

import torch


class MaskedTemporalCache:
    """Make empty history graph-compatible without inventing prior observations."""

    def __init__(self, transformer):
        self.transformer = transformer
        self.cache = transformer.kv_cache
        self.capacity = self.cache.max_seq_len
        self.step_size = self.cache.step_size
        if self.step_size < 1 or self.capacity < self.step_size or self.capacity % self.step_size:
            raise ValueError('Temporal cache capacity must contain whole model steps')
        self.valid_tokens = torch.zeros((), dtype=torch.int64, device=self.cache.device)
        self.enabled = True
        self.original_masks = []
        layers = transformer._transformer.transformer_layers
        if not layers:
            raise ValueError('A temporal transformer must have attention layers')
        # Each attention layer shares the count, but keeps its original causal mask.
        for layer in layers:
            attention = layer.self_attention
            if attention.kv_cache is not self.cache or attention._mask_fn is None:
                raise ValueError('Unsupported temporal attention/cache layout')
            original = attention._mask_fn
            sinks = attention.n_kv_sink_tokens
            self.original_masks.append(original)
            attention._mask_fn = self._wrap(original, sinks)
            attention.precompute_decode_masks(q_seq_length=self.step_size)

    def _wrap(self, original, sinks):
        """Exclude only nonexistent prefix keys while retaining real sink tokens."""
        def mask(batch, head, query, key):
            allowed = original(batch, head, query, key)
            if not self.enabled:
                return allowed
            valid = (key < sinks) | (key >= sinks + self.capacity - self.valid_tokens)
            return allowed & valid
        return mask

    def empty_state(self):
        """Allocate left-padded zero storage; none of it represents history yet."""
        self.reset()
        states = self.transformer.init_kv_cache_state()
        shape = (*self.cache.cache_shape[:2], self.capacity, self.cache.cache_shape[3])
        return [type(state)(torch.zeros(shape, dtype=self.cache.dtype, device=self.cache.device),
                            torch.zeros(shape, dtype=self.cache.dtype, device=self.cache.device))
                for state in states]

    def reset(self):
        """Reset validity in place so an existing CUDA graph keeps the same buffer."""
        self.valid_tokens.zero_()

    def advance(self):
        """Expose one real current observation to both passes of a prediction."""
        self.valid_tokens.add_(self.step_size).clamp_(max=self.capacity)

    @contextmanager
    def reference_attention(self):
        """Temporarily use original masks for eager numerical validation only."""
        previous = self.enabled
        self.enabled = False
        try:
            yield
        finally:
            self.enabled = previous
