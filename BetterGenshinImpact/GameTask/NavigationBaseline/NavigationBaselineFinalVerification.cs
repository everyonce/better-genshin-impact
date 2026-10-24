using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>One terminally closed-input final window; never grants or resumes a movement lease.</summary>
internal sealed class NavigationBaselineFinalVerification
{
    /// <summary>Separate file-only policy version, independent of movement-recovery tickets.</summary>
    internal const int Version = 2;
    /// <summary>One whole-window time/capture/read ceiling; accepted samples never restart it.</summary>
    internal const int MaximumWaitMs = 2000, MaximumCaptures = 32, MaximumReads = 32, RetryDelayMs = 20;
    /// <summary>At most400 Pending refunds, derived from2000ms/nominal5ms; the unchanged real deadline may stop earlier.</summary>
    internal const int MaximumPendingPolls = MaximumWaitMs / 5;
    /// <summary>Every call reserves evidence, independently of whether it later yields pixels.</summary>
    internal const int MaximumPolls = MaximumCaptures + MaximumPendingPolls;
    /// <summary>Only one serial native invocation can hold the final window's reservation.</summary>
    private CaptureReservation? _captureReservation;
    /// <summary>Immutable selected terminal segment; omitted callers retain the original leg.</summary>
    private readonly NavigationBaselineLeg _leg;
    /// <summary>Monotonic clock supplied by the same native boundary as the input-close cutoff.</summary>
    private readonly Func<double> _clock;
    /// <summary>Only fully admitted samples contribute to the final endpoint cluster.</summary>
    private readonly List<NavigationBaselineSample> _accepted = new(3);
    /// <summary>Every valid returned header advances this high-water, including an age-discarded source.</summary>
    private GameCaptureSourceInfo _seenSource;
    /// <summary>Clock regression is terminal even while no input is permitted.</summary>
    private double _lastClock;
    /// <summary>One immutable-window, bounded file record; failure does not erase its accepted prefix.</summary>
    internal NavigationBaselineFinalVerificationWindow Record { get; }
    /// <summary>The exact existing native close barrier is never moved by retry.</summary>
    internal double ClosedAtMs => Record.ClosedAtMs;
    /// <summary>Existing validated header high-water, including age discards; Pending may compare but never advance it.</summary>
    internal GameCaptureSourceInfo SeenSource => _seenSource;
    /// <summary>Construction requires an already closed lease; native callers enforce that separately.</summary>
    internal NavigationBaselineFinalVerification(Func<double> clock, double closedAtMs, double ownerDeadlineMs,
        GameCaptureSourceInfo lastSource, int observationStart, int pollStart, NavigationBaselineLeg? leg = null)
    {
        _clock = clock; _leg = leg ?? NavigationBaselineRouteProfile.First;
        var now = clock();
        if (!double.IsFinite(now) || now < 0 || !double.IsFinite(closedAtMs) || closedAtMs < 0 || now < closedAtMs
            || !double.IsFinite(ownerDeadlineMs)) throw new InvalidOperationException("invalid_final_verification_clock");
        if (NavigationBaselineRecovery.HardSourceRejection(lastSource, now, null) is { } reason)
            throw new InvalidOperationException(reason);
        _seenSource = lastSource; _lastClock = now;
        Record = new() { ClosedAtMs = closedAtMs, StartedAtMs = now,
            DeadlineAtMs = Math.Min(closedAtMs + MaximumWaitMs, ownerDeadlineMs),
            ObservationStart = observationStart, PollStart = pollStart };
    }

    /// <summary>Check the original window after slow native work as well as before admitting more work.</summary>
    internal double Check(CancellationToken ct)
    {
        var now = ReadClock(ct);
        if (now >= Record.DeadlineAtMs) throw new TimeoutException();
        return now;
    }

    /// <summary>One sampled clock supplies both the final age and deadline checks without understating callback delay.</summary>
    private double ReadClock(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        var now = _clock();
        if (!double.IsFinite(now) || now < _lastClock) throw new InvalidOperationException("invalid_final_verification_clock");
        _lastClock = now;
        return now;
    }

