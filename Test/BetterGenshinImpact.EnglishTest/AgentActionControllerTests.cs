using BetterGenshinImpact.Core.Agent;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise actual held-state transitions and release behavior without sending Windows input.</summary>
public sealed class AgentActionControllerTests
{
    /// <summary>A chunk executes movement once per interval and releases at its horizon.</summary>
    [Fact]
    public void ExecutesIntervalsOnceAndReleasesAtHorizon()
    {
        var input = new FakeInput();
        var controller = Create(input);
        var proposal = Proposal() with { Steps = [new() { DurationMs = 50, Keys = ["W"], MouseDx = 12 },
            new() { DurationMs = 50, Keys = ["W", "LBUTTON"] }] };
        Assert.Null(controller.Submit(proposal, 110));
        controller.Tick(110);
        controller.Tick(120);
        controller.Tick(160);
        Assert.Equal(1, input.Movements.Count);
        Assert.Contains("LBUTTON", input.Held);
        controller.Tick(210);
        Assert.Empty(input.Held);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal("completed", receipt.Status);
        Assert.Equal(2, receipt.AppliedSteps.Length);
        Assert.Equal(110, receipt.AppliedSteps[0].StartedAtMs);
    }

    /// <summary>Focus loss interrupts held input even with no new model response.</summary>
    [Fact]
    public void FocusLossReleasesHeldKeys()
    {
        var input = new FakeInput();
        var controller = Create(input);
        Assert.Null(controller.Submit(Proposal(), 110));
        controller.Tick(110);
        Assert.Contains("W", input.Held);
        input.IsAvailable = false;
        controller.Tick(120);
        Assert.Empty(input.Held);
        Assert.Equal("window_unavailable", Assert.Single(controller.DrainReceipts()).Reason);
    }

    /// <summary>Returning focus requires a fresh observation even when no chunk was active.</summary>
    [Fact]
    public void FocusRecoveryCannotReuseOldObservation()
    {
        var input = new FakeInput();
        var controller = Create(input);
        input.IsAvailable = false;
        controller.Tick(110);
        input.IsAvailable = true;
        Assert.Equal("world_not_ready", controller.Submit(Proposal(), 120));
        controller.RegisterFrame(new AgentObservation(2, 125, 1920, 1080, AgentWorldEvidence.WorldHud));
        Assert.Equal("world_not_ready", controller.Submit(Proposal() with { FrameId = 2, ObservedAtMs = 125 }, 130));
        controller.RegisterFrame(new AgentObservation(3, 160, 1920, 1080, AgentWorldEvidence.WorldHud));
        Assert.Null(controller.Submit(Proposal() with { FrameId = 3, ObservedAtMs = 160 }, 165));
    }

    /// <summary>A disconnected controller cannot leave movement held or submit another chunk.</summary>
    [Fact]
    public void StopReleasesAndRejectsFurtherInput()
    {
        var input = new FakeInput();
        var controller = Create(input);
        Assert.Null(controller.Submit(Proposal(), 110));
        controller.Tick(110);
        controller.Stop(115, "disconnect");
        Assert.Empty(input.Held);
        Assert.Equal("session_stopped", controller.Submit(Proposal() with { RequestId = "next" }, 120));
    }

    /// <summary>Expired chunks release input instead of extending the previous prediction.</summary>
    [Fact]
    public void ExpirationDoesNotRepeatPreviousInput()
    {
        var input = new FakeInput();
        var controller = Create(input);
        Assert.Null(controller.Submit(Proposal() with { ExpiresAtMs = 170 }, 110));
        controller.Tick(110);
        controller.Tick(180);
        Assert.Empty(input.Held);
        Assert.Equal("deadline_expired", Assert.Single(controller.DrainReceipts()).Reason);
    }

    /// <summary>Capture timestamps must match metadata issued by the server.</summary>
    [Theory]
    [InlineData(99, 110, "observation_timestamp_mismatch")]
    [InlineData(100, 601, "world_not_ready")]
    [InlineData(100, 99, "stale_frame")]
    public void RejectsInventedOrStaleObservations(double observationTime, double now, string reason)
    {
        var input = new FakeInput();
        var controller = Create(input);
        Assert.Equal(reason, controller.Submit(Proposal() with { ObservedAtMs = observationTime }, now));
        Assert.Empty(input.Held);
    }

    /// <summary>Input-disable is enforced by the executor independently of the Python client.</summary>
    [Fact]
    public void ObserveOnlyNeverInjectsInput()
    {
        var input = new FakeInput();
        var controller = Create(input, false);
        Assert.Equal("input_disabled", controller.Submit(Proposal(), 110));
        controller.Tick(120);
        controller.Stop(125, "stop");
        Assert.Equal(0, input.ReleaseCount);
        Assert.Empty(input.Held);
    }

