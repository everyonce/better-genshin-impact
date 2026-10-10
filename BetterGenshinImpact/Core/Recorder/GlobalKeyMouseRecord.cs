using BetterGenshinImpact.Core.Monitor;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Common;
using BetterGenshinImpact.GameTask.Common.Element.Assets;
using BetterGenshinImpact.Model;
using BetterGenshinImpact.Service.I18n;
using BetterGenshinImpact.View.Windows;
using Gma.System.MouseKeyHook;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Windows.Forms;
using Wpf.Ui.Violeta.Controls;

namespace BetterGenshinImpact.Core.Recorder;

public class GlobalKeyMouseRecord : Singleton<GlobalKeyMouseRecord>
{
    private readonly ILogger<GlobalKeyMouseRecord> _logger = App.GetLogger<GlobalKeyMouseRecord>();

    private KeyMouseRecorder? _recorder;

    private readonly Dictionary<Keys, bool> _keyDownState = [];

    private IDisposable? _relativeMouseSubscription;

    private readonly System.Timers.Timer _timer = new();

    private bool _isInMainUi = false; // 是否在主界面

    public KeyMouseRecorderStatus Status { get; set; } = KeyMouseRecorderStatus.Stop;

    public GlobalKeyMouseRecord()
    {
        _timer.Elapsed += Tick;
        _timer.Interval = 50; // ms
    }

    public async Task<bool> StartRecord(
        RelativeMouseInputType inputType = RelativeMouseInputType.DirectInput)
    {
        if (!TaskContext.Instance().IsInitialized)
        {
            Toast.Warning(I18nService.Instance.Translate("请先在启动页，启动截图器再使用本功能"));
            return false;
        }

        if (Status != KeyMouseRecorderStatus.Stop)
        {
            Toast.Warning(I18nService.Instance.Translate("已经在录制状态，请不要重复启动录制功能"));
            return false;
        }

        Status = KeyMouseRecorderStatus.Start;
        var taskTriggerStopped = false;
        try
        {
            SystemControl.ActivateWindow();

            _logger.LogInformation("Recording: {Text}", "Real-time tasks have been paused");
            _logger.LogInformation("When recording switches between the main screen (mouse stays centered) and other screens (mouse can move freely, such as the map), take your hand off the mouse and wait for the mode-switch log");

            for (var i = 3; i >= 1; i--)
            {
                _logger.LogInformation("Recording starts in {Sec} seconds...", i);
                await Task.Delay(1000);
            }

            TaskTriggerDispatcher.Instance().StopTimer();
            taskTriggerStopped = true;

            _recorder = new KeyMouseRecorder();
            var monitorFactory = App.GetService<IRelativeMouseInputMonitorFactory>()
                                 ?? throw new InvalidOperationException("The relative mouse capture factory is not registered");
            _relativeMouseSubscription = monitorFactory
                .Get(inputType)
                .Subscribe(RelativeMouseMoved);

            _timer.Start();
            Status = KeyMouseRecorderStatus.Recording;

            _logger.LogInformation("Recording started; relative mouse capture method: {InputType}", inputType);
            return true;
        }
        catch (Exception ex)
        {
            _timer.Stop();
            try
            {
                _relativeMouseSubscription?.Dispose();
            }
            catch (Exception disposeException)
            {
                _logger.LogWarning(disposeException, "Failed to clean up the relative mouse capture subscription");
            }
            _relativeMouseSubscription = null;
            _recorder = null;

            if (taskTriggerStopped)
            {
                TaskTriggerDispatcher.Instance().StartTimer();
            }

            Status = KeyMouseRecorderStatus.Stop;
            _logger.LogError(ex, "Failed to start keyboard and mouse recording; relative mouse capture method: {InputType}", inputType);
            await ThemedMessageBox.ErrorAsync(
                string.Format(I18nService.Instance.Translate("启动键鼠录制失败：{0}"), ex.Message),
                I18nService.Instance.Translate("键鼠录制启动失败"));
            return false;
        }
    }

