using System;
using System.IO;

namespace BetterGenshinImpact.Core.Script.Dependence;

/// <summary>Non-destructive admission control for ActOnePilot evidence. Never prunes user data.</summary>
internal static class CaptureStorageBudget
{
    internal const long MaxBytes = 1024L * 1024 * 1024;
    internal const int MaxFiles = 4096;
    internal const long MinimumFreeBytes = 2L * 1024 * 1024 * 1024;
    internal const long FrameReserveBytes = 16L * 1024 * 1024;

    internal static void Check(string root, long pendingBytes, Func<long>? availableBytes = null, long maxBytes = MaxBytes)
    {
        root = Path.GetFullPath(root);
        long bytes = 0;
        int count = 0;
        if (Directory.Exists(root))
        {
            AssertOrdinaryPath(root);
            // Enumerate explicitly so reparse-point directories are rejected before descent.
            void Visit(string directory)
            {
                // On Windows the directory enumeration supplies attributes and length together.
                // A file can be renamed immediately afterwards; its enumerated size still counts.
                foreach (var entry in new DirectoryInfo(directory).EnumerateFileSystemInfos())
                {
                    if ((entry.Attributes & FileAttributes.ReparsePoint) != 0)
                        throw new IOException("Capture evidence must not traverse a reparse point.");
                    if (entry is DirectoryInfo child)
                    {
                        try
                        {
                            AssertOrdinaryPath(child.FullName);
                            Visit(child.FullName);
                        }
                        catch (FileNotFoundException) { /* Removed between enumeration and descent. */ }
                        catch (DirectoryNotFoundException) { /* Directory was concurrently retired. */ }
                    }
                    else
                    {
                        bytes = checked(bytes + ((FileInfo)entry).Length);
                        if (++count >= MaxFiles || bytes > maxBytes - pendingBytes)
                            throw new IOException("Capture storage limit reached; archive reviewed evidence before restarting.");
                    }
                }
            }
            Visit(root);
        }
        var free = availableBytes?.Invoke() ?? new DriveInfo(Path.GetPathRoot(root)!).AvailableFreeSpace;
        CheckUsage(bytes, count, pendingBytes, free, maxBytes);
    }

    internal static void CheckUsage(long bytes, int count, long pendingBytes, long free, long maxBytes = MaxBytes)
    {
        // Reserve room for the companion observation JSON as well as the PNG.
        if (count >= MaxFiles - 1 || pendingBytes < 0 || pendingBytes > FrameReserveBytes ||
            bytes > maxBytes - pendingBytes - 128 * 1024)
            throw new IOException("Capture storage byte or file budget exceeded.");
        if (free < MinimumFreeBytes + pendingBytes + 128 * 1024)
            throw new IOException("Capture storage backpressure: at least 2 GiB free plus the next frame is required.");
    }

    internal static void AssertOrdinaryPath(string path)
    {
        for (var current = new FileInfo(Path.GetFullPath(path)); current != null;
             current = current.Directory == null ? null : new FileInfo(current.Directory.FullName))
        {
            if ((File.GetAttributes(current.FullName) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Capture evidence must not traverse a reparse point.");
        }
    }
}
