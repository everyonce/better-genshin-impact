"""Continuous BetterGI named-pipe client: latest frames, real policy, bounded recording.

Input stays disabled unless both BetterGI and this client explicitly enable it.
The video sidecar maps every encoded frame to the server monotonic clock;
video presentation time is an index, not an assumption about capture cadence.
"""
import argparse
import json
import math
import os
from pathlib import Path
import queue
import re
import struct
import subprocess
import sys
import threading
import time
import uuid


class Bridge:
    """Serialize request/response pairs on the same-user local named pipe."""
    def __init__(self, name):
        if not re.fullmatch(r'BetterGI\.Agent\.[A-Za-z0-9_.-]{1,100}', name):
            raise ValueError('Use a local pipe name beginning BetterGI.Agent.')
        if os.name != 'nt':
            raise RuntimeError('The BetterGI bridge requires Windows')
        self.handle = open('\\\\.\\pipe\\' + name, 'r+b', buffering=0)
        self.lock = threading.Lock()
        try:
            self.hello, payload = self._read()
            if (self.hello.get('version') != 1 or self.hello.get('type') != 'hello' or payload
                    or not self.hello.get('sessionId') or not self.hello.get('ownerEpoch')
                    or self.hello.get('goalVersion') != 1):
                raise ValueError('Unsupported BetterGI bridge handshake')
        except Exception:
            self.handle.close()
            raise

    def _exact(self, length):
        chunks = bytearray()
        while len(chunks) < length:
            chunk = self.handle.read(length-len(chunks))
            if not chunk:
                raise EOFError('BetterGI disconnected; input owner must release held input')
            chunks.extend(chunk)
        return bytes(chunks)

    def _read(self):
        length = struct.unpack('<I', self._exact(4))[0]
        if not 0 < length <= 4 * 1024 * 1024:
            raise ValueError('Invalid JSON packet length')
        message = json.loads(self._exact(length))
        if not isinstance(message, dict):
            raise ValueError('Expected a JSON packet object')
        size = message.get('payloadBytes', 0)
        if type(size) is not int or not 0 <= size <= 32 * 1024 * 1024:
            raise ValueError('Invalid image packet length')
        return message, self._exact(size) if size else b''

    def request(self, command, **kwargs):
        payload = dict(version=1, command=command, sessionId=self.hello['sessionId'],
                       ownerEpoch=self.hello['ownerEpoch'], goalVersion=self.hello['goalVersion'], **kwargs)
        encoded = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode('utf-8')
        if len(encoded) > 65536:
            raise ValueError('Request exceeds the server JSON limit')
        with self.lock:
            packet = memoryview(struct.pack('<I', len(encoded)) + encoded)
            while packet:
                written = self.handle.write(packet)
                if not written:
                    raise EOFError('BetterGI disconnected while sending a request')
                packet = packet[written:]
            return self._read()


def proposal_rejection(result, allowed_keys, enabled, age_ms, max_age_ms, policy_ms, budget_ms, trial_keys=None):
    """Require fresh observations and complete supported actions before submission."""
    if not enabled:
        return 'observeMode'
    if not math.isfinite(policy_ms) or policy_ms > budget_ms:
        return 'modelMissedDecisionBudget'
    if not math.isfinite(age_ms) or not 0 <= age_ms < max_age_ms:
        return 'observationTooOld'
    if not result.get('parseValid') or not result.get('steps'):
        return 'invalidAction'
    if result.get('scrollUnsupported'):
        return 'unsupportedScroll'
    if any(key not in allowed_keys for step in result['steps'] for key in step['keys']):
        return 'unsupportedKey'
    if trial_keys is not None and any(key not in trial_keys for step in result['steps'] for key in step['keys']):
        return 'trialKeyNotAllowed'
    return None


def resolve_input_keys(configured, server_keys):
    """Resolve an optional explicit key subset without altering any proposed action."""
    allowed = set(server_keys)
    if configured is None:
        return None, allowed
    keys = list(dict.fromkeys(key.strip().upper() for key in configured.split(',')))
    if not keys or any(not key for key in keys):
        raise ValueError('input-keys must contain comma-separated key names without empty entries')
    unsupported = sorted(set(keys) - allowed)
    if unsupported:
        raise ValueError('input-keys contains keys absent from the server allowlist: ' + ', '.join(unsupported))
    return keys, set(keys)


