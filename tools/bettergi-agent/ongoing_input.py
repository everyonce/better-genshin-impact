"""Capability-gated software-call evidence, never physical input authority."""

from collections import OrderedDict, deque
import json
import math

CLOCK = 'monotonic milliseconds since session start'
EVENT_CAPACITY = 256
STATE_CAPACITY = 16
PACKET_BYTES = 384 * 1024
EVENT_BYTES = 2048
STATE_BYTES = 16 * 1024
RESPONSE_TYPES = {'frame', 'waiting', 'status', 'released', 'stopped'}


def require(value, reason):
    """Reject ambiguous candidate telemetry without changing input authority."""
    if not value:
        raise ValueError('ongoing_' + reason)


def integer(value, name, minimum=0, maximum=(1 << 63) - 1):
    """Preserve exact .NET identities and counters, including Boolean rejection."""
    require(type(value) is int and minimum <= value <= maximum, name)
    return value


def text(value, name, maximum=160, empty=False):
    """Bound untrusted wire strings without normalizing their meaning."""
    require(type(value) is str and (empty or bool(value)) and len(value) <= maximum
            and all(ord(c) >= 32 for c in value), name)
    return value


def number(value, name, nullable=False):
    """Keep session milliseconds separate from the client knowledge clock."""
    if nullable and value is None:
        return None
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, name)
    return value


def shape(value, names, name):
    """Version one accepts only the explicitly reviewed producer fields."""
    require(type(value) is dict and set(value) == set(names.split()), name)


