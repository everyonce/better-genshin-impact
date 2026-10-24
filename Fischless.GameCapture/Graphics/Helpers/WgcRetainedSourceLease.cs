namespace Fischless.GameCapture.Graphics.Helpers;

/// <summary>Experimental selected-frame ownership only; contains no native calls, waits, counters or retry policy.</summary>
internal sealed class WgcRetainedSourceLease
{
    /// <summary>The selected pool frame remains checked out until successful readback or session teardown.</summary>
    private IDisposable? _frame;
    /// <summary>The queried texture wrapper is released before its owning pool frame.</summary>
    private IDisposable? _surface;

    /// <summary>Preserve the exact selected source identity without reading or updating any clock.</summary>
    public GameCaptureSourceInfo Source { get; }
    /// <summary>Whether both resources have been detached, including a disposal failure.</summary>
    public bool Released => _frame is null;

    /// <summary>Accept ownership only after callers validate the selected generation and geometry.</summary>
    public WgcRetainedSourceLease(IDisposable frame, GameCaptureSourceInfo source)
    {
        _frame = frame ?? throw new ArgumentNullException(nameof(frame));
        Source = source ?? throw new ArgumentNullException(nameof(source));
    }

    /// <summary>Attach one surface before HDR, Draw or Copy can consume it; rejected input remains caller-owned.</summary>
    public void AttachSurface(IDisposable surface)
    {
        ArgumentNullException.ThrowIfNull(surface);
        if (_frame is null || _surface is not null)
            throw new InvalidOperationException("Retained WGC surface cannot be attached twice or after release.");
        _surface = surface;
    }

    /// <summary>Detach before callbacks; attempt both releases exactly once, even when either throws or reenters.</summary>
    public void Release()
    {
        var surface = _surface;
        var frame = _frame;
        _surface = null;
        _frame = null;
        List<Exception>? errors = null;
        try { surface?.Dispose(); }
        catch (Exception error) { (errors ??= []).Add(error); }
        try { frame?.Dispose(); }
        catch (Exception error) { (errors ??= []).Add(error); }
        if (errors is not null) throw new AggregateException("Retained WGC source release failed.", errors);
    }
}
