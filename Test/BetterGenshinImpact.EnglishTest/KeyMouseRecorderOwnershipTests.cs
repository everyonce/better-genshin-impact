using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Monitor;
using BetterGenshinImpact.Core.Recorder;
using BetterGenshinImpact.Core.Recorder.Model;
using BetterGenshinImpact.GameTask.Model.Area;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using OpenCvSharp;
using System.Text.Json;
using System.Windows.Forms;
using Vanara.PInvoke;
using Xunit;
using Region = BetterGenshinImpact.GameTask.Model.Area.Region;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Uses detached input events, fake runtime metadata and CPU Mats; no hooks, GDI or game access.</summary>
public sealed class KeyMouseRecorderOwnershipTests
{
    /// <summary>Concurrent hook and relative-mouse producers retain every event while snapshots are taken.</summary>
    [Fact]
    public async Task ConcurrentProducersAndSnapshotsRetainAllEvents()
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1), new ObserveOnlyInputBackend());
        var recorder = new KeyMouseRecorder(runtime, new AllConfig());
        const int count = 10000;
        var start = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var keys = Task.Run(async () =>
        {
            await start.Task;
            for (var i = 0; i < count; i++) recorder.KeyDown(new KeyEventArgs(Keys.W), recorder.StartTime.AddMilliseconds(i));
        });
        var mouse = Task.Run(async () =>
        {
            await start.Task;
            for (var i = 0; i < count; i++) recorder.MouseMoveBy(new RelativeMouseMoveEventArgs(1, 0, recorder.StartTime.AddMilliseconds(i)));
        });
        var snapshots = Task.Run(async () =>
        {
            await start.Task;
            for (var i = 0; i < 50; i++) Assert.All(recorder.MacroEvents, e => Assert.NotNull(e));
        });
        start.SetResult();
        await Task.WhenAll(keys, mouse, snapshots).WaitAsync(TimeSpan.FromSeconds(20));
        var events = recorder.MacroEvents;
        Assert.Equal(count * 2, events.Count);
        Assert.Equal(count, events.Count(e => e.Type == MacroEventType.KeyDown));
        Assert.Equal(count, events.Count(e => e.Type == MacroEventType.MouseMoveBy));
    }

    /// <summary>Merging a snapshot must not add relative movement to the original recording on each serialization.</summary>
    [Fact]
    public void SerializationIsRepeatableAndSnapshotsAreDetached()
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1), new ObserveOnlyInputBackend());
        var recorder = new KeyMouseRecorder(runtime, new AllConfig());
        recorder.MouseMoveBy(new RelativeMouseMoveEventArgs(2, 3, recorder.StartTime));
        recorder.MouseMoveBy(new RelativeMouseMoveEventArgs(5, 7, recorder.StartTime.AddMilliseconds(5)));
        var first = recorder.ToJsonMacro();
        Assert.Equal(first, recorder.ToJsonMacro());
        var script = JsonSerializer.Deserialize<KeyMouseScript>(first, KeyMouseRecorder.JsonOptions)!;
        Assert.Equal(7, Assert.Single(script.MacroEvents).MouseX);
        Assert.Equal(10, script.MacroEvents[0].MouseY);
        var snapshot = recorder.MacroEvents;
        snapshot[0].MouseX = 100;
        snapshot.Clear();
        Assert.Equal(2, recorder.MacroEvents.Count);
        Assert.Equal(2, recorder.MacroEvents[0].MouseX);
    }

    /// <summary>Equal timestamps retain producer admission order, including key press/release pairs.</summary>
    [Fact]
    public void SerializationPreservesEqualTimestampOrderAndFiltersNegativeTimes()
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1), new ObserveOnlyInputBackend());
        var recorder = new KeyMouseRecorder(runtime, new AllConfig());
        recorder.KeyDown(new KeyEventArgs(Keys.A), recorder.StartTime.AddMilliseconds(-1));
        for (var i = 0; i < 20; i++)
        {
            recorder.KeyDown(new KeyEventArgs(Keys.W), recorder.StartTime);
            recorder.KeyUp(new KeyEventArgs(Keys.W), recorder.StartTime);
        }
        var script = JsonSerializer.Deserialize<KeyMouseScript>(recorder.ToJsonMacro(), KeyMouseRecorder.JsonOptions)!;
        Assert.Equal(40, script.MacroEvents.Count);
        for (var i = 0; i < script.MacroEvents.Count; i++)
        {
            Assert.Equal(i % 2 == 0 ? MacroEventType.KeyDown : MacroEventType.KeyUp, script.MacroEvents[i].Type);
            Assert.Equal(0, script.MacroEvents[i].Time);
        }
    }

    /// <summary>Recognition failure still disposes the captured image and its native Mat.</summary>
    [Fact]
    public void RecognitionFailureDisposesCapturedPixels()
    {
        using var pixels = new Mat(2, 2, MatType.CV_8UC3);
        var region = new ImageRegion(pixels, 0, 0);
        Assert.Throws<InvalidOperationException>(() => GlobalKeyMouseRecord.DetectMainUi(() => region,
            _ => throw new InvalidOperationException("fake recognition failure")));
        Assert.True(pixels.IsDisposed);
    }

    /// <summary>A failing icon cleanup cannot prevent cleanup of its captured image.</summary>
    [Fact]
    public void IconDisposalFailureStillDisposesCapturedPixels()
    {
        using var pixels = new Mat(2, 2, MatType.CV_8UC3);
        var region = new ImageRegion(pixels, 0, 0);
        var icon = new TrackedRegion(throwOnDispose: true);
        Assert.Throws<InvalidOperationException>(() => GlobalKeyMouseRecord.DetectMainUi(() => region, _ => icon));
        Assert.Equal(1, icon.DisposeCount);
        Assert.True(pixels.IsDisposed);
    }

    /// <summary>The normal recognition result is preserved while both owners are released.</summary>
    [Fact]
    public void SuccessfulRecognitionDisposesBothRegions()
    {
        using var pixels = new Mat(2, 2, MatType.CV_8UC3);
        var icon = new TrackedRegion(false);
        Assert.True(GlobalKeyMouseRecord.DetectMainUi(() => new ImageRegion(pixels, 0, 0), _ => icon));
        Assert.Equal(1, icon.DisposeCount);
        Assert.True(pixels.IsDisposed);
    }

    /// <summary>Managed recognition result with independently observable cleanup.</summary>
    private sealed class TrackedRegion(bool throwOnDispose) : Region(0, 0, 1, 1)
    {
        /// <summary>Records cleanup attempts even if cleanup throws.</summary>
        internal int DisposeCount { get; private set; }

        /// <summary>Simulates a secondary cleanup error without allocating native resources.</summary>
        public override void Dispose()
        {
            DisposeCount++;
            if (throwOnDispose) throw new InvalidOperationException("fake icon disposal failure");
        }
    }
}
