"""Route selection and heading regressions using synthetic frames only."""
import copy
from contextlib import redirect_stderr
import io
import unittest

from hybrid_navigation import HybridNavigation
from hybrid_routes import COURTYARD_ROUTE, LAMPPOST_ROUTE, camera_correction, route_heading, route_points
from stream_client import parse_arguments
from test_hybrid_navigation import capability, frame, proposal


class HybridRouteTests(unittest.TestCase):
    def lamp_frame(self, index, point, yaw):
        """Supply the original two native anchors alongside the surveyed route geometry."""
        item = frame(index, 100 * index, point, yaw=yaw)
        pose = item['navigationPose']
        start, end = route_points(COURTYARD_ROUTE)
        pose.update(headingToStartDegrees=int(route_heading(pose, start)),
                    headingToEndDegrees=int(route_heading(pose, end)))
        return item

    def test_surveyed_endpoints_choose_opposite_targets_and_keep_native_pose(self):
        start, end = route_points(LAMPPOST_ROUTE)
        for point, target, name in ((start, end, 'end'), (end, start, 'start')):
            with self.subTest(target=name):
                nav = HybridNavigation(capability(), LAMPPOST_ROUTE)
                facing = route_heading({'x': point[0], 'y': point[1]}, target)
                for index in range(1, 4):
                    item = self.lamp_frame(index, point, facing)
                    nav.prepare(item)
                original = copy.deepcopy(item['navigationPose'])
                selected = nav.choose(item, proposal(['W']))
                self.assertEqual((selected['owner'], selected['target']), ('open-p2p', name))
                self.assertEqual(selected['pose'], original)
                self.assertEqual(item['navigationPose'], original)
                self.assertEqual(nav.snapshot()['routeId'], LAMPPOST_ROUTE)
                self.assertEqual(nav.drain_events()[0]['routeId'], LAMPPOST_ROUTE)
                item = self.lamp_frame(4, point, (facing + 170) % 360)
                nav.prepare(item)
                self.assertEqual(nav.choose(item, proposal(['W']))['step'],
                                 dict(keys=[], mouseDx=-250, mouseDy=0, durationMs=100))

    def test_alternate_route_rejects_changed_native_bearings_or_outside_corridor(self):
        start, _ = route_points(LAMPPOST_ROUTE)
        nav = HybridNavigation(capability(), LAMPPOST_ROUTE)
        item = self.lamp_frame(1, start, 160)
        item['navigationPose']['headingToEndDegrees'] += 20
        with self.assertRaisesRegex(RuntimeError, 'native_bearing_mismatch'):
            nav.prepare(item)
        nav = HybridNavigation(capability(), LAMPPOST_ROUTE)
        with self.assertRaisesRegex(RuntimeError, 'outside_fixed_lamppost_corridor'):
            nav.prepare(self.lamp_frame(1, (start[0], start[1] + 5), 160))

    def test_angles_wrap_and_match_retained_native_sample(self):
        sample = dict(x=-875.32421875, y=2274.7060546875)
        for goal, native in zip(route_points(COURTYARD_ROUTE), (221, 151)):
            self.assertLess(abs(route_heading(sample, goal) - native), 1.1)
        self.assertEqual(camera_correction(358, 6), 16)
        self.assertEqual(camera_correction(6, 358), -16)

    def test_sidestep_remains_on_inward_side_after_retry_in_both_directions(self):
        nav = HybridNavigation(capability(), LAMPPOST_ROUTE)
        for attempt in (1, 2):
            self.assertEqual(nav.recovery_side('end', attempt), 'A')
            self.assertEqual(nav.recovery_side('start', attempt), 'D')

    def test_route_requires_hybrid_mode_and_a_registered_id(self):
        base = ['--resident', '--rdp-session-id', '3', '--model', 'open-p2p', '--source', 'test',
                '--checkpoint', 'test', '--p2p-fast-start', '--cuda-graph', '--enable-input',
                '--goal-intent', 'ground-navigation', '--output', 'unused.json']
        args = parse_arguments(base + ['--hybrid-navigation', '--hybrid-route', LAMPPOST_ROUTE])
        self.assertEqual(args.hybrid_route, LAMPPOST_ROUTE)
        for options in (['--hybrid-route', LAMPPOST_ROUTE], ['--hybrid-navigation', '--hybrid-route', 'custom']):
            with self.subTest(options=options), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_arguments(base + options)
