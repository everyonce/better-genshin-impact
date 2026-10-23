using BetterGenshinImpact.Core.Agent;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Keep future reported compositor times separate from immutable acquisition-based freshness leases.</summary>
public sealed class AgentAcquisitionFreshnessTests
{
    /// <summary>One native capture generation shared by deterministic fixtures.</summary>
    private const string Epoch = "22222222222222222222222222222222";

    /// <summary>Raw times remain intact while the earlier value determines the explicitly named freshness clock.</summary>
    [Theory]
    [InlineData(70, 100, 70, "reported_compositor_qpc")]
    [InlineData(130, 100, 100, "first_acquisition_qpc")]
    [InlineData(100, 100, 100, "reported_compositor_qpc")]
    [InlineData(10, -20, -20, "first_acquisition_qpc")]
    public void AnchorUsesEarlierImmutableTime(double reported, double acquired, double expected, string kind)
    {
        var source = Source(reported, acquired);
        Assert.Equal(reported, source.CapturedAtMs);
        Assert.Equal(acquired, source.AcquiredAtMs);
        Assert.Equal(expected, source.FreshnessAtMs);
        Assert.Equal(kind, source.FreshnessClockKind);
    }

    /// <summary>A future reported timestamp grants no extra held-key lifetime beyond original first acquisition.</summary>
    [Fact]
    public void FrozenFallbackReleasesHeldInputAtOriginalAcquisitionDeadline()
    {
        var input = new RecordingInput();
        var controller = new AgentActionController(input, true);
        controller.RegisterFrame(Frame(1, 100, 100, 70), 101);
        var frozen = Frame(2, 130, 130, 100);
        Assert.True(controller.RegisterFrame(frozen, 131).Ready);
        Assert.Null(controller.Submit(Request(2, 130, 500) with
        {
            Steps = [new() { DurationMs = 100, Keys = ["W"] }, new() { DurationMs = 100, Keys = ["W"] }]
        }, 140));
        controller.Tick(140);
        Assert.Equal(new[] { "W" }, input.Held);
        Assert.True(controller.RegisterFrame(frozen with { FrameId = 3, CapturedAtMs = 220 }, 221).Ready);
        Assert.True(controller.GetWorldReadiness(250).Ready);
        controller.Tick(251);
        Assert.Empty(input.Held);
        Assert.Equal("world_observation_stale", Assert.Single(controller.DrainReceipts()).Reason);
    }

    /// <summary>The same native identity cannot be re-stamped into either another fallback or the reported clock.</summary>
    [Theory]
    [InlineData(110)]
    [InlineData(140)]
    public void DuplicateIdentityRejectsChangedAcquisition(double acquiredAgain)
    {
        var gate = new AgentWorldReadinessGate();
        var first = Frame(1, 100, 130, 100);
        Assert.False(gate.Observe(first, 101).Ready);
        Assert.False(gate.Observe(first with { FrameId = 2, CapturedAtMs = 130 }, 131).Ready);
        var changed = first with { FrameId = 3, CapturedAtMs = 150,
            SourceFrame = first.SourceFrame! with { AcquiredAtMs = acquiredAgain } };
        Assert.Equal("source_timing_regressed", gate.Observe(changed, 151).Reason);
        Assert.False(gate.Observe(Frame(4, 160, 160, 130), 161).Ready);
        Assert.True(gate.Observe(Frame(5, 190, 190, 160), 191).Ready);
    }

    /// <summary>Scheduling lead changes do not create artificial interruptions when both native clocks advance.</summary>
    [Fact]
    public void ReportedAndAcquisitionClockModesCanTransitionWithFreshDistinctFrames()
    {
        var gate = new AgentWorldReadinessGate();
        Assert.False(gate.Observe(Frame(1, 100, 130, 100), 101).Ready);
        var reported = gate.Observe(Frame(2, 160, 150, 160), 161);
        Assert.True(reported.Ready);
        Assert.Equal("reported_compositor_qpc", reported.SourceFrame!.FreshnessClockKind);
        var fallback = gate.Observe(Frame(3, 170, 190, 170), 171);
        Assert.True(fallback.Ready);
        Assert.Equal("first_acquisition_qpc", fallback.SourceFrame!.FreshnessClockKind);
        Assert.Equal(reported.Epoch, fallback.Epoch);
    }

    /// <summary>Pre-release acquisitions cannot resume authority merely because their reported compositor time is later.</summary>
    [Fact]
    public void ReleaseBarrierRejectsFutureStampedOldAcquisitionAndAllowsDelayedRecovery()
    {
        var gate = new AgentWorldReadinessGate();
        gate.Observe(Frame(1, 90, 100, 70), 91);
        Assert.True(gate.Observe(Frame(2, 120, 130, 100), 121).Ready);
        var released = gate.Invalidate(130, "client_release", true);
        Assert.Equal("world_observation_invalidated", gate.Observe(Frame(3, 160, 150, 120), 161).Reason);
        Assert.False(gate.Observe(Frame(4, 200, 170, 140), 201).Ready);
        var resumed = gate.Observe(Frame(5, 230, 200, 170), 231);
        Assert.True(resumed.Ready);
        Assert.Equal(released.Epoch, resumed.Epoch);
    }

