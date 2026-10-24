using System.Diagnostics;
using System.Text.Json;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using Fischless.GameCapture.DesktopDc;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Host source authority and existing native windows, using only synthetic clocks and sinks.</summary>
public sealed class NavigationBaselineHostSourceTests
{
    /// <summary>Stable generation for this managed-only fixture.</summary>
    private static readonly Guid Epoch = Guid.Parse("e52c743d-cae1-4c27-8878-22423c650060");
    /// <summary>Represent exact millisecond fixture points in the platform QPC scale.</summary>
    private static long Ticks(double ms) => (long)(ms * Stopwatch.Frequency / 1000);
    /// <summary>One acquisition interval; completion never replaces the older start anchor.</summary>
    private static GameCaptureHostSnapshotInfo Host(long id = 1, double start = 1000, double end = 1010) =>
        new(Epoch, id, Ticks(start), Ticks(end), Stopwatch.Frequency);

    /// <summary>All malformed host headers fail before age-only retry can classify them.</summary>
    [Theory]
    [InlineData("epoch", "invalid_native_source")]
    [InlineData("id", "invalid_host_snapshot")]
    [InlineData("start", "invalid_host_snapshot")]
    [InlineData("end", "invalid_host_snapshot")]
    [InlineData("frequency", "invalid_source_clock")]
    [InlineData("future", "acquisition_in_future")]
    public void RejectMalformedHostHeader(string mutation, string expected)
    {
        var host = mutation switch
        {
            "epoch" => Host() with { CaptureEpoch = Guid.Empty },
            "id" => Host() with { SnapshotId = 0 },
            "start" => Host() with { StartedAtStopwatchTicks = 0 },
            "end" => Host() with { CompletedAtStopwatchTicks = Ticks(999) },
            "frequency" => Host() with { ClockFrequency = Stopwatch.Frequency + 1 },
            _ => Host(end: 1101)
        };
        var source = new CaptureSourceEvidence(host);
        Assert.Equal(expected, NavigationBaselineRecovery.HardSourceRejection(source, 1100, null));
        Assert.True(double.IsNaN(source.AgeAt(1100)));
    }

    /// <summary>Duplicate identities cannot acquire altered clocks or become a different evidence kind.</summary>
    [Theory]
    [InlineData("same-id", "host_snapshot_identity_changed")]
    [InlineData("epoch", "source_epoch_changed")]
    [InlineData("id", "native_source_regressed")]
    [InlineData("start", "native_source_regressed")]
    [InlineData("completion", "native_source_regressed")]
    [InlineData("kind", "source_kind_changed")]
    public void ImmutableIdentityAndHighWaterRemainHardFailures(string mutation, string expected)
    {
        var first = new CaptureSourceEvidence(Host(2));
        var candidate = mutation switch
        {
            "same-id" => new CaptureSourceEvidence(Host(2, 1000, 1011)),
            "epoch" => new CaptureSourceEvidence(Host(3) with { CaptureEpoch = Guid.NewGuid() }),
            "id" => new CaptureSourceEvidence(Host(1)),
            "start" => new CaptureSourceEvidence(Host(3, 999, 1010)),
            "completion" => new CaptureSourceEvidence(Host(3, 1000, 1009)),
            _ => new CaptureSourceEvidence(Epoch, 1000 * 10000L, Ticks(1000))
        };
        Assert.Equal(expected, candidate.IdentityRejection(first));
        Assert.False(candidate.StrictlyNewerThan(first));
    }

    /// <summary>Late copy/cleanup cannot make an old acquisition fresh, and 80 ms means start after the cutoff.</summary>
    [Theory]
    [InlineData(1079, 1090, false)]
    [InlineData(1080, 1090, true)]
    [InlineData(1081, 1110, true)]
    public void HostAgeAndResponseBarrierUseStart(double started, double completed, bool clearsBarrier)
    {
        var source = new CaptureSourceEvidence(Host(start: started, end: completed));
        Assert.Equal(1200 - started, NavigationBaselineTask.SourceAge(source, 1200), 6);
        Assert.Equal(clearsBarrier, NavigationBaselineTask.AfterBarrier(source, 1000, 80));
        Assert.Null(source.WgcSource);
    }

