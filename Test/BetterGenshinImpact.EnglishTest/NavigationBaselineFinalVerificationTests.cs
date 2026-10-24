using System.Diagnostics;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Deterministic terminal-read tests; no game, real capture, input, GPU, sleeps or SDK process.</summary>
public sealed class NavigationBaselineFinalVerificationTests
{
    /// <summary>Immutable synthetic source generation, shared by the whole measured leg.</summary>
    private static readonly Guid Epoch = Guid.Parse("713e569b-05ac-4a78-aadf-8a29455fcd92");
    /// <summary>Exact integer source clocks at the current high-resolution clock frequency.</summary>
    private static GameCaptureSourceInfo Source(double at) => new(Epoch, (long)(at * 10000), (long)(at * Stopwatch.Frequency / 1000));
    /// <summary>Finite endpoint pose; test mutations change only the predicate under test.</summary>
    private static NavigationBaselineSample Sample(double at, double age = 10, double fraction = 1)
    {
        var x = NavigationBaselineTask.StartX + fraction * (NavigationBaselineTask.EndX - NavigationBaselineTask.StartX);
        var y = NavigationBaselineTask.StartY + fraction * (NavigationBaselineTask.EndY - NavigationBaselineTask.StartY);
        var source = Source(at); var geometry = NavigationBaselineTask.Geometry(x, y);
        return new(x, y, 47, DateTimeOffset.UnixEpoch, Epoch, source.SourceTimestamp100ns, source.AcquiredAtStopwatchTicks,
            .999, .8, "City_102", new("normal", AgentMotionEvidence.MethodName, false, false, 1), age, 47,
            geometry.Distance, geometry.Projection, geometry.CrossTrack, new(at - 10, at - 10, at + 1, at + age));
    }

    /// <summary>Replay measured r27 final-source ages, including an image/callback-stage overrun with two retained poses.</summary>
    [Fact]
    public async Task R27ThirdReadAgesAfterRecognitionThenFourthCompletesWithoutDuplicateRows()
    {
        var fixture = new Fixture();
        fixture.RecognitionAges = [42.1362, 112.244, 146.5212, 10];
        fixture.CaptureAges = [10, 10, 101.1478, 10];
        fixture.CloneTimes = [0, 0, 6.0947, 0];
        await fixture.Run();
        Assert.Equal(4, fixture.Attempts.Count); Assert.Equal(4, fixture.Window.Record.ReadCount);
        Assert.Equal(4, fixture.Window.Record.CaptureCount); Assert.Equal(1, fixture.Window.Record.SourceAgeDiscards);
        Assert.Equal(new[] { 0, 1, 3 }, fixture.Window.Record.AcceptedReadIndices);
        Assert.Equal(3, fixture.Final.Count); Assert.Equal(3, fixture.Decisions.Count);
        Assert.Equal(3, fixture.Decisions.Select(x => x.Sample.SourceTimestamp100ns).Distinct().Count());
        Assert.Equal("source_age_discard", fixture.Attempts[2].FinalVerificationDisposition);
        Assert.InRange(fixture.Attempts[2].FinalVerificationSourceAgeMs!.Value, 152.6158, 152.6161);
        Assert.Equal("admitting_final_sample", fixture.Attempts[2].FinalVerificationCheckStage);
        Assert.Equal(fixture.Final[^1].Source, fixture.ImageSource);
        Assert.Null(NavigationBaselineTask.FinalRejection(fixture.Final));
        Assert.Equal("completed", fixture.Window.Record.Outcome); Assert.Equal(0, fixture.InputCalls);
    }

    /// <summary>Native stage-specific age checks all share the same bounded typed discard, not text matching.</summary>
    [Theory]
    [InlineData("after_capture")]
    [InlineData("after_recognition")]
    [InlineData("admitting_final_sample")]
    public void OnlyPositiveValidatedAgeProducesRetrySignal(string stage)
    {
        double now = 1100;
        var window = new NavigationBaselineFinalVerification(() => now, 1000, 31000, Source(900), 0, 0);
        var attempt = new NavigationBaselineObservationAttempt(now);
        Assert.Equal(Source(950), window.ValidateSource(Source(950), stage, attempt, default));
        now = 1100.001;
        var error = Assert.Throws<NavigationBaselineFinalVerification.SourceAgeException>(() =>
            window.ValidateSource(Source(950), stage, attempt, default));
        Assert.Equal($"final_verification_source_age: {stage}", error.Message);
        Assert.Equal("source_age_discard", attempt.FinalVerificationDisposition);
    }

