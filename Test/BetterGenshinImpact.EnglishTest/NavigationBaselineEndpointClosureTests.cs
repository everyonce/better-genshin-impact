using System.Diagnostics;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Actual workflow/final-window and pure endpoint predicates; no native capture/input or wall-clock timing.</summary>
public sealed class NavigationBaselineEndpointClosureTests
{
    /// <summary>Stable host generation, shared by each fixture's complete source sequence.</summary>
    private static readonly Guid Epoch = Guid.Parse("3768d164-236a-454e-8124-023935a63401");
    /// <summary>Construct a finite source and actual fixed-corridor position, retaining the original confidence/motion contract.</summary>
    private static NavigationBaselineSample Sample(double fraction, double start = 1000, bool host = true)
    {
        var x = NavigationBaselineTask.StartX + fraction * (NavigationBaselineTask.EndX - NavigationBaselineTask.StartX);
        var y = NavigationBaselineTask.StartY + fraction * (NavigationBaselineTask.EndY - NavigationBaselineTask.StartY);
        var geometry = NavigationBaselineTask.Geometry(x, y);
        var ticks = (long)(start * Stopwatch.Frequency / 1000);
        var value = new NavigationBaselineSample(x, y, 47, DateTimeOffset.UnixEpoch, Epoch,
            host ? null : (long)(start * 10000), host ? null : ticks, .999, .9, "City_102",
            new("normal", AgentMotionEvidence.MethodName, false, false, 1), 10, 47,
            geometry.Distance, geometry.Projection, geometry.CrossTrack, new(start, start, start + 1, start + 10));
        return host ? value with { HostSnapshot = new(Epoch, (long)start, ticks,
            ticks + Stopwatch.Frequency / 1000, Stopwatch.Frequency) } : value;
    }

    /// <summary>One correctly budgeted expiry ticket; only these fake clocks are adjusted by the boundary cases.</summary>
    private static NavigationBaselineEndpointClosure Closure() => new()
    {
        LeaseExpiresAtMs = 1100,
        Pause = new(1, NavigationBaselineRecoveryCause.LeaseExpired, 1101, 1102, null)
        { BudgetKind = NavigationBaselineRecoveryBudgetKind.MovementRecovery, HeldForwardAtEntry = true, MovementRecoveriesUsed = 1 },
        ClosedAtMs = 1102
    };

    /// <summary>Both ordinary and expired host endpoint closure lead only to the existing three-pose final path.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task HostEndpointOnlyClosesAndVerifies(bool expired)
    {
        var operations = new Operations { Expired = expired };
        var result = await new NavigationBaselineTask(operations, NavigationBaselineTiming.V4,
            NavigationBaselineCapturePolicy.TaskOwnedTimer).RunAsync(_ => { }, default);
        Assert.True(result.Verified); Assert.Equal(1, operations.Downs); Assert.Equal(1, operations.EndpointCalls);
        Assert.Equal(0, operations.Recoveries); Assert.Equal(3, operations.FinalReads); Assert.False(operations.ForwardHeld);
        Assert.Equal(expired, result.EndpointClosure is not null);
        Assert.Same(operations.EndpointClosure, result.Evidence!.EndpointClosure);
        Assert.Single(operations.Decisions.Where(row => row.Phase == "releasing"));
    }

    /// <summary>A typed endpoint exception cannot be caught by the ordinary movement-recovery loop.</summary>
    [Fact]
    public async Task EndpointInterruptionIsTerminalAndKeepsTheAcceptedPose()
    {
        var operations = new Operations { EndpointFailure = new NavigationBaselineRecoveryRequired(
            NavigationBaselineRecoveryCause.LeaseExpired, "endpoint", pause: Closure().Pause) };
        var result = await new NavigationBaselineTask(operations, NavigationBaselineTiming.V4,
            NavigationBaselineCapturePolicy.TaskOwnedTimer).RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal(0, operations.Recoveries); Assert.Equal(0, operations.FinalReads);
        Assert.Contains("baseline_recovery_required", result.Error!);
        var endpoint = Assert.Single(operations.Decisions.Where(row => row.Phase == "releasing"));
        Assert.Equal(0, endpoint.Sample.DistanceToEnd); Assert.Null(endpoint.Intent); Assert.True(operations.Closed);
    }

