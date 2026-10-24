using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Capture;
using Newtonsoft.Json;
using System.Diagnostics;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Pure managed host-evidence identity, age and controller tests without capture or Windows input.</summary>
public sealed class AgentHostSnapshotTests
{
    /// <summary>Fixed positive origin mapped with the actual process clock scale.</summary>
    internal static readonly long Origin = Stopwatch.Frequency * 100;
    /// <summary>One fixed capture generation used by each independent fixture.</summary>
    internal const string Epoch = "1234567890abcdef1234567890abcdef";
    /// <summary>Convert small fixture intervals into exact original QPC units.</summary>
    internal static long Ticks(double milliseconds) => Origin + checked((long)(milliseconds * Stopwatch.Frequency / 1000));
    /// <summary>Construct complete host evidence with an explicit authority choice.</summary>
    internal static AgentHostSnapshot Host(long id, double start, double end,
        string policy = DesktopCapturePolicy.HostAcquisitionV1) =>
        new(Epoch, id, Ticks(start), Ticks(end), Stopwatch.Frequency, Origin, policy);
    /// <summary>Capture request time remains a separate earlier compatibility timestamp.</summary>
    internal static AgentObservation Frame(long id, double start, double end) =>
        new(id, start - 1, 1920, 1080, AgentWorldEvidence.WorldHud, 1) { HostSnapshot = Host(id, start, end) };

    /// <summary>Two distinct clean snapshots use original start, with the unchanged inclusive150ms boundary.</summary>
    [Theory]
    [InlineData(280, true)]
    [InlineData(281, false)]
    public void WorldAgeUsesStartAfterRecognition(double checkedAt, bool expected)
    {
        var gate = new AgentWorldReadinessGate(DesktopCapturePolicy.HostAcquisitionV1);
        Assert.False(gate.Observe(Frame(1, 100, 110), 111).Ready);
        var second = gate.Observe(Frame(2, 130, 140), checkedAt);
        Assert.Equal(expected, second.Ready);
        Assert.Null(second.SourceFrame);
        Assert.Equal(130, second.HostSnapshot!.StartedAtMs);
        if (!expected) Assert.Equal("world_observation_stale", second.Reason);
    }

    /// <summary>Each malformed raw clock/identity/policy field fails instead of becoming receipt-time freshness.</summary>
    [Theory]
    [InlineData(0)] [InlineData(1)] [InlineData(2)] [InlineData(3)] [InlineData(4)]
    [InlineData(5)] [InlineData(6)] [InlineData(7)] [InlineData(8)] [InlineData(9)]
    public void InvalidHostEvidenceNeverEntersFallback(int mutation)
    {
        var frame = Frame(1, 100, 110);
        var host = frame.HostSnapshot!;
        host = mutation switch
        {
            0 => host with { CaptureEpoch = Guid.Empty.ToString("N") },
            1 => host with { SnapshotId = 0 },
            2 => host with { ClockFrequency = 0 },
            3 => host with { ClockFrequency = Stopwatch.Frequency + 1 },
            4 => host with { StartedAtStopwatchTicks = Origin - 1 },
            5 => host with { CompletedAtStopwatchTicks = host.StartedAtStopwatchTicks - 1 },
            6 => host with { CompletedAtStopwatchTicks = Ticks(201) },
            7 => host with { SessionOriginAtStopwatchTicks = 0 },
            8 => host with { DesktopDcSourcePolicy = "unknown" },
            _ => host with { DesktopDcSourcePolicy = DesktopCapturePolicy.ObserveOnly }
        };
        var gate = new AgentWorldReadinessGate(DesktopCapturePolicy.HostAcquisitionV1);
        var result = gate.Observe(frame with { HostSnapshot = host }, 200);
        Assert.False(result.Ready);
        Assert.Equal("invalid_host_snapshot", result.Reason);
    }

    /// <summary>Desktop cannot fall back on null evidence, mix WGC and host, or enter an unconfigured gate.</summary>
    [Theory]
    [InlineData(0)] [InlineData(1)] [InlineData(2)]
    public void MissingMixedAndUnexpectedKindsAreRejected(int kind)
    {
        var gate = new AgentWorldReadinessGate(kind == 2 ? null : DesktopCapturePolicy.HostAcquisitionV1);
        var frame = Frame(1, 100, 110);
        frame = kind switch
        {
            0 => frame with { HostSnapshot = null },
            1 => frame with { SourceFrame = new AgentSourceFrame(Epoch, 100, 100, 100) },
            _ => frame
        };
        Assert.Equal("invalid_host_snapshot", gate.Observe(frame, 111).Reason);
    }

    /// <summary>Repeated identity cannot add confirmation or renew its original expiry.</summary>
    [Fact]
    public void RepeatedSnapshotDoesNotRenewAuthority()
    {
        var gate = new AgentWorldReadinessGate(DesktopCapturePolicy.HostAcquisitionV1);
        var first = Frame(1, 100, 110);
        Assert.False(gate.Observe(first, 111).Ready);
        Assert.False(gate.Observe(first with { FrameId = 2, CapturedAtMs = 120 }, 121).Ready);
        var next = Frame(3, 140, 150) with { HostSnapshot = Host(2, 140, 150) };
        Assert.True(gate.Observe(next, 151).Ready);
        Assert.True(gate.Observe(next with { FrameId = 4, CapturedAtMs = 200 }, 201).Ready);
        Assert.False(gate.Get(291).Ready);
    }

