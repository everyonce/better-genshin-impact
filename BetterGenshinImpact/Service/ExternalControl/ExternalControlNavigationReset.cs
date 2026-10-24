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
    private void BeginNavigationReset(double yaw, string capturePolicy)
    {
        if (!NavigationResetCapturePolicy.IsSupported(capturePolicy)) throw new ArgumentException("unsupported_capture_policy", nameof(capturePolicy));
        if (IsRestartBusy()) throw new InvalidOperationException("A task or lifecycle operation is already active.");
        var expectedRuntime = _serviceProvider.GetRequiredService<GameRuntimeService>().Current
            ?? throw new InvalidOperationException("Start the RDP child game runtime before resetting navigation.");
        // Reject observe-only before accepting an owner or admitting any generic task/capture fallback.
        expectedRuntime.ThrowIfDesktopControllerUnavailable();
        var config = _serviceProvider.GetRequiredService<IConfigService>().Get();
        using var process = Process.GetCurrentProcess();
        if (!_navigationResetOwner.TryStart(yaw, expectedRuntime.Window.ProcessId, process.SessionId, async (token, phase) =>
            {
                NavigationResetSample[]? samples = null;
                NavigationResetTask? workflow = null;
                // Both overloads retain the same native disposal and result path; only the opt-in receives activation authority.
                async Task RunResetAsync(GameRuntime runtime, CancellationToken ct, Func<CancellationToken, Task>? activate)
                {
                    if (!ReferenceEquals(runtime, expectedRuntime)) throw new InvalidOperationException("runtime_identity_changed");
                    await using var native = new NativeNavigationResetOperations(runtime, config, ct, capturePolicy);
                    workflow = new NavigationResetTask(native, activate is null ? null : activationToken => native.IsolateCaptureAsync(activate, activationToken));
                    try { samples = await workflow.RunAsync(yaw, phase, native.Token); }
                    catch (OperationCanceledException) when (native.GuardError is not null)
                    { throw new InvalidOperationException(native.GuardError); }
                }
                var runner = new TaskRunner();
                var result = capturePolicy == NavigationResetCapturePolicy.TaskOwnedTimer
                    ? await runner.RunNativeControllerWithResultAsync((runtime, ct, activate) => RunResetAsync(runtime, ct, activate),
                        requestToken: token, taskName: "Fixed Mondstadt Navigation Reset", requiredRuntime: expectedRuntime.IsDesktopCapture ? expectedRuntime : null)
                    : await runner.RunNativeControllerWithResultAsync((runtime, ct) => RunResetAsync(runtime, ct, null), pauseTimerCapture: false,
                        requestToken: token, taskName: "Fixed Mondstadt Navigation Reset", requiredRuntime: expectedRuntime.IsDesktopCapture ? expectedRuntime : null);
                // TaskRunner maps workflow exceptions to a result; preserve failed observations after its cleanup too.
                return (result, samples, workflow?.VerificationDiagnostics ?? []);
            }, capturePolicy: capturePolicy, readbackMode: GameCaptureSettings.GetReadbackModeName(expectedRuntime.Capture),
                sourcePolicy: expectedRuntime.DesktopDcSourcePolicy))
            throw new InvalidOperationException("This service already owns a navigation reset.");
    }
}
