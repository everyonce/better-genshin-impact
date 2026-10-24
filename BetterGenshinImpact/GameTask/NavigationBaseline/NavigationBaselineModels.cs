using System;
using System.Collections.Generic;
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
    /// <summary>Present only for the new fixed route; old single-leg JSON remains unchanged.</summary>
    [JsonPropertyName("legIndex"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? LegIndex { get; init; }
    /// <summary>Reconstruct the immutable source for last-moment age checks without renewing its acquisition clock.</summary>
    [JsonIgnore] internal GameCaptureSourceInfo Source => new(SourceEpoch, SourceTimestamp100ns, AcquiredAtStopwatchTicks);
}

/// <summary>Controller intent and native-call timings, not a complete OS trace or game acknowledgment.</summary>
/// <param name="GrantMs">Selected nominal W grant before the optional source-relative cap; null for non-grant calls.</param>
/// <param name="SourceAnchorAtMs">Conservative immutable source clock used for this grant.</param>
/// <param name="SourceCapAtMs">V2/V3/V4 source anchor plus250ms; null for legacy or non-grant calls.</param>
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
    /// <summary>Separate v4 terminal-read disposition; absent outside the versioned final window.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? FinalVerificationDisposition { get; set; }
    /// <summary>Exact source check stage, including final image/callback admission checks.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? FinalVerificationCheckStage { get; set; }
    /// <summary>Absolute QPC time of that source check; not the recognition-time sample age.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? FinalVerificationCheckedAtMs { get; set; }
    /// <summary>Immutable-source age at the explicit final check; positive age alone may be discarded.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? FinalVerificationSourceAgeMs { get; set; }
    /// <summary>Separate midpoint admission/discard evidence; never terminal-final ownership.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? WaypointDisposition { get; set; }
    /// <summary>Exact midpoint source-check stage.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? WaypointCheckStage { get; set; }
    /// <summary>Actual midpoint check clock.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? WaypointCheckedAtMs { get; set; }
    /// <summary>Age at that check without renewing immutable source metadata.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public double? WaypointSourceAgeMs { get; set; }
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
    [property: JsonPropertyName("initialImagePath")] string? InitialImagePath, [property: JsonPropertyName("initialImageSha256")] string? InitialImageSha256, [property: JsonPropertyName("finalImagePath")] string? FinalImagePath, [property: JsonPropertyName("finalImageSha256")] string? FinalImageSha256)
{
    /// <summary>Effective backend mode pinned by the native run, independently of persisted configuration.</summary>
    [JsonPropertyName("readbackMode")] public string? ReadbackMode { get; init; }
}

