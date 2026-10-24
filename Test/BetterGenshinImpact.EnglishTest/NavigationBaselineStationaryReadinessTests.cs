using System.Diagnostics;
using System.Reflection;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Run-global stationary allowance tests use only fake clocks and native sinks; no app or OS input.</summary>
public sealed class NavigationBaselineStationaryReadinessTests
{
    /// <summary>One immutable fake backend generation.</summary>
    private static readonly Guid Epoch = Guid.Parse("a32a92e7-15fa-41ef-8222-71a82aab96c6");
    /// <summary>Construct independent native clocks in the fake monotonic domain.</summary>
    private static GameCaptureSourceInfo Source(double acquired, double? reported = null) => new(Epoch,
        (long)((reported ?? acquired) * 10000), (long)(acquired * Stopwatch.Frequency / 1000));

    /// <summary>One real lease with deterministic native callbacks and cleanup even after a terminal fault.</summary>
    private sealed class Rig : IAsyncDisposable
    {
        /// <summary>Mutable monotonic fake clock.</summary>
        internal double Now = 1000;
        /// <summary>Pinned target state checked by the unchanged lease gate.</summary>
        internal bool Available = true;
        /// <summary>Actual sink invocations, distinct from already-released cutoffs.</summary>
        internal int Downs, Ups;
        /// <summary>Optional same-thread reentrant or failing keyup behavior.</summary>
        internal Action? OnUp;
        /// <summary>Owner cancellation remains the original linked token.</summary>
        internal readonly CancellationTokenSource Cancellation = new();
        /// <summary>Production gate under test; explicit Check replaces the timed worker in deterministic cases.</summary>
        internal readonly NavigationBaselineInputLease Lease;

        /// <summary>Arm only v4; unchanged legacy fixtures explicitly verify recovery admission rejection.</summary>
        internal Rig(string contract = "v4")
        {
            Lease = new(() => Now, () => Available, () => Downs++, () => { Ups++; OnUp?.Invoke(); },
                _ => { }, Cancellation.Token, false, contract);
            if (contract == "v4") Lease.EnableRecovery();
        }

        /// <summary>Enter a typed SourceAge pause while either holding W or already released.</summary>
        internal NavigationBaselineRecoveryPause Pause(bool movement)
        {
            if (movement) { Lease.Forward(Source(Now), default); Now++; }
            return Lease.PauseForRecovery(new(NavigationBaselineRecoveryCause.SourceAge, "after_capture", Source(Now - 200)), default);
        }

        /// <summary>Rearm using a fresh source beyond both release barriers; this sends no native input.</summary>
        internal void Resume(NavigationBaselineRecoveryPause pause)
        {
            Now = pause.ReleasedAtMs + 90;
            Lease.ResumeRecovery(pause, Source(Now), default);
        }

        /// <summary>Terminal cleanup is retained even for deliberate fault/release-failure fixtures.</summary>
        public async ValueTask DisposeAsync()
        {
            OnUp = null;
            try { await Lease.DisposeAsync(); }
            catch (InvalidOperationException) { }
            finally { Cancellation.Dispose(); }
        }
    }

    /// <summary>The two allowances are independent, run-global and serial; neither rearm sends a keydown.</summary>
    [Theory]
    [InlineData("SSMM")]
    [InlineData("MMSS")]
    [InlineData("SMSM")]
    public async Task FourMixedWindowsKeepIndependentCumulativeCounts(string order)
    {
        await using var rig = new Rig();
        var movement = 0; var stationary = 0;
        foreach (var kind in order)
        {
            var pause = rig.Pause(kind == 'M');
            if (kind == 'M') movement++; else stationary++;
            Assert.Equal(kind == 'M', pause.HeldForwardAtEntry);
            Assert.Equal(kind == 'M' ? NavigationBaselineRecoveryBudgetKind.MovementRecovery
                : NavigationBaselineRecoveryBudgetKind.StationarySourceReadiness, pause.BudgetKind);
            Assert.Equal(movement, pause.MovementRecoveriesUsed);
            Assert.Equal(stationary, pause.StationaryReadinessUsed);
            Assert.Equal(movement + stationary, pause.TotalWindowsUsed);
            Assert.Equal(pause.Generation, pause.TotalWindowsUsed);
            var downs = rig.Downs; var ups = rig.Ups;
            rig.Resume(pause);
            Assert.Equal(downs, rig.Downs); Assert.Equal(ups, rig.Ups);
            Assert.False(rig.Lease.ForwardHeld); Assert.Null(rig.Lease.Fault);
        }
        Assert.Equal(4, rig.Lease.RecoveryPauses.Length);
        Assert.Equal(2, rig.Downs); Assert.Equal(2, rig.Ups);
        Assert.Throws<InvalidOperationException>(() => rig.Pause(false));
        Assert.Equal("recovery_limit_exceeded", rig.Lease.Fault);
        Assert.Equal(4, rig.Lease.RecoveryPauses.Length);
    }

