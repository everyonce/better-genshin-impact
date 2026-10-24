namespace Fischless.GameCapture;

/// <summary>Immutable host acquisition evidence retained with its exact pixels, separate from capture-source timestamps.</summary>
/// <param name="CaptureEpoch">Generation created by the successful Start that admitted this snapshot.</param>
/// <param name="SnapshotId">Positive acquisition identity within the generation; not a rendered-frame identity.</param>
/// <param name="StartedAtStopwatchTicks">Capture start under its gate, before target guards and GDI acquisition.</param>
/// <param name="CompletedAtStopwatchTicks">Completion after copy, post-guard, independent clone and successful cleanup.</param>
/// <param name="ClockFrequency">Stopwatch ticks per second for both interval endpoints.</param>
public sealed record GameCaptureHostSnapshotInfo(Guid CaptureEpoch, long SnapshotId,
    long StartedAtStopwatchTicks, long CompletedAtStopwatchTicks, long ClockFrequency);
