using System.Diagnostics;
using BetterGenshinImpact.GameTask.NavigationReset;
using BetterGenshinImpact.GameTask.Runtime;
using Fischless.GameCapture;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Deterministic opt-in reset accounting; no native timer, capture runtime, model or input is started.</summary>
public sealed class NavigationResetPollingTests
{
    /// <summary>Positive fake QPC and recorded waits make deadline tests independent of OS scheduling.</summary>
    private sealed class Clock
    {
        /// <summary>Initial QPC is shared with synthetic descriptor clocks.</summary>
        internal long Now = 10 * Stopwatch.Frequency;
        /// <summary>All requested waits, without turning them into claims about an actual timer.</summary>
        internal List<int> Waits { get; } = [];
        /// <summary>Advance the fake clock only by a known fixture interval.</summary>
        internal void Advance(int milliseconds) => Now += Stopwatch.Frequency * milliseconds / 1000;
        /// <summary>Model the caller's awaited delay, preserving cancellation.</summary>
        internal Task Delay(int milliseconds, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested(); Waits.Add(milliseconds); Advance(milliseconds); return Task.CompletedTask;
        }
    }

    /// <summary>One valid sample stands for the already checked native same-frame pose.</summary>
    private static NavigationResetSample Sample() => new(NavigationResetTask.SpawnX, NavigationResetTask.SpawnY, 0,
        DateTimeOffset.UnixEpoch, Guid.NewGuid(), 100_000_000, 10 * Stopwatch.Frequency, 1, 1, "City_102");
    /// <summary>Metadata outcome is typed; no retry string grants this classification.</summary>
    private static NavigationResetPoseProbe Pending() => new(null, "readback_pending", NavigationResetPoseProbeOutcome.ValidatedReadbackPending);
    /// <summary>A returned pixel/recognition miss remains charged and uses120ms.</summary>
    private static NavigationResetPoseProbe Miss() => new(null, "pose_source_stale; stage=after_capture");

