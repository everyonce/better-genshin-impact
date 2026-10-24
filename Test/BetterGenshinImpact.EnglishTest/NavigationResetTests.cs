using System.Diagnostics;
using System.Text;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoPathing;
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
    /// <summary>Only the first post-teleport acquisition can wait for missing HUD, without running pose work or camera input.</summary>
    [Fact]
    public async Task PostTeleportMissingHudSettlesBeforePoseWork()
    {
        var observations = new Queue<(AgentWorldEvidence Evidence, long Source)>([
            (AgentWorldEvidence.HudMissing, 100), (AgentWorldEvidence.HudMissing, 200),
            (AgentWorldEvidence.WorldHud, 300)]);
        var poseReads = 0;
        var waits = 0;
        var expected = Samples()[0];
        var actual = await NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            var observation = observations.Dequeue();
            var reason = NativeNavigationResetOperations.WorldRetryReason(observation.Evidence, true, observation.Source);
            if (reason is not null) return Task.FromResult(new NavigationResetPoseProbe(null, reason));
            poseReads++;
            return Task.FromResult(new NavigationResetPoseProbe(expected, null));
        }, (milliseconds, ct) =>
        {
            Assert.Equal(0, poseReads);
            Assert.Equal(120, milliseconds);
            ct.ThrowIfCancellationRequested();
            waits++;
            return Task.CompletedTask;
        }, CancellationToken.None);
        Assert.Same(expected, actual);
        Assert.Equal(1, poseReads);
        Assert.Equal(2, waits);
        Assert.Empty(observations);
    }

    /// <summary>Preparation/later reads, explicit blocking UI and recognizer failure never use the HUD allowance.</summary>
    [Theory]
    [InlineData(AgentWorldEvidence.HudMissing, false)]
    [InlineData(AgentWorldEvidence.BlockingUi, true)]
    [InlineData(AgentWorldEvidence.RecognitionFailed, true)]
    [InlineData(AgentWorldEvidence.Unknown, true)]
    public async Task WorldSettlingKeepsTerminalEvidenceHard(AgentWorldEvidence evidence, bool allowance)
    {
        var probes = 0;
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            probes++;
            var reason = NativeNavigationResetOperations.WorldRetryReason(evidence, allowance, 123);
            return Task.FromResult(new NavigationResetPoseProbe(null, reason));
        }, (_, _) => throw new Exception("must not retry terminal evidence"), CancellationToken.None));
        Assert.Equal(1, probes);
        Assert.Equal($"world_not_ready; evidence={evidence}; source=123", error.Message);
        Assert.Null(NativeNavigationResetOperations.WorldRetryReason(AgentWorldEvidence.WorldHud, allowance, 124));
    }

    /// <summary>A persistently missing HUD exhausts the existing finite read budget, with its exact evidence retained.</summary>
    [Fact]
    public async Task MissingPostTeleportHudNeverBecomesSuccessfulPose()
    {
        var probes = 0;
        var error = await Assert.ThrowsAsync<TimeoutException>(() => NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            var reason = NativeNavigationResetOperations.WorldRetryReason(AgentWorldEvidence.HudMissing, true, ++probes);
            return Task.FromResult(new NavigationResetPoseProbe(null, reason));
        }, (_, _) => Task.CompletedTask, CancellationToken.None));
        Assert.Equal(25, probes);
        Assert.Contains("attempts=25", error.Message);
        Assert.Contains("last=world_not_ready; evidence=HudMissing; source=25", error.Message);
    }

    /// <summary>The measured-yaw path preserves signed wraparound, gain thresholds, rounding and DPI without native input.</summary>
    [Theory]
    [InlineData(0, 0, 1, 0, 0, 0)]
    [InlineData(0, 5, 1, 5, -5, 1)]
    [InlineData(0, 6, 1, 6, -12, 1)]
    [InlineData(0, 30, 1, 30, -60, 1)]
    [InlineData(0, 31, 1, 31, -93, 1)]
    [InlineData(0, 90, 1, 90, -270, 1)]
    [InlineData(0, 91, 1, 91, -364, 1)]
    [InlineData(0, 180, 1, -180, 720, 1)]
    [InlineData(359, 1, 1, 2, -2, 1)]
    [InlineData(1, 359, 1, -2, 2, 1)]
    [InlineData(0, 1, 1.5, 1, -2, 1)]
    [InlineData(0, 6, 1.5, 6, -18, 1)]
    public void MeasuredCameraRotationPreservesExistingController(float target, float measured, double dpi,
        float expectedDifference, int expectedX, int expectedMoves)
    {
        var moves = new List<(int X, int Y)>();
        var difference = CameraRotateTask.ApplyMeasuredRotation(target, measured, dpi, CancellationToken.None,
            (dx, dy) => moves.Add((dx, dy)));
        Assert.Equal(expectedDifference, difference);
        Assert.Equal(expectedMoves, moves.Count);
        if (moves.Count != 0) Assert.Equal((expectedX, 0), moves.Single());
    }

    /// <summary>A cancelled task produces no camera movement, including when it was cancelled after its previous successful step.</summary>
    [Fact]
    public void MeasuredCameraRotationHonorsCancellationBeforeDispatch()
    {
        using var stop = new CancellationTokenSource();
        var moves = 0;
        CameraRotateTask.ApplyMeasuredRotation(0, 90, 1, stop.Token, (_, _) => { moves++; stop.Cancel(); });
        Assert.Equal(1, moves);
        Assert.ThrowsAny<OperationCanceledException>(() =>
            CameraRotateTask.ApplyMeasuredRotation(0, 30, 1, stop.Token, (_, _) => moves++));
        Assert.ThrowsAny<OperationCanceledException>(() =>
            CameraRotateTask.ApplyMeasuredRotation(0, 0, 1, stop.Token, (_, _) => moves++));
        Assert.Equal(1, moves);
    }

    /// <summary>Malformed supplied yaw/DPI cannot turn into an unchecked integer movement or invoke the sink.</summary>
    [Fact]
    public void MeasuredCameraRotationRejectsNonfiniteAndOverflowingInputs()
    {
        var moves = 0;
        foreach (var (target, measured, dpi) in new[] { (float.NaN, 0f, 1.0), (0f, float.PositiveInfinity, 1.0),
            (0f, 1f, double.NaN), (0f, 1f, 0.0), (0f, 1f, -1.0), (float.MaxValue, -float.MaxValue, 1.0) })
            Assert.Throws<ArgumentOutOfRangeException>(() => CameraRotateTask.ApplyMeasuredRotation(target, measured, dpi,
                CancellationToken.None, (_, _) => moves++));
        Assert.Throws<OverflowException>(() => CameraRotateTask.ApplyMeasuredRotation(0, 90, double.MaxValue,
            CancellationToken.None, (_, _) => moves++));
        Assert.Equal(0, moves);
    }

    /// <summary>A post-teleport map miss and low yaw wait for new probes without relaxing the evidence returned on success.</summary>
    [Fact]
    public async Task PoseAcquisitionRetriesTransientMissesThenReturnsCurrentEvidence()
    {
        var sample = Samples()[2];
        var probes = new Queue<NavigationResetPoseProbe>([
            new(null, "local_position_unrecognized; source=100"),
            new(null, "yaw_unrecognized; source=200"), new(sample, null)]);
        var waits = new List<int>();
        var result = await NavigationResetPoseAcquisition.ReadAsync(_ => Task.FromResult(probes.Dequeue()),
            (milliseconds, ct) => { ct.ThrowIfCancellationRequested(); waits.Add(milliseconds); return Task.CompletedTask; },
            CancellationToken.None);
        Assert.Same(sample, result);
        Assert.Empty(probes);
        Assert.Equal(new[] { 120, 120 }, waits);
        Assert.True(NavigationResetTask.IsValidPose(result));
    }

    /// <summary>Repeated misses have bounded work and bounded diagnostics, even when waits are immediate.</summary>
    [Fact]
    public async Task PoseAcquisitionHasFiniteAttemptsAndBoundedFailureEvidence()
    {
        var probes = 0;
        var waits = 0;
        var error = await Assert.ThrowsAsync<TimeoutException>(() => NavigationResetPoseAcquisition.ReadAsync(
            _ => { probes++; return Task.FromResult(new NavigationResetPoseProbe(null, "local_position_unrecognized; source=300; " + new string('x', 500))); },
            (_, _) => { waits++; return Task.CompletedTask; }, CancellationToken.None));
        Assert.Equal(25, probes);
        Assert.Equal(24, waits);
        Assert.Contains("pose_acquisition_timeout; attempts=25;", error.Message);
        Assert.Contains("last=local_position_unrecognized; source=300;", error.Message);
        Assert.True(error.Message.Length < 512);
    }

    /// <summary>World/source/target/wrong-pose failures never enter the retry path or generate another observation.</summary>
    [Theory]
    [InlineData("world_not_ready")]
    [InlineData("native_source_unavailable_or_stale")]
    [InlineData("game_target_lost")]
    [InlineData("pose_evidence_rejected")]
    public async Task PoseAcquisitionDoesNotRetryTerminalGuards(string reason)
    {
        var probes = 0;
        var expected = new InvalidOperationException(reason);
        var actual = await Assert.ThrowsAsync<InvalidOperationException>(() => NavigationResetPoseAcquisition.ReadAsync(
            _ => { probes++; throw expected; }, (_, _) => throw new Exception("must not wait"), CancellationToken.None));
        Assert.Same(expected, actual);
        Assert.Equal(1, probes);
    }

    /// <summary>The existing caller/task deadline cancels an ongoing settle delay and remains cancellation, not a local timeout.</summary>
    [Fact]
    public async Task PoseAcquisitionPreservesCallerCancellation()
    {
        using var stop = new CancellationTokenSource();
        var probes = 0;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => NavigationResetPoseAcquisition.ReadAsync(
            _ => { probes++; return Task.FromResult(new NavigationResetPoseProbe(null, "local_position_unrecognized")); },
            (_, ct) => { stop.Cancel(); ct.ThrowIfCancellationRequested(); return Task.CompletedTask; }, stop.Token));
        Assert.Equal(1, probes);
    }

    /// <summary>A probe that returns apparently valid data only after its cancellation cannot create late success.</summary>
    [Fact]
    public async Task PoseAcquisitionRejectsLateValidProbeWithoutAbandoningIt()
    {
        var cancellation = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finishProbe = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var operation = NavigationResetPoseAcquisition.ReadAsync(async ct =>
        {
            using var registration = ct.Register(() => cancellation.TrySetResult());
            await finishProbe.Task;
            return new NavigationResetPoseProbe(Samples()[0], null);
        }, (_, _) => throw new Exception("must not wait"), CancellationToken.None, TimeSpan.FromMilliseconds(30));
        await cancellation.Task.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.False(operation.IsCompleted);
        finishProbe.SetResult();
        var error = await Assert.ThrowsAsync<TimeoutException>(() => operation);
        Assert.Contains("pose_acquisition_timeout; attempts=1;", error.Message);
    }

    /// <summary>The local deadline cancels an in-flight cooperative read and retains the last completed failed source.</summary>
    [Fact]
    public async Task PoseAcquisitionDeadlineCancelsInFlightProbe()
    {
        var probes = 0;
        var error = await Assert.ThrowsAsync<TimeoutException>(() => NavigationResetPoseAcquisition.ReadAsync(async ct =>
        {
            if (++probes == 1) return new NavigationResetPoseProbe(null, "local_position_unrecognized; source=123");
            await Task.Delay(Timeout.Infinite, ct);
            throw new Exception("cancelled probe must not finish");
        }, (_, _) => Task.CompletedTask, CancellationToken.None, TimeSpan.FromMilliseconds(30)));
        Assert.Equal(2, probes);
        Assert.Contains("last=local_position_unrecognized; source=123", error.Message);
    }

    /// <summary>The same confidence boundary is used before local matching/input and by final sample acceptance.</summary>
    [Fact]
    public void ReliableYawDoesNotPermitHiddenFallbackOrMalformedAngles()
    {
        Assert.True(NavigationResetTask.IsReliableYaw(0, .2));
        Assert.True(NavigationResetTask.IsReliableYaw(359.9, 1));
        foreach (var (yaw, confidence) in new[] { (0.0, .199), (0.0, 1.01), (0.0, double.NaN),
            (double.NaN, .9), (double.PositiveInfinity, .9), (-1.0, .9), (360.0, .9) })
        {
            Assert.False(NavigationResetTask.IsReliableYaw(yaw, confidence));
            Assert.False(NavigationResetTask.IsValidPose(Samples()[0] with { YawDegrees = yaw, YawConfidence = confidence }));
        }
    }

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

    /// <summary>Evidence reads require a precise run and process identity, and cannot carry any movement parameters.</summary>
    [Fact]
    public void DiagnosticsRequestPinsRunAndKeepsRequestLimit()
    {
        var now = DateTimeOffset.UtcNow;
        var request = new ExternalControlRequest { Version = 1, RequestId = Guid.NewGuid(), CreatedAtUnixMs = now.ToUnixTimeMilliseconds(),
            Command = "navigationResetDiagnostics", NavigationResetRunId = Guid.NewGuid().ToString("N"),
            TargetProcessId = 100, TargetWindowsSessionId = 3, TargetNonce = "current" };
        Assert.Null(ExternalControlProtocol.ValidateRequest(request, now));
        Assert.False(ExternalControlProtocol.IsAutomationCommand(request.Command));
        Assert.Equal("target_required", ExternalControlProtocol.ValidateRequest(request with { TargetNonce = null }, now));
        foreach (var runId in new[] { null, "", "wrong-run", Guid.Empty.ToString("N"), Guid.NewGuid().ToString("D") })
            Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(request with { NavigationResetRunId = runId }, now));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(request with { TargetYawDegrees = 0 }, now));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(request with { Command = "status" }, now));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(request with { Command = "startNavigationReset" }, now));
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(request), ExternalControlProtocol.Fingerprint(request with { NavigationResetRunId = Guid.NewGuid().ToString("N") }));
        Assert.Equal(8192, ExternalControlProtocol.MaximumFrameBytes);
        Assert.Equal(8192, ExternalControlProtocol.MaximumResponseBytes("status"));
        Assert.Equal(8192, ExternalControlProtocol.MaximumResponseBytes("startNavigationReset"));
        Assert.Equal(32768, ExternalControlProtocol.MaximumResponseBytes(request.Command));
    }

    /// <summary>A read cannot disclose a different run or partial evidence while its executor still owns cleanup.</summary>
    [Fact]
    public async Task DiagnosticsReadsRequireMatchingTerminalRun()
    {
        var owner = new NavigationResetTaskOwner();
        var cleanup = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Assert.True(owner.TryStart(0, 10, 3, async (_, phase) =>
        {
            phase("verifying");
            await cleanup.Task;
            return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = "pose_not_settled" },
                (NavigationResetSample[]?)null, Array.Empty<NavigationResetVerificationDiagnostic>());
        }));
        var runId = owner.Snapshot().RunId!;
        Assert.Equal("navigation_reset_not_terminal", owner.TryGetDiagnostics(runId, out var pending));
        Assert.Null(pending);
        Assert.Equal("navigation_reset_run_mismatch", owner.TryGetDiagnostics(Guid.NewGuid().ToString("N"), out var wrong));
        Assert.Null(wrong);
        cleanup.SetResult();
        await WaitForIdle(owner);
        Assert.Null(owner.TryGetDiagnostics(runId, out var failed));
        Assert.Equal(runId, failed!.RunId);
        Assert.Equal("failed", failed.State);
        Assert.Empty(failed.Samples);
        Assert.NotNull(failed.VerificationDiagnostics);
        Assert.True(owner.TryStart(0, 10, 3, (_, _) => Task.FromResult<(SoloTaskRunResult, NavigationResetSample[]?, NavigationResetVerificationDiagnostic[])>(
            (new() { Outcome = SoloTaskRunOutcome.Completed }, Samples(), []))));
        Assert.Equal("navigation_reset_run_mismatch", owner.TryGetDiagnostics(runId, out var replaced));
        Assert.Null(replaced);
        await WaitForIdle(owner);
        Assert.Null(owner.TryGetDiagnostics(owner.Snapshot().RunId!, out var completed));
        Assert.Equal("completed", completed!.State);
        Assert.Equal(3, completed.Samples.Length);
    }

    /// <summary>Full native precision fits the dedicated response while ordinary status remains readable by an old 8 KiB peer.</summary>
    [Fact]
    public async Task DiagnosticsSerializationPreservesAllObservationsAndCompactStatus()
    {
        var sequence = VerificationSequence("position_spread_exceeded");
        var diagnostics = sequence.Select((sample, index) => new NavigationResetVerificationDiagnostic(index + 1,
            sample with { X = -867.68359375, Y = 2281.37890625, YawDegrees = 1.5,
                PositionConfidence = 0.9967853426933289, YawConfidence = 0.9999980926513672,
                SourceTimestamp100ns = 123456789012345 + index, AcquiredAtStopwatchTicks = 123456789012345 + index },
            3, "position_spread_exceeded", 1.5, 2.0123456789012345, 1.1234567890123456, 120.12345678901234)).ToArray();
        var owner = new NavigationResetTaskOwner();
        owner.TryStart(0, 10, 3, (_, _) => Task.FromResult<(SoloTaskRunResult, NavigationResetSample[]?, NavigationResetVerificationDiagnostic[])>(
            (new() { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = "pose_not_settled" }, null, diagnostics)));
        await WaitForIdle(owner);
        Assert.Null(owner.TryGetDiagnostics(owner.Snapshot().RunId!, out var full));
        var response = new ExternalControlResponse { RequestId = Guid.NewGuid(), Success = true,
            Status = new ExternalControlStatus { NavigationReset = owner.Snapshot(includeDiagnostics: false) } };
        var compactBytes = ExternalControlProtocol.SerializeResponse(response);
        using var compact = System.Text.Json.JsonDocument.Parse(compactBytes);
        var compactReset = compact.RootElement.GetProperty("status").GetProperty("navigationReset");
        Assert.False(compactReset.TryGetProperty("verificationDiagnostics", out _));
        Assert.Equal(1, compactReset.GetProperty("verificationDiagnosticsVersion").GetInt32());
        Assert.True(compactBytes.Length < ExternalControlProtocol.MaximumResponseBytes("status"));
        var fullBytes = ExternalControlProtocol.SerializeResponse(response with { Status = response.Status! with { NavigationReset = full! } });
        Assert.True(fullBytes.Length > ExternalControlProtocol.MaximumFrameBytes);
        Assert.True(fullBytes.Length < ExternalControlProtocol.MaximumResponseBytes("navigationResetDiagnostics"));
        using var fullJson = System.Text.Json.JsonDocument.Parse(fullBytes);
        var entries = fullJson.RootElement.GetProperty("status").GetProperty("navigationReset").GetProperty("verificationDiagnostics");
        Assert.Equal(15, entries.GetArrayLength());
        for (var index = 0; index < entries.GetArrayLength(); index++)
        {
            var decoded = System.Text.Json.JsonSerializer.Deserialize<NavigationResetVerificationDiagnostic>(entries[index].GetRawText());
            Assert.Equal(diagnostics[index], decoded);
        }
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
            return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, Samples(), Array.Empty<NavigationResetVerificationDiagnostic>());
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
        Assert.True(owner.TryStart(0, 10, 3, (_, _) => Task.FromResult<(SoloTaskRunResult, NavigationResetSample[]?, NavigationResetVerificationDiagnostic[])>((new() { Outcome = SoloTaskRunOutcome.Completed }, Samples(), []))));
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
            return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, Samples(), Array.Empty<NavigationResetVerificationDiagnostic>());
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
        owner.TryStart(0, 10, 3, (_, _) => Task.FromResult<(SoloTaskRunResult, NavigationResetSample[]?, NavigationResetVerificationDiagnostic[])>((new() { Outcome = outcome }, provideSamples ? Samples() : null, [])));
        await WaitForIdle(owner);
        Assert.Equal("failed", owner.Snapshot().State);
        Assert.NotNull(owner.Snapshot().Error);
        Assert.Empty(owner.Snapshot().Samples);
    }

    /// <summary>The four live-plausible final gate failures retain all returned observations without relaxing any threshold.</summary>
    [Theory]
    [InlineData("target_yaw_out_of_tolerance")]
    [InlineData("position_spread_exceeded")]
    [InlineData("yaw_spread_exceeded")]
    [InlineData("acquisition_spacing_too_short")]
    public async Task FailedVerificationRetainsExactGateEvidence(string reason)
    {
        var samples = VerificationSequence(reason);
        var operations = new FakeOperations { SampleAt = index => samples[index] };
        var workflow = new NavigationResetTask(operations);
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => workflow.RunAsync(0, _ => { }, CancellationToken.None));
        Assert.Equal("pose_not_settled", error.Message);
        var diagnostics = workflow.VerificationDiagnostics;
        Assert.Equal(15, diagnostics.Length);
        Assert.Equal(Enumerable.Range(1, 15), diagnostics.Select(item => item.Attempt));
        Assert.Equal(samples, diagnostics.Select(item => item.Sample));
        Assert.All(diagnostics.Skip(reason == "target_yaw_out_of_tolerance" ? 0 : 2), item => Assert.Equal(reason, item.Reason));
        Assert.All(samples, sample => Assert.True(NavigationResetTask.IsValidPose(sample)));
        Assert.False(NavigationResetTask.AcceptSamples(samples[^3..], 0));
        Assert.Equal(reason, NavigationResetTask.SamplesRejectionReason(samples[^3..], 0));
        var last = diagnostics[^1];
        switch (reason)
        {
            case "target_yaw_out_of_tolerance":
                Assert.Equal(4, last.TargetYawErrorDegrees);
                Assert.Equal(0, last.CandidateCount);
                Assert.Null(last.MaximumPositionSpread);
                break;
            case "position_spread_exceeded": Assert.Equal(2, last.MaximumPositionSpread); break;
            case "yaw_spread_exceeded": Assert.Equal(3, last.MaximumYawSpreadDegrees); break;
            case "acquisition_spacing_too_short": Assert.Equal(40, last.MinimumAcquisitionGapMs); break;
        }
        Assert.Equal(15, operations.Events.Count(item => item == "read"));
        Assert.Equal(1, operations.Events.Count(item => item == "rotate"));
        Assert.Equal("release", operations.Events.Last());
    }

    /// <summary>Successful evidence stays exactly three samples; diagnostics neither add reads nor trigger corrective input.</summary>
    [Fact]
    public async Task SuccessfulVerificationKeepsSeparateDetachedDiagnostics()
    {
        var operations = new FakeOperations();
        var workflow = new NavigationResetTask(operations);
        var samples = await workflow.RunAsync(0, _ => { }, CancellationToken.None);
        Assert.Equal(3, samples.Length);
        Assert.True(NavigationResetTask.AcceptSamples(samples, 0));
        var diagnostics = workflow.VerificationDiagnostics;
        Assert.Equal(new[] { "sample_count_not_three", "sample_count_not_three", "accepted" }, diagnostics.Select(item => item.Reason));
        Assert.Equal(samples, diagnostics.Select(item => item.Sample));
        Assert.Equal(120, diagnostics[^1].MinimumAcquisitionGapMs);
        diagnostics[0] = diagnostics[0] with { Reason = "changed_by_reader" };
        Assert.Equal("sample_count_not_three", workflow.VerificationDiagnostics[0].Reason);
        Assert.Equal(new[] { "prepare", "teleport", "rotate", "read", "read", "read", "release" }, operations.Events);
    }

    /// <summary>Failure diagnostics survive the same TaskRunner-style exception mapping used by the external command.</summary>
    [Fact]
    public async Task OwnerPublishesFailureDiagnosticsWithoutSuccessSamples()
    {
        var sequence = VerificationSequence("position_spread_exceeded");
        var workflow = new NavigationResetTask(new FakeOperations { SampleAt = index => sequence[index] });
        var owner = new NavigationResetTaskOwner();
        owner.TryStart(0, 10, 3, async (ct, phase) =>
        {
            try
            {
                var samples = await workflow.RunAsync(0, phase, ct);
                return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, samples, workflow.VerificationDiagnostics);
            }
            catch (InvalidOperationException error)
            {
                return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = error.Message }, null, workflow.VerificationDiagnostics);
            }
        });
        await WaitForIdle(owner);
        var status = owner.Snapshot();
        Assert.Equal("failed", status.State);
        Assert.Equal("verifying", status.Phase);
        Assert.Equal("pose_not_settled", status.Error);
        Assert.Empty(status.Samples);
        Assert.NotNull(status.VerificationDiagnostics);
        Assert.Equal(15, status.VerificationDiagnostics.Length);
        Assert.Equal("position_spread_exceeded", status.VerificationDiagnostics[^1].Reason);
        var json = System.Text.Json.JsonSerializer.Serialize(status);
        Assert.Contains("\"verificationDiagnostics\"", json);
        Assert.Contains("\"samples\":[]", json);
        status.VerificationDiagnostics[0] = status.VerificationDiagnostics[0] with { Reason = "changed_by_reader" };
        Assert.Equal("sample_count_not_three", owner.Snapshot().VerificationDiagnostics![0].Reason);
    }

    /// <summary>Cancellation after a returned pose retains it as unevaluated, never as an accepted sample or extra rotation.</summary>
    [Fact]
    public async Task CancellationRetainsReadDiagnosticsAndStillReleasesInput()
    {
        var owner = new NavigationResetTaskOwner();
        var operations = new FakeOperations { AfterRead = index => { if (index == 2) owner.Cancel(); } };
        var workflow = new NavigationResetTask(operations);
        owner.TryStart(0, 10, 3, async (ct, phase) =>
        {
            try
            {
                var samples = await workflow.RunAsync(0, phase, ct);
                return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, samples, workflow.VerificationDiagnostics);
            }
            catch (OperationCanceledException)
            {
                return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Cancelled }, null, workflow.VerificationDiagnostics);
            }
        });
        await WaitForIdle(owner);
        var status = owner.Snapshot();
        Assert.Equal("cancelled", status.State);
        Assert.Empty(status.Samples);
        Assert.NotNull(status.VerificationDiagnostics);
        Assert.Equal(3, status.VerificationDiagnostics.Length);
        Assert.Equal("cancelled_before_verification", status.VerificationDiagnostics[^1].Reason);
        Assert.Equal(new[] { "prepare", "teleport", "rotate", "read", "read", "read", "release" }, operations.Events);
    }

    /// <summary>The status boundary also caps diagnostic arrays supplied by an executor and copies them before publication.</summary>
    [Fact]
    public async Task OwnerBoundsRetainedDiagnostics()
    {
        var sample = Samples()[0];
        var diagnostics = Enumerable.Range(1, 20).Select(attempt => new NavigationResetVerificationDiagnostic(
            attempt, sample, 0, "target_yaw_out_of_tolerance", 4, null, null, null)).ToArray();
        var owner = new NavigationResetTaskOwner();
        owner.TryStart(0, 10, 3, (_, _) => Task.FromResult<(SoloTaskRunResult, NavigationResetSample[]?, NavigationResetVerificationDiagnostic[])>(
            (new() { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = "pose_not_settled" }, null, diagnostics)));
        await WaitForIdle(owner);
        Assert.Equal(15, owner.Snapshot().VerificationDiagnostics!.Length);
        Assert.Equal(15, owner.Snapshot().VerificationDiagnostics![^1].Attempt);
        diagnostics[0] = diagnostics[0] with { Reason = "changed_by_executor" };
        Assert.Equal("target_yaw_out_of_tolerance", owner.Snapshot().VerificationDiagnostics![0].Reason);
        Assert.Empty(owner.Snapshot().Samples);
    }

    /// <summary>Fresh same-epoch poses isolate one final-verification failure; all individual native pose gates pass.</summary>
    private static NavigationResetSample[] VerificationSequence(string reason)
    {
        var basis = Samples()[0];
        var intervalMs = reason == "acquisition_spacing_too_short" ? 40 : 120;
        return Enumerable.Range(0, 15).Select(index => basis with
        {
            X = basis.X + (reason == "position_spread_exceeded" ? index % 2 == 0 ? -1 : 1 : 0),
            YawDegrees = reason == "target_yaw_out_of_tolerance" ? 4
                : reason == "yaw_spread_exceeded" ? index % 2 == 0 ? 1.5 : 358.5 : 0,
            SourceTimestamp100ns = basis.SourceTimestamp100ns + index * intervalMs * 10_000L,
            AcquiredAtStopwatchTicks = basis.AcquiredAtStopwatchTicks + index * intervalMs * Stopwatch.Frequency / 1000
        }).ToArray();
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
        /// <summary>Optional deterministic sequence exercising each final verification gate.</summary>
        internal Func<int, NavigationResetSample>? SampleAt { get; init; }
        /// <summary>Optional cancellation injected after a pose returns but before workflow verification.</summary>
        internal Action<int>? AfterRead { get; init; }
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
        {
            Events.Add("read");
            var index = _index++;
            var sample = SampleAt?.Invoke(index) ?? _samples[RepeatFrame ? 0 : Math.Min(index, 2)];
            AfterRead?.Invoke(index);
            return Task.FromResult(sample);
        }
        /// <inheritdoc />
        public Task DelayAsync(int milliseconds, CancellationToken ct) { ct.ThrowIfCancellationRequested(); return Task.CompletedTask; }
        /// <inheritdoc />
        public void ReleaseInput() => Events.Add("release");
    }
}
