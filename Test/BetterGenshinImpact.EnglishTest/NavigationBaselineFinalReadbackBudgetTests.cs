using System.Diagnostics;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.GameTask.Runtime;
using Fischless.GameCapture;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Deterministic final-only Pending accounting; no real capture, input, model or timing sleeps.</summary>
public sealed class NavigationBaselineFinalReadbackBudgetTests
{
    /// <summary>One immutable synthetic capture generation throughout the window.</summary>
    private static readonly Guid Epoch = Guid.Parse("713e569b-05ac-4a78-aadf-8a29455fcd92");
    /// <summary>Exact positive clocks; raw report and acquisition remain independently represented.</summary>
    private static GameCaptureSourceInfo Source(long ms) => new(Epoch, ms * 10000, ms * Stopwatch.Frequency / 1000);
    /// <summary>Small fixed published geometry, independent of any native desktop.</summary>
    private static GameCapturePendingReadback Pending(long id = 1) => new(id, Source(1000), 1001 * Stopwatch.Frequency / 1000, 4, 3, null);
    /// <summary>Shared counter identity at each settled boundary, without claiming a call necessarily completed.</summary>
    private static void Counts(NavigationBaselineFinalVerification window, int captures, int pending)
    {
        Assert.Equal(captures, window.Record.CaptureCount); Assert.Equal(pending, window.Record.PendingPollCount);
        Assert.Equal(captures + pending, window.Record.PollCount);
        Assert.Equal(1000, window.ClosedAtMs); Assert.Equal(3000, window.Record.DeadlineAtMs);
    }
    /// <summary>Native composition uses this exact existing metadata validator before a Pending refund.</summary>
    private static void Refund(NavigationBaselineFinalVerification window,
        NavigationBaselineFinalVerification.CaptureReservation reservation, GameCapturePendingReadback pending, double now)
    {
        GameCaptureReadbackConsumer.ValidatePending(pending, (long)(now * Stopwatch.Frequency / 1000), window.SeenSource.WgcSource,
            width: 4, height: 3);
        reservation.CompletePending();
    }

    /// <summary>More than32 returns of the same immutable reservation are polling, not new pixels or age authority.</summary>
    [Fact]
    public void RepeatedSameReservationPassesOldCaptureLimitWithoutChangingHighWater()
    {
        double now = 1100; var source = Source(900);
        var window = new NavigationBaselineFinalVerification(() => now, 1000, 31000, source, 0, 0);
        var pending = Pending();
        for (var i = 0; i < 40; i++)
        {
            using var reservation = window.BeginCapture(default);
            Assert.True(reservation.CaptureCharged); Counts(window, 1, i);
            Refund(window, reservation, pending, now); Assert.False(reservation.CaptureCharged);
            Counts(window, 0, i + 1); now += 5;
        }
        Assert.Same(source, window.SeenSource?.WgcSource); Assert.Empty(window.Record.AcceptedReadIndices);
        Assert.Equal(0, window.Record.ReadCount); Assert.Equal(0, window.Record.SourceAgeDiscards);
    }

    /// <summary>Literal400-Pending allowance ends before another reservation/native call, even with a nonadvancing fake clock.</summary>
    [Fact]
    public void PendingLimitStopsBeforeFourHundredFirstCall()
    {
        var window = new NavigationBaselineFinalVerification(() => 1100, 1000, 31000, Source(900), 0, 0);
        var pending = Pending(); var calls = 0;
        for (; calls < 400; calls++)
        {
            using var reservation = window.BeginCapture(default); Refund(window, reservation, pending, 1100);
        }
        Assert.Equal("final_verification_pending_poll_limit_exceeded",
            Assert.Throws<InvalidOperationException>(() => window.BeginCapture(default)).Message);
        Assert.Equal(400, calls); Counts(window, 0, 400);
        Assert.Equal(400, window.Record.MaximumPendingPolls); Assert.Equal(432, window.Record.MaximumPolls);
    }

