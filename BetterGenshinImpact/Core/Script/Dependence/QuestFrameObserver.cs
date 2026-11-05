using System;
using System.Buffers.Binary;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Pipes;
using BetterGenshinImpact.GameTask.Runtime;
using Microsoft.Win32.SafeHandles;

namespace BetterGenshinImpact.Core.Script.Dependence;

/// <summary>Streams observations from the running quest script's game capture. Its only wire command is getFrame.</summary>
public sealed class QuestFrameObserver(GameRuntime runtime, CancellationToken scriptToken)
{
    /// <summary>Protects the single listener and its script-bound cancellation source.</summary>
    private readonly object _gate = new();
    /// <summary>The opt-in listener for this script invocation, or null while inactive.</summary>
    private Task? _listener;
    /// <summary>Cancels a pending accept, read, write or cadence wait when the script exits.</summary>
    private CancellationTokenSource? _stop;

    /// <summary>Open a same-user pipe only for the verified RDP process and the game owned by this script.</summary>
    public void Start(string session, int processId, int windowsSessionId, int gameProcessId)
    {
        scriptToken.ThrowIfCancellationRequested();
        using var self = Process.GetCurrentProcess();
        if (!System.Windows.Forms.SystemInformation.TerminalServerSession || windowsSessionId <= 1 ||
            self.Id != processId || self.SessionId != windowsSessionId || !runtime.Window.IsAlive ||
            runtime.Window.ProcessId != gameProcessId || gameProcessId == processId ||
            !Regex.IsMatch(session ?? "", @"\A[a-z0-9]{1,32}-[a-z0-9]{1,32}\z"))
            throw new InvalidOperationException("Quest frame observer requires the pinned pilot, game and RDP session.");
        using var game = Process.GetProcessById(gameProcessId);
        if (game.SessionId != windowsSessionId) throw new InvalidOperationException("Game and pilot sessions differ.");
        using var identity = WindowsIdentity.GetCurrent();
        var sid = identity.User ?? throw new InvalidOperationException("Quest frame observer requires a user SID.");
        var name = $"BetterGI.QuestFrames.{processId}.{session}";

        lock (_gate)
        {
            if (_listener is not null) throw new InvalidOperationException("Quest frame listener is already running.");
            var first = LocalUserPipe.Create(name, sid);
            var stop = CancellationTokenSource.CreateLinkedTokenSource(scriptToken);
            IDisposable? operation;
            try { operation = ScriptHostOperations.Enter(); }
            catch { first.Dispose(); stop.Dispose(); throw; }
            _stop = stop;
            _listener = Task.Run(async () =>
            {
                using (operation)
                {
                    try { await ListenAsync(first, name, sid, session!, windowsSessionId, gameProcessId, stop.Token).ConfigureAwait(false); }
                    catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
                    finally
                    {
                        first.Dispose();
                        lock (_gate)
                        {
                            _stop = null;
                            stop.Dispose();
                        }
                    }
                }
            });
        }
    }

    /// <summary>Stop serving frames and finish releasing the listener before the quest script releases its runtime.</summary>
    public async Task Stop()
    {
        Task? listener;
        lock (_gate)
        {
            _stop?.Cancel();
            listener = _listener;
        }
        if (listener is null) return;
        try { await listener.ConfigureAwait(false); }
        finally { lock (_gate) { if (ReferenceEquals(listener, _listener)) _listener = null; } }
    }

    /// <summary>Only a connected client in this RDP session requests frames. Idle and disconnected listeners do no capture work.</summary>
    private async Task ListenAsync(NamedPipeServerStream first, string name, SecurityIdentifier sid, string session,
        int windowsSessionId, int gameProcessId, CancellationToken token)
    {
        var publisher = new QuestFramePublisher(runtime, session, windowsSessionId, gameProcessId);
        NamedPipeServerStream? initial = first;
        while (!token.IsCancellationRequested)
        {
            using var pipe = initial ?? LocalUserPipe.Create(name, sid);
            initial = null;
            try
            {
                await pipe.WaitForConnectionAsync(token).ConfigureAwait(false);
                if (GetNamedPipeClientSessionId(pipe.SafePipeHandle, out var clientSession) && clientSession == windowsSessionId)
                    await ServeAsync(pipe, publisher.NextAsync, token).ConfigureAwait(false);
            }
            catch (IOException) { /* A closed or malformed client cannot end the owned script. */ }
            catch (JsonException) { /* A malformed JSON message has no operation. */ }
            catch (OperationCanceledException) when (!token.IsCancellationRequested) { /* Per-message I/O timeout. */ }
        }
    }

    /// <summary>Read a bounded length-prefixed getFrame request and return its header followed by raw RGB bytes.</summary>
    internal static async Task ServeAsync(Stream pipe,
        Func<CancellationToken, Task<(object Header, ReadOnlyMemory<byte> Pixels)>> capture, CancellationToken token)
    {
        byte[] prefix = new byte[sizeof(int)];
        while (!token.IsCancellationRequested)
        {
            // A paused adviser may hold the connection; the script's token always cancels this first-byte wait.
            if (await pipe.ReadAsync(prefix.AsMemory(0, 1), token).ConfigureAwait(false) == 0) return;
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(token);
            timeout.CancelAfter(TimeSpan.FromSeconds(5));
            var io = timeout.Token;
            await pipe.ReadExactlyAsync(prefix.AsMemory(1), io).ConfigureAwait(false);
            int size = BinaryPrimitives.ReadInt32LittleEndian(prefix);
            if (size is < 2 or > 256) return;
            var request = new byte[size];
            await pipe.ReadExactlyAsync(request, io).ConfigureAwait(false);
            using var doc = JsonDocument.Parse(request);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object || root.EnumerateObject().Count() != 1 ||
                !root.TryGetProperty("command", out var command) || command.ValueKind != JsonValueKind.String ||
                command.GetString() != "getFrame") return;

            var (header, pixels) = await capture(io).ConfigureAwait(false);
            var json = JsonSerializer.SerializeToUtf8Bytes(header);
            BinaryPrimitives.WriteInt32LittleEndian(prefix, json.Length);
            await pipe.WriteAsync(prefix, io).ConfigureAwait(false);
            await pipe.WriteAsync(json, io).ConfigureAwait(false);
            if (!pixels.IsEmpty) await pipe.WriteAsync(pixels, io).ConfigureAwait(false);
            await pipe.FlushAsync(io).ConfigureAwait(false);
        }
    }

    /// <summary>Verify the client in the kernel before sharing any pixels across the named pipe.</summary>
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetNamedPipeClientSessionId(SafePipeHandle pipe, out uint clientSessionId);
}
