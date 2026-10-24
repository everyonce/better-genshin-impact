using System.Reflection;
using System.Runtime.CompilerServices;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.GameTask.Runtime.Win32;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Managed startup boundaries with no process, window, input, timer or capture allocation.</summary>
public sealed class DesktopDcAutomatedStartupTests
{
    /// <summary>Only the startup-pinned Desktop backend and exact source policy may reach attachment after an await.</summary>
    [Theory]
    [InlineData("DesktopDc", "observe-only", true)]
    [InlineData("DesktopDc", "host-acquisition-v1", false)]
    [InlineData("WindowsGraphicsCaptureV2", "observe-only", false)]
    [InlineData("unknown", "observe-only", false)]
    public void ChangedCaptureSelectionCannotAttach(string mode, string policy, bool accepted)
    {
        var config = new AllConfig { CaptureMode = mode, DesktopDcSourcePolicy = policy };
        if (accepted) Win32RuntimeProvider.CheckDesktopStartupSelection(config, "observe-only");
        else Assert.Throws<InvalidOperationException>(() => Win32RuntimeProvider.CheckDesktopStartupSelection(config, "observe-only"));
    }

    /// <summary>An already foreground game needs no native setter or confirmation wait.</summary>
    [Fact]
    public async Task AlreadyForegroundDoesNotSet()
    {
        var f = new Focus { InitiallyForeground = true };
        await f.Run();
        Assert.Equal(0, f.Sets); Assert.Equal(1, f.Reads); Assert.Equal(0, f.Waits);
    }

    /// <summary>Immediate and asynchronously confirmed activation both invoke the setter exactly once.</summary>
    [Theory]
    [InlineData(0)] [InlineData(3)]
    public async Task OneSetterWithBoundedReadonlyConfirmation(int delayedReads)
    {
        var f = new Focus { DelayedReads = delayedReads };
        await f.Run();
        Assert.Equal(1, f.Sets); Assert.Equal(delayedReads + 2, f.Reads);
        Assert.Equal(delayedReads, f.Waits); Assert.InRange(f.Now, 10000, 11000);
    }

    /// <summary>A denied setter is terminal even if a later snapshot would claim foreground.</summary>
    [Fact]
    public async Task DeniedSetterDoesNotRetryOrReadAgain()
    {
        var f = new Focus { SetterResult = false };
        var error = await Assert.ThrowsAsync<InvalidOperationException>(f.Run);
        Assert.Equal("desktop_startup_foreground_denied", error.Message);
        Assert.Equal(1, f.Sets); Assert.Equal(1, f.Reads); Assert.Equal(0, f.Waits);
    }

    /// <summary>A native-setter exception remains the primary failure, without a second attempt.</summary>
    [Fact]
    public async Task SetterFailureRemainsObservable()
    {
        var expected = new InvalidOperationException("synthetic setter error");
        var f = new Focus { SetterError = expected };
        Assert.Same(expected, await Assert.ThrowsAsync<InvalidOperationException>(f.Run));
        Assert.Equal(1, f.Sets); Assert.Equal(1, f.Reads);
    }

    /// <summary>Invalid target/session/desktop evidence never reaches the foreground setter.</summary>
    [Theory]
    [InlineData("window")] [InlineData("pid")] [InlineData("creation")] [InlineData("process")]
    [InlineData("session")] [InlineData("callerSession")] [InlineData("callerPid")] [InlineData("class")]
    [InlineData("dead")] [InlineData("hidden")] [InlineData("minimized")]
    [InlineData("station")] [InlineData("threadDesktop")] [InlineData("inputDesktop")]
    public async Task InvalidInitialTargetCannotFocus(string field)
    {
        var f = new Focus { Transform = (_, row) => field switch
        {
            "window" => row with { Window = 1 }, "pid" => row with { ProcessId = 0 },
            "creation" => row with { CreatedAtUtcTicks = 0 }, "process" => row with { ProcessName = "Other" },
            "session" => row with { SessionId = 0 }, "callerSession" => row with { CallerSessionId = 2 },
            "callerPid" => row with { CallerProcessId = 0 }, "class" => row with { WindowClass = "Other" },
            "dead" => row with { Active = false }, "hidden" => row with { Visible = false },
            "minimized" => row with { Minimized = true }, "station" => row with { WindowStation = "Other" },
            "threadDesktop" => row with { ThreadDesktop = "Other" }, _ => row with { InputDesktop = "Other" }
        } };
        await Assert.ThrowsAsync<InvalidOperationException>(f.Run);
        Assert.Equal(0, f.Sets);
    }