    /// <summary>Ready/unavailable/error calls still exhaust the unchanged32-capture budget after any earlier Pending work.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void ChargedLimitRemainsThirtyTwo(bool exceptional)
    {
        var window = new NavigationBaselineFinalVerification(() => 1100, 1000, 31000, Source(900), 0, 0);
        for (var i = 0; i < 39; i++)
        { using var reservation = window.BeginCapture(default); Refund(window, reservation, Pending(), 1100); }
        for (var i = 0; i < 32; i++)
        {
            using var reservation = window.BeginCapture(default);
            if (!exceptional) reservation.CompleteCapture();
        }
        Assert.Equal("final_verification_capture_limit_exceeded",
            Assert.Throws<InvalidOperationException>(() => window.BeginCapture(default)).Message);
        Counts(window, 32, 39);
    }

    /// <summary>Duplicate explicit completion and late refunds cannot steal units from an earlier or active later call.</summary>
    [Theory]
    [InlineData("ready")] [InlineData("pending")] [InlineData("error")]
    public void EveryReservationSettlesAtMostOnce(string outcome)
    {
        var window = new NavigationBaselineFinalVerification(() => 1100, 1000, 31000, Source(900), 0, 0);
        var first = window.BeginCapture(default);
        if (outcome == "ready") first.CompleteCapture();
        else if (outcome == "pending") Refund(window, first, Pending(), 1100);
        else first.Dispose();
        first.Dispose(); first.Dispose();
        using var next = window.BeginCapture(default);
        Assert.Equal("final_verification_capture_already_settled", Assert.Throws<InvalidOperationException>(first.CompletePending).Message);
        Assert.Equal("final_verification_capture_already_settled", Assert.Throws<InvalidOperationException>(first.CompleteCapture).Message);
        Counts(window, outcome == "pending" ? 1 : 2, outcome == "pending" ? 1 : 0);
        next.CompleteCapture();
        Counts(window, outcome == "pending" ? 1 : 2, outcome == "pending" ? 1 : 0);
    }

    /// <summary>Unsettled work cannot overlap another native invocation; setup failure keeps its conservative charge.</summary>
    [Fact]
    public void SetupFailureSettlesWithoutAnotherNativeCall()
    {
        var window = new NavigationBaselineFinalVerification(() => 1100, 1000, 31000, Source(900), 0, 0);
        using (var reservation = window.BeginCapture(default))
            Assert.Equal("final_verification_capture_unsettled", Assert.Throws<InvalidOperationException>(() => window.BeginCapture(default)).Message);
        Counts(window, 1, 0);
        using var next = window.BeginCapture(default); next.CompleteCapture(); Counts(window, 2, 0);
    }

    /// <summary>Metadata rejection occurs before settlement; no stale descriptor, changed epoch or geometry earns a refund.</summary>
    [Theory]
    [InlineData("submission")] [InlineData("epoch")] [InlineData("regression")]
    [InlineData("identity")] [InlineData("geometry")] [InlineData("future_submit")]
    public void MalformedPendingRemainsCharged(string change)
    {
        var previous = Source(1000);
        var window = new NavigationBaselineFinalVerification(() => 1100, 1000, 31000, previous, 0, 0);
        var pending = change switch
        {
            "submission" => Pending() with { SubmissionId = 0 },
            "epoch" => Pending() with { SourceInfo = previous with { CaptureEpoch = Guid.NewGuid() } },
            "regression" => Pending() with { SourceInfo = Source(999) },
            "identity" => Pending() with { SourceInfo = previous with { AcquiredAtStopwatchTicks = previous.AcquiredAtStopwatchTicks + 1 } },
            "geometry" => Pending() with { Width = 8 },
            _ => Pending() with { SubmittedAtStopwatchTicks = 1101 * Stopwatch.Frequency / 1000 }
        };
        using (var reservation = window.BeginCapture(default))
            Assert.Throws<InvalidOperationException>(() => Refund(window, reservation, pending, 1100));
        Counts(window, 1, 0); Assert.Same(previous, window.SeenSource?.WgcSource);
    }

