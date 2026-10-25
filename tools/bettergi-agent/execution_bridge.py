"""Optional client-knowledge observation around the existing serialized bridge."""

import copy
import threading
import time

from execution_context import ExecutionContext


class ExecutionContextBridge:
    """Keep transport, evidence arrival, and proposal recording in one serial order.

    This wrapper supplies no input authority. The existing bridge validates and
    sends requests, and the existing controller still decides whether to run them.
    No ledger lock is held while calling the transport or the model.
    """

    def __init__(self, bridge, *, clock=time.perf_counter_ns):
        """Bind a bounded ledger to one existing authenticated pipe lease."""
        self._bridge = bridge
        self._clock = clock
        self._transport_lock = threading.Lock()
        # Only short evidence operations use this lock; pipe IO never holds it.
        self._lock = threading.Lock()
        self._origin = None
        if bridge.hello.get('inputTelemetry') is not None:
            if (bridge.hello.get('clock') != 'monotonic milliseconds since session start'
                    or type(bridge.hello.get('clockFrequency')) is not int
                    or bridge.hello['clockFrequency'] != 1000):
                raise ValueError('ongoing_hello_clock')
        self.context = ExecutionContext(
            {key: bridge.hello[key] for key in ('sessionId', 'ownerEpoch')},
            max_events=64, window_ns=5_000_000_000, input_telemetry=bridge.hello.get('inputTelemetry'))
        self._ongoing_negotiated = bridge.hello.get('inputTelemetry') is not None

    @property
    def hello(self):
        """Expose the original negotiated identity and capabilities unchanged."""
        return self._bridge.hello

    @property
    def handle(self):
        """Retain the original peer-verifiable handle and close ownership."""
        return self._bridge.handle

    def request(self, command, **kwargs):
        """Stamp full response arrival before any ordinary receipt processing."""
        with self._transport_lock:
            request_id = kwargs.get('requestId') if command == 'action' else None
            if command == 'action':
                with self._lock:
                    self.context.record('proposal', kwargs, observed_client_ns=self._clock(),
                                        decision_context=self._origin)
            try:
                response, pixels = self._bridge.request(command, **kwargs)
            except Exception:
                if command == 'action':
                    with self._lock:
                        self.context.record('unknown', {
                            'requestId': request_id,
                            'reason': 'transport_failed_outcome_unknown'},
                            observed_client_ns=self._clock())
                raise
            returned = self._clock()
            with self._lock:
                # A snapshot can occur before intake gets this lock. Do not claim
                # that snapshot knew a packet merely because transport returned.
                arrived = self._clock()
                negotiation = ({'identity': {key: self._bridge.hello[key] for key in ('sessionId', 'ownerEpoch')},
                                'input_telemetry': self._bridge.hello.get('inputTelemetry')}
                               if self._ongoing_negotiated else {})
                self.context.record_response(command, response, observed_client_ns=arrived,
                                             expected_request_id=request_id, payload_bytes=len(pixels), **negotiation)
            # This is local arrival metadata, never sent back as a server clock.
            observed = dict(response)
            observed['executionResponseReturnedClientNs'] = returned
            observed['executionObservedClientNs'] = arrived
            return observed, pixels

    def snapshot(self, frame, *, decision_context):
        """Freeze the evidence available immediately before this model call."""
        with self._lock:
            projected = {
                'frameId': frame['frameId'],
                'observedClientNs': frame['executionObservedClientNs'],
                'capturedAtMs': frame.get('capturedAtMs'),
                'serverNowMs': frame.get('serverNowMs'),
            }
            for key in ('sourceTimestampKind', 'sourceKind'):
                if frame.get(key) is not None:
                    projected[key] = frame[key]
            for key in ('sourceFrame', 'hostSnapshot'):
                if frame.get(key) is not None:
                    projected[key] = frame[key]
            if frame.get('sourceFrameAgeMs') is not None:
                projected['sourceAgeMs'] = frame['sourceFrameAgeMs']
            elif frame.get('hostAcquisitionAgeMs') is not None:
                projected['sourceAgeMs'] = frame['hostAcquisitionAgeMs']
            if frame.get('frameWorldReadiness') is not None:
                projected['readiness'] = frame['frameWorldReadiness']
            snapshot = self.context.snapshot(projected, cutoff_client_ns=self._clock(),
                                             decision_context=decision_context)
            self._origin = copy.deepcopy(decision_context)
            return snapshot

    def not_submitted(self, result, *, model_id, frame_id, reason):
        """Retain a rejected proposal separately from an attempted bridge action."""
        with self._lock:
            known = self._clock()
            self.context.record('proposal', {
                'modelId': model_id, 'frameId': frame_id, 'steps': result.get('steps', [])},
                observed_client_ns=known, decision_context=self._origin)
            self.context.record('admission', {
                'modelId': model_id, 'frameId': frame_id,
                'state': 'not_submitted', 'reason': reason}, observed_client_ns=known)


def decision_context(frame, control_token):
    """Keep decision epochs separate from the origins of earlier input requests."""
    source = frame.get('hostSnapshot') or frame.get('sourceFrame') or {}
    return {
        'controlEpoch': control_token[0],
        'policyGoalVersion': control_token[1],
        'readinessEpoch': frame.get('frameWorldReadiness', {}).get('epoch'),
        'sourceEpoch': source.get('captureEpoch'),
    }
