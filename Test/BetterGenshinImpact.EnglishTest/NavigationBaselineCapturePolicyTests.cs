using System.Diagnostics;
using System.Text;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.GameTask.SoloTask.Execution;
using BetterGenshinImpact.Service.ExternalControl;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>CPU-only policy, same-frame chat ordering and scoped emergency-cancel regressions; no live capture/input.</summary>
public sealed class NavigationBaselineCapturePolicyTests
{
    /// <summary>Synthetic detector output, not an assertion about real screenshot recognition.</summary>
    private static ChatUiDetectionResult Chat(ChatUiState state) => new(state, true, true, true, 2, true);

    /// <summary>Legacy/default capture does not run or update chat recognition on the control path.</summary>
    [Fact]
    public void SharedPathDoesNotRunAdditionalRecognition()
    {
        using var frame = new Mat(1, 1, MatType.CV_8UC3, Scalar.All(5));
        var calls = 0;
        var world = NavigationBaselineCapturePolicy.RecognizeWorld(frame, NavigationBaselineCapturePolicy.Shared,
            _ => throw new Exception("shared must not inspect chat"), source =>
            { Assert.Same(frame, source); calls++; return AgentWorldEvidence.WorldHud; },
            _ => throw new Exception("shared must not record chat"));
        Assert.Equal(AgentWorldEvidence.WorldHud, world); Assert.Equal(1, calls);
    }

    /// <summary>One open-chat observation fails immediately, even before the global guard's two-frame debounce completes.</summary>
    [Theory]
    [InlineData(ChatUiState.PanelOpen)]
    [InlineData(ChatUiState.InputOpen)]
    [InlineData((ChatUiState)99)]
    public void OpenChatTerminatesBeforeWorldRecognition(ChatUiState state)
    {
        ChatUiHotkeyGuard.Reset();
        try
        {
            using var frame = new Mat(1, 1, MatType.CV_8UC3, Scalar.All(5));
            var worldCalls = 0; var observed = new List<ChatUiState>();
            void Recognize() => NavigationBaselineCapturePolicy.RecognizeWorld(frame, NavigationBaselineCapturePolicy.TaskOwnedTimer,
                source => { Assert.Same(frame, source); return Chat(state); },
                _ => { worldCalls++; return AgentWorldEvidence.WorldHud; }, chat => observed.Add(chat.State));
            Assert.Throws<InvalidOperationException>(Recognize);
            Assert.False(ChatUiHotkeyGuard.ShouldBlockHotkey("ordinary"));
            Assert.Throws<InvalidOperationException>(Recognize);
            Assert.True(ChatUiHotkeyGuard.ShouldBlockHotkey("ordinary"));
            Assert.Equal(new[] { state, state }, observed); Assert.Equal(0, worldCalls);
        }
        finally { ChatUiHotkeyGuard.Reset(); }
    }

    /// <summary>Chat visual state is updated on the exact frame even when world recognition subsequently rejects it.</summary>
    [Fact]
    public void ChatUpdatePrecedesBlockedWorldOnSameOwnedPixels()
    {
        ChatUiHotkeyGuard.Reset();
        try
        {
            ChatUiHotkeyGuard.UpdateVisualState(Chat(ChatUiState.InputOpen));
            ChatUiHotkeyGuard.UpdateVisualState(Chat(ChatUiState.InputOpen));
            using var frame = new Mat(1, 1, MatType.CV_8UC3, Scalar.All(5));
            var order = new List<string>();
            for (var i = 0; i < 2; i++)
            {
                var world = NavigationBaselineCapturePolicy.RecognizeWorld(frame, NavigationBaselineCapturePolicy.TaskOwnedTimer,
                    source => { Assert.Same(frame, source); order.Add("chat"); return Chat(ChatUiState.Closed); },
                    source => { Assert.Same(frame, source); order.Add("world"); return AgentWorldEvidence.HudMissing; },
                    _ => order.Add("record"));
                Assert.Equal(AgentWorldEvidence.HudMissing, world);
            }
            Assert.Equal(new[] { "chat", "record", "world", "chat", "record", "world" }, order);
            Assert.False(ChatUiHotkeyGuard.ShouldBlockHotkey("ordinary"));
            Assert.Equal(5, frame.At<Vec3b>(0, 0).Item0);
        }
        finally { ChatUiHotkeyGuard.Reset(); }
    }

