"""Continuous BetterGI named-pipe client: latest frames, real policy, bounded recording.

Input stays disabled unless both BetterGI and this client explicitly enable it.
The video sidecar maps every encoded frame to the server monotonic clock;
video presentation time is an index, not an assumption about capture cadence.
"""
import argparse
import copy
from contextlib import contextmanager, nullcontext
import hashlib
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
from host_observation import HostObservationContract
from hybrid_routes import COURTYARD_ROUTE, EXECUTABLE_ROUTE_IDS, PATROL_STATIONS, ROUTE_IDS, STAIR_POST_ROUTE, STREET_PATROL_ROUTE, SURFACE_ROUTES
from navigation_profiles import COURTYARD_PROFILE,SURFACE_PROFILE,NAVIGATION_PROFILES,validate_capability,required_profile
from navigation_idle_recovery import (GOAL_INTENTS, NavigationIdleRecovery, RecoverySuperseded,
                                      capture_context, eligible_frame, fresh_frame)
from observation_profiles import (LEGACY, P2P_NATIVE, PROFILES, FrameProfileError,
                                  validate_model_profile, verify_hello, verify_frame)
from p2p_startup import validate_startup_options
from bridge_transport import forbid_reconnect, is_transport_failure, transport_origin


class Bridge:
    """Serialize request/response pairs on the same-user local named pipe."""
    @staticmethod
    def _pipe_io(operation, call, *args, **kwargs):
        """Keep transport provenance at the actual pipe call, including AST-only fixtures."""
        from bridge_transport import pipe_io
        return pipe_io(operation, call, *args, **kwargs)

    @staticmethod
    def _pipe_eof(message):
        """Preserve EOF type while identifying the owned pipe as its source."""
        from bridge_transport import pipe_eof
        return pipe_eof(message)

    @staticmethod
    def _terminal_transport_error(error):
        """Experimental ownership failures never authorize a new ordinary lease."""
        from bridge_transport import forbid_reconnect
        forbid_reconnect(error, "experimentalChannelFailure")

    def __init__(self, name):
        if not re.fullmatch(r'BetterGI\.Agent\.[A-Za-z0-9_.-]{1,100}', name):
            raise ValueError('Use a local pipe name beginning BetterGI.Agent.')
        if os.name != 'nt':
            raise RuntimeError('The BetterGI bridge requires Windows')
        self.handle = self._pipe_io('open', open, '\\\\.\\pipe\\' + name, 'r+b', buffering=0)
        self.lock = threading.Lock()
        # Keep only the original hello bytes and this connection's original owner.
        self._hello_handle = self.handle
        self._experimental_enable_attempted = False
        self._experimental_enable_failed = False
        self._experimental_enable_close_attempted = False
        try:
            self.hello, payload = self._read(remember_hello=True)
            self._hello_object = self.hello
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
            chunk = self._pipe_io('read', self.handle.read, length-len(chunks))
            if not chunk:
                raise self._pipe_eof('BetterGI disconnected; input owner must release held input')
            chunks.extend(chunk)
        return bytes(chunks)

    def _experimental_connection(self, *, prior_error=None):
        """Validate the negotiated connection before preparation, I/O and fact intake."""
        binding = getattr(self, '_experimental_connection_identity', None)
        if binding is None:
            return None  # Ordinary clients and manually attached inert intakes keep their path.
        owned, original_hello, original_raw, intake = binding
        try:
            from step_application_transport import parse_header
            import step_application_protocol as p
            p.require(self.handle is owned and self.hello is original_hello
                      and getattr(self, '_step_application_intake', None) is intake
                      and p.canonical(self.hello,4*1024*1024)
                          == p.canonical(parse_header(original_raw),4*1024*1024),
                      'experimental_original_connection')
        except BaseException as error:
            # Identity loss is uncertainty, even if this request wrote no bytes.
            # If I/O already failed, retain that actual failure as primary.
            failure = error if prior_error is None else prior_error
            self._experimental_connection_error = error
            self._experimental_enable_failed = True
            self._experimental_enable_error = failure
            try:
                intake.ledger.uncertain('experimental_original_connection')
            except BaseException as cleanup:
                self._experimental_enable_intake_error = cleanup
                BaseException.add_note(failure, 'Experimental intake cleanup failed: '+type(cleanup).__name__[:64])
            if not self._experimental_enable_close_attempted:
                self._experimental_enable_close_attempted = True
                try:
                    owned.close()
                except BaseException as cleanup:
                    self._experimental_enable_close_error = cleanup
                    BaseException.add_note(failure, 'Experimental connection close failed: '+type(cleanup).__name__[:64])
            if prior_error is None:
                raise
        return owned

    def _experimental_exact(self, length, *, owned_handle=None):
        """Read solely from the captured enable/negotiated handle; never follow a replacement."""
        chunks = bytearray()
        while len(chunks) < length:
            owned = self._experimental_connection() if owned_handle is None else owned_handle
            chunk = self._pipe_io('read', owned.read, length-len(chunks))
            if owned_handle is None:
                self._experimental_connection()
            if not chunk:
                raise self._pipe_eof('BetterGI disconnected; input owner must release held input')
            chunks.extend(chunk)
        return bytes(chunks)

    def _read(self, *, remember_hello=False, enabling=False, owned_handle=None):
        if owned_handle is not None:
            exact = lambda length: self._experimental_exact(length, owned_handle=owned_handle)
        else:
            exact = self._experimental_exact if getattr(self, '_experimental_connection_identity', None) is not None else self._exact
        length = struct.unpack('<I', exact(4))[0]
        if not 0 < length <= 4 * 1024 * 1024:
            raise ValueError('Invalid JSON packet length')
        raw_header = exact(length)
        if remember_hello:
            self._hello_raw = raw_header
        if not enabling and getattr(self, '_step_application_intake', None) is None:
            message = json.loads(raw_header)
        else:
            from step_application_transport import parse_header
            message = parse_header(raw_header)
        if not isinstance(message, dict):
            raise ValueError('Expected a JSON packet object')
        size = message.get('payloadBytes', 0)
        if type(size) is not int or not 0 <= size <= 32 * 1024 * 1024:
            raise ValueError('Invalid image packet length')
        if enabling and size:
            raise ValueError('An enable reply cannot carry image bytes')
        return message, exact(size) if size else b''

    def enable_experimental_step_applications(self, *, reviewed_producer_build_sha256):
        """Negotiate one explicit transport-only v2 channel; never construct/install a model owner.

        The caller supplies the reviewed producer DLL hash, not a guessed channel.
        A failed or ambiguous attempt retires only this Bridge's original handle.
        Normal clients do not call this entry and retain their existing behavior.
        """
        with self.lock:
            # A retired connection keeps its first failure and all cleanup evidence.
            if getattr(self, '_experimental_enable_failed', False):
                raise RuntimeError('experimental_enable_connection_retired')
            negotiated = getattr(self, '_experimental_connection_identity', None)
            owned = self._hello_handle if negotiated is None else negotiated[0]
            candidate = None
            try:
                if self._experimental_enable_attempted or getattr(self, '_step_application_intake', None) is not None:
                    raise RuntimeError('experimental_enable_single_attempt')
                self._experimental_enable_attempted = True
                from step_application_transport import StepApplicationIntake, parse_header
                import step_application_protocol as p
                import step_application_protocol_v2 as v2
                p.digest(reviewed_producer_build_sha256)
                original = parse_header(self._hello_raw)

                def original_connection():
                    """Join the retained object, exact hello content and original handle under the lock."""
                    p.require(self.handle is owned and self.hello is self._hello_object
                              and p.canonical(self.hello,4*1024*1024) == p.canonical(original,4*1024*1024),
                              'experimental_enable_original_connection')

                original_connection()
                p.require(type(original.get('version')) is int and original['version'] == 1
                          and original.get('type') == 'hello' and type(original.get('goalVersion')) is int
                          and original['goalVersion'] == 1 and original.get('inputEnabled') is True,
                          'experimental_enable_hello')
                p.text(original['sessionId']);p.text(original['ownerEpoch'])
                p.fields(original['stepApplicationsAvailable'], ('version','mode'))
                p.require(type(original['stepApplicationsAvailable']['version']) is int
                          and original['stepApplicationsAvailable']['version'] == 2
                          and original['stepApplicationsAvailable']['mode'] == v2.MODE,
                          'experimental_enable_capability')
                p.keys(original['allowedKeys'], len(p.ALLOWED), policy=False)
                telemetry = original['inputTelemetry']
                p.require(type(telemetry) is dict and type(telemetry.get('version')) is int
                          and telemetry['version'] == 1, 'experimental_enable_hello_clock')
                p.integer(telemetry['sessionOriginAtStopwatchTicks'], 1)
                p.integer(telemetry['stopwatchFrequency'], 1, 10**12)
                request = dict(version=1,command='enableStepApplications',sessionId=original['sessionId'],
                               ownerEpoch=original['ownerEpoch'],goalVersion=original['goalVersion'])
                encoded = p.canonical(request,65536)
                packet = memoryview(struct.pack('<I',len(encoded))+encoded)
                while packet:
                    written = self._pipe_io('write', owned.write, packet)
                    p.require(type(written) is int and 0 < written <= len(packet), 'experimental_enable_write')
                    packet = packet[written:]
                original_connection()
                response, pixels = self._read(enabling=True, owned_handle=owned)
                observed_client_ns = time.perf_counter_ns()
                p.fields(response, ('type','stepApplicationConfirmation','serverNowMs',
                                    'stepApplications','stepApplicationTerminals'))
                p.require(response['type'] == 'stepApplicationsEnabled' and not pixels,
                          'experimental_enable_response')
                v2.elapsed(response['serverNowMs'])
                confirmation = response['stepApplicationConfirmation']
                p.fields(confirmation, ('configuration','initialTracked','limits'))
                config = confirmation['configuration']
                v2.configuration(config)
                p.require(config['sessionId'] == original['sessionId'] and config['ownerEpoch'] == original['ownerEpoch']
                          and config['buildSha256'] == reviewed_producer_build_sha256
                          and config['backendId'] == 'win32-sendinput'
                          and config['sessionOriginTicks'] == telemetry['sessionOriginAtStopwatchTicks']
                          and config['clockFrequency'] == telemetry['stopwatchFrequency']
                          and config['allowedKeys'] == sorted(set(original['allowedKeys'])-{'SHIFT','CONTROL','ESC'}),
                          'experimental_enable_confirmation_identity')
                p.tracked(confirmation['initialTracked'])
                p.require(confirmation['initialTracked']['keys'] == []
                          and confirmation['initialTracked']['complete'] is True
                          and confirmation['initialTracked']['generation'] == 0, 'experimental_enable_initial_state')
                expected_batch = dict(version=2,channelId=config['channelId'],acknowledgedThrough=0,
                    nextReservedSequence=1,authorityLost=False,closedForSubmission=False,unpublished=0,records=[])
                p.require(p.canonical(response['stepApplications']) == p.canonical(expected_batch)
                          and response['stepApplicationTerminals'] == [], 'experimental_enable_fresh_channel')
                original_connection()
                candidate = StepApplicationIntake(config,p.canonical(confirmation,8192))
                candidate.receive(request,response,observed_client_ns=observed_client_ns)
                p.require(not candidate.ledger.quarantined and not candidate.ledger.closed_for_submission,
                          'experimental_enable_channel_unavailable')
                original_connection()
                # Retain the same immutable raw hello and original owners for every later request.
                self._experimental_connection_identity = (owned, self._hello_object, self._hello_raw, candidate)
                # Only a completely validated reply can publish one intake on this connection.
                self._step_application_intake = candidate
                return candidate
            except BaseException as error:
                self._terminal_transport_error(error)
                self._experimental_enable_failed = True
                self._experimental_enable_error = error
                # A repeat retires the negotiated owner, never a substituted public intake.
                retained = candidate or (negotiated[3] if negotiated is not None
                                         else getattr(self, '_step_application_intake', None))
                if retained is not None:
                    try:
                        retained.ledger.uncertain('experimental_enable_failed')
                    except BaseException as cleanup:
                        self._experimental_enable_intake_error = cleanup
                        BaseException.add_note(error, 'Experimental intake cleanup failed: '+type(cleanup).__name__[:64])
                if not self._experimental_enable_close_attempted:
                    self._experimental_enable_close_attempted = True
                    try:
                        owned.close()
                    except BaseException as cleanup:
                        self._experimental_enable_close_error = cleanup
                        BaseException.add_note(error, 'Experimental connection close failed: '+type(cleanup).__name__[:64])
                raise

    def request(self, command, **kwargs):
        with self.lock:
            if getattr(self, '_experimental_enable_failed', False):
                raise RuntimeError('Experimental enable failed; this connection is retired')
            self._experimental_connection()
            intake = getattr(self, '_step_application_intake', None)
            if intake is None:
                payload = dict(version=1, command=command, sessionId=self.hello['sessionId'],
                               ownerEpoch=self.hello['ownerEpoch'], goalVersion=self.hello['goalVersion'], **kwargs)
                encoded = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode('utf-8')
                if len(encoded) > 65536:
                    raise ValueError('Request exceeds the server JSON limit')
                packet = memoryview(struct.pack('<I', len(encoded)) + encoded)
                while packet:
                    written = self._pipe_io('write', self.handle.write, packet)
                    if not written:
                        raise self._pipe_eof('BetterGI disconnected while sending a request')
                    packet = packet[written:]
                return self._read()
            # Explicit experimental negotiation installs only a transport intake.
            # Native model-owner construction/install barriers remain separate and unchanged.
            # Keep a minimal action label even if local envelope construction itself fails.
            payload = {'command': command}
            write_attempted = False
            try:
                payload = dict(version=1, command=command, sessionId=self.hello['sessionId'],
                               ownerEpoch=self.hello['ownerEpoch'], goalVersion=self.hello['goalVersion'], **kwargs)
                encoded = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode('utf-8')
                if len(encoded) > 65536:
                    raise ValueError('Request exceeds the server JSON limit')
                self._experimental_connection()
                payload = intake.prepare(payload)
                encoded = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode('utf-8')
                if len(encoded) > 65536:
                    raise ValueError('Request exceeds the server JSON limit')
                packet = memoryview(struct.pack('<I', len(encoded)) + encoded)
                while packet:
                    owned = self._experimental_connection()
                    write_attempted = True
                    written = self._pipe_io('write', (self.handle if owned is None else owned).write, packet)
                    self._experimental_connection()
                    if not written:
                        raise self._pipe_eof('BetterGI disconnected while sending a request')
                    packet = packet[written:]
                response, pixels = self._read()
                observed_client_ns = time.perf_counter_ns()
                self._experimental_connection()
                intake.receive(payload, response, observed_client_ns=observed_client_ns)
                return response, pixels
            except BaseException as error:
                self._terminal_transport_error(error)
                if not getattr(self, '_experimental_enable_failed', False):
                    self._experimental_connection(prior_error=error)
                if getattr(self, '_experimental_enable_failed', False):
                    raise  # Identity loss was already quarantined; never label it known-not-submitted.
                try:
                    intake.failed(payload, write_attempted=write_attempted)
                except BaseException:
                    intake.ledger.uncertain('transport_failure_classification_failed')
                raise


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


def recording_frame_metadata(metadata, execution_mode):
    """Avoid repeating the controller's rolling journal in every ordinary recorded frame."""
    result = dict(metadata)
    if execution_mode == 'off' and 'executionContext' in result:
        result.pop('executionContext')
        result['executionContextOmitted'] = True
    return result


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


class RecordingFrameQueue(queue.Queue):
    """Measure exact peak depth under the queue's existing mutex without delaying image admission."""
    def __init__(self, maxsize):
        super().__init__(maxsize)
        self.max_depth = 0

    def _put(self, item):
        """Count every admitted image before the writer can take it off the queue."""
        super()._put(item)
        self.max_depth = max(self.max_depth, self._qsize())


