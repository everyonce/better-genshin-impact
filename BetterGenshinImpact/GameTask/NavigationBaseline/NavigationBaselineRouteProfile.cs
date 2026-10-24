using System;
using System.Linq;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Only two reviewed built-in routes; no caller coordinates, scripts or route actions.</summary>
internal sealed class NavigationBaselineRouteProfile
{
    /// <summary>Explicit continuation selection; omission retains the original single leg.</summary>
    internal const string TwoLegId = "mondstadt-city-two-legs-v1";
    /// <summary>Immutable shipped first leg, also used by all legacy static predicates.</summary>
    internal static readonly NavigationBaselineLeg First = new(1, 1, 2,
        NavigationBaselineTask.StartX, NavigationBaselineTask.StartY, NavigationBaselineTask.EndX, NavigationBaselineTask.EndY);
    /// <summary>Second walk-only segment of the same hash-pinned asset.</summary>
    internal static readonly NavigationBaselineLeg Second = new(2, 2, 3,
        NavigationBaselineTask.EndX, NavigationBaselineTask.EndY, -886.1494140625, 2263.282958984375);
    /// <summary>One shared immutable profile instance for the unchanged default.</summary>
    internal static readonly NavigationBaselineRouteProfile Single = new(NavigationBaselineTask.ProfileId, false);
    /// <summary>One explicit two-leg profile, requiring the existing v4/owned-timer contracts.</summary>
    internal static readonly NavigationBaselineRouteProfile TwoLegs = new(TwoLegId, true);
    /// <summary>Exact wire and evidence identity.</summary>
    internal string Id { get; }
    /// <summary>Whether one nonterminal waypoint is required.</summary>
    internal bool IsTwoLeg { get; }
    /// <summary>Fixed number of segments, never supplied by a caller.</summary>
    internal int Count => IsTwoLeg ? 2 : 1;
    /// <summary>Final immutable geometry selected without mutating global constants.</summary>
    internal NavigationBaselineLeg FinalLeg => IsTwoLeg ? Second : First;
    /// <summary>Construction stays private so equivalent unreviewed geometry cannot enter native execution.</summary>
    private NavigationBaselineRouteProfile(string id, bool twoLeg) { Id = id; IsTwoLeg = twoLeg; }
    /// <summary>Exact supported identities only; explicit null is rejected by the wire validator.</summary>
    internal static bool IsSupported(string? id) => id is NavigationBaselineTask.ProfileId or TwoLegId;
    /// <summary>Resolve before ownership/native acquisition and enforce the independent selected contracts.</summary>
    internal static NavigationBaselineRouteProfile Resolve(string id, string timing, string capture)
    {
        if (!IsSupported(id)) throw new ArgumentException("unsupported_route_profile", nameof(id));
        if (id == TwoLegId && (timing != NavigationBaselineTiming.V4 || capture != NavigationBaselineCapturePolicy.TaskOwnedTimer))
            throw new ArgumentException("two_leg_requires_v4_task_owned_timer");
        return id == TwoLegId ? TwoLegs : Single;
    }

