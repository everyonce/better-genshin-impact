using System.Security.Cryptography;
using System.Text.Json;
using BetterGenshinImpact.Service.ExternalControl;

namespace BetterGenshinImpact.UnitTest.ServiceTests.ExternalControl;

public sealed class ExternalControlRestartTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "BetterGI-restart-" + Guid.NewGuid().ToString("N"));
    private string Current => Path.Combine(_root, "release-r9", "BetterGI-English-win-x64");
    private string Target => Path.Combine(_root, "release-r10", "BetterGI-English-win-x64");

    public ExternalControlRestartTests()
    {
        Directory.CreateDirectory(Path.Combine(Current, "User", "ExternalControl"));
        Directory.CreateDirectory(Path.Combine(Target, "User", "ExternalControl"));
        File.WriteAllText(Path.Combine(Target, "BetterGI.exe"), "test executable only - never launched");
        File.WriteAllText(Path.Combine(Target, "BetterGI.dll"), "test assembly only");
        File.WriteAllText(Path.Combine(Target, "User", "ExternalControl", "enable-quest-control.json"), "{\"version\":1,\"enabled\":true,\"allowAppRestart\":true}");
        WriteManifest(Target);
    }

    private void WriteManifest(string target, string? dllHash = null)
    {
        File.WriteAllText(Path.Combine(Current, ExternalControlRestart.ManifestPath), JsonSerializer.Serialize(new
        {
            version = 1,
            targetDirectory = target,
            exeSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(Target, "BetterGI.exe")))),
            dllSha256 = dllHash ?? Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(Target, "BetterGI.dll"))))
        }));
    }

    [Fact]
    public void ValidatedSiblingStartsOnlyBetterGiChildAndWaitsForOldPid()
    {
        var start = ExternalControlRestart.Prepare(Current, 1234);
        Assert.Equal(Path.Combine(Target, "BetterGI.exe"), start.FileName);
        Assert.Equal(Target, start.WorkingDirectory);
        Assert.False(start.UseShellExecute);
        Assert.Equal(new[] { "--instance", "childsession", "--restart-from-pid", "1234" }, start.ArgumentList);
    }

    [Fact]
    public void ModifiedReplacementAssemblyIsRejected()
    {
        File.AppendAllText(Path.Combine(Target, "BetterGI.dll"), " changed");
        Assert.Throws<InvalidOperationException>(() => ExternalControlRestart.Prepare(Current, 1234));
    }

    [Theory]
    [InlineData("../elsewhere")]
    [InlineData("C:\\Windows\\System32")]
    [InlineData("\\\\server\\share\\BetterGI-English-win-x64")]
    public void ArbitraryTargetsAreRejected(string target)
    {
        WriteManifest(target);
        Assert.Throws<InvalidOperationException>(() => ExternalControlRestart.Prepare(Current, 1234));
    }

    [Fact]
    public void ReplacementMustHaveExternalControlEnabled()
    {
        File.WriteAllText(Path.Combine(Target, "User", "ExternalControl", "enable-quest-control.json"), "{\"version\":1,\"enabled\":false}");
        Assert.Throws<InvalidOperationException>(() => ExternalControlRestart.Prepare(Current, 1234));
    }

    public void Dispose() => Directory.Delete(_root, recursive: true);
}
