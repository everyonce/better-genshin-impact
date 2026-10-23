using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using Fischless.GameCapture;
using Fischless.GameCapture.Graphics;
using OpenCvSharp;
using System.Reflection;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Validate real source age and recovery using deterministic clocks and an input-only recording sink.</summary>
public sealed class AgentSourceFreshnessTests
{
    /// <summary>One stable native capture generation for ordinary fixtures.</summary>
    private const string Epoch = "11111111111111111111111111111111";

    /// <summary>WGC timestamps use 100ns units even when raw QPC uses a different frequency.</summary>
    [Theory]
    [InlineData(10000000)]
    [InlineData(3579545)]
    [InlineData(1000000000)]
    public void MapsSourceAndAcquisitionWithDistinctTickUnits(long frequency)
    {
        var origin = 3600 * frequency;
        var timing = new GameCaptureSourceInfo(Guid.ParseExact(Epoch, "N"),
            3600 * TimeSpan.TicksPerSecond + 1234567, origin + frequency);
        var mapped = AgentStreamSession.MapSourceFrame(timing, origin, frequency);
        Assert.Equal(Epoch, mapped.CaptureEpoch);
        Assert.Equal(timing.SourceTimestamp100ns, mapped.Timestamp100ns);
        Assert.Equal(123.4567, mapped.CapturedAtMs, 7);
        Assert.Equal(1000, mapped.AcquiredAtMs, 7);
    }

    /// <summary>Long uptimes cannot overflow intermediate clock arithmetic or silently clamp old frames to fresh.</summary>
    [Fact]
    public void MapsLargeClockOriginsAndPreservesPreSessionSourceTime()
    {
        const long origin = long.MaxValue / 10;
        var timing = new GameCaptureSourceInfo(Guid.ParseExact(Epoch, "N"),
            origin + 300 * TimeSpan.TicksPerMillisecond, origin + 500 * TimeSpan.TicksPerMillisecond);
        Assert.Equal(300, AgentStreamSession.MapSourceFrame(timing, origin, TimeSpan.TicksPerSecond).CapturedAtMs);
        var before = timing with { SourceTimestamp100ns = origin - 30 * TimeSpan.TicksPerMillisecond };
        Assert.Equal(-30, AgentStreamSession.MapSourceFrame(before, origin, TimeSpan.TicksPerSecond).CapturedAtMs);
        Assert.Throws<ArgumentOutOfRangeException>(() => AgentStreamSession.MapSourceFrame(timing, origin, 0));
    }

    /// <summary>A fresh pre-session compositor frame is valid evidence, followed by a distinct post-start frame.</summary>
    [Fact]
    public void FreshPreSessionSourceCanConfirmWithANewPostStartSource()
    {
        var gate = new AgentWorldReadinessGate();
        var frame = Frame(1, 10, -30);
        frame = frame with { SourceFrame = frame.SourceFrame! with { AcquiredAtMs = -20 } };
        var first = gate.Observe(frame, 11);
        Assert.False(first.Ready);
        Assert.Equal("world_confirming", first.Reason);
        Assert.Equal(-30, first.SourceFrame!.CapturedAtMs);
        Assert.True(gate.Observe(Frame(2, 30, 10), 31).Ready);
    }

    /// <summary>Negative source times remain subject to the same age limit and explicit release cutoff.</summary>
    [Fact]
    public void PreSessionSourcesStillExpireAndRespectInterruptionCutoffs()
    {
        var expired = new AgentWorldReadinessGate();
        Assert.Equal("world_observation_stale", expired.Observe(Frame(1, 10, -160), 11).Reason);
        var interrupted = new AgentWorldReadinessGate();
        interrupted.Invalidate(0, "client_release", true);
        Assert.Equal("world_observation_invalidated", interrupted.Observe(Frame(1, 10, -30), 11).Reason);
        Assert.False(interrupted.Observe(Frame(2, 30, 10), 31).Ready);
        Assert.True(interrupted.Observe(Frame(3, 60, 40), 61).Ready);
    }

