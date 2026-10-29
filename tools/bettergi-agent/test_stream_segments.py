"""CPU-only evidence rollover and healthy controller continuity regressions."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import stream_client as client
from stream_segments import EvidencePublicationError, RecordingBudget, StreamSegments


def report():
    return dict(hello={'sessionId': 'lease', 'ownerEpoch': 'owner'}, decisions=[], receipts=[],
                framesReceived=0, acceptedInputActions=0, unappliedAcceptedActions=0, receiptHistoryResets=0,
                captureQuality={'check': 'test', 'usableFrames': 0}, controlTransitions=[], goalChanges=[],
                navigationIdleRecoveryEvents=[])


def header(number):
    return {'frameId': number, 'capturedAtMs': number*10, 'sourceFrame': {'freshnessAtMs': number*10-5},
            'width': 2, 'height': 2}


def proposal(request, frame_id):
    return {'type': 'proposal', 'frameId': frame_id, 'observedAtMs': frame_id*10,
            'startBeforeMs': frame_id*10+145, 'steps': [{'keys': ['W'], 'durationMs': 100}],
            'acceptance': {'type': 'accepted', 'requestId': request}}


class RecordingMetadataTests(unittest.TestCase):
    def test_ordinary_recording_omits_only_redundant_context_without_mutating_live_frame(self):
        original = dict(header(1), navigationPose={'state': 'valid', 'frameId': 1},
                        executionContext={'rolling': ['prior-input']}, receipts=[{'requestId': 'a'}])
        result = client.recording_frame_metadata(original, 'off')
        self.assertNotIn('executionContext', result)
        self.assertTrue(result.pop('executionContextOmitted'))
        self.assertEqual(result, {k:v for k,v in original.items() if k != 'executionContext'})
        self.assertEqual(original['executionContext'], {'rolling': ['prior-input']})

    def test_explicit_context_recording_and_model_modes_preserve_full_context(self):
        original = dict(header(1), executionContext={'rolling': ['prior-input']})
        for mode in ('record', 'model'):
            self.assertEqual(client.recording_frame_metadata(original, mode), original)


class Recorder:
    """Model independently draining encoders without spawning a process."""
    def __init__(self, directory, *args, **kwargs):
        self.directory = directory
        self.error = None
        self.items = []
        self.events = []
        self.context = []
        self.close_gate = threading.Event()
        self.close_gate.set()
        self.finalizing = threading.Event()
        self.closing = False

    def put(self, metadata, pixels):
        assert not self.closing
        self.items.append(metadata)
        return True

    def event(self, item):
        assert not self.closing
        self.events.append(item)
        return True

    def observation(self, metadata, continuity=False):
        self.context.append(dict(metadata, continuityContext=continuity, videoQueueAccepted=None))

    def begin_close(self):
        self.closing = True

    def close(self, timeout=20):
        self.finalizing.set()
        if not self.close_gate.wait(timeout):
            self.error = 'synthetic recorder timeout'
        return {'complete': self.error is None, 'error': self.error, 'encodedFrames': len(self.items),
                'workerRetired': self.close_gate.is_set()}

    def fail(self, reason):
        self.error = reason


class SegmentTests(unittest.TestCase):
    def args(self, folder, record=True):
        return SimpleNamespace(output=str(Path(folder)/'reports'/'00001.json'),
            lease_output=str(Path(folder)/'reports'/'lease-00001.json'),
            record_dir=str(Path(folder)/'video'/'00001') if record else None,
            ffmpeg='unused', fps=30, preview=False, record_max_mib=1, segment_seconds=1)

    def test_only_negotiated_native_p2p_segments_receive_the_larger_image_queue(self):
        for model, contract, expected in (
                ('open-p2p', {'profile': client.P2P_NATIVE, 'serverAdvertised': True}, 32),
                ('open-p2p', {'profile': client.LEGACY, 'serverAdvertised': True}, 8),
                ('open-p2p', {'profile': client.P2P_NATIVE, 'serverAdvertised': False}, 8),
                ('open-p2p', {}, 8), ('observe', {'profile': client.P2P_NATIVE, 'serverAdvertised': True}, 8)):
            with self.subTest(model=model, contract=contract), tempfile.TemporaryDirectory() as folder:
                capacities = []
                def factory(*args, **kwargs):
                    capacities.append(kwargs['frame_capacity'])
                    return Recorder(*args, **kwargs)
                state = dict(report(), model=model, preprocessingContract=contract)
                archive = StreamSegments(self.args(folder), factory, state, now=0)
                archive.rotate(state, 2)
                state['endReason'] = 'durationElapsed'
                archive.finish(state)
                self.assertEqual(capacities, [expected, expected])

    def test_slow_finalizer_keeps_active_capture_and_carries_original_join_context(self):
        with tempfile.TemporaryDirectory() as folder:
            recorders = []
            def factory(*args, **kwargs):
                instance = Recorder(*args, **kwargs)
                recorders.append(instance)
                return instance
            state = report()
            archive = StreamSegments(self.args(folder), factory, state, now=0)
            recorders[0].close_gate.clear()
            archive.put(header(1), bytes(range(12)))
            original = proposal('crossing', 1)
            archive.event(original)
            state['decisions'].append(copy.deepcopy(original))
            state.update(framesReceived=1, acceptedInputActions=1)
            state['captureQuality']['usableFrames'] = 1
            archive.rotate(state, 1)
            self.assertTrue(recorders[0].finalizing.wait(2))
            self.assertFalse(recorders[0].close_gate.is_set())
            # The old encoder is still blocked, while the new one accepts images/events.
            archive.put(header(2), bytes(range(12)))
            receipt = {'requestId': 'crossing', 'frameId': 1, 'status': 'completed',
                       'appliedSteps': [{'startedAtMs': 20, 'keys': ['W']}]}
            archive.event(receipt)
            state['receipts'].append(receipt)
            state['framesReceived'] += 1
            state['captureQuality']['usableFrames'] += 1
            self.assertEqual(recorders[1].context[0]['frameId'], 1)
            self.assertIsNone(recorders[1].context[0]['videoQueueAccepted'])
            self.assertNotIn('videoFrameIndex', recorders[1].context[0])
            self.assertEqual(len(recorders[1].items), 1)
            with self.assertRaisesRegex(RuntimeError, 'backlog'):
                archive.rotate(state, 2)
            self.assertEqual(len(recorders), 2)
            self.assertEqual(archive.number, 2)
            self.assertEqual(state['receipts'], [receipt])
            recorders[0].close_gate.set()
            state['endReason'] = 'durationElapsed'
            manifest = archive.finish(state)
            self.assertEqual(manifest['status'], 'completed')
            self.assertEqual(len(manifest['segments']), 2)
            first, second = [json.loads(Path(item['report']).read_text()) for item in manifest['segments']]
            self.assertEqual((first['acceptedInputActions'], second['acceptedInputActions']), (1, 0))
            self.assertEqual((first['framesReceived'], second['framesReceived']), (1, 1))
            self.assertEqual(second['continuity']['pendingProposals'][0]['acceptance']['requestId'], 'crossing')
            self.assertEqual(second['continuity']['sourceFrames'][0], header(1))
            self.assertEqual(second['receipts'], [receipt])
            self.assertFalse(first['segment']['leaseEnded'])
            self.assertTrue(second['segment']['leaseEnded'])
            self.assertEqual(state['acceptedInputActions'], 1)  # Controller cap stays cumulative.

    def test_receipt_before_proposal_event_does_not_pin_finished_action_forever(self):
        with tempfile.TemporaryDirectory() as folder:
            state = report()
            archive = StreamSegments(self.args(folder, record=False), Recorder, state, now=0)
            archive.put(header(1), b'')
            archive.event({'requestId': 'fast', 'appliedSteps': []})
            archive.event(proposal('fast', 1))
            self.assertFalse(archive.pending)
            for number in range(2, 1000):
                archive.put(header(number), b'')
            self.assertEqual(len(archive.headers), 256)
            state['endReason'] = 'durationElapsed'
            archive.finish(state)

    def test_shared_budget_is_monotonic_across_both_writers(self):
        budget = RecordingBudget(100)
        self.assertEqual(budget.update('old', 60), 60)
        self.assertEqual(budget.update('new', 30), 90)
        self.assertEqual(budget.update('old', 55), 90)
        self.assertEqual(budget.update('old', 75), 105)
        self.assertEqual(budget.used, 105)

    def test_next_segment_starts_with_current_goal_without_rewriting_lease_origin(self):
        with tempfile.TemporaryDirectory() as folder:
            state = report()
            state.update(initialGoalState={'policyGoalVersion': 0}, policyMetadata={'goal': 'first'},
                         finalGoalState={'policyGoalVersion': 1}, finalPolicyMetadata={'goal': 'second'})
            state['goalChanges'].append({'policyGoalVersion': 1})
            archive = StreamSegments(self.args(folder, False), Recorder, state, now=0)
            archive.rotate(state, 1)
            self.assertEqual(state['initialGoalState'], {'policyGoalVersion': 1})
            self.assertEqual(state['policyMetadata'], {'goal': 'second'})
            self.assertEqual(state['goalChanges'], [])
            state['endReason'] = 'durationElapsed'
            manifest = archive.finish(state)
            first, second = [json.loads(Path(part['report']).read_text()) for part in manifest['segments']]
            self.assertEqual(first['initialGoalState'], {'policyGoalVersion': 0})
            self.assertEqual(first['policyMetadata'], {'goal': 'first'})
            self.assertEqual(second['initialGoalState'], {'policyGoalVersion': 1})
            self.assertEqual(second['policyMetadata'], {'goal': 'second'})
            self.assertEqual(second['leaseInitialGoalState'], {'policyGoalVersion': 0})
            self.assertEqual(second['leaseInitialPolicyMetadata'], {'goal': 'first'})

    def test_missing_source_or_request_identity_fails_join_explicitly(self):
        with tempfile.TemporaryDirectory() as folder:
            state = report()
            archive = StreamSegments(self.args(folder, False), Recorder, state, now=0)
            with self.assertRaisesRegex(RuntimeError, 'source header'):
                archive.event(proposal('unknown', 99))
            missing = proposal('ignored', 1)
            missing['acceptance'].pop('requestId')
            with self.assertRaisesRegex(RuntimeError, 'requestId'):
                archive.event(missing)
            state['endReason'] = 'error'
            archive.finish(state)

    def test_report_write_failure_retains_terminal_evidence_and_fails_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            state = report()
            archive = StreamSegments(self.args(folder, False), Recorder, state, now=0)
            state['acceptedInputActions'] = 1
            with patch.object(Path, 'replace', side_effect=OSError('synthetic disk failure')):
                archive.rotate(state, 1)
                deadline = time.monotonic()+2
                while archive.retiring is not None and time.monotonic() < deadline:
                    time.sleep(.005)
                self.assertIsNone(archive.retiring)
            state['endReason'] = 'error'
            state['error'] = 'prior archive failed'
            manifest = archive.finish(state)
            self.assertEqual(manifest['status'], 'failed')
            self.assertIn('synthetic disk failure', manifest['evidenceError'])
            self.assertEqual(manifest['acceptedInputActions'], 1)
            self.assertEqual(len(manifest['segments']), 2)
            self.assertTrue(Path(manifest['segments'][1]['report']).exists())
            self.assertFalse(archive.worker.is_alive())

    def test_terminal_submission_cannot_be_lost_during_retirement_exit_check(self):
        class PausedExitCheck:
            def __init__(self):
                self.value = threading.Event()
                self.entered = threading.Event()
                self.resume = threading.Event()
                self.once = True
            def set(self):
                self.value.set()
            def is_set(self):
                if self.once and threading.current_thread().name == 'BetterGI-segments':
                    self.once = False
                    self.entered.set()
                    if not self.resume.wait(2):
                        raise AssertionError('Test did not resume the retirement exit check')
                return self.value.is_set()
        with tempfile.TemporaryDirectory() as folder:
            state = report()
            archive = StreamSegments(self.args(folder, False), Recorder, state, now=0)
            gate = PausedExitCheck()
            archive.closing = gate
            archive.rotate(state, 1)
            self.assertTrue(gate.entered.wait(2))
            state['endReason'] = 'durationElapsed'
            result = []
            finished = threading.Event()
            def finish():
                result.append(archive.finish(state))
                finished.set()
            thread = threading.Thread(target=finish)
            thread.start()
            try:
                self.assertFalse(finished.wait(.03))
            finally:
                gate.resume.set()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result[0]['status'], 'completed', result)
            self.assertEqual(len(result[0]['segments']), 2)
            self.assertEqual(archive.submitted, 2)
            terminal = json.loads(Path(result[0]['segments'][-1]['report']).read_text())
            self.assertTrue(terminal['segment']['leaseEnded'])

    def test_unretired_recording_worker_forbids_a_third_writer(self):
        with tempfile.TemporaryDirectory() as folder:
            recorders = []
            def factory(*args, **kwargs):
                instance = Recorder(*args, **kwargs)
                recorders.append(instance)
                return instance
            state = report()
            archive = StreamSegments(self.args(folder), factory, state, now=0)
            # Queue/encoder closed is insufficient when its last filesystem write
            # still holds the worker. This fake deliberately has no prior error.
            recorders[0].close = lambda: {'closed': True, 'workerRetired': False, 'error': None}
            archive.rotate(state, 1)
            deadline = time.monotonic()+2
            while archive.retiring is not None and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertIsNone(archive.retiring)
            with self.assertRaisesRegex(RuntimeError, 'did not retire'):
                archive.rotate(state, 2)
            self.assertEqual(len(recorders), 2)
            state['endReason'] = 'error'
            manifest = archive.finish(state)
            self.assertEqual(manifest['status'], 'failed')
            self.assertIn('did not retire', manifest['evidenceError'])
            self.assertEqual(len(recorders), 2)

    def test_manifest_publication_failure_retains_totals_and_unknown_outcome(self):
        with tempfile.TemporaryDirectory() as folder:
            state = report()
            archive = StreamSegments(self.args(folder, False), Recorder, state, now=0)
            state.update(acceptedInputActions=3, framesReceived=7, endReason='error',
                         unacknowledgedAction={'requestId': 'unknown-request'})
            archive.budget.update('prior', 1234)
            original = Path.write_text
            def write(path, *args, **kwargs):
                if path.name == 'lease-00001.tmp':
                    raise OSError('synthetic manifest failure')
                return original(path, *args, **kwargs)
            with patch.object(Path, 'write_text', write):
                with self.assertRaises(EvidencePublicationError) as caught:
                    archive.finish(state)
            manifest = caught.exception.manifest
            self.assertEqual(manifest['acceptedInputActions'], 3)
            self.assertEqual(manifest['recordedBytes'], 1234)
            self.assertEqual(manifest['unacknowledgedAction'], 'unknown-request')
            self.assertIn('synthetic manifest failure', manifest['evidenceError'])
            self.assertFalse(Path(archive.args.lease_output).exists())
            self.assertTrue(Path(manifest['segments'][0]['report']).exists())

    def test_real_encoders_rotate_without_fabricating_video_indices_for_context(self):
        ffmpeg = shutil.which('ffmpeg') or ('C:/programs/ffmpeg.exe' if Path('C:/programs/ffmpeg.exe').exists() else None)
        if not ffmpeg:
            self.skipTest('Existing FFmpeg is unavailable')
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(folder)
            args.ffmpeg = ffmpeg
            state = report()
            archive = StreamSegments(args, client.AsyncVideoRecorder, state, now=0)
            archive.put(header(1), bytes(range(12)))
            archive.event(proposal('across-file', 1))
            state.update(framesReceived=1, acceptedInputActions=1)
            state['captureQuality']['usableFrames'] = 1
            archive.rotate(state, 1)
            archive.put(header(2), bytes(reversed(range(12))))
            receipt = {'requestId': 'across-file', 'frameId': 1, 'appliedSteps': [{'startedAtMs': 20}]}
            archive.event(receipt)
            state['receipts'].append(receipt)
            state['framesReceived'] += 1
            state['captureQuality']['usableFrames'] += 1
            state['endReason'] = 'durationElapsed'
            manifest = archive.finish(state)
            self.assertEqual(manifest['status'], 'completed', manifest)
            self.assertGreater(manifest['recordedBytes'], 0)
            for number in (1, 2):
                directory = Path(args.record_dir).parent / f'{number:05d}'
                frames = [json.loads(row) for row in (directory/'frames.jsonl').read_text().splitlines()]
                self.assertEqual([(item['frameId'], item['videoFrameIndex']) for item in frames], [(number, 0)])
                self.assertTrue((directory/'frames.mp4').is_file())
            directory = Path(args.record_dir).parent/'00002'
            observations = [json.loads(row) for row in (directory/'observations.jsonl').read_text().splitlines()]
            carried = next(item for item in observations if item.get('continuityContext'))
            self.assertEqual(carried['frameId'], 1)
            self.assertIsNone(carried['videoQueueAccepted'])
            self.assertNotIn('videoFrameIndex', carried)
            events = [json.loads(row) for row in (directory/'events.jsonl').read_text().splitlines()]
            self.assertIn(receipt, events)
            self.assertEqual(events[0]['continuity']['pendingProposals'][0]['acceptance']['requestId'], 'across-file')


class ContinuousBridge:
    """Hold one synthetic action across reporting boundaries; use real CPU clocks only."""
    def __init__(self, name):
        self.origin = time.perf_counter()
        self.hello = {'version': 1, 'sessionId': 'one-lease', 'ownerEpoch': 'one-owner',
                      'goalVersion': 1, 'inputEnabled': True, 'allowedKeys': ['W'],
                      'supportsStartBeforeMs': True}
        self.handle = SimpleNamespace(close=lambda: None)
        self.frames = 0
        self.commands = []
        self.pending = None
        self.receipts = []

    def receipt(self):
        if self.pending is None:
            return
        self.receipts.append({'requestId': self.pending['requestId'], 'modelId': 'open-p2p',
                              'frameId': self.pending['frameId'], 'status': 'completed',
                              'appliedSteps': [{'startedAtMs': self.pending['observedAtMs']+1, 'keys': ['W']}]})
        self.pending = None

    def request(self, command, **kwargs):
        self.commands.append((command, kwargs))
        if command == 'action':
            self.receipt()
            self.pending = kwargs
            return {'type': 'accepted', 'requestId': kwargs['requestId']}, b''
        if command == 'stop':
            self.receipt()
            receipts, self.receipts = self.receipts, []
            return {'type': 'stopped', 'receipts': receipts}, b''
        assert command == 'frame'
        self.frames += 1
        now = (time.perf_counter()-self.origin)*1000
        receipts, self.receipts = self.receipts, []
        return {'type': 'frame', 'frameId': self.frames, 'capturedAtMs': now, 'serverNowMs': now,
                'sourceWidth': 2, 'sourceHeight': 2, 'width': 2, 'height': 2,
                'pixelFormat': 'rgb24', 'payloadBytes': 12, 'receipts': receipts}, bytes(range(12))


class ContinuousPolicy:
    metadata = {'synthetic': True}
    execution_feedback = True
    def __init__(self):
        self.steps = 0
        self.resets = 0
    def predict(self, image, size):
        self.steps += 1
        return {'parseValid': True, 'steps': [{'keys': ['W'], 'durationMs': 100, 'mouseDx': 0, 'mouseDy': 0}],
                'episodeStep': self.steps, 'fullActionMs': 1}
    def reset(self):
        self.resets += 1
    def finish_action(self, committed):
        assert committed


class HealthyLeaseTests(unittest.TestCase):
    def test_rollover_keeps_one_owner_history_and_global_action_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            args = client.parse_arguments(['--seconds', '2', '--segment-seconds', '.07', '--fps', '100',
                '--decision-hz', '10', '--enable-input', '--max-input-actions', '4', '--model', 'open-p2p',
                '--source', 'synthetic', '--checkpoint', 'synthetic',
                '--output', str(Path(folder)/'00001.json')])
            args.lease_output = str(Path(folder)/'lease.json')
            args.record_dir = str(Path(folder)/'recordings'/'00001')
            bridge = ContinuousBridge('test')
            policy = ContinuousPolicy()
            recorders = []

            def recorder_factory(*values, **kwargs):
                recorder = Recorder(*values, **kwargs)
                recorders.append(recorder)
                return recorder

            with patch.object(client, 'Bridge', return_value=bridge), \
                    patch.object(client, 'AsyncVideoRecorder', side_effect=recorder_factory), redirect_stdout(io.StringIO()):
                self.assertEqual(client.run_episode(args, policy), 0)
            manifest = json.loads(Path(args.lease_output).read_text())
            parts = [json.loads(Path(item['report']).read_text()) for item in manifest['segments']]
            self.assertGreaterEqual(len(parts), 3)
            self.assertEqual(manifest['acceptedInputActions'], 4)
            self.assertEqual(sum(item['acceptedInputActions'] for item in parts), 4)
            self.assertEqual([name for name, _ in bridge.commands].count('stop'), 1)
            self.assertNotIn('release', [name for name, _ in bridge.commands])
            self.assertEqual(policy.resets, 0)
            self.assertEqual([item['episodeStep'] for part in parts for item in part['decisions']], [1, 2, 3, 4])
            requests = {args['requestId'] for name, args in bridge.commands if name == 'action'}
            received = {item['requestId'] for part in parts for item in part['receipts']}
            self.assertEqual(requests, received)
            for part in parts:
                local = {item['acceptance']['requestId'] for item in part['decisions']}
                carried = {item['acceptance']['requestId'] for item in part['continuity']['pendingProposals']}
                for receipt in part['receipts']:
                    self.assertIn(receipt['requestId'], local | carried)
            self.assertEqual(parts[-1]['endReason'], 'maxInputActions')
            self.assertTrue(all(part['hello']['sessionId'] == 'one-lease' for part in parts))
            events = [event for recorder in recorders for event in recorder.events if event.get('type') == 'proposal']
            self.assertEqual(len(events), 4)
            self.assertTrue(all(event['proposalJournalVersion'] == 2 and event['historyCommitted'] is True
                                for event in events))
            originals = {event['acceptance']['requestId']: event for event in events}
            carried_count = 0
            for part in parts:
                self.assertEqual(part['proposalJournal'], {'version': 2, 'historyCommitMode': 'accepted-proposals-only'})
                for pending in part['continuity']['pendingProposals']:
                    carried_count += 1
                    self.assertEqual({key: value for key, value in pending.items() if key != 'originSegment'},
                                     originals[pending['acceptance']['requestId']])
            self.assertGreater(carried_count, 0)

    def test_lost_action_acknowledgement_keeps_original_request_and_does_not_replay(self):
        class LostAcknowledgement(ContinuousBridge):
            def request(self, command, **kwargs):
                result = super().request(command, **kwargs)
                if command == 'action':
                    raise EOFError('synthetic acknowledgement loss')
                return result
        with tempfile.TemporaryDirectory() as folder:
            args = client.parse_arguments(['--seconds', '1', '--enable-input', '--model', 'open-p2p',
                '--source', 'synthetic', '--checkpoint', 'synthetic', '--output', str(Path(folder)/'00001.json')])
            args.lease_output = str(Path(folder)/'lease.json')
            bridge = LostAcknowledgement('test')
            with patch.object(client, 'Bridge', return_value=bridge), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(EOFError, 'acknowledgement loss'):
                    client.run_episode(args, ContinuousPolicy())
            manifest = json.loads(Path(args.lease_output).read_text())
            part = json.loads(Path(manifest['segments'][0]['report']).read_text())
            requests = [item for name, item in bridge.commands if name == 'action']
            self.assertEqual(len(requests), 1)
            self.assertEqual(manifest['status'], 'failed')
            self.assertEqual(manifest['unacknowledgedAction'], requests[0]['requestId'])
            self.assertEqual(part['unacknowledgedAction']['frame']['frameId'], requests[0]['frameId'])
            self.assertEqual(part['receipts'][0]['requestId'], requests[0]['requestId'])
            self.assertEqual([name for name, _ in bridge.commands].count('stop'), 1)

    def test_original_run_deadline_already_elapsed_does_not_send_input(self):
        with tempfile.TemporaryDirectory() as folder:
            args = client.parse_arguments(['--seconds', '5', '--enable-input', '--model', 'open-p2p',
                '--source', 'synthetic', '--checkpoint', 'synthetic', '--output', str(Path(folder)/'00001.json')])
            args.lease_output = str(Path(folder)/'lease.json')
            args.lease_deadline = time.monotonic()-1
            bridge = ContinuousBridge('test')
            policy = ContinuousPolicy()
            with patch.object(client, 'Bridge', return_value=bridge), redirect_stdout(io.StringIO()):
                client.run_episode(args, policy)
            self.assertEqual(policy.steps, 0)
            self.assertNotIn('action', [name for name, _ in bridge.commands])
            self.assertEqual([name for name, _ in bridge.commands].count('stop'), 1)


if __name__ == '__main__':
    unittest.main()
