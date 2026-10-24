using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>Bound preparation age/pending waits and one recognized map-close response; native work stays on the calling task and never outlives a probe.</summary>
internal static class NavigationResetPreparationReadiness
{
    /// <summary>Readiness shares the owner's existing cancellation and has its own smaller three-second budget.</summary>
    internal static readonly TimeSpan Timeout = TimeSpan.FromSeconds(3);
    /// <summary>Bound synchronous capture work even if timers or scheduler callbacks are delayed.</summary>
    internal const int MaximumAttempts = 25;
    /// <summary>Allow a new native frame between rejected observations without polling continuously.</summary>
    internal const int RetryDelayMilliseconds = 120;

    /// <summary>Only explicit age/polling-pending/one-shot-map-settling outcomes retry; all native/recognition exceptions propagate unchanged.</summary>
    internal static async Task WaitAsync(Func<int, CancellationToken, NavigationResetPreparationState> probe,
        Func<int, CancellationToken, Task> delay, CancellationToken ct, Func<long>? timestamp = null)
    {
        timestamp ??= Stopwatch.GetTimestamp;
        var started = timestamp();
        var previous = started;
        var attempts = 0;
        NavigationResetPreparationState? lastState = null;
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(Timeout);

        // Check both cancellation and the monotonic clock after native work: a delayed timer cannot admit late success.
        void CheckBudget()
        {
            ct.ThrowIfCancellationRequested();
            var now = timestamp();
            if (now < previous) throw new InvalidOperationException("preparation_clock_regressed");
            previous = now;
            if (deadline.IsCancellationRequested || Stopwatch.GetElapsedTime(started, now) >= Timeout)
                throw Failure(attempts, lastState);
        }

        try
        {
            while (attempts < MaximumAttempts)
            {
                CheckBudget();
                var state = probe(++attempts, deadline.Token);
                // No asynchronous capture, detached callback or stale success survives this point.
                if (state is not NavigationResetPreparationState.Ready and not NavigationResetPreparationState.SourceAge
                    and not NavigationResetPreparationState.ReadbackPending and not NavigationResetPreparationState.MapClosing)
                    throw new InvalidOperationException("invalid_preparation_probe_state");
                lastState = state;
                CheckBudget();
                if (state == NavigationResetPreparationState.Ready) return;
                if (attempts < MaximumAttempts) await delay(RetryDelayMilliseconds, deadline.Token);
            }
        }
        catch (OperationCanceledException error) when (IsOwnDeadlineCancellation(error, ct, deadline.Token))
        {
            throw Failure(attempts, lastState);
        }
        ct.ThrowIfCancellationRequested();
        throw Failure(attempts, lastState);
    }

    /// <summary>Only this linked window's cancellation can become its timeout; unrelated native and owner cancellations retain provenance.</summary>
    internal static bool IsOwnDeadlineCancellation(OperationCanceledException error, CancellationToken owner, CancellationToken deadline) =>
        !owner.IsCancellationRequested && deadline.IsCancellationRequested && error.CancellationToken == deadline;

    /// <summary>A stable preparation-only timeout remains the outer/base message consumed by reset status.</summary>
    private static NavigationResetPreparationTimeoutException Failure(int attempts, NavigationResetPreparationState? lastState) => new(attempts, lastState);
}

/// <summary>Typed preparation outcomes distinguish fresh world readiness, no-pixel/age waits, and the sole map-close response.</summary>
internal enum NavigationResetPreparationState
{
    /// <summary>All source, target and strict world checks succeeded on this same frame.</summary>
    Ready,
    /// <summary>All hard checks passed, but the conservative source age exceeded the unchanged 500ms threshold.</summary>
    SourceAge,
    /// <summary>Explicit PollSingleV1 submission has no pixels; no source/world readiness has been established.</summary>
    ReadbackPending,
    /// <summary>One positively identified map close was attempted; only newer settled world pixels can finish.</summary>
    MapClosing
}

/// <summary>Distinguish this bounded readiness deadline from a timeout thrown by native capture or recognition.</summary>
/// <param name="attempts">Number of synchronous probes actually entered.</param>
/// <param name="lastState">Actual last completed probe outcome, or null before a probe has returned.</param>
internal sealed class NavigationResetPreparationTimeoutException(int attempts, NavigationResetPreparationState? lastState) : TimeoutException(
    $"preparation_readiness_timeout; attempts={attempts}; last={lastState switch { NavigationResetPreparationState.SourceAge => "source_age_exceeds_500ms", NavigationResetPreparationState.ReadbackPending => "readback_pending", NavigationResetPreparationState.Ready => "ready_but_expired", NavigationResetPreparationState.MapClosing => "map_close_not_world_ready", _ => "no_completed_probe" }}");
