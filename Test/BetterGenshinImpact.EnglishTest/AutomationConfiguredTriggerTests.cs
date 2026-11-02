using System.Collections;
using System.Reflection;
using System.Text.Json;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Mask;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.Service.ExternalControl;
using BetterGenshinImpact.Service.Instance;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using Fischless.GameCapture;
using Microsoft.Extensions.Logging.Abstractions;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Actual dispatcher policy with inert triggers and runtimes; no timer, App, window, capture backend, or input is started.</summary>
public sealed class AutomationConfiguredTriggerTests
{
    /// <summary>Only an automation child suppresses preferences; ordinary primary, child, and WebView behavior stays intact.</summary>
    [Theory]
    [InlineData(false, BetterGiInstanceType.Primary, false)]
    [InlineData(true, BetterGiInstanceType.Primary, false)]
    [InlineData(false, BetterGiInstanceType.ChildSession, false)]
    [InlineData(true, BetterGiInstanceType.ChildSession, true)]
    [InlineData(false, BetterGiInstanceType.WebView, false)]
    [InlineData(true, BetterGiInstanceType.WebView, false)]
    public void StartupContextControlsConfiguredTriggersWithoutChangingPreferences(
        bool automationMode, BetterGiInstanceType instanceType, bool suppressed)
    {
        var config = new AllConfig(); config.AutoSkipConfig.Enabled = true;
        var dispatcher = Create(config, automationMode, instanceType);
        using var timer = Timer(dispatcher);
        var trigger = new RecordingTrigger(config); Install(dispatcher, trigger);
        Assert.Equal(suppressed, dispatcher.ConfiguredTriggersSuppressed);
        Assert.Equal(suppressed ? 0 : 1, Sync(dispatcher).Count);
        Assert.Equal(suppressed ? 0 : 1, trigger.Enabled);
        Assert.True(config.AutoSkipConfig.Enabled);
        if (!suppressed)
        {
            config.AutoSkipConfig.Enabled = false;
            Assert.Empty(Sync(dispatcher)); Assert.Equal(1, trigger.Disabled);
        }
    }

    /// <summary>An explicit task lease still works, then EndTask and later runtime slots cannot restore configured input.</summary>
    [Fact]
    public void TaskLeaseWorksButTaskEndAndReplacementSlotsRemainSuppressed()
    {
        var config = new AllConfig(); config.AutoSkipConfig.Enabled = true;
        var dispatcher = Create(config, true, BetterGiInstanceType.ChildSession);
        using var timer = Timer(dispatcher);
        var first = new RecordingTrigger(config); Install(dispatcher, first);
        Assert.Empty(Sync(dispatcher)); Assert.Equal(0, first.Enabled);
        dispatcher.BeginTask();
        using (Lease(dispatcher, first.GetType()))
        {
            Assert.Single(Sync(dispatcher)); Assert.Equal(1, first.Enabled);
            dispatcher.EndTask();
            Assert.Empty(Sync(dispatcher)); Assert.Equal(1, first.Disabled);
        }
        Assert.Empty(Sync(dispatcher));
        var rebound = new RecordingTrigger(config); Install(dispatcher, rebound);
        dispatcher.BeginTask(); dispatcher.EndTask();
        Assert.Empty(Sync(dispatcher)); Assert.Equal(0, rebound.Enabled);
        Assert.True(dispatcher.ConfiguredTriggersSuppressed);
        Assert.True(config.AutoSkipConfig.Enabled);
    }

