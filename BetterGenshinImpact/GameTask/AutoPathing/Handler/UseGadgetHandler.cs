using BetterGenshinImpact.Core.Input;
using Microsoft.Extensions.Logging;
using System;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Recognition.OCR;
using BetterGenshinImpact.Core.Recognition.OpenCv;
using BetterGenshinImpact.GameTask.AutoPathing.Model;
using static BetterGenshinImpact.GameTask.Common.TaskControl;
using BetterGenshinImpact.Core.Simulator.Extensions;
using BetterGenshinImpact.GameTask.AutoFight.Assets;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Model.Area;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Helpers;
using OpenCvSharp;

namespace BetterGenshinImpact.GameTask.AutoPathing.Handler;

/// <summary>
/// 触发使用小道具
/// </summary>
/// <param name="runtime">本次运行使用的运行环境</param>
public class UseGadgetHandler(GameRuntime runtime) : IActionHandler
{
    /// <summary>
    /// 本次运行使用的运行环境
    /// </summary>
    private readonly GameRuntime _runtime = runtime;

    public async Task RunAsync(CancellationToken ct, WaypointForTrack? waypointForTrack = null, object? config = null)
    {
        Logger.LogInformation("Executing {Text}", "Using gadget");
        InputHub.Foreground.SimulateAction(GIActions.QuickUseGadget);


        if (waypointForTrack != null
            && !string.IsNullOrEmpty(waypointForTrack.ActionParams)
            && waypointForTrack.ActionParams.Contains("not_wait", StringComparison.OrdinalIgnoreCase))
        {
            // 不等待
            InputHub.Foreground.SimulateAction(GIActions.QuickUseGadget);
        }
        else
        {
            double maxWaitSeconds = 100;
            if (waypointForTrack != null
                && !string.IsNullOrEmpty(waypointForTrack.ActionParams))
            {
                double.TryParse(waypointForTrack.ActionParams, out maxWaitSeconds); // 最大等待时间，单位秒
            }

            using var screen = _runtime.CaptureToRectArea();
            var cd = GetCurrentCd(screen);
            if (cd > 100)
            {
                Logger.LogWarning("Gadget is on cooldown with {Cd} seconds remaining. This may be a recognition error; skipping", cd);
                InputHub.Foreground.SimulateAction(GIActions.QuickUseGadget);
            }
            else if (cd > 0)
            {
                Logger.LogInformation("Gadget is on cooldown; waiting {Cd} seconds for it to end", cd);
                // 等待小道具CD结束
                int waitTime; // 等待CD结束后再继续
                if (cd > maxWaitSeconds)
                {
                    waitTime = (int)(maxWaitSeconds * 1000);
                    Logger.LogInformation("Cooldown is too long; using the maximum cooldown of {Max} seconds", maxWaitSeconds);
                }
                else
                {
                    waitTime = (int)(cd * 1000) + 100; // 等待CD结束后再继续
                }

                await _runtime.Delay(waitTime, ct);
                InputHub.Foreground.SimulateAction(GIActions.QuickUseGadget);
            }
            else
            {
                InputHub.Foreground.SimulateAction(GIActions.QuickUseGadget);
            }
        }

        Logger.LogInformation("Using gadget");
        await _runtime.Delay(300, ct);
    }

    /// <summary>
    /// 小道具是否正在CD中
    /// 77x77
    /// </summary>
    private double GetCurrentCd(ImageRegion imageRegion)
    {
        var eRa = imageRegion.DeriveCrop(AutoFightAssets.Get(imageRegion).ZCooldownRect);
        var eRaWhite = OpenCvCommonHelper.InRangeHsv(eRa.SrcMat, new Scalar(0, 0, 235), new Scalar(0, 25, 255));
        var text = OcrFactory.Paddle.OcrWithoutDetector(eRaWhite);
        return StringUtils.TryParseDouble(text);
    }
}
