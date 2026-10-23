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
    {
        Frame = frame;
        CaptureRect = captureRect;
        SourceInfo = sourceInfo;
    }

    public Mat Frame { get; }

    public RECT? CaptureRect { get; }

    /// <summary>Identity and timing of the exact source frame; cached copies retain the same metadata.</summary>
    public GameCaptureSourceInfo? SourceInfo { get; }

    public void Dispose()
    {
        Frame.Dispose();
        GC.SuppressFinalize(this);
    }
}
