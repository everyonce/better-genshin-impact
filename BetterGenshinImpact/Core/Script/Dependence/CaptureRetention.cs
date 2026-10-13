using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using System.Threading;

namespace BetterGenshinImpact.Core.Script.Dependence;

/// <summary>Retention for explicitly registered new captures; historical files are never adopted.</summary>
internal sealed class CaptureRetention(string root)
{
    internal const int LatestFrames = 256;
    internal const long RecentBytes = 512L * 1024 * 1024;
    internal const int PinnedFrames = 32;
    internal const long PinnedBytes = 64L * 1024 * 1024;
    private static readonly object Gate = new();
    private string Ledger => Path.Combine(root, "capture-retention.tsv");
    private sealed record Entry(string Path, long Bytes, long CreatedTicks, string Hash, bool Pinned, string MetadataHash);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFile(string path, uint access, uint share, IntPtr security, uint creation, uint attributes, IntPtr template);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetFileInformationByHandle(SafeFileHandle handle, int informationClass, ref Disposition value, uint size);
    [StructLayout(LayoutKind.Sequential)]
    private struct Disposition { [MarshalAs(UnmanagedType.Bool)] public bool Delete; }

    private List<Entry> Read()
    {
        if (!File.Exists(Ledger)) return [];
        CaptureStorageBudget.AssertOrdinaryPath(Ledger);
        if (new FileInfo(Ledger).Length > 2 * 1024 * 1024) throw new IOException("Capture retention ledger is too large");
        var entries = new List<Entry>();
        foreach (var line in File.ReadLines(Ledger))
        {
            var fields = line.Split('\t');
            if (fields.Length != 6 || !Regex.IsMatch(fields[0], @"^observations/[A-Za-z0-9_-]+/frame-[0-9]+\.png$") ||
                !long.TryParse(fields[1], out var size) || size < 0 || !long.TryParse(fields[2], out var ticks) ||
                !Regex.IsMatch(fields[3], "^[A-F0-9]{64}$") || fields[4] is not ("0" or "1") ||
                fields[5] != "" && !Regex.IsMatch(fields[5], "^[A-F0-9]{64}$"))
                throw new IOException("Invalid capture retention ledger; refusing cleanup");
            entries.Add(new Entry(fields[0], size, ticks, fields[3], fields[4] == "1", fields[5]));
        }
        return entries;
    }

    private void Save(List<Entry> entries)
    {
        if (entries.Count > 4096) throw new IOException("Capture retention entry limit exceeded");
        var temporary = Ledger + ".tmp";
        if (File.Exists(temporary)) CaptureStorageBudget.AssertOrdinaryPath(temporary);
        File.WriteAllLines(temporary, entries.Select(e => $"{e.Path}\t{e.Bytes}\t{e.CreatedTicks}\t{e.Hash}\t{(e.Pinned ? 1 : 0)}\t{e.MetadataHash}"));
        ReplaceLedger(temporary, Ledger);
    }

    internal static void ReplaceLedger(string temporary, string destination)
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

    private FileStream Lease()
    {
        CaptureStorageBudget.AssertOrdinaryPath(root);
        var path = Path.Combine(root, "capture-retention.lock");
        if (File.Exists(path)) CaptureStorageBudget.AssertOrdinaryPath(path);
        return new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
    }

    internal void Register(string path, long size, string hash)
    {
        lock (Gate)
        {
            using var lease = Lease();
            var entries = Read();
            var relative = Path.GetRelativePath(root, path).Replace('\\', '/');
            if (!Regex.IsMatch(relative, @"^observations/[A-Za-z0-9_-]+/frame-[0-9]+\.png$")) throw new IOException("Invalid managed capture path");
            if (entries.Any(e => e.Path == relative)) throw new IOException("Capture already registered");
            entries.Add(new Entry(relative, size, DateTime.UtcNow.Ticks, hash, false, ""));
            Save(entries);
        }
    }

    internal void RegisterMetadata(string path, string hash)
    {
        lock (Gate)
        {
            using var lease = Lease();
            var entries = Read();
            var relative = Path.ChangeExtension(Path.GetRelativePath(root, path), ".png").Replace('\\', '/');
            var index = entries.FindIndex(e => e.Path == relative);
            if (index < 0) return;
            entries[index] = entries[index] with { MetadataHash = hash };
            Save(entries);
        }
    }

    private static bool DeleteOwned(Entry entry, string path, string metadata)
    {
        var expected = new List<(string Path, string Hash)> { (path, entry.Hash) };
        if (File.Exists(metadata))
        {
            if (entry.MetadataHash.Length == 0) return false;
            expected.Add((metadata, entry.MetadataHash));
        }
        var streams = new List<FileStream>();
        try
        {
            foreach (var item in expected)
            {
                CaptureStorageBudget.AssertOrdinaryPath(item.Path);
                var handle = CreateFile(item.Path, 0x80000000 | 0x00010000, 0, IntPtr.Zero, 3, 0x80, IntPtr.Zero);
                if (handle.IsInvalid) { handle.Dispose(); return false; }
                var stream = new FileStream(handle, FileAccess.Read);
                streams.Add(stream);
                if (Convert.ToHexString(SHA256.HashData(stream)) != item.Hash) return false;
            }
            foreach (var stream in streams)
            {
                var disposition = new Disposition { Delete = true };
                if (!SetFileInformationByHandle(stream.SafeFileHandle, 4, ref disposition, (uint)Marshal.SizeOf<Disposition>())) return false;
            }
            return true;
        }
        finally { foreach (var stream in streams) stream.Dispose(); }
    }

