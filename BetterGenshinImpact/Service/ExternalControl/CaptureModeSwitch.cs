using System;
using System.Threading;
using System.Threading.Tasks;
using Fischless.GameCapture;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Reattach one capture runtime while reserving the same task gate used by TaskRunner.</summary>
internal static class CaptureModeSwitch
{
    /// <summary>Stop before changing configuration, then wait for startup; never close the game process.</summary>
    internal static Task ReattachAsync(CaptureModes mode, SemaphoreSlim taskGate,
        Func<Task> stopRuntime, Action<CaptureModes> selectMode, Action persistMode,
        Func<CancellationToken, Task<bool>> startRuntime, CancellationToken cancellationToken)
        => ReattachAsync(mode, "blocking", taskGate, stopRuntime,
            (selected, _) => selectMode(selected), persistMode, startRuntime, cancellationToken);

    /// <summary>Reserve capture ownership while stopping, persisting both settings, and attaching their new runtime.</summary>
    internal static async Task ReattachAsync(CaptureModes mode, string readbackMode, SemaphoreSlim taskGate,
        Func<Task> stopRuntime, Action<CaptureModes, string> selectSettings, Action persistMode,
        Func<CancellationToken, Task<bool>> startRuntime, CancellationToken cancellationToken)
    {
        if (!Enum.IsDefined(mode)) throw new ArgumentOutOfRangeException(nameof(mode));
        if (readbackMode is not ("blocking" or "poll_single_v1")
            || readbackMode == "poll_single_v1" && mode != CaptureModes.WindowsGraphicsCaptureV2)
            throw new ArgumentOutOfRangeException(nameof(readbackMode));
        if (!await taskGate.WaitAsync(0, cancellationToken))
            throw new InvalidOperationException("A standalone task is already active.");
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            // StopAsync has no cancellation overload. Retain ownership until its
            // cleanup finishes, rather than leaving a detached operation behind.
            await stopRuntime();
            cancellationToken.ThrowIfCancellationRequested();
            selectSettings(mode, readbackMode);
            persistMode();
            cancellationToken.ThrowIfCancellationRequested();
            var started = await startRuntime(cancellationToken);
            cancellationToken.ThrowIfCancellationRequested();
            if (!started) throw new InvalidOperationException("The game runtime could not attach with the selected capture backend.");
        }
        finally { taskGate.Release(); }
    }
}
