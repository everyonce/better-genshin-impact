"""Opt-in stream integration using synthetic RGB, fake policy and an in-memory pipe."""

from contextlib import redirect_stderr
import io
import time
import unittest
from unittest.mock import patch

import stream_client as client
from test_stream_client import CaptureQualityTests, CapturingRecorder, FakePolicy, ScriptedBridge


class ContextPolicy(FakePolicy):
    """Capture the immutable argument without loading image or tensor packages."""
    def __init__(self):
        super().__init__()
        self.contexts = []

    def predict(self, image, size, **kwargs):
        self.contexts.append(kwargs.get('execution_context'))
        result = super().predict(image, size)
        if kwargs.get('execution_context') is not None:
            from execution_context import render_gamescaling_context
            import hashlib
            text = render_gamescaling_context(kwargs['execution_context']).encode('utf-8')
            result['executionContextText'] = {'sha256': hashlib.sha256(text).hexdigest(), 'bytes': len(text)}
        return result


class ContextBridge(ScriptedBridge):
    """Add an exact lease identity and a complete terminal receipt to the old fixture."""
    def __init__(self):
        super().__init__([bytes(range(12))])
        self.hello.update(ownerEpoch='synthetic-owner', goalVersion=1)

    def request(self, command, **kwargs):
        reply, pixels = super().request(command, **kwargs)
        if command == 'stop':
            reply['receipts'] = [{'requestId': 'synthetic-stop', 'modelId': 'gamescaling', 'frameId': 1,
                'status': 'cancelled', 'reason': 'client_stop', 'acceptedAtMs': 0,
                'endedAtMs': 1, 'appliedSteps': []}]
        return reply, pixels


class ExecutionStreamTests(unittest.TestCase):
    """Exercise the real episode loop while preserving existing freshness decisions."""
    def run_mode(self, mode, *, model='gamescaling', extra=()):
        """Reuse the bounded original synthetic harness and its existing cleanup."""
        policy, recorder, bridge = ContextPolicy(), CapturingRecorder(), ContextBridge()
        code, report = CaptureQualityTests().run_episode(bridge, policy, recorder,
            extra=('--execution-context', mode, *extra), model=model)
        return code, report, policy, recorder, bridge

    def test_model_mode_passes_and_records_exact_predecision_snapshot(self):
        code, report, policy, recorder, bridge = self.run_mode('model')
        self.assertEqual(code, 0)
        self.assertTrue(policy.contexts)
        self.assertEqual(len(policy.contexts), len(report['decisions']))
        for snapshot, decision in zip(policy.contexts, report['decisions']):
            self.assertEqual(snapshot.to_dict(), decision['executionContext'])
            self.assertEqual(decision['acceptance']['type'], 'notSubmitted')
            self.assertLessEqual(decision['executionContextText']['bytes'], 2048)
        proposals = [e for e in recorder.events if e.get('type') == 'proposal']
        self.assertEqual([e['executionContextText'] for e in proposals],
                         [d['executionContextText'] for d in report['decisions']])
        self.assertNotIn('action', bridge.commands)

    def test_record_mode_does_not_condition_p2p(self):
        code, report, policy, _, _ = self.run_mode('record', model='open-p2p')
        self.assertEqual(code, 0)
        self.assertTrue(report['decisions'])
        self.assertTrue(all(snapshot is None for snapshot in policy.contexts))
        self.assertTrue(all(d['executionContextMode'] == 'record' for d in report['decisions']))

    def test_off_mode_preserves_previous_wire_and_result_shape(self):
        code, report, policy, recorder, _ = self.run_mode('off')
        self.assertEqual(code, 0)
        self.assertNotIn('executionContext', report)
        self.assertNotIn('executionContextFinal', report)
        self.assertTrue(all(snapshot is None for snapshot in policy.contexts))
        self.assertTrue(all('executionContext' not in d for d in report['decisions']))
        self.assertTrue(all('executionContext' not in event for event in recorder.events))

    def test_terminal_receipt_is_saved_after_last_decision(self):
        _, report, policy, recorder, _ = self.run_mode('model')
        final = report['executionContextFinal']
        receipts = [event for event in final['events'] if event['kind'] == 'receipt']
        self.assertEqual(receipts[-1]['payload']['requestId'], 'synthetic-stop')
        self.assertTrue(all(not any(event['kind'] == 'receipt' for event in s.to_dict()['events'])
                            for s in policy.contexts))
        self.assertEqual([event['context'] for event in recorder.events
                          if event.get('type') == 'executionContextFinal'], [final])

    def test_context_materialization_is_counted_before_client_budget_gate(self):
        from execution_context import ExecutionSnapshot
        original = ExecutionSnapshot.to_dict
        def delayed(snapshot):
            time.sleep(.03)
            return original(snapshot)
        with patch.object(ExecutionSnapshot, 'to_dict', delayed):
            _, report, _, _, bridge = self.run_mode('record', extra=('--enable-input',))
        self.assertTrue(report['decisions'])
        self.assertTrue(all(d['policyWallMs'] >= 25 for d in report['decisions']))
        self.assertTrue(all(d['acceptance'] == {'type': 'notSubmitted', 'reason': 'modelMissedDecisionBudget'}
                            for d in report['decisions']))
        self.assertNotIn('action', bridge.commands)

    def test_model_mode_rejects_incompatible_options_before_model_or_pipe(self):
        base = ['--output', 'unused.json', '--source', 'source', '--checkpoint', 'checkpoint',
                '--execution-context', 'model']
        cases = [('--model', 'open-p2p'), ('--model', 'gamescaling', '--history', '1'),
                 ('--model', 'gamescaling', '--cuda-graph', '--gamescaling-prefix-cache')]
        for arguments in cases:
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit):
                client.parse_arguments([*base, *arguments])
        args = client.parse_arguments([*base, '--model', 'gamescaling'])
        args.model = 'open-p2p'
        with patch.object(client, 'Bridge', side_effect=AssertionError('pipe must stay closed')), \
                self.assertRaisesRegex(ValueError, 'requires gamescaling'):
            client.run_episode(args)


if __name__ == '__main__':
    unittest.main()