def rgb_frame_quality(pixels):
    """Reject only wholly black/white RGB buffers; this does not establish game visibility."""
    if not pixels:
        raise ValueError('An RGB frame cannot be empty')
    # At most one native bytes.count scan, with no image conversion or array allocation.
    if pixels[0] == 0 and pixels.count(0) == len(pixels):
        return 'allBlack'
    if pixels[0] == 255 and pixels.count(255) == len(pixels):
        return 'allWhite'
    return 'usable'


class LatestFrame:
    """One-slot mailbox: a slow policy always reads the newest available capture."""
    def __init__(self):
        self.lock = threading.Lock()
        self.item = None

    def publish(self, metadata, pixels):
        with self.lock:
            self.item = (metadata, pixels)

    def newer_than(self, frame_id):
        with self.lock:
            return self.item if self.item is not None and self.item[0]['frameId'] != frame_id else None


class DecisionCadence:
    """Advance a fixed-rate capture/policy clock past missed ticks without catch-up bursts."""
    def __init__(self, hz, now):
        self.period = 1 / hz
        self.next_at = now

    def remaining(self, now):
        return max(0, self.next_at - now)

    def advance(self, now):
        ticks = max(1, math.floor((now - self.next_at) / self.period + 1e-9) + 1)
        self.next_at += ticks * self.period


def sleep_until(deadline, cancelled):
    """Use Python's high-resolution sleep with at most 5 ms between cancellation checks."""
    # Event.wait rounds ~33 ms up to ~47 ms on this Windows/Python combination.
    # Keep an absolute deadline so sleep overhead cannot accumulate across ticks.
    while not cancelled.is_set():
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return True
        time.sleep(min(.005, remaining))
    return False


