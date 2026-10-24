using System;
using System.Diagnostics;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Fixed opt-in timing contracts; no version changes observation freshness or response barriers.</summary>
internal static class NavigationBaselineTiming
{
    /// <summary>The original exact 100ms grant remains the default, including after realignment.</summary>
    internal const string V1 = "v1";
    /// <summary>Only the first W-down attempt may receive 150ms, capped by source anchor plus250ms.</summary>
    internal const string V2 = "v2";
    /// <summary>Each physical W-down attempt may receive 150ms; held-input renewals remain 100ms.</summary>
    internal const string V3 = "v3";
    /// <summary>V3 grants with bounded release-and-freshness recovery; legacy versions remain terminal.</summary>
    internal const string V4 = "v4";
    /// <summary>Logical source-relative authority cap, not a physical OS release or game-render guarantee.</summary>
    internal const double SourceHorizonMs = 250;

    /// <summary>No user-supplied durations or unknown contract identifiers are accepted.</summary>
    internal static bool IsSupported(string? contract) => contract is V1 or V2 or V3 or V4;

    /// <summary>Label the selected controller algorithm without implying verified endpoint success.</summary>
    internal static string ControllerMethod(string contract) => contract switch
    {
        V1 => "native-fixed-leg-feedback-v1",
        V2 => "native-fixed-leg-feedback-v2",
        V3 => "native-fixed-leg-feedback-v3",
        V4 => "native-fixed-leg-feedback-v4",
        _ => "unsupported"
    };

    /// <summary>Compute authority from the final pre-dispatch clock; native-call time consumes this grant.</summary>
    internal static (double GrantMs, double AnchorMs, double? SourceCapMs, double ExpiresAtMs) Grant(
        string contract, bool firstForwardAttempt, bool physicalDownAttempt, GameCaptureSourceInfo source, double now)
    {
        if (!IsSupported(contract)) throw new ArgumentException("unsupported_timing_contract", nameof(contract));
        var anchor = Math.Min(source.SourceTimestamp100ns / 10_000.0,
            source.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency);
        if (contract == V1) return (100, anchor, null, now + 100); // Preserve the original arithmetic exactly.
        // V2's run-first identity is independent of V3's actual held-to-pressed transition.
        var longGrant = contract is V3 or V4 ? physicalDownAttempt : firstForwardAttempt;
        var grant = longGrant ? 150 : 100;
        var cap = anchor + SourceHorizonMs;
        var expires = Math.Min(now + grant, cap);
        if (!double.IsFinite(now) || !double.IsFinite(anchor) || !double.IsFinite(expires) || expires <= now)
            throw new InvalidOperationException("invalid_forward_grant");
        return (grant, anchor, cap, expires);
    }
}
