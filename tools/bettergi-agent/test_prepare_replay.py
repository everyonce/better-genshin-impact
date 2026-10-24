"""Deterministic CPU evidence checks; no Torch, model, capture, or input imports."""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

from prepare_replay import CLOCK, EvidenceError, ReceiptTimeline, main, prepare


def receipt(rid, accepted, started, ended, keys, *, mouse=(0, 0), status='replaced'):
    """Make a terminal single-step backend receipt."""
    return {'requestId': rid, 'frameId': int(rid[1:]), 'modelId': 'open-p2p',
            'status': status, 'reason': 'newer_proposal' if status == 'replaced' else 'horizon_complete',
            'acceptedAtMs': accepted, 'endedAtMs': ended,
            'appliedSteps': [] if started is None else [
                {'index': 0, 'startedAtMs': started, 'keys': keys, 'mouseDx': mouse[0], 'mouseDy': mouse[1]}]}


def evidence(count=30, interval_ms=50):
    """Build a closed, loss-free recording with real indexed frames and complete actions."""
    observations, frames, decisions, receipts, proposals = [], [], [], [], []
    profile = 'p2p-native-hamming-192-v1'
    for fid in range(1, count+1):
        at = fid*float(interval_ms)
        source = {'captureEpoch': 'capture', 'timestamp100ns': int(at*10000), 'capturedAtMs': at-5,
                  'acquiredAtMs': at, 'freshnessAtMs': at-5, 'freshnessClockKind': 'reported_compositor_qpc'}
        ready = {'ready': True, 'epoch': 1}
        row = {'frameId': fid, 'capturedAtMs': at-1, 'sourceFrame': source,
               'sourceTimestampKind': 'wgc_reported_compositor_qpc', 'serverNowMs': at+5,
               'clientReceivedNs': int((at+6)*1e6), 'width': 192, 'height': 192,
               'sourceWidth': 1920, 'sourceHeight': 1080, 'pixelFormat': 'rgb24',
               'observationProfile': profile, 'inputAvailable': True, 'frameQuality': 'usable',
               'frameWorldReadiness': ready, 'worldReadiness': ready, 'droppedReceipts': 0,
               'videoQueueAccepted': True}
        observations.append(row)
        video = copy.deepcopy(row)
        video.pop('videoQueueAccepted')
        frames.append(dict(video, videoFrameIndex=fid-1, videoPtsSeconds=(fid-1)/20))
        step = {'durationMs': 100, 'keys': ['W'], 'mouseDx': 0, 'mouseDy': 0}
        acknowledgement = {'type': 'accepted', 'requestId': f'r{fid}', 'acceptedAtMs': at+10}
        decision = {'frameId': fid, 'episodeStep': fid, 'parseValid': True, 'historyCommitted': True,
                    'controlEpoch': 0, 'policyGoalVersion': 0, 'appliedGoalRequestId': None,
                    'goalIntent': 'ground-navigation', 'steps': [step],
                    'rawPolicySteps': [dict(step, durationMs=50)], 'acceptance': acknowledgement}
        decisions.append(decision)
        proposals.append(dict(copy.deepcopy(decision), type='proposal', observedAtMs=at-1))
        receipts.append(receipt(f'r{fid}', at+10, at+15, at+interval_ms+10 if fid<count else at+115,
                                ['W'], status='replaced' if fid<count else 'completed'))
    recording = {'complete': True, 'closed': True, 'error': None, 'encodedFrames': count,
                 'recordedObservations': count, 'droppedFrames': 0, 'droppedEvents': 0,
                 'abandonedFrames': 0, 'droppedObservations': 0}
    hello = {'sessionId': 'session', 'ownerEpoch': 'owner', 'clockFrequency': 1000, 'observationProfile': profile}
    report = {'model': 'open-p2p', 'inputRequested': True, 'recording': copy.deepcopy(recording),
              'framesReceived': count, 'acceptedInputActions': count, 'serverDroppedReceipts': 0,
              'capturePollHz': 20, 'observationProfile': profile, 'hello': hello,
              'decisions': decisions, 'receipts': receipts,
              'initialGoalState': {'controlEpoch': 0, 'policyGoalVersion': 0, 'appliedGoalRequestId': None,
                                   'goalIntent': 'ground-navigation', 'goalMetadata': None},
              'firstInputDeadlinePolicy': {'maxObservationAgeMs': 150, 'serverEnforcementRequested': True}}
    events = [dict(hello, type='episodeStart'), *proposals, *copy.deepcopy(receipts),
              {'type': 'episodeEnd', 'acceptedInputActions': count}]
    return [report, observations, frames, events, recording]


