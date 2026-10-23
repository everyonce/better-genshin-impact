"""CPU-only protocol, latest-frame, recording, and real FFmpeg integration tests."""
import io
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import stream_client as client


def packet(message, payload=b''):
    header = json.dumps(message).encode()
    return struct.pack('<I', len(header)) + header + payload


class FragmentedPipe:
    """Simulate short native pipe reads and writes without opening an actual game."""
    def __init__(self, incoming):
        self.incoming = io.BytesIO(incoming)
        self.written = bytearray()
        self.closed = False

    def read(self, size):
        return self.incoming.read(min(3, size))

    def write(self, data):
        count = min(5, len(data))
        self.written.extend(data[:count])
        return count

    def close(self):
        self.closed = True


def bridge_with(handle):
    bridge = object.__new__(client.Bridge)
    bridge.handle = handle
    bridge.lock = threading.Lock()
    bridge.hello = {'sessionId': 'test-session', 'ownerEpoch': 'test-owner', 'goalVersion': 1}
    return bridge


def frame(index, timestamp=None, width=64, height=48):
    return {'frameId': index, 'capturedAtMs': timestamp if timestamp is not None else index * 50,
            'width': width, 'height': height, 'pixelFormat': 'rgb24'}


class ProtocolTests(unittest.TestCase):
    def test_soft_cadence_allows_only_fresh_late_actions(self):
        result = {'parseValid': True, 'steps': [{'keys': ['W']}]}
        self.assertEqual(client.proposal_rejection(result, {'W'}, True, 120, 150, 80, 66), 'modelMissedDecisionBudget')
        self.assertIsNone(client.proposal_rejection(result, {'W'}, True, 120, 150, 80, 66, enforce_compute_budget=False))
        self.assertEqual(client.proposal_rejection(result, {'W'}, True, 180, 150, 80, 66,
                                                   enforce_compute_budget=False), 'observationTooOld')

    def test_observe_client_retains_final_stop_receipt_without_importing_a_model(self):
        class LocalBridge:
            def __init__(self, name):
                self.name = name
                self.handle = FragmentedPipe(b'')
                self.hello = {'version': 1, 'sessionId': 's', 'ownerEpoch': 'o', 'goalVersion': 1,
                              'inputEnabled': False, 'allowedKeys': []}
                self.count = 0

            def request(self, command, **kwargs):
                if command == 'stop':
                    return {'type': 'stopped', 'receipts': [{'requestId': 'final', 'appliedSteps': []}]}, b''
                if command != 'frame':
                    raise AssertionError('Observation mode must not submit actions')
                self.count += 1
                return dict(frame(self.count, width=2, height=2), type='frame', receipts=[],
                            serverNowMs=self.count * 50, sourceWidth=2, sourceHeight=2), bytes(range(12))

        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / 'report.json'
            argv = ['stream_client.py', '--seconds', '.06', '--fps', '100', '--output', str(target)]
            with patch.object(client, 'Bridge', LocalBridge), patch.object(sys, 'argv', argv):
                self.assertEqual(client.main(), 0)
            report = json.loads(target.read_text())
            self.assertGreater(report['framesReceived'], 0)
            self.assertFalse(report['inputRequested'])
            self.assertEqual(report['decisions'], [])
            self.assertEqual(report['receipts'][0]['requestId'], 'final')

    def test_fragmented_payload_and_partial_writes_keep_identity_and_version(self):
        pixels = bytes(range(24))
        handle = FragmentedPipe(packet({'type': 'frame', 'payloadBytes': len(pixels)}, pixels))
        bridge = bridge_with(handle)
        metadata, actual = bridge.request('frame')
        self.assertEqual(actual, pixels)
        self.assertEqual(metadata['type'], 'frame')
        size = struct.unpack('<I', handle.written[:4])[0]
        self.assertEqual(size, len(handle.written) - 4)
        request = json.loads(handle.written[4:])
        self.assertEqual(request, dict(version=1, command='frame', **bridge.hello))

    def test_invalid_lengths_and_nonobject_headers_fail_before_payload_allocation(self):
        for incoming in (struct.pack('<I', 0), struct.pack('<I', 4 * 1024 * 1024 + 1),
                         packet([]), packet({'payloadBytes': -1}), packet({'payloadBytes': True}),
                         packet({'payloadBytes': 32 * 1024 * 1024 + 1})):
            with self.subTest(incoming=incoming[:50]):
                with self.assertRaises(ValueError):
                    bridge_with(FragmentedPipe(incoming))._read()

    def test_disconnect_and_request_size_limits(self):
        with self.assertRaises(EOFError):
            bridge_with(FragmentedPipe(b'\x01\x00'))._read()
        handle = FragmentedPipe(b'')
        bridge = bridge_with(handle)
        with self.assertRaises(ValueError):
            bridge.request('action', modelId='x' * 65536)
        with self.assertRaises(ValueError):
            bridge.request('action', observedAtMs=float('nan'))
        self.assertEqual(handle.written, b'')

    def test_bad_handshake_closes_pipe_and_default_namespace_is_validated(self):
        handle = FragmentedPipe(packet({'type': 'hello', 'version': 2}))
        with patch.object(client.os, 'name', 'nt'), patch('builtins.open', return_value=handle):
            with self.assertRaises(ValueError):
                client.Bridge('BetterGI.Agent.local')
        self.assertTrue(handle.closed)
        with self.assertRaises(ValueError):
            client.Bridge('other-service')

    def test_latest_mailbox_never_builds_a_frame_backlog(self):
        latest = client.LatestFrame()
        self.assertIsNone(latest.newer_than(None))
        for index in range(1000):
            latest.publish(frame(index), bytes([index % 256]))
        self.assertEqual(latest.newer_than(10)[0]['frameId'], 999)
        self.assertIsNone(latest.newer_than(999))

    def test_policy_clock_skips_late_ticks_and_does_not_catch_up(self):
        cadence = client.DecisionCadence(20, 0)
        cadence.advance(.022)
        self.assertAlmostEqual(cadence.next_at, .05)
        cadence.advance(.191)
        self.assertAlmostEqual(cadence.next_at, .2)
        self.assertAlmostEqual(cadence.remaining(.191), .009)
        cadence.advance(.25)
        self.assertAlmostEqual(cadence.next_at, .3)
        self.assertGreater(cadence.remaining(.25), 0)

    def test_soft_policy_clock_resumes_after_overrun_then_limits_fast_predictions(self):
        cadence = client.DecisionCadence(20, 0, resume_immediately=True)
        now, starts = 0, []
        for work_seconds in (.055, .055, .008, .008, .300, .008, .008):
            now += cadence.remaining(now)
            starts.append(now)
            now += work_seconds
            cadence.advance(now)
        # Slight overruns retain useful throughput; a large stall adds no extra idle tick.
        for actual, expected in zip(starts, (0, .055, .110, .160, .210, .510, .560)):
            self.assertAlmostEqual(actual, expected)
        # Returning to fast inference never replays the ticks missed during the stall.
        self.assertAlmostEqual(cadence.next_at, .610)


