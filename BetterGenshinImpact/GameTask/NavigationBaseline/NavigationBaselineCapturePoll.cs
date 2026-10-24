using System;
using System.Diagnostics;
using System.Text.Json.Serialization;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>One file-only source poll; flat run-level storage is bounded before capture is invoked.</summary>
internal sealed class NavigationBaselineCapturePoll(int observationIndex, double startedAtMs)
{
    /// <summary>Optional detail has its own bound; one record remains reserved for the run's final capture.</summary>
    internal const int MaximumCaptureTimings = 64;
    /// <summary>Only slow or failed captures retain internal stages; every poll still retains its original evidence.</summary>
    internal const double SlowCaptureThresholdMs = 50;
    /// <summary>Zero-based parent read index, avoiding a second nested copy of the poll records.</summary>
    public int ObservationIndex { get; } = observationIndex;
    /// <summary>V2 final-window charge only: false after validated Pending; true for Ready/null/error. Other phases omit this field.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? FinalVerificationCaptureCharged { get; set; }
    /// <summary>Initial-window reservation charge; false only after validated Pending, omitted in all other phases.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? InitialReadinessCaptureCharged { get; set; }
    /// <summary>Native capture entry, including a call that never returned a frame.</summary>
    public double CaptureStartedAtMs { get; } = startedAtMs;
    /// <summary>Null if capture threw or returned no frame.</summary>
    public double? CaptureReturnedAtMs { get; set; }
    /// <summary>End of capture admission or its source wait, before any pose recognition.</summary>
    public double? EndedAtMs { get; set; }
    /// <summary>Exact returned identity, retained even when validation rejects it.</summary>
    public GameCaptureSourceInfo? Source { get; set; }
    /// <summary>Unpublished pending submission, distinct from this poll's returned pixel source; may also describe refill after Ready.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public GameCapturePendingReadback? PendingReadback { get; private set; }
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
    /// <summary>Whether this backend supports per-invocation timing, independent of selective retention.</summary>
    public bool CaptureTimingSupported { get; set; }
    /// <summary>Eligible optional detail was omitted at its separate capacity; required poll/source evidence remains retained.</summary>
    public bool CaptureTimingOmitted { get; private set; }
    /// <summary>Invocation-local backend stages; never a shared latest capture and never input authority.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public GameCaptureCallTiming? CaptureTiming { get; private set; }

    /// <summary>Retain typed unpublished work without deriving age, duplicate, world or barrier authority.</summary>
    internal void RecordReadback(GameCaptureAttempt attempt)
    {
        PendingReadback = attempt.Pending;
        if (attempt.Outcome == GameCaptureAttemptOutcome.ReadbackPending) Result = "readback_pending";
    }

    /// <summary>Retain selected detail in finally or promote the last invocation after input closure, without double counting.</summary>
    internal void RetainTiming(GameCaptureCallTiming? timing, bool terminalFailure, ref int retainedCount,
        bool readbackPending = false)
    {
        if (timing is null || CaptureTiming is not null) return;
        var elapsed = (timing.CompletedAtTicks - timing.StartedAtTicks) * 1000.0 / timing.ClockFrequency;
        if (!terminalFailure && (timing.Outcome == "frame" || readbackPending)
            && timing.ExceptionType is null && elapsed < SlowCaptureThresholdMs) return;
        var limit = terminalFailure ? MaximumCaptureTimings : MaximumCaptureTimings - 1;
        if (retainedCount >= limit) { CaptureTimingOmitted = true; return; }
        CaptureTiming = timing;
        CaptureTimingOmitted = false;
        retainedCount++;
    }

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
