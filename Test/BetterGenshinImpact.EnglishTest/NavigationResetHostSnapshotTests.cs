using System.Diagnostics;
using System.Text.Json;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.GameTask.NavigationReset;
using BetterGenshinImpact.GameTask.SoloTask.Execution;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Host reset metadata and fake workflow checks; no capture, input, timer, or model is started.</summary>
public sealed class NavigationResetHostSnapshotTests
{
    /// <summary>Positive deterministic QPC epoch used by all synthetic acquisitions.</summary>
    private static readonly long _origin = Stopwatch.Frequency * 10;
    /// <summary>Convert exact fixture millisecond offsets into the actual QPC unit.</summary>
    private static long Ticks(int milliseconds) => _origin + Stopwatch.Frequency * milliseconds / 1000;
    /// <summary>A real-format host interval contains no WGC render timestamp.</summary>
    private static GameCaptureHostSnapshotInfo Host(Guid epoch, long id = 1, int start = 0, int end = 10) =>
        new(epoch, id, Ticks(start), Ticks(end), Stopwatch.Frequency);
    /// <summary>Fresh high-confidence fixed-spawn pose with an explicitly tagged host snapshot.</summary>
    private static NavigationResetSample Sample(GameCaptureHostSnapshotInfo host) => new(
        NavigationResetTask.SpawnX, NavigationResetTask.SpawnY, 0, DateTimeOffset.UnixEpoch,
        host.CaptureEpoch, null, null, 1, 1, "City_102", HostSnapshot: host);
    /// <summary>Legacy fixture uses the same epoch and actual WGC clock units, without host metadata.</summary>
    private static NavigationResetSample Wgc(Guid epoch, int start = 0) => new(
        NavigationResetTask.SpawnX, NavigationResetTask.SpawnY, 0, DateTimeOffset.UnixEpoch,
        epoch, 100_000_000L + start * 10_000L, Ticks(start), 1, 1, "City_102");

    /// <summary>Reset keeps its500ms bound, anchored to capture start even when copying completes much later.</summary>
    [Theory]
    [InlineData(499, 490, true)]
    [InlineData(500, 500, true)]
    [InlineData(501, 500, false)]
    [InlineData(700, 690, false)]
    public void HostFreshnessUsesStartAndUnchangedBound(int now, int completion, bool expected)
    {
        var source = new CaptureSourceEvidence(Host(Guid.NewGuid(), end: completion));
        Assert.Equal(expected, NativeNavigationResetOperations.SourceIsFresh(source, Ticks(now)));
    }

    /// <summary>Header/epoch corruption is not converted into an age-only retry.</summary>
    [Theory]
    [InlineData("frequency", "invalid_source_clock")]
    [InlineData("id", "invalid_host_snapshot")]
    [InlineData("start", "invalid_host_snapshot")]
    [InlineData("inverted", "invalid_host_snapshot")]
    [InlineData("future", "acquisition_in_future")]
    [InlineData("epoch", "source_epoch_changed")]
    public void MalformedHostNeverGetsAnAgeRefund(string fault, string expected)
    {
        var epoch = Guid.NewGuid(); var host = Host(epoch);
        host = fault switch
        {
            "frequency" => host with { ClockFrequency = Stopwatch.Frequency + 1 },
            "id" => host with { SnapshotId = 0 },
            "start" => host with { StartedAtStopwatchTicks = 0 },
            "inverted" => host with { CompletedAtStopwatchTicks = host.StartedAtStopwatchTicks - 1 },
            "future" => host with { CompletedAtStopwatchTicks = Ticks(1001) },
            "epoch" => host with { CaptureEpoch = Guid.NewGuid() },
            _ => throw new InvalidOperationException()
        };
        var evidence = new CaptureSourceEvidence(host);
        Assert.Equal(expected, NativeNavigationResetOperations.SourceRejectionReason(evidence, Ticks(1000), epoch));
        Assert.Null(NativeNavigationResetOperations.PoseSourceRetryReason(evidence, Ticks(1000), epoch, "after_capture"));
    }

    /// <summary>Only the two existing pose source-check stages can retry a valid old host acquisition.</summary>
    [Theory]
    [InlineData("after_capture", true)]
    [InlineData("after_recognition", true)]
    [InlineData("before_input", false)]
    public void HostAgeRetryUsesOnlyExistingStages(string stage, bool expected)
    {
        var epoch = Guid.NewGuid(); var source = new CaptureSourceEvidence(Host(epoch));
        var result = NativeNavigationResetOperations.PoseSourceRetryReason(source, Ticks(600), epoch, stage);
        Assert.Equal(expected, result is not null);
        if (expected) Assert.Contains("source=host-snapshot:1", result);
    }

