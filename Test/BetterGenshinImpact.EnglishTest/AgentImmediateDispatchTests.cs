using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Agent;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>In-memory first-step dispatch and competing-tick failures; no stream, window or native input is constructed.</summary>
public sealed class AgentImmediateDispatchTests
{
    /// <summary>Only this immutable fake capture lifetime can supply the source clock.</summary>
    private const string CaptureEpoch = "33333333333333333333333333333333";

    /// <summary>Immediate dispatch uses the real final clock and retains the original acceptance and hold schedule.</summary>
    [Fact]
    public void ImmediateFirstStepKeepsAcceptanceDeadlineAndHold()
    {
        var now = 239.0;
        var input = new RecordingInput();
        var controller = Create(input, () => now);
        var request = Proposal();
        Assert.Null(controller.Submit(request, now, out var accepted));
        now = 240;
        RefreshWorld(controller);
        controller.TickFirstStandardStep(request.RequestId, 239);
        Assert.Equal(new[] { "W" }, input.Held);
        Assert.Equal(1, input.HeldCalls);
        Assert.Equal(1, input.MouseCalls);
        now = 251;
        controller.Tick(now);
        Assert.Equal(new[] { "W" }, input.Held);
        Assert.Empty(controller.DrainReceipts());
        now = 339;
        controller.Tick(now);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal(239, accepted);
        Assert.Equal(accepted, receipt.AcceptedAtMs);
        Assert.Equal(240, Assert.Single(receipt.AppliedSteps).StartedAtMs);
        Assert.Equal("horizon_complete", receipt.Reason);
        Assert.Equal(1, input.Releases);
    }

    /// <summary>Admission does not waive the exclusive source+150ms start bound or clock validity.</summary>
    [Theory]
    [InlineData(250, "start_deadline_expired")]
    [InlineData(251, "start_deadline_expired")]
    [InlineData(double.NaN, "invalid_start_clock")]
    [InlineData(238, "invalid_start_clock")]
    public void FinalClockStillRejectsLateOrInvalidFirstStep(double dispatchClock, string reason)
    {
        var now = 239.0;
        var input = new RecordingInput();
        var controller = Create(input, () => now);
        Assert.Null(controller.Submit(Proposal(), now));
        // Keep the latest world evidence fresh so only the original request's source deadline is tested.
        RefreshWorld(controller);
        now = dispatchClock;
        controller.TickFirstStandardStep("proposal", 239);
        Assert.Equal(0, input.HeldCalls);
        Assert.Equal(0, input.MouseCalls);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal(reason, receipt.Reason);
        Assert.Empty(receipt.AppliedSteps);
        Assert.Equal(1, input.Releases);
        // A normal deadline cancellation is not a dispatch fault and does not disable fresh admission.
        now = 260;
        Assert.Null(controller.Submit(Proposal() with
        {
            RequestId = "fresh", FrameId = 3, ObservedAtMs = 240, StartBeforeMs = 370
        }, now));
    }

    /// <summary>Focus or a newly blocked world can revoke an already accepted standard request before its fast tick.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void ChangedReadinessOrInputStillPreventsDispatch(bool blockedWorld)
    {
        var input = new RecordingInput();
        var controller = Create(input, () => 130);
        Assert.Null(controller.Submit(Proposal(), 130));
        if (blockedWorld) controller.InvalidateWorld(130, "fixture_modal");
        else input.Available = false;
        controller.TickFirstStandardStep("proposal", 130);
        Assert.Equal(0, input.HeldCalls);
        Assert.Equal(0, input.MouseCalls);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal(blockedWorld ? "fixture_modal" : "window_unavailable", receipt.Reason);
        Assert.Empty(receipt.AppliedSteps);
    }

