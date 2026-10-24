using System.Diagnostics;
using BetterGenshinImpact.Core.Infrastructure;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Real local timer lifecycle checks; no capture, game, input, priority or global timer changes.</summary>
public sealed class NavigationBaselineWaitTimerTests
{
    /// <summary>Reject invalid durations before admission; a rejected call must not poison the owned worker.</summary>
    [Theory]
    [InlineData(int.MinValue)]
    [InlineData(-1)]
    [InlineData(0)]
    [InlineData(1001)]
    [InlineData(int.MaxValue)]
    public async Task InvalidDurationDoesNotAdmitOrPoisonWait(int milliseconds)
    {
        await using var timer = new OwnedHighResolutionWaitTimer();
        Assert.Throws<ArgumentOutOfRangeException>(() => { timer.Start(milliseconds, default); });
        await timer.Start(1, default).Completion.WaitAsync(TimeSpan.FromSeconds(5));
    }

    /// <summary>A cancelled caller does not acquire the only request slot or require native arming.</summary>
    [Fact]
    public async Task PreCancelledRequestLeavesTimerUsable()
    {
        await using var timer = new OwnedHighResolutionWaitTimer();
        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        Assert.Throws<OperationCanceledException>(() => { timer.Start(5, cancelled.Token); });
        await timer.Start(5, default).Completion.WaitAsync(TimeSpan.FromSeconds(5));
    }

    /// <summary>Successful completion contains ordered monotonic host observations, not a precision guarantee.</summary>
    [Theory]
    [InlineData(1)]
    [InlineData(5)]
    public async Task SuccessfulWaitHasMonotonicArmAndWakeEvidence(int milliseconds)
    {
        var timer = new OwnedHighResolutionWaitTimer();
        try
        {
            long before = Stopwatch.GetTimestamp();
            var operation = timer.Start(milliseconds, default);
            var result = await operation.Completion.WaitAsync(TimeSpan.FromSeconds(5));
            long after = Stopwatch.GetTimestamp();
            Assert.True(operation.Armed.IsCompletedSuccessfully);
            Assert.InRange(result.ArmStartedTicks, before, after);
            Assert.InRange(result.ArmCompletedTicks, result.ArmStartedTicks, after);
            Assert.InRange(result.WakeObservedTicks, result.ArmCompletedTicks, after);
        }
        finally { await timer.DisposeAsync(); }
        Assert.True(timer.WorkerRetired);
    }

    /// <summary>Only one native wait can own the timer; explicit cancellation completes before the next admission.</summary>
    [Fact]
    public async Task ArmedWaitRejectsOverlapThenCancelsAndReuses()
    {
        await using var timer = new OwnedHighResolutionWaitTimer();
        using var cancellation = new CancellationTokenSource();
        var first = timer.Start(1000, cancellation.Token);
        await first.Armed.WaitAsync(TimeSpan.FromSeconds(5));
        var failure = Assert.Throws<InvalidOperationException>(() => { timer.Start(5, default); });
        Assert.Equal("One wait is already outstanding.", failure.Message);
        cancellation.Cancel();
        var cancelled = await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
            await first.Completion.WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.Equal(cancellation.Token, cancelled.CancellationToken);
        await timer.Start(5, default).Completion.WaitAsync(TimeSpan.FromSeconds(5));
    }

