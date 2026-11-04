using System.Reflection;
using Fischless.GameCapture.DwmSharedSurface;
using Fischless.GameCapture.Graphics.Helpers;
using SharpDX;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercises production device/staging ownership with managed fakes; no GPU, GDI or window capture is started.</summary>
public sealed class SharedSurfaceResourceTests
{
    /// <summary>Same-size staging must be recreated against the replacement device, never reused across generations.</summary>
    [Fact]
    public void SameSizeRecoveryDisposesOldStagingBeforeReplacingDevice()
    {
        var events = new List<string>();
        var generation = 0;
        using var resources = new SharedSurfaceResources<FakeDevice, FakeStaging>(() =>
        {
            var next = ++generation;
            events.Add($"create_device_{next}");
            return new FakeDevice(next, events);
        });
        resources.ResetDevice();
        var firstDevice = resources.Device!;
        var first = resources.GetOrCreateStaging(device => new FakeStaging(device, 1920, 1080, events));
        Assert.Same(first, resources.GetOrCreateStaging(_ => throw new Exception("unexpected allocation")));
        resources.ResetDevice();
        Assert.Equal(new[] { "create_device_1", "dispose_staging_1", "dispose_device_1", "create_device_2" }, events);
        Assert.Null(resources.Staging);
        var second = resources.GetOrCreateStaging(device => new FakeStaging(device, 1920, 1080, events));
        Assert.NotSame(first, second);
        Assert.NotSame(firstDevice, second.Device);
        Assert.Same(resources.Device, second.Device);
        Assert.Equal((1920, 1080), (second.Width, second.Height));
        Assert.Equal(1, first.DisposeCount);
        Assert.Equal(1, firstDevice.DisposeCount);
    }

    /// <summary>Repeated device failures each retire exactly their own device and staging pair.</summary>
    [Fact]
    public void RepeatedRecoveryAndStopStartReleaseEveryGenerationOnce()
    {
        var events = new List<string>();
        var devices = new List<FakeDevice>();
        var stages = new List<FakeStaging>();
        using var resources = new SharedSurfaceResources<FakeDevice, FakeStaging>(() =>
        {
            var device = new FakeDevice(devices.Count + 1, events);
            devices.Add(device);
            return device;
        });
        for (var i = 0; i < 10; i++)
        {
            resources.ResetDevice();
            stages.Add(resources.GetOrCreateStaging(device => new FakeStaging(device, 1920, 1080, events)));
            if (i % 2 == 0)
            {
                resources.Dispose();
                resources.Dispose();
                Assert.Null(resources.Device);
                Assert.Null(resources.Staging);
            }
        }
        resources.Dispose();
        Assert.All(devices, device => Assert.Equal(1, device.DisposeCount));
        Assert.All(stages, staging => Assert.Equal(1, staging.DisposeCount));
    }

    /// <summary>Failed replacement leaves no disposed reference and a later explicit restart can recover.</summary>
    [Fact]
    public void FailedReplacementLeavesNoDeviceOrStagingAndCanRestart()
    {
        var events = new List<string>();
        var attempts = 0;
        using var resources = new SharedSurfaceResources<FakeDevice, FakeStaging>(() =>
            ++attempts == 2 ? throw new InvalidOperationException("fake device creation failure") : new FakeDevice(attempts, events));
        resources.ResetDevice();
        var oldDevice = resources.Device!;
        var oldStage = resources.GetOrCreateStaging(device => new FakeStaging(device, 1920, 1080, events));
        Assert.Throws<InvalidOperationException>(resources.ResetDevice);
        Assert.Null(resources.Device);
        Assert.Null(resources.Staging);
        Assert.Throws<InvalidOperationException>(() => resources.GetOrCreateStaging(_ => throw new Exception("unreachable")));
        Assert.Equal(1, oldDevice.DisposeCount);
        Assert.Equal(1, oldStage.DisposeCount);
        resources.ResetDevice();
        Assert.Equal(3, resources.Device!.Generation);
        Assert.Null(resources.Staging);
    }

    /// <summary>A failing dependency release still releases its device, detaches both references and blocks replacement.</summary>
    [Fact]
    public void StagingDisposalFailureStillReleasesDeviceWithoutRetryingDisposedOwners()
    {
        var events = new List<string>();
        var created = 0;
        using var resources = new SharedSurfaceResources<FakeDevice, FakeStaging>(() => new FakeDevice(++created, events));
        resources.ResetDevice();
        var device = resources.Device!;
        var stage = resources.GetOrCreateStaging(current => new FakeStaging(current, 1920, 1080, events, true));
        Assert.Throws<InvalidOperationException>(resources.ResetDevice);
        Assert.Null(resources.Device);
        Assert.Null(resources.Staging);
        resources.Dispose();
        Assert.Equal(1, created);
        Assert.Equal(1, device.DisposeCount);
        Assert.Equal(1, stage.DisposeCount);
    }

