using System.Diagnostics;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using BetterGenshinImpact.GameTask.NavigationReset;
using Fischless.GameCapture;
using OpenCvSharp;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>One guarded map close and unchanged bounded world-readiness admission; no game, native input or application starts.</summary>
public sealed class NavigationResetMapRecoveryTests
{
    /// <summary>Synthetic positive QPC origin, shared by source timestamps and immutable acquisition clocks.</summary>
    private static readonly long Origin = Stopwatch.Frequency * 100;
    /// <summary>Convert an integral millisecond offset to the test clock.</summary>
    private static long At(int ms) => Origin + Stopwatch.Frequency * ms / 1000;
    /// <summary>Construct an exact source, allowing the two clocks to disagree in boundary tests.</summary>
    private static GameCaptureSourceInfo Source(Guid epoch, int reportedMs = 0, int? acquiredMs = null) =>
        new(epoch, 1_000_000_000L + reportedMs * 10_000L, At(acquiredMs ?? reportedMs));
    /// <summary>Direct visual result supplied by CPU tests; the production matcher remains unchanged.</summary>
    private static ChatUiDetectionResult Chat(ChatUiState state) => new(state, false, false, false, 0, false);

    /// <summary>Missing HUD is never authority; map and close markers must both exist on the same admitted pixels.</summary>
    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    public void MissingPositiveMapOrCloseSendsNoRecovery(bool map, bool close)
    {
        using var pixels = new Mat(1080, 1920, MatType.CV_8UC3, Scalar.All(1));
        Assert.False(NavigationResetMapRecovery.RecognizeKnownMap(pixels, _ => map, _ => close,
            _ => throw new Exception("chat must not run"), _ => throw new Exception("modal must not run"), _ => { }));
        Assert.Throws<InvalidOperationException>(() => NativeNavigationResetOperations.WorldRetryReason(
            AgentWorldEvidence.HudMissing, false, 100));
    }

    /// <summary>Template, closed-chat and modal checks borrow caller pixels and do not dispose their owner.</summary>
    [Fact]
    public void PositiveMapUsesSamePixelsAndAllGuardsInOrder()
    {
        using var pixels = new Mat(1080, 1920, MatType.CV_8UC4, Scalar.All(7));
        var order = new List<string>();
        Assert.True(NavigationResetMapRecovery.RecognizeKnownMap(pixels,
            region => { Assert.Equal(pixels.Data, region.SrcMat.Data); order.Add("map"); return true; },
            region => { Assert.Equal(pixels.Data, region.SrcMat.Data); order.Add("close"); return true; },
            _ => { order.Add("chat"); return Chat(ChatUiState.Closed); },
            _ => { order.Add("modal"); return false; }, _ => order.Add("update")));
        Assert.Equal(new[] { "map", "close", "chat", "update", "modal" }, order);
        Assert.False(pixels.IsDisposed); Assert.Equal(7, pixels.At<Vec4b>(0, 0).Item0);
    }

    /// <summary>Direct chat evidence, including unknown enum values, blocks Escape before modal or input work.</summary>
    [Theory]
    [InlineData(ChatUiState.PanelOpen)]
    [InlineData(ChatUiState.InputOpen)]
    [InlineData((ChatUiState)99)]
    public void OpenOrUnknownChatCannotAuthorizeMapClose(ChatUiState state)
    {
        using var pixels = new Mat(1080, 1920, MatType.CV_8UC3);
        var updated = false;
        var error = Assert.Throws<InvalidOperationException>(() => NavigationResetMapRecovery.RecognizeKnownMap(
            pixels, _ => true, _ => true, _ => Chat(state), _ => throw new Exception("must not run"), _ => updated = true));
        Assert.Contains("chat_not_closed", error.Message); Assert.True(updated);
    }

