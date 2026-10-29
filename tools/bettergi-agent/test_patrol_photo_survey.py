"""Named station photos must be lossless matches for verified, classifier-agreed arrivals."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from hybrid_routes import PATROL_STATIONS, STREET_PATROL_ROUTE
from landmark_recognizer import CLASSES, FEATURE, FORMAT, LandmarkRecognizer, signature
from patrol_photo_survey import PatrolPhotoSurvey, require_qualified_observer, verify_photos
from qualify_landmarks import qualify
from test_qualify_landmarks import NEW, OLD, paired


class PhotoSurveyTests(unittest.TestCase):
    """Exercise local files and frozen predictions without a game process or input controller."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rgb = {s:Image.new('RGB',(192,192),color).tobytes() for s,color in
                    zip(CLASSES,((255,0,0),(0,255,0),(0,0,255)))}
        prototypes = [dict(station=s,signature=signature(p).tolist()) for s,p in self.rgb.items()]
        path = self.root/'head.json'
        path.write_text(json.dumps(dict(format=FORMAT,feature=FEATURE,classes=list(CLASSES),
                             deployment='checkpoint-shadow-only',prototypes=prototypes)))
        self.head = LandmarkRecognizer.load(path)

    def visit(self, fid, station, depicts):
        """Create a bound RGB source together with the frozen classifier's actual prediction."""
        rgb = self.rgb[depicts]
        p = dict(frameId=fid,atMs=fid*100,x=PATROL_STATIONS[station][0],y=PATROL_STATIONS[station][1],yawDegrees=32)
        pose = dict(p,state='valid',layerId='City_102',positionConfidence=1,yawConfidence=.8)
        source = dict(captureEpoch='wgc',timestamp100ns=fid*1000000,capturedAtMs=p['atMs'])
        frame = dict(frameId=fid,inputAvailable=True,width=192,height=192,pixelFormat='rgb24',navigationPose=pose,
                     sourceFrame=source,frameWorldReadiness=dict(ready=True,sourceFrameId=fid,sourceFrame=source),
                     motionEvidence=dict(status='normal',spaceKeyMatched=False))
        prediction = self.head.predict(rgb)
        visual = dict(frameId=fid,checkpointId=self.head.checkpoint_id,prediction=prediction,
                      rgbSha256=hashlib.sha256(rgb).hexdigest(),elapsedUs=40)
        event = dict(type='hybridEndpointVerified',samples=[dict(p,frameId=fid-2),dict(p,frameId=fid-1),p],
                     routeId=STREET_PATROL_ROUTE,station=station,endpoint=station,sourceEpoch='wgc',visualStation=visual)
        archived = dict(frameId=fid,native=station,live=prediction['station'],sourceEpoch='wgc',
                        sourceTimestamp100ns=source['timestamp100ns'],liveRgbSha256=visual['rgbSha256'],
                        liveSquaredDistance=prediction['squaredDistance'])
        return event,frame,rgb,archived,p

    def test_collect_once_with_misses_in_travel_order_and_verify_saved_pixels(self):
        targets = ['stair-front','sidewalk-junction']
        folder = self.root/'photos'
        task = PatrolPhotoSurvey(folder,targets,self.head.checkpoint_id)
        scenes = [('west-lamp','west-lamp'),('stair-front','west-lamp'),('stair-front','stair-front'),
                  ('stair-front','stair-front'),('sidewalk-junction','sidewalk-junction'),('west-lamp','west-lamp')]
        sources,poses = [],{}
        for i,(station,depicts) in enumerate(scenes, start=1):
            e,f,raw,s,p = self.visit(i*10,station,depicts)
            task.observe(e,f,raw)
            self.assertIsNone(task.observe(e,f,raw))
            sources.append(s)
            poses[p['frameId']]=p
        m=json.loads((folder/'manifest.json').read_text())
        self.assertEqual([r['outcome'] for r in m['journal']],
                         ['unrequested','classificationMiss','collected','alreadyCollected','collected'])
        self.assertEqual(task.snapshot()['collected'],targets)
        with self.assertRaises(FileExistsError):
            PatrolPhotoSurvey(folder,targets,self.head.checkpoint_id)
        report=verify_photos(folder,m,targets,sources,poses,self.head)
        self.assertTrue(report['complete'])
        self.assertEqual(report['classificationMisses'],1)
        bogus=copy.deepcopy(m)
        bogus['journal'][2]['frameId']=765
        with self.assertRaisesRegex(ValueError,'differs from native'):
            verify_photos(folder,bogus,targets,sources,poses,self.head)
        photo=folder/m['journal'][2]['file']
        Image.new('RGB',(192,192),(1,2,3)).save(photo)
        with self.assertRaisesRegex(ValueError,'PNG digest differs'):
            verify_photos(folder,m,targets,sources,poses,self.head)
        m['journal'][2]['pngSha256']=hashlib.sha256(photo.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'pixels or frozen prediction'):
            verify_photos(folder,m,targets,sources,poses,self.head)

    def test_missing_or_wrong_source_checkpoint_and_live_digest_cannot_yield_a_photo(self):
        for i,issue in enumerate(('frame','hash','wrongHead','wrongGate','wrongPose','wrongBytes','noVisual')):
            task = PatrolPhotoSurvey(self.root/str(i),['west-lamp'],self.head.checkpoint_id)
            e,f,rgb,_,_ = self.visit(20,'west-lamp','west-lamp')
            if issue=='frame': f['frameId']=21
            if issue=='hash': e['visualStation']['rgbSha256']='0'*64
            if issue=='wrongHead': e['visualStation']['checkpointId']='f'*64
            if issue=='wrongGate': f['frameWorldReadiness']['ready']=False
            if issue=='wrongPose': f['navigationPose']['x']+=5
            if issue=='wrongBytes': rgb=rgb[:-3]
            if issue=='noVisual': del e['visualStation']
            with self.subTest(issue=issue):
                self.assertEqual(task.observe(e,f,rgb)['outcome'],'sourceMismatch')
                self.assertFalse(task.snapshot()['complete'])
                self.assertEqual(list(task.output.glob('*.png')),[])
        with self.assertRaisesRegex(ValueError,'unique registered'):
            PatrolPhotoSurvey(self.root/'bad',['../west-lamp'],self.head.checkpoint_id)

    def test_recompute_qualification_and_bind_the_exact_paired_evaluation_and_checkpoint(self):
        data=paired(old_errors=[2,4])
        evaluation=self.root/'paired.json'
        qualification=self.root/'qualification.json'
        def save(result):
            evaluation.write_text(json.dumps(data))
            qualification.write_text(json.dumps(dict(result,evaluation=evaluation.name,
                                     evaluationSha256=hashlib.sha256(evaluation.read_bytes()).hexdigest())))
        save(qualify(data,OLD,NEW))
        self.assertEqual(require_qualified_observer(qualification,NEW)['recommendation'],'use-challenger-as-observer')
        with self.assertRaisesRegex(ValueError,'checkpoint digest'):
            require_qualified_observer(qualification,OLD)
        evaluation.write_text(evaluation.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'qualification or checkpoint digest'):
            require_qualified_observer(qualification,NEW)
        data=paired()
        save(dict(qualify(data,OLD,NEW),recommendation='use-challenger-as-observer'))
        with self.assertRaisesRegex(ValueError,'recomputed promotion'):
            require_qualified_observer(qualification,NEW)
