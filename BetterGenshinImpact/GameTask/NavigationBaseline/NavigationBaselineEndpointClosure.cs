using System;
using System.Text.Json.Serialization;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Endpoint-only handling of a recorded expired lease; never authority to resume movement.</summary>
internal sealed record NavigationBaselineEndpointClosure
{
    /// <summary>Distinguish permanent endpoint closure from a movement recovery/resume attempt.</summary>
    [JsonPropertyName("method")]
    public string Method => "expired-endpoint-release-final-only-v1";
    /// <summary>The observed violation remains explicit even when release and later verification succeed.</summary>
    [JsonPropertyName("violation")]
    public string Violation => "forward_lease_expired";
    /// <summary>The original deadline that was violated; it is not extended by cleanup or verification.</summary>
    [JsonPropertyName("leaseExpiresAtMs")]
    public required double LeaseExpiresAtMs { get; init; }
    /// <summary>The exact existing movement-budget ticket, retaining its first expiry and release evidence.</summary>
    [JsonPropertyName("pause")]
    public required NavigationBaselineRecoveryPause Pause { get; init; }
    /// <summary>Confirmed permanent input-close cutoff; absent when cleanup did not complete successfully.</summary>
    [JsonPropertyName("closedAtMs")]
    public double? ClosedAtMs { get; init; }
    /// <summary>Retain failure even if later best-effort disposal succeeds; null alone is not completion.</summary>
    [JsonPropertyName("error")]
    public string? Error { get; init; }

    /// <summary>One original, budgeted expiry ticket with confirmed release and no restarted pause window.</summary>
    [JsonIgnore]
    internal bool ConfirmsClosure => Error is null && ClosedAtMs is { } closed && double.IsFinite(closed)
        && double.IsFinite(LeaseExpiresAtMs) && LeaseExpiresAtMs > 0
        && double.IsFinite(Pause.StartedAtMs) && double.IsFinite(Pause.ReleasedAtMs)
        && Pause.StartedAtMs >= LeaseExpiresAtMs && Pause.ReleasedAtMs >= Pause.StartedAtMs
        && closed >= Pause.ReleasedAtMs && closed < Pause.StartedAtMs + NavigationBaselineRecovery.MaximumWaitMs
        && Pause.Cause == NavigationBaselineRecoveryCause.LeaseExpired && Pause.ReleaseError is null
        && Pause.BudgetKind == NavigationBaselineRecoveryBudgetKind.MovementRecovery && Pause.HeldForwardAtEntry
        && Pause.Generation is >= 1 and <= NavigationBaselineRecovery.MaximumPauseWindows
        && Pause.MovementRecoveriesUsed is >= 1 and <= NavigationBaselineRecovery.MaximumRecoveries
        && Pause.StationaryReadinessUsed is >= 0 and <= NavigationBaselineRecovery.MaximumStationaryReadiness
        && Pause.Generation == Pause.TotalWindowsUsed;
}