    /// <summary>Reserve one total poll and conservatively charge one capture before native work; global capacity remains independent.</summary>
    internal CaptureReservation BeginCapture(CancellationToken ct)
    {
        Check(ct);
        if (_captureReservation is not null) throw new InvalidOperationException("final_verification_capture_unsettled");
        if (Record.CaptureCount >= MaximumCaptures) throw new InvalidOperationException("final_verification_capture_limit_exceeded");
        if (Record.PendingPollCount >= MaximumPendingPolls) throw new InvalidOperationException("final_verification_pending_poll_limit_exceeded");
        if (Record.PollCount >= MaximumPolls) throw new InvalidOperationException("final_verification_poll_limit_exceeded");
        var reservation = new CaptureReservation(this);
        Record.CaptureCount++; Record.PollCount++;
        _captureReservation = reservation;
        return reservation;
    }

    /// <summary>Only this exact outstanding call can settle; errors keep their conservative capture charge.</summary>
    private void SettleCapture(CaptureReservation reservation, bool validatedPending)
    {
        if (!ReferenceEquals(_captureReservation, reservation))
            throw new InvalidOperationException("final_verification_capture_already_settled");
        if (validatedPending)
        {
            Record.CaptureCount--; Record.PendingPollCount++;
        }
        _captureReservation = null;
    }

    /// <summary>One serial call's ownership, not a frame owner; Dispose conservatively settles throwing or unclassified calls.</summary>
    internal sealed class CaptureReservation(NavigationBaselineFinalVerification owner) : IDisposable
    {
        /// <summary>Exact window identity prevents a later call from refunding an earlier Ready/error reservation.</summary>
        private readonly NavigationBaselineFinalVerification _owner = owner;
        /// <summary>Settlement is final even after this object has left the native call's scope.</summary>
        private bool _settled;
        /// <summary>True until validated typed Pending explicitly returns this call's capture unit.</summary>
        internal bool CaptureCharged { get; private set; } = true;
        /// <summary>Ready, Unavailable and any unclassified outcome permanently keep the pre-call charge.</summary>
        internal void CompleteCapture() => Complete(false);
        /// <summary>Call only after existing typed-result and epoch/high-water/geometry Pending validation succeeds.</summary>
        internal void CompletePending() => Complete(true);
        /// <summary>Only the first explicit settlement may change counters; duplicate or late settlement is terminal.</summary>
        private void Complete(bool validatedPending)
        {
            if (_settled) throw new InvalidOperationException("final_verification_capture_already_settled");
            _owner.SettleCapture(this, validatedPending);
            CaptureCharged = !validatedPending; _settled = true;
        }
        /// <summary>Finally-safe and idempotent; native errors never acquire a Pending refund.</summary>
        public void Dispose()
        {
            if (!_settled) CompleteCapture();
        }
    }

    /// <summary>Known hard source predicates precede an age-only discard; a repeated stale tuple does not renew authority.</summary>
    internal GameCaptureSourceInfo ValidateSource(GameCaptureSourceInfo? source, string stage,
        NavigationBaselineObservationAttempt attempt, CancellationToken ct)
    {
        var now = ReadClock(ct);
        if (NavigationBaselineRecovery.HardSourceRejection(source, now, _seenSource) is { } reason)
            throw new InvalidOperationException(reason);
        _seenSource = source!;
        var age = NavigationBaselineTask.SourceAge(source, now);
        attempt.FinalVerificationCheckStage = stage;
        attempt.FinalVerificationCheckedAtMs = now;
        attempt.FinalVerificationSourceAgeMs = age;
        if (!double.IsFinite(age) || age < 0) throw new InvalidOperationException("invalid_source_age");
        if (now >= Record.DeadlineAtMs) throw new TimeoutException();
        if (age > NavigationBaselineTask.MaximumSourceAgeMs)
        {
            attempt.FinalVerificationDisposition = "source_age_discard";
            throw new SourceAgeException(stage);
        }
        return source!;
    }

