using BetterGenshinImpact.Core.Agent;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Readiness and release acknowledgements use the session clock after blocking controller work.</summary>
public sealed class AgentWorldReadinessSnapshotTests
{
    /// <summary>A slow availability check cannot preserve evidence that expired while it ran.</summary>
    [Fact]
    public void SnapshotSamplesAfterAvailabilityAndExpiresOldEvidence()
    {
        var now = 130d;
        var input = new DelayedInput();
        var controller = ReadyController(input, () => now);
        input.OnAvailability = () => now = 280;

        var readiness = controller.GetWorldReadinessSnapshot(out var sampledAt);

        Assert.Equal(280, sampledAt);
        Assert.False(readiness.Ready);
        Assert.Equal("world_observation_stale", readiness.Reason);
        Assert.Equal(sampledAt, readiness.CheckedAtMs);
    }

    /// <summary>Replay the r11 timestamps: current readiness may be newer than the retained RGB frame and request time.</summary>
    [Fact]
    public void SnapshotTimeIncludesTheLatestRegisteredReadiness()
    {
        var now = 2115.2839;
        var input = new DelayedInput();
        var controller = new AgentActionController(input, false, () => now);
        const string epoch = "7e0ffe11aafd4e8ca05f667b3373a923";
        controller.RegisterFrame(new(61, 2091.7852, 1920, 1080, AgentWorldEvidence.WorldHud, 8.6942,
            new(epoch, 1021798125000, 2106.3236, 2091.8314)), 2104.2657);
        Assert.True(controller.RegisterFrame(new(62, 2122.8207, 1920, 1080, AgentWorldEvidence.WorldHud, 9.6687,
            new(epoch, 1021798437500, 2137.5736, 2122.894)), 2135.8878).Ready);
        input.OnAvailability = () => now = 2136;

        var readiness = controller.GetWorldReadinessSnapshot(out var sampledAt);

        Assert.True(readiness.Ready);
        Assert.Equal(62, readiness.SourceFrameId);
        Assert.Equal(2136, sampledAt);
        Assert.True(readiness.CheckedAtMs <= sampledAt);
        Assert.True(readiness.SourceFrame!.AcquiredAtMs <= sampledAt);
        Assert.True(readiness.SourceFrame.FreshnessAtMs <= sampledAt);
    }

    /// <summary>A release acknowledgement cannot authorize pixels captured before a delayed key release completed.</summary>
    [Fact]
    public void PostReleaseSnapshotFollowsInputReleaseCompletion()
    {
        var now = 130d;
        var input = new DelayedInput();
        var controller = ReadyController(input, () => now);
        input.OnRelease = () => now = 200;

        controller.Release(130);
        var readiness = controller.GetWorldReadinessSnapshot(out var acknowledgedAt);

        Assert.Equal(200, acknowledgedAt);
        Assert.False(readiness.Ready);
        Assert.Equal("client_release", readiness.Reason);

        // A delayed in-flight capture cannot become one of the two required post-release confirmations.
        var delayed = controller.RegisterFrame(new(3, 160, 1920, 1080, AgentWorldEvidence.WorldHud), 210);
        Assert.False(delayed.Ready);
        Assert.Equal("world_observation_invalidated", delayed.Reason);
        Assert.Equal(readiness.Epoch, delayed.Epoch);
        Assert.False(controller.RegisterFrame(new(4, 220, 1920, 1080, AgentWorldEvidence.WorldHud), 221).Ready);
        var resumed = controller.RegisterFrame(new(5, 240, 1920, 1080, AgentWorldEvidence.WorldHud), 241);
        Assert.True(resumed.Ready);
        Assert.Equal(readiness.Epoch, resumed.Epoch);
    }

    /// <summary>Two distinct fresh world observations establish the fixture without Windows input.</summary>
    private static AgentActionController ReadyController(DelayedInput input, Func<double> clock)
    {
        var controller = new AgentActionController(input, true, clock);
        controller.RegisterFrame(new(1, 80, 1920, 1080, AgentWorldEvidence.WorldHud));
        Assert.True(controller.RegisterFrame(new(2, 120, 1920, 1080, AgentWorldEvidence.WorldHud)).Ready);
        return controller;
    }

    /// <summary>Advances a deterministic clock during operations that can block in the real input boundary.</summary>
    private sealed class DelayedInput : IAgentInput
    {
        /// <summary>Optional simulated delay during focus validation.</summary>
        public Action? OnAvailability { get; set; }
        /// <summary>Optional simulated delay while releasing held keys.</summary>
        public Action? OnRelease { get; set; }
        /// <inheritdoc />
        public bool IsAvailable { get { OnAvailability?.Invoke(); return true; } }
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) { }
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) { }
        /// <inheritdoc />
        public void ReleaseAll() => OnRelease?.Invoke();
    }
}