    /// <summary>If the periodic tick won, the request fast path must not dispatch a later interval even when it is due.</summary>
    [Fact]
    public void TimerWinnerLeavesLaterStepsOnTheirOriginalSchedule()
    {
        var now = 130.0;
        var input = new RecordingInput();
        var controller = Create(input, () => now);
        var request = Proposal() with
        {
            Steps = [new() { DurationMs = 50, Keys = ["W"] }, new() { DurationMs = 50, Keys = ["S"] }]
        };
        Assert.Null(controller.Submit(request, now));
        controller.Tick(now);
        now = 180;
        controller.TickFirstStandardStep(request.RequestId, now);
        Assert.Equal(1, input.HeldCalls);
        Assert.Equal(new[] { "W" }, input.Held);
        controller.Tick(now);
        Assert.Equal(2, input.HeldCalls);
        Assert.Equal(new[] { "S" }, input.Held);
        now = 230;
        controller.Tick(now);
        Assert.Equal(2, Assert.Single(controller.DrainReceipts()).AppliedSteps.Length);
    }

    /// <summary>A stale action callback cannot dispatch a replacement's first step under the old request identity.</summary>
    [Fact]
    public void ImmediateTickRequiresTheSamePendingRequest()
    {
        var input = new RecordingInput();
        var controller = Create(input, () => 130);
        Assert.Null(controller.Submit(Proposal() with { RequestId = "old" }, 130));
        Assert.Null(controller.Submit(Proposal() with { RequestId = "next" }, 130));
        controller.TickFirstStandardStep("old", 130);
        Assert.Equal(0, input.HeldCalls);
        controller.TickFirstStandardStep("next", 130);
        controller.TickFirstStandardStep("next", 130);
        Assert.Equal(1, input.HeldCalls);
        Assert.Equal(1, input.MouseCalls);
    }

    /// <summary>A stop between admission and the fast path still releases and records the unstarted request.</summary>
    [Fact]
    public void StopBeforeImmediateTickCannotDispatch()
    {
        var input = new RecordingInput();
        var controller = Create(input, () => 130);
        Assert.Null(controller.Submit(Proposal(), 130));
        controller.Stop(130, "fixture_stop");
        controller.TickFirstStandardStep("proposal", 130);
        controller.Tick(130);
        Assert.Equal(0, input.HeldCalls);
        Assert.Equal(1, input.Releases);
        Assert.Empty(Assert.Single(controller.DrainReceipts()).AppliedSteps);
        Assert.Equal("session_stopped", controller.Submit(Proposal() with { RequestId = "after_stop" }, 130));
    }

    /// <summary>Either dispatch caller can fault after partial keys or movement; neither caller may repeat the intent.</summary>
    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public void PartialFailureLatchesAcrossBothCallersWithoutSuppressingStop(bool timerFirst, bool failHeld)
    {
        var input = new RecordingInput { FailHeld = failHeld, FailMouse = !failHeld };
        var controller = Create(input, () => 130);
        Assert.Null(controller.Submit(Proposal(), 130));
        var error = Record.Exception(() => Dispatch(controller, timerFirst));
        Assert.Same(input.DispatchError, error);
        controller.Tick(130);
        controller.TickFirstStandardStep("proposal", 130);
        Assert.Equal(1, input.HeldCalls);
        Assert.Equal(failHeld ? 0 : 1, input.MouseCalls);
        Assert.Equal(new[] { "W" }, input.Held);
        Assert.Equal(0, input.Releases);
        Assert.Equal("input_dispatch_failed", controller.Submit(Proposal() with { RequestId = "after_fault" }, 130));
        controller.Stop(130, "session_ended");
        Assert.Equal(1, input.Releases);
        Assert.Empty(input.Held);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal("session_ended", receipt.Reason);
        Assert.Empty(receipt.AppliedSteps);
    }

