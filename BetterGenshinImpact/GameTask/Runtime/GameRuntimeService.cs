using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Input.Backends.Win32;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Runtime.WebPage;
using BetterGenshinImpact.GameTask.Runtime.Win32;
using BetterGenshinImpact.Service;
using BetterGenshinImpact.Service.Instance;
using BetterGenshinImpact.Service.I18n;
using BetterGenshinImpact.Service.Interface;
using BetterGenshinImpact.View.Windows;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;

namespace BetterGenshinImpact.GameTask.Runtime;

/// <summary>
/// 游戏运行环境的编排：选定 Provider，负责启动（绑定）、停止（解绑），并持有当前运行环境。
/// <para>
/// 所有状态变更都在 UI 线程上串行执行：窗口与 WinEventHook 依赖消息循环，
/// 而 StartAsync / StopAsync 可能从任务线程或截图调度线程调用。
/// </para>
/// </summary>
public sealed class GameRuntimeService
{
    private readonly IGameRuntimeProvider _provider;
    private readonly TaskTriggerDispatcher _dispatcher;
    private readonly IConfigService _configService;
    private readonly ILogger<GameRuntimeService> _logger;
    /// <summary>
    /// 把运行环境停止事件转发给当前任务。
    /// </summary>
    private readonly TaskStopService _taskStopService;
    private readonly SemaphoreSlim _startLock = new(1, 1);
    private Task _stopTask = Task.CompletedTask;
    private long _stopVersion;
    /// <summary>UI-owned restart reservation; queued and manual starts cannot reopen capture before process exit.</summary>
    private bool _restartReserved;

    public GameRuntimeService(
        IEnumerable<IGameRuntimeProvider> providers,
        InstanceBootstrap bootstrap,
        TaskTriggerDispatcher dispatcher,
        IConfigService configService,
        ILogger<GameRuntimeService> logger,
        TaskStopService taskStopService)
    {
        _dispatcher = dispatcher;
        _configService = configService;
        _logger = logger;
        _taskStopService = taskStopService;

        var registered = providers.ToList();
        var expectedKind = bootstrap.Context.InstanceType == BetterGiInstanceType.WebView
            ? GameRuntimeKind.WebPage
            : GameRuntimeKind.Win32Window;
        _provider = registered.FirstOrDefault(p => p.Kind == expectedKind)
                    ?? throw new InvalidOperationException($"No runtime provider is registered for {expectedKind}");
        if (_provider is WebPageRuntimeProvider webPageProvider)
        {
            webPageProvider.StopCaptureBeforeCloseAsync = StopAsync;
        }

        _dispatcher.UiTaskStopTickEvent += OnRuntimeLost;
    }

    /// <summary>
    /// 由实例类型决定，进程内不变
    /// </summary>
    public GameRuntimeKind Kind => _provider.Kind;

    /// <summary>
    /// 当前运行环境的存储字段。任务线程和截图调度线程都会读取，只在 UI 线程上写入
    /// </summary>
    private volatile GameRuntime? _current;

    /// <summary>
    /// 当前运行环境。截图器未启动时为 null。
    /// 进程级对象每次使用时读取，不要缓存；运行期对象使用构造时拿到的运行环境，不读取这里
    /// </summary>
    public GameRuntime? Current
    {
        get => _current;
        private set => _current = value;
    }

    /// <summary>
    /// 截图器是否已经启动（存在当前运行环境）
    /// </summary>
    public bool IsRunning => Current is not null;

    /// <summary>
    /// 正在获取运行环境（找窗、启动游戏、等待网页版登录与排队）。只在 UI 线程上变化
    /// </summary>
    public bool IsStarting { get; private set; }

    /// <summary>Reserve runtime-start admission on the UI thread after all current startup/stop work finishes.</summary>
    internal bool TryReserveRestart()
    {
        Application.Current.Dispatcher.VerifyAccess();
        if (_restartReserved || IsStarting || !_stopTask.IsCompleted || _startLock.CurrentCount == 0) return false;
        _restartReserved = true;
        return true;
    }

    /// <summary>Release only a failed restart attempt; a successful launch retains ownership until process exit.</summary>
    internal void ReleaseRestartReservation()
    {
        Application.Current.Dispatcher.VerifyAccess();
        _restartReserved = false;
    }

    /// <summary>
    /// <see cref="IsStarting"/> 变化后在 UI 线程上触发
    /// </summary>
    public event EventHandler? StartingChanged;

