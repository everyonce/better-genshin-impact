using System;
using System.Text.Json.Serialization;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Negative key-tip evidence only; normal never proves safe footing or physical velocity.</summary>
internal sealed record NavigationBaselineMotion([property: JsonPropertyName("status")] string Status, [property: JsonPropertyName("method")] string Method, [property: JsonPropertyName("spaceKeyMatched")] bool SpaceKeyMatched,
    [property: JsonPropertyName("xKeyMatched")] bool XKeyMatched, [property: JsonPropertyName("recognitionMs")] double RecognitionMs);

/// <summary>Absolute monotonic phase clocks distinguish barrier/frame waiting from recognition and scheduling cost.</summary>
internal sealed record NavigationBaselineObservationTiming([property: JsonPropertyName("observationStartedAtMs")] double ObservationStartedAtMs, [property: JsonPropertyName("captureRequestedAtMs")] double CaptureRequestedAtMs,
    [property: JsonPropertyName("captureReturnedAtMs")] double CaptureReturnedAtMs, [property: JsonPropertyName("recognitionCompletedAtMs")] double RecognitionCompletedAtMs);

/// <summary>One same-frame pose, confidence, native source identity and fixed-leg geometry.</summary>
internal sealed record NavigationBaselineSample([property: JsonPropertyName("x")] double X, [property: JsonPropertyName("y")] double Y, [property: JsonPropertyName("yawDegrees")] double YawDegrees, [property: JsonPropertyName("capturedAtUtc")] DateTimeOffset CapturedAtUtc,
    [property: JsonPropertyName("sourceEpoch")] Guid SourceEpoch, [property: JsonPropertyName("sourceTimestamp100ns")] long SourceTimestamp100ns, [property: JsonPropertyName("acquiredAtStopwatchTicks")] long AcquiredAtStopwatchTicks, [property: JsonPropertyName("positionConfidence")] double PositionConfidence,
    [property: JsonPropertyName("yawConfidence")] double YawConfidence, [property: JsonPropertyName("layerId")] string LayerId, [property: JsonPropertyName("motion")] NavigationBaselineMotion Motion, [property: JsonPropertyName("sourceAgeMs")] double SourceAgeMs,
    [property: JsonPropertyName("targetHeadingDegrees")] double TargetHeadingDegrees, [property: JsonPropertyName("distanceToEnd")] double DistanceToEnd, [property: JsonPropertyName("projection")] double Projection, [property: JsonPropertyName("crossTrack")] double CrossTrack,
    [property: JsonPropertyName("timing")] NavigationBaselineObservationTiming Timing)
{
    /// <summary>Reconstruct the immutable source for last-moment age checks without renewing its acquisition clock.</summary>
    [JsonIgnore] internal GameCaptureSourceInfo Source => new(SourceEpoch, SourceTimestamp100ns, AcquiredAtStopwatchTicks);
}

/// <summary>Controller intent and native-call timings, not a complete OS trace or game acknowledgment.</summary>
internal sealed record NavigationBaselineInputEvent([property: JsonPropertyName("kind")] string Kind, [property: JsonPropertyName("requestedAtMs")] double RequestedAtMs, [property: JsonPropertyName("completedAtMs")] double CompletedAtMs,
    [property: JsonPropertyName("expiresAtMs")] double? ExpiresAtMs = null, [property: JsonPropertyName("sourceAgeMs")] double? SourceAgeMs = null, [property: JsonPropertyName("mouseDx")] int MouseDx = 0, [property: JsonPropertyName("error")] string? Error = null);

/// <summary>One measured control decision; renewal can extend a lease without issuing another keydown.</summary>
internal sealed record NavigationBaselineDecision([property: JsonPropertyName("phase")] string Phase, NavigationBaselineSample Sample,
    NavigationBaselineInputEvent? Intent, [property: JsonPropertyName("rejectionReason")] string? RejectionReason = null);

/// <summary>Published local evidence references; bulk journal rows never expand ordinary pipe status.</summary>
internal sealed record NavigationBaselineEvidence([property: JsonPropertyName("complete")] bool Complete, [property: JsonPropertyName("journalPath")] string JournalPath, [property: JsonPropertyName("journalSha256")] string JournalSha256,
    [property: JsonPropertyName("initialImagePath")] string? InitialImagePath, [property: JsonPropertyName("initialImageSha256")] string? InitialImageSha256, [property: JsonPropertyName("finalImagePath")] string? FinalImagePath, [property: JsonPropertyName("finalImageSha256")] string? FinalImageSha256);

