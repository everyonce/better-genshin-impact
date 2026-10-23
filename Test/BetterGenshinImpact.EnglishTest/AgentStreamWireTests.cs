using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Pipes;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using Newtonsoft.Json.Linq;
using System.Buffers.Binary;
using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Exercise the real bridge codec over memory streams without connecting to a game or pipe.</summary>
public sealed class AgentStreamWireTests
{
    /// <summary>The real pipe connects locally while its ACL grants only the owner and denies network users.</summary>
    [Fact]
    public async Task LocalPipeConnectsWithRestrictedOwnerAcl()
    {
        using var identity = WindowsIdentity.GetCurrent();
        var sid = identity.User!;
        var name = "BetterGI.Agent.test-" + Guid.NewGuid().ToString("N");
        await using var server = LocalUserPipe.Create(name, sid);
        var rules = server.GetAccessControl().GetAccessRules(true, false, typeof(SecurityIdentifier)).Cast<PipeAccessRule>().ToArray();
        Assert.Contains(rules, r => r.IdentityReference.Equals(sid) && r.AccessControlType == AccessControlType.Allow);
        var network = new SecurityIdentifier(WellKnownSidType.NetworkSid, null);
        Assert.Contains(rules, r => r.IdentityReference.Equals(network) && r.AccessControlType == AccessControlType.Deny);
        Assert.All(rules, r => Assert.True(r.IdentityReference.Equals(sid) || r.IdentityReference.Equals(network)));
        await using var client = new NamedPipeClientStream(".", name, PipeDirection.InOut, PipeOptions.Asynchronous);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        await Task.WhenAll(server.WaitForConnectionAsync(timeout.Token), client.ConnectAsync(timeout.Token));
        await client.WriteAsync(new byte[] { 3, 2, 1 }, timeout.Token);
        var bytes = new byte[3];
        await server.ReadExactlyAsync(bytes, timeout.Token);
        Assert.Equal(new byte[] { 3, 2, 1 }, bytes);
    }

    /// <summary>A direct bridge invocation cannot bypass the existing TaskRunner input owner.</summary>
    [Fact]
    public async Task RequiresAnExistingTaskScopeBeforeCreatingTransport()
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1));
        var session = new AgentStreamSession(runtime);
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            session.RunAsync("BetterGI.Agent.test", false, CancellationToken.None));
        Assert.Contains("TaskRunner", error.Message);
    }

    /// <summary>Raw RGB follows UTF-8 JSON, and pooled-buffer capacity is not leaked into the packet.</summary>
    [Fact]
    public async Task WritesLittleEndianJsonLengthThenExactRgbPayload()
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1));
        var session = new AgentStreamSession(runtime);
        using var stream = new MemoryStream();
        var pixels = Enumerable.Repeat((byte)0xEE, 32).ToArray();
        new byte[] { 1, 2, 3, 4, 5, 6 }.CopyTo(pixels, 0);
        var write = typeof(AgentStreamSession).GetMethod("WriteAsync", BindingFlags.NonPublic | BindingFlags.Instance)!;
        await (Task)write.Invoke(session, [stream, new { Type = "frame", PayloadBytes = 6, ModelId = "test-λ" },
            (ReadOnlyMemory<byte>?)pixels.AsMemory(0, 6), CancellationToken.None])!;
        var packet = stream.ToArray();
        var length = BinaryPrimitives.ReadInt32LittleEndian(packet);
        var header = JObject.Parse(Encoding.UTF8.GetString(packet, 4, length));
        Assert.Equal("frame", header["type"]!.Value<string>());
        Assert.Equal("test-λ", header["modelId"]!.Value<string>());
        Assert.Equal(6, header["payloadBytes"]!.Value<int>());
        Assert.Equal(4 + length + 6, packet.Length);
        Assert.Equal(new byte[] { 1, 2, 3, 4, 5, 6 }, packet[(4 + length)..]);
    }

    /// <summary>Canonical Python request fields deserialize into the action contract with unchanged timing.</summary>
    [Fact]
    public async Task ReadsCamelCaseActionEnvelope()
    {
        var json = """
            {"version":1,"command":"action","sessionId":"session","ownerEpoch":"lease","goalVersion":1,
             "requestId":"request","modelId":"checkpoint","frameId":42,"observedAtMs":123.25,"expiresAtMs":500,
             "steps":[{"durationMs":50,"keys":["W","LSHIFT"],"mouseDx":8,"mouseDy":-2}]}
            """;
        using var stream = Packet(json);
        var request = await ReadAsync(stream);
        Assert.NotNull(request);
        Assert.Equal("action", request.Command);
        Assert.Equal("session", request.SessionId);
        Assert.Equal("lease", request.OwnerEpoch);
        Assert.Equal(123.25, request.ObservedAtMs);
        Assert.Equal(new[] { "W", "LSHIFT" }, Assert.Single(request.Steps).Keys);
        Assert.Equal(-2, request.Steps[0].MouseDy);
    }

    /// <summary>Oversized input is rejected before allocating its claimed body.</summary>
    [Theory]
    [InlineData(-1)]
    [InlineData(1)]
    [InlineData(65537)]
    public async Task RejectsInvalidPacketSizes(int length)
    {
        var prefix = new byte[4];
        BinaryPrimitives.WriteInt32LittleEndian(prefix, length);
        using var stream = new MemoryStream(prefix);
        await Assert.ThrowsAsync<InvalidDataException>(() => ReadAsync(stream));
    }

    /// <summary>Closed connections and partial messages have distinct, deterministic outcomes.</summary>
    [Fact]
    public async Task DistinguishesCleanDisconnectFromTruncatedPacket()
    {
        using var empty = new MemoryStream();
        Assert.Null(await ReadAsync(empty));
        using var partial = new MemoryStream(new byte[] { 12, 0 });
        await Assert.ThrowsAsync<EndOfStreamException>(() => ReadAsync(partial));
    }

    /// <summary>Create a correctly framed UTF-8 request fixture.</summary>
    private static MemoryStream Packet(string json)
    {
        var bytes = Encoding.UTF8.GetBytes(json);
        var packet = new byte[4 + bytes.Length];
        BinaryPrimitives.WriteInt32LittleEndian(packet, bytes.Length);
        bytes.CopyTo(packet, 4);
        return new MemoryStream(packet);
    }

    /// <summary>Call the production codec without running its RDP/task lifecycle or exposing a new public API.</summary>
    private static async Task<AgentRequest?> ReadAsync(Stream stream)
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1));
        var session = new AgentStreamSession(runtime);
        var read = typeof(AgentStreamSession).GetMethod("ReadAsync", BindingFlags.NonPublic | BindingFlags.Instance)!;
        return await (Task<AgentRequest?>)read.Invoke(session, [stream, CancellationToken.None])!;
    }
}