class HeldRecorder(client.AsyncVideoRecorder):
    """Hold the disk worker so queue admission can be checked deterministically."""
    def __init__(self, *args, **kwargs):
        self.release_writer = threading.Event()
        super().__init__(*args, **kwargs)

    def _write(self):
        self.release_writer.wait(5)
        super()._write()


class TimingTests(unittest.TestCase):
    """Verify scheduling/cancellation with a fake clock instead of timing-sensitive limits."""
    def test_sleep_uses_positive_bounded_slices_and_an_absolute_deadline(self):
        now = [10.0]
        sleeps = []

        def sleep(duration):
            sleeps.append(duration)
            now[0] += duration + .0003  # Deterministic scheduler overshoot.

        with patch.object(client.time, 'perf_counter', side_effect=lambda: now[0]), \
                patch.object(client.time, 'sleep', side_effect=sleep):
            self.assertTrue(client.sleep_until(10.033, threading.Event()))
        self.assertTrue(all(0 < duration <= .005 for duration in sleeps))
        self.assertAlmostEqual(now[0], 10.0333)
        self.assertLess(sleeps[-1], .005)

    def test_cancellation_stops_before_another_sleep_slice(self):
        cancelled = threading.Event()
        now = [5.0]

        def sleep(duration):
            now[0] += duration
            cancelled.set()

        with patch.object(client.time, 'perf_counter', side_effect=lambda: now[0]), \
                patch.object(client.time, 'sleep', side_effect=sleep) as sleeper:
            self.assertFalse(client.sleep_until(50, cancelled))
            sleeper.assert_called_once_with(.005)
            self.assertFalse(client.sleep_until(50, cancelled))
            sleeper.assert_called_once_with(.005)

    def test_expired_deadline_does_not_sleep_or_spin(self):
        with patch.object(client.time, 'perf_counter', return_value=5), \
                patch.object(client.time, 'sleep') as sleeper:
            self.assertTrue(client.sleep_until(4, threading.Event()))
            sleeper.assert_not_called()

    def test_capture_deadlines_preserve_rate_despite_work_and_sleep_overhead(self):
        now = [100.0]
        cadence = client.DecisionCadence(30, now[0])
        starts = []

        def sleep(duration):
            now[0] += duration + .0002

        with patch.object(client.time, 'perf_counter', side_effect=lambda: now[0]), \
                patch.object(client.time, 'sleep', side_effect=sleep):
            for _ in range(5):
                self.assertTrue(client.sleep_until(cadence.next_at, threading.Event()))
                starts.append(now[0])
                now[0] += .004  # Capture/transport work fits within the polling period.
                cadence.advance(now[0])
            self.assertAlmostEqual(cadence.next_at, 100 + 5/30)
            for index, start in enumerate(starts):
                self.assertAlmostEqual(start, 100 + index/30 + (.0002 if index else 0))
            # An overrun skips expired ticks instead of sending a catch-up burst.
            now[0] += .14
            cadence.advance(now[0])
            self.assertGreater(cadence.next_at, now[0])
            self.assertAlmostEqual(cadence.next_at, 100.3)


