namespace Fischless.GameCapture.DesktopDc;

/// <summary>Read successful capture diagnostics without granting freshness or input authority.</summary>
public interface IDesktopDcCaptureDiagnostics
{
    /// <summary>Return timings only for the identical successful snapshot, or null after another attempt or retirement.</summary>
    DesktopDcCaptureTiming? GetTiming(GameCaptureHostSnapshotInfo snapshot);
}
