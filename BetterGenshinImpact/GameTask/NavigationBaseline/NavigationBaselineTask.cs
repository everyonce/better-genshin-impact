using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Agent;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>One fixed street leg; no teleport or arbitrary route actions; only v4 permits bounded no-input timing recovery.</summary>
internal sealed class NavigationBaselineTask(INavigationBaselineOperations operations, string timingContract = NavigationBaselineTiming.V1,
    string capturePolicy = NavigationBaselineCapturePolicy.Shared)
{
    /// <summary>The reviewed first leg of the shipped Mondstadt crafting-bench route.</summary>
    internal const string ProfileId = "mondstadt-city-leg-1-v1";
    /// <summary>Shipped route bytes are checked before input; upstream changes require a new review.</summary>
    internal const string RouteSha256 = "2AB05CEA4A4B409498E381CBB32DC212AACC5604CD318779AF4CD17B766B09AA";
    /// <summary>Fixed world-coordinate anchor and endpoint; the source teleport tag is never executed.</summary>
    internal const double StartX = -867.7041015625, StartY = 2281.378173828125,
        EndX = -874.3662109375, EndY = 2274.179931640625;
    /// <summary>Whole-operation cooperative deadline, including native warmup and evidence publication.</summary>
    internal static readonly TimeSpan Timeout = TimeSpan.FromSeconds(30);
    /// <summary>Bound accepted control observations independently of the wall-clock deadline.</summary>
    internal const int MaximumObservations = 1024;
    /// <summary>Exact source-age ceiling immediately before input; no load-dependent widening.</summary>
    internal const double MaximumSourceAgeMs = 150;
    /// <summary>Finite route length in the same world-coordinate units as measured poses.</summary>
    internal static readonly double Length = double.Hypot(EndX - StartX, EndY - StartY);
    /// <summary>Accepted observations and decisions, retained after workflow failure.</summary>
    private readonly List<NavigationBaselineDecision> _decisions = [];
    /// <summary>Bounded file-only pacing outcomes, including cancellation before the next read starts.</summary>
    private readonly List<NavigationBaselineScheduleWait> _scheduleWaits = [];
    /// <summary>Last immutable outcome, readable after TaskRunner maps a cleanup failure.</summary>
    internal NavigationBaselineRunResult Result { get; private set; } = new() { TimingContract = timingContract, CapturePolicy = capturePolicy };

    /// <summary>Compute progress and cross-track error without mistaking elapsed time for route progress.</summary>
    internal static (double Distance, double Projection, double CrossTrack) Geometry(double x, double y)
    {
        var dx = EndX - StartX; var dy = EndY - StartY;
        return (double.Hypot(x - EndX, y - EndY), ((x - StartX) * dx + (y - StartY) * dy) / Length,
            Math.Abs((x - StartX) * dy - (y - StartY) * dx) / Length);
    }

    /// <summary>Shortest circular yaw distance; invalid values are rejected separately.</summary>
    internal static double YawDistance(double a, double b) => Math.Abs((a - b + 540) % 360 - 180);

    /// <summary>One strict same-frame pose with explicit negative motion evidence and corridor bounds.</summary>
    internal static string? PoseRejection(NavigationBaselineSample sample)
    {
        if (!double.IsFinite(sample.X) || !double.IsFinite(sample.Y)) return "invalid_position";
        if (!double.IsFinite(sample.YawDegrees) || sample.YawDegrees is < 0 or >= 360
            || !double.IsFinite(sample.TargetHeadingDegrees) || sample.TargetHeadingDegrees is < 0 or >= 360) return "invalid_yaw";
        if (!double.IsFinite(sample.YawConfidence) || sample.YawConfidence is < 0.2 or > 1) return "invalid_yaw_confidence";
        if (!double.IsFinite(sample.PositionConfidence) || sample.PositionConfidence is < 0.99 or > 1) return "invalid_position_confidence";
        if (sample.LayerId != "City_102") return "wrong_layer";
        if (sample.Motion is not { Status: "normal", Method: AgentMotionEvidence.MethodName, SpaceKeyMatched: false }
            || !double.IsFinite(sample.Motion.RecognitionMs) || sample.Motion.RecognitionMs < 0) return "non_normal_motion";
        if (sample.SourceEpoch == Guid.Empty || sample.SourceTimestamp100ns <= 0 || sample.AcquiredAtStopwatchTicks <= 0)
            return "invalid_native_source";
        if (!double.IsFinite(sample.SourceAgeMs) || sample.SourceAgeMs is < 0 or > MaximumSourceAgeMs) return "native_source_stale";
        var geometry = Geometry(sample.X, sample.Y);
        if (geometry.CrossTrack > 3 || geometry.Projection < -1.5 || geometry.Projection > Length + 2) return "route_corridor_exceeded";
        return null;
    }

    /// <summary>Exactly three new post-release samples establish only a stable 2D endpoint/yaw cluster.</summary>
    internal static string? FinalRejection(IReadOnlyList<NavigationBaselineSample> samples)
    {
        if (samples.Count != 3) return "sample_count_not_three";
        for (var i = 0; i < samples.Count; i++)
        {
            if (PoseRejection(samples[i]) is { } reason) return reason;
            if (Geometry(samples[i].X, samples[i].Y).Distance > 2) return "endpoint_not_reached";
            for (var j = 0; j < i; j++)
            {
                if (samples[i].SourceEpoch != samples[j].SourceEpoch) return "source_epoch_changed";
                if (samples[i].SourceTimestamp100ns <= samples[j].SourceTimestamp100ns
                    || samples[i].AcquiredAtStopwatchTicks <= samples[j].AcquiredAtStopwatchTicks) return "source_not_increasing";
                if (double.Hypot(samples[i].X - samples[j].X, samples[i].Y - samples[j].Y) > 1.5) return "position_spread_exceeded";
                if (YawDistance(samples[i].YawDegrees, samples[j].YawDegrees) > 2) return "yaw_spread_exceeded";
            }
            if (i > 0 && Stopwatch.GetElapsedTime(samples[i - 1].AcquiredAtStopwatchTicks,
                    samples[i].AcquiredAtStopwatchTicks).TotalMilliseconds < 80) return "acquisition_spacing_too_short";
        }
        return null;
    }

    /// <summary>Conservative acquisition freshness, deliberately distinct from unknown game-render age.</summary>
    internal static double SourceAge(GameCaptureSourceInfo? source, double nowMs)
    {
        if (!Stopwatch.IsHighResolution || source is null || source.CaptureEpoch == Guid.Empty
            || source.SourceTimestamp100ns <= 0 || source.AcquiredAtStopwatchTicks <= 0 || !double.IsFinite(nowMs)) return double.NaN;
        var acquired = source.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency;
        if (acquired > nowMs) return double.NaN;
        return nowMs - Math.Min(source.SourceTimestamp100ns / 10_000.0, acquired);
    }

    /// <summary>Both clocks must cross a real input response barrier; cached copies cannot move either clock.</summary>
    internal static bool AfterBarrier(GameCaptureSourceInfo source, double completedAtMs, double responseMs) =>
        source.SourceTimestamp100ns / 10_000.0 - completedAtMs >= responseMs
        && source.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency - completedAtMs >= responseMs;

    /// <summary>Run the fixed feedback loop and always close input before writing bounded evidence.</summary>
    internal async Task<NavigationBaselineRunResult> RunAsync(Action<string> phase, CancellationToken ct)
    {
        var started = operations.NowMs;
        var currentPhase = "preparing";
        NavigationBaselineSample? initial = null;
        var final = new List<NavigationBaselineSample>();
        string? error = null, releaseError = null;
        var verified = false;
        // The workflow clock measures actual call entry. Diagnostic sample fields cannot authorize cadence.
        double observationStarted = 0;
        Task<NavigationBaselineSample> ReadPoseAsync(string? retainImage)
        {
            observationStarted = operations.NowMs;
            return operations.ReadPoseAsync(retainImage, ct);
        }
        try
        {
            phase(currentPhase);
            await operations.PrepareAsync(ct);
            ct.ThrowIfCancellationRequested();
            currentPhase = "measuring_start"; phase(currentPhase);
            initial = await ReadPoseAsync("initial");
            if (PoseRejection(initial) is { } firstError) throw new InvalidOperationException(firstError);
            if (double.Hypot(initial.X - StartX, initial.Y - StartY) > 1.5) throw new InvalidOperationException("start_not_at_anchor");
            INavigationBaselineRecoveryOperations? recovery = null;
            if (timingContract == NavigationBaselineTiming.V4)
            {
                recovery = operations as INavigationBaselineRecoveryOperations
                    ?? throw new InvalidOperationException("recovery_implementation_unavailable");
                recovery.EnableRecovery();
            }
            var sample = initial;
            while (true)
            {
                try
                {
                    ct.ThrowIfCancellationRequested();
                    if (_decisions.Count >= MaximumObservations - 3)
                    {
                        _decisions.Add(new(currentPhase, sample, null, "observation_capacity_exceeded"));
                        throw new InvalidOperationException("observation_capacity_exceeded");
                    }
                    if (operations.NowMs - started >= Timeout.TotalMilliseconds) throw new InvalidOperationException("baseline_deadline_exceeded");
                    if (PoseRejection(sample) is { } poseError) throw new InvalidOperationException(poseError);
                    NavigationBaselineInputEvent? intent = null;
                    if (Geometry(sample.X, sample.Y).Distance <= 1.5)
                    {
                        currentPhase = "releasing"; phase(currentPhase);
                        operations.CloseInput();
                        _decisions.Add(new(currentPhase, sample, null));
                        break;
                    }
                    if (YawDistance(sample.YawDegrees, sample.TargetHeadingDegrees) > 5)
                    {
                        currentPhase = "aligning"; phase(currentPhase);
                        // A key release is followed by a new response frame before camera alignment.
                        intent = operations.ForwardHeld ? operations.ReleaseForward() : operations.Rotate(sample, ct);
                    }
                    else
                    {
                        currentPhase = "driving"; phase(currentPhase);
                        intent = operations.Forward(sample, ct);
                    }
                    _decisions.Add(new(currentPhase, sample, intent));
                    // Recognition consumes the existing 50ms cadence budget. Anchor to each actual read
                    // start rather than advancing an old deadline, so overruns cannot create catch-up bursts.
                    if (_scheduleWaits.Count >= MaximumObservations) throw new InvalidOperationException("schedule_diagnostics_capacity_exceeded");
                    var nextObservationAt = observationStarted + 50;
                    var waitStarted = operations.NowMs;
                    string? waitError = null;
                    try { await operations.WaitUntilAsync(nextObservationAt, ct); }
                    catch (Exception exception) { waitError = NavigationBaselineObservationAttempt.DescribeError(exception); throw; }
                    finally { _scheduleWaits.Add(new(observationStarted, nextObservationAt, waitStarted, operations.NowMs, waitError)); }
                    sample = await ReadPoseAsync(null);
                }
                catch (NavigationBaselineRecoveryRequired interruption) when (recovery is not null)
                {
                    currentPhase = "recovering"; phase(currentPhase);
                    sample = await recovery.RecoverAsync(interruption, started + Timeout.TotalMilliseconds, ct);
                    // The next ordinary decision counts this source once. Rearm itself is already retained
                    // in RecoveryAttempt.ResumedSample and recovery_resume, including before cancellation.
                    // Start a new cadence from actual recovery completion, never an old pre-pause schedule.
                    observationStarted = operations.NowMs;
                }
            }
            currentPhase = "verifying"; phase(currentPhase);
            if (timingContract == NavigationBaselineTiming.V4)
            {
                // Final evidence has its own fixed no-input window, never another movement recovery ticket.
                var finalOperations = operations as INavigationBaselineFinalVerificationOperations
                    ?? throw new InvalidOperationException("final_verification_implementation_unavailable");
                await finalOperations.ReadFinalSamplesAsync(started + Timeout.TotalMilliseconds,
                    sample => NavigationBaselineFinalVerification.StageDecision(sample, final, _decisions), ct);
            }
            else
            {
                // No retries or corrective input: precisely three new observations after permanent input closure.
                for (var i = 0; i < 3; i++)
                {
                    if (i > 0) await operations.WaitUntilAsync(operations.NowMs + 120, ct);
                    var finalSample = await ReadPoseAsync("final");
                    final.Add(finalSample);
                    _decisions.Add(new(currentPhase, finalSample, null));
                    ct.ThrowIfCancellationRequested();
                }
            }
            error = FinalRejection(final);
            verified = error is null;
        }
        catch (Exception exception)
        {
            var failure = exception is NavigationBaselineRecoveryTimeoutException or NavigationBaselineFinalVerification.TimeoutException
                ? exception.Message : exception.GetBaseException().Message;
            // A concurrent watchdog fault must not hide lost evidence from the completeness gate.
            // Every non-capacity error retains the existing lease-fault/cancellation priority.
            error = timingContract == NavigationBaselineTiming.V4 && exception is not OperationCanceledException
                ? failure // A hard observed failure must not be hidden by a simultaneous lease failure.
                : failure.Contains("capacity", StringComparison.Ordinal) ? failure
                : operations.Fault ?? (exception is OperationCanceledException ? "baseline_cancelled" : failure);
        }
        finally
        {
            try { operations.CloseInput(); }
            catch (Exception exception) { error ??= exception.GetBaseException().Message; }
            releaseError = operations.ReleaseError;
        }
        if (operations.Fault is { } fault) error ??= fault;
        verified &= error is null && releaseError is null && !ct.IsCancellationRequested;
        if (ct.IsCancellationRequested) error ??= "baseline_cancelled";
        Result = new() { TimingContract = timingContract, CapturePolicy = capturePolicy, Verified = verified, Phase = verified ? "completed" : currentPhase, Error = error,
            InitialSample = initial, Samples = verified ? final.ToArray() : [], VerificationSamples = final.ToArray(),
            ObservationCount = _decisions.Count, ElapsedMs = operations.NowMs - started, InputReleaseError = releaseError };
        try
        {
            phase("publishing_evidence");
            var evidence = await operations.PublishEvidenceAsync(Result, _decisions.ToArray(), _scheduleWaits.ToArray());
            Result = Result with { Evidence = evidence, Verified = verified && evidence.Complete,
                ElapsedMs = operations.NowMs - started };
        }
        catch (Exception exception)
        {
            Result = Result with { Verified = false, Samples = [], Phase = "publishing_evidence",
                Error = error ?? $"evidence_publication_failed: {exception.GetBaseException().Message}" };
        }
        // Late native/file work cannot become a successful result after the cooperative deadline.
        if (ct.IsCancellationRequested || operations.NowMs - started >= Timeout.TotalMilliseconds)
            Result = Result with { Verified = false, Samples = [], Error = Result.Error ?? "baseline_deadline_exceeded" };
        phase(Result.Phase);
        return Result;
    }
}

