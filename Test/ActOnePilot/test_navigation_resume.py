import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('route_command', Path(__file__).resolve().parents[2] / 'tools/quest-pilot/act-one-command.py')
command = importlib.util.module_from_spec(spec)
spec.loader.exec_module(command)


class NavigationResumeTests(unittest.TestCase):
    def setUp(self):
        self.route = {'objective': 'Go to the exam point', 'waypoints': [
            {'map': 'Teyvat', 'x': -1365, 'y': 1635},
            {'map': 'Teyvat', 'x': -1330, 'y': 1625},
            {'map': 'Teyvat', 'x': -1280, 'y': 1640}]}
        self.progress = {'session': 's', 'requestId': 'r', 'routeHash': command.navigation_route_hash(self.route), 'startIndex': 0}
        self.request = {'id': 'r', **self.route}
        self.receipt = {'session': 's', 'id': 'r', 'mission': 'navigation', 'status': 'failed', 'details': {'result': {
            'reason': 'Navigation deadline reached', 'nextWaypointIndex': 2, 'pauseVerified': True,
            'pauseProof': {'verified': True, 'session': 's', 'kind': 'inventory'}}}}

    def run_resume(self, **patch):
        values = dict(route=self.route, progress=self.progress, receipt=self.receipt, previous_request=self.request, session='s')
        values.update(patch)
        return command.resume_navigation_route(**values)

    def test_recorded_deadline_cursor_skips_completed_road_segments(self):
        self.assertEqual(self.run_resume(), (self.route['waypoints'][2:], 2))

    def test_multiple_deadlines_accumulate_offset(self):
        progress = {**self.progress, 'startIndex': 1}
        receipt = copy.deepcopy(self.receipt)
        receipt['details']['result']['nextWaypointIndex'] = 1
        self.assertEqual(self.run_resume(progress=progress, receipt=receipt,
                         previous_request={**self.request, 'waypoints': self.route['waypoints'][1:]}), (self.route['waypoints'][2:], 2))

    def test_changed_route_session_or_intervening_request_rejected(self):
        for patch in [dict(route={**self.route, 'objective': 'Other'}), dict(session='x'),
                      dict(previous_request={**self.request, 'id': 'other'}),
                      dict(progress={**self.progress, 'routeHash': 'changed'})]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.run_resume(**patch)

    def test_unknown_or_non_deadline_outcome_never_retried(self):
        for status in ['running', 'started', 'completed']:
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.run_resume(receipt={**self.receipt, 'status': status})
        for reason in ['Map coordinates stalled', 'Health dropped more than 10%', 'Guild approach requires safe grounded travel']:
            receipt = copy.deepcopy(self.receipt)
            receipt['details']['result']['reason'] = reason
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                self.run_resume(receipt=receipt)

    def test_pause_and_cursor_corruption_rejected(self):
        for cursor in [-1, 3, True, None, 1.5]:
            receipt = copy.deepcopy(self.receipt)
            receipt['details']['result']['nextWaypointIndex'] = cursor
            with self.subTest(cursor=cursor), self.assertRaises(ValueError):
                self.run_resume(receipt=receipt)
        receipt = copy.deepcopy(self.receipt)
        receipt['details']['result']['pauseProof']['verified'] = False
        with self.assertRaises(ValueError):
            self.run_resume(receipt=receipt)

    def test_provenance_edit_does_not_change_route_but_points_do(self):
        self.assertEqual(command.navigation_route_hash(self.route), command.navigation_route_hash({**self.route, 'provenance': 'notes'}))
        changed = copy.deepcopy(self.route)
        changed['waypoints'][0]['x'] += 1
        with self.assertRaises(ValueError):
            self.run_resume(route=changed)


if __name__ == '__main__':
    unittest.main()
