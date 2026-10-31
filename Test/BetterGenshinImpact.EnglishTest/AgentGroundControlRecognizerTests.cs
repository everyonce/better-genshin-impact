using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using OpenCvSharp;
using System.IO;
using System.Security.Cryptography;
using Xunit;
using Xunit.Abstractions;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Inert fixed-layout recognition and controller revocation, without assets, OCR, GPU or native input.</summary>
public sealed class AgentGroundControlRecognizerTests(ITestOutputHelper output)
{
    /// <summary>Use exact synthetic E/Q rectangles or the existing yellow swim hint in either supported channel format.</summary>
    [Theory]
    [InlineData(3, false)]
    [InlineData(4, false)]
    [InlineData(3, true)]
    [InlineData(4, true)]
    public void FixedNativeControlsPreserveOriginalPixelsAndInlineCrops(int channels, bool water)
    {
        using var pixels = Pixels(channels, water);
        using var before = pixels.Clone();
        var evidence = AgentGroundControlRecognizer.Recognize(pixels, Frame(1, 100), Normal());
        Assert.Equal("valid", evidence.State);
        Assert.Equal(!water, evidence.GroundControlsConfirmed);
        Assert.Equal(water ? 63 : 0, evidence.SwimHintPixels);
        Assert.False(evidence.PhysicallyGrounded);
        Assert.Equal(19530, evidence.Crops.Sum(c => Convert.FromBase64String(c.RgbBase64).Length));
        foreach (var crop in evidence.Crops)
            Assert.Equal(crop.Sha256, Convert.ToHexString(SHA256.HashData(Convert.FromBase64String(crop.RgbBase64))).ToLowerInvariant());
        Assert.Equal(0d, Cv2.Norm(before, pixels));
    }

    /// <summary>White boxes alone, a substituted glyph, and simultaneous airborne hints cannot grant ground controls.</summary>
    [Theory]
    [InlineData("blank")]
    [InlineData("swap")]
    [InlineData("space")]
    [InlineData("x")]
    public void DistinctGlyphsAndUnambiguousControlsAreRequired(string change)
    {
        using var pixels = Pixels(3, false);
        var motion = Normal();
        if (change == "blank")
        {
            using var region = new Mat(pixels, new Rect(1681, 1024, 40, 31));
            region.SetTo(Scalar.White);
        }
        if (change == "swap") Paint(pixels, AgentGroundControlRecognizer.EPattern, 1804);
        if (change == "space") motion = motion with { SpaceKeyMatched = true };
        if (change == "x") motion = motion with { XKeyMatched = true };
        Assert.False(AgentGroundControlRecognizer.Recognize(pixels, Frame(1, 100), motion).GroundControlsConfirmed);
    }

    /// <summary>The first contract rejects unreviewed geometry and unavailable source/HUD evidence.</summary>
    [Theory]
    [InlineData("720")]
    [InlineData("gray")]
    [InlineData("source")]
    [InlineData("world")]
    public void UnsupportedOrUnavailableCaptureNeverGrantsAdmission(string change)
    {
        using var pixels = change == "720" ? new Mat(720, 1280, MatType.CV_8UC3, Scalar.Black) :
            change == "gray" ? new Mat(1080, 1920, MatType.CV_8UC1, Scalar.Black) : Pixels(3, false);
        var frame = Frame(1, 100);
        if (change == "source") frame = frame with { SourceFrame = null };
        if (change == "world") frame = frame with { WorldEvidence = AgentWorldEvidence.BlockingUi };
        var evidence = AgentGroundControlRecognizer.Recognize(pixels, frame, Normal());
        Assert.Equal("unavailable", evidence.State);
        Assert.False(evidence.GroundControlsConfirmed);
        Assert.Empty(evidence.Crops);
    }

