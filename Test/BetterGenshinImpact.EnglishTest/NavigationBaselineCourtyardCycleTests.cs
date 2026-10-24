using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.GameTask.SoloTask.Execution;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Synthetic ownership, fixed geometry and evidence tests; no game or native input.</summary>
public sealed class NavigationBaselineCourtyardCycleTests
{
    /// <summary>One immutable synthetic capture epoch across both segments.</summary>
    private static readonly Guid Epoch = Guid.Parse("b9de4daa-1cae-42b7-9cd4-bc3ee074a105");
    /// <summary>Source clocks use the actual conversion frequency but no real capture.</summary>
    private static GameCaptureSourceInfo Source(double at) => new(Epoch, (long)(at * 10000), (long)(at * Stopwatch.Frequency / 1000));
    /// <summary>Valid same-frame confidence and explicit segment identity.</summary>
    private static NavigationBaselineSample Sample(NavigationBaselineLeg leg, double fraction, double at)
    {
        var x = leg.StartX + (leg.EndX - leg.StartX) * fraction;
        var y = leg.StartY + (leg.EndY - leg.StartY) * fraction;
        var geometry = leg.Geometry(x, y); var source = Source(at);
        return new(x, y, 45, DateTimeOffset.UnixEpoch, Epoch, source.SourceTimestamp100ns, source.AcquiredAtStopwatchTicks,
            .999, .8, "City_102", new("normal", AgentMotionEvidence.MethodName, false, false, 1), 10, 45,
            geometry.Distance, geometry.Projection, geometry.CrossTrack, new(at, at, at, at + 10)) { LegIndex = leg.Index };
    }

    /// <summary>Only explicit opposite fixed directions are admitted; ordinary forward has no continuation semantics.</summary>
    [Theory]
    [InlineData(NavigationBaselineRouteProfile.CourtyardForwardId, NavigationBaselineRouteProfile.CourtyardReturnId, true)]
    [InlineData(NavigationBaselineRouteProfile.CourtyardForwardId, NavigationBaselineTask.ProfileId, false)]
    [InlineData(NavigationBaselineRouteProfile.CourtyardForwardId, NavigationBaselineRouteProfile.CourtyardForwardId, false)]
    [InlineData(NavigationBaselineRouteProfile.CourtyardReturnId, NavigationBaselineTask.ProfileId, true)]
    [InlineData(NavigationBaselineRouteProfile.CourtyardReturnId, NavigationBaselineRouteProfile.CourtyardForwardId, true)]
    [InlineData(NavigationBaselineRouteProfile.CourtyardReturnId, NavigationBaselineRouteProfile.CourtyardReturnId, false)]
    [InlineData(NavigationBaselineRouteProfile.CourtyardReturnId, NavigationBaselineRouteProfile.TwoLegId, false)]
    [InlineData(NavigationBaselineRouteProfile.CourtyardReturnId, NavigationBaselineRouteProfile.ReverseId, false)]
    [InlineData(NavigationBaselineRouteProfile.CourtyardForwardId, NavigationBaselineRouteProfile.ReverseId, false)]
    [InlineData(NavigationBaselineRouteProfile.ReverseId, NavigationBaselineRouteProfile.TwoLegId, true)]
    [InlineData(NavigationBaselineRouteProfile.ReverseId, NavigationBaselineRouteProfile.CourtyardForwardId, false)]
    public void ExplicitDirectionPairs(string requested, string previous, bool accepted)
    {
        var route = NavigationBaselineRouteProfile.Resolve(requested, "v4", "task_owned_timer");
        Assert.Equal(accepted, route.AllowsPredecessor(previous));
    }