    /// <summary>Malformed model output cannot bypass key, mouse, or temporal bounds.</summary>
    [Fact]
    public void RejectsIllegalOutputAndNonFiniteDeadlines()
    {
        var controller = Create(new FakeInput());
        Assert.Equal("invalid_keys", controller.Submit(Proposal() with { Steps = [new() { DurationMs = 50, Keys = ["LWIN"] }] }, 110));
        Assert.Equal("invalid_mouse_delta", controller.Submit(Proposal() with { Steps = [new() { DurationMs = 50, MouseDx = int.MinValue }] }, 110));
        Assert.Equal("invalid_interval", controller.Submit(Proposal() with { Steps = [new() { DurationMs = 1 }] }, 110));
        Assert.Equal("invalid_deadline", controller.Submit(Proposal() with { ExpiresAtMs = double.NaN }, 110));
        Assert.Equal("reserved_hotkey", controller.Submit(Proposal() with { Steps = [new() { DurationMs = 50,
            Keys = ["LCONTROL", "LSHIFT", "ESCAPE"] }] }, 110));
        Assert.Equal("invalid_horizon", controller.Submit(Proposal() with { Steps = [new() { DurationMs = 100 },
            new() { DurationMs = 100 }, new() { DurationMs = 100 }] }, 110));
    }

    /// <summary>Replay is rejected even after the original action finished.</summary>
    [Fact]
    public void CompletedRequestCannotBeReplayed()
    {
        var controller = Create(new FakeInput());
        Assert.Null(controller.Submit(Proposal(), 110));
        controller.Tick(110);
        controller.Tick(160);
        Assert.Equal("replayed_request", controller.Submit(Proposal(), 170));
    }

    /// <summary>Long sessions prune expired replay entries without imposing a lifetime action limit.</summary>
    [Fact]
    public void MoreThanTenThousandActionsDoNotRequireSessionRestart()
    {
        var controller = Create(new FakeInput());
        for (var index = 0; index < 11000; index++)
        {
            var time = 100 + index * 50;
            controller.RegisterFrame(new AgentObservation(index + 2, time, 1920, 1080, AgentWorldEvidence.WorldHud));
            Assert.Null(controller.Submit(Proposal() with { RequestId = index.ToString(), FrameId = index + 2,
                ObservedAtMs = time, ExpiresAtMs = time + 150 }, time));
            controller.Tick(time);
            controller.Tick(time + 50);
        }
        Assert.Equal("world_not_ready", controller.Submit(Proposal() with { RequestId = "past", FrameId = 11001,
            ObservedAtMs = 550050, ExpiresAtMs = 550800 }, 551000));
    }

    /// <summary>Expiring an early deadline does not allow the same request to be replayed with a longer one.</summary>
    [Fact]
    public void ExtendingDeadlineDoesNotBypassReplayProtection()
    {
        var controller = Create(new FakeInput());
        Assert.Null(controller.Submit(Proposal() with { ExpiresAtMs = 170 }, 110));
        controller.Tick(110);
        controller.Tick(170);
        Assert.Equal("replayed_request", controller.Submit(Proposal() with { ExpiresAtMs = 500 }, 180));
    }

    /// <summary>An older concurrent inference result cannot replace the newer accepted observation.</summary>
    [Fact]
    public void OutOfOrderInferenceCannotReplaceNewerFrame()
    {
        var input = new FakeInput();
        var controller = Create(input);
        controller.RegisterFrame(new AgentObservation(2, 105, 1920, 1080, AgentWorldEvidence.WorldHud));
        Assert.Null(controller.Submit(Proposal() with { FrameId = 2, ObservedAtMs = 105 }, 110));
        Assert.Equal("superseded_frame", controller.Submit(Proposal() with { RequestId = "older" }, 115));
        controller.Tick(120);
        Assert.Equal(new[] { "W" }, input.Held);
    }

    /// <summary>Resizing invalidates earlier camera coordinates and stops the active plan.</summary>
    [Fact]
    public void ViewportChangeInvalidatesOldFramesAndReleasesInput()
    {
        var input = new FakeInput();
        var controller = Create(input);
        Assert.Null(controller.Submit(Proposal(), 110));
        controller.Tick(110);
        controller.RegisterFrame(new AgentObservation(2, 120, 1280, 720, AgentWorldEvidence.WorldHud));
        Assert.Empty(input.Held);
        Assert.Equal("viewport_changed", Assert.Single(controller.DrainReceipts()).Reason);
        Assert.Equal("world_not_ready", controller.Submit(Proposal() with { RequestId = "new" }, 125));
    }

