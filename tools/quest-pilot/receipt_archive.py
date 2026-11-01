"""Archive closed receipt sessions before request creation; never touch game evidence."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import stat
import time
from pathlib import Path

SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

TRIGGER_FILES = 3000
TARGET_FILES = 2000
TRIGGER_BYTES = 48 * 1024 * 1024
TARGET_BYTES = 32 * 1024 * 1024
MAX_ATTEMPTS = 3
MAX_RECEIPT_BYTES = 16 * 1024 * 1024
NATIVE_RECEIPT_BYTES = 64 * 1024 * 1024
NATIVE_COMPANION_BYTES = 128 * 1024
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")


class ArchiveBlocked(RuntimeError):
    """No request may be minted when safe capacity cannot be established."""


class PauseBoundaryUnavailable(ArchiveBlocked):
    """Historical archival must wait for a proven completed inventory boundary."""


def _native_headroom(count: int, size: int) -> bool:
    """Retain room for a new receipt and the unchanged native companion reserve."""
    return (count <= 4093
            and size <= NATIVE_RECEIPT_BYTES - MAX_RECEIPT_BYTES - NATIVE_COMPANION_BYTES)


def _ordinary(path: Path) -> Path:
    """Reject links and junctions before resolving an exact filesystem target."""
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ArchiveBlocked(f"Receipt archive path traverses a link or junction: {item}")
    return path.resolve()


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _status_snapshot(path: Path):
    """Tolerate only transient heartbeat rewrites, with at most 100 ms of waiting."""
    for attempt in range(3):
        try:
            return _json(path)
        except json.JSONDecodeError:
            if attempt == 2:
                raise
        except OSError as exc:
            if getattr(exc, "winerror", None) not in (32, 33) or attempt == 2:
                raise
        time.sleep(0.05)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _atomic(path: Path, value) -> None:
    """Commit helper-owned journal files outside the controller budget tree."""
    _ordinary(path)
    pending = path.with_name(path.name + ".writing")
    _ordinary(pending)
    with pending.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)


def _fence(root: Path, expected_session: str, process_id: int, windows_session_id: int):
    """Bind maintenance to the caller's already verified idle controller and request."""
    status_path = _ordinary(root / "controller-status.json")
    status = _status_snapshot(status_path)
    if not isinstance(status, dict) or type(status.get("heartbeatAt")) is not int:
        raise ArchiveBlocked("Controller heartbeat is invalid; no request was submitted.")
    age = int(time.time() * 1000) - status["heartbeatAt"]
    if (status.get("version") != 1 or status.get("session") != expected_session
            or status.get("processId") != process_id
            or status.get("windowsSessionId") != windows_session_id
            or status.get("state") != "idle" or status.get("activeRequestId") is not None
            or status.get("error") is not None or not 0 <= age <= 5000):
        raise ArchiveBlocked("Receipt maintenance requires the same fresh idle owner; no request was submitted.")
    request_path = _ordinary(root / "request.json")
    request_bytes = request_path.read_bytes() if request_path.exists() else b""
    request = json.loads(request_bytes.decode("utf-8-sig")) if request_bytes else {}
    protected = {expected_session}
    if isinstance(request.get("session"), str):
        protected.add(request["session"])
    return {
        "session": expected_session, "processId": process_id,
        "windowsSessionId": windows_session_id, "frameId": status.get("frameId"),
        "requestSha256": hashlib.sha256(request_bytes).hexdigest(),
        "protectedSessions": sorted(protected),
    }


def _same_fence(root: Path, binding: dict) -> None:
    current = _fence(root, binding["session"], binding["processId"], binding["windowsSessionId"])
    if current != {key: value for key, value in binding.items() if key != "pauseBoundary"}:
        raise ArchiveBlocked("Controller frame, session, or current request changed during maintenance.")
    if "pauseBoundary" in binding and _pause_boundary(root, current) != binding["pauseBoundary"]:
        raise ArchiveBlocked("The completed receipt or inventory pause evidence changed during maintenance.")


