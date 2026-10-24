using System;
using System.Diagnostics;
using System.Threading;
using BetterGenshinImpact.GameTask.AutoGeniusInvokation.Exception;
using BetterGenshinImpact.GameTask.Runtime;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.Common;

/// <summary>Explicit reset-teleport compatibility for pixel-free polling outcomes; no input, cache, or capture-mode changes.</summary>
internal static class TeleportCaptureReadback
{
    /// <summary>One screenshot request must finish within this monotonic window, including native calls.</summary>
    internal const int WindowMilliseconds = 2000;
    /// <summary>Bound actual capture calls even if an injected or unusual clock stops advancing.</summary>
    internal const int MaximumCaptureCalls = 200;
    /// <summary>Only typed Pending receives this short cancellable spacing.</summary>
    internal const int PendingDelayMilliseconds = 10;

    /// <summary>Read one owned frame in explicit polling mode. Unavailable retains the legacy four-attempt/three-delay limit.</summary>
    /// <param name="capture">The exact runtime-owned capture instance, already in PollSingleV1 mode.</param>
    /// <param name="ct">The linked teleport/owner/runtime cancellation token.</param>
    /// <param name="ensureTarget">Validate the same live target without input, activation, or capture.</param>
    /// <param name="unavailableWarning">Optional existing screenshot-failure warning, invoked once on first Unavailable.</param>
    /// <param name="nowMilliseconds">Test seam for monotonic time; production uses QPC.</param>
    /// <param name="delay">Test seam for a cancellable wait; production does not create a worker.</param>
    internal static GameCaptureFrame Capture(IGameCapture capture, CancellationToken ct, Action ensureTarget,
        Action? unavailableWarning = null, Func<double>? nowMilliseconds = null,
        Action<int, CancellationToken>? delay = null)
    {
        nowMilliseconds ??= static () => Stopwatch.GetTimestamp() * 1000d / Stopwatch.Frequency;
        delay ??= static (milliseconds, token) =>
        {
            if (token.WaitHandle.WaitOne(milliseconds)) token.ThrowIfCancellationRequested();
        };
        ct.ThrowIfCancellationRequested();
        var readback = capture as IGameCaptureReadback
            ?? throw new TeleportCaptureAbortedException(TeleportCaptureAbortReason.ModeChanged);
        var previous = nowMilliseconds();
        if (!double.IsFinite(previous) || previous < 0) throw new TeleportCaptureAbortedException(TeleportCaptureAbortReason.InvalidClock);
        var deadline = previous + WindowMilliseconds;
        var unavailable = 0;
        var calls = 0;

        // Context failures also take precedence when a native call throws instead of returning a typed result.
        void CheckContext()
        {
            ct.ThrowIfCancellationRequested();
            ensureTarget();
            ct.ThrowIfCancellationRequested();
            if (capture is not IGameCaptureReadback { ReadbackMode: GameCaptureReadbackMode.PollSingleV1 })
                throw new TeleportCaptureAbortedException(TeleportCaptureAbortReason.ModeChanged);
            if (!capture.IsCapturing)
                throw new TeleportCaptureAbortedException(TeleportCaptureAbortReason.CaptureStopped);
        }

        // Checks bracket every synchronous native call. A late result is disposed, never handed to a UI action.
        void Check()
        {
            CheckContext();
            var now = nowMilliseconds();
            if (!double.IsFinite(now) || now < previous)
                throw new TeleportCaptureAbortedException(TeleportCaptureAbortReason.InvalidClock);
            previous = now;
            if (now >= deadline)
                throw new TeleportCaptureAbortedException(TeleportCaptureAbortReason.Deadline);
        }

        while (true)
        {
            Check();
            if (calls >= MaximumCaptureCalls)
                throw new TeleportCaptureAbortedException(TeleportCaptureAbortReason.CallLimit);
            calls++;
            GameCaptureAttempt attempt;
            try
            {
                // Call the pinned typed API directly: a concurrent mode change must never select the legacy fallback.
                // The immutable GameCaptureAttempt constructor enforces outcome/frame ownership consistency.
                attempt = readback.CaptureAttempt();
                if (attempt.Outcome == GameCaptureAttemptOutcome.ReadbackPending)
                {
                    try
                    {
                        GameCaptureReadbackConsumer.ValidatePending(attempt.Pending!, Stopwatch.GetTimestamp());
                    }
                    catch (InvalidOperationException invalidMetadata)
                    {
                        // This pure validator's failure is distinct from a native CaptureAttempt exception.
                        throw new TeleportCaptureAbortedException(TeleportCaptureAbortReason.InvalidPendingMetadata, invalidMetadata);
                    }
                }
            }
            catch
            {
                CheckContext();
                throw;
            }
            var owned = attempt.Frame;
            try
            {
                Check();
                if (attempt.Outcome == GameCaptureAttemptOutcome.FrameReady)
                {
                    // Ready plus a next pending reservation is still this exact owned frame.
                    var frame = owned!;
                    owned = null;
                    return frame;
                }
                if (attempt.Outcome == GameCaptureAttemptOutcome.ReadbackPending)
                {
                    if (calls >= MaximumCaptureCalls)
                        throw new TeleportCaptureAbortedException(TeleportCaptureAbortReason.CallLimit);
                    delay(PendingDelayMilliseconds, ct);
                    continue;
                }

                // The old helper retries its first null immediately, then sleeps after each of the next three nulls.
                unavailable++;
                if (unavailable == 1) unavailableWarning?.Invoke();
                else delay(30, ct);
                Check();
                if (unavailable == 4) throw new Exception("Screenshot failed after multiple attempts!");
            }
            finally
            {
                owned?.Dispose();
            }
        }
    }

    /// <summary>Exact abort types that opt-in UI helpers must propagate before another map action; no message matching.</summary>
    internal static bool IsTerminal(Exception error) =>
        error is TeleportCaptureAbortedException or OperationCanceledException or NormalEndException;
}

/// <summary>Known reasons an opted-in teleport cannot safely resume its UI retry loops.</summary>
internal enum TeleportCaptureAbortReason
{
    /// <summary>The screenshot request's two-second window expired.</summary>
    Deadline,
    /// <summary>The screenshot request consumed all 200 actual calls.</summary>
    CallLimit,
    /// <summary>The monotonic clock became nonfinite or regressed.</summary>
    InvalidClock,
    /// <summary>The original runtime target is no longer available.</summary>
    TargetUnavailable,
    /// <summary>The explicitly pinned polling mode changed.</summary>
    ModeChanged,
    /// <summary>The original capture stopped.</summary>
    CaptureStopped,
    /// <summary>The typed Pending descriptor failed the existing structural/source-clock validator.</summary>
    InvalidPendingMetadata
}

/// <summary>A typed terminal capture boundary; repeating teleport or a UI fallback cannot repair this request.</summary>
internal sealed class TeleportCaptureAbortedException : Exception
{
    /// <summary>Construct a stable diagnostic retaining its exact typed cause.</summary>
    /// <param name="reason">The failed capture boundary.</param>
    /// <param name="innerException">Original pure-validator failure, when present; never a message-classified native error.</param>
    internal TeleportCaptureAbortedException(TeleportCaptureAbortReason reason, Exception? innerException = null)
        : base($"Teleport capture aborted: {reason}", innerException) => Reason = reason;

    /// <summary>Machine-readable cause used by tests and diagnostics; never inferred from text.</summary>
    internal TeleportCaptureAbortReason Reason { get; }
}
