using Vanara.PInvoke;

namespace Fischless.GameCapture.DesktopDc;

/// <summary>Read-only target facts pinned per generation; record equality also detects later geometry or desktop changes.</summary>
internal sealed record DesktopDcTargetSnapshot
{
    /// <summary>Exact supplied target window.</summary>
    internal required nint Window { get; init; }
    /// <summary>Observed foreground window.</summary>
    internal required nint ForegroundWindow { get; init; }
    /// <summary>Process owning the exact window.</summary>
    internal required uint ProcessId { get; init; }
    /// <summary>Exact process creation FILETIME, avoiding rounded timestamps and PID reuse.</summary>
    internal required long ProcessCreationFileTime { get; init; }
    /// <summary>Query-confirmed process liveness.</summary>
    internal required bool ProcessActive { get; init; }
    /// <summary>Target session, independently compared to the caller's session.</summary>
    internal required uint SessionId { get; init; }
    /// <summary>Calling process session.</summary>
    internal required uint CallerSessionId { get; init; }
    /// <summary>Target visibility at the sampled guard.</summary>
    internal required bool Visible { get; init; }
    /// <summary>Minimization is a hard failure rather than a restore request.</summary>
    internal required bool Minimized { get; init; }
    /// <summary>The capture caller's exact PMv2 DPI context.</summary>
    internal required bool PerMonitorV2 { get; init; }
    /// <summary>Target effective DPI, pinned across captures.</summary>
    internal required uint Dpi { get; init; }
    /// <summary>Unscaled target client coordinates.</summary>
    internal required RECT ClientRect { get; init; }
    /// <summary>Both translated signed client corners in physical screen coordinates.</summary>
    internal required RECT ScreenRect { get; init; }
    /// <summary>Current virtual desktop bounds.</summary>
    internal required RECT VirtualScreen { get; init; }
    /// <summary>Exact monitor containing the entire crop.</summary>
    internal required nint Monitor { get; init; }
    /// <summary>That monitor's full physical extent.</summary>
    internal required RECT MonitorRect { get; init; }
    /// <summary>Current process window station, never selected or changed here.</summary>
    internal required string WindowStation { get; init; }
    /// <summary>Calling thread desktop.</summary>
    internal required string ThreadDesktop { get; init; }
    /// <summary>Current input desktop's query-only name.</summary>
    internal required string InputDesktop { get; init; }
    /// <summary>Exact WTSConnectState value; zero is WTSActive.</summary>
    internal required int ConnectionState { get; init; }

    /// <summary>Require the tested foreground, session, coordinate and mapping conditions without changing them.</summary>
    internal void Validate(nint expectedWindow)
    {
        if (Window == 0 || Window != expectedWindow || ForegroundWindow != Window || ProcessId == 0
            || ProcessCreationFileTime <= 0 || !ProcessActive || SessionId != CallerSessionId || !Visible || Minimized)
            throw new InvalidOperationException("Desktop target identity, foreground or availability is invalid.");
        if (!PerMonitorV2 || Dpi == 0)
            throw new InvalidOperationException("Desktop capture requires the calling thread's PerMonitorV2 context.");
        if (ClientRect.left != 0 || ClientRect.top != 0 || ClientRect.right != DesktopDcGdiOwner.Width
            || ClientRect.bottom != DesktopDcGdiOwner.Height
            || (long)ScreenRect.right - ScreenRect.left != DesktopDcGdiOwner.Width
            || (long)ScreenRect.bottom - ScreenRect.top != DesktopDcGdiOwner.Height)
            throw new InvalidOperationException("Desktop capture admits only the tested 1920x1080 client crop.");
        if (Monitor == 0 || !Contains(VirtualScreen, ScreenRect) || !Contains(MonitorRect, ScreenRect))
            throw new InvalidOperationException("Desktop crop is outside the virtual screen or one monitor.");
        if (WindowStation != "WinSta0" || ThreadDesktop != "Default" || InputDesktop != ThreadDesktop || ConnectionState != 0)
            throw new InvalidOperationException("Desktop capture requires the active interactive desktop.");
    }

    /// <summary>Require positive outer dimensions and whole-crop containment, preserving negative monitor origins.</summary>
    private static bool Contains(RECT outer, RECT inner) => (long)outer.right - outer.left > 0
        && (long)outer.bottom - outer.top > 0 && outer.left <= inner.left && outer.top <= inner.top
        && outer.right >= inner.right && outer.bottom >= inner.bottom;
}