def _capture_start(observed: dict, session: str, frame: int):
    """Read explicit capture-start evidence without replacing it with publish time.

    The canonical engine retains the inventory UI-only declaration, while some
    existing runtimes retain a same-frame HUD captureStamp. Validate every
    declared representation and require agreement when both are present.
    """
    hud, capture_at = observed["hud"], None
    if "captureStamp" in hud:
        stamp = hud["captureStamp"]
        if (not isinstance(stamp, dict) or stamp.get("session") != session
                or type(stamp.get("frameId")) is not int or stamp["frameId"] != frame
                or stamp.get("source") != "game-capture-start"):
            raise PauseBoundaryUnavailable("Inventory capture provenance is invalid.")
        capture_at = stamp.get("capturedAt")
        if type(capture_at) is not int:
            raise PauseBoundaryUnavailable("Inventory capture start is not an integer timestamp.")
    timings = observed.get("timings")
    diagnostic = timings.get("mapDiagnostic") if isinstance(timings, dict) else None
    declared_ui = ("uiObservation" in observed or isinstance(diagnostic, dict)
                   and diagnostic.get("mode") == "inventory-ui-only-v1")
    if declared_ui:
        mode = observed.get("uiObservation")
        if (not isinstance(mode, dict) or set(mode) != {"version", "kind", "mapOmitted",
                "orientationOmitted", "observationStartedAtUnixMs"}
                or type(mode.get("version")) is not int or mode["version"] != 1
                or mode.get("kind") != "inventory-ui-only-v1"
                or mode.get("mapOmitted") is not True or mode.get("orientationOmitted") is not True
                or "map" not in observed or observed["map"] is not None or "compassAngle" in hud
                or diagnostic != {"reason": "Inventory UI-only v1: map and orientation deliberately omitted",
                                  "mode": "inventory-ui-only-v1"}
                or type(mode.get("observationStartedAtUnixMs")) is not int
                or capture_at is not None and capture_at != mode["observationStartedAtUnixMs"]):
            raise PauseBoundaryUnavailable("Inventory UI-only capture provenance is invalid or contradictory.")
        capture_at = mode["observationStartedAtUnixMs"]
    return capture_at


def _pause_boundary(root: Path, binding: dict) -> dict:
    """Verify the owner's held inventory boundary; never renew its capture time.

    This is evidence for passive maintenance only. After long maintenance, the
    caller must obtain a new observation before deciding on gameplay input.
    """
    def bounded_bytes(path):
        path = _ordinary(path)
        if path.stat().st_size > MAX_RECEIPT_BYTES:
            raise PauseBoundaryUnavailable("Pause evidence exceeds the bounded read.")
        return path.read_bytes()
    try:
        request_bytes = bounded_bytes(root / "request.json")
        request = json.loads(request_bytes.decode("utf-8-sig"))
        session, frame = binding["session"], binding["frameId"]
        identity = request.get("id") if isinstance(request, dict) else None
        if (not SAFE_NAME.fullmatch(session) or type(frame) is not int or frame < 1
                or not isinstance(identity, str) or not SAFE_NAME.fullmatch(identity)
                or request.get("session") != session
                or hashlib.sha256(request_bytes).hexdigest() != binding["requestSha256"]):
            raise PauseBoundaryUnavailable("Current request does not match the owned pause boundary.")
        receipt_bytes = bounded_bytes(root / "receipts" / session / (identity + ".json"))
        receipt = json.loads(receipt_bytes.decode("utf-8-sig"))
        observed_bytes = bounded_bytes(root / "observation.json")
        observed = json.loads(observed_bytes.decode("utf-8-sig"))
        immutable_bytes = bounded_bytes(root / "observations" / session / f"frame-{frame:04d}.json")
        immutable = json.loads(immutable_bytes.decode("utf-8-sig"))
        if (not isinstance(receipt, dict) or not isinstance(observed, dict)
                or receipt.get("status") not in ("completed", "stopped")
                or receipt.get("id") != identity or receipt.get("session") != session
                or receipt.get("mission") != request.get("mission")
                or receipt.get("frameId") != frame or observed.get("frameId") != frame
                or observed.get("session") != session or observed != immutable
                or observed.get("screenshotPath") != f"observations/{session}/frame-{frame:04d}.png"):
            raise PauseBoundaryUnavailable("A matching final receipt and immutable current observation are required.")
        hud, rows = observed.get("hud"), observed.get("ocr")
        if not isinstance(hud, dict) or not isinstance(rows, list):
            raise PauseBoundaryUnavailable("Inventory observation lacks structured HUD/OCR proof.")
        times = (request.get("createdAt"), _capture_start(observed, session, frame),
                 observed.get("timestamp"), receipt.get("timestamp"))
        if (any(type(value) is not int for value in times)
                or not 0 < times[0] <= times[1] <= times[2] <= times[3]
                or times[3] > int(time.time() * 1000)
                or any(hud.get(key) is True for key in
                       ("auto", "dialogueReady", "world", "loading", "climbing", "bigMap", "journal"))
                or hud.get("health") is not None):
            raise PauseBoundaryUnavailable("The current observation does not prove a held inventory pause.")
        def located(row, x0, x1, y0, y1):
            return (isinstance(row, dict) and isinstance(row.get("text"), str)
                    and type(row.get("x")) in (int, float) and type(row.get("y")) in (int, float)
                    and x0 <= row["x"] <= x1 and y0 <= row["y"] <= y1)
        labels = {"Food", "Weapons", "Artifacts", "Character Development Items", "Materials",
                  "Gadgets", "Quest", "Precious Items", "Furnishings"}
        headers = [row for row in rows if located(row, 100, 250, 15, 70)
                   and row["text"].strip() in labels]
        if len(headers) != 1:
            raise PauseBoundaryUnavailable("Inventory header proof is absent or ambiguous.")
        header = headers[0]["text"].strip()
        capacity = [row for row in rows if located(row, 1450, 1810, 15, 75)
                    and (re.fullmatch(r"Inventory capacity\s+\d+/\d+", row["text"].strip(), re.I)
                         or re.fullmatch(re.escape(header) + r" \d+/\d+", row["text"].strip()))]
        if len(capacity) != 1:
            raise PauseBoundaryUnavailable("Inventory capacity proof is absent or ambiguous.")
        return {"kind": "inventory", "session": session, "frameId": frame, "requestId": identity,
                "originalCaptureAt": times[1], "originalObservationAt": times[2],
                "finalReceiptSha256": hashlib.sha256(receipt_bytes).hexdigest(),
                "observationSha256": hashlib.sha256(observed_bytes).hexdigest(),
                "immutableObservationSha256": hashlib.sha256(immutable_bytes).hexdigest()}
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PauseBoundaryUnavailable("Completed inventory boundary evidence is unavailable.") from exc


