using System;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using BetterGenshinImpact.GameTask.Model.Area;
using OpenCvSharp;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Fixed baseline capture experiments; neither policy claims exclusive ownership of every capture consumer.</summary>
internal static class NavigationBaselineCapturePolicy
{
    /// <summary>Existing timer/task capture sharing remains the default.</summary>
    internal const string Shared = "shared";
    /// <summary>TaskRunner drains and pauses only its bound runtime's timer capture through task cleanup.</summary>
    internal const string TaskOwnedTimer = "task_owned_timer";
    /// <summary>Bv's capped template geometry cannot directly inspect larger raw frames in this opt-in experiment.</summary>
    internal const int MaximumChatWidth = 1920, MaximumChatHeight = 1080;

    /// <summary>Reject arbitrary names before task ownership or native work begins.</summary>
    internal static bool IsSupported(string? policy) => policy is Shared or TaskOwnedTimer;

    /// <summary>Reuse the exact admitted native pixels for chat protection when timer visual updates are paused.</summary>
    internal static AgentWorldEvidence RecognizeWorld(Mat source, string policy, Action<ChatUiDetectionResult> recordChat) =>
        RecognizeWorld(source, policy, RecognizeChat, AgentWorldRecognizer.Recognize, recordChat);

    /// <summary>Inject recognition only for CPU tests of same-frame ordering and fail-closed chat behavior.</summary>
    internal static AgentWorldEvidence RecognizeWorld(Mat source, string policy,
        Func<Mat, ChatUiDetectionResult> recognizeChat, Func<Mat, AgentWorldEvidence> recognizeWorld,
        Action<ChatUiDetectionResult> recordChat)
    {
        if (!IsSupported(policy)) throw new ArgumentException("unsupported_capture_policy", nameof(policy));
        if (policy == TaskOwnedTimer)
        {
            // Shared capture retains its original supported geometry; do not resize or calibrate this experimental chat path.
            if (source.Width <= 0 || source.Height <= 0 || source.Width > MaximumChatWidth || source.Height > MaximumChatHeight)
                throw new InvalidOperationException($"unsupported_chat_frame_geometry: {source.Width}x{source.Height}");
            var chat = recognizeChat(source);
            ChatUiHotkeyGuard.UpdateVisualState(chat);
            recordChat(chat);
            // Direct open-chat evidence terminates this task immediately; the global guard's two-frame debounce is not input authority.
            if (chat.State != ChatUiState.Closed) throw new InvalidOperationException($"chat_not_closed: {chat.State}");
        }
        return recognizeWorld(source);
    }

    /// <summary>The temporary header owns no caller pixels; Bv inspects the full native frame without another capture.</summary>
    private static ChatUiDetectionResult RecognizeChat(Mat source)
    {
        using var region = new ImageRegion(new Mat(source, new Rect(0, 0, source.Width, source.Height)), 0, 0);
        return Bv.DetectChatUi(region);
    }
}
