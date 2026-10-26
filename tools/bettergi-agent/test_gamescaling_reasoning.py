"""Inert checks for the opt-in offline reasoning comparison; no model or CUDA loads."""
import ast
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from benchmark import arguments
from test_gamescaling_execution_context import Frame, SOURCE, TEXT, load_adapter, make_adapter


class GameScalingReasoningTests(unittest.TestCase):
    """Keep prompt construction, parser input and bounded-output behavior aligned."""

    def test_benchmark_default_and_explicit_reasoning(self):
        """The offline flag is an explicit opt-in recorded by argument parsing."""
        base = ['benchmark.py', '--model', 'gamescaling', '--checkpoint', 'weights',
                '--source', 'source', '--images', 'one.png', '--output', 'out.json']
        with patch('sys.argv', base):
            self.assertFalse(arguments().gamescaling_reasoning)
        with patch('sys.argv', base + ['--gamescaling-reasoning', '--max-new-tokens', '160']):
            selected = arguments()
        self.assertTrue(selected.gamescaling_reasoning)
        self.assertEqual(selected.max_new_tokens, 160)

    def test_benchmark_rejects_reasoning_for_p2p(self):
        """A text-policy switch cannot silently change a P2P comparison."""
        argv = ['benchmark.py', '--model', 'open-p2p', '--checkpoint', 'weights',
                '--source', 'source', '--images', 'one.png', '--output', 'out.json',
                '--gamescaling-reasoning']
        with patch('sys.argv', argv), patch('sys.stderr'), self.assertRaises(SystemExit):
            arguments()

    def test_direct_factory_rejects_wrong_model_before_cuda_query(self):
        """The shared factory also protects direct callers before resource access."""
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'make_adapter')
        namespace = {'torch': object()}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), namespace)
        with self.assertRaisesRegex(ValueError, 'requires the GameScaling model'):
            namespace['make_adapter']('open-p2p', gamescaling_reasoning=True)

    def test_constructor_rejects_non_boolean_before_loading(self):
        """Truthiness cannot accidentally enable a more expensive output mode."""
        cls, _ = load_adapter(SOURCE)
        for value in (None, 0, 1, 'false'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'must be a boolean'):
                cls('unused', 'unused', gamescaling_reasoning=value)

    def test_constructor_metadata_matches_both_prefills(self):
        """Exercise the actual constructor with inert loader and source modules."""
        cls, _ = load_adapter(SOURCE)
        namespace = cls.__init__.__globals__
        namespace.update(Path=Path, sys=SimpleNamespace(path=[]))
        namespace['torch'].float16 = 'float16'
        model = SimpleNamespace(parameters=lambda: [], eval=lambda: model)
        transformers = ModuleType('transformers')
        transformers.AutoProcessor = SimpleNamespace(from_pretrained=lambda *args, **kwargs: object())
        transformers.AutoModelForImageTextToText = SimpleNamespace(from_pretrained=lambda *args, **kwargs: model)
        decode = ModuleType('gamescaling_decode')
        decode.sampling_options = lambda *args: None
        package = ModuleType('gamescaling')
        package.__path__ = []
        prompt = ModuleType('gamescaling.prompt')
        prompt.build_system_prompt = lambda name, **kwargs: kwargs['rules']
        action = ModuleType('gamescaling.action')
        action.parse_action = lambda text: None
        modules = {'transformers': transformers, 'gamescaling_decode': decode,
                   'gamescaling': package, 'gamescaling.prompt': prompt, 'gamescaling.action': action}
        with patch.dict(sys.modules, modules):
            for enabled, expected in ((False, '<think>\n\n</think>'), (True, '<think>')):
                with self.subTest(enabled=enabled):
                    adapter = cls('unused', 'unused', gamescaling_reasoning=enabled)
                    self.assertEqual(adapter._assistant_prefill, expected)
                    self.assertIs(adapter.metadata['reasoning'], enabled)

    def test_prediction_uses_the_same_prefill_for_template_and_parser(self):
        """Both decode paths preserve strict parser input and action-only history."""
        for graph in (False, True):
            for enabled in (False, True):
                with self.subTest(graph=graph, enabled=enabled):
                    adapter, _ = make_adapter(history=1, graph=graph)
                    prefix = '<think>' if enabled else '<think>\n\n</think>'
                    adapter._assistant_prefill = prefix
                    text = ('Consider the goal.</think>\n' if enabled else '') + TEXT
                    adapter.processor.tokenizer.decode = lambda values, **kwargs: text
                    original = adapter.parse_action
                    consumed = []

                    def parse(value):
                        """Record the exact input to the existing strict parser boundary."""
                        consumed.append(value)
                        return original(value)

                    adapter.parse_action = parse
                    result = adapter.predict(Frame())
                    self.assertEqual(adapter.processor.messages[-1]['content'], prefix)
                    self.assertEqual(consumed, [prefix + text])
                    self.assertTrue(result['parseValid'])
                    self.assertEqual(adapter.history[-1][1], TEXT)

    def test_budget_truncated_thinking_produces_no_steps_or_history(self):
        """A generation budget cannot turn an incomplete answer into a command."""
        adapter, _ = make_adapter(history=1)
        adapter._assistant_prefill = '<think>'
        adapter.processor.tokenizer.decode = lambda values, **kwargs: 'Still considering the instruction'
        result = adapter.predict(Frame())
        self.assertFalse(result['parseValid'])
        self.assertEqual(result['steps'], [])
        self.assertEqual(len(adapter.history), 0)


if __name__ == '__main__':
    unittest.main()
