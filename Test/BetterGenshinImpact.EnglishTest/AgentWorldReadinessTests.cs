using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Recognition;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.Model.Area;
using OpenCvSharp;
using System.IO;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>World/menu/focus transitions without a game, GPU inference, or Windows input.</summary>
public sealed class AgentWorldReadinessTests
{
    /// <summary>Unknown evidence and isolated positive matches never authorize gameplay.</summary>
    [Fact]
    public void RequiresTwoConsecutivePositiveCaptures()
    {
        var gate = new AgentWorldReadinessGate();
        Assert.False(gate.Observe(Frame(1, 100, AgentWorldEvidence.Unknown), 101).Ready);
        Assert.False(gate.Observe(Frame(2, 133), 134).Ready);
        Assert.False(gate.Observe(Frame(3, 166, AgentWorldEvidence.HudMissing), 167).Ready);
        Assert.False(gate.Observe(Frame(4, 199), 200).Ready);
        var ready = gate.Observe(Frame(5, 232) with { RecognitionMs = 2.5 }, 235);
        Assert.True(ready.Ready);
        Assert.Equal(5, ready.SourceFrameId);
        Assert.Equal(232, ready.SourceCapturedAtMs);
        Assert.Equal(235, ready.CheckedAtMs);
        Assert.Equal(2.5, ready.RecognitionMs);
    }

    /// <summary>All negative decisions cancel both queued and already-applied chunks immediately.</summary>
    [Theory]
    [InlineData(AgentWorldEvidence.Unknown, false)]
    [InlineData(AgentWorldEvidence.HudMissing, false)]
    [InlineData(AgentWorldEvidence.BlockingUi, false)]
    [InlineData(AgentWorldEvidence.RecognitionFailed, false)]
    [InlineData(AgentWorldEvidence.Unknown, true)]
    [InlineData(AgentWorldEvidence.HudMissing, true)]
    [InlineData(AgentWorldEvidence.BlockingUi, true)]
    [InlineData(AgentWorldEvidence.RecognitionFailed, true)]
    public void NegativeFrameCancelsAndRequiresNewWorldObservations(AgentWorldEvidence evidence, bool applyBeforeBlock)
    {
        var input = new RecordingInput();
        var controller = ReadyController(input);
        Assert.Null(controller.Submit(Proposal("before", 2, 100), 110));
        if (applyBeforeBlock) controller.Tick(110);
        var blocked = controller.RegisterFrame(Frame(3, 133, evidence), 134);
        Assert.False(blocked.Ready);
        Assert.Empty(input.Held);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal("cancelled", receipt.Status);
        Assert.Equal(applyBeforeBlock ? 1 : 0, receipt.AppliedSteps.Length);
        Assert.Equal("world_not_ready", controller.Submit(Proposal("late", 2, 100), 140));
        Assert.False(controller.RegisterFrame(Frame(4, 166), 167).Ready);
        Assert.True(controller.RegisterFrame(Frame(5, 199), 200).Ready);
        Assert.Equal("unknown_frame", controller.Submit(Proposal("old", 2, 100), 205));
        Assert.Null(controller.Submit(Proposal("new", 5, 199), 205));
        controller.Tick(205);
        Assert.Equal(new[] { "W" }, input.Held);
    }

    /// <summary>A stalled capture loop revokes input even though its proposed action deadline is later.</summary>
    [Fact]
    public void CaptureFreshnessIsIndependentOfActionDeadline()
    {
        var input = new RecordingInput();
        var controller = ReadyController(input);
        var proposal = Proposal("moving", 2, 100) with
        {
            ExpiresAtMs = 400,
            Steps = [new() { DurationMs = 100, Keys = ["W"] }, new() { DurationMs = 100, Keys = ["W"] }]
        };
        Assert.Null(controller.Submit(proposal, 110));
        controller.Tick(110);
        controller.Tick(251);
        Assert.Empty(input.Held);
        Assert.Equal("world_observation_stale", Assert.Single(controller.DrainReceipts()).Reason);
    }

