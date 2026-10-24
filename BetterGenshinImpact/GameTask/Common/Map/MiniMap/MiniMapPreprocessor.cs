using System;
using System.Diagnostics;
using OpenCvSharp;

namespace BetterGenshinImpact.GameTask.Common.Map.MiniMap;

public class MiniMapPreprocessor : IDisposable
{
    private readonly MaskCalculator _maskCalculator = new();
    private readonly CameraOrientationCalculator _coCalculator = new();
    private bool _disposed;
    
    public (float, float) PredictRotationWithConfidence(Mat miniMap)
    {
        var (src, mask) = _maskCalculator.Process1(miniMap);
        using (src)
        {
            return _coCalculator.PredictRotation(src, mask);
        }
    }

    public float PredictRotation(Mat miniMap)
    {
        return PredictRotationWithConfidence(miniMap).Item1;
    }

    public (Mat, Mat) GetMiniMapAndMask(Mat miniMap)
    {
        //Debug.WriteLine($"输入图片尺寸为{miniMap.Size()} 类型为 {miniMap.Type()}");
        var (src, mask) = _maskCalculator.Process1(miniMap);
        using (src)
        {
            var (angle, _) = _coCalculator.PredictRotation(src, mask);
            return _maskCalculator.Process2(angle);
        }
    }

    /// <summary>
    /// Measure yaw once and prepare owned matching pixels from that same scratch state.
    /// Invalid or low-confidence yaw returns null before Process2, preserving callers' early rejection.
    /// </summary>
    public PreparedMiniMap? TryPrepare(Mat miniMap, float minimumYawConfidence)
    {
        if (!float.IsFinite(minimumYawConfidence) || minimumYawConfidence is < 0 or > 1)
            throw new ArgumentOutOfRangeException(nameof(minimumYawConfidence));
        ObjectDisposedException.ThrowIf(_disposed, this);
        var (src, mask) = _maskCalculator.Process1(miniMap);
        using (src)
        {
            var (angle, confidence) = _coCalculator.PredictRotation(src, mask);
            if (!float.IsFinite(angle) || angle is < 0 or >= 360 || !float.IsFinite(confidence)
                || confidence < minimumYawConfidence || confidence > 1) return null;
            // Process2 consumes the current Process1 scratch state; do not run another image between these calls.
            var (pixels, preparedMask) = _maskCalculator.Process2(angle);
            try { return new PreparedMiniMap(pixels, preparedMask, angle, confidence); }
            catch { pixels.Dispose(); preparedMask.Dispose(); throw; }
        }
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _coCalculator.Dispose();
        _maskCalculator.Dispose();
    }
}
