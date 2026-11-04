using Fischless.GameCapture.Graphics.Helpers;
using SharpDX.Direct3D11;
using System.Diagnostics;
using System.Runtime.InteropServices;
using OpenCvSharp;
using SharpDX;
using Vanara.PInvoke;
using Device = SharpDX.Direct3D11.Device;

namespace Fischless.GameCapture.DwmSharedSurface;

public partial class SharedSurfaceCapture : IGameCapture
{
    // 窗口句柄
    private nint _hWnd;

    private static readonly object LockObject = new();

    // D3D 设备
    private readonly SharedSurfaceResources<Device, Texture2D> _resources = new(
        () => new Device(SharpDX.Direct3D.DriverType.Hardware, DeviceCreationFlags.BgraSupport)); // Software/Hardware

    // 截图区域
    private ResourceRegion? _region;
    private RECT? _captureRect;

    // 暂存贴图
    // The device owner also retires its staging texture whenever the device changes.

    // Surface 大小
    private int _surfaceWidth;
    private int _surfaceHeight;

    public bool IsCapturing { get; private set; }

    [LibraryImport("user32.dll", EntryPoint = "DwmGetDxSharedSurface", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool DwmGetDxSharedSurface(IntPtr hWnd, out IntPtr phSurface, out long pAdapterLuid, out long pFmtWindow, out long pPresentFlags, out long pWin32KUpdateId);

    public void Dispose()
    {
        Stop();
        GC.SuppressFinalize(this);
    }

    public void Start(nint hWnd, Dictionary<string, object>? settings = null)
    {
        lock (LockObject)
        {
            StopCore();
            try
            {
                _hWnd = hWnd;
                User32.ShowWindow(hWnd, ShowWindowCommand.SW_RESTORE);
                (_region, _captureRect) = GetGameScreenInfo(hWnd);
                _resources.ResetDevice();
                IsCapturing = true;
            }
            catch
            {
                StopCore();
                throw;
            }
        }
    }

    /// <summary>
    /// 从 GetWindowRect 的带窗口阴影面积矩形 截取出 GetClientRect的矩形（游戏区域）
    /// </summary>
    /// <param name="hWnd"></param>
    /// <returns></returns>
    private static (ResourceRegion? Region, RECT? CaptureRect) GetGameScreenInfo(nint hWnd)
    {
        var exStyle = User32.GetWindowLong(hWnd, User32.WindowLongFlags.GWL_EXSTYLE);
        if ((exStyle & (int)User32.WindowStylesEx.WS_EX_TOPMOST) != 0)
        {
            return (null, null);
        }

        ResourceRegion region = new();
        User32.GetWindowRect(hWnd, out var windowWithShadowRect);
        DwmApi.DwmGetWindowAttribute<RECT>(hWnd, DwmApi.DWMWINDOWATTRIBUTE.DWMWA_EXTENDED_FRAME_BOUNDS, out var windowRect);
        User32.GetClientRect(hWnd, out var clientRect);

        region.Left = windowRect.Left - windowWithShadowRect.Left;
        // 标题栏 windowRect.Height - clientRect.Height 上阴影 windowRect.Top - windowWithShadowRect.Top
        region.Top = windowRect.Height - clientRect.Height + windowRect.Top - windowWithShadowRect.Top;
        region.Right = region.Left + clientRect.Width;
        region.Bottom = region.Top + clientRect.Height;
        region.Front = 0;
        region.Back = 1;

        var left = windowRect.Left;
        var top = windowRect.Top + windowRect.Height - clientRect.Height;
        var right = left + clientRect.Width;
        var bottom = top + clientRect.Height;

        return (region, new RECT(left, top, right, bottom));
    }

    public GameCaptureFrame? Capture()
    {
        lock (LockObject)
        {
            if (_resources.Device is not { } device)
            {
                Debug.WriteLine("D3Device is null.");
                return null;
            }

            if (!DwmGetDxSharedSurface(_hWnd, out var phSurface, out _, out _, out _, out _))
            {
                return null;
            }
            if (phSurface == 0)
            {
                return null;
            }

            try
            {
                using var surfaceTexture = device.OpenSharedResource<Texture2D>(phSurface);

                if (_resources.Staging == null || _surfaceWidth != surfaceTexture.Description.Width ||
                    _surfaceHeight != surfaceTexture.Description.Height)
                {
                    if (User32.IsIconic(_hWnd))
                        return null;

                    _resources.ClearStaging();
                    _surfaceWidth = surfaceTexture.Description.Width;
                    _surfaceHeight = surfaceTexture.Description.Height;
                    (_region, _captureRect) = GetGameScreenInfo(_hWnd);
                }

                var staging = _resources.Staging ?? _resources.GetOrCreateStaging(currentDevice =>
                    Direct3D11Helper.CreateStagingTexture(currentDevice, _surfaceWidth, _surfaceHeight, _region));
                // Device-lost readback errors must reach the same recovery path as OpenSharedResource errors.
                var mat = staging.CreateMat(device, surfaceTexture, _region, propagateSharpDxErrors: true);
                if (mat == null)
                {
                    return null;
                }

                return new GameCaptureFrame(mat, _captureRect);
            }
            catch (SharpDXException e)
            {
                Debug.WriteLine($"SharpDXException: {e.Descriptor}");
                ClearSurfaceGeometry();
                try { _resources.ResetDevice(); }
                catch
                {
                    // Replacement failure leaves no device/staging references; explicit Start can retry.
                    IsCapturing = false;
                    throw;
                }
            }

            return null;
        }
    }

    public void Stop()
    {
        lock (LockObject)
        {
            StopCore();
        }
    }

    /// <summary>Clears metadata before resource cleanup so exceptions cannot publish an active, disposed session.</summary>
    private void StopCore()
    {
        IsCapturing = false;
        _hWnd = 0;
        ClearSurfaceGeometry();
        _resources.Dispose();
    }

    /// <summary>Invalidates old dimensions and bounds whenever their device or session is retired.</summary>
    private void ClearSurfaceGeometry()
    {
        _surfaceWidth = _surfaceHeight = 0;
        _region = null;
        _captureRect = null;
    }
}
