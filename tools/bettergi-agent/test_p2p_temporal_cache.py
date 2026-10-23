"""CPU checks for empty/padded attention and graph-stable reset storage."""
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple, Optional
import unittest

import torch

from p2p_compat_attention import create_block_mask, flex_attention
from p2p_temporal_cache import MaskedTemporalCache
from model_adapters import OpenP2PAdapter


class CacheState(NamedTuple):
    """The two tensor fields used by upstream inference cache states."""
    k_cache: torch.Tensor
    v_cache: torch.Tensor


class TemporalCacheTests(unittest.TestCase):
    """Test actual attention values, suffix validity, and reset rather than shapes alone."""

    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[2] / 'artifacts/agent/sources/open-p2p/elefant/policy_model/policy_transformer.py'
        if not source.exists():
            raise unittest.SkipTest('Official source checkout is needed for the original mask')
        tree = ast.parse(source.read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == '_img_policy_causal_mask')
        namespace = {'Optional': Optional}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        cls.factory = staticmethod(namespace['_img_policy_causal_mask'])

    def make_cache(self, history=8, sinks=0):
        """Attach the production mask wrapper to a minimal upstream-shaped layer."""
        step = 12
        cache = SimpleNamespace(max_seq_len=history*step, step_size=step,
                                cache_shape=(1, 2, 0, 8), device='cpu', dtype=torch.float32)
        original = self.factory(0, 1, 1, 9, history_len=history, n_text_tokens=1, n_kv_sink_tokens=sinks)
        attention = SimpleNamespace(kv_cache=cache, _mask_fn=original, n_kv_sink_tokens=sinks)
        def precompute(q_seq_length):
            attention.mask = create_block_mask(
                lambda b, h, q, k: attention._mask_fn(b, h, q+cache.max_seq_len-step, k),
                Q_LEN=q_seq_length, KV_LEN=cache.max_seq_len+sinks)
        attention.precompute_decode_masks = precompute
        transformer = SimpleNamespace(kv_cache=cache,
            _transformer=SimpleNamespace(transformer_layers=[SimpleNamespace(self_attention=attention)]),
            init_kv_cache_state=lambda: [CacheState(torch.zeros(cache.cache_shape), torch.zeros(cache.cache_shape))])
        return MaskedTemporalCache(transformer), attention, original

    def test_padding_matches_original_attention_and_never_becomes_history(self):
        torch.manual_seed(81)
        for sinks in (0, 1):
            cache, attention, original = self.make_cache(sinks=sinks)
            state = cache.empty_state()[0]
            self.assertEqual(cache.valid_tokens.item(), 0)
            self.assertEqual(torch.count_nonzero(state.k_cache).item(), 0)
            for observed in range(1, 11):
                cache.advance()
                valid = min(observed*cache.step_size, cache.capacity)
                self.assertEqual(cache.valid_tokens.item(), valid)
                q = torch.randn(1, 2, cache.step_size, 8)
                k, v = torch.randn(1, 2, sinks+valid, 8), torch.randn(1, 2, sinks+valid, 8)
                # Deliberately poison unused padding to prove it is excluded.
                padding = torch.full((1, 2, cache.capacity-valid, 8), 10000.0)
                padded_k = torch.cat((k[:, :, :sinks], padding, k[:, :, sinks:]), dim=2)
                padded_v = torch.cat((v[:, :, :sinks], padding, v[:, :, sinks:]), dim=2)
                reference_mask = create_block_mask(
                    lambda b, h, qi, ki: original(b, h, qi+valid-cache.step_size, ki))
                reference = flex_attention(q, k, v, reference_mask)
                actual = flex_attention(q, padded_k, padded_v, attention.mask)
                torch.testing.assert_close(actual, reference, rtol=2e-5, atol=2e-5)

    def test_reset_reuses_count_storage_and_reference_mode_restores_after_error(self):
        cache, attention, original = self.make_cache()
        pointer = cache.valid_tokens.data_ptr()
        cache.advance()
        cache.reset()
        self.assertEqual(cache.valid_tokens.data_ptr(), pointer)
        self.assertEqual(cache.valid_tokens.item(), 0)
        with self.assertRaisesRegex(RuntimeError, 'test interruption'):
            with cache.reference_attention():
                self.assertFalse(cache.enabled)
                raise RuntimeError('test interruption')
        self.assertTrue(cache.enabled)

    def test_rejected_action_restores_exact_history_without_changing_storage(self):
        policy = object.__new__(OpenP2PAdapter)
        policy.execution_feedback, policy._pending_feedback = True, False
        policy._history_backup = None
        policy.state = [CacheState(torch.arange(12).reshape(1, 1, 3, 4).float(), torch.ones(1, 1, 3, 4))]
        policy.idx, policy.steps_seen = torch.tensor(24), 2
        policy.temporal_cache = SimpleNamespace(valid_tokens=torch.tensor(24))
        pointers = [policy.idx.data_ptr(), policy.state[0].k_cache.data_ptr(), policy.temporal_cache.valid_tokens.data_ptr()]
        expected = policy.state[0].k_cache.clone()
        policy._begin_history_transaction()
        with self.assertRaisesRegex(RuntimeError, 'Resolve'):
            policy._begin_history_transaction()
        policy.state[0].k_cache.add_(100)
        policy.idx.add_(12)
        policy.temporal_cache.valid_tokens.add_(12)
        policy.steps_seen += 1
        policy.finish_action(False)
        torch.testing.assert_close(policy.state[0].k_cache, expected, rtol=0, atol=0)
        self.assertEqual((policy.idx.item(), policy.steps_seen, policy.temporal_cache.valid_tokens.item()), (24, 2, 24))
        self.assertEqual(pointers, [policy.idx.data_ptr(), policy.state[0].k_cache.data_ptr(), policy.temporal_cache.valid_tokens.data_ptr()])
        policy._begin_history_transaction()
        policy.state[0].k_cache.add_(2)
        policy.finish_action(True)
        torch.testing.assert_close(policy.state[0].k_cache, expected+2, rtol=0, atol=0)
        with self.assertRaisesRegex(RuntimeError, 'pending'):
            policy.finish_action(True)


if __name__ == '__main__':
    unittest.main()
