"""Observation retention under video backpressure; no model, native pipe or game."""
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import stream_client as client
from test_stream_client import HeldRecorder, frame


class MemoryEncoder:
    """A deterministic stdin consumer used only to test recording alignment."""
    def __init__(self):
        self.stdin = io.BytesIO()
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode


def observed_frame(index):
    """Include the source clock, gate generation and motion needed by offline joins."""
    return {**frame(index), 'sourceFrame': {'captureEpoch': 'native-epoch', 'frameId': index,
                                          'capturedAtMs': index * 50 - 3,
                                          'acquiredAtMs': index * 50 - 5,
                                          'freshnessAtMs': index * 50 - 5,
                                          'freshnessClockKind': 'first_acquisition_qpc'},
            'worldReadiness': {'ready': True, 'epoch': 7, 'sourceAtMs': index * 50 - 5},
            'motionEvidence': {'status': 'normal', 'spaceKeyMatched': False, 'xKeyMatched': False},
            'clientReceivedNs': index * 50_000_000, 'transportRoundTripMs': 2.5,
            'receipts': [{'type': 'executed', 'requestId': 'stored-separately'}]}


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


class RecorderMetadataTests(unittest.TestCase):
    def test_rgb192_burst_is_drained_losslessly_and_exact_peak_is_retained(self):
        with tempfile.TemporaryDirectory() as root, \
                patch.object(client.subprocess, 'Popen', return_value=MemoryEncoder()):
            recorder = HeldRecorder(Path(root)/'episode', 'synthetic-encoder', 20, 1024*1024, frame_capacity=32)
            pixels = bytes(192*192*3)
            try:
                for index in range(1, 33):
                    self.assertTrue(recorder.put(dict(observed_frame(index), width=192, height=192), pixels))
                self.assertEqual(recorder.queue.qsize(), 32)
                self.assertFalse(recorder.status()['lossless'])
            finally:
                recorder.release_writer.set()
                result = recorder.close()
            self.assertEqual((result['frameQueueCapacity'], result['maxFrameQueueDepth']), (32, 32))
            self.assertTrue(result['complete'] and result['lossless'])
            self.assertEqual((result['encodedFrames'], result['droppedFrames'], result['recordedObservations']), (32, 0, 32))
            disk = json.loads((recorder.directory/'recording.json').read_bytes())
            self.assertEqual((disk['frameQueueCapacity'], disk['maxFrameQueueDepth'], disk['lossless']), (32, 32, True))

    def test_dropped_video_retains_source_readiness_and_actual_video_indices(self):
        with tempfile.TemporaryDirectory() as root, \
                patch.object(client.subprocess, 'Popen', return_value=MemoryEncoder()):
            recorder = HeldRecorder(Path(root) / 'episode', 'synthetic-encoder', 20, 1024 * 1024,
                                    frame_capacity=1)
            first_encoded = threading.Event()
            recorder._save_preview = lambda metadata, pixels: first_encoded.set()
            original = observed_frame(2)
            original.update(videoFrameIndex=99, videoPtsSeconds=99)
            pixels = bytes(64 * 48 * 3)
            try:
                # Neither admission path may serialize or touch recording files.
                with patch.object(client.json, 'dumps', side_effect=AssertionError('Producer serialized JSON')):
                    self.assertTrue(recorder.put(observed_frame(1), pixels))
                    self.assertFalse(recorder.put(original, pixels))
                self.assertEqual(recorder.metadata_queue.qsize(), 2)
                self.assertFalse(recorder.directory.exists())  # Even directory creation waits for the IO worker.
                recorder.release_writer.set()
                self.assertTrue(first_encoded.wait(2))
                self.assertTrue(recorder.put(observed_frame(3), pixels))
            finally:
                recorder.release_writer.set()
                result = recorder.close()
            self.assertTrue(result['complete'], result)
            self.assertFalse(result['lossless'])
            self.assertEqual((result['frameQueueCapacity'], result['maxFrameQueueDepth']), (1, 1))
            self.assertEqual(result['encodedFrames'], 2)
            self.assertEqual(result['droppedFrames'], 1)
            self.assertEqual(result['recordedObservations'], 3)
            self.assertEqual(result['droppedObservations'], 0)
            summary = json.loads((recorder.directory / 'recording.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['observationSchemaVersion'], 1)
            self.assertEqual(summary['recordedObservations'], 3)
            encoded = read_rows(recorder.directory / 'frames.jsonl')
            observations = read_rows(recorder.directory / 'observations.jsonl')
            self.assertEqual([row['frameId'] for row in encoded], [1, 3])
            self.assertEqual([row['videoFrameIndex'] for row in encoded], [0, 1])
            self.assertEqual([row['videoPtsSeconds'] for row in encoded], [0, .05])
            self.assertEqual([row['frameId'] for row in observations], [1, 2, 3])
            self.assertEqual([row['videoQueueAccepted'] for row in observations], [True, False, True])
            for row in observations:
                self.assertNotIn('videoFrameIndex', row)
                self.assertNotIn('videoPtsSeconds', row)
                self.assertNotIn('receipts', row)
            for key in ('sourceFrame', 'worldReadiness', 'motionEvidence', 'clientReceivedNs', 'transportRoundTripMs'):
                self.assertEqual(observations[1][key], original[key])
            self.assertEqual(original['videoFrameIndex'], 99)
            self.assertIn('receipts', original)

    def test_metadata_exhaustion_is_bounded_and_explicit_without_displacing_receipts(self):
        with tempfile.TemporaryDirectory() as root:
            recorder = HeldRecorder(Path(root) / 'episode', 'unused', 20, 1024 * 1024,
                                    frame_capacity=4, event_capacity=2, metadata_capacity=1)
            try:
                self.assertTrue(recorder.event({'type': 'execution', 'requestId': 'preserved'}))
                with patch.object(client.json, 'dumps', side_effect=AssertionError('Producer serialized JSON')):
                    self.assertTrue(recorder.put(observed_frame(1), bytes(64 * 48 * 3)))
                    self.assertFalse(recorder.put(observed_frame(2), bytes(64 * 48 * 3)))
                self.assertEqual(recorder.metadata_queue.qsize(), 1)
                self.assertEqual(recorder.event_queue.qsize(), 1)
                self.assertIn('source timing metadata is incomplete', recorder.error)
            finally:
                recorder.release_writer.set()
                result = recorder.close()
            self.assertFalse(result['complete'])
            self.assertEqual(result['droppedObservations'], 1)
            self.assertEqual(result['recordedObservations'], 1)
            self.assertEqual(result['droppedEvents'], 0)
            self.assertEqual(result['abandonedFrames'], 2)
            self.assertEqual(read_rows(recorder.directory / 'events.jsonl')[0]['requestId'], 'preserved')

    def test_encoder_failure_does_not_claim_admitted_images_were_encoded(self):
        with tempfile.TemporaryDirectory() as root:
            recorder = client.AsyncVideoRecorder(Path(root) / 'episode', str(Path(root) / 'missing.exe'),
                                                20, 1024 * 1024)
            self.assertTrue(recorder.put(observed_frame(1), bytes(64 * 48 * 3)))
            result = recorder.close()
            self.assertFalse(result['complete'])
            self.assertEqual(result['encodedFrames'], 0)
            self.assertEqual(result['recordedObservations'], 1)
            self.assertEqual(result['droppedObservations'], 0)
            self.assertEqual(result['abandonedFrames'], 1)
            row = read_rows(recorder.directory / 'observations.jsonl')[0]
            self.assertTrue(row['videoQueueAccepted'])
            self.assertNotIn('videoFrameIndex', row)
            self.assertEqual(read_rows(recorder.directory / 'frames.jsonl'), [])

    def test_close_drains_observation_arriving_after_last_metadata_drain(self):
        reached_empty_check, release_empty_check = threading.Event(), threading.Event()

        class PausedEmptyQueue(client.RecordingFrameQueue):
            def get_nowait(self):
                reached_empty_check.set()
                if not release_empty_check.wait(2):
                    raise AssertionError('Late observation was not supplied')
                return super().get_nowait()

        with tempfile.TemporaryDirectory() as root:
            recorder = HeldRecorder(Path(root) / 'episode', 'unused', 20, 1024 * 1024)
            recorder.queue = PausedEmptyQueue(maxsize=8)
            recorder.release_writer.set()
            try:
                self.assertTrue(reached_empty_check.wait(2))
                # Model a producer resumed at metadata admission after its earlier
                # image-drop decision; close must inspect this queue as well.
                recorder.metadata_queue.put_nowait({'frameId': 2, 'capturedAtMs': 100,
                                                    'videoQueueAccepted': False})
                timer = threading.Timer(.02, release_empty_check.set)
                timer.start()
                result = recorder.close()
                timer.join()
            finally:
                release_empty_check.set()
                recorder.close()
            self.assertTrue(result['complete'], result)
            self.assertEqual(result['recordedObservations'], 1)
            self.assertEqual(result['droppedObservations'], 0)
            self.assertEqual(read_rows(recorder.directory / 'observations.jsonl')[0]['frameId'], 2)

    def test_invalid_observation_serialization_is_reported_as_metadata_loss(self):
        with tempfile.TemporaryDirectory() as root:
            recorder = HeldRecorder(Path(root) / 'episode', 'unused', 20, 1024 * 1024)
            recorder.put({**observed_frame(1), 'invalid': object()}, bytes(64 * 48 * 3))
            recorder.release_writer.set()
            result = recorder.close()
            self.assertFalse(result['complete'])
            self.assertEqual(result['droppedObservations'], 1)
            self.assertEqual(result['recordedObservations'], 0)
            self.assertEqual(result['abandonedFrames'], 1)
            self.assertIn('JSON serializable', result['error'])

    def test_observation_bytes_participate_in_budget_before_encoder_launch(self):
        with tempfile.TemporaryDirectory() as root, patch.object(client.subprocess, 'Popen') as launch:
            recorder = HeldRecorder(Path(root) / 'episode', 'unused', 20, 100)
            recorder.put(observed_frame(1), bytes(64 * 48 * 3))
            recorder.release_writer.set()
            result = recorder.close()
            launch.assert_not_called()
            self.assertFalse(result['complete'])
            self.assertIn('byte budget', result['error'])
            self.assertEqual(result['recordedObservations'], 1)
            self.assertEqual(result['abandonedFrames'], 1)


if __name__ == '__main__':
    unittest.main()
