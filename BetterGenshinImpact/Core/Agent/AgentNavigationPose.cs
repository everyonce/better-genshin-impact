using System;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Read-only native localization from the exact stream image; it never grants input authority.</summary>
/// <param name="State">Valid or unavailable, independently of the world/input gate.</param>
/// <param name="Reason">Bounded diagnostic explaining unavailable evidence.</param>
/// <param name="FrameId">The same observation identity carried by the RGB payload.</param>
/// <param name="X">Measured world map X coordinate.</param>
/// <param name="Y">Measured world map Y coordinate.</param>
/// <param name="YawDegrees">Measured camera heading, not inferred character velocity.</param>
/// <param name="PositionConfidence">Confidence from this successful rank-zero local match.</param>
/// <param name="YawConfidence">Confidence from this image's minimap preprocessing.</param>
/// <param name="LayerId">The matched map layer.</param>
/// <param name="HeadingToStartDegrees">Native bearing to the fixed courtyard start.</param>
/// <param name="HeadingToEndDegrees">Native bearing to the fixed courtyard end.</param>
/// <param name="MouseToStart">Horizontal correction calculated by BetterGI's existing camera controller.</param>
/// <param name="MouseToEnd">Horizontal correction calculated by BetterGI's existing camera controller.</param>
/// <param name="RecognitionMs">Native pose recognition time, separate from source age.</param>
public sealed record AgentNavigationPose(string State, string? Reason, long FrameId,
    double? X, double? Y, double? YawDegrees, double? PositionConfidence, double? YawConfidence,
    string? LayerId, double? HeadingToStartDegrees, double? HeadingToEndDegrees,
    int? MouseToStart, int? MouseToEnd, double RecognitionMs)
{
    /// <summary>Unavailable evidence has no reusable coordinate or camera values.</summary>
    public static AgentNavigationPose Unavailable(long frameId, string reason, double recognitionMs = 0) =>
        new("unavailable", reason, frameId, null, null, null, null, null, null, null, null, null, null, recognitionMs);

    /// <summary>Keep the strict confidence rules and apply only the explicitly selected localization scope.</summary>
    internal static bool IsQualified(double x, double y, double yaw, double positionConfidence,
        double yawConfidence, string? layerId, string? profileId = null) => double.IsFinite(x) && double.IsFinite(y)
        && double.IsFinite(yaw) && yaw is >= 0 and < 360
        && double.IsFinite(positionConfidence) && positionConfidence is >= .99 and <= 1
        && double.IsFinite(yawConfidence) && yawConfidence is >= .2 and <= 1
        && AgentNavigationProfile.AllowsPosition(profileId, x, y, layerId);
}
