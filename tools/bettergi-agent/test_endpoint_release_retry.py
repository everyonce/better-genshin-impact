"""A raced R57 release acknowledgement is refusal evidence, never an arrival barrier."""
import copy
import unittest
from unittest.mock import patch

from hybrid_navigation import HybridNavigation
from hybrid_routes import STREET_PATROL_ROUTE
from test_hybrid_itinerary import A, B, capability, station_frame, release
from test_hybrid_navigation import proposal


def ready_frame(index, station=B, epoch=2):
    """A fully bound native/source observation at the original station after invalidation."""
    frame = station_frame(index, station, epoch)
    frame['inputAvailable'] = True
    frame['frameWorldReadiness']['reason'] = 'world_ready'
    return frame


def arriving():
    """Establish the real geometry and a single, as-yet-unacknowledged endpoint release."""
    nav = HybridNavigation(capability(), STREET_PATROL_ROUTE, itinerary_start=A,
                           itinerary_destinations=[B,A], stationary_photo_retries=True)
    for index in (1,2,3):
        nav.prepare(station_frame(index,A,1))
    nav.drain_events()
    nav.prepare(ready_frame(4,B,1))
    failed = release(4,2)
    failed['worldReadiness']['reason'] = 'world_observation_invalidated'
    failed['executionContext'] = dict(sampledAtMs=405, telemetryComplete=True, active=None,
        trackedState=dict(heldKeys=[],telemetryIncomplete=False,releaseOutcome='returned_unverified'),
        lastInputEvent=dict(atMs=404, origin='release:client_release',
                            call=dict(operation='releaseAll',stage='returned_unverified',error=None)))
    return nav,failed


class ReleaseRetryTests(unittest.TestCase):
    def test_reissue_after_two_fresh_pose_samples_then_three_under_genuine_release(self):
        nav, failed = arriving()
        nav.released(failed)
        refused, = nav.drain_events()
        self.assertEqual(refused['rejectedReadiness'],failed['worldReadiness'])
        self.assertEqual(refused['rejectedExecution'],failed['executionContext'])
        self.assertIsNone(nav.release_at)
        self.assertEqual(nav.prepare(ready_frame(5)),'waitingForEndpointReleaseRetry')
        self.assertEqual(nav.prepare(ready_frame(5)),'waitingForEndpointReleaseRetry')
        with self.assertRaisesRegex(RuntimeError,'verified active leg'):
            nav.choose(ready_frame(5),proposal(['W']))
        self.assertEqual(nav.prepare(ready_frame(6)),'retryReleaseRequired')
        retried, = nav.drain_events()
        self.assertEqual((retried['firstArrivalFrameId'],retried['retryArrivalFrameId']),(4,6))
        self.assertEqual([s['frameId'] for s in retried['samples']],[5,6])
        nav.released(release(6,3))
        for index in (7,8,9):
            nav.prepare(ready_frame(index,epoch=3))
        endpoint, destination = nav.drain_events()
        self.assertEqual((endpoint['firstArrivalFrameId'],endpoint['arrivalFrameId'],endpoint['releaseEpoch'],
                          endpoint['releaseAtMs'],destination['frameId']), (4,6,3,605,9))
        self.assertEqual([s['frameId'] for s in endpoint['samples']],[7,8,9])

    def test_other_reasons_incomplete_release_and_second_miss_fail(self):
        for change in ('active','held','reason','capture','epoch','backend'):
            nav, reply = arriving()
            if change == 'active':
                reply['executionContext']['active'] = {'keys':['W']}
            elif change == 'held':
                reply['executionContext']['trackedState']['heldKeys'] = ['W']
            elif change == 'backend':
                reply['executionContext']['lastInputEvent']['call']['stage'] = 'skipped_backend_changed'
            elif change == 'reason':
                reply['worldReadiness']['reason'] = 'world_overlay_detected'
            elif change == 'capture':
                reply['worldReadiness']['sourceFrame']['captureEpoch'] = 'foreign'
            else:
                reply['worldReadiness']['epoch'] = 3
            with self.subTest(change=change), self.assertRaisesRegex(RuntimeError,'patrol_release_unbound'):
                nav.released(reply)
        nav, reply = arriving()
        nav.released(reply)
        nav.prepare(ready_frame(5))
        nav.prepare(ready_frame(6))
        second = copy.deepcopy(reply)
        second['worldReadiness']['epoch'] = 3
        second['serverNowMs'] = 605
        with self.assertRaisesRegex(RuntimeError,'patrol_release_unbound'):
            nav.released(second)

    def test_deadline_station_gate_and_epoch_cannot_be_bypassed(self):
        for key in ('deadline','station','epoch','source','interrupted'):
            nav, reply = arriving()
            nav.released(reply)
            frame = ready_frame(5,A if key=='station' else B,3 if key=='epoch' else 2)
            if key=='source':
                frame['frameWorldReadiness']['sourceFrameId'] = 4
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                if key == 'deadline':
                    with patch('hybrid_navigation.time.perf_counter_ns',return_value=nav.release_retry['deadlineNs']+1):
                        nav.check_release_retry_time()
                elif key == 'interrupted':
                    nav.interrupt('userPause')
                else:
                    nav.prepare(frame)
