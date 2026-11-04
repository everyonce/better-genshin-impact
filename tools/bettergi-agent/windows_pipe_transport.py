"""Deadline-bound Windows byte-pipe I/O without background I/O threads.

PIPE_NOWAIT makes each native call synchronous but nonblocking. Short sleeps
between empty reads/full writes check cancellation; a transaction shares one deadline
across its lock, header, and payload. No outstanding OVERLAPPED buffer can outlive
an exception. This module neither changes server authority nor retries a lease.
"""
from contextlib import contextmanager
import math
import os
import threading
import time

from bridge_transport import forbid_reconnect

DEFAULT_TIMEOUT = 10.0
POLL_SECONDS = 0.002
FRAGMENT_POLL_SECONDS = 0.00025


def terminal_timeout(message):
    """Timeout leaves the reply/action outcome uncertain, never reconnectable."""
    error = TimeoutError(message)
    forbid_reconnect(error, 'pipeDeadlineOrCancellation')
    return error


class WindowsPipe:
    """Own one original nonblocking pipe handle and its CRT identity descriptor."""
    def __init__(self, name, *, timeout=DEFAULT_TIMEOUT):
        if os.name != 'nt':
            raise RuntimeError('Windows named pipes require Windows')
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Pipe timeout must be finite and positive')
        import ctypes
        from ctypes import wintypes
        import msvcrt
        self.ctypes = ctypes
        self.timeout = timeout
        self._deadline = None
        self._state_lock = threading.Lock()
        self._cancelled = threading.Event()
        self._failure = None
        self._fd = None
        self.closed = False
        self.poll_waits = 0
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateFileW': (wintypes.HANDLE, [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]),
            'SetNamedPipeHandleState': (wintypes.BOOL, [wintypes.HANDLE,
                ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID, wintypes.LPVOID]),
            'GetNamedPipeInfo': (wintypes.BOOL, [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
                ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]),
            'ReadFile': (wintypes.BOOL, [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]),
            'WriteFile': (wintypes.BOOL, [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]),
            'CloseHandle': (wintypes.BOOL, [wintypes.HANDLE]),
        }
        for key, (result, arguments) in signatures.items():
            function = getattr(self.api, key)
            function.restype, function.argtypes = result, arguments
        handle = self.api.CreateFileW('\\\\.\\pipe\\' + name, 0xC0000000, 0, None, 3, 0, None)
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            # Byte-read mode (0) plus PIPE_NOWAIT (1); no protocol or server change.
            mode = wintypes.DWORD(1)
            if not self.api.SetNamedPipeHandleState(handle, ctypes.byref(mode), None, None):
                raise ctypes.WinError(ctypes.get_last_error())
            inbound = wintypes.DWORD()
            if not self.api.GetNamedPipeInfo(handle, None, None, ctypes.byref(inbound), None):
                raise ctypes.WinError(ctypes.get_last_error())
            # NOWAIT can return zero for an oversized write even on an empty pipe.
            # Server inbound capacity is the client's write quota; fragment below it.
            self._write_chunk = min(4096, inbound.value or 4096)
            self._fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        except BaseException:
            self.api.CloseHandle(handle)
            raise
        self._handle = handle

    def fileno(self):
        """Preserve existing same-user/server-PID verification on the owned handle."""
        with self._state_lock:
            self._check()
            return self._fd

    def _check(self):
        """Reject retired handles before issuing any further native operation."""
        if self._failure is not None:
            raise self._failure
        if self.closed:
            raise terminal_timeout('Agent pipe is closed; release outcome is not acknowledged')

    def cancel(self, reason='Agent pipe cancelled; release outcome is uncertain'):
        """Wake waiters and retire the original handle without acquiring the RPC lock."""
        with self._state_lock:
            if self._failure is None:
                self._failure = terminal_timeout(reason)
            failure = self._failure
            try:
                self._close_locked()
            except OSError as cleanup:
                failure.add_note('Pipe retirement failed: ' + str(cleanup))
        return failure

    def _close_locked(self):
        """Close once; native NOWAIT calls cannot leave pending buffer ownership."""
        self._cancelled.set()
        if not self.closed:
            if self._fd is not None:
                os.close(self._fd)
            self._fd = None
            self.closed = True

    def close(self):
        """Release the descriptor and wake any read/write waiter, idempotently."""
        with self._state_lock:
            self._close_locked()

    @contextmanager
    def transaction(self, lock):
        """One budget covers queueing for the serialized connection and all bytes."""
        deadline = time.perf_counter() + self.timeout
        acquired = False
        try:
            # Poll the mutex with an event-sized wait so cancellation also wakes
            # transactions queued behind a stalled original reader.
            while not acquired:
                with self._state_lock:
                    self._check()
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    raise self.cancel('Agent pipe transaction lock deadline exceeded; outcome is uncertain')
                acquired = lock.acquire(timeout=min(POLL_SECONDS, remaining))
            with self._state_lock:
                self._check()
                self._deadline = deadline
                self._transaction_touched = False
                self._reply_progress = False
            yield
        except BaseException as error:
            if acquired and getattr(self, '_transaction_touched', False):
                # A partially consumed/written frame cannot start another RPC on
                # this byte stream. Preserve the original exception and its veto.
                with self._state_lock:
                    if self._failure is None:
                        self._failure = error
                    try:
                        self._close_locked()
                    except OSError as cleanup:
                        error.add_note('Pipe retirement failed: ' + str(cleanup))
            raise
        finally:
            if acquired:
                self._deadline = None
                lock.release()

    def _transfer(self, size, data=None):
        """Read some available bytes or write some capacity, with bounded waiting."""
        ctypes = self.ctypes
        from ctypes import wintypes
        if type(size) is not int or size <= 0 or size > 32 * 1024 * 1024:
            raise ValueError('Invalid pipe transfer size')
        buffer = ctypes.create_string_buffer(size) if data is None else ctypes.create_string_buffer(bytes(data), size)
        count = wintypes.DWORD()
        deadline = self._deadline if self._deadline is not None else time.perf_counter() + self.timeout
        retry_delay = (FRAGMENT_POLL_SECONDS if data is None and getattr(self, '_reply_progress', False)
                       else POLL_SECONDS)
        while True:
            if time.perf_counter() >= deadline:
                raise self.cancel('Agent pipe I/O deadline exceeded; release/action outcome is uncertain')
            with self._state_lock:
                self._check()
                self._transaction_touched = True
                operation = self.api.ReadFile if data is None else self.api.WriteFile
                ok = operation(self._handle, buffer, size, ctypes.byref(count), None)
                error = 0 if ok else ctypes.get_last_error()
            if ok and count.value:
                if data is None:
                    self._reply_progress = True
                return ctypes.string_at(buffer, count.value) if data is None else count.value
            if not ok and error != 232:  # ERROR_NO_DATA is temporary only on NOWAIT pipes.
                raise ctypes.WinError(error)
            # A NOWAIT byte write can succeed with zero bytes when the buffer is full.
            # It is backpressure, not EOF. Actual disconnection is ERROR_BROKEN_PIPE.
            self.poll_waits += 1
            # Python 3.11+ uses a high-resolution Windows timer for sleep;
            # Event.wait can round 2 ms up to the 15.6 ms scheduler tick.
            # Cancellation is checked at most one short sleep later.
            # Once a reply is flowing, briefly favor its next fragment. Back off
            # after repeated empty reads so a stalled partial packet cannot spin.
            if not self._cancelled.is_set():
                time.sleep(min(retry_delay, max(0, deadline - time.perf_counter())))
            retry_delay = min(POLL_SECONDS, retry_delay * 2)

    def read(self, size):
        """Return a bounded byte fragment, preserving native broken-pipe errors."""
        return self._transfer(size)

    def write(self, data):
        """Return short writes to Bridge's existing exact packet write loop."""
        fragment = memoryview(data)[:self._write_chunk]
        return self._transfer(len(fragment), fragment)
