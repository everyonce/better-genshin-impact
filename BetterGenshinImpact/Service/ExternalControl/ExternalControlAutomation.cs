using System;
using System.IO;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Threading;
using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.Service.ChildSession;
using BetterGenshinImpact.Service.Interface;
using Fischless.GameCapture;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Opt-in RDP lifecycle commands, separate from the existing fixed pilot ownership protocol.</summary>
public sealed partial class ExternalControlService
{
    /// <summary>Current bounded game-start/stop operation; replacement waits for it to finish.</summary>
    private Task? _automationOperation;
    /// <summary>Cancel game startup before a requested cooperative stop.</summary>
    private CancellationTokenSource? _automationCancellation;
    /// <summary>Prevent completion of an older cancelled operation from overwriting new status.</summary>
    private int _automationGeneration;
    /// <summary>Machine-readable lifecycle state of this child.</summary>
    private string _automationState = "idle";
    /// <summary>Last lifecycle failure reported without a modal dialog.</summary>
    private string? _automationError;
    /// <summary>Read once per process so replacement clients can verify the loaded installation.</summary>
    private readonly Lazy<string> _assemblySha256 = new(ReadAssemblyHash);

    /// <summary>Pure boundary check shared by startup and pipe entry points.</summary>
    internal static string? AutomationTargetError(string command, bool enabled, bool isRoot, bool isRemoteChild)
    {
        if (!enabled) return "automation_disabled";
        var rootCommand = command is "startChildSession" or "cancelChildStart" or "minimizeChildSession"
            or "showChildSession" or "launchChildCommand";
        return rootCommand ? isRoot ? null : "primary_required" : isRemoteChild ? null : "rdp_child_required";
    }

    /// <summary>Start/attach Genshin only within an explicitly automated, actual RDP child.</summary>
    public void BeginAutomatedGameStart()
    {
        if (AutomationTargetError("startChildGame", CommandLineOptions.Instance.AutomationMode,
                _instances.Context.IsRoot, IsRemoteChildTarget()) is { } error)
            throw new InvalidOperationException(error);
        if (_automationOperation is { IsCompleted: false })
            throw new InvalidOperationException("A lifecycle operation is already active.");
        StartAutomationOperation("starting_game", "game_ready", TimeSpan.FromSeconds(60), async token =>
        {
            var runtime = await _serviceProvider.GetRequiredService<GameRuntimeService>().StartAsync(token);
            token.ThrowIfCancellationRequested();
            if (runtime is null) throw new InvalidOperationException("The configured Genshin game could not be launched or attached.");
        });
    }

    /// <summary>Dispatch fast control requests; long connection/start/stop work is polled through status.</summary>
    private async Task<ExternalControlResponse> HandleAutomationAsync(ExternalControlRequest request, CancellationToken token)
    {
        if (AutomationTargetError(request.Command!, CommandLineOptions.Instance.AutomationMode,
                _instances.Context.IsRoot, IsRemoteChildTarget()) is { } error)
            return ExternalControlResponse.Failure(request.RequestId, error, "The automation mode or instance role does not permit this command.");
        var dispatcher = Application.Current?.Dispatcher;
        if (dispatcher is null || dispatcher.HasShutdownStarted)
            return ExternalControlResponse.Failure(request.RequestId, "ui_unavailable", "The lifecycle dispatcher is unavailable.");
        try
        {
            await dispatcher.InvokeAsync(async () =>
            {
                if (_instances.Context.IsRoot)
                {
                    var child = _serviceProvider.GetRequiredService<ChildSessionService>();
                    switch (request.Command)
                    {
                        case "startChildSession": child.BeginAutomationStart(); break;
                        case "cancelChildStart": child.CancelAutomationStart(); break;
                        case "minimizeChildSession": child.MinimizeWindow(); break;
                        case "showChildSession": child.ShowWindow(); break;
                        case "launchChildCommand":
                            await child.LaunchStandardCommandAsync(checked((uint)request.ChildSessionId!.Value),
                                request.ExecutablePath!, request.Arguments!, request.WorkingDirectory!);
                            break;
                    }
                }
                else if (request.Command == "startChildGame") BeginAutomatedGameStart();
                else if (request.Command == "stopAutomationTasks") BeginAutomatedStop();
                else if (request.Command == "startAgentStream") BeginAgentStream(request.EnableInput == true, request.ObservationProfile);
                else if (request.Command == "stopAgentStream") StopAgentStream();
                else if (request.Command == "setCaptureMode") BeginCaptureModeSwitch(request.CaptureMode!.Value);
                else if (request.Command == "startNavigationReset") BeginNavigationReset(request.TargetYawDegrees ?? 0);
                else if (request.Command == "startNavigationBaseline") BeginNavigationBaseline();
            }, DispatcherPriority.Normal, token).Task.Unwrap().ConfigureAwait(false);
            return new ExternalControlResponse { RequestId = request.RequestId, Success = true,
                Message = "Command dispatched; inspect status or the command runner result to confirm completion.",
                Status = await BuildStatusAsync(token).ConfigureAwait(false) };
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            _logger.LogWarning(exception, "Automation command {Command} failed", request.Command);
            return ExternalControlResponse.Failure(request.RequestId, "automation_command_failed", exception.GetBaseException().Message);
        }
    }

