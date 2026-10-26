using System;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Reserve task/runtime admission through a child restart; committed ownership lasts until process exit.</summary>
internal sealed class ExternalControlRestartReservation(Func<SemaphoreSlim> taskSemaphore)
{
    /// <summary>Allow isolated tests to supply a semaphore without initializing application task logging.</summary>
    internal ExternalControlRestartReservation(SemaphoreSlim semaphore) : this(() => semaphore) { }

    /// <summary>Zero is idle, one is preparing a launch, and two is a committed launch or attempted irreversible retirement.</summary>
    private int _state;

    /// <summary>Block other admissions while checking or after launching a replacement.</summary>
    internal bool BlocksAdmission => Volatile.Read(ref _state) != 0;

    /// <summary>A launched replacement requires shutdown even if its response cannot be produced or sent.</summary>
    internal bool Committed => Volatile.Read(ref _state) == 2;

    /// <summary>Run synchronously on the UI dispatcher, keeping both gates after a non-null launch result.</summary>
    internal T? TryLaunch<T>(Func<bool> reserveRuntime, Action releaseRuntime, Func<bool> hasOtherWork,
        Func<T?> launch, bool commitBeforeLaunch = false) where T : class
    {
        if (Interlocked.CompareExchange(ref _state, 1, 0) != 0) return null;
        SemaphoreSlim? tasks = null;
        var taskReserved = false;
        var runtimeReserved = false;
        try
        {
            // TaskControl also initializes the application logger; resolve it only for an actual restart.
            tasks = taskSemaphore();
            taskReserved = tasks.Wait(0);
            if (!taskReserved) return null;
            runtimeReserved = reserveRuntime();
            if (!runtimeReserved || hasOtherWork()) return null;
            // Retirement is irreversible as soon as Kill is attempted, even if the native call throws.
            // Ordinary restart keeps its existing non-null-launch commitment boundary.
            if (commitBeforeLaunch) Volatile.Write(ref _state, 2);
            var replacement = launch();
            if (replacement is null) return null;
            // No await, status read, response serialization, or Process.Dispose precedes this latch.
            Volatile.Write(ref _state, 2);
            return replacement;
        }
        finally
        {
            if (!Committed)
            {
                try { if (runtimeReserved) releaseRuntime(); }
                finally
                {
                    if (taskReserved) tasks!.Release();
                    Volatile.Write(ref _state, 0);
                }
            }
        }
    }

    /// <summary>Wrap response construction and I/O so post-launch failure always queues old-child shutdown.</summary>
    internal async Task GuardRequestAsync(Func<Task> request, Action scheduleShutdown)
    {
        try { await request().ConfigureAwait(false); }
        finally { if (Committed) scheduleShutdown(); }
    }
}
