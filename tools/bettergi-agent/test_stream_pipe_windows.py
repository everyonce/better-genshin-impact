"""Real Windows pipe + observe CLI + FFmpeg smoke; all frames/receipts are synthetic."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid


class SyntheticPipeServer:
    """Serve only synthetic frames and stop; this fixture cannot execute game inputs."""
    def __init__(self):
        self.name = 'BetterGI.Agent.test-' + uuid.uuid4().hex
        self.identity = dict(version=1, sessionId='synthetic-session', ownerEpoch=uuid.uuid4().hex, goalVersion=1)
        self.requests = []
        self.failure = None
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateNamedPipeW': (wintypes.HANDLE, [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID]),
            'ConnectNamedPipe': (wintypes.BOOL, [wintypes.HANDLE, wintypes.LPVOID]),
            'ReadFile': (wintypes.BOOL, [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]),
            'WriteFile': (wintypes.BOOL, [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]),
            'FlushFileBuffers': (wintypes.BOOL, [wintypes.HANDLE]),
            'DisconnectNamedPipe': (wintypes.BOOL, [wintypes.HANDLE]),
            'CloseHandle': (wintypes.BOOL, [wintypes.HANDLE]),
        }
        for name, (restype, argtypes) in signatures.items():
            function = getattr(self.kernel, name)
            function.restype, function.argtypes = restype, argtypes
        # First-instance + local-only byte pipe. This unique test endpoint never
        # connects to BetterGI or changes its production RDP/input checks.
        self.handle = self.kernel.CreateNamedPipeW('\\\\.\\pipe\\' + self.name,
            3 | 0x00080000, 0x00000008, 1, 65536, 65536, 0, None)
        if self.handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        self.worker = threading.Thread(target=self._serve, daemon=True)
        self.worker.start()

    def _exact(self, size):
        """Read the client packet across native byte-pipe boundaries."""
        result = bytearray()
        while len(result) < size:
            buffer = ctypes.create_string_buffer(size - len(result))
            count = wintypes.DWORD()
            if not self.kernel.ReadFile(self.handle, buffer, len(buffer), ctypes.byref(count), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if not count.value:
                raise EOFError('Synthetic client disconnected')
            result.extend(buffer.raw[:count.value])
        return bytes(result)

    def _send(self, message, pixels=b''):
        """Fragment a real native pipe reply, including its JSON and RGB payload."""
        header = json.dumps(dict(message, payloadBytes=len(pixels))).encode()
        data = struct.pack('<I', len(header)) + header + pixels
        offset = 0
        while offset < len(data):
            chunk = data[offset:offset + 4096]
            buffer = ctypes.create_string_buffer(chunk)
            count = wintypes.DWORD()
            if not self.kernel.WriteFile(self.handle, buffer, len(chunk), ctypes.byref(count), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if not count.value:
                raise EOFError('Synthetic client stopped reading')
            offset += count.value

    @staticmethod
    def _receipt(request_id, stamp):
        """Mark generated receipt fixtures so they cannot be confused with gameplay."""
        return dict(requestId=request_id, modelId='synthetic', frameId=1, status='completed', reason=None,
                    acceptedAtMs=stamp, endedAtMs=stamp + 1, synthetic=True,
                    appliedSteps=[dict(index=0, startedAtMs=stamp, keys=[], mouseDx=0, mouseDy=0)])

    def _serve(self):
        """Exercise the production client's protocol with no production server dependency."""
        try:
            if not self.kernel.ConnectNamedPipe(self.handle, None) and ctypes.get_last_error() != 535:
                raise ctypes.WinError(ctypes.get_last_error())
            start = time.perf_counter()
            self._send(dict(self.identity, type='hello', inputEnabled=False, allowedKeys=[], synthetic=True,
                            clock='synthetic-monotonic-ms', clockFrequency=1000,
                            captureTimestampKind='synthetic-generated-frame'))
            frame_id = 0
            while True:
                size = struct.unpack('<I', self._exact(4))[0]
                if not 0 < size <= 65536:
                    raise ValueError('Invalid client packet size')
                request = json.loads(self._exact(size))
                if any(request.get(key) != value for key, value in self.identity.items()):
                    raise ValueError('Client omitted protocol version or session identity')
                self.requests.append(request)
                stamp = (time.perf_counter() - start) * 1000
                if request['command'] == 'stop':
                    self._send(dict(type='stopped', receipts=[self._receipt('synthetic-final-stop', stamp)],
                                    droppedReceipts=0))
                    self.kernel.FlushFileBuffers(self.handle)
                    break
                if request['command'] != 'frame':
                    raise ValueError('Synthetic observation fixture refuses action commands')
                frame_id += 1
                pixels = bytes([frame_id % 256, 64, 128]) * (64 * 48)
                self._send(dict(type='frame', frameId=frame_id, width=64, height=48, pixelFormat='rgb24',
                    sourceWidth=64, sourceHeight=48, capturedAtMs=stamp, serverNowMs=stamp,
                    captureMs=0, inputAvailable=False, synthetic=True, droppedReceipts=0,
                    receipts=[self._receipt('synthetic-earlier-step', stamp)] if frame_id == 2 else []), pixels)
        except Exception as exc:
            self.failure = repr(exc)
        finally:
            self.kernel.DisconnectNamedPipe(self.handle)

    def close(self):
        """Bound fixture shutdown even if the subprocess failed before connecting."""
        self.worker.join(timeout=2)
        self.kernel.CloseHandle(self.handle)
        self.worker.join(timeout=1)


