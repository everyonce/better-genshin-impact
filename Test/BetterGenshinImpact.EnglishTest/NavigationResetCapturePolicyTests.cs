using System.Diagnostics;
using System.IO;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using BetterGenshinImpact.GameTask.NavigationReset;
using BetterGenshinImpact.GameTask.SoloTask.Execution;
using BetterGenshinImpact.Service.ExternalControl;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Reset phase, evidence, owner and same-frame chat tests without a game or native input backend.</summary>
public sealed class NavigationResetCapturePolicyTests
{
    /// <summary>One synthetic detector result; no recognition accuracy is inferred from these fixtures.</summary>
    private static ChatUiDetectionResult Chat(ChatUiState state) => new(state, true, true, true, 2, true);

    /// <summary>Only completion of the awaited teleport may start isolation, and no pose/input work may pass a pending drain.</summary>
    [Fact]
    public async Task IsolationOccursAfterTeleportAndBeforeFirstOrientation()
    {
        var events = new List<string>();
        var teleport = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var isolate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var isolating = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var operations = new Operations(events) { TeleportWait = teleport.Task };
        var workflow = new NavigationResetTask(operations, async ct =>
        {
            events.Add("isolate"); isolating.SetResult(); await isolate.Task.WaitAsync(ct); events.Add("isolated");
        });
        var run = workflow.RunAsync(0, phase => events.Add("phase:" + phase), default);
        Assert.DoesNotContain("isolate", events); Assert.DoesNotContain("rotate", events);
        teleport.SetResult(); await isolating.Task.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.DoesNotContain("rotate", events); Assert.DoesNotContain("read", events);
        isolate.SetResult(); var result = await run;
        Assert.True(NavigationResetTask.AcceptSamples(result, 0));
        Assert.True(events.IndexOf("teleport_done") < events.IndexOf("isolate"));
        Assert.True(events.IndexOf("isolated") < events.IndexOf("rotate"));
        Assert.Equal("release", events[^1]);
    }

    /// <summary>Legacy shared mode never gains a new phase or changes the fixed workflow's input order.</summary>
    [Fact]
    public async Task SharedWorkflowHasNoIsolationPhase()
    {
        var events = new List<string>();
        var samples = await new NavigationResetTask(new Operations(events)).RunAsync(0, phase => events.Add("phase:" + phase), default);
        Assert.True(NavigationResetTask.AcceptSamples(samples, 0)); Assert.DoesNotContain("phase:isolating_capture", events);
        Assert.True(events.IndexOf("teleport_done") < events.IndexOf("rotate"));
    }

    /// <summary>Teleport failure and all activation failure/cancellation paths release input without a pose or camera call.</summary>
    [Theory]
    [InlineData("teleport")]
    [InlineData("activation")]
    [InlineData("cancel_pending")]
    [InlineData("cancel_after")]
    public async Task FailedIsolationNeverReachesOrientation(string failure)
    {
        var events = new List<string>(); using var stop = new CancellationTokenSource();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var operations = new Operations(events) { FailTeleport = failure == "teleport" };
        var workflow = new NavigationResetTask(operations, async ct =>
        {
            events.Add("isolate"); entered.TrySetResult();
            if (failure == "activation") throw new TimeoutException("timer_capture_drain_timeout");
            if (failure == "cancel_after") stop.Cancel();
            if (failure == "cancel_pending") await Task.Delay(Timeout.Infinite, ct);
        });
        var run = workflow.RunAsync(0, _ => { }, stop.Token);
        if (failure == "cancel_pending") { await entered.Task.WaitAsync(TimeSpan.FromSeconds(5)); stop.Cancel(); }
        await Assert.ThrowsAnyAsync<Exception>(() => run);
        Assert.DoesNotContain("rotate", events); Assert.DoesNotContain("read", events); Assert.Equal("release", events[^1]);
        Assert.Equal(failure != "teleport", events.Contains("isolate"));
    }

