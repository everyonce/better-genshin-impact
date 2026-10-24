using Fischless.GameCapture;
using Fischless.GameCapture.Graphics;
using Fischless.GameCapture.Graphics.Helpers;
using SharpDX;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercises the production reservation and Map/copy/Unmap/publication sequence without a GPU or WinRT session.</summary>
public sealed class WgcReadbackSlotTests
{
    /// <summary>One fake successful mapping; no test dereferences this address.</summary>
    private static DataBox Mapped => new(new IntPtr(1), 16, 32);
    /// <summary>Stable source used to expose accidental acquisition-clock renewal.</summary>
    private static GameCaptureSourceInfo Source(Guid epoch, long timestamp = 100) => new(epoch, timestamp, 200);
    /// <summary>Create the actual slot and reserve its one native-storage alias.</summary>
    private static (WgcReadbackSlot Slot, GameCapturePendingReadback Pending) Reserved()
    {
        var epoch = Guid.NewGuid();
        var slot = new WgcReadbackSlot(epoch);
        return (slot, slot.Begin(Source(epoch), 210, 4, 2, new RECT(10, 20, 14, 22)));
    }

    /// <summary>Busy is a single Map probe, never copy, Unmap, publication or renewed identity.</summary>
    [Fact]
    public void RepeatedBusyPollsRetainExactReservation()
    {
        var (slot, pending) = Reserved();
        var calls = new List<string>();
        for (var i = 0; i < 8; i++)
        {
            Assert.False(slot.TryComplete(() => { calls.Add("map"); return default; },
                _ => calls.Add("copy"), () => calls.Add("unmap"), _ => calls.Add("publish")));
            Assert.Same(pending, slot.Pending);
            Assert.Equal(200, slot.Pending!.SourceInfo.AcquiredAtStopwatchTicks);
            Assert.Equal(210, slot.Pending.SubmittedAtStopwatchTicks);
        }
        Assert.Equal(Enumerable.Repeat("map", 8), calls);
        Assert.False(slot.IsFaulted);
    }

    /// <summary>The cache publication boundary follows successful Unmap, with exactly the reserved metadata.</summary>
    [Fact]
    public void CopyAndUnmapPrecedePublication()
    {
        var (slot, pending) = Reserved();
        var calls = new List<string>();
        Assert.True(slot.TryComplete(() => { calls.Add("map"); return Mapped; },
            _ => { Assert.Same(pending, slot.Pending); calls.Add("copy"); },
            () => { Assert.Same(pending, slot.Pending); calls.Add("unmap"); },
            completed => { Assert.Same(pending, completed); calls.Add("publish"); }));
        Assert.Equal(new[] { "map", "copy", "unmap", "publish" }, calls);
        Assert.Null(slot.Pending);
        Assert.False(slot.IsFaulted);
    }

    /// <summary>Any uncertain native/copy/commit failure prevents reuse; no failed Unmap can publish pixels.</summary>
    [Theory]
    [InlineData("map", "map")]
    [InlineData("copy", "map,copy,unmap")]
    [InlineData("unmap", "map,copy,unmap")]
    [InlineData("publish", "map,copy,unmap,publish")]
    public void FailurePermanentlyFaultsSlot(string stage, string expectedCalls)
    {
        var (slot, pending) = Reserved();
        var failure = new InvalidOperationException(stage);
        var calls = new List<string>();
        void Step(string name) { calls.Add(name); if (name == stage) throw failure; }
        var error = Assert.Throws<InvalidOperationException>(() => slot.TryComplete(
            () => { Step("map"); return Mapped; }, _ => Step("copy"), () => Step("unmap"), _ => Step("publish")));
        Assert.Same(failure, error);
        Assert.Equal(expectedCalls.Split(','), calls);
        Assert.True(slot.IsFaulted);
        Assert.Null(slot.Pending);
        Assert.Throws<InvalidOperationException>(() => slot.Begin(pending.SourceInfo, 220, 4, 2, null));
        Assert.Throws<InvalidOperationException>(() => slot.TryComplete(
            () => throw new Exception("must not Map again"), _ => { }, () => { }, _ => { }));
    }

