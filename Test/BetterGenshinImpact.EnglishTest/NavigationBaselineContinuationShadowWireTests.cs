using System;
using System.Text;
using System.Text.Json;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.Service.ExternalControl;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Composed selector identity and null-presence semantics, without runtime or endpoint construction.</summary>
public sealed class NavigationBaselineContinuationShadowWireTests
{
    /// <summary>Every supported route can independently opt into the passive archive; reverse retains its required predecessor.</summary>
    [Theory]
    [InlineData(NavigationBaselineTask.ProfileId, false)]
    [InlineData(NavigationBaselineTask.ProfileId, true)]
    [InlineData(NavigationBaselineRouteProfile.TwoLegId, false)]
    [InlineData(NavigationBaselineRouteProfile.TwoLegId, true)]
    [InlineData(NavigationBaselineRouteProfile.ReverseId, false)]
    [InlineData(NavigationBaselineRouteProfile.ReverseId, true)]
    public void IndependentSelectorsRoundTripTogether(string route, bool shadow)
    {
        var request = new ExternalControlRequest
        {
            Version = 1, RequestId = Guid.NewGuid(), CreatedAtUnixMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
            Command = "startNavigationBaseline", TargetProcessId = 20, TargetWindowsSessionId = 3, TargetNonce = "fixed",
            TimingContract = "v4", CapturePolicy = "task_owned_timer", RouteProfile = route
        };
        if (route == NavigationBaselineRouteProfile.ReverseId) request = request with { ContinuationFromRunId = new string('a', 32) };
        if (shadow) request = request with { ShadowCapture = NavigationBaselineShadowMode.Rgb192 };
        Assert.Null(ExternalControlProtocol.ValidateRequest(request, DateTimeOffset.UtcNow));
        var json = JsonSerializer.SerializeToUtf8Bytes(request, ExternalControlProtocol.JsonOptions);
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(json, out var parsed));
        Assert.Null(ExternalControlProtocol.ValidateRequest(parsed!, DateTimeOffset.UtcNow));
        Assert.Equal(shadow, parsed!.HasShadowCapture);
        Assert.Equal(route == NavigationBaselineRouteProfile.ReverseId, parsed.HasContinuationFromRunId);
        Assert.Equal(ExternalControlProtocol.Fingerprint(request), ExternalControlProtocol.Fingerprint(parsed));
        if (shadow) Assert.NotEqual(ExternalControlProtocol.Fingerprint(request),
            ExternalControlProtocol.Fingerprint(request with { ShadowCapture = null }));
        if (route == NavigationBaselineRouteProfile.ReverseId) Assert.NotEqual(ExternalControlProtocol.Fingerprint(request),
            ExternalControlProtocol.Fingerprint(request with { ContinuationFromRunId = new string('b', 32) }));
    }

    /// <summary>Valid other selectors cannot turn explicit incoming null or an unknown archive mode into omission.</summary>
    [Theory]
    [InlineData("shadowCapture", "null")]
    [InlineData("shadowCapture", "\"unknown\"")]
    [InlineData("continuationFromRunId", "null")]
    public void ExplicitInvalidSelectorStillRejects(string field, string value)
    {
        var data = "{\"version\":1,\"requestId\":\"" + Guid.NewGuid() + "\",\"createdAtUnixMs\":"
            + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() + ",\"command\":\"startNavigationBaseline\","
            + "\"targetProcessId\":20,\"targetWindowsSessionId\":3,\"targetNonce\":\"fixed\","
            + "\"timingContract\":\"v4\",\"capturePolicy\":\"task_owned_timer\",\"routeProfile\":\""
            + NavigationBaselineRouteProfile.ReverseId + "\",\""
            + (field == "shadowCapture" ? "continuationFromRunId\":\"" + new string('a', 32) + "\""
                : "shadowCapture\":\"" + NavigationBaselineShadowMode.Rgb192 + "\"")
            + ",\"" + field + "\":" + value + "}";
        Assert.True(ExternalControlProtocol.TryDeserializeRequest(Encoding.UTF8.GetBytes(data), out var request));
        Assert.NotNull(ExternalControlProtocol.ValidateRequest(request!, DateTimeOffset.UtcNow));
    }
}
