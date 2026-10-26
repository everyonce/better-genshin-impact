using System.Diagnostics;
using System.Runtime.ExceptionServices;
using OpenCvSharp;

namespace Fischless.GameCapture.DesktopDc;

/// <summary>Synchronous desktop-client capture with one serialized transaction and no GDI resources retained between calls.</summary>
public sealed class DesktopDcCapture : IGameCapture, IDesktopDcCaptureDiagnostics
{
    /// <summary>Serializes Start/Capture/Stop; input release must never depend on this gate.</summary>
    private readonly object _gate = new();
    /// <summary>Read-only target and native ownership seams support deterministic lifecycle tests.</summary>
    private readonly Func<nint, DesktopDcTargetSnapshot> _readTarget;
    /// <summary>Stateless native functions; every Capture creates a fresh thread-owned resource owner.</summary>
    private readonly IDesktopDcGdi _gdi;
    /// <summary>Clone the flushed DIB into plain independently owned pixels, disposing its borrowed header first.</summary>
    private readonly Func<DesktopDcGdiOwner, Mat> _clonePixels;
    /// <summary>Host interval clock and its immutable scale; no source/render timestamp is fabricated.</summary>
    private readonly Func<long> _timestamp;
    /// <summary>Frequency for the two host endpoints.</summary>
    private readonly long _frequency;
    /// <summary>Enter a caller-local PMv2 scope and restore it before publication; no process configuration changes.</summary>
    private readonly Func<IDisposable> _enterDpiScope;
    /// <summary>Small scalar diagnostics use a separate clock so authoritative host endpoints retain their exact reads.</summary>
    private readonly Func<long> _diagnosticTimestamp;
    /// <summary>Scale of the diagnostic clock; never substituted for host-snapshot frequency.</summary>
    private readonly long _diagnosticFrequency;
    /// <summary>At most one complete successful timing record, selected by exact snapshot object identity.</summary>
    private DesktopDcCaptureTiming? _lastTiming;
    /// <summary>Immutable target/geometry snapshot admitted by the current Start.</summary>
    private DesktopDcTargetSnapshot? _target;
    /// <summary>Generation and strictly increasing successful snapshot identities.</summary>
    private Guid _epoch;
    /// <summary>Last published host snapshot identity and cleanup-complete clock.</summary>
    private long _snapshotId, _lastCompleted;
    /// <summary>Managed status is read without waiting for a capture or native cleanup.</summary>
    private volatile bool _capturing;
    /// <summary>Object disposal is permanent; ordinary Stop only retires this generation.</summary>
    private bool _disposed;
    /// <summary>Reject reentrant capture/start while a call owns native resources.</summary>
    private bool _captureActive;
    /// <summary>Cleanup uncertainty is sticky across Stop/Start and cannot be silently retried.</summary>
    private Exception? _terminalCleanupFailure;

    /// <summary>Create the ordinary backend without opening a target, DC, bitmap or native session.</summary>
    public DesktopDcCapture() : this(DesktopDcTarget.Read, DesktopDcGdi.Instance, ClonePixels,
        Stopwatch.GetTimestamp, Stopwatch.Frequency)
    {
    }

    /// <summary>Use the actual transaction/ownership implementation with fake native functions and controlled pixels in tests.</summary>
    internal DesktopDcCapture(Func<nint, DesktopDcTargetSnapshot> readTarget, IDesktopDcGdi gdi,
        Func<DesktopDcGdiOwner, Mat> clonePixels, Func<long> timestamp, long frequency,
        Func<IDisposable>? enterDpiScope = null, Func<long>? diagnosticTimestamp = null,
        long diagnosticFrequency = 0)
    {
        ArgumentNullException.ThrowIfNull(readTarget);
        ArgumentNullException.ThrowIfNull(gdi);
        ArgumentNullException.ThrowIfNull(clonePixels);
        ArgumentNullException.ThrowIfNull(timestamp);
        if (frequency <= 0) throw new ArgumentOutOfRangeException(nameof(frequency));
        _readTarget = readTarget;
        _gdi = gdi;
        _clonePixels = clonePixels;
        _timestamp = timestamp;
        _frequency = frequency;
        _enterDpiScope = enterDpiScope ?? DesktopDcThreadDpiScope.Enter;
        _diagnosticTimestamp = diagnosticTimestamp ?? Stopwatch.GetTimestamp;
        _diagnosticFrequency = diagnosticFrequency == 0 ? Stopwatch.Frequency : diagnosticFrequency;
    }

    /// <summary>Managed lifecycle metadata only; it grants no capture freshness or input authority.</summary>
    public bool IsCapturing => _capturing;

    /// <inheritdoc />
    public DesktopDcCaptureTiming? GetTiming(GameCaptureHostSnapshotInfo snapshot)
    {
        var timing = Volatile.Read(ref _lastTiming);
        return timing is not null && timing.IsFor(snapshot) ? timing : null;
    }

