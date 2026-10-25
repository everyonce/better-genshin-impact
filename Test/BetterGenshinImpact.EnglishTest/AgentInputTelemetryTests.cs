using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Prepared inert coverage of the real call observer and controller; no runtime or InputHub is constructed.</summary>
public sealed class AgentInputTelemetryTests
{
    /// <summary>Return evidence follows the unchanged call and its bookkeeping mutation.</summary>
    [Fact]
    public void ObserverStagesBracketTheActualMutation()
    {
        var observer = new AgentInputCallObserver();
        var held = false;
        var rows = new List<(AgentInputCall Call, bool Held)>();
        observer.Sink = call => rows.Add((call, held));
        observer.Invoke("keyDown", "W", 0, 0, () => held = true);
        Assert.Equal(new[] { "started", "returned" }, rows.Select(row => row.Call.Stage));
        Assert.False(rows[0].Held);
        Assert.True(rows[1].Held);
        Assert.Equal(rows[0].Call.CallId, rows[1].Call.CallId);
        Assert.False(observer.Incomplete);
    }

    /// <summary>A diagnostic callback failure cannot prevent or repeat a successful backend call.</summary>
    [Fact]
    public void ObserverFailureDoesNotChangeInputSuccess()
    {
        var calls = 0;
        var observer = new AgentInputCallObserver { Sink = _ => throw new InvalidOperationException("observer") };
        observer.Invoke("buttonDown", "LBUTTON", 0, 0, () => calls++);
        Assert.Equal(1, calls);
        Assert.True(observer.Incomplete);
    }

    /// <summary>Even a failing diagnostic sink cannot replace the original backend exception.</summary>
    [Fact]
    public void ObserverFailureDoesNotReplaceInputFailure()
    {
        var expected = new InvalidOperationException("backend");
        var observer = new AgentInputCallObserver { Sink = _ => throw new ApplicationException("observer") };
        Assert.Same(expected, Assert.Throws<InvalidOperationException>(() =>
            observer.Invoke("mouseMove", null, 3, -2, () => throw expected)));
        Assert.True(observer.Incomplete);
        Assert.True(observer.ExecutionUncertain);
    }

    /// <summary>Aggregate cleanup returns never certify individual key releases.</summary>
    [Theory]
    [InlineData("returned_unverified")]
    [InlineData("skipped_backend_changed")]
    public void AggregateReleaseRetainsExplicitUncertainty(string stage)
    {
        var rows = new List<AgentInputCall>();
        var observer = new AgentInputCallObserver { Sink = rows.Add };
        observer.Invoke("releaseAll", null, 0, 0, () => { }, stage);
        Assert.Equal(stage, observer.ReleaseOutcome);
        Assert.True(observer.ExecutionUncertain);
        Assert.Equal(new[] { "started", stage }, rows.Select(row => row.Stage));
    }

    /// <summary>The failure stage preserves type and uncertainty while the original exception escapes.</summary>
    [Fact]
    public void FailedReleaseIsNeverReportedAsReturned()
    {
        var rows = new List<AgentInputCall>();
        var expected = new InvalidOperationException("release");
        var observer = new AgentInputCallObserver { Sink = rows.Add };
        Assert.Same(expected, Assert.Throws<InvalidOperationException>(() =>
            observer.Invoke("releaseAll", null, 0, 0, () => throw expected, "returned_unverified")));
        Assert.Equal("failed", observer.ReleaseOutcome);
        Assert.Equal("InvalidOperationException", rows[^1].Error);
        Assert.True(observer.ExecutionUncertain);
    }