    /// <summary>Snapshot IDs and serial intervals cannot regress, change clocks or silently replace the generation.</summary>
    [Theory]
    [InlineData(0)] [InlineData(1)] [InlineData(2)] [InlineData(3)] [InlineData(4)]
    public void OriginalIdentityAndSerialIntervalRemainPinned(int mutation)
    {
        var gate = new AgentWorldReadinessGate(DesktopCapturePolicy.HostAcquisitionV1);
        gate.Observe(Frame(1, 100, 120), 121);
        var next = Host(2, 130, 140);
        next = mutation switch
        {
            0 => next with { CaptureEpoch = Guid.NewGuid().ToString("N") },
            1 => next with { SnapshotId = 1 },
            2 => next with { StartedAtStopwatchTicks = Ticks(110) },
            3 => next with { StartedAtStopwatchTicks = Ticks(100) },
            _ => next with { SessionOriginAtStopwatchTicks = Origin + 1 }
        };
        var rejected = gate.Observe(Frame(2, 130, 140) with { HostSnapshot = next }, 141);
        Assert.False(rejected.Ready);
        Assert.Equal(mutation == 0 ? "host_snapshot_epoch_changed" : "host_snapshot_timing_regressed", rejected.Reason);
    }

    /// <summary>A completed interval cannot rescue a start before the existing release barrier.</summary>
    [Fact]
    public void ReleaseBarrierUsesStartAndRequiresFreshConfirmations()
    {
        var gate = new AgentWorldReadinessGate(DesktopCapturePolicy.HostAcquisitionV1);
        gate.Observe(Frame(1, 100, 110), 111);
        Assert.True(gate.Observe(Frame(2, 130, 135), 136).Ready);
        gate.Invalidate(140, "client_release");
        Assert.Equal("world_observation_invalidated", gate.Observe(Frame(3, 139, 150), 151).Reason);
        Assert.False(gate.Observe(Frame(4, 151, 160), 161).Ready);
        Assert.True(gate.Observe(Frame(5, 181, 190), 191).Ready);
    }

    /// <summary>Observation-only evidence never grants controller authority even with a permissive fake input.</summary>
    [Fact]
    public void ObserveOnlyCannotBeEnabledByControllerOrPixels()
    {
        var input = new RecordingInput();
        var controller = new AgentActionController(input, true, desktopDcSourcePolicy: DesktopCapturePolicy.ObserveOnly);
        var frame = Frame(1, 100, 110) with { HostSnapshot = Host(1, 100, 110, DesktopCapturePolicy.ObserveOnly) };
        Assert.Equal("capture_policy_observe_only", controller.RegisterFrame(frame, 111).Reason);
        Assert.Equal("capture_policy_observe_only", controller.Submit(Request("denied", 1, 99), 112));
        controller.Tick(112);
        Assert.Equal(0, input.Dispatches);
    }

    /// <summary>The old500ms first-action ceiling uses host start while fresh later observations keep the world gate alive.</summary>
    [Theory]
    [InlineData(600, null)]
    [InlineData(601, "stale_frame")]
    public void ActionStartLimitIsUnchangedAndSeparateFromCurrentWorldAge(double now, string? error)
    {
        var controller = new AgentActionController(new RecordingInput(), true,
            desktopDcSourcePolicy: DesktopCapturePolicy.HostAcquisitionV1);
        controller.RegisterFrame(Frame(1, 60, 65), 66);
        controller.RegisterFrame(Frame(2, 100, 105), 106);
        for (var i = 3; i <= 7; i++)
        {
            var start = (i - 1) * 100;
            controller.RegisterFrame(Frame(i, start, start), start);
        }
        Assert.Equal(error, controller.Submit(Request("age", 2, 99), now));
    }

    /// <summary>An exclusive first-input deadline cannot be based on the later completion endpoint.</summary>
    [Fact]
    public void StartBeforeCeilingUsesOriginalHostStart()
    {
        var controller = new AgentActionController(new RecordingInput(), true,
            desktopDcSourcePolicy: DesktopCapturePolicy.HostAcquisitionV1);
        controller.RegisterFrame(Frame(1, 60, 65), 66);
        controller.RegisterFrame(Frame(2, 100, 120), 121);
        var request = Request("deadline", 2, 99) with { StartBeforeMs = 601 };
        Assert.Equal("invalid_start_deadline", controller.Submit(request, 125));
    }

    /// <summary>Existing record constructor and null JSON shape remain exactly compatible.</summary>
    [Fact]
    public void ExistingObservationAndReadinessJsonOmitHostExtension()
    {
        var source = new AgentSourceFrame(Epoch, 123, 10, 20);
        var frame = new AgentObservation(1, 30, 1920, 1080, AgentWorldEvidence.WorldHud, 2, source);
        var prior = new { frame.FrameId, frame.CapturedAtMs, frame.SourceWidth, frame.SourceHeight,
            frame.WorldEvidence, frame.RecognitionMs, frame.SourceFrame };
        Assert.Equal(JsonConvert.SerializeObject(prior), JsonConvert.SerializeObject(frame));
        var readiness = new AgentWorldReadiness(true, "world_ready", 1, 30, 32, 2, 0, source);
        Assert.DoesNotContain("HostSnapshot", JsonConvert.SerializeObject(readiness));
    }

    /// <summary>A bounded proposal for an older retained frame.</summary>
    private static AgentRequest Request(string id, long frame, double captured) => new()
    {
        RequestId = id, ModelId = "host-fixture", FrameId = frame, ObservedAtMs = captured,
        ExpiresAtMs = 750, Steps = [new() { DurationMs = 50, Keys = ["W"] }]
    };

    /// <summary>Only counts in-memory dispatches; never calls an input backend.</summary>
    private sealed class RecordingInput : IAgentInput
    {
        /// <summary>Count of key/mouse intents, independent of releases.</summary>
        internal int Dispatches;
        /// <inheritdoc />
        public bool IsAvailable => true;
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) => Dispatches++;
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) => Dispatches++;
        /// <inheritdoc />
        public void ReleaseAll() { }
    }
}
