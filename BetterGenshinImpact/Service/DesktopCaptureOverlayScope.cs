using System;
using System.Threading;
using BetterGenshinImpact.Core.Mask;
using BetterGenshinImpact.View;

namespace BetterGenshinImpact.Service;

/// <summary>Suppress application-owned overlays for a desktop-capture lifetime without changing saved preferences.</summary>
internal sealed class DesktopCaptureOverlayScope : IDisposable
{
    /// <summary>Overlapping rejected/manual attachments cannot release an older capture's suppression.</summary>
    private static int _owners;
    /// <summary>Queued picture-in-picture updates from either side of a lifetime are discarded.</summary>
    private static long _generation;
    /// <summary>Each acquisition retires at most once, and only after its capture has disposed.</summary>
    private int _disposed;

    /// <summary>Read-only admission predicate used by every owned overlay show path.</summary>
    internal static bool IsSuppressed => Volatile.Read(ref _owners) != 0;
    /// <summary>Captured by queued callbacks before copying their pixels.</summary>
    internal static long Generation => Interlocked.Read(ref _generation);

    /// <summary>Hide synchronously on the provider's UI thread before Start can publish usable pixels.</summary>
    internal static IDisposable Acquire(IMaskWindowHost host) => Acquire(() =>
    {
        host.Detach();
        PictureInPictureService.HideSynchronously();
        HtmlMaskWindow.HideAll();
        if (host.State.IsVisible) throw new InvalidOperationException("desktop_overlay_hide_failed");
    });

    /// <summary>Pure lifecycle seam: suppression is visible during hide, and a failed hide never starts capture.</summary>
    internal static IDisposable Acquire(Action hide)
    {
        Interlocked.Increment(ref _owners);
        Interlocked.Increment(ref _generation);
        var scope = new DesktopCaptureOverlayScope();
        try { hide(); return scope; }
        catch { scope.Dispose(); throw; }
    }

    /// <summary>Restore attachment eligibility only; no window is shown or attached by retirement.</summary>
    public void Dispose()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0) return;
        Interlocked.Increment(ref _generation);
        Interlocked.Decrement(ref _owners);
    }
}