    /// <summary>Recognized modal overlays cannot hide behind AgentWorldRecognizer's early missing-HUD return.</summary>
    [Fact]
    public void ModalAndRecognizerFailureRemainTerminal()
    {
        using var pixels = new Mat(1080, 1920, MatType.CV_8UC3);
        Assert.Contains("blocking_ui", Assert.Throws<InvalidOperationException>(() => NavigationResetMapRecovery.RecognizeKnownMap(
            pixels, _ => true, _ => true, _ => Chat(ChatUiState.Closed), _ => true, _ => { })).Message);
        var expected = new InvalidOperationException("asset failure");
        Assert.Same(expected, Assert.Throws<InvalidOperationException>(() => NavigationResetMapRecovery.RecognizeKnownMap(
            pixels, _ => throw expected, _ => true, _ => Chat(ChatUiState.Closed), _ => false, _ => { })));
    }

    /// <summary>Uncalibrated geometry fails before any matcher can label a full-size frame closed.</summary>
    [Theory]
    [InlineData(1921, 1080)]
    [InlineData(1920, 1081)]
    public void UnsupportedGeometryDoesNotInvokeRecognition(int width, int height)
    {
        using var pixels = new Mat(height, width, MatType.CV_8UC3);
        var called = false;
        Assert.Throws<InvalidOperationException>(() => NavigationResetMapRecovery.RecognizeKnownMap(
            pixels, _ => { called = true; return true; }, _ => true, _ => Chat(ChatUiState.Closed), _ => false, _ => { }));
        Assert.False(called);
    }

    /// <summary>One successful press includes an explicit release; reentry cannot send another Escape.</summary>
    [Fact]
    public void OneAttemptRecordsReleaseAndCannotRepeat()
    {
        var recovery = new NavigationResetMapRecovery(); var epoch = Guid.NewGuid(); var source = Source(epoch, -10);
        var now = Origin; var calls = new List<string>();
        recovery.CloseOnce(source, Origin, () => calls.Add("target"), () => { calls.Add("press"); now = At(1); },
            () => { calls.Add("up"); now = At(2); }, CancellationToken.None, () => now);
        Assert.Equal(new[] { "target", "press", "up" }, calls); Assert.Same(source, recovery.TriggerSource);
        Assert.Equal(Origin, recovery.RequestedAtTicks); Assert.Equal(At(2), recovery.ReleasedAtTicks);
        Assert.Throws<InvalidOperationException>(() => recovery.CloseOnce(source, Origin, () => { },
            () => calls.Add("second"), () => { }, CancellationToken.None, () => now));
        Assert.DoesNotContain("second", calls);
    }

    /// <summary>Native press failure still attempts key-up exactly once and preserves both failure identities.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void AmbiguousPressAlwaysReleasesAndNeverRetries(bool releaseFails)
    {
        var recovery = new NavigationResetMapRecovery(); var releases = 0;
        var expected = new InvalidOperationException("partial native press");
        Assert.Same(expected, Assert.Throws<InvalidOperationException>(() => recovery.CloseOnce(Source(Guid.NewGuid()), Origin,
            () => { }, () => throw expected, () => { releases++; if (releaseFails) throw new Exception("up failed"); },
            CancellationToken.None, () => Origin)));
        Assert.True(recovery.Attempted); Assert.Equal(1, releases); Assert.Equal(expected.Message, recovery.Error);
        Assert.Equal(releaseFails ? "up failed" : null, recovery.ReleaseError);
        Assert.Equal(releaseFails ? (long?)null : Origin, recovery.ReleasedAtTicks);
    }

    /// <summary>A failed key-up after a successful press is terminal and never supplies a settling cutoff.</summary>
    [Fact]
    public void ReleaseFailureIsNotSuccessfulRecovery()
    {
        var recovery = new NavigationResetMapRecovery(); var presses = 0;
        Assert.Throws<InvalidOperationException>(() => recovery.CloseOnce(Source(Guid.NewGuid()), Origin, () => { },
            () => presses++, () => throw new InvalidOperationException("release failed"), CancellationToken.None, () => Origin));
        Assert.Equal(1, presses); Assert.Null(recovery.ReleasedAtTicks); Assert.Equal("release failed", recovery.ReleaseError);
    }

