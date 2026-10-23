using BetterGenshinImpact.Core.Agent;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>First-input deadlines use source authority and the dispatch clock without shortening started holds.</summary>
public sealed class AgentActionStartDeadlineTests
{
    /// <summary>Stable native generation used by the deterministic capture fixtures.</summary>
    private const string Epoch = "33333333333333333333333333333333";

    /// <summary>A proposal can expire during transport even while the world gate itself remains fresh.</summary>
    [Theory]
    [InlineData(150)]
    [InlineData(151)]
    public void RejectsExpiredStartBeforeAcceptance(double now)
    {
        var input = new RecordingInput();
        var controller = Create(input);
        Assert.Equal("start_deadline_expired", controller.Submit(Proposal(), now));
        controller.Tick(now);
        Assert.Empty(input.Held);
        Assert.Empty(input.Movements);
        Assert.Empty(controller.DrainReceipts());
    }

    /// <summary>An accepted proposal is cancelled if the first tick reaches its exclusive start deadline.</summary>
    [Fact]
    public void CancelsAcceptedProposalAtLateFirstTick()
    {
        var input = new RecordingInput();
        var controller = Create(input);
        Assert.Null(controller.Submit(Proposal(), 130));
        controller.Tick(150);
        Assert.Empty(input.Held);
        Assert.Empty(input.Movements);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal("cancelled", receipt.Status);
        Assert.Equal("start_deadline_expired", receipt.Reason);
        Assert.Empty(receipt.AppliedSteps);
    }

    /// <summary>The injected clock includes admission-lock delay that the caller's earlier sample cannot see.</summary>
    [Fact]
    public void AcceptanceChecksCurrentSessionClock()
    {
        var controller = Create(new RecordingInput(), () => 151);
        Assert.Equal("start_deadline_expired", controller.Submit(Proposal(), 130));
    }

    /// <summary>The final dispatch check includes lock/focus delay after the scheduler sampled its tick time.</summary>
    [Fact]
    public void FirstTickResamplesClockBeforeDispatch()
    {
        var actualTime = 130.0;
        var input = new RecordingInput();
        var controller = Create(input, () => actualTime);
        Assert.Null(controller.Submit(Proposal(), 130));
        actualTime = 151;
        controller.Tick(140);
        Assert.Empty(input.Held);
        Assert.Empty(input.Movements);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal("start_deadline_expired", receipt.Reason);
        Assert.Equal(151, receipt.EndedAtMs);
    }

    /// <summary>Receipts expose the sampled acceptance and first-dispatch times rather than stale caller samples.</summary>
    [Fact]
    public void RecordsRefreshedAcceptanceAndFirstDispatchTimes()
    {
        var actualTime = 135.0;
        var controller = Create(new RecordingInput(), () => actualTime);
        Assert.Null(controller.Submit(Proposal(), 130, out var acceptedAt));
        Assert.Equal(135, acceptedAt);
        actualTime = 145;
        controller.Tick(140);
        controller.Tick(235);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal(135, receipt.AcceptedAtMs);
        Assert.Equal(145, Assert.Single(receipt.AppliedSteps).StartedAtMs);
        Assert.Equal("completed", receipt.Status);
    }

    /// <summary>A tick queued before acceptance can still dispatch on time after obtaining the controller lock.</summary>
    [Fact]
    public void PendingTickRefreshesBeforeComparingAcceptanceSchedule()
    {
        var actualTime = 145.0;
        var input = new RecordingInput();
        var controller = Create(input, () => actualTime);
        Assert.Null(controller.Submit(Proposal(), 130, out var acceptedAt));
        Assert.Equal(145, acceptedAt);
        actualTime = 147;
        controller.Tick(140);
        Assert.Equal(new[] { "W" }, input.Held);
        Assert.Single(input.Movements);
        controller.Tick(245);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal("completed", receipt.Status);
        Assert.Equal(147, Assert.Single(receipt.AppliedSteps).StartedAtMs);
    }

    /// <summary>A stale tick must not conceal a current-clock regression below the already-recorded acceptance.</summary>
    [Fact]
    public void PendingTickRejectsClockEarlierThanAcceptance()
    {
        var actualTime = 145.0;
        var input = new RecordingInput();
        var controller = Create(input, () => actualTime);
        Assert.Null(controller.Submit(Proposal(), 130));
        actualTime = 142;
        controller.Tick(140);
        Assert.Empty(input.Held);
        Assert.Empty(input.Movements);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal("invalid_start_clock", receipt.Reason);
        Assert.Empty(receipt.AppliedSteps);
        Assert.Equal(145, receipt.EndedAtMs);
    }

