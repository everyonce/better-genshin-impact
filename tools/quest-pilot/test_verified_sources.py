"""Injected source-loader tests. No native/game calls; Linux path fixtures only."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import relay_driver as bootstrap


class VerifiedSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="verified-test-", dir=Path(__file__).parent)
        self.root = Path(self.temp.name).absolute()
        self.source = self.root / "tools" / "quest-pilot"
        self.source.mkdir(parents=True)
        for filename in ["relay_driver.py", *bootstrap.ROLES.values()]:
            shutil.copyfile(Path(__file__).with_name(filename), self.source / filename)
        spec = importlib.util.spec_from_file_location("fixture_bootstrap", self.source / "relay_driver.py")
        self.boot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.boot)
        self.config = {"schema": 1, "owner": {"session": "test-session-r2", "process_id": 1234,
                       "windows_session_id": 2, "owner_lifetime_binding": "a" * 64},
                       "steps": ["safeStep"], "commandPath": str(self.source / "act-one-command.py"),
                       "pilotRoot": str(self.root / "app" / "User/JsScript/ActOnePilot"),
                       "appDirectory": str(self.root / "app"), "journalDirectory": str(self.root / "journal"),
                       "legacyResponses": str(self.root / "legacy"), "sourceHashes": {}}
        for name in ["journal", "legacy"]: (self.root / name).mkdir()
        self.refresh()
        self.loaded = []

    def tearDown(self):
        for loaded in self.loaded: loaded.close()
        self.temp.cleanup()

    def refresh(self):
        self.config["sourceHashes"] = {str(self.source / name): hashlib.sha256((self.source / name).read_bytes()).hexdigest()
                                       for name in self.boot.ROLES.values()}

    def capture(self):
        return self.boot.capture_sources(self.config)

    def load(self, mode="consume", captured=None):
        loaded = self.boot.VerifiedModules(*(captured or self.capture()))
        self.loaded.append(loaded)
        runtime, command = loaded.start(self.config, mode)
        return loaded, runtime, command

    def test_missing_empty_and_partial_source_maps_rejected(self):
        for value in [None, {}, {str(self.source / "owner_adapter.py"): "a" * 64}]:
            with self.subTest(value=value):
                self.config["sourceHashes"] = value
                with self.assertRaisesRegex(self.boot.BootstrapHeld, "required-source-roles"):
                    self.capture()

    def test_substituted_path_same_bytes_is_rejected(self):
        original = str(self.source / "owner_adapter.py")
        other = self.root / "owner_adapter.py"
        shutil.copyfile(original, other)
        self.config["sourceHashes"][str(other)] = self.config["sourceHashes"].pop(original)
        with self.assertRaises(self.boot.BootstrapHeld): self.capture()

    def test_command_path_must_match_fixed_role(self):
        self.config["commandPath"] = str(self.root / "alternate.py")
        with self.assertRaisesRegex(self.boot.BootstrapHeld, "command-role-path"):
            self.capture()

    def test_invalid_digests_rejected(self):
        key = str(self.source / "owner_adapter.py")
        for value in [None, "", "A" * 64, "a" * 63, 1]:
            self.config["sourceHashes"][key] = value
            with self.assertRaises(self.boot.BootstrapHeld): self.capture()

    def test_all_hashes_checked_before_any_project_execution(self):
        # A validly hashed first module must not execute if the final role is bad.
        marker = self.root / "effect"
        p = self.source / "relay_reliability.py"
        p.write_bytes(p.read_bytes() + f'\nopen({str(marker)!r}, "w").write("BAD")\n'.encode())
        self.refresh()
        self.config["sourceHashes"][str(self.source / "run-game-bound.js")] = "0" * 64
        with self.assertRaises(self.boot.BootstrapHeld): self.load("serve")
        self.assertFalse(marker.exists())

    def test_shadow_cwd_and_prepopulated_cache_ignored(self):
        original = os.getcwd()
        shadows = {}
        for name in self.boot.IMPORT_ROLES:
            (self.root / (name + ".py")).write_text('raise AssertionError("cwd shadow executed")\n')
            shadows[name] = types.ModuleType(name)
        try:
            os.chdir(self.root)
            with patch.dict(sys.modules, shadows):
                loaded, runtime, _ = self.load()
                self.assertIs(runtime.OwnerContext, loaded.modules["reliability"].OwnerContext)
                self.assertIs(runtime.Held, loaded.modules["reliability"].Held)
                self.assertIs(runtime.OwnerProvider, loaded.modules["owner"].OwnerProvider)
                self.assertIs(loaded.modules["owner"].OwnerContext, runtime.OwnerContext)
                self.assertIs(loaded.modules["prepared"].Held, runtime.Held)
                for name, shadow in shadows.items(): self.assertIs(sys.modules[name], shadow)
        finally:
            os.chdir(original)

    def test_disk_changes_after_capture_cannot_change_executed_bytes(self):
        captured = self.capture()
        for role in ["owner", "command", "controller", "archive"]:
            (self.source / self.boot.ROLES[role]).write_text('raise AssertionError("changed disk executed")\n')
        loaded, runtime, command = self.load("serve", captured)
        self.assertEqual(command.CALLER_SOURCE_SHA256, captured[1]["command"]["verifiedSha256"])
        self.assertEqual(loaded.modules["archive"].SOURCE_SHA256, captured[1]["archive"]["verifiedSha256"])
        for role in [*self.boot.CORE, "controller", "archive", "command"]:
            self.assertEqual(loaded.metadata[role]["executedSha256"], hashlib.sha256(captured[0][role]).hexdigest())

    def test_stale_unchecked_bytecode_is_never_used(self):
        p = self.source / "owner_adapter.py"
        good = p.read_bytes()
        p.write_text('raise AssertionError("cached bytecode executed")\n')
        py_compile.compile(str(p), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        p.write_bytes(good)
        self.load()

    def test_consume_verifies_core_but_never_executes_native_helpers(self):
        for role in ["command", "controller", "archive"]:
            (self.source / self.boot.ROLES[role]).write_text('raise AssertionError("native/helper execution forbidden")\n')
        self.refresh()
        with patch.object(subprocess, "run", side_effect=AssertionError("subprocess forbidden")):
            loaded, runtime, command = self.load()
        self.assertIsNone(command)
        self.assertEqual(set(loaded.modules), set(self.boot.CORE))
        for role in ["command", "controller", "archive", "caller"]:
            self.assertEqual(loaded.metadata[role]["state"], "verified-not-executed")
            self.assertIsNone(loaded.metadata[role]["executedSha256"])

    def test_consume_rejects_changed_core(self):
        p = self.source / "relay_prepared.py"
        p.write_bytes(p.read_bytes() + b'\n# changed\n')
        with self.assertRaisesRegex(self.boot.BootstrapHeld, "reviewed-source-changed-prepared"):
            self.load()

    def test_helpers_are_exact_verified_objects_with_no_dynamic_loader(self):
        loaded, _, command = self.load("serve")
        self.assertIs(command._VERIFIED_CONTROLLER_MODULE, loaded.modules["controller"])
        self.assertIs(command._receipt_archive_module, loaded.modules["archive"])
        with patch.object(importlib.util, "spec_from_file_location", side_effect=AssertionError("reread forbidden")):
            with patch.object(loaded.modules["controller"], "run", return_value={"synthetic": True}) as run:
                self.assertEqual(command.query_verified_service_status(1234, 2), {"synthetic": True})
                run.assert_called_once_with("status", 1234, 2)
            with patch.object(loaded.modules["archive"], "maintain", return_value={"ok": True}) as maintain:
                result = command.maintain_receipts_for_controller(command.ROOT, {"session": "test-session-r2", "processId": 1234, "windowsSessionId": 2})
                self.assertTrue(result["ok"])
                self.assertEqual(result["helperSourceSha256"], loaded.metadata["archive"]["executedSha256"])
                self.assertEqual(result["callerSourceSha256"], loaded.metadata["command"]["executedSha256"])
                maintain.assert_called_once()

    def test_consume_cli_returns_bound_result_metadata_and_preserves_journal(self):
        # Create only an injected prepared settled envelope, then consume through
        # the real CLI entrypoint with all native helpers booby-trapped.
        for role in ["command", "controller", "archive"]:
            (self.source / self.boot.ROLES[role]).write_text('raise AssertionError("native forbidden")\n')
        self.refresh()
        loaded, _, _ = self.load()
        reliability = loaded.modules["reliability"]
        owner = reliability.OwnerContext(**self.config["owner"])
        request = {"id": "request-test-0001", "kind": "questStep", "step": "safeStep", "frame": 10}
        journal = loaded.modules["prepared"].PreparedRelayJournal(
            self.root / "journal", self.config["steps"], owner_probe=lambda **_: owner,
            legacy_responses=self.root / "legacy", clock_ms=lambda: 100100)
        def fake_dispatch(request, owner, prepare):
            heartbeat = {"version": 1, "session": owner.session, "processId": owner.process_id,
                         "windowsSessionId": owner.windows_session_id, "remoteDesktop": True,
                         "heartbeatAt": 100100, "state": "idle", "frameId": 10, "activeRequestId": None}
            inner = {"id": "mission-" + "b" * 32, "session": owner.session, "mission": "questStep",
                     "step": "safeStep", "createdAt": 100000, "expectedFrameId": 10}
            ack = prepare(json.dumps(inner).encode(), heartbeat)
            ack["revalidate"](heartbeat)
            return {"id": request["id"], "code": 0, "error": None, "output": None,
                    "result": {"status": "completed", "session": owner.session, "frameId": 11,
                               "submittedId": "mission-" + "b" * 32, "terminalId": "mission-" + "b" * 32,
                               "controllerQuiescent": True}}
        journal.execute(request, owner, fake_dispatch)
        before = {p.name: p.read_bytes() for p in (self.root / "journal").iterdir()}
        config_path, request_path = self.root / "config.json", self.root / "request.json"
        config_path.write_text(json.dumps(self.config))
        request_path.write_text(json.dumps(request))
        result = subprocess.run([sys.executable, "-I", "-B", str(self.source / "relay_driver.py"),
                                 "consume", "--config", str(config_path), "--request-file", str(request_path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        response = json.loads(result.stdout)
        self.assertTrue(response["historicalRead"])
        self.assertTrue(response["boundResult"])
        self.assertEqual(response["boundRequest"], request)
        for role in self.boot.CORE:
            self.assertEqual(response["sourceVerification"]["roles"][role]["state"], "loaded")
        for role in ["controller", "archive", "command", "caller"]:
            self.assertEqual(response["sourceVerification"]["roles"][role]["state"], "verified-not-executed")
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / "journal").iterdir()})

    def test_duplicate_config_keys_and_nonfinite_rejected(self):
        p = self.root / "config.json"
        for raw in ['{"schema":1,"schema":1}', '{"schema":NaN}']:
            p.write_text(raw)
            with self.assertRaises(self.boot.BootstrapHeld): self.boot.load_config(p)

    def test_parent_traversal_not_normalized_away(self):
        with self.assertRaisesRegex(self.boot.BootstrapHeld, "parent-traversal"):
            self.boot.load_config(self.root / "alias" / ".." / "config.json")

    def test_config_and_source_size_bounded(self):
        p = self.root / "config.json"
        p.write_bytes(b" " * (self.boot.MAX_CONFIG + 1))
        with self.assertRaises(self.boot.BootstrapHeld): self.boot.load_config(p)
        (self.source / "owner_adapter.py").write_bytes(b" " * (self.boot.MAX_SOURCE + 1))
        with self.assertRaises(self.boot.BootstrapHeld): self.capture()

    @unittest.skipIf(os.name == "nt", "Linux-only link fixture, not Windows proof")
    def test_source_symlink_rejected(self):
        p = self.source / "owner_adapter.py"
        other = self.root / "other.py"
        p.rename(other)
        p.symlink_to(other)
        with self.assertRaisesRegex(self.boot.BootstrapHeld, "link-or-reparse"): self.capture()

    @unittest.skipIf(os.name == "nt", "Linux-only link fixture, not Windows proof")
    def test_parent_symlink_rejected_without_resolving(self):
        other = self.root / "other"
        self.source.rename(other)
        self.source.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(self.boot.BootstrapHeld, "link-or-reparse"): self.capture()

    def test_reparse_attribute_rejected_synthetically(self):
        path = self.source / "owner_adapter.py"
        real = Path.lstat
        def fake(p):
            info = real(p)
            return types.SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400) if p == path else info
        with patch.object(Path, "lstat", fake):
            with self.assertRaisesRegex(self.boot.BootstrapHeld, "link-or-reparse"): self.capture()

    def test_module_cleanup_never_removes_unrelated_replacement(self):
        loaded, _, _ = self.load()
        name = loaded.modules["owner"].__name__
        replacement = types.ModuleType(name)
        sys.modules[name] = replacement
        try:
            loaded.close()
            self.assertIs(sys.modules[name], replacement)
        finally:
            del sys.modules[name]

    def test_failed_module_load_cleans_own_cache(self):
        captured = self.capture()
        captured[0]["owner"] = b'raise RuntimeError("synthetic compile execution failure")\n'
        loaded = self.boot.VerifiedModules(*captured)
        before = set(sys.modules)
        with self.assertRaises(RuntimeError): loaded.start(self.config, "consume")
        self.assertFalse(any(name.startswith(loaded.prefix) for name in set(sys.modules) - before))

    def test_bootstrap_import_does_not_load_project_modules(self):
        # Isolated subprocess cannot inherit the test suite's own project imports.
        code = ('import runpy,sys; runpy.run_path(sys.argv[1],run_name="inspection"); '
                'assert not any(n in sys.modules for n in ["owner_adapter","relay_prepared","relay_reliability","relay_runtime"])')
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(self.source / "relay_driver.py")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
