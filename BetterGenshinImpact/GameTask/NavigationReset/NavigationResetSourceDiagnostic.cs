using System;
using System.Diagnostics;
using Fischless.GameCapture;
using Newtonsoft.Json;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>One bounded transient or terminal source rejection; exact phase/stage distinguishes pose acquisitions.</summary>
internal sealed record NavigationResetSourceDiagnostic
{
    /// <summary>Version of this bounded log-only schema, independent of the reset result protocol.</summary>
    public int Version => ObservedHostSnapshot is not null ? 4 : PollingWindow is null ? 2 : 3;
    /// <summary>Existing exception code; diagnostic detail never replaces it.</summary>
    public string ErrorCode { get; init; } = "native_source_unavailable_or_stale";
    /// <summary>Specific source predicate that failed.</summary>
    public required string Reason { get; init; }
    /// <summary>Capture, initial source admission, or post-recognition source check.</summary>
    public required string Stage { get; init; }
    /// <summary>Fixed workflow phase: preparing, orienting or verifying; independent of the source-validation stage.</summary>
    public string Phase { get; init; } = "preparing";
    /// <summary>One-based run-local pose probe, or null during preparation before pose acquisition begins.</summary>
    public int? PoseAcquisitionOrdinal { get; init; }
    /// <summary>One-based preparation observation (at most25); version3 Pending refunds can repeat it. Null outside preparation.</summary>
    public int? PreparationAcquisitionOrdinal { get; init; }
    /// <summary>Whether this orientation read retains its original initial missing-HUD allowance; null during preparation.</summary>
    public bool? InitialHudSettling { get; init; }
    /// <summary>Raw QPC observation and conversion frequency, never a new capture timestamp.</summary>
    public long NowTicks { get; init; }
    /// <summary>Frequency for local QPC values; reported source ticks retain their fixed 100ns unit.</summary>
    public long ClockFrequency => Stopwatch.Frequency;
    /// <summary>Whether this runtime supports the original high-resolution clock guard.</summary>
    public bool HighResolutionClock => Stopwatch.IsHighResolution;
    /// <summary>Unchanged reset freshness threshold, distinct from baseline/agent thresholds.</summary>
    public int MaximumAgeMs => 500;
    /// <summary>Accepted epoch, or a valid-header provisional preparation epoch; null before either is available.</summary>
    public Guid? ExpectedEpoch { get; init; }
    /// <summary>Observed exact source, including its epoch and immutable first-acquisition clock.</summary>
    public GameCaptureSourceInfo? ObservedSource { get; init; }
    /// <summary>Separate host-only metadata; omitted from every legacy WGC diagnostic.</summary>
    [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
    public GameCaptureHostSnapshotInfo? ObservedHostSnapshot { get; init; }
    /// <summary>Optional trace from this same invocation; null for a backend without the diagnostic extension.</summary>
    public GameCaptureCallTiming? Capture { get; init; }
    /// <summary>Effective attached mode; missing support is explicit null.</summary>
    public string? ReadbackMode { get; init; }
    /// <summary>Total explicit Pending probes so far; version3 separately accounts for validated metadata refunds.</summary>
    public int ReadbackPendingCount { get; init; }
    /// <summary>Unpublished pending metadata, never an observed/accepted source or pixel-age measurement.</summary>
    public GameCapturePendingReadback? PendingReadback { get; init; }
    /// <summary>Optional current/last-returned probe metadata for any pose timeout; null on unchanged other diagnostics.</summary>
    public NavigationResetPoseTimeoutDiagnostic? PoseAcquisitionTimeout { get; init; }
    /// <summary>Only the explicit polling path emits this bounded ledger; absent on unchanged version2 logs.</summary>
    [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
    public NavigationResetPollingDiagnostic? PollingWindow { get; init; }
}