    /// <summary>All observed non-age final predicates win over a simultaneous source-age overrun.</summary>
    internal static string? HardPrefixRejection(IReadOnlyList<NavigationBaselineSample> accepted, NavigationBaselineSample sample, NavigationBaselineLeg? leg = null)
    {
        if (NavigationBaselineRecovery.HardPoseRejection(sample, leg) is { } reason) return reason;
        if (accepted.Count >= 3) return "final_verification_sample_capacity_exceeded";
        if (NavigationBaselineTask.Geometry(sample.X, sample.Y, leg).Distance > 2) return "endpoint_not_reached";
        foreach (var previous in accepted)
        {
            if (sample.SourceEpoch != previous.SourceEpoch) return "source_epoch_changed";
            if (sample.SourceTimestamp100ns <= previous.SourceTimestamp100ns
                || sample.AcquiredAtStopwatchTicks <= previous.AcquiredAtStopwatchTicks) return "source_not_increasing";
            if (double.Hypot(sample.X - previous.X, sample.Y - previous.Y) > 1.5) return "position_spread_exceeded";
            if (NavigationBaselineTask.YawDistance(sample.YawDegrees, previous.YawDegrees) > 2) return "yaw_spread_exceeded";
        }
        if (accepted.Count > 0 && Stopwatch.GetElapsedTime(accepted[^1].AcquiredAtStopwatchTicks,
                sample.AcquiredAtStopwatchTicks).TotalMilliseconds < 80) return "acquisition_spacing_too_short";
        return null;
    }

    /// <summary>Call before age classification once recognition has supplied a candidate.</summary>
    internal void ValidatePose(NavigationBaselineSample sample)
    {
        if (HardPrefixRejection(_accepted, sample, _leg) is { } reason) throw new InvalidOperationException(reason);
        if (!NavigationBaselineTask.AfterBarrier(sample.Source, ClosedAtMs, 80))
            throw new InvalidOperationException("final_verification_response_barrier");
    }

    /// <summary>Prepare task rows without publishing them, recheck any preparation delay, then commit fixed fields/lists.</summary>
    internal void Admit(NavigationBaselineSample sample, int observationIndex, NavigationBaselineObservationAttempt attempt,
        Func<NavigationBaselineSample, Admission> stageRows, Action commitImage, Action checkAvailable, CancellationToken ct)
    {
        ValidatePose(sample);
        if (observationIndex < Record.ObservationStart || observationIndex >= Record.ObservationStart + Record.ReadCount)
            throw new InvalidOperationException("final_verification_read_identity_mismatch");
        // This fixed task callback may allocate/check capacity, but must not publish progress or mutate accepted rows.
        // All observable accepted evidence remains unchanged if preparation, availability or source checks fail.
        var rows = stageRows(sample) ?? throw new InvalidOperationException("final_verification_admission_missing");
        checkAvailable();
        ValidatePose(sample);
        ValidateSource(sample.Source, "admitting_final_sample", attempt, ct);
        // Both lists were preallocated for exactly three entries. The native image callback contains field assignments only.
        commitImage();
        _accepted.Add(sample); Record.AcceptedReadIndices.Add(observationIndex);
        attempt.FinalVerificationDisposition = "admitted";
        rows.Commit();
    }