    /// <summary>An unused allowance of the other kind never enlarges the exhausted kind's two-window limit.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ThirdWindowOfOneKindIsTerminal(bool movement)
    {
        await using var rig = new Rig();
        rig.Resume(rig.Pause(movement)); rig.Resume(rig.Pause(movement));
        Assert.Throws<InvalidOperationException>(() => rig.Pause(movement));
        Assert.Equal("recovery_limit_exceeded", rig.Lease.Fault);
        Assert.False(rig.Lease.ForwardHeld); Assert.Equal(2, rig.Lease.RecoveryPauses.Length);
        Assert.True(rig.Lease.Token.IsCancellationRequested);
    }

    /// <summary>Expiry wins before a later SourceAge origin, whether the watchdog or dispatch check creates its ticket.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task AlreadyExpiredTicketCannotBeReclassifiedAfterRelease(bool explicitCheck)
    {
        await using var rig = new Rig();
        var grant = rig.Lease.Forward(Source(rig.Now), default); rig.Now = grant.ExpiresAtMs!.Value;
        if (explicitCheck) rig.Lease.Check();
        var before = rig.Lease.PendingRecovery;
        var pause = rig.Lease.PauseForRecovery(new(NavigationBaselineRecoveryCause.SourceAge, "after_capture"), default);
        if (before is not null) Assert.Same(before, pause);
        Assert.Equal(NavigationBaselineRecoveryCause.LeaseExpired, pause.Cause);
        Assert.Equal(NavigationBaselineRecoveryBudgetKind.MovementRecovery, pause.BudgetKind);
        Assert.True(pause.HeldForwardAtEntry); Assert.Equal(1, pause.MovementRecoveriesUsed);
        Assert.Equal(0, pause.StationaryReadinessUsed); Assert.Equal(1, rig.Ups);
        Assert.Same(pause, rig.Lease.PauseForRecovery(new(NavigationBaselineRecoveryCause.SourceAge, "later"), default));
        Assert.Single(rig.Lease.RecoveryPauses);
    }

    /// <summary>A keyup callback cannot obtain a second classification or a new window while release is in progress.</summary>
    [Fact]
    public async Task ReentrantReleaseKeepsThePreReleaseMovementClassification()
    {
        await using var rig = new Rig(); Exception? nested = null;
        rig.OnUp = () => nested = Record.Exception(() => rig.Lease.PauseForRecovery(
            new(NavigationBaselineRecoveryCause.SourceAge, "reentrant"), default));
        var pause = rig.Pause(true);
        Assert.IsType<InvalidOperationException>(nested);
        Assert.Equal("recovery_release_in_progress", nested!.Message);
        Assert.Equal(NavigationBaselineRecoveryBudgetKind.MovementRecovery, pause.BudgetKind);
        Assert.True(pause.HeldForwardAtEntry); Assert.Single(rig.Lease.RecoveryPauses);
    }

    /// <summary>Successful explicit realignment release is separate from the later no-held-W SourceAge classification.</summary>
    [Fact]
    public async Task EarlierRealignmentDoesNotSpendStationaryWindowOrRearmFirstForward()
    {
        await using var rig = new Rig();
        Assert.True(rig.Lease.Forward(Source(rig.Now), default).FirstForwardAttempt);
        rig.Now++; rig.Lease.ReleaseForward();
        Assert.Empty(rig.Lease.RecoveryPauses);
        var pause = rig.Pause(false); Assert.False(pause.HeldForwardAtEntry);
        Assert.Equal(0, pause.MovementRecoveriesUsed); Assert.Equal(1, pause.StationaryReadinessUsed);
        rig.Resume(pause);
        Assert.False(rig.Lease.Forward(Source(rig.Now), default).FirstForwardAttempt);
    }