    /// <summary>Late recognition started before focus loss cannot reopen the gate after focus returns.</summary>
    [Fact]
    public void InFlightCaptureCannotCrossFocusInterruption()
    {
        var input = new RecordingInput();
        var controller = ReadyController(input);
        input.IsAvailable = false;
        controller.Tick(120);
        input.IsAvailable = true;
        var late = controller.RegisterFrame(Frame(3, 115), 130);
        Assert.False(late.Ready);
        Assert.Equal("world_observation_invalidated", late.Reason);
        Assert.False(controller.RegisterFrame(Frame(4, 145), 146).Ready);
        Assert.True(controller.RegisterFrame(Frame(5, 178), 179).Ready);
        Assert.Equal("unknown_frame", controller.Submit(Proposal("late", 3, 115), 180));
    }

    /// <summary>Explicit release clears queued/held input without permanently stopping the session.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void ReleaseAllowsOnlyFreshConfirmedActions(bool applyBeforeRelease)
    {
        var input = new RecordingInput();
        var controller = ReadyController(input);
        Assert.Null(controller.Submit(Proposal("before", 2, 100), 110));
        if (applyBeforeRelease) controller.Tick(110);
        controller.Release(120);
        Assert.Empty(input.Held);
        Assert.Equal("client_release", Assert.Single(controller.DrainReceipts()).Reason);
        Assert.False(controller.RegisterFrame(Frame(3, 115), 130).Ready);
        Assert.False(controller.RegisterFrame(Frame(4, 145), 146).Ready);
        Assert.True(controller.RegisterFrame(Frame(5, 178), 179).Ready);
        Assert.Equal("unknown_frame", controller.Submit(Proposal("old", 2, 100), 180));
        Assert.Null(controller.Submit(Proposal("fresh", 5, 178), 180));
        controller.Tick(180);
        Assert.Equal(new[] { "W" }, input.Held);
    }

    /// <summary>Polling blocked frames is one interruption; a hidden block/resume remains visible by epoch.</summary>
    [Fact]
    public void EpochChangesOncePerInterruptionAndOnExplicitRelease()
    {
        var input = new RecordingInput();
        var controller = ReadyController(input);
        var initial = controller.GetWorldReadiness(110).Epoch;
        var blocked = controller.RegisterFrame(Frame(3, 133, AgentWorldEvidence.HudMissing), 134);
        Assert.Equal(initial + 1, blocked.Epoch);
        Assert.Equal(blocked.Epoch, controller.RegisterFrame(Frame(4, 166, AgentWorldEvidence.HudMissing), 167).Epoch);
        Assert.Equal(blocked.Epoch, controller.GetWorldReadiness(170).Epoch);
        controller.RegisterFrame(Frame(5, 199), 200);
        var resumed = controller.RegisterFrame(Frame(6, 232), 233);
        Assert.True(resumed.Ready);
        Assert.Equal(blocked.Epoch, resumed.Epoch);
        controller.Release(240);
        Assert.Equal(resumed.Epoch + 1, controller.GetWorldReadiness(241).Epoch);
        controller.Release(242);
        Assert.Equal(resumed.Epoch + 2, controller.GetWorldReadiness(243).Epoch);
    }