def _inventory(receipts: Path):
    """Count metadata first; content hashing occurs only when maintenance is due."""
    count = size = 0
    sessions = []
    if not receipts.exists():
        return count, size, sessions
    _ordinary(receipts)
    def visit(directory: Path, depth: int):
        nonlocal count, size
        flat = []
        nested = False
        # Validate each entry before descending. scandir caches Windows metadata,
        # avoiding a fresh walk of every ancestor for every receipt on each call.
        with os.scandir(directory) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ArchiveBlocked(f"Receipt inventory encountered a link or junction: {entry.path}")
                if stat.S_ISDIR(info.st_mode):
                    nested = True
                    visit(Path(entry.path), depth + 1)
                elif stat.S_ISREG(info.st_mode):
                    count += 1
                    size += info.st_size
                    flat.append((Path(entry.path), info.st_mtime_ns))
                    if count > 16384:
                        raise ArchiveBlocked("Receipt tree exceeds the bounded archive inventory.")
                else:
                    raise ArchiveBlocked(f"Unexpected receipt filesystem entry: {entry.path}")
        if (depth == 1 and not nested and flat and SAFE_NAME.fullmatch(directory.name)
                and all(p.suffix == ".json" for p, _ in flat)):
            sessions.append((max(stamp for _, stamp in flat), directory, [p for p, _ in flat]))
    visit(receipts, 0)
    return count, size, sorted(sessions, key=lambda row: (row[0], row[1].name))


def _session_manifest(session: str, paths: list[Path]) -> dict:
    """Retain original filenames, JSON session identities, sizes, and hashes."""
    result = {}
    for path in paths:
        _ordinary(path)
        size = path.stat().st_size
        if size > MAX_RECEIPT_BYTES:
            raise ArchiveBlocked(f"Receipt exceeds the bounded archive read: {path.name}")
        payload = _json(path)
        if not isinstance(payload, dict) or payload.get("session") != session:
            raise ArchiveBlocked(f"Receipt session provenance does not match its directory: {path}")
        if payload.get("id") != path.stem:
            raise ArchiveBlocked(f"Receipt request identity does not match its filename: {path}")
        result[path.name] = {"bytes": size, "sha256": _digest(path)}
    return result


def _verify(directory: Path, entries: dict) -> None:
    _ordinary(directory)
    actual = list(directory.iterdir())
    if {p.name for p in actual} != set(entries) or any(not p.is_file() for p in actual):
        raise ArchiveBlocked(f"Receipt set changed or archive is incomplete: {directory}")
    for name, expected in entries.items():
        path = _ordinary(directory / name)
        if path.stat().st_size != expected["bytes"] or _digest(path) != expected["sha256"]:
            raise ArchiveBlocked(f"Receipt hash verification failed: {path}")


