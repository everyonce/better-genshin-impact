import copy
import importlib.util
import json
from pathlib import Path
import unittest
from PIL import Image

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('full_map_position', HERE.parents[1]/'tools/quest-pilot/full_map_position.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FullMapPositionTests(unittest.TestCase):
    def setUp(self):
        self.source = json.loads((HERE/'full-map-anchor.fixture.json').read_text(encoding='utf-8-sig'))
        self.audit = json.loads((HERE/'full-map-native-anchor.fixture.json').read_text(encoding='utf-8-sig'))
        self.sha = self.audit['rows'][0]['sha256']

    def validate(self, source=None, audit=None, marker=True, sha=None, now=None):
        return module.validate(source or self.source, audit or self.audit, self.source['session'],
                               self.source['frameId'], now or self.source['timestamp'], marker, sha or self.sha)

    def test_actual_fresh_teleport_match_is_accurate_but_never_grants_gameplay_authority(self):
        r = self.validate()
        self.assertLess(abs(r['position']['x'] + 867.23413), .2)
        self.assertLess(abs(r['position']['y'] - 1992.874), .2)
        self.assertTrue(r['sourcePositionVerified'])
        self.assertFalse(r['navigationAuthorized'])

    def test_recorded_center_marker_and_uncentered_or_empty_map(self):
        with Image.open(HERE/'fixtures/full-map-player-center.png') as image:
            self.assertTrue(module.center_marker(image))
        self.assertFalse(module.center_marker(Image.new('RGB', (80,80))))
        with self.assertRaises(ValueError):
            self.validate(marker=False)

    def test_sparse_and_clustered_matches_fail_even_with_plausible_coordinates(self):
        for patch in [dict(inliers=19), dict(good=80), dict(spreadX=.1), dict(spreadY=.1), dict(position={'x':8759,'y':2115})]:
            audit = copy.deepcopy(self.audit)
            audit['rows'][0]['result'].update(patch)
            with self.assertRaises(ValueError):
                self.validate(audit=audit)

    def test_wrong_account_stale_source_and_mismatched_pixels_fail(self):
        with self.assertRaises(ValueError):
            self.validate(source=dict(self.source, ocr=[]))
        with self.assertRaises(ValueError):
            self.validate(now=self.source['timestamp']+600001)
        with self.assertRaises(ValueError):
            self.validate(sha='different')


if __name__ == '__main__':
    unittest.main()
