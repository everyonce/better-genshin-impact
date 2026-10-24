using System;
using System.Threading;
using BetterGenshinImpact.GameTask.Runtime;
using Fischless.GameCapture;

namespace BetterGenshinImpact.GameTask.NavigationBaseline;

/// <summary>One paused recovery's serial capture accounting; it owns no pixels, timer, task or input permission.</summary>
internal sealed class NavigationBaselineRecoveryReadbackBudget
{
    /// <summary>Charged observations remain bounded separately from explicitly validated unpublished work.</summary>
    internal const int MaximumCaptures = 32, MaximumPendingPolls = 400, MaximumPolls = 432, PendingDelayMs = 5;
    /// <summary>The native monotonic clock and existing attempt record remain owned by this one recovery.</summary>
    private readonly Func<double> _clock;
    /// <summary>Bounded scalar evidence, shared with final publication after input closes.</summary>
    private readonly NavigationBaselineRecoveryAttempt _record;
    /// <summary>Geometry already established by the accepted initial pose cannot change while paused.</summary>
    private readonly int _width, _height;
    /// <summary>Most recent checked clock; failure cannot rewind or extend the original deadline.</summary>
    private double _lastClock;
    /// <summary>At most one pre-call reservation; scope exit keeps an unclassified call charged.</summary>
    private CaptureReservation? _reservation;
    /// <summary>Terminal scope closure permanently prevents later reservations/refunds.</summary>
    private bool _closed;
    /// <summary>Valid returned headers include stale discards, but Pending never advances this floor.</summary>
    internal GameCaptureSourceInfo? SeenSource => _record.SeenSource;

    /// <summary>Bind the already fixed deadline and known consumed source without creating any worker.</summary>
    internal NavigationBaselineRecoveryReadbackBudget(Func<double> clock, NavigationBaselineRecoveryAttempt record,
        GameCaptureSourceInfo? consumedSource, int width, int height)
    {
        _clock = clock; _record = record; _width = width; _height = height;
        _lastClock = record.Pause.StartedAtMs;
        _record.SeenSource = consumedSource;
        if (consumedSource is null || width <= 0 || height <= 0)
            throw new InvalidOperationException("recovery_source_context_missing");
    }

    /// <summary>Record a monotonic boundary before interpreting source metadata; no input authority is produced.</summary>
    private double ReadClock(CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if (_closed) throw new InvalidOperationException("recovery_readback_already_closed");
        var now = _clock();
        if (!double.IsFinite(now) || now < _lastClock)
            throw new InvalidOperationException("invalid_recovery_window");
        _lastClock = now; _record.LastBudgetCheckAtMs = now;
        return now;
    }

    /// <summary>Check the original fixed deadline without consuming a capture or renewing input.</summary>
    internal double Check(CancellationToken ct)
    {
        var now = ReadClock(ct);
        NavigationBaselineRecovery.EnsureWindow(now, _record.DeadlineAtMs, _record.CaptureCount);
        return now;
    }

    /// <summary>Reserve before setup/capture; only the exact active reservation may later receive one Pending refund.</summary>
    internal CaptureReservation BeginCapture(CancellationToken ct)
    {
        Check(ct);
        if (_reservation is not null) throw new InvalidOperationException("recovery_capture_unsettled");
        if (_record.CaptureCount >= MaximumCaptures) throw new InvalidOperationException("recovery_capture_limit_exceeded");
        if (_record.PendingPollCount >= MaximumPendingPolls) throw new InvalidOperationException("recovery_pending_poll_limit_exceeded");
        if (_record.PollCount >= MaximumPolls) throw new InvalidOperationException("recovery_poll_limit_exceeded");
        _reservation = new(this);
        _record.CaptureCount++; _record.PollCount++; _record.ReservationOutstanding = true;
        return _reservation;
    }

    /// <summary>Pin a hard-valid returned header before age; never roll back accepted source or release barriers.</summary>
    internal void ValidateHeader(GameCaptureSourceInfo? source, int width, int height, CancellationToken ct)
    {
        var now = ReadClock(ct);
        if (NavigationBaselineRecovery.HardSourceRejection(source, now, SeenSource) is { } error)
            throw new InvalidOperationException(error);
        if (SeenSource is { } previous && source!.SourceTimestamp100ns == previous.SourceTimestamp100ns
            && source.AcquiredAtStopwatchTicks != previous.AcquiredAtStopwatchTicks)
            throw new InvalidOperationException("native_source_regressed");
        if (width != _width || height != _height) throw new InvalidOperationException("native_frame_geometry_changed");
        NavigationBaselineRecovery.EnsureWindow(now, _record.DeadlineAtMs, _record.CaptureCount);
        _record.SeenSource = source;
    }

    /// <summary>Check metadata, hard target/cancellation and the original deadline before refunding unpublished work.</summary>
    private void CompletePending(CaptureReservation reservation, GameCapturePendingReadback pending,
        long nowTicks, Action checkAvailable, CancellationToken ct)
    {
        RequireActive(reservation);
        GameCaptureReadbackConsumer.ValidatePending(pending, nowTicks, SeenSource, width: _width, height: _height);
        checkAvailable();
        Check(ct);
        Settle(reservation, true);
    }

    /// <summary>Reference ownership, not equal values or a later reservation, controls every settlement.</summary>
    private void RequireActive(CaptureReservation reservation)
    {
        if (_closed || !ReferenceEquals(_reservation, reservation) || reservation.Settled)
            throw new InvalidOperationException("recovery_capture_already_settled");
    }

    /// <summary>Ready/null/native errors and cleanup failures retain the original charge.</summary>
    private void Settle(CaptureReservation reservation, bool pending)
    {
        RequireActive(reservation);
        if (pending) { _record.CaptureCount--; _record.PendingPollCount++; }
        reservation.Settled = true; _reservation = null; _record.ReservationOutstanding = false;
    }

    /// <summary>Final cleanup keeps any unfinished setup charged and rejects later use; no input/timer is touched.</summary>
    internal void Close()
    {
        if (_closed) return;
        _reservation?.Dispose();
        _closed = true;
    }

    /// <summary>Exactly one call's conservative unit, disposed before the enclosing recovery ends.</summary>
    internal sealed class CaptureReservation(NavigationBaselineRecoveryReadbackBudget owner) : IDisposable
    {
        /// <summary>One-way settlement, including an exceptional scope exit.</summary>
        internal bool Settled { get; set; }
        /// <summary>Normal/exceptional pixel paths preserve the charge without adding a timing allowance.</summary>
        internal void CompleteCapture() => owner.Settle(this, false);
        /// <summary>Only native-validated metadata with current target/deadline evidence can refund this unit.</summary>
        internal void CompletePending(GameCapturePendingReadback pending, long nowTicks,
            Action checkAvailable, CancellationToken ct) => owner.CompletePending(this, pending, nowTicks, checkAvailable, ct);
        /// <summary>Idempotent disposal handles setup failures before a poll row/capture was constructed.</summary>
        public void Dispose() { if (!Settled) CompleteCapture(); }
    }
}