    /// <summary>A newly captured water layout cancels pending/held input under the controller lock and stays terminal.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void WaterRevokesBeforeDispatchAndCannotResumeAfterRelease(bool alreadyApplied)
    {
        var input = new RecordingInput();
        var controller = new AgentActionController(input, true);
        controller.RequireGroundControlLayout(0);
        Assert.False(controller.RegisterFrame(WithControls(1, 100), 101).Ready);
        Assert.True(controller.RegisterFrame(WithControls(2, 133), 134).Ready);
        Assert.Null(controller.Submit(Proposal(2, 133), 140));
        if (alreadyApplied) controller.Tick(140);
        var blocked = controller.RegisterFrame(WithControls(3, 150, true), 151);
        Assert.False(blocked.Ready);
        Assert.Equal("ground_control_stop", blocked.Reason);
        Assert.Empty(input.Held);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal("cancelled", receipt.Status);
        Assert.Equal(alreadyApplied ? 1 : 0, receipt.AppliedSteps.Length);
        controller.Release(160);
        Assert.False(controller.RegisterFrame(WithControls(4, 200), 201).Ready);
        Assert.False(controller.RegisterFrame(WithControls(5, 233), 234).Ready);
        Assert.Equal("world_not_ready", controller.Submit(Proposal(5, 233), 240));
    }

    /// <summary>Missing evidence cannot admit initially; an acknowledged release permits fresh confirmation but not stale input.</summary>
    [Fact]
    public void MissingEvidenceWaitsOnlyBeforeArmingOrAfterAcknowledgedRelease()
    {
        var controller = new AgentActionController(new RecordingInput(), true);
        controller.RequireGroundControlLayout(0);
        Assert.False(controller.RegisterFrame(Frame(1, 100), 101).Ready);
        Assert.False(controller.RegisterFrame(WithControls(2, 133), 134).Ready);
        Assert.True(controller.RegisterFrame(WithControls(3, 166), 167).Ready);
        Assert.Null(controller.Submit(Proposal(3, 166), 170));
        controller.Release(180);
        Assert.False(controller.RegisterFrame(Frame(4, 200), 201).Ready);
        Assert.False(controller.RegisterFrame(WithControls(5, 233), 234).Ready);
        Assert.True(controller.RegisterFrame(WithControls(6, 266), 267).Ready);
        Assert.Null(controller.Submit(Proposal(6, 266), 270));
        Assert.False(controller.RegisterFrame(Frame(7, 280), 281).Ready);
        Assert.False(controller.RegisterFrame(WithControls(8, 310), 311).Ready);
    }

    /// <summary>The old normal/world contract remains unchanged unless this one-way gate is explicitly requested.</summary>
    [Fact]
    public void LegacyControllersStayUnchangedAndLateOrRepeatedOptInIsRejected()
    {
        var controller = new AgentActionController(new RecordingInput(), true);
        Assert.False(controller.RegisterFrame(Frame(1, 100), 101).Ready);
        Assert.True(controller.RegisterFrame(Frame(2, 133), 134).Ready);
        Assert.Null(controller.Submit(Proposal(2, 133), 140));
        Assert.Throws<InvalidOperationException>(() => controller.RequireGroundControlLayout(141));
        var fresh = new AgentActionController(new RecordingInput(), false);
        fresh.RequireGroundControlLayout(0);
        Assert.Throws<InvalidOperationException>(() => fresh.RequireGroundControlLayout(1));
    }

