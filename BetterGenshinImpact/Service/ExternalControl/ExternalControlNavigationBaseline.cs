using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.GameTask.Runtime;
using Microsoft.Extensions.DependencyInjection;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>One reviewed street leg, separately reset; no arbitrary routes, scripts, coordinates or input sequences.</summary>
public sealed partial class ExternalControlService
{
    /// <summary>Claim before TaskRunner acquisition so competing starts/replacement cannot race the pending baseline.</summary>
    private readonly NavigationBaselineTaskOwner _navigationBaselineOwner = new();

    /// <summary>Read a pinned finished run through the same authenticated child pipe, leaving ordinary status compact.</summary>
    private async Task<ExternalControlResponse> ReadNavigationBaselineResultAsync(ExternalControlRequest request, CancellationToken ct)
    {
        var status = await BuildStatusAsync(ct).ConfigureAwait(false);
        var error = _navigationBaselineOwner.TryGetResult(request.NavigationBaselineRunId!, out var baseline);
        if (error is not null) return ExternalControlResponse.Failure(request.RequestId, error, "The requested fixed-leg run is unfinished or no longer retained.");
        return new ExternalControlResponse { RequestId = request.RequestId, Success = true,
            Status = status with { NavigationBaseline = baseline! } };
    }

    /// <summary>Pin the current RDP runtime and start a result-bearing fixed task under existing exclusive ownership.</summary>
    private void BeginNavigationBaseline(string timingContract, string capturePolicy, string routeProfile = NavigationBaselineTask.ProfileId, string? continuationFromRunId = null, string? shadowCapture = null)
    {
        NavigationBaselineShadowMode.Validate(shadowCapture, timingContract, capturePolicy);
        var route = NavigationBaselineRouteProfile.Resolve(routeProfile, timingContract, capturePolicy);
        if (!NavigationBaselineTiming.IsSupported(timingContract)) throw new ArgumentException("unsupported_timing_contract", nameof(timingContract));
        if (!NavigationBaselineCapturePolicy.IsSupported(capturePolicy)) throw new ArgumentException("unsupported_capture_policy", nameof(capturePolicy));
        if (IsRestartBusy()) throw new InvalidOperationException("A task or lifecycle operation is already active.");
        var expected = _serviceProvider.GetRequiredService<GameRuntimeService>().Current
            ?? throw new InvalidOperationException("Start the RDP child game runtime before the navigation baseline.");
        expected.ThrowIfDesktopControllerUnavailable();
        if (expected.IsDesktopCapture && (timingContract != NavigationBaselineTiming.V4
            || capturePolicy != NavigationBaselineCapturePolicy.TaskOwnedTimer || !route.SupportsHostContinuation
            || shadowCapture is not null))
            throw new InvalidOperationException("desktop_capture_route_not_supported");
        using var process = Process.GetCurrentProcess();
        var childProcessId = process.Id; var windowsSessionId = process.SessionId;
        // Identity collection and owner admission run synchronously on the existing UI command dispatcher.
        // Runtime stop/replacement is rechecked after TaskSemaphore ownership and again after proof-file reads.
        NavigationBaselineOwnerBinding? ReadBinding()
        {
            if (!route.RetainsOwnerBinding(timingContract, capturePolicy)) return null;
            expected.ThrowIfStopping();
            if (!ReferenceEquals(_serviceProvider.GetRequiredService<GameRuntimeService>().Current, expected))
                throw new InvalidOperationException("runtime_identity_changed");
            using var game = Process.GetProcessById(expected.Window.ProcessId);
            if (game.HasExited || game.SessionId != windowsSessionId) throw new InvalidOperationException("game_target_unavailable");
            return new(expected, expected.Capture, expected.Input, childProcessId, windowsSessionId, _instanceNonce,
                game.Id, game.StartTime.ToUniversalTime().Ticks, expected.Capture.GetType().FullName!,
                GameCaptureSettings.GetReadbackModeName(expected.Capture), expected.DesktopDcSourcePolicy,
                expected.IsDesktopCapture ? _assemblySha256.Value : null);
        }
        var binding = ReadBinding();
        if (!_navigationBaselineOwner.TryStartBound(expected.Window.ProcessId, windowsSessionId, binding, continuationFromRunId,
            async (runId, token, phase, continuation) =>
            {
                NavigationBaselineRunResult? baseline = null;
                var taskResult = await new TaskRunner().RunNativeControllerWithResultAsync(async (runtime, ct) =>
                {
                    if (!ReferenceEquals(runtime, expected)) throw new InvalidOperationException("runtime_identity_changed");
                    if (binding is not null && !binding.Matches(ReadBinding()!)) throw new InvalidOperationException("continuation_runtime_identity_changed");
                    if (continuation is not null)
                    {
                        NavigationBaselineEndpointContinuation.VerifyEvidenceFiles(continuation.PredecessorEvidence);
                        ct.ThrowIfCancellationRequested();
                        if (!binding!.Matches(ReadBinding()!)) throw new InvalidOperationException("continuation_runtime_identity_changed");
                    }
                    await using var native = new NativeNavigationBaselineOperations(runtime, runId, ct, timingContract: timingContract, capturePolicy: capturePolicy,
                        routeProfile: routeProfile, continuation: continuation, shadowCapture: shadowCapture);
                    baseline = await new NavigationBaselineTask(native, timingContract, capturePolicy, routeProfile, continuation: continuation).RunAsync(phase, native.Token);
                    if (baseline.Verified) phase("cleaning_up");
                }, requestToken: token, taskName: "Fixed Mondstadt Street Baseline",
                    pauseTimerCapture: capturePolicy == NavigationBaselineCapturePolicy.TaskOwnedTimer,
                    requiredRuntime: continuation is not null || expected.IsDesktopCapture ? expected : null,
                    strictCleanup: expected.IsDesktopCapture);
                return (taskResult, baseline);
            }, timingContract: timingContract, capturePolicy: capturePolicy, routeProfile: routeProfile, shadowCapture: shadowCapture)) throw new InvalidOperationException("This service already owns a fixed navigation baseline.");
    }
}