class ScriptedBridge:
    """Supply tiny synthetic RGB frames, then repeat the last; no Windows/game access."""
    def __init__(self, pixels, before_frame=None, action_responses=None):
        self.pixels = pixels
        self.before_frame = before_frame
        self.action_responses = action_responses or ['accepted']
        self.count = 0
        self.commands = []
        self.handle = FragmentedPipe(b'')
        self.hello = {'sessionId': 'synthetic', 'inputEnabled': True, 'allowedKeys': ['W']}

    def request(self, command, **kwargs):
        self.commands.append(command)
        if command == 'stop':
            return {'type': 'stopped', 'receipts': [{'requestId': 'synthetic-stop', 'appliedSteps': []}]}, b''
        if command != 'frame':
            index = min(self.commands.count('action') - 1, len(self.action_responses) - 1)
            return {'type': self.action_responses[index]}, b''
        self.count += 1
        if self.before_frame:
            self.before_frame(self.count)
        pixels = self.pixels[min(self.count - 1, len(self.pixels) - 1)]
        return dict(frame(self.count, width=2, height=2), type='frame', receipts=[],
                    serverNowMs=self.count * 50, sourceWidth=2, sourceHeight=2), pixels


class CapturingRecorder:
    """Retain admitted evidence and sidecar events without an encoder dependency."""
    error = None

    def __init__(self):
        self.frames = []
        self.events = []

    def put(self, metadata, pixels):
        self.frames.append((dict(metadata), pixels))
        return True

    def event(self, event):
        self.events.append(dict(event))
        return True

    def close(self):
        return {'complete': True, 'error': None, 'encodedFrames': len(self.frames)}


class FakePolicy:
    """Return one supported action without importing a tensor or image library."""
    metadata = {'synthetic': True}

    def __init__(self, during_predict=None):
        self.images = []
        self.during_predict = during_predict

    def predict(self, image, size):
        self.images.append(image)
        if self.during_predict:
            self.during_predict()
        return {'parseValid': True, 'steps': [{'keys': ['W'], 'mouseDx': 0, 'mouseDy': 0,
                                             'durationMs': 50}], 'fullActionMs': 1}


