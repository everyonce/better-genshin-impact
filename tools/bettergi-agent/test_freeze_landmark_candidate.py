"""A replacement training image must remain distinguishable from the original live model input."""
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from freeze_landmark_candidate import original_rgb, sha


class LandmarkFreezeTests(unittest.TestCase):
    def test_rehashed_replacement_png_cannot_claim_original_station_rgb(self):
        """Changing one pixel and the PNG manifest hash cannot bypass the independently recorded RGB digest."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'stair-front-frame-925.png'
            image = Image.new('RGB',(192,192),(10,20,30))
            original = image.tobytes()
            image.save(path)
            self.assertEqual(original_rgb(path,sha(path.read_bytes()),sha(original)),original)
            image.putpixel((96,96),(10,21,30))
            image.save(path)
            with self.assertRaisesRegex(ValueError,'live RGB hash'):
                original_rgb(path,sha(path.read_bytes()),sha(original))