    /// <summary>A discarded after-capture source still advances immutable epoch/clock high-water.</summary>
    [Theory]
    [InlineData("epoch", "source_epoch_changed")]
    [InlineData("reported", "native_source_regressed")]
    [InlineData("acquired", "native_source_regressed")]
    [InlineData("missing", "invalid_native_source")]
    [InlineData("future", "acquisition_in_future")]
    public void HardSourceFailureWinsAfterStaleHeader(string mutation, string expected)
    {
        double now = 1200;
        var window = new NavigationBaselineFinalVerification(() => now, 1100, 31000, Source(900), 0, 0);
        var seen = Source(1000);
        Assert.Throws<NavigationBaselineFinalVerification.SourceAgeException>(() =>
            window.ValidateSource(seen, "after_capture", new(now), default));
        GameCaptureSourceInfo? next = mutation switch
        {
            "epoch" => seen with { CaptureEpoch = Guid.NewGuid() },
            "reported" => seen with { SourceTimestamp100ns = seen.SourceTimestamp100ns - 1 },
            "acquired" => seen with { AcquiredAtStopwatchTicks = seen.AcquiredAtStopwatchTicks - 1 },
            "future" => Source(1201), _ => null
        };
        Assert.Equal(expected, Assert.Throws<InvalidOperationException>(() =>
            window.ValidateSource(next, "after_capture", new(now), default)).Message);
    }

    /// <summary>Recognized endpoint/cluster/source failures remain terminal even when the same sample is aged.</summary>
    [Theory]
    [InlineData("endpoint", "endpoint_not_reached")]
    [InlineData("spread", "position_spread_exceeded")]
    [InlineData("yaw", "yaw_spread_exceeded")]
    [InlineData("spacing", "acquisition_spacing_too_short")]
    [InlineData("motion", "non_normal_motion")]
    [InlineData("corridor", "route_corridor_exceeded")]
    [InlineData("layer", "wrong_layer")]
    [InlineData("invalidAge", "invalid_source_age")]
    public void HardFinalPrefixPrecedesSourceAge(string mutation, string expected)
    {
        var first = Sample(1200); var candidate = Sample(1320, 151);
        candidate = mutation switch
        {
            "endpoint" => Sample(1320, 151, .7),
            "spread" => candidate with { X = candidate.X + 1.6 },
            "yaw" => candidate with { YawDegrees = 50 },
            "spacing" => Sample(1279, 151),
            "motion" => candidate with { Motion = candidate.Motion with { Status = "climb" } },
            "corridor" => candidate with { X = candidate.X + 10 },
            "layer" => candidate with { LayerId = "other" },
            _ => candidate with { SourceAgeMs = double.NaN }
        };
        Assert.Equal(expected, NavigationBaselineFinalVerification.HardPrefixRejection([first], candidate));
    }

