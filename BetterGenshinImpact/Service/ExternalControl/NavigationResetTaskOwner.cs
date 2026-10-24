using System;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.NavigationReset;
using BetterGenshinImpact.GameTask.SoloTask.Execution;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Own one fixed reset through TaskRunner cleanup; never publish a merely dispatched task as success.</summary>
internal sealed class NavigationResetTaskOwner
{
    /// <summary>Protect a coherent lease, run identity and status across pipe/task threads.</summary>
    private readonly object _sync = new();
    /// <summary>User/service stop source, distinct from the whole-operation deadline.</summary>
    private CancellationTokenSource? _cancellation;
    /// <summary>The complete operation, including TaskRunner cleanup.</summary>
    private Task? _execution;
    /// <summary>Last immutable status; completed evidence remains readable after the lease ends.</summary>
    private NavigationResetStatus _status = new();
    /// <summary>True until every owned task resource has drained.</summary>
    internal bool Running { get { lock (_sync) return _execution is { IsCompleted: false }; } }
    /// <summary>Return detached evidence, optionally excluding diagnostics for legacy-sized ordinary status responses.</summary>
    internal NavigationResetStatus Snapshot(bool includeDiagnostics = true)
    {
        lock (_sync) return _status with { Samples = [.. _status.Samples],
            VerificationDiagnostics = includeDiagnostics ? [.. (_status.VerificationDiagnostics ?? [])] : null };
    }

    /// <summary>Read only a pinned terminal run after cleanup; never substitute a newer run or partial evidence.</summary>
    internal string? TryGetDiagnostics(string runId, out NavigationResetStatus? status)
    {
        lock (_sync)
        {
            status = null;
            if (!string.Equals(runId, _status.RunId, StringComparison.Ordinal)) return "navigation_reset_run_mismatch";
            if (_execution is { IsCompleted: false } || _status.State is not ("completed" or "failed" or "cancelled"))
                return "navigation_reset_not_terminal";
            status = Snapshot();
            return null;
        }
    }

    /// <summary>Claim a single run and its finite deadline before dispatching any work.</summary>
    internal bool TryStart(double yaw, int gameProcessId, int sessionId,
        Func<CancellationToken, Action<string>, Task<(SoloTaskRunResult Result, NavigationResetSample[]? Samples,
            NavigationResetVerificationDiagnostic[] Diagnostics)>> execute,
        TimeSpan? timeout = null)
    {
        if (!NavigationResetTask.IsValidYaw(yaw)) throw new ArgumentOutOfRangeException(nameof(yaw));
        lock (_sync)
        {
            if (_execution is { IsCompleted: false }) return false;
            var stop = new CancellationTokenSource();
            var deadline = new CancellationTokenSource(timeout ?? NavigationResetTask.Timeout);
            _cancellation = stop;
            _status = new NavigationResetStatus { RunId = Guid.NewGuid().ToString("N"), State = "running", Phase = "starting",
                TargetYawDegrees = yaw, GameProcessId = gameProcessId, WindowsSessionId = sessionId,
                StartedAtUtc = DateTimeOffset.UtcNow };
            _execution = Task.Run(() => ExecuteAsync(stop, deadline, execute));
            return true;
        }
    }

    /// <summary>Cancel this reset only; input/resource ownership is retained until the executor finishes.</summary>
    internal void Cancel()
    {
        CancellationTokenSource? source;
        lock (_sync) source = _cancellation;
        try { source?.Cancel(); }
        catch (ObjectDisposedException) { /* The same operation already finished cleanup. */ }
    }

    /// <summary>Drain the complete operation without cancelling a newer run after a completion race.</summary>
    internal async Task StopAsync(CancellationToken ct)
    {
        Task? execution;
        CancellationTokenSource? source;
        lock (_sync) { execution = _execution; source = _cancellation; }
        try { source?.Cancel(); }
        catch (ObjectDisposedException) { /* Completion already drained this source. */ }
        if (execution is not null) await execution.WaitAsync(ct).ConfigureAwait(false);
    }

    /// <summary>Observe rejection, timeout and cancellation, and accept only verified samples after native cleanup.</summary>
    private async Task ExecuteAsync(CancellationTokenSource stop, CancellationTokenSource deadline,
        Func<CancellationToken, Action<string>, Task<(SoloTaskRunResult Result, NavigationResetSample[]? Samples,
            NavigationResetVerificationDiagnostic[] Diagnostics)>> execute)
    {
        using (stop)
        using (deadline)
        using (var linked = CancellationTokenSource.CreateLinkedTokenSource(stop.Token, deadline.Token))
        {
            SoloTaskRunResult result;
            NavigationResetSample[]? samples = null;
            NavigationResetVerificationDiagnostic[] diagnostics = [];
            try
            {
                (result, samples, diagnostics) = await execute(linked.Token, phase =>
                {
                    lock (_sync)
                        if (ReferenceEquals(_cancellation, stop) && !linked.IsCancellationRequested)
                            _status = _status with { Phase = phase };
                }).ConfigureAwait(false);
            }
            catch (OperationCanceledException) { result = new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Cancelled }; }
            catch (Exception exception)
            {
                result = new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = exception.GetBaseException().Message };
            }
            lock (_sync)
            {
                if (!ReferenceEquals(_cancellation, stop)) return;
                var verified = result.Outcome == SoloTaskRunOutcome.Completed && result.ErrorMessage is null
                    && samples is not null && NavigationResetTask.AcceptSamples(samples, _status.TargetYawDegrees);
                var state = deadline.IsCancellationRequested ? "failed"
                    : stop.IsCancellationRequested || result.Outcome == SoloTaskRunOutcome.Cancelled ? "cancelled"
                    : verified ? "completed" : "failed";
                var error = deadline.IsCancellationRequested ? "reset_deadline_exceeded"
                    : state == "cancelled" ? "reset_cancelled"
                    : state == "completed" ? null : result.ErrorMessage ?? (result.Outcome == SoloTaskRunOutcome.Rejected
                        ? "task_ownership_rejected" : "reset_result_unverified");
                _status = _status with { State = state, Phase = state == "completed" ? "completed" : _status.Phase,
                    Error = error is { Length: > 512 } ? error[..512] : error,
                    Samples = state == "completed" ? [.. samples!] : [],
                    VerificationDiagnostics = [.. diagnostics.AsSpan(0, Math.Min(diagnostics.Length, NavigationResetTask.MaximumVerificationAttempts))],
                    FinishedAtUtc = DateTimeOffset.UtcNow };
                _cancellation = null;
            }
        }
    }
}
