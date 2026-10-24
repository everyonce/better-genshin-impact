using System.Diagnostics;
using BetterGenshinImpact.Core.Capture;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using Xunit;
using Xunit.Abstractions;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Pure source/wait evidence and actual journal-capacity checks; no native capture, game, GPU or input.</summary>
public sealed class NavigationBaselineDiagnosticsTests(ITestOutputHelper output)
{
    /// <summary>One fixed synthetic source generation shared by these monotonic-clock examples.</summary>
    private static readonly Guid Epoch = Guid.Parse("201e1af5-55cf-43d3-a131-13813a939594");
    /// <summary>Create raw/acquisition clocks independently, including the observed RDP future-label case.</summary>
    private static GameCaptureSourceInfo Source(double reported, double acquired) =>
        new(Epoch, (long)(reported * 10_000), (long)(acquired * Stopwatch.Frequency / 1000));

    /// <summary>Fully populated invocation-local stages without sleeping, GPU calls or any actual capture.</summary>
    private static GameCaptureCallTiming Timing(double durationMs, string outcome = "frame", bool polling = false)
    {
        var timing = new GameCaptureCallTiming();
        var start = timing.StartedAtTicks;
        long At(double ms) => start + (long)(ms * Stopwatch.Frequency / 1000);
        timing.CompletedAtTicks = At(durationMs);
        timing.CaptureGateContended = true;
        timing.CaptureGateProbeStartedAtTicks = At(0.01); timing.CaptureGateProbeCompletedAtTicks = At(0.02);
        timing.GcBefore = new GameCaptureGcSnapshot { ReadStartedAtTicks = At(0.001), ReadCompletedAtTicks = At(0.002),
            TotalPauseDuration100ns = 123456789, Gen0Collections = 10000, Gen1Collections = 2000, Gen2Collections = 500 };
        timing.GcAfter = new GameCaptureGcSnapshot { ReadStartedAtTicks = At(durationMs - 0.002), ReadCompletedAtTicks = At(durationMs - 0.001),
            TotalPauseDuration100ns = 124456789, Gen0Collections = 10001, Gen1Collections = 2001, Gen2Collections = 501 };
        timing.CaptureGateAcquiredAtTicks = At(1); timing.StateLockAcquiredAtTicks = At(2);
        timing.PoolStartedAtTicks = At(3); timing.PoolCompletedAtTicks = At(4);
        timing.RenderStartedAtTicks = At(5); timing.RenderCompletedAtTicks = At(6);
        timing.SubmitStartedAtTicks = At(7); timing.SubmitCompletedAtTicks = At(8);
        timing.ReadbackMapStartedAtTicks = At(9); timing.ReadbackMapCompletedAtTicks = At(10);
        timing.CpuCopyStartedAtTicks = At(11); timing.CpuCopyCompletedAtTicks = At(12);
        timing.LastStage = "cpu_copy"; timing.Outcome = outcome; timing.PoolResult = "acquired";
        timing.CacheHit = false; timing.Recreated = true; timing.CpuConvert = false; timing.DrawWrite = true;
        timing.AcquiredSource = Source(116491375, 116491357.7388);
        timing.ReturnedSource = outcome == "frame" ? timing.AcquiredSource : null;
        if (polling)
        {
            timing.ReadbackMode = "poll_single_v1"; timing.ReadbackOutcome = "frame_ready";
            timing.ReadbackMapResult = "ready";
            timing.PolledReadback = new(long.MaxValue - 1, timing.AcquiredSource!, start - 1, 1920, 1080,
                new Vanara.PInvoke.RECT(8, 31, 1928, 1111));
            timing.PendingReadback = new(long.MaxValue, Source(116491395, 116491387.7388), start + 1, 1920, 1080,
                new Vanara.PInvoke.RECT(8, 31, 1928, 1111));
            timing.FlushStartedAtTicks = At(15); timing.FlushCompletedAtTicks = At(16);
        }
        if (outcome != "frame") { timing.ExceptionType = new string('e', 96); timing.FailureStage = "readback_map"; }
        return timing;
    }

    /// <summary>Exact50ms boundary and all null/failed calls are eligible; ordinary fast successes retain no stages.</summary>
    [Theory]
    [InlineData(49, "frame", false, false)]
    [InlineData(50, "frame", false, true)]
    [InlineData(80, "frame", false, true)]
    [InlineData(1, "null", true, true)]
    [InlineData(1, "threw", true, true)]
    [InlineData(1, "frame", true, true)]
    public void RetainOnlySelectedSlowOrTerminalDetail(double duration, string outcome, bool terminal, bool expected)
    {
        var poll = new NavigationBaselineCapturePoll(0, 1000) { CaptureTimingSupported = true };
        var timing = Timing(duration, outcome); var count = 0;
        poll.RetainTiming(timing, terminal, ref count);
        Assert.Equal(expected ? 1 : 0, count); Assert.Equal(expected, poll.CaptureTiming is not null);
        Assert.False(poll.CaptureTimingOmitted);
        if (expected) Assert.Same(timing, poll.CaptureTiming);
    }

    /// <summary>Optional overflow never consumes the reserved terminal slot or erases the parent source row.</summary>
    [Fact]
    public void OptionalDetailReservesTerminalSlotAndMarksEveryOmission()
    {
        var polls = new List<NavigationBaselineCapturePoll>(); var count = 0;
        for (var i = 0; i < 67; i++)
        {
            var poll = NativeNavigationBaselineOperations.BeginCapturePoll(polls, i / 4, 1000 + i);
            poll.Source = Source(1000 + i, 999 + i);
            poll.RetainTiming(Timing(60), false, ref count);
        }
        Assert.Equal(63, count); Assert.Equal(4, polls.Count(poll => poll.CaptureTimingOmitted));
        Assert.All(polls, poll => Assert.NotNull(poll.Source));
        var terminal = NativeNavigationBaselineOperations.BeginCapturePoll(polls, 17, 1100);
        terminal.RetainTiming(Timing(1, "threw"), true, ref count);
        Assert.Equal(64, count); Assert.NotNull(terminal.CaptureTiming); Assert.False(terminal.CaptureTimingOmitted);
        var overflow = NativeNavigationBaselineOperations.BeginCapturePoll(polls, 18, 1200);
        overflow.RetainTiming(Timing(1, "null"), true, ref count);
        Assert.Equal(64, count); Assert.True(overflow.CaptureTimingOmitted); Assert.Null(overflow.CaptureTiming);
    }

