using System.Diagnostics;
using System.Runtime.InteropServices;
using Fischless.GameCapture.Graphics.Helpers;
using OpenCvSharp;
using SharpDX;
using SharpDX.Direct3D11;

namespace Fischless.GameCapture.Graphics;

/// <summary>Explicit one-slot readback branch; the original blocking CaptureCore remains independent.</summary>
public partial class GraphicsCaptureV2
{
    /// <summary>Fixed selection for a Start lifetime; a later Start with no setting returns to Blocking.</summary>
    public GameCaptureReadbackMode ReadbackMode { get; private set; }
    /// <summary>One generation-bound metadata reservation; idle pending work never increments active captures.</summary>
    private WgcReadbackSlot? _readbackSlot;
    /// <summary>Alias of the existing staging member reserved by the slot; only normal session cleanup owns disposal.</summary>
    private SharpDX.Direct3D11.Resource? _pendingReadbackResource;
    /// <summary>Conversion path captured at submission, never inferred from a subsequent resource.</summary>
    private bool _pendingReadbackCpuConvert;

    /// <inheritdoc />
    public GameCaptureAttempt CaptureAttempt()
    {
        if (ReadbackMode == GameCaptureReadbackMode.PollSingleV1) return CapturePolling(null);
        var frame = CaptureCore(null);
        return frame is null ? default : new(GameCaptureAttemptOutcome.FrameReady, frame);
    }

    /// <inheritdoc />
    public GameCaptureAttempt CaptureAttempt(out GameCaptureCallTiming timing)
    {
        if (ReadbackMode == GameCaptureReadbackMode.PollSingleV1)
            return GameCaptureCallTiming.RunAttempt(CapturePolling, out timing);
        var frame = GameCaptureCallTiming.Run(CaptureCore, out timing);
        return frame is null ? default : new(GameCaptureAttemptOutcome.FrameReady, frame);
    }

