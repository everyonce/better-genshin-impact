using BetterGenshinImpact.Service.ChildSession;

namespace BetterGenshinImpact.UnitTest.ServiceTests.ChildSession;

public class ChildSessionCursorCaptureTests
{
    [Theory]
    [InlineData(true, true, false, true)]
    [InlineData(false, true, false, false)]
    [InlineData(true, false, false, false)]
    [InlineData(true, true, true, false)]
    public void HostWindowMustBeVisibleActiveAndNotMinimized(
        bool isVisible,
        bool isActive,
        bool isMinimized,
        bool expected)
    {
        Assert.Equal(
            expected,
            ChildSessionService.IsHostWindowEligibleForRelativeMouseCapture(
                isVisible,
                isActive,
                isMinimized));
    }
}
