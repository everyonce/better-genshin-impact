using System;
using System.Diagnostics;
using System.Text.Json.Serialization;
using Fischless.GameCapture;

namespace BetterGenshinImpact.Core.Capture;

/// <summary>Two explicit immutable authorities. Host acquisition never becomes a WGC timestamp or rendered-frame identity.</summary>
[JsonConverter(typeof(CaptureSourceEvidenceJsonConverter))]
internal sealed record CaptureSourceEvidence
{
    /// <summary>Original WGC metadata, unchanged; null for a desktop host snapshot.</summary>
    internal GameCaptureSourceInfo? WgcSource { get; }
    /// <summary>Original completed host interval, never consumer receipt time; null for WGC.</summary>
    internal GameCaptureHostSnapshotInfo? HostSnapshot { get; }
    /// <summary>Exactly one original evidence kind is retained.</summary>
    internal CaptureSourceEvidence(GameCaptureSourceInfo source) => WgcSource = source ?? throw new ArgumentNullException(nameof(source));
    /// <summary>Host headers remain untrusted until explicit header, target and age gates pass.</summary>
    internal CaptureSourceEvidence(GameCaptureHostSnapshotInfo source) => HostSnapshot = source ?? throw new ArgumentNullException(nameof(source));
    /// <summary>Compatibility construction preserves the original WGC identity and clocks.</summary>
    internal CaptureSourceEvidence(Guid epoch, long sourceTimestamp100ns, long acquiredAtStopwatchTicks)
        : this(new GameCaptureSourceInfo(epoch, sourceTimestamp100ns, acquiredAtStopwatchTicks)) { }
    /// <summary>Existing WGC callers can pass their original record without any metadata conversion.</summary>
    public static implicit operator CaptureSourceEvidence?(GameCaptureSourceInfo? source) => source is null ? null : new(source);
    /// <summary>Each backend Start owns a distinct generation.</summary>
    internal Guid CaptureEpoch => WgcSource?.CaptureEpoch ?? HostSnapshot!.CaptureEpoch;
    /// <summary>Minimum original WGC clocks, or the conservative beginning of host acquisition.</summary>
    internal double AnchorAtMs => WgcSource is { } wgc
        ? Math.Min(wgc.SourceTimestamp100ns / 10_000.0, wgc.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency)
        : HostSnapshot!.StartedAtStopwatchTicks * 1000.0 / HostSnapshot.ClockFrequency;
    /// <summary>Observation-spacing clock: WGC acquisition or desktop capture start, never copy return.</summary>
    internal double AcquisitionAtMs => WgcSource is { } wgc
        ? wgc.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency
        : HostSnapshot!.StartedAtStopwatchTicks * 1000.0 / HostSnapshot.ClockFrequency;

    /// <summary>Read the selected backend's exact metadata. Unexpected kinds cannot use another backend's fallback.</summary>
    internal static CaptureSourceEvidence? FromFrame(GameCaptureFrame frame, bool desktop)
    {
        if (desktop)
        {
            if (frame.SourceInfo is not null) throw new InvalidOperationException("source_kind_changed");
            return frame.HostSnapshotInfo is { } host ? new(host) : null;
        }
        if (frame.HostSnapshotInfo is not null) throw new InvalidOperationException("source_kind_changed");
        return frame.SourceInfo;
    }

    /// <summary>Validate shape/clock provenance before age classification. WGC's original future-source policy is unchanged.</summary>
    internal string? HeaderRejection(double nowMs)
    {
        if (!Stopwatch.IsHighResolution || !double.IsFinite(nowMs) || nowMs < 0) return "invalid_source_clock";
        if (CaptureEpoch == Guid.Empty) return "invalid_native_source";
        if (WgcSource is { } wgc)
        {
            if (wgc.SourceTimestamp100ns <= 0 || wgc.AcquiredAtStopwatchTicks <= 0) return "invalid_native_source";
            return wgc.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency > nowMs ? "acquisition_in_future" : null;
        }
        var host = HostSnapshot!;
        if (host.ClockFrequency != Stopwatch.Frequency || host.ClockFrequency <= 0) return "invalid_source_clock";
        if (host.SnapshotId <= 0 || host.StartedAtStopwatchTicks <= 0
            || host.CompletedAtStopwatchTicks < host.StartedAtStopwatchTicks) return "invalid_host_snapshot";
        return host.CompletedAtStopwatchTicks * 1000.0 / host.ClockFrequency > nowMs ? "acquisition_in_future" : null;
    }

