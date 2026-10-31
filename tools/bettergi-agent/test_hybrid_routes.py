"""Route selection and heading regressions using synthetic frames only."""
import copy
from contextlib import redirect_stderr
import io
import unittest
from unittest.mock import Mock,patch

from hybrid_navigation import HybridNavigation
from hybrid_routes import (COURTYARD_ROUTE, LAMPPOST_ROUTE, PATROL_STATIONS, STREET_PATROL_ROUTE, SURVEY_ROUTES,
                           camera_correction, route_heading, route_points)
from stream_client import parse_arguments
from test_hybrid_navigation import capability, frame, proposal


class HybridRouteTests(unittest.TestCase):
    def test_observation_mode_refuses_input_and_an_input_enabled_native_bridge(self):
        """A full-loop qualification cannot accidentally inherit an input-capable native lease."""
        import stream_client as client
        base=['--resident','--rdp-session-id','3','--model','open-p2p','--source','unused',
              '--checkpoint','unused','--p2p-fast-start','--cuda-graph','--hybrid-navigation','--hybrid-observe',
              '--goal-intent','ground-navigation','--output','unused.json']
        args=parse_arguments(base)
        self.assertTrue(client.validate_hybrid_observe_options(args))
        bridge=Mock(hello={'inputEnabled':True})
        with patch.object(client,'Bridge',return_value=bridge),self.assertRaisesRegex(ValueError,'native bridge'):
            client.run_episode(args)
        bridge.handle.close.assert_called_once()
        for extra in (['--enable-input'],['--model','observe']):
            with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):parse_arguments(base+extra)

    def test_unsurveyed_extension_stops_before_retreat_or_sidestep_for_both_obstacle_triggers(self):
        for route in SURVEY_ROUTES:
            for trigger in ('stationaryForward','climbDrop'):
                with self.subTest(route=route,trigger=trigger):
                    nav=HybridNavigation(capability(),route)
                    with self.assertRaisesRegex(RuntimeError,'survey_obstacle_requires_inspection'):
                        nav._begin_recovery(trigger)
                    self.assertEqual(nav.phase,'failed')
                    self.assertEqual(nav.recovery_attempts,0)

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

    def patrol_frame(self, index, point, epoch=1):
        """Use the live gate shape with a known capture and incrementing release generation."""
        item = self.lamp_frame(index, point, 90)
        item['frameWorldReadiness'] = dict(epoch=epoch, ready=True, sourceFrame=dict(captureEpoch='capture-a'))
        return item

    def test_patrol_can_begin_only_at_the_stair_front(self):
        nav = HybridNavigation(capability(), STREET_PATROL_ROUTE)
        for other in ('sidewalk-junction', 'west-lamp'):
            with self.subTest(other=other), self.assertRaises(RuntimeError):
                HybridNavigation(capability(), STREET_PATROL_ROUTE).prepare(self.patrol_frame(1, PATROL_STATIONS[other]))
        for i in range(1, 4):
            nav.prepare(self.patrol_frame(i, PATROL_STATIONS['stair-front']))
        start = nav.drain_events()[0]
        self.assertEqual((start['station'], start['target']), ('stair-front', 'sidewalk-junction'))
        self.assertEqual([s['frameId'] for s in start['samples']], [1, 2, 3])

    def test_two_circuits_verify_eight_ordered_station_releases_and_active_segment_steering(self):
        nav = HybridNavigation(capability(), STREET_PATROL_ROUTE)
        a, b, c = 'stair-front', 'sidewalk-junction', 'west-lamp'
        path = (a, b, c, b, a, b, c, b, a)
        index, epoch = 0, 1
        for _ in range(3):
            index += 1
            nav.prepare(self.patrol_frame(index, PATROL_STATIONS[a]))
        nav.drain_events()
        for leg, (origin, dest) in enumerate(zip(path, path[1:])):
            index += 1
            start = self.patrol_frame(index, PATROL_STATIONS[origin], epoch)
            self.assertIsNone(nav.prepare(start))  # Staying at the previous station never completes this leg.
            choice = nav.choose(start, proposal(['W']))
            self.assertEqual((choice['target'], choice['segmentIndex'], choice['circuit']), (dest, leg%4, leg//4+1))
            self.assertEqual((choice['fromStation'], choice['toStation']), (origin, dest))
            self.assertEqual((nav.start, nav.end), (PATROL_STATIONS[origin], PATROL_STATIONS[dest]))
            index += 1
            self.assertEqual(nav.prepare(self.patrol_frame(index, PATROL_STATIONS[dest], epoch)), 'releaseRequired')
            epoch += 1
            nav.released(dict(type='released', serverNowMs=index*100+5, worldReadiness=dict(epoch=epoch,
                ready=False, reason='client_release', sourceFrame=dict(captureEpoch='capture-a'))))
            for _ in range(3):
                index += 1
                state = nav.prepare(self.patrol_frame(index, PATROL_STATIONS[dest], epoch))
            self.assertEqual(state, 'endpointVerified')
            events = nav.drain_events()
            self.assertEqual((events[0]['endpoint'], events[0]['station'], events[0]['releaseEpoch']), (dest, dest, epoch))
            self.assertEqual(events[0]['arrivalFrameId'], index-3)
            self.assertEqual(len(events), 2 if (leg+1)%4 == 0 else 1)
            if len(events) == 2:
                self.assertEqual((events[1]['type'], events[1]['completedCircuits'], events[1]['frameId']),
                                 ('hybridCircuitVerified', (leg+1)//4, index))
        self.assertEqual((nav.legs, nav.snapshot()['completedCircuits']), (8, 2))

    def test_patrol_rejects_other_segments_and_unrelated_releases(self):
        for failure in ('wrongSegment', 'unrelatedAck', 'changedAfterRelease'):
            with self.subTest(failure=failure):
                nav = HybridNavigation(capability(), STREET_PATROL_ROUTE)
                for i in range(1, 4):
                    nav.prepare(self.patrol_frame(i, PATROL_STATIONS['stair-front']))
                if failure == 'wrongSegment':
                    with self.assertRaisesRegex(RuntimeError, 'corridor'):
                        nav.prepare(self.patrol_frame(4, PATROL_STATIONS['west-lamp']))
                    continue
                nav.prepare(self.patrol_frame(4, PATROL_STATIONS['sidewalk-junction']))
                ack = dict(type='released', serverNowMs=405, worldReadiness=dict(epoch=2,
                           ready=False, reason='client_release', sourceFrame=dict(captureEpoch='capture-a')))
                if failure == 'unrelatedAck':
                    ack['worldReadiness']['epoch'] = 5
                    with self.assertRaisesRegex(RuntimeError, 'release_unbound'):
                        nav.released(ack)
                else:
                    nav.released(ack)
                    with self.assertRaisesRegex(RuntimeError, 'readiness_changed'):
                        nav.prepare(self.patrol_frame(5, PATROL_STATIONS['sidewalk-junction'], epoch=3))

    def test_route_requires_hybrid_mode_and_a_registered_id(self):
        base = ['--resident', '--rdp-session-id', '3', '--model', 'open-p2p', '--source', 'test',
                '--checkpoint', 'test', '--p2p-fast-start', '--cuda-graph', '--enable-input',
                '--goal-intent', 'ground-navigation', '--output', 'unused.json']
        args = parse_arguments(base + ['--hybrid-navigation', '--hybrid-route', LAMPPOST_ROUTE])
        self.assertEqual(args.hybrid_route, LAMPPOST_ROUTE)
        for count in (4, 8):
            args = parse_arguments(base + ['--hybrid-navigation', '--hybrid-route', STREET_PATROL_ROUTE,
                                          '--hybrid-legs', str(count)])
            self.assertEqual((args.hybrid_route, args.hybrid_legs), (STREET_PATROL_ROUTE, count))
        for options in (['--hybrid-route', LAMPPOST_ROUTE], ['--hybrid-navigation', '--hybrid-route', 'custom']):
            with self.subTest(options=options), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_arguments(base + options)
