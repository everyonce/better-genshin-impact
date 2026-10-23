using System;

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
    /// <summary>Frame that the model actually consumed.</summary>
    public long FrameId { get; init; }
    /// <summary>Unmodified server monotonic capture timestamp from that frame.</summary>
    public double ObservedAtMs { get; init; }
    /// <summary>Hard execution deadline in the same server clock.</summary>
    public double ExpiresAtMs { get; init; }
    /// <summary>Checkpoint identifier retained in execution receipts.</summary>
    public string ModelId { get; init; } = string.Empty;
    /// <summary>Desired held states and one-shot relative movement for each interval.</summary>
    public AgentActionStep[] Steps { get; init; } = [];
    /// <summary>Explicit optional diagnostic opt-in, accepted only by configureDiagnostics.</summary>
    public bool? RecordReadinessTransitions { get; init; }
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
public sealed record AgentObservation(long FrameId, double CapturedAtMs, int SourceWidth, int SourceHeight,
    AgentWorldEvidence WorldEvidence = AgentWorldEvidence.Unknown, double RecognitionMs = 0);

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
public sealed record AgentWorldReadiness(bool Ready, string Reason, long SourceFrameId,
    double SourceCapturedAtMs, double CheckedAtMs, double RecognitionMs, long Epoch);

/// <summary>Acknowledgment of an input interval actually issued to the input backend.</summary>
public sealed record AgentAppliedStep(int Index, double StartedAtMs, string[] Keys, int MouseDx, int MouseDy);

/// <summary>Final execution result; accepted proposals are not mistaken for executed actions.</summary>
public sealed record AgentExecutionReceipt(string RequestId, string ModelId, long FrameId,
    string Status, string Reason, double AcceptedAtMs, double EndedAtMs, AgentAppliedStep[] AppliedSteps);

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