    /// <summary>New call clocks supplement rather than rewrite legacy pre-call timestamps and cadence.</summary>
    [Fact]
    public void KeyAndMouseEvidencePreservesLegacyTimingAndIdentity()
    {
        var f = new Fixture();
        f.Input.AfterCall = operation => f.Now += operation == "mouseMove" ? 7 : 3;
        Assert.Null(f.Controller.Submit(Request("first", ["W"], 3, -2), 130));
        f.Controller.Tick(130);
        var snapshot = f.Controller.GetExecutionContextSnapshot();
        var rows = snapshot.Events.Where(row => row.RequestId == "first").ToArray();
        Assert.Equal(new[] { 130d, 133d, 133d, 140d }, rows.Select(row => row.AtMs!.Value));
        Assert.All(rows, row => { Assert.Equal(0, row.StepIndex); Assert.Equal("dispatch", row.Origin); });
        Assert.Equal(3, rows[2].Call.MouseDx);
        Assert.Equal(-2, rows[2].Call.MouseDy);
        Assert.Equal(180, snapshot.Active!.NextStepAtMs);
        Assert.Equal("returned", snapshot.Active.LastDispatchOutcome);
        Assert.Equal(new[] { "W" }, snapshot.TrackedState.HeldKeys);
        f.Input.AfterCall = null;
        f.Now = 180;
        f.Controller.Tick(180);
        var receipt = Assert.Single(f.Controller.DrainReceipts());
        Assert.Equal(130, Assert.Single(receipt.AppliedSteps).StartedAtMs);
        Assert.Equal(180, receipt.EndedAtMs);
        Assert.Equal("completed", receipt.Status);
        Assert.False(snapshot.PhysicalExecutionProven);
    }

    /// <summary>A partial key transition is retained even when legacy appliedSteps stays empty.</summary>
    [Fact]
    public void PartialKeyFailureKeepsAttemptAndPriorSoftwareHold()
    {
        var f = new Fixture();
        f.Input.FailKey = "D";
        Assert.Null(f.Controller.Submit(Request("partial", ["W", "D"]), 130));
        Assert.Same(f.Input.Failure, Assert.Throws<InvalidOperationException>(() => f.Controller.Tick(130)));
        var state = f.Controller.GetExecutionContextSnapshot();
        Assert.Equal("failed", state.Active!.LastDispatchOutcome);
        Assert.Equal(0, state.Active.LastAttemptedStepIndex);
        Assert.Null(state.Active.LastAppliedKeys);
        Assert.Equal(new[] { "W" }, state.TrackedState.HeldKeys);
        Assert.True(state.TrackedState.ExecutionUncertain);
        Assert.Equal(new[] { "started", "returned", "started", "failed" },
            state.Events.Where(row => row.RequestId == "partial").Select(row => row.Call.Stage));
        f.Controller.Stop(140, "test_stop");
        var receipt = Assert.Single(f.Controller.DrainReceipts());
        Assert.Empty(receipt.AppliedSteps);
        var release = f.Controller.GetExecutionContextSnapshot().LastInputEvent!;
        Assert.Equal("partial", release.RequestId);
        Assert.Equal(0, release.StepIndex);
        Assert.Equal("release:test_stop", release.Origin);
    }

    /// <summary>An early availability exception cannot be mistaken for a completed empty step.</summary>
    [Fact]
    public void DispatchFailureBeforeARecordedCallIsStillExplicit()
    {
        var f = new Fixture();
        f.Input.FailBeforeCalls = true;
        Assert.Null(f.Controller.Submit(Request("early", ["W"]), 130));
        Assert.Throws<InvalidOperationException>(() => f.Controller.Tick(130));
        var snapshot = f.Controller.GetExecutionContextSnapshot();
        Assert.Equal("failed", snapshot.Active!.LastDispatchOutcome);
        Assert.Empty(snapshot.Events.Where(row => row.RequestId == "early"));
        Assert.Null(snapshot.Active.LastAppliedKeys);
    }

    /// <summary>A mouse failure after a returned key call preserves partial software input without an applied interval.</summary>
    [Fact]
    public void MouseFailureAfterKeyDoesNotEraseTheReturnedKeyCall()
    {
        var f = new Fixture();
        f.Input.BeforeCall = operation => { if (operation == "mouseMove") throw f.Input.Failure; };
        Assert.Null(f.Controller.Submit(Request("mouse_partial", ["W"], 3, -2), 130));
        Assert.Same(f.Input.Failure, Assert.Throws<InvalidOperationException>(() => f.Controller.Tick(130)));
        var snapshot = f.Controller.GetExecutionContextSnapshot();
        Assert.Equal(new[] { "W" }, snapshot.TrackedState.HeldKeys);
        Assert.True(snapshot.TrackedState.ExecutionUncertain);
        Assert.Equal("failed", snapshot.Active!.LastDispatchOutcome);
        Assert.Null(snapshot.Active.LastAppliedKeys);
        Assert.Equal("keyDown", snapshot.Events[^3].Call.Operation);
        Assert.Equal("returned", snapshot.Events[^3].Call.Stage);
        Assert.Equal("mouseMove", snapshot.Events[^1].Call.Operation);
        Assert.Equal("failed", snapshot.Events[^1].Call.Stage);
    }