def _copy_receipt(source: Path, target: Path, expected: dict) -> None:
    """An interrupted copy can only leave a helper-owned staging file."""
    _ordinary(source)
    _ordinary(target)
    if target.exists():
        if target.stat().st_size != expected["bytes"] or _digest(target) != expected["sha256"]:
            raise ArchiveBlocked(f"Existing retained copy does not match the journal: {target}")
        return
    pending = _ordinary(target.with_name(target.name + ".copying"))
    if pending.exists():
        pending.unlink()  # Only this helper's uncommitted copy, never a source receipt.
    with source.open("rb") as source_stream, pending.open("xb") as output:
        shutil.copyfileobj(source_stream, output, length=1024 * 1024)
        output.flush()
        os.fsync(output.fileno())
    if pending.stat().st_size != expected["bytes"] or _digest(pending) != expected["sha256"]:
        raise ArchiveBlocked(f"Retained copy verification failed: {pending}")
    os.replace(pending, target)


@contextlib.contextmanager
def _lock(archive: Path):
    """Use an ordinary file lock released by the OS on process exit."""
    path = _ordinary(archive / "maintenance.lock")
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
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
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ArchiveBlocked("Another receipt archive operation is active; no request was submitted.") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _apply(root: Path, archive: Path, journal: dict) -> dict:
    plan = journal["plan"]
    unsigned = {key: value for key, value in plan.items() if key != "batchId"}
    expected_id = hashlib.sha256(json.dumps(unsigned, sort_keys=True).encode()).hexdigest()[:24]
    if (plan.get("version") != 2 or journal.get("version") != 2
            or plan.get("batchId") != expected_id
            or type(journal.get("attempts")) is not int or journal["attempts"] < 0):
        raise ArchiveBlocked("Receipt archive journal integrity is invalid; all evidence is preserved.")
    binding = plan["binding"]
    _same_fence(root, binding)
    if journal["attempts"] >= MAX_ATTEMPTS:
        raise ArchiveBlocked("Receipt archive reached three attempts; inspect its durable journal before retrying.")
    journal["attempts"] += 1
    _atomic(archive / "pending.json", journal)
    batch = _ordinary(archive / "batches" / plan["batchId"])
    batch.mkdir(parents=True, exist_ok=True)
    _atomic(batch / "manifest.json", plan)
    for session, entries in plan["sessions"].items():
        if session in binding["protectedSessions"] or not SAFE_NAME.fullmatch(session):
            raise ArchiveBlocked("An active or current-request session appeared in the archive plan.")
        source = _ordinary(root / "receipts" / session)
        target = _ordinary(batch / "sessions" / session)
        retained = _ordinary(batch / "retained-copy" / session)
        if target.exists():
            if source.exists():
                raise ArchiveBlocked("Both source and retired original exist; inspect the journal without overwriting either.")
            _verify(target, entries)
            continue
        _verify(source, entries)
        retained.mkdir(parents=True, exist_ok=True)
        for name, expected in entries.items():
            _copy_receipt(source / name, retained / name, expected)
        _verify(retained, entries)
        _same_fence(root, binding)
        _verify(source, entries)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Same-volume rename retires the original directory atomically only after
        # an independent retained copy has been completely verified.
        source.rename(target)
        _verify(target, entries)
    count, size, _ = _inventory(root / "receipts")
    result = {
        "status": "archived", "batchId": plan["batchId"],
        "archivedSessions": sorted(plan["sessions"]),
        "archivedReceipts": sum(len(v) for v in plan["sessions"].values()),
        "remainingReceipts": count, "remainingBytes": size,
        "manifest": str(batch / "manifest.json"), "attempts": journal["attempts"],
        "sourceImagesTouched": False, "activeSessionTouched": False,
        "pauseBoundary": binding["pauseBoundary"], "freshObservationRequiredBeforeInput": True,
    }
    _atomic(batch / "complete.json", result)
    # Clean only this operation's verified duplicate copies. The original receipt
    # directories remain intact under sessions/ for readback and rollback.
    for session, entries in plan["sessions"].items():
        target = _ordinary(batch / "sessions" / session)
        retained = _ordinary(batch / "retained-copy" / session)
        _verify(target, entries)
        if retained.exists():
            for path in retained.iterdir():
                _ordinary(path)
                expected = entries.get(path.name)
                if not expected or not path.is_file() or _digest(path) != expected["sha256"]:
                    raise ArchiveBlocked("Unexpected staging content was preserved for inspection.")
                path.unlink()
            retained.rmdir()
    copied = batch / "retained-copy"
    if copied.exists() and not any(copied.iterdir()):
        copied.rmdir()
    (archive / "pending.json").unlink()
    return result


