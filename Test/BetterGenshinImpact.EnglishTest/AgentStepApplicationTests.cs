using System;
using System.Linq;
using System.Buffers.Binary;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask.AutoAgent;
using Newtonsoft.Json.Serialization;
using System.Security.Cryptography;
using System.Text;
using BetterGenshinImpact.Core.Agent;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Inert producer, serialization, framed-codec and controller tests; no live input or stream lifecycle is started.</summary>
public sealed class AgentStepApplicationTests
{
    /// <summary>Nonempty native capture epoch in the exact GUID N format required by the current readiness gate.</summary>
    private const string CaptureEpoch = "11111111111111111111111111111111";
    /// <summary>Production activation remains absent regardless of fixture composition.</summary>
    [Fact]
    public void CapabilityRemainsUnavailable() => Assert.False(AgentStepApplicationWire.Available);

    /// <summary>An explicit JSON null cannot disappear into legacy input routing.</summary>
    [Fact]
    public void NullExtensionPresenceSurvivesDeserialization()
    {
        var value = JsonConvert.DeserializeObject<AgentRequest>("{\"stepApplication\":null,\"stepApplicationsAck\":null}")!;
        Assert.True(value.HasStepApplicationEnvelope); Assert.True(value.HasStepApplicationsAck);
    }

    /// <summary>Duplicate fields are rejected even when nested inside the detached binding.</summary>
    [Fact]
    public void DuplicatePropertiesAreRejected() => Assert.ThrowsAny<Exception>(() => AgentStepApplicationWire.Parse("{\"x\":1,\"x\":2}", 1024));

    /// <summary>New authority JSON excludes permissive Json.NET syntax extensions as well as duplicate fields.</summary>
    [Fact]
    public void NonJsonNormalizationIsRejected()
    {
        foreach (var source in new[] { "{'x':1}", "{\"x\":1,}", "{\"x\":/*comment*/1}" })
            Assert.ThrowsAny<Exception>(() => AgentStepApplicationWire.Parse(source, 1024));
    }

    /// <summary>The corrected UTF-8 reservation excludes DEL at the server boundary too.</summary>
    [Fact]
    public void DelCannotEnterConfiguration()
    {
        var config = Config(); config["backendEpoch"] = "bad\u007f";
        Assert.Throws<InvalidOperationException>(() => new AgentStepApplicationOutbox(config, State()));
    }

    /// <summary>Exact request comparison does not coerce integer identities or clock token types.</summary>
    [Fact]
    public void TypedWireMismatchIsRejected()
    {
        var request = Request(); request.RawApplicationRequest!["observedAtMs"] = 120;
        Assert.Throws<InvalidOperationException>(() => AgentStepApplicationWire.Binding(request, Config()));
    }

    /// <summary>Signed zero cannot be normalized across the detached exact-double request comparison.</summary>
    [Fact]
    public void SignedZeroIsNotNormalized() => Assert.False(AgentStepApplicationWire.Same(new JValue(0.0), new JValue(-0.0)));

    /// <summary>Neither arbitrary extra fields nor aliases can be hidden by DTO deserialization.</summary>
    [Fact]
    public void UnknownSubmissionFieldsAreRejected()
    {
        var request = Request(); var submission = AgentStepApplicationWire.Parse((string)request.StepApplication!["submissionJson"]!, 16384);
        submission["unknown"] = 1; request.RawApplicationRequest!["unknown"] = 1;
        request.StepApplication["submissionJson"] = AgentStepApplicationWire.Freeze(submission, 16384);
        Assert.Throws<InvalidOperationException>(() => AgentStepApplicationWire.Binding(request, Config()));
    }

    /// <summary>Complete empty evaluation has a held return marker and zero backend calls.</summary>
    [Fact]
    public void NoopEvaluationProducesExplicitCompleteRecord()
    {
        var input = new FakeInput(); var controller = Controller(input); controller.ConfigureStepApplications(Config());
        Assert.Null(controller.Submit(Request(), 130)); controller.Tick(130);
        var row = (JObject)controller.StepApplicationExtensions()!["stepApplications"]!["records"]![0]!;
        Assert.Equal("complete_returned", (string?)row["outcome"]); Assert.Empty((JArray)row["calls"]!);
        Assert.Equal("returned", (string?)row["heldEvaluation"]); Assert.Empty(controller.DrainReceipts());
    }