    /// <summary>The optional start deadline does not truncate an on-time 100ms interval after it has begun.</summary>
    [Fact]
    public void StartedHoldContinuesPastStartDeadline()
    {
        var input = new RecordingInput();
        var controller = Create(input);
        Assert.Null(controller.Submit(Proposal(), 130));
        controller.Tick(130);
        controller.Tick(150);
        controller.Tick(229);
        Assert.Equal(new[] { "W" }, input.Held);
        Assert.Single(input.Movements);
        controller.Tick(230);
        Assert.Empty(input.Held);
        Assert.Equal("completed", Assert.Single(controller.DrainReceipts()).Status);
    }

    /// <summary>Later intervals retain their normal schedule and do not resample the first-input-only clock.</summary>
    [Fact]
    public void LaterIntervalsIgnoreStartDeadlineAndItsClock()
    {
        var failClock = false;
        var input = new RecordingInput();
        var controller = Create(input, () => failClock ? throw new InvalidOperationException("first input already started") : 130);
        Assert.Null(controller.Submit(Proposal() with
        {
            Steps = [new() { DurationMs = 50, Keys = ["W"] }, new() { DurationMs = 50, Keys = ["S"] }]
        }, 130));
        controller.Tick(130);
        failClock = true;
        controller.Tick(180);
        Assert.Equal(new[] { "S" }, input.Held);
        controller.Tick(230);
        var receipt = Assert.Single(controller.DrainReceipts());
        Assert.Equal("completed", receipt.Status);
        Assert.Equal(2, receipt.AppliedSteps.Length);
    }

    /// <summary>Bad current-clock samples cannot authorize acceptance even when the caller timestamp looks valid.</summary>
    [Theory]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    [InlineData(120)]
    public void InvalidAcceptanceClockIsRejected(double invalidTime)
    {
        var controller = Create(new RecordingInput(), () => invalidTime);
        Assert.Equal("invalid_start_clock", controller.Submit(Proposal(), 130));
    }

    /// <summary>Omitting the new field retains legacy admission/scheduling and never samples its optional clock.</summary>
    [Fact]
    public void LegacyRequestsDoNotUseStartDeadlineClock()
    {
        var input = new RecordingInput();
        var controller = Create(input, () => throw new InvalidOperationException("Unused optional clock."));
        Assert.Null(controller.Submit(Proposal() with { StartBeforeMs = null }, 130));
        controller.Tick(160);
        Assert.Equal(new[] { "W" }, input.Held);
        controller.Tick(230);
        Assert.Equal("completed", Assert.Single(controller.DrainReceipts()).Status);
    }

    /// <summary>First-start limits are finite, after the source anchor, and within both execution and age ceilings.</summary>
    [Theory]
    [InlineData(double.NaN, 800)]
    [InlineData(double.PositiveInfinity, 800)]
    [InlineData(double.NegativeInfinity, 800)]
    [InlineData(99, 800)]
    [InlineData(100, 800)]
    [InlineData(600.001, 800)]
    [InlineData(400.001, 400)]
    public void RejectsMalformedOrOutOfRangeStartDeadline(double startBefore, double expires)
    {
        var controller = Create(new RecordingInput());
        Assert.Equal("invalid_start_deadline", controller.Submit(
            Proposal() with { StartBeforeMs = startBefore, ExpiresAtMs = expires }, 130));
    }

    /// <summary>The age ceiling follows known source freshness, otherwise the existing explicit host-time fallback.</summary>
    [Theory]
    [InlineData(true, 600)]
    [InlineData(false, 620)]
    public void AcceptsExactSourceOrHostAgeCeiling(bool knownSource, double maximum)
    {
        var controller = Create(new RecordingInput(), knownSource: knownSource);
        Assert.Null(controller.Submit(Proposal() with { StartBeforeMs = maximum }, 130));
        Assert.Equal("invalid_start_deadline", controller.Submit(
            Proposal() with { RequestId = "out-of-range", StartBeforeMs = maximum + 0.001 }, 130));
    }