    /// <summary>
    /// 绑定完成后在 UI 线程上触发
    /// </summary>
    public event EventHandler? Started;

    /// <summary>
    /// 解绑完成后在 UI 线程上触发
    /// </summary>
    public event EventHandler? Stopped;

    /// <summary>
    /// 获取运行环境并启动截图器，返回绑定的运行环境；不能启动时返回 null。已在运行时直接返回当前运行环境。
    /// 停止请求会等待本次启动完成后再解绑，获取期间收到停止请求时，获取完成后不再绑定（网页版可关闭宿主窗口来结束等待）。
    /// 绑定过程中抛出的异常（例如分辨率不合规）会在回滚后继续向上抛出，与改造前一致
    /// </summary>
    public Task<GameRuntime?> StartAsync(CancellationToken ct = default)
    {
        var stopVersion = Interlocked.Read(ref _stopVersion);
        var uiDispatcher = Application.Current.Dispatcher;
        return uiDispatcher.CheckAccess()
            ? StartCoreAsync(ct, stopVersion)
            : uiDispatcher.InvokeAsync(() => StartCoreAsync(ct, stopVersion)).Task.Unwrap();
    }

    /// <summary>Explicit automated DesktopDc startup owns task admission through prior cleanup and runtime binding.</summary>
    internal Task<GameRuntime?> StartDesktopAutomationAsync(CancellationToken ct)
    {
        var stopVersion = Interlocked.Read(ref _stopVersion);
        var dispatcher = Application.Current.Dispatcher;
        Task<GameRuntime?> Start() => WithStartupTaskGateAsync(TaskControl.TaskSemaphore,
            token => StartCoreAsync(token, stopVersion, desktopStartupFocus: true), ct);
        return dispatcher.CheckAccess() ? Start() : dispatcher.InvokeAsync(Start).Task.Unwrap();
    }

    /// <summary>Never wait behind an active task or abandon startup cleanup when cancellation is requested.</summary>
    internal static async Task<T> WithStartupTaskGateAsync<T>(SemaphoreSlim gate,
        Func<CancellationToken, Task<T>> start, CancellationToken ct)
    {
        if (!await gate.WaitAsync(0, ct))
            throw new InvalidOperationException("A standalone task is already active.");
        try
        {
            ct.ThrowIfCancellationRequested();
            return await start(ct);
        }
        finally { gate.Release(); }
    }

    /// <summary>
    /// 用外部构造好的运行环境启动截图器，目前只用于手动选窗。在 UI 线程上调用。
    /// 无法启动时释放传入的运行环境并返回 false
    /// </summary>
    public bool Start(GameRuntime runtime)
    {
        ArgumentNullException.ThrowIfNull(runtime);
        Application.Current.Dispatcher.VerifyAccess();

        if (_restartReserved || IsRunning || !_stopTask.IsCompleted || _startLock.CurrentCount == 0 || !CheckTriggerInterval())
        {
            runtime.Input.Dispose();
            runtime.Dispose();
            return false;
        }

        Bind(runtime);
        return true;
    }

    /// <summary>
    /// 等待启动完成后停止截图器：取消任务、停止调度、释放运行环境。不关闭游戏
    /// </summary>
    public Task StopAsync()
    {
        Interlocked.Increment(ref _stopVersion);
        var uiDispatcher = Application.Current.Dispatcher;
        return uiDispatcher.CheckAccess()
            ? QueueStopAsync()
            : uiDispatcher.InvokeAsync(QueueStopAsync).Task.Unwrap();
    }

    private Task QueueStopAsync()
    {
        // 同一轮停止只排队一次；后续启动必须等这次解绑完成。
        if (_stopTask.IsCompleted)
        {
            _stopTask = StopCoreAsync();
        }

        return _stopTask;
    }

    private async Task StopCoreAsync()
    {
        await _startLock.WaitAsync();
        try
        {
            StopCurrent();
        }
        finally
        {
            _startLock.Release();
        }
    }

