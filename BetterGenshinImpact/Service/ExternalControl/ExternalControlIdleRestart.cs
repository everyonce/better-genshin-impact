using System.Text.Json.Serialization;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Request-bound target for the atomic idle-only restart capability; never accepts arbitrary executables.</summary>
internal sealed record ExternalControlIdleRestart
{
    /// <summary>Start only the authenticated BetterGI control endpoint after replacement.</summary>
    internal const string ControlEndpoint = "controlEndpoint";

    /// <summary>Attach or launch the configured game after replacement, retaining the original restart behavior.</summary>
    internal const string GameRuntime = "gameRuntime";

    /// <summary>Version one reserves admission and binds target pins; version two also requires explicit startup intent.</summary>
    [JsonPropertyName("version")]
    public int Version { get; init; }

    /// <summary>Version-two startup intent, covered by the request fingerprint; absent for legacy version one.</summary>
    [JsonPropertyName("startupMode")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? StartupMode { get; init; }

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
