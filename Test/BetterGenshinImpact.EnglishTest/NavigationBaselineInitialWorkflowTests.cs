using System.Diagnostics;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Actual workflow and initial collector composition with deterministic native-boundary fakes.</summary>
public sealed class NavigationBaselineInitialWorkflowTests
{
    /// <summary>Preparation consumes the original owner budget; only the fresh initial pose permits recovery/input admission.</summary>
    [Fact]
    public async Task OriginalDeadlineSurvivesPreparationAndDiscard()
    {
        var operations = new Operations();
        var result = await new NavigationBaselineTask(operations, "v4").RunAsync(_ => { }, default);
        Assert.Equal(31000, operations.InitialDeadline); Assert.Equal(2, operations.Window!.Record.ReadCount);
        Assert.Equal(4000, operations.Window.Record.DeadlineAtMs); Assert.Equal(1, operations.Recognized);
        Assert.Equal(1, operations.Downs); Assert.True(operations.EnabledAfterFresh); Assert.True(operations.PublishedAfterClose);
        Assert.Equal("test_stopped_after_first_input", result.Error); Assert.NotNull(result.InitialSample);
    }

    /// <summary>The existing start-region requirement is not weakened by successfully waiting for fresh pixels.</summary>
    [Fact]
    public async Task FreshInitialStillMustPassStartAnchorBeforeInput()
    {
        var operations = new Operations { StartOffset = 2 };
        var result = await new NavigationBaselineTask(operations, "v4").RunAsync(_ => { }, default);
        Assert.Equal("start_not_at_anchor", result.Error); Assert.Equal(0, operations.Downs);
        Assert.False(operations.EnabledAfterFresh); Assert.True(operations.PublishedAfterClose);
    }

    /// <summary>A valid fresh frame with hard world/motion/pose failure remains terminal, even after an earlier age discard.</summary>
    [Theory]
    [InlineData("world_not_ready")][InlineData("chat_not_closed")][InlineData("non_normal_motion")]
    public async Task HardFailureAfterDiscardDoesNotEnableRecoveryOrInput(string error)
    {
        var operations = new Operations { RecognitionFailure = error };
        var result = await new NavigationBaselineTask(operations, "v4").RunAsync(_ => { }, default);
        Assert.Equal(error, result.Error); Assert.Equal(2, operations.Window!.Record.ReadCount);
        Assert.Equal(0, operations.Downs); Assert.False(operations.EnabledAfterFresh); Assert.True(operations.PublishedAfterClose);
    }

    /// <summary>Legacy contracts never call the new optional boundary, and retain the prior initial image request.</summary>
    [Theory]
    [InlineData("v1")][InlineData("v2")][InlineData("v3")]
    public async Task LegacyInitialPathIsUnchanged(string contract)
    {
        var operations = new Operations();
        await new NavigationBaselineTask(operations, contract).RunAsync(_ => { }, default);
        Assert.Null(operations.InitialDeadline); Assert.Null(operations.Window); Assert.Equal(1, operations.LegacyReads);
        Assert.Equal("initial", operations.LastRetainImage); Assert.Equal(1, operations.Downs);
    }

    /// <summary>The default interface method keeps existing fakes/adapters strict without requiring a new implementation.</summary>
    [Fact]
    public async Task DefaultBoundaryForwardsToExistingStrictRead()
    {
        var operations = new LegacyOperations(); INavigationBaselineOperations boundary = operations;
        await boundary.ReadInitialPoseAsync(31000, default);
        Assert.Equal("initial", operations.RetainImage); Assert.Equal(1, operations.Reads);
    }

    /// <summary>Wrapped local cancellation keeps its fixed timeout code through the real workflow catch/publication.</summary>
    [Fact]
    public async Task InitialDeadlineCodeSurvivesWrappedCancellation()
    {
        var operations = new Operations { InitialFailure = new NavigationBaselineInitialReadiness.DeadlineException(new OperationCanceledException()) };
        var result = await new NavigationBaselineTask(operations, "v4").RunAsync(_ => { }, default);
        Assert.Equal("initial_readiness_deadline_exceeded", result.Error); Assert.Equal(0, operations.Downs);
        Assert.True(operations.PublishedAfterClose);
    }

    /// <summary>A fixed initial pose from one immutable source, never a retained or synthetic fallback for native execution.</summary>
    private static NavigationBaselineSample Sample(double now, double offset = 0)
    {
        var source = new GameCaptureSourceInfo(Guid.Parse("713e569b-05ac-4a78-aadf-8a29455fcd92"),
            (long)((now - 5) * 10000), (long)((now - 5) * Stopwatch.Frequency / 1000));
        return new(NavigationBaselineTask.StartX + offset, NavigationBaselineTask.StartY, 47, DateTimeOffset.UnixEpoch,
            source.CaptureEpoch, source.SourceTimestamp100ns, source.AcquiredAtStopwatchTicks, .999, .8, "City_102",
            new("normal", AgentMotionEvidence.MethodName, false, false, 1), 5, 47, NavigationBaselineTask.Length, 0, 0,
            new(now, now, now, now));
    }