    /// <summary>A stalled executor releases rather than sending overdue transitions in a burst.</summary>
    [Fact]
    public void MissedScheduleCancelsInsteadOfCatchingUp()
    {
        var input = new FakeInput();
        var controller = Create(input);
        Assert.Null(controller.Submit(Proposal() with { Steps = [new() { DurationMs = 50, Keys = ["W"] },
            new() { DurationMs = 50, Keys = ["S"], MouseDx = 25 }] }, 110));
        controller.Tick(110);
        controller.Tick(220);
        Assert.Empty(input.Held);
        Assert.Empty(input.Movements);
        Assert.Equal("scheduler_late", Assert.Single(controller.DrainReceipts()).Reason);
    }

    /// <summary>A newer result replaces the old plan without letting queued actions accumulate.</summary>
    [Fact]
    public void ReplacementSwitchesHeldStateAndRecordsBothPlans()
    {
        var input = new FakeInput();
        var controller = Create(input);
        Assert.Null(controller.Submit(Proposal(), 110));
        controller.Tick(110);
        Assert.Null(controller.Submit(Proposal() with { RequestId = "next", Steps = [new() { DurationMs = 50, Keys = ["S"] }] }, 130));
        controller.Tick(130);
        Assert.Equal(new[] { "S" }, input.Held);
        controller.Tick(180);
        Assert.Empty(input.Held);
        Assert.Equal(new[] { "replaced", "completed" }, controller.DrainReceipts().Select(r => r.Status));
    }

    /// <summary>The controller snapshots arrays; later mutation cannot inject unchecked keys.</summary>
    [Fact]
    public void SnapshotsAcceptedInput()
    {
        var input = new FakeInput();
        var controller = Create(input);
        var proposal = Proposal();
        Assert.Null(controller.Submit(proposal, 110));
        proposal.Steps[0].Keys[0] = "LWIN";
        controller.Tick(110);
        Assert.Equal(new[] { "W" }, input.Held);
    }

    /// <summary>Receipt overflow is detectable, bounded, and does not block ongoing control.</summary>
    [Fact]
    public void ReceiptQueueReportsOverflow()
    {
        var controller = Create(new FakeInput());
        for (var i = 0; i < 260; i++)
        {
            var time = 100 + i * 100;
            controller.RegisterFrame(new AgentObservation(i + 2, time, 1920, 1080, AgentWorldEvidence.WorldHud));
            Assert.Null(controller.Submit(Proposal() with { RequestId = i.ToString(), FrameId = i + 2,
                ObservedAtMs = time, ExpiresAtMs = time + 200 }, time));
            controller.Tick(time);
            controller.Tick(time + 50);
        }
        Assert.Equal(4, controller.DroppedReceipts);
        Assert.Equal(256, controller.DrainReceipts().Length);
    }

    /// <summary>Construct a session with one known capture.</summary>
    private static AgentActionController Create(FakeInput input, bool enabled = true)
    {
        var controller = new AgentActionController(input, enabled);
        controller.RegisterFrame(new AgentObservation(0, 60, 1920, 1080, AgentWorldEvidence.WorldHud));
        controller.RegisterFrame(new AgentObservation(1, 100, 1920, 1080, AgentWorldEvidence.WorldHud));
        return controller;
    }

    /// <summary>Default valid short movement proposal.</summary>
    private static AgentRequest Proposal() => new()
    {
        RequestId = "test", ModelId = "fixture", FrameId = 1, ObservedAtMs = 100, ExpiresAtMs = 500,
        Steps = [new() { DurationMs = 50, Keys = ["W"] }]
    };

    /// <summary>Records applied input rather than simulating Windows keystrokes.</summary>
    private sealed class FakeInput : IAgentInput
    {
        /// <inheritdoc />
        public bool IsAvailable { get; set; } = true;
        /// <summary>Current actual held state of this fake backend.</summary>
        public string[] Held { get; private set; } = [];
        /// <summary>Actual relative movement calls.</summary>
        public List<(int, int)> Movements { get; } = [];
        /// <summary>Number of release operations performed.</summary>
        public int ReleaseCount { get; private set; }
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) => Held = keys.ToArray();
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) => Movements.Add((dx, dy));
        /// <inheritdoc />
        public void ReleaseAll() { Held = []; ReleaseCount++; }
    }
}
