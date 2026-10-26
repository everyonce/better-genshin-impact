using System.Security.Cryptography;
using System.Text.Json;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.Pulonia.Services;

namespace BetterGenshinImpact.UnitTest.ServiceTests.ExternalControl;

/// <summary>Tiny disposable startup records; never creates a process, Application, service or connection.</summary>
public sealed class UpgradeStartupFileTests
{
    /// <summary>Create a complete package-local scalar record with fake binary hashes.</summary>
    private static Dictionary<string, object> Record(string directory, DateTimeOffset now) => new()
    {
        ["version"] = 1, ["nonce"] = new string('a', 32), ["targetDirectory"] = directory,
        ["rootSessionId"] = 2, ["cloneSessionId"] = 3, ["gameProcessId"] = 42, ["gameStartedFileTime"] = 1L,
        ["exeSha256"] = Convert.ToHexString(SHA256.HashData(new byte[] { 1 })).ToLowerInvariant(),
        ["dllSha256"] = Convert.ToHexString(SHA256.HashData(new byte[] { 2 })).ToLowerInvariant(),
        ["createdUtc"] = now, ["expiresUtc"] = now.AddMinutes(2)
    };

    /// <summary>Each fixture owns exactly its tiny temporary directory and removes only that directory.</summary>
    private static void InPackage(Action<string, DateTimeOffset, Dictionary<string, object>> body)
    {
        var directory = Path.Combine(Path.GetTempPath(), "upgrade-file-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            File.WriteAllBytes(Path.Combine(directory, "BetterGI.exe"), [1]);
            File.WriteAllBytes(Path.Combine(directory, "BetterGI.dll"), [2]);
            var now = DateTimeOffset.UtcNow;
            body(directory, now, Record(directory, now));
        }
        finally { Directory.Delete(directory, true); }
    }

    /// <summary>Consumption is one-shot; only explicit completion makes future normal starts usable.</summary>
    [Fact]
    public void PendingConsumedCompletedHaveDistinctStartupBehavior()
        => InPackage((directory, now, record) =>
        {
            File.WriteAllBytes(Path.Combine(directory, UpgradeStartupFile.PendingName), JsonSerializer.SerializeToUtf8Bytes(record));
            var binding = UpgradeStartupFile.Consume(directory, true, false, () => 2, now)!;
            Assert.Equal(3, binding.SessionId);
            Assert.False(binding.IsReleased);
            Assert.True(File.Exists(Path.Combine(directory, UpgradeStartupFile.ConsumedName)));
            Assert.Throws<InvalidOperationException>(() => UpgradeStartupFile.Consume(directory, true, false, () => 2, now));
            binding.CompleteStartupFile();
            binding.MarkReleased();
            Assert.Null(UpgradeStartupFile.Consume(directory, false, false,
                () => throw new Exception("Completed startup must not reuse old session identity"), now.AddDays(2)));
        });

    /// <summary>Missing opt-in, wrong local session and direct/file ambiguity cannot consume a record.</summary>
    [Theory]
    [InlineData(false, false, 2)]
    [InlineData(true, true, 2)]
    [InlineData(true, false, 4)]
    public void StartupContextMustMatch(bool enabled, bool direct, int session)
        => InPackage((directory, now, record) =>
        {
            var path = Path.Combine(directory, UpgradeStartupFile.PendingName);
            File.WriteAllBytes(path, JsonSerializer.SerializeToUtf8Bytes(record));
            Assert.Throws<InvalidOperationException>(() => UpgradeStartupFile.Consume(directory, enabled, direct, () => session, now));
            Assert.True(File.Exists(path));
        });

    /// <summary>Unknown schema, stale/oversized lifetime and wrong package identity all fail before consumption.</summary>
    [Theory]
    [InlineData("unknown")]
    [InlineData("expired")]
    [InlineData("tooLong")]
    [InlineData("hash")]
    [InlineData("path")]
    public void InvalidRecordCannotPublishHold(string change)
        => InPackage((directory, now, record) =>
        {
            if (change == "unknown") record["command"] = "arbitrary";
            if (change == "expired") record["expiresUtc"] = now;
            if (change == "tooLong") record["expiresUtc"] = now.AddMinutes(6);
            if (change == "hash") record["dllSha256"] = new string('0', 64);
            if (change == "path") record["targetDirectory"] = directory + "-foreign";
            var path = Path.Combine(directory, UpgradeStartupFile.PendingName);
            File.WriteAllBytes(path, JsonSerializer.SerializeToUtf8Bytes(record));
            Assert.Throws<InvalidDataException>(() => UpgradeStartupFile.Consume(directory, true, false, () => 2, now));
            Assert.True(File.Exists(path));
        });

    /// <summary>Completion never accepts caller replacement of the consumed identity.</summary>
    [Fact]
    public void ChangedConsumedRecordStaysBlocked()
        => InPackage((directory, now, record) =>
        {
            File.WriteAllBytes(Path.Combine(directory, UpgradeStartupFile.PendingName), JsonSerializer.SerializeToUtf8Bytes(record));
            var binding = UpgradeStartupFile.Consume(directory, true, false, () => 2, now)!;
            File.AppendAllText(Path.Combine(directory, UpgradeStartupFile.ConsumedName), " ");
            Assert.Throws<InvalidDataException>(binding.CompleteStartupFile);
            Assert.False(File.Exists(Path.Combine(directory, UpgradeStartupFile.CompletedName)));
            Assert.False(binding.IsReleased);
        });

    /// <summary>Starting initialization alone cannot unblock either direct mutations or background execution.</summary>
    [Fact]
    public async Task TwoPhaseHoldRequiresExplicitExecutionRelease()
    {
        var hold = new PuloniaStartupHold(true);
        var initialization = hold.WaitForInitializationAsync(CancellationToken.None);
        var execution = hold.WaitAsync(CancellationToken.None);
        Assert.False(initialization.IsCompleted);
        hold.AllowInitialization();
        await initialization;
        Assert.False(execution.IsCompleted);
        Assert.Throws<InvalidOperationException>(hold.RequireReleased);
        hold.Release();
        await execution;
        Assert.False(hold.IsHeld);
        hold.RequireReleased();
    }

    /// <summary>Manual launches cannot silently start capture/game services while the held root is being verified.</summary>
    [Fact]
    public void HeldManualLaunchIsEndpointOnlyUntilResume()
    {
        var binding = new UpgradeSessionBinding(3, 42, 1);
        Assert.Equal("controlEndpoint", binding.SelectStartupMode(null));
        Assert.Equal("controlEndpoint", binding.SelectStartupMode("controlEndpoint"));
        Assert.Throws<InvalidOperationException>(() => binding.SelectStartupMode("gameRuntime"));
        binding.MarkReleased();
        Assert.Null(binding.SelectStartupMode(null));
        Assert.Equal("gameRuntime", binding.SelectStartupMode("gameRuntime"));
    }
}
