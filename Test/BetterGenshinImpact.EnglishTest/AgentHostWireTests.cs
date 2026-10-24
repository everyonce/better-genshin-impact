using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Mask;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using Fischless.GameCapture;
using Fischless.GameCapture.DesktopDc;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Newtonsoft.Json.Serialization;
using OpenCvSharp;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Actual stream metadata/admission helpers with fake targets/input and CPU Mats; no live pipe/capture/input.</summary>
public sealed class AgentHostWireTests
{
    /// <summary>Map only the exact library interval and retain the session origin rather than synthesizing WGC clocks.</summary>
    [Fact]
    public void MappingRetainsRawClocksAndPolicy()
    {
        var host = AgentHostSnapshotTests.Host(1, 100, 120);
        using var frame = Frame(host);
        var mapped = AgentStreamSession.MapHostEvidence(frame, true, DesktopCapturePolicy.HostAcquisitionV1,
            AgentHostSnapshotTests.Origin, Stopwatch.Frequency, 121);
        Assert.Equal(host, mapped);
        Assert.Null(frame.SourceInfo);
        Assert.Equal(100, mapped!.StartedAtMs);
        Assert.Equal(120, mapped.CompletedAtMs);
    }

    /// <summary>Missing/foreign/invalid host metadata is rejected before recognition can publish it.</summary>
    [Theory]
    [InlineData(0)] [InlineData(1)] [InlineData(2)] [InlineData(3)] [InlineData(4)] [InlineData(5)]
    public void MappingRejectsUnsupportedEvidence(int kind)
    {
        var host = AgentHostSnapshotTests.Host(1, 100, 120);
        using var frame = kind switch
        {
            0 => new GameCaptureFrame(new Mat()),
            1 => new GameCaptureFrame(new Mat(), null, new GameCaptureSourceInfo(Guid.NewGuid(), 100, 100)),
            3 => Frame(host with { ClockFrequency = Stopwatch.Frequency + 1 }),
            _ => Frame(host)
        };
        Assert.ThrowsAny<Exception>(() => AgentStreamSession.MapHostEvidence(frame, kind != 2,
            kind == 4 ? null : DesktopCapturePolicy.HostAcquisitionV1,
            AgentHostSnapshotTests.Origin, Stopwatch.Frequency, kind == 5 ? 119 : 121));
    }

