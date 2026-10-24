using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.GameTask.Common.Map;
using BetterGenshinImpact.GameTask.Model.Area;
using System;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Runtime;
using Microsoft.Extensions.Logging;
using static BetterGenshinImpact.GameTask.Common.TaskControl;

namespace BetterGenshinImpact.GameTask.AutoPathing;

/// <summary>
/// 转动视角到目标角度
/// </summary>
/// <param name="runtime">本次运行使用的运行环境</param>
/// <param name="ct">取消令牌</param>
public class CameraRotateTask(GameRuntime runtime, CancellationToken ct)
{
    /// <summary>
    /// 本次运行使用的运行环境
    /// </summary>
    private readonly GameRuntime _runtime = runtime;

    private readonly double _dpi = runtime.SystemInfo.DpiScale;

    /// <summary>
    /// 向目标角度旋转
    /// </summary>
    /// <param name="targetOrientation"></param>
    /// <param name="imageRegion"></param>
    /// <returns></returns>
    public float RotateToApproach(float targetOrientation, ImageRegion imageRegion)
    {
        ct.ThrowIfCancellationRequested();
        return RotateToApproach(targetOrientation, CameraOrientation.Compute(imageRegion.SrcMat));
    }

    /// <summary>Rotate from an already measured camera yaw without repeating recognition or invoking its fallback.</summary>
    /// <param name="targetOrientation">Desired yaw in degrees.</param>
    /// <param name="currentOrientation">Current yaw measured from the caller's validated frame.</param>
    /// <returns>The same signed angular error used by the existing image-based controller.</returns>
    public float RotateToApproach(float targetOrientation, float currentOrientation) =>
        ApplyMeasuredRotation(targetOrientation, currentOrientation, _dpi, ct,
            (dx, dy) => InputHub.Foreground.Mouse.MoveMouseBy(dx, dy));

    /// <summary>Shared rotation gains and dispatch boundary; a supplied sink permits tests without creating native input.</summary>
    internal static float ApplyMeasuredRotation(float targetOrientation, float currentOrientation, double dpi,
        CancellationToken cancellationToken, Action<int, int> moveMouse)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!float.IsFinite(targetOrientation) || !float.IsFinite(currentOrientation)
            || !double.IsFinite(dpi) || dpi <= 0)
            throw new ArgumentOutOfRangeException(nameof(currentOrientation), "Camera yaw and DPI must be finite, with positive DPI.");
        var diff = (currentOrientation - targetOrientation + 180) % 360 - 180;
        diff += diff < -180 ? 360 : 0;
        if (!float.IsFinite(diff)) throw new ArgumentOutOfRangeException(nameof(currentOrientation));
        if (diff == 0)
        {
            return diff;
        }

        // 平滑的旋转视角
        // todo dpi 和分辨率都会影响转动速度
        double controlRatio = 1;
        if (Math.Abs(diff) > 90)
        {
            controlRatio = 4;
        }
        else if (Math.Abs(diff) > 30)
        {
            controlRatio = 3;
        }
        else if (Math.Abs(diff) > 5)
        {
            controlRatio = 2;
        }

        var deltaX = checked((int)Math.Round(-controlRatio * diff * dpi));
        // Cancellation may arrive during recognition or control calculation; never dispatch its pending movement.
        cancellationToken.ThrowIfCancellationRequested();
        moveMouse(deltaX, 0);
        return diff;
    }

    /// <summary>
    /// 转动视角到目标角度
    /// </summary>
    /// <param name="targetOrientation">目标角度</param>
    /// <param name="maxDiff">最大误差</param>
    /// <param name="maxTryTimes">最大尝试次数（超时时间）</param>
    /// <returns></returns>
    public async Task<bool> WaitUntilRotatedTo(int targetOrientation, int maxDiff, int maxTryTimes = 50)
    {
        bool isSuccessful = false;
        int count = 0;
        while (!ct.IsCancellationRequested)
        {
            using var screen = _runtime.CaptureToRectArea();
            if (Math.Abs(RotateToApproach(targetOrientation, screen)) < maxDiff)
            {
                isSuccessful = true;
                break;
            }

            if (count > maxTryTimes)
            {
                Logger.LogWarning("Timed out rotating to the target angle; stopping rotation");
                break;
            }

            await _runtime.Delay(50, ct);
            count++;
        }
        return isSuccessful;
    }
}
