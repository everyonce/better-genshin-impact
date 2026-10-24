using System;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.GameTask.SoloTask.Execution;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Own the single fixed leg through native/evidence/TaskRunner cleanup; dispatch never implies arrival.</summary>
internal sealed class NavigationBaselineTaskOwner
{
    /// <summary>Protect one coherent run/status/cancellation identity.</summary>
    private readonly object _gate = new();
    /// <summary>Caller/service cancellation, separate from the whole-operation deadline.</summary>
    private CancellationTokenSource? _stop;
    /// <summary>Complete execution, including all cleanup and evidence publication.</summary>
    private Task? _execution;
    /// <summary>Last terminal result remains available until a new run is explicitly requested.</summary>
    private NavigationBaselineStatus _status = new();
    /// <summary>True through cleanup, including terminal status assignment.</summary>
    internal bool Running { get { lock (_gate) return _execution is { IsCompleted: false }; } }

    /// <summary>Detach arrays, omitting bulk result fields from legacy-sized ordinary status.</summary>
    internal NavigationBaselineStatus Snapshot(bool includeResult = false)
    {
        lock (_gate)
            return _status with { Result = includeResult && _status.Result is { } result
                ? result with { Samples = [.. result.Samples], VerificationSamples = [.. result.VerificationSamples] } : null };
    }

    /// <summary>Return only the requested complete terminal run; no partial result or substituted newer run.</summary>
    internal string? TryGetResult(string runId, out NavigationBaselineStatus? status)
    {
        lock (_gate)
        {
            status = null;
            if (!string.Equals(runId, _status.RunId, StringComparison.Ordinal)) return "navigation_baseline_run_mismatch";
            if (_execution is { IsCompleted: false } || _status.State is not ("completed" or "failed" or "cancelled"))
                return "navigation_baseline_not_terminal";
            status = Snapshot(true);
            return null;
        }
    }

    /// <summary>Claim one fixed route/timing run before dispatching TaskRunner work.</summary>
    internal bool TryStart(int gameProcessId, int sessionId,
        Func<string, CancellationToken, Action<string>, Task<(SoloTaskRunResult TaskResult, NavigationBaselineRunResult? Baseline)>> execute,
        TimeSpan? timeout = null, string timingContract = NavigationBaselineTiming.V1)
    {
        if (!NavigationBaselineTiming.IsSupported(timingContract)) throw new ArgumentException("unsupported_timing_contract", nameof(timingContract));
        if (gameProcessId <= 0 || sessionId <= 0) throw new ArgumentOutOfRangeException(nameof(gameProcessId));
        lock (_gate)
        {
            if (_execution is { IsCompleted: false }) return false;
            var stop = new CancellationTokenSource();
            var bound = timeout ?? NavigationBaselineTask.Timeout;
            var deadline = new CancellationTokenSource(bound);
            var started = Stopwatch.GetTimestamp();
            var runId = Guid.NewGuid().ToString("N");
            _stop = stop;
            _status = new() { RunId = runId, TimingContract = timingContract, State = "running", Phase = "starting", GameProcessId = gameProcessId,
                WindowsSessionId = sessionId, StartedAtUtc = DateTimeOffset.UtcNow };
            _execution = Task.Run(() => ExecuteAsync(runId, started, bound, stop, deadline, execute));
            return true;
        }
    }

    /// <summary>Cancel only the current lease; keep it owned until every native resource and input operation drains.</summary>
    internal void Cancel()
    {
        CancellationTokenSource? stop;
        lock (_gate) stop = _stop;
        try { stop?.Cancel(); }
        catch (ObjectDisposedException) { /* This exact run already drained. */ }
    }

    /// <summary>Drain the captured run rather than accidentally cancelling a newer run after a race.</summary>
    internal async Task StopAsync(CancellationToken ct)
    {
        Task? execution; CancellationTokenSource? stop;
        lock (_gate) { execution = _execution; stop = _stop; }
        try { stop?.Cancel(); }
        catch (ObjectDisposedException) { /* Completion disposed the captured cancellation source. */ }
        if (execution is not null) await execution.WaitAsync(ct).ConfigureAwait(false);
    }

