namespace Fischless.GameCapture.Graphics.Helpers;

/// <summary>
/// One Start's callback lifetime and immutable source high-water mark. Pixel-cache
/// invalidation never resets this identity; callers serialize frame acquisition.
/// </summary>
internal sealed class WgcCaptureGeneration
{
    /// <summary>Atomic callback admission; retired callbacks cannot affect a replacement session.</summary>
    private int _active = 1;
    /// <summary>Diagnostic arrival count for this generation only.</summary>
    private long _arrivals;
    /// <summary>Last acquired source, retained even when rendering or resize invalidates pixels.</summary>
    private GameCaptureSourceInfo? _lastAcquired;

    /// <summary>Unique identity created once per Start, never reused after stop.</summary>
    public Guid Epoch { get; } = Guid.NewGuid();
    /// <summary>Whether this generation can still publish frames or request a stop.</summary>
    public bool IsActive => Volatile.Read(ref _active) != 0;
    /// <summary>Arrival signals received by this generation, independent of actual acquisition.</summary>
    public long Arrivals => Interlocked.Read(ref _arrivals);

    /// <summary>Signal-only callback: no capture, device work, or lifecycle lock.</summary>
    public void SignalArrival()
    {
        if (IsActive) Interlocked.Increment(ref _arrivals);
    }

    /// <summary>Closes callback admission once; the winner may queue generation-checked cleanup.</summary>
    public bool Deactivate() => Interlocked.Exchange(ref _active, 0) != 0;

    /// <summary>
    /// Acquires each strictly newer source once. Repeats/regressions are dropped,
    /// so a failed render or repeated cached image cannot renew acquisition time.
    /// </summary>
    public GameCaptureSourceInfo? TryAcquire(long sourceTimestamp100ns, long acquiredAtStopwatchTicks)
    {
        if (!IsActive || sourceTimestamp100ns <= 0 ||
            (_lastAcquired is { } previous && sourceTimestamp100ns <= previous.SourceTimestamp100ns))
            return null;
        _lastAcquired = new GameCaptureSourceInfo(Epoch, sourceTimestamp100ns, acquiredAtStopwatchTicks);
        return _lastAcquired;
    }
}