    public string StopRecord()
    {
        if (Status != KeyMouseRecorderStatus.Recording)
        {
            throw new InvalidOperationException("Recording is not active, so it cannot be stopped");
        }

        _timer.Stop();

        var recorder = _recorder;
        _recorder = null;
        var relativeMouseSubscription = _relativeMouseSubscription;
        _relativeMouseSubscription = null;

        try
        {
            relativeMouseSubscription?.Dispose();
            return recorder?.ToJsonMacro() ?? string.Empty;
        }
        finally
        {
            _logger.LogInformation("Recording: {Text}", "Recording ended");
            TaskTriggerDispatcher.Instance().StartTimer();
            Status = KeyMouseRecorderStatus.Stop;
        }
    }

    public void Tick(object? sender, EventArgs e)
    {
        var ra = TaskControl.CaptureToRectArea();
        var iconRa = ra.Find(ElementRecognition.Get("FriendChat", ra));
        var exist = iconRa.IsExist();
        if (exist != _isInMainUi)
        {
            _logger.LogInformation("Recording: {Text}", exist ? "Entered the main screen; capturing relative mouse movement" : "Left the main screen; capturing absolute mouse movement");
        }
        _isInMainUi = exist;
        iconRa.Dispose();
        ra.Dispose();
    }

    public void GlobalHookKeyDown(KeyEventArgs e, DateTime time)
    {
        // 排除热键
        if (e.KeyCode.ToString() == TaskContext.Instance().Config.HotKeyConfig.KeyMouseMacroRecordHotkey)
        {
            return;
        }

        if (_keyDownState.TryGetValue(e.KeyCode, out var v))
        {
            if (v)
            {
                return; // 处于按下状态的不再记录
            }
            else
            {
                _keyDownState[e.KeyCode] = true;
            }
        }
        else
        {
            _keyDownState.Add(e.KeyCode, true);
        }
        // Debug.WriteLine($"KeyDown: {e.KeyCode}");
        _recorder?.KeyDown(e, time);
    }

    public void GlobalHookKeyUp(KeyEventArgs e, DateTime time)
    {
        if (e.KeyCode.ToString() == TaskContext.Instance().Config.HotKeyConfig.Test1Hotkey)
        {
            return;
        }

        if (_keyDownState.TryGetValue(e.KeyCode, out bool state) && state)
        {
            // Debug.WriteLine($"KeyUp: {e.KeyCode}");
            _keyDownState[e.KeyCode] = false;
            _recorder?.KeyUp(e, time);
        }
    }

    public void GlobalHookMouseDown(MouseEventExtArgs e, DateTime time)
    {
        // Debug.WriteLine($"MouseDown: {e.Button}");
        _recorder?.MouseDown(e, time);
    }

    public void GlobalHookMouseUp(MouseEventExtArgs e, DateTime time)
    {
        // Debug.WriteLine($"MouseUp: {e.Button}");
        _recorder?.MouseUp(e, time);
    }

    public void GlobalHookMouseMoveTo(MouseEventExtArgs e, DateTime time)
    {
        if (_isInMainUi)
        {
            return;
        }
        // Debug.WriteLine($"MouseMove: {e.X}, {e.Y}");
        _recorder?.MouseMoveTo(e, time);
    }
    
    public void GlobalHookMouseWheel(MouseEventExtArgs e, DateTime time)
    {
        // Debug.WriteLine($"MouseWheel: {e.Delta}");
        _recorder?.MouseWheel(e, time);
    }

    private void RelativeMouseMoved(object? sender, RelativeMouseMoveEventArgs e)
    {
        if (e is { DeltaX: 0, DeltaY: 0 } || !_isInMainUi)
        {
            return;
        }
        // Debug.WriteLine($"MouseMoveBy: {e.DeltaX}, {e.DeltaY}");
        _recorder?.MouseMoveBy(e);
    }
}

public enum KeyMouseRecorderStatus
{
    Start,
    Recording,
    Stop
}
