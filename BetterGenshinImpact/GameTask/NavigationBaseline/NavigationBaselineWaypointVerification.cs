using BetterGenshinImpact.Core.Capture;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Exactly one released midpoint window: three checkpoint poses plus a distinct next-leg anchor.</summary>
internal sealed class NavigationBaselineWaypointVerification
{
    /// <summary>One whole-window budget; samples and Pending outcomes never restart it.</summary>
    internal const int MaximumWaitMs = 2000, MaximumCaptures = 32, MaximumReads = 32;
    /// <summary>Same native monotonic origin as the lease release completion.</summary>
    private readonly Func<double> _clock;
    /// <summary>The selected fixed profile affects geometry only; deadlines and3+1 admission stay unchanged.</summary>
    private readonly NavigationBaselineRouteProfile _route;
    /// <summary>Validated header high-water includes sole-age discards, never Pending descriptors.</summary>
    private CaptureSourceEvidence _seen;
    /// <summary>Last sampled clock for fail-closed monotonic validation.</summary>
    private double _lastClock;
    /// <summary>Owned bounded result, detached before crossing the native boundary.</summary>
    internal NavigationBaselineWaypointRecord Record { get; }
    /// <summary>Source floor consulted by typed Pending validation.</summary>
    internal CaptureSourceEvidence SeenSource => _seen;
    /// <summary>Exactly the fourth read changes segment geometry; no sample may be reused as its anchor.</summary>
    internal bool ReadingAnchor => Record.Samples.Length == 3;
    /// <summary>Pin successful release and the original owner deadline before any waypoint capture.</summary>
    internal NavigationBaselineWaypointVerification(Func<double> clock, NavigationBaselineInputEvent release,
        double ownerDeadline, CaptureSourceEvidence lastSource, int observationStart, int pollStart, NavigationBaselineRouteProfile? route = null)
    {
        _clock = clock; _route = route ?? NavigationBaselineRouteProfile.TwoLegs; var now = clock();
        if (!double.IsFinite(now) || now < 0 || !double.IsFinite(release.RequestedAtMs)
            || !double.IsFinite(release.CompletedAtMs) || release.RequestedAtMs < 0
            || release.CompletedAtMs < release.RequestedAtMs || now < release.CompletedAtMs
            || !double.IsFinite(ownerDeadline) || release.Error is not null
            || release.Kind is not ("w_up" or "already_released")) throw new InvalidOperationException("invalid_waypoint_release");
        if (NavigationBaselineRecovery.HardSourceRejection(lastSource, now, null) is { } reason)
            throw new InvalidOperationException(reason);
        _seen = lastSource; _lastClock = now;
        Record = new() { Release = release, DeadlineAtMs = Math.Min(release.CompletedAtMs + MaximumWaitMs, ownerDeadline),
            ObservationStart = observationStart, PollStart = pollStart };
    }

    /// <summary>Check original time bound before/after all delayed operations.</summary>
    internal double Check(CancellationToken ct)
    {
        var now = ReadClock(ct);
        if (now >= Record.DeadlineAtMs) throw new TimeoutException();
        return now;
    }

    /// <summary>Malformed/regressing clocks cannot manufacture another wait interval.</summary>
    private double ReadClock(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested(); var now = _clock();
        if (!double.IsFinite(now) || now < _lastClock) throw new InvalidOperationException("invalid_waypoint_clock");
        return _lastClock = now;
    }

    /// <summary>Reserve an actual call including Pending before invoking native capture.</summary>
    internal void BeginCapture(CancellationToken ct)
    {
        Check(ct);
        if (Record.CaptureCount >= MaximumCaptures) throw new InvalidOperationException("waypoint_capture_limit_exceeded");
        Record.CaptureCount++;
    }