    /// <summary>Changed/regressing host identity takes precedence over otherwise retryable source age.</summary>
    [Theory]
    [InlineData("same_id", "host_snapshot_identity_changed")]
    [InlineData("regressed_id", "native_source_regressed")]
    [InlineData("regressed_start", "native_source_regressed")]
    [InlineData("kind", "source_kind_changed")]
    public void PreparationAndPoseAgeCannotHideIdentityLoss(string fault, string expected)
    {
        var epoch = Guid.NewGuid(); var old = Host(epoch, 2, 100, 110);
        var changed = fault switch
        {
            "same_id" => old with { CompletedAtStopwatchTicks = Ticks(111) },
            "regressed_id" => Host(epoch, 1, 120, 130),
            "regressed_start" => Host(epoch, 3, 90, 130),
            _ => Host(epoch, 3, 120, 130)
        };
        CaptureSourceEvidence previous = fault == "kind" ? Wgc(epoch).Evidence! : new(old);
        var current = new CaptureSourceEvidence(changed);
        Assert.Equal(expected, NativeNavigationResetOperations.PreparationSourceRejectionReason(current, Ticks(800), epoch, previous));
        Assert.Null(NativeNavigationResetOperations.PoseSourceRetryReason(current, Ticks(800), epoch, "after_capture", previous));
    }

    /// <summary>Host geometry changes stay hard failures even when the source is stale.</summary>
    [Fact]
    public void StaleHostGeometryDoesNotEarnPreparationRetry()
    {
        var epoch = Guid.NewGuid(); var source = new CaptureSourceEvidence(Host(epoch));
        Assert.Equal("preparation_frame_geometry_changed", NativeNavigationResetOperations.PreparationFrameRejectionReason(
            source, Ticks(600), epoch, null, (1280, 720, MatType.CV_8UC4), (1920, 1080, MatType.CV_8UC4)));
    }

    /// <summary>A late completion cannot move an acquisition begun before the80ms response cutoff across it.</summary>
    [Theory]
    [InlineData(79, 150, false)]
    [InlineData(80, 150, true)]
    [InlineData(81, 81, true)]
    public void HostInputBarrierUsesIntervalStart(int start, int completion, bool expected)
    {
        Assert.Equal(expected, NativeNavigationResetOperations.SourceIsAfterBarrier(
            new CaptureSourceEvidence(Host(Guid.NewGuid(), start: start, end: completion)), _origin));
    }

    /// <summary>Three distinct spaced host acquisitions are accepted without pretending their rendered contents differ.</summary>
    [Fact]
    public void OrderedHostSequenceUsesStartSpacing()
    {
        var epoch = Guid.NewGuid();
        var samples = Enumerable.Range(0, 3).Select(i => Sample(Host(epoch, i + 1, i * 120, i * 120 + 10))).ToArray();
        Assert.True(NavigationResetTask.AcceptSamples(samples, 0));
        samples[1] = Sample(Host(epoch, 2, 79, 130));
        Assert.Equal("acquisition_spacing_too_short", NavigationResetTask.SamplesRejectionReason(samples, 0));
    }

    /// <summary>Cached identities, mutations and mixed kinds never form a settled host verification sequence.</summary>
    [Theory]
    [InlineData("duplicate", "source_not_increasing")]
    [InlineData("mutation", "host_snapshot_identity_changed")]
    [InlineData("kind", "source_kind_changed")]
    [InlineData("epoch", "source_epoch_changed")]
    public void HostVerificationRejectsFalseAdvance(string fault, string expected)
    {
        var epoch = Guid.NewGuid(); var first = Sample(Host(epoch));
        var second = fault switch
        {
            "duplicate" => first,
            "mutation" => Sample(first.HostSnapshot! with { CompletedAtStopwatchTicks = Ticks(20) }),
            "kind" => Wgc(epoch, 120),
            _ => Sample(Host(Guid.NewGuid(), 2, 120, 130))
        };
        Assert.Equal(expected, NavigationResetTask.SamplesRejectionReason([first, second, Sample(Host(epoch, 3, 240, 250))], 0));
    }

