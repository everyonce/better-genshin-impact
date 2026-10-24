"""Continuous BetterGI named-pipe client: latest frames, real policy, bounded recording.

Input stays disabled unless both BetterGI and this client explicitly enable it.
The video sidecar maps every encoded frame to the server monotonic clock;
video presentation time is an index, not an assumption about capture cadence.
"""
import argparse
import copy
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

from observation_timing import frame_timing, observation_timestamp
from navigation_idle_recovery import (GOAL_INTENTS, NavigationIdleRecovery, RecoverySuperseded,
                                      capture_context, eligible_frame, fresh_frame)
from observation_profiles import LEGACY, P2P_NATIVE, PROFILES, validate_model_profile, verify_hello, verify_frame


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


def proposal_rejection(result, allowed_keys, enabled, age_ms, max_age_ms, policy_ms, budget_ms, trial_keys=None,
                       enforce_compute_budget=True):
    """Require fresh observations and complete supported actions before submission."""
    if not enabled:
        return 'observeMode'
    if not math.isfinite(policy_ms) or (enforce_compute_budget and policy_ms > budget_ms):
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

    def clear(self):
        """Discard local pre-reset pixels; the source-time barrier also rejects racing old arrivals."""
        with self.lock:
            self.item = None


class DecisionCadence:
    """Bound the rate without queuing work; optionally resume immediately after an overrun."""
    def __init__(self, hz, now, resume_immediately=False):
        self.period = 1 / hz
        self.next_at = now
        self.resume_immediately = resume_immediately

    def remaining(self, now):
        return max(0, self.next_at - now)

    def advance(self, now):
        if self.resume_immediately:
            # A 55 ms prediction at a 50 ms target must not wait another 45 ms.
            # Rebase after slow work, then enforce the full period again; no backlog is replayed.
            self.next_at = max(self.next_at + self.period, now)
            return
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
    """Bound image, observation and event queues; only the worker performs recording IO."""
    def __init__(self, directory, ffmpeg, fps, max_bytes, frame_capacity=8, event_capacity=256, preview=False,
                 metadata_capacity=256):
        if not math.isfinite(fps) or fps <= 0 or max_bytes <= 0 or min(frame_capacity, event_capacity, metadata_capacity) < 1:
            raise ValueError('Recording rate, budget, and queue capacities must be positive')
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.queue = queue.Queue(maxsize=frame_capacity)
        self.event_queue = queue.Queue(maxsize=event_capacity)
        self.metadata_queue = queue.Queue(maxsize=metadata_capacity)
        self.ffmpeg, self.fps, self.max_bytes = ffmpeg, fps, max_bytes
        self.dropped = 0
        self.dropped_events = 0
        self.recorded_observations = 0
        self.dropped_observations = 0
        self.abandoned_frames = 0
        self.encoded = 0
        self.preview = preview
        self.preview_next_at = 0
        self.preview_frame_id = None
        self.preview_error = None
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
            # Headers retain source clocks/readiness even when image admission fails.
            # They contain no pixels or receipts, and never claim a video index.
            frame_metadata = dict(metadata)
            for key in ('receipts', 'videoFrameIndex', 'videoPtsSeconds', 'videoQueueAccepted'):
                frame_metadata.pop(key, None)
            video_accepted = True
            try:
                # Immutable bytes are shared, not recopied or encoded on the capture path.
                self.queue.put_nowait((frame_metadata, pixels))
            except queue.Full:
                video_accepted = False
                self.dropped += 1
            try:
                self.metadata_queue.put_nowait(dict(frame_metadata, videoQueueAccepted=video_accepted))
            except queue.Full:
                self.dropped_observations += 1
                self.fail('Recording observation queue overflow; source timing metadata is incomplete')
                return False
            if not video_accepted:
                self.event({'type': 'recordingDrop', 'frameId': metadata['frameId'],
                            'capturedAtMs': metadata['capturedAtMs']})
            self.wake.set()
            return video_accepted

    def status(self):
        with self.state_lock:
            return {'encodedFrames': self.encoded, 'droppedFrames': self.dropped,
                    'droppedEvents': self.dropped_events, 'abandonedFrames': self.abandoned_frames,
                    'recordedObservations': self.recorded_observations,
                    'droppedObservations': self.dropped_observations,
                    'error': self.error, 'closed': self.closed,
                    'previewFrameId': self.preview_frame_id, 'previewError': self.preview_error,
                    'complete': self.closed and self.error is None}

    def _save_preview(self, metadata, pixels):
        """Publish a small supervision image on the recorder worker, never the control path."""
        if not self.preview or time.monotonic() < self.preview_next_at:
            return
        self.preview_next_at = time.monotonic() + 1
        temporary = self.directory / '.latest-preview.tmp'
        try:
            from PIL import Image
            with Image.frombytes('RGB', (metadata['width'], metadata['height']), pixels) as picture:
                picture.save(temporary, format='JPEG', quality=85)
            temporary.replace(self.directory / 'latest.jpg')
            self.preview_frame_id = metadata['frameId']
            self.preview_error = None
        except Exception as error:
            # A viewer can briefly hold the destination on Windows. Keep recording
            # and retry next second; a preview never authorizes controller input.
            self.preview_error = str(error)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _write(self):
        process = None
        index = 0
        shape = None
        in_flight = False
        video = self.directory / 'frames.mp4'
        try:
            with (open(self.directory / 'frames.jsonl', 'w', encoding='utf-8') as frames,
                  open(self.directory / 'observations.jsonl', 'w', encoding='utf-8') as observations,
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
                    # Video backpressure may discard images, but each received
                    # header has its own bounded queue and durable source clock.
                    for _ in range(self.metadata_queue.maxsize):
                        try:
                            item = self.metadata_queue.get_nowait()
                        except queue.Empty:
                            break
                        try:
                            observations.write(json.dumps(item, separators=(',', ':'), allow_nan=False) + '\n')
                            self.recorded_observations += 1
                        except Exception:
                            self.dropped_observations += 1
                            raise
                    observations.flush()
                    if self.error:
                        break
                    size = video.stat().st_size if video.exists() else 0
                    if size + frames.tell() + observations.tell() + events.tell() >= self.max_bytes:
                        raise RuntimeError('Recording byte budget reached; inference continues without recording')
                    try:
                        metadata, pixels = self.queue.get_nowait()
                    except queue.Empty:
                        if self.closing.is_set():
                            # Final receipts/episode metadata may arrive after this
                            # iteration's event drain and immediately before close().
                            if self.event_queue.empty() and self.metadata_queue.empty():
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
                    self._save_preview(metadata, pixels)
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
            while True:
                try:
                    self.metadata_queue.get_nowait()
                    self.dropped_observations += 1
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
            summary['observationSchemaVersion'] = 1
            summary['alignment'] = ('Use observations.jsonl for received frame timing, including dropped video images; '
                                    'join frameId to frames.jsonl for an actual videoFrameIndex. '
                                    'videoQueueAccepted is queue admission, not encoding success. '
                                    'Use sourceFrame.capturedAtMs for reported compositor time, '
                                    'sourceFrame.freshnessAtMs for the declared freshness anchor, '
                                    'capturedAtMs for host request time, and receipts appliedSteps[].startedAtMs. '
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


def parse_arguments(argv=None):
    """Validate the shared one-shot/resident options before loading any GPU weights."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pipe', default='BetterGI.Agent.local')
    parser.add_argument('--model', choices=['observe', 'gamescaling', 'open-p2p'], default='observe')
    parser.add_argument('--observation-profile', choices=PROFILES, default=LEGACY,
                        help='Explicit stream preprocessing; native Hamming192 is opt-in for P2P/observe')
    parser.add_argument('--checkpoint')
    parser.add_argument('--source')
    parser.add_argument('--goal-embedding', help='Validated local P2P instruction JSON from encode_goal.py')
    parser.add_argument('--goal-intent', choices=GOAL_INTENTS, default='unspecified',
                        help='Intent of this initial goal; unspecified/stationary are exempt from idle recovery')
    parser.add_argument('--instruction', help='Per-trial text goal for GameScaling; P2P uses goal-embedding')
    parser.add_argument('--cache-root', default='artifacts/agent/compatibility')
    parser.add_argument('--history', type=int)
    parser.add_argument('--image-width', type=int, default=384)
    parser.add_argument('--max-new-tokens', type=int, default=64)
    parser.add_argument('--sampling', choices=['greedy', 'sample'], default='greedy',
                        help='GameScaling token selection; greedy remains the default')
    parser.add_argument('--temperature', type=float, default=1.0)
    parser.add_argument('--top-k', type=int, default=0, help='GameScaling sampling top-k; 0 disables filtering')
    parser.add_argument('--top-p', type=float, default=1.0, help='GameScaling sampling top-p; 1 disables filtering')
    parser.add_argument('--fps', type=float, default=30)
    parser.add_argument('--decision-hz', '--policy-fps', dest='decision_hz', type=float,
                        help='Policy cadence; defaults to 20 for Open P2P and 5 otherwise')
    parser.add_argument('--cuda-graph', action='store_true', help='Opt in to the selected policy\'s validated CUDA graph path')
    parser.add_argument('--gamescaling-prefix-cache', action='store_true',
                        help='Opt in to validated text-prefix reuse; requires GameScaling, history 0, and cuda-graph')
    parser.add_argument('--p2p-fast-start', action='store_true',
                        help='Use masked empty fixed-capacity P2P history; requires --cuda-graph')
    parser.add_argument('--p2p-mouse-sampling', choices=['mean', 'conservative', 'truncated_normal'],
                        help='Override the P2P checkpoint mouse decoder; mean reproduces older comparisons')
    parser.add_argument('--p2p-execution-feedback', action='store_true',
                        help='Roll back rejected P2P predictions instead of storing unexecuted actions in history')
    parser.add_argument('--soft-cadence', action='store_true',
                        help='Accept late but still fresh actions; never queue missed policy ticks')
    parser.add_argument('--fresh-frame-at-decision', action=argparse.BooleanOptionalAction, default=None,
                        help='Refresh the latest frame immediately before inference; enabled by default in resident mode')
    parser.add_argument('--action-hold-ms', type=int,
                        help='Explicit P2P controller key-hold horizon, 33–100ms; raw 50ms policy steps remain in evidence')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--max-observation-age-ms', type=float,
                        help='Freshness limit, defaults to 100ms for Open P2P and 200ms otherwise')
    parser.add_argument('--enable-input', action='store_true')
    parser.add_argument('--input-keys', help='Optional comma-separated subset of server keys; reject whole proposals outside it')
    parser.add_argument('--max-input-actions', type=int,
                        help='Stop after this many server-accepted proposals; requires --enable-input')
    parser.add_argument('--record-dir')
    parser.add_argument('--preview', action='store_true',
                        help='Save latest.jpg once per second on the recording worker; requires record-dir')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--record-max-mib', type=int, default=1024)
    parser.add_argument('--resident', action='store_true',
                        help='Keep the model loaded across pauses, bridge reconnects, and child replacement')
    parser.add_argument('--rdp-session-id', type=int,
                        help='Required resident target; must equal this process actual RDP Windows session')
    parser.add_argument('--control-file', help='Resident pause/run/stop JSON command file; must not already exist')
    parser.add_argument('--segment-seconds', type=float, default=300,
                        help='Bound each resident report/video segment while retaining loaded model weights')
    parser.add_argument('--reconnect-timeout', type=float, default=90,
                        help='Maximum continuous time waiting for a usable RDP bridge')
    parser.add_argument('--require-world-ready', action='store_true',
                        help='Require the server game-world recognition capability; always enabled in resident mode')
    parser.add_argument('--navigation-progress', action='store_true',
                        help='Record minimap stall evidence against actual applied movement receipts')
    parser.add_argument('--navigation-idle-reset-seconds', type=float,
                        help='Opt-in one-shot history reset after accepted navigation no-ops; disabled by default, trial value 8')
    parser.add_argument('--readiness-snapshots', action='store_true',
                        help='Opt into bounded native screenshots on visual readiness changes in the RDP BetterGI app')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        validate_model_profile(args.observation_profile, args.model)
    except ValueError as error:
        parser.error(str(error))
    if args.goal_embedding and args.model != 'open-p2p':
        parser.error('goal-embedding requires the Open P2P model')
    args.decision_hz = args.decision_hz if args.decision_hz is not None else (20 if args.model == 'open-p2p' else 5)
    args.max_observation_age_ms = args.max_observation_age_ms if args.max_observation_age_ms is not None else (100 if args.model == 'open-p2p' else 200)
    if any(not math.isfinite(value) or value <= 0 for value in (args.fps, args.seconds, args.decision_hz)) or args.record_max_mib <= 0:
        parser.error('fps, seconds, decision-hz, and record-max-mib must be finite and positive')
    if not math.isfinite(args.max_observation_age_ms) or not 0 < args.max_observation_age_ms <= 500:
        parser.error('max-observation-age-ms must be positive and at most the server ceiling of 500ms')
    if args.max_input_actions is not None and (args.max_input_actions <= 0 or not args.enable_input):
        parser.error('max-input-actions must be positive and requires --enable-input')
    if args.preview and not args.record_dir:
        parser.error('preview requires record-dir')
    if args.instruction is not None and (args.model != 'gamescaling' or not args.instruction.strip() or len(args.instruction) > 2000):
        parser.error('instruction requires gamescaling and 1–2000 characters')
    if (not math.isfinite(args.temperature) or args.temperature <= 0 or args.top_k < 0
            or not math.isfinite(args.top_p) or not 0 < args.top_p <= 1):
        parser.error('sampling requires positive finite temperature, nonnegative top-k, and top-p in (0,1]')
    if args.sampling == 'greedy' and (args.temperature, args.top_k, args.top_p) != (1.0, 0, 1.0):
        parser.error('temperature/top-k/top-p overrides require sampling sample')
    if args.sampling == 'sample' and args.model != 'gamescaling':
        parser.error('sampling sample requires gamescaling')
    if args.gamescaling_prefix_cache and (args.model != 'gamescaling' or not args.cuda_graph or args.history not in (None, 0)):
        parser.error('gamescaling-prefix-cache requires gamescaling, history 0, and cuda-graph')
    if args.p2p_fast_start and (args.model != 'open-p2p' or not args.cuda_graph):
        parser.error('p2p-fast-start requires the open-p2p model and cuda-graph')
    if args.p2p_mouse_sampling is not None and args.model != 'open-p2p':
        parser.error('p2p-mouse-sampling requires open-p2p')
    if args.action_hold_ms is not None and (args.model != 'open-p2p' or not 33 <= args.action_hold_ms <= 100):
        parser.error('action-hold-ms requires open-p2p and must be between 33 and 100')
    if args.resident:
        if args.rdp_session_id is None or args.rdp_session_id <= 0:
            parser.error('resident requires a positive rdp-session-id')
        if any(not math.isfinite(value) or value <= 0 for value in (args.segment_seconds, args.reconnect_timeout)):
            parser.error('segment-seconds and reconnect-timeout must be finite and positive')
        if args.model == 'open-p2p' and not args.p2p_fast_start:
            parser.error('resident Open P2P requires p2p-fast-start to resume without history warmup')
        args.require_world_ready = True
        args.soft_cadence = True
        args.navigation_progress = True
        if args.model == 'open-p2p' and args.enable_input:
            args.p2p_execution_feedback = True
    if args.p2p_execution_feedback and (not args.p2p_fast_start or not args.enable_input):
        parser.error('p2p-execution-feedback requires p2p-fast-start and enable-input')
    if args.navigation_idle_reset_seconds is not None:
        if (not math.isfinite(args.navigation_idle_reset_seconds)
                or not 1 <= args.navigation_idle_reset_seconds <= 120):
            parser.error('navigation-idle-reset-seconds must be finite and between 1 and 120')
        if args.model != 'open-p2p' or not args.p2p_execution_feedback:
            parser.error('navigation-idle-reset-seconds requires Open P2P with input, fast-start, and execution feedback')
        args.require_world_ready = True
    if args.fresh_frame_at_decision is None:
        args.fresh_frame_at_decision = args.resident
    if args.model != 'observe' and (not args.source or not args.checkpoint):
        parser.error('A real model source and checkpoint are required')
    return args


def load_policy(args):
    """Load a real checkpoint once; a resident caller reuses this object for every episode."""
    policy = None
    if args.model != 'observe':
        from model_adapters import make_adapter
        policy = make_adapter(args.model, source=args.source, checkpoint=args.checkpoint,
                              cache_root=args.cache_root, history=args.history if args.history is not None else (0 if args.model == 'gamescaling' else 200),
                              image_width=args.image_width, max_new_tokens=args.max_new_tokens,
                              cuda_graph=args.cuda_graph, fast_start=args.p2p_fast_start,
                              p2p_mouse_sampling=args.p2p_mouse_sampling,
                              observation_profile=getattr(args, 'observation_profile', LEGACY),
                              execution_feedback=args.p2p_execution_feedback, goal_embedding=args.goal_embedding,
                              instruction=args.instruction,
                              sampling=args.sampling, temperature=args.temperature,
                              top_k=args.top_k, top_p=args.top_p,
                              gamescaling_prefix_cache=args.gamescaling_prefix_cache)
    return policy


def run_episode(args, policy=None, control=None):
    """Run one owned bridge lease with an optional already-loaded model and live controls."""
    if policy is not None:
        from PIL import Image
    bridge = Bridge(args.pipe)
    try:
        profile_contract = verify_hello(bridge.hello, getattr(args, 'observation_profile', LEGACY), args.model)
        if (policy is not None and args.model == 'open-p2p'
                and getattr(policy, 'observation_profile', LEGACY) != profile_contract['profile']):
            raise ValueError('Loaded policy preprocessing differs from the verified stream profile')
    except Exception:
        bridge.handle.close()
        raise
    if getattr(args, 'expected_process_id', None) is not None:
        try:
            from resident_runtime import verify_bridge_identity
            verify_bridge_identity(bridge.handle, args.expected_process_id, args.expected_session_id)
        except Exception:
            bridge.handle.close()
            raise
    report = {'mode': 'live-bound-game-stream', 'hello': bridge.hello,
              'observationProfile': profile_contract['profile'], 'preprocessingContract': profile_contract,
              'inputRequested': args.enable_input, 'model': args.model, 'decisions': [], 'framesReceived': 0,
              'maxInputActions': args.max_input_actions, 'acceptedInputActions': 0,
              'softCadence': args.soft_cadence, 'actionHoldMs': args.action_hold_ms,
              'freshFrameAtDecision': args.fresh_frame_at_decision,
              'observationAgeClock': 'source_freshness_anchor_when_known; host_capture_request_fallback',
              'measuresGameRenderAge': False,
              'readinessSnapshotsRequested': args.readiness_snapshots,
              'decisionClock': 'resume-after-overrun' if args.soft_cadence else 'fixed-ticks',
              'unappliedAcceptedActions': 0, 'receiptHistoryResets': 0,
              'controlTransitions': [], 'goalChanges': [],
              'captureQuality': {'check': 'wholeBufferBlackOrWhite', 'usableFrames': 0,
                                 'allBlackFrames': 0, 'allWhiteFrames': 0, 'rejectedPredictions': 0}}
    # Only an explicit capability promises enforcement after pipe transport and
    # executor scheduling. Legacy peers still get the existing client age check.
    supports_start_deadline = bridge.hello.get('supportsStartBeforeMs') is True
    report['firstInputDeadlinePolicy'] = {
        'serverSupported': supports_start_deadline,
        'serverEnforcementRequested': supports_start_deadline and args.enable_input,
        'enforcement': ('client-proposal-and-server-first-input' if supports_start_deadline else 'client-proposal-only')
                        if args.enable_input else 'observation-only',
        'maxObservationAgeMs': args.max_observation_age_ms,
        'clock': report['observationAgeClock']}
    capability = bridge.hello.get('worldReadiness', {})
    if args.require_world_ready and (capability.get('version') != 1 or not capability.get('requiredForInput')):
        bridge.handle.close()
        raise RuntimeError('This session requires the game-world readiness gate in the BetterGI bridge')
    if args.enable_input and not bridge.hello.get('inputEnabled'):
        bridge.handle.close()
        raise RuntimeError('BetterGI started in observation-only mode; enable input explicitly on both sides')
    idle_recovery = getattr(control, 'navigation_idle_recovery', None)
    if idle_recovery is None:
        idle_recovery = NavigationIdleRecovery(getattr(args, 'navigation_idle_reset_seconds', None))
        if control:
            control.navigation_idle_recovery = idle_recovery
    idle_recovery.begin_lease(bridge.hello['sessionId'])
    initial_goal = control.goal_identity() if control else {
        'policyGoalVersion': 0, 'appliedGoalRequestId': None,
        'goalIntent': getattr(args, 'goal_intent', 'unspecified')}
    idle_recovery.set_goal(initial_goal['policyGoalVersion'], initial_goal['appliedGoalRequestId'],
                           initial_goal.get('goalIntent', 'unspecified'))
    motion_capability = bridge.hello.get('motionEvidence', {})
    report['navigationIdleRecoveryEvents'] = []
    report['navigationIdleRecovery'] = idle_recovery.snapshot()
    report['motionEvidenceCapability'] = motion_capability
    try:
        if idle_recovery.threshold is not None and (bridge.hello.get('supportsRelease') is not True
                or not getattr(policy, 'execution_feedback', False) or not callable(getattr(policy, 'reset', None))):
            raise RuntimeError('Navigation idle recovery requires acknowledged release and a resettable feedback policy')
        if args.readiness_snapshots:
            if bridge.hello.get('supportsReadinessSnapshots') is not True:
                raise RuntimeError('This BetterGI build does not support native readiness snapshots')
            configured = bridge.request('configureDiagnostics', recordReadinessTransitions=True)[0]
            if configured.get('type') != 'diagnostics' or configured.get('diagnostics', {}).get('enabled') is not True:
                raise RuntimeError('The bridge did not acknowledge native readiness snapshots')
            report['readinessDiagnostics'] = configured['diagnostics']
        server_keys = set(bridge.hello.get('allowedKeys', []))
        configured_keys, effective_keys = resolve_input_keys(args.input_keys, server_keys)
        report['configuredInputKeys'] = configured_keys
        report['effectiveInputKeys'] = sorted(effective_keys)
        recorder = AsyncVideoRecorder(args.record_dir, args.ffmpeg, args.fps, args.record_max_mib*2**20,
                                      preview=args.preview) if args.record_dir else None
    except Exception:
        bridge.handle.close()
        raise
    stopped = threading.Event()
    progress = None
    if args.navigation_progress:
        from navigation_progress import NavigationProgress
        progress = NavigationProgress()
        report['navigationProgress'] = []
    latest = LatestFrame()
    server_snapshot = (time.perf_counter(), {})
    unapplied_receipt_sequence = 0
    recovery_interruption_sequence = 0
    receipts = []
    report['decisionHz'] = args.decision_hz
    report['capturePollHz'] = args.fps
    report['maxObservationAgeMs'] = args.max_observation_age_ms
    # A later set_goal mutates adapter metadata; this episode's starting identity is immutable.
    report['policyMetadata'] = copy.deepcopy(policy.metadata) if policy else None
    report['initialGoalState'] = control.goal_state() if control else None
    report['residentRunId'] = control.run_id if control else None
    report['serverDroppedReceipts'] = 0
    if recorder:
        recorder.event({'type': 'episodeStart', 'sessionId': bridge.hello['sessionId'],
                        'clock': bridge.hello.get('clock'), 'clockFrequency': bridge.hello.get('clockFrequency'),
                        'captureTimestampKind': bridge.hello.get('captureTimestampKind'),
                        'sourceFrameTiming': bridge.hello.get('sourceFrameTiming'),
                        'observationProfile': profile_contract['profile'], 'preprocessingContract': profile_contract,
                        'observationAgeClock': report['observationAgeClock'],
                        'firstInputDeadlinePolicy': report['firstInputDeadlinePolicy'],
                        'navigationIdleRecovery': report['navigationIdleRecovery'],
                        'motionEvidenceCapability': motion_capability,
                        'model': args.model, 'inputRequested': args.enable_input,
                        'configuredInputKeys': configured_keys, 'effectiveInputKeys': sorted(effective_keys),
                        'maxInputActions': args.max_input_actions,
                        'capturePollHz': args.fps, 'decisionHz': args.decision_hz,
                        'freshFrameAtDecision': args.fresh_frame_at_decision,
                        'frameQualityCheck': report['captureQuality']['check'],
                        'maxObservationAgeMs': args.max_observation_age_ms,
                        'policyMetadata': report['policyMetadata'], 'goalState': report['initialGoalState'],
                        'residentRunId': report['residentRunId']})

    def collect_receipts(metadata):
        nonlocal unapplied_receipt_sequence
        # No JSON serialization, flushing, or filesystem access occurs here.
        for receipt in metadata.get('receipts', []):
            receipts.append(receipt)
            if progress:
                progress.receipt(receipt)
            if (getattr(policy, 'execution_feedback', False) and receipt.get('modelId') == args.model
                    and not receipt.get('appliedSteps')):
                unapplied_receipt_sequence += 1
                report['unappliedAcceptedActions'] += 1
            if recorder:
                recorder.event(receipt)
        dropped = metadata.get('droppedReceipts', 0)
        if dropped > report['serverDroppedReceipts']:
            report['serverDroppedReceipts'] = dropped
            if recorder:
                recorder.fail('Server dropped execution receipts; this episode has incomplete labels')

    receive_lock = threading.Lock()
    received_frame_id = None
    recovery_capture_context = None

    def unapplied_history_receipts(items):
        """Classify exactly the receipt set that requires the existing policy-history reset."""
        return [item for item in items if getattr(policy, 'execution_feedback', False)
                and item.get('modelId') == args.model and not item.get('appliedSteps')]

    def poll_frame():
        """Serialize frame ingestion so scheduled and just-in-time polls cannot reorder evidence."""
        nonlocal server_snapshot
        nonlocal received_frame_id
        nonlocal recovery_interruption_sequence
        nonlocal recovery_capture_context
        with receive_lock:
            start = time.perf_counter_ns()
            metadata, pixels = bridge.request('frame')
            arrived = time.perf_counter_ns()
            if metadata.get('type') == 'frame':
                verify_frame(metadata, pixels, profile_contract)
            if idle_recovery.threshold is not None:
                context = capture_context(metadata) if metadata.get('type') == 'frame' else None
                if recovery_capture_context is not None and context != recovery_capture_context:
                    # Include cached payload replies: current readiness may close while frameId is unchanged.
                    recovery_interruption_sequence += 1
                recovery_capture_context = context
            server_snapshot = (time.perf_counter(), metadata)
            collect_receipts(metadata)
            if metadata.get('type') == 'frame' and metadata['frameId'] != received_frame_id:
                if len(pixels) != metadata['width'] * metadata['height'] * 3:
                    raise ValueError('RGB payload does not match declared dimensions')
                metadata['clientReceivedNs'] = arrived
                metadata['transportRoundTripMs'] = (arrived-start)/1e6
                metadata['frameQuality'] = rgb_frame_quality(pixels)
                if idle_recovery.threshold is not None and not eligible_frame(metadata, metadata,
                        server_snapshot[0], time.perf_counter_ns(), args.max_observation_age_ms, motion_capability):
                    # Preserve a short ineligible transition even when policy ticks miss that payload.
                    recovery_interruption_sequence += 1
                report['captureQuality'][metadata['frameQuality'] + 'Frames'] += 1
                report['framesReceived'] += 1
                latest.publish(metadata, pixels)
                if recorder:
                    recorder.put(metadata, pixels)
                received_frame_id = metadata['frameId']

    def receive():
        capture_cadence = DecisionCadence(args.fps, time.perf_counter())
        try:
            while not stopped.is_set():
                if not sleep_until(capture_cadence.next_at, stopped):
                    break
                poll_frame()
                capture_cadence.advance(time.perf_counter())
        except Exception as exc:
            report['streamError'] = str(exc)
            stopped.set()

    producer = threading.Thread(target=receive, daemon=True)
    producer.start()
    deadline = time.perf_counter() + args.seconds
    cadence = DecisionCadence(args.decision_hz, time.perf_counter(), resume_immediately=args.soft_cadence)
    previous = None
    hold_reason = None
    last_readiness_epoch = None
    last_accepted_at = None
    history_gap_reset = False
    seen_unapplied_receipts = 0
    recovery_receipt_cursor = 0
    seen_recovery_interruptions = 0
    recording_error_reported = False

    def hold(reason, force_release=False):
        """Release once per interruption and clear stale context without unloading weights."""
        nonlocal hold_reason
        idle_recovery.interrupt(reason)
        if hold_reason is None or force_release:
            if force_release and not bridge.hello.get('supportsRelease'):
                raise RuntimeError('Live goal switching requires acknowledged bridge input release')
            if bridge.hello.get('supportsRelease'):
                released = bridge.request('release')[0]
                if released.get('type') != 'released':
                    raise RuntimeError('The bridge did not acknowledge input release')
                collect_receipts(released)
            if policy is not None and hasattr(policy, 'reset'):
                policy.reset()
            if progress:
                progress.reset()
            transition = {'type': 'controlTransition', 'state': 'held', 'reason': reason,
                          'clientTimeNs': time.perf_counter_ns(), 'frameId': previous}
            report['controlTransitions'].append(transition)
            if recorder:
                recorder.event(transition)
        hold_reason = reason
        if control:
            control.publish(state='paused' if reason in ('userPause', 'controlError', 'goalChange', 'goalChangeFailed')
                            else 'waitingForWorld', reason=reason,
                            framesReceived=report['framesReceived'], acceptedInputActions=report['acceptedInputActions'])

    def recovery_event(event):
        """Record sparse trigger/rearm outcomes on the policy thread only."""
        if event:
            event['clientTimeNs'] = time.perf_counter_ns()
            report['navigationIdleRecoveryEvents'].append(event)
            if recorder:
                recorder.event(event)

    def release_for_recovery(frame, expected_sequence, still_current):
        """Revalidate after any ingestion lock wait, immediately before dispatching the release."""
        nonlocal server_snapshot
        with receive_lock:
            if not still_current():
                raise RecoverySuperseded()
            checked_at = time.perf_counter_ns()
            received_at, status = server_snapshot
            eligible = (expected_sequence == recovery_interruption_sequence
                and latest_recovery_eligible(checked_at)
                and eligible_frame(frame, status, received_at, checked_at,
                                   args.max_observation_age_ms, motion_capability))
            if not idle_recovery.window_is_current(checked_at / 1e9, eligible):
                raise RecoverySuperseded()
            released = bridge.request('release')[0]
            collect_receipts(released)
            server_snapshot = (time.perf_counter(), released)
            return released

    def reset_for_recovery():
        """Clear only policy temporal history; adapter reset retains loaded weights and graph storage."""
        policy.reset()
        if progress:
            progress.reset()

    def latest_recovery_eligible(now_ns):
        """Observe current pixels independently of an older prediction's timing failure."""
        status_received_at, status = server_snapshot
        item = latest.newer_than(None)
        return (recovery_interruption_sequence == seen_recovery_interruptions and item is not None
                and eligible_frame(item[0], status, status_received_at, now_ns,
                                   args.max_observation_age_ms, motion_capability))

    try:
        while time.perf_counter() < deadline and not stopped.is_set():
            if recorder and recorder.error and not recording_error_reported:
                print(json.dumps({'recordingError': recorder.error, 'inferenceContinues': True}), file=sys.stderr, flush=True)
                recording_error_reported = True
            if not sleep_until(min(cadence.next_at, deadline), stopped) or time.perf_counter() >= deadline:
                break
            # Goal mutation stays on this thread, after the old action transaction has ended.
            # The monitor already invalidated its epoch, so no old-goal result can be reused.
            if control:
                from resident_runtime import apply_pending_goal
                change = apply_pending_goal(control, policy, lambda: hold('goalChange', force_release=True))
                if change:
                    report['goalChanges'].append(change)
                    if recorder:
                        recorder.event(change)
                    # Release invalidates earlier server observations. Wait for a payload
                    # captured after the acknowledgement instead of retrying a stale frame.
                    item = latest.newer_than(None)
                    if item:
                        previous = item[0]['frameId']
            command, control_error = control.snapshot() if control else ('run', None)
            goal_state = control.goal_identity() if control else {
                'policyGoalVersion': 0, 'appliedGoalRequestId': None,
                'goalIntent': getattr(args, 'goal_intent', 'unspecified')}
            idle_recovery.set_goal(goal_state['policyGoalVersion'], goal_state['appliedGoalRequestId'],
                                   goal_state.get('goalIntent', 'unspecified'))
            # Capture appends receipts, but only this serial thread mutates recovery state.
            with receive_lock:
                pending_receipts = receipts[recovery_receipt_cursor:]
                recovery_receipt_cursor += len(pending_receipts)
                observed_receipt_sequence = unapplied_receipt_sequence
            # Inspect before receipt() retires the bounded accepted-noop identity ledger.
            noop_history_reset = idle_recovery.matched_noop_expiries(unapplied_history_receipts(pending_receipts))
            for receipt in pending_receipts:
                recovery_event(idle_recovery.receipt(receipt))
            if recovery_interruption_sequence != seen_recovery_interruptions:
                idle_recovery.interrupt('ineligibleCapture')
                seen_recovery_interruptions = recovery_interruption_sequence
            if command == 'stop':
                report['endReason'] = 'userStop'
                break
            if command == 'pause':
                hold('goalChangeFailed' if control and control.goal_state()['goalError'] else
                     'controlError' if control_error else 'userPause')
                cadence.advance(time.perf_counter())
                continue
            # Control and goal changes are settled before selecting the next world observation.
            if observed_receipt_sequence != seen_unapplied_receipts:
                policy.reset()
                reset_checked_at = time.perf_counter_ns()
                idle_recovery.history_reset(noop_history_reset, reset_checked_at / 1e9,
                                            latest_recovery_eligible(reset_checked_at))
                seen_unapplied_receipts = observed_receipt_sequence
                report['receiptHistoryResets'] += 1
            refresh_ms = 0.0
            if policy is not None and args.fresh_frame_at_decision:
                refresh_started = time.perf_counter_ns()
                poll_frame()
                refresh_ms = (time.perf_counter_ns()-refresh_started)/1e6
            received_at, current_status = server_snapshot
            if capability.get('requiredForInput') and current_status:
                gate = current_status.get('worldReadiness', {})
                epoch = gate.get('epoch')
                changed = last_readiness_epoch is not None and epoch != last_readiness_epoch
                last_readiness_epoch = epoch
                if changed or gate.get('ready') is not True or current_status.get('inputAvailable') is not True or time.perf_counter()-received_at > .25:
                    hold('worldTransition' if changed else gate.get('reason', 'worldNotReady'))
                    cadence.advance(time.perf_counter())
                    continue
            item = latest.newer_than(previous)
            if item is None:
                cadence.advance(time.perf_counter())
                continue
            frame, pixels = item
            selected_at = time.perf_counter_ns()
            previous = frame['frameId']
            # Preserve blank captures as evidence but never feed them into policy history.
            # A later usable frame resumes inference normally after a loading fade.
            if frame['frameQuality'] != 'usable':
                hold('blankCapture')
                cadence.advance(time.perf_counter())
                continue
            if capability.get('requiredForInput') and frame.get('frameWorldReadiness', {}).get('ready') is not True:
                hold('payloadNotGameWorld')
                cadence.advance(time.perf_counter())
                continue
            if not idle_recovery.allows_frame(frame, current_status,
                    fresh=fresh_frame(frame, time.perf_counter_ns(), args.max_observation_age_ms)
                    if idle_recovery.barrier is not None else True):
                cadence.advance(time.perf_counter())
                continue
            if hold_reason is not None:
                transition = {'type': 'controlTransition', 'state': 'running', 'reason': 'freshGameWorld',
                              'clientTimeNs': time.perf_counter_ns(), 'frameId': previous}
                report['controlTransitions'].append(transition)
                if recorder:
                    recorder.event(transition)
                hold_reason = None
                last_accepted_at = None
                history_gap_reset = False
            if policy is None:
                if control:
                    control.publish(state='observing', reason=None, frameId=previous,
                                    framesReceived=report['framesReceived'], worldReadiness=current_status.get('worldReadiness'))
                cadence.advance(time.perf_counter())
                continue
            if (getattr(policy, 'execution_feedback', False) and last_accepted_at is not None
                    and time.perf_counter()-last_accepted_at > .5 and not history_gap_reset):
                policy.reset()
                idle_recovery.interrupt('acceptanceGapHistoryReset')
                history_gap_reset = True
            image = Image.frombytes('RGB', (frame['width'], frame['height']), pixels)
            if progress:
                metric = progress.observe(image, frame['capturedAtMs'])
                if metric:
                    event = dict(metric, type='navigationProgress', frameId=frame['frameId'],
                                 capturedAtMs=frame['capturedAtMs'])
                    report['navigationProgress'].append(event)
                    if recorder:
                        recorder.event(event)
                    if control:
                        control.publish(navigationProgress=event)
            control_token = control.prediction_token() if control else (0, 0, None, 'run')
            if control_token[3] != 'run':
                cadence.advance(time.perf_counter())
                continue
            predict_started = time.perf_counter_ns()
            profile_argument = {'observation_profile': P2P_NATIVE} if profile_contract['profile'] == P2P_NATIVE else {}
            result = policy.predict(image, (frame['sourceWidth'], frame['sourceHeight']), **profile_argument)
            now = time.perf_counter_ns()
            policy_ms = (now-predict_started)/1e6
            timing = frame_timing(frame, predict_started, selected_at, refresh_ms)
            observed_at = observation_timestamp(frame)
            # Add the full round trip as a conservative bound for server-to-client transfer.
            age = timing['serverAgeAtReceiptMs'] + (now-frame['clientReceivedNs'])/1e6 + frame['transportRoundTripMs']
            cadence_met = policy_ms <= cadence.period * 1000
            result.update(frameId=frame['frameId'], estimatedObservationAgeMs=age,
                          observationTimestampMs=observed_at,
                          policyWallMs=policy_ms, controlCadenceMet=cadence_met,
                          controlEpoch=control_token[0], policyGoalVersion=control_token[1],
                          appliedGoalRequestId=control_token[2], goalIntent=goal_state.get('goalIntent', 'unspecified'))
            result['frameTiming'] = timing
            if args.action_hold_ms is not None and result.get('parseValid') and len(result.get('steps', [])) == 1:
                result['rawPolicySteps'] = [dict(step) for step in result['steps']]
                result['steps'] = [dict(result['steps'][0], durationMs=args.action_hold_ms)]
                result['controllerResampling'] = 'explicit-bounded-key-hold; mouse applied once'
            rejection = proposal_rejection(result, server_keys, args.enable_input, age,
                                           args.max_observation_age_ms, policy_ms, cadence.period * 1000,
                                           trial_keys=effective_keys, enforce_compute_budget=not args.soft_cadence)
            # Capture can turn blank while predict() is running. Its older proposal
            # must not reach the controller even when compute and age budgets passed.
            newest = latest.newer_than(None)
            result['latestFrameQuality'] = newest[0]['frameQuality'] if newest else None
            if newest and newest[0]['frameQuality'] != 'usable':
                rejection = 'latestFrameBlank'
                report['captureQuality']['rejectedPredictions'] += 1
            _, latest_status = server_snapshot
            latest_gate = latest_status.get('worldReadiness', {})
            if capability.get('requiredForInput') and (latest_gate.get('ready') is not True
                    or latest_status.get('inputAvailable') is not True
                    or latest_gate.get('epoch') != frame.get('frameWorldReadiness', {}).get('epoch')):
                rejection = 'worldChangedDuringPrediction'
            if control and control.prediction_token() != control_token:
                rejection = 'residentControlEpochChanged'
            if unapplied_receipt_sequence != seen_unapplied_receipts:
                rejection = 'unappliedActionHistory'
            if stopped.is_set():
                rejection = 'streamStopped'
            # Do not silently strip keys or execute a different action than evaluated.
            if rejection is None:
                start_deadline = {'startBeforeMs': observed_at+args.max_observation_age_ms} if supports_start_deadline else {}
                if start_deadline:
                    result.update(start_deadline)
                result['acceptance'] = bridge.request('action', requestId=uuid.uuid4().hex,
                    frameId=frame['frameId'], observedAtMs=frame['capturedAtMs'],
                    expiresAtMs=observed_at+700, modelId=args.model,
                    steps=result['steps'], **start_deadline)[0]
            else:
                result['acceptance'] = {'type': 'notSubmitted', 'reason': rejection}
            if result['acceptance'].get('type') == 'accepted':
                report['acceptedInputActions'] += 1
                last_accepted_at = time.perf_counter()
                history_gap_reset = False
            if getattr(policy, 'execution_feedback', False):
                committed = result['acceptance'].get('type') == 'accepted'
                policy.finish_action(committed)
                result['historyCommitted'] = committed
            report['decisions'].append(result)
            if recorder:
                recorder.event({'type': 'proposal', 'frameId': frame['frameId'],
                                'observedAtMs': frame['capturedAtMs'], 'model': args.model,
                                'observationTimestampMs': observed_at,
                                'startBeforeMs': result.get('startBeforeMs'),
                                'steps': result['steps'], 'acceptance': result['acceptance'],
                                'rawPolicySteps': result.get('rawPolicySteps'),
                                'controllerResampling': result.get('controllerResampling'),
                                'controlEpoch': result['controlEpoch'], 'policyGoalVersion': result['policyGoalVersion'],
                                'appliedGoalRequestId': result['appliedGoalRequestId'],
                                'goalIntent': result['goalIntent'],
                                'latestFrameQuality': result['latestFrameQuality'],
                                'frameTiming': result['frameTiming'],
                                'policyWallMs': policy_ms, 'estimatedObservationAgeMs': age})
            print(json.dumps({'frameId': previous, 'modelMs': result['fullActionMs'], 'ageMs': age,
                              'acceptance': result['acceptance']}), flush=True)
            if control:
                control.publish(state='running', reason=None, frameId=previous,
                                framesReceived=report['framesReceived'], acceptedInputActions=report['acceptedInputActions'],
                                policyWallMs=policy_ms, observationAgeMs=age,
                                latestAcceptance=result['acceptance'])
            if args.max_input_actions is not None and report['acceptedInputActions'] >= args.max_input_actions:
                report['endReason'] = 'maxInputActions'
                break  # Normal stop/receipt cleanup releases the input owner immediately.
            if idle_recovery.threshold is not None:
                with receive_lock:
                    newly_unapplied = unapplied_history_receipts(receipts[recovery_receipt_cursor:])
                    new_receipt_count = unapplied_receipt_sequence - seen_unapplied_receipts
                status_received_at, recovery_status = server_snapshot
                checked_at = time.perf_counter_ns()
                latest_eligible = (latest_recovery_eligible(checked_at) and not stopped.is_set()
                    and (control is None or control.prediction_token() == control_token))
                # Both evaluated and latest pixels must still have eligible motion/world evidence.
                eligible = (latest_eligible and eligible_frame(frame, recovery_status, status_received_at,
                            checked_at, args.max_observation_age_ms, motion_capability))
                matched_noop_expiries = (len(newly_unapplied) == new_receipt_count
                                        and idle_recovery.matched_noop_expiries(newly_unapplied))
                trigger = idle_recovery.proposal(result, frame, checked_at / 1e9, eligible,
                    latest_eligible=latest_eligible, matched_noop_expiries=matched_noop_expiries)
                if trigger:
                    expected_recovery_sequence = seen_recovery_interruptions
                    # Pause/stop/new-goal tokens win before and after acknowledged release.
                    def still_current():
                        token_current = control is None or control.prediction_token() == control_token
                        return token_current and not stopped.is_set() and time.perf_counter() < deadline
                    event = idle_recovery.execute(trigger,
                        lambda: release_for_recovery(frame, expected_recovery_sequence, still_current), reset_for_recovery,
                                                  latest.clear, still_current)
                    recovery_event(event)
                    if event['outcome'] in ('releaseFailed', 'resetFailed'):
                        raise RuntimeError('Navigation idle recovery ' + event['outcome'] + ': ' + event['error'])
                    if 'releasedAtMs' in event:
                        if event['outcome'] == 'reset':
                            hold_reason = 'navigationIdleReset'
                            # Release may cancel the last accepted no-op before its first
                            # step. This reset already clears that action's history.
                            seen_unapplied_receipts = unapplied_receipt_sequence
                        last_readiness_epoch = event['readinessEpoch']
                        last_accepted_at = None
                        history_gap_reset = False
                report['navigationIdleRecovery'] = idle_recovery.snapshot()
                if control:
                    control.publish(navigationIdleRecovery=report['navigationIdleRecovery'])
            cadence.advance(time.perf_counter())
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        stopped.set()
        producer.join(timeout=3)
        if not producer.is_alive():
            try:
                if args.readiness_snapshots:
                    diagnostic_status = bridge.request('status')[0]
                    collect_receipts(diagnostic_status)
                    report['readinessDiagnosticsBeforeStop'] = diagnostic_status.get('diagnostics')
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
        if control:
            report['finalGoalState'] = control.goal_state()
            if report['finalGoalState']['goalError']:
                report.setdefault('error', report['finalGoalState']['goalError'])
        report.setdefault('endReason', 'noUsableFrames' if report.get('captureError') else
                          'streamError' if report.get('streamError') else 'error' if report.get('error') else
                          'durationElapsed' if time.perf_counter() >= deadline else 'stopped')
        # Keep the starting goal immutable while retaining validation costs and
        # cache state accumulated by later predictions (including failed ones).
        report['finalPolicyMetadata'] = copy.deepcopy(policy.metadata) if policy else None
        report['navigationIdleRecovery'] = idle_recovery.snapshot()
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


def main():
    """Select a bounded single lease or a resident process with explicit RDP ownership."""
    args = parse_arguments()
    if args.resident:
        from resident_runtime import run_resident
        return run_resident(args, load_policy, run_episode)
    return run_episode(args, load_policy(args))


if __name__ == '__main__':
    raise SystemExit(main())
