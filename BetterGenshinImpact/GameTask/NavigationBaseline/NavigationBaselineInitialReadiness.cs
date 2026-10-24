using System;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.Runtime;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>One initial v4 no-input window; only an age-only capture rejection can request another image.</summary>
internal sealed class NavigationBaselineInitialReadiness
{
    /// <summary>Separate file-only policy identity; travel, waypoint and final policies are unchanged.</summary>
    internal const int Version = 1;
    /// <summary>Conservative per-call accounting mirrors final v2 without sharing its input-close transaction.</summary>
    internal const int MaximumWaitMs = 2000, MaximumCaptures = 32, MaximumReads = 32,
        MaximumPendingPolls = 400, MaximumPolls = 432, RetryDelayMs = 5;
    /// <summary>Same native monotonic clock as the workflow owner; no retry resets its origin.</summary>
    private readonly Func<double> _clock;
    /// <summary>Selected native pixel geometry, including the owned-capture chat limit.</summary>
    private readonly string _capturePolicy;
    /// <summary>Only this outstanding reservation can settle the current capture.</summary>
    private CaptureReservation? _reservation;
    /// <summary>Monotonic clock high-water, including every rejected header.</summary>
    private double _lastClock;
    /// <summary>The collector can run once and cannot be reused after success or failure.</summary>
    private bool _started, _finished;
    /// <summary>Bounded post-release file evidence; never an input permission or compact response field.</summary>
    internal NavigationBaselineInitialReadinessWindow Record { get; }
    /// <summary>Only valid returned pixel headers advance this floor; Pending never does.</summary>
    internal GameCaptureSourceInfo? SeenSource => Record.SeenSource;
    /// <summary>Geometry pinned by the first valid returned header, even when that image is too old.</summary>
    internal int? Width => Record.Width;
    /// <summary>Height paired with the same immutable initial header.</summary>
    internal int? Height => Record.Height;

    /// <summary>Begin after preparation, clipped to the actual workflow deadline supplied by its caller.</summary>
    internal NavigationBaselineInitialReadiness(Func<double> clock, double ownerDeadlineMs,
        int observationStart, int pollStart, string capturePolicy)
    {
        if (!NavigationBaselineCapturePolicy.IsSupported(capturePolicy))
            throw new ArgumentException("unsupported_capture_policy", nameof(capturePolicy));
        _clock = clock; _capturePolicy = capturePolicy;
        var now = clock();
        if (!double.IsFinite(now) || now < 0 || !double.IsFinite(ownerDeadlineMs) || ownerDeadlineMs < 0
            || observationStart < 0 || pollStart < 0)
            throw new InvalidOperationException("invalid_initial_readiness_clock");
        _lastClock = now;
        Record = new() { StartedAtMs = now, OwnerDeadlineAtMs = ownerDeadlineMs,
            DeadlineAtMs = Math.Min(now + MaximumWaitMs, ownerDeadlineMs),
            ObservationStart = observationStart, PollStart = pollStart };
    }

    /// <summary>Reject owner cancellation and clock regression without sampling or interpreting pixels.</summary>
    private double ReadClock(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if (_finished) throw new InvalidOperationException("initial_readiness_already_finished");
        var now = _clock();
        if (!double.IsFinite(now) || now < _lastClock)
            throw new InvalidOperationException("invalid_initial_readiness_clock");
        _lastClock = now;
        return now;
    }

    /// <summary>Cooperative bound checked before admission and after native work; blocked native calls are not preempted.</summary>
    internal double Check(CancellationToken ct)
    {
        var now = ReadClock(ct);
        if (now >= Record.DeadlineAtMs) throw new DeadlineException();
        return now;
    }

    /// <summary>Reserve before native work; setup, malformed results, null and throws keep the capture charge.</summary>
    internal CaptureReservation BeginCapture(CancellationToken ct)
    {
        Check(ct);
        if (_reservation is not null) throw new InvalidOperationException("initial_readiness_capture_unsettled");
        if (Record.CaptureCount >= MaximumCaptures) throw new InvalidOperationException("initial_readiness_capture_limit_exceeded");
        if (Record.PendingPollCount >= MaximumPendingPolls) throw new InvalidOperationException("initial_readiness_pending_poll_limit_exceeded");
        if (Record.PollCount >= MaximumPolls) throw new InvalidOperationException("initial_readiness_poll_limit_exceeded");
        var reservation = new CaptureReservation(this);
        Record.CaptureCount++; Record.PollCount++;
        _reservation = reservation;
        return reservation;
    }

