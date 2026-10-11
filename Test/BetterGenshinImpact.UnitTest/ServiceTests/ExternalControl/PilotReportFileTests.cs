using BetterGenshinImpact.Core.Script.Dependence;

namespace BetterGenshinImpact.UnitTest.ServiceTests.ExternalControl;

public sealed class PilotReportFileTests
{
    [Fact]
    public void ScriptFileSandboxSupportsAppendOnlyJsonlReports()
    {
        var root = Path.Combine(Path.GetTempPath(), "BetterGI-report-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var file = new LimitedFile(root);
            Assert.True(file.WriteTextSync("reports/session.jsonl", "{\"status\":\"started\"}\n", true));
            Assert.True(file.WriteTextSync("reports/session.jsonl", "{\"status\":\"completed\"}\n", true));
            Assert.Equal(new[] { "{\"status\":\"started\"}", "{\"status\":\"completed\"}" },
                File.ReadAllLines(Path.Combine(root, "reports", "session.jsonl")));
            Assert.False(file.WriteTextSync("reports/command.ps1", "Write-Output denied"));
            Assert.False(File.Exists(Path.Combine(root, "reports", "command.ps1")));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }
}