    /// <summary>At most one Map attempt and one new staging submission; no GPU wait loop or cached pixels on busy.</summary>
    private GameCaptureAttempt CapturePolling(GameCaptureCallTiming? timing)
    {
        var entered = false;
        var active = false;
        Mat? target = null;
        WgcReadbackSlot? slot = null;
        WgcCaptureGeneration? generation = null;
        try
        {
            // Match the ordinary/diagnostic locking contract; diagnostics only observe the zero-time probe.
            if (timing is null) Monitor.Enter(_captureGate, ref entered);
            else
            {
                timing.CaptureGateProbeStartedAtTicks = Stopwatch.GetTimestamp();
                Monitor.TryEnter(_captureGate, 0, ref entered);
                timing.CaptureGateContended = !entered;
                timing.CaptureGateProbeCompletedAtTicks = Stopwatch.GetTimestamp();
                if (!entered) Monitor.Enter(_captureGate, ref entered);
                timing.CaptureGateAcquiredAtTicks = Stopwatch.GetTimestamp();
                timing.LastStage = "state_lock";
            }
            lock (_lock)
            {
                if (timing is not null)
                {
                    timing.StateLockAcquiredAtTicks = Stopwatch.GetTimestamp();
                    timing.LastStage = "state_check";
                    timing.CpuConvert = _useCpuConvert;
                    timing.DrawWrite = _useDrawWrite;
                }
                slot = _readbackSlot;
                generation = _generation;
                if (ReadbackMode != GameCaptureReadbackMode.PollSingleV1 || !IsCapturing || generation?.IsActive != true
                    || slot is null || slot.IsStopped || slot.IsFaulted || _sourceRetentionFaulted)
                    return default;
                // Only this synchronous invocation owns this count, including copy outside _lock.
                _activeCaptures++;
                active = true;
            }

            var pendingOnEntry = slot.Pending is not null;
            if (!pendingOnEntry)
            {
                lock (_lock)
                {
                    if (!PollingGenerationIsActive(generation)) return default;
                    RenderAndSubmitPolling(slot, timing);
                    if (slot.Pending is null)
                    {
                        if (!PollingGenerationIsActive(generation) || _cachedBgr is null || _cachedFrameTs == 0
                            || _cachedSourceInfo is null || _cachedFrameTs != _gpuFrameTs) return default;
                        if (timing is not null)
                        {
                            timing.CacheHit = true;
                            timing.LastStage = "cpu_copy";
                            timing.CpuCopyStartedAtTicks = Stopwatch.GetTimestamp();
                        }
                        try
                        {
                            target = AcquireBgrMat(_cachedBgr.Rows, _cachedBgr.Cols);
                            _cachedBgr.CopyTo(target);
                        }
                        finally { if (timing is not null) timing.CpuCopyCompletedAtTicks = Stopwatch.GetTimestamp(); }
                        return TransferPollingFrame(ref target, _cachedCaptureRect, _cachedSourceInfo, null);
                    }
                }
            }

            var pending = slot.Pending!;
            var staging = _pendingReadbackResource ?? throw new InvalidOperationException("Pending staging resource is missing.");
            var cpuConvert = _pendingReadbackCpuConvert;
            var context = staging.Device.ImmediateContext;
            if (timing is not null) { timing.CacheHit = false; timing.PolledReadback = pending; }
            // Copy into a caller-owned pooled Mat; the cache is untouched until Unmap has succeeded.
            var complete = slot.TryComplete(
                () => MapPolling(context, staging, timing),
                mapped =>
                {
                    ValidatePollingMap(mapped, pending.Width, pending.Height, cpuConvert);
                    if (timing is not null)
                    {
                        timing.LastStage = "cpu_copy";
                        timing.CpuCopyStartedAtTicks = Stopwatch.GetTimestamp();
                    }
                    target = AcquireBgrMat(pending.Height, pending.Width);
                    if (cpuConvert)
                    {
                        using var bgra = Mat.FromPixelData(pending.Height, pending.Width, MatType.CV_8UC4,
                            mapped.DataPointer, mapped.RowPitch);
                        Cv2.CvtColor(bgra, target, ColorConversionCodes.BGRA2BGR);
                    }
                    else
                    {
                        using var bgr = Mat.FromPixelData(pending.Height, pending.Width, MatType.CV_8UC3,
                            mapped.DataPointer, checked(pending.Width * 3));
                        bgr.CopyTo(target);
                    }
                },
                () =>
                {
                    try { context.UnmapSubresource(staging, 0); }
                    finally { if (timing?.CpuCopyStartedAtTicks is not null) timing.CpuCopyCompletedAtTicks = Stopwatch.GetTimestamp(); }
                },
                completed =>
                {
                    lock (_lock)
                    {
                        if (!PollingGenerationIsActive(generation)) throw new InvalidOperationException("Capture stopped before readback publication.");
                        CompleteSourceRetention(generation, completed.SourceInfo);
                        if (timing is not null) timing.LastStage = "cache_commit";
                        EnsureCache(completed.Width, completed.Height);
                        target!.CopyTo(_cachedBgr!);
                        _cachedFrameTs = completed.SourceInfo.SourceTimestamp100ns;
                        _cachedSourceInfo = completed.SourceInfo;
                        _cachedCaptureRect = completed.CaptureRect;
                    }
                });
            if (!complete)
            {
                lock (_lock)
                {
                    if (!PollingGenerationIsActive(generation)) return default;
                    return new(GameCaptureAttemptOutcome.ReadbackPending, pending: pending);
                }
            }
            _pendingReadbackResource = null;

            lock (_lock)
            {
                if (!PollingGenerationIsActive(generation)) return default;
                // Refill only after a previously pending copy completes; never Map the refill in this call.
                if (pendingOnEntry) RenderAndSubmitPolling(slot, timing);
                // A newly discovered resize invalidates old geometry before any old-size clone can escape.
                if (!PollingGenerationIsActive(generation) || _cachedFrameTs != pending.SourceInfo.SourceTimestamp100ns
                    || !ReferenceEquals(_cachedSourceInfo, pending.SourceInfo)) return default;
                return TransferPollingFrame(ref target, pending.CaptureRect, pending.SourceInfo, slot.Pending);
            }
        }
        catch (Exception error)
        {
            timing?.RecordFailure(error);
            if (entered && active && slot is not null && generation is not null)
            {
                lock (_lock)
                {
                    // A waiting/interrupted caller owns no publication. Fault only this admitted lifetime.
                    if (ReferenceEquals(_readbackSlot, slot) && ReferenceEquals(_generation, generation))
                    {
                        // Partial submission, failed Unmap and uncertain publication must never retry this storage.
                        FaultSourceRetention(generation);
                        slot.Fault();
                        _pendingReadbackResource = null;
                        InvalidatePublishedFrames();
                    }
                }
            }
            if (error is SharpDXException native) HandleSharpDxError(native);
            else Debug.WriteLine($"[WGC V2] Polling capture failed: {error.GetType().Name}: {error.Message}");
            return default;
        }
        finally
        {
            try
            {
                if (target is not null) ReleaseBgrMat(target);
            }
            finally
            {
                if (active)
                {
                    if (timing is not null) timing.LastStage = "cleanup";
                    lock (_lock) { _activeCaptures--; Monitor.PulseAll(_lock); }
                }
                if (entered) Monitor.Exit(_captureGate);
            }
        }
    }

