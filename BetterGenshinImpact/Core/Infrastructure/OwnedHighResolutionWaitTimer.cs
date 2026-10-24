using System;
using System.Threading;
using System.Threading.Tasks;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace BetterGenshinImpact.Core.Infrastructure;

/// <summary>One locally owned timer, one normal-priority worker, and at most one admitted wait.</summary>
internal sealed class OwnedHighResolutionWaitTimer : IAsyncDisposable
{
    /// <summary>Serializes admission with shutdown; native timer operations belong only to the worker.</summary>
    private readonly object _gate = new();
    /// <summary>Wakes the worker for the single admitted request.</summary>
    private readonly AutoResetEvent _command = new(false);
    /// <summary>Wakes both the idle and active worker during shutdown.</summary>
    private readonly ManualResetEvent _stop = new(false);
    /// <summary>Owns the native synchronization timer until the worker has left every wait.</summary>
    private readonly TimerHandle _timer;
    /// <summary>Completes after all worker-owned native resources have been retired.</summary>
    private readonly TaskCompletionSource _retired = new(TaskCreationOptions.RunContinuationsAsynchronously);
    /// <summary>The bounded active or queued request; there is no request collection.</summary>
    private Request? _current;
    /// <summary>Permanent admission closure after disposal or a worker/native failure.</summary>
    private bool _closed;

    /// <summary>True only after worker handle cleanup, including a retired worker that reported a native failure.</summary>
    internal bool WorkerRetired => _retired.Task.IsCompleted;

    /// <summary>Creates the explicit high-resolution timer; unsupported creation fails without fallback.</summary>
    internal OwnedHighResolutionWaitTimer()
    {
        try
        {
            // Synchronization timer (not manual-reset), unnamed/noninheritable, only required rights.
            var raw = CreateWaitableTimerExW(IntPtr.Zero, null, 0x00000002, 0x00100002);
            int error = Marshal.GetLastPInvokeError();
            if (raw == IntPtr.Zero) throw new Win32Exception(error, "CreateWaitableTimerExW HIGH_RESOLUTION failed.");
            _timer = new TimerHandle(raw);
            var worker = new Thread(Work) { IsBackground = true, Name = "BetterGI owned wait" };
            // Leave priority/affinity/power policy unchanged. No per-wait worker or Task.Run is created.
            worker.Start();
        }
        catch
        {
            _timer?.Dispose();
            _command.Dispose();
            _stop.Dispose();
            throw;
        }
    }

