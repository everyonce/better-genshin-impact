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
    /// <summary>Recovery is admitted only after the anchor gate; terminal closure never rearms it.</summary>
    private bool _recoveryEnabled;
    /// <summary>Latch before invoking keyup, including a same-thread reentrant sink.</summary>
    private bool _pauseInProgress;
    /// <summary>Same watchdog and gate own a bounded pause, without cancelling or replacing either CTS.</summary>
    private NavigationBaselineRecoveryPause? _pause;
    /// <summary>Every pause survives resume/failure in the file journal, including an unhandled final pause.</summary>
    private readonly List<NavigationBaselineRecoveryPause> _pauses = [];
    /// <summary>Movement pause admissions remain capped for the complete run, across both legs.</summary>
    private int _movementRecoveries;
    /// <summary>Only SourceAge with no possibly held W consumes this independent readiness allowance.</summary>
    private int _stationaryReadiness;
    /// <summary>One planned waypoint stop per run; latch before keyup to reject reentrant dispatch.</summary>
    private bool _waypointAttempted, _waypointReleaseInProgress;
    /// <summary>Reject same-thread reentrant handoff while availability is being checked.</summary>
    private bool _waypointEndInProgress;
    /// <summary>Exact immutable release identity; a terminal failure never clears this held-off state.</summary>
    private NavigationBaselineWaypointHold? _waypoint;

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

    /// <summary>The exact live pause ticket, not a terminal fault.</summary>
    internal NavigationBaselineRecoveryPause? PendingRecovery { get { lock (_gate) return _pause; } }
    /// <summary>Detached bounded history; a successful resume never erases its preceding interruption.</summary>
    internal NavigationBaselineRecoveryPause[] RecoveryPauses { get { lock (_gate) return _pauses.ToArray(); } }
    /// <summary>A planned hold forbids all input and recovery operations without replacing the watchdog.</summary>
    internal bool WaypointHeld { get { lock (_gate) return _waypointReleaseInProgress || _waypoint is not null; } }

    /// <summary>Reject dispatch/recovery while a planned release or its read-only checkpoint owns the gate.</summary>
    private void RequireNoWaypointHold()
    {
        if (_waypointReleaseInProgress || _waypoint is not null)
            throw new InvalidOperationException("waypoint_input_held");
    }

    /// <summary>Release once after the ordinary expiry/target checks; an existing recovery pause wins admission.</summary>
    internal NavigationBaselineWaypointHold BeginWaypointHold(CancellationToken ct)
    {
        lock (_gate)
        {
            ct.ThrowIfCancellationRequested();
            if (_timingContract != NavigationBaselineTiming.V4 || !_recoveryEnabled)
                throw new InvalidOperationException("waypoint_hold_not_available");
            if (_waypointAttempted) throw new InvalidOperationException("waypoint_hold_already_used");
            var now = CheckReady(true);
            // A reentrant availability callback may have closed input or admitted the one hold already.
            if (_fault is not null) throw new InvalidOperationException(_fault);
            if (_closed) throw new InvalidOperationException("baseline_input_closed");
            if (_waypointAttempted) throw new InvalidOperationException("waypoint_hold_already_used");
            RequireEventCapacity(now);
            ct.ThrowIfCancellationRequested(); Token.ThrowIfCancellationRequested();
            _waypointAttempted = true;
            _waypointReleaseInProgress = true;
            NavigationBaselineInputEvent release;
            try { release = Release(now); }
            finally { _waypointReleaseInProgress = false; }
            // Already-released is still a fresh cutoff. No source, first-W identity or worker is reset.
            _waypoint = new(release);
            _events.Add(new("waypoint_hold", now, release.CompletedAtMs, Error: release.Error));
            if (_closed || _fault is not null || _mayHold || _releaseError is not null || release.Error is not null)
            { Fail("waypoint_release_failed", release.CompletedAtMs); throw new InvalidOperationException(_fault); }
            if (ct.IsCancellationRequested || Token.IsCancellationRequested)
            { Fail("baseline_cancelled", release.CompletedAtMs); throw new OperationCanceledException(ct.IsCancellationRequested ? ct : Token); }
            return _waypoint;
        }
    }

    /// <summary>End only this live hold from a fresh post-release anchor; failures close input, never create recovery.</summary>
    internal void EndWaypointHold(NavigationBaselineWaypointHold ticket, GameCaptureSourceInfo source,
        double deadlineAtMs, CancellationToken ct)
    {
        lock (_gate)
        {
            var ownsEnd = false;
            try
            {
                if (_fault is not null) throw new InvalidOperationException(_fault);
                if (_closed) throw new InvalidOperationException("baseline_input_closed");
                ct.ThrowIfCancellationRequested(); Token.ThrowIfCancellationRequested();
                if (_waypointEndInProgress || _waypointReleaseInProgress || _waypoint is null || !ReferenceEquals(ticket, _waypoint))
                    throw new InvalidOperationException("waypoint_ticket_changed");
                if (_mayHold || _releaseError is not null || ticket.Release.Error is not null || _pause is not null)
                    throw new InvalidOperationException("waypoint_release_unconfirmed");
                var now = ReadNow();
                ValidateInputSourceIdentity(source, now);
                if (!double.IsFinite(deadlineAtMs) || deadlineAtMs < 0)
                    throw new InvalidOperationException("invalid_waypoint_deadline");
                _waypointEndInProgress = ownsEnd = true;
                bool available;
                try { available = _available(); }
                catch { throw new InvalidOperationException("game_target_check_failed"); }
                // Availability can be slow or reentrant: closure, owner cancellation and the clocks win afterward.
                now = ReadNow();
                if (_fault is not null) throw new InvalidOperationException(_fault);
                if (_closed) throw new InvalidOperationException("baseline_input_closed");
                if (!ReferenceEquals(ticket, _waypoint)) throw new InvalidOperationException("waypoint_ticket_changed");
                if (!available) throw new InvalidOperationException("game_target_lost");
                ct.ThrowIfCancellationRequested(); Token.ThrowIfCancellationRequested();
                ValidateInputSourceIdentity(source, now);
                if (now >= Math.Min(deadlineAtMs, ticket.Release.CompletedAtMs + 2000))
                    throw new InvalidOperationException("waypoint_deadline_exceeded");
                var age = NavigationBaselineTask.SourceAge(source, now);
                if (!double.IsFinite(age) || age is < 0 or > NavigationBaselineTask.MaximumSourceAgeMs)
                    throw new InvalidOperationException("native_source_stale");
                if (!NavigationBaselineTask.AfterBarrier(source, ticket.Release.CompletedAtMs, 80))
                    throw new InvalidOperationException("waypoint_source_before_release_barrier");
                RequireEventCapacity(now);
                ct.ThrowIfCancellationRequested(); Token.ThrowIfCancellationRequested();
                _events.Add(new("waypoint_resume", now, now));
                _waypoint = null; // The next ordinary input consumes this anchor once, after its own fresh-source gate.
            }
            catch (Exception error)
            {
                if (!_closed)
                    Fail(error is OperationCanceledException ? "baseline_cancelled" : error.GetBaseException().Message, _lastNow);
                throw;
            }
            finally { if (ownsEnd) _waypointEndInProgress = false; }
        }
    }

    /// <summary>Explicitly arm only this opt-in contract after initial-anchor verification.</summary>
    internal void EnableRecovery()
    {
        lock (_gate)
        {
            if (_timingContract != NavigationBaselineTiming.V4 || _closed || _fault is not null)
                throw new InvalidOperationException("recovery_not_available");
            CheckReady(true);
            _recoveryEnabled = true;
        }
    }

    /// <summary>Latch input pause before keyup. The same monitor remains alive but never presses.</summary>
    private NavigationBaselineRecoveryPause PauseCore(NavigationBaselineRecoveryCause cause, double now)
    {
        RequireNoWaypointHold();
        if (_pause is not null) return _pause;
        if (!_recoveryEnabled || _closed || _timingContract != NavigationBaselineTiming.V4)
            throw new InvalidOperationException("recovery_not_available");
        // Classify under the same gate BEFORE Release clears _mayHold. Existing tickets above keep their original kind.
        var heldForwardAtEntry = _mayHold;
        var stationary = cause == NavigationBaselineRecoveryCause.SourceAge && !heldForwardAtEntry;
        if (_pauses.Count >= NavigationBaselineRecovery.MaximumPauseWindows
            || (stationary ? _stationaryReadiness >= NavigationBaselineRecovery.MaximumStationaryReadiness
                : _movementRecoveries >= NavigationBaselineRecovery.MaximumRecoveries))
        { Fail("recovery_limit_exceeded", now); throw new InvalidOperationException(_fault); }
        if (_events.Count >= MaximumEvents - 3)
        { Fail("input_evidence_capacity_exceeded", now); throw new InvalidOperationException(_fault); }
        // The gate prevents every dispatch while release runs. Publish the ticket before returning to any caller.
        NavigationBaselineInputEvent release;
        _pauseInProgress = true;
        try { release = Release(now); }
        finally { _pauseInProgress = false; }
        if (stationary) _stationaryReadiness++; else _movementRecoveries++;
        _pause = new(_pauses.Count + 1, cause, now, release.CompletedAtMs, release.Error)
        {
            BudgetKind = stationary ? NavigationBaselineRecoveryBudgetKind.StationarySourceReadiness
                : NavigationBaselineRecoveryBudgetKind.MovementRecovery,
            HeldForwardAtEntry = heldForwardAtEntry,
            MovementRecoveriesUsed = _movementRecoveries,
            StationaryReadinessUsed = _stationaryReadiness
        };
        _pauses.Add(_pause);
        _events.Add(new("recovery_pause", now, release.CompletedAtMs, Error: release.Error));
        if (_mayHold || _releaseError is not null || _fault is not null || release.Error is not null)
        { Fail("input_release_failed", release.CompletedAtMs); throw new InvalidOperationException(_fault); }
        return _pause;
    }

    /// <summary>Join an existing watchdog pause or release once for a typed source-age interruption.</summary>
    internal NavigationBaselineRecoveryPause PauseForRecovery(NavigationBaselineRecoveryRequired interruption, CancellationToken ct)
    {
        lock (_gate)
        {
            ct.ThrowIfCancellationRequested();
            RequireNoWaypointHold();
            var now = CheckReady(false);
            if (_closed || !_recoveryEnabled) throw new InvalidOperationException("recovery_not_available");
            if (interruption.Pause is not null && !ReferenceEquals(interruption.Pause, _pause))
                throw new InvalidOperationException("recovery_ticket_changed");
            if (interruption.Cause is not (NavigationBaselineRecoveryCause.SourceAge or NavigationBaselineRecoveryCause.LeaseExpired))
                throw new InvalidOperationException("invalid_recovery_cause");
            return PauseCore(interruption.Cause, now);
        }
    }

    /// <summary>Rearm from an exact ticket and fresh post-release source; no key or mouse call occurs here.</summary>
    internal void ResumeRecovery(NavigationBaselineRecoveryPause pause, GameCaptureSourceInfo source, CancellationToken ct)
    {
        lock (_gate)
        {
            ct.ThrowIfCancellationRequested();
            RequireNoWaypointHold();
            if (_closed) throw new InvalidOperationException("baseline_input_closed");
            // Hard metadata cannot be concealed by a concurrent expiry/pause.
            ValidateInputSourceIdentity(source, ReadNow());
            var now = CheckReady(false);
            if (_closed || !_recoveryEnabled || !ReferenceEquals(_pause, pause))
                throw new InvalidOperationException("recovery_ticket_changed");
            if (_mayHold || _releaseError is not null || pause.ReleaseError is not null)
                throw new InvalidOperationException("recovery_release_unconfirmed");
            ValidateSource(source, now);
            if (!NavigationBaselineTask.AfterBarrier(source, pause.ReleasedAtMs, 80))
                throw new InvalidOperationException("recovery_source_before_release_barrier");
            RequireEventCapacity(now);
            ct.ThrowIfCancellationRequested(); Token.ThrowIfCancellationRequested();
            _events.Add(new("recovery_resume", now, now));
            _pause = null; // Keep run-first identity, source high-water and the same watcher/CTS.
        }
    }

    /// <summary>Reject malformed/regressing input sources before checking a possibly recoverable timing fault.</summary>
    private void ValidateInputSourceIdentity(GameCaptureSourceInfo source, double now)
    {
        var rejection = NavigationBaselineRecovery.HardSourceRejection(source, now, _lastSource);
        if (rejection is null && _lastSource is { } prior && (source.SourceTimestamp100ns <= prior.SourceTimestamp100ns
                || source.AcquiredAtStopwatchTicks <= prior.AcquiredAtStopwatchTicks)) rejection = "input_source_not_increasing";
        if (rejection is not null) { Fail(rejection, now); throw new InvalidOperationException(rejection); }
    }

    /// <summary>V4 keeps its original single watchdog alive during pause; only hard failures cancel its token.</summary>
    private double CheckV4(bool requireOpen)
    {
        if (_fault is not null) throw new InvalidOperationException(_fault);
        if (_pauseInProgress) throw new InvalidOperationException("recovery_release_in_progress");
        if (_waypointReleaseInProgress) throw new InvalidOperationException("waypoint_input_held");
        if (requireOpen) RequireNoWaypointHold();
        var now = ReadNow();
        if (_faultStop.IsCancellationRequested) { Fail("baseline_cancelled", now); throw new OperationCanceledException(Token); }
        if (requireOpen && _closed) throw new InvalidOperationException("baseline_input_closed");
        // Preserve prompt legacy release before a target check that may itself be delayed.
        // The ticket remains unexposed to this caller until all hard checks below have passed.
        if (_mayHold && now >= _expiresAt)
        {
            if (!_recoveryEnabled) { Fail("forward_lease_expired", now); throw new InvalidOperationException(_fault); }
            PauseCore(NavigationBaselineRecoveryCause.LeaseExpired, now);
        }
        bool available;
        try { available = _available(); }
        catch { Fail("game_target_check_failed", now); throw new InvalidOperationException(_fault); }
        now = ReadNow();
        if (!available) { Fail("game_target_lost", now); throw new InvalidOperationException(_fault); }
        if (_faultStop.IsCancellationRequested) { Fail("baseline_cancelled", now); throw new OperationCanceledException(Token); }
        if (_mayHold && now >= _expiresAt)
        {
            if (!_recoveryEnabled) { Fail("forward_lease_expired", now); throw new InvalidOperationException(_fault); }
            PauseCore(NavigationBaselineRecoveryCause.LeaseExpired, now);
        }
        if (_pause is { } pending && now >= pending.StartedAtMs + NavigationBaselineRecovery.MaximumWaitMs)
        { Fail("recovery_deadline_exceeded", now); throw new InvalidOperationException(_fault); }
        if (_waypoint is { } waypoint && now >= waypoint.Release.CompletedAtMs + 2000)
        { Fail("waypoint_deadline_exceeded", now); throw new InvalidOperationException(_fault); }
        if (requireOpen && _pause is { } pause)
            throw new NavigationBaselineRecoveryRequired(pause.Cause, "input_gate", pause: pause);
        return now;
    }

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
        if (_timingContract == NavigationBaselineTiming.V4) return CheckV4(requireOpen);
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
        if (_timingContract == NavigationBaselineTiming.V4) ValidateInputSourceIdentity(source, now);
        var age = NavigationBaselineTask.SourceAge(source, now);
        if (_recoveryEnabled && double.IsFinite(age) && age > NavigationBaselineTask.MaximumSourceAgeMs)
        {
            var pause = PauseCore(NavigationBaselineRecoveryCause.SourceAge, now);
            throw new NavigationBaselineRecoveryRequired(NavigationBaselineRecoveryCause.SourceAge, "input_source_age", source, pause);
        }
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
            RequireNoWaypointHold();
            if (_timingContract == NavigationBaselineTiming.V4) ValidateInputSourceIdentity(source, ReadNow());
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
            if (completed >= _expiresAt)
            {
                if (_recoveryEnabled)
                {
                    var pause = PauseCore(NavigationBaselineRecoveryCause.LeaseExpired, completed);
                    throw new NavigationBaselineRecoveryRequired(pause.Cause, "after_forward_dispatch", source, pause);
                }
                Fail("forward_lease_expired", completed); throw new InvalidOperationException(_fault);
            }
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
            RequireNoWaypointHold();
            if (_timingContract == NavigationBaselineTiming.V4) ValidateInputSourceIdentity(source, ReadNow());
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
            _recoveryEnabled = false; // Permanent closure wins over every outstanding resume ticket.
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

/// <summary>One run-local planned hold; matching values never replace the exact admitted ticket identity.</summary>
/// <param name="Release">Completed explicit keyup or already-released cutoff, not physical game acknowledgment.</param>
internal sealed record NavigationBaselineWaypointHold(NavigationBaselineInputEvent Release);