    /// <summary>A release exception is still observable and the receipt is retained despite the separate dispatch latch.</summary>
    [Fact]
    public void StopReleaseFailureStillPublishesTheTerminalReceipt()
    {
        var input = new RecordingInput { FailMouse = true, FailRelease = true };
        var controller = Create(input, () => 130);
        Assert.Null(controller.Submit(Proposal(), 130));
        Assert.Same(input.DispatchError, Record.Exception(() => controller.TickFirstStandardStep("proposal", 130)));
        Assert.Same(input.ReleaseError, Record.Exception(() => controller.Stop(130, "session_ended")));
        Assert.Equal(1, input.Releases);
        Assert.Empty(Assert.Single(controller.DrainReceipts()).AppliedSteps);
        controller.Tick(130);
        controller.TickFirstStandardStep("proposal", 130);
        Assert.Equal(1, input.MouseCalls);
        Assert.Equal(1, input.Releases);
    }

    /// <summary>Ordinary release and new positive observations cannot rearm a controller after partial dispatch.</summary>
    [Fact]
    public void ReleaseAndFreshWorldCannotClearDispatchFault()
    {
        var now = 130.0;
        var input = new RecordingInput { FailMouse = true };
        var controller = Create(input, () => now);
        Assert.Null(controller.Submit(Proposal(), now));
        Assert.Same(input.DispatchError, Record.Exception(() => controller.TickFirstStandardStep("proposal", now)));
        controller.Release(now);
        now = 200;
        controller.RegisterFrame(new(3, 170, 1920, 1080, AgentWorldEvidence.WorldHud, 0,
            new AgentSourceFrame(CaptureEpoch, 1000001800, 180, 150)));
        Assert.True(controller.RegisterFrame(new(4, 200, 1920, 1080, AgentWorldEvidence.WorldHud, 0,
            new AgentSourceFrame(CaptureEpoch, 1000002100, 210, 180))).Ready);
        Assert.Equal("input_dispatch_failed", controller.Submit(Proposal() with
        {
            RequestId = "fresh", FrameId = 4, ObservedAtMs = 200, StartBeforeMs = 330
        }, now));
        controller.Tick(now);
        controller.TickFirstStandardStep("fresh", now);
        Assert.Equal(1, input.HeldCalls);
        Assert.Equal(1, input.MouseCalls);
        Assert.Equal(1, input.Releases);
        Assert.Equal("client_release", Assert.Single(controller.DrainReceipts()).Reason);
    }

    /// <summary>A competing caller already waiting on the input gate cannot retry the first caller's partial failure.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ConcurrentWaiterCannotRepeatPartialDispatch(bool timerFirst)
    {
        using var entered = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        using var waiting = new ManualResetEventSlim();
        var input = new RecordingInput { FailMouse = true, MouseEntered = entered, ContinueMouse = release };
        var controller = Create(input, () => 130);
        Assert.Null(controller.Submit(Proposal(), 130));
        var first = Task.Run(() => Record.Exception(() => Dispatch(controller, timerFirst)));
        Task<Exception?>? second = null;
        try
        {
            Assert.True(entered.Wait(TimeSpan.FromSeconds(5)), "The first fake input call did not enter.");
            second = Task.Run<Exception?>(() =>
            {
                waiting.Set();
                return Record.Exception(() => Dispatch(controller, !timerFirst));
            });
            Assert.True(waiting.Wait(TimeSpan.FromSeconds(5)), "The competing fake caller did not start.");
            release.Set();
            Assert.Same(input.DispatchError, await first.WaitAsync(TimeSpan.FromSeconds(10)));
            Assert.Null(await second.WaitAsync(TimeSpan.FromSeconds(10)));
            Assert.Equal(1, input.HeldCalls);
            Assert.Equal(1, input.MouseCalls);
            Assert.Equal("input_dispatch_failed", controller.Submit(Proposal() with { RequestId = "after_fault" }, 130));
        }
        finally
        {
            // Every fixture wait is bounded, and both fake callers finish before the events are disposed.
            release.Set();
            await first.WaitAsync(TimeSpan.FromSeconds(10));
            if (second is not null) await second.WaitAsync(TimeSpan.FromSeconds(10));
            controller.Stop(130, "fixture_stop");
        }
        Assert.Equal(1, input.Releases);
        Assert.Empty(Assert.Single(controller.DrainReceipts()).AppliedSteps);
    }

