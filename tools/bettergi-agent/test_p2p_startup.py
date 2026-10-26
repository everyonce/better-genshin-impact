"""Startup ordering and empty-history checks without Torch, CUDA or bridge IO."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import p2p_startup as startup
import stream_client


def fixture():
    """Provide only the operations startup preparation may use."""
    events = []
    validity = SimpleNamespace(value=0)
    validity.item = lambda: validity.value
    policy = SimpleNamespace(use_cuda_graph=True, graph=None, steps_seen=0, _pending_feedback=False,
                             idx=SimpleNamespace(item=lambda: 0), text=SimpleNamespace(device='cuda:0'),
                             metadata={'graphCaptureValidated': False})

    def advance():
        """Expose a temporary preparation timestep."""
        events.append('advance')
        validity.value = 8

    def capture(frame):
        """Record graph readiness without decoding or emitting an action."""
        events.append('capture')
        policy.graph = object()
        policy.metadata['graphCaptureValidated'] = True

    def reset():
        """Restore the initial mask while retaining the captured graph."""
        events.append('reset')
        validity.value = 0

    policy.temporal_cache = SimpleNamespace(enabled=True, valid_tokens=validity, advance=Mock(side_effect=advance))
    policy._prepare_graph = Mock(side_effect=capture)
    policy.reset = Mock(side_effect=reset)
    frame = SimpleNamespace(stride=lambda: (1, 576, 3))
    storage = SimpleNamespace(permute=Mock(return_value=frame))
    numeric = SimpleNamespace(uint8=object(), zeros=Mock(return_value=storage),
        is_inference_mode_enabled=Mock(return_value=False),
        cuda=SimpleNamespace(synchronize=Mock(side_effect=lambda: events.append('synchronize'))))
    return policy, numeric, storage, events


class StartupPreparationTests(unittest.TestCase):
    """Keep dummy preparation outside controller and observation history."""

    def test_prepares_with_predict_layout_and_restores_empty_history(self):
        """A channels-last CHW view must match predict() rather than introduce NCHW storage."""
        policy, numeric, storage, events = fixture()
        with patch.dict('sys.modules', {'torch': numeric}):
            result = startup.prepare_startup_graph(policy)
        numeric.zeros.assert_called_once_with((192, 192, 3), dtype=numeric.uint8, device='cuda:0')
        storage.permute.assert_called_once_with(2, 0, 1)
        self.assertEqual(events, ['advance', 'capture', 'reset', 'synchronize'])
        self.assertEqual(policy.temporal_cache.valid_tokens.item(), 0)
        self.assertEqual(result['historyFramesAfterPreparation'], 0)
        self.assertEqual(result['controllerActionsEmitted'], 0)
        self.assertIs(policy.metadata['startupGraphPreparation'], result)

    def test_capture_failure_resets_and_propagates(self):
        """A failed graph must never become a successfully loaded policy."""
        policy, numeric, _, events = fixture()
        policy._prepare_graph.side_effect = RuntimeError('capture_failed')
        with patch.dict('sys.modules', {'torch': numeric}), self.assertRaisesRegex(RuntimeError, 'capture_failed'):
            startup.prepare_startup_graph(policy)
        self.assertEqual(events, ['advance', 'reset'])
        self.assertEqual(policy.temporal_cache.valid_tokens.item(), 0)
        self.assertNotIn('startupGraphPreparation', policy.metadata)

    def test_rejects_existing_history_or_pending_feedback_before_allocation(self):
        """Startup may not discard an observation or an unsettled proposal."""
        for field, value in (('steps_seen', 1), ('_pending_feedback', True)):
            with self.subTest(field=field):
                policy, numeric, _, _ = fixture()
                setattr(policy, field, value)
                with patch.dict('sys.modules', {'torch': numeric}), self.assertRaisesRegex(ValueError, 'empty, settled'):
                    startup.prepare_startup_graph(policy)
                numeric.zeros.assert_not_called()
                policy.reset.assert_not_called()

    def test_rejects_disabled_masks_or_existing_graph(self):
        """Native growing history and captured policies retain their original lifecycle."""
        for existing_graph in (False, True):
            with self.subTest(existing_graph=existing_graph):
                policy, numeric, _, _ = fixture()
                if existing_graph:
                    policy.graph = object()
                else:
                    policy.temporal_cache.enabled = False
                with patch.dict('sys.modules', {'torch': numeric}), self.assertRaisesRegex(ValueError, 'fresh masked'):
                    startup.prepare_startup_graph(policy)
                numeric.zeros.assert_not_called()

    def test_rejects_inference_mode_storage(self):
        """The live caller must remain able to update prepared buffers outside inference mode."""
        policy, numeric, _, _ = fixture()
        numeric.is_inference_mode_enabled.return_value = True
        with patch.dict('sys.modules', {'torch': numeric}), self.assertRaisesRegex(ValueError, 'outside torch.inference_mode'):
            startup.prepare_startup_graph(policy)
        numeric.zeros.assert_not_called()

    def test_incomplete_reset_cannot_publish_readiness(self):
        """A returned reset must actually clear the temporary valid timestep."""
        policy, numeric, _, _ = fixture()
        policy.reset.side_effect = None
        with patch.dict('sys.modules', {'torch': numeric}), self.assertRaisesRegex(ValueError, 'empty, settled'):
            startup.prepare_startup_graph(policy)
        self.assertNotIn('startupGraphPreparation', policy.metadata)


class StartupOptionTests(unittest.TestCase):
    """Default startup is unchanged; enabled preparation is validated before loading."""

    def arguments(self, *extra):
        """Parse a policy-only fixture without connecting to its named pipe."""
        return stream_client.parse_arguments(['--pipe', 'BetterGI.Agent.fixture', '--model', 'open-p2p',
            '--source', 'fixture', '--checkpoint', 'fixture', '--output', 'fixture.json', *extra])

    def test_default_remains_disabled(self):
        """Existing callers without the new option keep their exact factory path."""
        args = self.arguments()
        self.assertFalse(args.p2p_prewarm)
        factory = Mock(return_value=object())
        with patch.dict('sys.modules', {'model_adapters': SimpleNamespace(make_adapter=factory)}), \
                patch.object(startup, 'prepare_startup_graph') as prepare, patch.object(stream_client, 'Bridge') as bridge:
            self.assertIs(stream_client.load_policy(args), factory.return_value)
        prepare.assert_not_called()
        bridge.assert_not_called()

    def test_option_requires_p2p_masked_cuda_graphs(self):
        """Unsupported combinations fail before numeric imports or checkpoint loading."""
        for changes in ({'model': 'gamescaling'}, {'cuda_graph': False}, {'p2p_fast_start': False}, {'p2p_prewarm': 1}):
            values = dict(model='open-p2p', cuda_graph=True, p2p_fast_start=True, p2p_prewarm=True)
            values.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                startup.validate_startup_options(SimpleNamespace(**values))

    def test_load_prepares_before_return_without_opening_bridge(self):
        """Policy readiness includes preparation before run_episode can receive the policy."""
        args = self.arguments('--cuda-graph', '--p2p-fast-start', '--p2p-prewarm')
        policy = object()
        events = []
        factory = Mock(side_effect=lambda *a, **k: events.append('load') or policy)
        with patch.dict('sys.modules', {'model_adapters': SimpleNamespace(make_adapter=factory)}), \
                patch.object(startup, 'prepare_startup_graph', side_effect=lambda p: events.append('prepare')) as prepare, \
                patch.object(stream_client, 'Bridge') as bridge:
            self.assertIs(stream_client.load_policy(args), policy)
        self.assertEqual(events, ['load', 'prepare'])
        prepare.assert_called_once_with(policy)
        bridge.assert_not_called()

    def test_prepare_failure_prevents_returned_policy(self):
        """Startup failure remains an error and cannot silently fall back to live capture."""
        args = self.arguments('--cuda-graph', '--p2p-fast-start', '--p2p-prewarm')
        with patch.dict('sys.modules', {'model_adapters': SimpleNamespace(make_adapter=Mock(return_value=object()))}), \
                patch.object(startup, 'prepare_startup_graph', side_effect=RuntimeError('capture_failed')), \
                patch.object(stream_client, 'Bridge') as bridge, self.assertRaisesRegex(RuntimeError, 'capture_failed'):
            stream_client.load_policy(args)
        bridge.assert_not_called()


if __name__ == '__main__':
    unittest.main()
