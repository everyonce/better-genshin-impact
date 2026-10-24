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
    internal static Task ReattachAsync(CaptureModes mode, string readbackMode, SemaphoreSlim taskGate,
        Func<Task> stopRuntime, Action<CaptureModes, string> selectSettings, Action persistMode,
        Func<CancellationToken, Task<bool>> startRuntime, CancellationToken cancellationToken)
        => ReattachAsync(mode, readbackMode, null, null, taskGate, stopRuntime,
            (selected, readback, _, _) => selectSettings(selected, readback), persistMode, startRuntime, cancellationToken);

    /// <summary>Validate optional V2 choices before ownership/mutation; null retains the corresponding saved option.</summary>
    internal static Task ReattachAsync(CaptureModes mode, string readbackMode, string? sourceRetention,
        string? conversion, SemaphoreSlim taskGate, Func<Task> stopRuntime,
        Action<CaptureModes, string, string?, string?> selectSettings, Action persistMode,
        Func<CancellationToken, Task<bool>> startRuntime, CancellationToken cancellationToken)
        => ReattachAsync(mode, readbackMode, sourceRetention, conversion, null, taskGate, stopRuntime,
            (selected, readback, retention, convert, _) => selectSettings(selected, readback, retention, convert),
            persistMode, startRuntime, cancellationToken);

    /// <summary>Desktop selection preserves dormant WGC choices; its explicit policy is validated before admission.</summary>
    internal static async Task ReattachAsync(CaptureModes mode, string readbackMode, string? sourceRetention,
        string? conversion, string? desktopDcSourcePolicy, SemaphoreSlim taskGate, Func<Task> stopRuntime,
        Action<CaptureModes, string, string?, string?, string?> selectSettings, Action persistMode,
        Func<CancellationToken, Task<bool>> startRuntime, CancellationToken cancellationToken)
    {
        if (!Enum.IsDefined(mode)) throw new ArgumentOutOfRangeException(nameof(mode));
        if (readbackMode is not ("blocking" or "poll_single_v1")
            || readbackMode == "poll_single_v1" && mode is not (CaptureModes.WindowsGraphicsCaptureV2 or CaptureModes.DesktopDc))
            throw new ArgumentOutOfRangeException(nameof(readbackMode));
        if (sourceRetention is not null && (mode != CaptureModes.WindowsGraphicsCaptureV2
                || sourceRetention is not ("disabled" or "hold-until-readback-v1")))
            throw new ArgumentOutOfRangeException(nameof(sourceRetention));
        if (conversion is not null && (mode != CaptureModes.WindowsGraphicsCaptureV2 || conversion is not ("gpu" or "cpu")))
            throw new ArgumentOutOfRangeException(nameof(conversion));
        if (desktopDcSourcePolicy is not null && (mode != CaptureModes.DesktopDc
                || desktopDcSourcePolicy is not ("observe-only" or "host-acquisition-v1")))
            throw new ArgumentOutOfRangeException(nameof(desktopDcSourcePolicy));
        if (!await taskGate.WaitAsync(0, cancellationToken))
            throw new InvalidOperationException("A standalone task is already active.");
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            // StopAsync has no cancellation overload. Retain ownership until its
            // cleanup finishes, rather than leaving a detached operation behind.
            await stopRuntime();
            cancellationToken.ThrowIfCancellationRequested();
            selectSettings(mode, readbackMode, sourceRetention, conversion, desktopDcSourcePolicy);
            persistMode();
            cancellationToken.ThrowIfCancellationRequested();
            var started = await startRuntime(cancellationToken);
            cancellationToken.ThrowIfCancellationRequested();
            if (!started) throw new InvalidOperationException("The game runtime could not attach with the selected capture backend.");
        }
        finally { taskGate.Release(); }
    }
}
