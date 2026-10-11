using BetterGenshinImpact.GameTask;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public sealed class GameLaunchArgumentEnglishTests
{
    private const string RequiredChildArguments =
        "-screen-fullscreen 0 -popupwindow -screen-width 1920 -screen-height 1080";

    [Theory]
    [InlineData("-screen-fullscreen 1 -screen-width 3840 -screen-height 2160 -popupwindow")]
    [InlineData("-SCREEN-FULLSCREEN=1 -SCREEN-WIDTH=3840 -SCREEN-HEIGHT=2160 -POPUPWINDOW")]
    [InlineData("-window-mode exclusive -screen-fullscreen 1")]
    [InlineData("-WINDOW-MODE=fullscreen -SCREEN-FULLSCREEN=1")]
    public void ChildSessionOverridesConflictingDisplayArguments(string configuredArguments)
    {
        Assert.Equal(
            RequiredChildArguments,
            GenshinStartArguments.Build(configuredArguments, isChildSession: true));
    }

    [Fact]
    public void ChildSessionPreservesUnrelatedArgumentsAndAddsRequiredDisplayArguments()
    {
        Assert.Equal(
            "-platform windows -some-option \"keep this\" " + RequiredChildArguments,
            GenshinStartArguments.Build(
                "-popupwindow -platform windows -some-option \"keep this\" -screen-width=3840 -screen-height 2160 -window-mode=fullscreen",
                isChildSession: true));
    }

    [Fact]
    public void NonChildLaunchArgumentsRemainUnchanged()
    {
        const string configuredArguments = "-window-mode fullscreen -screen-fullscreen 1 -popupwindow";

        Assert.Equal(
            configuredArguments,
            GenshinStartArguments.Build(configuredArguments, isChildSession: false));
    }
}
