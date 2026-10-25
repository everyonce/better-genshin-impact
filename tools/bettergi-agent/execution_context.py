"""Bounded client-knowledge evidence; never authorizes input or infers game effects."""

from collections import deque
from dataclasses import dataclass
import json
import math
import threading

from ongoing_input import OngoingInput, capability as telemetry_capability, projection as telemetry_projection


SCHEMA = 'execution-context-v1'
MODEL_TEXT_LIMIT = 2048
_SNAPSHOT_KEY = object()
_IDENTITY_FIELDS = ('sessionId', 'ownerEpoch')
_DECISION_FIELDS = ('controlEpoch', 'readinessEpoch', 'policyGoalVersion', 'sourceEpoch')


def _integer(value, name, minimum=0):
    """Reject Boolean and lossy numeric identities/timestamps."""
    if type(value) is not int or value < minimum:
        raise ValueError(name)
    return value


def _text(value, name, maximum=160):
    """Keep wire labels bounded and free of control characters."""
    if type(value) is not str or not value or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(name)
    return value


def _json(value, limit):
    """Detach JSON without accepting opaque objects, NaN or unbounded structures."""
    result = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
    if len(result.encode('utf-8')) > limit:
        raise ValueError('context_payload_too_large')
    return result


def _identity(value):
    """Retain explicit unknown epochs; never guess a session or an owner."""
    if type(value) is not dict or set(value) - set(_IDENTITY_FIELDS):
        raise ValueError('context_identity')
    result = {key: value.get(key) for key in _IDENTITY_FIELDS}
    for key in ('sessionId', 'ownerEpoch'):
        _text(result[key], key)
    return _json(result, 1536)


def _decision(value):
    """Keep current decision epochs separate from the lease and from old proposals."""
    if value is None:
        value = {}
    if type(value) is not dict or set(value) - set(_DECISION_FIELDS):
        raise ValueError('decision_context')
    result = {key: value.get(key) for key in _DECISION_FIELDS}
    for key in ('controlEpoch', 'readinessEpoch', 'policyGoalVersion'):
        if result[key] is not None:
            _integer(result[key], key)
    if result['sourceEpoch'] is not None:
        _text(result['sourceEpoch'], 'sourceEpoch')
    return _json(result, 1536)


def _number(value, name):
    """Keep server milliseconds finite without converting them to client time."""
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(name)
    return value


def _steps(values, receipt):
    """Copy the R45 six-step envelope; receipt times are pre-dispatch stamps."""
    if type(values) is not list or len(values) > 6:
        raise ValueError('steps')
    result = []
    for value in values:
        if type(value) is not dict:
            raise ValueError('step')
        keys = value.get('keys')
        if type(keys) is not list or len(keys) > 16 or len(set(keys)) != len(keys):
            raise ValueError('keys')
        row = {'keys': [_text(key, 'key', 32) for key in keys]}
        for axis in ('mouseDx', 'mouseDy'):
            if type(value.get(axis)) is not int or abs(value[axis]) > 1_000_000:
                raise ValueError(axis)
            row[axis] = value[axis]
        if receipt:
            row['index'] = _integer(value.get('index'), 'index')
            row['startedAtMs'] = _number(value.get('startedAtMs'), 'startedAtMs')
        elif 'durationMs' in value:
            row['durationMs'] = _integer(value['durationMs'], 'durationMs')
        result.append(row)
    if receipt and [row['index'] for row in result] != list(range(len(result))):
        raise ValueError('noncontiguous_applied_steps')
    return result