class CaptureQualityTests(unittest.TestCase):
    def run_episode(self, bridge, policy=None, recorder=None, latest_type=None, extra=()):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            output = Path(directory) / 'report.json'
            argv = ['stream_client.py', '--seconds', '.08', '--fps', '100', '--decision-hz', '100',
                    '--output', str(output), *extra]
            if policy:
                argv += ['--model', 'open-p2p', '--source', 'synthetic', '--checkpoint', 'synthetic']
                stack.enter_context(patch.dict(sys.modules, {
                    'model_adapters': SimpleNamespace(make_adapter=lambda *args, **kwargs: policy),
                    'PIL': SimpleNamespace(Image=SimpleNamespace(frombytes=lambda mode, shape, pixels: pixels))}))
            else:
                stack.enter_context(patch.dict(sys.modules, {'model_adapters': None, 'PIL': None}))
            if recorder:
                argv += ['--record-dir', str(Path(directory) / 'episode')]
                stack.enter_context(patch.object(client, 'AsyncVideoRecorder', return_value=recorder))
            if latest_type:
                stack.enter_context(patch.object(client, 'LatestFrame', latest_type))
            stack.enter_context(patch.object(client, 'Bridge', return_value=bridge))
            stack.enter_context(patch.object(sys, 'argv', argv))
            stack.enter_context(redirect_stdout(io.StringIO()))
            code = client.main()
            return code, json.loads(output.read_text())

    def test_unapplied_accepted_receipt_resets_policy_history(self):
        class FeedbackPolicy(FakePolicy):
            execution_feedback = True
            resets = 0

            def finish_action(self, accepted):
                pass

            def reset(self):
                self.resets += 1

        class ReceiptBridge(ScriptedBridge):
            def request(self, command, **kwargs):
                metadata, pixels = super().request(command, **kwargs)
                if command == 'frame' and self.count == 2:
                    metadata['receipts'] = [{'requestId': 'cancelled-before-apply',
                                            'modelId': 'open-p2p', 'appliedSteps': []}]
                return metadata, pixels

        policy = FeedbackPolicy()
        _, report = self.run_episode(ReceiptBridge([bytes(range(12))]), policy,
                                     extra=['--enable-input'])
        self.assertEqual(report['unappliedAcceptedActions'], 1)
        self.assertEqual(report['receiptHistoryResets'], 1)
        self.assertEqual(policy.resets, 1)

    def test_world_block_and_resume_during_inference_invalidates_old_proposal(self):
        predicting, replacement_published = threading.Event(), threading.Event()

        class WorldBridge(ScriptedBridge):
            def __init__(self):
                super().__init__([bytes(range(12))])
                self.hello.update(worldReadiness={'version': 1, 'requiredForInput': True}, supportsRelease=True)

            def request(self, command, **kwargs):
                if command == 'release':
                    self.commands.append(command)
                    return {'type': 'released', 'receipts': []}, b''
                if command == 'frame' and self.count == 1:
                    if not predicting.wait(2):
                        raise AssertionError('The first world frame did not reach inference')
                metadata, pixels = super().request(command, **kwargs)
                if command == 'frame':
                    gate = {'ready': True, 'reason': 'world_ready', 'epoch': 1 if self.count == 1 else 2}
                    metadata.update(worldReadiness=gate, frameWorldReadiness=gate, inputAvailable=True)
                return metadata, pixels

        class SignallingLatestFrame(client.LatestFrame):
            def publish(self, metadata, pixels):
                super().publish(metadata, pixels)
                if metadata['worldReadiness']['epoch'] == 2:
                    replacement_published.set()

        def predict():
            predicting.set()
            self.assertTrue(replacement_published.wait(2))

        bridge = WorldBridge()
        code, report = self.run_episode(bridge, policy=FakePolicy(predict), latest_type=SignallingLatestFrame,
                                       extra=['--enable-input', '--decision-hz', '5', '--require-world-ready'])
        self.assertEqual(code, 0)
        self.assertEqual(len(report['decisions']), 1)
        self.assertEqual(report['decisions'][0]['acceptance']['reason'], 'worldChangedDuringPrediction')
        self.assertNotIn('action', bridge.commands)

    def test_blocked_world_keeps_capture_running_without_model_or_input(self):
        class BlockedWorld(ScriptedBridge):
            def __init__(self):
                super().__init__([bytes(range(12))])
                self.hello.update(worldReadiness={'version': 1, 'requiredForInput': True}, supportsRelease=True)

            def request(self, command, **kwargs):
                if command == 'release':
                    self.commands.append(command)
                    return {'type': 'released', 'receipts': []}, b''
                metadata, pixels = super().request(command, **kwargs)
                if command == 'frame':
                    gate = {'ready': False, 'reason': 'world_overlay_detected', 'epoch': 1}
                    metadata.update(worldReadiness=gate, frameWorldReadiness=gate, inputAvailable=False)
                return metadata, pixels

        bridge, policy = BlockedWorld(), FakePolicy()
        code, report = self.run_episode(bridge, policy=policy, extra=['--enable-input', '--require-world-ready'])
        self.assertEqual(code, 0)
        self.assertGreater(report['framesReceived'], 1)
        self.assertEqual(policy.images, [])
        self.assertNotIn('action', bridge.commands)
        self.assertEqual(bridge.commands.count('release'), 1)
        self.assertEqual(report['controlTransitions'][0]['reason'], 'world_overlay_detected')

    def test_explicit_hold_horizon_preserves_raw_policy_and_single_mouse_event(self):
        bridge, policy = ScriptedBridge([bytes(range(12))]), FakePolicy()
        code, report = self.run_episode(bridge, policy=policy,
            extra=['--enable-input', '--action-hold-ms', '100', '--max-input-actions', '1'])
        self.assertEqual(code, 0)
        result = report['decisions'][0]
        self.assertEqual(result['rawPolicySteps'][0]['durationMs'], 50)
        self.assertEqual(result['steps'][0]['durationMs'], 100)
        self.assertEqual(len(result['steps']), 1)
        self.assertEqual(result['rawPolicySteps'][0]['keys'], result['steps'][0]['keys'])
        self.assertEqual(result['rawPolicySteps'][0]['mouseDx'], result['steps'][0]['mouseDx'])

    def test_only_wholly_black_or_white_buffers_are_rejected(self):
        self.assertEqual(client.rgb_frame_quality(bytes(12)), 'allBlack')
        self.assertEqual(client.rgb_frame_quality(bytes([255]) * 12), 'allWhite')
        for pixels in (bytes([1]) * 12, bytes([254]) * 12, bytes([128]) * 12,
                       bytes([255, 0, 0]) * 4, bytes([0, 255]) * 6, bytes(range(12))):
            self.assertEqual(client.rgb_frame_quality(pixels), 'usable')
        with self.assertRaises(ValueError):
            client.rgb_frame_quality(b'')

    def test_white_observer_fails_but_keeps_raw_evidence_and_quality_counts(self):
        white = bytes([255]) * 12
        recorder = CapturingRecorder()
        bridge = ScriptedBridge([white])
        code, report = self.run_episode(bridge, recorder=recorder)
        self.assertEqual(code, 1)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('No usable RGB frames', report['captureError'])
        self.assertEqual(report['error'], report['captureError'])
        self.assertGreater(report['framesReceived'], 0)
        self.assertEqual(report['captureQuality']['allWhiteFrames'], report['framesReceived'])
        self.assertEqual(report['captureQuality']['usableFrames'], 0)
        self.assertEqual(len(recorder.frames), report['framesReceived'])
        self.assertTrue(all(metadata['frameQuality'] == 'allWhite' and pixels == white
                            for metadata, pixels in recorder.frames))
        summary = next(event for event in recorder.events if event.get('type') == 'captureQualitySummary')
        self.assertEqual(summary['captureQuality'], report['captureQuality'])
        self.assertEqual(summary['captureError'], report['captureError'])
        self.assertEqual(report['decisions'], [])
        self.assertNotIn('action', bridge.commands)

    def test_blank_frames_never_reach_policy_and_recovery_resumes_inference(self):
        policy = FakePolicy()
        code, report = self.run_episode(ScriptedBridge([bytes([255]) * 12]), policy=policy)
        self.assertEqual(code, 1)
        self.assertEqual(policy.images, [])
        usable = bytes(range(12))
        policy = FakePolicy()
        code, report = self.run_episode(ScriptedBridge([bytes(12), bytes(12), usable]), policy=policy)
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'completed')
        self.assertNotIn('captureError', report)
        self.assertEqual(report['captureQuality']['allBlackFrames'], 2)
        self.assertGreater(report['captureQuality']['usableFrames'], 0)
        self.assertGreater(len(policy.images), 0)
        self.assertTrue(all(image == usable for image in policy.images))

    def test_prediction_finishing_after_latest_frame_turns_blank_is_not_submitted(self):
        predicting = threading.Event()
        blank_published = threading.Event()

        class SignallingLatestFrame(client.LatestFrame):
            def publish(self, metadata, pixels):
                super().publish(metadata, pixels)
                if metadata['frameQuality'] != 'usable':
                    blank_published.set()

        def before_frame(index):
            if index == 2 and not predicting.wait(2):
                raise AssertionError('Policy did not begin on the first usable frame')

        def during_predict():
            predicting.set()
            self.assertTrue(blank_published.wait(2), 'Blank frame was not published during inference')

        policy = FakePolicy(during_predict)
        bridge = ScriptedBridge([bytes(range(12)), bytes([255]) * 12], before_frame)
        code, report = self.run_episode(bridge, policy=policy, latest_type=SignallingLatestFrame,
                                        extra=['--enable-input', '--decision-hz', '5'])
        self.assertEqual(code, 0)
        self.assertEqual(len(policy.images), 1)
        self.assertNotIn('action', bridge.commands)
        self.assertEqual(report['captureQuality']['rejectedPredictions'], 1)
        self.assertEqual(report['decisions'][0]['latestFrameQuality'], 'allWhite')
        self.assertEqual(report['decisions'][0]['acceptance'],
                         {'type': 'notSubmitted', 'reason': 'latestFrameBlank'})

    def test_trial_subset_rejects_whole_proposals_and_is_recorded(self):
        class MenuPolicy(FakePolicy):
            def predict(self, image, size):
                result = super().predict(image, size)
                result['steps'][0]['keys'] = ['W', 'ESC']
                return result

        bridge = ScriptedBridge([bytes(range(12))])
        bridge.hello['allowedKeys'] = ['W', 'ESC']
        recorder = CapturingRecorder()
        code, report = self.run_episode(bridge, MenuPolicy(), recorder,
                                        extra=['--enable-input', '--input-keys', 'W'])
        self.assertEqual(code, 0)
        self.assertGreater(len(report['decisions']), 0)
        self.assertTrue(all(item['acceptance']['reason'] == 'trialKeyNotAllowed'
                            for item in report['decisions']))
        self.assertTrue(all(item['steps'][0]['keys'] == ['W', 'ESC'] for item in report['decisions']))
        self.assertNotIn('action', bridge.commands)
        self.assertEqual(report['configuredInputKeys'], ['W'])
        self.assertEqual(report['effectiveInputKeys'], ['W'])
        start = next(event for event in recorder.events if event.get('type') == 'episodeStart')
        self.assertEqual(start['configuredInputKeys'], ['W'])
        self.assertEqual(start['effectiveInputKeys'], ['W'])

    def test_invalid_trial_subset_closes_pipe_before_starting_capture(self):
        bridge = ScriptedBridge([bytes(range(12))])
        with self.assertRaisesRegex(ValueError, 'absent from the server allowlist'):
            self.run_episode(bridge, extra=['--input-keys', 'W,TAB'])
        self.assertEqual(bridge.commands, [])
        self.assertTrue(bridge.handle.closed)

    def test_action_cap_counts_only_acceptances_and_runs_final_stop_cleanup(self):
        bridge = ScriptedBridge([bytes(range(12))], action_responses=['rejected', 'accepted', 'accepted'])
        recorder = CapturingRecorder()
        code, report = self.run_episode(bridge, FakePolicy(), recorder,
                                        extra=['--enable-input', '--max-input-actions', '2'])
        self.assertEqual(code, 0)
        self.assertEqual(bridge.commands.count('action'), 3)
        self.assertEqual([item['acceptance']['type'] for item in report['decisions']],
                         ['rejected', 'accepted', 'accepted'])
        self.assertEqual(report['maxInputActions'], 2)
        self.assertEqual(report['acceptedInputActions'], 2)
        self.assertEqual(report['endReason'], 'maxInputActions')
        self.assertEqual(bridge.commands[-1], 'stop')
        self.assertTrue(bridge.handle.closed)
        self.assertEqual(report['receipts'][-1]['requestId'], 'synthetic-stop')
        start = next(event for event in recorder.events if event.get('type') == 'episodeStart')
        end = next(event for event in recorder.events if event.get('type') == 'episodeEnd')
        self.assertEqual(start['maxInputActions'], 2)
        self.assertEqual(end, {'type': 'episodeEnd', 'endReason': 'maxInputActions',
                               'maxInputActions': 2, 'acceptedInputActions': 2})

    def test_action_cap_requires_positive_count_and_explicit_input(self):
        for extra in (['--max-input-actions', '1'], ['--max-input-actions', '0', '--enable-input'],
                      ['--max-input-actions', '-2', '--enable-input']):
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()), \
                    patch.object(client, 'Bridge') as bridge, \
                    patch.object(sys, 'argv', ['stream_client.py', '--output', 'unused.json', *extra]):
                with self.assertRaises(SystemExit) as error:
                    client.main()
                self.assertEqual(error.exception.code, 2)
                bridge.assert_not_called()


