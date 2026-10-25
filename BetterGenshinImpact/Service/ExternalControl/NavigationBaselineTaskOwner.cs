using System;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.Core.Capture;
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
    /// <summary>Only one retained runtime binding; a new ordinary run replaces the previous predecessor.</summary>
    private NavigationBaselineOwnerBinding? _binding;
    /// <summary>Opaque evidence identity is stable only while the exact retained reference tuple matches.</summary>
    private Guid _runtimeIdentity;
    /// <summary>Callback includes native disposal and TaskRunner return; not an OS release acknowledgement.</summary>
    private long _cleanupReturnedAtTicks;
    /// <summary>True through cleanup, including terminal status assignment.</summary>
    internal bool Running { get { lock (_gate) return _execution is { IsCompleted: false }; } }

    /// <summary>Detach arrays, omitting bulk result fields from legacy-sized ordinary status.</summary>
    internal NavigationBaselineStatus Snapshot(bool includeResult = false)
    {
        lock (_gate)
            return _status with { Result = includeResult && _status.Result is { } result
                ? result with { Samples = [.. result.Samples], VerificationSamples = [.. result.VerificationSamples], Legs = [.. result.Legs], Waypoint = result.Waypoint?.Snapshot() } : null };
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
        TimeSpan? timeout = null, string timingContract = NavigationBaselineTiming.V1,
        string capturePolicy = NavigationBaselineCapturePolicy.Shared, string routeProfile = NavigationBaselineTask.ProfileId, string? shadowCapture = null) =>
        TryStartCore(gameProcessId, sessionId, (id, token, phase, _) => execute(id, token, phase),
            timeout, timingContract, capturePolicy, routeProfile, binding: null, predecessorRunId: null, shadowCapture: shadowCapture);

    /// <summary>Only trusted service wiring supplies reference identities; linkage is captured atomically with owner admission.</summary>
    internal bool TryStartBound(int gameProcessId, int sessionId,
        NavigationBaselineOwnerBinding? binding, string? predecessorRunId,
        Func<string, CancellationToken, Action<string>, NavigationBaselineContinuationLink?, Task<(SoloTaskRunResult TaskResult, NavigationBaselineRunResult? Baseline)>> execute,
        TimeSpan? timeout = null, string timingContract = NavigationBaselineTiming.V1,
        string capturePolicy = NavigationBaselineCapturePolicy.Shared, string routeProfile = NavigationBaselineTask.ProfileId, string? shadowCapture = null) =>
        TryStartCore(gameProcessId, sessionId, execute, timeout, timingContract, capturePolicy, routeProfile, binding: binding, predecessorRunId: predecessorRunId, shadowCapture: shadowCapture);

    /// <summary>One lock covers completed-predecessor validation, snapshot, replacement and new callback scheduling.</summary>
    private bool TryStartCore(int gameProcessId, int sessionId,
        Func<string, CancellationToken, Action<string>, NavigationBaselineContinuationLink?, Task<(SoloTaskRunResult TaskResult, NavigationBaselineRunResult? Baseline)>> execute,
        TimeSpan? timeout, string timingContract, string capturePolicy, string routeProfile,
        NavigationBaselineOwnerBinding? binding, string? predecessorRunId, string? shadowCapture)
    {
        NavigationBaselineShadowMode.Validate(shadowCapture, timingContract, capturePolicy);
        var route = NavigationBaselineRouteProfile.Resolve(routeProfile, timingContract, capturePolicy);
        if (!NavigationBaselineTiming.IsSupported(timingContract)) throw new ArgumentException("unsupported_timing_contract", nameof(timingContract));
        if (!NavigationBaselineCapturePolicy.IsSupported(capturePolicy)) throw new ArgumentException("unsupported_capture_policy", nameof(capturePolicy));
        if (gameProcessId <= 0 || sessionId <= 0) throw new ArgumentOutOfRangeException(nameof(gameProcessId));
        // Host seed admission uses the same complete immutable binding as both later directions.
        if (binding?.SourcePolicy is not null && (!binding.Complete || !route.SupportsHostContinuation
            || timingContract != NavigationBaselineTiming.V4 || capturePolicy != NavigationBaselineCapturePolicy.TaskOwnedTimer
            || shadowCapture is not null)) throw new InvalidOperationException("continuation_host_contract_mismatch");
        lock (_gate)
        {
            if (_execution is { IsCompleted: false }) return false;
            NavigationBaselineContinuationLink? continuation = null;
            if (route.RequiresPredecessor)
            {
                if (binding is not { Complete: true } || _binding is not { Complete: true }
                    || !_binding.Matches(binding) || _runtimeIdentity == Guid.Empty)
                    throw new InvalidOperationException("continuation_runtime_identity_changed_or_unavailable");
                if (predecessorRunId != _status.RunId || _status.State != "completed"
                    || !route.AllowsPredecessor(_status.ProfileId) || _status.TimingContract != NavigationBaselineTiming.V4
                    || _status.CapturePolicy != NavigationBaselineCapturePolicy.TaskOwnedTimer || !VerifiedResult(_status.Result)
                    || _cleanupReturnedAtTicks <= 0 || _status.Result!.Evidence!.ReadbackMode != binding.ReadbackMode
                    || _status.SourcePolicy != binding.SourcePolicy || _status.Result.SourcePolicy != binding.SourcePolicy
                    || _status.Result.Evidence.SourcePolicy != binding.SourcePolicy
                    || binding.SourcePolicy is not null && (_status.ShadowCapture is not null || _status.Result.Evidence.ShadowCapture is not null))
                    throw new InvalidOperationException("continuation_predecessor_not_verified");
                continuation = new() { PredecessorRunId = _status.RunId!, PredecessorProfileId = _status.ProfileId, PredecessorEvidence = _status.Result.Evidence,
                    PredecessorFinalSource = _status.Result.Samples[^1].Source, RuntimeIdentity = _runtimeIdentity,
                    PredecessorCleanupReturnedAtTicks = _cleanupReturnedAtTicks, ChildProcessId = binding.ChildProcessId,
                    ChildNonce = binding.ChildNonce, WindowsSessionId = binding.WindowsSessionId,
                    GameProcessId = binding.GameProcessId, GameStartedAtUtcTicks = binding.GameStartedAtUtcTicks,
                    CaptureType = binding.CaptureType, ReadbackMode = binding.ReadbackMode,
                    SourcePolicy = binding.SourcePolicy, ChildAssemblySha256 = binding.ChildAssemblySha256?.ToLowerInvariant() };
            }
            else if (predecessorRunId is not null) throw new InvalidOperationException("unexpected_continuation_predecessor");
            if (binding is not null && (binding.GameProcessId != gameProcessId || binding.WindowsSessionId != sessionId))
                throw new InvalidOperationException("continuation_binding_identity_mismatch");
            if (binding is null || _binding is null || !_binding.Matches(binding)) _runtimeIdentity = Guid.NewGuid();
            _binding = binding; _cleanupReturnedAtTicks = 0;
            var stop = new CancellationTokenSource();
            var bound = timeout ?? NavigationBaselineTask.Timeout;
            var deadline = new CancellationTokenSource(bound);
            var started = Stopwatch.GetTimestamp();
            var runId = Guid.NewGuid().ToString("N");
            _stop = stop;
            _status = new() { SourcePolicy = binding?.SourcePolicy, ShadowCapture = shadowCapture, ProfileId = route.Id, RunId = runId, Continuation = continuation, TimingContract = timingContract, CapturePolicy = capturePolicy, State = "running", Phase = "starting", GameProcessId = gameProcessId,
                WindowsSessionId = sessionId, StartedAtUtc = DateTimeOffset.UtcNow };
            _execution = Task.Run(() => ExecuteAsync(runId, started, bound, stop, deadline, continuation, execute));
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

    /// <summary>Only the host final-only expiry branch can publish an endpoint ticket as successful cleanup.</summary>
    internal static bool EndpointClosureConsistent(NavigationBaselineRunResult result)
    {
        if (result.Evidence?.EndpointClosure != result.EndpointClosure) return false;
        if (result.EndpointClosure is not { } closure) return true;
        return result.SourcePolicy == DesktopCapturePolicy.HostAcquisitionV1
            && result.TimingContract == NavigationBaselineTiming.V4
            && result.CapturePolicy == NavigationBaselineCapturePolicy.TaskOwnedTimer
            && result.ProfileId is NavigationBaselineTask.ProfileId or NavigationBaselineRouteProfile.CourtyardReturnId or NavigationBaselineRouteProfile.CourtyardForwardId
            && closure.ConfirmsClosure;
    }

    /// <summary>Independently reject incomplete measured/evidence results, including otherwise successful TaskRunner execution.</summary>
    internal static bool VerifiedResult(NavigationBaselineRunResult? result) => result is
        { Verified: true, Error: null, InputReleaseError: null, Evidence.Complete: true, InitialSample: not null }
        && SourcePolicyConsistent(result) && EndpointClosureConsistent(result)
        && NavigationBaselineRouteProfile.IsSupported(result.ProfileId)
        && NavigationBaselineRouteProfile.VerifiedContinuation(result)
        && NavigationBaselineTiming.IsSupported(result.TimingContract)
        && NavigationBaselineCapturePolicy.IsSupported(result.CapturePolicy)
        && result.ObservationCount is > 0 and <= NavigationBaselineTask.MaximumObservations
        && double.IsFinite(result.ElapsedMs) && result.ElapsedMs is >= 0 and < 30_000
        && NavigationBaselineTask.PoseRejection(result.InitialSample, ResultRoute(result).InitialLeg) is null
        && double.Hypot(result.InitialSample.X - ResultRoute(result).InitialLeg.StartX, result.InitialSample.Y - ResultRoute(result).InitialLeg.StartY) <= 1.5
        && NavigationBaselineTask.FinalRejection(result.Samples, ResultRoute(result).FinalLeg) is null
        && result.VerificationSamples.SequenceEqual(result.Samples)
        && result.Samples.All(sample => sample.Source.StrictlyNewerThan(result.InitialSample.Source))
        && !string.IsNullOrEmpty(result.Evidence.InitialImagePath) && !string.IsNullOrEmpty(result.Evidence.FinalImagePath)
        && !string.IsNullOrEmpty(result.Evidence.JournalPath)
        && result.Evidence.JournalSha256.Length == 64 && result.Evidence.InitialImageSha256?.Length == 64
        && result.Evidence.FinalImageSha256?.Length == 64;

    /// <summary>A full result cannot silently swap source authority or label host pixels as a historical WGC run.</summary>
    internal static bool SourcePolicyConsistent(NavigationBaselineRunResult result)
    {
        if (result.Evidence?.SourcePolicy != result.SourcePolicy) return false;
        var samples = result.VerificationSamples.Prepend(result.InitialSample).Where(sample => sample is not null);
        if (result.SourcePolicy is null) return samples.All(sample => sample!.HostSnapshot is null)
            && (result.Continuation is null || result.Continuation.Version == 1
                && result.Continuation.SourcePolicy is null && result.Continuation.ChildAssemblySha256 is null);
        return result.SourcePolicy == DesktopCapturePolicy.HostAcquisitionV1
            && result.TimingContract == NavigationBaselineTiming.V4
            && result.CapturePolicy == NavigationBaselineCapturePolicy.TaskOwnedTimer
            && NavigationBaselineRouteProfile.IsSupported(result.ProfileId) && ResultRoute(result).SupportsHostContinuation
            && result.Evidence is { ReadbackMode: null, ShadowCapture: null }
            && (result.ProfileId == NavigationBaselineTask.ProfileId ? result.Continuation is null
                : result.Continuation is { HasHostSourceContract: true })
            && samples.All(sample => sample!.HostSnapshot is not null && sample.HasValidSourceShape);
    }

    /// <summary>Used only after IsSupported and selected-contract checks in owner validation.</summary>
    private static NavigationBaselineRouteProfile ResultRoute(NavigationBaselineRunResult result) =>
        NavigationBaselineRouteProfile.Resolve(result.ProfileId, result.TimingContract, result.CapturePolicy);

    /// <summary>Publish terminal state only after callback cleanup; monotonic elapsed time also guards delayed cancellation timers.</summary>
    private async Task ExecuteAsync(string runId, long started, TimeSpan timeout, CancellationTokenSource stop,
        CancellationTokenSource deadline, NavigationBaselineContinuationLink? continuation,
        Func<string, CancellationToken, Action<string>, NavigationBaselineContinuationLink?, Task<(SoloTaskRunResult TaskResult, NavigationBaselineRunResult? Baseline)>> execute)
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
                }, continuation).ConfigureAwait(false);
            }
            catch (OperationCanceledException) { taskResult = new() { Outcome = SoloTaskRunOutcome.Cancelled }; }
            catch (Exception exception) { taskResult = new() { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = exception.GetBaseException().Message }; }
            lock (_gate)
            {
                if (!ReferenceEquals(_stop, stop)) return;
                _cleanupReturnedAtTicks = Stopwatch.GetTimestamp();
                var expired = deadline.IsCancellationRequested || Stopwatch.GetElapsedTime(started) >= timeout;
                var contractMatches = baseline is null || baseline.TimingContract == _status.TimingContract;
                var routeMatches = baseline is null || baseline.ProfileId == _status.ProfileId;
                var continuationMatches = baseline is null || baseline.Continuation == continuation;
                var captureMatches = baseline is null || baseline.CapturePolicy == _status.CapturePolicy;
                var sourcePolicyMatches = baseline is null || baseline.SourcePolicy == _status.SourcePolicy;
                var verified = taskResult.Outcome == SoloTaskRunOutcome.Completed && taskResult.ErrorMessage is null
                    && contractMatches && captureMatches && sourcePolicyMatches && routeMatches && continuationMatches && VerifiedResult(baseline);
                var state = expired ? "failed" : stop.IsCancellationRequested || taskResult.Outcome == SoloTaskRunOutcome.Cancelled
                    ? "cancelled" : verified ? "completed" : "failed";
                var error = expired ? "baseline_deadline_exceeded" : state == "cancelled" ? "baseline_cancelled"
                    : state == "completed" ? null : !contractMatches ? "baseline_timing_contract_mismatch"
                    : !sourcePolicyMatches ? "baseline_source_policy_mismatch" : !captureMatches ? "baseline_capture_policy_mismatch" : !routeMatches ? "baseline_route_profile_mismatch"
                    : !continuationMatches ? "baseline_continuation_mismatch" : baseline?.Error ?? taskResult.ErrorMessage
                    ?? (taskResult.Outcome == SoloTaskRunOutcome.Rejected ? "task_ownership_rejected" : "baseline_result_unverified");
                if (error is { Length: > 512 }) error = error[..512];
                baseline ??= new() { SourcePolicy = _status.SourcePolicy, ProfileId = _status.ProfileId, Continuation = continuation, Phase = _status.Phase, TimingContract = _status.TimingContract, CapturePolicy = _status.CapturePolicy };
                baseline = baseline with { Verified = state == "completed", Error = error,
                    Samples = state == "completed" ? [.. baseline.Samples] : [], VerificationSamples = [.. baseline.VerificationSamples], Legs = [.. baseline.Legs], Waypoint = baseline.Waypoint?.Snapshot() };
                _status = _status with { State = state, Phase = state == "completed" ? "completed" : _status.Phase,
                    Error = error, FinishedAtUtc = DateTimeOffset.UtcNow, ObservationCount = baseline.ObservationCount,
                    EvidenceComplete = baseline.Evidence?.Complete == true, ReadbackMode = baseline.Evidence?.ReadbackMode, Result = baseline };
                _stop = null;
            }
        }
    }
}