    /// <summary>Explicit startup may yield BetterGI's foreground, never take it from an unrelated application.</summary>
    [Fact]
    public async Task OtherForegroundApplicationCannotFocus()
    {
        var f = new Focus { Transform = (_, row) => row with { ForegroundProcessId = 42 } };
        var error = await Assert.ThrowsAsync<InvalidOperationException>(f.Run);
        Assert.Equal("desktop_startup_caller_not_foreground", error.Message); Assert.Equal(0, f.Sets);
    }

    /// <summary>Reused identity or a different caller cannot be accepted after the single setter.</summary>
    [Theory]
    [InlineData("pid")] [InlineData("creation")] [InlineData("process")]
    [InlineData("session")] [InlineData("caller")]
    public async Task ChangedPostTargetCannotAttach(string field)
    {
        var f = new Focus { Transform = (index, row) => index == 1 ? row : field switch
        {
            "pid" => row with { ProcessId = 28 }, "creation" => row with { CreatedAtUtcTicks = 1235 },
            "process" => row with { ProcessName = "YuanShen" },
            "session" => row with { SessionId = 4, CallerSessionId = 4 }, _ => row with { CallerProcessId = 32 }
        } };
        await Assert.ThrowsAsync<InvalidOperationException>(f.Run);
        Assert.Equal(1, f.Sets); Assert.Equal(0, f.Waits);
    }

    /// <summary>Visibility changes after activation remain terminal rather than triggering restoration.</summary>
    [Fact]
    public async Task MinimizedAfterSetterCannotAttach()
    {
        var f = new Focus { Transform = (index, row) => index == 1 ? row : row with { Minimized = true } };
        await Assert.ThrowsAsync<InvalidOperationException>(f.Run); Assert.Equal(1, f.Sets);
    }

    /// <summary>Cancellation at each admitted asynchronous boundary cannot publish startup permission.</summary>
    [Theory]
    [InlineData("before")] [InlineData("initialRead")] [InlineData("setter")] [InlineData("wait")]
    public async Task CancellationNeverRetries(string phase)
    {
        using var cancellation = new CancellationTokenSource();
        var f = new Focus { Token = cancellation.Token, DelayedReads = 3 };
        if (phase == "before") cancellation.Cancel();
        if (phase == "initialRead") f.Transform = (_, row) => { cancellation.Cancel(); return row; };
        if (phase == "setter") f.AfterSet = cancellation.Cancel;
        if (phase == "wait") f.BeforeWait = cancellation.Cancel;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(f.Run);
        Assert.Equal(phase is "wait" or "setter" ? 1 : 0, f.Sets);
    }

    /// <summary>Missing foreground closes the finite read window without another setter.</summary>
    [Fact]
    public async Task ConfirmationTimeoutIsBounded()
    {
        var f = new Focus { DelayedReads = 1000 };
        var error = await Assert.ThrowsAsync<InvalidOperationException>(f.Run);
        Assert.Equal("desktop_startup_foreground_unconfirmed", error.Message);
        Assert.Equal(1, f.Sets); Assert.InRange(f.Reads, 2, 22); Assert.Equal(11000, f.Now);
    }

    /// <summary>A query that finishes past the confirmation deadline cannot grant readiness.</summary>
    [Fact]
    public async Task LateForegroundSnapshotCannotAttach()
    {
        var f = new Focus();
        f.Transform = (index, row) => { if (index > 1) f.Now += 1001; return row; };
        await Assert.ThrowsAsync<InvalidOperationException>(f.Run);
        Assert.Equal(1, f.Sets); Assert.Equal(0, f.Waits);
    }

