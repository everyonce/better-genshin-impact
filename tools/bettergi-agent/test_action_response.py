"""Action settlement through the actual episode loop with inert transport and policy."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import stream_client as client


def reply(kind, request_id):
    """Match the camel-case C# action reply; accepted means admission only."""
    return {'type': kind, 'requestId': request_id,
            'reason': None if kind == 'accepted' else 'start_deadline_expired',
            'receivedAtMs': 1001, 'acceptedAtMs': 1001 if kind == 'accepted' else None}


class ResponseIdentityTests(unittest.TestCase):
    """Do not derive settlement from unrecognized or unbound server metadata."""
    def test_local_handoff_refusal_never_registers_an_unknown_wire_action(self):
        arguments = dict(frameId=2153, requestId='next', startBeforeMs=79134.391)
        for key in ('unacknowledgedAction','unacknowledgedRecoveryAction'):
            with self.subTest(key=key):
                bridge, warm, report = Mock(), Mock(), {}
                warm.require_batch_dispatch_window.side_effect = RuntimeError('handoff deadline')
                with self.assertRaisesRegex(RuntimeError,'handoff deadline'):
                    client.transmit_bound_action(bridge,warm,report,arguments,key,arguments)
                bridge.request.assert_not_called()
                self.assertNotIn(key,report)
                warm.require_batch_dispatch_window.side_effect = None
                bridge.request.side_effect = EOFError('lost response')
                with self.assertRaises(EOFError):
                    client.transmit_bound_action(bridge,warm,report,arguments,key,arguments)
                self.assertEqual(report[key],arguments)

    def test_current_accepted_and_rejected_shapes(self):
        for kind, expected in [('accepted', True), ('rejected', False)]:
            self.assertIs(client.action_response_accepted(reply(kind, 'r1'), 'r1'), expected)

    def test_absent_or_nonstring_request_id_is_unresolved(self):
        for value in [None, True, 1, 1.0, [], {}, '']:
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, 'Unresolved'):
                client.action_response_accepted({'type': 'accepted', 'requestId': value}, 'r1')

    def test_other_request_id_is_unresolved_for_both_outcomes(self):
        for kind in ['accepted', 'rejected']:
            with self.subTest(kind=kind), self.assertRaisesRegex(RuntimeError, 'Unresolved'):
                client.action_response_accepted(reply(kind, 'earlier-request'), 'r1')

    def test_unknown_response_kinds_cannot_be_local_rejection(self):
        for kind in [None, True, 1, [], 'notSubmitted', 'status', 'Accepted', 'error']:
            with self.subTest(kind=kind), self.assertRaisesRegex(RuntimeError, 'Unresolved'):
                client.action_response_accepted({'type': kind, 'requestId': 'r1'}, 'r1')

    def test_nonobject_response_is_unresolved(self):
        for value in [None, True, 1, 'accepted', []]:
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, 'Unresolved'):
                client.action_response_accepted(value, 'r1')

    def test_payload_is_not_an_action_acknowledgment(self):
        with self.assertRaisesRegex(RuntimeError, 'Unresolved'):
            client.action_response_accepted(reply('accepted', 'r1'), 'r1', b'unexpected')

    def test_actual_session_identity_rejection_is_unbound(self):
        with self.assertRaisesRegex(RuntimeError, 'Unresolved'):
            client.action_response_accepted({'type': 'rejected', 'reason': 'session_identity_mismatch'}, 'r1')


