"""Stdlib-only relay bootstrap. This file and the interpreter are trust roots.

Project sources execute only from the byte strings whose hashes were checked.
No claim is made that Python/stdlib, this bootstrap, or native code is verified.
"""
from __future__ import annotations

import argparse
import builtins
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types
import uuid

MAX_CONFIG = 128 * 1024
MAX_SOURCE = 2 * 1024 * 1024
ROLES = {
    "reliability": "relay_reliability.py",
    "prepared": "relay_prepared.py",
    "owner": "owner_adapter.py",
    "runtime": "relay_runtime.py",
    "command": "act-one-command.py",
    "controller": "controller-control.py",
    "archive": "receipt_archive.py",
    "caller": "run-game-bound.js",
}
CORE = ("reliability", "prepared", "owner", "runtime")
IMPORT_ROLES = {"relay_reliability": "reliability", "relay_prepared": "prepared",
                "owner_adapter": "owner", "relay_runtime": "runtime"}


class BootstrapHeld(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise BootstrapHeld(reason)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate-config-key")
        result[key] = value
    return result


def lexical_absolute(path):
    path = Path(path)
    require(".." not in path.parts, "parent-traversal-not-permitted")
    return path if path.is_absolute() else Path.cwd() / path


def check_path(path):
    """Inspect lexical paths, including every parent, without resolving links."""
    require(path.is_absolute(), "source-path-not-absolute")
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode)
                and not (getattr(info, "st_file_attributes", 0) & 0x400),
                "source-link-or-reparse")
        require(stat.S_ISREG(info.st_mode) if item == path else stat.S_ISDIR(info.st_mode),
                "source-not-regular" if item == path else "source-parent-not-directory")
    return info


def read_once(path, limit):
    before = check_path(path)
    require(0 < before.st_size <= limit, "source-size-out-of-bounds")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        require(stat.S_ISREG(opened.st_mode)
                and (opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
                "source-changed-during-open")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        after = os.fstat(fd)
        current = check_path(path)
        require((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                == (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                and (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino),
                "source-changed-during-read")
        require(0 < len(data) <= limit, "source-size-out-of-bounds")
        return data
    finally:
        os.close(fd)


def load_config(path):
    raw = read_once(lexical_absolute(path), MAX_CONFIG)
    try:
        config = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(BootstrapHeld("nonfinite-config")))
    except (ValueError, UnicodeError) as exc:
        raise BootstrapHeld("invalid-config-json") from exc
    require(type(config) is dict and type(config.get("schema")) is int
            and config["schema"] == 1, "invalid-owner-adapter-config")
    require(type(config.get("owner")) is dict, "invalid-owner-config")
    require(type(config.get("steps")) is list and config["steps"]
            and all(type(step) is str and step for step in config["steps"]), "invalid-reviewed-step-list")
    for key in ("commandPath", "pilotRoot", "appDirectory", "journalDirectory", "legacyResponses"):
        require(type(config.get(key)) is str and bool(config[key]), "missing-config-" + key)
    return config


def capture_sources(config):
    """All roles must validate before any project module executes, in every mode."""
    root = lexical_absolute(__file__).parent
    entries = config.get("sourceHashes")
    require(type(entries) is dict and set(entries) == {str(root / filename) for filename in ROLES.values()}, "required-source-roles-mismatch")
    sources, metadata = {}, {}
    for role, filename in ROLES.items():
        expected_path = str(root / filename)
        digest = entries[expected_path]
        require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest), "invalid-source-digest-" + role)
        data = read_once(Path(expected_path), MAX_SOURCE)
        actual = hashlib.sha256(data).hexdigest()
        require(actual == digest, "reviewed-source-changed-" + role)
        sources[role] = data
        metadata[role] = {"path": expected_path, "expectedSha256": digest, "verifiedSha256": actual,
                          "executedSha256": None, "state": "verified-not-executed",
                          "loadMethod": "read-once-sha256", "scope": "source-bytes-only"}
    require(config["commandPath"] == metadata["command"]["path"], "command-role-path-mismatch")
    return sources, metadata


class VerifiedModules:
    """Private names and per-module import wiring; ambient project cache is ignored."""
    def __init__(self, sources, metadata):
        self.sources, self.metadata = sources, metadata
        self.modules = {}
        self.prefix = "_bettergi_verified_" + uuid.uuid4().hex
        self.names = {}

    def project_import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if level == 0 and name in IMPORT_ROLES:
            role = IMPORT_ROLES[name]
            require(role in self.modules, "verified-dependency-not-loaded-" + role)
            return self.modules[role]
        # No dynamic project package imports are part of the reviewed graph.
        require(level == 0 and name not in {"receipt_archive", "controller_control", "relay_driver"},
                "unwired-project-import")
        return builtins.__import__(name, globals, locals, fromlist, level)

    def load(self, role, injected=None):
        require(role not in self.modules, "duplicate-verified-module")
        name = self.prefix + "_" + role
        require(name not in sys.modules, "isolated-module-name-collision")
        module = types.ModuleType(name)
        module.__file__ = self.metadata[role]["path"]
        module.__package__ = ""
        module.__dict__["__builtins__"] = {**vars(builtins), "__import__": self.project_import}
        if injected:
            module.__dict__.update(injected)
        # dataclasses looks up its defining module. Register only our new name.
        sys.modules[name] = module
        self.names[name] = module
        try:
            exec(compile(self.sources[role], module.__file__, "exec", dont_inherit=True), module.__dict__)
        except BaseException:
            self.close()
            raise
        self.modules[role] = module
        self.metadata[role].update(state="loaded", executedSha256=self.metadata[role]["verifiedSha256"],
                                   loadMethod="compile-and-exec-verified-bytes")
        return module

    def close(self):
        for name, own_module in self.names.items():
            # Never delete or replace another component's cache entry.
            entry = sys.modules.get(name)
            if entry is own_module:
                del sys.modules[name]
        self.names.clear()

    def start(self, config, mode):
        for role in CORE:
            self.load(role)
        command = None
        if mode != "consume":
            controller = self.load("controller")
            archive = self.load("archive", {"_VERIFIED_SOURCE_SHA256": self.metadata["archive"]["verifiedSha256"]})
            command = self.load("command", {
                "_VERIFIED_CONTROLLER_MODULE": controller, "_VERIFIED_ARCHIVE_MODULE": archive,
                "_VERIFIED_SOURCE_SHA256": self.metadata["command"]["verifiedSha256"],
                "_VERIFIED_APP_DIRECTORY": config["appDirectory"],
            })
        return self.modules["runtime"], command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["serve", "consume", "verify-owner", "qualify-recovery"])
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--request-file", type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    sources, metadata = capture_sources(config)
    loaded = VerifiedModules(sources, metadata)
    try:
        runtime, command = loaded.start(config, args.mode)
        report = {"roles": metadata, "trustRoot": "relay_driver.py and Python interpreter/stdlib",
                  "excludes": ["bootstrap-execution", "interpreter", "stdlib", "native-binaries"],
                  "caller": "verified bytes only; JS execution belongs to external caller"}
        try:
            runtime.run(args, config, command, report)
        except loaded.modules["reliability"].Held as exc:
            raise BootstrapHeld(str(exc)) from exc
    finally:
        loaded.close()


if __name__ == "__main__":
    try:
        main()
    except (BootstrapHeld, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"state": "held", "boundResult": False, "reason": str(exc)}), flush=True)
        raise SystemExit(2)
