using System.Diagnostics;
using BetterGenshinImpact.GameTask.NavigationReset;
using Fischless.GameCapture;
using Newtonsoft.Json;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Pure terminal evidence and unchanged reset source predicates; no logger, app, model, or input is initialized.</summary>
public sealed class NavigationResetSourceDiagnosticTests
{
    /// <summary>Build clocks relative to one fixed QPC reading without using UTC as source age.</summary>
    private static GameCaptureSourceInfo Source(Guid epoch, long now, int ageMs) => new(epoch,
        (long)(((double)now / Stopwatch.Frequency - ageMs / 1000.0) * 10_000_000),
        now - Stopwatch.Frequency * ageMs / 1000);

    /// <summary>Reason detail distinguishes invalid clocks and epoch change without broadening source admission.</summary>
    [Fact]
    public void ReasonsPreserveFreshnessAndEpochRules()
    {
        var now = Stopwatch.GetTimestamp();
        var epoch = Guid.NewGuid();
        var valid = Source(epoch, now, 100);
        Assert.Null(NativeNavigationResetOperations.SourceRejectionReason(valid, now, epoch));
        Assert.Equal("source_missing", NativeNavigationResetOperations.SourceRejectionReason(null, now, epoch));
        Assert.Equal("source_epoch_empty", NativeNavigationResetOperations.SourceRejectionReason(valid with { CaptureEpoch = Guid.Empty }, now, epoch));
        Assert.Equal("source_timestamp_invalid", NativeNavigationResetOperations.SourceRejectionReason(valid with { SourceTimestamp100ns = 0 }, now, epoch));
        Assert.Equal("acquisition_timestamp_invalid", NativeNavigationResetOperations.SourceRejectionReason(valid with { AcquiredAtStopwatchTicks = 0 }, now, epoch));
        Assert.Equal("acquisition_in_future", NativeNavigationResetOperations.SourceRejectionReason(valid with { AcquiredAtStopwatchTicks = now + 1 }, now, epoch));
        Assert.Equal("source_age_exceeds_500ms", NativeNavigationResetOperations.SourceRejectionReason(Source(epoch, now, 501), now, epoch));
        Assert.Null(NativeNavigationResetOperations.SourceRejectionReason(Source(epoch, now, 499), now, epoch));
        Assert.Equal("source_epoch_changed", NativeNavigationResetOperations.SourceRejectionReason(valid, now, Guid.NewGuid()));
        Assert.Equal("source_epoch_changed", NativeNavigationResetOperations.SourceRejectionReason(Source(epoch, now, 700), now, Guid.NewGuid()));
        // A reported timestamp in the future remains governed by the original conservative acquisition anchor.
        Assert.Null(NativeNavigationResetOperations.SourceRejectionReason(valid with { SourceTimestamp100ns = long.MaxValue }, now, epoch));
    }

    /// <summary>The fixed schema fits a small structured log while retaining exact clocks and both epoch identities.</summary>
    [Fact]
    public void TerminalDiagnosticIsBoundedAndRetainsUnchangedSource()
    {
        var source = new GameCaptureSourceInfo(Guid.NewGuid(), long.MaxValue, long.MaxValue);
        var expected = Guid.NewGuid();
        GameCaptureCallTiming.Run(_ => null, out var capture);
        var record = new NavigationResetSourceDiagnostic { Reason = "source_age_exceeds_500ms", Stage = "after_capture",
            NowTicks = long.MaxValue, ExpectedEpoch = expected, ObservedSource = source, Capture = capture };
        var json = JsonConvert.SerializeObject(record);
        Assert.True(System.Text.Encoding.UTF8.GetByteCount(json) < 8192);
        Assert.Equal("native_source_unavailable_or_stale", record.ErrorCode);
        Assert.Equal(500, record.MaximumAgeMs);
        Assert.Equal(expected, record.ExpectedEpoch);
        Assert.Same(source, record.ObservedSource);
        Assert.Same(capture, record.Capture);
        Assert.Contains(long.MaxValue.ToString(), json);
    }
}
