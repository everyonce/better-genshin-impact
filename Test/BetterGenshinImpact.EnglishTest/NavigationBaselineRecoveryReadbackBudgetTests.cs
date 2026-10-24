using System.Diagnostics;
using System.Text.Json;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Paused recovery accounting uses fake clocks and input sinks; no capture/model/runtime or real input starts.</summary>
public sealed class NavigationBaselineRecoveryReadbackBudgetTests
{
    /// <summary>One immutable fake capture generation per independent test.</summary>
    private static readonly Guid Epoch = Guid.Parse("f9660d07-f7d3-4b22-acdd-2f905a009393");
    /// <summary>Convert fixture milliseconds to actual QPC units without assuming a particular host frequency.</summary>
    private static long Ticks(double ms) => (long)(ms * Stopwatch.Frequency / 1000);
    /// <summary>Both source clocks describe the same fake acquisition; no current wall clock is consulted.</summary>
    private static GameCaptureSourceInfo Source(double ms) => new(Epoch, (long)(ms * 10000), Ticks(ms));
    /// <summary>A valid unpublished submission has no pixel/sample/source-age authority.</summary>
    private static GameCapturePendingReadback Pending(double ms = 1000) => new(1, Source(ms), Ticks(ms), 1920, 1080, null);
    /// <summary>Keep the existing release ticket and its fixed two-second deadline in every scalar fixture.</summary>
    private static NavigationBaselineRecoveryAttempt Record(double start = 1000, double? deadline = null) => new()
    {
        Pause = new(1, NavigationBaselineRecoveryCause.SourceAge, start, start, null),
        TriggerCause = NavigationBaselineRecoveryCause.SourceAge, TriggerStage = "after_capture",
        DeadlineAtMs = deadline ?? start + 2000, ObservationStart = 0, PollStart = 0
    };

