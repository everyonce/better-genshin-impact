using System.Diagnostics;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Production workflow boundaries use deterministic synthetic observations and no input/capture services.</summary>
public sealed class NavigationBaselineRecoveryWorkflowTests
{
    /// <summary>Valid same-frame route pose with independently increasing native clocks.</summary>
    private static NavigationBaselineSample Sample(double fraction, double now)
    {
        var x = NavigationBaselineTask.StartX + fraction * (NavigationBaselineTask.EndX - NavigationBaselineTask.StartX);
        var y = NavigationBaselineTask.StartY + fraction * (NavigationBaselineTask.EndY - NavigationBaselineTask.StartY);
        var geometry = NavigationBaselineTask.Geometry(x, y);
        return new(x, y, 47, DateTimeOffset.UnixEpoch, Guid.Parse("713e569b-05ac-4a78-aadf-8a29455fcd92"),
            (long)(now * 10000), (long)(now * Stopwatch.Frequency / 1000), 0.999, 0.8, "City_102",
            new("normal", AgentMotionEvidence.MethodName, false, false, 1), 10, 47,
            geometry.Distance, geometry.Projection, geometry.CrossTrack, new(now, now, now, now));
    }

    /// <summary>Recovery begins after anchor admission, releases before waiting, and never itself sends a movement step.</summary>
    [Fact]
    public async Task WorkflowResumesOnlyFromReturnedFreshPoseAndStillVerifiesAfterClose()
    {
        var ops = new Operations { InterruptRead = 1 };
        var result = await new NavigationBaselineTask(ops, "v4").RunAsync(_ => { }, default);
        Assert.True(result.Verified); Assert.Equal(1, ops.Recoveries); Assert.Equal(31000, ops.RecoveryDeadline);
        Assert.True(ops.EnabledAfterAnchor); Assert.True(ops.ReleasedBeforeRecoveryWait); Assert.Equal(2, ops.Downs);
        Assert.Equal(3, ops.FinalReadClosed.Count); Assert.All(ops.FinalReadClosed, value => Assert.True(value));
        Assert.DoesNotContain(ops.Decisions, row => row.Phase == "recovered");
        Assert.Equal(6, result.ObservationCount); Assert.Equal(result.ObservationCount, ops.Decisions.Length);
        Assert.Equal(ops.Decisions.Length, ops.Decisions.Select(row =>
            (row.Sample.SourceEpoch, row.Sample.SourceTimestamp100ns, row.Sample.AcquiredAtStopwatchTicks)).Distinct().Count());
        Assert.True(ops.PublishedAfterClose);
    }

    /// <summary>Observed hard failures remain the actual result, even when a simultaneous lease fault exists.</summary>
    [Theory]
    [InlineData("source_epoch_changed")]
    [InlineData("native_source_regressed")]
    [InlineData("native_frame_geometry_changed")]
    [InlineData("world_not_ready")]
    [InlineData("chat_open")]
    [InlineData("non_normal_motion")]
    [InlineData("route_corridor_exceeded")]
    public async Task HardFailureWinsThroughWorkflowAndPublication(string failure)
    {
        var ops = new Operations { HardFailure = failure, FaultAtRead = "forward_lease_expired" };
        var result = await new NavigationBaselineTask(ops, "v4").RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal(failure, result.Error); Assert.Equal(0, ops.Recoveries);
        Assert.True(ops.PublishedAfterClose); Assert.Equal(failure, ops.PublishedResult!.Error);
    }

    /// <summary>Initial/final observations cannot use the travel-only catch or consume a recovery ticket.</summary>
    [Theory]
    [InlineData(0)]
    [InlineData(3)]
    public async Task InitialAndFinalReadInterruptionsRemainStrict(int interruptRead)
    {
        var ops = new Operations { InterruptRead = interruptRead };
        var result = await new NavigationBaselineTask(ops, "v4").RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal(0, ops.Recoveries);
        Assert.StartsWith("baseline_recovery_required:", result.Error);
        Assert.Equal(interruptRead != 0, ops.EnabledAfterAnchor);
        Assert.True(ops.PublishedAfterClose);
    }

    /// <summary>Recovery errors close the task; long native work cannot reset the original30-second budget.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task FailedOrOverdueRecoveryDoesNotDispatchAgain(bool overrun)
    {
        var ops = new Operations { InterruptRead = 1, RecoveryFailure = overrun ? null : "recovery_poll_limit_exceeded",
            RecoveryWorkMs = overrun ? 30001 : 90 };
        var result = await new NavigationBaselineTask(ops, "v4").RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal(1, ops.Downs); Assert.Equal(1, ops.Recoveries);
        Assert.Equal(overrun ? "baseline_deadline_exceeded" : "recovery_poll_limit_exceeded", result.Error);
        Assert.True(ops.PublishedAfterClose);
    }

