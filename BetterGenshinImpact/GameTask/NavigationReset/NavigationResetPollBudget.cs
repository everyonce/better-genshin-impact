using System;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;

namespace BetterGenshinImpact.GameTask.NavigationReset;

/// <summary>One opt-in reset window: Pending metadata has a finite budget separate from actual observations.</summary>
internal sealed class NavigationResetPollBudget
{
    /// <summary>Unchanged wall-clock allowance for either preparation or pose acquisition.</summary>
    internal const int MaximumWaitMilliseconds = 3000;
    /// <summary>Existing bound on potentially completed or failed native observations.</summary>
    internal const int MaximumObservations = 25;
    /// <summary>Finite metadata-only allowance; another call is forbidden once it is exhausted.</summary>
    internal const int MaximumPendingPolls = 400;
    /// <summary>Conservative reservations, including charged setup failures before a native call.</summary>
    internal const int MaximumPolls = MaximumObservations + MaximumPendingPolls;
    /// <summary>Requested wait for validated metadata only; actual scheduling is not guaranteed.</summary>
    internal const int PendingDelayMilliseconds = 5;
    /// <summary>Monotonic clock; injectable only for deterministic budget checks.</summary>
    private readonly Func<long> _timestamp;
    /// <summary>Existing owner and separately linked window cancellation retain their identities.</summary>
    private readonly CancellationToken _owner, _deadline;
    /// <summary>Bounded metadata observer; diagnostic failures cannot replace control failures.</summary>
    private readonly Action<NavigationResetPollingDiagnostic>? _observe;
    /// <summary>Entry/deadline and previous observed clock belong to this one window.</summary>
    private readonly long _started, _deadlineAt;
    /// <summary>Most recent actual budget-check time; snapshots do not advance it.</summary>
    private long _lastClock;
    /// <summary>At most one reservation may be unsettled; no detached capture work is supported.</summary>
    private Reservation? _active;
    /// <summary>Aggregate immutable publication is constructed from these bounded scalar counters.</summary>
    private int _polls, _charged, _pending, _waits;
    /// <summary>Only one last wait plus aggregate elapsed time are retained, never a growing array.</summary>
    private long? _waitStarted, _waitExited, _ended;
    /// <summary>Requested duration and summed/max observed waits include scheduling and continuation time.</summary>
    private int? _waitRequested;
    /// <summary>Measured aggregate waits are host intervals, not GPU readiness or kernel wake times.</summary>
    private double _waitSum, _waitMax;
    /// <summary>Separate Pending5ms waits from unchanged120ms observation settling in successful final summaries.</summary>
    private int _pendingWaits, _observationWaits;
    /// <summary>Separate measured host intervals without storing an unbounded per-poll series.</summary>
    private double _pendingWaitSum, _pendingWaitMax, _observationWaitSum, _observationWaitMax;
    /// <summary>Current/terminal outcome and bounded error remain distinct from readiness admission.</summary>
    private string _outcome = "active";
    /// <summary>Terminal exception text is diagnostic only; callers preserve the original exception.</summary>
    private string? _error;

    /// <summary>Pin one clock origin and the existing owner/window tokens without starting any worker.</summary>
    internal NavigationResetPollBudget(CancellationToken owner, CancellationToken deadline,
        Action<NavigationResetPollingDiagnostic>? observe = null, Func<long>? timestamp = null)
    {
        _timestamp = timestamp ?? Stopwatch.GetTimestamp;
        _owner = owner; _deadline = deadline; _observe = observe;
        _started = _lastClock = _timestamp();
        _deadlineAt = checked(_started + 3 * Stopwatch.Frequency);
        Publish();
    }

    /// <summary>One-based provisional observation ordinal; Pending refunds can cause it to repeat.</summary>
    internal int ChargedObservations => _charged;
    /// <summary>Total reservations so far, not necessarily completed native calls.</summary>
    internal int PollCount => _polls;
    /// <summary>Independent monotonic deadline rejects late work even when the cancellation timer runs late.</summary>
    internal void CheckBudget()
    {
        _owner.ThrowIfCancellationRequested();
        var now = _timestamp();
        if (now < _lastClock) throw new InvalidOperationException("reset_readiness_clock_regressed");
        _lastClock = now;
        if (_deadline.IsCancellationRequested || now >= _deadlineAt)
            throw new NavigationResetPollLimitException("deadline");
    }

    /// <summary>Reserve before native/setup work; any path other than validated Pending keeps its charge.</summary>
    internal Reservation BeginPoll()
    {
        EnsureNextPollAvailable();
        if (_active is not null) throw new InvalidOperationException("reset_readiness_reservation_active");
        _polls++; _charged++;
        _active = new Reservation(this);
        Publish();
        return _active;
    }

