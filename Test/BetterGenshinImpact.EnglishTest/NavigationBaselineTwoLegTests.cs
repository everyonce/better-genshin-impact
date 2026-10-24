using System.Diagnostics;
using System.Text;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>CPU-only fixed continuation/collector tests; all poses and input effects are synthetic.</summary>
public sealed class NavigationBaselineTwoLegTests
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

    /// <summary>The original corridor cannot accidentally authorize the second endpoint.</summary>
    [Fact]
    public void FixedGeometryChangesExplicitlyAndLegacyRemainsFirstLeg()
    {
        var sample = Sample(NavigationBaselineRouteProfile.Second, 1, 1000);
        Assert.Null(NavigationBaselineTask.PoseRejection(sample, NavigationBaselineRouteProfile.Second));
        Assert.Equal("route_leg_mismatch", NavigationBaselineTask.PoseRejection(sample));
        Assert.Equal("route_corridor_exceeded", NavigationBaselineTask.PoseRejection(sample with { LegIndex = null }));
        Assert.InRange(NavigationBaselineRouteProfile.Second.Length, 16.0495, 16.0496);
        Assert.Equal(NavigationBaselineTask.Geometry(sample.X, sample.Y), NavigationBaselineRouteProfile.First.Geometry(sample.X, sample.Y));
    }

    /// <summary>Unsupported combinations fail before native ownership or route mutation.</summary>
    [Theory]
    [InlineData("v1", "task_owned_timer")]
    [InlineData("v3", "task_owned_timer")]
    [InlineData("v4", "shared")]
    public void ContinuationRequiresBothExplicitContracts(string timing, string capture)
    {
        Assert.Throws<ArgumentException>(() => NavigationBaselineRouteProfile.Resolve(NavigationBaselineRouteProfile.TwoLegId, timing, capture));
        Assert.Same(NavigationBaselineRouteProfile.Single,
            NavigationBaselineRouteProfile.Resolve(NavigationBaselineTask.ProfileId, timing, capture));
    }

    /// <summary>One atomic workflow retains one owner/prepare/final close and counts every decision source once.</summary>
    [Fact]
    public async Task TwoLegWorkflowUsesOneLifetimeAndIndependentOwnerAcceptance()
    {
        var native = new Operations();
        var result = await Run(native);
        Assert.True(result.Verified, result.Error); Assert.True(NavigationBaselineTaskOwner.VerifiedResult(result));
        Assert.Equal(1, native.Prepares); Assert.Equal(1, native.Waypoints); Assert.Equal(1, native.PermanentCloses);
        Assert.Equal(31000, native.WaypointDeadline); Assert.Equal(31000, native.FinalDeadline);
        Assert.True(native.PublishedAfterClose); Assert.Equal(2, result.Legs.Length);
        Assert.Equal(3, result.Waypoint!.Samples.Length); Assert.NotNull(result.Waypoint.Anchor);
        Assert.Equal(3, result.Samples.Length); Assert.All(result.Samples, pose => Assert.Equal(2, pose.LegIndex));
        Assert.Equal(native.Decisions.Length, native.Decisions.Select(row => row.Sample.Source).Distinct().Count());
        Assert.Single(native.Decisions.Where(row => row.Sample.Source == result.Waypoint.Anchor!.Source));
        Assert.False(NavigationBaselineTaskOwner.VerifiedResult(result with { Waypoint = result.Waypoint with { Outcome = "failed" } }));
        Assert.False(NavigationBaselineTaskOwner.VerifiedResult(result with { Legs = result.Legs[..1] }));
    }

    /// <summary>Waypoint work consumes the original owner deadline and cannot continue input after a late return.</summary>
    [Fact]
    public async Task LateHandoffDoesNotRestartGlobalDeadline()
    {
        var native = new Operations { HandoffDelay = 30001 };
        var result = await Run(native);
        Assert.False(result.Verified); Assert.Equal("baseline_deadline_exceeded", result.Error);
        Assert.Equal(0, native.SecondLegForwards); Assert.Equal(1, native.PermanentCloses);
        Assert.Equal(31000, native.WaypointDeadline); Assert.True(native.PublishedAfterClose);
    }

    /// <summary>Typed hard midpoint failure is terminal and never reaches movement recovery.</summary>
    [Theory]
    [InlineData("world_not_ready")]
    [InlineData("handoff_anchor_not_reached")]
    [InlineData("waypoint_capture_limit_exceeded")]
    public async Task FailedWaypointNeverDispatchesSecondLeg(string failure)
    {
        var native = new Operations { WaypointFailure = failure };
        var result = await Run(native);
        Assert.False(result.Verified); Assert.Equal(failure, result.Error); Assert.Equal(0, native.Recoveries);
        Assert.Equal(0, native.SecondLegForwards); Assert.True(native.Closed); Assert.Empty(result.Samples);
    }

    /// <summary>Readiness retains a completed prefix but never publishes callback work before freshness admission.</summary>
    [Fact]
    public async Task StaleReadAndDelayedAdmissionRetryInsideOneWaypointWindow()
    {
        var fixture = new Collector(); fixture.AgeFirst = true; fixture.StageDelayOnce = 151;
        var anchor = await fixture.Run();
        Assert.Equal(6, fixture.Window.Record.ReadCount); Assert.Equal(2, fixture.Window.Record.SourceAgeDiscards);
        Assert.Equal(3, fixture.Decisions.Count); Assert.Equal(3, fixture.Window.Record.Samples.Length);
        Assert.Equal(anchor, fixture.Window.Record.Anchor); Assert.Equal(2, anchor.LegIndex);
        Assert.Equal(3000, fixture.Window.Record.DeadlineAtMs); Assert.Equal(3, fixture.Decisions.Select(row => row.Sample.Source).Distinct().Count());
        Assert.Equal("holding", fixture.Window.Record.Outcome); // Collection alone cannot authorize clearing the lease hold.
    }

    /// <summary>Known source/pose failures precede source age and are not retry classifications.</summary>
    [Theory]
    [InlineData("layer", "wrong_layer")]
    [InlineData("motion", "non_normal_motion")]
    [InlineData("epoch", "source_epoch_changed")]
    [InlineData("regressed", "native_source_regressed")]
    [InlineData("spacing", "acquisition_spacing_too_short")]
    [InlineData("yaw", "yaw_spread_exceeded")]
    public async Task HardWaypointFailureDoesNotBecomeAgeRetry(string mutation, string error)
    {
        var fixture = new Collector { Mutation = mutation };
        var actual = await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.Run());
        Assert.Equal(error, actual.Message); Assert.Equal(0, fixture.Window.Record.SourceAgeDiscards);
        Assert.Null(fixture.Window.Record.Anchor);
    }

    /// <summary>Endpoint tolerance2 cannot silently relax the next anchor's1.5 limit.</summary>
    [Fact]
    public async Task StableEndpointOutsideNextAnchorFailsWithoutCorrectiveInput()
    {
        var fixture = new Collector { AnchorOffset = 1.6 };
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => fixture.Run());
        Assert.Equal("handoff_anchor_not_reached", error.Message);
        Assert.Equal(3, fixture.Window.Record.Samples.Length); Assert.Null(fixture.Window.Record.Anchor);
    }

    /// <summary>A prepared checkpoint cannot commit after the owner-clipped window ends or cancellation wins.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void DelayedAdmissionRemainsUnpublished(bool cancel)
    {
        double now = 1100;
        using var stop = new CancellationTokenSource();
        var window = new NavigationBaselineWaypointVerification(() => now, new("w_up", 1000, 1000), 1200, Source(990), 0, 0);
        var rows = new List<NavigationBaselineDecision>(); var sample = Sample(NavigationBaselineRouteProfile.First, 1, now);
        var error = Record.Exception(() => window.Admit(sample, new(now), pose =>
        {
            var staged = NavigationBaselineWaypointVerification.StageDecision(pose, rows);
            if (cancel) stop.Cancel(); else now = 1200;
            return staged;
        }, () => { }, stop.Token));
        Assert.NotNull(error); Assert.Empty(rows); Assert.Empty(window.Record.Samples);
        if (cancel) Assert.IsAssignableFrom<OperationCanceledException>(error);
        else Assert.IsType<NavigationBaselineWaypointVerification.TimeoutException>(error);
    }

    /// <summary>A failed age header advances the immutable floor even though no pose was admitted.</summary>
    [Fact]
    public void AgeDiscardCannotBeFollowedByOlderHeaderOrRenewedPendingIdentity()
    {
        double now = 1300;
        var window = new NavigationBaselineWaypointVerification(() => now, new("already_released", 1000, 1000), 31000, Source(990), 0, 0);
        Assert.Throws<NavigationBaselineWaypointVerification.SourceAgeException>(() => window.ValidateSource(Source(1100), "capture", new(now), default));
        Assert.Equal(Source(1100), window.SeenSource?.WgcSource);
        Assert.Equal("native_source_regressed", Assert.Throws<InvalidOperationException>(() =>
            window.ValidateSource(Source(1099), "capture", new(now), default)).Message);
        Assert.Empty(window.Record.Samples);
    }

    /// <summary>The midpoint cannot replenish movement recovery allowance already spent during leg1.</summary>
    [Fact]
    public async Task RecoveryBudgetIsGlobalAcrossTheSameWorkflowInstance()
    {
        var native = new Operations { InjectRecoveries = true };
        var result = await Run(native);
        Assert.False(result.Verified); Assert.Equal("recovery_limit_exceeded", result.Error);
        Assert.Equal(3, native.Recoveries); Assert.Equal(1, native.Waypoints);
        Assert.Equal(31000, native.WaypointDeadline); Assert.True(native.PublishedAfterClose);
    }

    /// <summary>Owner success cannot hide a missing read outcome or repeat the handoff source as a terminal pose.</summary>
    [Theory]
    [InlineData("missing_outcome")]
    [InlineData("source_reuse")]
    public async Task OwnerRejectsBrokenIntermediateEvidence(string mutation)
    {
        var result = await Run(new Operations());
        Assert.True(NavigationBaselineTaskOwner.VerifiedResult(result));
        if (mutation == "missing_outcome")
        { result.Waypoint!.ReadCount++; result.Waypoint.ObservationEnd++; result.Waypoint.CaptureCount++; result.Waypoint.PollEnd++; }
        else
        {
            var anchor = result.Waypoint!.Anchor!;
            result = result with { Samples = result.Samples.Select((sample, index) => index == 0
                ? sample with { SourceTimestamp100ns = anchor.SourceTimestamp100ns, AcquiredAtStopwatchTicks = anchor.AcquiredAtStopwatchTicks }
                : sample).ToArray() };
        }
        Assert.False(NavigationBaselineTaskOwner.VerifiedResult(result));
    }

    /// <summary>Thirty-two Pending calls consume the same fixed window and never create an accepted pose.</summary>
    [Fact]
    public async Task PendingConsumesBothGlobalAndWaypointBounds()
    {
        double now = 1100;
        var window = new NavigationBaselineWaypointVerification(() => now, new("already_released", 1000, 1000), 31000, Source(990), 20, 4064);
        var polls = Enumerable.Range(0, 4064).Select(index => new NavigationBaselineCapturePoll(index / 4, 900)).ToList();
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => window.CollectAsync((_, token) =>
        {
            while (true)
            {
                window.BeginCapture(token);
                var poll = NativeNavigationBaselineOperations.BeginCapturePoll(polls, 20, now);
                poll.RecordReadback(new(GameCaptureAttemptOutcome.ReadbackPending, pending: new(1, Source(1050),
                    Source(1050).AcquiredAtStopwatchTicks + 1, 1920, 1080, null)));
                now += 5;
            }
        }, (_, _) => Task.CompletedTask, default));
        Assert.Equal("waypoint_capture_limit_exceeded", error.Message); Assert.Equal(4096, polls.Count);
        Assert.Equal(32, window.Record.CaptureCount); Assert.Empty(window.Record.Samples);
        Assert.Equal(Source(990), window.SeenSource?.WgcSource); Assert.Equal(1, window.Record.ReadCount);
    }

    /// <summary>Selected route is presence-aware and remains in the authenticated replay fingerprint.</summary>
    [Theory]
    [InlineData(null, false)]
    [InlineData("other", false)]
    [InlineData(NavigationBaselineTask.ProfileId, true)]
    [InlineData(NavigationBaselineRouteProfile.TwoLegId, true)]
    public void WireRoutePresenceAndFingerprint(string? route, bool valid)
    {
        var now = DateTimeOffset.UtcNow;
        var data = JsonSerializer.Serialize(new { version = 1, requestId = Guid.NewGuid(),
            createdAtUnixMs = now.ToUnixTimeMilliseconds(), command = "startNavigationBaseline", routeProfile = route,
            timingContract = "v4", capturePolicy = "task_owned_timer", targetProcessId = 20, targetWindowsSessionId = 3, targetNonce = "fixed" });
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes(data), out var request));
        Assert.True(request!.HasRouteProfile);
        Assert.Equal(valid, ExternalControlProtocol.ValidateRequest(request, now) is null);
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(request), ExternalControlProtocol.Fingerprint(request with { RouteProfile = "other-identity" }));
    }

    /// <summary>One public workflow invocation with the explicit new profile.</summary>
    private static Task<NavigationBaselineRunResult> Run(Operations native) => new NavigationBaselineTask(native, "v4",
        "task_owned_timer", NavigationBaselineRouteProfile.TwoLegId).RunAsync(_ => { }, default);

    /// <summary>Real collector on deterministic frames; no native inputs, captures or sleeping.</summary>
    private sealed class Collector
    {
        /// <summary>Virtual monotonic clock and scripted failures.</summary>
        internal double Now = 1100, StageDelayOnce, AnchorOffset;
        /// <summary>One initial source-age rejection.</summary>
        internal bool AgeFirst;
        /// <summary>Optional hard failure after one accepted checkpoint.</summary>
        internal string? Mutation;
        /// <summary>Real fixed collector and global decision sink.</summary>
        internal readonly NavigationBaselineWaypointVerification Window;
        /// <summary>Only committed checkpoint rows.</summary>
        internal readonly List<NavigationBaselineDecision> Decisions = [];
        /// <summary>Unique candidate source index.</summary>
        private int _reads;
        /// <summary>Initialize a release at1000ms and no prior accepted endpoint.</summary>
        internal Collector() => Window = new(() => Now, new("already_released", 1000, 1000), 31000, Source(990), 0, 0);
        /// <summary>Run real bounds/source/admission with synthetic same-frame evidence.</summary>
        internal Task<NavigationBaselineSample> Run() => Window.CollectAsync((anchor, token) =>
        {
            Window.BeginCapture(token); _reads++;
            var at = Now; var attempt = new NavigationBaselineObservationAttempt(Now);
            var leg = anchor ? NavigationBaselineRouteProfile.Second : NavigationBaselineRouteProfile.First;
            var sample = Sample(leg, anchor ? 0 : 1, at);
            if (AgeFirst && _reads == 1) Now += 151;
            if (_reads == 2 && Mutation is not null)
                sample = Mutation switch
                {
                    "layer" => sample with { LayerId = "other", SourceAgeMs = 151 },
                    "motion" => sample with { Motion = sample.Motion with { Status = "fly" }, SourceAgeMs = 151 },
                    "epoch" => sample with { SourceEpoch = Guid.NewGuid() },
                    "regressed" => sample with { SourceTimestamp100ns = Source(989).SourceTimestamp100ns },
                    "spacing" => Sample(leg, 1, Window.Record.Samples[0].AcquiredAtStopwatchTicks!.Value * 1000.0 / Stopwatch.Frequency + 79),
                    "yaw" => sample with { YawDegrees = 48, SourceAgeMs = 151 }, _ => sample
                };
            if (anchor) sample = sample with { X = sample.X + AnchorOffset };
            Window.ValidateSource(sample.Source, "after_capture", attempt, token);
            Window.ValidatePose(sample);
            Window.Admit(sample, attempt, pose =>
            {
                var staged = NavigationBaselineWaypointVerification.StageDecision(pose, Decisions);
                Now += StageDelayOnce; StageDelayOnce = 0; return staged;
            }, () => { }, token);
            return Task.FromResult(sample);
        }, (deadline, _) => { Now = Math.Max(Now, deadline); return Task.CompletedTask; }, default);
    }

    /// <summary>Workflow fake retains the actual waypoint collector; lease races have a separate real-lease test cohort.</summary>
    private sealed class Operations : INavigationBaselineOperations, INavigationBaselineRecoveryOperations,
        INavigationBaselineFinalVerificationOperations, INavigationBaselineWaypointOperations
    {
        /// <summary>One virtual owner clock.</summary>
        public double NowMs { get; private set; } = 1000;
        /// <summary>Explicit fake held state.</summary>
        public bool ForwardHeld { get; private set; }
        /// <summary>No injected lease fault in this boundary fake.</summary>
        public string? Fault => null;
        /// <summary>Fake keyup always completes.</summary>
        public string? ReleaseError => null;
        /// <summary>Immutable selected profile.</summary>
        public string RouteProfileId => NavigationBaselineRouteProfile.TwoLegId;
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
            return Task.FromResult(Sample(_leg == 1 ? NavigationBaselineRouteProfile.First : NavigationBaselineRouteProfile.Second, fraction, NowMs));
        }
        /// <summary>Expose one released3+1 collector under the unchanged original owner deadline.</summary>
        public async Task<NavigationBaselineSample> VerifyWaypointAndAdvanceAsync(double deadline,
            Func<NavigationBaselineSample, NavigationBaselineWaypointVerification.Admission> rows, CancellationToken ct)
        {
            Waypoints++; WaypointDeadline = deadline; ForwardHeld = false;
            if (WaypointFailure is not null) throw new InvalidOperationException(WaypointFailure);
            var window = new NavigationBaselineWaypointVerification(() => NowMs, new("w_up", NowMs, NowMs), deadline, Source(NowMs), 3, 3);
            WaypointRecord = window.Record;
            var anchor = await window.CollectAsync((next, token) =>
            {
                window.BeginCapture(token); NowMs += 120;
                var sample = Sample(next ? NavigationBaselineRouteProfile.Second : NavigationBaselineRouteProfile.First, next ? 0 : 1, NowMs);
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
        { Assert.False(Closed); if (_leg == 2) SecondLegForwards++; ForwardHeld = true; return new("w_down", NowMs, NowMs); }
        /// <summary>Unused aligned synthetic camera path.</summary>
        public NavigationBaselineInputEvent Rotate(NavigationBaselineSample sample, CancellationToken ct) => throw new InvalidOperationException("unexpected_camera");
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
            return Task.FromResult(Sample(NavigationBaselineRouteProfile.First, .5, NowMs));
        }
        /// <summary>Capture exact global decisions without disk files or fake training claims.</summary>
        public Task<NavigationBaselineEvidence> PublishEvidenceAsync(NavigationBaselineRunResult result,
            NavigationBaselineDecision[] decisions, NavigationBaselineScheduleWait[] waits)
        {
            PublishedAfterClose = Closed; Decisions = decisions;
            return Task.FromResult(new NavigationBaselineEvidence(true, "journal", new('a', 64), "initial", new('b', 64), "final", new('c', 64)));
        }
    }
}
