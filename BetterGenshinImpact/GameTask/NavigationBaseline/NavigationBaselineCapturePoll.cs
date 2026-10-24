using System;
using System.Diagnostics;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>One file-only source poll; flat run-level storage is bounded before capture is invoked.</summary>
internal sealed class NavigationBaselineCapturePoll(int observationIndex, double startedAtMs)
{
    /// <summary>Zero-based parent read index, avoiding a second nested copy of the poll records.</summary>
    public int ObservationIndex { get; } = observationIndex;
    /// <summary>Native capture entry, including a call that never returned a frame.</summary>
    public double CaptureStartedAtMs { get; } = startedAtMs;
    /// <summary>Null if capture threw or returned no frame.</summary>
    public double? CaptureReturnedAtMs { get; set; }
    /// <summary>End of capture admission or its source wait, before any pose recognition.</summary>
    public double? EndedAtMs { get; set; }
    /// <summary>Exact returned identity, retained even when validation rejects it.</summary>
    public GameCaptureSourceInfo? Source { get; set; }
    /// <summary>Equality with the preceding returned poll, independent of the last accepted pose.</summary>
    public bool? RepeatsPreviousPoll { get; private set; }
    /// <summary>The unchanged control predicate: either clock equal to the last accepted source means duplicate.</summary>
    public bool? DuplicateOfAccepted { get; private set; }
    /// <summary>Reported source time minus the real-input response threshold; null when no barrier is active.</summary>
    public double? ReportedBarrierMarginMs { get; private set; }
    /// <summary>Immutable first acquisition minus the same threshold, never renewed on a cached return.</summary>
    public double? AcquisitionBarrierMarginMs { get; private set; }
    /// <summary>Age at capture validation, using the same conservative clock as the input gate.</summary>
    public double? SourceAgeMs { get; private set; }
    /// <summary>Capturing, admitted, duplicate, response_barrier, or duplicate_and_response_barrier.</summary>
    public string Result { get; private set; } = "capturing";
    /// <summary>Exact wait request, not a claim about when Windows schedules its continuation.</summary>
    public double? WaitRequestedDeadlineMs { get; set; }
    /// <summary>Entry to the existing source wait; null for an admitted capture.</summary>
    public double? WaitStartedAtMs { get; set; }
    /// <summary>Finally clock includes a wait interrupted by cancellation or lease expiry.</summary>
    public double? WaitExitedAtMs { get; set; }
    /// <summary>Bounded original capture/validation/wait failure, without substituting a later lease reason.</summary>
    public string? Error { get; set; }

    /// <summary>Compute evidence and the existing eligibility predicates only after native source validation succeeds.</summary>
    internal void Classify(GameCaptureSourceInfo source, GameCaptureSourceInfo? previousPoll,
        GameCaptureSourceInfo? acceptedSource, double inputCompletedAtMs, double responseMs, double nowMs)
    {
        Source = source;
        RepeatsPreviousPoll = source == previousPoll;
        DuplicateOfAccepted = acceptedSource is not null &&
            (source.SourceTimestamp100ns == acceptedSource.SourceTimestamp100ns
             || source.AcquiredAtStopwatchTicks == acceptedSource.AcquiredAtStopwatchTicks);
        SourceAgeMs = NavigationBaselineTask.SourceAge(source, nowMs);
        var beforeBarrier = responseMs > 0 && !NavigationBaselineTask.AfterBarrier(source, inputCompletedAtMs, responseMs);
        if (responseMs > 0)
        {
            ReportedBarrierMarginMs = source.SourceTimestamp100ns / 10_000.0 - inputCompletedAtMs - responseMs;
            AcquisitionBarrierMarginMs = source.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency - inputCompletedAtMs - responseMs;
        }
        Result = DuplicateOfAccepted == true ? (beforeBarrier ? "duplicate_and_response_barrier" : "duplicate")
            : beforeBarrier ? "response_barrier" : "admitted";
    }
}
