"""Portable inert checks for adjacent adapter/context modules; no model imports.

The real GameScaling methods are AST-extracted and use inert image, processor,
transfer and generation stubs. The adjacent stdlib context module is real.
These tests establish message construction and software contracts, not model
quality, tokenizer compatibility, numerical parity or live input behavior.
"""
import ast
from collections import deque
import hashlib
import json
import importlib.util
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'model_adapters.py'
TEXT = '<|action_start|>0 0 0; LB; ; ; ; ;<|action_end|>'


class Frame:
    """An image-shaped object whose resize only records dimensions."""
    width, height, size = 192, 192, (192, 192)

    def resize(self, dimensions, mode):
        self.resized = (dimensions, mode)
        return self


class Value:
    """An inert tensor-shaped transport value."""
    def __init__(self, log, shape, floating=False):
        self.log, self.shape, self.floating = log, shape, floating

    def to(self, *args, **kwargs):
        self.log.append(('to', args, kwargs))
        return self

    def __getitem__(self, key):
        return [1, 2, 3]


def load_adapter(path):
    """Compile only the actual pure helpers and classes; imports stay excluded."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = {'canonical_key', 'gamescaling_steps', 'complete_gamescaling_action',
             'FirstTokenClock', 'GameScalingAdapter'}
    nodes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    log = []

    class Inference:
        def __enter__(self):
            log.append('inference_enter')

        def __exit__(self, *args):
            log.append('inference_exit')

    class Clock:
        ticks = 0

        def perf_counter_ns(self):
            self.ticks += 1000000
            return self.ticks

    fake_torch = SimpleNamespace(cuda=SimpleNamespace(synchronize=lambda: log.append('sync')),
                                 is_floating_point=lambda value: value.floating,
                                 inference_mode=Inference)
    namespace = {'torch': fake_torch, 'time': Clock(), 'math': math, 'deque': deque,
                 'Image': SimpleNamespace(Resampling=SimpleNamespace(BILINEAR='bilinear')),
                 'KEYS': {'LB': 'LBUTTON'}, 'ARROWS': {}, 'DIGITS': {}, 'FUNCTIONS': {}}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['GameScalingAdapter'], log


def make_adapter(path=SOURCE, history=0, prefix=False, graph=False, valid=True):
    """Construct an inert owner without executing the model-loading constructor."""
    cls, log = load_adapter(path)
    obj = cls.__new__(cls)
    obj.image_width = 384
    obj.history = deque(maxlen=history)
    obj.system = 'original system rules'
    obj._assistant_prefill = '<think>\n\n</think>'
    obj.dtype = 'float16'
    obj.max_new_tokens = 96
    obj.sampling = {'do_sample': True, 'temperature': 0.7}
    obj.parse_action = lambda text: SimpleNamespace(parsed=valid, truncated=False, dropped=(),
        mouse=(0.0, 0.0, 0.0), steps=[['LB'], [], [], [], [], []],
        body='0 0 0; LB; ; ; ; ;', history_text=TEXT)

    class Processor:
        tokenizer = SimpleNamespace(convert_tokens_to_ids=lambda value: 99, unk_token_id=-1,
                                    decode=lambda values, **kwargs: TEXT)

        def apply_chat_template(self, messages, **kwargs):
            self.messages, self.options = messages, kwargs
            return {'input_ids': Value(log, (1, 4)), 'pixel_values': Value(log, (1, 3), True)}

    def generate(**kwargs):
        obj.generated = kwargs
        log.append('generate')
        kwargs['streamer'].put(None)
        kwargs['streamer'].put([1])
        return Value(log, (1, 7))

    obj.processor = Processor()
    obj.model = SimpleNamespace(generate=generate, generation_config=SimpleNamespace(eos_token_id=2))
    if prefix or graph:
        def graph_generate(inputs, count, eos, clock):
            log.append('graph_generate')
            return generate(**inputs, max_new_tokens=count, eos_token_id=eos, streamer=clock)
        obj.decode_graph = SimpleNamespace(prefix=SimpleNamespace(metadata={'lastRun': {'fixed': 1}}) if prefix else None,
                                          generate=graph_generate)
    else:
        obj.decode_graph = None
    return obj, log


def renderer(text='{"ongoing":"unknown","physicalEffect":"unknown"}', error=None):
    """A strict helper stub for consumer-boundary fault injection only."""
    module = ModuleType('execution_context')
    module.calls = []
    token = object()

    def render(snapshot):
        module.calls.append(snapshot)
        if snapshot is not token:
            raise TypeError('Expected ExecutionSnapshot')
        if error:
            raise error
        return text

    module.render_gamescaling_context = render
    return module, token


class AdapterCases(unittest.TestCase):
    def test_none_exact_legacy_prompt_options_result_and_call_order(self):
        implicit, implicit_log = make_adapter()
        explicit, explicit_log = make_adapter()
        frame = Frame()
        result = implicit.predict(frame, (1920, 1080))
        self.assertEqual(result, explicit.predict(frame, (1920, 1080), execution_context=None))
        self.assertEqual(implicit.processor.messages, [
            {'role': 'system', 'content': 'original system rules'},
            {'role': 'user', 'content': [{'type': 'text', 'text': 'current game screen'},
                                       {'type': 'image', 'image': frame}]},
            {'role': 'assistant', 'content': '<think>\n\n</think>'}])
        self.assertEqual(implicit.processor.options, dict(tokenize=True, return_dict=True,
            return_tensors='pt', add_generation_prompt=False, continue_final_message=True))
        self.assertEqual(implicit_log, [('to', ('cuda',), {}),
            ('to', ('cuda',), {'dtype': 'float16'}), 'sync', 'inference_enter',
            'generate', 'sync', 'inference_exit', 'sync'])
        self.assertEqual(implicit_log, explicit_log)
        self.assertEqual(result['steps'], [dict(durationMs=33 if i < 5 else 35,
            keys=['LBUTTON'] if i == 0 else [], mouseDx=0, mouseDy=0) for i in range(6)])
        self.assertEqual({key: result[key] for key in ('preprocessMs', 'firstTokenMs',
            'fullActionMs', 'generatedTokens')},
            dict(preprocessMs=1.0, firstTokenMs=2.0, fullActionMs=3.0, generatedTokens=3))
        self.assertNotIn('executionContextText', result)


    def test_none_history_and_prefix_behavior_retained(self):
        frame = Frame()
        obj, _ = make_adapter(history=2)
        obj.history.append((frame, TEXT))
        result = obj.predict(frame)
        self.assertEqual([row['role'] for row in obj.processor.messages],
                         ['system', 'user', 'assistant', 'user', 'assistant'])
        self.assertEqual(obj.processor.messages[2]['content'], TEXT)
        self.assertEqual(len(obj.history), 2)
        self.assertNotIn('executionContextText', result)
        cached, log = make_adapter(prefix=True)
        result = cached.predict(frame)
        self.assertEqual(result['prefixCache'], {'fixed': 1})
        self.assertEqual(log.count('graph_generate'), 1)
        self.assertNotIn('executionContextText', result)


    def test_none_does_not_import_shared_module(self):
        obj, _ = make_adapter()
        with patch.dict(sys.modules, {'execution_context': None}):
            self.assertNotIn('executionContextText', obj.predict(Frame()))

    def test_context_only_added_to_current_user_turn(self):
        module, token = renderer()
        obj, _ = make_adapter()
        frame = Frame()
        with patch.dict(sys.modules, {'execution_context': module}):
            result = obj.predict(frame, (1920, 1080), execution_context=token)
        messages = obj.processor.messages
        self.assertEqual(messages[0], {'role': 'system', 'content': obj.system})
        self.assertEqual([row['type'] for row in messages[1]['content']], ['text', 'text', 'image'])
        self.assertEqual(messages[1]['content'][0]['text'], 'current game screen')
        self.assertIs(messages[1]['content'][2]['image'], frame)
        self.assertEqual(messages[-1], {'role': 'assistant', 'content': '<think>\n\n</think>'})
        self.assertEqual(obj.processor.options, dict(tokenize=True, return_dict=True, return_tensors='pt',
            add_generation_prompt=False, continue_final_message=True))
        self.assertTrue(result['parseValid'])
        self.assertEqual(result['steps'][0]['keys'], ['LBUTTON'])
        self.assertEqual(len(obj.history), 0)
        self.assertEqual(module.calls, [token])

    def test_exact_consumed_text_hash_and_detached_receipt(self):
        text = '{"reported":"LBUTTON","heldNow":"unknown"}'
        module, token = renderer(text)
        obj, _ = make_adapter()
        with patch.dict(sys.modules, {'execution_context': module}):
            first = obj.predict(Frame(), execution_context=token)
            second = obj.predict(Frame(), execution_context=token)
        self.assertEqual(first['executionContextText'], {'sha256': hashlib.sha256(text.encode()).hexdigest(), 'bytes': len(text.encode())})
        self.assertIsNot(first['executionContextText'], second['executionContextText'])
        first['executionContextText']['bytes'] = 0
        self.assertGreater(second['executionContextText']['bytes'], 0)

    def test_context_keyword_only(self):
        obj, log = make_adapter()
        with self.assertRaises(TypeError):
            obj.predict(Frame(), (1920, 1080), object())
        self.assertEqual(log, [])

    def test_nonzero_history_rejected_before_renderer_or_numerical_boundary(self):
        module, token = renderer()
        obj, log = make_adapter(history=1)
        with patch.dict(sys.modules, {'execution_context': module}), self.assertRaisesRegex(ValueError, 'history=0'):
            obj.predict(Frame(), execution_context=token)
        self.assertEqual(module.calls, [])
        self.assertEqual(log, [])

    def test_prefix_rejected_before_renderer_or_numerical_boundary(self):
        module, token = renderer()
        obj, log = make_adapter(prefix=True)
        with patch.dict(sys.modules, {'execution_context': module}), self.assertRaisesRegex(ValueError, 'cached text prefixes'):
            obj.predict(Frame(), execution_context=token)
        self.assertEqual(module.calls, [])
        self.assertEqual(log, [])

    def test_normal_decode_graph_without_prefix_still_delegated(self):
        module, token = renderer()
        obj, log = make_adapter(graph=True)
        with patch.dict(sys.modules, {'execution_context': module}):
            result = obj.predict(Frame(), execution_context=token)
        self.assertEqual(log.count('graph_generate'), 1)
        self.assertEqual(log.count('generate'), 1)
        self.assertTrue(result['parseValid'])

    def test_invalid_snapshot_rejected_without_generation(self):
        module, _ = renderer()
        obj, log = make_adapter()
        with patch.dict(sys.modules, {'execution_context': module}), self.assertRaises(TypeError):
            obj.predict(Frame(), execution_context={})
        self.assertEqual(log, [])

    def test_renderer_error_preserved_without_generation(self):
        error = ValueError('incomplete context')
        module, token = renderer(error=error)
        obj, log = make_adapter()
        with patch.dict(sys.modules, {'execution_context': module}), self.assertRaises(ValueError) as caught:
            obj.predict(Frame(), execution_context=token)
        self.assertIs(caught.exception, error)
        self.assertEqual(log, [])

    def test_utf8_exact_boundary(self):
        module, token = renderer('é' * 1024)
        obj, _ = make_adapter()
        with patch.dict(sys.modules, {'execution_context': module}):
            result = obj.predict(Frame(), execution_context=token)
        self.assertEqual(result['executionContextText']['bytes'], 2048)

    def test_overlong_empty_and_nontext_rejected_without_generation(self):
        for text in ('é' * 1025, '', b'{}', None):
            with self.subTest(text_type=type(text).__name__, size=len(text) if text is not None else None):
                module, token = renderer(text)
                obj, log = make_adapter()
                with patch.dict(sys.modules, {'execution_context': module}), self.assertRaises(ValueError):
                    obj.predict(Frame(), execution_context=token)
                self.assertEqual(log, [])

    def test_context_does_not_repair_invalid_action(self):
        module, token = renderer()
        obj, _ = make_adapter(valid=False)
        with patch.dict(sys.modules, {'execution_context': module}):
            result = obj.predict(Frame(), execution_context=token)
        self.assertFalse(result['parseValid'])
        self.assertEqual(result['steps'], [])
        self.assertEqual(len(obj.history), 0)

    def test_context_leaves_native_sampling_and_step_conversion_unchanged(self):
        old, old_log = make_adapter()
        obj, log = make_adapter()
        module, token = renderer()
        baseline = old.predict(Frame(), (1920, 1080))
        with patch.dict(sys.modules, {'execution_context': module}):
            result = obj.predict(Frame(), (1920, 1080), execution_context=token)
        result.pop('executionContextText')
        self.assertEqual(result, baseline)
        for key in ('max_new_tokens', 'do_sample', 'temperature', 'eos_token_id', 'use_cache'):
            self.assertEqual(obj.generated[key], old.generated[key])
        self.assertEqual(log, old_log)


PATH = ROOT / 'execution_context.py'
SPEC = importlib.util.spec_from_file_location('_gamescaling_execution_context_test_dependency', PATH)
SHARED = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SHARED
SPEC.loader.exec_module(SHARED)


def fixture():
    """Use real R45 field names and the canonical LBUTTON controller key."""
    ledger = SHARED.ExecutionContext({'sessionId': 'session', 'ownerEpoch': 'owner'})
    receipt = {'requestId': 'reported-attack', 'modelId': 'gamescaling', 'frameId': 1,
               'status': 'replaced', 'reason': 'newer_proposal', 'acceptedAtMs': 1.0, 'endedAtMs': 2.0,
               'appliedSteps': [{'index': 0, 'startedAtMs': 1.5, 'keys': ['LBUTTON'], 'mouseDx': 0, 'mouseDy': 0}]}
    ledger.record('receipt', receipt, observed_client_ns=100)
    frame = {'frameId': 2, 'observedClientNs': 90, 'capturedAtMs': 1.2, 'sourceAgeMs': 10.0,
             'hostSnapshot': {'startedAtMs': 1.3, 'completedAtMs': 1.4}}
    snapshot = ledger.snapshot(frame, cutoff_client_ns=110,
        decision_context={'controlEpoch': 2, 'readinessEpoch': 3, 'policyGoalVersion': 4, 'sourceEpoch': 'epoch'})
    return ledger, frame, snapshot, receipt


class SharedContextCases(unittest.TestCase):
    def test_real_snapshot_text_and_receipt_join(self):
        _, _, snapshot, _ = fixture()
        expected = SHARED.render_gamescaling_context(snapshot)
        obj, _ = make_adapter()
        with patch.dict(sys.modules, {'execution_context': SHARED}):
            result = obj.predict(Frame(), execution_context=snapshot)
        self.assertEqual(obj.processor.messages[1]['content'][1]['text'], expected)
        self.assertEqual(result['executionContextText'],
                         {'sha256': hashlib.sha256(expected.encode()).hexdigest(), 'bytes': len(expected.encode())})
        projection = json.loads(expected)
        self.assertIn('UNKNOWN', projection['limits'])
        self.assertEqual(projection['cutoffClientNs'], 110)
        self.assertEqual(projection['events'][0]['steps'][0]['keys'], ['LBUTTON'])
        self.assertLessEqual(len(expected.encode()), 2048)

    def test_later_receipt_and_caller_mutation_cannot_change_consumed_snapshot(self):
        ledger, frame, snapshot, receipt = fixture()
        before = SHARED.render_gamescaling_context(snapshot)
        receipt['requestId'] = 'later-reported'
        receipt['appliedSteps'][0]['keys'] = ['W']
        ledger.record('receipt', receipt, observed_client_ns=120)
        detached = snapshot.to_dict()
        detached['events'].clear()
        newer = ledger.snapshot(frame, cutoff_client_ns=130)
        self.assertEqual(SHARED.render_gamescaling_context(snapshot), before)
        self.assertNotIn('later-reported', before)
        self.assertIn('later-reported', SHARED.render_gamescaling_context(newer))
        obj, _ = make_adapter()
        with patch.dict(sys.modules, {'execution_context': SHARED}):
            obj.predict(Frame(), execution_context=snapshot)
        self.assertEqual(obj.processor.messages[1]['content'][1]['text'], before)

    def test_plain_dict_and_unissued_snapshot_rejected_before_generation(self):
        _, _, snapshot, _ = fixture()
        for bad in (snapshot.to_dict(), SHARED.ExecutionSnapshot('{}', object())):
            obj, log = make_adapter()
            with patch.dict(sys.modules, {'execution_context': SHARED}), self.assertRaises((ValueError, TypeError)):
                obj.predict(Frame(), execution_context=bad)
            self.assertEqual(log, [])

    def test_bounded_projection_keeps_explicit_omitted_count(self):
        ledger, frame, _, receipt = fixture()
        for index in range(20):
            item = dict(receipt, requestId='record-' + str(index))
            ledger.record('receipt', item, observed_client_ns=200 + index)
        snapshot = ledger.snapshot(frame, cutoff_client_ns=230)
        obj, _ = make_adapter()
        with patch.dict(sys.modules, {'execution_context': SHARED}):
            result = obj.predict(Frame(), execution_context=snapshot)
        rendered = obj.processor.messages[1]['content'][1]['text']
        self.assertGreater(json.loads(rendered)['projectionOmittedEvents'], 0)
        self.assertEqual(result['executionContextText']['bytes'], len(rendered.encode()))
        self.assertLessEqual(result['executionContextText']['bytes'], 2048)


    def test_real_v2_receipt_age_is_lower_bound_not_server_source_age(self):
        _, _, snapshot, _ = fixture()
        obj, _ = make_adapter()
        with patch.dict(sys.modules, {'execution_context': SHARED}):
            result = obj.predict(Frame(), execution_context=snapshot)
        consumed = obj.processor.messages[1]['content'][1]['text']
        projection = json.loads(consumed)
        self.assertEqual(projection['ageSinceImageReceiptMs'], (110 - 90) / 1_000_000)
        self.assertIn('lower bound', projection['imageReceiptAgeBasis'])
        self.assertNotIn('sourceAgeMs', projection)
        self.assertNotIn('sourceAgeMs', projection['imageTiming'])
        self.assertEqual(snapshot.to_dict()['frame']['sourceAgeMs'], 10.0)
        self.assertEqual(result['executionContextText']['sha256'], hashlib.sha256(consumed.encode()).hexdigest())

    def test_real_v2_keeps_reported_attack_before_verbose_plans(self):
        ledger, frame, _, _ = fixture()
        for index in range(8):
            ledger.record('proposal', {'requestId': 'planned-' + str(index), 'modelId': 'gamescaling',
                'frameId': 2, 'steps': [dict(durationMs=50, keys=['W', 'A', 'S', 'D'],
                    mouseDx=10, mouseDy=-10) for _ in range(6)]}, observed_client_ns=120 + index)
        snapshot = ledger.snapshot(frame, cutoff_client_ns=140)
        obj, _ = make_adapter()
        with patch.dict(sys.modules, {'execution_context': SHARED}):
            result = obj.predict(Frame(), execution_context=snapshot)
        projection = json.loads(obj.processor.messages[1]['content'][1]['text'])
        actual = [row for row in projection['events'] if row['kind'] == 'receipt']
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0]['requestId'], 'reported-attack')
        self.assertEqual(actual[0]['steps'][0]['keys'], ['LBUTTON'])
        self.assertGreater(projection['projectionOmittedEvents'], 0)
        self.assertLessEqual(result['executionContextText']['bytes'], 2048)


if __name__ == '__main__':
    unittest.main(verbosity=2)
