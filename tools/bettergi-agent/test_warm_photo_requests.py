"""Exercise ownership, release barriers and receipt retirement without a live controller."""
import json
from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from warm_photo_requests import WarmPhotoRequests, validate_plan


class WarmRequestsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = dict(version=1, requests=[
            dict(id='a'*32, name='lamp', targets=['west-lamp'], circuits=1),
            dict(id='b'*32, name='stairs', targets=['stair-front'], circuits=1)])
        self.file = self.root/'plan.json'
        factory = patch('warm_photo_requests.PatrolPhotoSurvey')
        self.factory = factory.start()
        self.addCleanup(factory.stop)
        self.load(self.plan['requests'], 'photos')
        self.start = dict(type='hybridStartVerified', frameId=1, sourceEpoch='capture')
        self.circuit = dict(type='hybridCircuitVerified', completedLegs=4, sourceEpoch='capture', frameId=100)
        self.endpoint = dict(samples=[dict(frameId=100)], releaseEpoch=9, releaseAtMs=123, arrivalFrameId=94)
        self.release = dict(type='released', serverNowMs=123, worldReadiness=dict(
            epoch=9, reason='client_release', ready=False, sourceFrame=dict(captureEpoch='capture')))

    def load(self, requests, folder):
        """Construct a fresh lease with distinct mocked photo collectors."""
        self.file.write_text(json.dumps(dict(version=1, requests=requests)))
        self.surveys = [Mock() for _ in requests]
        for survey in self.surveys:
            survey.snapshot.return_value = {'complete':True}
        self.factory.side_effect = self.surveys
        self.warm = WarmPhotoRequests(self.file, self.root/folder, 'c'*64, self.file,
                                      dict(sessionId='lease', ownerEpoch='owner'), 'run', 4*sum(r['circuits'] for r in requests))

    def admit(self):
        self.warm.after_native(self.start)
        self.warm.accepted('old', 10)
        self.warm.released(94, self.release)

    def test_release_and_photo_barrier_prevent_old_action_leak(self):
        self.admit()
        with self.assertRaisesRegex(RuntimeError, 'terminal receipts'):
            self.warm.after_native(self.circuit, self.endpoint)
        self.warm.receipt(dict(requestId='old', frameId=10, appliedSteps=[{}]))
        self.surveys[0].snapshot.return_value = {'complete':False}
        with self.assertRaisesRegex(RuntimeError, 'complete photos'):
            self.warm.after_native(self.circuit, self.endpoint)
        self.surveys[0].snapshot.return_value = {'complete':True}
        rows = self.warm.after_native(self.circuit, self.endpoint)
        self.assertEqual([r['type'] for r in rows], ['warmPhotoRequestCompleted','warmPhotoHandoff','warmPhotoRequestStarted'])
        self.assertEqual([r['warmRequestId'] for r in rows], ['a'*32,'a'*32,'b'*32])
        self.assertEqual(rows[1]['release']['arrivalFrameId'], 94)
        self.assertEqual(rows[1]['pendingActionIds'], [])
        self.assertIsNone(self.warm.first_applied)
        with self.assertRaisesRegex(RuntimeError, 'frame boundary'):
            self.warm.accepted('late', 100)
        self.warm.accepted('new', 101)
        self.warm.receipt(dict(requestId='new', frameId=101, appliedSteps=[{}]))
        status = json.loads((self.root/'photos/warm-status.json').read_bytes())
        self.assertEqual((status['activeOrdinal'],status['activeFirstAppliedFrameId']), (2,101))

    def test_wrong_epoch_cannot_end_request(self):
        self.admit()
        self.warm.receipt(dict(requestId='old', frameId=10, appliedSteps=[{}]))
        with self.assertRaisesRegex(RuntimeError, 'verified release'):
            self.warm.after_native(self.circuit, dict(self.endpoint, releaseEpoch=8))
        self.assertEqual(self.warm.index,0)

    def test_same_targets_or_oversized_plan_refused(self):
        for edits in (dict(targets=['west-lamp']),dict(circuits=32),dict(id='a'*32),dict(name='lamp')):
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                validate_plan(dict(self.plan,requests=[self.plan['requests'][0],dict(self.plan['requests'][1], **edits)]))

    def test_three_requests_use_two_separate_barriers_and_retire_at_the_last(self):
        requests = [*self.plan['requests'], dict(id='d'*32, name='junction', targets=['sidewalk-junction'], circuits=1)]
        self.load(requests, 'three')
        self.warm.after_native(self.start)
        for ordinal, request in enumerate(requests, 1):
            frame = 100 * ordinal
            endpoint = dict(self.endpoint, samples=[dict(frameId=frame)], arrivalFrameId=frame-6, releaseEpoch=ordinal)
            circuit = dict(self.circuit, frameId=frame, completedLegs=4*ordinal)
            release = dict(self.release, worldReadiness=dict(self.release['worldReadiness'], epoch=ordinal))
            self.warm.accepted(request['name'], frame-30)
            self.warm.receipt(dict(requestId=request['name'], frameId=frame-30, appliedSteps=[{}]))
            if ordinal > 1:
                with self.assertRaisesRegex(RuntimeError, 'verified release'):
                    self.warm.after_native(circuit, endpoint)
            self.warm.released(frame-6, release)
            rows = self.warm.after_native(circuit, endpoint)
            self.assertEqual((rows[0]['warmRequestId'], rows[0]['ordinal']), (request['id'], ordinal))
            if ordinal < 3:
                self.assertEqual([row['type'] for row in rows], [
                    'warmPhotoRequestCompleted','warmPhotoHandoff','warmPhotoRequestStarted'])
                self.assertEqual((rows[1]['nextRequestId'],rows[2]['warmRequestId']), (requests[ordinal]['id'],)*2)
                with self.assertRaisesRegex(RuntimeError, 'frame boundary'):
                    self.warm.require_action_frame(frame)
            else:
                self.assertEqual([row['type'] for row in rows], ['warmPhotoRequestCompleted'])
                self.assertTrue(self.warm.finished)
                with self.assertRaisesRegex(RuntimeError, 'frame boundary'):
                    self.warm.require_action_frame(frame+1)

    def test_predeclared_count_aggregate_budget_and_nonadjacent_duplicates(self):
        first, second = self.plan['requests']
        third = dict(id='3'*32,name='junction',targets=['sidewalk-junction'],circuits=1)
        fourth = dict(id='4'*32,name='pair',targets=['west-lamp','stair-front'],circuits=1)
        valid = [first,second,third,fourth]
        self.assertEqual(validate_plan(dict(version=1,requests=valid)), valid)
        for rows in ([first], valid+[dict(fourth,id='5'*32)], [first,second,dict(third,id=first['id'])],
                     [first,second,third,dict(fourth,name=first['name'])],
                     [fourth,second,dict(third,targets=['stair-front','west-lamp'])],
                     [first,second,third,dict(fourth,circuits=30)]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validate_plan(dict(version=1, requests=rows))

    def test_child_revalidates_owner_time_and_freshness_limits(self):
        """Direct child invocation must obey the same bounds as the launcher."""
        from run_rdp_patrol import options, patrol_argv
        from stream_client import parse_arguments
        args = options([])
        args.warm_photo_plan = self.file
        args.landmark_shadow = args.photo_qualification = self.file
        cli = patrol_argv(args,3,self.root)[5:]
        binding = f"--patrol-series-binding=111:{'a'*32}:222:{'b'*32}:{time.monotonic_ns()+60_000_000_000}"
        self.assertIsNotNone(parse_arguments(cli+[binding]).patrol_series_binding)
        for suffix in ([],[binding,'--seconds=601'],[binding,'--max-observation-age-ms=151']):
            with self.subTest(suffix=suffix), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_arguments(cli+suffix)
