"""Offline evaluation math and missing-evidence checks; no model, GPU, or controller."""
import json
from pathlib import Path
import tempfile
import unittest

import evaluate_trials as evaluation
from stream_segments import StreamSegments


class EvaluationTests(unittest.TestCase):
    """Use small synthetic artifacts to verify denominators, clocks, and trial isolation."""
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.base = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def write(self, name, value):
        """Write JSON fixtures using the real stream-client field names."""
        path = self.base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return name

    def trial(self, identifier, decisions=None, outcome=None, **extra):
        """Create an explicitly input-enabled trial with optional human labels."""
        report = {'mode': 'live-bound-game-stream', 'model': 'open-p2p', 'inputRequested': True,
                  'hello': {'sessionId': identifier, 'inputEnabled': True}, 'decisionHz': 20,
                  'maxObservationAgeMs': 100, 'decisions': decisions or [], 'receipts': []}
        trial = {'id': identifier, 'kind': 'live-control', 'model': 'open-p2p',
                 'configurationId': 'graph200', 'goalId': 'waypoints', 'startStateId': 'bridge-start',
                 'gpuContext': 'game-shared', 'conditioning': {'mode': 'none'},
                 'report': self.write(identifier + '.json', report), 'outcome': outcome, **extra}
        return trial, report

    def test_missing_outcomes_are_not_failures_and_progress_is_per_trial(self):
        trials = []
        for identifier, outcome in (
                ('a', {'source': 'human', 'rater': 'tester', 'success': True, 'elapsedSeconds': 40,
                       'interventions': 0, 'progress': {'completed': 1, 'total': 1, 'unit': 'waypoints'}}),
                ('b', {'source': 'human', 'rater': 'tester', 'success': False, 'elapsedSeconds': 60,
                       'interventions': 2, 'progress': {'completed': 1, 'total': 4, 'unit': 'waypoints'}}),
                ('c', None)):
            trial, _ = self.trial(identifier, outcome=outcome)
            trials.append(trial)
        result = evaluation.evaluate({'version': 1, 'trials': trials}, self.base)['groups'][0]['metrics']
        self.assertEqual(result['success'], {'known': 2, 'true': 1, 'rate': .5})
        self.assertEqual(result['humanOutcomeTrials'], 2)
        self.assertEqual(result['progressFractionByUnit']['waypoints']['mean'], .625)
        self.assertEqual(result['elapsedSeconds']['mean'], 50)
        self.assertEqual(result['successfulTrialSeconds']['mean'], 40)
        self.assertEqual(result['interventions']['mean'], 1)

    def test_proposals_acceptance_receipts_and_clock_alignment_stay_distinct(self):
        empty = {'durationMs': 50, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}
        decisions = [
            {'frameId': 1, 'steps': [empty], 'parseValid': True, 'policyWallMs': 20,
             'estimatedObservationAgeMs': 40, 'controlCadenceMet': True,
             'acceptance': {'type': 'accepted', 'requestId': 'r1'}},
            {'frameId': 2, 'steps': [{**empty, 'keys': ['W']}], 'parseValid': True, 'policyWallMs': 40,
             'estimatedObservationAgeMs': 100, 'controlCadenceMet': True,
             'acceptance': {'type': 'notSubmitted', 'reason': 'observationTooOld'}},
            {'frameId': 3, 'steps': [], 'parseValid': False, 'policyWallMs': 60,
             'estimatedObservationAgeMs': 80, 'controlCadenceMet': False,
             'acceptance': {'type': 'rejected', 'requestId': 'r3', 'reason': 'window_unavailable'}}]
        trial, report = self.trial('timing', decisions)
        receipt = {'requestId': 'r1', 'frameId': 1, 'status': 'cancelled', 'acceptedAtMs': 130,
                   'appliedSteps': [{'startedAtMs': 140, 'keys': [], 'mouseDx': 0, 'mouseDy': 0}]}
        report['receipts'] = [receipt]
        self.write(trial['report'], report)
        episode = self.base / 'episode'
        episode.mkdir()
        (episode / 'events.jsonl').write_text('\n'.join(json.dumps(row) for row in [
            {'type': 'episodeStart', 'sessionId': 'timing', 'model': 'open-p2p'},
            {'type': 'proposal', 'frameId': 1, 'observedAtMs': 100}, receipt]), encoding='utf-8')
        trial['episodeDirectory'] = 'episode'
        metrics = evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)['trials'][0]['metrics']
        self.assertEqual(metrics['decisions'], 3)
        self.assertEqual(metrics['receipts'], 1)  # sidecar copy must not double-count
        self.assertEqual(metrics['receiptStatusCounts'], {'cancelled': 1})
        self.assertEqual(metrics['appliedSteps'], 1)
        self.assertEqual(metrics['nonIdleAppliedSteps'], 0)
        self.assertEqual(metrics['acceptedPerDecision'], 1 / 3)
        self.assertEqual(metrics['serverRejectedPerSubmitted'], .5)
        self.assertEqual(metrics['noOpProposals']['rate'], .5)
        self.assertEqual(metrics['withinDeclaredFreshnessLimit']['rate'], 2 / 3)
        self.assertEqual(metrics['timingMs']['policyWallMs']['p95'], 58)
        self.assertEqual(metrics['timingMs']['captureToFirstAppliedMs']['p50'], 40)
        self.assertEqual(metrics['timingMs']['acceptedToFirstAppliedMs']['p50'], 10)
        self.assertEqual(metrics['acceptedRequestReceiptCoverage']['rate'], 1)
        self.assertIsNone(metrics['success']['rate'])  # no-op is not a competence label

    def test_progress_rate_averages_individual_trials_with_positive_elapsed_time(self):
        trials = []
        for identifier, completed, elapsed in [('fast', 2, 10), ('slow', 3, 60),
                                               ('zero', 1, 0), ('unknown', 1, None)]:
            trial, _ = self.trial(identifier, outcome={
                'source': 'human', 'rater': 'tester', 'elapsedSeconds': elapsed,
                'progress': {'completed': completed, 'total': 3, 'unit': 'landmarks'}})
            trials.append(trial)
        result = evaluation.evaluate({'version': 1, 'trials': trials}, self.base)
        rates = result['groups'][0]['metrics']['progressPerSecondByUnit']['landmarks']
        self.assertEqual(rates['n'], 2)
        self.assertAlmostEqual(rates['mean'], (.2 + .05) / 2)
        self.assertNotAlmostEqual(rates['mean'], 5 / 70)
        self.assertEqual(result['trials'][0]['metrics']['progressPerSecondByUnit']['landmarks']['mean'], .2)
        self.assertEqual(result['trials'][2]['metrics']['progressPerSecondByUnit'], {})

    def test_without_sidecars_capture_latency_remains_unavailable(self):
        trial, report = self.trial('missing')
        report['receipts'] = [{'requestId': 'a', 'frameId': 8, 'acceptedAtMs': 50,
                               'status': 'completed', 'appliedSteps': [{'startedAtMs': 52, 'keys': ['W']}]}]
        report['serverDroppedReceipts'] = 1
        self.write(trial['report'], report)
        result = evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)['trials'][0]
        self.assertEqual(result['metrics']['timingMs']['acceptedToFirstAppliedMs']['p50'], 2)
        self.assertIsNone(result['metrics']['timingMs']['captureToFirstAppliedMs']['p50'])
        self.assertTrue(any('incomplete' in warning for warning in result['warnings']))

    def test_offline_missing_acceptance_is_not_reported_as_zero_acceptance(self):
        trial, _ = self.trial('offline', kind='offline-replay', gpuContext='game-stopped')
        self.write(trial['report'], {'model': 'open-p2p', 'status': 'completed', 'samples': [
            {'fullActionMs': 28, 'parseValid': True, 'steps': []}]})
        result = evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)['trials'][0]['metrics']
        self.assertIsNone(result['acceptedPerDecision'])
        self.assertIsNone(result['withinDeclaredFreshnessLimit']['rate'])
        self.assertEqual(result['timingMs']['fullActionMs']['p50'], 28)
        trial['outcome'] = {'source': 'human', 'rater': 'tester', 'success': True}
        with self.assertRaisesRegex(ValueError, 'live-control'):
            evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)

    def test_lost_reply_retains_decision_but_not_invented_measurements_or_acceptance(self):
        """A terminal request cannot disappear from the denominator of an otherwise successful run."""
        trial, report = self.trial('lost-reply', [
            {'policyWallMs': 20, 'parseValid': True,
             'acceptance': {'type': 'accepted', 'requestId': 'known'}}])
        report['unacknowledgedAction'] = {'requestId': 'lost', 'frame': {'frameId': 2},
                                         'steps': [{'keys': ['W'], 'durationMs': 50}]}
        report['receipts'] = [{'requestId': 'lost', 'frameId': 2, 'status': 'completed',
                               'appliedSteps': [{'startedAtMs': 150, 'keys': ['W']}]}]
        self.write(trial['report'], report)
        result = evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)['trials'][0]
        metrics = result['metrics']
        self.assertEqual(metrics['decisions'], 2)
        self.assertEqual(metrics['proposalStatusCounts'], {'accepted': 1, 'unacknowledged': 1})
        self.assertEqual(metrics['decisionsWithAcceptance'], 1)
        self.assertIsNone(metrics['acceptedPerDecision'])
        self.assertIsNone(metrics['serverRejectedPerSubmitted'])
        self.assertEqual(metrics['serverRejectedPerAcknowledgedRequest'], 0)
        self.assertEqual(metrics['timingMs']['policyWallMs']['n'], 1)
        self.assertEqual(metrics['parseValid']['known'], 1)
        self.assertEqual(metrics['appliedSteps'], 1)
        self.assertEqual(metrics['nonIdleAppliedSteps'], 1)
        self.assertEqual(metrics['acceptedRequestReceiptCoverage']['matchedReceipts'], 0)
        self.assertEqual(metrics['unacknowledgedRequestReceiptCoverage'],
                         {'unacknowledgedWithId': 1, 'matchedReceipts': 1, 'rate': 1})
        self.assertTrue(any('Unacknowledged' in warning for warning in result['warnings']))

    def test_unacknowledged_latch_overrides_raw_reply_without_counting_twice(self):
        """Even a matching raw reply may have failed payload validation before settlement."""
        trial, report = self.trial('unvalidated', [
            {'policyWallMs': 35, 'acceptance': {'type': 'accepted', 'requestId': 'r1'}}])
        report['unacknowledgedAction'] = {'requestId': 'r1', 'steps': []}
        self.write(trial['report'], report)
        metrics = evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)['trials'][0]['metrics']
        self.assertEqual(metrics['decisions'], 1)
        self.assertEqual(metrics['proposalStatusCounts'], {'unacknowledged': 1})
        self.assertEqual(metrics['decisionsWithAcceptance'], 0)
        self.assertEqual(metrics['timingMs']['policyWallMs']['p50'], 35)
        self.assertIsNone(metrics['serverRejectedPerAcknowledgedRequest'])

    def test_unacknowledged_receipt_matches_remain_scoped_to_the_trial(self):
        """Matching request strings in different sessions do not prove receipt coverage."""
        first, first_report = self.trial('first')
        first_report['unacknowledgedAction'] = {'requestId': 'shared', 'steps': []}
        second, second_report = self.trial('second')
        second_report['receipts'] = [{'requestId': 'shared', 'appliedSteps': []}]
        self.write(first['report'], first_report)
        self.write(second['report'], second_report)
        metrics = evaluation.evaluate({'version': 1, 'trials': [first, second]}, self.base)['groups'][0]['metrics']
        self.assertEqual(metrics['unacknowledgedRequestReceiptCoverage'],
                         {'unacknowledgedWithId': 1, 'matchedReceipts': 0, 'rate': 0})

    def test_malformed_or_ambiguous_unacknowledged_requests_fail(self):
        """Incomplete identities cannot be silently ignored or joined by frame alone."""
        trial, report = self.trial('malformed')
        for pending in ({}, {'requestId': ''}, {'requestId': 42}, 'r1'):
            with self.subTest(pending=pending):
                report['unacknowledgedAction'] = pending
                self.write(trial['report'], report)
                with self.assertRaisesRegex(ValueError, 'nonempty requestId'):
                    evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)
        report['unacknowledgedAction'] = {'requestId': 'r1'}
        report['decisions'] = [{'acceptance': {'requestId': 'r1'}}] * 2
        self.write(trial['report'], report)
        with self.assertRaisesRegex(ValueError, 'Multiple decisions'):
            evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)

    def test_offline_replay_cannot_claim_an_unacknowledged_submission(self):
        """Replay evidence must stay separate from requests made to a live controller."""
        trial, _ = self.trial('offline-request', kind='offline-replay')
        self.write(trial['report'], {'samples': [], 'unacknowledgedAction': {'requestId': 'r1'}})
        with self.assertRaisesRegex(ValueError, 'offline replay'):
            evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)

    def test_different_kinds_start_states_and_gpu_contexts_do_not_merge(self):
        trials = [self.trial('a')[0], self.trial('b', kind='live-observe')[0],
                  self.trial('c', startStateId='different')[0], self.trial('d', gpuContext='unknown')[0]]
        result = evaluation.evaluate({'version': 1, 'trials': trials}, self.base)
        self.assertEqual(len(result['groups']), 4)

    def test_mismatched_report_episode_sessions_fail(self):
        trial, _ = self.trial('session-a')
        episode = self.base / 'episode'
        episode.mkdir()
        (episode / 'events.jsonl').write_text(json.dumps({'type': 'episodeStart', 'sessionId': 'session-b'}))
        trial['episodeDirectory'] = 'episode'
        with self.assertRaisesRegex(ValueError, 'different sessions'):
            evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)

    def test_unlabeled_empty_and_nonfinite_values_do_not_create_scores(self):
        trial, _ = self.trial('empty')
        result = evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)['trials'][0]['metrics']
        self.assertEqual(result['success']['known'], 0)
        self.assertIsNone(result['elapsedSeconds']['mean'])
        self.assertIsNone(evaluation.distribution([float('nan'), float('inf'), True])['p95'])
        trial['outcome'] = {'source': 'automatic-no-op-score', 'rater': 'model', 'success': True}
        with self.assertRaisesRegex(ValueError, 'source=human'):
            evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)


