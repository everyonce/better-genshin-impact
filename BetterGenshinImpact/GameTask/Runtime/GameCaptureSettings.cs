using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.Helpers;
using Fischless.GameCapture;
using Fischless.GameCapture.Graphics;
using System;
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
        // Host capture has no WGC readback/retention or BitBlt registry startup options.
        if (config.CaptureMode == nameof(CaptureModes.DesktopDc))
        {
            DesktopCapturePolicy.Validate(config.DesktopDcSourcePolicy);
            return [];
        }
        var settings = new Dictionary<string, object>
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
        // Disabled remains an omitted library opt-in, preserving the tested default startup path.
        if (config.WgcV2SourceRetention == "hold-until-readback-v1")
            settings["ExperimentalSourceRetention"] = config.WgcV2SourceRetention;
        else if (config.WgcV2SourceRetention != "disabled")
            throw new ArgumentOutOfRangeException(nameof(config), "Unknown WGC V2 source retention setting.");
        return settings;
    }

    /// <summary>Report active V2 source selection without native work or a capture lock; not a health check.</summary>
    public static string? GetSourceRetentionName(IGameCapture? capture) =>
        capture is GraphicsCaptureV2 { IsCapturing: true } v2 ? v2.SourceRetentionMode : null;

    /// <summary>Report active V2 conversion independently of configuration; stopped/other captures have no value.</summary>
    public static string? GetConversionName(IGameCapture? capture) =>
        capture is GraphicsCaptureV2 { IsCapturing: true } v2 ? v2.ConversionMode : null;

    /// <summary>Read immutable runtime policy only; status must not wait on native capture or its gate.</summary>
    public static string? GetDesktopDcSourcePolicy(GameRuntime? runtime) =>
        runtime is { IsStopping: false, IsDesktopCapture: true } && runtime.Capture.IsCapturing
            ? runtime.DesktopDcSourcePolicy : null;

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
