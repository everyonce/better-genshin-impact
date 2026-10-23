using System.Runtime.InteropServices;
using System.Text.Json;
using BetterGenshinImpact.Helpers;
using BetterGenshinImpact.Service.ChildSession;
using BetterGenshinImpact.Service.ExternalControl;
using BetterGenshinImpact.Service.Instance;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise automation boundaries without launching a game, changing sessions, or running a scheduled task.</summary>
public sealed class RdpAutomationTests
{
    /// <summary>Desktop clone and quiet-mode flags must survive parsing without becoming a game-start action.</summary>
    [Fact]
    public void RootAutomationFlagsDoNotBecomeATask()
    {
        var options = CommandLineOptions.Parse(["BetterGI.exe", "--automation", "--desktopClone"]);
        Assert.True(options.AutomationMode);
        Assert.True(options.OpenDesktopClone);
        Assert.Equal(CommandLineAction.None, options.Action);
        Assert.Equal(BetterGiInstanceType.Primary, options.InstanceType);
    }

    /// <summary>Child replacement retains the role, explicit opt-in, startup action, and old-process handoff.</summary>
    [Fact]
    public void ChildAutomationAndRestartArgumentsRemainIndependent()
    {
        var options = CommandLineOptions.Parse(["BetterGI.exe", "--instance", "childsession", "--automation",
            "--restart-from-pid", "234", "start"]);
        Assert.True(options.AutomationMode);
        Assert.False(options.OpenDesktopClone);
        Assert.Equal(BetterGiInstanceType.ChildSession, options.InstanceType);
        Assert.Equal(234, options.RestartFromProcessId);
        Assert.Equal(CommandLineAction.Start, options.Action);
        Assert.False(CommandLineOptions.Parse(["BetterGI.exe"]).AutomationMode);
    }

    /// <summary>Machine mode does not permit a primary to run a game or an RDP child to launch host commands.</summary>
    [Theory]
    [InlineData("startChildSession", false, true, false, "automation_disabled")]
    [InlineData("launchChildCommand", true, false, true, "primary_required")]
    [InlineData("startChildGame", true, true, false, "rdp_child_required")]
    [InlineData("stopAutomationTasks", true, false, false, "rdp_child_required")]
    [InlineData("startChildSession", true, true, false, null)]
    [InlineData("startChildGame", true, false, true, null)]
    public void AutomationRequiresExplicitModeAndCorrectRole(string command, bool enabled, bool root, bool remoteChild, string? error)
        => Assert.Equal(error, ExternalControlService.AutomationTargetError(command, enabled, root, remoteChild));

    /// <summary>Structured command parameters are bounded and cannot be smuggled into another lifecycle command.</summary>
    [Fact]
    public void CommandEnvelopeRequiresExactTargetAndBoundedLocalArguments()
    {
        var now = DateTimeOffset.UtcNow;
        var valid = new ExternalControlRequest { Version = 1, RequestId = Guid.NewGuid(), CreatedAtUnixMs = now.ToUnixTimeMilliseconds(),
            Command = "launchChildCommand", TargetProcessId = 123, TargetWindowsSessionId = 2, TargetNonce = "current-root",
            ChildSessionId = 5, ExecutablePath = @"C:\Programs\Python\python.exe", WorkingDirectory = @"D:\work",
            Arguments = ["-I", "runner.py", "job.json"] };
        Assert.Null(ExternalControlProtocol.ValidateRequest(valid, now));
        Assert.Equal("target_required", ExternalControlProtocol.ValidateRequest(valid with { TargetNonce = null }, now));
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(valid with { ChildSessionId = 0 }, now));
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(valid with { ExecutablePath = @"\\server\share\python.exe" }, now));
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(valid with { WorkingDirectory = "relative" }, now));
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(valid with { Arguments = ["a\0b"] }, now));
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(valid with { Arguments = Enumerable.Repeat("x", 65).ToArray() }, now));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(valid with { Command = "startChildSession" }, now));
    }

    /// <summary>Windows' own parser must recover every argv item, including empty values and trailing backslashes.</summary>
    [Fact]
    public void SchedulerArgumentQuotingRoundTripsThroughWindows()
    {
        string[] args = ["", "simple", "a b", "quote\"here", @"D:\folder with spaces\", "slashes\\\\\"quote", "$(not-a-shell)", "a;b&c|d"];
        var commandLine = "program.exe " + string.Join(" ", args.Select(ChildSessionProcessLauncher.QuoteArgument));
        var vector = CommandLineToArgvW(commandLine, out var count);
        Assert.NotEqual(nint.Zero, vector);
        try
        {
            var actual = Enumerable.Range(1, count - 1)
                .Select(index => Marshal.PtrToStringUni(Marshal.ReadIntPtr(vector, index * nint.Size))).ToArray();
            Assert.Equal(args, actual);
        }
        finally { LocalFree(vector); }
        Assert.Throws<ArgumentException>(() => ChildSessionProcessLauncher.QuoteArgument("a\0b"));
    }

    /// <summary>Native parser for Windows command lines, used only with synthetic strings.</summary>
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern nint CommandLineToArgvW(string commandLine, out int count);

    /// <summary>Release the native parser's local heap allocation.</summary>
    [DllImport("kernel32.dll")]
    private static extern nint LocalFree(nint handle);
}
