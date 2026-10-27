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