    /// <summary>The final successful read is kept when its following input gate fails, without relabelling that capture as failed.</summary>
    [Theory]
    [InlineData(9.7511, false)]
    [InlineData(80, true)]
    public void CompletedReadTracePromotesAfterFollowingInputGateFault(double duration, bool initiallyOmitted)
    {
        var count = 63;
        var last = new NavigationBaselineCapturePoll(31, 1000) { CaptureTimingSupported = true, EndedAtMs = 1010 };
        var timing = Timing(duration);
        last.RetainTiming(timing, false, ref count);
        Assert.Null(last.CaptureTiming); Assert.Equal(initiallyOmitted, last.CaptureTimingOmitted);
        // Publication follows input closure for forward_lease_expired; the completed poll has no capture/admission error.
        last.RetainTiming(timing, true, ref count);
        Assert.Equal(64, count); Assert.Same(timing, last.CaptureTiming);
        Assert.Equal("frame", last.CaptureTiming!.Outcome); Assert.Null(last.Error);
        Assert.False(last.CaptureTimingOmitted);
        last.RetainTiming(timing, true, ref count);
        Assert.Equal(64, count); Assert.False(last.CaptureTimingOmitted);
    }

    /// <summary>An already-retained slow final call is not counted twice by terminal promotion.</summary>
    [Fact]
    public void FinalPromotionDoesNotDoubleCountRetainedInvocation()
    {
        var count = 0; var timing = Timing(80); var poll = new NavigationBaselineCapturePoll(0, 1000);
        poll.RetainTiming(timing, false, ref count);
        poll.RetainTiming(timing, true, ref count);
        Assert.Equal(1, count); Assert.Same(timing, poll.CaptureTiming);
    }

    /// <summary>The actual out-on-throw contract survives a caller finally without replacing the original exception.</summary>
    [Fact]
    public void OutTimingSurvivesOriginalExceptionAndFinallyRetention()
    {
        GameCaptureCallTiming? timing = null; var count = 0;
        var original = new InvalidOperationException("synthetic_capture_failure");
        var poll = new NavigationBaselineCapturePoll(0, 1000) { CaptureTimingSupported = true };
        var failure = Assert.Throws<InvalidOperationException>(() =>
        {
            try { GameCaptureCallTiming.Run(_ => throw original, out timing); }
            finally { poll.RetainTiming(timing, true, ref count); }
        });
        Assert.Same(original, failure); Assert.Same(timing, poll.CaptureTiming); Assert.Equal(1, count);
        Assert.Equal("threw", poll.CaptureTiming!.Outcome);
        Assert.True(poll.CaptureTiming.CompletedAtTicks >= poll.CaptureTiming.StartedAtTicks);
    }

    /// <summary>A repeated rejected frame was invisible to the old duplicate count; the new poll identity makes it explicit.</summary>
    [Fact]
    public void RejectedCacheIsDistinctFromLastAcceptedButRepeatsPreviousPoll()
    {
        var accepted = Source(1000, 990);
        var rejected = Source(1080, 1055);
        var poll = new NavigationBaselineCapturePoll(1, 1065);
        poll.Classify(rejected, rejected, accepted, 1000, 60, 1070);
        Assert.True(poll.RepeatsPreviousPoll); Assert.False(poll.DuplicateOfAccepted);
        Assert.Equal("response_barrier", poll.Result);
        Assert.Equal(20, poll.ReportedBarrierMarginMs.Value, 6);
        Assert.Equal(-5, poll.AcquisitionBarrierMarginMs.Value, 6);
        Assert.Equal(15, poll.SourceAgeMs.Value, 6);
        Assert.Equal(rejected, poll.Source?.WgcSource);
    }

    /// <summary>Both source clocks remain independent and exact at the boundary; diagnostics do not round a rejected clock up.</summary>
    [Theory]
    [InlineData(59, 60, "response_barrier")]
    [InlineData(60, 59, "response_barrier")]
    [InlineData(59, 59, "response_barrier")]
    [InlineData(60, 60, "admitted")]
    public void ReportExactlyWhichResponseClockIsEarly(double raw, double acquisition, string expected)
    {
        var source = Source(1000 + raw, 1000 + acquisition);
        var poll = new NavigationBaselineCapturePoll(0, 1070);
        poll.Classify(source, null, null, 1000, 60, 1070);
        Assert.Equal(expected, poll.Result);
        Assert.Equal(raw - 60, poll.ReportedBarrierMarginMs.Value, 6);
        Assert.Equal(acquisition - 60, poll.AcquisitionBarrierMarginMs.Value, 6);
        Assert.Equal(expected == "admitted", NavigationBaselineTask.AfterBarrier(source, 1000, 60));
    }

