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
/// <param name="GrantMs">Selected nominal W grant before the optional source-relative cap; null for non-grant calls.</param>
/// <param name="SourceAnchorAtMs">Conservative immutable source clock used for this grant.</param>
/// <param name="SourceCapAtMs">V2/V3 source anchor plus250ms; null for legacy or non-grant calls.</param>
/// <param name="FirstForwardAttempt">Whether this is the run's first W-down attempt, not an OS/game acknowledgment.</param>
internal sealed record NavigationBaselineInputEvent([property: JsonPropertyName("kind")] string Kind, [property: JsonPropertyName("requestedAtMs")] double RequestedAtMs, [property: JsonPropertyName("completedAtMs")] double CompletedAtMs,
    [property: JsonPropertyName("expiresAtMs")] double? ExpiresAtMs = null, [property: JsonPropertyName("sourceAgeMs")] double? SourceAgeMs = null, [property: JsonPropertyName("mouseDx")] int MouseDx = 0, [property: JsonPropertyName("error")] string? Error = null,
    [property: JsonPropertyName("grantMs")] double? GrantMs = null, [property: JsonPropertyName("sourceAnchorAtMs")] double? SourceAnchorAtMs = null,
    [property: JsonPropertyName("sourceCapAtMs")] double? SourceCapAtMs = null, [property: JsonPropertyName("firstForwardAttempt")] bool? FirstForwardAttempt = null);

/// <summary>One measured control decision; renewal can extend a lease without issuing another keydown.</summary>
internal sealed record NavigationBaselineDecision([property: JsonPropertyName("phase")] string Phase, NavigationBaselineSample Sample,
    NavigationBaselineInputEvent? Intent, [property: JsonPropertyName("rejectionReason")] string? RejectionReason = null);

/// <summary>File-only pacing evidence, including a wait cancelled before the next native observation begins.</summary>
internal sealed record NavigationBaselineScheduleWait(double PreviousObservationStartedAtMs, double RequestedDeadlineMs,
    double StartedAtMs, double ExitedAtMs, string? Error);

/// <summary>File-only single-reader diagnostics; a failed read retains its last stage without claiming an accepted pose.</summary>
internal sealed class NavigationBaselineObservationAttempt(double startedAtMs)
{
    /// <summary>Actual native read entry and exit in absolute QPC milliseconds.</summary>
    public double StartedAtMs { get; } = startedAtMs;
    /// <summary>Set in finally even when capture, recognition, source checks or cancellation fail.</summary>
    public double? EndedAtMs { get; set; }
    /// <summary>Last reached phase; failure does not replace the useful in-flight stage.</summary>
    public string Stage { get; set; } = "starting";
    /// <summary>Last capture call boundaries, including a call that failed before returning.</summary>
    public double? CaptureStartedAtMs { get; set; }
    /// <summary>Null when the most recent capture did not return.</summary>
    public double? CaptureReturnedAtMs { get; set; }
    /// <summary>Beginning of same-frame recognition, after source/barrier admission.</summary>
    public double? RecognitionStartedAtMs { get; set; }
    /// <summary>Null until all same-frame recognition has completed.</summary>
    public double? RecognitionCompletedAtMs { get; set; }
    /// <summary>Fixed phase boundaries keep timing evidence bounded without one nested row per operation.</summary>
    public double? WorldCompletedAtMs { get; set; }
    /// <summary>Optional same-frame chat completion; null on the unchanged shared-capture path.</summary>
    public double? ChatCompletedAtMs { get; set; }
    /// <summary>Direct chat classification, including open-chat evidence that terminates before world recognition.</summary>
    public string? ChatState { get; set; }
    /// <summary>End of native key-tip recognition on the same frame.</summary>
    public double? MotionCompletedAtMs { get; set; }
    /// <summary>End of color conversion, owned content construction and minimap crop setup.</summary>
    public double? CropCompletedAtMs { get; set; }
    /// <summary>End of the single yaw/mask preprocessing pass; null if that pass throws.</summary>
    public double? PreprocessingCompletedAtMs { get; set; }
    /// <summary>Exact immutable metadata from the last returned capture, even if its source was rejected.</summary>
    public GameCaptureSourceInfo? LastReturnedSource { get; set; }
    /// <summary>Counts include rejected/cached polls without retaining an unbounded per-poll list.</summary>
    public int CaptureCount { get; set; }
    /// <summary>Number of captures with either source clock unchanged.</summary>
    public int DuplicateCount { get; set; }
    /// <summary>Number of captures rejected by the unchanged dual-clock response barrier.</summary>
    public int BarrierCount { get; set; }
    /// <summary>Original read exception, independent of a concurrent lease fault.</summary>
    public string? Error { get; set; }
    /// <summary>Watchdog reason at read exit, when present.</summary>
    public string? LeaseFault { get; set; }

