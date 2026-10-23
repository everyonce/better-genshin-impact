"""Keep immutable source freshness separate from reported render and host clocks."""
import math


def _clock_value(value, name):
    """Reject malformed timing rather than treating an unknown age as fresh."""
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite clock value')
    return value


def observation_timestamp(frame):
    """Use the declared immutable source anchor; retain the legacy/backend contract."""
    source = frame.get('sourceFrame')
    if source is None:
        return _clock_value(frame['capturedAtMs'], 'capturedAtMs')
    if not isinstance(source, dict):
        raise ValueError('sourceFrame must be an object or null')
    reported_at = _clock_value(source.get('capturedAtMs'), 'sourceFrame.capturedAtMs')
    bounded_contract = ('freshnessAtMs' in source or 'freshnessClockKind' in source
                        or frame.get('sourceTimestampKind') == 'wgc_reported_compositor_qpc')
    if not bounded_contract:
        return reported_at
    acquired_at = _clock_value(source.get('acquiredAtMs'), 'sourceFrame.acquiredAtMs')
    anchor = _clock_value(source.get('freshnessAtMs'), 'sourceFrame.freshnessAtMs')
    expected_kind = 'reported_compositor_qpc' if reported_at <= acquired_at else 'first_acquisition_qpc'
    if anchor != min(reported_at, acquired_at) or source.get('freshnessClockKind') != expected_kind:
        raise ValueError('Source freshness must use the declared earlier-of-reported/first-acquisition anchor')
    return anchor


def frame_timing(frame, predict_started_ns, selected_at_ns, refresh_ms):
    """Expose both clocks so cached-frame delays cannot look like inference cost."""
    server_now = _clock_value(frame['serverNowMs'], 'serverNowMs')
    host_time = _clock_value(frame['capturedAtMs'], 'capturedAtMs')
    observed_at = observation_timestamp(frame)
    source = frame.get('sourceFrame')
    source_age = max(0, server_now-observed_at) if source is not None else None
    acquisition_delay = None
    reported_age = None
    reported_lead = None
    if source is not None:
        acquired_at = _clock_value(source.get('acquiredAtMs'), 'sourceFrame.acquiredAtMs')
        reported_at = _clock_value(source.get('capturedAtMs'), 'sourceFrame.capturedAtMs')
        if acquired_at > server_now + 0.001:
            raise ValueError('Source acquisition cannot occur after the server response')
        reported_age = server_now-reported_at
        reported_lead = max(0, reported_at-acquired_at)
        # Future reported timestamps do not establish compositor-to-acquisition latency.
        acquisition_delay = acquired_at-reported_at if reported_at <= acquired_at else None
        if reported_at > acquired_at and 'freshnessAtMs' not in source:
            raise ValueError('Future source timing requires the explicit bounded freshness contract')
    return {
        'version': 3,
        'observationTimestampKind': source.get('freshnessClockKind', frame.get('sourceTimestampKind', 'source_frame'))
                                    if source is not None else 'host_capture_request',
        'serverAgeAtReceiptMs': max(0, server_now-observed_at),
        'hostCaptureAgeAtReceiptMs': max(0, server_now-host_time),
        'sourceFrameAgeAtReceiptMs': source_age,
        'reportedSourceFrameAgeAtReceiptMs': reported_age,
        'reportedSourceLeadAtAcquisitionMs': reported_lead,
        'sourceAcquisitionDelayMs': acquisition_delay,
        'transportRoundTripMs': frame['transportRoundTripMs'],
        'clientReceiptToPredictMs': (predict_started_ns-frame['clientReceivedNs'])/1e6,
        'clientSelectionToPredictMs': (predict_started_ns-selected_at_ns)/1e6,
        'freshFrameRequestMs': refresh_ms,
    }
