using BetterGenshinImpact.Service;
using Serilog;
using Xunit;
using System.IO;

namespace BetterGenshinImpact.EnglishTest;

public class RuntimeLogRetentionTests
{
    [Fact]
    public void SharedWritersRotateAndRetainOnlyLatestSegments()
    {
        var root = Path.Combine(Path.GetTempPath(), "BetterGI-log-retention-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var path = Path.Combine(root, "test.log");
            using (var first = RuntimeLogRetention.Configure(new LoggerConfiguration(), path, 1024, 3).CreateLogger())
            using (var second = RuntimeLogRetention.Configure(new LoggerConfiguration(), path, 1024, 3).CreateLogger())
            {
                for (var i = 0; i < 100; i++)
                {
                    first.Information("first-{Index}: {Payload}", i, new string('a', 256));
                    second.Information("second-{Index}: {Payload}", i, new string('b', 256));
                }
                second.Information("LAST-RETENTION-RECORD");
            }
            var files = Directory.GetFiles(root);
            Assert.InRange(files.Length, 1, 3);
            Assert.Contains("LAST-RETENTION-RECORD", string.Join("", files.Select(File.ReadAllText)));
            Assert.DoesNotContain("first-0:", string.Join("", files.Select(File.ReadAllText)));
        }
        finally { Directory.Delete(root, true); }
    }
}