    /// <summary>Continuation changes admission, not shipped forward coordinates or legacy omission.</summary>
    [Fact]
    public void RequestedForwardGeometryAndLegacyProfilesRemainExact()
    {
        var route = NavigationBaselineRouteProfile.CourtyardForward;
        Assert.True(route.RequiresPredecessor); Assert.Same(NavigationBaselineRouteProfile.First, route.InitialLeg);
        Assert.Same(NavigationBaselineRouteProfile.First, route.FinalLeg);
        Assert.Equal(1, route.Count); Assert.False(route.IsTwoLeg);
        var back = NavigationBaselineRouteProfile.CourtyardReturn;
        Assert.Equal((1, 2, 1), (back.InitialLeg.Index, back.InitialLeg.StartPointId, back.InitialLeg.EndPointId));
        Assert.Same(back.InitialLeg, back.FinalLeg);
        Assert.Equal(NavigationBaselineRouteProfile.First.EndX, back.InitialLeg.StartX);
        Assert.Equal(NavigationBaselineRouteProfile.First.EndY, back.InitialLeg.StartY);
        Assert.Equal(NavigationBaselineRouteProfile.First.StartX, back.InitialLeg.EndX);
        Assert.Equal(NavigationBaselineRouteProfile.First.StartY, back.InitialLeg.EndY);
        Assert.False(NavigationBaselineRouteProfile.Single.RequiresPredecessor);
        Assert.False(NavigationBaselineRouteProfile.TwoLegs.RequiresPredecessor);
        Assert.Throws<ArgumentException>(() => NavigationBaselineRouteProfile.Resolve(route.Id, "v3", "task_owned_timer"));
        Assert.Throws<ArgumentException>(() => NavigationBaselineRouteProfile.Resolve(route.Id, "v4", "shared"));
        Assert.Contains(route.Id, new NavigationBaselineStatus().RouteProfiles);
    }

    /// <summary>Real workflow/owner transitions compose as four separately requested runs, with no reset operation.</summary>
    [Fact]
    public async Task OwnerCompletesExplicitForwardReverseForwardReverse()
    {
        var owner = new NavigationBaselineTaskOwner(); var binding = Binding();
        NavigationBaselineStatus? previous = null;
        foreach (var route in new[] { NavigationBaselineRouteProfile.Single, NavigationBaselineRouteProfile.CourtyardReturn,
                     NavigationBaselineRouteProfile.CourtyardForward, NavigationBaselineRouteProfile.CourtyardReturn })
        {
            var current = await Complete(owner, binding, route);
            Assert.True(NavigationBaselineTaskOwner.VerifiedResult(current.Result));
            Assert.Null(current.Result!.Waypoint);
            Assert.Equal(route.RecordsLegs ? 1 : 0, current.Result.Legs.Length);
            Assert.Equal(route.RecordsLegs ? 1 : (int?)null, current.Result.RouteVersion);
            if (route.RecordsLegs)
            {
                Assert.Equal(route.InitialLeg.StartPointId, current.Result.Legs[0].StartPointId);
                Assert.Equal(route.InitialLeg.EndPointId, current.Result.Legs[0].EndPointId);
                Assert.Equal(current.ObservationCount, current.Result.Legs[0].DecisionEnd);
            }
            if (previous is null) Assert.Null(current.Continuation);
            else
            {
                Assert.NotEqual(previous.RunId, current.RunId);
                Assert.Equal(previous.RunId, current.Continuation!.PredecessorRunId);
                Assert.Equal(previous.ProfileId, current.Continuation.PredecessorProfileId);
                Assert.Equal(previous.Result!.Samples[^1].Source, current.Continuation.PredecessorFinalSource);
                Assert.True(current.Continuation.PredecessorCleanupReturnedAtTicks > 0);
                Assert.True(current.Result!.InitialSample!.AcquiredAtStopwatchTicks > previous.Result.Samples[^1].AcquiredAtStopwatchTicks);
                if (previous.Continuation is not null) Assert.Equal(previous.Continuation.RuntimeIdentity, current.Continuation.RuntimeIdentity);
                using var json = JsonDocument.Parse(ExternalControlProtocol.SerializeResponse(new ExternalControlResponse
                    { Status = new() { NavigationBaseline = current } }));
                var evidence = json.RootElement.GetProperty("status").GetProperty("navigationBaseline").GetProperty("result").GetProperty("continuation").GetProperty("predecessorEvidence");
                Assert.False(evidence.TryGetProperty("continuation", out _)); // No recursive prior result growth.
            }
            previous = current;
        }
    }

