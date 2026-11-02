"""Owner-only adapters for the reviewed prepared relay. Importing sends no input.

Native status is read only through the existing PID/WTS/SID-authenticated client.
The nonce never leaves this process; only its canonical lifetime digest is kept.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
import re
import time
from dataclasses import asdict
from pathlib import Path

from relay_prepared import HEARTBEAT_MAX_AGE_MS, heartbeat_matches, raw_object
from relay_reliability import Held, MAX_RECORD, OwnerContext, _directory, _regular, require


def normalized_app_directory(value):
    # This v1 contract is restricted to the ordinary ASCII drive path used by
    # this runtime. Reject namespaces/relative paths rather than normalize them
    # differently from the independently verified .NET GetFullPath recipe.
    require(type(value) is str and value.isascii()
            and re.fullmatch(r"[A-Za-z]:[\\/][A-Za-z0-9_ .:\\/-]+", value),
            "unsupported-native-app-path")
    require(not any(part.endswith((" ", ".")) and part not in (".", "..")
                    for part in value.replace("/", "\\").split("\\")),
            "ambiguous-native-app-path")
    return ntpath.normpath(value).rstrip("\\").lower()


def native_owner(status):
    require(type(status) is dict, "invalid-authenticated-status")
    pid, wts = status.get("processId"), status.get("windowsSessionId")
    session, nonce = status.get("scriptSession"), status.get("instanceNonce")
    require(type(pid) is int and pid > 0 and type(wts) is int and wts > 1,
            "invalid-native-owner-ids")
    require(type(session) is str and re.fullmatch(r"[a-z0-9]+-[a-z0-9]+(?:-r[23])?", session),
            "invalid-native-script-session")
    require(status.get("instanceType") == "ChildSession"
            and status.get("remoteDesktop") is True, "native-child-required")
    require(type(nonce) is str and re.fullmatch(r"[0-9a-f]{32}", nonce),
            "invalid-native-lifetime-nonce")
    # Exact ordered v1 fields. PowerShell ConvertTo-Json -Compress equivalence
    # is checked with a synthetic fixture; accepted values are ASCII-only.
    payload = {"version": 1, "processId": pid, "windowsSessionId": wts,
               "scriptSession": session,
               "appDirectory": normalized_app_directory(status.get("appDirectory")),
               "instanceType": status["instanceType"], "instanceNonce": nonce}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    owner = OwnerContext(session, pid, wts, hashlib.sha256(raw).hexdigest())
    owner.validate()
    return owner


class OwnerProvider:
    def __init__(self, authenticated_query, expected, app_directory, clock_ms=None):
        expected.validate()
        self.query = authenticated_query
        self.expected = expected
        self.app_directory = normalized_app_directory(str(app_directory))
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    def __call__(self, *, current_admission=None):
        try:
            status = self.query(self.expected.process_id, self.expected.windows_session_id)
        except Exception:
            raise Held("authenticated-native-status-unavailable") from None
        actual = native_owner(status)
        require(actual == self.expected, "authenticated-native-lifetime-changed")
        require(normalized_app_directory(status["appDirectory"]) == self.app_directory,
                "authenticated-native-app-changed")
        now, stamp = self.clock_ms(), status.get("heartbeatAtUnixMs")
        require(type(stamp) is int and 0 <= now - stamp <= HEARTBEAT_MAX_AGE_MS
                and status.get("heartbeatFresh") is True
                and status.get("serviceOwnsPilot") is True, "native-owned-heartbeat-required")
        if current_admission is not None:
            require(type(current_admission) is dict, "current-admission-required")
            frame = current_admission.get("frameId")
            heartbeat_matches(current_admission, {"owner": asdict(actual)}, frame, now)
            require(type(status.get("frameId")) is int and status["frameId"] == frame
                    and status.get("scriptState") == "idle" and status.get("pilotState") == "idle"
                    and status.get("activeRequestId") in (None, ""),
                    "native-current-admission-changed")
        return actual


def read_regular_utf8(path):
    path = Path(path)
    _directory(path.parent)
    info = _regular(path)
    require(0 < info.st_size <= MAX_RECORD, "invalid-native-proof-size")
    raw = path.read_bytes()
    require(0 < len(raw) <= MAX_RECORD, "invalid-native-proof-size")
    return raw.decode("utf-8")


class ReadOnlyCollector:
    """Two fresh owner-bracketed reads. There is deliberately no submit callback."""
    def __init__(self, root, owner_probe, receipt_path, observation_path,
                 clock_ms=None, monotonic_ms=None, sleep=None):
        self.root = Path(root)
        self.owner_probe = owner_probe
        self.receipt_path = receipt_path
        self.observation_path = observation_path
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self.monotonic_ms = monotonic_ms or (lambda: int(time.monotonic() * 1000))
        self.sleep = sleep or time.sleep

    def sample(self, prepared):
        before = self.owner_probe()
        inner = prepared["innerRequest"]
        request = read_regular_utf8(self.root / "request.json")
        receipt = read_regular_utf8(self.receipt_path(self.root, inner["session"], inner["id"]))
        # Decode solely to select the immutable filename; the journal separately
        # validates duplicate keys, exact IDs, chronology, status and all bytes.
        frame = json.loads(receipt).get("frameId")
        require(type(frame) is int and frame > 0, "recovery-frame-required")
        observed = read_regular_utf8(self.observation_path(self.root, inner["session"], frame))
        latest = read_regular_utf8(self.root / "observation.json")
        heartbeat = read_regular_utf8(self.root / "controller-status.json")
        # Authenticate native idle/frame/no-active-request against this exact
        # collected heartbeat; identity-only proof cannot establish quiescence.
        after = self.owner_probe(current_admission=raw_object(heartbeat))
        return {"ownerBefore": asdict(before), "ownerAfter": asdict(after),
                "readAtMs": self.clock_ms(), "monotonicMs": self.monotonic_ms(),
                "requestUtf8": request, "receiptUtf8": receipt, "observationUtf8": observed,
                "latestObservationUtf8": latest, "heartbeatUtf8": heartbeat}

    def __call__(self, prepared):
        first = self.sample(prepared)
        self.sleep(0.410)
        return {"samples": [first, self.sample(prepared)]}
