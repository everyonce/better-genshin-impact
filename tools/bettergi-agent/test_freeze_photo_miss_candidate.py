"""Protect whole-lease exclusion and original-only supervision for a natural photo failure."""
import copy
import unittest

from freeze_photo_miss_candidate import extend_template_bank
from landmark_recognizer import CLASSES, FEATURE, FORMAT, LandmarkRecognizer, signature


class NaturalPhotoCandidateTests(unittest.TestCase):
    """A diagnostic retry or aliased capture must never become independent new training material."""
    def setUp(self):
        self.old = dict(runId='old',lease=['session0','owner0'],captureEpoch='epoch',sourceInterval100ns=[1,3],evidenceSha256='old')
        self.meta = dict(runId='new',lease=['session1','owner1'],captureEpoch='epoch',sourceInterval100ns=[4,100],evidenceSha256='new')
        self.base = dict(format=FORMAT,feature=FEATURE,classes=list(CLASSES),deployment='checkpoint-shadow-only',
            trainingRuns=[self.old],prototypes=[dict(station=station,signature=signature(bytes([value])*(192*192*3)).tolist())
                for station,value in zip(CLASSES,(0,128,255))])
        self.rows = [dict(runId='new',station=CLASSES[1],signature=signature(bytes([45])*(192*192*3)).tolist(),
            evidence=dict(frameId=7,captureEpoch='epoch',sourceTimestamp100ns=50))]

    def test_original_bank_and_whole_training_interval_remain_exact(self):
        original = copy.deepcopy(self.base)
        result = extend_template_bank(self.base,self.meta,self.rows,[7])
        self.assertEqual(self.base,original)
        self.assertEqual(result['prototypes'][:-1],original['prototypes'])
        self.assertEqual(result['trainingRuns'][-1],self.meta)
        self.assertEqual(LandmarkRecognizer(result).predict(bytes([45])*(192*192*3))['station'],CLASSES[1])

    def test_retry_or_repeated_frame_cannot_be_added(self):
        for ids in ([8],[7,7],[]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                extend_template_bank(self.base,self.meta,self.rows,ids)

    def test_duplicate_originals_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'distinct original'):
            extend_template_bank(self.base,self.meta,self.rows*2,[7])

    def test_whole_lease_alias_and_overlapping_capture_are_rejected(self):
        for change in ({'lease':self.old['lease']},{'runId':self.old['runId']},
                       {'evidenceSha256':self.old['evidenceSha256']},{'sourceInterval100ns':[3,100]}):
            metadata = dict(self.meta,**change)
            rows = copy.deepcopy(self.rows)
            rows[0]['runId'] = metadata['runId']
            with self.subTest(change=change), self.assertRaises(ValueError):
                extend_template_bank(self.base,metadata,rows,[7])

    def test_source_outside_original_lease_cannot_supply_a_label(self):
        for field,value in (('captureEpoch','another'),('sourceTimestamp100ns',101)):
            rows = copy.deepcopy(self.rows)
            rows[0]['evidence'][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,'provenance'):
                extend_template_bank(self.base,self.meta,rows,[7])

    def test_experimental_metric_cannot_enter_this_promotion_path(self):
        with self.assertRaisesRegex(ValueError,'v1 family'):
            extend_template_bank(dict(self.base,format='experimental'),self.meta,self.rows,[7])
