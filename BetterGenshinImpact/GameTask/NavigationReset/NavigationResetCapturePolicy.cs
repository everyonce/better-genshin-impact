using System;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using BetterGenshinImpact.GameTask.Model.Area;
using OpenCvSharp;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>Explicit reset capture experiment; teleport stays shared and isolation begins only before orientation.</summary>
internal static class NavigationResetCapturePolicy
{
    /// <summary>Legacy timer/task sharing remains the default for the entire reset.</summary>
    internal const string Shared = "shared";
    /// <summary>After teleport, TaskRunner pauses its bound timer through native disposal and input cleanup.</summary>
    internal const string TaskOwnedTimer = "task_owned_timer";
    /// <summary>Match the native baseline's supported unscaled chat-template geometry.</summary>
    internal const int MaximumChatWidth = 1920, MaximumChatHeight = 1080;

    /// <summary>Reject unknown or null explicit selections before acquiring any reset resources.</summary>
    internal static bool IsSupported(string? policy) => policy is Shared or TaskOwnedTimer;

    /// <summary>Inspect chat on the exact admitted native pixels before world recognition after isolation.</summary>
    internal static AgentWorldEvidence RecognizeWorld(Mat source, bool isolated) =>
        RecognizeWorld(source, isolated, RecognizeChat, AgentWorldRecognizer.Recognize, ChatUiHotkeyGuard.UpdateVisualState);

    /// <summary>CPU-test seam proves same-frame ordering without global application initialization.</summary>
    internal static AgentWorldEvidence RecognizeWorld(Mat source, bool isolated,
        Func<Mat, ChatUiDetectionResult> recognizeChat, Func<Mat, AgentWorldEvidence> recognizeWorld,
        Action<ChatUiDetectionResult> updateChat)
    {
        if (isolated)
        {
            if (source.Width <= 0 || source.Height <= 0 || source.Width > MaximumChatWidth || source.Height > MaximumChatHeight)
                throw new InvalidOperationException($"unsupported_chat_frame_geometry: {source.Width}x{source.Height}");
            var chat = recognizeChat(source);
            updateChat(chat);
            // Global debounce is not input authority: reject direct open or unrecognized enum evidence immediately.
            if (chat.State != ChatUiState.Closed) throw new InvalidOperationException($"chat_not_closed: {chat.State}");
        }
        return recognizeWorld(source);
    }

    /// <summary>The temporary header borrows caller pixels; no clone, resize, second capture or ownership transfer occurs.</summary>
    private static ChatUiDetectionResult RecognizeChat(Mat source)
    {
        using var region = new ImageRegion(new Mat(source, new Rect(0, 0, source.Width, source.Height)), 0, 0);
        return Bv.DetectChatUi(region);
    }
}
