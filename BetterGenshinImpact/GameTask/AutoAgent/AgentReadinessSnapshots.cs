using BetterGenshinImpact.Core.Agent;
using BetterGenshinImpact.Core.Script.Dependence;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;
using OpenCvSharp;
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask.AutoAgent;

/// <summary>Opt-in bounded native-image evidence; capture never waits for encoding or filesystem work.</summary>
internal sealed class AgentReadinessSnapshots
{
    /// <summary>Lifetime quotas cannot be reset by toggling recording off and on.</summary>
    internal const int MaximumFrames = 32;
    /// <summary>Limit total admitted PNG and metadata bytes for one stream session.</summary>
    internal const long MaximumBytes = 128 * 1024 * 1024;
    /// <summary>At most two native snapshots may be owned by background work.</summary>
    internal const int MaximumPending = 2;
    /// <summary>Reject larger-than-4K sources rather than allocating unbounded diagnostic buffers.</summary>
    internal const long MaximumSourcePixels = 3840L * 2160;
    /// <summary>Protect small metadata and quota operations; encoding and IO never hold this lock.</summary>
    private readonly object _sync = new();
    /// <summary>Clones only admitted images and disposes them after the background callback completes.</summary>
    private readonly CaptureWriteQueue _queue = new(MaximumPending);
    /// <summary>At most one completion task per lifetime-admitted frame is retained.</summary>
    private readonly List<Task> _writes = [];
    /// <summary>Destination is supplied by the server, never a wire request.</summary>
    private readonly string _directory;
    /// <summary>Allow small deterministic quota and encoder fixtures without changing production defaults.</summary>
    private readonly int _maximumFrames;
    /// <summary>Lifetime encoded-byte budget, including metadata.</summary>
    private readonly long _maximumBytes;
    /// <summary>Default encoding runs in the queue worker; tests can hold or fail that same boundary.</summary>
    private readonly Func<Mat, byte[]> _encode;
    /// <summary>Explicit recording state; false until an authenticated client opts in.</summary>
    private bool _enabled;
    /// <summary>Do not record repeated freshness/focus changes when the visual evidence is unchanged.</summary>
    private AgentWorldEvidence? _lastEvidence;
    /// <summary>Admission includes failed and dropped-after-encoding writes so quotas remain finite.</summary>
    private int _admitted;
    /// <summary>Completed image-and-metadata pairs.</summary>
    private int _written;
    /// <summary>Nonblocking capacity or quota refusals.</summary>
    private int _dropped;
    /// <summary>Observed cloning, encoding or write failures.</summary>
    private int _failed;
    /// <summary>Number of admitted writers not yet completely finished.</summary>
    private int _pending;
    /// <summary>Reserved byte budget is never reused after a partial write failure.</summary>
    private long _reservedBytes;
    /// <summary>Bytes in complete persisted pairs, excluding any incomplete temporary files.</summary>
    private long _bytesWritten;
    /// <summary>Stop further allocation after the frame or encoded-byte quota is exhausted.</summary>
    private bool _limitReached;
    /// <summary>Compact diagnostic failure text; failures never escape into the control loop.</summary>
    private string? _lastError;

    /// <summary>Create an inactive recorder without touching the filesystem.</summary>
    internal AgentReadinessSnapshots(string directory, int maximumFrames = MaximumFrames,
        long maximumBytes = MaximumBytes, Func<Mat, byte[]>? encode = null)
    {
        if (maximumFrames is < 1 or > MaximumFrames) throw new ArgumentOutOfRangeException(nameof(maximumFrames));
        if (maximumBytes is < 1 or > MaximumBytes) throw new ArgumentOutOfRangeException(nameof(maximumBytes));
        _directory = Path.GetFullPath(directory);
        _maximumFrames = maximumFrames;
        _maximumBytes = maximumBytes;
        _encode = encode ?? (static image => image.ImEncode(".png"));
    }

    /// <summary>Start with the next image as a baseline; already-admitted writes finish when disabled.</summary>
    internal void Configure(bool enabled)
    {
        lock (_sync)
        {
            if (_enabled != enabled) _lastEvidence = null;
            _enabled = enabled;
        }
    }