def encode(value, bound):
    """Detach exact JSON types and bound retained serialization, not total process memory."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
    require(len(encoded.encode()) <= bound, 'byte_bound')
    return encoded


def keys(value, nullable=False):
    """Preserve intended aliases separately from normalized tracked keys."""
    if value is None and nullable:
        return
    require(type(value) is list and len(value) <= 80, 'keys')
    for key in value:
        text(key, 'key', 32)
    require(len(set(value)) == len(value), 'duplicate_keys')


def capability(value):
    """Bind the unpublished v1 hello contract and its exact session clock origin."""
    shape(value, 'version eventCapacity clock sessionOriginAtStopwatchTicks stopwatchFrequency '
          'snapshotBasis retainedEvents observesBlockedCallConcurrently physicalExecutionProven', 'capability')
    require(type(value['version']) is int and value['version'] == 1, 'capability_version')
    require(type(value['eventCapacity']) is int and value['eventCapacity'] == EVENT_CAPACITY, 'event_capacity')
    require(value['clock'] == CLOCK and value['snapshotBasis'] == 'controller_lock_publication_time', 'clock_basis')
    integer(value['sessionOriginAtStopwatchTicks'], 'session_origin')
    integer(value['stopwatchFrequency'], 'stopwatch_frequency', 1)
    require(value['retainedEvents'] is True and value['observesBlockedCallConcurrently'] is False
            and value['physicalExecutionProven'] is False, 'capability_semantics')
    return encode(value, 2048)


def request_fields(row, proposals, nullable=False):
    """Join only exact request IDs; older replacement/release origins may remain unknown."""
    if nullable and row['requestId'] is None:
        require(row['modelId'] is None and row['frameId'] is None, 'unbound_request')
        return
    text(row['requestId'], 'request_id', 128)
    text(row['modelId'], 'model_id', empty=True)
    integer(row['frameId'], 'frame_id', 1)
    prior = proposals.get(row['requestId'])
    if prior is not None:
        require(row['modelId'] == prior.get('modelId') and row['frameId'] == prior.get('frameId'),
                'request_identity_conflict')


def event(row, proposals):
    """Retain call attempts/results; never derive held state or release success from them."""
    shape(row, 'sequence atMs requestId modelId frameId stepIndex origin call', 'event_shape')
    integer(row['sequence'], 'event_sequence', 1)
    number(row['atMs'], 'event_time', True)
    request_fields(row, proposals, True)
    if row['stepIndex'] is not None:
        integer(row['stepIndex'], 'step_index', 0, 5)
    text(row['origin'], 'origin')
    call = row['call']
    shape(call, 'callId operation stage key mouseDx mouseDy error', 'call_shape')
    integer(call['callId'], 'call_id', 1)
    op, stage = call['operation'], call['stage']
    require(op in ('keyDown', 'keyUp', 'buttonDown', 'buttonUp', 'mouseMove', 'releaseAll'), 'operation')
    require(stage in ('started', 'failed', 'returned', 'returned_unverified', 'skipped_backend_changed'), 'stage')
    require(stage not in ('returned_unverified', 'skipped_backend_changed') or op == 'releaseAll', 'aggregate_stage')
    require(op != 'releaseAll' or stage != 'returned', 'aggregate_return')
    for axis in ('mouseDx', 'mouseDy'):
        integer(call[axis], axis, -1_000_000, 1_000_000)
    if op in ('mouseMove', 'releaseAll'):
        require(call['key'] is None, 'non_key_operation')
    else:
        text(call['key'], 'call_key', 32)
        require(call['mouseDx'] == call['mouseDy'] == 0, 'key_delta')
        if op.startswith('button'):
            require(call['key'] in ('LBUTTON', 'RBUTTON', 'MBUTTON'), 'button_key')
    if op == 'releaseAll':
        require(call['mouseDx'] == call['mouseDy'] == 0, 'release_delta')
    if stage == 'failed':
        text(call['error'], 'error_type', 128)
    else:
        require(call['error'] is None, 'unexpected_error')
    return encode(row, EVENT_BYTES)


def validate(value, proposals):
    """Validate a detached controller snapshot, permitting explicitly incomplete telemetry."""
    shape(value, 'version clock observesBlockedCallConcurrently physicalExecutionProven sampledAtMs '
          'telemetryComplete trackedState active lastInputEvent firstSequence lastSequence evictedEvents events', 'snapshot_shape')
    require(type(value['version']) is int and value['version'] == 1 and value['clock'] == CLOCK, 'snapshot_version_clock')
    require(value['observesBlockedCallConcurrently'] is False and value['physicalExecutionProven'] is False, 'snapshot_semantics')
    require(type(value['telemetryComplete']) is bool, 'complete_type')
    sampled = number(value['sampledAtMs'], 'sample_time', True)
    state = value['trackedState']
    shape(state, 'heldKeys executionUncertain releaseOutcome telemetryIncomplete', 'tracked_state')
    keys(state['heldKeys'])
    require(type(state['executionUncertain']) is bool and type(state['telemetryIncomplete']) is bool, 'tracked_flags')
    require(state['releaseOutcome'] in ('not_requested', 'started', 'failed', 'returned_unverified',
                                      'skipped_backend_changed', 'unavailable'), 'release_outcome')
    require(not value['telemetryComplete'] or sampled is not None and not state['telemetryIncomplete'], 'false_completeness')
    active = value['active']
    if active is not None:
        shape(active, 'requestId modelId frameId acceptedAtMs expiresAtMs startBeforeMs nextStepAtMs '
              'nextStepIndex lastAttemptedStepIndex lastDispatchOutcome nextIntendedKeys lastAppliedKeys', 'active_shape')
        request_fields(active, proposals)
        for key in ('acceptedAtMs', 'expiresAtMs', 'nextStepAtMs'):
            number(active[key], key)
        number(active['startBeforeMs'], 'start_before', True)
        integer(active['nextStepIndex'], 'next_step', 0, 6)
        if active['lastAttemptedStepIndex'] is not None:
            integer(active['lastAttemptedStepIndex'], 'last_step', 0, 5)
        require(active['lastDispatchOutcome'] in ('not_started', 'started', 'returned', 'failed'), 'dispatch_outcome')
        keys(active['nextIntendedKeys'], True)
        keys(active['lastAppliedKeys'], True)
    for key in ('firstSequence', 'lastSequence', 'evictedEvents'):
        integer(value[key], key)
    events = value['events']
    require(type(events) is list and len(events) <= EVENT_CAPACITY, 'event_count')
    encoded = [event(row, proposals) for row in events]
    seqs = [row['sequence'] for row in events]
    require(seqs == sorted(set(seqs)), 'sequence_order')
    require(value['firstSequence'] == (seqs[0] if seqs else 0), 'first_sequence')
    require(not seqs or seqs[-1] <= value['lastSequence'], 'last_sequence')
    require(value['lastInputEvent'] == (events[-1] if events else None), 'last_event')
    if value['lastInputEvent'] is not None:
        # Validate the duplicate independently; Python equality alone accepts True == 1.
        event(value['lastInputEvent'], proposals)
        require(encode(value['lastInputEvent'], EVENT_BYTES) == encoded[-1], 'last_event_types')
    times = [row['atMs'] for row in events if row['atMs'] is not None]
    require(times == sorted(times) and (sampled is None or not times or times[-1] <= sampled), 'event_time_order')
    if value['telemetryComplete']:
        require(all(row['atMs'] is not None for row in events), 'missing_event_clock')
        require((value['lastSequence'] - value['firstSequence'] + 1 == len(seqs)
                 and all(seq == value['firstSequence'] + i for i, seq in enumerate(seqs))) if seqs
                else value['lastSequence'] == 0, 'complete_sequence_gap')
    metadata = dict(value)
    metadata.pop('events')
    metadata.pop('lastInputEvent')
    return encode(metadata, STATE_BYTES), encoded


class OngoingInput:
    """Keep 256 unique call stages and 16 small state snapshots under the caller's lock."""
    def __init__(self, declared):
        """Negotiate only the unpublished v1 producer; no lock, input, or clock calls."""
        self.capability_json = capability(declared)
        self.events = OrderedDict()
        self.states = deque()
        self.high = self.evicted = self.missing = self.state_evictions = 0
        self.first = 0
        self.sample = None
        self.incomplete = False

    def ingest(self, packet, *, observed_client_ns, proposals):
        """Commit validated evidence atomically; repeat sequences must be byte-identical."""
        detached = json.loads(encode(packet, PACKET_BYTES))
        metadata, events = validate(detached, proposals)
        require(detached['lastSequence'] >= self.high and detached['evictedEvents'] >= self.evicted, 'counter_regression')
        require(detached['firstSequence'] >= self.first, 'ring_regression')
        sample = detached['sampledAtMs']
        require(sample is None or self.sample is None or sample >= self.sample, 'sample_regression')
        require(not self.incomplete or detached['telemetryComplete'] is False, 'incomplete_latch_regression')
        added = []
        for raw, row in zip(events, detached['events']):
            seq = row['sequence']
            if seq in self.events:
                require(self.events[seq][1] == raw, 'sequence_content_conflict')
            elif seq > self.high:
                added.append((seq, raw))
        missing = self.missing + detached['lastSequence'] - self.high - len(added)
        # Only metadata is repeated per response; call payloads are retained once by sequence.
        for seq, raw in added:
            self.events[seq] = (observed_client_ns, raw)
        while len(self.events) > EVENT_CAPACITY:
            self.events.popitem(last=False)
        self.high, self.first, self.evicted = detached['lastSequence'], detached['firstSequence'], detached['evictedEvents']
        self.missing = missing
        self.sample = self.sample if sample is None else sample
        self.incomplete = self.incomplete or not detached['telemetryComplete']
        self.states.append((observed_client_ns, metadata, tuple(row['sequence'] for row in detached['events']), missing))
        while len(self.states) > STATE_CAPACITY:
            self.states.popleft()
            self.state_evictions += 1

    def snapshot(self, cutoff, frame_known, origins):
        """Select only knowledge available at cutoff; never infer state from later calls."""
        visible = [row for row in self.states if row[0] <= cutoff]
        result = {'schema': 'ongoing-software-input-v1', 'capability': json.loads(self.capability_json),
                  'state': None, 'events': [], 'coverage': {'stateUnavailableAtCutoff': not visible,
                  'clientStateEvictions': self.state_evictions, 'stateEvictionCountBasis': 'current_retention_not_historical_knowledge',
                  'clientEventHistoryMissing': 0, 'unobservedSequenceCount': None},
                  'physicalHeldState': 'unknown', 'releaseSuccess': 'unknown', 'gameEffect': 'unknown'}
        if not visible:
            return result
        known, raw, sequences, missing = visible[-1]
        state = json.loads(raw)
        result.update(state=state, observedClientNs=known, knownAfterImageReceipt=known > frame_known)
        for seq, (arrived, encoded) in self.events.items():
            if seq in sequences and arrived <= cutoff:
                row = json.loads(encoded)
                result['events'].append({'event': row, 'firstObservedClientNs': arrived,
                    'knownAfterImageReceipt': arrived > frame_known, 'originContext': origins.get(row['requestId'])})
        result['coverage'].update(clientEventHistoryMissing=len(sequences)-len(result['events']), unobservedSequenceCount=missing)
        return result