class EpisodeSettlementTests(unittest.TestCase):
    """Unknown outcomes retain pending history and take existing stop/disconnect cleanup."""
    def run_case(self, response='accepted', *, archive=False, local_rejection=False, feedback=True):
        commands, submitted, settlements, resets, predictions = [], [], [], [], []

        class LocalBridge:
            """Publish one stable frame and never perform transport or native input."""
            def __init__(self):
                self.handle = io.BytesIO()
                self.hello = {'sessionId': 'settlement-session', 'ownerEpoch': 'settlement-owner',
                              'goalVersion': 1, 'inputEnabled': True, 'allowedKeys': ['W']}

            def request(self, command, **kwargs):
                commands.append(command)
                if command == 'frame':
                    return {'type': 'frame', 'frameId': 1, 'capturedAtMs': 995, 'serverNowMs': 1000,
                            'width': 2, 'height': 2, 'sourceWidth': 2, 'sourceHeight': 2,
                            'pixelFormat': 'rgb24'}, bytes(range(12))
                if command == 'stop':
                    return {'type': 'stopped', 'receipts': []}, b''
                if command == 'action':
                    submitted.append(dict(kwargs))
                    if isinstance(response, BaseException):
                        raise response
                    if callable(response):
                        return response(kwargs['requestId'])
                    return reply(response, kwargs['requestId']), b''
                raise AssertionError(command)

        class Policy:
            """Keep pending history observable without importing a numerical library."""
            metadata = {'model': 'inert'}
            execution_feedback = feedback
            pending = False

            def predict(self, image, size):
                predictions.append(1)
                self.pending = True
                return {'parseValid': not local_rejection, 'fullActionMs': 0,
                        'steps': [{'keys': ['W'], 'durationMs': 50, 'mouseDx': 0, 'mouseDy': 0}]}

            def finish_action(self, committed):
                settlements.append(committed)
                self.pending = False

            def reset(self):
                resets.append(1)

        bridge, policy = LocalBridge(), Policy()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'00001.json'
            args = client.parse_arguments(['--model', 'open-p2p', '--source', 'inert', '--checkpoint', 'inert',
                '--seconds', '.15', '--fps', '100', '--decision-hz', '100', '--enable-input',
                '--max-input-actions', '1', '--output', str(output)])
            if archive:
                args.lease_output = str(Path(folder)/'lease.json')
            caught = None
            with patch.object(client, 'Bridge', return_value=bridge), redirect_stdout(io.StringIO()):
                try:
                    code = client.run_episode(args, policy)
                except Exception as exc:
                    caught, code = exc, None
            self.assertTrue(output.exists(), f'No report after {caught!r}; commands={commands!r}')
            report = json.loads(output.read_text(encoding='utf-8'))
            manifest = json.loads(Path(args.lease_output).read_text()) if archive else None
        self.assertTrue(bridge.handle.closed)
        self.assertEqual(commands.count('stop'), 1)
        self.assertEqual(len(predictions), 1)
        self.assertEqual(resets, [])
        self.assertNotIn('release', commands)
        self.assertIsNone(report.get('stopError'))
        self.assertIsNone(report.get('streamError'))
        return report, manifest, submitted, settlements, policy.pending, caught, code

    def assert_unresolved(self, response, **options):
        """Prove no false rollback, retry or history reset after a submitted unknown outcome."""
        report, manifest, submitted, settlements, pending, caught, code = self.run_case(response, **options)
        self.assertIsNotNone(caught)
        self.assertIsNone(code)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(len(submitted), 1)
        self.assertEqual(settlements, [])
        self.assertTrue(pending)
        self.assertEqual(report['acceptedInputActions'], 0)
        self.assertEqual(report['decisions'], [])
        unresolved = report['unacknowledgedAction']
        self.assertEqual(unresolved['requestId'], submitted[0]['requestId'])
        self.assertEqual(unresolved['steps'], submitted[0]['steps'])
        self.assertEqual(unresolved['frame']['frameId'], submitted[0]['frameId'])
        self.assertEqual(unresolved['expiresAtMs'], submitted[0]['expiresAtMs'])
        if manifest:
            self.assertEqual(manifest['unacknowledgedAction'], submitted[0]['requestId'])
        return report

    def test_matching_acceptance_commits_admission_without_execution_receipt(self):
        report, _, submitted, settlements, pending, error, code = self.run_case()
        self.assertEqual(code, 0)
        self.assertIsNone(error)
        self.assertEqual((len(submitted), settlements, pending), (1, [True], False))
        self.assertEqual(report['acceptedInputActions'], 1)
        self.assertEqual(report['receipts'], [])
        self.assertNotIn('unacknowledgedAction', report)

    def test_matching_rejection_rolls_back_known_proposal(self):
        report, _, submitted, settlements, pending, error, code = self.run_case('rejected')
        self.assertEqual(code, 0)
        self.assertIsNone(error)
        self.assertEqual((len(submitted), settlements, pending), (1, [False], False))
        self.assertEqual(report['decisions'][0]['acceptance']['reason'], 'start_deadline_expired')
        self.assertNotIn('unacknowledgedAction', report)

    def test_local_not_submitted_rolls_back_without_request(self):
        report, _, submitted, settlements, pending, error, code = self.run_case(local_rejection=True)
        self.assertEqual(code, 0)
        self.assertIsNone(error)
        self.assertEqual((submitted, settlements, pending), ([], [False], False))
        self.assertEqual(report['decisions'][0]['acceptance']['type'], 'notSubmitted')

    def test_wrong_accepted_id_is_unresolved(self):
        self.assert_unresolved(lambda _: (reply('accepted', 'another-request'), b''))

    def test_wrong_rejected_id_is_unresolved(self):
        self.assert_unresolved(lambda _: (reply('rejected', 'another-request'), b''))

    def test_session_rejection_without_id_is_unresolved(self):
        self.assert_unresolved(lambda _: ({'type': 'rejected', 'reason': 'session_identity_mismatch'}, b''))

    def test_server_not_submitted_is_unresolved(self):
        self.assert_unresolved('notSubmitted')

    def test_malformed_response_is_unresolved(self):
        self.assert_unresolved(lambda _: (None, b''))

    def test_lost_response_retains_nonarchive_request(self):
        self.assert_unresolved(OSError('synthetic lost response'))

    def test_unknown_response_retains_archive_request(self):
        self.assert_unresolved('unknown', archive=True)

    def test_lost_response_retains_archive_request(self):
        self.assert_unresolved(EOFError('synthetic EOF'), archive=True)

    def test_unexpected_payload_is_unresolved(self):
        self.assert_unresolved(lambda rid: (reply('accepted', rid), b'pixels'))

    def test_reply_validation_also_applies_without_feedback(self):
        self.assert_unresolved('unknown', feedback=False)


if __name__ == '__main__':
    unittest.main()
