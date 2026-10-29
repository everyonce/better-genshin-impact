using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using Newtonsoft.Json.Linq;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Offline checks of the actual controller/inspection transition using inert keys and synthetic pixels.</summary>
public sealed class AgentMapInspectionTests
{
    [Fact]
    public void OpenVerifyCloseAndRearmUsesOnlyTwoFixedPulses()
    {
        using var f = new Fixture();
        f.Start();
        f.WalkTo("awaitMap", true);
        Assert.True(f.Inspection.BlocksMovement);
        f.WalkTo("awaitWorld", false);
        f.WalkTo("completed", true);
        Assert.Equal(new[] { "M:down", "M:up", "ESCAPE:down", "ESCAPE:up" }, f.Input.Keys);
        var result = f.Result;
        Assert.Equal(3, ((JArray)result["before"]!).Count);
        Assert.Equal(2, ((JArray)result["map"]!).Count);
        Assert.Equal(3, ((JArray)result["returned"]!).Count);
        foreach (var phase in new[] { "before", "map", "returned" })
        {
            long frame = (long)result[phase]!.Last!["FrameId"]!;
            var png = f.Inspection.Image(f.Id, frame);
            using var decoded = Cv2.ImDecode(png, ImreadModes.Unchanged);
            Assert.Equal(f.Pixels.Size(), decoded.Size());
            Assert.Throws<InvalidOperationException>(() => f.Inspection.Image("other-owner", frame));
        }
        Assert.False(f.Inspection.BlocksMovement);
        Assert.Throws<InvalidOperationException>(() => f.Start());
    }

    [Fact]
    public void MissingReleaseWrongPoseAndCancellationNeverAuthorizeAMapKey()
    {
        using var f = new Fixture();
        Assert.Throws<InvalidOperationException>(() => f.Inspection.Start(f.Id, true));
        f.Start();
        for (int i = 0; i < 6; i++) f.Frame(true, x: -858.7);
        f.Inspection.Cancel();
        Assert.Equal("cancelled", (string?)f.Result["phase"]);
        Assert.True(f.Inspection.BlocksMovement);
        Assert.Empty(f.Input.Keys);
        Assert.Throws<InvalidOperationException>(() => f.Start());
    }

    [Fact]
    public void EpochLossAfterOpenNeverClosesAnUnownedMap()
    {
        using var f = new Fixture();
        f.Start();
        f.WalkTo("awaitMap", true);
        f.Frame(false, epoch: new string('b', 32));
        Assert.Equal("failed", (string?)f.Result["phase"]);
        Assert.Equal("map_source_discontinuity", (string?)f.Result["reason"]);
        Assert.Equal(new[] { "M:down", "M:up" }, f.Input.Keys);
        Assert.True(f.Inspection.BlocksMovement);
    }

    [Fact]
    public void StaleFrameFromTheOpenKeyHoldClearsTheStreakAndWaitsForFreshMapEvidence()
    {
        using var f = new Fixture();
        f.Start();
        f.WalkTo("awaitMap", true);
        var open = f.Result["inputs"]![0]!;
        var duringHold = ((long)open["RequestedTicks"]! + (long)open["ReleasedTicks"]!) / 2;
        Thread.Sleep(130);
        f.Frame(false, reportedTicks: duringHold);
        Assert.Equal("awaitMap", (string?)f.Result["phase"]);
        Assert.Equal(1, (int?)f.Result["staleCandidates"]);
        Assert.Equal(new[] { "M:down", "M:up" }, f.Input.Keys);
        f.KnownMap = true;
        f.WalkTo("awaitWorld", false);
        f.WalkTo("completed", true);
        Assert.Equal(new[] { "M:down", "M:up", "ESCAPE:down", "ESCAPE:up" }, f.Input.Keys);
    }

