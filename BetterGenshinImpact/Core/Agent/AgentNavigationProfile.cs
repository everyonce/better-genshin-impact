namespace BetterGenshinImpact.Core.Agent;

/// <summary>Named, read-only localization scopes; none grants movement or changes confidence thresholds.</summary>
public static class AgentNavigationProfile
{
    /// <summary>The original city-only guidance contract, retained as the default.</summary>
    public const string Courtyard = "mondstadt-courtyard-hybrid-v1";
    /// <summary>Explicit scope for surveying the city gate, bridge and nearby surface.</summary>
    public const string MondstadtSurface = "mondstadt-surface-hybrid-v1";
    /// <summary>Explicit local scope for approaching encounters east of the surveyed bridge.</summary>
    public const string MondstadtCombatScout = "mondstadt-combat-scout-v1";
    /// <summary>Separate read-only local scope from the camp through the northern Statue and tracked encounter area.</summary>
    public const string MondstadtNorthCombatScout = "mondstadt-north-combat-scout-v1";
    /// <summary>Separate read-only perception scope around the Windrise Statue and its verified teleport spawn.</summary>
    public const string WindriseStatueRecovery = "windrise-statue-recovery-v1";
    /// <summary>Minimum numeric world X inside the original anchor's local search area.</summary>
    public const double MinimumX = -1100;
    /// <summary>Maximum numeric world X inside the original anchor's local search area.</summary>
    public const double MaximumX = -820;
    /// <summary>Southern world-coordinate limit inside the original anchor's local search area.</summary>
    public const double MinimumY = 2100;
    /// <summary>Northern world-coordinate limit inside the original anchor's local search area.</summary>
    public const double MaximumY = 2350;
    /// <summary>Minimum numeric X of the separately selected combat-scouting area.</summary>
    public const double ScoutMinimumX = -1350;
    /// <summary>Maximum numeric X retains an overlap with the verified bridge approach.</summary>
    public const double ScoutMaximumX = -980;
    /// <summary>Southern numerical limit of the local scouting area.</summary>
    public const double ScoutMinimumY = 2050;
    /// <summary>Northern numerical limit of the local scouting area.</summary>
    public const double ScoutMaximumY = 2480;
    /// <summary>Fixed local search center; callers cannot provide an arbitrary matching anchor.</summary>
    public const double ScoutAnchorX = -1165;
    /// <summary>Fixed local search center keeps the new area within the existing local matcher radius.</summary>
    public const double ScoutAnchorY = 2265;
    /// <summary>Minimum numeric X of the northern scouting rectangle, translated by -150.</summary>
    public const double NorthScoutMinimumX = -1500;
    /// <summary>Maximum numeric X of the northern scouting rectangle, translated by -150.</summary>
    public const double NorthScoutMaximumX = -1130;
    /// <summary>Southern numerical limit of the northern scouting rectangle, translated by +380.</summary>
    public const double NorthScoutMinimumY = 2430;
    /// <summary>Northern numerical limit of the northern scouting rectangle, translated by +380.</summary>
    public const double NorthScoutMaximumY = 2860;
    /// <summary>Fixed northern search center preserves the original scouting rectangle's local matching radius.</summary>
    public const double NorthScoutAnchorX = -1315;
    /// <summary>Fixed northern search center is selected by profile, never supplied by the caller.</summary>
    public const double NorthScoutAnchorY = 2645;
    /// <summary>Western numerical edge of the tightly bounded Windrise Statue area.</summary>
    public const double WindriseMinimumX = -1272;
    /// <summary>Eastern numerical edge of the tightly bounded Windrise Statue area.</summary>
    public const double WindriseMaximumX = -1260;
    /// <summary>Southern numerical edge enclosing the Statue and verified spawn only.</summary>
    public const double WindriseMinimumY = 1922;
    /// <summary>Northern numerical edge enclosing the Statue and verified spawn only.</summary>
    public const double WindriseMaximumY = 1940;
    /// <summary>Fixed local matching anchor; callers cannot supply another center.</summary>
    public const double WindriseAnchorX = -1266;
    /// <summary>Fixed local matching anchor between the Statue and verified spawn.</summary>
    public const double WindriseAnchorY = 1931;

    /// <summary>Omission preserves the original contract; arbitrary scope names are never accepted.</summary>
    public static bool IsSupported(string? profileId) => profileId is null or Courtyard or MondstadtSurface
        or MondstadtCombatScout or MondstadtNorthCombatScout or WindriseStatueRecovery;

    /// <summary>Constrain the named layer and location independently of the numerical confidence checks.</summary>
    public static bool AllowsPosition(string? profileId, double x, double y, string? layerId) => profileId switch
    {
        null or Courtyard => layerId == "City_102",
        MondstadtSurface => layerId is "City_102" or "MapBack_2"
            && x is >= MinimumX and <= MaximumX && y is >= MinimumY and <= MaximumY,
        MondstadtCombatScout => layerId is "City_102" or "MapBack_2"
            && x is >= ScoutMinimumX and <= ScoutMaximumX && y is >= ScoutMinimumY and <= ScoutMaximumY,
        MondstadtNorthCombatScout => layerId is "City_102" or "MapBack_2"
            && x is >= NorthScoutMinimumX and <= NorthScoutMaximumX
            && y is >= NorthScoutMinimumY and <= NorthScoutMaximumY,
        WindriseStatueRecovery => layerId == "MapBack_2"
            && x is >= WindriseMinimumX and <= WindriseMaximumX
            && y is >= WindriseMinimumY and <= WindriseMaximumY,
        _ => false
    };
}
