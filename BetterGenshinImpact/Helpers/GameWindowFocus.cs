using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace BetterGenshinImpact.Helpers;

/// <summary>Bounded foreground recovery for the already-bound game window.</summary>
internal static class GameWindowFocus
{
    private const uint UoiName = 2;
    private const uint DesktopReadObjects = 0x0001;
    private const int MaxAttempts = 3;

    internal sealed record WindowIdentity(long Handle, int? ProcessId, int? SessionId, string? ProcessName, string? ClassName);
    internal sealed record FocusDiagnostics(WindowIdentity Bound, WindowIdentity Foreground, string? InputDesktopName, bool InputDesktopAccessible);

    internal static FocusDiagnostics GetDiagnostics(nint boundHandle)
    {
        var foreground = GetForegroundWindow();
        var inputDesktop = OpenInputDesktop(0, false, DesktopReadObjects);
        try
        {
            var inputName = inputDesktop == IntPtr.Zero ? null : GetObjectName(inputDesktop);
            return new(CreateIdentity(boundHandle), CreateIdentity(foreground), inputName, inputDesktop != IntPtr.Zero && inputName != null);
        }
        finally
        {
            if (inputDesktop != IntPtr.Zero) CloseDesktop(inputDesktop);
        }
    }

    internal static bool TryFocus(nint handle, out string failure)
    {
        failure = "Foreground activation did not succeed.";
        if (handle == IntPtr.Zero || !IsWindow(handle)) { failure = "Bound game window is no longer valid."; return false; }
        uint targetThread = GetWindowThreadProcessId(handle, out var targetPid);
        uint currentThread = GetCurrentThreadId();
        if (targetThread == 0 || targetPid == 0) { failure = "Could not identify the bound game window owner."; return false; }
        if (!TryGetSession((int)targetPid, out int targetSession) || !TryGetSession(Environment.ProcessId, out int currentSession)
            || targetSession != currentSession)
        { failure = "Bound game window is not in this Windows session."; return false; }

        var targetDesktop = GetThreadDesktop(targetThread);
        var currentDesktop = GetThreadDesktop(currentThread);
        var inputDesktop = OpenInputDesktop(0, false, DesktopReadObjects);
        if (inputDesktop == IntPtr.Zero) { failure = "Input desktop is inaccessible; focus recovery stopped."; return false; }
        try
        {
            var inputName = GetObjectName(inputDesktop);
            if (inputName == null || GetObjectName(targetDesktop) != inputName || GetObjectName(currentDesktop) != inputName)
            { failure = "Bound game is not on the accessible input desktop; focus recovery stopped."; return false; }

            // AttachThreadInput requires both threads to have message queues. PeekMessage creates
            // the current script thread's queue without removing or dispatching any messages.
            _ = PeekMessage(out _, IntPtr.Zero, 0, 0, 0);

            for (int attempt = 0; attempt < MaxAttempts; attempt++)
            {
                if (GetForegroundWindow() == handle) return true;
                uint foregroundThread = GetWindowThreadProcessId(GetForegroundWindow(), out _);
                bool attachedTarget = false, attachedForeground = false;
                try
                {
                    if (targetThread != currentThread) attachedTarget = AttachThreadInput(currentThread, targetThread, true);
                    if (foregroundThread != 0 && foregroundThread != currentThread && foregroundThread != targetThread)
                        attachedForeground = AttachThreadInput(currentThread, foregroundThread, true);
                    ShowWindowAsync(handle, 9); // SW_RESTORE; avoid waiting on the target thread.
                    SetForegroundWindow(handle);
                }
                finally
                {
                    if (attachedForeground) AttachThreadInput(currentThread, foregroundThread, false);
                    if (attachedTarget) AttachThreadInput(currentThread, targetThread, false);
                }
                Thread.Sleep(100);
                if (GetForegroundWindow() == handle) return true;
            }
            failure = "Could not focus the bound game window after three bounded attempts.";
            return false;
        }
        finally { CloseDesktop(inputDesktop); }
    }

    private static WindowIdentity CreateIdentity(nint handle)
    {
        if (handle == IntPtr.Zero || !IsWindow(handle)) return new((long)handle, null, null, null, null);
        _ = GetWindowThreadProcessId(handle, out var pid);
        if (pid == 0) return new((long)handle, null, null, null, GetClass(handle));
        int? session = TryGetSession((int)pid, out var sid) ? sid : null;
        string? name = null;
        try { using var process = Process.GetProcessById((int)pid); name = process.ProcessName; } catch { }
        return new((long)handle, (int)pid, session, name, GetClass(handle));
    }

    private static bool TryGetSession(int pid, out int session)
    {
        try { using var process = Process.GetProcessById(pid); session = process.SessionId; return true; }
        catch { session = -1; return false; }
    }

    private static string? GetClass(nint handle)
    {
        var buffer = new StringBuilder(256);
        return GetClassName(handle, buffer, buffer.Capacity) > 0 ? buffer.ToString() : null;
    }

    private static string? GetObjectName(nint handle)
    {
        if (handle == IntPtr.Zero) return null;
        var buffer = Marshal.AllocHGlobal(1024);
        try { return GetUserObjectInformation(handle, UoiName, buffer, 1024, out _) ? Marshal.PtrToStringUni(buffer) : null; }
        finally { Marshal.FreeHGlobal(buffer); }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct NativePoint { public int X; public int Y; }

    [StructLayout(LayoutKind.Sequential)]
    private struct NativeMessage
    {
        public nint Window;
        public uint Message;
        public nuint WParam;
        public nint LParam;
        public uint Time;
        public NativePoint Point;
        public uint Private;
    }

    [DllImport("user32.dll")] private static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] private static extern bool IsWindow(nint hWnd);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint hWnd, out uint processId);
    [DllImport("user32.dll")] private static extern bool ShowWindowAsync(nint hWnd, int command);
    [DllImport("user32.dll")] private static extern bool PeekMessage(out NativeMessage message, nint hWnd, uint min, uint max, uint remove);
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(nint hWnd);
    [DllImport("user32.dll")] private static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool attach);
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] private static extern nint GetThreadDesktop(uint threadId);
    [DllImport("user32.dll", SetLastError = true)] private static extern nint OpenInputDesktop(uint flags, bool inherit, uint desiredAccess);
    [DllImport("user32.dll")] private static extern bool CloseDesktop(nint desktop);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool GetUserObjectInformation(nint handle, uint index, nint info, uint length, out uint needed);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(nint hWnd, StringBuilder className, int maxCount);
}