    [Fact]
    public void SlowPositiveRecognitionCannotAuthorizeEscapeOrKeepItsPriorStreak()
    {
        using var f = new Fixture();
        f.Start(recovery: true);
        f.Frame(false);
        Assert.Single((JArray)f.Result["map"]!);
        f.RecognitionDelayMs = 175;
        f.Frame(false);
        Assert.Empty((JArray)f.Result["map"]!);
        Assert.Empty(f.Input.Keys);
        f.RecognitionDelayMs = 0;
        f.Frame(false);
        Assert.Empty(f.Input.Keys);
        f.Frame(false);
        f.WalkTo("completed", true);
        var result = f.Result;
        Assert.Equal("recovery", (string?)result["mode"]);
        Assert.Equal(new string('a',64), (string?)result["priorEvidenceSha256"]);
        Assert.Empty((JArray)result["before"]!);
        Assert.Equal(new[] { "ESCAPE:down", "ESCAPE:up" }, f.Input.Keys);
        Assert.Equal(12 * Stopwatch.Frequency, (long)result["deadlineTicks"]! - (long)result["startedTicks"]!);
    }

    [Fact]
    public void RecoveryCannotOpenAMapAndUnknownOrChangedSourceNeverAuthorizesEscape()
    {
        using var f = new Fixture();
        Assert.Throws<InvalidOperationException>(() => f.Inspection.Start(f.Id, true, true, "unbound"));
        f.Start(recovery: true);
        f.KnownMap = false;
        f.Frame(false);
        f.Frame(false);
        f.Frame(true);
        Assert.Empty(f.Input.Keys);
        Assert.Equal("awaitRecoveryMap", (string?)f.Result["phase"]);
        f.Frame(false, epoch: new string('b',32));
        Assert.Equal("failed", (string?)f.Result["phase"]);
        Assert.Equal("map_source_discontinuity", (string?)f.Result["reason"]);
        Assert.Empty(f.Input.Keys);
        Assert.True(f.Inspection.BlocksMovement);
    }

    [Fact]
    public async Task CancellationAfterMapDownReleasesTheOriginalKeyAndPrecludesEscape()
    {
        using var f = new Fixture();
        using var down = new ManualResetEventSlim();
        f.Input.OnOpenDown = down.Set;
        f.Start();
        var capture = Task.Run(() =>
        {
            for (int i = 0; i < 10 && f.Inspection.Pending; i++) f.Frame(true);
        });
        Assert.True(down.Wait(TimeSpan.FromSeconds(4)));
        f.Inspection.Cancel();
        await capture;
        Assert.Equal("cancelled", (string?)f.Result["phase"]);
        Assert.Equal(new[] { "M:down", "M:up" }, f.Input.Keys);
        Assert.True(f.Inspection.BlocksMovement);
    }

    [Fact]
    public void FencedOrdinaryProposalNeverDispatchesOrEarnsSuccessfulMapCredit()
    {
        using var f = new Fixture();
        f.Start();
        Assert.True(f.Inspection.RejectWalkingProposal());
        f.WalkTo("awaitMap", true);
        f.WalkTo("awaitWorld", false);
        f.WalkTo("failed", true);
        Assert.Equal(1, (int?)f.Result["ordinaryRequestsWhileFenced"]);
        Assert.Equal("map_unexpected_ordinary_proposal", (string?)f.Result["reason"]);
        Assert.Equal(new[] { "M:down", "M:up", "ESCAPE:down", "ESCAPE:up" }, f.Input.Keys);
    }