    /// <summary>A cancelled replacement must release inherited held keys and may not issue its queued movement.</summary>
    [Fact]
    public void LateReplacementReleasesPreviouslyHeldKeysAndAllowsFreshActions()
    {
        var input = new RecordingInput();
        var controller = Create(input);
        Assert.Null(controller.Submit(Proposal() with { RequestId = "old", StartBeforeMs = null }, 130));
        controller.Tick(130);
        var replacement = Proposal() with
        {
            RequestId = "replacement", Steps = [new() { DurationMs = 100, Keys = ["S"], MouseDx = 20 }]
        };
        Assert.Null(controller.Submit(replacement, 140));
        Assert.Equal(new[] { "W" }, input.Held);
        controller.Tick(151);
        Assert.Empty(input.Held);
        Assert.Single(input.Movements);
        var receipts = controller.DrainReceipts();
        Assert.Equal("replaced", receipts[0].Status);
        Assert.Equal("start_deadline_expired", receipts[1].Reason);
        Assert.Empty(receipts[1].AppliedSteps);
        Assert.Null(controller.Submit(Proposal() with { RequestId = "fresh", StartBeforeMs = 250 }, 160));
        controller.Tick(160);
        Assert.Equal(new[] { "W" }, input.Held);
    }

    /// <summary>Nonfinite or regressing clock samples cannot dispatch a replacement or leave its inherited keys held.</summary>
    [Theory]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    [InlineData(120)]
    public void InvalidFirstTickClockCancelsAndReleases(double invalidTime)
    {
        var actualTime = 140.0;
        var input = new RecordingInput();
        var controller = Create(input, () => actualTime);
        Assert.Null(controller.Submit(Proposal() with { RequestId = "old", StartBeforeMs = null }, 130));
        controller.Tick(130);
        Assert.Null(controller.Submit(Proposal(), 140));
        actualTime = invalidTime;
        controller.Tick(145);
        Assert.Empty(input.Held);
        var receipt = controller.DrainReceipts().Last();
        Assert.Equal("invalid_start_clock", receipt.Reason);
        Assert.Empty(receipt.AppliedSteps);
        Assert.True(double.IsFinite(receipt.EndedAtMs));
    }

    /// <summary>Clock exceptions are contained for both admission and first dispatch, with no input authorization.</summary>
    [Fact]
    public void ThrowingClockFailsClosedAtAcceptanceAndFirstTick()
    {
        var failClock = false;
        var input = new RecordingInput();
        var controller = Create(input, () => failClock ? throw new InvalidOperationException("clock failed") : 130);
        Assert.Null(controller.Submit(Proposal(), 130));
        failClock = true;
        controller.Tick(140);
        Assert.Empty(input.Held);
        Assert.Equal("invalid_start_clock", Assert.Single(controller.DrainReceipts()).Reason);
        Assert.Equal("invalid_start_clock", controller.Submit(Proposal() with { RequestId = "next" }, 140));
    }

    /// <summary>Establish two positive captures with independent host polls and acquisition-based source freshness.</summary>
    private static AgentActionController Create(RecordingInput input, Func<double>? clock = null, bool knownSource = true)
    {
        var controller = new AgentActionController(input, true, clock);
        controller.RegisterFrame(Frame(1, 80, 60, knownSource));
        Assert.True(controller.RegisterFrame(Frame(2, 120, 100, knownSource)).Ready);
        return controller;
    }

    /// <summary>Reported compositor time intentionally leads immutable acquisition by 30ms in the native fixture.</summary>
    private static AgentObservation Frame(long id, double host, double acquired, bool knownSource) =>
        new(id, host, 1920, 1080, AgentWorldEvidence.WorldHud, 0, knownSource
            ? new AgentSourceFrame(Epoch, 1000000000 + (long)((acquired + 30) * 10000), acquired + 30, acquired)
            : null);

    /// <summary>A 100ms action whose optional start deadline is earlier than its unchanged execution expiry.</summary>
    private static AgentRequest Proposal() => new()
    {
        RequestId = "deadline", ModelId = "start-deadline-fixture", FrameId = 2, ObservedAtMs = 120,
        ExpiresAtMs = 800, StartBeforeMs = 150,
        Steps = [new() { DurationMs = 100, Keys = ["W"], MouseDx = 5 }]
    };

    /// <summary>Records dispatch intent in memory; no Windows input or game window is used.</summary>
    private sealed class RecordingInput : IAgentInput
    {
        /// <inheritdoc />
        public bool IsAvailable => true;
        /// <summary>Current keys held by the fixture.</summary>
        public string[] Held { get; private set; } = [];
        /// <summary>Relative movement dispatches actually attempted.</summary>
        public List<(int Dx, int Dy)> Movements { get; } = [];
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) => Held = keys.ToArray();
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) => Movements.Add((dx, dy));
        /// <inheritdoc />
        public void ReleaseAll() => Held = [];
    }
}
