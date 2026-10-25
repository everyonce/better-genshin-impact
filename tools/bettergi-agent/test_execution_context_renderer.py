"""Focused receipt-age and evidence-priority tests; no model or transport."""
import json
import unittest

from execution_context import ExecutionContext, render_gamescaling_context


def receipt(request='actual', status='completed'):
    """Keep exact R45 fields and its pre-dispatch timestamp semantics."""
    return {'requestId': request, 'modelId': 'gamescaling', 'frameId': 1,
            'status': status, 'reason': 'horizon_complete', 'acceptedAtMs': 10.,
            'endedAtMs': 20., 'appliedSteps': [{'index': 0, 'startedAtMs': 12.,
                'keys': ['LBUTTON'], 'mouseDx': 0, 'mouseDy': 0}]}


def plan(request):
    """A legal verbose six-step plan stresses the model-text budget."""
    return {'requestId': request, 'steps': [
        {'keys': ['W', 'LBUTTON'], 'mouseDx': 100, 'mouseDy': -50, 'durationMs': 50}
        for _ in range(6)]}


class RendererCorrectionTests(unittest.TestCase):
    """Exercise the changed projection through real immutable ledger snapshots."""

    def setUp(self):
        """Use an explicit inert session owner for each test."""
        self.ledger = ExecutionContext({'sessionId': 's', 'ownerEpoch': 'o'})

    def snapshot(self, cutoff=3_250_000_000, received=1_000_000_000, **frame_fields):
        """Separate client receipt time from arbitrary server-clock numbers."""
        frame = {'frameId': 2, 'observedClientNs': received, 'capturedAtMs': 11.,
                 'sourceAgeMs': 0.5, 'serverNowMs': 11.5,
                 'hostSnapshot': {'startedAtMs': 11.1, 'completedAtMs': 11.4}}
        frame.update(frame_fields)
        return self.ledger.snapshot(frame, cutoff_client_ns=cutoff)

    def render(self, snapshot):
        """Validate every projected fixture's hard UTF-8 byte bound."""
        text = render_gamescaling_context(snapshot)
        self.assertLessEqual(len(text.encode('utf-8')), 2048)
        return json.loads(text)

    def test_age_uses_only_client_receipt_and_cutoff(self):
        result = self.render(self.snapshot())
        self.assertEqual(result['ageSinceImageReceiptMs'], 2250.)
        self.assertIn('client_perf_counter_ns', result['imageReceiptAgeBasis'])
        self.assertIn('lower bound', result['imageReceiptAgeBasis'])
        self.assertIn('not game-render age', result['imageReceiptAgeBasis'])
        self.assertNotIn('sourceAgeMs', result)

    def test_equal_client_instants_have_zero_receipt_age(self):
        self.assertEqual(self.render(self.snapshot(cutoff=0, received=0))['ageSinceImageReceiptMs'], 0.)

    def test_old_reply_age_remains_in_machine_evidence_only(self):
        snapshot = self.snapshot(sourceAgeMs=123.75, serverNowMs=123456789.)
        before = snapshot.to_dict()
        result = self.render(snapshot)
        self.assertEqual(before['frame']['sourceAgeMs'], 123.75)
        self.assertEqual(before, snapshot.to_dict())
        self.assertEqual(result['ageSinceImageReceiptMs'], 2250.)
        self.assertNotIn('sourceAgeMs', result)

    def test_host_clock_window_stays_separate(self):
        timing = self.render(self.snapshot())['imageTiming']
        self.assertEqual(timing['clock'], 'agent_session_ms')
        self.assertEqual(timing['hostRequestMs'], 11.)
        self.assertEqual(timing['hostAcquisitionMs'], [11.1, 11.4])

    def test_wgc_source_is_not_converted_to_client_time(self):
        result = self.render(self.snapshot(hostSnapshot=None,
            sourceTimestampKind='wgc_reported_compositor_qpc', sourceFrame={
                'capturedAtMs': 8., 'acquiredAtMs': 9., 'freshnessAtMs': 8.,
                'freshnessClockKind': 'wgc_reported_compositor_qpc'}))
        self.assertEqual(result['imageTiming']['wgcReportedMs'], 8.)
        self.assertEqual(result['imageTiming']['firstAcquiredMs'], 9.)
        self.assertEqual(result['ageSinceImageReceiptMs'], 2250.)

    def test_latest_receipt_survives_newer_verbose_plans(self):
        self.ledger.record('receipt', receipt(), observed_client_ns=1_100_000_000)
        for i in range(8):
            self.ledger.record('proposal', plan('planned-' + str(i)), observed_client_ns=1_200_000_000+i)
        snapshot = self.snapshot()
        result = self.render(snapshot)
        self.assertIn('actual', [row['requestId'] for row in result['events']])
        self.assertGreater(result['projectionOmittedEvents'], 0)
        self.assertEqual(len(result['events']) + result['projectionOmittedEvents'], 9)
        self.assertEqual(len(snapshot.to_dict()['events']), 9)

    def test_newest_receipt_prioritized_without_reordering_survivors(self):
        for i in range(12):
            self.ledger.record('receipt', receipt('actual-' + str(i)), observed_client_ns=1_100_000_000+i)
        result = self.render(self.snapshot())
        self.assertEqual(result['events'][-1]['requestId'], 'actual-11')
        seq = [row['seq'] for row in result['events']]
        self.assertEqual(seq, sorted(seq))
        self.assertEqual(len(seq) + result['projectionOmittedEvents'], 12)

    def test_old_proposal_cannot_displace_later_replaced_receipt(self):
        self.ledger.record('proposal', plan('planned'), observed_client_ns=1_100_000_000)
        self.ledger.record('receipt', receipt(status='replaced'), observed_client_ns=1_200_000_000)
        result = self.render(self.snapshot())
        actual = next(row for row in result['events'] if row['kind'] == 'receipt')
        self.assertEqual(actual['status'], 'replaced')
        self.assertIn('Hold/release/game effect UNKNOWN', result['limits'])

    def test_duplicate_receipts_and_budget_omissions_count_separately(self):
        self.ledger.record('receipt', receipt(), observed_client_ns=1_100_000_000)
        self.ledger.record('receipt', receipt(), observed_client_ns=1_200_000_000)
        for i in range(8):
            self.ledger.record('proposal', plan('plan-' + str(i)), observed_client_ns=1_300_000_000+i)
        result = self.render(self.snapshot())
        self.assertEqual(result['duplicateReceiptsOmitted'], 1)
        self.assertEqual(sum(row['kind'] == 'receipt' for row in result['events']), 1)
        self.assertEqual(len(result['events']) + result['projectionOmittedEvents'] +
                         result['duplicateReceiptsOmitted'], 10)

    def test_future_receipt_does_not_enter_priority_selection(self):
        self.ledger.record('proposal', plan('known'), observed_client_ns=1_200_000_000)
        self.ledger.record('receipt', receipt('future'), observed_client_ns=3_250_000_001)
        result = self.render(self.snapshot())
        self.assertNotIn('future', [row.get('requestId') for row in result['events']])

    def test_later_arrival_cannot_change_frozen_age_or_projection(self):
        snapshot = self.snapshot()
        before = render_gamescaling_context(snapshot)
        self.ledger.record('receipt', receipt(), observed_client_ns=4_000_000_000)
        self.assertEqual(before, render_gamescaling_context(snapshot))

    def test_without_receipts_oldest_plans_are_removed_first(self):
        for i in range(8):
            self.ledger.record('proposal', plan('planned-' + str(i)), observed_client_ns=1_200_000_000+i)
        result = self.render(self.snapshot())
        self.assertEqual(result['events'][-1]['requestId'], 'planned-7')
        self.assertEqual(len(result['events']) + result['projectionOmittedEvents'], 8)
