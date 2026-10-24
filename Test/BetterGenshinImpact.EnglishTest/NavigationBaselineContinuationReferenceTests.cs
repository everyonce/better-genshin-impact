using System;
using System.Linq;
using System.Text.Json;
using BetterGenshinImpact.GameTask.NavigationBaseline;
using BetterGenshinImpact.Core.Capture;
using BetterGenshinImpact.Service.ExternalControl;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Wire references do not replace the full owner/result proof or grow with predecessor artifact paths.</summary>
public sealed class NavigationBaselineContinuationReferenceTests
{
    /// <summary>Initial/ordinary owners advertise capability2 without manufacturing predecessor provenance.</summary>
    [Fact]
    public void AbsentLinkRemainsAbsentOnWire()
    {
        using var json = JsonDocument.Parse(Wire(new()));
        var owner = json.RootElement.GetProperty("status").GetProperty("navigationBaseline");
        Assert.Equal(2, owner.GetProperty("endpointContinuationVersion").GetInt32());
        Assert.False(owner.TryGetProperty("continuation", out _));
    }

    /// <summary>All complete proof fields remain in memory; only the explicit reference is serialized in status.</summary>
    [Fact]
    public void ReferenceHasOnlyTheThreeSpecifiedFields()
    {
        var link = Link(1024);
        var status = new NavigationBaselineStatus { Continuation = link };
        Assert.Same(link, status.Continuation);
        using var json = JsonDocument.Parse(Wire(status));
        var reference = json.RootElement.GetProperty("status").GetProperty("navigationBaseline").GetProperty("continuation");
        Assert.Equal(new[] { "predecessorProfileId", "predecessorRunId", "version" }, reference.EnumerateObject().Select(x => x.Name).OrderBy(x => x).ToArray());
        Assert.Equal(2, reference.GetProperty("version").GetInt32());
        Assert.Equal(link.PredecessorRunId, reference.GetProperty("predecessorRunId").GetString());
        Assert.Equal(link.PredecessorProfileId, reference.GetProperty("predecessorProfileId").GetString());
    }

    /// <summary>Evidence growth never changes ordinary bytes; this is not a proof that arbitrary dedicated evidence fits its limit.</summary>
    [Theory]
    [InlineData(1)]
    [InlineData(1024)]
    [InlineData(4096)]
    public void OrdinaryStatusSizeIsIndependentOfPredecessorPaths(int pathLength)
    {
        var expected = Wire(new() { Continuation = Link(1) });
        var actual = Wire(new() { Continuation = Link(pathLength) });
        Assert.Equal(expected, actual);
        Assert.InRange(actual.Length, 1, ExternalControlProtocol.MaximumFrameBytes - 1);
    }

    /// <summary>The actual result serializer retains original fields and version1 instead of silently projecting the proof.</summary>
    [Fact]
    public void DedicatedResultKeepsFullLink()
    {
        var link = Link(1024);
        var result = new NavigationBaselineRunResult { Continuation = link };
        using var json = JsonDocument.Parse(Wire(new() { Continuation = link, Result = result }));
        var owner = json.RootElement.GetProperty("status").GetProperty("navigationBaseline");
        Assert.Equal(2, owner.GetProperty("continuation").GetProperty("version").GetInt32());
        var full = owner.GetProperty("result").GetProperty("continuation");
        Assert.Equal(1, full.GetProperty("version").GetInt32());
        Assert.Equal(1024, full.GetProperty("predecessorEvidence").GetProperty("journalPath").GetString()!.Length);
        Assert.Equal(link.RuntimeIdentity, full.GetProperty("runtimeIdentity").GetGuid());
        Assert.Equal(link.PredecessorFinalSource.CaptureEpoch, full.GetProperty("predecessorFinalSource").GetProperty("CaptureEpoch").GetGuid());
        Assert.False(full.GetProperty("physicalInputAcknowledged").GetBoolean());
    }

