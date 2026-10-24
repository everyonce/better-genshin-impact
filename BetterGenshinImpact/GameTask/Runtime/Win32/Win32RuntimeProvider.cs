using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Input.Backends.Win32;
using BetterGenshinImpact.Core.Mask;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.Service.Instance;
using BetterGenshinImpact.GameTask.Model;
using BetterGenshinImpact.Service.Interface;
using BetterGenshinImpact.Service.I18n;
using BetterGenshinImpact.Service;
using BetterGenshinImpact.View.Windows;
using Fischless.GameCapture;
using Microsoft.Extensions.Logging;
using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask.Runtime.Win32;

/// <summary>
/// 本机 Win32 游戏窗口的运行环境：本地原神、Windows 云原神
/// </summary>
public sealed class Win32RuntimeProvider(
    IConfigService configService,
    IMaskWindowDrawingBoard maskWindowDrawingBoard,
    IMaskWindowMapState maskWindowMapState,
    IMaskWindowHost maskWindowHost,
    ILogger<Win32RuntimeProvider> logger)
    : IGameRuntimeProvider
{
    public GameRuntimeKind Kind => GameRuntimeKind.Win32Window;

    /// <summary>
    /// 找到游戏窗口就附着；找不到时，开启了关联启动则启动游戏后附着，否则提示并返回 null
    /// </summary>
    public Task<GameRuntime?> AcquireAsync(CancellationToken ct) => AcquireCoreAsync(ct, desktopStartupFocus: false);

    /// <summary>Used only by explicit automated startup while the task gate and runtime start lock are owned.</summary>
    internal Task<GameRuntime?> AcquireForDesktopAutomationAsync(CancellationToken ct) => AcquireCoreAsync(ct, desktopStartupFocus: true);

    /// <summary>Find one target; the optional startup action never changes ordinary capture or task focus policy.</summary>
    private async Task<GameRuntime?> AcquireCoreAsync(CancellationToken ct, bool desktopStartupFocus)
    {
        var automation = CommandLineOptions.Instance.AutomationMode;
        if (automation && (InstanceBootstrap.Current.Context.InstanceType != BetterGiInstanceType.ChildSession
                           || !System.Windows.Forms.SystemInformation.TerminalServerSession))
            throw new InvalidOperationException("Automated Genshin startup is restricted to the real RDP child.");
        var config = configService.Get();
        var desktop = config.CaptureMode == nameof(CaptureModes.DesktopDc);
        if (desktopStartupFocus && (!automation || !desktop))
            throw new InvalidOperationException("Explicit automated DesktopDc startup is required.");
        var startupPolicy = desktopStartupFocus ? DesktopCapturePolicy.Validate(config.DesktopDcSourcePolicy) : null;
        // Desktop capture observes the already foreground game; it never changes HDR or starts the game.
        if (!desktop) DisableGenshinHdrIfNeeded(config);

        var hWnd = SystemControl.FindGenshinImpactHandle();
        if (hWnd == IntPtr.Zero)
        {
            if (desktop) throw new InvalidOperationException("desktop_capture_target_unavailable");
            var startConfig = config.GenshinStartConfig;
            if (startConfig.LinkedStartEnabled || automation)
            {
                if (automation && (!File.Exists(startConfig.InstallPath)
                    || (!string.Equals(Path.GetFileName(startConfig.InstallPath), "GenshinImpact.exe", StringComparison.OrdinalIgnoreCase)
                        && !string.Equals(Path.GetFileName(startConfig.InstallPath), "YuanShen.exe", StringComparison.OrdinalIgnoreCase))))
                    throw new InvalidOperationException("Configure an existing GenshinImpact.exe or YuanShen.exe path before automated startup.");
                if (string.IsNullOrEmpty(startConfig.InstallPath))
                {
                    await ThemedMessageBox.ErrorAsync(I18nService.Instance.Translate("没有找到原神的安装路径"));
                    return null;
                }

                hWnd = await SystemControl.StartFromLocalAsync(startConfig.InstallPath, ct);
                if (hWnd == IntPtr.Zero)
                {
                    // 启动失败的提示已由 StartFromLocalAsync 给出
                    return null;
                }
            }

            if (hWnd == IntPtr.Zero)
            {
                await ThemedMessageBox.ErrorAsync(I18nService.Instance.Translate("未找到原神窗口，请先启动原神！"));
                return null;
            }
        }

        ct.ThrowIfCancellationRequested();
        if (desktopStartupFocus) await DesktopDcStartupFocus.AcquireAsync(hWnd, ct);
        ct.ThrowIfCancellationRequested();
        if (desktopStartupFocus) CheckDesktopStartupSelection(configService.Get(), startupPolicy!);
        return AttachTo(hWnd);
    }

    /// <summary>UI selection may change during read-only confirmation; never attach a different backend or policy.</summary>
    internal static void CheckDesktopStartupSelection(AllConfig config, string expectedPolicy)
    {
        if (config.CaptureMode != nameof(CaptureModes.DesktopDc) || config.DesktopDcSourcePolicy != expectedPolicy)
            throw new InvalidOperationException("desktop_startup_capture_selection_changed");
    }

    /// <summary>
    /// 附着到指定的游戏窗口，手动选窗也走这里。在 UI 线程上调用
    /// </summary>
    public GameRuntime AttachTo(nint hWnd)
    {
        var config = configService.Get();
        var mode = GetCaptureMode(config);
        var desktop = mode == CaptureModes.DesktopDc;
        var policy = desktop ? DesktopCapturePolicy.Validate(config.DesktopDcSourcePolicy) : null;
        // 激活窗口，保证后面能够正常获取窗口信息。DesktopDc only observes an already foreground target.
        if (!desktop) SystemControl.ActivateWindow(hWnd);

        var window = new Win32GameWindow(hWnd);
        IGameCapture? capture = null;
        IDisposable? overlayScope = null;
        try
        {
            if (window.IsMinimized)
            {
                throw new ArgumentException("The game window cannot be minimized");
            }
            if (desktop && !window.IsForeground)
                throw new InvalidOperationException("desktop_capture_target_not_foreground");

            // 先按画面区域构建 SystemInfo：分辨率不合规时在启动截图器之前失败
            var systemInfo = new SystemInfo(window.Viewport, maskWindowDrawingBoard);

            if (desktop) overlayScope = DesktopCaptureOverlayScope.Acquire(maskWindowHost);
            capture = GameCaptureFactory.Create(mode);
            capture.Start(hWnd, GameCaptureSettings.From(config));
            IInputBackend input = desktop && policy == DesktopCapturePolicy.ObserveOnly
                ? new ObserveOnlyInputBackend() : new Win32InputBackend(hWnd);
            var runtime = new GameRuntime(Kind, window, capture, input, systemInfo,
                maskWindowDrawingBoard, maskWindowMapState, policy, overlayScope);
            overlayScope = null; // Runtime owns suppression through confirmed capture disposal.

            // 自动查找、关联启动、手动选窗都经过这里；同一个游戏进程只通知一次
            if (!desktop) StarwardPlaytime.TryRecord(window, config.GenshinStartConfig);
            return runtime;
        }
        catch
        {
            capture?.Dispose();
            overlayScope?.Dispose();
            window.Dispose();
            throw;
        }
    }

    /// <summary>
    /// 结束游戏进程：已绑定时只结束绑定窗口所属的进程名
    /// </summary>
    public void CloseGame(GameRuntime? current) => SystemControl.CloseGameProcesses(current?.Window);

    private static CaptureModes GetCaptureMode(AllConfig config)
    {
        try
        {
            return config.CaptureMode.ToCaptureMode();
        }
        catch (Exception)
        {
            config.CaptureMode = CaptureModes.BitBlt.ToString();
            return CaptureModes.BitBlt;
        }
    }

    private void DisableGenshinHdrIfNeeded(AllConfig config)
    {
        if (!config.GenshinStartConfig.AutoDisableGenshinHdrEnabled)
        {
            return;
        }

        if (!GenshinHdrRegistryHelper.TryDisableHdr(out _))
        {
            return;
        }

        // 这行日志可能看不到
        logger.LogWarning("Genshin Impact HDR was enabled and has been turned off automatically. If the game is already running, restart it for the change to take effect.");
    }
}