/// <summary>Fixed baseline native boundary; deliberately not an arbitrary input or route interface.</summary>
internal interface INavigationBaselineOperations
{
    /// <summary>Absolute monotonic milliseconds, consistent with immutable native source clocks.</summary>
    double NowMs { get; }
    /// <summary>Whether this lease may currently hold W.</summary>
    bool ForwardHeld { get; }
    /// <summary>Latched native target/lease failure.</summary>
    string? Fault { get; }
    /// <summary>Explicit native keyup failure, distinct from a watchdog/source failure that released successfully.</summary>
    string? ReleaseError { get; }
    /// <summary>Pin assets and warm only the explicit local map before input.</summary>
    Task PrepareAsync(CancellationToken ct);
    /// <summary>Read a distinct, barrier-qualified same-frame pose; optional initial/final image retention.</summary>
    Task<NavigationBaselineSample> ReadPoseAsync(string? retainImage, CancellationToken ct);
    /// <summary>Horizontal measured-yaw correction while W is released.</summary>
    NavigationBaselineInputEvent Rotate(NavigationBaselineSample sample, CancellationToken ct);
    /// <summary>Start or renew W from a fresh pose; renewing sends no keydown.</summary>
    NavigationBaselineInputEvent Forward(NavigationBaselineSample sample, CancellationToken ct);
    /// <summary>Release W before realignment, retaining the ability to start a later valid lease.</summary>
    NavigationBaselineInputEvent ReleaseForward();
    /// <summary>Permanently close input before final verification or failure cleanup.</summary>
    void CloseInput();
    /// <summary>Short cancellation-aware waits; no long reset retry delay while W is held.</summary>
    Task WaitUntilAsync(double deadlineMs, CancellationToken ct);
    /// <summary>Publish bounded local evidence only after input is permanently closed.</summary>
    Task<NavigationBaselineEvidence> PublishEvidenceAsync(NavigationBaselineRunResult result, NavigationBaselineDecision[] decisions,
        NavigationBaselineScheduleWait[] scheduleWaits);
}
