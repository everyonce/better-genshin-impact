"""Offline evaluation math and missing-evidence checks; no model, GPU, or controller."""
import json
from pathlib import Path
import tempfile
import unittest

import evaluate_trials as evaluation


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


if __name__ == '__main__':
    unittest.main()
