using System.Buffers.Binary;
using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Security.Principal;
using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Input;
using BetterGenshinImpact.Core.Pipes;
using BetterGenshinImpact.GameTask.AutoAgent;
using BetterGenshinImpact.UnitTest.GameTaskTests;
using Vanara.PInvoke;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Tests real ServeAsync framing with the production local pipe and fake input; does not run RDP or bypass RunAsync guards.</summary>
public sealed class AgentStreamDisconnectTests
{
    /// <summary>EOF ends transport, truncated frames fault it, and the separately invoked owner Stop clears fake held input.</summary>
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(5)]
    public async Task DisconnectEndsTransportAndOwnerStopRevokesHeldInput(int partialBytes)
    {
        using var runtime = TestGameRuntime.Create(new FakeSystemInfo(new RECT(0, 0, 1920, 1080), 1), new ObserveOnlyInputBackend());
        var session = new AgentStreamSession(runtime);
        var input = new RecordingInput();
        var controller = new AgentActionController(input, true);
        controller.RegisterFrame(new AgentObservation(0, 60, 1920, 1080, AgentWorldEvidence.WorldHud));
        controller.RegisterFrame(new AgentObservation(1, 100, 1920, 1080, AgentWorldEvidence.WorldHud));
        var request = new AgentRequest
        {
            RequestId = "disconnect-test", ModelId = "fake-input", FrameId = 1, ObservedAtMs = 100,
            ExpiresAtMs = 500, Steps = [new() { DurationMs = 50, Keys = ["W"] }]
        };
        Assert.Null(controller.Submit(request, 110));
        controller.Tick(110);
        Assert.Equal(new[] { "W" }, input.Held);

        // Use the real security-label/ACL factory, never a replacement to get around an environment restriction.
        using var identity = WindowsIdentity.GetCurrent();
        var pipeName = "BetterGI.Agent.disconnect-test-" + Guid.NewGuid().ToString("N");
        await using var server = LocalUserPipe.Create(pipeName, identity.User!);
        await using var client = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut, PipeOptions.Asynchronous);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var serve = typeof(AgentStreamSession).GetMethod("ServeAsync", BindingFlags.NonPublic | BindingFlags.Instance)!;
        var serving = (Task)serve.Invoke(session, [server, controller, new RuntimeAgentInput(runtime), true, timeout.Token])!;
        try
        {
            await client.ConnectAsync(timeout.Token);
            var prefix = new byte[4];
            await client.ReadExactlyAsync(prefix, timeout.Token);
            var length = BinaryPrimitives.ReadInt32LittleEndian(prefix);
            Assert.InRange(length, 2, 65536);
            await client.ReadExactlyAsync(new byte[length], timeout.Token);

            if (partialBytes > 0)
            {
                var truncated = new byte[5];
                BinaryPrimitives.WriteInt32LittleEndian(truncated, 32);
                truncated[4] = (byte)'{';
                await client.WriteAsync(truncated.AsMemory(0, partialBytes), timeout.Token);
                await client.FlushAsync(timeout.Token);
            }
            await client.DisposeAsync();
            if (partialBytes == 0) await serving.WaitAsync(TimeSpan.FromSeconds(5));
            else await Assert.ThrowsAnyAsync<IOException>(() => serving.WaitAsync(TimeSpan.FromSeconds(5)));

            // ServeAsync deliberately does not own release. RunAsync's finally calls this exact Stop method
            // before waiting for other loops. This assertion prevents overstating this as full RunAsync coverage.
            Assert.Equal(new[] { "W" }, input.Held);
            controller.Stop(115, "session_ended");
            Assert.Empty(input.Held);
            Assert.Equal(1, input.ReleaseCount);
            var receipt = Assert.Single(controller.DrainReceipts());
            Assert.Equal("cancelled", receipt.Status);
            Assert.Equal("session_ended", receipt.Reason);
            Assert.Equal("session_stopped", controller.Submit(request with { RequestId = "cannot-reuse-lease" }, 120));
        }
        finally
        {
            timeout.Cancel();
            await server.DisposeAsync();
            // Observe transport termination even if an earlier assertion failed.
            try { await serving.WaitAsync(TimeSpan.FromSeconds(5)); }
            catch (IOException) { }
            catch (OperationCanceledException) { }
            catch (ObjectDisposedException) { }
        }
    }

    /// <summary>Only in-memory key bookkeeping; no Windows input is ever sent.</summary>
    private sealed class RecordingInput : IAgentInput
    {
        /// <inheritdoc />
        public bool IsAvailable => true;
        /// <summary>Tracks synthetic held keys.</summary>
        internal string[] Held { get; private set; } = [];
        /// <summary>Counts software release calls without claiming physical execution.</summary>
        internal int ReleaseCount { get; private set; }
        /// <inheritdoc />
        public void SetHeldKeys(string[] keys) => Held = keys.ToArray();
        /// <inheritdoc />
        public void MoveMouse(int dx, int dy) { }
        /// <inheritdoc />
        public void ReleaseAll() { Held = []; ReleaseCount++; }
    }
}
