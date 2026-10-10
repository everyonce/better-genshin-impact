using Microsoft.Extensions.Logging;
using System;
using System.ComponentModel;
using System.Drawing;
using System.Runtime.InteropServices;

namespace BetterGenshinImpact.Core.Monitor;

/// <summary>
/// 在本地会话中约束并隐藏鼠标。所有调用应来自同一个 UI 线程，
/// 以便成对恢复 ShowCursor 的显示计数。
/// </summary>
internal sealed class LocalCursorCapture(ILogger logger) : IDisposable
{
    private const int MaxCursorHideAttempts = 64;
    private const int SmXVirtualScreen = 76;
    private const int SmYVirtualScreen = 77;
    private const int SmCxVirtualScreen = 78;
    private const int SmCyVirtualScreen = 79;

    private NativeRect _previousClipRect;
    private Rectangle _appliedBounds;
    private bool _hasPreviousClipRect;
    private bool _isCaptureSessionActive;
    private bool _isRestrictionApplied;
    private bool _isDisposed;
    private int _cursorHideCallCount;

    internal void Capture(Rectangle bounds)
    {
        ObjectDisposedException.ThrowIf(_isDisposed, this);
        if (bounds.Width <= 0 || bounds.Height <= 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(bounds),
                bounds,
                "The mouse restriction area must have a valid width and height.");
        }

        if (!_isCaptureSessionActive)
        {
            var clipRectRead = NativeMethods.GetClipCursor(out _previousClipRect);
            if (!clipRectRead)
            {
                logger.LogWarning(
                    "Failed to read the existing mouse restriction area, Win32Error: {Win32Error}",
                    Marshal.GetLastWin32Error());
            }

            _hasPreviousClipRect =
                clipRectRead && !IsVirtualDesktopBounds(_previousClipRect);
            _isCaptureSessionActive = true;
        }

        if (_isRestrictionApplied && _appliedBounds == bounds)
        {
            return;
        }

        var clipRect = NativeRect.FromRectangle(bounds);
        if (!NativeMethods.ClipCursor(ref clipRect))
        {
            var exception = new Win32Exception(
                Marshal.GetLastWin32Error(),
                "Failed to restrict the local mouse to the desktop mirror window");
            if (!_isRestrictionApplied)
            {
                Release();
            }
            throw exception;
        }

        _appliedBounds = bounds;
        if (!_isRestrictionApplied)
        {
            HideCursor();
            _isRestrictionApplied = true;
        }
    }

    internal void ReleaseTemporarily()
    {
        ObjectDisposedException.ThrowIf(_isDisposed, this);
        if (!_isCaptureSessionActive || !_isRestrictionApplied)
        {
            return;
        }

        if (!NativeMethods.ReleaseClipCursor(IntPtr.Zero))
        {
            throw new Win32Exception(
                Marshal.GetLastWin32Error(),
                "Failed to temporarily release the local mouse restriction");
        }

        var centerX = _appliedBounds.Left + _appliedBounds.Width / 2;
        var centerY = _appliedBounds.Top + _appliedBounds.Height / 2;
        if (!NativeMethods.SetCursorPos(centerX, centerY))
        {
            logger.LogWarning(
                "Failed to move the local mouse to the center of the desktop mirror control, Win32Error: {Win32Error}",
                Marshal.GetLastWin32Error());
        }

        RestoreCursorVisibility();
        _isRestrictionApplied = false;
        _appliedBounds = Rectangle.Empty;
    }

    internal void Release()
    {
        if (!_isCaptureSessionActive)
        {
            return;
        }

        var restored = _hasPreviousClipRect
            ? NativeMethods.ClipCursor(ref _previousClipRect)
            : NativeMethods.ReleaseClipCursor(IntPtr.Zero);
        if (!restored)
        {
            logger.LogWarning(
                "Failed to restore the mouse restriction area, Win32Error: {Win32Error}",
                Marshal.GetLastWin32Error());
        }

        RestoreCursorVisibility();
        _hasPreviousClipRect = false;
        _isCaptureSessionActive = false;
        _isRestrictionApplied = false;
        _appliedBounds = Rectangle.Empty;
    }

    public void Dispose()
    {
        if (_isDisposed)
        {
            return;
        }

        Release();
        _isDisposed = true;
        GC.SuppressFinalize(this);
    }

    private void HideCursor()
    {
        var displayCount = 0;
        do
        {
            displayCount = NativeMethods.ShowCursor(false);
            _cursorHideCallCount++;
        }
        while (displayCount >= 0 && _cursorHideCallCount < MaxCursorHideAttempts);

        if (displayCount >= 0)
        {
            logger.LogWarning(
                "ShowCursor display count remained nonnegative while hiding the local mouse: {DisplayCount}",
                displayCount);
        }
    }

    private void RestoreCursorVisibility()
    {
        while (_cursorHideCallCount > 0)
        {
            _ = NativeMethods.ShowCursor(true);
            _cursorHideCallCount--;
        }
    }

    private static bool IsVirtualDesktopBounds(NativeRect rect)
    {
        var left = NativeMethods.GetSystemMetrics(SmXVirtualScreen);
        var top = NativeMethods.GetSystemMetrics(SmYVirtualScreen);
        var width = NativeMethods.GetSystemMetrics(SmCxVirtualScreen);
        var height = NativeMethods.GetSystemMetrics(SmCyVirtualScreen);
        return rect.Left == left
               && rect.Top == top
               && rect.Right == left + width
               && rect.Bottom == top + height;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct NativeRect
    {
        public int Left;

        public int Top;

        public int Right;

        public int Bottom;

        internal static NativeRect FromRectangle(Rectangle rectangle)
        {
            return new NativeRect
            {
                Left = rectangle.Left,
                Top = rectangle.Top,
                Right = rectangle.Right,
                Bottom = rectangle.Bottom
            };
        }
    }

    private static class NativeMethods
    {
        [DllImport("user32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool GetClipCursor(out NativeRect rect);

        [DllImport("user32.dll", EntryPoint = "ClipCursor", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool ClipCursor(ref NativeRect rect);

        [DllImport("user32.dll", EntryPoint = "ClipCursor", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool ReleaseClipCursor(nint rect);

        [DllImport("user32.dll")]
        internal static extern int ShowCursor(
            [MarshalAs(UnmanagedType.Bool)] bool show);

        [DllImport("user32.dll")]
        internal static extern int GetSystemMetrics(int index);

        [DllImport("user32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool SetCursorPos(int x, int y);
    }
}
