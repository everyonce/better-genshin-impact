using System.Diagnostics;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.GameTask.NavigationReset;
using BetterGenshinImpact.GameTask.Runtime;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Pending consumes existing native windows and never grants input, pose or source-age authority.</summary>
public sealed class NavigationReadbackPendingTests
{
    /// <summary>Preparation waits at its original cadence, returning only after a fully ready native probe.</summary>
    [Fact]
    public async Task PreparationPendingThenFreshUsesOriginalAttemptWindow()
    {
        var calls = 0; var waits = new List<int>();
        await NavigationResetPreparationReadiness.WaitAsync((ordinal, _) =>
        {
            Assert.Equal(++calls, ordinal);
            return calls < 3 ? NavigationResetPreparationState.ReadbackPending : NavigationResetPreparationState.Ready;
        }, (delay, _) => { waits.Add(delay); return Task.CompletedTask; }, default, () => 1);
        Assert.Equal(3, calls); Assert.Equal(new[] { 120, 120 }, waits);
    }

    /// <summary>A pending interval may not reset the25-probe or3-second preparation bounds.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public async Task PreparationPendingBudgetIsFinite(bool lateReady)
    {
        long now = 1; var calls = 0;
        var error = await Assert.ThrowsAsync<NavigationResetPreparationTimeoutException>(() =>
            NavigationResetPreparationReadiness.WaitAsync((_, _) =>
            {
                calls++;
                if (lateReady) { now += Stopwatch.Frequency * 3; return NavigationResetPreparationState.Ready; }
                return NavigationResetPreparationState.ReadbackPending;
            }, (_, _) => Task.CompletedTask, default, () => now));
        Assert.Equal(lateReady ? 1 : 25, calls);
        Assert.Contains(lateReady ? "ready_but_expired" : "readback_pending", error.Message);
    }

    /// <summary>Hard native failures and owner cancellation are never translated to a Pending retry.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public async Task PreparationHardFailureAndCancellationStopImmediately(bool cancel)
    {
        using var stop = new CancellationTokenSource(); var calls = 0; var waits = 0;
        var work = NavigationResetPreparationReadiness.WaitAsync((_, _) =>
        {
            calls++;
            if (cancel) { stop.Cancel(); return NavigationResetPreparationState.ReadbackPending; }
            throw new InvalidOperationException("source_epoch_changed");
        }, (_, _) => { waits++; return Task.CompletedTask; }, stop.Token, () => 1);
        if (cancel) await Assert.ThrowsAnyAsync<OperationCanceledException>(() => work);
        else Assert.Equal("source_epoch_changed", (await Assert.ThrowsAsync<InvalidOperationException>(() => work)).Message);
        Assert.Equal(1, calls); Assert.Equal(0, waits);
    }

    /// <summary>Pose acquisition's unchanged no-input retry admits no synthetic pose and caps pending attempts.</summary>
    [Fact]
    public async Task ResetPosePendingUsesExisting25AttemptLimit()
    {
        var calls = 0; var waits = 0;
        var error = await Assert.ThrowsAsync<TimeoutException>(() => NavigationResetPoseAcquisition.ReadAsync(
            _ => { calls++; return Task.FromResult(new NavigationResetPoseProbe(null, "readback_pending")); },
            (delay, _) => { Assert.Equal(120, delay); waits++; return Task.CompletedTask; }, default));
        Assert.Equal(25, calls); Assert.Equal(24, waits); Assert.Contains("readback_pending", error.Message);
    }

    /// <summary>Expected Pending stores only unpublished metadata, not source-age/barrier or accepted pixels.</summary>
    [Fact]
    public void PollMetadataDoesNotFabricateAFrameOrAge()
    {
        var pending = GameCaptureReadbackConsumerTests.Pending();
        var poll = new NavigationBaselineCapturePoll(0, 100);
        poll.RecordReadback(new(GameCaptureAttemptOutcome.ReadbackPending, pending: pending));
        Assert.Equal("readback_pending", poll.Result); Assert.Same(pending, poll.PendingReadback);
        Assert.Null(poll.Source); Assert.Null(poll.SourceAgeMs); Assert.Null(poll.DuplicateOfAccepted);
        Assert.Null(poll.ReportedBarrierMarginMs); Assert.Null(poll.AcquisitionBarrierMarginMs);
    }

    /// <summary>Expected Pending uses5ms with target/cancellation checks; ordinary recovery waits stay separate.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public async Task BaselineWaitRetainsCadenceAndChecks(bool recovering)
    {
        double now = 1000; var checks = 0; var waits = 0;
        var poll = new NavigationBaselineCapturePoll(0, now);
        await NativeNavigationBaselineOperations.WaitForReadbackAsync(poll, () => checks++, () => now,
            (deadline, _) => { waits++; now = deadline; return Task.CompletedTask; }, recovering, default);
        Assert.Equal(1005, now); Assert.Equal(2, checks); Assert.Equal(1, waits);
        Assert.Equal(now, poll.WaitExitedAtMs); Assert.Null(poll.Source); Assert.Null(poll.SourceAgeMs);
    }

