using System;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.SoloTask.Execution;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Owns one agent task until TaskRunner has finished releasing input and its runtime lease.</summary>
internal sealed class AgentStreamTaskOwner
{
    /// <summary>Protects one coherent ownership/status snapshot across the task and pipe threads.</summary>
    private readonly object _sync = new();
    /// <summary>Independent lifetime; completing the launch request must not cancel the stream.</summary>
    private CancellationTokenSource? _cancellation;
    /// <summary>The complete execution and cleanup operation, not merely its dispatch.</summary>
    private Task? _execution;
    /// <summary>Current machine-readable stream state.</summary>
    private string _state = "idle";
    /// <summary>Most recent failure or rejected task result.</summary>
    private string? _error;
    /// <summary>Input permission is immutable for one running task.</summary>
    private bool _enableInput;
    /// <summary>Preprocessing is fixed for a lease and retained afterward for last-run diagnostics.</summary>
    private string _observationProfile = AgentObservationProfile.Legacy;

    /// <summary>Return a consistent task ownership snapshot without touching UI or input.</summary>
    internal AgentStreamTaskSnapshot Snapshot()
    {
        lock (_sync) return new(_execution is { IsCompleted: false }, _state, _error, _enableInput, _observationProfile);
    }

    /// <summary>Claim a task once; the executor reports readiness only after its pipe exists.</summary>
    internal bool TryStart(bool enableInput, Func<CancellationToken, Action, Task<SoloTaskRunResult>> execute,
        string? observationProfile = AgentObservationProfile.Legacy)
    {
        var profile = AgentObservationProfile.Normalize(observationProfile);
        lock (_sync)
        {
            if (_execution is { IsCompleted: false }) return false;
            var source = new CancellationTokenSource();
            _cancellation = source;
            _state = "starting";
            _error = null;
            _enableInput = enableInput;
            _observationProfile = profile;
            _execution = Task.Run(() => ExecuteAsync(source, execute));
            return true;
        }
    }

    /// <summary>Cancel only this owner's task, preserving any unrelated task/runtime.</summary>
    internal void Cancel()
    {
        CancellationTokenSource? source;
        lock (_sync)
        {
            source = _cancellation;
            if (source is not null && _execution is { IsCompleted: false }) _state = "stopping";
        }
        CancelSource(source);
    }

    /// <summary>Keep the lease busy until its executor's TaskRunner cleanup has completed.</summary>
    internal async Task StopAsync(CancellationToken cancellationToken)
    {
        Task? execution;
        CancellationTokenSource? source;
        lock (_sync)
        {
            execution = _execution;
            source = _cancellation;
            if (source is not null && execution is { IsCompleted: false }) _state = "stopping";
        }
        CancelSource(source);
        if (execution is not null) await execution.WaitAsync(cancellationToken).ConfigureAwait(false);
    }

    /// <summary>A completion/disposal race must never cancel a newer owner or fail a completed stop.</summary>
    private static void CancelSource(CancellationTokenSource? source)
    {
        try { source?.Cancel(); }
        catch (ObjectDisposedException) { /* Completion won the race; the task is already drained. */ }
    }

    /// <summary>Observe all outcomes and update status only for the still-current lease.</summary>
    private async Task ExecuteAsync(CancellationTokenSource source,
        Func<CancellationToken, Action, Task<SoloTaskRunResult>> execute)
    {
        SoloTaskRunResult result;
        try
        {
            result = await execute(source.Token, () =>
            {
                lock (_sync)
                    if (ReferenceEquals(_cancellation, source) && !source.IsCancellationRequested)
                        _state = "listening";
            }).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            result = new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Cancelled };
        }
        catch (Exception exception)
        {
            result = new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Faulted,
                ErrorMessage = exception.GetBaseException().Message };
        }
        lock (_sync)
        {
            if (ReferenceEquals(_cancellation, source))
            {
                _state = result.Outcome switch
                {
                    SoloTaskRunOutcome.Faulted => "failed",
                    SoloTaskRunOutcome.Rejected => "rejected",
                    SoloTaskRunOutcome.Cancelled => "stopped",
                    _ => "completed"
                };
                _error = result.ErrorMessage;
                _enableInput = false;
                _cancellation = null;
            }
        }
        source.Dispose();
    }
}

/// <summary>Small immutable ownership/status value exposed by the external-control service.</summary>
internal sealed record AgentStreamTaskSnapshot(bool Running, string State, string? Error, bool EnableInput,
    string ObservationProfile)
{
    /// <summary>Only an active matching task may be joined; stopping must finish before another start.</summary>
    internal bool CanReuse(bool enableInput, string observationProfile) => Running
        && State is "starting" or "listening" && EnableInput == enableInput
        && string.Equals(ObservationProfile, observationProfile, StringComparison.Ordinal);
}
