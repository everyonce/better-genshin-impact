using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>A single W lease and horizontal camera gate; capture and recognition never hold this lock.</summary>
internal sealed class NavigationBaselineInputLease : IAsyncDisposable
{
    /// <summary>Regular renewable W lifetime; opted-in physical starts are separately bounded and every expired grant is terminal.</summary>
    internal const double LeaseMs = 100;
    /// <summary>Bound real transitions separately from per-observation renewal intent.</summary>
    internal const int MaximumEvents = 64;
    /// <summary>Serialize dispatch, expiration and terminal release so delayed work cannot re-press.</summary>
    private readonly object _gate = new();
    /// <summary>Monotonic clock and pinned-target check; injected tests need no actual input.</summary>
    private readonly Func<double> _clock;
    /// <summary>Availability checks use the original process/window/backend identity.</summary>
    private readonly Func<bool> _available;
    /// <summary>Only these fixed W and horizontal mouse sinks can dispatch native input.</summary>
    private readonly Action _down, _up;
    /// <summary>Bound horizontal relative mouse sink.</summary>
    private readonly Action<int> _mouse;
    /// <summary>Immutable fixed contract, selected before any native resource or input activity.</summary>
    private readonly string _timingContract;
    /// <summary>Consumed immediately before the first W-down attempt; release/camera work never rearms it.</summary>
    private bool _firstForwardAttempted;
    /// <summary>Task cancellation plus latched watchdog faults; closing normal input does not cancel final verification.</summary>
    private readonly CancellationTokenSource _faultStop;
    /// <summary>Stop the independent watchdog after terminal input closure.</summary>
    private readonly CancellationTokenSource _monitorStop = new();
    /// <summary>A dedicated worker avoids recognition occupying the only watchdog execution slot.</summary>
    private readonly Task _watchdog;
    /// <summary>Bound native-call intent evidence, never an OS-complete or game-acknowledgment trace.</summary>
    private readonly List<NavigationBaselineInputEvent> _events = [];
    /// <summary>Monotonic high-water, current expiry and input-closure completion.</summary>
    private double _lastNow, _expiresAt, _closedAt;
    /// <summary>May-hold is set before keydown and cleared only after successful explicit keyup.</summary>
    private bool _mayHold, _closed;
    /// <summary>Last source used for an input/grant; the same pixels can never renew authority.</summary>
    private GameCaptureSourceInfo? _lastSource;
    /// <summary>First terminal fault and any ambiguous native release failure remain observable.</summary>
    private string? _fault, _releaseError;

    /// <summary>Start only after the caller pins the runtime; tests may drive Check explicitly instead of starting a worker.</summary>
    internal NavigationBaselineInputLease(Func<double> clock, Func<bool> available, Action down, Action up,
        Action<int> mouse, CancellationToken ct, bool startWatchdog = true, string timingContract = NavigationBaselineTiming.V1)
    {
        if (!NavigationBaselineTiming.IsSupported(timingContract)) throw new ArgumentException("unsupported_timing_contract", nameof(timingContract));
        _timingContract = timingContract;
        _clock = clock; _available = available; _down = down; _up = up; _mouse = mouse;
        _faultStop = CancellationTokenSource.CreateLinkedTokenSource(ct);
        try
        {
            _lastNow = clock();
            if (!double.IsFinite(_lastNow) || _lastNow < 0) throw new InvalidOperationException("invalid_lease_clock");
            _watchdog = startWatchdog ? Task.Factory.StartNew(MonitorLoop, CancellationToken.None,
                TaskCreationOptions.LongRunning, TaskScheduler.Default) : Task.CompletedTask;
        }
        catch
        {
            // Failed construction never transfers ownership to the native adapter.
            _faultStop.Dispose(); _monitorStop.Dispose(); throw;
        }
    }

    /// <summary>Combined task/watchdog cancellation for cooperative native observations.</summary>
    internal CancellationToken Token => _faultStop.Token;
    /// <summary>Own held-state evidence, independent of InputChannelBase's optimistic bookkeeping.</summary>
    internal bool ForwardHeld { get { lock (_gate) return _mayHold; } }
    /// <summary>First terminal reason.</summary>
    internal string? Fault { get { lock (_gate) return _fault; } }
    /// <summary>Explicit keyup failure, preserved even if a later best-effort retry succeeds.</summary>
    internal string? ReleaseError { get { lock (_gate) return _releaseError; } }
    /// <summary>Detached bounded transition evidence for publication after input closure.</summary>
    internal NavigationBaselineInputEvent[] Events { get { lock (_gate) return _events.ToArray(); } }

    /// <summary>Read a clock without allowing regressions or malformed samples to extend a lease.</summary>
    private double ReadNow()
    {
        double now;
        try { now = _clock(); }
        catch { Fail("invalid_lease_clock", _lastNow); throw new InvalidOperationException("invalid_lease_clock"); }
        if (!double.IsFinite(now) || now < _lastNow)
        { Fail("invalid_lease_clock", _lastNow); throw new InvalidOperationException("invalid_lease_clock"); }
        return _lastNow = now;
    }