    /// <summary>Last-accepted duplicate authority and no-barrier initial reads retain their previous semantics.</summary>
    [Fact]
    public void DuplicateAuthorityAndInitialReadRemainSeparate()
    {
        var source = Source(1060, 1060);
        var duplicate = new NavigationBaselineCapturePoll(1, 1070);
        duplicate.Classify(source, null, source, 1000, 60, 1070);
        Assert.True(duplicate.DuplicateOfAccepted); Assert.False(duplicate.RepeatsPreviousPoll);
        Assert.Equal("duplicate", duplicate.Result);
        var initial = new NavigationBaselineCapturePoll(0, 1070);
        initial.Classify(source, null, null, 0, 0, 1070);
        Assert.Equal("admitted", initial.Result);
        Assert.Null(initial.ReportedBarrierMarginMs); Assert.Null(initial.AcquisitionBarrierMarginMs);
    }

    /// <summary>Poll admission stops before another capture could occur and retains every previously admitted row.</summary>
    [Fact]
    public void PollCapacityIsExplicitAndIncomplete()
    {
        var polls = new List<NavigationBaselineCapturePoll>();
        for (var i = 0; i < NativeNavigationBaselineOperations.MaximumCapturePolls; i++)
            NativeNavigationBaselineOperations.BeginCapturePoll(polls, i / 4, 1000 + i);
        var first = polls[0]; var last = polls[^1];
        var error = Assert.Throws<InvalidOperationException>(() =>
            NativeNavigationBaselineOperations.BeginCapturePoll(polls, 1023, 10000));
        Assert.Equal("capture_diagnostics_capacity_exceeded", error.Message);
        Assert.Equal(NativeNavigationBaselineOperations.MaximumCapturePolls, polls.Count);
        Assert.Same(first, polls[0]); Assert.Same(last, polls[^1]);
        Assert.False(NativeNavigationBaselineOperations.EvidenceIsComplete(new() { Error = error.Message }));
        Assert.Equal(1024, NavigationBaselineTask.MaximumObservations);
    }

    /// <summary>A fast Pending is expected unavailability; slow, failed and final calls still retain the bounded trace.</summary>
    [Theory]
    [InlineData(1, false, false)] [InlineData(50, false, true)] [InlineData(1, true, true)]
    public void ExpectedPendingTraceSelection(double duration, bool terminal, bool retained)
    {
        var poll = new NavigationBaselineCapturePoll(0, 1000) { CaptureTimingSupported = true };
        var timing = Timing(duration, polling: true); timing.Outcome = "null"; timing.ReadbackOutcome = "readback_pending";
        var count = 0; poll.RetainTiming(timing, terminal, ref count, readbackPending: true);
        Assert.Equal(retained, poll.CaptureTiming is not null); Assert.Equal(retained ? 1 : 0, count);
    }

    /// <summary>Existing window checks stop a delayed host read before any capture reservation or poll charge.</summary>
    [Theory]
    [InlineData("initial", "initial_readiness_deadline_exceeded")]
    [InlineData("final", "final_verification_deadline_exceeded")]
    [InlineData("recovery", "recovery_deadline_exceeded")]
    public async Task HostResponseWaitPreservesWindowDeadlinesAndZeroCaptureAccounting(string window, string expected)
    {
        double now = 1000; var captures = 0;
        var host = new GameCaptureHostSnapshotInfo(Epoch, 1, Stopwatch.Frequency, Stopwatch.Frequency, Stopwatch.Frequency);
        var source = new CaptureSourceEvidence(host);
        var initial = new NavigationBaselineInitialReadiness(() => now, 1080, 0, 0, NavigationBaselineCapturePolicy.TaskOwnedTimer);
        var final = new NavigationBaselineFinalVerification(() => now, 1000, 1080, source, 0, 0);
        var recoveryRecord = new NavigationBaselineRecoveryAttempt
        {
            Pause = new(1, NavigationBaselineRecoveryCause.LeaseExpired, 1000, 1000, null),
            TriggerCause = NavigationBaselineRecoveryCause.LeaseExpired, TriggerStage = "between_observations", DeadlineAtMs = 1080
        };
        var recovery = new NavigationBaselineRecoveryReadbackBudget(() => now, recoveryRecord, source, 1920, 1080);
        var attempts = new List<NavigationBaselineObservationAttempt>(); var polls = new List<NavigationBaselineCapturePoll>();
        void Check(CancellationToken token)
        {
            if (window == "initial") initial.Check(token);
            else if (window == "final") final.Check(token);
            else recovery.Check(token);
        }
        var error = await Record.ExceptionAsync(() => NativeNavigationBaselineOperations.RecordObservationAsync(
            attempts, () => now, () => null, async attempt =>
            {
                Check(default);
                await NativeNavigationBaselineOperations.WaitForHostResponseAsync(1000, 80, attempt, () => now,
                    (deadline, _) => { now = deadline; return Task.CompletedTask; }, Check, default);
                captures++; NativeNavigationBaselineOperations.BeginCapturePoll(polls, 0, now);
                throw new InvalidOperationException("capture_should_not_start");
            }));
        Assert.NotNull(error); Assert.Equal(expected, error.Message);
        var read = Assert.Single(attempts);
        Assert.Equal("waiting_host_response", read.Stage); Assert.Equal(expected, read.Error);
        Assert.Equal(1000, read.StartedAtMs); Assert.Equal(1080, read.EndedAtMs);
        Assert.Null(read.CaptureStartedAtMs); Assert.Equal(0, captures); Assert.Equal(0, read.CaptureCount); Assert.Empty(polls);
        Assert.Equal(0, initial.Record.PollCount); Assert.Equal(0, initial.Record.CaptureCount); Assert.Equal(0, initial.Record.PendingPollCount);
        Assert.Equal(0, final.Record.PollCount); Assert.Equal(0, final.Record.CaptureCount); Assert.Equal(0, final.Record.PendingPollCount);
        Assert.Equal(0, recoveryRecord.PollCount); Assert.Equal(0, recoveryRecord.CaptureCount); Assert.Equal(0, recoveryRecord.PendingPollCount);
        Assert.False(recoveryRecord.ReservationOutstanding);
        Assert.Equal(1080, initial.Record.DeadlineAtMs); Assert.Equal(1080, final.Record.DeadlineAtMs); Assert.Equal(1080, recoveryRecord.DeadlineAtMs);
    }

