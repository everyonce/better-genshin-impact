"""Verify source alignment, teacher-label joins, evaluation isolation and the shadow API."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from steering_head import CLASSES, SteeringHead, features
from hybrid_routes import PATROL_STATIONS, STREET_PATROL_ROUTE
from train_steering import Run, applied_label, distinct, evaluate, fit, read_run, steering_point


def observation(yaw=90.):
    """An admitted source pose whose waypoint is at world bearing 90 degrees."""
    source = dict(captureEpoch='capture', timestamp100ns=123, freshnessAtMs=100.)
    return dict(frameId=8, inputAvailable=True, sourceFrame=source, frameQuality='usable',
        frameWorldReadiness=dict(ready=True, sourceFrameId=8, sourceFrame=source.copy()),
        navigationPose=dict(frameId=8, state='valid', x=0., y=0., yawDegrees=yaw, positionConfidence=1.,
                            yawConfidence=.5, layerId='City_102'),
        motionEvidence=dict(status='normal', spaceKeyMatched=False))


def receipt_case():
    """Generate one positive W joined by request, source timestamp, frame, dispatch and broker clocks."""
    frame = observation()
    step = dict(keys=['W'], mouseDx=0, mouseDy=0, durationMs=100)
    decision = dict(frameId=8, parseValid=True, steps=[step], observationTimestampMs=100., startBeforeMs=250.,
        acceptance=dict(type='accepted', requestId='r', acceptedAtMs=122.),
        hybridNavigation=dict(owner='hybrid-native', reason='modelIdleOrOffRoute', pose=frame['navigationPose'], step=step))
    receipt = dict(frameId=8, modelId='hybrid-native', status='completed', requestId='r',
                   acceptedAtMs=122., endedAtMs=222., appliedSteps=[dict(step, startedAtMs=122.5)])
    return frame, decision, receipt


def meta(tag, span):
    """Represent a distinct lease on a potentially shared continuously running compositor."""
    return dict(runId='run'+tag, lease=['s'+tag, 'owner'+tag], evidenceSha256=tag,
                captureEpoch='compositor', sourceInterval100ns=span, classCounts={k: 1 for k in CLASSES})


class SteeringTests(unittest.TestCase):
    def test_reader_supplies_qualified_edges_for_directed_native_labels(self):
        """A queued action becomes a label only through its external plan, without silently skipping the whole run."""
        frame,decision,receipt=receipt_case()
        edge=('stair-front','sidewalk-junction',1,'sidewalk-junction')
        decision['hybridNavigation'].update(navigationMode='itinerary',completedLegs=0,segmentIndex=0,
            fromStation=edge[0],toStation=edge[1],target=edge[1],destinationOrdinal=1,requestedDestination=edge[3])
        decision['rawPolicySteps']=[dict(keys=[],mouseDx=0,mouseDy=0)]
        with tempfile.TemporaryDirectory() as scratch:
            folder=Path(scratch)
            path=folder/'patrol.json'
            path.write_text(json.dumps(dict(status='completed',evidenceComplete=True,runId='run',modelLoads=1,
                inputRequested=True,segments=[dict(number=1)])))
            (folder/'patrol-segments').mkdir()
            recording=folder/'patrol-recording/00001'
            recording.mkdir(parents=True)
            part=dict(status='completed',model='open-p2p',residentRunId='run',serverDroppedReceipts=0,
                observationProfile='p2p-native-hamming-192-v1',
                recording=dict(droppedFrames=0,droppedEvents=0,abandonedFrames=0,droppedObservations=0),
                hello=dict(sessionId='lease',ownerEpoch='owner'),decisions=[decision],receipts=[receipt],
                hybridNavigation=dict(routeId=STREET_PATROL_ROUTE),
                policyMetadata=dict(implementation='fixture',parameterCount=150_000_000,precision='float16'))
            (folder/'patrol-segments/00001.json').write_text(json.dumps(part))
            (recording/'observations.jsonl').write_text(json.dumps(frame)+'\n')
            proof=dict(verifiedLegs=1,files=[],humanExpertDemonstration=False)
            with patch('training_itinerary.qualified_edges',return_value=([edge],proof)) as qualified:
                run=read_run(path)
                qualified.assert_called_once_with(folder.resolve())
            self.assertEqual(len(run.samples),1)
            self.assertEqual(run.samples[0][3],PATROL_STATIONS[edge[1]])
            self.assertEqual(run.meta['directedItinerary'],proof)
            from episode_split import reserve_split
            reserve_split(folder,'run','holdout')
            with patch('training_itinerary.qualified_edges',return_value=([edge],proof)):
                heldout=read_run(path)
            self.assertEqual(heldout.meta['datasetSplit'],'holdout')
            with self.assertRaisesRegex(ValueError,'cannot be used for fitting'):fit([heldout])
            with patch('training_itinerary.qualified_edges',side_effect=ValueError('unqualified itinerary')):
                with self.assertRaisesRegex(ValueError,'unqualified itinerary'):read_run(path)

    def test_patrol_goal_comes_from_the_current_directed_leg(self):
        h = dict(target='west-lamp', toStation='west-lamp', fromStation='sidewalk-junction', completedLegs=1)
        self.assertEqual(steering_point(STREET_PATROL_ROUTE, h), PATROL_STATIONS['west-lamp'])
        self.assertIsNone(steering_point(STREET_PATROL_ROUTE, dict(h, completedLegs=2)))
        self.assertIsNone(steering_point(STREET_PATROL_ROUTE, dict(h, bypassPointIndex=0)))

    def test_itinerary_shadow_follows_only_the_externally_bound_hop(self):
        a, b, c = 'stair-front', 'sidewalk-junction', 'west-lamp'
        edges = [(a,b,1,b), (b,a,2,a), (a,b,3,c), (b,c,3,c)]
        for leg, (origin, target, ordinal, requested) in enumerate(edges):
            h = dict(navigationMode='itinerary', completedLegs=leg, segmentIndex=leg, fromStation=origin,
                     toStation=target, target=target, destinationOrdinal=ordinal, requestedDestination=requested)
            self.assertEqual(steering_point(STREET_PATROL_ROUTE, h, edges), PATROL_STATIONS[target])
            self.assertIsNone(steering_point(STREET_PATROL_ROUTE, h))
            for changes in (dict(navigationMode=None), dict(segmentIndex=leg+1), dict(completedLegs=True),
                            dict(destinationOrdinal=True), dict(requestedDestination=origin), dict(fromStation=target),
                            dict(toStation=origin), dict(steeringPoint=dict(x=1, y=2)), dict(bypassPointIndex=0)):
                with self.subTest(leg=leg, changes=changes):
                    self.assertIsNone(steering_point(STREET_PATROL_ROUTE, dict(h, **changes), edges))

    def test_source_and_input_match_the_current_observation(self):
        f, raw = observation(), [dict(keys=[], mouseDx=0, mouseDy=0)]
        goal = (0., -1.)
        row = features(f, goal, raw)
        self.assertEqual(row[1:3], (0., 0.))
        self.assertEqual(features(dict(f, nextPose=dict(yawDegrees=0), receipt={'keys': ['A']}), goal, raw), row)
        self.assertIsNone(features(dict(f, navigationPose=dict(f['navigationPose'], frameId=7)), goal, raw))
        self.assertIsNone(features(dict(f, frameWorldReadiness=dict(f['frameWorldReadiness'], sourceFrameId=9)), goal, raw))
        self.assertIsNone(features(dict(f, motionEvidence=dict(status='climb')), goal, raw))
        self.assertIsNone(features(f, (float('nan'), 0), raw))
        self.assertIsNone(features(f, goal, []))

    def test_only_matching_native_terminal_labels_count(self):
        f, d, r = receipt_case()
        self.assertEqual(applied_label(d, f, r), 'forward')
        self.assertEqual(applied_label(d, f, dict(r, status='replaced')), 'forward')
        for bad in (dict(r, frameId=7), dict(r, acceptedAtMs=130.), dict(r, requestId='other'),
                    dict(r, modelId='open-p2p'), dict(r, status='cancelled'), dict(r, appliedSteps=[]),
                    dict(r, endedAtMs=300., appliedSteps=[dict(r['appliedSteps'][0], startedAtMs=251.)]),
                    dict(r, appliedSteps=[dict(r['appliedSteps'][0], mouseDx=2)])):
            self.assertIsNone(applied_label(d, f, bad))
        self.assertIsNone(applied_label(dict(d, observationTimestampMs=99.), f, r))
        self.assertIsNone(applied_label(dict(d, hybridNavigation=dict(d['hybridNavigation'], reason='obstacleRetreat')), f, r))

    def test_independent_run_ids_leases_and_source_windows(self):
        a, b = meta('a', [1, 100]), meta('b', [101, 200])
        distinct([a, b])
        for key in ('runId', 'lease', 'evidenceSha256'):
            with self.assertRaises(ValueError):
                distinct([a, dict(b, **{key: a[key]})])
        with self.assertRaisesRegex(ValueError, 'overlap'):
            distinct([a, dict(b, sourceInterval100ns=[100, 190])])

    def test_fit_save_reload_and_score_separate_archive_without_input_access(self):
        def sample(yaw, label):
            f, goal, raw = observation(yaw), (0., -1.), [dict(keys=[], mouseDx=0, mouseDy=0)]
            return features(f, goal, raw), CLASSES.index(label), f, goal, raw
        samples = [sample(90, 'forward'), sample(115, 'turnLeft'), sample(65, 'turnRight')]
        fitted = fit([Run(meta('a', [1, 100]), samples)])
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'head.json'
            p.write_text(json.dumps(fitted.checkpoint), encoding='utf-8')
            head = SteeringHead.load(p)
            self.assertEqual(head.checkpoint_id, hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertEqual(evaluate(head, Run(meta('b', [101, 200]), samples))['learned']['balancedAccuracy'], 1)
            with self.assertRaises(ValueError):
                evaluate(head, Run(meta('a', [1, 100]), samples))
            _, _, f, goal, raw = samples[0]
            self.assertEqual(set(head.predict(f, goal, raw)), {'actionClass', 'confidence'})
            self.assertIsNone(head.predict(dict(f, inputAvailable=False), goal, raw))
        invalid = copy.deepcopy(fitted.checkpoint)
        invalid['weights'][0][0] = float('inf')
        with self.assertRaises(ValueError):
            SteeringHead(invalid)


if __name__ == '__main__':
    unittest.main()
