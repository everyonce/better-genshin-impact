using BetterGenshinImpact.Helpers;

namespace BetterGenshinImpact.UnitTest.Helpers;

public sealed class GameWindowFocusTests
{
    [Theory]
    [InlineData(0L)]
    [InlineData(-1L)]
    public void InvalidBoundHandleStopsBeforeForegroundRecovery(long value)
    {
        Assert.False(GameWindowFocus.TryFocus((nint)value, out var failure));
        Assert.Equal("Bound game window is no longer valid.", failure);
    }

    [Fact]
    public void MissingBoundWindowDiagnosticsDoNotInventAnOwner()
    {
        var diagnostic = GameWindowFocus.GetDiagnostics(nint.Zero);
        Assert.Equal(0L, diagnostic.Bound.Handle);
        Assert.Null(diagnostic.Bound.ProcessId);
        Assert.Null(diagnostic.Bound.SessionId);
        Assert.Null(diagnostic.Bound.ProcessName);
        Assert.Null(diagnostic.Bound.ClassName);
    }
}