    /// <summary>Recognition failure is not treated as a closed chat or a usable world observation.</summary>
    [Fact]
    public void ChatRecognitionFailureDoesNotProceed()
    {
        using var frame = new Mat(1, 1, MatType.CV_8UC3);
        var failure = new InvalidOperationException("synthetic detector error");
        var thrown = Assert.Throws<InvalidOperationException>(() => NavigationBaselineCapturePolicy.RecognizeWorld(frame,
            NavigationBaselineCapturePolicy.TaskOwnedTimer, _ => throw failure,
            _ => throw new Exception("world must not run"), _ => throw new Exception("must not invent evidence")));
        Assert.Same(failure, thrown);
    }

    /// <summary>Reject unsupported raw chat geometry before any detector can falsely report a closed panel; shared remains unchanged.</summary>
    [Theory]
    [InlineData(1921, 10)]
    [InlineData(10, 1081)]
    [InlineData(2560, 1440)]
    public void OwnedChatRejectsLargerFramesBeforeRecognition(int width, int height)
    {
        using var frame = new Mat(height, width, MatType.CV_8UC3);
        var error = Assert.Throws<InvalidOperationException>(() => NavigationBaselineCapturePolicy.RecognizeWorld(frame,
            NavigationBaselineCapturePolicy.TaskOwnedTimer, _ => throw new Exception("chat must not run"),
            _ => throw new Exception("world must not run"), _ => throw new Exception("no evidence")));
        Assert.StartsWith("unsupported_chat_frame_geometry:", error.Message);
        Assert.Equal(AgentWorldEvidence.WorldHud, NavigationBaselineCapturePolicy.RecognizeWorld(frame,
            NavigationBaselineCapturePolicy.Shared, _ => throw new Exception("chat must not run"),
            _ => AgentWorldEvidence.WorldHud, _ => throw new Exception("no chat evidence")));
    }

    /// <summary>The current 1920x1080 native boundary is supported without resizing or replacing the source Mat.</summary>
    [Fact]
    public void OwnedChatSupportsCurrentNativeGeometryBoundary()
    {
        ChatUiHotkeyGuard.Reset();
        try
        {
            using var frame = new Mat(1080, 1920, MatType.CV_8UC3);
            var calls = 0;
            Assert.Equal(AgentWorldEvidence.WorldHud, NavigationBaselineCapturePolicy.RecognizeWorld(frame,
                NavigationBaselineCapturePolicy.TaskOwnedTimer,
                source => { Assert.Same(frame, source); calls++; return Chat(ChatUiState.Closed); },
                source => { Assert.Same(frame, source); calls++; return AgentWorldEvidence.WorldHud; }, _ => { }));
            Assert.Equal(2, calls);
        }
        finally { ChatUiHotkeyGuard.Reset(); }
    }

    /// <summary>Nested scopes preserve only cancel/stop usability through visual resets; repeated cleanup cannot revoke another scope.</summary>
    [Fact]
    public void CancellationExemptionIsScopedAndSurvivesVisualReset()
    {
        ChatUiHotkeyGuard.Reset();
        using var first = ChatUiHotkeyGuard.PreserveTaskCancellation();
        using var second = ChatUiHotkeyGuard.PreserveTaskCancellation();
        try
        {
            ChatUiHotkeyGuard.UpdateVisualState(Chat(ChatUiState.InputOpen));
            ChatUiHotkeyGuard.UpdateVisualState(Chat(ChatUiState.InputOpen));
            Assert.False(ChatUiHotkeyGuard.ShouldBlockHotkey(nameof(HotKeyConfig.CancelTaskHotkey)));
            Assert.False(ChatUiHotkeyGuard.ShouldBlockHotkey(nameof(HotKeyConfig.BgiEnabledHotkey)));
            Assert.True(ChatUiHotkeyGuard.ShouldBlockHotkey("ordinary"));
            first.Dispose(); first.Dispose();
            ChatUiHotkeyGuard.Reset();
            ChatUiHotkeyGuard.UpdateVisualState(Chat(ChatUiState.InputOpen));
            ChatUiHotkeyGuard.UpdateVisualState(Chat(ChatUiState.InputOpen));
            Assert.False(ChatUiHotkeyGuard.ShouldBlockHotkey(nameof(HotKeyConfig.CancelTaskHotkey)));
            second.Dispose();
            Assert.True(ChatUiHotkeyGuard.ShouldBlockHotkey(nameof(HotKeyConfig.CancelTaskHotkey)));
            Assert.False(ChatUiHotkeyGuard.ShouldBlockHotkey(nameof(HotKeyConfig.BgiEnabledHotkey)));
        }
        finally { ChatUiHotkeyGuard.Reset(); }
    }