    /// <summary>The host result explicitly omits WGC clocks, while old WGC serialization retains its exact original members.</summary>
    [Fact]
    public void ResultWireKeepsEvidenceKindsDistinct()
    {
        var epoch = Guid.NewGuid();
        using var host = JsonDocument.Parse(JsonSerializer.Serialize(Sample(Host(epoch))));
        Assert.Equal("host-acquisition-v1", host.RootElement.GetProperty("sourceKind").GetString());
        Assert.True(host.RootElement.TryGetProperty("hostSnapshot", out _));
        Assert.False(host.RootElement.TryGetProperty("sourceTimestamp100ns", out _));
        Assert.False(host.RootElement.TryGetProperty("acquiredAtStopwatchTicks", out _));
        using var wgc = JsonDocument.Parse(JsonSerializer.Serialize(Wgc(epoch)));
        Assert.Equal(10, wgc.RootElement.EnumerateObject().Count());
        Assert.Equal(100_000_000L, wgc.RootElement.GetProperty("sourceTimestamp100ns").GetInt64());
        Assert.Equal(_origin, wgc.RootElement.GetProperty("acquiredAtStopwatchTicks").GetInt64());
        Assert.False(wgc.RootElement.TryGetProperty("sourceKind", out _));
        Assert.False(wgc.RootElement.TryGetProperty("hostSnapshot", out _));
        Assert.False(NavigationResetTask.IsValidPose(Sample(Host(epoch)) with { SourceTimestamp100ns = 1 }));
    }

    /// <summary>Log-only host metadata keeps the raw WGC field null and cannot be mistaken for a returned source.</summary>
    [Fact]
    public void HostDiagnosticsUseSeparateVersionedMetadata()
    {
        var host = Host(Guid.NewGuid());
        var record = new NavigationResetSourceDiagnostic
            { Reason = "source_age_exceeds_500ms", Stage = "after_capture", ObservedHostSnapshot = host };
        var json = Newtonsoft.Json.Linq.JObject.Parse(Newtonsoft.Json.JsonConvert.SerializeObject(record));
        Assert.Equal(4, (int)json["Version"]!);
        Assert.Equal(Newtonsoft.Json.Linq.JTokenType.Null, json["ObservedSource"]!.Type);
        Assert.Equal(1, (long)json["ObservedHostSnapshot"]!["SnapshotId"]!);
        Assert.Null(new NavigationResetPoseProbeDiagnostic { HostSnapshot = host }.Source);
        Assert.Equal(host, new NavigationResetPoseProbeDiagnostic { HostSnapshot = host }.Evidence!.HostSnapshot);
    }

    /// <summary>Map closing remains one fake key dispatch/release and requires a distinct post-release host acquisition.</summary>
    [Fact]
    public void HostMapRecoveryRetainsOneShotAndResponseBarrier()
    {
        var epoch = Guid.NewGuid(); var trigger = Host(epoch, start: -100, end: -90);
        var recovery = new NavigationResetMapRecovery(); var calls = new List<string>();
        recovery.CloseOnce(new(trigger), _origin, () => calls.Add("target"), () => calls.Add("press"),
            () => calls.Add("release"), CancellationToken.None, () => _origin);
        Assert.Equal(new[] { "target", "press", "release" }, calls);
        Assert.Null(recovery.TriggerSource); Assert.Equal(trigger, recovery.TriggerHostSnapshot);
        Assert.False(recovery.SourcePassedRelease(new(trigger)));
        Assert.False(recovery.SourcePassedRelease(new(Host(epoch, 2, 79, 120))));
        Assert.True(recovery.SourcePassedRelease(new(Host(epoch, 2, 80, 120))));
        Assert.Throws<InvalidOperationException>(() => recovery.CloseOnce(new(trigger), _origin, () => { },
            () => calls.Add("again"), () => { }, CancellationToken.None, () => _origin));
        Assert.Equal(3, calls.Count);
    }

    /// <summary>Rejected mixed-kind windows retain their diagnostic reason rather than throwing from gap calculation.</summary>
    [Fact]
    public async Task MixedKindWorkflowRetainsFailureAndCleanup()
    {
        var epoch = Guid.NewGuid();
        var operations = new FakeOperations(i => i % 2 == 0
            ? Sample(Host(epoch, i + 1, i * 120, i * 120 + 10)) : Wgc(epoch, i * 120));
        var task = new NavigationResetTask(operations);
        var failure = await Assert.ThrowsAsync<InvalidOperationException>(() => task.RunAsync(0, _ => { }, CancellationToken.None));
        Assert.Equal("pose_not_settled", failure.Message);
        Assert.Equal(15, task.VerificationDiagnostics.Length);
        Assert.Equal("source_kind_changed", task.VerificationDiagnostics[^1].Reason);
        Assert.Null(task.VerificationDiagnostics[^1].MinimumAcquisitionGapMs);
        Assert.Equal(1, operations.Releases);
    }