    /// <summary>Select only the two actual controller entry points; all time and input are fixture-owned.</summary>
    private static void Dispatch(AgentActionController controller, bool timer)
    {
        if (timer) controller.Tick(130);
        else controller.TickFirstStandardStep("proposal", 130);
    }

    /// <summary>Establish two native-shaped positive observations without reading a screen or invoking recognition.</summary>
    private static AgentActionController Create(RecordingInput input, Func<double> clock)
    {
        var controller = new AgentActionController(input, true, clock);
        controller.RegisterFrame(new(1, 80, 1920, 1080, AgentWorldEvidence.WorldHud, 0,
            new AgentSourceFrame(CaptureEpoch, 1000000900, 90, 60)));
        Assert.True(controller.RegisterFrame(new(2, 120, 1920, 1080, AgentWorldEvidence.WorldHud, 0,
            new AgentSourceFrame(CaptureEpoch, 1000001300, 130, 100))).Ready);
        return controller;
    }

    /// <summary>Refresh only latest-world readiness; an accepted request still owns its original source and deadline.</summary>
    private static void RefreshWorld(AgentActionController controller) =>
        Assert.True(controller.RegisterFrame(new(3, 240, 1920, 1080, AgentWorldEvidence.WorldHud, 0,
            new AgentSourceFrame(CaptureEpoch, 1000002500, 250, 220))).Ready);

    /// <summary>Use the unchanged 150ms first-input source cap and an ordinary 100ms standard hold.</summary>
    private static AgentRequest Proposal() => new()
    {
        RequestId = "proposal", ModelId = "immediate-dispatch-fixture", FrameId = 2, ObservedAtMs = 120,
        ExpiresAtMs = 800, StartBeforeMs = 250,
        Steps = [new() { DurationMs = 100, Keys = ["W"], MouseDx = 5 }]
    };

    /// <summary>Controlled partial software input plus bounded synchronization, with no OS input/backend calls.</summary>
    private sealed class RecordingInput : IAgentInput
    {
        /// <summary>Mutable fake availability exercises the original final input gate.</summary>
        internal bool Available = true;
        /// <summary>Independent failures distinguish held/movement intent from later release cleanup.</summary>
        internal bool FailHeld, FailMouse, FailRelease;
        /// <summary>Actual attempted call counts, serialized by the production controller gate.</summary>
        internal int HeldCalls, MouseCalls, Releases;
        /// <summary>Fake key ownership remains visible after a partial movement failure.</summary>
        internal string[] Held = [];
        /// <summary>Optional bounded gate used only by the concurrent-caller fixture.</summary>
        internal ManualResetEventSlim? MouseEntered, ContinueMouse;
        /// <summary>Exact first failure and cleanup exception identities remain distinguishable.</summary>
        internal readonly InvalidOperationException DispatchError = new("fixture_partial_dispatch"),
            ReleaseError = new("fixture_release");
        /// <inheritdoc />
        public bool IsAvailable => Available;
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys)
        {
            HeldCalls++;
            Held = keys.ToArray();
            if (FailHeld) throw DispatchError;
        }
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy)
        {
            MouseCalls++;
            MouseEntered?.Set();
            if (ContinueMouse is not null && !ContinueMouse.Wait(TimeSpan.FromSeconds(10)))
                throw new TimeoutException("The fake movement gate was not released.");
            if (FailMouse) throw DispatchError;
        }
        /// <inheritdoc />
        public void ReleaseAll()
        {
            Releases++;
            if (FailRelease) throw ReleaseError;
            Held = [];
        }
    }
}