    /// <summary>Acquisition starts at the fixed input-completion cutoff, including when workflow cadence already consumed most of it.</summary>
    [Theory]
    [InlineData(60, 0)] [InlineData(60, 51)] [InlineData(80, 51)] [InlineData(80, 79)]
    public async Task HostResponseWaitPrecedesAcquisition(double responseMs, double elapsed)
    {
        double now = 1000 + elapsed; var waits = new List<double>(); var checks = 0;
        using var cancellation = new CancellationTokenSource();
        var attempt = new NavigationBaselineObservationAttempt(now);
        await NativeNavigationBaselineOperations.WaitForHostResponseAsync(1000, responseMs, attempt, () => now,
            (deadline, token) =>
            {
                Assert.Equal(cancellation.Token, token);
                waits.Add(deadline); now = deadline; return Task.CompletedTask;
            }, token => { Assert.Equal(cancellation.Token, token); checks++; }, cancellation.Token);
        var acquiredAt = now;
        Assert.Equal(1000 + responseMs, Assert.Single(waits)); Assert.Equal(1, checks);
        Assert.Equal(1000 + responseMs, acquiredAt);
        Assert.True(NavigationBaselineTask.AfterBarrier(new CaptureSourceEvidence(Host(start: acquiredAt, end: acquiredAt + 30)), 1000, responseMs));
        Assert.False(NavigationBaselineTask.AfterBarrier(new CaptureSourceEvidence(Host(start: acquiredAt - 1, end: acquiredAt + 30)), 1000, responseMs));
        // A second read does not restart the interval from its later clock.
        now += 30;
        await NativeNavigationBaselineOperations.WaitForHostResponseAsync(1000, responseMs, attempt, () => now,
            (_, _) => throw new InvalidOperationException("unexpected_second_wait"), _ => checks++, default);
        Assert.Equal(1, checks);
    }

    /// <summary>No active barrier or an already reached cutoff adds a wait or another availability call.</summary>
    [Theory]
    [InlineData(0, 1000)] [InlineData(60, 1060)] [InlineData(60, 1061)] [InlineData(80, 1080)]
    public async Task HostResponseWaitSkipsInactiveAndElapsedBarriers(double responseMs, double now)
    {
        var attempt = new NavigationBaselineObservationAttempt(now) { Stage = "checking_target" };
        await NativeNavigationBaselineOperations.WaitForHostResponseAsync(1000, responseMs, attempt, () => now,
            (_, _) => throw new InvalidOperationException("unexpected_wait"),
            _ => throw new InvalidOperationException("unexpected_postwait_check"), default);
        Assert.Equal("checking_target", attempt.Stage);
    }

    /// <summary>Both an in-wait failure and a changed condition at return prevent the acquisition callback.</summary>
    [Theory]
    [InlineData(false, false)] [InlineData(false, true)] [InlineData(true, false)] [InlineData(true, true)]
    public async Task HostResponseWaitRejectsCancellationOrTargetLoss(bool cancellation, bool duringWait)
    {
        double now = 1000; var available = true; var captures = 0;
        using var stop = new CancellationTokenSource();
        void Check(CancellationToken token)
        {
            token.ThrowIfCancellationRequested();
            if (!available) throw new InvalidOperationException("game_target_lost");
        }
        var error = await Record.ExceptionAsync(async () =>
        {
            await NativeNavigationBaselineOperations.WaitForHostResponseAsync(1000, 80, new(now), () => now,
                (deadline, token) =>
                {
                    now = duringWait ? 1040 : deadline;
                    if (cancellation) stop.Cancel(); else available = false;
                    if (duringWait) Check(token);
                    return Task.CompletedTask;
                }, Check, stop.Token);
            captures++;
        });
        if (cancellation) Assert.IsAssignableFrom<OperationCanceledException>(error);
        else Assert.Equal("game_target_lost", Assert.IsType<InvalidOperationException>(error).Message);
        Assert.Equal(0, captures);
    }

