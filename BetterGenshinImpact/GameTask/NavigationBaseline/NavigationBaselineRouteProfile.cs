using System;
using System.Linq;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Only fixed built-in routes; continuation requires an exact completed opposite-direction predecessor and accepts no caller coordinates.</summary>
internal sealed class NavigationBaselineRouteProfile
{
    /// <summary>Explicit continuation selection; omission retains the original single leg.</summary>
    internal const string TwoLegId = "mondstadt-city-two-legs-v1";
    /// <summary>One explicit reverse run after an exact completed forward predecessor; never an automatic loop.</summary>
    internal const string ReverseId = "mondstadt-city-reverse-two-legs-v1";
    /// <summary>Explicit point1-to-point2 continuation after a verified courtyard return; never an automatic loop.</summary>
    internal const string CourtyardForwardId = "mondstadt-city-courtyard-forward-v1";
    /// <summary>Explicit point2-to-point1 return on the original upper courtyard segment.</summary>
    internal const string CourtyardReturnId = "mondstadt-city-courtyard-return-v1";
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
    /// <summary>Reversed immutable asset endpoints, with logical leg indices still1/2.</summary>
    internal static readonly NavigationBaselineLeg ReverseFirst = new(1, 3, 2, Second.EndX, Second.EndY, Second.StartX, Second.StartY);
    /// <summary>Point2 to the unchanged positive local map anchor at point1.</summary>
    internal static readonly NavigationBaselineLeg ReverseSecond = new(2, 2, 1, First.EndX, First.EndY, First.StartX, First.StartY);
    /// <summary>No caller coordinates or per-run mutable global route geometry.</summary>
    internal static readonly NavigationBaselineRouteProfile Reverse = new(ReverseId, true);
    /// <summary>Fixed forward geometry with mandatory reverse predecessor ownership proof.</summary>
    internal static readonly NavigationBaselineRouteProfile CourtyardForward = new(CourtyardForwardId, false);
    /// <summary>Reversed first segment only; never traverses the point2-to-point3 elevation edge.</summary>
    internal static readonly NavigationBaselineLeg CourtyardReturnLeg = new(1, 2, 1, First.EndX, First.EndY, First.StartX, First.StartY);
    /// <summary>One bounded explicit return with no waypoint or reset.</summary>
    internal static readonly NavigationBaselineRouteProfile CourtyardReturn = new(CourtyardReturnId, false);
    /// <summary>Both explicit continuation profiles require the exact retained completed owner.</summary>
    internal bool RequiresPredecessor => Id is ReverseId or CourtyardReturnId or CourtyardForwardId;
    /// <summary>Explicit profiles record their fixed leg identities; the original omitted short keeps its legacy shape.</summary>
    internal bool RecordsLegs => IsTwoLeg || RequiresPredecessor;
    /// <summary>A fresh ordinary v4/owned short retains the same identity proof needed by its later courtyard return.</summary>
    internal bool RetainsOwnerBinding(string timing, string capture) => IsTwoLeg || RequiresPredecessor
        || timing == NavigationBaselineTiming.V4 && capture == NavigationBaselineCapturePolicy.TaskOwnedTimer;
    /// <summary>Only opposite directions may follow; the original ordinary forward remains a valid first predecessor.</summary>
    internal bool AllowsPredecessor(string? profile) => Id switch
    {
        ReverseId => profile == TwoLegId,
        CourtyardReturnId => profile is NavigationBaselineTask.ProfileId or CourtyardForwardId,
        CourtyardForwardId => profile == CourtyardReturnId,
        _ => false
    };
    /// <summary>Selected initial segment; legacy static First remains unchanged.</summary>
    internal NavigationBaselineLeg InitialLeg => Id == ReverseId ? ReverseFirst : Id == CourtyardReturnId ? CourtyardReturnLeg : First;
    /// <summary>Selected second segment; callers resolve only these fixed profiles.</summary>
    internal NavigationBaselineLeg SecondLeg => Id == ReverseId ? ReverseSecond : Second;
    /// <summary>Exact wire and evidence identity.</summary>
    internal string Id { get; }
    /// <summary>Whether one nonterminal waypoint is required.</summary>
    internal bool IsTwoLeg { get; }
    /// <summary>Fixed number of segments, never supplied by a caller.</summary>
    internal int Count => IsTwoLeg ? 2 : 1;
    /// <summary>Final immutable geometry selected without mutating global constants.</summary>
    internal NavigationBaselineLeg FinalLeg => IsTwoLeg ? SecondLeg : InitialLeg;
    /// <summary>Construction stays private so equivalent unreviewed geometry cannot enter native execution.</summary>
    private NavigationBaselineRouteProfile(string id, bool twoLeg) { Id = id; IsTwoLeg = twoLeg; }
    /// <summary>Exact supported identities only; explicit null is rejected by the wire validator.</summary>
    internal static bool IsSupported(string? id) => id is NavigationBaselineTask.ProfileId or TwoLegId or ReverseId or CourtyardReturnId or CourtyardForwardId;
    /// <summary>Resolve before ownership/native acquisition and enforce the independent selected contracts.</summary>
    internal static NavigationBaselineRouteProfile Resolve(string id, string timing, string capture)
    {
        if (!IsSupported(id)) throw new ArgumentException("unsupported_route_profile", nameof(id));
        if ((id is TwoLegId or ReverseId or CourtyardReturnId or CourtyardForwardId) && (timing != NavigationBaselineTiming.V4 || capture != NavigationBaselineCapturePolicy.TaskOwnedTimer))
            throw new ArgumentException("two_leg_requires_v4_task_owned_timer");
        return id == ReverseId ? Reverse : id == CourtyardReturnId ? CourtyardReturn : id == CourtyardForwardId ? CourtyardForward : id == TwoLegId ? TwoLegs : Single;
    }

