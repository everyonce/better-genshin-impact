using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using BetterGenshinImpact.Core.Agent;
using Fischless.GameCapture;
using OpenCvSharp;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>Bounded passive copies from one native producer; only its worker resizes, hashes, or writes files.</summary>
internal sealed class NavigationBaselineShadowCapture : IAsyncDisposable
{
    /// <summary>Independent shadow limits never increase native capture, observation, journal, or owner budgets.</summary>
    internal const int MaximumFrames = 1024, RawBankCount = 2, MaximumBufferSlots = 8, MaximumManifestBytes = 8 * 1024 * 1024;
    /// <summary>Two worst-case packed BGRA buffers are reserved before the first baseline input.</summary>
    internal const int MaximumRawBytes = 3840 * 2160 * 4;
    /// <summary>One absolute post-input drain bound; a timed-out worker retains the process reservation until retirement.</summary>
    internal static readonly TimeSpan RetirementTimeout = TimeSpan.FromSeconds(2);
    /// <summary>Never accumulate writers/raw buffers after an unresolved filesystem stall.</summary>
    private static readonly SemaphoreSlim WorkerSlot = new(1, 1);
    /// <summary>Protect admission/close only; no worker IO or transform occurs while holding this gate.</summary>
    private readonly object _gate = new();
    /// <summary>Fixed buffers move exclusively between free, queued, and worker-owned states.</summary>
    private readonly Queue<Memory<byte>> _free = new(MaximumBufferSlots);
    /// <summary>The same two fixed banks are reserved before input; geometry only partitions their existing bytes.</summary>
    private readonly byte[][] _rawBanks = new byte[RawBankCount][];
    /// <summary>At most eight disjoint raw slots including the active resizer; the writer's RGB output is separately owned.</summary>
    private readonly Queue<(NavigationBaselineShadowFrame Frame, Memory<byte> Pixels)> _pending = new(MaximumBufferSlots);
    /// <summary>Wake the sole worker after publication or final close.</summary>
    private readonly SemaphoreSlim _wake = new(0);
    /// <summary>Only a retirement timeout cancels file IO; ordinary native cancellation still permits bounded evidence drain.</summary>
    private readonly CancellationTokenSource _ioStop = new();
    /// <summary>Storage initialization completes before native PrepareAsync can finish.</summary>
    private readonly TaskCompletionSource _ready = new(TaskCreationOptions.RunContinuationsAsynchronously);
    /// <summary>The only worker owns all archive persistence and releases its global reservation in finally.</summary>
    private readonly Task _worker;
    /// <summary>Native owner-selected identities and server-derived output directory; no caller-supplied filenames.</summary>
    private readonly string _directory, _runId, _readbackMode;
    /// <summary>Pin the native owner and game/session in the archive, without opening another runtime.</summary>
    private readonly int _gameProcessId, _windowsSessionId;
    /// <summary>Worker-only asynchronous test seam; null in production, never invoked by the capture hook.</summary>
    private readonly Func<CancellationToken, Task>? _beforeWrite;
    /// <summary>Worker-only test seam after raw return; permits deterministic IO stalls without blocking capture.</summary>
    private readonly Func<CancellationToken, Task>? _afterResizeBeforeWrite;
    /// <summary>Fresh returned-image high-water is shadow-only and never updates native accepted sources or barriers.</summary>
    private GameCaptureSourceInfo? _lastSource;
    /// <summary>Fixed geometry/format after the first admitted copy.</summary>
    private int _width, _height, _channels;
    /// <summary>Bounded geometry-specific capacity and scalar pressure diagnostics, always accessed under the gate.</summary>
    private int _rawSlots, _rawSlotsInUse, _rawSlotsHighWater, _pendingHighWater;
    /// <summary>Worker-only completed-phase timings; these include scheduling delay and do not claim CPU or durable IO time.</summary>
    private double _resizeTotalMs, _resizeMaxMs, _writeTotalMs, _writeMaxMs;
    /// <summary>Bounded first failure and counters remain available even when final manifest publication fails.</summary>
    private string? _error, _manifestPath, _manifestHash, _journalPath, _journalHash;
    /// <summary>Stop admission independently of final close so a failed shadow cannot stop native control.</summary>
    private bool _accepting = true, _finishing, _retired;
    /// <summary>Exact offered/retained/written counts, with deduplicated immutable source tuples.</summary>
    private int _seen, _accepted, _written, _duplicates, _rejected, _ignored;
    /// <summary>First final close establishes one absolute cleanup deadline, shared by subsequent Dispose calls.</summary>
    private long _closeStarted;

