"""Inert receipt-rollover state machine. No live adapter or command-line entry point.

The owner supplies an authenticated adapter. This module never imports BetterGI,
opens a process/pipe, captures a screen, writes controller files, or archives data.
Only the explicitly supplied journal store is writable here.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


SHA = re.compile(r"[0-9a-f]{64}\Z")
OLD_SESSION = re.compile(r"[a-z0-9]+-[a-z0-9]+(?:-r[23])?\Z")
NEW_SESSION = re.compile(r"[a-z0-9]+-[a-z0-9]+\Z")
REQUEST_ID = re.compile(r"mission-[0-9a-f]{32}\Z")
MAX_AGE = 5000
MAX_TTL = 300000
MAX_ATTEMPTS = 3
MAX_RECEIPT = 16 * 1024 * 1024
MAX_RECEIPT_TREE = 64 * 1024 * 1024
COMPANION = 128 * 1024
PHASES = ("prepared", "stop-confirmed", "start-confirmed",
          "fresh-observe-confirmed", "archive-eligible")


class Held(RuntimeError):
    """No effect is authorized by this step; inspect the recorded reason/state."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def require(condition, message):
    if not condition:
        raise Held(message)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def parse(raw: bytes, limit: int):
    require(type(raw) is bytes and 0 < len(raw) <= limit, "Invalid evidence size")
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise Held("Invalid evidence JSON") from exc
    require(type(value) is dict, "Evidence must be an object")
    return value


@dataclass(frozen=True)
class Identity:
    process_id: int
    windows_session_id: int
    uid: str
    owner_lifetime_binding: str

    def validate(self):
        require(integer(self.process_id, 1) and integer(self.windows_session_id, 2),
                "Invalid pinned RDP process identity")
        require(type(self.uid) is str and re.fullmatch(r"[0-9]{6,12}", self.uid),
                "Invalid pinned game UID")
        require(type(self.owner_lifetime_binding) is str
                and SHA.fullmatch(self.owner_lifetime_binding),
                "Missing verified owner/process-lifetime/nonce binding")


@dataclass(frozen=True)
class Evidence:
    request: bytes
    final_receipt: bytes
    observation: bytes
    immutable_observation: bytes

    def saved(self):
        return {name: {"sha256": digest(raw), "base64": base64.b64encode(raw).decode("ascii")}
                for name, raw in asdict(self).items()}


@dataclass(frozen=True)
class MenuContinuity:
    """Independent owner guard evidence, never inferred from an old image or idle."""
    transition_id: str
    identity: Identity
    inventory_sha256: str
    stop_request_sha256: str
    stop_receipt_sha256: str
    verified_at: int
    expires_at: int
    same_game_verified: bool
    held_through_exit: bool
    native_trigger_menu_hold: bool
    startup_menu_hold: bool
    source: str = "owner-menu-continuity-guard"


@dataclass(frozen=True)
class Snapshot:
    identity: Identity
    authenticated: bool
    observed_at: int
    process_alive: bool
    session: str
    frame: int
    script_state: str
    task_running: bool
    service_owns_pilot: bool
    active_request_id: str | None
    error: str | None
    heartbeat_at: int
    evidence: Evidence
    receipt_count: int
    receipt_bytes: int
    no_pending_archive: bool
    output_reserve_verified: bool
    menu_guard_verified: bool
    successor_unused: bool = False
    transition_id: str | None = None
    suppressed_request_sha256: str | None = None
    menu_continuity: MenuContinuity | None = None


@dataclass(frozen=True)
class Reconciliation:
    # not-submitted requires durable proof that no effect was dispatched.
    status: str  # not-submitted, in-flight, succeeded, failed, unknown
    operation_key: str
    snapshot: Snapshot | None = None
    request_id: str | None = None
    reason: str | None = None
    durable_proof: bool = False


