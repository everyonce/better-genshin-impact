"""Local inert filesystem/lock tests. Dispatch is always a synthetic function."""
import copy
import json
import os
import stat
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from relay_reliability import Held, OwnerContext, RelayJournal, binding, encode, parse_request, validate_result


HERE = Path(__file__).resolve().parent
TEST_ROOT = HERE / ".test-work"
STEPS = {"allowedTravel", "allowedCombat"}
OWNER = OwnerContext("test-owned-r3", 1234, 2, "a" * 64)
REQUEST = {"id": "request-0001", "kind": "questStep", "frame": 42, "step": "allowedTravel"}
MISSION = "mission-" + "b" * 32


class Crash(BaseException):
    pass


def terminal(request, owner):
    return {"id": request["id"], "code": 0, "error": None, "output": None,
            "result": {"status": "completed", "session": owner.session, "frameId": request["frame"] + 1,
                       "submittedId": MISSION, "terminalId": MISSION, "controllerQuiescent": True}}


class CrashJournal(RelayJournal):
    crash_at = None

    def _checkpoint(self, name):
        if name == self.crash_at:
            raise Crash(name)


class RelayTests(unittest.TestCase):
    def setUp(self):
        TEST_ROOT.mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="case-", dir=TEST_ROOT)).resolve()
        self.assertEqual(self.root.parent, TEST_ROOT.resolve())
        self.journal_dir = self.root / "journal"
        self.legacy = self.root / "legacy"
        self.journal_dir.mkdir()
        self.legacy.mkdir()
        self.calls = []
        self.request = copy.deepcopy(REQUEST)
        self.journal = self.restart()

    def tearDown(self):
        resolved = self.root.resolve()
        self.assertEqual(resolved.parent, TEST_ROOT.resolve())
        self.assertTrue(resolved.name.startswith("case-"))
        shutil.rmtree(resolved)

    def restart(self, cls=RelayJournal):
        return cls(self.journal_dir, STEPS, self.legacy)

    def dispatch(self, request, owner):
        self.calls.append(copy.deepcopy(request))
        # Both durable records must exist before even the injected CLI is called.
        self.assertTrue((self.journal_dir / "active.json").is_file())
        self.assertTrue((self.journal_dir / (request["id"] + ".intent.json")).is_file())
        return terminal(request, owner)

    def execute(self, journal=None, request=None, owner=OWNER, dispatch=None):
        return (journal or self.journal).execute(request or self.request, owner, dispatch or self.dispatch)

    def another(self):
        return {**self.request, "id": "request-0002", "frame": 44}

    def test_completed_duplicate_within_process_calls_once(self):
        first = self.execute()
        second = self.execute()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(validate_result(second, self.request, OWNER, STEPS), first["response"])

    def test_restart_replays_bound_result_without_dispatch_or_rewrite(self):
        self.execute()
        path = self.journal_dir / "request-0001.response.json"
        before = path.read_bytes()
        result = self.execute(journal=self.restart())
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(result["replayed"])
        self.assertEqual(path.read_bytes(), before)

    def test_changed_frame_or_step_rejected_and_old_result_reader_rejects(self):
        old = self.execute()
        for change in ({"frame": 44}, {"step": "allowedCombat"}, {"kind": "observe", "step": None}):
            changed = {**self.request, **change}
            if changed["kind"] == "observe":
                del changed["step"]
            with self.subTest(change=change):
                result = self.execute(journal=self.restart(), request=changed)
                self.assertEqual(result["reason"], "request-binding-mismatch")
                with self.assertRaises(Held):
                    validate_result(old, changed, OWNER, STEPS)
                with self.assertRaises(Held):
                    validate_result(result, changed, OWNER, STEPS)
        self.assertEqual(len(self.calls), 1)

    def test_changed_session_process_windows_session_or_lifetime_rejected(self):
        old = self.execute()
        contexts = [OwnerContext("next-owned-r3", 1234, 2, "a" * 64),
                    OwnerContext(OWNER.session, 1235, 2, "a" * 64),
                    OwnerContext(OWNER.session, 1234, 3, "a" * 64),
                    OwnerContext(OWNER.session, 1234, 2, "c" * 64)]
        for owner in contexts:
            with self.subTest(owner=owner):
                result = self.execute(journal=self.restart(), owner=owner)
                self.assertEqual(result["reason"], "request-binding-mismatch")
                with self.assertRaises(Held):
                    validate_result(old, self.request, owner, STEPS)
        self.assertEqual(len(self.calls), 1)

    def test_legacy_unbound_response_preserved_and_never_dispatched(self):
        path = self.legacy / "request-0001.json"
        old = terminal(self.request, OWNER)
        path.write_bytes(encode(old))
        before = path.read_bytes()
        result = self.execute()
        self.assertEqual(result["reason"], "legacy-unbound-response")
        self.assertEqual(self.calls, [])
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaises(Held):
            validate_result(old, self.request, OWNER, STEPS)

    def test_crash_after_active_before_intent_holds_all_requests(self):
        journal = self.restart(CrashJournal)
        journal.crash_at = "after-active"
        with self.assertRaises(Crash):
            self.execute(journal=journal)
        for request in (self.request, self.another()):
            result = self.execute(journal=self.restart(), request=request)
            self.assertEqual(result["reason"], "active-intent-incomplete")
        self.assertEqual(self.calls, [])

    def test_crash_after_intent_before_dispatch_never_assumes_nonsubmission(self):
        journal = self.restart(CrashJournal)
        journal.crash_at = "after-intent"
        with self.assertRaises(Crash):
            self.execute(journal=journal)
        self.assertEqual(self.execute(journal=self.restart())["state"], "unknown")
        self.assertEqual(self.execute(journal=self.restart(), request=self.another())["reason"], "unknown-in-flight")
        self.assertEqual(self.calls, [])

    def test_crash_after_dispatch_before_response_does_not_repeat_cli(self):
        journal = self.restart(CrashJournal)
        journal.crash_at = "after-dispatch"
        with self.assertRaises(Crash):
            self.execute(journal=journal)
        self.assertEqual(self.execute(journal=self.restart())["state"], "unknown")
        self.assertEqual(self.execute(journal=self.restart(), request=self.another())["state"], "held")
        self.assertEqual(len(self.calls), 1)

    def test_lost_response_after_durable_settlement_reconciles_read_only(self):
        journal = self.restart(CrashJournal)
        journal.crash_at = "after-response"
        with self.assertRaises(Crash):
            self.execute(journal=journal)
        before = {p.name: p.read_bytes() for p in self.journal_dir.iterdir()}
        result = self.restart().read_result(self.request, OWNER)
        self.assertTrue(result["replayed"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.journal_dir.iterdir()})
        self.assertEqual(self.execute(journal=self.restart(), request=self.another())["state"], "settled")
        self.assertEqual(len(self.calls), 2)

    def test_dispatch_exception_is_unknown_and_blocks_another_request(self):
        def failing(request, owner):
            self.calls.append(request)
            raise RuntimeError("simulated failure after possible submission")
        result = self.execute(dispatch=failing)
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(self.execute(journal=self.restart(), request=self.another())["reason"], "unknown-in-flight")
        self.assertEqual(len(self.calls), 1)

    def test_pending_or_unquiescent_terminal_holds(self):
        for result_change in ({"status": "pending"}, {"controllerQuiescent": False},
                              {"terminalId": "mission-" + "c" * 32}, {"session": "wrong-owned-r3"},
                              {"frameId": 41}, {"submittedId": None}):
            with self.subTest(change=result_change):
                request = {**self.request, "id": "pending-" + str(len(self.calls)).zfill(4)}
                child = self.root / request["id"]
                child.mkdir()
                journal = RelayJournal(child, STEPS)
                def pending(req, owner):
                    self.calls.append(req)
                    value = terminal(req, owner)
                    value["result"].update(result_change)
                    return value
                self.assertEqual(journal.execute(request, OWNER, pending)["state"], "unknown")
                self.assertEqual(journal.execute(self.another(), OWNER, pending)["reason"], "unknown-in-flight")

    def test_v4_explicit_deferred_nonsubmission_allows_new_frame_request(self):
        def deferred(request, owner):
            self.calls.append(request)
            return {"id": request["id"], "code": 0, "error": None, "output": None,
                    "result": {"status": "deferred", "session": owner.session, "frameId": request["frame"],
                               "requestSubmitted": False, "nextAction": "observe",
                               "receiptMaintenance": {"status": "archived"}}}
        result = self.execute(dispatch=deferred)
        self.assertEqual(result["state"], "settled")
        self.assertEqual(self.execute(request=self.another())["state"], "settled")
        self.assertEqual(len(self.calls), 2)

    def test_partial_response_after_dispatch_remains_held_without_overwrite(self):
        class Partial(RelayJournal):
            def _new(instance, name, value):
                if name.endswith(".response.json"):
                    (instance.directory / name).write_bytes(b'{"partial":')
                    raise OSError("simulated incomplete write")
                super()._new(name, value)
        self.assertEqual(self.execute(journal=self.restart(Partial))["state"], "held")
        path = self.journal_dir / "request-0001.response.json"
        before = path.read_bytes()
        self.assertEqual(self.execute(journal=self.restart())["reason"], "corrupt-record")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(self.calls), 1)

    def test_corrupt_intent_or_active_marker_blocks_dispatch(self):
        for name in ("active.json", "request-0001.intent.json"):
            path = self.journal_dir / name
            path.write_bytes(b"{")
            self.assertEqual(self.execute()["reason"], "corrupt-record")
            path.unlink()
        self.assertEqual(self.calls, [])

    def test_response_without_intent_is_never_treated_as_admission(self):
        (self.journal_dir / "request-0001.response.json").write_bytes(encode({"old": True}))
        self.assertEqual(self.execute()["reason"], "response-without-intent")
        self.assertEqual(self.calls, [])

    def test_tampered_binding_hash_holds(self):
        self.execute()
        path = self.journal_dir / "request-0001.response.json"
        value = json.loads(path.read_bytes())
        value["binding"] = "0" * 64
        path.write_bytes(encode(value))
        self.assertEqual(self.execute(journal=self.restart())["reason"], "stored-response-binding-mismatch")
        self.assertEqual(len(self.calls), 1)

    def test_result_reader_rejects_schema_boolean_and_changed_request(self):
        result = self.execute()
        result["schema"] = True
        with self.assertRaises(Held):
            validate_result(result, self.request, OWNER, STEPS)

    def test_request_parser_rejects_duplicate_keys_and_nonfinite_values(self):
        for raw in ('{"id":"first","id":"second"}', '{"frame":NaN}', '[]'):
            with self.subTest(raw=raw), self.assertRaises(Held):
                parse_request(raw)

    def test_invalid_input_or_missing_complete_owner_never_dispatches(self):
        for change in ({"id": "../escape"}, {"frame": True}, {"step": "unlisted"},
                       {"extra": 1}, {"kind": []}):
            with self.subTest(change=change), self.assertRaises(Held):
                self.execute(request={**self.request, **change})
        with self.assertRaises(Held):
            self.execute(owner=OwnerContext(OWNER.session, 1234, 2, ""))
        self.assertEqual(self.calls, [])

    def test_cross_process_lock_allows_only_one_caller(self):
        code = ('import json,sys; sys.path.insert(0,sys.argv[1]); '
                'from relay_reliability import *; '
                'j=RelayJournal(sys.argv[2],{"allowedTravel"}); '
                'o=OwnerContext("test-owned-r3",1234,2,"a"*64); '
                'r=json.loads(sys.argv[3]); '
                'print(json.dumps(j.execute(r,o,lambda *_:{"unexpected":True})))')
        with self.journal._lock():
            child = subprocess.run([sys.executable, "-I", "-B", "-c", code,
                                    str(HERE), str(self.journal_dir), json.dumps(self.request)],
                                   capture_output=True, text=True, timeout=10, check=True)
        self.assertEqual(json.loads(child.stdout)["reason"], "journal-busy")
        self.assertFalse((self.journal_dir / "active.json").exists())
        self.assertEqual(self.execute()["state"], "settled")

    def test_abrupt_process_exit_keeps_unknown_intent_after_lock_is_released(self):
        code = '''import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from relay_reliability import *
class Abrupt(RelayJournal):
    def _checkpoint(self,name):
        if name == "after-dispatch": os._exit(77)
def dispatch(request,owner):
    with (Path(sys.argv[2])/"inert-dispatch.txt").open("a",encoding="utf-8") as f:
        f.write("one synthetic call\\n")
        f.flush()
        os.fsync(f.fileno())
    return None
j=Abrupt(sys.argv[2],{"allowedTravel"})
j.execute(json.loads(sys.argv[3]),OwnerContext("test-owned-r3",1234,2,"a"*64),dispatch)
'''
        child = subprocess.run([sys.executable, "-I", "-B", "-c", code,
                                str(HERE), str(self.journal_dir), json.dumps(self.request)],
                               capture_output=True, text=True, timeout=10)
        self.assertEqual(child.returncode, 77, child.stderr)
        self.assertEqual(self.execute(journal=self.restart())["state"], "unknown")
        self.assertEqual(self.execute(journal=self.restart(), request=self.another())["reason"], "unknown-in-flight")
        self.assertEqual((self.journal_dir / "inert-dispatch.txt").read_text().splitlines(), ["one synthetic call"])
        self.assertEqual(self.calls, [])

    def test_unknown_result_cannot_be_read_as_completion(self):
        self.execute(dispatch=lambda *_: None)
        with self.assertRaises(Held):
            self.restart().read_result(self.request, OWNER)

    def test_dangling_entries_refuse_before_open_or_dispatch(self):
        """Model dangling POSIX/Windows entries without requiring symlink privileges."""
        real_exists, real_lstat, real_open = Path.exists, Path.lstat, Path.open
        entries = (("journal.lock", False), ("active.json", False),
                   ("request-0001.intent.json", False),
                   ("request-0001.response.json", False), ("request-0001.json", True))
        for index, (name, is_legacy) in enumerate(entries):
            for kind in ("symlink", "windows-reparse"):
                with self.subTest(entry=name, kind=kind):
                    case = self.root / f"dangling-{index}-{kind}"
                    journal, legacy = case / "journal", case / "legacy"
                    journal.mkdir(parents=True)
                    legacy.mkdir()
                    target = (legacy if is_legacy else journal) / name
                    before = b"retained entry; target unavailable"
                    target.write_bytes(before)
                    info = SimpleNamespace(st_mode=stat.S_IFLNK if kind == "symlink" else stat.S_IFREG,
                                           st_file_attributes=0 if kind == "symlink" else 0x400,
                                           st_size=len(before))
                    def entry_exists(path):
                        return False if path == target else real_exists(path)
                    def entry_lstat(path, *args, **kwargs):
                        return info if path == target else real_lstat(path, *args, **kwargs)
                    def guarded_open(path, *args, **kwargs):
                        self.assertNotEqual(path, target, "must reject before opening the dangling entry")
                        return real_open(path, *args, **kwargs)
                    def dispatch(request, owner):
                        self.calls.append(request)
                        return terminal(request, owner)
                    with patch.object(Path, "exists", entry_exists), \
                         patch.object(Path, "lstat", entry_lstat), patch.object(Path, "open", guarded_open):
                        result = RelayJournal(journal, STEPS, legacy).execute(self.request, OWNER, dispatch)
                    self.assertEqual(result["state"], "held")
                    self.assertEqual(result["reason"], "reparse-path-held")
                    self.assertEqual(self.calls, [])
                    self.assertEqual(target.read_bytes(), before)
                    self.assertLessEqual({p.name for p in journal.iterdir()},
                                         {"journal.lock", name} if not is_legacy else {"journal.lock"})

    def test_entry_metadata_errors_never_mean_absence(self):
        """Access and I/O failures hold all three admission paths without opening or dispatch."""
        real_lstat, real_open = Path.lstat, Path.open
        entries = (("journal.lock", False), ("request-0001.response.json", False),
                   ("request-0001.json", True))
        for index, (name, is_legacy) in enumerate(entries):
            for error_type in (PermissionError, OSError):
                with self.subTest(entry=name, error=error_type.__name__):
                    case = self.root / f"metadata-{index}-{error_type.__name__}"
                    journal, legacy = case / "journal", case / "legacy"
                    journal.mkdir(parents=True)
                    legacy.mkdir()
                    target = (legacy if is_legacy else journal) / name
                    before = b"retained inaccessible entry"
                    target.write_bytes(before)
                    def entry_lstat(path, *args, **kwargs):
                        if path == target:
                            raise error_type("simulated unavailable metadata")
                        return real_lstat(path, *args, **kwargs)
                    def guarded_open(path, *args, **kwargs):
                        self.assertNotEqual(path, target, "must reject before opening unavailable evidence")
                        return real_open(path, *args, **kwargs)
                    def dispatch(request, owner):
                        self.calls.append(request)
                        return terminal(request, owner)
                    with patch.object(Path, "lstat", entry_lstat), patch.object(Path, "open", guarded_open):
                        result = RelayJournal(journal, STEPS, legacy).execute(self.request, OWNER, dispatch)
                    self.assertEqual(result["state"], "held")
                    self.assertEqual(result["reason"], "storage-or-response-error")
                    self.assertEqual(self.calls, [])
                    self.assertEqual(target.read_bytes(), before)
                    self.assertLessEqual({p.name for p in journal.iterdir()},
                                         {"journal.lock", name} if not is_legacy else {"journal.lock"})

    def test_non_regular_record_is_held(self):
        (self.journal_dir / "active.json").mkdir()
        self.assertEqual(self.execute()["reason"], "unexpected-path-type")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