    /// <summary>Real Tick keeps capture and liveness housekeeping both before and after the owned task retires.</summary>
    [Fact]
    public void ActualTickPreservesCaptureAndLivenessAfterTaskEnd()
    {
        var info = new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1);
        using var template = TestGameRuntime.Create(info);
        var capture = new CountingCapture();
        using var runtime = new GameRuntime(template.Kind, template.Window, capture, template.Input, info,
            template.MaskWindowDrawingBoard, template.MaskWindowMapState);
        var mask = new RecordingMaskHost();
        var config = new AllConfig(); config.AutoSkipConfig.Enabled = true;
        var dispatcher = Create(config, true, BetterGiInstanceType.ChildSession, mask);
        using var timer = Timer(dispatcher);
        Set(dispatcher, "_runtime", runtime);
        var trigger = new RecordingTrigger(config); Install(dispatcher, trigger);
        dispatcher.Tick(null, EventArgs.Empty);
        Assert.Equal(1, capture.Calls); Assert.True(mask.Reports > 0);
        dispatcher.BeginTask(); dispatcher.EndTask();
        dispatcher.Tick(null, EventArgs.Empty);
        Assert.Equal(2, capture.Calls); Assert.Equal(0, trigger.Enabled); Assert.Equal(0, trigger.Captures);
        capture.Running = false;
        var stopped = 0; dispatcher.UiTaskStopTickEvent += (_, _) => stopped++;
        dispatcher.Tick(null, EventArgs.Empty);
        Assert.Equal(1, stopped); Assert.False(mask.Last.IsCapturing);
        Assert.True(dispatcher.ConfiguredTriggersSuppressed); Assert.True(config.AutoSkipConfig.Enabled);
    }

    /// <summary>The added wire fields state a configured-trigger policy, not global input suppression or task retirement.</summary>
    [Fact]
    public void StatusProofRetainsTypedVersionAndPolicyWithoutInventingIdle()
    {
        var dispatcher = Create(new AllConfig(), true, BetterGiInstanceType.ChildSession);
        using var timer = Timer(dispatcher);
        var status = new ExternalControlStatus
        {
            ConfiguredTriggerPolicyVersion = TaskTriggerDispatcher.ConfiguredTriggerPolicyVersion,
            ConfiguredTriggersSuppressed = dispatcher.ConfiguredTriggersSuppressed,
            TaskRunning = true,
            RuntimeRunning = true
        };
        using var wire = JsonDocument.Parse(JsonSerializer.Serialize(status));
        Assert.Equal(1, wire.RootElement.GetProperty("configuredTriggerPolicyVersion").GetInt32());
        Assert.True(wire.RootElement.GetProperty("configuredTriggersSuppressed").GetBoolean());
        Assert.True(wire.RootElement.GetProperty("taskRunning").GetBoolean());
        Assert.True(wire.RootElement.GetProperty("runtimeRunning").GetBoolean());
    }

    /// <summary>Construct the actual dispatcher with explicit inert startup facts.</summary>
    private static TaskTriggerDispatcher Create(AllConfig config, bool automationMode, BetterGiInstanceType type,
        RecordingMaskHost? mask = null) =>
        new(NullLogger<TaskTriggerDispatcher>.Instance, null!, mask ?? new RecordingMaskHost(), config, automationMode, type);

    /// <summary>Own and dispose the never-started timer without invoking production UI teardown.</summary>
    private static System.Timers.Timer Timer(TaskTriggerDispatcher dispatcher) =>
        (System.Timers.Timer)Get(dispatcher, "_timer");

    /// <summary>Read only an actual private dispatcher fixture seam.</summary>
    private static object Get(TaskTriggerDispatcher dispatcher, string name) =>
        typeof(TaskTriggerDispatcher).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(dispatcher)!;

    /// <summary>Install an inert runtime or slot list; no game or timer is created.</summary>
    private static void Set(TaskTriggerDispatcher dispatcher, string name, object value) =>
        typeof(TaskTriggerDispatcher).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(dispatcher, value);

    /// <summary>Exercise the exact production activation and retirement rules synchronously.</summary>
    private static List<ITaskTrigger> Sync(TaskTriggerDispatcher dispatcher) =>
        (List<ITaskTrigger>)typeof(TaskTriggerDispatcher).GetMethod("SyncTriggerStates", BindingFlags.Instance | BindingFlags.NonPublic)!
            .Invoke(dispatcher, [false])!;

    /// <summary>Model Start's fresh inactive slots without constructing OCR triggers or starting its timer.</summary>
    private static void Install(TaskTriggerDispatcher dispatcher, RecordingTrigger trigger)
    {
        var type = typeof(TaskTriggerDispatcher).GetNestedType("TriggerSlot", BindingFlags.NonPublic)!;
        var slots = (IList)Activator.CreateInstance(typeof(List<>).MakeGenericType(type))!;
        slots.Add(Activator.CreateInstance(type, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
            null, [trigger], null)!);
        Set(dispatcher, "_slots", slots);
    }

    /// <summary>Install the real private task-lease type for the inert trigger, preserving the existing public trigger allowlist.</summary>
    private static IDisposable Lease(TaskTriggerDispatcher dispatcher, Type triggerType)
    {
        var type = typeof(TaskTriggerDispatcher).GetNestedType("TriggerLease", BindingFlags.NonPublic)!;
        var lease = (IDisposable)Activator.CreateInstance(type, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
            null, [dispatcher, triggerType, null], null)!;
        ((IList)Get(dispatcher, "_leases")).Add(lease);
        return lease;
    }

    /// <summary>Count activation without loading AutoSkip models, images, or game input.</summary>
    private sealed class RecordingTrigger(AllConfig config) : ITaskTrigger
    {
        /// <summary>Number of activation transitions.</summary>
        internal int Enabled;
        /// <summary>Number of retirement transitions.</summary>
        internal int Disabled;
        /// <summary>Number of pixel callbacks.</summary>
        internal int Captures;
        /// <inheritdoc />
        public string Name => "configured-auto-skip-probe";
        /// <inheritdoc />
        public int Priority => 0;
        /// <inheritdoc />
        public bool IsEnabledByConfig => config.AutoSkipConfig.Enabled;
        /// <inheritdoc />
        public bool IsExclusive => false;
        /// <inheritdoc />
        public bool IsBackgroundRunning => true;
        /// <inheritdoc />
        public void OnEnabled(object? options) => Enabled++;
        /// <inheritdoc />
        public void OnDisabled() => Disabled++;
        /// <inheritdoc />
        public void OnCapture(CaptureContent content) => Captures++;
    }

    /// <summary>Count capture requests without allocating pixels or starting a native backend.</summary>
    private sealed class CountingCapture : IGameCapture
    {
        /// <summary>Mutable synthetic runtime lifecycle.</summary>
        internal bool Running = true;
        /// <summary>Number of capture requests.</summary>
        internal int Calls;
        /// <inheritdoc />
        public bool IsCapturing => Running;
        /// <inheritdoc />
        public GameCaptureFrame? Capture() { Calls++; return null; }
        /// <inheritdoc />
        public void Start(nint window, Dictionary<string, object>? settings = null) => Running = true;
        /// <inheritdoc />
        public void Stop() => Running = false;
        /// <inheritdoc />
        public void Dispose() { }
    }

    /// <summary>Retain housekeeping evidence without a WPF window or UI event source.</summary>
    private sealed class RecordingMaskHost : IMaskWindowHost
    {
        /// <summary>Number of game-window reports.</summary>
        internal int Reports;
        /// <summary>Last lifecycle report.</summary>
        internal GameWindowState Last;
        /// <inheritdoc />
        public void ReportGameWindow(GameWindowState state) { Reports++; Last = state; }
        /// <inheritdoc />
        public MaskWindowState State => default;
        /// <inheritdoc />
        public event EventHandler<MaskWindowState>? StateChanged { add { } remove { } }
        /// <inheritdoc />
        public void Attach(nint handle) { }
        /// <inheritdoc />
        public void Detach() { }
        /// <inheritdoc />
        public void Close() { }
    }
}
