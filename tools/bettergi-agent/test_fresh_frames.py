"""Check decision-time refresh against a deterministically stale capture mailbox."""
import io
from contextlib import redirect_stdout
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import stream_client as client


class FreshFrameTests(unittest.TestCase):
    def test_resident_default_can_be_disabled_for_matched_latency_trials(self):
        base = ['--resident', '--rdp-session-id', '3', '--output', 'unused.json']
        self.assertTrue(client.parse_arguments(base).fresh_frame_at_decision)
        self.assertFalse(client.parse_arguments(base + ['--no-fresh-frame-at-decision']).fresh_frame_at_decision)
        self.assertFalse(client.parse_arguments(['--output', 'unused.json']).fresh_frame_at_decision)

    def test_refresh_uses_new_server_frame_and_never_replays_the_older_mailbox_image(self):
        for refresh, expected_frame in ((False, 1), (True, 2)):
            with self.subTest(refresh=refresh), tempfile.TemporaryDirectory() as root:
                published = threading.Event()
                main_thread = threading.current_thread()
                original_publish = client.LatestFrame.publish
                submitted, observed_pixels, diagnostic_requests = [], [], []

                class LocalBridge:
                    """Publish frame one on the recorder poll and frame two on demand."""
                    def __init__(self, name):
                        self.handle = io.BytesIO()
                        self.hello = {'sessionId': 's', 'ownerEpoch': 'o', 'goalVersion': 1,
                                      'inputEnabled': True, 'allowedKeys': ['W'],
                                      'supportsReadinessSnapshots': True}
                        self.frame_id = 0

                    def request(self, command, **kwargs):
                        if command == 'configureDiagnostics':
                            diagnostic_requests.append(kwargs)
                            return {'type': 'diagnostics', 'diagnostics': {'enabled': True}}, b''
                        if command == 'status':
                            return {'type': 'status', 'diagnostics': {'enabled': True, 'written': 2, 'pending': 0}}, b''
                        if command == 'frame':
                            self.frame_id += 1
                            return {'type': 'frame', 'frameId': self.frame_id, 'capturedAtMs': 0,
                                    'serverNowMs': 1, 'width': 2, 'height': 2,
                                    'sourceWidth': 2, 'sourceHeight': 2}, bytes([self.frame_id] * 12)
                        if command == 'action':
                            submitted.append(kwargs['frameId'])
                            return {'type': 'accepted'}, b''
                        if command == 'stop':
                            return {'type': 'stopped', 'receipts': []}, b''
                        raise AssertionError(command)

                class Policy:
                    """Observe the actual image selected; avoid importing a GPU framework."""
                    metadata = {'model': 'test'}

                    def predict(self, image, source_size):
                        observed_pixels.append(image.getpixel((0, 0))[0])
                        return {'parseValid': True, 'fullActionMs': 0,
                                'steps': [{'keys': ['W'], 'durationMs': 50, 'mouseDx': 0, 'mouseDy': 0}]}

                def publish(mailbox, metadata, pixels):
                    original_publish(mailbox, metadata, pixels)
                    published.set()

                def sleep_until(deadline, stopped):
                    if threading.current_thread() is main_thread:
                        self.assertTrue(published.wait(2), 'The initial capture was never published')
                        return not stopped.is_set()
                    if not published.is_set():
                        return True
                    # Freeze periodic polling after the old frame. Only the decision
                    # refresh can obtain frame two before the single accepted action.
                    stopped.wait(2)
                    return False

                output = Path(root)/'report.json'
                args = client.parse_arguments([
                    '--model', 'open-p2p', '--source', 'unused', '--checkpoint', 'unused',
                    '--seconds', '1', '--fps', '1', '--decision-hz', '1', '--enable-input',
                    '--max-input-actions', '1', '--readiness-snapshots', '--output', str(output),
                    '--fresh-frame-at-decision' if refresh else '--no-fresh-frame-at-decision'])
                with patch.object(client, 'Bridge', LocalBridge), \
                        patch.object(client.LatestFrame, 'publish', publish), \
                        patch.object(client, 'sleep_until', sleep_until), redirect_stdout(io.StringIO()):
                    self.assertEqual(client.run_episode(args, Policy()), 0)
                report = json.loads(output.read_text())
                self.assertEqual(submitted, [expected_frame])
                self.assertEqual(observed_pixels, [expected_frame])
                self.assertEqual(diagnostic_requests, [{'recordReadinessTransitions': True}])
                self.assertEqual(report['readinessDiagnosticsBeforeStop']['written'], 2)
                self.assertEqual(report['framesReceived'], expected_frame)
                self.assertEqual(report['decisions'][0]['frameId'], expected_frame)
                timing = report['decisions'][0]['frameTiming']
                self.assertGreaterEqual(timing['clientReceiptToPredictMs'], timing['clientSelectionToPredictMs'])
                self.assertEqual(timing['serverAgeAtReceiptMs'], 1)

    def test_requested_diagnostics_fail_before_capture_when_server_cannot_confirm(self):
        for supported, acknowledgement in ((False, None), (True, {'type': 'rejected'}),
                                           (True, {'type': 'diagnostics', 'diagnostics': {'enabled': False}})):
            with self.subTest(supported=supported, acknowledgement=acknowledgement):
                class LocalBridge:
                    """A setup failure must close the lease without starting any input work."""
                    def __init__(self, name):
                        self.handle = io.BytesIO()
                        self.hello = {'sessionId': 'diagnostics-setup-test', 'inputEnabled': False,
                                      'supportsReadinessSnapshots': supported}

                    def request(self, command, **kwargs):
                        if command != 'configureDiagnostics':
                            raise AssertionError('No capture or input request is allowed after failed setup')
                        return acknowledgement, b''

                bridge = LocalBridge('test')
                args = client.parse_arguments(['--readiness-snapshots', '--output', 'unused.json'])
                with patch.object(client, 'Bridge', return_value=bridge):
                    with self.assertRaises(RuntimeError):
                        client.run_episode(args)
                self.assertTrue(bridge.handle.closed)


if __name__ == '__main__':
    unittest.main()
