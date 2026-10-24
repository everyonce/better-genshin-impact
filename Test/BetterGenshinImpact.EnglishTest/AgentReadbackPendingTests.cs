using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using Fischless.GameCapture;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise the actual stream skip boundary and independent controller; no pipe, native input or model.</summary>
public sealed class AgentReadbackPendingTests
{
    /// <summary>Polling must neither invalidate fresh authority nor renew it; stale input releases through the original watchdog.</summary>
    [Fact]
    public void PendingKeepsOriginalAuthorityWhichExpiresWithoutNewFrames()
    {
        var stream = new AgentStreamSession(null!); var input = new Input();
        var controller = new AgentActionController(input, true);
        controller.RegisterFrame(new(1, 60, 1920, 1080, AgentWorldEvidence.WorldHud), 61);
        controller.RegisterFrame(new(2, 100, 1920, 1080, AgentWorldEvidence.WorldHud), 101);
        var before = controller.GetWorldReadiness(101);
        Assert.Null(controller.Submit(new() { RequestId = "pending", ModelId = "test", FrameId = 2,
            ObservedAtMs = 100, ExpiresAtMs = 400,
            Steps = [new() { DurationMs = 100, Keys = ["W"] }, new() { DurationMs = 100, Keys = ["W"] }] }, 110));
        controller.Tick(110);
        var pending = new GameCaptureAttempt(GameCaptureAttemptOutcome.ReadbackPending,
            pending: GameCaptureReadbackConsumerTests.Pending());
        Assert.True(stream.SkipUnpublishedCapture(pending, controller, 120));
        Assert.Equal(new[] { "W" }, input.Held);
        controller.Tick(130);
        var still = controller.GetWorldReadiness(130);
        Assert.Equal(before.Epoch, still.Epoch); Assert.Equal(2, still.SourceFrameId);
        Assert.True(stream.SkipUnpublishedCapture(pending, controller, 250));
        controller.Tick(251);
        Assert.Empty(input.Held); Assert.Equal("world_observation_stale", Assert.Single(controller.DrainReceipts()).Reason);
        Assert.False(controller.RegisterFrame(new(3, 280, 1920, 1080, AgentWorldEvidence.WorldHud), 281).Ready);
        Assert.True(controller.RegisterFrame(new(4, 315, 1920, 1080, AgentWorldEvidence.WorldHud), 316).Ready);
    }

    /// <summary>Unavailable remains a negative gate while Ready plus refill still proceeds to the normal recognition path.</summary>
    [Fact]
    public void UnavailableAndReadyRefillRemainDistinct()
    {
        var stream = new AgentStreamSession(null!); var input = new Input();
        var controller = new AgentActionController(input, true);
        controller.RegisterFrame(new(1, 60, 1920, 1080, AgentWorldEvidence.WorldHud), 61);
        controller.RegisterFrame(new(2, 100, 1920, 1080, AgentWorldEvidence.WorldHud), 101);
        Assert.True(stream.SkipUnpublishedCapture(default, controller, 110));
        Assert.False(controller.GetWorldReadiness(110).Ready);
        using var frame = new GameCaptureFrame(new Mat(3, 4, MatType.CV_8UC3, Scalar.All(1)));
        Assert.False(stream.SkipUnpublishedCapture(new(GameCaptureAttemptOutcome.FrameReady, frame,
            GameCaptureReadbackConsumerTests.Pending()), controller, 120));
        Assert.False(frame.Frame.IsDisposed);
    }

    /// <summary>Record only in-memory requested state; never touch the Windows input backend.</summary>
    private sealed class Input : IAgentInput
    {
        /// <inheritdoc />
        public bool IsAvailable => true;
        /// <summary>Current fake key state.</summary>
        internal string[] Held = [];
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) => Held = keys.ToArray();
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) { }
        /// <inheritdoc />
        public void ReleaseAll() => Held = [];
    }
}
