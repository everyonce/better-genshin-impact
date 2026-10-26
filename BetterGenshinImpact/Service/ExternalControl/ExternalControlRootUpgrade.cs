using System;
using System.Diagnostics;
using System.IO;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.Service.Instance;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.DependencyInjection;
using System.Windows.Threading;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Exact native root and published-package preconditions for one retirement, never a restart target.</summary>
internal sealed record RootUpgradeExpectation
{
    /// <summary>Original root PID authenticated independently by the caller.</summary>
    [JsonPropertyName("processId")] public int ProcessId { get; init; }
    /// <summary>Original root's interactive session.</summary>
    [JsonPropertyName("windowsSessionId")] public int WindowsSessionId { get; init; }
    /// <summary>Native UTC creation time; unlike a PID this cannot silently identify a reused process.</summary>
    [JsonPropertyName("startedFileTime")] public long StartedFileTime { get; init; }
    /// <summary>Original root's validated numbered release directory.</summary>
    [JsonPropertyName("appDirectory")] public string AppDirectory { get; init; } = "";
    /// <summary>Actual original root executable hash.</summary>
    [JsonPropertyName("exeSha256")] public string ExeSha256 { get; init; } = "";
    /// <summary>Actual original root assembly hash.</summary>
    [JsonPropertyName("dllSha256")] public string DllSha256 { get; init; } = "";

    /// <summary>Validate wire scalars without opening files or processes.</summary>
    internal bool IsValid() => ProcessId > 0 && WindowsSessionId > 0 && StartedFileTime > 0
        && AppDirectory is { Length: > 0 and <= 512 } && Path.IsPathFullyQualified(AppDirectory)
        && !AppDirectory.StartsWith(@"\\", StringComparison.Ordinal)
        && IsHash(ExeSha256) && IsHash(DllSha256);

    /// <summary>Only a complete lowercase SHA256 digest is accepted.</summary>
    private static bool IsHash(string? value) => value is { Length: 64 }
        && System.Linq.Enumerable.All(value, c => c is >= '0' and <= '9' or >= 'a' and <= 'f');

    /// <summary>Pure comparison with values obtained from the retained native root and verified package.</summary>
    internal void Verify(int pid, int session, long started, string directory, string exe, string dll)
    {
        if (!IsValid() || ProcessId != pid || WindowsSessionId != session || StartedFileTime != started
            || !string.Equals(Path.TrimEndingDirectorySeparator(AppDirectory), directory, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(ExeSha256, exe, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(DllSha256, dll, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("The original root lifetime or package changed.");
    }
}

/// <summary>Retire only the verified root and this idle bootstrap child; preserve the clone/game for an external bounded upgrade.</summary>
public sealed partial class ExternalControlService
{
    /// <summary>No staging or replacement launch occurs here; the caller must observe both original processes exiting.</summary>
    private async Task<ExternalControlResponse> RetireRootForUpgradeAsync(ExternalControlRequest request, CancellationToken token)
    {
        if (!CommandLineOptions.Instance.AutomationMode)
            return ExternalControlResponse.Failure(request.RequestId, "automation_disabled", "Root upgrade requires an explicitly automated bootstrap child.");
        if (CheckRecoveryMutation(request.RequestId) is { } rejected) return rejected;
        try
        {
            token.ThrowIfCancellationRequested();
            var childDirectory = Path.TrimEndingDirectorySeparator(Path.GetFullPath(AppContext.BaseDirectory));
            if (!_instances.TryGetConnectedRoot(out var root) || root is null)
                throw new InvalidOperationException("No authenticated root is connected.");
            var rootSession = ExternalControlRecovery.GetRootSessionId(root, _instances.Context.WindowsSessionId);
            using var process = Process.GetProcessById(root.ProcessId);
            // Retain the native handle before identity reads and the await; Kill/Wait must use this lifetime.
            // The borrowed SafeHandle is owned and disposed only by Process.
            _ = process.SafeHandle;
            var rootPath = process.MainModule?.FileName;
            if (process.HasExited || process.Id == Environment.ProcessId || process.SessionId != rootSession
                || rootPath is null || !string.Equals(Path.GetFileName(rootPath), "BetterGI.exe", StringComparison.OrdinalIgnoreCase)
                || root.StartedAt == default || process.StartTime.ToUniversalTime() != root.StartedAt.UtcDateTime)
                throw new InvalidOperationException("The connected root native identity changed.");
            var rootPlan = ExternalControlRecovery.CreateValidatedRecoveryPlan(Path.GetDirectoryName(rootPath)!,
                request.RootUpgrade!.ExeSha256, request.RootUpgrade.DllSha256);
            request.RootUpgrade!.Verify(process.Id, process.SessionId, process.StartTime.ToUniversalTime().ToFileTimeUtc(),
                rootPlan.AppDirectory, rootPlan.ExeSha256, rootPlan.DllSha256);
            if (string.Equals(rootPlan.AppDirectory, childDirectory, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(Directory.GetParent(rootPlan.AppDirectory)?.Parent?.FullName,
                    Directory.GetParent(childDirectory)?.Parent?.FullName, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Upgrade requires a distinct sibling bootstrap package.");

            var ui = System.Windows.Application.Current?.Dispatcher
                ?? throw new InvalidOperationException("The application dispatcher is unavailable.");
            var retained = await ui.InvokeAsync(() =>
            {
                var runtime = _serviceProvider.GetRequiredService<BetterGenshinImpact.GameTask.Runtime.GameRuntimeService>();
                return _restartReservation.TryLaunch(() => ReserveIdleRuntimeRestart(runtime),
                    () => ReleaseIdleRuntimeRestart(runtime), () => HasOtherRestartWork()
                        || !_instances.TryGetConnectedRoot(out var latest) || latest is null
                        || latest.ProcessId != root.ProcessId || latest.StartedAt != root.StartedAt
                        || latest.WindowsSessionId != rootSession || process.HasExited,
                    () =>
                    {
                        // Root Dispose logs off the clone. Kill only this retained native root, never its process tree.
                        process.Kill(entireProcessTree: false);
                        return process;
                    }, commitBeforeLaunch: true);
            }, DispatcherPriority.Normal, token).Task.ConfigureAwait(false);
            if (retained is null)
                return ExternalControlResponse.Failure(request.RequestId, "busy", "The idle bootstrap reservation was not acquired.");
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(token);
            timeout.CancelAfter(TimeSpan.FromSeconds(2));
            await process.WaitForExitAsync(timeout.Token).ConfigureAwait(false);
            _applicationRestarting = true;
            return new ExternalControlResponse { RequestId = request.RequestId, Success = true, ShutdownAfterWrite = true,
                Status = await BuildStatusAsync(token).ConfigureAwait(false),
                Message = "Verified root exited; this reserved bootstrap child will exit after the response attempt. Observe both exits before staging. Store coherence remains unverified." };
        }
        catch (Exception error) when (IsRecoveryException(error))
        {
            _logger.LogWarning(error, "Root upgrade retirement failed or is uncertain for request {RequestId}", request.RequestId);
            // GuardRequestAsync also schedules child exit after any irreversible attempt, including failed response writes.
            return ExternalControlResponse.Failure(request.RequestId,
                _restartReservation.Committed ? "upgrade_retirement_unknown" : "upgrade_retirement_refused",
                "Preserve all packages and inspect the exact process lifetimes; do not retry this request.");
        }
    }
}
