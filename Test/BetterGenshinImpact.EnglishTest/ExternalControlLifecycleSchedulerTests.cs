using System.Text.Json;
using System.Windows.Threading;
using BetterGenshinImpact.Service.ExternalControl;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise lifecycle scheduling and bounded acknowledgements on a headless real STA dispatcher.</summary>
public sealed class ExternalControlLifecycleSchedulerTests
{
    /// <summary>A synchronous native-style stop can outlive the request budget without delaying admission or its response.</summary>
    [Fact]
    public async Task AcknowledgesWhileSynchronousStopOutlivesRequestBudget()
    {
        using var host = new DispatcherThread();
        using var release = new ManualResetEventSlim();
        using var requestBudget = new CancellationTokenSource();
        using var lifecycle = new CancellationTokenSource();
        var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        Task? tracked = null;
        var starts = 0;
        try
        {
            await host.Dispatcher.InvokeAsync(() =>
            {
                tracked = ExternalControlLifecycleScheduler.RunAsync(host.Dispatcher, token =>
                {
                    host.Dispatcher.VerifyAccess();
                    Interlocked.Increment(ref starts);
                    entered.SetResult(true);
                    Assert.True(release.Wait(TimeSpan.FromSeconds(10)), "Test teardown was not released.");
                    token.ThrowIfCancellationRequested();
                    return Task.CompletedTask;
                }, lifecycle.Token);
                // This is the admission boundary that previously executed native work inline.
                Assert.False(entered.Task.IsCompleted);
                Assert.False(tracked.IsCompleted);
            }).Task.WaitAsync(TimeSpan.FromSeconds(5));
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));

            // Shrink only the existing status-collection budget; no real five-second sleep
            // or application/game runtime is needed to reproduce a blocked dispatcher.
            var status = await ExternalControlStatusCollector.ReadAsync(host.Dispatcher,
                () => throw new InvalidOperationException("Blocked UI must not advertise readiness."),
                new ExternalControlStatus { ProcessId = 123 }, requestBudget.Token,
                TimeSpan.FromMilliseconds(30)).WaitAsync(TimeSpan.FromSeconds(3));
            var response = new ExternalControlResponse
            {
                RequestId = Guid.NewGuid(), Success = true, Status = status
            };
            requestBudget.Token.ThrowIfCancellationRequested();
            using var wire = JsonDocument.Parse(ExternalControlProtocol.SerializeResponse(response));
            Assert.True(wire.RootElement.GetProperty("success").GetBoolean());
            Assert.Equal("timeout", status.UiStatus);
            Assert.True(status.TaskRunning);
            Assert.False(status.RuntimeRunning);
            Assert.False(tracked!.IsCompleted);

            // Expire the simulated pipe budget after the response while teardown remains
            // blocked. It must neither cancel the admitted operation nor discard its task.
            requestBudget.Cancel();
            Assert.False(lifecycle.IsCancellationRequested);
            Assert.False(tracked.IsCompleted);
            release.Set();
            await tracked.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(1, starts);
        }
        finally { release.Set(); }
    }

    /// <summary>A cancelled queued start does no native work when the dispatcher later reaches it.</summary>
    [Fact]
    public async Task CancelledQueuedStartNeverInvokesOperation()
    {
        using var host = new DispatcherThread();
        using var cancellation = new CancellationTokenSource();
        Task? tracked = null;
        var invoked = false;
        await host.Dispatcher.InvokeAsync(() =>
        {
            tracked = ExternalControlLifecycleScheduler.RunAsync(host.Dispatcher,
                _ => { invoked = true; return Task.CompletedTask; }, cancellation.Token);
            cancellation.Cancel();
            Assert.False(invoked);
        }).Task.WaitAsync(TimeSpan.FromSeconds(5));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
            await tracked!.WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.False(invoked);
    }

    /// <summary>The whole async operation retains dispatcher affinity, and cancellation cannot abandon its cleanup.</summary>
    [Fact]
    public async Task StartedOperationRemainsTrackedUntilUiAffineCleanupCompletes()
    {
        using var host = new DispatcherThread();
        using var cancellation = new CancellationTokenSource();
        var entered = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var cleaned = false;
        var tracked = ExternalControlLifecycleScheduler.RunAsync(host.Dispatcher, async token =>
        {
            host.Dispatcher.VerifyAccess();
            entered.SetResult(true);
            try
            {
                await release.Task;
                host.Dispatcher.VerifyAccess();
                token.ThrowIfCancellationRequested();
            }
            finally
            {
                host.Dispatcher.VerifyAccess();
                cleaned = true;
            }
        }, cancellation.Token);
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            cancellation.Cancel();
            Assert.False(tracked.IsCompleted);
            Assert.False(cleaned);
            release.SetResult(true);
            await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
                await tracked.WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.True(cleaned);
        }
        finally { release.TrySetResult(true); }
    }

    /// <summary>Both synchronous and post-await failures stay observable by the service's generation-aware owner.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task OperationFailuresRemainObservable(bool afterAwait)
    {
        using var host = new DispatcherThread();
        var error = new InvalidOperationException("synthetic lifecycle failure");
        var tracked = ExternalControlLifecycleScheduler.RunAsync(host.Dispatcher, async _ =>
        {
            host.Dispatcher.VerifyAccess();
            if (afterAwait) await Task.Yield();
            host.Dispatcher.VerifyAccess();
            throw error;
        }, CancellationToken.None);
        Assert.Same(error, await Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await tracked.WaitAsync(TimeSpan.FromSeconds(5))));
    }

    /// <summary>Own one test-only STA loop without constructing Application or a visible window.</summary>
    private sealed class DispatcherThread : IDisposable
    {
        /// <summary>Only this fixture's background thread is stopped during cleanup.</summary>
        private readonly Thread _thread;
        /// <summary>Dispatcher initialized on the fixture's STA thread.</summary>
        public Dispatcher Dispatcher { get; }

        /// <summary>Wait until the headless dispatcher can accept queued work.</summary>
        public DispatcherThread()
        {
            var ready = new TaskCompletionSource<Dispatcher>(TaskCreationOptions.RunContinuationsAsynchronously);
            _thread = new Thread(() =>
            {
                ready.SetResult(System.Windows.Threading.Dispatcher.CurrentDispatcher);
                System.Windows.Threading.Dispatcher.Run();
            }) { IsBackground = true, Name = "ExternalControl lifecycle test dispatcher" };
            _thread.SetApartmentState(ApartmentState.STA);
            _thread.Start();
            Dispatcher = ready.Task.WaitAsync(TimeSpan.FromSeconds(5)).GetAwaiter().GetResult();
        }

        /// <summary>Exit the fixture loop after test-owned blocked callbacks are released.</summary>
        public void Dispose()
        {
            Dispatcher.BeginInvokeShutdown(DispatcherPriority.Send);
            Assert.True(_thread.Join(TimeSpan.FromSeconds(5)), "Headless test dispatcher did not stop.");
        }
    }
}
