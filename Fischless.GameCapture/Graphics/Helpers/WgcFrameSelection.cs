using System.Diagnostics;
using Windows.Graphics;

namespace Fischless.GameCapture.Graphics.Helpers;

/// <summary>
/// Selects from the two-buffer WGC pool without rendering discarded frames. The small
/// frame/property delegates let ownership and source ordering be checked without WinRT.
/// </summary>
internal static class WgcFrameSelection
{
    /// <summary>
    /// Pull at most twice, stamping each non-null acquisition before reading its properties.
    /// Return the newest accepted frame to the caller, who owns its disposal. An accepted
    /// geometry change stops lookahead immediately; the caller retains the existing resize path.
    /// Outputs retain the last known accepted geometry even on failure so old-size publication
    /// can be invalidated if disposal of a superseded candidate fails.
    /// </summary>
    internal static TFrame? TakeNewest<TFrame>(Func<TFrame?> takeNext,
        Func<TFrame, long> timestamp, Func<TFrame, SizeInt32> size,
        WgcCaptureGeneration? generation, SizeInt32 currentSize,
        out GameCaptureSourceInfo? selectedSource, out SizeInt32 selectedSize,
        GameCaptureCallTiming? timing = null, Func<long>? acquisitionClock = null)
        where TFrame : class, IDisposable
    {
        selectedSource = null;
        selectedSize = currentSize;
        TFrame? selected = null;
        var sawFrame = false;
        if (timing is not null)
        {
            timing.LastStage = "pool";
            timing.PoolStartedAtTicks = Stopwatch.GetTimestamp();
        }
        try
        {
            try
            {
                // Two attempts match the native pool's fixed capacity; never drain until empty.
                for (var attempt = 0; attempt < 2; attempt++)
                {
                    TFrame? candidate = null;
                    try
                    {
                        if (timing is not null) timing.PoolPullCount++;
                        candidate = takeNext();
                        if (candidate is null) break;
                        // This clock belongs to this acquisition, not the later selected render.
                        var acquiredAt = acquisitionClock?.Invoke() ?? Stopwatch.GetTimestamp();
                        sawFrame = true;
                        if (timing is not null) timing.PoolFrameCount++;
                        var source = generation?.TryAcquire(timestamp(candidate), acquiredAt);
                        if (source is null) continue;
                        if (timing is not null) timing.AcquiredSource = source;
                        var contentSize = size(candidate);

                        // Advance high-water before disposal/render, even for a superseded frame.
                        // Transfer the new owner first so both frames get a disposal attempt if
                        // releasing the old one throws; no failed candidate can escape to render.
                        var previous = selected;
                        selected = candidate;
                        candidate = null;
                        selectedSource = source;
                        selectedSize = contentSize;
                        DisposeDiscarded(ref previous, timing);
                        if (contentSize.Width != currentSize.Width || contentSize.Height != currentSize.Height)
                            break;
                    }
                    finally
                    {
                        DisposeDiscarded(ref candidate, timing);
                    }
                }

                if (timing is not null)
                    timing.PoolResult = selected is not null ? "acquired" : sawFrame ? "rejected_identity" : "empty";
                var result = selected;
                selected = null; // Only the returned frame changes ownership to the renderer.
                return result;
            }
            finally
            {
                DisposeDiscarded(ref selected, timing);
            }
        }
        catch (Exception error)
        {
            if (timing is not null)
            {
                timing.PoolResult = "threw";
                timing.RecordFailure(error);
            }
            throw;
        }
        finally
        {
            if (timing is not null) timing.PoolCompletedAtTicks = Stopwatch.GetTimestamp();
        }
    }

    /// <summary>Clear ownership before disposal so a throwing native Close is never retried accidentally.</summary>
    private static void DisposeDiscarded<TFrame>(ref TFrame? frame, GameCaptureCallTiming? timing)
        where TFrame : class, IDisposable
    {
        var owned = frame;
        frame = null;
        if (owned is null) return;
        if (timing is not null) timing.PoolDiscardedFrameCount++;
        owned.Dispose();
    }
}
