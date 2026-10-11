using System;
using System.Text;
using BetterGenshinImpact.Core.Script;
using BetterGenshinImpact.Service.ExternalControl;

namespace BetterGenshinImpact.UnitTest.ServiceTests.ExternalControl;

public class ExternalControlProtocolTests
{
    [Fact]
    public void OptInRequiresVersionOneAndExplicitEnabledFlag()
    {
        Assert.True(ExternalControlOptIn.IsEnabled("{\"version\":1,\"enabled\":true}"));
        Assert.False(ExternalControlOptIn.IsEnabled("{\"version\":1,\"enabled\":false}"));
        Assert.False(ExternalControlOptIn.IsEnabled("{\"version\":2,\"enabled\":true}"));
        Assert.False(ExternalControlOptIn.IsEnabled("not-json"));
        Assert.False(ExternalControlOptIn.IsAppRestartEnabled("{\"version\":1,\"enabled\":true}"));
        Assert.True(ExternalControlOptIn.IsAppRestartEnabled("{\"version\":1,\"enabled\":true,\"allowAppRestart\":true}"));
        Assert.False(ExternalControlOptIn.IsAppRestartEnabled("{\"version\":1,\"enabled\":false,\"allowAppRestart\":true}"));
    }

    [Fact]
    public void RequestParserRejectsUnknownProperties()
    {
        var payload = Encoding.UTF8.GetBytes(
            "{\"version\":1,\"requestId\":\"8c14fa26-d655-4df1-b1bd-37d6dc3c177b\","
            + "\"createdAtUnixMs\":1,\"command\":\"status\",\"shell\":\"whoami\"}");

        Assert.False(ExternalControlProtocol.TryDeserializeRequest(payload, out _));
    }

    [Fact]
    public void StatusRequestAllowsNoMutationTarget()
    {
        var now = DateTimeOffset.UtcNow;
        var request = CreateRequest(now, "status");

        Assert.Null(ExternalControlProtocol.ValidateRequest(request, now));
    }

    [Fact]
    public void MutationRequiresExactTargetFields()
    {
        var now = DateTimeOffset.UtcNow;
        var incomplete = CreateRequest(now, "startPilot");
        var complete = incomplete with
        {
            TargetProcessId = 42,
            TargetWindowsSessionId = 5,
            TargetNonce = "instance-nonce"
        };

        Assert.Equal("target_required", ExternalControlProtocol.ValidateRequest(incomplete, now));
        Assert.Null(ExternalControlProtocol.ValidateRequest(complete, now));

        var restart = CreateRequest(now, "restartApp") with
        {
            TargetProcessId = 42,
            TargetWindowsSessionId = 5,
            TargetNonce = "instance-nonce"
        };
        Assert.Null(ExternalControlProtocol.ValidateRequest(restart, now));
        Assert.Equal("target_required", ExternalControlProtocol.ValidateRequest(restart with { TargetNonce = null }, now));
    }

    [Fact]
    public void RejectsStaleFutureAndUnsupportedRequests()
    {
        var now = DateTimeOffset.UtcNow;

        Assert.Equal(
            "stale_request",
            ExternalControlProtocol.ValidateRequest(CreateRequest(now.AddSeconds(-31), "status"), now));
        Assert.Equal(
            "stale_request",
            ExternalControlProtocol.ValidateRequest(CreateRequest(now.AddSeconds(31), "status"), now));
        Assert.Equal(
            "unsupported_command",
            ExternalControlProtocol.ValidateRequest(CreateRequest(now, "runScript"), now));
    }

    [Theory]
    [InlineData("installRecoveryLauncher")]
    [InlineData("restartHost")]
    [InlineData("shutdownApp")]
    public void RecoveryCommandsRequireExactTargetAndRejectPayloadPaths(string command)
    {
        var now = DateTimeOffset.UtcNow;
        var request = CreateRequest(now, command);
        Assert.Equal("target_required", ExternalControlProtocol.ValidateRequest(request, now));
        Assert.Null(ExternalControlProtocol.ValidateRequest(request with
            { TargetProcessId = 42, TargetWindowsSessionId = 6, TargetNonce = "nonce" }, now));
        var payload = Encoding.UTF8.GetBytes("{\"command\":\"" + command + "\",\"path\":\"C:/untrusted.exe\"}");
        Assert.False(ExternalControlProtocol.TryDeserializeRequest(payload, out _));
    }