    /// <summary>Only fixed navigation commands accept this selector; explicit null/unknown values never default.</summary>
    [Theory]
    [InlineData("startNavigationBaseline", null, null)]
    [InlineData("startNavigationBaseline", "\"shared\"", null)]
    [InlineData("startNavigationBaseline", "\"task_owned_timer\"", null)]
    [InlineData("startNavigationBaseline", "null", "invalid_command_parameters")]
    [InlineData("startNavigationBaseline", "\"exclusive\"", "invalid_command_parameters")]
    [InlineData("status", "\"shared\"", "unexpected_command_parameters")]
    [InlineData("startNavigationReset", "null", "invalid_command_parameters")]
    public void WireCapturePolicyIsExact(string command, string? literal, string? rejection)
    {
        var json = "{\"version\":1,\"requestId\":\"" + Guid.NewGuid() + "\",\"createdAtUnixMs\":"
            + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + ",\"command\":\"" + command
            + "\",\"targetProcessId\":20,\"targetWindowsSessionId\":3,\"targetNonce\":\"fixed\""
            + (literal is null ? "" : ",\"capturePolicy\":" + literal) + "}";
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes(json), out var request));
        Assert.Equal(rejection, ExternalControlProtocol.ValidateRequest(request!, DateTimeOffset.UtcNow));
        var serialized = JsonSerializer.SerializeToElement(request, ExternalControlProtocol.JsonOptions);
        Assert.False(serialized.TryGetProperty("CapturePolicy", out _));
        Assert.Equal(request!.CapturePolicy is not null, serialized.TryGetProperty("capturePolicy", out _));
        if (literal == "\"task_owned_timer\"")
        {
            Assert.NotEqual(ExternalControlProtocol.Fingerprint(request!),
                ExternalControlProtocol.Fingerprint(request! with { CapturePolicy = "shared" }));
            Assert.Null(ExternalControlProtocol.ValidateRequest(request! with { TimingContract = "v2" }, DateTimeOffset.UtcNow));
        }
    }

    /// <summary>Failure before native creation still records the admitted policy, independently of v1/v2.</summary>
    [Theory]
    [InlineData("v1")]
    [InlineData("v2")]
    public async Task EarlyOwnerFailureRetainsSelectedPolicy(string timing)
    {
        var owner = new NavigationBaselineTaskOwner();
        Assert.True(owner.TryStart(10, 3, (_, _, _) => Task.FromResult((new SoloTaskRunResult
            { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = "synthetic drain failure" }, (NavigationBaselineRunResult?)null)),
            timingContract: timing, capturePolicy: NavigationBaselineCapturePolicy.TaskOwnedTimer));
        var wait = Stopwatch.StartNew();
        while (owner.Running && wait.Elapsed < TimeSpan.FromSeconds(5)) await Task.Delay(1);
        Assert.False(owner.Running);
        var status = owner.Snapshot(true);
        Assert.Equal("failed", status.State); Assert.Equal("synthetic drain failure", status.Error);
        Assert.Equal("task_owned_timer", status.CapturePolicy); Assert.Equal(status.CapturePolicy, status.Result!.CapturePolicy);
        Assert.Equal(timing, status.Result.TimingContract);
        Assert.Equal(new[] { "shared", "task_owned_timer" }, status.CapturePolicies);
    }

    /// <summary>Invalid policies cannot claim an owner or execute a task callback.</summary>
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("exclusive")]
    public void UnsupportedPolicyFailsBeforeOwnership(string? policy)
    {
        var owner = new NavigationBaselineTaskOwner();
        Assert.Throws<ArgumentException>(() => owner.TryStart(10, 3,
            (_, _, _) => throw new Exception("must not dispatch"), capturePolicy: policy!));
        Assert.False(owner.Running); Assert.Null(owner.Snapshot().RunId);
    }
}
