using System;
using System.Text.Json.Serialization;
using BetterGenshinImpact.Core.Capture;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>One measured 2D pose; native source identity prevents cached pixels counting twice.</summary>
internal sealed record NavigationResetSample(
    [property: JsonPropertyName("x")] double X,
    [property: JsonPropertyName("y")] double Y,
    [property: JsonPropertyName("yawDegrees")] double YawDegrees,
    [property: JsonPropertyName("capturedAtUtc")] DateTimeOffset CapturedAtUtc,
    [property: JsonPropertyName("sourceEpoch")] Guid SourceEpoch,
    [property: JsonPropertyName("sourceTimestamp100ns"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] long? SourceTimestamp100ns,
    [property: JsonPropertyName("acquiredAtStopwatchTicks"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] long? AcquiredAtStopwatchTicks,
    [property: JsonPropertyName("positionConfidence")] double PositionConfidence,
    [property: JsonPropertyName("yawConfidence")] double YawConfidence,
    [property: JsonPropertyName("layerId")] string LayerId,
    [property: JsonPropertyName("hostSnapshot"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] GameCaptureHostSnapshotInfo? HostSnapshot = null)
{
    /// <summary>Only host samples add a source-kind tag; old WGC sample JSON remains unchanged.</summary>
    [JsonPropertyName("sourceKind"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SourceKind => HostSnapshot is null ? null : DesktopCapturePolicy.HostAcquisitionV1;
    /// <summary>Internal identity/spacing view retains the original fields without inventing missing WGC clocks.</summary>
    internal CaptureSourceEvidence? Evidence => HostSnapshot is { } host ? new(host)
        : SourceTimestamp100ns is { } reported && AcquiredAtStopwatchTicks is { } acquired
            ? new(SourceEpoch, reported, acquired) : null;
}

/// <summary>One returned final-verification observation, retained even when its rolling window is rejected.</summary>
/// <param name="Attempt">One-based verification read number, at most fifteen per run.</param>
/// <param name="Sample">The measured observation; this field alone never establishes successful verification.</param>
/// <param name="CandidateCount">Rolling candidate count after this observation, or zero when it cleared the window.</param>
/// <param name="Reason">Exact shared gate rejection, or accepted for the final successful window.</param>
/// <param name="TargetYawErrorDegrees">Circular target error, or null for invalid yaw.</param>
/// <param name="MaximumPositionSpread">Largest pairwise candidate distance, or null without a candidate pair.</param>
/// <param name="MaximumYawSpreadDegrees">Largest pairwise circular candidate yaw error, or null without a pair.</param>
/// <param name="MinimumAcquisitionGapMs">Smallest adjacent first-acquisition gap, or null without a pair.</param>
internal sealed record NavigationResetVerificationDiagnostic(
    [property: JsonPropertyName("attempt")] int Attempt,
    [property: JsonPropertyName("sample")] NavigationResetSample Sample,
    [property: JsonPropertyName("candidateCount")] int CandidateCount,
    [property: JsonPropertyName("reason")] string Reason,
    [property: JsonPropertyName("targetYawErrorDegrees")] double? TargetYawErrorDegrees,
    [property: JsonPropertyName("maximumPositionSpread")] double? MaximumPositionSpread,
    [property: JsonPropertyName("maximumYawSpreadDegrees")] double? MaximumYawSpreadDegrees,
    [property: JsonPropertyName("minimumAcquisitionGapMs")] double? MinimumAcquisitionGapMs);

/// <summary>Immutable command status. Completion means verification and TaskRunner cleanup both finished.</summary>
internal sealed record NavigationResetStatus
{
    /// <summary>Startup-fixed host authority, retained even on empty failures; absent on legacy WGC results.</summary>
    [JsonPropertyName("sourcePolicy"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SourcePolicy { get; init; }
    /// <summary>Effective runtime mode pinned before this reset was dispatched; not the current persisted setting.</summary>
    [JsonPropertyName("readbackMode")] public string? ReadbackMode { get; init; }
    /// <summary>Supported reset choices; task-owned isolation starts after teleport, unlike baseline's whole-task boundary.</summary>
    [JsonPropertyName("capturePolicies")] public string[] CapturePolicies => [NavigationResetCapturePolicy.Shared, NavigationResetCapturePolicy.TaskOwnedTimer];
    /// <summary>Immutable selection retained with this run, including terminal failures and diagnostics.</summary>
    [JsonPropertyName("capturePolicy")] public string CapturePolicy { get; init; } = NavigationResetCapturePolicy.Shared;
    /// <summary>Unique accepted run; null before the first request.</summary>
    [JsonPropertyName("runId")] public string? RunId { get; init; }
    /// <summary>Idle, running, completed, failed, or cancelled.</summary>
    [JsonPropertyName("state")] public string State { get; init; } = "idle";
    /// <summary>Current phase, retained on failure to locate the failed operation.</summary>
    [JsonPropertyName("phase")] public string Phase { get; init; } = "idle";
    /// <summary>Explicit failure/cancellation reason; no success is inferred from task dispatch.</summary>
    [JsonPropertyName("error")] public string? Error { get; init; }
    /// <summary>This command has exactly one fixed, reviewed waypoint profile.</summary>
    [JsonPropertyName("profileId")] public string ProfileId { get; init; } = NavigationResetTask.ProfileId;
    /// <summary>Requested minimap camera yaw, in degrees, with right=0 and down=90.</summary>
    [JsonPropertyName("targetYawDegrees")] public double TargetYawDegrees { get; init; }
    /// <summary>Game process pinned before dispatch.</summary>
    [JsonPropertyName("gameProcessId")] public int GameProcessId { get; init; }
    /// <summary>Actual Windows RDP session pinned before dispatch.</summary>
    [JsonPropertyName("windowsSessionId")] public int WindowsSessionId { get; init; }
    /// <summary>Accepted operation time, not native source time.</summary>
    [JsonPropertyName("startedAtUtc")] public DateTimeOffset? StartedAtUtc { get; init; }
    /// <summary>Time that the complete owned operation, including cleanup, ended.</summary>
    [JsonPropertyName("finishedAtUtc")] public DateTimeOffset? FinishedAtUtc { get; init; }
    /// <summary>Exactly three final verified samples on success; no pitch/elevation or save-state claim.</summary>
    [JsonPropertyName("samples")] public NavigationResetSample[] Samples { get; init; } = [];
    /// <summary>Advertise the pinned read-only diagnostics query without expanding ordinary status beyond legacy limits.</summary>
    [JsonPropertyName("verificationDiagnosticsVersion")] public int VerificationDiagnosticsVersion => 1;
    /// <summary>At most fifteen observations; omitted from ordinary status and included only in the explicit diagnostics reply.</summary>
    [JsonPropertyName("verificationDiagnostics")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public NavigationResetVerificationDiagnostic[]? VerificationDiagnostics { get; init; }
}
