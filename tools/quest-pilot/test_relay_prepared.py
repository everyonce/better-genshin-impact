import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import stat
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import asdict, replace
from unittest.mock import patch
from types import SimpleNamespace

import relay_prepared as subject
from relay_reliability import Held, OwnerContext, encode


class Crash(BaseException):
    pass


class CheckpointJournal(subject.PreparedRelayJournal):
    def _checkpoint(self, name):
        if getattr(self, "checkpoint_action", None):
            self.checkpoint_action(name)
        if getattr(self, "crash_at", None) == name:
            raise Crash(name)


OWNER = OwnerContext("test-session-r2", 1234, 2, "a" * 64)
OUTER = {"id": "outer-00000001", "kind": "observe", "frame": 10}


def heartbeat(frame=10, at=100000):
    return {"version": 1, "session": OWNER.session, "processId": OWNER.process_id,
            "windowsSessionId": OWNER.windows_session_id, "remoteDesktop": True,
            "frameId": frame, "heartbeatAt": at, "state": "idle", "activeRequestId": None}


def inner_request(outer=OUTER, digit="1"):
    value = {"session": OWNER.session, "expectedFrameId": outer["frame"],
             "id": "mission-" + digit * 32, "createdAt": 100000, "mission": outer["kind"]}
    if outer["kind"] == "questStep":
        value["step"] = outer["step"]
    return value



def child_command(mode, root):
    source = Path(__file__).resolve()
    bootstrap = ("import runpy, sys; sys.path.insert(0, sys.argv[1]); "
                 "sys.argv = sys.argv[2:]; runpy.run_path(sys.argv[0], run_name='__main__')")
    return [sys.executable, "-B", "-c", bootstrap, str(source.parent), str(source), mode, str(root)]


def child_environment():
    # Keep inherited settings and exercise the trusted import bootstrap under
    # safe-path mode. No interpreter or machine settings are changed.
    return {**os.environ, "PYTHONSAFEPATH": "1"}


def child_mode(mode, root):
    root = Path(root)
    journal = subject.PreparedRelayJournal(root / "journal", {"safeStep"}, owner_probe=lambda **_: OWNER,
                                           legacy_responses=root / "legacy", clock_ms=lambda: 100000)
    if mode == "--hold-lock":
        with journal._lock():
            (root / "ready").write_text("ready")
            sys.stdin.read(1)
    else:
        def dispatch(outer, owner, prepare):
            raw = json.dumps(inner_request()).encode("utf-8")
            prepare(raw, heartbeat())
            (root / "request.json").write_bytes(raw)
            (root / "synthetic-effect-count").write_text("1")
            os._exit(77)
        journal.execute(OUTER, OWNER, dispatch)


class PreparedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="prepared-relay-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "journal").mkdir()
        (self.root / "legacy").mkdir()
        self.clock = 100000
        self.current_owner = OWNER
        self.effects = []
        self.journal = self.make_journal()

    def make_journal(self):
        return CheckpointJournal(self.root / "journal", {"safeStep"},
                                 owner_probe=lambda **_: self.current_owner,
                                 legacy_responses=self.root / "legacy", clock_ms=lambda: self.clock)

    def prepared(self):
        return json.loads((self.root / "journal" / (OUTER["id"] + ".prepared.json")).read_text())

    def response(self, outer, inner):
        return {"id": outer["id"], "code": 0, "error": None, "output": None,
                "result": {"submittedId": inner["id"], "terminalId": inner["id"], "session": OWNER.session,
                           "status": "completed", "frameId": 11, "controllerQuiescent": True}}

    def dispatch(self, outer, owner, prepare, *, crash=None, digit="1", timeout=False):
        inner = inner_request(outer, digit)
        raw = json.dumps(inner).encode("utf-8")
        ack = prepare(raw, heartbeat())
        self.assertEqual(ack["requestSha256"], hashlib.sha256(raw).hexdigest())
        self.assertTrue(ack["durable"])
        self.assertEqual(self.prepared()["requestUtf8"].encode("utf-8"), raw)
        ack["revalidate"](heartbeat())
        (self.root / "request.json").write_bytes(raw)
        if crash == "after-request":
            raise Crash(crash)
        self.effects.append(inner["id"])
        if crash == "after-native":
            raise Crash(crash)
        if timeout:
            return {"id": outer["id"], "code": 0, "error": None, "result": None, "output": "pending"}
        return self.response(outer, inner)

    def start_unknown(self):
        result = self.journal.execute(OUTER, OWNER,
                                      lambda *args: self.dispatch(*args, timeout=True))
        self.assertEqual(result["state"], "unknown")

    def proof(self):
        prepared = self.prepared()
        inner = prepared["innerRequest"]
        receipt = {"id": inner["id"], "session": OWNER.session, "mission": inner["mission"],
                   "status": "completed", "frameId": 11, "timestamp": 100100, "details": {"synthetic": True}}
        observed = {"session": OWNER.session, "frameId": 11, "timestamp": 100050,
                    "screenshotPath": "synthetic/frame-0011.png"}
        samples = []
        for at, mono in [(100500, 5000), (100900, 5400)]:
            samples.append({"ownerBefore": asdict(OWNER), "ownerAfter": asdict(OWNER),
                            "readAtMs": at, "monotonicMs": mono, "requestUtf8": prepared["requestUtf8"],
                            "receiptUtf8": json.dumps(receipt), "observationUtf8": json.dumps(observed),
                            "latestObservationUtf8": json.dumps(observed), "heartbeatUtf8": json.dumps(heartbeat(11, at))})
        return {"samples": samples}

    def recover(self, proof=None):
        self.clock = 100900
        return self.make_journal().reconcile(OUTER, OWNER, lambda _: proof or self.proof())

    def assert_global_hold(self):
        other = {**OUTER, "id": "outer-00000002"}
        dispatch = unittest.mock.Mock()
        result = self.make_journal().execute(other, OWNER, dispatch)
        self.assertEqual(result["state"], "held")
        dispatch.assert_not_called()
        self.assertTrue((self.root / "journal" / "active.json").exists())

    def test_prepared_mapping_binds_exact_bytes_and_actual_inner_id(self):
        result = self.journal.execute(OUTER, OWNER, self.dispatch)
        response = subject.validate_prepared_result(result, OUTER, OWNER, {"safeStep"})
        self.assertEqual(response["result"]["submittedId"], inner_request()["id"])
        self.assertEqual(self.prepared()["requestUtf8"].encode(), (self.root / "request.json").read_bytes())
        self.assertFalse((self.root / "journal" / "active.json").exists())

    def test_crash_before_and_during_prepared_mapping_never_redispatches(self):
        for point in ("before-prepared", "after-inner-claim", "after-prepared"):
            with self.subTest(point=point), tempfile.TemporaryDirectory(dir=self.root) as folder:
                journal_dir = Path(folder) / "journal"; journal_dir.mkdir()
                journal = CheckpointJournal(journal_dir, {"safeStep"}, owner_probe=lambda **_: OWNER,
                                           legacy_responses=self.root / "legacy", clock_ms=lambda: 100000)
                journal.crash_at = point
                with self.assertRaises(Crash):
                    journal.execute(OUTER, OWNER, self.dispatch)
                again = subject.PreparedRelayJournal(journal_dir, {"safeStep"}, owner_probe=lambda **_: OWNER,
                                                      legacy_responses=self.root / "legacy", clock_ms=lambda: 100000)
                dispatch = unittest.mock.Mock()
                self.assertEqual(again.execute(OUTER, OWNER, dispatch)["state"], "unknown")
                dispatch.assert_not_called()
                proof = unittest.mock.Mock(side_effect=FileNotFoundError("synthetic missing receipt"))
                self.assertEqual(again.reconcile(OUTER, OWNER, proof)["state"], "held")
                self.assertFalse((self.root / "request.json").exists())

    def test_mapping_storage_failure_stops_submission_and_holds_all_ids(self):
        original = self.journal._new
        def write(name, value):
            if name.endswith(".prepared.json"):
                raise OSError("synthetic full disk")
            return original(name, value)
        with patch.object(self.journal, "_new", side_effect=write):
            self.assertEqual(self.journal.execute(OUTER, OWNER, self.dispatch)["state"], "unknown")
        self.assertFalse((self.root / "request.json").exists())
        self.assertEqual(self.effects, [])
        self.assert_global_hold()

    def test_crash_after_request_write_requires_positive_completion(self):
        with self.assertRaises(Crash):
            self.journal.execute(OUTER, OWNER, lambda *args: self.dispatch(*args, crash="after-request"))
        collector = unittest.mock.Mock(side_effect=FileNotFoundError("synthetic receipt not yet present"))
        self.assertEqual(self.make_journal().reconcile(OUTER, OWNER, collector)["state"], "held")
        self.assert_global_hold()
        result = self.recover()
        self.assertEqual(result["state"], "settled")
        self.assertTrue(result["replayed"])
        self.assertEqual(self.effects, [])  # Reconciliation did not perform the simulated action.

    def test_crash_after_native_completion_recovers_without_another_dispatch(self):
        with self.assertRaises(Crash):
            self.journal.execute(OUTER, OWNER, lambda *args: self.dispatch(*args, crash="after-native"))
        result = self.recover()
        self.assertEqual(result["response"]["result"]["status"], "completed")
        self.assertEqual(len(self.effects), 1)
        self.assertEqual(self.prepared()["innerRequest"]["createdAt"], 100000)
        self.assertTrue(result["response"]["result"]["historicalOutcome"])

    def test_unknown_response_is_preserved_when_recovery_is_saved(self):
        self.start_unknown()
        path = self.root / "journal" / (OUTER["id"] + ".response.json")
        before = path.read_bytes()
        result = self.recover()
        self.assertEqual(result["state"], "settled")
        self.assertEqual(path.read_bytes(), before)
        self.assertTrue((self.root / "journal" / (OUTER["id"] + ".recovery.json")).exists())

    def test_crash_after_outer_response_reuses_durable_result(self):
        self.journal.crash_at = "after-response"
        with self.assertRaises(Crash):
            self.journal.execute(OUTER, OWNER, self.dispatch)
        dispatch = unittest.mock.Mock()
        result = self.make_journal().execute(OUTER, OWNER, dispatch)
        self.assertEqual(result["state"], "settled")
        self.assertTrue(result["replayed"])
        dispatch.assert_not_called()
        self.assertEqual(len(self.effects), 1)

    def test_crash_after_recovery_save_reuses_same_recovery(self):
        self.start_unknown(); self.clock = 100900
        journal = self.make_journal(); journal.crash_at = "after-recovery"
        with self.assertRaises(Crash):
            journal.reconcile(OUTER, OWNER, lambda _: self.proof())
        collector = unittest.mock.Mock()
        result = self.make_journal().reconcile(OUTER, OWNER, collector)
        self.assertEqual(result["state"], "settled")
        collector.assert_not_called()

    def test_owner_changes_before_or_after_mapping_block_request_write(self):
        self.journal.checkpoint_action = lambda point: setattr(self, "current_owner", replace(OWNER, owner_lifetime_binding="b" * 64)) if point == "after-prepared" else None
        result = self.journal.execute(OUTER, OWNER, self.dispatch)
        self.assertEqual(result["state"], "held")
        self.assertFalse((self.root / "request.json").exists())
        self.assertTrue((self.root / "journal" / "active.json").exists())

    def test_recovery_rejects_current_owner_change_without_reading_native_evidence(self):
        self.start_unknown(); self.current_owner = replace(OWNER, process_id=5678)
        collector = unittest.mock.Mock()
        result = self.journal.reconcile(OUTER, OWNER, collector)
        self.assertEqual(result["state"], "held")
        collector.assert_not_called()

    def test_mismatched_or_stale_proofs_keep_the_whole_journal_held(self):
        self.start_unknown(); self.clock = 100900
        def change_json(proof, field, **updates):
            for sample in proof["samples"]:
                value = json.loads(sample[field]); value.update(updates); sample[field] = json.dumps(value)
        mutations = [
            lambda p: change_json(p, "receiptUtf8", id="mission-" + "2" * 32),
            lambda p: change_json(p, "receiptUtf8", session="foreign-session-r3"),
            lambda p: change_json(p, "receiptUtf8", mission="questStep"),
            lambda p: change_json(p, "receiptUtf8", status="running"),
            lambda p: change_json(p, "receiptUtf8", status="failed"),
            lambda p: change_json(p, "observationUtf8", frameId=12),
            lambda p: change_json(p, "observationUtf8", timestamp=99999),
            lambda p: change_json(p, "heartbeatUtf8", heartbeatAt=1),
            lambda p: change_json(p, "heartbeatUtf8", activeRequestId="pending-other"),
            lambda p: change_json(p, "heartbeatUtf8", state="running"),
            lambda p: change_json(p, "heartbeatUtf8", frameId=12),
            lambda p: p["samples"][1].update(monotonicMs=5399),
            lambda p: p["samples"][1].update(readAtMs=100499),
            lambda p: p["samples"][1].update(readAtMs=100901),
            lambda p: p["samples"][0]["ownerBefore"].update(owner_lifetime_binding="c" * 64),
            lambda p: p["samples"][1].update(requestUtf8=p["samples"][1]["requestUtf8"] + " "),
            lambda p: p["samples"][1].update(receiptUtf8=p["samples"][1]["receiptUtf8"] + " "),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                proof = self.proof(); mutate(proof)
                self.assertEqual(self.recover(proof)["state"], "held")
                self.assert_global_hold()

    def test_missing_observation_is_unknown_not_non_submission(self):
        self.start_unknown()
        result = self.journal.reconcile(OUTER, OWNER, lambda _: (_ for _ in ()).throw(FileNotFoundError("expired frame")))
        self.assertEqual(result["state"], "held")
        self.assert_global_hold()

    def test_corrupt_prepared_record_never_recovers(self):
        self.start_unknown()
        (self.root / "journal" / (OUTER["id"] + ".prepared.json")).write_text('{"schema":')
        collector = unittest.mock.Mock()
        self.assertEqual(self.journal.reconcile(OUTER, OWNER, collector)["state"], "held")
        collector.assert_not_called()
        self.assert_global_hold()

    def test_incomplete_recovery_record_is_held_explicitly(self):
        self.start_unknown()
        path = self.root / "journal" / (OUTER["id"] + ".recovery.json")
        path.write_text('{"state":"unknown"}')
        dispatch = unittest.mock.Mock()
        result = self.journal.execute(OUTER, OWNER, dispatch)
        self.assertEqual(result["state"], "held")
        self.assertEqual(result["reason"], "invalid-recovery-record-state")
        dispatch.assert_not_called()
        self.assert_global_hold()

    def test_inner_claim_change_cannot_be_used_for_recovery(self):
        self.start_unknown()
        claim = self.root / "journal" / ("inner-" + inner_request()["id"] + ".claim.json")
        claim.write_text(json.dumps({"binding": "b" * 64, "requestSha256": "c" * 64}))
        collector = unittest.mock.Mock()
        self.assertEqual(self.journal.reconcile(OUTER, OWNER, collector)["state"], "held")
        collector.assert_not_called()
        self.assert_global_hold()

    def test_prepared_readback_failure_stops_before_submission(self):
        def mutate(point):
            if point == "after-prepared":
                (self.root / "journal" / (OUTER["id"] + ".prepared.json")).write_text("{}")
        self.journal.checkpoint_action = mutate
        self.assertEqual(self.journal.execute(OUTER, OWNER, self.dispatch)["state"], "held")
        self.assertFalse((self.root / "request.json").exists())

    def test_saved_recovery_remains_historical_without_refreshing_timestamps(self):
        self.start_unknown(); first = self.recover()
        path = self.root / "journal" / (OUTER["id"] + ".recovery.json")
        raw = path.read_bytes(); self.clock += 100000
        later = self.make_journal().read_result(OUTER, OWNER)
        self.assertTrue(later["replayed"])
        self.assertTrue(later["response"]["result"]["historicalOutcome"])
        self.assertEqual(later["recovery"]["verifiedAtMs"], first["recovery"]["verifiedAtMs"])
        self.assertEqual(later["prepared"]["innerRequest"]["createdAt"], 100000)
        self.assertEqual(path.read_bytes(), raw)

    def test_prepared_callback_cannot_be_reused_after_dispatch(self):
        saved = []
        def dispatch(outer, owner, prepare):
            saved.append(prepare)
            return self.dispatch(outer, owner, prepare)
        self.assertEqual(self.journal.execute(OUTER, OWNER, dispatch)["state"], "settled")
        before = (self.root / "request.json").read_bytes()
        with self.assertRaisesRegex(Held, "single-use"):
            saved[0](json.dumps(inner_request()).encode(), heartbeat())
        self.assertEqual((self.root / "request.json").read_bytes(), before)

    def test_changed_outer_payload_never_dispatches(self):
        self.start_unknown()
        dispatch = unittest.mock.Mock()
        result = self.journal.execute({**OUTER, "frame": 20}, OWNER, dispatch)
        self.assertEqual(result["state"], "held"); dispatch.assert_not_called()

    def test_wrong_inner_step_stops_before_request_write(self):
        outer = {**OUTER, "kind": "questStep", "step": "safeStep"}
        def dispatch(request, owner, prepare):
            inner = inner_request(request); inner["step"] = "otherStep"
            prepare(json.dumps(inner).encode(), heartbeat())
            self.fail("mismatched inner request must not be submitted")
        self.assertEqual(self.journal.execute(outer, OWNER, dispatch)["state"], "unknown")
        self.assert_global_hold()

    def test_existing_inner_id_claim_blocks_another_outer_request(self):
        self.assertEqual(self.journal.execute(OUTER, OWNER, self.dispatch)["state"], "settled")
        other = {**OUTER, "id": "outer-00000002"}
        result = self.journal.execute(other, OWNER, self.dispatch)
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(len(self.effects), 1)

    def test_unmapped_terminal_response_is_not_accepted(self):
        result = self.journal.execute(OUTER, OWNER, lambda *_: self.response(OUTER, inner_request()))
        self.assertEqual(result["state"], "held")
        self.assert_global_hold()

    def test_v4_explicit_archive_deferral_needs_no_inner_request(self):
        def dispatch(*_):
            return {"id": OUTER["id"], "code": 0, "error": None, "output": None,
                    "result": {"session": OWNER.session, "frameId": 10, "status": "deferred",
                               "requestSubmitted": False, "nextAction": "observe",
                               "receiptMaintenance": {"status": "archived"}}}
        result = self.journal.execute(OUTER, OWNER, dispatch)
        self.assertEqual(result["state"], "settled")
        self.assertIsNone(result["prepared"])

    def test_legacy_unbound_response_remains_a_collision_guard(self):
        (self.root / "legacy" / (OUTER["id"] + ".json")).write_text("{}")
        dispatch = unittest.mock.Mock()
        self.assertEqual(self.journal.execute(OUTER, OWNER, dispatch)["state"], "held")
        dispatch.assert_not_called()

    def _assert_legacy_entry_refused(self, metadata, reason):
        target = self.root / "legacy" / (OUTER["id"] + ".json")
        original = b"retained collision evidence"
        target.write_bytes(original)
        real_lstat, real_open, real_exists = Path.lstat, Path.open, Path.exists
        def entry_lstat(path, *args, **kwargs):
            if path == target:
                if isinstance(metadata, Exception):
                    raise metadata
                return metadata
            return real_lstat(path, *args, **kwargs)
        def guarded_open(path, *args, **kwargs):
            self.assertNotEqual(path, target, "invalid legacy evidence must not be opened")
            return real_open(path, *args, **kwargs)
        def dangling_exists(path):
            return False if path == target else real_exists(path)
        dispatch = unittest.mock.Mock()
        with patch.object(Path, "lstat", entry_lstat), patch.object(Path, "open", guarded_open), \
             patch.object(Path, "exists", dangling_exists):
            result = self.journal.execute(OUTER, OWNER, dispatch)
        self.assertEqual((result["state"], result["reason"]), ("held", reason))
        dispatch.assert_not_called()
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual({path.name for path in (self.root / "journal").iterdir()}, {"journal.lock"})
        self.assertFalse((self.root / "request.json").exists())

    def test_prepared_legacy_dangling_entries_refuse_before_dispatch(self):
        for mode, attributes in [(stat.S_IFLNK, 0), (stat.S_IFREG, 0x400)]:
            with self.subTest(mode=mode, attributes=attributes):
                self._assert_legacy_entry_refused(
                    SimpleNamespace(st_mode=mode, st_file_attributes=attributes, st_size=27),
                    "reparse-path-held")

    def test_prepared_legacy_metadata_errors_do_not_mean_absence(self):
        for error in [PermissionError("simulated metadata access failure"), OSError("simulated I/O failure")]:
            with self.subTest(error=type(error).__name__):
                self._assert_legacy_entry_refused(error, "storage-or-response-error")

    def test_real_child_exit_after_request_write_has_one_synthetic_effect(self):
        completed = subprocess.run(child_command("--crash-child", self.root),
                                   capture_output=True, text=True, timeout=10, cwd=self.root, env=child_environment())
        self.assertEqual(completed.returncode, 77, completed.stderr)
        dispatch = unittest.mock.Mock()
        self.assertEqual(self.make_journal().execute(OUTER, OWNER, dispatch)["state"], "unknown")
        dispatch.assert_not_called()
        self.assertEqual(self.recover()["state"], "settled")
        self.assertEqual((self.root / "synthetic-effect-count").read_text(), "1")

    def test_actual_os_lock_excludes_a_second_writer(self):
        child = subprocess.Popen(child_command("--hold-lock", self.root),
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 cwd=self.root, env=child_environment(),
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "ready").exists() and time.monotonic() < deadline:
                self.assertIsNone(child.poll()); time.sleep(0.01)
            self.assertTrue((self.root / "ready").exists())
            dispatch = unittest.mock.Mock()
            result = self.journal.execute(OUTER, OWNER, dispatch)
            self.assertEqual(result["reason"], "journal-busy"); dispatch.assert_not_called()
        finally:
            child.communicate(b"x", timeout=5)
        self.assertEqual(child.returncode, 0)


class CliHookTests(unittest.TestCase):
    # Share fixture helpers without running the protocol cases a second time.
    setUp = PreparedTests.setUp
    make_journal = PreparedTests.make_journal
    prepared = PreparedTests.prepared
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("prepared_candidate_cli", Path(__file__).with_name("act-one-command.py"))
        cls.cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.cli)

    def cli_context(self):
        stack = contextlib.ExitStack()
        root = self.root / "client"; root.mkdir(exist_ok=True)
        (root / "observation.json").write_text(json.dumps({"session": OWNER.session, "frameId": 10, "timestamp": 99900}))
        argv = ["candidate", "observe", "--session", OWNER.session, "--frame", "10",
                "--expected-windows-session-id", "2", "--wait-seconds", "0", "--compact"]
        stack.enter_context(patch.object(sys, "argv", argv))
        stack.enter_context(patch.object(self.cli, "ROOT", root))
        stack.enter_context(patch.object(self.cli, "require_live_controller", return_value=heartbeat()))
        stack.enter_context(patch.object(self.cli, "maintain_receipts_for_controller", return_value={"status": "not_needed"}))
        stack.enter_context(patch.object(self.cli.time, "time", return_value=100.0))
        identity = stack.enter_context(patch.object(self.cli.uuid, "uuid4", return_value=type("UUID", (), {"hex": "1" * 32})()))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        return stack, root, identity

    def test_actual_cli_calls_prepared_hook_before_atomic_request_write(self):
        stack, root, identity = self.cli_context()
        atomic = self.cli.atomic
        def write(path, value, **kwargs):
            self.assertEqual(path.name, "request.json")
            self.assertEqual(self.prepared()["requestUtf8"], json.dumps(value))
            atomic(path, value, **kwargs)
        def dispatch(outer, owner, prepare):
            with patch.object(self.cli, "atomic", side_effect=write):
                self.cli.main(before_request_write=prepare)
            return {"id": outer["id"], "code": 0, "error": None, "result": None, "output": "pending"}
        with stack:
            self.assertEqual(self.journal.execute(OUTER, OWNER, dispatch)["state"], "unknown")
            identity.assert_called_once()
        self.assertEqual((root / "request.json").read_bytes(), self.prepared()["requestUtf8"].encode())

    def test_actual_cli_refuses_missing_ack_before_write(self):
        stack, root, identity = self.cli_context()
        with stack, patch.object(self.cli, "atomic") as writing:
            with self.assertRaisesRegex(RuntimeError, "durably bound"):
                self.cli.main(before_request_write=lambda *_: None)
            writing.assert_not_called(); identity.assert_called_once()
        self.assertFalse((root / "request.json").exists())

    def test_actual_cli_prepared_callback_failure_does_not_submit(self):
        stack, root, identity = self.cli_context()
        with stack, patch.object(self.cli, "atomic") as writing:
            with self.assertRaisesRegex(OSError, "synthetic"):
                self.cli.main(before_request_write=lambda *_: (_ for _ in ()).throw(OSError("synthetic journal failure")))
            writing.assert_not_called(); identity.assert_called_once()

    def test_actual_cli_rejects_mismatched_prepared_ack(self):
        mutations = [lambda ack: ack.update(requestId="mission-" + "2" * 32),
                     lambda ack: ack.update(requestSha256="b" * 64),
                     lambda ack: ack.update(binding="invalid"),
                     lambda ack: ack.update(durable=False)]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                stack, root, identity = self.cli_context()
                def callback(raw, status):
                    ack = {"requestId": json.loads(raw)["id"], "requestSha256": hashlib.sha256(raw).hexdigest(),
                           "binding": "a" * 64, "durable": True, "revalidate": lambda: None}
                    mutate(ack); return ack
                with stack, patch.object(self.cli, "atomic") as writing:
                    with self.assertRaisesRegex(RuntimeError, "durably bound"):
                        self.cli.main(before_request_write=callback)
                    writing.assert_not_called()
                self.assertFalse((root / "request.json").exists())

    def test_actual_cli_archive_deferral_precedes_uuid_and_prepared_hook(self):
        stack, root, identity = self.cli_context()
        argv = ["candidate", "questStep", "--step", "safeStep", "--session", OWNER.session,
                "--frame", "10", "--expected-windows-session-id", "2", "--compact"]
        callback = unittest.mock.Mock()
        with stack, patch.object(sys, "argv", argv), patch.object(self.cli, "atomic") as writing, \
             patch.object(self.cli, "maintain_receipts_for_controller", return_value={"status": "archived"}):
            self.cli.main(before_request_write=callback)
            identity.assert_not_called(); callback.assert_not_called(); writing.assert_not_called()

    def test_actual_cli_owner_change_during_replace_retry_stops_before_second_attempt(self):
        stack, root, identity = self.cli_context()
        calls = []
        def replacing(source, destination):
            calls.append(Path(source).read_bytes())
            self.current_owner = replace(OWNER, owner_lifetime_binding="d" * 64)
            error = OSError("synthetic sharing violation"); error.winerror = 32; raise error
        def dispatch(outer, owner, prepare):
            self.cli.main(before_request_write=prepare)
            self.fail("changed owner must prevent successful replacement")
        with stack, patch.object(self.cli.os, "replace", side_effect=replacing), \
             patch.object(self.cli.time, "sleep", return_value=None):
            result = self.journal.execute(OUTER, OWNER, dispatch)
            self.assertEqual(result["state"], "held")
            identity.assert_called_once()
        self.assertEqual(len(calls), 1)
        self.assertFalse((root / "request.json").exists())
        self.assertEqual((root / "request.pending.json").read_bytes(), self.prepared()["requestUtf8"].encode())
        self.assertTrue((self.root / "journal" / "active.json").exists())

    def test_actual_cli_same_owner_retry_preserves_bytes_and_rechecks_each_attempt(self):
        stack, root, identity = self.cli_context()
        actual_replace = self.cli.os.replace
        events, payloads = [], []
        def owner_probe(**_):
            events.append("owner"); return self.current_owner
        self.journal.owner_probe = owner_probe
        def replacing(source, destination):
            self.assertEqual(events[-1], "owner")
            events.append("replace"); payloads.append(Path(source).read_bytes())
            if len(payloads) == 1:
                error = OSError("synthetic sharing violation"); error.winerror = 32; raise error
            return actual_replace(source, destination)
        def dispatch(outer, owner, prepare):
            self.cli.main(before_request_write=prepare)
            return {"id": outer["id"], "code": 0, "error": None, "result": None, "output": "pending"}
        with stack, patch.object(self.cli.os, "replace", side_effect=replacing), \
             patch.object(self.cli.time, "sleep", return_value=None):
            self.assertEqual(self.journal.execute(OUTER, OWNER, dispatch)["state"], "unknown")
            identity.assert_called_once()
        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[0], payloads[1])
        self.assertEqual((root / "request.json").read_bytes(), payloads[0])
        self.assertEqual(json.loads(payloads[0])["createdAt"], 100000)


    def _retry_after_admission_change(self, current, *, advance_clock=False):
        stack, root, identity = self.cli_context()
        attempts = []
        def replacing(source, destination):
            attempts.append(Path(source).read_bytes())
            if advance_clock:
                self.clock = 106000
            error = OSError("synthetic sharing violation"); error.winerror = 32; raise error
        def dispatch(outer, owner, prepare):
            self.cli.main(before_request_write=prepare)
            self.fail("changed admission must stop replacement")
        with stack, patch.object(self.cli, "require_live_controller", side_effect=[heartbeat(), heartbeat(), current]) as gate, \
             patch.object(self.cli.os, "replace", side_effect=replacing), \
             patch.object(self.cli.time, "sleep", return_value=None):
            result = self.journal.execute(OUTER, OWNER, dispatch)
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(gate.call_count, 3)
        identity.assert_called_once()
        self.assertEqual(len(attempts), 1)
        self.assertFalse((root / "request.json").exists())
        self.assertEqual((root / "request.pending.json").read_bytes(), attempts[0])
        self.assertEqual(json.loads(attempts[0])["createdAt"], 100000)
        self.assertTrue((self.root / "journal" / "active.json").exists())

    def test_actual_cli_busy_current_state_stops_same_owner_retry(self):
        self._retry_after_admission_change({**heartbeat(), "state": "running", "activeRequestId": "mission-" + "2" * 32})

    def test_actual_cli_current_frame_change_stops_same_owner_retry(self):
        self._retry_after_admission_change(heartbeat(frame=11))

    def test_actual_cli_fresh_heartbeat_cannot_renew_expired_original_gate(self):
        self._retry_after_admission_change(heartbeat(at=106000), advance_clock=True)

    def test_actual_cli_fresh_native_admission_rejection_prevents_replacement(self):
        stack, root, identity = self.cli_context()
        admission_checks = []
        def owner_probe(*, current_admission=None):
            if current_admission is not None:
                admission_checks.append(current_admission)
                self.assertEqual(current_admission, heartbeat())
                raise Held("synthetic-native-status-no-longer-owned")
            return self.current_owner
        self.journal.owner_probe = owner_probe
        def dispatch(outer, owner, prepare):
            self.cli.main(before_request_write=prepare)
            self.fail("native admission rejection must stop replacement")
        with stack, patch.object(self.cli.os, "replace") as replacing:
            result = self.journal.execute(OUTER, OWNER, dispatch)
            replacing.assert_not_called()
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(len(admission_checks), 1)
        identity.assert_called_once()
        self.assertFalse((root / "request.json").exists())
        self.assertTrue((self.root / "journal" / "active.json").exists())


    def test_actual_atomic_slow_retry_validation_cannot_cross_original_deadline(self):
        path = self.root / "request.json"
        value = inner_request()
        clock, validations, attempts = [0.0], [], []
        error = OSError("synthetic sharing violation"); error.winerror = 32
        def validate():
            validations.append(clock[0])
            if len(validations) == 2:
                clock[0] += 2.0
        def replacing(source, destination):
            attempts.append(clock[0])
            if len(attempts) == 1:
                raise error
            self.fail("no retry may replace after its original deadline")
        def sleep(seconds):
            clock[0] += seconds
        with patch.object(self.cli.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(self.cli.time, "sleep", side_effect=sleep), \
             patch.object(self.cli.os, "replace", side_effect=replacing):
            with self.assertRaises(OSError) as raised:
                self.cli.atomic(path, value, before_replace=validate)
        self.assertIs(raised.exception, error)
        self.assertEqual(attempts, [0.0])
        self.assertEqual(len(validations), 2)
        self.assertEqual(clock[0], 2.05)
        self.assertFalse(path.exists())
        self.assertEqual(json.loads(path.with_suffix(".pending.json").read_text()), value)

    def test_actual_atomic_preserves_first_attempt_after_slow_validation(self):
        path = self.root / "request.json"
        value = inner_request()
        clock, attempts = [0.0], []
        actual_replace = self.cli.os.replace
        def validate():
            clock[0] += 2.0
        def replacing(source, destination):
            attempts.append(clock[0]); actual_replace(source, destination)
        with patch.object(self.cli.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(self.cli.os, "replace", side_effect=replacing):
            self.cli.atomic(path, value, before_replace=validate)
        self.assertEqual(attempts, [2.0])
        self.assertEqual(json.loads(path.read_text()), value)


    def test_actual_cli_original_heartbeat_alias_cannot_renew_expired_gate(self):
        """A caller's later mutation cannot refresh the original pre-write admission."""
        stack, root, identity = self.cli_context()
        def dispatch(outer, owner, prepare):
            def wrapped(raw, original_heartbeat):
                ack = prepare(raw, original_heartbeat)
                self.clock = 106000
                original_heartbeat["heartbeatAt"] = self.clock
                return ack
            self.cli.main(before_request_write=wrapped)
            self.fail("the original six-second-old heartbeat must refuse publication")
        with stack, patch.object(self.cli.time, "time", side_effect=lambda: self.clock / 1000), \
             patch.object(self.cli, "require_live_controller", side_effect=[heartbeat(), heartbeat(at=106000)]), \
             patch.object(self.cli.os, "replace") as replacing:
            result = self.journal.execute(OUTER, OWNER, dispatch)
            replacing.assert_not_called()
            identity.assert_called_once()
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["response"]["error"], "dispatch-Held")
        self.assertFalse((root / "request.json").exists())
        self.assertEqual(self.prepared()["innerRequest"]["createdAt"], 100000)
        self.assertEqual((root / "request.pending.json").read_bytes(), self.prepared()["requestUtf8"].encode())
        self.assertTrue((self.root / "journal/active.json").exists())

    def test_actual_cli_snapshot_precedes_blocking_owner_probe(self):
        """The first owner check cannot mutate a borrowed heartbeat into a fresh admission."""
        stack, root, identity = self.cli_context()
        supplied = []
        def owner_probe(**_):
            if supplied:
                self.clock = 106000
                supplied[0]["heartbeatAt"] = self.clock
            return self.current_owner
        self.journal.owner_probe = owner_probe
        def dispatch(outer, owner, prepare):
            def wrapped(raw, original_heartbeat):
                supplied.append(original_heartbeat)
                return prepare(raw, original_heartbeat)
            self.cli.main(before_request_write=wrapped)
            self.fail("expired initial admission must not prepare or submit")
        with stack, patch.object(self.cli.time, "time", side_effect=lambda: self.clock / 1000), \
             patch.object(self.cli.os, "replace") as replacing:
            result = self.journal.execute(OUTER, OWNER, dispatch)
            replacing.assert_not_called()
            identity.assert_called_once()
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["response"]["error"], "dispatch-Held")
        self.assertFalse((root / "request.json").exists())
        self.assertFalse((self.root / "journal" / (OUTER["id"] + ".prepared.json")).exists())
        self.assertTrue((self.root / "journal/active.json").exists())


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ("--crash-child", "--hold-lock"):
        child_mode(sys.argv[1], sys.argv[2])
    else:
        unittest.main(verbosity=2)
