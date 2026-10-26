using BetterGenshinImpact.Pulonia.Remote;
using System;
using System.Buffers.Binary;
using System.ComponentModel;
using System.Collections.Generic;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Script;
using BetterGenshinImpact.Core.Script.Group;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.Service.Instance;
using BetterGenshinImpact.ViewModel.Pages;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Win32.SafeHandles;
using System.Windows.Threading;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>
/// Per-user, opt-in command endpoint for the one fixed Act One pilot group.
/// It is available only inside an interactive remote-desktop child instance.
/// </summary>
public sealed partial class ExternalControlService : BackgroundService
{
    private static readonly TimeSpan IoTimeout = TimeSpan.FromSeconds(5);
    private static readonly TimeSpan HeartbeatFreshness = TimeSpan.FromSeconds(5);
    private const int MaximumCachedRequests = 4096;
    private const string PilotGroupName = "ActOneRun";
    private const string PilotScriptFolder = "ActOnePilot";
    private const string OptInPath = "User/ExternalControl/enable-quest-control.json";
    private const string HeartbeatPath = "User/JsScript/ActOnePilot/controller-status.json";

    private readonly InstanceService _instances;
    private readonly IServiceProvider _serviceProvider;
    private readonly ILogger<ExternalControlService> _logger;
    private readonly string _instanceNonce = Guid.NewGuid().ToString("N");
    private readonly Dictionary<Guid, CachedResponse> _responses = new();
    private readonly Queue<CachedRequestExpiry> _responseOrder = new();
    private readonly SemaphoreSlim _commandGate = new(1, 1);
    /// <summary>Atomic task ownership for explicitly requested idle-only child replacements.</summary>
    private readonly ExternalControlRestartReservation _restartReservation = new(() => TaskControl.TaskSemaphore);
    private readonly object _ownershipLock = new();
    private WindowsIdentity? _identity;
    private SecurityIdentifier? _userSid;
    private string? _pipeName;
    private Task? _ownedExecutionTask;
    private CancellationTokenSource? _ownedCancellationSource;
    private string? _ownedScriptSession;
    private string? _previousScriptSession;
    private long _acceptedStartAtUnixMs;
    private bool _hasObservedOwnedHeartbeat;
    private bool _stopRequested;
    private bool _applicationRestarting;
    private bool _recoveryLauncherInstalled;
    private string? _hostRecoveryState;
    private string _pilotState = "idle";
    private bool _enabled;

    public ExternalControlService(
        InstanceService instances,
        IServiceProvider serviceProvider,
        ILogger<ExternalControlService> logger)
    {
        _instances = instances;
        _serviceProvider = serviceProvider;
        _logger = logger;
    }

