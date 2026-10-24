using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>Fixed teleport/yaw/settle workflow, separated from native operations for cancellation tests.</summary>
internal sealed class NavigationResetTask(INavigationResetOperations operations, Func<CancellationToken, Task>? isolateAfterTeleport = null)
{
    /// <summary>Only this reviewed surface waypoint can be selected.</summary>
    internal const string ProfileId = "mondstadt-city-10";
    /// <summary>Map icon, distinct from the actual teleport spawn.</summary>
    internal const double IconX = -876.1047, IconY = 2277.604;
    /// <summary>Reviewed ID10 spawn in Genshin map coordinates.</summary>
    internal const double SpawnX = -867.6852, SpawnY = 2281.4954;
    /// <summary>Position and circular yaw acceptance bounds, in map units and degrees respectively.</summary>
    internal const double PositionTolerance = 3, YawTolerance = 3;
    /// <summary>Aim inside the final yaw band, leaving two degrees for recognition/settling drift before verification.</summary>
    internal const double OrientationYawTolerance = 1;
    /// <summary>Whole-operation cooperative deadline, including warmup and TaskRunner acquisition.</summary>
    internal static readonly TimeSpan Timeout = TimeSpan.FromSeconds(75);
    /// <summary>Existing final-verification work bound, also limiting retained diagnostic evidence.</summary>
    internal const int MaximumVerificationAttempts = 15;
    /// <summary>Returned verification observations only; failed native probes never become pose evidence.</summary>
    private readonly List<NavigationResetVerificationDiagnostic> _verificationDiagnostics = [];
    /// <summary>Detached evidence survives a failed workflow without being mistaken for verified success samples.</summary>
    internal NavigationResetVerificationDiagnostic[] VerificationDiagnostics => _verificationDiagnostics.ToArray();

    /// <summary>Reject non-finite, wrapped, or unbounded external targets before any operation.</summary>
    internal static bool IsValidYaw(double yaw) => double.IsFinite(yaw) && yaw >= 0 && yaw < 360;

    /// <summary>Match the existing yaw threshold without accepting the camera helper's low-confidence fallback.</summary>
    internal static bool IsReliableYaw(double yaw, double confidence) => IsValidYaw(yaw)
        && IsReliableYawConfidence(confidence);

    /// <summary>Keep native acquisition and diagnostic pose rejection on the same confidence predicate.</summary>
    private static bool IsReliableYawConfidence(double confidence) => double.IsFinite(confidence) && confidence is >= 0.2 and <= 1;

    /// <summary>Shortest circular angular distance; accepts wraparound near north/right.</summary>
    internal static double YawDistance(double a, double b) => Math.Abs((a - b + 540) % 360 - 180);

    /// <summary>Share the stricter orientation target between correction dispatch and loop completion; final acceptance stays separate.</summary>
    internal static bool IsYawOriented(double measuredYaw, double targetYaw) => IsValidYaw(measuredYaw)
        && IsValidYaw(targetYaw) && YawDistance(measuredYaw, targetYaw) <= OrientationYawTolerance;

    /// <summary>One current high-confidence surface sample near the fixed spawn.</summary>
    internal static bool IsValidPose(NavigationResetSample sample) => PoseRejectionReason(sample) is null;

    /// <summary>Name the exact existing pose condition without changing its confidence, position or source bounds.</summary>
    private static string? PoseRejectionReason(NavigationResetSample sample)
    {
        if (!double.IsFinite(sample.X) || !double.IsFinite(sample.Y)) return "invalid_position";
        if (!IsValidYaw(sample.YawDegrees)) return "invalid_yaw";
        if (!IsReliableYawConfidence(sample.YawConfidence)) return "invalid_yaw_confidence";
        if (double.Hypot(sample.X - SpawnX, sample.Y - SpawnY) > PositionTolerance) return "position_out_of_bounds";
        if (!double.IsFinite(sample.PositionConfidence) || sample.PositionConfidence is < 0.99 or > 1) return "invalid_position_confidence";
        if (sample.LayerId != "City_102") return "wrong_layer";
        if (sample.SourceEpoch == Guid.Empty) return "invalid_source_epoch";
        if (sample.HostSnapshot is { } host)
        {
            if (sample.SourceTimestamp100ns is not null || sample.AcquiredAtStopwatchTicks is not null)
                return "mixed_source_kinds";
            if (host.CaptureEpoch != sample.SourceEpoch || host.SnapshotId <= 0
                || host.StartedAtStopwatchTicks <= 0 || host.CompletedAtStopwatchTicks < host.StartedAtStopwatchTicks
                || host.ClockFrequency != Stopwatch.Frequency) return "invalid_host_snapshot";
            return null;
        }
        if (sample.SourceTimestamp100ns is not > 0) return "invalid_source_timestamp";
        return sample.AcquiredAtStopwatchTicks is not > 0 ? "invalid_acquisition_timestamp" : null;
    }

    /// <summary>The same single-sample rejection clears the rolling window and explains that observation.</summary>
    private static string? SampleRejectionReason(NavigationResetSample sample, double yaw) =>
        PoseRejectionReason(sample) ?? (YawDistance(sample.YawDegrees, yaw) > YawTolerance ? "target_yaw_out_of_tolerance" : null);

    /// <summary>Require distinct ordered sources and a stable cluster, not three cached recognition results.</summary>
    internal static bool AcceptSamples(IReadOnlyList<NavigationResetSample> samples, double yaw) =>
        SamplesRejectionReason(samples, yaw) is null;

