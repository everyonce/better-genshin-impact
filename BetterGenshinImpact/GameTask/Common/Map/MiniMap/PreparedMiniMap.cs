using System;
using OpenCvSharp;

namespace BetterGenshinImpact.GameTask.Common.Map.MiniMap;

/// <summary>Owned map pixels and mask derived from the same preprocessing pass as the measured camera yaw.</summary>
public sealed class PreparedMiniMap : IDisposable
{
    /// <summary>Independent output Mats remain valid when the preprocessor receives its next image.</summary>
    private readonly Mat _pixels, _mask;
    /// <summary>Disposed outputs must never be reused by a later local match.</summary>
    private bool _disposed;

    /// <summary>Transfer ownership of the completed mask calculation without retaining its mutable scratch state.</summary>
    internal PreparedMiniMap(Mat pixels, Mat mask, float yawDegrees, float yawConfidence)
    {
        _pixels = pixels;
        _mask = mask;
        YawDegrees = yawDegrees;
        YawConfidence = yawConfidence;
    }

    /// <summary>Borrowed processed pixels; only this result disposes them.</summary>
    public Mat Pixels { get { ObjectDisposedException.ThrowIf(_disposed, this); return _pixels; } }
    /// <summary>Borrowed matching mask from the exact same input image.</summary>
    public Mat Mask { get { ObjectDisposedException.ThrowIf(_disposed, this); return _mask; } }
    /// <summary>Original recognizer output, without rounding or a low-confidence fallback.</summary>
    public float YawDegrees { get; }
    /// <summary>Confidence associated with the yaw used to prepare these pixels.</summary>
    public float YawConfidence { get; }

    /// <summary>Release both owned outputs exactly once; the source image and preprocessor remain independently owned.</summary>
    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _pixels.Dispose();
        _mask.Dispose();
    }
}