    [Theory]
    [InlineData("idle", true)]
    [InlineData("starting", true)]
    [InlineData("running", true)]
    [InlineData("stopped", false)]
    [InlineData("faulted", false)]
    [InlineData(null, false)]
    public void CooperativeStopAllowsLivePilotListenerStates(string? state, bool expected)
    {
        Assert.Equal(expected, ExternalControlService.IsCancellablePilotState(state));
    }

    [Fact]
    public void OwnedStopAllowsFreshFaultedListenerButRejectsStaleUnownedOrMismatchedHeartbeat()
    {
        Assert.True(ExternalControlService.CanStopOwnedPilot(
            ownedTaskCurrent: true,
            currentOwnedHeartbeat: true,
            heartbeatFresh: true,
            heartbeatSession: "script-1",
            ownedScriptSession: "script-1",
            heartbeatState: "faulted"));

        Assert.False(ExternalControlService.CanStopOwnedPilot(
            ownedTaskCurrent: true,
            currentOwnedHeartbeat: true,
            heartbeatFresh: false,
            heartbeatSession: "script-1",
            ownedScriptSession: "script-1",
            heartbeatState: "faulted"));
        Assert.False(ExternalControlService.CanStopOwnedPilot(
            ownedTaskCurrent: false,
            currentOwnedHeartbeat: true,
            heartbeatFresh: true,
            heartbeatSession: "script-1",
            ownedScriptSession: "script-1",
            heartbeatState: "faulted"));
        Assert.False(ExternalControlService.CanStopOwnedPilot(
            ownedTaskCurrent: true,
            currentOwnedHeartbeat: false,
            heartbeatFresh: true,
            heartbeatSession: "script-1",
            ownedScriptSession: "script-1",
            heartbeatState: "faulted"));
        Assert.False(ExternalControlService.CanStopOwnedPilot(
            ownedTaskCurrent: true,
            currentOwnedHeartbeat: true,
            heartbeatFresh: true,
            heartbeatSession: "other-script",
            ownedScriptSession: "script-1",
            heartbeatState: "faulted"));
    }

    [Fact]
    public void ReplayCacheExpiryMatchesRequestFreshnessWindowIncludingFutureDatedRequests()
    {
        var now = DateTimeOffset.FromUnixTimeMilliseconds(DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
        var requestCreated = now.AddSeconds(20);
        var expiresAt = ExternalControlProtocol.GetReplayExpiry(requestCreated.ToUnixTimeMilliseconds());

        Assert.Equal(
            requestCreated + ExternalControlProtocol.MaximumRequestAge + TimeSpan.FromMilliseconds(1),
            expiresAt);
        Assert.True(expiresAt - now <= TimeSpan.FromSeconds(50) + TimeSpan.FromMilliseconds(1));
    }

    [Fact]
    public void TargetedManualStopUsesTheFinalGenerationAfterRunMultiAndTaskRunnerReset()
    {
        var context = new CancellationContext();
        var initialSource = context.Cts;
        context.Set(); // ScriptService.RunMulti
        var runMultiSource = context.Cts;
        context.Set();
        var taskRunnerSource = context.Cts;

        try
        {
            Assert.False(context.TryManualCancel(initialSource));
            Assert.False(context.TryManualCancel(runMultiSource));
            Assert.False(taskRunnerSource.IsCancellationRequested);
            Assert.True(context.TryManualCancel(taskRunnerSource));
            Assert.True(taskRunnerSource.IsCancellationRequested);
            Assert.True(context.IsManualStop);
        }
        finally
        {
            initialSource.Dispose();
            runMultiSource.Dispose();
            context.Clear();
        }
    }

    private static ExternalControlRequest CreateRequest(DateTimeOffset createdAt, string command) => new()
    {
        Version = ExternalControlProtocol.Version,
        RequestId = Guid.NewGuid(),
        CreatedAtUnixMs = createdAt.ToUnixTimeMilliseconds(),
        Command = command
    };
}
