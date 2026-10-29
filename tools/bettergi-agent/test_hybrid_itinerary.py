"""Exercise destination-directed geometry and native progress without Windows input or a model."""
import unittest

from hybrid_navigation import HybridNavigation
from hybrid_routes import COURTYARD_ROUTE, PATROL_STATIONS, STREET_PATROL_ROUTE, itinerary_legs, route_heading, route_points
from test_hybrid_navigation import capability, frame, proposal


A, B, C = 'stair-front', 'sidewalk-junction', 'west-lamp'


def station_frame(index, station, epoch):
    """Return a distinct WGC/native pose at the named station with the original anchor bearings."""
    item = frame(index, index * 100, PATROL_STATIONS[station])
    pose = item['navigationPose']
    start, end = route_points(COURTYARD_ROUTE)
    pose.update(headingToStartDegrees=int(route_heading(pose, start)),
                headingToEndDegrees=int(route_heading(pose, end)))
    item['frameWorldReadiness'] = dict(epoch=epoch, ready=True, sourceFrameId=index, sourceFrame=item['sourceFrame'].copy())
    return item


def release(index, epoch):
    """Acknowledge release after the arrival frame on the same capture."""
    return dict(type='released', serverNowMs=index * 100 + 5, worldReadiness=dict(
        epoch=epoch, ready=False, reason='client_release', sourceFrame=dict(captureEpoch='capture-a')))