    /// <summary>Clock/source/target failure at admission cannot send a key or consume its once-only latch.</summary>
    [Theory]
    [InlineData(501, 0)]
    [InlineData(0, 3000)]
    [InlineData(0, -1)]
    public void InvalidSourceOrWindowPreventsInput(int age, int elapsed)
    {
        var recovery = new NavigationResetMapRecovery(); var calls = 0;
        Assert.Throws<InvalidOperationException>(() => recovery.CloseOnce(Source(Guid.NewGuid(), elapsed - age), Origin,
            () => { }, () => calls++, () => calls++, CancellationToken.None, () => At(elapsed)));
        Assert.Equal(0, calls); Assert.False(recovery.Attempted);
    }

    /// <summary>Target validation time is charged to both freshness and the original preparation deadline.</summary>
    [Theory]
    [InlineData(501)]
    [InlineData(3000)]
    public void SlowTargetCheckCannotDispatch(int delay)
    {
        var recovery = new NavigationResetMapRecovery(); var now = Origin; var calls = 0;
        Assert.Throws<InvalidOperationException>(() => recovery.CloseOnce(Source(Guid.NewGuid()), Origin,
            () => now = At(delay), () => calls++, () => calls++, CancellationToken.None, () => now));
        Assert.Equal(0, calls); Assert.False(recovery.Attempted);
    }

    /// <summary>Cancellation before dispatch sends nothing; cancellation during native work still releases the attempted key.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void CancellationRespectsInputBoundary(bool duringPress)
    {
        using var stop = new CancellationTokenSource(); var recovery = new NavigationResetMapRecovery(); var press = 0; var up = 0;
        if (!duringPress) stop.Cancel();
        Assert.Throws<OperationCanceledException>(() => recovery.CloseOnce(Source(Guid.NewGuid()), Origin, () => { },
            () => { press++; stop.Cancel(); }, () => up++, stop.Token, () => Origin));
        Assert.Equal(duringPress ? 1 : 0, press); Assert.Equal(duringPress ? 1 : 0, up);
    }

    /// <summary>A delayed native call is released but cannot produce a valid readiness result.</summary>
    [Fact]
    public void LatePressCannotBecomeReadiness()
    {
        var recovery = new NavigationResetMapRecovery(); var now = Origin; var up = 0;
        Assert.Throws<InvalidOperationException>(() => recovery.CloseOnce(Source(Guid.NewGuid()), Origin, () => { },
            () => now = At(3000), () => up++, CancellationToken.None, () => now));
        Assert.Equal(1, up); Assert.True(recovery.Attempted); Assert.NotNull(recovery.Error);
    }

    /// <summary>Both clocks and source identity must advance beyond the explicit key-up cutoff.</summary>
    [Theory]
    [InlineData(0, 0, false)]
    [InlineData(79, 81, false)]
    [InlineData(81, 79, false)]
    [InlineData(81, 81, true)]
    public void BothClockBarrierRejectsCachedOrPrematurePixels(int reported, int acquired, bool accepted)
    {
        var epoch = Guid.NewGuid(); var recovery = new NavigationResetMapRecovery();
        recovery.CloseOnce(Source(epoch), Origin, () => { }, () => { }, () => { }, CancellationToken.None, () => Origin);
        Assert.Equal(accepted, recovery.SourcePassedRelease(Source(epoch, reported, acquired)));
        Assert.False(recovery.SourcePassedRelease(Source(Guid.NewGuid(), 81)));
    }

    /// <summary>The existing preparation helper counts map waiting and never reopens a spent three-second/25-probe window.</summary>
    [Fact]
    public async Task PersistentMapExhaustsExistingBudgetWithOnePress()
    {
        var recovery = new NavigationResetMapRecovery(); var now = Origin; var attempts = 0; var presses = 0;
        var error = await Assert.ThrowsAsync<NavigationResetPreparationTimeoutException>(() => NavigationResetPreparationReadiness.WaitAsync(
            (_, token) => { attempts++; if (!recovery.Attempted) recovery.CloseOnce(Source(Guid.NewGuid()), Origin,
                () => { }, () => presses++, () => { }, token, () => now); return NavigationResetPreparationState.MapClosing; },
            (ms, _) => { now += Stopwatch.Frequency * ms / 1000; return Task.CompletedTask; }, CancellationToken.None, () => now));
        Assert.Equal(25, attempts); Assert.Equal(1, presses); Assert.Contains("map_close_not_world_ready", error.Message);
    }