    /// <summary>Sample expiry before and after potentially delayed target checks; a late grant cannot outrun the watchdog.</summary>
    private double CheckReady(bool requireOpen)
    {
        if (_fault is not null) throw new InvalidOperationException(_fault);
        var now = ReadNow();
        if (_mayHold && now >= _expiresAt) { Fail("forward_lease_expired", now); throw new InvalidOperationException(_fault); }
        if (_faultStop.IsCancellationRequested) { Fail("baseline_cancelled", now); throw new OperationCanceledException(Token); }
        if (requireOpen && _closed) throw new InvalidOperationException("baseline_input_closed");
        bool available;
        try { available = _available(); }
        catch { Fail("game_target_check_failed", now); throw new InvalidOperationException(_fault); }
        now = ReadNow();
        if (_mayHold && now >= _expiresAt) { Fail("forward_lease_expired", now); throw new InvalidOperationException(_fault); }
        if (!available) { Fail("game_target_lost", now); throw new InvalidOperationException(_fault); }
        if (_faultStop.IsCancellationRequested) { Fail("baseline_cancelled", now); throw new OperationCanceledException(Token); }
        return now;
    }

    /// <summary>Final source check is performed under the same gate as the actual dispatch or renewal.</summary>
    private double ValidateSource(GameCaptureSourceInfo source, double now)
    {
        var age = NavigationBaselineTask.SourceAge(source, now);
        if (!double.IsFinite(age) || age is < 0 or > NavigationBaselineTask.MaximumSourceAgeMs)
        { Fail("native_source_stale", now); throw new InvalidOperationException(_fault); }
        if (_lastSource is { } previous && (source.CaptureEpoch != previous.CaptureEpoch
                || source.SourceTimestamp100ns <= previous.SourceTimestamp100ns
                || source.AcquiredAtStopwatchTicks <= previous.AcquiredAtStopwatchTicks))
        { Fail("input_source_not_increasing", now); throw new InvalidOperationException(_fault); }
        return age;
    }

    /// <summary>Reserve two terminal/release entries before a real call; overflow must not create unrecorded input.</summary>
    private void RequireEventCapacity(double now)
    {
        if (_events.Count >= MaximumEvents - 2)
        { Fail("input_evidence_capacity_exceeded", now); throw new InvalidOperationException(_fault); }
    }

    /// <summary>Renew only on a new source. An existing W hold never receives another keydown.</summary>
    internal NavigationBaselineInputEvent Forward(GameCaptureSourceInfo source, CancellationToken ct)
    {
        lock (_gate)
        {
            ct.ThrowIfCancellationRequested();
            var now = CheckReady(true);
            var age = ValidateSource(source, now);
            var changed = !_mayHold;
            if (changed) RequireEventCapacity(now);
            ct.ThrowIfCancellationRequested();
            var firstAttempt = !_firstForwardAttempted;
            (double GrantMs, double AnchorMs, double? SourceCapMs, double ExpiresAtMs) grant;
            try { grant = NavigationBaselineTiming.Grant(_timingContract, firstAttempt, changed, source, now); }
            catch { Fail("invalid_forward_grant", now); throw; }
            _lastSource = source;
            _expiresAt = grant.ExpiresAtMs;
            if (changed)
            {
                _mayHold = true; // Native partial failure can occur before InputChannelBase records the key.
                _firstForwardAttempted = true;
                try { _down(); }
                catch (Exception exception)
                {
                    _events.Add(new("w_down", now, ReadNow(), _expiresAt, age, Error: exception.GetBaseException().Message,
                        GrantMs: grant.GrantMs, SourceAnchorAtMs: grant.AnchorMs, SourceCapAtMs: grant.SourceCapMs, FirstForwardAttempt: firstAttempt));
                    Fail("forward_dispatch_failed", _lastNow); throw;
                }
            }
            var completed = ReadNow();
            var intent = new NavigationBaselineInputEvent(changed ? "w_down" : "renew_w", now, completed, _expiresAt, age,
                GrantMs: grant.GrantMs, SourceAnchorAtMs: grant.AnchorMs, SourceCapAtMs: grant.SourceCapMs, FirstForwardAttempt: firstAttempt);
            if (changed) _events.Add(intent);
            if (completed >= _expiresAt) { Fail("forward_lease_expired", completed); throw new InvalidOperationException(_fault); }
            if (_faultStop.IsCancellationRequested) { Fail("baseline_cancelled", completed); throw new OperationCanceledException(Token); }
            return intent;
        }
    }

