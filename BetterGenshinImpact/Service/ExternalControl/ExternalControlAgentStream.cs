using System;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.GameTask.Runtime;
using Microsoft.Extensions.DependencyInjection;

namespace BetterGenshinImpact.Service.ExternalControl;

/// <summary>Fixed agent bridge entry points: no supplied script, group, pipe name, or executable.</summary>
public sealed partial class ExternalControlService
{
    /// <summary>Stable local endpoint; session and owner epochs still change on every start.</summary>
    internal const string AgentStreamPipeName = "BetterGI.Agent.local";
    /// <summary>Independent ownership keeps stop-agent limited to this stream.</summary>
    private readonly AgentStreamTaskOwner _agentStreamOwner = new();

    /// <summary>Start the fixed native bridge through the same TaskRunner scope used by AgentStream.js.</summary>
    private void BeginAgentStream(bool enableInput, string? observationProfile)
    {
        var profile = AgentObservationProfile.Normalize(observationProfile);
        var existing = _agentStreamOwner.Snapshot();
        if (existing.Running)
        {
            if (existing.CanReuse(enableInput, profile)) return;
            throw new InvalidOperationException("Stop the current agent and wait for cleanup before changing its input permission or observation profile.");
        }
        if (IsRestartBusy()) throw new InvalidOperationException("A task or lifecycle operation is already active.");
        var expected = _serviceProvider.GetRequiredService<GameRuntimeService>().Current
            ?? throw new InvalidOperationException("Start the RDP child game runtime before starting the agent stream.");
        // Denied input is rejected before the owner schedules TaskRunner initialization.
        if (enableInput) expected.ThrowIfDesktopControllerUnavailable();
        else expected.ThrowIfDesktopCaptureUnavailable();
        if (!_agentStreamOwner.TryStart(enableInput, (token, listening) =>
                new TaskRunner().RunAgentWithResultAsync(
                    (runtime, ct) => new AgentStreamSession(runtime, profile).RunAsync(AgentStreamPipeName, enableInput, ct, listening),
                    requestToken: token, requiredRuntime: expected, enableInput: enableInput), profile))
            throw new InvalidOperationException("This service already owns an agent stream.");
    }

    /// <summary>Cancel this stream only; its task remains busy until input and capture cleanup finish.</summary>
    private void StopAgentStream() => _agentStreamOwner.Cancel();

    /// <summary>Add precise agent status without treating an accepted launch as a listening server.</summary>
    private ExternalControlStatus AddAgentStreamStatus(ExternalControlStatus status)
    {
        var stream = _agentStreamOwner.Snapshot();
        return status with { AgentStreamState = stream.State, AgentStreamError = stream.Error,
            AgentStreamRunning = stream.Running, AgentInputEnabled = stream.EnableInput,
            AgentObservationProfile = stream.ObservationProfile,
            AgentPipeName = AgentStreamPipeName };
    }
}
