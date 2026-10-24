using System.Diagnostics;
using System.IO;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Deterministic fake-clock/native-sink checks; no game, keyboard, mouse or GPU is used.</summary>
public sealed class NavigationBaselineInputLeaseTests
{
    /// <summary>Fixed native generation shared by the synthetic frame sequence.</summary>
    private static readonly Guid Epoch = Guid.Parse("8e4531ef-7241-4fa9-ab63-7be3827032b4");
    /// <summary>Create honest immutable source clocks in the same QPC time domain as the fake lease.</summary>
    private static GameCaptureSourceInfo Source(double acquiredMs, double? reportedMs = null) => new(Epoch,
        (long)((reportedMs ?? acquiredMs) * 10_000), (long)(acquiredMs * Stopwatch.Frequency / 1000));
    /// <summary>Dispose a deliberately faulted lease while still requiring its watchdog/resources to drain.</summary>
    private static async Task DisposeFaulted(NavigationBaselineInputLease lease)
    { try { await lease.DisposeAsync(); } catch (InvalidOperationException) { } }

    /// <summary>Renewal advances authority without repeated keydown or another native transition.</summary>
    [Fact]
    public async Task RenewalUsesNewSourceWithoutAnotherKeydown()
    {
        double now = 1000; var downs = 0; var ups = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => ups++, _ => { }, default, false);
        var first = lease.Forward(Source(950), default);
        now = 1050;
        var renewal = lease.Forward(Source(1030), default);
        Assert.Equal("w_down", first.Kind); Assert.Equal("renew_w", renewal.Kind);
        Assert.Equal(1150, renewal.ExpiresAtMs); Assert.Equal(1, downs); Assert.Single(lease.Events);
        now = 1090; lease.Close();
        Assert.Equal(1, ups); Assert.False(lease.ForwardHeld);
    }

    /// <summary>Even without a scheduled watchdog tick, exact expiry is terminal and a fresh result cannot renew.</summary>
    [Theory]
    [InlineData(1100)]
    [InlineData(1101)]
    public async Task ExpiredGrantNeverRenewsOrRepresses(double expiredNow)
    {
        double now = 1000; var downs = 0; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => ups++, _ => { }, default, false);
        try
        {
            lease.Forward(Source(990), default); now = expiredNow;
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(expiredNow - 1), default));
            now += 10;
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(now - 1), default));
            Assert.Equal("forward_lease_expired", lease.Fault); Assert.Equal(1, downs); Assert.Equal(1, ups);
            Assert.False(lease.ForwardHeld); Assert.Null(lease.ReleaseError);
            Assert.Equal(expiredNow, lease.Events.Single(item => item.Kind == "w_up").CompletedAtMs);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Independent checking releases while observation work is blocked outside the input lock.</summary>
    [Fact]
    public async Task BlockedObservationDoesNotBlockWatchdogRelease()
    {
        double now = 1000; var ups = 0; var downs = 0;
        var resume = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var lease = new NavigationBaselineInputLease(() => Volatile.Read(ref now), () => true, () => downs++, () => ups++, _ => { }, default, false);
        try
        {
            lease.Forward(Source(990), default);
            var delayed = Task.Run(async () => { await resume.Task; lease.Forward(Source(1110), default); });
            Volatile.Write(ref now, 1111); lease.Check();
            Assert.Equal(1, ups); Assert.False(lease.ForwardHeld);
            resume.SetResult();
            await Assert.ThrowsAsync<InvalidOperationException>(() => delayed);
            Assert.Equal(1, downs);
        }
        finally { resume.TrySetResult(); await DisposeFaulted(lease); }
    }

    /// <summary>A target-check delay inside the gate must recheck expiry rather than admit the queued result.</summary>
    [Fact]
    public async Task GateContentionCannotHideExpiredAcceptance()
    {
        double now = 1000; var block = false; var downs = 0; var ups = 0;
        using var entered = new ManualResetEventSlim(); using var resume = new ManualResetEventSlim();
        var lease = new NavigationBaselineInputLease(() => Volatile.Read(ref now), () =>
        { if (block) { entered.Set(); if (!resume.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException(); } return true; },
            () => downs++, () => ups++, _ => { }, default, false);
        try
        {
            lease.Forward(Source(990), default); Volatile.Write(ref now, 1050); block = true;
            var delayed = Task.Run(() => lease.Forward(Source(1040), default));
            Assert.True(entered.Wait(TimeSpan.FromSeconds(5)));
            Volatile.Write(ref now, 1120);
            var watchdog = Task.Run(lease.Check);
            resume.Set();
            await Assert.ThrowsAsync<InvalidOperationException>(() => delayed); await watchdog;
            Assert.Equal("forward_lease_expired", lease.Fault); Assert.Equal(1, downs); Assert.Equal(1, ups);
        }
        finally { resume.Set(); await DisposeFaulted(lease); }
    }

    /// <summary>A slow actual keydown cannot shift expiry to its completion time.</summary>
    [Fact]
    public async Task LateNativeKeydownReleasesAtReturn()
    {
        double now = 1000; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => now = 1115, () => ups++, _ => { }, default, false);
        try
        {
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(990), default));
            Assert.Equal(1, ups); Assert.False(lease.ForwardHeld);
            var press = lease.Events.Single(item => item.Kind == "w_down");
            Assert.Equal(1000, press.RequestedAtMs); Assert.Equal(1115, press.CompletedAtMs); Assert.Equal(1100, press.ExpiresAtMs);
            Assert.Equal(1115, lease.Events.Single(item => item.Kind == "w_up").CompletedAtMs);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Ambiguous keydown failure still owns W release even when channel bookkeeping never marked it down.</summary>
    [Fact]
    public async Task PartialKeydownFailureStillReleases()
    {
        double now = 1000; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => throw new IOException("partial send"), () => ups++, _ => { }, default, false);
        try
        {
            Assert.Throws<IOException>(() => lease.Forward(Source(990), default));
            Assert.Equal(1, ups); Assert.Equal("forward_dispatch_failed", lease.Fault); Assert.False(lease.ForwardHeld);
            Assert.Equal("partial send", lease.Events.Single(item => item.Kind == "w_down").Error);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Every failed keyup attempt retains its own error, including a second failure after the first was latched.</summary>
    [Fact]
    public async Task RepeatedFailedReleasesNeverLoseErrorEvidence()
    {
        double now = 1000; var failRelease = true; var attempts = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () =>
        { attempts++; if (failRelease) throw new IOException($"release {attempts}"); }, _ => { }, default, false);
        try
        {
            lease.Forward(Source(990), default);
            Assert.Throws<InvalidOperationException>(() => lease.Close());
            Assert.Throws<InvalidOperationException>(() => lease.Close());
            Assert.True(lease.ForwardHeld);
            Assert.Equal(new[] { "release 1", "release 2" }, lease.Events.Where(item => item.Kind == "w_up").Select(item => item.Error));
            Assert.Equal("release 1", lease.ReleaseError);
            failRelease = false;
        }
        finally { await DisposeFaulted(lease); }
        Assert.False(lease.ForwardHeld);
    }

    /// <summary>A source that becomes stale during the final target check cannot authorize the first keydown.</summary>
    [Fact]
    public async Task FinalSourceAgeIncludesTargetCheckDelay()
    {
        double now = 1000; var downs = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => { now = 1160; return true; }, () => downs++, () => { }, _ => { }, default, false);
        try
        {
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(1000), default));
            Assert.Equal("native_source_stale", lease.Fault); Assert.Equal(0, downs);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Repeated source identity is not a renewable freshness grant.</summary>
    [Fact]
    public async Task CachedSourceCannotRenew()
    {
        double now = 1000; var downs = 0; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => ups++, _ => { }, default, false);
        try
        {
            lease.Forward(Source(990), default); now = 1050;
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(990), default));
            Assert.Equal("input_source_not_increasing", lease.Fault); Assert.Equal(1, downs); Assert.Equal(1, ups);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Normal closure permits subsequent observation tokens but rejects any queued controller input.</summary>
    [Fact]
    public async Task NormalCloseKeepsVerificationTokenAndRejectsLateInput()
    {
        double now = 1000;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => now += 4, _ => { }, default, false);
        lease.Forward(Source(990), default); now = 1040;
        Assert.Equal(1044, lease.Close()); Assert.False(lease.Token.IsCancellationRequested);
        now = 1200;
        Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(1190), default));
        Assert.Equal(1044, lease.Close()); Assert.Null(lease.Fault);
    }

    /// <summary>Capacity is checked before another native camera dispatch and retains bounded terminal evidence.</summary>
    [Fact]
    public async Task InputEvidenceCapacityStopsBeforeUnrecordedDispatch()
    {
        double now = 1000; var moves = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { }, _ => moves++, default, false);
        try
        {
            for (var i = 0; i < NavigationBaselineInputLease.MaximumEvents - 2; i++)
            { now += 1; lease.Rotate(Source(now - 0.5), 1, default); }
            now += 1;
            Assert.Throws<InvalidOperationException>(() => lease.Rotate(Source(now - 0.5), 1, default));
            Assert.Equal(NavigationBaselineInputLease.MaximumEvents - 2, moves);
            Assert.Equal("input_evidence_capacity_exceeded", lease.Fault);
            Assert.True(lease.Events.Length <= NavigationBaselineInputLease.MaximumEvents);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Malformed or regressing clocks cannot extend an active hold.</summary>
    [Theory]
    [InlineData(double.NaN)]
    [InlineData(999)]
    public async Task InvalidClockReleases(double invalid)
    {
        double now = 1000; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => ups++, _ => { }, default, false);
        try
        {
            lease.Forward(Source(990), default); now = invalid; lease.Check();
            Assert.Equal("invalid_lease_clock", lease.Fault); Assert.Equal(1, ups); Assert.False(lease.ForwardHeld);
        }
        finally { now = 1000; await DisposeFaulted(lease); }
    }
}
