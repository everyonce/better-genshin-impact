using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Script.Dependence;
using BetterGenshinImpact.GameTask.AutoPathing;
using System.Threading;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public class QuestPathingTests
{
    [Fact]
    public async Task Deadline_CancelsRouteAndReleasesWithoutCancellingOwner()
    {
        using var owner = new CancellationTokenSource();
        using var request = new CancellationTokenSource();
        var releases = 0;
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => AutoPathingScript.RunBoundedQuest(
            token => Task.Delay(Timeout.Infinite, token), () => releases++, owner.Token, request.Token, 100));
        Assert.Equal(1, releases);
        Assert.False(owner.IsCancellationRequested);
        Assert.False(request.IsCancellationRequested);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Deadline_PropagatesCancellationAndAlwaysReleases(bool cancelOwner)
    {
        using var owner = new CancellationTokenSource();
        using var request = new CancellationTokenSource();
        var releases = 0;
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var run = AutoPathingScript.RunBoundedQuest(async token => {
            entered.SetResult();
            await Task.Delay(Timeout.Infinite, token);
        }, () => releases++, owner.Token, request.Token, 60000);
        await entered.Task;
        (cancelOwner ? owner : request).Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => run);
        Assert.Equal(1, releases);
    }

    [Fact]
    public async Task Deadline_RejectsInvalidBudgetBeforeExecutingAndReleasesOnFailure()
    {
        var calls = 0;
        foreach (var timeout in new[] { -1, 0, 99, 60001 })
            await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => AutoPathingScript.RunBoundedQuest(
                _ => { calls++; return Task.CompletedTask; }, () => calls++, default, default, timeout));
        Assert.Equal(0, calls);
        await Assert.ThrowsAsync<InvalidOperationException>(() => AutoPathingScript.RunBoundedQuest(
            _ => throw new InvalidOperationException(), () => calls++, default, default, 100));
        Assert.Equal(1, calls);
    }

    [Fact]
    public void BuildQuestPartyConfig_ClonesNestedSettingsAndDisablesQuestSideEffects()
    {
        var source = new PathingPartyConfig
        {
            Enabled = true,
            AutoFightEnabled = true,
            AutoSkipEnabled = true,
            AutoPickEnabled = true,
            PartyName = "Quest party",
            AutoFightConfig = { StrategyName = "Custom strategy", FinishDetectConfig = { CheckEndDelay = "1.2" } }
        };

        var questConfig = AutoPathingScript.BuildQuestPartyConfig(source);

        Assert.NotSame(source, questConfig);
        Assert.NotSame(source.AutoFightConfig, questConfig.AutoFightConfig);
        Assert.NotSame(source.AutoFightConfig.FinishDetectConfig, questConfig.AutoFightConfig.FinishDetectConfig);
        Assert.True(questConfig.Enabled);
        Assert.True(questConfig.AutoFightEnabled);
        Assert.Equal("Custom strategy", questConfig.AutoFightConfig.StrategyName);
        Assert.Equal("1.2", questConfig.AutoFightConfig.FinishDetectConfig.CheckEndDelay);
        Assert.False(questConfig.AutoSkipEnabled);
        Assert.False(questConfig.AutoPickEnabled);
    }

    [Fact]
    public void BuildQuestPartyConfig_DoesNotChangeCallerConfiguration()
    {
        var source = new PathingPartyConfig { AutoSkipEnabled = true, AutoPickEnabled = true };

        _ = AutoPathingScript.BuildQuestPartyConfig(source);

        Assert.True(source.AutoSkipEnabled);
        Assert.True(source.AutoPickEnabled);
    }

    [Fact]
    public void BuildQuestPartyConfig_PreservesDisabledSourceAndExecutorPolicyOwnsDialogue()
    {
        var source = new PathingPartyConfig { Enabled = false, AutoSkipEnabled = false, AutoPickEnabled = false };
        var questConfig = AutoPathingScript.BuildQuestPartyConfig(source);
        var executor = new PathExecutor(CancellationToken.None)
        {
            ScriptControlsDialogue = true,
            PartyConfig = new PathingPartyConfig { AutoSkipEnabled = true }
        };

        Assert.False(questConfig.Enabled);
        Assert.False(questConfig.AutoSkipEnabled);
        Assert.False(questConfig.AutoPickEnabled);
        // The executor guard remains authoritative even after PathExecutor replaces a disabled
        // config with the conditional config, which may have AutoSkipEnabled=true.
        Assert.False(executor.ShouldRunNativeAutoSkip);
        Assert.False(executor.ShouldCloseUnexpectedUi);
        Assert.True(executor.ShouldPropagatePathingFailures);

        var ordinaryExecutor = new PathExecutor(CancellationToken.None)
        {
            PartyConfig = new PathingPartyConfig()
        };
        Assert.False(ordinaryExecutor.ShouldPropagatePathingFailures);
    }
}
