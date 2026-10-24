using System.Text.Json.Serialization;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Compact archive outcome, independent of measured navigation success and never input authority.</summary>
internal sealed record NavigationBaselineShadowEvidence(
    [property: JsonPropertyName("mode")] string Mode,
    [property: JsonPropertyName("complete")] bool Complete,
    [property: JsonPropertyName("workerRetired")] bool WorkerRetired,
    [property: JsonPropertyName("error")] string? Error,
    [property: JsonPropertyName("framesSeen")] int FramesSeen,
    [property: JsonPropertyName("framesAccepted")] int FramesAccepted,
    [property: JsonPropertyName("framesWritten")] int FramesWritten,
    [property: JsonPropertyName("duplicateFrames")] int DuplicateFrames,
    [property: JsonPropertyName("framesRejected")] int FramesRejected,
    [property: JsonPropertyName("offersIgnoredAfterStop")] int OffersIgnoredAfterStop,
    [property: JsonPropertyName("framesLost")] int FramesLost,
    [property: JsonPropertyName("manifestPath")] string? ManifestPath,
    [property: JsonPropertyName("manifestSha256")] string? ManifestSha256,
    [property: JsonPropertyName("nativeJournalSha256")] string? NativeJournalSha256);