    /// <summary>One bounded native read cannot hide an unlimited duplicate/barrier loop.</summary>
    [Fact]
    public async Task ActualCaptureLimitStopsBeforeThirtyThirdCall()
    {
        double now = 1000;
        var window = new NavigationBaselineFinalVerification(() => now, 1000, 31000, Source(990), 0, 0);
        var captures = 0;
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => window.CollectAsync(token =>
        {
            while (true) { window.BeginCapture(token).CompleteCapture(); captures++; now += 1; }
        }, (_, _) => Task.CompletedTask, default));
        Assert.Equal("final_verification_capture_limit_exceeded", error.Message);
        Assert.Equal(32, captures); Assert.Equal(1, window.Record.ReadCount);
        Assert.Equal(32, window.Record.CaptureCount); Assert.Empty(window.Record.AcceptedReadIndices);
    }

    /// <summary>Repeated identical stale pixels cannot reset the window or manufacture a new source.</summary>
    [Fact]
    public async Task IdenticalStaleHeaderEndsAtWholeWindowReadLimit()
    {
        double now = 1051;
        var window = new NavigationBaselineFinalVerification(() => now, 1000, 31000, Source(900), 0, 0);
        var reads = 0;
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => window.CollectAsync(token =>
        {
            reads++; window.BeginCapture(token).CompleteCapture();
            window.ValidateSource(Source(900), "after_capture", new(now), token);
            throw new Exception("unreachable");
        }, (at, _) => { now = at; return Task.CompletedTask; }, default));
        Assert.Equal("final_verification_read_limit_exceeded", error.Message);
        Assert.Equal(32, reads); Assert.Equal(32, window.Record.SourceAgeDiscards);
        Assert.Equal(3000, window.Record.DeadlineAtMs); Assert.Empty(window.Record.AcceptedReadIndices);
    }

    /// <summary>Delayed row preparation never publishes a discarded row, count or image before the final gate.</summary>
    [Fact]
    public async Task PreparedRowsRemainUnpublishedWhenCallbackDelayAgesSource()
    {
        var fixture = new Fixture { StageDelayOnce = 151 };
        await fixture.Run();
        Assert.Equal(4, fixture.Attempts.Count); Assert.Equal(3, fixture.Final.Count);
        Assert.Equal(new[] { 1, 2, 3 }, fixture.Window.Record.AcceptedReadIndices);
        Assert.Equal(fixture.Final.Count, fixture.ImageCommits);
        Assert.Equal(fixture.Final[^1].Source, fixture.ImageSource);
        Assert.DoesNotContain(fixture.Decisions, row => row.Sample.Source == fixture.Attempts[0].LastReturnedSource);
        Assert.All(fixture.PreparationCounts, counts => Assert.Equal(counts.Before, counts.After));
    }

    /// <summary>A real decision-capacity failure preserves earlier image/sample identity rather than committing rejected pixels.</summary>
    [Fact]
    public async Task AdmissionCapacityFailureRetainsOnlyEarlierSampleAndImage()
    {
        var fixture = new Fixture { ExhaustDecisionsAfterFirst = true };
        var error = await Assert.ThrowsAsync<InvalidOperationException>(fixture.Run);
        Assert.Equal("final_verification_sample_capacity_exceeded", error.Message);
        Assert.Single(fixture.Final); Assert.Equal(1, fixture.ImageCommits);
        Assert.Equal(fixture.Final[0].Source, fixture.ImageSource);
        Assert.Single(fixture.Window.Record.AcceptedReadIndices);
        Assert.False(NativeNavigationBaselineOperations.EvidenceIsComplete(new() { Error = error.Message }));
    }

    /// <summary>A preparation exception after row allocation cannot publish the candidate or erase the prior prefix.</summary>
    [Fact]
    public async Task RowPreparationFailureDoesNotCommitCandidateImageOrCounts()
    {
        var fixture = new Fixture { PreparationFailureAfterTwo = true };
        var error = await Assert.ThrowsAsync<InvalidOperationException>(fixture.Run);
        Assert.Equal("row_preparation_failed", error.Message);
        Assert.Equal(2, fixture.Final.Count); Assert.Equal(2, fixture.Decisions.Count);
        Assert.Equal(2, fixture.ImageCommits); Assert.Equal(fixture.Final[^1].Source, fixture.ImageSource);
        Assert.Equal(new[] { 0, 1 }, fixture.Window.Record.AcceptedReadIndices);
        Assert.All(fixture.PreparationCounts, counts => Assert.Equal(counts.Before, counts.After));
    }

    /// <summary>A late synchronous capture/recognition/clone cannot admit a pose beyond either fixed deadline.</summary>
    [Theory]
    [InlineData("capture", 31000)]
    [InlineData("recognition", 31000)]
    [InlineData("clone", 31000)]
    [InlineData("clone", 1100)]
    public async Task SlowWorkCannotPublishLateReadiness(string stage, double ownerDeadline)
    {
        var fixture = new Fixture(ownerDeadline);
        if (stage == "capture") fixture.CaptureAges = [2100];
        if (stage == "recognition") fixture.RecognitionAges = [2100];
        if (stage == "clone") fixture.CloneTimes = [2100];
        await Assert.ThrowsAsync<NavigationBaselineFinalVerification.TimeoutException>(fixture.Run);
        Assert.Empty(fixture.Final); Assert.Empty(fixture.Decisions); Assert.Null(fixture.ImageSource);
        Assert.Equal(0, fixture.InputCalls); Assert.Equal("final_verification_deadline_exceeded", fixture.Window.Record.Error);
    }

    /// <summary>A late third read retains exactly the two already committed poses and their matching image.</summary>
    [Fact]
    public async Task DeadlineAfterTwoKeepsOnlyTheAdmittedPrefix()
    {
        var fixture = new Fixture { CloneTimes = [0, 0, 2100] };
        await Assert.ThrowsAsync<NavigationBaselineFinalVerification.TimeoutException>(fixture.Run);
        Assert.Equal(2, fixture.Final.Count); Assert.Equal(2, fixture.Decisions.Count);
        Assert.Equal(2, fixture.ImageCommits); Assert.Equal(fixture.Final[^1].Source, fixture.ImageSource);
        Assert.Equal(new[] { 0, 1 }, fixture.Window.Record.AcceptedReadIndices);
        Assert.Equal(0, fixture.Window.Record.SourceAgeDiscards);
    }

    /// <summary>Owner cancellation wins before any capture or read, without being translated to a final-window timeout.</summary>
    [Fact]
    public async Task CancelledOwnerCannotStartARead()
    {
        using var stop = new CancellationTokenSource(); stop.Cancel();
        var window = new NavigationBaselineFinalVerification(() => 1000, 1000, 31000, Source(990), 0, 0);
        var error = await Assert.ThrowsAsync<OperationCanceledException>(() => window.CollectAsync(
            _ => throw new InvalidOperationException("unexpected_read"), (_, _) => Task.CompletedTask, stop.Token));
        Assert.Equal(stop.Token, error.CancellationToken);
        Assert.Equal(0, window.Record.ReadCount); Assert.Equal(0, window.Record.CaptureCount);
        Assert.Empty(window.Record.AcceptedReadIndices);
    }

    /// <summary>Hard recognizer errors and foreign cancellation never become age retries.</summary>
    [Theory]
    [InlineData("world_not_ready")]
    [InlineData("chat_open")]
    [InlineData("native_frame_geometry_changed")]
    [InlineData("native_source_unavailable_or_stale")]
    public async Task UntypedErrorsPropagateWithoutRetry(string message)
    {
        var fixture = new Fixture { FailureAfterTwo = new InvalidOperationException(message) };
        Assert.Same(fixture.FailureAfterTwo, await Assert.ThrowsAsync<InvalidOperationException>(fixture.Run));
        Assert.Equal(3, fixture.Attempts.Count); Assert.Equal(2, fixture.Final.Count);
        Assert.Equal(2, fixture.ImageCommits); Assert.Equal(0, fixture.Window.Record.SourceAgeDiscards);
    }

    /// <summary>The first owner deadline can prevent all work; a foreign OCE retains its own instance and token.</summary>
    [Fact]
    public async Task ZeroWorkExpiredOwnerAndForeignCancellationRemainDistinct()
    {
        var expired = new Fixture(999);
        await Assert.ThrowsAsync<NavigationBaselineFinalVerification.TimeoutException>(expired.Run);
        Assert.Empty(expired.Attempts); Assert.Equal(0, expired.Window.Record.CaptureCount);
        using var foreign = new CancellationTokenSource(); foreign.Cancel();
        var error = new OperationCanceledException("foreign native cancellation", foreign.Token);
        var fixture = new Fixture { FailureAfterTwo = error };
        Assert.Same(error, await Assert.ThrowsAsync<OperationCanceledException>(fixture.Run));
        Assert.Equal("foreign native cancellation", fixture.Window.Record.Error);
        Assert.Equal(2, fixture.Final.Count);
    }

    /// <summary>The real closed input owner rejects all dispatch/rearm attempts throughout a successful final window.</summary>
    [Fact]
    public async Task ClosedLeaseCannotPressRotateOrResumeDuringFinalReads()
    {
        var fixture = new Fixture(); var downs = 0; var ups = 0; var camera = 0;
        var lease = new NavigationBaselineInputLease(() => fixture.Now, () => true, () => downs++, () => ups++,
            _ => camera++, default, false, "v4");
        try
        {
            lease.EnableRecovery(); lease.Forward(Source(990), default);
            Assert.Equal(1000, lease.Close());
            fixture.BeforeAdmission = sample =>
            {
                Assert.Throws<InvalidOperationException>(() => lease.Forward(sample.Source, default));
                Assert.Throws<InvalidOperationException>(() => lease.Rotate(sample.Source, 1, default));
                Assert.Throws<InvalidOperationException>(() => lease.ResumeRecovery(
                    new(1, NavigationBaselineRecoveryCause.SourceAge, 1000, 1000, null), sample.Source, default));
            };
            await fixture.Run();
            Assert.Equal(1, downs); Assert.Equal(1, ups); Assert.Equal(0, camera);
            Assert.False(lease.ForwardHeld); Assert.Empty(lease.RecoveryPauses);
            Assert.Equal(1000, lease.Close()); Assert.Equal(1000, fixture.Window.Record.ClosedAtMs);
        }
        finally { try { await lease.DisposeAsync(); } catch (InvalidOperationException) { } }
    }

    /// <summary>Invalid/regressed collector clocks fail before source age can become a retry label.</summary>
    [Theory]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    [InlineData(999)]
    public void InvalidCollectorClockCannotAuthorizeAgeDiscard(double badClock)
    {
        double now = 1000;
        var window = new NavigationBaselineFinalVerification(() => now, 1000, 31000, Source(990), 0, 0);
        now = badClock;
        var attempt = new NavigationBaselineObservationAttempt(1000);
        Assert.Equal("invalid_final_verification_clock", Assert.Throws<InvalidOperationException>(() =>
            window.ValidateSource(Source(990), "after_capture", attempt, default)).Message);
        Assert.Null(attempt.FinalVerificationDisposition);
    }

    /// <summary>Missing final policy on v1–v3 is distinct from v4 with a final window never reached.</summary>
    [Theory]
    [InlineData("v1", false)]
    [InlineData("v2", false)]
    [InlineData("v3", false)]
    [InlineData("v4", true)]
    public void FinalPolicyVersionIsSeparateFromMovementRecovery(string contract, bool expected)
    {
        var journal = new NavigationBaselineJournal { RunId = new string('a', 32), GameProcessId = 1, WindowsSessionId = 3,
            WorkflowResult = new() { TimingContract = contract }, Observations = [], InputTransitions = [],
            ScheduleWaits = [], ObservationAttempts = [], CapturePolls = [] };
        using var document = JsonDocument.Parse(journal.Serialize());
        Assert.Equal(expected, document.RootElement.TryGetProperty("finalVerificationReadinessVersion", out var version));
        if (expected) Assert.Equal(2, version.GetInt32());
        Assert.False(document.RootElement.TryGetProperty("finalVerificationWindow", out _));
        Assert.Equal(expected ? 2 : 1, document.RootElement.GetProperty("recoverySchemaVersion").GetInt32());
    }

    /// <summary>The real task callback retains exactly three rows/images through the measured late-third-read scenario.</summary>
    [Fact]
    public async Task WorkflowUsesClosedWindowAndPublishesEachAcceptedSourceOnce()
    {
        var operations = new WorkflowOperations();
        var task = new NavigationBaselineTask(operations, "v4");
        var progress = new List<(string Phase, int Accepted)>();
        var result = await task.RunAsync(value => progress.Add((value, task.Result.ObservationCount)), default);
        Assert.True(result.Verified); Assert.Equal(3, result.Samples.Length);
        Assert.Equal(3, result.VerificationSamples.Length); Assert.Equal(5, result.ObservationCount);
        Assert.Equal(4, operations.FinalFixture!.Attempts.Count);
        Assert.Equal(result.Samples[^1].Source, operations.FinalFixture.ImageSource);
        Assert.Equal(1, operations.Downs); Assert.True(operations.Closed);
        Assert.Equal(0, operations.Recoveries); Assert.Equal(31000, operations.OwnerDeadline);
        Assert.Equal(result.ObservationCount, operations.Decisions.Length);
        Assert.Equal(operations.Decisions.Length, operations.Decisions.Select(row => row.Sample.Source).Distinct().Count());
        Assert.All(progress.TakeWhile(value => value.Phase != "publishing_evidence"), value => Assert.Equal(0, value.Accepted));
        Assert.Single(progress.Where(value => value.Phase == "verifying"));
    }

    /// <summary>Final hard errors preserve two admitted samples and their image in the task's failed published result.</summary>
    [Fact]
    public async Task WorkflowRetainsPartialPrefixWithoutReopeningInput()
    {
        var operations = new WorkflowOperations { FinalFailure = new InvalidOperationException("chat_open") };
        var result = await new NavigationBaselineTask(operations, "v4").RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal("chat_open", result.Error); Assert.Empty(result.Samples);
        Assert.Equal(2, result.VerificationSamples.Length); Assert.Equal(4, result.ObservationCount);
        Assert.Equal(result.VerificationSamples[^1].Source, operations.FinalFixture!.ImageSource);
        Assert.Equal(1, operations.Downs); Assert.Equal(0, operations.Recoveries); Assert.True(operations.Closed);
    }

    /// <summary>V1–V3 keep the existing exact-three branch and do not invoke the new final collector.</summary>
    [Theory]
    [InlineData("v1")]
    [InlineData("v2")]
    [InlineData("v3")]
    public async Task LegacyTaskBranchRemainsStrict(string contract)
    {
        var operations = new WorkflowOperations();
        var result = await new NavigationBaselineTask(operations, contract).RunAsync(_ => { }, default);
        Assert.False(result.Verified); Assert.Equal("native_source_stale", result.Error);
        Assert.Null(operations.FinalFixture); Assert.Equal(3, operations.LegacyFinalReads);
        Assert.True(operations.Closed); Assert.Equal(0, operations.Recoveries);
    }

    /// <summary>The real native-record wrapper and final helper share a deterministic capture/recognition/image boundary.</summary>
    private sealed class Fixture
    {
        /// <summary>Absolute fake QPC clock and immutable terminal closure.</summary>
        internal double Now = 1000;
        /// <summary>The production helper under test; no input primitive is available to it.</summary>
        internal readonly NavigationBaselineFinalVerification Window;
        /// <summary>Same lists passed by the production task callback.</summary>
        internal readonly List<NavigationBaselineSample> Final = [];
        /// <summary>Single decision per admitted source.</summary>
        internal readonly List<NavigationBaselineDecision> Decisions = [];
        /// <summary>Real wrapper records success, typed discard or hard failure.</summary>
        internal readonly List<NavigationBaselineObservationAttempt> Attempts = [];
        /// <summary>Private row counts must not change while the real preparation callback is evaluated.</summary>
        internal readonly List<(int Before, int After)> PreparationCounts = [];
        /// <summary>Synthetic durations at native stages, independently configurable per read.</summary>
        internal double[] CaptureAges = [10], RecognitionAges = [10], CloneTimes = [0];
        /// <summary>Last image identity changes only in the production admission callback.</summary>
        internal GameCaptureSourceInfo? ImageSource;
        /// <summary>No control dispatch exists in this fixture; count must remain zero.</summary>
        internal int InputCalls, ImageCommits;
        /// <summary>Exercise the post-callback gate rather than only pre-recognition freshness.</summary>
        internal double StageDelayOnce;
        /// <summary>Introduce actual task-row capacity failure after the first committed image.</summary>
        internal bool ExhaustDecisionsAfterFirst;
        /// <summary>A fake allocation/capacity boundary may fail after constructing an unpublished row.</summary>
        internal bool PreparationFailureAfterTwo;
        /// <summary>Preserve the first two accepted poses when a later hard error occurs.</summary>
        internal Exception? FailureAfterTwo;
        /// <summary>Test-only callback exercises an already closed real lease without exposing a dispatch sink to the collector.</summary>
        internal Action<NavigationBaselineSample>? BeforeAdmission;
        /// <summary>Integration fixtures use the real task-owned row transaction rather than this fixture's lists.</summary>
        internal Func<NavigationBaselineSample, NavigationBaselineFinalVerification.Admission>? ExternalStage;
        /// <summary>One closed-input window uses the original owner deadline.</summary>
        internal Fixture(double ownerDeadline = 31000, double closedAt = 1000)
        { Now = closedAt; Window = new(() => Now, closedAt, ownerDeadline, Source(closedAt - 10), 0, 0); }
        /// <summary>Use the exact production read wrapper and helper; no timing sleeps.</summary>
        internal Task Run() => Window.CollectAsync(Read, (at, _) => { Now = Math.Max(Now, at); return Task.CompletedTask; }, default);
        /// <summary>Mirror only stage IO; all source/window/admission classification calls are production code.</summary>
        private Task<NavigationBaselineSample> Read(CancellationToken ct) =>
            NativeNavigationBaselineOperations.RecordObservationAsync(Attempts, () => Now, () => null, attempt =>
            {
                var index = Attempts.Count - 1;
                if (index == 2 && FailureAfterTwo is not null) throw FailureAfterTwo;
                Window.BeginCapture(ct).CompleteCapture();
                var sourceAt = Math.Max(Now, Window.ClosedAtMs + 80);
                var source = Source(sourceAt);
                attempt.LastReturnedSource = source; attempt.CaptureCount = 1;
                Now = sourceAt + CaptureAges[Math.Min(index, CaptureAges.Length - 1)];
                Window.ValidateSource(source, "after_capture", attempt, ct);
                Now = Math.Max(Now, sourceAt + RecognitionAges[Math.Min(index, RecognitionAges.Length - 1)]);
                var sample = Sample(sourceAt, Now - sourceAt);
                Window.ValidatePose(sample);
                Window.ValidateSource(source, "after_recognition", attempt, ct);
                Now += CloneTimes[Math.Min(index, CloneTimes.Length - 1)];
                if (ExhaustDecisionsAfterFirst && Final.Count == 1)
                    while (Decisions.Count < NavigationBaselineTask.MaximumObservations) Decisions.Add(new("other", sample, null));
                BeforeAdmission?.Invoke(sample);
                Window.Admit(sample, index, attempt, value =>
                {
                    var before = Final.Count;
                    var staged = ExternalStage is null ? NavigationBaselineFinalVerification.StageDecision(value, Final, Decisions)
                        : ExternalStage(value);
                    PreparationCounts.Add((before, Final.Count));
                    if (index == 2 && PreparationFailureAfterTwo) throw new InvalidOperationException("row_preparation_failed");
                    Now += StageDelayOnce; StageDelayOnce = 0;
                    return staged;
                }, () => { ImageSource = source; ImageCommits++; }, () => { }, ct);
                attempt.Stage = "completed";
                return Task.FromResult(sample);
            });
    }

    /// <summary>Production task integration with a fake capture boundary and the real final collector/row transaction.</summary>
    private sealed class WorkflowOperations : INavigationBaselineOperations, INavigationBaselineRecoveryOperations,
        INavigationBaselineFinalVerificationOperations
    {
        /// <summary>Travel clock before the terminal final-read fixture owns it.</summary>
        private double _now = 1000;
        /// <summary>Distinct travel-read count.</summary>
        private int _reads;
        /// <summary>Actual final collector fixture, absent on unchanged legacy paths.</summary>
        internal Fixture? FinalFixture;
        /// <summary>Optional hard final failure after two admitted observations.</summary>
        internal Exception? FinalFailure;
        /// <summary>Only task-level calls can change this fake input state.</summary>
        internal bool Closed;
        /// <summary>Counts prove the final collector never invokes movement or recovery.</summary>
        internal int Downs, Recoveries, LegacyFinalReads;
        /// <summary>The fixed owner deadline forwarded by the task.</summary>
        internal double OwnerDeadline;
        /// <summary>Exact decision publication, without image or disk IO.</summary>
        internal NavigationBaselineDecision[] Decisions = [];
        /// <summary>One continuous absolute clock.</summary>
        public double NowMs => FinalFixture?.Now ?? _now;
        /// <summary>Fake held state, cleared at permanent closure.</summary>
        public bool ForwardHeld { get; private set; }
        /// <summary>No hidden native fault or failed release in these fixtures.</summary>
        public string? Fault => null;
        /// <summary>All fake key releases succeed.</summary>
        public string? ReleaseError => null;
        /// <summary>No asset setup or native capture.</summary>
        public Task PrepareAsync(CancellationToken ct) => Task.CompletedTask;
        /// <summary>Travel reaches the endpoint after one W; legacy final sample three is intentionally aged.</summary>
        public Task<NavigationBaselineSample> ReadPoseAsync(string? retainImage, CancellationToken ct)
        {
            _now += _reads++ == 0 ? 20 : 80;
            if (retainImage == "final")
            {
                Assert.True(Closed); LegacyFinalReads++;
                return Task.FromResult(Sample(_now - 10, LegacyFinalReads == 3 ? 151 : 10));
            }
            return Task.FromResult(Sample(_now - 10, fraction: retainImage == "initial" ? 0 : 1));
        }
        /// <summary>The production task is responsible for closure before invoking this explicit final-only boundary.</summary>
        public Task ReadFinalSamplesAsync(double ownerDeadlineMs,
            Func<NavigationBaselineSample, NavigationBaselineFinalVerification.Admission> stageRows, CancellationToken ct)
        {
            Assert.True(Closed); Assert.False(ForwardHeld); OwnerDeadline = ownerDeadlineMs;
            FinalFixture = new(ownerDeadlineMs, _now) { ExternalStage = stageRows,
                RecognitionAges = [42.1362, 112.244, 146.5212, 10], CaptureAges = [10, 10, 101.1478, 10],
                CloneTimes = [0, 0, 6.0947, 0], FailureAfterTwo = FinalFailure };
            return FinalFixture.Run();
        }
        /// <summary>Travel-only capability is present but never used by terminal reads.</summary>
        public void EnableRecovery() { Assert.False(Closed); }
        /// <summary>Any attempted movement recovery in this final-read test is a failure.</summary>
        public Task<NavigationBaselineSample> RecoverAsync(NavigationBaselineRecoveryRequired interruption, double deadline, CancellationToken ct)
        { Recoveries++; throw new InvalidOperationException("unexpected_movement_recovery"); }
        /// <summary>Aligned fake travel never requires camera input.</summary>
        public NavigationBaselineInputEvent Rotate(NavigationBaselineSample sample, CancellationToken ct) => throw new InvalidOperationException("unexpected_camera");
        /// <summary>Real task control entry only; closure is permanent.</summary>
        public NavigationBaselineInputEvent Forward(NavigationBaselineSample sample, CancellationToken ct)
        { Assert.False(Closed); Downs++; ForwardHeld = true; return new("w_down", NowMs, NowMs); }
        /// <summary>No realignment is needed in this fixture.</summary>
        public NavigationBaselineInputEvent ReleaseForward() { ForwardHeld = false; return new("w_up", NowMs, NowMs); }
        /// <summary>One terminal latch, never changed by later collection or repeated finally cleanup.</summary>
        public void CloseInput() { Closed = true; ForwardHeld = false; }
        /// <summary>Advance the fake clock without wall-clock sleeps.</summary>
        public Task WaitUntilAsync(double at, CancellationToken ct) { _now = Math.Max(_now, at); return Task.CompletedTask; }
        /// <summary>Preserve exact task output; no physical evidence claims are made by this test stub.</summary>
        public Task<NavigationBaselineEvidence> PublishEvidenceAsync(NavigationBaselineRunResult result,
            NavigationBaselineDecision[] decisions, NavigationBaselineScheduleWait[] scheduleWaits)
        {
            Assert.True(Closed); Decisions = decisions;
            return Task.FromResult(new NavigationBaselineEvidence(true, "journal", new string('a', 64),
                "initial", new string('b', 64), "final", new string('c', 64)));
        }
    }
}
