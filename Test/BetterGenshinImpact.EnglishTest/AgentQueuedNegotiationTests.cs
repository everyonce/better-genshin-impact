using System.Buffers.Binary;
using System.IO;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.SoloTask.Execution;
using BetterGenshinImpact.Service.ExternalControl;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Newtonsoft.Json.Serialization;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Prepared CPU-only negotiation checks; no GameRuntime, pipe, OS input or native clock is constructed.</summary>
public sealed class AgentQueuedNegotiationTests
{
    /// <summary>Omission retains the original external wire shape and global availability remains false.</summary>
    [Fact]
    public void NormalSessionHasNoCapabilityOrStartField()
    {
        Assert.False(AgentStepApplicationWire.Available);
        var request = Start();
        Assert.False(request.HasExperimentalQueuedStepApplications);
        Assert.DoesNotContain("experimentalQueuedStepApplications", System.Text.Json.JsonSerializer.Serialize(request, ExternalControlProtocol.JsonOptions));
        var header = new { type = "hello", version = 1 };
        Assert.Same(header, Session(false).WithQueuedCapability(header, true));
    }

    /// <summary>The new option is an exact boolean and may never authorize input by itself.</summary>
    [Theory]
    [InlineData(false, false, null)]
    [InlineData(false, true, null)]
    [InlineData(true, true, null)]
    [InlineData(true, false, "invalid_command_parameters")]
    public void StartOptionRequiresSeparateInputOptIn(bool experimental, bool input, string? error)
    {
        var request = Start() with { ExperimentalQueuedStepApplications = experimental, EnableInput = input };
        Assert.Equal(error, ExternalControlProtocol.ValidateRequest(request, DateTimeOffset.UtcNow));
    }

