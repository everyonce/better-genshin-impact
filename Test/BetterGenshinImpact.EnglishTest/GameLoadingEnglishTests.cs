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
    public void MatchesExplicitClickToBeginPromptAtObservedCenteredPosition(string text)
    {
        var expected = new Region(849, 570, 215, 34) { Text = text };
        var other = new Region(100, 570, 215, 34) { Text = "CLICK TO BEGIN" };

        var match = GameLoadingEnglishMatcher.FindEntryPrompt([other, expected], 1920, 1080, true);

        Assert.Same(expected, match);
    }

    [Fact]
    public void MatchesObservedStartGameLabel()
    {
        var startGame = new Region(761, 472, 389, 67) { Text = "START GAME" };

        var match = GameLoadingEnglishMatcher.FindEntryPrompt([startGame], 1920, 1080, true);

        Assert.Same(startGame, match);
    }

    [Fact]
    public void PrefersClickToBeginWhenBothEntryLabelsArePresent()
    {
        var startGame = new Region(761, 472, 389, 67) { Text = "START GAME" };
        var clickToBegin = new Region(849, 570, 215, 34) { Text = "CLICK TO BEGIN" };

        var match = GameLoadingEnglishMatcher.FindEntryPrompt([startGame, clickToBegin], 1920, 1080, true);

        Assert.Same(clickToBegin, match);
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

        Assert.Null(GameLoadingEnglishMatcher.FindEntryPrompt([region], 1920, 1080, true));
    }

    [Theory]
    [InlineData(850, 450)]
    [InlineData(500, 570)]
    [InlineData(1400, 570)]
    public void RejectsPromptOutsideLowerCenter(int x, int y)
    {
        var region = new Region(x, y, 215, 34) { Text = "CLICK TO BEGIN" };

        Assert.Null(GameLoadingEnglishMatcher.FindEntryPrompt([region], 1920, 1080, true));
    }

    [Fact]
    public void RejectsEnglishPromptWhenGameLanguageIsNotEnglish()
    {
        var region = new Region(849, 570, 215, 34) { Text = "CLICK TO BEGIN" };

        Assert.Null(GameLoadingEnglishMatcher.FindEntryPrompt([region], 1920, 1080, false));
    }

    [Theory]
    [InlineData(1920, 1080, 849, 570, 215, 34)]
    [InlineData(1280, 720, 566, 380, 143, 23)]
    [InlineData(2560, 1440, 1132, 760, 287, 45)]
    public void UsesRelativeBoundsAtDifferentCaptureScales(int width, int height, int x, int y, int regionWidth, int regionHeight)
    {
        var region = new Region(x, y, regionWidth, regionHeight) { Text = "CLICK TO BEGIN" };

        var match = GameLoadingEnglishMatcher.FindEntryPrompt([region], width, height, true);

        Assert.Same(region, match);
        Assert.Equal(x, match!.Left);
        Assert.Equal(y, match.Top);
    }

    [Theory]
    [InlineData("Password")]
    [InlineData("Sign in")]
    [InlineData("Login")]
    [InlineData("Verification code")]
    [InlineData("CAPTCHA")]
    public void RejectsEntryLabelsOnAuthenticationScreens(string authenticationText)
    {
        var entry = new Region(849, 570, 215, 34) { Text = "CLICK TO BEGIN" };
        var dialogText = new Region(600, 300, 300, 40) { Text = authenticationText };

        Assert.Null(GameLoadingEnglishMatcher.FindEntryPrompt([entry, dialogText], 1920, 1080, true));
    }

    [Fact]
    public void DoesNotTreatMaskedAccountEmailAsAnAuthenticationDialog()
    {
        var entry = new Region(849, 570, 215, 34) { Text = "CLICK TO BEGIN" };
        var maskedEmail = new Region(850, 900, 240, 30) { Text = "d***@g***.com" };

        Assert.Same(entry, GameLoadingEnglishMatcher.FindEntryPrompt([maskedEmail, entry], 1920, 1080, true));
    }

    [Fact]
    public void UnfocusedFrameDoesNotConsumeTheSingleEntryClickAttempt()
    {
        var clickAttempted = false;

        Assert.False(GameLoadingEnglishMatcher.TryMarkEntryClickAttempted(false, ref clickAttempted));
        Assert.False(clickAttempted);

        // A subsequent fresh capture after focus returns may reserve the one click.
        Assert.True(GameLoadingEnglishMatcher.TryMarkEntryClickAttempted(true, ref clickAttempted));
        Assert.True(clickAttempted);
        Assert.False(GameLoadingEnglishMatcher.TryMarkEntryClickAttempted(true, ref clickAttempted));
    }

    [Theory]
    [InlineData("CLICK TO BEGIN")]
    [InlineData("Click   to	Begin!")]
    [InlineData("CLICK-TO-BEGIN")]
    public void MatchesExactDoorStagePromptAtObservedBottomPosition(string text)
    {
        var prompt = new Region(854, 1007, 209, 26) { Text = text };

        var match = GameLoadingEnglishMatcher.FindDoorEntryPrompt([prompt], 1920, 1080, true);

        Assert.Same(prompt, match);
    }

    [Theory]
    [InlineData(1920, 1080, 854, 1007, 209, 26)]
    [InlineData(1280, 720, 569, 671, 139, 17)]
    [InlineData(2560, 1440, 1139, 1343, 279, 35)]
    public void MatchesDoorPromptAtDifferentCaptureScales(int width, int height, int x, int y, int regionWidth, int regionHeight)
    {
        var prompt = new Region(x, y, regionWidth, regionHeight) { Text = "CLICK TO BEGIN" };

        Assert.Same(prompt, GameLoadingEnglishMatcher.FindDoorEntryPrompt([prompt], width, height, true));
    }

    [Fact]
    public void KeepsTitleAndDoorPromptMatchersIsolated()
    {
        var titlePrompt = new Region(849, 570, 215, 34) { Text = "CLICK TO BEGIN" };
        var doorPrompt = new Region(854, 1007, 209, 26) { Text = "CLICK TO BEGIN" };

        Assert.Same(titlePrompt, GameLoadingEnglishMatcher.FindEntryPrompt([titlePrompt], 1920, 1080, true));
        Assert.Null(GameLoadingEnglishMatcher.FindDoorEntryPrompt([titlePrompt], 1920, 1080, true));
        Assert.Null(GameLoadingEnglishMatcher.FindEntryPrompt([doorPrompt], 1920, 1080, true));
        Assert.Same(doorPrompt, GameLoadingEnglishMatcher.FindDoorEntryPrompt([doorPrompt], 1920, 1080, true));
    }

    [Theory]
    [InlineData(500, 1007)]
    [InlineData(1400, 1007)]
    [InlineData(854, 970)]
    [InlineData(854, 1055)]
    public void RejectsDoorPromptOutsideBottomCenter(int x, int y)
    {
        var prompt = new Region(x, y, 209, 26) { Text = "CLICK TO BEGIN" };

        Assert.Null(GameLoadingEnglishMatcher.FindDoorEntryPrompt([prompt], 1920, 1080, true));
    }

    [Theory]
    [InlineData("Password")]
    [InlineData("Login")]
    [InlineData("CAPTCHA")]
    [InlineData("START GAME")]
    [InlineData("America")]
    [InlineData("North America Server")]
    public void RejectsDoorPromptWhenAuthenticationOrTitleServerTextIsPresent(string sceneText)
    {
        var prompt = new Region(854, 1007, 209, 26) { Text = "CLICK TO BEGIN" };
        var otherText = new Region(850, 400, 220, 35) { Text = sceneText };

        Assert.Null(GameLoadingEnglishMatcher.FindDoorEntryPrompt([prompt, otherText], 1920, 1080, true));
    }

    [Fact]
    public void AllowsOneIndependentAttemptForEachEnglishEntryPhase()
    {
        var titleClickAttempted = false;
        var doorClickAttempted = false;

        Assert.True(GameLoadingEnglishMatcher.TryMarkEntryClickAttempted(true, ref titleClickAttempted));
        Assert.False(GameLoadingEnglishMatcher.TryMarkEntryClickAttempted(true, ref titleClickAttempted));
        Assert.True(GameLoadingEnglishMatcher.TryMarkEntryClickAttempted(true, ref doorClickAttempted));
        Assert.False(GameLoadingEnglishMatcher.TryMarkEntryClickAttempted(true, ref doorClickAttempted));
    }
}
