"""Keep source-render age separate from host capture and transport latency."""
import math


def _clock_value(value, name):
    """Reject malformed timing rather than treating an unknown age as fresh."""
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite clock value')
    return value


def observation_timestamp(frame):
    """Use the original pixels' time when known; retain legacy/backend fallback."""
    source = frame.get('sourceFrame')
    if source is None:
        return _clock_value(frame['capturedAtMs'], 'capturedAtMs')
    if not isinstance(source, dict):
        raise ValueError('sourceFrame must be an object or null')
    return _clock_value(source.get('capturedAtMs'), 'sourceFrame.capturedAtMs')


def frame_timing(frame, predict_started_ns, selected_at_ns, refresh_ms):
    """Expose both clocks so cached-frame delays cannot look like inference cost."""
    server_now = _clock_value(frame['serverNowMs'], 'serverNowMs')
    host_time = _clock_value(frame['capturedAtMs'], 'capturedAtMs')
    observed_at = observation_timestamp(frame)
    source = frame.get('sourceFrame')
    source_age = max(0, server_now-observed_at) if source is not None else None
    acquisition_delay = None
    if source is not None:
        acquired_at = _clock_value(source.get('acquiredAtMs'), 'sourceFrame.acquiredAtMs')
        acquisition_delay = max(0, acquired_at-observed_at)
    return {
        'version': 2,
        'observationTimestampKind': frame.get('sourceTimestampKind', 'source_frame')
                                    if source is not None else 'host_capture_request',
        'serverAgeAtReceiptMs': max(0, server_now-observed_at),
        'hostCaptureAgeAtReceiptMs': max(0, server_now-host_time),
        'sourceFrameAgeAtReceiptMs': source_age,
        'sourceAcquisitionDelayMs': acquisition_delay,
        'transportRoundTripMs': frame['transportRoundTripMs'],
        'clientReceiptToPredictMs': (predict_started_ns-frame['clientReceivedNs'])/1e6,
        'clientSelectionToPredictMs': (predict_started_ns-selected_at_ns)/1e6,
        'freshFrameRequestMs': refresh_ms,
    }
