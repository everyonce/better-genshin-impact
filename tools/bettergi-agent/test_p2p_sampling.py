"""CPU checks for explicit sampling, original defaults and the live-input boundary."""
import contextlib
import io
import math
from types import SimpleNamespace
import unittest
from unittest import mock

import p2p_sampling as sampling
import stream_client
import benchmark


class P2PSamplingTests(unittest.TestCase):
    """Exercise adapter selection and externally visible upstream arguments without CUDA."""

    def test_default_delegates_original_factory_without_extra_arguments(self):
        """An omitted or unit temperature preserves the original construction contract."""
        for name in ('open-p2p', 'gamescaling'):
            with self.subTest(name=name), mock.patch.object(sampling, 'make_original_adapter') as original:
                self.assertIs(sampling.make_adapter(name, history=41), original.return_value)
                original.assert_called_once_with(name, history=41)

    def test_override_selects_separate_adapter(self):
        """A requested scalar reaches the experimental class before prediction starts."""
        with mock.patch.object(sampling.torch.cuda, 'is_available', return_value=True), \
                mock.patch.object(sampling, 'TemperatureP2PAdapter') as adapter:
            self.assertIs(sampling.make_adapter('open-p2p', p2p_temperature=.2, history=41), adapter.return_value)
            adapter.assert_called_once_with(p2p_temperature=.2, history=41)

    def test_invalid_values_never_construct_a_model(self):
        """Malformed scalars fail before CUDA admission or model construction."""
        for value in (True, False, None, '0.2', 0, -1, math.nan, math.inf):
            with self.subTest(value=value), mock.patch.object(sampling.torch.cuda, 'is_available') as cuda, \
                    mock.patch.object(sampling, 'make_original_adapter') as original:
                with self.assertRaisesRegex(ValueError, 'finite and positive'):
                    sampling.make_adapter('open-p2p', p2p_temperature=value)
                cuda.assert_not_called()
                original.assert_not_called()

    def test_override_rejects_other_models_and_native_scope(self):
        """The new profile cannot silently alter another model or claim native qualification."""
        with self.assertRaisesRegex(ValueError, 'requires open-p2p'):
            sampling.make_adapter('gamescaling', p2p_temperature=.2)
        with self.assertRaisesRegex(ValueError, 'native checkpoint qualification'):
            sampling.make_adapter('open-p2p', p2p_temperature=.2, checkpoint_scope=object())
        with self.assertRaisesRegex(ValueError, 'native checkpoint qualification'):
            sampling.TemperatureP2PAdapter(p2p_temperature=.2, checkpoint_scope=object())

    def test_forward_passes_only_the_requested_sampling_change(self):
        """The upstream API receives the same state, goal and uniform sampling tensors."""
        policy = sampling.TemperatureP2PAdapter.__new__(sampling.TemperatureP2PAdapter)
        policy._sampling_temperature = .2
        policy.dtype = object()
        policy.text = object()
        policy.model = mock.Mock()
        frame, index, state, uniform = (object() for _ in range(4))
        contexts = SimpleNamespace(float32=object(), inference_mode=lambda:contextlib.nullcontext(),
            device=lambda *_:contextlib.nullcontext(), autocast=lambda *_,**__:contextlib.nullcontext())
        with mock.patch.object(sampling, 'torch', contexts):
            self.assertIs(policy._forward(frame,index,state,uniform), policy.model.online_kv_cache_predict.return_value)
        policy.model.online_kv_cache_predict.assert_called_once_with(frame,index,state,compile=False,
            sampling_temperature=.2,text_tokens_embed=policy.text,unif_rand=uniform)

    def test_native_runtime_rejects_experimental_class(self):
        """The actual native source/type admission refuses this separate adapter profile."""
        import model_adapters
        from native_history_feedback import FeedbackError
        from native_history_runtime import TorchRuntime
        runtime = TorchRuntime.__new__(TorchRuntime)
        runtime.adapter_module = model_adapters
        runtime.torch = sampling.torch
        policy = sampling.TemperatureP2PAdapter.__new__(sampling.TemperatureP2PAdapter)
        with self.assertRaisesRegex(FeedbackError,'adapter_class_namespace'):
            runtime.qualify(policy)

    def test_shadow_cli_passes_override_to_experimental_factory(self):
        """The user-facing shadow option reaches the selected model factory."""
        args = stream_client.parse_arguments(['--model','open-p2p','--checkpoint','unused',
            '--source','unused','--output','unused.json','--p2p-temperature','0.2'])
        with mock.patch.object(sampling, 'make_adapter') as factory:
            self.assertIs(stream_client.load_policy(args), factory.return_value)
            self.assertEqual(factory.call_args.kwargs['p2p_temperature'],.2)

    def test_live_override_is_rejected_before_loading_or_connection(self):
        """Experimental sampling cannot be enabled accidentally for real input."""
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as failure:
            stream_client.parse_arguments(['--model','open-p2p','--checkpoint','unused',
                '--source','unused','--output','unused.json','--p2p-temperature','0.2','--enable-input'])
        self.assertEqual(failure.exception.code,2)
        self.assertIn('replay and shadow runs only', errors.getvalue())

    def test_direct_policy_load_rechecks_live_boundary(self):
        """Programmatic callers receive the same validation as the command-line parser."""
        args = stream_client.parse_arguments(['--model','open-p2p','--checkpoint','unused',
            '--source','unused','--output','unused.json','--p2p-temperature','0.2'])
        args.enable_input = True
        with mock.patch.object(sampling,'make_adapter') as factory:
            with self.assertRaisesRegex(ValueError,'replay and shadow runs only'):
                stream_client.load_policy(args)
            factory.assert_not_called()

    def test_benchmark_cli_accepts_p2p_temperature(self):
        """Saved-image replay exposes the setting without changing GameScaling sampling flags."""
        argv = ['benchmark.py','--model','open-p2p','--checkpoint','unused','--source','unused',
                '--images','unused.png','--output','unused.json','--p2p-temperature','0.2']
        with mock.patch('sys.argv',argv):
            args = benchmark.arguments()
        self.assertEqual(args.p2p_temperature,.2)
        self.assertEqual(args.temperature,1.0)

    def test_benchmark_cli_rejects_invalid_or_wrong_model_override(self):
        """Invalid replay settings fail during parsing, before files or weights are read."""
        for model, value, message in (('open-p2p','0','finite and positive'),
                                      ('open-p2p','nan','finite and positive'),
                                      ('gamescaling','0.2','requires open-p2p')):
            argv = ['benchmark.py','--model',model,'--checkpoint','unused','--source','unused',
                    '--images','unused.png','--output','unused.json','--p2p-temperature',value]
            errors = io.StringIO()
            with self.subTest(model=model,value=value), mock.patch('sys.argv',argv), \
                    contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as failure:
                benchmark.arguments()
            self.assertEqual(failure.exception.code,2)
            self.assertIn(message,errors.getvalue())


if __name__ == '__main__':
    unittest.main()