    /// <summary>Explicit optional retained-PNG replay pins both actual R63 images and exercises BGR/BGRA without a game.</summary>
    [Fact]
    public void RetainedDryAndWaterPngsReplayWhenSupplied()
    {
        var paths = Environment.GetEnvironmentVariable("BETTERGI_GROUND_CONTROL_REPLAY_IMAGES");
        if (string.IsNullOrWhiteSpace(paths)) { output.WriteLine("Retained-image replay not requested."); return; }
        var files = paths.Split(';', StringSplitOptions.RemoveEmptyEntries);
        Assert.Equal(2, files.Length);
        var hashes = new[] { "e2d586be955c79eafbf84fec522dac925e571122f93bc81ef21566952109efb8",
            "9787ab4ad4233567015e5290a4c07f4be00803e7635e0129f1967ecbed8aaa5a" };
        for (var i = 0; i < files.Length; i++)
        {
            Assert.Equal(hashes[i], Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(files[i]))).ToLowerInvariant());
            using var bgr = Cv2.ImRead(files[i], ImreadModes.Color);
            using var bgra = new Mat();
            Cv2.CvtColor(bgr, bgra, ColorConversionCodes.BGR2BGRA);
            foreach (var image in new[] { bgr, bgra })
            {
                var result = AgentGroundControlRecognizer.Recognize(image, Frame(1, 100), Normal());
                Assert.Equal(i == 0, result.GroundControlsConfirmed);
                Assert.Equal(i == 0 ? 0 : 40, result.SwimHintPixels);
                // Report warmed native-only latency without making scheduler-sensitive timing assertions.
                for (var warmup = 0; warmup < 5; warmup++)
                    AgentGroundControlRecognizer.Recognize(image, Frame(1, 100), Normal());
                var elapsed = new double[30];
                for (var sample = 0; sample < elapsed.Length; sample++)
                    elapsed[sample] = AgentGroundControlRecognizer.Recognize(image, Frame(1, 100), Normal()).RecognitionMs;
                Array.Sort(elapsed);
                var median = (elapsed[14] + elapsed[15]) / 2;
                var p95 = elapsed[(int)Math.Ceiling(.95 * elapsed.Length) - 1];
                output.WriteLine($"{Path.GetFileName(files[i])}: {image.Channels()} channels, {result.Reason}, " +
                    $"5 warmups, 30 samples, median={median:F4} ms, p95={p95:F4} ms");
            }
        }
    }

    /// <summary>Use one valid immutable QPC source for each synthetic observation.</summary>
    private static AgentObservation Frame(long id, double at) => new(id, at, 1920, 1080, AgentWorldEvidence.WorldHud, 1,
        new AgentSourceFrame("11111111111111111111111111111111", (long)(at * 10000), at, at + .01));
    /// <summary>Retain the existing negative Space/X classification without relabeling it as grounded.</summary>
    private static AgentMotionEvidence Normal() => new(AgentMotionStatus.Normal, "space_key_not_found", AgentMotionEvidence.MethodName, .1, false, false);
    /// <summary>Produce a same-source native layout for controller-only scenarios.</summary>
    private static AgentObservation WithControls(long id, double at, bool water = false)
    {
        using var image = Pixels(3, water);
        var frame = Frame(id, at);
        return frame with { GroundControlEvidence = AgentGroundControlRecognizer.Recognize(image, frame, Normal()) };
    }
    /// <summary>Bound the synthetic action to one original source and a fifty-millisecond W hold.</summary>
    private static AgentRequest Proposal(long id, double at) => new()
    { RequestId = "ground-" + id, ModelId = "inert", FrameId = id, ObservedAtMs = at, ExpiresAtMs = at + 250,
        Steps = [new() { DurationMs = 50, Keys = ["W"] }] };
    /// <summary>Draw only code masks or the already-existing yellow swim-control marker.</summary>
    private static Mat Pixels(int channels, bool water)
    {
        var image = new Mat(1080, 1920, channels == 3 ? MatType.CV_8UC3 : MatType.CV_8UC4, new Scalar(65, 45, 30, 255));
        if (!water) { Paint(image, AgentGroundControlRecognizer.EPattern, 1684); Paint(image, AgentGroundControlRecognizer.QPattern, 1804); }
        else for (var y = 1028; y < 1035; y++) for (var x = 1819; x < 1828; x++) Set(image, x, y, 250, 228, 42);
        return image;
    }
    /// <summary>Render dark glyph, light keycap and ignored antialias colours into the borrowed test image.</summary>
    private static void Paint(Mat image, string[] pattern, int left)
    {
        for (var y = 0; y < 25; y++) for (var x = 0; x < 30; x++)
        { var value = (byte)(pattern[y][x] == '#' ? 50 : pattern[y][x] == '.' ? 240 : 180); Set(image, left + x, 1027 + y, value, value, value); }
    }
    /// <summary>Write RGB meaning through either native BGR representation.</summary>
    private static void Set(Mat image, int x, int y, byte r, byte g, byte b)
    { if (image.Channels() == 3) image.Set(y, x, new Vec3b(b, g, r)); else image.Set(y, x, new Vec4b(b, g, r, 255)); }
    /// <summary>Record only software-held keys; no Windows input implementation is reachable.</summary>
    private sealed class RecordingInput : IAgentInput
    {
        /// <inheritdoc />
        public bool IsAvailable => true;
        /// <summary>Last synthetic held-key state.</summary>
        public string[] Held { get; private set; } = [];
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) => Held = keys.ToArray();
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) { }
        /// <inheritdoc />
        public void ReleaseAll() => Held = [];
    }
}
