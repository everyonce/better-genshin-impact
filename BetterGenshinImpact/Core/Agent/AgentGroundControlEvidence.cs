using System;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Small exact native RGB crops retained inline; they never claim physical footing or input authority.</summary>
public sealed record AgentControlCrop(int X, int Y, int Width, int Height, string Format, string RgbBase64, string Sha256);

/// <summary>Bounded keycap geometry and separately distinguishable dark-glyph/light-background matches.</summary>
public sealed record AgentKeycapEvidence(bool Matched, int X, int Y, int Width, int Height,
    int DarkMatches, int DarkExpected, int LightMatches, int LightExpected);

/// <summary>Versioned same-source control layout; normal motion alone remains insufficient evidence.</summary>
public sealed record AgentGroundControlEvidence(string State, string Reason, long FrameId, AgentSourceFrame? SourceFrame,
    int SourceWidth, int SourceHeight, bool GroundControlsConfirmed, int SwimHintPixels,
    bool? SpaceKeyMatched, bool? XKeyMatched, AgentKeycapEvidence? EKey, AgentKeycapEvidence? QKey,
    AgentControlCrop[] Crops, double RecognitionMs)
{
    /// <summary>The first contract is deliberately restricted to the inspected 1920 by 1080 RDP layout.</summary>
    public const string MethodName = "native_ground_control_layout_v1";
    /// <summary>Independent contract version; existing motion v1 is not reinterpreted.</summary>
    public int Version => 1;
    /// <summary>Stable pixel method identifier.</summary>
    public string Method => MethodName;
    /// <summary>Recognition alone cannot grant a lease or send an input.</summary>
    public bool AuthorizesInput => false;
    /// <summary>Visible ground controls do not establish dry terrain, collision geometry or physical footing.</summary>
    public bool PhysicallyGrounded => false;
    /// <summary>Keep unavailable observations explicit without retaining invented positive measurements.</summary>
    public static AgentGroundControlEvidence Unavailable(AgentObservation observation, string reason, double elapsedMs = 0) =>
        new("unavailable", reason, observation.FrameId, observation.SourceFrame, observation.SourceWidth,
            observation.SourceHeight, false, 0, null, null, null, null, [], elapsedMs);
    /// <summary>Only the exact native observation and positive complete layout may satisfy the optional controller gate.</summary>
    public bool Admits(AgentObservation observation) => State == "valid" && GroundControlsConfirmed &&
        FrameId == observation.FrameId && SourceFrame is not null && SourceFrame == observation.SourceFrame &&
        SourceWidth == 1920 && SourceHeight == 1080 && SourceWidth == observation.SourceWidth &&
        SourceHeight == observation.SourceHeight && SwimHintPixels < 4 && SpaceKeyMatched == false &&
        XKeyMatched == false && EKey?.Matched == true && QKey?.Matched == true;
}
