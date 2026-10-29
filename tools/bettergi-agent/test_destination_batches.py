"""Exercise addressed successor admission on an inert continuous lease."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from warm_photo_requests import WarmPhotoRequests, batch_plan_digest
from run_rdp_patrol import native_qpc_sample
import test_hybrid_itinerary as itinerary
from test_hybrid_itinerary import A, B, C, station_frame
from test_hybrid_navigation import proposal


def destination_plan(start, entries):
    """Create a strict frozen version-two plan with unique request IDs."""
    return dict(version=2, mode='destinations', start=start, requests=[
        dict(id=name*32, name=name, destination=station, targets=[station]) for name,station in entries])


class DestinationBatchTests(unittest.TestCase):
    def setUp(self):
        """Initialize a two-batch warm controller with real scoped journal files and inert photo heads."""
        tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.file = self.root/'photo-requests.json'
        self.first = destination_plan(A,[('a',B),('b',A)])
        self.second = destination_plan(A,[('c',C),('d',B)])
        self.file.write_text(json.dumps(self.first))
        self.factory = patch('warm_photo_requests.PatrolPhotoSurvey', side_effect=lambda *a, **k: Mock(collected={}))
        self.factory.start()
        self.addCleanup(self.factory.stop)
        self.owner = WarmPhotoRequests(self.file, self.root/'photos', 'c'*64, self.file,
            dict(sessionId='lease',ownerEpoch=5), 'run', 8, batch_count=2)
        self.owner.after_native(dict(type='hybridStartVerified',frameId=1,sourceEpoch='capture',station=A))
        self.batch = self.root/'batches'/'00002.json'
        self.batch.parent.mkdir()
        self.envelope = dict(version=1,mode='destination-batch',runId='run',sessionId='lease',ownerEpoch=5,
            batchOrdinal=2,previousSha256=self.owner.plan_sha,plan=self.second,
            witness=dict(batchOrdinal=1, requestId='a'*32,nativeRequestId='1'*32,frameId=10))

    def finish(self, ordinal, settled, legs):
        """Provide original scoped movement receipts, fresh photo and release acknowledgements."""
        action = str(ordinal)*32
        self.owner.accepted(action, settled-10)
        self.owner.receipt(dict(requestId=action,frameId=settled-10,appliedSteps=[dict(startedAtMs=settled-9)]))
        self.owner.released(settled-6,dict(type='released', serverNowMs=settled-5, worldReadiness=dict(
            epoch=ordinal,reason='client_release',ready=False,sourceFrame=dict(captureEpoch='capture'))))
        station = self.owner.current['destination']
        self.owner.survey.collected[station] = settled
        self.owner.survey.snapshot.return_value = {'complete':True}
        endpoint = dict(samples=[dict(frameId=settled)],station=station,releaseEpoch=ordinal,
                        releaseAtMs=settled-5,arrivalFrameId=settled-6)
        native = dict(type='hybridDestinationVerified',completedLegs=legs,frameId=settled,sourceEpoch='capture',
                      destinationOrdinal=ordinal,requestedDestination=station,station=station)
        return self.owner.after_native(native,endpoint)

    def publish(self):
        """Seal a selected payload and its local Windows QPC publication before the consumer reads it."""
        raw = json.dumps(self.envelope).encode()
        self.batch.write_bytes(raw)
        binding = {k:v for k,v in self.envelope.items() if k not in ('plan','mode')}
        binding.update(batchSha256=hashlib.sha256(raw).hexdigest(),observedAtMonotonicNs=1)
        freq, ticks = native_qpc_sample()
        bracket = dict(clock='windows-query-performance-counter',frequencyHz=freq,beforeTicks=ticks,afterTicks=ticks)
        self.batch.with_suffix('.intent.json').write_text(json.dumps(
            dict(binding,type='destinationBatchIntent',plan=self.second)))
        self.batch.with_suffix('.publication.json').write_text(json.dumps(
            dict(binding,type='destinationBatchPublished',publishedAtMonotonicNs=2,publicationQpc=bracket)))

    def test_successor_requires_a_release_then_opens_fresh_goal_and_finishes_under_ceiling(self):
        self.finish(1,20,1)
        self.publish()
        with self.assertRaisesRegex(RuntimeError,'boundary'):
            self.owner.consume_batch(25)
        done, = self.finish(2,40,2)
        self.assertEqual(done['type'], 'warmPhotoRequestCompleted')
        with self.assertRaisesRegex(RuntimeError,'frame boundary'):
            self.owner.require_action_frame(41)
        destinations, rows = self.owner.consume_batch(43)
        self.assertEqual(destinations,[C,B])
        self.assertEqual([r['type'] for r in rows], ['warmBatchAccepted','warmPhotoHandoff','warmPhotoRequestStarted'])
        raw = self.batch.read_bytes()
        accepted, old, new = rows
        self.assertEqual((accepted['nextBatchBytes'], accepted['publicationWitness']), (len(raw), self.envelope['witness']))
        self.assertEqual((accepted['nextBatchSha256'], accepted['nextBatchPlanSha256']),
                         (hashlib.sha256(raw).hexdigest(),batch_plan_digest(self.second)))
        self.assertEqual((accepted['admissionFrameId'], old['batchOrdinal'], new['batchOrdinal'],new['ordinal']), (43,1,2,3))
        self.assertEqual(accepted['release'],done['release'])
        self.assertIsNone(self.owner.first_applied)
        self.assertIsNone(self.owner.release)
        self.owner.require_batch_dispatch_window(1030)
        with self.assertRaisesRegex(RuntimeError,'one-second'):
            self.owner.require_batch_dispatch_window(1031)
        with self.assertRaisesRegex(RuntimeError,'frame boundary'):
            self.owner.require_action_frame(43)
        self.finish(3,60,4)
        self.finish(4,80,5)
        self.assertTrue(self.owner.finished)

    def test_missing_or_invalid_successor_never_advances(self):
        self.finish(1,20,1)
        self.finish(2,40,2)
        self.assertIsNone(self.owner.consume_batch(41))
        self.publish()
        for changes in (dict(runId='foreign'),dict(ownerEpoch=7),dict(previousSha256='0'*64),
                        dict(witness=dict(self.envelope['witness'],frameId=9)),dict(plan=destination_plan(B,[('c',C),('d',B)])),
                        dict(plan=destination_plan(A,[('a',C),('d',B)])),dict(mode='command'),
                        dict(plan=destination_plan(A,[('c',B),('d',A)]))):
            self.batch.write_text(json.dumps(dict(self.envelope,**changes)))
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.owner.consume_batch(41)
            self.assertEqual(self.owner.index,1)
        with patch('warm_photo_requests.time.perf_counter_ns',return_value=self.owner.batch_boundary[2]+1):
            with self.assertRaisesRegex(RuntimeError,'1000 ms'):
                self.owner.consume_batch(41)

    def test_native_wait_never_walks_or_reuses_the_admission_frame(self):
        nav = itinerary.ItineraryNavigationTests().at_first_photo((B,))
        nav.finish_destination_photo(await_batch=True)
        self.assertEqual(nav.prepare(station_frame(8,B,2)), 'batchEndpointStillVerified')
        with self.assertRaisesRegex(RuntimeError,'verified active leg'):
            nav.choose(station_frame(8,B,2),proposal(['W']))
        nav.append_destination_batch([A,C])
        self.assertEqual((nav.segment['destinationOrdinal'],nav.legs,nav.target_name),(2,1,A))
        with self.assertRaisesRegex(RuntimeError,'newer navigable frame'):
            nav.choose(station_frame(8,B,2),proposal(['W']))

    def test_native_batch_wait_cannot_admit_from_a_different_station_epoch_or_expired_window(self):
        """Late publication cannot revive an obsolete receipt or move the stationary game during the wait."""
        for index, station, epoch in ((8,A,2),(8,B,3),(18,B,2)):
            with self.subTest(index=index,station=station,epoch=epoch):
                nav = itinerary.ItineraryNavigationTests().at_first_photo((B,))
                nav.finish_destination_photo(await_batch=True)
                with self.assertRaises(RuntimeError):
                    nav.prepare(station_frame(index, station, epoch))
                with self.assertRaises(RuntimeError):
                    nav.append_destination_batch([A,C])