    /// <summary>Mouse evidence uses an explicit JSON-null key before strict validation or serialization.</summary>
    [Fact]
    public void MouseEvidenceHasExplicitNullKeyBeforeSerialization()
    {
        var ticks = 1000L;
        var proof = new AgentStepApplicationEvidence(() => ++ticks, State(), "backend", 1000);
        proof.HeldCompleted();
        proof.Call("mouseMove", null, 2, -1, () => { });
        var after = State(); after["generation"] = 1L;
        var row = proof.Finish(after, "backend", true);
        var call = Assert.Single((JArray)row["calls"]!);
        Assert.Equal(JTokenType.Null, call["key"]!.Type);
        Assert.Equal(2, (int)call["mouseDx"]!); Assert.Equal(-1, (int)call["mouseDy"]!);
    }

    /// <summary>A retained held key requires a new complete evaluation marker, not a fabricated backend call.</summary>
    [Fact]
    public void InheritedKeyEvaluationRequiresNoTransition()
    {
        var input = new FakeInput("W"); var outbox = new AgentStepApplicationOutbox(Config(), input.ApplicationTrackedState);
        var request = Request(keys: ["W"]); outbox.Admitted("request", outbox.CheckSubmission(request));
        var tick = 1000L; var proof = outbox.Reserve("request", input, () => ++tick);
        proof.HeldCompleted(); input.EndApplication(true, ["W"]);
        outbox.Complete("request", proof.Finish(input.ApplicationTrackedState, "backend", true));
        var row = outbox.Extensions()["stepApplications"]!["records"]![0]!;
        Assert.Empty((JArray)row["calls"]!); Assert.Equal("W", (string?)row["trackedAfter"]!["keys"]![0]);
    }

    /// <summary>Returned software application precedes the separate legacy horizon terminal.</summary>
    [Fact]
    public void HorizonTerminalLinksTheExactApplication()
    {
        var input = new FakeInput(); var controller = Controller(input); controller.ConfigureStepApplications(Config());
        Assert.Null(controller.Submit(Request(), 130)); controller.Tick(130); controller.Tick(180);
        var extensions = controller.StepApplicationExtensions()!;
        var terminal = extensions["stepApplicationTerminals"]![0]!;
        Assert.Equal(1, terminal["applicationSequences"]![0]!.Value<int>());
        Assert.Equal("returned_unverified", (string?)terminal["releaseOutcome"]);
        Assert.Equal("completed", Assert.Single(controller.DrainReceipts()).Status);
    }

    /// <summary>Acknowledgment validates all fields before deleting even a valid application prefix.</summary>
    [Fact]
    public void UnknownTerminalAckCannotPartiallyRemoveApplication()
    {
        var input = new FakeInput(); var controller = Controller(input); controller.ConfigureStepApplications(Config());
        Assert.Null(controller.Submit(Request(), 130)); controller.Tick(130);
        var before = AgentStepApplicationWire.Freeze(controller.StepApplicationExtensions()!, 65536);
        Assert.Throws<InvalidOperationException>(() => controller.AcknowledgeStepApplications(Ack(1, "unpublished")));
        Assert.Equal(before, AgentStepApplicationWire.Freeze(controller.StepApplicationExtensions()!, 65536));
    }

    /// <summary>Application and terminal ACKs are independently validated and idempotent after retention.</summary>
    [Fact]
    public void ValidAckRemovesOnlyTheRetainedPrefix()
    {
        var input = new FakeInput(); var controller = Controller(input); controller.ConfigureStepApplications(Config());
        Assert.Null(controller.Submit(Request(), 130)); controller.Tick(130); controller.Tick(180);
        controller.AcknowledgeStepApplications(Ack(1, "request")); controller.AcknowledgeStepApplications(Ack(1, "request"));
        Assert.Empty((JArray)controller.StepApplicationExtensions()!["stepApplications"]!["records"]!);
        Assert.Empty((JArray)controller.StepApplicationExtensions()!["stepApplicationTerminals"]!);
    }