    /// <summary>Resize failure cannot leave the old disposed staging reference published.</summary>
    [Fact]
    public void FailedStagingReplacementLeavesDeviceAvailableAndStagingAbsent()
    {
        var events = new List<string>();
        using var resources = new SharedSurfaceResources<FakeDevice, FakeStaging>(() => new FakeDevice(1, events));
        resources.ResetDevice();
        var device = resources.Device!;
        var previous = resources.GetOrCreateStaging(current => new FakeStaging(current, 1920, 1080, events));
        resources.ClearStaging();
        Assert.Throws<InvalidOperationException>(() => resources.GetOrCreateStaging(_ => throw new InvalidOperationException("fake staging allocation failure")));
        Assert.Null(resources.Staging);
        Assert.Same(device, resources.Device);
        Assert.Equal(0, device.DisposeCount);
        Assert.Equal(1, previous.DisposeCount);
        var replacement = resources.GetOrCreateStaging(current => new FakeStaging(current, 1280, 720, events));
        Assert.Same(device, replacement.Device);
    }

    /// <summary>Only opted-in SharpDX failures propagate; OpenCV/general failures and legacy callers retain null-on-failure behavior.</summary>
    [Fact]
    public void RecoveryErrorFilterPropagatesOnlyOptedInSharpDxFailures()
    {
        var gpuError = new SharpDXException(Result.Fail);
        Assert.False(Texture2DExtensions.ShouldSuppressFailure(gpuError, true));
        Assert.True(Texture2DExtensions.ShouldSuppressFailure(gpuError, false));
        Assert.True(Texture2DExtensions.ShouldSuppressFailure(new InvalidOperationException("non-GPU failure"), true));
        Assert.True(Texture2DExtensions.ShouldSuppressFailure(new InvalidOperationException("non-GPU failure"), false));
    }

    /// <summary>Stop takes the capture's existing lifecycle lock and clears its state without opening native resources.</summary>
    [Fact]
    public async Task StopWaitsForCaptureLockAndIsIdempotentWithoutNativeResources()
    {
        using var capture = new SharedSurfaceCapture();
        var gate = typeof(SharedSurfaceCapture).GetField("LockObject", BindingFlags.Static | BindingFlags.NonPublic)!.GetValue(null)!;
        using var held = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        var holder = Task.Run(() => { lock (gate) { held.Set(); release.Wait(); } });
        Task? stopping = null;
        try
        {
            Assert.True(held.Wait(TimeSpan.FromSeconds(5)));
            stopping = Task.Run(capture.Stop);
            await Task.Delay(30);
            Assert.False(stopping.IsCompleted);
        }
        finally
        {
            release.Set();
            await holder.WaitAsync(TimeSpan.FromSeconds(5));
            if (stopping is not null) await stopping.WaitAsync(TimeSpan.FromSeconds(5));
        }
        capture.Stop();
        Assert.False(capture.IsCapturing);
        Assert.Null(capture.Capture());
    }

    /// <summary>Managed device identity and disposal accounting.</summary>
    private sealed class FakeDevice(int generation, List<string> events) : IDisposable
    {
        /// <summary>Distinguishes equal-sized resources from different device lifetimes.</summary>
        internal int Generation { get; } = generation;
        /// <summary>Counts cleanup attempts.</summary>
        internal int DisposeCount { get; private set; }
        /// <summary>Records device cleanup order.</summary>
        public void Dispose() { DisposeCount++; events.Add($"dispose_device_{Generation}"); }
    }

    /// <summary>Managed staging identity tied to its device, with controllable cleanup failure.</summary>
    private sealed class FakeStaging(FakeDevice device, int width, int height, List<string> events, bool throwOnDispose = false) : IDisposable
    {
        /// <summary>Device which created this staging resource.</summary>
        internal FakeDevice Device { get; } = device;
        /// <summary>Retains width independently from device identity.</summary>
        internal int Width { get; } = width;
        /// <summary>Retains height independently from device identity.</summary>
        internal int Height { get; } = height;
        /// <summary>Counts cleanup attempts.</summary>
        internal int DisposeCount { get; private set; }
        /// <summary>Records dependency cleanup order and optionally simulates failure.</summary>
        public void Dispose()
        {
            DisposeCount++;
            events.Add($"dispose_staging_{Device.Generation}");
            if (throwOnDispose) throw new InvalidOperationException("fake staging disposal failure");
        }
    }
}
