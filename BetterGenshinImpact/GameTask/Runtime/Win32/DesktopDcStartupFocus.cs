using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask.Runtime.Win32;

/// <summary>One explicit idle-start foreground handoff; ordinary capture and task execution never call this helper.</summary>
internal static class DesktopDcStartupFocus
{
    /// <summary>Bound read-only confirmation of queued activation independently of the existing lifecycle deadline.</summary>
    private const double ConfirmationMilliseconds = 1000;

    /// <summary>Pin target identity and desktop facts independently of the changing foreground window.</summary>
    internal sealed record Snapshot(nint Window, int ProcessId, long CreatedAtUtcTicks, string ProcessName,
        int SessionId, int CallerSessionId, int CallerProcessId, string WindowClass, bool Active, bool Visible,
        bool Minimized, string WindowStation, string ThreadDesktop, string InputDesktop,
        nint ForegroundWindow, int ForegroundProcessId);

    /// <summary>Use only query APIs plus the single setter in the foreground BetterGI process; never restore or send input.</summary>
    internal static Task AcquireAsync(nint hwnd, CancellationToken ct) => AcquireAsync(hwnd, Read,
        SetForegroundWindow, () => Stopwatch.GetTimestamp() * 1000d / Stopwatch.Frequency,
        (milliseconds, token) => Task.Delay(TimeSpan.FromMilliseconds(milliseconds), token), ct);

    /// <summary>Execute the real one-shot ordering with injected native/clock boundaries for managed tests.</summary>
    internal static async Task AcquireAsync(nint hwnd, Func<nint, Snapshot> read, Func<nint, bool> set,
        Func<double> now, Func<double, CancellationToken, Task> delay, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        var original = read(hwnd);
        Validate(original, hwnd);
        ct.ThrowIfCancellationRequested();
        if (IsForeground(original)) return;
        // The explicit startup may yield its own application's foreground, never steal it from another application.
        if (original.ForegroundProcessId != original.CallerProcessId)
            throw new InvalidOperationException("desktop_startup_caller_not_foreground");
        if (!set(hwnd)) throw new InvalidOperationException("desktop_startup_foreground_denied");
        ct.ThrowIfCancellationRequested();

        var deadline = now() + ConfirmationMilliseconds;
        for (var attempt = 0; attempt < 21; attempt++)
        {
            ct.ThrowIfCancellationRequested();
            if (now() >= deadline) break;
            var observed = read(hwnd);
            Validate(observed, hwnd);
            if (observed.ProcessId != original.ProcessId || observed.CreatedAtUtcTicks != original.CreatedAtUtcTicks
                || observed.ProcessName != original.ProcessName || observed.SessionId != original.SessionId
                || observed.CallerProcessId != original.CallerProcessId || observed.CallerSessionId != original.CallerSessionId)
                throw new InvalidOperationException("desktop_startup_target_changed");
            ct.ThrowIfCancellationRequested();
            // A read returning after the confirmation deadline does not establish timely startup permission.
            var completed = now();
            if (completed <= deadline && IsForeground(observed)) return;
            if (completed >= deadline) break;
            await delay(Math.Min(50, deadline - completed), ct);
        }
        throw new InvalidOperationException("desktop_startup_foreground_unconfirmed");
    }

    /// <summary>Reject another process/session/desktop and any hidden, minimized or dead target before a setter or attachment.</summary>
    private static void Validate(Snapshot value, nint hwnd)
    {
        if (hwnd == 0 || value.Window != hwnd || value.ProcessId <= 0 || value.CreatedAtUtcTicks <= 0
            || value.ProcessName is not ("GenshinImpact" or "YuanShen") || value.WindowClass != "UnityWndClass"
            || value.CallerProcessId <= 0 || value.SessionId <= 0 || value.SessionId != value.CallerSessionId
            || !value.Active || !value.Visible || value.Minimized || value.WindowStation != "WinSta0"
            || value.ThreadDesktop != "Default" || value.InputDesktop != "Default")
            throw new InvalidOperationException("desktop_startup_target_invalid");
    }

    /// <summary>Require both the exact target HWND and its process owner.</summary>
    private static bool IsForeground(Snapshot value) => value.ForegroundWindow == value.Window
        && value.ForegroundProcessId == value.ProcessId;

