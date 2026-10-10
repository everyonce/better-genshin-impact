using BetterGenshinImpact.Core.Script.Group;
using BetterGenshinImpact.Service;

namespace BetterGenshinImpact.UnitTest.ServiceTests;

public class ScriptServiceStartupPolicyTests
{
    [Fact]
    public void ShouldWaitForMainUi_WhenDefaultOrEmpty()
    {
        Assert.False(new ScriptGroupConfig().AllowNonMainUiStart);
        Assert.True(ScriptService.ShouldWaitForMainUi([]));
        Assert.True(ScriptService.ShouldWaitForMainUi([CreateProject(allowNonMainUiStart: false)]));
        Assert.True(ScriptService.ShouldWaitForMainUi([new ScriptGroupProject()]));
    }

    [Fact]
    public void ShouldWaitForMainUi_WhenAnyProjectHasNotOptedIn()
    {
        var optedIn = CreateProject(allowNonMainUiStart: true);
        var optedOut = CreateProject(allowNonMainUiStart: false);

        Assert.True(ScriptService.ShouldWaitForMainUi([optedIn, optedOut]));
    }

    [Fact]
    public void ShouldNotWaitForMainUi_WhenEveryProjectHasOptedIn()
    {
        Assert.False(ScriptService.ShouldWaitForMainUi([
            CreateProject(allowNonMainUiStart: true),
            CreateProject(allowNonMainUiStart: true)
        ]));
    }

    private static ScriptGroupProject CreateProject(bool allowNonMainUiStart)
    {
        var group = new ScriptGroup
        {
            Config = new ScriptGroupConfig { AllowNonMainUiStart = allowNonMainUiStart }
        };
        var project = new ScriptGroupProject();
        group.AddProject(project);
        return project;
    }
}
