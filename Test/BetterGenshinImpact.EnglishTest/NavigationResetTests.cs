using System.Diagnostics;
using System.Text;
using BetterGenshinImpact.GameTask.NavigationReset;
using BetterGenshinImpact.GameTask.SoloTask.Execution;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Fixed reset validation, evidence and lifetime checks; no native runtime, image, window or input is created.</summary>
public sealed class NavigationResetTests
{
    /// <summary>A read-only handle to this test process supports identity/exit checks and rejects mismatched session/PID.</summary>
    [Fact]
    public void MinimalProcessPinChecksIdentitySessionAndHandleLifetime()
    {
        var processId = checked((int)Kernel32.GetCurrentProcessId());
        Assert.True(Kernel32.ProcessIdToSessionId((uint)processId, out var sessionId));
        var handle = NativeNavigationResetOperations.OpenPinnedProcess(processId, sessionId);
        try
        {
            Assert.True(NativeNavigationResetOperations.IsPinnedProcessAlive(handle, processId));
            Assert.False(NativeNavigationResetOperations.IsPinnedProcessAlive(handle, processId + 1));
            Assert.Throws<InvalidOperationException>(() => NativeNavigationResetOperations.OpenPinnedProcess(processId, sessionId + 1));
            Assert.Throws<InvalidOperationException>(() => NativeNavigationResetOperations.OpenPinnedProcess(0, sessionId));
        }
        finally { handle.Dispose(); }
        Assert.False(NativeNavigationResetOperations.IsPinnedProcessAlive(handle, processId));
    }

