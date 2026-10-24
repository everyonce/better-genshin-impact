using System.Diagnostics;
using System.IO;
using System.Text.Json;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Fake-clock physical-start/renewal and evidence tests; no game, capture or OS input is used.</summary>
public sealed class NavigationBaselineTimingV3Tests
{
    /// <summary>One immutable synthetic capture generation across a complete lease sequence.</summary>
    private static readonly Guid Epoch = Guid.Parse("44bf102c-21cd-4e3c-9e2a-65f3becfe998");

    /// <summary>Preserve both independent native clocks so either can limit the source-relative grant.</summary>
    private static GameCaptureSourceInfo Source(double acquisition, double? reported = null) => new(Epoch,
        (long)((reported ?? acquisition) * 10_000), (long)(acquisition * Stopwatch.Frequency / 1000));

    /// <summary>Drain a faulted lease while retaining its already-asserted terminal error.</summary>
    private static async Task DisposeFaulted(NavigationBaselineInputLease lease)
    { try { await lease.DisposeAsync(); } catch (InvalidOperationException) { } }

    /// <summary>Only v3 lengthens later physical starts; all versions renew without another keydown or relabeling first.</summary>
    [Theory]
    [InlineData("v1", 100, 100)]
    [InlineData("v2", 150, 100)]
    [InlineData("v3", 150, 150)]
    public async Task PhysicalStartsAreIndependentFromRenewalAndRunFirstIdentity(string contract, double firstGrant, double laterGrant)
    {
        double now = 900; var downs = 0; var ups = 0; var cameras = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => ups++,
            _ => cameras++, default, false, contract);
        lease.Rotate(Source(890), 2, default);
        now = 1000; var first = lease.Forward(Source(990), default);
        Assert.Equal(firstGrant, first.GrantMs); Assert.Equal(now + firstGrant, first.ExpiresAtMs);
        Assert.Equal("w_down", first.Kind); Assert.True(first.FirstForwardAttempt);
        now = 1060; var renewal = lease.Forward(Source(1050), default);
        Assert.Equal(100, renewal.GrantMs); Assert.Equal(1160, renewal.ExpiresAtMs);
        Assert.Equal("renew_w", renewal.Kind); Assert.False(renewal.FirstForwardAttempt);
        now = 1070; lease.ReleaseForward();
        now = 1160; lease.Rotate(Source(1150), -2, default);
        now = 1250; var later = lease.Forward(Source(1240), default);
        Assert.Equal(laterGrant, later.GrantMs); Assert.Equal(now + laterGrant, later.ExpiresAtMs);
        Assert.Equal("w_down", later.Kind); Assert.False(later.FirstForwardAttempt);
        now = 1310; var laterRenewal = lease.Forward(Source(1300), default);
        Assert.Equal(100, laterRenewal.GrantMs); Assert.Equal(1410, laterRenewal.ExpiresAtMs);
        Assert.False(laterRenewal.FirstForwardAttempt);
        Assert.Equal(2, downs); Assert.Equal(1, ups); Assert.Equal(2, cameras);
    }

    /// <summary>The second v3 start is independently capped by an old acquisition or reported source clock.</summary>
    [Theory]
    [InlineData(0, 150, false)]
    [InlineData(100, 150, false)]
    [InlineData(125, 125, false)]
    [InlineData(150, 100, false)]
    [InlineData(125, 125, true)]
    public async Task LaterPhysicalStartUsesConservativeSourceCap(double age, double lifetime, bool olderReported)
    {
        double now = 1000;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => { }, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V3);
        lease.Forward(Source(990), default);
        now = 1050; lease.ReleaseForward();
        now = 1300;
        var source = olderReported ? Source(1290, now - age) : Source(now - age, 1350);
        var input = lease.Forward(source, default);
        Assert.Equal(150, input.GrantMs); Assert.Equal(now + lifetime, input.ExpiresAtMs);
        Assert.Equal(now - age, input.SourceAnchorAtMs); Assert.Equal(now - age + 250, input.SourceCapAtMs);
        Assert.False(input.FirstForwardAttempt);
    }

    /// <summary>Early renewal replaces the previous deadline rather than inheriting a physical start's 150ms.</summary>
    [Fact]
    public async Task RenewalCanShortenAStartGrantAndNeverSendsAnotherDown()
    {
        double now = 1000; var downs = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => { },
            _ => { }, default, false, NavigationBaselineTiming.V3);
        Assert.Equal(1150, lease.Forward(Source(990), default).ExpiresAtMs);
        now = 1010; var renewal = lease.Forward(Source(1005), default);
        Assert.Equal(1110, renewal.ExpiresAtMs); Assert.Equal(100, renewal.GrantMs);
        Assert.Equal(1255, renewal.SourceCapAtMs); Assert.False(renewal.FirstForwardAttempt);
        Assert.Equal(1, downs);
    }

    /// <summary>Exact expiry or a delayed target check cannot renew the second start or authorize another press.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task LaterStartExpiryRemainsPermanentBeforeAndAfterTargetCheck(bool delayedTarget)
    {
        double now = 1000; var delay = false; var downs = 0; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => { if (delay) now = 1350; return true; },
            () => downs++, () => ups++, _ => { }, default, false, NavigationBaselineTiming.V3);
        try
        {
            lease.Forward(Source(990), default);
            now = 1050; lease.ReleaseForward();
            now = 1200; Assert.Equal(1350, lease.Forward(Source(1190), default).ExpiresAtMs);
            now = delayedTarget ? 1340 : 1350; delay = delayedTarget;
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(1330), default));
            Assert.Equal("forward_lease_expired", lease.Fault); Assert.Equal(2, downs); Assert.Equal(2, ups);
            delay = false; now = 1400;
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(1390), default));
            Assert.Equal(2, downs); Assert.False(lease.ForwardHeld);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>Later dispatch time consumes the grant anchored before the call, including when the source cap is tighter.</summary>
    [Theory]
    [InlineData(false, 1450)]
    [InlineData(false, 1471)]
    [InlineData(true, 1400)]
    public async Task LaterDownAtOrAfterDeadlineReleasesWithActualClocks(bool sourceCapped, double completed)
    {
        double now = 1000; var downs = 0; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => { if (++downs == 2) now = completed; }, () => { ups++; now += 3; }, _ => { },
            default, false, NavigationBaselineTiming.V3);
        try
        {
            lease.Forward(Source(990), default);
            now = 1050; lease.ReleaseForward();
            now = 1300;
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(sourceCapped ? 1150 : 1290), default));
            var press = lease.Events.Last(item => item.Kind == "w_down");
            Assert.Equal(sourceCapped ? 1400 : 1450, press.ExpiresAtMs);
            Assert.Equal(150, press.GrantMs); Assert.False(press.FirstForwardAttempt);
            Assert.Equal(completed, press.CompletedAtMs);
            Assert.Equal(completed + 3, lease.Events.Last(item => item.Kind == "w_up").CompletedAtMs);
            Assert.Equal("forward_lease_expired", lease.Fault); Assert.Equal(2, ups); Assert.False(lease.ForwardHeld);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>An ambiguous later keydown failure still releases and cannot become a fresh first attempt.</summary>
    [Fact]
    public async Task FailedLaterDownRetainsItsGrantAndNonFirstIdentity()
    {
        double now = 1000; var downs = 0; var ups = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => { if (++downs == 2) throw new IOException("synthetic partial down"); }, () => ups++, _ => { },
            default, false, NavigationBaselineTiming.V3);
        try
        {
            lease.Forward(Source(990), default);
            now = 1050; lease.ReleaseForward();
            now = 1200;
            Assert.Throws<IOException>(() => lease.Forward(Source(1190), default));
            var press = lease.Events.Last(item => item.Kind == "w_down");
            Assert.Equal(150, press.GrantMs); Assert.Equal(1350, press.ExpiresAtMs);
            Assert.False(press.FirstForwardAttempt); Assert.Equal("synthetic partial down", press.Error);
            Assert.Equal("forward_dispatch_failed", lease.Fault); Assert.Equal(2, ups);
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(1195), default));
            Assert.Equal(2, downs);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>V3 still rejects stale input evidence before a later physical start, with no inferred motion or cached reuse.</summary>
    [Fact]
    public async Task LaterStartDoesNotRelaxFreshness()
    {
        double now = 1000; var downs = 0;
        var lease = new NavigationBaselineInputLease(() => now, () => true, () => downs++, () => { }, _ => { },
            default, false, NavigationBaselineTiming.V3);
        try
        {
            lease.Forward(Source(990), default);
            now = 1050; lease.ReleaseForward();
            now = 1300;
            Assert.Throws<InvalidOperationException>(() => lease.Forward(Source(1149), default));
            Assert.Equal("native_source_stale", lease.Fault); Assert.Equal(1, downs);
        }
        finally { await DisposeFaulted(lease); }
    }

    /// <summary>File evidence carries the selected v3 controller identity even when the measured run failed.</summary>
    [Fact]
    public void JournalRetainsV3IdentityOnFailure()
    {
        var journal = new NavigationBaselineJournal
        {
            RunId = "09a11dc82295411891d98f2442819392", GameProcessId = 10, WindowsSessionId = 3,
            WorkflowResult = new() { TimingContract = NavigationBaselineTiming.V3, Error = "forward_lease_expired" },
            Observations = [], InputTransitions = [], ScheduleWaits = [], ObservationAttempts = [], CapturePolls = []
        };
        using var json = JsonDocument.Parse(journal.Serialize());
        Assert.Equal("v3", json.RootElement.GetProperty("timingContract").GetString());
        Assert.Equal("native-fixed-leg-feedback-v3", json.RootElement.GetProperty("controllerMethod").GetString());
        Assert.Equal("v3", json.RootElement.GetProperty("workflowResult").GetProperty("timingContract").GetString());
        Assert.False(json.RootElement.GetProperty("workflowResult").GetProperty("verified").GetBoolean());
    }
}