class TimelineTests(unittest.TestCase):
    def test_replacement_keeps_keys_across_frames_and_mouse_occurs_once(self):
        timeline = ReceiptTimeline([receipt('r1', 0, 10, 60, ['W'], mouse=(7, -2)),
                                    receipt('r2', 60, 70, 120, ['W', 'SHIFT'], mouse=(3, 0), status='completed')])
        first = timeline.label(20, 65)
        self.assertEqual(first['heldKeys'], ['W'])
        self.assertEqual(first['stateTransitions'], [])  # replacement at60 is not a release
        self.assertEqual(first['mouseDx'], 0)
        second, third = timeline.label(65, 70), timeline.label(70, 100)
        self.assertEqual(second['mouseDx'], 3)
        self.assertEqual(second['mouseEvents'][0]['eventId'], 'r2:step:0')
        self.assertEqual(third['mouseDx'], 0)
        self.assertEqual(third['heldKeys'], ['SHIFT', 'W'])
        self.assertFalse(third['trainingEligible'])

    def test_horizon_and_cancel_release_are_known_empty_states(self):
        for status in ('completed', 'cancelled'):
            with self.subTest(status=status):
                timeline = ReceiptTimeline([receipt('r1', 0, 10, 60, ['W'], status=status)])
                label = timeline.label(20, 70)
                self.assertEqual(label['heldKeys'], [])
                self.assertEqual(label['stateTransitions'][0]['kind'], 'release')

    def test_unstarted_cancellation_releases_inherited_state(self):
        timeline = ReceiptTimeline([receipt('r1', 0, 10, 60, ['W']),
                                    receipt('r2', 60, None, 90, [], status='cancelled')])
        self.assertEqual(timeline.label(20, 95)['heldKeys'], [])

    def test_unknown_initial_interval_and_equal_time_mutations_fail(self):
        timeline = ReceiptTimeline([receipt('r1', 10, 15, 80, ['W'], status='completed')])
        with self.assertRaisesRegex(EvidenceError, 'unknown_initial'):
            timeline.label(0, 30)
        with self.assertRaisesRegex(EvidenceError, 'ambiguous_equal'):
            ReceiptTimeline([receipt('r1', 0, 10, 60, ['W'], status='completed'),
                             receipt('r2', 60, 60, 100, ['A'], status='completed')])

    def test_impossible_completion_and_negative_action_clocks_fail(self):
        with self.assertRaisesRegex(EvidenceError, 'completed_without_applied_step'):
            ReceiptTimeline([receipt('r1', 0, None, 60, [], status='completed')])
        with self.assertRaisesRegex(EvidenceError, 'negative_action_clock'):
            ReceiptTimeline([receipt('r1', -3, -2, -1, ['W'], status='completed')])


