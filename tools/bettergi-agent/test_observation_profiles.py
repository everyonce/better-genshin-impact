"""CPU-only opt-in protocol/preprocessing tests; no model or game initialization."""
import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from PIL import Image
import observation_profiles as profiles
import stream_client
import test_stream_client as stream_fixtures


class ObservationProfileTests(unittest.TestCase):
    def hello(self):
        return {'observationProfile': profiles.P2P_NATIVE, 'widthLimit': 192, 'heightLimit': 192,
                'observationPreprocessing': {'source': 'native_capture', 'resize': 'fir-5.1.4-interpolation-hamming',
                                             'pixelFormat': 'rgb24', 'preserveAspectRatio': False}}

    def test_legacy_is_default_and_alone_accepts_old_server(self):
        args = stream_client.parse_arguments(['--output', 'unused.json'])
        self.assertEqual(args.observation_profile, profiles.LEGACY)
        contract = profiles.verify_hello({}, profiles.LEGACY, 'observe')
        profiles.verify_frame({'width': 2, 'height': 1, 'pixelFormat': 'rgb24'}, bytes(6), contract)
        with self.assertRaisesRegex(ValueError, 'advertise'):
            profiles.verify_hello({}, profiles.P2P_NATIVE, 'observe')

    def test_native_contract_checks_model_and_geometry_and_metadata(self):
        profiles.verify_hello(self.hello(), profiles.P2P_NATIVE, 'open-p2p')
        for model in ('gamescaling', 'unsupported'):
            with self.subTest(model=model), self.assertRaises(ValueError):
                profiles.verify_hello(self.hello(), profiles.P2P_NATIVE, model)
        for key, value in (('widthLimit', 640), ('heightLimit', 360), ('observationPreprocessing', {})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                profiles.verify_hello({**self.hello(), key: value}, profiles.P2P_NATIVE, 'observe')
        with self.assertRaises(ValueError):
            profiles.verify_hello(self.hello(), profiles.LEGACY, 'observe')

    def test_every_native_frame_must_repeat_exact_profile_and_rgb192(self):
        contract = profiles.verify_hello(self.hello(), profiles.P2P_NATIVE, 'observe')
        valid = {'observationProfile': profiles.P2P_NATIVE, 'width': 192, 'height': 192, 'pixelFormat': 'rgb24'}
        pixels = bytes(192*192*3)
        profiles.verify_frame(valid, pixels, contract)
        for key, value in (('observationProfile', None), ('observationProfile', profiles.LEGACY),
                           ('width', 191), ('height', True), ('pixelFormat', 'bgr24')):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                profiles.verify_frame({**valid, key: value}, pixels, contract)
        with self.assertRaises(ValueError):
            profiles.verify_frame(valid, pixels[:-1], contract)
        # Once a new server advertises even the legacy contract, omission on a frame is rejected.
        legacy = profiles.verify_hello({'observationProfile': profiles.LEGACY}, profiles.LEGACY, 'observe')
        with self.assertRaises(ValueError):
            profiles.verify_frame({'width': 1, 'height': 1, 'pixelFormat': 'rgb24'}, bytes(3), legacy)

    def test_native_p2p_preprocessing_is_identity_and_requires_verified_provenance(self):
        image = Image.new('RGB', (192, 192), (12, 34, 56))
        with patch.object(Image.Image, 'resize', side_effect=AssertionError('Unexpected second resize')):
            self.assertIs(profiles.prepare_p2p_image(image, profiles.P2P_NATIVE, profiles.P2P_NATIVE), image)
        for wrong, evidence in ((image, None), (image, profiles.LEGACY), (Image.new('RGB', (640, 360)), profiles.P2P_NATIVE),
                                (Image.new('L', (192, 192)), profiles.P2P_NATIVE)):
            with self.subTest(size=wrong.size, evidence=evidence), self.assertRaises(ValueError):
                profiles.prepare_p2p_image(wrong, profiles.P2P_NATIVE, evidence)

    def test_legacy_p2p_keeps_original_pillow_bilinear_bytes(self):
        image = Image.frombytes('RGB', (23, 17), bytes(i % 251 for i in range(23*17*3)))
        expected = image.resize((192, 192), Image.Resampling.BILINEAR)
        actual = profiles.prepare_p2p_image(image, profiles.LEGACY)
        self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_cli_rejects_gamescaling_native_before_model_loading(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            stream_client.parse_arguments(['--model', 'gamescaling', '--observation-profile', profiles.P2P_NATIVE, '--output', 'unused.json'])

    def test_fake_bridge_passes_verified_profile_to_policy(self):
        bridge = ProfileBridge(self.hello())
        policy = ProfilePolicy()
        code, report = stream_fixtures.CaptureQualityTests().run_episode(
            bridge, policy=policy, extra=['--observation-profile', profiles.P2P_NATIVE])
        self.assertEqual(code, 0)
        self.assertTrue(policy.verified)
        self.assertEqual(set(policy.verified), {profiles.P2P_NATIVE})
        self.assertEqual(report['observationProfile'], profiles.P2P_NATIVE)
        self.assertEqual(report['preprocessingContract']['adapterPreprocessing']['adapterResize'], 'none-verified-rgb192')

    def test_fake_bridge_frame_profile_mismatch_stops_before_inference(self):
        bridge = ProfileBridge(self.hello(), frame_profile=profiles.LEGACY)
        policy = ProfilePolicy()
        code, report = stream_fixtures.CaptureQualityTests().run_episode(
            bridge, policy=policy, extra=['--observation-profile', profiles.P2P_NATIVE, '--enable-input'])
        self.assertEqual(code, 1)
        self.assertIn('profile changed', report['streamError'])
        self.assertFalse(policy.verified)
        self.assertNotIn('action', bridge.commands)


class ProfilePolicy(stream_fixtures.FakePolicy):
    """Accept only the explicit verified profile keyword, with no tensor/image imports."""
    observation_profile = profiles.P2P_NATIVE

    def __init__(self):
        super().__init__()
        self.verified = []

    def predict(self, image, size, observation_profile=None):
        self.verified.append(observation_profile)
        return super().predict(image, size)


class ProfileBridge(stream_fixtures.ScriptedBridge):
    """Use the actual client loop with a declared192 frame stream; never open a pipe."""
    def __init__(self, hello, frame_profile=profiles.P2P_NATIVE):
        super().__init__([bytes([12, 34, 56]) * (192*192)])
        self.hello.update(hello)
        self.frame_profile = frame_profile

    def request(self, command, **kwargs):
        metadata, pixels = super().request(command, **kwargs)
        if metadata['type'] == 'frame':
            metadata.update(width=192, height=192, observationProfile=self.frame_profile)
        return metadata, pixels


if __name__ == '__main__':
    unittest.main()
