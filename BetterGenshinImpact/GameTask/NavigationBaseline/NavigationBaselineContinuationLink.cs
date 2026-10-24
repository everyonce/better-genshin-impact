using System;
using System.Text.Json.Serialization;
using System.Linq;
using BetterGenshinImpact.Core.Capture;
using Fischless.GameCapture.DesktopDc;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Owner-created immutable evidence linking exactly one explicit run to its opposite-direction local predecessor.</summary>
internal sealed record NavigationBaselineContinuationLink
{
    /// <summary>Separate linkage version; geometry and final-readiness policies are unchanged.</summary>
    [JsonPropertyName("version")] public int Version => PredecessorFinalSource.HostSnapshot is null ? 1 : 2;
    /// <summary>Exact retained owner run, never arbitrary supplied result JSON.</summary>
    [JsonPropertyName("predecessorRunId")] public required string PredecessorRunId { get; init; }
    /// <summary>Exact owner-retained predecessor profile; the default preserves existing ordinary-forward links.</summary>
    [JsonPropertyName("predecessorProfileId")] public string PredecessorProfileId { get; init; } = NavigationBaselineRouteProfile.TwoLegId;
    /// <summary>Hashes refer to existing predecessor files, checked again before this task may read or send input.</summary>
    [JsonPropertyName("predecessorEvidence")] public required NavigationBaselineEvidence PredecessorEvidence { get; init; }
    /// <summary>Last of the predecessor's three final samples; it is a floor, never a pose for a new decision.</summary>
    [JsonPropertyName("predecessorFinalSource")] public required CaptureSourceEvidence PredecessorFinalSource { get; init; }
    /// <summary>Original callback including native disposal and TaskRunner return finished before this tick.</summary>
    [JsonPropertyName("predecessorCleanupReturnedAtTicks")] public required long PredecessorCleanupReturnedAtTicks { get; init; }
    /// <summary>Owner-generated identity for the exact retained runtime reference.</summary>
    [JsonPropertyName("runtimeIdentity")] public required Guid RuntimeIdentity { get; init; }
    /// <summary>Authenticated child service identity, not a caller-selected process.</summary>
    [JsonPropertyName("childProcessId")] public required int ChildProcessId { get; init; }
    /// <summary>Authenticated child service nonce prevents process/service substitution.</summary>
    [JsonPropertyName("childNonce")] public required string ChildNonce { get; init; }
    /// <summary>Same child/game Windows session.</summary>
    [JsonPropertyName("windowsSessionId")] public required int WindowsSessionId { get; init; }
    /// <summary>Current game PID paired with its process creation time.</summary>
    [JsonPropertyName("gameProcessId")] public required int GameProcessId { get; init; }
    /// <summary>PID reuse cannot match this process-start identity.</summary>
    [JsonPropertyName("gameStartedAtUtcTicks")] public required long GameStartedAtUtcTicks { get; init; }
    /// <summary>Exact backend implementation, also checked by object reference inside the owner.</summary>
    [JsonPropertyName("captureType")] public required string CaptureType { get; init; }
    /// <summary>Effective Start-fixed backend mode from both runs, not merely configuration.</summary>
    [JsonPropertyName("readbackMode")] public required string? ReadbackMode { get; init; }
    /// <summary>Host-only selected authority; omitted from unchanged WGC links.</summary>
    [JsonPropertyName("sourcePolicy"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SourcePolicy { get; init; }
    /// <summary>Cached service assembly identity, joined separately to the package and source proof.</summary>
    [JsonPropertyName("childAssemblySha256"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ChildAssemblySha256 { get; init; }
    /// <summary>Only well-formed immutable host proof may cross the native continuation boundary.</summary>
    [JsonIgnore] internal bool HasHostSourceContract => Version == 2
        && SourcePolicy == DesktopCapturePolicy.HostAcquisitionV1 && ReadbackMode is null
        && CaptureType == typeof(DesktopDcCapture).FullName && IsAssemblyHash(ChildAssemblySha256)
        && PredecessorEvidence.SourcePolicy == SourcePolicy && PredecessorEvidence.ReadbackMode is null
        && PredecessorEvidence.ShadowCapture is null;
    /// <summary>Assembly hashes are exact hexadecimal identities; comparison may normalize their case.</summary>
    internal static bool IsAssemblyHash(string? hash) => hash is { Length: 64 } && hash.All(char.IsAsciiHexDigit);
    /// <summary>Explicitly does not turn method cleanup into physical release or game acknowledgement.</summary>
    [JsonPropertyName("physicalInputAcknowledged")] public bool PhysicalInputAcknowledged => false;
}