/// <summary>Measured workflow result; only its owner can declare completion after TaskRunner/native cleanup.</summary>
internal sealed record NavigationBaselineRunResult
{
    /// <summary>True only for the strict three-sample final gate and complete evidence.</summary>
    [JsonPropertyName("verified")]
    public bool Verified { get; init; }
    /// <summary>Workflow phase retained for failures, separately from later owner cleanup.</summary>
    [JsonPropertyName("phase")]
    public string Phase { get; init; } = "starting";
    /// <summary>Explicit workflow failure, including source, input or evidence publication errors.</summary>
    [JsonPropertyName("error")]
    public string? Error { get; init; }
    /// <summary>First accepted pose, before any baseline input.</summary>
    [JsonPropertyName("initialSample")]
    public NavigationBaselineSample? InitialSample { get; init; }
    /// <summary>Exactly three strictly verified poses on success, otherwise empty.</summary>
    [JsonPropertyName("samples")]
    public NavigationBaselineSample[] Samples { get; init; } = [];
    /// <summary>All of the at-most-three final reads, including rejected evidence.</summary>
    [JsonPropertyName("verificationSamples")]
    public NavigationBaselineSample[] VerificationSamples { get; init; } = [];
    /// <summary>Number of bounded accepted observations retained in the local journal.</summary>
    [JsonPropertyName("observationCount")]
    public int ObservationCount { get; init; }
    /// <summary>Artifact paths and hashes; null when publication failed.</summary>
    [JsonPropertyName("evidence")]
    public NavigationBaselineEvidence? Evidence { get; init; }
    /// <summary>Monotonic elapsed workflow time, including evidence publication.</summary>
    [JsonPropertyName("elapsedMs")]
    public double ElapsedMs { get; init; }
    /// <summary>Failed native release is never represented as an input acknowledgment.</summary>
    [JsonPropertyName("inputReleaseError")]
    public string? InputReleaseError { get; init; }
}

/// <summary>Small owner status compatible with the legacy ordinary-status response limit.</summary>
internal sealed record NavigationBaselineStatus
{
    /// <summary>Accepted fixed-leg run identity, or null before the first run.</summary>
    [JsonPropertyName("runId")]
    public string? RunId { get; init; }
    /// <summary>Idle, running, completed, failed or cancelled.</summary>
    [JsonPropertyName("state")]
    public string State { get; init; } = "idle";
    /// <summary>Current phase, retained on failure.</summary>
    [JsonPropertyName("phase")]
    public string Phase { get; init; } = "idle";
    /// <summary>Owner or workflow failure, never inferred from dispatch alone.</summary>
    [JsonPropertyName("error")]
    public string? Error { get; init; }
    /// <summary>The one shipped leg supported by this endpoint.</summary>
    [JsonPropertyName("profileId")]
    public string ProfileId => NavigationBaselineTask.ProfileId;
    /// <summary>Pinned game process identity.</summary>
    [JsonPropertyName("gameProcessId")]
    public int GameProcessId { get; init; }
    /// <summary>Pinned Windows RDP session.</summary>
    [JsonPropertyName("windowsSessionId")]
    public int WindowsSessionId { get; init; }
    /// <summary>Wall-clock request acceptance, not native image time.</summary>
    [JsonPropertyName("startedAtUtc")]
    public DateTimeOffset? StartedAtUtc { get; init; }
    /// <summary>Wall-clock completion after cleanup.</summary>
    [JsonPropertyName("finishedAtUtc")]
    public DateTimeOffset? FinishedAtUtc { get; init; }
    /// <summary>Retained journal observation count.</summary>
    [JsonPropertyName("observationCount")]
    public int ObservationCount { get; init; }
    /// <summary>Whether bounded local evidence publication finished.</summary>
    [JsonPropertyName("evidenceComplete")]
    public bool EvidenceComplete { get; init; }
    /// <summary>Advertises the separate pinned result endpoint.</summary>
    [JsonPropertyName("resultVersion")]
    public int ResultVersion => 1;
    /// <summary>Omitted from ordinary status; exposed only by the authenticated terminal result command.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    [JsonPropertyName("result")]
    public NavigationBaselineRunResult? Result { get; init; }
}
