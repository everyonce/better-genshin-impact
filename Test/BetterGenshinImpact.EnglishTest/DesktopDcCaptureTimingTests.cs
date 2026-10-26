using System.Diagnostics;
using System.Runtime.InteropServices;
using Fischless.GameCapture;
using Fischless.GameCapture.DesktopDc;
using Newtonsoft.Json;
using OpenCvSharp;
using Xunit;
using Xunit.Abstractions;
using FakeGdi = BetterGenshinImpact.EnglishTest.DesktopDcGdiOwnershipTests.FakeGdi;
using Scope = BetterGenshinImpact.EnglishTest.DesktopDcThreadDpiScopeTests.CallbackScope;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Fake native calls and small CPU Mats verify timing, publication and unchanged ownership without a desktop.</summary>
public sealed class DesktopDcCaptureTimingTests(ITestOutputHelper output)
{
    /// <summary>Independent diagnostic reads preserve the two authority endpoints, native order and exact returned bytes.</summary>
    [Fact]
    public void CompletePhasesPreserveNativeOrderPixelsAndHostClock()
    {
        var native = new FakeGdi();
        long diagnostic = 100, authority = 1000;
        var clockReads = 0;
        var targetReads = 0;
        var authorityReads = 0;
        native.OnCopy = () => diagnostic += 11;
        using var capture = new DesktopDcCapture(_ =>
            {
                diagnostic += ++targetReads;
                return DesktopDcTargetTests.Valid();
            }, native, owner =>
            {
                Assert.Equal((nint)40, owner.Bits);
                diagnostic += 13;
                return new Mat(2, 2, MatType.CV_8UC3, Scalar.All(7));
            }, () => { authorityReads++; return ++authority; }, 1000,
            () => { diagnostic += 5; return new Scope(() => diagnostic += 7); },
            () => { clockReads++; return ++diagnostic; }, 1000);
        capture.Start(100);
        using var frame = capture.Capture();
        var host = Assert.IsType<GameCaptureHostSnapshotInfo>(frame!.HostSnapshotInfo);
        var timing = Assert.IsType<DesktopDcCaptureTiming>(capture.GetTiming(host));
        Assert.Equal(21, clockReads);
        Assert.Equal(2, authorityReads);
        Assert.Equal((1001L, 1002L, 1000L), (host.StartedAtStopwatchTicks, host.CompletedAtStopwatchTicks, host.ClockFrequency));
        Assert.Equal(new[] { "screen", "device", "memory", "bitmap", "layout", "select", "copy", "flush",
            "flush", "restore", "delete_bitmap", "delete_dc", "release_screen" }, native.Calls);
        var pixels = new byte[12];
        Marshal.Copy(frame.Frame.Data, pixels, 0, pixels.Length);
        Assert.Equal(Enumerable.Repeat((byte)7, 12), pixels);
        Assert.Equal(new double[] { 1, 6, 3, 1, 12, 1, 4, 14, 1, 8 }, Phases(timing));
        Assert.Equal(61, timing.TotalMs);
        Assert.Equal(10, timing.UnattributedMs);
        Assert.Equal(timing.TotalMs, Phases(timing).Sum() + timing.UnattributedMs);
        Assert.True(timing.DiagnosticOnly);
        Assert.Equal(host.CaptureEpoch.ToString("N"), timing.CaptureEpoch);
        Assert.Equal(host.SnapshotId, timing.SnapshotId);
        Assert.Null(capture.GetTiming(host with { })); // Value equality is not acquisition ownership.
        Assert.True(JsonConvert.SerializeObject(timing).Length < 2048);
    }

    /// <summary>A new attempt clears the provider; immutable records retained by an older frame do not mutate.</summary>
    [Fact]
    public void NextAttemptFailureAndStopCannotReusePreviousTiming()
    {
        var native = new FakeGdi();
        using var capture = Create(native);
        capture.Start(100);
        using var first = capture.Capture();
        var old = Assert.IsType<DesktopDcCaptureTiming>(capture.GetTiming(first!.HostSnapshotInfo!));
        using var second = capture.Capture();
        Assert.Null(capture.GetTiming(first.HostSnapshotInfo!));
        Assert.Equal(2, capture.GetTiming(second!.HostSnapshotInfo!)!.SnapshotId);
        Assert.Equal(1, old.SnapshotId);
        native.Failures.Add("copy");
        Assert.Throws<InvalidOperationException>(() => capture.Capture());
        Assert.Null(capture.GetTiming(second.HostSnapshotInfo!));
        native.Failures.Clear();
        using var third = capture.Capture();
        Assert.Equal(3, capture.GetTiming(third!.HostSnapshotInfo!)!.SnapshotId);
        capture.Stop();
        Assert.Null(capture.GetTiming(third.HostSnapshotInfo!));
        Assert.Null(capture.Capture());
        capture.Start(100);
        Assert.Null(capture.GetTiming(third.HostSnapshotInfo!));
        using var fresh = capture.Capture();
        Assert.NotEqual(third.HostSnapshotInfo!.CaptureEpoch, fresh!.HostSnapshotInfo!.CaptureEpoch);
        Assert.Equal(1, capture.GetTiming(fresh.HostSnapshotInfo)!.SnapshotId);
    }