def maintain(root: Path, archive: Path, expected_session: str, process_id: int,
             windows_session_id: int, *, trigger_files=TRIGGER_FILES,
             target_files=TARGET_FILES, trigger_bytes=TRIGGER_BYTES,
             target_bytes=TARGET_BYTES) -> dict:
    """Run once between requests, before IDs/timestamps/leases are created.

    The existing caller must verify sole-controller ownership first. A session
    other than the controller's and current request's session is historical in
    that single-writer lifecycle. No service, monitor, capture, or input is used.
    """
    root, archive = _ordinary(Path(root)), _ordinary(Path(archive))
    if (root.name != "ActOnePilot" or archive.is_relative_to(root)
            or root.is_relative_to(archive) or root.anchor.lower() != archive.anchor.lower()):
        raise ArchiveBlocked("Archive must be on the same volume and outside the complete ActOnePilot tree.")
    if not (0 <= target_files < trigger_files <= 4094
            and 0 <= target_bytes < trigger_bytes <= 64 * 1024 * 1024 - 128 * 1024):
        raise ArchiveBlocked("Archive watermarks must remain below the unchanged native receipt budget.")
    binding = _fence(root, expected_session, process_id, windows_session_id)
    count, size, candidates = _inventory(root / "receipts")
    pending = _ordinary(archive / "pending.json")
    if (not pending.exists() and count < trigger_files and size < trigger_bytes
            and _native_headroom(count, size)):
        _same_fence(root, binding)
        return {"status": "not_needed", "remainingReceipts": count, "remainingBytes": size}
    eligible = [row for row in candidates if row[1].name not in binding["protectedSessions"]]
    if not pending.exists() and not eligible:
        if _native_headroom(count, size):
            _same_fence(root, binding)
            return {"status": "deferred_no_closed_capacity",
                    "reason": "Only protected sessions remain; defer archival while native receipt headroom is available.",
                    "remainingReceipts": count, "remainingBytes": size, "archiveStarted": False}
        raise ArchiveBlocked(
            "No sufficient closed-session capacity: active/current-request receipts are preserved; "
            "the sole owner must establish a safe session lifecycle boundary before another request.")
    try:
        binding["pauseBoundary"] = _pause_boundary(root, binding)
    except PauseBoundaryUnavailable as exc:
        # Defer optional maintenance while the unchanged native maximum-size
        # receipt and companion reserve still fit. Never use this for pending
        # archive recovery or when another receipt could reach the hard budget.
        if not pending.exists() and _native_headroom(count, size):
            _same_fence(root, binding)
            return {"status": "deferred_until_inventory_pause", "reason": str(exc),
                    "remainingReceipts": count, "remainingBytes": size, "archiveStarted": False}
        raise ArchiveBlocked("Receipt capacity requires a verified completed inventory pause before another request.") from exc
    _same_fence(root, binding)
    archive.mkdir(parents=True, exist_ok=True)
    with _lock(archive):
        if pending.exists():
            journal = _json(pending)
            plan = journal.get("plan") or {}
            if plan.get("root") != str(root) or plan.get("archive") != str(archive) or plan.get("binding") != binding:
                raise ArchiveBlocked("Pending archive belongs to another owner/request boundary; inspect it before retrying.")
        else:
            selected = {}
            after_count, after_bytes = count, size
            for _, directory, paths in candidates:
                if directory.name in binding["protectedSessions"]:
                    continue
                entries = _session_manifest(directory.name, paths)
                selected[directory.name] = entries
                after_count -= len(entries)
                after_bytes -= sum(v["bytes"] for v in entries.values())
                if after_count <= target_files and after_bytes <= target_bytes:
                    break
            if not selected or not _native_headroom(after_count, after_bytes):
                raise ArchiveBlocked(
                    "No sufficient closed-session capacity: active/current-request receipts are preserved; "
                    "the sole owner must establish a safe session lifecycle boundary before another request.")
            reserve = max(sum(v["bytes"] for entries in selected.values() for v in entries.values()),
                          sum(len(entries) for entries in selected.values()) * 8192)
            if shutil.disk_usage(archive).free < 2 * 1024 * 1024 * 1024 + reserve:
                raise ArchiveBlocked("Insufficient headroom for a retained copy plus the native 2 GiB reserve.")
            plan = {"version": 2, "root": str(root), "archive": str(archive),
                    "binding": binding, "beforeReceipts": count, "beforeBytes": size,
                    "sessions": selected}
            plan["batchId"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()[:24]
            journal = {"version": 2, "attempts": 0, "plan": plan}
            _atomic(pending, journal)
        try:
            return _apply(root, archive, journal)
        except Exception as exc:
            journal["lastError"] = f"{type(exc).__name__}: {exc}"
            _atomic(pending, journal)
            raise
