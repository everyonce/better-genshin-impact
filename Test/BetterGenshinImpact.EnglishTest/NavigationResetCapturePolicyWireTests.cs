using System.Text;
using System.Text.Json;
using BetterGenshinImpact.Service.ExternalControl;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Authenticated reset selector parsing and fingerprint tests; no task, capture or input is created.</summary>
public sealed class NavigationResetCapturePolicyWireTests
{
    /// <summary>Omission is legacy shared; explicit null/unknown values and unrelated commands fail validation.</summary>
    [Theory]
    [InlineData("startNavigationReset", null, null)]
    [InlineData("startNavigationReset", "\"shared\"", null)]
    [InlineData("startNavigationReset", "\"task_owned_timer\"", null)]
    [InlineData("startNavigationReset", "null", "invalid_command_parameters")]
    [InlineData("startNavigationReset", "\"exclusive\"", "invalid_command_parameters")]
    [InlineData("startAgentStream", "\"shared\"", "unexpected_command_parameters")]
    [InlineData("status", "null", "unexpected_command_parameters")]
    public void ResetCaptureSelectorIsExact(string command, string? literal, string? rejection)
    {
        var json = "{\"version\":1,\"requestId\":\"" + Guid.NewGuid() + "\",\"createdAtUnixMs\":"
            + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + ",\"command\":\"" + command
            + "\",\"targetProcessId\":20,\"targetWindowsSessionId\":3,\"targetNonce\":\"fixed\""
            + (literal is null ? "" : ",\"capturePolicy\":" + literal) + "}";
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes(json), out var request));
        Assert.Equal(rejection, ExternalControlProtocol.ValidateRequest(request!, DateTimeOffset.UtcNow));
        Assert.Equal(literal is not null, request!.HasCapturePolicy);
        var serialized = JsonSerializer.SerializeToElement(request, ExternalControlProtocol.JsonOptions);
        Assert.False(serialized.TryGetProperty("CapturePolicy", out _));
        Assert.Equal(request.CapturePolicy is not null, serialized.TryGetProperty("capturePolicy", out _));
        if (request.CapturePolicy == "task_owned_timer")
        {
            Assert.NotEqual(ExternalControlProtocol.Fingerprint(request),
                ExternalControlProtocol.Fingerprint(request with { CapturePolicy = "shared" }));
            Assert.Null(ExternalControlProtocol.ValidateRequest(request with { TargetYawDegrees = 123.5 }, DateTimeOffset.UtcNow));
            Assert.Equal("unexpected_command_parameters", ExternalControlProtocol.ValidateRequest(
                request with { TimingContract = "v3" }, DateTimeOffset.UtcNow));
        }
    }

    /// <summary>Non-string selectors are malformed wire input, not a coerced shared mode.</summary>
    [Theory]
    [InlineData("true")]
    [InlineData("150")]
    [InlineData("[]")]
    public void ResetCaptureSelectorRejectsWrongJsonTypes(string literal) =>
        Assert.False(ExternalControlProtocol.TryDeserializeRequest(
            Encoding.UTF8.GetBytes("{\"command\":\"startNavigationReset\",\"capturePolicy\":" + literal + "}"), out _));
}
