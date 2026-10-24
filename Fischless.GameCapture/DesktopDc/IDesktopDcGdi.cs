namespace Fischless.GameCapture.DesktopDc;

/// <summary>Small per-call GDI ownership seam; the production implementation changes no process/window settings.</summary>
internal interface IDesktopDcGdi
{
    /// <summary>Acquire the current session's common desktop DC using a literal NULL HWND.</summary>
    nint GetScreenDc();
    /// <summary>Read the DC's raster/format/origin properties without changing its mapping.</summary>
    DesktopDcDeviceInfo ReadDeviceInfo(nint screen);
    /// <summary>Create a private compatible memory DC.</summary>
    nint CreateMemoryDc(nint screen);
    /// <summary>Create a top-down BGR24 DIB of the fixed, bounded dimensions.</summary>
    nint CreateBitmap(nint screen, int width, int height, int stride, out nint bits);
    /// <summary>Read the allocation's actual dimensions and address before selecting it.</summary>
    DesktopDcBitmapInfo ReadBitmapInfo(nint bitmap);
    /// <summary>Select or restore a bitmap in the private DC, returning the previous object.</summary>
    nint SelectBitmap(nint memory, nint bitmap);
    /// <summary>Perform one SRCCOPY from signed physical screen coordinates.</summary>
    bool Copy(nint memory, nint screen, int left, int top, int width, int height);
    /// <summary>Flush this calling thread's GDI batch.</summary>
    bool Flush();
    /// <summary>Delete one owned private DC.</summary>
    bool DeleteMemoryDc(nint memory);
    /// <summary>Delete one owned bitmap only after it is known to be deselected.</summary>
    bool DeleteBitmap(nint bitmap);
    /// <summary>Release the common desktop DC on the thread that acquired it.</summary>
    bool ReleaseScreenDc(nint screen);
}

/// <summary>Managed read-only device facts used by the same validation in production and fake-GDI tests.</summary>
/// <param name="RasterCaps">Raster capability flags, including RC_BITBLT.</param>
/// <param name="Planes">Number of color planes.</param>
/// <param name="BitsPerPixel">Desktop pixel depth.</param>
/// <param name="MapMode">Mapping mode; only MM_TEXT is admitted.</param>
/// <param name="WindowX">Window mapping origin X.</param>
/// <param name="WindowY">Window mapping origin Y.</param>
/// <param name="ViewportX">Viewport mapping origin X.</param>
/// <param name="ViewportY">Viewport mapping origin Y.</param>
internal readonly record struct DesktopDcDeviceInfo(int RasterCaps, int Planes, int BitsPerPixel,
    int MapMode, int WindowX, int WindowY, int ViewportX, int ViewportY)
{
    /// <summary>Only the reviewed normal desktop raster/format/origin is supported.</summary>
    internal bool IsSupported => (RasterCaps & 1) != 0 && Planes == 1 && BitsPerPixel is 24 or 32
        && MapMode == 1 && WindowX == 0 && WindowY == 0 && ViewportX == 0 && ViewportY == 0;
}

/// <summary>Actual native DIB layout, kept separate from the requested allocation.</summary>
/// <param name="Width">Actual pixel width.</param>
/// <param name="Height">Actual positive storage height.</param>
/// <param name="Stride">Actual row-byte count.</param>
/// <param name="Planes">Actual color-plane count.</param>
/// <param name="BitsPerPixel">Actual pixel depth.</param>
/// <param name="Bits">Actual allocation address.</param>
internal readonly record struct DesktopDcBitmapInfo(int Width, int Height, int Stride, int Planes,
    int BitsPerPixel, nint Bits);
