using System.Diagnostics;
using System.Text;
using System.Text.Json;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.GameTask.SoloTask.Execution;
using BetterGenshinImpact.Service.ExternalControl;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exact selector presence, replay identity and retained owner selection without runtime/game construction.</summary>
public sealed class NavigationBaselineShadowWireTests
{
    /// <summary>Valid pinned synthetic request; permissions/actual endpoint authentication remain outside this pure parser test.</summary>
    private static ExternalControlRequest Request() => new()
    {
        Version = 1, RequestId = Guid.NewGuid(), CreatedAtUnixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
        Command = "startNavigationBaseline", TargetProcessId = 20, TargetWindowsSessionId = 3, TargetNonce = "fixed"
    };

    /// <summary>Omitted legacy mode is legal, but explicit null is distinguished and rejected before dispatch.</summary>
    [Fact]
    public void PresenceDependenciesAndFingerprintAreExact()
    {
        var request = Request(); var now = DateTimeOffset.UtcNow;
        Assert.Null(ExternalControlProtocol.ValidateRequest(request, now));
        Assert.Equal("invalid_shadow_capture", ExternalControlProtocol.ValidateRequest(request with { ShadowCapture = null }, now));
        Assert.Equal("invalid_shadow_capture", ExternalControlProtocol.ValidateRequest(request with { ShadowCapture = "other" }, now));
        Assert.Equal("shadow_capture_requires_v4_task_owned_timer", ExternalControlProtocol.ValidateRequest(
            request with { ShadowCapture = NavigationBaselineShadowMode.Rgb192 }, now));
        var selected = request with { ShadowCapture = NavigationBaselineShadowMode.Rgb192,
            TimingContract = NavigationBaselineTiming.V4, CapturePolicy = NavigationBaselineCapturePolicy.TaskOwnedTimer };
        Assert.Null(ExternalControlProtocol.ValidateRequest(selected, now));
        Assert.Equal("invalid_shadow_capture", ExternalControlProtocol.ValidateRequest(selected with { Command = "status" }, now));
        Assert.NotEqual(ExternalControlProtocol.Fingerprint(request), ExternalControlProtocol.Fingerprint(selected));
        var json = JsonSerializer.SerializeToUtf8Bytes(selected, ExternalControlProtocol.JsonOptions);
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(json, out var parsed));
        Assert.True(parsed!.HasShadowCapture); Assert.Equal(NavigationBaselineShadowMode.Rgb192, parsed.ShadowCapture);
        Assert.Equal(ExternalControlProtocol.Fingerprint(selected), ExternalControlProtocol.Fingerprint(parsed));
    }

    /// <summary>An omitted selector survives ordinary request serialization; incoming explicit null remains invalid.</summary>
    [Theory]
    [InlineData("status")] [InlineData("setCaptureMode")] [InlineData("startNavigationBaseline")]
    public void OmittedSelectorRoundTripRetainsLegacyAdmission(string command)
    {
        var request = command switch
        {
            "status" => Request() with { Command = command, TargetProcessId = null, TargetWindowsSessionId = null, TargetNonce = null },
            "setCaptureMode" => Request() with { Command = command, CaptureMode = Fischless.GameCapture.CaptureModes.WindowsGraphicsCapture },
            _ => Request() with { Command = command }
        };
        var json = JsonSerializer.SerializeToUtf8Bytes(request, ExternalControlProtocol.JsonOptions);
        Assert.DoesNotContain("\"shadowCapture\":", Encoding.UTF8.GetString(json));
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(json, out var parsed));
        Assert.False(parsed!.HasShadowCapture); Assert.Null(parsed.ShadowCapture);
        Assert.Null(ExternalControlProtocol.ValidateRequest(parsed, DateTimeOffset.UtcNow));
        var supplied = Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(json)[..^1] + ",\"shadowCapture\":null}");
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(supplied, out var explicitNull));
        Assert.True(explicitNull!.HasShadowCapture);
        Assert.Equal("invalid_shadow_capture", ExternalControlProtocol.ValidateRequest(explicitNull, DateTimeOffset.UtcNow));
    }

    /// <summary>Invalid opt-in never reaches the callback; valid selection cannot be overwritten while cleanup is active.</summary>
    [Fact]
    public async Task OwnerSelectionIsImmutableThroughFailureAndCleanup()
    {
        var owner = new NavigationBaselineTaskOwner(); var invoked = false;
        Assert.Throws<ArgumentException>(() => owner.TryStart(20, 3, (_, _, _) =>
        { invoked = true; throw new Exception("unreachable"); }, shadowCapture: NavigationBaselineShadowMode.Rgb192));
        Assert.False(invoked); Assert.Null(owner.Snapshot().ShadowCapture);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finish = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Assert.True(owner.TryStart(20, 3, async (_, _, phase) =>
        {
            phase("cleaning_up"); entered.SetResult(); await finish.Task;
            return (new SoloTaskRunResult { Outcome = SoloTaskRunOutcome.Faulted, ErrorMessage = "synthetic_failure" },
                (NavigationBaselineRunResult?)null);
        }, timingContract: NavigationBaselineTiming.V4, capturePolicy: NavigationBaselineCapturePolicy.TaskOwnedTimer,
            shadowCapture: NavigationBaselineShadowMode.Rgb192));
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        Assert.Equal(NavigationBaselineShadowMode.Rgb192, owner.Snapshot().ShadowCapture);
        Assert.False(owner.TryStart(20, 3, (_, _, _) => throw new Exception("unreachable")));
        Assert.Equal(NavigationBaselineShadowMode.Rgb192, owner.Snapshot().ShadowCapture);
        finish.SetResult(); var elapsed = Stopwatch.StartNew();
        while (owner.Running && elapsed.Elapsed < TimeSpan.FromSeconds(5)) await Task.Delay(1);
        Assert.False(owner.Running); Assert.Equal("failed", owner.Snapshot().State);
        Assert.Equal(NavigationBaselineShadowMode.Rgb192, owner.Snapshot().ShadowCapture);
    }

    /// <summary>Compact status contains only selector/capability, while the bounded archive summary stays in the dedicated result.</summary>
    [Fact]
    public void ArchiveSummaryUsesExplicitWireNamesAndFitsLegacyEnvelope()
    {
        var summary = new NavigationBaselineShadowEvidence(NavigationBaselineShadowMode.Rgb192, false, false,
            new string('x', 256), 4096, 1024, 1023, 0, 1, 3071, 2,
            @"D:\User\NavigationBaselineShadows\0123456789abcdef0123456789abcdef\manifest.json", new('A', 64), new('B', 64));
        var payload = JsonSerializer.SerializeToUtf8Bytes(summary, ExternalControlProtocol.JsonOptions);
        using var doc = JsonDocument.Parse(payload);
        Assert.False(doc.RootElement.GetProperty("workerRetired").GetBoolean());
        Assert.Equal(1024, doc.RootElement.GetProperty("framesAccepted").GetInt32());
        Assert.True(payload.Length < 2048);
        var status = JsonSerializer.SerializeToUtf8Bytes(new NavigationBaselineStatus(), ExternalControlProtocol.JsonOptions);
        Assert.True(status.Length < 8192);
        Assert.DoesNotContain("\"shadowCapture\":", Encoding.UTF8.GetString(status));
        Assert.Contains("\"shadowCaptureVersion\":1", Encoding.UTF8.GetString(status));
        Assert.Equal(8192, ExternalControlProtocol.MaximumResponseBytes("status"));
        Assert.Equal(32768, ExternalControlProtocol.MaximumResponseBytes("navigationBaselineResult"));
    }
}
