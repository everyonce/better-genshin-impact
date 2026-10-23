using System;
using System.Threading;
using System.Threading.Tasks;
using OpenCvSharp;

namespace BetterGenshinImpact.Core.Script.Dependence;

/// <summary>
/// Bounds background image writes and owns each snapshot until its writer finishes.
/// </summary>
internal sealed class CaptureWriteQueue
{
    /// <summary>Admission slots include snapshots currently being cloned or written.</summary>
    private readonly SemaphoreSlim _slots;

    /// <summary>Creates a writer with a fixed maximum number of owned snapshots.</summary>
    internal CaptureWriteQueue(int capacity)
    {
        if (capacity <= 0) throw new ArgumentOutOfRangeException(nameof(capacity));
        _slots = new SemaphoreSlim(capacity, capacity);
    }

    /// <summary>
    /// Copies the source before returning, then writes off the caller's thread.
    /// Refuses immediately when full, without retaining or cloning the source.
    /// </summary>
    internal Task<bool> TryWriteAsync(Mat source, Func<Mat, bool> write)
    {
        if (!_slots.Wait(0)) return Task.FromResult(false);
        Mat? snapshot = null;
        try
        {
            // A JS ImageRegion may be disposed or reused immediately after this call.
            snapshot = source.Clone();
            var owned = snapshot;
            return Task.Run(() =>
            {
                try
                {
                    using (owned) return write(owned);
                }
                finally
                {
                    // Dispose the native image before admitting another allocation.
                    _slots.Release();
                }
            });
        }
        catch
        {
            snapshot?.Dispose();
            _slots.Release();
            throw;
        }
    }
}
