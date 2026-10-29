"""Offline gate cases for paired landmark predictions on verified station samples."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from landmark_recognizer import CLASSES, FORMAT, ROLES, metrics
from qualify_landmarks import STOPS, main, qualify


OLD, NEW = '1'*64, '2'*64


def paired(circuits=10, old_errors=(), new_errors=()):
    """Make sealed, source-joined native labels with the same shared circuit boundary as production."""
    evaluations = []
    for checkpoint, errors in ((OLD, old_errors), (NEW, new_errors)):
        visits, unique, sealed = [], {}, hashlib.sha256()
        for lap in range(circuits):
            for stop, station in enumerate(STOPS):
                fid = 4*lap + stop + 1
                predicted = CLASSES[(CLASSES.index(station)+1) % 3] if fid in errors else station
                evidence = dict(frameId=fid, captureEpoch='c'*32, segment=1, videoFrameIndex=fid-1,
                                sourceTimestamp100ns=10000*fid, rgbSha256=hashlib.sha256(str(fid).encode()).hexdigest())
                v = dict(circuit=lap+1, stop=stop, station=station, role=ROLES[stop], prediction=predicted,
                         frameId=fid, evidence=evidence)
                if fid not in unique:
                    unique[fid] = v
                    sealed.update(json.dumps(evidence, sort_keys=True).encode())
                visits.append(v)
        meta = dict(path='patrol.json', runId='a'*32, lease=['b'*32,'d'*32], captureEpoch='c'*32,
                    sourceInterval100ns=[10000, max(unique)*10000], circuits=circuits, orderedVisits=len(visits),
                    uniqueImages=len(unique), evidenceSha256=sealed.hexdigest())
        evaluations.append(dict(checkpointId=checkpoint, run=meta, visits=visits,
                                unique=metrics(list(unique.values()), CLASSES[0]), allVisits=metrics(visits, CLASSES[0]),
                                perApproach={r:metrics([v for v in visits if v['role'] == r], CLASSES[0]) for r in ROLES}))
    return dict(format=FORMAT, evaluations=evaluations)


class QualificationTests(unittest.TestCase):
    """Cover improvements, regressions, minimum support, and provenance failures."""
    def test_promotes_strict_improvement_with_shared_frames_counted_once(self):
        data = paired(old_errors=[5, 7])
        data['evaluations'].reverse()
        result = qualify(data, OLD, NEW)
        self.assertEqual((result['recommendation'], result['additionalCorrect'], result['uniqueSamples']),
                         ('use-challenger-as-observer', 2, 41))
        self.assertEqual(result['stations']['stair-front']['uniqueSamples'], 11)

    def test_small_support_ties_and_any_regressing_class_keep_existing_generation(self):
        for data, reason in [(paired(9, [3]), 'west-lamp has 9 unique samples'),
                             (paired(), 'did not improve total'),
                             (paired(old_errors=[2, 4, 6], new_errors=[3]), 'west-lamp recall regressed')]:
            with self.subTest(reason=reason):
                result = qualify(data, OLD, NEW)
                self.assertEqual(result['recommendation'], 'retain-incumbent')
                self.assertTrue(any(reason in why for why in result['failedChecks']))

    def test_rejects_unpaired_sources_labels_repeated_predictions_metrics_or_checkpoint_ids(self):
        original = paired()
        for mutate in [lambda b: b['run'].update(captureEpoch='e'*32),
                       lambda b: b['visits'][1]['evidence'].update(rgbSha256='f'*64),
                       lambda b: b['visits'][2].update(station='stair-front'),
                       lambda b: b['visits'][5].update(prediction='west-lamp'),
                       lambda b: b['unique'].update(correct=200),
                       lambda b: b['allVisits'].update(samples=41),
                       lambda b: b.update(checkpointId=OLD)]:
            with self.subTest(mutation=mutate):
                data = copy.deepcopy(original)
                mutate(data['evaluations'][1])
                with self.assertRaises(ValueError):
                    qualify(data, OLD, NEW)
        for a, b in [(OLD, OLD), (OLD, 'a'), ('0'*64, NEW)]:
            with self.assertRaises(ValueError):
                qualify(original, a, b)

    def test_malformed_cli_evidence_is_explained_and_no_existing_file_is_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'paired.json'
            p.write_text('{"format":', encoding='utf-8')
            output = Path(tmp)/'fresh.json'
            argv = ['--evaluation', str(p), '--incumbent-sha', OLD, '--challenger-sha', NEW, '--output', str(output)]
            self.assertEqual(main(argv), 2)
            result = json.loads(output.read_text())
            self.assertEqual(result['status'], 'invalid-evidence')
            self.assertEqual(result['recommendation'], 'retain-incumbent')
            self.assertEqual(result['evaluationSha256'], hashlib.sha256(p.read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):
                main(argv)


if __name__ == '__main__':
    unittest.main()
