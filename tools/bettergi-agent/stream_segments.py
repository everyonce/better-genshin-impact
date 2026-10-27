"""Bounded evidence rollover, independent of a live bridge or policy's lifetime."""
from collections import OrderedDict, deque
import copy
import json
from pathlib import Path
import threading
import time


class EvidencePublicationError(RuntimeError):
    """Terminal evidence was not published; retain totals and forbid transport retry."""
    def __init__(self, message, manifest):
        super().__init__(message)
        self.manifest = manifest


class RecordingBudget:
    """Share measured video/sidecar usage between the active and retiring writers."""
    def __init__(self, maximum):
        self.maximum = maximum
        self.lock = threading.Lock()
        self.sizes = {}

    def update(self, key, size):
        with self.lock:
            self.sizes[key] = max(size, self.sizes.get(key, 0))
            return sum(self.sizes.values())

    @property
    def used(self):
        with self.lock:
            return sum(self.sizes.values())


class StreamSegments:
    """Keep one active segment and at most one asynchronously retiring segment.

    The owner calls rotate between policy transactions under its ingestion lock.
    Report lists transfer ownership instead of being serialized on that thread.
    A stalled finalizer fails the next rollover explicitly; it cannot accumulate
    arbitrary writers, reports or native encoder processes.
    """
    LISTS = ('decisions', 'receipts', 'controlTransitions', 'goalChanges',
             'navigationProgress', 'navigationIdleRecoveryEvents',
             'navigationClimbRecoveryEvents', 'navigationClimbActions', 'hybridNavigationEvents')
    COUNTERS = ('framesReceived', 'acceptedInputActions', 'unappliedAcceptedActions', 'receiptHistoryResets')
    MAX_SEGMENTS = 4096
    MAX_CONTEXT = 256

    def __init__(self, args, recorder_factory, report, now=None):
        self.args = args
        self.factory = recorder_factory
        self.number = int(getattr(args, 'segment_start_index', 1))
        self.report_parent = Path(args.output).parent
        self.record_parent = Path(args.record_dir).parent if args.record_dir else None
        self.budget = RecordingBudget(args.record_max_mib * 2**20)
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.closing = threading.Event()
        self.retiring = None
        self.results = []
        self.submitted = 0
        self._error = None
        self.recording_error = None
        self.headers = OrderedDict()
        self.pending = OrderedDict()
        self.early_receipts = deque(maxlen=self.MAX_CONTEXT)
        self.started = time.perf_counter() if now is None else now
        self.next_at = self.started + args.segment_seconds
        self.counter_base = {key: 0 for key in self.COUNTERS}
        self.quality_base = {key: 0 for key in report['captureQuality'] if key != 'check'}
        self.context = self._context(None)
        self.recorder = self._new_recorder()
        self.worker = threading.Thread(target=self._finalize, name='BetterGI-segments', daemon=True)
        self.worker.start()

    @property
    def error(self):
        with self.lock:
            return self._error or self.recording_error or (self.recorder.error if self.recorder else None)

    def _new_recorder(self):
        if self.record_parent is None or self.budget.used >= self.budget.maximum:
            return None
        return self.factory(str(self.record_parent / f'{self.number:05d}'), self.args.ffmpeg,
                            self.args.fps, self.budget.maximum, preview=self.args.preview,
                            shared_budget=self.budget)

    def _context(self, previous):
        """Carry original evidence, explicitly as context rather than new decisions/video."""
        proposals = copy.deepcopy(list(self.pending.values()))
        ids = {item['frameId'] for item in proposals}
        if self.headers:
            ids.add(next(reversed(self.headers)))
        return {'previousReport': previous, 'sameBridgeLease': previous is not None,
                'pendingProposals': [item for item in proposals if item.get('type') == 'proposal'],
                'pendingRecoveryActions': [item for item in proposals if item.get('type') == 'navigationClimbAction'],
                'sourceFrames': [copy.deepcopy(self.headers[key]) for key in ids if key in self.headers],
                'join': 'sessionId + ownerEpoch + requestId; frameId refers to the same lease clock'}

    def put(self, metadata, pixels):
        with self.lock:
            header = {key: value for key, value in metadata.items() if key != 'receipts'}
            self.headers[metadata['frameId']] = header
            self.headers.move_to_end(metadata['frameId'])
            # Pending accepted proposals pin their source headers until terminal receipt.
            pinned = {item['frameId'] for item in self.pending.values()}
            while len(self.headers) > self.MAX_CONTEXT:
                removable = next((key for key in self.headers if key not in pinned), None)
                if removable is None:
                    raise RuntimeError('Segment source context capacity exhausted')
                self.headers.pop(removable)
            return self.recorder.put(metadata, pixels) if self.recorder else False

    def event(self, event):
        with self.lock:
            acceptance = event.get('acceptance', {})
            if event.get('type') in ('proposal', 'navigationClimbAction') and acceptance.get('type') == 'accepted':
                request = acceptance.get('requestId')
                if not request:
                    raise RuntimeError('Accepted proposal lacks requestId for segment evidence joins')
                if event['frameId'] not in self.headers:
                    raise RuntimeError('Accepted proposal lacks its source header for segment evidence joins')
                if request not in self.early_receipts:
                    if len(self.pending) >= self.MAX_CONTEXT:
                        raise RuntimeError('Unresolved segment proposal context capacity exhausted')
                    self.pending[request] = dict(event, originSegment=self.number)
            elif event.get('requestId') and 'appliedSteps' in event:
                request = event['requestId']
                if self.pending.pop(request, None) is None:
                    # Capture can collect a terminal receipt between action acknowledgement
                    # and this policy thread's proposal event. Do not retain it forever.
                    self.early_receipts.append(request)
            return self.recorder.event(event) if self.recorder else False

    def fail(self, reason):
        with self.lock:
            self.recording_error = self.recording_error or str(reason)
            if self.recorder:
                self.recorder.fail(reason)

    def due(self, now):
        return now >= self.next_at

    def _snapshot(self, report, reason, now):
        report.setdefault('leaseInitialGoalState', copy.deepcopy(report.get('initialGoalState')))
        report.setdefault('leaseInitialPolicyMetadata', copy.deepcopy(report.get('policyMetadata')))
        snapshot = dict(report)
        for key in self.LISTS:
            if key in report:
                snapshot[key], report[key] = report[key], []
        for key in self.COUNTERS:
            snapshot[key] = report[key] - self.counter_base[key]
            self.counter_base[key] = report[key]
        quality = dict(report['captureQuality'])
        for key in self.quality_base:
            quality[key] -= self.quality_base[key]
            self.quality_base[key] = report['captureQuality'][key]
        snapshot.update(captureQuality=quality, endReason=reason,
                        segment={'number': self.number, 'startedAtClientNs': round(self.started*1e9),
                                 'endedAtClientNs': round(now*1e9), 'leaseEnded': reason != 'segmentRotated'},
                        continuity=self.context)
        if reason == 'segmentRotated':
            report['initialGoalState'] = copy.deepcopy(report.get('finalGoalState'))
            report['policyMetadata'] = copy.deepcopy(report.get('finalPolicyMetadata'))
        return snapshot

    def _submit(self, report, reason, now, terminal=False):
        if self.retiring is not None:
            raise RuntimeError('Segment finalizer backlog exhausted; evidence is incomplete')
        if self._error and not terminal:
            raise RuntimeError('Segment finalization failed; evidence is incomplete: ' + self._error)
        if self.number > self.MAX_SEGMENTS:
            raise RuntimeError('Segment count limit reached')
        path = self.report_parent / f'{self.number:05d}.json'
        snapshot = self._snapshot(report, reason, now)
        recorder, self.recorder = self.recorder, None
        if recorder:
            recorder.event({'type': 'segmentEnd', 'segment': self.number, 'endReason': reason,
                            'leaseEnded': reason != 'segmentRotated'})
            recorder.begin_close()
        self.retiring = (snapshot, recorder, path)
        self.submitted += 1
        self.wake.set()
        return path

    def rotate(self, report, now):
        """Nonblocking ownership transfer; never calls bridge, policy, encoder wait or file IO."""
        with self.lock:
            path = self._submit(report, 'segmentRotated', now)
            self.number += 1
            self.started = now
            self.next_at = now + self.args.segment_seconds
            self.context = self._context(str(path))
            self.recorder = self._new_recorder()
            if self.recorder:
                self.recorder.event({'type': 'segmentStart', 'segment': self.number,
                                     'sessionId': report['hello']['sessionId'],
                                     'ownerEpoch': report['hello'].get('ownerEpoch'),
                                     'continuity': self.context})
                for header in self.context['sourceFrames']:
                    self.recorder.observation(header, continuity=True)

    def _finalize(self):
        while True:
            self.wake.wait()
            self.wake.clear()
            with self.lock:
                job = self.retiring
                if job is None:
                    if self.closing.is_set():
                        return
                    continue
            snapshot, recorder, path = job
            error = None
            try:
                if recorder:
                    snapshot['recording'] = recorder.close()
                    if snapshot['recording'].get('workerRetired') is not True:
                        # A timed-out writer can still own IO even after its encoder
                        # exits. Never permit another rollover/reconnect to add writers.
                        error = 'Recording worker did not retire; evidence is incomplete'
                        snapshot['recording']['error'] = snapshot['recording'].get('error') or error
                    if snapshot['recording'].get('error'):
                        self.recording_error = snapshot['recording']['error']
                snapshot['status'] = 'failed' if (snapshot.get('error') or snapshot.get('streamError')
                    or snapshot.get('stopError') or snapshot.get('recording', {}).get('error')) else 'completed'
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix('.tmp')
                temporary.write_text(json.dumps(snapshot, indent=2, allow_nan=False), encoding='utf-8')
                temporary.replace(path)
            except Exception as exc:
                error = str(exc)
            finally:
                with self.lock:
                    self.results.append({'number': snapshot['segment']['number'], 'report': str(path),
                        'endReason': snapshot['endReason'], 'framesReceived': snapshot['framesReceived'],
                        'acceptedInputActions': snapshot['acceptedInputActions'],
                        'exitCode': int(error is not None or snapshot.get('status') != 'completed'),
                        **({'error': error} if error else {})})
                    self._error = self._error or error
                    self.retiring = None
                    # Retirement and exit are one decision. finish() may submit
                    # the terminal job only after this lock is released.
                    if self.closing.is_set():
                        return

    def finish(self, report):
        """Called only after input/transport stop; bound the final archive drain separately."""
        # Waiting is permitted only at terminal lease teardown, never at rollover.
        end = time.monotonic() + 24
        while self.retiring is not None and time.monotonic() < end:
            time.sleep(.01)
        failure = None
        with self.lock:
            try:
                self._submit(report, report['endReason'], time.perf_counter(), terminal=True)
            except Exception as exc:
                failure = str(exc)
                if self.recorder:
                    self.recorder.fail(failure)
            self.closing.set()
            self.wake.set()
        self.worker.join(timeout=24)
        if self.worker.is_alive():
            failure = failure or 'Segment finalizer did not finish; evidence is incomplete'
        elif self.retiring is not None or len(self.results) != self.submitted:
            failure = failure or 'Segment finalizer omitted a submitted report; evidence is incomplete'
        if failure and self.recorder:
            self.recorder.close(timeout=2)
        if failure:
            self._error = self._error or failure
        manifest = {'version': 1, 'segments': list(self.results), 'recordedBytes': self.budget.used,
                    'recordingBudgetExhausted': self.budget.used >= self.budget.maximum,
                    'status': 'failed' if self.error or any(item['exitCode'] for item in self.results) else 'completed',
                    'error': self.error, 'evidenceError': self._error,
                    'acceptedInputActions': report['acceptedInputActions'], 'framesReceived': report['framesReceived'],
                    'unacknowledgedAction': report.get('unacknowledgedAction', {}).get('requestId'),
                    'endReason': report['endReason'],
                    **({'navigationClimbRecovery': copy.deepcopy(report['navigationClimbRecovery']),
                        'unacknowledgedRecoveryAction': report.get('unacknowledgedRecoveryAction', {}).get('requestId')}
                       if 'navigationClimbRecovery' in report else {})}
        path = Path(self.args.lease_output)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding='utf-8')
            temporary.replace(path)
        except Exception as exc:
            # OSError is otherwise reconnectable at the transport layer. Losing
            # this index must not discard later parts, caps or an uncertain action.
            manifest.update(status='failed', evidenceError=f'Cannot publish lease manifest: {exc}')
            raise EvidencePublicationError(manifest['evidenceError'], manifest) from exc
        return manifest
