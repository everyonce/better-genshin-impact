using System.Reflection;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Mask;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Model;
using BetterGenshinImpact.GameTask.Model.Area;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using Fischless.GameCapture;
using Fischless.GameCapture.Graphics.Helpers;
using Microsoft.Extensions.Logging.Abstractions;
using OpenCvSharp;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Real OpenCV and WGC recycler ownership, without a capture session, App, native window or input.</summary>
public sealed class DispatcherCaptureOwnershipTests
{
    /// <summary>Native pixels transfer to content; oversized pixels recycle after resize while independent content remains valid.</summary>
    [Theory]
    [InlineData(1920, 1080, 1920, 1080, false)]
    [InlineData(2560, 1440, 1920, 1080, true)]
    [InlineData(3440, 1440, 2580, 1080, true)]
    public void SuccessfulContentTransferAndRepeatedDisposalRecycleExactlyOnce(
        int width, int height, int outputWidth, int outputHeight, bool resized)
    {
        using var owner = new Mat(height, width, MatType.CV_8UC3, Scalar.All(37));
        var recycled = 0;
        using var frame = new GameCaptureFrame(WgcBgrMat.CreateFrom(owner, returned =>
        {
            Assert.Same(owner, returned); Assert.False(returned.IsDisposed); recycled++;
        }));
        var info = new FakeSystemInfo(new RECT(0, 0, width, height), 1);
        using var content = new CaptureContent(frame.Frame, 0, 50, info);
        var pixels = content.CaptureRectArea.SrcMat;
        var grey = content.CaptureRectArea.CacheGreyMat;
        Assert.Equal(outputWidth, pixels.Width); Assert.Equal(outputHeight, pixels.Height);
        Assert.Equal(resized ? 1 : 0, recycled);
        Assert.Equal(resized, frame.Frame.IsDisposed);
        Assert.False(pixels.IsDisposed); Assert.False(grey.IsDisposed);
        Assert.Equal(new Vec3b(37, 37, 37), pixels.At<Vec3b>(0, 0));
        Assert.Equal((byte)37, grey.At<byte>(0, 0));
        if (resized)
        {
            // Simulate the capture pool reusing the returned source before resized content finishes.
            owner.SetTo(Scalar.All(91));
            Assert.Equal(new Vec3b(37, 37, 37), pixels.At<Vec3b>(0, 0));
        }

        content.Dispose();
        Assert.True(pixels.IsDisposed); Assert.True(grey.IsDisposed);
        Assert.Equal(1, recycled); Assert.False(owner.IsDisposed);
        frame.Dispose(); content.Dispose(); frame.Dispose();
        Assert.Equal(1, recycled); Assert.False(owner.IsDisposed);
    }

    /// <summary>Normal returns and trigger-body exceptions unwind content before the enclosing frame, without duplicate pool returns.</summary>
    [Theory]
    [InlineData(1920, 1080, false)]
    [InlineData(1920, 1080, true)]
    [InlineData(2560, 1440, false)]
    [InlineData(2560, 1440, true)]
    public void ContentAndFrameScopesReleaseNativePixelsOnBodyExit(int width, int height, bool failBody)
    {
        using var owner = new Mat(height, width, MatType.CV_8UC3, Scalar.All(19));
        var recycled = 0;
        using var frame = new GameCaptureFrame(WgcBgrMat.CreateFrom(owner, returned =>
        {
            Assert.Same(owner, returned); recycled++;
        }));
        var info = new FakeSystemInfo(new RECT(0, 0, width, height), 1);
        Mat? pixels = null, grey = null;
        void Consume()
        {
            using var captured = frame;
            using var content = new CaptureContent(captured.Frame, 0, 50, info);
            pixels = content.CaptureRectArea.SrcMat;
            grey = content.CaptureRectArea.CacheGreyMat;
            if (failBody) throw new InvalidOperationException("synthetic_trigger_failure");
        }
        if (failBody) Assert.Throws<InvalidOperationException>((Action)Consume);
        else Consume();
        Assert.NotNull(pixels); Assert.NotNull(grey);
        Assert.True(pixels.IsDisposed); Assert.True(grey.IsDisposed); Assert.True(frame.Frame.IsDisposed);
        Assert.Equal(1, recycled); Assert.False(owner.IsDisposed);
    }

