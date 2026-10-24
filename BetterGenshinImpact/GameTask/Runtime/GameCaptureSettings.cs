using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Helpers;
using Fischless.GameCapture;
using System.Collections.Generic;

namespace BetterGenshinImpact.GameTask.Runtime;

/// <summary>
/// 截图器 Start 参数的唯一构建处，各 Provider 共用
/// </summary>
public static class GameCaptureSettings
{
    /// <summary>Freeze the configured capture options for one runtime attachment.</summary>
    public static Dictionary<string, object> From(AllConfig config)
    {
        return new Dictionary<string, object>
        {
            // BitBlt 必须传这个键，否则 Start 直接返回，截图器不会启动
            { "autoFixWin11BitBlt", OsVersionHelper.IsWindows11_OrGreater && config.AutoFixWin11BitBlt },
            // WGC 限流：0 = 不启用；>0 = DWM 最小推帧间隔（毫秒）
            { "MinUpdateIntervalMs", config.WgcMinUpdateIntervalMs },
            // WGC V2 开关：CPU 颜色转换回退（默认 GPU 打包）
            { "UseCpuConvert", config.WgcV2UseCpuConvert },
            // WGC V2 validates the exact mode at Start; pending work never changes it mid-run.
            { "ReadbackMode", config.WgcV2ReadbackMode },
        };
    }

    /// <summary>Report the mode of the attached capture, independently of saved configuration; this is not a health check.</summary>
    public static string? GetReadbackModeName(IGameCapture? capture)
    {
        if (capture is not { IsCapturing: true } || capture is not IGameCaptureReadback readback)
            return null;
        return readback.ReadbackMode switch
        {
            GameCaptureReadbackMode.Blocking => "blocking",
            GameCaptureReadbackMode.PollSingleV1 => "poll_single_v1",
            _ => null,
        };
    }
}
