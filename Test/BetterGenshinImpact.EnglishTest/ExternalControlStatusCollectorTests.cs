using System.Text.Json;
using System.Windows.Threading;
using BetterGenshinImpact.Service.ExternalControl;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Bound real WPF dispatcher reads without starting App, a game, an RDP session, or Windows input.</summary>
public sealed class ExternalControlStatusCollectorTests
{
    /// <summary>A completed fresh read preserves its readiness and exposes its collection state on the wire.</summary>
    [Fact]
    public async Task ResponsiveDispatcherReturnsFreshStatus()
    {
        using var host = new DispatcherThread();
        var status = await ExternalControlStatusCollector.ReadAsync(host.Dispatcher, ReadyStatus,
            new ExternalControlStatus(), CancellationToken.None);
        Assert.Equal("current", status.UiStatus);
        Assert.True(status.RuntimeRunning);
        Assert.False(status.TaskRunning);
        using var wire = JsonDocument.Parse(JsonSerializer.Serialize(status));
        Assert.Equal("current", wire.RootElement.GetProperty("uiStatus").GetString());
    }

    /// <summary>Timeout and caller cancellation abort queued reads, rather than accumulating stale callbacks.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task BlockedDispatcherAbortsQueuedCollection(bool cancel)
    {
        using var host = new DispatcherThread();
        using var release = new ManualResetEventSlim();
        using var cancellation = new CancellationTokenSource();
        var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var blocker = host.Dispatcher.InvokeAsync(() =>
        {
            entered.SetResult(true);
            release.Wait(TimeSpan.FromSeconds(10));
        });
        var collected = 0;
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            var pending = ExternalControlStatusCollector.ReadAsync(host.Dispatcher,
                () => { Interlocked.Increment(ref collected); return ReadyStatus(); }, ReadyStatus(),
                cancellation.Token, TimeSpan.FromMilliseconds(150));
            if (cancel) cancellation.Cancel();
            var result = await pending.WaitAsync(TimeSpan.FromSeconds(3));
            AssertUnavailable(result, cancel ? "cancelled" : "timeout");
            release.Set();
            await blocker.Task.WaitAsync(TimeSpan.FromSeconds(5));
            await host.Dispatcher.InvokeAsync(() => { }).Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(0, collected);
            var fresh = await ExternalControlStatusCollector.ReadAsync(host.Dispatcher, ReadyStatus,
                new ExternalControlStatus(), CancellationToken.None);
            Assert.Equal("current", fresh.UiStatus);
        }
        finally { release.Set(); }
    }

    /// <summary>An already-running read may finish late, but cannot hold a request indefinitely or return stale readiness.</summary>
    [Fact]
    public async Task InProgressCollectionTimesOutAndItsLateResultIsDiscarded()
    {
        using var host = new DispatcherThread();
        using var release = new ManualResetEventSlim();
        var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var pending = ExternalControlStatusCollector.ReadAsync(host.Dispatcher, () =>
        {
            entered.SetResult(true);
            release.Wait(TimeSpan.FromSeconds(10));
            return ReadyStatus();
        }, ReadyStatus(), CancellationToken.None, TimeSpan.FromMilliseconds(150));
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            var result = await pending.WaitAsync(TimeSpan.FromSeconds(3));
            AssertUnavailable(result, "timeout");
            release.Set();
            await host.Dispatcher.InvokeAsync(() => { }).Task.WaitAsync(TimeSpan.FromSeconds(5));
            AssertUnavailable(result, "timeout");
            var fresh = await ExternalControlStatusCollector.ReadAsync(host.Dispatcher,
                () => ReadyStatus() with { AutomationState = "stopped", RuntimeRunning = false },
                ReadyStatus(), CancellationToken.None);
            Assert.Equal("current", fresh.UiStatus);
            Assert.Equal("stopped", fresh.AutomationState);
            Assert.False(fresh.RuntimeRunning);
        }
        finally { release.Set(); }
    }

    /// <summary>A collection exception is observed and never converted into a cached ready state.</summary>
    [Fact]
    public async Task FailedCollectionReturnsUnknownReadiness()
    {
        using var host = new DispatcherThread();
        var result = await ExternalControlStatusCollector.ReadAsync(host.Dispatcher,
            () => throw new InvalidOperationException("synthetic read failure"), ReadyStatus(), CancellationToken.None);
        AssertUnavailable(result, "failed");
    }

    /// <summary>Shutdown or cancellation before dispatch requires no UI callback and keeps mutation acknowledgements possible.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task MissingDispatcherOrCancelledRequestCannotAdvertiseReadiness(bool cancelled)
    {
        using var cancellation = new CancellationTokenSource();
        if (cancelled) cancellation.Cancel();
        var result = await ExternalControlStatusCollector.ReadAsync(null,
            () => throw new InvalidOperationException("must not run"), ReadyStatus(), cancellation.Token);
        AssertUnavailable(result, cancelled ? "cancelled" : "unavailable");
    }

    /// <summary>Deliberately ready baseline demonstrates that fallback cannot accidentally retain old UI fields.</summary>
    private static ExternalControlStatus ReadyStatus() => new()
    {
        ProcessId = 123, InstanceNonce = "fixed-test-identity", UiStatus = "current", AutomationState = "game_ready",
        RuntimeRunning = true, TaskRunning = false, ChildSessionId = 3, ChildConnectedState = 1,
        ChildWindowMinimized = true, CaptureMode = "WindowsGraphicsCapture"
    };

    /// <summary>Identity remains usable for diagnosis while every UI-dependent ready claim is revoked.</summary>
    private static void AssertUnavailable(ExternalControlStatus status, string state)
    {
        Assert.Equal(state, status.UiStatus);
        Assert.Equal("unresponsive", status.AutomationState);
        Assert.False(status.RuntimeRunning);
        Assert.True(status.TaskRunning);
        Assert.Null(status.ChildSessionId);
        Assert.Equal(0, status.ChildConnectedState);
        Assert.False(status.ChildWindowMinimized);
        Assert.Empty(status.CaptureMode);
        Assert.Equal(123, status.ProcessId);
        Assert.Equal("fixed-test-identity", status.InstanceNonce);
        Assert.False(string.IsNullOrEmpty(status.AutomationError));
    }

    /// <summary>Own a real STA message loop with no Application instance or visible window.</summary>
    private sealed class DispatcherThread : IDisposable
    {
        /// <summary>Only this fixture's headless background thread is stopped during cleanup.</summary>
        private readonly Thread _thread;
        /// <summary>Dispatcher initialized on the fixture's STA thread.</summary>
        public Dispatcher Dispatcher { get; }

        /// <summary>Start a message loop and wait until it can accept queued collection callbacks.</summary>
        public DispatcherThread()
        {
            var ready = new TaskCompletionSource<Dispatcher>(TaskCreationOptions.RunContinuationsAsynchronously);
            _thread = new Thread(() =>
            {
                ready.SetResult(System.Windows.Threading.Dispatcher.CurrentDispatcher);
                System.Windows.Threading.Dispatcher.Run();
            }) { IsBackground = true, Name = "ExternalControl status test dispatcher" };
            _thread.SetApartmentState(ApartmentState.STA);
            _thread.Start();
            Dispatcher = ready.Task.WaitAsync(TimeSpan.FromSeconds(5)).GetAwaiter().GetResult();
        }

        /// <summary>Finish the fixture's message loop after test-owned blocked callbacks are released.</summary>
        public void Dispose()
        {
            Dispatcher.BeginInvokeShutdown(DispatcherPriority.Send);
            Assert.True(_thread.Join(TimeSpan.FromSeconds(5)), "Headless test dispatcher did not stop.");
        }
    }
}