    /// <summary>A throwing release preserves existing terminal-receipt behavior and the failed call origin.</summary>
    [Fact]
    public void ThrowingCleanupKeepsReceiptAndUnknownRelease()
    {
        var f = new Fixture();
        Assert.Null(f.Controller.Submit(Request("cleanup", ["W"]), 130));
        f.Controller.Tick(130);
        f.Input.FailRelease = true;
        Assert.Same(f.Input.Failure, Assert.Throws<InvalidOperationException>(() => f.Controller.Stop(140, "test_stop")));
        Assert.Equal("cancelled", Assert.Single(f.Controller.DrainReceipts()).Status);
        var snapshot = f.Controller.GetExecutionContextSnapshot();
        Assert.Null(snapshot.Active);
        Assert.Equal("failed", snapshot.TrackedState.ReleaseOutcome);
        Assert.Equal(new[] { "W" }, snapshot.TrackedState.HeldKeys);
        Assert.Equal("cleanup", snapshot.LastInputEvent!.RequestId);
        Assert.Equal("failed", snapshot.LastInputEvent.Call.Stage);
    }

    /// <summary>Replacing a proposal changes intention without manufacturing an intervening release.</summary>
    [Fact]
    public void ReplacementSeparatesNewIntentionFromOldHeldState()
    {
        var f = new Fixture();
        Assert.Null(f.Controller.Submit(Request("old", ["W"]), 130));
        f.Controller.Tick(130);
        f.Now = 140;
        f.Controller.RegisterFrame(new(3, 140, 1920, 1080, AgentWorldEvidence.WorldHud));
        var previous = f.Controller.GetExecutionContextSnapshot();
        Assert.Null(f.Controller.Submit(Request("new", ["S"]) with { FrameId = 3, ObservedAtMs = 140 }, 140));
        var current = f.Controller.GetExecutionContextSnapshot();
        Assert.Equal(previous.LastSequence, current.LastSequence);
        Assert.Equal("new", current.Active!.RequestId);
        Assert.Equal(new[] { "S" }, current.Active.NextIntendedKeys);
        Assert.Equal(new[] { "W" }, current.TrackedState.HeldKeys);
        Assert.Equal("old", current.LastInputEvent!.RequestId);
        Assert.Equal("replaced", Assert.Single(f.Controller.DrainReceipts()).Status);
    }

    /// <summary>Repeated held intervals do not add a new backend down; intentions still advance.</summary>
    [Fact]
    public void UnchangedHoldDoesNotManufactureInputEvents()
    {
        var f = new Fixture();
        var request = Request("held", ["W"]);
        request = request with { Steps = [request.Steps[0], request.Steps[0]] };
        Assert.Null(f.Controller.Submit(request, 130));
        f.Controller.Tick(130);
        var first = f.Controller.GetExecutionContextSnapshot();
        f.Now = 180;
        f.Controller.Tick(180);
        var second = f.Controller.GetExecutionContextSnapshot();
        Assert.Equal(first.LastSequence, second.LastSequence);
        Assert.Equal(2, second.Active!.NextStepIndex);
        Assert.Equal("returned", second.Active.LastDispatchOutcome);
        Assert.Null(second.Active.NextIntendedKeys);
    }

    /// <summary>Readiness-triggered release finishes before publication context is sampled.</summary>
    [Fact]
    public void ReadinessSnapshotIncludesItsOwnReleaseButKeepsOldClockMeaning()
    {
        var f = new Fixture();
        Assert.Null(f.Controller.Submit(Request("stale", ["W"]), 130));
        f.Controller.Tick(130);
        f.Now = 300;
        f.Input.AfterCall = _ => f.Now += 5;
        var readiness = f.Controller.GetWorldReadinessAndExecutionSnapshot(out var oldSample, out var context);
        Assert.False(readiness.Ready);
        Assert.Equal(300, oldSample);
        Assert.Equal(305, context.SampledAtMs);
        Assert.Null(context.Active);
        Assert.Equal("returned_unverified", context.TrackedState.ReleaseOutcome);
        Assert.Equal(305, context.LastInputEvent!.AtMs);
        Assert.Equal(300, Assert.Single(f.Controller.DrainReceipts()).EndedAtMs);
    }

