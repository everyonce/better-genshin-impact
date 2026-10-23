"""Verify source-age rejection even when the server's capture poll is fresh."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import stream_client as client
from observation_timing import frame_timing, observation_timestamp


class ObservationTimingTests(unittest.TestCase):
    def test_source_and_host_clocks_remain_distinct_in_latency_breakdown(self):
        frame = {'capturedAtMs': 40, 'serverNowMs': 50, 'clientReceivedNs': 1_000_000,
                 'transportRoundTripMs': 2, 'sourceTimestampKind': 'wgc_compositor_qpc',
                 'sourceFrame': {'capturedAtMs': -10, 'acquiredAtMs': 0}}
        timing = frame_timing(frame, 4_000_000, 3_000_000, 1.5)
        self.assertEqual(observation_timestamp(frame), -10)
        self.assertEqual(timing['serverAgeAtReceiptMs'], 60)
        self.assertEqual(timing['hostCaptureAgeAtReceiptMs'], 10)
        self.assertEqual(timing['sourceFrameAgeAtReceiptMs'], 60)
        self.assertEqual(timing['sourceAcquisitionDelayMs'], 10)
        self.assertEqual(timing['clientReceiptToPredictMs'], 3)
        self.assertEqual(timing['clientSelectionToPredictMs'], 1)
        self.assertEqual(timing['observationTimestampKind'], 'wgc_compositor_qpc')

    def test_legacy_and_unknown_backends_explicitly_use_host_fallback(self):
        for extra in ({}, {'sourceFrame': None, 'sourceTimestampKind': 'unknown'}):
            with self.subTest(extra=extra):
                frame = {'capturedAtMs': 40, 'serverNowMs': 50, 'clientReceivedNs': 0,
                         'transportRoundTripMs': 1, **extra}
                timing = frame_timing(frame, 0, 0, 0)
                self.assertEqual(timing['serverAgeAtReceiptMs'], 10)
                self.assertIsNone(timing['sourceFrameAgeAtReceiptMs'])
                self.assertIsNone(timing['sourceAcquisitionDelayMs'])
                self.assertEqual(timing['observationTimestampKind'], 'host_capture_request')

    def test_malformed_source_clock_never_falls_back_to_a_fresh_host_poll(self):
        for source in ([], {}, {'capturedAtMs': True}, {'capturedAtMs': '10'},
                       {'capturedAtMs': float('nan')}, {'capturedAtMs': float('inf')}):
            with self.subTest(source=source), self.assertRaises(ValueError):
                observation_timestamp({'capturedAtMs': 999, 'sourceFrame': source})

    def test_future_reported_time_keeps_first_arrival_age_and_raw_anomaly_visible(self):
        frame = {'capturedAtMs': 1040, 'serverNowMs': 1050, 'clientReceivedNs': 0,
                 'transportRoundTripMs': 1, 'sourceTimestampKind': 'wgc_reported_compositor_qpc',
                 'sourceFrame': {'capturedAtMs': 1079, 'acquiredAtMs': 1000,
                                 'freshnessAtMs': 1000, 'freshnessClockKind': 'first_acquisition_qpc'}}
        timing = frame_timing(frame, 0, 0, 0)
        self.assertEqual(observation_timestamp(frame), 1000)
        self.assertEqual(timing['serverAgeAtReceiptMs'], 50)
        self.assertEqual(timing['reportedSourceFrameAgeAtReceiptMs'], -29)
        self.assertEqual(timing['reportedSourceLeadAtAcquisitionMs'], 79)
        self.assertIsNone(timing['sourceAcquisitionDelayMs'])
        self.assertEqual(timing['observationTimestampKind'], 'first_acquisition_qpc')

    def test_bounded_contract_cannot_choose_a_newer_anchor_or_mislabel_the_clock(self):
        source = {'capturedAtMs': 1029, 'acquiredAtMs': 1000,
                  'freshnessAtMs': 1000, 'freshnessClockKind': 'first_acquisition_qpc'}
        for extra in ({'freshnessAtMs': 1029}, {'freshnessClockKind': 'reported_compositor_qpc'},
                      {'freshnessAtMs': float('nan')}, {'acquiredAtMs': None}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                observation_timestamp({'capturedAtMs': 1040, 'sourceFrame': {**source, **extra}})
        with self.assertRaises(ValueError):
            observation_timestamp({'capturedAtMs': 1040, 'sourceTimestampKind': 'wgc_reported_compositor_qpc',
                                   'sourceFrame': {'capturedAtMs': 1029, 'acquiredAtMs': 1000}})

    def test_reported_time_before_arrival_retains_the_older_anchor(self):
        source = {'capturedAtMs': -10, 'acquiredAtMs': 0,
                  'freshnessAtMs': -10, 'freshnessClockKind': 'reported_compositor_qpc'}
        self.assertEqual(observation_timestamp({'capturedAtMs': 40, 'sourceFrame': source}), -10)

    def test_live_client_rejects_old_pixels_and_keeps_wire_identity_on_host_clock(self):
        for source_time, anchor_time, should_submit in ((700, None, False), (900, None, True), (None, None, True),
                                                       (869, 840, False), (929, 900, True)):
            with self.subTest(source_time=source_time, anchor_time=anchor_time), tempfile.TemporaryDirectory() as root:
                submitted = []

                class LocalBridge:
                    """Hold host age at one millisecond while varying the actual pixels' age."""
                    def __init__(self, name):
                        self.handle = io.BytesIO()
                        self.hello = {'sessionId': 's', 'ownerEpoch': 'o', 'goalVersion': 1,
                                      'inputEnabled': True, 'allowedKeys': ['W']}
                        self.index = 0

                    def request(self, command, **kwargs):
                        if command == 'frame':
                            self.index += 1
                            frame = {'type': 'frame', 'frameId': self.index, 'capturedAtMs': 999,
                                     'serverNowMs': 1000, 'width': 2, 'height': 2,
                                     'sourceWidth': 2, 'sourceHeight': 2}
                            if source_time is not None:
                                frame.update(sourceTimestampKind='wgc_compositor_qpc',
                                             sourceFrame={'capturedAtMs': source_time,
                                                          'acquiredAtMs': source_time+10})
                                if anchor_time is not None:
                                    frame['sourceTimestampKind'] = 'wgc_reported_compositor_qpc'
                                    frame['sourceFrame'].update(acquiredAtMs=anchor_time, freshnessAtMs=anchor_time,
                                                                freshnessClockKind='first_acquisition_qpc')
                            return frame, bytes([64] * 12)
                        if command == 'action':
                            submitted.append(kwargs)
                            return {'type': 'accepted'}, b''
                        if command == 'stop':
                            return {'type': 'stopped', 'receipts': []}, b''
                        raise AssertionError(command)

                class Policy:
                    """Return a valid movement action without importing any model or GPU runtime."""
                    metadata = {'model': 'test'}

                    def predict(self, image, source_size):
                        return {'parseValid': True, 'fullActionMs': 0,
                                'steps': [{'keys': ['W'], 'durationMs': 50, 'mouseDx': 0, 'mouseDy': 0}]}

                output = Path(root)/'report.json'
                args = client.parse_arguments([
                    '--model', 'open-p2p', '--source', 'unused', '--checkpoint', 'unused',
                    '--seconds', '.3', '--fps', '30', '--decision-hz', '20', '--enable-input',
                    '--max-input-actions', '1', '--max-observation-age-ms', '150', '--output', str(output)])
                with patch.object(client, 'Bridge', LocalBridge), redirect_stdout(io.StringIO()):
                    self.assertEqual(client.run_episode(args, Policy()), 0)
                report = json.loads(output.read_text())
                self.assertTrue(report['decisions'])
                if should_submit:
                    self.assertEqual(len(submitted), 1)
                    self.assertEqual(submitted[0]['observedAtMs'], 999)
                    self.assertEqual(submitted[0]['expiresAtMs'],
                                     (anchor_time if anchor_time is not None else source_time or 999)+700)
                else:
                    self.assertEqual(submitted, [])
                    self.assertTrue(all(item['acceptance']['reason'] == 'observationTooOld'
                                        for item in report['decisions']))
                    self.assertTrue(all(item['estimatedObservationAgeMs'] >= 1000-(anchor_time or source_time)
                                        for item in report['decisions']))


if __name__ == '__main__':
    unittest.main()
