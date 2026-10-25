"""CPU-only causal-arrival and transport-preservation checks for optional context."""

import copy
import threading
import unittest

from execution_bridge import ExecutionContextBridge, decision_context


class Clock:
    """Supply strictly increasing test knowledge timestamps."""
    def __init__(self):
        self.now = 0

    def __call__(self):
        self.now += 1_000_000
        return self.now


def receipt(request='a', keys=None, status='completed'):
    """A software receipt deliberately makes no game-effect assertion."""
    return {'requestId': request, 'modelId': 'gamescaling', 'frameId': 1,
            'status': status, 'reason': 'horizon_complete', 'acceptedAtMs': 10,
            'endedAtMs': 65, 'appliedSteps': [
                {'index': 0, 'startedAtMs': 15, 'keys': keys or ['LBUTTON'],
                 'mouseDx': 0, 'mouseDy': 0}]}


def action(request='a'):
    """A single ordinary action request for the existing bridge."""
    return {'requestId': request, 'modelId': 'gamescaling', 'frameId': 1,
            'observedAtMs': 0, 'expiresAtMs': 100,
            'steps': [{'keys': ['LBUTTON'], 'mouseDx': 0, 'mouseDy': 0, 'durationMs': 50}]}


class StubBridge:
    """Return scripted packets without importing Windows transport or a model."""
    def __init__(self, responder=None):
        self.hello = {'sessionId': 'lease', 'ownerEpoch': 'owner'}
        self.handle = object()
        self.calls = []
        self.responder = responder

    def request(self, command, **kwargs):
        self.calls.append((command, copy.deepcopy(kwargs)))
        if self.responder:
            return self.responder(command, kwargs)
        if command == 'frame':
            return {'type': 'frame', 'frameId': 1, 'capturedAtMs': 0,
                    'serverNowMs': 5, 'receipts': []}, b'rgb'
        if command == 'action':
            return {'type': 'accepted', 'requestId': kwargs['requestId'],
                    'receivedAtMs': 9, 'acceptedAtMs': 10}, b''
        return {'type': 'status', 'serverNowMs': 70, 'receipts': [receipt()]}, b''