    /// <summary>Independently reject incomplete measured/evidence results, including otherwise successful TaskRunner execution.</summary>
    internal static bool VerifiedResult(NavigationBaselineRunResult? result) => result is
        { Verified: true, Error: null, InputReleaseError: null, Evidence.Complete: true, InitialSample: not null }
        && NavigationBaselineTiming.IsSupported(result.TimingContract)
        && result.ObservationCount is > 0 and <= NavigationBaselineTask.MaximumObservations
        && double.IsFinite(result.ElapsedMs) && result.ElapsedMs is >= 0 and < 30_000
        && NavigationBaselineTask.PoseRejection(result.InitialSample) is null
        && double.Hypot(result.InitialSample.X - NavigationBaselineTask.StartX, result.InitialSample.Y - NavigationBaselineTask.StartY) <= 1.5
        && NavigationBaselineTask.FinalRejection(result.Samples) is null
        && result.VerificationSamples.SequenceEqual(result.Samples)
        && result.Samples.All(sample => sample.SourceEpoch == result.InitialSample.SourceEpoch
            && sample.SourceTimestamp100ns > result.InitialSample.SourceTimestamp100ns
            && sample.AcquiredAtStopwatchTicks > result.InitialSample.AcquiredAtStopwatchTicks)
        && !string.IsNullOrEmpty(result.Evidence.InitialImagePath) && !string.IsNullOrEmpty(result.Evidence.FinalImagePath)
        && !string.IsNullOrEmpty(result.Evidence.JournalPath)
        && result.Evidence.JournalSha256.Length == 64 && result.Evidence.InitialImageSha256?.Length == 64
        && result.Evidence.FinalImageSha256?.Length == 64;

    /// <summary>Publish terminal state only after callback cleanup; monotonic elapsed time also guards delayed cancellation timers.</summary>
    private async Task ExecuteAsync(string runId, long started, TimeSpan timeout, CancellationTokenSource stop,
        CancellationTokenSource deadline,
        Func<string, CancellationToken, Action<string>, Task<(SoloTaskRunResult TaskResult, NavigationBaselineRunResult? Baseline)>> execute)
    {
        using (stop)
        using (deadline)
        using (var linked = CancellationTokenSource.CreateLinkedTokenSource(stop.Token, deadline.Token))
        {
            SoloTaskRunResult taskResult;
            NavigationBaselineRunResult? baseline = null;
            try
            {
                (taskResult, baseline) = await execute(runId, linked.Token, phase =>
                {
                    lock (_gate) if (ReferenceEquals(_stop, stop) && !linked.IsCancellationRequested)
                        _status = _status with { Phase = phase };
                }).ConfigureAwait(false);
            }
            catch (OperationCanceledException) { taskResult = new() { Outcome = SoloTaskRunOutcome.Cancelled }; }
            catch (Exception exception) { taskResult = new() { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = exception.GetBaseException().Message }; }
            lock (_gate)
            {
                if (!ReferenceEquals(_stop, stop)) return;
                var expired = deadline.IsCancellationRequested || Stopwatch.GetElapsedTime(started) >= timeout;
                var contractMatches = baseline is null || baseline.TimingContract == _status.TimingContract;
                var verified = taskResult.Outcome == SoloTaskRunOutcome.Completed && taskResult.ErrorMessage is null
                    && contractMatches && VerifiedResult(baseline);
                var state = expired ? "failed" : stop.IsCancellationRequested || taskResult.Outcome == SoloTaskRunOutcome.Cancelled
                    ? "cancelled" : verified ? "completed" : "failed";
                var error = expired ? "baseline_deadline_exceeded" : state == "cancelled" ? "baseline_cancelled"
                    : state == "completed" ? null : !contractMatches ? "baseline_timing_contract_mismatch" : baseline?.Error ?? taskResult.ErrorMessage
                    ?? (taskResult.Outcome == SoloTaskRunOutcome.Rejected ? "task_ownership_rejected" : "baseline_result_unverified");
                if (error is { Length: > 512 }) error = error[..512];
                baseline ??= new() { Phase = _status.Phase, TimingContract = _status.TimingContract };
                baseline = baseline with { Verified = state == "completed", Error = error,
                    Samples = state == "completed" ? [.. baseline.Samples] : [], VerificationSamples = [.. baseline.VerificationSamples] };
                _status = _status with { State = state, Phase = state == "completed" ? "completed" : _status.Phase,
                    Error = error, FinishedAtUtc = DateTimeOffset.UtcNow, ObservationCount = baseline.ObservationCount,
                    EvidenceComplete = baseline.Evidence?.Complete == true, Result = baseline };
                _stop = null;
            }
        }
    }
}