    /// <summary>Pin a valid already-foreground target; settings are deliberately inert for this backend.</summary>
    public void Start(nint hWnd, Dictionary<string, object>? settings = null)
    {
        lock (_gate)
        {
            Volatile.Write(ref _lastTiming, null);
            CheckAvailable();
            if (_capturing || _captureActive) throw new InvalidOperationException("Stop the current desktop capture before starting another generation.");
            try
            {
                DesktopDcTargetSnapshot? target = null;
                IDisposable? dpiScope = null;
                Exception? failure = null;
                try
                {
                    dpiScope = _enterDpiScope() ?? throw new InvalidOperationException("Desktop DPI scope was not created.");
                    target = _readTarget(hWnd);
                    target.Validate(hWnd);
                }
                catch (Exception error) { failure = error; }
                finally { RestoreDpi(dpiScope, ref failure); }
                if (failure is not null) ExceptionDispatchInfo.Capture(failure).Throw();
                // No generation is visible until the caller's original DPI context is restored.
                _target = target;
                _epoch = Guid.NewGuid();
                _snapshotId = _lastCompleted = 0;
                _capturing = true;
            }
            catch (Exception error)
            {
                QuarantineCleanup(error);
                throw;
            }
        }
    }

    /// <summary>Return only a new independent Mat after the exact target and all owned cleanup have succeeded.</summary>
    public GameCaptureFrame? Capture()
    {
        // Twenty-one scalar clock reads and fixed-size records add no native call or pixel copy.
        var timing = new DesktopDcCapturePhaseRecorder(_diagnosticTimestamp, _diagnosticFrequency);
        timing.Begin(DesktopDcCapturePhase.GateWait);
        lock (_gate)
        {
            timing.End(DesktopDcCapturePhase.GateWait);
            Volatile.Write(ref _lastTiming, null);
            CheckAvailable();
            if (!_capturing || _target is null) return null;
            if (_captureActive) throw new InvalidOperationException("A desktop capture is already active on this caller.");
            _captureActive = true;
            try { return CaptureUnderGate(_target, _epoch, timing); }
            finally { _captureActive = false; }
        }
    }

    /// <summary>Keep one target/generation throughout the call, including any reentrant Stop request.</summary>
    private GameCaptureFrame CaptureUnderGate(DesktopDcTargetSnapshot target, Guid epoch,
        DesktopDcCapturePhaseRecorder timing)
    {
        var started = _timestamp(); // Deliberately excludes queue time, includes all guards and GDI acquisition.
        if (started <= 0 || started < _lastCompleted)
            throw new InvalidOperationException("Desktop host clock regressed.");
        var owner = new DesktopDcGdiOwner(_gdi);
        IDisposable? dpiScope = null;
        Mat? image = null;
        Exception? failure = null;
        try
        {
            timing.Begin(DesktopDcCapturePhase.DpiSetup);
            dpiScope = _enterDpiScope() ?? throw new InvalidOperationException("Desktop DPI scope was not created.");
            timing.End(DesktopDcCapturePhase.DpiSetup);
            timing.Begin(DesktopDcCapturePhase.PreTargetCheck);
            CheckTarget(target, epoch);
            timing.End(DesktopDcCapturePhase.PreTargetCheck);
            timing.Begin(DesktopDcCapturePhase.Allocation);
            owner.Initialize();
            timing.End(DesktopDcCapturePhase.Allocation);
            owner.Copy(target.ScreenRect.left, target.ScreenRect.top, timing);
            timing.Begin(DesktopDcCapturePhase.PostTargetCheck);
            CheckTarget(target, epoch);
            timing.End(DesktopDcCapturePhase.PostTargetCheck);
            timing.Begin(DesktopDcCapturePhase.Clone);
            image = _clonePixels(owner);
            if (image is null) throw new InvalidOperationException("Desktop clone returned no pixels.");
            timing.End(DesktopDcCapturePhase.Clone);
        }
        catch (Exception error) { failure = error; }
        finally
        {
            timing.Begin(DesktopDcCapturePhase.Cleanup);
            try { owner.Dispose(); }
            catch (Exception error)
            {
                failure = DesktopDcCleanupException.Combine(failure,
                    new DesktopDcCleanupException("Desktop GDI owner cleanup threw.", error));
            }
            if (!owner.CleanupSucceeded)
                failure = DesktopDcCleanupException.Combine(failure,
                    new DesktopDcCleanupException("Desktop GDI cleanup incomplete: " + string.Join("; ", owner.CleanupFailures)));
            timing.End(DesktopDcCapturePhase.Cleanup);
            // Borrowed pixels and GDI resources retire before restoring caller DPI; completion includes both.
            timing.Begin(DesktopDcCapturePhase.DpiRestore);
            RestoreDpi(dpiScope, ref failure);
            timing.End(DesktopDcCapturePhase.DpiRestore);
        }

        try
        {
            if (failure is not null) ExceptionDispatchInfo.Capture(failure).Throw();
            var completed = _timestamp();
            if (completed < started) throw new InvalidOperationException("Desktop host completion clock regressed.");
            CheckGeneration(target, epoch);
            var nextId = checked(_snapshotId + 1);
            var host = new GameCaptureHostSnapshotInfo(epoch, nextId, started, completed, _frequency);
            var frame = new GameCaptureFrame(image!, target.ScreenRect, null, host);
            _snapshotId = nextId;
            _lastCompleted = completed;
            image = null; // Ownership transfers only after cleanup and frame construction succeed.
            Volatile.Write(ref _lastTiming, timing.Complete(host));
            return frame;
        }
        catch (Exception error)
        {
            var terminal = error;
            try { image?.Dispose(); }
            catch (Exception cleanup)
            {
                terminal = DesktopDcCleanupException.Combine(terminal,
                    new DesktopDcCleanupException("Rejected desktop clone cleanup failed.", cleanup));
            }
            QuarantineCleanup(terminal);
            ExceptionDispatchInfo.Capture(terminal).Throw();
            throw;
        }
    }

