namespace Fischless.GameCapture;

/// <summary>Optional per-invocation diagnostics; ordinary capture and frame ownership remain unchanged.</summary>
public interface IGameCaptureDiagnostics
{
    /// <summary>Capture once, assigning diagnostics even when the call returns null or throws.</summary>
    GameCaptureFrame? Capture(out GameCaptureCallTiming timing);
}
