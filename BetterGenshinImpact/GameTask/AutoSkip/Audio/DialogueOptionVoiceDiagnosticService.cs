using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Service.Interface;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask.AutoSkip.Audio;

internal sealed class DialogueOptionVoiceDiagnosticService : BackgroundService
{
    private static readonly TimeSpan UpdateInterval = TimeSpan.FromMilliseconds(32);
    private static readonly TimeSpan DisabledPollInterval = TimeSpan.FromMilliseconds(200);
    private static readonly TimeSpan DetectorRetryDelay = TimeSpan.FromSeconds(5);

    private readonly AutoSkipConfig _config;
    private readonly DialogueOptionVoiceDiagnosticState _state;
    private readonly ILogger<DialogueOptionVoiceDiagnosticService> _logger;
    private readonly TaskTriggerDispatcher _triggers;

    /// <summary>
    /// 游戏运行环境服务。进程级服务不持有运行环境，每次查找游戏进程时读取 Current
    /// </summary>
    private readonly GameRuntimeService _runtimeService;
    private DialogueOptionVoiceDetector? _detector;
    private PcmWaveRecorder? _recorder;
    private int? _unavailableProcessId;
    private DateTime _detectorRetryAfter = DateTime.MinValue;

    public DialogueOptionVoiceDiagnosticService(
        IConfigService configService,
        DialogueOptionVoiceDiagnosticState state,
        ILogger<DialogueOptionVoiceDiagnosticService> logger,
        TaskTriggerDispatcher triggers,
        GameRuntimeService runtimeService)
    {
        _config = configService.Get().AutoSkipConfig;
        _state = state;
        _logger = logger;
        _triggers = triggers;
        _runtimeService = runtimeService;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                if (!_config.DialogueOptionVoiceVadDiagnosticEnabled)
                {
                    StopRecording();
                    ReleaseDetector();
                    _state.SetDisabled();
                    await Task.Delay(DisabledPollInterval, stoppingToken);
                    continue;
                }

                try
                {
                    if (!_state.IsRecordingRequested)
                    {
                        StopRecording();
                    }

                    var detector = GetDetector();
                    if (detector == null)
                    {
                        await Task.Delay(DisabledPollInterval, stoppingToken);
                        continue;
                    }

                    UpdateRecordingState();
                    var recordedSamples = _recorder == null ? null : new List<float>();
                    var result = detector.Update(recordedSamples);
                    if (recordedSamples is { Count: > 0 })
                    {
                        _recorder?.Write(recordedSamples);
                    }

                    var decisionText = BuildDecisionText();
                    if (result == null)
                    {
                        _state.SetWaiting("Waiting for a complete audio frame", decisionText);
                    }
                    else
                    {
                        var probability = result.Value.Probability;
                        var verdict = probability >= DialogueOptionVoiceThresholds.SpeechProbability
                            ? "说话"
                            : probability > DialogueOptionVoiceThresholds.MaybeSpeechProbability
                                ? "疑似语音"
                                : "静音";
                        _state.SetSample(result.Value, verdict, decisionText);
                    }
                }
                catch (Exception e)
                {
                    _logger.LogWarning(e, "Auto-dialogue: continuous Silero VAD diagnostics failed; retrying later");
                    var processId = _detector?.TargetProcessId;
                    StopRecording();
                    ReleaseDetector();
                    _unavailableProcessId = processId;
                    _detectorRetryAfter = DateTime.Now.Add(DetectorRetryDelay);
                    _state.SetWaiting("Detection failed; retrying later", BuildDecisionText());
                }

                await Task.Delay(UpdateInterval, stoppingToken);
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
        }
        finally
        {
            StopRecording();
            ReleaseDetector();
            _state.SetDisabled();
        }
    }

    private DialogueOptionVoiceDetector? GetDetector()
    {
        using var process = FindGameProcess();
        if (process == null || process.Id <= 0)
        {
            ReleaseDetector();
            _state.SetWaiting("Game process not found", BuildDecisionText());
            return null;
        }

        var processId = process.Id;
        if (_detector?.TargetProcessId == processId)
        {
            return _detector;
        }

        ReleaseDetector();
        if (_unavailableProcessId == processId && DateTime.Now < _detectorRetryAfter)
        {
            _state.SetWaiting("Detector initialization failed; waiting to retry", BuildDecisionText());
            return null;
        }

        try
        {
            _detector = DialogueOptionVoiceDetector.Create(processId);
            _unavailableProcessId = null;
            _detectorRetryAfter = DateTime.MinValue;
            _state.SetWaiting("Waiting for a complete audio frame", BuildDecisionText());
            _logger.LogDebug("Auto-dialogue: continuous Silero VAD diagnostics sample source is game process audio, PID={ProcessId}", processId);
            return _detector;
        }
        catch (Exception e)
        {
            _unavailableProcessId = processId;
            _detectorRetryAfter = DateTime.Now.Add(DetectorRetryDelay);
            _state.SetWaiting("Detector initialization failed; waiting to retry", BuildDecisionText());
            _logger.LogWarning(e, "Auto-dialogue: failed to initialize continuous Silero VAD diagnostics; retrying later");
            return null;
        }
    }

    private void UpdateRecordingState()
    {
        if (_state.IsRecordingRequested)
        {
            if (_recorder != null)
            {
                return;
            }

            var directory = Global.Absolute(Path.Combine("log", "VadDiagnostics"));
            var filePath = Path.Combine(directory, $"silero-vad-{DateTime.Now:yyyyMMdd-HHmmss-fff}.wav");
            _recorder = new PcmWaveRecorder(filePath);
            _state.SetRecordingStarted(filePath);
            return;
        }

        StopRecording();
    }

    private void StopRecording()
    {
        if (_recorder == null)
        {
            if (_state.IsRecordingRequested)
            {
                _state.SetRecordingStopped(null);
            }

            return;
        }

        var filePath = _recorder.FilePath;
        _recorder.Dispose();
        _recorder = null;
        _state.SetRecordingStopped(filePath);
    }

    private string BuildDecisionText()
    {
        var trigger = _triggers.GetTrigger<AutoSkipTrigger>();
        if (trigger == null || !trigger.VoiceWaiter.TryGetProgress(out var progress))
        {
            return "Not waiting for an option";
        }

        if (progress.IsFallback)
        {
            return "Waiting for option · fixed-delay fallback";
        }

        if (progress.HeardSpeech)
        {
            return $"Waiting for option · speech confirmed · silence {progress.QuietMilliseconds / 1000d:F1}s / {progress.RequiredQuietMilliseconds / 1000d:F1}s";
        }

        return progress.InStartGrace
            ? $"Waiting for option · speech not started · grace period {progress.WaitingMilliseconds / 1000d:F1}s / {DialogueOptionAudioWaiter.SpeechStartGraceMilliseconds / 1000d:F1}s"
            : $"Waiting for option · speech not started · silence {progress.QuietMilliseconds / 1000d:F1}s / {progress.RequiredQuietMilliseconds / 1000d:F1}s";
    }

    /// <summary>
    /// 优先取当前运行环境的游戏窗口所在进程；截图器未启动时按进程名查找游戏窗口
    /// </summary>
    private Process? FindGameProcess()
    {
        var configuredHandle = _runtimeService.Current?.Window.Handle ?? IntPtr.Zero;
        if (configuredHandle != IntPtr.Zero)
        {
            var configuredProcess = SystemControl.GetProcessByHandle(configuredHandle);
            if (configuredProcess is { Id: > 0 })
            {
                return configuredProcess;
            }

            configuredProcess?.Dispose();
        }

        var detectedHandle = SystemControl.FindGenshinImpactHandle();
        return detectedHandle == IntPtr.Zero
            ? null
            : SystemControl.GetProcessByHandle(detectedHandle);
    }

    private void ReleaseDetector()
    {
        _detector?.Dispose();
        _detector = null;
    }
}