    /// <summary>Reserve memory/worker once before native control; reject a still-unretired prior shadow.</summary>
    internal NavigationBaselineShadowCapture(string directory, string runId, int gameProcessId, int windowsSessionId,
        string readbackMode, Func<CancellationToken, Task>? beforeWrite = null,
        Func<CancellationToken, Task>? afterResizeBeforeWrite = null)
    {
        if (!Guid.TryParseExact(runId, "N", out var id) || id == Guid.Empty) throw new ArgumentException("invalid_shadow_run_id");
        if (readbackMode is not ("blocking" or "poll_single_v1")) throw new ArgumentException("shadow_readback_mode_required");
        if (gameProcessId <= 0 || windowsSessionId <= 0) throw new ArgumentException("shadow_owner_identity_required");
        if (!WorkerSlot.Wait(0)) throw new InvalidOperationException("shadow_previous_worker_not_retired");
        _directory = directory; _runId = runId; _gameProcessId = gameProcessId; _windowsSessionId = windowsSessionId;
        _readbackMode = readbackMode; _beforeWrite = beforeWrite; _afterResizeBeforeWrite = afterResizeBeforeWrite;
        try
        {
            for (var i = 0; i < RawBankCount; i++) _rawBanks[i] = GC.AllocateUninitializedArray<byte>(MaximumRawBytes);
            _worker = Task.Run(WorkAsync);
        }
        catch { _ioStop.Dispose(); _wake.Dispose(); WorkerSlot.Release(); throw; }
    }

    /// <summary>Fail opt-in storage admission before movement; no input is owned by this session.</summary>
    internal async Task InitializeAsync(CancellationToken ct)
    {
        try { await _ready.Task.WaitAsync(RetirementTimeout, ct).ConfigureAwait(false); }
        catch (Exception error) { Fail("shadow_initialization_failed:" + error.GetType().Name); throw; }
    }

    /// <summary>Copy only already validated native Ready pixels; no IO/resize/hash/wait/native-state mutation here.</summary>
    internal unsafe void Offer(Mat pixels, GameCaptureSourceInfo source, int pollIndex, NavigationBaselineCapturePoll poll)
    {
        lock (_gate)
        {
            // Final close fixes producer counts; a late caller cannot rewrite completed evidence.
            if (_finishing || _retired) return;
            _seen++;
            if (!_accepting) { _ignored++; return; }
            try
            {
                if (source.CaptureEpoch == Guid.Empty || source.SourceTimestamp100ns <= 0 || source.AcquiredAtStopwatchTicks <= 0)
                    throw new InvalidOperationException("shadow_source_metadata_invalid");
                if (_lastSource == source) { _duplicates++; return; }
                if (_lastSource is { } last && (source.CaptureEpoch != last.CaptureEpoch
                    || source.SourceTimestamp100ns <= last.SourceTimestamp100ns
                    || source.AcquiredAtStopwatchTicks <= last.AcquiredAtStopwatchTicks))
                    throw new InvalidOperationException("shadow_source_regression");
                var width = pixels.Width; var height = pixels.Height; var channels = pixels.Channels();
                if (width is < 1 or > 3840 || height is < 1 or > 2160 || channels is not (3 or 4)
                    || pixels.Type() != (channels == 3 ? MatType.CV_8UC3 : MatType.CV_8UC4))
                    throw new InvalidOperationException("shadow_geometry_unsupported");
                if (_width != 0 && (_width != width || _height != height || _channels != channels))
                    throw new InvalidOperationException("shadow_geometry_changed");
                if (pollIndex < 0 || pollIndex >= NativeNavigationBaselineOperations.MaximumCapturePolls
                    || poll.Source?.WgcSource != source || poll.CaptureReturnedAtMs is null || poll.SourceAgeMs is null
                    || !double.IsFinite(poll.SourceAgeMs.Value) || poll.SourceAgeMs.Value is < 0 or > 150
                    || poll.Result is not ("admitted" or "duplicate" or "response_barrier" or "duplicate_and_response_barrier"))
                    throw new InvalidOperationException("shadow_capture_join_invalid");
                if (_accepted >= MaximumFrames) throw new InvalidOperationException("shadow_frame_capacity_exceeded");
                var stride = checked(width * channels);
                var sourceStride = pixels.Step();
                var sourceBytes = checked(sourceStride * (height - 1) + stride);
                if (sourceStride < stride || sourceBytes > int.MaxValue || pixels.Data == IntPtr.Zero)
                    throw new InvalidOperationException("shadow_stride_invalid");
                // Binding creates only value-type views in pre-sized queues, never more raw storage on the capture path.
                if (_rawSlots == 0) BindRawSlots(checked(stride * height));
                if (_free.Count == 0) throw new InvalidOperationException("shadow_buffer_exhausted");
                var buffer = _free.Dequeue();
                _rawSlotsInUse++;
                _rawSlotsHighWater = Math.Max(_rawSlotsHighWater, _rawSlotsInUse);
                try
                {
                    var started = Stopwatch.GetTimestamp();
                    var borrowed = new ReadOnlySpan<byte>((void*)pixels.Data, (int)sourceBytes);
                    for (var row = 0; row < height; row++)
                        borrowed.Slice(checked((int)(row * sourceStride)), stride).CopyTo(buffer.Span.Slice(row * stride, stride));
                    var frame = new NavigationBaselineShadowFrame(_accepted, pollIndex, poll.ObservationIndex, source,
                        width, height, channels, stride, poll.CaptureStartedAtMs, poll.CaptureReturnedAtMs.Value,
                        poll.SourceAgeMs.Value, poll.Result, started, Stopwatch.GetTimestamp());
                    _pending.Enqueue((frame, buffer));
                    _pendingHighWater = Math.Max(_pendingHighWater, _pending.Count);
                    _width = width; _height = height; _channels = channels; _lastSource = source; _accepted++;
                    _wake.Release();
                }
                catch { ReturnRaw(buffer); throw; }
            }
            catch (Exception error) { _rejected++; FailLocked(error.GetBaseException().Message); }
        }
    }

