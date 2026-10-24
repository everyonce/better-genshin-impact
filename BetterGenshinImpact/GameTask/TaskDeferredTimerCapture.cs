using System;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask;

/// <summary>TaskRunner-owned, single-use activation whose resources outlive native work and final input cleanup.</summary>
internal sealed class TaskDeferredTimerCapture(
    CancellationToken ownerToken, Action validateRuntime,
    Func<IDisposable> preserveCancellation, Func<CancellationToken, Task<IDisposable>> acquire)
{
    /// <summary>Serialize admission and closure without holding a lock across the worker drain.</summary>
    private readonly object _sync = new();
    /// <summary>Ending the task cancels an admitted but unfinished activation.</summary>
    private readonly CancellationTokenSource _closing = new();
    /// <summary>The actual activation completion, never a timeout wrapper that leaves a waiter running.</summary>
    private Task? _activation;
    /// <summary>One cleanup completion also makes repeated owner cleanup idempotent.</summary>
    private Task? _ending;
    /// <summary>Closure permanently rejects callbacks retained by a finished task.</summary>
    private bool _closed;
    /// <summary>Successful acquisition is retained even if cancellation wins its subsequent validation.</summary>
    private IDisposable? _captureLease;
    /// <summary>The configured cancel hotkey remains usable during acquisition and final cleanup.</summary>
    private IDisposable? _cancellationHotkey;

    /// <summary>Activate once for this owner; the existing dispatcher supplies bounded, cancellable worker admission.</summary>
    internal Task ActivateAsync(CancellationToken token)
    {
        TaskCompletionSource completion;
        lock (_sync)
        {
            if (_closed) throw new InvalidOperationException("timer_capture_owner_ended");
            if (_activation is not null) throw new InvalidOperationException("timer_capture_activation_already_requested");
            completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
            _activation = completion.Task;
        }
        _ = ActivateCoreAsync(token, completion);
        return completion.Task;
    }

    /// <summary>Link caller/owner/closure cancellation and retain acquired resources until End, including fault paths.</summary>
    private async Task ActivateCoreAsync(CancellationToken token, TaskCompletionSource completion)
    {
        try
        {
            using (var linked = CancellationTokenSource.CreateLinkedTokenSource(ownerToken, token, _closing.Token))
            {
                Task<IDisposable> pending;
                lock (_sync)
                {
                    // Close may win after reservation but before this method starts. Do not touch hotkeys or the dispatcher then.
                    if (_closed) throw new InvalidOperationException("timer_capture_owner_ended");
                    linked.Token.ThrowIfCancellationRequested();
                    validateRuntime();
                    _cancellationHotkey = preserveCancellation();
                    pending = acquire(linked.Token);
                }
                var lease = await pending.ConfigureAwait(false);
                lock (_sync) _captureLease = lease;
                linked.Token.ThrowIfCancellationRequested();
                validateRuntime();
            }
            completion.TrySetResult();
        }
        catch (OperationCanceledException exception) { completion.TrySetCanceled(exception.CancellationToken); }
        catch (Exception exception) { completion.TrySetException(exception); }
    }

    /// <summary>Close admission, cancel/drain pending work, run End, then release capture and hotkey resources.</summary>
    internal Task EndAsync(Action endTask)
    {
        TaskCompletionSource completion;
        Task? activation;
        lock (_sync)
        {
            if (_ending is not null) return _ending;
            _closed = true;
            activation = _activation;
            completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
            _ending = completion.Task;
        }
        _ = EndCoreAsync(endTask, activation, completion);
        return completion.Task;
    }

    /// <summary>Even an unawaited activation retires before End; synchronous trigger callbacks remain cooperatively bounded.</summary>
    private async Task EndCoreAsync(Action endTask, Task? activation, TaskCompletionSource completion)
    {
        try
        {
            try
            {
                try { _closing.Cancel(); }
                finally
                {
                    // The activation's caller owns its result. Cleanup observes faults without replacing the task's original error.
                    if (activation is not null)
                        // End retains its caller's context, matching TaskRunner's existing cleanup affinity.
                        try { await activation; }
                        catch (Exception) { }
                }
            }
            finally
            {
                try { endTask(); }
                finally
                {
                    try { _captureLease?.Dispose(); }
                    finally
                    {
                        try { _cancellationHotkey?.Dispose(); }
                        finally { _closing.Dispose(); }
                    }
                }
            }
            completion.TrySetResult();
        }
        catch (Exception exception) { completion.TrySetException(exception); }
    }
}
