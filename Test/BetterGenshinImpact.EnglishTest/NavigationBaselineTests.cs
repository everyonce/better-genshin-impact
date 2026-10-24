using System.Diagnostics;
using System.IO;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.GameTask.SoloTask.Execution;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Fixed-leg geometry, evidence, ownership and fake-native workflow checks; no game/input/GPU actions.</summary>
public sealed class NavigationBaselineTests
{
    /// <summary>Stable synthetic native generation.</summary>
    private static readonly Guid Epoch = Guid.Parse("d84d7ca8-5d37-4acb-883c-873b709c2b98");
    /// <summary>Build a finite native-clock sample at a route fraction, with known same-frame confidence.</summary>
    private static NavigationBaselineSample Sample(double fraction, double atMs = 1000)
    {
        var x = NavigationBaselineTask.StartX + fraction * (NavigationBaselineTask.EndX - NavigationBaselineTask.StartX);
        var y = NavigationBaselineTask.StartY + fraction * (NavigationBaselineTask.EndY - NavigationBaselineTask.StartY);
        var geometry = NavigationBaselineTask.Geometry(x, y);
        return new(x, y, 47, DateTimeOffset.UtcNow, Epoch, (long)(atMs * 10_000),
            (long)(atMs * Stopwatch.Frequency / 1000), 0.999, 0.8, "City_102",
            new("normal", AgentMotionEvidence.MethodName, false, false, 1), 10, 47,
            geometry.Distance, geometry.Projection, geometry.CrossTrack, new(atMs, atMs, atMs + 1, atMs + 2));
    }
    /// <summary>Complete synthetic local artifact references; tests never create these files.</summary>
    private static NavigationBaselineEvidence Evidence(bool complete = true) => new(complete, @"D:\synthetic\journal.json", new('A', 64),
        @"D:\synthetic\initial.png", new('B', 64), @"D:\synthetic\final.png", new('C', 64));
    /// <summary>Valid owner result for deterministic cleanup/cancellation tests.</summary>
    private static NavigationBaselineRunResult ValidResult()
    {
        var samples = new[] { Sample(1, 2000), Sample(1, 2120), Sample(1, 2240) };
        return new() { Verified = true, Phase = "completed", InitialSample = Sample(0), Samples = samples,
            VerificationSamples = samples, ObservationCount = 6, Evidence = Evidence(), ElapsedMs = 1500 };
    }
    /// <summary>Wait only for local test task completion, with a generous failure bound instead of performance assertions.</summary>
    private static async Task WaitForOwner(NavigationBaselineTaskOwner owner)
    {
        var end = Stopwatch.StartNew();
        while (owner.Running && end.Elapsed < TimeSpan.FromSeconds(5)) await Task.Delay(1);
        Assert.False(owner.Running);
    }

    /// <summary>A result produced under another timing contract cannot satisfy a v2 owner, even with valid poses.</summary>
    [Fact]
    public async Task OwnerRejectsTimingContractMismatch()
    {
        var owner = new NavigationBaselineTaskOwner();
        Assert.True(owner.TryStart(10, 3, (_, _, _) => Task.FromResult((new SoloTaskRunResult
            { Outcome = SoloTaskRunOutcome.Completed }, (NavigationBaselineRunResult?)ValidResult())),
            timingContract: NavigationBaselineTiming.V2));
        await WaitForOwner(owner);
        var status = owner.Snapshot(true);
        Assert.Equal("failed", status.State); Assert.Equal("baseline_timing_contract_mismatch", status.Error);
        Assert.Equal("v2", status.TimingContract); Assert.Equal("v1", status.Result!.TimingContract);
        Assert.False(status.Result.Verified); Assert.Empty(status.Result.Samples);
    }

    /// <summary>Workflow evidence preserves the selected controller identity through both success and failure.</summary>
    [Fact]
    public async Task WorkflowCarriesV2Identity()
    {
        var operations = new FakeOperations();
        var result = await new NavigationBaselineTask(operations, NavigationBaselineTiming.V2).RunAsync(_ => { }, default);
        Assert.Equal("v2", result.TimingContract);
        Assert.Equal("native-fixed-leg-feedback-v2", result.ControllerMethod);
    }

    /// <summary>Task policy labels are independent of timing and survive measured workflow success.</summary>
    [Theory]
    [InlineData("v1", "shared")]
    [InlineData("v2", "shared")]
    [InlineData("v1", "task_owned_timer")]
    [InlineData("v2", "task_owned_timer")]
    [InlineData("v3", "shared")]
    [InlineData("v3", "task_owned_timer")]
    public async Task WorkflowCarriesIndependentCapturePolicy(string timing, string capturePolicy)
    {
        var operations = new FakeOperations();
        var result = await new NavigationBaselineTask(operations, timing, capturePolicy).RunAsync(_ => { }, default);
        Assert.True(result.Verified); Assert.Equal(timing, result.TimingContract);
        Assert.Equal(capturePolicy, result.CapturePolicy); Assert.True(operations.Closed);
    }