    /// <summary>An input exception remains primary and the outbox explicitly reports lost authority.</summary>
    [Fact]
    public void PartialCallFailureRetainsFailureAndPoisonsAuthority()
    {
        var input = new FakeInput { ThrowMouse = true }; var controller = Controller(input); controller.ConfigureStepApplications(Config());
        Assert.Null(controller.Submit(Request(1), 130));
        Assert.Equal("input_failure", Assert.Throws<InvalidOperationException>(() => controller.Tick(130)).Message);
        var batch = controller.StepApplicationExtensions()!["stepApplications"]!;
        Assert.True(batch["authorityLost"]!.Value<bool>());
        Assert.Equal("partial_failed", (string?)batch["records"]![0]!["outcome"]);
        Assert.Equal("failed", (string?)batch["records"]![0]!["calls"]![0]!["stage"]);
    }

    /// <summary>A clock failure after a failed input call cannot replace that input exception.</summary>
    [Fact]
    public void FailedObserverPreservesPrimaryBackendError()
    {
        var count = 0; var proof = new AgentStepApplicationEvidence(() => ++count < 3 ? 1000 + count : throw new Exception("clock"), State(), "backend", 1000);
        Assert.Equal("primary", Assert.Throws<InvalidOperationException>(() => proof.Call("keyDown", "W", 0, 0, () => throw new InvalidOperationException("primary"))).Message);
    }

    /// <summary>Regressing clocks fail before any wrapped invocation.</summary>
    [Fact]
    public void ClockRegressionCannotDispatch()
    {
        var tick = 1001L; var invoked = false; var proof = new AgentStepApplicationEvidence(() => tick--, State(), "backend", 1000);
        Assert.Throws<InvalidOperationException>(() => proof.Call("keyDown", "W", 0, 0, () => invoked = true)); Assert.False(invoked);
    }

    /// <summary>Legacy receipt fields and default-off controller behavior stay available without the new channel.</summary>
    [Fact]
    public void LegacyControllerDoesNotProduceApplications()
    {
        var input = new FakeInput(); var controller = Controller(input);
        var request = new AgentRequest { RequestId = "legacy", ModelId = "model", FrameId = 2, ObservedAtMs = 120,
            ExpiresAtMs = 500, Steps = [new() { DurationMs = 50, Keys = [] }] };
        Assert.Null(controller.Submit(request, 130)); controller.Tick(130); controller.Tick(180);
        Assert.Null(controller.StepApplicationExtensions()); Assert.Equal("completed", Assert.Single(controller.DrainReceipts()).Status);
    }

    /// <summary>A request cannot opt itself in while the server has no configured authority channel.</summary>
    [Fact]
    public void ExtensionCannotActivateLegacyController()
    {
        var controller = Controller(new FakeInput());
        Assert.Equal("step_applications_unavailable", controller.Submit(Request(), 130));
    }

    /// <summary>Replacement/longer holds need a separate mapping contract, so this initial mode refuses replacement.</summary>
    [Fact]
    public void ActiveHorizonCannotBeReplacedInInitialMode()
    {
        var controller = Controller(new FakeInput()); controller.ConfigureStepApplications(Config());
        Assert.Null(controller.Submit(Request(), 130));
        Assert.Equal("step_application_active_horizon", controller.Submit(Request(requestId: "second"), 131));
    }

