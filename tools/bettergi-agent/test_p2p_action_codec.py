"""CPU-only checks against the official P2P action decoder and checkpoint config."""
import ast
from copy import deepcopy
import json
import logging
import math
import io
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import List, NamedTuple, Optional
import unittest
from unittest.mock import patch

import pydantic
import torch

from model_adapters import OpenP2PAdapter
from p2p_action_codec import resolve_mouse_sampling


class MouseSamplingConfigTests(unittest.TestCase):
    """A checkpoint default and an explicit reproducibility override are distinct."""

    def test_checkpoint_default_override_and_missing_config_fallback(self):
        with TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / 'weights.ckpt'
            config = checkpoint.with_name('model_config.yaml')
            self.assertEqual(resolve_mouse_sampling(checkpoint, fallback='conservative'),
                             ('conservative', 'upstream-config-fallback'))
            config.write_text('inference:\n  mouse_sampling_approach: truncated_normal\n', encoding='utf-8')
            self.assertEqual(resolve_mouse_sampling(checkpoint), ('truncated_normal', 'checkpoint-config'))
            self.assertEqual(resolve_mouse_sampling(checkpoint, 'mean'), ('mean', 'explicit-override'))
            config.write_text('shared: {}\n', encoding='utf-8')
            self.assertEqual(resolve_mouse_sampling(checkpoint), ('mean', 'checkpoint-config'))

    def test_malformed_checkpoint_setting_cannot_silently_change_decoder(self):
        with TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / 'weights.ckpt'
            for content in ('[]', 'inference: null', 'inference:\n  mouse_sampling_approach: invalid'):
                checkpoint.with_name('model_config.yaml').write_text(content, encoding='utf-8')
                with self.assertRaises(ValueError):
                    resolve_mouse_sampling(checkpoint)
            with self.assertRaises(ValueError):
                resolve_mouse_sampling(checkpoint, 'invalid')

    def test_adapter_reports_the_actual_checkpoint_mode_and_legacy_override(self):
        # Constructor plumbing is exercised without creating a model or CUDA state.
        config = SimpleNamespace(inference=SimpleNamespace(mouse_sampling_approach='mean'))
        model = SimpleNamespace(parameters=lambda: [])
        with TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / 'weights.ckpt'
            checkpoint.with_name('model_config.yaml').write_text(
                'inference:\n  mouse_sampling_approach: truncated_normal\n', encoding='utf-8')
            with patch('p2p_loader.load_model', return_value=(model, config, {})), \
                    patch.object(OpenP2PAdapter, 'reset'):
                policy = OpenP2PAdapter(checkpoint, 'unused', 'unused')
                legacy = OpenP2PAdapter(checkpoint, 'unused', 'unused', p2p_mouse_sampling='mean')
            self.assertEqual(policy.mouse_sampling, 'truncated_normal')
            self.assertEqual(policy.metadata['mouseSampling'], 'truncated_normal')
            self.assertEqual(policy.metadata['mouseSamplingSource'], 'checkpoint-config')
            self.assertEqual(legacy.mouse_sampling, 'mean')
            self.assertEqual(legacy.metadata['mouseSamplingSource'], 'explicit-override')

    def test_cli_defaults_overrides_and_stream_factory_plumbing(self):
        import benchmark
        import stream_client
        base = ['--model', 'open-p2p', '--checkpoint', 'weights.ckpt', '--source', 'source',
                '--output', 'unused.json']
        for mode in (None, 'mean', 'conservative', 'truncated_normal'):
            options = [] if mode is None else ['--p2p-mouse-sampling', mode]
            args = stream_client.parse_arguments(base + options)
            self.assertEqual(args.p2p_mouse_sampling, mode)
            with patch('model_adapters.make_adapter') as factory:
                stream_client.load_policy(args)
                self.assertEqual(factory.call_args.kwargs['p2p_mouse_sampling'], mode)
            with patch('sys.argv', ['benchmark'] + base + ['--images', 'frame.png'] + options):
                self.assertEqual(benchmark.arguments().p2p_mouse_sampling, mode)

    def test_both_cli_parsers_reject_mouse_overrides_for_gamescaling(self):
        import benchmark
        import stream_client
        base = ['--model', 'gamescaling', '--checkpoint', 'weights', '--source', 'source',
                '--output', 'unused.json', '--p2p-mouse-sampling', 'mean']
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                stream_client.parse_arguments(base)
            with patch('sys.argv', ['benchmark'] + base + ['--images', 'frame.png']):
                with self.assertRaises(SystemExit):
                    benchmark.arguments()