    /// <summary>Busy admission rejects immediately and cannot release another task's gate.</summary>
    [Fact]
    public async Task BusyTaskCannotEnterStartup()
    {
        using var gate = new SemaphoreSlim(0, 1); var calls = 0;
        await Assert.ThrowsAsync<InvalidOperationException>(() => GameRuntimeService.WithStartupTaskGateAsync(gate,
            _ => { calls++; return Task.FromResult(true); }, default));
        Assert.Equal(0, calls); Assert.Equal(0, gate.CurrentCount);
    }

    /// <summary>Cancelled admission owns no semaphore and invokes no startup callback.</summary>
    [Fact]
    public async Task CancelledTaskAdmissionDoesNotStart()
    {
        using var gate = new SemaphoreSlim(1, 1); using var cancellation = new CancellationTokenSource();
        cancellation.Cancel(); var calls = 0;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => GameRuntimeService.WithStartupTaskGateAsync(gate,
            _ => { calls++; return Task.FromResult(true); }, cancellation.Token));
        Assert.Equal(0, calls); Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>The same production gate encloses all successful focus observations and releases only after the callback returns.</summary>
    [Fact]
    public async Task TaskGateEnclosesSuccessfulFocus()
    {
        using var gate = new SemaphoreSlim(1, 1);
        var f = new Focus { DelayedReads = 2, Transform = (_, row) => { Assert.Equal(0, gate.CurrentCount); return row; } };
        Assert.True(await GameRuntimeService.WithStartupTaskGateAsync(gate, async _ =>
        { await f.Run(); Assert.Equal(0, gate.CurrentCount); return true; }, default));
        Assert.Equal(1, f.Sets); Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>Failure and cancellation retain the task gate until the startup callback's cleanup has returned.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public async Task TaskGateRemainsOwnedThroughCleanup(bool cancel)
    {
        using var gate = new SemaphoreSlim(1, 1); using var cancellation = new CancellationTokenSource();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var failure = new InvalidOperationException("synthetic startup failure"); var cleaned = false;
        var pending = GameRuntimeService.WithStartupTaskGateAsync<bool>(gate, async token =>
        {
            try { entered.SetResult(); await release.Task; token.ThrowIfCancellationRequested(); throw failure; }
            finally { cleaned = true; }
        }, cancellation.Token);
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        if (cancel) cancellation.Cancel();
        Assert.False(pending.IsCompleted); Assert.False(cleaned); Assert.Equal(0, gate.CurrentCount);
        release.SetResult();
        if (cancel) await Assert.ThrowsAnyAsync<OperationCanceledException>(async () => await pending);
        else Assert.Same(failure, await Assert.ThrowsAsync<InvalidOperationException>(async () => await pending));
        Assert.True(cleaned); Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>The real existing-runtime branch never invokes a provider; explicit focus is rejected while default remains idempotent.</summary>
    [Theory]
    [InlineData(false)] [InlineData(true)]
    public async Task ExistingRuntimeCannotBeRefocused(bool explicitStartup)
    {
        using var gate = new SemaphoreSlim(1, 1);
        var service = BareService(gate, Task.CompletedTask);
        // These inert shells own no resources; the branch under test only compares/returns the reference.
        var current = (GameRuntime)RuntimeHelpers.GetUninitializedObject(typeof(GameRuntime));
        Field(service, "_current", current);
        if (explicitStartup)
        {
            var error = await Assert.ThrowsAsync<InvalidOperationException>(() => Core(service, true));
            Assert.Equal("desktop_capture_start_requires_stopped_runtime", error.Message);
        }
        else Assert.Same(current, await Core(service, false));
        Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>A queued stop/restart invalidation is checked after both waits, before any provider/config/native dependency.</summary>
    [Theory]
    [InlineData(false, false)] [InlineData(false, true)]
    [InlineData(true, false)] [InlineData(true, true)]
    public async Task QueuedStartupCannotCrossStopOrRestart(bool waitingForStop, bool restart)
    {
        using var startGate = new SemaphoreSlim(waitingForStop ? 1 : 0, 1);
        var stopped = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var service = BareService(startGate, waitingForStop ? stopped.Task : Task.CompletedTask);
        var pending = Core(service, true);
        Assert.False(pending.IsCompleted);
        if (restart) Field(service, "_restartReserved", true); else Field(service, "_stopVersion", 1L);
        if (waitingForStop) stopped.SetResult(); else startGate.Release();
        Assert.Null(await pending.WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.Equal(1, startGate.CurrentCount);
    }

    /// <summary>Build only the fields reached by the real early-admission branches; native dependencies intentionally stay absent.</summary>
    private static GameRuntimeService BareService(SemaphoreSlim startGate, Task stopped)
    {
        var service = (GameRuntimeService)RuntimeHelpers.GetUninitializedObject(typeof(GameRuntimeService));
        Field(service, "_startLock", startGate); Field(service, "_stopTask", stopped);
        return service;
    }

    /// <summary>Set a test-owned private state without constructing WPF, a provider, or an input channel.</summary>
    private static void Field(object owner, string name, object value) => owner.GetType()
        .GetField(name, BindingFlags.NonPublic | BindingFlags.Instance)!.SetValue(owner, value);

    /// <summary>Invoke the exact private start-lock branch, stopping before any runtime publication.</summary>
    private static Task<GameRuntime?> Core(GameRuntimeService service, bool explicitStartup) =>
        (Task<GameRuntime?>)typeof(GameRuntimeService).GetMethod("StartCoreAsync", BindingFlags.Instance | BindingFlags.NonPublic)!
            .Invoke(service, [CancellationToken.None, 0L, explicitStartup])!;

    /// <summary>Deterministic injected boundaries execute the production focus algorithm without any Win32 import.</summary>
    private sealed class Focus
    {
        /// <summary>Fake monotonic milliseconds.</summary>
        public double Now = 10000;
        /// <summary>Observed production boundary counts.</summary>
        public int Reads, Sets, Waits;
        /// <summary>Number of post-call snapshots before foreground appears.</summary>
        public int DelayedReads;
        /// <summary>Initial foreground may already belong to the game.</summary>
        public bool InitiallyForeground;
        /// <summary>Native Boolean return used by the real algorithm.</summary>
        public bool SetterResult = true;
        /// <summary>Optional native error preserved by the algorithm.</summary>
        public Exception? SetterError;
        /// <summary>Optional field/time mutation at the native-read boundary.</summary>
        public Func<int, DesktopDcStartupFocus.Snapshot, DesktopDcStartupFocus.Snapshot>? Transform;
        /// <summary>Optional cancellation at the delay boundary.</summary>
        public Action? BeforeWait;
        /// <summary>Optional cancellation immediately after the native setter boundary.</summary>
        public Action? AfterSet;
        /// <summary>Caller-owned cancellation, never replaced by the fixture.</summary>
        public CancellationToken Token;

        /// <summary>Run against the actual fixed bounds and single-setter control flow.</summary>
        public Task Run() => DesktopDcStartupFocus.AcquireAsync(99, _ =>
        {
            Reads++;
            var foreground = InitiallyForeground || (Sets == 1 && Reads > DelayedReads + 1);
            var row = new DesktopDcStartupFocus.Snapshot(99, 27, 1234, "GenshinImpact", 3, 3, 31,
                "UnityWndClass", true, true, false, "WinSta0", "Default", "Default", foreground ? 99 : 88, foreground ? 27 : 31);
            return Transform?.Invoke(Reads, row) ?? row;
        }, _ => { Sets++; if (SetterError is not null) throw SetterError; AfterSet?.Invoke(); return SetterResult; }, () => Now,
        (milliseconds, token) => { Waits++; BeforeWait?.Invoke(); token.ThrowIfCancellationRequested(); Now += milliseconds; return Task.CompletedTask; }, Token);
    }
}
