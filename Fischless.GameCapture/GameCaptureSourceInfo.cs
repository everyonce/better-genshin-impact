namespace Fischless.GameCapture;

/// <summary>
/// Immutable identity and timing supplied by the capture source, retained with the same pixels.
/// </summary>
/// <param name="CaptureEpoch">Generation created once for each capture Start.</param>
/// <param name="SourceTimestamp100ns">WGC SystemRelativeTime in 100-nanosecond units.</param>
/// <param name="AcquiredAtStopwatchTicks">Local Stopwatch timestamp immediately after successful frame acquisition.</param>
public sealed record GameCaptureSourceInfo(Guid CaptureEpoch, long SourceTimestamp100ns, long AcquiredAtStopwatchTicks)
{
    /// <summary>Identifies the capture generation; timestamps alone do not identify a restarted source.</summary>
    public Guid CaptureEpoch { get; init; } = CaptureEpoch;

    /// <summary>The source frame's SystemRelativeTime.Ticks, preserved when cached pixels are copied again.</summary>
    public long SourceTimestamp100ns { get; init; } = SourceTimestamp100ns;

    /// <summary>Frame acquisition time in Stopwatch ticks, distinct from event dispatch or consumer copy time.</summary>
    public long AcquiredAtStopwatchTicks { get; init; } = AcquiredAtStopwatchTicks;
}
