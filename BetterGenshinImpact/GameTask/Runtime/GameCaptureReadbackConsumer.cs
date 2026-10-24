using System;
using System.Diagnostics;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.Runtime;

/// <summary>Adapt only explicitly selected polling capture; this boundary never waits, retries, or grants image authority.</summary>
internal static class GameCaptureReadbackConsumer
{
    /// <summary>Preserve the original ordinary/diagnostic calls outside PollSingleV1; transfer one returned frame to the caller.</summary>
    internal static GameCaptureAttempt Capture(IGameCapture capture, bool diagnostics, out GameCaptureCallTiming? timing)
    {
        timing = null;
        if (capture is not IGameCaptureReadback { ReadbackMode: GameCaptureReadbackMode.PollSingleV1 } readback)
        {
            var frame = diagnostics && capture is IGameCaptureDiagnostics measured
                ? measured.Capture(out timing) : capture.Capture();
            return new(frame is null ? GameCaptureAttemptOutcome.Unavailable : GameCaptureAttemptOutcome.FrameReady, frame, null);
        }
        var attempt = diagnostics ? readback.CaptureAttempt(out timing) : readback.CaptureAttempt();
        var valid = attempt.Outcome switch
        {
            GameCaptureAttemptOutcome.FrameReady => attempt.Frame is not null,
            GameCaptureAttemptOutcome.ReadbackPending => attempt.Frame is null && attempt.Pending is not null,
            GameCaptureAttemptOutcome.Unavailable => attempt.Frame is null && attempt.Pending is null,
            _ => false
        };
        if (valid)
        {
            if (attempt.Outcome == GameCaptureAttemptOutcome.ReadbackPending)
                ValidatePending(attempt.Pending!, Stopwatch.GetTimestamp());
            return attempt;
        }
        // A malformed producer cannot leak returned pixels or turn an error into a retryable pending result.
        attempt.Frame?.Dispose();
        throw new InvalidOperationException("invalid_capture_attempt");
    }

    /// <summary>Validate unpublished metadata only against existing identity; do not pin/advance accepted clocks or apply pixel age.</summary>
    internal static void ValidatePending(GameCapturePendingReadback pending, long now,
        GameCaptureSourceInfo? previous = null, Guid? expectedEpoch = null, int? width = null, int? height = null)
    {
        var source = pending.SourceInfo;
        // Reported QPC may lead first acquisition on real WGC. It remains raw and is not bounded by now here.
        if (pending.SubmissionId <= 0 || source is null || source.CaptureEpoch == Guid.Empty
            || source.SourceTimestamp100ns <= 0 || source.AcquiredAtStopwatchTicks <= 0
            || pending.SubmittedAtStopwatchTicks < source.AcquiredAtStopwatchTicks
            || pending.SubmittedAtStopwatchTicks > now || pending.Width <= 0 || pending.Height <= 0)
            throw new InvalidOperationException("invalid_pending_readback_metadata");
        if (expectedEpoch is { } epoch && source.CaptureEpoch != epoch
            || previous is not null && source.CaptureEpoch != previous.CaptureEpoch)
            throw new InvalidOperationException("source_epoch_changed");
        if (previous is not null && (source.SourceTimestamp100ns < previous.SourceTimestamp100ns
            || source.AcquiredAtStopwatchTicks < previous.AcquiredAtStopwatchTicks
            || source.SourceTimestamp100ns == previous.SourceTimestamp100ns
                && source.AcquiredAtStopwatchTicks != previous.AcquiredAtStopwatchTicks))
            throw new InvalidOperationException("native_source_regressed");
        if (width is { } w && pending.Width != w || height is { } h && pending.Height != h)
            throw new InvalidOperationException("native_frame_geometry_changed");
    }
}
