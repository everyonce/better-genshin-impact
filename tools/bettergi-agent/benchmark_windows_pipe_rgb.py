"""640x360 synthetic RGB comparison on unique local Windows pipes, without game input."""
import ctypes
from ctypes import wintypes
import gc
import json
import os
import statistics
import struct
import time
import tracemalloc

from stream_client import Bridge
from test_stream_pipe_windows import SyntheticPipeServer
from windows_pipe_transport import WindowsPipe

RGB = bytes(range(256)) * (640 * 360 * 3 // 256)


class RgbServer(SyntheticPipeServer):
    """Use 64 KiB server buffers and the production prefix/JSON/payload write order."""
    def __init__(self, fragment_size=None):
        self.fragment_size = fragment_size
        super().__init__()

    def _send(self, value, pixels=b''):
        header = json.dumps(dict(value, payloadBytes=len(pixels))).encode()
        for data in (struct.pack('<I', len(header)), header, pixels):
            if not data:
                continue
            buffer = ctypes.create_string_buffer(data)
            offset = 0
            while offset < len(data):
                count = wintypes.DWORD()
                size = min(len(data)-offset, self.fragment_size or len(data))
                if not self.kernel.WriteFile(self.handle, ctypes.byref(buffer, offset), size,
                                             ctypes.byref(count), None):
                    raise ctypes.WinError(ctypes.get_last_error())
                if not count.value:
                    raise EOFError('Synthetic client disconnected')
                offset += count.value

    def _serve(self):
        """Serve frame bytes only; reject actions and all other controller requests."""
        try:
            if not self.kernel.ConnectNamedPipe(self.handle, None) and ctypes.get_last_error() != 535:
                raise ctypes.WinError(ctypes.get_last_error())
            self._send(dict(self.identity, type='hello', inputEnabled=False, allowedKeys=[], synthetic=True))
            frame = 0
            while True:
                size = struct.unpack('<I', self._exact(4))[0]
                assert 0 < size <= 65536
                request = json.loads(self._exact(size))
                assert request['command'] in ('frame', 'stop')
                if request['command'] == 'stop':
                    self._send({'type': 'stopped', 'synthetic': True})
                    self.kernel.FlushFileBuffers(self.handle)
                    return
                frame += 1
                self._send(dict(type='frame', frameId=frame, width=640, height=360,
                                pixelFormat='rgb24', synthetic=True), RGB)
        except BaseException as error:
            self.failure = repr(error)
        finally:
            self.kernel.DisconnectNamedPipe(self.handle)


class ReadProbe:
    """Count requested allocation sizes and actual fragments without changing data."""
    def __init__(self, handle):
        self.handle = handle
        self.reads = []

    def transaction(self, lock):
        method = getattr(self.handle, 'transaction', None)
        return method(lock) if method is not None else lock

    def read(self, size):
        result = self.handle.read(size)
        self.reads.append((size, len(result)))
        return result

    def write(self, data):
        return self.handle.write(data)

    def close(self):
        self.handle.close()


def measure(native, count=80, traced_count=10, fragment_size=None):
    """Measure timing without tracing; trace allocations in a separate phase."""
    server = RgbServer(fragment_size)
    probes = []
    bridge = None
    def factory(name):
        handle = WindowsPipe(name, timeout=2) if native else open('\\\\.\\pipe\\'+name, 'r+b', buffering=0)
        result = ReadProbe(handle)
        probes.append(result)
        return result
    try:
        bridge = Bridge(server.name, transport_factory=factory)
        for _ in range(5):
            assert bridge.request('frame')[1] == RGB
        probe = probes[0]
        probe.reads.clear()
        times = []
        gc.collect()
        cpu_start, start = time.process_time(), time.perf_counter()
        for _ in range(count):
            before = time.perf_counter()
            response, pixels = bridge.request('frame')
            times.append((time.perf_counter()-before)*1000)
            assert response['payloadBytes'] == len(RGB) and pixels == RGB
        elapsed, cpu = time.perf_counter()-start, time.process_time()-cpu_start
        reads = list(probe.reads)
        del pixels
        probe.reads.clear()
        gc.collect()
        tracemalloc.start()
        for _ in range(traced_count):
            response, pixels = bridge.request('frame')
            assert pixels == RGB
            del pixels
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        result = dict(frames=count, rgbBytes=len(RGB), serverWriteFragmentBytes=fragment_size, medianMs=statistics.median(times),
            p95Ms=sorted(times)[int(count*.95)], totalMs=elapsed*1000, cpuMs=cpu*1000,
            tracedFrames=traced_count, peakMiB=peak/2**20, readCallsPerFrame=len(reads)/count,
            requestedReadBytesPerFrame=sum(size for size, _ in reads)/count,
            actualReadBytesPerFrame=sum(size for _, size in reads)/count,
            payloadFragmentSizes=sorted(set(size for _,size in reads if size > 1024)),
            pollWaitsAcrossAllPhases=getattr(probe.handle, 'poll_waits', None))
        bridge.request('stop')
        return result
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        for probe in probes:
            probe.close()
        server.close()
        assert not server.worker.is_alive(), 'Synthetic RGB server did not retire'
        assert server.failure is None, server.failure


def main():
    """Compare only controlled endpoints; all frame bytes are generated in memory."""
    assert os.name == 'nt'
    print(json.dumps(dict(scope='synthetic RGB only; blocking server writes, 64 KiB buffers; no game/model',
                         legacy=measure(False), bounded=measure(True),
                         fragmented4096=dict(legacy=measure(False, fragment_size=4096),
                                             bounded=measure(True, fragment_size=4096))), indent=2))


if __name__ == '__main__':
    main()