    /// <summary>Reservation overhead cannot silently bypass the existing first-dispatch deadline.</summary>
    [Fact]
    public void PostReservationDeadlineRecheckCancelsWithoutApplication()
    {
        var clockCalls = 0; var clock = 130.0;
        var input = new FakeInput(); var controller = Controller(input, () => ++clockCalls == 1 ? 130 : clock);
        controller.ConfigureStepApplications(Config()); Assert.Null(controller.Submit(Request(startBefore: 150), 130));
        clockCalls = 0; clock = 151; controller.Tick(130);
        var batch = controller.StepApplicationExtensions()!["stepApplications"]!;
        Assert.True(batch["authorityLost"]!.Value<bool>()); Assert.Equal(1, batch["unpublished"]!.Value<int>());
        Assert.Empty((JArray)batch["records"]!); Assert.Equal("start_deadline_expired", Assert.Single(controller.DrainReceipts()).Reason);
    }

    /// <summary>Both ordinary serializer policies preserve omission and do not expose presence bookkeeping.</summary>
    [Theory]
    [InlineData(NullValueHandling.Include)]
    [InlineData(NullValueHandling.Ignore)]
    public void OmittedExtensionsKeepLegacySerialization(NullValueHandling nulls)
    {
        var settings = JsonSettings(nulls);
        var request = JsonConvert.DeserializeObject<AgentRequest>("{}", settings)!;
        Assert.False(request.HasStepApplicationEnvelope); Assert.False(request.HasStepApplicationsAck);
        var wire = JObject.Parse(JsonConvert.SerializeObject(request, settings));
        Assert.Null(wire.Property("stepApplication")); Assert.Null(wire.Property("stepApplicationsAck"));
        Assert.Null(wire.Property("hasStepApplicationEnvelope")); Assert.Null(wire.Property("hasStepApplicationsAck"));
    }

    /// <summary>Property inclusion overrides global Ignore, and explicit-null round trips cannot silently become omission.</summary>
    [Theory]
    [InlineData("stepApplication", NullValueHandling.Include)]
    [InlineData("stepApplication", NullValueHandling.Ignore)]
    [InlineData("stepApplicationsAck", NullValueHandling.Include)]
    [InlineData("stepApplicationsAck", NullValueHandling.Ignore)]
    public void ExplicitNullExtensionKeepsPresenceAcrossRoundTrip(string field, NullValueHandling nulls)
    {
        var settings = JsonSettings(nulls);
        var request = JsonConvert.DeserializeObject<AgentRequest>("{\"" + field + "\":null}", settings)!;
        Assert.Equal(field == "stepApplication", request.HasStepApplicationEnvelope);
        Assert.Equal(field == "stepApplicationsAck", request.HasStepApplicationsAck);
        var json = JsonConvert.SerializeObject(request, settings); var wire = JObject.Parse(json);
        Assert.Equal(JTokenType.Null, wire[field]!.Type);
        var other = field == "stepApplication" ? "stepApplicationsAck" : "stepApplication";
        Assert.Null(wire.Property(other));
        var copy = JsonConvert.DeserializeObject<AgentRequest>(json, settings)! with { RequestId = "copy" };
        Assert.Equal(request.HasStepApplicationEnvelope, copy.HasStepApplicationEnvelope);
        Assert.Equal(request.HasStepApplicationsAck, copy.HasStepApplicationsAck);
    }

    /// <summary>Present object extensions still serialize without dropping or rewriting their detached content.</summary>
    [Theory]
    [InlineData("stepApplication")]
    [InlineData("stepApplicationsAck")]
    public void ObjectExtensionContentSurvivesSerialization(string field)
    {
        var settings = JsonSettings(NullValueHandling.Ignore);
        var request = JsonConvert.DeserializeObject<AgentRequest>("{\"" + field + "\":{\"version\":1}}", settings)!;
        var wire = JObject.Parse(JsonConvert.SerializeObject(request, settings));
        Assert.True(JToken.DeepEquals(JObject.Parse("{\"version\":1}"), wire[field]));
    }

    /// <summary>A null envelope is rejected by the real default-off controller before it owns an action.</summary>
    [Fact]
    public void ExplicitNullApplicationCannotBecomeLegacyAction()
    {
        var request = LegacyRequest() with { StepApplication = null };
        var controller = Controller(new FakeInput());
        Assert.Equal("step_applications_unavailable", controller.Submit(request, 130));
        Assert.Null(Active(controller)); Assert.Empty(controller.DrainReceipts());
    }

