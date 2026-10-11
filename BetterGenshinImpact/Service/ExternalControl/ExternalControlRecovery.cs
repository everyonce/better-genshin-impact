using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Installs one fixed, on-demand recovery task for this verified portable release.</summary>
internal static class ExternalControlRecovery
{
    internal const string ManifestFileName = "Host-Launcher.json";
    internal const string TaskName = "BetterGI-Quest-RDP-Host";
    internal const string FixedArguments = "--desktopClone";

    private const int TaskActionExecute = 0;
    private const int TaskCreateOrUpdate = 6;
    private const int TaskLogonInteractiveToken = 3;
    private const int TaskRunLevelHighest = 1;
    private const int TaskMultipleInstancesParallel = 0;
    private const int TaskSessionId = 1;

    internal static RecoveryPlan CreateValidatedRecoveryPlan(string appDirectory)
    {
        if (string.IsNullOrWhiteSpace(appDirectory) || !Path.IsPathFullyQualified(appDirectory)
            || appDirectory.StartsWith(@"\\", StringComparison.Ordinal))
            throw new InvalidOperationException("Recovery requires a local absolute BetterGI directory.");

        var app = Path.TrimEndingDirectorySeparator(Path.GetFullPath(appDirectory));
        var release = Directory.GetParent(app);
        var artifacts = release?.Parent;
        if (!string.Equals(Path.GetFileName(app), "BetterGI-English-win-x64", StringComparison.OrdinalIgnoreCase)
            || release is null || !Regex.IsMatch(release.Name, @"^release-r[0-9]+$", RegexOptions.CultureInvariant)
            || artifacts is null || !string.Equals(artifacts.Name, "artifacts", StringComparison.OrdinalIgnoreCase)
            || artifacts.Parent is null
            || !(Directory.Exists(Path.Combine(artifacts.Parent.FullName, ".git"))
                 || File.Exists(Path.Combine(artifacts.Parent.FullName, ".git"))))
            throw new InvalidOperationException("Recovery directory must be artifacts/release-rN/BetterGI-English-win-x64.");

        // Every path component through the release must be a real directory, not a reparse point.
        for (var directory = new DirectoryInfo(app); directory is not null; directory = directory.Parent)
        {
            if (!directory.Exists || directory.Attributes.HasFlag(FileAttributes.ReparsePoint))
                throw new InvalidOperationException("Recovery directory is missing or contains a filesystem link.");
            if (string.Equals(directory.FullName, artifacts.Parent.FullName, StringComparison.OrdinalIgnoreCase)) break;
        }

        var optInPath = Path.Combine(app, "User", "ExternalControl", "enable-quest-control.json");
        EnsureNoLinkedAncestors(app, optInPath);
        if (!ExternalControlOptIn.TryReadAppRestart(optInPath))
            throw new InvalidOperationException("External control and app restart must both be enabled.");

        var manifestPath = Path.Combine(app, ManifestFileName);
        EnsureNoLinkedAncestors(app, manifestPath);
        var manifestInfo = new FileInfo(manifestPath);
        if (!manifestInfo.Exists || manifestInfo.Length is <= 0 or > 4096
            || manifestInfo.Attributes.HasFlag(FileAttributes.ReparsePoint))
            throw new InvalidOperationException("A bounded, local Host-Launcher.json manifest is required.");

        LauncherManifest manifest;
        try
        {
            manifest = JsonSerializer.Deserialize<LauncherManifest>(File.ReadAllBytes(manifestPath),
                new JsonSerializerOptions { UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow, MaxDepth = 4 })
                ?? throw new InvalidOperationException("Host-Launcher.json is empty.");
        }
        catch (JsonException exception)
        {
            throw new InvalidOperationException("Host-Launcher.json is invalid.", exception);
        }

        if (manifest.Version != 1 || !manifest.DesktopClone || manifest.Sha256?.Hashes is not { Count: 2 } hashes
            || !hashes.ContainsKey("BetterGI.exe") || !hashes.ContainsKey("BetterGI.dll"))
            throw new InvalidOperationException("Host-Launcher.json must declare version 1, desktopClone true, and exactly both BetterGI hashes.");

        var exe = Path.Combine(app, "BetterGI.exe");
        var dll = Path.Combine(app, "BetterGI.dll");
        var exeHash = HashFile(exe, hashes["BetterGI.exe"].GetString());
        var dllHash = HashFile(dll, hashes["BetterGI.dll"].GetString());
        return new RecoveryPlan(app, exe, FixedArguments, exeHash, dllHash);
    }

