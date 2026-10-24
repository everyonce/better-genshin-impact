using System;
using System.Diagnostics;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>One terminal source rejection; fixed fields retain timing without changing the stable error or retry rules.</summary>
internal sealed record NavigationResetSourceDiagnostic
{
    /// <summary>Version of this bounded log-only schema, independent of the reset result protocol.</summary>
    public int Version => 1;
    /// <summary>Existing exception code; diagnostic detail never replaces it.</summary>
    public string ErrorCode { get; init; } = "native_source_unavailable_or_stale";
    /// <summary>Specific source predicate that failed.</summary>
    public required string Reason { get; init; }
    /// <summary>Capture, initial source admission, or post-recognition source check.</summary>
    public required string Stage { get; init; }
    /// <summary>Raw QPC observation and conversion frequency, never a new capture timestamp.</summary>
    public long NowTicks { get; init; }
    /// <summary>Frequency for local QPC values; reported source ticks retain their fixed 100ns unit.</summary>
    public long ClockFrequency => Stopwatch.Frequency;
    /// <summary>Whether this runtime supports the original high-resolution clock guard.</summary>
    public bool HighResolutionClock => Stopwatch.IsHighResolution;
    /// <summary>Unchanged reset freshness threshold, distinct from baseline/agent thresholds.</summary>
    public int MaximumAgeMs => 500;
    /// <summary>Epoch pinned by a previously accepted source, or null before first admission.</summary>
    public Guid? ExpectedEpoch { get; init; }
    /// <summary>Observed exact source, including its epoch and immutable first-acquisition clock.</summary>
    public GameCaptureSourceInfo? ObservedSource { get; init; }
    /// <summary>Optional trace from this same invocation; null for a backend without the diagnostic extension.</summary>
    public GameCaptureCallTiming? Capture { get; init; }
}