class OfficialMouseDecoderTests(unittest.TestCase):
    """Use upstream code, including its bin edges, bounds and integer rounding."""

    @classmethod
    def setUpClass(cls):
        source = Path(__file__).resolve().parents[2] / 'artifacts/agent/sources/open-p2p/elefant/data/action_mapping.py'
        if not source.is_file():
            raise unittest.SkipTest('Official Open P2P source checkout is required')
        tree = ast.parse(source.read_text(encoding='utf-8'))
        classes = {'StructuredAction', 'UniversalAutoregressiveActionMappingConfig',
                   'UniversalAutoregressiveActionMapping'}
        nodes = [node for node in tree.body if isinstance(node, ast.Assign)
                 or isinstance(node, ast.ClassDef) and node.name in classes
                 or isinstance(node, ast.FunctionDef) and node.name == 'obtain_lower_upper_bound']
        future = ast.parse('from __future__ import annotations').body
        namespace = {'torch': torch, 'pydantic': pydantic, 'ConfigBase': pydantic.BaseModel,
                     'Optional': Optional, 'NamedTuple': NamedTuple, 'List': List,
                     'math': math, 'json': json, 'logging': logging, 'deepcopy': deepcopy}
        exec(compile(ast.Module(body=future + nodes, type_ignores=[]), str(source), 'exec'), namespace)
        cls.upstream = namespace
        cls.mapping = namespace['UniversalAutoregressiveActionMapping']()

    def action(self, x=21, y=15):
        """Use wide positive mouse bins and nonempty keyboard/mouse-button tokens."""
        return self.upstream['StructuredAction'](
            torch.tensor([[11, 18, 0, 0]]), torch.tensor([[1, 0]]),
            torch.tensor([[x]]), torch.tensor([[y]]))

    def test_seeded_official_sampling_replays_and_preserves_keys_and_bin_tokens(self):
        action = self.action()
        original = [part.clone() for part in action]
        def sample(seed):
            with torch.random.fork_rng(devices=[]):
                torch.manual_seed(seed)
                return [self.mapping.tensor_to_action(action, 'truncated_normal') for _ in range(32)]
        first, repeat = sample(427), sample(427)
        self.assertEqual(first, repeat)
        self.assertGreater(len({(a.mouse_delta_x, a.mouse_delta_y) for a in first}), 1)
        for decoded in first:
            self.assertEqual(decoded.keys, ['LeftShift', 'w'])
            self.assertEqual(decoded.mouse_buttons, ['0'])
            self.assertTrue(145 <= decoded.mouse_delta_x <= 500)
            self.assertTrue(25 <= decoded.mouse_delta_y <= 150)
        for before, after in zip(original, action):
            self.assertTrue(torch.equal(before, after))
        mean = self.mapping.tensor_to_action(action, 'mean')
        self.assertEqual((mean.mouse_delta_x, mean.mouse_delta_y), (322, 87))

    def test_zero_and_nonzero_bins_preserve_noop_identity(self):
        # Truncated-normal decoding must not invent movement in the zero bin or
        # erase a nonzero bin. This cannot cure empty keyboard/zero-mouse tokens.
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(812)
            for x in range(self.mapping.get_n_mouse_x_bins()):
                for y in range(self.mapping.get_n_mouse_y_bins()):
                    action = self.action(x, y)
                    mean = self.mapping.tensor_to_action(action, 'mean')
                    sampled = self.mapping.tensor_to_action(action, 'truncated_normal')
                    self.assertEqual(sampled.mouse_delta_x == 0, mean.mouse_delta_x == 0)
                    self.assertEqual(sampled.mouse_delta_y == 0, mean.mouse_delta_y == 0)
                    self.assertEqual(sampled.keys, mean.keys)
                    self.assertEqual(sampled.mouse_buttons, mean.mouse_buttons)

    def test_explicit_mean_preserves_old_values_without_consuming_rng(self):
        before = torch.random.get_rng_state()
        decoded = self.mapping.tensor_to_action(self.action(), 'mean')
        self.assertEqual((decoded.mouse_delta_x, decoded.mouse_delta_y), (322, 87))
        self.assertTrue(torch.equal(before, torch.random.get_rng_state()))


if __name__ == '__main__':
    unittest.main()
