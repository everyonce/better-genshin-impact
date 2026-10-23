using System;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Immutable source identity and QPC-based times mapped into this bridge's monotonic clock.</summary>
/// <param name="CaptureEpoch">Capture generation; changes whenever the backend starts again.</param>
/// <param name="Timestamp100ns">Reported WGC compositor timestamp in 100ns units, also identifying repeated source frames.</param>
/// <param name="CapturedAtMs">Reported compositor QPC time relative to this stream's start; it may lead frame acquisition.</param>
/// <param name="AcquiredAtMs">Local frame-pool handoff time in the same session clock, before readback/conversion.</param>
public sealed record AgentSourceFrame(string CaptureEpoch, long Timestamp100ns, double CapturedAtMs, double AcquiredAtMs)
{
    /// <summary>Bound the freshness lease by first acquisition; this does not measure the game's actual render age.</summary>
    public double FreshnessAtMs => Math.Min(CapturedAtMs, AcquiredAtMs);

    /// <summary>Identify which immutable clock value limits the lease without hiding the raw compositor timestamp.</summary>
    public string FreshnessClockKind => CapturedAtMs <= AcquiredAtMs ? "reported_compositor_qpc" : "first_acquisition_qpc";
}