    /// <summary>Owner rechecks the bounded intermediate record independently of a workflow success flag.</summary>
    internal static bool VerifiedContinuation(NavigationBaselineRunResult result)
    {
        if (result.ProfileId == NavigationBaselineTask.ProfileId) return result.Waypoint is null && result.Legs.Length == 0;
        if (result.ProfileId != TwoLegId || result.RouteVersion != 1 || result.TimingContract != NavigationBaselineTiming.V4
            || result.CapturePolicy != NavigationBaselineCapturePolicy.TaskOwnedTimer || result.InitialSample is null
            || result.Waypoint is not { Outcome: "completed", Error: null, Anchor: not null, EndedAtMs: not null } point
            || result.Legs.Length != 2 || result.Legs.Any(leg => leg.Outcome != "completed")) return false;
        if (!double.IsFinite(point.Release.RequestedAtMs) || !double.IsFinite(point.Release.CompletedAtMs)
            || point.Release.RequestedAtMs < 0 || point.Release.CompletedAtMs < point.Release.RequestedAtMs
            || !double.IsFinite(point.EndedAtMs.Value) || point.EndedAtMs.Value < point.Release.CompletedAtMs
            || point.ObservationStart < 0 || point.ObservationEnd < point.ObservationStart
            || point.ObservationEnd > NavigationBaselineTask.MaximumObservations
            || point.ObservationEnd - point.ObservationStart != point.ReadCount
            || point.PollStart < 0 || point.PollEnd < point.PollStart
            || point.PollEnd > NativeNavigationBaselineOperations.MaximumCapturePolls
            || point.PollEnd - point.PollStart != point.CaptureCount
            || point.SourceAgeDiscards < 0 || point.SourceAgeDiscards != point.ReadCount - 4
            || point.Release.Error is not null || point.Release.Kind is not ("w_up" or "already_released")
            || !double.IsFinite(point.DeadlineAtMs) || point.DeadlineAtMs > point.Release.CompletedAtMs + 2000
            || point.EndedAtMs.Value >= point.DeadlineAtMs || point.ReadCount is < 4 or > 32 || point.CaptureCount is < 4 or > 32
            || point.CaptureCount < point.ReadCount
            || point.Samples.Length != 3 || NavigationBaselineTask.FinalRejection(point.Samples, First) is not null
            || NavigationBaselineTask.PoseRejection(point.Anchor, Second) is not null
            || double.Hypot(point.Anchor.X - Second.StartX, point.Anchor.Y - Second.StartY) > 1.5
            || point.Anchor.LegIndex != 2 || result.InitialSample.LegIndex != 1
            || !NavigationBaselineTask.AfterBarrier(point.Anchor.Source, point.Release.CompletedAtMs, 80)) return false;
        if (System.Diagnostics.Stopwatch.GetElapsedTime(point.Samples[^1].AcquiredAtStopwatchTicks,
                point.Anchor.AcquiredAtStopwatchTicks).TotalMilliseconds < 80
            || NavigationBaselineTask.SourceAge(point.Anchor.Source, point.EndedAtMs.Value) is not (>= 0 and <= 150)) return false;
        for (var i = 0; i < 2; i++)
        {
            var summary = result.Legs[i];
            if (summary.LegIndex != i + 1 || summary.StartPointId != i + 1 || summary.EndPointId != i + 2
                || !double.IsFinite(summary.StartedAtMs) || !double.IsFinite(summary.EndedAtMs)
                || summary.StartedAtMs < 0 || summary.EndedAtMs < summary.StartedAtMs
                || summary.DecisionStart < 0 || summary.DecisionEnd <= summary.DecisionStart
                || summary.DecisionEnd > result.ObservationCount) return false;
        }
        if (result.Legs[0].DecisionStart != 0 || result.Legs[0].DecisionEnd != result.Legs[1].DecisionStart
            || result.Legs[1].DecisionEnd != result.ObservationCount
            || result.Legs[1].StartedAtMs < result.Legs[0].EndedAtMs) return false;
        var prior = result.InitialSample;
        foreach (var sample in point.Samples.Append(point.Anchor).Concat(result.Samples))
        {
            if (sample.SourceEpoch != prior.SourceEpoch || sample.SourceTimestamp100ns <= prior.SourceTimestamp100ns
                || sample.AcquiredAtStopwatchTicks <= prior.AcquiredAtStopwatchTicks) return false;
            prior = sample;
        }
        return point.Samples.All(sample => sample.LegIndex == 1 && NavigationBaselineTask.AfterBarrier(sample.Source, point.Release.CompletedAtMs, 80))
            && result.Samples.All(sample => sample.LegIndex == 2)
            && result.Legs[0].LegIndex == 1 && result.Legs[1].LegIndex == 2
            && result.Legs[0].EndPointId == 2 && result.Legs[1].EndPointId == 3;
    }
}

/// <summary>Pure immutable segment geometry; map-space bearing still comes from the existing native helper.</summary>
internal sealed record NavigationBaselineLeg(int Index, int StartPointId, int EndPointId,
    double StartX, double StartY, double EndX, double EndY)
{
    /// <summary>Finite fixed map-coordinate length.</summary>
    internal double Length => double.Hypot(EndX - StartX, EndY - StartY);
    /// <summary>Recompute endpoint distance and corridor progress from measured position.</summary>
    internal (double Distance, double Projection, double CrossTrack) Geometry(double x, double y)
    {
        var dx = EndX - StartX; var dy = EndY - StartY;
        return (double.Hypot(x - EndX, y - EndY), ((x - StartX) * dx + (y - StartY) * dy) / Length,
            Math.Abs((x - StartX) * dy - (y - StartY) * dx) / Length);
    }
}