    /// <summary>Retain a primary failure while making every uncertain restoration terminal.</summary>
    private static void RestoreDpi(IDisposable? scope, ref Exception? failure)
    {
        try { scope?.Dispose(); }
        catch (Exception error)
        {
            failure = DesktopDcCleanupException.Combine(failure,
                error is DesktopDcCleanupException ? error
                    : new DesktopDcCleanupException("Desktop caller DPI cleanup threw.", error));
        }
    }

    /// <summary>Retire the generation after any active serialized call; no GDI cleanup is repeated here.</summary>
    public void Stop()
    {
        lock (_gate)
        {
            Volatile.Write(ref _lastTiming, null);
            _capturing = false;
            _target = null;
            _epoch = Guid.Empty;
        }
    }

    /// <summary>Idempotently retire managed lifetime; no finalizer or background native worker exists.</summary>
    public void Dispose()
    {
        lock (_gate)
        {
            Stop();
            _disposed = true;
        }
        GC.SuppressFinalize(this);
    }

    /// <summary>Revalidate sampled guards and exact generation geometry without adjusting the crop.</summary>
    private void CheckTarget(DesktopDcTargetSnapshot target, Guid epoch)
    {
        CheckGeneration(target, epoch);
        var current = _readTarget(target.Window);
        current.Validate(target.Window);
        CheckGeneration(target, epoch);
        if (current != target) throw new InvalidOperationException("Desktop target or geometry changed during its capture generation.");
    }

    /// <summary>A reentrant Stop can retire admission, but cannot publish an older in-flight snapshot.</summary>
    private void CheckGeneration(DesktopDcTargetSnapshot target, Guid epoch)
    {
        if (!_capturing || !ReferenceEquals(_target, target) || _epoch != epoch)
            throw new InvalidOperationException("Desktop capture generation retired before publication.");
    }

    /// <summary>Failed cleanup permanently blocks reuse even after explicit Stop.</summary>
    private void CheckAvailable()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        if (_terminalCleanupFailure is not null)
            throw new DesktopDcCleanupException("Desktop capture is quarantined after cleanup uncertainty.", _terminalCleanupFailure);
    }

    /// <summary>Keep the original cleanup failure and expose a nonblocking stopped state.</summary>
    private void QuarantineCleanup(Exception error)
    {
        if (!DesktopDcCleanupException.IsPresent(error)) return;
        _terminalCleanupFailure ??= error;
        _capturing = false;
    }

    /// <summary>The borrowed DIB header is retired before its GDI owner; only a plain deep clone can escape.</summary>
    private static Mat ClonePixels(DesktopDcGdiOwner owner)
    {
        Mat? view = null;
        Mat? image = null;
        Exception? failure = null;
        try
        {
            view = Mat.FromPixelData(DesktopDcGdiOwner.Height, DesktopDcGdiOwner.Width,
                MatType.CV_8UC3, owner.Bits, DesktopDcGdiOwner.Stride);
            image = view.Clone();
        }
        catch (Exception error) { failure = error; }
        finally
        {
            try { view?.Dispose(); }
            catch (Exception error)
            {
                failure = DesktopDcCleanupException.Combine(failure,
                    new DesktopDcCleanupException("Borrowed desktop Mat header cleanup failed.", error));
            }
        }
        if (failure is null && image is not null) return image;
        try { image?.Dispose(); }
        catch (Exception error)
        {
            failure = DesktopDcCleanupException.Combine(failure,
                new DesktopDcCleanupException("Failed desktop image clone cleanup failed.", error));
        }
        ExceptionDispatchInfo.Capture(failure ?? new InvalidOperationException("Desktop image clone failed.")).Throw();
        throw new InvalidOperationException("Unreachable desktop clone failure.");
    }
}
