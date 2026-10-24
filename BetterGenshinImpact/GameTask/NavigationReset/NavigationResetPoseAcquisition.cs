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

    /// <summary>Retry only explicit unavailable observations; identity, world and wrong-pose exceptions propagate immediately.</summary>
    internal static async Task<NavigationResetSample> ReadAsync(
        Func<CancellationToken, Task<NavigationResetPoseProbe>> probe,
        Func<int, CancellationToken, Task> delay, CancellationToken ct, TimeSpan? timeout = null)
    {
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

    /// <summary>Report bounded attempt/time/source diagnostics rather than the first transient miss alone.</summary>
    private static TimeoutException Failure(int attempts, long started, string lastReason) => new(
        FormattableString.Invariant($"pose_acquisition_timeout; attempts={attempts}; elapsedMs={Stopwatch.GetElapsedTime(started).TotalMilliseconds:F0}; last={lastReason}"));
}

/// <summary>A probe either returns its newly verified frame or an explicit transient reason; it never returns cached pose data.</summary>
/// <param name="Sample">Valid same-frame evidence, or null when recognition must wait.</param>
/// <param name="RetryReason">Bounded diagnostic for a missing match, unreliable yaw or not-yet-new source.</param>
internal sealed record NavigationResetPoseProbe(NavigationResetSample? Sample, string? RetryReason);