    /// <summary>Admits one positive finite millisecond delay; all scheduling overhead remains caller-visible.</summary>
    internal Operation Start(int milliseconds, CancellationToken token)
    {
        if (milliseconds is < 1 or > 1000) throw new ArgumentOutOfRangeException(nameof(milliseconds));
        token.ThrowIfCancellationRequested();
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_closed, this);
            if (_current is not null) throw new InvalidOperationException("One wait is already outstanding.");
            var request = new Request(milliseconds, token);
            _current = request;
            _command.Set();
            return new Operation(request.Armed.Task, request.Completion.Task);
        }
    }

    /// <summary>Closes admission, wakes the worker, and awaits retirement without closing an in-flight handle.</summary>
    public async ValueTask DisposeAsync()
    {
        lock (_gate)
        {
            if (!_closed)
            {
                _closed = true;
                _stop.Set();
            }
        }
        // A timeout reports failure; only the worker finally may close handles while it still owns them.
        await _retired.Task.WaitAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false);
    }

    /// <summary>Runs all native arm/wait/cancel operations in order and retires handles on its own exit.</summary>
    private void Work()
    {
        Exception? fatal = null;
        try
        {
            while (WaitHandle.WaitAny([_stop, _command]) == 1)
            {
                Request request;
                lock (_gate) request = _current ?? throw new InvalidOperationException("Missing admitted wait.");
                Exception? failure = null;
                Stamp? stamp = null;
                bool armed = false;
                try
                {
                    if (_stop.WaitOne(0)) throw new ObjectDisposedException(nameof(OwnedHighResolutionWaitTimer));
                    request.Token.ThrowIfCancellationRequested();
                    long due = -checked(request.Milliseconds * 10_000L);
                    long armStarted = Stopwatch.GetTimestamp();
                    bool set = SetWaitableTimerEx(_timer.SafeWaitHandle, ref due, 0, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 0);
                    int error = Marshal.GetLastPInvokeError();
                    if (!set) throw new Win32Exception(error, "SetWaitableTimerEx failed.");
                    armed = true;
                    long armCompleted = Stopwatch.GetTimestamp();
                    request.Armed.TrySetResult();
                    // Stop/cancellation win ties; an old timer signal is never interpreted as a later request.
                    int selected = WaitHandle.WaitAny([_stop, request.Cancelled, _timer]);
                    long wakeObserved = Stopwatch.GetTimestamp();
                    if (selected == 0) throw new ObjectDisposedException(nameof(OwnedHighResolutionWaitTimer));
                    if (selected == 1 || request.Token.IsCancellationRequested)
                        throw new OperationCanceledException(request.Token);
                    stamp = new Stamp(armStarted, armCompleted, wakeObserved);
                }
                catch (Exception error)
                {
                    failure = error;
                }
                finally
                {
                    if (armed)
                    {
                        bool cancelled = CancelWaitableTimer(_timer.SafeWaitHandle);
                        int error = Marshal.GetLastPInvokeError();
                        if (!cancelled) failure = new Win32Exception(error, "CancelWaitableTimer failed; timer cannot be reused.");
                    }
                    // Dispose drains the cancellation callback before its event can be closed/reused.
                    request.Dispose();
                }
                lock (_gate)
                {
                    if (!ReferenceEquals(_current, request)) throw new InvalidOperationException("Wait ownership changed.");
                    _current = null;
                    if (failure is not null && failure is not OperationCanceledException && failure is not ObjectDisposedException)
                    {
                        _closed = true;
                        fatal = failure;
                    }
                    Complete(request, stamp, failure);
                }
                if (fatal is not null || _stop.WaitOne(0)) break;
            }
        }
        catch (Exception error)
        {
            fatal = error;
        }
        finally
        {
            Request? abandoned;
            lock (_gate)
            {
                _closed = true;
                abandoned = _current;
                _current = null;
            }
            if (abandoned is not null)
            {
                abandoned.Dispose();
                Complete(abandoned, null, fatal ?? new ObjectDisposedException(nameof(OwnedHighResolutionWaitTimer)));
            }
            _timer.Dispose();
            _command.Dispose();
            _stop.Dispose();
            if (fatal is null) _retired.TrySetResult();
            else
            {
                _retired.TrySetException(fatal);
                // DisposeAsync still awaits this failure; observe also if a previous retirement wait timed out.
                _ = _retired.Task.Exception;
            }
        }
    }

    /// <summary>Completes a request only after timer cancellation and callback retirement.</summary>
    private static void Complete(Request request, Stamp? stamp, Exception? failure)
    {
        if (failure is OperationCanceledException)
        {
            request.Armed.TrySetCanceled(request.Token);
            request.Completion.TrySetCanceled(request.Token);
        }
        else if (failure is not null)
        {
            request.Armed.TrySetException(failure);
            // Production awaits Completion only; retain Armed's fault while observing its duplicate exception.
            _ = request.Armed.Task.Exception;
            request.Completion.TrySetException(failure);
        }
        else request.Completion.TrySetResult(stamp ?? throw new InvalidOperationException("No timer stamp."));
    }

    /// <summary>Owns cancellation state for exactly one request; external token handles are never borrowed.</summary>
    private sealed class Request : IDisposable
    {
        /// <summary>Requested positive relative delay.</summary>
        internal readonly int Milliseconds;
        /// <summary>Original token, used for outcome identity.</summary>
        internal readonly CancellationToken Token;
        /// <summary>Owned wake event for token cancellation.</summary>
        internal readonly ManualResetEvent Cancelled = new(false);
        /// <summary>Arm handshake for lifecycle tests; this is not a kernel signal timestamp.</summary>
        internal readonly TaskCompletionSource Armed = new(TaskCreationOptions.RunContinuationsAsynchronously);
        /// <summary>Asynchronous caller completion after native retirement.</summary>
        internal readonly TaskCompletionSource<Stamp> Completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
        /// <summary>Registration drained before closing the owned cancellation event.</summary>
        private readonly CancellationTokenRegistration _registration;

        /// <summary>Registers only a bounded event signal; the callback neither disposes nor touches the timer.</summary>
        internal Request(int milliseconds, CancellationToken token)
        {
            Milliseconds = milliseconds;
            Token = token;
            try { _registration = token.Register(static state => ((ManualResetEvent)state!).Set(), Cancelled); }
            catch { Cancelled.Dispose(); throw; }
        }

        /// <summary>Waits for any cancellation callback before closing its event.</summary>
        public void Dispose()
        {
            _registration.Dispose();
            Cancelled.Dispose();
        }
    }

    /// <summary>Wraps the native synchronization timer in a sole owning SafeWaitHandle.</summary>
    private sealed class TimerHandle : WaitHandle
    {
        /// <summary>Adopts the successfully created native handle exactly once.</summary>
        internal TimerHandle(IntPtr raw) => SafeWaitHandle = new SafeWaitHandle(raw, true);
    }

    /// <summary>Tasks for one admission; the arm task is not a kernel-signal timestamp.</summary>
    internal sealed record Operation(Task Armed, Task<Stamp> Completion);
    /// <summary>Host clocks bracketing arm and observing wake, not the unobserved kernel signal time.</summary>
    internal sealed record Stamp(long ArmStartedTicks, long ArmCompletedTicks, long WakeObservedTicks);

    /// <summary>Creates the high-resolution timer with explicit access flags and no global timer policy.</summary>
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, ExactSpelling = true)]
    private static extern IntPtr CreateWaitableTimerExW(IntPtr attributes, string? name, uint flags, uint access);
    /// <summary>Arms one relative one-shot without APC, wake-from-suspend, or coalescing tolerance.</summary>
    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWaitableTimerEx(SafeWaitHandle timer, ref long dueTime, int period,
        IntPtr completion, IntPtr argument, IntPtr wakeContext, uint tolerableDelay);
    /// <summary>Deactivates the timer; a new arm resets any old signaled state before reuse.</summary>
    [DllImport("kernel32.dll", SetLastError = true, ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CancelWaitableTimer(SafeWaitHandle timer);
}