    /// <summary>Retry only this window's typed sole-age outcomes; waits never reopen input or erase an accepted prefix.</summary>
    internal async Task CollectAsync(Func<CancellationToken, Task<NavigationBaselineSample>> read,
        Func<double, CancellationToken, Task> wait, CancellationToken ct)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        try
        {
            var now = Check(ct);
            deadline.CancelAfter(TimeSpan.FromMilliseconds(Record.DeadlineAtMs - now));
            while (_accepted.Count < 3)
            {
                Check(deadline.Token);
                if (Record.ReadCount >= MaximumReads) throw new InvalidOperationException("final_verification_read_limit_exceeded");
                Record.ReadCount++;
                var before = _accepted.Count;
                try
                {
                    await read(deadline.Token).ConfigureAwait(false);
                    Check(deadline.Token);
                    if (_accepted.Count != before + 1) throw new InvalidOperationException("final_verification_admission_missing");
                    if (_accepted.Count < 3)
                        await wait(Math.Min(_clock() + 120, Record.DeadlineAtMs), deadline.Token).ConfigureAwait(false);
                }
                catch (SourceAgeException)
                {
                    if (_accepted.Count != before) throw new InvalidOperationException("final_verification_discard_after_admission");
                    Record.SourceAgeDiscards++;
                    await wait(Math.Min(_clock() + RetryDelayMs, Record.DeadlineAtMs), deadline.Token).ConfigureAwait(false);
                }
            }
            Check(deadline.Token);
            Record.Outcome = "completed";
        }
        catch (OperationCanceledException error) when (!ct.IsCancellationRequested && deadline.IsCancellationRequested
            && error.CancellationToken == deadline.Token)
        {
            Record.Outcome = "failed"; Record.Error = "final_verification_deadline_exceeded";
            throw new TimeoutException(error);
        }
        catch (Exception error)
        {
            Record.Outcome = "failed";
            Record.Error = error is TimeoutException ? error.Message : NavigationBaselineObservationAttempt.DescribeError(error);
            throw;
        }
        finally { Record.EndedAtMs = _clock(); }
    }

    /// <summary>Prepare exactly one fixed task row and list capacity; no count, progress callback or accepted data is published.</summary>
    internal static Admission StageDecision(NavigationBaselineSample sample, List<NavigationBaselineSample> final,
        List<NavigationBaselineDecision> decisions)
    {
        if (final.Count >= 3 || decisions.Count >= NavigationBaselineTask.MaximumObservations)
            throw new InvalidOperationException("final_verification_sample_capacity_exceeded");
        var decision = new NavigationBaselineDecision("verifying", sample, null);
        final.EnsureCapacity(3); decisions.EnsureCapacity(decisions.Count + 1);
        return new Admission(final, decisions, sample, decision);
    }

    /// <summary>Prepared fixed task rows only; commit performs no allocation, callbacks, disposal or native work.</summary>
    internal sealed class Admission
    {
        /// <summary>Serial task-owned list whose capacity was reserved before freshness validation.</summary>
        private readonly List<NavigationBaselineSample> _final;
        /// <summary>Matching serial decision journal, likewise reserved before freshness validation.</summary>
        private readonly List<NavigationBaselineDecision> _decisions;
        /// <summary>Already allocated immutable sample and matching journal row.</summary>
        private readonly NavigationBaselineSample _sample;
        /// <summary>Already allocated decision; construction cannot occur after final freshness validation.</summary>
        private readonly NavigationBaselineDecision _decision;
        /// <summary>Commit remains idempotent without a second acceptance or observer callback.</summary>
        private bool _finished;
        /// <summary>Retain only private task data; preparing an admission does not change list counts.</summary>
        internal Admission(List<NavigationBaselineSample> final, List<NavigationBaselineDecision> decisions,
            NavigationBaselineSample sample, NavigationBaselineDecision decision)
        { _final = final; _decisions = decisions; _sample = sample; _decision = decision; }
        /// <summary>No allocation, callbacks or native work occurs at commit.</summary>
        internal void Commit()
        {
            if (_finished) return;
            _finished = true;
            _final.Add(_sample); _decisions.Add(_decision);
        }
    }

    /// <summary>Only validated positive source age can construct the retry signal at the native gate.</summary>
    internal sealed class SourceAgeException(string stage) : InvalidOperationException($"final_verification_source_age: {stage}")
    {
    }
    /// <summary>Preserve the final-window timeout code through an inner cancellation without changing owner cancellation.</summary>
    internal sealed class TimeoutException(Exception? inner = null) : InvalidOperationException("final_verification_deadline_exceeded", inner)
    {
    }
}

/// <summary>V4-only final evidence boundary; terminal input closure remains the native implementation's prerequisite.</summary>
internal interface INavigationBaselineFinalVerificationOperations
{
    /// <summary>Collect exactly three admitted samples or retain a partial prefix; this method cannot perform input.</summary>
    /// <param name="ownerDeadlineMs">Original fixed owner deadline, never restarted by final reads.</param>
    /// <param name="stageRows">Fixed internal row preparation only; no accepted-count mutation, progress publication or external callbacks.</param>
    /// <param name="ct">Original owner cancellation remains authoritative.</param>
    Task ReadFinalSamplesAsync(double ownerDeadlineMs,
        Func<NavigationBaselineSample, NavigationBaselineFinalVerification.Admission> stageRows, CancellationToken ct);
}