    /// <summary>Owner rechecks the bounded intermediate record independently of a workflow success flag.</summary>
    internal static bool VerifiedContinuation(NavigationBaselineRunResult result)
    {
        if (result.ProfileId == NavigationBaselineTask.ProfileId) return result.Continuation is null && result.Waypoint is null && result.Legs.Length == 0;
        if (result.ProfileId is CourtyardReturnId or CourtyardForwardId)
        {
            if (result.RouteVersion != 1 || result.TimingContract != NavigationBaselineTiming.V4
                || result.CapturePolicy != NavigationBaselineCapturePolicy.TaskOwnedTimer || result.InitialSample is null
                || result.Continuation is null || result.Waypoint is not null || result.Legs.Length != 1) return false;
            var courtyard = Resolve(result.ProfileId, result.TimingContract, result.CapturePolicy);
            if (NavigationBaselineEndpointContinuation.StartRejection(result.Continuation, result.InitialSample, courtyard) is not null) return false;
            var leg = result.Legs[0];
            return leg.LegIndex == 1 && leg.StartPointId == courtyard.InitialLeg.StartPointId
                && leg.EndPointId == courtyard.InitialLeg.EndPointId && leg.Outcome == "completed"
                && double.IsFinite(leg.StartedAtMs) && double.IsFinite(leg.EndedAtMs)
                && leg.StartedAtMs >= 0 && leg.EndedAtMs >= leg.StartedAtMs
                && leg.DecisionStart == 0 && leg.DecisionEnd == result.ObservationCount && leg.DecisionEnd > 0
                && result.InitialSample.LegIndex == 1 && result.Samples.All(sample => sample.LegIndex == 1);
        }
        if (result.ProfileId is not (TwoLegId or ReverseId) || result.RouteVersion != 1 || result.TimingContract != NavigationBaselineTiming.V4
            || result.CapturePolicy != NavigationBaselineCapturePolicy.TaskOwnedTimer || result.InitialSample is null
            || result.Waypoint is not { Outcome: "completed", Error: null, Anchor: not null, EndedAtMs: not null } point
            || result.Legs.Length != 2 || result.Legs.Any(leg => leg.Outcome != "completed")) return false;
        var profile = Resolve(result.ProfileId, result.TimingContract, result.CapturePolicy);
        if (profile.RequiresPredecessor && (result.Continuation is null
                || NavigationBaselineEndpointContinuation.StartRejection(result.Continuation, result.InitialSample, profile) is not null)) return false;
        if (!profile.RequiresPredecessor && result.Continuation is not null) return false;
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
            || point.Samples.Length != 3 || NavigationBaselineTask.FinalRejection(point.Samples, profile.InitialLeg) is not null
            || NavigationBaselineTask.PoseRejection(point.Anchor, profile.SecondLeg) is not null
            || double.Hypot(point.Anchor.X - profile.SecondLeg.StartX, point.Anchor.Y - profile.SecondLeg.StartY) > 1.5
            || point.Anchor.LegIndex != 2 || result.InitialSample.LegIndex != 1
            || !NavigationBaselineTask.AfterBarrier(point.Anchor.Source, point.Release.CompletedAtMs, 80)) return false;
        if (System.Diagnostics.Stopwatch.GetElapsedTime(point.Samples[^1].AcquiredAtStopwatchTicks,
                point.Anchor.AcquiredAtStopwatchTicks).TotalMilliseconds < 80
            || NavigationBaselineTask.SourceAge(point.Anchor.Source, point.EndedAtMs.Value) is not (>= 0 and <= 150)) return false;
        for (var i = 0; i < 2; i++)
        {
            var summary = result.Legs[i]; var leg = i == 0 ? profile.InitialLeg : profile.SecondLeg;
            if (summary.LegIndex != i + 1 || summary.StartPointId != leg.StartPointId || summary.EndPointId != leg.EndPointId
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
            && result.Legs[0].EndPointId == profile.InitialLeg.EndPointId && result.Legs[1].EndPointId == profile.SecondLeg.EndPointId;
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