    /// <summary>Null, coerced and cross-command options fail before any task is scheduled.</summary>
    [Fact]
    public void InvalidStartOptionCannotBecomeDefaultOff()
    {
        Assert.False(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes("{\"experimentalQueuedStepApplications\":\"true\"}"), out _));
        Assert.False(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes("{\"experimentalQueuedStepApplications\":1}"), out _));
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes("{\"experimentalQueuedStepApplications\":null}"), out var suppliedNull));
        Assert.True(suppliedNull!.HasExperimentalQueuedStepApplications);
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(Start() with { ExperimentalQueuedStepApplications = null }, DateTimeOffset.UtcNow));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(Start() with { Command = "stopAgentStream", ExperimentalQueuedStepApplications = false }, DateTimeOffset.UtcNow));
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(Start()), ExternalControlProtocol.Fingerprint(Start() with { ExperimentalQueuedStepApplications = true, EnableInput = true }));
    }

    /// <summary>A live lease cannot silently upgrade or downgrade its immutable experimental permission.</summary>
    [Fact]
    public async Task OwnerRetainsOptionThroughCancellationCleanup()
    {
        var owner = new AgentStreamTaskOwner();
        var finish = new TaskCompletionSource<SoloTaskRunResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        Assert.Throws<InvalidOperationException>(() => owner.TryStart(false, (_, _) => finish.Task, experimentalQueuedStepApplications: true));
        Assert.False(owner.Snapshot().Running);
        Assert.True(owner.TryStart(true, (_, _) => finish.Task, experimentalQueuedStepApplications: true));
        Assert.True(owner.Snapshot().ExperimentalQueuedStepApplications);
        Assert.True(owner.Snapshot().CanReuse(true, AgentObservationProfile.Legacy, true));
        Assert.False(owner.Snapshot().CanReuse(true, AgentObservationProfile.Legacy));
        var stop = owner.StopAsync(CancellationToken.None);
        Assert.False(stop.IsCompleted);
        Assert.False(owner.Snapshot().CanReuse(true, AgentObservationProfile.Legacy, true));
        Assert.False(owner.TryStart(true, (_, _) => throw new InvalidOperationException("must not run")));
        finish.SetResult(new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Cancelled });
        await stop.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.False(owner.Snapshot().Running);
    }

    /// <summary>The hello extension advertises only v2 and the exact fixed mode, never a configured channel.</summary>
    [Fact]
    public void CapabilityIsExplicitQueuedOnlyAndDetached()
    {
        var session = Session(true);
        var source = new JObject { ["type"] = "hello", ["version"] = 1 };
        var hello = Assert.IsType<JObject>(session.WithQueuedCapability(source, true));
        var capability = Assert.IsType<JObject>(hello["stepApplicationsAvailable"]);
        AgentStepApplicationWire.Fields(capability, "version", "mode");
        Assert.Equal(2, (int)capability["version"]!);
        Assert.Equal(AgentStepApplicationWire.QueuedMode, (string?)capability["mode"]);
        Assert.Null(source["stepApplicationsAvailable"]);
        Assert.Throws<InvalidOperationException>(() => session.WithQueuedCapability(source, false));
    }

    /// <summary>Each supplied identity must be exact before the one-shot negotiation latch can be consumed.</summary>
    [Theory]
    [InlineData("version")]
    [InlineData("command")]
    [InlineData("sessionId")]
    [InlineData("ownerEpoch")]
    [InlineData("goalVersion")]
    public void ForeignIdentityDoesNotConsumeTheNegotiation(string field)
    {
        var session = Session(true);
        var bad = EnableRaw();
        bad[field] = field is "version" or "goalVersion" ? new JValue(2) : new JValue("foreign");
        Assert.Throws<InvalidOperationException>(() => session.ClaimQueuedEnable(Enable(bad), true));
        session.ClaimQueuedEnable(Enable(), true);
        Assert.Throws<InvalidOperationException>(() => session.ClaimQueuedEnable(Enable(), true));
    }

    /// <summary>Request mode/hash/configuration/ACK fields cannot choose or mutate server authority.</summary>
    [Theory]
    [InlineData("mode")]
    [InlineData("configuration")]
    [InlineData("buildSha256")]
    [InlineData("stepApplicationsAck")]
    [InlineData("queueAfter")]
    public void ClosedEnableShapeRejectsExtraFields(string field)
    {
        var session = Session(true); var raw = EnableRaw(); raw[field] = null;
        Assert.Throws<InvalidOperationException>(() => session.ClaimQueuedEnable(Enable(raw), true));
        session.ClaimQueuedEnable(Enable(), true);
    }

    /// <summary>Duplicate/coerced fields are rejected by the same strict parser used before enable dispatch.</summary>
    [Fact]
    public void EnableIdentityRetainsExactJsonTypes()
    {
        var raw = EnableRaw(); raw["version"] = "1";
        Assert.Throws<InvalidOperationException>(() => Session(true).ClaimQueuedEnable(Enable(raw), true));
        raw = EnableRaw(); raw["goalVersion"] = true;
        Assert.Throws<InvalidOperationException>(() => Session(true).ClaimQueuedEnable(Enable(raw), true));
        Assert.ThrowsAny<Exception>(() => AgentStepApplicationWire.Parse("{\"version\":1,\"version\":1}", 65536));
        Assert.Throws<InvalidOperationException>(() => Session(false).ClaimQueuedEnable(Enable(), true));
        Assert.Throws<InvalidOperationException>(() => Session(true).ClaimQueuedEnable(Enable(), false));
    }

    /// <summary>Readiness failure after a valid enable consumes the single attempt; later readiness cannot rearm it.</summary>
    [Fact]
    public void FailedFirstEnableCannotRetryAfterReadinessChanges()
    {
        var session = Session(true); var f = new Fixture(ready: false);
        session.ClaimQueuedEnable(Enable(), true);
        Assert.Throws<InvalidOperationException>(() => f.Controller.ConfigureQueuedStepApplications(Config(), f.Input));
        Assert.Null(f.Controller.StepApplicationExtensions());
        f.Ready();
        Assert.Throws<InvalidOperationException>(() => session.ClaimQueuedEnable(Enable(), true));
        Assert.Equal(0, f.Input.Calls);
    }

    /// <summary>Successful enable returns the actual detached controller confirmation and immutable reviewed limits.</summary>
    [Fact]
    public void KnownEmptyOriginalOwnerReceivesExactConfirmation()
    {
        var f = new Fixture(); var config = Config();
        var confirmation = f.Controller.ConfigureQueuedStepApplications(config, f.Input);
        Assert.True(AgentStepApplicationWire.Same(config, confirmation["configuration"]));
        Assert.True(AgentStepApplicationWire.Same(f.Input.ApplicationTrackedState, confirmation["initialTracked"]));
        Assert.Equal(8192, (int)confirmation["limits"]!["recordBytes"]!);
        Assert.Equal(32, (int)confirmation["limits"]!["channelAttempts"]!);
        Assert.Equal(4, (int)confirmation["limits"]!["batchRecords"]!);
        config["channelId"] = "mutated";
        Assert.Equal("channel", (string?)confirmation["configuration"]!["channelId"]);
        Assert.Throws<InvalidOperationException>(() => f.Controller.ConfigureQueuedStepApplications(Config(), f.Input));
        Assert.Equal(0, f.Input.Calls);
    }

    /// <summary>The controller cannot use a fresh substitute wrapper, used generation, held state or unknown bookkeeping.</summary>
    [Theory]
    [InlineData("foreign")]
    [InlineData("generation")]
    [InlineData("held")]
    [InlineData("unknown")]
    [InlineData("backend")]
    public void OriginalFreshOwnerIsMandatory(string fault)
    {
        var f = new Fixture(); IAgentApplicationInput argument = f.Input;
        if (fault == "foreign") argument = new FakeInput();
        if (fault == "generation") f.Input.Generation = 1;
        if (fault == "held") f.Input.Keys = ["W"];
        if (fault == "unknown") f.Input.Known = false;
        if (fault == "backend") f.Input.Backend = "changed";
        Assert.Throws<InvalidOperationException>(() => f.Controller.ConfigureQueuedStepApplications(Config(), argument));
        Assert.Null(f.Controller.StepApplicationExtensions());
        Assert.Equal(0, f.Input.Calls);
    }

    /// <summary>A legacy proposal retained before configuration cannot be converted into a queued channel.</summary>
    [Fact]
    public void ActiveLegacyProposalPreventsConfiguration()
    {
        var f = new Fixture();
        Assert.Null(f.Controller.Submit(new AgentRequest { RequestId = "legacy", ModelId = "fixture", FrameId = 2,
            ObservedAtMs = 120, ExpiresAtMs = 200, Steps = [new() { DurationMs = 50, Keys = ["W"] }] }, f.Now));
        Assert.Throws<InvalidOperationException>(() => f.Controller.ConfigureQueuedStepApplications(Config(), f.Input));
        Assert.Null(f.Controller.StepApplicationExtensions());
        Assert.Equal(0, f.Input.Calls);
    }

    /// <summary>Existing release and viewport cleanup are preserved and cannot be repaired by enable.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void ReleaseAndViewportChangePreserveUnknownState(bool viewport)
    {
        var f = new Fixture();
        if (viewport) f.Controller.RegisterFrame(new(3, 130, 1280, 720, AgentWorldEvidence.WorldHud));
        else f.Controller.Release(130);
        Assert.Equal(1, f.Input.Releases); Assert.False(f.Input.Known);
        f.Ready(viewport ? 1280 : 1920, viewport ? 720 : 1080, 160, 200, 4);
        Assert.True(f.Controller.GetWorldReadiness(f.Now).Ready);
        Assert.Throws<InvalidOperationException>(() => f.Controller.ConfigureQueuedStepApplications(Config(), f.Input));
        Assert.Equal(1, f.Input.Releases);
    }

    /// <summary>Input permission, observe-only policy, live readiness and exact v2 remain independent preconditions.</summary>
    [Theory]
    [InlineData("input")]
    [InlineData("policy")]
    [InlineData("availability")]
    [InlineData("stopped")]
    [InlineData("version")]
    public void ExistingGatesAreNotBypassed(string fault)
    {
        var f = new Fixture(input: fault != "input", policy: fault == "policy" ? DesktopCapturePolicy.ObserveOnly : null);
        var config = Config();
        if (fault == "availability") f.Input.Available = false;
        if (fault == "stopped") f.Controller.Stop(130, "test_stop");
        if (fault == "version") { config["version"] = 1; config["mode"] = AgentStepApplicationWire.Mode; }
        Assert.Throws<InvalidOperationException>(() => f.Controller.ConfigureQueuedStepApplications(config, f.Input));
        Assert.Null(f.Controller.StepApplicationExtensions());
    }

    /// <summary>Repeated idle ticks before first readiness never manufacture a release or consume the fresh input owner.</summary>
    [Fact]
    public void WaitingForFirstReadinessDoesNotResetOrRelease()
    {
        var f = new Fixture(ready: false);
        f.Controller.Tick(100); f.Controller.Tick(120);
        Assert.True(f.Input.Known); Assert.Equal(0, f.Input.Releases);
        f.Ready();
        Assert.NotNull(f.Controller.ConfigureQueuedStepApplications(Config(), f.Input));
        Assert.Equal(0, f.Input.Calls);
    }

    /// <summary>The real framed writer merges the actual confirmation with batch/terminal extensions without collision.</summary>
    [Fact]
    public async Task RealWriterKeepsConfirmationAndOrdinaryExtensionsDistinct()
    {
        var f = new Fixture(); var confirmation = f.Controller.ConfigureQueuedStepApplications(Config(), f.Input);
        var session = Session(true); Set(session, "_applicationController", f.Controller);
        var reply = AgentStreamSession.QueuedEnableReply(confirmation, 130);
        using var memory = new MemoryStream();
        var writer = typeof(AgentStreamSession).GetMethod("WriteAsync", BindingFlags.Instance | BindingFlags.NonPublic)!;
        await ((Task)writer.Invoke(session, [memory, reply, null, CancellationToken.None])!).WaitAsync(TimeSpan.FromSeconds(3));
        var bytes = memory.ToArray(); var count = BinaryPrimitives.ReadInt32LittleEndian(bytes);
        Assert.Equal(count + 4, bytes.Length); Assert.True(count <= AgentStepApplicationWire.HeaderBytes);
        var actual = AgentStepApplicationWire.Parse(Encoding.ASCII.GetString(bytes, 4, count), AgentStepApplicationWire.HeaderBytes);
        Assert.Equal("stepApplicationsEnabled", (string?)actual["type"]);
        Assert.True(AgentStepApplicationWire.Same(confirmation, actual["stepApplicationConfirmation"]));
        Assert.NotNull(actual["stepApplications"]); Assert.NotNull(actual["stepApplicationTerminals"]);
        Assert.Empty((JArray)actual["stepApplications"]!["records"]!);
        Assert.Empty((JArray)actual["stepApplicationTerminals"]!);
        Assert.Equal(0, f.Input.Calls);
    }

    /// <summary>Construct only ordinary immutable request data, with no service or pipe.</summary>
    private static ExternalControlRequest Start() => new() { Version = 1, RequestId = Guid.NewGuid(), CreatedAtUnixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), Command = "startAgentStream", TargetProcessId = 123, TargetWindowsSessionId = 3, TargetNonce = "child" };
    /// <summary>Fixed authenticated enable grammar; server configuration is deliberately absent.</summary>
    private static JObject EnableRaw() => new() { ["version"] = 1, ["command"] = "enableStepApplications", ["sessionId"] = "session", ["ownerEpoch"] = "owner", ["goalVersion"] = 1 };
    /// <summary>Pass through the production strict parser used by the real stream reader.</summary>
    private static AgentRequest Enable(JObject? raw = null) => new() { RawApplicationRequest = AgentStepApplicationWire.Parse((raw ?? EnableRaw()).ToString(Formatting.None), 65536) };
    /// <summary>Use the existing exact fixture configuration, without platform clock queries or configuration duplication.</summary>
    private static JObject Config() => AgentStepApplicationQueuedTests.Config();
    /// <summary>Allocate only managed fields needed by pure session methods; the GameRuntime constructor never runs.</summary>
    private static AgentStreamSession Session(bool enabled)
    {
        var session = (AgentStreamSession)RuntimeHelpers.GetUninitializedObject(typeof(AgentStreamSession));
        Set(session, "_experimentalQueuedStepApplications", enabled); Set(session, "_sessionId", "session"); Set(session, "_ownerEpoch", "owner");
        Set(session, "_json", new JsonSerializerSettings { ContractResolver = new CamelCasePropertyNamesContractResolver(), MaxDepth = 16, TypeNameHandling = TypeNameHandling.None });
        return session;
    }
    /// <summary>Assign only named managed fixture fields; never invoke a runtime lifecycle method.</summary>
    private static void Set(object target, string field, object value) => target.GetType().GetField(field, BindingFlags.NonPublic | BindingFlags.Instance)!.SetValue(target, value);

    /// <summary>Original controller with a deterministic fake clock and source observations.</summary>
    private sealed class Fixture
    {
        /// <summary>Exact fake input owner retained for all configuration attempts.</summary>
        internal readonly FakeInput Input = new();
        /// <summary>Production controller; it performs no native input through this sink.</summary>
        internal readonly AgentActionController Controller;
        /// <summary>Finite managed clock advances only with the supplied fake source series.</summary>
        internal double Now = 130;
        /// <summary>Construct one local controller, optionally before any readiness observation.</summary>
        internal Fixture(bool ready = true, bool input = true, string? policy = null)
        {
            Controller = new AgentActionController(Input, input, () => Now, policy);
            if (ready) Ready();
        }
        /// <summary>Register two exact fake sources; no source clock is renewed in place.</summary>
        internal void Ready(int width = 1920, int height = 1080, double first = 80, double second = 120, long firstFrame = 1)
        {
            const string epoch = "11111111111111111111111111111111";
            Now = second + 10;
            Controller.RegisterFrame(new(firstFrame, first, width, height, AgentWorldEvidence.WorldHud, 0, new AgentSourceFrame(epoch, (long)(1000000100 + first * 10), first + 10, first - 20)));
            Controller.RegisterFrame(new(firstFrame + 1, second, width, height, AgentWorldEvidence.WorldHud, 0, new AgentSourceFrame(epoch, (long)(1000000100 + second * 10), second + 10, second - 20)));
        }
    }

    /// <summary>In-memory state only; any attempted application fails the fixture immediately.</summary>
    private sealed class FakeInput : IAgentInput, IAgentApplicationInput
    {
        /// <summary>Controlled current availability, initial certainty and generation.</summary>
        internal bool Available = true, Known = true;
        /// <summary>Observed software generation, never a physical key-state claim.</summary>
        internal long Generation;
        /// <summary>Held bookkeeping and exact backend identity.</summary>
        internal string[] Keys = [];
        /// <summary>Changed identity must reject the original configuration.</summary>
        internal string Backend = "backend";
        /// <summary>Count all forbidden application entries and normal aggregate cleanup calls.</summary>
        internal int Calls, Releases;
        /// <inheritdoc />
        public bool IsAvailable => Available;
        /// <inheritdoc />
        public string ApplicationBackendEpoch => Backend;
        /// <inheritdoc />
        public JObject ApplicationTrackedState => new() { ["keys"] = new JArray(Keys), ["generation"] = Generation, ["complete"] = Known };
        /// <inheritdoc />
        public void BeginApplication(AgentStepApplicationEvidence proof) { Calls++; throw new InvalidOperationException("unexpected_application"); }
        /// <inheritdoc />
        public void EndApplication(bool completed, string[] desired) { Calls++; throw new InvalidOperationException("unexpected_application"); }
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) { Calls++; Known = false; throw new InvalidOperationException("unexpected_input"); }
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) { Calls++; throw new InvalidOperationException("unexpected_input"); }
        /// <inheritdoc />
        public void ReleaseAll() { Releases++; Known = false; Keys = []; }
    }
}