    /// <summary>A point3 pose, changed epoch, or either nonadvancing source clock fails before any native command.</summary>
    [Theory]
    [InlineData("wrong-anchor")][InlineData("epoch")][InlineData("reported-clock")][InlineData("acquisition-clock")][InlineData("wrong-predecessor-profile")][InlineData("climb")]
    public async Task NewForwardStartIsStrictBeforeInput(string failure)
    {
        var link = Link() with { PredecessorProfileId = NavigationBaselineRouteProfile.CourtyardReturnId };
        var native = new Operations { Route = NavigationBaselineRouteProfile.CourtyardForward };
        native.InitialMutation = sample => failure switch
        {
            "wrong-anchor" => Sample(NavigationBaselineRouteProfile.CourtyardReturnLeg, 0, 1120),
            "epoch" => sample with { SourceEpoch = Guid.NewGuid() },
            "reported-clock" => sample with { SourceTimestamp100ns = link.PredecessorFinalSource.SourceTimestamp100ns },
            "acquisition-clock" => sample with { AcquiredAtStopwatchTicks = link.PredecessorFinalSource.AcquiredAtStopwatchTicks },
            "climb" => sample with { Motion = new("Climb", AgentMotionEvidence.MethodName, false, true, 1) },
            _ => sample
        };
        if (failure == "wrong-predecessor-profile") link = link with { PredecessorProfileId = NavigationBaselineTask.ProfileId };
        var result = await Run(native, link);
        Assert.False(result.Verified); Assert.NotNull(result.Error); Assert.Equal(0, native.Commands);
        Assert.True(native.Closed);
    }

    /// <summary>A wrong direction cannot overwrite the last verified ordinary forward or invoke its proposed body.</summary>
    [Fact]
    public async Task OrdinaryForwardCannotPrecedeCourtyardForward()
    {
        var owner = new NavigationBaselineTaskOwner(); var binding = Binding();
        var prior = await Complete(owner, binding, NavigationBaselineRouteProfile.Single);
        Assert.Throws<InvalidOperationException>(() => StartForward(owner, binding, prior.RunId!, (_, _, _, _) => throw new Exception("must_not_dispatch")));
        Assert.Equal(JsonSerializer.Serialize(prior), JsonSerializer.Serialize(owner.Snapshot(true)));
    }

    /// <summary>Reference and process identity equality remain mandatory in the new direction.</summary>
    [Theory]
    [InlineData("runtime")][InlineData("capture")][InlineData("input")][InlineData("nonce")][InlineData("game-start")]
    [InlineData("mode")][InlineData("child")][InlineData("session")][InlineData("game")][InlineData("capture-type")]
    public async Task ChangedBindingCannotPrecedeCourtyardForward(string field)
    {
        var owner = new NavigationBaselineTaskOwner(); var binding = Binding();
        await Complete(owner, binding, NavigationBaselineRouteProfile.Single);
        var prior = await Complete(owner, binding, NavigationBaselineRouteProfile.CourtyardReturn);
        var changed = field switch
        {
            "runtime" => binding with { Runtime = new object() }, "capture" => binding with { Capture = new object() },
            "input" => binding with { Input = new object() }, "nonce" => binding with { ChildNonce = Guid.NewGuid().ToString("N") },
            "game-start" => binding with { GameStartedAtUtcTicks = 2 }, "mode" => binding with { ReadbackMode = "blocking" },
            "child" => binding with { ChildProcessId = 21 }, "session" => binding with { WindowsSessionId = 4 },
            "game" => binding with { GameProcessId = 11 }, _ => binding with { CaptureType = "other" }
        };
        Assert.Throws<InvalidOperationException>(() => StartForward(owner, changed, prior.RunId!, (_, _, _, _) => throw new Exception("must_not_dispatch")));
        Assert.Equal(JsonSerializer.Serialize(prior), JsonSerializer.Serialize(owner.Snapshot(true)));
    }

