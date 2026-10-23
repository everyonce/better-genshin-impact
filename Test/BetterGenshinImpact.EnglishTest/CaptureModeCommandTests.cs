using System.Text;
using System.Text.Json;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Capture-switch contract and ordering tests using isolated gates and fake runtime callbacks.</summary>
public sealed class CaptureModeCommandTests
{
    /// <summary>Only exact named members of the real capture enum are accepted by the wire format.</summary>
    [Fact]
    public void NamedBackendRoundTripsAndInvalidWireValuesAreRejected()
    {
        foreach (var mode in Enum.GetValues<CaptureModes>())
        {
            var request = Request(mode);
            var bytes = JsonSerializer.SerializeToUtf8Bytes(request, ExternalControlProtocol.JsonOptions);
            Assert.True(ExternalControlProtocol.TryDeserializeRequest(bytes, out var decoded));
            Assert.Equal(mode, decoded!.CaptureMode);
            Assert.Null(ExternalControlProtocol.ValidateRequest(decoded, DateTimeOffset.UtcNow));
        }
        foreach (var value in new[] { "1", "999", "true", "\"1\"", "\"windowsgraphicscapture\"", "\"other\"",
                     "\"BitBlt,WindowsGraphicsCapture\"", "{}" })
            Assert.False(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes("{\"captureMode\":" + value + "}"), out _));
    }

    /// <summary>No other command gains a capture/config parameter; the mutation still requires a pinned identity.</summary>
    [Fact]
    public void ModeParameterIsCommandSpecificAndRequired()
    {
        var now = DateTimeOffset.UtcNow;
        var valid = Request(CaptureModes.WindowsGraphicsCapture);
        Assert.True(ExternalControlProtocol.IsAutomationCommand(valid.Command));
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(valid with { CaptureMode = null }, now));
        Assert.Equal("invalid_command_parameters", ExternalControlProtocol.ValidateRequest(valid with { CaptureMode = (CaptureModes)99 }, now));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(valid with { Command = "startChildGame" }, now));
        Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(valid with { Arguments = ["arbitrary.exe"] }, now));
        Assert.Equal("target_required", ExternalControlProtocol.ValidateRequest(valid with { TargetNonce = null }, now));
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(valid),
            ExternalControlProtocol.Fingerprint(valid with { CaptureMode = CaptureModes.BitBlt }));
        Assert.Equal("automation_disabled", ExternalControlService.AutomationTargetError(valid.Command!, false, false, true));
        Assert.Equal("rdp_child_required", ExternalControlService.AutomationTargetError(valid.Command!, true, true, false));
        Assert.Equal("rdp_child_required", ExternalControlService.AutomationTargetError(valid.Command!, true, false, false));
        Assert.Null(ExternalControlService.AutomationTargetError(valid.Command!, true, false, true));
    }

    /// <summary>Configuration changes only after the old runtime stops, and no competing task can acquire the gate.</summary>
    [Fact]
    public async Task SwitchReservesTaskOwnershipAndOrdersStopSelectStart()
    {
        using var gate = new SemaphoreSlim(1, 1);
        var steps = new List<string>();
        var selected = CaptureModes.BitBlt;
        await CaptureModeSwitch.ReattachAsync(CaptureModes.WindowsGraphicsCapture, gate,
            () => { Assert.Equal(0, gate.CurrentCount); steps.Add("stop"); return Task.CompletedTask; },
            mode => { Assert.Equal(new[] { "stop" }, steps); selected = mode; steps.Add("select"); },
            () => { Assert.Equal(new[] { "stop", "select" }, steps); steps.Add("flush"); },
            _ => { Assert.Equal(0, gate.CurrentCount); Assert.Equal(CaptureModes.WindowsGraphicsCapture, selected);
                steps.Add("start"); return Task.FromResult(true); }, CancellationToken.None);
        Assert.Equal(new[] { "stop", "select", "flush", "start" }, steps);
        Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>A task already holding the gate rejects the switch before stop or config mutation.</summary>
    [Fact]
    public async Task BusyTaskCannotBeInterruptedBySwitch()
    {
        using var gate = new SemaphoreSlim(0, 1);
        await Assert.ThrowsAsync<InvalidOperationException>(() => CaptureModeSwitch.ReattachAsync(CaptureModes.BitBlt, gate,
            () => throw new Exception("must not stop"), _ => throw new Exception("must not select"),
            () => throw new Exception("must not persist"),
            _ => throw new Exception("must not start"), CancellationToken.None));
        Assert.Equal(0, gate.CurrentCount);
    }

    /// <summary>Cancellation during noncancelable stop retains ownership until cleanup and never changes the config.</summary>
    [Fact]
    public async Task CancellationDrainsStopBeforeReleasingGateAndSkipsSelection()
    {
        using var gate = new SemaphoreSlim(1, 1);
        using var cancel = new CancellationTokenSource();
        var stopped = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var task = CaptureModeSwitch.ReattachAsync(CaptureModes.WindowsGraphicsCapture, gate, () => stopped.Task,
            _ => throw new Exception("must not select"), () => throw new Exception("must not persist"),
            _ => throw new Exception("must not start"), cancel.Token);
        cancel.Cancel();
        Assert.False(task.IsCompleted);
        Assert.Equal(0, gate.CurrentCount);
        stopped.SetResult();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => task);
        Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>The bounded startup token reaches acquisition, and failure cannot masquerade as game readiness.</summary>
    [Fact]
    public async Task StartupFailureOrCancellationReleasesGateAndSurfacesError()
    {
        using var gate = new SemaphoreSlim(1, 1);
        await Assert.ThrowsAsync<InvalidOperationException>(() => CaptureModeSwitch.ReattachAsync(CaptureModes.WindowsGraphicsCapture, gate,
            () => Task.CompletedTask, _ => { }, () => { }, _ => Task.FromResult(false), CancellationToken.None));
        Assert.Equal(1, gate.CurrentCount);
        using var cancel = new CancellationTokenSource();
        var starting = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var task = CaptureModeSwitch.ReattachAsync(CaptureModes.WindowsGraphicsCapture, gate,
            () => Task.CompletedTask, _ => { }, () => { }, async token =>
            { starting.SetResult(); await Task.Delay(Timeout.Infinite, token); return true; }, cancel.Token);
        await starting.Task.WaitAsync(TimeSpan.FromSeconds(3));
        cancel.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => task);
        Assert.Equal(1, gate.CurrentCount);
    }

    /// <summary>Construct a synthetic nonce-bound child request without opening a control pipe.</summary>
    private static ExternalControlRequest Request(CaptureModes mode) => new()
    {
        Version = 1, RequestId = Guid.NewGuid(), CreatedAtUnixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
        Command = "setCaptureMode", CaptureMode = mode, TargetProcessId = 123,
        TargetWindowsSessionId = 3, TargetNonce = "child-epoch"
    };
}
