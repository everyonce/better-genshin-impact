using System;
using System.IO;
using System.Security.Cryptography;
using System.Text.RegularExpressions;

namespace BetterGenshinImpact.Core.Script.Dependence;

internal sealed class CaptureImageWriter
{
    private static readonly object Gate = new();

    internal static bool Applies(string root, string path) =>
        string.Equals(Path.GetFileName(Path.TrimEndingDirectorySeparator(root)), "ActOnePilot", StringComparison.OrdinalIgnoreCase) &&
        Path.GetRelativePath(root, path).Replace('\\', '/').StartsWith("observations/", StringComparison.OrdinalIgnoreCase);

    internal void Write(string root, string path, byte[] png, Func<long>? availableBytes = null)
    {
        root = Path.GetFullPath(root);
        path = Path.GetFullPath(path);
        var relative = Path.GetRelativePath(root, path).Replace('\\', '/');
        if (!Regex.IsMatch(relative, @"^observations/[A-Za-z0-9_-]+/frame-[0-9]+\.png$"))
            throw new IOException("Invalid immutable capture path.");
        lock (Gate)
        {
            var retention = new CaptureRetention(root);
            retention.Sweep(DateTime.UtcNow, png.LongLength, 1);
            var parent = Path.GetDirectoryName(path)!;
            CaptureStorageBudget.AssertOrdinaryPath(parent);
            CaptureStorageBudget.Check(Path.Combine(root, "observations"), png.LongLength, availableBytes);
            if (File.Exists(path)) throw new IOException("Capture evidence already exists; overwriting is forbidden.");
            var hash = Convert.ToHexString(SHA256.HashData(png));
            // Each frame retains its original path, metadata and exact PNG bytes.
            // Even identical captures need independent file identities: strict evidence
            // readers reject hard links. Logical storage quotas remain unchanged.
            using (var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read))
            {
                stream.Write(png);
            }
            retention.Register(path, png.LongLength, hash);
        }
    }
}
