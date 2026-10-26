using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.Core.Mask;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using Fischless.GameCapture.DesktopDc;
using Vanara.PInvoke;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.Pulonia.Services;

namespace BetterGenshinImpact.UnitTest.Pulonia;

/// <summary>
/// 游戏任务租约的嵌套检测，不启动游戏、不占用全局任务锁。
/// </summary>
public sealed class PuloniaGameTaskCoordinatorTests
{
    /// <summary>
    /// 已在任务会话内（例如节点执行器或 TaskRunner 任务内部）再次获取租约时立即报错，而不是永久等待不可重入的任务锁。
    /// </summary>
    [Fact]
    public async Task AcquireAsync_InsideGameTaskSession_ThrowsImmediately()
    {
        var coordinator = new PuloniaGameTaskCoordinator(null!);
        using (GameTaskSessionScope.Enter())
        {
            var error = await Assert.ThrowsAsync<InvalidOperationException>(
                () => coordinator.AcquireAsync(CancellationToken.None)).WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Contains("当前已在任务会话中", error.Message);
        }
        Assert.False(GameTaskSessionScope.IsActive);
    }
    /// <summary>Both desktop policies remain unavailable to a generic Pulonia node before activation.</summary>
    [Theory]
    [InlineData(DesktopCapturePolicy.ObserveOnly)]
    [InlineData(DesktopCapturePolicy.HostAcquisitionV1)]
    public void GenericAdmissionRejectsDesktopCapture(string policy)
    {
        using var baseline = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1));
        using var runtime = new GameRuntime(baseline.Kind, baseline.Window, new DesktopDcCapture(),
            baseline.Input, baseline.SystemInfo, NullMaskWindowDrawingBoard.Instance, new MaskWindowMapState(), policy);
        var error = Assert.Throws<InvalidOperationException>(() => PuloniaGameTaskCoordinator.ValidateAdmission(runtime));
        Assert.Equal("desktop_capture_legacy_task_not_supported", error.Message);
    }

    /// <summary>Ordinary managed fake bindings remain admitted; stopping cannot pass the post-wait recheck.</summary>
    [Fact]
    public void GenericAdmissionPreservesOrdinaryBindingAndRejectsStopping()
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1));
        PuloniaGameTaskCoordinator.ValidateAdmission(runtime);
        runtime.SignalStopping();
        Assert.Throws<InvalidOperationException>(() => PuloniaGameTaskCoordinator.ValidateAdmission(runtime));
    }
}