    /// <summary>Default-interface fixture with no window implementation.</summary>
    private class LegacyOperations : INavigationBaselineOperations
    {
        /// <summary>Deterministic owner clock.</summary>
        public double NowMs { get; protected set; } = 1000;
        /// <summary>No real key state is owned by this fixture.</summary>
        public bool ForwardHeld => false;
        /// <summary>No concurrent native fault.</summary>
        public string? Fault => null;
        /// <summary>No native release call is performed.</summary>
        public string? ReleaseError => null;
        /// <summary>Old boundary call evidence.</summary>
        internal int Reads;
        /// <summary>Exact original image retention request.</summary>
        internal string? RetainImage;
        /// <summary>Cleanup precedes publication even after a failed initial observation.</summary>
        internal bool Closed, PublishedAfterClose;
        /// <summary>Preparation deliberately consumes part of the original owner interval.</summary>
        public Task PrepareAsync(CancellationToken ct) { NowMs += 1000; return Task.CompletedTask; }
        /// <summary>The unchanged strict legacy read.</summary>
        public virtual Task<NavigationBaselineSample> ReadPoseAsync(string? retainImage, CancellationToken ct)
        { Reads++; RetainImage = retainImage; return Task.FromResult(Sample(NowMs)); }
        /// <summary>Unexpected camera commands are not hidden by the fixture.</summary>
        public NavigationBaselineInputEvent Rotate(NavigationBaselineSample sample, CancellationToken ct) => throw new InvalidOperationException("unexpected_camera");
        /// <summary>Stop after proving that the workflow reached its first input boundary.</summary>
        public virtual NavigationBaselineInputEvent Forward(NavigationBaselineSample sample, CancellationToken ct) => throw new InvalidOperationException("test_stopped_after_first_input");
        /// <summary>No actual key release.</summary>
        public NavigationBaselineInputEvent ReleaseForward() => new("already_released", NowMs, NowMs);
        /// <summary>Permanent fixture cleanup.</summary>
        public void CloseInput() => Closed = true;
        /// <summary>No real timer execution.</summary>
        public Task WaitUntilAsync(double deadlineMs, CancellationToken ct) { NowMs = deadlineMs; return Task.CompletedTask; }
        /// <summary>Observe real workflow publication ordering while returning a synthetic evidence identity.</summary>
        public Task<NavigationBaselineEvidence> PublishEvidenceAsync(NavigationBaselineRunResult result, NavigationBaselineDecision[] decisions,
            NavigationBaselineScheduleWait[] scheduleWaits)
        {
            PublishedAfterClose = Closed;
            return Task.FromResult(new NavigationBaselineEvidence(true, "journal", new string('a', 64), null, null, null, null));
        }
    }

    /// <summary>Explicitly reimplement the interface so its optional method dispatches to the production initial collector.</summary>
    private sealed class Operations : LegacyOperations, INavigationBaselineOperations, INavigationBaselineRecoveryOperations
    {
        /// <summary>Exact deadline supplied by the real workflow.</summary>
        internal double? InitialDeadline;
        /// <summary>Actual collector evidence, including the discarded old capture.</summary>
        internal NavigationBaselineInitialReadiness? Window;
        /// <summary>Only code beyond successful capture admission counts as recognition.</summary>
        internal int Recognized, Downs, LegacyReads;
        /// <summary>Selected failing recognition, if any.</summary>
        internal string? RecognitionFailure, LastRetainImage;
        /// <summary>One direct boundary error for workflow exception-code coverage.</summary>
        internal Exception? InitialFailure;
        /// <summary>Demonstrate the unchanged initial anchor tolerance.</summary>
        internal double StartOffset;
        /// <summary>Recovery can only be enabled after the collector completed a fresh pose.</summary>
        internal bool EnabledAfterFresh;
        /// <summary>The default/legacy workflow never dispatches the optional initial method.</summary>
        public override Task<NavigationBaselineSample> ReadPoseAsync(string? retainImage, CancellationToken ct)
        { LegacyReads++; LastRetainImage = retainImage; return base.ReadPoseAsync(retainImage, ct); }
        /// <summary>Run the real collector/header/age checks with one stale then one fresh returned source.</summary>
        public Task<NavigationBaselineSample> ReadInitialPoseAsync(double ownerDeadlineMs, CancellationToken ct)
        {
            InitialDeadline = ownerDeadlineMs;
            if (InitialFailure is not null) throw InitialFailure;
            var window = Window = new(() => NowMs, ownerDeadlineMs, 0, 0, "task_owned_timer");
            return window.ReadAsync(token =>
            {
                using var reservation = window.BeginCapture(token); reservation.CompleteCapture();
                var sample = Sample(window.Record.ReadCount == 1 ? NowMs - 500 : NowMs, StartOffset);
                window.ValidateHeader(sample.Source, 1920, 1080, 3, token);
                window.ValidateSource(sample.Source, "after_capture", window.Record.ReadCount - 1, window.Record.PollCount - 1, token);
                Recognized++;
                if (RecognitionFailure is not null) throw new InvalidOperationException(RecognitionFailure);
                return Task.FromResult(sample);
            }, WaitUntilAsync, ct);
        }
        /// <summary>Prove collector completion precedes recovery admission.</summary>
        public void EnableRecovery() => EnabledAfterFresh = Window?.Record.Outcome == "completed" && Downs == 0;
        /// <summary>Initial-window failures must never use travel recovery.</summary>
        public Task<NavigationBaselineSample> RecoverAsync(NavigationBaselineRecoveryRequired interruption, double deadline, CancellationToken ct) =>
            throw new InvalidOperationException("unexpected_travel_recovery");
        /// <summary>Only a fully admitted initial pose can reach the real workflow's movement call.</summary>
        public override NavigationBaselineInputEvent Forward(NavigationBaselineSample sample, CancellationToken ct)
        { Downs++; return base.Forward(sample, ct); }
    }
}
