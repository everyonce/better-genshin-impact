using System;
using System.Globalization;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.Service.Instance;
using BetterGenshinImpact.Service.Interface;

namespace BetterGenshinImpact.Service.ChildSession;

internal static class ChildSessionProcessLauncher
{
    private const int TaskActionExecute = 0;
    private const int TaskCreate = 2;
    private const int TaskLogonInteractiveToken = 3;
    private const int TaskRunLevelHighest = 1;
    /// <summary>Ordinary automation commands always use the user's standard interactive token.</summary>
    private const int TaskRunLevelLeastPrivilege = 0;
    private const int TaskRunUseSessionId = 0x4;

    internal static Task LaunchBetterGiAsync(
        uint childSessionId, string? startupMode = null, CancellationToken cancellationToken = default)
    {
        // 分身实例共用同一个 config.json，启动前先写入防抖窗口内尚未落盘的配置改动
        App.GetService<IConfigService>()?.Flush();

        cancellationToken.ThrowIfCancellationRequested();
        var startInfo = CreateBetterGiStartInfo(startupMode);
        return LaunchElevatedAsync(
            childSessionId,
            startInfo.ExecutablePath,
            startInfo.Arguments,
            startInfo.WorkingDirectory, cancellationToken);
    }

    internal static Task LaunchElevatedAsync(uint childSessionId, string executablePath)
    {
        var fullPath = ValidateExecutablePath(executablePath);
        return LaunchElevatedAsync(
            childSessionId,
            fullPath,
            string.Empty,
            Path.GetDirectoryName(fullPath) ?? AppContext.BaseDirectory);
    }

    /// <summary>Launch an ordinary command in the verified child session without elevation or a shell.</summary>
    internal static Task LaunchStandardAsync(uint childSessionId, string executablePath,
        IReadOnlyList<string> arguments, string workingDirectory)
    {
        var fullPath = ValidateExecutablePath(executablePath);
        if (!Path.IsPathFullyQualified(workingDirectory) || !Directory.Exists(workingDirectory))
            throw new ArgumentException("An existing absolute working directory is required.");
        var commandLine = string.Join(" ", arguments.Select(QuoteArgument));
        return Task.Run(() => LaunchWithTemporaryTask(childSessionId, fullPath, commandLine,
            Path.GetFullPath(workingDirectory), TaskRunLevelLeastPrivilege));
    }

    private static Task LaunchElevatedAsync(
        uint childSessionId,
        string executablePath,
        string arguments,
        string workingDirectory, CancellationToken cancellationToken = default)
    {
        return Task.Run(() =>
            LaunchWithTemporaryTask(
                childSessionId,
                executablePath,
                arguments,
                workingDirectory, cancellationToken: cancellationToken), cancellationToken);
    }

    private static ProcessLaunchInfo CreateBetterGiStartInfo(string? startupMode)
    {
        var currentProcessPath = Environment.ProcessPath
            ?? throw new InvalidOperationException("Could not get the BetterGI executable path.");
        var fullProcessPath = Path.GetFullPath(currentProcessPath);

        // 通过 dotnet BetterGI.dll 启动时，计划任务也需要使用 dotnet 作为入口。
        if (string.Equals(
                Path.GetFileNameWithoutExtension(fullProcessPath),
                "dotnet",
                StringComparison.OrdinalIgnoreCase))
        {
            var entryAssemblyPath = Assembly.GetEntryAssembly()?.Location;
            if (string.IsNullOrWhiteSpace(entryAssemblyPath))
            {
                throw new InvalidOperationException("Could not get the BetterGI entry assembly path.");
            }

            return new ProcessLaunchInfo(
                fullProcessPath,
                $"{QuoteArgument(Path.GetFullPath(entryAssemblyPath))} "
                + $"{CommandLineOptions.InstanceArgument} childSession" + AutomationArguments(CommandLineOptions.Instance.AutomationMode, startupMode),
                AppContext.BaseDirectory);
        }

        return new ProcessLaunchInfo(
            ValidateExecutablePath(fullProcessPath),
            $"{CommandLineOptions.InstanceArgument} childSession" + AutomationArguments(CommandLineOptions.Instance.AutomationMode, startupMode),
            AppContext.BaseDirectory);
    }

    /// <summary>Omitted/manual intent preserves legacy argv; endpoint-only automation never includes the game start action.</summary>
    internal static string AutomationArguments(bool automated, string? startupMode)
    {
        if (startupMode is not null && !ChildSessionStartupOperation.IsSupported(startupMode))
            throw new ArgumentException("Unsupported child startup mode.", nameof(startupMode));
        return !automated ? string.Empty : startupMode == ChildSessionStartupOperation.ControlEndpoint ? " --automation" : " --automation start";
    }

