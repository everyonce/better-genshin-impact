using System;
using System.Diagnostics;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Fixed v4 interruption limits and hard predicates; no movement, recognition or arbitrary retry policy.</summary>
internal static class NavigationBaselineRecovery
{
    /// <summary>At most two interruptions may acquire a recovery window during the same30-second owner.</summary>
    internal const int MaximumRecoveries = 2;
    /// <summary>Each window is also clipped to the original owner deadline.</summary>
    internal const double MaximumWaitMs = 2000;
    /// <summary>Every capture, including duplicate/barrier polls, consumes this separate bound.</summary>
    internal const int MaximumPolls = 32;
    /// <summary>No held input is present during this cooperative wait for another source.</summary>
    internal const int RetryDelayMs = 20;

    /// <summary>Check the unchanged absolute deadline on every boundary and count every actual capture admission.</summary>
    internal static void EnsureWindow(double now, double deadline, int completedPolls, bool admitCapture = false)
    {
        if (!double.IsFinite(now) || !double.IsFinite(deadline) || now < 0 || completedPolls < 0)
            throw new InvalidOperationException("invalid_recovery_window");
        if (now >= deadline) throw new InvalidOperationException("recovery_deadline_exceeded");
        if (admitCapture && completedPolls >= MaximumPolls)
            throw new InvalidOperationException("recovery_poll_limit_exceeded");
    }

    /// <summary>Classify identity and malformed clocks before age or a concurrent lease pause.</summary>
    internal static string? HardSourceRejection(GameCaptureSourceInfo? source, double now, GameCaptureSourceInfo? previous)
    {
        if (!Stopwatch.IsHighResolution || !double.IsFinite(now) || now < 0) return "invalid_source_clock";
        if (source is null || source.CaptureEpoch == Guid.Empty || source.SourceTimestamp100ns <= 0
            || source.AcquiredAtStopwatchTicks <= 0) return "invalid_native_source";
        if (previous is not null && source.CaptureEpoch != previous.CaptureEpoch) return "source_epoch_changed";
        if (source.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency > now) return "acquisition_in_future";
        return previous is not null && (source.SourceTimestamp100ns < previous.SourceTimestamp100ns
            || source.AcquiredAtStopwatchTicks < previous.AcquiredAtStopwatchTicks) ? "native_source_regressed" : null;
    }

    /// <summary>Keep all pose gates, including corridor, ahead of a recoverable positive age overrun.</summary>
    internal static string? HardPoseRejection(NavigationBaselineSample sample)
    {
        if (!double.IsFinite(sample.SourceAgeMs) || sample.SourceAgeMs < 0) return "invalid_source_age";
        return NavigationBaselineTask.PoseRejection(sample with { SourceAgeMs = 0 });
    }
}

/// <summary>Only these two evidence-backed interruptions can enter v4 recovery.</summary>
[JsonConverter(typeof(JsonStringEnumConverter))]
internal enum NavigationBaselineRecoveryCause { SourceAge, LeaseExpired }

/// <summary>Immutable, run-local release ticket; equality of values never grants another instance authority.</summary>
/// <param name="Generation">One-based pause generation, never reset by a resume.</param>
/// <param name="Cause">The first cause of this pause.</param>
/// <param name="StartedAtMs">Gate-held pause entry.</param>
/// <param name="ReleasedAtMs">Completed explicit release/cutoff, not physical game acknowledgment.</param>
/// <param name="ReleaseError">Ambiguous release evidence remains terminal even after later cleanup succeeds.</param>
internal sealed record NavigationBaselineRecoveryPause(int Generation, NavigationBaselineRecoveryCause Cause,
    double StartedAtMs, double ReleasedAtMs, string? ReleaseError);

/// <summary>A typed interruption, never synthesized by matching a generic exception message.</summary>
internal sealed class NavigationBaselineRecoveryRequired : Exception
{
    /// <summary>Explicit source-stage or input-lease trigger.</summary>
    internal NavigationBaselineRecoveryCause Cause { get; }
    /// <summary>Fixed diagnostic stage; no input authority is derived from this string.</summary>
    internal string Stage { get; }
    /// <summary>Original rejected immutable source, when observed.</summary>
    internal GameCaptureSourceInfo? ObservedSource { get; }
    /// <summary>Existing watchdog/dispatch pause, when already released.</summary>
    internal NavigationBaselineRecoveryPause? Pause { get; }
    /// <summary>Retain the exact typed origin while preserving ordinary exception reporting.</summary>
    internal NavigationBaselineRecoveryRequired(NavigationBaselineRecoveryCause cause, string stage,
        GameCaptureSourceInfo? source = null, NavigationBaselineRecoveryPause? pause = null)
        : base($"baseline_recovery_required: {cause}; stage={stage}")
    { Cause = cause; Stage = stage; ObservedSource = source; Pause = pause; }
}

/// <summary>Retain cooperative cancellation context without losing the fixed recovery deadline result code.</summary>
internal sealed class NavigationBaselineRecoveryTimeoutException(Exception inner)
    : TimeoutException("recovery_deadline_exceeded", inner)
{
}

/// <summary>File-only bounded recovery outcome; ranges join the existing complete observation/poll journals.</summary>
internal sealed class NavigationBaselineRecoveryAttempt
{
    /// <summary>The exact release ticket retained by the input owner.</summary>
    public required NavigationBaselineRecoveryPause Pause { get; init; }
    /// <summary>Current typed origin may differ from an earlier watchdog cause retained by Pause.</summary>
    public required NavigationBaselineRecoveryCause TriggerCause { get; init; }
    /// <summary>Original observed failure remains distinct from a preceding watchdog pause.</summary>
    public required string TriggerStage { get; init; }
    /// <summary>Observed rejected source, if the interruption carried one.</summary>
    public GameCaptureSourceInfo? TriggerSource { get; init; }
    /// <summary>Absolute fixed deadline, clipped to the owner deadline; retries cannot move it.</summary>
    public required double DeadlineAtMs { get; init; }
    /// <summary>Half-open existing journal ranges preserve every wait/failure without duplicating rows.</summary>
    public int ObservationStart { get; init; }
    /// <summary>Exclusive final observation offset, including rejected attempts.</summary>
    public int ObservationEnd { get; set; }
    /// <summary>First capture poll offset for this recovery.</summary>
    public int PollStart { get; init; }
    /// <summary>Exclusive final capture poll offset; all polls count toward32.</summary>
    public int PollEnd { get; set; }
    /// <summary>Actual completion/failure clock.</summary>
    public double? EndedAtMs { get; set; }
    /// <summary>Only resumed indicates a rearm; neither state is proof of route completion.</summary>
    public string Outcome { get; set; } = "waiting";
    /// <summary>Bounded failure text, also retained in the normal workflow result.</summary>
    public string? Error { get; set; }
    /// <summary>Fresh same-frame pose used at successful rearm; never a fallback pose.</summary>
    public NavigationBaselineSample? ResumedSample { get; set; }
}

/// <summary>Optional fixed baseline capability; legacy test/native implementations need no new methods.</summary>
internal interface INavigationBaselineRecoveryOperations
{
    /// <summary>Enable only after the initial anchor has passed, never during preparation/final verification.</summary>
    void EnableRecovery();
    /// <summary>Release, wait and rearm without any movement or camera command.</summary>
    Task<NavigationBaselineSample> RecoverAsync(NavigationBaselineRecoveryRequired interruption,
        double ownerDeadlineMs, CancellationToken ct);
}
