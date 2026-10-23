using System.Collections.Concurrent;
using System.Diagnostics;

namespace Fischless.GameCapture.Graphics.Helpers;

/// <summary>
/// Owns one session's WinRT thread. A dispatch timeout disables further work;
/// retirement still runs after any native operation already in progress.
/// </summary>
internal sealed class WgcCapturePump
{
    /// <summary>Protects admission and retirement, never held while waiting for the worker.</summary>
    private readonly object _gate = new();
    /// <summary>The worker always consumes this instance's queue, including during retirement.</summary>
    private readonly BlockingCollection<Action> _actions = new();
    /// <summary>Dedicated owner of all WinRT creation, recreation and destruction.</summary>
    private readonly Thread _thread;
    /// <summary>Signals that final cleanup has run and the queue has been drained.</summary>
    private readonly TaskCompletionSource _retired = new(TaskCreationOptions.RunContinuationsAsynchronously);
    /// <summary>The sole admitted operation; callers cannot build an unbounded work backlog.</summary>
    private Task? _pending;
    /// <summary>Set after a dispatch timeout; native work itself cannot be forcibly cancelled.</summary>
    private bool _faulted;
    /// <summary>Once retirement is admitted, no additional normal operation is allowed.</summary>
    private bool _retiring;
    /// <summary>Failure from final cleanup, delivered through the retirement task.</summary>
    private Exception? _cleanupError;

    /// <summary>Starts a new worker with its own immutable queue.</summary>
    public WgcCapturePump()
    {
        _thread = new Thread(PumpLoop) { IsBackground = true, Name = "BGI-WgcCaptureV2" };
        _thread.Start();
    }

    /// <summary>Whether dispatch timed out and this session must now retire.</summary>
    public bool IsFaulted
    {
        get { lock (_gate) return _faulted; }
    }

    /// <summary>
    /// Runs an operation with a bounded caller wait. Timeout never transfers
    /// ownership of its resources to the caller; Retire must perform cleanup.
    /// </summary>
    public void Run(Action action, TimeSpan timeout)
    {
        ArgumentNullException.ThrowIfNull(action);
        if (timeout <= TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(timeout));
        if (Thread.CurrentThread == _thread)
            throw new InvalidOperationException("WGC pump actions must not synchronously dispatch another action.");

        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        // 0 = queued, 1 = started, 2 = cancelled before starting. Running native calls are never cancelled.
        var state = 0;
        lock (_gate)
        {
            if (_retiring || _faulted)
                throw new InvalidOperationException("The WGC session is retiring after stop or a dispatch timeout.");
            if (_pending is { IsCompleted: false })
                throw new InvalidOperationException("A WGC operation is already running.");
            _pending = completion.Task;
            _actions.Add(() =>
            {
                try
                {
                    if (Interlocked.CompareExchange(ref state, 1, 0) == 0) action();
                    completion.TrySetResult();
                }
                catch (Exception error)
                {
                    Debug.WriteLine($"[WGC V2] Pump operation failed: {error}");
                    completion.TrySetException(error);
                    // A timed-out caller may no longer await this task; still observe a late failure.
                    _ = completion.Task.Exception;
                }
            });
        }

        if (!WaitWithoutWrapping(completion.Task, timeout))
        {
            lock (_gate) _faulted = true;
            Interlocked.CompareExchange(ref state, 2, 0);
            throw new TimeoutException("WGC operation timed out; capture is unavailable until session retirement completes.");
        }
    }

    /// <summary>
    /// Queues final cleanup behind the running operation and closes admission.
    /// Repeated calls return the same completion, so stop does not enqueue retries.
    /// </summary>
    public Task Retire(Action cleanup)
    {
        ArgumentNullException.ThrowIfNull(cleanup);
        lock (_gate)
        {
            if (_retiring) return _retired.Task;
            _retiring = true;
            _actions.Add(() =>
            {
                try { cleanup(); }
                catch (Exception error) { _cleanupError = error; }
            });
            _actions.CompleteAdding();
            return _retired.Task;
        }
    }

    /// <summary>Waits without changing an operation's original exception type.</summary>
    public static bool WaitWithoutWrapping(Task task, TimeSpan timeout)
    {
        try
        {
            if (!task.Wait(timeout)) return false;
        }
        catch (AggregateException)
        {
            task.GetAwaiter().GetResult();
            throw;
        }
        task.GetAwaiter().GetResult();
        return true;
    }

    /// <summary>Executes admitted actions serially, then releases the session queue.</summary>
    private void PumpLoop()
    {
        foreach (var action in _actions.GetConsumingEnumerable()) action();
        _actions.Dispose();
        if (_cleanupError is null) _retired.TrySetResult();
        else
        {
            _retired.TrySetException(_cleanupError);
            _ = _retired.Task.Exception;
        }
    }
}