    /// <summary>Native work finishing is insufficient until the actual predecessor callback returns and its owner retires.</summary>
    [Fact]
    public async Task ForwardWaitsForReverseCallbackRetirement()
    {
        var owner = new NavigationBaselineTaskOwner(); var binding = Binding();
        var first = await Complete(owner, binding, NavigationBaselineRouteProfile.Single);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Assert.True(StartReverse(owner, binding, first.RunId!, async (_, _, _, link) =>
        {
            var result = await Run(new Operations { NowMs = 5000 }, link);
            Assert.True(result.Verified, result.Error); entered.SetResult(); await release.Task;
            return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, result);
        }));
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        var running = owner.Snapshot(true);
        Assert.False(StartForward(owner, binding, running.RunId!, (_, _, _, _) => throw new Exception("must_not_dispatch")));
        release.SetResult(); await Wait(owner);
        Assert.Equal("completed", owner.Snapshot(true).State);
        await Complete(owner, binding, NavigationBaselineRouteProfile.CourtyardForward);
    }

    /// <summary>Failed reverse completion is terminal and cannot be used as a source or endpoint proof.</summary>
    [Fact]
    public async Task FailedReverseCannotContinueForward()
    {
        var owner = new NavigationBaselineTaskOwner(); var binding = Binding();
        var first = await Complete(owner, binding, NavigationBaselineRouteProfile.Single);
        Assert.True(StartReverse(owner, binding, first.RunId!, (_, _, _, _) => Task.FromResult((
            new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = "synthetic" }, (NavigationBaselineRunResult?)null))));
        await Wait(owner); var failed = owner.Snapshot(true);
        Assert.Equal("failed", failed.State);
        Assert.Throws<InvalidOperationException>(() => StartForward(owner, binding, failed.RunId!, (_, _, _, _) => throw new Exception("must_not_dispatch")));
        Assert.Equal(JsonSerializer.Serialize(failed), JsonSerializer.Serialize(owner.Snapshot(true)));
    }

    /// <summary>Actual wire parsing, validation and replay identity include both the exact new selector and predecessor.</summary>
    [Theory]
    [InlineData(null, false)][InlineData("", false)][InlineData("00000000000000000000000000000000", false)]
    [InlineData("e23d76c14ed14df89f88c074bd1890b5", true)]
    public void NewWireRetainsExactPredecessor(string? predecessor, bool valid)
    {
        var now = DateTimeOffset.UtcNow;
        var data = JsonSerializer.Serialize(new { version = 1, requestId = Guid.NewGuid(), createdAtUnixMs = now.ToUnixTimeMilliseconds(),
            command = "startNavigationBaseline", routeProfile = NavigationBaselineRouteProfile.CourtyardForwardId,
            continuationFromRunId = predecessor, timingContract = "v4", capturePolicy = "task_owned_timer",
            targetProcessId = 20, targetWindowsSessionId = 3, targetNonce = "fixed" });
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes(data), out var request));
        Assert.Equal(valid, ExternalControlProtocol.ValidateRequest(request!, now) is null);
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(request!), ExternalControlProtocol.Fingerprint(request! with { RouteProfile = NavigationBaselineRouteProfile.CourtyardReturnId }));
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(request!), ExternalControlProtocol.Fingerprint(request! with { ContinuationFromRunId = Guid.NewGuid().ToString("N") }));
    }

    /// <summary>Only v4/owned short runs gain a future binding; defaults retain legacy process-query behavior.</summary>
    [Theory]
    [InlineData("v1", "shared", false)][InlineData("v2", "task_owned_timer", false)]
    [InlineData("v3", "task_owned_timer", false)][InlineData("v4", "shared", false)]
    [InlineData("v4", "task_owned_timer", true)]
    public void OrdinaryShortRetainsBindingOnlyForSelectedContract(string timing, string capture, bool expected) =>
        Assert.Equal(expected, NavigationBaselineRouteProfile.Single.RetainsOwnerBinding(timing, capture));

    /// <summary>An old unbound ordinary short cannot be retroactively promoted to a current runtime proof.</summary>
    [Fact]
    public async Task UnboundShortCannotAuthorizeCourtyardReturn()
    {
        var owner = new NavigationBaselineTaskOwner(); var binding = Binding();
        var result = await Run(new Operations { Route = NavigationBaselineRouteProfile.Single });
        Assert.True(owner.TryStartBound(10, 3, null, null, (_, _, _, _) => Task.FromResult((
            new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, (NavigationBaselineRunResult?)result)),
            timingContract: "v4", capturePolicy: "task_owned_timer", routeProfile: NavigationBaselineTask.ProfileId));
        await Wait(owner); var prior = owner.Snapshot(true);
        Assert.Equal("completed", prior.State);
        Assert.Throws<InvalidOperationException>(() => StartReverse(owner, binding, prior.RunId!, (_, _, _, _) => throw new Exception("must_not_dispatch")));
        Assert.Equal(JsonSerializer.Serialize(prior), JsonSerializer.Serialize(owner.Snapshot(true)));
    }

    /// <summary>One-leg completion cannot carry a fabricated midpoint or second leg.</summary>
    [Fact]
    public async Task OwnerRechecksCourtyardShapeAndFinalGeometry()
    {
        var result = await Run(new Operations { Route = NavigationBaselineRouteProfile.CourtyardReturn }, Link());
        Assert.True(NavigationBaselineTaskOwner.VerifiedResult(result), result.Error);
        Assert.False(NavigationBaselineTaskOwner.VerifiedResult(result with { Legs = [result.Legs[0], result.Legs[0]] }));
        Assert.False(NavigationBaselineTaskOwner.VerifiedResult(result with
        {
            Waypoint = new() { Release = new("w_up", 0, 0), DeadlineAtMs = 1 }
        }));
        Assert.False(NavigationBaselineTaskOwner.VerifiedResult(result with { Legs = [result.Legs[0] with { StartPointId = 3 }] }));
        Assert.False(NavigationBaselineTaskOwner.VerifiedResult(result with { Samples = result.Samples.Select(p => p with { LegIndex = 2 }).ToArray() }));
        Assert.False(NavigationBaselineTaskOwner.VerifiedResult(result with { Samples = result.Samples.Select(p => p with { X = NavigationBaselineRouteProfile.First.EndX, Y = NavigationBaselineRouteProfile.First.EndY }).ToArray() }));
    }

    /// <summary>Complete one explicit owner request using the same real workflow/collector fixture as the original continuation tests.</summary>
    private static async Task<NavigationBaselineStatus> Complete(NavigationBaselineTaskOwner owner, NavigationBaselineOwnerBinding binding, NavigationBaselineRouteProfile route)
    {
        var previous = owner.Snapshot(true);
        Assert.True(owner.TryStartBound(10, 3, binding, route.RequiresPredecessor ? previous.RunId : null,
            async (_, _, _, link) =>
            {
                var at = link is null ? 1000 : link.PredecessorFinalSource.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency + 200;
                var native = new Operations { Route = route, NowMs = at };
                var result = await Run(native, link);
                Assert.True(result.Verified, result.Error); Assert.True(native.Closed);
                Assert.Equal(0, native.Waypoints); Assert.Equal(1, native.PermanentCloses);
                Assert.Equal(native.Decisions.Length, native.Decisions.Select(d => d.Sample.Source).Distinct().Count());
                return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, (NavigationBaselineRunResult?)result);
            }, timingContract: "v4", capturePolicy: "task_owned_timer", routeProfile: route.Id));
        await Wait(owner); var current = owner.Snapshot(true); Assert.Equal("completed", current.State); return current;
    }

    /// <summary>New direction shares the exact bound owner path; it has no teleport/reset fallback.</summary>
    private static bool StartForward(NavigationBaselineTaskOwner owner, NavigationBaselineOwnerBinding binding, string predecessor,
        Func<string, CancellationToken, Action<string>, NavigationBaselineContinuationLink?, Task<(SoloTaskRunResult, NavigationBaselineRunResult?)>> callback) =>
        owner.TryStartBound(10, 3, binding, predecessor, callback, timingContract: "v4", capturePolicy: "task_owned_timer",
            routeProfile: NavigationBaselineRouteProfile.CourtyardForwardId);

    /// <summary>Trusted synthetic binding; values never name real processes or controls.</summary>
    private static NavigationBaselineOwnerBinding Binding() => new(new object(), new object(), new object(), 20, 3,
        "e23d76c14ed14df89f88c074bd1890b5", 10, 1, "fake-capture", "poll_single_v1");
    /// <summary>Standalone workflow linkage carries no input authority.</summary>
    private static NavigationBaselineContinuationLink Link() => new() { PredecessorRunId = Guid.NewGuid().ToString("N"),
        PredecessorProfileId = NavigationBaselineTask.ProfileId,
        PredecessorEvidence = new(true, "journal", new('a',64), "initial", new('b',64), "final", new('c',64)),
        PredecessorFinalSource = Source(900), PredecessorCleanupReturnedAtTicks = 1, RuntimeIdentity = Guid.NewGuid(),
        ChildProcessId = 20, ChildNonce = "e23d76c14ed14df89f88c074bd1890b5", WindowsSessionId = 3,
        GameProcessId = 10, GameStartedAtUtcTicks = 1, CaptureType = "fake-capture", ReadbackMode = "poll_single_v1" };
    /// <summary>Real workflow and collector over synthetic poses only.</summary>
    private static Task<NavigationBaselineRunResult> Run(Operations native, NavigationBaselineContinuationLink? link = null) =>
        new NavigationBaselineTask(native, "v4", "task_owned_timer", native.Route.Id, link).RunAsync(_ => { }, default);
    /// <summary>Build an independently verified predecessor without bypassing workflow/collector predicates.</summary>
    private static async Task<NavigationBaselineRunResult> ForwardResult()
    {
        var result = await Run(new Operations { Route = NavigationBaselineRouteProfile.Single });
        Assert.True(NavigationBaselineTaskOwner.VerifiedResult(result), result.Error); return result;
    }
    /// <summary>Retain a completed forward result through the actual owner callback/cleanup boundary.</summary>
    private static async Task<string> FinishForward(NavigationBaselineTaskOwner owner, NavigationBaselineOwnerBinding binding)
    {
        var result = await ForwardResult();
        Assert.True(owner.TryStartBound(10, 3, binding, null, (_, _, _, _) => Task.FromResult((new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, (NavigationBaselineRunResult?)result)),
            timingContract: "v4", capturePolicy: "task_owned_timer", routeProfile: NavigationBaselineTask.ProfileId));
        await Wait(owner); Assert.Equal("completed", owner.Snapshot(true).State); return owner.Snapshot(true).RunId!;
    }
    /// <summary>Invoke only the new reverse owner seam; fake callback owns no native inputs.</summary>
    private static bool StartReverse(NavigationBaselineTaskOwner owner, NavigationBaselineOwnerBinding binding, string predecessor,
        Func<string, CancellationToken, Action<string>, NavigationBaselineContinuationLink?, Task<(SoloTaskRunResult, NavigationBaselineRunResult?)>> callback) =>
        owner.TryStartBound(10, 3, binding, predecessor, callback, timingContract: "v4", capturePolicy: "task_owned_timer", routeProfile: NavigationBaselineRouteProfile.CourtyardReturnId);
    /// <summary>Finite test-only retirement wait; never a performance assertion.</summary>
    private static async Task Wait(NavigationBaselineTaskOwner owner)
    {
        var clock = Stopwatch.StartNew();
        while (owner.Running && clock.Elapsed < TimeSpan.FromSeconds(5)) await Task.Delay(1);
        Assert.False(owner.Running);
    }

    /// <summary>Workflow fake retains the actual waypoint collector; lease races have a separate real-lease test cohort.</summary>
    private sealed class Operations : INavigationBaselineOperations, INavigationBaselineRecoveryOperations,
        INavigationBaselineFinalVerificationOperations, INavigationBaselineWaypointOperations
    {
        /// <summary>One virtual owner clock.</summary>
        public double NowMs { get; set; } = 1000;
        /// <summary>Explicit fake held state.</summary>
        public bool ForwardHeld { get; private set; }
        /// <summary>No injected lease fault in this boundary fake.</summary>
        public string? Fault => null;
        /// <summary>Fake keyup always completes.</summary>
        public string? ReleaseError => null;
        /// <summary>Immutable selected profile.</summary>
        public string RouteProfileId => Route.Id;
        /// <summary>Fixed selected test route; no caller coordinates.</summary>
        internal NavigationBaselineRouteProfile Route = NavigationBaselineRouteProfile.CourtyardReturn;
        /// <summary>Optional first-sample corruption is rejected before any input.</summary>
        internal Func<NavigationBaselineSample, NavigationBaselineSample>? InitialMutation;
        /// <summary>Count every command attempt, including camera attempts.</summary>
        internal int Commands;
        /// <summary>Bounded midpoint result retained by the workflow.</summary>
        public NavigationBaselineWaypointRecord? WaypointRecord { get; private set; }
        /// <summary>Observable one-lifetime effects and global deadlines.</summary>
        internal int Prepares, Waypoints, PermanentCloses, Recoveries, SecondLegForwards;
        /// <summary>Failure injection remains outside actual input.</summary>
        internal string? WaypointFailure;
        /// <summary>Virtual late return after a valid midpoint.</summary>
        internal double HandoffDelay, WaypointDeadline, FinalDeadline;
        /// <summary>Permanent closure and publication observation.</summary>
        internal bool Closed, PublishedAfterClose;
        /// <summary>Exercise two leg1 interruptions followed by a third request after the waypoint.</summary>
        internal bool InjectRecoveries;
        /// <summary>Read-side injection count is global, never cleared by the waypoint.</summary>
        private int _interruptions;
        /// <summary>Exact workflow rows for source uniqueness checks.</summary>
        internal NavigationBaselineDecision[] Decisions = [];
        /// <summary>Per-leg fake progress only; production retains one global source/counter state.</summary>
        private int _leg = 1, _reads;
        /// <summary>One owned native setup.</summary>
        public Task PrepareAsync(CancellationToken ct) { Prepares++; return Task.CompletedTask; }
        /// <summary>Deterministic progress reaches each endpoint without teleport behavior.</summary>
        public Task<NavigationBaselineSample> ReadPoseAsync(string? image, CancellationToken ct)
        {
            if (InjectRecoveries && image is null && ((_leg == 1 && _interruptions < 2) || (_leg == 2 && _interruptions == 2)))
            { _interruptions++; NowMs += 120; throw new NavigationBaselineRecoveryRequired(NavigationBaselineRecoveryCause.SourceAge, "after_capture"); }
            NowMs += 120; var fraction = Closed ? 1 : _leg == 1 ? Math.Min(1, _reads++ * .5) : Math.Min(1, ++_reads * .5);
            var sample = Sample(_leg == 1 ? Route.InitialLeg : Route.SecondLeg, fraction, NowMs) with { LegIndex = Route.RecordsLegs ? _leg : null };
            if (image == "initial" && InitialMutation is not null) sample = InitialMutation(sample);
            return Task.FromResult(sample);
        }
        /// <summary>Expose one released3+1 collector under the unchanged original owner deadline.</summary>
        public async Task<NavigationBaselineSample> VerifyWaypointAndAdvanceAsync(double deadline,
            Func<NavigationBaselineSample, NavigationBaselineWaypointVerification.Admission> rows, CancellationToken ct)
        {
            Waypoints++; WaypointDeadline = deadline; ForwardHeld = false;
            if (WaypointFailure is not null) throw new InvalidOperationException(WaypointFailure);
            var window = new NavigationBaselineWaypointVerification(() => NowMs, new("w_up", NowMs, NowMs), deadline, Source(NowMs), 3, 3, Route);
            WaypointRecord = window.Record;
            var anchor = await window.CollectAsync((next, token) =>
            {
                window.BeginCapture(token); NowMs += 120;
                var sample = Sample(next ? Route.SecondLeg : Route.InitialLeg, next ? 0 : 1, NowMs);
                var attempt = new NavigationBaselineObservationAttempt(NowMs);
                window.ValidateSource(sample.Source, "after_capture", attempt, token);
                window.Admit(sample, attempt, rows, () => Assert.False(ForwardHeld), token);
                return Task.FromResult(sample);
            }, WaitUntilAsync, ct);
            WaypointRecord.Outcome = "completed"; WaypointRecord.EndedAtMs = NowMs;
            WaypointRecord.ObservationEnd = 3 + window.Record.ReadCount;
            WaypointRecord.PollEnd = 3 + window.Record.CaptureCount;
            _leg = 2; _reads = 0; NowMs += HandoffDelay; return anchor;
        }
        /// <summary>Final native evidence can occur only after permanent close.</summary>
        public async Task ReadFinalSamplesAsync(double deadline,
            Func<NavigationBaselineSample, NavigationBaselineFinalVerification.Admission> rows, CancellationToken ct)
        {
            Assert.True(Closed); FinalDeadline = deadline;
            for (var i = 0; i < 3; i++) rows(await ReadPoseAsync("final", ct)).Commit();
        }
        /// <summary>Ordinary control is never permitted while permanently closed.</summary>
        public NavigationBaselineInputEvent Forward(NavigationBaselineSample sample, CancellationToken ct)
        { Commands++; Assert.False(Closed); if (_leg == 2) SecondLegForwards++; ForwardHeld = true; return new("w_down", NowMs, NowMs); }
        /// <summary>Unused aligned synthetic camera path.</summary>
        public NavigationBaselineInputEvent Rotate(NavigationBaselineSample sample, CancellationToken ct) { Commands++; throw new InvalidOperationException("unexpected_camera"); }
        /// <summary>Ordinary realignment release, not terminal closure.</summary>
        public NavigationBaselineInputEvent ReleaseForward() { ForwardHeld = false; return new("w_up", NowMs, NowMs); }
        /// <summary>Idempotent permanent close, invoked again by cleanup without a new lifetime.</summary>
        public void CloseInput() { if (!Closed) PermanentCloses++; Closed = true; ForwardHeld = false; }
        /// <summary>No worker or sleep; caller-specified cadence advances the virtual clock.</summary>
        public Task WaitUntilAsync(double deadline, CancellationToken ct) { NowMs = Math.Max(NowMs, deadline); return Task.CompletedTask; }
        /// <summary>Legacy recovery activation occurs once after the initial anchor.</summary>
        public void EnableRecovery() { }
        /// <summary>Any accidental waypoint recovery is observable and terminal in this fake.</summary>
        public Task<NavigationBaselineSample> RecoverAsync(NavigationBaselineRecoveryRequired error, double deadline, CancellationToken ct)
        {
            Recoveries++;
            if (!InjectRecoveries) throw new InvalidOperationException("unexpected_recovery");
            if (Recoveries > NavigationBaselineRecovery.MaximumRecoveries) throw new InvalidOperationException("recovery_limit_exceeded");
            Assert.Equal(31000, deadline); ForwardHeld = false; NowMs += 120;
            return Task.FromResult(Sample(Route.InitialLeg, .5, NowMs));
        }
        /// <summary>Capture exact global decisions without disk files or fake training claims.</summary>
        public Task<NavigationBaselineEvidence> PublishEvidenceAsync(NavigationBaselineRunResult result,
            NavigationBaselineDecision[] decisions, NavigationBaselineScheduleWait[] waits)
        {
            PublishedAfterClose = Closed; Decisions = decisions;
            return Task.FromResult(new NavigationBaselineEvidence(true, "journal", new('a', 64), "initial", new('b', 64), "final", new('c', 64)) { ReadbackMode = "poll_single_v1" });
        }
    }
}