/// <summary>File-only bounded final-read record; it cannot resume input or consume a movement recovery ticket.</summary>
internal sealed class NavigationBaselineFinalVerificationWindow
{
    /// <summary>Explicit policy identity, distinct from movement recovery and legacy strict final reads.</summary>
    public string Method => "closed-input-final-source-age-readiness-v2";
    /// <summary>Fixed bounds apply to this whole three-sample window.</summary>
    public int MaximumWaitMs => NavigationBaselineFinalVerification.MaximumWaitMs;
    /// <summary>Every Ready/null/error call is charged, including duplicate/barrier/stale pixels; only validated Pending is excluded.</summary>
    public int MaximumCaptures => NavigationBaselineFinalVerification.MaximumCaptures;
    /// <summary>Finite unpublished-work polling allowance within the unchanged whole-window deadline.</summary>
    public int MaximumPendingPolls => NavigationBaselineFinalVerification.MaximumPendingPolls;
    /// <summary>Total call reservations remain bounded even when no frame ever becomes ready.</summary>
    public int MaximumPolls => NavigationBaselineFinalVerification.MaximumPolls;
    /// <summary>Read invocations are bounded independently of inner duplicate/barrier polls.</summary>
    public int MaximumReads => NavigationBaselineFinalVerification.MaximumReads;
    /// <summary>The first successful terminal input close, never a refreshed retry cutoff.</summary>
    public required double ClosedAtMs { get; init; }
    /// <summary>Actual window entry; may already be past the owner-clipped deadline.</summary>
    public required double StartedAtMs { get; init; }
    /// <summary>Earlier of terminal close plus two seconds and the original owner deadline.</summary>
    public required double DeadlineAtMs { get; init; }
    /// <summary>Exit after completed or failed collection; synchronous work is never abandoned.</summary>
    public double? EndedAtMs { get; set; }
    /// <summary>Half-open global read range, including a recorded terminal native failure.</summary>
    public required int ObservationStart { get; init; }
    /// <summary>Global read count at window exit; admission failure can prevent a requested read row.</summary>
    public int ObservationEnd { get; set; }
    /// <summary>Half-open global capture-poll range.</summary>
    public required int PollStart { get; init; }
    /// <summary>Global poll count at window exit.</summary>
    public int PollEnd { get; set; }
    /// <summary>Number of native read invocations requested, including one rejected by global evidence capacity.</summary>
    public int ReadCount { get; set; }
    /// <summary>V2 conservative capture charges: Ready/null/error plus any unclassified reservation; validated Pending alone is refunded.</summary>
    public int CaptureCount { get; set; }
    /// <summary>Pre-call reservations (setup may still fail); equals CaptureCount plus PendingPollCount, including failures.</summary>
    public int PollCount { get; set; }
    /// <summary>Only typed Pending with valid source/epoch/geometry metadata consumes this separate allowance.</summary>
    public int PendingPollCount { get; set; }
    /// <summary>Typed sole-age outcomes caught by this window, not generic recognition/input failures.</summary>
    public int SourceAgeDiscards { get; set; }
    /// <summary>At most three global read indexes with transactional sample/decision/image admission.</summary>
    public List<int> AcceptedReadIndices { get; } = new(3);
    /// <summary>Only completed means exactly three admitted samples before the unchanged final gate.</summary>
    public string Outcome { get; set; } = "starting";
    /// <summary>Specific terminal failure, preserving original hard-error/cancellation provenance.</summary>
    public string? Error { get; set; }
}