    /// <summary>A failed pre-acquisition wait retains the read and any earlier poll without inventing another capture or refund.</summary>
    [Theory]
    [InlineData(false, false)] [InlineData(false, true)] [InlineData(true, false)] [InlineData(true, true)]
    public async Task FailedHostResponseWaitRetainsOnlyRealReadAndPriorPoll(bool earlierPoll, bool cancellation)
    {
        double now = 1000;
        var attempts = new List<NavigationBaselineObservationAttempt>(); var polls = new List<NavigationBaselineCapturePoll>();
        using var stop = new CancellationTokenSource();
        var error = await Record.ExceptionAsync(() => NativeNavigationBaselineOperations.RecordObservationAsync(
            attempts, () => now, () => null, async attempt =>
            {
                if (earlierPoll)
                {
                    var earlier = NativeNavigationBaselineOperations.BeginCapturePoll(polls, 0, now);
                    attempt.CaptureStartedAtMs = now; attempt.CaptureCount++;
                    now++; earlier.CaptureReturnedAtMs = now; earlier.EndedAtMs = now; attempt.CaptureReturnedAtMs = now;
                }
                await NativeNavigationBaselineOperations.WaitForHostResponseAsync(1000, 80, attempt, () => now,
                    (_, token) =>
                    {
                        now = 1040;
                        if (cancellation) { stop.Cancel(); token.ThrowIfCancellationRequested(); }
                        throw new InvalidOperationException("game_target_lost");
                    }, _ => throw new InvalidOperationException("unexpected_postwait_check"), stop.Token);
                NativeNavigationBaselineOperations.BeginCapturePoll(polls, 0, now);
                throw new InvalidOperationException("capture_should_not_start");
            }));
        if (cancellation) Assert.IsAssignableFrom<OperationCanceledException>(error);
        else Assert.Equal("game_target_lost", Assert.IsType<InvalidOperationException>(error).Message);
        var read = Assert.Single(attempts);
        Assert.Equal("waiting_host_response", read.Stage); Assert.NotNull(read.Error); Assert.Equal(1040, read.EndedAtMs);
        Assert.Equal(earlierPoll ? 1 : 0, read.CaptureCount); Assert.Equal(earlierPoll ? 1 : 0, polls.Count);
        Assert.Null(read.RecognitionStartedAtMs); Assert.Null(read.LastReturnedSource); Assert.Null(read.LeaseFault);
        if (earlierPoll)
        {
            Assert.Equal(1000, read.CaptureStartedAtMs); Assert.Equal(1001, read.CaptureReturnedAtMs);
            Assert.Equal(1000, polls[0].CaptureStartedAtMs); Assert.Equal(1001, polls[0].EndedAtMs);
        }
        else { Assert.Null(read.CaptureStartedAtMs); Assert.Null(read.CaptureReturnedAtMs); }
    }

    /// <summary>Successful waiting consumes read time while the capture request and snapshot retain their actual later times.</summary>
    [Fact]
    public async Task SuccessfulHostWaitRecordsActualPostWaitRequest()
    {
        double now = 1000;
        var attempts = new List<NavigationBaselineObservationAttempt>(); var polls = new List<NavigationBaselineCapturePoll>();
        var result = await NativeNavigationBaselineOperations.RecordObservationAsync(attempts, () => now, () => null, async attempt =>
        {
            await NativeNavigationBaselineOperations.WaitForHostResponseAsync(1000, 80, attempt, () => now,
                (deadline, _) => { now = deadline; return Task.CompletedTask; }, _ => Assert.Equal(1080, now), default);
            var requested = now;
            var poll = NativeNavigationBaselineOperations.BeginCapturePoll(polls, 0, requested);
            attempt.Stage = "capturing"; attempt.CaptureCount++; attempt.CaptureStartedAtMs = requested;
            now += 10;
            poll.CaptureReturnedAtMs = now; attempt.CaptureReturnedAtMs = now;
            var host = new GameCaptureHostSnapshotInfo(Epoch, 2, (long)(requested * Stopwatch.Frequency / 1000),
                (long)(now * Stopwatch.Frequency / 1000), Stopwatch.Frequency);
            poll.Source = new CaptureSourceEvidence(host); attempt.LastReturnedSource = poll.Source;
            attempt.RecognitionStartedAtMs = now; now += 10; attempt.RecognitionCompletedAtMs = now; poll.EndedAtMs = now;
            return new(0, 0, 0, DateTimeOffset.UnixEpoch, Epoch, null, null, 1, 1, "City_102",
                new("normal", "native_key_tip_templates_v1", false, false, 1), 20, 0, 0, 0, 0,
                new(attempt.StartedAtMs, requested, requested + 10, now)) { HostSnapshot = host };
        });
        var read = Assert.Single(attempts); var capture = Assert.Single(polls);
        Assert.Equal(1000, read.StartedAtMs); Assert.Equal(1080, read.CaptureStartedAtMs); Assert.Equal(1100, read.EndedAtMs);
        Assert.Equal(1080, capture.CaptureStartedAtMs); Assert.Equal(1, read.CaptureCount); Assert.Null(read.Error);
        Assert.Equal(1000, result.Timing.ObservationStartedAtMs); Assert.Equal(1080, result.Timing.CaptureRequestedAtMs);
        Assert.Equal(1080, result.Source.AnchorAtMs); Assert.Equal(20, result.Source.AgeAt(now), 6);
    }

