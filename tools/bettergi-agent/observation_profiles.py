"""Explicit stream preprocessing contracts, independent of model/GPU imports."""

LEGACY = 'legacy-area-640x360-v1'
P2P_NATIVE = 'p2p-native-hamming-192-v1'
PROFILES = (LEGACY, P2P_NATIVE)


class FrameProfileError(ValueError):
    """A received frame violates the profile negotiated with BetterGI."""


def validate_model_profile(profile, model):
    """Keep native policy pixels opt-in and reject incompatible model geometry."""
    if profile not in PROFILES:
        raise ValueError('Unsupported observation profile: ' + str(profile))
    if profile == P2P_NATIVE and model not in ('open-p2p', 'observe'):
        raise ValueError('p2p-native-hamming-192-v1 requires Open P2P or observe mode')
    return profile


def verify_hello(hello, requested, model):
    """Only the legacy default may connect to an older server without a profile declaration."""
    validate_model_profile(requested, model)
    advertised = hello.get('observationProfile')
    if advertised is None:
        if requested != LEGACY:
            raise ValueError('The bridge does not advertise the requested native observation profile')
        advertised = LEGACY
    if advertised not in PROFILES or advertised != requested:
        raise ValueError('Bridge observation profile differs from the explicit client request')
    if requested == P2P_NATIVE:
        transform = hello.get('observationPreprocessing', {})
        if (hello.get('widthLimit') != 192 or hello.get('heightLimit') != 192
                or transform.get('source') != 'native_capture'
                or transform.get('resize') != 'fir-5.1.4-interpolation-hamming'
                or transform.get('pixelFormat') != 'rgb24'
                or transform.get('preserveAspectRatio') is not False):
            raise ValueError('The native observation profile has incompatible preprocessing metadata')
    return {'profile': requested, 'serverAdvertised': 'observationProfile' in hello,
            'serverPreprocessing': hello.get('observationPreprocessing'),
            'adapterPreprocessing': p2p_preprocessing(requested) if model == 'open-p2p' else None}


def verify_frame(frame, pixels, contract):
    """Check every payload before publication/inference, including repeated frame IDs."""
    profile = contract['profile']
    advertised = frame.get('observationProfile')
    if advertised is None and not contract['serverAdvertised'] and profile == LEGACY:
        advertised = LEGACY
    if advertised != profile:
        raise FrameProfileError('Frame observation profile changed or is missing')
    width, height = frame.get('width'), frame.get('height')
    if (type(width) is not int or type(height) is not int or width <= 0 or height <= 0
            or frame.get('pixelFormat') != 'rgb24' or len(pixels) != width * height * 3):
        raise FrameProfileError('RGB payload does not match its declared profile/dimensions')
    if profile == P2P_NATIVE and (width, height) != (192, 192):
        raise FrameProfileError('Native P2P profile requires exact RGB192 payloads')


def p2p_preprocessing(profile):
    """Record pixel processing and model normalization with its runtime precision."""
    validate_model_profile(profile, 'open-p2p')
    return {'observationProfile': profile,
            'adapterResize': 'none-verified-rgb192' if profile == P2P_NATIVE else 'pillow-bilinear-192x192',
            'expectedStreamResize': 'native-fir-5.1.4-interpolation-hamming' if profile == P2P_NATIVE else 'legacy-area-cap-640x360',
            'inputType': 'rgb-uint8', 'normalization': 'uint8-to-runtime-dtype-divide-255',
            'requiresVerifiedProfile': profile == P2P_NATIVE}


def prepare_p2p_image(image, profile, verified_profile=None):
    """Avoid a second resize only after the caller verifies the native stream contract."""
    validate_model_profile(profile, 'open-p2p')
    if profile == P2P_NATIVE:
        if verified_profile != P2P_NATIVE or image.mode != 'RGB' or image.size != (192, 192):
            raise ValueError('Native P2P preprocessing requires a verified RGB192 observation')
        return image
    from PIL import Image
    return image.resize((192, 192), Image.Resampling.BILINEAR)
