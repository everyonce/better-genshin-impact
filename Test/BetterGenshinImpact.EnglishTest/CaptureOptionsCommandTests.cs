using System.Reflection;
using System.Text;
using System.Text.Json;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using Fischless.GameCapture.Graphics;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise exact opt-ins, lifecycle admission and responsive metadata without native capture or input.</summary>
public sealed class CaptureOptionsCommandTests
{
    /// <summary>All explicit choices are authenticated, fingerprint-bound and limited to WGC V2.</summary>
    [Theory]
    [InlineData("disabled", "gpu")]
    [InlineData("disabled", "cpu")]
    [InlineData("hold-until-readback-v1", "gpu")]
    [InlineData("hold-until-readback-v1", "cpu")]
    public void ExactOptionsRoundTripAndBindFingerprint(string retention, string conversion)
    {
        var omitted = Request();
        var selected = omitted with { SourceRetention = retention, Conversion = conversion };
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(
            JsonSerializer.SerializeToUtf8Bytes(selected, ExternalControlProtocol.JsonOptions), out var decoded));
        Assert.Null(ExternalControlProtocol.ValidateRequest(decoded!, DateTimeOffset.UtcNow));
        Assert.True(decoded!.HasSourceRetention && decoded.HasConversion);
        Assert.Equal(retention, decoded.SourceRetention);
        Assert.Equal(conversion, decoded.Conversion);
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(omitted), ExternalControlProtocol.Fingerprint(decoded));
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(selected with { Conversion = "gpu" }),
            ExternalControlProtocol.Fingerprint(selected with { Conversion = "cpu" }));
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(
            selected with { CaptureMode = CaptureModes.BitBlt }, DateTimeOffset.UtcNow));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(
            selected with { Command = "status", CaptureMode = null }, DateTimeOffset.UtcNow));
        Assert.Equal("target_required", ExternalControlProtocol.ValidateRequest(
            selected with { TargetNonce = null }, DateTimeOffset.UtcNow));
    }

    /// <summary>Explicit null, aliases and wrong JSON types fail before any stop/configuration mutation.</summary>
    [Theory]
    [InlineData("sourceRetention", "null", true)]
    [InlineData("conversion", "null", true)]
    [InlineData("sourceRetention", "\"Disabled\"", true)]
    [InlineData("sourceRetention", "\"hold\"", true)]
    [InlineData("conversion", "\"GPU\"", true)]
    [InlineData("conversion", "\"cpu \"", true)]
    [InlineData("sourceRetention", "true", false)]
    [InlineData("sourceRetention", "1", false)]
    [InlineData("conversion", "{}", false)]
    [InlineData("conversion", "[]", false)]
    public void InvalidWireOptionsCannotReachDispatch(string field, string value, bool parsed)
    {
        var json = JsonSerializer.Serialize(Request(), ExternalControlProtocol.JsonOptions);
        Assert.Equal(parsed, ExternalControlProtocol.TryDeserializeRequest(
            Encoding.UTF8.GetBytes(json[..^1] + ",\"" + field + "\":" + value + "}"), out var request));
        if (!parsed) return;
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(request!, DateTimeOffset.UtcNow));
        Assert.True(field == "sourceRetention" ? request!.HasSourceRetention : request!.HasConversion);
    }

    /// <summary>Defaults omit source retention; later config mutation cannot change an already-built startup dictionary.</summary>
    [Fact]
    public void CentralSettingsPreserveDefaultsAndFreezeExplicitSelections()
    {
        var config = new AllConfig();
        var original = GameCaptureSettings.From(config);
        Assert.Equal("disabled", config.WgcV2SourceRetention);
        Assert.False(config.WgcV2UseCpuConvert);
        Assert.False(original.ContainsKey("ExperimentalSourceRetention"));
        Assert.Equal(false, original["UseCpuConvert"]);
        config.WgcV2SourceRetention = "hold-until-readback-v1";
        config.WgcV2UseCpuConvert = true;
        var selected = GameCaptureSettings.From(config);
        Assert.Equal("hold-until-readback-v1", selected["ExperimentalSourceRetention"]);
        Assert.Equal(true, selected["UseCpuConvert"]);
        config.WgcV2SourceRetention = "disabled";
        Assert.False(GameCaptureSettings.From(config).ContainsKey("ExperimentalSourceRetention"));
        Assert.Equal("hold-until-readback-v1", selected["ExperimentalSourceRetention"]);
        Assert.False(original.ContainsKey("ExperimentalSourceRetention"));
    }

    /// <summary>Option validation takes precedence over busy ownership and all runtime callbacks.</summary>
    [Theory]
    [InlineData(CaptureModes.BitBlt, "disabled", null)]
    [InlineData(CaptureModes.WindowsGraphicsCapture, null, "gpu")]
    [InlineData(CaptureModes.WindowsGraphicsCaptureV2, "unknown", "gpu")]
    [InlineData(CaptureModes.WindowsGraphicsCaptureV2, "disabled", "CPU")]
    public async Task InvalidSelectionHasNoSideEffects(CaptureModes mode, string? retention, string? conversion)
    {
        using var gate = new SemaphoreSlim(0, 1);
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => CaptureModeSwitch.ReattachAsync(mode,
            "blocking", retention, conversion, gate, () => throw new Exception("stop forbidden"),
            (_, _, _, _) => throw new Exception("select forbidden"), () => throw new Exception("persist forbidden"),
            _ => throw new Exception("start forbidden"), CancellationToken.None));
        Assert.Equal(0, gate.CurrentCount);
    }

    /// <summary>Absent options remain absent through lifecycle callbacks; explicit options are selected only after stop.</summary>
    [Theory]
    [InlineData(null, null)]
    [InlineData("hold-until-readback-v1", "cpu")]
    [InlineData("disabled", "gpu")]
    public async Task SelectionIsAtomicWithStopAndStartup(string? retention, string? conversion)
    {
        using var gate = new SemaphoreSlim(1, 1);
        var steps = new List<string>();
        await CaptureModeSwitch.ReattachAsync(CaptureModes.WindowsGraphicsCaptureV2, "poll_single_v1",
            retention, conversion, gate,
            () => { Assert.Equal(0, gate.CurrentCount); steps.Add("stop"); return Task.CompletedTask; },
            (mode, readback, actualRetention, actualConversion) =>
            {
                Assert.Equal(new[] { "stop" }, steps);
                Assert.Equal(CaptureModes.WindowsGraphicsCaptureV2, mode);
                Assert.Equal("poll_single_v1", readback);
                Assert.Equal(retention, actualRetention);
                Assert.Equal(conversion, actualConversion);
                steps.Add("select");
            }, () => steps.Add("persist"),
            _ => { Assert.Equal(new[] { "stop", "select", "persist" }, steps); steps.Add("start"); return Task.FromResult(true); },
            CancellationToken.None);
        Assert.Equal(new[] { "stop", "select", "persist", "start" }, steps);
        Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>Cancellation during stop leaves persisted settings unchanged and releases the existing gate after cleanup.</summary>
    [Fact]
    public async Task CancellationDuringStopCannotSelectOrStart()
    {
        using var gate = new SemaphoreSlim(1, 1);
        using var cancellation = new CancellationTokenSource();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => CaptureModeSwitch.ReattachAsync(
            CaptureModes.WindowsGraphicsCaptureV2, "poll_single_v1", "hold-until-readback-v1", "cpu", gate,
            () => { cancellation.Cancel(); return Task.CompletedTask; },
            (_, _, _, _) => throw new Exception("select forbidden"), () => throw new Exception("persist forbidden"),
            _ => throw new Exception("start forbidden"), cancellation.Token));
        Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>Existing capture-state locks cannot block a status metadata query, even during a simulated stall.</summary>
    [Fact]
    public async Task EffectiveOptionsRequireActiveV2AndNeverWaitOnCaptureLocks()
    {
        using var capture = new GraphicsCaptureV2();
        Assert.Null(GameCaptureSettings.GetSourceRetentionName(capture));
        Assert.Null(GameCaptureSettings.GetConversionName(capture));
        Assert.Null(GameCaptureSettings.GetSourceRetentionName(null));
        Assert.Null(GameCaptureSettings.GetConversionName(null));
        SetField(capture, "_sourceRetentionEnabled", true);
        SetField(capture, "_useCpuConvert", true);
        typeof(GraphicsCaptureV2).GetProperty(nameof(GraphicsCaptureV2.IsCapturing))!.SetValue(capture, true);
        using var held = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        var owner = Task.Run(() =>
        {
            lock (GetField(capture, "_lock"))
            lock (GetField(capture, "_captureGate"))
            {
                held.Set();
                release.Wait();
            }
        });
        try
        {
            Assert.True(held.Wait(TimeSpan.FromSeconds(2)));
            var query = Task.Run(() => (GameCaptureSettings.GetSourceRetentionName(capture), GameCaptureSettings.GetConversionName(capture)));
            var actual = await query.WaitAsync(TimeSpan.FromSeconds(2));
            Assert.Equal(("hold-until-readback-v1", "cpu"), actual);
        }
        finally
        {
            release.Set();
            await owner.WaitAsync(TimeSpan.FromSeconds(2));
            // No native session was created; restore stopped metadata before normal disposal.
            typeof(GraphicsCaptureV2).GetProperty(nameof(GraphicsCaptureV2.IsCapturing))!.SetValue(capture, false);
        }
    }

    /// <summary>Representative complete lifecycle, capability and retained reset status, shared by long proof-envelope cases.</summary>
    internal static ExternalControlStatus CompleteEnvelope(ExternalControlStatus status, string readbackMode) => status with
    {
        CaptureMode = "WindowsGraphicsCaptureV2", ReadbackVersion = 1, ReadbackModes = ["blocking", "poll_single_v1"],
        ConfiguredReadbackMode = readbackMode, EffectiveReadbackMode = readbackMode,
        CaptureOptionsVersion = 1, SourceRetentions = ["disabled", "hold-until-readback-v1"], ConversionModes = ["gpu", "cpu"],
        ConfiguredSourceRetention = "hold-until-readback-v1", EffectiveSourceRetention = "hold-until-readback-v1",
        ConfiguredConversion = "gpu", EffectiveConversion = "gpu",
        DesktopDcSourcePolicyVersion = 1, DesktopDcSourcePolicies = ["observe-only", "host-acquisition-v1"],
        ConfiguredDesktopDcSourcePolicy = "host-acquisition-v1", EffectiveDesktopDcSourcePolicy = null,
        UiStatus = "current", AutomationEnabled = true, RuntimeRunning = true, AutomationState = "game_ready",
        IdleRestartVersion = 2, AppVersion = "0.66.2-alpha.4", AssemblySha256 = new string('a', 64),
        AppDirectory = new string('d', 1024), CaptureStorageVersion = 1,
        ProcessId = 12345, WindowsSessionId = 3, InstanceType = "ChildSession", RemoteDesktop = true,
        PipeName = "BetterGI.ExternalControl.DC8465355EE156CA.3.12345", InstanceNonce = new string('b', 32), RootProcessId = 23456,
        AgentStreamState = "completed", AgentObservationProfile = "p2p-native-hamming-192-v1", AgentPipeName = "BetterGI.Agent.local",
        AgentStreamError = new string('e', 512), PilotState = "idle",
        NavigationReset = new()
        {
            ReadbackMode = readbackMode, CapturePolicy = "task_owned_timer", State = "completed", Phase = "verify",
            RunId = new string('c', 32), GameProcessId = 34567, WindowsSessionId = 3,
            Samples = Enumerable.Range(1, 3).Select(index => new BetterGenshinImpact.GameTask.NavigationReset.NavigationResetSample(
                -867.68359375, 2281.37890625, 359.123456789, DateTimeOffset.Parse("2026-10-24T09:00:00.1234567+00:00"),
                Guid.Parse("fedcba98-7654-3210-fedc-ba9876543210"), 123456789012345 + index, 123456789012345 + index,
                .9967853426933289, .9999980926513672, "City_102")).ToArray()
        }
    };

    /// <summary>Construct one valid authenticated request without a pipe or desktop.</summary>
    private static ExternalControlRequest Request() => new()
    {
        Version = 1, RequestId = Guid.NewGuid(), CreatedAtUnixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
        Command = "setCaptureMode", CaptureMode = CaptureModes.WindowsGraphicsCaptureV2,
        TargetProcessId = 123, TargetWindowsSessionId = 3, TargetNonce = "child-epoch"
    };

    /// <summary>Read a private managed field solely to hold the actual lock in the no-native metadata fixture.</summary>
    private static object GetField(object capture, string name) =>
        typeof(GraphicsCaptureV2).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(capture)!;

    /// <summary>Set start-selected managed metadata without starting any capture or native object.</summary>
    private static void SetField(object capture, string name, object value) =>
        typeof(GraphicsCaptureV2).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(capture, value);
}