def run_smoke(directory, ffmpeg, ffprobe):
    """Run the actual observe CLI and keep its report, recording, and validation evidence."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    server = SyntheticPipeServer()
    try:
        command = [sys.executable, str(Path(__file__).with_name('stream_client.py')), '--pipe', server.name,
                   '--seconds', '.4', '--fps', '30', '--model', 'observe', '--record-dir', str(root / 'episode'),
                   '--ffmpeg', ffmpeg, '--record-max-mib', '4', '--output', str(root / 'client-report.json')]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        if completed.returncode:
            raise AssertionError(f'Observe CLI failed {completed.returncode}: {completed.stdout}\n{completed.stderr}')
    finally:
        server.close()
    if server.failure or server.worker.is_alive():
        raise AssertionError(f'Synthetic pipe server failed: {server.failure}')
    report = json.loads((root / 'client-report.json').read_text())
    rows = [json.loads(line) for line in (root / 'episode/frames.jsonl').read_text().splitlines()]
    events = [json.loads(line) for line in (root / 'episode/events.jsonl').read_text().splitlines()]
    probe = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-count_frames',
        '-show_entries', 'stream=nb_read_frames,width,height', '-of', 'json', str(root / 'episode/frames.mp4')],
        capture_output=True, check=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    result = dict(synthetic=True, realWindowsNamedPipe=True, productionRdpRuntimeExercised=False,
                  gameInputSent=False, gpuInferencePerformed=False, clientReturnCode=completed.returncode,
                  commands=[item['command'] for item in server.requests], recording=report['recording'],
                  receivedFrames=report['framesReceived'], sidecarFrames=len(rows),
                  receipts=[item.get('requestId') for item in events if 'requestId' in item],
                  ffprobe=json.loads(probe.stdout))
    (root / 'smoke-validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result, report, rows


@unittest.skipUnless(os.name == 'nt', 'Windows named pipe integration')
class WindowsPipeTests(unittest.TestCase):
    def test_real_pipe_observe_cli_records_rgb_and_final_receipts(self):
        ffmpeg = shutil.which('ffmpeg') or 'C:/programs/ffmpeg.exe'
        ffprobe = shutil.which('ffprobe') or 'C:/programs/ffprobe.exe'
        if not Path(ffmpeg).exists() or not Path(ffprobe).exists():
            self.skipTest('FFmpeg and ffprobe required')
        with tempfile.TemporaryDirectory() as directory:
            result, report, rows = run_smoke(directory, ffmpeg, ffprobe)
            self.assertTrue(report['hello']['synthetic'])
            self.assertFalse(report['inputRequested'])
            self.assertEqual(report['decisions'], [])
            self.assertGreaterEqual(result['receivedFrames'], 2)
            self.assertEqual(result['commands'][-1], 'stop')
            self.assertEqual(set(result['commands']), {'frame', 'stop'})
            self.assertIsNone(result['recording']['error'])
            self.assertEqual(result['recording']['droppedFrames'], 0)
            self.assertEqual(result['recording']['droppedEvents'], 0)
            self.assertEqual(result['sidecarFrames'], result['receivedFrames'])
            self.assertEqual(int(result['ffprobe']['streams'][0]['nb_read_frames']), result['receivedFrames'])
            self.assertEqual(result['receipts'], ['synthetic-earlier-step', 'synthetic-final-stop'])
            self.assertEqual([row['videoFrameIndex'] for row in rows], list(range(len(rows))))
            self.assertTrue(all(row['synthetic'] for row in rows))


if __name__ == '__main__':
    unittest.main()