    /// <summary>Cleanup uncertainty clears prior timing and preserves the existing sticky quarantine.</summary>
    [Fact]
    public void CleanupFailureCannotPublishSuccessfulDiagnostics()
    {
        var native = new FakeGdi();
        using var capture = Create(native);
        capture.Start(100);
        using var first = capture.Capture();
        native.Failures.Add("release_screen");
        Assert.Throws<DesktopDcCleanupException>(() => capture.Capture());
        Assert.Null(capture.GetTiming(first!.HostSnapshotInfo!));
        Assert.False(capture.IsCapturing);
        var calls = native.Calls.Count;
        capture.Stop();
        Assert.Throws<DesktopDcCleanupException>(() => capture.Start(100));
        Assert.Equal(calls, native.Calls.Count);
    }

    /// <summary>A blocked second caller records its gate wait separately without moving either authoritative host endpoint.</summary>
    [Fact]
    public async Task ConcurrentCallerRecordsOnlyItsOwnPreGateWait()
    {
        var native = new FakeGdi();
        using var entered = new ManualResetEventSlim();
        using var queued = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        var copyCount = 0;
        var secondThread = 0;
        var secondReads = 0;
        long authority = 1000, diagnostic = 100;
        native.OnCopy = () =>
        {
            if (Interlocked.Increment(ref copyCount) != 1) return;
            entered.Set();
            if (!release.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("fake first copy release");
        };
        using var capture = new DesktopDcCapture(_ => DesktopDcTargetTests.Valid(), native, _ => new Mat(),
            () => Interlocked.Increment(ref authority), 1000, () => new Scope(() => { }), () =>
            {
                var now = Interlocked.Read(ref diagnostic);
                if (Environment.CurrentManagedThreadId == Volatile.Read(ref secondThread) &&
                    Interlocked.Increment(ref secondReads) == 1) queued.Set();
                return now;
            }, 1000);
        capture.Start(100);
        var first = Task.Run(() => capture.Capture());
        Task<GameCaptureFrame?>? second = null;
        try
        {
            Assert.True(entered.Wait(TimeSpan.FromSeconds(5)));
            second = Task.Run(() =>
            {
                Volatile.Write(ref secondThread, Environment.CurrentManagedThreadId);
                return capture.Capture();
            });
            Assert.True(queued.Wait(TimeSpan.FromSeconds(5)));
            Interlocked.Exchange(ref diagnostic, 200);
        }
        finally { release.Set(); }
        using var firstFrame = await first.WaitAsync(TimeSpan.FromSeconds(5));
        using var secondFrame = await second!.WaitAsync(TimeSpan.FromSeconds(5));
        var timing = Assert.IsType<DesktopDcCaptureTiming>(capture.GetTiming(secondFrame!.HostSnapshotInfo!));
        Assert.Equal(100, timing.GateWaitMs);
        Assert.Equal(100, timing.TotalMs);
        Assert.Equal(0, Phases(timing).Skip(1).Sum());
        Assert.Null(capture.GetTiming(firstFrame!.HostSnapshotInfo!));
        Assert.Equal((1003L, 1004L), (secondFrame.HostSnapshotInfo!.StartedAtStopwatchTicks,
            secondFrame.HostSnapshotInfo.CompletedAtStopwatchTicks));
    }

    /// <summary>Failed diagnostic clocks omit metadata without suppressing native cleanup or changing pixels/host endpoints.</summary>
    [Theory]
    [InlineData("throw")]
    [InlineData("regress")]
    [InlineData("negative")]
    [InlineData("frequency")]
    public void InvalidDiagnosticClockDoesNotAffectSuccessfulAcquisition(string fault)
    {
        var native = new FakeGdi();
        var reads = 0;
        long authority = 100;
        using var capture = new DesktopDcCapture(_ => DesktopDcTargetTests.Valid(), native,
            _ => new Mat(1, 1, MatType.CV_8UC3, Scalar.All(9)), () => ++authority, 1000,
            () => new Scope(() => { }), () =>
            {
                reads++;
                if (reads == 3)
                {
                    if (fault == "throw") throw new InvalidOperationException("diagnostic clock only");
                    if (fault == "regress") return 1;
                    if (fault == "negative") return -1;
                }
                return 100 + reads;
            }, fault == "frequency" ? -1 : 1000);
        capture.Start(100);
        using var frame = capture.Capture();
        Assert.Null(capture.GetTiming(frame!.HostSnapshotInfo!));
        Assert.Equal((101L, 102L), (frame.HostSnapshotInfo!.StartedAtStopwatchTicks, frame.HostSnapshotInfo.CompletedAtStopwatchTicks));
        Assert.Equal(new Vec3b(9, 9, 9), frame.Frame.At<Vec3b>(0, 0));
        Assert.Equal("release_screen", native.Calls.Last());
        Assert.True(capture.IsCapturing);
    }

    /// <summary>Pre/post-copy target failure and a reentrant Stop leave no diagnostic record for the previous frame.</summary>
    [Theory]
    [InlineData("pre")]
    [InlineData("post")]
    [InlineData("stop")]
    public void TargetOrGenerationFailureCannotReuseTiming(string failure)
    {
        var native = new FakeGdi();
        var fail = false;
        var reads = 0;
        using var capture = Create(native, reader: _ =>
        {
            reads++;
            if (fail && ((failure == "pre" && reads == 4) || (failure == "post" && reads == 5)))
                throw new InvalidOperationException("target changed");
            return DesktopDcTargetTests.Valid();
        });
        capture.Start(100);
        using var first = capture.Capture();
        fail = true;
        if (failure == "stop") native.OnCopy = capture.Stop;
        Assert.Throws<InvalidOperationException>(() => capture.Capture());
        Assert.Null(capture.GetTiming(first!.HostSnapshotInfo!));
    }

    /// <summary>Metadata work is measured separately from capture; report cost without a machine-load-sensitive pass threshold.</summary>
    [Fact]
    public void RecorderCostIsBoundedAndReportedWithoutNativeWork()
    {
        var phases = Enum.GetValues<DesktopDcCapturePhase>();
        var host = new GameCaptureHostSnapshotInfo(Guid.NewGuid(), 1, 100, 101, Stopwatch.Frequency);
        // Exercise only the scalar recorder: no capture, image, native API or external interface.
        DesktopDcCaptureTiming? Record()
        {
            var recorder = new DesktopDcCapturePhaseRecorder(Stopwatch.GetTimestamp, Stopwatch.Frequency);
            foreach (var phase in phases) { recorder.Begin(phase); recorder.End(phase); }
            return recorder.Complete(host);
        }
        for (var i = 0; i < 256; i++) Assert.NotNull(Record());
        var allocated = GC.GetAllocatedBytesForCurrentThread();
        var started = Stopwatch.GetTimestamp();
        DesktopDcCaptureTiming? last = null;
        const int count = 10_000;
        for (var i = 0; i < count; i++) last = Record();
        var elapsed = Stopwatch.GetElapsedTime(started);
        var bytes = GC.GetAllocatedBytesForCurrentThread() - allocated;
        Assert.NotNull(last);
        Assert.InRange(bytes / count, 1, 1024);
        output.WriteLine($"Diagnostic-only recorder: {elapsed.TotalMicroseconds / count:F3} us/call, {bytes / count} allocated bytes/call; {count} samples, no GDI/pixels.");
    }

    /// <summary>Use the actual capture transaction with deterministic authority/diagnostic clocks and a managed DPI scope.</summary>
    private static DesktopDcCapture Create(FakeGdi native, Func<nint, DesktopDcTargetSnapshot>? reader = null)
    {
        long authority = 100, diagnostic = 100;
        return new DesktopDcCapture(reader ?? (_ => DesktopDcTargetTests.Valid()), native,
            _ => new Mat(1, 1, MatType.CV_8UC3, Scalar.All(7)), () => ++authority, 1000,
            () => new Scope(() => { }), () => ++diagnostic, 1000);
    }

    /// <summary>Read all exclusive intervals in their fixed execution order for the decomposition check.</summary>
    private static double[] Phases(DesktopDcCaptureTiming timing) =>
        [timing.GateWaitMs, timing.DpiSetupMs, timing.PreTargetCheckMs, timing.AllocationMs,
            timing.BitBltMs, timing.FirstFlushMs, timing.PostTargetCheckMs, timing.CloneMs,
            timing.CleanupMs, timing.DpiRestoreMs];
}
