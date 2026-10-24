using System;

namespace BetterGenshinImpact.Core.Capture;

/// <summary>Exact opt-in authority choices for host-acquired desktop pixels; neither measures render time.</summary>
public static class DesktopCapturePolicy
{
    /// <summary>Default desktop capture supplies observations without controller input authority.</summary>
    public const string ObserveOnly = "observe-only";

    /// <summary>Explicit controller policy uses the beginning of a validated host acquisition interval.</summary>
    public const string HostAcquisitionV1 = "host-acquisition-v1";

    /// <summary>Reject unknown and explicitly null choices before runtime ownership changes.</summary>
    public static string Validate(string? value) => value is ObserveOnly or HostAcquisitionV1
        ? value : throw new ArgumentOutOfRangeException(nameof(value), "Unknown desktop capture source policy.");
}