    /// <summary>Real typed consumer errors cannot become Pending refunds; exceptional scope cleanup settles once.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void NativeThrowOrMalformedTypedResultKeepsCharge(bool malformed)
    {
        var window = new NavigationBaselineFinalVerification(() => 1100, 1000, 31000, Source(900), 0, 0);
        using (var reservation = window.BeginCapture(default))
        {
            Assert.Throws<InvalidOperationException>((Action)(() =>
            {
                if (!malformed) throw new InvalidOperationException("native_capture_failed");
                var capture = new GameCaptureReadbackConsumerTests.FakeCapture(GameCaptureReadbackMode.PollSingleV1)
                { Attempt = new(GameCaptureAttemptOutcome.ReadbackPending, pending: Pending() with { SubmissionId = 0 }) };
                _ = GameCaptureReadbackConsumer.Capture(capture, true, out _);
                reservation.CompletePending();
            }));
        }
        Counts(window, 1, 0);
    }

    /// <summary>Ready with a next staged refill is still one completed capture; null is terminal and charged too.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void ReadyRefillAndUnavailableKeepCharge(bool ready)
    {
        var window = new NavigationBaselineFinalVerification(() => 1100, 1000, 31000, Source(900), 0, 0);
        using var frame = ready ? new GameCaptureFrame(new Mat(3, 4, MatType.CV_8UC3), null, Source(1090)) : null;
        var capture = new GameCaptureReadbackConsumerTests.FakeCapture(GameCaptureReadbackMode.PollSingleV1)
        { Attempt = ready ? new(GameCaptureAttemptOutcome.FrameReady, frame, Pending()) : default };
        using var reservation = window.BeginCapture(default);
        var result = GameCaptureReadbackConsumer.Capture(capture, true, out _);
        Assert.NotEqual(GameCaptureAttemptOutcome.ReadbackPending, result.Outcome);
        reservation.CompleteCapture(); Assert.True(reservation.CaptureCharged); Counts(window, 1, 0);
        if (ready) { Assert.Same(frame, result.Frame); Assert.NotNull(result.Pending); }
        else Assert.Null(result.Frame);
    }

    /// <summary>Late-return/cancelled Pending may be classified, but continuation cannot escape the original closed-input deadline.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public async Task PendingWaitStillFailsDeadlineOrOwnerCancellation(bool cancel)
    {
        double now = 1100; using var stop = new CancellationTokenSource();
        var window = new NavigationBaselineFinalVerification(() => now, 1000, 31000, Source(900), 0, 0);
        using var reservation = window.BeginCapture(stop.Token); Refund(window, reservation, Pending(), now);
        var poll = new NavigationBaselineCapturePoll(0, now);
        Task Wait() => NativeNavigationBaselineOperations.WaitForReadbackAsync(poll, () => window.Check(stop.Token), () => now,
            (_, _) => { if (cancel) stop.Cancel(); else now = 3000; return Task.CompletedTask; }, false, stop.Token);
        if (cancel) await Assert.ThrowsAnyAsync<OperationCanceledException>(Wait);
        else await Assert.ThrowsAsync<NavigationBaselineFinalVerification.TimeoutException>(Wait);
        Counts(window, 0, 1); Assert.Empty(window.Record.AcceptedReadIndices);
    }

    /// <summary>The owner may clip the original2s deadline; refunds never change that deadline or allow one more call.</summary>
    [Fact]
    public void OwnerClippedDeadlineStopsBeforeReservation()
    {
        double now = 1100;
        var window = new NavigationBaselineFinalVerification(() => now, 1000, 1200, Source(900), 0, 0);
        using (var reservation = window.BeginCapture(default)) Refund(window, reservation, Pending(), now);
        now = 1200;
        Assert.Throws<NavigationBaselineFinalVerification.TimeoutException>(() => window.BeginCapture(default));
        Assert.Equal(1, window.Record.PollCount); Assert.Equal(1200, window.Record.DeadlineAtMs);
    }

    /// <summary>Global4096 poll evidence still rejects before the native call despite local Pending capacity.</summary>
    [Fact]
    public void GlobalPollCapacityIsNotRefunded()
    {
        var polls = new List<NavigationBaselineCapturePoll>();
        for (var i = 0; i < NativeNavigationBaselineOperations.MaximumCapturePolls; i++)
            NativeNavigationBaselineOperations.BeginCapturePoll(polls, 0, i);
        Assert.Equal("capture_diagnostics_capacity_exceeded", Assert.Throws<InvalidOperationException>(() =>
            NativeNavigationBaselineOperations.BeginCapturePoll(polls, 0, 4096)).Message);
        Assert.Equal(4096, polls.Count);
    }

