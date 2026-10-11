using GenshinApi = BetterGenshinImpact.Core.Script.Dependence.Genshin;
using Vanara.PInvoke;

namespace BetterGenshinImpact.UnitTest.GenshinTests;

public class GameWindowInfoTests
{
    [Fact]
    public void BoundsMatch_RecognizesDesktopSizedWindowWithinPhysicalPixelTolerance()
    {
        var desktop = new RECT(-2560, 0, 0, 1440);
        var gameWindow = new RECT(-2560, 0, -1, 1440);

        Assert.True(GenshinApi.BoundsMatch(gameWindow, desktop));
        Assert.False(GenshinApi.BoundsMatch(gameWindow, desktop, tolerance: 0));
    }

    [Fact]
    public void BoundsMatch_RejectsWindowedClientAndDifferentDesktopOrigin()
    {
        var desktop = new RECT(0, 0, 2560, 1440);
        var windowedClient = new RECT(320, 180, 2240, 1260);
        var sameSizeWrongOrigin = new RECT(-2560, 0, 0, 1440);

        Assert.False(GenshinApi.BoundsMatch(windowedClient, desktop));
        Assert.False(GenshinApi.BoundsMatch(sameSizeWrongOrigin, desktop));
    }
}
