"""Pure runtime-pin and exact Windows redirector ancestry regressions."""
import copy
from pathlib import Path
import tempfile
import unittest

from combat_process_identity import runtime_contract, worker_ancestry, verify_worker_broker


class CombatProcessIdentityTests(unittest.TestCase):
    """Never query or launch a process while testing process evidence acceptance."""
    def setUp(self):
        """Create tiny inert executable/config bytes under a disposable local tree."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.venv, self.base = root / 'venv/Scripts/python.exe', root / 'base/python.exe'
        for path in (self.venv, self.base, self.base.with_name('pythonw.exe')):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('inert ' + str(path)).encode())
        self.cfg = self.venv.parent.parent / 'pyvenv.cfg'
        self.cfg.write_text(f'home = {self.base.parent}\ninclude-system-site-packages = false\nexecutable = {self.base}\n')
        self.resources = dict(gpuPython=str(self.venv), runnerPython=str(self.base))
        self.contract = runtime_contract(self.resources)
        def identity(pid, parent, image, created):
            """Describe one live creation identity without asking Windows for it."""
            return dict(processId=pid, parentProcessId=parent, executable=str(image),
                windowsSessionId=3, startedFileTime=created)
        self.chain = [identity(300, 200, self.base, 30), identity(200, 100, self.venv, 20),
            identity(100, 50, self.base.with_name('pythonw.exe'), 10)]
        self.worker = dict(processId=300, parentProcessId=200, windowsSessionId=3,
            processIdentity=copy.deepcopy(self.chain[0]), launchAncestry=copy.deepcopy(self.chain))
        self.broker = dict(runnerProcessId=100, commandProcessId=200, commandIdentity=copy.deepcopy(self.chain[1]))

    def test_exact_suspended_command_and_one_redirector_edge(self):
        """The broker's command PID is the exact live shim, not its arbitrary descendant."""
        rows = {row['processId']: row for row in self.chain}
        observed = []
        def read(pid):
            """Track the three bounded exact-PID reads in their required order."""
            observed.append(pid)
            return copy.deepcopy(rows[pid])
        self.assertEqual(worker_ancestry(self.contract, 300, 200, read), self.chain)
        self.assertEqual(observed, [300, 200, 100])
        verify_worker_broker(self.worker, self.broker, self.contract)

    def test_missing_command_pid_cannot_retroactively_prove_old_failed_chain(self):
        """The real failed run lacked this witness and remains unqualified historically."""
        with self.assertRaises(ValueError):
            verify_worker_broker(self.worker, dict(runnerProcessId=100), self.contract)

    def test_pid_reuse_image_session_or_extra_ancestry_is_rejected(self):
        """Matching integer PIDs alone never qualify a venv worker."""
        for mutation in ('command-time', 'worker-time', 'image', 'session', 'extra', 'different-parent', 'missing-time'):
            with self.subTest(mutation=mutation):
                worker, broker = copy.deepcopy(self.worker), copy.deepcopy(self.broker)
                if mutation == 'command-time':
                    broker['commandIdentity']['startedFileTime'] += 1
                elif mutation == 'worker-time':
                    worker['launchAncestry'][0]['startedFileTime'] = 19
                    worker['processIdentity']['startedFileTime'] = 19
                elif mutation == 'image':
                    worker['launchAncestry'][1]['executable'] = str(self.base)
                elif mutation == 'session':
                    worker['launchAncestry'][1]['windowsSessionId'] = 4
                elif mutation == 'extra':
                    worker['launchAncestry'].append(copy.deepcopy(self.chain[2]))
                elif mutation == 'missing-time':
                    worker['launchAncestry'][0].pop('startedFileTime')
                else:
                    worker['parentProcessId'] = 999
                with self.assertRaises(ValueError):
                    verify_worker_broker(worker, broker, self.contract)

    def test_exact_direct_mode_and_historical_direct_replay_remain_distinct(self):
        """New direct witnesses require command/worker creation equality; old direct proofs stay strict."""
        current = copy.deepcopy(self.chain[0])
        current['parentProcessId'] = 100
        worker = dict(processId=300, parentProcessId=100, windowsSessionId=3, processIdentity=current)
        contract = dict(kind='direct-python-v1', executable=str(self.base))
        broker = dict(runnerProcessId=100, commandProcessId=300, commandIdentity=copy.deepcopy(current))
        verify_worker_broker(worker, broker, contract)
        verify_worker_broker(dict(processId=300, parentProcessId=100), dict(runnerProcessId=100))
        for change in ({'commandProcessId': 301}, {'commandIdentity': dict(current, startedFileTime=31)}):
            with self.assertRaises(ValueError):
                verify_worker_broker(worker, dict(broker, **change), contract)
        with self.assertRaises(ValueError):
            verify_worker_broker(worker, dict(runnerProcessId=100), contract)

    def test_partial_new_witnesses_cannot_select_historical_direct_replay(self):
        """Removing the contract cannot hide even malformed or null new-format remnants."""
        old_worker, old_broker = dict(processId=300, parentProcessId=100), dict(runnerProcessId=100)
        for key in ('processIdentity', 'launchAncestry', 'commandProcessId', 'commandIdentity'):
            for value in (None, {}, 300):
                with self.subTest(key=key, value=value):
                    worker, broker = copy.deepcopy(old_worker), copy.deepcopy(old_broker)
                    (worker if key in ('processIdentity', 'launchAncestry') else broker)[key] = value
                    with self.assertRaisesRegex(ValueError, 'Undeclared process'):
                        verify_worker_broker(worker, broker)

    def test_frozen_venv_configuration_replays_without_current_installed_bytes(self):
        """Only the original cfg and exact executable bytes determine historical base identity."""
        originals = {name: Path(name).read_bytes() for name in self.contract['files']}
        def reader(path):
            """Expose the original archive without reading the now-mutated configuration."""
            return originals[str(path)]
        reader.venv = True
        self.cfg.write_text('executable = Z:/unknown/python.exe\n')
        self.assertEqual(runtime_contract(self.resources, reader), self.contract)
        with self.assertRaises(ValueError):
            runtime_contract(self.resources)

    def test_second_unpinned_background_redirector_is_not_supported(self):
        """The broker uses only the frozen base pythonw, without an additional venv launcher."""
        with self.assertRaisesRegex(ValueError, 'pinned base Python'):
            runtime_contract(dict(self.resources, runnerPython=str(self.venv)))

    def test_venv_command_shim_cannot_be_promoted_to_the_worker(self):
        """A venv declaration always requires its actual base interpreter and all three live rows."""
        shim = copy.deepcopy(self.chain[1])
        worker = dict(processId=shim['processId'], parentProcessId=shim['parentProcessId'],
            windowsSessionId=3, processIdentity=shim)
        with self.assertRaisesRegex(ValueError, 'promoted'):
            verify_worker_broker(worker, self.broker, self.contract)


if __name__ == '__main__':
    unittest.main()
