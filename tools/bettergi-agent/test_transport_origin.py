"""Synthetic transport-origin and resident retry tests; no Windows pipe or model."""
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import bridge_transport as origin
import resident_runtime as resident
import stream_client as client
from test_resident_runtime import child
from test_stream_client import FragmentedPipe, ScriptedBridge, FakePolicy, bridge_with, packet


def fail(error):
    """Raise the exact supplied exception, including from a fake pipe method."""
    def operation(*args, **kwargs):
        raise error
    return operation


def disconnected():
    """Obtain an actual Bridge-generated EOF from an empty synthetic pipe."""
    try:
        bridge_with(FragmentedPipe(b''))._exact(4)
    except EOFError as error:
        return error
    raise AssertionError('The empty pipe did not disconnect')


class BridgeOriginTests(unittest.TestCase):
    """Only the named-pipe operations confer provenance; exception identity stays exact."""
    def test_open_read_write_failures_keep_original_exception(self):
        for operation in ('open', 'read', 'write'):
            with self.subTest(operation=operation):
                error = OSError('synthetic ' + operation)
                if operation == 'open':
                    with patch.object(client, 'os', SimpleNamespace(name='nt')), \
                            patch.object(client, 'open', fail(error), create=True):
                        with self.assertRaises(OSError) as caught:
                            client.Bridge('BetterGI.Agent.synthetic')
                else:
                    handle = FragmentedPipe(packet({'type': 'status'}))
                    setattr(handle, operation, fail(error))
                    bridge = bridge_with(handle)
                    with self.assertRaises(OSError) as caught:
                        bridge._exact(4) if operation == 'read' else bridge.request('status')
                self.assertIs(caught.exception, error)
                self.assertEqual(origin.transport_origin(error), operation)
                self.assertTrue(origin.is_transport_failure(error))

    def test_zero_read_and_zero_write_are_explicit_eof(self):
        read_error = disconnected()
        handle = FragmentedPipe(b''); handle.write = lambda data: 0
        with self.assertRaises(EOFError) as caught:
            bridge_with(handle).request('status')
        for error in (read_error, caught.exception):
            self.assertEqual(origin.transport_origin(error), 'eof')
            self.assertTrue(origin.is_transport_failure(error))

    def test_serialization_and_close_oserrors_are_not_transport(self):
        handle = FragmentedPipe(b''); bridge = bridge_with(handle)
        error = OSError('same error class as pipe I/O')
        with patch.object(client.json, 'dumps', fail(error)):
            with self.assertRaises(OSError) as caught:
                bridge.request('status')
        self.assertIs(caught.exception, error); self.assertFalse(origin.is_transport_failure(error))
        self.assertEqual(handle.written, b'')
        handle.close = fail(error)
        with self.assertRaises(OSError) as caught: handle.close()
        self.assertIs(caught.exception, error); self.assertIsNone(origin.transport_origin(error))

    def test_intake_errors_are_terminal_without_retyping(self):
        for phase in ('prepare', 'receive'):
            with self.subTest(phase=phase):
                error = OSError('synthetic intake ' + phase); failures = []
                handle = FragmentedPipe(packet({'type': 'status'})); bridge = bridge_with(handle)
                intake = SimpleNamespace(prepare=lambda value: value, receive=lambda *a, **k: None,
                    failed=lambda value, **kw: failures.append(kw))
                setattr(intake, phase, fail(error)); bridge._step_application_intake = intake
                with self.assertRaises(OSError) as caught: bridge.request('status')
                self.assertIs(caught.exception, error); self.assertFalse(origin.is_transport_failure(error))
                self.assertEqual(failures, [{'write_attempted': phase == 'receive'}])

    def test_experimental_pipe_failure_is_marked_but_never_retryable(self):
        import test_step_application_handshake as h
        bridge, owned, _, _ = h.bridge(extra=h.packet(dict(type='status')))
        intake = bridge.enable_experimental_step_applications(reviewed_producer_build_sha256=h.BUILD)
        error = OSError('original negotiated pipe failure'); owned.write = fail(error)
        with self.assertRaises(OSError) as caught: bridge.request('status')
        self.assertIs(caught.exception, error); self.assertEqual(origin.transport_origin(error), 'write')
        self.assertFalse(origin.is_transport_failure(error)); self.assertTrue(intake.ledger.quarantined)

    def test_enable_pipe_failure_is_terminal_and_keeps_owned_close(self):
        import test_step_application_handshake as h
        bridge, owned, _, _ = h.bridge(); error = OSError('original enable write')
        owned.write = fail(error)
        with self.assertRaises(OSError) as caught:
            bridge.enable_experimental_step_applications(reviewed_producer_build_sha256=h.BUILD)
        self.assertIs(caught.exception, error); self.assertIs(bridge._experimental_enable_error, error)
        self.assertFalse(origin.is_transport_failure(error)); self.assertEqual(owned.close_calls, 1)

    def test_error_number_message_and_cause_do_not_confer_origin(self):
        for error in (OSError(32, 'pipe'), BrokenPipeError('pipe'), EOFError('pipe')):
            self.assertFalse(origin.is_transport_failure(error))
        error = RuntimeError('terminal recovery failure'); error.__cause__ = disconnected()
        self.assertFalse(origin.is_transport_failure(error))