/// <summary>Measured workflow result; only its owner can declare completion after TaskRunner/native cleanup.</summary>
internal sealed record NavigationBaselineRunResult
{
    /// <summary>Selected fixed profile; legacy callers retain the original leg.</summary>
    [JsonPropertyName("profileId")] public string ProfileId { get; init; } = NavigationBaselineTask.ProfileId;
    /// <summary>Additive continuation schema, omitted on the unchanged single-leg path.</summary>
    [JsonPropertyName("routeVersion"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? RouteVersion => ProfileId == NavigationBaselineRouteProfile.TwoLegId ? 1 : null;
    /// <summary>At most two summaries; empty for legacy single-leg evidence.</summary>
    [JsonPropertyName("legs")] public NavigationBaselineLegResult[] Legs { get; init; } = [];
    /// <summary>Detached partial or completed waypoint evidence; never overall completion by itself.</summary>
    [JsonPropertyName("waypoint"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public NavigationBaselineWaypointRecord? Waypoint { get; init; }

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
    /// <summary>At most three final samples: v4 admitted prefix; legacy strict reads may include a final-gate rejection.</summary>
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
    /// <summary>Effective native run mode from its completed evidence, null until that evidence exists.</summary>
    [JsonPropertyName("readbackMode")] public string? ReadbackMode { get; init; }
    /// <summary>Supported timer/task sharing choices; old hosts omit this capability.</summary>
    [JsonPropertyName("capturePolicies")]
    public string[] CapturePolicies => [NavigationBaselineCapturePolicy.Shared, NavigationBaselineCapturePolicy.TaskOwnedTimer];
    /// <summary>Pinned selection for this run, independent of the timing contract.</summary>
    [JsonPropertyName("capturePolicy")]
    public string CapturePolicy { get; init; } = NavigationBaselineCapturePolicy.Shared;
    /// <summary>Supported fixed contracts; older hosts omit this additive capability.</summary>
    [JsonPropertyName("timingContracts")]
    public string[] TimingContracts => [NavigationBaselineTiming.V1, NavigationBaselineTiming.V2, NavigationBaselineTiming.V3, NavigationBaselineTiming.V4];
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
    public string ProfileId { get; init; } = NavigationBaselineTask.ProfileId;
    /// <summary>Advertise exact fixed-route selection before any mutation.</summary>
    [JsonPropertyName("routeVersion")] public int RouteVersion => 1;
    /// <summary>Only these reviewed built-in route identities are accepted.</summary>
    [JsonPropertyName("routeProfiles")] public string[] RouteProfiles => [NavigationBaselineTask.ProfileId, NavigationBaselineRouteProfile.TwoLegId];
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

/// <summary>At most two immutable per-leg outcomes; the final overall owner may still fail cleanup.</summary>
internal sealed record NavigationBaselineLegResult([property: JsonPropertyName("legIndex")] int LegIndex,
    [property: JsonPropertyName("startPointId")] int StartPointId, [property: JsonPropertyName("endPointId")] int EndPointId,
    [property: JsonPropertyName("startedAtMs")] double StartedAtMs, [property: JsonPropertyName("endedAtMs")] double EndedAtMs,
    [property: JsonPropertyName("decisionStart")] int DecisionStart, [property: JsonPropertyName("decisionEnd")] int DecisionEnd,
    [property: JsonPropertyName("outcome")] string Outcome);

/// <summary>One bounded midpoint window, separate from permanent final closure and movement recovery.</summary>
internal sealed record NavigationBaselineWaypointRecord
{
    /// <summary>Fixed waypoint policy identity, never a generic pause command.</summary>
    [JsonPropertyName("method")]
    public string Method => "released-waypoint-three-plus-anchor-v1";
    /// <summary>Exact native release completion, including already-released cutoff.</summary>
    [JsonPropertyName("release")]
    public required NavigationBaselineInputEvent Release { get; init; }
    /// <summary>Immutable owner-clipped two-second deadline.</summary>
    [JsonPropertyName("deadlineAtMs")]
    public required double DeadlineAtMs { get; init; }
    /// <summary>Actual handoff or terminal failure clock.</summary>
    [JsonPropertyName("endedAtMs")]
    public double? EndedAtMs { get; set; }
    /// <summary>Half-open global read range; no counter resets at the waypoint.</summary>
    [JsonPropertyName("observationStart")]
    public int ObservationStart { get; init; }
    /// <summary>Exclusive global read end including failed work.</summary>
    [JsonPropertyName("observationEnd")]
    public int ObservationEnd { get; set; }
    /// <summary>First global poll offset.</summary>
    [JsonPropertyName("pollStart")]
    public int PollStart { get; init; }
    /// <summary>Exclusive poll end including Pending and age discards.</summary>
    [JsonPropertyName("pollEnd")]
    public int PollEnd { get; set; }
    /// <summary>All read attempts, bounded to32 across the checkpoint and anchor.</summary>
    [JsonPropertyName("readCount")]
    public int ReadCount { get; set; }
    /// <summary>Actual native calls, bounded to32 including Pending.</summary>
    [JsonPropertyName("captureCount")]
    public int CaptureCount { get; set; }
    /// <summary>Only typed sole-age retries, never hard recognition/source failures.</summary>
    [JsonPropertyName("sourceAgeDiscards")]
    public int SourceAgeDiscards { get; set; }
    /// <summary>At most three committed checkpoint poses; partial evidence survives failure.</summary>
    [JsonPropertyName("samples")]
    public NavigationBaselineSample[] Samples { get; set; } = [];
    /// <summary>The separate fourth pose, used by the next decision exactly once.</summary>
    [JsonPropertyName("anchor")]
    public NavigationBaselineSample? Anchor { get; set; }
    /// <summary>Only completed represents a cleared hold; it is not overall route success.</summary>
    [JsonPropertyName("outcome")]
    public string Outcome { get; set; } = "holding";
    /// <summary>Bounded terminal reason retained without retrying input.</summary>
    [JsonPropertyName("error")]
    public string? Error { get; set; }
    /// <summary>Detach mutable arrays before status/publication exposes this serial native record.</summary>
    internal NavigationBaselineWaypointRecord Snapshot() => this with { Samples = [.. Samples] };
}