class ExecutionBridgeTests(unittest.TestCase):
    """Verify the wrapper adds evidence without changing input authority."""
    def setUp(self):
        self.raw = StubBridge()
        self.bridge = ExecutionContextBridge(self.raw, clock=Clock())
        self.frame, _ = self.bridge.request('frame')
        self.origin = {'controlEpoch': 1, 'policyGoalVersion': 2,
                       'readinessEpoch': 3, 'sourceEpoch': 'capture-a'}

    def snapshot(self, origin=None):
        """Freeze current evidence on the previously received image."""
        return self.bridge.snapshot(self.frame, decision_context=origin or self.origin)

    def test_preserves_request_bytes_payload_and_original_handle(self):
        self.snapshot()
        sent = action()
        reply, pixels = self.bridge.request('action', **sent)
        self.assertEqual(self.raw.calls[-1], ('action', sent))
        self.assertEqual(reply['type'], 'accepted')
        self.assertEqual(pixels, b'')
        self.assertIs(self.bridge.handle, self.raw.handle)
        self.assertIs(self.bridge.hello, self.raw.hello)

    def test_proposal_admission_and_receipt_are_distinct(self):
        self.snapshot()
        self.bridge.request('action', **action())
        self.bridge.request('status')
        data = self.snapshot().to_dict()
        self.assertEqual([e['kind'] for e in data['events']], ['proposal', 'admission', 'receipt'])
        self.assertEqual(data['semantics']['ongoingHold'], 'unknown')
        self.assertEqual(data['semantics']['observedGameEffect'], 'unknown')
        times = [e['observedClientNs'] for e in data['events']]
        self.assertEqual(times, sorted(times))

    def test_receipt_arriving_during_inference_cannot_mutate_frozen_context(self):
        self.snapshot()
        self.bridge.request('action', **action())
        before = self.snapshot()
        frozen = before.to_dict()
        self.bridge.request('status')
        self.assertEqual(before.to_dict(), frozen)
        self.assertFalse(any(e['kind'] == 'receipt' for e in frozen['events']))
        self.assertTrue(any(e['kind'] == 'receipt' for e in self.snapshot().to_dict()['events']))

    def test_old_request_origin_survives_goal_change(self):
        self.snapshot()
        self.bridge.request('action', **action())
        changed = dict(self.origin, controlEpoch=4, policyGoalVersion=5)
        self.snapshot(changed)
        self.bridge.request('status')
        data = self.snapshot(changed).to_dict()
        actual = next(e for e in data['events'] if e['kind'] == 'receipt')
        self.assertEqual(actual['originContext'], self.origin)
        self.assertEqual(data['decisionContext'], changed)

    def test_unknown_transport_outcome_is_not_an_admission(self):
        self.snapshot()
        def fail(command, kwargs):
            raise EOFError('disconnected')
        self.raw.responder = fail
        with self.assertRaises(EOFError):
            self.bridge.request('action', **action())
        events = self.snapshot().to_dict()['events']
        self.assertEqual([e['kind'] for e in events], ['proposal', 'unknown'])
        self.assertEqual(events[-1]['payload']['reason'], 'transport_failed_outcome_unknown')

    def test_mismatched_acknowledgement_stays_unknown(self):
        self.snapshot()
        self.raw.responder = lambda command, kwargs: ({'type': 'accepted', 'requestId': 'other'}, b'')
        self.bridge.request('action', **action())
        events = self.snapshot().to_dict()['events']
        self.assertEqual(events[-1]['payload']['state'], 'unknown')

    def test_not_submitted_proposal_cannot_become_executed(self):
        self.snapshot()
        self.bridge.not_submitted(action(), model_id='gamescaling', frame_id=1, reason='observationTooOld')
        events = self.snapshot().to_dict()['events']
        self.assertEqual([e['kind'] for e in events], ['proposal', 'admission'])
        self.assertEqual(events[-1]['payload']['state'], 'not_submitted')
        self.assertNotIn('action', [command for command, _ in self.raw.calls])

    def test_release_return_remains_uncertain(self):
        self.raw.responder = lambda command, kwargs: ({'type': 'released', 'serverNowMs': 90, 'receipts': []}, b'')
        self.bridge.request('release')
        data = self.snapshot().to_dict()
        self.assertEqual(data['semantics']['releaseSuccess'], 'unknown')
        self.assertTrue(any('release' in e['payload'].get('reason', '') for e in data['events']))

    def test_frame_projection_retains_capture_identity_without_clock_conversion(self):
        self.frame.update(sourceKind='host-acquisition-v1', sourceTimestampKind='unknown',
                          hostSnapshot={'captureEpoch': 'epoch', 'startedAtMs': 1, 'completedAtMs': 3},
                          frameWorldReadiness={'epoch': 7, 'ready': True}, hostAcquisitionAgeMs=4)
        data = self.snapshot().to_dict()
        self.assertEqual(data['frame']['hostSnapshot']['startedAtMs'], 1)
        self.assertEqual(data['frame']['serverNowMs'], 5)
        self.assertEqual(data['frame']['observedClientNs'], self.frame['executionObservedClientNs'])
        self.assertEqual(decision_context(self.frame, (2, 3, None, 'run')),
                         {'controlEpoch': 2, 'policyGoalVersion': 3, 'readinessEpoch': 7, 'sourceEpoch': 'epoch'})

    def test_concurrent_requests_keep_transport_and_knowledge_order(self):
        entered, release, second_started = threading.Event(), threading.Event(), threading.Event()
        def respond(command, kwargs):
            if command == 'action':
                entered.set()
                if not release.wait(2):
                    raise RuntimeError('test synchronization timed out')
                return {'type': 'accepted', 'requestId': kwargs['requestId']}, b''
            return {'type': 'status', 'receipts': [receipt()]}, b''
        self.raw.responder = respond
        failures = []
        def call(command, **kwargs):
            try:
                if command == 'status':
                    second_started.set()
                self.bridge.request(command, **kwargs)
            except Exception as error:
                failures.append(error)
        first = threading.Thread(target=call, args=('action',), kwargs=action())
        second = threading.Thread(target=call, args=('status',))
        first.start()
        self.assertTrue(entered.wait(1))
        second.start()
        self.assertTrue(second_started.wait(1))
        self.assertEqual([c for c, _ in self.raw.calls], ['frame', 'action'])
        release.set()
        first.join(2)
        second.join(2)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertFalse(failures)
        events = self.snapshot().to_dict()['events']
        self.assertEqual([e['kind'] for e in events], ['proposal', 'admission', 'receipt'])

    def test_snapshot_and_local_rejection_do_not_wait_for_blocked_pipe(self):
        entered, release, completed = threading.Event(), threading.Event(), threading.Event()
        failures, snapshots = [], []
        def respond(command, kwargs):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('test synchronization timed out')
            return {'type': 'status', 'receipts': [receipt()]}, b''
        self.raw.responder = respond
        def poll():
            try:
                self.bridge.request('status')
            except Exception as error:
                failures.append(error)
        def snapshot_without_io():
            try:
                self.bridge.not_submitted(action(), model_id='gamescaling', frame_id=1,
                                          reason='modelMissedDecisionBudget')
                snapshots.append(self.snapshot().to_dict())
            except Exception as error:
                failures.append(error)
            finally:
                completed.set()
        reader = threading.Thread(target=poll)
        observer = threading.Thread(target=snapshot_without_io)
        reader.start()
        self.assertTrue(entered.wait(1))
        observer.start()
        try:
            self.assertTrue(completed.wait(1), 'Evidence observation must not wait on pipe IO')
        finally:
            release.set()
            reader.join(2)
            observer.join(2)
        self.assertFalse(failures)
        self.assertFalse(any(e['kind'] == 'receipt' for e in snapshots[0]['events']))
        self.assertTrue(any(e['kind'] == 'receipt' for e in self.snapshot().to_dict()['events']))


if __name__ == '__main__':
    unittest.main()
