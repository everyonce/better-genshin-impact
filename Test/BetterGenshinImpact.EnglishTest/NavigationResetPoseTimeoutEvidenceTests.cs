using BetterGenshinImpact.GameTask.NavigationReset;
using Fischless.GameCapture;
using Newtonsoft.Json;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Bounded timeout metadata and the actual unchanged acquisition loop, without native capture/model/input.</summary>
public sealed class NavigationResetPoseTimeoutEvidenceTests
{
    /// <summary>Every existing transient reason retains the last fully returned probe at the unchanged attempt limit.</summary>
    [Theory]
    [InlineData("pose_source_stale; stage=after_capture; source=100", "after_capture")]
    [InlineData("pose_source_stale; stage=after_recognition; source=100", "after_recognition")]
    [InlineData("readback_pending", "capture")]
    [InlineData("awaiting_new_source; source=100", "after_capture")]
    [InlineData("world_not_ready; evidence=HudMissing; source=100", "world_recognition")]
    [InlineData("yaw_unrecognized; source=100", "yaw_recognition")]
    [InlineData("local_position_unrecognized; source=100", "position_recognition")]
    public async Task CountExhaustionRetainsEveryRetryCategory(string reason, string stage)
    {
        var evidence = new NavigationResetPoseTimeoutEvidence(1);
        var calls = 0; var waits = 0;
        var failure = await Assert.ThrowsAsync<TimeoutException>(() => NavigationResetPoseAcquisition.ReadAsync(
            _ =>
            {
                var row = evidence.Begin(++calls, calls * 10);
                row.Stage = stage;
                if (reason == "readback_pending") row.PendingReadback = GameCaptureReadbackConsumerTests.Pending();
                else row.Source = new GameCaptureSourceInfo(Guid.NewGuid(), 100, 101);
                var result = new NavigationResetPoseProbe(null, reason);
                evidence.Complete(result, calls * 10 + 1);
                return Task.FromResult(result);
            }, (ms, _) => { Assert.Equal(120, ms); waits++; return Task.CompletedTask; }, default));
        Assert.Contains(reason, failure.Message);
        Assert.Equal(25, calls); Assert.Equal(24, waits);
        var timeout = evidence.Snapshot(300);
        Assert.Equal(25, timeout.CurrentProbe!.PoseAcquisitionOrdinal);
        Assert.Equal(stage, timeout.CurrentProbe.Stage);
        Assert.Equal(reason, timeout.CurrentProbe.RetryReason);
        Assert.False(timeout.CurrentProbe.ReturnedSample);
        Assert.NotNull(timeout.CurrentProbe.ReturnedAtTicks);
        Assert.Null(timeout.LastCompletedProbe);
    }

    /// <summary>An interrupted later probe never relabels the previous retry/source/timing as its own.</summary>
    [Fact]
    public void IncompleteProbeRetainsSeparateCompletedEvidence()
    {
        var evidence = new NavigationResetPoseTimeoutEvidence(1);
        var first = evidence.Begin(21, 100);
        first.Stage = first.SourceCheckStage = "after_recognition";
        first.Source = new GameCaptureSourceInfo(Guid.NewGuid(), 20, 30);
        first.SourceCheckedAtTicks = 150;
        first.RecognitionStartedAtTicks = 120; first.RecognitionFinishedAtTicks = 149;
        GameCaptureCallTiming.Run(_ => null, out var timing); first.Capture = timing;
        evidence.Complete(new(null, "pose_source_stale; stage=after_recognition; source=20"), 151);
        var current = evidence.Begin(22, 270);
        current.PendingReadback = GameCaptureReadbackConsumerTests.Pending();
        current.CaptureFinishedAtTicks = 280;
        var timeout = evidence.Snapshot(300);
        Assert.Equal(22, timeout.CurrentProbe!.PoseAcquisitionOrdinal);
        Assert.Null(timeout.CurrentProbe.Source); Assert.Null(timeout.CurrentProbe.Capture);
        Assert.Null(timeout.CurrentProbe.SourceCheckedAtTicks); Assert.Null(timeout.CurrentProbe.ReturnedAtTicks);
        Assert.Null(timeout.CurrentProbe.ReturnedSample); Assert.Null(timeout.CurrentProbe.RetryReason);
        Assert.Equal(21, timeout.LastCompletedProbe!.PoseAcquisitionOrdinal);
        Assert.Equal(150, timeout.LastCompletedProbe.SourceCheckedAtTicks);
        Assert.Same(timing, timeout.LastCompletedProbe.Capture);
        Assert.Same(first.Source, timeout.LastCompletedProbe.Source);
        Assert.Equal(300, timeout.TimedOutAtTicks);
        Assert.NotEqual(timeout.TimedOutAtTicks, timeout.LastCompletedProbe.SourceCheckedAtTicks);
    }