    /// <summary>A window-only cancellation retains its specific terminal code through the real workflow catch.</summary>
    [Fact]
    public async Task WrappedRecoveryDeadlineSurvivesFinalResultAndJournalPublication()
    {
        var ops = new Operations { InterruptRead = 1,
            RecoveryException = new NavigationBaselineRecoveryTimeoutException(new OperationCanceledException("inner cancellation")) };
        var result = await new NavigationBaselineTask(ops, "v4").RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal("recovery_deadline_exceeded", result.Error);
        Assert.Equal(result.Error, ops.PublishedResult!.Error); Assert.Equal(1, ops.Downs);
    }

    /// <summary>Positive age alone is recoverable; known hard same-frame predicates remain distinguishable.</summary>
    [Theory]
    [InlineData("age", null)]
    [InlineData("nonfinite", "invalid_source_age")]
    [InlineData("motion", "non_normal_motion")]
    [InlineData("layer", "wrong_layer")]
    [InlineData("corridor", "route_corridor_exceeded")]
    public void HardPoseClassificationDoesNotHideBehindAge(string mutation, string? expected)
    {
        var sample = Sample(0.4, 1000) with { SourceAgeMs = 151 };
        sample = mutation switch { "nonfinite" => sample with { SourceAgeMs = double.NaN },
            "motion" => sample with { Motion = sample.Motion with { Status = "fly" } },
            "layer" => sample with { LayerId = "other" }, "corridor" => sample with { X = sample.X + 10 }, _ => sample };
        Assert.Equal(expected, NavigationBaselineRecovery.HardPoseRejection(sample));
    }

    /// <summary>Recovery history is file evidence, never a training eligibility or success assertion.</summary>
    [Fact]
    public void JournalPreservesPauseWaitRangesAndFailedOutcome()
    {
        var pause = new NavigationBaselineRecoveryPause(1, NavigationBaselineRecoveryCause.LeaseExpired, 1000, 1003, null);
        var attempt = new NavigationBaselineRecoveryAttempt { Pause = pause, TriggerCause = NavigationBaselineRecoveryCause.SourceAge,
            TriggerStage = "after_capture", DeadlineAtMs = 3000,
            ObservationStart = 2, ObservationEnd = 4, PollStart = 3, PollEnd = 35,
            EndedAtMs = 2000, Outcome = "failed", Error = "recovery_poll_limit_exceeded" };
        var journal = new NavigationBaselineJournal { RunId = new string('a', 32), GameProcessId = 10, WindowsSessionId = 3,
            WorkflowResult = new() { TimingContract = "v4", Error = attempt.Error }, Observations = [], InputTransitions = [],
            ScheduleWaits = [], ObservationAttempts = [], CapturePolls = [], RecoveryPauses = [pause], RecoveryAttempts = [attempt] };
        using var doc = JsonDocument.Parse(journal.Serialize()); var value = doc.RootElement;
        Assert.False(value.GetProperty("trainingEligible").GetBoolean()); Assert.Equal("v4", value.GetProperty("timingContract").GetString());
        Assert.Equal(1, value.GetProperty("recoverySchemaVersion").GetInt32());
        Assert.Equal(35, value.GetProperty("recoveryAttempts")[0].GetProperty("pollEnd").GetInt32());
        Assert.Equal("failed", value.GetProperty("recoveryAttempts")[0].GetProperty("outcome").GetString());
        Assert.Equal("SourceAge", value.GetProperty("recoveryAttempts")[0].GetProperty("triggerCause").GetString());
        Assert.Equal("LeaseExpired", value.GetProperty("recoveryAttempts")[0].GetProperty("pause").GetProperty("cause").GetString());
    }

