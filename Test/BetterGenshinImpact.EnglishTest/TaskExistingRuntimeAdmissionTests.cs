using System;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.Runtime;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exact existing-runtime seam has no factory, restart, UI or input callback.</summary>
public sealed class TaskExistingRuntimeAdmissionTests
{
    /// <summary>Reject missing/replaced/stopping/cancelled ownership before any updater wait.</summary>
    [Theory]
    [InlineData("missing")][InlineData("replacement")][InlineData("stopping")][InlineData("cancel")]
    public async Task RejectBeforeWait(string mutation)
    {
        using var expected = Create(); using var replacement = Create(); using var cancellation = new CancellationTokenSource();
        GameRuntime? current = mutation == "missing" ? null : mutation == "replacement" ? replacement : expected;
        if (mutation == "stopping") expected.SignalStopping();
        if (mutation == "cancel") cancellation.Cancel();
        var waits = 0;
        var error = await Record.ExceptionAsync(() => TaskRunner.AcquireExistingRuntimeAsync(expected, () => current,
            _ => { waits++; return Task.CompletedTask; }, cancellation.Token));
        Assert.NotNull(error); Assert.Equal(0, waits);
    }

    /// <summary>An asynchronous existing dependency cannot hide replacement or stopping during its wait.</summary>
    [Theory]
    [InlineData("missing")][InlineData("replacement")][InlineData("stopping")][InlineData("cancel")]
    public async Task RejectAfterWait(string mutation)
    {
        using var expected = Create(); using var replacement = Create(); using var cancellation = new CancellationTokenSource();
        GameRuntime? current = expected; var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var result = TaskRunner.AcquireExistingRuntimeAsync(expected, () => current, async token =>
        { Assert.Equal(cancellation.Token, token); entered.SetResult(); await release.Task; }, cancellation.Token);
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        if (mutation == "missing") current = null;
        if (mutation == "replacement") current = replacement;
        if (mutation == "stopping") expected.SignalStopping();
        if (mutation == "cancel") cancellation.Cancel();
        release.SetResult();
        Assert.NotNull(await Record.ExceptionAsync(async () => { await result; }));
    }

    /// <summary>Unchanged exact reference is returned after exactly one existing updater wait.</summary>
    [Fact]
    public async Task PreserveSameRuntimeWithoutFactory()
    {
        using var expected = Create(); var waits = 0;
        var result = await TaskRunner.AcquireExistingRuntimeAsync(expected, () => expected,
            _ => { waits++; return Task.CompletedTask; }, default);
        Assert.Same(expected, result); Assert.Equal(1, waits); Assert.False(expected.IsStopping);
    }

    /// <summary>Use the repository's existing no-native fake runtime components.</summary>
    private static GameRuntime Create() => TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1));
}
