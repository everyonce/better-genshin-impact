using System.ComponentModel;
using System.Runtime.ExceptionServices;
using System.Runtime.InteropServices;
using System.Text;
using Vanara.PInvoke;

namespace Fischless.GameCapture.DesktopDc;

/// <summary>Read exact target/session/desktop/DPI facts without activation, selection, launch or settings changes.</summary>
internal static class DesktopDcTarget
{
    /// <summary>Read-only target queries acquire and close their own query handles before returning.</summary>
    internal static DesktopDcTargetSnapshot Read(nint hwnd)
    {
        if (hwnd == 0 || GetWindowThreadProcessId(hwnd, out var pid) == 0 || pid == 0)
            throw new InvalidOperationException("Desktop target window is unavailable.");
        var process = OpenProcess(0x1000, false, pid);
        if (process == 0) throw new Win32Exception(Marshal.GetLastWin32Error(), "Desktop target query handle");
        return WithQueryHandle(process, CloseHandle, () => ReadCore(hwnd, pid, process), "target process");
    }

    /// <summary>Gather physical signed corners and exact process creation identity, then apply shared managed guards.</summary>
    private static DesktopDcTargetSnapshot ReadCore(nint hwnd, uint pid, nint process)
    {
        if (!GetProcessTimes(process, out var created, out _, out _, out _)
            || !GetExitCodeProcess(process, out var exitCode)
            || !ProcessIdToSessionId(pid, out var session)
            || !ProcessIdToSessionId((uint)Environment.ProcessId, out var callerSession)
            || !GetClientRect(hwnd, out var client))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Desktop target identity/client query");
        var first = new Point { X = client.left, Y = client.top };
        var second = new Point { X = client.right, Y = client.bottom };
        if (!ClientToScreen(hwnd, ref first) || !ClientToScreen(hwnd, ref second))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Desktop client-to-screen corners");
        var crop = new RECT(first.X, first.Y, second.X, second.Y);
        var left = GetSystemMetrics(76);
        var top = GetSystemMetrics(77);
        var width = GetSystemMetrics(78);
        var height = GetSystemMetrics(79);
        if (width <= 0 || height <= 0) throw new InvalidOperationException("Virtual screen is unavailable.");
        var virtualScreen = new RECT(left, top, checked(left + width), checked(top + height));
        var monitor = MonitorFromRect(ref crop, 0);
        var monitorInfo = new MonitorInfo { Size = (uint)Marshal.SizeOf<MonitorInfo>() };
        if (monitor == 0 || !GetMonitorInfoW(monitor, ref monitorInfo))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Desktop crop monitor");
        var input = OpenInputDesktop(0, false, 1); // DESKTOP_READOBJECTS only; never switch desktops.
        if (input == 0) throw new Win32Exception(Marshal.GetLastWin32Error(), "Input desktop query handle");
        var inputName = WithQueryHandle(input, CloseDesktop, () => ObjectName(input), "input desktop");
        var snapshot = new DesktopDcTargetSnapshot
        {
            Window = hwnd, ForegroundWindow = GetForegroundWindow(), ProcessId = pid,
            ProcessCreationFileTime = created, ProcessActive = exitCode == 259,
            SessionId = session, CallerSessionId = callerSession,
            Visible = IsWindowVisible(hwnd), Minimized = IsIconic(hwnd),
            PerMonitorV2 = AreDpiAwarenessContextsEqual(GetThreadDpiAwarenessContext(), -4),
            Dpi = GetDpiForWindow(hwnd), ClientRect = client, ScreenRect = crop,
            VirtualScreen = virtualScreen, Monitor = monitor, MonitorRect = monitorInfo.Monitor,
            WindowStation = ObjectName(GetProcessWindowStation()),
            ThreadDesktop = ObjectName(GetThreadDesktop(GetCurrentThreadId())),
            InputDesktop = inputName, ConnectionState = ConnectionState(session)
        };
        // Check the HWND owner again after the other sampled queries, without trusting a PID alone.
        if (GetWindowThreadProcessId(hwnd, out var finalPid) == 0 || finalPid != pid)
            throw new InvalidOperationException("Desktop window owner changed during guard.");
        snapshot.Validate(hwnd);
        return snapshot;
    }

    /// <summary>Close a query handle once; retain primary failures and explicitly quarantine uncertain cleanup.</summary>
    internal static T WithQueryHandle<T>(nint handle, Func<nint, bool> close, Func<T> read, string stage)
    {
        T result = default!;
        Exception? failure = null;
        try { result = read(); }
        catch (Exception error) { failure = error; }
        try
        {
            if (!close(handle)) throw new DesktopDcCleanupException("Failed to close " + stage + " query handle.");
        }
        catch (Exception error)
        {
            var cleanup = error as DesktopDcCleanupException
                ?? new DesktopDcCleanupException("Failed to close " + stage + " query handle.", error);
            failure = DesktopDcCleanupException.Combine(failure, cleanup);
        }
        if (failure is not null) ExceptionDispatchInfo.Capture(failure).Throw();
        return result;
    }

    /// <summary>Read a bounded object name; borrowed process/thread handles are never closed.</summary>
    private static string ObjectName(nint handle)
    {
        if (handle == 0) throw new InvalidOperationException("Desktop/window-station handle unavailable.");
        var name = new StringBuilder(256);
        if (!GetUserObjectInformationW(handle, 2, name, 512, out var needed) || needed > 512)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Desktop object name");
        return name.ToString();
    }

