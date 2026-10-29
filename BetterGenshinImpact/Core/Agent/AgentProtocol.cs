using System;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Versioned client request for the local, single-controller agent session.</summary>
public sealed record AgentRequest
{
    /// <summary>Wire protocol version.</summary>
    public int Version { get; init; } = 1;
    /// <summary>Operation: frame, action, status, release, configureDiagnostics, or stop.</summary>
    public string Command { get; init; } = string.Empty;
    /// <summary>Session capability returned by the initial hello.</summary>
    public string SessionId { get; init; } = string.Empty;
    /// <summary>Input lease identity; changes on every bridge invocation.</summary>
    public string OwnerEpoch { get; init; } = string.Empty;
    /// <summary>Current task instruction revision.</summary>
    public int GoalVersion { get; init; } = 1;
    /// <summary>Unique action identifier. Replays are rejected.</summary>
    public string RequestId { get; init; } = string.Empty;
    /// <summary>Recovery-only SHA-256 of the external original-visit failure and passive full-map proof.</summary>
    public string? PriorEvidenceSha256 { get; init; }
    /// <summary>Frame that the model actually consumed.</summary>
    public long FrameId { get; init; }
    /// <summary>Unmodified server monotonic capture timestamp from that frame.</summary>
    public double ObservedAtMs { get; init; }
    /// <summary>Hard execution deadline in the same server clock.</summary>
    public double ExpiresAtMs { get; init; }
    /// <summary>Optional exclusive first-input deadline in the server clock; omitted preserves legacy scheduling.</summary>
    public double? StartBeforeMs { get; init; }
    /// <summary>Checkpoint identifier retained in execution receipts.</summary>
    public string ModelId { get; init; } = string.Empty;
    /// <summary>Desired held states and one-shot relative movement for each interval.</summary>
    public AgentActionStep[] Steps { get; init; } = [];
    /// <summary>Explicit optional diagnostic opt-in, accepted only by configureDiagnostics.</summary>
    public bool? RecordReadinessTransitions { get; init; }
    /// <summary>V2 predecessor link: explicit null starts an idle chain; omission is never v2 admission.</summary>
    [JsonProperty(NullValueHandling = NullValueHandling.Include)]
    public JObject? QueueAfter { get => _queueAfter; init { _queueAfter = value; HasQueueAfter = true; } }
    /// <summary>Preserve absent versus explicit-null queue intent during deserialization and record copying.</summary>
    [JsonIgnore]
    internal bool HasQueueAfter { get; private init; }
    /// <summary>Legacy serialization never adds an omitted v2 field.</summary>
    public bool ShouldSerializeQueueAfter() => HasQueueAfter;
    /// <summary>Raw optional queue link, detached before admission.</summary>
    private JObject? _queueAfter;
    /// <summary>Unavailable v1 application binding envelope; omission preserves the legacy request.</summary>
    [JsonProperty(NullValueHandling = NullValueHandling.Include)]
    public JObject? StepApplication { get => _stepApplication; init { _stepApplication = value; HasStepApplicationEnvelope = true; } }
    /// <summary>Presence is distinct from JSON null, so unavailable features cannot fall through to legacy input.</summary>
    [JsonIgnore]
    internal bool HasStepApplicationEnvelope { get; private init; }
    /// <summary>Omitted legacy fields stay absent; an explicitly supplied null retains its rejection semantics.</summary>
    public bool ShouldSerializeStepApplication() => HasStepApplicationEnvelope;
    /// <summary>Extension value supplied during deserialization.</summary>
    private JObject? _stepApplication;
    /// <summary>Versioned cumulative application ACK and exact terminal ledger ACKs; never model publication.</summary>
    [JsonProperty(NullValueHandling = NullValueHandling.Include)]
    public JObject? StepApplicationsAck { get => _stepApplicationsAck; init { _stepApplicationsAck = value; HasStepApplicationsAck = true; } }
    /// <summary>A null ACK is malformed, not an absent opt-in field.</summary>
    [JsonIgnore]
    internal bool HasStepApplicationsAck { get; private init; }
    /// <summary>Omitted legacy fields stay absent; an explicitly supplied null retains its rejection semantics.</summary>
    public bool ShouldSerializeStepApplicationsAck() => HasStepApplicationsAck;
    /// <summary>Raw ACK before whole-envelope validation.</summary>
    private JObject? _stepApplicationsAck;
    /// <summary>Strictly parsed original wire object, retained only for the opted-in binding check.</summary>
    [JsonIgnore]
    internal JObject? RawApplicationRequest { get; init; }
}

/// <summary>One interval in an action chunk; movement is applied only on interval entry.</summary>
public sealed record AgentActionStep
{
    /// <summary>Interval length; 33 through 100 milliseconds.</summary>
    public int DurationMs { get; init; }
    /// <summary>Canonical keys/buttons desired held throughout the interval.</summary>
    public string[] Keys { get; init; } = [];
    /// <summary>Relative horizontal movement, in source-capture pixel-equivalent units.</summary>
    public int MouseDx { get; init; }
    /// <summary>Relative vertical movement, in source-capture pixel-equivalent units.</summary>
    public int MouseDy { get; init; }
}

