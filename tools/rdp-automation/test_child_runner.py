"""Command runner guardrails and local process-lifetime tests; no game/GUI input."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import child_runner as runner


class RunnerTests(unittest.TestCase):
    def test_suspended_command_identity_is_retained_before_any_resume(self):
        """Capture the exact original Popen PID/creation identity before a redirector can spawn."""
        ordinary = dict(windowsSessionId=3, remoteDesktop=True, elevated=False, integrityRid=8192)
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory).resolve() / 'python.exe'
            executable.write_bytes(b'inert')
            calls = []
            identity = dict(processId=222, parentProcessId=os.getpid(), windowsSessionId=3,
                executable=str(executable), startedFileTime=12345)
            process = SimpleNamespace(pid=222, returncode=0, stdout=io.BufferedReader(io.BytesIO(b'ok')),
                stderr=io.BufferedReader(io.BytesIO()), wait=lambda **kwargs: 0, poll=lambda: 0,
                kill=lambda: calls.append('kill'))
            def read(pid):
                """The exact suspended process is the only native identity queried."""
                self.assertEqual(pid, 222)
                calls.append('identity')
                return identity
            def resume(value):
                """The command cannot run before its original identity was retained."""
                self.assertEqual(calls, ['identity'])
                self.assertIs(value, process)
                calls.append('resume')
            owner = SimpleNamespace(assign_and_resume=resume, close=lambda: calls.append('close'))
            job = dict(windowsSessionId=3, maxOutputBytes=1024, argv=[str(executable)],
                workingDirectory=directory, timeoutSeconds=5)
            with patch.object(runner, 'process_identity', side_effect=read), \
                    patch.object(runner, 'CommandJob', return_value=owner), \
                    patch.object(runner.subprocess, 'Popen', return_value=process):
                result = runner.execute(job, identity_reader=lambda: ordinary)
            self.assertEqual(calls, ['identity', 'resume', 'close'])
            self.assertEqual(result['commandProcessId'], 222)
            self.assertEqual(result['commandIdentity'], identity)
            self.assertTrue(result['success'])

    def test_changed_suspended_parent_never_resumes(self):
        """A contradictory original command witness fails before any child code can execute."""
        ordinary = dict(windowsSessionId=3, remoteDesktop=True, elevated=False, integrityRid=8192)
        cleanup = []
        process = SimpleNamespace(pid=222, returncode=None, stdout=io.BufferedReader(io.BytesIO()),
            stderr=io.BufferedReader(io.BytesIO()), wait=lambda **kwargs: cleanup.append('wait'),
            poll=lambda: None, kill=lambda: cleanup.append('kill'))
        owner = SimpleNamespace(assign_and_resume=lambda value: self.fail('unexpected resume'), close=lambda: None)
        with patch.object(runner, 'CommandJob', return_value=owner), \
                patch.object(runner.subprocess, 'Popen', return_value=process), \
                patch.object(runner, 'process_identity', return_value=dict(processId=222, parentProcessId=os.getpid() + 1,
                    windowsSessionId=3, executable=str(Path('python.exe').resolve()), startedFileTime=1)):
            with self.assertRaisesRegex(RuntimeError, 'suspended command identity'):
                runner.execute(dict(windowsSessionId=3, maxOutputBytes=1024, argv=[str(Path('python.exe').resolve())],
                    workingDirectory=str(Path.cwd()), timeoutSeconds=5), identity_reader=lambda: ordinary)
        self.assertEqual(cleanup, ['kill', 'wait'])

    def test_console_wrong_session_and_elevated_tokens_are_rejected(self):
        ordinary = {'windowsSessionId': 3, 'remoteDesktop': True, 'elevated': False, 'integrityRid': 0x2000}
        runner.require_ordinary_rdp(ordinary, 3)
        for changed in ({'windowsSessionId': 2}, {'remoteDesktop': False}, {'elevated': True}, {'integrityRid': 0x3000}):
            with self.assertRaises(RuntimeError):
                runner.require_ordinary_rdp({**ordinary, **changed}, 3)
        with patch.object(runner.subprocess, 'Popen') as process:
            with self.assertRaises(RuntimeError):
                runner.execute({'windowsSessionId': 3}, identity_reader=lambda: {**ordinary, 'remoteDesktop': False})
        process.assert_not_called()

    def test_output_is_drained_but_storage_is_bounded(self):
        sink = runner.BoundedOutput(1024)
        sink.drain(io.BufferedReader(io.BytesIO(b'x' * 100000)))
        self.assertEqual(sink.total, 100000)
        self.assertEqual(len(sink.data), 1024)

    def test_validate_expiry_literal_arguments_and_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'test.exe'
            executable.write_bytes(b'fixture')
            job_id = str(uuid.uuid4())
            job = {'version': 1, 'jobId': job_id, 'createdAtUnixMs': 100000, 'windowsSessionId': 1,
                   'argv': [str(executable), 'literal & | > value', 'quoted " value', '末尾'],
                   'workingDirectory': directory, 'timeoutSeconds': 10, 'maxOutputBytes': 1024}
            self.assertIs(runner.validate_job(job, job_id, 100000), job)
            for changed in ({'timeoutSeconds': 0}, {'timeoutSeconds': True}, {'createdAtUnixMs': 1},
                            {'maxOutputBytes': 2000000}, {'argv': [str(executable), '\x00']},
                            {'extraField': 'not accepted'}):
                with self.assertRaises(ValueError):
                    runner.validate_job({**job, **changed}, job_id, 100000)

    def test_job_claim_is_single_use_and_errors_are_atomic_results(self):
        with tempfile.TemporaryDirectory() as directory:
            job_id = str(uuid.uuid4())
            path = Path(directory) / (job_id + '.job.json')
            path.write_text('{}')
            result = runner.run_job(str(path))
            self.assertFalse(result['success'])
            saved = json.loads(path.with_name(job_id + '.result.json').read_text())
            self.assertEqual(saved['jobId'], job_id)
            with self.assertRaisesRegex(ValueError, 'will not be replayed'):
                runner.run_job(str(path))
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])

    @unittest.skipUnless(os.name == 'nt', 'Windows native Job Object test')
    def test_native_suspended_command_assignment_output_and_job_cleanup(self):
        # Test only the process-container primitive with harmless console Python.
        # Production execute() still rejects this console session before Popen.
        owner = runner.CommandJob()
        process = subprocess.Popen([sys.executable, '-c', 'print("job-object-ok", flush=True)'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=subprocess.CREATE_NO_WINDOW | 0x4)
        try:
            identity = runner.process_identity(process.pid)
            self.assertEqual(identity['processId'], process.pid)
            self.assertEqual(identity['parentProcessId'], os.getpid())
            self.assertEqual(identity['windowsSessionId'], runner.windows_identity()['windowsSessionId'])
            self.assertEqual(Path(identity['executable']), Path(sys.executable))
            self.assertGreater(identity['startedFileTime'], 0)
            owner.assign_and_resume(process)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0)
            self.assertEqual(stdout.strip(), b'job-object-ok')
            self.assertEqual(stderr, b'')
        finally:
            owner.close()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        owner = runner.CommandJob()
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                   creationflags=subprocess.CREATE_NO_WINDOW | 0x4)
        try:
            owner.assign_and_resume(process)
        finally:
            owner.close()
        # Windows may use exit code zero for JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        # bounded termination of a 60-second sleeper is the relevant assertion.
        process.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
