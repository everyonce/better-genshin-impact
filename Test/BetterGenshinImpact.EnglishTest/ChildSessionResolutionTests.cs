using System.Drawing;
using System.Text.Json;
using BetterGenshinImpact.Core.Config;
using BetterGenshinImpact.Service;
using BetterGenshinImpact.Service.ChildSession;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

public sealed class ChildSessionResolutionTests
{
    [Fact]
    public void MissingResolutionUses2560x1440Default()
    {
        var config = JsonSerializer.Deserialize<ChildSessionConfig>("{}");

        Assert.NotNull(config);
        Assert.Equal(ChildSessionResolution.Resolution2560x1440, config.DesktopResolution);
        Assert.Equal(new Size(2560, 1440), ChildSessionService.GetDesktopSize(config.DesktopResolution));
    }

    [Fact]
    public void InvalidResolutionFallsBackTo2560x1440()
    {
        var config = JsonSerializer.Deserialize<ChildSessionConfig>(
            "{\"desktopResolution\":1234}",
            ConfigService.JsonOptions);

        Assert.NotNull(config);
        Assert.Equal(ChildSessionResolution.Resolution2560x1440,
            ChildSessionService.NormalizeDesktopResolution(config.DesktopResolution));
        Assert.Equal(new Size(2560, 1440), ChildSessionService.GetDesktopSize(config.DesktopResolution));
    }

    [Theory]
    [InlineData(ChildSessionResolution.Resolution1920x1080, 1920, 1080)]
    [InlineData(ChildSessionResolution.Resolution2560x1440, 2560, 1440)]
    public void MapsBothSupportedResolutions(ChildSessionResolution resolution, int width, int height)
    {
        Assert.Equal(new Size(width, height), ChildSessionService.GetDesktopSize(resolution));
    }

    [Theory]
    [InlineData(ChildSessionResolution.Resolution1920x1080)]
    [InlineData(ChildSessionResolution.Resolution2560x1440)]
    public void ResolutionChoicePersistsThroughConfigSerialization(ChildSessionResolution resolution)
    {
        var config = new ChildSessionConfig { DesktopResolution = resolution };
        var json = JsonSerializer.Serialize(config, ConfigService.JsonOptions);
        var restored = JsonSerializer.Deserialize<ChildSessionConfig>(json, ConfigService.JsonOptions);

        Assert.NotNull(restored);
        Assert.Equal(resolution, restored.DesktopResolution);
    }
}