    /// <summary>The real lease check creates the pause during an oversleep; scheduling neither renews nor hides it.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public async Task HostResponseWaitPreservesWatchdogPause(bool duringWait)
    {
        double now = 1000; var downs = 0; var ups = 0; var captures = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => downs++, () => ups++, _ => { }, default, false, NavigationBaselineTiming.V4);
        lease.EnableRecovery();
        var grant = lease.Forward(new CaptureSourceEvidence(Host(start: 1000, end: 1000)), default);
        void Check(CancellationToken token)
        {
            token.ThrowIfCancellationRequested();
            if (lease.PendingRecovery is { } pause)
                throw new NavigationBaselineRecoveryRequired(pause.Cause, "between_observations", pause: pause);
        }
        var error = await Assert.ThrowsAsync<NavigationBaselineRecoveryRequired>(async () =>
        {
            await NativeNavigationBaselineOperations.WaitForHostResponseAsync(grant.CompletedAtMs, 60, new(now), () => now,
                (_, token) =>
                {
                    now = grant.ExpiresAtMs!.Value; lease.Check();
                    if (duringWait) Check(token);
                    return Task.CompletedTask;
                }, Check, default);
            captures++;
        });
        Assert.Equal(1150, grant.ExpiresAtMs); Assert.Equal(NavigationBaselineRecoveryCause.LeaseExpired, error.Cause);
        Assert.Same(lease.PendingRecovery, error.Pause); Assert.Equal("between_observations", error.Stage);
        Assert.Equal(0, captures); Assert.Equal(1, downs); Assert.Equal(1, ups); Assert.False(lease.ForwardHeld);
    }

    /// <summary>An eligible acquisition followed by slow recognition still expires the unchanged 150 ms grant.</summary>
    [Fact]
    public async Task EligibleHostCaptureDoesNotGuaranteeRecognitionFitsTheLease()
    {
        double now = 1000; var ups = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => { }, () => ups++, _ => { }, default, false, NavigationBaselineTiming.V4);
        lease.EnableRecovery();
        var grant = lease.Forward(new CaptureSourceEvidence(Host(start: now, end: now)), default);
        await NativeNavigationBaselineOperations.WaitForHostResponseAsync(grant.CompletedAtMs, 60, new(now), () => now,
            (deadline, _) => { now = deadline; return Task.CompletedTask; }, _ => Assert.Null(lease.PendingRecovery), default);
        var source = new CaptureSourceEvidence(Host(2, now, now + 57));
        now += 57 + 34; lease.Check();
        Assert.True(NavigationBaselineTask.AfterBarrier(source, grant.CompletedAtMs, 60));
        Assert.Equal(91, source.AgeAt(now), 6); Assert.Equal(1150, grant.ExpiresAtMs);
        Assert.Equal(NavigationBaselineRecoveryCause.LeaseExpired, Assert.IsType<NavigationBaselineRecoveryPause>(lease.PendingRecovery).Cause);
        Assert.Throws<NavigationBaselineRecoveryRequired>(() => lease.Forward(source, default));
        Assert.Equal(1, ups); Assert.False(lease.ForwardHeld);
    }

    /// <summary>A held renewal creates no new response barrier; the existing physical-down cutoff is already elapsed.</summary>
    [Fact]
    public async Task HostRenewalDoesNotRestartResponseWait()
    {
        double now = 1000;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => { }, () => { }, _ => { }, default, false, NavigationBaselineTiming.V4);
        var down = lease.Forward(new CaptureSourceEvidence(Host(start: now, end: now)), default);
        now = 1065;
        var renewal = lease.Forward(new CaptureSourceEvidence(Host(2, now, now)), default);
        Assert.Equal("renew_w", renewal.Kind);
        await NativeNavigationBaselineOperations.WaitForHostResponseAsync(down.CompletedAtMs, 60, new(now), () => now,
            (_, _) => throw new InvalidOperationException("renewal_restarted_response_wait"), _ => { }, default);
        Assert.Equal(1065, now); Assert.Equal(1165, renewal.ExpiresAtMs);
    }

    /// <summary>Keep all raw WGC property names and values byte-for-byte under both serializer policies.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void HistoricalWgcSerializationIsUnchanged(bool camelCase)
    {
        var raw = new GameCaptureSourceInfo(Epoch, 123456789, Ticks(1000));
        var options = new JsonSerializerOptions { PropertyNamingPolicy = camelCase ? JsonNamingPolicy.CamelCase : null };
        Assert.Equal(JsonSerializer.SerializeToUtf8Bytes(raw, options),
            JsonSerializer.SerializeToUtf8Bytes(new CaptureSourceEvidence(raw), options));
    }

    /// <summary>Host wire evidence names the interval and cannot masquerade as a compositor timestamp.</summary>
    [Fact]
    public void HostSerializationHasExplicitKindAndNoWgcClocks()
    {
        using var document = JsonDocument.Parse(JsonSerializer.Serialize(new CaptureSourceEvidence(Host())));
        var root = document.RootElement;
        Assert.Equal("host-acquisition-v1", root.GetProperty("kind").GetString());
        Assert.Equal(1, root.GetProperty("hostSnapshot").GetProperty("SnapshotId").GetInt64());
        Assert.False(root.TryGetProperty("SourceTimestamp100ns", out _));
        Assert.False(root.TryGetProperty("AcquiredAtStopwatchTicks", out _));
    }

    /// <summary>The original 250 ms source horizon constrains a host first grant, with unchanged expiry release.</summary>
    [Fact]
    public async Task HostGrantUsesStartHorizonAndNeverRenewsAfterExpiry()
    {
        double now = 1000; var down = 0; var up = 0;
        await using var lease = new NavigationBaselineInputLease(() => now, () => true,
            () => down++, () => up++, _ => { }, default, false, NavigationBaselineTiming.V4);
        lease.EnableRecovery();
        var first = lease.Forward(new CaptureSourceEvidence(Host(start: 900, end: 990)), default);
        Assert.Equal(1150, first.ExpiresAtMs);
        now = 1150;
        Assert.Throws<NavigationBaselineRecoveryRequired>(() =>
            lease.Forward(new CaptureSourceEvidence(Host(2, 1140, 1145)), default));
        Assert.Equal(1, down); Assert.Equal(1, up); Assert.False(lease.ForwardHeld);
    }

    /// <summary>Initial age discard retains the host header floor and fixed original owner deadline.</summary>
    [Fact]
    public void InitialWindowRetriesOnlyAgeWithoutResettingHeaderOrDeadline()
    {
        double now = 1200;
        var window = new NavigationBaselineInitialReadiness(() => now, 3000, 0, 0, NavigationBaselineCapturePolicy.TaskOwnedTimer);
        var old = new CaptureSourceEvidence(Host(start: 1000, end: 1190));
        window.ValidateHeader(old, 1920, 1080, 3, default);
        Assert.Throws<NavigationBaselineInitialReadiness.SourceAgeException>(() =>
            window.ValidateSource(old, "after_capture", 0, 0, default));
        Assert.Same(old, window.SeenSource); Assert.Equal(3000, window.Record.DeadlineAtMs);
        Assert.Equal("source_age_discard", Assert.Single(window.Record.SourceChecks).Disposition);
        var fresh = new CaptureSourceEvidence(Host(2, 1190, 1195));
        window.ValidateHeader(fresh, 1920, 1080, 3, default);
        Assert.Equal(fresh, window.ValidateSource(fresh, "after_capture", 1, 1, default));
        Assert.Equal(3000, window.Record.DeadlineAtMs);
    }

    /// <summary>Keep the endpoint's three distinct intervals, spacing, and confidence gates for host snapshots.</summary>
    [Theory]
    [InlineData("valid", null)]
    [InlineData("duplicate", "source_not_increasing")]
    [InlineData("spacing", "acquisition_spacing_too_short")]
    [InlineData("mixed", "invalid_native_source")]
    public void HostFinalClusterUsesRealIntervals(string mutation, string? expected)
    {
        var samples = new[] { Pose(2, 2000), Pose(3, 2100), Pose(4, 2200) };
        if (mutation == "duplicate") samples[1] = samples[1] with { HostSnapshot = samples[0].HostSnapshot };
        if (mutation == "spacing") samples[1] = Pose(3, 2079);
        if (mutation == "mixed") samples[1] = samples[1] with { SourceTimestamp100ns = 1 };
        Assert.Equal(expected, NavigationBaselineTask.FinalRejection(samples));
    }

    /// <summary>Successful callback evidence cannot substitute an unselected source policy or old WGC shape.</summary>
    [Theory]
    [InlineData("valid", true)]
    [InlineData("unselected", false)]
    [InlineData("evidence-policy", false)]
    [InlineData("mixed-initial", false)]
    [InlineData("legacy-timing", false)]
    [InlineData("other-route", false)]
    public void OwnerRequiresExactSelectedHostAuthority(string mutation, bool accepted)
    {
        var result = Result();
        result = mutation switch
        {
            "unselected" => result with { SourcePolicy = null },
            "evidence-policy" => result with { Evidence = result.Evidence! with { SourcePolicy = null } },
            "mixed-initial" => result with { InitialSample = result.InitialSample! with { AcquiredAtStopwatchTicks = 1 } },
            "legacy-timing" => result with { TimingContract = "v3" },
            "other-route" => result with { ProfileId = NavigationBaselineRouteProfile.TwoLegId },
            _ => result
        };
        Assert.Equal(accepted, NavigationBaselineTaskOwner.VerifiedResult(result));
    }

    /// <summary>The dedicated host result keeps its raw interval without widening the ordinary or result envelope.</summary>
    [Fact]
    public void HostResultHasExplicitPolicyAndBoundedWireShape()
    {
        var status = new NavigationBaselineStatus { SourcePolicy = DesktopCapturePolicy.HostAcquisitionV1,
            TimingContract = "v4", CapturePolicy = NavigationBaselineCapturePolicy.TaskOwnedTimer,
            State = "completed", Result = Result() };
        var complete = CaptureOptionsCommandTests.CompleteEnvelope(new() { NavigationBaseline = status }, "poll_single_v1");
        var response = new ExternalControlResponse { Status = complete with { CaptureMode = "DesktopDc",
            EffectiveReadbackMode = null, EffectiveSourceRetention = null, EffectiveConversion = null,
            EffectiveDesktopDcSourcePolicy = "host-acquisition-v1",
            NavigationReset = complete.NavigationReset with { SourcePolicy = "host-acquisition-v1", ReadbackMode = null,
                Samples = complete.NavigationReset.Samples.Select((sample, index) => sample with {
                    SourceEpoch = Epoch, SourceTimestamp100ns = null, AcquiredAtStopwatchTicks = null,
                    HostSnapshot = Host(index + 1, 1000 + index * 100, 1010 + index * 100) }).ToArray() } } };
        var full = ExternalControlProtocol.SerializeResponse(response);
        Assert.InRange(full.Length, 1, 32767);
        using var parsed = JsonDocument.Parse(full);
        var initial = parsed.RootElement.GetProperty("status").GetProperty("navigationBaseline")
            .GetProperty("result").GetProperty("initialSample");
        Assert.True(initial.TryGetProperty("hostSnapshot", out _));
        Assert.False(initial.TryGetProperty("sourceTimestamp100ns", out _));
        Assert.False(initial.TryGetProperty("acquiredAtStopwatchTicks", out _));
        var compact = ExternalControlProtocol.SerializeResponse(response with
            { Status = response.Status! with { NavigationBaseline = status with { Result = null } } });
        Assert.InRange(compact.Length, 1, 8191);
    }

    /// <summary>Host predecessor metadata remains a rejection floor; identity failures cannot become age-only retries.</summary>
    [Theory]
    [InlineData("valid-gap", null, null)]
    [InlineData("epoch", "source_epoch_changed", null)]
    [InlineData("frequency", "invalid_source_clock", null)]
    [InlineData("kind", "source_kind_changed", null)]
    [InlineData("id-regressed", "native_source_regressed", null)]
    [InlineData("id-reused-changed", "host_snapshot_identity_changed", null)]
    [InlineData("identical", null, "continuation_source_not_newer")]
    [InlineData("equal-start", null, "continuation_source_not_newer")]
    [InlineData("equal-end", null, "continuation_source_not_newer")]
    [InlineData("start-regressed", "native_source_regressed", null)]
    [InlineData("end-regressed", "native_source_regressed", null)]
    [InlineData("invalid-interval", "invalid_host_snapshot", null)]
    [InlineData("future", "acquisition_in_future", null)]
    public void HostContinuationFloorDoesNotRenewOrReplaceSource(string mutation, string? hard, string? startError)
    {
        var link = HostLink(); var floor = link.PredecessorFinalSource;
        var current = mutation switch
        {
            "epoch" => Host(9, 1090, 1100) with { CaptureEpoch = Guid.NewGuid() },
            "frequency" => Host(9, 1090, 1100) with { ClockFrequency = Stopwatch.Frequency + 1 },
            "id-regressed" => Host(1, 1090, 1100),
            "id-reused-changed" => Host(2, 1090, 1100),
            "identical" => floor.HostSnapshot!,
            "equal-start" => Host(9, 1000, 1100),
            "equal-end" => Host(9, 1005, 1010),
            "start-regressed" => Host(9, 999, 1100),
            "end-regressed" => Host(9, 1001, 1009),
            "invalid-interval" => Host(9, 1100, 1090),
            "future" => Host(9, 1190, 1201),
            _ => Host(9, 1090, 1100)
        };
        var observed = mutation == "kind" ? new CaptureSourceEvidence(Epoch, 10900000, Ticks(1090)) : new CaptureSourceEvidence(current);
        if (hard is not null)
            Assert.Equal(hard, Assert.Throws<InvalidOperationException>(() =>
                NavigationBaselineEndpointContinuation.ValidateObservedSource(link, observed, 1200)).Message);
        else
        {
            NavigationBaselineEndpointContinuation.ValidateObservedSource(link, observed, 1200);
            var pose = Pose(9, 1090) with { HostSnapshot = current, SourceEpoch = current.CaptureEpoch, LegIndex = 1 };
            Assert.Equal(startError, NavigationBaselineEndpointContinuation.StartRejection(link, pose, NavigationBaselineRouteProfile.CourtyardReturn));
        }
        Assert.Same(floor, link.PredecessorFinalSource); Assert.Equal(2, floor.HostSnapshot!.SnapshotId);
    }

    /// <summary>The existing start radius and150ms source-age contract are not widened for a continuation.</summary>
    [Theory]
    [InlineData(1.5, 150, null)]
    [InlineData(1.5001, 150, "start_not_at_anchor")]
    [InlineData(1.5, 150.0001, "native_source_stale")]
    public void HostContinuationKeepsStartDistanceAndFreshness(double offset, double age, string? expected)
    {
        var pose = Pose(9, 1090) with { X = NavigationBaselineTask.EndX + offset, SourceAgeMs = age, LegIndex = 1 };
        Assert.Equal(expected, NavigationBaselineEndpointContinuation.StartRejection(HostLink(), pose,
            NavigationBaselineRouteProfile.CourtyardReturn));
    }

    /// <summary>Full host links require the exact typed source, assembly, backend, policy and predecessor evidence.</summary>
    [Theory]
    [InlineData("valid", true)][InlineData("build-short", false)][InlineData("build-nonhex", false)]
    [InlineData("policy", false)][InlineData("readback", false)][InlineData("capture", false)]
    [InlineData("evidence-policy", false)][InlineData("evidence-readback", false)][InlineData("wgc-source", false)]
    public void FullHostLinkContractCannotMixAuthority(string mutation, bool expected)
    {
        var link = HostLink();
        link = mutation switch
        {
            "build-short" => link with { ChildAssemblySha256 = "a" },
            "build-nonhex" => link with { ChildAssemblySha256 = new string('g', 64) },
            "policy" => link with { SourcePolicy = DesktopCapturePolicy.ObserveOnly },
            "readback" => link with { ReadbackMode = "blocking" },
            "capture" => link with { CaptureType = "Fischless.GameCapture.Graphics.GraphicsCaptureV2" },
            "evidence-policy" => link with { PredecessorEvidence = link.PredecessorEvidence with { SourcePolicy = null } },
            "evidence-readback" => link with { PredecessorEvidence = link.PredecessorEvidence with { ReadbackMode = "poll_single_v1" } },
            "wgc-source" => link with { PredecessorFinalSource = new(Epoch, 10000000, Ticks(1000)) },
            _ => link
        };
        Assert.Equal(expected, link.HasHostSourceContract);
    }

    /// <summary>Only explicit shipped seed/return/forward profiles opt into typed host continuation.</summary>
    [Theory]
    [InlineData(NavigationBaselineTask.ProfileId, true)]
    [InlineData(NavigationBaselineRouteProfile.CourtyardReturnId, true)]
    [InlineData(NavigationBaselineRouteProfile.CourtyardForwardId, true)]
    [InlineData(NavigationBaselineRouteProfile.TwoLegId, false)]
    [InlineData(NavigationBaselineRouteProfile.ReverseId, false)]
    public void HostSupportUsesExplicitProfiles(string id, bool expected) =>
        Assert.Equal(expected, NavigationBaselineRouteProfile.Resolve(id, "v4", "task_owned_timer").SupportsHostContinuation);

    /// <summary>Synthetic fixed host floor with a complete bounded predecessor proof and no native owner.</summary>
    internal static NavigationBaselineContinuationLink HostLink() => new()
    {
        PredecessorRunId = new string('a', 32), PredecessorProfileId = NavigationBaselineTask.ProfileId,
        PredecessorEvidence = new(true, new string('j', 1024), new string('a', 64), new string('i', 1024),
            new string('b', 64), new string('f', 1024), new string('c', 64)) { SourcePolicy = DesktopCapturePolicy.HostAcquisitionV1 },
        PredecessorFinalSource = new(Host(2, 1000, 1010)), PredecessorCleanupReturnedAtTicks = Ticks(1050),
        RuntimeIdentity = Guid.Parse("11111111-2222-3333-4444-555555555555"), ChildProcessId = 20,
        ChildNonce = new string('b', 32), WindowsSessionId = 3, GameProcessId = 10, GameStartedAtUtcTicks = 1,
        CaptureType = typeof(DesktopDcCapture).FullName!, ReadbackMode = null,
        SourcePolicy = DesktopCapturePolicy.HostAcquisitionV1, ChildAssemblySha256 = new string('a', 64)
    };

    /// <summary>Synthetic same-frame endpoint evidence with no image/native execution.</summary>
    private static NavigationBaselineSample Pose(long id, double start, bool initial = false)
    {
        var x = initial ? NavigationBaselineTask.StartX : NavigationBaselineTask.EndX;
        var y = initial ? NavigationBaselineTask.StartY : NavigationBaselineTask.EndY;
        var geometry = NavigationBaselineTask.Geometry(x, y);
        return new(x, y, 45, DateTimeOffset.UnixEpoch, Epoch, null, null, 1, 1, "City_102",
            new("normal", "native_key_tip_templates_v1", false, false, 1), 30, 45,
            geometry.Distance, geometry.Projection, geometry.CrossTrack, new(start, start, start + 10, start + 30))
            { HostSnapshot = Host(id, start, start + 10) };
    }

    /// <summary>Exact ordinary-short proof used to exercise owner acceptance without dispatch.</summary>
    private static NavigationBaselineRunResult Result()
    {
        var final = new[] { Pose(2, 2000), Pose(3, 2100), Pose(4, 2200) };
        return new() { SourcePolicy = DesktopCapturePolicy.HostAcquisitionV1, TimingContract = "v4",
            CapturePolicy = NavigationBaselineCapturePolicy.TaskOwnedTimer, Verified = true, ObservationCount = 4,
            ElapsedMs = 1500, InitialSample = Pose(1, 1000, true), Samples = final, VerificationSamples = final,
            Evidence = new(true, new string('j', 1024), new string('A', 64), new string('i', 1024), new string('B', 64),
                new string('f', 1024), new string('C', 64)) { SourcePolicy = DesktopCapturePolicy.HostAcquisitionV1 } };
    }
}