    /// <summary>One shared final gate supplies both boolean acceptance and stable diagnostic rejection codes.</summary>
    internal static string? SamplesRejectionReason(IReadOnlyList<NavigationResetSample> samples, double yaw)
    {
        if (!IsValidYaw(yaw)) return "invalid_target_yaw";
        if (samples.Count != 3) return "sample_count_not_three";
        for (var i = 0; i < samples.Count; i++)
        {
            var sample = samples[i];
            if (SampleRejectionReason(sample, yaw) is { } reason) return reason;
            for (var j = 0; j < i; j++)
            {
                var previous = samples[j];
                if (sample.SourceEpoch != previous.SourceEpoch) return "source_epoch_changed";
                if ((sample.HostSnapshot is null) != (previous.HostSnapshot is null)) return "source_kind_changed";
                if (sample.HostSnapshot is not null)
                {
                    if (sample.Evidence!.IdentityRejection(previous.Evidence) is { } identityError) return identityError;
                    if (!sample.Evidence.StrictlyNewerThan(previous.Evidence!)) return "source_not_increasing";
                }
                else
                {
                    if (sample.SourceTimestamp100ns <= previous.SourceTimestamp100ns) return "source_not_increasing";
                    if (sample.AcquiredAtStopwatchTicks <= previous.AcquiredAtStopwatchTicks) return "acquisition_not_increasing";
                }
                if (double.Hypot(sample.X - previous.X, sample.Y - previous.Y) > 1.5) return "position_spread_exceeded";
                if (YawDistance(sample.YawDegrees, previous.YawDegrees) > 2) return "yaw_spread_exceeded";
            }
            if (i > 0 && sample.Evidence!.GapFrom(samples[i - 1].Evidence!) < 80) return "acquisition_spacing_too_short";
        }
        return null;
    }

    /// <summary>Summarize only the current candidate window; no diagnostic value affects the acceptance decision.</summary>
    private static NavigationResetVerificationDiagnostic DescribeVerification(int attempt, NavigationResetSample sample,
        IReadOnlyList<NavigationResetSample> candidates, double yaw, string? rejectionReason)
    {
        double? positionSpread = null, yawSpread = null, minimumGap = null;
        for (var i = 0; i < candidates.Count; i++)
        {
            for (var j = 0; j < i; j++)
            {
                var distance = double.Hypot(candidates[i].X - candidates[j].X, candidates[i].Y - candidates[j].Y);
                var yawDistance = YawDistance(candidates[i].YawDegrees, candidates[j].YawDegrees);
                positionSpread = Math.Max(positionSpread ?? 0, distance);
                yawSpread = Math.Max(yawSpread ?? 0, yawDistance);
            }
            if (i > 0 && (candidates[i].HostSnapshot is null) == (candidates[i - 1].HostSnapshot is null))
            {
                // A mixed-kind rejected window has no comparable acquisition gap; diagnostics must not replace its failure.
                var gap = candidates[i].Evidence!.GapFrom(candidates[i - 1].Evidence!);
                minimumGap = minimumGap is { } previous ? Math.Min(previous, gap) : gap;
            }
        }
        var targetError = IsValidYaw(sample.YawDegrees) ? YawDistance(sample.YawDegrees, yaw) : (double?)null;
        return new(attempt, sample, candidates.Count, rejectionReason ?? "accepted", targetError,
            positionSpread, yawSpread, minimumGap);
    }

    /// <summary>Run only under TaskRunner ownership; cleanup never waits for another capture.</summary>
    internal async Task<NavigationResetSample[]> RunAsync(double yaw, Action<string> phase, CancellationToken ct)
    {
        if (!IsValidYaw(yaw)) throw new ArgumentOutOfRangeException(nameof(yaw));
        _verificationDiagnostics.Clear();
        try
        {
            phase("preparing");
            await operations.PrepareAsync(ct);
            ct.ThrowIfCancellationRequested();
            phase("teleporting");
            await operations.TeleportAsync(ct);
            ct.ThrowIfCancellationRequested();
            if (isolateAfterTeleport is not null)
            {
                phase("isolating_capture");
                await isolateAfterTeleport(ct);
                ct.ThrowIfCancellationRequested();
            }
            phase("orienting");
            if (!await operations.RotateAsync(yaw, ct)) throw new InvalidOperationException("yaw_not_reached");
            ct.ThrowIfCancellationRequested();
            phase("verifying");
            var samples = new List<NavigationResetSample>();
            // A bounded settling window tolerates an isolated noisy sample, but never weakens the final gate.
            for (var attempt = 0; attempt < MaximumVerificationAttempts; attempt++)
            {
                await operations.DelayAsync(120, ct);
                var sample = await operations.ReadPoseAsync(ct);
                try { ct.ThrowIfCancellationRequested(); }
                catch (OperationCanceledException)
                {
                    _verificationDiagnostics.Add(DescribeVerification(attempt + 1, sample, [], yaw, "cancelled_before_verification"));
                    throw;
                }
                var rejectionReason = SampleRejectionReason(sample, yaw);
                if (rejectionReason is not null) samples.Clear();
                else
                {
                    samples.Add(sample);
                    if (samples.Count > 3) samples.RemoveAt(0);
                    rejectionReason = SamplesRejectionReason(samples, yaw);
                }
                _verificationDiagnostics.Add(DescribeVerification(attempt + 1, sample, samples, yaw, rejectionReason));
                if (rejectionReason is null) return samples.ToArray();
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
