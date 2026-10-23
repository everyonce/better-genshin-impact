using Newtonsoft.Json;
using Newtonsoft.Json.Converters;
using System.Runtime.Serialization;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Observed keyboard-hint pattern, not physical velocity, safe footing, or a grounded-state guarantee.</summary>
[JsonConverter(typeof(StringEnumConverter))]
public enum AgentMotionStatus
{
    /// <summary>No usable world frame or successful recognition is available.</summary>
    [EnumMember(Value = "unknown")] Unknown,
    /// <summary>The Space hint was not detected; this is the existing recognizer's negative fallback.</summary>
    [EnumMember(Value = "normal")] Normal,
    /// <summary>Both Space and X hints were detected in the existing key-tip region.</summary>
    [EnumMember(Value = "climb")] Climb,
    /// <summary>The Space hint was detected without X.</summary>
    [EnumMember(Value = "fly")] Fly
}

/// <summary>Immutable, same-frame motion evidence; it never grants input authority or replaces world readiness.</summary>
/// <param name="Status">Hint classification; normal does not prove the character is grounded.</param>
/// <param name="Reason">Stable recognition or unavailability reason.</param>
/// <param name="Method">Versioned evidence method.</param>
/// <param name="RecognitionMs">Recognition duration, separate from source and capture timestamps.</param>
/// <param name="SpaceKeyMatched">Space template result; null when recognition was unavailable.</param>
/// <param name="XKeyMatched">X template result; null when recognition was unavailable.</param>
public sealed record AgentMotionEvidence(AgentMotionStatus Status, string Reason, string Method,
    double RecognitionMs, bool? SpaceKeyMatched, bool? XKeyMatched)
{
    /// <summary>Existing template assets, ROI and thresholds; no OCR or additional capture.</summary>
    public const string MethodName = "native_key_tip_templates_v1";

    /// <summary>Unavailable evidence cannot inherit a previous frame's successful classification.</summary>
    public static AgentMotionEvidence Unavailable(string reason, double recognitionMs = 0) =>
        new(AgentMotionStatus.Unknown, reason, MethodName, recognitionMs, null, null);
}
