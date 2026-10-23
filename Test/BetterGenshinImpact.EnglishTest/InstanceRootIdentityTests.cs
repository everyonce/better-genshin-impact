using BetterGenshinImpact.Service.Instance;
using BetterGenshinImpact.Service.ExternalControl;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Root metadata must retain its registered session identity without assuming a fixed console ID.</summary>
public sealed class InstanceRootIdentityTests
{
    /// <summary>The live console-2/child-3 pair and later console allocations are legitimate root identities.</summary>
    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(7)]
    public void RegisteredPrimaryRootAcceptsActualWindowsSession(int rootSession)
    {
        var endpoint = new InstanceEndpoint { InstanceType = BetterGiInstanceType.Primary,
            ProcessId = 28072, WindowsSessionId = rootSession };
        Assert.True(InstanceService.IsExpectedRootEndpoint(endpoint, rootSession, 35832));
    }

    /// <summary>A non-1 session must not weaken type, registered-session, valid-PID, or self-target checks.</summary>
    [Theory]
    [InlineData(BetterGiInstanceType.Primary, 2, 28072, 1)]
    [InlineData(BetterGiInstanceType.Primary, 2, 28072, null)]
    [InlineData(BetterGiInstanceType.Primary, -1, 28072, -1)]
    [InlineData(BetterGiInstanceType.Primary, 2, 0, 2)]
    [InlineData(BetterGiInstanceType.Primary, 2, 35832, 2)]
    [InlineData(BetterGiInstanceType.ChildSession, 2, 28072, 2)]
    [InlineData(BetterGiInstanceType.WebView, 2, 28072, 2)]
    public void InvalidOrUnregisteredRootIsRejected(BetterGiInstanceType type, int session, int processId,
        int? registeredSession)
    {
        var endpoint = new InstanceEndpoint { InstanceType = type, ProcessId = processId, WindowsSessionId = session };
        Assert.False(InstanceService.IsExpectedRootEndpoint(endpoint, registeredSession, 35832));
    }

    /// <summary>No root connection is distinct from a root with an arbitrary console session number.</summary>
    [Fact]
    public void MissingEndpointIsRejected()
    {
        Assert.False(InstanceService.IsExpectedRootEndpoint(null, 2, 35832));
    }

    /// <summary>Recovery takes the verified root's session, rather than a caller-provided or hardcoded session.</summary>
    [Fact]
    public void RecoveryUsesRegisteredRootSessionTwoAndNeverTheChildSession()
    {
        var root = new InstanceEndpoint { InstanceType = BetterGiInstanceType.Primary,
            ProcessId = 28072, WindowsSessionId = 2 };
        Assert.Equal(2, ExternalControlRecovery.GetRootSessionId(root, childSessionId: 3));
        Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.GetRootSessionId(root, childSessionId: 2));
        Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.GetRootSessionId(
            new InstanceEndpoint { InstanceType = BetterGiInstanceType.ChildSession, ProcessId = 35832, WindowsSessionId = 3 }, 2));
        Assert.Throws<InvalidOperationException>(() => ExternalControlRecovery.GetRootSessionId(
            new InstanceEndpoint { InstanceType = BetterGiInstanceType.Primary, ProcessId = 28072, WindowsSessionId = 0 }, 3));
    }
}