    /// <summary>Per-observation calls retain legacy total meaning; only final v2 carries the nullable per-poll charge.</summary>
    [Fact]
    public void JournalDistinguishesTotalAttemptCountAndSettledFinalBudget()
    {
        var window = new NavigationBaselineFinalVerification(() => 1100, 1000, 31000, Source(900), 0, 0);
        var read = new NavigationBaselineObservationAttempt(1100) { CaptureCount = 2 };
        var pendingPoll = new NavigationBaselineCapturePoll(0, 1100) { FinalVerificationCaptureCharged = true };
        using (var reservation = window.BeginCapture(default))
        {
            pendingPoll.RecordReadback(new(GameCaptureAttemptOutcome.ReadbackPending, pending: Pending()));
            Refund(window, reservation, Pending(), 1100); pendingPoll.FinalVerificationCaptureCharged = reservation.CaptureCharged;
        }
        var readyPoll = new NavigationBaselineCapturePoll(0, 1101) { FinalVerificationCaptureCharged = true };
        window.BeginCapture(default).CompleteCapture(); Counts(window, 1, 1);
        Assert.Equal(2, read.CaptureCount); Assert.False(pendingPoll.FinalVerificationCaptureCharged);
        Assert.True(readyPoll.FinalVerificationCaptureCharged);
        Assert.Null(new NavigationBaselineCapturePoll(0, 900).FinalVerificationCaptureCharged);
        Assert.Equal(2, NavigationBaselineFinalVerification.Version);
    }

    /// <summary>One read may wait past the old32-poll limit then admit three genuinely distinct, spaced poses in the same window.</summary>
    [Fact]
    public async Task ManyPendingThenThreeFreshPosesCompleteWithoutRestartingFinalWindow()
    {
        double now = 1100;
        var window = new NavigationBaselineFinalVerification(() => now, 1000, 31000, Source(900), 0, 0);
        var samples = new List<NavigationBaselineSample>(); var decisions = new List<NavigationBaselineDecision>();
        var totalCalls = 0; var pending = Pending();
        await window.CollectAsync(async token =>
        {
            if (samples.Count == 0)
                for (var i = 0; i < 40; i++)
                {
                    using var reservation = window.BeginCapture(token); totalCalls++;
                    Refund(window, reservation, pending, now);
                    await NativeNavigationBaselineOperations.WaitForReadbackAsync(new(0, now), () => window.Check(token), () => now,
                        (at, _) => { now = at; return Task.CompletedTask; }, false, token);
                }
            window.BeginCapture(token).CompleteCapture(); totalCalls++;
            var atSource = (long)now - 5; var source = Source(atSource);
            var sample = new NavigationBaselineSample(NavigationBaselineTask.EndX, NavigationBaselineTask.EndY, 47,
                DateTimeOffset.UnixEpoch, Epoch, source.SourceTimestamp100ns, source.AcquiredAtStopwatchTicks,
                .999, .8, "City_102", new("normal", AgentMotionEvidence.MethodName, false, false, 1), 5, 47,
                0, NavigationBaselineTask.Length, 0, new(atSource - 1, atSource, now, now));
            var read = new NavigationBaselineObservationAttempt(now);
            window.ValidateSource(source, "after_capture", read, token); window.ValidatePose(sample);
            window.Admit(sample, samples.Count, read, value => NavigationBaselineFinalVerification.StageDecision(value, samples, decisions),
                () => { }, () => { }, token);
            return sample;
        }, (at, _) => { now = at; return Task.CompletedTask; }, default);
        Counts(window, 3, 40); Assert.Equal(43, totalCalls); Assert.Equal(3, window.Record.ReadCount);
        Assert.Equal(3, samples.Count); Assert.Equal(3, decisions.Count); Assert.Equal("completed", window.Record.Outcome);
        Assert.Null(NavigationBaselineTask.FinalRejection(samples));
        Assert.Equal(3, samples.Select(sample => sample.SourceTimestamp100ns).Distinct().Count());
    }
}
