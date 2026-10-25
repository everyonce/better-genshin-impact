using System.Diagnostics;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Endpoint close uses the actual lease with fake clock/input sinks; no watchdog, capture or OS input is started.</summary>
public sealed class NavigationBaselineEndpointLeaseTests
{
    /// <summary>One immutable host generation for synthetic acquired snapshots.</summary>
    private static readonly Guid Epoch = Guid.Parse("5847604c-a75c-4a93-a211-990ad9a85062");

    /// <summary>Construct completed host acquisition intervals without pretending to measure a render timestamp.</summary>
    private static CaptureSourceEvidence Source(long id, double startMs) =>
        new(new GameCaptureHostSnapshotInfo(Epoch, id,
            (long)(startMs * Stopwatch.Frequency / 1000),
            (long)((startMs + 1) * Stopwatch.Frequency / 1000), Stopwatch.Frequency));

    /// <summary>Dispose deliberately faulted fake leases while leaving assertions about the original fault explicit.</summary>
    private static async Task DisposeFaulted(NavigationBaselineInputLease lease)
    { try { await lease.DisposeAsync(); } catch (InvalidOperationException) { } }

    /// <summary>The exact original deadline decides expiry; permanent closure never adds another down or resume.</summary>
    [Theory]
    [InlineData(-0.001, false)]
    [InlineData(0, true)]
    [InlineData(1.3114, true)]
    public async Task ExactExpiryBoundaryClosesPermanently(double offset, bool expired)
    {
        double now = 1000; var downs = 0; var ups = 0; var moves = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => ups++,
            _ => moves++, default, false, NavigationBaselineTiming.V4);
        lease.EnableRecovery(); var grant = lease.Forward(Source(1, 990), default);
        now = 1150 + offset;
        Assert.Equal(now, lease.CloseAtEndpoint(default));
        Assert.False(lease.ForwardHeld); Assert.Null(lease.Fault); Assert.False(lease.Token.IsCancellationRequested);
        Assert.Equal(1, downs); Assert.Equal(1, ups); Assert.Equal(1150d, grant.ExpiresAtMs);
        var record = lease.EndpointClosure;
        if (expired)
        {
            Assert.NotNull(record); Assert.True(record.ConfirmsClosure); Assert.Equal(1150d, record.LeaseExpiresAtMs);
            Assert.Same(lease.PendingRecovery, record.Pause); Assert.Same(record.Pause, Assert.Single(lease.RecoveryPauses));
            Assert.Equal(1, record.Pause.MovementRecoveriesUsed); Assert.True(record.Pause.HeldForwardAtEntry);
            Assert.Equal(now, record.Pause.StartedAtMs); Assert.Equal(now, record.ClosedAtMs);
        }
        else { Assert.Null(record); Assert.Empty(lease.RecoveryPauses); }
        now += 100;
        Assert.Equal("baseline_input_closed", Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(2, now - 1), default)).Message);
        Assert.Equal("baseline_input_closed", Assert.Throws<InvalidOperationException>(() => lease.Rotate(Source(2, now - 1), 3, default)).Message);
        if (record is not null)
            Assert.Equal("baseline_input_closed", Assert.Throws<InvalidOperationException>(() => lease.ResumeRecovery(record.Pause, Source(2, now - 1), default)).Message);
        Assert.Equal("baseline_input_closed", Assert.Throws<InvalidOperationException>(() => lease.CloseAtEndpoint(default)).Message);
        Assert.Same(record, lease.EndpointClosure); Assert.Equal(1, downs); Assert.Equal(1, ups); Assert.Equal(0, moves);
        Assert.DoesNotContain(lease.Events, item => item.Kind == "recovery_resume");
    }

    /// <summary>An expired renewal retains the actual 100 ms renewal deadline rather than substituting a 150 ms physical grant.</summary>
    [Fact]
    public async Task RenewalExpiryRetainsItsOriginalDeadline()
    {
        double now = 1000;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V4);
        lease.EnableRecovery(); lease.Forward(Source(1, 990), default);
        now = 1090; var renewal = lease.Forward(Source(2, 1080), default);
        Assert.Equal(100d, renewal.GrantMs); Assert.Equal(1190d, renewal.ExpiresAtMs);
        now = 1191.3114; lease.CloseAtEndpoint(default);
        Assert.Equal(1190d, lease.EndpointClosure!.LeaseExpiresAtMs); Assert.True(lease.EndpointClosure.ConfirmsClosure);
    }

    /// <summary>A real watchdog check creates the exact ticket once; endpoint handling neither resumes nor consumes another allowance.</summary>
    [Fact]
    public async Task ExistingWatchdogExpiryIsJoinedOnce()
    {
        double now = 1000; var ups = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => ups++,
            _ => { }, default, false, NavigationBaselineTiming.V4);
        lease.EnableRecovery(); lease.Forward(Source(1, 990), default);
        now = 1151; lease.Check(); var pause = lease.PendingRecovery!; var events = lease.Events.Length;
        now = 1200; lease.CloseAtEndpoint(default);
        Assert.Same(pause, lease.EndpointClosure!.Pause); Assert.Same(pause, Assert.Single(lease.RecoveryPauses));
        Assert.Equal(1151d, pause.StartedAtMs); Assert.Equal(1200d, lease.EndpointClosure.ClosedAtMs);
        Assert.Equal(events, lease.Events.Length); Assert.Equal(1, ups); Assert.True(lease.EndpointClosure.ConfirmsClosure);
    }

    /// <summary>Source-age interruptions, whether held or stationary, cannot be relabeled as an endpoint lease violation.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SourceAgePauseCannotBePromoted(bool held)
    {
        double now = 1000;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); if (held) lease.Forward(Source(1, 990), default); now = 1050;
            var pause = lease.PauseForRecovery(new(NavigationBaselineRecoveryCause.SourceAge, "fixture"), default);
            Assert.Equal("endpoint_recovery_cause_changed", Assert.Throws<InvalidOperationException>(() => lease.CloseAtEndpoint(default)).Message);
            Assert.Null(lease.EndpointClosure); Assert.Same(pause, lease.PendingRecovery); Assert.False(lease.ForwardHeld);
            Assert.Equal("endpoint_recovery_cause_changed", lease.Fault);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>A synthetic expiry interruption after an explicit release is not evidence that an expired W grant was held.</summary>
    [Fact]
    public async Task UnheldExpiryTicketCannotConfirmEndpointClosure()
    {
        double now = 1000;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1100; lease.ReleaseForward(); now = 1160;
            var pause = lease.PauseForRecovery(new(NavigationBaselineRecoveryCause.LeaseExpired, "fixture"), default);
            Assert.False(pause.HeldForwardAtEntry);
            Assert.Throws<InvalidOperationException>(() => lease.CloseAtEndpoint(default));
            Assert.Null(lease.EndpointClosure); Assert.Same(pause, lease.PendingRecovery);
            Assert.Equal("endpoint_recovery_cause_changed", lease.Fault);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Target loss or target-query failure remains hard failure even when expiry has already caused a successful release.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task TargetFailureCannotBecomeEndpointSuccess(bool throwFromTarget)
    {
        double now = 1000; var fail = false;
        var lease = new NavigationBaselineInputLease(() => now, () =>
        { if (fail && throwFromTarget) throw new InvalidOperationException("target fixture"); return !fail; },
            () => { }, () => { }, _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1151; fail = true;
            var expected = throwFromTarget ? "game_target_check_failed" : "game_target_lost";
            Assert.Equal(expected, Assert.Throws<InvalidOperationException>(() => lease.CloseAtEndpoint(default)).Message);
            Assert.Equal(expected, lease.Fault); Assert.False(lease.ForwardHeld);
            Assert.Equal(expected, lease.EndpointClosure!.Error); Assert.Null(lease.EndpointClosure.ClosedAtMs);
            Assert.False(lease.EndpointClosure.ConfirmsClosure);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Caller cancellation before the endpoint call still permanently releases an otherwise valid live grant.</summary>
    [Fact]
    public async Task CallerCancellationClosesWithoutAnExpiryPromotion()
    {
        double now = 1000; var ups = 0; using var caller = new CancellationTokenSource();
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => ups++,
            _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1100; caller.Cancel();
            Assert.Throws<OperationCanceledException>(() => lease.CloseAtEndpoint(caller.Token));
            Assert.Equal("baseline_cancelled", lease.Fault); Assert.False(lease.ForwardHeld); Assert.Equal(1, ups);
            Assert.Null(lease.EndpointClosure); Assert.Empty(lease.RecoveryPauses);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Cancellation inside the target callback wins after an already-recorded expiry release.</summary>
    [Fact]
    public async Task OwnerCancellationDuringTargetCheckRetainsFailure()
    {
        double now = 1000; var cancel = false; using var owner = new CancellationTokenSource();
        var lease = new NavigationBaselineInputLease(() => now, () => { if (cancel) owner.Cancel(); return true; },
            () => { }, () => { }, _ => { }, owner.Token, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1151; cancel = true;
            Assert.Throws<OperationCanceledException>(() => lease.CloseAtEndpoint(default));
            Assert.Equal("baseline_cancelled", lease.Fault); Assert.Equal("baseline_cancelled", lease.EndpointClosure!.Error);
            Assert.Null(lease.EndpointClosure.ClosedAtMs); Assert.False(lease.EndpointClosure.ConfirmsClosure);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>The supplied caller token is rechecked after keyup, without requiring it to equal the lease owner token.</summary>
    [Fact]
    public async Task CallerCancellationDuringReleaseCannotPublishSuccess()
    {
        double now = 1000; using var caller = new CancellationTokenSource();
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, caller.Cancel,
            _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1151;
            Assert.Throws<OperationCanceledException>(() => lease.CloseAtEndpoint(caller.Token));
            Assert.False(lease.ForwardHeld); Assert.Equal("baseline_cancelled", lease.EndpointClosure!.Error);
            Assert.Null(lease.EndpointClosure.ClosedAtMs);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Crossing the deadline on the final same-gate clock sample creates a pause instead of ordinary Close's second-clock fault.</summary>
    [Fact]
    public async Task FinalCloseSampleCatchesExpiryAfterHardChecks()
    {
        double now = 1000; var closing = false; var reads = 0;
        await using var lease = new NavigationBaselineInputLease(() =>
        { if (closing && ++reads == 3) now = 1151; return now; }, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V4);
        lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1149; closing = true;
        Assert.Equal(1151d, lease.CloseAtEndpoint(default));
        Assert.Equal(1151d, lease.EndpointClosure!.Pause.StartedAtMs); Assert.True(lease.EndpointClosure.ConfirmsClosure);
    }

    /// <summary>Ambiguous first keyup remains failed evidence even when the existing best-effort fault cleanup releases W.</summary>
    [Fact]
    public async Task ReleaseFailureCannotBeErasedBySuccessfulFaultCleanup()
    {
        double now = 1000; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () =>
        { if (++ups == 1) throw new InvalidOperationException("ambiguous-up"); }, _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1151;
            Assert.Throws<InvalidOperationException>(() => lease.CloseAtEndpoint(default));
            Assert.Equal(2, ups); Assert.False(lease.ForwardHeld); Assert.Equal("ambiguous-up", lease.ReleaseError);
            Assert.Equal("ambiguous-up", lease.EndpointClosure!.Pause.ReleaseError); Assert.Null(lease.EndpointClosure.ClosedAtMs);
            Assert.Equal("input_release_failed", lease.EndpointClosure.Error); Assert.False(lease.EndpointClosure.ConfirmsClosure);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Invalid release-clock evidence remains terminal and never gets a successful endpoint cutoff.</summary>
    [Fact]
    public async Task InvalidReleaseClockCannotConfirmEndpointClosure()
    {
        double now = 1000;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => now = double.NaN,
            _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1151;
            Assert.Throws<InvalidOperationException>(() => lease.CloseAtEndpoint(default));
            Assert.Equal("invalid_lease_clock", lease.Fault); Assert.False(lease.ForwardHeld);
            Assert.Equal("invalid_release_clock", lease.EndpointClosure!.Pause.ReleaseError);
            Assert.Null(lease.EndpointClosure.ClosedAtMs); Assert.False(lease.EndpointClosure.ConfirmsClosure);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>The old pause's absolute deadline is never restarted at endpoint admission.</summary>
    [Theory]
    [InlineData(1999.999, true)]
    [InlineData(2000, false)]
    public async Task ExistingPauseDeadlineIsStrict(double delay, bool accepted)
    {
        double now = 1000;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1151; lease.Check(); var pause = lease.PendingRecovery!;
            now = pause.StartedAtMs + delay;
            if (accepted)
            { Assert.Equal(now, lease.CloseAtEndpoint(default)); Assert.True(lease.EndpointClosure!.ConfirmsClosure); }
            else
            {
                Assert.Equal("recovery_deadline_exceeded", Assert.Throws<InvalidOperationException>(() => lease.CloseAtEndpoint(default)).Message);
                Assert.Null(lease.EndpointClosure!.ClosedAtMs); Assert.False(lease.EndpointClosure.ConfirmsClosure);
            }
            Assert.Same(pause, lease.EndpointClosure!.Pause); Assert.Single(lease.RecoveryPauses);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Even an already-released close cutoff must complete before the original pause deadline.</summary>
    [Fact]
    public async Task ClosureCompletionCannotCrossOriginalPauseDeadline()
    {
        double now = 1000; var closing = false; var reads = 0;
        var lease = new NavigationBaselineInputLease(() =>
        { if (closing && ++reads == 4) now = 3151; return now; }, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1151; lease.Check(); now = 3150; closing = true;
            Assert.Equal("recovery_deadline_exceeded", Assert.Throws<InvalidOperationException>(() => lease.CloseAtEndpoint(default)).Message);
            Assert.Equal("recovery_deadline_exceeded", lease.EndpointClosure!.Error); Assert.Null(lease.EndpointClosure.ClosedAtMs);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Two real expiry/resume cycles exhaust the existing movement budget; a third endpoint expiry remains terminal.</summary>
    [Fact]
    public async Task EndpointExpiryCannotBypassMovementBudget()
    {
        double now = 1000; long id = 1;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(id++, now - 10), default);
            for (var i = 0; i < NavigationBaselineRecovery.MaximumRecoveries; i++)
            {
                now += 150; lease.Check(); var pause = lease.PendingRecovery!; now += 90;
                var source = Source(id++, now - 10); lease.ResumeRecovery(pause, source, default); lease.Forward(source, default);
            }
            now += 150;
            Assert.Equal("recovery_limit_exceeded", Assert.Throws<InvalidOperationException>(() => lease.CloseAtEndpoint(default)).Message);
            Assert.Equal(2, lease.RecoveryPauses.Length); Assert.Null(lease.EndpointClosure); Assert.False(lease.ForwardHeld);
            Assert.Equal("recovery_limit_exceeded", lease.Fault);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>A planned waypoint hold cannot be consumed by this distinct terminal endpoint path.</summary>
    [Fact]
    public async Task WaypointHoldCannotBecomeEndpointClosure()
    {
        double now = 1000;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1050; lease.BeginWaypointHold(default);
            Assert.Equal("waypoint_input_held", Assert.Throws<InvalidOperationException>(() => lease.CloseAtEndpoint(default)).Message);
            Assert.True(lease.WaypointHeld); Assert.Null(lease.EndpointClosure); Assert.False(lease.ForwardHeld);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>The existing reentrant gate cannot let availability callbacks dispatch or resume while endpoint closure owns it.</summary>
    [Fact]
    public async Task ReentrantAvailabilityCannotDispatchResumeOrCloseAgain()
    {
        double now = 1000; var attempt = false; var downs = 0; var moves = 0; NavigationBaselineInputLease? active = null;
        await using var lease = new NavigationBaselineInputLease(() => now, () =>
        {
            if (attempt)
            {
                attempt = false; var source = Source(2, now - 1);
                Assert.Equal("endpoint_close_in_progress", Assert.Throws<InvalidOperationException>(() => active!.Forward(source, default)).Message);
                Assert.Equal("endpoint_close_in_progress", Assert.Throws<InvalidOperationException>(() => active!.Rotate(source, 3, default)).Message);
                Assert.Equal("endpoint_close_in_progress", Assert.Throws<InvalidOperationException>(() => active!.ResumeRecovery(active.PendingRecovery!, source, default)).Message);
                Assert.Equal("endpoint_close_in_progress", Assert.Throws<InvalidOperationException>(() => active!.CloseAtEndpoint(default)).Message);
            }
            return true;
        }, () => downs++, () => { }, _ => moves++, default, false, NavigationBaselineTiming.V4);
        active = lease; lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1151; lease.Check();
        now = 1250; attempt = true; lease.CloseAtEndpoint(default);
        Assert.True(lease.EndpointClosure!.ConfirmsClosure); Assert.Equal(1, downs); Assert.Equal(0, moves);
        Assert.DoesNotContain(lease.Events, item => item.Kind == "recovery_resume");
    }

    /// <summary>Keyup callbacks cannot exploit the reentrant lock to issue another down or camera input during terminal release.</summary>
    [Fact]
    public async Task ReentrantReleaseCannotRepressOrResume()
    {
        double now = 1000; var downs = 0; var moves = 0; NavigationBaselineInputLease? active = null;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () =>
        {
            var source = Source(2, now - 1);
            Assert.Equal("endpoint_close_in_progress", Assert.Throws<InvalidOperationException>(() => active!.Forward(source, default)).Message);
            Assert.Equal("endpoint_close_in_progress", Assert.Throws<InvalidOperationException>(() => active!.Rotate(source, 2, default)).Message);
            Assert.Equal("endpoint_close_in_progress", Assert.Throws<InvalidOperationException>(() => active!.ResumeRecovery(active.PendingRecovery!, source, default)).Message);
        }, _ => moves++, default, false, NavigationBaselineTiming.V4);
        active = lease; lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1100;
        lease.CloseAtEndpoint(default);
        Assert.Equal(1, downs); Assert.Equal(0, moves); Assert.Null(lease.Fault); Assert.Null(lease.EndpointClosure);
        Assert.Equal(new[] { "w_down", "w_up" }, lease.Events.Select(item => item.Kind));
    }

    /// <summary>Ordinary Close retains its old fail-on-expiry semantics even with recovery enabled.</summary>
    [Fact]
    public async Task OrdinaryCloseIsStillTerminalOnExpiredHeldGrant()
    {
        double now = 1000;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1151;
            Assert.Equal("forward_lease_expired", Assert.Throws<InvalidOperationException>(() => lease.Close()).Message);
            Assert.Equal("forward_lease_expired", lease.Fault); Assert.Empty(lease.RecoveryPauses); Assert.Null(lease.EndpointClosure);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Endpoint closure is not a way to enable recovery before the original anchor admission.</summary>
    [Fact]
    public async Task RecoveryMustAlreadyBeEnabled()
    {
        double now = 1000;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.Forward(Source(1, 990), default); now = 1050;
            Assert.Equal("endpoint_close_not_available", Assert.Throws<InvalidOperationException>(() => lease.CloseAtEndpoint(default)).Message);
            Assert.False(lease.ForwardHeld); Assert.Empty(lease.RecoveryPauses); Assert.Null(lease.EndpointClosure);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>The existing bounded transition journal must still have room for an expiry pause and its release.</summary>
    [Fact]
    public async Task EndpointExpiryCannotBypassEventCapacity()
    {
        double now = 1000;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V4);
        try
        {
            lease.EnableRecovery();
            for (var i = 1; i <= 60; i++) { lease.Rotate(Source(i, now - 1), 1, default); now += 2; }
            lease.Forward(Source(61, now - 1), default); now += 150;
            Assert.Equal("input_evidence_capacity_exceeded", Assert.Throws<InvalidOperationException>(() => lease.CloseAtEndpoint(default)).Message);
            Assert.False(lease.ForwardHeld); Assert.Empty(lease.RecoveryPauses); Assert.Null(lease.EndpointClosure);
            Assert.True(lease.Events.Length <= NavigationBaselineInputLease.MaximumEvents);
        }
        finally { await DisposeFaulted(lease); }
    }
}
