using System.Text.Json.Serialization;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Bounded ordinary-status identity; complete runtime, source and artifact proof stays in the dedicated result.</summary>
internal sealed record NavigationBaselineContinuationReference
{
    /// <summary>Explicit reference representation, distinct from the full version1 continuation link.</summary>
    [JsonPropertyName("version")] public int Version => 2;
    /// <summary>Exact immediate predecessor, atomically selected by the owner before this run starts.</summary>
    [JsonPropertyName("predecessorRunId")] public required string PredecessorRunId { get; init; }
    /// <summary>Fixed profile of that immediate predecessor; no recursive history is retained.</summary>
    [JsonPropertyName("predecessorProfileId")] public required string PredecessorProfileId { get; init; }
}