class ItineraryNavigationTests(unittest.TestCase):
    def at_first_photo(self, requests=(B, A)):
        """Reach the first physical endpoint and pin its original acknowledged release."""
        nav = HybridNavigation(capability(), STREET_PATROL_ROUTE, itinerary_start=A,
                               itinerary_destinations=requests, stationary_photo_retries=True)
        for index in range(1, 4):
            nav.prepare(station_frame(index, A, 1))
        nav.drain_events()
        nav.prepare(station_frame(4, B, 1))
        nav.released(release(4, 2))
        for index in (5, 6, 7):
            nav.prepare(station_frame(index, B, 2))
        return nav

    def test_photo_hold_only_at_a_requested_station_and_only_when_enabled(self):
        transit = self.at_first_photo((C,))
        self.assertEqual([e['type'] for e in transit.drain_events()], ['hybridEndpointVerified'])
        self.assertEqual((transit.phase, transit.target_name), ('walking', C))
        with self.assertRaises(RuntimeError):
            transit.retry_destination_photo()
        with self.assertRaises(ValueError):
            HybridNavigation(capability(), STREET_PATROL_ROUTE, stationary_photo_retries=True)
        for requests in ((B,), (B,A)):
            with self.subTest(requests=requests):
                nav = self.at_first_photo(requests)
                self.assertEqual(nav.phase, 'destinationPhotoDecision')
                nav.finish_destination_photo()
                self.assertEqual(nav.phase, 'walking' if len(requests) > 1 else 'complete')
                self.assertEqual(nav.leg_started, 700)

    def test_reobserve_three_distinct_new_frames_without_input_or_duplicate_arrival(self):
        nav = self.at_first_photo()
        self.assertEqual([e['type'] for e in nav.drain_events()], ['hybridEndpointVerified', 'hybridDestinationVerified'])
        self.assertEqual((nav.legs, nav.completed_destinations, nav.target_name), (1,1,B))
        nav.retry_destination_photo()
        with self.assertRaisesRegex(RuntimeError, 'verified active leg'):
            nav.choose(station_frame(8, B, 2), proposal(['W']))
        for i in (7,8,8,9):
            self.assertEqual(nav.prepare(station_frame(i, B, 2)), 'waitingForDestinationPhoto')
        self.assertEqual(nav.drain_events(), [])
        self.assertEqual(nav.prepare(station_frame(10, B, 2)), 'destinationPhotoRetry')
        marker, = nav.drain_events()
        self.assertEqual((marker['type'],marker['retryOrdinal'],marker['initialEndpointFrameId'],marker['arrivalFrameId'],
                          marker['releaseAtMs'],marker['releaseEpoch']), ('hybridDestinationPhotoRetry',1,7,4,405,2))
        self.assertEqual([s['frameId'] for s in marker['samples']], [8,9,10])
        self.assertEqual((marker['completedLegs'],marker['station'],marker['frameId'],marker['destinationOrdinal']),
                         (1,B,10,1))
        with self.assertRaisesRegex(RuntimeError, 'verified active leg'):
            nav.choose(station_frame(10, B, 2), proposal(['W']))
        nav.finish_destination_photo()
        self.assertEqual((nav.legs, nav.completed_destinations, nav.target_name, nav.leg_started), (1,1,A,700))
        self.assertEqual(nav.drain_events(), [])
        with self.assertRaisesRegex(RuntimeError, 'newer navigable frame'):
            nav.choose(station_frame(10, B, 2), proposal(['W']))
        item = station_frame(11, B, 2)
        self.assertIsNone(nav.prepare(item))
        self.assertEqual(nav.choose(item, proposal(['W']))['toStation'], A)

    def test_each_photo_retry_requires_three_more_samples_under_the_same_attempt_and_time_limits(self):
        nav = self.at_first_photo((B,))
        nav.drain_events()
        for attempt in (1,2,3):
            nav.retry_destination_photo()
            for i in range(5 + 3*attempt, 8 + 3*attempt):
                state = nav.prepare(station_frame(i, B, 2))
            self.assertEqual(state, 'destinationPhotoRetry')
            marker, = nav.drain_events()
            self.assertEqual((marker['retryOrdinal'],marker['completedLegs']), (attempt,1))
            self.assertEqual([s['frameId'] for s in marker['samples']], [i-2,i-1,i])
        with self.assertRaisesRegex(RuntimeError, 'attempts_exhausted'):
            nav.retry_destination_photo()
        self.assertEqual((nav.phase,nav.legs), ('failed',1))
        nav = self.at_first_photo()
        nav.retry_destination_photo()
        nav.prepare(station_frame(20, B, 2))
        nav.prepare(station_frame(21, B, 2))
        nav.prepare(station_frame(22, B, 2))  # Last possible retry, 1.5 s after original frame 7.
        nav.retry_destination_photo()
        with self.assertRaisesRegex(RuntimeError, 'destination_photo_deadline'):
            nav.prepare(station_frame(23, B, 2))

    def test_changed_release_source_pose_clock_or_motion_cannot_prove_a_photo_retry(self):
        for kind in ('gateEpoch','source','notReady','sourceIdentity','stamp','yaw','climb','confidence','interrupt'):
            with self.subTest(kind=kind):
                nav = self.at_first_photo()
                nav.drain_events()
                nav.retry_destination_photo()
                f = station_frame(8, B, 2)
                if kind == 'gateEpoch':
                    f['frameWorldReadiness']['epoch'] += 1
                elif kind == 'source':
                    f['sourceFrame']['captureEpoch'] = 'other'
                elif kind == 'notReady':
                    f['frameWorldReadiness']['ready'] = False
                elif kind == 'sourceIdentity':
                    f['frameWorldReadiness']['sourceFrameId'] -= 1
                elif kind == 'stamp':
                    f['sourceFrame']['timestamp100ns'] -= 1000000
                    f['frameWorldReadiness']['sourceFrame'] = f['sourceFrame'].copy()
                elif kind == 'yaw':
                    f['navigationPose']['yawDegrees'] += 4
                elif kind == 'climb':
                    f['motionEvidence']['status'] = 'climb'
                elif kind == 'confidence':
                    f['navigationPose']['positionConfidence'] = .98
                with self.assertRaises(RuntimeError):
                    if kind == 'interrupt':
                        nav.interrupt('userPause')
                    else:
                        nav.prepare(f)
                self.assertEqual((nav.phase, nav.legs, nav.drain_events()), ('failed',1,[]))

    def test_shortest_ordered_paths_include_only_surveyed_neighbors(self):
        expected = {(A, B): (B,), (B, A): (A,), (B, C): (C,), (C, B): (B,),
                    (A, C): (B, C), (C, A): (B, A)}
        for (origin, destination), path in expected.items():
            with self.subTest(origin=origin, destination=destination):
                self.assertEqual(itinerary_legs(origin, [destination]),
                                 tuple((a, b, 1) for a, b in zip((origin,) + path, path)))
        self.assertEqual(itinerary_legs(A, [B, A, C, A]), (
            (A, B, 1), (B, A, 2), (A, B, 3), (B, C, 3), (C, B, 4), (B, A, 4)))

    def test_invalid_station_stationary_or_unbounded_requests_fail_at_construction(self):
        for start, destinations in ((None, [A]), (B, []), (A, C), ('off-street', [A]), (B, [A, 'off-street']),
                                    (A, [A]), (A, [C, C]), (B, [C, A, C, A, C])):
            with self.subTest(start=start, destinations=destinations), self.assertRaises(ValueError):
                HybridNavigation(capability(), STREET_PATROL_ROUTE,
                                 itinerary_start=start, itinerary_destinations=destinations)
        with self.assertRaises(ValueError):
            HybridNavigation(capability(), itinerary_destinations=[C])

    def test_every_named_start_requires_three_qualified_observations_on_site(self):
        for start, dest in ((A, B), (B, A), (C, B)):
            with self.subTest(start=start):
                nav = HybridNavigation(capability(), STREET_PATROL_ROUTE, itinerary_start=start, itinerary_destinations=[dest])
                with self.assertRaises(RuntimeError):
                    nav.prepare(station_frame(1, dest, 1))
                with self.assertRaises(RuntimeError):
                    nav.choose(station_frame(2, dest, 1), proposal(['W']))
                self.assertEqual((nav.legs, nav.drain_events()), (0, []))
                nav = HybridNavigation(capability(), STREET_PATROL_ROUTE, itinerary_start=start, itinerary_destinations=[dest])
                self.assertEqual(nav.prepare(station_frame(1, start, 1)), 'confirmingStart')
                self.assertEqual(nav.prepare(station_frame(1, start, 1)), 'duplicatePose')
                self.assertEqual(nav.prepare(station_frame(2, start, 1)), 'confirmingStart')
                self.assertEqual(nav.drain_events(), [])
                nav.prepare(station_frame(3, start, 1))
                marker, = nav.drain_events()
                self.assertEqual((marker['type'], marker['station'], marker['requestedDestination'], marker['target']),
                                 ('hybridStartVerified', start, dest, dest))
                self.assertEqual([s['frameId'] for s in marker['samples']], [1, 2, 3])

    def test_revisit_and_pass_through_advance_only_on_settled_released_receipts(self):
        # At the junction, the first request heads back toward the stairs instead of following the patrol to the lamp.
        requests = [A, C, B]
        nav = HybridNavigation(capability(), STREET_PATROL_ROUTE, itinerary_start=B, itinerary_destinations=requests)
        requests[0] = C  # The owner cannot change a live plan by mutating its input.
        path = ((B, A, 1, A), (A, B, 2, C), (B, C, 2, C), (C, B, 3, B))
        i, epoch = 3, 1
        for j in range(1, 4):
            nav.prepare(station_frame(j, B, epoch))
        nav.drain_events()
        for leg, (origin, target, ordinal, requested) in enumerate(path):
            i += 1
            source = station_frame(i, origin, epoch)
            self.assertIsNone(nav.prepare(source))
            choice = nav.choose(source, proposal(['W']))
            self.assertEqual((choice['fromStation'], choice['toStation'], choice['requestedDestination'],
                              choice['destinationOrdinal'], choice['segmentIndex']), (origin, target, requested, ordinal, leg))
            self.assertEqual(choice['navigationMode'], 'itinerary')
            self.assertNotIn('circuit', choice)
            i += 1
            self.assertEqual(nav.prepare(station_frame(i, target, epoch)), 'releaseRequired')
            with self.assertRaises(RuntimeError):
                nav.choose(station_frame(i, target, epoch), proposal(['W']))
            self.assertEqual(nav.drain_events(), [])
            arrival = i
            epoch += 1
            nav.released(release(i, epoch))
            for _ in range(2):
                i += 1
                self.assertEqual(nav.prepare(station_frame(i, target, epoch)), 'verifyingEndpoint')
                self.assertEqual(nav.snapshot()['completedLegs'], leg)
                self.assertEqual(nav.drain_events(), [])
            i += 1
            self.assertEqual(nav.prepare(station_frame(i, target, epoch)), 'endpointVerified')
            endpoint, *goals = nav.drain_events()
            self.assertEqual((endpoint['type'], endpoint['releaseEpoch'], endpoint['arrivalFrameId']),
                             ('hybridEndpointVerified', epoch, arrival))
            self.assertEqual([s['frameId'] for s in endpoint['samples']], [i - 2, i - 1, i])
            if requested == target:
                marker, = goals
                self.assertEqual((marker['type'], marker['frameId'], marker['destinationOrdinal'], marker['station'],
                                  marker['completedLegs']), ('hybridDestinationVerified', i, ordinal, requested, leg + 1))
            else:
                self.assertEqual(goals, [])
        final = nav.snapshot()
        self.assertEqual((final['phase'], final['completedLegs'], final['completedDestinations']), ('complete', 4, 3))
        self.assertNotIn('completedCircuits', final)
        self.assertEqual(nav.prepare(station_frame(i + 1, B, epoch)), 'itineraryComplete')
        with self.assertRaises(RuntimeError):
            nav.choose(station_frame(i + 1, B, epoch), proposal(['W']))
        self.assertEqual(nav.drain_events(), [])

    def test_direct_shortcut_or_unrelated_release_cannot_advance_an_itinerary(self):
        for failure in ('shortcut', 'badRelease'):
            nav = HybridNavigation(capability(), STREET_PATROL_ROUTE, itinerary_start=A, itinerary_destinations=[C])
            for i in range(1, 4):
                nav.prepare(station_frame(i, A, 1))
            nav.drain_events()
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                if failure == 'shortcut':
                    nav.prepare(station_frame(4, C, 1))
                else:
                    self.assertEqual(nav.prepare(station_frame(4, B, 1)), 'releaseRequired')
                    nav.released(release(4, 9))
            self.assertEqual((nav.legs, nav.completed_destinations, nav.drain_events()), (0, 0, []))
