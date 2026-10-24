using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>Fixed teleport/yaw/settle workflow, separated from native operations for cancellation tests.</summary>
internal sealed class NavigationResetTask(INavigationResetOperations operations)
{
    /// <summary>Only this reviewed surface waypoint can be selected.</summary>
    internal const string ProfileId = "mondstadt-city-10";
    /// <summary>Map icon, distinct from the actual teleport spawn.</summary>
    internal const double IconX = -876.1047, IconY = 2277.604;
    /// <summary>Reviewed ID10 spawn in Genshin map coordinates.</summary>
    internal const double SpawnX = -867.6852, SpawnY = 2281.4954;
    /// <summary>Position and circular yaw acceptance bounds, in map units and degrees respectively.</summary>
    internal const double PositionTolerance = 3, YawTolerance = 3;
    /// <summary>Whole-operation cooperative deadline, including warmup and TaskRunner acquisition.</summary>
    internal static readonly TimeSpan Timeout = TimeSpan.FromSeconds(75);

    /// <summary>Reject non-finite, wrapped, or unbounded external targets before any operation.</summary>
    internal static bool IsValidYaw(double yaw) => double.IsFinite(yaw) && yaw >= 0 && yaw < 360;

    /// <summary>Match the existing yaw threshold without accepting the camera helper's low-confidence fallback.</summary>
    internal static bool IsReliableYaw(double yaw, double confidence) => IsValidYaw(yaw)
        && double.IsFinite(confidence) && confidence is >= 0.2 and <= 1;

    /// <summary>Shortest circular angular distance; accepts wraparound near north/right.</summary>
    internal static double YawDistance(double a, double b) => Math.Abs((a - b + 540) % 360 - 180);

    /// <summary>One current high-confidence surface sample near the fixed spawn.</summary>
    internal static bool IsValidPose(NavigationResetSample sample) =>
        double.IsFinite(sample.X) && double.IsFinite(sample.Y) && IsReliableYaw(sample.YawDegrees, sample.YawConfidence)
        && double.Hypot(sample.X - SpawnX, sample.Y - SpawnY) <= PositionTolerance
        && double.IsFinite(sample.PositionConfidence) && sample.PositionConfidence is >= 0.99 and <= 1
        && sample.LayerId == "City_102" && sample.SourceEpoch != Guid.Empty
        && sample.SourceTimestamp100ns > 0 && sample.AcquiredAtStopwatchTicks > 0;

    /// <summary>Require distinct ordered sources and a stable cluster, not three cached recognition results.</summary>
    internal static bool AcceptSamples(IReadOnlyList<NavigationResetSample> samples, double yaw)
    {
        if (!IsValidYaw(yaw) || samples.Count != 3) return false;
        for (var i = 0; i < samples.Count; i++)
        {
            var sample = samples[i];
            if (!IsValidPose(sample) || YawDistance(sample.YawDegrees, yaw) > YawTolerance) return false;
            for (var j = 0; j < i; j++)
            {
                var previous = samples[j];
                if (sample.SourceEpoch != previous.SourceEpoch || sample.SourceTimestamp100ns <= previous.SourceTimestamp100ns
                    || sample.AcquiredAtStopwatchTicks <= previous.AcquiredAtStopwatchTicks
                    || double.Hypot(sample.X - previous.X, sample.Y - previous.Y) > 1.5
                    || YawDistance(sample.YawDegrees, previous.YawDegrees) > 2) return false;
            }
            if (i > 0 && Stopwatch.GetElapsedTime(samples[i - 1].AcquiredAtStopwatchTicks,
                    sample.AcquiredAtStopwatchTicks).TotalMilliseconds < 80) return false;
        }
        return true;
    }

    /// <summary>Run only under TaskRunner ownership; cleanup never waits for another capture.</summary>
    internal async Task<NavigationResetSample[]> RunAsync(double yaw, Action<string> phase, CancellationToken ct)
    {
        if (!IsValidYaw(yaw)) throw new ArgumentOutOfRangeException(nameof(yaw));
        try
        {
            phase("preparing");
            await operations.PrepareAsync(ct);
            ct.ThrowIfCancellationRequested();
            phase("teleporting");
            await operations.TeleportAsync(ct);
            ct.ThrowIfCancellationRequested();
            phase("orienting");
            if (!await operations.RotateAsync(yaw, ct)) throw new InvalidOperationException("yaw_not_reached");
            ct.ThrowIfCancellationRequested();
            phase("verifying");
            var samples = new List<NavigationResetSample>();
            // A bounded settling window tolerates an isolated noisy sample, but never weakens the final gate.
            for (var attempt = 0; attempt < 15; attempt++)
            {
                await operations.DelayAsync(120, ct);
                var sample = await operations.ReadPoseAsync(ct);
                ct.ThrowIfCancellationRequested();
                if (!IsValidPose(sample) || YawDistance(sample.YawDegrees, yaw) > YawTolerance) samples.Clear();
                else
                {
                    samples.Add(sample);
                    if (samples.Count > 3) samples.RemoveAt(0);
                    if (AcceptSamples(samples, yaw)) return samples.ToArray();
                }
            }
            throw new InvalidOperationException("pose_not_settled");
        }
        finally { operations.ReleaseInput(); }
    }
}

/// <summary>Narrow native boundary for this single task; not a script or arbitrary input interface.</summary>
internal interface INavigationResetOperations
{
    /// <summary>Pin the runtime, verify assets/world/capture, and warm local matching before any teleport.</summary>
    Task PrepareAsync(CancellationToken ct);
    /// <summary>Teleport only to the fixed profile icon.</summary>
    Task TeleportAsync(CancellationToken ct);
    /// <summary>Use the existing camera controller, with bounded attempts and same-frame recognition guards.</summary>
    Task<bool> RotateAsync(double yaw, CancellationToken ct);
    /// <summary>Measure a new native source, never a cached navigation result.</summary>
    Task<NavigationResetSample> ReadPoseAsync(CancellationToken ct);
    /// <summary>Cooperative waiting between operations and settled observations.</summary>
    Task DelayAsync(int milliseconds, CancellationToken ct);
    /// <summary>Release only the originally bound runtime's input backend.</summary>
    void ReleaseInput();
}