    /// <summary>Ambiguous release never admits final reads or successful route publication.</summary>
    [Fact]
    public async Task ReleaseFailureKeepsEndpointAndStopsBeforeVerification()
    {
        var operations = new Operations { EndpointFailure = new InvalidOperationException("input_release_failed") };
        var result = await new NavigationBaselineTask(operations, NavigationBaselineTiming.V4,
            NavigationBaselineCapturePolicy.TaskOwnedTimer).RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal("input_release_failed", result.Error);
        Assert.Equal(0, operations.Recoveries); Assert.Equal(0, operations.FinalReads); Assert.True(operations.Closed);
        Assert.Single(operations.Decisions.Where(row => row.Phase == "releasing"));
    }

    /// <summary>Reaching the initial endpoint is not proof that the later three fresh poses satisfy the final gate.</summary>
    [Fact]
    public async Task FinalDriftFailsWithoutResumingMovement()
    {
        var operations = new Operations { Expired = true, FinalOffset = 2.01 };
        var result = await new NavigationBaselineTask(operations, NavigationBaselineTiming.V4,
            NavigationBaselineCapturePolicy.TaskOwnedTimer).RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal("endpoint_not_reached", result.Error);
        Assert.Equal(1, operations.Downs); Assert.Equal(0, operations.Recoveries); Assert.Equal(3, operations.FinalReads);
    }

    /// <summary>Unchanged WGC v4 and legacy host-labelled fixtures keep ordinary Close and omit endpoint metadata.</summary>
    [Theory]
    [InlineData(false, "v4", "task_owned_timer")]
    [InlineData(true, "v3", "task_owned_timer")]
    [InlineData(true, "v4", "shared")]
    public async Task OtherContractsNeverEnterEndpointClose(bool host, string timing, string capture)
    {
        var operations = new Operations { Host = host, EndpointFailure = new Exception("unexpected_endpoint_close") };
        var result = await new NavigationBaselineTask(operations, timing, capture).RunAsync(_ => { }, default);
        Assert.True(result.Verified); Assert.Equal(0, operations.EndpointCalls); Assert.Null(result.EndpointClosure);
        Assert.DoesNotContain("endpointClosure", JsonSerializer.Serialize(result));
    }

    /// <summary>The accepted endpoint recheck keeps the existing150ms/source and1.5-unit endpoint boundaries.</summary>
    [Theory]
    [InlineData(1.5, 150, true)]
    [InlineData(1.5001, 150, false)]
    [InlineData(1, 150.001, false)]
    [InlineData(0, 100, true)]
    public void EndpointAdmissionDoesNotRelaxAgeOrDistance(double distance, double age, bool accepted)
    {
        var sample = Sample(1) with { X = NavigationBaselineTask.EndX + distance };
        var rejection = NativeNavigationBaselineOperations.EndpointSampleRejection(sample, sample.Source,
            NavigationBaselineRouteProfile.First, 1000 + age);
        Assert.Equal(accepted, rejection is null);
    }

    /// <summary>Hard source, confidence and motion errors remain terminal before an expiry can be used.</summary>
    [Theory]
    [InlineData("mixed")]
    [InlineData("identity")]
    [InlineData("confidence")]
    [InlineData("motion")]
    [InlineData("wgc")]
    public void HardEndpointEvidenceNeverUsesTheExpiryPath(string change)
    {
        var sample = Sample(1); var previous = sample.Source;
        sample = change switch
        {
            "mixed" => sample with { SourceTimestamp100ns = 1 },
            "identity" => sample with { HostSnapshot = sample.HostSnapshot! with { SnapshotId = 1001 } },
            "confidence" => sample with { PositionConfidence = .5 },
            "motion" => sample with { Motion = sample.Motion with { Status = "climbing" } },
            _ => Sample(1, host: false)
        };
        Assert.NotNull(NativeNavigationBaselineOperations.EndpointSampleRejection(sample, previous,
            NavigationBaselineRouteProfile.First, 1100));
    }

