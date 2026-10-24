namespace Fischless.GameCapture.DesktopDc;

/// <summary>Own one capture's GDI resources on its caller thread, including partial initialization and uncertain cleanup.</summary>
internal sealed class DesktopDcGdiOwner : IDisposable
{
    /// <summary>The first implementation admits only the experimentally verified crop shape.</summary>
    internal const int Width = 1920, Height = 1080, Stride = (Width * 3 + 3) & ~3;
    /// <summary>Native calls can be replaced by managed fakes without replacing the ownership algorithm.</summary>
    private readonly IDesktopDcGdi _native;
    /// <summary>GetDC and ReleaseDC must remain on the same caller thread.</summary>
    private readonly int _thread = Environment.CurrentManagedThreadId;
    /// <summary>Owned resources and borrowed old selection; none may cross a public Capture call.</summary>
    private nint _screen, _memory, _bitmap, _oldBitmap, _bits;
    /// <summary>Admission and publication state are never inferred from a nonzero pointer alone.</summary>
    private bool _initialized, _pixelsValid, _disposed, _initializationAttempted, _selectionAttempted;
    /// <summary>At most six cleanup results are retained; native failures are never retried.</summary>
    private readonly List<string> _cleanupFailures = new();

    /// <summary>Retain the owner before starting any native initialization.</summary>
    internal DesktopDcGdiOwner(IDesktopDcGdi native) => _native = native;

    /// <summary>Only a successful copy and flush expose the borrowed allocation.</summary>
    internal nint Bits
    {
        get
        {
            CheckThread();
            if (_disposed || !_pixelsValid) throw new InvalidOperationException("No flushed desktop pixels.");
            return _bits;
        }
    }

    /// <summary>True only if every attempted cleanup operation returned success.</summary>
    internal bool CleanupSucceeded => _disposed && _cleanupFailures.Count == 0;

    /// <summary>Bounded facts remain available after resource addresses have been retired.</summary>
    internal IReadOnlyList<string> CleanupFailures => _cleanupFailures;

    /// <summary>Acquire the desktop DC and checked crop-sized DIB once; the caller always disposes this owner.</summary>
    internal void Initialize()
    {
        CheckThread();
        if (_disposed || _initializationAttempted) throw new InvalidOperationException("GDI owner already used.");
        _initializationAttempted = true;
        _screen = _native.GetScreenDc();
        if (_screen == 0) throw new InvalidOperationException("GetDC(NULL) failed.");
        if (!_native.ReadDeviceInfo(_screen).IsSupported)
            throw new InvalidOperationException("Unsupported desktop DC raster/format/mapping.");
        _memory = _native.CreateMemoryDc(_screen);
        if (_memory == 0) throw new InvalidOperationException("CreateCompatibleDC failed.");
        _bitmap = _native.CreateBitmap(_screen, Width, Height, Stride, out _bits);
        if (_bitmap == 0 || _bits == 0) throw new InvalidOperationException("CreateDIBSection failed.");
        var actual = _native.ReadBitmapInfo(_bitmap);
        if (actual != new DesktopDcBitmapInfo(Width, Height, Stride, 1, 24, _bits))
            throw new InvalidOperationException("Unexpected desktop DIB layout.");
        _selectionAttempted = true;
        var previous = _native.SelectBitmap(_memory, _bitmap);
        if (previous == 0 || previous == -1) throw new InvalidOperationException("SelectObject failed.");
        _oldBitmap = previous;
        _initialized = true;
    }

    /// <summary>One SRCCOPY and flush; no retry, cached frame or Pending result is available.</summary>
    internal void Copy(int left, int top)
    {
        CheckThread();
        if (_disposed || !_initialized) throw new InvalidOperationException("GDI owner is unavailable.");
        _pixelsValid = false;
        if (!_native.Copy(_memory, _screen, left, top, Width, Height))
            throw new InvalidOperationException("Desktop SRCCOPY failed.");
        if (!_native.Flush()) throw new InvalidOperationException("Desktop copy GdiFlush failed.");
        _pixelsValid = true;
    }

    /// <summary>Attempt every independently safe cleanup once; failure to deselect requires deleting the private DC first.</summary>
    public void Dispose()
    {
        CheckThread();
        if (_disposed) return;
        _disposed = true;
        _pixelsValid = false;
        if (_bitmap == 0 && _bits != 0)
            _cleanupFailures.Add("bitmap_address: nonzero DIB address without an owned bitmap handle");
        if (_screen != 0) Release("flush", _native.Flush);
        var deselected = !_selectionAttempted;
        if (_oldBitmap != 0)
            deselected = Release("restore_bitmap", () => _native.SelectBitmap(_memory, _oldBitmap) == _bitmap);
        var memoryDeleted = false;
        if (!deselected && _memory != 0)
            memoryDeleted = Release("delete_dc_before_bitmap", () => _native.DeleteMemoryDc(_memory));
        if (_bitmap != 0)
        {
            if (deselected || memoryDeleted) Release("delete_bitmap", () => _native.DeleteBitmap(_bitmap));
            else _cleanupFailures.Add("delete_bitmap: not attempted because selection remains uncertain");
        }
        if (_memory != 0 && deselected) Release("delete_dc", () => _native.DeleteMemoryDc(_memory));
        if (_screen != 0) Release("release_screen_dc", () => _native.ReleaseScreenDc(_screen));
        // Do not retry a failed native cleanup from Stop, Dispose, another call or a finalizer.
        _screen = _memory = _bitmap = _oldBitmap = _bits = 0;
    }

    /// <summary>Record failures without preventing cleanup of independently owned resources.</summary>
    private bool Release(string operation, Func<bool> release)
    {
        try
        {
            if (release()) return true;
            _cleanupFailures.Add(operation + ": returned false");
        }
        catch (Exception error) { _cleanupFailures.Add(operation + ": " + error.GetType().Name + ": " + error.Message); }
        return false;
    }

    /// <summary>Cross-thread lifecycle callers get independent owners rather than transferring GDI handles.</summary>
    private void CheckThread()
    {
        if (Environment.CurrentManagedThreadId != _thread)
            throw new InvalidOperationException("Desktop GDI owner thread changed.");
    }
}
