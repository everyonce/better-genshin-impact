using Fischless.GameCapture;
using BetterGenshinImpact.Core.Capture;
using Newtonsoft.Json;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>Retain only the current probe and last fully returned probe in one existing bounded acquisition.</summary>
/// <param name="startedAtTicks">Diagnostic entry time of this window, without redefining the acquisition deadline.</param>
internal sealed class NavigationResetPoseTimeoutEvidence(long startedAtTicks)
{
    /// <summary>Current probe, which may still be incomplete when cooperative cancellation is observed.</summary>
    private NavigationResetPoseProbeDiagnostic? _current;
    /// <summary>Last probe returned through all native disposals; no pixel or pose object is retained.</summary>
    private NavigationResetPoseProbeDiagnostic? _lastCompleted;

    /// <summary>Start a new probe without borrowing the previous probe's source, timing or Pending descriptor.</summary>
    internal NavigationResetPoseProbeDiagnostic Begin(int ordinal, long now) => _current = new()
        { PoseAcquisitionOrdinal = ordinal, StartedAtTicks = now };

    /// <summary>Mark return only outside the native using scopes; this does not imply acquisition-window acceptance.</summary>
    internal void Complete(NavigationResetPoseProbe probe, long now)
    {
        if (_current is not { } current) return;
        current.ReturnedAtTicks = now;
        current.ReturnedSample = probe.Sample is not null;
        current.RetryReason = probe.RetryReason is { Length: > 200 } reason ? reason[..200] : probe.RetryReason;
        _lastCompleted = current;
    }

    /// <summary>Copy two bounded metadata slots; omit the second when it is the same completed current probe.</summary>
    internal NavigationResetPoseTimeoutDiagnostic Snapshot(long now) => new(startedAtTicks, now,
        _current is null ? null : _current with { },
        _lastCompleted is null || ReferenceEquals(_current, _lastCompleted) ? null : _lastCompleted with { });
}

/// <summary>Log-only acquisition-window evidence, distinct from a valid pose or completed control operation.</summary>
/// <param name="StartedAtTicks">Local diagnostic entry time, not the owner or linked-token deadline origin.</param>
/// <param name="TimedOutAtTicks">Local time when the unchanged acquisition timeout was caught.</param>
/// <param name="CurrentProbe">Most recently entered probe, including an incomplete or late-returned probe.</param>
/// <param name="LastCompletedProbe">Earlier fully returned probe only when the current probe did not return.</param>
internal sealed record NavigationResetPoseTimeoutDiagnostic(long StartedAtTicks, long TimedOutAtTicks,
    NavigationResetPoseProbeDiagnostic? CurrentProbe, NavigationResetPoseProbeDiagnostic? LastCompletedProbe)
{
    /// <summary>Version of the optional bounded timeout detail; outer source-diagnostic version stays unchanged.</summary>
    public int Version => 1;
}

/// <summary>One native invocation's metadata; mutable only during that invocation, with no owned pixels or handles.</summary>
internal sealed record NavigationResetPoseProbeDiagnostic
{
    /// <summary>Existing one-based run-local pose ordinal, not a reset preparation ordinal.</summary>
    public int PoseAcquisitionOrdinal { get; init; }
    /// <summary>QPC at the actual native probe entry, after its original cancellation check.</summary>
    public long StartedAtTicks { get; init; }
    /// <summary>Last entered stage; incomplete work never becomes a completed recognition measurement.</summary>
    public string Stage { get; internal set; } = "capture";
    /// <summary>QPC after the capture call returns or throws; its own trace retains exact internal stages.</summary>
    public long? CaptureFinishedAtTicks { get; internal set; }
    /// <summary>Beginning of the same-frame world/yaw/map recognition block, when entered.</summary>
    public long? RecognitionStartedAtTicks { get; internal set; }
    /// <summary>Recognition block exit, including a transient miss or thrown/cancelled observation.</summary>
    public long? RecognitionFinishedAtTicks { get; internal set; }
    /// <summary>Time supplied to the most recent actual source-age predicate, never replaced by timeout emission time.</summary>
    public long? SourceCheckedAtTicks { get; internal set; }
    /// <summary>Source predicate stage; null for Pending, which carries no returned pixels/source age.</summary>
    public string? SourceCheckStage { get; internal set; }
    /// <summary>Exact source of returned pixels; null for Pending or a capture which has not returned pixels.</summary>
    public GameCaptureSourceInfo? Source { get; internal set; }
    /// <summary>Exact host interval when selected; no fabricated WGC source is retained.</summary>
    [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
    public GameCaptureHostSnapshotInfo? HostSnapshot { get; internal set; }
    /// <summary>Internal union used only to forward the current diagnostic to its terminal log.</summary>
    internal CaptureSourceEvidence? Evidence => HostSnapshot is { } host
        ? new CaptureSourceEvidence(host) : (CaptureSourceEvidence?)Source;
    /// <summary>Timing of this capture invocation, including null/throw; never copied from a prior probe.</summary>
    public GameCaptureCallTiming? Capture { get; internal set; }
    /// <summary>Current metadata-only Pending outcome; a Ready frame's next refill stays inside its capture trace.</summary>
    public GameCapturePendingReadback? PendingReadback { get; internal set; }
    /// <summary>QPC after this probe fully returns through disposal; null means it has not returned.</summary>
    public long? ReturnedAtTicks { get; internal set; }
    /// <summary>Whether the returned probe carried a sample; true alone never proves the deadline accepted it.</summary>
    public bool? ReturnedSample { get; internal set; }
    /// <summary>At most 200 characters, matching the existing acquisition exception's retry-reason bound.</summary>
    public string? RetryReason { get; internal set; }
}
