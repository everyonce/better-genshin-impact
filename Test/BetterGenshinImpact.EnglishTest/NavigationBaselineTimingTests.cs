using System.Diagnostics;
using System.Text;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.GameTask.SoloTask.Execution;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Fixed timing selection, fake-clock dispatch and wire tests; no game or native input.</summary>
public sealed class NavigationBaselineTimingTests
{
    /// <summary>Stable native generation for deterministic synthetic frame clocks.</summary>
    private static readonly Guid Epoch = Guid.Parse("48f54548-2d13-43ea-a217-c015fcaa25a6");
    /// <summary>Construct immutable clocks with an optional future/older compositor timestamp.</summary>
    private static GameCaptureSourceInfo Source(double acquisition, double? reported = null) => new(Epoch,
        (long)((reported ?? acquisition) * 10_000), (long)(acquisition * Stopwatch.Frequency / 1000));
    /// <summary>Faulted input is still explicitly released and its monitor drained during disposal.</summary>
    private static async Task DisposeFaulted(NavigationBaselineInputLease lease)
    { try { await lease.DisposeAsync(); } catch (InvalidOperationException) { } }

    /// <summary>V2 caps the first grant while retaining the exact150ms source admission ceiling.</summary>
    [Theory]
    [InlineData(0, 150)]
    [InlineData(100, 150)]
    [InlineData(125, 125)]
    [InlineData(150, 100)]
    public async Task FirstGrantUsesConservativeSourceCap(double age, double lifetime)
    {
        double now = 1000; var downs = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V2);
        // A future compositor timestamp cannot conceal the older acquisition.
        var input = lease.Forward(Source(now - age, 1100), default);
        Assert.Equal(now + lifetime, input.ExpiresAtMs); Assert.Equal(150, input.GrantMs);
        Assert.Equal(now - age, input.SourceAnchorAtMs); Assert.Equal(now - age + 250, input.SourceCapAtMs);
        Assert.True(input.FirstForwardAttempt); Assert.Equal(1, downs);
    }

    /// <summary>Older compositor time is the limiting source even when acquisition is recent.</summary>
    [Fact]
    public async Task FirstGrantAlsoHonorsOlderReportedClock()
    {
        double now = 1000;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { }, _ => { },
            default, false, NavigationBaselineTiming.V2);
        var input = lease.Forward(Source(990, 875), default);
        Assert.Equal(1125, input.ExpiresAtMs); Assert.Equal(875, input.SourceAnchorAtMs);
    }

    /// <summary>Omitted and explicit v1 retain original100ms arithmetic at every accepted source age.</summary>
    [Theory]
    [InlineData(0)]
    [InlineData(100)]
    [InlineData(150)]
    public async Task V1IsExactAndDefault(double age)
    {
        double now = 1000;
        await using var legacy = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { }, _ => { }, default, false);
        await using var explicitV1 = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { }, _ => { }, default, false, NavigationBaselineTiming.V1);
        var original = legacy.Forward(Source(now - age), default);
        Assert.Equal(original, explicitV1.Forward(Source(now - age), default));
        Assert.Equal(now + 100, original.ExpiresAtMs); Assert.Null(original.SourceCapAtMs);
    }

    /// <summary>Camera activity does not consume the first grant; release/realignment never rearms it.</summary>
    [Fact]
    public async Task OnlyFirstDownAttemptGetsLongGrantAcrossRealignment()
    {
        double now = 1000; var downs = 0; var ups = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => ups++, _ => { },
            default, false, NavigationBaselineTiming.V2);
        lease.Rotate(Source(990), 2, default);
        now = 1100; var first = lease.Forward(Source(1090), default);
        Assert.Equal(1250, first.ExpiresAtMs); Assert.True(first.FirstForwardAttempt);
        now = 1160; var renewal = lease.Forward(Source(1150), default);
        Assert.Equal(1260, renewal.ExpiresAtMs); Assert.Equal(100, renewal.GrantMs); Assert.False(renewal.FirstForwardAttempt);
        now = 1170; lease.ReleaseForward();
        now = 1260; lease.Rotate(Source(1250), 2, default);
        now = 1350; var next = lease.Forward(Source(1340), default);
        Assert.Equal(1450, next.ExpiresAtMs); Assert.Equal(100, next.GrantMs); Assert.False(next.FirstForwardAttempt);
        Assert.Equal(2, downs); Assert.Equal(1, ups);
    }

    /// <summary>Each renewal replaces its grant; retaining a larger old expiry would conceal the selected contract.</summary>
    [Fact]
    public async Task EarlyRenewalDoesNotTakeMaximumWithOldExpiry()
    {
        double now = 1000;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { }, _ => { },
            default, false, NavigationBaselineTiming.V2);
        Assert.Equal(1150, lease.Forward(Source(990), default).ExpiresAtMs);
        now = 1010;
        Assert.Equal(1110, lease.Forward(Source(1005), default).ExpiresAtMs);
    }

    /// <summary>Late target checks and exact expiry both fault before a renewal can overwrite the old deadline.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ExpiredInitialGrantCannotBeRevived(bool delayedAvailability)
    {
        double now = 1000; var delay = false; var downs = 0; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => { if (delay) now = 1150; return true; },
            () => downs++, () => ups++, _ => { }, default, false, NavigationBaselineTiming.V2);
        try
        {
            lease.Forward(Source(990), default); now = delayedAvailability ? 1140 : 1150; delay = delayedAvailability;
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(1130), default));
            Assert.Equal("forward_lease_expired", lease.Fault); Assert.Equal(1, downs); Assert.Equal(1, ups);
            now = 1170; delay = false;
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(1160), default));
            Assert.Equal(1, downs);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>A slow down consumes the grant; actual late release remains evidence instead of a scheduling claim.</summary>
    [Theory]
    [InlineData(1150)]
    [InlineData(1171)]
    public async Task NativeDownAtOrBeyondExpiryReleasesAndReportsActualClocks(double downCompleted)
    {
        double now = 1000; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => now = downCompleted,
            () => { ups++; now += 3; }, _ => { }, default, false, NavigationBaselineTiming.V2);
        try
        {
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(990), default));
            var press = lease.Events.Single(item => item.Kind == "w_down");
            Assert.Equal(1150, press.ExpiresAtMs); Assert.Equal(downCompleted, press.CompletedAtMs);
            Assert.Equal(150, press.GrantMs); Assert.True(press.FirstForwardAttempt);
            Assert.Equal(downCompleted + 3, lease.Events.Single(item => item.Kind == "w_up").CompletedAtMs);
            Assert.Equal(1, ups); Assert.False(lease.ForwardHeld);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Neither larger first grants nor source caps allow a stale frame to authorize input.</summary>
    [Fact]
    public async Task V2DoesNotRelaxFreshness()
    {
        double now = 1000; var downs = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => { }, _ => { },
            default, false, NavigationBaselineTiming.V2);
        try
        {
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(849), default));
            Assert.Equal("native_source_stale", lease.Fault); Assert.Equal(0, downs);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Reject malformed/nonpositive computed authority before any native sink can use it.</summary>
    [Theory]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    [InlineData(1250)]
    public void V2GrantRejectsUnusableDeadline(double now) => Assert.Throws<InvalidOperationException>(() =>
        NavigationBaselineTiming.Grant(NavigationBaselineTiming.V2, true, true, Source(1000), now));

    /// <summary>Unknown selectors fail before clocks, watchdogs or input are touched.</summary>
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("V2")]
    [InlineData("v5")]
    public void InvalidContractCannotCreateLease(string? contract)
    {
        var calls = 0;
        Assert.Throws<ArgumentException>(() => new NavigationBaselineInputLease(() => { calls++; return 1000; },
            () => true, () => { }, () => { }, _ => { }, default, false, contract!));
        Assert.Equal(0, calls);
    }

    /// <summary>Only the authenticated fixed-leg start accepts the additive field; explicit null never defaults.</summary>
    [Theory]
    [InlineData("startNavigationBaseline", null, null)]
    [InlineData("startNavigationBaseline", "\"v1\"", null)]
    [InlineData("startNavigationBaseline", "\"v2\"", null)]
    [InlineData("startNavigationBaseline", "\"v3\"", null)]
    [InlineData("startNavigationBaseline", "\"v4\"", null)]
    [InlineData("startNavigationBaseline", "null", "invalid_command_parameters")]
    [InlineData("startNavigationBaseline", "\"v5\"", "invalid_command_parameters")]
    [InlineData("startAgentStream", "\"v2\"", "unexpected_command_parameters")]
    [InlineData("status", "null", "unexpected_command_parameters")]
    public void WireSelectionIsExact(string command, string? literal, string? rejection)
    {
        var json = "{\"version\":1,\"requestId\":\"" + Guid.NewGuid() + "\",\"createdAtUnixMs\":"
            + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + ",\"command\":\"" + command
            + "\",\"targetProcessId\":20,\"targetWindowsSessionId\":3,\"targetNonce\":\"fixed\""
            + (literal is null ? "" : ",\"timingContract\":" + literal) + "}";
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes(json), out var request));
        Assert.Equal(rejection, ExternalControlProtocol.ValidateRequest(request!, DateTimeOffset.UtcNow));
    }

    /// <summary>Failure before native construction still retains the admitted contract and controller identity.</summary>
    [Theory]
    [InlineData("v2")]
    [InlineData("v3")]
    [InlineData("v4")]
    public async Task OwnerPreservesOptInContractOnEarlyFailure(string contract)
    {
        var owner = new NavigationBaselineTaskOwner();
        Assert.True(owner.TryStart(10, 3, (_, _, _) => Task.FromResult((new SoloTaskRunResult
            { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = "synthetic_native_failure" }, (NavigationBaselineRunResult?)null)),
            timingContract: contract));
        var wait = Stopwatch.StartNew();
        while (owner.Running && wait.Elapsed < TimeSpan.FromSeconds(5)) await Task.Delay(1);
        Assert.False(owner.Running);
        var status = owner.Snapshot(true);
        Assert.Equal("failed", status.State);
        Assert.Equal(contract, status.TimingContract); Assert.Equal(contract, status.Result!.TimingContract);
        Assert.Equal($"native-fixed-leg-feedback-{contract}", status.Result.ControllerMethod);
        Assert.Equal(new[] { "v1", "v2", "v3", "v4" }, status.TimingContracts);
    }
}