    /// <summary>Do not wait unnecessarily after the last allowed miss, or enter an over-limit native call.</summary>
    internal void EnsureNextPollAvailable()
    {
        CheckBudget();
        if (_charged >= MaximumObservations) throw new NavigationResetPollLimitException("observation_limit");
        if (_pending >= MaximumPendingPolls) throw new NavigationResetPollLimitException("pending_limit");
        if (_polls >= MaximumPolls) throw new NavigationResetPollLimitException("poll_limit");
    }

    /// <summary>Only the exact outstanding reservation can receive one metadata refund.</summary>
    private void Settle(Reservation reservation, bool pending)
    {
        if (!ReferenceEquals(_active, reservation) || reservation.Settled)
            throw new InvalidOperationException("reset_readiness_reservation_already_settled");
        reservation.Settled = true;
        _active = null;
        if (pending) { _charged--; _pending++; }
        Publish();
    }

    /// <summary>Retain one actual wait interval and check the same original deadline before and after await.</summary>
    internal async Task WaitAsync(int milliseconds, Func<int, CancellationToken, Task> delay)
    {
        if (_active is not null) throw new InvalidOperationException("reset_readiness_unsettled_before_wait");
        CheckBudget();
        _waitStarted = _lastClock; _waitExited = null; _waitRequested = milliseconds; _waits++;
        if (milliseconds == PendingDelayMilliseconds) _pendingWaits++; else _observationWaits++;
        Publish();
        try { await delay(milliseconds, _deadline).ConfigureAwait(false); }
        finally
        {
            _waitExited = _timestamp();
            if (_waitExited >= _waitStarted)
            {
                var elapsed = Stopwatch.GetElapsedTime(_waitStarted.Value, _waitExited.Value).TotalMilliseconds;
                _waitSum += elapsed; _waitMax = Math.Max(_waitMax, elapsed);
                if (milliseconds == PendingDelayMilliseconds)
                { _pendingWaitSum += elapsed; _pendingWaitMax = Math.Max(_pendingWaitMax, elapsed); }
                else { _observationWaitSum += elapsed; _observationWaitMax = Math.Max(_observationWaitMax, elapsed); }
            }
            Publish();
        }
        CheckBudget();
    }

    /// <summary>Publish final metadata only after all reservation scopes have settled.</summary>
    internal void Finish(Exception? error)
    {
        _ended = _timestamp();
        _outcome = error is null ? "completed" : error is OperationCanceledException ? "cancelled" : "failed";
        _error = error?.Message is { Length: > 200 } message ? message[..200] : error?.Message;
        Publish();
    }

    /// <summary>Snapshot contains metadata only and conservatively includes an in-flight charge.</summary>
    internal NavigationResetPollingDiagnostic Snapshot() => new()
    {
        StartedAtTicks = _started, DeadlineAtTicks = _deadlineAt, LastCheckedAtTicks = _lastClock,
        EndedAtTicks = _ended, PollCount = _polls, ChargedObservations = _charged, ValidatedPendingPolls = _pending,
        ReservationOutstanding = _active is not null, Outcome = _outcome, Error = _error,
        WaitCount = _waits, LastWaitRequestedMilliseconds = _waitRequested, LastWaitStartedAtTicks = _waitStarted,
        LastWaitExitedAtTicks = _waitExited, ObservedWaitSumMilliseconds = _waitSum, ObservedWaitMaximumMilliseconds = _waitMax,
        PendingWaitCount = _pendingWaits, PendingWaitSumMilliseconds = _pendingWaitSum, PendingWaitMaximumMilliseconds = _pendingWaitMax,
        ObservationWaitCount = _observationWaits, ObservationWaitSumMilliseconds = _observationWaitSum, ObservationWaitMaximumMilliseconds = _observationWaitMax
    };

    /// <summary>Source diagnostics cannot change cancellation, capture ownership or the original error.</summary>
    private void Publish()
    {
        try { _observe?.Invoke(Snapshot()); }
        catch { /* Bounded evidence never replaces readiness behavior. */ }
    }

    /// <summary>Exactly one provisional charge; disposing without a valid refund remains charged.</summary>
    internal sealed class Reservation(NavigationResetPollBudget owner) : IDisposable
    {
        /// <summary>True after the sole successful charge/refund settlement.</summary>
        internal bool Settled { get; set; }
        /// <summary>Native caller must already have validated the typed Pending descriptor.</summary>
        internal void CompleteValidatedPending() => owner.Settle(this, true);
        /// <summary>Ready, null, malformed metadata and exceptions all retain their charge.</summary>
        public void Dispose() { if (!Settled) owner.Settle(this, false); }
    }
}

/// <summary>Internal budget signal, distinguished from unrelated native timeouts by the phase helper.</summary>
internal sealed class NavigationResetPollLimitException(string reason) : Exception(reason);