    private static void LaunchWithTemporaryTask(
        uint childSessionId,
        string executablePath,
        string arguments,
        string workingDirectory,
        int runLevel = TaskRunLevelHighest, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var actualChildSessionId = ChildSessionNativeMethods.TryGetChildSessionId();
        if (actualChildSessionId != childSessionId)
        {
            throw new InvalidOperationException(
                $"The target child session changed. Requested session: {childSessionId}; current session: "
                + (actualChildSessionId?.ToString(CultureInfo.InvariantCulture) ?? "none")
                + "。");
        }

        var schedulerType = Type.GetTypeFromProgID("Schedule.Service")
            ?? throw new InvalidOperationException("Task Scheduler COM is not available on this version of Windows.");
        var taskName = $"BetterGI-ChildSession-{(runLevel == TaskRunLevelHighest ? "Elevated" : "Standard")}Launch-{Guid.NewGuid():N}";
        string accountName;
        using (var currentIdentity = WindowsIdentity.GetCurrent())
        {
            accountName = currentIdentity.Name;
        }

        object? schedulerObject = null;
        object? rootFolderObject = null;
        object? taskDefinitionObject = null;
        object? actionObject = null;
        object? registeredTaskObject = null;
        object? runningTaskObject = null;
        var taskRegistered = false;

        try
        {
            schedulerObject = Activator.CreateInstance(schedulerType)
                ?? throw new InvalidOperationException("Could not create the Task Scheduler COM object.");
            dynamic scheduler = schedulerObject;
            scheduler.Connect();

            rootFolderObject = scheduler.GetFolder("\\");
            dynamic rootFolder = rootFolderObject;
            taskDefinitionObject = scheduler.NewTask(0);
            dynamic taskDefinition = taskDefinitionObject;

            taskDefinition.RegistrationInfo.Author = "BetterGI";
            taskDefinition.RegistrationInfo.Description =
                $"Temporarily launching {Path.GetFileName(executablePath)} in child session {childSessionId}";

            taskDefinition.Settings.Enabled = true;
            taskDefinition.Settings.Hidden = true;
            taskDefinition.Settings.AllowDemandStart = true;
            taskDefinition.Settings.DisallowStartIfOnBatteries = false;
            taskDefinition.Settings.StopIfGoingOnBatteries = false;
            taskDefinition.Settings.ExecutionTimeLimit = "PT0S";

            taskDefinition.Principal.UserId = accountName;
            taskDefinition.Principal.LogonType = TaskLogonInteractiveToken;
            taskDefinition.Principal.RunLevel = runLevel;

            actionObject = taskDefinition.Actions.Create(TaskActionExecute);
            dynamic action = actionObject;
            action.Path = executablePath;
            action.Arguments = arguments;
            action.WorkingDirectory = workingDirectory;

            registeredTaskObject = rootFolder.RegisterTaskDefinition(
                taskName,
                taskDefinition,
                TaskCreate,
                accountName,
                null,
                TaskLogonInteractiveToken,
                null);
            taskRegistered = true;

            dynamic registeredTask = registeredTaskObject;
            // Cancellation after admission must still prevent a queued COM launch;
            // after RunEx starts a process, the caller must not replay the request.
            cancellationToken.ThrowIfCancellationRequested();
            runningTaskObject = registeredTask.RunEx(
                null,
                TaskRunUseSessionId,
                checked((int)childSessionId),
                null);

            if (runningTaskObject is null)
            {
                throw new InvalidOperationException("Task Scheduler did not return a running instance.");
            }
        }
        finally
        {
            if (taskRegistered && rootFolderObject is not null)
            {
                try
                {
                    dynamic rootFolder = rootFolderObject;
                    rootFolder.DeleteTask(taskName, 0);
                }
                catch (COMException)
                {
                    // 临时任务启动成功后，清理失败不应中断已经启动的目标程序。
                }
            }

            ReleaseComObject(runningTaskObject);
            ReleaseComObject(registeredTaskObject);
            ReleaseComObject(actionObject);
            ReleaseComObject(taskDefinitionObject);
            ReleaseComObject(rootFolderObject);
            ReleaseComObject(schedulerObject);
        }
    }

    private static string ValidateExecutablePath(string executablePath)
    {
        var fullPath = Path.GetFullPath(executablePath);
        if (!File.Exists(fullPath))
        {
            throw new FileNotFoundException("The program to launch does not exist.", fullPath);
        }

        if (!string.Equals(Path.GetExtension(fullPath), ".exe", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("Only .exe programs can be selected.", nameof(executablePath));
        }

        return fullPath;
    }

    /// <summary>Quote one Windows argv item for Task Scheduler's string-only COM Arguments property.</summary>
    internal static string QuoteArgument(string argument)
    {
        ArgumentNullException.ThrowIfNull(argument);
        if (argument.Contains('\0')) throw new ArgumentException("Command arguments cannot contain NUL.");
        var result = new StringBuilder("\"");
        var slashes = 0;
        foreach (var character in argument)
        {
            if (character == '\\') { slashes++; continue; }
            result.Append('\\', character == '"' ? slashes * 2 + 1 : slashes);
            result.Append(character);
            slashes = 0;
        }
        result.Append('\\', slashes * 2);
        return result.Append('"').ToString();
    }

    private static void ReleaseComObject(object? value)
    {
        if (value is not null && Marshal.IsComObject(value))
        {
            Marshal.FinalReleaseComObject(value);
        }
    }

    private sealed record ProcessLaunchInfo(
        string ExecutablePath,
        string Arguments,
        string WorkingDirectory);
}
