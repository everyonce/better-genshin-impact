using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using BetterGenshinImpact.Service.ExternalControl;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Bind Host/Game replacement intent without launching processes or changing the legacy direct restart contract.</summary>
public sealed class IdleRestartStartupIntentTests
{
    /// <summary>Version two requires an exact intent; version one cannot smuggle in endpoint-only startup.</summary>
    [Theory]
    [InlineData(1, null, true)]
    [InlineData(1, "controlEndpoint", false)]
    [InlineData(1, "gameRuntime", false)]
    [InlineData(2, null, false)]
    [InlineData(2, "controlEndpoint", true)]
    [InlineData(2, "gameRuntime", true)]
    [InlineData(2, "ControlEndpoint", false)]
    [InlineData(2, "unknown", false)]
    [InlineData(3, "controlEndpoint", false)]
    public void ContractValidatesVersionAndIntentTogether(int version, string? mode, bool valid)
    {
        var now = DateTimeOffset.UtcNow;
        var request = Request(now, new ExternalControlIdleRestart
        {
            Version = version, StartupMode = mode,
            TargetDirectory = @"D:\artifacts\release-r20\BetterGI-English-win-x64",
            ExeSha256 = new string('a', 64), DllSha256 = new string('b', 64)
        });
        var error = ExternalControlProtocol.ValidateRequest(request, now);
        Assert.Equal(valid ? null : "invalid_command_parameters", error);
    }

    /// <summary>Changing only startup intent changes replay identity and survives the exact JSON request round trip.</summary>
    [Fact]
    public void StartupIntentIsPartOfTheReplayFingerprint()
    {
        var now = DateTimeOffset.UtcNow;
        var endpoint = Request(now, new ExternalControlIdleRestart
        {
            Version = 2, StartupMode = ExternalControlIdleRestart.ControlEndpoint,
            TargetDirectory = @"D:\artifacts\release-r20\BetterGI-English-win-x64",
            ExeSha256 = new string('a', 64), DllSha256 = new string('b', 64)
        });
        var game = endpoint with { IdleRestart = endpoint.IdleRestart! with { StartupMode = ExternalControlIdleRestart.GameRuntime } };
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(endpoint), ExternalControlProtocol.Fingerprint(game));
        var bytes = JsonSerializer.SerializeToUtf8Bytes(endpoint, ExternalControlProtocol.JsonOptions);
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(bytes, out var decoded));
        Assert.Equal(ExternalControlIdleRestart.ControlEndpoint, decoded!.IdleRestart!.StartupMode);
        Assert.Equal(ExternalControlProtocol.Fingerprint(endpoint), ExternalControlProtocol.Fingerprint(decoded));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(
            endpoint with { Command = "startPilot" }, now));
        using var wire = JsonDocument.Parse(ExternalControlProtocol.SerializeResponse(new ExternalControlResponse
        {
            Status = new ExternalControlStatus { IdleRestartVersion = 2 }
        }));
        Assert.Equal(2, wire.RootElement.GetProperty("status").GetProperty("idleRestartVersion").GetInt32());
    }

    /// <summary>The same validated target starts only its endpoint for Host, while Game and both legacy forms retain start.</summary>
    [Theory]
    [InlineData(0, null, true)]
    [InlineData(1, null, true)]
    [InlineData(2, "gameRuntime", true)]
    [InlineData(2, "controlEndpoint", false)]
    public void PreparedArgumentsRespectIntentWithoutWeakeningTargetPins(int version, string? mode, bool startsGame)
    {
        var root = Path.Combine(Path.GetTempPath(), "BetterGI-startup-intent-" + Guid.NewGuid().ToString("N"));
        try
        {
            var current = Path.Combine(root, "release-r19", "BetterGI-English-win-x64");
            var target = Path.Combine(root, "release-r20", "BetterGI-English-win-x64");
            Directory.CreateDirectory(Path.Combine(current, "User", "ExternalControl"));
            Directory.CreateDirectory(Path.Combine(target, "User", "ExternalControl"));
            File.WriteAllText(Path.Combine(target, "BetterGI.exe"), "synthetic executable never launched");
            File.WriteAllText(Path.Combine(target, "BetterGI.dll"), "synthetic assembly never loaded");
            File.WriteAllText(Path.Combine(target, "User", "ExternalControl", "enable-quest-control.json"),
                "{\"version\":1,\"enabled\":true,\"allowAppRestart\":true}");
            var manifest = new ExternalControlIdleRestart
            {
                Version = 1, TargetDirectory = target,
                ExeSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(target, "BetterGI.exe")))),
                DllSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(target, "BetterGI.dll"))))
            };
            File.WriteAllText(Path.Combine(current, ExternalControlRestart.ManifestPath), JsonSerializer.Serialize(manifest));
            var intent = version == 0 ? null : manifest with { Version = version, StartupMode = mode };
            var start = ExternalControlRestart.Prepare(current, 123, true, intent);
            var arguments = new List<string> { "--instance", "childsession", "--restart-from-pid", "123", "--automation" };
            if (startsGame) arguments.Add("start");
            Assert.Equal(arguments, start.ArgumentList);
            Assert.Equal(Path.Combine(target, "BetterGI.exe"), start.FileName);
            Assert.Equal(target, start.WorkingDirectory);
            Assert.False(start.UseShellExecute);
            if (intent is not null)
                Assert.Throws<InvalidOperationException>(() => ExternalControlRestart.Prepare(current, 123, true,
                    intent with { DllSha256 = new string('0', 64) }));
        }
        finally { Directory.Delete(root, recursive: true); }
    }

    /// <summary>Use one pinned synthetic child identity; no application services are initialized.</summary>
    private static ExternalControlRequest Request(DateTimeOffset now, ExternalControlIdleRestart expectation) => new()
    {
        Version = 1, RequestId = Guid.NewGuid(), Command = "restartApp", CreatedAtUnixMs = now.ToUnixTimeMilliseconds(),
        TargetProcessId = 123, TargetWindowsSessionId = 3, TargetNonce = "fixture-child", IdleRestart = expectation
    };
}
