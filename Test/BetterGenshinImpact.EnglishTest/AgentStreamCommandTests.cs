using System.Text;
using System.Text.Json;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.SoloTask.Execution;
using BetterGenshinImpact.Service.ExternalControl;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Headless ownership and protocol checks; never creates a runtime, pipe, window, or input event.</summary>
public sealed class AgentStreamCommandTests
{
    /// <summary>The input flag is optional, typed, specific to start, and cannot carry executable/script parameters.</summary>
    [Fact]
    public void StreamRequestDefaultsToObservationAndRequiresPinnedTarget()
    {
        var now = DateTimeOffset.UtcNow;
        var request = new ExternalControlRequest { Version = 1, RequestId = Guid.NewGuid(),
            CreatedAtUnixMs = now.ToUnixTimeMilliseconds(), Command = "startAgentStream",
            TargetProcessId = 123, TargetWindowsSessionId = 3, TargetNonce = "current-child" };
        Assert.Null(ExternalControlProtocol.ValidateRequest(request, now));
        Assert.False(request.EnableInput == true);
        Assert.Null(ExternalControlProtocol.ValidateRequest(request with { EnableInput = true }, now));
        Assert.Equal("target_required", ExternalControlProtocol.ValidateRequest(request with { TargetNonce = null }, now));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(request with { Arguments = ["other.js"] }, now));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(request with { Command = "stopAgentStream", EnableInput = true }, now));
        Assert.False(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes("{\"enableInput\":\"true\"}"), out _));
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(request), ExternalControlProtocol.Fingerprint(request with { EnableInput = true }));
    }

    /// <summary>Only known exact encodings may be requested; omission and null keep the existing profile.</summary>
    [Fact]
    public void ObservationProfileIsTypedOptionalAndSpecificToStart()
    {
        var now = DateTimeOffset.UtcNow;
        var request = new ExternalControlRequest { Version = 1, RequestId = Guid.NewGuid(),
            CreatedAtUnixMs = now.ToUnixTimeMilliseconds(), Command = "startAgentStream",
            TargetProcessId = 123, TargetWindowsSessionId = 3, TargetNonce = "current-child" };
        Assert.Null(ExternalControlProtocol.ValidateRequest(request, now));
        foreach (var profile in new string?[] { null, AgentObservationProfile.Legacy, AgentObservationProfile.P2PNativeHamming192 })
            Assert.Null(ExternalControlProtocol.ValidateRequest(request with { ObservationProfile = profile }, now));
        foreach (var invalid in new[] { "", "unknown", "P2P-NATIVE-HAMMING-192-V1" })
            Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(request with { ObservationProfile = invalid }, now));
        foreach (var command in new[] { "status", "stopAgentStream", "startChildSession", "startNavigationReset" })
        {
            Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(
                request with { Command = command, ObservationProfile = AgentObservationProfile.Legacy }, now));
            Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(
                request with { Command = command, ObservationProfile = null }, now));
        }
        Assert.False(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes("{\"observationProfile\":1}"), out _));
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes("{\"observationProfile\":null}"), out var explicitNull));
        Assert.True(explicitNull!.HasObservationProfile);
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(request), ExternalControlProtocol.Fingerprint(
            request with { ObservationProfile = AgentObservationProfile.P2PNativeHamming192 }));
    }

    /// <summary>Machine status names the current/last profile independently of whether task cleanup is complete.</summary>
    [Fact]
    public void StreamStatusSerializesItsObservationProfile()
    {
        Assert.Equal(AgentObservationProfile.Legacy, new ExternalControlStatus().AgentObservationProfile);
        var response = ExternalControlProtocol.SerializeResponse(new ExternalControlResponse
        {
            Success = true,
            Status = new ExternalControlStatus { AgentObservationProfile = AgentObservationProfile.P2PNativeHamming192 }
        });
        using var document = JsonDocument.Parse(response);
        Assert.Equal(AgentObservationProfile.P2PNativeHamming192,
            document.RootElement.GetProperty("status").GetProperty("agentObservationProfile").GetString());
    }

    /// <summary>A live task cannot change encoding, and its final profile remains available after cleanup.</summary>
    [Fact]
    public async Task ObservationProfileIsImmutableUntilTaskCleanupCompletes()
    {
        var owner = new AgentStreamTaskOwner();
        Assert.Equal(AgentObservationProfile.Legacy, owner.Snapshot().ObservationProfile);
        var finish = new TaskCompletionSource<SoloTaskRunResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        Assert.True(owner.TryStart(false, (_, _) => finish.Task, AgentObservationProfile.P2PNativeHamming192));
        var active = owner.Snapshot();
        Assert.True(active.CanReuse(false, AgentObservationProfile.P2PNativeHamming192));
        Assert.False(active.CanReuse(false, AgentObservationProfile.Legacy));
        Assert.False(active.CanReuse(true, AgentObservationProfile.P2PNativeHamming192));
        Assert.False(owner.TryStart(false, (_, _) => throw new InvalidOperationException("must not execute"), AgentObservationProfile.Legacy));
        Assert.Equal(AgentObservationProfile.P2PNativeHamming192, owner.Snapshot().ObservationProfile);
        owner.Cancel();
        Assert.False(owner.Snapshot().CanReuse(false, AgentObservationProfile.P2PNativeHamming192));
        finish.SetResult(new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Cancelled });
        await WaitForIdleAsync(owner);
        Assert.Equal(AgentObservationProfile.P2PNativeHamming192, owner.Snapshot().ObservationProfile);
        Assert.False(owner.Snapshot().CanReuse(false, AgentObservationProfile.P2PNativeHamming192));
        Assert.True(owner.TryStart(false, (_, _) => Task.FromResult(new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed }), null));
        await WaitForIdleAsync(owner);
        Assert.Equal(AgentObservationProfile.Legacy, owner.Snapshot().ObservationProfile);
        Assert.Throws<ArgumentException>(() => owner.TryStart(false, (_, _) => throw new InvalidOperationException("must not execute"), "unknown"));
        Assert.False(owner.Snapshot().Running);
    }

    /// <summary>Neither primary/console processes nor a missing automation opt-in may launch or stop an agent.</summary>
    [Theory]
    [InlineData("startAgentStream", false, false, true, "automation_disabled")]
    [InlineData("startAgentStream", true, true, false, "rdp_child_required")]
    [InlineData("startAgentStream", true, false, false, "rdp_child_required")]
    [InlineData("stopAgentStream", true, true, false, "rdp_child_required")]
    [InlineData("startAgentStream", true, false, true, null)]
    [InlineData("stopAgentStream", true, false, true, null)]
    public void StreamCommandsRequireActualOptedInChild(string command, bool enabled, bool root, bool remote, string? error)
    {
        Assert.True(ExternalControlProtocol.IsAutomationCommand(command));
        Assert.Equal(error, ExternalControlService.AutomationTargetError(command, enabled, root, remote));
    }

    /// <summary>Cancellation does not free ownership while executor cleanup still holds input/runtime resources.</summary>
    [Fact]
    public async Task StopRetainsLeaseUntilCleanupAndCannotUpgradeRunningInputPermission()
    {
        var owner = new AgentStreamTaskOwner();
        var listening = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var cancelled = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var cleanup = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Assert.True(owner.TryStart(false, async (token, ready) =>
        {
            using var registration = token.Register(() => cancelled.TrySetResult());
            ready();
            listening.SetResult();
            await cleanup.Task;
            return new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Cancelled };
        }));
        await listening.Task.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.Equal("listening", owner.Snapshot().State);
        Assert.False(owner.Snapshot().EnableInput);
        Assert.False(owner.TryStart(true, (_, _) => throw new InvalidOperationException("must not run")));
        var stop = owner.StopAsync(CancellationToken.None);
        await cancelled.Task.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.False(stop.IsCompleted);
        Assert.True(owner.Snapshot().Running);
        Assert.Equal("stopping", owner.Snapshot().State);
        Assert.False(owner.TryStart(true, (_, _) => throw new InvalidOperationException("must not run")));
        cleanup.SetResult();
        await stop.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.False(owner.Snapshot().Running);
        Assert.Equal("stopped", owner.Snapshot().State);
        Assert.True(owner.TryStart(true, (_, ready) =>
        {
            ready();
            return Task.FromResult(new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed });
        }));
        await WaitForIdleAsync(owner);
        Assert.Equal("completed", owner.Snapshot().State);
        Assert.False(owner.Snapshot().EnableInput);
    }

    /// <summary>TaskRunner reports rejection as a result, so an accepted launch must not hide it.</summary>
    [Theory]
    [InlineData(SoloTaskRunOutcome.Rejected, "rejected")]
    [InlineData(SoloTaskRunOutcome.Faulted, "failed")]
    public async Task FailedTaskResultIsPublishedAndReleasesOwnership(SoloTaskRunOutcome outcome, string expected)
    {
        var owner = new AgentStreamTaskOwner();
        Assert.True(owner.TryStart(false, (_, _) => Task.FromResult(new SoloTaskRunResult
            { Outcome = outcome, ErrorMessage = "test runtime unavailable" })));
        await WaitForIdleAsync(owner);
        Assert.Equal(expected, owner.Snapshot().State);
        Assert.Equal("test runtime unavailable", owner.Snapshot().Error);
        Assert.False(owner.Snapshot().Running);
    }

    /// <summary>Concurrent callers get exactly one executor and cannot replace its permission.</summary>
    [Fact]
    public async Task ConcurrentStartsAcquireExactlyOneLease()
    {
        var owner = new AgentStreamTaskOwner();
        var release = new TaskCompletionSource<SoloTaskRunResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        var accepted = 0;
        Parallel.For(0, 32, _ =>
        {
            if (owner.TryStart(false, (_, _) => release.Task)) Interlocked.Increment(ref accepted);
        });
        Assert.Equal(1, accepted);
        release.SetResult(new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Completed });
        await WaitForIdleAsync(owner);
        owner.Cancel();
        Assert.Equal("completed", owner.Snapshot().State);
    }

    /// <summary>Wait only for synthetic tasks with a bounded test deadline.</summary>
    private static async Task WaitForIdleAsync(AgentStreamTaskOwner owner)
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        while (owner.Snapshot().Running) await Task.Delay(5, deadline.Token);
    }
}
