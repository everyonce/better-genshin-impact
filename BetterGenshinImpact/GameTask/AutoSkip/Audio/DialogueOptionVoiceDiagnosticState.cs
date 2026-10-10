using CommunityToolkit.Mvvm.ComponentModel;
using System;
using System.Globalization;
using System.Threading;
using System.Windows;

namespace BetterGenshinImpact.GameTask.AutoSkip.Audio;

public partial class DialogueOptionVoiceDiagnosticState : ObservableObject
{
    private int _recordingRequested;

    [ObservableProperty]
    private double _probability;

    [ObservableProperty]
    private string _probabilityText = "--";

    [ObservableProperty]
    private string _rmsText = "--";

    [ObservableProperty]
    private string _peakText = "--";

    [ObservableProperty]
    private string _statusText = "Diagnostics are disabled";

    [ObservableProperty]
    private string _verdictText = "—";

    [ObservableProperty]
    private string _decisionText = "Not waiting for an option";

    public string ThresholdText { get; } =
        $"Speech start {DialogueOptionVoiceThresholds.SpeechProbability:F2}  ·  possible speech {DialogueOptionVoiceThresholds.MaybeSpeechProbability:F2}  ·  " +
        $"speech confirmation {DialogueOptionVoiceThresholds.SpeechRiseMilliseconds}ms  ·  end silence {DialogueOptionVoiceThresholds.SilenceMilliseconds / 1000d:F1}s";

    [ObservableProperty]
    private string _recordingButtonText = "开始录制";

    [ObservableProperty]
    private string _recordingStatusText = "Recordings will be saved to log\\VadDiagnostics";

    internal bool IsRecordingRequested => Volatile.Read(ref _recordingRequested) != 0;

    public void ToggleRecording()
    {
        var requested = IsRecordingRequested;
        Interlocked.Exchange(ref _recordingRequested, requested ? 0 : 1);
        RecordingButtonText = requested ? "开始录制" : "停止并保存";
        RecordingStatusText = requested ? "Stopping recording…" : "Recording will start after an audio frame arrives…";
    }

    internal void SetRecordingStarted(string filePath)
    {
        Dispatch(() =>
        {
            RecordingButtonText = "停止并保存";
            RecordingStatusText = $"Recording: {filePath}";
        });
    }

    internal void SetRecordingStopped(string? filePath)
    {
        Interlocked.Exchange(ref _recordingRequested, 0);
        Dispatch(() =>
        {
            RecordingButtonText = "开始录制";
            RecordingStatusText = filePath == null
                ? "Recordings will be saved to log\\VadDiagnostics"
                : $"Saved: {filePath}";
        });
    }

    internal void SetDisabled()
    {
        Dispatch(() =>
        {
            Probability = 0;
            ProbabilityText = "--";
            RmsText = "--";
            PeakText = "--";
            StatusText = "Diagnostics are disabled";
            VerdictText = "—";
            DecisionText = "Not waiting for an option";
        });
    }

    internal void SetWaiting(string statusText, string decisionText)
    {
        Dispatch(() =>
        {
            Probability = 0;
            ProbabilityText = "--";
            RmsText = "--";
            PeakText = "--";
            StatusText = statusText;
            VerdictText = "—";
            DecisionText = decisionText;
        });
    }

    internal void SetSample(DialogueOptionVoiceDetector.VoiceDetectionResult result, string verdictText, string decisionText)
    {
        Dispatch(() =>
        {
            Probability = Math.Clamp(result.Probability, 0f, 1f);
            ProbabilityText = result.Probability.ToString("F6", CultureInfo.InvariantCulture);
            RmsText = result.Rms.ToString("F5", CultureInfo.InvariantCulture);
            PeakText = result.Peak.ToString("F5", CultureInfo.InvariantCulture);
            StatusText = "Monitoring continuously";
            VerdictText = verdictText;
            DecisionText = decisionText;
        });
    }

    private static void Dispatch(Action update)
    {
        var dispatcher = Application.Current?.Dispatcher;
        if (dispatcher == null || dispatcher.CheckAccess())
        {
            update();
            return;
        }

        dispatcher.BeginInvoke(update);
    }
}