    /// <summary>A cached image neither supplies a second confirmation nor extends the original source lifetime.</summary>
    [Fact]
    public void RepeatedSourceCannotConfirmOrRenewReadiness()
    {
        var gate = new AgentWorldReadinessGate();
        Assert.False(gate.Observe(Frame(1, 100, 90), 101).Ready);
        Assert.False(gate.Observe(Frame(2, 130, 90), 131).Ready);
        Assert.True(gate.Observe(Frame(3, 150, 140), 151).Ready);
        var cached = gate.Observe(Frame(4, 200, 140), 201);
        Assert.True(cached.Ready);
        Assert.Equal(200, cached.SourceCapturedAtMs); // Wire compatibility retains host poll time.
        Assert.Equal(140, cached.SourceFrame!.CapturedAtMs);
        Assert.True(gate.Get(290).Ready);
        Assert.False(gate.Get(291).Ready);
        Assert.Equal("world_observation_stale", gate.Get(292).Reason);
        Assert.Equal(1, gate.Get(500).Epoch);
    }

    /// <summary>The input watchdog releases held keys when cached-source age expires, before the action deadline.</summary>
    [Fact]
    public void FreshHostPollingDoesNotKeepFrozenSourceInputHeld()
    {
        var input = new RecordingInput();
        var controller = new AgentActionController(input, true);
        controller.RegisterFrame(Frame(1, 100, 70), 101);
        controller.RegisterFrame(Frame(2, 130, 100), 131);
        Assert.Null(controller.Submit(Request(2, 130, 500) with
        {
            Steps = [new() { DurationMs = 100, Keys = ["W"] }, new() { DurationMs = 100, Keys = ["W"] }]
        }, 140));
        controller.Tick(140);
        Assert.Equal(new[] { "W" }, input.Held);
        Assert.True(controller.RegisterFrame(Frame(3, 220, 100), 221).Ready);
        controller.Tick(251);
        Assert.Empty(input.Held);
        Assert.Contains(controller.DrainReceipts(), receipt => receipt.Reason == "world_observation_stale");
    }

    /// <summary>Rejected delayed frames do not chase the interruption cutoff forward forever.</summary>
    [Fact]
    public void ExplicitReleaseRecoversWithConsistentlyDelayedNewSourceFrames()
    {
        var gate = new AgentWorldReadinessGate();
        gate.Observe(Frame(1, 90, 30), 91);
        Assert.True(gate.Observe(Frame(2, 120, 60), 121).Ready);
        var released = gate.Invalidate(130, "client_release", true);
        Assert.Equal("world_observation_invalidated", gate.Observe(Frame(3, 160, 100), 161).Reason);
        Assert.False(gate.Observe(Frame(4, 200, 140), 201).Ready);
        var recovered = gate.Observe(Frame(5, 230, 170), 231);
        Assert.True(recovered.Ready);
        Assert.Equal(released.Epoch, recovered.Epoch);
    }

    /// <summary>A visually blocked source invalidates older images without discarding newer delayed world evidence.</summary>
    [Fact]
    public void VisualBlockUsesItsSourceTimeAndResumesAfterTwoNewSources()
    {
        var gate = new AgentWorldReadinessGate();
        gate.Observe(Frame(1, 90, 30), 91);
        gate.Observe(Frame(2, 120, 60), 121);
        var blocked = gate.Observe(Frame(3, 150, 90) with { WorldEvidence = AgentWorldEvidence.BlockingUi }, 151);
        Assert.False(blocked.Ready);
        Assert.Equal("world_overlay_detected", blocked.Reason);
        Assert.False(gate.Observe(Frame(4, 180, 120), 181).Ready);
        Assert.True(gate.Observe(Frame(5, 210, 150), 211).Ready);
    }

