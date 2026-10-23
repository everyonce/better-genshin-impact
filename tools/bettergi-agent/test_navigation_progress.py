"""Synthetic image/receipt tests for navigation evidence without game input."""
import unittest

import numpy as np
from PIL import Image

from navigation_progress import NavigationProgress


class NavigationProgressTests(unittest.TestCase):
    def image(self, shift=0, center_marker=False):
        """A textured north-up minimap with optional translation/heading-marker change."""
        pixels = np.zeros((360, 640), dtype=np.uint8)
        patch = np.random.default_rng(71).integers(30, 220, (64, 64), dtype=np.uint8)
        patch = np.roll(patch, shift, axis=0)
        if center_marker:
            patch[26:38, 26:38] = 255
        pixels[6:70, 26:90] = patch
        return Image.fromarray(pixels).convert('RGB')

    def movement(self, tracker, identity='moving', keys=('W',), steps=True):
        tracker.receipt({'requestId': identity, 'endedAtMs': 1600,
                         'appliedSteps': [{'startedAtMs': 500, 'keys': list(keys)}] if steps else []})

    def test_static_map_stalls_only_after_real_movement_and_not_proposals(self):
        tracker = NavigationProgress()
        tracker.observe(self.image(), 0)
        self.movement(tracker, steps=False)
        self.assertEqual(tracker.observe(self.image(), 3000)['state'], 'insufficientExecutedMovement')
        tracker.reset()
        tracker.observe(self.image(), 0)
        self.movement(tracker)
        self.assertEqual(tracker.observe(self.image(), 3000)['state'], 'stalled')

    def test_heading_marker_does_not_count_as_translation_but_map_shift_does(self):
        tracker = NavigationProgress()
        tracker.observe(self.image(), 0)
        self.movement(tracker)
        self.assertEqual(tracker.observe(self.image(center_marker=True), 3000)['state'], 'stalled')
        tracker.reset()
        tracker.observe(self.image(), 0)
        self.movement(tracker)
        self.assertEqual(tracker.observe(self.image(shift=2), 1000)['state'], 'moving')

    def test_duplicate_receipts_and_opposed_keys_do_not_inflate_movement(self):
        tracker = NavigationProgress()
        self.movement(tracker)
        self.movement(tracker)
        self.movement(tracker, 'opposed', ('W', 'S', 'A', 'D'))
        self.assertEqual(tracker.movement_between(600, 1500), 900)
        tracker.reset()
        self.assertEqual(tracker.movement_between(0, 5000), 0)

    def test_textureless_and_unsupported_hud_are_unavailable(self):
        tracker = NavigationProgress()
        self.assertEqual(tracker.observe(Image.new('RGB', (640, 360)), 0)['reason'], 'insufficientMinimapTexture')
        self.assertEqual(tracker.observe(Image.new('RGB', (640, 480)), 300)['reason'], 'unsupportedHudAspectRatio')


if __name__ == '__main__':
    unittest.main()
