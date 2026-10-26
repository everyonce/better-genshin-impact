namespace Fischless.GameCapture.DesktopDc;

/// <summary>Fixed nonoverlapping phases; no dynamically named samples or unbounded retained history.</summary>
internal enum DesktopDcCapturePhase
{
    /// <summary>Request entry until capture-gate acquisition.</summary>
    GateWait,
    /// <summary>Caller-local DPI admission.</summary>
    DpiSetup,
    /// <summary>Target validation before allocating native resources.</summary>
    PreTargetCheck,
    /// <summary>DC/DIB creation and selection.</summary>
    Allocation,
    /// <summary>The existing native SRCCOPY.</summary>
    BitBlt,
    /// <summary>Completion flush immediately after SRCCOPY.</summary>
    FirstFlush,
    /// <summary>Target validation before pixel cloning.</summary>
    PostTargetCheck,
    /// <summary>Independent pixel cloning and borrowed-header cleanup.</summary>
    Clone,
    /// <summary>Complete original GDI ownership cleanup.</summary>
    Cleanup,
    /// <summary>Restore the caller's original DPI scope.</summary>
    DpiRestore
}

/// <summary>One small request-owned recorder; diagnostic failure never changes capture or cleanup behavior.</summary>
internal sealed class DesktopDcCapturePhaseRecorder(Func<long> timestamp, long frequency)
{
    /// <summary>Exactly ten durations; each phase can be completed once.</summary>
    private readonly long[] _durations = new long[10];
    /// <summary>Monotonic diagnostic endpoints are separate from the two authoritative host clock reads.</summary>
    private long _started, _phaseStarted, _last;
    /// <summary>Only one phase may be active; its absence is represented by minus one.</summary>
    private int _active = -1;
    /// <summary>Completed phases and sticky invalidity prevent partial or overlapping records from escaping.</summary>
    private int _completed;
    /// <summary>A failed clock discards only diagnostics, including on an otherwise successful capture.</summary>
    private bool _valid = frequency > 0;

    /// <summary>Begin one existing operation without invoking, replacing or retrying it.</summary>
    internal void Begin(DesktopDcCapturePhase phase)
    {
        if (!_valid) return;
        var index = (int)phase;
        if (_active != -1 || (_completed & (1 << index)) != 0 || !TryStamp(out var now))
        { _valid = false; return; }
        if (phase == DesktopDcCapturePhase.GateWait) _started = now;
        _phaseStarted = now;
        _active = index;
    }

    /// <summary>End only the matching phase; failed operations do not publish partial diagnostics.</summary>
    internal void End(DesktopDcCapturePhase phase)
    {
        if (!_valid) return;
        if (_active != (int)phase || !TryStamp(out var now)) { _valid = false; return; }
        _durations[_active] = now - _phaseStarted;
        _completed |= 1 << _active;
        _active = -1;
    }

    /// <summary>Freeze a complete successful record, rejecting invalid clocks rather than clamping durations.</summary>
    internal DesktopDcCaptureTiming? Complete(GameCaptureHostSnapshotInfo snapshot)
    {
        if (!_valid || _active != -1 || _completed != (1 << _durations.Length) - 1 || !TryStamp(out var now)) return null;
        try
        {
            var total = now - _started;
            long attributed = 0;
            foreach (var duration in _durations) attributed = checked(attributed + duration);
            if (attributed > total) return null;
            return new DesktopDcCaptureTiming(snapshot, frequency, total, total - attributed, _durations);
        }
        catch (Exception) { return null; } // Diagnostic conversion/allocation cannot mask successful ownership cleanup.
    }

    /// <summary>Clock faults/regressions are diagnostic-only and must not interrupt native ownership cleanup.</summary>
    private bool TryStamp(out long now)
    {
        now = 0;
        try
        {
            now = timestamp();
            if (now < 0 || now < _last) { _valid = false; return false; }
            _last = now;
            return true;
        }
        catch (Exception) { _valid = false; return false; }
    }
}
