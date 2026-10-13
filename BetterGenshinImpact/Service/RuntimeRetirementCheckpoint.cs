using System;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace BetterGenshinImpact.Service;

/// <summary>Each managed portable build must finish verified retirement before another publish.</summary>
internal static class RuntimeRetirementCheckpoint
{
    internal const string RelativePath = "User/ExternalControl/retention-checkpoint.json";

    internal static void Ensure(string appDirectory)
    {
        var app = new DirectoryInfo(Path.GetFullPath(appDirectory));
        if (app.Name != "BetterGI-English-win-x64" || app.Parent?.Parent?.Name != "artifacts" ||
            !Regex.IsMatch(app.Parent.Name, @"^release-r[0-9]+$")) return;
        for (var ancestor = app; ancestor is not null; ancestor = ancestor.Parent)
            if (ancestor.Attributes.HasFlag(FileAttributes.ReparsePoint)) throw new IOException("Linked runtime checkpoint path rejected");
        var assembly = Path.Combine(app.FullName, "BetterGI.dll");
        Core.Script.Dependence.CaptureStorageBudget.AssertOrdinaryPath(assembly);
        using var stream = File.OpenRead(assembly);
        var hash = Convert.ToHexString(SHA256.HashData(stream));
        var path = Path.Combine(app.FullName, RelativePath);
        if (File.Exists(path))
        {
            Core.Script.Dependence.CaptureStorageBudget.AssertOrdinaryPath(path);
            if (new FileInfo(path).Length > 65536) throw new IOException("Oversized runtime checkpoint");
            using var previous = JsonDocument.Parse(File.ReadAllText(path));
            if (previous.RootElement.TryGetProperty("dllSha256", out var value) &&
                previous.RootElement.TryGetProperty("appDirectory", out var previousDirectory) &&
                string.Equals(previousDirectory.GetString(), app.FullName, StringComparison.OrdinalIgnoreCase) &&
                string.Equals(value.GetString(), hash, StringComparison.OrdinalIgnoreCase)) return;
        }
        var directory = app.FullName;
        foreach (var part in new[] { "User", "ExternalControl" })
        {
            directory = Path.Combine(directory, part);
            if (Directory.Exists(directory) || File.Exists(directory))
                Core.Script.Dependence.CaptureStorageBudget.AssertOrdinaryPath(directory);
            Directory.CreateDirectory(directory);
            Core.Script.Dependence.CaptureStorageBudget.AssertOrdinaryPath(directory);
        }
        var temporary = path + "." + Environment.ProcessId + ".tmp";
        using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            JsonSerializer.Serialize(output, new { version = 1, appDirectory = app.FullName, dllSha256 = hash,
                state = "verification-required", createdAtUnixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() });
        File.Move(temporary, path, true);
    }
}