    internal static RecoveryInstallResult Install(RecoveryPlan plan)
    {
        ArgumentNullException.ThrowIfNull(plan);
        var verified = CreateValidatedRecoveryPlan(plan.AppDirectory);
        if (verified != plan)
            throw new InvalidOperationException("Recovery plan changed after validation; create a fresh plan.");

        var schedulerType = Type.GetTypeFromProgID("Schedule.Service")
            ?? throw new InvalidOperationException("Task Scheduler COM is unavailable.");
        string accountName;
        string accountSid;
        using (var identity = WindowsIdentity.GetCurrent())
        {
            accountName = identity.Name;
            accountSid = identity.User?.Value ?? throw new InvalidOperationException("Current Windows identity has no SID.");
        }

        object? schedulerObject = null, folderObject = null, definitionObject = null, actionObject = null, taskObject = null;
        object? registrationInfoObject = null, settingsObject = null, principalObject = null, actionsObject = null;
        try
        {
            schedulerObject = Activator.CreateInstance(schedulerType)
                ?? throw new InvalidOperationException("Could not create Task Scheduler COM object.");
            dynamic scheduler = schedulerObject;
            scheduler.Connect();
            folderObject = scheduler.GetFolder("\\");
            dynamic folder = folderObject;
            definitionObject = scheduler.NewTask(0);
            dynamic definition = definitionObject;
            registrationInfoObject = definition.RegistrationInfo;
            dynamic registrationInfo = registrationInfoObject;
            registrationInfo.Author = "BetterGI";
            registrationInfo.Description = "On-demand recovery for the verified BetterGI desktop clone in console session 1.";
            settingsObject = definition.Settings;
            dynamic settings = settingsObject;
            settings.Enabled = true;
            settings.AllowDemandStart = true;
            settings.MultipleInstances = TaskMultipleInstancesParallel;
            settings.ExecutionTimeLimit = "PT0S";
            settings.DisallowStartIfOnBatteries = false;
            settings.StopIfGoingOnBatteries = false;
            principalObject = definition.Principal;
            dynamic principal = principalObject;
            principal.UserId = accountName;
            principal.LogonType = TaskLogonInteractiveToken;
            principal.RunLevel = TaskRunLevelHighest;
            actionsObject = definition.Actions;
            dynamic actions = actionsObject;
            actionObject = actions.Create(TaskActionExecute);
            dynamic action = actionObject;
            action.Path = verified.ExecutablePath;
            action.Arguments = FixedArguments;
            action.WorkingDirectory = verified.AppDirectory;

            taskObject = folder.RegisterTaskDefinition(TaskName, definition, TaskCreateOrUpdate,
                accountName, null, TaskLogonInteractiveToken, null);
            VerifyRegisteredTask(taskObject, verified, accountSid);

            return new RecoveryInstallResult(TaskName, accountName, TaskSessionId, verified.ExecutablePath, FixedArguments,
                verified.ExeSha256, verified.DllSha256);
        }
        finally
        {
            ReleaseComObject(principalObject);
            ReleaseComObject(settingsObject);
            ReleaseComObject(registrationInfoObject);
            ReleaseComObject(actionsObject);
            ReleaseComObject(actionObject);
            ReleaseComObject(taskObject);
            ReleaseComObject(definitionObject);
            ReleaseComObject(folderObject);
            ReleaseComObject(schedulerObject);
        }
    }

