using Fischless.GameCapture.DesktopDc;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Pure managed validation of the target facts actually used by DesktopDc; no target queries are executed.</summary>
public sealed class DesktopDcTargetTests
{
    /// <summary>Provide the whole valid record, including exact process/session and signed physical geometry.</summary>
    internal static DesktopDcTargetSnapshot Valid() => new()
    {
        Window = 100, ForegroundWindow = 100, ProcessId = 200, ProcessCreationFileTime = 123456789,
        ProcessActive = true, SessionId = 3, CallerSessionId = 3, Visible = true, Minimized = false,
        PerMonitorV2 = true, Dpi = 96, ClientRect = new RECT(0, 0, 1920, 1080),
        ScreenRect = new RECT(320, 180, 2240, 1260), VirtualScreen = new RECT(0, 0, 2560, 1440),
        Monitor = 300, MonitorRect = new RECT(0, 0, 2560, 1440), WindowStation = "WinSta0",
        ThreadDesktop = "Default", InputDesktop = "Default", ConnectionState = 0
    };

    /// <summary>Negative screen coordinates are preserved when both complete containment checks pass.</summary>
    [Fact]
    public void SignedCropCanBeContainedOnANegativeOriginMonitor()
    {
        var target = Valid() with
        {
            ScreenRect = new RECT(-1920, 0, 0, 1080), VirtualScreen = new RECT(-1920, 0, 2560, 1440),
            MonitorRect = new RECT(-1920, 0, 0, 1080)
        };
        target.Validate(100);
        Assert.Equal(-1920, target.ScreenRect.left);
    }

    /// <summary>Each target/session/desktop/DPI/crop predicate rejects independently.</summary>
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    [InlineData(5)]
    [InlineData(6)]
    [InlineData(7)]
    [InlineData(8)]
    [InlineData(9)]
    [InlineData(10)]
    [InlineData(11)]
    [InlineData(12)]
    [InlineData(13)]
    [InlineData(14)]
    [InlineData(15)]
    [InlineData(16)]
    [InlineData(17)]
    [InlineData(18)]
    [InlineData(19)]
    public void InvalidTargetFactsNeverAdmit(int mutation)
    {
        var original = Valid();
        var target = mutation switch
        {
            0 => original with { Window = 0 },
            1 => original with { ForegroundWindow = 101 },
            2 => original with { ProcessId = 0 },
            3 => original with { ProcessCreationFileTime = 0 },
            4 => original with { ProcessActive = false },
            5 => original with { SessionId = 4 },
            6 => original with { Visible = false },
            7 => original with { Minimized = true },
            8 => original with { PerMonitorV2 = false },
            9 => original with { Dpi = 0 },
            10 => original with { ClientRect = new RECT(0, 0, 1919, 1080) },
            11 => original with { ClientRect = new RECT(1, 0, 1920, 1080) },
            12 => original with { ScreenRect = new RECT(320, 180, 2241, 1260) },
            13 => original with { VirtualScreen = new RECT(0, 0, 2239, 1440) },
            14 => original with { MonitorRect = new RECT(321, 0, 2560, 1440) },
            15 => original with { Monitor = 0 },
            16 => original with { WindowStation = "Service-0x0" },
            17 => original with { ThreadDesktop = "Other", InputDesktop = "Other" },
            18 => original with { InputDesktop = "Winlogon" },
            _ => original with { ConnectionState = 4 }
        };
        Assert.Throws<InvalidOperationException>(() => target.Validate(100));
    }

    /// <summary>A valid snapshot cannot be applied to a different requested HWND.</summary>
    [Fact]
    public void ExactRequestedWindowIsRequired() =>
        Assert.Throws<InvalidOperationException>(() => Valid().Validate(101));

    /// <summary>A cleanup error preserves the original read failure and prevents a successful returned snapshot.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void QueryHandleFailureIsClosedOnceAndBothErrorsSurvive(bool closeThrows)
    {
        var primary = new InvalidOperationException("read failed");
        var closeCount = 0;
        var error = Assert.Throws<AggregateException>(() => DesktopDcTarget.WithQueryHandle<int>(123,
            handle =>
            {
                Assert.Equal((nint)123, handle);
                closeCount++;
                if (closeThrows) throw new InvalidOperationException("close failed");
                return false;
            }, () => throw primary, "fixture"));
        Assert.Same(primary, error.InnerExceptions[0]);
        Assert.True(DesktopDcCleanupException.IsPresent(error));
        Assert.Equal(1, closeCount);
    }

    /// <summary>Successful query cleanup returns the original value without another read or close.</summary>
    [Fact]
    public void QueryHandleSuccessPreservesResultIdentity()
    {
        var result = new object();
        var closed = 0;
        var actual = DesktopDcTarget.WithQueryHandle(123, _ => { closed++; return true; }, () => result, "fixture");
        Assert.Same(result, actual);
        Assert.Equal(1, closed);
    }
}