    private void StopCurrent()
    {
        var runtime = Current;
        if (runtime is null)
        {
            return;
        }

        Current = null;
        // 先通知持有这个运行环境的对象：之后的截图和等待按正常中断处理
        runtime.SignalStopping();
        _taskStopService.StopAll(TaskStopReason.RuntimeStopped); // 取消依赖当前运行环境的任务
        _dispatcher.Stop();
        ReleaseInputBeforeDetach();
        InputHub.Attach(new Win32InputBackend(IntPtr.Zero));
        // 绘制内容和地图点位状态都以这次运行环境为坐标，解绑后不再有意义
        runtime.MaskWindowDrawingBoard.ClearAll();
        runtime.MaskWindowMapState.Reset();
        runtime.Dispose();
        Stopped?.Invoke(this, EventArgs.Empty);
    }

    /// <summary>
    /// 关闭游戏。截图器会在下一次调度时发现游戏已退出并自动停止
    /// </summary>
    public void CloseGame() => _provider.CloseGame(Current);

    private async Task<GameRuntime?> StartCoreAsync(CancellationToken ct, long stopVersion, bool desktopStartupFocus = false)
    {
        await _stopTask.WaitAsync(ct);
        await _startLock.WaitAsync(ct);
        try
        {
            // Recheck after both waits: a restart can reserve admission while this call is queued.
            if (_restartReserved) return null;
            // 停止请求之前排队的启动不能在解绑后重新启动截图器。
            if (stopVersion != Interlocked.Read(ref _stopVersion))
            {
                return null;
            }

            if (Current is { } current)
            {
                if (desktopStartupFocus)
                    throw new InvalidOperationException("desktop_capture_start_requires_stopped_runtime");
                return current;
            }

            if (!CheckTriggerInterval())
            {
                return null;
            }

            GameRuntime? runtime;
            SetStarting(true);
            try
            {
                // Only the explicit task-gated entry reaches this intent, after stop cleanup and the start lock.
                runtime = desktopStartupFocus
                    ? await (_provider as Win32RuntimeProvider
                        ?? throw new InvalidOperationException("DesktopDc startup requires the Win32 provider."))
                        .AcquireForDesktopAutomationAsync(ct)
                    : await _provider.AcquireAsync(ct);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                _logger.LogInformation("Capture service startup canceled");
                return null;
            }
            finally
            {
                SetStarting(false);
            }

            if (runtime is null)
            {
                return null;
            }

            // 获取期间收到了停止请求：不再绑定，等价于"绑定后立即解绑"，但不会闪一下遮罩、也不会加载触发器
            if (stopVersion != Interlocked.Read(ref _stopVersion) || (desktopStartupFocus && ct.IsCancellationRequested))
            {
                runtime.Input.Dispose();
                runtime.Dispose();
                return null;
            }

            Bind(runtime);
            return runtime;
        }
        finally
        {
            _startLock.Release();
        }
    }

    private void Bind(GameRuntime runtime)
    {
        var inputAttached = false;
        try
        {
            InputHub.Attach(runtime.Input);
            inputAttached = true;
            _dispatcher.Start(runtime, _configService.Get().TriggerInterval);
        }
        catch
        {
            _dispatcher.Stop();
            if (inputAttached)
            {
                ReleaseInputBeforeDetach();
                InputHub.Attach(new Win32InputBackend(IntPtr.Zero));
            }
            else
            {
                runtime.Input.Dispose();
            }

            runtime.Dispose();
            throw;
        }

        Current = runtime;
        _logger.LogDebug("Game runtime bound: {Kind}, window handle {Handle}", runtime.Kind, runtime.Window.Handle);
        Started?.Invoke(this, EventArgs.Empty);
    }

    private void SetStarting(bool value)
    {
        if (IsStarting == value)
        {
            return;
        }

        IsStarting = value;
        StartingChanged?.Invoke(this, EventArgs.Empty);
    }

    private void ReleaseInputBeforeDetach()
    {
        try
        {
            InputHub.ReleaseAll();
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Failed to release keys while unbinding the runtime");
        }
    }

    private bool CheckTriggerInterval()
    {
        if (BetterGenshinImpact.Helpers.CommandLineOptions.Instance.AutomationMode
            && _configService.Get().TriggerInterval <= 0)
            throw new InvalidOperationException("Capture trigger interval must be positive.");
        if (_configService.Get().TriggerInterval > 0)
        {
            return true;
        }

        ThemedMessageBox.Error(I18nService.Instance.Translate("触发器触发频率必须大于0"));
        return false;
    }

    /// <summary>
    /// 截图调度发现游戏已退出或截图器停止
    /// </summary>
    private async void OnRuntimeLost(object? sender, EventArgs e)
    {
        try
        {
            await StopAsync();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to stop the game runtime");
        }
    }
}