    /// <summary>Maximum declared row counts serialize through the real envelope, with full timings and a terminal error retained.</summary>
    [Theory]
    [InlineData("v2", false, false, false, null)]
    [InlineData("v4", false, false, false, null)]
    [InlineData("v4", true, false, false, null)]
    [InlineData("v4", true, true, false, null)]
    [InlineData("v4", false, false, true, null)]
    [InlineData("v4", false, false, true, NavigationBaselineRouteProfile.CourtyardReturnId)]
    [InlineData("v4", false, false, true, NavigationBaselineRouteProfile.CourtyardForwardId)]
    public void FullCapacityJournalFitsTheExplicitPostReleaseFileBound(string contract, bool polling, bool twoLegs, bool host, string? hostContinuation)
    {
        const double origin = 116491268.704253;
        var capturedAt = new DateTimeOffset(2026, 10, 23, 12, 34, 56, TimeSpan.Zero).AddTicks(1234567);
        var observations = new NavigationBaselineDecision[NavigationBaselineTask.MaximumObservations];
        var attempts = new NavigationBaselineObservationAttempt[observations.Length];
        var waits = new NavigationBaselineScheduleWait[observations.Length];
        var polls = new List<NavigationBaselineCapturePoll>();
        for (var i = 0; i < observations.Length; i++)
        {
            var at = origin + i * 50.123456;
            var source = Source(at + 20.123456, at);
            // The additional host representation is size-only, like the legacy maximal trajectory below.
            var snapshot = host ? new GameCaptureHostSnapshotInfo(Epoch, i + 1, source.AcquiredAtStopwatchTicks,
                source.AcquiredAtStopwatchTicks + 1, Stopwatch.Frequency) : null;
            CaptureSourceEvidence sourceEvidence = snapshot is null ? new(source) : new(snapshot);
            var sample = new NavigationBaselineSample(-867.68359375, 2281.37890625, 47.123456789, capturedAt,
                Epoch, host ? null : source.SourceTimestamp100ns, host ? null : source.AcquiredAtStopwatchTicks, 0.996785123456789, 0.987654321,
                "City_102", new("normal", AgentMotionEvidence.MethodName, false, false, 0.987654321), 37.504612345,
                47.123456789, 9.8078123456, 0.123456789, 0.0123456789, new(at, at + 10.123456, at + 20.123456, at + 40.123456)) { HostSnapshot = snapshot, LegIndex = twoLegs ? (i < 512 ? 1 : 2) : hostContinuation is null ? null : 1 };
            observations[i] = new("moving", sample, new("renew_w", at + 40.123456, at + 41.123456, at + 140.123456, 41.123456,
                GrantMs: 100, SourceAnchorAtMs: at, SourceCapAtMs: at + 250, FirstForwardAttempt: false));
            attempts[i] = new(at) { EndedAtMs = at + 43.123456, Stage = "completed", CaptureStartedAtMs = at + 10.123456,
                CaptureReturnedAtMs = at + 20.123456, RecognitionStartedAtMs = at + 21.123456,
                ChatCompletedAtMs = at + 22.123456, ChatState = "Closed",
                WorldCompletedAtMs = at + 24.123456, MotionCompletedAtMs = at + 25.123456,
                CropCompletedAtMs = at + 26.123456, PreprocessingCompletedAtMs = at + 32.123456,
                RecognitionCompletedAtMs = at + 40.123456, LastReturnedSource = sourceEvidence, CaptureCount = 4,
                DuplicateCount = 2, BarrierCount = 3 };
            waits[i] = new(at - 50.123456, at + 0.123456, at + 0.023456, at + 0.234567, null);
            for (var j = 0; j < 4; j++)
            {
                var poll = NativeNavigationBaselineOperations.BeginCapturePoll(polls, i, at - 10.123456 + j);
                poll.CaptureReturnedAtMs = at + 0.123456; poll.EndedAtMs = at + 5.234567;
                if (polling && j < 3)
                {
                    poll.RecordReadback(new(GameCaptureAttemptOutcome.ReadbackPending, pending:
                        new(long.MaxValue - i, source, source.AcquiredAtStopwatchTicks + 1, 1920, 1080,
                            new Vanara.PInvoke.RECT(-8, -31, 1912, 1049))));
                }
                else
                {
                    poll.Classify(sourceEvidence, sourceEvidence, null, at - 50.123456, 60, at + 0.123456);
                    if (polling)
                    {
                        using var returned = new GameCaptureFrame(new OpenCvSharp.Mat(1, 1, OpenCvSharp.MatType.CV_8UC3));
                        poll.RecordReadback(new(GameCaptureAttemptOutcome.FrameReady, returned,
                            new(long.MaxValue - i, source, source.AcquiredAtStopwatchTicks + 1, 1920, 1080,
                                new Vanara.PInvoke.RECT(8, 31, 1928, 1111))));
                    }
                }
                poll.WaitStartedAtMs = at + 0.134567; poll.WaitRequestedDeadlineMs = at + 5.134567;
                poll.WaitExitedAtMs = at + 5.234567;
            }
        }
        // A real run terminates on its first read error; retain that maximal bounded failure text once, not in every prior row.
        var failure = new string('\u0001', 512);
        polls[^1].Error = failure;
        attempts[^1].Error = failure; attempts[^1].LeaseFault = "forward_lease_expired";
        var transitions = Enumerable.Range(0, NavigationBaselineInputLease.MaximumEvents)
            .Select(i => new NavigationBaselineInputEvent("w_up", origin + i, origin + i + 1.123456,
                origin + i + 100.123456, 37.504612345, Error: i == 63 ? failure : null)).ToArray();
        var retainedTimings = 0;
        for (var i = 0; i < 63; i++)
        {
            polls[i].CaptureTimingSupported = true;
            polls[i].RetainTiming(Timing(80, polling: polling), false, ref retainedTimings);
        }
        polls[63].CaptureTimingSupported = true;
        polls[63].RetainTiming(Timing(80, polling: polling), false, ref retainedTimings); // Explicitly omitted optional detail.
        polls[^1].CaptureTimingSupported = true;
        polls[^1].RetainTiming(Timing(80, "threw", polling), true, ref retainedTimings);
        NavigationBaselineWaypointRecord? waypoint = twoLegs ? new()
        {
            Release = new("w_up", origin + 12000, origin + 12001.123456, origin + 12100.123456),
            DeadlineAtMs = origin + 14001.123456, EndedAtMs = origin + 13999.123456,
            ObservationStart = 576, ObservationEnd = 608, PollStart = 2304, PollEnd = 2336,
            ReadCount = 32, CaptureCount = 32, SourceAgeDiscards = 28,
            Samples = observations.Skip(604).Take(3).Select(row => row.Sample).ToArray(), Anchor = observations[607].Sample,
            Outcome = "failed", Error = failure
        } : null;
        if (twoLegs)
            for (var i = 576; i < 608; i++)
            {
                attempts[i].WaypointDisposition = "source_age_discard";
                attempts[i].WaypointCheckStage = "admitting_waypoint_sample";
                attempts[i].WaypointCheckedAtMs = origin + i * 50.123456 + 123.456789;
                attempts[i].WaypointSourceAgeMs = 151.987654;
            }
        // Four maximal tickets exercise both independent counts without duplicating global poll rows.
        var recoveryPauses = contract == "v4" ? Enumerable.Range(1, 4).Select(i =>
            new NavigationBaselineRecoveryPause(i, NavigationBaselineRecoveryCause.SourceAge, origin + i * 1000,
                origin + i * 1000 + 1.123456, null)
            {
                BudgetKind = i <= 2 ? NavigationBaselineRecoveryBudgetKind.MovementRecovery
                    : NavigationBaselineRecoveryBudgetKind.StationarySourceReadiness,
                HeldForwardAtEntry = i <= 2, MovementRecoveriesUsed = Math.Min(i, 2),
                StationaryReadinessUsed = Math.Max(0, i - 2)
            }).ToArray() : [];
        var journal = new NavigationBaselineJournal
        {
            Waypoint = waypoint,
            ReadbackMode = host ? null : polling ? "poll_single_v1" : "blocking",
            RunId = "f2fcdd4e43b14eeab9500e1fae5e4a63", GameProcessId = int.MaxValue, WindowsSessionId = 3,
            WorkflowResult = new() { SourcePolicy = host ? DesktopCapturePolicy.HostAcquisitionV1 : null,
                ProfileId = hostContinuation ?? (twoLegs ? NavigationBaselineRouteProfile.TwoLegId : NavigationBaselineTask.ProfileId),
                Continuation = hostContinuation is null ? null : NavigationBaselineHostSourceTests.HostLink() with {
                    PredecessorProfileId = hostContinuation == NavigationBaselineRouteProfile.CourtyardForwardId
                        ? NavigationBaselineRouteProfile.CourtyardReturnId : NavigationBaselineRouteProfile.CourtyardForwardId },
                Waypoint = waypoint, Legs = twoLegs ? [new(1, 1, 2, origin, origin + 14000, 0, 512, "completed"),
                    new(2, 2, 3, origin + 14000, origin + 29999, 512, 1024, "failed")] : hostContinuation is null ? [] :
                    [new(1, hostContinuation == NavigationBaselineRouteProfile.CourtyardReturnId ? 2 : 1,
                        hostContinuation == NavigationBaselineRouteProfile.CourtyardReturnId ? 1 : 2, origin, origin + 29999, 0, 1024, "failed")], TimingContract = contract, CapturePolicy = NavigationBaselineCapturePolicy.TaskOwnedTimer,
                Phase = "moving", Error = "capture_diagnostics_capacity_exceeded",
                InitialSample = observations[0].Sample, ObservationCount = observations.Length,
                VerificationSamples = observations.TakeLast(3).Select(item => item.Sample).ToArray(), ElapsedMs = 30000.123456 },
            Observations = observations, ObservationAttempts = attempts, ScheduleWaits = waits,
            CapturePolls = polls, InputTransitions = transitions,
            RecoveryPauses = recoveryPauses,
            RecoveryAttempts = contract == "v4" ? Enumerable.Range(0, 4).Select(i => new NavigationBaselineRecoveryAttempt
            {
                Pause = recoveryPauses[i], TriggerCause = NavigationBaselineRecoveryCause.SourceAge, TriggerStage = "after_recognition",
                TriggerSource = observations[i].Sample.Source, DeadlineAtMs = origin + i * 1000 + 2000,
                ObservationStart = 108 + i * 108, ObservationEnd = 216 + i * 108,
                PollStart = 432 + i * 432, PollEnd = 864 + i * 432,
                PollCount = 432, CaptureCount = 32, PendingPollCount = 400, ReservationOutstanding = false,
                LastBudgetCheckAtMs = origin + i * 1000 + 1998.123456, SeenSource = observations[i].Sample.Source,
                EndedAtMs = origin + i * 1000 + 1999.123456, Outcome = "failed", Error = failure,
                ResumedSample = observations[i].Sample
            }).ToArray() : [],
            FinalVerificationWindow = contract == "v4" ? new()
            {
                ClosedAtMs = origin + 25000.123456, StartedAtMs = origin + 25000.234567,
                DeadlineAtMs = origin + 27000.123456, EndedAtMs = origin + 26999.123456,
                ObservationStart = 992, ObservationEnd = 1024, PollStart = 4096 - 432, PollEnd = 4096,
                ReadCount = 32, CaptureCount = 32, PollCount = 432, PendingPollCount = 400, SourceAgeDiscards = 29, Outcome = "failed", Error = failure
            } : null,
            InitialReadinessWindow = contract == "v4" ? new()
            {
                StartedAtMs = origin, OwnerDeadlineAtMs = origin + 30000, DeadlineAtMs = origin + 2000,
                EndedAtMs = origin + 1999.123456, ObservationStart = 0, ObservationEnd = 32, PollStart = 0, PollEnd = 432,
                ReadCount = 32, CaptureCount = 32, PollCount = 432, PendingPollCount = 400, SourceAgeDiscards = 31,
                Width = 1920, Height = 1080, SeenSource = observations[31].Sample.Source, AdmittedReadIndex = 31,
                Outcome = "completed"
            } : null,
            InitialImage = new(new string('p', 1024), new string('A', 64), observations[0].Sample.Source),
            FinalImage = new(new string('p', 1024), new string('B', 64), observations[^1].Sample.Source)
        };
        if (contract == "v4")
        {
            // Include the full additive initial-window representation without claiming this synthetic trajectory is valid.
            for (var i = 0; i < 432; i++) polls[i].InitialReadinessCaptureCharged = i >= 400;
            var initialStages = new[] { "after_capture", "after_recognition", "before_initial_retention", "after_initial_retention", "returning_initial_pose" };
            for (var i = 0; i < 32; i++)
                foreach (var stage in initialStages)
                    journal.InitialReadinessWindow!.SourceChecks.Add(new(i, i + 400,
                        origin + i * 5.123456, i == 31 ? 149.123456 : 151.987654,
                        i == 31 ? "fresh_source" : "source_age_discard", stage));
            Assert.Equal(NavigationBaselineInitialReadiness.MaximumSourceChecks, journal.InitialReadinessWindow!.SourceChecks.Count);
            // Four disjoint maximal recovery ranges retain all1,728 charge markers within4096 global rows.
            for (var i = 432; i < 2160; i++) polls[i].RecoveryCaptureCharged = (i - 432) % 432 >= 400;
            for (var i = 0; i < 128; i++)
            {
                // Four maximal age-only windows retain rejected read/poll rows without exceeding either global cap.
                polls[i].Error = "baseline_recovery_required: SourceAge; stage=after_recognition";
                attempts[i].Error = polls[i].Error;
            }
            // Maximum-count representation fixture: all432 final rows include the additive charge marker.
            // This bounds serialization size, not every possible string/numeric representation or a valid live trajectory.
            for (var i = polls.Count - 432; i < polls.Count; i++)
                polls[i].FinalVerificationCaptureCharged = i < polls.Count - 400;
            journal.FinalVerificationWindow!.AcceptedReadIndices.AddRange([992, 993, 1023]);
            for (var i = 992; i < 1024; i++)
            {
                attempts[i].FinalVerificationDisposition = i is 992 or 993 or 1023 ? "admitted" : "source_age_discard";
                attempts[i].FinalVerificationCheckStage = "admitting_final_sample";
                attempts[i].FinalVerificationCheckedAtMs = origin + i * 50.123456 + 123.456789;
                attempts[i].FinalVerificationSourceAgeMs = i is 992 or 993 or 1023 ? 149.123456 : 151.987654;
            }
        }
        var bytes = journal.Serialize();
        output.WriteLine($"Full row-cap journal: {bytes.Length:N0} bytes; file limit: {NativeNavigationBaselineOperations.MaximumJournalBytes:N0}.");
        if (twoLegs)
        {
            var compact = new BetterGenshinImpact.Service.ExternalControl.ExternalControlResponse
            { Status = new() { NavigationBaseline = new() { ProfileId = NavigationBaselineRouteProfile.TwoLegId } } };
            var compactBytes = BetterGenshinImpact.Service.ExternalControl.ExternalControlProtocol.SerializeResponse(compact);
            Assert.True(compactBytes.Length < 8192);
            var full = new BetterGenshinImpact.Service.ExternalControl.ExternalControlResponse
            { Status = new() { NavigationBaseline = new() { ProfileId = NavigationBaselineRouteProfile.TwoLegId, Result = journal.WorkflowResult } } };
            var fullBytes = BetterGenshinImpact.Service.ExternalControl.ExternalControlProtocol.SerializeResponse(full);
            output.WriteLine($"Two-leg wire responses: compact {compactBytes.Length:N0} bytes; dedicated result {fullBytes.Length:N0} bytes.");
            Assert.True(fullBytes.Length < 32768);
            // The deeper response must retain real checkpoint motion evidence, rather than silently omit it to fit.
            using var response = JsonDocument.Parse(fullBytes);
            var checkpointSamples = response.RootElement.GetProperty("status").GetProperty("navigationBaseline")
                .GetProperty("result").GetProperty("waypoint").GetProperty("samples");
            Assert.Equal(3, checkpointSamples.GetArrayLength());
            Assert.Equal("normal", checkpointSamples[0].GetProperty("motion").GetProperty("status").GetString());
        }
        if (hostContinuation is not null)
        {
            using var hostJson = JsonDocument.Parse(bytes);
            var continuation = hostJson.RootElement.GetProperty("workflowResult").GetProperty("continuation");
            Assert.Equal(2, continuation.GetProperty("version").GetInt32());
            Assert.Equal("host-acquisition-v1", continuation.GetProperty("predecessorFinalSource").GetProperty("kind").GetString());
            var raw = continuation.GetProperty("predecessorFinalSource").GetProperty("hostSnapshot");
            Assert.Equal(5, raw.EnumerateObject().Count()); Assert.True(raw.TryGetProperty("snapshotId", out _));
            Assert.False(raw.TryGetProperty("sourceTimestamp100ns", out _));
        }
        Assert.InRange(bytes.Length, 1, NativeNavigationBaselineOperations.MaximumJournalBytes);
        using var parsed = JsonDocument.Parse(bytes);
        if (polling)
        {
            // The bounded journal preserves original signed edges on Pending and Ready-refill metadata.
            var serializedPolls = parsed.RootElement.GetProperty("capturePolls");
            var pendingRect = serializedPolls[0].GetProperty("pendingReadback").GetProperty("captureRect");
            Assert.Equal(4, pendingRect.EnumerateObject().Count());
            Assert.Equal(-8, pendingRect.GetProperty("left").GetInt32());
            Assert.Equal(-31, pendingRect.GetProperty("top").GetInt32());
            Assert.Equal(1912, pendingRect.GetProperty("right").GetInt32());
            Assert.Equal(1049, pendingRect.GetProperty("bottom").GetInt32());
            var refillRect = serializedPolls[3].GetProperty("pendingReadback").GetProperty("captureRect");
            Assert.Equal(4, refillRect.EnumerateObject().Count());
            Assert.Equal(8, refillRect.GetProperty("left").GetInt32());
            Assert.Equal(31, refillRect.GetProperty("top").GetInt32());
            Assert.Equal(1928, refillRect.GetProperty("right").GetInt32());
            Assert.Equal(1111, refillRect.GetProperty("bottom").GetInt32());
        }
        Assert.Equal(2, parsed.RootElement.GetProperty("diagnosticSchemaVersion").GetInt32());
        Assert.Equal(contract, parsed.RootElement.GetProperty("timingContract").GetString());
        Assert.Equal(contract == "v4", parsed.RootElement.TryGetProperty("finalVerificationReadinessVersion", out var finalVersion));
        if (contract == "v4")
        {
            Assert.Equal(3, parsed.RootElement.GetProperty("recoverySchemaVersion").GetInt32());
            var recoveryRows = parsed.RootElement.GetProperty("capturePolls").EnumerateArray()
                .Where(row => row.TryGetProperty("recoveryCaptureCharged", out _)).ToArray();
            Assert.Equal(1728, recoveryRows.Length);
            Assert.Equal(128, recoveryRows.Count(row => row.GetProperty("recoveryCaptureCharged").GetBoolean()));
            Assert.Equal(2, parsed.RootElement.GetProperty("maximumMovementRecoveries").GetInt32());
            Assert.Equal(2, parsed.RootElement.GetProperty("maximumStationaryReadinessWindows").GetInt32());
            Assert.Equal(4, parsed.RootElement.GetProperty("maximumPauseWindows").GetInt32());
            Assert.Equal(2, parsed.RootElement.GetProperty("movementRecoveryCount").GetInt32());
            Assert.Equal(2, parsed.RootElement.GetProperty("stationaryReadinessCount").GetInt32());
            Assert.Equal(4, parsed.RootElement.GetProperty("recoveryPauses").GetArrayLength());
            Assert.Equal(4, parsed.RootElement.GetProperty("recoveryAttempts").GetArrayLength());
            foreach (var recovery in parsed.RootElement.GetProperty("recoveryAttempts").EnumerateArray())
            {
                Assert.Equal(432, recovery.GetProperty("pollCount").GetInt32());
                Assert.Equal(400, recovery.GetProperty("pendingPollCount").GetInt32());
                Assert.Equal(32, recovery.GetProperty("captureCount").GetInt32());
                Assert.Equal(5, recovery.GetProperty("pendingDelayMs").GetInt32());
                Assert.Equal(20, recovery.GetProperty("retryDelayMs").GetInt32());
            }
            Assert.Equal(2, finalVersion.GetInt32());
            var finalWindow = parsed.RootElement.GetProperty("finalVerificationWindow");
            Assert.Equal(32, finalWindow.GetProperty("readCount").GetInt32());
            Assert.Equal(432, finalWindow.GetProperty("pollCount").GetInt32());
            Assert.Equal(400, finalWindow.GetProperty("pendingPollCount").GetInt32());
            Assert.Equal(32, finalWindow.GetProperty("captureCount").GetInt32());
            var finalPolls = parsed.RootElement.GetProperty("capturePolls").EnumerateArray()
                .Where(row => row.TryGetProperty("finalVerificationCaptureCharged", out _)).ToArray();
            Assert.Equal(432, finalPolls.Length);
            Assert.Equal(32, finalPolls.Count(row => row.GetProperty("finalVerificationCaptureCharged").GetBoolean()));
            Assert.Equal(3, finalWindow.GetProperty("acceptedReadIndices").GetArrayLength());
            Assert.Equal("source_age_discard", parsed.RootElement.GetProperty("observationAttempts")[1022]
                .GetProperty("finalVerificationDisposition").GetString());
        }
        Assert.Equal("task_owned_timer", parsed.RootElement.GetProperty("capturePolicy").GetString());
        Assert.Equal($"native-fixed-leg-feedback-{contract}", parsed.RootElement.GetProperty("controllerMethod").GetString());
        Assert.Equal(1, parsed.RootElement.GetProperty("captureTimingSchemaVersion").GetInt32());
        Assert.Equal(64, parsed.RootElement.GetProperty("retainedCaptureTimings").GetInt32());
        Assert.Equal(1, parsed.RootElement.GetProperty("omittedCaptureTimings").GetInt32());
        Assert.False(parsed.RootElement.GetProperty("completeCaptureTimingTrace").GetBoolean());
        Assert.Equal("slow-or-failed-plus-final-invocation", parsed.RootElement.GetProperty("captureTimingSelection").GetString());
        Assert.Equal(4096, parsed.RootElement.GetProperty("capturePolls").GetArrayLength());
        Assert.Equal(1024, parsed.RootElement.GetProperty("observationAttempts").GetArrayLength());
        Assert.Equal(failure, parsed.RootElement.GetProperty("capturePolls")[4095].GetProperty("error").GetString());
        Assert.False(parsed.RootElement.GetProperty("evidenceComplete").GetBoolean());
        Assert.False(parsed.RootElement.GetProperty("trainingEligible").GetBoolean());
    }
}
