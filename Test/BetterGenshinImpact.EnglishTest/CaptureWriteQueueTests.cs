using BetterGenshinImpact.Core.Script.Dependence;
using BetterGenshinImpact.Core.Script;
using Microsoft.ClearScript.V8;
using OpenCvSharp;
using System.IO;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Checks native image ownership and bounded background writer admission.</summary>
public sealed class CaptureWriteQueueTests
{
    /// <summary>The real script host exposes an awaitable method with safe Mat ownership.</summary>
    [Fact]
    public async Task ScriptCanDisposeCaptureBeforeAwaitingItsDurableImage()
    {
        var root = Path.Combine(Path.GetTempPath(), "BetterGI-AsyncCapture-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            using var source = new Mat(2, 2, MatType.CV_8UC1, new Scalar(17));
            bool? saved = null;
            await ScriptExecution.ExecuteAsync(_ =>
            {
                var engine = new V8ScriptEngine(V8ScriptEngineFlags.UseCaseInsensitiveMemberBinding
                    | V8ScriptEngineFlags.EnableTaskPromiseConversion);
                engine.AddHostObject("file", new LimitedFile(root));
                engine.AddHostObject("image", source);
                engine.AddHostObject("publish", new Action<bool>(value => saved = value));
                return engine;
            }, engine => engine.Evaluate("""
                (async () => {
                    if (typeof file.writeImageAsync !== 'function') throw new Error('Missing async image method');
                    const pending = file.writeImageAsync('frame.png', image);
                    image.dispose();
                    publish(await pending);
                })()
                """), CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(15));
            Assert.Equal(true, saved);
            using var written = Cv2.ImRead(Path.Combine(root, "frame.png"), ImreadModes.Grayscale);
            Assert.Equal((byte)17, written.At<byte>(0, 0));
        }
        finally { Directory.Delete(root, true); }
    }

    /// <summary>The queued image survives disposal and mutation of its original capture.</summary>
    [Fact]
    public async Task OwnsSnapshotBeforeReturningAndDisposesItAfterWriting()
    {
        var queue = new CaptureWriteQueue(1);
        using var release = new ManualResetEventSlim();
        using var source = new Mat(2, 2, MatType.CV_8UC1, new Scalar(17));
        Mat? written = null;
        var result = queue.TryWriteAsync(source, snapshot =>
        {
            if (!release.Wait(TimeSpan.FromSeconds(10))) throw new TimeoutException();
            written = snapshot;
            Assert.Equal((byte)17, snapshot.At<byte>(0, 0));
            return true;
        });
        try
        {
            source.SetTo(new Scalar(99));
            source.Dispose();
            Assert.False(result.IsCompleted);
        }
        finally { release.Set(); }

        Assert.True(await result.WaitAsync(TimeSpan.FromSeconds(10)));
        Assert.NotNull(written);
        Assert.True(written.IsDisposed);
    }

    /// <summary>Full admission refuses work immediately and recovers after completion.</summary>
    [Fact]
    public async Task FullQueueRefusesWithoutRetainingAnotherImage()
    {
        var queue = new CaptureWriteQueue(1);
        using var release = new ManualResetEventSlim();
        using var source = new Mat(2, 2, MatType.CV_8UC1, new Scalar(17));
        var first = queue.TryWriteAsync(source, _ => release.Wait(TimeSpan.FromSeconds(10)));
        try
        {
            // A disposed source proves the refused job never even attempts to clone.
            using var disposed = new Mat();
            disposed.Dispose();
            var refused = queue.TryWriteAsync(disposed, _ => throw new InvalidOperationException("Must not run"));
            Assert.True(refused.IsCompletedSuccessfully);
            Assert.False(await refused);
        }
        finally { release.Set(); }

        Assert.True(await first.WaitAsync(TimeSpan.FromSeconds(10)));
        Assert.True(await queue.TryWriteAsync(source, _ => true));
    }

    /// <summary>A failed encoder releases both the image and its admission slot.</summary>
    [Fact]
    public async Task FailedWriterDisposesSnapshotAndAllowsNextWrite()
    {
        var queue = new CaptureWriteQueue(1);
        using var source = new Mat(2, 2, MatType.CV_8UC1, new Scalar(17));
        Mat? written = null;
        var failed = queue.TryWriteAsync(source, snapshot =>
        {
            written = snapshot;
            throw new InvalidOperationException("Encoder failed");
        });
        await Assert.ThrowsAsync<InvalidOperationException>(() => failed);
        Assert.NotNull(written);
        Assert.True(written.IsDisposed);
        Assert.True(await queue.TryWriteAsync(source, _ => true));
    }

    /// <summary>A failed clone cannot permanently consume the sole admission slot.</summary>
    [Fact]
    public async Task FailedCloneReturnsItsSlot()
    {
        var queue = new CaptureWriteQueue(1);
        using var disposed = new Mat();
        disposed.Dispose();
        Assert.Throws<ObjectDisposedException>(() => { _ = queue.TryWriteAsync(disposed, _ => true); });
        using var source = new Mat(2, 2, MatType.CV_8UC1, new Scalar(17));
        Assert.True(await queue.TryWriteAsync(source, _ => true));
    }
}