    /// <summary>Only an exact outstanding reservation can refund a fully validated typed Pending result.</summary>
    private void Settle(CaptureReservation reservation, bool pending)
    {
        if (!ReferenceEquals(reservation, _reservation))
            throw new InvalidOperationException("initial_readiness_capture_already_settled");
        if (pending) { Record.CaptureCount--; Record.PendingPollCount++; }
        _reservation = null;
    }

    /// <summary>Serial call ownership only; it neither owns a Mat nor authorizes another capture after closure.</summary>
    internal sealed class CaptureReservation(NavigationBaselineInitialReadiness owner) : IDisposable
    {
        /// <summary>Settlement is permanent, including exceptional scope exit.</summary>
        private bool _settled;
        /// <summary>Ready, null and unclassified calls retain the unit charged before native work.</summary>
        internal void CompleteCapture() => Complete(false);
        /// <summary>Use only after typed, clock, epoch, high-water and geometry Pending validation.</summary>
        internal void CompletePending() => Complete(true);
        /// <summary>Reject duplicate/late settlement without touching any later call's counters.</summary>
        private void Complete(bool pending)
        {
            if (_settled) throw new InvalidOperationException("initial_readiness_capture_already_settled");
            owner.Settle(this, pending); _settled = true;
        }
        /// <summary>Idempotent conservative cleanup; an exceptional call cannot receive a Pending refund.</summary>
        public void Dispose() { if (!_settled) CompleteCapture(); }
    }

    /// <summary>Pin only valid returned pixel headers before age; a stale resize or epoch change is still terminal.</summary>
    internal void ValidateHeader(GameCaptureSourceInfo? source, int width, int height, int channels, CancellationToken ct)
    {
        var now = ReadClock(ct);
        if (NavigationBaselineRecovery.HardSourceRejection(source, now, SeenSource) is { } error)
            throw new InvalidOperationException(error);
        if (SeenSource is { } previous && source!.SourceTimestamp100ns == previous.SourceTimestamp100ns
            && source.AcquiredAtStopwatchTicks != previous.AcquiredAtStopwatchTicks)
            throw new InvalidOperationException("native_source_regressed");
        if (channels is not (3 or 4))
            throw new InvalidOperationException("unsupported_native_frame");
        ValidateDimensions(width, height);
        Record.SeenSource = source; Record.Width = width; Record.Height = height;
    }

    /// <summary>Known geometry faults are terminal for either returned pixels or unpublished metadata.</summary>
    private void ValidateDimensions(int width, int height)
    {
        if (width <= 0 || height <= 0 || width > NativeNavigationBaselineOperations.MaximumWidth
            || height > NativeNavigationBaselineOperations.MaximumHeight)
            throw new InvalidOperationException("unsupported_native_frame");
        if (Width is { } w && width != w || Height is { } h && height != h)
            throw new InvalidOperationException("native_frame_geometry_changed");
        if (_capturePolicy == NavigationBaselineCapturePolicy.TaskOwnedTimer
            && (width > NavigationBaselineCapturePolicy.MaximumChatWidth || height > NavigationBaselineCapturePolicy.MaximumChatHeight))
            throw new InvalidOperationException($"unsupported_chat_frame_geometry: {width}x{height}");
    }

    /// <summary>Validate Pending against seen pixels and fixed geometry limits without pinning or advancing source authority.</summary>
    internal void ValidatePending(GameCapturePendingReadback pending, long nowTicks)
    {
        GameCaptureReadbackConsumer.ValidatePending(pending, nowTicks, SeenSource, width: Width, height: Height);
        ValidateDimensions(pending.Width, pending.Height);
    }

