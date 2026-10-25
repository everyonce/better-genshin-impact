"""Producer-shaped inert coverage for the unpublished ongoing-input contract."""
import copy
import json
from pathlib import Path
import unittest

import ongoing_input as oi
from execution_context import ExecutionContext, render_gamescaling_context
from execution_bridge import ExecutionContextBridge

IDENTITY = {'sessionId': 'session-one', 'ownerEpoch': 'owner-one'}
CAP = {'version': 1, 'eventCapacity': 256, 'clock': oi.CLOCK, 'sessionOriginAtStopwatchTicks': 123456,
       'stopwatchFrequency': 10_000_000, 'snapshotBasis': 'controller_lock_publication_time',
       'retainedEvents': True, 'observesBlockedCallConcurrently': False, 'physicalExecutionProven': False}
FRAME = {'frameId': 1, 'observedClientNs': 5, 'capturedAtMs': 4}


def event(sequence, *, operation='keyDown', stage=None, key='W', request='request-one', origin='dispatch'):
    """Match the actual camel-case AgentInputCallEvent/AgentInputCall DTOs."""
    stage = stage or ('started' if sequence % 2 else 'returned')
    return {'sequence': sequence, 'atMs': sequence + 10, 'requestId': request,
            'modelId': 'model-one' if request else None, 'frameId': 1 if request else None,
            'stepIndex': 0 if request else None, 'origin': origin,
            'call': {'callId': (sequence + 1) // 2, 'operation': operation, 'stage': stage,
                     'key': key, 'mouseDx': 0, 'mouseDy': 0,
                     'error': 'InvalidOperationException' if stage == 'failed' else None}}


def packet(events=None, *, sample=40, active=True):
    """Represent publication-time state independently from image acquisition and intent."""
    events = [event(1), event(2)] if events is None else events
    return {'version': 1, 'clock': oi.CLOCK, 'observesBlockedCallConcurrently': False,
            'physicalExecutionProven': False, 'sampledAtMs': sample, 'telemetryComplete': True,
            'trackedState': {'heldKeys': ['W'], 'executionUncertain': False,
                             'releaseOutcome': 'not_requested', 'telemetryIncomplete': False},
            'active': {'requestId': 'request-one', 'modelId': 'model-one', 'frameId': 1,
                       'acceptedAtMs': 8, 'expiresAtMs': 200, 'startBeforeMs': 100,
                       'nextStepAtMs': 60, 'nextStepIndex': 1, 'lastAttemptedStepIndex': 0,
                       'lastDispatchOutcome': 'returned', 'nextIntendedKeys': ['A'],
                       'lastAppliedKeys': ['W']} if active else None,
            'lastInputEvent': copy.deepcopy(events[-1]) if events else None,
            'firstSequence': events[0]['sequence'] if events else 0,
            'lastSequence': events[-1]['sequence'] if events else 0, 'evictedEvents': 0, 'events': events}


def ledger():
    """Start an explicit candidate-only connection with no authority or bridge IO."""
    return ExecutionContext(IDENTITY, input_telemetry=CAP)


def feed(context, value, known=10, **kwargs):
    """Use public response intake with the authenticated identity/capability each time."""
    return context.record_response('status', {'type': 'status', 'executionContext': value},
                                   observed_client_ns=known, identity=IDENTITY, input_telemetry=CAP, **kwargs)


def snapshot(context, cutoff=10):
    """Read only public immutable snapshots; do not construct their private representation."""
    return context.snapshot(FRAME, cutoff_client_ns=cutoff).to_dict()['ongoingInput']