    /// <summary>Use the earlier owner/pause deadline, never closedAt+2000 when the expiry window began earlier.</summary>
    [Theory]
    [InlineData(2900, 2900)]
    [InlineData(5000, 3101)]
    public void FinalWindowRetainsTheOriginalPauseBudget(double ownerDeadline, double expected)
    {
        var closure = Closure(); var now = closure.ClosedAtMs!.Value;
        var clipped = NativeNavigationBaselineOperations.EndpointFinalDeadline(ownerDeadline, closure);
        var collector = new NavigationBaselineFinalVerification(() => now, now, clipped, Sample(1).Source, 0, 0);
        Assert.Equal(expected, collector.Record.DeadlineAtMs);
        now = expected;
        Assert.Throws<NavigationBaselineFinalVerification.TimeoutException>(() => collector.BeginCapture(default));
        Assert.Equal(0, collector.Record.PollCount);
    }

    /// <summary>Missing/failed cleanup metadata cannot begin the final-read window or satisfy owner result consistency.</summary>
    [Theory]
    [InlineData("unconfirmed")]
    [InlineData("failed")]
    [InlineData("cause")]
    [InlineData("late")]
    public void UnconfirmedClosureIsNotSuccess(string change)
    {
        var closure = Closure();
        closure = change switch
        {
            "unconfirmed" => closure with { ClosedAtMs = null },
            "failed" => closure with { Error = "input_release_failed" },
            "cause" => closure with { Pause = closure.Pause with { Cause = NavigationBaselineRecoveryCause.SourceAge } },
            _ => closure with { ClosedAtMs = 3101 }
        };
        Assert.False(closure.ConfirmsClosure);
        Assert.Throws<InvalidOperationException>(() => NativeNavigationBaselineOperations.EndpointFinalDeadline(5000, closure));
        var evidence = new NavigationBaselineEvidence(true, "journal", new('a', 64), "initial", new('b', 64), "final", new('c', 64))
            { EndpointClosure = closure, SourcePolicy = DesktopCapturePolicy.HostAcquisitionV1 };
        Assert.False(NavigationBaselineTaskOwner.EndpointClosureConsistent(new()
        {
            EndpointClosure = closure, Evidence = evidence, SourcePolicy = DesktopCapturePolicy.HostAcquisitionV1,
            TimingContract = NavigationBaselineTiming.V4, CapturePolicy = NavigationBaselineCapturePolicy.TaskOwnedTimer
        }));
    }