    /// <summary>A command accepts only a pinned target and a bounded yaw, never arbitrary tasks or destinations.</summary>
    [Fact]
    public void RequestIsFixedTypedAndTargetPinned()
    {
        var now = DateTimeOffset.UtcNow;
        var request = new ExternalControlRequest { Version = 1, RequestId = Guid.NewGuid(), CreatedAtUnixMs = now.ToUnixTimeMilliseconds(),
            Command = "startNavigationReset", TargetProcessId = 100, TargetWindowsSessionId = 3, TargetNonce = "current" };
        Assert.Null(ExternalControlProtocol.ValidateRequest(request, now));
        Assert.Null(ExternalControlProtocol.ValidateRequest(request with { TargetYawDegrees = 359.9 }, now));
        Assert.Equal("target_required", ExternalControlProtocol.ValidateRequest(request with { TargetNonce = null }, now));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(request with { EnableInput = true }, now));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(request with { Command = "status", TargetYawDegrees = 1 }, now));
        Assert.False(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes("{\"targetYawDegrees\":\"0\"}"), out _));
        Assert.False(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes("{\"destination\":10}"), out _));
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(request), ExternalControlProtocol.Fingerprint(request with { TargetYawDegrees = 1 }));
        foreach (var yaw in new[] { -1, 360, double.NaN, double.PositiveInfinity, double.NegativeInfinity })
            Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(request with { TargetYawDegrees = yaw }, now));
    }

    /// <summary>Automation opt-in, actual remote child role and authenticated session are all required.</summary>
    [Theory]
    [InlineData(false, false, true, "automation_disabled")]
    [InlineData(true, true, false, "rdp_child_required")]
    [InlineData(true, false, false, "rdp_child_required")]
    [InlineData(true, false, true, null)]
    public void ResetRequiresOptedInRdpChild(bool enabled, bool primary, bool remote, string? error)
    {
        Assert.True(ExternalControlProtocol.IsAutomationCommand("startNavigationReset"));
        Assert.Equal(error, ExternalControlService.AutomationTargetError("startNavigationReset", enabled, primary, remote));
    }

    /// <summary>Accept circular yaw near zero only with three stable, high-confidence, distinct native sources.</summary>
    [Fact]
    public void SettledGateRequiresRealRepeatedMeasurements()
    {
        var samples = Samples();
        samples[0] = samples[0] with { YawDegrees = 359.5 };
        Assert.True(NavigationResetTask.AcceptSamples(samples, 0));
        Assert.False(NavigationResetTask.AcceptSamples(samples[..2], 0));
        foreach (var bad in new[]
        {
            samples[1] with { X = NavigationResetTask.IconX, Y = NavigationResetTask.IconY },
            samples[1] with { X = double.NaN }, samples[1] with { Y = double.PositiveInfinity },
            samples[1] with { YawDegrees = double.NaN }, samples[1] with { YawDegrees = 4 },
            samples[1] with { PositionConfidence = .98 }, samples[1] with { PositionConfidence = double.NaN },
            samples[1] with { YawConfidence = .19 }, samples[1] with { LayerId = "underground" },
            samples[1] with { SourceTimestamp100ns = samples[0].SourceTimestamp100ns },
            samples[1] with { SourceEpoch = Guid.NewGuid() },
            samples[1] with { AcquiredAtStopwatchTicks = samples[0].AcquiredAtStopwatchTicks },
            samples[1] with { X = samples[0].X + 2 },
            samples[1] with { YawDegrees = 2.5 }
        }) Assert.False(NavigationResetTask.AcceptSamples([samples[0], bad, samples[2]], 0));
    }

    /// <summary>Future compositor timestamps cannot renew old acquisitions or cross a post-input cutoff alone.</summary>
    [Fact]
    public void SourceFreshnessAndBarrierUseBothNativeClocks()
    {
        var now = 10 * Stopwatch.Frequency;
        var source = new GameCaptureSourceInfo(Guid.NewGuid(), 102_000_000, now - Stopwatch.Frequency / 10);
        Assert.True(NativeNavigationResetOperations.SourceIsFresh(source, now));
        Assert.False(NativeNavigationResetOperations.SourceIsFresh(source with { AcquiredAtStopwatchTicks = now - Stopwatch.Frequency }, now));
        Assert.False(NativeNavigationResetOperations.SourceIsFresh(source with { SourceTimestamp100ns = 90_000_000 }, now));
        Assert.False(NativeNavigationResetOperations.SourceIsFresh(source with { AcquiredAtStopwatchTicks = now + 1 }, now));
        Assert.False(NativeNavigationResetOperations.SourceIsFresh(null, now));
        Assert.False(NativeNavigationResetOperations.SourceIsAfterBarrier(source, now));
        Assert.False(NativeNavigationResetOperations.SourceIsAfterBarrier(source with { SourceTimestamp100ns = 90_000_000 }, now - Stopwatch.Frequency));
        Assert.True(NativeNavigationResetOperations.SourceIsAfterBarrier(source, now - Stopwatch.Frequency));
    }

    /// <summary>The workflow releases input after final verification and never substitutes teleport's icon return for a pose.</summary>
    [Fact]
    public async Task WorkflowVerifiesAfterRotationAndAlwaysReleases()
    {
        var ops = new FakeOperations();
        var phases = new List<string>();
        var result = await new NavigationResetTask(ops).RunAsync(0, phases.Add, CancellationToken.None);
        Assert.True(NavigationResetTask.AcceptSamples(result, 0));
        Assert.Equal(new[] { "preparing", "teleporting", "orienting", "verifying" }, phases);
        Assert.Equal(new[] { "prepare", "teleport", "rotate", "read", "read", "read", "release" }, ops.Events);
    }

    /// <summary>Rotation failure, teleport failure and cancelled native calls all release the owned input.</summary>
    [Theory]
    [InlineData("teleport")]
    [InlineData("rotate")]
    [InlineData("cancel")]
    public async Task FailureNeverReturnsVerifiedSamples(string failure)
    {
        var ops = new FakeOperations { Failure = failure };
        await Assert.ThrowsAnyAsync<Exception>(() => new NavigationResetTask(ops).RunAsync(0, _ => { }, CancellationToken.None));
        Assert.Equal("release", ops.Events.Last());
        Assert.DoesNotContain("read", ops.Events);
    }

    /// <summary>A non-settling sequence has a finite attempt bound and no successful result.</summary>
    [Fact]
    public async Task RepeatedCachedSamplesCannotSatisfyWorkflow()
    {
        var ops = new FakeOperations { RepeatFrame = true };
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => new NavigationResetTask(ops).RunAsync(0, _ => { }, CancellationToken.None));
        Assert.Equal("pose_not_settled", error.Message);
        Assert.Equal(15, ops.Events.Count(item => item == "read"));
        Assert.Equal("release", ops.Events.Last());
    }

    /// <summary>The lease remains owned after cancellation until the executor's cleanup actually completes.</summary>
    [Fact]
    public async Task CancellationDrainsCleanupAndRejectsConcurrentStarts()
    {
        var owner = new NavigationResetTaskOwner();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var cancelled = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var cleanup = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Assert.True(owner.TryStart(0, 10, 3, async (ct, phase) =>
        {
            using var registration = ct.Register(() => cancelled.TrySetResult());
            phase("teleporting"); entered.SetResult();
            await cleanup.Task;
            return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, Samples());
        }));
        var firstId = owner.Snapshot().RunId;
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        var stop = owner.StopAsync(CancellationToken.None);
        await cancelled.Task.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.True(owner.Running);
        Assert.False(stop.IsCompleted);
        Assert.False(owner.TryStart(0, 10, 3, (_, _) => throw new Exception("must not execute")));
        cleanup.SetResult();
        await stop.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.False(owner.Running);
        Assert.Equal("cancelled", owner.Snapshot().State);
        Assert.Empty(owner.Snapshot().Samples);
        Assert.Equal(firstId, owner.Snapshot().RunId);
        Assert.True(owner.TryStart(0, 10, 3, (_, _) => Task.FromResult<(SoloTaskRunResult, NavigationResetSample[]?)>((new() { Outcome = SoloTaskRunOutcome.Completed }, Samples()))));
        await WaitForIdle(owner);
        Assert.Equal("completed", owner.Snapshot().State);
        Assert.NotEqual(firstId, owner.Snapshot().RunId);
    }

    /// <summary>An elapsed whole-operation deadline remains a failure even if native cleanup returns a completed result.</summary>
    [Fact]
    public async Task DeadlineCancelsButDoesNotAbandonExecutor()
    {
        var owner = new NavigationResetTaskOwner();
        var cancellation = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var cleanup = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        owner.TryStart(0, 10, 3, async (ct, _) =>
        {
            using var registration = ct.Register(() => cancellation.TrySetResult());
            await cleanup.Task;
            return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, Samples());
        }, TimeSpan.FromMilliseconds(30));
        await cancellation.Task.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.True(owner.Running);
        cleanup.SetResult();
        await WaitForIdle(owner);
        Assert.Equal("failed", owner.Snapshot().State);
        Assert.Equal("reset_deadline_exceeded", owner.Snapshot().Error);
    }

    /// <summary>TaskRunner rejection/fault and missing or invalid evidence cannot advertise completed reset state.</summary>
    [Theory]
    [InlineData(SoloTaskRunOutcome.Rejected, false)]
    [InlineData(SoloTaskRunOutcome.Faulted, true)]
    [InlineData(SoloTaskRunOutcome.Completed, false)]
    public async Task OwnerRejectsUnverifiedExecutorResults(SoloTaskRunOutcome outcome, bool provideSamples)
    {
        var owner = new NavigationResetTaskOwner();
        owner.TryStart(0, 10, 3, (_, _) => Task.FromResult<(SoloTaskRunResult, NavigationResetSample[]?)>((new() { Outcome = outcome }, provideSamples ? Samples() : null)));
        await WaitForIdle(owner);
        Assert.Equal("failed", owner.Snapshot().State);
        Assert.NotNull(owner.Snapshot().Error);
        Assert.Empty(owner.Snapshot().Samples);
    }

    /// <summary>Native source fixtures have one epoch and120ms spaced first acquisitions.</summary>
    private static NavigationResetSample[] Samples()
    {
        var epoch = Guid.NewGuid();
        return Enumerable.Range(0, 3).Select(i => new NavigationResetSample(NavigationResetTask.SpawnX, NavigationResetTask.SpawnY,
            0, DateTimeOffset.UtcNow, epoch, 100_000_000 + i * 1_200_000,
            10 * Stopwatch.Frequency + i * Stopwatch.Frequency * 12 / 100, .999, .9, "City_102")).ToArray();
    }

    /// <summary>Bounded polling only for synthetic owner tasks; no game/session resource is involved.</summary>
    private static async Task WaitForIdle(NavigationResetTaskOwner owner)
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        while (owner.Running) await Task.Delay(5, deadline.Token);
    }

    /// <summary>Records workflow order while injecting failure, cancellation and duplicate-source observations.</summary>
    private sealed class FakeOperations : INavigationResetOperations
    {
        /// <summary>Deterministic fresh sample series for one synthetic run.</summary>
        private readonly NavigationResetSample[] _samples = Samples();
        /// <summary>Next sample index.</summary>
        private int _index;
        /// <summary>Observed operation order, including mandatory release.</summary>
        internal List<string> Events { get; } = [];
        /// <summary>Selected synthetic failure point.</summary>
        internal string? Failure { get; init; }
        /// <summary>Return one native identity repeatedly to exercise cached-frame rejection.</summary>
        internal bool RepeatFrame { get; init; }
        /// <inheritdoc />
        public Task PrepareAsync(CancellationToken ct) { Events.Add("prepare"); return Task.CompletedTask; }
        /// <inheritdoc />
        public Task TeleportAsync(CancellationToken ct)
        {
            Events.Add("teleport");
            if (Failure == "teleport") throw new InvalidOperationException("unlocked_waypoint_required");
            if (Failure == "cancel") throw new OperationCanceledException();
            return Task.CompletedTask;
        }
        /// <inheritdoc />
        public Task<bool> RotateAsync(double yaw, CancellationToken ct) { Events.Add("rotate"); return Task.FromResult(Failure != "rotate"); }
        /// <inheritdoc />
        public Task<NavigationResetSample> ReadPoseAsync(CancellationToken ct)
        { Events.Add("read"); return Task.FromResult(_samples[RepeatFrame ? 0 : Math.Min(_index++, 2)]); }
        /// <inheritdoc />
        public Task DelayAsync(int milliseconds, CancellationToken ct) { ct.ThrowIfCancellationRequested(); return Task.CompletedTask; }
        /// <inheritdoc />
        public void ReleaseInput() => Events.Add("release");
    }
}