class InstructionRoutingTests(unittest.TestCase):
    """A declared per-trial goal must reach the model rather than only its report."""

    def test_gamescaling_goal_reaches_the_loaded_adapter(self):
        goal = 'Turn left away from the wall and follow the open street.'
        args = client.parse_arguments(['--model', 'gamescaling', '--instruction', goal,
                                       '--source', 'unused', '--checkpoint', 'unused', '--output', 'unused.json'])
        with patch('model_adapters.make_adapter') as factory:
            self.assertIs(client.load_policy(args), factory.return_value)
        self.assertEqual(factory.call_args.kwargs['instruction'], goal)

    def test_wrong_model_and_empty_goals_are_rejected_before_loading(self):
        for argv in (['--instruction', 'Walk forward'],
                     ['--model', 'open-p2p', '--instruction', 'Walk forward'],
                     ['--model', 'gamescaling', '--instruction', '   ']):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                client.parse_arguments(argv + ['--source', 'unused', '--checkpoint', 'unused', '--output', 'unused.json'])


class RecorderTests(unittest.TestCase):
    def test_close_drains_final_events_arriving_after_the_last_event_drain(self):
        reached_frame_queue = threading.Event()
        release_frame_check = threading.Event()

        class PausedEmptyQueue(client.queue.Queue):
            def get_nowait(self):
                reached_frame_queue.set()
                if not release_frame_check.wait(2):
                    raise AssertionError('Final metadata was not supplied')
                return super().get_nowait()

        with tempfile.TemporaryDirectory() as root:
            recorder = HeldRecorder(Path(root) / 'episode', 'unused-ffmpeg', 20, 1024 * 1024)
            recorder.queue = PausedEmptyQueue(maxsize=8)
            recorder.release_writer.set()
            try:
                self.assertTrue(reached_frame_queue.wait(2))
                self.assertTrue(recorder.event({'type': 'finalReceipt'}))
                self.assertTrue(recorder.event({'type': 'episodeEnd'}))
                timer = threading.Timer(.02, release_frame_check.set)
                timer.start()
                result = recorder.close()
                timer.join()
            finally:
                release_frame_check.set()
                recorder.close()
            self.assertTrue(result['complete'])
            self.assertEqual(result['droppedEvents'], 0)
            events = [json.loads(line) for line in (recorder.directory / 'events.jsonl').read_text().splitlines()]
            self.assertEqual(events, [{'type': 'finalReceipt'}, {'type': 'episodeEnd'}])

    def test_overflow_is_bounded_and_enqueue_never_serializes_or_flushes(self):
        with tempfile.TemporaryDirectory() as root:
            recorder = HeldRecorder(Path(root) / 'episode', 'unused-ffmpeg', 20, 1024 * 1024,
                                    frame_capacity=1, event_capacity=2)
            try:
                with patch.object(client.json, 'dumps', side_effect=AssertionError('Producer serialized JSON')):
                    self.assertTrue(recorder.put(frame(1), b'\0' * (64 * 48 * 3)))
                    self.assertFalse(recorder.put(frame(2), b'\0' * (64 * 48 * 3)))
                    self.assertTrue(recorder.event({'type': 'execution', 'requestId': 'a'}))
                    self.assertFalse(recorder.event({'type': 'execution', 'requestId': 'b'}))
                self.assertEqual(recorder.queue.qsize(), 1)
                self.assertEqual(recorder.event_queue.qsize(), 2)
                self.assertEqual(list(recorder.directory.iterdir()), [])
                self.assertIn('labels are incomplete', recorder.error)
            finally:
                recorder.release_writer.set()
                result = recorder.close()
            self.assertFalse(result['complete'])
            self.assertEqual(result['droppedFrames'], 1)
            self.assertEqual(result['droppedEvents'], 1)
            self.assertEqual(result['abandonedFrames'], 1)
            events = [json.loads(line) for line in (recorder.directory / 'events.jsonl').read_text().splitlines()]
            self.assertEqual(events[0]['type'], 'recordingDrop')
            self.assertEqual(events[0]['frameId'], 2)
            self.assertEqual(events[1]['requestId'], 'a')

    def test_metadata_failure_is_visible_and_final_status_is_incomplete(self):
        with tempfile.TemporaryDirectory() as root:
            recorder = client.AsyncVideoRecorder(Path(root) / 'episode', 'unused-ffmpeg', 20, 1024 * 1024)
            self.assertTrue(recorder.event({'unserializable': object()}))
            result = recorder.close()
            self.assertIn('JSON serializable', result['error'])
            self.assertEqual(result['droppedEvents'], 1)
            self.assertFalse(result['complete'])
            saved = json.loads((recorder.directory / 'recording.json').read_text())
            self.assertEqual(saved['error'], result['error'])

    def test_missing_encoder_surfaces_error_and_abandoned_frame(self):
        with tempfile.TemporaryDirectory() as root:
            recorder = client.AsyncVideoRecorder(Path(root) / 'episode', str(Path(root) / 'missing.exe'), 20, 1024 * 1024)
            self.assertTrue(recorder.put(frame(1), b'\0' * (64 * 48 * 3)))
            result = recorder.close()
            self.assertIsNotNone(result['error'])
            self.assertFalse(result['complete'])
            self.assertEqual(result['encodedFrames'], 0)
            self.assertEqual(result['abandonedFrames'], 1)

    def test_close_does_not_wait_for_a_queue_sentinel(self):
        with tempfile.TemporaryDirectory() as root:
            recorder = HeldRecorder(Path(root) / 'episode', 'unused-ffmpeg', 20, 1024 * 1024, frame_capacity=1)
            recorder.put(frame(1), b'\0' * (64 * 48 * 3))
            # The deliberately stalled worker is released independently. close must set
            # the timeout error without needing an extra slot in the full frame queue.
            timer = threading.Timer(.1, recorder.release_writer.set)
            timer.start()
            result = recorder.close(timeout=.01)
            timer.join()
            self.assertTrue(result['closed'])
            self.assertIn('shutdown timed out', result['error'])

    def test_real_ffmpeg_clip_preserves_frame_indices_and_irregular_capture_times(self):
        ffmpeg = shutil.which('ffmpeg') or (str(Path('C:/programs/ffmpeg.exe')) if Path('C:/programs/ffmpeg.exe').exists() else None)
        ffprobe = shutil.which('ffprobe') or (str(Path('C:/programs/ffprobe.exe')) if Path('C:/programs/ffprobe.exe').exists() else None)
        if not ffmpeg or not ffprobe:
            self.skipTest('FFmpeg/ffprobe not available')
        with tempfile.TemporaryDirectory() as root:
            recorder = client.AsyncVideoRecorder(Path(root) / 'episode', ffmpeg, 20, 1024 * 1024, preview=True)
            times = [0, 50, 150, 200, 260, 310]
            for index, stamp in enumerate(times):
                self.assertTrue(recorder.put(frame(index, stamp), bytes([index * 30, 0, 200]) * (64 * 48)))
            receipt = {'type': 'executed', 'requestId': 'actual-input',
                       'appliedSteps': [{'index': 0, 'startedAtMs': 51.5, 'keys': ['W'], 'mouseDx': 0, 'mouseDy': 0}]}
            self.assertTrue(recorder.event(receipt))
            result = recorder.close()
            self.assertIsNone(result['error'])
            self.assertTrue(result['complete'])
            self.assertEqual(result['encodedFrames'], 6)
            self.assertIsNone(result['previewError'])
            self.assertIsNotNone(result['previewFrameId'])
            from PIL import Image
            with Image.open(recorder.directory / 'latest.jpg') as preview:
                self.assertEqual(preview.size, (64, 48))
                self.assertEqual(preview.format, 'JPEG')
            rows = [json.loads(line) for line in (recorder.directory / 'frames.jsonl').read_text().splitlines()]
            self.assertEqual([row['capturedAtMs'] for row in rows], times)
            self.assertEqual([row['videoFrameIndex'] for row in rows], list(range(6)))
            self.assertEqual([row['videoPtsSeconds'] for row in rows], [i / 20 for i in range(6)])
            self.assertEqual(json.loads((recorder.directory / 'events.jsonl').read_text()), receipt)
            probe = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-count_frames',
                                    '-show_entries', 'stream=nb_read_frames,width,height', '-of', 'json',
                                    str(recorder.directory / 'frames.mp4')], capture_output=True, check=True, timeout=15)
            video = json.loads(probe.stdout)['streams'][0]
            self.assertEqual(int(video['nb_read_frames']), 6)
            self.assertEqual((video['width'], video['height']), (64, 48))


