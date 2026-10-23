using System;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Versioned client request for the local, single-controller agent session.</summary>
public sealed record AgentRequest
{
    /// <summary>Wire protocol version.</summary>
    public int Version { get; init; } = 1;
    /// <summary>Operation: frame, action, status, or stop.</summary>
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
public sealed record AgentObservation(long FrameId, double CapturedAtMs, int SourceWidth, int SourceHeight);

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