    /// <summary>Host proof2 is explicit; the compact reference stays2 and contains no full predecessor evidence.</summary>
    [Fact]
    public void HostResultKeepsTypedFullProofAndAdditiveCapability()
    {
        var link = NavigationBaselineHostSourceTests.HostLink();
        var status = new NavigationBaselineStatus { SourcePolicy = DesktopCapturePolicy.HostAcquisitionV1, Continuation = link,
            Result = new() { SourcePolicy = DesktopCapturePolicy.HostAcquisitionV1, Continuation = link } };
        using var json = JsonDocument.Parse(Wire(status));
        var owner = json.RootElement.GetProperty("status").GetProperty("navigationBaseline");
        Assert.Equal(2, owner.GetProperty("endpointContinuationVersion").GetInt32());
        Assert.Equal(1, owner.GetProperty("hostEndpointContinuationVersion").GetInt32());
        var reference = owner.GetProperty("continuation");
        Assert.Equal(2, reference.GetProperty("version").GetInt32()); Assert.Equal(3, reference.EnumerateObject().Count());
        var full = owner.GetProperty("result").GetProperty("continuation");
        Assert.Equal(2, full.GetProperty("version").GetInt32());
        Assert.Equal(DesktopCapturePolicy.HostAcquisitionV1, full.GetProperty("sourcePolicy").GetString());
        Assert.Equal(link.ChildAssemblySha256, full.GetProperty("childAssemblySha256").GetString());
        Assert.Equal(JsonValueKind.Null, full.GetProperty("readbackMode").ValueKind);
        var source = full.GetProperty("predecessorFinalSource");
        Assert.Equal("host-acquisition-v1", source.GetProperty("kind").GetString());
        var raw = source.GetProperty("hostSnapshot");
        Assert.Equal(5, raw.EnumerateObject().Count());
        Assert.Equal(link.PredecessorFinalSource.HostSnapshot!.SnapshotId, raw.GetProperty("SnapshotId").GetInt64());
        Assert.False(source.TryGetProperty("SourceTimestamp100ns", out _));
        Assert.False(source.TryGetProperty("AcquiredAtStopwatchTicks", out _));
        Assert.False(full.GetProperty("physicalInputAcknowledged").GetBoolean());
    }

    /// <summary>Legacy full proof and raw WGC source retain their exact serializer shape with no host claims.</summary>
    [Fact]
    public void WgcFullProofOmitsHostCapabilityAndFields()
    {
        var link = Link(10);
        using var json = JsonDocument.Parse(Wire(new() { Continuation = link, Result = new() { Continuation = link } }));
        var owner = json.RootElement.GetProperty("status").GetProperty("navigationBaseline");
        Assert.False(owner.TryGetProperty("hostEndpointContinuationVersion", out _));
        var full = owner.GetProperty("result").GetProperty("continuation");
        Assert.Equal(1, full.GetProperty("version").GetInt32());
        Assert.False(full.TryGetProperty("sourcePolicy", out _)); Assert.False(full.TryGetProperty("childAssemblySha256", out _));
        Assert.Equal(JsonSerializer.Serialize(link.PredecessorFinalSource.WgcSource), full.GetProperty("predecessorFinalSource").GetRawText());
    }

    /// <summary>Use the production response serializer and its fixed envelope.</summary>
    private static byte[] Wire(NavigationBaselineStatus status) => ExternalControlProtocol.SerializeResponse(new() { Status = new() { NavigationBaseline = status } });

    /// <summary>Fixed identities isolate the contribution of path length without runtime/input construction.</summary>
    private static NavigationBaselineContinuationLink Link(int pathLength) => new()
    {
        PredecessorRunId = new string('a', 32), PredecessorProfileId = NavigationBaselineRouteProfile.CourtyardReturnId,
        PredecessorEvidence = new(true, new string('j', pathLength), new string('b', 64), new string('i', pathLength),
            new string('c', 64), new string('f', pathLength), new string('d', 64)),
        PredecessorFinalSource = new(Guid.Parse("11111111-2222-3333-4444-555555555555"), 123, 456),
        PredecessorCleanupReturnedAtTicks = 789, RuntimeIdentity = Guid.Parse("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        ChildProcessId = 1, ChildNonce = new string('e', 32), WindowsSessionId = 3,
        GameProcessId = 2, GameStartedAtUtcTicks = 638982123456789012,
        CaptureType = "Fischless.GameCapture.Graphics.GraphicsCaptureV2", ReadbackMode = "poll_single_v1"
    };
}
