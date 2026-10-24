using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>Bound transient post-teleport recognition misses without retaining or relaxing any pose evidence.</summary>
internal static class NavigationResetPoseAcquisition
{
    /// <summary>One acquisition may wait for the minimap to settle, independently of the whole75-second reset deadline.</summary>
    internal static readonly TimeSpan SettleTimeout = TimeSpan.FromSeconds(3);
    /// <summary>Bound recognition work even if a test or delayed timer makes wall-clock cancellation late.</summary>
    internal const int MaximumAttempts = 25;
    /// <summary>Allow fresh native/game frames between failed observations, without busy polling.</summary>
    internal const int RetryDelayMilliseconds = 120;

    /// <summary>Retry only explicit unavailable observations; identity, terminal world and wrong-pose exceptions propagate immediately.</summary>
    internal static async Task<NavigationResetSample> ReadAsync(
        Func<CancellationToken, Task<NavigationResetPoseProbe>> probe,
        Func<int, CancellationToken, Task> delay, CancellationToken ct, TimeSpan? timeout = null,
        bool pollReadback = false, Func<int, CancellationToken, Task>? pendingDelay = null,
        Action<NavigationResetPollingDiagnostic>? observePolling = null, Func<long>? timestamp = null,
        Func<CancellationToken, Action, Task<NavigationResetPoseProbe>>? pollingProbe = null)
    {
        if (pollReadback)
        {
            if (timeout is { } supplied && supplied != SettleTimeout)
                throw new ArgumentException("poll_readback_requires_fixed_three_second_window", nameof(timeout));
            return await ReadPollingAsync(probe, delay, pendingDelay ?? throw new ArgumentNullException(nameof(pendingDelay)),
                ct, observePolling, timestamp, pollingProbe).ConfigureAwait(false);
        }
        // Blocking/default callers retain the original25-call loop, waits and cancellation behavior.
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(timeout ?? SettleTimeout);
        var started = Stopwatch.GetTimestamp();
        var attempts = 0;
        var lastReason = "no_observation";
        try
        {
            for (; attempts < MaximumAttempts;)
            {
                deadline.Token.ThrowIfCancellationRequested();
                attempts++;
                var observed = await probe(deadline.Token);
                // A synchronous/native operation may finish after cancellation; it cannot create late success.
                deadline.Token.ThrowIfCancellationRequested();
                if (observed.Sample is { } sample) return sample;
                lastReason = observed.RetryReason is { Length: > 200 } reason ? reason[..200]
                    : observed.RetryReason ?? "pose_unavailable";
                if (attempts < MaximumAttempts) await delay(RetryDelayMilliseconds, deadline.Token);
            }
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested && deadline.IsCancellationRequested)
        {
            // Preserve a bounded diagnostic as the base exception message used by TaskRunner/status.
            throw Failure(attempts, started, lastReason);
        }
        ct.ThrowIfCancellationRequested();
        throw Failure(attempts, started, lastReason);
    }

    /// <summary>Only native-validated metadata refunds a provisional observation in the opt-in path.</summary>
    private static async Task<NavigationResetSample> ReadPollingAsync(
        Func<CancellationToken, Task<NavigationResetPoseProbe>> probe,
        Func<int, CancellationToken, Task> delay, Func<int, CancellationToken, Task> pendingDelay,
        CancellationToken ct, Action<NavigationResetPollingDiagnostic>? observe, Func<long>? timestamp,
        Func<CancellationToken, Action, Task<NavigationResetPoseProbe>>? pollingProbe)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(SettleTimeout);
        var budget = new NavigationResetPollBudget(ct, deadline.Token, observe, timestamp);
        var started = Stopwatch.GetTimestamp();
        var lastReason = "no_observation";
        Exception? terminal = null;
        try
        {
            while (true)
            {
                NavigationResetPoseProbe observed;
                using (var reservation = budget.BeginPoll())
                {
                    // Native may call the real deadline guard again immediately before its camera dispatch.
                    observed = pollingProbe is null ? await probe(deadline.Token).ConfigureAwait(false)
                        : await pollingProbe(deadline.Token, budget.CheckBudget).ConfigureAwait(false);
                    if (observed.Outcome == NavigationResetPoseProbeOutcome.ValidatedReadbackPending)
                    {
                        if (observed.Sample is not null)
                            throw new InvalidOperationException("invalid_pending_pose_probe");
                        reservation.CompleteValidatedPending();
                    }
                    else if (observed.Outcome != NavigationResetPoseProbeOutcome.Observation)
                        throw new InvalidOperationException("invalid_pose_probe_outcome");
                }
                // Settlement precedes every await; late Pending/Ready still cannot become readiness.
                budget.CheckBudget();
                if (observed.Sample is { } sample) return sample;
                lastReason = observed.RetryReason is { Length: > 200 } reason ? reason[..200]
                    : observed.RetryReason ?? "pose_unavailable";
                var pending = observed.Outcome == NavigationResetPoseProbeOutcome.ValidatedReadbackPending;
                budget.EnsureNextPollAvailable();
                await budget.WaitAsync(pending ? NavigationResetPollBudget.PendingDelayMilliseconds : RetryDelayMilliseconds,
                    pending ? pendingDelay : delay).ConfigureAwait(false);
            }
        }
        catch (NavigationResetPollLimitException error)
        {
            terminal = Failure(budget.PollCount, started, lastReason + "; budget=" + error.Message);
            throw terminal;
        }
        catch (OperationCanceledException error) when (!ct.IsCancellationRequested && deadline.IsCancellationRequested
            && error.CancellationToken == deadline.Token)
        {
            terminal = Failure(budget.PollCount, started, lastReason + "; budget=deadline");
            throw terminal;
        }
        catch (Exception error) { terminal = error; throw; }
        finally { budget.Finish(terminal); }
    }

    /// <summary>Report bounded attempt/time/source diagnostics rather than the first transient miss alone.</summary>
    private static TimeoutException Failure(int attempts, long started, string lastReason) => new(
        FormattableString.Invariant($"pose_acquisition_timeout; attempts={attempts}; elapsedMs={Stopwatch.GetElapsedTime(started).TotalMilliseconds:F0}; last={lastReason}"));
}

/// <summary>A probe either returns its newly verified frame or an explicit transient reason; it never returns cached pose data.</summary>
/// <param name="Sample">Valid same-frame evidence, or null when recognition must wait.</param>
/// <param name="RetryReason">Bounded diagnostic for initial missing HUD, missing match, unreliable yaw or not-yet-new source.</param>
/// <param name="Outcome">Typed metadata proof is supplied only after native descriptor validation.</param>
internal sealed record NavigationResetPoseProbe(NavigationResetSample? Sample, string? RetryReason,
    NavigationResetPoseProbeOutcome Outcome = NavigationResetPoseProbeOutcome.Observation);

/// <summary>Metadata-only Pending must never be inferred from exception or retry text.</summary>
internal enum NavigationResetPoseProbeOutcome
{
    /// <summary>A real observation or ordinary recognition/source miss retains its original charge and delay.</summary>
    Observation,
    /// <summary>The native boundary validated an explicit unpublished Pending descriptor without pixels.</summary>
    ValidatedReadbackPending
}
