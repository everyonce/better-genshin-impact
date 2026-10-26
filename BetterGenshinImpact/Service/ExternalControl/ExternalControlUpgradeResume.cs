using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.Pulonia.Services;
using BetterGenshinImpact.Service.ChildSession;
using BetterGenshinImpact.Service.Instance;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Explicit release of an upgraded root; the replacement transaction never calls this operation.</summary>
public sealed partial class ExternalControlService
{
    /// <summary>One state-initialization/release operation at a time.</summary>
    private int _upgradeResumeInProgress;

    /// <summary>Resolve the existing interface singleton; never construct or register a second coordinator.</summary>
    internal static PuloniaTaskService UpgradeCoordinator(IServiceProvider services)
        => services.GetRequiredService<IPuloniaTaskService>() as PuloniaTaskService
           ?? throw new InvalidOperationException("The registered Pulonia coordinator does not support held startup.");

    /// <summary>Require the actual registered child, same final executable, and the preserved game lifetime.</summary>
    private InstanceEndpoint RequireUpgradeChild(UpgradeSessionBinding binding)
    {
        binding.VerifyExisting(ChildSessionNativeMethods.TryGetChildSessionId());
        var children = _instances.GetConnectedChildInstances()
            .Where(x => x.InstanceType == BetterGiInstanceType.ChildSession).ToArray();
        if (children.Length != 1 || children[0].WindowsSessionId != binding.SessionId)
            throw new InvalidOperationException("Exactly one final child must remain authenticated in the preserved session.");
        return children[0];
    }

    /// <summary>Read existing state while held, recheck identities, then commit durable completion before releasing work.</summary>
    private async Task<ExternalControlResponse> ResumeRootAfterUpgradeAsync(ExternalControlRequest request, CancellationToken token)
    {
        var binding = CommandLineOptions.Instance.UpgradeSession;
        var hold = _serviceProvider.GetRequiredService<PuloniaStartupHold>();
        if (binding is null || binding.IsReleased || !hold.IsHeld)
            return ExternalControlResponse.Failure(request.RequestId, "upgrade_not_held", "This root has no unreleased upgrade hold.");
        if (Interlocked.CompareExchange(ref _upgradeResumeInProgress, 1, 0) != 0)
            return ExternalControlResponse.Failure(request.RequestId, "busy", "Upgrade resume is already in progress.");
        try
        {
            ThrowIfRestartReserved();
            if (IsRestartBusy()) throw new InvalidOperationException("The root is not idle.");
            var child = RequireUpgradeChild(binding);
            using var process = Process.GetProcessById(child.ProcessId);
            // Keep the actual child lifetime across asynchronous state initialization and IPC status reads.
            _ = process.SafeHandle;
            if (process.HasExited || process.SessionId != binding.SessionId
                || process.StartTime.ToUniversalTime() != child.StartedAt.UtcDateTime
                || !string.Equals(process.MainModule?.FileName, Path.Combine(AppContext.BaseDirectory, "BetterGI.exe"), StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("The connected child does not belong to the final package/lifetime.");
            if ((await _instances.RefreshSoloTaskStatusAsync(child, token).ConfigureAwait(false)).IsActive)
                throw new InvalidOperationException("The child has active task ownership.");
            await UpgradeCoordinator(_serviceProvider).PrepareUpgradeResumeAsync(token).ConfigureAwait(false);
            var current = RequireUpgradeChild(binding);
            if (process.HasExited || current.ProcessId != child.ProcessId || current.StartedAt != child.StartedAt
                || (await _instances.RefreshSoloTaskStatusAsync(current, token).ConfigureAwait(false)).IsActive)
                throw new InvalidOperationException("The final child changed or became busy during state initialization.");
            var dispatcher = System.Windows.Application.Current?.Dispatcher
                ?? throw new InvalidOperationException("The lifecycle dispatcher is unavailable.");
            await dispatcher.InvokeAsync(() =>
            {
                // Root lifecycle commands share this dispatcher. Recheck after every asynchronous preparation step.
                token.ThrowIfCancellationRequested();
                ThrowIfRestartReserved();
                if (IsRestartBusy() || !hold.IsHeld || binding.IsReleased)
                    throw new InvalidOperationException("Root admission changed before explicit release.");
                var finalChild = RequireUpgradeChild(binding);
                if (process.HasExited || finalChild.ProcessId != child.ProcessId || finalChild.StartedAt != child.StartedAt)
                    throw new InvalidOperationException("The child changed before explicit release.");
                // The durable completion belongs to explicit resume, not to copy/launch success.
                binding.CompleteStartupFile();
                binding.MarkReleased();
                hold.Release();
            }, System.Windows.Threading.DispatcherPriority.Normal, token).Task.ConfigureAwait(false);
            return new ExternalControlResponse { RequestId = request.RequestId, Success = true,
                Status = await BuildStatusAsync(token).ConfigureAwait(false),
                Message = "Explicit upgrade hold released after existing state checks. Historical multi-file coherence remains unverified." };
        }
        catch (Exception error) when (IsRecoveryException(error))
        {
            _logger.LogWarning(error, "Explicit upgrade resume failed for {RequestId}", request.RequestId);
            return ExternalControlResponse.Failure(request.RequestId, "upgrade_resume_failed",
                "Resume failed or its response is uncertain; inspect hold status. No failed initialization releases scheduling.");
        }
        finally { Volatile.Write(ref _upgradeResumeInProgress, 0); }
    }
}