def _payload(kind, value):
    """Project named evidence fields, never private proposal tokens or arbitrary text."""
    if kind not in ('proposal', 'admission', 'receipt', 'unknown') or type(value) is not dict:
        raise ValueError('context_event')
    row = {}
    for key in ('requestId', 'modelId', 'reason'):
        if value.get(key) is not None:
            row[key] = _text(value[key], key)
    if value.get('frameId') is not None:
        row['frameId'] = _integer(value['frameId'], 'frameId')
    if kind == 'proposal':
        row['steps'] = _steps(value.get('steps', []), False)
    elif kind == 'admission':
        state = value.get('state')
        if state not in ('accepted', 'rejected', 'not_submitted', 'unknown'):
            raise ValueError('admission_state')
        if state in ('accepted', 'rejected') and not row.get('requestId'):
            raise ValueError('admission_request_identity')
        row['state'] = state
        for key in ('receivedAtMs', 'acceptedAtMs'):
            if value.get(key) is not None:
                row[key] = _number(value[key], key)
    elif kind == 'receipt':
        for key in ('requestId', 'modelId', 'frameId'):
            if key not in row:
                raise ValueError('receipt_' + key)
        row['status'] = _text(value.get('status'), 'receipt_status', 64)
        for key in ('acceptedAtMs', 'endedAtMs'):
            row[key] = _number(value.get(key), key)
        row['appliedSteps'] = _steps(value.get('appliedSteps'), True)
    else:
        row['reason'] = _text(value.get('reason'), 'unknown_reason')
        if 'droppedReceipts' in value:
            row['droppedReceipts'] = _integer(value['droppedReceipts'], 'droppedReceipts')
    return _json(row, 8192)


@dataclass(frozen=True)
class ExecutionSnapshot:
    """Immutable canonical machine evidence; projections returned to callers are detached."""
    _document_json: str
    _key: object

    def to_dict(self):
        """Return an independent JSON object without exposing ledger references."""
        if self._key is not _SNAPSHOT_KEY:
            raise ValueError('snapshot_not_created_by_ledger')
        return json.loads(self._document_json)


