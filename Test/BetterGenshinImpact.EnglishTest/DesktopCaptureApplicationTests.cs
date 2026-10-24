using System.Reflection;
using System.Text;
using System.Text.Json;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Mask;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Service;
using BetterGenshinImpact.Service.ExternalControl;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using Fischless.GameCapture;
using Fischless.GameCapture.DesktopDc;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Desktop selection, passive/controller separation and overlay lifetime without native allocation or input.</summary>
public sealed class DesktopCaptureApplicationTests
{
    /// <summary>Build one authenticated wire request without a pipe or lifecycle side effect.</summary>
    private static ExternalControlRequest Request() => new()
    {
        Version = 1, RequestId = Guid.NewGuid(), CreatedAtUnixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
        Command = "setCaptureMode", CaptureMode = CaptureModes.DesktopDc,
        TargetProcessId = 123, TargetWindowsSessionId = 3, TargetNonce = "child-epoch"
    };

    /// <summary>Only two exact policy values bind the authenticated fingerprint.</summary>
    [Theory]
    [InlineData("observe-only")] [InlineData("host-acquisition-v1")]
    public void ExplicitPolicyRoundTripsAndBindsRequest(string policy)
    {
        var omitted = Request();
        var selected = omitted with { DesktopDcSourcePolicy = policy };
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(JsonSerializer.SerializeToUtf8Bytes(selected,
            ExternalControlProtocol.JsonOptions), out var read));
        Assert.True(read!.HasDesktopDcSourcePolicy);
        Assert.Equal(policy, read.DesktopDcSourcePolicy);
        Assert.Null(ExternalControlProtocol.ValidateRequest(read, DateTimeOffset.UtcNow));
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(omitted), ExternalControlProtocol.Fingerprint(selected));
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(
            selected with { CaptureMode = CaptureModes.WindowsGraphicsCaptureV2 }, DateTimeOffset.UtcNow));
    }

    /// <summary>Explicit null, aliases and WGC-only parameters never reach backend selection.</summary>
    [Theory]
    [InlineData("desktopDcSourcePolicy", "null")]
    [InlineData("desktopDcSourcePolicy", "\"Host-acquisition-v1\"")]
    [InlineData("desktopDcSourcePolicy", "\"host-acquisition-v2\"")]
    [InlineData("readbackMode", "\"blocking\"")]
    [InlineData("sourceRetention", "\"disabled\"")]
    [InlineData("conversion", "\"cpu\"")]
    public void InvalidDesktopWireIsRejected(string field, string value)
    {
        var json = JsonSerializer.Serialize(Request(), ExternalControlProtocol.JsonOptions);
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes(
            json[..^1] + ",\"" + field + "\":" + value + "}"), out var request));
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(request!, DateTimeOffset.UtcNow));
    }

    /// <summary>Desktop settings are inert; saved WGC fields survive selection and cannot grant host permission.</summary>
    [Fact]
    public void DesktopDefaultsToObserveOnlyWithoutWgcSettings()
    {
        var config = new AllConfig { CaptureMode = nameof(CaptureModes.DesktopDc),
            WgcV2ReadbackMode = "poll_single_v1", WgcV2SourceRetention = "hold-until-readback-v1", WgcV2UseCpuConvert = true };
        Assert.Equal(DesktopCapturePolicy.ObserveOnly, config.DesktopDcSourcePolicy);
        Assert.Empty(GameCaptureSettings.From(config));
        Assert.Equal("poll_single_v1", config.WgcV2ReadbackMode);
        Assert.True(config.WgcV2UseCpuConvert);
        Assert.Equal("hold-until-readback-v1", config.WgcV2SourceRetention);
        config.DesktopDcSourcePolicy = "unknown";
        Assert.Throws<ArgumentOutOfRangeException>(() => GameCaptureSettings.From(config));
    }

    /// <summary>The same task gate covers stop, dormant-setting preservation and selected-policy startup.</summary>
    [Theory]
    [InlineData(null)] [InlineData("observe-only")] [InlineData("host-acquisition-v1")]
    public async Task DesktopLifecyclePreservesOmittedOptions(string? policy)
    {
        using var gate = new SemaphoreSlim(1, 1); var events = new List<string>();
        await CaptureModeSwitch.ReattachAsync(CaptureModes.DesktopDc, "poll_single_v1", null, null, policy, gate,
            () => { events.Add("stop"); return Task.CompletedTask; },
            (mode, readback, retention, conversion, selected) =>
            {
                Assert.Equal(0, gate.CurrentCount); Assert.Equal(new[] { "stop" }, events);
                Assert.Equal(CaptureModes.DesktopDc, mode); Assert.Equal("poll_single_v1", readback);
                Assert.Null(retention); Assert.Null(conversion); Assert.Equal(policy, selected); events.Add("select");
            }, () => events.Add("persist"), _ => { events.Add("start"); return Task.FromResult(true); }, default);
        Assert.Equal(new[] { "stop", "select", "persist", "start" }, events); Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>Observe-only has no input channel, but release/disposal stay safe and idempotent.</summary>
    [Fact]
    public void ObserveOnlyBackendCannotDispatch()
    {
        using var input = new ObserveOnlyInputBackend();
        Assert.Throws<InvalidOperationException>(() => input.Foreground);
        Assert.Throws<InvalidOperationException>(() => input.Background);
        input.ReleaseAll(); input.Dispose(); input.ReleaseAll();
    }

    /// <summary>Only the explicit native observer can enter without controller permission; generic tasks remain denied.</summary>
    [Fact]
    public void PassiveRuntimeCannotBecomeControllerOrGenericTask()
    {
        using var runtime = CreateRuntime(DesktopCapturePolicy.ObserveOnly, new Window());
        TaskRunner.ValidateDesktopAdmission(runtime, false, true);
        Assert.Throws<InvalidOperationException>(() => TaskRunner.ValidateDesktopAdmission(runtime, true));
        Assert.Throws<InvalidOperationException>(() => TaskRunner.ValidateDesktopAdmission(runtime, false));
        Assert.Equal(DesktopCapturePolicy.ObserveOnly, GameCaptureSettings.GetDesktopDcSourcePolicy(runtime));
        runtime.SignalStopping(); Assert.Null(GameCaptureSettings.GetDesktopDcSourcePolicy(runtime));
    }

    /// <summary>Foreground loss in the shared teleport wait is terminal and never invokes Activate or a focus retry.</summary>
    [Theory]
    [InlineData(false, false)] [InlineData(true, true)]
    public void SharedWaitNeverRestoresDesktopFocus(bool foreground, bool minimized)
    {
        var window = new Window { IsForeground = foreground, IsMinimized = minimized };
        using var runtime = CreateRuntime(DesktopCapturePolicy.HostAcquisitionV1, window);
        Assert.Throws<InvalidOperationException>(() => GameRuntimeExtensions.CheckAndActivateGameWindow(runtime,
            new GameTaskWait(() => true, default)));
        Assert.Equal(0, window.Activations);
    }

    /// <summary>Suppression precedes synchronous hide and survives overlapping owners; releasing it never shows UI.</summary>
    [Fact]
    public void OverlayScopeOrdersHideAndRetirement()
    {
        var generation = DesktopCaptureOverlayScope.Generation; var hides = 0;
        using var first = DesktopCaptureOverlayScope.Acquire(() =>
        { Assert.True(DesktopCaptureOverlayScope.IsSuppressed); hides++; });
        var second = DesktopCaptureOverlayScope.Acquire(() => hides++);
        first.Dispose(); Assert.True(DesktopCaptureOverlayScope.IsSuppressed);
        second.Dispose(); second.Dispose(); Assert.False(DesktopCaptureOverlayScope.IsSuppressed);
        Assert.Equal(2, hides); Assert.True(DesktopCaptureOverlayScope.Generation > generation);
    }

    /// <summary>A failed whole-overlay hide cannot leak a suppression owner or authorize capture startup.</summary>
    [Fact]
    public void FailedOverlayHideRestoresOnlyEligibility()
    {
        Assert.Throws<InvalidOperationException>(() => DesktopCaptureOverlayScope.Acquire(() => throw new InvalidOperationException("hide")));
        Assert.False(DesktopCaptureOverlayScope.IsSuppressed);
    }

    /// <summary>Use only managed start-state metadata; no target/DC/native capture is opened.</summary>
    private static GameRuntime CreateRuntime(string policy, Window window)
    {
        var capture = new DesktopDcCapture();
        typeof(DesktopDcCapture).GetField("_capturing", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(capture, true);
        return new(GameRuntimeKind.Win32Window, window, capture, new ObserveOnlyInputBackend(),
            new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1), NullMaskWindowDrawingBoard.Instance, new MaskWindowMapState(), policy);
    }

    /// <summary>Read-only target double counts any forbidden activation.</summary>
    private sealed class Window : IGameWindow
    {
        /// <summary>Fake identity only; no Win32 lookup uses this value.</summary>
        public nint Handle => 0;
        /// <summary>Existing process ID is metadata, not a capture target.</summary>
        public int ProcessId => Environment.ProcessId;
        /// <summary>Fixed synthetic physical crop.</summary>
        public GameViewport Viewport => new(new RECT(0, 0, 1920, 1080), 1);
        /// <summary>Fixture target remains alive.</summary>
        public bool IsAlive => true;
        /// <summary>Mutable sampled focus for rejection tests.</summary>
        public bool IsForeground { get; init; } = true;
        /// <summary>Mutable sampled minimization for rejection tests.</summary>
        public bool IsMinimized { get; init; }
        /// <summary>Use the real foreground-required admission branch.</summary>
        public bool RequiresForeground => true;
        /// <summary>No controller path may request this operation.</summary>
        public int Activations { get; private set; }
        /// <summary>Count only; never touch a real window.</summary>
        public void Activate() => Activations++;
        /// <summary>No real event source exists.</summary>
        public event EventHandler? ViewportChanged { add { } remove { } }
        /// <summary>No native resource exists.</summary>
        public void Dispose() { }
    }
}
