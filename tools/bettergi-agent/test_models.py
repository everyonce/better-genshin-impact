"""Numerical and protocol boundary tests for the native pretrained adapters."""
import ast
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Optional
import unittest

import torch

from model_adapters import canonical_key, complete_gamescaling_action, gamescaling_steps
from p2p_compat_attention import create_block_mask, flex_attention
from p2p_rotary import rotary_values, restore_rotary_precision
from action_validation import action_observations


class AdapterBoundaryTests(unittest.TestCase):
    """Protect unit conversion, case-sensitive keys and complete-action validation."""
    def test_digit_function_and_arrow_distinctions(self):
        self.assertEqual(canonical_key('one'), '1')
        self.assertEqual(canonical_key('One'), 'F1')
        self.assertEqual(canonical_key('Left'), 'LEFT')
        self.assertEqual(canonical_key('LB'), 'LBUTTON')

    def test_whole_chunk_mouse_is_applied_once(self):
        action = SimpleNamespace(parsed=True, truncated=False, dropped=[],
                                 mouse=(100, -50, 0), steps=[['W']] * 6)
        steps = gamescaling_steps(action, 1920, 1080)
        self.assertEqual(sum(step['durationMs'] for step in steps), 200)
        self.assertEqual(sum(step['mouseDx'] for step in steps), 192)
        self.assertEqual(sum(step['mouseDy'] for step in steps), -54)
        self.assertTrue(all(step['mouseDx'] == 0 for step in steps[1:]))

    def test_unusable_and_nonfinite_outputs_are_rejected(self):
        action = SimpleNamespace(parsed=True, truncated=False, dropped=[], body='0 0 0 ; W ; ; ; ; ;')
        self.assertTrue(complete_gamescaling_action('<|action_end|>', action))
        self.assertFalse(complete_gamescaling_action('', action))
        for body in ['nan 0 0 ; W ; ; ; ; ;', '0 0 0 ; W ; ;', '0 0 0 ; W A S D Q ; ; ; ; ;']:
            action.body = body
            self.assertFalse(complete_gamescaling_action('<|action_end|>', action))

    def test_parsing_does_not_imply_protocol_compatibility_or_nonzero_action(self):
        action = {'parseValid': True, 'steps': [{'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}]}
        self.assertEqual(action_observations(action, (1920, 1080)),
                         {'protocolCompatible': True, 'protocolRejection': None, 'noOpAction': True})
        action['scrollUnsupported'] = True
        self.assertEqual(action_observations(action, (1920, 1080))['protocolRejection'], 'unsupported_scroll')
        action['scrollUnsupported'] = False
        action['steps'][0]['keys'] = ['UNKNOWN']
        self.assertEqual(action_observations(action, (1920, 1080))['protocolRejection'], 'unsupported_keys')
        action['steps'][0]['keys'] = ['LCONTROL', 'ESCAPE']
        self.assertEqual(action_observations(action, (1920, 1080))['protocolRejection'], 'reserved_hotkey')


class AttentionCompatibilityTests(unittest.TestCase):
    """Compare SDPA to explicit masked-softmax attention on the upstream mask."""
    def test_exact_upstream_mask_and_decode_offset(self):
        source = Path(__file__).resolve().parents[2] / 'artifacts/agent/sources/open-p2p/elefant/policy_model/policy_transformer.py'
        if not source.exists():
            self.skipTest('Official source checkout is required for upstream mask comparison')
        tree = ast.parse(source.read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_img_policy_causal_mask')
        namespace = {'Optional': Optional}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        factory = namespace['_img_policy_causal_mask']
        torch.manual_seed(17)
        for sinks in [0, 1]:
            upstream = factory(0, 1, 1, 9, history_len=3, n_text_tokens=1, n_kv_sink_tokens=sinks)
            for offset in [0, 12, 24]:
                shifted = lambda b, h, q, k: upstream(b, h, q + offset, k)
                mask = create_block_mask(shifted, Q_LEN=12, KV_LEN=36+sinks)
                q = torch.randn(1, 2, 12, 8)
                k, v = torch.randn(1, 2, 36+sinks, 8), torch.randn(1, 2, 36+sinks, 8)
                actual = flex_attention(q, k, v, mask)
                allowed = torch.tensor([[bool(upstream(0, 0, qi+offset, ki))
                                         for ki in range(36+sinks)] for qi in range(12)])
                scores = q @ k.transpose(-1, -2) / math.sqrt(8)
                expected = torch.softmax(scores.masked_fill(~allowed, float('-inf')), dim=-1) @ v
                torch.testing.assert_close(actual, expected, rtol=2e-5, atol=2e-5)

    def test_rotary_matches_upstream_beyond_fp16_position_limit(self):
        source = Path(__file__).resolve().parents[2] / 'artifacts/agent/sources/open-p2p/elefant/policy_model/pos_embed.py'
        if not source.exists():
            self.skipTest('Official source checkout is required for rotary comparison')
        namespace = {}
        exec(compile(source.read_text(encoding='utf-8'), str(source), 'exec'), namespace)
        rotary_class = namespace['RotaryPositionalEmbeddings']
        reference = rotary_class(dim=64, max_seq_len=100000)
        # Compare exact upstream cache values at/after half-precision rounding
        # and overflow thresholds, including batched packed positions.
        positions = torch.tensor([[0, 2049, 65520, 99999]])
        adapted = rotary_class(dim=64, max_seq_len=12).half()
        restore_rotary_precision(adapted)
        values = rotary_values(adapted.theta, 4, positions)
        self.assertTrue(torch.isfinite(values).all())
        self.assertEqual(adapted.theta.dtype, torch.float32)
        torch.testing.assert_close(values, reference.cache[positions], rtol=0, atol=0)
        torch.testing.assert_close(rotary_values(adapted.theta, 12), reference.cache[:12], rtol=0, atol=0)


if __name__ == '__main__':
    unittest.main()