    /// <summary>Failed native keyup is never relabeled stationary and remains terminal after later best-effort cleanup.</summary>
    [Fact]
    public async Task AmbiguousReleaseRetainsMovementChargeAndCannotResume()
    {
        await using var rig = new Rig(); rig.OnUp = () => throw new InvalidOperationException("injected-keyup");
        Assert.Throws<InvalidOperationException>(() => rig.Pause(true));
        var pause = Assert.Single(rig.Lease.RecoveryPauses);
        Assert.Equal(NavigationBaselineRecoveryBudgetKind.MovementRecovery, pause.BudgetKind);
        Assert.True(pause.HeldForwardAtEntry); Assert.NotNull(pause.ReleaseError);
        Assert.Equal(1, pause.MovementRecoveriesUsed); Assert.Equal(0, pause.StationaryReadinessUsed);
        rig.OnUp = null; Assert.Throws<InvalidOperationException>(() => rig.Resume(pause));
        Assert.NotNull(rig.Lease.Fault);
    }

    /// <summary>Terminal closure from inside keyup cannot be undone by the returned pause or a stationary request.</summary>
    [Fact]
    public async Task CloseDuringReleaseWinsOverAnyLaterResume()
    {
        await using var rig = new Rig(); var closing = false;
        rig.OnUp = () => { if (!closing) { closing = true; rig.Lease.Close(); } };
        var error = Record.Exception(() => rig.Pause(true));
        var pause = Assert.Single(rig.Lease.RecoveryPauses);
        Assert.True(pause.HeldForwardAtEntry); Assert.Equal(0, pause.StationaryReadinessUsed);
        Assert.Throws<InvalidOperationException>(() => rig.Resume(pause));
        Assert.Throws<InvalidOperationException>(() => rig.Pause(false));
        Assert.False(rig.Lease.ForwardHeld);
        // A synchronous Close may let Pause return its already-terminal evidence; it must never grant input.
        Assert.True(error is null or InvalidOperationException);
    }

    /// <summary>The original pause freshness, source identity, barrier, cancellation and deadline gates remain exact.</summary>
    [Theory]
    [InlineData("reported-barrier")]
    [InlineData("acquired-barrier")]
    [InlineData("stale")]
    [InlineData("foreign-epoch")]
    [InlineData("future")]
    [InlineData("copied-ticket")]
    [InlineData("deadline")]
    [InlineData("cancel")]
    [InlineData("close")]
    [InlineData("target")]
    public async Task StationaryResumeDoesNotRelaxExistingAdmission(string defect)
    {
        await using var rig = new Rig(); var pause = rig.Pause(false); rig.Now = 1100;
        var source = defect switch
        {
            "reported-barrier" => Source(1090, 1079),
            "acquired-barrier" => Source(1079, 1090),
            "stale" => Source(900),
            "future" => Source(1101),
            "foreign-epoch" => Source(1090) with { CaptureEpoch = Guid.NewGuid() },
            _ => Source(1090)
        };
        // Establish an epoch using ordinary input before this pause in the dedicated identity case.
        if (defect == "foreign-epoch")
        {
            rig.Resume(pause); rig.Lease.Rotate(Source(rig.Now), 0, default); rig.Now++;
            pause = rig.Pause(false); rig.Now = pause.ReleasedAtMs + 90;
            source = Source(rig.Now) with { CaptureEpoch = Guid.NewGuid() };
        }
        if (defect == "copied-ticket") pause = pause with { };
        if (defect == "deadline") rig.Now = pause.ReleasedAtMs + 2000;
        if (defect == "cancel") rig.Cancellation.Cancel();
        if (defect == "close") rig.Lease.Close();
        if (defect == "target") rig.Available = false;
        Assert.NotNull(Record.Exception(() => rig.Lease.ResumeRecovery(pause, source, default)));
        Assert.Equal(0, rig.Downs); Assert.False(rig.Lease.ForwardHeld);
    }

