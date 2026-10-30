"""Verify scene-only inputs and deterministic experimental feature classification without loading the GPU."""
import unittest
import numpy as np

from experiments.p2p_station_features import scene,normalize,predict
from landmark_recognizer import CLASSES


class SceneFeatureTests(unittest.TestCase):
    """HUD changes cannot masquerade as landmark features, and invalid vectors cannot receive labels."""
    def test_minimap_and_sidebar_pixels_do_not_enter_the_encoder_input(self):
        rgb=np.zeros((192,192,3),dtype=np.uint8)
        rgb[32:160,32:160]=80
        altered=rgb.copy()
        altered[:32]=255
        altered[160:]=255
        altered[:,:32]=255
        altered[:,160:]=255
        np.testing.assert_array_equal(scene(rgb),scene(altered))
        altered[64:96,64:96]=150
        self.assertFalse(np.array_equal(scene(rgb),scene(altered)))

    def test_wrong_shape_or_pixel_type_is_rejected(self):
        for rgb in (np.zeros((192,192,3)),np.zeros((128,128,3),dtype=np.uint8)):
            with self.subTest(shape=rgb.shape),self.assertRaisesRegex(ValueError,'RGB192'):
                scene(rgb)

    def test_invalid_features_do_not_create_a_prediction(self):
        for values in (np.zeros(1008),np.ones(10),np.full(1008,np.nan),np.full(1008,np.inf)):
            with self.assertRaisesRegex(ValueError,'embedding'):
                normalize(values)

    def test_class_tie_order_does_not_depend_on_training_row_order(self):
        vector=normalize(np.ones(1008))
        result=predict(vector,np.stack([vector]*3),list(reversed(CLASSES)))
        self.assertEqual(result['station'],CLASSES[0])
        self.assertEqual(result['margin'],0)

    def test_partial_or_nonfinite_bank_is_rejected(self):
        vector=normalize(np.ones(1008))
        with self.assertRaisesRegex(ValueError,'prototype bank'):
            predict(vector,np.stack([vector]*2),list(CLASSES[:2]))
        with self.assertRaisesRegex(ValueError,'prototype bank'):
            predict(vector,np.full((3,1008),np.nan),list(CLASSES))
