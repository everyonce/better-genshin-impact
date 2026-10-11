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
    public void TargetedManualStopCannotCancelANewerTaskGeneration()
    {
        var context = new CancellationContext();
        var previousSource = context.Cts;
        context.Set();
        var currentSource = context.Cts;

        try
        {
            Assert.False(context.TryManualCancel(previousSource));
            Assert.False(currentSource.IsCancellationRequested);
            Assert.True(context.TryManualCancel(currentSource));
            Assert.True(currentSource.IsCancellationRequested);
            Assert.True(context.IsManualStop);
        }
        finally
        {
            previousSource.Dispose();
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