    /// <summary>Bound diagnostic text without changing the workflow's original exception.</summary>
    internal static string DescribeError(Exception exception)
    {
        var message = exception.GetBaseException().Message;
        return message.Length <= 512 ? message : message[..512];
    }
}

/// <summary>Published local evidence references; bulk journal rows never expand ordinary pipe status.</summary>
internal sealed record NavigationBaselineEvidence([property: JsonPropertyName("complete")] bool Complete, [property: JsonPropertyName("journalPath")] string JournalPath, [property: JsonPropertyName("journalSha256")] string JournalSha256,
    [property: JsonPropertyName("initialImagePath")] string? InitialImagePath, [property: JsonPropertyName("initialImageSha256")] string? InitialImageSha256, [property: JsonPropertyName("finalImagePath")] string? FinalImagePath, [property: JsonPropertyName("finalImageSha256")] string? FinalImageSha256);

/// <summary>Measured workflow result; only its owner can declare completion after TaskRunner/native cleanup.</summary>
internal sealed record NavigationBaselineRunResult
{
    /// <summary>Selected capture experiment, independent of input timing and retained on failure.</summary>
    [JsonPropertyName("capturePolicy")]
    public string CapturePolicy { get; init; } = NavigationBaselineCapturePolicy.Shared;
    /// <summary>Exact selected timing contract, retained on failure as well as measured success.</summary>
    [JsonPropertyName("timingContract")]
    public string TimingContract { get; init; } = NavigationBaselineTiming.V1;
    /// <summary>Controller identity makes cross-version comparisons explicit.</summary>
    [JsonPropertyName("controllerMethod")]
    public string ControllerMethod => NavigationBaselineTiming.ControllerMethod(TimingContract);
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
    /// <summary>Supported timer/task sharing choices; old hosts omit this capability.</summary>
    [JsonPropertyName("capturePolicies")]
    public string[] CapturePolicies => [NavigationBaselineCapturePolicy.Shared, NavigationBaselineCapturePolicy.TaskOwnedTimer];
    /// <summary>Pinned selection for this run, independent of the timing contract.</summary>
    [JsonPropertyName("capturePolicy")]
    public string CapturePolicy { get; init; } = NavigationBaselineCapturePolicy.Shared;
    /// <summary>Supported fixed contracts; older hosts omit this additive capability.</summary>
    [JsonPropertyName("timingContracts")]
    public string[] TimingContracts => [NavigationBaselineTiming.V1, NavigationBaselineTiming.V2, NavigationBaselineTiming.V3];
    /// <summary>Selected contract for the retained run; omitted requests use v1.</summary>
    [JsonPropertyName("timingContract")]
    public string TimingContract { get; init; } = NavigationBaselineTiming.V1;
    /// <summary>Algorithm identity is pinned with the run, independent of endpoint success.</summary>
    [JsonPropertyName("controllerMethod")]
    public string ControllerMethod => NavigationBaselineTiming.ControllerMethod(TimingContract);
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
