"""Run one bounded ordinary command inside a verified, non-elevated RDP session."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid

MAX_JOB_BYTES = 65536
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_JOB_AGE_MS = 60000


def atomic_json(path, value):
    """Publish a complete UTF-8 result, never a partially written JSON file."""
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def local_absolute(value):
    """Require an absolute local path, excluding UNC and device namespaces."""
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('A local absolute path is required.')
    if not os.path.isabs(value) or value.startswith(('\\\\', '//')):
        raise ValueError('A local absolute path is required.')
    return Path(value)


def validate_job(job, job_id, now_ms=None):
    """Validate the finite, single-use command specification before creating a process."""
    fields = {'version', 'jobId', 'createdAtUnixMs', 'windowsSessionId', 'argv',
              'workingDirectory', 'timeoutSeconds', 'maxOutputBytes'}
    if not isinstance(job, dict) or set(job) != fields or job.get('version') != 1:
        raise ValueError('Invalid command job fields or version.')
    if job['jobId'] != job_id or str(uuid.UUID(job_id)) != job_id:
        raise ValueError('Job identity does not match the file name.')
    created = job['createdAtUnixMs']
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if type(created) is not int or not -30000 <= now_ms - created <= MAX_JOB_AGE_MS:
        raise ValueError('The command job is expired or has a future timestamp.')
    if type(job['windowsSessionId']) is not int or job['windowsSessionId'] <= 0:
        raise ValueError('A positive, explicitly pinned RDP session is required.')
    argv = job['argv']
    if (not isinstance(argv, list) or not 1 <= len(argv) <= 65
            or any(not isinstance(arg, str) or '\x00' in arg for arg in argv)):
        raise ValueError('argv must contain an executable and at most 64 literal arguments.')
    executable = local_absolute(argv[0])
    if executable.suffix.lower() != '.exe' or not executable.is_file():
        raise ValueError('The command executable must be an existing local .exe file.')
    if not local_absolute(job['workingDirectory']).is_dir():
        raise ValueError('The working directory does not exist.')
    if type(job['timeoutSeconds']) is not int or not 1 <= job['timeoutSeconds'] <= 3600:
        raise ValueError('Command timeout must be between 1 and 3600 seconds.')
    if type(job['maxOutputBytes']) is not int or not 1024 <= job['maxOutputBytes'] <= MAX_OUTPUT_BYTES:
        raise ValueError('Output limit must be between 1024 and 1048576 bytes per stream.')
    if len(subprocess.list2cmdline(argv)) > 30000:
        raise ValueError('The Windows command line is too long.')
    return job


def windows_identity():
    """Read the current process session, RDP protocol, elevation and integrity directly."""
    if os.name != 'nt':
        raise RuntimeError('The child command runner requires Windows.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    wts = ctypes.WinDLL('wtsapi32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    session = wintypes.DWORD()
    if not kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
        raise ctypes.WinError(ctypes.get_last_error())
    protocol = ctypes.c_void_p()
    count = wintypes.DWORD()
    wts.WTSQuerySessionInformationW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_int,
                                              ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    wts.WTSFreeMemory.argtypes = [ctypes.c_void_p]
    if not wts.WTSQuerySessionInformationW(None, session.value, 16, ctypes.byref(protocol), ctypes.byref(count)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        remote = count.value >= 2 and ctypes.cast(protocol, ctypes.POINTER(ctypes.c_ushort))[0] == 2
    finally:
        wts.WTSFreeMemory(protocol)
    token = wintypes.HANDLE()
    advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                          wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        elevated = wintypes.DWORD()
        size = wintypes.DWORD()
        if not advapi.GetTokenInformation(token, 20, ctypes.byref(elevated), ctypes.sizeof(elevated), ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        advapi.GetTokenInformation(token, 25, None, 0, ctypes.byref(size))
        if not size.value or size.value > 65536:
            raise RuntimeError('Could not read the process integrity level.')
        storage = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 25, storage, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = ctypes.cast(storage, ctypes.POINTER(ctypes.c_void_p))[0]
        advapi.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
        advapi.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
        advapi.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        advapi.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
        rid = advapi.GetSidSubAuthority(sid, advapi.GetSidSubAuthorityCount(sid)[0] - 1)[0]
        return {'windowsSessionId': session.value, 'remoteDesktop': remote,
                'elevated': bool(elevated.value), 'integrityRid': rid}
    finally:
        kernel.CloseHandle(token)


def require_ordinary_rdp(identity, expected_session):
    """Never run a command on the console or with an elevated/high-integrity token."""
    if identity['windowsSessionId'] != expected_session or identity['remoteDesktop'] is not True:
        raise RuntimeError('The runner is not in the explicitly requested RDP session.')
    if identity['elevated'] or identity['integrityRid'] >= 0x3000:
        raise RuntimeError('The runner refuses an elevated or high-integrity token.')


class CommandJob:
    """Own a Windows Job Object so timeout/exit also closes the command's descendants."""
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        class Basic(ctypes.Structure):
            _fields_ = [('processTime', ctypes.c_longlong), ('jobTime', ctypes.c_longlong),
                        ('flags', wintypes.DWORD), ('minWorkingSet', ctypes.c_size_t),
                        ('maxWorkingSet', ctypes.c_size_t), ('activeProcesses', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('ioCounters', ctypes.c_ulonglong * 6),
                        ('processMemory', ctypes.c_size_t), ('jobMemory', ctypes.c_size_t),
                        ('peakProcessMemory', ctypes.c_size_t), ('peakJobMemory', ctypes.c_size_t)]
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign_and_resume(self, process):
        """Assign the still-suspended process before any command code can spawn a child."""
        kernel = self.kernel
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        process_handle = kernel.OpenProcess(0x0100 | 0x0001, False, process.pid)
        if not process_handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not kernel.AssignProcessToJobObject(self.handle, process_handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.CloseHandle(process_handle)
        # Popen closes the initial thread handle; find that suspended thread through
        # documented Toolhelp APIs rather than relying on private Python internals.
        class ThreadEntry(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('threadId', wintypes.DWORD),
                        ('processId', wintypes.DWORD), ('basePriority', wintypes.LONG),
                        ('deltaPriority', wintypes.LONG), ('flags', wintypes.DWORD)]
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        kernel.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenThread.restype = wintypes.HANDLE
        kernel.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel.ResumeThread.restype = wintypes.DWORD
        snapshot = kernel.CreateToolhelp32Snapshot(4, 0)
        if snapshot == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry = ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            exists = kernel.Thread32First(snapshot, ctypes.byref(entry))
            while exists:
                if entry.processId == process.pid:
                    thread = kernel.OpenThread(2, False, entry.threadId)
                    if not thread:
                        raise ctypes.WinError(ctypes.get_last_error())
                    try:
                        if kernel.ResumeThread(thread) == 0xFFFFFFFF:
                            raise ctypes.WinError(ctypes.get_last_error())
                        return
                    finally:
                        kernel.CloseHandle(thread)
                exists = kernel.Thread32Next(snapshot, ctypes.byref(entry))
            raise RuntimeError('The suspended command thread could not be located.')
        finally:
            kernel.CloseHandle(snapshot)

    def close(self):
        """Closing the sole job handle terminates any remaining owned command processes."""
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class BoundedOutput:
    """Drain continuously while retaining only a finite prefix of each output stream."""
    def __init__(self, limit):
        self.limit = limit
        self.data = bytearray()
        self.total = 0

    def drain(self, stream):
        """Keep the pipe moving after the retained output limit has been reached."""
        try:
            while chunk := stream.read1(4096):
                self.total += len(chunk)
                self.data.extend(chunk[:max(0, self.limit - len(self.data))])
        finally:
            stream.close()


def execute(job, *, identity_reader=windows_identity):
    """Execute literal argv with hidden windows and bounded lifetime/output; never a shell."""
    identity = identity_reader()
    require_ordinary_rdp(identity, job['windowsSessionId'])
    started = time.monotonic()
    owner = CommandJob()
    process = None
    output = [BoundedOutput(job['maxOutputBytes']), BoundedOutput(job['maxOutputBytes'])]
    threads = []
    timed_out = False
    try:
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        process = subprocess.Popen(job['argv'], cwd=job['workingDirectory'], shell=False,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=subprocess.CREATE_NO_WINDOW | 0x4, startupinfo=startup)
        for sink, stream in zip(output, (process.stdout, process.stderr)):
            thread = threading.Thread(target=sink.drain, args=(stream,), daemon=True)
            thread.start()
            threads.append(thread)
        owner.assign_and_resume(process)
        try:
            process.wait(timeout=job['timeoutSeconds'])
        except subprocess.TimeoutExpired:
            timed_out = True
    finally:
        owner.close()
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=5)
    return {'success': process.returncode == 0 and not timed_out,
            'returnCode': process.returncode, 'timedOut': timed_out,
            'elapsedMs': round((time.monotonic() - started) * 1000, 3), **identity,
            'stdout': output[0].data.decode('utf-8', errors='replace'),
            'stderr': output[1].data.decode('utf-8', errors='replace'),
            'stdoutBytes': output[0].total, 'stderrBytes': output[1].total,
            'stdoutTruncated': output[0].total > output[0].limit,
            'stderrTruncated': output[1].total > output[1].limit,
            'outputIncomplete': any(thread.is_alive() for thread in threads)}


def run_job(path):
    """Claim a UUID-named job exactly once and atomically publish its result beside it."""
    path = local_absolute(os.fspath(path))
    suffix = '.job.json'
    if not path.name.endswith(suffix):
        raise ValueError('Expected a UUID.job.json command file.')
    job_id = path.name[:-len(suffix)]
    if str(uuid.UUID(job_id)) != job_id:
        raise ValueError('Expected a canonical UUID job file name.')
    result_path = path.with_name(job_id + '.result.json')
    if result_path.exists():
        raise ValueError('The command job already has a result; it will not be replayed.')
    # Keep this exclusive claim after completion so a lost response cannot replay work.
    with path.with_name(job_id + '.claimed').open('x', encoding='utf-8') as claim:
        claim.write(str(os.getpid()))
    result = {'version': 1, 'jobId': job_id, 'runnerProcessId': os.getpid(),
              'startedAtUtc': datetime.now(timezone.utc).isoformat()}
    try:
        if not 0 < path.stat().st_size <= MAX_JOB_BYTES:
            raise ValueError('Command job exceeds the size limit.')
        job = validate_job(json.loads(path.read_text(encoding='utf-8')), job_id)
        result.update(execute(job))
    except Exception as error:
        result.update(success=False, error=f'{type(error).__name__}: {error}')
    result['endedAtUtc'] = datetime.now(timezone.utc).isoformat()
    atomic_json(result_path, result)
    return result


def main():
    """Entry point launched by the ordinary-token scheduled task in the RDP child."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', required=True)
    args = parser.parse_args()
    try:
        result = run_job(args.job)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    return 0 if result['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