def projection(data, bound=720):
    """Bound the optional model projection, explicitly retaining any omitted-field counts."""
    state = data['state']
    result = {'version': 1, 'state': None, 'calls': [], 'omittedCalls': 0, 'omittedFields': []}
    if state is not None:
        result['state'] = {'sampleMs': state['sampledAtMs'], 'knownAfterImage': data['knownAfterImageReceipt'],
            'complete': state['telemetryComplete'], 'tracked': json.loads(encode(state['trackedState'], STATE_BYTES)),
            'intended': state['active']}
        result['loss'] = [state['evictedEvents'], data['coverage']['unobservedSequenceCount'],
                          data['coverage']['clientEventHistoryMissing']]
        for item in data['events'][-4:]:
            row = item['event']
            result['calls'].append({'seq': row['sequence'], 'ms': row['atMs'], 'request': row['requestId'],
                'step': row['stepIndex'], 'origin': row['origin'], 'call': row['call'],
                'knownAfterImage': item['knownAfterImageReceipt']})
        result['omittedCalls'] = len(data['events']) - len(result['calls'])
    while len(encode(result, 2 * 1024 * 1024).encode()) > bound:
        # Preserve reported call stages ahead of a verbose plan or tracked-key list.
        if result['state']['intended'] is not None:
            result['state']['intended'] = None
            result['omittedFields'].append('activeIntention')
        elif len(result['calls']) > 1:
            result['calls'].pop(0)
            result['omittedCalls'] += 1
        elif result['state']['tracked']['heldKeys']:
            result['omittedTrackedKeyCount'] = len(result['state']['tracked']['heldKeys'])
            result['state']['tracked']['heldKeys'] = []
            result['omittedFields'].append('trackedKeys')
        elif result['calls']:
            # An individually oversized call cannot be represented within the fixed cap.
            result['calls'].pop(0)
            result['omittedCalls'] += 1
        else:
            raise ValueError('ongoing_projection_fixed_budget')
    return result