    /// <summary>Runs the already-installed fixed task in console session 1 after full task and host validation.</summary>
    internal static void ValidateInstalled(RecoveryPlan plan)
    {
        ArgumentNullException.ThrowIfNull(plan);
        var verified = CreateValidatedRecoveryPlan(plan.AppDirectory);
        if (verified != plan)
            throw new InvalidOperationException("Recovery plan changed after validation; create a fresh plan.");

        var accountSid = GetCurrentSid();

        var schedulerType = Type.GetTypeFromProgID("Schedule.Service")
            ?? throw new InvalidOperationException("Task Scheduler COM is unavailable.");
        object? schedulerObject = null, folderObject = null, taskObject = null;
        try
        {
            schedulerObject = Activator.CreateInstance(schedulerType)
                ?? throw new InvalidOperationException("Could not create Task Scheduler COM object.");
            dynamic scheduler = schedulerObject;
            scheduler.Connect();
            folderObject = scheduler.GetFolder("\\");
            dynamic folder = folderObject;
            taskObject = folder.GetTask(TaskName);
            VerifyRegisteredTask(taskObject, verified, accountSid);
        }
        finally
        {
            ReleaseComObject(taskObject);
            ReleaseComObject(folderObject);
            ReleaseComObject(schedulerObject);
        }
    }

    internal static RecoveryRunResult RunHost(RecoveryPlan plan)
    {
        ArgumentNullException.ThrowIfNull(plan);
        var verified = CreateValidatedRecoveryPlan(plan.AppDirectory);
        if (verified != plan)
            throw new InvalidOperationException("Recovery plan changed after validation; create a fresh plan.");

        var schedulerType = Type.GetTypeFromProgID("Schedule.Service")
            ?? throw new InvalidOperationException("Task Scheduler COM is unavailable.");
        object? schedulerObject = null, folderObject = null, taskObject = null, runningTaskObject = null;
        try
        {
            schedulerObject = Activator.CreateInstance(schedulerType)
                ?? throw new InvalidOperationException("Could not create Task Scheduler COM object.");
            dynamic scheduler = schedulerObject;
            scheduler.Connect();
            folderObject = scheduler.GetFolder("\\");
            dynamic folder = folderObject;
            taskObject = folder.GetTask(TaskName);
            VerifyRegisteredTask(taskObject, verified, GetCurrentSid());
            dynamic task = taskObject;
            runningTaskObject = task.RunEx(null, 0x4, TaskSessionId, null);
            if (runningTaskObject is null)
                throw new InvalidOperationException("Task Scheduler did not return a running recovery instance.");
            return new RecoveryRunResult(TaskName, TaskSessionId);
        }
        finally
        {
            ReleaseComObject(runningTaskObject);
            ReleaseComObject(taskObject);
            ReleaseComObject(folderObject);
            ReleaseComObject(schedulerObject);
        }
    }

    private static void VerifyRegisteredTask(object taskObject, RecoveryPlan plan, string expectedSid)
    {
        object? definitionObject = null, actionCollectionObject = null, actionObject = null;
        object? principalObject = null, settingsObject = null, triggersObject = null;
        try
        {
            dynamic task = taskObject;
            definitionObject = task.Definition;
            dynamic definition = definitionObject;
            actionCollectionObject = definition.Actions;
            dynamic actionCollection = actionCollectionObject;
            if ((int)actionCollection.Count != 1)
                throw new InvalidOperationException("Recovery task must have exactly one action.");
            actionObject = actionCollection.Item(1);
            dynamic action = actionObject;
            principalObject = definition.Principal;
            dynamic principal = principalObject;
            settingsObject = definition.Settings;
            dynamic settings = settingsObject;
            triggersObject = definition.Triggers;
            dynamic triggers = triggersObject;

            var actualSid = ResolveSid((string)principal.UserId);
            if (!string.Equals((string)action.Path, plan.ExecutablePath, StringComparison.OrdinalIgnoreCase)
                || !string.Equals((string)action.Arguments, FixedArguments, StringComparison.Ordinal)
                || !string.Equals((string)action.WorkingDirectory, plan.AppDirectory, StringComparison.OrdinalIgnoreCase)
                || (int)action.Type != TaskActionExecute
                || !string.Equals(actualSid, expectedSid, StringComparison.OrdinalIgnoreCase)
                || (int)principal.LogonType != TaskLogonInteractiveToken
                || (int)principal.RunLevel != TaskRunLevelHighest
                || !(bool)settings.Enabled || !(bool)settings.AllowDemandStart
                || !string.Equals((string)settings.ExecutionTimeLimit, "PT0S", StringComparison.OrdinalIgnoreCase)
                || (int)settings.MultipleInstances != TaskMultipleInstancesParallel
                || (int)triggers.Count != 0)
                throw new InvalidOperationException("Installed recovery task does not match the validated host, identity, or on-demand settings.");
        }
        finally
        {
            ReleaseComObject(triggersObject);
            ReleaseComObject(settingsObject);
            ReleaseComObject(principalObject);
            ReleaseComObject(actionObject);
            ReleaseComObject(actionCollectionObject);
            ReleaseComObject(definitionObject);
        }
    }