    /// <summary>Cancel tasks through their registered ownership callbacks, release input, and detach without closing Genshin.</summary>
    private void BeginAutomatedStop()
    {
        _automationCancellation?.Cancel();
        _agentStreamOwner.Cancel();
        _navigationResetOwner.Cancel();
        _navigationBaselineOwner.Cancel();
        StartAutomationOperation("stopping", "stopped", TimeSpan.FromSeconds(20), async token =>
        {
            _serviceProvider.GetRequiredService<TaskStopService>().StopAll(TaskStopReason.UserRequested);
            await _serviceProvider.GetRequiredService<GameRuntimeService>().StopAsync().WaitAsync(token);
            await _agentStreamOwner.StopAsync(token);
            await _navigationResetOwner.StopAsync(token);
            await _navigationBaselineOwner.StopAsync(token);
            InputHub.ReleaseAll();
            // StopAsync detaches immediately; task cleanup/finally must finish before replacement.
            while (TaskControl.TaskSemaphore.CurrentCount == 0 || RunnerContext.Instance.IsContinuousRunGroup || IsOwnedTaskRunning())
                await Task.Delay(50, token);
        });
    }

    /// <summary>Use the Home page's stop/start runtime flow for one typed capture setting, without restarting the game.</summary>
    private void BeginCaptureModeSwitch(CaptureModes mode)
    {
        if (IsRestartBusy()) throw new InvalidOperationException("Stop active tasks and wait for lifecycle completion before changing capture mode.");
        var runtime = _serviceProvider.GetRequiredService<GameRuntimeService>();
        var config = _serviceProvider.GetRequiredService<IConfigService>();
        StartAutomationOperation("changing_capture", "game_ready", TimeSpan.FromSeconds(60), token =>
            CaptureModeSwitch.ReattachAsync(mode, TaskControl.TaskSemaphore, runtime.StopAsync,
                // Use the same shared observable config as the Home dropdown,
                // and flush the selected backend before attaching its new runtime.
                selected => config.Get().CaptureMode = selected.ToString(), config.Flush,
                async ct => await runtime.StartAsync(ct) is not null, token));
    }

    /// <summary>One bounded operation with generation-aware final status; no request timeout leaves untracked work.</summary>
    private void StartAutomationOperation(string initialState, string completedState, TimeSpan timeout,
        Func<CancellationToken, Task> operation)
    {
        _automationCancellation?.Dispose();
        _automationCancellation = new CancellationTokenSource(timeout);
        var generation = ++_automationGeneration;
        _automationState = initialState;
        _automationError = null;
        _automationOperation = RunAutomationOperationAsync(operation, _automationCancellation.Token, generation, completedState);
    }

    /// <summary>Observe lifecycle failures and return them through status instead of blocking modal startup UI.</summary>
    private async Task RunAutomationOperationAsync(Func<CancellationToken, Task> operation,
        CancellationToken token, int generation, string completedState)
    {
        try
        {
            // The operation owns cancellation of its underlying work. Keep tracking it
            // until cleanup completes instead of abandoning it at an outer timeout.
            await operation(token);
            if (generation == _automationGeneration) _automationState = completedState;
        }
        catch (Exception exception)
        {
            if (generation != _automationGeneration) return;
            _automationState = "failed";
            _automationError = exception is OperationCanceledException
                ? "Lifecycle operation was cancelled or exceeded its deadline."
                : exception.GetBaseException().Message;
            _logger.LogWarning(exception, "Automated lifecycle operation failed");
        }
    }

    /// <summary>Read WPF-owned state on its dispatcher and append process/build readiness data.</summary>
    private Task<ExternalControlStatus> AddAutomationStatusAsync(ExternalControlStatus status, CancellationToken token)
    {
        var result = AddAgentStreamStatus(status) with { NavigationReset = _navigationResetOwner.Snapshot(includeDiagnostics: false),
            NavigationBaseline = _navigationBaselineOwner.Snapshot(),
            AutomationEnabled = CommandLineOptions.Instance.AutomationMode,
            AppVersion = Global.Version, AssemblySha256 = _assemblySha256.Value };
        var dispatcher = Application.Current?.Dispatcher;
        return ExternalControlStatusCollector.ReadAsync(dispatcher, () =>
        {
            var runtime = _serviceProvider.GetRequiredService<GameRuntimeService>();
            var current = result with { RuntimeRunning = runtime.IsRunning, TaskRunning = IsRestartBusy() || runtime.IsStarting,
                AutomationState = _automationState, AutomationError = _automationError,
                CaptureMode = _serviceProvider.GetRequiredService<IConfigService>().Get().CaptureMode };
            if (!_instances.Context.IsRoot) return current;
            var child = _serviceProvider.GetRequiredService<ChildSessionService>();
            child.RefreshState();
            return current with { ChildSessionId = child.ChildSessionId, ChildConnectedState = child.ConnectedState,
                ChildWindowMinimized = child.IsWindowMinimized, AutomationState = child.AutomationState,
                AutomationError = child.AutomationError };
        }, result, token);
    }

    /// <summary>Fingerprint the staged assembly; empty means readiness cannot be verified.</summary>
    private static string ReadAssemblyHash()
    {
        try
        {
            using var stream = File.OpenRead(typeof(App).Assembly.Location);
            return Convert.ToHexString(SHA256.HashData(stream));
        }
        catch (IOException) { return string.Empty; }
        catch (UnauthorizedAccessException) { return string.Empty; }
    }
}