    /// <summary>Client-side mutation of detached arrays cannot change later context or active scheduling.</summary>
    [Fact]
    public void ReturnedArraysAreDetached()
    {
        var f = new Fixture();
        var request = Request("copy", ["W"]);
        request = request with { Steps = [request.Steps[0], new() { DurationMs = 50, Keys = ["D"] }] };
        Assert.Null(f.Controller.Submit(request, 130));
        f.Controller.Tick(130);
        var one = f.Controller.GetExecutionContextSnapshot();
        one.TrackedState.HeldKeys[0] = "S";
        one.Active!.LastAppliedKeys![0] = "D";
        one.Active.NextIntendedKeys![0] = "S";
        one.Events[0] = one.Events[0] with { Origin = "changed" };
        var two = f.Controller.GetExecutionContextSnapshot();
        Assert.Equal(new[] { "W" }, two.TrackedState.HeldKeys);
        Assert.Equal(new[] { "W" }, two.Active!.LastAppliedKeys);
        Assert.Equal(new[] { "D" }, two.Active.NextIntendedKeys);
        Assert.DoesNotContain(two.Events, row => row.Origin == "changed");
    }

    /// <summary>Retained ledgers remain bounded and expose exact eviction watermarks without draining.</summary>
    [Fact]
    public void RingEvictionAndRepeatedSnapshotsAreExplicit()
    {
        var input = new FakeInput();
        var now = 0d;
        var controller = new AgentActionController(input, false, () => now, null, input.State);
        input.Telemetry.Sink = controller.RecordInputCall;
        for (var index = 0; index < 140; index++)
        {
            now++;
            input.Telemetry.Invoke("mouseMove", null, 1, 0, () => { });
        }
        var first = controller.GetExecutionContextSnapshot();
        var second = controller.GetExecutionContextSnapshot();
        Assert.Equal(256, first.Events.Length);
        Assert.Equal(24, first.EvictedEvents);
        Assert.Equal(25, first.FirstSequence);
        Assert.Equal(280, first.LastSequence);
        Assert.Equal(first.Events, second.Events);
        Assert.All(first.Events, row => Assert.Null(row.RequestId));
    }

    /// <summary>Clock exceptions cannot escape the diagnostic callback or suppress a backend call.</summary>
    [Fact]
    public void ClockFailureOnlyInvalidatesTelemetry()
    {
        var input = new FakeInput();
        var controller = new AgentActionController(input, true, () => throw new InvalidOperationException("clock"), null, input.State);
        input.Telemetry.Sink = controller.RecordInputCall;
        input.SetHeldKeys(["W"]);
        var snapshot = controller.GetExecutionContextSnapshot();
        Assert.Equal(new[] { "W" }, snapshot.TrackedState.HeldKeys);
        Assert.False(snapshot.TelemetryComplete);
        Assert.Null(snapshot.SampledAtMs);
        Assert.All(snapshot.Events, row => Assert.Null(row.AtMs));
    }

    /// <summary>Nonfinite, negative, or regressed telemetry clocks never create apparently valid timestamps.</summary>
    [Theory]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    [InlineData(-1d)]
    [InlineData(9d)]
    public void InvalidTelemetryClockIsRejected(double invalid)
    {
        var input = new FakeInput();
        var now = 10d;
        var controller = new AgentActionController(input, true, () => now, null, input.State);
        Assert.Equal(10, controller.GetExecutionContextSnapshot().SampledAtMs);
        now = invalid;
        Assert.Null(controller.GetExecutionContextSnapshot().SampledAtMs);
        Assert.False(controller.GetExecutionContextSnapshot().TelemetryComplete);
    }