    /// <summary>A retirement during a mapped copy still unmaps, but cannot publish into a replacement lifetime.</summary>
    [Fact]
    public void StopDuringCopyPreventsLatePublication()
    {
        var (slot, _) = Reserved();
        var calls = new List<string>();
        Assert.Throws<InvalidOperationException>(() => slot.TryComplete(() => Mapped,
            _ => { calls.Add("copy"); slot.Stop(); }, () => calls.Add("unmap"), _ => calls.Add("publish")));
        Assert.Equal(new[] { "copy", "unmap" }, calls);
        Assert.True(slot.IsStopped);
        Assert.Null(slot.Pending);
    }

    /// <summary>Stopping an idle pending slot performs no native completion work and a fresh epoch gets fresh storage authority.</summary>
    [Fact]
    public void StoppedPendingCannotLeakIntoRestart()
    {
        var (old, prior) = Reserved();
        old.Stop();
        Assert.Null(old.Pending);
        Assert.Throws<InvalidOperationException>(() => old.TryComplete(
            () => throw new Exception("no Map during retirement"), _ => { }, () => { }, _ => { }));
        var epoch = Guid.NewGuid();
        var fresh = new WgcReadbackSlot(epoch);
        var current = fresh.Begin(Source(epoch), 250, 8, 3, null);
        Assert.NotEqual(prior.SourceInfo.CaptureEpoch, current.SourceInfo.CaptureEpoch);
        Assert.Equal(1, current.SubmissionId);
        Assert.Throws<ArgumentException>(() => new WgcReadbackSlot(epoch).Begin(prior.SourceInfo, 250, 4, 2, null));
    }

    /// <summary>Storage cannot be overwritten while busy; refill after completion retains separate identities.</summary>
    [Fact]
    public void CompletionPermitsExactlyOneNewReservation()
    {
        var (slot, first) = Reserved();
        Assert.Throws<InvalidOperationException>(() => slot.Begin(first.SourceInfo, 230, 4, 2, null));
        Assert.Same(first, slot.Pending);
        Assert.True(slot.TryComplete(() => Mapped, _ => { }, () => { }, _ => { }));
        var next = slot.Begin(Source(first.SourceInfo.CaptureEpoch, 101), 240, 4, 2, new RECT(11, 21, 15, 23));
        Assert.Equal(first.SubmissionId + 1, next.SubmissionId);
        Assert.Equal(100, first.SourceInfo.SourceTimestamp100ns);
        Assert.Equal(101, next.SourceInfo.SourceTimestamp100ns);
        Assert.NotEqual(first.CaptureRect, next.CaptureRect);
        Assert.Throws<InvalidOperationException>(() => slot.Begin(next.SourceInfo, 250, 4, 2, null));
    }

    /// <summary>A failed copy cannot make an already acquired source new again in this generation.</summary>
    [Fact]
    public void FailedReadbackDoesNotRenewSourceHighWater()
    {
        var generation = new WgcCaptureGeneration();
        var source = generation.TryAcquire(100, 200)!;
        var slot = new WgcReadbackSlot(generation.Epoch);
        slot.Begin(source, 210, 4, 2, null);
        Assert.Throws<InvalidOperationException>(() => slot.TryComplete(() => Mapped,
            _ => throw new InvalidOperationException("copy"), () => { }, _ => { }));
        Assert.Null(generation.TryAcquire(100, 999));
        Assert.Equal(200, source.AcquiredAtStopwatchTicks);
        Assert.Equal(1000, generation.TryAcquire(101, 1000)!.AcquiredAtStopwatchTicks);
    }

    /// <summary>Malformed pointer, pitch and overflowing pixel bounds fail before pointer access, still paired with Unmap.</summary>
    [Theory]
    [InlineData(0, 16, 4, 2, true)]
    [InlineData(1, 15, 4, 2, true)]
    [InlineData(1, 16, 0, 2, false)]
    [InlineData(1, 16, int.MaxValue, 2, false)]
    public void InvalidMappedLayoutCannotPublish(int pointer, int pitch, int width, int height, bool cpu)
    {
        var (slot, _) = Reserved();
        var unmapped = 0;
        var published = 0;
        Assert.ThrowsAny<Exception>(() => slot.TryComplete(() => new DataBox(new IntPtr(pointer), pitch, 32),
            box => GraphicsCaptureV2.ValidatePollingMap(box, width, height, cpu),
            () => unmapped++, _ => published++));
        Assert.Equal(1, unmapped);
        Assert.Equal(0, published);
        Assert.True(slot.IsFaulted);
    }
}