class ResidentDispositionTests(unittest.TestCase):
    """Account actual failed evidence once before retry or terminal propagation."""
    def scenario(self, failure=None, *, returned_failure=False, veto=None, retry=False):
        """Keep all authority and report files in this owned synthetic directory."""
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(output=str(Path(directory)/'resident.json'), model='observe',
                rdp_session_id=3, control_file=None, seconds=2, reconnect_timeout=1,
                enable_input=True, segment_seconds=1, record_dir=None, max_input_actions=2)
            counts = dict(starts=0, calls=0, resets=0, loads=0)
            def start(entry, *a, **k): counts['starts'] += 1; return entry
            def reset(): counts['resets'] += 1
            policy = SimpleNamespace(reset=reset)
            def load(args): counts['loads'] += 1; return policy
            lifecycle = SimpleNamespace(discover=lambda: {'instances':[child()]}, start_agent=start)
            def episode(values, actual, control):
                self.assertIs(actual, policy); counts['calls'] += 1
                if counts['calls'] > 1 and not retry: raise AssertionError('Unexpected reconnect')
                failed = counts['calls'] == 1
                manifest = dict(status='failed' if failed else 'completed',
                    segments=[dict(number=counts['calls'], report=values.output, exitCode=int(failed),
                                   acceptedInputActions=1)], acceptedInputActions=1, framesReceived=1,
                    recordedBytes=7, recordingBudgetExhausted=False,
                    endReason='streamError' if failed else 'maxInputActions')
                if veto: manifest[veto] = 'synthetic unknown/evidence failure'
                resident.atomic_json(values.lease_output, manifest)
                if failed and failure is not None: raise failure
                return int(failed and returned_failure)
            caught = None; result = None
            with patch.object(resident, 'require_current_rdp'), \
                    patch.object(resident, 'control_module', return_value=lifecycle):
                try: result = resident.run_resident(args, load, episode)
                except Exception as error: caught = error
            summary = json.loads(Path(args.output).read_text())
            return result, caught, summary, counts

    def test_unmarked_io_and_non_io_errors_account_once_and_never_reconnect(self):
        for error in (OSError('prediction'), BrokenPipeError('stdout'), EOFError('model data'),
                      ValueError('frame contract'), RuntimeError('terminal recovery')):
            with self.subTest(error=str(error)):
                _, caught, report, counts = self.scenario(error)
                self.assertIs(caught, error); self.assertEqual(counts['starts'], 1)
                self.assertEqual(report['acceptedInputActions'], 1); self.assertEqual(report['recordedBytes'], 7)
                self.assertEqual(report['failedLeases'], 1); self.assertEqual(len(report['segments']), 1)

    def test_marked_pipe_loss_reuses_model_and_preserves_action_accounting(self):
        result, caught, report, counts = self.scenario(disconnected(), retry=True)
        self.assertIsNone(caught); self.assertEqual(result, 1)
        self.assertEqual(counts, dict(starts=2, calls=2, resets=2, loads=1))
        self.assertEqual(report['acceptedInputActions'], 2); self.assertEqual(report['recordedBytes'], 14)
        self.assertEqual(report['failedLeases'], 1)

    def test_generic_failed_return_is_terminal_without_a_transport_exception(self):
        result, caught, report, counts = self.scenario(returned_failure=True)
        self.assertIsNone(caught); self.assertEqual(result, 1); self.assertEqual(counts['starts'], 1)
        self.assertEqual(report['acceptedInputActions'], 1); self.assertFalse(report['evidenceComplete'])

    def test_failed_manifest_is_terminal_even_if_callback_returns_zero(self):
        result, caught, report, counts = self.scenario()
        self.assertIsNone(caught); self.assertEqual(result, 1); self.assertEqual(counts['starts'], 1)
        self.assertEqual(report['acceptedInputActions'], 1); self.assertFalse(report['evidenceComplete'])

    def test_unknown_action_and_incomplete_evidence_override_pipe_origin(self):
        for veto in ('unacknowledgedAction', 'evidenceError'):
            with self.subTest(veto=veto):
                _, caught, report, counts = self.scenario(disconnected(), veto=veto)
                self.assertIsInstance(caught, RuntimeError); self.assertEqual(counts['starts'], 1)
                self.assertEqual(report['acceptedInputActions'], 1); self.assertEqual(report['recordedBytes'], 7)


