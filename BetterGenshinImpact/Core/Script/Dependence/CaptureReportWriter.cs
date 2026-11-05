using System;
using System.IO;
using System.Text;
using System.Threading;

namespace BetterGenshinImpact.Core.Script.Dependence;

/// <summary>Publishes one complete replayable JSON snapshot. Append-only event streams use a separate path.</summary>
internal static class CaptureReportWriter
{
    /// <summary>Retry only publication of the already-written bytes while a Windows reader temporarily holds the target.</summary>
    internal static void Replace(string path, string content)
    {
        var directory = Path.GetDirectoryName(path) ?? throw new IOException("Missing report directory.");
        CaptureStorageBudget.AssertOrdinaryPath(directory);
        if (File.Exists(path)) CaptureStorageBudget.AssertOrdinaryPath(path);
        var pending = Path.Combine(directory, $".bgi-report-{Guid.NewGuid():N}.tmp");
        try
        {
            using (var stream = new FileStream(pending, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                stream.Write(Encoding.UTF8.GetBytes(content));
                stream.Flush(flushToDisk: true);
            }
            PublishPending(pending, path);
        }
        finally { File.Delete(pending); }
    }

    /// <summary>Publish the same prepared bytes, allowing brief sharing conflicts without repeating any input or append.</summary>
    internal static void PublishPending(string temporary, string destination)
    {
        // Indexers/scanners can briefly deny delete-sharing during atomic replacement.
        // Retry the same operation briefly; never change ACLs or ignore persistent denial.
        for (var attempt = 0; ; attempt++)
        {
            try { File.Move(temporary, destination, true); return; }
            catch (Exception error) when (attempt < 5 &&
                (error is IOException || error is UnauthorizedAccessException) &&
                (error.HResult & 0xffff) is 5 or 32 or 33)
            {
                Thread.Sleep(50);
            }
        }
    }
}