class ExecutionContext:
    """Serialize bounded intake and snapshots; external calls must occur outside this lock."""

    def __init__(self, identity, *, max_events=128, window_ns=30_000_000_000, input_telemetry=None):
        """Create an empty ledger for one exact connection/control/source identity."""
        self._identity = _identity(identity)
        self._limit = _integer(max_events, 'max_events', 1)
        self._window = _integer(window_ns, 'window_ns', 1)
        if self._limit > 256 or self._window > 300_000_000_000:
            raise ValueError('context_bounds')
        self._lock = threading.Lock()
        self._events = deque()
        self._sequence = 0
        self._generation = 0
        self._last_ns = -1
        self._snapshot_ns = -1
        self._begin_ns = 0
        self._evicted = 0
        self._evicted_ns = -1
        self._previous_decision = None
        self._ongoing = OngoingInput(input_telemetry) if input_telemetry is not None else None

    def _check(self, observed_client_ns, identity):
        """Require explicit monotonic knowledge times on the serialized ingress stream."""
        _integer(observed_client_ns, 'observed_client_ns')
        if observed_client_ns < self._last_ns:
            raise ValueError('knowledge_clock_regression')
        if identity is not None and _identity(identity) != self._identity:
            raise ValueError('context_identity_changed')

    def _append(self, kind, payload_json, observed_client_ns):
        """Assign an ingress sequence and evict only an explicit bounded prefix."""
        self._sequence += 1
        self._last_ns = observed_client_ns
        self._events.append((self._sequence, observed_client_ns, kind, payload_json))
        while self._events and (len(self._events) > self._limit or
                self._events[0][1] < observed_client_ns - self._window):
            old = self._events.popleft()
            self._evicted += 1
            self._evicted_ns = old[1]
        return self._sequence

    def record(self, kind, payload, *, observed_client_ns, identity=None, decision_context=None):
        """Record current evidence; historical events without receipt time are rejected."""
        encoded = _payload(kind, payload)
        if decision_context is not None:
            if kind != 'proposal':
                raise ValueError('origin_context_only_on_proposal')
            detached = json.loads(encoded)
            detached['originContext'] = json.loads(_decision(decision_context))
            encoded = _json(detached, 8192)
        with self._lock:
            self._check(observed_client_ns, identity)
            return self._append(kind, encoded, observed_client_ns)

    def record_response(self, command, response, *, observed_client_ns,
                        expected_request_id=None, payload_bytes=0, identity=None, input_telemetry=None):
        """Atomically project a returned bridge packet, before ordinary receipt processing."""
        if type(response) is not dict or type(command) is not str:
            raise ValueError('bridge_response')
        _integer(payload_bytes, 'payload_bytes')
        rows = []
        if command == 'action':
            matched = (type(expected_request_id) is str and bool(expected_request_id)
                       and response.get('requestId') == expected_request_id and payload_bytes == 0
                       and response.get('type') in ('accepted', 'rejected'))
            row = {'state': response['type'] if matched else 'unknown',
                   'requestId': expected_request_id,
                   'reason': response.get('reason') if matched else 'unmatched_or_malformed_action_response'}
            if matched:
                row.update({key: response[key] for key in ('receivedAtMs', 'acceptedAtMs') if key in response})
            rows.append(('admission', _payload('admission', row)))
        if command == 'release':
            rows.append(('unknown', _payload('unknown', {'reason': 'release_ack_is_not_per_key_release_proof'})))
        receipts = response.get('receipts', [])
        if type(receipts) is not list or len(receipts) > 4096:
            raise ValueError('receipt_batch')
        if len(receipts) > self._limit:
            rows.append(('unknown', _payload('unknown', {'reason': 'receipt_batch_prefix_omitted',
                                                        'droppedReceipts': len(receipts) - self._limit})))
        rows.extend(('receipt', _payload('receipt', row)) for row in receipts[-self._limit:])
        dropped = response.get('droppedReceipts', 0)
        _integer(dropped, 'droppedReceipts')
        if dropped:
            rows.append(('unknown', _payload('unknown', {'reason': 'server_reported_dropped_receipts',
                                                        'droppedReceipts': dropped})))
        with self._lock:
            self._check(observed_client_ns, identity)
            if self._ongoing is not None:
                # This contract has no per-packet epoch: the authenticated hello binds it.
                if identity is None or telemetry_capability(input_telemetry) != self._ongoing.capability_json:
                    raise ValueError('ongoing_negotiation_changed')
                expected_type = {'frame': ('frame', 'waiting'), 'status': ('status',),
                                 'release': ('released',), 'stop': ('stopped',)}
                if response.get('type') in expected_type.get(command, ()):
                    if 'executionContext' not in response:
                        raise ValueError('ongoing_snapshot_missing')
                    proposals = {}
                    for _, _, kind, encoded in self._events:
                        if kind == 'proposal':
                            proposal = json.loads(encoded)
                            if proposal.get('requestId'):
                                prior = proposals.get(proposal['requestId'])
                                if prior is not None and prior != proposal:
                                    raise ValueError('ongoing_ambiguous_proposal')
                                proposals[proposal['requestId']] = proposal
                    self._ongoing.ingest(response['executionContext'], observed_client_ns=observed_client_ns,
                                         proposals=proposals)
                elif 'executionContext' in response:
                    raise ValueError('ongoing_unexpected_response')
            elif 'executionContext' in response:
                raise ValueError('ongoing_capability_required')
            self._last_ns = observed_client_ns
            return tuple(self._append(kind, encoded, observed_client_ns) for kind, encoded in rows)

    def reset_identity(self, identity, *, observed_client_ns, input_telemetry=None):
        """Invalidate only on lease/session change; goal/source changes must not erase actions."""
        encoded = _identity(identity)
        ongoing = OngoingInput(input_telemetry) if input_telemetry is not None else None
        with self._lock:
            self._check(observed_client_ns, None)
            self._identity = encoded
            self._ongoing = ongoing
            self._generation += 1
            self._events.clear()
            self._evicted = 0
            self._evicted_ns = -1
            self._begin_ns = observed_client_ns
            self._previous_decision = None
            return self._append('unknown', _payload('unknown', {'reason': 'lease_changed_prior_input_and_release_unknown'}),
                                observed_client_ns)

    def snapshot(self, frame, *, cutoff_client_ns, identity=None, decision_context=None):
        """Freeze only data already ingested and known by cutoff, immediately before predict."""
        if type(frame) is not dict:
            raise ValueError('frame')
        allowed = ('frameId', 'observedClientNs', 'capturedAtMs', 'sourceAgeMs', 'sourceFrame',
                   'hostSnapshot', 'serverNowMs', 'readiness', 'sourceTimestampKind', 'sourceKind')
        if set(frame) - set(allowed):
            raise ValueError('frame_fields')
        _integer(frame.get('frameId'), 'frameId')
        _integer(frame.get('observedClientNs'), 'frame_observed_client_ns')
        _integer(cutoff_client_ns, 'cutoff_client_ns')
        if frame['observedClientNs'] > cutoff_client_ns:
            raise ValueError('frame_after_cutoff')
        for key in ('capturedAtMs', 'sourceAgeMs', 'serverNowMs'):
            if frame.get(key) is not None:
                _number(frame[key], key)
        frame_copy = json.loads(_json(frame, 4096))
        current_decision = json.loads(_decision(decision_context))
        with self._lock:
            if identity is not None and _identity(identity) != self._identity:
                raise ValueError('snapshot_identity_changed')
            if cutoff_client_ns < max(self._begin_ns, self._snapshot_ns):
                raise ValueError('snapshot_clock_regression')
            if frame_copy['observedClientNs'] < self._begin_ns:
                raise ValueError('frame_from_prior_lease')
            self._snapshot_ns = cutoff_client_ns
            visible = [row for row in self._events if row[1] <= cutoff_client_ns]
            selected = [row for row in visible if row[1] >= cutoff_client_ns - self._window]
            events, receipts = [], {}
            origins = {}
            for _, _, kind, encoded in visible:
                row = json.loads(encoded)
                if kind == 'proposal' and row.get('requestId') and row.get('originContext'):
                    if row['requestId'] in origins and origins[row['requestId']] != row['originContext']:
                        origins[row['requestId']] = None
                    else:
                        origins.setdefault(row['requestId'], row['originContext'])
            for seq, known, kind, encoded in selected:
                payload = json.loads(encoded)
                event = {'sequence': seq, 'observedClientNs': known, 'kind': kind, 'payload': payload,
                         'knownAfterFrameReceipt': known > frame_copy['observedClientNs'],
                         'originContext': origins.get(payload.get('requestId'))}
                if kind == 'receipt':
                    prior = receipts.setdefault(payload['requestId'], [])
                    event['duplicateOfSequence'] = next((p['sequence'] for p in prior
                                                        if p['payload'] == payload), None)
                    prior.append(event)
                    event['reportedCompletedStepCount'] = len(payload['appliedSteps'])
                    event['partialInputPossible'] = True
                    event['serverTimeOrderAnomaly'] = (payload['endedAtMs'] < payload['acceptedAtMs']
                        or any(step['startedAtMs'] < payload['acceptedAtMs']
                               or step['startedAtMs'] > payload['endedAtMs']
                               for step in payload['appliedSteps']))
                events.append(event)
            conflicts = []
            for request, items in receipts.items():
                conflict = any(item['payload'] != items[0]['payload'] for item in items[1:])
                for item in items:
                    item['receiptConflict'] = conflict
                if conflict:
                    conflicts.append(request)
            document = {'schema': SCHEMA, 'generation': self._generation,
                        'identity': json.loads(self._identity), 'frame': frame_copy,
                        'decisionContext': current_decision,
                        'decisionContextChanges': [key for key in _DECISION_FIELDS
                            if self._previous_decision is not None
                            and self._previous_decision[key] != current_decision[key]],
                        'cutoffClientNs': cutoff_client_ns, 'events': events,
                        'coverage': {'maxEvents': self._limit, 'windowNs': self._window,
                                     'evictedEvents': self._evicted if self._evicted_ns <= cutoff_client_ns else None,
                                     'retentionAdvancedBeyondCutoff': self._evicted_ns > cutoff_client_ns,
                                     'outsideWindowEvents': len(visible) - len(selected),
                                     'receiptConflictRequestIds': conflicts,
                                     'historicalUntimestampedEventsIncluded': False,
                                     'deduplicationScope': 'retained_selected_events_only'},
                        'semantics': {'knowledgeClock': 'client_perf_counter_ns',
                                      'serverClock': 'session_relative_ms_not_client_clock',
                                      'startedAtMs': 'pre_dispatch', 'endedAtMs': 'pre_release',
                                      'nonemptyStep': 'keys_and_mouse_calls_returned_not_game_effect',
                                      'ongoingHold': 'unknown', 'releaseSuccess': 'unknown',
                                      'observedGameEffect': 'unknown', 'authority': 'none'}}
            if self._ongoing is not None:
                document['ongoingInput'] = self._ongoing.snapshot(cutoff_client_ns, frame_copy['observedClientNs'], origins)
            self._previous_decision = current_decision
            return ExecutionSnapshot(_json(document, 2 * 1024 * 1024), _SNAPSHOT_KEY)


