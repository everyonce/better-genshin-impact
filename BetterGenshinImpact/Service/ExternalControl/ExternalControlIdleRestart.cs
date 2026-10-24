using System.Text.Json.Serialization;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Request-bound target for the atomic idle-only restart capability; never accepts arbitrary executables.</summary>
internal sealed record ExternalControlIdleRestart
{
    /// <summary>Version one reserves task/runtime admission and binds all target fields to the staged manifest.</summary>
    [JsonPropertyName("version")]
    public int Version { get; init; }

    /// <summary>Exact sibling numbered portable installation selected by the caller.</summary>
    [JsonPropertyName("targetDirectory")]
    public string? TargetDirectory { get; init; }

    /// <summary>Expected SHA256 of the fixed BetterGI.exe in that installation.</summary>
    [JsonPropertyName("exeSha256")]
    public string? ExeSha256 { get; init; }

    /// <summary>Expected SHA256 of the fixed BetterGI.dll in that installation.</summary>
    [JsonPropertyName("dllSha256")]
    public string? DllSha256 { get; init; }
}
