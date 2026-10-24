using System.Diagnostics;
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
    private static GameCaptureCallTiming Timing(double durationMs, string outcome = "frame")
    {
        var timing = new GameCaptureCallTiming();
        var start = timing.StartedAtTicks;
        long At(double ms) => start + (long)(ms * Stopwatch.Frequency / 1000);
        timing.CompletedAtTicks = At(durationMs);
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
        Assert.Equal(rejected, poll.Source);
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

    /// <summary>Maximum declared row counts serialize through the real envelope, with full timings and a terminal error retained.</summary>
    [Fact]
    public void FullCapacityJournalFitsTheExplicitPostReleaseFileBound()
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
            var sample = new NavigationBaselineSample(-867.68359375, 2281.37890625, 47.123456789, capturedAt,
                Epoch, source.SourceTimestamp100ns, source.AcquiredAtStopwatchTicks, 0.996785123456789, 0.987654321,
                "City_102", new("normal", AgentMotionEvidence.MethodName, false, false, 0.987654321), 37.504612345,
                47.123456789, 9.8078123456, 0.123456789, 0.0123456789, new(at, at + 10.123456, at + 20.123456, at + 40.123456));
            observations[i] = new("moving", sample, new("renew_w", at + 40.123456, at + 41.123456, at + 140.123456, 41.123456,
                GrantMs: 100, SourceAnchorAtMs: at, SourceCapAtMs: at + 250, FirstForwardAttempt: false));
            attempts[i] = new(at) { EndedAtMs = at + 43.123456, Stage = "completed", CaptureStartedAtMs = at + 10.123456,
                CaptureReturnedAtMs = at + 20.123456, RecognitionStartedAtMs = at + 21.123456,
                WorldCompletedAtMs = at + 24.123456, MotionCompletedAtMs = at + 25.123456,
                CropCompletedAtMs = at + 26.123456, PreprocessingCompletedAtMs = at + 32.123456,
                RecognitionCompletedAtMs = at + 40.123456, LastReturnedSource = source, CaptureCount = 4,
                DuplicateCount = 2, BarrierCount = 3 };
            waits[i] = new(at - 50.123456, at + 0.123456, at + 0.023456, at + 0.234567, null);
            for (var j = 0; j < 4; j++)
            {
                var poll = NativeNavigationBaselineOperations.BeginCapturePoll(polls, i, at - 10.123456 + j);
                poll.CaptureReturnedAtMs = at + 0.123456; poll.EndedAtMs = at + 5.234567;
                poll.Classify(source, source, null, at - 50.123456, 60, at + 0.123456);
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
            polls[i].RetainTiming(Timing(80), false, ref retainedTimings);
        }
        polls[63].CaptureTimingSupported = true;
        polls[63].RetainTiming(Timing(80), false, ref retainedTimings); // Explicitly omitted optional detail.
        polls[^1].CaptureTimingSupported = true;
        polls[^1].RetainTiming(Timing(80, "threw"), true, ref retainedTimings);
        var journal = new NavigationBaselineJournal
        {
            RunId = "f2fcdd4e43b14eeab9500e1fae5e4a63", GameProcessId = int.MaxValue, WindowsSessionId = 3,
            WorkflowResult = new() { TimingContract = NavigationBaselineTiming.V2, Phase = "moving", Error = "capture_diagnostics_capacity_exceeded",
                InitialSample = observations[0].Sample, ObservationCount = observations.Length,
                VerificationSamples = observations.TakeLast(3).Select(item => item.Sample).ToArray(), ElapsedMs = 30000.123456 },
            Observations = observations, ObservationAttempts = attempts, ScheduleWaits = waits,
            CapturePolls = polls, InputTransitions = transitions,
            InitialImage = new(new string('p', 1024), new string('A', 64), observations[0].Sample.Source),
            FinalImage = new(new string('p', 1024), new string('B', 64), observations[^1].Sample.Source)
        };
        var bytes = journal.Serialize();
        output.WriteLine($"Full row-cap journal: {bytes.Length:N0} bytes; file limit: {NativeNavigationBaselineOperations.MaximumJournalBytes:N0}.");
        Assert.InRange(bytes.Length, 1, NativeNavigationBaselineOperations.MaximumJournalBytes);
        using var parsed = JsonDocument.Parse(bytes);
        Assert.Equal(2, parsed.RootElement.GetProperty("diagnosticSchemaVersion").GetInt32());
        Assert.Equal("v2", parsed.RootElement.GetProperty("timingContract").GetString());
        Assert.Equal("native-fixed-leg-feedback-v2", parsed.RootElement.GetProperty("controllerMethod").GetString());
        Assert.Equal(1, parsed.RootElement.GetProperty("captureTimingSchemaVersion").GetInt32());
        Assert.Equal(64, parsed.RootElement.GetProperty("retainedCaptureTimings").GetInt32());
        Assert.Equal(1, parsed.RootElement.GetProperty("omittedCaptureTimings").GetInt32());
        Assert.False(parsed.RootElement.GetProperty("completeCaptureTimingTrace").GetBoolean());
        Assert.Equal(4096, parsed.RootElement.GetProperty("capturePolls").GetArrayLength());
        Assert.Equal(1024, parsed.RootElement.GetProperty("observationAttempts").GetArrayLength());
        Assert.Equal(failure, parsed.RootElement.GetProperty("capturePolls")[4095].GetProperty("error").GetString());
        Assert.False(parsed.RootElement.GetProperty("evidenceComplete").GetBoolean());
        Assert.False(parsed.RootElement.GetProperty("trainingEligible").GetBoolean());
    }
}