class Adapter(Protocol):
    def inspect(self, plan: dict) -> Snapshot: ...
    def dispatch(self, operation: str, operation_key: str, plan: dict,
                 expected: Snapshot, startup_contract: dict | None) -> None: ...
    def reconcile(self, operation: str, operation_key: str, plan: dict) -> Reconciliation: ...


class Store(Protocol):
    def load(self) -> dict | None: ...
    def commit(self, value: dict, expected_revision: int | None) -> None: ...
    def exclusive(self): ...


def _ordinary(path: Path):
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode)
                and not (getattr(info, "st_file_attributes", 0) & 0x400),
                "Journal path traverses a link or junction")


class FileStore:
    """One owner, explicitly selected inert journal; durable-before-effect commits.

    Revision comparison catches stale callers. The OS-held lock is released when
    its process exits; a leftover lock filename does not claim live ownership.
    """
    def __init__(self, path: Path):
        self.path = Path(os.path.abspath(path))
        _ordinary(self.path)

    def load(self):
        _ordinary(self.path)
        if not self.path.exists():
            return None
        require(self.path.stat().st_size <= 96 * 1024 * 1024, "Journal exceeds bounded size")
        wrapper = parse(self.path.read_bytes(), 96 * 1024 * 1024)
        value = wrapper.get("record")
        require(type(value) is dict and wrapper.get("sha256") == digest(encoded(value)),
                "Journal integrity mismatch")
        return value

    def exclusive(self):
        # Hold across inspect, durable intent, dispatch and confirmation so a
        # second coordinator cannot clear an intent while its sender is active.
        return _journal_lock(self.path.with_name(self.path.name + ".coordinator.lock"))

    def commit(self, value, expected_revision):
        _ordinary(self.path)
        require(self.path.parent.is_dir(), "Explicit journal directory must already exist")
        lock = self.path.with_name(self.path.name + ".lock")
        temporary = self.path.with_name(self.path.name + ".writing")
        _ordinary(lock)
        _ordinary(temporary)
        with _journal_lock(lock):
            current = self.load()
            require((None if current is None else current.get("revision")) == expected_revision,
                    "Journal revision changed")
            require(value.get("revision") == (0 if expected_revision is None else expected_revision + 1),
                    "Invalid journal revision")
            payload = encoded({"record": value, "sha256": digest(encoded(value))})
            require(len(payload) <= 96 * 1024 * 1024, "Journal exceeds bounded size")
            with temporary.open("wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)


@contextlib.contextmanager
def _journal_lock(path: Path):
    """Nonblocking OS mutex over a persistent ordinary file; never stale-lock deletion."""
    _ordinary(path)
    with path.open("a+b") as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise Held("Another journal writer holds the OS lock") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _identity(snapshot: Snapshot, identity: Identity, now: int):
    identity.validate()
    require(snapshot.identity == identity, "Owner, process lifetime, nonce, PID, UID or Windows session changed")
    require(snapshot.authenticated is True and snapshot.process_alive is True,
            "Authenticated live owner is required")
    require(integer(now) and integer(snapshot.observed_at)
            and 0 <= now - snapshot.observed_at <= MAX_AGE,
            "Authenticated status is stale or future-dated")
    require(snapshot.error is None and snapshot.active_request_id is None,
            "Controller is busy or has an unresolved error")
    require(snapshot.menu_guard_verified is True and snapshot.output_reserve_verified is True,
            "Menu preservation or existing output reserve is unverified")
    require(snapshot.no_pending_archive is True, "An archive transaction is pending")


def _pause(snapshot: Snapshot, session: str, now: int, *, fresh=True):
    evidence = snapshot.evidence
    require(evidence.observation == evidence.immutable_observation,
            "Current and immutable pause observations differ")
    obs = parse(evidence.observation, COMPANION)
    hud = obs.get("hud")
    require(type(hud) is dict, "Missing pause HUD")
    stamp = hud.get("captureStamp")
    require(type(stamp) is dict and set(stamp) == {"session", "frameId", "capturedAt", "source"},
            "Invalid original capture provenance")
    require(obs.get("session") == session == snapshot.session == stamp.get("session")
            and integer(snapshot.frame, 1)
            and obs.get("frameId") == snapshot.frame == stamp.get("frameId")
            and stamp.get("source") == "game-capture-start",
            "Pause session/frame does not match the controller")
    captured, observed = stamp.get("capturedAt"), obs.get("timestamp")
    require(integer(captured) and integer(observed)
            and captured <= observed <= now, "Invalid original observation time order")
    if fresh:
        require(now - captured <= MAX_AGE, "Held inventory source is older than five seconds")
    require(hud.get("world") is False and hud.get("health") is None
            and not any(hud.get(key) for key in ("loading", "dialogueReady", "choice", "climbing", "bigMap", "journal")),
            "Scene is not the held inventory boundary")
    rows = obs.get("ocr")
    require(type(rows) is list, "Missing inventory OCR")
    def at(row, pattern, x0, x1, y0, y1):
        return (type(row) is dict and type(row.get("text")) is str
                and re.fullmatch(pattern, row["text"].strip(), flags=re.IGNORECASE)
                and type(row.get("x")) in (int, float) and type(row.get("y")) in (int, float)
                and x0 <= row["x"] <= x1 and y0 <= row["y"] <= y1)
    require(any(at(r, r"Food", 100, 300, 10, 90) for r in rows)
            and any(at(r, r"Inventory capacity [0-9]+/[0-9]+", 1300, 1850, 10, 90) for r in rows)
            and any(at(r, r"(?:UID:\s*)?" + re.escape(snapshot.identity.uid), 1600, 1900, 1000, 1080) for r in rows),
            "Exact held Food inventory and UID evidence is missing")
    return obs


def _terminal(snapshot: Snapshot, session: str, now: int, mission=None, request_id=None):
    request = parse(snapshot.evidence.request, 8192)
    receipt = parse(snapshot.evidence.final_receipt, MAX_RECEIPT)
    rid = request.get("id")
    require(type(rid) is str and REQUEST_ID.fullmatch(rid), "Invalid real request ID")
    require(request.get("session") == receipt.get("session") == session
            and receipt.get("id") == rid and receipt.get("mission") == request.get("mission")
            and receipt.get("status") in ("completed", "stopped")
            and receipt.get("frameId") == snapshot.frame,
            "Request and immutable final receipt do not match")
    require(integer(request.get("createdAt")) and integer(receipt.get("timestamp"))
            and request["createdAt"] <= receipt["timestamp"] <= now,
            "Invalid terminal receipt time order")
    observation = parse(snapshot.evidence.observation, COMPANION)
    require(integer(request.get("expectedFrameId"))
            and request["expectedFrameId"] <= snapshot.frame
            and integer(observation.get("timestamp"))
            and observation["timestamp"] <= receipt["timestamp"],
            "Terminal receipt predates its observation or has an invalid requested frame")
    if mission is not None:
        require(request.get("mission") == mission, "Unexpected terminal mission")
    if request_id is not None:
        require(rid == request_id, "Terminal request differs from the durably reconciled request")
    return request, receipt


def _capacity(snapshot: Snapshot, reserve: int):
    require(integer(snapshot.receipt_count) and integer(snapshot.receipt_bytes), "Invalid capacity inventory")
    require(snapshot.receipt_count <= 4094 - reserve
            and snapshot.receipt_bytes <= MAX_RECEIPT_TREE - reserve * MAX_RECEIPT - COMPANION,
            "Insufficient stop/observe native capacity reserve")


def _running(snapshot: Snapshot):
    require(snapshot.task_running is True and snapshot.service_owns_pilot is True
            and snapshot.script_state == "idle", "Expected sole-owned idle listener")
    require(integer(snapshot.heartbeat_at)
            and 0 <= snapshot.observed_at - snapshot.heartbeat_at <= MAX_AGE,
            "Listener heartbeat is stale or future-dated")


def _stopped(snapshot: Snapshot):
    require(snapshot.task_running is False and snapshot.service_owns_pilot is False
            and snapshot.script_state == "stopped", "Listener termination is not confirmed")


def _same_saved(evidence: Evidence, saved: dict, names=None):
    for name in names or tuple(asdict(evidence)):
        raw = getattr(evidence, name)
        require(digest(raw) == saved[name]["sha256"]
                and base64.b64encode(raw).decode("ascii") == saved[name]["base64"],
                "Preserved request, receipt or pause evidence changed")


def _continuity(snapshot: Snapshot, record: dict, now: int):
    proof, plan, stop = snapshot.menu_continuity, record["plan"], record["proofs"]["stop"]
    require(type(proof) is MenuContinuity, "Independent menu continuity evidence is unavailable")
    require(proof.source == "owner-menu-continuity-guard"
            and proof.transition_id == plan["id"] and proof.identity == snapshot.identity
            and proof.inventory_sha256 == stop["evidence"]["observation"]["sha256"]
            and proof.stop_request_sha256 == stop["evidence"]["request"]["sha256"]
            and proof.stop_receipt_sha256 == stop["evidence"]["final_receipt"]["sha256"],
            "Menu continuity is bound to different owner, game or source evidence")
    require(integer(proof.verified_at) and integer(proof.expires_at)
            and 0 <= now - proof.verified_at <= MAX_AGE
            and now <= proof.expires_at <= plan["expiresAt"],
            "Menu continuity guard is stale, expired or exceeds the transition")
    require(proof.same_game_verified is True and proof.held_through_exit is True
            and proof.native_trigger_menu_hold is True and proof.startup_menu_hold is True,
            "Menu continuity across exit, native triggers and startup is unverified")


def startup_contract(record: dict):
    """Pure fields for Root's reviewed one-use startup adapter; never writes it."""
    stop = record.get("proofs", {}).get("stop")
    require(stop is not None, "A real terminal stop proof is required before startup")
    return {"version": 1, "transitionId": record["plan"]["id"],
            "identity": record["plan"]["identity"],
            "oldSession": record["plan"]["oldSession"],
            "nextSession": record["plan"]["nextSession"],
            "createdAt": record["plan"]["createdAt"], "expiresAt": record["plan"]["expiresAt"],
            "oldFrame": stop["frame"], "stopRequestId": stop["requestId"],
            "stopEvidence": stop["evidence"], "originalEvidence": record["plan"]["originalEvidence"],
            "menuContinuity": (record.get("pending") or {}).get("menuContinuity")}


class Coordinator:
    def __init__(self, store: Store, adapter: Adapter, clock):
        self.store, self.adapter, self.clock = store, adapter, clock

    def prepare(self, snapshot: Snapshot, next_session: str, expires_at: int):
        with self.store.exclusive():
            return self._prepare(snapshot, next_session, expires_at)

    def _prepare(self, snapshot: Snapshot, next_session: str, expires_at: int):
        now = self.clock()
        require(self.store.load() is None, "A transition already exists; reconcile it instead of replacing it")
        _identity(snapshot, snapshot.identity, now)
        _running(snapshot)
        require(type(snapshot.session) is str and len(snapshot.session) <= 96
                and OLD_SESSION.fullmatch(snapshot.session), "Invalid current session")
        require(type(next_session) is str and len(next_session) <= 96
                and NEW_SESSION.fullmatch(next_session) and next_session != snapshot.session,
                "Successor must be a distinct native base-session name")
        require(snapshot.successor_unused is True, "Successor session is already used or unverified")
        require(integer(expires_at) and 0 < expires_at - now <= MAX_TTL, "Invalid transition expiry")
        _pause(snapshot, snapshot.session, now)
        _terminal(snapshot, snapshot.session, now)
        _capacity(snapshot, 2)
        plan = {"version": 1, "identity": asdict(snapshot.identity),
                "oldSession": snapshot.session, "nextSession": next_session,
                "oldFrame": snapshot.frame, "createdAt": now, "expiresAt": expires_at,
                "originalEvidence": snapshot.evidence.saved(),
                "capacity": {"count": snapshot.receipt_count, "bytes": snapshot.receipt_bytes}}
        plan["id"] = digest(encoded(plan))
        record = {"version": 1, "revision": 0, "plan": plan, "phase": "prepared",
                  "pending": None, "proofs": {}, "attempts": {}, "lastOutcome": None,
                  "clockHighWaterAt": now, "dispatchClosedReason": None}
        self.store.commit(record, None)
        return record

    def _save(self, record):
        previous = record["revision"]
        record["revision"] += 1
        self.store.commit(record, previous)

    def _load(self):
        record = self.store.load()
        require(type(record) is dict and record.get("version") == 1
                and record.get("phase") in PHASES and integer(record.get("revision")), "Invalid transition journal")
        plan = record.get("plan", {})
        require(plan.get("id") == digest(encoded({k: v for k, v in plan.items() if k != "id"})),
                "Transition contract changed")
        Identity(**plan["identity"]).validate()
        pending = record.get("pending")
        if pending is not None:
            expected = {"prepared": "stop", "stop-confirmed": "start",
                        "start-confirmed": "observe"}.get(record["phase"])
            require(type(pending) is dict and pending.get("operation") == expected
                    and type(pending.get("key")) is str and SHA.fullmatch(pending["key"])
                    and integer(pending.get("createdAt"))
                    and integer(pending.get("attempt"), 1)
                    and integer(pending.get("expectedFrame"), 1), "Invalid pending effect binding")
        require(integer(record.get("clockHighWaterAt"))
                and record["clockHighWaterAt"] >= plan["createdAt"]
                and record.get("dispatchClosedReason") in (None, "expired", "clock-rollback"),
                "Invalid durable transition clock guard")
        return record

    def _observe_clock(self, record, now, *, persist):
        """Remember observed expiry/rollback without preventing pending-effect reconciliation."""
        require(integer(now), "Invalid transition clock")
        previous = (record["clockHighWaterAt"], record["dispatchClosedReason"])
        if record["dispatchClosedReason"] is None:
            if now < record["clockHighWaterAt"]:
                record["dispatchClosedReason"] = "clock-rollback"
            elif now > record["plan"]["expiresAt"]:
                record["dispatchClosedReason"] = "expired"
        record["clockHighWaterAt"] = max(record["clockHighWaterAt"], now)
        changed = previous != (record["clockHighWaterAt"], record["dispatchClosedReason"])
        if persist and changed:
            self._save(record)
        return changed

    def _before(self, record, operation, snapshot, now):
        plan = record["plan"]
        self._observe_clock(record, now, persist=False)
        reason = record["dispatchClosedReason"]
        require(reason is None, "Transition expired; no new effect may be dispatched" if reason == "expired"
                else "Transition is future-dated or its clock moved backwards; no new effect may be dispatched")
        _identity(snapshot, Identity(**plan["identity"]), now)
        require(plan["createdAt"] <= now, "Transition is future-dated; no new effect may be dispatched")
        require(now <= plan["expiresAt"], "Transition expired; no new effect may be dispatched")
        expected_session = plan["oldSession"] if operation in ("stop", "start") else plan["nextSession"]
        # A stopped listener cannot refresh its old image. Only start may use
        # preserved historical source, with an independent live continuity guard.
        _pause(snapshot, expected_session, now, fresh=operation != "start")
        if operation == "stop":
            _running(snapshot)
            require(snapshot.frame == plan["oldFrame"], "Prepared frame changed")
            require(snapshot.successor_unused is True, "Successor session is no longer unused")
            _same_saved(snapshot.evidence, plan["originalEvidence"])
            _terminal(snapshot, expected_session, now)
            _capacity(snapshot, 2)
        elif operation == "start":
            _stopped(snapshot)
            stop = record["proofs"]["stop"]
            require(snapshot.frame == stop["frame"] and snapshot.successor_unused is True,
                    "Stopped boundary or successor availability changed")
            _same_saved(snapshot.evidence, stop["evidence"])
            _continuity(snapshot, record, now)
            _terminal(snapshot, expected_session, now, "stop", stop["requestId"])
            _capacity(snapshot, 1)
        elif operation == "observe":
            _running(snapshot)
            start = record["proofs"]["start"]
            require(snapshot.frame == start["frame"] and snapshot.transition_id == plan["id"]
                    and snapshot.suppressed_request_sha256 == record["proofs"]["stop"]["evidence"]["request"]["sha256"],
                    "Startup continuation binding changed")
            _same_saved(snapshot.evidence, start["evidence"])
            _capacity(snapshot, 1)

    def _confirm(self, record, pending, outcome, now):
        require(outcome.durable_proof is True and outcome.snapshot is not None,
                "Successful effect lacks durable provenance")
        snapshot, plan, operation = outcome.snapshot, record["plan"], pending["operation"]
        _identity(snapshot, Identity(**plan["identity"]), now)
        # Reconciliation may finish after expiry, but cannot authorize another effect.
        # Historical evidence is retained with its original time; the next dispatch
        # separately requires fresh source evidence and an unexpired contract.
        if operation == "stop":
            _stopped(snapshot)
            _pause(snapshot, plan["oldSession"], now, fresh=False)
            require(outcome.request_id is not None, "Stop request identity is missing")
            req, receipt = _terminal(snapshot, plan["oldSession"], now, "stop", outcome.request_id)
            require(receipt["status"] == "stopped" and req["createdAt"] >= pending["createdAt"]
                    and req["expectedFrameId"] == pending["expectedFrame"]
                    and snapshot.frame >= plan["oldFrame"], "Stop is not the newly submitted terminal request")
            phase = "stop-confirmed"
        elif operation == "start":
            _running(snapshot)
            observation = _pause(snapshot, plan["nextSession"], now, fresh=False)
            stop = record["proofs"]["stop"]
            require(snapshot.frame > stop["frame"] and snapshot.transition_id == plan["id"]
                    and snapshot.suppressed_request_sha256 == stop["evidence"]["request"]["sha256"],
                    "New listener has no matching consumed one-use continuation")
            require(observation["hud"]["captureStamp"]["capturedAt"] >= pending["createdAt"],
                    "Startup observation predates the authenticated start intent")
            _same_saved(snapshot.evidence, stop["evidence"], ("request", "final_receipt"))
            phase = "start-confirmed"
        else:
            _running(snapshot)
            observation = _pause(snapshot, plan["nextSession"], now, fresh=False)
            require(outcome.request_id is not None, "Observe request identity is missing")
            req, receipt = _terminal(snapshot, plan["nextSession"], now, "observe", outcome.request_id)
            require(receipt["status"] == "completed" and req["createdAt"] >= pending["createdAt"]
                    and req["expectedFrameId"] == pending["expectedFrame"]
                    and observation["hud"]["captureStamp"]["capturedAt"] >= req["createdAt"]
                    and snapshot.frame > record["proofs"]["start"]["frame"],
                    "Observe is not the newly submitted completed request")
            phase = "fresh-observe-confirmed"
        record["proofs"][operation] = {"frame": snapshot.frame,
                "requestId": outcome.request_id, "evidence": snapshot.evidence.saved(),
                "reconciledAt": now, "operationKey": pending["key"],
                "menuContinuity": pending.get("menuContinuity")}
        record["phase"], record["pending"] = phase, None
        record["lastOutcome"] = {"status": "succeeded", "operation": operation}
        self._save(record)
        return record

    def step(self):
        with self.store.exclusive():
            return self._step()

    def _step(self):
        record, now = self._load(), self.clock()
        if record["phase"] == "archive-eligible":
            return record
        # A closed dispatch gate is durable, but resolving an existing effect remains read-only.
        self._observe_clock(record, now, persist=True)
        pending = record["pending"]
        if pending:
            outcome = self.adapter.reconcile(pending["operation"], pending["key"], record["plan"])
            now = self.clock()
            self._observe_clock(record, now, persist=True)
            require(outcome.operation_key == pending["key"], "Reconciliation operation identity changed")
            require(outcome.status in ("not-submitted", "in-flight", "succeeded", "failed", "unknown"),
                    "Invalid reconciliation outcome")
            if outcome.status == "succeeded":
                return self._confirm(record, pending, outcome, now)
            if outcome.status == "not-submitted":
                require(outcome.durable_proof is True, "Non-submission lacks durable proof")
                record["pending"] = None
                record["lastOutcome"] = {"status": "not-submitted", "operation": pending["operation"]}
                self._save(record)
                return record  # Retry is a separate step with complete revalidation.
            record["lastOutcome"] = {"status": outcome.status, "operation": pending["operation"],
                                     "reason": outcome.reason}
            self._save(record)
            return record  # Includes terminal failure: preserve it; never blindly retry.
        snapshot = self.adapter.inspect(record["plan"])
        now = self.clock()
        self._observe_clock(record, now, persist=True)
        if record["phase"] == "fresh-observe-confirmed":
            _identity(snapshot, Identity(**record["plan"]["identity"]), now)
            _running(snapshot)
            _pause(snapshot, record["plan"]["nextSession"], now)
            _same_saved(snapshot.evidence, record["proofs"]["observe"]["evidence"])
            req, _ = _terminal(snapshot, record["plan"]["nextSession"], now, "observe",
                               record["proofs"]["observe"]["requestId"])
            require(req["session"] != record["plan"]["oldSession"], "Old current-request protection remains")
            record["phase"] = "archive-eligible"
            record["lastOutcome"] = {"status": "archive-eligible", "archiveExecuted": False}
            self._save(record)
            return record
        operation = {"prepared": "stop", "stop-confirmed": "start", "start-confirmed": "observe"}[record["phase"]]
        self._before(record, operation, snapshot, now)
        attempt = record["attempts"].get(operation, 0) + 1
        require(attempt <= MAX_ATTEMPTS, "Bounded dispatch attempts exhausted")
        key = digest(encoded([record["plan"]["id"], operation, attempt]))
        record["attempts"][operation] = attempt
        record["pending"] = {"operation": operation, "key": key, "createdAt": now,
                             "attempt": attempt, "expectedFrame": snapshot.frame}
        if operation == "start":
            record["pending"]["menuContinuity"] = asdict(snapshot.menu_continuity)
        record["lastOutcome"] = {"status": "dispatch-intent", "operation": operation}
        self._save(record)  # Always durable before the injected external effect.
        contract = startup_contract(record) if operation == "start" else None
        saved_clock = record["clockHighWaterAt"]
        try:
            # Disk/journal latency cannot renew the original five-second source.
            self._before(record, operation, snapshot, self.clock())
        except Held as exc:
            record["pending"] = None  # Dispatch has not been called: locally proven.
            record["lastOutcome"] = {"status": "not-submitted", "operation": operation,
                                     "reason": str(exc), "proof": "local-pre-dispatch-gate"}
            self._save(record)
            return record
        try:
            self.adapter.dispatch(operation, key, record["plan"], snapshot, contract)
        except Exception as exc:
            # An exception never proves non-submission. Leave the exact pending key.
            record["lastOutcome"] = {"status": "unknown", "operation": operation,
                                     "reason": type(exc).__name__}
            self._save(record)
        else:
            # Intent was already durable; retain the final successful clock sample as well.
            # A failed commit still leaves the original pending key for reconciliation.
            if record["clockHighWaterAt"] != saved_clock:
                self._save(record)
        return record