    /// <summary>The real input owner expires during Pending; no new source or input renewal is supplied by the wait.</summary>
    [Fact]
    public async Task BaselinePendingWaitCannotRenewOrHideLeaseExpiry()
    {
        double now = 1000; var downs = 0; var ups = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => downs++, () => ups++, _ => { }, default, false, "v4");
        lease.EnableRecovery();
        var source = new GameCaptureSourceInfo(Guid.NewGuid(), 990 * 10000L, 990 * Stopwatch.Frequency / 1000);
        lease.Forward(source, default);
        var poll = new NavigationBaselineCapturePoll(0, now);
        void Check()
        {
            lease.Check();
            if (lease.PendingRecovery is not null) throw new InvalidOperationException("existing_lease_recovery");
        }
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => NativeNavigationBaselineOperations.WaitForReadbackAsync(
            poll, Check, () => now, (_, _) => { now = 1150; lease.Check(); return Task.CompletedTask; }, false, default));
        Assert.Equal("existing_lease_recovery", error.Message); Assert.False(lease.ForwardHeld);
        Assert.Equal(1, downs); Assert.Equal(1, ups); Assert.Single(lease.RecoveryPauses);
        Assert.Equal(1150, poll.WaitExitedAtMs);
    }

    /// <summary>Unclassified calls retain conservative final charges and the original terminal close barrier.</summary>
    [Fact]
    public async Task FinalUnclassifiedCapturesKeepOriginalCloseAnd32CaptureLimit()
    {
        double now = 1100;
        var source = new GameCaptureSourceInfo(Guid.NewGuid(), 900 * 10000L, 900 * Stopwatch.Frequency / 1000);
        var final = new NavigationBaselineFinalVerification(() => now, 1000, 31000, source, 0, 0);
        for (var i = 0; i < 32; i++)
        {
            final.BeginCapture(default).Dispose();
            var poll = new NavigationBaselineCapturePoll(0, now);
            await NativeNavigationBaselineOperations.WaitForReadbackAsync(poll, () => final.Check(default), () => now,
                (deadline, _) => { now = deadline; return Task.CompletedTask; }, false, default);
        }
        Assert.Equal("final_verification_capture_limit_exceeded", Assert.Throws<InvalidOperationException>(() => final.BeginCapture(default)).Message);
        Assert.Equal(32, final.Record.CaptureCount); Assert.Equal(1000, final.ClosedAtMs); Assert.Equal(3000, final.Record.DeadlineAtMs);
        Assert.Empty(final.Record.AcceptedReadIndices); Assert.Equal(0, final.Record.SourceAgeDiscards);
    }

    /// <summary>An age-discarded valid header remains the ordering floor, but Pending never advances that floor or accepted evidence.</summary>
    [Theory]
    [InlineData(-1, false)] [InlineData(0, true)] [InlineData(1, true)]
    public void FinalPendingCannotRegressBehindDiscardedHeaderOrAdvanceAuthority(int delta, bool valid)
    {
        var epoch = Guid.NewGuid();
        GameCaptureSourceInfo Source(long ms) => new(epoch, ms * 10000, ms * Stopwatch.Frequency / 1000);
        var before = Source(900); var stale = Source(1100);
        var final = new NavigationBaselineFinalVerification(() => 1300, 1000, 31000, before, 0, 0);
        var read = new NavigationBaselineObservationAttempt(1200);
        Assert.Throws<NavigationBaselineFinalVerification.SourceAgeException>(() =>
            final.ValidateSource(stale, "after_capture", read, default));
        Assert.Equal(stale, final.SeenSource);
        var pending = new GameCapturePendingReadback(1, Source(1100 + delta), 1200 * Stopwatch.Frequency / 1000, 1920, 1080, null);
        void Validate() => GameCaptureReadbackConsumer.ValidatePending(pending, 1300 * Stopwatch.Frequency / 1000, final.SeenSource!.WgcSource);
        if (valid) Validate();
        else Assert.Equal("native_source_regressed", Assert.Throws<InvalidOperationException>((Action)Validate).Message);
        Assert.Equal(stale, final.SeenSource); Assert.Equal(1000, final.ClosedAtMs);
        Assert.Empty(final.Record.AcceptedReadIndices); Assert.Equal(0, final.Record.CaptureCount);
    }

    /// <summary>A late pending continuation cannot extend the terminal deadline or manufacture a successful final source.</summary>
    [Fact]
    public async Task FinalPendingDeadlineAndCancellationRemainTerminal()
    {
        // Both source clocks belong to the same synthetic second as this test's window clock.
        double now = 1100; var source = new GameCaptureSourceInfo(Guid.NewGuid(), 10_000_000, Stopwatch.Frequency);
        var final = new NavigationBaselineFinalVerification(() => now, 1000, 31000, source, 0, 0);
        final.BeginCapture(default).Dispose(); var poll = new NavigationBaselineCapturePoll(0, now);
        await Assert.ThrowsAsync<NavigationBaselineFinalVerification.TimeoutException>(() => NativeNavigationBaselineOperations.WaitForReadbackAsync(poll,
            () => final.Check(default), () => now, (_, _) => { now = 3000; return Task.CompletedTask; }, false, default));
        Assert.Equal(3000, poll.WaitExitedAtMs); Assert.Equal(1, final.Record.CaptureCount); Assert.Equal(1000, final.ClosedAtMs);
        using var stop = new CancellationTokenSource(); stop.Cancel(); var waits = 0;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => NativeNavigationBaselineOperations.WaitForReadbackAsync(
            new(0, now), () => { }, () => now, (_, _) => { waits++; return Task.CompletedTask; }, false, stop.Token));
        Assert.Equal(0, waits);
    }
}
