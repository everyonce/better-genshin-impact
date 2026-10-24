using BetterGenshinImpact.Core.Capture;
using System;
using System.Diagnostics;

namespace BetterGenshinImpact.Core.Agent;

/// <summary>Original host acquisition evidence; neither a WGC timestamp nor a measured game-render age.</summary>
/// <param name="CaptureEpoch">Exact capture generation.</param>
/// <param name="SnapshotId">Positive identity of this successful host acquisition.</param>
/// <param name="StartedAtStopwatchTicks">Original start before guards, acquisition and copy.</param>
/// <param name="CompletedAtStopwatchTicks">Original completion after owned cleanup.</param>
/// <param name="ClockFrequency">Original QPC scale, required to match this process.</param>
/// <param name="SessionOriginAtStopwatchTicks">Fixed bridge origin used only to map the raw interval.</param>
/// <param name="DesktopDcSourcePolicy">Startup-fixed observation/controller policy.</param>
public sealed record AgentHostSnapshot(string CaptureEpoch, long SnapshotId, long StartedAtStopwatchTicks,
    long CompletedAtStopwatchTicks, long ClockFrequency, long SessionOriginAtStopwatchTicks, string DesktopDcSourcePolicy)
{
    /// <summary>Version of this separate evidence representation.</summary>
    public int Version => 1;
    /// <summary>The acquisition basis is explicit even when the policy permits observation only.</summary>
    public string SourceKind => DesktopCapturePolicy.HostAcquisitionV1;
    /// <summary>Conservative authority time; an immutable original start cannot be renewed by delivery.</summary>
    public double StartedAtMs => (double)((Int128)StartedAtStopwatchTicks - SessionOriginAtStopwatchTicks) * 1000 / ClockFrequency;
    /// <summary>Host cleanup-complete endpoint in the same bridge clock.</summary>
    public double CompletedAtMs => (double)((Int128)CompletedAtStopwatchTicks - SessionOriginAtStopwatchTicks) * 1000 / ClockFrequency;

    /// <summary>Check raw identity/clock order before using the mapped interval; no tolerance admits future completion.</summary>
    public bool IsValidAt(double checkedAtMs) =>
        Guid.TryParseExact(CaptureEpoch, "N", out var epoch) && epoch != Guid.Empty && SnapshotId > 0 &&
        SessionOriginAtStopwatchTicks > 0 && StartedAtStopwatchTicks >= SessionOriginAtStopwatchTicks &&
        CompletedAtStopwatchTicks >= StartedAtStopwatchTicks && ClockFrequency == Stopwatch.Frequency &&
        ClockFrequency > 0 && DesktopDcSourcePolicy is DesktopCapturePolicy.ObserveOnly or DesktopCapturePolicy.HostAcquisitionV1 &&
        double.IsFinite(checkedAtMs) && double.IsFinite(StartedAtMs) && double.IsFinite(CompletedAtMs) &&
        StartedAtMs >= 0 && CompletedAtMs <= checkedAtMs;
}
