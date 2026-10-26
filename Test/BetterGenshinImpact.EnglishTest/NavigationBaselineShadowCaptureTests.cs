using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Serialize tests sharing the deliberately process-wide single-writer admission gate.</summary>
[CollectionDefinition("ShadowCaptureSerial", DisableParallelization = true)]
public sealed class ShadowCaptureSerialCollection { }

/// <summary>Owned Mat copies, bounded worker failure/drain, exact RGB output and immutable journal joins; no game/input/GPU.</summary>
[Collection("ShadowCaptureSerial")]
public sealed class NavigationBaselineShadowCaptureTests
{
    /// <summary>Fixed synthetic native owner and capture generation.</summary>
    private const string Run = "0123456789abcdef0123456789abcdef";
    /// <summary>Immutable epoch for synthetic monotonically advancing captures.</summary>
    private static readonly Guid Epoch = Guid.Parse("01234567-89ab-cdef-0123-456789abcdef");
    /// <summary>Every fixture owns a fresh bounded directory, removed only after worker retirement.</summary>
    private static string Folder() => Path.Combine(Path.GetTempPath(), "bgi-shadow-tests", Guid.NewGuid().ToString("N"));
    /// <summary>Produce metadata on the same units as the actual poll classifier.</summary>
    private static GameCaptureSourceInfo Source(int index) => new(Epoch, (1000L + index * 20) * 10_000,
        (long)((1000 + index * 20) * Stopwatch.Frequency / 1000.0));
    /// <summary>A fresh source may still precede the response barrier; this does not grant pose/input authority.</summary>
    private static NavigationBaselineCapturePoll Poll(int index, bool beforeBarrier = false)
    {
        var source = Source(index);
        var poll = new NavigationBaselineCapturePoll(index, 1000 + index * 20)
        { Source = source, CaptureReturnedAtMs = 1002 + index * 20 };
        poll.Classify(source, null, null, beforeBarrier ? 1000 + index * 20 : 0, beforeBarrier ? 80 : 0, 1002 + index * 20);
        return poll;
    }
    /// <summary>Write only the minimal actual owner join needed by the archive writer.</summary>
    private static (string Path, string Hash) Journal(string folder, string run = Run)
    {
        Directory.CreateDirectory(folder);
        var path = Path.Combine(folder, "native.json");
        var bytes = JsonSerializer.SerializeToUtf8Bytes(new { runId = run });
        File.WriteAllBytes(path, bytes);
        return (path, Convert.ToHexString(SHA256.HashData(bytes)));
    }
    /// <summary>The source can be modified and disposed while the worker is blocked; only the independent packed copy survives.</summary>
    [Theory]
    [InlineData(3, 12, 8, false)]
    [InlineData(4, 12, 8, true)]
    [InlineData(4, 3840, 2160, false)]
    public async Task BorrowedPixelsAreCopiedBeforeDisposalAndWrittenAsExactRgb(int channels, int width, int height, bool padded)
    {
        var folder = Folder(); var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var session = new NavigationBaselineShadowCapture(Path.Combine(folder, "shadow"), Run, 123, 3, "poll_single_v1",
            async ct => { entered.TrySetResult(); await release.Task.WaitAsync(ct); });
        try
        {
            await session.InitializeAsync(CancellationToken.None);
            using (var backing = new Mat(height, width + (padded ? 7 : 0), channels == 3 ? MatType.CV_8UC3 : MatType.CV_8UC4,
                       new Scalar(11, 22, 33, 99)))
            using (var pixels = new Mat(backing, new Rect(0, 0, width, height)))
            {
                session.Offer(pixels, Source(0), 0, Poll(0, true));
                await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
                backing.SetTo(Scalar.Black);
            }
            release.TrySetResult();
            var native = Journal(folder);
            var result = await session.CompleteAsync(native.Path, native.Hash.ToLowerInvariant());
            Assert.True(result.Complete); Assert.True(result.WorkerRetired);
            var rgb = File.ReadAllBytes(Path.Combine(folder, "shadow", "0000.rgb"));
            Assert.Equal(192 * 192 * 3, rgb.Length);
            for (var i = 0; i < rgb.Length; i += 3) Assert.Equal(new byte[] { 33, 22, 11 }, rgb[i..(i + 3)]);
            using var manifest = JsonDocument.Parse(File.ReadAllBytes(result.ManifestPath!));
            var row = manifest.RootElement.GetProperty("frames")[0];
            Assert.Equal("response_barrier", row.GetProperty("frame").GetProperty("captureGateDisposition").GetString());
            Assert.Equal("not_evaluated_at_copy", row.GetProperty("poseAdmission").GetString());
            Assert.False(row.GetProperty("inputAuthority").GetBoolean());
            Assert.Equal(result.ManifestSha256, Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(result.ManifestPath!))));
        }
        finally { release.TrySetResult(); await session.DisposeAsync(); if (session.Snapshot().WorkerRetired) Directory.Delete(folder, true); }
    }

    /// <summary>Eight bounded raw slots include the active resizer; overflow stays visible and never waits for the writer.</summary>
    [Fact]
    public async Task BoundedSlotsOverflowOnceAndIgnoreFurtherOffersWithoutHidingLoss()
    {
        var folder = Folder(); var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var session = new NavigationBaselineShadowCapture(Path.Combine(folder, "shadow"), Run, 123, 3, "blocking",
            async ct => { entered.TrySetResult(); await release.Task.WaitAsync(ct); });
        try
        {
            await session.InitializeAsync(CancellationToken.None);
            using var pixels = new Mat(8, 12, MatType.CV_8UC3, Scalar.White);
            session.Offer(pixels, Source(0), 0, Poll(0)); await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            session.Offer(pixels, Source(0), 1, Poll(0)); // Exact same immutable pixels are not copied twice.
            for (var i = 1; i < NavigationBaselineShadowCapture.MaximumBufferSlots; i++)
                session.Offer(pixels, Source(i), i + 1, Poll(i));
            session.Offer(pixels, Source(8), 9, Poll(8));
            session.Offer(pixels, Source(9), 10, Poll(9));
            release.TrySetResult(); var native = Journal(folder);
            var result = await session.CompleteAsync(native.Path, native.Hash);
            Assert.False(result.Complete); Assert.True(result.WorkerRetired);
            Assert.Equal("shadow_buffer_exhausted", result.Error);
            Assert.Equal((11, 8, 8, 1, 1, 1, 1), (result.FramesSeen, result.FramesAccepted, result.FramesWritten,
                result.DuplicateFrames, result.FramesRejected, result.OffersIgnoredAfterStop, result.FramesLost));
            session.Offer(pixels, Source(10), 11, Poll(10));
            Assert.Equal(result, session.Snapshot()); // Final close fixes counts; no late admission/publication.
        }
        finally { release.TrySetResult(); await session.DisposeAsync(); if (session.Snapshot().WorkerRetired) Directory.Delete(folder, true); }
    }

    /// <summary>An uncooperative write cannot admit a second session; timeout never frees another worker's buffers.</summary>
    [Fact]
    public async Task RetirementTimeoutRetainsGlobalReservationUntilActualWorkerExit()
    {
        var folder = Folder(); var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var session = new NavigationBaselineShadowCapture(Path.Combine(folder, "shadow"), Run, 123, 3, "blocking",
            _ => { entered.TrySetResult(); return release.Task; });
        try
        {
            await session.InitializeAsync(CancellationToken.None);
            using var pixels = new Mat(8, 12, MatType.CV_8UC3, Scalar.White);
            session.Offer(pixels, Source(0), 0, Poll(0)); await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            var native = Journal(folder); var result = await session.CompleteAsync(native.Path, native.Hash);
            Assert.False(result.WorkerRetired); Assert.False(result.Complete);
            Assert.Equal("shadow_worker_retirement_timeout", result.Error);
            Assert.Throws<InvalidOperationException>(() => new NavigationBaselineShadowCapture(Path.Combine(folder, "other"), Run, 123, 3, "blocking"));
        }
        finally
        {
            release.TrySetResult();
            var elapsed = Stopwatch.StartNew();
            while (!session.Snapshot().WorkerRetired && elapsed.Elapsed < TimeSpan.FromSeconds(5)) await Task.Delay(1);
            await session.DisposeAsync(); Assert.True(session.Snapshot().WorkerRetired); Directory.Delete(folder, true);
        }
    }

    /// <summary>A timeout/cancelled private waiter leaves no observer; late failure is still observed and still awaitable as the same error.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public async Task LateReadinessFailureAfterAbandonedWaitIsObserved(bool cancelled)
    {
        var ready = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var stop = new CancellationTokenSource();
        if (cancelled)
        {
            stop.Cancel();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => ready.Task.WaitAsync(TimeSpan.FromSeconds(2), stop.Token));
        }
        else await Assert.ThrowsAsync<TimeoutException>(() => ready.Task.WaitAsync(TimeSpan.Zero));
        var original = new IOException("late_initialization_failure");
        // The actual worker helper reads Task.Exception, marking it observed without changing its future await result.
        var observed = NavigationBaselineShadowCapture.FailReadiness(ready, original);
        Assert.NotNull(observed); Assert.Same(original, Assert.Single(observed!.InnerExceptions));
        Assert.Same(original, await Assert.ThrowsAsync<IOException>(async () => await ready.Task));
        Assert.Null(NavigationBaselineShadowCapture.FailReadiness(ready, new IOException("later_failure")));
    }

    /// <summary>A later writer error never changes an already successful storage-admission task.</summary>
    [Fact]
    public void ReadinessSuccessCannotBecomeFaultedByLaterWriterFailure()
    {
        var ready = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        ready.SetResult();
        Assert.Null(NavigationBaselineShadowCapture.FailReadiness(ready, new IOException("writer_failure")));
        Assert.True(ready.Task.IsCompletedSuccessfully);
    }

    /// <summary>Writer faults retain honest bounded counts without returning a successful archive.</summary>
    [Fact]
    public async Task WorkerFailureAndWrongJournalNeverBecomeComplete()
    {
        foreach (var failWriter in new[] { false, true })
        {
            var folder = Folder();
            await using var session = new NavigationBaselineShadowCapture(Path.Combine(folder, "shadow"), Run, 123, 3, "blocking",
                failWriter ? _ => Task.FromException(new IOException("synthetic disk failure")) : null);
            try
            {
                await session.InitializeAsync(CancellationToken.None);
                using var pixels = new Mat(8, 12, MatType.CV_8UC3, Scalar.White);
                session.Offer(pixels, Source(0), 0, Poll(0));
                var native = Journal(folder, new string('b', 32));
                var result = await session.CompleteAsync(native.Path, native.Hash);
                Assert.False(result.Complete); Assert.True(result.WorkerRetired); Assert.NotNull(result.Error);
                Assert.Null(result.ManifestPath);
                Assert.Equal(failWriter ? 1 : 0, result.FramesLost);
            }
            finally { await session.DisposeAsync(); if (session.Snapshot().WorkerRetired) Directory.Delete(folder, true); }
        }
    }

    /// <summary>Fixed banks yield eight 1080p BGRA slots or two 4K slots without reserving another raw byte.</summary>
    [Theory]
    [InlineData(1920, 1080, 8)]
    [InlineData(3840, 2160, 2)]
    public async Task GeometryPartitionsTheSameReservedRawBudget(int width, int height, int slots)
    {
        var folder = Folder(); var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var session = new NavigationBaselineShadowCapture(Path.Combine(folder, "shadow"), Run, 123, 3, "blocking",
            async ct => { entered.TrySetResult(); await release.Task.WaitAsync(ct); });
        try
        {
            Assert.Equal((0, 0, 0, 66_355_200), session.BufferStateForValidation());
            await session.InitializeAsync(CancellationToken.None);
            using var pixels = new Mat(height, width, MatType.CV_8UC4, new Scalar(11, 22, 33, 99));
            session.Offer(pixels, Source(0), 0, Poll(0));
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal((slots, 1, slots - 1, 66_355_200), session.BufferStateForValidation());
            for (var i = 1; i < slots; i++) session.Offer(pixels, Source(i), i, Poll(i));
            Assert.Equal((slots, slots, 0, 66_355_200), session.BufferStateForValidation());
            session.Offer(pixels, Source(slots), slots, Poll(slots));
            release.TrySetResult(); var native = Journal(folder);
            var result = await session.CompleteAsync(native.Path, native.Hash);
            Assert.False(result.Complete); Assert.True(result.WorkerRetired);
            Assert.Equal("shadow_buffer_exhausted", result.Error);
            Assert.Equal(slots, result.FramesAccepted); Assert.Equal(slots, result.FramesWritten);
            Assert.Equal(1, result.FramesRejected); Assert.Equal(1, result.FramesLost);
            Assert.Equal((slots, 0, 0, 0), session.BufferStateForValidation());
            using var manifest = JsonDocument.Parse(File.ReadAllBytes(result.ManifestPath!));
            Assert.Equal(slots, manifest.RootElement.GetProperty("rawBufferSlots").GetInt32());
            Assert.Equal(66_355_200, manifest.RootElement.GetProperty("maximumRawBytes").GetInt32());
            Assert.Equal(2, manifest.RootElement.GetProperty("rawBankCount").GetInt32());
            Assert.Equal(slots, manifest.RootElement.GetProperty("rawSlotsHighWater").GetInt32());
            Assert.Equal(0, manifest.RootElement.GetProperty("rawSlotsInUse").GetInt32());
        }
        finally { release.TrySetResult(); await session.DisposeAsync(); if (session.Snapshot().WorkerRetired) Directory.Delete(folder, true); }
    }

    /// <summary>All raw slots, including the first, can be overwritten during a write stall without altering its RGB bytes.</summary>
    [Fact]
    public async Task EarlyRawReturnAllowsReuseWhileWriterOwnsSeparateRgb()
    {
        var folder = Folder(); var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var session = new NavigationBaselineShadowCapture(Path.Combine(folder, "shadow"), Run, 123, 3, "blocking",
            afterResizeBeforeWrite: async ct => { entered.TrySetResult(); await release.Task.WaitAsync(ct); });
        try
        {
            await session.InitializeAsync(CancellationToken.None);
            using (var pixels = new Mat(8, 12, MatType.CV_8UC3, new Scalar(11, 22, 33)))
            {
                session.Offer(pixels, Source(0), 0, Poll(0));
                await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
                Assert.Equal((8, 0, 8, 66_355_200), session.BufferStateForValidation());
                for (var i = 1; i <= 8; i++)
                {
                    pixels.SetTo(new Scalar(11 + i, 22 + i, 33 + i));
                    session.Offer(pixels, Source(i), i, Poll(i));
                }
                Assert.Equal((8, 8, 0, 66_355_200), session.BufferStateForValidation());
                pixels.SetTo(Scalar.Black);
            }
            release.TrySetResult(); var native = Journal(folder);
            var result = await session.CompleteAsync(native.Path, native.Hash);
            Assert.True(result.Complete); Assert.True(result.WorkerRetired);
            Assert.Equal(9, result.FramesAccepted); Assert.Equal(9, result.FramesWritten); Assert.Equal(0, result.FramesLost);
            Assert.Equal((8, 0, 0, 0), session.BufferStateForValidation());
            using var manifest = JsonDocument.Parse(File.ReadAllBytes(result.ManifestPath!));
            var root = manifest.RootElement;
            Assert.Equal(8, root.GetProperty("rawSlotsHighWater").GetInt32());
            Assert.Equal(8, root.GetProperty("pendingHighWater").GetInt32());
            Assert.Equal(0, root.GetProperty("rawSlotsInUse").GetInt32());
            var totalResize = 0d; var totalWrite = 0d;
            foreach (var row in root.GetProperty("frames").EnumerateArray())
            {
                var index = row.GetProperty("frame").GetProperty("frameIndex").GetInt32();
                var expected = new byte[192 * 192 * 3];
                for (var i = 0; i < expected.Length; i += 3)
                { expected[i] = (byte)(33 + index); expected[i + 1] = (byte)(22 + index); expected[i + 2] = (byte)(11 + index); }
                var bytes = File.ReadAllBytes(Path.Combine(folder, "shadow", row.GetProperty("file").GetString()!));
                Assert.Equal(expected, bytes);
                Assert.Equal(row.GetProperty("sha256").GetString(), Convert.ToHexString(SHA256.HashData(bytes)));
                var timing = row.GetProperty("processing");
                var resize = timing.GetProperty("resizeMs").GetDouble(); var write = timing.GetProperty("writeMs").GetDouble();
                Assert.True(double.IsFinite(resize) && resize >= 0); Assert.True(double.IsFinite(write) && write >= 0);
                Assert.True(timing.GetProperty("queueWaitMs").GetDouble() >= 0);
                Assert.True(timing.GetProperty("workerDequeuedAtTicks").GetInt64() <= timing.GetProperty("resizeStartedAtTicks").GetInt64());
                Assert.True(timing.GetProperty("resizeStartedAtTicks").GetInt64() <= timing.GetProperty("resizeCompletedAtTicks").GetInt64());
                Assert.True(timing.GetProperty("resizeCompletedAtTicks").GetInt64() <= timing.GetProperty("rawReturnedAtTicks").GetInt64());
                Assert.True(timing.GetProperty("rawReturnedAtTicks").GetInt64() <= timing.GetProperty("writeStartedAtTicks").GetInt64());
                Assert.True(timing.GetProperty("writeStartedAtTicks").GetInt64() <= timing.GetProperty("writeCompletedAtTicks").GetInt64());
                totalResize += resize; totalWrite += write;
            }
            Assert.Equal(totalResize, root.GetProperty("workerResizeTotalMs").GetDouble(), 6);
            Assert.Equal(totalWrite, root.GetProperty("workerWriteTotalMs").GetDouble(), 6);
        }
        finally { release.TrySetResult(); await session.DisposeAsync(); if (session.Snapshot().WorkerRetired) Directory.Delete(folder, true); }
    }

    /// <summary>Returning all raw memory does not release the global worker slot or reset the original two-second drain.</summary>
    [Fact]
    public async Task PostResizeWriteStallStillRetainsWorkerReservation()
    {
        var folder = Folder(); var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        await using var session = new NavigationBaselineShadowCapture(Path.Combine(folder, "shadow"), Run, 123, 3, "blocking",
            afterResizeBeforeWrite: _ => { entered.TrySetResult(); return release.Task; });
        try
        {
            await session.InitializeAsync(CancellationToken.None);
            using var pixels = new Mat(8, 12, MatType.CV_8UC3, Scalar.White);
            session.Offer(pixels, Source(0), 0, Poll(0)); await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal((8, 0, 8, 66_355_200), session.BufferStateForValidation());
            var native = Journal(folder); var result = await session.CompleteAsync(native.Path, native.Hash);
            Assert.False(result.Complete); Assert.False(result.WorkerRetired);
            Assert.Equal("shadow_worker_retirement_timeout", result.Error);
            Assert.Equal(66_355_200, session.BufferStateForValidation().ReservedBytes);
            Assert.Throws<InvalidOperationException>(() => new NavigationBaselineShadowCapture(Path.Combine(folder, "other"), Run, 123, 3, "blocking"));
            // A second close uses the original deadline rather than granting another drain window.
            var second = await session.CompleteAsync(native.Path, native.Hash);
            Assert.False(second.WorkerRetired); Assert.Equal(result.Error, second.Error);
        }
        finally
        {
            release.TrySetResult(); var elapsed = Stopwatch.StartNew();
            while (!session.Snapshot().WorkerRetired && elapsed.Elapsed < TimeSpan.FromSeconds(5)) await Task.Delay(1);
            await session.DisposeAsync(); Assert.True(session.Snapshot().WorkerRetired);
            Assert.Equal((8, 0, 0, 0), session.BufferStateForValidation()); Directory.Delete(folder, true);
        }
    }

    /// <summary>A write failure after early return cannot double-return raw slots or produce a complete archive.</summary>
    [Fact]
    public async Task PostResizeWriteFailureReturnsRawExactlyOnce()
    {
        var folder = Folder();
        await using var session = new NavigationBaselineShadowCapture(Path.Combine(folder, "shadow"), Run, 123, 3, "blocking",
            afterResizeBeforeWrite: _ => Task.FromException(new IOException("synthetic post-resize failure")));
        try
        {
            await session.InitializeAsync(CancellationToken.None);
            using var pixels = new Mat(8, 12, MatType.CV_8UC3, Scalar.White);
            session.Offer(pixels, Source(0), 0, Poll(0)); var native = Journal(folder);
            var result = await session.CompleteAsync(native.Path, native.Hash);
            Assert.False(result.Complete); Assert.True(result.WorkerRetired); Assert.Equal(1, result.FramesLost);
            Assert.Equal(0, result.FramesWritten); Assert.Null(result.ManifestPath);
            Assert.Contains("synthetic post-resize failure", result.Error);
            Assert.Equal((8, 0, 0, 0), session.BufferStateForValidation());
        }
        finally { await session.DisposeAsync(); if (session.Snapshot().WorkerRetired) Directory.Delete(folder, true); }
    }

}