    /// <summary>Null native source remains compatible only outside the desktop backend.</summary>
    [Fact]
    public void LegacyUnknownBackendKeepsItsPriorFallback()
    {
        using var frame = new GameCaptureFrame(new Mat());
        Assert.Null(AgentStreamSession.MapHostEvidence(frame, false, null, AgentHostSnapshotTests.Origin, Stopwatch.Frequency, 121));
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1));
        var session = new AgentStreamSession(runtime);
        var header = new { type = "frame", sourceTimestampKind = "unknown", sourceFrame = (object?)null };
        Assert.Same(header, session.WithDesktopEvidence(header));
    }

    /// <summary>Only additive desktop fields appear; WGC source clocks stay explicitly unknown.</summary>
    [Fact]
    public void FrameWireSeparatesHostAndSourceEvidence()
    {
        using var runtime = Runtime(DesktopCapturePolicy.HostAcquisitionV1, false);
        var session = new AgentStreamSession(runtime);
        var host = AgentHostSnapshotTests.Host(1, 100, 120);
        var header = new { type = "frame", sourceFrame = (object?)null, sourceTimestampKind = "unknown",
            sourceFrameAgeMs = (double?)null, reportedSourceFrameAgeMs = (double?)null };
        var value = Assert.IsType<JObject>(session.WithDesktopEvidence(header, host, 130));
        Assert.Equal(1, value["hostSnapshotVersion"]!.Value<int>());
        Assert.Equal("host-acquisition-v1", value["sourceKind"]!.Value<string>());
        Assert.Equal("unknown", value["sourceTimestampKind"]!.Value<string>());
        Assert.Equal(JTokenType.Null, value["sourceFrame"]!.Type);
        Assert.Equal(JTokenType.Null, value["sourceFrameAgeMs"]!.Type);
        Assert.Equal(30, value["hostAcquisitionAgeMs"]!.Value<double>());
        Assert.Equal(20, value["hostAcquisitionIntervalMs"]!.Value<double>());
        Assert.Equal(host.StartedAtStopwatchTicks, value["hostSnapshot"]!["startedAtStopwatchTicks"]!.Value<long>());
        Assert.Equal(host.SessionOriginAtStopwatchTicks, value["hostSnapshot"]!["sessionOriginAtStopwatchTicks"]!.Value<long>());
        Assert.True(System.Text.Encoding.UTF8.GetByteCount(value.ToString(Formatting.None)) < 4096);
    }

    /// <summary>The final publication helper rejects absent/mismatched/future host evidence, without altering pixels.</summary>
    [Theory]
    [InlineData(0)] [InlineData(1)] [InlineData(2)]
    public void FramePublicationRequiresExactHostEvidence(int kind)
    {
        using var runtime = Runtime(DesktopCapturePolicy.HostAcquisitionV1, false);
        var session = new AgentStreamSession(runtime);
        var host = AgentHostSnapshotTests.Host(1, 100, 120);
        if (kind == 1) host = host with { DesktopDcSourcePolicy = DesktopCapturePolicy.ObserveOnly };
        Assert.Throws<InvalidOperationException>(() => session.WithDesktopEvidence(new { type = "frame" },
            kind == 0 ? null : host, kind == 2 ? 119 : 121));
    }

    /// <summary>Hello declares the exact host basis and forbidden fallback for both selected policies.</summary>
    [Theory]
    [InlineData(DesktopCapturePolicy.ObserveOnly)]
    [InlineData(DesktopCapturePolicy.HostAcquisitionV1)]
    public void HelloDeclaresHostAcquisitionWithoutRenderFreshness(string policy)
    {
        using var runtime = Runtime(policy, false);
        var session = new AgentStreamSession(runtime);
        var method = typeof(AgentStreamSession).GetMethod("CreateHello", BindingFlags.Instance | BindingFlags.NonPublic)!;
        var value = JObject.FromObject(method.Invoke(session, [false])!);
        Assert.Equal(policy, value["desktopDcSourcePolicy"]!.Value<string>());
        Assert.Equal("rejected", value["sourceFrameTiming"]!["unknownFallback"]!.Value<string>());
        Assert.Equal("unknown", value["sourceFrameTiming"]!["knownTimestampKind"]!.Value<string>());
        Assert.Equal("unknown", value["worldReadiness"]!["sourceTimestampKind"]!.Value<string>());
        Assert.Equal("host-acquisition-v1", value["worldReadiness"]!["sourceKind"]!.Value<string>());
        Assert.False(value["sourceFrameTiming"]!["measuresGameRenderAge"]!.Value<bool>());
        Assert.Equal(150, value["sourceFrameTiming"]!["maxAgeMs"]!.Value<double>());
        Assert.Equal(500, value["maxActionStartAgeMs"]!.Value<double>());
        Assert.False(value["inputEnabled"]!.Value<bool>());
    }

    /// <summary>Observe-only rejects enabling and dispatch before any input channel/native operation is reached.</summary>
    [Fact]
    public void ObserveOnlyDeniesStreamEnableAndRuntimeDispatch()
    {
        using var runtime = Runtime(DesktopCapturePolicy.ObserveOnly, false);
        var session = new AgentStreamSession(runtime);
        session.ValidateInputPolicy(false);
        Assert.Equal("capture_policy_observe_only", Assert.Throws<InvalidOperationException>(() => session.ValidateInputPolicy(true)).Message);
        var input = new RuntimeAgentInput(runtime);
        Assert.False(input.IsAvailable);
        Assert.Equal("capture_policy_observe_only", Assert.Throws<InvalidOperationException>(() => input.SetHeldKeys(["W"])).Message);
        Assert.Equal("capture_policy_observe_only", Assert.Throws<InvalidOperationException>(() => input.MoveMouse(1, 1)).Message);
    }

    /// <summary>A selected host policy cannot bypass a stopped or nonforeground runtime at dispatch.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void HostPolicyStillRequiresCurrentTarget(bool focusLoss)
    {
        using var runtime = Runtime(DesktopCapturePolicy.HostAcquisitionV1, focusLoss);
        if (focusLoss) ((Window)runtime.Window).Foreground = false;
        var input = new RuntimeAgentInput(runtime);
        Assert.False(input.IsAvailable);
        Assert.Equal("desktop_capture_target_unavailable", Assert.Throws<InvalidOperationException>(() => input.SetHeldKeys(["W"])).Message);
        Assert.Equal("desktop_capture_target_unavailable", Assert.Throws<InvalidOperationException>(() => input.MoveMouse(1, 1)).Message);
    }

    /// <summary>Serialize host records with the actual stream resolver; no renamed/raw fields disappear.</summary>
    [Fact]
    public void ReadinessRetainsHostRecordButNeverCreatesSourceFrame()
    {
        var gate = new AgentWorldReadinessGate(DesktopCapturePolicy.HostAcquisitionV1);
        var readiness = gate.Observe(AgentHostSnapshotTests.Frame(1, 100, 120), 121);
        var value = JObject.FromObject(readiness, JsonSerializer.Create(new JsonSerializerSettings
        { ContractResolver = new CamelCasePropertyNamesContractResolver() }));
        Assert.Equal(JTokenType.Null, value["sourceFrame"]!.Type);
        Assert.Equal(1, value["hostSnapshot"]!["snapshotId"]!.Value<long>());
    }

    /// <summary>The actual off-thread metadata writer preserves separate host evidence and its unchanged byte quota.</summary>
    [Fact]
    public void SavedReadinessImageRetainsOriginalHostMetadata()
    {
        var directory = Path.Combine(Path.GetTempPath(), "bettergi-agent-host-" + Guid.NewGuid().ToString("N"));
        var recorder = new AgentReadinessSnapshots(directory, encode: _ => [1, 2, 3]);
        var observation = AgentHostSnapshotTests.Frame(1, 100, 120);
        var gate = new AgentWorldReadinessGate(DesktopCapturePolicy.HostAcquisitionV1);
        var readiness = gate.Observe(observation, 121);
        using var pixels = new Mat();
        try
        {
            var save = typeof(AgentReadinessSnapshots).GetMethod("Save", BindingFlags.Instance | BindingFlags.NonPublic)!;
            Assert.True((bool)save.Invoke(recorder, [pixels, observation, readiness, 1])!);
            var value = JObject.Parse(File.ReadAllText(Assert.Single(Directory.GetFiles(directory, "*.json"))));
            Assert.Equal(3, value["freshnessContractVersion"]!.Value<int>());
            Assert.Equal("unknown", value["sourceTimestampKind"]!.Value<string>());
            Assert.Equal(JTokenType.Null, value["sourceFrame"]!.Type);
            Assert.Equal(observation.HostSnapshot!.StartedAtStopwatchTicks,
                value["hostSnapshot"]!["startedAtStopwatchTicks"]!.Value<long>());
            Assert.Equal("host-acquisition-v1", value["sourceKind"]!.Value<string>());
        }
        finally
        {
            if (Directory.Exists(directory)) Directory.Delete(directory, true);
        }
    }

    /// <summary>Build the exact library evidence wrapper around an owned empty CPU Mat.</summary>
    private static GameCaptureFrame Frame(AgentHostSnapshot host) => new(new Mat(), new RECT(0, 0, 1920, 1080), null,
        new GameCaptureHostSnapshotInfo(Guid.ParseExact(host.CaptureEpoch, "N"), host.SnapshotId,
            host.StartedAtStopwatchTicks, host.CompletedAtStopwatchTicks, host.ClockFrequency));

    /// <summary>A real DesktopDc type with only fake target/GDI functions; construction/start invokes no native API.</summary>
    private static GameRuntime Runtime(string policy, bool start)
    {
        var capture = new DesktopDcCapture(_ => DesktopDcTargetTests.Valid(), new DesktopDcGdiOwnershipTests.FakeGdi(),
            _ => new Mat(), () => AgentHostSnapshotTests.Ticks(100), Stopwatch.Frequency,
            () => new DesktopDcThreadDpiScopeTests.CallbackScope(() => { }));
        if (start) capture.Start(100);
        return new GameRuntime(GameRuntimeKind.Win32Window, new Window(), capture, new ForbiddenInput(),
            new FakeSystemInfo(new RECT(320, 180, 2240, 1260), 1), NullMaskWindowDrawingBoard.Instance,
            new MaskWindowMapState(), policy);
    }

    /// <summary>A mutable managed foreground flag tests terminal target loss without Windows calls.</summary>
    private sealed class Window : IGameWindow
    {
        /// <summary>Current sampled foreground state.</summary>
        internal bool Foreground = true;
        /// <inheritdoc />
        public nint Handle => 100;
        /// <inheritdoc />
        public int ProcessId => 200;
        /// <inheritdoc />
        public GameViewport Viewport => new(new RECT(320, 180, 2240, 1260), 1);
        /// <inheritdoc />
        public bool IsAlive => true;
        /// <inheritdoc />
        public bool IsForeground => Foreground;
        /// <inheritdoc />
        public bool IsMinimized => false;
        /// <inheritdoc />
        public bool RequiresForeground => true;
        /// <inheritdoc />
        public void Activate() => throw new InvalidOperationException("No activation permitted.");
        /// <inheritdoc />
        public event EventHandler? ViewportChanged { add { } remove { } }
        /// <inheritdoc />
        public void Dispose() { }
    }

    /// <summary>Any channel access would fail the fixture; the tested rejections must precede it.</summary>
    private sealed class ForbiddenInput : IInputBackend
    {
        /// <inheritdoc />
        public InputBackendKind Kind => InputBackendKind.Win32;
        /// <inheritdoc />
        public IInputChannel Foreground => throw new InvalidOperationException("Unexpected input channel.");
        /// <inheritdoc />
        public IInputChannel Background => throw new InvalidOperationException("Unexpected input channel.");
        /// <inheritdoc />
        public void ReleaseAll() => throw new InvalidOperationException("Unexpected input release.");
        /// <inheritdoc />
        public void Dispose() { }
    }
}
