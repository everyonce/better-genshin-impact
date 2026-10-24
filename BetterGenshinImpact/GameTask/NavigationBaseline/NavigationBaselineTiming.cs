using System;
using System.Diagnostics;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Fixed opt-in timing contracts; neither version changes observation freshness or response barriers.</summary>
internal static class NavigationBaselineTiming
{
    /// <summary>The original exact 100ms grant remains the default, including after realignment.</summary>
    internal const string V1 = "v1";
    /// <summary>Only the first W-down attempt may receive 150ms, capped by source anchor plus250ms.</summary>
    internal const string V2 = "v2";
    /// <summary>Logical source-relative authority cap, not a physical OS release or game-render guarantee.</summary>
    internal const double SourceHorizonMs = 250;

    /// <summary>No user-supplied durations or unknown contract identifiers are accepted.</summary>
    internal static bool IsSupported(string? contract) => contract is V1 or V2;

    /// <summary>Label the selected controller algorithm without implying verified endpoint success.</summary>
    internal static string ControllerMethod(string contract) => contract switch
    {
        V1 => "native-fixed-leg-feedback-v1",
        V2 => "native-fixed-leg-feedback-v2",
        _ => "unsupported"
    };

    /// <summary>Compute authority from the final pre-dispatch clock; native-call time consumes this grant.</summary>
    internal static (double GrantMs, double AnchorMs, double? SourceCapMs, double ExpiresAtMs) Grant(
        string contract, bool firstForwardAttempt, GameCaptureSourceInfo source, double now)
    {
        if (!IsSupported(contract)) throw new ArgumentException("unsupported_timing_contract", nameof(contract));
        var anchor = Math.Min(source.SourceTimestamp100ns / 10_000.0,
            source.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency);
        if (contract == V1) return (100, anchor, null, now + 100); // Preserve the original arithmetic exactly.
        var grant = firstForwardAttempt ? 150 : 100;
        var cap = anchor + SourceHorizonMs;
        var expires = Math.Min(now + grant, cap);
        if (!double.IsFinite(now) || !double.IsFinite(anchor) || !double.IsFinite(expires) || expires <= now)
            throw new InvalidOperationException("invalid_forward_grant");
        return (grant, anchor, cap, expires);
    }
}
