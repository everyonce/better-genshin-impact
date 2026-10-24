using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>File-only evidence envelope shared by publication and capacity tests; never included in a pipe response.</summary>
internal sealed class NavigationBaselineJournal
{
    /// <summary>Existing controller/pose schema remains compatible; detailed diagnostics have their own additive version.</summary>
    public int SchemaVersion => 1;
    /// <summary>Flat source-poll records and fixed recognition-phase boundaries.</summary>
    public int DiagnosticSchemaVersion => 2;
    /// <summary>Owner-issued identifier shared by the terminal result and artifact directory.</summary>
    public required string RunId { get; init; }
    /// <summary>The only reviewed fixed route.</summary>
    public string ProfileId => NavigationBaselineTask.ProfileId;
    /// <summary>Capacity exhaustion remains incomplete even when its retained rows publish successfully.</summary>
    public bool EvidenceComplete => NativeNavigationBaselineOperations.EvidenceIsComplete(WorkflowResult);
    /// <summary>Algorithm identity does not imply a complete OS execution trace.</summary>
    public string ControllerMethod => "native-fixed-leg-feedback-v1";
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
    public string Clock => "QPC milliseconds; source anchor=min(reported,first acquisition); game-render age unknown";
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
    /// <summary>Optional initial pixels and their immutable identity.</summary>
    public NavigationBaselineJournalImage? InitialImage { get; init; }
    /// <summary>Optional final pixels and their immutable identity.</summary>
    public NavigationBaselineJournalImage? FinalImage { get; init; }

    /// <summary>Serialize only after input closure; the existing file writer enforces the separate file-byte ceiling.</summary>
    internal byte[] Serialize() => JsonSerializer.SerializeToUtf8Bytes(this,
        new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
}

/// <summary>One retained image reference; pixels stay in the separately bounded PNG file.</summary>
internal sealed record NavigationBaselineJournalImage(string? Path, string? Sha256, GameCaptureSourceInfo? Source);