    /// <summary>Check the exact active generation before accessing resources or handing out pixels.</summary>
    private bool PollingGenerationIsActive(WgcCaptureGeneration generation) =>
        IsCapturing && ReferenceEquals(_generation, generation) && generation.IsActive && !_sourceRetentionFaulted;

    /// <summary>Take native ownership from a local pooled Mat only after frame construction succeeds.</summary>
    private GameCaptureAttempt TransferPollingFrame(ref Mat? target, Vanara.PInvoke.RECT? rect,
        GameCaptureSourceInfo source, GameCapturePendingReadback? pending)
    {
        var frame = new GameCaptureFrame(WgcBgrMat.CreateFrom(target!, ReleaseBgrMat), rect, source);
        target = null;
        return new(GameCaptureAttemptOutcome.FrameReady, frame, pending);
    }

    /// <summary>Reject malformed non-busy results before touching the native pointer; successful Map still gets Unmap.</summary>
    internal static void ValidatePollingMap(DataBox mapped, int width, int height, bool cpuConvert)
    {
        if (mapped.DataPointer == IntPtr.Zero || width <= 0 || height <= 0)
            throw new InvalidOperationException("Invalid mapped readback pointer or geometry.");
        var rowBytes = checked(width * (cpuConvert ? 4 : 3));
        _ = checked(rowBytes * height);
        if (cpuConvert && mapped.RowPitch < rowBytes)
            throw new InvalidOperationException("Mapped texture row pitch is smaller than its pixels.");
    }

    /// <summary>The installed SharpDX overload returns an empty box for WasStillDrawing; all other errors throw.</summary>
    private static DataBox MapPolling(DeviceContext context, SharpDX.Direct3D11.Resource staging, GameCaptureCallTiming? timing)
    {
        if (timing is not null) { timing.LastStage = "readback_map"; timing.ReadbackMapStartedAtTicks = Stopwatch.GetTimestamp(); }
        try
        {
            var mapped = context.MapSubresource(staging, 0, MapMode.Read, SharpDX.Direct3D11.MapFlags.DoNotWait);
            if (timing is not null) timing.ReadbackMapResult = mapped.IsEmpty ? "still_drawing" : "ready";
            return mapped;
        }
        catch { if (timing is not null) timing.ReadbackMapResult = "failed"; throw; }
        finally { if (timing is not null) timing.ReadbackMapCompletedAtTicks = Stopwatch.GetTimestamp(); }
    }