    /// <summary>Require WTSActive independently of input-desktop availability, freeing any query buffer once.</summary>
    private static int ConnectionState(uint session)
    {
        nint buffer = 0;
        var result = -1;
        Exception? failure = null;
        try
        {
            if (!WTSQuerySessionInformationW(0, session, 8, out buffer, out var bytes) || buffer == 0 || bytes != 4)
                throw new Win32Exception(Marshal.GetLastWin32Error(), "WTS connection state");
            result = Marshal.ReadInt32(buffer);
        }
        catch (Exception error) { failure = error; }
        if (buffer != 0)
        {
            try { WTSFreeMemory(buffer); }
            catch (Exception error)
            {
                failure = DesktopDcCleanupException.Combine(failure,
                    new DesktopDcCleanupException("WTS query buffer cleanup failed.", error));
            }
        }
        if (failure is not null) ExceptionDispatchInfo.Capture(failure).Throw();
        return result;
    }

    /// <summary>Signed native screen/client coordinates.</summary>
    [StructLayout(LayoutKind.Sequential)] private struct Point { public int X, Y; }
    /// <summary>Read the full monitor extent; work-area metadata never replaces physical bounds.</summary>
    [StructLayout(LayoutKind.Sequential)] private struct MonitorInfo { public uint Size; public RECT Monitor, Work; public uint Flags; }
    /// <summary>Read the exact current foreground window.</summary>
    [DllImport("user32.dll")] private static extern nint GetForegroundWindow();
    /// <summary>Read the target's current process owner.</summary>
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint hwnd, out uint pid);
    /// <summary>Read visibility without showing the window.</summary>
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(nint hwnd);
    /// <summary>Read minimized state without restoring the window.</summary>
    [DllImport("user32.dll")] private static extern bool IsIconic(nint hwnd);
    /// <summary>Read client coordinates without resizing.</summary>
    [DllImport("user32.dll", SetLastError = true)] private static extern bool GetClientRect(nint hwnd, out RECT rect);
    /// <summary>Translate both physical client corners under the admitted DPI context.</summary>
    [DllImport("user32.dll", SetLastError = true)] private static extern bool ClientToScreen(nint hwnd, ref Point point);
    /// <summary>Read virtual screen dimensions and signed origin.</summary>
    [DllImport("user32.dll")] private static extern int GetSystemMetrics(int index);
    /// <summary>Find an intersecting monitor; whole-crop containment is checked separately.</summary>
    [DllImport("user32.dll")] private static extern nint MonitorFromRect(ref RECT rect, uint flags);
    /// <summary>Read monitor coordinates without moving windows.</summary>
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool GetMonitorInfoW(nint monitor, ref MonitorInfo info);
    /// <summary>Read effective target DPI.</summary>
    [DllImport("user32.dll")] private static extern uint GetDpiForWindow(nint hwnd);
    /// <summary>Read the calling thread's context rather than changing it.</summary>
    [DllImport("user32.dll")] private static extern nint GetThreadDpiAwarenessContext();
    /// <summary>Compare the context to PerMonitorV2.</summary>
    [DllImport("user32.dll")] private static extern bool AreDpiAwarenessContextsEqual(nint first, nint second);
    /// <summary>Borrow the current process window station.</summary>
    [DllImport("user32.dll")] private static extern nint GetProcessWindowStation();
    /// <summary>Borrow the current thread's desktop.</summary>
    [DllImport("user32.dll")] private static extern nint GetThreadDesktop(uint thread);
    /// <summary>Read current native thread identity.</summary>
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    /// <summary>Read a bounded object name using query-only access.</summary>
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool GetUserObjectInformationW(nint handle, int index, StringBuilder value, uint bytes, out uint needed);
    /// <summary>Open only a read-object handle to the input desktop.</summary>
    [DllImport("user32.dll", SetLastError = true)] private static extern nint OpenInputDesktop(uint flags, bool inherit, uint access);
    /// <summary>Close the explicitly opened input-desktop handle.</summary>
    [DllImport("user32.dll")] private static extern bool CloseDesktop(nint desktop);
    /// <summary>Open only a limited-information process query handle.</summary>
    [DllImport("kernel32.dll", SetLastError = true)] private static extern nint OpenProcess(uint access, bool inherit, uint pid);
    /// <summary>Read exact kernel creation identity.</summary>
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool GetProcessTimes(nint process, out long creation, out long exit, out long kernel, out long user);
    /// <summary>Read process liveness using its query handle.</summary>
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool GetExitCodeProcess(nint process, out uint exitCode);
    /// <summary>Read the target/caller session without selecting a session.</summary>
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool ProcessIdToSessionId(uint pid, out uint session);
    /// <summary>Close only the explicitly opened process query handle.</summary>
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(nint handle);
    /// <summary>Read WTSConnectState for the actual pinned session.</summary>
    [DllImport("wtsapi32.dll", SetLastError = true)] private static extern bool WTSQuerySessionInformationW(nint server, uint session, int infoClass, out nint buffer, out uint bytes);
    /// <summary>Return the WTS-owned query buffer.</summary>
    [DllImport("wtsapi32.dll")] private static extern void WTSFreeMemory(nint buffer);
}
