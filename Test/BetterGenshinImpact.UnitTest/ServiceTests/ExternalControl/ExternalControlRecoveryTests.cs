using System.Security.Cryptography;
using System.Text.Json;
using BetterGenshinImpact.Service.ExternalControl;

namespace BetterGenshinImpact.UnitTest.ServiceTests.ExternalControl;

public sealed class ExternalControlRecoveryTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "BetterGI-recovery-" + Guid.NewGuid().ToString("N"));
    private string App => Path.Combine(_root, "artifacts", "release-r11", "BetterGI-English-win-x64");
    private string Control => Path.Combine(App, "User", "ExternalControl");
    private string ManifestPath => Path.Combine(App, ExternalControlRecovery.ManifestFileName);

    public ExternalControlRecoveryTests()
    {
        Directory.CreateDirectory(Path.Combine(Control));
        Directory.CreateDirectory(Path.Combine(_root, ".git"));
        File.WriteAllText(Path.Combine(App, "BetterGI.exe"), "test executable only - never launched");
        File.WriteAllText(Path.Combine(App, "BetterGI.dll"), "test assembly only");
        File.WriteAllText(Path.Combine(Control, "enable-quest-control.json"), "{\"version\":1,\"enabled\":true,\"allowAppRestart\":true}");
        WriteManifest();
    }

    private void WriteManifest(string? arguments = null, int version = 1, bool desktopClone = true,
        string? exeHash = null, string? dllHash = null, bool includeExtra = false,
        bool includeMissingHash = false, bool includeExtraHash = false)
    {
        var payload = new Dictionary<string, object?>
        {
            ["version"] = version,
            ["desktopClone"] = desktopClone,
            ["sha256"] = new Dictionary<string, string>
            {
                ["BetterGI.exe"] = exeHash ?? Hash(Path.Combine(App, "BetterGI.exe")),
                ["BetterGI.dll"] = dllHash ?? Hash(Path.Combine(App, "BetterGI.dll"))
            }
        };
        var hashes = (Dictionary<string, string>)payload["sha256"]!;
        if (includeMissingHash) hashes.Remove("BetterGI.dll");
        if (includeExtraHash) hashes["cmd.exe"] = Hash(Path.Combine(App, "BetterGI.exe"));
        if (arguments is not null) payload["arguments"] = arguments;
        if (includeExtra) payload["shell"] = "cmd.exe";
        File.WriteAllText(ManifestPath, JsonSerializer.Serialize(payload));
    }

    private static string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path)));

    [Fact]
    public void ValidPlanContainsOnlyFixedHostAndArgument()
    {
        var plan = ExternalControlRecovery.CreateValidatedRecoveryPlan(App);
        Assert.Equal(Path.Combine(App, "BetterGI.exe"), plan.ExecutablePath);
        Assert.Equal(App, plan.AppDirectory);
        Assert.Equal("--desktopClone", plan.Arguments);
        Assert.Equal(Hash(Path.Combine(App, "BetterGI.exe")), plan.ExeSha256);
        Assert.Equal(Hash(Path.Combine(App, "BetterGI.dll")), plan.DllSha256);
    }

    [Theory]
    [InlineData("--desktopClone --arbitrary")]
    [InlineData("cmd.exe /c whoami")]
    [InlineData("")]
    public void ManifestCannotSupplyAdditionalArguments(string arguments)
    {
        WriteManifest(arguments);
        Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.CreateValidatedRecoveryPlan(App));
    }

    [Theory]
    [InlineData("C:\\Windows\\System32")]
    [InlineData("\\\\server\\share\\artifacts\\release-r1\\BetterGI-English-win-x64")]
    [InlineData("C:\\workspace\\artifacts\\releases\\BetterGI-English-win-x64")]
    public void NonWorkspaceOrWrongReleasePathsAreRejected(string path)
        => Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.CreateValidatedRecoveryPlan(path));

    [Fact]
    public void HashMismatchIsRejected()
    {
        WriteManifest(exeHash: new string('0', 64));
        Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.CreateValidatedRecoveryPlan(App));
    }

    [Fact]
    public void InvalidVersionMissingHashAndUnknownManifestFieldsAreRejected()
    {
        WriteManifest(version: 2);
        Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.CreateValidatedRecoveryPlan(App));
        WriteManifest(dllHash: "bad");
        Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.CreateValidatedRecoveryPlan(App));
        WriteManifest(includeMissingHash: true);
        Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.CreateValidatedRecoveryPlan(App));
        WriteManifest(includeExtraHash: true);
        Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.CreateValidatedRecoveryPlan(App));
        WriteManifest(includeExtra: true);
        Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.CreateValidatedRecoveryPlan(App));
    }

    [Fact]
    public void RecoveryRequiresExplicitOptIn()
    {
        File.WriteAllText(Path.Combine(Control, "enable-quest-control.json"), "{\"version\":1,\"enabled\":true}");
        Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.CreateValidatedRecoveryPlan(App));
    }

    public void Dispose() => Directory.Delete(_root, recursive: true);
}
