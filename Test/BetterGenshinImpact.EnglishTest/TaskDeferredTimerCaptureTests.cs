using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Common.BgiVision;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Managed owner/drain/cleanup tests; no application, timer, game capture or native input is created.</summary>
public sealed class TaskDeferredTimerCaptureTests
{
    /// <summary>A callback-only lease gives assertions exact ownership and cleanup order.</summary>
    private sealed class Lease(Action release) : IDisposable
    {
        /// <inheritdoc />
        public void Dispose() => release();
    }

    /// <summary>Task return/fault/cancellation cannot strand a pending activation, even when End itself fails.</summary>
    [Theory]
    [InlineData("return", false)]
    [InlineData("fault", false)]
    [InlineData("cancel", false)]
    [InlineData("return", true)]
    public async Task PendingActivationDrainsBeforeEndAndRetainsAcquiredResources(string exit, bool endThrows)
    {
        var order = new List<string>(); var pending = new TaskCompletionSource<IDisposable>(TaskCreationOptions.RunContinuationsAsynchronously);
        var cancellationSeen = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var ownerStop = new CancellationTokenSource();
        using var taskSemaphore = new SemaphoreSlim(0, 1);
        var hotkeyHeld = false; var captureHeld = false; CancellationTokenRegistration registration = default;
        var owner = new TaskDeferredTimerCapture(ownerStop.Token, () => { },
            () => { hotkeyHeld = true; return new Lease(() => { order.Add("hotkey"); hotkeyHeld = false; }); },
            token => { registration = token.Register(() => cancellationSeen.TrySetResult()); return pending.Task; });
        Task? activation = null; Task? ending = null; Exception? actionError = null;
        try
        {
            try
            {
                activation = owner.ActivateAsync(default);
                Assert.True(hotkeyHeld); Assert.False(activation.IsCompleted);
                if (exit == "fault") throw new InvalidOperationException("native_work_failed");
                if (exit == "cancel") { ownerStop.Cancel(); throw new OperationCanceledException(ownerStop.Token); }
            }
            catch (Exception exception) { actionError = exception; }
            finally
            {
                order.Add("native_disposed");
                ending = owner.EndAsync(() =>
                {
                    Assert.True(hotkeyHeld); Assert.True(captureHeld); Assert.Equal(0, taskSemaphore.CurrentCount);
                    order.Add("end_inputs"); if (endThrows) throw new InvalidOperationException("end_failed");
                });
            }
            await cancellationSeen.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.False(ending.IsCompleted); Assert.DoesNotContain("end_inputs", order);
            Assert.Throws<InvalidOperationException>(() => { _ = owner.ActivateAsync(default); });
            // Model a real waiter whose cancellation is only observed after synchronous trigger cleanup returns.
            captureHeld = true;
            pending.SetResult(new Lease(() => { order.Add("capture"); captureHeld = false; Assert.Equal(0, taskSemaphore.CurrentCount); }));
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => activation!);
            if (endThrows) await Assert.ThrowsAsync<InvalidOperationException>(() => ending);
            else await ending;
            Assert.Same(ending, owner.EndAsync(() => throw new Exception("must not end twice")));
            Assert.Equal(new[] { "native_disposed", "end_inputs", "capture", "hotkey" }, order);
            Assert.False(hotkeyHeld); Assert.False(captureHeld);
            Assert.Equal(exit != "return", actionError is not null);
        }
        finally { registration.Dispose(); taskSemaphore.Release(); }
    }

    /// <summary>A never-used optional callback creates no hotkey/capture side effects, and late invocation stays rejected.</summary>
    [Fact]
    public async Task NeverActivatedOwnerEndsWithoutSideEffects()
    {
        var ended = 0;
        var owner = new TaskDeferredTimerCapture(default, () => throw new Exception("must not validate"),
            () => throw new Exception("must not preserve"), _ => throw new Exception("must not acquire"));
        await owner.EndAsync(() => ended++);
        Assert.Throws<InvalidOperationException>(() => { _ = owner.ActivateAsync(default); });
        await owner.EndAsync(() => ended++);
        Assert.Equal(1, ended);
    }

    /// <summary>Already-cancelled owner/caller tokens reject admission before runtime, hotkeys or dispatcher access.</summary>
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task PreCancelledAdmissionHasNoSideEffects(bool ownerCancelled)
    {
        using var stop = new CancellationTokenSource(); stop.Cancel();
        var owner = new TaskDeferredTimerCapture(ownerCancelled ? stop.Token : default,
            () => throw new Exception("must not validate"), () => throw new Exception("must not preserve"),
            _ => throw new Exception("must not acquire"));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => owner.ActivateAsync(ownerCancelled ? default : stop.Token));
        await owner.EndAsync(() => { });
    }

    /// <summary>Only one admission is possible, whether the first is pending or successfully acquired.</summary>
    [Fact]
    public async Task RepeatedActivationCannotAcquireOrReleaseAnotherLease()
    {
        var acquisitions = 0; var disposals = 0;
        var pending = new TaskCompletionSource<IDisposable>(TaskCreationOptions.RunContinuationsAsynchronously);
        var owner = new TaskDeferredTimerCapture(default, () => { }, () => new Lease(() => disposals++),
            _ => { acquisitions++; return pending.Task; });
        var first = owner.ActivateAsync(default);
        Assert.Throws<InvalidOperationException>(() => { _ = owner.ActivateAsync(default); });
        pending.SetResult(new Lease(() => disposals++)); await first;
        Assert.Throws<InvalidOperationException>(() => { _ = owner.ActivateAsync(default); });
        Assert.Equal(1, acquisitions); Assert.Equal(0, disposals);
        await owner.EndAsync(() => Assert.Equal(0, disposals)); Assert.Equal(2, disposals);
    }

    /// <summary>Runtime rejection before admission has no side effects; rejection after acquisition retains both scopes through End.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RuntimeReplacementBeforeOrAfterAcquisitionFailsClosed(bool afterAcquire)
    {
        var validations = 0; var hotkeyHeld = false; var captureHeld = false;
        var owner = new TaskDeferredTimerCapture(default, () =>
        {
            if (++validations == (afterAcquire ? 2 : 1)) throw new InvalidOperationException("timer_capture_runtime_changed");
        }, () => { hotkeyHeld = true; return new Lease(() => hotkeyHeld = false); },
        _ => { captureHeld = true; return Task.FromResult<IDisposable>(new Lease(() => captureHeld = false)); });
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => owner.ActivateAsync(default));
        Assert.Equal("timer_capture_runtime_changed", error.Message);
        await owner.EndAsync(() => { Assert.Equal(afterAcquire, hotkeyHeld); Assert.Equal(afterAcquire, captureHeld); });
        Assert.False(hotkeyHeld); Assert.False(captureHeld);
    }

    /// <summary>Timeout/capture cleanup failure still preserves the actual configured cancellation hotkey until End.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task FailureDoesNotLeakConfiguredCancellationScope(bool captureDisposeThrows)
    {
        ChatUiHotkeyGuard.Reset();
        var chat = new ChatUiDetectionResult(ChatUiState.InputOpen, true, true, true, 2, true);
        ChatUiHotkeyGuard.UpdateVisualState(chat); ChatUiHotkeyGuard.UpdateVisualState(chat);
        var owner = new TaskDeferredTimerCapture(default, () => { }, ChatUiHotkeyGuard.PreserveTaskCancellation,
            _ => captureDisposeThrows ? Task.FromResult<IDisposable>(new Lease(() => throw new InvalidOperationException("dispose_failed")))
                : Task.FromException<IDisposable>(new TimeoutException("timer_capture_drain_timeout")));
        try
        {
            if (captureDisposeThrows) await owner.ActivateAsync(default);
            else await Assert.ThrowsAsync<TimeoutException>(() => owner.ActivateAsync(default));
            void End() => Assert.False(ChatUiHotkeyGuard.ShouldBlockHotkey(nameof(HotKeyConfig.CancelTaskHotkey)));
            if (captureDisposeThrows) await Assert.ThrowsAsync<InvalidOperationException>(() => owner.EndAsync(End));
            else await owner.EndAsync(End);
            Assert.True(ChatUiHotkeyGuard.ShouldBlockHotkey(nameof(HotKeyConfig.CancelTaskHotkey)));
        }
        finally { ChatUiHotkeyGuard.Reset(); }
    }
}
