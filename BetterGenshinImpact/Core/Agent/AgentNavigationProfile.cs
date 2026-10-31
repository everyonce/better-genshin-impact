namespace BetterGenshinImpact.Core.Agent;

/// <summary>Named, read-only localization scopes; none grants movement or changes confidence thresholds.</summary>
public static class AgentNavigationProfile
{
    /// <summary>The original city-only guidance contract, retained as the default.</summary>
    public const string Courtyard = "mondstadt-courtyard-hybrid-v1";
    /// <summary>Explicit scope for surveying the city gate, bridge and nearby surface.</summary>
    public const string MondstadtSurface = "mondstadt-surface-hybrid-v1";
    /// <summary>Western world-coordinate limit inside the original anchor's local search area.</summary>
    public const double MinimumX = -1100;
    /// <summary>Eastern world-coordinate limit inside the original anchor's local search area.</summary>
    public const double MaximumX = -820;
    /// <summary>Southern world-coordinate limit inside the original anchor's local search area.</summary>
    public const double MinimumY = 2100;
    /// <summary>Northern world-coordinate limit inside the original anchor's local search area.</summary>
    public const double MaximumY = 2350;

    /// <summary>Omission preserves the original contract; arbitrary scope names are never accepted.</summary>
    public static bool IsSupported(string? profileId) => profileId is null or Courtyard or MondstadtSurface;

    /// <summary>Constrain the named layer and location independently of the numerical confidence checks.</summary>
    public static bool AllowsPosition(string? profileId, double x, double y, string? layerId) => profileId switch
    {
        null or Courtyard => layerId == "City_102",
        MondstadtSurface => layerId is "City_102" or "MapBack_2"
            && x is >= MinimumX and <= MaximumX && y is >= MinimumY and <= MaximumY,
        _ => false
    };
}