    internal void Pin(string session, int frame)
    {
        if (!Regex.IsMatch(session, "^[A-Za-z0-9_-]+$") || frame < 0) throw new IOException("Invalid evidence pin");
        lock (Gate)
        {
            using var lease = Lease();
            var entries = Read();
            var relative = $"observations/{session}/frame-{frame:D4}.png";
            var index = entries.FindIndex(e => e.Path == relative);
            if (index < 0) return; // Unmanaged historical evidence remains untouched.
            entries[index] = entries[index] with { Pinned = true };
            BoundEvidence(entries);
            Save(entries);
        }
    }

    // Evidence is a bounded recent rollup, not a permanent exemption from retention.
    // Older evidence returns to the normal recent-frame policy before it can expire.
    private static void BoundEvidence(List<Entry> entries)
    {
        long bytes = 0;
        int count = 0;
        foreach (var entry in entries.Where(e => e.Pinned).OrderByDescending(e => e.CreatedTicks).ToArray())
        {
            if (count < PinnedFrames && bytes + entry.Bytes <= PinnedBytes)
            {
                count++;
                bytes += entry.Bytes;
            }
            else entries[entries.IndexOf(entry)] = entry with { Pinned = false };
        }
    }

    internal void Sweep(DateTime now, long pendingBytes = 0, int pendingFrames = 0)
    {
        lock (Gate)
        {
            using var lease = Lease();
            var entries = Read();
            BoundEvidence(entries);
            long bytes = 0;
            int count = 0;
            var remove = new List<Entry>();
            foreach (var entry in entries.Where(e => !e.Pinned).OrderByDescending(e => e.CreatedTicks))
            {
                bytes += entry.Bytes;
                count++;
                // Never remove the newest two frames, even after a long idle period.
                if (count > 2 && (count > LatestFrames - pendingFrames || bytes > RecentBytes - pendingBytes || now.Ticks - entry.CreatedTicks > TimeSpan.FromDays(1).Ticks))
                    remove.Add(entry);
            }
            foreach (var entry in remove)
            {
                var path = Path.Combine(root, entry.Path);
                var metadata = Path.ChangeExtension(path, ".json");
                if (!File.Exists(path)) { entries.Remove(entry); continue; }
                CaptureStorageBudget.AssertOrdinaryPath(path);
                // Refuse active/locked or changed data; remove only this writer's immutable bytes.
                try
                {
                    if (DeleteOwned(entry, path, metadata)) entries.Remove(entry);
                }
                catch (IOException) { /* Locked captures stay retained; the hard quota provides backpressure. */ }
                catch (UnauthorizedAccessException) { /* Never override file permissions. */ }
            }
            if (pendingFrames > 0)
            {
                // Include locked, externally changed and unregistered PNGs in admission.
                // Preserving such files must never silently expand the retention limit.
                long actualBytes = 0;
                int actualFrames = 0;
                foreach (var image in Directory.EnumerateFiles(Path.Combine(root, "observations"), "*.png", SearchOption.AllDirectories))
                {
                    CaptureStorageBudget.AssertOrdinaryPath(image);
                    actualBytes += new FileInfo(image).Length;
                    actualFrames++;
                }
                // A changed/locked old entry can survive the ordinary sweep. Do not
                // let that one entry prevent retiring other owned, unchanged frames
                // when admitting the next capture. Preserve pins and the newest two.
                var newest = entries.Where(e => !e.Pinned).OrderByDescending(e => e.CreatedTicks)
                    .Take(2).Select(e => e.Path).ToHashSet(StringComparer.OrdinalIgnoreCase);
                foreach (var entry in entries.Where(e => !e.Pinned && !newest.Contains(e.Path))
                             .OrderBy(e => e.CreatedTicks).ToArray())
                {
                    if (actualFrames + pendingFrames <= LatestFrames + PinnedFrames &&
                        actualBytes + pendingBytes <= RecentBytes + PinnedBytes) break;
                    var path = Path.Combine(root, entry.Path);
                    if (!File.Exists(path)) { entries.Remove(entry); continue; }
                    try
                    {
                        var length = new FileInfo(path).Length;
                        if (!DeleteOwned(entry, path, Path.ChangeExtension(path, ".json"))) continue;
                        entries.Remove(entry);
                        actualFrames--;
                        actualBytes -= length;
                    }
                    catch (IOException) { /* Preserve locked or changed evidence. */ }
                    catch (UnauthorizedAccessException) { /* Never override permissions. */ }
                }
                Save(entries);
                if (actualFrames + pendingFrames > LatestFrames + PinnedFrames || actualBytes + pendingBytes > RecentBytes + PinnedBytes)
                    throw new IOException("Capture retention is full; locked or unregistered evidence requires review");
            }
            else Save(entries);
        }
    }
}