    /// <summary>Direct open/unknown chat evidence aborts on the same admitted Mat, without waiting for global debounce.</summary>
    [Theory]
    [InlineData(ChatUiState.PanelOpen)]
    [InlineData(ChatUiState.InputOpen)]
    [InlineData((ChatUiState)99)]
    public void ChatBlocksBeforeWorldRecognition(ChatUiState state)
    {
        using var frame = new Mat(2, 2, MatType.CV_8UC3, Scalar.All(5));
        var updated = false;
        Assert.Throws<InvalidOperationException>(() => NavigationResetCapturePolicy.RecognizeWorld(frame, true,
            source => { Assert.Same(frame, source); return Chat(state); },
            _ => throw new Exception("world must not run"), chat => { Assert.Equal(state, chat.State); updated = true; }));
        Assert.True(updated); Assert.Equal(5, frame.At<Vec3b>(0, 0).Item0);
    }

    /// <summary>Closed-chat state updates precede world detection and share the original supported full-size native frame.</summary>
    [Fact]
    public void OwnedWorldUsesSameNativePixelsAndUpdatesChatFirst()
    {
        using var frame = new Mat(1080, 1920, MatType.CV_8UC3);
        var order = new List<string>();
        var result = NavigationResetCapturePolicy.RecognizeWorld(frame, true,
            source => { Assert.Same(frame, source); order.Add("chat"); return Chat(ChatUiState.Closed); },
            source => { Assert.Same(frame, source); order.Add("world"); return AgentWorldEvidence.HudMissing; },
            _ => order.Add("update"));
        Assert.Equal(AgentWorldEvidence.HudMissing, result); Assert.Equal(new[] { "chat", "update", "world" }, order);
    }

    /// <summary>Shared and pre-teleport phases do not acquire additional chat work or inherit the owned geometry restriction.</summary>
    [Fact]
    public void NonIsolatedPathRetainsLegacyRecognition()
    {
        using var frame = new Mat(1440, 2560, MatType.CV_8UC3);
        Assert.Equal(AgentWorldEvidence.WorldHud, NavigationResetCapturePolicy.RecognizeWorld(frame, false,
            _ => throw new Exception("no added chat"), source => { Assert.Same(frame, source); return AgentWorldEvidence.WorldHud; },
            _ => throw new Exception("no chat update")));
    }

    /// <summary>Oversized or empty raw frames cannot falsely pass uncalibrated chat recognition.</summary>
    [Theory]
    [InlineData(1921, 1)]
    [InlineData(1, 1081)]
    [InlineData(0, 0)]
    public void OwnedGeometryFailsBeforeAnyRecognition(int width, int height)
    {
        using var frame = new Mat(height, width, MatType.CV_8UC3);
        var error = Assert.Throws<InvalidOperationException>(() => NavigationResetCapturePolicy.RecognizeWorld(frame, true,
            _ => throw new Exception("no chat"), _ => throw new Exception("no world"), _ => throw new Exception("no update")));
        Assert.StartsWith("unsupported_chat_frame_geometry:", error.Message);
    }

    /// <summary>Detector errors remain terminal rather than invented closed-chat/world evidence.</summary>
    [Fact]
    public void DetectorFailureIsNotTreatedAsClosed()
    {
        using var frame = new Mat(2, 2, MatType.CV_8UC3);
        Assert.Throws<IOException>(() => NavigationResetCapturePolicy.RecognizeWorld(frame, true,
            _ => throw new IOException("detector failed"), _ => throw new Exception("no world"), _ => throw new Exception("no update")));
    }