def render_gamescaling_context(snapshot):
    """Bound model text, label receipt age, and prefer recent reported input over plans."""
    if type(snapshot) is not ExecutionSnapshot:
        raise TypeError('ExecutionSnapshot required')
    data = snapshot.to_dict()
    frame = data['frame']
    timing = {'clock': 'agent_session_ms', 'hostRequestMs': frame.get('capturedAtMs'),
              'sourceTimestampKind': frame.get('sourceTimestampKind', 'unknown')}
    host, source = frame.get('hostSnapshot'), frame.get('sourceFrame')
    if type(host) is dict:
        timing['hostAcquisitionMs'] = [host.get('startedAtMs'), host.get('completedAtMs')]
    if type(source) is dict:
        timing['wgcReportedMs'] = source.get('capturedAtMs')
        timing['firstAcquiredMs'] = source.get('acquiredAtMs')
        timing['freshnessMs'] = source.get('freshnessAtMs')
        timing['freshnessKind'] = source.get('freshnessClockKind')
    rows = []
    duplicate_count = 0
    for event in data['events']:
        if event.get('duplicateOfSequence') is not None:
            duplicate_count += 1
            continue
        payload = event['payload']
        row = {'seq': event['sequence'], 'kind': event['kind'],
               'knownAfterImageReceipt': event['knownAfterFrameReceipt'],
               'origin': event['originContext']}
        for key in ('requestId', 'state', 'status', 'reason', 'droppedReceipts'):
            if key in payload:
                row[key] = payload[key]
        if event['kind'] == 'receipt':
            row.update(steps=payload['appliedSteps'], conflict=event['receiptConflict'],
                       serverTimeOrderUnknown=event['serverTimeOrderAnomaly'])
        elif event['kind'] == 'proposal':
            row['plannedSteps'] = payload['steps']
        rows.append(row)
    result = {'format': SCHEMA, 'frameId': data['frame']['frameId'],
              'decisionContext': data['decisionContext'], 'imageTiming': timing,
              'cutoffClientNs': data['cutoffClientNs'],
              'ageSinceImageReceiptMs': (data['cutoffClientNs'] - frame['observedClientNs']) / 1_000_000,
              'imageReceiptAgeBasis': 'client_perf_counter_ns; receipt-to-decision lower bound on image age, not game-render age',
              'limits': 'Evidence only; admission is not execution. Receipt steps mean aggregate input calls returned. startedAtMs is PRE-dispatch; endedAtMs is PRE-release and can be stale. Earlier dispatch stamp does NOT prove completion before image. Partial input possible. Hold/release/game effect UNKNOWN. Knowledge after image receipt is not input after image.',
              'historyIncomplete': bool(data['coverage']['evictedEvents'] or
                                        data['coverage']['outsideWindowEvents'] or
                                        data['coverage']['retentionAdvancedBeyondCutoff']),
              'projectionOmittedEvents': 0, 'events': rows}
    result['duplicateReceiptsOmitted'] = duplicate_count
    if 'ongoingInput' in data:
        result['ongoingSoftwareInput'] = telemetry_projection(data['ongoingInput'])
        # The added telemetry does not replace terminal-receipt timestamp qualifications.
        result['limits'] += (' Call stages and tracked keys are software reports, not physical state. '
                             'Telemetry sample is publication time, not image time. Blocked input calls block snapshots.')
    while True:
        rendered = json.dumps(result, ensure_ascii=True, separators=(',', ':'), allow_nan=False)
        if len(rendered.encode('utf-8')) <= MODEL_TEXT_LIMIT:
            return rendered
        if not result['events']:
            raise ValueError('context_renderer_fixed_budget')
        # Keep original sequence order; discard plans before the newest reported receipt.
        candidates = result['events']
        proposal = next((i for i, row in enumerate(candidates) if row['kind'] == 'proposal'), None)
        newest_receipt = next((i for i in range(len(candidates) - 1, -1, -1)
                               if candidates[i]['kind'] == 'receipt'), None)
        remove = proposal if proposal is not None else next(
            (i for i in range(len(candidates)) if i != newest_receipt), 0)
        candidates.pop(remove)
        result['projectionOmittedEvents'] += 1