    /// <summary>The configured channel requires a real binding for both omission and explicit null.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void ConfiguredControllerRejectsMissingOrNullApplication(bool explicitNull)
    {
        var request = LegacyRequest();
        if (explicitNull) request = request with { StepApplication = null };
        var controller = Controller(new FakeInput()); controller.ConfigureStepApplications(Config());
        Assert.Equal("invalid_step_application_binding", controller.Submit(request, 130));
        Assert.Null(Active(controller)); Assert.Empty(controller.DrainReceipts());
    }

    /// <summary>The actual Submit clone preserves absent extension flags while detaching ordinary action arrays.</summary>
    [Fact]
    public void SubmittedLegacyClonePreservesOmittedExtensions()
    {
        var request = LegacyRequest(); var controller = Controller(new FakeInput());
        Assert.Null(controller.Submit(request, 130)); var copy = Assert.IsType<AgentRequest>(Active(controller));
        Assert.NotSame(request, copy); Assert.NotSame(request.Steps, copy.Steps);
        Assert.NotSame(request.Steps[0].Keys, copy.Steps[0].Keys);
        Assert.False(copy.HasStepApplicationEnvelope); Assert.False(copy.HasStepApplicationsAck);
        var wire = JObject.Parse(JsonConvert.SerializeObject(copy, JsonSettings(NullValueHandling.Include)));
        Assert.Null(wire.Property("stepApplication")); Assert.Null(wire.Property("stepApplicationsAck"));
    }

    /// <summary>Fixing omission cannot weaken ownership of an accepted object envelope or its original wire request.</summary>
    [Fact]
    public void SubmittedApplicationCloneDetachesObjectAndRawRequest()
    {
        var request = Request(keys: ["W"]); var controller = Controller(new FakeInput()); controller.ConfigureStepApplications(Config());
        Assert.Null(controller.Submit(request, 130)); var copy = Assert.IsType<AgentRequest>(Active(controller));
        Assert.NotSame(request.StepApplication, copy.StepApplication); Assert.NotSame(request.RawApplicationRequest, copy.RawApplicationRequest);
        Assert.True(copy.HasStepApplicationEnvelope); Assert.False(copy.HasStepApplicationsAck);
        request.StepApplication!["version"] = 99; request.RawApplicationRequest!["modelId"] = "changed"; request.Steps[0].Keys[0] = "LBUTTON";
        Assert.Equal(1, copy.StepApplication!["version"]!.Value<int>());
        Assert.Equal("model", (string?)copy.RawApplicationRequest!["modelId"]); Assert.Equal("W", copy.Steps[0].Keys[0]);
    }

    /// <summary>The old invalid epoch remains rejected; the fixture correction does not relax the production gate.</summary>
    [Fact]
    public void InvalidCaptureEpochStillCannotConfirmWorld()
    {
        var controller = new AgentActionController(new FakeInput(), true);
        var first = controller.RegisterFrame(new(1, 80, 1920, 1080, AgentWorldEvidence.WorldHud, 0, new AgentSourceFrame("source", 1000000900, 90, 60)));
        var second = controller.RegisterFrame(new(2, 120, 1920, 1080, AgentWorldEvidence.WorldHud, 0, new AgentSourceFrame("source", 1000001300, 130, 100)));
        Assert.False(first.Ready); Assert.False(second.Ready);
        Assert.Equal("invalid_source_timing", first.Reason); Assert.Equal("invalid_source_timing", second.Reason);
    }

    /// <summary>The real framed decoder retains null presence and selects the strict extension parser for both fields.</summary>
    [Theory]
    [InlineData("stepApplication")]
    [InlineData("stepApplicationsAck")]
    public async Task StreamReadRetainsExplicitNullExtension(string field)
    {
        var request = (await ReadRequest("{\"" + field + "\":null}"))!;
        Assert.Equal(field == "stepApplication", request.HasStepApplicationEnvelope);
        Assert.Equal(field == "stepApplicationsAck", request.HasStepApplicationsAck);
        Assert.NotNull(request.RawApplicationRequest); Assert.Equal(JTokenType.Null, request.RawApplicationRequest![field]!.Type);
    }