    /// <summary>A known map close, one cached HUD, and then a settled new HUD finish without a second Escape.</summary>
    [Fact]
    public async Task ClosedMapRequiresNewSettledWorldBeforeReadiness()
    {
        var epoch = Guid.NewGuid(); var recovery = new NavigationResetMapRecovery(); var now = Origin; var presses = 0; var probes = 0;
        await NavigationResetPreparationReadiness.WaitAsync((_, token) =>
        {
            probes++;
            if (!recovery.Attempted)
            {
                recovery.CloseOnce(Source(epoch), Origin, () => { }, () => presses++, () => { }, token, () => now);
                return NavigationResetPreparationState.MapClosing;
            }
            var current = probes == 2 ? Source(epoch) : Source(epoch, 240);
            NativeNavigationResetOperations.WorldRetryReason(AgentWorldEvidence.WorldHud, true, current.SourceTimestamp100ns);
            return recovery.SourcePassedRelease(current) ? NavigationResetPreparationState.Ready : NavigationResetPreparationState.MapClosing;
        }, (ms, _) => { now += Stopwatch.Frequency * ms / 1000; return Task.CompletedTask; }, CancellationToken.None, () => now);
        Assert.Equal(3, probes); Assert.Equal(1, presses);
    }

    /// <summary>Blocking/recognition errors remain terminal even after the single known-map action.</summary>
    [Theory]
    [InlineData(AgentWorldEvidence.BlockingUi)]
    [InlineData(AgentWorldEvidence.RecognitionFailed)]
    [InlineData((AgentWorldEvidence)99)]
    public void HardPostCloseWorldFailureNeverSettles(AgentWorldEvidence evidence) =>
        Assert.Throws<InvalidOperationException>(() => NativeNavigationResetOperations.WorldRetryReason(evidence, true, 100));
    /// <summary>A true modal on a missing-HUD transition fails immediately instead of waiting for a later clear frame.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void MissingHudSettlingChecksModalIndependently(bool modal)
    {
        using var pixels = new Mat(1080, 1920, MatType.CV_8UC3);
        var seen = false;
        void Validate() => NavigationResetMapRecovery.ValidateSettlingWorld(pixels, AgentWorldEvidence.HudMissing,
            region => { seen = true; Assert.Equal(pixels.Data, region.SrcMat.Data); return modal; });
        if (modal) Assert.Throws<InvalidOperationException>((Action)Validate); else Validate();
        Assert.True(seen); Assert.False(pixels.IsDisposed);
    }

    /// <summary>A clock regression after successful key-up cannot publish a usable response cutoff.</summary>
    [Fact]
    public void ClockRegressionAfterReleaseFailsClosed()
    {
        var recovery = new NavigationResetMapRecovery(); var clocks = new Queue<long>([Origin, Origin, At(10), At(5)]);
        var error = Assert.Throws<InvalidOperationException>(() => recovery.CloseOnce(Source(Guid.NewGuid()), Origin,
            () => { }, () => { }, () => { }, CancellationToken.None, () => clocks.Dequeue()));
        Assert.Equal("preparation_clock_regressed", error.Message); Assert.NotNull(recovery.Error);
    }

    /// <summary>Target/backend/mode failure has no key cleanup side effect before an attempt exists.</summary>
    [Fact]
    public void TargetFailureBeforeAttemptSendsNothing()
    {
        var recovery = new NavigationResetMapRecovery(); var calls = 0;
        var expected = new InvalidOperationException("readback_mode_changed");
        Assert.Same(expected, Assert.Throws<InvalidOperationException>(() => recovery.CloseOnce(Source(Guid.NewGuid()), Origin,
            () => throw expected, () => calls++, () => calls++, CancellationToken.None, () => Origin)));
        Assert.False(recovery.Attempted); Assert.Equal(0, calls);
    }

}
