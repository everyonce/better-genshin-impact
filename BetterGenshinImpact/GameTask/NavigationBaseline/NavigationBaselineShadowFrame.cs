using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Immutable copied-pixel identity; capture-gate admission is not world/pose admission.</summary>
internal sealed record NavigationBaselineShadowFrame(
    int FrameIndex, int PollIndex, int ObservationIndex, GameCaptureSourceInfo Source,
    int Width, int Height, int Channels, int PackedStride,
    double CaptureStartedAtMs, double CaptureReturnedAtMs, double SourceAgeAtGateMs,
    string CaptureGateDisposition, long CopyStartedAtTicks, long CopyCompletedAtTicks);
