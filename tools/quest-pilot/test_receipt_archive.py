"""Offline failure-path tests; all mutable fixtures live in isolated local scratch."""
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import receipt_archive as subject

SCRATCH = Path(os.environ.get("RECEIPT_ARCHIVE_TEST_TMP", tempfile.gettempdir()))


class ReceiptArchiveTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(subject.time, "time", return_value=1000.0)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="receipt-archive-test-", dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "runtime" / "User" / "JsScript" / "ActOnePilot"
        self.root.mkdir(parents=True)
        self.archive = self.base / "archives"
        self.status = {"version": 1, "session": "active", "processId": 42,
                       "windowsSessionId": 2, "state": "idle", "activeRequestId": None,
                       "error": None, "frameId": 7, "heartbeatAt": int(time.time() * 1000)}
        self.write_status()
        self.put_json(self.root / "request.json", {"id": "mission-current", "session": "active"})
        self.add_receipts("active", 1)
        self.add_receipts("closed", 3)
        self.image = self.root / "observations" / "active" / "frame-0007.png"
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b"frozen-game-image-must-not-change")
        self.source = self.root / "mission.js"
        self.source.write_bytes(b"// current owner overlay must not change")
        self.write_pause_boundary()

    @staticmethod
    def put_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def write_status(self):
        self.status["heartbeatAt"] = int(time.time() * 1000)
        self.put_json(self.root / "controller-status.json", self.status)

    def add_receipts(self, session, count):
        for i in range(count):
            identity = f"mission-{i:05d}"
            self.put_json(self.root / "receipts" / session / (identity + ".json"),
                          {"session": session, "id": identity, "status": "completed",
                           "frameId": i, "details": {"retained": "original evidence"}})

    def write_pause_boundary(self):
        request = {"id": "mission-00000", "session": "active", "mission": "observe", "createdAt": 999000}
        self.put_json(self.root / "request.json", request)
        self.put_json(self.root / "receipts" / "active" / "mission-00000.json",
                      {"id": request["id"], "session": "active", "mission": "observe",
                       "status": "completed", "frameId": 7, "timestamp": 1000000})
        observation = {"session": "active", "frameId": 7, "timestamp": 999500,
                       "screenshotPath": "observations/active/frame-0007.png",
                       "hud": {"auto": False, "dialogueReady": False, "world": False, "health": None,
                               "captureStamp": {"session": "active", "frameId": 7,
                                                "capturedAt": 999400, "source": "game-capture-start"}},
                       "ocr": [{"text": "Food", "x": 144, "y": 28},
                               {"text": "Inventory capacity 487/26000", "x": 1480, "y": 29}]}
        self.put_json(self.root / "observation.json", observation)
        self.put_json(self.root / "observations" / "active" / "frame-0007.json", observation)

    def run_maintenance(self, **kwargs):
        self.write_status()
        return subject.maintain(self.root, self.archive, "active", 42, 2,
                                trigger_files=kwargs.pop("trigger_files", 4),
                                target_files=kwargs.pop("target_files", 2), **kwargs)

    def fingerprints(self, directory):
        return {p.relative_to(directory).as_posix(): subject._digest(p)
                for p in directory.rglob("*") if p.is_file()}

    def native_ui_observation(self):
        """Match engine.observe's serialized fields and bgi's UI-only provenance."""
        observation = subject._json(self.root / "observation.json")
        observation["hud"].pop("captureStamp")
        observation["map"] = None
        observation["uiObservation"] = {"version": 1, "kind": "inventory-ui-only-v1",
            "mapOmitted": True, "orientationOmitted": True, "observationStartedAtUnixMs": 999400}
        observation["timings"] = {"totalMs": 100, "mapDiagnostic": {
            "reason": "Inventory UI-only v1: map and orientation deliberately omitted",
            "mode": "inventory-ui-only-v1"}}
        return observation

    def retain_observation(self, observation):
        """Retain both canonical observation publications without changing receipts."""
        self.put_json(self.root / "observation.json", observation)
        self.put_json(self.root / "observations" / "active" / "frame-0007.json", observation)

    def test_native_ui_only_padded_frame_archives_with_original_capture_start(self):
        observation = self.native_ui_observation()
        self.retain_observation(observation)
        active_before = self.fingerprints(self.root / "receipts" / "active")
        evidence_before = self.fingerprints(self.root / "observations")
        result = self.run_maintenance()
        self.assertEqual(result["status"], "archived")
        self.assertEqual(result["pauseBoundary"]["originalCaptureAt"], 999400)
        self.assertEqual(result["pauseBoundary"]["originalObservationAt"], 999500)
        self.assertEqual(self.fingerprints(self.root / "receipts" / "active"), active_before)
        self.assertEqual(self.fingerprints(self.root / "observations"), evidence_before)
        self.assertNotIn("captureStamp", observation["hud"])
        self.assertNotIn("capturedAt", observation)

    def test_native_ui_only_rejects_incomplete_or_changed_provenance(self):
        mutations = (
            lambda row: row.pop("uiObservation"),
            lambda row: row["uiObservation"].update(version=True),
            lambda row: row["uiObservation"].update(kind="other-mode"),
            lambda row: row["uiObservation"].update(mapOmitted=False),
            lambda row: row["uiObservation"].update(orientationOmitted=False),
            lambda row: row["uiObservation"].update(extra=True),
            lambda row: row["uiObservation"].update(observationStartedAtUnixMs=True),
            lambda row: row["uiObservation"].update(observationStartedAtUnixMs=998999),
            lambda row: row["uiObservation"].update(observationStartedAtUnixMs=999501),
            lambda row: row.update(map={"x": 0, "y": 0}),
            lambda row: row.pop("map"),
            lambda row: row["hud"].update(compassAngle=0),
            lambda row: row["timings"].pop("mapDiagnostic"),
        )
        before = self.fingerprints(self.root / "receipts")
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                observation = self.native_ui_observation()
                mutate(observation)
                self.retain_observation(observation)
                result = self.run_maintenance()
                self.assertEqual(result["status"], "deferred_until_inventory_pause")
                self.assertEqual(self.fingerprints(self.root / "receipts"), before)
                self.assertFalse(self.archive.exists())
                self.write_pause_boundary()

    def test_native_ui_only_does_not_fall_back_to_publish_or_private_timestamp(self):
        observation = self.native_ui_observation()
        observation.pop("uiObservation")
        observation["timings"].pop("mapDiagnostic")
        observation["capturedAt"] = 999400  # Not part of the serialized producer contract.
        self.retain_observation(observation)
        self.assertEqual(self.run_maintenance()["status"], "deferred_until_inventory_pause")
        self.assertFalse(self.archive.exists())

    def test_native_ui_only_and_legacy_capture_stamps_must_agree(self):
        observation = self.native_ui_observation()
        stamp = {"session": "active", "frameId": 7, "capturedAt": 999400,
                 "source": "game-capture-start"}
        observation["hud"]["captureStamp"] = stamp
        self.retain_observation(observation)
        binding = subject._fence(self.root, "active", 42, 2)
        self.assertEqual(subject._pause_boundary(self.root, binding)["originalCaptureAt"], 999400)
        for key, value in (("capturedAt", 999399), ("capturedAt", True),
                           ("session", "foreign"), ("frameId", 8)):
            with self.subTest(key=key, value=value):
                changed = json.loads(json.dumps(observation))
                changed["hud"]["captureStamp"][key] = value
                self.retain_observation(changed)
                with self.assertRaises(subject.PauseBoundaryUnavailable):
                    subject._pause_boundary(self.root, binding)
        self.assertFalse(self.archive.exists())

    def test_native_ui_only_marker_cannot_be_stripped_into_legacy_branch(self):
        observation = self.native_ui_observation()
        observation["hud"]["captureStamp"] = {"session": "active", "frameId": 7,
            "capturedAt": 999400, "source": "game-capture-start"}
        observation.pop("uiObservation")
        self.retain_observation(observation)
        self.assertEqual(self.run_maintenance()["status"], "deferred_until_inventory_pause")
        self.assertFalse(self.archive.exists())

    def test_unpadded_observation_alias_is_not_accepted_as_native_frame(self):
        observation = self.native_ui_observation()
        observation["screenshotPath"] = "observations/active/frame-7.png"
        self.retain_observation(observation)
        canonical = self.root / "observations" / "active" / "frame-0007.json"
        canonical.rename(canonical.with_name("frame-7.json"))
        self.assertEqual(self.run_maintenance()["status"], "deferred_until_inventory_pause")
        self.assertFalse(self.archive.exists())

    def test_actual_caller_native_ui_archive_still_defers_gameplay_before_uuid(self):
        self.retain_observation(self.native_ui_observation())
        path = Path(__file__).with_name("act-one-command.py")
        spec = importlib.util.spec_from_file_location("native_ui_archive_command", path)
        command = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(command)
        command._receipt_archive_module = subject
        self.assertEqual(command.observation_path(self.root, "active-session", 7).name, "frame-0007.json")
        inventory = subject._inventory(self.root / "receipts")
        def inventory_pressure(path):
            count, size, candidates = inventory if (self.root / "receipts" / "closed").exists() else (1, 1, [])
            return (3000 if count > 1 else count), size, candidates
        argv = ["candidate", "questStep", "--step", "natlanStoryDainBattle", "--session", "active",
                "--frame", "7", "--expected-windows-session-id", "2", "--compact"]
        with patch.object(sys, "argv", argv), patch.object(command, "ROOT", self.root), \
             patch.object(command, "require_live_controller", return_value=self.status), \
             patch.object(subject, "_inventory", side_effect=inventory_pressure), \
             patch.object(command.uuid, "uuid4") as identity, patch.object(command, "atomic") as writing, \
             patch("builtins.print") as printing:
            command.main()
            identity.assert_not_called()
            writing.assert_not_called()
            result = json.loads(printing.call_args_list[-1].args[0])
        self.assertEqual(result["status"], "deferred")
        self.assertEqual(result["nextAction"], "observe")
        self.assertFalse(result["requestSubmitted"])
        self.assertTrue((self.root / "receipts" / "active").exists())
        self.assertFalse((self.root / "receipts" / "closed").exists())

    def test_verified_originals_retired_and_only_duplicate_copies_cleaned(self):
        before = self.fingerprints(self.root / "receipts")
        result = self.run_maintenance()
        self.assertEqual(result["status"], "archived")
        self.assertEqual(result["remainingReceipts"], 1)
        batch = Path(result["manifest"]).parent
        archived = self.fingerprints(batch / "sessions")
        self.assertEqual(archived, {k: v for k, v in before.items() if k.startswith("closed/")})
        self.assertEqual(self.fingerprints(self.root / "receipts"),
                         {k: v for k, v in before.items() if k.startswith("active/")})
        self.assertFalse((batch / "retained-copy").exists())
        self.assertFalse((self.archive / "pending.json").exists())
        self.assertEqual(self.image.read_bytes(), b"frozen-game-image-must-not-change")
        self.assertEqual(self.source.read_bytes(), b"// current owner overlay must not change")
        self.assertEqual(self.run_maintenance()["status"], "not_needed")

    def test_4095_file_recurrence_fixture_releases_capacity_without_active_loss(self):
        for path in (self.root / "receipts" / "closed").iterdir():
            path.unlink()
        for path in (self.root / "receipts" / "active").iterdir():
            path.unlink()
        self.add_receipts("closed", 2191)
        self.add_receipts("active", 1904)
        self.write_pause_boundary()
        active_before = self.fingerprints(self.root / "receipts" / "active")
        count_before = sum(1 for _ in (self.root / "receipts").rglob("*.json"))
        self.assertEqual(count_before, 4095)
        # This is the observed native MaxFiles - 1 admission boundary. Native
        # code is unchanged; this test exercises real filesystem preservation.
        self.assertGreaterEqual(count_before, 4096 - 1)
        result = self.run_maintenance(trigger_files=3000, target_files=2000)
        self.assertEqual(result["archivedReceipts"], 2191)
        self.assertEqual(result["remainingReceipts"], 1904)
        self.assertLess(result["remainingReceipts"], 4096 - 1)
        self.assertEqual(self.fingerprints(self.root / "receipts" / "active"), active_before)
        manifest = subject._json(Path(result["manifest"]))
        subject._verify(Path(result["manifest"]).parent / "sessions" / "closed",
                        manifest["sessions"]["closed"])

    def test_copy_failure_leaves_all_originals_and_retry_is_idempotent(self):
        before = self.fingerprints(self.root / "receipts")
        real = subject._copy_receipt
        calls = 0
        def fail_second(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated copy interruption")
            return real(*args)
        with patch.object(subject, "_copy_receipt", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "copy interruption"):
                self.run_maintenance()
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)
        result = self.run_maintenance()
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["archivedReceipts"], 3)

    def test_corrupt_retained_copy_never_retires_originals(self):
        before = self.fingerprints(self.root / "receipts")
        real = subject._copy_receipt
        def corrupt(source, target, expected):
            real(source, target, expected)
            target.write_bytes(b"corrupt copy")
        with patch.object(subject, "_copy_receipt", side_effect=corrupt):
            with self.assertRaises(subject.ArchiveBlocked):
                self.run_maintenance()
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)

    def test_changed_current_request_blocks_commit(self):
        before = self.fingerprints(self.root / "receipts")
        real = subject._copy_receipt
        def changed(*args):
            real(*args)
            self.put_json(self.root / "request.json", {"id": "mission-new", "session": "active"})
        with patch.object(subject, "_copy_receipt", side_effect=changed):
            with self.assertRaisesRegex(subject.ArchiveBlocked, "current request changed"):
                self.run_maintenance()
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)

    def test_controller_session_change_blocks_commit(self):
        before = self.fingerprints(self.root / "receipts")
        real = subject._copy_receipt
        def changed(*args):
            real(*args)
            self.status["session"] = "next-session"
            self.write_status()
        with patch.object(subject, "_copy_receipt", side_effect=changed):
            with self.assertRaises(subject.ArchiveBlocked):
                self.run_maintenance()
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)

    def test_current_request_session_is_protected_even_when_not_active(self):
        self.put_json(self.root / "request.json", {"id": "mission-prior", "session": "closed"})
        before = self.fingerprints(self.root / "receipts")
        self.assertEqual(self.run_maintenance()["status"], "deferred_no_closed_capacity")
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)

    def test_all_active_soft_capacity_defers_and_preserves_everything(self):
        for path in (self.root / "receipts" / "closed").iterdir():
            path.unlink()
        (self.root / "receipts" / "closed").rmdir()
        self.add_receipts("active", 4)
        before = self.fingerprints(self.root / "receipts")
        self.assertEqual(self.run_maintenance()["status"], "deferred_no_closed_capacity")
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)
        self.assertFalse(self.archive.exists())

    def test_actual_caller_all_active_soft_headroom_defers_archive_and_submits(self):
        for path in (self.root / "receipts" / "closed").iterdir():
            path.unlink()
        (self.root / "receipts" / "closed").rmdir()
        boundary = subject._fence(self.root, "active", 42, 2)
        self.assertEqual(subject._pause_boundary(self.root, boundary)["kind"], "inventory")
        before = self.fingerprints(self.root / "receipts")
        real_inventory = subject._inventory(self.root / "receipts")
        path = Path(__file__).with_name("act-one-command.py")
        spec = importlib.util.spec_from_file_location("all_active_soft_command", path)
        command = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(command)
        command._receipt_archive_module = subject
        actual_maintenance = command.maintain_receipts_for_controller
        results = []
        def recorded_maintenance(*args):
            result = actual_maintenance(*args)
            results.append(result)
            return result
        argv = ["candidate", "observe", "--session", "active", "--frame", "7",
                "--expected-windows-session-id", "2"]
        for count in (3000, 4093):
            with self.subTest(receiptCount=count), patch.object(sys, "argv", argv), \
                 patch.object(command, "ROOT", self.root), \
                 patch.object(command, "require_live_controller", return_value=self.status), \
                 patch.object(command, "maintain_receipts_for_controller", side_effect=recorded_maintenance), \
                 patch.object(subject, "_inventory", return_value=(count, real_inventory[1], real_inventory[2])), \
                 patch.object(command.uuid, "uuid4", return_value=type("UUID", (), {"hex": "unique"})()) as identity, \
                 patch.object(command, "atomic", side_effect=RuntimeError("offline normal submission")) as writing:
                with self.assertRaisesRegex(RuntimeError, "offline normal submission"):
                    command.main()
                identity.assert_called_once()
                writing.assert_called_once()
                self.assertEqual(results[-1]["status"], "deferred_no_closed_capacity")
                self.assertFalse(results[-1]["archiveStarted"])
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)
        self.assertFalse((self.base / "receipt-archives").exists())

    def test_actual_caller_all_active_hard_headroom_blocks_uuid_and_write(self):
        for path in (self.root / "receipts" / "closed").iterdir():
            path.unlink()
        (self.root / "receipts" / "closed").rmdir()
        boundary = subject._fence(self.root, "active", 42, 2)
        self.assertEqual(subject._pause_boundary(self.root, boundary)["kind"], "inventory")
        before = self.fingerprints(self.root / "receipts")
        real_inventory = subject._inventory(self.root / "receipts")
        path = Path(__file__).with_name("act-one-command.py")
        spec = importlib.util.spec_from_file_location("all_active_hard_command", path)
        command = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(command)
        command._receipt_archive_module = subject
        argv = ["candidate", "observe", "--session", "active", "--frame", "7",
                "--expected-windows-session-id", "2"]
        for count in (4094, 4095):
            with self.subTest(receiptCount=count), patch.object(sys, "argv", argv), \
                 patch.object(command, "ROOT", self.root), \
                 patch.object(command, "require_live_controller", return_value=self.status), \
                 patch.object(subject, "_inventory", return_value=(count, real_inventory[1], real_inventory[2])), \
                 patch.object(command.uuid, "uuid4") as identity, patch.object(command, "atomic") as writing:
                with self.assertRaisesRegex(SystemExit, "sole owner must establish"):
                    command.main()
                identity.assert_not_called()
                writing.assert_not_called()
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)
        self.assertFalse((self.base / "receipt-archives").exists())

    def test_actual_caller_exact_native_byte_headroom_and_one_byte_over(self):
        for path in (self.root / "receipts" / "closed").iterdir():
            path.unlink()
        (self.root / "receipts" / "closed").rmdir()
        before = self.fingerprints(self.root / "receipts")
        inventory = subject._inventory(self.root / "receipts")
        boundary = 64 * 1024 * 1024 - 16 * 1024 * 1024 - 128 * 1024
        self.assertEqual(boundary, 50200576)
        self.assertLess(boundary + 1, subject.TRIGGER_BYTES)
        path = Path(__file__).with_name("act-one-command.py")
        spec = importlib.util.spec_from_file_location("exact_byte_boundary_command", path)
        command = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(command)
        command._receipt_archive_module = subject
        actual_maintenance = command.maintain_receipts_for_controller
        results = []
        def recorded_maintenance(*args):
            result = actual_maintenance(*args)
            results.append(result)
            return result
        argv = ["candidate", "observe", "--session", "active", "--frame", "7",
                "--expected-windows-session-id", "2"]
        for size in (boundary - 1, boundary, boundary + 1):
            with self.subTest(receiptBytes=size), patch.object(sys, "argv", argv), \
                 patch.object(command, "ROOT", self.root), \
                 patch.object(command, "require_live_controller", return_value=self.status), \
                 patch.object(command, "maintain_receipts_for_controller", side_effect=recorded_maintenance), \
                 patch.object(subject, "_inventory", return_value=(1, size, inventory[2])), \
                 patch.object(command.uuid, "uuid4", return_value=type("UUID", (), {"hex": "unique"})()) as identity, \
                 patch.object(command, "atomic", side_effect=RuntimeError("offline byte-boundary submission")) as writing:
                if size <= boundary:
                    with self.assertRaisesRegex(RuntimeError, "offline byte-boundary submission"):
                        command.main()
                    identity.assert_called_once()
                    writing.assert_called_once()
                    self.assertEqual(results[-1]["status"], "not_needed")
                else:
                    with self.assertRaisesRegex(SystemExit, "before request creation"):
                        command.main()
                    identity.assert_not_called()
                    writing.assert_not_called()
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)
        self.assertFalse((self.base / "receipt-archives").exists())

    def test_busy_controller_never_starts_archiving(self):
        self.status.update(state="running", activeRequestId="mission-inflight")
        before = self.fingerprints(self.root / "receipts")
        with self.assertRaises(subject.ArchiveBlocked):
            self.run_maintenance()
        self.assertFalse(self.archive.exists())
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)

    def test_below_trigger_does_not_hash_receipt_contents_or_write_archive(self):
        with patch.object(subject, "_digest", side_effect=AssertionError("no content hash on fast path")):
            self.assertEqual(self.run_maintenance(trigger_files=10, target_files=2)["status"], "not_needed")
        self.assertFalse(self.archive.exists())

    def test_transient_heartbeat_json_rewrite_is_bounded_and_recovers(self):
        real = subject._json
        attempts = []
        def read_once_partial(path):
            if path.name == "controller-status.json":
                attempts.append(path)
                if len(attempts) == 1:
                    raise json.JSONDecodeError("simulated heartbeat rewrite", "", 0)
            return real(path)
        with patch.object(subject, "_json", side_effect=read_once_partial), \
             patch.object(subject.time, "sleep") as sleep:
            self.assertEqual(self.run_maintenance(trigger_files=10)["status"], "not_needed")
            sleep.assert_called_once_with(0.05)
        self.assertEqual(len(attempts), 3)  # Retry plus final unchanged-owner readback.

    def test_permanent_invalid_heartbeat_stops_after_three_reads(self):
        with patch.object(subject, "_json", side_effect=json.JSONDecodeError("partial", "", 0)) as reading, \
             patch.object(subject.time, "sleep") as sleep:
            with self.assertRaises(json.JSONDecodeError):
                self.run_maintenance(trigger_files=10)
            self.assertEqual(reading.call_count, 3)
            self.assertEqual(sleep.call_count, 2)
        self.assertFalse(self.archive.exists())

    def test_heartbeat_access_denial_is_not_retried(self):
        denied = OSError("simulated access denied")
        denied.winerror = 5
        with patch.object(subject, "_json", side_effect=denied) as reading, \
             patch.object(subject.time, "sleep") as sleep:
            with self.assertRaises(OSError):
                self.run_maintenance(trigger_files=10)
            self.assertEqual(reading.call_count, 1)
            sleep.assert_not_called()

    def test_unpaused_soft_boundary_defers_without_writes(self):
        observation = subject._json(self.root / "observation.json")
        observation["ocr"] = []
        self.put_json(self.root / "observation.json", observation)
        self.put_json(self.root / "observations" / "active" / "frame-0007.json", observation)
        preserved = self.fingerprints(self.root)
        result = self.run_maintenance()
        self.assertEqual(result["status"], "deferred_until_inventory_pause")
        self.assertFalse(result["archiveStarted"])
        self.assertEqual(self.fingerprints(self.root), preserved)
        self.assertFalse(self.archive.exists())

    def test_unpaused_hard_boundary_blocks_before_actual_caller_uuid(self):
        observation = subject._json(self.root / "observation.json")
        observation["hud"]["world"] = True
        self.put_json(self.root / "observation.json", observation)
        self.put_json(self.root / "observations" / "active" / "frame-0007.json", observation)
        real_inventory = subject._inventory(self.root / "receipts")
        path = Path(__file__).with_name("act-one-command.py")
        spec = importlib.util.spec_from_file_location("hard_boundary_command", path)
        command = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(command)
        command._receipt_archive_module = subject
        argv = ["candidate", "observe", "--session", "active", "--frame", "7",
                "--expected-windows-session-id", "2"]
        with patch.object(sys, "argv", argv), patch.object(command, "ROOT", self.root), \
             patch.object(command, "require_live_controller", return_value=self.status), \
             patch.object(subject, "_inventory", return_value=(4095, real_inventory[1], real_inventory[2])), \
             patch.object(command.uuid, "uuid4") as identity, patch.object(command, "atomic") as writing:
            with self.assertRaisesRegex(SystemExit, "verified completed inventory pause"):
                command.main()
            identity.assert_not_called()
            writing.assert_not_called()
        self.assertFalse((self.base / "receipt-archives").exists())

    def test_final_receipt_mismatch_defers_maintenance(self):
        path = self.root / "receipts" / "active" / "mission-00000.json"
        receipt = subject._json(path)
        receipt["frameId"] = 6
        self.put_json(path, receipt)
        self.assertEqual(self.run_maintenance()["status"], "deferred_until_inventory_pause")
        self.assertFalse(self.archive.exists())

    def test_immutable_inventory_mismatch_defers_maintenance(self):
        path = self.root / "observations" / "active" / "frame-0007.json"
        observation = subject._json(path)
        observation["timestamp"] -= 1
        self.put_json(path, observation)
        self.assertEqual(self.run_maintenance()["status"], "deferred_until_inventory_pause")
        self.assertFalse(self.archive.exists())

    def test_pause_evidence_change_during_copy_preserves_originals(self):
        before = self.fingerprints(self.root / "receipts")
        real = subject._copy_receipt
        def change_evidence(*args):
            real(*args)
            observation = subject._json(self.root / "observation.json")
            observation["ocr"][0]["text"] = "Weapons"
            self.put_json(self.root / "observation.json", observation)
            self.put_json(self.root / "observations" / "active" / "frame-0007.json", observation)
        with patch.object(subject, "_copy_receipt", side_effect=change_evidence):
            with self.assertRaisesRegex(subject.ArchiveBlocked, "pause evidence changed"):
                self.run_maintenance()
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)

    def test_paused_archive_retains_original_capture_time(self):
        before = self.fingerprints(self.root / "observations")
        result = self.run_maintenance()
        self.assertEqual(result["pauseBoundary"]["originalCaptureAt"], 999400)
        self.assertEqual(result["pauseBoundary"]["originalObservationAt"], 999500)
        self.assertTrue(result["freshObservationRequiredBeforeInput"])
        self.assertEqual(self.fingerprints(self.root / "observations"), before)

    def test_actual_caller_blocks_changed_noop_frame_request_or_state_before_uuid(self):
        path = Path(__file__).with_name("act-one-command.py")
        spec = importlib.util.spec_from_file_location("noop_candidate_command", path)
        command = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(command)
        command._receipt_archive_module = subject
        self.put_json(self.root / "observation.json", {"session": "active", "frameId": 7})
        original_status = dict(self.status)
        real = subject._inventory
        argv = ["candidate", "observe", "--session", "active", "--frame", "7",
                "--expected-windows-session-id", "2"]
        for change in ("frame", "request", "state"):
            with self.subTest(change=change):
                self.status = dict(original_status)
                self.write_status()
                self.put_json(self.root / "request.json", {"id": "mission-current", "session": "active"})
                def changed_during_inventory(receipts):
                    result = real(receipts)
                    if change == "frame":
                        self.status["frameId"] = 8
                        self.write_status()
                    elif change == "state":
                        self.status.update(state="running", activeRequestId="mission-other")
                        self.write_status()
                    else:
                        self.put_json(self.root / "request.json", {"id": "mission-other", "session": "active"})
                    return result
                with patch.object(sys, "argv", argv), patch.object(command, "ROOT", self.root), \
                     patch.object(command, "require_live_controller", return_value=original_status), \
                     patch.object(subject, "_inventory", side_effect=changed_during_inventory), \
                     patch.object(command.uuid, "uuid4") as identity, patch.object(command, "atomic") as writing:
                    with self.assertRaisesRegex(SystemExit, "before request creation"):
                        command.main()
                    identity.assert_not_called()
                    writing.assert_not_called()
        self.assertFalse((self.base / "receipt-archives").exists())

    def test_low_disk_copy_headroom_preserves_originals(self):
        before = self.fingerprints(self.root / "receipts")
        fake = type("Usage", (), {"free": 2 * 1024 * 1024 * 1024})()
        with patch.object(subject.shutil, "disk_usage", return_value=fake):
            with self.assertRaisesRegex(subject.ArchiveBlocked, "headroom"):
                self.run_maintenance()
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)

    def test_retry_budget_is_three_attempts(self):
        before = self.fingerprints(self.root / "receipts")
        with patch.object(subject, "_copy_receipt", side_effect=OSError("copy unavailable")) as copying:
            for _ in range(3):
                with self.assertRaises(OSError):
                    self.run_maintenance()
            with self.assertRaisesRegex(subject.ArchiveBlocked, "three attempts"):
                self.run_maintenance()
            self.assertEqual(copying.call_count, 3)
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)

    def test_interruption_after_atomic_retirement_resumes_without_duplicate_loss(self):
        real = subject._verify
        fired = False
        def fail_after_rename(directory, entries):
            nonlocal fired
            real(directory, entries)
            if "sessions" in directory.parts and not fired:
                fired = True
                raise OSError("simulated interruption after original retirement")
        with patch.object(subject, "_verify", side_effect=fail_after_rename):
            with self.assertRaisesRegex(OSError, "after original retirement"):
                self.run_maintenance()
        self.assertFalse((self.root / "receipts" / "closed").exists())
        self.assertEqual(len(list(self.archive.rglob("sessions/closed/mission-*.json"))), 3)
        self.assertEqual(len(list(self.archive.rglob("retained-copy/closed/mission-*.json"))), 3)
        result = self.run_maintenance()
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(len(list(self.archive.rglob("retained-copy/closed/mission-*.json"))), 0)

    def test_archive_inside_runtime_is_rejected(self):
        self.archive = self.root / "archive"
        with self.assertRaisesRegex(subject.ArchiveBlocked, "outside the complete"):
            self.run_maintenance()
        self.assertFalse(self.archive.exists())

    def test_wrong_session_provenance_is_not_archived(self):
        path = self.root / "receipts" / "closed" / "mission-00000.json"
        payload = subject._json(path)
        payload["session"] = "another-session"
        self.put_json(path, payload)
        before = self.fingerprints(self.root / "receipts")
        with self.assertRaisesRegex(subject.ArchiveBlocked, "provenance"):
            self.run_maintenance()
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)

    def test_unexpected_game_image_in_session_is_preserved(self):
        image = self.root / "receipts" / "closed" / "image.png"
        image.write_bytes(b"never archive unknown content")
        before = self.fingerprints(self.root / "receipts")
        self.assertEqual(self.run_maintenance()["status"], "deferred_no_closed_capacity")
        inventory = subject._inventory(self.root / "receipts")
        with patch.object(subject, "_inventory", return_value=(4095, inventory[1], inventory[2])):
            with self.assertRaises(subject.ArchiveBlocked):
                self.run_maintenance()
        self.assertEqual(self.fingerprints(self.root / "receipts"), before)

    def test_partial_relief_below_trigger_is_allowed_above_preferred_target(self):
        self.add_receipts("active", 3)
        self.write_pause_boundary()
        result = self.run_maintenance(trigger_files=5, target_files=2)
        self.assertEqual(result["remainingReceipts"], 3)
        self.assertEqual(result["status"], "archived")

    def test_partial_relief_can_remain_above_soft_trigger_with_native_headroom(self):
        self.add_receipts("active", 6)
        self.write_pause_boundary()
        result = self.run_maintenance(trigger_files=5, target_files=2)
        self.assertEqual(result["remainingReceipts"], 6)
        self.assertEqual(result["archivedReceipts"], 3)
        self.assertEqual(result["status"], "archived")
        self.assertEqual(self.run_maintenance(trigger_files=5, target_files=2)["status"],
                         "deferred_no_closed_capacity")

    def test_tampered_pending_plan_cannot_escape_archive_directory(self):
        with patch.object(subject, "_copy_receipt", side_effect=OSError("interrupt")):
            with self.assertRaises(OSError):
                self.run_maintenance()
        journal = subject._json(self.archive / "pending.json")
        journal["plan"]["batchId"] = "../../outside"
        self.put_json(self.archive / "pending.json", journal)
        with self.assertRaisesRegex(subject.ArchiveBlocked, "integrity"):
            self.run_maintenance()
        self.assertTrue((self.root / "receipts" / "closed").exists())

    def test_4095_boundary_through_actual_candidate_caller(self):
        preparation_started = time.perf_counter()
        for directory in (self.root / "receipts" / "closed", self.root / "receipts" / "active"):
            for path in directory.iterdir():
                path.unlink()
        self.add_receipts("closed", 2191)
        self.add_receipts("active", 1904)
        self.write_pause_boundary()
        active_before = self.fingerprints(self.root / "receipts" / "active")
        path = Path(__file__).with_name("act-one-command.py")
        spec = importlib.util.spec_from_file_location("boundary_candidate_command", path)
        command = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(command)
        actual_write = command.atomic
        actual_maintenance = command.maintain_receipts_for_controller
        captured = []
        measurements = []
        phase = {}
        def timed_maintenance(*args):
            started = time.perf_counter()
            result = actual_maintenance(*args)
            phase["maintenanceMs"] = (time.perf_counter() - started) * 1000
            phase["maintenanceStatus"] = result["status"]
            phase["helperSha256"] = result["helperSourceSha256"]
            phase["callerSha256"] = result["callerSourceSha256"]
            return result
        def submit(candidate_path, request):
            phase["callerToWriteEntryMs"] = (time.perf_counter() - phase["started"]) * 1000
            count = sum(1 for _ in (self.root / "receipts").rglob("*.json"))
            self.assertEqual(count, 1904)
            self.assertLess(count, 4096 - 1)
            self.assertFalse((self.root / "receipts" / "closed").exists())
            actual_write(candidate_path, request)
            captured.append(request)
            raise RuntimeError("offline request submitted after archive")
        argv = ["candidate", "observe", "--session", "active", "--frame", "7",
                "--expected-windows-session-id", "2"]
        preparation_ms = (time.perf_counter() - preparation_started) * 1000
        with patch.object(sys, "argv", argv), patch.object(command, "ROOT", self.root), \
             patch.object(command, "require_live_controller", return_value=self.status), \
             patch.object(command, "maintain_receipts_for_controller", side_effect=timed_maintenance), \
             patch.object(command, "atomic", side_effect=submit):
            for count_before in (4095, 1904):
                phase = {"receiptCountBefore": count_before, "started": time.perf_counter()}
                with self.assertRaisesRegex(RuntimeError, "after archive"):
                    command.main()
                measurements.append({key: value for key, value in phase.items() if key != "started"})
        self.assertEqual(len(captured), 2)
        self.assertEqual(self.fingerprints(self.root / "receipts" / "active"), active_before)
        self.assertEqual(subject._json(self.root / "observation.json")["timestamp"], 999500)
        self.assertEqual(len(list((self.base / "receipt-archives").rglob("sessions/closed/mission-*.json"))), 2191)
        timing_path = os.environ.get("RECEIPT_ARCHIVE_TIMING_PATH")
        if timing_path:
            self.put_json(Path(timing_path), {
                "scope": "One offline actual-caller fixture; native process gate mocked; no game input",
                "volume": self.base.anchor, "fixturePreparationMs": preparation_ms,
                "fixturePreparationIncludes": "4095 file creation, provenance hashes, observation and module import",
                "excludedFromMaintenanceTiming": "fixture setup, assertions, request write, fixture cleanup",
                "firstCallIncludesHelperImport": True, "measurements": measurements,
                "cleanup": "TemporaryDirectory cleanup runs outside the timed interval",
            })


class CallerOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name("act-one-command.py")
        spec = importlib.util.spec_from_file_location("archive_candidate_command", path)
        cls.command = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.command)

    def test_maintenance_precedes_uuid_timestamp_and_request_write(self):
        command = self.command
        events = []
        clock = [100.0]
        heartbeat = {"state": "idle", "processId": 42, "windowsSessionId": 2, "session": "active"}
        observation = {"session": "active", "frameId": 7}
        def maintenance(*_):
            events.append("maintenance")
            clock[0] = 112.0  # Simulate work exceeding the old freshness window.
            return {"status": "archived"}
        def create_uuid():
            events.append("uuid")
            return type("UUID", (), {"hex": "unique"})()
        def write(path, request):
            events.append("write")
            self.assertEqual(request["createdAt"], 112000)
            raise RuntimeError("offline write sentinel")
        argv = ["candidate", "observe", "--session", "active", "--frame", "7",
                "--expected-windows-session-id", "2"]
        with patch.object(sys, "argv", argv), patch.object(command, "read", return_value=observation), \
             patch.object(command, "require_live_controller", return_value=heartbeat) as gate, \
             patch.object(command, "maintain_receipts_for_controller", side_effect=maintenance), \
             patch.object(command.time, "time", side_effect=lambda: clock[0]), \
             patch.object(command.uuid, "uuid4", side_effect=create_uuid), \
             patch.object(command, "atomic", side_effect=write):
            with self.assertRaisesRegex(RuntimeError, "offline write sentinel"):
                command.main()
            self.assertEqual(gate.call_count, 2)
        self.assertEqual(events, ["maintenance", "uuid", "write"])

    def test_maintenance_failure_does_not_mint_or_submit_request(self):
        command = self.command
        argv = ["candidate", "observe", "--session", "active", "--frame", "7",
                "--expected-windows-session-id", "2"]
        with patch.object(sys, "argv", argv), \
             patch.object(command, "read", return_value={"session": "active", "frameId": 7}), \
             patch.object(command, "require_live_controller", return_value={"state": "idle"}), \
             patch.object(command, "maintain_receipts_for_controller", side_effect=subject.ArchiveBlocked("all active")), \
             patch.object(command.uuid, "uuid4") as identity, patch.object(command, "atomic") as writing:
            with self.assertRaisesRegex(SystemExit, "before request creation"):
                command.main()
            identity.assert_not_called()
            writing.assert_not_called()

    def test_archived_gameplay_action_is_deferred_without_uuid_or_replay(self):
        command = self.command
        observation = {"session": "active", "frameId": 7, "timestamp": 100000}
        heartbeat = {"state": "idle", "session": "active", "processId": 42, "windowsSessionId": 2}
        argv = ["candidate", "questStep", "--step", "natlanStoryDainBattle", "--session", "active",
                "--frame", "7", "--expected-windows-session-id", "2", "--compact"]
        with patch.object(sys, "argv", argv), patch.object(command, "read", return_value=observation), \
             patch.object(command, "require_live_controller", return_value=heartbeat), \
             patch.object(command, "maintain_receipts_for_controller", return_value={"status": "archived"}), \
             patch.object(command.uuid, "uuid4") as identity, patch.object(command, "atomic") as writing, \
             patch("builtins.print") as printing:
            command.main()
            identity.assert_not_called()
            writing.assert_not_called()
            output = json.loads(printing.call_args_list[-1].args[0])
            self.assertEqual(output["status"], "deferred")
            self.assertFalse(output["requestSubmitted"])
            self.assertEqual(output["nextAction"], "observe")
        self.assertEqual(observation["timestamp"], 100000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