class NativeSettlementEvaluationTests(unittest.TestCase):
    """Use the exact frozen bridge projection/acknowledgement shapes without a live policy."""
    setUp = EvaluationTests.setUp
    tearDown = EvaluationTests.tearDown
    write = EvaluationTests.write
    trial = EvaluationTests.trial

    def native_report(self, kind='accepted', completed=False):
        """Build one interrupted native decision with actual writer field names and bounded data."""
        trial, report = self.trial('native')
        request = 'new-request' if kind != 'notSubmitted' else None
        acceptance = {'type': kind, 'receivedAtMs': 132.0, 'acceptedAtMs': 133.0 if kind == 'accepted' else None}
        if request:
            acceptance['requestId'] = request
        if kind != 'accepted':
            acceptance['reason'] = 'window_unavailable' if kind == 'rejected' else 'observationTooOld'
        decision = {'frameId': 17, 'steps': [{'durationMs': 50, 'keys': ['W'], 'mouseDx': 0, 'mouseDy': 0}],
                    'policyWallMs': 29.25, 'estimatedObservationAgeMs': 72.5, 'acceptance': acceptance}
        report['nativeHistorySettlement'] = {
            'requestId': request, 'outcome': 'accepted_admission' if kind == 'accepted' else 'known_not_admitted',
            'acknowledgementKnown': kind != 'notSubmitted', 'completed': completed,
            'error': None if completed else 'OwnerPoisoned: settle failed', 'decision': decision}
        if kind != 'notSubmitted':
            report['nativeHistoryAcknowledgement'] = {'type': kind, 'requestId': request}
        return trial, report

    def evaluate_report(self, trial, report):
        """Exercise the public saved-file evaluator and expose its joined facts for assertions."""
        self.write(trial['report'], report)
        result = evaluation.evaluate({'version': 1, 'trials': [trial]}, self.base)['trials'][0]
        _, facts = evaluation.load_trial(trial, self.base)
        return result, facts

    def unknown_report(self, reply_id='wrong-request'):
        """A malformed raw reply remains evidence, never a confirmed admission."""
        trial, report = self.native_report()
        settlement = report['nativeHistorySettlement']
        settlement.update(outcome='unknown', acknowledgementKnown=False)
        settlement['decision']['acceptance']['requestId'] = reply_id
        report.pop('nativeHistoryAcknowledgement')
        report['unacknowledgedAction'] = {'requestId': 'new-request', 'frame': {'frameId': 17},
                                         'steps': settlement['decision']['steps']}
        return trial, report

    def test_accepted_settlement_failure_retains_admission_and_measurements(self):
        trial, report = self.native_report()
        result, facts = self.evaluate_report(trial, report)
        metrics = result['metrics']
        self.assertEqual(metrics['proposalStatusCounts'], {'accepted': 1})
        self.assertEqual(metrics['acceptedPerDecision'], 1)
        self.assertEqual(metrics['timingMs']['policyWallMs']['p50'], 29.25)
        self.assertEqual(metrics['timingMs']['estimatedObservationAgeMs']['p50'], 72.5)
        self.assertEqual(metrics['parseValid']['known'], 0)
        self.assertEqual(metrics['protocolCompatible']['known'], 0)
        self.assertEqual(metrics['appliedSteps'], 0)
        self.assertEqual(metrics['acceptedRequestReceiptCoverage']['matchedReceipts'], 0)
        self.assertEqual(result['nativeHistorySettlement'], report['nativeHistorySettlement'])
        self.assertFalse(result['nativeHistorySettlement']['completed'])
        self.assertNotIn('historyCommitted', facts['decisions'][0])

    def test_rejected_settlement_failure_stays_known_rejection(self):
        trial, report = self.native_report('rejected')
        result, _ = self.evaluate_report(trial, report)
        self.assertEqual(result['metrics']['proposalStatusCounts'], {'rejected': 1})
        self.assertEqual(result['metrics']['serverRejectedPerAcknowledgedRequest'], 1)
        self.assertEqual(result['metrics']['parseValid']['known'], 0)
        self.assertEqual(result['nativeHistoryAcknowledgement'], report['nativeHistoryAcknowledgement'])

    def test_completed_settlement_then_older_receipt_error_preserves_current_admission(self):
        trial, report = self.native_report(completed=True)
        report['error'] = 'NativeHistoryTerminal: older receipt only partially applied'
        report['decisions'] = [{'acceptance': {'type': 'accepted', 'requestId': 'older'}}]
        report['receipts'] = [{'requestId': 'older', 'status': 'cancelled', 'appliedSteps': [{'keys': ['W']}]}]
        result, _ = self.evaluate_report(trial, report)
        self.assertEqual(result['metrics']['proposalStatusCounts'], {'accepted': 2})
        self.assertEqual(result['metrics']['acceptedRequestReceiptCoverage']['matchedReceipts'], 1)
        self.assertTrue(result['nativeHistorySettlement']['completed'])
        self.assertEqual(result['metrics']['appliedSteps'], 1)

    def test_completed_rejection_is_independent_of_settlement_success(self):
        trial, report = self.native_report('rejected', completed=True)
        result, _ = self.evaluate_report(trial, report)
        self.assertEqual(result['metrics']['proposalStatusCounts'], {'rejected': 1})
        self.assertTrue(result['nativeHistorySettlement']['completed'])

    def test_local_not_submitted_without_id_is_not_fuzzily_deduplicated(self):
        trial, report = self.native_report('notSubmitted')
        # Same frame, times and action still do not identify the same local proposal.
        report['decisions'] = [json.loads(json.dumps(report['nativeHistorySettlement']['decision']))]
        result, _ = self.evaluate_report(trial, report)
        self.assertEqual(result['metrics']['decisions'], 2)
        self.assertEqual(result['metrics']['proposalStatusCounts'], {'notSubmitted': 2})
        self.assertEqual(result['metrics']['timingMs']['policyWallMs']['n'], 2)
        self.assertEqual(result['metrics']['acceptedRequestReceiptCoverage']['acceptedWithId'], 0)

    def test_local_failure_with_bound_but_unsubmitted_id_is_still_local(self):
        trial, report = self.native_report('notSubmitted')
        report['nativeHistorySettlement']['requestId'] = 'bound-before-transport'
        result, facts = self.evaluate_report(trial, report)
        self.assertEqual(result['metrics']['proposalStatusCounts'], {'notSubmitted': 1})
        self.assertNotIn('requestId', facts['decisions'][0]['acceptance'])

    def test_wrong_id_accepted_raw_reply_stays_unknown_and_retained_separately(self):
        trial, report = self.unknown_report()
        result, facts = self.evaluate_report(trial, report)
        self.assertEqual(result['metrics']['decisions'], 1)
        self.assertEqual(result['metrics']['proposalStatusCounts'], {'unacknowledged': 1})
        self.assertIsNone(result['metrics']['acceptedPerDecision'])
        self.assertEqual(result['metrics']['timingMs']['policyWallMs']['p50'], 29.25)
        self.assertEqual(result['nativeHistoryUnverifiedAcceptance']['requestId'], 'wrong-request')
        self.assertEqual(facts['decisions'][0]['unverifiedAcceptance']['requestId'], 'wrong-request')
        self.assertEqual(facts['decisions'][0]['acceptance']['requestId'], 'new-request')
        self.assertEqual(result['metrics']['parseValid']['known'], 0)

    def test_unknown_matching_raw_reply_and_existing_decision_count_once(self):
        trial, report = self.unknown_report('new-request')
        report['decisions'] = [json.loads(json.dumps(report['nativeHistorySettlement']['decision']))]
        result, facts = self.evaluate_report(trial, report)
        self.assertEqual(result['metrics']['proposalStatusCounts'], {'unacknowledged': 1})
        self.assertEqual(facts['decisions'][0]['unverifiedAcceptance']['type'], 'accepted')

    def test_unknown_requires_exact_latch_and_no_explicit_acknowledgement(self):
        for change in ('missing', 'different', 'ack'):
            with self.subTest(change=change):
                trial, report = self.unknown_report()
                if change == 'missing': report.pop('unacknowledgedAction')
                if change == 'different': report['unacknowledgedAction']['requestId'] = 'other'
                if change == 'ack': report['nativeHistoryAcknowledgement'] = {'type': 'accepted', 'requestId': 'new-request'}
                with self.assertRaisesRegex(ValueError, 'exact unacknowledgedAction'):
                    self.evaluate_report(trial, report)

    def test_known_exact_id_dedup_keeps_full_existing_measurements(self):
        trial, report = self.native_report()
        existing = json.loads(json.dumps(report['nativeHistorySettlement']['decision']))
        existing.update(parseValid=True, fullActionMs=27.0)
        report['decisions'] = [existing]
        result, _ = self.evaluate_report(trial, report)
        self.assertEqual(result['metrics']['decisions'], 1)
        self.assertEqual(result['metrics']['timingMs']['fullActionMs']['p50'], 27)
        self.assertEqual(result['metrics']['parseValid']['known'], 1)

    def test_same_id_conflicting_projection_or_reply_is_rejected(self):
        for field, value in (('frameId', 18), ('policyWallMs', 30), ('steps', []), ('reply', 'rejected')):
            with self.subTest(field=field):
                trial, report = self.native_report()
                existing = json.loads(json.dumps(report['nativeHistorySettlement']['decision']))
                if field == 'reply': existing['acceptance']['type'] = value
                else: existing[field] = value
                report['decisions'] = [existing]
                with self.assertRaisesRegex(ValueError, 'Conflicting native'):
                    self.evaluate_report(trial, report)

    def test_duplicate_existing_request_ids_are_ambiguous(self):
        trial, report = self.native_report()
        report['decisions'] = [report['nativeHistorySettlement']['decision']] * 2
        with self.assertRaisesRegex(ValueError, 'Multiple decisions'):
            self.evaluate_report(trial, report)

    def test_known_acknowledgement_outcome_id_and_flags_must_join(self):
        for change in ('missing', 'wrong-id', 'wrong-type', 'projection-id', 'projection-type', 'flag', 'pending'):
            with self.subTest(change=change):
                trial, report = self.native_report()
                if change == 'missing': report.pop('nativeHistoryAcknowledgement')
                if change == 'wrong-id': report['nativeHistoryAcknowledgement']['requestId'] = 'other'
                if change == 'wrong-type': report['nativeHistoryAcknowledgement']['type'] = 'rejected'
                if change == 'projection-id': report['nativeHistorySettlement']['decision']['acceptance']['requestId'] = 'other'
                if change == 'projection-type': report['nativeHistorySettlement']['decision']['acceptance']['type'] = 'rejected'
                if change == 'flag': report['nativeHistorySettlement']['acknowledgementKnown'] = False
                if change == 'pending': report['unacknowledgedAction'] = {'requestId': 'new-request'}
                with self.assertRaises(ValueError): self.evaluate_report(trial, report)

    def test_local_projection_cannot_impersonate_a_server_reply(self):
        for change in ('accepted', 'ack', 'missing-acceptance', 'conflicting-existing'):
            with self.subTest(change=change):
                trial, report = self.native_report('notSubmitted')
                if change == 'accepted': report['nativeHistorySettlement']['decision']['acceptance']['type'] = 'accepted'
                if change == 'ack': report['nativeHistoryAcknowledgement'] = {'type': 'rejected', 'requestId': 'x'}
                if change == 'missing-acceptance': report['nativeHistorySettlement']['decision'].pop('acceptance')
                if change == 'conflicting-existing':
                    report['nativeHistorySettlement']['requestId'] = 'x'
                    report['decisions'] = [{'acceptance': {'type': 'accepted', 'requestId': 'x'}}]
                with self.assertRaises(ValueError): self.evaluate_report(trial, report)

    def test_unknown_projection_conflicts_with_latched_action_are_rejected(self):
        for field in ('frameId', 'steps'):
            trial, report = self.unknown_report()
            report['nativeHistorySettlement']['decision'][field] = 18 if field == 'frameId' else []
            with self.assertRaisesRegex(ValueError, 'conflicts with unresolved request'):
                self.evaluate_report(trial, report)

    def test_projection_bound_and_no_invented_parse_flags_are_enforced(self):
        for change in ('parseValid', 'oversize', 'nonfinite'):
            with self.subTest(change=change):
                trial, report = self.native_report()
                decision = report['nativeHistorySettlement']['decision']
                if change == 'parseValid': decision['parseValid'] = True
                if change == 'oversize': decision['steps'] = ['x' * 24576]
                if change == 'nonfinite': decision['policyWallMs'] = float('nan')
                with self.assertRaises(ValueError): self.evaluate_report(trial, report)

    def test_boolean_or_float_identity_flags_do_not_pass_exact_join(self):
        for change in ('known', 'completed', 'request', 'frame-type'):
            with self.subTest(change=change):
                trial, report = self.native_report()
                if change == 'known': report['nativeHistorySettlement']['acknowledgementKnown'] = 1
                if change == 'completed': report['nativeHistorySettlement']['completed'] = 0.0
                if change == 'request': report['nativeHistorySettlement']['requestId'] = True
                if change == 'frame-type':
                    report['decisions'] = [json.loads(json.dumps(report['nativeHistorySettlement']['decision']))]
                    report['decisions'][0]['frameId'] = 17.0
                with self.assertRaises(ValueError): self.evaluate_report(trial, report)

    def test_offline_replay_rejects_both_native_terminal_evidence_fields(self):
        for name in ('nativeHistorySettlement', 'nativeHistoryAcknowledgement'):
            with self.subTest(name=name):
                trial, report = self.native_report()
                trial['kind'] = 'offline-replay'
                report = {'samples': [], name: report[name]}
                with self.assertRaisesRegex(ValueError, 'offline replay'):
                    self.evaluate_report(trial, report)

    def test_explicit_ack_without_projection_retains_metadata_without_new_decision(self):
        for kind in ('accepted', 'rejected'):
            with self.subTest(kind=kind):
                trial, report = self.native_report(kind, completed=True)
                report['nativeHistorySettlement'].pop('decision')
                result, _ = self.evaluate_report(trial, report)
                self.assertEqual(result['metrics']['proposalStatusCounts'], {})
                self.assertEqual(result['metrics']['timingMs']['policyWallMs']['n'], 0)
                self.assertEqual(result['metrics']['parseValid']['known'], 0)
                self.assertEqual(result['nativeHistoryAcknowledgement'], report['nativeHistoryAcknowledgement'])
                self.assertEqual(result['nativeHistorySettlement'], report['nativeHistorySettlement'])

    def assert_segment_carryover_not_counted_twice(self, kind):
        """Use actual snapshot list-transfer semantics without constructing its worker or recorder."""
        trial, report = self.native_report(kind, completed=True)
        report['decisions'] = [report['nativeHistorySettlement'].pop('decision')]
        report.update({key: 0 for key in StreamSegments.COUNTERS})
        report['acceptedInputActions'] = int(kind == 'accepted')
        report['captureQuality'] = {'check': 'fixture'}
        segments = object.__new__(StreamSegments)
        segments.counter_base = {key: 0 for key in StreamSegments.COUNTERS}
        segments.quality_base = {}
        segments.number, segments.started, segments.context = 1, 10.0, {}
        first = segments._snapshot(report, 'segmentRotated', 11.0)
        self.assertEqual(len(first['decisions']), 1)
        self.assertEqual(report['decisions'], [])
        self.assertNotIn('decision', report['nativeHistorySettlement'])
        segments.number, segments.started = 2, 11.0
        segments.context = {'previousReport': 'segment-1.json', 'sameBridgeLease': True}
        second = segments._snapshot(report, 'stopped', 11.5)
        self.assertEqual(second['decisions'], [])
        self.assertEqual(second['nativeHistoryAcknowledgement'], first['nativeHistoryAcknowledgement'])
        self.assertEqual(second['nativeHistorySettlement'], first['nativeHistorySettlement'])
        first_trial = dict(trial, id=kind + '-segment-1', report=kind + '-segment-1.json')
        second_trial = dict(trial, id=kind + '-segment-2', report=kind + '-segment-2.json')
        first_result, _ = self.evaluate_report(first_trial, first)
        second_result, _ = self.evaluate_report(second_trial, second)
        self.assertEqual(first_result['metrics']['proposalStatusCounts'], {kind: 1})
        self.assertEqual(second_result['metrics']['proposalStatusCounts'], {})
        self.assertEqual(second_result['nativeHistorySettlement'], first['nativeHistorySettlement'])
        both = evaluation.evaluate({'version': 1, 'trials': [first_trial, second_trial]}, self.base)
        self.assertEqual(both['groups'][0]['metrics']['proposalStatusCounts'], {kind: 1})
        self.assertEqual(both['groups'][0]['metrics']['timingMs']['policyWallMs']['n'], 1)

    def test_actual_snapshot_accepted_carryover_does_not_fabricate_second_trial_decision(self):
        self.assert_segment_carryover_not_counted_twice('accepted')

    def test_actual_snapshot_rejected_carryover_does_not_fabricate_second_trial_decision(self):
        self.assert_segment_carryover_not_counted_twice('rejected')

    def test_no_projection_still_validates_exact_existing_request_and_rejects_ambiguity(self):
        for kind in ('accepted', 'rejected'):
            for shape in ('matching', 'other-id', 'conflicting', 'duplicate'):
                with self.subTest(kind=kind, shape=shape):
                    trial, report = self.native_report(kind, completed=True)
                    decision = report['nativeHistorySettlement'].pop('decision')
                    report['decisions'] = [decision]
                    if shape == 'other-id':
                        decision['acceptance']['requestId'] = 'earlier-request'
                    elif shape == 'conflicting':
                        decision['acceptance']['type'] = 'rejected' if kind == 'accepted' else 'accepted'
                    elif shape == 'duplicate':
                        report['decisions'].append(json.loads(json.dumps(decision)))
                    if shape in ('conflicting', 'duplicate'):
                        with self.assertRaises(ValueError):
                            self.evaluate_report(trial, report)
                    else:
                        result, _ = self.evaluate_report(trial, report)
                        self.assertEqual(result['metrics']['proposalStatusCounts'], {kind: 1})
                        rows = evaluation.retain_native_history_decision(report['decisions'],
                            report['nativeHistorySettlement'], report['nativeHistoryAcknowledgement'], None)
                        self.assertEqual(rows, report['decisions'])

    def test_unknown_without_projection_retains_exact_unresolved_request(self):
        trial, report = self.unknown_report()
        report['nativeHistorySettlement'].pop('decision')
        result, _ = self.evaluate_report(trial, report)
        self.assertEqual(result['metrics']['proposalStatusCounts'], {'unacknowledged': 1})
        self.assertIsNone(result['metrics']['acceptedPerDecision'])
        self.assertEqual(result['metrics']['timingMs']['policyWallMs']['n'], 0)

    def test_join_does_not_mutate_raw_settlement_or_input_decisions(self):
        trial, report = self.unknown_report('new-request')
        report['decisions'] = [json.loads(json.dumps(report['nativeHistorySettlement']['decision']))]
        original = json.dumps(report, sort_keys=True)
        evaluation.retain_native_history_decision(report['decisions'], report['nativeHistorySettlement'],
                                                 None, report['unacknowledgedAction'])
        self.assertEqual(json.dumps(report, sort_keys=True), original)


if __name__ == '__main__':
    unittest.main()
