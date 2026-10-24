using System.ComponentModel;
using System.Runtime.InteropServices;

namespace Fischless.GameCapture.DesktopDc;

/// <summary>Direct read/copy GDI calls for the per-capture owner; no registry, focus, mapping or desktop mutation.</summary>
internal sealed class DesktopDcGdi : IDesktopDcGdi
{
    /// <summary>Stateless native functions can be shared; all handles belong to a call-local owner.</summary>
    internal static readonly DesktopDcGdi Instance = new();

    /// <inheritdoc />
    public nint GetScreenDc() => GetDC(0);

    /// <inheritdoc />
    public DesktopDcDeviceInfo ReadDeviceInfo(nint screen)
    {
        if (!GetWindowOrgEx(screen, out var window) || !GetViewportOrgEx(screen, out var viewport))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Desktop DC origins");
        return new DesktopDcDeviceInfo(GetDeviceCaps(screen, 38), GetDeviceCaps(screen, 14),
            GetDeviceCaps(screen, 12), GetMapMode(screen), window.X, window.Y, viewport.X, viewport.Y);
    }

    /// <inheritdoc />
    public nint CreateMemoryDc(nint screen) => CreateCompatibleDC(screen);

    /// <inheritdoc />
    public nint CreateBitmap(nint screen, int width, int height, int stride, out nint bits)
    {
        var info = new BitmapInfo
        {
            Header = new BitmapHeader
            {
                Size = (uint)Marshal.SizeOf<BitmapHeader>(), Width = width, Height = -height,
                Planes = 1, BitCount = 24, Compression = 0, SizeImage = checked((uint)(stride * height))
            }
        };
        return CreateDIBSection(screen, ref info, 0, out bits, 0, 0);
    }

    /// <inheritdoc />
    public DesktopDcBitmapInfo ReadBitmapInfo(nint bitmap)
    {
        if (GetObjectW(bitmap, Marshal.SizeOf<Bitmap>(), out var actual) != Marshal.SizeOf<Bitmap>())
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Desktop DIB GetObject");
        return new DesktopDcBitmapInfo(actual.Width, actual.Height, actual.WidthBytes,
            actual.Planes, actual.BitsPixel, actual.Bits);
    }

    /// <inheritdoc />
    public nint SelectBitmap(nint memory, nint bitmap) => SelectObject(memory, bitmap);
    /// <inheritdoc />
    public bool Copy(nint memory, nint screen, int left, int top, int width, int height) =>
        BitBlt(memory, 0, 0, width, height, screen, left, top, 0x00CC0020);
    /// <inheritdoc />
    public bool Flush() => GdiFlush();
    /// <inheritdoc />
    public bool DeleteMemoryDc(nint memory) => DeleteDC(memory);
    /// <inheritdoc />
    public bool DeleteBitmap(nint bitmap) => DeleteObject(bitmap);
    /// <inheritdoc />
    public bool ReleaseScreenDc(nint screen) => ReleaseDC(0, screen) == 1;

    /// <summary>Native signed mapping coordinates.</summary>
    [StructLayout(LayoutKind.Sequential)]
    private struct Point { public int X, Y; }
    /// <summary>BI_RGB header for the crop-sized top-down allocation.</summary>
    [StructLayout(LayoutKind.Sequential)]
    private struct BitmapHeader
    {
        public uint Size;
        public int Width, Height;
        public ushort Planes, BitCount;
        public uint Compression, SizeImage;
        public int XPelsPerMeter, YPelsPerMeter;
        public uint ClrUsed, ClrImportant;
    }
    /// <summary>The unused palette entry preserves native BITMAPINFO layout.</summary>
    [StructLayout(LayoutKind.Sequential)]
    private struct BitmapInfo { public BitmapHeader Header; public uint Colors; }
    /// <summary>Native allocation layout returned by GetObject.</summary>
    [StructLayout(LayoutKind.Sequential)]
    private struct Bitmap
    {
        public int Type, Width, Height, WidthBytes;
        public ushort Planes, BitsPixel;
        public nint Bits;
    }

    /// <summary>Acquire the common screen DC on the calling thread.</summary>
    [DllImport("user32.dll", SetLastError = true)] private static extern nint GetDC(nint hwnd);
    /// <summary>Release that DC on the acquiring thread.</summary>
    [DllImport("user32.dll")] private static extern int ReleaseDC(nint hwnd, nint dc);
    /// <summary>Read raster and format capability values.</summary>
    [DllImport("gdi32.dll")] private static extern int GetDeviceCaps(nint dc, int index);
    /// <summary>Read the current mapping without changing it.</summary>
    [DllImport("gdi32.dll")] private static extern int GetMapMode(nint dc);
    /// <summary>Read the native window origin.</summary>
    [DllImport("gdi32.dll", SetLastError = true)] private static extern bool GetWindowOrgEx(nint dc, out Point point);
    /// <summary>Read the native viewport origin.</summary>
    [DllImport("gdi32.dll", SetLastError = true)] private static extern bool GetViewportOrgEx(nint dc, out Point point);
    /// <summary>Create one privately owned memory DC.</summary>
    [DllImport("gdi32.dll", SetLastError = true)] private static extern nint CreateCompatibleDC(nint dc);
    /// <summary>Allocate only the requested DIB, without a shared file section.</summary>
    [DllImport("gdi32.dll", SetLastError = true)] private static extern nint CreateDIBSection(nint dc, ref BitmapInfo info, uint usage, out nint bits, nint section, uint offset);
    /// <summary>Read the actual DIB address and layout.</summary>
    [DllImport("gdi32.dll", EntryPoint = "GetObjectW", SetLastError = true)] private static extern int GetObjectW(nint handle, int size, out Bitmap bitmap);
    /// <summary>Select or restore an object only in the private memory DC.</summary>
    [DllImport("gdi32.dll", SetLastError = true)] private static extern nint SelectObject(nint dc, nint bitmap);
    /// <summary>Copy physical screen pixels with SRCCOPY and no extra raster flags.</summary>
    [DllImport("gdi32.dll", SetLastError = true)] private static extern bool BitBlt(nint destination, int x, int y, int width, int height, nint source, int sourceX, int sourceY, uint operation);
    /// <summary>Finish this thread's GDI batch before a borrowed image reads its DIB.</summary>
    [DllImport("gdi32.dll")] private static extern bool GdiFlush();
    /// <summary>Delete a privately created memory DC.</summary>
    [DllImport("gdi32.dll")] private static extern bool DeleteDC(nint dc);
    /// <summary>Delete a known-deselected owned bitmap.</summary>
    [DllImport("gdi32.dll")] private static extern bool DeleteObject(nint bitmap);
}
