using BetterGenshinImpact.GameTask.Common.BgiVision;
using System;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.Model.Area;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using BetterGenshinImpact.Helpers;
using Microsoft.Extensions.Logging;
using BetterGenshinImpact.GameTask.Runtime;
using static BetterGenshinImpact.GameTask.Common.TaskControl;

namespace BetterGenshinImpact.GameTask.Common.Job;

/// <summary>
/// 跳过月卡
/// </summary>
/// <param name="runtime">本次运行使用的运行环境</param>
public class BlessingOfTheWelkinMoonTask(GameRuntime runtime)
{
    /// <summary>
    /// 本次运行使用的运行环境
    /// </summary>
    private readonly GameRuntime _runtime = runtime;

    public string Name => "自动点击空月祝福";

    /// <summary>Keep the existing standalone best-effort behavior.</summary>
    /// <param name="ct">The existing task token.</param>
    public Task Start(CancellationToken ct) => Start(ct, null);

    /// <summary>Allow reset teleport to carry its exact capture reader into the loading-screen helper.</summary>
    /// <param name="ct">The existing linked teleport token.</param>
    /// <param name="capture">An explicit reset-teleport reader, or null for the legacy path.</param>
    internal Task Start(CancellationToken ct, Func<ImageRegion>? capture)
    {
        // A supplied reader owns only one returned region; there is no nullable-image fallback.
        ImageRegion Capture() => capture is null ? _runtime.CaptureToRectArea() : capture();
        return RunCheckAsync(CheckAsync, error => Logger.LogError("Welkin Moon check failed: " + error.Message), capture is not null);

        async Task CheckAsync()
        {
            var t = ServerTimeHelper.GetServerTimeNow().AddMinutes(5);
            if (t.Hour == 4 && t.Minute < 10)
            {
                using var ra = Capture();
                if (Bv.IsInBlessingOfTheWelkinMoon(ra) || ra.Find(ElementRecognition.Get("Primogem", ra)).IsExist())
                {
                    Logger.LogInformation("检测到空月祝福界面，自动点击");
                    _runtime.GameRegion1080PPosMove(100, 100);
                    for (int i = 0, j = 0; i < 20 && j < 3; ++i)
                    {
                        if (j == 0)
                        {
                            // 双击快速跳过
                            _runtime.GameRegion1080PPosClick(100, 100);
                            await Task.Delay(100, ct);
                            _runtime.GameRegion1080PPosClick(100, 100);
                        }
                        await _runtime.Delay(500, ct);
                        using var ra2 = Capture();
                        if (Bv.IsInBlessingOfTheWelkinMoon(ra2))
                        {
                            // 仍在空月祝福界面
                            j = 0;
                        }
                        else if (ra2.Find(ElementRecognition.Get("Primogem", ra2)).IsExist())
                        {
                            // 仍在原石界面
                            j = 0;
                        }
                        else
                        {
                            // 连续3次没检测到才认为处理完毕，避免淡出/淡入特效影响
                            ++j;
                        }
                    }
                    Logger.LogInformation("Welkin Moon handling complete");
                }
            }
        }
    }

    /// <summary>Preserve legacy logging, but never swallow an opted-in capture abort into later teleport input.</summary>
    /// <param name="check">The existing Welkin check, isolated for deterministic exception-boundary tests.</param>
    /// <param name="logError">The existing best-effort error logger.</param>
    /// <param name="propagateCaptureStops">True only for the explicit teleport reader.</param>
    internal static async Task RunCheckAsync(Func<Task> check, Action<Exception> logError, bool propagateCaptureStops)
    {
        try
        {
            await check();
        }
        catch (Exception error) when (propagateCaptureStops && TeleportCaptureReadback.IsTerminal(error))
        {
            throw;
        }
        catch (Exception error)
        {
            logError(error);
        }
    }
}