    /// <summary>Query the selected existing target without selection, geometry changes, or process launch.</summary>
    private static Snapshot Read(nint hwnd)
    {
        if (GetWindowThreadProcessId(hwnd, out var pid) == 0 || pid == 0)
            throw new InvalidOperationException("desktop_startup_target_unavailable");
        using var target = Process.GetProcessById(checked((int)pid));
        using var caller = Process.GetCurrentProcess();
        var name = new StringBuilder(256);
        if (GetClassNameW(hwnd, name, name.Capacity) == 0)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Desktop startup window class");
        var foreground = GetForegroundWindow();
        var foregroundPid = 0u;
        if (foreground != 0 && GetWindowThreadProcessId(foreground, out foregroundPid) == 0)
            throw new InvalidOperationException("desktop_startup_foreground_unavailable");
        var value = new Snapshot(hwnd, target.Id, target.StartTime.ToUniversalTime().Ticks, target.ProcessName,
            target.SessionId, caller.SessionId, caller.Id, name.ToString(), !target.HasExited,
            IsWindowVisible(hwnd), IsIconic(hwnd), ObjectName(GetProcessWindowStation()),
            ObjectName(GetThreadDesktop(GetCurrentThreadId())), InputDesktopName(), foreground, checked((int)foregroundPid));
        if (GetWindowThreadProcessId(hwnd, out var finalPid) == 0 || finalPid != pid || target.HasExited)
            throw new InvalidOperationException("desktop_startup_target_changed");
        return value;
    }

    /// <summary>Close the one query-only input-desktop handle; uncertain cleanup prevents startup.</summary>
    private static string InputDesktopName()
    {
        var handle = OpenInputDesktop(0, false, 1);
        if (handle == 0) throw new Win32Exception(Marshal.GetLastWin32Error(), "Desktop startup input desktop");
        string? name = null;
        Exception? failure = null;
        try { name = ObjectName(handle); }
        catch (Exception error) { failure = error; }
        if (!CloseDesktop(handle))
        {
            var cleanup = new Win32Exception(Marshal.GetLastWin32Error(), "Desktop startup input-desktop cleanup");
            if (failure is null) throw cleanup;
            throw new AggregateException(failure, cleanup);
        }
        if (failure is not null) System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(failure).Throw();
        return name!;
    }

    /// <summary>Read a bounded desktop/window-station name; borrowed process and thread handles are not closed.</summary>
    private static string ObjectName(nint handle)
    {
        var name = new StringBuilder(256);
        if (handle == 0 || !GetUserObjectInformationW(handle, 2, name, 512, out var needed) || needed > 512)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Desktop startup object name");
        return name.ToString();
    }

    /// <summary>The only mutating native call; caller owns explicit idle-start admission.</summary>
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(nint hwnd);
    /// <summary>Read current foreground without activation.</summary>
    [DllImport("user32.dll")] private static extern nint GetForegroundWindow();
    /// <summary>Read the current HWND process owner.</summary>
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint hwnd, out uint pid);
    /// <summary>Read the target window class.</summary>
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern int GetClassNameW(nint hwnd, StringBuilder value, int capacity);
    /// <summary>Read visibility without showing the target.</summary>
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(nint hwnd);
    /// <summary>Read minimized state without restoring the target.</summary>
    [DllImport("user32.dll")] private static extern bool IsIconic(nint hwnd);
    /// <summary>Borrow the current process window station.</summary>
    [DllImport("user32.dll")] private static extern nint GetProcessWindowStation();
    /// <summary>Borrow the current thread's desktop.</summary>
    [DllImport("user32.dll")] private static extern nint GetThreadDesktop(uint thread);
    /// <summary>Read current native thread identity.</summary>
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    /// <summary>Query a bounded name without changing desktops.</summary>
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool GetUserObjectInformationW(nint handle, int index, StringBuilder value, uint bytes, out uint needed);
    /// <summary>Open only DESKTOP_READOBJECTS access to the active input desktop.</summary>
    [DllImport("user32.dll", SetLastError = true)] private static extern nint OpenInputDesktop(uint flags, bool inherit, uint access);
    /// <summary>Close the explicitly acquired query handle once.</summary>
    [DllImport("user32.dll", SetLastError = true)] private static extern bool CloseDesktop(nint desktop);
}
