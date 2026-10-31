using System;
using System.Collections.Generic;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Native HUD color evidence from one exact source image; no field grants input authority.</summary>
/// <param name="State">Valid analysis or unavailable evidence.</param>
/// <param name="Reason">Bounded explanation of the analysis state.</param>
/// <param name="FrameId">The observation carrying these same pixels.</param>
/// <param name="SourceFrame">The immutable WGC identity, including its original freshness anchor.</param>
/// <param name="SourceWidth">Native image width before policy resizing.</param>
/// <param name="SourceHeight">Native image height before policy resizing.</param>
/// <param name="PlayerHealthColor">Green, red, or unknown at the fixed native HUD bar.</param>
/// <param name="PlayerHealthFractionEstimate">Visible fill extent, not OCR or an exact numerical HP value.</param>
/// <param name="PlayerHealthMatchingPixels">Pixels matching the selected HUD color along the inspected row.</param>
/// <param name="EnemyBarCandidates">Red horizontal components; these do not identify an enemy.</param>
/// <param name="RedMaskOverloaded">Excess color or components makes target selection ambiguous.</param>
/// <param name="RecognitionMs">Time spent analyzing this image.</param>
public sealed record AgentCombatEvidence(string State, string Reason, long FrameId, AgentSourceFrame? SourceFrame,
    int SourceWidth, int SourceHeight, string PlayerHealthColor, double? PlayerHealthFractionEstimate,
    int PlayerHealthMatchingPixels, IReadOnlyList<AgentEnemyBarCandidate> EnemyBarCandidates,
    bool RedMaskOverloaded, double RecognitionMs)
{
    /// <summary>Versioned image-analysis contract, independent of policy choice.</summary>
    public const string MethodName = "native_hud_color_components_v1";
    /// <summary>Schema version for the optional evidence block.</summary>
    public int Version => 1;
    /// <summary>The fixed analysis method used by this observation.</summary>
    public string Method => MethodName;
    /// <summary>Visual candidates never authorize controls.</summary>
    public bool AuthorizesInput => false;
    /// <summary>Color components alone cannot prove a hostile identity.</summary>
    public bool EnemyIdentityVerified => false;
    /// <summary>A missing bar cannot establish a defeated enemy.</summary>
    public bool KillVerified => false;

    /// <summary>Clear all usable HUD values when the current source cannot be analyzed.</summary>
    public static AgentCombatEvidence Unavailable(AgentObservation observation, string reason, double elapsedMs = 0) =>
        new("unavailable", reason, observation.FrameId, observation.SourceFrame, observation.SourceWidth,
            observation.SourceHeight, "unknown", null, 0, Array.Empty<AgentEnemyBarCandidate>(), false, elapsedMs);
}

/// <summary>One red horizontal component in native capture coordinates, with no target identity claim.</summary>
/// <param name="X">Left native-image coordinate.</param>
/// <param name="Y">Top native-image coordinate.</param>
/// <param name="Width">Component width in native pixels.</param>
/// <param name="Height">Component height in native pixels.</param>
/// <param name="Pixels">Number of matching red pixels in the connected component.</param>
public sealed record AgentEnemyBarCandidate(int X, int Y, int Width, int Height, int Pixels);
