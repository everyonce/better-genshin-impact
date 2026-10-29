"""Station-view export must retain traversal order and fail on missing or contradictory images."""
import json
import copy
from pathlib import Path
import tempfile
import unittest

from patrol_landmarks import PATROL_ORDER, STREET_PATROL_ROUTE, circuit_visits, indexed_frames
from audit_patrol_landmarks import live_views


class PatrolLandmarkTests(unittest.TestCase):
    """Exercise raw frame joins independently of a game, GPU or video encoder."""

    def test_live_class_disagreements_are_counted_but_misattributed_station_observations_are_rejected(self):
        sample = dict(frameId=17,atMs=100,x=-844.,y=2255.,yawDegrees=24.)
        event = dict(type='hybridStartVerified',samples=[sample],station='stair-front',routeId=STREET_PATROL_ROUTE,
                     frameId=17,sourceEpoch='wgc',visualStation=dict(checkpointId='ck',frameId=17,rgbSha256='f'*64,
                     elapsedUs=50.1,prediction={'station':'west-lamp','squaredDistance':.83}))
        f = dict(frameId=17,navigationPose=dict(sample,state='valid'),sourceFrame=dict(captureEpoch='wgc',
                 timestamp100ns=123456,capturedAtMs=100),width=192,height=192,pixelFormat='rgb24')
        rows = live_views([event],{17:f},[event],'ck','wgc')
        self.assertEqual((rows[0]['native'],rows[0]['live']),('stair-front','west-lamp'))
        for issue in ('missing','fakeJournal','wrongFrame','wrongEpoch','wrongCheckpoint','rgbHash','distance',
                      'nanDuration','unexpectedClass','wrongSize','duplicate','wrongPose'):
            e, frame = copy.deepcopy((event,f))
            v = e['visualStation']
            if issue=='missing': del e['visualStation']
            if issue=='wrongFrame': v['frameId']=18
            if issue=='wrongEpoch': frame['sourceFrame']['captureEpoch']='other'
            if issue=='wrongCheckpoint': v['checkpointId']='other'
            if issue=='rgbHash': v['rgbSha256']='not a sha256'
            if issue=='distance': v['prediction']['squaredDistance']=-1
            if issue=='nanDuration': v['elapsedUs']=float('nan')
            if issue=='unexpectedClass': v['prediction']['station']='other'
            if issue=='wrongSize': frame['height']=256
            if issue=='wrongPose': frame['navigationPose']['yawDegrees']=35
            events = [e,e] if issue=='duplicate' else [e]
            journal = [dict(e, visualStation={})] if issue=='fakeJournal' else events
            with self.subTest(issue=issue), self.assertRaises(ValueError):
                live_views(events,{17:frame},journal,'ck','wgc')

    def test_second_circuit_starts_from_previous_verified_return(self):
        circuits = [dict(endingFrameId=end, legs=[dict(toStation=s, verifiedFrameId=end-3+i)
                    for i, s in enumerate(PATROL_ORDER[1:])]) for end in (20, 50)]
        summary = dict(routeId=STREET_PATROL_ROUTE, verifiedCircuits=2, patrolCircuits=circuits)
        visits = circuit_visits(summary, 7, 2)
        self.assertEqual([v['station'] for v in visits], list(PATROL_ORDER))
        self.assertEqual([v['frameId'] for v in visits], [20, 47, 48, 49, 50])
        self.assertEqual(circuit_visits(summary, 7, 1)[0]['frameId'], 7)
        with self.assertRaisesRegex(ValueError, 'not independently verified'):
            circuit_visits(summary, 7, 3)

    def test_exact_encoded_observation_has_no_nearest_frame_fallback(self):
        source = dict(captureEpoch='wgc', timestamp100ns=12, acquiredAtMs=2, capturedAtMs=2,
                      freshnessAtMs=2, freshnessClockKind='reported_compositor_qpc')
        frame = dict(frameId=11, sourceFrame=source, capturedAtMs=3, clientReceivedNs=5, serverNowMs=4,
                     sourceTimestampKind='wgc_reported_compositor_qpc', videoQueueAccepted=True,
                     observationProfile='p2p', pixelFormat='rgb24', width=192, height=192,
                     sourceWidth=1920, sourceHeight=1080, droppedReceipts=0, navigationPose={'x': 42})
        part = dict(observationProfile='p2p', capturePollHz=20, recording={'encodedFrames': 1})
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            (directory/'observations.jsonl').write_text(json.dumps(frame)+'\n')
            (directory/'recording.json').write_text(json.dumps(dict(closed=True, complete=True, encodedFrames=1)))
            path = directory/'frames.jsonl'
            original = dict(frame, videoFrameIndex=0, videoPtsSeconds=0)
            path.write_text(json.dumps(original)+'\n')
            self.assertEqual(indexed_frames(directory, part)[0][11]['videoFrameIndex'], 0)
            for changes, error in ((dict(frameId=12), 'ambiguous_video_join'),
                                   (dict(navigationPose={'x': 43}), 'different native pose'),
                                   (dict(sourceFrame=dict(source, timestamp100ns=13)), 'video_metadata_mismatch'),
                                   (dict(videoFrameIndex=1), 'noncontiguous_video_index'),
                                   (dict(videoPtsSeconds=.5), 'video_pts_mismatch')):
                with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, error):
                    path.write_text(json.dumps(dict(original, **changes))+'\n')
                    indexed_frames(directory, part)
            path.write_text('')
            with self.assertRaisesRegex(ValueError, 'missing encoded frames'):
                indexed_frames(directory, part)