    /// <summary>Only horizontal camera movement is permitted, while W is released and the measured source is current.</summary>
    internal NavigationBaselineInputEvent Rotate(GameCaptureSourceInfo source, int dx, CancellationToken ct)
    {
        lock (_gate)
        {
            ct.ThrowIfCancellationRequested();
            var now = CheckReady(true);
            if (_mayHold) throw new InvalidOperationException("camera_requires_forward_release");
            var age = ValidateSource(source, now);
            RequireEventCapacity(now);
            ct.ThrowIfCancellationRequested();
            _lastSource = source;
            try { if (dx != 0) _mouse(dx); }
            catch (Exception exception)
            {
                _events.Add(new("camera", now, ReadNow(), SourceAgeMs: age, MouseDx: dx, Error: exception.GetBaseException().Message));
                Fail("camera_dispatch_failed", _lastNow); throw;
            }
            var intent = new NavigationBaselineInputEvent(dx == 0 ? "camera_noop" : "camera", now, ReadNow(), SourceAgeMs: age, MouseDx: dx);
            if (dx != 0) _events.Add(intent);
            if (_faultStop.IsCancellationRequested) { Fail("baseline_cancelled", _lastNow); throw new OperationCanceledException(Token); }
            return intent;
        }
    }

    /// <summary>Explicit W release retains ambiguous held-state on native failure.</summary>
    private NavigationBaselineInputEvent Release(double now)
    {
        var kind = _mayHold ? "w_up" : "already_released";
        string? error = null;
        if (_mayHold)
        {
            try { _up(); _mayHold = false; }
            catch (Exception exception) { error = exception.GetBaseException().Message; _releaseError ??= error; }
        }
        // A failing clock cannot prevent keyup. Preserve the latest safe clock and flag the release measurement.
        double completed;
        try { completed = _clock(); if (!double.IsFinite(completed) || completed < now) throw new InvalidOperationException(); }
        catch { completed = now; _fault ??= "invalid_lease_clock"; error ??= "invalid_release_clock"; }
        _lastNow = Math.Max(_lastNow, completed);
        var entry = new NavigationBaselineInputEvent(kind, now, completed, _expiresAt > 0 ? _expiresAt : null, Error: error);
        if (kind == "w_up" && _events.Count < MaximumEvents) _events.Add(entry);
        return entry;
    }

    /// <summary>First terminal failure latches before release; later valid observations cannot reopen input.</summary>
    private void Fail(string reason, double now)
    {
        _fault ??= reason;
        _closed = true;
        var release = Release(now);
        _closedAt = release.CompletedAtMs;
        if (_events.Count < MaximumEvents) _events.Add(new("fault", now, _closedAt, _expiresAt > 0 ? _expiresAt : null, Error: _fault));
        _faultStop.Cancel();
        _monitorStop.Cancel();
    }

    /// <summary>Release for normal realignment without permanently closing this controller.</summary>
    internal NavigationBaselineInputEvent ReleaseForward()
    {
        lock (_gate)
        {
            var now = CheckReady(true);
            RequireEventCapacity(now);
            var result = Release(now);
            if (result.Error is not null) { Fail("input_release_failed", result.CompletedAtMs); throw new InvalidOperationException(_fault); }
            return result;
        }
    }

    /// <summary>Latch closure before keyup; return the completed release/cutoff clock for final fresh-frame verification.</summary>
    internal double Close()
    {
        lock (_gate)
        {
            if (!_closed)
            {
                var now = ReadNow();
                if (_mayHold && now >= _expiresAt) Fail("forward_lease_expired", now);
                else { _closed = true; _closedAt = Release(now).CompletedAtMs; }
            }
            else if (_mayHold) _closedAt = Release(_lastNow).CompletedAtMs;
            _monitorStop.Cancel();
            if (_releaseError is not null) throw new InvalidOperationException($"input_release_failed: {_releaseError}");
            if (_fault is not null) throw new InvalidOperationException(_fault);
            return _closedAt;
        }
    }

    /// <summary>One watchdog check; deterministic tests can control the exact contention and expiry time.</summary>
    internal void Check()
    {
        lock (_gate)
        {
            if (_closed) return;
            try { CheckReady(false); }
            catch (Exception) when (_fault is not null) { /* Fault latching already attempted explicit release. */ }
        }
    }

    /// <summary>Nominal25ms independent release checks, with no hard OS scheduling or native-call latency guarantee.</summary>
    private void MonitorLoop()
    {
        try
        {
            while (!_monitorStop.IsCancellationRequested)
            {
                Check();
                if (_monitorStop.Token.WaitHandle.WaitOne(25)) break;
            }
        }
        catch (Exception)
        {
            lock (_gate) if (!_closed) Fail("lease_watchdog_failed", _lastNow);
        }
    }

    /// <summary>Always drain the independent worker before disposing resources, including after failed native release.</summary>
    public async ValueTask DisposeAsync()
    {
        try { Close(); }
        finally
        {
            _monitorStop.Cancel();
            await _watchdog.ConfigureAwait(false);
            _faultStop.Dispose(); _monitorStop.Dispose();
        }
    }
}
