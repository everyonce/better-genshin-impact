using BetterGenshinImpact.Core.Capture;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>File-only evidence envelope shared by publication and capacity tests; never included in a pipe response.</summary>
internal sealed class NavigationBaselineJournal
{
    /// <summary>Existing controller/pose schema remains compatible; detailed diagnostics have their own additive version.</summary>
    public int SchemaVersion => SourcePolicy is null ? 1 : 2;
    /// <summary>Explicit versioned host authority; null leaves all historical WGC evidence unchanged.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public string? SourcePolicy => WorkflowResult.SourcePolicy;
    /// <summary>Flat source-poll records and fixed recognition-phase boundaries.</summary>
    public int DiagnosticSchemaVersion => 2;
    /// <summary>Additive per-call backend stage schema; the original flat poll contract remains unchanged.</summary>
    public int CaptureTimingSchemaVersion => 1;
    /// <summary>Additive typed Pending evidence; source fields still describe returned pixels only.</summary>
    public int ReadbackVersion => 1;
    /// <summary>Effective Start-fixed mode pinned when this native run acquired ownership; null without support.</summary>
    public string? ReadbackMode { get; init; }
    /// <summary>All explicit Pending polls are retained within the existing global and per-window limits.</summary>
    public int ReadbackPendingCount => CapturePolls.Count(poll => poll.Result == "readback_pending");
    /// <summary>Selective slow/failure detail is never represented as a complete capture trace.</summary>
    public bool CompleteCaptureTimingTrace => false;
    /// <summary>Promote the final available invocation's stages after input closure, including a fast read followed by gate failure.</summary>
    public string CaptureTimingSelection => "slow-or-failed-plus-final-invocation";
    /// <summary>Threshold for retaining an otherwise successful backend call's internal stages.</summary>
    public double CaptureTimingThresholdMs => NavigationBaselineCapturePoll.SlowCaptureThresholdMs;
    /// <summary>Independent optional-detail capacity, with one terminal slot reserved.</summary>
    public int MaximumCaptureTimings => NavigationBaselineCapturePoll.MaximumCaptureTimings;
    /// <summary>Actual retained detail count, computed only during post-release publication.</summary>
    public int RetainedCaptureTimings => CapturePolls.Count(poll => poll.CaptureTiming is not null);
    /// <summary>Explicit eligible-detail loss count; omission never erases its required poll/source row.</summary>
    public int OmittedCaptureTimings => CapturePolls.Count(poll => poll.CaptureTimingOmitted);
    /// <summary>Owner-issued identifier shared by the terminal result and artifact directory.</summary>
    public required string RunId { get; init; }
    /// <summary>The only reviewed fixed route.</summary>
    public string ProfileId => WorkflowResult.ProfileId;
    /// <summary>Additive fixed continuation identity; absent for original single-leg records.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public int? RouteVersion => WorkflowResult.RouteVersion;
    /// <summary>Server-retained predecessor proof is part of the hashed journal, not supplied authority.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public NavigationBaselineContinuationLink? Continuation => WorkflowResult.Continuation;
    /// <summary>One bounded nonterminal waypoint record, separate from final closure and recovery.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] public NavigationBaselineWaypointRecord? Waypoint { get; init; }
    /// <summary>Capacity exhaustion remains incomplete even when its retained rows publish successfully.</summary>
    public bool EvidenceComplete => NativeNavigationBaselineOperations.EvidenceIsComplete(WorkflowResult);
    /// <summary>Algorithm identity does not imply a complete OS execution trace.</summary>
    public string ControllerMethod => WorkflowResult.ControllerMethod;
    /// <summary>Explicit timing selection does not change the route, image or pose acceptance contract.</summary>
    public string TimingContract => WorkflowResult.TimingContract;
    /// <summary>Selected timer-sharing experiment; no claim that other hotkey/background capture consumers were excluded.</summary>
    public string CapturePolicy => WorkflowResult.CapturePolicy;
    /// <summary>Pinned shipped route provenance.</summary>
    public string RouteSha256 => NavigationBaselineTask.RouteSha256;
    /// <summary>These are system-controller intent and recognized pose records.</summary>
    public string EvidenceKind => "controller-intent-and-pose";
    /// <summary>No human demonstration was captured.</summary>
    public bool HumanDemonstration => false;
    /// <summary>Neither this limited capture nor its timings establish training eligibility.</summary>
    public bool TrainingEligible => false;
    /// <summary>Input evidence records selected controller calls, not every OS dispatch.</summary>
    public bool CompleteLowLevelDispatchTrace => false;
    /// <summary>Only the owner can declare success after awaited cleanup.</summary>
    public bool OwnerCompletionRequired => true;
    /// <summary>Acquisition freshness must not be interpreted as physical game-render age.</summary>
    public string Clock => SourcePolicy is null
        ? "QPC milliseconds; source anchor=min(reported,first acquisition); game-render age unknown"
        : "QPC milliseconds; host acquisition-start anchor; compositor and game-render age unknown";
    /// <summary>Conversion factor for immutable native source ticks.</summary>
    public long QpcFrequency => Stopwatch.Frequency;
    /// <summary>Pinned process identity for this run.</summary>
    public required int GameProcessId { get; init; }
    /// <summary>Pinned RDP session.</summary>
    public required uint WindowsSessionId { get; init; }
    /// <summary>Workflow result before publication and final owner completion.</summary>
    public required NavigationBaselineRunResult WorkflowResult { get; init; }
    /// <summary>At most 1,024 accepted control observations.</summary>
    public required NavigationBaselineDecision[] Observations { get; init; }
    /// <summary>Bounded native-call intent, including release and fault evidence.</summary>
    public required NavigationBaselineInputEvent[] InputTransitions { get; init; }
    /// <summary>At most 1,024 workflow pacing records.</summary>
    public required NavigationBaselineScheduleWait[] ScheduleWaits { get; init; }
    /// <summary>At most 1,024 completed or failed native reads.</summary>
    public required IReadOnlyList<NavigationBaselineObservationAttempt> ObservationAttempts { get; init; }
    /// <summary>At most 4,096 flat poll records, without repeated nested lists.</summary>
    public required IReadOnlyList<NavigationBaselineCapturePoll> CapturePolls { get; init; }
    /// <summary>Additive v4 pause schema; all versions remain excluded from training.</summary>
    public int RecoverySchemaVersion => TimingContract == NavigationBaselineTiming.V4 ? 3 : 1;
    /// <summary>At most four run-global release tickets, including an interrupted pause that never reached a recovery loop.</summary>
    public IReadOnlyList<NavigationBaselineRecoveryPause> RecoveryPauses { get; init; } = [];
    /// <summary>At most four complete range-joined wait/rearm/failure records.</summary>
    public IReadOnlyList<NavigationBaselineRecoveryAttempt> RecoveryAttempts { get; init; } = [];
    /// <summary>Version3 keeps the original movement allowance and adds a distinct no-held-W source allowance.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? MaximumMovementRecoveries => TimingContract == NavigationBaselineTiming.V4
        ? NavigationBaselineRecovery.MaximumRecoveries : null;
    /// <summary>Stationary readiness is bounded across the complete run, not per leg.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? MaximumStationaryReadinessWindows => TimingContract == NavigationBaselineTiming.V4
        ? NavigationBaselineRecovery.MaximumStationaryReadiness : null;
    /// <summary>The total bound also applies to a pause that failed before entering its read loop.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? MaximumPauseWindows => TimingContract == NavigationBaselineTiming.V4
        ? NavigationBaselineRecovery.MaximumPauseWindows : null;
    /// <summary>Ticket-derived count includes failed release admissions without inventing a completed recovery.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? MovementRecoveryCount => TimingContract == NavigationBaselineTiming.V4
        ? RecoveryPauses.Count(pause => pause.BudgetKind == NavigationBaselineRecoveryBudgetKind.MovementRecovery) : null;
    /// <summary>Only atomically classified tickets contribute to this count; TriggerCause alone is insufficient.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? StationaryReadinessCount => TimingContract == NavigationBaselineTiming.V4
        ? RecoveryPauses.Count(pause => pause.BudgetKind == NavigationBaselineRecoveryBudgetKind.StationarySourceReadiness) : null;
    /// <summary>V4 final-read policy is independent of movement recovery; absent on unchanged legacy runs.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? FinalVerificationReadinessVersion => TimingContract == NavigationBaselineTiming.V4
        ? NavigationBaselineFinalVerification.Version : null;
    /// <summary>At most one terminally closed-input final window; null if travel never reached it.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public NavigationBaselineFinalVerificationWindow? FinalVerificationWindow { get; init; }
    /// <summary>At most one v4 no-input initial window; absent on legacy or preparation-only failures.</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public NavigationBaselineInitialReadinessWindow? InitialReadinessWindow { get; init; }
    /// <summary>Optional initial pixels and their immutable identity.</summary>
    public NavigationBaselineJournalImage? InitialImage { get; init; }
    /// <summary>Optional final pixels and their immutable identity.</summary>
    public NavigationBaselineJournalImage? FinalImage { get; init; }

    /// <summary>Serialize only after input closure; the existing file writer enforces the separate file-byte ceiling.</summary>
    internal byte[] Serialize() => JsonSerializer.SerializeToUtf8Bytes(this,
        new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            Converters = { new NavigationBaselineCaptureRectJsonConverter() } });
}

/// <summary>One retained image reference; pixels stay in the separately bounded PNG file.</summary>
internal sealed record NavigationBaselineJournalImage(string? Path, string? Sha256, CaptureSourceEvidence? Source);
