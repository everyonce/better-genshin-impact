"""CPU-only contract tests using tiny real Qwen3.5 modules, never checkpoint weights."""
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest import mock

import torch
from transformers import StaticCache
from transformers.models.qwen3_5.configuration_qwen3_5 import Qwen3_5Config
from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5ForConditionalGeneration

from gamescaling_prefix import HybridCacheSnapshot, InvariantTextPrefix
from gamescaling_decode import StaticGreedyDecode, sampling_options
from benchmark import arguments
from stream_client import load_policy, parse_arguments


class PrefixCacheTests(unittest.TestCase):
    """Exercise actual multimodal positions and hybrid flags with CPU tensors."""
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
        torch.manual_seed(71)
        config = Qwen3_5Config(
            text_config=dict(vocab_size=128, hidden_size=32, intermediate_size=64,
                             num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=1,
                             head_dim=16, linear_num_key_heads=2, linear_num_value_heads=2,
                             linear_key_head_dim=8, linear_value_head_dim=8,
                             layer_types=['linear_attention', 'full_attention'],
                             rope_parameters={'rope_type': 'default', 'rope_theta': 10000,
                                              'partial_rotary_factor': .5, 'mrope_section': [1, 1, 2]}),
            vision_config=dict(depth=1, hidden_size=32, intermediate_size=64, num_heads=2,
                               out_hidden_size=32, num_position_embeddings=64, patch_size=16,
                               spatial_merge_size=2, temporal_patch_size=2),
            image_token_id=120, vision_start_token_id=121, vision_end_token_id=122,
            video_token_id=123, eos_token_id=124, pad_token_id=0)
        config._attn_implementation = 'sdpa'
        cls.model = Qwen3_5ForConditionalGeneration(config).eval()

    def inputs(self, grid=4):
        """Build one text-prefix/image/text-suffix prompt with exact placeholder counts."""
        generator = torch.Generator().manual_seed(123)
        prefix = torch.randint(1, 110, (1, 70), generator=generator)
        count = grid*grid//4
        ids = torch.cat([prefix, torch.tensor([[121] + [120]*count + [122, 12, 13, 14]])], dim=1)
        types = torch.zeros_like(ids)
        types[:, 71:71+count] = 1
        return dict(input_ids=ids, attention_mask=torch.ones_like(ids), mm_token_type_ids=types,
                    image_grid_thw=torch.tensor([[1, grid, grid]]),
                    pixel_values=torch.randn((grid*grid, 3*2*16*16), generator=generator))

    def cache(self):
        return StaticCache(self.model.config, max_cache_len=128)

    @torch.inference_mode()
    def test_restores_flags_numbers_and_live_tensor_addresses(self):
        cache = self.cache()
        self.model(**self.inputs(), past_key_values=cache, use_cache=True, logits_to_keep=1)
        snapshot = HybridCacheSnapshot(cache)
        pointers = snapshot._layout(cache)
        cache.reset()
        self.assertFalse(cache.layers[0].has_previous_state[0])
        cache.layers[0].is_conv_states_initialized[0] = False
        cache.layers[0].is_recurrent_states_initialized[0] = False
        cache.layers[0].conv_kernel_size[0] = 999
        cache.layers[0].record_past = True
        cache.layers[1].is_initialized = False
        snapshot.restore(cache)
        self.assertTrue(cache.layers[0].has_previous_state[0])
        self.assertFalse(cache.layers[0].record_past)
        self.assertEqual(snapshot.compare(cache, rtol=0, atol=0), [])
        self.assertEqual(snapshot._layout(cache), pointers)
        self.assertGreater(snapshot.bytes, 0)

    @torch.inference_mode()
    def test_replaced_buffers_are_rejected_before_partial_restore(self):
        cache = self.cache()
        self.model(**self.inputs(), past_key_values=cache, use_cache=True, logits_to_keep=1)
        snapshot = HybridCacheSnapshot(cache)
        cache.layers[0].has_previous_state[0] = False
        cache.layers[1].keys = cache.layers[1].keys.clone()
        with self.assertRaisesRegex(RuntimeError, 'replaced'):
            snapshot.restore(cache)
        self.assertFalse(cache.layers[0].has_previous_state[0])

    @torch.inference_mode()
    def test_reference_comparison_includes_non_tensor_flags(self):
        cache = self.cache()
        self.model(**self.inputs(), past_key_values=cache, use_cache=True, logits_to_keep=1)
        snapshot = HybridCacheSnapshot(cache)
        cache.layers[0].has_previous_state[0] = False
        with self.assertRaisesRegex(AssertionError, 'has_previous_state'):
            snapshot.compare(cache)

    @torch.inference_mode()
    def test_integer_cache_positions_are_exact_even_with_float_tolerance(self):
        cache = self.cache()
        self.model(**self.inputs(), past_key_values=cache, use_cache=True, logits_to_keep=1)
        cache.layers[1].cumulative_length.fill_(1000)
        snapshot = HybridCacheSnapshot(cache)
        cache.layers[1].cumulative_length.add_(1)
        with self.assertRaisesRegex(AssertionError, 'cumulative_length'):
            snapshot.compare(cache)

    @torch.inference_mode()
    def test_two_different_images_reuse_prefix_and_validate_all_cache_state(self):
        helper, cache = InvariantTextPrefix(self.model), self.cache()
        helper.prefill(self.inputs(), cache)
        pointers = helper.snapshot._layout(cache)
        cache.reset()  # The existing decode owner resets between independent frames.
        helper.prefill(self.inputs(grid=8), cache)
        self.assertEqual(helper.metadata['setupCount'], 1)
        self.assertEqual(helper.metadata['restoreCount'], 1)
        self.assertEqual(helper.metadata['validatedPrefills'], 2)
        self.assertEqual(helper.snapshot._layout(cache), pointers)
        self.assertEqual(helper.metadata['prefixTokens'], 70)
        self.assertGreater(helper.metadata['snapshotBytes'], 0)
        self.assertGreaterEqual(helper.metadata['lastRun']['restoreMs'], 0)
        self.assertGreater(helper.metadata['totalValidationMs'], 0)

    @torch.inference_mode()
    def test_instruction_change_rebuilds_and_requires_new_validation(self):
        helper, cache, inputs = InvariantTextPrefix(self.model), self.cache(), self.inputs()
        helper.prefill(inputs, cache)
        helper.confirm_action(torch.tensor([1, 2]), torch.tensor([1, 2]))
        inputs['input_ids'][0, 0] += 1
        helper.prefill(inputs, cache)
        self.assertEqual(helper.metadata['setupCount'], 2)
        self.assertEqual(helper.metadata['validatedActions'], 0)
        self.assertEqual(helper.metadata['validatedPrefills'], 1)

    @torch.inference_mode()
    def test_new_cache_rebuilds_after_complete_action_validation(self):
        helper, inputs = InvariantTextPrefix(self.model), self.inputs()
        helper.prefill(inputs, self.cache())
        for _ in range(2):
            helper.confirm_action(torch.tensor([1, 2]), torch.tensor([1, 2]))
        helper.prefill(inputs, StaticCache(self.model.config, max_cache_len=256))
        self.assertEqual(helper.metadata['validatedActions'], 0)
        self.assertEqual(helper.metadata['validatedPrefills'], 1)
        self.assertEqual(helper.metadata['lastRun']['rebuildReason'], 'cache-replaced')

    @torch.inference_mode()
    def test_failed_prefill_parity_retains_diagnostic_delta_and_never_validates(self):
        helper, original = InvariantTextPrefix(self.model), self.model.forward
        calls = 0

        def changed_reference(*args, **kwargs):
            nonlocal calls
            output = original(*args, **kwargs)
            calls += 1
            if calls == 2:  # Suffix first, original full-prompt reference second.
                output.logits[:, -1, 0] += 1
            return output

        with mock.patch.object(self.model, 'forward', side_effect=changed_reference):
            with self.assertRaisesRegex(AssertionError, 'logits'):
                helper.prefill(self.inputs(), self.cache())
        self.assertEqual(helper.metadata['validatedPrefills'], 0)
        self.assertEqual(helper.metadata['validatedActions'], 0)
        self.assertGreater(helper.metadata['maxLogitAbsDelta'], .99)
        self.assertFalse(helper.metadata['bitwiseEquivalent'])
        self.assertGreater(helper.metadata['lastValidation']['validationMs'], 0)
        self.assertIn('logits', helper.metadata['validationError'])

    @torch.inference_mode()
    def test_prefix_and_original_path_have_exact_synthetic_autoregressive_tokens(self):
        inputs = self.inputs()

        def generate(use_prefix, sample):
            cache = self.cache()
            helper = InvariantTextPrefix(self.model) if use_prefix else None
            output = helper.prefill(inputs, cache) if helper else self.model(
                **inputs, past_key_values=cache, use_cache=True, logits_to_keep=1)
            logits = output.logits[:, -1]
            delta = self.model.model.rope_deltas.clone()
            generated = []
            torch.manual_seed(42)
            for index in range(8):
                token = (torch.multinomial(torch.softmax(logits.float(), dim=-1), 1)
                         if sample else logits.argmax(dim=-1).view(1, 1))
                generated.append(token)
                position = inputs['input_ids'].shape[-1] + index
                positions = (torch.tensor(position)+delta).view(1, 1, 1).expand(3, 1, 1)
                mask = (torch.arange(128) <= position).view(1, 1, 1, -1)
                output = self.model.model.language_model(
                    input_ids=token, position_ids=positions,
                    attention_mask={'full_attention': mask, 'linear_attention': None},
                    past_key_values=cache, use_cache=True, return_dict=True)
                logits = self.model.lm_head(output.last_hidden_state[:, -1])
            return torch.cat(generated, dim=1), helper

        for sample in (False, True):
            expected, _ = generate(False, sample)
            actual, helper = generate(True, sample)
            helper.confirm_action(actual, expected)
            self.assertEqual(helper.metadata['validatedActions'], 1)
            with self.assertRaises(AssertionError):
                helper.confirm_action(actual, expected+1)

    @torch.inference_mode()
    def test_integrated_decoder_checks_original_generate_again_after_prefix_change(self):
        """Use eager CPU replay to test orchestration, not CUDA graph/checkpoint parity."""
        # Allocate the real static cache on CPU and substitute only the CUDA
        # transport/graph API. Prefill, suffix, token sampling and original
        # model.generate all execute real tiny Qwen3.5 modules.
        class CpuDecode(StaticGreedyDecode):
            def _capture(owner):
                def replay():
                    owner.logits = owner._decode()
                owner.graph = SimpleNamespace(replay=replay)
                owner.cache_pointers = [tensor.data_ptr() for tensor in owner._cache_tensors()]

        originals = {name: getattr(torch, name) for name in ('empty', 'zeros', 'arange')}
        def cpu_factory(name):
            def allocate(*args, **kwargs):
                if kwargs.get('device') == 'cuda':
                    kwargs['device'] = 'cpu'
                return originals[name](*args, **kwargs)
            return allocate

        with ExitStack() as stack:
            for name in originals:
                stack.enter_context(mock.patch.object(torch, name, side_effect=cpu_factory(name)))
            stack.enter_context(mock.patch('torch.cuda.synchronize'))
            stack.enter_context(mock.patch('torch.cuda.get_rng_state', side_effect=lambda device: torch.random.get_rng_state()))
            stack.enter_context(mock.patch('torch.cuda.set_rng_state', side_effect=lambda state, device: torch.random.set_rng_state(state)))
            for sampling in (None, sampling_options('sample')):
                decoder = CpuDecode(self.model, sampling=sampling, prefix_cache=True)
                inputs = self.inputs()
                with mock.patch.object(self.model, 'generate', wraps=self.model.generate) as original_generate:
                    for index in range(4):
                        if index == 3:
                            inputs['input_ids'][0, 0] += 1
                        torch.manual_seed(42+index)
                        decoder.generate(inputs, 8, [124], SimpleNamespace(put=lambda value: None, end=lambda: None))
                    # First two outputs validate; third reuses the result; a
                    # changed prefix resets local validation despite global=2.
                    self.assertEqual(original_generate.call_count, 3)
                    self.assertEqual(decoder.metadata['validatedActions'], 3)
                    self.assertEqual(decoder.prefix.metadata['validatedActions'], 1)
                    self.assertEqual(decoder.prefix.metadata['setupCount'], 2)
                    self.assertGreater(decoder.prefix.metadata['totalActionValidationMs'], 0)

    def test_sample_validation_restores_rng_even_when_original_generation_fails(self):
        """A parity error must abort without consuming the caller's next random draws."""
        model = SimpleNamespace(generate=mock.Mock(side_effect=RuntimeError('reference failed')))
        decoder = StaticGreedyDecode(model, sampling=sampling_options('sample'))
        before, after = torch.tensor([1], dtype=torch.uint8), torch.tensor([2], dtype=torch.uint8)
        with mock.patch('torch.cuda.synchronize'), mock.patch('torch.cuda.get_rng_state', return_value=after), \
             mock.patch('torch.cuda.set_rng_state') as restore:
            with self.assertRaisesRegex(RuntimeError, 'reference failed'):
                decoder._validate_action({'input_ids': torch.tensor([[1]])}, torch.tensor([[1, 2]]), 1, [2], before)
        self.assertEqual([call.args[0].item() for call in restore.call_args_list], [1, 2])
        self.assertEqual(decoder.metadata['validatedActions'], 0)

    def test_opt_in_cli_defaults_validation_and_live_passthrough(self):
        common = ['--model', 'gamescaling', '--checkpoint', 'weights', '--source', 'source', '--output', 'out.json']
        with mock.patch('sys.argv', ['benchmark.py']+common+['--images', 'one.png']):
            self.assertFalse(arguments().gamescaling_prefix_cache)
        self.assertFalse(parse_arguments(common).gamescaling_prefix_cache)
        enabled = common+['--gamescaling-prefix-cache', '--cuda-graph', '--history', '0']
        with mock.patch('sys.argv', ['benchmark.py']+enabled+['--images', 'one.png']):
            self.assertTrue(arguments().gamescaling_prefix_cache)
        with mock.patch('model_adapters.make_adapter') as factory:
            load_policy(parse_arguments(enabled))
        self.assertTrue(factory.call_args.kwargs['gamescaling_prefix_cache'])
        for extra in ([], ['--cuda-graph', '--history', '1'], ['--cuda-graph', '--model', 'open-p2p']):
            with self.subTest(extra=extra), mock.patch('sys.stderr'):
                options = common+['--gamescaling-prefix-cache']+extra
                with self.assertRaises(SystemExit):
                    parse_arguments(options)
                with mock.patch('sys.argv', ['benchmark.py']+options+['--images', 'one.png']), self.assertRaises(SystemExit):
                    arguments()

    def test_direct_adapter_rejects_unsupported_prefix_options_before_loading(self):
        from model_adapters import GameScalingAdapter, make_adapter
        for options in ({'history': 1, 'cuda_graph': True}, {'history': 0, 'cuda_graph': False}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, 'history=0'):
                GameScalingAdapter('missing', 'missing', gamescaling_prefix_cache=True, **options)
        with self.assertRaisesRegex(ValueError, 'GameScaling'):
            make_adapter('open-p2p', gamescaling_prefix_cache=True)

    @torch.inference_mode()
    def test_rejects_history_padding_and_incomplete_modality_layout(self):
        with self.assertRaisesRegex(ValueError, 'history=0'):
            InvariantTextPrefix(self.model, history_frames=1)
        with self.assertRaises(ValueError):
            HybridCacheSnapshot(self.cache())
        helper = InvariantTextPrefix(self.model)
        inputs = self.inputs()
        inputs['attention_mask'][0, 0] = 0
        with self.assertRaisesRegex(ValueError, 'padding'):
            helper.prefill(inputs, self.cache())
        inputs = self.inputs()
        inputs['mm_token_type_ids'][0, 0] = 1
        with self.assertRaisesRegex(ValueError, 'modality-token'):
            helper.prefill(inputs, self.cache())
        inputs = self.inputs()
        inputs['input_ids'][0, 72] = 10
        with self.assertRaisesRegex(ValueError, 'placeholders'):
            helper.prefill(inputs, self.cache())

    def tearDown(self):
        self.assertFalse(torch.cuda.is_initialized(), 'Prefix tests must remain CPU-only')


if __name__ == '__main__':
    unittest.main()
