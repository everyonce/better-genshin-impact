import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2] / 'tools' / 'quest-pilot' / 'act-one-route.py'
spec = importlib.util.spec_from_file_location('act_one_route', SCRIPT)
route_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route_tool)


class FakeClock:
    def __init__(self, root, on_poll=None):
        self.root = root
        self.value = 0.0
        self.on_poll = on_poll
        self.handled = set()

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds
        if self.on_poll is None:
            return
        request = json.loads((self.root / 'request.json').read_text(encoding='utf-8'))
        if request['id'] in self.handled:
            return
        self.handled.add(request['id'])
        self.on_poll(request)


class ActOneRouteResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.session = 'session-5-test'
        self.waypoints = [
            {'map': 'Teyvat', 'x': -1200, 'y': 2200},
            {'map': 'Teyvat', 'x': -1180, 'y': 2240},
            {'map': 'Teyvat', 'x': -1160, 'y': 2280},
        ]
        self.route = {'objective': 'Go to Mondstadt', 'waypoints': self.waypoints}
        self.write_observation(1)

    def tearDown(self):
        self.temp.cleanup()

    def write_observation(self, frame):
        (self.root / 'observation.json').write_text(json.dumps({'session': self.session, 'frameId': frame}), encoding='utf-8')

    def write_receipt(self, request, status, result, frame):
        self.write_observation(frame)
        receipt = {'session': self.session, 'id': request['id'], 'mission': 'navigation', 'status': status,
                   'frameId': frame, 'details': {'result': result}}
        (self.root / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')

    def test_pending_existing_request_is_refused_before_any_write(self):
        previous = {'id': 'already-running', 'session': self.session, 'mission': 'navigation'}
        (self.root / 'request.json').write_text(json.dumps(previous), encoding='utf-8')
        (self.root / 'receipt.json').write_text(json.dumps({'id': 'already-running', 'session': self.session,
                                                             'mission': 'navigation', 'status': 'started'}), encoding='utf-8')
        with mock.patch.object(route_tool, 'atomic', wraps=route_tool.atomic) as write_request:
            with self.assertRaises(route_tool.RouteError):
                route_tool.run_route(self.root, self.route, self.session, emit=lambda _: None)
        self.assertEqual(write_request.call_count, 0)
        self.assertEqual(json.loads((self.root / 'request.json').read_text()), previous)

    def test_matching_terminal_prior_request_allows_new_route(self):
        previous = {'id': 'already-finished', 'session': self.session, 'mission': 'navigation'}
        (self.root / 'request.json').write_text(json.dumps(previous), encoding='utf-8')
        (self.root / 'receipt.json').write_text(json.dumps({'id': 'already-finished', 'session': self.session,
                                                             'mission': 'navigation', 'status': 'completed'}), encoding='utf-8')

        def on_poll(request):
            self.write_receipt(request, 'completed', {'status': 'arrived',
                                                       'nextWaypointIndex': len(request['waypoints'])}, 2)

        clock = FakeClock(self.root, on_poll)
        with mock.patch.object(route_tool, 'atomic', wraps=route_tool.atomic) as write_request:
            result = route_tool.run_route(self.root, self.route, self.session, deadline_ms=1000,
                                          monotonic=clock.monotonic, sleep=clock.sleep, emit=lambda _: None)
        self.assertEqual(result, 'arrived')
        self.assertEqual(write_request.call_count, 1)
    def test_deadline_checkpoint_resumes_exact_remaining_sequence_with_fresh_id_and_frame(self):
        seen = []

        def on_poll(request):
            seen.append(request)
            if len(seen) == 1:
                self.write_receipt(request, 'failed', {'status': 'stopped', 'reason': 'Navigation deadline reached',
                                                       'nextWaypointIndex': 1}, 2)
            else:
                self.write_receipt(request, 'completed', {'status': 'arrived',
                                                          'nextWaypointIndex': len(request['waypoints'])}, 3)

        clock = FakeClock(self.root, on_poll)
        writes = []
        atomic = route_tool.atomic

        def count_atomic(path, value):
            writes.append(value)
            atomic(path, value)

        output = []
        with mock.patch.object(route_tool, 'atomic', side_effect=count_atomic):
            result = route_tool.run_route(self.root, self.route, self.session, deadline_ms=1000,
                                          monotonic=clock.monotonic, sleep=clock.sleep, emit=output.append)
        self.assertEqual(result, 'arrived')
        self.assertEqual(len(seen), 2)
        self.assertNotEqual(seen[0]['id'], seen[1]['id'])
        self.assertEqual(seen[0]['expectedFrameId'], 1)
        self.assertEqual(seen[1]['expectedFrameId'], 2)
        self.assertEqual(seen[1]['waypoints'], self.waypoints[1:])
        self.assertEqual(len(writes), 2)

    def test_stale_terminal_observation_stops_without_submitting_resume(self):
        def on_poll(request):
            receipt = {'session': self.session, 'id': request['id'], 'mission': 'navigation', 'status': 'failed',
                       'frameId': 2, 'details': {'result': {'status': 'stopped', 'reason': 'Navigation deadline reached',
                                                            'nextWaypointIndex': 1}}}
            (self.root / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
            self.write_observation(1)

        clock = FakeClock(self.root, on_poll)
        output = []
        with mock.patch.object(route_tool, 'atomic', wraps=route_tool.atomic) as write_request:
            with self.assertRaises(route_tool.RouteError):
                route_tool.run_route(self.root, self.route, self.session, deadline_ms=1000,
                                     monotonic=clock.monotonic, sleep=clock.sleep, emit=output.append)
        self.assertEqual(write_request.call_count, 1)

    def test_client_timeout_reports_pending_and_never_replays(self):
        clock = FakeClock(self.root)
        output = []
        with mock.patch.object(route_tool, 'atomic', wraps=route_tool.atomic) as write_request:
            result = route_tool.run_route(self.root, self.route, self.session, deadline_ms=1000,
                                          monotonic=clock.monotonic, sleep=clock.sleep, emit=output.append)
        self.assertEqual(result, 'pending')
        self.assertEqual(write_request.call_count, 1)
        self.assertTrue(any('pending' in line and 'Do not replay' in line for line in output))


    def test_non_deadline_stop_is_terminal_and_never_resumes(self):
        def on_poll(request):
            self.write_receipt(request, 'failed', {'status': 'stopped', 'reason': 'Map coordinates stalled',
                                                   'nextWaypointIndex': 1}, 2)

        clock = FakeClock(self.root, on_poll)
        output = []
        with mock.patch.object(route_tool, 'atomic', wraps=route_tool.atomic) as write_request:
            result = route_tool.run_route(self.root, self.route, self.session, deadline_ms=1000,
                                          monotonic=clock.monotonic, sleep=clock.sleep, emit=output.append)
        self.assertEqual(result, 'stopped')
        self.assertEqual(write_request.call_count, 1)
if __name__ == '__main__':
    unittest.main()

