using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.NavigationReset;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Service.Interface;
using Microsoft.Extensions.DependencyInjection;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Fixed navigation reset only; no supplied script, coordinates, executable, or input sequence.</summary>
public sealed partial class ExternalControlService
{
    /// <summary>Independent ownership prevents reset, stream and replacement from racing before TaskRunner acquires its lock.</summary>
    private readonly NavigationResetTaskOwner _navigationResetOwner = new();

    /// <summary>Return complete evidence only for the requested finished run on the authenticated RDP child.</summary>
    private async Task<ExternalControlResponse> ReadNavigationResetDiagnosticsAsync(
        ExternalControlRequest request, CancellationToken token)
    {
        // ExecuteCommandAsync has already verified the pipe target, opt-in and real RDP child role.
        var status = await BuildStatusAsync(token).ConfigureAwait(false);
        var error = _navigationResetOwner.TryGetDiagnostics(request.NavigationResetRunId!, out var reset);
        if (error is not null)
            return ExternalControlResponse.Failure(request.RequestId, error, "The requested reset has not finished or is no longer retained.");
        // The command gate excludes a competing start; the terminal owner snapshot supplies every reset field together.
        return new ExternalControlResponse { RequestId = request.RequestId, Success = true,
            Status = status with { NavigationReset = reset! } };
    }

    /// <summary>Dispatch a bounded reset, pinning the current runtime before returning an accepted run ID.</summary>
    private void BeginNavigationReset(double yaw)
    {
        if (IsRestartBusy()) throw new InvalidOperationException("A task or lifecycle operation is already active.");
        var expectedRuntime = _serviceProvider.GetRequiredService<GameRuntimeService>().Current
            ?? throw new InvalidOperationException("Start the RDP child game runtime before resetting navigation.");
        var config = _serviceProvider.GetRequiredService<IConfigService>().Get();
        using var process = Process.GetCurrentProcess();
        if (!_navigationResetOwner.TryStart(yaw, expectedRuntime.Window.ProcessId, process.SessionId, async (token, phase) =>
            {
                NavigationResetSample[]? samples = null;
                NavigationResetTask? workflow = null;
                var result = await new TaskRunner().RunCurrentWithResultAsync(async (runtime, ct) =>
                {
                    if (!ReferenceEquals(runtime, expectedRuntime)) throw new InvalidOperationException("runtime_identity_changed");
                    await using var native = new NativeNavigationResetOperations(runtime, config, ct);
                    workflow = new NavigationResetTask(native);
                    try { samples = await workflow.RunAsync(yaw, phase, native.Token); }
                    catch (OperationCanceledException) when (native.GuardError is not null)
                    { throw new InvalidOperationException(native.GuardError); }
                }, waitForMainUi: false, requestToken: token, taskName: "Fixed Mondstadt Navigation Reset");
                // TaskRunner maps workflow exceptions to a result; preserve failed observations after its cleanup too.
                return (result, samples, workflow?.VerificationDiagnostics ?? []);
            })) throw new InvalidOperationException("This service already owns a navigation reset.");
    }
}
