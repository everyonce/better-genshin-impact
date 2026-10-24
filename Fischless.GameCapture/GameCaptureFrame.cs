using OpenCvSharp;
using Vanara.PInvoke;

namespace Fischless.GameCapture;

public sealed class GameCaptureFrame : IDisposable
{
    /// <summary>Own a pixel frame while preserving the original public constructor signature.</summary>
    /// <param name="frame">Pixels owned by this frame and released on disposal.</param>
    /// <param name="captureRect">Desktop bounds corresponding to these pixels, when known.</param>
    public GameCaptureFrame(Mat frame, RECT? captureRect = null)
        : this(frame, captureRect, null)
    {
    }

    /// <summary>Own pixels together with immutable identity and timing from their capture source.</summary>
    /// <param name="frame">Pixels owned by this frame and released on disposal.</param>
    /// <param name="captureRect">Desktop bounds corresponding to these pixels, when known.</param>
    /// <param name="sourceInfo">Source identity and timing; null when the backend cannot supply them.</param>
    public GameCaptureFrame(Mat frame, RECT? captureRect, GameCaptureSourceInfo? sourceInfo)
        : this(frame, captureRect, sourceInfo, null)
    {
    }

    /// <summary>Own pixels with exactly one optional evidence kind; host acquisition is not a WGC source timestamp.</summary>
    /// <param name="frame">Independently owned pixels released on disposal.</param>
    /// <param name="captureRect">Physical desktop crop corresponding to the pixels.</param>
    /// <param name="sourceInfo">Original capture-source evidence, or null for a host snapshot.</param>
    /// <param name="hostSnapshotInfo">Host acquisition interval, or null for existing backends.</param>
    public GameCaptureFrame(Mat frame, RECT? captureRect, GameCaptureSourceInfo? sourceInfo,
        GameCaptureHostSnapshotInfo? hostSnapshotInfo)
    {
        if (sourceInfo is not null && hostSnapshotInfo is not null)
            throw new ArgumentException("A frame cannot combine source and host-snapshot evidence.");
        Frame = frame;
        CaptureRect = captureRect;
        SourceInfo = sourceInfo;
        HostSnapshotInfo = hostSnapshotInfo;
    }

    public Mat Frame { get; }

    public RECT? CaptureRect { get; }

    /// <summary>Identity and timing of the exact source frame; cached copies retain the same metadata.</summary>
    public GameCaptureSourceInfo? SourceInfo { get; }

    /// <summary>Original host acquisition identity and interval; neither a render timestamp nor input authority.</summary>
    public GameCaptureHostSnapshotInfo? HostSnapshotInfo { get; }

    public void Dispose()
    {
        Frame.Dispose();
        GC.SuppressFinalize(this);
    }
}