    /// <summary>Hard source metadata precedes positive-age classification; this never creates a movement recovery.</summary>
    internal CaptureSourceEvidence ValidateSource(CaptureSourceEvidence? source, string stage,
        NavigationBaselineObservationAttempt attempt, CancellationToken ct)
    {
        var now = ReadClock(ct);
        if (NavigationBaselineRecovery.HardSourceRejection(source, now, _seen) is { } reason)
            throw new InvalidOperationException(reason);
        _seen = source!;
        var age = NavigationBaselineTask.SourceAge(source, now);
        attempt.WaypointCheckStage = stage; attempt.WaypointCheckedAtMs = now; attempt.WaypointSourceAgeMs = age;
        if (!double.IsFinite(age) || age < 0) throw new InvalidOperationException("invalid_source_age");
        if (now >= Record.DeadlineAtMs) throw new TimeoutException();
        if (age > NavigationBaselineTask.MaximumSourceAgeMs)
        { attempt.WaypointDisposition = "source_age_discard"; throw new SourceAgeException(stage); }
        return source!;
    }

    /// <summary>Known hard pose/cluster/barrier errors remain terminal even alongside stale pixels.</summary>
    internal void ValidatePose(NavigationBaselineSample sample)
    {
        if (Record.Anchor is not null) throw new InvalidOperationException("waypoint_sample_capacity_exceeded");
        if (!ReadingAnchor)
        {
            if (sample.LegIndex != 1) throw new InvalidOperationException("route_leg_mismatch");
            if (NavigationBaselineFinalVerification.HardPrefixRejection(Record.Samples, sample,
                    _route.InitialLeg) is { } reason) throw new InvalidOperationException(reason);
        }
        else
        {
            var leg = _route.SecondLeg;
            if (sample.LegIndex != 2) throw new InvalidOperationException("route_leg_mismatch");
            if (NavigationBaselineRecovery.HardPoseRejection(sample, leg) is { } reason) throw new InvalidOperationException(reason);
            if (double.Hypot(sample.X - leg.StartX, sample.Y - leg.StartY) > 1.5)
                throw new InvalidOperationException("handoff_anchor_not_reached");
            var prior = Record.Samples[^1];
            if (!sample.Source.StrictlyNewerThan(prior.Source))
                throw new InvalidOperationException("source_not_increasing");
            if (sample.Source.GapFrom(prior.Source) < 80)
                throw new InvalidOperationException("acquisition_spacing_too_short");
        }
        if (!NavigationBaselineTask.AfterBarrier(sample.Source, Record.Release.CompletedAtMs, 80))
            throw new InvalidOperationException("waypoint_response_barrier");
    }

    /// <summary>Recheck the committed anchor without admitting it twice or reopening a failed window.</summary>
    internal void ValidatePoseForHandoff(NavigationBaselineSample sample)
    {
        if (!ReferenceEquals(sample, Record.Anchor) || Record.Samples.Length != 3)
            throw new InvalidOperationException("waypoint_anchor_identity_changed");
        if (NavigationBaselineTask.FinalRejection(Record.Samples, _route.InitialLeg) is { } reason)
            throw new InvalidOperationException(reason);
        if (NavigationBaselineTask.PoseRejection(sample, _route.SecondLeg) is { } anchorError)
            throw new InvalidOperationException(anchorError);
        if (double.Hypot(sample.X - _route.SecondLeg.StartX,
                sample.Y - _route.SecondLeg.StartY) > 1.5)
            throw new InvalidOperationException("handoff_anchor_not_reached");
    }

    /// <summary>Stage capacity before last source/target checks; commit only fixed private rows afterward.</summary>
    internal void Admit(NavigationBaselineSample sample, NavigationBaselineObservationAttempt attempt,
        Func<NavigationBaselineSample, Admission> stageRows, Action checkAvailable, CancellationToken ct)
    {
        ValidatePose(sample);
        var anchor = ReadingAnchor;
        var rows = anchor ? null : stageRows(sample);
        if (!anchor && rows is null) throw new InvalidOperationException("waypoint_admission_missing");
        var updated = anchor ? Record.Samples : new NavigationBaselineSample[Record.Samples.Length + 1];
        if (!anchor) { Record.Samples.CopyTo(updated, 0); updated[^1] = sample; }
        checkAvailable(); ValidatePose(sample);
        ValidateSource(sample.Source, "admitting_waypoint_sample", attempt, ct);
        if (anchor) Record.Anchor = sample; else Record.Samples = updated;
        attempt.WaypointDisposition = anchor ? "anchor_admitted" : "checkpoint_admitted";
        rows?.Commit(); // The anchor becomes one ordinary decision after the hold ends, never a second checkpoint row.
    }

