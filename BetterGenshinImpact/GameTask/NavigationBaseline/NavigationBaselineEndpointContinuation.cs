using System;
using System.IO;
using System.Security.Cryptography;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Strict source and file gates for one fixed continuation; contains no capture, movement or retries.</summary>
internal static class NavigationBaselineEndpointContinuation
{
    /// <summary>Metadata checks precede age/discard; the predecessor floor is never installed as consumed input state.</summary>
    internal static void ValidateObservedSource(NavigationBaselineContinuationLink link, GameCaptureSourceInfo? source, double nowMs)
    {
        if (NavigationBaselineRecovery.HardSourceRejection(source, nowMs, link.PredecessorFinalSource) is { } reason)
            throw new InvalidOperationException(reason);
    }

    /// <summary>A new run must independently observe point3, with both source clocks newer than its predecessor.</summary>
    internal static string? StartRejection(NavigationBaselineContinuationLink link, NavigationBaselineSample sample)
    {
        if (NavigationBaselineTask.PoseRejection(sample, NavigationBaselineRouteProfile.ReverseFirst) is { } error) return error;
        var leg = NavigationBaselineRouteProfile.ReverseFirst;
        if (double.Hypot(sample.X - leg.StartX, sample.Y - leg.StartY) > 1.5) return "start_not_at_anchor";
        var previous = link.PredecessorFinalSource;
        if (sample.SourceEpoch != previous.CaptureEpoch) return "continuation_source_epoch_changed";
        if (sample.SourceTimestamp100ns <= previous.SourceTimestamp100ns
            || sample.AcquiredAtStopwatchTicks <= previous.AcquiredAtStopwatchTicks) return "continuation_source_not_newer";
        return null;
    }

    /// <summary>Rehash only server-retained bounded files before native preparation; caller paths are never accepted.</summary>
    internal static void VerifyEvidenceFiles(NavigationBaselineEvidence evidence)
    {
        if (!evidence.Complete) throw new InvalidOperationException("continuation_evidence_incomplete");
        VerifyFile(evidence.JournalPath, evidence.JournalSha256, NativeNavigationBaselineOperations.MaximumJournalBytes);
        VerifyFile(evidence.InitialImagePath, evidence.InitialImageSha256, NativeNavigationBaselineOperations.MaximumPngBytes);
        VerifyFile(evidence.FinalImagePath, evidence.FinalImageSha256, NativeNavigationBaselineOperations.MaximumPngBytes);
    }

    /// <summary>Holding a read-only non-write-sharing handle prevents a concurrent writer from changing checked bytes.</summary>
    private static void VerifyFile(string? path, string? expected, long maximumBytes)
    {
        if (string.IsNullOrEmpty(path) || expected?.Length != 64)
            throw new InvalidOperationException("continuation_evidence_identity_missing");
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length <= 0 || stream.Length > maximumBytes)
            throw new InvalidOperationException("continuation_evidence_size_invalid");
        if (!string.Equals(Convert.ToHexString(SHA256.HashData(stream)), expected, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("continuation_evidence_hash_changed");
    }
}