    /// <summary>The original owner deadline covers isolation; it is never restarted after teleport.</summary>
    [Fact]
    public async Task OwnerDeadlineCoversPostTeleportDrainAndRetainsSelectedPolicy()
    {
        Assert.Equal(TimeSpan.FromSeconds(75), NavigationResetTask.Timeout);
        var events = new List<string>(); var owner = new NavigationResetTaskOwner();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Assert.True(owner.TryStart(0, 10, 3, async (token, phase) =>
        {
            var workflow = new NavigationResetTask(new Operations(events), async ct =>
            { entered.TrySetResult(); await Task.Delay(Timeout.Infinite, ct); });
            var samples = await workflow.RunAsync(0, phase, token);
            return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }, samples, workflow.VerificationDiagnostics);
        }, timeout: TimeSpan.FromSeconds(1), capturePolicy: NavigationResetCapturePolicy.TaskOwnedTimer));
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        using var bounded = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        while (owner.Running) await Task.Delay(5, bounded.Token);
        var status = owner.Snapshot();
        Assert.Equal("failed", status.State); Assert.Equal("reset_deadline_exceeded", status.Error);
        Assert.Equal("isolating_capture", status.Phase); Assert.Equal("task_owned_timer", status.CapturePolicy);
        Assert.Empty(status.Samples); Assert.DoesNotContain("rotate", events); Assert.Equal("release", events[^1]);
        Assert.Null(owner.TryGetDiagnostics(status.RunId!, out var diagnostics));
        Assert.Equal(status.CapturePolicy, diagnostics!.CapturePolicy);
        var json = JsonSerializer.SerializeToElement(status, ExternalControlProtocol.JsonOptions);
        Assert.Equal("task_owned_timer", json.GetProperty("capturePolicy").GetString());
        Assert.Equal(new[] { "shared", "task_owned_timer" }, status.CapturePolicies);
    }

    /// <summary>Invalid policy cannot claim an owner or dispatch code; an untouched status advertises legacy shared.</summary>
    [Fact]
    public void OwnerRejectsUnknownPolicyBeforeDispatch()
    {
        var owner = new NavigationResetTaskOwner();
        Assert.Throws<ArgumentException>(() => owner.TryStart(0, 10, 3, (_, _) => throw new Exception("must not dispatch"),
            capturePolicy: "exclusive"));
        Assert.False(owner.Running); Assert.Equal("shared", owner.Snapshot().CapturePolicy);
    }

    /// <summary>Deterministic workflow boundary with fresh synthetic pose observations.</summary>
    private sealed class Operations(List<string> events) : INavigationResetOperations
    {
        /// <summary>Keep all synthetic frames in one generation.</summary>
        private readonly Guid _epoch = Guid.NewGuid();
        /// <summary>Distinct positive acquisition times, spaced120ms.</summary>
        private int _index;
        /// <summary>Optional held teleport demonstrates that activation cannot run early.</summary>
        internal Task TeleportWait { get; init; } = Task.CompletedTask;
        /// <summary>Fail before teleport completion without granting isolation.</summary>
        internal bool FailTeleport { get; init; }
        /// <inheritdoc />
        public Task PrepareAsync(CancellationToken ct) { events.Add("prepare"); return Task.CompletedTask; }
        /// <inheritdoc />
        public async Task TeleportAsync(CancellationToken ct)
        {
            events.Add("teleport_begin");
            if (FailTeleport) throw new InvalidOperationException("teleport_failed");
            await TeleportWait.WaitAsync(ct); events.Add("teleport_done");
        }
        /// <inheritdoc />
        public Task<bool> RotateAsync(double yaw, CancellationToken ct) { events.Add("rotate"); return Task.FromResult(true); }
        /// <inheritdoc />
        public Task<NavigationResetSample> ReadPoseAsync(CancellationToken ct)
        {
            events.Add("read"); var index = _index++;
            return Task.FromResult(new NavigationResetSample(NavigationResetTask.SpawnX, NavigationResetTask.SpawnY, 0,
                DateTimeOffset.UtcNow, _epoch, 100_000_000 + index * 1_200_000L,
                10 * Stopwatch.Frequency + index * Stopwatch.Frequency * 12 / 100, .999, .9, "City_102"));
        }
        /// <inheritdoc />
        public Task DelayAsync(int milliseconds, CancellationToken ct) { ct.ThrowIfCancellationRequested(); return Task.CompletedTask; }
        /// <inheritdoc />
        public void ReleaseInput() => events.Add("release");
    }
}
