using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using Newtonsoft.Json.Linq;
using OpenCvSharp;
using System.IO;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise real native cloning, PNG IO and finite quotas without a game or desktop capture.</summary>
public sealed class AgentReadinessSnapshotsTests
{
    /// <summary>Default-off recording touches no files; visual transitions preserve exact source pixels and timestamps.</summary>
    [Fact]
    public async Task OptInOwnsPixelsAndIgnoresRepeatedVisualEvidence()
    {
        var directory = NewDirectory();
        var recorder = new AgentReadinessSnapshots(directory);
        using var blocked = new ManualResetEventSlim(false);
        var heldRecorder = new AgentReadinessSnapshots(directory, encode: image =>
        {
            Assert.True(blocked.Wait(TimeSpan.FromSeconds(10)));
            return image.ImEncode(".png");
        });
        using var source = new Mat(6, 8, MatType.CV_8UC3, new Scalar(12, 34, 56));
        var observation = Observe(7, AgentWorldEvidence.WorldHud);
        recorder.Observe(source, observation, Ready(7));
        Assert.Equal(0, State(recorder)["admitted"]!.Value<int>());
        Assert.False(Directory.Exists(directory));
        heldRecorder.Configure(true);
        try
        {
            heldRecorder.Observe(source, observation, Ready(7));
            // Focus/freshness epoch changes alone must not create more visual evidence files.
            heldRecorder.Observe(source, Observe(8, AgentWorldEvidence.WorldHud), Ready(8) with { Epoch = 9, Ready = false });
            source.SetTo(Scalar.White);
            source.Dispose();
        }
        finally { blocked.Set(); }
        await heldRecorder.CompleteAsync(TimeSpan.FromSeconds(10));
        var state = State(heldRecorder);
        Assert.Equal(1, state["written"]!.Value<int>());
        Assert.Equal(0, state["pending"]!.Value<int>());
        using var written = Cv2.ImRead(Assert.Single(Directory.GetFiles(directory, "*.png")));
        Assert.Equal(new Vec3b(12, 34, 56), written.At<Vec3b>(0, 0));
        var metadata = JObject.Parse(File.ReadAllText(Assert.Single(Directory.GetFiles(directory, "*.json"))));
        Assert.Equal(7, metadata["frameId"]!.Value<long>());
        Assert.Equal(70, metadata["capturedAtMs"]!.Value<double>());
        Assert.Equal("WorldHud", metadata["evidence"]!.Value<string>());
        Assert.Equal(1, metadata["worldReadiness"]!["epoch"]!.Value<int>());
        Assert.Equal("native_template", metadata["recognition"]!["modalStarConfirmation"]!.Value<string>());
        Assert.Equal(64, metadata["imageSha256"]!.Value<string>()!.Length);
    }

    /// <summary>A blocked writer cannot queue a third native clone, and toggling recording cannot replenish quotas.</summary>
    [Fact]
    public async Task PendingAndLifetimeQuotasNeverBlockCapture()
    {
        using var gate = new ManualResetEventSlim(false);
        var recorder = new AgentReadinessSnapshots(NewDirectory(), maximumFrames: 3, encode: image =>
        {
            Assert.True(gate.Wait(TimeSpan.FromSeconds(10)));
            return image.ImEncode(".png");
        });
        using var pixels = new Mat(6, 8, MatType.CV_8UC4, Scalar.Black);
        recorder.Configure(true);
        try
        {
            recorder.Observe(pixels, Observe(1, AgentWorldEvidence.WorldHud), Ready(1));
            recorder.Observe(pixels, Observe(2, AgentWorldEvidence.BlockingUi), Ready(2));
            recorder.Observe(pixels, Observe(3, AgentWorldEvidence.WorldHud), Ready(3));
            Assert.Equal(2, State(recorder)["pending"]!.Value<int>());
            Assert.Equal(1, State(recorder)["dropped"]!.Value<int>());
        }
        finally { gate.Set(); }
        await recorder.CompleteAsync(TimeSpan.FromSeconds(10));
        recorder.Configure(true);
        recorder.Observe(pixels, Observe(4, AgentWorldEvidence.HudMissing), Ready(4));
        recorder.Observe(pixels, Observe(5, AgentWorldEvidence.WorldHud), Ready(5));
        await recorder.CompleteAsync(TimeSpan.FromSeconds(10));
        Assert.Equal(3, State(recorder)["admitted"]!.Value<int>());
        Assert.Equal(3, State(recorder)["written"]!.Value<int>());
        Assert.Equal(2, State(recorder)["dropped"]!.Value<int>());
        Assert.True(State(recorder)["limitReached"]!.Value<bool>());
    }

    /// <summary>Encoded-byte quotas include metadata and are enforced before any filesystem write.</summary>
    [Fact]
    public async Task ByteLimitRejectsOversizedPairWithoutFiles()
    {
        var directory = NewDirectory();
        var recorder = new AgentReadinessSnapshots(directory, maximumBytes: 16);
        using var pixels = new Mat(6, 8, MatType.CV_8UC3, Scalar.White);
        recorder.Configure(true);
        recorder.Observe(pixels, Observe(1, AgentWorldEvidence.WorldHud), Ready(1));
        await recorder.CompleteAsync(TimeSpan.FromSeconds(10));
        var state = State(recorder);
        Assert.Equal(1, state["dropped"]!.Value<int>());
        Assert.Equal(0, state["failed"]!.Value<int>());
        Assert.Equal(0, state["bytesWritten"]!.Value<long>());
        Assert.True(state["limitReached"]!.Value<bool>());
        Assert.False(Directory.Exists(directory));
    }

    /// <summary>Background failures are counted and owned Mats are disposed without faulting capture or shutdown.</summary>
    [Fact]
    public async Task WriterFailureIsObservedAndDisposesOwnedClone()
    {
        Mat? owned = null;
        var recorder = new AgentReadinessSnapshots(NewDirectory(), encode: image =>
        {
            owned = image;
            throw new IOException("Synthetic encoder failure.");
        });
        using var pixels = new Mat(6, 8, MatType.CV_8UC3, Scalar.White);
        recorder.Configure(true);
        recorder.Observe(pixels, Observe(1, AgentWorldEvidence.HudMissing), Ready(1));
        await recorder.CompleteAsync(TimeSpan.FromSeconds(10));
        Assert.Equal(1, State(recorder)["failed"]!.Value<int>());
        Assert.Equal(0, State(recorder)["pending"]!.Value<int>());
        Assert.NotNull(owned);
        Assert.True(owned.IsDisposed);
        Assert.False(pixels.IsDisposed);
    }

    /// <summary>Produce only tiny test artifacts under the existing ignored build output directory.</summary>
    private static string NewDirectory() => Path.Combine(AppContext.BaseDirectory, "snapshot-tests", Guid.NewGuid().ToString("N"));
    /// <summary>Use a consistent timestamp and image size in exact-source metadata fixtures.</summary>
    private static AgentObservation Observe(long frame, AgentWorldEvidence evidence) => new(frame, frame * 10, 8, 6, evidence, 2.5);
    /// <summary>Provide a deterministic readiness state independently of visual-evidence transition counting.</summary>
    private static AgentWorldReadiness Ready(long frame) => new(true, "world_ready", frame, frame * 10, frame * 10 + 3, 2.5, 1);
    /// <summary>Inspect the same immutable diagnostics object serialized by the bridge.</summary>
    private static JObject State(AgentReadinessSnapshots recorder) => JObject.FromObject(recorder.Snapshot());
}
