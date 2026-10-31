using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.GameTask.AutoAgent;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Newtonsoft.Json.Serialization;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Native guidance cannot promote weak matches or reuse pose fields on an unavailable frame.</summary>
public sealed class AgentNavigationPoseTests
{
    /// <summary>The separate scouting scope retains strict confidence, layer, and rectangular limits.</summary>
    [Theory]
    [InlineData(-1350, 2050, .99, .2, "MapBack_2", true)]
    [InlineData(-980, 2480, .99, .2, "City_102", true)]
    [InlineData(-1350.01, 2200, .999, .8, "MapBack_2", false)]
    [InlineData(-979.99, 2200, .999, .8, "MapBack_2", false)]
    [InlineData(-1165, 2049.99, .999, .8, "MapBack_2", false)]
    [InlineData(-1165, 2480.01, .999, .8, "MapBack_2", false)]
    [InlineData(-1165, 2265, .989, .8, "MapBack_2", false)]
    [InlineData(-1165, 2265, .999, .199, "MapBack_2", false)]
    [InlineData(-1165, 2265, .999, .8, "MapBack_1", false)]
    public void ScoutingScopeDoesNotBroadenTheExistingSurface(double x, double y, double position,
        double yaw, string layer, bool accepted)
    {
        Assert.Equal(accepted, AgentNavigationPose.IsQualified(x, y, 15, position, yaw, layer,
            AgentNavigationProfile.MondstadtCombatScout));
        Assert.False(AgentNavigationPose.IsQualified(-1165, 2265, 15, .999, .8, "MapBack_2",
            AgentNavigationProfile.MondstadtSurface));
    }

    /// <summary>A new fixed local anchor cannot silently change the original route heading anchors.</summary>
    [Fact]
    public void ScoutingCapabilitySeparatesSearchAnchorFromRouteGeometry()
    {
        var scout = JObject.FromObject(AgentNavigationRecognizer.GetCapability(AgentNavigationProfile.MondstadtCombatScout));
        var original = JObject.FromObject(AgentNavigationRecognizer.Capability);
        Assert.True(scout["localOnly"]!.Value<bool>());
        Assert.Equal(-1165, scout["searchAnchor"]!["x"]!.Value<double>());
        Assert.Equal(2265, scout["searchAnchor"]!["y"]!.Value<double>());
        Assert.True(JToken.DeepEquals(original["start"], scout["start"]));
        Assert.True(JToken.DeepEquals(original["end"], scout["end"]));
    }

    /// <summary>Outdoor localization requires an explicit scope; low confidence and unrelated layers remain rejected.</summary>
    [Theory]
    [InlineData(-947.53906, 2222.0996, .992757, .751167, "MapBack_2", true)]
    [InlineData(-947.53906, 2222.0996, .989, .751167, "MapBack_2", false)]
    [InlineData(-947.53906, 2222.0996, .992757, .199, "MapBack_2", false)]
    [InlineData(-947.53906, 2222.0996, .992757, .751167, "MapBack_1", false)]
    [InlineData(-1100.01, 2222, .999, .8, "MapBack_2", false)]
    [InlineData(-819.99, 2222, .999, .8, "MapBack_2", false)]
    [InlineData(-947, 2099.99, .999, .8, "MapBack_2", false)]
    [InlineData(-947, 2350.01, .999, .8, "MapBack_2", false)]
    public void SurfaceScopePreservesThresholdsAndBounds(double x, double y, double confidence,
        double yawConfidence, string layer, bool accepted)
    {
        Assert.False(AgentNavigationPose.IsQualified(x, y, 15, confidence, yawConfidence, layer));
        Assert.Equal(accepted, AgentNavigationPose.IsQualified(x, y, 15, confidence, yawConfidence, layer,
            AgentNavigationProfile.MondstadtSurface));
    }

    /// <summary>Scope negotiation remains explicit and publishes finite, inspectable bounds.</summary>
    [Fact]
    public void SurfaceCapabilityIsSeparateFromTheUnchangedDefault()
    {
        var wire = JObject.FromObject(AgentNavigationRecognizer.GetCapability(AgentNavigationProfile.MondstadtSurface));
        Assert.Equal("mondstadt-surface-hybrid-v1", wire["profileId"]!.Value<string>());
        Assert.Equal(new[] { "City_102", "MapBack_2" }, wire["allowedLayerIds"]!.Values<string>());
        Assert.Equal(-1100, wire["bounds"]!["minX"]!.Value<double>());
        Assert.True(wire["readOnly"]!.Value<bool>());
        Assert.False(AgentNavigationProfile.IsSupported("unbounded"));
        Assert.False(AgentNavigationPose.IsQualified(-947, 2222, 15, .999, .8, "City_102", "unbounded"));
    }

    /// <summary>Only the existing native route's finite rank-zero City_102 confidence contract is accepted.</summary>
    [Theory]
    [InlineData(.99, .2, "City_102", 0, true)]
    [InlineData(.989, .8, "City_102", 47, false)]
    [InlineData(.999, .199, "City_102", 47, false)]
    [InlineData(.999, .8, "City_103", 47, false)]
    [InlineData(1.01, .8, "City_102", 47, false)]
    [InlineData(.999, .8, "City_102", 360, false)]
    public void QualificationKeepsNativeThresholds(double position, double yawConfidence, string layer, double yaw, bool valid)
    {
        Assert.Equal(valid, AgentNavigationPose.IsQualified(-867, 2281, yaw, position, yawConfidence, layer));
        Assert.False(AgentNavigationPose.IsQualified(double.NaN, 2281, yaw, position, yawConfidence, layer));
    }

    /// <summary>Unavailable wire data cannot masquerade as a previous successful coordinate or correction.</summary>
    [Fact]
    public void UnavailablePoseHasOnlyItsOwnFrameIdentity()
    {
        var settings = new JsonSerializerSettings { ContractResolver = new CamelCasePropertyNamesContractResolver() };
        var wire = JObject.Parse(JsonConvert.SerializeObject(AgentNavigationPose.Unavailable(92, "world_not_ready"), settings));
        Assert.Equal(92, wire["frameId"]!.Value<long>());
        Assert.Equal("unavailable", wire["state"]!.Value<string>());
        Assert.Equal(JTokenType.Null, wire["x"]!.Type);
        Assert.Equal(JTokenType.Null, wire["mouseToEnd"]!.Type);
    }

    /// <summary>The capability is a fixed local route, not a caller-defined coordinate or input service.</summary>
    [Fact]
    public void CapabilityDeclaresSameFrameReadOnlyGuidance()
    {
        var wire = JObject.FromObject(AgentNavigationRecognizer.Capability);
        Assert.True(wire["sameFrame"]!.Value<bool>());
        Assert.True(wire["readOnly"]!.Value<bool>());
        Assert.Equal("mondstadt-courtyard-hybrid-v1", wire["profileId"]!.Value<string>());
        Assert.Equal(-867.7041015625, wire["start"]!["x"]!.Value<double>());
    }
}