    /// <summary>The owner accepts only sample kinds matching its immutable startup policy.</summary>
    [Theory]
    [InlineData(null, false, "completed")]
    [InlineData(null, true, "failed")]
    [InlineData(DesktopCapturePolicy.HostAcquisitionV1, true, "completed")]
    [InlineData(DesktopCapturePolicy.HostAcquisitionV1, false, "failed")]
    public async Task OwnerJoinsSuccessfulSamplesToSelectedPolicy(string? policy, bool host, string expected)
    {
        var epoch = Guid.NewGuid(); var owner = new NavigationResetTaskOwner();
        var samples = Enumerable.Range(0, 3).Select(i => host
            ? Sample(Host(epoch, i + 1, i * 120, i * 120 + 10)) : Wgc(epoch, i * 120)).ToArray();
        Assert.True(owner.TryStart(0, 1, 3, (_, _) => Completed(samples), sourcePolicy: policy));
        await WaitForIdle(owner);
        var status = owner.Snapshot();
        Assert.Equal(expected, status.State); Assert.Equal(policy, status.SourcePolicy);
        Assert.Equal(expected == "completed" ? 3 : 0, status.Samples.Length);
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(status));
        Assert.Equal(policy is not null, json.RootElement.TryGetProperty("sourcePolicy", out _));
    }

    /// <summary>A preparation failure with no sample still records the exact requested host authority.</summary>
    [Fact]
    public async Task EmptyFailureRetainsHostPolicy()
    {
        var owner = new NavigationResetTaskOwner();
        Assert.True(owner.TryStart(0, 1, 3, (_, _) => Task.FromResult<(SoloTaskRunResult,
            NavigationResetSample[]?, NavigationResetVerificationDiagnostic[])>((new()
            { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = "preparation_readiness_timeout" }, null, [])),
            sourcePolicy: DesktopCapturePolicy.HostAcquisitionV1));
        await WaitForIdle(owner);
        var status = owner.Snapshot();
        Assert.Equal("failed", status.State); Assert.Empty(status.Samples);
        Assert.Equal(DesktopCapturePolicy.HostAcquisitionV1, status.SourcePolicy);
        Assert.Equal("preparation_readiness_timeout", status.Error);
    }

    /// <summary>Unsupported or observation-only authority fails before the synthetic executor can start.</summary>
    [Theory]
    [InlineData(DesktopCapturePolicy.ObserveOnly)]
    [InlineData("unknown")]
    public void OwnerRejectsPolicyBeforeDispatch(string policy)
    {
        var owner = new NavigationResetTaskOwner(); var dispatched = false;
        Assert.Throws<ArgumentException>(() => owner.TryStart(0, 1, 3, (_, _) =>
        { dispatched = true; return Completed([]); }, sourcePolicy: policy));
        Assert.False(dispatched); Assert.Equal("idle", owner.Snapshot().State);
    }

    /// <summary>Successful fake task completion has no native/controller side effects.</summary>
    private static Task<(SoloTaskRunResult, NavigationResetSample[]?, NavigationResetVerificationDiagnostic[])>
        Completed(NavigationResetSample[] samples) => Task.FromResult<(SoloTaskRunResult,
            NavigationResetSample[]?, NavigationResetVerificationDiagnostic[])>((new()
            { Outcome = SoloTaskRunOutcome.Completed }, samples, []));

    /// <summary>Bound only the managed synthetic owner task; no SDK or native capture is involved.</summary>
    private static async Task WaitForIdle(NavigationResetTaskOwner owner)
    {
        using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        while (owner.Running) await Task.Delay(1, stop.Token);
    }

    /// <summary>Pure fake workflow boundary; all captures, waits and controls are inert.</summary>
    private sealed class FakeOperations(Func<int, NavigationResetSample> sample) : INavigationResetOperations
    {
        /// <summary>Next synthetic observation.</summary>
        private int _index;
        /// <summary>Observed workflow cleanup count.</summary>
        internal int Releases { get; private set; }
        /// <inheritdoc />
        public Task PrepareAsync(CancellationToken ct) => Task.CompletedTask;
        /// <inheritdoc />
        public Task TeleportAsync(CancellationToken ct) => Task.CompletedTask;
        /// <inheritdoc />
        public Task<bool> RotateAsync(double yaw, CancellationToken ct) => Task.FromResult(true);
        /// <inheritdoc />
        public Task<NavigationResetSample> ReadPoseAsync(CancellationToken ct) => Task.FromResult(sample(_index++));
        /// <inheritdoc />
        public Task DelayAsync(int milliseconds, CancellationToken ct) => Task.CompletedTask;
        /// <inheritdoc />
        public void ReleaseInput() => Releases++;
    }
}
