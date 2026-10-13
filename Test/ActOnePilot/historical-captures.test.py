import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('historical', Path(__file__).parents[2] / 'tools/quest-pilot/plan-historical-captures.py')
historical = importlib.util.module_from_spec(spec)
spec.loader.exec_module(historical)


class HistoricalSafety(unittest.TestCase):
    def fixture(self, root, count=12):
        frames = root / 'observations/session'
        frames.mkdir(parents=True)
        (root / 'reports').mkdir()
        for frame in range(1, count + 1):
            (frames / f'frame-{frame:04}.png').write_bytes(bytes([frame % 256]))
            data = dict(session='session', frameId=frame, timestamp=10**15+frame,
                        hud={'world': frame % 2 == 0}, ocr=[])
            (frames / f'frame-{frame:04}.json').write_text(json.dumps(data))
        return frames

    def test_transitions_do_not_pin_every_frame_and_concrete_evidence_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix='BetterGI-history-test-') as directory:
            root = Path(directory)
            frames = self.fixture(root)
            (root / 'reports/session.json').write_text(json.dumps([dict(frameId=4, mission='navigation', status='failed')]))
            (root / 'reports/session.jsonl').write_text(json.dumps(dict(frameId=6, mission='navigation', status='failed'))+'\n')
            (root / 'reports/session.regression.json').write_text(json.dumps(dict(session='session', frameId=3, type='regression')))
            (frames / 'frame-0009.json').write_text('invalid')
            reference = root / 'validation.json'
            reference.write_text(json.dumps({'image': 'observations/session/frame-0002.png'}))
            result = historical.plan(root, latest=2, external_references=[reference])
            self.assertEqual({row['frame'] for row in result['retained']}, {2, 3, 6, 9, 11, 12})
            self.assertEqual(len(list(frames.glob('*.png'))), 12)
            self.assertEqual(len(list(frames.glob('*.json'))), 12)
            self.assertTrue(all(len(row['sha256']) == 64 for row in result['candidates']))

    def test_tail_byte_limit_and_missing_report_do_not_create_exemptions(self):
        with tempfile.TemporaryDirectory(prefix='BetterGI-history-test-') as directory:
            root = Path(directory)
            self.fixture(root)
            result = historical.plan(root, latest=256, tail_bytes=2)
            self.assertEqual({row['frame'] for row in result['retained']}, {11, 12})
            self.assertEqual(result['retainedBytes'], 2)

    def test_indispensable_evidence_over_cap_stops_planning(self):
        with tempfile.TemporaryDirectory(prefix='BetterGI-history-test-') as directory:
            root = Path(directory)
            frames = self.fixture(root)
            for frame in (1, 2):
                (frames / f'frame-{frame:04}.json').write_text('invalid')
            with self.assertRaisesRegex(ValueError, 'exceeds cap'):
                historical.plan(root, evidence_count=1)

    def test_identical_representative_images_are_deduplicated(self):
        with tempfile.TemporaryDirectory(prefix='BetterGI-history-test-') as directory:
            root = Path(directory)
            frames = self.fixture(root)
            (frames / 'frame-0004.png').write_bytes(b'same')
            (frames / 'frame-0006.png').write_bytes(b'same')
            (root / 'reports/session.json').write_text(json.dumps([
                dict(frameId=4, mission='navigation', status='failed'),
                dict(frameId=6, mission='questStep', status='completed', details={'result': {'step': 'completion'}})]))
            result = historical.plan(root, latest=1)
            self.assertEqual({row['frame'] for row in result['retained']}, {6, 12})


if __name__ == '__main__':
    unittest.main()
