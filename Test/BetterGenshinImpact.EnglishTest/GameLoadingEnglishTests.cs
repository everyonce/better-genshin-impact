using BetterGenshinImpact.GameTask.GameLoading;
using BetterGenshinImpact.GameTask.Model.Area;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public class GameLoadingEnglishTests
{
    [Theory]
    [InlineData("CLICK TO BEGIN")]
    [InlineData("Click   to\tBegin!")]
    [InlineData("CLICK-TO-BEGIN")]
    public void MatchesExplicitEnglishPromptInsideLowerCenter(string text)
    {
        var expected = new Region(850, 700, 220, 50) { Text = text };
        var other = new Region(100, 700, 220, 50) { Text = "CLICK TO BEGIN" };

        var match = GameLoadingEnglishMatcher.FindClickToBegin([other, expected], 1920, 1080, true);

        Assert.Same(expected, match);
    }

    [Theory]
    [InlineData("START")]
    [InlineData("ENTER")]
    [InlineData("CLICK TO START")]
    [InlineData("CLICK TO BEGIN NOW")]
    [InlineData("BEGIN")]
    public void RejectsGenericOrNonExactPrompt(string text)
    {
        var region = new Region(850, 700, 220, 50) { Text = text };

        Assert.Null(GameLoadingEnglishMatcher.FindClickToBegin([region], 1920, 1080, true));
    }

    [Theory]
    [InlineData(850, 450)]
    [InlineData(500, 700)]
    [InlineData(1400, 700)]
    public void RejectsPromptOutsideLowerCenter(int x, int y)
    {
        var region = new Region(x, y, 220, 50) { Text = "CLICK TO BEGIN" };

        Assert.Null(GameLoadingEnglishMatcher.FindClickToBegin([region], 1920, 1080, true));
    }

    [Fact]
    public void RejectsEnglishPromptWhenGameLanguageIsNotEnglish()
    {
        var region = new Region(850, 700, 220, 50) { Text = "CLICK TO BEGIN" };

        Assert.Null(GameLoadingEnglishMatcher.FindClickToBegin([region], 1920, 1080, false));
    }

    [Theory]
    [InlineData(1920, 1080, 850, 700)]
    [InlineData(1280, 720, 570, 470)]
    [InlineData(2560, 1440, 1150, 950)]
    public void UsesRelativeBoundsAtDifferentCaptureScales(int width, int height, int x, int y)
    {
        var region = new Region(x, y, 100, 40) { Text = "CLICK TO BEGIN" };

        var match = GameLoadingEnglishMatcher.FindClickToBegin([region], width, height, true);

        Assert.Same(region, match);
        Assert.Equal(x, match!.Left);
        Assert.Equal(y, match.Top);
    }
}
