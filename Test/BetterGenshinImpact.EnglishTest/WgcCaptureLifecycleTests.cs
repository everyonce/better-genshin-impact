using System.Reflection;
using Fischless.GameCapture;
using Fischless.GameCapture.Graphics;
using Fischless.GameCapture.Graphics.Helpers;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercises V2 ownership with managed pumps and CPU Mats; no native capture session is created.</summary>
public sealed class WgcCaptureLifecycleTests
{
    /// <summary>Reflection installs controlled state without invoking WinRT or a game window.</summary>
    private static void SetField(GraphicsCaptureV2 capture, string name, object? value) =>
        typeof(GraphicsCaptureV2).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(capture, value);

    /// <summary>Reads ownership state without exposing test-only mutable production properties.</summary>
    private static object? GetField(GraphicsCaptureV2 capture, string name) =>
        typeof(GraphicsCaptureV2).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(capture);

    /// <summary>Marks the controlled fixture active without creating any WinRT resources.</summary>
    private static void MarkCapturing(GraphicsCaptureV2 capture) =>
        typeof(GraphicsCaptureV2).GetProperty(nameof(GraphicsCaptureV2.IsCapturing))!.SetValue(capture, true);

    /// <summary>Stop keeps pixel resources alive while a timed-out operation still owns the session.</summary>
    [Fact]
    public async Task StopDefersDisposalAndBlocksRestartUntilOperationCompletes()
    {
        using var capture = new GraphicsCaptureV2();
        var pump = new WgcCapturePump();
        var generation = new WgcCaptureGeneration();
        using var cached = new Mat(2, 2, MatType.CV_8UC3, Scalar.All(30));
        using var release = new ManualResetEventSlim();
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        SetField(capture, "_wgcPump", pump);
        SetField(capture, "_generation", generation);
        SetField(capture, "_cachedBgr", cached);
        MarkCapturing(capture);
        try
        {
            var dispatch = Task.Run(() => pump.Run(() => { started.SetResult(); release.Wait(); }, TimeSpan.FromMilliseconds(100)));
            await started.Task.WaitAsync(TimeSpan.FromSeconds(10));
            await Assert.ThrowsAsync<TimeoutException>(() => dispatch);
            capture.Stop();
            Assert.False(capture.IsCapturing);
            Assert.False(generation.IsActive);
            Assert.False(cached.IsDisposed);
            Assert.Null(capture.Capture());
            // The retirement guard fires before any Win32/WinRT startup work, even with an invalid HWND.
            var error = Assert.Throws<InvalidOperationException>(() => capture.Start(IntPtr.Zero));
            Assert.Contains("still retiring", error.Message);
            Assert.False(cached.IsDisposed);
            var retirement = Assert.IsAssignableFrom<Task>(GetField(capture, "_pumpRetirement"));
            release.Set();
            await retirement.WaitAsync(TimeSpan.FromSeconds(10));
            Assert.True(cached.IsDisposed);
            capture.Stop();
            Assert.Null(GetField(capture, "_wgcPump"));
        }
        finally
        {
            release.Set();
            await pump.Retire(() => { }).WaitAsync(TimeSpan.FromSeconds(10));
        }
    }

    /// <summary>A close queued by an old generation cannot stop a replacement generation.</summary>
    [Fact]
    public void DelayedCloseCannotStopReplacementGeneration()
    {
        using var capture = new GraphicsCaptureV2();
        var previous = new WgcCaptureGeneration();
        var replacement = new WgcCaptureGeneration();
        previous.Deactivate();
        SetField(capture, "_generation", replacement);
        MarkCapturing(capture);
        capture.StopGeneration(previous);
        Assert.True(capture.IsCapturing);
        Assert.True(replacement.IsActive);
        Assert.Same(replacement, GetField(capture, "_generation"));
        capture.StopGeneration(replacement);
        Assert.False(capture.IsCapturing);
        Assert.False(replacement.IsActive);
    }

    /// <summary>Resize/failure clears publishable pixels without renewing a previously acquired source.</summary>
    [Fact]
    public void PublicationInvalidationRetainsSourceHighWaterMark()
    {
        using var capture = new GraphicsCaptureV2();
        var generation = new WgcCaptureGeneration();
        var source = generation.TryAcquire(1000, 2000);
        Assert.NotNull(source);
        SetField(capture, "_generation", generation);
        SetField(capture, "_gpuFrameTs", 1000L);
        SetField(capture, "_cachedFrameTs", 1000L);
        SetField(capture, "_gpuSourceInfo", source);
        SetField(capture, "_cachedSourceInfo", source);
        typeof(GraphicsCaptureV2).GetMethod("InvalidatePublishedFrames", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(capture, null);
        Assert.Equal(0L, GetField(capture, "_gpuFrameTs"));
        Assert.Equal(0L, GetField(capture, "_cachedFrameTs"));
        Assert.Null(GetField(capture, "_gpuSourceInfo"));
        Assert.Null(GetField(capture, "_cachedSourceInfo"));
        Assert.Null(generation.TryAcquire(1000, 9000));
        Assert.Null(generation.TryAcquire(999, 9001));
        var next = generation.TryAcquire(1001, 9002);
        Assert.NotNull(next);
        Assert.Equal(source.CaptureEpoch, next.CaptureEpoch);
        Assert.Equal(2000, source.AcquiredAtStopwatchTicks);
    }

    /// <summary>Each Start gets a new epoch, while stop rejects both arrivals and acquisition.</summary>
    [Fact]
    public void GenerationLifetimeNeverReusesEpochOrFirstAcquisition()
    {
        var first = new WgcCaptureGeneration();
        var second = new WgcCaptureGeneration();
        var source = first.TryAcquire(1000, 2000);
        first.SignalArrival();
        Assert.Equal(1, first.Arrivals);
        Assert.Null(first.TryAcquire(1000, 3000));
        Assert.True(first.Deactivate());
        Assert.False(first.Deactivate());
        first.SignalArrival();
        Assert.Equal(1, first.Arrivals);
        Assert.Null(first.TryAcquire(1001, 4000));
        var restarted = second.TryAcquire(1000, 5000);
        Assert.NotNull(restarted);
        Assert.NotEqual(source!.CaptureEpoch, restarted.CaptureEpoch);
        Assert.Equal(2000, source.AcquiredAtStopwatchTicks);
    }

    /// <summary>Retained images share immutable timing metadata while owning independent CPU pixels.</summary>
    [Fact]
    public void RepeatedCachedFramesKeepExactSourceIdentity()
    {
        var generation = new WgcCaptureGeneration();
        var source = generation.TryAcquire(1000, 2000);
        using var first = new GameCaptureFrame(new Mat(2, 2, MatType.CV_8UC3, Scalar.All(30)), null, source);
        using var cached = new GameCaptureFrame(first.Frame.Clone(), first.CaptureRect, first.SourceInfo);
        Assert.Same(first.SourceInfo, cached.SourceInfo);
        Assert.Null(generation.TryAcquire(1000, 3000));
        first.Frame.SetTo(Scalar.All(60));
        Assert.Equal(30, cached.Frame.At<Vec3b>(0, 0).Item0);
    }
}
