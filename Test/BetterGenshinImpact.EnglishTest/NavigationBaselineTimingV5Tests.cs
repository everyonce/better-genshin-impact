using System.Diagnostics;
using System.IO;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Deterministic v5 lease and response-boundary cases; no real clock wait, watchdog, capture or input.</summary>
public sealed class NavigationBaselineTimingV5Tests
{
    /// <summary>One immutable fake host capture generation.</summary>
    private static readonly Guid Epoch = Guid.Parse("549f5625-ea7d-435f-a7d6-fde8d822c865");

    /// <summary>Independent monotonically identified host pixels, with a bounded one-millisecond acquisition.</summary>
    private static CaptureSourceEvidence Source(long id, double anchor, Guid? epoch = null) =>
        new(new GameCaptureHostSnapshotInfo(epoch ?? Epoch, id,
            (long)(anchor * Stopwatch.Frequency / 1000),
            (long)((anchor + 1) * Stopwatch.Frequency / 1000), Stopwatch.Frequency));

    /// <summary>Faulted cleanup is still attempted; individual tests assert the original terminal reason.</summary>
    private static async Task Drain(NavigationBaselineInputLease lease)
    { try { await lease.DisposeAsync(); } catch (InvalidOperationException) { } }

    /// <summary>Both physical starts and held renewals end at the same source-relative cap.</summary>
    [Theory]
    [InlineData(1)]
    [InlineData(70)]
    [InlineData(150)]
    public async Task SourceAgeConsumesTheSameHorizonForStartsAndRenewals(double age)
    {
        double now = 1000; var downs = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => downs++, () => { }, _ => { }, default, false, NavigationBaselineTiming.V5);
        lease.EnableRecovery();
        var first = lease.Forward(Source(1, now - age), default);
        Assert.Equal(now - age + 250, first.ExpiresAtMs);
        Assert.Equal(250 - age, first.GrantMs);
        now += 50;
        var next = lease.Forward(Source(2, now - age), default);
        Assert.Equal(now - age + 250, next.ExpiresAtMs);
        Assert.Equal(250 - age, next.GrantMs);
        Assert.Equal("renew_w", next.Kind); Assert.Equal(1, downs);
        Assert.Empty(lease.RecoveryPauses);
    }

    /// <summary>Saved first/second start overruns fit only the existing source horizon, not the old 150ms sub-grant.</summary>
    [Theory]
    [InlineData("v4", 77, 152, true)]
    [InlineData("v5", 77, 152, false)]
    [InlineData("v4", 79, 160, true)]
    [InlineData("v5", 79, 160, false)]
    public async Task AfterInputSettlingAndLateRecognitionUseActualOriginalExpiry(string contract, double age, double elapsed, bool expires)
    {
        double now = 1000; var downs = 0; var ups = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => downs++, () => ups++, _ => { }, default, false, contract);
        lease.EnableRecovery(); lease.Forward(Source(1, now - age), default);
        // The next source starts after the unchanged 60ms response barrier; processing then consumes wall time.
        now += elapsed;
        if (expires)
        {
            Assert.Throws<NavigationBaselineRecoveryRequired>(() => lease.Forward(Source(2, 1061), default));
            Assert.NotNull(lease.PendingRecovery); Assert.Equal(1, ups);
        }
        else
        {
            Assert.Equal("renew_w", lease.Forward(Source(2, 1061), default).Kind);
            Assert.Null(lease.PendingRecovery); Assert.Equal(0, ups);
        }
        Assert.Equal(1, downs);
    }

    /// <summary>The final saved recognition span exceeds v4's renewal but never bypasses v5 source freshness.</summary>
    [Theory]
    [InlineData("v4", true)]
    [InlineData("v5", false)]
    public async Task HundredAndSixMillisecondReadAfterRenewalRemainsVersioned(string contract, bool expires)
    {
        double now = 900;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => { }, () => { }, _ => { }, default, false, contract);
        lease.EnableRecovery(); lease.Forward(Source(1, 890), default);
        now = 1000; var renewed = lease.Forward(Source(2, 930), default);
        Assert.Equal(contract == "v4" ? 1100d : 1180d, renewed.ExpiresAtMs);
        now = 1106;
        if (expires) Assert.Throws<NavigationBaselineRecoveryRequired>(() => lease.Forward(Source(3, 1000), default));
        else Assert.Equal("renew_w", lease.Forward(Source(3, 1000), default).Kind);
    }

    /// <summary>The existing host barrier waits only its remainder and never starts capture early.</summary>
    [Theory]
    [InlineData(60, 1000, 1060)]
    [InlineData(60, 1050, 1060)]
    [InlineData(80, 1000, 1080)]
    [InlineData(80, 1081, 1081)]
    public async Task ResponseBarrierRemainsIndependentFromGrant(double response, double initial, double expected)
    {
        double now = initial; var checks = 0;
        var attempt = new NavigationBaselineObservationAttempt(now);
        await NativeNavigationBaselineOperations.WaitForHostResponseAsync(1000, response, attempt, () => now,
            (deadline, _) => { now = deadline; return Task.CompletedTask; }, _ => checks++, default);
        Assert.Equal(expected, now);
        Assert.Equal(initial < 1000 + response ? 1 : 0, checks);
    }

    /// <summary>Neither a duplicate ID nor a changed generation can renew held input.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DuplicateOrChangedEpochFailsBeforeRenewal(bool changedEpoch)
    {
        double now = 1000; var downs = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V5);
        try
        {
            lease.EnableRecovery(); var first = Source(1, 990); lease.Forward(first, default); now = 1050;
            var next = changedEpoch ? Source(2, 1040, Guid.Parse("53327253-c779-4ee2-a98b-93002b5b758c")) : first;
            Assert.Throws<InvalidOperationException>(() => lease.Forward(next, default));
            Assert.NotNull(lease.Fault); Assert.Equal(1, downs); Assert.False(lease.ForwardHeld);
        }
        finally { await Drain(lease); }
    }

    /// <summary>A stale fresh ID still pauses rather than using the longer source horizon as input freshness.</summary>
    [Fact]
    public async Task FreshnessStillRejectsAgeAbove150()
    {
        double now = 1000; var downs = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => downs++, () => { }, _ => { }, default, false, NavigationBaselineTiming.V5);
        lease.EnableRecovery(); lease.Forward(Source(1, 900), default); now = 1080;
        var error = Assert.Throws<NavigationBaselineRecoveryRequired>(() => lease.Forward(Source(2, 929), default));
        Assert.Equal(NavigationBaselineRecoveryCause.SourceAge, error.Cause);
        Assert.Equal(1, downs); Assert.False(lease.ForwardHeld);
    }

    /// <summary>A new pose does not resurrect an already expired source grant.</summary>
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    public async Task ExactSourceHorizonStillReleasesBeforeAnyRenewal(double late)
    {
        double now = 1000; var downs = 0; var ups = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => downs++, () => ups++, _ => { }, default, false, NavigationBaselineTiming.V5);
        lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1240 + late;
        Assert.Throws<NavigationBaselineRecoveryRequired>(() => lease.Forward(Source(2, now - 10), default));
        Assert.Equal(NavigationBaselineRecoveryCause.LeaseExpired, lease.PendingRecovery!.Cause);
        Assert.Equal(1, downs); Assert.Equal(1, ups); Assert.False(lease.ForwardHeld);
    }

    /// <summary>Time spent inside a physical keydown consumes the cap; failed dispatch never earns more authority.</summary>
    [Fact]
    public async Task NativeReturnPastCapRetainsActualDispatchAndReleases()
    {
        double now = 1000; var ups = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => now = 1241, () => ups++, _ => { }, default, false, NavigationBaselineTiming.V5);
        lease.EnableRecovery();
        Assert.Throws<NavigationBaselineRecoveryRequired>(() => lease.Forward(Source(1, 990), default));
        var sent = Assert.Single(lease.Events.Where(e => e.Kind == "w_down"));
        Assert.Equal(1240d, sent.ExpiresAtMs); Assert.Equal(1241d, sent.CompletedAtMs);
        Assert.Equal(240d, sent.GrantMs); Assert.Equal(1, ups);
    }

    /// <summary>Endpoint admission retains the original cap and cannot resume movement after closure.</summary>
    [Theory]
    [InlineData(-0.001, false)]
    [InlineData(0, true)]
    [InlineData(3.2052, true)]
    public async Task EndpointClosureJoinsActualV5Expiry(double offset, bool expired)
    {
        double now = 1000; var downs = 0; var ups = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => downs++, () => ups++, _ => { }, default, false, NavigationBaselineTiming.V5);
        lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1240 + offset;
        lease.CloseAtEndpoint(default);
        if (expired)
        {
            Assert.True(lease.EndpointClosure!.ConfirmsClosure);
            Assert.Equal(1240d, lease.EndpointClosure.LeaseExpiresAtMs);
        }
        else Assert.Null(lease.EndpointClosure);
        Assert.False(lease.ForwardHeld); Assert.Equal(1, ups);
        now += 100;
        Assert.Equal("baseline_input_closed", Assert.Throws<InvalidOperationException>(() =>
            lease.Forward(Source(2, now - 10), default)).Message);
        Assert.Equal(1, downs);
    }

    /// <summary>Longer grants do not reset the two-ticket movement recovery bound.</summary>
    [Fact]
    public async Task ThirdExpiryStillFailsWithOnlyTwoTickets()
    {
        double now = 1000; long id = 1;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V5);
        try
        {
            lease.EnableRecovery(); var current = lease.Forward(Source(id++, now - 10), default);
            for (var i = 0; i < 2; i++)
            {
                now = current.ExpiresAtMs!.Value; lease.Check(); var pause = lease.PendingRecovery!;
                now += 90; var source = Source(id++, now - 10);
                lease.ResumeRecovery(pause, source, default); current = lease.Forward(source, default);
            }
            now = current.ExpiresAtMs!.Value; lease.Check();
            Assert.Equal("recovery_limit_exceeded", lease.Fault); Assert.Equal(2, lease.RecoveryPauses.Length);
            Assert.False(lease.ForwardHeld);
        }
        finally { await Drain(lease); }
    }

    /// <summary>A release failure stays latched even if later cleanup returns successfully.</summary>
    [Fact]
    public async Task FailedReleaseCannotBecomeHealthyRecovery()
    {
        double now = 1000; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { },
            () => { if (++ups == 1) throw new IOException("synthetic up uncertainty"); }, _ => { },
            default, false, NavigationBaselineTiming.V5);
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(1, 990), default); now = 1240; lease.Check();
            Assert.Equal("input_release_failed", lease.Fault); Assert.Equal("synthetic up uncertainty", lease.ReleaseError);
            now = 1330;
            Assert.Throws<InvalidOperationException>(() => lease.ResumeRecovery(lease.PendingRecovery!, Source(2, 1320), default));
        }
        finally { await Drain(lease); }
        Assert.True(ups >= 2);
    }

    /// <summary>Omitted selection and explicit v1-v4 retain their original first/renewal arithmetic.</summary>
    [Theory]
    [InlineData("v1", 100)]
    [InlineData("v2", 150)]
    [InlineData("v3", 150)]
    [InlineData("v4", 150)]
    public async Task LegacyGrantsRemainUnchanged(string contract, double initialGrant)
    {
        double now = 1000;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false, contract);
        var first = lease.Forward(Source(1, 990), default);
        Assert.Equal(initialGrant, first.GrantMs); Assert.Equal(1000 + initialGrant, first.ExpiresAtMs);
        now = 1060; var renewal = lease.Forward(Source(2, 1050), default);
        Assert.Equal(100d, renewal.GrantMs); Assert.Equal(1160d, renewal.ExpiresAtMs);
    }

    /// <summary>Default construction never enables v5.</summary>
    [Fact]
    public async Task OmittedTimingRemainsOriginalV1()
    {
        double now = 1000;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false);
        Assert.Equal(1100d, lease.Forward(Source(1, 990), default).ExpiresAtMs);
        Assert.Throws<InvalidOperationException>(lease.EnableRecovery);
    }
}
