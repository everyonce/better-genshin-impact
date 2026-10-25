"""Pure-stdlib causal, retention and honest-evidence regression cases."""

from dataclasses import FrozenInstanceError
import json
import threading
import unittest

from execution_context import ExecutionContext, ExecutionSnapshot, render_gamescaling_context


def identity(session='s'):
    """Supply an explicit fake bridge identity without a game or transport."""
    return {'sessionId': session, 'ownerEpoch': 'owner'}


def receipt(request='r', status='completed', steps=True):
    """Use the exact R45 applied-step field names and pre-dispatch timestamps."""
    return {'requestId': request, 'modelId': 'gamescaling', 'frameId': 1,
            'status': status, 'reason': 'horizon_complete', 'acceptedAtMs': 10.,
            'endedAtMs': 20., 'appliedSteps': ([{'index': 0, 'startedAtMs': 12.,
                    'keys': ['W'], 'mouseDx': 0, 'mouseDy': 0}] if steps else [])}


class ContextTests(unittest.TestCase):
    """Check observable semantics, not implementation-specific containers."""

    def setUp(self):
        """Start every case with an independent bounded ledger."""
        self.c = ExecutionContext(identity())

    def snap(self, cutoff=100, frame_ns=90, **kwargs):
        """Use a declared image-receipt instant separate from source milliseconds."""
        return self.c.snapshot({'frameId': 2, 'observedClientNs': frame_ns,
                                'capturedAtMs': 11., 'sourceAgeMs': 5.,
                                'hostSnapshot': {'startedAtMs': 11.1, 'completedAtMs': 11.9}},
                               cutoff_client_ns=cutoff, **kwargs)

    def add(self, value=None, ns=95):
        """Record one freshly observed terminal report."""
        return self.c.record('receipt', receipt() if value is None else value, observed_client_ns=ns)

    def test_snapshot_detaches_intake_payload(self):
        value = receipt()
        self.add(value)
        value['appliedSteps'][0]['keys'].append('A')
        self.assertEqual(self.snap().to_dict()['events'][0]['payload']['appliedSteps'][0]['keys'], ['W'])

    def test_snapshot_detaches_all_returned_dicts(self):
        self.add()
        snapshot = self.snap()
        snapshot.to_dict()['events'][0]['payload']['status'] = 'invented'
        self.assertEqual(snapshot.to_dict()['events'][0]['payload']['status'], 'completed')
        with self.assertRaises(FrozenInstanceError):
            snapshot._document_json = '{}'

    def test_mid_predict_arrival_cannot_change_consumed_snapshot(self):
        snapshot = self.snap()
        before = render_gamescaling_context(snapshot)
        thread = threading.Thread(target=lambda: self.add(ns=101))
        thread.start()
        thread.join()
        self.assertEqual(before, render_gamescaling_context(snapshot))
        self.assertEqual(len(self.snap(102).to_dict()['events']), 1)

    def test_already_ingested_future_receipt_excluded(self):
        self.add(ns=110)
        data = self.snap().to_dict()
        self.assertEqual(data['events'], [])
        self.assertNotIn('horizon_complete', render_gamescaling_context(self.snap()))

    def test_cutoff_is_inclusive(self):
        self.add(ns=100)
        self.assertEqual(len(self.snap().to_dict()['events']), 1)

    def test_unknown_historical_knowledge_time_rejected(self):
        with self.assertRaises(ValueError):
            self.add(ns=None)
        self.assertEqual(self.snap().to_dict()['events'], [])

    def test_intake_clock_regression_leaves_evidence_unchanged(self):
        self.add(ns=95)
        with self.assertRaises(ValueError):
            self.add(receipt('late'), ns=94)
        self.assertEqual(len(self.snap().to_dict()['events']), 1)

    def test_equal_intake_time_allows_one_response_batch(self):
        self.add(receipt('a'))
        self.add(receipt('b'))
        self.assertEqual([e['sequence'] for e in self.snap().to_dict()['events']], [1, 2])

    def test_snapshot_clock_regression_rejected(self):
        self.snap()
        with self.assertRaises(ValueError):
            self.snap(99)

    def test_future_frame_rejected(self):
        with self.assertRaises(ValueError):
            self.snap(100, 101)

    def test_epoch_change_does_not_erase_old_input(self):
        old = {'controlEpoch': 1, 'readinessEpoch': 1, 'policyGoalVersion': 1, 'sourceEpoch': 'a'}
        new = dict(old, controlEpoch=2, policyGoalVersion=2, sourceEpoch='b')
        self.c.record('proposal', {'requestId': 'r', 'steps': []}, observed_client_ns=80,
                      decision_context=old)
        self.snap(90, 90, decision_context=old)
        self.add(ns=95)
        data = self.snap(decision_context=new).to_dict()
        self.assertEqual(data['events'][-1]['originContext'], old)
        self.assertEqual(data['decisionContext'], new)
        self.assertEqual(set(data['decisionContextChanges']), {'controlEpoch', 'policyGoalVersion', 'sourceEpoch'})

    def test_terminal_without_retained_proposal_origin_stays_unknown(self):
        self.add()
        self.assertIsNone(self.snap(decision_context={'controlEpoch': 2}).to_dict()['events'][0]['originContext'])

    def test_conflicting_proposal_origins_not_silently_selected(self):
        for ns, epoch in ((80, 1), (81, 2)):
            self.c.record('proposal', {'requestId': 'r'}, observed_client_ns=ns,
                          decision_context={'controlEpoch': epoch})
        self.add()
        self.assertIsNone(self.snap().to_dict()['events'][-1]['originContext'])

    def test_mismatched_lease_rejected(self):
        with self.assertRaises(ValueError):
            self.c.record('receipt', receipt(), observed_client_ns=95, identity=identity('other'))
        with self.assertRaises(ValueError):
            self.snap(identity=identity('other'))

    def test_reset_marks_discontinuity_and_invalidates_old_frame(self):
        self.add(ns=80)
        self.c.reset_identity(identity('new'), observed_client_ns=90)
        with self.assertRaises(ValueError):
            self.snap(frame_ns=89)
        data = self.snap().to_dict()
        self.assertEqual(data['generation'], 1)
        self.assertEqual(len(data['events']), 1)
        self.assertIn('release_unknown', data['events'][0]['payload']['reason'])

    def test_duplicate_receipt_has_one_model_input_evidence_row(self):
        self.add(ns=94)
        self.add(ns=95)
        snapshot = self.snap()
        self.assertEqual(snapshot.to_dict()['events'][1]['duplicateOfSequence'], 1)
        model = json.loads(render_gamescaling_context(snapshot))
        self.assertEqual(len(model['events']), 1)
        self.assertEqual(model['duplicateReceiptsOmitted'], 1)

    def test_conflicting_receipt_marks_both_versions_uncertain(self):
        self.add(ns=94)
        self.add(receipt(status='replaced'), ns=95)
        data = self.snap().to_dict()
        self.assertEqual(data['coverage']['receiptConflictRequestIds'], ['r'])
        self.assertTrue(all(e['receiptConflict'] for e in data['events']))

    def test_future_conflict_does_not_taint_earlier_cutoff(self):
        self.add(ns=94)
        self.add(receipt(status='replaced'), ns=101)
        self.assertFalse(self.snap().to_dict()['events'][0]['receiptConflict'])

    def test_replaced_receipt_never_implies_release(self):
        self.add(receipt(status='replaced'))
        semantics = self.snap().to_dict()['semantics']
        self.assertEqual(semantics['releaseSuccess'], 'unknown')
        self.assertEqual(semantics['ongoingHold'], 'unknown')

    def test_empty_receipt_keeps_partial_input_possible(self):
        self.add(receipt(steps=False))
        row = self.snap().to_dict()['events'][0]
        self.assertTrue(row['partialInputPossible'])
        self.assertEqual(row['reportedCompletedStepCount'], 0)

    def test_nonempty_receipt_does_not_establish_game_effect(self):
        self.add()
        self.assertEqual(self.snap().to_dict()['semantics']['observedGameEffect'], 'unknown')

    def test_stale_ended_sample_preserved_as_anomaly(self):
        value = receipt()
        value['endedAtMs'] = 9.
        self.add(value)
        row = self.snap().to_dict()['events'][0]
        self.assertEqual(row['payload']['endedAtMs'], 9.)
        self.assertTrue(row['serverTimeOrderAnomaly'])

    def test_receipt_can_postdate_frame_header_server_now(self):
        self.add()
        data = self.c.snapshot({'frameId': 2, 'observedClientNs': 90, 'serverNowMs': 11.},
                               cutoff_client_ns=100).to_dict()
        self.assertEqual(data['events'][0]['payload']['endedAtMs'], 20.)

    def test_knowledge_after_frame_is_not_dispatch_after_frame(self):
        self.add()
        row = self.snap().to_dict()['events'][0]
        self.assertTrue(row['knownAfterFrameReceipt'])
        self.assertEqual(row['payload']['appliedSteps'][0]['startedAtMs'], 12.)

    def test_exact_action_reply_matching(self):
        self.c.record_response('action', {'type': 'accepted', 'requestId': 'r', 'acceptedAtMs': 10.},
                               observed_client_ns=95, expected_request_id='r')
        self.assertEqual(self.snap().to_dict()['events'][0]['payload']['state'], 'accepted')

    def test_wrong_request_or_binary_reply_is_unknown(self):
        for expected, binary in (('other', 0), ('r', 1)):
            c = ExecutionContext(identity())
            c.record_response('action', {'type': 'accepted', 'requestId': 'r'},
                              observed_client_ns=95, expected_request_id=expected, payload_bytes=binary)
            self.assertEqual(c.snapshot({'frameId': 1, 'observedClientNs': 90},
                             cutoff_client_ns=100).to_dict()['events'][0]['payload']['state'], 'unknown')

    def test_missing_action_reply_type_is_unknown(self):
        self.c.record_response('action', {'requestId': 'r'}, observed_client_ns=95, expected_request_id='r')
        self.assertEqual(self.snap().to_dict()['events'][0]['payload']['state'], 'unknown')

    def test_release_response_retains_uncertainty(self):
        self.c.record_response('release', {'type': 'released'}, observed_client_ns=95)
        self.assertIn('not_per_key', self.snap().to_dict()['events'][0]['payload']['reason'])

    def test_response_receipts_and_drop_counter_atomic(self):
        self.c.record_response('frame', {'receipts': [receipt()], 'droppedReceipts': 3}, observed_client_ns=95)
        events = self.snap().to_dict()['events']
        self.assertEqual([row['observedClientNs'] for row in events], [95, 95])
        self.assertEqual(events[-1]['payload']['droppedReceipts'], 3)

    def test_bad_response_batch_does_not_partially_append(self):
        with self.assertRaises(ValueError):
            self.c.record_response('frame', {'receipts': [receipt(), {}]}, observed_client_ns=95)
        self.assertEqual(self.snap().to_dict()['events'], [])

    def test_event_bound_reports_evicted_prefix(self):
        self.c = ExecutionContext(identity(), max_events=2)
        for ns in (91, 92, 93):
            self.add(receipt(str(ns)), ns=ns)
        data = self.snap().to_dict()
        self.assertEqual([row['sequence'] for row in data['events']], [2, 3])
        self.assertEqual(data['coverage']['evictedEvents'], 1)

    def test_time_window_ages_evidence_without_faking_completion(self):
        self.c = ExecutionContext(identity(), window_ns=5)
        self.add(ns=90)
        data = self.snap().to_dict()
        self.assertEqual(data['events'], [])
        self.assertEqual(data['coverage']['outsideWindowEvents'], 1)
        self.assertEqual(data['semantics']['ongoingHold'], 'unknown')

    def test_future_eviction_does_not_publish_future_counter(self):
        self.c = ExecutionContext(identity(), max_events=1)
        self.add(receipt('a'), ns=101)
        self.add(receipt('b'), ns=102)
        data = self.snap().to_dict()
        self.assertIsNone(data['coverage']['evictedEvents'])
        self.assertTrue(data['coverage']['retentionAdvancedBeyondCutoff'])

    def test_private_fields_are_not_projected(self):
        value = receipt()
        value['privateToken'] = object()
        self.add(value)
        self.assertNotIn('privateToken', self.snap()._document_json)

    def test_invalid_timestamp_types_and_nonfinite_server_values(self):
        for bad in (True, -1, 1.5, None):
            with self.assertRaises(ValueError):
                self.add(ns=bad)
        for bad in (float('nan'), float('inf'), True):
            value = receipt()
            value['endedAtMs'] = bad
            with self.assertRaises(ValueError):
                self.add(value)

    def test_oversized_and_opaque_frame_rejected(self):
        for field in ({'raw': 'x' * 5000}, {'raw': object()}):
            with self.assertRaises((ValueError, TypeError)):
                self.c.snapshot({'frameId': 1, 'observedClientNs': 90, 'sourceFrame': field}, cutoff_client_ns=100)

    def test_renderer_budget_and_explicit_projection_omission(self):
        for i in range(20):
            self.add(receipt('r' + str(i)), ns=i)
        text = render_gamescaling_context(self.snap())
        self.assertLessEqual(len(text.encode('utf-8')), 2048)
        result = json.loads(text)
        self.assertGreater(result['projectionOmittedEvents'], 0)
        self.assertEqual(result['events'][-1]['requestId'], 'r19')

    def test_renderer_includes_image_and_dispatch_clock_separately(self):
        self.add()
        result = json.loads(render_gamescaling_context(self.snap()))
        self.assertEqual(result['imageTiming']['hostAcquisitionMs'], [11.1, 11.9])
        self.assertEqual(result['events'][0]['steps'][0]['startedAtMs'], 12.)
        self.assertIn('does NOT prove', result['limits'])

    def test_renderer_rejects_plain_or_forged_snapshots(self):
        for value in ({}, ExecutionSnapshot('{}', None)):
            with self.assertRaises((ValueError, TypeError)):
                render_gamescaling_context(value)


if __name__ == '__main__':
    unittest.main()
