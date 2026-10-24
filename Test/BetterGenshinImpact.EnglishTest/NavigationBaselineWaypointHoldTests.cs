using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Planned waypoint holds use fake clocks and sinks only; no game, GPU or operating-system input.</summary>
public sealed class NavigationBaselineWaypointHoldTests
{
    /// <summary>Immutable fake capture generation shared by one route.</summary>
    private static readonly Guid Epoch = Guid.Parse("1833ac6a-7438-486b-871a-f29565caa557");
    /// <summary>Both source clocks are independently controllable.</summary>
    private static GameCaptureSourceInfo Source(double acquired, double? reported = null) => new(Epoch,
        (long)((reported ?? acquired) * 10_000), (long)(acquired * Stopwatch.Frequency / 1000));
    /// <summary>Inspect exact worker/token/source ownership without creating a native backend.</summary>
    private static object? Field(NavigationBaselineInputLease lease, string name) =>
        typeof(NavigationBaselineInputLease).GetField(name, BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(lease);
    /// <summary>Fault fixtures still drain their single worker and dispose both token sources.</summary>
    private static async Task Drain(NavigationBaselineInputLease lease)
    { try { await lease.DisposeAsync(); } catch (InvalidOperationException) { } }

    /// <summary>Handoff sends no input, retains all run ownership, and leaves its source for the next ordinary decision once.</summary>
    [Fact]
    public async Task HoldAndEndPreserveOneLeaseAndDoNotConsumeTheAnchor()
    {
        double now = 1000; var downs = 0; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => ups++, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); var token = lease.Token;
            var fields = new[] { "_watchdog", "_faultStop", "_monitorStop" };
            var owners = fields.Select(name => Field(lease, name)).ToArray();
            var first = Source(990); lease.Forward(first, default); now = 1040;
            var ticket = lease.BeginWaypointHold(default);
            Assert.True(lease.WaypointHeld); Assert.False(lease.ForwardHeld);
            Assert.Equal("w_up", ticket.Release.Kind); Assert.Equal(1040, ticket.Release.CompletedAtMs);
            now = 1130; var anchor = Source(1120);
            lease.EndWaypointHold(ticket, anchor, 3040, default);
            Assert.False(lease.WaypointHeld); Assert.Equal(1, downs); Assert.Equal(1, ups);
            Assert.Equal(first, Assert.IsType<CaptureSourceEvidence>(Field(lease, "_lastSource")).WgcSource); Assert.Equal(token, lease.Token);
            for (var index = 0; index < fields.Length; index++) Assert.Same(owners[index], Field(lease, fields[index]));
            Assert.Empty(lease.RecoveryPauses); Assert.Null(lease.Fault);
            var next = lease.Forward(anchor, default);
            Assert.False(next.FirstForwardAttempt); Assert.Equal(150, next.GrantMs); Assert.Equal(2, downs);
            Assert.Throws<InvalidOperationException>(() => lease.BeginWaypointHold(default));
            Assert.Equal(2, downs); Assert.Single(lease.Events.Where(e => e.Kind == "waypoint_hold"));
            Assert.Single(lease.Events.Where(e => e.Kind == "waypoint_resume"));
        }
        finally { await Drain(lease); }
    }

    /// <summary>Already-released still pins its own completed cutoff; an older keyup cannot shorten the80ms barrier.</summary>
    [Fact]
    public async Task AlreadyReleasedGetsANewCutoffWithoutAnotherNativeKeyup()
    {
        double now = 1000; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => ups++, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1040; lease.ReleaseForward();
            now = 1100; var ticket = lease.BeginWaypointHold(default);
            Assert.Equal("already_released", ticket.Release.Kind); Assert.Equal(1100, ticket.Release.CompletedAtMs);
            now = 1180; lease.EndWaypointHold(ticket, Source(1180), 3100, default);
            Assert.Equal(1, ups); Assert.False(lease.WaypointHeld);
        }
        finally { await Drain(lease); }
    }

    /// <summary>Old expiry wins before hold admission, including expiry reached inside a slow availability check.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ExistingExpiryMustRecoverBeforeWaypointAdmission(bool slowTarget)
    {
        double now = 1000; var delay = false; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => { if (delay) now += 60; return true; },
            () => { }, () => ups++, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default);
            now = slowTarget ? 1100 : 1150; delay = slowTarget;
            var interruption = Assert.Throws<NavigationBaselineRecoveryRequired>(() => lease.BeginWaypointHold(default));
            Assert.Equal(NavigationBaselineRecoveryCause.LeaseExpired, interruption.Cause);
            Assert.False(lease.WaypointHeld); Assert.Equal(1, ups); Assert.False((bool)Field(lease, "_waypointAttempted")!);
            delay = false; now = 1250;
            lease.ResumeRecovery(lease.PendingRecovery!, Source(1240), default);
            Assert.Equal("already_released", lease.BeginWaypointHold(default).Release.Kind);
        }
        finally { delay = false; await Drain(lease); }
    }

    /// <summary>Latch before native keyup; neither reentrant nor later dispatch/recovery may bypass the hold.</summary>
    [Fact]
    public async Task HoldRejectsEveryInputAndRecoveryEntryBeforeAndAfterKeyup()
    {
        double now = 1000; var downs = 0; var cameras = 0; var blocked = 0;
        NavigationBaselineInputLease? lease = null;
        void Probe()
        {
            Action[] actions = [() => lease!.Forward(Source(1040), default), () => lease!.Rotate(Source(1040), 2, default),
                () => lease!.PauseForRecovery(new(NavigationBaselineRecoveryCause.SourceAge, "fake"), default),
                () => lease!.ResumeRecovery(new(1, NavigationBaselineRecoveryCause.SourceAge, 0, 0, null), Source(1040), default)];
            foreach (var action in actions)
            { Assert.Equal("waypoint_input_held", Assert.Throws<InvalidOperationException>(action).Message); blocked++; }
        }
        lease = new(() => now, () => true, () => downs++, Probe, _ => cameras++, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1040;
            lease.BeginWaypointHold(default); Probe();
            Assert.Equal(8, blocked); Assert.Equal(1, downs); Assert.Equal(0, cameras);
            Assert.Empty(lease.RecoveryPauses); Assert.Null(lease.Fault); Assert.False(lease.ForwardHeld);
        }
        finally { await Drain(lease); }
    }

    /// <summary>A target callback cannot let an outer admission replace a nested ticket or resurrect closed input.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ReentrantAdmissionCannotReplaceAHoldOrReopenClose(bool close)
    {
        double now = 1000; var nested = false; var ups = 0; NavigationBaselineInputLease? lease = null;
        NavigationBaselineWaypointHold? admitted = null;
        lease = new(() => now, () =>
        {
            if (nested)
            {
                nested = false;
                if (close) lease!.Close(); else admitted = lease!.BeginWaypointHold(default);
            }
            return true;
        }, () => { }, () => ups++, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1040; nested = true;
            Assert.Equal(close ? "baseline_input_closed" : "waypoint_hold_already_used",
                Assert.Throws<InvalidOperationException>(() => lease.BeginWaypointHold(default)).Message);
            Assert.Equal(1, ups); Assert.False(lease.ForwardHeld);
            if (!close)
            {
                Assert.Single(lease.Events.Where(e => e.Kind == "waypoint_hold"));
                now = 1130; lease.EndWaypointHold(admitted!, Source(1120), 3040, default);
                Assert.False(lease.WaypointHeld);
            }
            else Assert.Throws<InvalidOperationException>(() => lease.BeginWaypointHold(default));
        }
        finally { nested = false; await Drain(lease); }
    }

    /// <summary>Every invalid End is terminal and leaves the exact hold latched rather than entering movement recovery.</summary>
    [Theory]
    [InlineData("foreign", "waypoint_ticket_changed")]
    [InlineData("reported-barrier", "waypoint_source_before_release_barrier")]
    [InlineData("acquired-barrier", "waypoint_source_before_release_barrier")]
    [InlineData("age", "native_source_stale")]
    [InlineData("epoch", "source_epoch_changed")]
    [InlineData("regression", "native_source_regressed")]
    [InlineData("duplicate", "input_source_not_increasing")]
    [InlineData("future", "acquisition_in_future")]
    [InlineData("missing", "invalid_native_source")]
    [InlineData("owner-deadline", "waypoint_deadline_exceeded")]
    [InlineData("hold-deadline", "waypoint_deadline_exceeded")]
    [InlineData("invalid-deadline", "invalid_waypoint_deadline")]
    public async Task InvalidEndCannotResumeOrSpendARecovery(string reason, string expected)
    {
        double now = 1000; var downs = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => { }, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1040; var exact = lease.BeginWaypointHold(default);
            var ticket = reason == "foreign" ? exact with { } : exact; now = 1130;
            var source = reason switch
            {
                "reported-barrier" => Source(1130, 1119), "acquired-barrier" => Source(1119, 1130),
                "age" => Source(1120), "epoch" => Source(1120) with { CaptureEpoch = Guid.NewGuid() },
                "regression" => Source(989), "duplicate" => Source(990), "future" => Source(1131),
                "missing" => Source(1120) with { SourceTimestamp100ns = 0 }, _ => Source(1120)
            };
            if (reason == "age") now = 1271;
            if (reason == "hold-deadline") { now = 3040; source = Source(3030); }
            var deadline = reason == "owner-deadline" ? 1130 : reason == "invalid-deadline" ? double.NaN : 10_000;
            Assert.Equal(expected, Assert.Throws<InvalidOperationException>(() => lease.EndWaypointHold(ticket, source, deadline, default)).Message);
            Assert.True(lease.WaypointHeld); Assert.Equal(expected, lease.Fault); Assert.True(lease.Token.IsCancellationRequested);
            Assert.Empty(lease.RecoveryPauses); Assert.Equal(1, downs); Assert.False(lease.ForwardHeld);
            Assert.Throws<InvalidOperationException>(() => lease.EndWaypointHold(exact, Source(now), 10_000, default));
        }
        finally { await Drain(lease); }
    }

    /// <summary>Exact150ms freshness and exact80ms clocks remain accepted; no threshold is widened.</summary>
    [Fact]
    public async Task ExactSourceAgeAndBarrierBoundariesAreAccepted()
    {
        double now = 1000;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { }, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1040; var ticket = lease.BeginWaypointHold(default);
            now = 1270; lease.EndWaypointHold(ticket, Source(1120), 3040, default);
            Assert.False(lease.WaypointHeld); Assert.Null(lease.Fault);
        }
        finally { await Drain(lease); }
    }

    /// <summary>A delayed or reentrant target check cannot clear a hold after expiry, source aging, cancellation or Close.</summary>
    [Theory]
    [InlineData("owner-deadline", "waypoint_deadline_exceeded")]
    [InlineData("source-age", "native_source_stale")]
    [InlineData("target", "game_target_lost")]
    [InlineData("close", "baseline_input_closed")]
    [InlineData("reentrant-end", "waypoint_ticket_changed")]
    public async Task FinalTargetCheckCannotOverrunOrReopenTheHold(string reason, string expected)
    {
        double now = 1000; var delayed = false; NavigationBaselineInputLease? lease = null;
        NavigationBaselineWaypointHold? ticket = null;
        lease = new(() => now, () =>
        {
            if (!delayed) return true;
            delayed = false;
            if (reason == "close") lease!.Close();
            else if (reason == "reentrant-end") Assert.Throws<InvalidOperationException>(() => lease!.EndWaypointHold(ticket!, Source(1120), 2000, default));
            else now = reason == "owner-deadline" ? 1200 : 1271;
            return reason != "target";
        }, () => { }, () => { }, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1040; ticket = lease.BeginWaypointHold(default);
            now = 1130; delayed = true;
            var deadline = reason == "owner-deadline" ? 1200 : 3040;
            Assert.Equal(expected, Assert.Throws<InvalidOperationException>(() => lease.EndWaypointHold(ticket, Source(1120), deadline, default)).Message);
            Assert.True(lease.WaypointHeld); Assert.False(lease.ForwardHeld); Assert.Empty(lease.RecoveryPauses);
        }
        finally { delayed = false; await Drain(lease); }
    }

    /// <summary>Cancellation before or inside End stays terminal, even if another call supplies an uncancelled token.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task CancelledEndDoesNotClearTheHold(bool duringTarget)
    {
        double now = 1000; var checking = false; using var cancel = new CancellationTokenSource();
        var lease = new NavigationBaselineInputLease(() => now, () => { if (checking) cancel.Cancel(); return true; },
            () => { }, () => { }, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1040; var ticket = lease.BeginWaypointHold(default);
            now = 1130; checking = duringTarget; if (!duringTarget) cancel.Cancel();
            Assert.Throws<OperationCanceledException>(() => lease.EndWaypointHold(ticket, Source(1120), 3040, cancel.Token));
            Assert.Equal("baseline_cancelled", lease.Fault); Assert.True(lease.WaypointHeld);
            Assert.Throws<InvalidOperationException>(() => lease.EndWaypointHold(ticket, Source(1120), 3040, default));
        }
        finally { checking = false; await Drain(lease); }
    }

    /// <summary>A failed keyup remains terminal even if a later cleanup retry succeeds.</summary>
    [Fact]
    public async Task FailedReleaseCannotBeRearmedOrReset()
    {
        double now = 1000; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { },
            () => { if (++ups == 1) throw new IOException("uncertain-release"); }, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1040;
            Assert.Throws<InvalidOperationException>(() => lease.BeginWaypointHold(default));
            Assert.True(lease.WaypointHeld); Assert.Equal("uncertain-release", lease.ReleaseError);
            Assert.Equal("waypoint_release_failed", lease.Fault); Assert.True(lease.Token.IsCancellationRequested);
            Assert.True(ups >= 2); Assert.Empty(lease.RecoveryPauses);
        }
        finally { await Drain(lease); }
    }

    /// <summary>A partial physical-down failure remains terminal before any planned handoff can be admitted.</summary>
    [Fact]
    public async Task FailedDownCannotEnterWaypointHold()
    {
        double now = 1000; var downs = 0; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => { downs++; throw new IOException("partial-down"); }, () => ups++, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); Assert.Throws<IOException>(() => lease.Forward(Source(990), default));
            Assert.Equal("forward_dispatch_failed", Assert.Throws<InvalidOperationException>(() => lease.BeginWaypointHold(default)).Message);
            Assert.False(lease.WaypointHeld); Assert.False(lease.ForwardHeld); Assert.True((bool)Field(lease, "_firstForwardAttempted")!);
            Assert.Equal(1, downs); Assert.Equal(1, ups); Assert.Empty(lease.RecoveryPauses);
        }
        finally { await Drain(lease); }
    }

    /// <summary>The existing watchdog still checks target and owner cancellation while W is already released.</summary>
    [Theory]
    [InlineData("target", "game_target_lost")]
    [InlineData("cancel", "baseline_cancelled")]
    [InlineData("clock", "invalid_lease_clock")]
    [InlineData("deadline", "waypoint_deadline_exceeded")]
    public async Task WatchdogChecksRemainLiveDuringHold(string reason, string expected)
    {
        double now = 1000; var available = true; using var cancel = new CancellationTokenSource(); var downs = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => available, () => downs++, () => { }, _ => { }, cancel.Token, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1040; lease.BeginWaypointHold(default);
            if (reason == "target") available = false;
            if (reason == "cancel") cancel.Cancel();
            now = reason == "clock" ? 1039 : reason == "deadline" ? 3040 : 1100;
            lease.Check(); Assert.Equal(expected, lease.Fault); Assert.True(lease.Token.IsCancellationRequested);
            Assert.Equal(1, downs); Assert.False(lease.ForwardHeld); Assert.Empty(lease.RecoveryPauses);
        }
        finally { await Drain(lease); }
    }

    /// <summary>Close serialized behind a native release still permanently defeats the exact pending handoff.</summary>
    [Fact]
    public async Task ConcurrentCloseAfterReleasePreventsEnd()
    {
        double now = 1000; using var entered = new ManualResetEventSlim(); using var release = new ManualResetEventSlim();
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => { },
            () => { entered.Set(); Assert.True(release.Wait(2000)); }, _ => { }, default, false, "v4");
        Task<NavigationBaselineWaypointHold>? begin = null; Task<double>? close = null;
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1040;
            begin = Task.Run(() => lease.BeginWaypointHold(default)); Assert.True(entered.Wait(2000));
            close = Task.Run(lease.Close); release.Set();
            var ticket = await begin.WaitAsync(TimeSpan.FromSeconds(2)); await close.WaitAsync(TimeSpan.FromSeconds(2));
            now = 1130;
            Assert.Equal("baseline_input_closed", Assert.Throws<InvalidOperationException>(() => lease.EndWaypointHold(ticket, Source(1120), 3040, default)).Message);
            Assert.True(lease.WaypointHeld); Assert.False(lease.ForwardHeld);
        }
        finally
        {
            release.Set(); if (begin is not null) await begin; if (close is not null) await close;
            await Drain(lease);
        }
    }

    /// <summary>A consumed ticket cannot reopen a second time, even with another otherwise fresh source.</summary>
    [Fact]
    public async Task RepeatedEndIsTerminalWithoutAnExtraInput()
    {
        double now = 1000; var downs = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => { }, _ => { }, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1040; var ticket = lease.BeginWaypointHold(default);
            now = 1130; lease.EndWaypointHold(ticket, Source(1120), 3040, default);
            now = 1140;
            Assert.Equal("waypoint_ticket_changed", Assert.Throws<InvalidOperationException>(() => lease.EndWaypointHold(ticket, Source(1130), 3040, default)).Message);
            Assert.Equal("waypoint_ticket_changed", lease.Fault); Assert.Equal(1, downs); Assert.False(lease.ForwardHeld);
        }
        finally { await Drain(lease); }
    }

    /// <summary>The one real worker survives a held checkpoint and is drained only by normal terminal disposal.</summary>
    [Fact]
    public async Task RealWatchdogContinuesDuringHoldAndDrainsAtDispose()
    {
        long now = 1000; var checks = 0; using var cancel = new CancellationTokenSource();
        var lease = new NavigationBaselineInputLease(() => Interlocked.Read(ref now), () => { Interlocked.Increment(ref checks); return true; },
            () => { }, () => { }, _ => { }, cancel.Token, true, "v4");
        var worker = (Task)Field(lease, "_watchdog")!;
        try
        {
            lease.EnableRecovery(); lease.BeginWaypointHold(default); var before = Volatile.Read(ref checks);
            Assert.True(SpinWait.SpinUntil(() => Volatile.Read(ref checks) > before, TimeSpan.FromSeconds(2)));
            Assert.Same(worker, Field(lease, "_watchdog")); Assert.False(worker.IsCompleted); Assert.False(lease.Token.IsCancellationRequested);
            cancel.Cancel();
            Assert.True(SpinWait.SpinUntil(() => lease.Fault == "baseline_cancelled", TimeSpan.FromSeconds(2)));
            Assert.True(lease.WaypointHeld); Assert.False(lease.ForwardHeld);
        }
        finally { await Drain(lease); }
        Assert.True(worker.IsCompleted);
    }
}