    public override Task StartAsync(CancellationToken cancellationToken)
    {
        if (!IsSupportedTarget())
        {
            _logger.LogInformation(
                "External pilot control is unavailable for BetterGI instance {InstanceType}, session {SessionId}",
                _instances.Context.InstanceType,
                _instances.Context.WindowsSessionId);
            return Task.CompletedTask;
        }

        var optInFile = Global.Absolute(OptInPath);
        if (!CommandLineOptions.Instance.AutomationMode && !ExternalControlOptIn.TryRead(optInFile))
        {
            _logger.LogInformation("External pilot control is disabled; opt-in marker not enabled at {Path}", optInFile);
            return Task.CompletedTask;
        }

        _identity = WindowsIdentity.GetCurrent();
        _userSid = _identity.User
                   ?? throw new InvalidOperationException("Could not get the current Windows user SID.");
        _pipeName = ExternalControlProtocol.CreatePipeName(
            _instances.Context.WindowsSessionId,
            _instances.Context.ProcessId,
            _userSid.Value);
        _enabled = true;
        _logger.LogInformation(
            "External pilot control enabled for process {ProcessId}, session {SessionId}, pipe {PipeName}",
            _instances.Context.ProcessId,
            _instances.Context.WindowsSessionId,
            _pipeName);
        return base.StartAsync(cancellationToken);
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _automationCancellation?.Cancel();
        await _agentStreamOwner.StopAsync(cancellationToken).ConfigureAwait(false);
        await _navigationResetOwner.StopAsync(cancellationToken).ConfigureAwait(false);
        await _navigationBaselineOwner.StopAsync(cancellationToken).ConfigureAwait(false);
        await base.StopAsync(cancellationToken).ConfigureAwait(false);
        _identity?.Dispose();
        _commandGate.Dispose();
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_enabled || _pipeName is null || _userSid is null)
        {
            return;
        }

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await using var pipe = CreateServer(_pipeName, _userSid);
                await pipe.WaitForConnectionAsync(stoppingToken).ConfigureAwait(false);
                await HandleConnectionAsync(pipe, stoppingToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception) when (exception is IOException
                                               or UnauthorizedAccessException
                                               or ObjectDisposedException)
            {
                _logger.LogWarning(exception, "External pilot-control pipe connection failed");
                await Task.Delay(TimeSpan.FromMilliseconds(250), stoppingToken).ConfigureAwait(false);
            }
        }
    }

    private bool IsSupportedTarget() =>
        (CommandLineOptions.Instance.AutomationMode && _instances.Context.IsRoot)
        || IsRemoteChildTarget();

    /// <summary>Gameplay and child replacement never target a primary or local-desktop instance.</summary>
    private bool IsRemoteChildTarget() =>
        _instances.Context.InstanceType == BetterGiInstanceType.ChildSession
        && RemoteSessionApi.IsRemoteDesktop();

    /// <summary>Reuse the shared same-user pipe policy, including its medium-integrity label.</summary>
    private static NamedPipeServerStream CreateServer(string pipeName, SecurityIdentifier userSid) =>
        BetterGenshinImpact.Core.Pipes.LocalUserPipe.Create(pipeName, userSid, ExternalControlProtocol.MaximumFrameBytes);

    /// <summary>A successful reserved launch commits shutdown independently of all later response failures.</summary>
    private Task HandleConnectionAsync(NamedPipeServerStream pipe, CancellationToken stoppingToken) =>
        _restartReservation.GuardRequestAsync(() => HandleConnectionCoreAsync(pipe, stoppingToken), ScheduleApplicationShutdown);

    /// <summary>Authenticate and handle one bounded request; legacy direct restart retains response-driven shutdown.</summary>
    private async Task HandleConnectionCoreAsync(NamedPipeServerStream pipe, CancellationToken stoppingToken)
    {
        if (!IsLocalClient(pipe.SafePipeHandle))
        {
            return;
        }

        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        timeout.CancelAfter(IoTimeout);
        var shutdownAfterWrite = false;
        try
        {
            var lengthBytes = new byte[sizeof(int)];
            await ReadExactlyAsync(pipe, lengthBytes, timeout.Token).ConfigureAwait(false);
            var length = BinaryPrimitives.ReadInt32LittleEndian(lengthBytes);
            if (length is <= 0 or > ExternalControlProtocol.MaximumFrameBytes)
            {
                return;
            }

            var payload = new byte[length];
            await ReadExactlyAsync(pipe, payload, timeout.Token).ConfigureAwait(false);
            // Impersonation metadata is available only after reading a client message.
            if (!IsSameUserClient(pipe))
            {
                return;
            }

            var request = ExternalControlProtocol.TryDeserializeRequest(payload, out var parsed)
                ? parsed
                : null;
            var response = request is null
                ? ExternalControlResponse.Failure(Guid.Empty, "invalid_json", "Request JSON is invalid.")
                : await HandleRequestAsync(request, timeout.Token).ConfigureAwait(false);
            shutdownAfterWrite = response.ShutdownAfterWrite;
            var responseBytes = ExternalControlProtocol.SerializeResponse(response);
            if (responseBytes.Length > ExternalControlProtocol.MaximumResponseBytes(request?.Command))
            {
                responseBytes = ExternalControlProtocol.SerializeResponse(
                    ExternalControlResponse.Failure(response.RequestId, "response_too_large", "Response exceeds the protocol limit."));
            }

            BinaryPrimitives.WriteInt32LittleEndian(lengthBytes, responseBytes.Length);
            await pipe.WriteAsync(lengthBytes, timeout.Token).ConfigureAwait(false);
            await pipe.WriteAsync(responseBytes, timeout.Token).ConfigureAwait(false);
            await pipe.FlushAsync(timeout.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!stoppingToken.IsCancellationRequested)
        {
            _logger.LogDebug("External pilot-control client exceeded the I/O deadline");
        }
        catch (IOException exception)
        {
            _logger.LogDebug(exception, "External pilot-control client disconnected during a request");
        }
        finally
        {
            if (shutdownAfterWrite && !_restartReservation.Committed)
            {
                ScheduleApplicationShutdown();
            }
        }
    }

    private async Task<ExternalControlResponse> HandleRequestAsync(
        ExternalControlRequest request,
        CancellationToken cancellationToken)
    {
        var now = DateTimeOffset.UtcNow;
        var validationError = ExternalControlProtocol.ValidateRequest(request, now);
        if (validationError is not null)
        {
            return ExternalControlResponse.Failure(request.RequestId, validationError, "Request validation failed.");
        }

        PruneExpiredResponses(now);
        var fingerprint = ExternalControlProtocol.Fingerprint(request);
        if (_responses.TryGetValue(request.RequestId, out var cached))
        {
            return string.Equals(cached.Fingerprint, fingerprint, StringComparison.Ordinal)
                ? cached.Response
                : ExternalControlResponse.Failure(request.RequestId, "request_id_conflict", "Request ID was already used with different content.");
        }

        await _commandGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            PruneExpiredResponses(DateTimeOffset.UtcNow);
            if (_responses.TryGetValue(request.RequestId, out cached))
            {
                return string.Equals(cached.Fingerprint, fingerprint, StringComparison.Ordinal)
                    ? cached.Response
                    : ExternalControlResponse.Failure(request.RequestId, "request_id_conflict", "Request ID was already used with different content.");
            }
            if (_responses.Count >= MaximumCachedRequests)
            {
                return ExternalControlResponse.Failure(request.RequestId, "request_capacity", "Request replay-protection capacity is full; no action was executed.");
            }

            var response = await ExecuteCommandAsync(request, cancellationToken).ConfigureAwait(false);
            CacheResponse(request, fingerprint, response);
            return response;
        }
        finally
        {
            _commandGate.Release();
        }
    }

    private async Task<ExternalControlResponse> ExecuteCommandAsync(
        ExternalControlRequest request,
        CancellationToken cancellationToken)
    {
        if (request.Command is "status")
        {
            return new ExternalControlResponse
            {
                RequestId = request.RequestId,
                Success = true,
                Status = await BuildStatusAsync(cancellationToken).ConfigureAwait(false)
            };
        }

        if (request.TargetProcessId != _instances.Context.ProcessId
            || request.TargetWindowsSessionId != _instances.Context.WindowsSessionId
            || !string.Equals(request.TargetNonce, _instanceNonce, StringComparison.Ordinal))
        {
            return ExternalControlResponse.Failure(request.RequestId, "target_mismatch", "Target process, session, or instance nonce does not match.");
        }
        if (!CommandLineOptions.Instance.AutomationMode && !ExternalControlOptIn.TryRead(Global.Absolute(OptInPath)))
        {
            return ExternalControlResponse.Failure(request.RequestId, "disabled", "External control is no longer enabled.");
        }

        if ((_restartReservation.BlocksAdmission || _applicationRestarting)
            && request.Command is not ("navigationResetDiagnostics" or "navigationBaselineResult"))
            return ExternalControlResponse.Failure(request.RequestId, "restart_in_progress", "This instance has committed to restart; no new operation was admitted.");
        if (ExternalControlProtocol.IsAutomationCommand(request.Command))
            return await HandleAutomationAsync(request, cancellationToken).ConfigureAwait(false);
        if (!IsRemoteChildTarget())
            return ExternalControlResponse.Failure(request.RequestId, "rdp_child_required", "This operation requires the real RDP child instance.");

        return request.Command switch
        {
            "startPilot" => await StartPilotAsync(request.RequestId, cancellationToken).ConfigureAwait(false),
            "stopPilot" => await StopPilotAsync(request.RequestId, cancellationToken).ConfigureAwait(false),
            "restartApp" => await RestartApplicationAsync(request.RequestId, request.IdleRestart, cancellationToken).ConfigureAwait(false),
            "installRecoveryLauncher" => await InstallRecoveryLauncherAsync(request.RequestId, cancellationToken).ConfigureAwait(false),
            "restartHost" => await RestartHostAsync(request.RequestId, cancellationToken).ConfigureAwait(false),
            "shutdownApp" => await ShutdownChildApplicationAsync(request.RequestId, cancellationToken).ConfigureAwait(false),
            "navigationResetDiagnostics" => await ReadNavigationResetDiagnosticsAsync(request, cancellationToken).ConfigureAwait(false),
            "navigationBaselineResult" => await ReadNavigationBaselineResultAsync(request, cancellationToken).ConfigureAwait(false),
            _ => ExternalControlResponse.Failure(request.RequestId, "unsupported_command", "Command is not supported.")
        };
    }

    private async Task<ExternalControlResponse> RestartApplicationAsync(Guid requestId,
        ExternalControlIdleRestart? idleRestart, CancellationToken cancellationToken)
    {
        if (!ExternalControlOptIn.TryReadAppRestart(Global.Absolute(OptInPath)))
        {
            return ExternalControlResponse.Failure(
                requestId,
                "restart_disabled",
                "App restart requires allowAppRestart:true in the local external-control opt-in.");
        }

        if (IsRestartBusy())
        {
            return ExternalControlResponse.Failure(
                requestId,
                "busy",
                "The pilot or another BetterGI task is still active; stop it and wait for completion before restarting.");
        }

        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            var startInfo = ExternalControlRestart.Prepare(AppContext.BaseDirectory, Environment.ProcessId,
                CommandLineOptions.Instance.AutomationMode, idleRestart);
            var dispatcher = System.Windows.Application.Current?.Dispatcher;
            if (dispatcher is null || dispatcher.HasShutdownStarted)
            {
                return ExternalControlResponse.Failure(requestId, "ui_unavailable", "BetterGI's task dispatcher is unavailable.");
            }

            var replacement = await dispatcher.InvokeAsync(() =>
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (idleRestart is not null)
                {
                    var runtime = _serviceProvider.GetRequiredService<BetterGenshinImpact.GameTask.Runtime.GameRuntimeService>();
                    return _restartReservation.TryLaunch(() => ReserveIdleRuntimeRestart(runtime),
                        () => ReleaseIdleRuntimeRestart(runtime),
                        HasOtherRestartWork, () =>
                        {
                            cancellationToken.ThrowIfCancellationRequested();
                            return Process.Start(startInfo);
                        });
                }
                return IsRestartBusy() ? null : Process.Start(startInfo);
            }, DispatcherPriority.Normal, cancellationToken).Task.ConfigureAwait(false);
            if (replacement is null)
            {
                return ExternalControlResponse.Failure(
                    requestId,
                    "busy",
                    "A BetterGI task became active before the replacement could be launched.");
            }
            replacement.Dispose();

            _applicationRestarting = true;
            _logger.LogInformation("Started staged BetterGI replacement for request {RequestId}; shutdown follows response attempt", requestId);
            return new ExternalControlResponse
            {
                RequestId = requestId,
                Success = true,
                Message = "The verified staged replacement was launched. This instance will close after the response is sent or its write deadline expires.",
                Status = await BuildStatusAsync(cancellationToken).ConfigureAwait(false),
                ShutdownAfterWrite = true
            };
        }
        catch (Exception exception) when (_restartReservation.Committed)
        {
            // The replacement exists. Never report a failed launch or release its old-owner reservation.
            _logger.LogWarning(exception, "Replacement was launched but its response failed for request {RequestId}", requestId);
            return ExternalControlResponse.Failure(requestId, "restart_dispatched_response_failed",
                "The pinned replacement was launched, but its response failed. Verify the new child before any further action; do not replay restart.")
                with { ShutdownAfterWrite = true };
        }
        catch (Exception exception) when (exception is InvalidOperationException or IOException or UnauthorizedAccessException or System.ComponentModel.Win32Exception)
        {
            _logger.LogWarning(exception, "Could not launch the staged BetterGI replacement for request {RequestId}", requestId);
            return ExternalControlResponse.Failure(requestId, "restart_launch_failed", "The staged BetterGI replacement could not be launched.");
        }
    }

    /// <summary>Compose the existing runtime gate with remote pure/pending ownership before launch.</summary>
    private static bool ReserveIdleRuntimeRestart(BetterGenshinImpact.GameTask.Runtime.GameRuntimeService runtime)
    {
        if (!runtime.TryReserveRestart()) return false;
        if (PuloniaRemoteNodeHost.TryReserveRestart()) return true;
        runtime.ReleaseRestartReservation();
        return false;
    }

    /// <summary>A failed launch releases exactly the two reservations acquired by this owner.</summary>
    private static void ReleaseIdleRuntimeRestart(BetterGenshinImpact.GameTask.Runtime.GameRuntimeService runtime)
    {
        try { PuloniaRemoteNodeHost.ReleaseRestartReservation(); }
        finally { runtime.ReleaseRestartReservation(); }
    }

    /// <summary>Ordinary admission sees the reserved semaphore; only its owner excludes that one check.</summary>
    private bool IsRestartBusy() => _applicationRestarting || _restartReservation.BlocksAdmission
        || TaskControl.TaskSemaphore.CurrentCount == 0 || HasOtherRestartWork();

    /// <summary>Work that must remain absent even after the restart owns the task semaphore.</summary>
    private bool HasOtherRestartWork() =>
        IsOwnedTaskRunning()
        || PuloniaRemoteNodeHost.HasActiveNodes
        || _agentStreamOwner.Snapshot().Running
        || _navigationResetOwner.Running
        || _navigationBaselineOwner.Running
        || _automationOperation is { IsCompleted: false }
        || _serviceProvider.GetService<BetterGenshinImpact.GameTask.Runtime.GameRuntimeService>()?.IsStarting == true
        || RunnerContext.Instance.IsContinuousRunGroup
        || _pilotState is "starting" or "running" or "stopping";

    private ExternalControlResponse? CheckRecoveryMutation(Guid requestId)
    {
        if (!ExternalControlOptIn.TryReadAppRestart(Global.Absolute(OptInPath)))
            return ExternalControlResponse.Failure(requestId, "restart_disabled", "Recovery requires allowAppRestart:true in the local external-control opt-in.");
        return IsRestartBusy()
            ? ExternalControlResponse.Failure(requestId, "busy", "Stop the pilot and wait for completion before changing the application or recovery launcher.")
            : null;
    }

    private async Task<ExternalControlResponse> InstallRecoveryLauncherAsync(Guid requestId, CancellationToken cancellationToken)
    {
        if (CheckRecoveryMutation(requestId) is { } rejected) return rejected;
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            var plan = ExternalControlRecovery.CreateValidatedRecoveryPlan(AppContext.BaseDirectory);
            if (!_instances.TryGetConnectedRoot(out var root) || root is null)
                return ExternalControlResponse.Failure(requestId, "root_unavailable", "No verified connected root is available.");
            var rootSessionId = ExternalControlRecovery.GetRootSessionId(root, _instances.Context.WindowsSessionId);
            ExternalControlRecovery.Install(plan, rootSessionId);
            _recoveryLauncherInstalled = true;
            return new ExternalControlResponse { RequestId = requestId, Success = true,
                Message = "The fixed on-demand RDP host task was installed and read back. No application was launched.",
                Status = await BuildStatusAsync(cancellationToken).ConfigureAwait(false) };
        }
        catch (Exception exception) when (IsRecoveryException(exception))
        {
            _logger.LogWarning(exception, "Could not install the fixed recovery launcher for request {RequestId}", requestId);
            return ExternalControlResponse.Failure(requestId, "recovery_install_failed", "The recovery task could not be installed or verified; inspect the application log.");
        }
    }

    private async Task<ExternalControlResponse> RestartHostAsync(Guid requestId, CancellationToken cancellationToken)
    {
        if (CheckRecoveryMutation(requestId) is { } rejected) return rejected;
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            var plan = ExternalControlRecovery.CreateValidatedRecoveryPlan(AppContext.BaseDirectory);
            ExternalControlRecovery.ValidateInstalled(plan);
            if (!_instances.TryGetConnectedRoot(out var root) || root is null)
                return ExternalControlResponse.Failure(requestId, "root_unavailable", "No verified connected root is available. Use the installed recovery launcher.");
            var rootSessionId = ExternalControlRecovery.GetRootSessionId(root, _instances.Context.WindowsSessionId);

            using var process = Process.GetProcessById(root.ProcessId);
            var rootPath = process.MainModule?.FileName;
            if (process.HasExited || process.Id == Environment.ProcessId || process.SessionId != rootSessionId
                || rootPath is null || !string.Equals(Path.GetFileName(rootPath), "BetterGI.exe", StringComparison.OrdinalIgnoreCase)
                || root.StartedAt == default || process.StartTime.ToUniversalTime() != root.StartedAt.UtcDateTime)
                throw new InvalidOperationException("The connected root no longer identifies the expected live BetterGI process.");
            var rootPlan = ExternalControlRecovery.CreateValidatedRecoveryPlan(Path.GetDirectoryName(rootPath)!);
            if (!string.Equals(Directory.GetParent(rootPlan.AppDirectory)?.Parent?.FullName,
                    Directory.GetParent(plan.AppDirectory)?.Parent?.FullName, StringComparison.OrdinalIgnoreCase)
                || !_instances.TryGetConnectedRoot(out var latestRoot) || latestRoot is null || latestRoot.ProcessId != root.ProcessId
                || latestRoot.WindowsSessionId != rootSessionId || latestRoot.StartedAt != root.StartedAt
                || IsRestartBusy())
                throw new InvalidOperationException("The root identity or task state changed before host restart.");

            // Graceful root disposal logs off the entire desktop clone. Terminate only this
            // checked root process so the child, game and RDP session survive the handoff.
            process.Kill(entireProcessTree: false);
            using var exitTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            exitTimeout.CancelAfter(TimeSpan.FromSeconds(2));
            await process.WaitForExitAsync(exitTimeout.Token).ConfigureAwait(false);
            ExternalControlRecovery.RunHost(plan, rootSessionId);
            _hostRecoveryState = "launch_dispatched";
            _logger.LogInformation("Terminated verified root {RootProcessId} and dispatched fixed recovery for request {RequestId}", root.ProcessId, requestId);
            return new ExternalControlResponse { RequestId = requestId, Success = true,
                Message = "Root replacement was dispatched. Verify the new root, RDP connection and child status before resuming gameplay.",
                Status = await BuildStatusAsync(cancellationToken).ConfigureAwait(false) };
        }
        catch (Exception exception) when (IsRecoveryException(exception))
        {
            _hostRecoveryState = "failed_or_unknown";
            _logger.LogWarning(exception, "Host recovery failed or has an unknown outcome for request {RequestId}", requestId);
            return ExternalControlResponse.Failure(requestId, "host_recovery_failed_or_unknown", "Inspect live processes and use the installed recovery launcher if the root is absent. Do not replay this command blindly.");
        }
    }

    private async Task<ExternalControlResponse> ShutdownChildApplicationAsync(Guid requestId, CancellationToken cancellationToken)
    {
        if (CheckRecoveryMutation(requestId) is { } rejected) return rejected;
        _applicationRestarting = true;
        return new ExternalControlResponse { RequestId = requestId, Success = true,
            Message = "Only this verified RDP child will exit after the response attempt. The outer host and game remain running.",
            Status = await BuildStatusAsync(cancellationToken).ConfigureAwait(false), ShutdownAfterWrite = true };
    }

    private static bool IsRecoveryException(Exception exception) => exception is InvalidOperationException
        or ArgumentException or IOException or UnauthorizedAccessException or Win32Exception or COMException or OperationCanceledException;

    private void ScheduleApplicationShutdown()
    {
        var application = System.Windows.Application.Current;
        var dispatcher = application?.Dispatcher;
        if (application is null || dispatcher is null || dispatcher.HasShutdownStarted)
        {
            return;
        }

        try
        {
            dispatcher.BeginInvoke(new Action(application.Shutdown), DispatcherPriority.Normal);
        }
        catch (InvalidOperationException exception)
        {
            _logger.LogWarning(exception, "Could not schedule BetterGI shutdown after replacement launch");
        }
    }

    private async Task<ExternalControlResponse> StartPilotAsync(Guid requestId, CancellationToken cancellationToken)
    {
        if (IsOwnedTaskRunning())
        {
            return ExternalControlResponse.Failure(requestId, "already_owned", "The controller already owns an active pilot task.");
        }
        if (_navigationBaselineOwner.Running || RunnerContext.Instance.IsContinuousRunGroup
            || TaskControl.TaskSemaphore.CurrentCount == 0)
        {
            return ExternalControlResponse.Failure(requestId, "busy", "A BetterGI task is already active or stopping.");
        }

        var heartbeat = ReadHeartbeat();
        if (heartbeat is { IsIdentityMatch: true, IsFresh: true }
            && IsCancellablePilotState(heartbeat.Heartbeat.State))
        {
            return ExternalControlResponse.Failure(requestId, "pilot_already_active", "The pilot reports an active task that this service did not start.");
        }

        var dispatcher = System.Windows.Application.Current?.Dispatcher;
        if (dispatcher is null || dispatcher.HasShutdownStarted)
        {
            return ExternalControlResponse.Failure(requestId, "ui_unavailable", "BetterGI's task dispatcher is unavailable.");
        }

        try
        {
            var acceptedAtUnixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            var start = await dispatcher.InvokeAsync(() =>
            {
                // A request can time out while waiting in the dispatcher queue. Never let
                // that abandoned request start the pilot later when the UI becomes free.
                cancellationToken.ThrowIfCancellationRequested();
                var scriptControl = _serviceProvider.GetRequiredService<ScriptControlViewModel>();
                scriptControl.OnNavigatedTo();
                var group = scriptControl.ScriptGroups.FirstOrDefault(item => item.Name == PilotGroupName);
                if (!IsPinnedPilotGroup(group))
                {
                    return new StartResult(null, null, "The ActOneRun group is missing or does not contain only the pinned ActOnePilot JavaScript project.");
                }
                if (_navigationBaselineOwner.Running || RunnerContext.Instance.IsContinuousRunGroup
                    || TaskControl.TaskSemaphore.CurrentCount == 0)
                {
                    return new StartResult(null, null, "A BetterGI task became active before the pilot could start.");
                }

                var source = new CancellationTokenSource();
                var executionTask = scriptControl.StartGroups([group!], requestToken: source.Token);
                return new StartResult(executionTask, source, null);
            }, DispatcherPriority.Normal, cancellationToken).Task.ConfigureAwait(false);

            if (start.Error is not null || start.ExecutionTask is null || start.CancellationSource is null)
            {
                return ExternalControlResponse.Failure(requestId, "start_rejected", start.Error ?? "Pilot start was rejected.");
            }

            lock (_ownershipLock)
            {
                _ownedExecutionTask = start.ExecutionTask;
                _ownedCancellationSource = start.CancellationSource;
                _ownedScriptSession = null;
                _previousScriptSession = heartbeat?.IsIdentityMatch == true ? heartbeat.Heartbeat.Session : null;
                _acceptedStartAtUnixMs = acceptedAtUnixMs;
                _hasObservedOwnedHeartbeat = false;
                _stopRequested = false;
                _pilotState = "starting";
                _ = start.ExecutionTask.ContinueWith(
                    _ => ObserveOwnedTaskCompletion(start.ExecutionTask),
                    CancellationToken.None,
                    TaskContinuationOptions.ExecuteSynchronously,
                    TaskScheduler.Default);
            }

            return new ExternalControlResponse
            {
                RequestId = requestId,
                Success = true,
                Message = "Pilot task start was dispatched; running is reported only after a matching fresh heartbeat.",
                Status = await BuildStatusAsync(cancellationToken).ConfigureAwait(false)
            };
        }
        catch (Exception exception) when (exception is InvalidOperationException or OperationCanceledException)
        {
            _logger.LogWarning(exception, "Could not start the pinned pilot group");
            return ExternalControlResponse.Failure(requestId, "start_failed", "BetterGI could not dispatch the pilot task.");
        }
    }

    private async Task<ExternalControlResponse> StopPilotAsync(Guid requestId, CancellationToken cancellationToken)
    {
        if (!IsOwnedTaskRunning() || !IsOwnedTaskStillCurrent())
        {
            return ExternalControlResponse.Failure(requestId, "not_owned", "There is no active pilot task owned by this service; unrelated work was left untouched.");
        }

        var heartbeat = ReadHeartbeat();
        if (!IsCurrentOwnedHeartbeat(heartbeat) || heartbeat?.Heartbeat.Session is not { Length: > 0 } session)
        {
            return ExternalControlResponse.Failure(requestId, "pilot_identity_unknown", "The pilot has not published a matching session heartbeat, so cancellation was not sent.");
        }
        string? ownedScriptSession;
        lock (_ownershipLock)
        {
            ownedScriptSession = _ownedScriptSession;
        }
        if (ownedScriptSession is null || !string.Equals(ownedScriptSession, session, StringComparison.Ordinal))
        {
            return ExternalControlResponse.Failure(requestId, "pilot_session_unverified", "A fresh matching pilot heartbeat must be observed before cancellation is allowed.");
        }

        if (!CanStopOwnedPilot(
                IsOwnedTaskStillCurrent(),
                IsCurrentOwnedHeartbeat(heartbeat),
                heartbeat.IsFresh,
                session,
                ownedScriptSession,
                heartbeat.Heartbeat.State))
        {
            return heartbeat.IsFresh
                ? ExternalControlResponse.Failure(requestId, "pilot_not_active", "The owned pilot heartbeat does not report a stoppable state.")
                : ExternalControlResponse.Failure(requestId, "pilot_heartbeat_stale", "The owned pilot heartbeat is stale; cancellation was not sent.");
        }
        var dispatcher = System.Windows.Application.Current?.Dispatcher;
        if (dispatcher is null || dispatcher.HasShutdownStarted)
        {
            return ExternalControlResponse.Failure(requestId, "ui_unavailable", "BetterGI's task dispatcher is unavailable.");
        }

        var cancelResult = await dispatcher.InvokeAsync(() =>
        {
            if (!IsOwnedTaskRunning() || !IsOwnedTaskStillCurrent())
            {
                return "task_changed";
            }

            var latestHeartbeat = ReadHeartbeat();
            if (!IsCurrentOwnedHeartbeat(latestHeartbeat)
                || !string.Equals(latestHeartbeat?.Heartbeat.Session, session, StringComparison.Ordinal))
            {
                return "pilot_identity_changed";
            }

            string? currentOwnedScriptSession;
            lock (_ownershipLock)
            {
                currentOwnedScriptSession = _ownedScriptSession;
            }
            if (latestHeartbeat is null
                || !CanStopOwnedPilot(
                    IsOwnedTaskStillCurrent(),
                    IsCurrentOwnedHeartbeat(latestHeartbeat),
                    latestHeartbeat.IsFresh,
                    latestHeartbeat.Heartbeat.Session,
                    currentOwnedScriptSession,
                    latestHeartbeat.Heartbeat.State))
            {
                return "pilot_not_active";
            }

            CancellationTokenSource? source;
            lock (_ownershipLock)
            {
                if (!string.Equals(_ownedScriptSession, session, StringComparison.Ordinal))
                {
                    return "pilot_identity_changed";
                }
                source = _ownedCancellationSource;
                if (source is null)
                {
                    return "task_changed";
                }
                _stopRequested = true;
                _pilotState = "stopping";
            }

            // Cancel only this service-owned caller token, never the global stop service.
            if (!TryCancelOwnedSource(source))
            {
                lock (_ownershipLock)
                {
                    _stopRequested = false;
                    _pilotState = "running";
                }
                return "task_changed";
            }
            return null;
        }, DispatcherPriority.Normal, cancellationToken).Task.ConfigureAwait(false);
        if (cancelResult is not null)
        {
            return ExternalControlResponse.Failure(requestId, cancelResult, "The owned task changed before cancellation; no unrelated task was stopped.");
        }
        await Task.Yield();
        return new ExternalControlResponse
        {
            RequestId = requestId,
            Success = true,
            Message = "Cooperative cancellation was requested for the service-owned pilot. Completion is not yet confirmed.",
            Status = await BuildStatusAsync(cancellationToken).ConfigureAwait(false)
        };
    }

    /// <summary>Combine process identity with bounded, cancellable collection of UI-owned runtime readiness.</summary>
    private Task<ExternalControlStatus> BuildStatusAsync(CancellationToken cancellationToken)
    {
        var heartbeat = ReadHeartbeat();
        var ownedTaskRunning = IsOwnedTaskRunning();
        var ownedHeartbeat = IsCurrentOwnedHeartbeat(heartbeat);
        bool hasObservedOwnedHeartbeat;
        string pilotState;
        lock (_ownershipLock)
        {
            if (ownedTaskRunning
                && _ownedExecutionTask is { IsCompleted: false }
                && ownedHeartbeat
                && heartbeat is { IsFresh: true, Heartbeat.Session: not null })
            {
                _ownedScriptSession ??= heartbeat.Heartbeat.Session;
                _hasObservedOwnedHeartbeat = true;
                if (heartbeat.Heartbeat.State == "running")
                {
                    _pilotState = "running";
                }
            }
            hasObservedOwnedHeartbeat = _hasObservedOwnedHeartbeat;
            pilotState = _pilotState;
        }
        var state = ownedTaskRunning
            ? ownedHeartbeat && heartbeat is { IsFresh: true, Heartbeat.State: not null }
                ? heartbeat.Heartbeat.State
                : hasObservedOwnedHeartbeat
                    ? "unresponsive"
                    : pilotState
            : heartbeat is { IsIdentityMatch: true, IsFresh: true }
                ? heartbeat.Heartbeat.State ?? "idle"
                : pilotState is "completed" or "faulted" or "stopped" ? pilotState : "idle";

        return AddAutomationStatusAsync(new ExternalControlStatus
        {
            AppDirectory = AppContext.BaseDirectory,
            CaptureStorageVersion = 1,
            ProcessId = _instances.Context.ProcessId,
            WindowsSessionId = _instances.Context.WindowsSessionId,
            InstanceType = _instances.Context.InstanceType.ToString(),
            RemoteDesktop = RemoteSessionApi.IsRemoteDesktop(),
            PipeName = _pipeName ?? string.Empty,
            InstanceNonce = _instanceNonce,
            PilotState = _applicationRestarting ? "restarting" : state,
            ServiceOwnsPilot = ownedTaskRunning,
            HeartbeatFresh = ownedHeartbeat && heartbeat is { IsFresh: true },
            ScriptSession = heartbeat?.Heartbeat.Session,
            HeartbeatAtUnixMs = heartbeat?.Heartbeat.HeartbeatAt,
            FrameId = heartbeat?.Heartbeat.FrameId,
            ActiveRequestId = heartbeat?.Heartbeat.ActiveRequestId,
            ScriptState = heartbeat?.Heartbeat.State,
            ScriptError = heartbeat?.Heartbeat.Error,
            RootProcessId = _instances.TryGetConnectedRoot(out var root) ? root?.ProcessId : null,
            RecoveryLauncherInstalled = _recoveryLauncherInstalled,
            HostRecoveryState = _hostRecoveryState
        }, cancellationToken);
    }

    private HeartbeatRead? ReadHeartbeat()
    {
        var path = Global.Absolute(HeartbeatPath);
        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            if (stream.Length is <= 0 or > 4096)
            {
                return null;
            }
            var heartbeat = JsonSerializer.Deserialize<PilotHeartbeat>(stream);
            if (heartbeat is null
                || heartbeat.Version != 1
                || heartbeat.FrameId < 0
                || heartbeat.Session is not { Length: > 0 and <= 128 }
                || heartbeat.State is not ("starting" or "idle" or "running" or "stopped" or "faulted"))
            {
                return null;
            }

            DateTimeOffset timestamp;
            try
            {
                timestamp = DateTimeOffset.FromUnixTimeMilliseconds(heartbeat.HeartbeatAt);
            }
            catch (ArgumentOutOfRangeException)
            {
                return new HeartbeatRead(heartbeat, false, IsHeartbeatIdentityMatch(heartbeat));
            }

            var age = DateTimeOffset.UtcNow - timestamp;
            var fresh = age >= TimeSpan.Zero && age <= HeartbeatFreshness;
            return new HeartbeatRead(heartbeat, fresh, IsHeartbeatIdentityMatch(heartbeat));
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException)
        {
            _logger.LogDebug(exception, "Could not read the Act One pilot heartbeat");
            return null;
        }
    }

    private bool IsHeartbeatIdentityMatch(PilotHeartbeat heartbeat) =>
        heartbeat.ProcessId == _instances.Context.ProcessId
        && heartbeat.WindowsSessionId == _instances.Context.WindowsSessionId
        && !string.IsNullOrWhiteSpace(heartbeat.Session);

    private bool IsCurrentOwnedHeartbeat(HeartbeatRead? heartbeat) =>
        heartbeat is { IsIdentityMatch: true }
        && heartbeat.Heartbeat.HeartbeatAt >= _acceptedStartAtUnixMs
        && !string.Equals(heartbeat.Heartbeat.Session, _previousScriptSession, StringComparison.Ordinal);

    private bool IsPinnedPilotGroup(ScriptGroup? group) =>
        group is not null
        && group.Projects.Count == 1
        && group.Projects[0].Type == "Javascript"
        && group.Projects[0].FolderName == PilotScriptFolder
        && group.Projects[0].Status == "Enabled";

    private bool IsOwnedTaskRunning() =>
        IsOwnedTaskStillCurrent();

    private bool IsOwnedTaskStillCurrent()
    {
        lock (_ownershipLock)
        {
            return _ownedExecutionTask is { IsCompleted: false }
                   && _ownedCancellationSource is not null;
        }
    }

    /// <summary>Cancel the source only while it still belongs to the active pilot run.</summary>
    private bool TryCancelOwnedSource(CancellationTokenSource source)
    {
        lock (_ownershipLock)
        {
            return TryCancelOwnedRun(_ownedCancellationSource, _ownedExecutionTask, source);
        }
    }

    /// <summary>Validate run ownership before cancelling a caller token; completed or unrelated runs are untouched.</summary>
    internal static bool TryCancelOwnedRun(CancellationTokenSource? currentSource, Task? currentTask,
        CancellationTokenSource requestedSource)
    {
        if (!ReferenceEquals(currentSource, requestedSource) || currentTask is not { IsCompleted: false }) return false;
        requestedSource.Cancel();
        return true;
    }

    internal static bool IsCancellablePilotState(string? state) =>
        state is "starting" or "running" or "idle";

    internal static bool CanStopOwnedPilot(
        bool ownedTaskCurrent,
        bool currentOwnedHeartbeat,
        bool heartbeatFresh,
        string? heartbeatSession,
        string? ownedScriptSession,
        string? heartbeatState) =>
        ownedTaskCurrent
        && currentOwnedHeartbeat
        && heartbeatFresh
        && heartbeatSession is { Length: > 0 }
        && string.Equals(heartbeatSession, ownedScriptSession, StringComparison.Ordinal)
        && (IsCancellablePilotState(heartbeatState) || heartbeatState == "faulted");

    private void ObserveOwnedTaskCompletion(Task executionTask)
    {
        lock (_ownershipLock)
        {
            if (!ReferenceEquals(_ownedExecutionTask, executionTask))
            {
                return;
            }

            _pilotState = executionTask.IsFaulted
                ? "faulted"
                : _stopRequested ? "stopped" : "completed";
            if (executionTask.IsFaulted)
            {
                _logger.LogWarning(executionTask.Exception, "Service-owned pilot task ended with an error");
            }
            _ownedExecutionTask = null;
            _ownedCancellationSource?.Dispose();
            _ownedCancellationSource = null;
            _ownedScriptSession = null;
        }
    }

    private void CacheResponse(ExternalControlRequest request, string fingerprint, ExternalControlResponse response)
    {
        var expiresAt = ExternalControlProtocol.GetReplayExpiry(request.CreatedAtUnixMs);
        _responses[request.RequestId] = new CachedResponse(fingerprint, response, expiresAt);
        _responseOrder.Enqueue(new CachedRequestExpiry(request.RequestId, expiresAt));
    }

    private void PruneExpiredResponses(DateTimeOffset now)
    {
        while (_responseOrder.TryPeek(out var oldest) && oldest.ExpiresAt <= now)
        {
            _responseOrder.Dequeue();
            if (_responses.TryGetValue(oldest.RequestId, out var cached)
                && cached.ExpiresAt == oldest.ExpiresAt)
            {
                _responses.Remove(oldest.RequestId);
            }
        }
    }

    private bool IsSameUserClient(NamedPipeServerStream pipe)
    {
        if (_userSid is null)
        {
            return false;
        }
        SecurityIdentifier? clientSid = null;
        try
        {
            pipe.RunAsClient(() =>
            {
                using var clientIdentity = WindowsIdentity.GetCurrent(ifImpersonating: true);
                clientSid = clientIdentity.User;
            });
            return clientSid is not null && clientSid.Equals(_userSid);
        }
        catch (Exception exception) when (exception is IOException or InvalidOperationException or UnauthorizedAccessException)
        {
            _logger.LogDebug(exception, "Could not verify external-control client SID");
            return false;
        }
    }

    private static bool IsLocalClient(SafePipeHandle pipeHandle)
    {
        var computerName = new StringBuilder(256);
        if (NamedPipePeerApi.GetNamedPipeClientComputerName(pipeHandle, computerName, computerName.Capacity * sizeof(char)))
        {
            return string.Equals(computerName.ToString(), Environment.MachineName, StringComparison.OrdinalIgnoreCase);
        }

        // The API reports ERROR_PIPE_LOCAL (229) for a same-machine named-pipe client.
        return Marshal.GetLastWin32Error() == NamedPipePeerApi.ErrorPipeLocal;
    }

    private static async Task ReadExactlyAsync(Stream stream, Memory<byte> buffer, CancellationToken cancellationToken)
    {
        var offset = 0;
        while (offset < buffer.Length)
        {
            var read = await stream.ReadAsync(buffer[offset..], cancellationToken).ConfigureAwait(false);
            if (read == 0)
            {
                throw new EndOfStreamException("Client closed before the full frame was received.");
            }
            offset += read;
        }
    }

    private sealed record CachedResponse(string Fingerprint, ExternalControlResponse Response, DateTimeOffset ExpiresAt);

    private sealed record CachedRequestExpiry(Guid RequestId, DateTimeOffset ExpiresAt);

    private sealed record StartResult(
        Task? ExecutionTask,
        CancellationTokenSource? CancellationSource,
        string? Error);

    private sealed record HeartbeatRead(PilotHeartbeat Heartbeat, bool IsFresh, bool IsIdentityMatch);

    private static class NamedPipePeerApi
    {
        internal const int ErrorPipeLocal = 229;

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool GetNamedPipeClientComputerName(
            SafePipeHandle pipe,
            StringBuilder clientComputerName,
            int clientComputerNameLength);
    }

    private static class RemoteSessionApi
    {
        private const int SmRemoteSession = 0x1000;

        [DllImport("user32.dll")]
        private static extern int GetSystemMetrics(int index);

        internal static bool IsRemoteDesktop() => GetSystemMetrics(SmRemoteSession) != 0;
    }
}
