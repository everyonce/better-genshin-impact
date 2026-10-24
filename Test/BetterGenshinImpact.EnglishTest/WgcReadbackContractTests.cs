using System.Reflection;
using Fischless.GameCapture;
using Fischless.GameCapture.Graphics;
using Fischless.GameCapture.Graphics.Helpers;
using OpenCvSharp;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Public result/mode and actual stopped/empty-backend contracts; no native capture or GPU is initialized.</summary>
public sealed class WgcReadbackContractTests
{
    /// <summary>Set controlled managed lifecycle fields without introducing native test hooks.</summary>
    private static void SetField(GraphicsCaptureV2 capture, string name, object? value) =>
        typeof(GraphicsCaptureV2).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(capture, value);

    /// <summary>Missing selection and the exact legacy string preserve Blocking.</summary>
    [Fact]
    public void ModeDefaultIsBlockingAndExplicitSelectionIsExact()
    {
        Assert.Equal(GameCaptureReadbackMode.Blocking, WgcReadbackSlot.ReadMode(null));
        Assert.Equal(GameCaptureReadbackMode.Blocking, WgcReadbackSlot.ReadMode(new()));
        Assert.Equal(GameCaptureReadbackMode.Blocking, WgcReadbackSlot.ReadMode(new() { ["ReadbackMode"] = "blocking" }));
        Assert.Equal(GameCaptureReadbackMode.PollSingleV1, WgcReadbackSlot.ReadMode(new() { ["ReadbackMode"] = "poll_single_v1" }));
    }

    /// <summary>No case-folding, enum coercion, null fallback or unknown future mode is silently admitted.</summary>
    [Theory]
    [InlineData(null)]
    [InlineData(1)]
    [InlineData("")]
    [InlineData("Blocking")]
    [InlineData("poll_single_v2")]
    [InlineData(" poll_single_v1")]
    public void InvalidModeFailsBeforeNativeStart(object? value) =>
        Assert.Throws<ArgumentException>(() => WgcReadbackSlot.ReadMode(new() { ["ReadbackMode"] = value! }));

    /// <summary>Default and malformed results cannot masquerade as pixels or a pending source.</summary>
    [Fact]
    public void ResultEnforcesOutcomeOwnership()
    {
        var source = new GameCaptureSourceInfo(Guid.NewGuid(), 100, 200);
        var pending = new GameCapturePendingReadback(1, source, 210, 2, 2, null);
        Assert.Equal(GameCaptureAttemptOutcome.Unavailable, default(GameCaptureAttempt).Outcome);
        Assert.Null(default(GameCaptureAttempt).Frame);
        Assert.Throws<ArgumentException>(() => new GameCaptureAttempt(GameCaptureAttemptOutcome.FrameReady));
        Assert.Throws<ArgumentException>(() => new GameCaptureAttempt(GameCaptureAttemptOutcome.ReadbackPending));
        Assert.Throws<ArgumentException>(() => new GameCaptureAttempt(GameCaptureAttemptOutcome.Unavailable, pending: pending));
        Assert.Throws<ArgumentException>(() => new GameCaptureAttempt((GameCaptureAttemptOutcome)99));
    }

    /// <summary>Completing A while refilling B returns A's exact geometry/source, never B's identity on old pixels.</summary>
    [Fact]
    public void ReadyFrameAndRefillHaveDistinctImmutableIdentity()
    {
        var epoch = Guid.NewGuid();
        var sourceA = new GameCaptureSourceInfo(epoch, 100, 200);
        var sourceB = new GameCaptureSourceInfo(epoch, 101, 220);
        var rectA = new RECT(10, 20, 12, 22);
        using var frame = new GameCaptureFrame(new Mat(2, 2, MatType.CV_8UC3, Scalar.All(17)), rectA, sourceA);
        var pendingB = new GameCapturePendingReadback(2, sourceB, 230, 2, 2, new RECT(11, 21, 13, 23));
        var actual = GameCaptureCallTiming.RunAttempt(_ => new(GameCaptureAttemptOutcome.FrameReady, frame, pendingB), out var timing);
        Assert.Equal(GameCaptureAttemptOutcome.FrameReady, actual.Outcome);
        Assert.Same(frame, actual.Frame);
        Assert.Equal(rectA, actual.Frame!.CaptureRect);
        Assert.Same(sourceA, timing.ReturnedSource);
        Assert.Same(pendingB, timing.PendingReadback);
        Assert.Equal("frame_ready", timing.ReadbackOutcome);
        Assert.False(frame.Frame.IsDisposed);
    }