    /// <summary>A bookkeeping observer fault returns unknown evidence instead of changing session control flow.</summary>
    [Fact]
    public void StateObserverFailureIsExplicit()
    {
        var controller = new AgentActionController(new FakeInput(), true, () => 1, null,
            () => throw new InvalidOperationException("state"));
        var snapshot = controller.GetExecutionContextSnapshot();
        Assert.False(snapshot.TelemetryComplete);
        Assert.True(snapshot.TrackedState.ExecutionUncertain);
        Assert.Equal("unavailable", snapshot.TrackedState.ReleaseOutcome);
    }

    /// <summary>A transient bookkeeping observation failure remains visible after the provider recovers.</summary>
    [Fact]
    public void StateObserverFailureLatchesAcrossLaterSuccessfulSnapshots()
    {
        var failed = false;
        var controller = new AgentActionController(new FakeInput(), true, () => 1, null, () =>
        {
            if (!failed) { failed = true; throw new InvalidOperationException("once"); }
            return new AgentTrackedInputState(["W"], false, "not_requested", false);
        });
        Assert.False(controller.GetExecutionContextSnapshot().TelemetryComplete);
        var recovered = controller.GetExecutionContextSnapshot();
        Assert.Equal(new[] { "W" }, recovered.TrackedState.HeldKeys);
        Assert.False(recovered.TrackedState.TelemetryIncomplete);
        Assert.False(recovered.TelemetryComplete);
    }

    /// <summary>The existing lock blocks concurrent snapshots during a backend call; the timestamp is sampled afterward.</summary>
    [Fact]
    public async Task ConcurrentSnapshotWaitsForBackendReturn()
    {
        var f = new Fixture();
        using var entered = new ManualResetEventSlim();
        using var proceed = new ManualResetEventSlim();
        using var requested = new ManualResetEventSlim();
        f.Input.BeforeCall = _ => { entered.Set(); Assert.True(proceed.Wait(TimeSpan.FromSeconds(3))); };
        Assert.Null(f.Controller.Submit(Request("blocked", ["W"]), 130));
        var tick = Task.Run(() => f.Controller.Tick(130));
        Task<AgentExecutionContext>? read = null;
        try
        {
            Assert.True(entered.Wait(TimeSpan.FromSeconds(3)));
            read = Task.Run(() => { requested.Set(); return f.Controller.GetExecutionContextSnapshot(); });
            Assert.True(requested.Wait(TimeSpan.FromSeconds(3)));
            Assert.False(read.IsCompleted);
            f.Now = 150;
        }
        finally
        {
            proceed.Set();
            await tick.WaitAsync(TimeSpan.FromSeconds(3));
        }
        var snapshot = await read!.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.Equal(150, snapshot.SampledAtMs);
        Assert.Equal("returned", snapshot.LastInputEvent!.Call.Stage);
        Assert.False(snapshot.ObservesBlockedCallConcurrently);
    }

    /// <summary>Instrumentation does not alter the existing scheduler's returned receipt or backend call order.</summary>
    [Fact]
    public void LegacyReceiptAndInputOrderRemainEqual()
    {
        var observed = new Fixture();
        var legacy = new Fixture(observe: false);
        foreach (var f in new[] { observed, legacy })
        {
            Assert.Null(f.Controller.Submit(Request("same", ["W"], 2, 1), 130));
            f.Controller.Tick(130);
            f.Now = 180;
            f.Controller.Tick(180);
        }
        Assert.Equal(JsonConvert.SerializeObject(legacy.Controller.DrainReceipts()),
            JsonConvert.SerializeObject(observed.Controller.DrainReceipts()));
        Assert.Equal(legacy.Input.Calls, observed.Input.Calls);
    }

    /// <summary>Wire properties explicitly preserve uncertainty and the independent publication clock.</summary>
    [Fact]
    public void SerializedContextKeepsTheAuthorityLimits()
    {
        var snapshot = new Fixture().Controller.GetExecutionContextSnapshot();
        var json = JsonConvert.SerializeObject(snapshot, new JsonSerializerSettings
        {
            ContractResolver = new CamelCasePropertyNamesContractResolver()
        });
        Assert.Contains("\"version\":1", json);
        Assert.Contains("\"physicalExecutionProven\":false", json);
        Assert.Contains("\"observesBlockedCallConcurrently\":false", json);
        Assert.Contains("\"sampledAtMs\":", json);
        Assert.DoesNotContain("gameAccepted", json);
    }

