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

/// <summary>Ignored proposal tests only: synthetic ownership, fixed geometry and evidence; no game or native input.</summary>
public sealed class NavigationBaselineEndpointContinuationTests
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

    /// <summary>Only reversed shipped endpoints are selectable; the legacy constants remain identical.</summary>
    [Fact]
    public void ReverseUsesOnlyShippedPoints()
    {
        var route = NavigationBaselineRouteProfile.Reverse;
        Assert.Equal((3, 2), (route.InitialLeg.StartPointId, route.InitialLeg.EndPointId));
        Assert.Equal((2, 1), (route.SecondLeg.StartPointId, route.SecondLeg.EndPointId));
        Assert.Equal(NavigationBaselineRouteProfile.Second.EndX, route.InitialLeg.StartX);
        Assert.Equal(NavigationBaselineRouteProfile.First.StartY, route.SecondLeg.EndY);
        Assert.Same(NavigationBaselineRouteProfile.First, NavigationBaselineRouteProfile.Single.InitialLeg);
        Assert.True(route.RequiresPredecessor);
    }

    /// <summary>Fresh reverse workflow preserves the real waypoint3+1 collector and the original global deadline.</summary>
    [Fact]
    public async Task ReverseWorkflowRetainsThreePlusOneAndFreshFinalEvidence()
    {
        var native = new Operations(); var link = Link();
        var result = await Run(native, link);
        Assert.True(result.Verified, result.Error); Assert.True(NavigationBaselineTaskOwner.VerifiedResult(result));
        Assert.Same(link, result.Continuation); Assert.Equal(1, native.Prepares); Assert.Equal(1, native.PermanentCloses);
        Assert.Equal(31000, native.WaypointDeadline); Assert.Equal(31000, native.FinalDeadline);
        Assert.Equal(3, result.Waypoint!.Samples.Length); Assert.NotNull(result.Waypoint.Anchor);
        Assert.Equal(new[] { 3, 2 }, result.Legs.Select(x => x.StartPointId));
        Assert.Equal(new[] { 2, 1 }, result.Legs.Select(x => x.EndPointId));
        Assert.Equal(3, result.Samples.Length); Assert.True(native.PublishedAfterClose);
        Assert.False(NavigationBaselineTaskOwner.VerifiedResult(result with { Continuation = null }));
    }

    /// <summary>Freshness/start/epoch/floor failures never reach a camera or W command.</summary>
    [Theory]
    [InlineData("outside")]
    [InlineData("epoch")]
    [InlineData("reported")]
    [InlineData("acquired")]
    [InlineData("stale")]
    [InlineData("motion")]
    public async Task InitialRejectionCannotAuthorizeInput(string mutation)
    {
        var link = Link();
        var native = new Operations { InitialMutation = sample => mutation switch
        {
            "outside" => sample with { X = sample.X + 1.5001 },
            "epoch" => sample with { SourceEpoch = Guid.NewGuid() },
            "reported" => sample with { SourceTimestamp100ns = link.PredecessorFinalSource.SourceTimestamp100ns },
            "acquired" => sample with { AcquiredAtStopwatchTicks = link.PredecessorFinalSource.AcquiredAtStopwatchTicks },
            "stale" => sample with { SourceAgeMs = 150.001 },
            _ => sample with { Motion = sample.Motion with { Status = "fly" } }
        } };
        var result = await Run(native, link);
        Assert.False(result.Verified); Assert.Equal(0, native.Commands); Assert.Equal(1, native.PermanentCloses);
    }

    /// <summary>Returning late from midpoint cannot renew the thirty-second owner budget.</summary>
    [Fact]
    public async Task ReverseWaypointDoesNotResetDeadline()
    {
        var native = new Operations { HandoffDelay = 30001 };
        var result = await Run(native, Link());
        Assert.False(result.Verified); Assert.Equal("baseline_deadline_exceeded", result.Error);
        Assert.Equal(0, native.SecondLegForwards); Assert.Equal(31000, native.WaypointDeadline);
    }

    /// <summary>All reference and process/mode fields participate; matching serialized PID alone is insufficient.</summary>
    [Theory]
    [InlineData("runtime")][InlineData("capture")][InlineData("input")][InlineData("child")]
    [InlineData("session")][InlineData("nonce")][InlineData("game")][InlineData("start")]
    [InlineData("backend")][InlineData("mode")]
    public async Task OwnerRejectsChangedBinding(string field)
    {
        var owner = new NavigationBaselineTaskOwner(); var binding = Binding();
        var predecessor = await FinishForward(owner, binding);
        var changed = field switch
        {
            "runtime" => binding with { Runtime = new object() }, "capture" => binding with { Capture = new object() },
            "input" => binding with { Input = new object() }, "child" => binding with { ChildProcessId = 21 },
            "session" => binding with { WindowsSessionId = 4 }, "nonce" => binding with { ChildNonce = Guid.NewGuid().ToString("N") },
            "game" => binding with { GameProcessId = 11 }, "start" => binding with { GameStartedAtUtcTicks = 2 },
            "backend" => binding with { CaptureType = "different" }, _ => binding with { ReadbackMode = "blocking" }
        };
        Assert.Throws<InvalidOperationException>(() => StartReverse(owner, changed, predecessor, (_, _, _, _) => throw new Exception("must_not_dispatch")));
        Assert.Equal(predecessor, owner.Snapshot(true).RunId);
    }

    /// <summary>A result produced before callback/native cleanup return is not a predecessor yet.</summary>
    [Fact]
    public async Task CleanupCompletionAndLatestOwnerAreRequired()
    {
        var owner = new NavigationBaselineTaskOwner(); var binding = Binding();
        var result = await ForwardResult(); var retire = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Assert.True(owner.TryStartBound(10, 3, binding, null, async (_, _, _, _) =>
        { await retire.Task; return (new() { Outcome = SoloTaskRunOutcome.Completed }, result); },
            timingContract: "v4", capturePolicy: "task_owned_timer", routeProfile: NavigationBaselineRouteProfile.TwoLegId));
        var predecessor = owner.Snapshot(true).RunId!;
        Assert.False(StartReverse(owner, binding, predecessor, (_, _, _, _) => throw new Exception("must_not_dispatch")));
        retire.SetResult(); await Wait(owner);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finish = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        NavigationBaselineContinuationLink? retained = null;
        Assert.True(StartReverse(owner, binding, predecessor, async (_, _, _, link) =>
        { retained = link; entered.SetResult(); await finish.Task; return (new() { Outcome = SoloTaskRunOutcome.Faulted }, null); }));
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.NotNull(retained); Assert.Equal(predecessor, retained!.PredecessorRunId);
        Assert.True(retained.PredecessorCleanupReturnedAtTicks > 0); Assert.False(retained.PhysicalInputAcknowledged);
        Assert.False(StartReverse(owner, binding, predecessor, (_, _, _, _) => throw new Exception("must_not_dispatch")));
        finish.SetResult(); await Wait(owner);
        Assert.Throws<InvalidOperationException>(() => StartReverse(owner, binding, predecessor, (_, _, _, _) => throw new Exception("must_not_dispatch")));
    }

    /// <summary>The actual owner accepts only its captured link and never treats a reverse result as another forward predecessor.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task OwnerBindsReturnedResultToItsOwnLink(bool changeLink)
    {
        var owner = new NavigationBaselineTaskOwner(); var binding = Binding();
        var predecessor = await FinishForward(owner, binding);
        Assert.True(StartReverse(owner, binding, predecessor, async (_, _, _, link) =>
        {
            var result = await Run(new Operations { NowMs = 5000 }, link);
            Assert.True(result.Verified, result.Error);
            if (changeLink) result = result with { Continuation = link! with { PredecessorRunId = Guid.NewGuid().ToString("N") } };
            return (new() { Outcome = SoloTaskRunOutcome.Completed }, result);
        }));
        await Wait(owner);
        Assert.Equal(changeLink ? "failed" : "completed", owner.Snapshot(true).State);
        var reverseId = owner.Snapshot(true).RunId!;
        Assert.Throws<InvalidOperationException>(() => StartReverse(owner, binding, reverseId, (_, _, _, _) => throw new Exception("must_not_dispatch")));
    }

    /// <summary>Wire lineage is presence-aware and bound into authenticated request replay identity.</summary>
    [Theory]
    [InlineData(null, false)][InlineData("", false)][InlineData("not-a-run", false)]
    [InlineData("e23d76c14ed14df89f88c074bd1890b5", true)]
    public void WireRequiresExactPredecessor(string? predecessor, bool valid)
    {
        var now = DateTimeOffset.UtcNow;
        var data = JsonSerializer.Serialize(new { version = 1, requestId = Guid.NewGuid(), createdAtUnixMs = now.ToUnixTimeMilliseconds(),
            command = "startNavigationBaseline", routeProfile = NavigationBaselineRouteProfile.ReverseId, continuationFromRunId = predecessor,
            timingContract = "v4", capturePolicy = "task_owned_timer", targetProcessId = 20, targetWindowsSessionId = 3, targetNonce = "fixed" });
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes(data), out var request));
        Assert.Equal(valid, ExternalControlProtocol.ValidateRequest(request!, now) is null);
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(request!), ExternalControlProtocol.Fingerprint(request! with { ContinuationFromRunId = Guid.NewGuid().ToString("N") }));
    }

    /// <summary>Predecessor evidence is content-bound even when paths are unchanged.</summary>
    [Fact]
    public void ChangedRetainedEvidenceCannotPass()
    {
        var path = Path.GetTempFileName();
        try
        {
            File.WriteAllBytes(path, new byte[] { 1, 2, 3 });
            var hash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path)));
            var evidence = new NavigationBaselineEvidence(true, path, hash, path, hash, path, hash);
            NavigationBaselineEndpointContinuation.VerifyEvidenceFiles(evidence);
            File.WriteAllBytes(path, new byte[] { 3, 2, 1 });
            Assert.Equal("continuation_evidence_hash_changed", Assert.Throws<InvalidOperationException>(() => NavigationBaselineEndpointContinuation.VerifyEvidenceFiles(evidence)).Message);
        }
        finally { File.Delete(path); }
    }

    /// <summary>Shadow selection must use the same bound admission and survive cleanup/failure with its exact predecessor.</summary>
    [Fact]
    public async Task ShadowAndContinuationStayPinnedThroughBoundCleanup()
    {
        var owner = new NavigationBaselineTaskOwner(); var binding = Binding();
        var predecessor = await FinishForward(owner, binding);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finish = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Assert.True(owner.TryStartBound(10, 3, binding, predecessor, async (_, _, _, link) =>
        {
            Assert.NotNull(link); Assert.Equal(predecessor, link!.PredecessorRunId);
            entered.SetResult(); await finish.Task;
            return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = "synthetic" },
                (NavigationBaselineRunResult?)null);
        }, timingContract: "v4", capturePolicy: "task_owned_timer", routeProfile: NavigationBaselineRouteProfile.ReverseId,
            shadowCapture: NavigationBaselineShadowMode.Rgb192));
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        var admitted = owner.Snapshot(true);
        Assert.Equal(NavigationBaselineShadowMode.Rgb192, admitted.ShadowCapture);
        Assert.Equal(predecessor, admitted.Continuation!.PredecessorRunId);
        Assert.False(StartReverse(owner, binding, predecessor, (_, _, _, _) => throw new Exception("must_not_dispatch")));
        finish.SetResult(); await Wait(owner);
        var terminal = owner.Snapshot(true);
        Assert.Equal("failed", terminal.State); Assert.Equal(admitted.Continuation, terminal.Continuation);
        Assert.Equal(admitted.ShadowCapture, terminal.ShadowCapture);
        Assert.Equal(admitted.Continuation, terminal.Result!.Continuation);
    }

    /// <summary>An archive request cannot bypass missing/changed runtime ownership or overwrite the retained forward proof.</summary>
    [Fact]
    public async Task ShadowDoesNotBypassContinuationAdmission()
    {
        var owner = new NavigationBaselineTaskOwner(); var binding = Binding();
        var predecessor = await FinishForward(owner, binding);
        Assert.Throws<InvalidOperationException>(() => owner.TryStart(10, 3, (_, _, _) => throw new Exception("must_not_dispatch"),
            timingContract: "v4", capturePolicy: "task_owned_timer", routeProfile: NavigationBaselineRouteProfile.ReverseId,
            shadowCapture: NavigationBaselineShadowMode.Rgb192));
        Assert.Throws<InvalidOperationException>(() => owner.TryStartBound(10, 3, binding with { Runtime = new object() }, predecessor,
            (_, _, _, _) => throw new Exception("must_not_dispatch"), timingContract: "v4", capturePolicy: "task_owned_timer",
            routeProfile: NavigationBaselineRouteProfile.ReverseId, shadowCapture: NavigationBaselineShadowMode.Rgb192));
        Assert.Throws<ArgumentException>(() => owner.TryStartBound(10, 3, binding, predecessor,
            (_, _, _, _) => throw new Exception("must_not_dispatch"), timingContract: "v4", capturePolicy: "task_owned_timer",
            routeProfile: NavigationBaselineRouteProfile.ReverseId, shadowCapture: "unknown"));
        Assert.Equal(predecessor, owner.Snapshot(true).RunId);
        Assert.Equal("completed", owner.Snapshot(true).State); Assert.Null(owner.Snapshot().ShadowCapture);
    }

    /// <summary>Trusted synthetic binding; values never name real processes or controls.</summary>
    private static NavigationBaselineOwnerBinding Binding() => new(new object(), new object(), new object(), 20, 3,
        "e23d76c14ed14df89f88c074bd1890b5", 10, 1, "fake-capture", "poll_single_v1");
    /// <summary>Standalone workflow linkage carries no input authority.</summary>
    private static NavigationBaselineContinuationLink Link() => new() { PredecessorRunId = Guid.NewGuid().ToString("N"),
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
        var result = await Run(new Operations { Route = NavigationBaselineRouteProfile.TwoLegs });
        Assert.True(NavigationBaselineTaskOwner.VerifiedResult(result), result.Error); return result;
    }
    /// <summary>Retain a completed forward result through the actual owner callback/cleanup boundary.</summary>
    private static async Task<string> FinishForward(NavigationBaselineTaskOwner owner, NavigationBaselineOwnerBinding binding)
    {
        var result = await ForwardResult();
        Assert.True(owner.TryStartBound(10, 3, binding, null, (_, _, _, _) => Task.FromResult((new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, (NavigationBaselineRunResult?)result)),
            timingContract: "v4", capturePolicy: "task_owned_timer", routeProfile: NavigationBaselineRouteProfile.TwoLegId));
        await Wait(owner); Assert.Equal("completed", owner.Snapshot(true).State); return owner.Snapshot(true).RunId!;
    }
    /// <summary>Invoke only the new reverse owner seam; fake callback owns no native inputs.</summary>
    private static bool StartReverse(NavigationBaselineTaskOwner owner, NavigationBaselineOwnerBinding binding, string predecessor,
        Func<string, CancellationToken, Action<string>, NavigationBaselineContinuationLink?, Task<(SoloTaskRunResult, NavigationBaselineRunResult?)>> callback) =>
        owner.TryStartBound(10, 3, binding, predecessor, callback, timingContract: "v4", capturePolicy: "task_owned_timer", routeProfile: NavigationBaselineRouteProfile.ReverseId);
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
        internal NavigationBaselineRouteProfile Route = NavigationBaselineRouteProfile.Reverse;
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
            var sample = Sample(_leg == 1 ? Route.InitialLeg : Route.SecondLeg, fraction, NowMs);
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