    /// <summary>Partition each bank into at most four equal, nonoverlapping views after geometry validation.</summary>
    private void BindRawSlots(int frameBytes)
    {
        var slotsPerBank = Math.Min(MaximumBufferSlots / RawBankCount, MaximumRawBytes / frameBytes);
        if (slotsPerBank < 1) throw new InvalidOperationException("shadow_geometry_unsupported");
        foreach (var bank in _rawBanks)
            for (var slot = 0; slot < slotsPerBank; slot++)
                _free.Enqueue(bank.AsMemory(checked(slot * frameBytes), frameBytes));
        _rawSlots = slotsPerBank * RawBankCount;
    }

    /// <summary>Return an exclusively owned raw view once; only the worker-owned RGB copy survives a successful resize.</summary>
    private void ReturnRaw(Memory<byte> pixels)
    {
        lock (_gate) { _free.Enqueue(pixels); _rawSlotsInUse--; }
    }

    /// <summary>Scalar owned-pool snapshot for deterministic validation; no buffer reference escapes.</summary>
    internal (int Capacity, int InUse, int Free, int ReservedBytes) BufferStateForValidation()
    {
        lock (_gate)
        {
            var bytes = 0;
            foreach (var bank in _rawBanks) bytes += bank?.Length ?? 0;
            return (_rawSlots, _rawSlotsInUse, _free.Count, bytes);
        }
    }

    /// <summary>Record one bounded error without throwing into the native controller.</summary>
    private void Fail(string message) { lock (_gate) FailLocked(message); }
    /// <summary>Only admission is disabled here; the worker still waits for the final native journal association.</summary>
    private void FailLocked(string message)
    {
        _error ??= message.Length <= 256 ? message : message[..256];
        _accepting = false;
    }

    /// <summary>Close producer admission after native input closure, then await the single worker within one fixed drain budget.</summary>
    internal async Task<NavigationBaselineShadowEvidence> CompleteAsync(string? journalPath, string? journalHash)
    {
        lock (_gate)
        {
            if (!_finishing)
            {
                _accepting = false; _finishing = true; _closeStarted = Stopwatch.GetTimestamp();
                _journalPath = journalPath; _journalHash = journalHash;
                if (journalPath is null || journalHash is null) FailLocked("shadow_native_journal_unavailable");
                if (!_retired) _wake.Release();
            }
        }
        var remaining = RetirementTimeout - Stopwatch.GetElapsedTime(_closeStarted);
        try
        {
            if (!_worker.IsCompleted && remaining > TimeSpan.Zero) await _worker.WaitAsync(remaining).ConfigureAwait(false);
            if (!_worker.IsCompleted) throw new TimeoutException();
            await _worker.ConfigureAwait(false);
        }
        catch (TimeoutException)
        {
            Fail("shadow_worker_retirement_timeout");
            // Cancellation is cooperative. Keep the global slot and raw owners with the actual worker until it retires.
            try { _ioStop.Cancel(); }
            catch (ObjectDisposedException) { /* The actual worker completed its finally during timeout handling. */ }
        }
        catch (Exception error) { Fail("shadow_worker_failed:" + error.GetType().Name); }
        return Snapshot();
    }