    /// <summary>Keep kind, generation, immutable equal identities and both original clocks monotonic.</summary>
    internal string? IdentityRejection(CaptureSourceEvidence? previous)
    {
        if (previous is null) return null;
        if ((WgcSource is null) != (previous.WgcSource is null)) return "source_kind_changed";
        if (CaptureEpoch != previous.CaptureEpoch) return "source_epoch_changed";
        if (WgcSource is { } wgc)
            return wgc.SourceTimestamp100ns < previous.WgcSource!.SourceTimestamp100ns
                || wgc.AcquiredAtStopwatchTicks < previous.WgcSource.AcquiredAtStopwatchTicks ? "native_source_regressed" : null;
        var host = HostSnapshot!; var old = previous.HostSnapshot!;
        if (host.ClockFrequency != old.ClockFrequency) return "invalid_source_clock";
        if (host.SnapshotId == old.SnapshotId && host != old) return "host_snapshot_identity_changed";
        return host.SnapshotId < old.SnapshotId || host.StartedAtStopwatchTicks < old.StartedAtStopwatchTicks
            || host.CompletedAtStopwatchTicks < old.CompletedAtStopwatchTicks ? "native_source_regressed" : null;
    }

    /// <summary>Distinct host acquisitions are required; this is not a claim that game rendering advanced.</summary>
    internal bool StrictlyNewerThan(CaptureSourceEvidence previous) => IdentityRejection(previous) is null
        && (WgcSource is { } wgc
            ? wgc.SourceTimestamp100ns > previous.WgcSource!.SourceTimestamp100ns
                && wgc.AcquiredAtStopwatchTicks > previous.WgcSource.AcquiredAtStopwatchTicks
            : HostSnapshot!.SnapshotId > previous.HostSnapshot!.SnapshotId
                && HostSnapshot.StartedAtStopwatchTicks > previous.HostSnapshot.StartedAtStopwatchTicks
                && HostSnapshot.CompletedAtStopwatchTicks > previous.HostSnapshot.CompletedAtStopwatchTicks);

    /// <summary>Header checks precede conservative start-age; malformed/late metadata yields no authority.</summary>
    internal double AgeAt(double nowMs) => HeaderRejection(nowMs) is null ? nowMs - AnchorAtMs : double.NaN;
    /// <summary>Both WGC clocks or the entire host interval must begin after the unchanged input-response cutoff.</summary>
    internal bool AfterBarrier(double completedAtMs, double responseMs) => WgcSource is { } wgc
        ? wgc.SourceTimestamp100ns / 10_000.0 - completedAtMs >= responseMs
            && wgc.AcquiredAtStopwatchTicks * 1000.0 / Stopwatch.Frequency - completedAtMs >= responseMs
        : HostSnapshot!.StartedAtStopwatchTicks * 1000.0 / HostSnapshot.ClockFrequency - completedAtMs >= responseMs;
    /// <summary>Keep the old WGC elapsed-ticks arithmetic; host spacing uses its explicitly pinned frequency.</summary>
    internal double GapFrom(CaptureSourceEvidence previous) => WgcSource is { } wgc && previous.WgcSource is { } old
        ? Stopwatch.GetElapsedTime(old.AcquiredAtStopwatchTicks, wgc.AcquiredAtStopwatchTicks).TotalMilliseconds
        : (HostSnapshot!.StartedAtStopwatchTicks - previous.HostSnapshot!.StartedAtStopwatchTicks) * 1000.0 / HostSnapshot.ClockFrequency;
}