    /// <summary>Returned samples remain explicitly distinguishable from deadline acceptance.</summary>
    [Fact]
    public void ReturnedSampleIsNotWindowSuccess()
    {
        var evidence = new NavigationResetPoseTimeoutEvidence(1);
        evidence.Begin(1, 10);
        var sample = new NavigationResetSample(1, 2, 3, DateTimeOffset.UnixEpoch, Guid.NewGuid(), 4, 5, 1, 1, "City_102");
        evidence.Complete(new(sample, null), 99);
        var timeout = evidence.Snapshot(100);
        Assert.True(timeout.CurrentProbe!.ReturnedSample);
        Assert.Null(timeout.CurrentProbe.RetryReason);
        Assert.Equal(99, timeout.CurrentProbe.ReturnedAtTicks);
        Assert.DoesNotContain("\"Sample\":", JsonConvert.SerializeObject(timeout));
    }

    /// <summary>Starting another acquisition cannot inherit the last orientation/readback evidence.</summary>
    [Fact]
    public void NewWindowHasNoPreviousProbeAndSnapshotIsDetached()
    {
        var old = new NavigationResetPoseTimeoutEvidence(1);
        var row = old.Begin(9, 10); row.Stage = "yaw_recognition";
        old.Complete(new(null, "yaw_unrecognized"), 11);
        var saved = old.Snapshot(12);
        row.Stage = "changed_after_snapshot";
        Assert.Equal("yaw_recognition", saved.CurrentProbe!.Stage);
        var next = new NavigationResetPoseTimeoutEvidence(20).Snapshot(21);
        Assert.Null(next.CurrentProbe); Assert.Null(next.LastCompletedProbe);
    }

    /// <summary>Owner cancellation and hard failures keep their original exception types and perform no retry delay.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public async Task CancellationAndHardFailureAreNotTimeoutEvidence(bool cancel)
    {
        using var stop = new CancellationTokenSource();
        var evidence = new NavigationResetPoseTimeoutEvidence(1); var delays = 0;
        var work = NavigationResetPoseAcquisition.ReadAsync(_ =>
        {
            evidence.Begin(1, 2);
            if (cancel) { stop.Cancel(); stop.Token.ThrowIfCancellationRequested(); }
            throw new InvalidOperationException("game_target_lost");
        }, (_, _) => { delays++; return Task.CompletedTask; }, stop.Token);
        if (cancel) await Assert.ThrowsAnyAsync<OperationCanceledException>(() => work);
        else Assert.Equal("game_target_lost", (await Assert.ThrowsAsync<InvalidOperationException>(() => work)).Message);
        Assert.Equal(0, delays);
        Assert.Null(evidence.Snapshot(3).CurrentProbe!.ReturnedAtTicks);
    }

    /// <summary>Only two metadata slots survive many probes, and retry text uses the pre-existing200-character bound.</summary>
    [Fact]
    public void MetadataStorageAndTextRemainBounded()
    {
        var evidence = new NavigationResetPoseTimeoutEvidence(1);
        for (var i = 1; i <= 25; i++)
        {
            var row = evidence.Begin(i, i * 10);
            row.Source = new GameCaptureSourceInfo(Guid.NewGuid(), long.MaxValue, long.MaxValue);
            GameCaptureCallTiming.Run(_ => null, out var timing); row.Capture = timing;
            row.PendingReadback = GameCaptureReadbackConsumerTests.Pending();
            if (i < 25) evidence.Complete(new(null, new string('x', 5000)), i * 10 + 1);
        }
        var detail = evidence.Snapshot(300);
        Assert.Equal(25, detail.CurrentProbe!.PoseAcquisitionOrdinal);
        Assert.Equal(24, detail.LastCompletedProbe!.PoseAcquisitionOrdinal);
        Assert.Equal(200, detail.LastCompletedProbe.RetryReason!.Length);
        var record = new NavigationResetSourceDiagnostic { Reason = "pose_acquisition_timeout", Stage = "capture",
            Phase = "verifying", NowTicks = 300, PoseAcquisitionTimeout = detail };
        var json = JsonConvert.SerializeObject(record);
        Assert.True(System.Text.Encoding.UTF8.GetByteCount(json) < 32 * 1024);
        Assert.Equal(2, record.Version); Assert.Equal(1, detail.Version); Assert.Equal(500, record.MaximumAgeMs);
        Assert.DoesNotContain("\"Frame\":", json);
        Assert.DoesNotContain("\"Samples\":", json);
    }
}
