"""Named station photos must be lossless matches for verified, classifier-agreed arrivals."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from audit_photo_handoff import photo_proofs
from hybrid_routes import PATROL_STATIONS, STREET_PATROL_ROUTE
from landmark_recognizer import CLASSES, FEATURE, FORMAT, G4_SHA256, LandmarkRecognizer, signature
from patrol_photo_survey import PatrolPhotoSurvey, require_qualified_observer, verify_photos
from qualify_landmarks import qualify
from test_qualify_landmarks import NEW, OLD, paired
from warm_photo_requests import WarmPhotoRequests


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

    def test_starting_station_is_bound_to_the_plan_and_exact_source(self):
        """The same qualified west-lamp arrival is valid only under a matching start declaration."""
        station = 'west-lamp'
        event, frame, rgb, _, _ = self.visit(30, station, station)
        event.update(type='hybridStartVerified', frameId=30)
        for label, kwargs, expected in (('declared', dict(start_station=station), 'unrequested'),
                                        ('fixed', {}, 'sourceMismatch'),
                                        ('other', dict(start_station='sidewalk-junction'), 'sourceMismatch'),
                                        ('handoff', dict(start_station=None), 'sourceMismatch')):
            with self.subTest(label=label):
                task = PatrolPhotoSurvey(self.root/label, ['stair-front'], self.head.checkpoint_id, **kwargs)
                self.assertEqual(task.observe(event, frame, rgb)['outcome'], expected)
        task = PatrolPhotoSurvey(self.root/'stale', ['stair-front'], self.head.checkpoint_id, start_station=station)
        wrong = dict(frame, frameWorldReadiness=dict(frame['frameWorldReadiness'], sourceFrameId=27))
        self.assertEqual(task.observe(event, wrong, rgb)['outcome'], 'sourceMismatch')

    def test_stationary_attempts_preserve_original_pixels_release_and_limits(self):
        """The real collector and warm lifecycle can advance only on the required number of native RGB matches."""
        stairs, junction = 'stair-front', 'sidewalk-junction'
        visits = ((False, [stairs,junction], ['classificationMiss','collected']),
                  (True, [junction,junction], ['confirmationPending','collected']),
                  (True, [stairs,junction,junction], ['classificationMiss','confirmationPending','collected']),
                  (False, [stairs]*4, ['classificationMiss']*4))
        for case, (confirm, predictions, outcomes) in enumerate(visits):
            requests = [dict(id='a'*32, name='east', destination=junction, targets=[junction]),
                        dict(id='b'*32, name='home', destination=stairs, targets=[stairs])]
            plan = self.root/f'plan-{case}.json'
            plan.write_text(json.dumps(dict(version=2, mode='destinations', start=stairs,
                                            confirmFirstArrival=confirm, requests=requests)))
            root = self.root/f'lease-{case}'
            owner = WarmPhotoRequests(plan, root, self.head.checkpoint_id, self.root/'head.json',
                                      dict(sessionId='lease', ownerEpoch='owner'), 'run', 2)
            owner.after_native(dict(type='hybridStartVerified', frameId=1, sourceEpoch='wgc', station=stairs))
            owner.accepted('moved', 3)
            owner.receipt(dict(requestId='moved', frameId=3, appliedSteps=[{}]))
            owner.released(8, dict(type='released', serverNowMs=900, worldReadiness=dict(epoch=9,
                           reason='client_release',ready=False,sourceFrame=dict(captureEpoch='wgc'))))
            for attempt, (predicted, expected) in enumerate(zip(predictions, outcomes)):
                fid = 12 + 3*attempt
                event, frame, pixels, _, _ = self.visit(fid, junction, predicted)
                event.update(completedLegs=1, destinationOrdinal=1, requestedDestination=junction,
                             frameId=fid, arrivalFrameId=8, releaseAtMs=900, releaseEpoch=9)
                if attempt:
                    event.update(type='hybridDestinationPhotoRetry', initialEndpointFrameId=12, retryOrdinal=attempt)
                visit = owner.survey.observe(event, frame, pixels, retain_miss=True, confirm_only=owner.needs_first_view)
                event['photoSurveyVisit'] = visit
                self.assertEqual(visit['outcome'], expected)
                if expected != 'collected':
                    filename = root/requests[0]['id']/visit['retryEvidenceFile']
                    self.assertEqual(hashlib.sha256(filename.read_bytes()).hexdigest(), visit['retryEvidencePngSha256'])
                    with Image.open(filename) as image:
                        self.assertEqual(image.tobytes(), pixels)
                marker = event if attempt else dict(event, type='hybridDestinationVerified')
                if attempt == 3:
                    with self.assertRaisesRegex(RuntimeError,'three stationary retries'):
                        owner.after_native(marker)
                    self.assertEqual(owner.index, 0)
                else:
                    rows = owner.after_native(marker, event if not attempt else None)
                    if expected == 'collected':
                        self.assertEqual((rows[0]['frameId'], rows[0]['initialEndpointFrameId'],
                                          rows[0]['release']['arrivalFrameId']), (fid,12,8))
                        if confirm:
                            self.assertEqual(rows[0]['firstConfirmedFrameId'], fid-3)
                        self.assertEqual(owner.index, 1)
                    else:
                        self.assertEqual(rows, [])
                        with self.assertRaisesRegex(RuntimeError,'frame boundary'):
                            owner.require_action_frame(fid+1)
                        with patch('warm_photo_requests.time.perf_counter_ns', return_value=owner.retry_deadline_ns + 1):
                            with self.assertRaisesRegex(RuntimeError,'1500 ms'):
                                owner.check_photo_deadline()

    def test_destination_photo_requires_own_exact_completion_and_fresh_revisit(self):
        b,c='sidewalk-junction','west-lamp'
        specs=[dict(id=str(n)*32,targets=[s],destination=s) for n,s in enumerate((b,c,b),1)]
        events,sources=[],[]
        for i,(fid,station) in enumerate(((10,b),(20,c),(30,b))):
            spec=specs[i]
            task=PatrolPhotoSurvey(self.root/spec['id'],spec['targets'],self.head.checkpoint_id)
            e,f,rgb,s,_=self.visit(fid,station,station)
            e.update(warmRequestId=spec['id'],photoSurveyVisit=task.observe(e,f,rgb))
            events.append(e)
            sources.append(dict(s,decoded=station))
        report=dict(landmarkShadow=dict(sources=sources))
        done=[dict(frameId=n) for n in (10,20,30)]
        def check(plan,completed):
            return photo_proofs(self.root,report,events,plan,[10,20][:len(plan)-1],self.head,completed)
        self.assertEqual([p['frameId'] for p in check(specs[:2],done[:2])],[10,20])
        with self.assertRaisesRegex(ValueError,'reused an earlier photo'):
            check(specs,done)
        with self.assertRaisesRegex(ValueError,'Photo source differs'):
            check(specs[:2],[done[0],dict(frameId=10)])
        with self.assertRaisesRegex(ValueError,'Unfinished request already claims'):
            check(specs[:2],done[:1])
        events[1]['warmRequestId']=specs[0]['id']
        with self.assertRaisesRegex(ValueError,'journal crossed'):
            check(specs[:2],done[:2])

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
        accepted, foreign = copy.copy(self.head), copy.copy(self.head)
        accepted.checkpoint_id, foreign.checkpoint_id = NEW, OLD
        self.assertEqual(require_qualified_observer(qualification,accepted)['recommendation'],'use-challenger-as-observer')
        with self.assertRaisesRegex(ValueError,'checkpoint digest'):
            require_qualified_observer(qualification,foreign)
        evaluation.write_text(evaluation.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'qualification or checkpoint digest'):
            require_qualified_observer(qualification,accepted)
        data=paired()
        save(dict(qualify(data,OLD,NEW),recommendation='use-challenger-as-observer'))
        with self.assertRaisesRegex(ValueError,'recomputed promotion'):
            require_qualified_observer(qualification,accepted)

    def test_old_resident_can_only_admit_the_canonical_g4_and_rechecks_its_entire_qualification(self):
        """Exercise the historical function call used by an already-loaded resident during hot replacement."""
        landmarks = Path(__file__).resolve().parents[2]/'artifacts/agent/landmarks'
        checkpoint, qualification = landmarks/'gen-04.json', landmarks/'qualify-g4-fresh-10.json'
        if not (checkpoint.exists() and qualification.exists()):
            self.skipTest('requires deployed G4 and its original qualification')
        head = LandmarkRecognizer.load(checkpoint)
        self.assertEqual(head.checkpoint_id,G4_SHA256)
        actual = require_qualified_observer(qualification,head.checkpoint_id)
        self.assertEqual(actual,require_qualified_observer(qualification,head))
        self.assertEqual(actual['recommendation'],'use-challenger-as-observer')
        # A copied, embellished recommendation still fails after the genuine paired evaluation is recomputed.
        saved = json.loads(qualification.read_bytes())
        saved['additionalCorrect'] += 1
        altered = self.root/'altered.json'
        altered.write_text(json.dumps(saved))
        with self.assertRaisesRegex(ValueError,'recomputed promotion'):
            require_qualified_observer(altered,head.checkpoint_id)
        for experimental in ('4c347fc40796ccd33248982e5979273d10e6dd2afed45e8f2d5be7b8f1f7e446',
                             '99531706a59ce3e53156f0ad1a4532292e375d1ed783ba49bc82653ebce1e3c6',
                             G4_SHA256.upper(),G4_SHA256[:-1]+'0'):
            with self.subTest(digest=experimental),self.assertRaisesRegex(ValueError,'exact deployed G4'):
                require_qualified_observer(qualification,experimental)
