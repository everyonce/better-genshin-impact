using System;
using System.IO;
using System.Security.Cryptography;
using BetterGenshinImpact.Core.Capture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Strict source and file gates for one fixed continuation; contains no capture, movement or retries.</summary>
internal static class NavigationBaselineEndpointContinuation
{
    /// <summary>Metadata checks precede age/discard; the predecessor floor is never installed as consumed input state.</summary>
    internal static void ValidateObservedSource(NavigationBaselineContinuationLink link, CaptureSourceEvidence? source, double nowMs)
    {
        if (NavigationBaselineRecovery.HardSourceRejection(source, nowMs, link.PredecessorFinalSource) is { } reason)
            throw new InvalidOperationException(reason);
    }

    /// <summary>A new run independently observes its exact requested start anchor with both clocks newer than its predecessor.</summary>
    internal static string? StartRejection(NavigationBaselineContinuationLink link, NavigationBaselineSample sample,
        NavigationBaselineRouteProfile? requested = null)
    {
        var route = requested ?? NavigationBaselineRouteProfile.Reverse;
        if (!route.AllowsPredecessor(link.PredecessorProfileId)) return "continuation_predecessor_profile_mismatch";
        var leg = route.InitialLeg;
        if (NavigationBaselineTask.PoseRejection(sample, leg) is { } error) return error;
        if (double.Hypot(sample.X - leg.StartX, sample.Y - leg.StartY) > 1.5) return "start_not_at_anchor";
        var previous = link.PredecessorFinalSource;
        if (sample.SourceEpoch != previous.CaptureEpoch) return "continuation_source_epoch_changed";
        // The predecessor is a rejection floor only. A new host acquisition must advance all three values.
        if (previous.HostSnapshot is not null)
        {
            if (!route.SupportsHostContinuation || !link.HasHostSourceContract) return "continuation_host_contract_mismatch";
            if (sample.HostSnapshot is null) return "source_kind_changed";
            if (sample.Source.IdentityRejection(previous) is { } identity) return identity;
            if (!sample.Source.StrictlyNewerThan(previous)) return "continuation_source_not_newer";
        }
        else
        {
            if (sample.HostSnapshot is not null || link.SourcePolicy is not null || link.ChildAssemblySha256 is not null)
                return "source_kind_changed";
            if (sample.SourceTimestamp100ns <= previous.WgcSource!.SourceTimestamp100ns
                || sample.AcquiredAtStopwatchTicks <= previous.WgcSource.AcquiredAtStopwatchTicks) return "continuation_source_not_newer";
        }
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