class ContractCases(unittest.TestCase):
    """Version, session, request and clock mistakes never become claimed support."""
    def test_missing_capability_rejects_future_field(self):
        with self.assertRaisesRegex(ValueError, 'capability_required'):
            feed(ExecutionContext(IDENTITY), packet())

    def test_wrong_or_boolean_version_rejected(self):
        for version in (True, 1.0, 2):
            with self.subTest(version=version), self.assertRaises(ValueError):
                ExecutionContext(IDENTITY, input_telemetry={**CAP, 'version': version})

    def test_capability_semantics_and_clock_are_exact(self):
        for key, value in [('clock', 'QPC'), ('eventCapacity', 255), ('physicalExecutionProven', True),
                           ('observesBlockedCallConcurrently', True), ('stopwatchFrequency', 0),
                           ('sessionOriginAtStopwatchTicks', True), ('retainedEvents', False)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                ExecutionContext(IDENTITY, input_telemetry={**CAP, key: value})

    def test_identity_required_on_feature_intake(self):
        with self.assertRaisesRegex(ValueError, 'negotiation_changed'):
            ledger().record_response('status', {'type': 'status', 'executionContext': packet()},
                                     observed_client_ns=10, input_telemetry=CAP)

    def test_epoch_drift_rejected(self):
        with self.assertRaisesRegex(ValueError, 'identity_changed'):
            ledger().record_response('status', {'type': 'status', 'executionContext': packet()},
                observed_client_ns=10, identity={**IDENTITY, 'ownerEpoch': 'other'}, input_telemetry=CAP)

    def test_clock_origin_drift_rejected(self):
        with self.assertRaisesRegex(ValueError, 'negotiation_changed'):
            ledger().record_response('status', {'type': 'status', 'executionContext': packet()},
                observed_client_ns=10, identity=IDENTITY, input_telemetry={**CAP, 'sessionOriginAtStopwatchTicks': 0})

    def test_missing_negotiated_snapshot_rejected(self):
        with self.assertRaisesRegex(ValueError, 'snapshot_missing'):
            ledger().record_response('frame', {'type': 'waiting'}, observed_client_ns=10,
                                     identity=IDENTITY, input_telemetry=CAP)

    def test_action_ack_does_not_require_or_create_ongoing_state(self):
        context = ledger()
        context.record_response('action', {'type': 'accepted', 'requestId': 'r'}, observed_client_ns=10,
            expected_request_id='r', identity=IDENTITY, input_telemetry=CAP)
        self.assertIsNone(snapshot(context)['state'])

    def test_request_join_conflict_rejected(self):
        context = ledger()
        context.record('proposal', {'requestId': 'request-one', 'modelId': 'other', 'frameId': 1},
                       observed_client_ns=1)
        with self.assertRaisesRegex(ValueError, 'request_identity_conflict'):
            feed(context, packet())

    def test_old_request_origin_survives_replacement(self):
        context = ledger()
        context.record('proposal', {'requestId': 'request-one', 'modelId': 'model-one', 'frameId': 1},
                       observed_client_ns=1, decision_context={'controlEpoch': 2})
        value = packet(); value['active']['requestId'] = 'new-request'
        feed(context, value)
        result = snapshot(context)
        self.assertEqual(result['state']['active']['requestId'], 'new-request')
        self.assertEqual(result['events'][0]['event']['requestId'], 'request-one')
        self.assertEqual(result['events'][0]['originContext']['controlEpoch'], 2)

    def test_reset_requires_fresh_negotiation(self):
        context = ledger(); feed(context, packet())
        context.reset_identity(IDENTITY, observed_client_ns=11)
        with self.assertRaisesRegex(ValueError, 'capability_required'):
            feed(context, packet(), 12)

    def test_reset_explicit_capability_resets_sequence(self):
        context = ledger(); feed(context, packet())
        context.reset_identity(IDENTITY, observed_client_ns=11, input_telemetry=CAP)
        feed(context, packet([]), 12)
        result = context.snapshot({**FRAME, 'observedClientNs': 11}, cutoff_client_ns=12).to_dict()
        self.assertEqual(result['generation'], 1)
        self.assertEqual(result['ongoingInput']['events'], [])


class EvidenceCases(unittest.TestCase):
    """Call attempts, returned software state, sequence loss and knowledge cutoffs stay distinct."""
    def test_intent_tracked_and_physical_state_separate(self):
        context = ledger(); feed(context, packet())
        result = snapshot(context)
        self.assertEqual(result['state']['active']['nextIntendedKeys'], ['A'])
        self.assertEqual(result['state']['trackedState']['heldKeys'], ['W'])
        self.assertEqual(result['physicalHeldState'], 'unknown')
        self.assertEqual(result['releaseSuccess'], 'unknown')
        self.assertEqual(result['gameEffect'], 'unknown')

    def test_partial_failure_retains_completed_and_failed_calls(self):
        value = packet([event(1), event(2), event(3, key='E'), event(4, key='E', stage='failed')])
        value['active']['lastDispatchOutcome'] = 'failed'
        value['active']['lastAppliedKeys'] = None
        value['trackedState']['executionUncertain'] = True
        context = ledger(); feed(context, value)
        result = snapshot(context)
        self.assertEqual([r['event']['call']['stage'] for r in result['events']], ['started', 'returned', 'started', 'failed'])
        self.assertEqual(result['state']['trackedState']['heldKeys'], ['W'])

    def test_release_return_is_unverified(self):
        rows = [event(1, operation='releaseAll', key=None, origin='release:client_release'),
                event(2, operation='releaseAll', stage='returned_unverified', key=None, origin='release:client_release')]
        value = packet(rows, active=False)
        value['trackedState'] = {'heldKeys': [], 'executionUncertain': True,
                                 'releaseOutcome': 'returned_unverified', 'telemetryIncomplete': False}
        context = ledger(); feed(context, value)
        result = snapshot(context)
        self.assertEqual(result['events'][-1]['event']['origin'], 'release:client_release')
        self.assertEqual(result['releaseSuccess'], 'unknown')

    def test_mouse_delta_is_requested_not_measured(self):
        rows = [event(i, operation='mouseMove', key=None) for i in (1, 2)]
        for row in rows: row['call'].update(mouseDx=-7, mouseDy=4)
        context = ledger(); feed(context, packet(rows))
        self.assertEqual(snapshot(context)['events'][1]['event']['call']['mouseDx'], -7)

    def test_detachment_at_intake_and_snapshot(self):
        value = packet(); context = ledger(); feed(context, value)
        value['events'][0]['call']['key'] = 'E'; value['trackedState']['heldKeys'].clear()
        first = snapshot(context); first['events'].clear()
        self.assertEqual(snapshot(context)['events'][0]['event']['call']['key'], 'W')
        self.assertEqual(snapshot(context)['state']['trackedState']['heldKeys'], ['W'])

    def test_duplicate_snapshots_do_not_duplicate_event_payloads(self):
        context = ledger(); feed(context, packet()); feed(context, packet(sample=45), 11)
        self.assertEqual(len(context._ongoing.events), 2)
        result = snapshot(context, 11)
        self.assertEqual(len(result['events']), 2)
        self.assertTrue(all(row['firstObservedClientNs'] == 10 for row in result['events']))

    def test_sequence_conflict_rejected_without_mutating_prior(self):
        context = ledger(); feed(context, packet())
        bad = packet(sample=45); bad['events'][0]['call']['key'] = 'E'
        with self.assertRaisesRegex(ValueError, 'sequence_content_conflict'):
            feed(context, bad, 11)
        self.assertEqual(snapshot(context, 11)['state']['sampledAtMs'], 40)

    def test_counter_and_sample_regressions_rejected(self):
        context = ledger(); feed(context, packet())
        for bad in (packet([]), packet(sample=39)):
            with self.assertRaises(ValueError): feed(context, bad, 11)

    def test_server_eviction_is_not_assumed_client_loss(self):
        context = ledger(); feed(context, packet())
        value = packet([event(i) for i in range(3, 259)], sample=300); value['evictedEvents'] = 2
        feed(context, value, 20)
        result = snapshot(context, 20)
        self.assertEqual(result['state']['evictedEvents'], 2)
        self.assertEqual(result['coverage']['unobservedSequenceCount'], 0)

    def test_first_delivery_missing_prefix_is_explicit(self):
        context = ledger(); value = packet([event(i) for i in range(3, 259)], sample=300)
        value['evictedEvents'] = 2; feed(context, value)
        self.assertEqual(snapshot(context)['coverage']['unobservedSequenceCount'], 2)

    def test_later_knowledge_not_available_at_earlier_cutoff(self):
        context = ledger(); feed(context, packet(), 20)
        self.assertIsNone(snapshot(context, 10)['state'])
        self.assertEqual(snapshot(context, 20)['observedClientNs'], 20)

    def test_old_state_after_event_eviction_reports_missing_payloads(self):
        context = ledger(); feed(context, packet(), 10)
        value = packet([event(i) for i in range(3, 259)], sample=300); value['evictedEvents'] = 2
        feed(context, value, 20)
        old = snapshot(context, 15)
        self.assertEqual(old['state']['sampledAtMs'], 40)
        self.assertEqual(old['events'], [])
        self.assertEqual(old['coverage']['clientEventHistoryMissing'], 2)

    def test_only_small_state_history_is_repeated(self):
        context = ledger()
        for n in range(20): feed(context, packet(sample=40+n), 10+n)
        self.assertEqual(len(context._ongoing.events), 2)
        self.assertEqual(len(context._ongoing.states), oi.STATE_CAPACITY)
        self.assertTrue(all('"events"' not in state[1] for state in context._ongoing.states))

    def test_null_clock_requires_incomplete_and_latches(self):
        context = ledger(); value = packet(); value['sampledAtMs'] = None
        with self.assertRaises(ValueError): feed(context, value)
        value['telemetryComplete'] = False; feed(context, value)
        with self.assertRaisesRegex(ValueError, 'incomplete_latch_regression'):
            feed(context, packet(), 11)

    def test_sequence_hole_only_permitted_as_incomplete(self):
        value = packet([event(1), event(3)]); context = ledger()
        with self.assertRaisesRegex(ValueError, 'complete_sequence_gap'): feed(context, value)
        value['telemetryComplete'] = False; feed(context, value)
        self.assertEqual(snapshot(context)['coverage']['unobservedSequenceCount'], 1)

    def test_duplicate_last_event_has_exact_types(self):
        value = packet(); value['lastInputEvent']['call']['callId'] = True
        with self.assertRaises(ValueError): feed(ledger(), value)

    def test_event_capacity_and_future_fields_rejected(self):
        for bad in (packet([event(i) for i in range(1, 258)], sample=300), {**packet(), 'future': True}):
            with self.assertRaises(ValueError): feed(ledger(), bad)

    def test_model_projection_bounded_and_truthful(self):
        context = ledger(); feed(context, packet())
        rendered = render_gamescaling_context(context.snapshot(FRAME, cutoff_client_ns=10))
        self.assertLessEqual(len(rendered.encode()), 2048)
        value = json.loads(rendered)
        self.assertIn('software', value['limits'])
        self.assertIn('not physical', value['limits'])
        self.assertIn('ongoingSoftwareInput', value)

    def test_projection_does_not_mutate_snapshot_and_marks_omissions(self):
        context = ledger(); feed(context, packet())
        value = snapshot(context); value['state']['trackedState']['heldKeys'] = ['KEY'+str(n)+'X'*25 for n in range(80)]
        before = copy.deepcopy(value); projected = oi.projection(value)
        self.assertEqual(value, before)
        self.assertIn('trackedKeys', projected['omittedFields'])
        self.assertEqual(projected['omittedTrackedKeyCount'], 80)


class FakeBridge:
    """Inert transport with the candidate hello, no handle or external side effect."""
    def __init__(self, negotiated=True):
        self.hello = {**IDENTITY, 'clock': oi.CLOCK, 'clockFrequency': 1000}
        if negotiated: self.hello['inputTelemetry'] = copy.deepcopy(CAP)
        self.calls = []

    def request(self, command, **kwargs):
        self.calls.append(command)
        return {'type': 'frame', 'frameId': 1, 'capturedAtMs': 4, 'executionContext': packet()}, b'RGB'


class BridgeAndLegacyCases(unittest.TestCase):
    """The public wrapper negotiates telemetry; ordinary R45 snapshots retain their exact bytes."""
    def test_bridge_intake_and_cutoff(self):
        bridge = FakeBridge(); ticks = iter((10, 11, 12))
        wrapper = ExecutionContextBridge(bridge, clock=lambda: next(ticks))
        frame, rgb = wrapper.request('frame')
        result = wrapper.snapshot(frame, decision_context={}).to_dict()
        self.assertEqual(rgb, b'RGB')
        self.assertEqual(result['ongoingInput']['observedClientNs'], 11)
        self.assertEqual(result['cutoffClientNs'], 12)
        self.assertEqual(bridge.calls, ['frame'])

    def test_bridge_hello_clock_mismatch(self):
        bridge = FakeBridge(); bridge.hello['clockFrequency'] = 1000.0
        with self.assertRaisesRegex(ValueError, 'hello_clock'): ExecutionContextBridge(bridge)

    def test_bridge_epoch_drift_is_not_ingested(self):
        bridge = FakeBridge(); wrapper = ExecutionContextBridge(bridge, clock=lambda: 10)
        bridge.hello['ownerEpoch'] = 'other'
        with self.assertRaisesRegex(ValueError, 'identity_changed'): wrapper.request('frame')

    def test_legacy_snapshot_and_renderer_byte_equivalence(self):
        """Compare exact bytes from the pinned original using only a local golden fixture."""
        path = Path(__file__).resolve().parent/'fixtures/execution_context_legacy_v1.json'
        golden = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(golden['schema'], 'execution-context-legacy-golden-v1')
        self.assertEqual(golden['baseline']['sha256'],
                         '3ae2f51bd52b28e57fd91dfc51655bd7f72020f901a32f629e1de36a9c837c42')
        inputs = golden['inputs']
        self.assertEqual(inputs['identity'], IDENTITY)
        self.assertEqual(inputs['frame'], FRAME)
        context = ExecutionContext(inputs['identity'])
        context.record('proposal', inputs['proposal']['payload'],
                       observed_client_ns=inputs['proposal']['observedClientNs'])
        context.record_response('action', inputs['admission']['response'],
                                observed_client_ns=inputs['admission']['observedClientNs'],
                                expected_request_id=inputs['admission']['expectedRequestId'])
        frozen = context.snapshot(inputs['frame'], cutoff_client_ns=inputs['cutoffClientNs'])
        self.assertEqual(frozen._document_json.encode('utf-8'),
                         golden['expected']['snapshotJsonUtf8'].encode('utf-8'))
        self.assertEqual(render_gamescaling_context(frozen).encode('utf-8'),
                         golden['expected']['renderedTextUtf8'].encode('utf-8'))


class ProjectionCorrectionCases(unittest.TestCase):
    """Keep actual software-call evidence and receipt-time limits under both budgets."""
    def single_call(self, stage='returned'):
        """Use the reviewed ordinary active-state shape with one reported call stage."""
        row = event(1, stage=stage, request='a' * 32)
        row.update(atMs=190.0, modelId='open-p2p', frameId=2)
        value = packet([row], sample=200.0)
        value['active'].update(requestId='a' * 32, modelId='open-p2p', frameId=2,
            acceptedAtMs=180.0, expiresAtMs=300.0, startBeforeMs=230.0,
            nextStepAtMs=240.0, nextIntendedKeys=['W'], lastDispatchOutcome=stage)
        if stage == 'failed':
            value['trackedState']['executionUncertain'] = True
        context = ledger(); feed(context, value)
        return snapshot(context)

    def untrimmed(self, data):
        """Reconstruct only the documented projection shape for the byte-bound regression."""
        state = data['state']; item = data['events'][-1]; row = item['event']
        return {'version': 1, 'state': {'sampleMs': state['sampledAtMs'],
            'knownAfterImage': data['knownAfterImageReceipt'], 'complete': state['telemetryComplete'],
            'tracked': copy.deepcopy(state['trackedState']), 'intended': copy.deepcopy(state['active'])},
            'calls': [{'seq': row['sequence'], 'ms': row['atMs'], 'request': row['requestId'],
                'step': row['stepIndex'], 'origin': row['origin'], 'call': row['call'],
                'knownAfterImage': item['knownAfterImageReceipt']}],
            'omittedCalls': 0, 'omittedFields': [], 'loss': [0, 0, 0]}

    def test_reviewed_787_byte_shape_keeps_returned_call(self):
        data = self.single_call(); before = copy.deepcopy(data)
        self.assertEqual(len(oi.encode(self.untrimmed(data), 4096).encode()), 787)
        result = oi.projection(data)
        self.assertLessEqual(len(oi.encode(result, 4096).encode()), 720)
        self.assertEqual(result['calls'][0]['call']['stage'], 'returned')
        self.assertEqual(result['omittedCalls'], 0)
        self.assertEqual(result['omittedFields'], ['activeIntention'])
        self.assertIsNone(result['state']['intended'])
        self.assertEqual(data, before)

    def test_failed_call_survives_verbose_active_intention(self):
        result = oi.projection(self.single_call('failed'))
        self.assertEqual(result['calls'][-1]['call']['stage'], 'failed')
        self.assertEqual(result['calls'][-1]['call']['error'], 'InvalidOperationException')
        self.assertTrue(result['state']['tracked']['executionUncertain'])
        self.assertEqual(result['omittedCalls'], 0)
        self.assertIn('activeIntention', result['omittedFields'])

    def test_latest_call_and_order_survive_older_call_omission(self):
        context = ledger(); feed(context, packet([event(n) for n in range(1, 5)]))
        result = oi.projection(snapshot(context))
        seq = [row['seq'] for row in result['calls']]
        self.assertTrue(seq); self.assertEqual(seq[-1], 4)
        self.assertEqual(seq, sorted(seq))
        self.assertEqual(result['omittedCalls'] + len(seq), 4)
        self.assertIn('activeIntention', result['omittedFields'])

    def test_latest_call_precedes_verbose_tracked_keys(self):
        data = self.single_call()
        data['state']['trackedState']['heldKeys'] = ['KEY' + str(n) + 'X' * 25 for n in range(80)]
        before = copy.deepcopy(data); result = oi.projection(data)
        self.assertEqual(result['calls'][-1]['call']['stage'], 'returned')
        self.assertEqual(result['omittedCalls'], 0)
        self.assertEqual(result['omittedTrackedKeyCount'], 80)
        self.assertEqual(set(result['omittedFields']), {'activeIntention', 'trackedKeys'})
        self.assertEqual(data, before)

    def receipt_text(self, ended=20.0):
        """Use public intake plus the actual terminal-receipt field layout."""
        context = ledger(); feed(context, packet([], active=False))
        context.record('receipt', {'requestId': 'r', 'modelId': 'm', 'frameId': 1,
            'status': 'completed', 'reason': 'horizon_complete', 'acceptedAtMs': 10.0,
            'endedAtMs': ended, 'appliedSteps': [{'index': 0, 'startedAtMs': 12.0,
                'keys': ['W'], 'mouseDx': 0, 'mouseDy': 0}]}, observed_client_ns=11)
        frozen = context.snapshot(FRAME, cutoff_client_ns=12); before = frozen.to_dict()
        text = render_gamescaling_context(frozen)
        self.assertLessEqual(len(text.encode()), 2048)
        self.assertEqual(before, frozen.to_dict())
        return json.loads(text)

    def test_telemetry_and_retained_receipt_keep_all_time_cautions(self):
        result = self.receipt_text()
        self.assertEqual(result['events'][-1]['kind'], 'receipt')
        for phrase in ('PRE-dispatch', 'PRE-release', 'can be stale',
            'Earlier dispatch stamp does NOT prove completion before image',
            'Knowledge after image receipt is not input after image', 'publication time', 'not physical'):
            self.assertIn(phrase, result['limits'])
        self.assertTrue(result['events'][-1]['knownAfterImageReceipt'])
        self.assertIn('ongoingSoftwareInput', result)

    def test_stale_receipt_stamp_is_retained_as_uncertain(self):
        result = self.receipt_text(ended=5.0)
        self.assertTrue(result['events'][-1]['serverTimeOrderUnknown'])
        self.assertEqual(result['events'][-1]['steps'][0]['startedAtMs'], 12.0)
        self.assertIn('PRE-release and can be stale', result['limits'])


if __name__ == '__main__':
    unittest.main()