    /// <summary>Cancellation leaves no previous signaled state that can prematurely satisfy the next arm.</summary>
    [Fact]
    public async Task ReuseAfterCancellationRequiresNewDueTime()
    {
        await using var timer = new OwnedHighResolutionWaitTimer();
        using var cancellation = new CancellationTokenSource();
        var first = timer.Start(1000, cancellation.Token);
        await first.Armed.WaitAsync(TimeSpan.FromSeconds(5));
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
            await first.Completion.WaitAsync(TimeSpan.FromSeconds(5)));
        var reused = await timer.Start(50, default).Completion.WaitAsync(TimeSpan.FromSeconds(5));
        // A broad lower bound detects reuse of an old signal without asserting production scheduling precision.
        Assert.True((reused.WakeObservedTicks - reused.ArmStartedTicks) * 1000.0 / Stopwatch.Frequency >= 40);
    }

    /// <summary>A retired cancellation registration cannot cancel the next admitted request.</summary>
    [Fact]
    public async Task CompletedRequestTokenCannotCancelItsSuccessor()
    {
        await using var timer = new OwnedHighResolutionWaitTimer();
        using var old = new CancellationTokenSource();
        await timer.Start(1, old.Token).Completion.WaitAsync(TimeSpan.FromSeconds(5));
        using var current = new CancellationTokenSource();
        var second = timer.Start(1000, current.Token);
        await second.Armed.WaitAsync(TimeSpan.FromSeconds(5));
        old.Cancel();
        await Task.Delay(20);
        Assert.False(second.Completion.IsCompleted);
        current.Cancel();
        var cancelled = await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
            await second.Completion.WaitAsync(TimeSpan.FromSeconds(5)));
        Assert.Equal(current.Token, cancelled.CancellationToken);
    }

    /// <summary>Every cancel/completion race retires its request before reuse, regardless of which outcome wins.</summary>
    [Fact]
    public async Task CancellationCompletionRacesKeepSingleRequestOwnership()
    {
        await using var timer = new OwnedHighResolutionWaitTimer();
        for (int index = 0; index < 16; index++)
        {
            using var cancellation = new CancellationTokenSource();
            var racing = timer.Start(5, cancellation.Token);
            cancellation.Cancel();
            try { await racing.Completion.WaitAsync(TimeSpan.FromSeconds(5)); }
            catch (OperationCanceledException) { }
            await timer.Start(1, default).Completion.WaitAsync(TimeSpan.FromSeconds(5));
        }
    }

    /// <summary>Two concurrent disposers must share retirement and reject a still-armed operation.</summary>
    [Fact]
    public async Task ActiveShutdownAndConcurrentDisposeDrainBeforeClosing()
    {
        var timer = new OwnedHighResolutionWaitTimer();
        try
        {
            var active = timer.Start(1000, default);
            await active.Armed.WaitAsync(TimeSpan.FromSeconds(5));
            await Task.WhenAll(timer.DisposeAsync().AsTask(), timer.DisposeAsync().AsTask());
            await Assert.ThrowsAsync<ObjectDisposedException>(async () => await active.Completion);
            Assert.True(timer.WorkerRetired);
            Assert.Throws<ObjectDisposedException>(() => { timer.Start(5, default); });
        }
        finally { await timer.DisposeAsync(); }
    }

    /// <summary>Idle disposal wakes the worker rather than waiting for a timer signal or creating another wait.</summary>
    [Fact]
    public async Task IdleShutdownIsPermanentAndIdempotent()
    {
        var timer = new OwnedHighResolutionWaitTimer();
        await timer.DisposeAsync();
        await timer.DisposeAsync();
        Assert.True(timer.WorkerRetired);
        Assert.Throws<ObjectDisposedException>(() => { timer.Start(1, default); });
    }

    /// <summary>Immediate shutdown settles an admitted request whether or not the worker reached its first arm.</summary>
    [Fact]
    public async Task ShutdownRacingWorkerAdmissionDoesNotLeaveARequestUnsettled()
    {
        for (int index = 0; index < 8; index++)
        {
            var timer = new OwnedHighResolutionWaitTimer();
            try
            {
                var request = timer.Start(1000, default);
                await timer.DisposeAsync();
                await Assert.ThrowsAsync<ObjectDisposedException>(async () => await request.Completion);
                // Observe either completed arm or its failure without creating an unobserved handshake exception.
                try { await request.Armed; } catch (ObjectDisposedException) { }
                Assert.True(timer.WorkerRetired);
            }
            finally { await timer.DisposeAsync(); }
        }
    }
}
