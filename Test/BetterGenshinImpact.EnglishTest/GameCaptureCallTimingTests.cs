using System.Diagnostics;
using System.Reflection;
using Fischless.GameCapture;
using Fischless.GameCapture.Graphics;
using Fischless.GameCapture.Graphics.Helpers;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Managed lock/return/exception diagnostics only; no WinRT session, game, or GPU is started.</summary>
public sealed class GameCaptureCallTimingTests
{
    /// <summary>Access existing locks without introducing a callback or injectable native work into production.</summary>
    private static object Field(GraphicsCaptureV2 capture, string name) =>
        typeof(GraphicsCaptureV2).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(capture)!;

    /// <summary>A stopped source remains null and receives no fabricated pool/render/source evidence.</summary>
    [Fact]
    public void StoppedCaptureHasCompleteLocalTraceAndUnchangedOrdinaryResult()
    {
        using var capture = new GraphicsCaptureV2();
        Assert.Null(capture.Capture());
        Assert.Null(((IGameCaptureDiagnostics)capture).Capture(out var timing));
        Assert.Equal(1, timing.Version);
        Assert.Equal(Stopwatch.Frequency, timing.ClockFrequency);
        Assert.Equal("null", timing.Outcome);
        Assert.Equal("not_called", timing.PoolResult);
        Assert.True(timing.StartedAtTicks <= timing.CaptureGateAcquiredAtTicks);
        Assert.True(timing.CaptureGateAcquiredAtTicks <= timing.StateLockAcquiredAtTicks);
        Assert.True(timing.StateLockAcquiredAtTicks <= timing.CompletedAtTicks);
        Assert.Null(timing.PoolStartedAtTicks);
        Assert.Null(timing.RenderStartedAtTicks);
        Assert.Null(timing.ReturnedSource);
    }

    /// <summary>A controlled active generation with no pool follows the ordinary empty-frame path.</summary>
    [Fact]
    public void EmptyPoolRecordsOnlyEnteredStages()
    {
        using var capture = new GraphicsCaptureV2();
        typeof(GraphicsCaptureV2).GetField("_generation", BindingFlags.Instance | BindingFlags.NonPublic)!
            .SetValue(capture, new WgcCaptureGeneration());
        typeof(GraphicsCaptureV2).GetProperty(nameof(GraphicsCaptureV2.IsCapturing))!.SetValue(capture, true);
        Assert.Null(capture.Capture(out var timing));
        Assert.Equal("empty", timing.PoolResult);
        Assert.True(timing.StateLockAcquiredAtTicks <= timing.PoolStartedAtTicks);
        Assert.True(timing.PoolStartedAtTicks <= timing.PoolCompletedAtTicks);
        Assert.True(timing.PoolCompletedAtTicks <= timing.CompletedAtTicks);
        Assert.Null(timing.AcquiredSource);
        Assert.Null(timing.SubmitStartedAtTicks);
        Assert.Null(timing.ReadbackMapStartedAtTicks);
    }

    /// <summary>Each real lock wait is separately visible before release; completion never leaks a shared last-call record.</summary>
    [Theory]
    [InlineData("_captureGate")]
    [InlineData("_lock")]
    public async Task LockWaitClocksAreInvocationLocal(string field)
    {
        using var capture = new GraphicsCaptureV2();
        GameCaptureCallTiming? timing = null;
        Task worker;
        lock (Field(capture, field))
        {
            worker = Task.Run(() => Assert.Null(capture.Capture(out timing)));
            Assert.True(SpinWait.SpinUntil(() => Volatile.Read(ref timing) is not null
                && (field == "_captureGate" || timing.CaptureGateAcquiredAtTicks is not null), TimeSpan.FromSeconds(5)));
            Assert.False(worker.IsCompleted);
            Assert.Equal(0, timing!.CompletedAtTicks);
            if (field == "_captureGate") Assert.Null(timing.CaptureGateAcquiredAtTicks);
            Assert.Null(timing.StateLockAcquiredAtTicks);
        }
        await worker.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.True(timing!.StartedAtTicks <= timing.CaptureGateAcquiredAtTicks);
        Assert.True(timing.CaptureGateAcquiredAtTicks <= timing.StateLockAcquiredAtTicks);
        Assert.True(timing.StateLockAcquiredAtTicks <= timing.CompletedAtTicks);
        capture.Capture(out var second);
        Assert.NotSame(timing, second);
        Assert.True(second.StartedAtTicks >= timing.CompletedAtTicks);
    }

    /// <summary>An exceptional completion retains the same exception and the already-assigned out record.</summary>
    [Fact]
    public void ThrowCompletesTraceWithoutReplacingTheFailure()
    {
        var expected = new InvalidOperationException("fixture");
        GameCaptureCallTiming timing = null!;
        var actual = Assert.Throws<InvalidOperationException>(() => GameCaptureCallTiming.Run(trace =>
        {
            trace.LastStage = "submit";
            throw expected;
        }, out timing));
        Assert.Same(expected, actual);
        Assert.Equal("threw", timing.Outcome);
        Assert.Equal("submit", timing.FailureStage);
        Assert.Equal(nameof(InvalidOperationException), timing.ExceptionType);
        Assert.True(timing.CompletedAtTicks >= timing.StartedAtTicks);
    }

    /// <summary>A returned cached frame retains exact source identity and caller ownership despite a rejected new acquisition.</summary>
    [Fact]
    public void CachedPublicationDoesNotRestampOrDisposeReturnedPixels()
    {
        var source = new GameCaptureSourceInfo(Guid.NewGuid(), 1000, 2000);
        using var frame = new GameCaptureFrame(new Mat(2, 2, MatType.CV_8UC3, Scalar.All(30)), null, source);
        var returned = GameCaptureCallTiming.Run(trace =>
        {
            trace.CacheHit = true;
            trace.PoolResult = "rejected_identity";
            trace.LastStage = "render";
            trace.RecordFailure(new InvalidOperationException("an intentionally unretained message"));
            trace.LastStage = "cleanup";
            return frame;
        }, out var timing);
        Assert.Same(frame, returned);
        Assert.False(frame.Frame.IsDisposed);
        Assert.Same(source, timing.ReturnedSource);
        Assert.Equal(2000, timing.ReturnedSource!.AcquiredAtStopwatchTicks);
        Assert.Null(timing.AcquiredSource);
        Assert.Equal("frame", timing.Outcome);
        Assert.Equal("render", timing.FailureStage);
    }
}