    /// <summary>Record the first image and each visual-evidence transition using an owned, exact source clone.</summary>
    internal void Observe(Mat source, AgentObservation observation, AgentWorldReadiness readiness)
    {
        lock (_sync)
        {
            if (!_enabled || _lastEvidence == observation.WorldEvidence) return;
            _lastEvidence = observation.WorldEvidence;
            if (_limitReached || _admitted >= _maximumFrames || _pending >= MaximumPending ||
                source.Empty() || source.Type() != MatType.CV_8UC3 && source.Type() != MatType.CV_8UC4 ||
                (long)source.Width * source.Height > MaximumSourcePixels)
            {
                _dropped++;
                if (_admitted >= _maximumFrames) _limitReached = true;
                return;
            }
            var sequence = ++_admitted;
            _pending++;
            try
            {
                // This is the only synchronous work: a bounded source clone before the capture is disposed.
                var work = _queue.TryWriteAsync(source, owned => Save(owned, observation, readiness, sequence));
                _writes.Add(ObserveCompletionAsync(work));
            }
            catch (Exception error)
            {
                _pending--;
                _failed++;
                _lastError = error.GetType().Name;
            }
        }
    }

    /// <summary>Return an immutable copy of counters and limits without waiting for a writer.</summary>
    internal object Snapshot()
    {
        lock (_sync) return new
        {
            enabled = _enabled, directory = _directory, admitted = _admitted, written = _written,
            dropped = _dropped, failed = _failed, pending = _pending, bytesWritten = _bytesWritten,
            limitReached = _limitReached, lastError = _lastError,
            limits = new { frames = _maximumFrames, bytes = _maximumBytes, pending = MaximumPending,
                sourcePixels = MaximumSourcePixels }
        };
    }

    /// <summary>Allow a short shutdown flush after input is released; workers retain ownership if IO outlasts it.</summary>
    internal async Task CompleteAsync(TimeSpan timeout)
    {
        Task[] pending;
        lock (_sync) { _enabled = false; pending = _writes.ToArray(); }
        try { await Task.WhenAll(pending).WaitAsync(timeout).ConfigureAwait(false); }
        catch (TimeoutException) { lock (_sync) _lastError = "flush_timeout"; }
    }

    /// <summary>Observe every task failure and count completion only after the queue disposes its owned image.</summary>
    private async Task ObserveCompletionAsync(Task<bool> work)
    {
        try
        {
            var written = await work.ConfigureAwait(false);
            lock (_sync) { if (written) _written++; else _dropped++; }
        }
        catch (Exception error)
        {
            lock (_sync) { _failed++; _lastError = error.GetType().Name; }
        }
        finally { lock (_sync) _pending--; }
    }

    /// <summary>Encode and persist an image with source timing and readiness metadata entirely off capture.</summary>
    private bool Save(Mat image, AgentObservation observation, AgentWorldReadiness readiness, int sequence)
    {
        var png = _encode(image);
        var metadata = Encoding.UTF8.GetBytes(JsonConvert.SerializeObject(new
        {
            version = 1, observation.FrameId, observation.CapturedAtMs, observation.SourceWidth, observation.SourceHeight,
            observation.SourceFrame,
            sourceTimestampKind = observation.SourceFrame is null ? "unknown" : "wgc_compositor_qpc",
            evidence = observation.WorldEvidence.ToString(), observation.RecognitionMs, worldReadiness = readiness,
            imageSha256 = Convert.ToHexString(SHA256.HashData(png)).ToLowerInvariant(),
            recognition = new { maxWidth = AgentWorldRecognizer.MaxWidth, maxHeight = AgentWorldRecognizer.MaxHeight,
                modalStarConfirmation = "native_template", nativeMaxWidth = AgentWorldRecognizer.NativeModalMaxWidth,
                nativeMaxHeight = AgentWorldRecognizer.NativeModalMaxHeight }
        }, new JsonSerializerSettings { ContractResolver = new CamelCasePropertyNamesContractResolver(), Formatting = Formatting.Indented }));
        var bytes = (long)png.Length + metadata.Length;
        lock (_sync)
        {
            if (bytes > _maximumBytes - _reservedBytes)
            {
                _limitReached = true;
                _lastError = "byte_limit";
                return false;
            }
            _reservedBytes += bytes;
        }
        Directory.CreateDirectory(_directory);
        var name = $"{sequence:D2}-frame-{observation.FrameId:D12}";
        var imagePath = Path.Combine(_directory, name + ".png");
        WriteNewAtomic(imagePath, png);
        try { WriteNewAtomic(Path.Combine(_directory, name + ".json"), metadata); }
        catch { File.Delete(imagePath); throw; }
        lock (_sync) _bytesWritten += bytes;
        return true;
    }

    /// <summary>Publish complete files without overwriting an existing artifact; clean only our temporary path.</summary>
    private static void WriteNewAtomic(string path, byte[] bytes)
    {
        var temporary = path + ".writing";
        var created = false;
        try
        {
            using (var file = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                created = true;
                file.Write(bytes);
            }
            File.Move(temporary, path);
        }
        finally { if (created && File.Exists(temporary)) File.Delete(temporary); }
    }
}