    /// <summary>Workflow stub counts every movement/final boundary while the actual task owns decision and failure handling.</summary>
    private sealed class Operations : INavigationBaselineOperations, INavigationBaselineRecoveryOperations, INavigationBaselineFinalVerificationOperations
    {
        /// <summary>Fixture selection; legacy paths must not call the new endpoint method.</summary>
        internal bool Host = true, Expired, Closed;
        /// <summary>Optional terminal closure failure, never a physical native error claim.</summary>
        internal Exception? EndpointFailure;
        /// <summary>Allows the actual final pose gate to reject drift without movement retry.</summary>
        internal double FinalOffset;
        /// <summary>Actual task-call counts and detached published decisions.</summary>
        internal int Downs, Recoveries, EndpointCalls, FinalReads;
        /// <summary>Exact workflow decisions supplied to fake publication.</summary>
        internal NavigationBaselineDecision[] Decisions = [];
        /// <summary>Monotonic synthetic workflow clock.</summary>
        private double _now = 1000;
        /// <summary>The chosen source family is never inferred from null clocks.</summary>
        public string? SourcePolicy => Host ? DesktopCapturePolicy.HostAcquisitionV1 : null;
        /// <summary>All fixture stages use one clock.</summary>
        public double NowMs => _now;
        /// <summary>Simple fake held state, permanently cleared by closure.</summary>
        public bool ForwardHeld { get; private set; }
        /// <summary>No hidden native fault; each injected failure is thrown explicitly.</summary>
        public string? Fault => null;
        /// <summary>The stub's ordinary cleanup succeeds, but cannot erase EndpointFailure.</summary>
        public string? ReleaseError => null;
        /// <summary>Only a selected expired endpoint creates a fixture ticket.</summary>
        public NavigationBaselineEndpointClosure? EndpointClosure { get; private set; }
        /// <summary>No native asset preparation.</summary>
        public Task PrepareAsync(CancellationToken ct) => Task.CompletedTask;
        /// <summary>One initial pose, then endpoint; legacy final reads remain separate.</summary>
        public Task<NavigationBaselineSample> ReadPoseAsync(string? retainImage, CancellationToken ct)
        {
            _now += 100;
            if (retainImage == "final") FinalReads++;
            return Task.FromResult(retainImage == "final" ? FinalSample() : Sample(retainImage == "initial" ? 0 : 1, _now - 10, Host));
        }
        /// <summary>The real task must close before requesting final evidence.</summary>
        public Task ReadFinalSamplesAsync(double deadline, Func<NavigationBaselineSample, NavigationBaselineFinalVerification.Admission> stageRows, CancellationToken ct)
        {
            Assert.True(Closed); Assert.False(ForwardHeld);
            for (var i = 0; i < 3; i++)
            {
                _now += 100; FinalReads++;
                var admission = stageRows(FinalSample());
                admission.Commit();
            }
            return Task.CompletedTask;
        }
        /// <summary>Offset final verification across the corridor, leaving its projection and original endpoint read unchanged.</summary>
        private NavigationBaselineSample FinalSample()
        {
            var sample = Sample(1, _now - 10, Host);
            return sample with
            {
                X = sample.X - FinalOffset * (NavigationBaselineTask.EndY - NavigationBaselineTask.StartY) / NavigationBaselineTask.Length,
                Y = sample.Y + FinalOffset * (NavigationBaselineTask.EndX - NavigationBaselineTask.StartX) / NavigationBaselineTask.Length
            };
        }
        /// <summary>Only enables the fixture's travel contract.</summary>
        public void EnableRecovery() => Assert.False(Closed);
        /// <summary>Any endpoint path reaching movement recovery is a regression.</summary>
        public Task<NavigationBaselineSample> RecoverAsync(NavigationBaselineRecoveryRequired interruption, double deadline, CancellationToken ct)
        { Recoveries++; throw new InvalidOperationException("unexpected_movement_recovery"); }
        /// <summary>Aligned fixture never needs rotation.</summary>
        public NavigationBaselineInputEvent Rotate(NavigationBaselineSample sample, CancellationToken ct) => throw new InvalidOperationException("unexpected_rotation");
        /// <summary>Exactly one travel down precedes the endpoint; permanent close is asserted.</summary>
        public NavigationBaselineInputEvent Forward(NavigationBaselineSample sample, CancellationToken ct)
        { Assert.False(Closed); Downs++; ForwardHeld = true; return new("w_down", _now, _now); }
        /// <summary>No fixture realignment, retained only to satisfy the original boundary.</summary>
        public NavigationBaselineInputEvent ReleaseForward() { ForwardHeld = false; return new("w_up", _now, _now); }
        /// <summary>Original finally cleanup stays idempotent.</summary>
        public void CloseInput() { Closed = true; ForwardHeld = false; }
        /// <summary>Typed and ordinary closure failures are injected after the task has staged its endpoint decision.</summary>
        public void CloseAtEndpoint(NavigationBaselineSample sample, CancellationToken ct)
        {
            EndpointCalls++;
            if (EndpointFailure is not null) throw EndpointFailure;
            CloseInput();
            if (Expired) EndpointClosure = Closure();
        }
        /// <summary>No real delay or clock catch-up.</summary>
        public Task WaitUntilAsync(double deadline, CancellationToken ct) { _now = Math.Max(_now, deadline); return Task.CompletedTask; }
        /// <summary>Capture the real task output without local files or physical image claims.</summary>
        public Task<NavigationBaselineEvidence> PublishEvidenceAsync(NavigationBaselineRunResult result, NavigationBaselineDecision[] decisions, NavigationBaselineScheduleWait[] waits)
        {
            Decisions = decisions;
            return Task.FromResult(new NavigationBaselineEvidence(true, "journal", new('a', 64), "initial", new('b', 64), "final", new('c', 64))
                { SourcePolicy = SourcePolicy, EndpointClosure = EndpointClosure });
        }
    }
}
