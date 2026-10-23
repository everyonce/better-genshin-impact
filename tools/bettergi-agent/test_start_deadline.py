"""Fake-bridge checks for first-input deadlines; no game, model or GPU access."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import stream_client as client


class StartDeadlineTests(unittest.TestCase):
    """Exercise the real episode submission path and retained report evidence."""
    def run_case(self, capability, with_source=True):
        """Vary only the advertised capability and immutable source-clock metadata."""
        submitted = []

        class LocalBridge:
            def __init__(self, name):
                self.handle = io.BytesIO()
                self.hello = {'sessionId': 's', 'ownerEpoch': 'o', 'goalVersion': 1,
                              'inputEnabled': True, 'allowedKeys': ['W'], **capability}
                self.index = 0

            def request(self, command, **kwargs):
                if command == 'frame':
                    self.index += 1
                    frame = {'type': 'frame', 'frameId': self.index, 'capturedAtMs': 999,
                             'serverNowMs': 1000, 'width': 2, 'height': 2,
                             'sourceWidth': 2, 'sourceHeight': 2}
                    if with_source:
                        # Future compositor time must not move the deadline
                        # past first acquisition or the fresh host capture poll.
                        frame.update(sourceTimestampKind='wgc_reported_compositor_qpc',
                                     sourceFrame={'capturedAtMs': 1029, 'acquiredAtMs': 950,
                                                  'freshnessAtMs': 950,
                                                  'freshnessClockKind': 'first_acquisition_qpc'})
                    return frame, bytes([64] * 12)
                if command == 'action':
                    submitted.append(kwargs)
                    return {'type': 'accepted'}, b''
                if command == 'stop':
                    return {'type': 'stopped', 'receipts': []}, b''
                raise AssertionError(command)

        class Policy:
            metadata = {'model': 'synthetic'}

            def predict(self, image, source_size):
                self.metadata = {'model': 'synthetic', 'validatedActions': 1}
                return {'parseValid': True, 'fullActionMs': 0,
                        'steps': [{'keys': ['W'], 'durationMs': 50, 'mouseDx': 0, 'mouseDy': 0}]}

        with tempfile.TemporaryDirectory() as root:
            output = Path(root)/'report.json'
            args = client.parse_arguments([
                '--model', 'open-p2p', '--source', 'unused', '--checkpoint', 'unused',
                '--seconds', '1', '--fps', '30', '--decision-hz', '20', '--enable-input',
                '--max-input-actions', '1', '--max-observation-age-ms', '150',
                '--action-hold-ms', '100', '--output', str(output)])
            with patch.object(client, 'Bridge', LocalBridge), redirect_stdout(io.StringIO()):
                self.assertEqual(client.run_episode(args, Policy()), 0)
            report = json.loads(output.read_text())
        self.assertEqual(len(submitted), 1)
        self.assertEqual(submitted[0]['observedAtMs'], 999)
        self.assertEqual(submitted[0]['expiresAtMs'], (950 if with_source else 999)+700)
        self.assertEqual(submitted[0]['steps'][0]['durationMs'], 100)
        self.assertEqual(report['decisions'][0]['rawPolicySteps'][0]['durationMs'], 50)
        return submitted[0], report

    def test_supported_deadline_uses_source_anchor_and_keeps_wire_identity_and_hold(self):
        request, report = self.run_case({'supportsStartBeforeMs': True, 'maxActionStartAgeMs': 500})
        self.assertEqual(request['startBeforeMs'], 1100)
        self.assertEqual(report['decisions'][0]['startBeforeMs'], 1100)
        policy = report['firstInputDeadlinePolicy']
        self.assertTrue(policy['serverSupported'])
        self.assertTrue(policy['serverEnforcementRequested'])
        self.assertEqual(policy['enforcement'], 'client-proposal-and-server-first-input')
        self.assertEqual(policy['maxObservationAgeMs'], 150)

    def test_final_policy_metadata_retains_validation_without_rewriting_start(self):
        _, report = self.run_case({})
        self.assertEqual(report['policyMetadata'], {'model': 'synthetic'})
        self.assertEqual(report['finalPolicyMetadata'], {'model': 'synthetic', 'validatedActions': 1})

    def test_unknown_source_uses_existing_host_clock_fallback(self):
        request, report = self.run_case({'supportsStartBeforeMs': True}, with_source=False)
        self.assertEqual(request['startBeforeMs'], 1149)
        self.assertEqual(report['decisions'][0]['observationTimestampMs'], 999)

    def test_legacy_or_non_boolean_capability_omits_optional_wire_field(self):
        for capability in ({}, {'supportsStartBeforeMs': False},
                           {'supportsStartBeforeMs': 'true'}, {'supportsStartBeforeMs': 1}):
            with self.subTest(capability=capability):
                request, report = self.run_case(capability)
                self.assertNotIn('startBeforeMs', request)
                self.assertNotIn('startBeforeMs', report['decisions'][0])
                policy = report['firstInputDeadlinePolicy']
                self.assertFalse(policy['serverSupported'])
                self.assertFalse(policy['serverEnforcementRequested'])
                self.assertEqual(policy['enforcement'], 'client-proposal-only')


if __name__ == '__main__':
    unittest.main()
