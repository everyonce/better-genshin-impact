using System.Diagnostics;
using BetterGenshinImpact.GameTask.NavigationReset;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Pure first-acquisition retry checks; no runtime, logger, model, capture backend or input is initialized.</summary>
public sealed class NavigationResetInitialSourceRetryTests
{
    /// <summary>Whole-second clocks make the exact 500ms boundary independent of fixture rounding.</summary>
    private static readonly long Now = 2 * Stopwatch.Frequency;
    /// <summary>Build matching reported/acquisition clocks in their original units.</summary>
    private static GameCaptureSourceInfo Source(Guid epoch, int ageMs) => new(epoch,
        20_000_000L - ageMs * 10_000L, Now - Stopwatch.Frequency * ageMs / 1000);
    /// <summary>Construct valid final evidence only for the fake fresh-frame consumer.</summary>
    private static NavigationResetSample Sample(GameCaptureSourceInfo source) => new(
        NavigationResetTask.SpawnX, NavigationResetTask.SpawnY, 0, DateTimeOffset.UnixEpoch,
        source.CaptureEpoch, source.SourceTimestamp100ns, source.AcquiredAtStopwatchTicks, 1, 1, "Teyvat");

    /// <summary>Exactly 500ms stays admitted; only strictly older same-epoch images enter the bounded discard path.</summary>
    [Theory]
    [InlineData(499, false)]
    [InlineData(500, false)]
    [InlineData(501, true)]
    [InlineData(906, true)]
    public void FreshnessBoundaryIsUnchanged(int ageMs, bool retry)
    {
        var epoch = Guid.NewGuid(); var source = Source(epoch, ageMs);
        Assert.Equal(!retry, NativeNavigationResetOperations.SourceIsFresh(source, Now));
        var reason = NativeNavigationResetOperations.InitialSourceRetryReason(source, Now, epoch, true, "after_capture");
        Assert.Equal(retry, reason is not null);
        if (retry) Assert.Equal($"post_teleport_source_stale; source={source.SourceTimestamp100ns}", reason);
    }

    /// <summary>Preparation, later orientation/verification and post-recognition failures never acquire this allowance.</summary>
    [Theory]
    [InlineData(false, "after_capture")]
    [InlineData(true, "after_recognition")]
    [InlineData(true, "prepare_after_world")]
    [InlineData(true, "capture")]
    public void InitialAllowanceIsLimitedToItsExactStage(bool initial, string stage)
    {
        var epoch = Guid.NewGuid(); var source = Source(epoch, 700);
        Assert.Null(NativeNavigationResetOperations.InitialSourceRetryReason(source, Now, epoch, initial, stage));
        Assert.Equal("source_age_exceeds_500ms", NativeNavigationResetOperations.SourceRejectionReason(source, Now, epoch));
    }

    /// <summary>Staleness cannot hide a different generation or establish a new expected epoch.</summary>
    [Fact]
    public void StaleChangedOrUnpinnedEpochRemainsTerminal()
    {
        var epoch = Guid.NewGuid(); var source = Source(epoch, 700); var expected = Guid.NewGuid();
        Assert.Equal("source_epoch_changed", NativeNavigationResetOperations.SourceRejectionReason(source, Now, expected));
        Assert.Null(NativeNavigationResetOperations.InitialSourceRetryReason(source, Now, expected, true, "after_capture"));
        Assert.Null(NativeNavigationResetOperations.InitialSourceRetryReason(source, Now, null, true, "after_capture"));
        Assert.Null(NativeNavigationResetOperations.InitialSourceRetryReason(source, Now, Guid.Empty, true, "after_capture"));
    }

    /// <summary>Missing or invalid source clocks never become ordinary initial stale-frame retries.</summary>
    [Fact]
    public void InvalidSourcesCannotEnterTheAgeOnlyRetry()
    {
        var epoch = Guid.NewGuid(); var source = Source(epoch, 700);
        foreach (var invalid in new GameCaptureSourceInfo?[] { null,
            source with { CaptureEpoch = Guid.Empty }, source with { SourceTimestamp100ns = 0 },
            source with { SourceTimestamp100ns = -1 }, source with { AcquiredAtStopwatchTicks = 0 },
            source with { AcquiredAtStopwatchTicks = -1 }, source with { AcquiredAtStopwatchTicks = Now + 1 } })
        {
            Assert.False(NativeNavigationResetOperations.SourceIsFresh(invalid, Now));
            Assert.Null(NativeNavigationResetOperations.InitialSourceRetryReason(invalid, Now, epoch, true, "after_capture"));
            Assert.NotEqual("source_age_exceeds_500ms", NativeNavigationResetOperations.SourceRejectionReason(invalid, Now, epoch));
        }
    }

