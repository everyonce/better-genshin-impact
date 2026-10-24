namespace Fischless.GameCapture;

/// <summary>Immutable per-call result. Only FrameReady transfers a frame which the caller must dispose once.</summary>
public readonly record struct GameCaptureAttempt
{
    /// <summary>The exact outcome of this invocation, never inferred from a shared last-call property.</summary>
    public GameCaptureAttemptOutcome Outcome { get; }
    /// <summary>Caller-owned pixels, present only for FrameReady; disposing this value does not dispose pixels.</summary>
    public GameCaptureFrame? Frame { get; }
    /// <summary>Unpublished work, including a refill after FrameReady; this is not accepted image evidence.</summary>
    public GameCapturePendingReadback? Pending { get; }

    /// <summary>Construct a valid result; default(GameCaptureAttempt) is an unavailable result.</summary>
    /// <param name="outcome">Outcome of this call.</param>
    /// <param name="frame">Owned frame only when outcome is FrameReady.</param>
    /// <param name="pending">Required for ReadbackPending, optional for a ready frame followed by refill.</param>
    public GameCaptureAttempt(GameCaptureAttemptOutcome outcome, GameCaptureFrame? frame = null,
        GameCapturePendingReadback? pending = null)
    {
        if (!Enum.IsDefined(outcome) || (outcome == GameCaptureAttemptOutcome.FrameReady) != (frame is not null)
            || (outcome == GameCaptureAttemptOutcome.ReadbackPending && pending is null)
            || (outcome == GameCaptureAttemptOutcome.Unavailable && pending is not null))
            throw new ArgumentException("The readback outcome, owned frame and pending descriptor do not agree.");
        Outcome = outcome;
        Frame = frame;
        Pending = pending;
    }
}