class AsyncVideoRecorder:
    """Bound both queues; only the worker serializes metadata or accesses recording files."""
    def __init__(self, directory, ffmpeg, fps, max_bytes, frame_capacity=8, event_capacity=256):
        if not math.isfinite(fps) or fps <= 0 or max_bytes <= 0 or min(frame_capacity, event_capacity) < 1:
            raise ValueError('Recording rate, budget, and queue capacities must be positive')
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.queue = queue.Queue(maxsize=frame_capacity)
        self.event_queue = queue.Queue(maxsize=event_capacity)
        self.ffmpeg, self.fps, self.max_bytes = ffmpeg, fps, max_bytes
        self.dropped = 0
        self.dropped_events = 0
        self.abandoned_frames = 0
        self.encoded = 0
        self.error = None
        self.closed = False
        self.state_lock = threading.RLock()
        self.closing = threading.Event()
        self.wake = threading.Event()
        self.process = None
        self.worker = threading.Thread(target=self._write, name='BetterGI-recorder', daemon=True)
        self.worker.start()

    def fail(self, reason):
        """Report loss or failure without doing IO on the calling capture thread."""
        with self.state_lock:
            if self.error is None:
                self.error = str(reason)
            self.closing.set()
            self.wake.set()

    def event(self, item):
        with self.state_lock:
            if self.closing.is_set():
                return False
            try:
                self.event_queue.put_nowait(dict(item))
            except queue.Full:
                # Losing actual execution labels makes the dataset incomplete. Stop
                # recording explicitly instead of silently treating proposals as labels.
                self.dropped_events += 1
                self.fail('Recording event queue overflow; execution labels are incomplete')
                return False
            self.wake.set()
            return True

    def put(self, metadata, pixels):
        with self.state_lock:
            if self.closing.is_set():
                return False
            try:
                # Immutable bytes are shared, not recopied or encoded on the capture path.
                frame_metadata = dict(metadata)
                # Receipts can concern earlier frames; they have their own event clock.
                frame_metadata.pop('receipts', None)
                self.queue.put_nowait((frame_metadata, pixels))
            except queue.Full:
                self.dropped += 1
                self.event({'type': 'recordingDrop', 'frameId': metadata['frameId'],
                            'capturedAtMs': metadata['capturedAtMs']})
                return False
            self.wake.set()
            return True

    def status(self):
        with self.state_lock:
            return {'encodedFrames': self.encoded, 'droppedFrames': self.dropped,
                    'droppedEvents': self.dropped_events, 'abandonedFrames': self.abandoned_frames,
                    'error': self.error, 'closed': self.closed,
                    'complete': self.closed and self.error is None}

    def _write(self):
        process = None
        index = 0
        shape = None
        in_flight = False
        video = self.directory / 'frames.mp4'
        try:
            with (open(self.directory / 'frames.jsonl', 'w', encoding='utf-8') as frames,
                  open(self.directory / 'events.jsonl', 'w', encoding='utf-8') as events,
                  open(self.directory / 'ffmpeg.log', 'wb') as diagnostic):
                while True:
                    self.wake.clear()
                    # Service receipt metadata even when no new frame arrives.
                    for _ in range(self.event_queue.maxsize):
                        try:
                            item = self.event_queue.get_nowait()
                        except queue.Empty:
                            break
                        try:
                            events.write(json.dumps(item, separators=(',', ':'), allow_nan=False) + '\n')
                        except Exception:
                            self.dropped_events += 1
                            raise
                    events.flush()
                    if self.error:
                        break
                    try:
                        metadata, pixels = self.queue.get_nowait()
                    except queue.Empty:
                        if self.closing.is_set():
                            # Final receipts/episode metadata may arrive after this
                            # iteration's event drain and immediately before close().
                            if self.event_queue.empty():
                                break
                            continue
                        self.wake.wait(.05)
                        continue
                    in_flight = True
                    width, height = metadata['width'], metadata['height']
                    if (type(width) is not int or type(height) is not int or min(width, height) <= 0
                            or width % 2 or height % 2 or len(pixels) != width * height * 3):
                        raise ValueError('Recording requires complete, even-sized RGB24 frames')
                    if shape is not None and shape != (width, height):
                        raise ValueError('Recording dimensions changed; start a new episode')
                    if process is None:
                        shape = (width, height)
                        command = [self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo',
                                   '-pixel_format', 'rgb24', '-video_size', f'{width}x{height}',
                                   '-framerate', str(self.fps), '-i', 'pipe:0', '-an', '-c:v', 'libx264',
                                   '-threads', '2', '-preset', 'ultrafast', '-crf', '20', '-pix_fmt', 'yuv420p',
                                   '-fs', str(self.max_bytes), str(video)]
                        process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                                   stdout=subprocess.DEVNULL, stderr=diagnostic,
                                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        with self.state_lock:
                            self.process = process
                    size = video.stat().st_size if video.exists() else 0
                    if size + frames.tell() + events.tell() >= self.max_bytes:
                        raise RuntimeError('Recording byte budget reached; inference continues without recording')
                    payload = memoryview(pixels)
                    while payload:
                        written = process.stdin.write(payload)
                        if not written:
                            raise BrokenPipeError('FFmpeg stopped accepting RGB frames')
                        payload = payload[written:]
                    # Buffered stdin must reach FFmpeg before recording the aligned index.
                    process.stdin.flush()
                    frames.write(json.dumps(dict(metadata, videoFrameIndex=index, videoPtsSeconds=index/self.fps),
                                            separators=(',', ':'), allow_nan=False) + '\n')
                    frames.flush()
                    index += 1
                    self.encoded = index
                    in_flight = False
        except Exception as exc:
            self.fail(exc)
        finally:
            if process:
                try:
                    process.stdin.close()
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.fail('FFmpeg did not finalize within 15 seconds')
                    process.kill()
                    process.wait()
                except Exception as exc:
                    self.fail(exc)
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                if process.returncode:
                    self.fail(f'FFmpeg exited {process.returncode}; see ffmpeg.log')
            self.closing.set()
            if in_flight:
                self.abandoned_frames += 1
            # Release queued image references if an encoder/metadata failure stopped us.
            while True:
                try:
                    self.queue.get_nowait()
                    self.abandoned_frames += 1
                except queue.Empty:
                    break
            while True:
                try:
                    self.event_queue.get_nowait()
                    self.dropped_events += 1
                except queue.Empty:
                    break
            try:
                total_bytes = sum(path.stat().st_size for path in self.directory.iterdir() if path.is_file())
                if total_bytes >= self.max_bytes:
                    self.fail('Recording byte budget reached during finalization')
            except OSError as exc:
                self.fail(exc)
            with self.state_lock:
                self.closed = True
            summary = self.status()
            summary['alignment'] = ('Use frames.jsonl capturedAtMs and receipts appliedSteps[].startedAtMs. '
                                    'videoPtsSeconds indexes encoded frames, not wall time; exclude capture gaps.')
            summary['budgetNote'] = 'Video plus sidecars checked between frames; FFmpeg muxer buffers/footer can overshoot.'
            try:
                (self.directory / 'recording.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
            except Exception as exc:
                self.fail(f'Cannot save recording summary: {exc}')

    def close(self, timeout=20):
        """Bound shutdown independently of a full queue or a stalled encoder."""
        with self.state_lock:
            self.closing.set()
            self.wake.set()
        self.worker.join(timeout=timeout)
        if self.worker.is_alive():
            self.fail('Recording shutdown timed out; output may be incomplete')
            with self.state_lock:
                process = self.process
            if process is not None and process.poll() is None:
                process.kill()
            self.worker.join(timeout=2)
        return self.status()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pipe', default='BetterGI.Agent.local')
    parser.add_argument('--model', choices=['observe', 'gamescaling', 'open-p2p'], default='observe')
    parser.add_argument('--checkpoint')
    parser.add_argument('--source')
    parser.add_argument('--cache-root', default='artifacts/agent/compatibility')
    parser.add_argument('--history', type=int)
    parser.add_argument('--image-width', type=int, default=384)
    parser.add_argument('--max-new-tokens', type=int, default=64)
    parser.add_argument('--fps', type=float, default=30)
    parser.add_argument('--decision-hz', '--policy-fps', dest='decision_hz', type=float,
                        help='Policy cadence; defaults to 20 for Open P2P and 5 otherwise')
    parser.add_argument('--cuda-graph', action='store_true', help='Opt in to the selected policy\'s validated CUDA graph path')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--max-observation-age-ms', type=float,
                        help='Freshness limit, defaults to 100ms for Open P2P and 200ms otherwise')
    parser.add_argument('--enable-input', action='store_true')
    parser.add_argument('--input-keys', help='Optional comma-separated subset of server keys; reject whole proposals outside it')
    parser.add_argument('--max-input-actions', type=int,
                        help='Stop after this many server-accepted proposals; requires --enable-input')
    parser.add_argument('--record-dir')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--record-max-mib', type=int, default=1024)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    args.decision_hz = args.decision_hz if args.decision_hz is not None else (20 if args.model == 'open-p2p' else 5)
    args.max_observation_age_ms = args.max_observation_age_ms if args.max_observation_age_ms is not None else (100 if args.model == 'open-p2p' else 200)
    if any(not math.isfinite(value) or value <= 0 for value in (args.fps, args.seconds, args.decision_hz)) or args.record_max_mib <= 0:
        parser.error('fps, seconds, decision-hz, and record-max-mib must be finite and positive')
    if not math.isfinite(args.max_observation_age_ms) or not 0 < args.max_observation_age_ms <= 500:
        parser.error('max-observation-age-ms must be positive and at most the server ceiling of 500ms')
    if args.max_input_actions is not None and (args.max_input_actions <= 0 or not args.enable_input):
        parser.error('max-input-actions must be positive and requires --enable-input')
    policy = None
    if args.model != 'observe':
        if not args.source or not args.checkpoint:
            parser.error('A real model source and checkpoint are required')
        from model_adapters import make_adapter
        policy = make_adapter(args.model, source=args.source, checkpoint=args.checkpoint,
                              cache_root=args.cache_root, history=args.history if args.history is not None else (0 if args.model == 'gamescaling' else 200),
                              image_width=args.image_width, max_new_tokens=args.max_new_tokens, cuda_graph=args.cuda_graph)
    if policy is not None:
        from PIL import Image
    bridge = Bridge(args.pipe)
    report = {'mode': 'live-bound-game-stream', 'hello': bridge.hello,
              'inputRequested': args.enable_input, 'model': args.model, 'decisions': [], 'framesReceived': 0,
              'maxInputActions': args.max_input_actions, 'acceptedInputActions': 0,
              'captureQuality': {'check': 'wholeBufferBlackOrWhite', 'usableFrames': 0,
                                 'allBlackFrames': 0, 'allWhiteFrames': 0, 'rejectedPredictions': 0}}
    if args.enable_input and not bridge.hello.get('inputEnabled'):
        bridge.handle.close()
        raise RuntimeError('BetterGI started in observation-only mode; enable input explicitly on both sides')
    try:
        server_keys = set(bridge.hello.get('allowedKeys', []))
        configured_keys, effective_keys = resolve_input_keys(args.input_keys, server_keys)
        report['configuredInputKeys'] = configured_keys
        report['effectiveInputKeys'] = sorted(effective_keys)
        recorder = AsyncVideoRecorder(args.record_dir, args.ffmpeg, args.fps, args.record_max_mib*2**20) if args.record_dir else None
    except Exception:
        bridge.handle.close()
        raise
    stopped = threading.Event()
    latest = LatestFrame()
    receipts = []
    report['decisionHz'] = args.decision_hz
    report['capturePollHz'] = args.fps
    report['maxObservationAgeMs'] = args.max_observation_age_ms
    report['policyMetadata'] = policy.metadata if policy else None
    report['serverDroppedReceipts'] = 0
    if recorder:
        recorder.event({'type': 'episodeStart', 'sessionId': bridge.hello['sessionId'],
                        'clock': bridge.hello.get('clock'), 'clockFrequency': bridge.hello.get('clockFrequency'),
                        'captureTimestampKind': bridge.hello.get('captureTimestampKind'),
                        'model': args.model, 'inputRequested': args.enable_input,
                        'configuredInputKeys': configured_keys, 'effectiveInputKeys': sorted(effective_keys),
                        'maxInputActions': args.max_input_actions,
                        'capturePollHz': args.fps, 'decisionHz': args.decision_hz,
                        'frameQualityCheck': report['captureQuality']['check'],
                        'maxObservationAgeMs': args.max_observation_age_ms,
                        'policyMetadata': report['policyMetadata']})

    def collect_receipts(metadata):
        # No JSON serialization, flushing, or filesystem access occurs here.
        for receipt in metadata.get('receipts', []):
            receipts.append(receipt)
            if recorder:
                recorder.event(receipt)
        dropped = metadata.get('droppedReceipts', 0)
        if dropped > report['serverDroppedReceipts']:
            report['serverDroppedReceipts'] = dropped
            if recorder:
                recorder.fail('Server dropped execution receipts; this episode has incomplete labels')

    def receive():
        previous = None
        capture_cadence = DecisionCadence(args.fps, time.perf_counter())
        try:
            while not stopped.is_set():
                if not sleep_until(capture_cadence.next_at, stopped):
                    break
                start = time.perf_counter_ns()
                metadata, pixels = bridge.request('frame')
                arrived = time.perf_counter_ns()
                collect_receipts(metadata)
                if metadata.get('type') == 'frame' and metadata['frameId'] != previous:
                    if len(pixels) != metadata['width'] * metadata['height'] * 3:
                        raise ValueError('RGB payload does not match declared dimensions')
                    metadata['clientReceivedNs'] = arrived
                    metadata['transportRoundTripMs'] = (arrived-start)/1e6
                    metadata['frameQuality'] = rgb_frame_quality(pixels)
                    report['captureQuality'][metadata['frameQuality'] + 'Frames'] += 1
                    report['framesReceived'] += 1
                    latest.publish(metadata, pixels)
                    if recorder:
                        recorder.put(metadata, pixels)
                    previous = metadata['frameId']
                capture_cadence.advance(time.perf_counter())
        except Exception as exc:
            report['streamError'] = str(exc)
            stopped.set()

    producer = threading.Thread(target=receive, daemon=True)
    producer.start()
    deadline = time.perf_counter() + args.seconds
    cadence = DecisionCadence(args.decision_hz, time.perf_counter())
    previous = None
    recording_error_reported = False
    try:
        while time.perf_counter() < deadline and not stopped.is_set():
            if recorder and recorder.error and not recording_error_reported:
                print(json.dumps({'recordingError': recorder.error, 'inferenceContinues': True}), file=sys.stderr, flush=True)
                recording_error_reported = True
            if not sleep_until(min(cadence.next_at, deadline), stopped) or time.perf_counter() >= deadline:
                break
            item = latest.newer_than(previous)
            if item is None:
                cadence.advance(time.perf_counter())
                continue
            frame, pixels = item
            previous = frame['frameId']
            # Preserve blank captures as evidence but never feed them into policy history.
            # A later usable frame resumes inference normally after a loading fade.
            if frame['frameQuality'] != 'usable' or not policy:
                cadence.advance(time.perf_counter())
                continue
            image = Image.frombytes('RGB', (frame['width'], frame['height']), pixels)
            predict_started = time.perf_counter_ns()
            result = policy.predict(image, (frame['sourceWidth'], frame['sourceHeight']))
            now = time.perf_counter_ns()
            policy_ms = (now-predict_started)/1e6
            # Add the full round trip as a conservative bound for server-to-client transfer.
            age = max(0, frame['serverNowMs']-frame['capturedAtMs']) + (now-frame['clientReceivedNs'])/1e6 + frame['transportRoundTripMs']
            cadence_met = policy_ms <= cadence.period * 1000
            result.update(frameId=frame['frameId'], estimatedObservationAgeMs=age,
                          policyWallMs=policy_ms, controlCadenceMet=cadence_met)
            rejection = proposal_rejection(result, server_keys, args.enable_input, age,
                                           args.max_observation_age_ms, policy_ms, cadence.period * 1000,
                                           trial_keys=effective_keys)
            # Capture can turn blank while predict() is running. Its older proposal
            # must not reach the controller even when compute and age budgets passed.
            newest = latest.newer_than(None)
            result['latestFrameQuality'] = newest[0]['frameQuality'] if newest else None
            if newest and newest[0]['frameQuality'] != 'usable':
                rejection = 'latestFrameBlank'
                report['captureQuality']['rejectedPredictions'] += 1
            # Do not silently strip keys or execute a different action than evaluated.
            if rejection is None:
                result['acceptance'] = bridge.request('action', requestId=uuid.uuid4().hex,
                    frameId=frame['frameId'], observedAtMs=frame['capturedAtMs'],
                    expiresAtMs=frame['capturedAtMs']+700, modelId=args.model,
                    steps=result['steps'])[0]
            else:
                result['acceptance'] = {'type': 'notSubmitted', 'reason': rejection}
            if result['acceptance'].get('type') == 'accepted':
                report['acceptedInputActions'] += 1
            report['decisions'].append(result)
            if recorder:
                recorder.event({'type': 'proposal', 'frameId': frame['frameId'],
                                'observedAtMs': frame['capturedAtMs'], 'model': args.model,
                                'steps': result['steps'], 'acceptance': result['acceptance'],
                                'latestFrameQuality': result['latestFrameQuality'],
                                'policyWallMs': policy_ms, 'estimatedObservationAgeMs': age})
            print(json.dumps({'frameId': previous, 'modelMs': result['fullActionMs'], 'ageMs': age,
                              'acceptance': result['acceptance']}), flush=True)
            if args.max_input_actions is not None and report['acceptedInputActions'] >= args.max_input_actions:
                report['endReason'] = 'maxInputActions'
                break  # Normal stop/receipt cleanup releases the input owner immediately.
            cadence.advance(time.perf_counter())
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        stopped.set()
        producer.join(timeout=3)
        if not producer.is_alive():
            try:
                report['stop'] = bridge.request('stop')[0]
                collect_receipts(report['stop'])
            except Exception as exc:
                report['stopError'] = str(exc)
        bridge.handle.close()
        producer.join(timeout=1)
        if producer.is_alive():
            report['streamError'] = 'Frame reader did not stop after disconnection'
        if report['captureQuality']['usableFrames'] == 0:
            report['captureError'] = 'No usable RGB frames were received; wholly black/white captures cannot evaluate a live policy.'
            report.setdefault('error', report['captureError'])
        report.setdefault('endReason', 'noUsableFrames' if report.get('captureError') else
                          'streamError' if report.get('streamError') else 'error' if report.get('error') else
                          'durationElapsed' if time.perf_counter() >= deadline else 'stopped')
        if recorder:
            recorder.event({'type': 'captureQualitySummary', 'captureQuality': dict(report['captureQuality']),
                            'captureError': report.get('captureError')})
            recorder.event({'type': 'episodeEnd', 'endReason': report['endReason'],
                            'maxInputActions': args.max_input_actions,
                            'acceptedInputActions': report['acceptedInputActions']})
            report['recording'] = recorder.close()
        report['receipts'] = receipts
        report['status'] = 'failed' if (report.get('error') or report.get('streamError') or
                                        report.get('recording', {}).get('error')) else 'completed'
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 1 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
