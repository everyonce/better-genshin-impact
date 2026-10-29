"""Exercise the reporting distinction on an artificial real-image miss and new image agreement."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from freeze_landmark_candidate import original_rgb
from landmark_recognizer import CLASSES, FEATURE, FORMAT, LandmarkRecognizer, signature
from report_stationary_photo_recovery import outcome


class RecoveryOutcomeTests(unittest.TestCase):
    """Current image agreement and a qualified successor handoff are independently necessary for recovery credit."""
    def setUp(self):
        templates = [dict(station=station,signature=signature(bytes([v])*(192*192*3)).tolist())
                     for station,v in zip(CLASSES,(20,160,230))]
        self.head = LandmarkRecognizer(dict(format=FORMAT,feature=FEATURE,classes=list(CLASSES),
                    deployment='checkpoint-shadow-only',prototypes=templates))
        self.switch = dict(boundaryFrameId=15,dispatchGapMs=986)

    def test_lossless_first_image_miss_then_genuine_new_agreement_and_qualified_handoff(self):
        images = []
        with tempfile.TemporaryDirectory() as temp:
            for fid,value,reason in ((12,20,'classificationMiss'),(15,160,'collected')):
                path = Path(temp)/f'{fid}.png'
                image = Image.new('RGB',(192,192),(value,)*3)
                image.save(path)
                rgb = original_rgb(path,hashlib.sha256(path.read_bytes()).hexdigest(),hashlib.sha256(image.tobytes()).hexdigest())
                images.append(dict(frameId=fid,native='stair-front',predicted=self.head.predict(rgb)['station'],outcome=reason))
        self.assertEqual(outcome(images,True,True,self.switch,False),'naturalRecoveryWithHandoff')
        self.assertEqual(outcome(images,False,True,self.switch,False),'correctedImageWithoutQualifiedHandoff')
        self.assertEqual(outcome(images,True,True,None,False),'correctedImageWithoutQualifiedHandoff')
        for changed in (dict(self.switch,dispatchGapMs=1000),dict(self.switch,boundaryFrameId=12)):
            with self.assertRaises(ValueError):
                outcome(images,True,True,changed,False)

    def test_planned_match_and_three_exhausted_misses_are_never_natural_recoveries(self):
        matched = dict(frameId=12,native='stair-front',predicted='stair-front',outcome='confirmationPending')
        collected = dict(matched,frameId=15,outcome='collected')
        miss = dict(matched,predicted='sidewalk-junction',outcome='classificationMiss')
        self.assertEqual(outcome([matched,collected],True,True,self.switch,True),'plannedConfirmation')
        self.assertEqual(outcome([miss,dict(matched,frameId=13),collected],True,True,self.switch,True),'plannedConfirmationAfterMiss')
        self.assertEqual(outcome([dict(miss,frameId=f) for f in range(12,16)],False,False,None,False),'exhaustedMisses')
        with self.assertRaises(ValueError):
            outcome([matched,collected],True,True,self.switch,False)
        with self.assertRaises(ValueError):
            outcome([dict(miss,predicted='stair-front'),collected],True,True,self.switch,False)