    /// <summary>Run the same bounded selector/render path, then reserve and submit at most one exact staging copy.</summary>
    private void RenderAndSubmitPolling(WgcReadbackSlot slot, GameCaptureCallTiming? timing)
    {
        if (slot.Pending is not null) throw new InvalidOperationException("Cannot render over a pending staging copy.");
        var previousRecreateFailures = _recreateFailures;
        try { TryRenderNewFrameLocked(timing); }
        finally { if (timing?.RenderStartedAtTicks is not null) timing.RenderCompletedAtTicks = Stopwatch.GetTimestamp(); }
        if (_recreateFailures != previousRecreateFailures) throw new InvalidOperationException("Polling capture resize failed.");
        if (!IsCapturing || _generation?.IsActive != true || _gpuTexture is null || _gpuFrameTs == 0) return;
        if (_cachedBgr is not null && _cachedFrameTs == _gpuFrameTs) return;
        var source = _gpuSourceInfo ?? throw new InvalidOperationException("Rendered source metadata is missing.");
        var device = _gpuTexture.Device;
        var width = _gpuTexture.Description.Width;
        var height = _gpuTexture.Description.Height;
        var context = device.ImmediateContext;
        if (timing is not null) { timing.LastStage = "submit"; timing.SubmitStartedAtTicks = Stopwatch.GetTimestamp(); }
        try
        {
            _pendingReadbackCpuConvert = _useCpuConvert;
            if (_useCpuConvert)
            {
                EnsureStagingTextureLocked(device, width, height);
                _pendingReadbackResource = _stagingTexture!;
                slot.Begin(source, Stopwatch.GetTimestamp(), width, height, _captureRect);
                context.CopyResource(_gpuTexture, _stagingTexture);
            }
            else
            {
                EnsurePackResourcesLocked(device, width, height);
                var total = checked(width * height);
                // Retain WriteDiscard for the dynamic constant buffer; DoNotWait is only for readback.
                var constants = context.MapSubresource(_packCb, 0, MapMode.WriteDiscard, SharpDX.Direct3D11.MapFlags.None);
                try
                {
                    Marshal.WriteInt32(constants.DataPointer, 0, width);
                    Marshal.WriteInt32(constants.DataPointer, 4, height);
                    Marshal.WriteInt32(constants.DataPointer, 8, total);
                }
                finally { context.UnmapSubresource(_packCb, 0); }
                using var srv = new ShaderResourceView(device, _gpuTexture);
                var pixelGroups = checked((total + 3) / 4);
                var groups = (pixelGroups + 63) / 64;
                context.ComputeShader.Set(_packCs);
                context.ComputeShader.SetShaderResource(0, srv);
                context.ComputeShader.SetUnorderedAccessView(0, _packUav);
                context.ComputeShader.SetConstantBuffer(0, _packCb);
                try { context.Dispatch(groups, 1, 1); }
                finally
                {
                    context.ComputeShader.SetShaderResource(0, null);
                    context.ComputeShader.SetUnorderedAccessView(0, null);
                    context.ComputeShader.Set(null);
                }
                _pendingReadbackResource = _packStagingBuf!;
                if (checked(total * 3) > _packStagingBuf!.Description.SizeInBytes)
                    throw new InvalidOperationException("Packed staging storage is too small.");
                slot.Begin(source, Stopwatch.GetTimestamp(), width, height, _captureRect);
                context.CopyResource(_packGpuBuf, _packStagingBuf);
            }
        }
        finally { if (timing is not null) timing.SubmitCompletedAtTicks = Stopwatch.GetTimestamp(); }
        // One submission-only Flush guarantees queued work is sent before the caller sleeps; it is not a fence.
        if (timing is not null) { timing.LastStage = "flush"; timing.FlushStartedAtTicks = Stopwatch.GetTimestamp(); }
        try { context.Flush(); }
        finally { if (timing is not null) timing.FlushCompletedAtTicks = Stopwatch.GetTimestamp(); }
    }
}
