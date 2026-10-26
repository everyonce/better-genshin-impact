namespace Fischless.GameCapture.DesktopDc;

/// <summary>Bounded immutable wall timings for one successful acquisition; never render timestamps or authority.</summary>
public sealed class DesktopDcCaptureTiming
{
    /// <summary>Exact object identity prevents another acquisition or reconstructed metadata from selecting this record.</summary>
    private readonly GameCaptureHostSnapshotInfo _snapshot;

    /// <summary>Copy scalar durations only; neither native handles, pixels nor mutable recorder arrays escape.</summary>
    internal DesktopDcCaptureTiming(GameCaptureHostSnapshotInfo snapshot, long frequency, long totalTicks,
        long unattributedTicks, long[] phases)
    {
        _snapshot = snapshot;
        ClockFrequency = frequency;
        var scale = 1000.0 / frequency;
        TotalMs = totalTicks * scale;
        UnattributedMs = unattributedTicks * scale;
        GateWaitMs = phases[(int)DesktopDcCapturePhase.GateWait] * scale;
        DpiSetupMs = phases[(int)DesktopDcCapturePhase.DpiSetup] * scale;
        PreTargetCheckMs = phases[(int)DesktopDcCapturePhase.PreTargetCheck] * scale;
        AllocationMs = phases[(int)DesktopDcCapturePhase.Allocation] * scale;
        BitBltMs = phases[(int)DesktopDcCapturePhase.BitBlt] * scale;
        FirstFlushMs = phases[(int)DesktopDcCapturePhase.FirstFlush] * scale;
        PostTargetCheckMs = phases[(int)DesktopDcCapturePhase.PostTargetCheck] * scale;
        CloneMs = phases[(int)DesktopDcCapturePhase.Clone] * scale;
        CleanupMs = phases[(int)DesktopDcCapturePhase.Cleanup] * scale;
        DpiRestoreMs = phases[(int)DesktopDcCapturePhase.DpiRestore] * scale;
    }

    /// <summary>Diagnostic grammar version; independent of the unchanged host-snapshot schema.</summary>
    public int Version => 1;
    /// <summary>Explicitly excludes this record from freshness, readiness and input admission.</summary>
    public bool DiagnosticOnly => true;
    /// <summary>Successful acquisition generation, copied only for an exact frame join.</summary>
    public string CaptureEpoch => _snapshot.CaptureEpoch.ToString("N");
    /// <summary>Successful acquisition identity within its generation.</summary>
    public long SnapshotId => _snapshot.SnapshotId;
    /// <summary>Frequency of the separate monotonic diagnostic clock.</summary>
    public long ClockFrequency { get; }
    /// <summary>First diagnostic sample through successful acquisition publication, including gate wait and bookkeeping.</summary>
    public double TotalMs { get; }
    /// <summary>Uninstrumented bookkeeping between nonoverlapping phase intervals.</summary>
    public double UnattributedMs { get; }
    /// <summary>Time before entry into the capture gate, including scheduling and lock wait.</summary>
    public double GateWaitMs { get; }
    /// <summary>Entry into the caller-local DPI scope.</summary>
    public double DpiSetupMs { get; }
    /// <summary>Complete original target validation before GDI allocation.</summary>
    public double PreTargetCheckMs { get; }
    /// <summary>Original DC/DIB allocation, format checks and bitmap selection.</summary>
    public double AllocationMs { get; }
    /// <summary>Original single SRCCOPY call; wall time may include native waiting.</summary>
    public double BitBltMs { get; }
    /// <summary>First GdiFlush after the copy, separate from cleanup's original flush.</summary>
    public double FirstFlushMs { get; }
    /// <summary>Complete original target validation after the copy and flush.</summary>
    public double PostTargetCheckMs { get; }
    /// <summary>Independent pixel clone and borrowed-header retirement.</summary>
    public double CloneMs { get; }
    /// <summary>Original complete GDI disposal, including its second flush and all handle releases.</summary>
    public double CleanupMs { get; }
    /// <summary>Restoration of the caller's original DPI context.</summary>
    public double DpiRestoreMs { get; }

    /// <summary>Match the actual returned snapshot rather than a caller-supplied equivalent value.</summary>
    internal bool IsFor(GameCaptureHostSnapshotInfo snapshot) => ReferenceEquals(_snapshot, snapshot);
}