    /// <summary>Forty metadata polls can finish before the first charged pose without resetting the original deadline.</summary>
    [Fact]
    public async Task RepeatedPendingThenPoseUsesOnlyOneObservation()
    {
        var clock = new Clock(); var calls = 0; var sample = Sample(); NavigationResetPollingDiagnostic? last = null;
        var sameReservation = new GameCapturePendingReadback(1, new GameCaptureSourceInfo(sample.SourceEpoch,
            sample.SourceTimestamp100ns!.Value, sample.AcquiredAtStopwatchTicks!.Value), clock.Now, 1920, 1080, null);
        var result = await NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            if (++calls > 40) return Task.FromResult(new NavigationResetPoseProbe(sample, null));
            GameCaptureReadbackConsumer.ValidatePending(sameReservation, clock.Now, expectedEpoch: sample.SourceEpoch,
                width: 1920, height: 1080);
            return Task.FromResult(Pending());
        },
            clock.Delay, CancellationToken.None, pollReadback: true, pendingDelay: clock.Delay,
            observePolling: value => last = value, timestamp: () => clock.Now);
        Assert.Same(sample, result); Assert.Equal(41, calls); Assert.Equal(40, clock.Waits.Count);
        Assert.All(clock.Waits, value => Assert.Equal(5, value));
        Assert.Equal(41, last!.PollCount); Assert.Equal(1, last.ChargedObservations); Assert.Equal(40, last.ValidatedPendingPolls);
        Assert.False(last.ReservationOutstanding); Assert.Equal("completed", last.Outcome);
        Assert.Equal(40, last.PendingWaitCount); Assert.Equal(200, last.PendingWaitSumMilliseconds);
        Assert.Equal(5, last.PendingWaitMaximumMilliseconds); Assert.Equal(0, last.ObservationWaitCount);
        Assert.Equal(3 * Stopwatch.Frequency, last.DeadlineAtTicks - last.StartedAtTicks);
    }

    /// <summary>Preparation's legacy ordinal remains1..25 and is not silently changed into the metadata-poll ordinal.</summary>
    [Fact]
    public async Task PreparationPendingDoesNotAdvanceObservationOrdinal()
    {
        var clock = new Clock(); var calls = 0; var ordinals = new List<int>(); NavigationResetPollingDiagnostic? last = null;
        await NavigationResetPreparationReadiness.WaitAsync((attempt, _) =>
        {
            ordinals.Add(attempt); return ++calls <= 40 ? NavigationResetPreparationState.ReadbackPending : NavigationResetPreparationState.Ready;
        }, clock.Delay, CancellationToken.None, () => clock.Now, true, clock.Delay, value => last = value);
        Assert.All(ordinals, value => Assert.Equal(1, value)); Assert.Equal(41, last!.PollCount);
        Assert.Equal(1, last.ChargedObservations); Assert.Equal(40, last.ValidatedPendingPolls);
    }

    /// <summary>At400 metadata refunds the next call and its extra wait are forbidden.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task PendingLimitIsLiteralAndFinite(bool preparation)
    {
        var clock = new Clock(); var calls = 0; NavigationResetPollingDiagnostic? last = null;
        Task Run() => preparation
            ? NavigationResetPreparationReadiness.WaitAsync((_, _) => { calls++; return NavigationResetPreparationState.ReadbackPending; },
                clock.Delay, CancellationToken.None, () => clock.Now, true, clock.Delay, value => last = value)
            : NavigationResetPoseAcquisition.ReadAsync(_ => { calls++; return Task.FromResult(Pending()); }, clock.Delay,
                CancellationToken.None, pollReadback: true, pendingDelay: clock.Delay, observePolling: value => last = value,
                timestamp: () => clock.Now);
        await Assert.ThrowsAnyAsync<TimeoutException>(Run);
        Assert.Equal(400, calls); Assert.Equal(399, clock.Waits.Count); Assert.All(clock.Waits, value => Assert.Equal(5, value));
        Assert.Equal(400, last!.PollCount); Assert.Equal(400, last.ValidatedPendingPolls); Assert.Equal(0, last.ChargedObservations);
        Assert.False(last.ReservationOutstanding); Assert.Equal("failed", last.Outcome);
    }

    /// <summary>The unchanged25-observation ceiling is checked before an extra native call, even with a stopped fake clock.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ActualObservationLimitRemainsTwentyFive(bool preparation)
    {
        var clock = new Clock(); var calls = 0; var delays = 0; NavigationResetPollingDiagnostic? last = null;
        Task Delay(int ms, CancellationToken _) { Assert.Equal(120, ms); delays++; return Task.CompletedTask; }
        Task Run() => preparation
            ? NavigationResetPreparationReadiness.WaitAsync((_, _) => { calls++; return NavigationResetPreparationState.SourceAge; },
                Delay, CancellationToken.None, () => clock.Now, true, Delay, value => last = value)
            : NavigationResetPoseAcquisition.ReadAsync(_ => { calls++; return Task.FromResult(Miss()); }, Delay,
                CancellationToken.None, pollReadback: true, pendingDelay: Delay, observePolling: value => last = value,
                timestamp: () => clock.Now);
        await Assert.ThrowsAnyAsync<TimeoutException>(Run);
        Assert.Equal(25, calls); Assert.Equal(24, delays); Assert.Equal(25, last!.ChargedObservations);
        Assert.Equal(0, last.ValidatedPendingPolls); Assert.Equal(25, last.PollCount);
    }

    /// <summary>A retry reason that looks like Pending is still an ordinary charged observation without typed proof.</summary>
    [Fact]
    public async Task RetryTextCannotManufactureMetadataRefund()
    {
        var clock = new Clock(); var calls = 0; NavigationResetPollingDiagnostic? last = null;
        await NavigationResetPoseAcquisition.ReadAsync(_ => Task.FromResult(++calls == 1
                ? new NavigationResetPoseProbe(null, "readback_pending") : new(Sample(), null)), clock.Delay,
            CancellationToken.None, pollReadback: true, pendingDelay: (_, _) => throw new Exception("wrong delay"),
            observePolling: value => last = value, timestamp: () => clock.Now);
        Assert.Equal(new[] { 120 }, clock.Waits); Assert.Equal(2, last!.ChargedObservations); Assert.Equal(0, last.ValidatedPendingPolls);
    }

    /// <summary>Malformed typed outputs retain their charge and cannot become pose or Pending authority.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task ContradictoryOrUnknownPoseOutcomeIsChargedFailure(bool hasSample)
    {
        var clock = new Clock(); NavigationResetPollingDiagnostic? last = null;
        var bad = hasSample ? new NavigationResetPoseProbe(Sample(), null, NavigationResetPoseProbeOutcome.ValidatedReadbackPending)
            : new NavigationResetPoseProbe(null, null, (NavigationResetPoseProbeOutcome)99);
        await Assert.ThrowsAsync<InvalidOperationException>(() => NavigationResetPoseAcquisition.ReadAsync(_ => Task.FromResult(bad),
            clock.Delay, CancellationToken.None, pollReadback: true, pendingDelay: clock.Delay,
            observePolling: value => last = value, timestamp: () => clock.Now));
        Assert.Empty(clock.Waits); Assert.Equal(1, last!.ChargedObservations); Assert.Equal(0, last.ValidatedPendingPolls);
    }

    /// <summary>Real native metadata checks throw before the helper can refund epoch, geometry or malformed descriptors.</summary>
    [Theory]
    [InlineData("identity")]
    [InlineData("epoch")]
    [InlineData("geometry")]
    [InlineData("regression")]
    public async Task InvalidMetadataNeverReturnsTypedPending(string kind)
    {
        var clock = new Clock(); var epoch = Guid.NewGuid(); NavigationResetPollingDiagnostic? last = null;
        var previous = new GameCaptureSourceInfo(epoch, 100_000_000, clock.Now);
        var pending = new GameCapturePendingReadback(1, previous, clock.Now, 1920, 1080, null);
        pending = kind switch
        {
            "identity" => pending with { SubmissionId = 0 },
            "epoch" => pending with { SourceInfo = previous with { CaptureEpoch = Guid.NewGuid() } },
            "geometry" => pending with { Width = 1280 },
            _ => pending with { SourceInfo = previous with { SourceTimestamp100ns = previous.SourceTimestamp100ns - 1 } }
        };
        await Assert.ThrowsAsync<InvalidOperationException>(() => NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            GameCaptureReadbackConsumer.ValidatePending(pending, clock.Now, previous, epoch, 1920, 1080);
            return Task.FromResult(Pending());
        }, clock.Delay, CancellationToken.None, pollReadback: true, pendingDelay: clock.Delay,
            observePolling: value => last = value, timestamp: () => clock.Now));
        Assert.Empty(clock.Waits); Assert.Equal(1, last!.PollCount); Assert.Equal(1, last.ChargedObservations);
        Assert.Equal(0, last.ValidatedPendingPolls); Assert.False(last.ReservationOutstanding);
    }

    /// <summary>The monotonic deadline rejects both late Ready and late Pending even before linked cancellation fires.</summary>
    [Theory]
    [InlineData(true, true)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(false, false)]
    public async Task LateNativeReturnCannotSucceed(bool preparation, bool ready)
    {
        var clock = new Clock(); var calls = 0; NavigationResetPollingDiagnostic? last = null;
        Task Run() => preparation
            ? NavigationResetPreparationReadiness.WaitAsync((_, _) => { calls++; clock.Advance(3000);
                return ready ? NavigationResetPreparationState.Ready : NavigationResetPreparationState.ReadbackPending; },
                clock.Delay, CancellationToken.None, () => clock.Now, true, clock.Delay, value => last = value)
            : NavigationResetPoseAcquisition.ReadAsync(_ => { calls++; clock.Advance(3000);
                return Task.FromResult(ready ? new NavigationResetPoseProbe(Sample(), null) : Pending()); }, clock.Delay,
                CancellationToken.None, pollReadback: true, pendingDelay: clock.Delay, observePolling: value => last = value,
                timestamp: () => clock.Now);
        await Assert.ThrowsAnyAsync<TimeoutException>(Run);
        Assert.Equal(1, calls); Assert.Empty(clock.Waits); Assert.Equal("failed", last!.Outcome);
        Assert.Equal(1, last.PollCount); Assert.Equal(ready ? 1 : 0, last.ChargedObservations);
    }

    /// <summary>Expiry during the Pending wait prevents another probe and preserves the requested versus actual interval.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task DeadlineAfterAwaitRejectsNextPoll(bool preparation)
    {
        var clock = new Clock(); var calls = 0; NavigationResetPollingDiagnostic? last = null;
        Task Delay(int ms, CancellationToken _) { Assert.Equal(5, ms); clock.Advance(3000); return Task.CompletedTask; }
        Task Run() => preparation
            ? NavigationResetPreparationReadiness.WaitAsync((_, _) => { calls++; return NavigationResetPreparationState.ReadbackPending; },
                clock.Delay, CancellationToken.None, () => clock.Now, true, Delay, value => last = value)
            : NavigationResetPoseAcquisition.ReadAsync(_ => { calls++; return Task.FromResult(Pending()); }, clock.Delay,
                CancellationToken.None, pollReadback: true, pendingDelay: Delay, observePolling: value => last = value,
                timestamp: () => clock.Now);
        await Assert.ThrowsAnyAsync<TimeoutException>(Run); Assert.Equal(1, calls);
        Assert.Equal(5, last!.LastWaitRequestedMilliseconds); Assert.Equal(3000, last.ObservedWaitMaximumMilliseconds);
    }

    /// <summary>Owner cancellation remains cancellation rather than being relabeled as the local timeout.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task OwnerCancellationDuringWaitPreservesProvenance(bool preparation)
    {
        using var owner = new CancellationTokenSource(); var clock = new Clock(); NavigationResetPollingDiagnostic? last = null;
        Task Delay(int _, CancellationToken token) { owner.Cancel(); token.ThrowIfCancellationRequested(); return Task.CompletedTask; }
        Task Run() => preparation
            ? NavigationResetPreparationReadiness.WaitAsync((_, _) => NavigationResetPreparationState.ReadbackPending,
                clock.Delay, owner.Token, () => clock.Now, true, Delay, value => last = value)
            : NavigationResetPoseAcquisition.ReadAsync(_ => Task.FromResult(Pending()), clock.Delay, owner.Token,
                pollReadback: true, pendingDelay: Delay, observePolling: value => last = value, timestamp: () => clock.Now);
        await Assert.ThrowsAnyAsync<OperationCanceledException>(Run); Assert.Equal("cancelled", last!.Outcome);
        Assert.False(last.ReservationOutstanding); Assert.Equal(1, last.ValidatedPendingPolls);
    }

    /// <summary>Unrelated native timeout/cancellation/worker failures are preserved without a retry.</summary>
    [Theory]
    [InlineData("timeout")]
    [InlineData("cancel")]
    [InlineData("worker")]
    public async Task UnrelatedFailuresAreNotLocalTimeouts(string kind)
    {
        var clock = new Clock(); var original = kind switch { "timeout" => (Exception)new TimeoutException("native timeout"),
            "cancel" => new OperationCanceledException("unrelated"), _ => new InvalidOperationException("timer failed") };
        NavigationResetPollingDiagnostic? last = null;
        var task = NavigationResetPoseAcquisition.ReadAsync(_ => Task.FromException<NavigationResetPoseProbe>(original), clock.Delay,
            CancellationToken.None, pollReadback: true, pendingDelay: clock.Delay,
            observePolling: value => last = value, timestamp: () => clock.Now);
        Assert.Same(original, await Record.ExceptionAsync(async () => { await task; }));
        Assert.Equal(1, last!.ChargedObservations); Assert.Equal(0, last.WaitCount);
    }

    /// <summary>A duplicate/late refund cannot erase a Ready charge or a later reservation.</summary>
    [Fact]
    public void ExactlyOnceSettlementPreservesLaterCharges()
    {
        var clock = new Clock(); var budget = new NavigationResetPollBudget(default, default, timestamp: () => clock.Now);
        var ready = budget.BeginPoll(); ready.Dispose();
        Assert.Throws<InvalidOperationException>(() => ready.CompleteValidatedPending());
        var pending = budget.BeginPoll(); pending.CompleteValidatedPending();
        Assert.Throws<InvalidOperationException>(() => pending.CompleteValidatedPending()); pending.Dispose();
        using var next = budget.BeginPoll();
        Assert.Throws<InvalidOperationException>(() => pending.CompleteValidatedPending());
        Assert.Equal(3, budget.Snapshot().PollCount); Assert.Equal(2, budget.Snapshot().ChargedObservations);
        Assert.Equal(1, budget.Snapshot().ValidatedPendingPolls);
    }

    /// <summary>Observer exceptions cannot erase the charge or replace original readiness behavior.</summary>
    [Fact]
    public void ThrowingDiagnosticObserverIsNotControlFlow()
    {
        var clock = new Clock(); var budget = new NavigationResetPollBudget(default, default,
            _ => throw new Exception("diagnostic"), () => clock.Now);
        using (budget.BeginPoll()) { }
        budget.Finish(null); Assert.Equal(1, budget.Snapshot().ChargedObservations);
    }

    /// <summary>No overlapping request or wait is admitted while native work still owns the reservation.</summary>
    [Fact]
    public async Task ActiveReservationBlocksAnotherCallAndAwait()
    {
        var clock = new Clock(); var budget = new NavigationResetPollBudget(default, default, timestamp: () => clock.Now);
        using var reservation = budget.BeginPoll();
        Assert.Throws<InvalidOperationException>(() => { budget.BeginPoll(); });
        await Assert.ThrowsAsync<InvalidOperationException>(() => budget.WaitAsync(5, clock.Delay));
        Assert.Equal(1, budget.Snapshot().PollCount); Assert.Empty(clock.Waits);
    }

    /// <summary>Regressing local time is hard failure, independent of cancellation scheduling.</summary>
    [Fact]
    public void ClockRegressionIsNotAnotherReadinessRetry()
    {
        var clock = new Clock(); var budget = new NavigationResetPollBudget(default, default, timestamp: () => clock.Now);
        clock.Now--; Assert.Throws<InvalidOperationException>(() => budget.CheckBudget());
    }

    /// <summary>The callback used at camera and map-close boundaries rejects a late dispatch while retaining its charge.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task RealWindowGuardPreventsLateInputInsideNativeProbe(bool preparation)
    {
        var clock = new Clock(); var inputs = 0; NavigationResetPollingDiagnostic? last = null;
        Task Run() => preparation
            ? NavigationResetPreparationReadiness.WaitAsync((_, _) => throw new Exception("legacy probe invoked"), clock.Delay,
                CancellationToken.None, () => clock.Now, true, clock.Delay, value => last = value,
                pollingProbe: (_, _, checkBudget) => { clock.Advance(3000); checkBudget(); inputs++; return NavigationResetPreparationState.MapClosing; })
            : NavigationResetPoseAcquisition.ReadAsync(_ => throw new Exception("legacy probe invoked"), clock.Delay,
                CancellationToken.None, pollReadback: true, pendingDelay: clock.Delay, observePolling: value => last = value,
                timestamp: () => clock.Now, pollingProbe: (_, checkBudget) =>
                { clock.Advance(3000); checkBudget(); inputs++; return Task.FromResult(new NavigationResetPoseProbe(Sample(), null)); });
        await Assert.ThrowsAnyAsync<TimeoutException>(Run); Assert.Equal(0, inputs);
        Assert.Equal(1, last!.ChargedObservations); Assert.Equal(0, last.ValidatedPendingPolls); Assert.False(last.ReservationOutstanding);
    }

    /// <summary>400 Pending and25 observation limits apply together without a counter reset between groups.</summary>
    [Fact]
    public void MixedReservationsKeepGlobalWindowConservation()
    {
        var clock = new Clock(); var budget = new NavigationResetPollBudget(default, default, timestamp: () => clock.Now);
        for (var i = 0; i < 24; i++) { using var charged = budget.BeginPoll(); }
        for (var i = 0; i < 399; i++)
        {
            using var pending = budget.BeginPoll(); pending.CompleteValidatedPending();
            var snapshot = budget.Snapshot(); Assert.Equal(snapshot.PollCount, snapshot.ChargedObservations + snapshot.ValidatedPendingPolls);
        }
        using (budget.BeginPoll()) { }
        Assert.Throws<NavigationResetPollLimitException>(() => { budget.BeginPoll(); });
        Assert.Equal(424, budget.Snapshot().PollCount); Assert.Equal(25, budget.Snapshot().ChargedObservations);
        Assert.Equal(399, budget.Snapshot().ValidatedPendingPolls);
    }

    /// <summary>Cancellation already present before entry admits neither native work nor a metadata refund.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task PreCancelledOwnerAdmitsNoProbe(bool preparation)
    {
        using var owner = new CancellationTokenSource(); owner.Cancel(); var calls = 0; var clock = new Clock();
        NavigationResetPollingDiagnostic? last = null;
        Task Run() => preparation
            ? NavigationResetPreparationReadiness.WaitAsync((_, _) => { calls++; return NavigationResetPreparationState.Ready; },
                clock.Delay, owner.Token, () => clock.Now, true, clock.Delay, value => last = value)
            : NavigationResetPoseAcquisition.ReadAsync(_ => { calls++; return Task.FromResult(new NavigationResetPoseProbe(Sample(), null)); },
                clock.Delay, owner.Token, pollReadback: true, pendingDelay: clock.Delay, observePolling: value => last = value,
                timestamp: () => clock.Now);
        await Assert.ThrowsAnyAsync<OperationCanceledException>(Run);
        Assert.Equal(0, calls); Assert.Equal(0, last!.PollCount); Assert.Equal("cancelled", last.Outcome);
    }

    /// <summary>Final success metadata distinguishes actual-observation waits from requested5ms metadata waits.</summary>
    [Fact]
    public async Task FinalSummarySeparatesWaitKindsAndRemainsBounded()
    {
        var clock = new Clock(); var calls = 0; NavigationResetPollingDiagnostic? last = null;
        await NavigationResetPoseAcquisition.ReadAsync(_ => Task.FromResult(++calls switch
            { 1 => Pending(), 2 => Miss(), _ => new NavigationResetPoseProbe(Sample(), null) }), clock.Delay,
            CancellationToken.None, pollReadback: true, pendingDelay: clock.Delay, observePolling: value => last = value,
            timestamp: () => clock.Now);
        Assert.Equal("completed", last!.Outcome); Assert.Equal(3, last.PollCount); Assert.Equal(2, last.ChargedObservations);
        Assert.Equal(1, last.PendingWaitCount); Assert.Equal(5, last.PendingWaitSumMilliseconds);
        Assert.Equal(1, last.ObservationWaitCount); Assert.Equal(120, last.ObservationWaitSumMilliseconds);
        Assert.Equal(125, last.ObservedWaitSumMilliseconds); Assert.Equal(120, last.LastWaitRequestedMilliseconds);
        Assert.NotNull(last.EndedAtTicks); Assert.False(last.ReservationOutstanding);
        Assert.True(JsonConvert.SerializeObject(last).Length < 2048);
    }

    /// <summary>Default callers retain25 total attempts and120ms delays, even for an old typed Pending fixture.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task DefaultModeDoesNotEnterMetadataAccounting(bool preparation)
    {
        var calls = 0; var waits = 0;
        Task Delay(int ms, CancellationToken _) { Assert.Equal(120, ms); waits++; return Task.CompletedTask; }
        Task Run() => preparation ? NavigationResetPreparationReadiness.WaitAsync((_, _) =>
            { calls++; return NavigationResetPreparationState.ReadbackPending; }, Delay, CancellationToken.None)
            : NavigationResetPoseAcquisition.ReadAsync(_ => { calls++; return Task.FromResult(Pending()); }, Delay, CancellationToken.None);
        await Assert.ThrowsAnyAsync<TimeoutException>(Run); Assert.Equal(25, calls); Assert.Equal(24, waits);
    }

    /// <summary>Old source logs stay version2 with no extra null field; only new ledgers select version3.</summary>
    [Fact]
    public void LogVersionIsExplicitAndLegacyShapeRemainsAbsent()
    {
        var plain = new NavigationResetSourceDiagnostic { Reason = "fixture", Stage = "capture" };
        var old = JObject.Parse(JsonConvert.SerializeObject(plain));
        Assert.Equal(2, (int)old["Version"]!); Assert.Null(old["PollingWindow"]);
        var clock = new Clock(); var budget = new NavigationResetPollBudget(default, default, timestamp: () => clock.Now);
        using (var reservation = budget.BeginPoll()) reservation.CompleteValidatedPending();
        budget.Finish(new TimeoutException("fixture"));
        var current = JObject.Parse(JsonConvert.SerializeObject(plain with { PollingWindow = budget.Snapshot() }));
        Assert.Equal(3, (int)current["Version"]!);
        Assert.Equal(1, (int)current["PollingWindow"]!["PollCount"]!);
        Assert.Equal(0, (int)current["PollingWindow"]!["ChargedObservations"]!);
        Assert.Equal(1, (int)current["PollingWindow"]!["ValidatedPendingPolls"]!);
        Assert.True(current.ToString(Formatting.None).Length < 4096);
    }
}