    /// <summary>The observed32-Pending-only shape can reach a later Ready source; metadata never rearms or presses W.</summary>
    [Fact]
    public async Task ThirtyTwoPendingThenReadyUsesOriginalLeaseAndBarrier()
    {
        double now = 1000; var downs = 0; var ups = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => downs++, () => ups++, _ => { }, default, false, "v4");
        lease.EnableRecovery(); lease.Forward(Source(990), default); now = 1150; lease.Check();
        var pause = lease.PendingRecovery!;
        var record = WithPause(pause);
        var budget = new NavigationBaselineRecoveryReadbackBudget(() => now, record, Source(990), 1920, 1080);
        var polls = new List<NavigationBaselineCapturePoll>();
        for (var i = 0; i < 32; i++)
        {
            using var call = budget.BeginCapture(default);
            var poll = NativeNavigationBaselineOperations.BeginCapturePoll(polls, 0, now);
            poll.RecoveryCaptureCharged = true;
            poll.RecordReadback(new(GameCaptureAttemptOutcome.ReadbackPending, pending: Pending(1150)));
            call.CompletePending(Pending(1150), Ticks(now), () => lease.Check(), default);
            poll.RecoveryCaptureCharged = false;
            await NativeNavigationBaselineOperations.WaitForReadbackAsync(poll, () => budget.Check(default), () => now,
                (deadline, _) => { now = deadline; return Task.CompletedTask; }, true, default);
            Assert.Same(pause, lease.PendingRecovery); Assert.False(lease.ForwardHeld);
            Assert.Equal(Source(990), budget.SeenSource); Assert.Null(poll.Source); Assert.Null(poll.SourceAgeMs);
        }
        using (var ready = budget.BeginCapture(default))
        {
            ready.CompleteCapture(); var source = Source(now - 1);
            budget.ValidateHeader(source, 1920, 1080, default);
            Assert.True(NavigationBaselineTask.AfterBarrier(source, pause.ReleasedAtMs, 80));
            lease.ResumeRecovery(pause, source, default);
        }
        budget.Close();
        Assert.Equal(33, record.PollCount); Assert.Equal(1, record.CaptureCount); Assert.Equal(32, record.PendingPollCount);
        Assert.False(record.ReservationOutstanding); Assert.Equal(1, downs); Assert.Equal(1, ups);
        Assert.Null(lease.PendingRecovery); Assert.False(lease.ForwardHeld);
    }

    /// <summary>Only the attempt's exact ticket changes in the replay fixture; it remains an ordinary mutable evidence DTO.</summary>
    private static NavigationBaselineRecoveryAttempt WithPause(NavigationBaselineRecoveryPause pause) => new()
    {
        Pause = pause, TriggerCause = NavigationBaselineRecoveryCause.LeaseExpired, TriggerStage = "watchdog",
        DeadlineAtMs = pause.StartedAtMs + 2000
    };

    /// <summary>Ready, null, native errors, setup failures and duplicate/barrier pixels all keep a charged unit.</summary>
    [Theory]
    [InlineData("ready")][InlineData("null")][InlineData("throw")][InlineData("setup")][InlineData("duplicate")][InlineData("barrier")]
    public void EveryNonPendingPathExhaustsTheUnchangedThirtyTwoCharges(string outcome)
    {
        var record = Record(); var budget = new NavigationBaselineRecoveryReadbackBudget(() => 1100, record, Source(990), 1920, 1080);
        for (var i = 0; i < 32; i++)
        {
            using var call = budget.BeginCapture(default);
            if (outcome is not ("throw" or "setup")) call.CompleteCapture();
        }
        Assert.Equal("recovery_capture_limit_exceeded", Assert.Throws<InvalidOperationException>(() => budget.BeginCapture(default)).Message);
        Assert.Equal(32, record.PollCount); Assert.Equal(32, record.CaptureCount); Assert.Equal(0, record.PendingPollCount);
        budget.Check(default); // The completed final charged call may still resume before the same fixed deadline.
        budget.Close(); Assert.False(record.ReservationOutstanding);
    }

    /// <summary>The independent400-Pending cap prevents another call even when no pixels were charged.</summary>
    [Fact]
    public void PendingCapAndMixedGlobalAccountingAreFinite()
    {
        var record = Record(); var budget = new NavigationBaselineRecoveryReadbackBudget(() => 1100, record, Source(990), 1920, 1080);
        for (var i = 0; i < 31; i++) budget.BeginCapture(default).Dispose();
        for (var i = 0; i < 400; i++)
        {
            using var call = budget.BeginCapture(default);
            call.CompletePending(Pending(), Ticks(1100), () => { }, default);
        }
        Assert.Equal(431, record.PollCount); Assert.Equal(31, record.CaptureCount); Assert.Equal(400, record.PendingPollCount);
        Assert.Equal(record.PollCount, record.CaptureCount + record.PendingPollCount);
        Assert.Equal("recovery_pending_poll_limit_exceeded", Assert.Throws<InvalidOperationException>(() => budget.BeginCapture(default)).Message);
        budget.Close();
    }

    /// <summary>Malformed/changed metadata stays charged and cannot be hidden by a simultaneous elapsed deadline.</summary>
    [Theory]
    [InlineData("epoch", "source_epoch_changed")][InlineData("regression", "native_source_regressed")]
    [InlineData("geometry", "native_frame_geometry_changed")][InlineData("submission", "invalid_pending_readback_metadata")]
    [InlineData("future", "invalid_pending_readback_metadata")]
    public void InvalidPendingIsNeverRefunded(string kind, string expected)
    {
        double now = 1100; var record = Record();
        var budget = new NavigationBaselineRecoveryReadbackBudget(() => now, record, Source(1000), 1920, 1080);
        var pending = kind switch
        {
            "epoch" => Pending() with { SourceInfo = Source(1000) with { CaptureEpoch = Guid.NewGuid() } },
            "regression" => Pending(999), "geometry" => Pending() with { Width = 1919 },
            "submission" => Pending() with { SubmissionId = 0 }, _ => Pending(4001)
        };
        using (var call = budget.BeginCapture(default))
        {
            now = 4000;
            var error = Assert.Throws<InvalidOperationException>(() => call.CompletePending(pending, Ticks(now),
                () => throw new Exception("hard metadata must be checked first"), default));
            Assert.Equal(expected, error.Message);
        }
        Assert.Equal(1, record.CaptureCount); Assert.Equal(0, record.PendingPollCount); Assert.False(record.ReservationOutstanding);
    }

    /// <summary>A slow target check, cancellation, or clock regression after native return retains the provisional charge.</summary>
    [Theory]
    [InlineData("deadline")][InlineData("target")][InlineData("cancel")][InlineData("clock")]
    public void PostCaptureGuardFailureCannotRefund(string failure)
    {
        double now = 1100; using var stop = new CancellationTokenSource(); var record = Record(deadline: 1200);
        var budget = new NavigationBaselineRecoveryReadbackBudget(() => now, record, Source(990), 1920, 1080);
        using (var call = budget.BeginCapture(stop.Token))
        {
            var error = Xunit.Record.Exception(() => call.CompletePending(Pending(), Ticks(now), () =>
            {
                if (failure == "target") throw new InvalidOperationException("game_target_lost");
                if (failure == "cancel") stop.Cancel(); else now = failure == "clock" ? 1099 : 1200;
            }, stop.Token));
            Assert.NotNull(error);
            Assert.Equal(failure switch { "target" => "game_target_lost", "clock" => "invalid_recovery_window",
                "deadline" => "recovery_deadline_exceeded", _ => error!.Message }, error!.Message);
            if (failure == "cancel") Assert.IsAssignableFrom<OperationCanceledException>(error);
        }
        Assert.Equal(1, record.CaptureCount); Assert.Equal(0, record.PendingPollCount); Assert.Equal(1200, record.DeadlineAtMs);
    }

    /// <summary>A valid stale header constrains later unpublished metadata while accepted source/barriers stay external.</summary>
    [Fact]
    public void PendingBehindDiscardedHeaderFailsWithoutAdvancingTheFloor()
    {
        double now = 1300; var record = Record(); var consumed = Source(990);
        var budget = new NavigationBaselineRecoveryReadbackBudget(() => now, record, consumed, 1920, 1080);
        using (var call = budget.BeginCapture(default)) call.CompleteCapture();
        budget.ValidateHeader(Source(1100), 1920, 1080, default); // Age200ms: hard header only, no readiness.
        using (var call = budget.BeginCapture(default))
            Assert.Equal("native_source_regressed", Assert.Throws<InvalidOperationException>(() =>
                call.CompletePending(Pending(1099), Ticks(now), () => { }, default)).Message);
        foreach (var sourceMs in new[] { 1100, 1200 })
        {
            using var call = budget.BeginCapture(default);
            call.CompletePending(Pending(sourceMs), Ticks(now), () => { }, default);
            Assert.Equal(Source(1100), budget.SeenSource);
        }
        Assert.Equal(Source(990), consumed); Assert.Equal(2, record.CaptureCount); Assert.Equal(2, record.PendingPollCount);
    }

    /// <summary>The newer typed triggering source constrains the first poll before any recovery capture is admitted.</summary>
    [Fact]
    public void TriggerHeaderFloorAndChangedAcquisitionArePreserved()
    {
        double now = 1300; var record = Record();
        var budget = new NavigationBaselineRecoveryReadbackBudget(() => now, record, Source(990), 1920, 1080);
        budget.ValidateHeader(Source(1100), 1920, 1080, default);
        Assert.Equal(0, record.PollCount);
        using (var call = budget.BeginCapture(default))
            Assert.Equal("native_source_regressed", Assert.Throws<InvalidOperationException>(() =>
                call.CompletePending(Pending(1099), Ticks(now), () => { }, default)).Message);
        now = 4000;
        Assert.Equal("native_source_regressed", Assert.Throws<InvalidOperationException>(() =>
            budget.ValidateHeader(Source(1100) with { AcquiredAtStopwatchTicks = Ticks(1101) }, 1920, 1080, default)).Message);
        Assert.Equal(Source(1100), budget.SeenSource);
    }

    /// <summary>Existing raw source-future-QPC semantics are preserved; only immutable acquisition/submission must be current.</summary>
    [Fact]
    public void RawReportedFutureDoesNotAcquirePixelsOrChangeClockPolicy()
    {
        var record = Record(); var budget = new NavigationBaselineRecoveryReadbackBudget(() => 1100, record, Source(990), 1920, 1080);
        using var call = budget.BeginCapture(default);
        call.CompletePending(Pending() with { SourceInfo = Source(1000) with { SourceTimestamp100ns = 2000 * 10000L } },
            Ticks(1100), () => { }, default);
        Assert.Equal(1, record.PendingPollCount); Assert.Equal(Source(990), budget.SeenSource);
    }

    /// <summary>Close settles setup failure once; a stale reservation cannot refund the next call or outlive the window.</summary>
    [Fact]
    public void ReservationAndCloseOwnershipAreExact()
    {
        var record = Record(); var budget = new NavigationBaselineRecoveryReadbackBudget(() => 1100, record, Source(990), 1920, 1080);
        var old = budget.BeginCapture(default); old.CompleteCapture();
        var current = budget.BeginCapture(default);
        Assert.Throws<InvalidOperationException>(() => old.CompletePending(Pending(), Ticks(1100), () => { }, default));
        Assert.True(record.ReservationOutstanding); budget.Close(); budget.Close(); current.Dispose();
        Assert.False(record.ReservationOutstanding); Assert.Equal(2, record.CaptureCount); Assert.Equal(0, record.PendingPollCount);
        Assert.Throws<InvalidOperationException>(() => current.CompletePending(Pending(), Ticks(1100), () => { }, default));
        Assert.Throws<InvalidOperationException>(() => budget.BeginCapture(default));
    }

    /// <summary>Target-check reentrancy can close a window but cannot turn its already charged call into a late refund.</summary>
    [Fact]
    public void CloseDuringFinalGuardKeepsCharge()
    {
        var record = Record(); var budget = new NavigationBaselineRecoveryReadbackBudget(() => 1100, record, Source(990), 1920, 1080);
        using var call = budget.BeginCapture(default);
        Assert.Throws<InvalidOperationException>(() => call.CompletePending(Pending(), Ticks(1100), budget.Close, default));
        Assert.Equal(1, record.CaptureCount); Assert.Equal(0, record.PendingPollCount); Assert.False(record.ReservationOutstanding);
    }

    /// <summary>Every retained refunded row is metadata-only, and the selected recovery file schema is explicit.</summary>
    [Fact]
    public void FileEvidenceHasIndependentCountersAndNoPendingPixelAuthority()
    {
        var record = Record(); var budget = new NavigationBaselineRecoveryReadbackBudget(() => 1100, record, Source(990), 1920, 1080);
        var poll = new NavigationBaselineCapturePoll(0, 1100) { RecoveryCaptureCharged = true };
        poll.RecordReadback(new(GameCaptureAttemptOutcome.ReadbackPending, pending: Pending()));
        using (var call = budget.BeginCapture(default)) call.CompletePending(Pending(), Ticks(1100), () => { }, default);
        poll.RecoveryCaptureCharged = false; budget.Close();
        var journal = new NavigationBaselineJournal { RunId = new string('a', 32), GameProcessId = 1, WindowsSessionId = 3,
            WorkflowResult = new() { TimingContract = "v4" }, Observations = [], InputTransitions = [], ScheduleWaits = [],
            ObservationAttempts = [], CapturePolls = [poll], RecoveryAttempts = [record] };
        using var data = JsonDocument.Parse(journal.Serialize()); var root = data.RootElement;
        Assert.Equal(3, root.GetProperty("recoverySchemaVersion").GetInt32());
        Assert.False(root.GetProperty("capturePolls")[0].GetProperty("recoveryCaptureCharged").GetBoolean());
        Assert.Equal(JsonValueKind.Null, root.GetProperty("capturePolls")[0].GetProperty("source").ValueKind);
        Assert.Equal(400, root.GetProperty("recoveryAttempts")[0].GetProperty("maximumPendingPolls").GetInt32());
        Assert.False(root.GetProperty("trainingEligible").GetBoolean());
    }
}