    /// <summary>Synthetic independent compositor and acquisition evidence on the actual process QPC clock.</summary>
    private sealed class Fixture : IDisposable
    {
        internal readonly string Id = Guid.NewGuid().ToString("N");
        internal readonly Mat Pixels = new(48, 64, MatType.CV_8UC3, new Scalar(40, 80, 120));
        internal readonly InertInput Input = new();
        internal readonly AgentMapInspection Inspection;
        internal bool KnownMap = true;
        internal int RecognitionDelayMs;
        private readonly long _origin = Stopwatch.GetTimestamp();
        private readonly AgentActionController _controller;
        private long _frame;
        internal JObject Result => JObject.FromObject(Inspection.Status(Id));
        internal Fixture()
        {
            _controller = new AgentActionController(Input, true, () => Stopwatch.GetElapsedTime(_origin).TotalMilliseconds,
                null, () => new AgentTrackedInputState([], Input.Telemetry.ExecutionUncertain, Input.Telemetry.ReleaseOutcome, false));
            Input.Telemetry.Sink = _controller.RecordInputCall;
            Inspection = new AgentMapInspection("session", "owner", _origin, _controller, Input, _ =>
            {
                if (RecognitionDelayMs != 0) Thread.Sleep(RecognitionDelayMs);
                return KnownMap;
            });
        }
        internal void Start(bool recovery = false)
        {
            _controller.Release(Stopwatch.GetElapsedTime(_origin).TotalMilliseconds);
            Inspection.Start(Id, true, recovery, recovery ? new string('a',64) : null);
        }
        internal void WalkTo(string phase, bool world)
        {
            for (int i = 0; i < 12 && (string?)Result["phase"] != phase; i++) Frame(world);
            Assert.True((string?)Result["phase"] == phase, Result.ToString());
        }
        internal void Frame(bool world, double x = -846.30078125, string epoch = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", int ageMs = 0, long? reportedTicks = null)
        {
            Thread.Sleep(85);
            var now = Stopwatch.GetTimestamp();
            long acquired = now - (long)(ageMs * Stopwatch.Frequency / 1000.0);
            double at = (acquired - _origin) * 1000.0 / Stopwatch.Frequency;
            var reported = reportedTicks ?? acquired;
            long stamp = (long)((Int128)reported * TimeSpan.TicksPerSecond / Stopwatch.Frequency);
            var src = new AgentSourceFrame(epoch, stamp, (reported - _origin) * 1000.0 / Stopwatch.Frequency, at);
            var obs = new AgentObservation(++_frame, (now - _origin) * 1000.0 / Stopwatch.Frequency,
                64, 48, world ? AgentWorldEvidence.WorldHud : AgentWorldEvidence.HudMissing, 1, src);
            var ready = _controller.RegisterFrame(obs, Stopwatch.GetElapsedTime(_origin).TotalMilliseconds);
            var pose = new AgentNavigationPose("valid", null, _frame, x, 2261.13671875, 10, .999, .6, "City_102",
                null, null, null, null, 1);
            Inspection.Observe(Pixels, obs, ready, new(AgentMotionStatus.Normal, "normal", "fake", 1, false, false), pose, default);
        }
        public void Dispose() => Pixels.Dispose();
    }

    /// <summary>Emits the actual telemetry event shapes without opening or controlling any window.</summary>
    private sealed class InertInput : IAgentInput, IMapInspectionInput
    {
        internal readonly List<string> Keys = [];
        internal Action? OnOpenDown;
        internal readonly AgentInputCallObserver Telemetry = new();
        public bool MapTargetReady => true;
        public int GameProcessId => 123;
        public long GameWindowHandle => 456;
        public bool IsAvailable => true;
        public void MapKey(bool open, bool down)
        {
            var key = open ? "M" : "ESCAPE";
            Telemetry.Invoke(down ? "keyDown" : "keyUp", key, 0, 0, () =>
            {
                Keys.Add(key + (down ? ":down" : ":up"));
                if (open && down) OnOpenDown?.Invoke();
            });
        }
        public void SetHeldKeys(string[] keys) => throw new InvalidOperationException();
        public void MoveMouse(int dx, int dy) => throw new InvalidOperationException();
        public void ReleaseAll() => Telemetry.Invoke("releaseAll", null, 0, 0, () => { }, "returned_unverified");
    }
}
