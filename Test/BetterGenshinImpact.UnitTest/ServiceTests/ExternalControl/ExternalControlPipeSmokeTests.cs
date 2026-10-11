using System;
using System.Buffers.Binary;
using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Service.ExternalControl;

namespace BetterGenshinImpact.UnitTest.ServiceTests.ExternalControl;

public class ExternalControlPipeSmokeTests
{
    [Fact]
    public async Task LocalSameUserClientCanConnectAndPassPeerChecks()
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        using var identity = WindowsIdentity.GetCurrent();
        var sid = identity.User ?? throw new InvalidOperationException("Current Windows identity has no SID.");
        var pipeName = "bgi-ext-smoke-" + Guid.NewGuid().ToString("N");
        var createServer = typeof(ExternalControlService).GetMethod("CreateServer", BindingFlags.NonPublic | BindingFlags.Static)
                           ?? throw new MissingMethodException("External control server factory was not found.");
        await using var server = (NamedPipeServerStream)(createServer.Invoke(null, [pipeName, sid])
                                                        ?? throw new InvalidOperationException("Pipe factory returned null."));

        var service = new ExternalControlService(null!, null!, null!);
        typeof(ExternalControlService)
            .GetField("_userSid", BindingFlags.NonPublic | BindingFlags.Instance)!
            .SetValue(service, sid);

        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(8));
        var waitForClient = server.WaitForConnectionAsync(timeout.Token);
        await using var client = new NamedPipeClientStream(
            ".",
            pipeName,
            PipeDirection.InOut,
            PipeOptions.Asynchronous,
            TokenImpersonationLevel.Impersonation);
        await client.ConnectAsync(timeout.Token);
        await waitForClient;

        var payload = Encoding.UTF8.GetBytes("{}");
        var prefix = new byte[sizeof(int)];
        BinaryPrimitives.WriteInt32LittleEndian(prefix, payload.Length);
        await client.WriteAsync(prefix, timeout.Token);
        await client.WriteAsync(payload, timeout.Token);
        await client.FlushAsync(timeout.Token);

        var receivedPrefix = new byte[sizeof(int)];
        await ReadExactlyAsync(server, receivedPrefix, timeout.Token);
        var receivedLength = BinaryPrimitives.ReadInt32LittleEndian(receivedPrefix);
        Assert.Equal(payload.Length, receivedLength);
        var receivedPayload = new byte[receivedLength];
        await ReadExactlyAsync(server, receivedPayload, timeout.Token);
        Assert.Equal(payload, receivedPayload);

        var isLocalClient = typeof(ExternalControlService).GetMethod("IsLocalClient", BindingFlags.NonPublic | BindingFlags.Static)!;
        Assert.True((bool)isLocalClient.Invoke(null, [server.SafePipeHandle])!);

        var isSameUserClient = typeof(ExternalControlService).GetMethod("IsSameUserClient", BindingFlags.NonPublic | BindingFlags.Instance)!;
        Assert.True((bool)isSameUserClient.Invoke(service, [server])!);
    }

    private static async Task ReadExactlyAsync(Stream stream, Memory<byte> buffer, CancellationToken cancellationToken)
    {
        var offset = 0;
        while (offset < buffer.Length)
        {
            var read = await stream.ReadAsync(buffer[offset..], cancellationToken);
            Assert.NotEqual(0, read);
            offset += read;
        }
    }
}