    /// <summary>The existing loop discards stale images before the fake recognition/consumption/input boundary, then uses only fresh evidence.</summary>
    [Fact]
    public async Task InitialStaleFramesThenFreshDoNotConsumeRejectedEvidence()
    {
        var epoch = Guid.NewGuid(); var stale = Source(epoch, 700); var fresh = Source(epoch, 80);
        var frames = new Queue<GameCaptureSourceInfo>([stale, stale, fresh]);
        var recognized = new List<GameCaptureSourceInfo>(); var delays = 0; var consumed = 0L; var barrier = 123L;
        var result = await NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            var source = frames.Dequeue();
            if (NativeNavigationResetOperations.InitialSourceRetryReason(source, Now, epoch, true, "after_capture") is { } reason)
                return Task.FromResult(new NavigationResetPoseProbe(null, reason));
            Assert.Null(NativeNavigationResetOperations.SourceRejectionReason(source, Now, epoch));
            recognized.Add(source); consumed = source.SourceTimestamp100ns;
            return Task.FromResult(new NavigationResetPoseProbe(Sample(source), null));
        }, (milliseconds, ct) =>
        {
            ct.ThrowIfCancellationRequested(); Assert.Equal(120, milliseconds);
            Assert.Empty(recognized); Assert.Equal(0, consumed); Assert.Equal(123, barrier); delays++;
            return Task.CompletedTask;
        }, CancellationToken.None);
        Assert.Equal(2, delays); Assert.Empty(frames); Assert.Same(fresh, recognized.Single());
        Assert.Equal(fresh.SourceTimestamp100ns, result.SourceTimestamp100ns);
        Assert.Equal(fresh.SourceTimestamp100ns, consumed); Assert.Equal(123, barrier);
        // A returned sample ends this initial acquisition; the later caller must omit the initial allowance.
        Assert.Null(NativeNavigationResetOperations.InitialSourceRetryReason(stale, Now, epoch, false, "after_capture"));
    }

    /// <summary>Persistent old pixels cannot become a pose and retain the existing finite attempt/diagnostic bounds.</summary>
    [Fact]
    public async Task PersistentStaleFramesExhaustExistingAttempts()
    {
        var epoch = Guid.NewGuid(); var source = Source(epoch, 900); var probes = 0; var waits = 0;
        var error = await Assert.ThrowsAsync<TimeoutException>(() => NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            probes++;
            return Task.FromResult(new NavigationResetPoseProbe(null,
                NativeNavigationResetOperations.InitialSourceRetryReason(source, Now, epoch, true, "after_capture")));
        }, (milliseconds, _) => { Assert.Equal(120, milliseconds); waits++; return Task.CompletedTask; }, CancellationToken.None));
        Assert.Equal(25, probes); Assert.Equal(24, waits);
        Assert.Contains("last=post_teleport_source_stale; source=", error.Message);
        Assert.Equal(TimeSpan.FromSeconds(3), NavigationResetPoseAcquisition.SettleTimeout);
    }

    /// <summary>Both an already-cancelled owner and cancellation during the first retry prevent subsequent recognition.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task CancellationNeverAdvancesPastDiscardedSource(bool cancelledBeforeProbe)
    {
        using var stop = new CancellationTokenSource(); if (cancelledBeforeProbe) stop.Cancel();
        var epoch = Guid.NewGuid(); var source = Source(epoch, 700); var probes = 0;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            probes++;
            return Task.FromResult(new NavigationResetPoseProbe(null,
                NativeNavigationResetOperations.InitialSourceRetryReason(source, Now, epoch, true, "after_capture")));
        }, (milliseconds, ct) => { Assert.Equal(120, milliseconds); stop.Cancel(); return Task.FromCanceled(ct); }, stop.Token));
        Assert.Equal(cancelledBeforeProbe ? 0 : 1, probes);
    }

    /// <summary>The same acquisition deadline cancels the wait and retains the last stale-source reason, without widening freshness.</summary>
    [Fact]
    public async Task AcquisitionDeadlineStopsInitialSourceSettling()
    {
        var epoch = Guid.NewGuid(); var source = Source(epoch, 700); var probes = 0;
        var error = await Assert.ThrowsAsync<TimeoutException>(() => NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            probes++;
            return Task.FromResult(new NavigationResetPoseProbe(null,
                NativeNavigationResetOperations.InitialSourceRetryReason(source, Now, epoch, true, "after_capture")));
        }, (_, ct) => Task.Delay(Timeout.Infinite, ct), CancellationToken.None, TimeSpan.FromMilliseconds(100)));
        Assert.Equal(1, probes); Assert.Contains("last=post_teleport_source_stale; source=", error.Message);
        Assert.False(NativeNavigationResetOperations.SourceIsFresh(source, Now));
    }
}
