using System.ComponentModel;
using System.Runtime.ExceptionServices;
using System.Runtime.InteropServices;

namespace Fischless.GameCapture.DesktopDc;

/// <summary>Temporarily select PMv2 on this synchronous caller only; restore before publishing host pixels.</summary>
internal sealed class DesktopDcThreadDpiScope : IDisposable
{
    /// <summary>Native context selector, equality query and thread identity, injectable without native calls in tests.</summary>
    private readonly Func<nint, nint> _set;
    /// <summary>Read the current thread context after each successful change.</summary>
    private readonly Func<nint> _get;
    /// <summary>Compare opaque DPI contexts through the Windows equality contract.</summary>
    private readonly Func<nint, nint, bool> _equal;
    /// <summary>Never restore a different native thread.</summary>
    private readonly Func<uint> _thread;
    /// <summary>Exact original context and the thread that owns its restoration.</summary>
    private readonly nint _previous;
    /// <summary>Native thread at admission; no async or thread transfer is supported.</summary>
    private readonly uint _ownerThread;
    /// <summary>Exactly one restoration attempt, including failed attempts.</summary>
    private bool _settled;

    /// <summary>Enter a real caller-local scope without changing process or WPF DPI configuration.</summary>
    internal static DesktopDcThreadDpiScope Enter() => new(SetThreadDpiAwarenessContext,
        GetThreadDpiAwarenessContext, AreDpiAwarenessContextsEqual, GetCurrentThreadId);

    /// <summary>Own the previous context immediately; failed post-set checks restore before this constructor throws.</summary>
    internal DesktopDcThreadDpiScope(Func<nint, nint> set, Func<nint> get,
        Func<nint, nint, bool> equal, Func<uint> thread)
    {
        ArgumentNullException.ThrowIfNull(set);
        ArgumentNullException.ThrowIfNull(get);
        ArgumentNullException.ThrowIfNull(equal);
        ArgumentNullException.ThrowIfNull(thread);
        _set = set;
        _get = get;
        _equal = equal;
        _thread = thread;
        _ownerThread = thread();
        if (_ownerThread == 0) throw new InvalidOperationException("Desktop DPI caller thread is unavailable.");
        try { _previous = _set(-4); } // DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        catch (Exception error) { throw new DesktopDcCleanupException("Desktop DPI entry state is uncertain.", error); }
        if (_previous == 0)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Desktop PMv2 thread admission failed.");
        try
        {
            if (!_equal(_get(), -4)) throw new InvalidOperationException("Desktop PMv2 thread admission was not verified.");
        }
        catch (Exception error)
        {
            Exception failure = error;
            try { Dispose(); }
            catch (Exception cleanup) { failure = DesktopDcCleanupException.Combine(failure, cleanup); }
            ExceptionDispatchInfo.Capture(failure).Throw();
            throw;
        }
    }

    /// <summary>Restore once on the owning thread; uncertainty is terminal and must quarantine the capture backend.</summary>
    public void Dispose()
    {
        if (_settled) return;
        _settled = true;
        try
        {
            if (_thread() != _ownerThread)
                throw new InvalidOperationException("Desktop DPI scope cannot be restored on another thread.");
            if (_set(_previous) == 0)
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Desktop DPI restoration failed.");
            if (!_equal(_get(), _previous))
                throw new InvalidOperationException("Desktop DPI restoration was not verified.");
        }
        catch (Exception error)
        {
            throw new DesktopDcCleanupException("Desktop caller DPI context cleanup is uncertain.", error);
        }
    }

    /// <summary>Set only this thread's context, returning its opaque prior context on success.</summary>
    [DllImport("user32.dll", SetLastError = true)]
    private static extern nint SetThreadDpiAwarenessContext(nint context);
    /// <summary>Read the caller context without changing global configuration.</summary>
    [DllImport("user32.dll")]
    private static extern nint GetThreadDpiAwarenessContext();
    /// <summary>Opaque context values require semantic equality, not numeric equality.</summary>
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AreDpiAwarenessContextsEqual(nint first, nint second);
    /// <summary>Bind restoration to the actual Windows thread that selected PMv2.</summary>
    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();
}
