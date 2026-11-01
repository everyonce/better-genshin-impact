"""Isolated relay journal and matching result reader; no production adapter.

The caller supplies a verified owner context and the existing guarded CLI dispatch.
This module has no process, pipe, capture, game, network, or CLI-loading operations.
Unknown delivery is retained and blocks dispatch, including after process restart.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path


OUTER_ID = re.compile(r"[a-z0-9-]{8,64}\Z")
SESSION = re.compile(r"[a-z0-9]+-[a-z0-9]+(?:-r[23])?\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
MISSION = re.compile(r"mission-[0-9a-f]{32}\Z")
MAX_RECORD = 2 * 1024 * 1024


class Held(RuntimeError):
    """No new dispatch is admitted; existing evidence must be inspected."""


def require(condition, reason):
    if not condition:
        raise Held(reason)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(value):
    return hashlib.sha256(encode(value)).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate-json-key")
        result[key] = value
    return result


def parse_request(raw):
    require(type(raw) in (str, bytes) and 0 < len(raw) <= 32768,
            "invalid-request-size")
    try:
        result = json.loads(raw, object_pairs_hook=_unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(Held("nonfinite-json")))
    except (ValueError, UnicodeError) as exc:
        raise Held("invalid-request-json") from exc
    require(type(result) is dict, "request-must-be-object")
    return result


@dataclass(frozen=True)
class OwnerContext:
    session: str
    process_id: int
    windows_session_id: int
    owner_lifetime_binding: str

    def validate(self):
        require(type(self.session) is str and SESSION.fullmatch(self.session), "invalid-session")
        require(type(self.process_id) is int and self.process_id > 0, "invalid-process-id")
        require(type(self.windows_session_id) is int and self.windows_session_id >= 2,
                "invalid-child-windows-session")
        require(type(self.owner_lifetime_binding) is str
                and SHA.fullmatch(self.owner_lifetime_binding),
                "missing-verified-owner-lifetime-binding")


def binding(request, owner, steps):
    require(type(owner) is OwnerContext, "verified-owner-context-required")
    owner.validate()
    require(type(request) is dict, "request-must-be-object")
    kind = request.get("kind")
    require(type(kind) is str, "unsupported-request-kind")
    required = {"id", "kind", "frame", "step"} if kind == "questStep" else {"id", "kind", "frame"}
    require(set(request) == required and kind in {"observe", "questStep"}, "unsupported-request-fields")
    require(type(request.get("id")) is str and OUTER_ID.fullmatch(request["id"]), "invalid-outer-id")
    require(type(request.get("frame")) is int and request["frame"] > 0, "invalid-frame")
    if kind == "questStep":
        require(type(request["step"]) is str and request["step"] in steps, "unlisted-step")
    payload = {"schema": 1, "request": dict(request), "owner": asdict(owner)}
    return {**payload, "binding": sha(payload)}


def _settled(response, key):
    """Recognize only existing CLI terminal+quiescent or V4 non-submission proof.

    This checks structure/binding, not authenticity. The trusted owner adapter must
    obtain these fields from the unchanged guarded CLI, never from relay input.
    """
    if type(response) is not dict or response.get("id") != key["request"]["id"]:
        return False
    if type(response.get("code")) is not int or not {"error", "result", "output"} <= set(response):
        return False
    result = response.get("result")
    if type(result) is not dict or result.get("session") != key["owner"]["session"]:
        return False
    frame = result.get("frameId")
    if type(frame) is not int or frame < key["request"]["frame"]:
        return False
    if result.get("status") == "deferred":
        return (response["code"] == 0 and response["error"] is None
                and result.get("requestSubmitted") is False and result.get("nextAction") == "observe"
                and type(result.get("receiptMaintenance")) is dict
                and result["receiptMaintenance"].get("status") == "archived"
                and "submittedId" not in result and "terminalId" not in result)
    mission = result.get("submittedId")
    return (result.get("status") in {"completed", "failed", "rejected", "stopped"}
            and type(mission) is str and MISSION.fullmatch(mission) is not None
            and result.get("terminalId") == mission and result.get("controllerQuiescent") is True)


def validate_result(envelope, request, owner, steps):
    """Required caller hook. An old id.json or a held/unknown result never passes."""
    expected = binding(request, owner, steps)
    require(type(envelope) is dict, "unbound-result")
    for field, value in expected.items():
        require(encode(envelope.get(field)) == encode(value), "result-binding-mismatch")
    require(envelope.get("state") == "settled", "result-not-settled")
    require(_settled(envelope.get("response"), expected), "invalid-settlement-proof")
    return envelope["response"]


def _regular(path, directory=False):
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode)
            and not (getattr(info, "st_file_attributes", 0) & 0x400), "reparse-path-held")
    require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode),
            "unexpected-path-type")
    return info


def _regular_if_present(path):
    """Validate the entry itself; only FileNotFoundError means it is absent."""
    try:
        return _regular(path)
    except FileNotFoundError:
        return None


def _directory(path):
    path = Path(os.path.abspath(path))
    for item in reversed((path, *path.parents)):
        _regular(item, directory=True)
    return path


class RelayJournal:
    """One durable in-flight request across all callers sharing this journal.

    Directory creation and any activation belong to the owner. Use one persistent
    directory across relay restarts, never a fresh directory to evade an unknown.
    Existing legacy response files are read-only collision guards. No automatic
    clearing or re-dispatch of unknown outcomes is implemented.
    """

    def __init__(self, directory, steps, legacy_responses=None):
        self.directory = _directory(directory)
        self.steps = frozenset(steps)
        self.legacy = _directory(legacy_responses) if legacy_responses is not None else None

    def _checkpoint(self, name):
        """Inert test subclasses may raise to model a process crash at this point."""

    def _sync_directory(self):
        if os.name != "nt":
            descriptor = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    @contextlib.contextmanager
    def _lock(self):
        _directory(self.directory)
        path = self.directory / "journal.lock"
        _regular_if_present(path)
        with path.open("a+b") as stream:
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise Held("journal-busy") from exc
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def _read(self, name):
        path = self.directory / name
        info = _regular_if_present(path)
        if info is None:
            return None
        require(0 < info.st_size <= MAX_RECORD, "invalid-record-size")
        with path.open("rb") as stream:
            raw = stream.read(MAX_RECORD + 1)
        require(len(raw) <= MAX_RECORD, "oversized-record")
        try:
            value = json.loads(raw, object_pairs_hook=_unique)
        except (ValueError, UnicodeError) as exc:
            raise Held("corrupt-record") from exc
        require(type(value) is dict, "invalid-record")
        return value

    def _new(self, name, value):
        raw = encode(value)
        require(0 < len(raw) <= MAX_RECORD, "oversized-record")
        with (self.directory / name).open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        self._sync_directory()

    def _intent(self, value):
        require(type(value) is dict and type(value.get("owner")) is dict, "invalid-intent")
        try:
            expected = binding(value.get("request"), OwnerContext(**value["owner"]), self.steps)
        except TypeError as exc:
            raise Held("invalid-owner-record") from exc
        require(encode(value) == encode(expected), "intent-binding-mismatch")
        return value

    def _response(self, key):
        result = self._read(key["request"]["id"] + ".response.json")
        if result is not None:
            require(all(encode(result.get(field)) == encode(value) for field, value in key.items()),
                    "stored-response-binding-mismatch")
            require(result.get("state") in {"settled", "unknown"}, "invalid-response-state")
            if result["state"] == "settled":
                validate_result(result, key["request"], OwnerContext(**key["owner"]), self.steps)
        return result

    def _clear_settled_active(self):
        active = self._read("active.json")
        if active is None:
            return
        self._intent(active)
        saved = self._read(active["request"]["id"] + ".intent.json")
        require(encode(saved) == encode(active), "active-intent-incomplete")
        response = self._response(active)
        require(response is not None and response["state"] == "settled", "unknown-in-flight")
        # Only a bound, durably saved settlement permits retiring this active marker.
        require(self._read("active.json") == active, "active-marker-changed")
        (self.directory / "active.json").unlink()
        self._sync_directory()

    def _held(self, key, reason):
        return {**key, "state": "held", "reason": reason, "response": None}

    def execute(self, request, owner, dispatch):
        key = binding(request, owner, self.steps)
        identity = key["request"]["id"]
        try:
            with self._lock():
                if self.legacy is not None:
                    _directory(self.legacy)
                    require(_regular_if_present(self.legacy / (identity + ".json")) is None,
                            "legacy-unbound-response")
                saved = self._read(identity + ".intent.json")
                if saved is not None:
                    self._intent(saved)
                    require(encode(saved) == encode(key), "request-binding-mismatch")
                    response = self._response(key)
                    if response is None:
                        return {**key, "state": "unknown", "reason": "intent-without-response", "response": None}
                    # Replayed results are historical outcomes, never fresh game observations.
                    return {**response, "replayed": True}
                require(self._read(identity + ".response.json") is None, "response-without-intent")
                self._clear_settled_active()
                self._new("active.json", key)
                self._checkpoint("after-active")
                self._new(identity + ".intent.json", key)
                self._checkpoint("after-intent")
                try:
                    response = dispatch(dict(key["request"]), owner)
                except Exception as exc:
                    response = {"id": identity, "code": 1, "error": "dispatch-" + type(exc).__name__,
                                "result": None, "output": None}
                self._checkpoint("after-dispatch")
                envelope = {**key, "state": "settled" if _settled(response, key) else "unknown",
                            "response": response}
                self._new(identity + ".response.json", envelope)
                self._checkpoint("after-response")
                if envelope["state"] == "settled":
                    self._clear_settled_active()
                return {**envelope, "replayed": False}
        except Held as exc:
            return self._held(key, str(exc))
        except (OSError, TypeError, ValueError):
            # May follow dispatch: this is never evidence of non-submission.
            return self._held(key, "storage-or-response-error")

    def read_result(self, request, owner):
        """Read-only reconciliation of a bound saved result; never calls dispatch."""
        key = binding(request, owner, self.steps)
        with self._lock():
            saved = self._read(key["request"]["id"] + ".intent.json")
            require(encode(saved) == encode(key), "no-matching-intent")
            response = self._response(key)
            require(response is not None, "intent-without-response")
            validate_result(response, request, owner, self.steps)
            return {**response, "replayed": True}