    /// <summary>The real Tick must release captured pixels when system information fails before a region owns them.</summary>
    [Fact]
    public void ActualTickRecyclesFrameWhenContentConstructionFailsBeforeOwnershipTransfer()
    {
        using var owner = new Mat(1080, 1920, MatType.CV_8UC3, Scalar.All(23));
        var recycled = 0;
        using var frame = new GameCaptureFrame(WgcBgrMat.CreateFrom(owner, _ => recycled++));
        var info = new FailingRegionSystemInfo();
        using var template = TestGameRuntime.Create(info);
        var capture = new SingleFrameCapture(frame);
        using var runtime = new GameRuntime(template.Kind, template.Window, capture, template.Input, info,
            template.MaskWindowDrawingBoard, template.MaskWindowMapState);
        var config = new AllConfig(); config.AutoSkipConfig.Enabled = false;
        var dispatcher = new TaskTriggerDispatcher(NullLogger<TaskTriggerDispatcher>.Instance, null!, new NullMaskHost(), config);
        using var timer = (System.Timers.Timer)typeof(TaskTriggerDispatcher)
            .GetField("_timer", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(dispatcher)!;
        typeof(TaskTriggerDispatcher).GetField("_runtime", BindingFlags.Instance | BindingFlags.NonPublic)!
            .SetValue(dispatcher, runtime);

        var error = Assert.Throws<InvalidOperationException>(() => dispatcher.Tick(null, EventArgs.Empty));
        Assert.Equal("synthetic_region_construction_failure", error.Message);
        Assert.Equal(1, capture.Calls); Assert.Equal(1, info.RegionRequests);
        // Assert before fixture cleanup; otherwise a test-owned final Dispose would mask the production leak.
        Assert.True(frame.Frame.IsDisposed); Assert.Equal(1, recycled); Assert.False(owner.IsDisposed);
        dispatcher.Tick(null, EventArgs.Empty); // A null second capture also proves the tick lock was released.
        Assert.Equal(2, capture.Calls); Assert.Equal(1, recycled);
    }

    /// <summary>Return one caller-owned synthetic frame; fixture cleanup cannot hide missing Tick disposal.</summary>
    private sealed class SingleFrameCapture(GameCaptureFrame frame) : IGameCapture
    {
        /// <summary>Number of synchronous capture calls.</summary>
        internal int Calls;
        /// <summary>Only an inert test capture exists.</summary>
        public bool IsCapturing => true;
        /// <summary>Transfer the fixture frame once, then exercise the null-capture return.</summary>
        public GameCaptureFrame? Capture() => ++Calls == 1 ? frame : null;
        /// <summary>No operating-system capture is started.</summary>
        public void Start(nint window, Dictionary<string, object>? settings = null) { }
        /// <summary>No operating-system capture is stopped.</summary>
        public void Stop() { }
        /// <summary>The fixture independently owns cleanup; do not hide a missing consumer disposal.</summary>
        public void Dispose() { }
    }

    /// <summary>Keep all pre-capture window properties valid, then fail exactly where CaptureContent takes pixel ownership.</summary>
    private sealed class FailingRegionSystemInfo : ISystemInfo
    {
        /// <summary>Count region-construction attempts separately from window/viewport reads.</summary>
        internal int RegionRequests;
        /// <summary>Synthetic display dimensions require no native monitor query.</summary>
        public System.Drawing.Size DisplaySize => new(1920, 1080);
        /// <summary>Synthetic native image geometry.</summary>
        public RECT GameScreenSize => new(0, 0, 1920, 1080);
        /// <summary>No asset scaling is needed.</summary>
        public double AssetScale => 1;
        /// <summary>No preview scaling is needed.</summary>
        public double ZoomOutMax1080PRatio => 1;
        /// <summary>No normalization scaling is needed.</summary>
        public double ScaleTo1080PRatio => 1;
        /// <summary>Empty screen coordinates keep the synthetic dispatcher position unchanged.</summary>
        public RECT CaptureAreaRect { get; set; }
        /// <summary>Normal reference geometry for downstream code that should not run.</summary>
        public Rect ScaleMax1080PCaptureRect { get; set; } = new(0, 0, 1920, 1080);
        /// <summary>Fail before DesktopRegion.Derive can acquire the Mat.</summary>
        public DesktopRegion DesktopRectArea
        {
            get { RegionRequests++; throw new InvalidOperationException("synthetic_region_construction_failure"); }
        }
        /// <summary>No display scaling.</summary>
        public float DpiScale => 1;
    }

    /// <summary>No-op mask host keeps the actual Tick regression free of windows and dispatchers.</summary>
    private sealed class NullMaskHost : IMaskWindowHost
    {
        /// <summary>No visual overlay is created.</summary>
        public void ReportGameWindow(GameWindowState state) { }
        /// <summary>No visual overlay state exists.</summary>
        public MaskWindowState State => default;
        /// <summary>No callbacks are installed.</summary>
        public event EventHandler<MaskWindowState>? StateChanged { add { } remove { } }
        /// <summary>No native attachment.</summary>
        public void Attach(nint handle) { }
        /// <summary>No native detachment.</summary>
        public void Detach() { }
        /// <summary>No window to close.</summary>
        public void Close() { }
    }
}