    /// <summary>Valid shared-capture poses cannot be reported as an owned-timer run; retain the mismatching evidence on failure.</summary>
    [Fact]
    public async Task OwnerRejectsCapturePolicyMismatch()
    {
        var owner = new NavigationBaselineTaskOwner();
        Assert.True(owner.TryStart(10, 3, (_, _, _) => Task.FromResult((new SoloTaskRunResult
            { Outcome = SoloTaskRunOutcome.Completed }, (NavigationBaselineRunResult?)ValidResult())),
            capturePolicy: NavigationBaselineCapturePolicy.TaskOwnedTimer));
        await WaitForOwner(owner);
        var status = owner.Snapshot(true);
        Assert.Equal("failed", status.State); Assert.Equal("baseline_capture_policy_mismatch", status.Error);
        Assert.Equal("task_owned_timer", status.CapturePolicy); Assert.Equal("shared", status.Result!.CapturePolicy);
        Assert.False(status.Result.Verified); Assert.Empty(status.Result.Samples);
        Assert.Equal(3, status.Result.VerificationSamples.Length);
    }

    /// <summary>The reviewed route's bytes and coordinates are immutable input provenance, not a route-execution command.</summary>
    [Fact]
    public void ShippedLegProfileAndTamperDetection()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null && !File.Exists(Path.Combine(directory.FullName, "BetterGenshinImpact.sln"))) directory = directory.Parent;
        Assert.NotNull(directory);
        var bytes = File.ReadAllBytes(Path.Combine(directory!.FullName, "BetterGenshinImpact", "GameTask", "Common", "Element", "Assets", "Json", "合成台_蒙德.json"));
        NativeNavigationBaselineOperations.ValidateRoute(bytes);
        bytes[0] ^= 1;
        Assert.Throws<InvalidOperationException>(() => NativeNavigationBaselineOperations.ValidateRoute(bytes));
        Assert.InRange(NavigationBaselineTask.Length, 9.807, 9.809);
        var start = NavigationBaselineTask.Geometry(NavigationBaselineTask.StartX, NavigationBaselineTask.StartY);
        Assert.Equal(0, start.Projection); Assert.Equal(0, start.CrossTrack);
        var end = NavigationBaselineTask.Geometry(NavigationBaselineTask.EndX, NavigationBaselineTask.EndY);
        Assert.Equal(0, end.Distance); Assert.Equal(NavigationBaselineTask.Length, end.Projection, 8);
    }

    /// <summary>Pose gates reject confidence, layer and motion errors instead of treating normal as proven footing.</summary>
    [Theory]
    [InlineData("confidence", "invalid_position_confidence")]
    [InlineData("yaw", "invalid_yaw_confidence")]
    [InlineData("layer", "wrong_layer")]
    [InlineData("climb", "non_normal_motion")]
    [InlineData("fly", "non_normal_motion")]
    [InlineData("unknown", "non_normal_motion")]
    [InlineData("space", "non_normal_motion")]
    [InlineData("stale", "native_source_stale")]
    [InlineData("corridor", "route_corridor_exceeded")]
    public void RejectUnusablePose(string mutation, string expected)
    {
        var sample = Sample(0.4);
        sample = mutation switch
        {
            "confidence" => sample with { PositionConfidence = 0.989 },
            "yaw" => sample with { YawConfidence = 0.199 },
            "layer" => sample with { LayerId = "underground" },
            "space" => sample with { Motion = sample.Motion with { SpaceKeyMatched = true } },
            "stale" => sample with { SourceAgeMs = 150.001 },
            "corridor" => sample with { X = sample.X + 10 },
            _ => sample with { Motion = sample.Motion with { Status = mutation } }
        };
        Assert.Equal(expected, NavigationBaselineTask.PoseRejection(sample));
    }

    /// <summary>Future compositor timestamps remain anchored to first acquisition; both clocks must clear response barriers.</summary>
    [Theory]
    [InlineData(60, 60, true)]
    [InlineData(59, 60, false)]
    [InlineData(60, 59, false)]
    public void BothSourceClocksMustClearWResponse(double reportedDelta, double acquisitionDelta, bool accepted)
    {
        var source = new GameCaptureSourceInfo(Epoch, (long)((1000 + reportedDelta) * 10_000),
            (long)((1000 + acquisitionDelta) * Stopwatch.Frequency / 1000));
        Assert.Equal(accepted, NavigationBaselineTask.AfterBarrier(source, 1000, 60));
        Assert.False(NavigationBaselineTask.AfterBarrier(source, 1000, 80));
        var future = new GameCaptureSourceInfo(Epoch, 1300 * 10_000, (long)(1000.0 * Stopwatch.Frequency / 1000));
        Assert.Equal(150, NavigationBaselineTask.SourceAge(future, 1150), 6);
        Assert.True(double.IsNaN(NavigationBaselineTask.SourceAge(future, 999)));
    }

    /// <summary>Resize-generation/reordered sources are terminal; equality permits waiting but never a new measurement.</summary>
    [Fact]
    public void SourceIdentityRejectsEpochAndEitherClockRegression()
    {
        var source = Sample(0).Source;
        Assert.Null(NativeNavigationBaselineOperations.SourceIdentityRejection(source, source));
        Assert.Equal("source_epoch_changed", NativeNavigationBaselineOperations.SourceIdentityRejection(source with { CaptureEpoch = Guid.NewGuid() }, source));
        Assert.Equal("native_source_regressed", NativeNavigationBaselineOperations.SourceIdentityRejection(source with { SourceTimestamp100ns = source.SourceTimestamp100ns - 1 }, source));
        Assert.Equal("native_source_regressed", NativeNavigationBaselineOperations.SourceIdentityRejection(source with { AcquiredAtStopwatchTicks = source.AcquiredAtStopwatchTicks - 1 }, source));
    }

    /// <summary>Stable cached pixels, close acquisition spacing and endpoint drift never establish successful arrival.</summary>
    [Theory]
    [InlineData("duplicate", "source_not_increasing")]
    [InlineData("spacing", "acquisition_spacing_too_short")]
    [InlineData("yaw", "yaw_spread_exceeded")]
    [InlineData("endpoint", "endpoint_not_reached")]
    [InlineData("spread", "position_spread_exceeded")]
    public void FinalClusterRemainsStrict(string mutation, string expected)
    {
        var samples = new[] { Sample(1, 1000), Sample(1, 1120), Sample(1, 1240) };
        Assert.Null(NavigationBaselineTask.FinalRejection(samples));
        if (mutation == "duplicate") samples[1] = samples[0];
        if (mutation == "spacing") samples[1] = Sample(1, 1079);
        if (mutation == "yaw") samples[1] = samples[1] with { YawDegrees = 49.01 };
        if (mutation == "endpoint") samples[1] = Sample(1 - 2.01 / NavigationBaselineTask.Length, 1120);
        if (mutation == "spread") { samples[0] = samples[0] with { X = samples[0].X - 0.8 }; samples[1] = samples[1] with { X = samples[1].X + 0.8 }; }
        Assert.Equal(expected, NavigationBaselineTask.FinalRejection(samples));
    }

    /// <summary>Success closes input before the three final reads and evidence publication; no reset or recovery operation exists.</summary>
    [Fact]
    public async Task WorkflowMeasuresArrivalOnlyAfterRelease()
    {
        var operations = new FakeOperations();
        var result = await new NavigationBaselineTask(operations).RunAsync(_ => { }, default);
        Assert.True(result.Verified); Assert.True(result.Evidence!.Complete); Assert.Equal(3, result.Samples.Length);
        Assert.Equal(result.Samples, result.VerificationSamples); Assert.True(operations.PublishedAfterClosed);
        Assert.Equal(1, operations.Downs); Assert.Equal(1, operations.Ups); Assert.Equal(0, operations.Rotations);
        Assert.Equal(3, operations.FinalReads); Assert.All(operations.FinalReadClosed, value => Assert.True(value));
        Assert.True(NavigationBaselineTask.AfterBarrier(result.Samples[0].Source, operations.ClosedAt, 80));
        Assert.True(NavigationBaselineTask.FinalRejection(result.Samples) is null);
    }

    /// <summary>Alignment first releases an active hold, then waits for response evidence before horizontal camera input.</summary>
    [Fact]
    public async Task RealignmentReleasesBeforeCameraAndDoesNotRepeatKeydownOnRenewal()
    {
        var operations = new FakeOperations { SampleAt = (index, sample) => index == 1 ? sample with { YawDegrees = 100 }
            : index == 2 ? Sample(0.65, sample.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency) with { YawDegrees = 100 } : sample };
        var result = await new NavigationBaselineTask(operations).RunAsync(_ => { }, default);
        Assert.True(result.Verified);
        Assert.Equal(new[] { "w_down", "w_up", "camera" }, operations.ControlKinds.Take(3));
        Assert.False(operations.CameraWhileHeld);
        Assert.All(operations.RealInputBarriers, item => Assert.True(item.AfterMs - item.BeforeMs >= item.RequiredMs));
    }

    /// <summary>A bad first pose cannot trigger any baseline input; native read errors are never retried.</summary>
    [Theory]
    [InlineData("motion")]
    [InlineData("anchor")]
    [InlineData("native")]
    public async Task InitialFailureHasNoInputOrRetry(string kind)
    {
        var operations = new FakeOperations { ReadError = kind == "native" ? "world_not_ready" : null,
            SampleAt = (_, sample) => kind == "motion" ? sample with { Motion = sample.Motion with { Status = "climb" } }
                : kind == "anchor" ? Sample(0.3, sample.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency) : sample };
        var result = await new NavigationBaselineTask(operations).RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal(0, operations.Downs); Assert.Equal(0, operations.Rotations);
        Assert.Equal(1, operations.ReadCount); Assert.True(operations.Closed); Assert.NotNull(result.Error);
    }

    /// <summary>Failed final verification retains all three observations and never returns to driving or retries the cluster.</summary>
    [Fact]
    public async Task FailedFinalClusterRetainsEvidenceWithoutMoreInput()
    {
        var operations = new FakeOperations { SampleAt = (index, sample) => index == 4 ? sample with { YawDegrees = 55 } : sample };
        var result = await new NavigationBaselineTask(operations).RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Empty(result.Samples); Assert.Equal(3, result.VerificationSamples.Length);
        Assert.Equal("yaw_spread_exceeded", result.Error); Assert.Equal(6, operations.ReadCount);
        Assert.Equal(1, operations.Downs); Assert.Equal(1, operations.Ups);
    }

    /// <summary>Cancellation during observation still releases before publishing failure evidence.</summary>
    [Fact]
    public async Task CancellationReleasesAndCannotPublishSuccess()
    {
        using var cancel = new CancellationTokenSource();
        var operations = new FakeOperations { OnRead = index => { if (index == 1) cancel.Cancel(); } };
        var result = await new NavigationBaselineTask(operations).RunAsync(_ => { }, cancel.Token);
        Assert.False(result.Verified); Assert.Equal("baseline_cancelled", result.Error);
        Assert.Equal(1, operations.Downs); Assert.Equal(1, operations.Ups); Assert.True(operations.PublishedAfterClosed);
    }

    /// <summary>Recognition consumes cadence; forged sample diagnostic clocks cannot move the actual workflow deadline.</summary>
    [Fact]
    public async Task CadenceUsesReadEntryAndIncludesRecognitionWork()
    {
        var operations = new FakeOperations { ReadWorkMs = _ => 30,
            SampleAt = (_, sample) => sample with { Timing = sample.Timing with { ObservationStartedAtMs = -5000 } } };
        var result = await new NavigationBaselineTask(operations).RunAsync(_ => { }, default);
        Assert.True(result.Verified);
        Assert.Equal(new[] { 1000d, 1050d }, operations.ReadEntries.Take(2));
        var wait = operations.SavedWaits[0];
        Assert.Equal(1000, wait.PreviousObservationStartedAtMs); Assert.Equal(1050, wait.RequestedDeadlineMs);
        Assert.Equal(1031, wait.StartedAtMs); Assert.Equal(1050, wait.ExitedAtMs); Assert.Null(wait.Error);
        Assert.All(operations.RealInputBarriers, barrier => Assert.True(barrier.AfterMs - barrier.BeforeMs >= barrier.RequiredMs));
    }

    /// <summary>A late read starts the next observation once; its actual entry replaces the expired cadence anchor.</summary>
    [Fact]
    public async Task CadenceOverrunDoesNotAccumulateCatchUpDeadlines()
    {
        var operations = new FakeOperations { ReadWorkMs = index => index == 0 ? 120 : 0,
            SampleAt = (index, sample) => index == 2 ? Sample(0.65, sample.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency) : sample };
        var result = await new NavigationBaselineTask(operations).RunAsync(_ => { }, default);
        Assert.True(result.Verified);
        Assert.Equal(new[] { 1000d, 1121d, 1181d, 1231d }, operations.ReadEntries.Take(4));
        Assert.Equal(new[] { 1050d, 1171d, 1231d }, operations.SavedWaits.Select(wait => wait.RequestedDeadlineMs));
        Assert.Equal(1, operations.Downs); Assert.Equal(new[] { "w_down", "renew_w", "renew_w" }, operations.ControlKinds);
    }

    /// <summary>A cancelled/expired pacing wait keeps its deadline and actual exit even though no later read starts.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task FailedCadenceWaitRetainsEvidenceAndReleases(bool cancelled)
    {
        var operations = new FakeOperations { WaitError = cancelled ? new OperationCanceledException("synthetic wait cancellation")
            : new InvalidOperationException("forward_lease_expired"), WaitOverrunMs = 7 };
        var result = await new NavigationBaselineTask(operations).RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal(cancelled ? "baseline_cancelled" : "forward_lease_expired", result.Error);
        Assert.Equal(1, operations.ReadCount); Assert.Equal(1, operations.Downs); Assert.Equal(1, operations.Ups);
        Assert.True(operations.PublishedAfterClosed);
        var wait = Assert.Single(operations.SavedWaits);
        Assert.Equal(1000, wait.PreviousObservationStartedAtMs); Assert.Equal(1050, wait.RequestedDeadlineMs);
        Assert.Equal(1057, wait.ExitedAtMs); Assert.Equal(operations.WaitError.Message, wait.Error);
    }

    /// <summary>The production diagnostic wrapper closes an interrupted attempt and preserves its original stage/error.</summary>
    [Theory]
    [InlineData("capturing")]
    [InlineData("waiting_source")]
    [InlineData("recognizing_position")]
    public async Task FailedNativeAttemptIsRetainedWithSourceAndPollCounts(string stage)
    {
        var attempts = new List<NavigationBaselineObservationAttempt>();
        var finish = new TaskCompletionSource<NavigationBaselineSample>(TaskCreationOptions.RunContinuationsAsynchronously);
        double now = 1000;
        var pending = NativeNavigationBaselineOperations.RecordObservationAsync(attempts, () => now, () => "forward_lease_expired", attempt =>
        {
            attempt.Stage = stage; attempt.CaptureStartedAtMs = 1020; attempt.CaptureCount = 4;
            attempt.DuplicateCount = 2; attempt.BarrierCount = 3; attempt.LastReturnedSource = Sample(0, 1010).Source;
            if (stage != "capturing") attempt.CaptureReturnedAtMs = 1025;
            if (stage == "recognizing_position") attempt.RecognitionStartedAtMs = 1026;
            return finish.Task;
        });
        var retained = Assert.Single(attempts); Assert.Null(retained.EndedAtMs);
        var failure = new OperationCanceledException("synthetic interrupted read");
        now = 1108; finish.SetException(failure);
        Assert.Same(failure, await Assert.ThrowsAsync<OperationCanceledException>(async () => await pending));
        Assert.Equal(stage, retained.Stage); Assert.Equal(1000, retained.StartedAtMs); Assert.Equal(1108, retained.EndedAtMs);
        Assert.Equal(1020, retained.CaptureStartedAtMs); Assert.Equal(4, retained.CaptureCount);
        Assert.Equal(2, retained.DuplicateCount); Assert.Equal(3, retained.BarrierCount);
        Assert.Equal(Sample(0, 1010).Source, retained.LastReturnedSource);
        Assert.Null(retained.RecognitionCompletedAtMs); Assert.Equal(failure.Message, retained.Error);
        Assert.Equal("forward_lease_expired", retained.LeaseFault);
    }

    /// <summary>Diagnostic capacity rejects work before admission; successful/failed rows and exception text remain bounded.</summary>
    [Fact]
    public async Task NativeAttemptCapacityFailsExplicitlyWithoutDroppingRetainedRows()
    {
        var attempts = new List<NavigationBaselineObservationAttempt>();
        var sample = Sample(0);
        Assert.Same(sample, await NativeNavigationBaselineOperations.RecordObservationAsync(attempts, () => 1000, () => null, _ => Task.FromResult(sample)));
        Assert.Equal(1000, attempts[0].EndedAtMs); Assert.Null(attempts[0].Error);
        attempts.AddRange(Enumerable.Repeat(attempts[0], NavigationBaselineTask.MaximumObservations - 1));
        var invoked = false;
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => NativeNavigationBaselineOperations.RecordObservationAsync(attempts,
            () => 1001, () => null, _ => { invoked = true; return Task.FromResult(sample); }));
        Assert.Equal("observation_diagnostics_capacity_exceeded", error.Message); Assert.False(invoked);
        Assert.Equal(NavigationBaselineTask.MaximumObservations, attempts.Count);
        Assert.False(NativeNavigationBaselineOperations.EvidenceIsComplete(new() { Error = error.Message }));
        Assert.Equal(512, NavigationBaselineObservationAttempt.DescribeError(new Exception(new string('x', 1000))).Length);
    }

    /// <summary>Capacity loss stays incomplete even beside a lease fault; ordinary failures retain the existing fault priority.</summary>
    [Theory]
    [InlineData("observation_diagnostics_capacity_exceeded", false)]
    [InlineData("capture_diagnostics_capacity_exceeded", false)]
    [InlineData("world_not_ready", true)]
    public async Task ConcurrentLeaseFaultCannotMaskDiagnosticCapacity(string readError, bool complete)
    {
        var operations = new FakeOperations { ReadError = readError, Fault = "forward_lease_expired" };
        var result = await new NavigationBaselineTask(operations).RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal(complete, result.Evidence!.Complete);
        Assert.Equal(complete ? "forward_lease_expired" : readError, result.Error);
        Assert.True(operations.Closed); Assert.Empty(operations.ControlKinds);
    }

    /// <summary>The cooperative deadline terminates a no-progress controller without retries or extra recovery keys.</summary>
    [Fact]
    public async Task NoProgressStopsAtWholeTaskDeadline()
    {
        var operations = new FakeOperations { AlwaysAtStart = true };
        var result = await new NavigationBaselineTask(operations).RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal("baseline_deadline_exceeded", result.Error);
        Assert.True(operations.Closed); Assert.Equal(1, operations.Downs); Assert.Equal(1, operations.Ups);
        Assert.True(operations.ReadCount < NavigationBaselineTask.MaximumObservations);
    }

    /// <summary>Retention has an independent work bound, and a written partial journal remains explicitly incomplete.</summary>
    [Fact]
    public async Task ObservationCapacityIsBoundedAndIncomplete()
    {
        var operations = new FakeOperations { AlwaysAtStart = true, IgnoreCadenceForCapacityTest = true };
        var result = await new NavigationBaselineTask(operations).RunAsync(_ => { }, default);
        Assert.Equal("observation_capacity_exceeded", result.Error); Assert.False(result.Verified);
        Assert.False(result.Evidence!.Complete); Assert.True(operations.Saved.Length <= NavigationBaselineTask.MaximumObservations);
        Assert.Equal("observation_capacity_exceeded", operations.Saved.Last().RejectionReason);
        Assert.False(NativeNavigationBaselineOperations.EvidenceIsComplete(result with { Error = "input_evidence_capacity_exceeded" }));
    }

    /// <summary>Measured endpoint success cannot mask evidence publication failure.</summary>
    [Fact]
    public async Task PublicationFailureRejectsMeasuredSuccess()
    {
        var operations = new FakeOperations { PublicationError = true };
        var result = await new NavigationBaselineTask(operations).RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Empty(result.Samples); Assert.Equal(3, result.VerificationSamples.Length);
        Assert.Contains("evidence_publication_failed", result.Error); Assert.Null(result.Evidence);
        Assert.True(operations.Closed); Assert.Equal(1, operations.Ups);
    }

    /// <summary>The owner remains exclusive during cleanup, and cancellation beats an already measured successful result.</summary>
    [Fact]
    public async Task OwnerRetainsLeaseThroughCleanupAndCancellation()
    {
        var owner = new NavigationBaselineTaskOwner();
        var measured = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var cleanup = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Assert.True(owner.TryStart(10, 3, async (_, _, phase) =>
        { phase("cleaning_up"); measured.SetResult(); await cleanup.Task; return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, ValidResult()); }));
        await measured.Task.WaitAsync(TimeSpan.FromSeconds(5));
        var runId = owner.Snapshot().RunId!;
        Assert.False(owner.TryStart(10, 3, (_, _, _) => throw new Exception("must not start")));
        Assert.Equal("navigation_baseline_not_terminal", owner.TryGetResult(runId, out _));
        owner.Cancel(); cleanup.SetResult(); await WaitForOwner(owner);
        Assert.Equal("cancelled", owner.Snapshot().State); Assert.Null(owner.TryGetResult(runId, out var terminal));
        Assert.False(terminal!.Result!.Verified); Assert.Empty(terminal.Result.Samples);
    }

    /// <summary>Task-lock rejection and later cleanup failure both dominate otherwise valid measured evidence.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task OwnerRejectsTaskOrCleanupFailure(bool cleanupFailure)
    {
        var owner = new NavigationBaselineTaskOwner();
        owner.TryStart(10, 3, (_, _, _) => Task.FromResult((new SoloTaskRunResult
            { Outcome = cleanupFailure ? SoloTaskRunOutcome.Faulted : SoloTaskRunOutcome.Rejected,
                ErrorMessage = cleanupFailure ? "cleanup_failed" : null }, cleanupFailure ? ValidResult() : null)));
        await WaitForOwner(owner);
        Assert.Equal("failed", owner.Snapshot().State); Assert.False(owner.Snapshot(true).Result!.Verified);
        Assert.Equal(cleanupFailure ? "cleanup_failed" : "task_ownership_rejected", owner.Snapshot().Error);
        Assert.Equal("navigation_baseline_run_mismatch", owner.TryGetResult(Guid.NewGuid().ToString("N"), out _));
    }

    /// <summary>Owner deadline does not depend on a cancellation timer running before a very fast callback.</summary>
    [Fact]
    public async Task OwnerDeadlineAlwaysOverridesLateSuccess()
    {
        var owner = new NavigationBaselineTaskOwner();
        owner.TryStart(10, 3, (_, _, _) => Task.FromResult((new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, (NavigationBaselineRunResult?)ValidResult())), TimeSpan.Zero);
        await WaitForOwner(owner);
        Assert.Equal("baseline_deadline_exceeded", owner.Snapshot().Error); Assert.False(owner.Snapshot(true).Result!.Verified);
    }

    /// <summary>Old-sized status omits the full result while the pinned result has exact camel-case evidence and bounded size.</summary>
    [Fact]
    public async Task WireStatusIsCompactAndResultIsPinnedAndDetached()
    {
        var owner = new NavigationBaselineTaskOwner();
        owner.TryStart(10, 3, (_, _, _) => Task.FromResult((new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, (NavigationBaselineRunResult?)ValidResult())));
        await WaitForOwner(owner); Assert.Equal("completed", owner.Snapshot().State);
        var response = new ExternalControlResponse { Success = true, Status = new() { NavigationBaseline = owner.Snapshot() } };
        var compact = ExternalControlProtocol.SerializeResponse(response);
        Assert.True(compact.Length < ExternalControlProtocol.MaximumFrameBytes);
        using var compactJson = JsonDocument.Parse(compact);
        Assert.False(compactJson.RootElement.GetProperty("status").GetProperty("navigationBaseline").TryGetProperty("result", out _));
        Assert.Null(owner.TryGetResult(owner.Snapshot().RunId!, out var full));
        var fullBytes = ExternalControlProtocol.SerializeResponse(response with { Status = response.Status with { NavigationBaseline = full! } });
        Assert.True(fullBytes.Length < ExternalControlProtocol.MaximumResponseBytes("navigationBaselineResult"));
        using var fullJson = JsonDocument.Parse(fullBytes);
        Assert.Equal("normal", fullJson.RootElement.GetProperty("status").GetProperty("navigationBaseline").GetProperty("result")
            .GetProperty("samples")[0].GetProperty("motion").GetProperty("status").GetString());
        full!.Result!.Samples[0] = full.Result.Samples[0] with { X = 0 };
        Assert.NotEqual(0, owner.Snapshot(true).Result!.Samples[0].X);
    }

    /// <summary>The fixed start accepts no yaw/input/route arguments; its larger read-only response does not enlarge inbound frames.</summary>
    [Fact]
    public void ProtocolKeepsFixedStartAndBoundedReadOnlyResult()
    {
        var request = new ExternalControlRequest { Version = 1, RequestId = Guid.NewGuid(), CreatedAtUnixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
            Command = "startNavigationBaseline", TargetProcessId = 20, TargetWindowsSessionId = 3, TargetNonce = "fixed" };
        Assert.Null(ExternalControlProtocol.ValidateRequest(request, DateTimeOffset.UtcNow));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(request with { TargetYawDegrees = 0 }, DateTimeOffset.UtcNow));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(request with { EnableInput = true }, DateTimeOffset.UtcNow));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(request with { NavigationBaselineRunId = Guid.NewGuid().ToString("N") }, DateTimeOffset.UtcNow));
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(request with { Command = "navigationBaselineResult", NavigationBaselineRunId = Guid.Empty.ToString("N") }, DateTimeOffset.UtcNow));
        Assert.Null(ExternalControlProtocol.ValidateRequest(request with { Command = "navigationBaselineResult", NavigationBaselineRunId = Guid.NewGuid().ToString("N") }, DateTimeOffset.UtcNow));
        Assert.Equal(8192, ExternalControlProtocol.MaximumFrameBytes); Assert.Equal(8192, ExternalControlProtocol.MaximumResponseBytes("status"));
        Assert.Equal(32768, ExternalControlProtocol.MaximumResponseBytes("navigationBaselineResult"));
    }

    /// <summary>One fake fixed native adapter exercises workflow ordering without constructing runtime, map or input objects.</summary>
    private sealed class FakeOperations : INavigationBaselineOperations
    {
        /// <summary>Controlled monotonic time and input-state counters.</summary>
        public double NowMs { get; private set; } = 1000;
        /// <summary>Owned simulated W state.</summary>
        public bool ForwardHeld { get; private set; }
        /// <summary>No hidden native fault unless the test injects one.</summary>
        public string? Fault { get; init; }
        /// <summary>Fake releases succeed; native release errors are exercised separately.</summary>
        public string? ReleaseError => null;
        /// <summary>Read mutation/failure/cancellation hooks operate on deterministic evidence only.</summary>
        public Func<int, NavigationBaselineSample, NavigationBaselineSample>? SampleAt { get; init; }
        /// <summary>Optional callback just before returning one observation.</summary>
        public Action<int>? OnRead { get; init; }
        /// <summary>Controlled recognition work, separate from the immutable response barrier.</summary>
        public Func<int, double>? ReadWorkMs { get; init; }
        /// <summary>Optional pacing failure after its requested deadline.</summary>
        public Exception? WaitError { get; init; }
        /// <summary>Controlled scheduler delay for failed-wait evidence.</summary>
        public double WaitOverrunMs { get; init; }
        /// <summary>Injected recognition error.</summary>
        public string? ReadError { get; init; }
        /// <summary>Never progress along the route.</summary>
        public bool AlwaysAtStart { get; init; }
        /// <summary>Exercise independent work retention when a fake wait does not advance time.</summary>
        public bool IgnoreCadenceForCapacityTest { get; init; }
        /// <summary>Injected file-publication error after input is closed.</summary>
        public bool PublicationError { get; init; }
        /// <summary>Observed lifecycle and call counts.</summary>
        public int ReadCount, Downs, Ups, Rotations, FinalReads;
        /// <summary>Input closure and publication order evidence.</summary>
        public bool Closed, PublishedAfterClosed, CameraWhileHeld;
        /// <summary>Completed permanent input cutoff.</summary>
        public double ClosedAt;
        /// <summary>Recorded controls and final-read ownership states.</summary>
        public List<string> ControlKinds { get; } = [];
        /// <summary>Actual fake method entry clocks independent of returned diagnostic fields.</summary>
        public List<double> ReadEntries { get; } = [];
        /// <summary>Final reads must all follow permanent closure.</summary>
        public List<bool> FinalReadClosed { get; } = [];
        /// <summary>Fresh response barrier observations.</summary>
        public List<(double BeforeMs, double AfterMs, double RequiredMs)> RealInputBarriers { get; } = [];
        /// <summary>Last real input barrier, unchanged by lease renewal.</summary>
        private double _barrier, _response;
        /// <summary>Detached saved observation journal.</summary>
        public NavigationBaselineDecision[] Saved { get; private set; } = [];
        /// <summary>Detached workflow wait diagnostics supplied for local-file publication.</summary>
        public NavigationBaselineScheduleWait[] SavedWaits { get; private set; } = [];
        /// <summary>No setup side effects.</summary>
        public Task PrepareAsync(CancellationToken ct) => Task.CompletedTask;
        /// <summary>Return a distinct response-qualified synthetic source and record ordering.</summary>
        public Task<NavigationBaselineSample> ReadPoseAsync(string? retainImage, CancellationToken ct)
        {
            var index = ReadCount++;
            ReadEntries.Add(NowMs);
            if (ReadError is not null) throw new InvalidOperationException(ReadError);
            NowMs = Math.Max(NowMs + 1, _barrier + _response);
            if (_response > 0) RealInputBarriers.Add((_barrier, NowMs, _response));
            NowMs += ReadWorkMs?.Invoke(index) ?? 0;
            if (retainImage == "final") { FinalReads++; FinalReadClosed.Add(Closed); }
            var sample = Sample(AlwaysAtStart || index == 0 ? 0 : index == 1 ? 0.45 : 1, NowMs);
            OnRead?.Invoke(index);
            return Task.FromResult(SampleAt?.Invoke(index, sample) ?? sample);
        }
        /// <summary>Fake real camera change, forbidden while W is held.</summary>
        public NavigationBaselineInputEvent Rotate(NavigationBaselineSample sample, CancellationToken ct)
        { CameraWhileHeld |= ForwardHeld; Rotations++; ControlKinds.Add("camera"); _barrier = NowMs; _response = 80; return new("camera", NowMs, NowMs, MouseDx: 3); }
        /// <summary>Renewal has no repeated keydown and does not move the response barrier.</summary>
        public NavigationBaselineInputEvent Forward(NavigationBaselineSample sample, CancellationToken ct)
        {
            if (Closed) throw new InvalidOperationException("closed");
            var kind = ForwardHeld ? "renew_w" : "w_down";
            if (!ForwardHeld) { Downs++; ForwardHeld = true; _barrier = NowMs; _response = 60; }
            ControlKinds.Add(kind); return new(kind, NowMs, NowMs, NowMs + 100);
        }
        /// <summary>Explicit release before alignment.</summary>
        public NavigationBaselineInputEvent ReleaseForward()
        { if (ForwardHeld) Ups++; ForwardHeld = false; ControlKinds.Add("w_up"); _barrier = NowMs; _response = 80; return new("w_up", NowMs, NowMs); }
        /// <summary>Idempotent permanent input closure, without cancelling verification.</summary>
        public void CloseInput()
        { if (Closed) return; Closed = true; if (ForwardHeld) Ups++; ForwardHeld = false; ClosedAt = _barrier = NowMs; _response = 80; }
        /// <summary>Advance deterministic cadence without real sleeps.</summary>
        public Task WaitUntilAsync(double deadlineMs, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            if (!IgnoreCadenceForCapacityTest) NowMs = Math.Max(NowMs, deadlineMs);
            if (WaitError is not null) { NowMs += WaitOverrunMs; throw WaitError; }
            return Task.CompletedTask;
        }
        /// <summary>Capture publication order and reuse the production capacity-completeness predicate.</summary>
        public Task<NavigationBaselineEvidence> PublishEvidenceAsync(NavigationBaselineRunResult result, NavigationBaselineDecision[] decisions,
            NavigationBaselineScheduleWait[] scheduleWaits)
        {
            PublishedAfterClosed = Closed; Saved = decisions; SavedWaits = scheduleWaits;
            if (PublicationError) throw new IOException("synthetic disk failure");
            return Task.FromResult(Evidence(NativeNavigationBaselineOperations.EvidenceIsComplete(result)));
        }
    }
}
