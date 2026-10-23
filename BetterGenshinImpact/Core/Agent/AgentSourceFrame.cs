namespace BetterGenshinImpact.Core.Agent;

/// <summary>Immutable source identity and QPC-based times mapped into this bridge's monotonic clock.</summary>
/// <param name="CaptureEpoch">Capture generation; changes whenever the backend starts again.</param>
/// <param name="Timestamp100ns">WGC compositor timestamp in 100ns units, also identifying repeated source frames.</param>
/// <param name="CapturedAtMs">Actual compositor-render time, in milliseconds relative to this stream's start.</param>
/// <param name="AcquiredAtMs">Local frame-pool handoff time in the same session clock, before readback/conversion.</param>
public sealed record AgentSourceFrame(string CaptureEpoch, long Timestamp100ns, double CapturedAtMs, double AcquiredAtMs);