    /// <summary>Build a valid bounded proposal with an exact observed frame identity.</summary>
    private static AgentRequest Request(string id, string[] keys, int dx = 0, int dy = 0) => new()
    {
        RequestId = id, ModelId = "fake", FrameId = 2, ObservedAtMs = 120, ExpiresAtMs = 350,
        Steps = [new() { DurationMs = 50, Keys = keys, MouseDx = dx, MouseDy = dy }]
    };

    /// <summary>Own a deterministic clock and actual controller, with no application/runtime objects.</summary>
    private sealed class Fixture
    {
        /// <summary>Session time used by all telemetry callbacks.</summary>
        internal double Now = 130;
        /// <summary>Inert backend with the real observer.</summary>
        internal FakeInput Input { get; } = new();
        /// <summary>Actual production scheduler under test.</summary>
        internal AgentActionController Controller { get; }
        /// <summary>Acquire ordinary two-frame readiness before each case.</summary>
        internal Fixture(bool observe = true)
        {
            Controller = new(Input, true, () => Now, null, observe ? Input.State : null);
            if (observe) Input.Telemetry.Sink = Controller.RecordInputCall;
            Controller.RegisterFrame(new(1, 80, 1920, 1080, AgentWorldEvidence.WorldHud));
            Assert.True(Controller.RegisterFrame(new(2, 120, 1920, 1080, AgentWorldEvidence.WorldHud)).Ready);
        }
    }

    /// <summary>Explicit effects and partial failures; shares the real observer without touching InputHub.</summary>
    private sealed class FakeInput : IAgentInput
    {
        /// <summary>Real nonthrowing call observation helper.</summary>
        internal AgentInputCallObserver Telemetry { get; } = new();
        /// <summary>Software-held set, never an OS query.</summary>
        internal HashSet<string> Held { get; } = [];
        /// <summary>Backend invocations used for exact legacy ordering comparisons.</summary>
        internal List<string> Calls { get; } = [];
        /// <summary>Stable backend exception object for identity assertions.</summary>
        internal InvalidOperationException Failure { get; } = new("inert backend failure");
        /// <summary>Optional failed down after earlier successful keys.</summary>
        internal string? FailKey;
        /// <summary>Simulate the hard availability guard before any low-level call.</summary>
        internal bool FailBeforeCalls;
        /// <summary>Simulate the unchanged throwing aggregate boundary.</summary>
        internal bool FailRelease;
        /// <summary>Optional synchronization inside the actual observed operation.</summary>
        internal Action<string>? BeforeCall;
        /// <summary>Optional elapsed time after the operation and bookkeeping complete.</summary>
        internal Action<string>? AfterCall;
        /// <inheritdoc />
        public bool IsAvailable => true;
        /// <summary>Detach the software state with the helper's explicit uncertainty.</summary>
        internal AgentTrackedInputState State() => new(Held.Order().ToArray(), Telemetry.ExecutionUncertain || Telemetry.Incomplete,
            Telemetry.ReleaseOutcome, Telemetry.Incomplete);
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys)
        {
            if (FailBeforeCalls) throw Failure;
            foreach (var key in Held.Except(keys).ToArray())
                Call("keyUp", key, () => Held.Remove(key));
            foreach (var key in keys.Where(key => !Held.Contains(key)))
                Call(key.EndsWith("BUTTON", StringComparison.Ordinal) ? "buttonDown" : "keyDown", key, () =>
                {
                    if (key == FailKey) throw Failure;
                    Held.Add(key);
                });
        }
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) => Call("mouseMove", null, () => { }, dx, dy);
        /// <inheritdoc />
        public void ReleaseAll() => Call("releaseAll", null, () =>
        {
            if (FailRelease) throw Failure;
            Held.Clear();
        }, returned: "returned_unverified");
        /// <summary>Run a single fake backend effect between actual observer stages.</summary>
        private void Call(string operation, string? key, Action effect, int dx = 0, int dy = 0, string returned = "returned")
        {
            Telemetry.Invoke(operation, key, dx, dy, () =>
            {
                Calls.Add(operation + ":" + key);
                BeforeCall?.Invoke(operation);
                effect();
                AfterCall?.Invoke(operation);
            }, returned);
        }
    }
}
