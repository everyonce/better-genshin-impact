"""CPU-only sampling contract checks; never loads weights or initializes CUDA."""
import math
from unittest import mock
import unittest

import torch
from transformers.generation.logits_process import LogitsProcessorList, TemperatureLogitsWarper, TopKLogitsWarper, TopPLogitsWarper

from benchmark import arguments
from gamescaling_decode import sampling_options, select_token
from stream_client import load_policy, parse_arguments


class GameScalingSamplingTests(unittest.TestCase):
    """Protect the greedy path and explicit sampling support/truncation semantics."""
    def test_greedy_preserves_argmax_and_does_not_consume_randomness(self):
        self.assertIsNone(sampling_options())
        logits = torch.tensor([[0.5, 3.0, -2.0], [9.0, 1.0, 9.0]], dtype=torch.float16)
        before = torch.random.get_rng_state()
        self.assertEqual(select_token(logits).tolist(), [[1], [0]])
        self.assertTrue(torch.equal(before, torch.random.get_rng_state()))

    def test_temperature_one_does_not_inherit_top_k_fifty(self):
        options = sampling_options('sample')
        self.assertEqual(options, dict(do_sample=True, temperature=1.0, top_k=0, top_p=1.0))
        # All vocabulary entries remain reachable, including those beyond 50.
        torch.manual_seed(71)
        tokens = select_token(torch.zeros(1024, 64, dtype=torch.float16), options)
        self.assertEqual(set(tokens.flatten().tolist()), set(range(64)))

    def test_filtering_and_float_conversion_match_transformers(self):
        logits = torch.tensor([[0.0, 0.1, 0.3, 0.8, 1.4], [2.0, 2.0, 1.0, 0.0, -3.0]], dtype=torch.float16)
        original = logits.clone()
        options = sampling_options('sample', temperature=0.65, top_k=3, top_p=0.9)
        processors = LogitsProcessorList([TemperatureLogitsWarper(0.65), TopKLogitsWarper(3), TopPLogitsWarper(0.9)])
        scores = processors(torch.empty((2, 0), dtype=torch.long), logits.to(dtype=torch.float32, copy=True))
        for seed in range(8):
            torch.manual_seed(seed)
            expected = torch.multinomial(torch.softmax(scores, dim=-1), num_samples=1)
            torch.manual_seed(seed)
            self.assertTrue(torch.equal(select_token(logits, options), expected))
        self.assertTrue(torch.equal(logits, original))

    def test_top_k_one_retains_only_the_most_likely_token(self):
        logits = torch.tensor([[1.0, 4.0, 2.0]]).repeat(100, 1)
        sampled = select_token(logits, sampling_options('sample', top_k=1))
        self.assertTrue(bool((sampled == 1).all()))

    def test_invalid_or_silently_ignored_settings_are_rejected(self):
        for options in [dict(mode='beam'), dict(temperature=0), dict(temperature=math.nan),
                        dict(temperature=math.inf), dict(top_k=-1), dict(top_k=True),
                        dict(top_p=0), dict(top_p=1.1), dict(top_p=math.nan),
                        dict(mode='greedy', temperature=0.8), dict(mode='greedy', top_k=50),
                        dict(mode='greedy', top_p=0.9)]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                sampling_options(**options)

    def test_benchmark_defaults_and_explicit_comparison_arguments(self):
        required = ['benchmark.py', '--model', 'gamescaling', '--checkpoint', 'weights',
                    '--source', 'source', '--images', 'one.png', '--output', 'out.json']
        with mock.patch('sys.argv', required):
            defaults = arguments()
        self.assertEqual((defaults.sampling, defaults.temperature, defaults.top_k, defaults.top_p, defaults.sample_mode),
                         ('greedy', 1.0, 0, 1.0, 'latest'))
        with mock.patch('sys.argv', required + ['--sampling', 'sample', '--temperature', '0.8',
                                              '--top-k', '16', '--top-p', '0.95', '--sample-mode', 'independent']):
            selected = arguments()
        self.assertEqual((selected.sampling, selected.temperature, selected.top_k, selected.top_p, selected.sample_mode),
                         ('sample', 0.8, 16, 0.95, 'independent'))

    def test_live_selection_reaches_the_adapter_without_loading_weights(self):
        args = parse_arguments(['--model', 'gamescaling', '--checkpoint', 'weights', '--source', 'source',
                                '--output', 'out.json', '--sampling', 'sample', '--temperature', '0.8',
                                '--top-k', '16', '--top-p', '0.95'])
        with mock.patch('model_adapters.make_adapter') as factory:
            self.assertIs(load_policy(args), factory.return_value)
        self.assertEqual({key: factory.call_args.kwargs[key] for key in ('sampling', 'temperature', 'top_k', 'top_p')},
                         dict(sampling='sample', temperature=0.8, top_k=16, top_p=0.95))

    def test_live_cli_rejects_ignored_or_invalid_sampling_before_loading(self):
        base = ['--model', 'gamescaling', '--checkpoint', 'weights', '--source', 'source', '--output', 'out.json']
        for extra in (['--top-k', '50'], ['--sampling', 'sample', '--temperature', 'nan'],
                      ['--sampling', 'sample', '--top-p', '0'], ['--sampling', 'sample', '--top-k', '-1'],
                      ['--model', 'observe', '--sampling', 'sample']):
            with self.subTest(extra=extra), mock.patch('sys.stderr'), self.assertRaises(SystemExit):
                parse_arguments(base + extra)


if __name__ == '__main__':
    unittest.main()
