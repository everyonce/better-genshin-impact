"""Exercise the lossless fixed-route shadow journal offline, including genuinely wrong live predictions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

import landmark_shadow_sources as archive
import run_patrol_series
import run_rdp_patrol
from hybrid_routes import PATROL_SEGMENTS, PATROL_STATIONS, STREET_PATROL_ROUTE
from stream_client import observe_station, parse_arguments


class ShadowHead:
    """Repeatable test classifier with a correct class on only one physical station."""
    checkpoint_id = 'b'*64

    def predict(self,rgb):
        return dict(station='sidewalk-junction',squaredDistance=float(rgb[0]))


class StationSourceTests(unittest.TestCase):
    """Require the same native markers, resident ownership and exact pre-encode bytes as the live observer."""
    def setUp(self):
        self.head = ShadowHead()
        self.run = '1'*32
        self.hello = dict(sessionId='2'*32,ownerEpoch='3'*32)
        self.pid,self.session = 200,7
        self.markers,self.frames,self.rows = [],[],[]
        for i,station in enumerate(['stair-front',*[b for _,b in PATROL_SEGMENTS]],1):
            x,y = PATROL_STATIONS[station]
            at = i*1000
            source = dict(captureEpoch='capture',timestamp100ns=i*100000,capturedAtMs=at)
            frame = dict(frameId=i,sourceFrame=source,width=192,height=192,pixelFormat='rgb24',
                         frameWorldReadiness=dict(ready=True,sourceFrameId=i,sourceFrame=source,epoch=i),
                         navigationPose=dict(state='valid',frameId=i,layerId='City_102',x=x,y=y,yawDegrees=65))
            native = dict(type=archive.KINDS[0] if i==1 else archive.KINDS[1],station=station,
                          samples=[dict(frameId=i,atMs=at,x=x,y=y,yawDegrees=65)],sourceEpoch='capture',routeId=STREET_PATROL_ROUTE)
            if i==1:
                native['frameId'] = i
            else:
                native.update(releaseEpoch=i,releaseAtMs=at-200)
            raw = bytes([i])*archive.RGB_BYTES
            observe_station(self.head,native,frame,raw)
            self.markers.append(native)
            self.frames.append(frame)
            self.rows.append(archive.pack(native,frame,raw,self.run,self.hello,self.pid,self.session))

    def verify(self,rows,checkpoint=None):
        """Use the production seal reader with a complete circuit and its separate native audit."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root/'frames'/'00001'
            folder.mkdir(parents=True)
            part = dict(residentRunId=self.run,hello=self.hello,hybridNavigationEvents=self.markers)
            run = dict(runId=self.run,status='completed',evidenceComplete=True,windowsSessionId=self.session,
                       segments=[dict(number=1,report='part.json',processId=self.pid)])
            (root/'run.json').write_text(json.dumps(run))
            (root/'part.json').write_text(json.dumps(part))
            (folder/'observations.jsonl').write_text('\n'.join(map(json.dumps,self.frames)))
            (folder/'events.jsonl').write_text('\n'.join(map(json.dumps,[*self.markers,*rows])))
            visits = [dict(segment=1,frameId=r['frameId'],native=r['station'],liveRgbSha256=r['rgbSha256'],
                           sourceTimestamp100ns=r['sourceTimestamp100ns'],sourceEpoch=r['captureEpoch']) for r in self.rows]
            route = dict(passed=True,routeId=STREET_PATROL_ROUTE,controllerLeases=1,verifiedCircuits=1,verifiedLegs=4,
                         landmarkShadow=dict(sources=visits))
            if checkpoint:
                # Supply deterministic codec output; execute both production classifier-loading and replay paths.
                from audit_patrol_landmarks import audit_landmarks
                frames = {f['frameId']:f for f in self.frames}
                indexes = {fid:dict(videoFrameIndex=i,videoPtsSeconds=i/20) for i,fid in enumerate(frames)}
                decoded = {i:np.full((192,192,3),fid,dtype=np.uint8) for i,fid in enumerate(frames)}
                with patch('audit_patrol_landmarks.indexed_frames',return_value=(indexes,len(frames))),patch('audit_patrol_landmarks.decode',return_value=decoded):
                    route['landmarkShadow'] = audit_landmarks(run,[part],self.markers,frames,folder.parent,'capture',checkpoint,'ffmpeg','ffprobe')
                self.assertEqual(route['landmarkShadow']['liveVsDecodedMatches'],len(frames))
                return archive.verify_archive(root/'run.json',folder.parent,checkpoint,route,root)
            with patch('weighted_landmark_recognizer.load_landmark_shadow',return_value=self.head):
                return archive.verify_archive(root/'run.json',folder.parent,'checkpoint',route,root)

    def test_frozen_g7_shadow_predictions_replay_from_both_sparse_sources(self):
        """One synthetic circuit goes through the live observer, decoded verifier and original-RGB verifier."""
        from weighted_landmark_recognizer import load_landmark_shadow
        checkpoint = Path(__file__).resolve().parents[2]/'artifacts/agent/landmarks/g7-half-color-frozen/gen-07.json'
        if not checkpoint.exists():
            self.skipTest('requires frozen G7 checkpoint')
        head = load_landmark_shadow(checkpoint)
        for i,(native,frame) in enumerate(zip(self.markers,self.frames)):
            pixels = bytes([frame['frameId']])*archive.RGB_BYTES
            observe_station(head,native,frame,pixels)
            self.rows[i] = archive.pack(native,frame,pixels,self.run,self.hello,self.pid,self.session)
        result = self.verify(self.rows,checkpoint)
        self.assertEqual((result['sourceCount'],result['checkpointId']),(5,head.checkpoint_id))

    def test_keeps_all_stations_even_when_the_live_prediction_is_wrong(self):
        result = self.verify(self.rows)
        self.assertEqual(result['sourceCount'],5)
        source = result['sources'][0]
        self.assertEqual((source['station'],source['prediction']['station']),('stair-front','sidewalk-junction'))
        self.assertNotIn('rgb24Base64',source)

    def test_rejects_tampered_pixels_foreign_owner_shifted_frame_and_missing_or_duplicate_source(self):
        for field,value in [('rgb24Base64',self.rows[1]['rgb24Base64']),('ownerEpoch','foreign'),('frameId',2),
                            ('childProcessId',35),('windowsSessionId',9),('sourceTimestamp100ns',9),('readinessEpoch',9)]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.verify([dict(self.rows[0],**{field:value}),*self.rows[1:]])
        for rows in (self.rows[:-1],[self.rows[0],*self.rows]):
            with self.assertRaises(ValueError):
                self.verify(rows)

    def test_rejects_a_replayed_prediction_with_an_altered_live_label(self):
        self.markers[0]['visualStation']['prediction']['station'] = 'stair-front'
        with self.assertRaisesRegex(ValueError,'replay prediction'):
            self.verify(self.rows)

    def test_series_flag_is_opt_in_and_changes_only_evidence_capture(self):
        base = ['--batches','1','--circuits','10','--landmark-shadow','station.json']
        ordinary = run_patrol_series.options(base)
        enabled = run_patrol_series.options(base+['--retain-station-rgb'])
        expected = run_rdp_patrol.patrol_argv(ordinary,self.session,Path.cwd())
        observed = run_rdp_patrol.patrol_argv(enabled,self.session,Path.cwd())
        self.assertEqual(expected,[s for s in observed if s!='--retain-station-rgb'])
        self.assertTrue(parse_arguments(observed[5:]).retain_station_rgb)

    def test_rejects_unrelated_source_pose_or_readiness_at_capture(self):
        for name in ('frameWorldReadiness','navigationPose'):
            frame = copy.deepcopy(self.frames[0])
            if name=='navigationPose':
                frame[name]['x'] += 1
            else:
                frame[name]['sourceFrameId'] += 1
            with self.assertRaises(ValueError):
                archive.pack(self.markers[0],frame,bytes([1])*archive.RGB_BYTES,self.run,self.hello,self.pid,self.session)

    def test_a_bad_shadow_binding_records_an_evidence_error_without_interrupting_control(self):
        recorder = Mock()
        archive.retain(recorder,self.markers[0],{},b'',self.run,self.hello,self.pid,self.session)
        event = recorder.event.call_args.args[0]
        self.assertEqual(event['type'],'landmarkShadowSourceRejected')
        with self.assertRaisesRegex(ValueError,'rejected at capture'):
            self.verify([*self.rows,event])