    /// <summary>Hot captures during continuous focus loss retain one interruption generation.</summary>
    [Fact]
    public void PositiveCapturesWhileUnfocusedDoNotAdvanceEpochRepeatedly()
    {
        var input = new RecordingInput();
        var controller = ReadyController(input);
        var initialEpoch = controller.GetWorldReadiness(110).Epoch;
        Assert.Null(controller.Submit(Proposal("moving", 2, 100), 110));
        controller.Tick(110);
        input.IsAvailable = false;
        var blocked = controller.RegisterFrame(Frame(3, 133), 134);
        Assert.False(blocked.Ready);
        Assert.Equal("window_unavailable", blocked.Reason);
        Assert.Equal(initialEpoch + 1, blocked.Epoch);
        Assert.Empty(input.Held);
        Assert.Equal("window_unavailable", Assert.Single(controller.DrainReceipts()).Reason);
        Assert.Equal(blocked.Epoch, controller.GetWorldReadiness(140).Epoch);
        Assert.Equal(blocked.Epoch, controller.RegisterFrame(Frame(4, 166), 167).Epoch);
        var stillBlocked = controller.RegisterFrame(Frame(5, 199), 200);
        Assert.False(stillBlocked.Ready);
        Assert.Equal(5, stillBlocked.SourceFrameId);
        Assert.Equal(blocked.Epoch, stillBlocked.Epoch);
        input.IsAvailable = true;
        Assert.False(controller.RegisterFrame(Frame(6, 232), 233).Ready);
        var resumed = controller.RegisterFrame(Frame(7, 265), 266);
        Assert.True(resumed.Ready);
        Assert.Equal(blocked.Epoch, resumed.Epoch);
        Assert.Equal("unknown_frame", controller.Submit(Proposal("old", 2, 100), 270));
        Assert.Null(controller.Submit(Proposal("fresh", 7, 265), 270));
    }

    /// <summary>Neither one repeated frame nor a slow old recognition can provide positive confirmation.</summary>
    [Fact]
    public void ReplayedAndStaleRecognitionCannotConfirmWorld()
    {
        var gate = new AgentWorldReadinessGate();
        Assert.False(gate.Observe(Frame(1, 100), 101).Ready);
        Assert.False(gate.Observe(Frame(1, 100), 102).Ready);
        Assert.False(gate.Observe(Frame(2, 133), 134).Ready);
        Assert.False(gate.Observe(Frame(3, 166), 317).Ready);
        Assert.False(gate.Observe(Frame(4, 330), 331).Ready);
        Assert.True(gate.Observe(Frame(5, 363), 364).Ready);
    }

    /// <summary>A capture gap resets confirmation and epoch even when input ticks were also delayed.</summary>
    [Fact]
    public void LongGapCannotPreserveAnEarlierConfirmation()
    {
        var gate = new AgentWorldReadinessGate();
        gate.Observe(Frame(1, 100), 101);
        Assert.True(gate.Observe(Frame(2, 133), 134).Ready);
        var afterGap = gate.Observe(Frame(3, 400), 401);
        Assert.False(afterGap.Ready);
        Assert.Equal(1, afterGap.Epoch);
        Assert.True(gate.Observe(Frame(4, 433), 434).Ready);
    }

    /// <summary>The shipped HUD template authorizes recognition; adding a shipped modal defeats that match.</summary>
    [Fact]
    public void ShippedTemplatesRejectModalEvenWithHudBehindIt()
    {
        using var templates = new TemplateFixture(1920, 1080);
        using var pixels = new Mat(1080, 1920, MatType.CV_8UC3, Scalar.Black);
        PasteTemplate(pixels, templates.Hud);
        Assert.Equal(AgentWorldEvidence.WorldHud, AgentWorldRecognizer.Recognize(pixels, templates.Get));
        PasteTemplate(pixels, templates.Modal);
        Assert.Equal(AgentWorldEvidence.BlockingUi, AgentWorldRecognizer.Recognize(pixels, templates.Get));
        Assert.False(pixels.IsDisposed);
    }

    /// <summary>Blank capture failure frames must not produce a world-ready false positive.</summary>
    [Theory]
    [InlineData(0)]
    [InlineData(255)]
    public void UniformCaptureIsNotWorld(int brightness)
    {
        using var templates = new TemplateFixture(1280, 720);
        using var pixels = new Mat(720, 1280, MatType.CV_8UC4, Scalar.All(brightness));
        Assert.Equal(AgentWorldEvidence.HudMissing, AgentWorldRecognizer.Recognize(pixels, templates.Get));
    }

    /// <summary>Read existing template pixels directly; the general asset loader starts App through its logger.</summary>
    private sealed class TemplateFixture : IDisposable
    {
        /// <summary>Owned fixture templates, keyed identically to production asset requests.</summary>
        private readonly Dictionary<(string Task, string Name), RecognitionObject> _templates = [];
        /// <summary>World HUD template used to compose a synthetic gameplay frame.</summary>
        public RecognitionObject Hud => _templates[(@"Common\Element", "PaimonMenu")];
        /// <summary>Modal decoration used to compose a blocking overlay.</summary>
        public RecognitionObject Modal => _templates[(@"Common\Element", "PromptDialogLeftBottomStar")];

