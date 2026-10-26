using System;
using System.Diagnostics;

namespace BetterGenshinImpact.Helpers;

/// <summary>One opt-in root startup may reconnect only to an existing clone and its retained game lifetime.</summary>
public sealed class UpgradeSessionBinding
{
    /// <summary>The existing clone session, never a request to create a session.</summary>
    public int SessionId { get; }
    /// <summary>The protected game process; PID alone is not a lifetime identity.</summary>
    public int GameProcessId { get; }
    /// <summary>Native process creation time in UTC Windows FILETIME ticks.</summary>
    public long GameStartedFileTime { get; }

    /// <summary>One-way publication after the explicit resume's state and identity checks.</summary>
    private int _released;
    /// <summary>Exact small startup record, owned until explicit completion; no runtime settings are retained here.</summary>
    private (string Path, byte[] Bytes)? _startupFile;
    /// <summary>Retain the consumed record only after its exact-byte comparison succeeds.</summary>
    internal void RetainStartupFile(string path, byte[] bytes) => _startupFile = (path, bytes);
    /// <summary>Direct explicit arguments have no file; the approved fixed launcher must complete its consumed record.</summary>
    internal void CompleteStartupFile()
    {
        if (_startupFile is { } record) UpgradeStartupFile.Complete(record.Path, record.Bytes);
    }
    /// <summary>The startup-only restriction remains active until verified resume succeeds.</summary>
    public bool IsReleased => System.Threading.Volatile.Read(ref _released) != 0;
    /// <summary>Publish normal startup behavior before releasing scheduling waiters.</summary>
    internal void MarkReleased() => System.Threading.Volatile.Write(ref _released, 1);
    /// <summary>Keep both manual and automatic launches endpoint-only while startup is held.</summary>
    internal string? SelectStartupMode(string? requested)
    {
        if (IsReleased) return requested;
        if (requested is not null and not "controlEndpoint")
            throw new InvalidOperationException("Upgrade startup permits only an endpoint child until explicit resume.");
        return "controlEndpoint";
    }

    /// <summary>Validate the complete explicit startup identity without accessing any process.</summary>
    public UpgradeSessionBinding(int sessionId, int gameProcessId, long gameStartedFileTime)
    {
        if (sessionId <= 0 || gameProcessId <= 0 || gameStartedFileTime <= 0)
            throw new ArgumentException("Upgrade startup requires positive session, game PID and creation time.");
        _ = DateTime.FromFileTimeUtc(gameStartedFileTime);
        SessionId = sessionId;
        GameProcessId = gameProcessId;
        GameStartedFileTime = gameStartedFileTime;
    }

    /// <summary>Recheck the live native identity immediately before connecting or launching an endpoint child.</summary>
    internal void VerifyExisting(uint? actualSessionId)
    {
        if (actualSessionId != (uint)SessionId)
            throw new InvalidOperationException("The original desktop clone no longer exists.");
        using var game = Process.GetProcessById(GameProcessId);
        VerifyGame(game.Id, game.SessionId, game.StartTime.ToUniversalTime().ToFileTimeUtc(),
            game.ProcessName, game.HasExited);
    }

    /// <summary>Pure identity predicate, also used by inactive fixtures; no name-only fallback is allowed.</summary>
    internal void VerifyGame(int processId, int sessionId, long startedFileTime, string name, bool exited)
    {
        if (exited || processId != GameProcessId || sessionId != SessionId
            || startedFileTime != GameStartedFileTime || name is not ("YuanShen" or "GenshinImpact"))
            throw new InvalidOperationException("The protected game lifetime no longer matches upgrade startup.");
    }
}
