using Fischless.GameCapture.Graphics.Helpers;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Managed workers and explicit barriers exercise native-operation ownership without starting WGC.</summary>
public sealed class WgcCapturePumpTests
{
    /// <summary>Tests have generous completion limits; no assertion depends on scheduler performance.</summary>
    private static readonly TimeSpan CompletionLimit = TimeSpan.FromSeconds(10);

    /// <summary>A timed-out running call retains its resources until it actually returns.</summary>
    [Fact]
    public async Task TimeoutRetiresBehindRunningOperationAndRejectsFurtherWork()
    {
        var pump = new WgcCapturePump();
        using var release = new ManualResetEventSlim();
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var disposed = 0;
        var executionThread = 0;
        var cleanupThread = 0;
        Task? retirement = null;
        try
        {
            var dispatch = Task.Run(() => pump.Run(() =>
            {
                executionThread = Environment.CurrentManagedThreadId;
                started.SetResult();
                release.Wait();
                Assert.Equal(0, Volatile.Read(ref disposed));
            }, TimeSpan.FromMilliseconds(100)));
            await started.Task.WaitAsync(CompletionLimit);
            await Assert.ThrowsAsync<TimeoutException>(() => dispatch);
            Assert.True(pump.IsFaulted);
            Assert.Throws<InvalidOperationException>(() => pump.Run(() => { }, CompletionLimit));
            retirement = pump.Retire(() =>
            {
                cleanupThread = Environment.CurrentManagedThreadId;
                Interlocked.Increment(ref disposed);
            });
            Assert.Same(retirement, pump.Retire(() => throw new Exception("Must not enqueue a second cleanup.")));
            Assert.False(retirement.IsCompleted);
            Assert.Equal(0, Volatile.Read(ref disposed));
            release.Set();
            await retirement.WaitAsync(CompletionLimit);
            Assert.Equal(1, disposed);
            Assert.Equal(executionThread, cleanupThread);
        }
        finally
        {
            release.Set();
            await (retirement ?? pump.Retire(() => { })).WaitAsync(CompletionLimit);
        }
    }

    /// <summary>Even a late native failure cannot skip the cleanup queued behind it.</summary>
    [Fact]
    public async Task LateFailureAfterTimeoutStillRunsRetirement()
    {
        var pump = new WgcCapturePump();
        using var release = new ManualResetEventSlim();
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var cleaned = false;
        try
        {
            var dispatch = Task.Run(() => pump.Run(() =>
            {
                started.SetResult();
                release.Wait();
                throw new InvalidOperationException("Controlled late native failure.");
            }, TimeSpan.FromMilliseconds(100)));
            await started.Task.WaitAsync(CompletionLimit);
            await Assert.ThrowsAsync<TimeoutException>(() => dispatch);
            var retirement = pump.Retire(() => cleaned = true);
            Assert.False(cleaned);
            release.Set();
            await retirement.WaitAsync(CompletionLimit);
            Assert.True(cleaned);
        }
        finally
        {
            release.Set();
            await pump.Retire(() => { }).WaitAsync(CompletionLimit);
        }
    }

    /// <summary>A retired worker rejects work; replacement workers retain their own queue and thread.</summary>
    [Fact]
    public async Task ReplacementHasItsOwnQueueAndThread()
    {
        var first = new WgcCapturePump();
        var second = new WgcCapturePump();
        var firstThread = 0;
        var secondThread = 0;
        try
        {
            first.Run(() => firstThread = Environment.CurrentManagedThreadId, CompletionLimit);
            second.Run(() => secondThread = Environment.CurrentManagedThreadId, CompletionLimit);
            Assert.NotEqual(firstThread, secondThread);
            await first.Retire(() => Assert.Equal(firstThread, Environment.CurrentManagedThreadId)).WaitAsync(CompletionLimit);
            Assert.Throws<InvalidOperationException>(() => first.Run(() => { }, CompletionLimit));
            second.Run(() => Assert.Equal(secondThread, Environment.CurrentManagedThreadId), CompletionLimit);
        }
        finally
        {
            await first.Retire(() => { }).WaitAsync(CompletionLimit);
            await second.Retire(() => { }).WaitAsync(CompletionLimit);
        }
    }

    /// <summary>Dispatch and cleanup failures retain their original type and never report a successful retirement.</summary>
    [Fact]
    public async Task ErrorsRemainObservable()
    {
        var pump = new WgcCapturePump();
        Assert.Throws<ArgumentException>(() => pump.Run(() => throw new ArgumentException("operation"), CompletionLimit));
        var retirement = pump.Retire(() => throw new InvalidOperationException("cleanup"));
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => retirement.WaitAsync(CompletionLimit));
        Assert.Equal("cleanup", error.Message);
        Assert.Throws<InvalidOperationException>(() => pump.Run(() => { }, CompletionLimit));
    }

    /// <summary>A slow operation cannot accumulate additional ordinary operations behind itself.</summary>
    [Fact]
    public async Task PendingOperationRejectsBacklog()
    {
        var pump = new WgcCapturePump();
        using var release = new ManualResetEventSlim();
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var dispatch = Task.Run(() => pump.Run(() => { started.SetResult(); release.Wait(); }, CompletionLimit));
        try
        {
            await started.Task.WaitAsync(CompletionLimit);
            Assert.Throws<InvalidOperationException>(() => pump.Run(() => { }, CompletionLimit));
            release.Set();
            await dispatch.WaitAsync(CompletionLimit);
        }
        finally
        {
            release.Set();
            await pump.Retire(() => { }).WaitAsync(CompletionLimit);
        }
    }
}