class AsyncVideoRecorder:
    """Bound image, observation and event queues; only the worker performs recording IO."""
    def __init__(self, directory, ffmpeg, fps, max_bytes, frame_capacity=8, event_capacity=256, preview=False,
                 metadata_capacity=256, shared_budget=None, retain_policy_rgb=False):
        if not math.isfinite(fps) or fps <= 0 or max_bytes <= 0 or min(frame_capacity, event_capacity, metadata_capacity) < 1:
            raise ValueError('Recording rate, budget, and queue capacities must be positive')
        self.directory = Path(directory)
        self.queue = RecordingFrameQueue(frame_capacity)
        self.event_queue = queue.Queue(maxsize=event_capacity)
        self.metadata_queue = queue.Queue(maxsize=metadata_capacity)
        self.ffmpeg, self.fps, self.max_bytes = ffmpeg, fps, max_bytes
        self.shared_budget = shared_budget
        self.retain_policy_rgb = retain_policy_rgb
        self.policy_rgb_bytes = 0
        self.policy_rgb_frames = 0
        self.recorded_bytes = 0
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
            for key in ('receipts', 'videoFrameIndex', 'videoPtsSeconds', 'videoQueueAccepted', 'policyRgb'):
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
            complete = self.closed and self.error is None
            return {'encodedFrames': self.encoded, 'droppedFrames': self.dropped,
                    'frameQueueCapacity': self.queue.maxsize, 'maxFrameQueueDepth': self.queue.max_depth,
                    'droppedEvents': self.dropped_events, 'abandonedFrames': self.abandoned_frames,
                    'recordedObservations': self.recorded_observations,
                    'droppedObservations': self.dropped_observations,
                    'recordedBytes': self.recorded_bytes,
                    'policyRgbEnabled': self.retain_policy_rgb, 'policyRgbBytes': self.policy_rgb_bytes,
                    'policyRgbFrames': self.policy_rgb_frames,
                    'error': self.error, 'closed': self.closed,
                    'previewFrameId': self.preview_frame_id, 'previewError': self.preview_error,
                    'complete': complete, 'lossless': complete and not any((
                        self.dropped, self.dropped_events, self.dropped_observations, self.abandoned_frames))}

    def observation(self, metadata, continuity=False):
        """Persist a source header carried across rollover without inventing a video index."""
        with self.state_lock:
            if self.closing.is_set():
                return False
            header = {key: value for key, value in metadata.items()
                      if key not in ('receipts', 'videoFrameIndex', 'videoPtsSeconds', 'videoQueueAccepted')}
            header.update(continuityContext=continuity, videoQueueAccepted=None)
            try:
                self.metadata_queue.put_nowait(header)
            except queue.Full:
                self.dropped_observations += 1
                self.fail('Recording observation queue overflow; source timing metadata is incomplete')
                return False
            self.wake.set()
            return True

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
            self.directory.mkdir(parents=True, exist_ok=False)
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
                    self.recorded_bytes = size + frames.tell() + observations.tell() + events.tell() + self.policy_rgb_bytes
                    total = self.shared_budget.update(str(self.directory), self.recorded_bytes) if self.shared_budget else self.recorded_bytes
                    if total >= self.max_bytes:
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
                    if self.retain_policy_rgb:
                        # Reserve raw bytes before any write. A retiring segment shares this same finite budget.
                        from policy_rgb_archive import write_policy_rgb
                        projected = self.recorded_bytes + len(pixels)
                        total = self.shared_budget.update(str(self.directory), projected) if self.shared_budget else projected
                        if total >= self.max_bytes:
                            raise RuntimeError('Recording byte budget reached before exact policy RGB retention')
                        metadata['policyRgb'] = write_policy_rgb(self.directory, index, metadata, pixels)
                        self.policy_rgb_bytes += len(pixels)
                        self.policy_rgb_frames += 1
                        self.recorded_bytes = projected
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
                self.recorded_bytes = total_bytes
                total = self.shared_budget.update(str(self.directory), total_bytes) if self.shared_budget else total_bytes
                if total >= self.max_bytes:
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
                                    'Explicit host snapshots retain raw QPC and use hostSnapshot.startedAtMs; '
                                    'they do not measure compositor or game-render time. '
                                    'videoPtsSeconds indexes encoded frames, not wall time; exclude capture gaps.')
            summary['budgetNote'] = ('Video plus sidecars checked between frames across active/retiring segments; '
                                     'at most two FFmpeg muxer buffers/footers can overshoot.')
            try:
                (self.directory / 'recording.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
            except Exception as exc:
                self.fail(f'Cannot save recording summary: {exc}')

    def begin_close(self):
        """Stop admission without waiting for queued evidence or the encoder footer."""
        with self.state_lock:
            self.closing.set()
            self.wake.set()

    def close(self, timeout=20):
        """Bound shutdown independently of a full queue or a stalled encoder."""
        self.begin_close()
        self.worker.join(timeout=timeout)
        if self.worker.is_alive():
            self.fail('Recording shutdown timed out; output may be incomplete')
            with self.state_lock:
                process = self.process
            if process is not None and process.poll() is None:
                process.kill()
            self.worker.join(timeout=2)
        result = self.status()
        # closed marks encoder/queue completion; the final summary write can
        # still block. Rollover requires the actual writer thread to have exited.
        result['workerRetired'] = not self.worker.is_alive()
        return result


def validate_hybrid_observe_options(args):
    """Keep the full navigation decision loop available for diagnostics without an input lease."""
    if not getattr(args,'hybrid_observe',False):
        return False
    if (not args.hybrid_navigation or not args.resident or args.model != 'open-p2p'
            or args.enable_input or args.goal_intent != 'ground-navigation'):
        raise ValueError('hybrid-observe requires resident Open P2P hybrid navigation with input disabled')
    return True


def validate_navigation_scope_options(args):
    """Keep the new outdoor scope explicit and confined to its declared route family."""
    profile=getattr(args,'navigation_profile',COURTYARD_PROFILE)
    if profile not in NAVIGATION_PROFILES:raise ValueError('Unsupported navigation profile')
    from reviewed_scout_route import validate_reviewed_options
    reviewed=validate_reviewed_options(args)
    if reviewed is None and getattr(args,'hybrid_navigation',False) and required_profile(getattr(args,'hybrid_route',None) or COURTYARD_ROUTE)!=profile:
        raise ValueError('Fixed routes require their exact explicit navigation profile')
    if profile!=COURTYARD_PROFILE and not (getattr(args,'navigation_guidance',False) or getattr(args,'hybrid_navigation',False)):
        raise ValueError('A surface or scouting profile requires explicit native navigation guidance')
    return profile


def validate_execution_context_options(args):
    """Reject incompatible conditioning before loading weights or opening a pipe."""
    mode = getattr(args, 'execution_context', 'off')
    if mode not in ('off', 'record', 'model'):
        raise ValueError('execution-context must be off, record, or model')
    if mode == 'model' and (args.model != 'gamescaling'
            or args.history not in (None, 0) or args.gamescaling_prefix_cache):
        raise ValueError('execution-context model requires gamescaling, history 0, and no prefix cache')
    return mode


def validate_p2p_temperature_options(args):
    """Limit experimental sampling to P2P replay/shadow before model or pipe work."""
    temperature = getattr(args, 'p2p_temperature', 1.0)
    if type(temperature) not in (int, float) or not math.isfinite(temperature) or temperature <= 0:
        raise ValueError('p2p-temperature must be finite and positive')
    if temperature != 1.0 and args.model != 'open-p2p':
        raise ValueError('p2p-temperature requires open-p2p')
    if temperature != 1.0 and getattr(args, 'enable_input', False):
        raise ValueError('p2p-temperature overrides currently support replay and shadow runs only')
    return float(temperature)


def transmit_bound_action(bridge, warm, report, arguments, evidence_key, evidence):
    """Record an unknown outcome only after the local guards pass and immediately before the wire call."""
    if warm:
        warm.require_action_frame(arguments['frameId'])
        warm.require_batch_dispatch_window(arguments.get('startBeforeMs'))
    report[evidence_key] = evidence
    return bridge.request('action', **arguments)


def validate_navigation_climb_options(args):
    """Authorize only the explicit standard-channel P2P recovery combination."""
    if not getattr(args, 'navigation_climb_recovery', False):
        return
    if (not args.resident or args.model != 'open-p2p' or not args.enable_input
            or not args.p2p_fast_start or not args.p2p_execution_feedback):
        raise ValueError('navigation-climb-recovery requires resident Open P2P, input, fast-start, and feedback')
    if args.execution_context != 'off':
        raise ValueError('navigation-climb-recovery currently requires execution-context off')


def scout_release(bridge, guard, report, recorder, reason):
    """Serialize the native release and guard disarm with intake, retaining the exact acknowledgement."""
    with (guard.intake_lock if guard is not None else nullcontext()):
        reply,payload=bridge.request('release')
        if guard is not None:
            event=guard.acknowledge_release(reply,len(payload),time.perf_counter_ns(),reason)
            report['scoutEncounterGuardState']=event['state']
            if recorder:recorder.event(event)
        return reply,payload


def scout_dispatch(guard, report, recorder, frame, request_id):
    """Record the final source-bound gate for either a model/navigation action or an existing X recovery."""
    from scout_encounter_guard import sensor_frame
    marker=guard.check_dispatch(frame,time.perf_counter_ns())
    report['scoutEncounterGuardState']=guard.snapshot()
    if recorder:
        recorder.event(dict(type='scoutEncounterGuardDispatch',requestId=request_id,marker=copy.deepcopy(marker),
                            frame=sensor_frame(frame),state=report['scoutEncounterGuardState']))
    return marker


def validate_combat_trial_options(args, policy, control):
    """Keep the explicit single-lease combat authority separate from navigation and scout reuse."""
    binding = getattr(args, 'combat_trial_binding', None)
    if binding is None:
        if getattr(control, 'combat_trial_guard', None) is not None:
            raise ValueError('Combat trial authority cannot be removed or reused')
        return None
    from combat_trial_guard import validate_binding, canonical
    validate_binding(binding)
    if (control is None or getattr(control, 'frozen_goal', False) is not True
            or getattr(control, 'combat_trial_guard', None) is not None
            or getattr(control, 'scout_encounter_guard', None) is not None
            or policy is None or args.model != 'open-p2p' or not getattr(policy, 'execution_feedback', False)
            or getattr(policy, 'combat_trial_goal_sha256', None) != binding['goalSha256']
            or canonical(getattr(args, 'combat_trial_owner', None)) != canonical(binding['owner'])):
        raise ValueError('Combat trial requires its original frozen owner and separately loaded goal')
    forbidden = ('resident', 'lease_output', 'patrol_series_binding', 'scout_encounter_guard',
                 'combat_shadow', 'hybrid_navigation', 'hybrid_observe', 'navigation_guidance', 'navigation_progress',
                 'navigation_climb_recovery', 'navigation_idle_reset_seconds', 'warm_photo_plan',
                 'camera_calibration', 'steering_shadow', 'landmark_shadow', 'photo_station')
    if (any(getattr(args, key, None) for key in forbidden) or args.execution_context != 'off'
            or not args.enable_input or not args.native_combat_observation or not args.require_world_ready
            or args.observation_profile != P2P_NATIVE or args.input_keys != 'LBUTTON'
            or args.max_input_actions != 3 or not 0 < args.seconds <= 5
            or not 0 < args.max_observation_age_ms <= 150 or args.action_hold_ms != 100
            or not args.record_dir or not args.retain_policy_rgb or not 0 < args.record_max_mib <= 160
            or not args.p2p_execution_feedback or not args.p2p_prewarm or not args.soft_cadence):
        raise ValueError('Combat trial requires one recorded bounded pure-LBUTTON lease without other controllers')
    child = binding['owner']['child']
    if (getattr(args, 'expected_process_id', None) != child['processId']
            or getattr(args, 'expected_session_id', None) != child['windowsSessionId']
            or not args.goal_embedding
            or hashlib.sha256(Path(args.goal_embedding).read_bytes()).hexdigest() != binding['goalSha256']):
        raise ValueError('Combat trial child or goal file differs from its review')
    return copy.deepcopy(binding)


class CombatTrialRecorder:
    """Make any lost combat label or source pixels terminal instead of continuing inference."""

    def __init__(self, recorder):
        """Wrap only this explicit trial's existing bounded recorder."""
        self.recorder = recorder

    def __getattr__(self, name):
        """Keep the ordinary recorder's status and finalization interface intact."""
        return getattr(self.recorder, name)

    def _require_retention(self, result, label):
        """Treat asynchronous queue eviction as loss even before the recorder publishes an error."""
        losses = {name: getattr(self.recorder, name, 0) for name in
                  ('dropped', 'dropped_events', 'dropped_observations', 'abandoned_frames')}
        losses = {name: value for name, value in losses.items() if type(value) is not int or value != 0}
        if result is False or self.recorder.error or losses:
            raise RuntimeError('Combat trial ' + label + ' retention failed: ' + str(self.recorder.error)
                               + ('; counters=' + str(losses) if losses else ''))

    def event(self, item):
        """Reject failed or silently refused journal writes before another dispatch."""
        result = self.recorder.event(item)
        self._require_retention(result, 'journal')
        return result

    def put(self, metadata, pixels):
        """Require exact pixels as well as source metadata for every retained trial observation."""
        result = self.recorder.put(metadata, pixels)
        self._require_retention(result, 'RGB')
        return result


def combat_trial_release(bridge, guard, report, recorder, reason):
    """Serialize release/disarm with intake and retain the exact reply before journal failure."""
    from combat_trial_guard import retained
    with guard.intake_lock:
        reply, payload = bridge.request('release')
        now = time.perf_counter_ns()
        report.setdefault('combatTrialReleases', []).append(dict(response=retained(reply),
            payloadBytes=len(payload), clientTimeNs=now, reason=reason))
        event = guard.acknowledge_release(reply, len(payload), now, reason)
        report['combatTrialGuardState'] = event['state']
        if recorder:
            recorder.event(event)
        last = event['state']['lastRelease']
        if last is None or last['clientTimeNs'] != now:
            raise RuntimeError('Combat trial release was not acknowledged')
        return reply, payload


def close_combat_setup_failure(args, bridge, guard, report, recorder, error, reason):
    """Close every acquired resource before rethrowing the original pre-loop failure."""
    report['error'] = str(error)
    report['status'], report['endReason'] = 'failed', 'combatTrialSetupFailure'
    report['combatTrialGuardState'] = guard.fail(reason, time.perf_counter_ns(), error=str(error))['state']
    cleanup_errors = []

    def retain_cleanup(operation, failure):
        """Keep cleanup errors separate so they never replace the initiating exception."""
        cleanup_errors.append(dict(operation=operation, error=str(failure)))
        error.add_note('Combat trial ' + operation + ' cleanup failed: ' + str(failure))

    try:
        combat_trial_release(bridge, guard, report, None, reason)
    except Exception as failure:
        retain_cleanup('release', failure)
    if recorder is not None:
        try:
            report['recording'] = recorder.close()
            if report['recording'].get('error'):
                retain_cleanup('recorder', report['recording']['error'])
        except Exception as failure:
            retain_cleanup('recorder', failure)
    try:
        bridge.handle.close()
    except Exception as failure:
        retain_cleanup('bridge', failure)
    report['combatTrialGuardState'] = guard.snapshot()
    report['combatTrialCleanupErrors'] = cleanup_errors
    error.combat_trial_cleanup_errors = cleanup_errors
    try:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    except Exception as failure:
        retain_cleanup('report', failure)


class ClimbRecoveryStream:
    """Serial integration of pure recovery intents with the existing standard bridge.

    The caller holds its ingestion lock while tick runs. No model prediction or
    feedback commit occurs here. The capture worker only appends receipt facts.
    """
    def __init__(self, args, bridge, policy, control, report, recorder, *, collect, reset, clear, released,
                 drop_resumed=None):
        """Pin the owned connection and carry the resident's finite budget across clean leases."""
        from navigation_climb_recovery import NavigationClimbRecovery
        validate_navigation_climb_options(args)
        if not getattr(args, 'navigation_climb_recovery', False):
            raise RuntimeError('Climb recovery requires its explicit opt-in')
        if control is None or not policy.execution_feedback or not callable(getattr(policy, 'reset', None)):
            raise RuntimeError('Climb recovery requires a resident control and resettable feedback policy')
        previous = getattr(control, 'navigation_climb_recovery', None)
        if previous is not None and previous.blocks_model:
            raise RuntimeError('Previous climb recovery lease remains unresolved; reconnect refused')
        if getattr(bridge, '_step_application_intake', None) is not None:
            raise RuntimeError('Climb recovery requires the standard terminal-receipt channel')
        self.helper = NavigationClimbRecovery(bridge.hello, enabled=True, input_requested=args.enable_input,
            x_authorized=True, initial_attempts=previous.attempts if previous else 0,
            initial_cooldown_until_ns=previous.cooldown_until_ns if previous else 0)
        control.navigation_climb_recovery = self.helper
        self.bridge, self.handle, self.hello = bridge, bridge.handle, bridge.hello
        self.hello_value = copy.deepcopy(bridge.hello)
        self.control, self.report, self.recorder = control, report, recorder
        self.scout_guard = getattr(control,'scout_encounter_guard',None)
        self.collect, self.reset, self.clear, self.released = collect, reset, clear, released
        self.drop_resumed = drop_resumed
        self.warm = None
        self.token = None
        self.first_error = None
        self.cleanup_attempted = False
        report['navigationClimbRecoveryEvents'] = []
        report['navigationClimbActions'] = []
        self.publish()

    def context(self):
        """Sample the actual resident authority, without extending the model key allowlist."""
        return dict(sessionId=self.bridge.hello.get('sessionId'), ownerEpoch=self.bridge.hello.get('ownerEpoch'),
            controlToken=self.control.prediction_token(), goalIntent=self.control.goal_identity().get('goalIntent'),
            inputEnabled=self.bridge.hello.get('inputEnabled') is True, xAuthorized=True,
            standardChannel=getattr(self.bridge, '_step_application_intake', None) is None)

    def identity_matches(self):
        """A replaced public handle or hello cannot inherit this recovery authority."""
        return (self.bridge.handle is self.handle and self.bridge.hello is self.hello
                and self.bridge.hello == self.hello_value
                and getattr(self.bridge, '_step_application_intake', None) is None)

    def record(self, event):
        """Keep recovery evidence separate from decisions and sampled-history commits."""
        row = dict(event, type=event.get('type', 'navigationClimbRecovery'),
                   clientTimeNs=time.perf_counter_ns(), sessionId=self.hello_value['sessionId'],
                   ownerEpoch=self.hello_value['ownerEpoch'], modelHistoryCommitted=False)
        if self.warm:
            row['warmRequestId'] = self.warm.current['id']
        self.report['navigationClimbRecoveryEvents'].append(row)
        if self.recorder:
            self.recorder.event(row)

    def publish(self):
        """Replace a scalar snapshot so an earlier segment never shares mutable state."""
        state = dict(enabled=True, phase=self.helper.phase, attempts=self.helper.attempts,
                     maxAttempts=self.helper.max_attempts, cooldownUntilClientNs=self.helper.cooldown_until_ns,
                     blocksModel=self.helper.blocks_model, failure=self.helper.failure,
                     origin='navigation-climb-drop-v1', normalIsGroundedProof=False)
        self.report['navigationClimbRecovery'] = state
        self.control.publish(navigationClimbRecovery=state)

    def terminate(self, reason, error=None, *, cleanup_allowed=True):
        """Preserve first failure, attempt cleanup once, and return a non-reconnectable error."""
        if self.first_error is None:
            self.first_error = dict(reason=reason, errorType=type(error).__name__ if error else None,
                                    error=str(error) if error else None)
            self.report['navigationClimbFailure'] = self.first_error
        event = self.helper.fail(reason)
        try:
            self.record(event)
        except Exception as evidence_error:
            self.report.setdefault('navigationClimbEvidenceError', str(evidence_error))
        if not self.cleanup_attempted:
            self.cleanup_attempted = True
            try:
                if not cleanup_allowed:
                    raise RuntimeError('Reader did not retire; skip another pipe request and close the original handle')
                if not self.identity_matches():
                    raise RuntimeError('Original bridge changed; release not sent through substituted connection')
                reply, payload = scout_release(self.bridge,self.scout_guard,self.report,self.recorder,'climbFailureCleanup')
                self.collect(reply)
                if payload or reply.get('type') != 'released':
                    raise RuntimeError('Recovery cleanup release was not acknowledged')
                self.report['navigationClimbFailureCleanup'] = dict(released=True, response=copy.deepcopy(reply))
            except Exception as cleanup_error:
                self.report['navigationClimbFailureCleanup'] = dict(released=False,
                    errorType=type(cleanup_error).__name__, error=str(cleanup_error))
        self.publish()
        self.report.setdefault('error', 'Navigation climb recovery: ' + self.first_error['reason'])
        return RuntimeError(self.report['error'])

    def check_control(self):
        """Run before goal mutation or generic pause handling can release a pending X."""
        if self.scout_guard is not None and self.scout_guard.snapshot()['trip'] is not None:
            from scout_encounter_guard import ScoutEncounterStop
            raise ScoutEncounterStop('Scout encounter guard: '+self.scout_guard.snapshot()['trip']['reason'])
        if not self.identity_matches():
            raise self.terminate('connection_identity_changed')
        if self.helper.blocks_model and self.token is not None and self.control.prediction_token() != self.token:
            raise self.terminate('resident_control_changed')

    def execute(self, event, frame, status, status_received_ns):
        """Consume a bounded intent chain; only matching terminal completion releases X normally."""
        while event is not None:
            self.record(event)
            kind = event['kind']
            if kind == 'hold':
                raise self.terminate(event['reason'])
            self.check_control()
            if kind == 'release':
                reply, payload = scout_release(self.bridge,self.scout_guard,self.report,self.recorder,'climbRecovery')
                self.record(dict(kind='release_returned', origin=event['origin'], attempt=event['attempt'],
                                 response=copy.deepcopy(reply), payloadBytes=len(payload)))
                self.collect(reply)
                if payload:
                    raise RuntimeError('Unexpected release payload')
                event = self.helper.released(reply, self.context(), now_ns=time.perf_counter_ns())
                if event and event['kind'] == 'reset_history':
                    self.released(reply)
                continue
            if kind == 'reset_history':
                self.clear()
                self.reset()
                event = self.helper.history_reset_done(self.context(), now_ns=time.perf_counter_ns())
                if event is None:
                    self.record(dict(kind='history_reset_completed', origin='navigation-climb-drop-v1',
                                     attempt=self.helper.attempts))
                continue
            if kind == 'drop_ready':
                event = self.helper.claim_action(frame, status, self.context(), uuid.uuid4().hex,
                    status_received_ns=status_received_ns, now_ns=time.perf_counter_ns())
                continue
            if kind == 'action':
                arguments = event['arguments']
                guard_marker = None
                def submit_recovery():
                    """Only evidence retention and owned bridge I/O; never re-enter control methods."""
                    nonlocal guard_marker
                    with (self.scout_guard.intake_lock if self.scout_guard is not None else nullcontext()):
                        if self.scout_guard is not None:
                            guard_marker=scout_dispatch(self.scout_guard,self.report,self.recorder,frame,arguments['requestId'])
                        return transmit_bound_action(self.bridge, self.warm, self.report, arguments,
                                                     'unacknowledgedRecoveryAction', copy.deepcopy(arguments))
                # The monitor cannot change the token between this final check and the write.
                # Interpret/refuse/clean up only after the plain control lock is released.
                submitted, result = self.control.guarded_submit(self.token, submit_recovery)
                if not submitted:
                    self.record(dict(kind='submission_refused', origin=event['origin'], attempt=event['attempt'],
                                     requestId=arguments['requestId'], transmissionAttempted=False,
                                     reason='resident_control_changed_before_submit'))
                    raise self.terminate('resident_control_changed_before_submit')
                reply, payload = result
                next_event = self.helper.admitted(reply, self.context(), now_ns=time.perf_counter_ns(),
                                                 payload_bytes=len(payload))
                row = dict(type='navigationClimbAction', origin=event['origin'], attempt=event['attempt'],
                           frameId=arguments['frameId'], requestId=arguments['requestId'],
                           arguments=copy.deepcopy(arguments), acceptance=copy.deepcopy(reply),
                           controlToken=self.token, modelHistoryCommitted=False)
                if guard_marker is not None:row['scoutEncounterGuard']=guard_marker
                if self.warm:
                    row['warmRequestId'] = self.warm.current['id']
                    if reply.get('type') == 'accepted':
                        self.warm.accepted(arguments['requestId'], arguments['frameId'])
                self.report['navigationClimbActions'].append(row)
                self.record(row)
                # Record admission before consuming any terminal returned in the same reply.
                self.collect(reply)
                if next_event is None or next_event.get('reason') == 'drop_rejected':
                    self.report.pop('unacknowledgedRecoveryAction', None)
                event = next_event
                continue
            if kind == 'resume':
                self.token = None
                if self.drop_resumed and 'climbExit' in event:
                    self.drop_resumed(event['climbExit'])
            event = None

    def tick(self, frame, status, status_received_ns, receipts, dropped_receipts):
        """Process facts on the policy thread, heartbeat deadlines, and report whether to skip predict."""
        was_blocked = self.helper.blocks_model
        try:
            self.check_control()
            if self.scout_guard is not None and self.scout_guard.snapshot()['state']!='ready':
                # An explicit release may temporarily invalidate HUD recognition. Wait for
                # reconfirmation without consuming an X intent or extending any deadline.
                return True
            if dropped_receipts:
                raise self.terminate('receipt_loss')
            for receipt in receipts:
                self.execute(self.helper.receipt(receipt, self.context(), now_ns=time.perf_counter_ns(),
                    dropped_receipts=dropped_receipts), frame, status, status_received_ns)
            event = self.helper.observe(frame, status, self.context(), status_received_ns=status_received_ns,
                                        now_ns=time.perf_counter_ns())
            if self.helper.blocks_model and self.token is None:
                self.token = self.control.prediction_token()
            elif not self.helper.blocks_model:
                self.token = None  # A disproved initial hint must not pin an obsolete goal token.
            self.execute(event, frame, status, status_received_ns)
            self.publish()
            return was_blocked or self.helper.blocks_model or event is not None
        except Exception as error:
            raise self.terminate('recovery_failed', error) from error


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
    parser.add_argument('--execution-context', choices=('off', 'record', 'model'), default='off',
                        help='Record input reports known before each decision; model also supplies them to GameScaling')
    parser.add_argument('--p2p-fast-start', action='store_true',
                        help='Use masked empty fixed-capacity P2P history; requires --cuda-graph')
    parser.add_argument('--p2p-prewarm', action='store_true',
                        help='Prepare the P2P graph before connecting; requires cuda-graph and p2p-fast-start')
    parser.add_argument('--p2p-mouse-sampling', choices=['mean', 'conservative', 'truncated_normal'],
                        help='Override the P2P checkpoint mouse decoder; mean reproduces older comparisons')
    parser.add_argument('--p2p-temperature', type=float, default=1.0,
                        help='Experimental P2P temperature for shadow runs; live input keeps temperature 1')
    parser.add_argument('--p2p-execution-feedback', action='store_true',
                        help='Roll back rejected P2P predictions instead of storing unexecuted actions in history')
    parser.add_argument('--p2p-executed-history', action='store_true',
                        help='Opt in to serialized receipt-verified scout history with 50 or 60 ms holds')
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
    parser.add_argument('--retain-policy-rgb', action='store_true',
                        help='Retain exact RGB192 files on the recording worker, inside the existing byte budget')
    parser.add_argument('--combat-shadow', action='store_true',
                        help='Record read-only combat candidates beside GPU P2P predictions; input must remain disabled')
    parser.add_argument('--native-combat-observation', action='store_true',
                        help='Record optional same-source native HUD evidence; this never enables input')
    parser.add_argument('--preview', action='store_true',
                        help='Save latest.jpg once per second on the recording worker; requires record-dir')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--record-max-mib', type=int, default=1024)
    parser.add_argument('--resident', action='store_true',
                        help='Keep the model loaded across pauses, bridge reconnects, and child replacement')
    parser.add_argument('--rdp-session-id', type=int,
                        help='Required resident target; must equal this process actual RDP Windows session')
    parser.add_argument('--patrol-series-binding', help=argparse.SUPPRESS)
    parser.add_argument('--control-file', help='Resident pause/run/stop JSON command file; must not already exist')
    parser.add_argument('--segment-seconds', type=float, default=300,
                        help='Rotate resident evidence files without restarting a healthy bridge or policy history')
    parser.add_argument('--reconnect-timeout', type=float, default=90,
                        help='Maximum continuous time waiting for a usable RDP bridge')
    parser.add_argument('--require-world-ready', action='store_true',
                        help='Require the server game-world recognition capability; always enabled in resident mode')
    parser.add_argument('--navigation-progress', action='store_true',
                        help='Record minimap stall evidence against actual applied movement receipts')
    parser.add_argument('--navigation-guidance', action='store_true',
                        help='Opt in to same-frame, read-only native courtyard pose metadata')
    parser.add_argument('--navigation-profile',choices=NAVIGATION_PROFILES,default=COURTYARD_PROFILE,
                        help='Select an explicit localization scope; the original city profile remains the default')
    parser.add_argument('--hybrid-navigation', action='store_true',
                        help='Combine Open P2P with same-frame BetterGI guidance on a fixed route')
    parser.add_argument('--hybrid-observe', action='store_true',
                        help='Run the full hybrid loop with native input disabled for bounded qualification')
    parser.add_argument('--hybrid-route', choices=EXECUTABLE_ROUTE_IDS,
                        help='Choose a surveyed fixed route; defaults to the original courtyard segment')
    parser.add_argument('--reviewed-scout-route',metavar='JSON',
                        help='Explicit scout geometry; requires a reviewed cached-session request')
    parser.add_argument('--steering-shadow', metavar='CHECKPOINT',
                        help='Record a trained steering prediction after each hybrid decision has settled')
    parser.add_argument('--landmark-shadow', metavar='CHECKPOINT',
                        help='Identify verified patrol stations from unannotated RGB192 frames')
    parser.add_argument('--retain-station-rgb',action='store_true',
                        help='Retain original RGB at every fixed-patrol station in the bounded shadow journal')
    parser.add_argument('--photo-station', action='append', choices=PATROL_STATIONS, default=[],
                        help='Collect one source photo when the native station and its visual prediction agree')
    parser.add_argument('--photo-directory', help='Fresh directory for original station photos and their source IDs')
    parser.add_argument('--photo-qualification', help='Sealed observer qualification for the selected checkpoint')
    parser.add_argument('--warm-photo-plan', help='Two to four independently verified photo requests on the same native patrol lease')
    parser.add_argument('--inspect-junction-map', action='store_true', help='Require the fixed junction map operation before navigation')
    parser.add_argument('--recover-junction-map', action='store_true', help='Require a proven interrupted-map recovery before navigation')
    parser.add_argument('--warm-batch-count', type=int, help='Total addressed destination batches on this bounded lease (2 to 12)')
    parser.add_argument('--warm-open-queue', action='store_true', help='Treat the batch count as a ceiling; require an explicit released-boundary finish')
    parser.add_argument('--warm-endurance', action='store_true', help='Use the explicit 900-second, 40-batch, 256-leg open-queue profile')
    parser.add_argument('--camera-calibration', metavar='CHECKPOINT',
                        help='Trial a holdout-qualified camera response on the street patrol')
    parser.add_argument('--remember-hybrid-bypass', action='store_true',
                        help='Reuse a verified stair-post passage within the current controller lease')
    parser.add_argument('--hybrid-legs', type=int,
                        help='Stop after this many verified route legs; requires hybrid-navigation')
    parser.add_argument('--navigation-idle-reset-seconds', type=float,
                        help='Opt-in one-shot history reset after accepted navigation no-ops; disabled by default, trial value 8')
    parser.add_argument('--navigation-climb-recovery', action='store_true',
                        help='Opt-in bounded native climb-drop X recovery; resident P2P input only')
    parser.add_argument('--readiness-snapshots', action='store_true',
                        help='Opt into bounded native screenshots on visual readiness changes in the RDP BetterGI app')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    if args.reviewed_scout_route:
        if args.hybrid_route:parser.error('Choose either a fixed route or an explicit reviewed scout specification')
        from reviewed_scout_route import load_reviewed_route
        try:args.reviewed_scout_route=load_reviewed_route(args.reviewed_scout_route)
        except (ValueError,OSError) as error:parser.error(str(error))
        args.hybrid_route=args.reviewed_scout_route.route_id
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
    try:
        validate_execution_context_options(args)
    except ValueError as error:
        parser.error(str(error))
    if args.p2p_fast_start and (args.model != 'open-p2p' or not args.cuda_graph):
        parser.error('p2p-fast-start requires the open-p2p model and cuda-graph')
    try:
        validate_startup_options(args)
    except ValueError as error:
        parser.error(str(error))
    if args.p2p_mouse_sampling is not None and args.model != 'open-p2p':
        parser.error('p2p-mouse-sampling requires open-p2p')
    try:
        validate_p2p_temperature_options(args)
    except ValueError as error:
        parser.error(str(error))
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
    if args.patrol_series_binding is not None:
        from resident_runtime import parse_series_binding
        passive_pose = not args.enable_input and ((args.model == 'observe' and args.navigation_guidance)
                                                  or args.combat_shadow)
        bounded_extension = (args.hybrid_navigation and (args.hybrid_route in ROUTE_IDS or args.reviewed_scout_route is not None) and 1 <= args.hybrid_legs <= 4
                             and args.max_observation_age_ms <= 150 and args.action_hold_ms is not None
                             and args.action_hold_ms <= 100)
        if not (args.resident and (passive_pose or bounded_extension
                                  or args.hybrid_navigation and args.hybrid_route == STREET_PATROL_ROUTE)):
            parser.error('A series binding requires a resident street patrol, bounded declared route, or input-disabled pose observation')
        try:
            args.patrol_series_binding = parse_series_binding(args.patrol_series_binding)
        except ValueError as error:
            parser.error(str(error))
    if args.p2p_execution_feedback and (not args.p2p_fast_start or not args.enable_input):
        parser.error('p2p-execution-feedback requires p2p-fast-start and enable-input')
    if args.navigation_idle_reset_seconds is not None:
        if (not math.isfinite(args.navigation_idle_reset_seconds)
                or not 1 <= args.navigation_idle_reset_seconds <= 120):
            parser.error('navigation-idle-reset-seconds must be finite and between 1 and 120')
        if args.model != 'open-p2p' or not args.p2p_execution_feedback:
            parser.error('navigation-idle-reset-seconds requires Open P2P with input, fast-start, and execution feedback')
        args.require_world_ready = True
    try:
        validate_navigation_climb_options(args)
    except ValueError as error:
        parser.error(str(error))
    if args.fresh_frame_at_decision is None:
        args.fresh_frame_at_decision = args.resident
    if args.model != 'observe' and (not args.source or not args.checkpoint):
        parser.error('A real model source and checkpoint are required')
    if args.hybrid_legs is not None and (not args.hybrid_navigation or args.hybrid_legs <= 0):
        parser.error('hybrid-legs requires hybrid-navigation and a positive count')
    if args.hybrid_route is not None and not args.hybrid_navigation:
        parser.error('hybrid-route requires hybrid-navigation')
    if args.steering_shadow and not args.hybrid_navigation:
        parser.error('steering-shadow requires hybrid-navigation')
    if args.landmark_shadow and (not args.hybrid_navigation or args.hybrid_route != STREET_PATROL_ROUTE
                                 or args.observation_profile != P2P_NATIVE):
        parser.error('landmark-shadow requires the street patrol and native RGB192 input')
    if args.retain_station_rgb and (not args.landmark_shadow or not args.resident or not args.record_dir
            or args.warm_photo_plan or args.photo_station or not args.hybrid_legs or args.hybrid_legs%4
            or not 4 <= args.hybrid_legs <= 128):
        parser.error('retain-station-rgb requires a bounded, recorded fixed-circuit landmark shadow without photo tasks')
    if args.photo_station or args.photo_directory or args.photo_qualification or args.warm_photo_plan:
        if not ((bool(args.photo_station) != bool(args.warm_photo_plan)) and args.photo_directory and args.photo_qualification
                and args.landmark_shadow and args.resident and args.enable_input):
            parser.error('A photo survey requires named stations, fresh output, the qualified landmark observer and a live resident')
    if args.warm_photo_plan and (args.model != 'open-p2p' or not args.goal_embedding or not args.hybrid_legs
                                 or not args.p2p_execution_feedback or not args.record_dir):
        parser.error('Warm photos require the receipt-backed resident P2P policy, walking embedding and recorded leg budget')
    from destination_queue_limits import ENDURANCE, STANDARD
    queue_cap = ENDURANCE if args.warm_endurance else STANDARD
    if args.warm_endurance and not (args.warm_open_queue and args.warm_batch_count and args.warm_photo_plan):
        parser.error('Endurance requires a bounded open destination queue')
    if args.warm_photo_plan and (not args.patrol_series_binding or args.seconds > queue_cap.seconds or args.max_observation_age_ms > 150):
        parser.error(f'Warm photos require pinned patrol owners, a {queue_cap.seconds} second maximum and a 150 ms source-age ceiling')
    if args.inspect_junction_map or args.recover_junction_map:
        if not args.warm_photo_plan or not args.enable_input or (args.inspect_junction_map and args.recover_junction_map):
            parser.error('Map inspection requires one operation and an input-enabled warm destination plan')
        if args.warm_batch_count is not None and (args.recover_junction_map or not args.warm_open_queue):
            parser.error('Only a fresh map inspection may precede a bounded open destination queue')
    if args.warm_open_queue and args.warm_batch_count is None:
        parser.error('An open queue requires bounded warm destination batches')
    if args.warm_batch_count is not None and (not args.warm_photo_plan or not 2 <= args.warm_batch_count <= queue_cap.batches
                                             or not (2 if args.warm_open_queue else 2*args.warm_batch_count) <= args.hybrid_legs <= queue_cap.legs):
        parser.error(f'Warm batch count requires a bounded warm destination lease and at most {queue_cap.legs} total legs')
    if args.camera_calibration and (args.hybrid_route != STREET_PATROL_ROUTE or not args.enable_input
                                    or not args.resident or args.max_observation_age_ms != 150):
        parser.error('camera-calibration requires the resident live street patrol and its 150 ms input deadline')
    if args.remember_hybrid_bypass and args.hybrid_route != STAIR_POST_ROUTE:
        parser.error('remember-hybrid-bypass requires the surveyed stair-post hybrid route')
    if args.hybrid_navigation:
        if (not args.resident or args.model != 'open-p2p' or not (args.enable_input or args.hybrid_observe)
                or args.goal_intent != 'ground-navigation' or args.navigation_idle_reset_seconds is not None):
            parser.error('hybrid-navigation requires resident Open P2P input or hybrid-observe, ground-navigation intent, and no separate idle reset')
        args.navigation_guidance = True
        if args.input_keys is None:
            args.input_keys = 'W,A,S,D'
    try:validate_hybrid_observe_options(args)
    except ValueError as error:parser.error(str(error))
    try:validate_navigation_scope_options(args)
    except ValueError as error:parser.error(str(error))
    if args.retain_policy_rgb and (not args.record_dir or args.observation_profile != P2P_NATIVE or args.record_max_mib > 160):
        parser.error('Exact policy RGB requires a recording directory, native Hamming192, and at most 160 MiB')
    if args.combat_shadow:
        from combat_observer import validate_shadow_options
        try:validate_shadow_options(args)
        except ValueError as error:parser.error(str(error))
    from p2p_executed_history import validate_executed_history_options
    try:validate_executed_history_options(args)
    except ValueError as error:parser.error(str(error))
    return args


def observe_station(head, event, frame, pixels):
    """Join a visual hypothesis to the verified start or final stable arrival frame."""
    if event['type'] == 'hybridStartVerified':
        source_id = event['frameId']
    elif event['type'] in ('hybridEndpointVerified', 'hybridDestinationPhotoRetry'):
        source_id = event['samples'][-1]['frameId']
    else:
        return
    if frame is None or source_id != frame['frameId']:
        raise RuntimeError('Visual station check requires the exact verified source frame')
    started = time.perf_counter_ns()
    prediction = head.predict(pixels)
    elapsed_us = (time.perf_counter_ns() - started) / 1000
    event['visualStation'] = dict(checkpointId=head.checkpoint_id, frameId=source_id,
                                  prediction=prediction, elapsedUs=elapsed_us,
                                  rgbSha256=hashlib.sha256(pixels).hexdigest())


def open_queue_interruption(control, token):
    """Any interruption invalidates the issued queue, including a pause resumed before the next frame."""
    current = control.prediction_token()
    if current[3] == 'stop':
        return 'userStop'
    if current[3] == 'pause':
        return 'userPause'
    return 'openQueueAuthorityChanged' if current != token else None


def consume_queue_decision(warm, frame, control, token, maximum_age_ms):
    """Serialize open-queue admission against the original control generation, then recheck its disk command and RGB age."""
    if not warm.open_queue:
        return warm.consume_batch(frame['frameId'])
    from resident_runtime import read_control_document
    def still_current():
        document,error = read_control_document(control.path,control.run_id)
        return (not error and document.get('command') == 'run' and document.get('goalRequestId') == token[2]
                and fresh_frame(frame,time.perf_counter_ns(),maximum_age_ms))
    try:
        permitted,decision = control.guarded_submit(token,lambda:warm.consume_batch(frame['frameId'],still_current=still_current))
    except (ValueError,KeyError,TypeError,OSError):
        # A stop can reach disk while the bounded packet is being read or rejected.
        warm.check_batch_interruption()
        raise
    return decision if permitted else None


def record_open_queue_boundary_error(warm, error, native_failure, report, recorder):
    """Classify a released-boundary interruption without claiming a native stop acknowledgement."""
    if not warm or not warm.open_queue or warm.batch_boundary is None:
        return False
    from warm_photo_requests import WarmQueueInterrupted, WarmQueueStarved
    interruption = error if isinstance(error,WarmQueueInterrupted) else None
    if not interruption and (isinstance(error,WarmQueueStarved) or native_failure == 'destination_batch_deadline'):
        try:
            warm.check_batch_interruption()
        except WarmQueueInterrupted as command:
            interruption = command
        except ValueError as lost_control:
            report['openQueueControlError'] = str(lost_control)
            return False
        if not interruption:
            starved = warm.starved_event()
            report['hybridNavigationEvents'].append(starved)
            recorder.event(starved)
    if not interruption:
        return False
    proof = dict(runId=warm.identity['runId'],frameId=warm.batch_boundary[0]['frameId'],
                 source=interruption.source,reason=interruption.reason)
    report.update(endReason=interruption.reason,openQueueInterruption=proof)
    recorder.event(dict(type='openQueueOperatorInterruption',**proof))
    return True


def load_policy(args):
    """Load a real checkpoint once; a resident caller reuses this object for every episode."""
    validate_hybrid_observe_options(args)
    validate_navigation_scope_options(args)
    validate_execution_context_options(args)
    if getattr(args,'combat_shadow',False):
        from combat_observer import validate_shadow_options
        validate_shadow_options(args)
    prewarm = validate_startup_options(args)
    p2p_temperature = validate_p2p_temperature_options(args)
    warm_goal_sha = hashlib.sha256(Path(args.goal_embedding).read_bytes()).hexdigest() if getattr(args, 'warm_photo_plan', None) else None
    policy = None
    if args.model != 'observe':
        # Bind a photographic task to the exact observer bytes before allocating the GPU policy.
        landmark = None
        if getattr(args, 'landmark_shadow', None):
            from weighted_landmark_recognizer import load_landmark_shadow
            landmark = load_landmark_shadow(args.landmark_shadow)
            if getattr(args, 'photo_qualification', None):
                from patrol_photo_survey import require_qualified_observer
                require_qualified_observer(args.photo_qualification, landmark,execution_context=args)
        from model_adapters import make_adapter
        temperature_options = {}
        if p2p_temperature != 1.0:
            # Explicit overrides use a separate experimental adapter class.
            from p2p_sampling import make_adapter
            temperature_options['p2p_temperature'] = p2p_temperature
        policy = make_adapter(args.model, source=args.source, checkpoint=args.checkpoint,
                              cache_root=args.cache_root, history=args.history if args.history is not None else (0 if args.model == 'gamescaling' else 200),
                              image_width=args.image_width, max_new_tokens=args.max_new_tokens,
                              cuda_graph=args.cuda_graph, fast_start=args.p2p_fast_start,
                              p2p_mouse_sampling=args.p2p_mouse_sampling,
                              observation_profile=getattr(args, 'observation_profile', LEGACY),
                              execution_feedback=args.p2p_execution_feedback, goal_embedding=args.goal_embedding,
                              **({'executed_history': True} if getattr(args, 'p2p_executed_history', False) else {}),
                              instruction=args.instruction,
                              sampling=args.sampling, temperature=args.temperature,
                              top_k=args.top_k, top_p=args.top_p,
                              gamescaling_prefix_cache=args.gamescaling_prefix_cache, **temperature_options)
        if prewarm:
            from p2p_startup import prepare_startup_graph
            prepare_startup_graph(policy)
        if getattr(args, 'steering_shadow', None):
            from steering_head import SteeringHead
            policy.steering_shadow = SteeringHead.load(args.steering_shadow)
        if landmark is not None:
            prepare_observer=getattr(landmark,'prepare',None)
            if callable(prepare_observer):
                prepare_observer()
                policy.metadata['landmarkObserver']=copy.deepcopy(landmark.runtime_metadata)
                if getattr(landmark,'_scene_photo_admission',None):
                    policy.metadata['landmarkObserver'].update(authority='single-use-'+landmark._scene_photo_admission['scope'],
                        photoTrial=copy.deepcopy(landmark._scene_photo_admission))
            policy.landmark_shadow = landmark
            if warm_goal_sha:
                if (not policy.execution_feedback or not callable(getattr(policy, 'reset', None))
                        or Path(policy.metadata['goal']['file']).resolve() != Path(args.goal_embedding).resolve()
                        or hashlib.sha256(Path(args.goal_embedding).read_bytes()).hexdigest() != warm_goal_sha):
                    raise RuntimeError('Loaded warm policy must retain the same receipt-backed goal embedding')
                policy.warm_goal_sha = warm_goal_sha
        if getattr(args, 'camera_calibration', None):
            from camera_response import CameraCalibration
            policy.camera_calibration = CameraCalibration.load(args.camera_calibration)
    return policy


def action_response_accepted(response, request_id, payload=b''):
    """Settle only a matching server admission reply; acceptance is not execution."""
    if (not isinstance(response, dict) or type(request_id) is not str or not request_id
            or type(response.get('requestId')) is not str or response['requestId'] != request_id
            or response.get('type') not in ('accepted', 'rejected') or payload != b''):
        raise RuntimeError('Unresolved action response: expected matching accepted/rejected requestId and no payload')
    return response['type'] == 'accepted'


def run_episode(args, policy=None, control=None):
    """Run one owned bridge lease with an optional already-loaded model and live controls."""
    from p2p_executed_history import (MODE as EXECUTED_HISTORY_MODE, ExecutedHistoryRecorder,
        encode_controller_step, executed_history_policy, source_after_terminal, validate_executed_history_options)
    executed_history = validate_executed_history_options(args, policy, control, require_bound=True)
    combat_binding = validate_combat_trial_options(args, policy, control)
    combat_guard = None
    hybrid_observe = validate_hybrid_observe_options(args)
    navigation_profile = validate_navigation_scope_options(args)
    native_combat_enabled = getattr(args,'native_combat_observation',False)
    scout_guard = getattr(control,'scout_encounter_guard',None)
    if getattr(args,'scout_encounter_guard',None) is not None and scout_guard is None:
        raise ValueError('Scout encounter guard requires the reviewed resident owner')
    combat_observer = None
    if getattr(args,'combat_shadow',False):
        from combat_observer import CombatObserver,validate_shadow_options
        validate_shadow_options(args)
        combat_observer = CombatObserver()
    execution_mode = validate_execution_context_options(args)
    validate_navigation_climb_options(args)
    if policy is not None:
        from PIL import Image
    bridge = Bridge(args.pipe)
    try:
        if scout_guard is not None and (not native_combat_enabled or bridge.hello.get('supportsRelease') is not True):
            raise ValueError('Scout encounter guard requires native HUD evidence and acknowledged release')
        if hybrid_observe and bridge.hello.get('inputEnabled') is not False:
            raise ValueError('Hybrid observation requires input disabled at the native bridge as well')
        if combat_observer is not None and bridge.hello.get('inputEnabled') is not False:
            raise ValueError('Combat shadow requires input disabled at the native bridge as well')
        host_contract = HostObservationContract(bridge.hello, args.enable_input)
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
    if combat_binding is not None:
        try:
            from combat_trial_guard import CombatTrialGuard
            combat_guard = CombatTrialGuard(combat_binding, args.combat_trial_owner, bridge.hello, time.perf_counter_ns())
            control.combat_trial_guard = combat_guard
        except Exception:
            bridge.handle.close()
            raise
    if execution_mode != 'off':
        from execution_bridge import ExecutionContextBridge, decision_context
        try:
            bridge = ExecutionContextBridge(bridge)
        except Exception:
            bridge.handle.close()
            raise
    report = {'mode': 'live-bound-game-stream', 'hello': bridge.hello,
              'proposalJournal': {'version': 2, 'historyCommitMode': 'accepted-proposals-only'
                                  if getattr(policy, 'execution_feedback', False) else 'not-applicable'},
              'observationProfile': profile_contract['profile'], 'preprocessingContract': profile_contract,
              'inputRequested': args.enable_input, 'model': args.model, 'decisions': [], 'receipts': [], 'framesReceived': 0,
              'nativeInputEnabled': bridge.hello.get('inputEnabled'), 'hybridObservationOnly': hybrid_observe,
              'recordedExecutionContext': execution_mode != 'off',
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
    if executed_history:
        report.update(historyCommitMode=EXECUTED_HISTORY_MODE,
                      executedHistoryPolicy=executed_history_policy(args.action_hold_ms), executedHistoryEvents=[])
        report['proposalJournal'] = dict(version=3, historyCommitMode=EXECUTED_HISTORY_MODE)
    history_predecessor = None
    history_requests, history_receipts = {}, set()
    if getattr(args,'warm_endurance',False):
        from destination_queue_limits import ENDURANCE
        report['queueLimitsProfile'] = ENDURANCE.profile
    if combat_observer is not None:
        report['combatShadow'] = dict(inputAuthority=False,enemyRecognitionQualified=False,
                                    observer='coarse-red-bar-and-health-color-v1',goalEmbedding=args.goal_embedding)
    if scout_guard is not None:
        report['scoutEncounterGuard'] = copy.deepcopy(scout_guard.binding)
        report['scoutEncounterGuardState'] = scout_guard.snapshot()
    if combat_guard is not None:
        report['combatTrialGuard'] = combat_binding
        report['combatTrialGuardState'] = combat_guard.snapshot()
    if execution_mode != 'off':
        report['executionContext'] = {'mode': execution_mode, 'schema': 'execution-context-v1',
                                      'knowledgeClock': 'client_perf_counter_ns',
                                      'knowledgeStamp': 'serialized_intake_after_response_return',
                                      'sourceAgeBasis': 'server_reply_not_decision_or_game_render',
                                      'holdAndReleaseState': 'unknown_on_terminal_receipt_protocol',
                                      'inputAuthority': 'unchanged'}
    if host_contract.policy is not None:
        report['hostSourceContract'] = host_contract.describe()
        report['observationAgeClock'] = 'host_snapshot_started_qpc; not_game_render_time'
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
    climb = None
    hybrid = None
    terminal_climb_error = None
    recorder = None
    try:
        # Snapshot caller-owned metadata before creating recorder/encoder resources.
        if combat_guard is not None:
            report['policyMetadata'] = copy.deepcopy(policy.metadata) if policy else None
            report['initialGoalState'] = control.goal_state()
            report['residentRunId'] = control.run_id
        warm = None
        queue_control_token = None
        itinerary = {}
        if getattr(args, 'warm_photo_plan', None):
            from warm_photo_requests import WarmPhotoRequests
            warm = WarmPhotoRequests(args.warm_photo_plan, args.photo_directory, policy.landmark_shadow.checkpoint_id,
                                     args.goal_embedding, bridge.hello, control.run_id, args.hybrid_legs,
                                     batch_count=getattr(args, 'warm_batch_count', None),open_queue=getattr(args,'warm_open_queue',False),
                                     control_path=control.path if getattr(args,'warm_open_queue',False) else None,
                                     limits_profile=report.get('queueLimitsProfile'),observer=policy.landmark_shadow)
            if warm.open_queue:
                queue_control_token = control.prediction_token()
            if warm.identity['goalEmbeddingSha256'] != policy.warm_goal_sha:
                raise RuntimeError('Warm goal embedding changed since model load')
            if warm.destinations:
                itinerary = dict(itinerary_start=warm.itinerary_start, itinerary_destinations=warm.destinations,
                                 stationary_photo_retries=True)
        if getattr(args, 'navigation_guidance', False):
            from hybrid_navigation import HybridNavigation
            # Validate the advertised fixed geometry before enabling native recognition.
            route_id = getattr(args, 'hybrid_route', None) or COURTYARD_ROUTE
            validate_capability(bridge.hello.get('navigationGuidance') or {},COURTYARD_PROFILE)
            if navigation_profile!=COURTYARD_PROFILE and navigation_profile not in bridge.hello.get('navigationProfiles',[]):
                raise RuntimeError('The bridge does not support the requested outdoor localization scope')
            profile_request={} if navigation_profile==COURTYARD_PROFILE else dict(navigationProfile=navigation_profile)
            configured = bridge.request('enableNavigationGuidance',**profile_request)[0]
            if configured.get('type') != 'navigationGuidance' or configured.get('enabled') is not True:
                raise RuntimeError('The bridge did not acknowledge native navigation guidance')
            validate_capability(configured.get('capability') or {},navigation_profile)
            report['navigationGuidance'] = configured['capability']
            if getattr(args, 'hybrid_navigation', False):
                hybrid = HybridNavigation(configured['capability'], route_id,
                    remember_bypass=getattr(args, 'remember_hybrid_bypass', False),
                    **({'action_hold_ms': args.action_hold_ms} if executed_history else {}),
                    navigation_profile=navigation_profile, reviewed_scout_route=getattr(args,'reviewed_scout_route',None), **itinerary)
                report['hybridNavigation'] = hybrid.snapshot()
                report['hybridNavigationEvents'] = []
        if native_combat_enabled:
            from native_combat import negotiate
            report['nativeCombatObservation'] = negotiate(bridge)
            report['nativeCombatEvidenceFrames'] = 0
        if getattr(args, 'inspect_junction_map', False) or getattr(args,'recover_junction_map',False):
            from map_inspection_client import inspect_before_navigation
            if not warm or warm.itinerary_start != 'sidewalk-junction' or warm.destinations != ('west-lamp','sidewalk-junction'):
                raise ValueError('Map inspection requires the prescribed junction, west lamp and return route')
            report['mapInspection'] = inspect_before_navigation(bridge,args,policy,control,profile_contract)
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
        if executed_history and (not effective_keys or not effective_keys <= {'W', 'A', 'S', 'D'}):
            raise ValueError('Executed-history scout input remains limited to W/A/S/D')
        report['configuredInputKeys'] = configured_keys
        report['effectiveInputKeys'] = sorted(effective_keys)
        photo_survey = None
        if getattr(args, 'photo_station', None):
            from patrol_photo_survey import PatrolPhotoSurvey
            photo_survey = PatrolPhotoSurvey(Path(args.photo_directory), args.photo_station,
                                            policy.landmark_shadow.checkpoint_id)
        if getattr(args, 'navigation_climb_recovery', False):
            climb = ClimbRecoveryStream(args, bridge, policy, control, report, None,
                collect=lambda value: collect_receipts(value), reset=lambda: reset_for_climb(),
                clear=lambda: latest.clear(), released=lambda value: climb_released(value),
                drop_resumed=hybrid.latch_climb_exit if hybrid else None)
            climb.warm = warm
        archive = None
        if getattr(args, 'lease_output', None):
            from stream_segments import StreamSegments
            archive = StreamSegments(args, AsyncVideoRecorder, report)
            recorder = archive
        else:
            recorder = AsyncVideoRecorder(args.record_dir, args.ffmpeg, args.fps, args.record_max_mib*2**20,
                                          preview=args.preview, retain_policy_rgb=getattr(args,'retain_policy_rgb',False)) if args.record_dir else None
        if combat_guard is not None:
            recorder = CombatTrialRecorder(recorder)
        if executed_history:
            recorder = ExecutedHistoryRecorder(recorder)
        if climb:
            climb.recorder = recorder
    except Exception as error:
        if combat_guard is not None:
            close_combat_setup_failure(args, bridge, combat_guard, report, recorder, error, 'setupFailure')
        else:
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
    receipt_inbox = []
    report['decisionHz'] = args.decision_hz
    report['capturePollHz'] = args.fps
    report['maxObservationAgeMs'] = args.max_observation_age_ms
    # A later set_goal mutates adapter metadata; this episode's starting identity is immutable.
    if combat_guard is None:
        report['policyMetadata'] = copy.deepcopy(policy.metadata) if policy else None
        report['initialGoalState'] = control.goal_state() if control else None
        report['residentRunId'] = control.run_id if control else None
    report['serverDroppedReceipts'] = 0

    def record_initial_event(event):
        """Release an admitted combat lease even if its first journal write fails before reader setup."""
        try:
            recorder.event(event)
        except Exception as error:
            if combat_guard is not None:
                close_combat_setup_failure(args, bridge, combat_guard, report, recorder, error, 'recordingFailure')
            elif executed_history:
                # This happens before the ordinary episode finally owns cleanup.
                # Preserve the first error and always attempt release, encoder close and pipe close.
                report.update(error=str(error), endReason='executedHistorySetupFailure')
                cleanup = []
                for label, operation in (('release', lambda: bridge.request('release')),
                                         ('recorderClose', lambda: archive.finish(report) if archive else recorder.close()),
                                         ('pipeClose', bridge.handle.close)):
                    try:operation()
                    except Exception as failure:cleanup.append(dict(operation=label, error=str(failure)))
                if cleanup:error.add_note('Executed-history setup cleanup: ' + json.dumps(cleanup))
            raise

    if recorder:
        record_initial_event({'type': 'episodeStart', 'sessionId': bridge.hello['sessionId'],
                        **({'historyCommitMode': EXECUTED_HISTORY_MODE,
                            'executedHistoryPolicy': report['executedHistoryPolicy']} if executed_history else {}),
                        **({'combatTrialGuard': combat_binding} if combat_guard is not None else {}),
                        **({'hostSourceContract': report['hostSourceContract']} if host_contract.policy is not None else {}),
                        'proposalJournal': report['proposalJournal'],
                        'clock': bridge.hello.get('clock'), 'clockFrequency': bridge.hello.get('clockFrequency'),
                        'captureTimestampKind': bridge.hello.get('captureTimestampKind'),
                        'sourceFrameTiming': bridge.hello.get('sourceFrameTiming'),
                        'observationProfile': profile_contract['profile'], 'preprocessingContract': profile_contract,
                        'observationAgeClock': report['observationAgeClock'],
                        'firstInputDeadlinePolicy': report['firstInputDeadlinePolicy'],
                        'navigationIdleRecovery': report['navigationIdleRecovery'],
                        **({'navigationClimbRecovery': report['navigationClimbRecovery']} if climb else {}),
                        'motionEvidenceCapability': motion_capability,
                        'model': args.model, 'inputRequested': args.enable_input,
                        'configuredInputKeys': configured_keys, 'effectiveInputKeys': sorted(effective_keys),
                        'maxInputActions': args.max_input_actions,
                        'capturePollHz': args.fps, 'decisionHz': args.decision_hz,
                        'freshFrameAtDecision': args.fresh_frame_at_decision,
                        'frameQualityCheck': report['captureQuality']['check'],
                        'maxObservationAgeMs': args.max_observation_age_ms,
                        'policyMetadata': report['policyMetadata'], 'goalState': report['initialGoalState'],
                        **({'executionContext': report['executionContext']} if execution_mode != 'off' else {}),
                        'residentRunId': report['residentRunId']})

    def collect_receipts(metadata):
        nonlocal unapplied_receipt_sequence
        # No JSON serialization, flushing, or filesystem access occurs here.
        if combat_guard is not None and (metadata.get('receipts') or metadata.get('droppedReceipts', 0)):
            from combat_trial_guard import retained
            report.setdefault('combatTrialReceiptEnvelopes', []).append(retained({key: metadata.get(key)
                for key in ('type', 'serverNowMs', 'receipts', 'droppedReceipts')}))
        for receipt in metadata.get('receipts', []):
            report['receipts'].append(receipt)
            receipt_inbox.append(receipt)
            if executed_history:
                if recorder:recorder.event(receipt)
                identity = receipt.get('requestId') if isinstance(receipt, dict) else None
                if identity not in history_requests or identity in history_receipts:
                    raise RuntimeError('Executed-history receipt is unknown or duplicated')
                history_receipts.add(identity)
            if combat_guard is not None:
                event = combat_guard.receipt(receipt, time.perf_counter_ns())
                report['combatTrialGuardState'] = event['state']
                if recorder:
                    recorder.event(event)
            if archive and len(receipt_inbox) > 4096:
                raise RuntimeError('Policy receipt inbox overflow; execution feedback is incomplete')
            if progress:
                progress.receipt(receipt)
            if (getattr(policy, 'execution_feedback', False) and receipt.get('modelId') == args.model
                    and not receipt.get('appliedSteps')):
                unapplied_receipt_sequence += 1
                report['unappliedAcceptedActions'] += 1
            if recorder and not executed_history:
                recorder.event(receipt)
        dropped = metadata.get('droppedReceipts', 0)
        if dropped > report['serverDroppedReceipts']:
            report['serverDroppedReceipts'] = dropped
            if recorder:
                recorder.fail('Server dropped execution receipts; this episode has incomplete labels')
            if executed_history:
                raise RuntimeError('Executed-history terminal receipts were dropped')

    receive_lock = (combat_guard.intake_lock if combat_guard is not None else
                    scout_guard.intake_lock if scout_guard is not None else threading.Lock())
    received_frame_id = None
    recovery_capture_context = None

    def unapplied_history_receipts(items):
        """Classify exactly the receipt set that requires the existing policy-history reset."""
        return [item for item in items if getattr(policy, 'execution_feedback', False)
                and item.get('modelId') == args.model and not item.get('appliedSteps')]

    @contextmanager
    def combat_intake_boundary():
        """Latch and attempt release before a failed frame/journal operation drops the shared intake lock."""
        try:
            yield
        except Exception as error:
            if combat_guard is not None:
                stopped.set()
                report['combatTrialGuardState'] = combat_guard.fail('frameProcessingFailure', time.perf_counter_ns(), error=str(error))['state']
                report.setdefault('endReason', 'combatTrialGuard')
                try:
                    released, _ = combat_trial_release(bridge, combat_guard, report,
                        recorder if recorder and not recorder.error else None, 'combatTrialFailure')
                    collect_receipts(released)
                except Exception as release_error:
                    report['combatTrialReleaseError'] = str(release_error)
            elif executed_history:
                # Publish the terminal reader latch before dropping the intake lock.
                # A waiting inference must not dispatch in the reader's exception gap.
                stopped.set()
            raise

    def poll_frame():
        """Serialize frame ingestion so scheduled and just-in-time polls cannot reorder evidence."""
        nonlocal server_snapshot
        nonlocal received_frame_id
        nonlocal recovery_interruption_sequence
        nonlocal recovery_capture_context
        with receive_lock, combat_intake_boundary():
            start = time.perf_counter_ns()
            metadata, pixels = bridge.request('frame')
            arrived = time.perf_counter_ns()
            if combat_guard is not None:
                event = combat_guard.observe(metadata, arrived, round_trip_ms=(arrived-start)/1e6)
                report['combatTrialGuardState'] = event['state']
                trip = event['state']['trip']
                if trip:
                    # A hazard is never published to policy. Keep its original event and,
                    # where ordinary validations succeed, exact RGB before reader failure.
                    stopped.set()
                    report['endReason'] = 'combatTrialGuard'
                    try:
                        recorder.event(event)
                    except Exception as error:
                        report['combatTrialTriggerJournalError'] = str(error)
                    try:
                        host_contract.validate(metadata)
                        verify_frame(metadata, pixels, profile_contract)
                        from native_combat import validate_frame
                        validate_frame(metadata)
                        if len(pixels) != metadata['width'] * metadata['height'] * 3:
                            raise ValueError('Combat trigger RGB payload does not match declared dimensions')
                        metadata.update(clientReceivedNs=arrived, transportRoundTripMs=(arrived-start)/1e6,
                                        frameQuality=rgb_frame_quality(pixels))
                        report['captureQuality'][metadata['frameQuality'] + 'Frames'] += 1
                        report['framesReceived'] += 1
                        if metadata.get('combatEvidence') is not None:
                            report['nativeCombatEvidenceFrames'] += 1
                        report['combatTrialTriggerRecorded'] = bool(recorder.put(recording_frame_metadata(metadata, execution_mode), pixels))
                    except Exception as error:
                        report['combatTrialTriggerCaptureError'] = str(error)
                    try:
                        collect_receipts(metadata)
                    except Exception as error:
                        report['combatTrialTriggerReceiptError'] = str(error)
                    from combat_trial_guard import CombatTrialStop
                    raise CombatTrialStop('Combat trial stopped: ' + trip['reason'])
                recorder.event(event)
            if scout_guard is not None:
                guard_event = scout_guard.observe(metadata, arrived)
                report['scoutEncounterGuardState'] = guard_event['state']
                trip = guard_event['state']['trip']
                if trip:
                    # Latch and retain the original trigger before recorder, receipt or reader errors.
                    stopped.set()
                    report['endReason'] = 'scoutEncounterGuard'
                try:
                    if recorder:
                        recorder.event(guard_event)
                    if trip:
                        # Preserve exact hazardous pixels only after the ordinary host/profile/sensor
                        # checks. They enter evidence storage, never the policy's latest-frame slot.
                        try:
                            host_contract.validate(metadata)
                            verify_frame(metadata, pixels, profile_contract)
                            from native_combat import validate_frame
                            validate_frame(metadata)
                            if len(pixels) != metadata['width'] * metadata['height'] * 3:
                                raise ValueError('Trigger RGB payload does not match declared dimensions')
                            metadata['clientReceivedNs'] = arrived
                            metadata['transportRoundTripMs'] = (arrived-start)/1e6
                            metadata['frameQuality'] = rgb_frame_quality(pixels)
                            report['captureQuality'][metadata['frameQuality'] + 'Frames'] += 1
                            report['framesReceived'] += 1
                            if metadata.get('combatEvidence') is not None:
                                report['nativeCombatEvidenceFrames'] += 1
                            report['scoutEncounterGuardTriggerRecorded'] = bool(recorder and recorder.put(
                                recording_frame_metadata(metadata, execution_mode), pixels))
                        except Exception as error:
                            report['scoutEncounterGuardTriggerCaptureError'] = str(error)
                except Exception as error:
                    if not trip:raise
                    report['scoutEncounterGuardTriggerCaptureError'] = str(error)
                finally:
                    if trip:
                        try:
                            collect_receipts(metadata)
                        except Exception as error:
                            report['scoutEncounterGuardTriggerReceiptError'] = str(error)
                        try:
                            # This attempt is unconditional even if trigger retention or receipt intake failed.
                            released, payload = scout_release(bridge,scout_guard,report,recorder,'scoutEncounterGuard')
                            report['scoutEncounterGuardRelease'] = copy.deepcopy(released)
                            control.scout_encounter_guard_release = copy.deepcopy(released)
                            if released.get('type') != 'released' or payload:
                                raise RuntimeError('Scout encounter guard release was not acknowledged')
                            collect_receipts(released)
                        except Exception as error:
                            report['scoutEncounterGuardReleaseError'] = str(error)
                        from scout_encounter_guard import ScoutEncounterStop
                        raise ScoutEncounterStop('Scout encounter guard: '+trip['reason'])
            host_contract.validate(metadata)
            if metadata.get('type') == 'frame':
                verify_frame(metadata, pixels, profile_contract)
                if native_combat_enabled:
                    from native_combat import validate_frame
                    validate_frame(metadata)
            if idle_recovery.threshold is not None:
                context = capture_context(metadata) if metadata.get('type') == 'frame' else None
                if recovery_capture_context is not None and context != recovery_capture_context:
                    # Include cached payload replies: current readiness may close while frameId is unchanged.
                    recovery_interruption_sequence += 1
                recovery_capture_context = context
            server_snapshot = (time.perf_counter(), metadata)
            collect_receipts(metadata)
            if combat_guard is not None and combat_guard.snapshot()['trip'] is not None:
                from combat_trial_guard import CombatTrialStop
                raise CombatTrialStop('Combat trial receipt evidence failed')
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
                if native_combat_enabled and metadata.get('combatEvidence') is not None:
                    report['nativeCombatEvidenceFrames'] += 1
                latest.publish(metadata, pixels)
                if recorder:
                    # Proposal/receipt events and source/pose clocks remain complete.
                    # Full rolling context is retained only when explicitly requested.
                    recorder.put(recording_frame_metadata(metadata, execution_mode), pixels)
                received_frame_id = metadata['frameId']

    # Keep one actual reader failure; strings alone cannot authorize another lease.
    receive_failure = []

    def receive():
        capture_cadence = DecisionCadence(args.fps, time.perf_counter())
        try:
            while not stopped.is_set():
                if not sleep_until(capture_cadence.next_at, stopped):
                    break
                poll_frame()
                capture_cadence.advance(time.perf_counter())
        except Exception as exc:
            receive_failure.append(exc)
            report['streamError'] = str(exc)
            stopped.set()

    producer = threading.Thread(target=receive, daemon=True)
    try:
        producer.start()
    except Exception as error:
        if combat_guard is not None:
            close_combat_setup_failure(args, bridge, combat_guard, report, recorder, error, 'readerStartFailure')
        raise
    remaining = min(args.seconds, max(0, args.lease_deadline-time.monotonic())) if getattr(args, 'lease_deadline', None) else args.seconds
    deadline = time.perf_counter() + remaining
    cadence = DecisionCadence(args.decision_hz, time.perf_counter(), resume_immediately=args.soft_cadence)
    previous = None
    hold_reason = None
    last_readiness_epoch = None
    last_accepted_at = None
    last_hybrid_action = None
    camera_trial = None
    if getattr(args, 'camera_calibration', None):
        from patrol_camera_trial import PatrolCameraTrial
        camera_trial = PatrolCameraTrial(policy.camera_calibration)
    history_gap_reset = False
    seen_unapplied_receipts = 0
    seen_recovery_interruptions = 0
    recording_error_reported = False

    def finish_executed_feedback(result, frame, request, control_token):
        """Resolve one action before another prediction, retaining failures before retirement."""
        previous_receipt = (None if history_predecessor is None else
                            {key: history_predecessor[key] for key in ('requestId', 'endedAtMs')})
        event = dict(type='p2pExecutedHistory', version=1, historyCommitMode=EXECUTED_HISTORY_MODE,
            outcome='failed', requestId=request['requestId'] if request else None,
            frameId=frame['frameId'], modelId=result.get('hybridNavigation', {}).get('owner', args.model),
            sourceFrame=copy.deepcopy(frame['sourceFrame']), observationTimestampMs=observation_timestamp(frame),
            step=copy.deepcopy(result['steps'][0]), encodedAction=encode_controller_step(result['steps'][0]),
            arguments=copy.deepcopy(request), acceptance=copy.deepcopy(result['acceptance']), receipt=None,
            previousReceipt=previous_receipt, error=None)
        failure = None
        try:
            if result['acceptance']['type'] != 'accepted':
                policy.finish_action(False)
                event['outcome'] = 'rejected'
            else:
                started = time.perf_counter_ns()
                policy.prepare_executed_action(event['step'])
                event['candidatePreparationMs'] = (time.perf_counter_ns()-started)/1e6
                while True:
                    # The reader remains live during GPU work and receipt waiting.
                    # Its latched hazard, an operator stop, or any ownership change wins.
                    if stopped.is_set() or control.prediction_token() != control_token or control.snapshot()[0] != 'run':
                        raise RuntimeError('Executed-history action interrupted before its terminal proof')
                    if time.perf_counter() >= deadline:
                        raise RuntimeError('Executed-history lease ended before its terminal proof')
                    hybrid.check_leg_deadline()
                    recorder.check()
                    with receive_lock:
                        matches = [item for item in receipt_inbox if item.get('requestId') == request['requestId']]
                        if len(matches) > 1 or report['serverDroppedReceipts']:
                            raise RuntimeError('Executed-history terminal evidence is duplicated or incomplete')
                        if matches:
                            event['receipt'] = copy.deepcopy(matches[0])
                            policy.finish_executed_action(event['receipt'], request, result['acceptance'])
                            event['outcome'] = 'committed'
                            break
                        received_at, status = server_snapshot
                        server_now = status.get('serverNowMs')
                        if (type(server_now) not in (int, float) or not math.isfinite(server_now)
                                or server_now+(time.perf_counter()-received_at)*1000 >= request['expiresAtMs']):
                            raise RuntimeError('Executed-history receipt is unavailable before the original request deadline')
                    stopped.wait(.002)
        except Exception as error:
            failure, event['error'] = error, str(error)
            # Partial or unknown execution cannot preserve a counterfactual cache.
            policy.reset()
            forbid_reconnect(error, 'executedHistoryIncomplete')
        event['history'] = policy.executed_history_counters()
        event['clientTimeNs'] = time.perf_counter_ns()
        return event, failure

    def hold(reason, force_release=False, preserve_navigation=False):
        """Release once per interruption and clear stale context without unloading weights."""
        nonlocal hold_reason
        endpoint_reconfirmation = (hybrid is not None and hybrid.phase == 'verifying'
                                   and reason in ('worldTransition', 'client_release', 'world_confirming',
                                                  'world_observation_invalidated', 'payloadNotGameWorld'))
        if executed_history and reason != 'hybridEndpoint' and not endpoint_reconfirmation:
            raise RuntimeError('Executed-history interruption is terminal: ' + reason)
        if combat_guard is not None:
            from combat_trial_guard import CombatTrialStop
            report['combatTrialGuardState'] = combat_guard.fail('inputInterrupted', time.perf_counter_ns(), interruption=reason)['state']
            try:
                released, _ = combat_trial_release(bridge, combat_guard, report, recorder, reason)
                collect_receipts(released)
            finally:
                raise CombatTrialStop('Combat trial interrupted: ' + reason)
        idle_recovery.interrupt(reason)
        if hybrid and reason != 'hybridEndpoint' and not preserve_navigation:
            hybrid.interrupt(reason)
        released = None
        stale_replay = hybrid and hybrid.bypass and reason == 'hybridStalePose'
        if hold_reason is None or force_release:
            if force_release and not bridge.hello.get('supportsRelease'):
                raise RuntimeError('Live goal switching requires acknowledged bridge input release')
            if bridge.hello.get('supportsRelease'):
                # The frame reader may already have taken the last terminal off
                # the bridge after this tick drained its inbox. Pin that inbox
                # and the actual release reply to the same ingestion boundary.
                with (receive_lock if stale_replay else nullcontext()):
                    if stale_replay:
                        pending_count = len(receipt_inbox)
                        pending_hybrid_receipts = receipt_inbox[:] if pending_count <= 12 else []
                    released = scout_release(bridge,scout_guard,report,recorder,reason)[0]
                    if released.get('type') != 'released':
                        raise RuntimeError('The bridge did not acknowledge input release')
                    collect_receipts(released)
                    if stale_replay:
                        if pending_count > 12 or report['serverDroppedReceipts']:
                            hybrid.bypass.invalidate(hybrid, 'staleHoldReceiptContinuityLost')
                        else:
                            # Hybrid receipt IDs are idempotent. Leave the inbox
                            # intact for the normal history, climb and idle owners.
                            for receipt in pending_hybrid_receipts:
                                hybrid.receipt(receipt)
                            hybrid.bypass.acknowledge_stale_hold(hybrid, released, last_hybrid_action)
            if policy is not None and hasattr(policy, 'reset'):
                policy.reset()
            if progress:
                progress.reset()
            transition = {'type': 'controlTransition', 'state': 'held', 'reason': reason,
                          'clientTimeNs': time.perf_counter_ns(), 'frameId': previous}
            if warm:
                transition['warmRequestId'] = warm.current['id']
                if reason == 'hybridEndpoint':
                    transition['warmRelease'] = warm.released(previous, released)
                    if warm.destinations and released['worldReadiness']['reason'] == 'world_observation_invalidated':
                        from hybrid_navigation import rejected_release_record
                        transition.update(rejected_release_record(released))
            if stale_replay and released:
                # Keep the exact release barrier and terminal identities so a
                # later route audit can verify the gap during re-localization.
                transition['release'] = dict(serverNowMs=released['serverNowMs'],
                    worldReadiness=copy.deepcopy(released['worldReadiness']), inputAvailable=released.get('inputAvailable'),
                    receiptIds=[r['requestId'] for r in released.get('receipts', [])],
                    priorInboxReceiptCount=pending_count, priorInboxReceiptIds=[r['requestId'] for r in pending_hybrid_receipts],
                    lastAcceptedAction=copy.deepcopy(last_hybrid_action))
            report['controlTransitions'].append(transition)
            if recorder:
                recorder.event(transition)
        hold_reason = reason
        if control:
            control.publish(state='paused' if reason in ('userPause', 'controlError', 'goalChange', 'goalChangeFailed')
                            else 'waitingForWorld', reason=reason,
                            framesReceived=report['framesReceived'], acceptedInputActions=report['acceptedInputActions'])
        return released

    def publish_hybrid(station_frame=None, station_pixels=None):
        """Keep sparse native verification and selected-controller attribution in each evidence segment."""
        if hybrid is None:
            return
        endpoint = None
        for event in hybrid.drain_events():
            if warm:
                event['warmRequestId'] = warm.current['id']
            if getattr(args, 'landmark_shadow', None):
                observe_station(policy.landmark_shadow, event, station_frame, station_pixels)
                survey = warm.survey if warm else photo_survey
                if survey and 'visualStation' in event:
                    retain_miss = bool(warm and warm.destinations and event.get('station') == warm.current['destination']
                                       and event['type'] in ('hybridEndpointVerified', 'hybridDestinationPhotoRetry'))
                    visit = survey.observe(event, station_frame, station_pixels, retain_miss=retain_miss,
                                           confirm_only=retain_miss and warm.needs_first_view)
                    if visit is not None:
                        event['photoSurveyVisit'] = visit
                    report['stationPhotoSurvey'] = survey.snapshot()
            report['hybridNavigationEvents'].append(event)
            if recorder:
                recorder.event(event)
                if getattr(args,'retain_station_rgb',False) and event['type'] in ('hybridStartVerified','hybridEndpointVerified'):
                    from landmark_shadow_sources import retain
                    retain(recorder,event,station_frame,station_pixels,control.run_id,bridge.hello,
                           args.expected_process_id,args.expected_session_id)
            if warm:
                if event['type'] == 'hybridEndpointVerified':
                    endpoint = event
                transitions = warm.after_native(event, endpoint, received_ns=(station_frame or {}).get('clientReceivedNs'))
                if warm.destinations and event['type'] in ('hybridDestinationVerified', 'hybridDestinationPhotoRetry'):
                    if warm.retry_endpoint is not None:
                        hybrid.retry_destination_photo()
                    else:
                        hybrid.finish_destination_photo(await_batch=warm.batch_boundary is not None)
                for transition in transitions:
                    report['hybridNavigationEvents'].append(transition)
                    recorder.event(transition)
        report['hybridNavigation'] = hybrid.snapshot()
        if control:
            control.publish(hybridNavigation=report['hybridNavigation'])

    def admit_successor(frame):
        """Poll only after native validation of the released station. The next frame starts any new action."""
        batch = consume_queue_decision(warm,frame,control,queue_control_token,args.max_observation_age_ms)
        if batch:
            destinations, transitions = batch
            if destinations is None:
                hybrid.finish_destination_queue()
            else:
                hybrid.append_destination_batch(destinations)
            for row in transitions:
                report['hybridNavigationEvents'].append(row)
                recorder.event(row)
            report['hybridNavigation'] = hybrid.snapshot()
            control.publish(hybridNavigation=report['hybridNavigation'])

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
            released = scout_release(bridge,scout_guard,report,recorder,'navigationIdleRecovery')[0]
            collect_receipts(released)
            server_snapshot = (time.perf_counter(), released)
            return released

    def reset_for_recovery():
        """Clear only policy temporal history; adapter reset retains loaded weights and graph storage."""
        policy.reset()
        if progress:
            progress.reset()

    def climb_released(value):
        """Own release epochs must not trigger a second generic release during X recovery."""
        nonlocal server_snapshot, last_readiness_epoch
        server_snapshot = (time.perf_counter(), value)
        last_readiness_epoch = value['worldReadiness']['epoch']

    def reset_for_climb():
        """Reset settled history once per acknowledged recovery release, retaining loaded weights."""
        nonlocal seen_unapplied_receipts, last_accepted_at, history_gap_reset, hold_reason
        reset_for_recovery()
        seen_unapplied_receipts = unapplied_receipt_sequence
        last_accepted_at, history_gap_reset = None, False
        hold_reason = 'navigationClimbRecovery'
        idle_recovery.interrupt('navigationClimbRecovery')

    def latest_recovery_eligible(now_ns):
        """Observe current pixels independently of an older prediction's timing failure."""
        status_received_at, status = server_snapshot
        item = latest.newer_than(None)
        return (recovery_interruption_sequence == seen_recovery_interruptions and item is not None
                and eligible_frame(item[0], status, status_received_at, now_ns,
                                   args.max_observation_age_ms, motion_capability))

    episode_failure = None
    stop_failure = None
    try:
        while time.perf_counter() < deadline and not stopped.is_set():
            if executed_history:
                recorder.check()
            if recorder and recorder.error and not recording_error_reported:
                if combat_guard is not None:
                    raise RuntimeError('Combat trial recording failed: ' + str(recorder.error))
                print(json.dumps({'recordingError': recorder.error, 'inferenceContinues': True}), file=sys.stderr, flush=True)
                recording_error_reported = True
            if not sleep_until(min(cadence.next_at, deadline), stopped) or time.perf_counter() >= deadline:
                break
            if archive and archive.due(time.perf_counter()):
                # File boundaries never release input, reconnect, clear latest pixels,
                # reset temporal history or change the serial controller's counters.
                with receive_lock:
                    report['finalPolicyMetadata'] = copy.deepcopy(policy.metadata) if policy else None
                    report['finalGoalState'] = control.goal_state() if control else None
                    archive.rotate(report, time.perf_counter())
                if control:
                    control.publish(segment=archive.number)
            if climb:
                # A pending recovery is terminally interrupted before goal/pause code can release it.
                with receive_lock:
                    climb.check_control()
            # Goal mutation stays on this thread, after the old action transaction has ended.
            # The monitor already invalidated its epoch, so no old-goal result can be reused.
            if control:
                from resident_runtime import apply_pending_goal
                def release_for_goal_change():
                    """Keep the warm plan bound to its original instruction through completion or operator stop."""
                    hold('goalChange', force_release=True)
                    if warm:
                        raise RuntimeError('External goal change interrupted the warm photo plan')
                change = apply_pending_goal(control, policy, release_for_goal_change)
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
            if combat_guard is not None and command != 'run':
                report['endReason'] = 'userStop' if command == 'stop' else 'userPause'
                report['combatTrialGuardState'] = combat_guard.fail(report['endReason'], time.perf_counter_ns(), controlError=control_error)['state']
                break
            goal_state = control.goal_identity() if control else {
                'policyGoalVersion': 0, 'appliedGoalRequestId': None,
                'goalIntent': getattr(args, 'goal_intent', 'unspecified')}
            idle_recovery.set_goal(goal_state['policyGoalVersion'], goal_state['appliedGoalRequestId'],
                                   goal_state.get('goalIntent', 'unspecified'))
            # Capture appends receipts, but only this serial thread mutates recovery state.
            with receive_lock:
                pending_receipts = receipt_inbox[:]
                receipt_inbox.clear()
                observed_receipt_sequence = unapplied_receipt_sequence
            # Inspect before receipt() retires the bounded accepted-noop identity ledger.
            noop_history_reset = idle_recovery.matched_noop_expiries(unapplied_history_receipts(pending_receipts))
            for receipt in pending_receipts:
                if warm:
                    warm.receipt(receipt)
                recovery_event(idle_recovery.receipt(receipt))
                if camera_trial:
                    camera_trial.receipt(receipt)
                if hybrid:
                    hybrid.receipt(receipt)
            if recovery_interruption_sequence != seen_recovery_interruptions:
                idle_recovery.interrupt('ineligibleCapture')
                seen_recovery_interruptions = recovery_interruption_sequence
            if command == 'stop':
                report['endReason'] = 'userStop'
                break
            # This must precede every early continue, including waits without a usable source frame.
            if hybrid:
                hybrid.check_leg_deadline()
            if warm and warm.open_queue:
                interrupted = open_queue_interruption(control,queue_control_token)
                if interrupted:
                    report['endReason'] = interrupted
                    break
            awaiting_photo = bool(warm and warm.retry_endpoint is not None)
            if awaiting_photo:
                warm.check_photo_deadline()
            awaiting_batch = bool(warm and warm.batch_boundary is not None)
            if awaiting_batch:
                warm.check_batch_deadline()
            awaiting_release_retry = bool(hybrid and hybrid.phase == 'awaitingEndpointReleaseRetry')
            if awaiting_release_retry:
                hybrid.check_release_retry_time()
            if command == 'pause':
                hold('goalChangeFailed' if control and control.goal_state()['goalError'] else
                     'controlError' if control_error else 'userPause')
                cadence.advance(time.perf_counter())
                continue
            if hybrid and goal_state.get('goalIntent') != 'ground-navigation':
                hold('hybridGoalIntentChanged')
                cadence.advance(time.perf_counter())
                continue
            # Control and goal changes are settled before selecting the next world observation.
            if observed_receipt_sequence != seen_unapplied_receipts and not (climb and climb.helper.blocks_model):
                if executed_history:
                    raise RuntimeError('Executed-history unapplied receipt cannot resume with empty history')
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
            if scout_guard is not None and scout_guard.snapshot()['state']!='ready':
                # Released/startup sensor gaps wait before either recovery or world-transition
                # handling. A newer terminal trip is still checked by each dispatch boundary.
                cadence.advance(time.perf_counter())
                continue
            if combat_guard is not None:
                with receive_lock:
                    state = combat_guard.tick(time.perf_counter_ns())
                    report['combatTrialGuardState'] = state
                    if state['trip'] is not None:
                        from combat_trial_guard import CombatTrialStop
                        raise CombatTrialStop('Combat trial stopped: ' + state['trip']['reason'])
                    if state['trialComplete']:
                        report['endReason'] = 'combatTrialComplete'
                        break
                    if state['phase'] == 'awaitingRelease':
                        released, _ = combat_trial_release(bridge, combat_guard, report, recorder, 'completedCombatPulse')
                        collect_receipts(released)
                        last_readiness_epoch = released['worldReadiness']['epoch']
                        latest.clear()
                        state = combat_guard.snapshot()
                    if state['phase'] != 'ready' or not state['evidenceReady']:
                        # No inference, superseding action, generic release or automatic resume
                        # can overtake the owned terminal receipt and post-release source barrier.
                        cadence.advance(time.perf_counter())
                        continue
            # Keep observing while the admitted first successor action produces its original terminal receipt.
            awaiting_dispatch = warm and warm.awaiting_batch_dispatch_receipt(server_snapshot[1].get('serverNowMs'))
            if climb and not awaiting_dispatch and not awaiting_photo and not awaiting_batch and not awaiting_release_retry:
                with receive_lock:
                    received_at, current_status = server_snapshot
                    item = latest.newer_than(None)
                    consumed = climb.tick(item[0] if item else None, current_status, round(received_at*1e9),
                                          pending_receipts, report['serverDroppedReceipts'])
                if consumed:
                    # Includes release reconfirmation and pending X; do not call generic hold().
                    if hybrid:
                        hybrid.interrupt('climbRecovery')
                    cadence.advance(time.perf_counter())
                    continue
            received_at, current_status = server_snapshot
            if capability.get('requiredForInput') and current_status:
                gate = current_status.get('worldReadiness', {})
                epoch = gate.get('epoch')
                changed = last_readiness_epoch is not None and epoch != last_readiness_epoch
                last_readiness_epoch = epoch
                status_fresh = time.perf_counter()-received_at <= .25
                if changed or gate.get('ready') is not True or current_status.get('inputAvailable') is not True or not status_fresh:
                    if (awaiting_release_retry and status_fresh and current_status.get('inputAvailable') is True
                            and hybrid.permit_release_reconfirmation(gate)):
                        if gate.get('ready') is not True:
                            cadence.advance(time.perf_counter())
                            continue
                    else:
                        own_release = (status_fresh and hybrid and hybrid.bypass
                                       and hybrid.bypass.release_wait(hybrid, current_status, 'worldReadiness'))
                        hold('worldTransition' if changed else gate.get('reason', 'worldNotReady'),
                             preserve_navigation=own_release)
                        cadence.advance(time.perf_counter())
                        continue
            item = latest.newer_than(previous)
            if item is None:
                cadence.advance(time.perf_counter())
                continue
            frame, pixels = item
            selected_at = time.perf_counter_ns()
            previous = frame['frameId']
            if executed_history and not source_after_terminal(frame, observation_timestamp(frame), history_predecessor):
                cadence.advance(time.perf_counter())
                continue
            if scout_guard is not None and scout_guard.snapshot()['state']!='ready':
                # Startup pending/unavailable sensors do not enter model history or acquire input.
                cadence.advance(time.perf_counter())
                continue
            # Preserve blank captures as evidence but never feed them into policy history.
            # A later usable frame resumes inference normally after a loading fade.
            if frame['frameQuality'] != 'usable':
                hold('blankCapture')
                cadence.advance(time.perf_counter())
                continue
            if capability.get('requiredForInput') and frame.get('frameWorldReadiness', {}).get('ready') is not True:
                if (awaiting_release_retry and frame.get('inputAvailable') is True
                        and hybrid.permit_release_reconfirmation(frame['frameWorldReadiness'])):
                    cadence.advance(time.perf_counter())
                    continue
                own_release = hybrid and hybrid.bypass and hybrid.bypass.release_wait(hybrid, frame, 'frameWorldReadiness')
                hold('payloadNotGameWorld', preserve_navigation=own_release)
                cadence.advance(time.perf_counter())
                continue
            if awaiting_dispatch:
                cadence.advance(time.perf_counter())
                continue
            if not idle_recovery.allows_frame(frame, current_status,
                    fresh=fresh_frame(frame, time.perf_counter_ns(), args.max_observation_age_ms)
                    if idle_recovery.barrier is not None else True):
                cadence.advance(time.perf_counter())
                continue
            if hybrid:
                if not fresh_frame(frame, time.perf_counter_ns(), args.max_observation_age_ms):
                    hold('hybridStalePose')
                    cadence.advance(time.perf_counter())
                    continue
                hybrid_wait = hybrid.prepare(frame)
                if hybrid_wait == 'releaseRequired':
                    hybrid.released(hold('hybridEndpoint', force_release=True))
                elif hybrid_wait == 'retryReleaseRequired':
                    # Journal the exact post-refusal pose samples before recording the reissued native release.
                    publish_hybrid(frame, pixels)
                    hybrid.released(hold('hybridEndpoint', force_release=True))
                elif executed_history and hybrid_wait in ('confirmingStart', 'duplicatePose', 'sourceNotIncreasing'):
                    # These are read-only sampling waits. There is no pending action
                    # and no reason to erase settled visual/action history.
                    pass
                elif hybrid_wait not in (None, 'endpointVerified', 'verifyingEndpoint', 'waitingAfterRelease',
                                         'waitingAfterClimbResume', 'confirmingBypassReentry',
                                         'waitingForDestinationPhoto', 'destinationPhotoRetry', 'batchEndpointStillVerified',
                                         'waitingForEndpointReleaseRetry'):
                    # Stable-start sampling and duplicate source frames are waits,
                    # not interruptions of the navigation evidence being gathered.
                    hold('hybrid:' + hybrid_wait, preserve_navigation=hybrid_wait in (
                        'confirmingStart', 'duplicatePose', 'sourceNotIncreasing'))
                publish_hybrid(frame, pixels)
                if (warm and warm.batch_boundary is not None
                        and hybrid_wait in ('endpointVerified','destinationPhotoRetry','batchEndpointStillVerified')):
                    admit_successor(frame)
                if (warm and warm.batch_count and warm.finished
                        or args.hybrid_legs is not None and hybrid.legs >= args.hybrid_legs
                        and not (warm and (warm.retry_endpoint is not None or warm.open_queue and warm.batch_boundary is not None))):
                    if warm and not warm.finished:
                        raise RuntimeError('Native route ended with an unfinished warm request')
                    report['endReason'] = 'destinationQueueFinished' if warm and warm.open_queue else 'hybridLegLimit'
                    break
                if hybrid_wait is not None:
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
                if executed_history:
                    raise RuntimeError('Executed-history acceptance gap cannot resume with empty history')
                policy.reset()
                idle_recovery.interrupt('acceptanceGapHistoryReset')
                history_gap_reset = True
            image = Image.frombytes('RGB', (frame['width'], frame['height']), pixels)
            if progress:
                # Progress is diagnostic only; restore HUD geometry without changing policy pixels.
                metric = progress.observe(image, frame['capturedAtMs'],
                    observation_profile=profile_contract['profile'],
                    source_size=(frame.get('sourceWidth'), frame.get('sourceHeight'))
                    if profile_contract['profile'] == P2P_NATIVE else None)
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
            combat_result = None
            if combat_observer is not None:
                combat_started = time.perf_counter_ns()
                combat_result = combat_observer.observe(frame,pixels)
                combat_result.update(frameId=frame['frameId'],sourceFrame=copy.deepcopy(frame.get('sourceFrame')),
                    sourceRgbSha256=hashlib.sha256(pixels).hexdigest(),observerMs=(time.perf_counter_ns()-combat_started)/1e6,
                    frameWorldReady=(frame.get('frameWorldReadiness') or {}).get('ready') is True,
                    currentWorldReady=(frame.get('worldReadiness') or {}).get('ready') is True)
            predict_started = time.perf_counter_ns()
            profile_argument = {'observation_profile': P2P_NATIVE} if profile_contract['profile'] == P2P_NATIVE else {}
            execution_snapshot = None
            if execution_mode != 'off':
                execution_snapshot = bridge.snapshot(frame, decision_context=decision_context(frame, control_token))
                if execution_mode == 'model':
                    profile_argument['execution_context'] = execution_snapshot
            result = policy.predict(image, (frame['sourceWidth'], frame['sourceHeight']), **profile_argument)
            if combat_result is not None:result['combatObservation'] = combat_result
            if native_combat_enabled:result['nativeCombatEvidence'] = frame.get('combatEvidence')
            if execution_snapshot is not None:
                result['executionContext'] = execution_snapshot.to_dict()
                result['executionContextMode'] = execution_mode
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
            if warm:
                result['warmRequestId'] = warm.current['id']
            if args.action_hold_ms is not None and result.get('parseValid') and len(result.get('steps', [])) == 1:
                result['rawPolicySteps'] = [dict(step) for step in result['steps']]
                result['steps'] = [dict(result['steps'][0], durationMs=args.action_hold_ms)]
                result['controllerResampling'] = 'explicit-bounded-key-hold; mouse applied once'
            action_model_id = args.model
            if hybrid:
                selection = hybrid.choose(frame, result)
                if camera_trial:
                    started = time.perf_counter_ns()
                    candidate = camera_trial.propose(selection, hybrid.target, observed_at)
                    if candidate:
                        candidate['elapsedUs'] = (time.perf_counter_ns() - started) / 1000
                        result['cameraCalibration'] = candidate
                        hybrid.selections[selection['reason']] -= 1
                        selection.update(owner='calibrated-camera', reason='calibratedHeading',
                                         step=dict(selection['step'], mouseDx=candidate['proposedMouseDx']))
                        hybrid.selections[selection['reason']] += 1
                result['hybridNavigation'] = selection
                result['steps'] = [selection['step']]
                result['parseValid'] = True
                result['controllerResampling'] = 'explicit-hybrid-selection; original modelSteps retained'
                action_model_id = selection['owner']
                publish_hybrid()
            if executed_history:
                # Validate before input; unsupported fields never get silently dropped by the codec.
                encode_controller_step(result['steps'][0])
                result['executedHistoryPredecessor'] = (None if history_predecessor is None else
                    {key: history_predecessor[key] for key in ('requestId', 'endedAtMs')})
            executed_request = None
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
            if hybrid and newest and not hybrid.latest_pose_usable(newest[0]):
                rejection = 'latestNavigationPoseUnavailable'
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
            # Hybrid corrections are explicitly attributed above; ordinary proposals remain unchanged.
            if rejection is None:
                start_deadline = {'startBeforeMs': observed_at+args.max_observation_age_ms} if supports_start_deadline else {}
                if warm and start_deadline:
                    # Both constraints are upper bounds. Give the native controller their
                    # intersection instead of requiring a whole 150 ms window to remain.
                    try:
                        start_deadline['startBeforeMs'] = warm.bound_start_deadline(observed_at,start_deadline['startBeforeMs'])
                    except RuntimeError:
                        # Keep the original refused prediction separate from genuine native receipts.
                        refused = dict(type='localActionRefusal',reason='warmHandoffDeadline',transmissionAttempted=False,
                                       frameId=frame['frameId'],sourceFrame=copy.deepcopy(frame.get('sourceFrame')),
                                       sourceDeadlineMs=start_deadline['startBeforeMs'],handoffBeforeMs=warm.batch_dispatch_before_ms,
                                       warmRequestId=warm.current['id'],model=action_model_id,steps=copy.deepcopy(result['steps']),
                                       rawPolicySteps=copy.deepcopy(result.get('rawPolicySteps')),clientTimeNs=time.perf_counter_ns())
                        report.setdefault('localActionRefusals',[]).append(refused)
                        if recorder:
                            recorder.event(refused)
                        raise
                if start_deadline:
                    result.update(start_deadline)
                request_id = uuid.uuid4().hex
                # A failed or unbound response is an unknown outcome in every report,
                # never an invitation to replay on another connection or segment.
                evidence = {'requestId': request_id, 'frame': dict(frame),
                    'steps': result['steps'], 'observedAtMs': frame['capturedAtMs'],
                    'expiresAtMs': observed_at+700, **start_deadline}
                def submit_action():
                    """Finish this policy transaction under the current resident authority."""
                    nonlocal executed_request
                    arguments = dict(requestId=request_id, frameId=frame['frameId'],
                        observedAtMs=frame['capturedAtMs'], expiresAtMs=observed_at+700, modelId=action_model_id,
                        steps=result['steps'], **start_deadline)
                    # Intake and dispatch share this gate only for guarded scouts: a newer latched
                    # hazard can never be overtaken by an inference that started on healthy pixels.
                    with (receive_lock if scout_guard is not None or combat_guard is not None else nullcontext()):
                        if executed_history:
                            if stopped.is_set():
                                raise RuntimeError('Executed-history reader stopped before dispatch')
                            recorder.check()
                            executed_request = dict(version=1, command='action',
                                **{key: bridge.hello[key] for key in ('sessionId', 'ownerEpoch', 'goalVersion')},
                                **copy.deepcopy(arguments))
                        if scout_guard is not None:
                            result['scoutEncounterGuard'] = scout_dispatch(scout_guard,report,recorder,frame,request_id)
                        if combat_guard is not None:
                            marker = combat_guard.prepare_action(frame, result, request_id, time.perf_counter_ns(),
                                owner=args.combat_trial_owner, hello=bridge.hello)
                            result['combatTrialGuard'] = marker
                            report['combatTrialGuardState'] = marker['state']
                            recorder.event(marker)
                            if marker['type'] != 'combatTrialDispatch':
                                return dict(type='notSubmitted', reason=marker['reason']), b''
                            arguments = marker['arguments']
                            result['startBeforeMs'] = arguments['startBeforeMs']
                            evidence.update(expiresAtMs=arguments['expiresAtMs'], startBeforeMs=arguments['startBeforeMs'])
                        response = transmit_bound_action(bridge,warm,report,arguments,'unacknowledgedAction',evidence)
                        if executed_history and action_response_accepted(response[0], request_id, response[1]):
                            # Register while intake is excluded, before a fast terminal reply can be collected.
                            history_requests[request_id] = copy.deepcopy(executed_request)
                        if combat_guard is not None:
                            event = combat_guard.admission(response[0], len(response[1]), time.perf_counter_ns())
                            report['combatTrialGuardState'] = event['state']
                            recorder.event(event)
                        return response
                submitted, response = control.guarded_submit(control_token, submit_action) if warm or combat_guard is not None or executed_history else (True, submit_action())
                if submitted:
                    result['acceptance'], response_payload = response
                    committed = (False if combat_guard is not None and result['acceptance'].get('type') == 'notSubmitted'
                                 else action_response_accepted(result['acceptance'], request_id, response_payload))
                    if warm and committed:
                        warm.accepted(request_id, frame['frameId'])
                else:
                    result['acceptance'] = dict(type='notSubmitted', reason='residentControlEpochChanged')
                    committed = False
                if committed and camera_trial:
                    camera_trial.accepted(request_id, observed_at, result['steps'][0])
                report.pop('unacknowledgedAction', None)
                if committed and hybrid and hybrid.bypass:
                    # Keep one actual admission across recorder rotation. Every
                    # accepted action supersedes the earlier one, including turns.
                    selection = result['hybridNavigation']
                    last_hybrid_action = dict(requestId=request_id, frameId=frame['frameId'], modelId=action_model_id,
                        observedAtMs=observed_at, sourceEpoch=(frame.get('sourceFrame') or {}).get('captureEpoch'),
                        acceptedAtMs=result['acceptance'].get('acceptedAtMs'), step=copy.deepcopy(result['steps'][0]),
                        reason=selection['reason'], target=selection.get('target'), completedLegs=selection.get('completedLegs'),
                        bypassPointIndex=selection.get('bypassPointIndex'))
            else:
                result['acceptance'] = {'type': 'notSubmitted', 'reason': rejection}
                committed = False  # This branch proves no action request was submitted.
                if execution_mode != 'off':
                    bridge.not_submitted(result, model_id=action_model_id, frame_id=frame['frameId'], reason=rejection)
            if committed:
                report['acceptedInputActions'] += 1
                last_accepted_at = time.perf_counter()
                history_gap_reset = False
            feedback_error = None
            if executed_history:
                event, feedback_error = finish_executed_feedback(result, frame, executed_request, control_token)
                result['historyCommitted'] = event['outcome'] == 'committed'
                result['executedHistory'] = event
                report['executedHistoryEvents'].append(event)
                if result['historyCommitted']:
                    history_predecessor = dict(requestId=event['requestId'], frameId=event['frameId'],
                        endedAtMs=event['receipt']['endedAtMs'], sourceFrame=copy.deepcopy(event['sourceFrame']))
            elif getattr(policy, 'execution_feedback', False):
                model_committed = committed and action_model_id == args.model
                policy.finish_action(model_committed)
                result['historyCommitted'] = model_committed
                if hybrid and action_model_id != args.model:
                    # The unexecuted model prediction is not the native correction's action history.
                    policy.reset()
            # The candidate observes the original image-derived proposal and current
            # waypoint only after dispatch or rejection. It never owns input.
            shadow = policy.steering_shadow if hybrid and getattr(args, 'steering_shadow', None) else None
            if shadow is not None:
                selection = result['hybridNavigation']
                point = selection.get('steeringPoint') or dict(zip(('x', 'y'), hybrid.target))
                shadow_start = time.perf_counter_ns()
                prediction = shadow.predict(frame, (point['x'], point['y']),
                                            result.get('rawPolicySteps', selection['modelSteps']))
                result['steeringShadow'] = dict(checkpointId=shadow.checkpoint_id, prediction=prediction,
                    elapsedUs=(time.perf_counter_ns()-shadow_start)/1000)
            report['decisions'].append(result)
            if recorder:
                recorder.event({'type': 'proposal', 'frameId': frame['frameId'],
                                **({'warmRequestId': result['warmRequestId']} if warm else {}),
                                **({'scoutEncounterGuard': result['scoutEncounterGuard']}
                                   if 'scoutEncounterGuard' in result else {}),
                                **({'combatTrialGuard': result['combatTrialGuard']}
                                   if 'combatTrialGuard' in result else {}),
                                **({key: result[key] for key in ('episodeStep', 'validHistoryFrames', 'cudaGraphActive')}
                                   if warm and warm.destinations else {}),
                                'proposalJournalVersion': 3 if executed_history else 2,
                                **({'historyCommitMode': EXECUTED_HISTORY_MODE,
                                    'executedHistoryPredecessor': result['executedHistoryPredecessor']}
                                   if executed_history else {}),
                                # Null explicitly means this policy has no acceptance feedback.
                                'historyCommitted': result.get('historyCommitted'),
                                'observedAtMs': frame['capturedAtMs'], 'model': action_model_id,
                                **({'hybridNavigation': result['hybridNavigation']} if hybrid else {}),
                                **({'steeringShadow': result['steeringShadow']} if shadow is not None else {}),
                                **({'cameraCalibration': result['cameraCalibration']} if 'cameraCalibration' in result else {}),
                                'observationTimestampMs': observed_at,
                                'startBeforeMs': result.get('startBeforeMs'),
                                'steps': result['steps'], 'acceptance': result['acceptance'],
                                'rawPolicySteps': result.get('rawPolicySteps'),
                                'controllerResampling': result.get('controllerResampling'),
                                'controlEpoch': result['controlEpoch'], 'policyGoalVersion': result['policyGoalVersion'],
                                'appliedGoalRequestId': result['appliedGoalRequestId'],
                                'goalIntent': result['goalIntent'],
                                **({'executionContext': result['executionContext'],
                                    'executionContextMode': execution_mode,
                                    'executionContextText': result.get('executionContextText')}
                                   if execution_mode != 'off' else {}),
                                'latestFrameQuality': result['latestFrameQuality'],
                                'frameTiming': result['frameTiming'],
                                'policyWallMs': policy_ms, 'estimatedObservationAgeMs': age})
                if executed_history:
                    recorder.event(result['executedHistory'])
            if feedback_error is not None:
                raise feedback_error
            print(json.dumps({'frameId': previous, 'modelMs': result['fullActionMs'], 'ageMs': age,
                              'acceptance': result['acceptance']}), flush=True)
            if control:
                control.publish(state='running', reason=None, frameId=previous,
                                framesReceived=report['framesReceived'], acceptedInputActions=report['acceptedInputActions'],
                                policyWallMs=policy_ms, observationAgeMs=age,
                                latestAcceptance=result['acceptance'])
            if combat_guard is None and args.max_input_actions is not None and report['acceptedInputActions'] >= args.max_input_actions:
                report['endReason'] = 'maxInputActions'
                break  # Normal stop/receipt cleanup releases the input owner immediately.
            if idle_recovery.threshold is not None:
                with receive_lock:
                    newly_unapplied = unapplied_history_receipts(receipt_inbox)
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
        if combat_guard is not None:
            report['combatTrialGuardState'] = combat_guard.fail('episodeFailure', time.perf_counter_ns(), error=str(exc))['state']
        if not record_open_queue_boundary_error(warm,exc,getattr(hybrid,'failure',None),report,recorder):
            episode_failure = exc
            report['error'] = str(exc)
            if climb and climb.helper.blocks_model:
                raise climb.terminate('episode_failed_during_recovery', exc) from exc
            raise
    finally:
        stopped.set()
        if executed_history:
            # Attempt release before any encoder failure or cache reset can interrupt cleanup.
            # Keep the raw acknowledgement even when its journal write fails.
            with receive_lock:
                try:
                    released, payload = bridge.request('release')
                    report['executedHistoryRelease'] = dict(response=copy.deepcopy(released), payloadBytes=len(payload))
                    marker = scout_guard.acknowledge_release(released, len(payload), time.perf_counter_ns(), 'executedHistoryTeardown')
                    report['scoutEncounterGuardState'] = marker['state']
                    collect_receipts(released)
                    if recorder:recorder.event(marker)
                except Exception as error:
                    stop_failure = error
                    report['executedHistoryReleaseError'] = str(error)
            try:
                policy.reset()
            except Exception as error:
                stop_failure = stop_failure or error
                report['executedHistoryResetError'] = str(error)
        if combat_guard is not None:
            # Release is unconditional, including failed recording, unknown admission,
            # an interrupted final hold and an already latched reader hazard.
            with receive_lock:
                state = combat_guard.snapshot()
                if not state['trialComplete'] and state['trip'] is None:
                    report['combatTrialGuardState'] = combat_guard.fail('trialEndedBeforeDrain', time.perf_counter_ns())['state']
                try:
                    released, _ = combat_trial_release(bridge, combat_guard, report,
                        recorder if recorder and not recorder.error else None, 'combatTrialTeardown')
                    collect_receipts(released)
                except Exception as error:
                    stop_failure = error
                    report['combatTrialReleaseError'] = str(error)
                    report['combatTrialGuardState'] = combat_guard.fail('terminalReleaseFailure', time.perf_counter_ns(), error=str(error))['state']
        producer.join(timeout=3)
        if climb and climb.helper.blocks_model:
            terminal_climb_error = climb.terminate('lease_ended_during_recovery', cleanup_allowed=not producer.is_alive())
        if not producer.is_alive():
            try:
                if args.readiness_snapshots:
                    diagnostic_status = bridge.request('status')[0]
                    collect_receipts(diagnostic_status)
                    report['readinessDiagnosticsBeforeStop'] = diagnostic_status.get('diagnostics')
                report['stop'], stop_payload = bridge.request('stop')
                collect_receipts(report['stop'])
                if combat_guard is not None and (report['stop'].get('type') != 'stopped' or stop_payload):
                    report['combatTrialGuardState'] = combat_guard.fail('invalidStopAcknowledgement', time.perf_counter_ns(),
                        response=report['stop'], payloadBytes=len(stop_payload))['state']
                    raise RuntimeError('Combat trial stop was not acknowledged')
            except Exception as exc:
                stop_failure = exc
                report['stopError'] = str(exc)
        if climb:
            try:
                climb.handle.close()  # Never close a substituted public handle.
            except Exception as close_error:
                report['navigationClimbHandleCloseError'] = str(close_error)
                report.setdefault('error', 'Recovery handle close failed')
                terminal_climb_error = terminal_climb_error or RuntimeError(report['error'])
        else:
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
            if combat_guard is not None:
                try:
                    raw_control = json.loads(control.path.read_text(encoding='utf-8'))
                    report['combatTrialFinalControl'] = copy.deepcopy(raw_control)
                    goal_state = report['finalGoalState']
                    if (not isinstance(raw_control, dict)
                            or raw_control.get('version') != 1 or raw_control.get('runId') != control.run_id
                            or raw_control.get('command') not in ('run', 'pause', 'stop')
                            or any(key in raw_control for key in ('goalRequestId', 'goalEmbedding', 'goalIntent'))
                            or goal_state['goalRequestId'] is not None or goal_state['policyGoalVersion'] != 0
                            or goal_state['appliedGoalRequestId'] is not None or goal_state['goalError']
                            or hashlib.sha256(Path(args.goal_embedding).read_bytes()).hexdigest() != combat_binding['goalSha256']
                            or getattr(policy, 'combat_trial_goal_sha256', None) != combat_binding['goalSha256']):
                        raise RuntimeError('Combat trial frozen goal was changed or requested to change')
                except Exception as error:
                    report['combatTrialGuardState'] = combat_guard.fail('goalMutation', time.perf_counter_ns(), error=str(error))['state']
        if scout_guard is not None:
            report['scoutEncounterGuardState'] = scout_guard.snapshot()
            if report['scoutEncounterGuardState']['trip'] is not None:
                report.setdefault('error', 'Scout encounter guard: '+report['scoutEncounterGuardState']['trip']['reason'])
            elif not report['scoutEncounterGuardState']['admitted']:
                report.setdefault('error', 'Scout encounter guard never admitted native health evidence')
        if combat_guard is not None:
            state = combat_guard.snapshot()
            report['combatTrialGuardState'] = state
            # A journal failure may interrupt the ordinary proposal accounting after
            # a valid native acknowledgement; retain the known admission count anyway.
            report['acceptedInputActions'] = state['acceptedActions']
            if state['trip'] is not None or not state['trialComplete']:
                report.setdefault('error', 'Combat trial incomplete: ' + (state['trip']['reason'] if state['trip'] else state['phase']))
            else:
                report['endReason'] = 'combatTrialComplete'
        report.setdefault('endReason', 'noUsableFrames' if report.get('captureError') else
                          'streamError' if report.get('streamError') else 'error' if report.get('error') else
                          'durationElapsed' if time.perf_counter() >= deadline else 'stopped')
        # Keep the starting goal immutable while retaining validation costs and
        # cache state accumulated by later predictions (including failed ones).
        report['finalPolicyMetadata'] = copy.deepcopy(policy.metadata) if policy else None
        report['navigationIdleRecovery'] = idle_recovery.snapshot()
        if hybrid:
            publish_hybrid()
            reached = warm.finished if warm and warm.batch_count else (args.hybrid_legs is None or hybrid.legs >= args.hybrid_legs)
            if not reached and report['endReason'] not in ('userStop','userPause'):
                report.setdefault('error', 'Requested hybrid route legs were not completed')
        if execution_mode != 'off':
            # Include terminal reports that arrived after the last model decision.
            final_frame = latest.newer_than(None)
            if final_frame is not None and not producer.is_alive():
                try:
                    final_token = control.prediction_token() if control else (0, 0, None, 'run')
                    final_context = bridge.snapshot(final_frame[0],
                        decision_context=decision_context(final_frame[0], final_token)).to_dict()
                    report['executionContextFinal'] = final_context
                    if recorder:
                        recorder.event({'type': 'executionContextFinal', 'context': final_context})
                except Exception as exc:
                    report['executionContextFinalError'] = str(exc)
            elif producer.is_alive():
                report['executionContextFinalError'] = 'Frame reader is still running; final evidence is incomplete'
        failure = episode_failure or (receive_failure[0] if receive_failure else None)
        if failure is None and stop_failure is not None:
            # An intended end must not reconnect merely because its stop/receipt cleanup failed.
            failure = stop_failure
            forbid_reconnect(failure, 'stopOnlyFailure')
            report.setdefault('error', str(failure) or type(failure).__name__)
        if failure is not None:
            if executed_history:
                forbid_reconnect(failure, 'executedHistoryModeFailure')
            # A pipe loss never overrides concurrent non-transport or ownership failures.
            if receive_failure and not is_transport_failure(receive_failure[0]):
                forbid_reconnect(failure, 'frameProcessingFailure')
            if stop_failure is not None and not is_transport_failure(stop_failure):
                forbid_reconnect(failure, 'stopProcessingFailure')
            if producer.is_alive():
                forbid_reconnect(failure, 'readerNotRetired')
            if report.get('unacknowledgedAction'):
                forbid_reconnect(failure, 'actionOutcomeUnknown')
            if recorder and recorder.error:
                forbid_reconnect(failure, 'recordingFailure')
            report['episodeFailure'] = dict(type=type(failure).__name__,
                transportOperation=transport_origin(failure))
        if recorder:
            try:
                recorder.event({'type': 'captureQualitySummary', 'captureQuality': dict(report['captureQuality']),
                                'captureError': report.get('captureError')})
                recorder.event({'type': 'episodeEnd', 'endReason': report['endReason'],
                                'maxInputActions': args.max_input_actions,
                                'acceptedInputActions': report['acceptedInputActions']})
            except Exception as error:
                if combat_guard is None and not executed_history:
                    raise
                report['recordingFinalizationError'] = str(error)
                if combat_guard is not None:
                    report['combatTrialGuardState'] = combat_guard.fail('recordingFailure', time.perf_counter_ns(), error=str(error))['state']
                report.setdefault('error', 'Required journal finalization failed')
            try:
                if archive:
                    manifest = archive.finish(report)
                    report['status'] = manifest['status']
                else:
                    report['recording'] = recorder.close()
            except Exception as error:
                if combat_guard is None and not executed_history:
                    raise
                report['recording'] = dict(error=str(error))
                if executed_history:report.setdefault('error', 'Executed-history recording close failed')
            if combat_guard is not None and (recorder.error or report.get('recording', {}).get('error')):
                report['combatTrialGuardState'] = combat_guard.fail('recordingFailure', time.perf_counter_ns(),
                    error=recorder.error or report['recording']['error'])['state']
                report.setdefault('error', 'Combat trial recording failed')
            # A late encoder/finalizer failure also vetoes a previously identified pipe loss.
            if failure is not None and (recorder.error or report.get('recording', {}).get('error')):
                forbid_reconnect(failure, 'recordingFailure')
        if not archive:
            report['status'] = 'failed' if (report.get('error') or report.get('streamError') or
                                            report.get('recording', {}).get('error')) else 'completed'
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if terminal_climb_error is not None:
        # An unresolved recovery remains terminal even when its underlying cause was pipe loss.
        raise terminal_climb_error
    if failure is not None:
        # Teardown and evidence finish first; preserve the actual reader or stop-only exception.
        raise failure
    return 1 if report['status'] == 'failed' else 0


def main():
    """Select a bounded single lease or a resident process with explicit RDP ownership."""
    args = parse_arguments()
    if args.resident:
        from resident_runtime import run_resident
        return run_resident(args, load_policy, run_episode)
    try:
        return run_episode(args, load_policy(args))
    except FrameProfileError as exc:
        # The single-lease runner has already released input and written its failed report.
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
