using System.Diagnostics;
using BetterGenshinImpact.GameTask.NavigationReset;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Pure bounded pose-source retry checks; no runtime, logger, model, capture backend or input is initialized.</summary>
public sealed class NavigationResetSourceRetryTests
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
        foreach (var stage in new[] { "after_capture", "after_recognition" })
        {
            var reason = NativeNavigationResetOperations.PoseSourceRetryReason(source, Now, epoch, stage);
            Assert.Equal(retry, reason is not null);
            if (retry) Assert.Equal($"pose_source_stale; stage={stage}; source={source.SourceTimestamp100ns}", reason);
        }
    }

    /// <summary>Only the two pose-source stages can discard stale sources; preparation and backend failures remain strict.</summary>
    [Theory]
    [InlineData("after_capture", true)]
    [InlineData("after_recognition", true)]
    [InlineData("prepare_after_world", false)]
    [InlineData("capture", false)]
    [InlineData("", false)]
    public void AgeAllowanceIsLimitedToPoseStages(string stage, bool retry)
    {
        var epoch = Guid.NewGuid(); var source = Source(epoch, 700);
        Assert.Equal(retry, NativeNavigationResetOperations.PoseSourceRetryReason(source, Now, epoch, stage) is not null);
        Assert.Equal("source_age_exceeds_500ms", NativeNavigationResetOperations.SourceRejectionReason(source, Now, epoch));
    }

    /// <summary>Staleness cannot hide a different generation or establish a new expected epoch.</summary>
    [Fact]
    public void StaleChangedOrUnpinnedEpochRemainsTerminal()
    {
        var epoch = Guid.NewGuid(); var source = Source(epoch, 700); var expected = Guid.NewGuid();
        Assert.Equal("source_epoch_changed", NativeNavigationResetOperations.SourceRejectionReason(source, Now, expected));
        foreach (var stage in new[] { "after_capture", "after_recognition" })
        {
            Assert.Null(NativeNavigationResetOperations.PoseSourceRetryReason(source, Now, expected, stage));
            Assert.Null(NativeNavigationResetOperations.PoseSourceRetryReason(source, Now, null, stage));
            Assert.Null(NativeNavigationResetOperations.PoseSourceRetryReason(source, Now, Guid.Empty, stage));
        }
    }

    /// <summary>Missing or invalid source clocks never become ordinary stale-frame retries at either pose stage.</summary>
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
            Assert.Null(NativeNavigationResetOperations.PoseSourceRetryReason(invalid, Now, epoch, "after_capture"));
            Assert.Null(NativeNavigationResetOperations.PoseSourceRetryReason(invalid, Now, epoch, "after_recognition"));
            Assert.NotEqual("source_age_exceeds_500ms", NativeNavigationResetOperations.SourceRejectionReason(invalid, Now, epoch));
        }
    }

    /// <summary>The existing loop discards stale images before the fake recognition/consumption/input boundary, then uses only fresh evidence.</summary>
    [Fact]
    public async Task StaleFramesThenFreshDoNotConsumeRejectedEvidence()
    {
        var epoch = Guid.NewGuid(); var stale = Source(epoch, 700); var fresh = Source(epoch, 80);
        var frames = new Queue<GameCaptureSourceInfo>([stale, stale, fresh]);
        var recognized = new List<GameCaptureSourceInfo>(); var delays = 0; var consumed = 0L; var barrier = 123L;
        var result = await NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            var source = frames.Dequeue();
            if (NativeNavigationResetOperations.PoseSourceRetryReason(source, Now, epoch, "after_capture") is { } reason)
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
        // A later orientation or verification acquisition has the same age-only rule, independently of initial HUD settling.
        Assert.NotNull(NativeNavigationResetOperations.PoseSourceRetryReason(stale, Now, epoch, "after_capture"));
    }

    /// <summary>Expiry during recognition preserves consumed clocks and the preceding camera barrier, never authorizing another input.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task RecognitionExpiryRetainsHighWaterUntilAnIndependentlyFreshPose(bool orienting)
    {
        var epoch = Guid.NewGuid(); var expiring = Source(epoch, 100);
        var fresh = new GameCaptureSourceInfo(epoch, 24_500_000L, Stopwatch.Frequency * 245 / 100);
        var frames = new Queue<GameCaptureSourceInfo>([expiring, expiring, fresh]);
        var now = Now; var consumedTimestamp = 0L; var consumedAcquisition = 0L;
        var inputBarrier = Now - Stopwatch.Frequency / 5; var originalBarrier = inputBarrier;
        var recognized = 0; var cameraCommands = 0; var waits = 0;
        var result = await NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            var source = frames.Dequeue();
            if (NativeNavigationResetOperations.PoseSourceRetryReason(source, now, epoch, "after_capture") is { } captureReason)
                return Task.FromResult(new NavigationResetPoseProbe(null, captureReason));
            Assert.Null(NativeNavigationResetOperations.SourceRejectionReason(source, now, epoch));
            Assert.True(source.SourceTimestamp100ns > consumedTimestamp);
            Assert.True(source.AcquiredAtStopwatchTicks > consumedAcquisition);
            Assert.True(NativeNavigationResetOperations.SourceIsAfterBarrier(source, inputBarrier));
            consumedTimestamp = source.SourceTimestamp100ns; consumedAcquisition = source.AcquiredAtStopwatchTicks;
            recognized++;
            // The first recognition consumes 500ms; its valid-at-capture source is now 600ms old.
            now = Now + Stopwatch.Frequency / 2;
            if (NativeNavigationResetOperations.PoseSourceRetryReason(source, now, epoch, "after_recognition") is { } recognitionReason)
                return Task.FromResult(new NavigationResetPoseProbe(null, recognitionReason));
            Assert.Null(NativeNavigationResetOperations.SourceRejectionReason(source, now, epoch));
            if (orienting) { cameraCommands++; inputBarrier = now; }
            return Task.FromResult(new NavigationResetPoseProbe(Sample(source), null));
        }, (milliseconds, ct) =>
        {
            ct.ThrowIfCancellationRequested(); Assert.Equal(120, milliseconds); waits++;
            Assert.Equal(expiring.SourceTimestamp100ns, consumedTimestamp);
            Assert.Equal(expiring.AcquiredAtStopwatchTicks, consumedAcquisition);
            Assert.Equal(originalBarrier, inputBarrier); Assert.Equal(0, cameraCommands); Assert.Equal(1, recognized);
            return Task.CompletedTask;
        }, CancellationToken.None);
        Assert.Equal(2, waits); Assert.Equal(2, recognized); Assert.Empty(frames);
        Assert.Equal(orienting ? 1 : 0, cameraCommands);
        Assert.Equal(fresh.SourceTimestamp100ns, result.SourceTimestamp100ns);
        Assert.Equal(fresh.SourceTimestamp100ns, consumedTimestamp);
        Assert.Equal(fresh.AcquiredAtStopwatchTicks, consumedAcquisition);
        Assert.Equal(orienting ? now : originalBarrier, inputBarrier);
    }

    /// <summary>A later acquisition starts its own bounded wait after a prior successful pose; no initial-HUD flag enables it.</summary>
    [Fact]
    public async Task LaterPoseAcquisitionsUseTheSameBoundedAgeRule()
    {
        var epoch = Guid.NewGuid(); var waits = 0; var lastConsumed = 0L;
        for (var acquisition = 0; acquisition < 3; acquisition++)
        {
            var now = Now + Stopwatch.Frequency * acquisition;
            var stale = new GameCaptureSourceInfo(epoch, (20_000_000L + acquisition * 10_000_000L) - 9_000_000L,
                now - Stopwatch.Frequency * 9 / 10);
            var fresh = new GameCaptureSourceInfo(epoch, (20_000_000L + acquisition * 10_000_000L) - 800_000L,
                now - Stopwatch.Frequency * 8 / 100);
            var frames = new Queue<GameCaptureSourceInfo>([stale, fresh]);
            var result = await NavigationResetPoseAcquisition.ReadAsync(_ =>
            {
                var source = frames.Dequeue();
                var reason = NativeNavigationResetOperations.PoseSourceRetryReason(source, now, epoch, "after_capture");
                return Task.FromResult(reason is not null ? new NavigationResetPoseProbe(null, reason)
                    : new NavigationResetPoseProbe(Sample(source), null));
            }, (milliseconds, ct) =>
            {
                ct.ThrowIfCancellationRequested(); Assert.Equal(120, milliseconds); waits++;
                return Task.CompletedTask;
            }, CancellationToken.None);
            Assert.Empty(frames); Assert.Equal(fresh.SourceTimestamp100ns, result.SourceTimestamp100ns);
            Assert.True(result.SourceTimestamp100ns > lastConsumed); lastConsumed = result.SourceTimestamp100ns!.Value;
        }
        Assert.Equal(3, waits);
    }

    /// <summary>Persistent old pixels cannot become a pose and retain the existing finite attempt/diagnostic bounds.</summary>
    [Theory]
    [InlineData("after_capture")]
    [InlineData("after_recognition")]
    public async Task PersistentStaleFramesExhaustExistingAttempts(string stage)
    {
        var epoch = Guid.NewGuid(); var source = Source(epoch, 900); var probes = 0; var waits = 0;
        var error = await Assert.ThrowsAsync<TimeoutException>(() => NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            probes++;
            return Task.FromResult(new NavigationResetPoseProbe(null,
                NativeNavigationResetOperations.PoseSourceRetryReason(source, Now, epoch, stage)));
        }, (milliseconds, _) => { Assert.Equal(120, milliseconds); waits++; return Task.CompletedTask; }, CancellationToken.None));
        Assert.Equal(25, probes); Assert.Equal(24, waits);
        Assert.Contains($"last=pose_source_stale; stage={stage}; source=", error.Message);
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
                NativeNavigationResetOperations.PoseSourceRetryReason(source, Now, epoch, "after_capture")));
        }, (milliseconds, ct) => { Assert.Equal(120, milliseconds); stop.Cancel(); return Task.FromCanceled(ct); }, stop.Token));
        Assert.Equal(cancelledBeforeProbe ? 0 : 1, probes);
    }

    /// <summary>The same acquisition deadline cancels the wait and retains the last stale-source reason, without widening freshness.</summary>
    [Fact]
    public async Task AcquisitionDeadlineStopsSourceSettling()
    {
        var epoch = Guid.NewGuid(); var source = Source(epoch, 700); var probes = 0;
        var error = await Assert.ThrowsAsync<TimeoutException>(() => NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            probes++;
            return Task.FromResult(new NavigationResetPoseProbe(null,
                NativeNavigationResetOperations.PoseSourceRetryReason(source, Now, epoch, "after_capture")));
        }, (_, ct) => Task.Delay(Timeout.Infinite, ct), CancellationToken.None, TimeSpan.FromMilliseconds(100)));
        Assert.Equal(1, probes); Assert.Contains("last=pose_source_stale; stage=after_capture; source=", error.Message);
        Assert.False(NativeNavigationResetOperations.SourceIsFresh(source, Now));
    }
}