    /// <summary>Restarting a capture backend revokes previous readiness even if both generations contain a HUD.</summary>
    [Fact]
    public void CaptureGenerationChangeRequiresNewConfirmations()
    {
        var gate = new AgentWorldReadinessGate();
        gate.Observe(Frame(1, 50, 10), 51);
        var before = gate.Observe(Frame(2, 80, 40), 81);
        var nextEpoch = Guid.NewGuid().ToString("N");
        var first = gate.Observe(Frame(3, 110, 70, nextEpoch), 111);
        Assert.False(first.Ready);
        Assert.Equal(before.Epoch + 1, first.Epoch);
        var second = gate.Observe(Frame(4, 140, 100, nextEpoch), 141);
        Assert.True(second.Ready);
        Assert.Equal(first.Epoch, second.Epoch);
    }

    /// <summary>Bad timing closes authority but does not poison the last valid native identity or recovery.</summary>
    [Theory]
    [InlineData("future", "invalid_source_timing")]
    [InlineData("nan", "invalid_source_timing")]
    [InlineData("epoch", "invalid_source_timing")]
    [InlineData("timestamp", "invalid_source_timing")]
    [InlineData("acquisition", "invalid_source_timing")]
    [InlineData("regressed", "source_timing_regressed")]
    [InlineData("missing", "source_timing_missing")]
    public void InvalidNativeTimingFailsClosedAndAllowsFreshRecovery(string kind, string reason)
    {
        var gate = new AgentWorldReadinessGate();
        gate.Observe(Frame(1, 50, 30), 51);
        gate.Observe(Frame(2, 80, 60), 81);
        var bad = Frame(3, 100, 90);
        bad = bad with { SourceFrame = kind switch
        {
            "future" => bad.SourceFrame! with { CapturedAtMs = 110 },
            "nan" => bad.SourceFrame! with { CapturedAtMs = double.NaN },
            "epoch" => bad.SourceFrame! with { CaptureEpoch = "invalid" },
            "timestamp" => bad.SourceFrame! with { Timestamp100ns = 0 },
            "acquisition" => bad.SourceFrame! with { AcquiredAtMs = 110 },
            "regressed" => Frame(3, 100, 40).SourceFrame,
            _ => null
        } };
        var blocked = gate.Observe(bad, 101);
        Assert.False(blocked.Ready);
        Assert.Equal(reason, blocked.Reason);
        Assert.False(gate.Observe(Frame(4, 140, 120), 141).Ready);
        Assert.True(gate.Observe(Frame(5, 170, 150), 171).Ready);
    }

    /// <summary>Backends without source metadata retain the explicit host-request fallback from protocol version one.</summary>
    [Fact]
    public void UnknownSourceKeepsHostTimingFallback()
    {
        var gate = new AgentWorldReadinessGate();
        gate.Observe(new(1, 10, 1920, 1080, AgentWorldEvidence.WorldHud), 11);
        var ready = gate.Observe(new(2, 40, 1920, 1080, AgentWorldEvidence.WorldHud), 41);
        Assert.True(ready.Ready);
        Assert.Null(ready.SourceFrame);
        Assert.True(gate.Get(190).Ready);
        Assert.False(gate.Get(191).Ready);
    }

    /// <summary>A fresh current gate cannot make a retained, over-age source proposal acceptable.</summary>
    [Fact]
    public void ProposalAgeUsesSourceWhileObservedAtStillUsesHostIdentity()
    {
        var controller = new AgentActionController(new RecordingInput(), true);
        for (var index = 0; index <= 7; index++)
            controller.RegisterFrame(Frame(index + 1, index * 80 + 30, index * 80), index * 80 + 31);
        // The retained host observation is 490ms old; its actual source is 520ms old.
        Assert.Equal("stale_frame", controller.Submit(Request(2, 110, 700), 600));
        Assert.Equal("observation_timestamp_mismatch", controller.Submit(Request(8, 560, 700), 600));
        Assert.Null(controller.Submit(Request(8, 590, 700), 600));
    }