class EpisodeDispositionTests(unittest.TestCase):
    """Use the actual episode and synthetic RGB/control/pipe callbacks only."""
    def episode(self, bridge, policy=None, *, printing_error=None, stop_error=None,
                recorder=None, producer_type=None, control=None):
        """Publish a real temporary report while fake callbacks provide all observations."""
        from contextlib import ExitStack, redirect_stdout
        import sys
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            output = Path(directory)/'report.json'
            argv = ['--seconds','.08','--fps','100','--decision-hz','100','--output',str(output)]
            if policy: argv += ['--model','open-p2p','--source','synthetic','--checkpoint','synthetic']
            if recorder: argv += ['--record-dir',str(Path(directory)/'recording')]
            args = client.parse_arguments(argv)
            stack.enter_context(patch.object(client,'Bridge',return_value=bridge))
            stack.enter_context(patch.dict(sys.modules, {'PIL': SimpleNamespace(
                Image=SimpleNamespace(frombytes=lambda *args: args[-1]))}))
            stack.enter_context(redirect_stdout(io.StringIO()))
            if recorder: stack.enter_context(patch.object(client,'AsyncVideoRecorder',return_value=recorder))
            if producer_type: stack.enter_context(patch.object(client.threading,'Thread',producer_type))
            if printing_error: stack.enter_context(patch.object(client,'print',fail(printing_error),create=True))
            if stop_error:
                request = bridge.request
                def wrapped(command, **kwargs):
                    if command == 'stop': raise stop_error
                    return request(command, **kwargs)
                bridge.request = wrapped
            caught = None
            try: result = client.run_episode(args, policy, control)
            except Exception as error: caught = error; result = None
            self.assertTrue(bridge.handle.closed)
            return result, caught, json.loads(output.read_text())

    def test_frame_thread_original_errors_survive_report_publication(self):
        for error in (disconnected(), OSError('frame callback file'), ValueError('frame shape')):
            with self.subTest(error=str(error)):
                bridge = ScriptedBridge([bytes(range(12))], before_frame=fail(error))
                _, caught, report = self.episode(bridge)
                self.assertIs(caught, error); self.assertEqual(report['streamError'], str(error))
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['episodeFailure']['transportOperation'], origin.transport_origin(error))

    def test_foreground_prediction_and_stdout_errors_stay_unmarked(self):
        for phase in ('prediction','stdout','finish_action'):
            with self.subTest(phase=phase):
                error = OSError('synthetic ' + phase); bridge = ScriptedBridge([bytes(range(12))])
                request = bridge.request
                def frame_source(command, **kwargs):
                    metadata, pixels = request(command, **kwargs)
                    if command == 'frame': metadata.update(sourceWidth=2,sourceHeight=2)
                    return metadata,pixels
                bridge.request = frame_source; policy = FakePolicy()
                if phase == 'prediction': policy.predict = fail(error)
                if phase == 'finish_action':
                    policy.execution_feedback = True; policy.finish_action = fail(error)
                _, caught, report = self.episode(bridge, policy,
                    printing_error=error if phase == 'stdout' else None)
                self.assertIs(caught, error); self.assertFalse(origin.is_transport_failure(error))
                self.assertEqual(report['error'], str(error))

    def test_nontransport_stop_failure_vetoes_background_pipe_retry(self):
        error = disconnected(); bridge = ScriptedBridge([bytes(range(12))], before_frame=fail(error))
        _, caught, report = self.episode(bridge, stop_error=OSError('stop receipt callback'))
        self.assertIs(caught,error); self.assertFalse(origin.is_transport_failure(error))
        self.assertEqual(report['episodeFailure']['transportOperation'], 'eof')

    def test_normal_duration_stop_errors_are_terminal_after_report_publication(self):
        for error in (OSError('stop callback file'), ValueError('stop validation'), OSError()):
            with self.subTest(error=type(error).__name__):
                bridge = ScriptedBridge([bytes(range(12))])
                result,caught,report = self.episode(bridge,stop_error=error)
                self.assertIsNone(result); self.assertIs(caught,error)
                self.assertGreater(report['captureQuality']['usableFrames'],0)
                self.assertEqual(report['endReason'],'durationElapsed')
                self.assertEqual(report['status'],'failed'); self.assertTrue(report['error'])
                self.assertEqual(report['stopError'],str(error))
                self.assertFalse(origin.is_transport_failure(error))

    def test_user_stop_callback_failure_is_terminal(self):
        import threading
        seen = threading.Event(); error = OSError('user stop callback')
        bridge = ScriptedBridge([bytes(range(12))],before_frame=lambda number: seen.set())
        def snapshot():
            self.assertTrue(seen.wait(.5)); return 'stop',None
        control = SimpleNamespace(run_id='synthetic',begin_goal=lambda:None,snapshot=snapshot,
            goal_state=lambda:dict(goalError=None),publish=lambda **fields:None,
            goal_identity=lambda:dict(policyGoalVersion=0,appliedGoalRequestId=None,goalIntent='unspecified'))
        result,caught,report = self.episode(bridge,stop_error=error,control=control)
        self.assertIsNone(result); self.assertIs(caught,error)
        self.assertEqual(report['endReason'],'userStop'); self.assertEqual(report['status'],'failed')
        self.assertFalse(origin.is_transport_failure(error))

    def test_stop_receipt_processing_failure_retains_report_and_closes_recorder(self):
        from test_stream_client import CapturingRecorder
        for error in (OSError('receipt sidecar write'),ValueError('receipt validation')):
            with self.subTest(error=type(error).__name__):
                class ReceiptFailure(CapturingRecorder):
                    """Fail only in collect_receipts after the stop reply actually returned."""
                    closed = False
                    def event(self,event):
                        if event.get('requestId') == 'synthetic-stop': raise error
                        return super().event(event)
                    def close(self):
                        self.closed = True; return super().close()
                recorder = ReceiptFailure(); bridge = ScriptedBridge([bytes(range(12))])
                result,caught,report = self.episode(bridge,recorder=recorder)
                self.assertIsNone(result); self.assertIs(caught,error); self.assertTrue(recorder.closed)
                self.assertEqual(report['status'],'failed'); self.assertEqual(report['endReason'],'durationElapsed')
                self.assertEqual(report['stopError'],str(error)); self.assertFalse(origin.is_transport_failure(error))
                self.assertEqual(report['stop']['receipts'][0]['requestId'],'synthetic-stop')
                self.assertEqual(report['receipts'][-1]['requestId'],'synthetic-stop')

    def test_stop_only_pipe_failures_never_restart_an_intended_end(self):
        write_error = OSError(22,'Invalid argument')
        with self.assertRaises(OSError): client.Bridge._pipe_io('write',fail(write_error))
        for error in (disconnected(),write_error):
            with self.subTest(error=type(error).__name__):
                bridge = ScriptedBridge([bytes(range(12))])
                result,caught,report = self.episode(bridge,stop_error=error)
                self.assertIsNone(result); self.assertIs(caught,error)
                self.assertIsNotNone(origin.transport_origin(error)); self.assertFalse(origin.is_transport_failure(error))
                self.assertEqual(report['endReason'],'durationElapsed'); self.assertEqual(report['status'],'failed')

    def test_pipe_eof_and_pipe_stop_error_with_complete_recording_remain_retryable(self):
        from test_stream_client import CapturingRecorder
        class CompleteRecording(CapturingRecorder):
            """Model the retained complete recording from the successful continuity trial."""
            def close(self):
                return dict(complete=True,closed=True,dropped=0,error=None)
        error = disconnected(); stop_error = OSError(22,'Invalid argument')
        with self.assertRaises(OSError) as result:
            client.Bridge._pipe_io('write',fail(stop_error))
        self.assertIs(result.exception,stop_error)
        bridge = ScriptedBridge([bytes(range(12))],before_frame=fail(error))
        _,caught,report = self.episode(bridge,stop_error=stop_error,recorder=CompleteRecording())
        self.assertIs(caught,error); self.assertTrue(origin.is_transport_failure(error))
        self.assertEqual(report['stopError'],str(stop_error))
        self.assertTrue(report['recording']['complete']); self.assertTrue(report['recording']['closed'])
        self.assertEqual(report['status'],'failed')

    def test_unretired_reader_vetoes_retry_and_does_not_send_stop(self):
        class Unretired:
            """Expose the owned reader's timeout state without leaving an actual thread."""
            def __init__(self, target, **kwargs): self.target = target
            def start(self): self.target()
            def join(self, timeout): pass
            def is_alive(self): return True
        error = disconnected(); bridge = ScriptedBridge([bytes(range(12))], before_frame=fail(error))
        _, caught, report = self.episode(bridge, producer_type=Unretired)
        self.assertIs(caught,error); self.assertFalse(origin.is_transport_failure(error))
        self.assertNotIn('stop',bridge.commands)
        self.assertEqual(report['streamError'],'Frame reader did not stop after disconnection')

    def test_recording_failure_discovered_during_close_vetoes_pipe_retry(self):
        from test_stream_client import CapturingRecorder
        class LateFailure(CapturingRecorder):
            """The recorder can fail only while its final retained data are drained."""
            def close(self):
                self.error = 'synthetic late recording failure'
                return dict(error=self.error, complete=False)
        error = disconnected(); bridge = ScriptedBridge([bytes(range(12))], before_frame=fail(error))
        _, caught, report = self.episode(bridge, recorder=LateFailure())
        self.assertIs(caught,error); self.assertFalse(origin.is_transport_failure(error))
        self.assertEqual(report['recording']['error'],'synthetic late recording failure')

    def test_concurrent_frame_callback_failure_vetoes_foreground_pipe_retry(self):
        import threading
        entered = threading.Event(); observed = threading.Event()
        secondary = OSError('frame callback failed'); primary = disconnected()
        def before_frame(number):
            if number >= 2:
                self.assertTrue(entered.wait(.5)); observed.set(); raise secondary
        bridge = ScriptedBridge([bytes(range(12))], before_frame=before_frame)
        request = bridge.request
        def frame_source(command, **kwargs):
            metadata,pixels = request(command,**kwargs)
            if command == 'frame': metadata.update(sourceWidth=2,sourceHeight=2)
            return metadata,pixels
        bridge.request = frame_source; policy = FakePolicy()
        def predict(*args,**kwargs):
            entered.set(); self.assertTrue(observed.wait(.5)); raise primary
        policy.predict = predict
        _, caught, report = self.episode(bridge,policy)
        self.assertIs(caught,primary); self.assertFalse(origin.is_transport_failure(primary))
        self.assertEqual(report['streamError'],str(secondary))


if __name__ == '__main__':
    unittest.main()