    /// <summary>Positive retirement is required; queued/worker-owned buffers are never freed by a timed-out caller.</summary>
    internal NavigationBaselineShadowEvidence Snapshot()
    {
        lock (_gate)
        {
            var retired = _retired && _worker.IsCompleted;
            return new(NavigationBaselineShadowMode.Rgb192,
                retired && _error is null && _written > 0 && _written == _accepted && _manifestHash is not null,
                retired, _error, _seen, _accepted, _written, _duplicates, _rejected, _ignored, _accepted - _written + _rejected,
                _manifestPath, _manifestHash, _journalHash);
        }
    }

    /// <summary>Lossless packed RGB192 and bounded metadata are written only on this worker, never on the capture producer.</summary>
    private async Task WorkAsync()
    {
        var rows = new List<object>(MaximumFrames);
        try
        {
            if (Directory.Exists(_directory)) throw new IOException("shadow_directory_exists");
            Directory.CreateDirectory(_directory);
            await WriteAsync("reservation.json", JsonSerializer.SerializeToUtf8Bytes(new { runId = _runId }), _ioStop.Token).ConfigureAwait(false);
            _ready.TrySetResult();
            AgentHamming192Plan? plan = null;
            var rgb = new byte[AgentHamming192Plan.OutputBytes];
            while (true)
            {
                (NavigationBaselineShadowFrame Frame, Memory<byte> Pixels)? next = null;
                lock (_gate)
                {
                    if (_pending.Count > 0) next = _pending.Dequeue();
                    else if (_finishing) break;
                }
                if (next is null) { await _wake.WaitAsync(_ioStop.Token).ConfigureAwait(false); continue; }
                var (frame, pixels) = next.Value;
                var workerDequeuedAtTicks = Stopwatch.GetTimestamp();
                var rawReturned = false;
                try
                {
                    if (_beforeWrite is not null) await _beforeWrite(_ioStop.Token).ConfigureAwait(false);
                    var resizeStartedAtTicks = Stopwatch.GetTimestamp();
                    plan ??= new(frame.Width, frame.Height);
                    plan.ResizeInto(pixels.Span, frame.PackedStride, frame.Channels, true, rgb);
                    var resizeCompletedAtTicks = Stopwatch.GetTimestamp();
                    var resizeMs = Stopwatch.GetElapsedTime(resizeStartedAtTicks, resizeCompletedAtTicks).TotalMilliseconds;
                    _resizeTotalMs += resizeMs; _resizeMaxMs = Math.Max(_resizeMaxMs, resizeMs);
                    // RGB is a separate sole-worker buffer. IO, hashing and metadata must not retain a scarce raw slot.
                    ReturnRaw(pixels); rawReturned = true;
                    var rawReturnedAtTicks = Stopwatch.GetTimestamp();
                    var name = $"{frame.FrameIndex:D4}.rgb";
                    var writeStartedAtTicks = Stopwatch.GetTimestamp();
                    if (_afterResizeBeforeWrite is not null) await _afterResizeBeforeWrite(_ioStop.Token).ConfigureAwait(false);
                    await WriteAsync(name, rgb, _ioStop.Token).ConfigureAwait(false);
                    var writeCompletedAtTicks = Stopwatch.GetTimestamp();
                    var writeMs = Stopwatch.GetElapsedTime(writeStartedAtTicks, writeCompletedAtTicks).TotalMilliseconds;
                    _writeTotalMs += writeMs; _writeMaxMs = Math.Max(_writeMaxMs, writeMs);
                    var digest = Convert.ToHexString(SHA256.HashData(rgb));
                    rows.Add(new { frame, file = name, bytes = rgb.Length, sha256 = digest, pixelFormat = "rgb24", width = 192, height = 192,
                        poseAdmission = "not_evaluated_at_copy", inputAuthority = false,
                        processing = new { workerDequeuedAtTicks, resizeStartedAtTicks, resizeCompletedAtTicks,
                            rawReturnedAtTicks, writeStartedAtTicks, writeCompletedAtTicks,
                            queueWaitMs = Stopwatch.GetElapsedTime(frame.CopyCompletedAtTicks, workerDequeuedAtTicks).TotalMilliseconds,
                            resizeMs, writeMs } });
                    lock (_gate) _written++;
                }
                finally { if (!rawReturned) ReturnRaw(pixels); }
            }
            if (_journalPath is not null && _journalHash is not null)
            {
                var file = new FileInfo(_journalPath);
                if (file.Length > NativeNavigationBaselineOperations.MaximumJournalBytes) throw new IOException("shadow_native_journal_oversized");
                var bytes = await File.ReadAllBytesAsync(_journalPath, _ioStop.Token).ConfigureAwait(false);
                if (!string.Equals(Convert.ToHexString(SHA256.HashData(bytes)), _journalHash, StringComparison.OrdinalIgnoreCase))
                    throw new IOException("shadow_native_journal_hash_mismatch");
                using var doc = JsonDocument.Parse(bytes);
                if (doc.RootElement.GetProperty("runId").GetString() != _runId) throw new IOException("shadow_native_journal_run_mismatch");
            }
            if (_written == 0) Fail("shadow_no_images");
            var manifest = JsonSerializer.SerializeToUtf8Bytes(new
            {
                schemaVersion = 1, mode = NavigationBaselineShadowMode.Rgb192, runId = _runId,
                gameProcessId = _gameProcessId, windowsSessionId = _windowsSessionId, readbackMode = _readbackMode,
                qpcFrequency = Stopwatch.Frequency, preprocessing = AgentObservationProfile.P2PNativeHamming192,
                evidenceKind = "native-owned-source-pixels", fixedRate = false, trainingEligible = false,
                completeLowLevelDispatchTrace = false, inputAuthority = false, nativeJournalPath = _journalPath,
                nativeJournalSha256 = _journalHash, framesSeen = _seen, framesAccepted = _accepted, framesWritten = _written,
                duplicateFrames = _duplicates, framesRejected = _rejected, offersIgnoredAfterStop = _ignored,
                framesLost = _accepted - _written + _rejected, error = _error,
                complete = _error is null && _written == _accepted && _written > 0,
                maximumFrames = MaximumFrames, maximumRawBuffers = MaximumBufferSlots,
                rawBufferSlots = _rawSlots, rawBankCount = RawBankCount, maximumRawBytes = RawBankCount * MaximumRawBytes,
                rawSlotsHighWater = _rawSlotsHighWater, pendingHighWater = _pendingHighWater, rawSlotsInUse = _rawSlotsInUse,
                workerResizeTotalMs = _resizeTotalMs, workerResizeMaxMs = _resizeMaxMs,
                workerWriteTotalMs = _writeTotalMs, workerWriteMaxMs = _writeMaxMs,
                workerTimingKind = "qpc-wall-including-scheduling", frames = rows
            }, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
            if (manifest.Length > MaximumManifestBytes) throw new IOException("shadow_manifest_capacity_exceeded");
            await WriteAsync("manifest.json", manifest, _ioStop.Token).ConfigureAwait(false);
            lock (_gate) { _manifestPath = Path.Combine(_directory, "manifest.json"); _manifestHash = Convert.ToHexString(SHA256.HashData(manifest)); }
        }
        catch (Exception error)
        {
            Fail("shadow_writer_failed:" + error.GetType().Name + ":" + error.GetBaseException().Message);
            _ = FailReadiness(_ready, error);
        }
        finally
        {
            lock (_gate)
            {
                _accepting = false;
                while (_pending.Count > 0) ReturnRaw(_pending.Dequeue().Pixels);
                _free.Clear(); Array.Clear(_rawBanks); _retired = true;
            }
            _ioStop.Dispose(); _wake.Dispose();
            WorkerSlot.Release();
        }
    }

    /// <summary>Observe private readiness faults even after its timeout/cancelled waiter leaves; awaiting still throws the original failure.</summary>
    internal static AggregateException? FailReadiness(TaskCompletionSource ready, Exception error) =>
        ready.TrySetException(error) ? ready.Task.Exception : null;

    /// <summary>Exclusive lossless writes never overwrite an existing archive; no durable-flush or physical-storage claim.</summary>
    private async Task WriteAsync(string name, ReadOnlyMemory<byte> bytes, CancellationToken ct)
    {
        await using var stream = new FileStream(Path.Combine(_directory, name), FileMode.CreateNew, FileAccess.Write,
            FileShare.Read, 4096, FileOptions.Asynchronous);
        await stream.WriteAsync(bytes, ct).ConfigureAwait(false);
        await stream.FlushAsync(ct).ConfigureAwait(false);
    }

    /// <summary>Abort without a journal only when normal publication never occurred; never release native input here.</summary>
    public async ValueTask DisposeAsync() { await CompleteAsync(null, null).ConfigureAwait(false); }
}