    /// <summary>The source-based deadline ceiling cannot be extended by an expensive later copy or recognition.</summary>
    [Fact]
    public void ProposalDeadlineUsesActualSourceTime()
    {
        var controller = new AgentActionController(new RecordingInput(), true);
        controller.RegisterFrame(Frame(1, 30, 10), 31);
        controller.RegisterFrame(Frame(2, 60, 40), 61);
        Assert.Equal("invalid_deadline", controller.Submit(Request(2, 60, 800), 62));
        Assert.Null(controller.Submit(Request(2, 60, 789), 62));
    }

    /// <summary>Replay IDs remain protected through the source's latest legal deadline and can expire afterward.</summary>
    [Fact]
    public void ReplayRetentionEndsAtTheSourceBasedDeadlineCeiling()
    {
        var controller = new AgentActionController(new RecordingInput(), true);
        controller.RegisterFrame(Frame(1, 30, 10), 31);
        controller.RegisterFrame(Frame(2, 60, 40), 61);
        var first = Request(2, 60, 150);
        Assert.Null(controller.Submit(first, 62));
        for (var index = 3; index <= 10; index++)
        {
            var source = 40 + (index - 2) * 90;
            controller.RegisterFrame(Frame(index, source + 20, source), source + 21);
        }
        var fresh = Request(10, 780, 900) with { RequestId = first.RequestId };
        Assert.Equal("replayed_request", controller.Submit(fresh, 789));
        Assert.Null(controller.Submit(fresh, 790));
    }

    /// <summary>Repeated WGC cache reads preserve source identity and clone pixels without starting capture or a GPU.</summary>
    [Fact]
    public void CachedWgcFramesKeepTheirMetadataAndOwnTheirPixels()
    {
        using var capture = new GraphicsCapture();
        var pixels = new Mat(2, 3, MatType.CV_8UC3, new Scalar(12, 34, 56));
        var source = new GameCaptureSourceInfo(Guid.NewGuid(), 1000000, 1500000);
        typeof(GraphicsCapture).GetField("_latestFrame", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(capture, pixels);
        typeof(GraphicsCapture).GetField("_latestSourceInfo", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(capture, source);
        using var first = capture.Capture();
        using var second = capture.Capture();
        Assert.NotNull(first);
        Assert.NotNull(second);
        Assert.Same(source, first.SourceInfo);
        Assert.Same(source, second.SourceInfo);
        first.Frame.SetTo(Scalar.White);
        Assert.Equal(new Vec3b(12, 34, 56), second.Frame.At<Vec3b>(0, 0));
        capture.Stop();
        Assert.Null(capture.Capture());
        Assert.Equal(new Vec3b(12, 34, 56), second.Frame.At<Vec3b>(0, 0));
    }

    /// <summary>Build consistent source identities on a separate absolute QPC timeline.</summary>
    private static AgentObservation Frame(long id, double host, double source, string epoch = Epoch) =>
        new(id, host, 1920, 1080, AgentWorldEvidence.WorldHud, 1,
            new AgentSourceFrame(epoch, 1000000000 + (long)(source * 10000), source, Math.Min(host, source + 40)));

    /// <summary>Use host timing only for the existing proposal-to-observation identity check.</summary>
    private static AgentRequest Request(long frame, double host, double expires) => new()
    {
        RequestId = Guid.NewGuid().ToString("N"), ModelId = "source-fixture", FrameId = frame,
        ObservedAtMs = host, ExpiresAtMs = expires, Steps = [new() { DurationMs = 50, Keys = ["W"] }]
    };

    /// <summary>Record key ownership without invoking Windows input.</summary>
    private sealed class RecordingInput : IAgentInput
    {
        /// <inheritdoc />
        public bool IsAvailable => true;
        /// <summary>The currently held fixture keys.</summary>
        public string[] Held { get; private set; } = [];
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) => Held = keys.ToArray();
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) { }
        /// <inheritdoc />
        public void ReleaseAll() => Held = [];
    }
}
