"""Native process-container tests only: no RDP connection, GUI, or game inputs.

execute() receives an injected test identity to exercise harmless local Python
children. Production run_job() always obtains and enforces its real WTS identity.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import unittest

import child_runner as runner


@unittest.skipUnless(os.name == 'nt', 'Windows process-container integration tests')
class NativeRunnerTests(unittest.TestCase):
    """Verify literal argv and ownership of descendants under the real Windows API."""
    def _execute(self, arguments, timeout=5):
        """Use only this interpreter and headless, bounded test programs."""
        identity = {'windowsSessionId': 91, 'remoteDesktop': True,
                    'elevated': False, 'integrityRid': 0x2000}
        job = {'windowsSessionId': 91, 'argv': [sys.executable, *arguments],
               'workingDirectory': str(Path(__file__).resolve().parent),
               'timeoutSeconds': timeout, 'maxOutputBytes': 1024}
        return runner.execute(job, identity_reader=lambda: identity)

    def _assert_process_exited(self, process_id):
        """Job termination may legitimately produce exit code zero; wait state matters."""
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, process_id)  # SYNCHRONIZE only
        if not handle:
            self.assertEqual(ctypes.get_last_error(), 87)  # PID no longer exists
            return
        try:
            self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
        finally:
            kernel.CloseHandle(handle)

    def test_literal_argv_survives_real_windows_process_creation(self):
        arguments = ['', 'a b', 'a"b', 'trailing\\', '\\"',
                     'literal & | > $(x) %PATH%', 'unicode-\u754c']
        result = self._execute(['-c', 'import sys,json; print(json.dumps(sys.argv[1:],ensure_ascii=True))',
                                *arguments])
        self.assertTrue(result['success'], result)
        self.assertEqual(json.loads(result['stdout']), arguments)
        self.assertFalse(result['outputIncomplete'])

    def test_timeout_and_parent_exit_both_terminate_owned_descendants(self):
        for parent_waits in (True, False):
            with self.subTest(parent_waits=parent_waits):
                source = ('import subprocess,sys,time; '
                          'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"],'
                          'creationflags=subprocess.CREATE_NO_WINDOW); '
                          'print(p.pid,flush=True); ' + ('time.sleep(60)' if parent_waits else ''))
                result = self._execute(['-c', source], timeout=1 if parent_waits else 5)
                self.assertEqual(result['timedOut'], parent_waits, result)
                self.assertEqual(result['success'], not parent_waits, result)
                self.assertFalse(result['outputIncomplete'], result)
                self._assert_process_exited(int(result['stdout'].strip()))


if __name__ == '__main__':
    unittest.main()
