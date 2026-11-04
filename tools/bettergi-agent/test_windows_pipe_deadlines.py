"""Controlled local test pipes only: no BetterGI, RDP, game or input controller."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

import bridge_transport
import stream_client
from windows_pipe_transport import WindowsPipe


def packet(value, payload=b''):
    """Encode synthetic packets without granting any live input authority."""
    encoded = json.dumps(value).encode()
    return struct.pack('<I', len(encoded)) + encoded + payload


def hello():
    """Offer an observation-only fake owner identity."""
    return dict(version=1, type='hello', sessionId='synthetic', ownerEpoch='synthetic',
                goalVersion=1, inputEnabled=False, allowedKeys=[])


class SyntheticServer:
    """Own a unique nonblocking, local-only byte-pipe server with bounded calls."""
    def __init__(self):
        self.name = 'BetterGI.Agent.deadline-test-' + uuid.uuid4().hex
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateNamedPipeW': (wintypes.HANDLE, [wintypes.LPCWSTR, wintypes.DWORD,
                wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                wintypes.DWORD, wintypes.LPVOID]),
            'ConnectNamedPipe': (wintypes.BOOL, [wintypes.HANDLE, wintypes.LPVOID]),
            'DisconnectNamedPipe': (wintypes.BOOL, [wintypes.HANDLE]),
            'CloseHandle': (wintypes.BOOL, [wintypes.HANDLE]),
            'ReadFile': (wintypes.BOOL, [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]),
            'WriteFile': (wintypes.BOOL, [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]),
        }
        for key, (result, arguments) in signatures.items():
            method = getattr(self.api, key)
            method.restype, method.argtypes = result, arguments
        self.handle = self.api.CreateNamedPipeW('\\\\.\\pipe\\' + self.name,
            3 | 0x00080000, 1 | 8, 1, 4096, 4096, 0, None)
        if self.handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        self.closed = False
        self.api.ConnectNamedPipe(self.handle, None)

    def connect(self, *, timeout=0.12, greeting=None):
        """Connect only this fixture endpoint and optionally send a synthetic hello."""
        pipe = WindowsPipe(self.name, timeout=timeout)
        try:
            self.api.ConnectNamedPipe(self.handle, None)
            if greeting is not None:
                self.write(greeting)
            return pipe
        except BaseException:
            pipe.close()
            raise

    def write(self, data):
        """Write a small synthetic reply under a finite fixture deadline."""
        deadline = time.monotonic() + 2
        while data:
            buffer = ctypes.create_string_buffer(data)
            count = wintypes.DWORD()
            ok = self.api.WriteFile(self.handle, buffer, len(data), ctypes.byref(count), None)
            if not ok and ctypes.get_last_error() != 232:
                raise ctypes.WinError(ctypes.get_last_error())
            if time.monotonic() >= deadline:
                raise TimeoutError('Synthetic server write timeout')
            data = data[count.value:]
            if not count.value:
                time.sleep(.002)

    def read(self, size=65536):
        """Read only currently available synthetic client bytes."""
        buffer = ctypes.create_string_buffer(size)
        count = wintypes.DWORD()
        ok = self.api.ReadFile(self.handle, buffer, size, ctypes.byref(count), None)
        if not ok and ctypes.get_last_error() != 232:
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw[:count.value]

    def close(self):
        """Close this server handle exactly once without joining any native worker."""
        if not self.closed:
            self.closed = True
            self.api.DisconnectNamedPipe(self.handle)
            self.api.CloseHandle(self.handle)


@unittest.skipUnless(os.name == 'nt', 'Controlled Windows pipe tests')
class WindowsDeadlineTests(unittest.TestCase):
    """Exercise the actual Windows transport, packet framing and retirement."""
    def setUp(self):
        self.server = SyntheticServer()
        self.addCleanup(self.server.close)
        self.pipes = []

    def connect(self, greeting=None, timeout=.12):
        pipe = self.server.connect(timeout=timeout, greeting=greeting)
        self.pipes.append(pipe)
        self.addCleanup(pipe.close)
        return pipe

    def bridge(self):
        return stream_client.Bridge(self.server.name,
            transport_factory=lambda _: self.connect(packet(hello())))

    def assert_terminal(self, pipe, operation):
        """Require bounded failure, no reconnect authority, and descriptor retirement."""
        start = time.monotonic()
        with self.assertRaises(TimeoutError) as caught:
            operation()
        self.assertLess(time.monotonic() - start, 1)
        self.assertFalse(bridge_transport.is_transport_failure(caught.exception))
        self.assertTrue(pipe.closed)
        with self.assertRaises(TimeoutError):
            pipe.write(b'no-reuse')
        return caught.exception

    def test_handshake_header_stall_closes_original_handle(self):
        pipe = self.connect()
        self.assert_terminal(pipe, lambda: stream_client.Bridge(self.server.name,
            transport_factory=lambda _: pipe))

    def test_header_and_payload_stalls_retire_without_reconnect(self):
        for response in (b'', b'\x10', packet({'type': 'frame', 'payloadBytes': 12}, b'ab')):
            with self.subTest(response=response):
                self.server.close()
                self.server = SyntheticServer()
                self.addCleanup(self.server.close)
                bridge = self.bridge()
                if response:
                    self.server.write(response)
                error = self.assert_terminal(bridge.handle, lambda: bridge.request('frame'))
                self.assertEqual(bridge_transport.transport_origin(error), 'read')

    def test_partial_and_zero_write_backpressure_has_one_deadline(self):
        pipe = self.connect()
        with pipe.transaction(threading.Lock()):
            first = pipe.write(b'x' * 65536)
            self.assertGreater(first, 0)
            self.assertLess(first, 65536)
            original = pipe.api.WriteFile
            outcomes = []
            def observed(*arguments):
                result = original(*arguments)
                outcomes.append((bool(result), arguments[3]._obj.value))
                return result
            with patch.object(pipe.api, 'WriteFile', side_effect=observed):
                self.assert_terminal(pipe, lambda: pipe.write(b'y' * 65536))
            self.assertIn((True, 0), outcomes)
        self.assertGreater(pipe.poll_waits, 0)

    def test_bridge_write_stall_is_terminal_uncertainty(self):
        bridge = self.bridge()
        error = self.assert_terminal(bridge.handle,
            lambda: bridge.request('status', syntheticPadding='x' * 60000))
        self.assertEqual(bridge_transport.transport_origin(error), 'write')

    def test_no_data_is_not_eof_and_disconnect_is_not_timeout(self):
        pipe = self.connect(timeout=1)
        result = []
        reader = threading.Thread(target=lambda: result.append(pipe.read(3)))
        reader.start()
        try:
            time.sleep(.04)
            self.assertTrue(reader.is_alive())
            self.server.write(b'abc')
        finally:
            reader.join(1)
            if reader.is_alive():
                pipe.cancel()
                reader.join(1)
        self.assertFalse(reader.is_alive())
        self.assertEqual(result, [b'abc'])
        self.server.close()
        with self.assertRaises(OSError) as caught:
            pipe.read(1)
        self.assertNotIsInstance(caught.exception, TimeoutError)

    def test_cancel_wakes_reader_and_preserves_terminal_error(self):
        pipe = self.connect(timeout=2)
        result = []
        def read():
            try:
                pipe.read(1)
            except BaseException as error:
                result.append(error)
        reader = threading.Thread(target=read)
        reader.start()
        try:
            time.sleep(.02)
            error = pipe.cancel()
        finally:
            pipe.close()
            reader.join(1)
        self.assertFalse(reader.is_alive())
        self.assertEqual(result, [error])
        self.assertFalse(bridge_transport.is_transport_failure(error))

    def test_transaction_lock_timeout_is_terminal(self):
        bridge = self.bridge()
        bridge.lock.acquire()
        try:
            self.assert_terminal(bridge.handle, lambda: bridge.request('status'))
        finally:
            bridge.lock.release()

    def test_stalled_reader_releases_intake_for_teardown(self):
        bridge = self.bridge()
        intake = threading.RLock()
        entered, finished = threading.Event(), threading.Event()
        errors = []
        def reader():
            with intake:
                entered.set()
                try:
                    bridge.request('frame')
                except BaseException as error:
                    errors.append(error)
        thread = threading.Thread(target=reader)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            start = time.monotonic()
            with intake:
                with self.assertRaises(TimeoutError):
                    bridge.request('release')
                finished.set()
            self.assertLess(time.monotonic() - start, 1)
        finally:
            bridge.handle.close()
            thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertTrue(finished.is_set())
        self.assertEqual(len(errors), 1)
        self.assertFalse(bridge_transport.is_transport_failure(errors[0]))

    def test_clean_release_acknowledgement_is_preserved(self):
        bridge = self.bridge()
        reply = {'type': 'released', 'releasedAtMs': 1, 'receipts': []}
        self.server.write(packet(reply))
        self.assertEqual(bridge.request('release'), (reply, b''))
        self.assertFalse(bridge.handle.closed)
        request = self.server.read()
        self.assertEqual(json.loads(request[4:])['command'], 'release')

    def test_reply_progress_resets_per_transaction_and_ignores_writes(self):
        pipe = self.connect(timeout=.04)
        lock = threading.Lock()
        self.server.write(b'a')
        with pipe.transaction(lock):
            self.assertEqual(pipe.read(1), b'a')
            self.assertTrue(pipe._reply_progress)
        with pipe.transaction(lock):
            self.assertFalse(pipe._reply_progress)
            pipe.write(b'request-bytes')
            self.assertFalse(pipe._reply_progress)
            sleeps = []
            original = time.sleep
            def sleep(delay):
                sleeps.append(delay)
                original(delay)
            with patch('windows_pipe_transport.time.sleep', side_effect=sleep):
                with self.assertRaises(TimeoutError):
                    pipe.read(1)
            self.assertAlmostEqual(sleeps[0], .002)

    def test_partial_reply_empty_reads_back_off_without_extending_deadline(self):
        pipe = self.connect(timeout=.04)
        self.server.write(b'a')
        sleeps = []
        original = time.sleep
        def sleep(delay):
            sleeps.append(delay)
            original(delay)
        start = time.perf_counter()
        with pipe.transaction(threading.Lock()):
            self.assertEqual(pipe.read(1), b'a')
            with patch('windows_pipe_transport.time.sleep', side_effect=sleep):
                with self.assertRaises(TimeoutError):
                    pipe.read(1)
        self.assertEqual(sleeps[:4], [.00025, .0005, .001, .002])
        self.assertLessEqual(max(sleeps), .002)
        self.assertLess(time.perf_counter() - start, .15)
        self.assertTrue(pipe.closed)

    def test_partial_transactions_disconnect_and_never_reuse_the_handle(self):
        for phase in ('header', 'payload', 'write'):
            with self.subTest(phase=phase):
                self.server.close()
                self.server = SyntheticServer()
                self.addCleanup(self.server.close)
                bridge = self.bridge()
                bridge.handle.timeout = .5
                if phase == 'header':
                    self.server.write(b'\x10\x00')
                elif phase == 'payload':
                    self.server.write(packet({'type': 'frame', 'payloadBytes': 12}, b'ab'))
                errors = []
                def request():
                    try:
                        bridge.request('status', **({'syntheticPadding': 'x'*60000} if phase == 'write' else {}))
                    except BaseException as error:
                        errors.append(error)
                thread = threading.Thread(target=request)
                thread.start()
                try:
                    deadline = time.perf_counter() + 1
                    while bridge.handle.poll_waits == 0 and time.perf_counter() < deadline:
                        time.sleep(.001)
                    self.assertGreater(bridge.handle.poll_waits, 0)
                    if phase == 'write':
                        consumed = self.server.read()
                        self.assertGreater(len(consumed), 0)
                        self.assertLess(len(consumed), 60000)
                    self.server.close()
                    thread.join(1)
                finally:
                    bridge.handle.close()
                    thread.join(1)
                self.assertFalse(thread.is_alive())
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], OSError)
                self.assertTrue(bridge.handle.closed)
                with self.assertRaises(OSError) as repeated:
                    bridge.request('status')
                self.assertIs(repeated.exception, errors[0])
                # Ordinary disconnect keeps its existing classification; timeouts
                # are stricter. Action uncertainty is separately vetoed by the owner.
                self.assertEqual(bridge_transport.is_transport_failure(errors[0]),
                                 not isinstance(errors[0], TimeoutError))

    def test_cancellation_wakes_a_queued_transaction_without_unlocking_owner(self):
        bridge = self.bridge()
        bridge.handle.timeout = 2
        bridge.lock.acquire()
        errors = []
        def request():
            try:
                bridge.request('status')
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=request)
        thread.start()
        try:
            time.sleep(.02)
            failure = bridge.handle.cancel()
            thread.join(1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [failure])
        finally:
            bridge.lock.release()
            bridge.handle.close()
            thread.join(1)

    def test_close_failure_keeps_uncertainty_and_allows_cleanup_retry(self):
        pipe = self.connect()
        descriptor = pipe.fileno()
        with patch('windows_pipe_transport.os.close', side_effect=OSError('synthetic close failure')):
            failure = pipe.cancel()
        self.assertFalse(pipe.closed)
        self.assertFalse(bridge_transport.is_transport_failure(failure))
        self.assertIn('synthetic close failure', failure.__notes__[0])
        with self.assertRaises(TimeoutError):
            pipe.read(1)
        pipe.close()
        self.assertTrue(pipe.closed)
        with self.assertRaises(OSError):
            os.fstat(descriptor)

    def test_malformed_reply_retires_without_reusing_consumed_stream(self):
        bridge = self.bridge()
        self.server.write(struct.pack('<I', 1) + b'{')
        with self.assertRaises(json.JSONDecodeError) as caught:
            bridge.request('status')
        self.assertTrue(bridge.handle.closed)
        with self.assertRaises(json.JSONDecodeError) as repeated:
            bridge.request('release')
        self.assertIs(caught.exception, repeated.exception)
        self.assertFalse(bridge_transport.is_transport_failure(caught.exception))

    def test_original_descriptor_supports_peer_identity_and_closes(self):
        import msvcrt
        pipe = self.connect()
        descriptor = pipe.fileno()
        self.assertEqual(msvcrt.get_osfhandle(descriptor), pipe._handle)
        self.assertFalse(os.get_inheritable(descriptor))
        pipe.close()
        with self.assertRaises(OSError):
            os.fstat(descriptor)

    def test_fragmented_write_is_complete_when_server_drains(self):
        pipe = self.connect(timeout=2)
        payload = bytes(range(256)) * 256
        received = bytearray()
        failures = []
        stop = threading.Event()
        def drain():
            try:
                deadline = time.monotonic() + 2
                while len(received) < len(payload) and not stop.is_set():
                    received.extend(self.server.read())
                    if time.monotonic() > deadline:
                        raise TimeoutError('Synthetic drain deadline')
                    stop.wait(.001)
            except BaseException as error:
                failures.append(error)
        thread = threading.Thread(target=drain)
        thread.start()
        try:
            with pipe.transaction(threading.Lock()):
                remaining = memoryview(payload)
                while remaining:
                    remaining = remaining[pipe.write(remaining):]
            thread.join(2)
        finally:
            stop.set()
            thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(received, payload)

    def test_deadline_is_shared_across_fragments_not_renewed_per_read(self):
        pipe = self.connect(timeout=.08)
        self.server.write(b'ab')
        start = time.monotonic()
        with pipe.transaction(threading.Lock()):
            self.assertEqual(pipe.read(1), b'a')
            time.sleep(.055)
            self.assertEqual(pipe.read(1), b'b')
            with self.assertRaises(TimeoutError):
                pipe.read(1)
        self.assertLess(time.monotonic() - start, .13)
        self.assertTrue(pipe.closed)

    def test_observe_episode_stall_writes_failure_report_and_closes(self):
        bridge = self.bridge()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'report.json'
            args = stream_client.parse_arguments(['--seconds', '.05', '--fps', '100', '--output', str(target)])
            with patch.object(stream_client, 'Bridge', return_value=bridge):
                with self.assertRaises(TimeoutError):
                    stream_client.run_episode(args)
            report = json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['episodeFailure']['type'], 'TimeoutError')
            self.assertNotIn('stop', report)
            self.assertTrue(bridge.handle.closed)
            self.assertFalse(report['inputRequested'])


if __name__ == '__main__':
    unittest.main()