    /// <summary>Busy diagnostics are explicitly pending, with no returned or cached pixel identity.</summary>
    [Fact]
    public void PendingTimingDoesNotClaimFrameOrLoseDescriptor()
    {
        var pending = new GameCapturePendingReadback(1, new(Guid.NewGuid(), 100, 200), 210, 2, 2, null);
        var result = GameCaptureCallTiming.RunAttempt(_ => new(GameCaptureAttemptOutcome.ReadbackPending, pending: pending), out var timing);
        Assert.Equal(GameCaptureAttemptOutcome.ReadbackPending, result.Outcome);
        Assert.Null(result.Frame);
        Assert.Null(timing.ReturnedSource);
        Assert.Same(pending, timing.PendingReadback);
        Assert.Equal("null", timing.Outcome);
        Assert.Equal("poll_single_v1", timing.ReadbackMode);
        Assert.Equal("readback_pending", timing.ReadbackOutcome);
        Assert.True(timing.CompletedAtTicks >= timing.StartedAtTicks);
    }

    /// <summary>Invocation-local diagnostic failures preserve the original exception and close their clock interval.</summary>
    [Fact]
    public void ExceptionalTimingPreservesFailureIdentity()
    {
        var expected = new InvalidOperationException("fixture");
        GameCaptureCallTiming timing = null!;
        Action run = () => GameCaptureCallTiming.RunAttempt(trace =>
        {
            trace.LastStage = "readback_map";
            throw expected;
        }, out timing);
        Assert.Same(expected, Assert.Throws<InvalidOperationException>(run));
        Assert.Equal("readback_map", timing.FailureStage);
        Assert.Equal("threw", timing.Outcome);
        Assert.True(timing.CompletedAtTicks >= timing.StartedAtTicks);
    }

    /// <summary>The actual stopped entrypoints agree, do not allocate native work, and preserve legacy timing fields.</summary>
    [Theory]
    [InlineData(GameCaptureReadbackMode.Blocking)]
    [InlineData(GameCaptureReadbackMode.PollSingleV1)]
    public void StoppedEntryPointsAreEquivalent(GameCaptureReadbackMode mode)
    {
        using var capture = new GraphicsCaptureV2();
        typeof(GraphicsCaptureV2).GetProperty(nameof(GraphicsCaptureV2.ReadbackMode))!.SetValue(capture, mode);
        Assert.Null(capture.Capture());
        Assert.Null(capture.Capture(out var legacy));
        Assert.Equal(GameCaptureAttemptOutcome.Unavailable, capture.CaptureAttempt().Outcome);
        Assert.Equal(GameCaptureAttemptOutcome.Unavailable, capture.CaptureAttempt(out var typed).Outcome);
        Assert.Equal("null", legacy.Outcome);
        Assert.Equal("null", typed.Outcome);
        Assert.Null(typed.PolledReadback);
        Assert.Null(typed.FlushStartedAtTicks);
        Assert.Null(typed.ReadbackMapStartedAtTicks);
        Assert.Equal(mode == GameCaptureReadbackMode.Blocking ? null : "poll_single_v1", typed.ReadbackMode);
    }

