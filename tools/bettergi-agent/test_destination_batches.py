"""Exercise addressed successor admission on an inert continuous lease."""
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from warm_photo_requests import WarmPhotoRequests, WarmQueueInterrupted, WarmQueueStarved, batch_plan_digest
from landmark_recognizer import G4_SHA256
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

    def finish(self, ordinal, settled, legs, *, before_endpoint=None):
        """Provide original scoped movement receipts, fresh photo and release acknowledgements."""
        action = str(ordinal)*32
        self.owner.accepted(action, settled-10)
        self.owner.receipt(dict(requestId=action,frameId=settled-10,status='completed',acceptedAtMs=settled-10,
                                endedAtMs=settled-8,appliedSteps=[dict(startedAtMs=settled-9)]))
        if before_endpoint is not None:
            before_endpoint()
        self.owner.released(settled-6,dict(type='released', serverNowMs=settled-5, worldReadiness=dict(
            epoch=ordinal,reason='client_release',ready=False,sourceFrame=dict(captureEpoch='capture'))))
        station = self.owner.current['destination']
        self.owner.survey.collected[station] = settled
        self.owner.survey.snapshot.return_value = {'complete':True}
        endpoint = dict(samples=[dict(frameId=settled)],station=station,releaseEpoch=ordinal,
                        releaseAtMs=settled-5,arrivalFrameId=settled-6)
        native = dict(type='hybridDestinationVerified',completedLegs=legs,frameId=settled,atMs=settled,sourceEpoch='capture',
                      destinationOrdinal=ordinal,requestedDestination=station,station=station)
        return self.owner.after_native(native,endpoint)

    def publish(self):
        """Seal a selected payload and its local Windows QPC publication before the consumer reads it."""
        raw = json.dumps(self.envelope).encode()
        self.batch.write_bytes(raw)
        binding = {k:v for k,v in self.envelope.items() if k not in ('plan','mode','kind')}
        binding.update(batchSha256=hashlib.sha256(raw).hexdigest(),observedAtMonotonicNs=1)
        if self.owner.open_queue:
            chosen = [r['destination'] for r in self.envelope.get('plan',{}).get('requests',[])]
            clock = self.owner.batch_clocks[binding['witness']['requestId']]
            policy = json.dumps(dict(binding,type='destinationQueueDecision',gameplayClock=clock,selectedStations=chosen)).encode()
            self.batch.with_suffix('.decision.json').write_bytes(policy)
            binding['policyDecisionSha256'] = hashlib.sha256(policy).hexdigest()
        freq, ticks = native_qpc_sample()
        bracket = dict(clock='windows-query-performance-counter',frequencyHz=freq,beforeTicks=ticks,afterTicks=ticks)
        decision = {'plan':self.second} if 'plan' in self.envelope else {'kind':self.envelope['kind']}
        self.batch.with_suffix('.intent.json').write_text(json.dumps(dict(binding,type='destinationBatchIntent',**decision)))
        self.batch.with_suffix('.publication.json').write_text(json.dumps(
            dict(binding,type='destinationBatchPublished',publishedAtMonotonicNs=2,publicationQpc=bracket)))

    def open_queue(self, *, count=12, legs=2):
        """Start an opt-in queue against a real local QPC, with synthetic dispatch times in the same domain."""
        freq,ticks = native_qpc_sample()
        hello = dict(sessionId='lease',ownerEpoch=5,inputTelemetry=dict(stopwatchFrequency=freq,sessionOriginAtStopwatchTicks=ticks-freq//3))
        (self.root/'patrol.json.control.json').write_text(json.dumps(dict(version=1,runId='run',command='run')))
        self.owner = WarmPhotoRequests(self.file,self.root/'open',G4_SHA256,self.file,hello,'run',legs,batch_count=count,open_queue=True)
        self.owner.after_native(dict(type='hybridStartVerified',frameId=1,sourceEpoch='capture',station=A))
        return hello

    def test_finish_at_actual_leg_cap_without_reserving_unused_batches(self):
        hello = self.open_queue()
        self.envelope.pop('plan')
        self.envelope['kind'] = 'finish'
        self.finish(1,20,1)
        self.publish()
        with self.assertRaisesRegex(RuntimeError,'released request boundary'):
            self.owner.consume_batch(21)
        done, = self.finish(2,40,2)
        status = json.loads((self.root/'open/warm-status.json').read_bytes())
        self.assertFalse(status['complete'])
        clock = hello['inputTelemetry']
        hz,origin = clock['stopwatchFrequency'],clock['sessionOriginAtStopwatchTicks']
        self.assertEqual(status['gameplayClock'],dict(frequencyHz=hz,firstAppliedTicks=origin+round(11*hz/1000),
                         witnessAppliedTicks=origin+round(31*hz/1000),firstNativeRequestId='1'*32,firstFrameId=10))
        with self.assertRaisesRegex(ValueError,'fresh frame'):
            self.owner.consume_batch(39)
        self.assertIsNone(self.owner.consume_batch(40,still_current=lambda:False))
        def stop_on_last_check():
            (self.root/'STOP').touch()
            return True
        with self.assertRaisesRegex(WarmQueueInterrupted,'userStop'):
            self.owner.consume_batch(40,still_current=stop_on_last_check)
        (self.root/'STOP').unlink()
        destinations, (last,) = self.owner.consume_batch(40)
        self.assertIsNone(destinations)
        self.assertEqual((last['type'],last['decisionOrdinal'],last['ordinal'],last['batchOrdinal']),('warmQueueFinished',2,2,1))
        self.assertEqual(last['publicationWitness'],self.envelope['witness'])
        self.assertEqual(last['release'],done['release'])
        self.assertEqual(last['pendingActionIds'],[])
        self.assertNotIn('nextRequestId',last)
        self.assertEqual(last['decisionSha256'],hashlib.sha256(self.batch.read_bytes()).hexdigest())
        self.assertTrue(self.owner.finished)
        self.assertEqual(self.owner.first_applied,('2'*32,30))
        with self.assertRaisesRegex(RuntimeError,'frame boundary'):
            self.owner.require_action_frame(41)

    def test_early_finish_exclusive_and_release_bound(self):
        self.open_queue()
        self.finish(1,20,1)
        self.finish(2,40,2)
        self.assertIsNone(self.owner.consume_batch(41))
        with patch('warm_photo_requests.time.perf_counter_ns',return_value=self.owner.batch_boundary[2]+1):
            with self.assertRaises(WarmQueueStarved):
                self.owner.consume_batch(41)
        event = self.owner.starved_event()
        self.assertEqual((event['type'],event['frameId'],event['decisionOrdinal']),('warmQueueStarved',40,2))
        self.publish()
        with self.assertRaisesRegex(ValueError,'edge budget'):
            self.owner.consume_batch(41)
        del self.envelope['plan']
        self.envelope['kind'] = 'finish'
        self.publish()
        original = self.batch.read_bytes()
        for changes in (dict(ownerEpoch='other'),dict(previousSha256='0'*64),dict(plan=self.second),dict(kind='other'),
                        dict(witness=dict(self.envelope['witness'],nativeRequestId='wrong'))):
            self.batch.write_text(json.dumps(dict(self.envelope,**changes)))
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.owner.consume_batch(41)
        self.batch.write_bytes(original)
        self.owner.pending['unretired'] = 32
        with self.assertRaisesRegex(ValueError,'terminal receipt barrier'):
            self.owner.consume_batch(41)
        self.assertFalse(self.owner.finished)

    def test_open_queue_at_batch_cap_reserves_one_finish_only_slot(self):
        self.open_queue(count=2,legs=5)
        self.finish(1,20,1)
        self.finish(2,40,2)
        self.publish()
        _,rows = self.owner.consume_batch(40)
        self.finish(3,60,4)
        self.finish(4,80,5)
        self.assertFalse(self.owner.finished)
        self.batch = self.batch.with_name('00003.json')
        self.envelope.update(batchOrdinal=3,previousSha256=rows[0]['nextBatchSha256'],
                             witness=dict(batchOrdinal=2,requestId='c'*32,nativeRequestId='3'*32,frameId=50))
        self.publish()
        with self.assertRaisesRegex(ValueError,'Misaddressed'):
            self.owner.consume_batch(80)
        self.envelope.pop('plan')
        self.envelope['kind'] = 'finish'
        self.publish()
        _,(last,) = self.owner.consume_batch(80)
        self.assertEqual((last['decisionOrdinal'],last['batchOrdinal'],last['ordinal']),(3,2,4))

    def pending_first_successor(self):
        """Accept the first ordinary action of a new batch before its terminal receipt is available."""
        self.open_queue(count=2,legs=5)
        self.finish(1,20,1)
        self.finish(2,40,2)
        self.publish()
        self.owner.consume_batch(40)
        self.assertFalse(self.owner.awaiting_batch_dispatch_receipt(905))
        self.owner.require_batch_dispatch_window(1000)
        self.owner.accepted('3'*32,50)
        return dict(requestId='3'*32,frameId=50,status='completed',acceptedAtMs=910,endedAtMs=1045,
                    appliedSteps=[dict(startedAtMs=911)])

    def test_delayed_terminal_proves_first_applied_successor_without_a_second_proposal(self):
        receipt=self.pending_first_successor()
        bound=self.owner.batch_dispatch_before_ms
        self.assertTrue(self.owner.awaiting_batch_dispatch_receipt(bound+10))
        self.assertIsNone(self.owner.first_applied)
        with self.assertRaisesRegex(RuntimeError,'one-second'):
            self.owner.require_batch_dispatch_window(bound+44)
        self.owner.receipt(receipt)
        self.assertEqual(self.owner.first_applied,('3'*32,50))
        self.assertFalse(self.owner.awaiting_batch_dispatch_receipt(bound+14))
        self.owner.require_batch_dispatch_window(bound+150)

    def test_unapplied_or_late_first_dispatch_never_earns_the_handoff(self):
        receipt=self.pending_first_successor()
        bound=self.owner.batch_dispatch_before_ms
        with self.assertRaisesRegex(ValueError,'one-second'):
            self.owner.receipt(dict(receipt,appliedSteps=[dict(startedAtMs=bound)]))
        self.assertTrue(self.owner.awaiting_batch_dispatch_receipt(bound+1))
        self.owner.receipt(dict(receipt,status='expired',appliedSteps=[]))
        self.assertIsNone(self.owner.first_applied)
        self.assertFalse(self.owner.awaiting_batch_dispatch_receipt(bound+2))
        with self.assertRaisesRegex(RuntimeError,'one-second'):
            self.owner.require_batch_dispatch_window(bound+2)

    def test_missing_terminal_has_bounded_wait_and_operator_stop_wins(self):
        self.pending_first_successor()
        bound=self.owner.batch_dispatch_before_ms
        self.assertTrue(self.owner.awaiting_batch_dispatch_receipt(bound+699))
        for now in (None,float('nan'),bound+700):
            with self.subTest(now=now),self.assertRaisesRegex(RuntimeError,'bounded wait'):
                self.owner.awaiting_batch_dispatch_receipt(now)
        (self.root/'STOP').touch()
        with self.assertRaisesRegex(WarmQueueInterrupted,'userStop'):
            self.owner.awaiting_batch_dispatch_receipt(bound+700)
        self.assertIsNone(self.owner.first_applied)
        self.assertEqual(self.owner.batch_dispatch_before_ms,bound)

    def test_native_finish_requires_the_released_final_endpoint_and_emits_no_more_legs(self):
        nav = itinerary.ItineraryNavigationTests().at_first_photo((B,))
        nav.finish_destination_photo(await_batch=True)
        nav.finish_destination_queue()
        self.assertEqual((nav.phase,nav.legs,nav.completed_destinations),('complete',1,1))
        self.assertEqual(nav.prepare(station_frame(8,B,2)),'itineraryComplete')
        with self.assertRaises(RuntimeError):
            nav.append_destination_batch([A,C])

    def assert_prepublished_finish_interrupted(self,command):
        """Issue a real addressed control document mid-walk, after valid finish bytes are already immutable."""
        from resident_runtime import ResidentControl,atomic_json
        from stream_client import consume_queue_decision,open_queue_interruption
        self.open_queue()
        control = ResidentControl(self.root/'control.json',self.root/'status.json','run')
        self.addCleanup(control.close)
        token = control.prediction_token()
        def issue(value):
            atomic_json(control.path,dict(version=1,runId=control.run_id,command=value))
            until = time.monotonic()+2
            while control.snapshot()[0] != value and time.monotonic()<until:
                time.sleep(.01)
            self.assertEqual(control.snapshot()[0],value)
        self.finish(1,20,1)
        self.envelope.pop('plan')
        self.envelope['kind'] = 'finish'
        self.publish()
        # At interruption the second action is already terminal, but its released endpoint has not arrived.
        def interrupt():
            self.assertIsNone(self.owner.batch_boundary)
            issue(command)
            self.assertEqual(open_queue_interruption(control,token),'userStop' if command=='stop' else 'userPause')
        completed = self.finish(2,40,2,before_endpoint=interrupt)
        self.assertEqual([r['type'] for r in completed],['warmPhotoRequestCompleted'])
        with patch('warm_photo_requests.batch_bytes',side_effect=AssertionError('Interrupted run reopened a decision file')):
            self.assertIsNone(consume_queue_decision(self.owner,dict(frameId=41),control,token,150))
            if command=='pause':
                issue('run')
                self.assertEqual(open_queue_interruption(control,token),'openQueueAuthorityChanged')
                self.assertIsNone(consume_queue_decision(self.owner,dict(frameId=42),control,token,150))
        self.assertFalse(self.owner.finished)
        self.assertEqual(len(self.owner.requests),2)
        self.assertFalse(json.loads((self.root/'open/warm-status.json').read_bytes())['complete'])

    def test_prepublished_finish_yields_to_stop_before_released_boundary(self):
        self.assert_prepublished_finish_interrupted('stop')

    def test_prepublished_finish_cannot_be_revived_after_operator_pause(self):
        self.assert_prepublished_finish_interrupted('pause')

    def test_expired_boundary_and_stale_finish_yield_to_the_original_operator(self):
        """A late/malformed packet, a missed deadline, and the native pose timeout must all preserve STOP priority."""
        from stream_client import record_open_queue_boundary_error
        self.open_queue()
        self.finish(1,20,1)
        self.envelope.pop('plan')
        self.envelope['kind'] = 'finish'
        self.publish()
        self.finish(2,40,2)
        self.batch.write_bytes(b'corrupt')
        control = self.root/'patrol.json.control.json'
        for command,marker,wanted,source in (('run',True,'userStop','runLocalStopFile'),
                                              ('pause',False,'userPause','addressedControl'),
                                              ('stop',False,'userStop','addressedControl')):
            control.write_text(json.dumps(dict(version=1,runId='run',command=command)))
            if marker:
                (self.root/'STOP').touch()
            with self.subTest(command=command),patch('warm_photo_requests.time.perf_counter_ns',return_value=self.owner.batch_boundary[2]+1):
                with self.assertRaises(WarmQueueInterrupted) as failure:
                    self.owner.consume_batch(41)
                self.assertEqual((failure.exception.reason,failure.exception.source),(wanted,source))
                for exc in (failure.exception,WarmQueueStarved('elapsed'),RuntimeError('hybrid_navigation:destination_batch_deadline')):
                    report,recorder = dict(hybridNavigationEvents=[]),Mock()
                    self.assertTrue(record_open_queue_boundary_error(self.owner,exc,'destination_batch_deadline',report,recorder))
                    self.assertEqual(report['endReason'],wanted)
                    self.assertEqual(report['openQueueInterruption']['source'],source)
                    self.assertEqual(report['hybridNavigationEvents'],[])
                    self.assertNotIn('stop',report)
                    self.assertFalse(self.owner.finished)
            if marker:
                (self.root/'STOP').unlink()
        control.write_text(json.dumps(dict(version=1,runId='another',command='stop')))
        (self.root/'STOP').touch()
        with self.assertRaisesRegex(ValueError,'lost its addressed control'):
            self.owner.consume_batch(41)

    def test_stop_arrives_during_an_invalid_packet_read(self):
        """The guarded policy read reports the arriving operator marker instead of the packet error."""
        import warm_photo_requests as warm_module
        from stream_client import consume_queue_decision
        self.open_queue()
        self.finish(1,20,1)
        self.finish(2,40,2)
        self.publish()
        original = warm_module.batch_bytes
        def read_packet(path):
            if path==self.batch:
                (self.root/'STOP').touch()
                return b'bad json'
            return original(path)
        ctl=Mock()
        ctl.guarded_submit.side_effect=lambda _,action:(True,action())
        with patch.object(warm_module,'batch_bytes',side_effect=read_packet):
            with self.assertRaisesRegex(WarmQueueInterrupted,'userStop'):
                consume_queue_decision(self.owner,dict(frameId=41),ctl,None,150)
        self.assertFalse(self.owner.finished)

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
