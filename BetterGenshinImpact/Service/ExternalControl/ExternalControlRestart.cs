using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Validates one explicitly staged portable BetterGI replacement; never launches a shell.</summary>
internal static class ExternalControlRestart
{
    internal const string ManifestPath = "User/ExternalControl/pending-restart.json";

    /// <summary>Validate optional request-bound pins before constructing one immutable launch description.</summary>
    internal static ProcessStartInfo Prepare(string currentDirectory, int currentProcessId, bool automationMode = false,
        ExternalControlIdleRestart? expected = null)
    {
        if (currentProcessId <= 0) throw new InvalidOperationException("Invalid source process.");
        var current = Path.TrimEndingDirectorySeparator(Path.GetFullPath(currentDirectory));
        var manifestFile = Path.Combine(current, ManifestPath);
        var info = new FileInfo(manifestFile);
        if (!info.Exists || info.Length is <= 0 or > 4096)
            throw new InvalidOperationException("A bounded pending-restart.json manifest is required.");
        RestartManifest manifest;
        try
        {
            manifest = JsonSerializer.Deserialize<RestartManifest>(File.ReadAllBytes(manifestFile),
                new JsonSerializerOptions { UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow, MaxDepth = 4 })
                ?? throw new InvalidOperationException("Restart manifest is empty.");
        }
        catch (JsonException exception)
        {
            throw new InvalidOperationException("Restart manifest is invalid.", exception);
        }
        if (manifest.Version != 1 || string.IsNullOrWhiteSpace(manifest.TargetDirectory)
            || !Path.IsPathFullyQualified(manifest.TargetDirectory) || manifest.TargetDirectory.StartsWith(@"\\"))
            throw new InvalidOperationException("Restart requires a local absolute target directory and manifest version 1.");

        var target = Path.TrimEndingDirectorySeparator(Path.GetFullPath(manifest.TargetDirectory));
        if (expected is not null && (!IsValidExpectation(expected)
            || !string.Equals(target, Path.TrimEndingDirectorySeparator(Path.GetFullPath(expected.TargetDirectory!)), StringComparison.OrdinalIgnoreCase)
            || !string.Equals(manifest.ExeSha256, expected.ExeSha256, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(manifest.DllSha256, expected.DllSha256, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException("The staged restart manifest does not match the request-bound target.");
        var currentRelease = Directory.GetParent(current)
            ?? throw new InvalidOperationException("Current installation has no release directory.");
        var artifactRoot = currentRelease.Parent
            ?? throw new InvalidOperationException("Current installation has no staging root.");
        var targetRelease = Directory.GetParent(target);
        if (!string.Equals(Path.GetFileName(current), "BetterGI-English-win-x64", StringComparison.OrdinalIgnoreCase)
            || !Regex.IsMatch(currentRelease.Name, @"^release-r[0-9]+$", RegexOptions.CultureInvariant)
            || !string.Equals(Path.GetFileName(target), "BetterGI-English-win-x64", StringComparison.OrdinalIgnoreCase)
            || targetRelease?.Parent is null
            || !Regex.IsMatch(targetRelease.Name, @"^release-r[0-9]+$", RegexOptions.CultureInvariant)
            || !string.Equals(targetRelease.Parent.FullName, artifactRoot.FullName, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Restart target must be this installation or a sibling numbered portable release.");

        // Resolve no links: the target must stay in the explicitly selected local staging tree.
        for (var directory = new DirectoryInfo(target); directory is not null; directory = directory.Parent)
        {
            if (!directory.Exists || directory.Attributes.HasFlag(FileAttributes.ReparsePoint))
                throw new InvalidOperationException("Restart target directory is missing or contains a filesystem link.");
        }
        VerifyFile(Path.Combine(target, "BetterGI.exe"), manifest.ExeSha256);
        VerifyFile(Path.Combine(target, "BetterGI.dll"), manifest.DllSha256);
        if (!ExternalControlOptIn.TryReadAppRestart(Path.Combine(target, "User/ExternalControl/enable-quest-control.json")))
            throw new InvalidOperationException("The replacement has not enabled external quest control.");

        var start = new ProcessStartInfo(Path.Combine(target, "BetterGI.exe"))
        {
            UseShellExecute = false,
            WorkingDirectory = target,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden
        };
        start.ArgumentList.Add("--instance");
        start.ArgumentList.Add("childsession");
        start.ArgumentList.Add("--restart-from-pid");
        start.ArgumentList.Add(currentProcessId.ToString(System.Globalization.CultureInfo.InvariantCulture));
        if (automationMode)
        {
            // The child reattaches its existing game after the old owner releases input.
            start.ArgumentList.Add("--automation");
            start.ArgumentList.Add("start");
        }
        return start;
    }

    /// <summary>Validate the small optional restart contract without reading configuration or launching a process.</summary>
    internal static bool IsValidExpectation(ExternalControlIdleRestart expected) =>
        expected.Version == 1 && !string.IsNullOrWhiteSpace(expected.TargetDirectory)
        && Path.IsPathFullyQualified(expected.TargetDirectory) && !expected.TargetDirectory.StartsWith(@"\\")
        && !expected.TargetDirectory.Contains('\0')
        && expected.ExeSha256 is not null && Regex.IsMatch(expected.ExeSha256, "^[A-Fa-f0-9]{64}$", RegexOptions.CultureInvariant)
        && expected.DllSha256 is not null && Regex.IsMatch(expected.DllSha256, "^[A-Fa-f0-9]{64}$", RegexOptions.CultureInvariant);

    private static void VerifyFile(string path, string? expectedHash)
    {
        if (expectedHash is null || !Regex.IsMatch(expectedHash, "^[A-Fa-f0-9]{64}$", RegexOptions.CultureInvariant))
            throw new InvalidOperationException("Both executable and assembly SHA256 values are required.");
        var info = new FileInfo(path);
        if (!info.Exists || info.Attributes.HasFlag(FileAttributes.ReparsePoint))
            throw new InvalidOperationException("Restart executable or assembly is missing or linked.");
        using var stream = File.OpenRead(path);
        if (!string.Equals(Convert.ToHexString(SHA256.HashData(stream)), expectedHash, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Replacement hash does not match the staged manifest.");
    }

    private sealed record RestartManifest
    {
        [JsonPropertyName("version")] public int Version { get; init; }
        [JsonPropertyName("targetDirectory")] public string? TargetDirectory { get; init; }
        [JsonPropertyName("exeSha256")] public string? ExeSha256 { get; init; }
        [JsonPropertyName("dllSha256")] public string? DllSha256 { get; init; }
    }
}
