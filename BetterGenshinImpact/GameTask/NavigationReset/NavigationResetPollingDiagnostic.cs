using System.Diagnostics;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>Bounded log-only ledger for opt-in metadata polling; it contains no pixels or readiness authority.</summary>
internal sealed record NavigationResetPollingDiagnostic
{
    /// <summary>New ledger semantics are explicit; old reset source logs keep their previous versions.</summary>
    public int Version => 1;
    /// <summary>Only the explicit PollSingleV1 reset path produces this accounting.</summary>
    public string Method => "reset-poll-single-readiness-v1";
    /// <summary>Frequency applies only to the recorded local QPC values.</summary>
    public long ClockFrequency => Stopwatch.Frequency;
    /// <summary>Original entry and fixed three-second deadline; neither is reset by Pending.</summary>
    public long StartedAtTicks { get; init; }
    /// <summary>Original monotonic window deadline; the linked owner can expire sooner.</summary>
    public long DeadlineAtTicks { get; init; }
    /// <summary>Last actual budget check, not a substituted source-age timestamp.</summary>
    public long LastCheckedAtTicks { get; init; }
    /// <summary>Finally entry after probe settlement; null while this snapshot is in progress.</summary>
    public long? EndedAtTicks { get; init; }
    /// <summary>Native-call reservations, including conservative pre-call setup failures.</summary>
    public int PollCount { get; init; }
    /// <summary>Ready/error charges plus any outstanding provisional charge; at most25.</summary>
    public int ChargedObservations { get; init; }
    /// <summary>Only typed, validated metadata-only returns can increment this counter; at most400.</summary>
    public int ValidatedPendingPolls { get; init; }
    /// <summary>True means a conservative charge has not settled; never claim a completed native call.</summary>
    public bool ReservationOutstanding { get; init; }
    /// <summary>Window status is distinct from a source check, pose or overall reset success.</summary>
    public string Outcome { get; init; } = "active";
    /// <summary>At most200 characters; preserved exceptions remain authoritative.</summary>
    public string? Error { get; init; }
    /// <summary>Number of entered waits, including one cancelled or failed wait.</summary>
    public int WaitCount { get; init; }
    /// <summary>Only the last requested interval is retained, without growing per-poll history.</summary>
    public int? LastWaitRequestedMilliseconds { get; init; }
    /// <summary>Host interval start; not GPU readiness or kernel signal time.</summary>
    public long? LastWaitStartedAtTicks { get; init; }
    /// <summary>Host continuation/finally time, including a wait that threw.</summary>
    public long? LastWaitExitedAtTicks { get; init; }
    /// <summary>Sum of observed nonnegative host wait intervals.</summary>
    public double ObservedWaitSumMilliseconds { get; init; }
    /// <summary>Largest observed host wait interval; OS scheduling can exceed its request.</summary>
    public double ObservedWaitMaximumMilliseconds { get; init; }
    /// <summary>Entered5ms waits, including cancelled/failed waits; a count is not proof of successful timer completion.</summary>
    public int PendingWaitCount { get; init; }
    /// <summary>Sum of measured host intervals for requested5ms metadata waits only.</summary>
    public double PendingWaitSumMilliseconds { get; init; }
    /// <summary>Largest measured host interval for requested5ms metadata waits only.</summary>
    public double PendingWaitMaximumMilliseconds { get; init; }
    /// <summary>Entered unchanged120ms waits for actual observation misses.</summary>
    public int ObservationWaitCount { get; init; }
    /// <summary>Sum of measured host intervals for actual-observation settling.</summary>
    public double ObservationWaitSumMilliseconds { get; init; }
    /// <summary>Largest measured host interval for actual-observation settling.</summary>
    public double ObservationWaitMaximumMilliseconds { get; init; }
}
