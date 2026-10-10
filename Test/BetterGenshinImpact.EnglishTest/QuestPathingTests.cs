using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Core.Script.Dependence;
using BetterGenshinImpact.GameTask.AutoPathing;
using System.Threading;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public class QuestPathingTests
{
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
