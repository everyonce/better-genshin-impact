using System.Buffers.Binary;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using BetterGenshinImpact.Core.Script.Dependence;
using Fischless.GameCapture;
using Xunit;

namespace BetterGenshinImpact.EnglishTest;

/// <summary>Offline wire and source-clock tests for the quest script's read-only observer.</summary>
public class QuestFrameObserverTests
{
    /// <summary>Send a real framed request and parse the response using only synthetic pixels.</summary>
    [Fact]
    public async Task PipeSendsRawPixelsOnlyForGetFrameAndCancelsWhileIdle()
    {
        string name = "QuestFrames.Test." + Guid.NewGuid().ToString("N");
        using var server = new NamedPipeServerStream(name, PipeDirection.InOut, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous);
        using var client = new NamedPipeClientStream(".", name, PipeDirection.InOut, PipeOptions.Asynchronous);
        using var life = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var wait = server.WaitForConnectionAsync(life.Token);
        await client.ConnectAsync(life.Token);
        await wait;
        int pulls = 0;
        byte[] pixels = [1, 2, 3];
        var serving = QuestFrameObserver.ServeAsync(server, _ =>
        {
            pulls++;
            return Task.FromResult<(object, ReadOnlyMemory<byte>)>((new { type = "frame", payloadBytes = pixels.Length }, pixels));
        }, life.Token);
        await WriteRequest(client, """{"command":"getFrame"}""", life.Token);
        var prefix = new byte[4];
        await client.ReadExactlyAsync(prefix, life.Token);
        var json = new byte[BinaryPrimitives.ReadInt32LittleEndian(prefix)];
        await client.ReadExactlyAsync(json, life.Token);
        using var header = JsonDocument.Parse(json);
        Assert.Equal("frame", header.RootElement.GetProperty("type").GetString());
        var received = new byte[header.RootElement.GetProperty("payloadBytes").GetInt32()];
        await client.ReadExactlyAsync(received, life.Token);
        Assert.Equal(pixels, received);
        Assert.Equal(1, pulls);
        await life.CancelAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => serving);
    }

    /// <summary>Unknown commands, extra fields, duplicate command keys and bad sizes cannot call even the capture callback.</summary>
    [Theory]
    [InlineData("""{"command":"action","keys":["W"]}""")]
    [InlineData("""{"command":"getFrame","enableInput":true}""")]
    [InlineData("""{"command":"getFrame","command":"getFrame"}""")]
    [InlineData("[]")]
    public async Task AnyOtherCommandEndsBeforeCapture(string request)
    {
        var bytes = Encoding.UTF8.GetBytes(request);
        using var stream = new MemoryStream();
        await WriteRequest(stream, request, default);
        stream.Position = 0;
        await QuestFrameObserver.ServeAsync(stream, _ => throw new InvalidOperationException("Unexpected capture"), default);
        Assert.Equal(bytes.Length+4, stream.Length);
    }

    /// <summary>Length-prefix a single UTF-8 command like the Python client.</summary>
    private static async Task WriteRequest(Stream stream, string text, CancellationToken token)
    {
        var bytes = Encoding.UTF8.GetBytes(text);
        var prefix = new byte[4];
        BinaryPrimitives.WriteInt32LittleEndian(prefix, bytes.Length);
        await stream.WriteAsync(prefix, token);
        await stream.WriteAsync(bytes, token);
        await stream.FlushAsync(token);
    }

    /// <summary>WGC cached-source timestamps and true desktop acquisition starts retain their original age.</summary>
    [Fact]
    public void StaleAndMixedSourcesCannotGainRequestFreshness()
    {
        long now = Stopwatch.GetTimestamp(), f = Stopwatch.Frequency;
        var epoch = Guid.NewGuid();
        var old = new GameCaptureSourceInfo(epoch,
            (long)((Int128)(now-f)*TimeSpan.TicksPerSecond/f), now-f/2);
        var wgc = QuestFramePublisher.SourceTiming(old,null,false,now-1,now);
        Assert.True(wgc.HasValue);
        Assert.True(wgc.Value.AgeMs >= 999);
        var host = new GameCaptureHostSnapshotInfo(epoch, 1, now-f/3, now-f/4, f);
        var desktop = QuestFramePublisher.SourceTiming(null,host,true,now-1,now);
        Assert.Equal("desktopdc-host", desktop!.Value.Kind);
        Assert.InRange(desktop.Value.AgeMs, 332, 335);
        Assert.Null(QuestFramePublisher.SourceTiming(old,host,true,now-1,now));
        Assert.Null(QuestFramePublisher.SourceTiming(null,null,true,now-1,now));
        Assert.Equal("capture-request", QuestFramePublisher.SourceTiming(null,null,false,now-1,now)!.Value.Kind);
    }
}
