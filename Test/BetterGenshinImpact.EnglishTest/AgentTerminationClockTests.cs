using BetterGenshinImpact.Core.Agent;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Terminal receipts include lock delay without inventing physical input timing.</summary>
public sealed class AgentTerminationClockTests
{
    /// <summary>A caller's earlier timestamp must not precede input already dispatched under the lock.</summary>
    [Theory]
    [InlineData("stop")]
    [InlineData("release")]
    [InlineData("invalidate")]
    public void TerminalReleaseRefreshesStaleCallerTime(string operation)
    {
        var actualTime = 110.0;
        var input = new RecordingInput();
        var controller = Create(input, () => actualTime);
        Assert.Null(controller.Submit(Proposal(), 110));
        actualTime = 130;
        controller.Tick(115);
        Assert.Contains("W", input.Held);
        actualTime = 135;
        if (operation == "stop") controller.Stop(120, "client_stop");
        else if (operation == "release") controller.Release(120);
        else controller.InvalidateWorld(120, "capture_stopped");
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal(130, Assert.Single(receipt.AppliedSteps).StartedAtMs);
        Assert.Equal(135, receipt.EndedAtMs);
        Assert.Empty(input.Held);
    }

    /// <summary>Replacement retains one exact timestamp for the old end and new acceptance.</summary>
    [Fact]
    public void ReplacementDoesNotResampleItsSharedBoundary()
    {
        var actualTime = 110.0;
        var input = new RecordingInput();
        var controller = Create(input, () => actualTime++);
        Assert.Null(controller.Submit(Proposal(), 110));
        actualTime = 130;
        controller.Tick(115);
        actualTime = 145;
        Assert.Null(controller.Submit(Proposal() with { RequestId = "successor" }, 140, out var accepted));
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal("replaced", receipt.Status);
        Assert.Equal(accepted, receipt.EndedAtMs);
        Assert.Equal(145, accepted);
        Assert.Contains("W", input.Held);
    }

    /// <summary>A failed optional clock cannot prevent cleanup; the original caller time remains explicit.</summary>
    [Fact]
    public void ClockFailureStillReleasesInput()
    {
        var failClock = false;
        var input = new RecordingInput();
        var controller = Create(input, () => failClock ? throw new InvalidOperationException("clock") : 110);
        Assert.Null(controller.Submit(Proposal(), 110));
        controller.Tick(110);
        failClock = true;
        controller.Stop(140, "disconnect");
        Assert.Empty(input.Held);
        Assert.Equal(140, Assert.Single(controller.DrainReceipts()).EndedAtMs);
    }

    /// <summary>Use a deterministic session clock and two independent world confirmations.</summary>
    private static AgentActionController Create(RecordingInput input, Func<double> clock)
    {
        var controller = new AgentActionController(input, true, clock);
        controller.RegisterFrame(new AgentObservation(0, 60, 1920, 1080, AgentWorldEvidence.WorldHud));
        controller.RegisterFrame(new AgentObservation(1, 100, 1920, 1080, AgentWorldEvidence.WorldHud));
        return controller;
    }

    /// <summary>One bounded movement with a first-input deadline exercises the actual dispatch clock.</summary>
    private static AgentRequest Proposal() => new()
    {
        RequestId = "terminal-clock", ModelId = "fixture", FrameId = 1, ObservedAtMs = 100,
        ExpiresAtMs = 500, StartBeforeMs = 150, Steps = [new() { DurationMs = 50, Keys = ["W"] }]
    };

    /// <summary>In-memory input boundary; these tests never invoke Windows input.</summary>
    private sealed class RecordingInput : IAgentInput
    {
        /// <inheritdoc />
        public bool IsAvailable => true;
        /// <summary>Last complete held state requested from the fake backend.</summary>
        public string[] Held { get; private set; } = [];
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) => Held = keys.ToArray();
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) { }
        /// <inheritdoc />
        public void ReleaseAll() => Held = [];
    }
}