    /// <summary>A visual block cuts off only its effective source, allowing delayed newer captures to confirm again.</summary>
    [Fact]
    public void VisualBlockUsesAcquisitionAnchorInsteadOfFutureReportedTime()
    {
        var gate = new AgentWorldReadinessGate();
        gate.Observe(Frame(1, 90, 100, 70), 91);
        gate.Observe(Frame(2, 120, 130, 100), 121);
        var blocked = gate.Observe(Frame(3, 150, 180, 140) with { WorldEvidence = AgentWorldEvidence.BlockingUi }, 151);
        Assert.Equal("world_overlay_detected", blocked.Reason);
        Assert.False(gate.Observe(Frame(4, 180, 190, 150), 181).Ready);
        Assert.True(gate.Observe(Frame(5, 210, 200, 170), 211).Ready);
    }

    /// <summary>Acquisition metadata remains finite, chronological and no later than observation completion.</summary>
    [Theory]
    [InlineData(double.NaN, "invalid_source_timing")]
    [InlineData(double.PositiveInfinity, "invalid_source_timing")]
    [InlineData(200, "invalid_source_timing")]
    [InlineData(50, "source_timing_regressed")]
    public void InvalidAcquisitionStillFailsClosed(double acquired, string reason)
    {
        var gate = new AgentWorldReadinessGate();
        gate.Observe(Frame(1, 90, 100, 70), 91);
        gate.Observe(Frame(2, 120, 130, 100), 121);
        Assert.Equal(reason, gate.Observe(Frame(3, 150, 160, acquired), 151).Reason);
        Assert.False(gate.Observe(Frame(4, 180, 190, 160), 181).Ready);
        Assert.True(gate.Observe(Frame(5, 210, 220, 190), 211).Ready);
    }

    /// <summary>Fallback proposals use original acquisition for both the age ceiling and maximum action deadline.</summary>
    [Fact]
    public void ProposalAgeAndDeadlineCannotUseTheFutureRawStamp()
    {
        var controller = new AgentActionController(new RecordingInput(), true);
        for (var index = 0; index <= 7; index++)
            controller.RegisterFrame(Frame(index + 1, index * 80 + 30, index * 80 + 30, index * 80), index * 80 + 31);
        Assert.Equal("stale_frame", controller.Submit(Request(2, 110, 800), 600));
        Assert.Equal("invalid_deadline", controller.Submit(Request(8, 590, 1320), 600));
        Assert.Null(controller.Submit(Request(8, 590, 1310), 600));
    }

    /// <summary>Replay protection uses the fallback lease ceiling and neither expires early nor survives indefinitely.</summary>
    [Fact]
    public void ReplayRetentionUsesOriginalAcquisitionCeiling()
    {
        var controller = new AgentActionController(new RecordingInput(), true);
        controller.RegisterFrame(Frame(1, 40, 40, 10), 41);
        controller.RegisterFrame(Frame(2, 70, 70, 40), 71);
        var first = Request(2, 70, 150);
        Assert.Null(controller.Submit(first, 72));
        for (var index = 3; index <= 10; index++)
        {
            var acquired = 40 + (index - 2) * 90;
            controller.RegisterFrame(Frame(index, acquired + 20, acquired + 30, acquired), acquired + 21);
        }
        var fresh = Request(10, 780, 900) with { RequestId = first.RequestId };
        Assert.Equal("replayed_request", controller.Submit(fresh, 789));
        Assert.Null(controller.Submit(fresh, 790));
    }

    /// <summary>Preserve an independent absolute identity and the two unmodified mapped clock values.</summary>
    private static AgentSourceFrame Source(double reported, double acquired) =>
        new(Epoch, 1000000000 + (long)(reported * 10000), reported, acquired);

    /// <summary>Use real-world HUD evidence while keeping host poll and native acquisition independent.</summary>
    private static AgentObservation Frame(long id, double host, double reported, double acquired) =>
        new(id, host, 1920, 1080, AgentWorldEvidence.WorldHud, 1, Source(reported, acquired));

    /// <summary>Keep observedAtMs tied to the existing host publication identity.</summary>
    private static AgentRequest Request(long frame, double host, double expires) => new()
    {
        RequestId = Guid.NewGuid().ToString("N"), ModelId = "acquisition-fixture", FrameId = frame,
        ObservedAtMs = host, ExpiresAtMs = expires, Steps = [new() { DurationMs = 50, Keys = ["W"] }]
    };

    /// <summary>Record input intent in memory without invoking any Windows input API.</summary>
    private sealed class RecordingInput : IAgentInput
    {
        /// <inheritdoc />
        public bool IsAvailable => true;
        /// <summary>Current held-state fixture.</summary>
        public string[] Held { get; private set; } = [];
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) => Held = keys.ToArray();
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) { }
        /// <inheritdoc />
        public void ReleaseAll() => Held = [];
    }
}