        /// <summary>Use the shipped imagery and its three existing rectangular search regions.</summary>
        public TemplateFixture(int width, int height)
        {
            Add(@"Common\Element", "PaimonMenu", "paimon_menu.png", new Rect(0, 0, width / 4, height / 4), width);
            Add(@"Common\Element", "PromptDialogLeftBottomStar", "prompt_dialog_left_bottom_star.png",
                new Rect(0, height / 2, width / 2, height - height / 2), width);
            Add("AutoFight", "Confirm", "confirm.png", new Rect(width / 2, height / 2, width / 2, height / 2), width);
        }

        /// <summary>Return the same owned template for each recognition call; no asset logger is initialized.</summary>
        public RecognitionObject Get(string task, string name, ImageRegion region) => _templates[(task, name)];

        /// <summary>Decode an existing CPU image and normalize its scale for the fixture viewport.</summary>
        private void Add(string task, string name, string file, Rect roi, int width)
        {
            using var original = Cv2.ImRead(Path.Combine(AppContext.BaseDirectory, "GameTask", task, "Assets", "1920x1080", file));
            Assert.False(original.Empty());
            var template = new Mat();
            Cv2.Resize(original, template, new Size((int)(original.Width * width / 1920.0),
                (int)(original.Height * width / 1920.0)), interpolation: InterpolationFlags.Area);
            _templates[(task, name)] = new RecognitionObject
            {
                RecognitionType = RecognitionTypes.TemplateMatch, TemplateImageMat = template,
                RegionOfInterest = roi, DrawOnWindow = false
            }.InitTemplate();
        }

        /// <summary>Release fixture images after synthetic recognition has finished.</summary>
        public void Dispose()
        {
            foreach (var template in _templates.Values)
            {
                template.TemplateImageGreyMat?.Dispose();
                template.TemplateImageMat?.Dispose();
            }
        }
    }

    /// <summary>Place an existing template inside its configured ROI, with no screen capture or new assets.</summary>
    private static void PasteTemplate(Mat pixels, RecognitionObject recognition)
    {
        var template = recognition.TemplateImageMat!;
        var roi = recognition.RegionOfInterest;
        using var target = new Mat(pixels, new Rect(roi.X + 8, roi.Y + 8, template.Width, template.Height));
        template.CopyTo(target);
    }

    /// <summary>Construct one immutable recognition result in the server's monotonic clock.</summary>
    private static AgentObservation Frame(long id, double time, AgentWorldEvidence evidence = AgentWorldEvidence.WorldHud) =>
        new(id, time, 1920, 1080, evidence, 1);

    /// <summary>Start a fake controller after two distinct, positive observations.</summary>
    private static AgentActionController ReadyController(RecordingInput input)
    {
        var controller = new AgentActionController(input, true);
        controller.RegisterFrame(Frame(1, 60), 61);
        controller.RegisterFrame(Frame(2, 100), 101);
        return controller;
    }

    /// <summary>A short valid proposal tied to the exact source image.</summary>
    private static AgentRequest Proposal(string id, long frame, double time) => new()
    {
        RequestId = id, ModelId = "world-test", FrameId = frame, ObservedAtMs = time, ExpiresAtMs = time + 250,
        Steps = [new() { DurationMs = 50, Keys = ["W"] }]
    };

    /// <summary>Only records desired state; never invokes the Windows input backend.</summary>
    private sealed class RecordingInput : IAgentInput
    {
        /// <inheritdoc />
        public bool IsAvailable { get; set; } = true;
        /// <summary>Current fake held state.</summary>
        public string[] Held { get; private set; } = [];
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) => Held = keys.ToArray();
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) { }
        /// <inheritdoc />
        public void ReleaseAll() => Held = [];
    }
}