/// <summary>Immutable observation metadata retained independently of image buffers.</summary>
/// <param name="FrameId">Server publication identity for this observation.</param>
/// <param name="CapturedAtMs">Host capture-request time, preserved for proposal identity compatibility.</param>
/// <param name="SourceWidth">Native capture width before stream downsampling.</param>
/// <param name="SourceHeight">Native capture height before stream downsampling.</param>
/// <param name="WorldEvidence">Visual evidence assessed from these exact pixels.</param>
/// <param name="RecognitionMs">Time spent assessing visual readiness.</param>
/// <param name="SourceFrame">Optional native source identity and reported/acquisition timing; null retains the host-time fallback.</param>
public sealed record AgentObservation(long FrameId, double CapturedAtMs, int SourceWidth, int SourceHeight,
    AgentWorldEvidence WorldEvidence = AgentWorldEvidence.Unknown, double RecognitionMs = 0, AgentSourceFrame? SourceFrame = null)
{
    /// <summary>Separate host evidence; omission preserves the existing WGC and unknown-backend wire shape.</summary>
    [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
    public AgentHostSnapshot? HostSnapshot { get; init; }
}

/// <summary>Template-only evidence from the exact image being published, never supplied by a client.</summary>
public enum AgentWorldEvidence
{
    /// <summary>No successful recognition has established a usable world image.</summary>
    Unknown,
    /// <summary>The world HUD is visible and no checked modal overlay is present.</summary>
    WorldHud,
    /// <summary>Menus, loading screens and cinematics normally lack the world HUD.</summary>
    HudMissing,
    /// <summary>A modal prompt blocks gameplay even if the HUD remains visible behind it.</summary>
    BlockingUi,
    /// <summary>Missing assets or a recognition failure must never authorize input.</summary>
    RecognitionFailed
}

/// <summary>Server-assessed input readiness with the exact source frame and monotonic timing.</summary>
/// <param name="Ready">Whether fresh visual evidence currently permits input.</param>
/// <param name="Reason">Stable machine-readable reason for the current decision.</param>
/// <param name="SourceFrameId">Publication identity of the evaluated observation.</param>
/// <param name="SourceCapturedAtMs">Host capture-request timestamp retained for compatibility.</param>
/// <param name="CheckedAtMs">Most recent evaluation or interruption time.</param>
/// <param name="RecognitionMs">Visual recognition duration for the evaluated observation.</param>
/// <param name="Epoch">Interruption generation used to discard pre-interruption proposals.</param>
/// <param name="SourceFrame">Actual source identity/timing when supplied by the capture backend.</param>
public sealed record AgentWorldReadiness(bool Ready, string Reason, long SourceFrameId,
    double SourceCapturedAtMs, double CheckedAtMs, double RecognitionMs, long Epoch, AgentSourceFrame? SourceFrame = null)
{
    /// <summary>Original host interval used for this decision, never relabeled as a WGC source.</summary>
    [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
    public AgentHostSnapshot? HostSnapshot { get; init; }
}

/// <summary>Acknowledgment of an input interval actually issued to the input backend.</summary>
public sealed record AgentAppliedStep(int Index, double StartedAtMs, string[] Keys, int MouseDx, int MouseDy);

/// <summary>Final execution result; accepted proposals are not mistaken for executed actions.</summary>
public sealed record AgentExecutionReceipt(string RequestId, string ModelId, long FrameId,
    string Status, string Reason, double AcceptedAtMs, double EndedAtMs, AgentAppliedStep[] AppliedSteps);

/// <summary>One observed software input call; stages never claim OS delivery or game acceptance.</summary>
/// <param name="CallId">Runtime-local call identity, shared by start and terminal stages.</param>
/// <param name="Operation">keyDown, keyUp, buttonDown, buttonUp, mouseMove, or releaseAll.</param>
/// <param name="Stage">started, returned, failed, returned_unverified, or skipped_backend_changed.</param>
/// <param name="Key">Normalized key/button when applicable.</param>
/// <param name="MouseDx">Requested relative horizontal delta, not measured motion.</param>
/// <param name="MouseDy">Requested relative vertical delta, not measured motion.</param>
/// <param name="Error">Exception type only, capped at 128 characters; null on a nonthrowing call.</param>
public sealed record AgentInputCall(long CallId, string Operation, string Stage, string? Key,
    int MouseDx, int MouseDy, string? Error);

/// <summary>Controller-bound call evidence in its original session clock.</summary>
/// <param name="Sequence">Strictly increasing retained-event identity.</param>
/// <param name="AtMs">Clock sampled under the controller lock; null means invalid telemetry clock.</param>
/// <param name="RequestId">Current request, or null for unbound lifecycle cleanup.</param>
/// <param name="ModelId">Current proposal model identity, not execution authority.</param>
/// <param name="FrameId">Current proposal's source frame identity.</param>
/// <param name="StepIndex">Last attempted step, including a partially failed dispatch.</param>
/// <param name="Origin">dispatch, release reason, or unbound lifecycle context.</param>
/// <param name="Call">Exact observed call stage.</param>
public sealed record AgentInputCallEvent(long Sequence, double? AtMs, string? RequestId, string? ModelId,
    long? FrameId, int? StepIndex, string Origin, AgentInputCall Call);

/// <summary>Runtime bookkeeping only; even a returned call does not establish physical held state.</summary>
/// <param name="HeldKeys">Normalized session-owned bookkeeping keys, detached from the mutable set.</param>
/// <param name="ExecutionUncertain">A call failure, aggregate release, or telemetry failure prevents exact reconstruction.</param>
/// <param name="ReleaseOutcome">Last aggregate release result; returned_unverified is not per-key success.</param>
/// <param name="TelemetryIncomplete">An observer failure or counter overflow occurred.</param>
public sealed record AgentTrackedInputState(string[] HeldKeys, bool ExecutionUncertain,
    string ReleaseOutcome, bool TelemetryIncomplete);

/// <summary>Current scheduler intention, separate from the runtime's tracked holds.</summary>
/// <param name="RequestId">Active request identity.</param>
/// <param name="ModelId">Active proposal model identity.</param>
/// <param name="FrameId">Active proposal frame identity.</param>
/// <param name="AcceptedAtMs">Original admission clock, unchanged by telemetry.</param>
/// <param name="ExpiresAtMs">Original hard expiry.</param>
/// <param name="StartBeforeMs">Original optional first-input deadline.</param>
/// <param name="NextStepAtMs">Original scheduler boundary.</param>
/// <param name="NextStepIndex">Next interval index; may equal the interval count while awaiting closure.</param>
/// <param name="LastAttemptedStepIndex">Most recent attempt, including a failed backend call.</param>
/// <param name="LastDispatchOutcome">not_started, started, returned, or failed; returned is software-call completion only.</param>
/// <param name="NextIntendedKeys">Next requested keys, or null when no next interval remains.</param>
/// <param name="LastAppliedKeys">Last fully returned legacy applied step, or null if none.</param>
public sealed record AgentActiveInputContext(string RequestId, string ModelId, long FrameId,
    double AcceptedAtMs, double ExpiresAtMs, double? StartBeforeMs, double NextStepAtMs,
    int NextStepIndex, int? LastAttemptedStepIndex, string LastDispatchOutcome, string[]? NextIntendedKeys, string[]? LastAppliedKeys);

/// <summary>Detached publication-time context; image acquisition and game effect remain separate.</summary>
/// <param name="SampledAtMs">Session clock sampled after acquiring the input lock.</param>
/// <param name="TelemetryComplete">False if timing, state observation, or event recording failed.</param>
/// <param name="TrackedState">Software bookkeeping and explicit uncertainty.</param>
/// <param name="Active">Current request intention, or null after terminal cleanup.</param>
/// <param name="LastInputEvent">Last observed call origin, retained even when active ownership changes.</param>
/// <param name="FirstSequence">Oldest retained event, or zero for an empty ledger.</param>
/// <param name="LastSequence">Most recently allocated event sequence.</param>
/// <param name="EvictedEvents">Cumulative retention eviction count, not consumer delivery loss.</param>
/// <param name="Events">Bounded retained ring; repeated snapshots may repeat sequences.</param>
public sealed record AgentExecutionContext(double? SampledAtMs, bool TelemetryComplete,
    AgentTrackedInputState TrackedState, AgentActiveInputContext? Active, AgentInputCallEvent? LastInputEvent,
    long FirstSequence, long LastSequence, long EvictedEvents, AgentInputCallEvent[] Events)
{
    /// <summary>Additive telemetry contract version.</summary>
    public int Version => 1;
    /// <summary>Same server clock as legacy receipts; not a game-render or client clock.</summary>
    public string Clock => "monotonic milliseconds since session start";
    /// <summary>Backend calls are serialized under the controller lock, so a blocked call prevents concurrent snapshots.</summary>
    public bool ObservesBlockedCallConcurrently => false;
    /// <summary>No software telemetry field establishes physical input or game consumption.</summary>
    public bool PhysicalExecutionProven => false;
}

/// <summary>Input boundary used by the scheduler and by deterministic tests without a game.</summary>
public interface IAgentInput
{
    /// <summary>Whether this bound runtime still owns an operable game window.</summary>
    bool IsAvailable { get; }
    /// <summary>Apply transitions to the requested held state.</summary>
    void SetHeldKeys(string[] keys);
    /// <summary>Issue one relative movement.</summary>
    void MoveMouse(int dx, int dy);
    /// <summary>Release every input owned by this session.</summary>
    void ReleaseAll();
}
