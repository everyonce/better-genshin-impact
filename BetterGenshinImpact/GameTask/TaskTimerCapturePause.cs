using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask;

/// <summary>Drain one dispatcher's tick before suppressing only its timer capture for an exact task runtime.</summary>
internal sealed class TaskTimerCapturePause(object tickGate)
{
    /// <summary>Bound admission before task input; an abandoned waiter must never install a late lease.</summary>
    internal static readonly TimeSpan MaximumDrainWait = TimeSpan.FromSeconds(2);
    /// <summary>Only one TaskRunner owner may pause this dispatcher at a time.</summary>
    private Lease? _active;

    /// <summary>Wait on a worker, recheck ownership after draining, then finish trigger cleanup before admitting task work.</summary>
    internal Task<IDisposable> AcquireAsync(object runtimeIdentity, Func<bool> isCurrent,
        Action finishTriggerDisable, CancellationToken cancellationToken, TimeSpan? drainWait = null)
    {
        ArgumentNullException.ThrowIfNull(runtimeIdentity);
        ArgumentNullException.ThrowIfNull(isCurrent);
        ArgumentNullException.ThrowIfNull(finishTriggerDisable);
        var bound = drainWait ?? MaximumDrainWait;
        if (bound <= TimeSpan.Zero || bound > MaximumDrainWait) throw new ArgumentOutOfRangeException(nameof(drainWait));
        var started = Stopwatch.GetTimestamp();
        // Cancellation is checked inside the waiter too. Do not wrap this task in
        // WaitAsync: the actual waiter must finish before its caller can move on.
        return Task.Run<IDisposable>(() =>
        {
            var entered = false;
            try
            {
                while (!entered)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    var remaining = bound - Stopwatch.GetElapsedTime(started);
                    if (remaining <= TimeSpan.Zero) throw new TimeoutException("timer_capture_drain_timeout");
                    entered = Monitor.TryEnter(tickGate, TimeSpan.FromMilliseconds(Math.Min(25, remaining.TotalMilliseconds)));
                }
                cancellationToken.ThrowIfCancellationRequested();
                if (Stopwatch.GetElapsedTime(started) >= bound) throw new TimeoutException("timer_capture_drain_timeout");
                if (!isCurrent()) throw new InvalidOperationException("timer_capture_runtime_changed");
                if (Volatile.Read(ref _active) is not null) throw new InvalidOperationException("timer_capture_already_owned");
                finishTriggerDisable();
                cancellationToken.ThrowIfCancellationRequested();
                if (Stopwatch.GetElapsedTime(started) >= bound) throw new TimeoutException("timer_capture_drain_timeout");
                if (!isCurrent()) throw new InvalidOperationException("timer_capture_runtime_changed");
                var lease = new Lease(this, runtimeIdentity);
                Volatile.Write(ref _active, lease);
                return lease;
            }
            finally { if (entered) Monitor.Exit(tickGate); }
        }, cancellationToken);
    }

    /// <summary>A replacement runtime is never paused by an older task's lease.</summary>
    internal bool IsPausedFor(object runtimeIdentity) =>
        Volatile.Read(ref _active) is { } lease && ReferenceEquals(lease.RuntimeIdentity, runtimeIdentity);

    /// <summary>Release only this owner, without blocking cleanup on a subsequent housekeeping tick.</summary>
    private sealed class Lease(TaskTimerCapturePause owner, object runtimeIdentity) : IDisposable
    {
        /// <summary>Opaque, reference-equal runtime pinned at admission.</summary>
        internal object RuntimeIdentity { get; } = runtimeIdentity;
        /// <summary>Disposal is idempotent even when cancellation and cleanup converge.</summary>
        public void Dispose() => Interlocked.CompareExchange(ref owner._active, null, this);
    }
}