    /// <summary>Only after_capture can emit the private retry signal; recognition/retention/dispatch ages stay terminal.</summary>
    internal GameCaptureSourceInfo ValidateSource(GameCaptureSourceInfo? source, string stage,
        int observationIndex, int pollIndex, CancellationToken ct)
    {
        var now = ReadClock(ct);
        if (NavigationBaselineRecovery.HardSourceRejection(source, now, SeenSource) is { } error)
            throw new InvalidOperationException(error);
        if (SeenSource is null || source != SeenSource) throw new InvalidOperationException("initial_readiness_header_missing");
        var age = NavigationBaselineTask.SourceAge(source, now);
        if (!double.IsFinite(age) || age < 0) throw new InvalidOperationException("invalid_source_age");
        if (now >= Record.DeadlineAtMs) throw new DeadlineException();
        if (stage == "after_capture")
        {
            if (Record.SourceChecks.Count >= MaximumCaptures) throw new InvalidOperationException("initial_readiness_check_capacity_exceeded");
            Record.SourceChecks.Add(new(observationIndex, pollIndex, now, age,
                age > NavigationBaselineTask.MaximumSourceAgeMs ? "source_age_discard" : "fresh_capture"));
            if (age > NavigationBaselineTask.MaximumSourceAgeMs) throw new SourceAgeException(this);
        }
        else if (age > NavigationBaselineTask.MaximumSourceAgeMs)
            throw new InvalidOperationException("native_source_unavailable_or_stale");
        return source!;
    }

    /// <summary>Collect one strict initial pose; later image/recognition errors never become another acquisition attempt.</summary>
    internal async Task<NavigationBaselineSample> ReadAsync(Func<CancellationToken, Task<NavigationBaselineSample>> read,
        Func<double, CancellationToken, Task> wait, CancellationToken ct)
    {
        if (_started) throw new InvalidOperationException("initial_readiness_already_started");
        _started = true;
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        try
        {
            deadline.CancelAfter(TimeSpan.FromMilliseconds(Record.DeadlineAtMs - Check(ct)));
            while (true)
            {
                Check(deadline.Token);
                if (Record.ReadCount >= MaximumReads) throw new InvalidOperationException("initial_readiness_read_limit_exceeded");
                Record.ReadCount++;
                try
                {
                    var sample = await read(deadline.Token).ConfigureAwait(false);
                    Check(deadline.Token);
                    if (_reservation is not null) throw new InvalidOperationException("initial_readiness_capture_unsettled");
                    if (Record.SourceChecks.Count == 0 || Record.SourceChecks[^1].Disposition != "fresh_capture"
                        || Record.SourceChecks[^1].ObservationIndex != Record.ObservationStart + Record.ReadCount - 1)
                        throw new InvalidOperationException("initial_readiness_capture_admission_missing");
                    // Disposal/read-finally time cannot turn an old sample into a successfully admitted initial pose.
                    ValidateSource(sample.Source, "returning_initial_pose", Record.ObservationStart + Record.ReadCount - 1,
                        Record.SourceChecks[^1].PollIndex, deadline.Token);
                    Record.AdmittedReadIndex = Record.ObservationStart + Record.ReadCount - 1;
                    Record.Outcome = "completed";
                    return sample;
                }
                catch (SourceAgeException error) when (ReferenceEquals(error.Owner, this))
                {
                    Record.SourceAgeDiscards++;
                    await wait(Math.Min(Check(deadline.Token) + RetryDelayMs, Record.DeadlineAtMs), deadline.Token).ConfigureAwait(false);
                }
            }
        }
        catch (OperationCanceledException error) when (!ct.IsCancellationRequested && deadline.IsCancellationRequested
            && error.CancellationToken == deadline.Token)
        {
            Record.Outcome = "failed"; Record.Error = "initial_readiness_deadline_exceeded";
            throw new DeadlineException(error);
        }
        catch (Exception error)
        {
            Record.Outcome = "failed"; Record.Error = NavigationBaselineObservationAttempt.DescribeError(error);
            throw;
        }
        finally { Record.EndedAtMs = _clock(); _finished = true; }
    }

    /// <summary>Window identity prevents another collector's signal or a generic message from granting a retry.</summary>
    internal sealed class SourceAgeException(NavigationBaselineInitialReadiness owner)
        : InvalidOperationException("initial_readiness_source_age: after_capture")
    {
        /// <summary>Exact collector whose validated header produced the interruption.</summary>
        internal NavigationBaselineInitialReadiness Owner { get; } = owner;
    }
    /// <summary>Preserve the fixed timeout code across linked cancellation and workflow exception unwrapping.</summary>
    internal sealed class DeadlineException(Exception? inner = null)
        : InvalidOperationException("initial_readiness_deadline_exceeded", inner) { }
}
