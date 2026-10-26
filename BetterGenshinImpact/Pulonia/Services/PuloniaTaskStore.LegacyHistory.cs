using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Pulonia.Models;
using Newtonsoft.Json;

namespace BetterGenshinImpact.Pulonia.Services;

/// <summary>Separate diagnostic-only history access; no result is inserted into the current run service or scheduler.</summary>
public sealed partial class PuloniaTaskStore
{
    /// <summary>Bound one diagnostic listing without claiming a bound on managed-object overhead.</summary>
    public const int LegacyHistoryListByteLimit = 32 * 1024 * 1024;
    /// <summary>Bound files examined by one listing; additional files remain available through explicit reads.</summary>
    public const int LegacyHistoryListFileLimit = 128;
    /// <summary>Bound examined plan directories, including invalid and empty entries that contain no counted files.</summary>
    public const int LegacyHistoryListDirectoryLimit = 128;

    /// <summary>
    /// Read a schema-2-era file by exact historical plan ID and GUID-N filename. The distinct result cannot enter ResumeAsync.
    /// This reads no state, account, current plan, resources or checkpoint, and never writes a file.
    /// </summary>
    public async Task<PuloniaLegacyHistoryRecord?> LoadLegacyHistoryRecordAsync(string planId, string runId,
        CancellationToken ct = default)
    {
        PuloniaLegacyHistoryReader.ValidateLegacyId(planId);
        if (!Guid.TryParseExact(runId, "N", out var id) || id == Guid.Empty || id.ToString("N") != runId)
            throw new JsonSerializationException("legacy_history_filename_guid");
        var directory = Path.Combine(RootDirectory, "history", planId);
        RefuseLegacyReparsePoint(Path.Combine(RootDirectory, "history"));
        RefuseLegacyReparsePoint(directory);
        var path = Path.Combine(directory, runId + ".json");
        var bytes = await ReadLegacyHistoryBytesAsync(path, ct).ConfigureAwait(false);
        return bytes is null ? null : PuloniaLegacyHistoryReader.Read(bytes, planId, runId);
    }

    /// <summary>
    /// List only old envelopes, with visible per-file/limit failures. Current envelopes are left to the existing current reader.
    /// The bounded list retains original bytes for inspection; it does not populate executable state or migrate anything.
    /// </summary>
    public async Task<PuloniaTaskFileListResult<PuloniaLegacyHistoryRecord>> ListLegacyHistoryWithFailuresAsync(
        CancellationToken ct = default)
    {
        var root = Path.Combine(RootDirectory, "history");
        if (!Directory.Exists(root)) return PuloniaTaskFileListResult<PuloniaLegacyHistoryRecord>.Empty;
        RefuseLegacyReparsePoint(root);
        var records = new List<PuloniaLegacyHistoryRecord>();
        var failures = new List<PuloniaTaskFileLoadFailure>();
        long byteCount = 0;
        var fileCount = 0;
        var directoryCount = 0;
        // Only the actual history/<plan>/<run>.json layout is read, never arbitrary recursive descendants.
        foreach (var directory in Directory.EnumerateDirectories(root))
        {
            ct.ThrowIfCancellationRequested();
            // Count before validation: invalid and empty directories must not bypass the diagnostic-list bound.
            if (++directoryCount > LegacyHistoryListDirectoryLimit)
            {
                failures.Add(new PuloniaTaskFileLoadFailure(directory, null, "legacy_history_listing_directory_limit; remaining directories were not read"));
                return LegacyHistoryListResult(records, failures);
            }
            var planId = Path.GetFileName(directory);
            try
            {
                PuloniaLegacyHistoryReader.ValidateLegacyId(planId);
                RefuseLegacyReparsePoint(directory);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                failures.Add(new PuloniaTaskFileLoadFailure(directory, null, ex.Message));
                continue;
            }
            foreach (var path in Directory.EnumerateFiles(directory, "*.json", SearchOption.TopDirectoryOnly))
            {
                ct.ThrowIfCancellationRequested();
                if (++fileCount > LegacyHistoryListFileLimit)
                {
                    failures.Add(new PuloniaTaskFileLoadFailure(path, null, "legacy_history_listing_file_limit; remaining files were not read"));
                    return LegacyHistoryListResult(records, failures);
                }
                try
                {
                    var bytes = await ReadLegacyHistoryBytesAsync(path, ct, LegacyHistoryListByteLimit - byteCount).ConfigureAwait(false);
                    if (bytes is null) continue;
                    byteCount += bytes.Length;
                    if (!PuloniaLegacyHistoryReader.HasLegacyMarker(bytes)) continue;
                    records.Add(PuloniaLegacyHistoryReader.Read(bytes, planId, Path.GetFileNameWithoutExtension(path)));
                }
                catch (Exception ex) when (ex is not OperationCanceledException)
                {
                    failures.Add(new PuloniaTaskFileLoadFailure(path, Path.GetFileNameWithoutExtension(path), ex.Message));
                }
            }
        }
        return LegacyHistoryListResult(records, failures);
    }

    /// <summary>Order detached diagnostic records without adapting them into the current history type.</summary>
    private static PuloniaTaskFileListResult<PuloniaLegacyHistoryRecord> LegacyHistoryListResult(
        List<PuloniaLegacyHistoryRecord> records, List<PuloniaTaskFileLoadFailure> failures)
        => new(records.OrderByDescending(record => record.SubmittedAt).ToArray(), failures.AsReadOnly());

    /// <summary>Read one bounded file through one handle; atomic path replacement cannot mix the bytes and hash.</summary>
    private static async Task<byte[]?> ReadLegacyHistoryBytesAsync(string path, CancellationToken ct,
        long remainingBytes = PuloniaLegacyHistoryReader.MaxRecordBytes)
    {
        try
        {
            RefuseLegacyReparsePoint(path);
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read | FileShare.Delete,
                4096, FileOptions.Asynchronous | FileOptions.SequentialScan);
            var length = stream.Length;
            if (length <= 0 || length > PuloniaLegacyHistoryReader.MaxRecordBytes || length > remainingBytes)
                throw new JsonSerializationException("legacy_history_read_byte_limit; file remains unchanged");
            var bytes = new byte[checked((int)length)];
            await stream.ReadExactlyAsync(bytes.AsMemory(), ct).ConfigureAwait(false);
            return bytes;
        }
        catch (Exception ex) when (ex is FileNotFoundException or DirectoryNotFoundException)
        {
            return null;
        }
    }

    /// <summary>Do not follow known links out of the diagnostic history tree.</summary>
    private static void RefuseLegacyReparsePoint(string path)
    {
        if ((File.Exists(path) || Directory.Exists(path)) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            throw new JsonSerializationException("legacy_history_reparse_point");
    }
}
