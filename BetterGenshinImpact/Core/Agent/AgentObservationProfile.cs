using System;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Fixed stream-lifetime image contracts; native P2P preprocessing is explicitly opt-in.</summary>
public static class AgentObservationProfile
{
    /// <summary>Existing aspect-preserving Area downsample, capped at 640x360, then RGB24.</summary>
    public const string Legacy = "legacy-area-640x360-v1";

    /// <summary>Direct native pixels to RGB192 using the Rust-verified FIR5.1.4 Hamming operation.</summary>
    public const string P2PNativeHamming192 = "p2p-native-hamming-192-v1";

    /// <summary>Omission means legacy; spelling/case must otherwise match the exact wire contract.</summary>
    public static bool IsSupported(string? profile) => profile is null or Legacy or P2PNativeHamming192;

    /// <summary>Normalize legacy omission and reject unknown preprocessing before starting a task.</summary>
    public static string Normalize(string? profile) => IsSupported(profile) ? profile ?? Legacy
        : throw new ArgumentException("Unsupported agent observation profile.", nameof(profile));

    /// <summary>Declare color, geometric and source provenance independently of model normalization.</summary>
    public static object Describe(string profile) => new
    {
        source = "native_capture",
        resize = Normalize(profile) == P2PNativeHamming192 ? "fir-5.1.4-interpolation-hamming" : "opencv-area-cap",
        pixelFormat = "rgb24",
        preserveAspectRatio = profile != P2PNativeHamming192,
        normalization = "none-rgb-uint8"
    };
}
