using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.RegularExpressions;

namespace BetterGenshinImpact.Core.Script.Dependence;

internal sealed class CaptureImageWriter
{
    private static readonly object Gate = new();
    private string? _lastHash;
    private string? _lastPath;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CreateHardLink(string newName, string existingName, IntPtr reserved);

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
            // Each frame retains its original path and metadata. Exact consecutive PNGs
            // share immutable NTFS data; changed and transition frames keep their own bytes.
            // Logical sizes still count toward the quota, even when physical bytes are shared.
            bool previousMatches = false;
            if (_lastHash == hash && _lastPath != null && File.Exists(_lastPath))
            {
                CaptureStorageBudget.AssertOrdinaryPath(_lastPath);
                using var previous = File.OpenRead(_lastPath);
                previousMatches = Convert.ToHexString(SHA256.HashData(previous)) == hash;
            }
            if (!previousMatches || _lastPath == null ||
                !OperatingSystem.IsWindows() || !CreateHardLink(path, _lastPath, IntPtr.Zero))
            {
                using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
                stream.Write(png);
            }
            _lastHash = hash;
            _lastPath = path;
            retention.Register(path, png.LongLength, hash);
        }
    }
}
