using System.Diagnostics;
using System.IO;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Opt-in recovery uses fake native sinks and clocks only; no game, GPU or input API is invoked.</summary>
public sealed class NavigationBaselineRecoveryTests
{
    /// <summary>One immutable fake capture generation.</summary>
    private static readonly Guid Epoch = Guid.Parse("6f638d42-4151-48dc-9cc7-28997f0c6c55");
    /// <summary>Independent native clocks, including a reported stamp ahead of acquisition.</summary>
    private static GameCaptureSourceInfo Source(double acquired, double? reported = null) => new(Epoch,
        (long)((reported ?? acquired) * 10_000), (long)(acquired * Stopwatch.Frequency / 1000));
    /// <summary>Fault assertions precede cleanup; no intentional fault may leave a test worker alive.</summary>
    private static async Task Drain(NavigationBaselineInputLease lease)
    { try { await lease.DisposeAsync(); } catch (InvalidOperationException) { } }

    /// <summary>The same lease token survives a pause; resume sends no input and preserves run-first/grant semantics.</summary>
    [Fact]
    public async Task ExpiryReleasesAndResumesWithoutPressingOrCancellingTheOwner()
    {
        double now = 1000; var downs = 0; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => ups++, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); var token = lease.Token;
            Assert.True(lease.Forward(Source(990), default).FirstForwardAttempt);
            now = 1150; lease.Check();
            var pause = Assert.IsType<NavigationBaselineRecoveryPause>(lease.PendingRecovery);
            Assert.Equal(NavigationBaselineRecoveryCause.LeaseExpired, pause.Cause);
            Assert.Null(lease.Fault); Assert.False(token.IsCancellationRequested); Assert.Equal(token, lease.Token);
            Assert.False(lease.ForwardHeld); Assert.Equal(1, downs); Assert.Equal(1, ups);
            now = 1240; lease.ResumeRecovery(pause, Source(1230), default);
            Assert.Null(lease.PendingRecovery); Assert.Equal(1, downs); Assert.Equal(1, ups);
            var next = lease.Forward(Source(1230), default);
            Assert.False(next.FirstForwardAttempt); Assert.Equal(150, next.GrantMs); Assert.Equal(1390, next.ExpiresAtMs);
            now = 1250; var renewal = lease.Forward(Source(1245), default);
            Assert.Equal(100, renewal.GrantMs); Assert.Equal(1350, renewal.ExpiresAtMs); Assert.Equal(2, downs);
            Assert.Single(lease.RecoveryPauses);
        }
        finally { await Drain(lease); }
    }

    /// <summary>A same-thread keyup callback cannot re-press while release is still in progress.</summary>
    [Fact]
    public async Task PauseLatchesBeforeCallingTheReleaseSink()
    {
        double now = 1000; var downs = 0; Exception? attempted = null;
        NavigationBaselineInputLease? lease = null;
        lease = new(() => now, () => true, () => downs++,
            () => attempted = Record.Exception(() => lease!.Forward(Source(1140), default)), _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1150; lease.Check();
            Assert.IsType<InvalidOperationException>(attempted); Assert.Equal("recovery_release_in_progress", attempted!.Message);
            Assert.Equal(1, downs); Assert.False(lease.ForwardHeld); Assert.NotNull(lease.PendingRecovery);
        }
        finally { await Drain(lease); }
    }

    /// <summary>Resume requires both post-release clocks and the exact ticket instance, not matching values.</summary>
    [Theory]
    [InlineData("reported")]
    [InlineData("acquired")]
    [InlineData("copied-ticket")]
    [InlineData("closed")]
    public async Task AStaleOrSupersededResumeNeverPresses(string failure)
    {
        double now = 1000; var downs = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => { }, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1150; lease.Check();
            var ticket = lease.PendingRecovery!; now = 1240;
            var sample = failure == "reported" ? Source(1230, 1229) : failure == "acquired" ? Source(1229, 1230) : Source(1230);
            if (failure == "copied-ticket") ticket = ticket with { };
            if (failure == "closed") lease.Close();
            Assert.Throws<InvalidOperationException>(() => lease.ResumeRecovery(ticket, sample, default));
            Assert.Equal(1, downs); Assert.False(lease.ForwardHeld);
        }
        finally { await Drain(lease); }
    }

    /// <summary>Pause does not stop target, cancellation or monotonic-clock checks; all remain terminal.</summary>
    [Theory]
    [InlineData("target", "game_target_lost")]
    [InlineData("cancel", "baseline_cancelled")]
    [InlineData("clock", "invalid_lease_clock")]
    [InlineData("deadline", "recovery_deadline_exceeded")]
    public async Task TheSingleWatchdogKeepsCheckingDuringPause(string reason, string expected)
    {
        double now = 1000; var available = true; using var cancel = new CancellationTokenSource();
        var lease = new NavigationBaselineInputLease(() => now, () => available, () => { }, () => { }, _ => { }, cancel.Token, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1150; lease.Check();
            if (reason == "target") available = false;
            if (reason == "cancel") cancel.Cancel();
            now = reason == "clock" ? 1149 : reason == "deadline" ? 3150 : 1160;
            lease.Check(); Assert.Equal(expected, lease.Fault); Assert.True(lease.Token.IsCancellationRequested);
            Assert.False(lease.ForwardHeld);
        }
        finally { await Drain(lease); }
    }

    /// <summary>An already-expired hold releases before slow availability, while target loss still terminates recovery.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ExpiredHoldReleasesBeforeDelayedTargetValidation(bool stillAvailable)
    {
        double now = 1000; var delay = false; var ups = 0; var releasedBeforeAvailability = false;
        var lease = new NavigationBaselineInputLease(() => now, () =>
        {
            if (!delay) return true;
            releasedBeforeAvailability = ups == 1;
            now += 60;
            return stillAvailable;
        }, () => { }, () => ups++, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1150; delay = true; lease.Check();
            Assert.True(releasedBeforeAvailability); Assert.Equal(1150, lease.Events.Single(row => row.Kind == "w_up").CompletedAtMs);
            Assert.False(lease.ForwardHeld);
            if (stillAvailable) Assert.Null(lease.Fault);
            else { Assert.Equal("game_target_lost", lease.Fault); Assert.True(lease.Token.IsCancellationRequested); }
        }
        finally { delay = false; await Drain(lease); }
    }

    /// <summary>Malformed identity accompanying an expired grant never becomes a recoverable expiry.</summary>
    [Theory]
    [InlineData("epoch", "source_epoch_changed")]
    [InlineData("regression", "native_source_regressed")]
    [InlineData("future-acquisition", "acquisition_in_future")]
    [InlineData("empty", "invalid_native_source")]
    public async Task HardMetadataWinsOverSimultaneousExpiry(string fault, string expected)
    {
        double now = 1000; var downs = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => { }, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1200;
            var sample = fault switch { "epoch" => Source(1190) with { CaptureEpoch = Guid.NewGuid() },
                "regression" => Source(989), "future-acquisition" => Source(1201), _ => Source(1190) with { SourceTimestamp100ns = 0 } };
            Assert.Equal(expected, Assert.Throws<InvalidOperationException>(() => lease.Forward(sample, default)).Message);
            Assert.Equal(expected, lease.Fault); Assert.Empty(lease.RecoveryPauses); Assert.Equal(1, downs);
        }
        finally { await Drain(lease); }
    }

    /// <summary>Positive sole-age rejection is distinct from invalid timing and releases before throwing the typed origin.</summary>
    [Fact]
    public async Task SoleAgeCanPauseWithoutReplayingAnInput()
    {
        double now = 1000; var downs = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => { }, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1050; lease.ReleaseForward(); now = 1200;
            var interruption = Assert.Throws<NavigationBaselineRecoveryRequired>(() => lease.Forward(Source(1000), default));
            Assert.Equal(NavigationBaselineRecoveryCause.SourceAge, interruption.Cause);
            Assert.Same(lease.PendingRecovery, interruption.Pause); Assert.Equal(Source(1000), interruption.ObservedSource?.WgcSource);
            Assert.False(lease.ForwardHeld); Assert.Null(lease.Fault); Assert.Equal(1, downs);
        }
        finally { await Drain(lease); }
    }

    /// <summary>The observed r25 after-camera age failure can wait/rearm when W was already released.</summary>
    [Fact]
    public async Task SourceAgeRecoveryAfterCameraDoesNotInventHeldInputOrReplayTheCamera()
    {
        double now = 1000; var downs = 0; var ups = 0; var cameras = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => ups++, _ => cameras++, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Rotate(Source(990), 2, default); now = 2000;
            var interruption = new NavigationBaselineRecoveryRequired(NavigationBaselineRecoveryCause.SourceAge, "after_capture", Source(1034));
            var pause = lease.PauseForRecovery(interruption, default);
            Assert.Equal(NavigationBaselineRecoveryCause.SourceAge, pause.Cause);
            Assert.Equal(2000, pause.ReleasedAtMs); Assert.Null(lease.Fault); Assert.False(lease.ForwardHeld);
            now = 2090; lease.ResumeRecovery(pause, Source(2080), default);
            Assert.Equal(0, downs); Assert.Equal(0, ups); Assert.Equal(1, cameras);
            Assert.True(lease.Forward(Source(2080), default).FirstForwardAttempt);
            Assert.Equal(1, downs); Assert.Equal(1, cameras);
        }
        finally { await Drain(lease); }
    }

    /// <summary>The first post-recovery physical start still obeys whichever immutable source clock is older.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RecoveredStartRetainsTheOlderSourcePlus250Cap(bool olderReported)
    {
        double now = 1000;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { }, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1150; lease.Check();
            var pause = lease.PendingRecovery!; now = 1355;
            var source = olderReported ? Source(1350, 1230) : Source(1230, 1400);
            lease.ResumeRecovery(pause, source, default);
            var start = lease.Forward(source, default);
            Assert.Equal(150, start.GrantMs); Assert.Equal(1230, start.SourceAnchorAtMs);
            Assert.Equal(1480, start.SourceCapAtMs); Assert.Equal(1480, start.ExpiresAtMs);
            Assert.False(start.FirstForwardAttempt);
        }
        finally { await Drain(lease); }
    }

    /// <summary>Failed keyup is terminal even when cleanup's second attempt subsequently succeeds.</summary>
    [Fact]
    public async Task UncertainReleaseCanNeverBeRearmed()
    {
        double now = 1000; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { },
            () => { if (++ups == 1) throw new IOException("uncertain-up"); }, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1150; lease.Check();
            Assert.Equal("input_release_failed", lease.Fault); Assert.Equal("uncertain-up", lease.ReleaseError);
            Assert.Equal("uncertain-up", Assert.Single(lease.RecoveryPauses).ReleaseError);
            now = 1240; Assert.Throws<InvalidOperationException>(() => lease.ResumeRecovery(lease.PendingRecovery!, Source(1230), default));
            Assert.True(ups >= 2);
        }
        finally { await Drain(lease); }
    }

    /// <summary>The third interruption closes rather than extending either the count or original watchdog lifetime.</summary>
    [Fact]
    public async Task ThirdRecoveryIsTerminalAndDoesNotResetRunFirst()
    {
        double now = 1000;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { }, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default);
            for (var index = 0; index < 2; index++)
            {
                now += 150; lease.Check(); var pause = lease.PendingRecovery!;
                now += 90; lease.ResumeRecovery(pause, Source(now - 10), default);
                Assert.False(lease.Forward(Source(now - 10), default).FirstForwardAttempt);
            }
            now += 150; lease.Check(); Assert.Equal("recovery_limit_exceeded", lease.Fault);
            Assert.Equal(2, lease.RecoveryPauses.Length); Assert.False(lease.ForwardHeld);
        }
        finally { await Drain(lease); }
    }

    /// <summary>V1-v3 and the pre-anchor v4 phase retain terminal expiry, without implicit recovery admission.</summary>
    [Theory]
    [InlineData("v1")]
    [InlineData("v2")]
    [InlineData("v3")]
    [InlineData("v4")]
    public async Task RecoveryNeverAppearsWithoutOptInAndVerifiedAnchor(string contract)
    {
        double now = 1000;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { }, _ => { }, default, false, contract);
        try
        {
            var start = lease.Forward(Source(990), default); now = start.ExpiresAtMs!.Value; lease.Check();
            Assert.Equal("forward_lease_expired", lease.Fault); Assert.Empty(lease.RecoveryPauses);
        }
        finally { await Drain(lease); }
    }

    /// <summary>Every duplicate/barrier capture consumes a poll; deadlines remain strict even after slow work.</summary>
    [Fact]
    public void WindowBoundsAllCaptureAdmissionsAndOwnerDeadline()
    {
        for (var index = 0; index < 32; index++) NavigationBaselineRecovery.EnsureWindow(1000 + index, 1100, index, true);
        Assert.Equal("recovery_poll_limit_exceeded", Assert.Throws<InvalidOperationException>(() =>
            NavigationBaselineRecovery.EnsureWindow(1032, 1100, 32, true)).Message);
        NavigationBaselineRecovery.EnsureWindow(1099, 1100, 32); // A completed last poll can still rearm before deadline.
        Assert.Equal("recovery_deadline_exceeded", Assert.Throws<InvalidOperationException>(() =>
            NavigationBaselineRecovery.EnsureWindow(1100, 1100, 1)).Message);
        Assert.Throws<InvalidOperationException>(() => NavigationBaselineRecovery.EnsureWindow(double.NaN, 1100, 1));
    }

    /// <summary>A blocked second keyup serializes terminal Close and an old ticket without any re-press race.</summary>
    [Fact]
    public async Task BlockedReleaseSerializesCompetingCloseAndStaleResume()
    {
        double now = 1000; var ups = 0; var downs = 0;
        using var releaseEntered = new ManualResetEventSlim(); using var allowRelease = new ManualResetEventSlim();
        using var closeEntered = new ManualResetEventSlim(); using var resumeEntered = new ManualResetEventSlim();
        var lease = new NavigationBaselineInputLease(() => Volatile.Read(ref now), () => true, () => downs++, () =>
        {
            if (++ups != 2) return;
            releaseEntered.Set();
            if (!allowRelease.Wait(TimeSpan.FromSeconds(3))) throw new TimeoutException("test release not unblocked");
        }, _ => { }, default, false, "v4");
        Task? pauseTask = null, closeTask = null; Task<Exception?>? resumeTask = null;
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1150; lease.Check();
            var oldTicket = lease.PendingRecovery!;
            now = 1240; lease.ResumeRecovery(oldTicket, Source(1230), default); lease.Forward(Source(1230), default);
            now = 1390; pauseTask = Task.Run(lease.Check);
            Assert.True(releaseEntered.Wait(TimeSpan.FromSeconds(3)));
            closeTask = Task.Run(() => { closeEntered.Set(); lease.Close(); });
            resumeTask = Task.Run(() => { resumeEntered.Set(); return Record.Exception(() => lease.ResumeRecovery(oldTicket, Source(1470), default)); });
            Assert.True(closeEntered.Wait(TimeSpan.FromSeconds(3))); Assert.True(resumeEntered.Wait(TimeSpan.FromSeconds(3)));
            Assert.False(closeTask.IsCompleted); Assert.False(resumeTask.IsCompleted);
            Volatile.Write(ref now, 1480); allowRelease.Set();
            await Task.WhenAll(pauseTask, closeTask, resumeTask).WaitAsync(TimeSpan.FromSeconds(3));
            Assert.IsType<InvalidOperationException>(await resumeTask);
            Assert.Equal(2, downs); Assert.Equal(2, ups); Assert.False(lease.ForwardHeld);
            now = 1590; Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(1580), default));
            Assert.Equal(2, downs);
        }
        finally
        {
            allowRelease.Set();
            if (pauseTask is not null) await pauseTask.WaitAsync(TimeSpan.FromSeconds(3));
            if (closeTask is not null) await closeTask.WaitAsync(TimeSpan.FromSeconds(3));
            if (resumeTask is not null) await resumeTask.WaitAsync(TimeSpan.FromSeconds(3));
            await Drain(lease);
        }
    }

    /// <summary>The actual dedicated worker continues checking while paused and Dispose awaits that same worker's exit.</summary>
    [Fact]
    public async Task RealWatchdogSurvivesPauseAndDrainsOnDispose()
    {
        double now = 1000; var ups = 0; var downs = 0; var pausedChecks = 0; var disposed = false;
        var observed = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var lease = new NavigationBaselineInputLease(() => Volatile.Read(ref now), () =>
        {
            if (Volatile.Read(ref ups) != 0 && Interlocked.Increment(ref pausedChecks) >= 2) observed.TrySetResult(true);
            return true;
        }, () => Interlocked.Increment(ref downs), () => Interlocked.Increment(ref ups), _ => { }, default, true, "v4");
        try
        {
            lease.EnableRecovery(); var token = lease.Token; lease.Forward(Source(990), default);
            Volatile.Write(ref now, 1150);
            await observed.Task.WaitAsync(TimeSpan.FromSeconds(3));
            Assert.NotNull(lease.PendingRecovery); Assert.Null(lease.Fault); Assert.False(token.IsCancellationRequested);
            Assert.Equal(1, Volatile.Read(ref ups)); Assert.Equal(1, Volatile.Read(ref downs));
            await lease.DisposeAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(3)); disposed = true;
            Assert.False(lease.ForwardHeld); Assert.Equal(1, Volatile.Read(ref downs));
        }
        finally { if (!disposed) await Drain(lease); }
    }
}