class ProposalFreshnessTests(unittest.TestCase):
    """Fast model completion alone must not authorize an old or unsupported action."""

    def test_freshness_and_model_budget_are_independent(self):
        result = {'parseValid': True, 'steps': [{'keys': ['W']}]}
        check = lambda age, duration: client.proposal_rejection(result, {'W'}, True, age, 100, duration, 50)
        self.assertIsNone(check(99.9, 28))
        self.assertEqual(check(100, 28), 'observationTooOld')
        self.assertEqual(check(350, 28), 'observationTooOld')
        self.assertEqual(check(float('nan'), 28), 'observationTooOld')
        self.assertEqual(check(40, 50.1), 'modelMissedDecisionBudget')
        self.assertEqual(check(40, float('inf')), 'modelMissedDecisionBudget')

    def test_unsupported_actions_are_rejected_in_full(self):
        result = {'parseValid': True, 'steps': [{'keys': ['W', 'ALT']}]}
        self.assertEqual(client.proposal_rejection(result, {'W'}, True, 40, 100, 28, 50), 'unsupportedKey')
        self.assertEqual(result['steps'][0]['keys'], ['W', 'ALT'])
        self.assertEqual(client.proposal_rejection(result, {'W'}, False, 40, 100, 28, 50), 'observeMode')
        result = {'parseValid': True, 'steps': [{'keys': ['W']}], 'scrollUnsupported': True}
        self.assertEqual(client.proposal_rejection(result, {'W'}, True, 40, 100, 28, 50), 'unsupportedScroll')

    def test_trial_keys_are_an_explicit_validated_subset_with_default_server_keys(self):
        server = {'W', 'A', 'SPACE'}
        self.assertEqual(client.resolve_input_keys(None, server), (None, server))
        self.assertEqual(client.resolve_input_keys(' w, A ,W', server), (['W', 'A'], {'W', 'A'}))
        for value in ('', 'W,', 'W,,A', 'W,TAB'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                client.resolve_input_keys(value, server)

    def test_trial_filter_distinguishes_protocol_support_and_preserves_relative_mouse(self):
        result = {'parseValid': True, 'steps': [{'keys': ['W']}, {'keys': ['ESC']}]}
        original = json.loads(json.dumps(result))
        self.assertEqual(client.proposal_rejection(result, {'W', 'ESC'}, True, 40, 100, 28, 50,
                                                    trial_keys={'W'}), 'trialKeyNotAllowed')
        self.assertEqual(result, original)
        self.assertEqual(client.proposal_rejection(result, {'W'}, True, 40, 100, 28, 50,
                                                    trial_keys={'W'}), 'unsupportedKey')
        result['steps'] = [{'keys': [], 'mouseDx': 7, 'mouseDy': -3}]
        self.assertIsNone(client.proposal_rejection(result, {'W'}, True, 40, 100, 28, 50,
                                                    trial_keys={'W'}))
        self.assertEqual(result['steps'][0], {'keys': [], 'mouseDx': 7, 'mouseDy': -3})


if __name__ == '__main__':
    unittest.main()
