using System.Collections;
using System.Reflection;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Mask;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using Fischless.GameCapture;
using Microsoft.Extensions.Logging.Abstractions;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Managed gate and synthetic dispatcher tests: no actual timer, game, capture, input or App startup.</summary>
public sealed class TaskTimerCapturePauseTests
{
    /// <summary>An already-running tick must finish, and trigger disable must complete, before task admission.</summary>
    [Fact]
    public async Task DrainsTickAndFinishesDisableBeforeLeaseReturns()
    {
        var gate = new object(); var runtime = new object(); var coordinator = new TaskTimerCapturePause(gate);
        using var holder = new HeldTick(gate);
        var disabled = false;
        var pending = coordinator.AcquireAsync(runtime, () => true, () =>
        {
            Assert.True(Monitor.IsEntered(gate)); disabled = true;
        }, CancellationToken.None);
        Assert.False(pending.IsCompleted); Assert.False(disabled); Assert.False(coordinator.IsPausedFor(runtime));
        holder.Release();
        using var lease = await pending;
        Assert.True(disabled); Assert.True(coordinator.IsPausedFor(runtime));
    }

    /// <summary>Cancellation finishes the real waiter while the tick remains blocked; it cannot later install a lease.</summary>
    [Fact]
    public async Task CancellationDoesNotLeaveAnOrphanedWaiter()
    {
        var gate = new object(); var runtime = new object(); var coordinator = new TaskTimerCapturePause(gate);
        using var holder = new HeldTick(gate); using var stop = new CancellationTokenSource();
        var pending = coordinator.AcquireAsync(runtime, () => true, () => throw new Exception("must not prepare"), stop.Token);
        stop.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => pending);
        Assert.False(coordinator.IsPausedFor(runtime));
        holder.Release();
        using var recovered = await coordinator.AcquireAsync(runtime, () => true, () => { }, CancellationToken.None);
        Assert.True(coordinator.IsPausedFor(runtime));
    }

    /// <summary>Timeout likewise retires the waiter before the held tick is released.</summary>
    [Fact]
    public async Task BoundedDrainTimeoutCannotPauseLaterWork()
    {
        var gate = new object(); var runtime = new object(); var coordinator = new TaskTimerCapturePause(gate);
        using var holder = new HeldTick(gate);
        var pending = coordinator.AcquireAsync(runtime, () => true, () => throw new Exception("must not prepare"),
            CancellationToken.None, TimeSpan.FromMilliseconds(50));
        var error = await Assert.ThrowsAsync<TimeoutException>(() => pending);
        Assert.Equal("timer_capture_drain_timeout", error.Message); Assert.False(coordinator.IsPausedFor(runtime));
        holder.Release();
        using var recovered = await coordinator.AcquireAsync(runtime, () => true, () => { }, CancellationToken.None);
    }

    /// <summary>Runtime replacement during draining rejects the old task before preparation or input.</summary>
    [Fact]
    public async Task RuntimeReplacementWhileWaitingRejectsAdmission()
    {
        var gate = new object(); var runtime = new object(); object? current = runtime;
        var coordinator = new TaskTimerCapturePause(gate); using var holder = new HeldTick(gate);
        var prepared = false;
        var pending = coordinator.AcquireAsync(runtime, () => ReferenceEquals(Volatile.Read(ref current), runtime),
            () => prepared = true, CancellationToken.None);
        Volatile.Write(ref current, new object()); holder.Release();
        await Assert.ThrowsAsync<InvalidOperationException>(() => pending);
        Assert.False(prepared); Assert.False(coordinator.IsPausedFor(runtime));
    }

    /// <summary>Trigger cleanup cannot turn cancellation/replacement/failure into an admitted task.</summary>
    [Theory]
    [InlineData("cancel")]
    [InlineData("replace")]
    [InlineData("throw")]
    public async Task PreparationFailureNeverInstallsLease(string failure)
    {
        var runtime = new object(); var current = true; var coordinator = new TaskTimerCapturePause(new object());
        using var stop = new CancellationTokenSource();
        var pending = coordinator.AcquireAsync(runtime, () => current, () =>
        {
            if (failure == "cancel") stop.Cancel();
            if (failure == "replace") current = false;
            if (failure == "throw") throw new InvalidOperationException("disable_failed");
        }, stop.Token);
        await Assert.ThrowsAnyAsync<Exception>(() => pending);
        Assert.False(coordinator.IsPausedFor(runtime));
    }

    /// <summary>Only the owning lease can clear its pause, and that pause never applies to a replacement runtime.</summary>
    [Fact]
    public async Task LeaseOwnershipAndRuntimeIdentitySurviveRepeatedDisposal()
    {
        var first = new object(); var second = new object(); var coordinator = new TaskTimerCapturePause(new object());
        var old = await coordinator.AcquireAsync(first, () => true, () => { }, CancellationToken.None);
        Assert.True(coordinator.IsPausedFor(first)); Assert.False(coordinator.IsPausedFor(second));
        await Assert.ThrowsAsync<InvalidOperationException>(() => coordinator.AcquireAsync(second, () => true, () => { }, CancellationToken.None));
        old.Dispose();
        using var current = await coordinator.AcquireAsync(second, () => true, () => { }, CancellationToken.None);
        old.Dispose();
        Assert.False(coordinator.IsPausedFor(first)); Assert.True(coordinator.IsPausedFor(second));
    }

    /// <summary>TaskRunner releases scopes after native/input cleanup, even when cleanup or a scope throws.</summary>
    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public void CleanupPreservesOrderAndCancellationScope(bool failCleanup, bool failLease)
    {
        var order = new List<string>();
        using var taskSemaphore = new SemaphoreSlim(0, 1);
        var capture = new CallbackLease(() => { Assert.Equal(0, taskSemaphore.CurrentCount); order.Add("capture"); if (failLease) throw new InvalidOperationException(); });
        var cancel = new CallbackLease(() => { Assert.Equal(0, taskSemaphore.CurrentCount); order.Add("cancel"); });
        try
        {
            TaskRunner.EndWithCaptureScopes(() => { order.Add("input_cleanup"); if (failCleanup) throw new InvalidOperationException(); }, capture, cancel);
        }
        catch (InvalidOperationException) when (failCleanup || failLease) { }
        finally { taskSemaphore.Release(); }
        Assert.Equal(new[] { "input_cleanup", "capture", "cancel" }, order);
        Assert.Equal(1, taskSemaphore.CurrentCount);
    }

    /// <summary>Exercise the real Tick: trigger disable is synchronous, housekeeping remains, and shared capture resumes.</summary>
    [Fact]
    public async Task ActualDispatcherSkipsOnlyCaptureAndPreservesLiveness()
    {
        var info = new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1);
        using var template = TestGameRuntime.Create(info);
        var capture = new CountingCapture();
        using var runtime = new GameRuntime(template.Kind, template.Window, capture, template.Input, info,
            template.MaskWindowDrawingBoard, template.MaskWindowMapState);
        var mask = new RecordingMaskHost(); var config = new AllConfig(); config.AutoSkipConfig.Enabled = false;
        var dispatcher = new TaskTriggerDispatcher(NullLogger<TaskTriggerDispatcher>.Instance, null!, mask, config);
        using var timer = GetUnstartedTimer(dispatcher);
        SetField(dispatcher, "_runtime", runtime);
        var trigger = new RecordingTrigger(); InstallActiveTrigger(dispatcher, trigger);
        dispatcher.BeginTask();
        using (await dispatcher.PauseTimerCaptureForTaskAsync(runtime, CancellationToken.None))
        {
            Assert.Equal(1, trigger.Disabled); Assert.Equal(0, capture.Calls);
            dispatcher.Tick(null, EventArgs.Empty);
            Assert.True(mask.Reports > 0); Assert.Equal(0, capture.Calls); Assert.Equal(0, trigger.Captures);
            capture.Running = false; var stopped = 0;
            dispatcher.UiTaskStopTickEvent += (_, _) => stopped++;
            dispatcher.Tick(null, EventArgs.Empty);
            Assert.Equal(1, stopped); Assert.False(mask.Last.IsCapturing); Assert.Equal(0, capture.Calls);
            capture.Running = true;
        }
        dispatcher.Tick(null, EventArgs.Empty);
        Assert.Equal(1, capture.Calls); Assert.Equal(1, trigger.Disabled);
        dispatcher.EndTask();
    }

    /// <summary>Task-specific suppression requires task mode without explicitly requested timer triggers.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DispatcherRejectsMissingOrConflictingTaskOwnership(bool hasTriggerLease)
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1));
        var dispatcher = new TaskTriggerDispatcher(NullLogger<TaskTriggerDispatcher>.Instance, null!, new RecordingMaskHost(), new AllConfig());
        using var timer = GetUnstartedTimer(dispatcher);
        SetField(dispatcher, "_runtime", runtime);
        if (hasTriggerLease) dispatcher.BeginTask();
        using var triggerLease = hasTriggerLease ? dispatcher.AddTrigger("AutoPick", null) : null;
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => dispatcher.PauseTimerCaptureForTaskAsync(runtime, CancellationToken.None));
        Assert.Equal("timer_capture_requires_exclusive_task", error.Message);
    }

    /// <summary>Admission fails after any disable failure, but all remaining triggers still receive cleanup.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task DispatcherDisableFailureRejectsAdmissionAfterRemainingCleanup(bool tickFirst)
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1));
        var config = new AllConfig(); config.AutoSkipConfig.Enabled = false;
        var dispatcher = new TaskTriggerDispatcher(NullLogger<TaskTriggerDispatcher>.Instance, null!, new RecordingMaskHost(), config);
        using var timer = GetUnstartedTimer(dispatcher);
        SetField(dispatcher, "_runtime", runtime);
        var failing = new RecordingTrigger(failDisable: true); var other = new RecordingTrigger();
        InstallActiveTrigger(dispatcher, failing, other); dispatcher.BeginTask();
        if (tickFirst) dispatcher.Tick(null, EventArgs.Empty);
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => dispatcher.PauseTimerCaptureForTaskAsync(runtime, CancellationToken.None));
        Assert.Equal("timer_capture_trigger_disable_failed", error.Message);
        Assert.Equal(1, failing.Disabled); Assert.Equal(1, other.Disabled);
        var pause = (TaskTimerCapturePause)typeof(TaskTriggerDispatcher).GetField("_taskCapturePause", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(dispatcher)!;
        Assert.False(pause.IsPausedFor(runtime));
        dispatcher.BeginTask();
        await Assert.ThrowsAsync<InvalidOperationException>(() => dispatcher.PauseTimerCaptureForTaskAsync(runtime, CancellationToken.None));
        Assert.Equal(1, failing.Disabled); // A new task boundary neither retries nor erases failed cleanup.

        failing.FailDisable = false;
        dispatcher.EndTask(); dispatcher.Tick(null, EventArgs.Empty); // Actual re-enable, not an evidence reset.
        dispatcher.BeginTask(); dispatcher.Tick(null, EventArgs.Empty); // The next actual disable succeeds.
        using var recovered = await dispatcher.PauseTimerCaptureForTaskAsync(runtime, CancellationToken.None);
        Assert.Equal(2, failing.Disabled); Assert.True(pause.IsPausedFor(runtime));
    }

    /// <summary>Discarding an inactive failed trigger cannot erase uncertainty or retain arbitrary exception/trigger objects.</summary>
    [Fact]
    public async Task RetiredDisableFailureKeepsBoundedAdmissionEvidence()
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1));
        var config = new AllConfig(); config.AutoSkipConfig.Enabled = false;
        var dispatcher = new TaskTriggerDispatcher(NullLogger<TaskTriggerDispatcher>.Instance, null!, new RecordingMaskHost(), config);
        using var timer = GetUnstartedTimer(dispatcher);
        SetField(dispatcher, "_runtime", runtime);
        var failing = new RecordingTrigger(failDisable: true); InstallActiveTrigger(dispatcher, failing);
        dispatcher.BeginTask(); dispatcher.Tick(null, EventArgs.Empty);
        var slots = (IList)typeof(TaskTriggerDispatcher).GetField("_slots", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(dispatcher)!;
        var retired = (IList)typeof(TaskTriggerDispatcher).GetField("_retiredSlots", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(dispatcher)!;
        retired.Add(slots[0]); slots.Clear();
        await Assert.ThrowsAsync<InvalidOperationException>(() => dispatcher.PauseTimerCaptureForTaskAsync(runtime, CancellationToken.None));
        Assert.Empty(retired);
        var summary = Assert.IsType<string>(typeof(TaskTriggerDispatcher).GetField("_retiredDisableFailure", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(dispatcher));
        Assert.True(summary.Length <= 290); Assert.Contains("synthetic_disable_failed", summary);
        dispatcher.BeginTask();
        await Assert.ThrowsAsync<InvalidOperationException>(() => dispatcher.PauseTimerCaptureForTaskAsync(runtime, CancellationToken.None));
        Assert.Equal(1, failing.Disabled);
    }

    /// <summary>Bind synthetic state without Start(), which intentionally creates production triggers and an actual timer.</summary>
    private static void SetField(TaskTriggerDispatcher dispatcher, string field, object value) =>
        typeof(TaskTriggerDispatcher).GetField(field, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(dispatcher, value);

    /// <summary>Dispose only the never-started test timer; production Stop() also manages real runtime/UI services.</summary>
    private static System.Timers.Timer GetUnstartedTimer(TaskTriggerDispatcher dispatcher) =>
        (System.Timers.Timer)typeof(TaskTriggerDispatcher).GetField("_timer", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(dispatcher)!;

    /// <summary>Install one previously active fake trigger to prove the actual state-transition path is drained.</summary>
    private static void InstallActiveTrigger(TaskTriggerDispatcher dispatcher, params RecordingTrigger[] triggers)
    {
        var type = typeof(TaskTriggerDispatcher).GetNestedType("TriggerSlot", BindingFlags.NonPublic)!;
        var slots = (IList)Activator.CreateInstance(typeof(List<>).MakeGenericType(type))!;
        foreach (var trigger in triggers)
        {
            var slot = Activator.CreateInstance(type, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic, null, [trigger], null)!;
            type.GetProperty("IsActive")!.SetValue(slot, true); slots.Add(slot);
        }
        SetField(dispatcher, "_slots", slots);
    }

    /// <summary>Hold the tick monitor on a dedicated managed thread, avoiding thread-affine monitor ownership across awaits.</summary>
    private sealed class HeldTick : IDisposable
    {
        /// <summary>Signals that the simulated old tick owns the gate.</summary>
        private readonly ManualResetEventSlim _entered = new();
        /// <summary>Explicitly lets the simulated tick finish.</summary>
        private readonly ManualResetEventSlim _release = new();
        /// <summary>Dedicated monitor-owning thread.</summary>
        private readonly Thread _thread;
        /// <summary>Start the simulated tick before returning to the test.</summary>
        internal HeldTick(object gate)
        {
            _thread = new Thread(() => { lock (gate) { _entered.Set(); _release.Wait(); } }) { IsBackground = true };
            _thread.Start(); Assert.True(_entered.Wait(TimeSpan.FromSeconds(5)));
        }
        /// <summary>Release and join once or repeatedly without leaving a waiter behind.</summary>
        internal void Release() { _release.Set(); Assert.True(_thread.Join(TimeSpan.FromSeconds(5))); }
        /// <summary>Always drain the simulated tick, including assertion failures.</summary>
        public void Dispose() { Release(); _entered.Dispose(); _release.Dispose(); }
    }

    /// <summary>Observe cleanup order without touching real input or task ownership.</summary>
    private sealed class CallbackLease(Action callback) : IDisposable
    {
        /// <summary>Execute the test callback on release.</summary>
        public void Dispose() => callback();
    }

    /// <summary>Count captures; return no pixels so the shared-path check performs no recognition.</summary>
    private sealed class CountingCapture : IGameCapture
    {
        /// <summary>Mutable synthetic lifecycle status.</summary>
        internal bool Running = true;
        /// <summary>Number of actual capture calls.</summary>
        internal int Calls;
        /// <summary>No native backend is involved.</summary>
        public bool IsCapturing => Running;
        /// <summary>Return no frame after recording the call.</summary>
        public GameCaptureFrame? Capture() { Calls++; return null; }
        /// <summary>Test lifecycle stub.</summary>
        public void Start(nint window, Dictionary<string, object>? settings = null) => Running = true;
        /// <summary>Test lifecycle stub.</summary>
        public void Stop() => Running = false;
        /// <summary>Nothing native is owned.</summary>
        public void Dispose() { }
    }

    /// <summary>Capture housekeeping observations without creating any WPF window.</summary>
    private sealed class RecordingMaskHost : IMaskWindowHost
    {
        /// <summary>Number of housekeeping reports.</summary>
        internal int Reports;
        /// <summary>Last game lifecycle observation.</summary>
        internal GameWindowState Last;
        /// <summary>Observe a report without UI work.</summary>
        public void ReportGameWindow(GameWindowState state) { Reports++; Last = state; }
        /// <summary>No window state is needed.</summary>
        public MaskWindowState State => default;
        /// <summary>No UI event source is installed.</summary>
        public event EventHandler<MaskWindowState>? StateChanged { add { } remove { } }
        /// <summary>No native attachment.</summary>
        public void Attach(nint handle) { }
        /// <summary>No native attachment.</summary>
        public void Detach() { }
        /// <summary>No window is owned.</summary>
        public void Close() { }
    }

    /// <summary>A formerly active trigger whose cleanup and capture calls can be independently counted.</summary>
    private sealed class RecordingTrigger(bool failDisable = false) : ITaskTrigger
    {
        /// <summary>Permit an actual later cleanup to succeed, rather than resetting the dispatcher's evidence.</summary>
        internal bool FailDisable { get; set; } = failDisable;
        /// <summary>Number of stop transitions.</summary>
        internal int Disabled;
        /// <summary>Number of pixel callbacks.</summary>
        internal int Captures;
        /// <summary>Stable synthetic name.</summary>
        public string Name => "synthetic";
        /// <summary>Only one test trigger exists.</summary>
        public int Priority => 0;
        /// <summary>Task mode must override this otherwise enabled trigger.</summary>
        public bool IsEnabledByConfig => true;
        /// <summary>No special routing.</summary>
        public bool IsExclusive => false;
        /// <summary>Record the synchronous disable transition.</summary>
        public void OnDisabled() { Disabled++; if (FailDisable) throw new InvalidOperationException("synthetic_disable_failed"); }
        /// <summary>Record forbidden pixel callbacks during the pause.</summary>
        public void OnCapture(CaptureContent content) => Captures++;
    }
}
