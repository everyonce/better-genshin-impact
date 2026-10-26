"""Synthetic CPU checks for a diagnostic-only HUD geometry adaptation."""
import unittest

import numpy as np
from PIL import Image

from navigation_progress import NavigationProgress
from observation_profiles import LEGACY, P2P_NATIVE


def texture(shift=0):
    """Create broad synthetic minimap structure that survives severe downsampling."""
    y, x = np.mgrid[:360, :640]
    a = np.zeros((360, 640), dtype=np.uint8)
    a[6:70, 26:90] = (35 + ((x[6:70, 26:90] + shift)//8 % 2)*110
                     + (y[6:70, 26:90]//9 % 2)*65).astype(np.uint8)
    return Image.fromarray(a).convert('RGB')


def native(image):
    """Synthetic Pillow Hamming stretching is not a claim of native FIR byte parity."""
    return image.resize((192, 192), Image.Resampling.HAMMING)


def movement(tracker):
    """Provide only an inert completed software receipt; no keys are sent."""
    tracker.receipt({'requestId': 'synthetic', 'endedAtMs': 1600,
                     'appliedSteps': [{'startedAtMs': 500, 'keys': ['W']}]})


def observe(tracker, image, at=0, **kwargs):
    """Supply the explicit native contract used by the actual stream call site."""
    return tracker.observe(image, at, observation_profile=P2P_NATIVE,
                           source_size=(1920, 1080), **kwargs)


class NavigationProgressGeometryTests(unittest.TestCase):
    """Exercise diagnostic geometry with synthetic CPU pixels and inert receipts."""

    def test_restored_reference_is_exact_existing_coordinate_plane(self):
        image = native(texture())
        tracker = NavigationProgress()
        result = observe(tracker, image)
        expected = np.asarray(image.resize((640, 360), Image.Resampling.BILINEAR)
                              .convert('L').crop((26, 6, 90, 70)), dtype=np.float32)[tracker.mask]
        self.assertTrue(np.array_equal(tracker.reference, expected))
        self.assertEqual(result['state'], 'collecting')
        self.assertEqual(result['evidenceKind'], 'low-detail-hud-difference')
        self.assertFalse({'x', 'y', 'yaw', 'grounded'} & result.keys())

    def test_stationary_only_stalls_after_receipt_movement(self):
        tracker = NavigationProgress()
        image = native(texture())
        observe(tracker, image)
        self.assertEqual(observe(tracker, image, 3000)['state'], 'insufficientExecutedMovement')
        tracker.reset()
        observe(tracker, image)
        movement(tracker)
        result = observe(tracker, image, 3000)
        self.assertEqual(result['state'], 'stalled')
        self.assertEqual(result['executedMovementMs'], 1100)

    def test_shifted_map_is_moving_at_unchanged_threshold(self):
        tracker = NavigationProgress()
        observe(tracker, native(texture()))
        result = observe(tracker, native(texture(8)), 3000)
        self.assertEqual(result['state'], 'moving')
        self.assertEqual(result['differenceThreshold'], 2.0)
        self.assertGreater(result['minimapDifference'], 2.0)

    def test_model_pixels_and_object_are_unchanged(self):
        image = native(texture())
        before = image.tobytes()
        observe(NavigationProgress(), image)
        self.assertEqual(image.tobytes(), before)
        self.assertEqual(image.size, (192, 192))
        self.assertEqual(image.mode, 'RGB')


    def test_explicit_legacy_geometry_keeps_original_results(self):
        image = texture()
        self.assertEqual(NavigationProgress().observe(image, 0),
                         NavigationProgress().observe(image, 0, observation_profile=LEGACY, source_size=(1920, 1080)))

    def test_native_requires_complete_strict_source_dimensions(self):
        for size in [None, (), (1920,), (1920, 1080, 3), '1920x1080', (True, 1080),
                     (1920.0, 1080), (1920, '1080'), (0, 1080), (1920, -1), (8193, 4608)]:
            with self.subTest(size=size):
                result = NavigationProgress().observe(native(texture()), 0, observation_profile=P2P_NATIVE, source_size=size)
                self.assertEqual(result['reason'], 'invalidSourceGeometry')

    def test_unsupported_source_aspect_stays_unavailable(self):
        for size in [(640, 480), (1080, 1920), (192, 192)]:
            result = NavigationProgress().observe(native(texture()), 0, observation_profile=P2P_NATIVE, source_size=size)
            self.assertEqual(result['reason'], 'unsupportedHudAspectRatio')

    def test_native_exact_payload_and_profile_are_required(self):
        for image in [texture(), Image.new('RGB', (191, 192)), Image.new('L', (192, 192))]:
            self.assertEqual(observe(NavigationProgress(), image)['reason'], 'invalidNativePayloadGeometry')
        for profile in [None, 'native', 'cropped-rgb192']:
            self.assertEqual(NavigationProgress().observe(native(texture()), 0,
                observation_profile=profile, source_size=(1920, 1080))['reason'], 'unsupportedObservationProfile')

    def test_unlabelled_square_does_not_gain_native_admission(self):
        self.assertEqual(NavigationProgress().observe(native(texture()), 0)['reason'], 'unsupportedHudAspectRatio')

    def test_texture_cadence_and_reset_stay_exact(self):
        tracker = NavigationProgress()
        self.assertEqual(observe(tracker, Image.new('RGB', (192, 192)))['reason'], 'insufficientMinimapTexture')
        self.assertIsNone(observe(tracker, native(texture()), 199))
        self.assertEqual(observe(tracker, native(texture()), 200)['state'], 'collecting')
        tracker.reset()
        self.assertEqual(observe(tracker, native(texture()), 1)['windowMs'], 0)

    def test_original_dimension_upper_bound_is_accepted(self):
        result = NavigationProgress().observe(native(texture()), 0,
            observation_profile=P2P_NATIVE, source_size=(8192, 4608))
        self.assertEqual(result['state'], 'collecting')
