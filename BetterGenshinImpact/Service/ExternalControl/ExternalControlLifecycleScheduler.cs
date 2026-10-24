using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Threading;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Separate lifecycle admission from synchronous UI-affine work while retaining its entire cleanup task.</summary>
internal static class ExternalControlLifecycleScheduler
{
    /// <summary>Always enqueue, even on the dispatcher thread; cancellation does not abandon work that has started.</summary>
    internal static Task RunAsync(Dispatcher dispatcher, Func<CancellationToken, Task> operation,
        CancellationToken cancellationToken)
    {
        // Do not pass the request token or race the operation against a timeout. The
        // lifecycle owns its token; a cancelled queued start must never invoke native work.
        return dispatcher.InvokeAsync(() =>
        {
            cancellationToken.ThrowIfCancellationRequested();
            return operation(cancellationToken);
        }, DispatcherPriority.Background).Task.Unwrap();
    }
}
