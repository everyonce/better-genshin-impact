"""Exercise the one-pass prototype rule with synthetic source pixels and genuine v1 classifier math."""
import copy
import tempfile
from pathlib import Path
import unittest

from freeze_missed_landmark_prototypes import extend, read_pinned, sha
from landmark_recognizer import CLASSES, FEATURE, FORMAT, LandmarkRecognizer, signature


def pixels(value):
    """Build small synthetic examples in the same uncompressed RGB192 channel layout."""
    return bytes([value])*(192*192*3)


def visit(value,station,index):
    """Give each synthetic visit its own native frame key independently of appearance."""
    return pixels(value),dict(segment=1,frameId=index,station=station,runId='new',rgbSha256=sha(pixels(value)))


class MissedPrototypeTests(unittest.TestCase):
    """The old ordered bank, all G5-correct labels and unconditional same-lease exclusion are invariant."""
    def setUp(self):
        self.meta = dict(runId='new',lease=['s1','o1'],captureEpoch='cap',sourceInterval100ns=[4,100],evidenceSha256='new')
        old = dict(runId='old',lease=['s0','o0'],captureEpoch='cap',sourceInterval100ns=[1,3],evidenceSha256='old')
        rows = [dict(station=c,signature=signature(pixels(v)).tolist()) for c,v in zip(CLASSES,(0,128,255))]
        model = dict(format=FORMAT,feature=FEATURE,classes=list(CLASSES),deployment='checkpoint-shadow-only',trainingRuns=[old],prototypes=rows)
        self.head = LandmarkRecognizer(model)

    def test_first_pass_selects_only_g5_misses_and_preserves_ordered_parent_and_correct_labels(self):
        old = copy.deepcopy(self.head.data)
        sources = [visit(0,CLASSES[0],15),visit(45,CLASSES[2],25),visit(255,CLASSES[2],35)]
        candidate,rows = extend(self.head,self.meta,sources)
        self.assertEqual(self.head.data,old)
        self.assertEqual(candidate['prototypes'][:-1],old['prototypes'])
        self.assertEqual(candidate['trainingRuns'],[*old['trainingRuns'],self.meta])
        self.assertEqual([r['appendPrototype'] for r in rows],[False,True,False])
        self.assertEqual(candidate['prototypes'][-1]['evidence'],sources[1][1])
        self.assertTrue(all(r['candidateTrainingPrediction']['station']==r['station'] for r in rows))

    def test_no_misses_returns_no_candidate(self):
        candidate,rows = extend(self.head,self.meta,[visit(128,CLASSES[1],7)])
        self.assertIsNone(candidate)
        self.assertFalse(rows[0]['appendPrototype'])

    def test_conflicting_same_appearance_fails_without_issuing_or_tuning_a_candidate(self):
        with self.assertRaisesRegex(ValueError,'Training integrity failed'):
            extend(self.head,self.meta,[visit(45,CLASSES[0],7),visit(45,CLASSES[2],8)])

    def test_mismatched_sealed_input_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'input'
            path.write_bytes(b'forged')
            with self.assertRaisesRegex(ValueError,'Changed training input'):
                read_pinned(path,sha(b'sealed'))
