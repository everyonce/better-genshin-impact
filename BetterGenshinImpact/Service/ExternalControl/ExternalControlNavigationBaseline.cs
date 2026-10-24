using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask;
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
    private void BeginNavigationBaseline()
    {
        if (IsRestartBusy()) throw new InvalidOperationException("A task or lifecycle operation is already active.");
        var expected = _serviceProvider.GetRequiredService<GameRuntimeService>().Current
            ?? throw new InvalidOperationException("Start the RDP child game runtime before the navigation baseline.");
        using var process = Process.GetCurrentProcess();
        if (!_navigationBaselineOwner.TryStart(expected.Window.ProcessId, process.SessionId, async (runId, token, phase) =>
            {
                NavigationBaselineRunResult? baseline = null;
                var taskResult = await new TaskRunner().RunCurrentWithResultAsync(async (runtime, ct) =>
                {
                    if (!ReferenceEquals(runtime, expected)) throw new InvalidOperationException("runtime_identity_changed");
                    await using var native = new NativeNavigationBaselineOperations(runtime, runId, ct);
                    baseline = await new NavigationBaselineTask(native).RunAsync(phase, native.Token);
                    if (baseline.Verified) phase("cleaning_up");
                }, waitForMainUi: false, requestToken: token, taskName: "Fixed Mondstadt Street Baseline");
                return (taskResult, baseline);
            })) throw new InvalidOperationException("This service already owns a fixed navigation baseline.");
    }
}
