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
public sealed class ExternalControlService : BackgroundService
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
    private readonly object _ownershipLock = new();
    private WindowsIdentity? _identity;
    private SecurityIdentifier? _userSid;
    private string? _pipeName;
    private Task? _ownedExecutionTask;
    private BetterGenshinImpact.GameTask.TaskProgress.TaskProgress? _ownedTaskProgress;
    private CancellationTokenSource? _ownedCancellationSource;
    private string? _ownedScriptSession;
    private string? _previousScriptSession;
    private long _acceptedStartAtUnixMs;
    private bool _hasObservedOwnedHeartbeat;
    private bool _stopRequested;
    private bool _applicationRestarting;
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
        if (!ExternalControlOptIn.TryRead(optInFile))
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
        _instances.Context.InstanceType == BetterGiInstanceType.ChildSession
        && _instances.Context.WindowsSessionId != 1
        && RemoteSessionApi.IsRemoteDesktop();

    private static NamedPipeServerStream CreateServer(string pipeName, SecurityIdentifier userSid)
    {
        var security = new PipeSecurity();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
        security.SetOwner(userSid);
        security.AddAccessRule(new PipeAccessRule(
            new SecurityIdentifier(WellKnownSidType.NetworkSid, null),
            PipeAccessRights.FullControl,
            AccessControlType.Deny));
        security.AddAccessRule(new PipeAccessRule(userSid, PipeAccessRights.FullControl, AccessControlType.Allow));
        var pipe = NamedPipeServerStreamAcl.Create(
            pipeName,
            PipeDirection.InOut,
            1,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous | PipeOptions.WriteThrough,
            inBufferSize: ExternalControlProtocol.MaximumFrameBytes,
            outBufferSize: ExternalControlProtocol.MaximumFrameBytes,
            security,
            additionalAccessRights: PipeAccessRights.TakeOwnership);
        try
        {
            // CreateNamedPipe with a SACL requires ACCESS_SYSTEM_SECURITY / SeSecurityPrivilege.
            // LABEL_SECURITY_INFORMATION is narrower: set only the mandatory label after
            // creation using the pipe handle's WRITE_OWNER right. This lowers only this
            // pipe object to medium integrity while preserving its same-user DACL.
            SetMediumMandatoryLabel(pipe.SafePipeHandle);
            return pipe;
        }
        catch
        {
            pipe.Dispose();
            throw;
        }
    }

    private static void SetMediumMandatoryLabel(SafePipeHandle pipeHandle)
    {
        var descriptor = new RawSecurityDescriptor("S:(ML;;NW;;;ME)");
        var binary = new byte[descriptor.BinaryLength];
        descriptor.GetBinaryForm(binary, 0);
        var saclOffset = BitConverter.ToInt32(binary, 12);
        if (saclOffset <= 0 || saclOffset >= binary.Length)
        {
            throw new InvalidOperationException("Could not build the pipe's medium-integrity label.");
        }

        var descriptorMemory = Marshal.AllocHGlobal(binary.Length);
        try
        {
            Marshal.Copy(binary, 0, descriptorMemory, binary.Length);
            var sacl = IntPtr.Add(descriptorMemory, saclOffset);
            var error = NativeSecurityApi.SetSecurityInfo(
                pipeHandle,
                NativeSecurityApi.SeKernelObject,
                NativeSecurityApi.LabelSecurityInformation,
                IntPtr.Zero,
                IntPtr.Zero,
                IntPtr.Zero,
                sacl);
            if (error != 0)
            {
                throw new Win32Exception(unchecked((int)error), "Could not set the named pipe's medium-integrity label.");
            }
        }
        finally
        {
            Marshal.FreeHGlobal(descriptorMemory);
        }
    }

    private async Task HandleConnectionAsync(NamedPipeServerStream pipe, CancellationToken stoppingToken)
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
            if (responseBytes.Length > ExternalControlProtocol.MaximumFrameBytes)
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
            if (shutdownAfterWrite)
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
                Status = BuildStatus()
            };
        }

        if (request.TargetProcessId != _instances.Context.ProcessId
            || request.TargetWindowsSessionId != _instances.Context.WindowsSessionId
            || !string.Equals(request.TargetNonce, _instanceNonce, StringComparison.Ordinal))
        {
            return ExternalControlResponse.Failure(request.RequestId, "target_mismatch", "Target process, session, or instance nonce does not match.");
        }
        if (!ExternalControlOptIn.TryRead(Global.Absolute(OptInPath)))
        {
            return ExternalControlResponse.Failure(request.RequestId, "disabled", "External control is no longer enabled.");
        }

        return request.Command switch
        {
            "startPilot" => await StartPilotAsync(request.RequestId, cancellationToken).ConfigureAwait(false),
            "stopPilot" => await StopPilotAsync(request.RequestId, cancellationToken).ConfigureAwait(false),
            "restartApp" => await RestartApplicationAsync(request.RequestId, cancellationToken).ConfigureAwait(false),
            _ => ExternalControlResponse.Failure(request.RequestId, "unsupported_command", "Command is not supported.")
        };
    }

    private async Task<ExternalControlResponse> RestartApplicationAsync(Guid requestId, CancellationToken cancellationToken)
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
            var startInfo = ExternalControlRestart.Prepare(AppContext.BaseDirectory, Environment.ProcessId);
            var dispatcher = System.Windows.Application.Current?.Dispatcher;
            if (dispatcher is null || dispatcher.HasShutdownStarted)
            {
                return ExternalControlResponse.Failure(requestId, "ui_unavailable", "BetterGI's task dispatcher is unavailable.");
            }

            var replacement = await dispatcher.InvokeAsync(() =>
            {
                cancellationToken.ThrowIfCancellationRequested();
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
                Status = BuildStatus(),
                ShutdownAfterWrite = true
            };
        }
        catch (Exception exception) when (exception is InvalidOperationException or IOException or UnauthorizedAccessException or System.ComponentModel.Win32Exception)
        {
            _logger.LogWarning(exception, "Could not launch the staged BetterGI replacement for request {RequestId}", requestId);
            return ExternalControlResponse.Failure(requestId, "restart_launch_failed", "The staged BetterGI replacement could not be launched.");
        }
    }

    private bool IsRestartBusy() =>
        IsOwnedTaskRunning()
        || TaskControl.TaskSemaphore.CurrentCount == 0
        || RunnerContext.Instance.IsContinuousRunGroup
        || RunnerContext.Instance.taskProgress is not null
        || _pilotState is "starting" or "running" or "stopping";

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
        if (RunnerContext.Instance.IsContinuousRunGroup
            || RunnerContext.Instance.taskProgress is not null
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
                if (RunnerContext.Instance.IsContinuousRunGroup
                    || RunnerContext.Instance.taskProgress is not null
                    || TaskControl.TaskSemaphore.CurrentCount == 0)
                {
                    return new StartResult(null, null, "A BetterGI task became active before the pilot could start.");
                }

                var executionTask = scriptControl.OnStartMultiScriptGroupWithNamesAsync(PilotGroupName);
                var taskProgress = RunnerContext.Instance.taskProgress;
                if (taskProgress is null
                    || taskProgress.ScriptGroupNames.Count != 1
                    || taskProgress.ScriptGroupNames[0] != PilotGroupName)
                {
                    return new StartResult(null, null, "BetterGI did not establish the pinned pilot task context.");
                }
                return new StartResult(executionTask, taskProgress, null);
            }, DispatcherPriority.Normal, cancellationToken).Task.ConfigureAwait(false);

            if (start.Error is not null || start.ExecutionTask is null || start.TaskProgress is null)
            {
                return ExternalControlResponse.Failure(requestId, "start_rejected", start.Error ?? "Pilot start was rejected.");
            }

            lock (_ownershipLock)
            {
                _ownedExecutionTask = start.ExecutionTask;
                _ownedTaskProgress = start.TaskProgress;
                // RunMulti and TaskRunner replace CancellationContext.Cts. Bind the actual
                // final generation only after the pilot publishes its first fresh heartbeat.
                _ownedCancellationSource = null;
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
                Status = BuildStatus()
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

        if (heartbeat.IsFresh && !IsCancellablePilotState(heartbeat.Heartbeat.State))
        {
            return ExternalControlResponse.Failure(requestId, "pilot_not_active", "The pilot heartbeat does not report an active state.");
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

            // Cancel the exact source created by this RunMulti call. A newer task's
            // CancellationContext source is not touched if ownership has moved on.
            if (!CancellationContext.Instance.TryManualCancel(source))
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
            Status = BuildStatus()
        };
    }

    private ExternalControlStatus BuildStatus()
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
                _ownedCancellationSource ??= CancellationContext.Instance.Cts;
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

        return new ExternalControlStatus
        {
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
            ScriptError = heartbeat?.Heartbeat.Error
        };
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
                   && _ownedTaskProgress is not null
                   && ReferenceEquals(RunnerContext.Instance.taskProgress, _ownedTaskProgress)
                   && RunnerContext.Instance.IsContinuousRunGroup
                   && _ownedTaskProgress.ScriptGroupNames.Count == 1
                   && _ownedTaskProgress.ScriptGroupNames[0] == PilotGroupName;
        }
    }

    internal static bool IsCancellablePilotState(string? state) =>
        state is "starting" or "running" or "idle";

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
            _ownedTaskProgress = null;
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
        BetterGenshinImpact.GameTask.TaskProgress.TaskProgress? TaskProgress,
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

    private static class NativeSecurityApi
    {
        internal const int SeKernelObject = 6;
        internal const uint LabelSecurityInformation = 0x00000010;

        [DllImport("advapi32.dll", SetLastError = true)]
        internal static extern uint SetSecurityInfo(
            SafePipeHandle handle,
            int objectType,
            uint securityInfo,
            IntPtr owner,
            IntPtr group,
            IntPtr dacl,
            IntPtr sacl);
    }

    private static class RemoteSessionApi
    {
        private const int SmRemoteSession = 0x1000;

        [DllImport("user32.dll")]
        private static extern int GetSystemMetrics(int index);

        internal static bool IsRemoteDesktop() => GetSystemMetrics(SmRemoteSession) != 0;
    }
}