    /// <summary>An explicit-null extension cannot bypass strict duplicate-property rejection in the actual decoder.</summary>
    [Theory]
    [InlineData("stepApplication")]
    [InlineData("stepApplicationsAck")]
    public async Task NullExtensionStillRejectsDuplicateWireProperties(string field) =>
        await Assert.ThrowsAnyAsync<Exception>(() => ReadRequest("{\"" + field + "\":null,\"x\":1,\"x\":2}"));

    /// <summary>Use the production camel-case contract with both global null policies and no type-name handling.</summary>
    private static JsonSerializerSettings JsonSettings(NullValueHandling nulls) => new()
    {
        ContractResolver = new CamelCasePropertyNamesContractResolver(), NullValueHandling = nulls,
        MaxDepth = 16, TypeNameHandling = TypeNameHandling.None
    };

    /// <summary>Legacy request metadata shares the exact valid frame used by the application fixture.</summary>
    private static AgentRequest LegacyRequest() => new()
    {
        RequestId = "legacy", ModelId = "model", FrameId = 2, ObservedAtMs = 120,
        ExpiresAtMs = 500, Steps = [new() { DurationMs = 50, Keys = ["W"] }]
    };

    /// <summary>Inspect retained detached data only; this never ticks or dispatches the fake controller.</summary>
    private static AgentRequest? Active(AgentActionController controller) =>
        (AgentRequest?)typeof(AgentActionController).GetField("_active", BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(controller);

    /// <summary>Exercise only the existing in-memory codec; no stream lifecycle, pipe or runtime is started.</summary>
    private static async Task<AgentRequest?> ReadRequest(string json)
    {
        var bytes = Encoding.UTF8.GetBytes(json); var packet = new byte[4 + bytes.Length];
        BinaryPrimitives.WriteInt32LittleEndian(packet, bytes.Length); bytes.CopyTo(packet, 4);
        using var stream = new MemoryStream(packet); var session = new AgentStreamSession(null!);
        var read = typeof(AgentStreamSession).GetMethod("ReadAsync", BindingFlags.NonPublic | BindingFlags.Instance)!;
        return await (Task<AgentRequest?>)read.Invoke(session, [stream, CancellationToken.None])!;
    }

    /// <summary>Fixed valid configuration; no Win32 or native clock query is performed by this helper.</summary>
    private static JObject Config() => new()
    {
        ["version"] = 1, ["mode"] = AgentStepApplicationWire.Mode, ["sessionId"] = "session", ["ownerEpoch"] = "owner", ["channelId"] = "channel",
        ["backendId"] = "win32-sendinput", ["backendEpoch"] = "backend", ["buildSha256"] = new string('a', 64), ["clockKind"] = "windows_qpc",
        ["sessionOriginTicks"] = 1L, ["clockFrequency"] = 1000, ["allowedKeys"] = new JArray("W", "LBUTTON")
    };

    /// <summary>Complete empty local bookkeeping.</summary>
    private static JObject State() => new() { ["keys"] = new JArray(), ["generation"] = 0L, ["complete"] = true };

    /// <summary>Exact documented v1 transport ACK envelope.</summary>
    private static JObject Ack(long through, string terminal) => new() { ["version"] = 1, ["channelId"] = "channel", ["through"] = through, ["terminalRequestIds"] = new JArray(terminal) };

    /// <summary>Detach the exact request JSON, then add the separately hashed authority envelope.</summary>
    private static AgentRequest Request(int dx = 0, string[]? keys = null, string requestId = "request", double? startBefore = null)
    {
        var step = new JObject { ["durationMs"] = 50, ["keys"] = new JArray(keys ?? []), ["mouseDx"] = dx, ["mouseDy"] = 0 };
        var source = new JObject { ["version"] = 1, ["command"] = "action", ["sessionId"] = "session", ["ownerEpoch"] = "owner", ["goalVersion"] = 1,
            ["requestId"] = requestId, ["frameId"] = 2L, ["observedAtMs"] = 120.0, ["expiresAtMs"] = 500.0, ["modelId"] = "model", ["steps"] = new JArray(step.DeepClone()) };
        if (startBefore.HasValue) source["startBeforeMs"] = startBefore.Value;
        var raw = AgentStepApplicationWire.Freeze(source, 16384);
        var bound = new JObject { ["identity"] = new JObject { ["sessionId"] = "session", ["ownerEpoch"] = "owner", ["sourceEpoch"] = CaptureEpoch, ["modelId"] = "model",
                ["goalVersion"] = 1, ["controlEpoch"] = 1, ["policyGoalVersion"] = 1, ["readinessEpoch"] = 1, ["frameId"] = 2L },
            ["requestId"] = requestId, ["submissionSha256"] = Convert.ToHexString(SHA256.HashData(Encoding.ASCII.GetBytes(raw))).ToLowerInvariant(),
            ["model"] = new JObject { ["checkpointSha256"] = new string('b', 64), ["profile"] = "original", ["mapping"] = "native-raw-to-one-step-v1" },
            ["intervalCount"] = 1, ["stepIndex"] = 0, ["step"] = step };
        var extension = new JObject { ["version"] = 1, ["submissionJson"] = raw, ["binding"] = bound };
        var wire = (JObject)source.DeepClone(); wire["stepApplication"] = extension.DeepClone();
        return source.ToObject<AgentRequest>()! with { StepApplication = extension, RawApplicationRequest = wire };
    }

    /// <summary>Use the repository's established two-observation readiness fixture with ordinary legacy ms clocks.</summary>
    private static AgentActionController Controller(FakeInput input, Func<double>? clock = null)
    {
        var controller = new AgentActionController(input, true, clock);
        controller.RegisterFrame(new(1, 80, 1920, 1080, AgentWorldEvidence.WorldHud, 0, new AgentSourceFrame(CaptureEpoch, 1000000900, 90, 60)));
        Assert.True(controller.RegisterFrame(new(2, 120, 1920, 1080, AgentWorldEvidence.WorldHud, 0, new AgentSourceFrame(CaptureEpoch, 1000001300, 130, 100))).Ready);
        return controller;
    }

    /// <summary>Only in-memory calls; real RuntimeAgentInput instrumentation requires separate C# validation.</summary>
    private sealed class FakeInput : IAgentInput, IAgentApplicationInput
    {
        /// <summary>Installed proof and local generation; no external backend exists.</summary>
        private AgentStepApplicationEvidence? _proof;
        /// <summary>Detached tracked software state.</summary>
        private JObject _tracked = State();
        /// <summary>Optional already-known software state; it is not a physical input measurement.</summary>
        public FakeInput(params string[] initialKeys) { _tracked["keys"] = new JArray(initialKeys); }
        /// <summary>Inject a backend failure after the held-state evaluation returned.</summary>
        public bool ThrowMouse { get; init; }
        /// <inheritdoc />
        public bool IsAvailable => true;
        /// <inheritdoc />
        public string ApplicationBackendEpoch => "backend";
        /// <inheritdoc />
        public JObject ApplicationTrackedState => (JObject)_tracked.DeepClone();
        /// <inheritdoc />
        public void BeginApplication(AgentStepApplicationEvidence proof) => _proof = proof;
        /// <inheritdoc />
        public void EndApplication(bool completed, string[] desired)
        {
            _proof = null; _tracked["keys"] = new JArray(desired); _tracked["complete"] = completed;
            if (completed) _tracked["generation"] = _tracked["generation"]!.Value<long>() + 1;
        }
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) { Assert.Empty(keys); }
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) => _proof!.Call("mouseMove", null, dx, dy, () => { if (ThrowMouse) throw new InvalidOperationException("input_failure"); });
        /// <inheritdoc />
        public void ReleaseAll() { _tracked["complete"] = false; }
    }
}