    private static string ResolveSid(string userId)
    {
        var identity = userId.StartsWith("S-1-", StringComparison.OrdinalIgnoreCase)
            ? new SecurityIdentifier(userId)
            : (SecurityIdentifier)new NTAccount(userId).Translate(typeof(SecurityIdentifier));
        return identity.Value;
    }

    private static string GetCurrentSid()
    {
        using var identity = WindowsIdentity.GetCurrent();
        return identity.User?.Value ?? throw new InvalidOperationException("Current Windows identity has no SID.");
    }

    private static string HashFile(string path, string? expected)
    {
        if (expected is null || !Regex.IsMatch(expected, "^[A-Fa-f0-9]{64}$", RegexOptions.CultureInvariant))
            throw new InvalidOperationException("Manifest must declare executable and assembly SHA256 hashes.");
        var info = new FileInfo(path);
        if (!info.Exists || info.Attributes.HasFlag(FileAttributes.ReparsePoint))
            throw new InvalidOperationException("Recovery executable or assembly is missing or linked.");
        using var stream = File.OpenRead(path);
        var actual = Convert.ToHexString(SHA256.HashData(stream));
        if (!string.Equals(actual, expected, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Recovery file hash does not match Host-Launcher.json.");
        return actual;
    }

    private static void EnsureNoLinkedAncestors(string trustedRoot, string path)
    {
        var root = Path.GetFullPath(trustedRoot);
        var current = Path.GetFullPath(path);
        while (current.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
        {
            if (File.Exists(current))
            {
                if (File.GetAttributes(current).HasFlag(FileAttributes.ReparsePoint))
                    throw new InvalidOperationException("Recovery configuration file is linked.");
            }
            else if (Directory.Exists(current) && File.GetAttributes(current).HasFlag(FileAttributes.ReparsePoint))
                throw new InvalidOperationException("Recovery configuration directory is linked.");
            if (string.Equals(current, root, StringComparison.OrdinalIgnoreCase)) break;
            var parent = Path.GetDirectoryName(current);
            if (parent is null) break;
            current = parent;
        }
    }

    private static void ReleaseComObject(object? value)
    {
        if (value is not null && Marshal.IsComObject(value)) Marshal.FinalReleaseComObject(value);
    }

    internal sealed record RecoveryPlan(string AppDirectory, string ExecutablePath, string Arguments, string ExeSha256, string DllSha256);
    internal sealed record RecoveryInstallResult(string TaskName, string AccountName, int ConsoleSessionId,
        string ExecutablePath, string Arguments, string ExeSha256, string DllSha256);
    internal sealed record RecoveryRunResult(string TaskName, int ConsoleSessionId);

    private sealed record LauncherManifest
    {
        [JsonPropertyName("version")] public int Version { get; init; }
        [JsonPropertyName("desktopClone")] public bool DesktopClone { get; init; }
        [JsonPropertyName("sha256")] public HashManifest? Sha256 { get; init; }
    }

    private sealed record HashManifest
    {
        [JsonExtensionData] public Dictionary<string, JsonElement>? Hashes { get; init; }
    }
}