    /// <summary>Exact150ms freshness and exact80ms both-clock barrier remain inclusive.</summary>
    [Theory]
    [InlineData(1080, 1080)]
    [InlineData(1230, 1080)]
    public async Task StationaryResumeRetainsExactBoundaryAcceptance(double now, double sourceAt)
    {
        await using var rig = new Rig(); var pause = rig.Pause(false); rig.Now = now;
        rig.Lease.ResumeRecovery(pause, Source(sourceAt), default);
        Assert.Null(rig.Lease.PendingRecovery); Assert.Equal(0, rig.Downs);
    }

    /// <summary>Hard lifecycle failures are checked before a new no-input allowance can be spent.</summary>
    [Theory]
    [InlineData("target")]
    [InlineData("cancel")]
    [InlineData("clock")]
    [InlineData("close")]
    public async Task HardFailurePrecedesStationaryAdmission(string defect)
    {
        await using var rig = new Rig();
        if (defect == "target") rig.Available = false;
        if (defect == "cancel") rig.Cancellation.Cancel();
        if (defect == "clock") rig.Now = 999;
        if (defect == "close") rig.Lease.Close();
        Assert.NotNull(Record.Exception(() => rig.Pause(false)));
        Assert.Empty(rig.Lease.RecoveryPauses); Assert.Equal(0, rig.Downs);
    }

    /// <summary>A verified waypoint hold is not a new run and cannot reset exhausted stationary budget.</summary>
    [Fact]
    public async Task PlannedWaypointDoesNotResetEitherAllowance()
    {
        await using var rig = new Rig(); rig.Resume(rig.Pause(false)); rig.Resume(rig.Pause(false));
        var hold = rig.Lease.BeginWaypointHold(default); rig.Now = hold.Release.CompletedAtMs + 90;
        rig.Lease.EndWaypointHold(hold, Source(rig.Now), rig.Now + 1000, default);
        Assert.Throws<InvalidOperationException>(() => rig.Pause(false));
        Assert.Equal("recovery_limit_exceeded", rig.Lease.Fault); Assert.Equal(2, rig.Lease.RecoveryPauses.Length);
    }

    /// <summary>All pauses retain the same worker/token/source history and original first-down latch.</summary>
    [Fact]
    public async Task StationaryPauseRetainsTheEntireLeaseLifetime()
    {
        await using var rig = new Rig(); var token = rig.Lease.Token;
        object? Field(string name) => typeof(NavigationBaselineInputLease).GetField(name,
            BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(rig.Lease);
        var worker = Field("_watchdog"); var stop = Field("_faultStop"); var monitor = Field("_monitorStop");
        rig.Lease.Forward(Source(rig.Now), default); rig.Now++; rig.Lease.ReleaseForward();
        var consumed = Field("_lastSource"); var pause = rig.Pause(false); rig.Resume(pause);
        Assert.Same(worker, Field("_watchdog")); Assert.Same(stop, Field("_faultStop"));
        Assert.Same(monitor, Field("_monitorStop")); Assert.Same(consumed, Field("_lastSource"));
        Assert.Equal(token, rig.Lease.Token); Assert.False(token.IsCancellationRequested);
        Assert.True((bool)Field("_firstForwardAttempted")!);
    }

    /// <summary>Legacy contracts still reject recovery enablement and retain their original terminal expiry behavior.</summary>
    [Theory]
    [InlineData("v1")]
    [InlineData("v2")]
    [InlineData("v3")]
    public async Task LegacyContractsDoNotGainStationaryReadiness(string contract)
    {
        await using var rig = new Rig(contract);
        Assert.Throws<InvalidOperationException>(() => rig.Lease.EnableRecovery());
        var grant = rig.Lease.Forward(Source(rig.Now), default); rig.Now = grant.ExpiresAtMs!.Value;
        rig.Lease.Check(); Assert.Equal("forward_lease_expired", rig.Lease.Fault);
        Assert.Empty(rig.Lease.RecoveryPauses); Assert.Equal(1, rig.Ups); Assert.False(rig.Lease.ForwardHeld);
    }
}
