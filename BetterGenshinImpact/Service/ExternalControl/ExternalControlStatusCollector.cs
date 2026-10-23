using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Threading;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Bound read-only UI collection even when a dispatcher callback has started and cannot be aborted.</summary>
internal static class ExternalControlStatusCollector
{
    /// <summary>Leave room inside the five-second pipe deadline to serialize and deliver degraded status.</summary>
    internal static readonly TimeSpan CollectionTimeout = TimeSpan.FromSeconds(1);

    /// <summary>Never reuse an old ready snapshot; cancellation also preserves already-committed command acknowledgements.</summary>
    internal static async Task<ExternalControlStatus> ReadAsync(Dispatcher? dispatcher,
        Func<ExternalControlStatus> collect, ExternalControlStatus baseline, CancellationToken cancellationToken,
        TimeSpan? timeout = null)
    {
        if (cancellationToken.IsCancellationRequested)
            return Unavailable(baseline, "cancelled", "UI status collection was cancelled.");
        if (dispatcher is null || dispatcher.HasShutdownStarted || dispatcher.HasShutdownFinished)
            return Unavailable(baseline, "unavailable", "The UI status dispatcher is unavailable.");

        DispatcherOperation<ExternalControlStatus>? operation = null;
        try
        {
            operation = dispatcher.InvokeAsync(() =>
            {
                try
                {
                    // Only a newly completed collection can advertise a running runtime or connected child.
                    return collect() with { UiStatus = "current" };
                }
                catch (Exception)
                {
                    // Observe failures here even when the request has already abandoned this callback.
                    return Unavailable(baseline, "failed", "UI status collection failed.");
                }
            }, DispatcherPriority.Normal, cancellationToken);
            return await operation.Task.WaitAsync(timeout ?? CollectionTimeout, cancellationToken).ConfigureAwait(false);
        }
        catch (TimeoutException)
        {
            return Unavailable(baseline, "timeout", "UI status collection exceeded its deadline.");
        }
        catch (OperationCanceledException)
        {
            return Unavailable(baseline, cancellationToken.IsCancellationRequested ? "cancelled" : "unavailable",
                "UI status collection was cancelled or its dispatcher stopped.");
        }
        catch (InvalidOperationException)
        {
            return Unavailable(baseline, "unavailable", "The UI status dispatcher is unavailable.");
        }
        finally
        {
            // Abort queued reads so repeated polling cannot fill a stalled dispatcher queue.
            // An executing COM/UI read cannot be interrupted; its late immutable result is discarded.
            if (operation is { Status: DispatcherOperationStatus.Pending }) operation.Abort();
        }
    }

    /// <summary>Unknown UI state is conservatively busy and cannot satisfy game or child readiness checks.</summary>
    private static ExternalControlStatus Unavailable(ExternalControlStatus baseline, string state, string error) =>
        baseline with
        {
            UiStatus = state, AutomationState = "unresponsive", AutomationError = error,
            RuntimeRunning = false, TaskRunning = true, CaptureMode = string.Empty,
            ChildSessionId = null, ChildConnectedState = 0, ChildWindowMinimized = false
        };
}
