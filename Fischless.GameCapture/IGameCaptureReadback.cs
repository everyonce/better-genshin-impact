namespace Fischless.GameCapture;

/// <summary>Optional per-call readback outcomes; legacy capture interfaces retain their signatures.</summary>
public interface IGameCaptureReadback
{
    /// <summary>Immutable selection for the current Start lifetime.</summary>
    GameCaptureReadbackMode ReadbackMode { get; }
    /// <summary>Acquire once without waiting for a polling-mode staging copy to become readable.</summary>
    GameCaptureAttempt CaptureAttempt();
    /// <summary>The same native operations with invocation-local timing, including pending and failure.</summary>
    GameCaptureAttempt CaptureAttempt(out GameCaptureCallTiming timing);
}

/// <summary>Explicit readback selection; blocking remains the default on every Start.</summary>
public enum GameCaptureReadbackMode
{
    /// <summary>Existing synchronous readback sequence.</summary>
    Blocking = 0,
    /// <summary>One staging submission, polled once per invocation with DoNotWait.</summary>
    PollSingleV1 = 1
}

/// <summary>This call's pixel result, independent of whether its refill left another pending copy.</summary>
public enum GameCaptureAttemptOutcome
{
    /// <summary>No pixels or pending work can be returned, including a stopped/faulted capture.</summary>
    Unavailable = 0,
    /// <summary>An independently owned frame is returned; unchanged cache identity is still possible.</summary>
    FrameReady = 1,
    /// <summary>A particular staging copy is still busy; no cached pixels are supplied.</summary>
    ReadbackPending = 2
}