class PreparationTests(unittest.TestCase):
    def run_prepare(self, data, **kwargs):
        return prepare(*data, history_frames=3, max_windows=1, probe_frame_ids=[10], **kwargs)

    def test_three_arms_exclude_probe_and_preserve_auditable_labels(self):
        result = self.run_prepare(evidence())
        self.assertEqual(result['comparisonMode'], 'three-arm')
        self.assertTrue(result['nominalGridRequirementsApplied'])
        self.assertEqual(result['status'], 'prepared')
        window = result['windows'][0]
        self.assertIsNone(window['probeLabel'])
        self.assertFalse(window['trainingEligible'])
        for name, arm in window['arms'].items():
            self.assertEqual(arm['labelClock'], CLOCK)
            ids = [x['frame']['frameId'] for x in arm['samples']]
            self.assertEqual(ids, [7, 8, 9])
            self.assertNotIn(10, ids)
            self.assertTrue(all(x['frame']['labelTimeMs'] < window['probe']['labelTimeMs'] for x in arm['samples']))
            self.assertTrue(all(not x['label']['trainingEligible'] for x in arm['samples']))
        self.assertEqual(result['firstInputDeadlinePolicy']['maxObservationAgeMs'], 150)
        self.assertFalse(result['inferenceExecuted'])

    def test_same_frames_only_omits_grid_without_changing_real_images(self):
        data = evidence(interval_ms=70)
        strict = self.run_prepare(data)
        self.assertIn('grid_jitter_exceeded', strict['rejectedCandidateCounts'])
        result = self.run_prepare(data, comparison_mode='same-frames-only')
        self.assertEqual(result['comparisonMode'], 'same-frames-only')
        self.assertFalse(result['nominalGridRequirementsApplied'])
        self.assertIsNone(result['parameters']['nominalHz'])
        self.assertIsNone(result['parameters']['maxJitterMs'])
        window = result['windows'][0]
        self.assertEqual(window['comparisonMode'], 'same-frames-only')
        self.assertEqual(set(window['arms']), {'accepted_proxy', 'receipt_same_frames'})
        proxy, actual = (window['arms'][name] for name in ('accepted_proxy', 'receipt_same_frames'))
        self.assertEqual(proxy['anchor'], actual['anchor'])
        self.assertEqual([s['frame'] for s in proxy['samples']], [s['frame'] for s in actual['samples']])
        self.assertEqual([s['frame']['frameId'] for s in actual['samples']], [7, 8, 9])
        self.assertEqual([s['frame']['labelTimeMs'] for s in actual['samples']], [490, 560, 630])
        self.assertTrue(all('nominalTargetMs' not in s['frame'] for s in actual['samples']))
        self.assertEqual(actual['wallSpanMs'], 210)
        self.assertEqual(window['probe']['frameId'], 10)
        self.assertIsNone(window['probeLabel'])
        self.assertFalse(window['trainingEligible'])

    def test_same_frames_only_retains_non_grid_rejection_guards(self):
        mode = {'comparison_mode': 'same-frames-only'}
        data = evidence()
        for rows in (data[1], data[2]):
            rows[7]['sourceFrame'] = copy.deepcopy(rows[6]['sourceFrame'])
        self.assertIn('duplicate_real_frame_or_probe_in_history', self.run_prepare(data, **mode)['rejectedCandidateCounts'])
        data = evidence(interval_ms=70)
        data[0]['receipts'].pop(5)
        with self.assertRaisesRegex(EvidenceError, 'missing_terminal_receipts'):
            self.run_prepare(data, **mode)
        data = evidence(interval_ms=70)
        data[2].pop(5)
        with self.assertRaisesRegex(EvidenceError, 'recording_count_mismatch'):
            self.run_prepare(data, **mode)
        for key in ('episodeStep', 'policyGoalVersion'):
            data = evidence(interval_ms=70)
            data[0]['decisions'][7][key] = data[3][8][key] = 1
            self.assertEqual(self.run_prepare(data, **mode)['status'], 'no_eligible_windows')
        data = evidence(interval_ms=70)
        for rows in (data[1], data[2]):
            rows[7]['inputAvailable'] = False
        self.assertIn('world_or_capture_not_ready', self.run_prepare(data, **mode)['rejectedCandidateCounts'])
        self.assertIn('source_observation_gap', self.run_prepare(evidence(interval_ms=110), **mode)['rejectedCandidateCounts'])

    def test_missing_receipt_and_video_join_fail_global_evidence(self):
        for target, expected in [('receipt', 'missing_terminal_receipts'), ('video', 'recording_count_mismatch')]:
            data = evidence()
            if target == 'receipt':
                data[0]['receipts'].pop(5)
            else:
                data[2].pop(5)
            with self.subTest(target=target), self.assertRaisesRegex(EvidenceError, expected):
                self.run_prepare(data)

    def test_duplicate_video_index_and_nonmonotonic_acquisition_fail(self):
        data = evidence()
        data[2][7]['videoFrameIndex'] = 6
        with self.assertRaisesRegex(EvidenceError, 'noncontiguous_video_index'):
            self.run_prepare(data)
        data = evidence()
        data[1][7]['sourceFrame'].update(acquiredAtMs=300, freshnessAtMs=300, freshnessClockKind='first_acquisition_qpc')
        with self.assertRaisesRegex(EvidenceError, 'nonmonotonic_observations'):
            self.run_prepare(data)

    def test_duplicate_real_source_is_not_a_second_history_image(self):
        data = evidence()
        for collection in (data[1], data[2]):
            collection[7]['sourceFrame'] = copy.deepcopy(collection[6]['sourceFrame'])
        result = self.run_prepare(data, max_jitter_ms=24)
        self.assertEqual(result['status'], 'no_eligible_windows')
        self.assertIn('grid_jitter_exceeded', result['rejectedCandidateCounts'])

    def test_history_reset_and_goal_change_boundaries_are_excluded(self):
        for change, reason in [('episodeStep', 'policy_history_reset'), ('policyGoalVersion', 'goal_or_control')]:
            data = evidence()
            data[0]['decisions'][7][change] = 1
            data[3][8][change] = 1
            result = self.run_prepare(data)
            self.assertEqual(result['status'], 'no_eligible_windows')
            self.assertTrue(any(reason in key for key in result['rejectedCandidateCounts']))

    def test_control_pause_between_frames_and_world_boundary_are_excluded(self):
        data = evidence()
        transition = {'type': 'controlTransition', 'state': 'held', 'reason': 'pause', 'clientTimeNs': int(390e6)}
        data[3].append(transition)
        data[0]['controlTransitions'] = [transition]
        self.assertIn('boundary:controlTransition', self.run_prepare(data)['rejectedCandidateCounts'])
        data = evidence()
        for rows in (data[1], data[2]):
            rows[7]['inputAvailable'] = False
        self.assertIn('world_or_capture_not_ready', self.run_prepare(data)['rejectedCandidateCounts'])

    def test_missing_events_or_ambiguous_receipt_action_are_not_labels(self):
        data = evidence()
        data[4]['droppedEvents'] = 1
        with self.assertRaisesRegex(EvidenceError, 'recording_loss:droppedEvents'):
            self.run_prepare(data)
        data = evidence()
        data[0]['receipts'][4]['appliedSteps'][0]['keys'] = ['D']
        data[3][35]['appliedSteps'][0]['keys'] = ['D']
        with self.assertRaisesRegex(EvidenceError, 'receipt_action_mismatch'):
            self.run_prepare(data)

    def test_mouse_events_are_not_repeated_across_an_arm(self):
        data = evidence()
        # r7 starts365ms, so the (350,400] label contains the delta exactly once.
        for step in (data[0]['decisions'][6]['steps'][0], data[0]['decisions'][6]['rawPolicySteps'][0],
                     data[0]['receipts'][6]['appliedSteps'][0], data[3][7]['steps'][0],
                     data[3][7]['rawPolicySteps'][0], data[3][37]['appliedSteps'][0]):
            step['mouseDx'] = 9
        result = self.run_prepare(data)
        for name in ('receipt_same_frames', 'receipt_nominal_20hz'):
            labels = [x['label'] for x in result['windows'][0]['arms'][name]['samples']]
            self.assertEqual(sum(x['mouseDx'] for x in labels), 9)
            self.assertEqual([e['eventId'] for x in labels for e in x['mouseEvents']], ['r7:step:0'])

    def test_known_empty_hold_is_distinct_from_missing_action_evidence(self):
        data = evidence()
        # A genuine completed action releases W; a later image can validly label an empty held state.
        data[0]['receipts'][5].update(status='completed', reason='horizon_complete', endedAtMs=340)
        data[3][36] = copy.deepcopy(data[0]['receipts'][5])
        result = self.run_prepare(data)
        first = result['windows'][0]['arms']['receipt_same_frames']['samples'][0]['label']
        self.assertEqual(first['heldKeys'], [])
        self.assertEqual(first['stateEvidenceEventId'], 'r6:release')

    def test_video_reordering_and_missing_pause_evidence_fail(self):
        data = evidence()
        data[2][5], data[2][6] = data[2][6], data[2][5]
        for index, row in enumerate(data[2]):
            row.update(videoFrameIndex=index, videoPtsSeconds=index/20)
        with self.assertRaisesRegex(EvidenceError, 'nonmonotonic_video_join'):
            self.run_prepare(data)
        data = evidence()
        data[0]['controlTransitions'] = [{'type': 'controlTransition', 'state': 'held', 'clientTimeNs': 390000000}]
        with self.assertRaisesRegex(EvidenceError, 'boundary_events'):
            self.run_prepare(data)

    def test_overlapping_receipt_owners_fail_even_with_matching_sidecars(self):
        data = evidence()
        data[0]['receipts'][4]['endedAtMs'] = 320
        data[3][35] = copy.deepcopy(data[0]['receipts'][4])
        with self.assertRaisesRegex(EvidenceError, 'overlapping_action_owners'):
            self.run_prepare(data)

    def test_native_resolution_change_is_not_mixed_into_a_window(self):
        data = evidence()
        for rows in (data[1], data[2]):
            rows[7]['sourceWidth'] = 1280
        self.assertIn('capture_geometry_boundary', self.run_prepare(data)['rejectedCandidateCounts'])

    def test_replacement_ends_at_exact_successor_acceptance(self):
        data = evidence()
        data[0]['receipts'][4]['endedAtMs'] -= 1
        data[3][35] = copy.deepcopy(data[0]['receipts'][4])
        with self.assertRaisesRegex(EvidenceError, 'replacement_successor_clock_mismatch'):
            self.run_prepare(data)

    def test_receipts_cannot_apply_future_decisions_to_earlier_images(self):
        data = evidence()
        count = len(data[0]['decisions'])
        for i, item in enumerate(data[0]['receipts']):
            accepted = (i+1)*25
            item['acceptedAtMs'] = accepted
            item['appliedSteps'][0]['startedAtMs'] = accepted+1
            item['endedAtMs'] = accepted+25 if i+1 < count else accepted+101
            data[0]['decisions'][i]['acceptance']['acceptedAtMs'] = accepted
            data[3][i+1]['acceptance']['acceptedAtMs'] = accepted
            data[3][count+1+i] = copy.deepcopy(item)
        with self.assertRaisesRegex(EvidenceError, 'receipt_before_observation_response'):
            self.run_prepare(data, comparison_mode='same-frames-only')

    def test_applied_goal_event_is_joined_and_bound_to_window_metadata(self):
        data = evidence()
        event = {'type': 'policyGoalChange', 'runId': 'run', 'requestId': 'new-goal',
                 'goalEmbedding': 'stand-still.json', 'policyGoalVersion': 1, 'appliedGoalRequestId': 'new-goal',
                 'goalIntent': 'stationary', 'status': 'applied', 'superseded': False, 'error': None,
                 'goalMetadata': {'instruction': 'Stand still.', 'file': 'stand-still.json'}, 'clientTimeNs': 175000000}
        data[0]['goalChanges'] = [event]
        data[3].append(copy.deepcopy(event))
        for i in range(3, len(data[0]['decisions'])):
            for decision in (data[0]['decisions'][i], data[3][i+1]):
                decision.update(policyGoalVersion=1, appliedGoalRequestId='new-goal', goalIntent='stationary')
        for mode in ('three-arm', 'same-frames-only'):
            result = self.run_prepare(data, comparison_mode=mode)
            goal = result['windows'][0]['goalProvenance']
            self.assertEqual(goal['source'], 'policyGoalChange')
            self.assertEqual(goal['appliedEvent'], event)
            self.assertEqual(goal['goalMetadata']['instruction'], 'Stand still.')
            self.assertIsNone(goal['initialGoalState']['goalMetadata'])
        # A complete event join cannot substitute a failed acknowledgement for an applied goal.
        data[0]['goalChanges'][0]['status'] = data[3][-1]['status'] = 'failed'
        result = self.run_prepare(data, comparison_mode='same-frames-only')
        self.assertIn('unresolved_applied_goal_provenance', result['rejectedCandidateCounts'])

    def test_explicit_cli_writes_manifest_without_decoding_video(self):
        data = evidence()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            for name, item in zip(('report.json', 'observations.jsonl', 'frames.jsonl', 'events.jsonl', 'recording.json'), data):
                text = '\n'.join(json.dumps(x) for x in item) if name.endswith('.jsonl') else json.dumps(item)
                (path/name).write_text(text, encoding='utf-8')
            (path/'frames.mp4').write_bytes(b'synthetic fixture; no decoding promised')
            with redirect_stdout(io.StringIO()):
                code = main(['--report', str(path/'report.json'), '--recording-dir', str(path),
                             '--output', str(path/'plan.json'), '--history-frames', '3', '--max-windows', '1',
                             '--probe-frame-id', '10'])
            result = json.loads((path/'plan.json').read_text())
            self.assertEqual(code, 0)
            self.assertEqual(len(result['inputEvidence']), 6)
            self.assertFalse(result['trainingEligible'])
            self.assertEqual(len(result['inputEvidence']['frames.mp4']['sha256']), 64)
            with redirect_stdout(io.StringIO()):
                code = main(['--report', str(path/'report.json'), '--recording-dir', str(path),
                             '--output', str(path/'two-arm.json'), '--history-frames', '3',
                             '--probe-frame-id', '10', '--comparison-mode', 'same-frames-only'])
            result = json.loads((path/'two-arm.json').read_text())
            self.assertEqual(code, 0)
            self.assertEqual(result['comparisonMode'], 'same-frames-only')
            self.assertEqual(len(result['windows'][0]['arms']), 2)


if __name__ == '__main__':
    unittest.main()
