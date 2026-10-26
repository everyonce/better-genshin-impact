using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;

namespace BetterGenshinImpact.Helpers;

/// <summary>One fixed, bounded startup binding for the existing approved launcher's unchanged arguments.</summary>
internal static class UpgradeStartupFile
{
    /// <summary>Only these package-local filenames participate; callers cannot select arbitrary files.</summary>
    internal const string PendingName = "root-upgrade-startup.json";
    internal const string ConsumedName = "root-upgrade-startup.consumed.json";
    internal const string CompletedName = "root-upgrade-startup.completed.json";
    /// <summary>Exact scalar schema, with duplicate and unknown fields refused.</summary>
    private static readonly string[] Fields = ["version", "nonce", "targetDirectory", "rootSessionId", "cloneSessionId",
        "gameProcessId", "gameStartedFileTime", "exeSha256", "dllSha256", "createdUtc", "expiresUtc"];

    /// <summary>Normal/child parsing stays unchanged; only an explicit package file opts a primary into the hold.</summary>
    internal static UpgradeSessionBinding? Consume(string directory, bool automatedClone, bool hasDirectBinding,
        Func<int> currentSession, DateTimeOffset now)
    {
        directory = Path.TrimEndingDirectorySeparator(Path.GetFullPath(directory));
        var pending = Path.Combine(directory, PendingName);
        var consumed = Path.Combine(directory, ConsumedName);
        var completed = Path.Combine(directory, CompletedName);
        var count = new[] { pending, consumed, completed }.Count(File.Exists);
        if (count == 0) return null;
        if (count != 1 || File.Exists(consumed))
            throw new InvalidOperationException("Upgrade startup is consumed or ambiguous; preserve the files and do not retry.");
        var path = File.Exists(completed) ? completed : pending;
        var bytes = Read(path);
        using var document = JsonDocument.Parse(bytes);
        var value = document.RootElement;
        var names = value.EnumerateObject().Select(x => x.Name).ToArray();
        if (names.Length != Fields.Length || names.Distinct(StringComparer.Ordinal).Count() != Fields.Length
            || Fields.Except(names, StringComparer.Ordinal).Any() || value.GetProperty("version").GetInt32() != 1
            || value.GetProperty("nonce").GetString() is not { Length: 32 } nonce || !Guid.TryParseExact(nonce, "N", out _)
            || !string.Equals(value.GetProperty("targetDirectory").GetString(), directory, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Upgrade startup schema or target is invalid.");
        foreach (var name in new[] { "exe", "dll" })
        {
            var binary = Path.Combine(directory, "BetterGI." + name);
            RejectLinks(binary);
            using var stream = new FileStream(binary, FileMode.Open, FileAccess.Read, FileShare.Read);
            if (value.GetProperty(name + "Sha256").GetString() != Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant())
                throw new InvalidDataException("Upgrade startup package hash changed.");
        }
        // A completed record permits later ordinary starts, but never another use of its old game identity.
        if (path == completed) return null;
        if (!automatedClone || hasDirectBinding || currentSession() != value.GetProperty("rootSessionId").GetInt32())
            throw new InvalidOperationException("Upgrade startup requires the original root session and fixed automated clone command.");
        var created = value.GetProperty("createdUtc").GetDateTimeOffset();
        var expires = value.GetProperty("expiresUtc").GetDateTimeOffset();
        if (created.Offset != TimeSpan.Zero || expires.Offset != TimeSpan.Zero || now < created || now >= expires
            || expires <= created || expires - created > TimeSpan.FromMinutes(5))
            throw new InvalidDataException("Upgrade startup is expired or has invalid bounds.");
        var binding = new UpgradeSessionBinding(value.GetProperty("cloneSessionId").GetInt32(),
            value.GetProperty("gameProcessId").GetInt32(), value.GetProperty("gameStartedFileTime").GetInt64());
        // Non-overwriting rename is the one-shot reservation. A failed later check stays consumed.
        File.Move(pending, consumed);
        if (!Read(consumed).AsSpan().SequenceEqual(bytes)) throw new InvalidDataException("Upgrade startup changed during consumption.");
        binding.RetainStartupFile(consumed, bytes);
        return binding;
    }

    /// <summary>Flush/verify the exact consumed record, then publish non-overwriting durable completion on explicit resume.</summary>
    internal static void Complete(string consumed, byte[] expected)
    {
        RejectLinks(consumed);
        using (var stream = new FileStream(consumed, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            if (stream.Length != expected.Length) throw new InvalidDataException("Consumed startup size changed.");
            var bytes = new byte[expected.Length];
            stream.ReadExactly(bytes);
            if (!bytes.AsSpan().SequenceEqual(expected)) throw new InvalidDataException("Consumed startup bytes changed.");
            stream.Flush(flushToDisk: true);
        }
        var completed = Path.Combine(Path.GetDirectoryName(consumed)!, CompletedName);
        File.Move(consumed, completed);
        if (!Read(completed).AsSpan().SequenceEqual(expected)) throw new InvalidDataException("Completion publication changed.");
    }

    /// <summary>Keep this scalar file bounded before allocating or parsing it.</summary>
    private static byte[] Read(string path)
    {
        RejectLinks(path);
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length is <= 0 or > 4096) throw new InvalidDataException("Upgrade startup exceeds its 4 KiB bound.");
        var bytes = new byte[(int)stream.Length];
        stream.ReadExactly(bytes);
        return bytes;
    }

    /// <summary>Do not follow a package/record redirected through a reparse point.</summary>
    private static void RejectLinks(string path)
    {
        for (string? current = Path.GetFullPath(path); current is not null; current = Path.GetDirectoryName(current))
            if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("Upgrade startup rejects reparse points.");
    }
}
