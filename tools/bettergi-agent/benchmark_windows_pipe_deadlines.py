"""Synthetic local-only latency/CPU benchmark; never connects to BetterGI or a game."""
import json
import os
import statistics
import struct
import threading
import time

from stream_client import Bridge
from test_windows_pipe_deadlines import SyntheticServer, hello, packet
from windows_pipe_transport import WindowsPipe, POLL_SECONDS


def round_trips(native, count=200):
    """Compare current and legacy handle reads using identical synthetic replies."""
    server = SyntheticServer()
    handles = []
    stop = threading.Event()
    errors = []
    def factory(name):
        handle = WindowsPipe(name, timeout=2) if native else open('\\\\.\\pipe\\' + name, 'r+b', buffering=0)
        handles.append(handle)
        server.api.ConnectNamedPipe(server.handle, None)
        server.write(packet(hello()))
        return handle
    bridge = None
    worker = None
    def serve():
        pending = bytearray()
        deadline = time.monotonic() + 10
        try:
            while not stop.is_set() and time.monotonic() < deadline:
                pending.extend(server.read())
                while len(pending) >= 4:
                    length = struct.unpack('<I', pending[:4])[0]
                    if len(pending) < length + 4:
                        break
                    request = json.loads(pending[4:4 + length])
                    del pending[:4 + length]
                    assert request['command'] == 'status'
                    server.write(packet({'type': 'status', 'synthetic': True}))
                time.sleep(.0005)
        except BaseException as error:
            errors.append(type(error).__name__)
        finally:
            server.close()
    try:
        bridge = Bridge(server.name, transport_factory=factory)
        worker = threading.Thread(target=serve)
        worker.start()
        durations = []
        cpu_start, start = time.process_time(), time.perf_counter()
        for _ in range(count):
            before = time.perf_counter()
            assert bridge.request('status')[0]['synthetic']
            durations.append((time.perf_counter() - before) * 1000)
        elapsed, cpu = time.perf_counter() - start, time.process_time() - cpu_start
        return dict(requests=count, elapsedMs=elapsed*1000, cpuMs=cpu*1000,
                    medianRpcMs=statistics.median(durations), p95RpcMs=sorted(durations)[int(count*.95)],
                    pollWaits=getattr(bridge.handle, 'poll_waits', None))
    finally:
        stop.set()
        if worker is not None:
            worker.join(2)
            assert not worker.is_alive(), 'Synthetic benchmark worker did not retire'
        for handle in handles:
            handle.close()
        server.close()
        assert not errors, errors


def idle_wait(partial_reply=False):
    """Measure bounded idle waiting rather than a CPU-spinning no-data loop."""
    server = SyntheticServer()
    pipe = server.connect(timeout=2)
    if partial_reply:
        server.write(b'a')
        assert pipe.read(1) == b'a'
    cpu_start, start = time.process_time(), time.perf_counter()
    try:
        try:
            pipe.read(1)
        except TimeoutError:
            pass
        else:
            raise AssertionError('Expected an empty synthetic pipe timeout')
        elapsed, cpu = time.perf_counter() - start, time.process_time() - cpu_start
        return dict(elapsedMs=elapsed*1000, cpuMs=cpu*1000, pollWaits=pipe.poll_waits,
                    pollWaitsPerSecond=pipe.poll_waits/elapsed, closed=pipe.closed)
    finally:
        pipe.close()
        server.close()


def cancellation_samples(count=30):
    """Measure cancellation to reader retirement, not a real-time scheduler guarantee."""
    times = []
    for _ in range(count):
        server = SyntheticServer()
        pipe = server.connect(timeout=2)
        failures = []
        entered = threading.Event()
        def read():
            entered.set()
            try:
                pipe.read(1)
            except TimeoutError:
                pass
            except BaseException as error:
                failures.append(type(error).__name__)
        reader = threading.Thread(target=read)
        try:
            reader.start()
            assert entered.wait(1)
            time.sleep(.005)
            start = time.perf_counter()
            pipe.cancel()
            reader.join(1)
            times.append((time.perf_counter()-start)*1000)
            assert not reader.is_alive() and not failures
        finally:
            pipe.close()
            reader.join(1)
            server.close()
    return dict(samples=count, medianMs=statistics.median(times),
                p95Ms=sorted(times)[int(count*.95)], maxObservedMs=max(times))


def main():
    """Publish measurements and scope, without any live transport endpoint."""
    assert os.name == 'nt'
    print(json.dumps(dict(scope='unique synthetic local byte pipes; no game/input/GPU',
        pollIntervalMs=POLL_SECONDS*1000, idle=idle_wait(),
        stalledPartialReply=idle_wait(True), cancellation=cancellation_samples(),
        legacy=round_trips(False), bounded=round_trips(True)), indent=2))


if __name__ == '__main__':
    main()