    /// <summary>Only this collector's typed age outcomes retry; hard errors never escape as recovery tickets.</summary>
    internal async Task<NavigationBaselineSample> CollectAsync(Func<bool, CancellationToken, Task<NavigationBaselineSample>> read,
        Func<double, CancellationToken, Task> wait, CancellationToken ct)
    {
        using var bound = CancellationTokenSource.CreateLinkedTokenSource(ct);
        try
        {
            bound.CancelAfter(TimeSpan.FromMilliseconds(Record.DeadlineAtMs - Check(ct)));
            while (Record.Anchor is null)
            {
                Check(bound.Token);
                if (Record.ReadCount >= MaximumReads) throw new InvalidOperationException("waypoint_read_limit_exceeded");
                Record.ReadCount++;
                var count = Record.Samples.Length;
                try
                {
                    await read(ReadingAnchor, bound.Token).ConfigureAwait(false);
                    Check(bound.Token);
                    if (Record.Anchor is null && Record.Samples.Length != count + 1)
                        throw new InvalidOperationException("waypoint_admission_missing");
                    if (Record.Anchor is null)
                        await wait(Math.Min(_clock() + 120, Record.DeadlineAtMs), bound.Token).ConfigureAwait(false);
                }
                catch (SourceAgeException)
                {
                    if (Record.Samples.Length != count || Record.Anchor is not null)
                        throw new InvalidOperationException("waypoint_discard_after_admission");
                    Record.SourceAgeDiscards++;
                    await wait(Math.Min(_clock() + 20, Record.DeadlineAtMs), bound.Token).ConfigureAwait(false);
                }
            }
            Check(bound.Token);
            return Record.Anchor; // Only native EndWaypointHold may mark the record completed.
        }
        catch (OperationCanceledException error) when (!ct.IsCancellationRequested && bound.IsCancellationRequested
            && error.CancellationToken == bound.Token) { throw new TimeoutException(error); }
    }

    /// <summary>Reserve one checkpoint row; initial arrival and the later anchor remain ordinary workflow decisions.</summary>
    internal static Admission StageDecision(NavigationBaselineSample sample, List<NavigationBaselineDecision> decisions)
    {
        if (decisions.Count >= NavigationBaselineTask.MaximumObservations - 3)
            throw new InvalidOperationException("waypoint_decision_capacity_exceeded");
        decisions.EnsureCapacity(decisions.Count + 1);
        return new(decisions, new("waypoint_verifying", sample, null));
    }

    /// <summary>Prepared fixed list append with no user callbacks or native work after source validation.</summary>
    internal sealed class Admission(List<NavigationBaselineDecision> decisions, NavigationBaselineDecision decision)
    {
        /// <summary>Repeated commit cannot duplicate a source in the global decision journal.</summary>
        private bool _committed;
        /// <summary>Capacity was reserved before freshness admission.</summary>
        internal void Commit() { if (_committed) return; _committed = true; decisions.Add(decision); }
    }

    /// <summary>Only validated positive source age emits this retry signal.</summary>
    internal sealed class SourceAgeException(string stage) : InvalidOperationException($"waypoint_source_age: {stage}") { }
    /// <summary>Keep the fixed waypoint timeout visible through linked cancellation.</summary>
    internal sealed class TimeoutException(Exception? inner = null) : InvalidOperationException("waypoint_deadline_exceeded", inner) { }
}

/// <summary>Opt-in fixed midpoint boundary; no arbitrary route coordinates or input primitives.</summary>
internal interface INavigationBaselineWaypointOperations
{
    /// <summary>Exact immutable native/task route binding.</summary>
    string RouteProfileId { get; }
    /// <summary>Detached bounded partial evidence, including terminal failure while held off.</summary>
    NavigationBaselineWaypointRecord? WaypointRecord { get; }
    /// <summary>Release, verify3+1 and advance the fixed leg without replacing owner/input/source state.</summary>
    Task<NavigationBaselineSample> VerifyWaypointAndAdvanceAsync(double ownerDeadlineMs,
        Func<NavigationBaselineSample, NavigationBaselineWaypointVerification.Admission> stageRows, CancellationToken ct);
}
