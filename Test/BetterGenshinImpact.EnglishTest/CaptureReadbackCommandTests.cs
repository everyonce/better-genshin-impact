using System.IO;
using System.Text;
using System.Text.Json;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise readback selection and attachment reporting without a game, window, or graphics device.</summary>
public sealed class CaptureReadbackCommandTests
{
    /// <summary>Both exact options round-trip with presence tracking and distinct replay fingerprints.</summary>
    [Fact]
    public void ExactReadbackChoicesAreScopedAndFingerprintBound()
    {
        var omitted = Request();
        Assert.False(omitted.HasReadbackMode);
        Assert.Null(ExternalControlProtocol.ValidateRequest(omitted, DateTimeOffset.UtcNow));
        foreach (var mode in new[] { "blocking", "poll_single_v1" })
        {
            var request = omitted with { ReadbackMode = mode };
            Assert.True(ExternalControlProtocol.TryDeserializeRequest(
                JsonSerializer.SerializeToUtf8Bytes(request, ExternalControlProtocol.JsonOptions), out var decoded));
            Assert.True(decoded!.HasReadbackMode);
            Assert.Equal(mode, decoded.ReadbackMode);
            Assert.Null(ExternalControlProtocol.ValidateRequest(decoded, DateTimeOffset.UtcNow));
            Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(
                request with { CaptureMode = CaptureModes.BitBlt }, DateTimeOffset.UtcNow));
            Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(
                request with { Command = "startChildGame", CaptureMode = null }, DateTimeOffset.UtcNow));
            Assert.Equal("target_required", ExternalControlProtocol.ValidateRequest(
                request with { TargetNonce = null }, DateTimeOffset.UtcNow));
            Assert.NotEqual(ExternalControlProtocol.Fingerprint(omitted), ExternalControlProtocol.Fingerprint(request));
        }
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(omitted with { ReadbackMode = "blocking" }),
            ExternalControlProtocol.Fingerprint(omitted with { ReadbackMode = "poll_single_v1" }));
    }

    /// <summary>Explicit JSON null is rejected rather than silently selecting the omitted-option default.</summary>
    [Fact]
    public void ExplicitNullRetainsPresenceAndIsRejectedBeforeDispatch()
    {
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(AppendReadback("null"), out var decoded));
        Assert.True(decoded!.HasReadbackMode);
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(decoded, DateTimeOffset.UtcNow));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(
            decoded with { Command = "status", CaptureMode = null }, DateTimeOffset.UtcNow));
    }

    /// <summary>Aliases and malformed strings never reach runtime mutation.</summary>
    [Theory]
    [InlineData("")]
    [InlineData("Blocking")]
    [InlineData("PollSingleV1")]
    [InlineData("poll_single_v2")]
    [InlineData(" blocking")]
    public void UnknownNamesAreRejected(string mode)
    {
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(
            Request() with { ReadbackMode = mode }, DateTimeOffset.UtcNow));
    }

    /// <summary>JSON scalars and containers cannot be coerced into a readback name.</summary>
    [Theory]
    [InlineData("1")]
    [InlineData("true")]
    [InlineData("{}")]
    [InlineData("[]")]
    public void NonStringWireValuesFailDeserialization(string value)
    {
        Assert.False(ExternalControlProtocol.TryDeserializeRequest(AppendReadback(value), out _));
    }

    /// <summary>Runtime selection is validated before acquiring a busy gate or touching the old capture.</summary>
    [Theory]
    [InlineData(CaptureModes.BitBlt, "poll_single_v1")]
    [InlineData(CaptureModes.WindowsGraphicsCapture, "poll_single_v1")]
    [InlineData(CaptureModes.WindowsGraphicsCaptureV2, "unknown")]
    [InlineData(CaptureModes.WindowsGraphicsCaptureV2, null)]
    public async Task InvalidSelectionDoesNotStopOrSelect(CaptureModes mode, string? readback)
    {
        using var gate = new SemaphoreSlim(0, 1);
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => CaptureModeSwitch.ReattachAsync(mode, readback!, gate,
            () => throw new Exception("must not stop"), (_, _) => throw new Exception("must not select"),
            () => throw new Exception("must not persist"), _ => throw new Exception("must not start"), CancellationToken.None));
        Assert.Equal(0, gate.CurrentCount);
    }

    /// <summary>Both settings are selected together after stop, persisted once, then used by startup.</summary>
    [Fact]
    public async Task NewModeKeepsStopSelectPersistStartOrderingAndOwnership()
    {
        using var gate = new SemaphoreSlim(1, 1);
        var steps = new List<string>();
        var selectedMode = CaptureModes.BitBlt;
        var selectedReadback = "blocking";
        await CaptureModeSwitch.ReattachAsync(CaptureModes.WindowsGraphicsCaptureV2, "poll_single_v1", gate,
            () => { Assert.Equal(0, gate.CurrentCount); steps.Add("stop"); return Task.CompletedTask; },
            (mode, readback) =>
            {
                Assert.Equal(new[] { "stop" }, steps);
                selectedMode = mode;
                selectedReadback = readback;
                steps.Add("select");
            },
            () => { Assert.Equal(new[] { "stop", "select" }, steps); steps.Add("persist"); },
            _ =>
            {
                Assert.Equal(0, gate.CurrentCount);
                Assert.Equal(CaptureModes.WindowsGraphicsCaptureV2, selectedMode);
                Assert.Equal("poll_single_v1", selectedReadback);
                steps.Add("start");
                return Task.FromResult(true);
            }, CancellationToken.None);
        Assert.Equal(new[] { "stop", "select", "persist", "start" }, steps);
        Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>A configuration persistence failure cannot attach a runtime or report completion.</summary>
    [Fact]
    public async Task FailedPersistenceSkipsStartupAndReleasesOwnership()
    {
        using var gate = new SemaphoreSlim(1, 1);
        var steps = new List<string>();
        await Assert.ThrowsAsync<IOException>(() => CaptureModeSwitch.ReattachAsync(
            CaptureModes.WindowsGraphicsCaptureV2, "poll_single_v1", gate,
            () => { steps.Add("stop"); return Task.CompletedTask; }, (_, _) => steps.Add("select"),
            () => { steps.Add("persist"); throw new IOException("synthetic persistence failure"); },
            _ => throw new Exception("must not start"), CancellationToken.None));
        Assert.Equal(new[] { "stop", "select", "persist" }, steps);
        Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>New configuration defaults to blocking, and only startup consumes a changed value.</summary>
    [Fact]
    public void SettingsPreserveDefaultAndFreezeExplicitStartupValue()
    {
        var config = new AllConfig();
        Assert.Equal("blocking", config.WgcV2ReadbackMode);
        var first = GameCaptureSettings.From(config);
        config.WgcV2ReadbackMode = "poll_single_v1";
        Assert.Equal("blocking", first["ReadbackMode"]);
        Assert.Equal("poll_single_v1", GameCaptureSettings.From(config)["ReadbackMode"]);
    }

    /// <summary>Mode reporting reads the actual capture and never performs capture work or consults saved options.</summary>
    [Fact]
    public void EffectiveModeRequiresAnAttachedCapturingImplementation()
    {
        Assert.Null(GameCaptureSettings.GetReadbackModeName(null));
        using var plain = new FakeCapture { IsCapturing = true };
        Assert.Null(GameCaptureSettings.GetReadbackModeName(plain));
        using var readback = new FakeReadbackCapture();
        Assert.Null(GameCaptureSettings.GetReadbackModeName(readback));
        readback.Start(0);
        Assert.Equal("blocking", GameCaptureSettings.GetReadbackModeName(readback));
        readback.ReadbackMode = GameCaptureReadbackMode.PollSingleV1;
        Assert.Equal("poll_single_v1", GameCaptureSettings.GetReadbackModeName(readback));
        readback.Stop();
        Assert.Null(GameCaptureSettings.GetReadbackModeName(readback));
    }

    /// <summary>Construct a valid nonce-bound request without contacting any process.</summary>
    private static ExternalControlRequest Request() => new()
    {
        Version = 1, RequestId = Guid.NewGuid(), CreatedAtUnixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
        Command = "setCaptureMode", CaptureMode = CaptureModes.WindowsGraphicsCaptureV2,
        TargetProcessId = 123, TargetWindowsSessionId = 3, TargetNonce = "child-epoch"
    };

    /// <summary>Append an uncoerced JSON value so the real parser exercises presence and type handling.</summary>
    private static byte[] AppendReadback(string jsonValue)
    {
        var request = JsonSerializer.Serialize(Request(), ExternalControlProtocol.JsonOptions);
        return Encoding.UTF8.GetBytes(request[..^1] + ",\"readbackMode\":" + jsonValue + "}");
    }

    /// <summary>Minimal capture used solely to test metadata; pixel calls are forbidden.</summary>
    private class FakeCapture : IGameCapture
    {
        /// <summary>Expose only a synthetic attachment state.</summary>
        public bool IsCapturing { get; set; }
        /// <summary>Mark this synthetic capture as attached without touching a window.</summary>
        public void Start(nint hWnd, Dictionary<string, object>? settings = null) => IsCapturing = true;
        /// <summary>Metadata queries must never invoke capture.</summary>
        public GameCaptureFrame? Capture() => throw new InvalidOperationException("Metadata must not capture.");
        /// <summary>End the synthetic attachment.</summary>
        public void Stop() => IsCapturing = false;
        /// <summary>Dispose only the synthetic attachment state.</summary>
        public void Dispose() => Stop();
    }

    /// <summary>Provide an actual readback mode independently of persisted configuration.</summary>
    private sealed class FakeReadbackCapture : FakeCapture, IGameCaptureReadback
    {
        /// <summary>The selected mode is metadata, not a readiness or freshness guarantee.</summary>
        public GameCaptureReadbackMode ReadbackMode { get; set; } = GameCaptureReadbackMode.Blocking;
        /// <summary>Metadata queries cannot initiate readback.</summary>
        public GameCaptureAttempt CaptureAttempt() => throw new InvalidOperationException("Metadata must not poll.");
        /// <summary>Metadata queries cannot initiate diagnostic readback either.</summary>
        public GameCaptureAttempt CaptureAttempt(out GameCaptureCallTiming timing)
        {
            timing = default!;
            throw new InvalidOperationException("Metadata must not poll.");
        }
    }
}