    /// <summary>An admitted generation with no pool remains unavailable and drains the per-call active count.</summary>
    [Fact]
    public void EmptyPoolAndPendingStopNeverRetainAnActiveCaller()
    {
        using var capture = new GraphicsCaptureV2();
        var generation = new WgcCaptureGeneration();
        var slot = new WgcReadbackSlot(generation.Epoch);
        typeof(GraphicsCaptureV2).GetProperty(nameof(GraphicsCaptureV2.ReadbackMode))!.SetValue(capture, GameCaptureReadbackMode.PollSingleV1);
        typeof(GraphicsCaptureV2).GetProperty(nameof(GraphicsCaptureV2.IsCapturing))!.SetValue(capture, true);
        SetField(capture, "_generation", generation);
        SetField(capture, "_readbackSlot", slot);
        Assert.Equal(GameCaptureAttemptOutcome.Unavailable, capture.CaptureAttempt(out var timing).Outcome);
        Assert.Equal("empty", timing.PoolResult);
        Assert.Equal(0, (int)typeof(GraphicsCaptureV2).GetField("_activeCaptures", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(capture)!);
        slot.Begin(new(generation.Epoch, 100, 200), 210, 2, 2, null);
        capture.Stop();
        Assert.True(slot.IsStopped);
        Assert.Null(slot.Pending);
        Assert.Equal(GameCaptureAttemptOutcome.Unavailable, capture.CaptureAttempt().Outcome);
    }

    /// <summary>An interrupted waiter has no authority to invalidate another caller's pending slot or cached source.</summary>
    [Fact]
    public void InterruptedWaiterDoesNotMutateExistingLifetime()
    {
        using var capture = new GraphicsCaptureV2();
        var generation = new WgcCaptureGeneration();
        var source = generation.TryAcquire(100, 200)!;
        var slot = new WgcReadbackSlot(generation.Epoch);
        var pending = slot.Begin(source, 210, 2, 2, null);
        typeof(GraphicsCaptureV2).GetProperty(nameof(GraphicsCaptureV2.ReadbackMode))!.SetValue(capture, GameCaptureReadbackMode.PollSingleV1);
        typeof(GraphicsCaptureV2).GetProperty(nameof(GraphicsCaptureV2.IsCapturing))!.SetValue(capture, true);
        SetField(capture, "_generation", generation);
        SetField(capture, "_readbackSlot", slot);
        SetField(capture, "_cachedSourceInfo", source);
        SetField(capture, "_cachedFrameTs", 100L);
        SetField(capture, "_gpuSourceInfo", source);
        SetField(capture, "_gpuFrameTs", 100L);
        var gate = typeof(GraphicsCaptureV2).GetField("_captureGate", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(capture)!;
        GameCaptureCallTiming? timing = null;
        Exception? failure = null;
        GameCaptureAttempt result = default;
        var worker = new Thread(() =>
        {
            try { result = capture.CaptureAttempt(out timing); }
            catch (Exception error) { failure = error; }
        }) { IsBackground = true };
        lock (gate)
        {
            worker.Start();
            Assert.True(SpinWait.SpinUntil(() => Volatile.Read(ref timing)?.CaptureGateContended == true, TimeSpan.FromSeconds(5)));
            worker.Interrupt();
            Assert.True(worker.Join(TimeSpan.FromSeconds(5)));
            Assert.True(Monitor.IsEntered(gate));
            Assert.Same(pending, slot.Pending);
            Assert.False(slot.IsFaulted);
            Assert.Same(source, typeof(GraphicsCaptureV2).GetField("_cachedSourceInfo", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(capture));
            Assert.Equal(100L, typeof(GraphicsCaptureV2).GetField("_gpuFrameTs", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(capture));
        }
        Assert.Null(failure);
        Assert.Equal(GameCaptureAttemptOutcome.Unavailable, result.Outcome);
        Assert.Equal(nameof(ThreadInterruptedException), timing!.ExceptionType);
        Assert.Equal(0, (int)typeof(GraphicsCaptureV2).GetField("_activeCaptures", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(capture)!);
        Assert.Null(generation.TryAcquire(100, 999));
    }
}
