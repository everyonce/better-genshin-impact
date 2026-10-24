using BetterGenshinImpact.Core.Capture;
using System.Collections.Generic;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>One bounded file-only initial-readiness record; no accepted trajectory or input claim is inferred from discards.</summary>
internal sealed class NavigationBaselineInitialReadinessWindow
{
    /// <summary>Separate initial-only policy identity.</summary>
    public int Version => NavigationBaselineInitialReadiness.Version;
    /// <summary>Explicit scope, distinct from movement recovery and terminal verification.</summary>
    public string Method => "no-input-initial-source-readiness-v2";
    /// <summary>Actual start after preparation, on the workflow's QPC origin.</summary>
    public required double StartedAtMs { get; init; }
    /// <summary>Original workflow deadline supplied by Task; preparation time is not reset.</summary>
    public required double OwnerDeadlineAtMs { get; init; }
    /// <summary>Earlier of entry plus2s and the original owner deadline.</summary>
    public required double DeadlineAtMs { get; init; }
    /// <summary>Collector exit, including failed or cancelled work.</summary>
    public double? EndedAtMs { get; set; }
    /// <summary>First global read index; no accepted observation is implied.</summary>
    public int ObservationStart { get; init; }
    /// <summary>Exclusive read end, including source discards and terminal attempts.</summary>
    public int ObservationEnd { get; set; }
    /// <summary>First global capture-poll index.</summary>
    public int PollStart { get; init; }
    /// <summary>Exclusive poll end; setup failure may leave one charged reservation without a row.</summary>
    public int PollEnd { get; set; }
    /// <summary>All initial read attempts, including solely-age rejections.</summary>
    public int ReadCount { get; set; }
    /// <summary>Pre-call reservations; Pending never erases this count or the global evidence count.</summary>
    public int PollCount { get; set; }
    /// <summary>Conservative charged calls; only validated typed Pending refunds one.</summary>
    public int CaptureCount { get; set; }
    /// <summary>Exactly settled valid Pending returns, not images or poses.</summary>
    public int PendingPollCount { get; set; }
    /// <summary>Only recorded typed age rejections handled inside this no-input initial collector.</summary>
    public int SourceAgeDiscards { get; set; }
    /// <summary>Fixed limits copied into evidence, independent of elapsed-time exhaustion.</summary>
    public int MaximumWaitMs => NavigationBaselineInitialReadiness.MaximumWaitMs;
    /// <summary>Read limit is independent of the capture/Pending budget.</summary>
    public int MaximumReads => NavigationBaselineInitialReadiness.MaximumReads;
    /// <summary>Ready/null/error reservation ceiling.</summary>
    public int MaximumCaptures => NavigationBaselineInitialReadiness.MaximumCaptures;
    /// <summary>Validated Pending refund ceiling.</summary>
    public int MaximumPendingPolls => NavigationBaselineInitialReadiness.MaximumPendingPolls;
    /// <summary>Total pre-call ceiling.</summary>
    public int MaximumPolls => NavigationBaselineInitialReadiness.MaximumPolls;
    /// <summary>Capture plus recognition/retention/returned-read checks have an independent fixed evidence bound.</summary>
    public int MaximumSourceChecks => NavigationBaselineInitialReadiness.MaximumSourceChecks;
    /// <summary>Header high-water includes stale returned pixels, never Pending or accepted-pose authority.</summary>
    public CaptureSourceEvidence? SeenSource { get; set; }
    /// <summary>Geometry pinned before the first age rejection, if a valid returned header exists.</summary>
    public int? Width { get; set; }
    /// <summary>Height from the same returned header.</summary>
    public int? Height { get; set; }
    /// <summary>At most160 stage checks join flat polls/reads. A returned-read discard does not change its completed read row.</summary>
    public List<NavigationBaselineInitialSourceCheck> SourceChecks { get; } = [];
    /// <summary>Only a completely returned, still timely initial pose sets this index; Task still checks its start region.</summary>
    public int? AdmittedReadIndex { get; set; }
    /// <summary>Waiting, completed or failed; completed is not route success.</summary>
    public string Outcome { get; set; } = "waiting";
    /// <summary>Bounded terminal failure, retaining the normal read/poll evidence as well.</summary>
    public string? Error { get; set; }
}

/// <summary>One explicit-stage check against the unchanged150ms gate; pixels remain in the referenced poll, never in Pending.</summary>
internal sealed record NavigationBaselineInitialSourceCheck(int ObservationIndex, int PollIndex, double CheckedAtMs,
    double SourceAgeMs, string Disposition, string Stage = "after_capture");