    /// <summary>Minimal fake at the existing native boundary; it does not reproduce the production lease implementation.</summary>
    private sealed class Operations : INavigationBaselineOperations, INavigationBaselineRecoveryOperations
    {
        /// <summary>Deterministic monotonic clock.</summary>
        public double NowMs { get; private set; } = 1000;
        /// <summary>Fake owned forward state and terminal fault.</summary>
        public bool ForwardHeld { get; private set; }
        /// <summary>Optional concurrent fault, installed only at the failed read.</summary>
        public string? Fault { get; private set; }
        /// <summary>Successful fake releases.</summary>
        public string? ReleaseError => null;
        /// <summary>One injected typed read interruption; -1 means none.</summary>
        internal int InterruptRead = -1;
        /// <summary>Hard failure and simultaneous watchdog evidence.</summary>
        internal string? HardFailure, FaultAtRead, RecoveryFailure;
        /// <summary>Preserve a wrapped production timeout instead of simulating only its final string.</summary>
        internal Exception? RecoveryException;
        /// <summary>Recovery does not move the overall clock origin.</summary>
        internal double RecoveryWorkMs = 90, RecoveryDeadline;
        /// <summary>Observable workflow order, decisions and counts.</summary>
        internal bool Closed, EnabledAfterAnchor, ReleasedBeforeRecoveryWait, PublishedAfterClose;
        /// <summary>Only physical fake starts are counted.</summary>
        internal int Downs, Recoveries, Reads;
        /// <summary>Final observation closure states.</summary>
        internal List<bool> FinalReadClosed = [];
        /// <summary>Exact workflow publication arguments.</summary>
        internal NavigationBaselineDecision[] Decisions = [];
        /// <summary>Failure precedence must survive through evidence publication.</summary>
        internal NavigationBaselineRunResult? PublishedResult;
        /// <summary>No setup side effects.</summary>
        public Task PrepareAsync(CancellationToken ct) => Task.CompletedTask;
        /// <summary>Distinct synthetic sources with a single selected failure.</summary>
        public Task<NavigationBaselineSample> ReadPoseAsync(string? retainImage, CancellationToken ct)
        {
            var read = Reads++; NowMs += 120;
            if (read == 1 && HardFailure is not null) { Fault = FaultAtRead; throw new InvalidOperationException(HardFailure); }
            if (read == InterruptRead) throw new NavigationBaselineRecoveryRequired(NavigationBaselineRecoveryCause.SourceAge, "after_capture");
            if (read >= 3) FinalReadClosed.Add(Closed);
            return Task.FromResult(Sample(read == 0 ? 0 : read == 1 ? 0.45 : 1, NowMs));
        }
        /// <summary>Enable must be after the anchor read and before any interruption handling.</summary>
        public void EnableRecovery() => EnabledAfterAnchor = Reads == 1 && Downs == 0;
        /// <summary>Model only the native boundary result; dedicated lease tests prove real gate/release semantics.</summary>
        public Task<NavigationBaselineSample> RecoverAsync(NavigationBaselineRecoveryRequired interruption, double deadline, CancellationToken ct)
        {
            Recoveries++; RecoveryDeadline = deadline; ForwardHeld = false; ReleasedBeforeRecoveryWait = !ForwardHeld;
            NowMs += RecoveryWorkMs;
            if (RecoveryException is not null) throw RecoveryException;
            if (RecoveryFailure is not null) throw new InvalidOperationException(RecoveryFailure);
            return Task.FromResult(Sample(0.45, NowMs));
        }
        /// <summary>Fake camera only, unused by aligned fixtures.</summary>
        public NavigationBaselineInputEvent Rotate(NavigationBaselineSample sample, CancellationToken ct) => new("camera", NowMs, NowMs);
        /// <summary>Only workflow calls can press; recovery never calls this.</summary>
        public NavigationBaselineInputEvent Forward(NavigationBaselineSample sample, CancellationToken ct)
        { if (Closed) throw new InvalidOperationException("closed"); if (!ForwardHeld) Downs++; ForwardHeld = true; return new("w_down", NowMs, NowMs); }
        /// <summary>Nonterminal fake release.</summary>
        public NavigationBaselineInputEvent ReleaseForward() { ForwardHeld = false; return new("w_up", NowMs, NowMs); }
        /// <summary>Final closure is permanent.</summary>
        public void CloseInput() { Closed = true; ForwardHeld = false; }
        /// <summary>No wall-clock sleeps.</summary>
        public Task WaitUntilAsync(double deadlineMs, CancellationToken ct) { NowMs = Math.Max(NowMs, deadlineMs); return Task.CompletedTask; }
        /// <summary>Capture the exact result/decisions while providing synthetic complete evidence.</summary>
        public Task<NavigationBaselineEvidence> PublishEvidenceAsync(NavigationBaselineRunResult result, NavigationBaselineDecision[] decisions,
            NavigationBaselineScheduleWait[] scheduleWaits)
        {
            PublishedAfterClose = Closed; PublishedResult = result; Decisions = decisions;
            return Task.FromResult(new NavigationBaselineEvidence(true, "journal", new string('a', 64), "initial", new string('b', 64), "final", new string('c', 64)));
        }
    }
}
