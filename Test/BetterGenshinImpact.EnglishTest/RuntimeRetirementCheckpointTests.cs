using System.IO;
using System.Text.Json;
using BetterGenshinImpact.Service;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public sealed class RuntimeRetirementCheckpointTests
{
    [Fact]
    public void EveryNewBuildRequiresRetirementButSameBuildKeepsCompletedCheckpoint()
    {
        var root = Path.Combine(Path.GetTempPath(), "BetterGI-checkpoint-" + Guid.NewGuid().ToString("N"));
        var app = Path.Combine(root, "artifacts", "release-r16", "BetterGI-English-win-x64");
        Directory.CreateDirectory(app);
        try
        {
            var assembly = Path.Combine(app, "BetterGI.dll");
            var checkpoint = Path.Combine(app, RuntimeRetirementCheckpoint.RelativePath);
            File.WriteAllText(assembly, "first build");
            RuntimeRetirementCheckpoint.Ensure(app);
            using var first = JsonDocument.Parse(File.ReadAllText(checkpoint));
            Assert.Equal("verification-required", first.RootElement.GetProperty("state").GetString());
            File.WriteAllText(checkpoint, File.ReadAllText(checkpoint).Replace("verification-required", "completed"));
            RuntimeRetirementCheckpoint.Ensure(app);
            Assert.Contains("completed", File.ReadAllText(checkpoint));
            var copiedApp = Path.Combine(root, "artifacts", "release-r17", "BetterGI-English-win-x64");
            Directory.CreateDirectory(Path.Combine(copiedApp, "User", "ExternalControl"));
            File.Copy(assembly, Path.Combine(copiedApp, "BetterGI.dll"));
            var copiedCheckpoint = Path.Combine(copiedApp, RuntimeRetirementCheckpoint.RelativePath);
            File.Copy(checkpoint, copiedCheckpoint);
            RuntimeRetirementCheckpoint.Ensure(copiedApp);
            Assert.Contains("verification-required", File.ReadAllText(copiedCheckpoint));
            File.WriteAllText(assembly, "second build");
            RuntimeRetirementCheckpoint.Ensure(app);
            Assert.Contains("verification-required", File.ReadAllText(checkpoint));
        }
        finally { Directory.Delete(root, true); }
    }

    [Fact]
    public void OrdinaryDeveloperBuildDoesNotCreatePortableCheckpoint()
    {
        var root = Path.Combine(Path.GetTempPath(), "BetterGI-checkpoint-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            RuntimeRetirementCheckpoint.Ensure(root);
            Assert.Empty(Directory.GetFiles(root, "*", SearchOption.AllDirectories));
        }
        finally { Directory.Delete(root, true); }
    }
}
