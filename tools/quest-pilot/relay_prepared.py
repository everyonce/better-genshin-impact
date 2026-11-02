"""Inactive prepared-request journal extension. All native reads are injected.

No game, process, pipe, CLI loading, or input operations occur in this module.
The owner must supply authenticated lifetime checks and a read-only collector.
Missing evidence always holds the whole journal; reconciliation never dispatches.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict

from relay_reliability import (
    Held, MAX_RECORD, MISSION, OwnerContext, RelayJournal, _directory, _regular_if_present, _settled, _unique,
    binding, encode, require, sha, validate_result,
)

HEARTBEAT_MAX_AGE_MS = 5000  # Existing CLI heartbeat limit, not action freshness.
QUIESCENCE_MIN_MS = 400      # Existing CLI stable-quiescence window.


def raw_object(raw, limit=MAX_RECORD):
    require(type(raw) is str and 0 < len(raw.encode("utf-8")) <= limit,
            "invalid-proof-json-size")
    try:
        value = json.loads(raw, object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(Held("nonfinite-json")))
        require(type(value) is dict, "proof-json-must-be-object")
        encode(value)
        return value
    except (ValueError, UnicodeError) as exc:
        raise Held("invalid-proof-json") from exc


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def prepared_record(raw, key):
    require(type(raw) is bytes and 0 < len(raw) <= 8192, "invalid-prepared-request-bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise Held("prepared-request-not-utf8") from exc
    request = raw_object(text, 8192)
    fields = {"id", "session", "mission", "createdAt", "expectedFrameId"}
    if key["request"]["kind"] == "questStep":
        fields.add("step")
    require(set(request) == fields, "unsupported-inner-request-fields")
    require(type(request["id"]) is str and MISSION.fullmatch(request["id"]), "invalid-inner-id")
    require(request["session"] == key["owner"]["session"], "inner-session-mismatch")
    require(type(request["expectedFrameId"]) is int
            and request["expectedFrameId"] == key["request"]["frame"], "inner-frame-mismatch")
    require(request["mission"] == key["request"]["kind"], "inner-mission-mismatch")
    require(integer(request["createdAt"]), "invalid-original-request-time")
    if "step" in fields:
        require(request["step"] == key["request"]["step"], "inner-step-mismatch")
    return {"schema": "prepared-v1", "binding": key["binding"], "innerRequest": request,
            "requestUtf8": text, "requestSha256": hashlib.sha256(raw).hexdigest()}


def validate_prepared(value, key):
    require(type(value) is dict and type(value.get("requestUtf8")) is str,
            "missing-prepared-request")
    expected = prepared_record(value["requestUtf8"].encode("utf-8"), key)
    require(encode(value) == encode(expected), "prepared-binding-mismatch")
    return expected


def heartbeat_matches(heartbeat, key, frame, now_ms):
    require(type(heartbeat) is dict, "missing-heartbeat")
    owner = key["owner"]
    require(heartbeat.get("version") == 1 and type(heartbeat.get("version")) is int
            and heartbeat.get("session") == owner["session"]
            and type(heartbeat.get("processId")) is int
            and heartbeat["processId"] == owner["process_id"]
            and type(heartbeat.get("windowsSessionId")) is int
            and heartbeat["windowsSessionId"] == owner["windows_session_id"]
            and heartbeat.get("remoteDesktop") is True, "heartbeat-owner-mismatch")
    require(integer(heartbeat.get("heartbeatAt")) and integer(now_ms)
            and 0 <= now_ms - heartbeat["heartbeatAt"] <= HEARTBEAT_MAX_AGE_MS,
            "stale-or-future-heartbeat")
    require(type(heartbeat.get("frameId")) is int and heartbeat["frameId"] == frame,
            "heartbeat-frame-mismatch")
    require(heartbeat.get("state") == "idle" and heartbeat.get("activeRequestId") in (None, ""),
            "controller-not-idle")


def recovery_response(key, prepared, proof, verified_at):
    """Validate two stable, positive completed outcomes from an owner-only reader.

    The wall/monotonic sampling times are trusted collector metadata, never relay
    input. Historical observations are output evidence only. No input lease is
    renewed and no missing-file conclusion is permitted.
    """
    require(type(proof) is dict and set(proof) == {"samples"}
            and type(proof["samples"]) is list and len(proof["samples"]) == 2,
            "two-positive-recovery-samples-required")
    inner = prepared["innerRequest"]
    samples = proof["samples"]
    required = {"ownerBefore", "ownerAfter", "readAtMs", "monotonicMs", "requestUtf8",
                "receiptUtf8", "observationUtf8", "latestObservationUtf8", "heartbeatUtf8"}
    decoded = []
    for sample in samples:
        require(type(sample) is dict and set(sample) == required, "incomplete-recovery-sample")
        require(encode(sample["ownerBefore"]) == encode(key["owner"])
                and encode(sample["ownerAfter"]) == encode(key["owner"]), "recovery-owner-changed")
        require(integer(sample["readAtMs"]) and integer(sample["monotonicMs"]), "invalid-sample-clock")
        require(sample["requestUtf8"] == prepared["requestUtf8"], "current-request-bytes-mismatch")
        receipt = raw_object(sample["receiptUtf8"])
        observed = raw_object(sample["observationUtf8"])
        latest = raw_object(sample["latestObservationUtf8"])
        heartbeat = raw_object(sample["heartbeatUtf8"])
        require(receipt.get("id") == inner["id"] and receipt.get("session") == inner["session"]
                and receipt.get("mission") == inner["mission"] and receipt.get("status") == "completed",
                "matching-completed-receipt-required")
        frame = receipt.get("frameId")
        require(integer(frame) and frame > inner["expectedFrameId"]
                and observed.get("session") == inner["session"]
                and type(observed.get("frameId")) is int and observed["frameId"] == frame,
                "post-request-immutable-observation-required")
        require(integer(observed.get("timestamp")) and integer(receipt.get("timestamp"))
                and inner["createdAt"] <= observed["timestamp"] <= receipt["timestamp"] <= sample["readAtMs"],
                "invalid-completion-chronology")
        require(latest.get("session") == inner["session"] and integer(latest.get("frameId"))
                and latest["frameId"] >= frame and integer(latest.get("timestamp"))
                and observed["timestamp"] <= latest["timestamp"] <= sample["readAtMs"],
                "latest-observation-mismatch")
        heartbeat_matches(heartbeat, key, latest["frameId"], sample["readAtMs"])
        decoded.append((receipt, observed, latest))
    first, last = samples
    require(QUIESCENCE_MIN_MS <= last["monotonicMs"] - first["monotonicMs"] <= 5000
            and 0 <= last["readAtMs"] - first["readAtMs"] <= 5000, "quiescence-window-unproven")
    require(integer(verified_at) and 0 <= verified_at - last["readAtMs"] <= HEARTBEAT_MAX_AGE_MS,
            "recovery-proof-is-stale")
    for name in ("requestUtf8", "receiptUtf8", "observationUtf8", "latestObservationUtf8"):
        require(first[name] == last[name], "recovery-evidence-changed")
    receipt, observed, latest = decoded[-1]
    result = {"submittedId": inner["id"], "terminalId": inner["id"], "session": inner["session"],
              "status": "completed", "frameId": receipt["frameId"], "latestFrameId": latest["frameId"],
              "controllerState": "idle", "controllerQuiescent": True, "historicalOutcome": True,
              "originalRequestCreatedAt": inner["createdAt"], "observationTimestamp": observed["timestamp"],
              "receiptTimestamp": receipt["timestamp"], "details": receipt.get("details")}
    return {"id": key["request"]["id"], "code": 0, "error": None, "result": result, "output": None}


def validate_prepared_result(envelope, request, owner, steps):
    response = validate_result(envelope, request, owner, steps)
    key = binding(request, owner, steps)
    require(envelope.get("preparedSchema") == "prepared-v1", "prepared-result-schema-required")
    if response["result"]["status"] == "deferred":
        require(envelope.get("prepared") is None and envelope.get("recovery") is None,
                "deferred-result-has-prepared-request")
        return response
    prepared = validate_prepared(envelope.get("prepared"), key)
    require(response["result"]["submittedId"] == prepared["innerRequest"]["id"], "terminal-inner-id-mismatch")
    recovery = envelope.get("recovery")
    if recovery is not None:
        require(type(recovery) is dict and set(recovery) == {"proof", "verifiedAtMs", "proofSha256"},
                "invalid-recovery-record")
        require(recovery["proofSha256"] == sha(recovery["proof"]), "recovery-proof-digest-mismatch")
        expected = recovery_response(key, prepared, recovery["proof"], recovery["verifiedAtMs"])
        require(encode(expected) == encode(response), "recovered-response-mismatch")
    return response


class PreparedRelayJournal(RelayJournal):
    """Same persistent OS lock and active marker as v1; no production wiring.

    dispatch(outer, owner, prepare) must run the guarded CLI with its new optional
    before_request_write callback. prepare(raw_bytes, guarded_heartbeat) returns
    an acknowledgment only after fsync and a second authenticated owner check.
    The required legacy folder is a collision guard, not a recovery source.
    """

    def __init__(self, directory, steps, *, owner_probe, legacy_responses, clock_ms=None):
        super().__init__(directory, steps, legacy_responses=legacy_responses)
        require(self.legacy is not None and callable(owner_probe), "owner-adapters-required")
        self.owner_probe = owner_probe
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    def _owner(self, owner, current_admission=None):
        actual = (self.owner_probe() if current_admission is None else
                  self.owner_probe(current_admission=json.loads(encode(current_admission))))
        require(type(actual) is OwnerContext and actual == owner, "authenticated-owner-changed")
        actual.validate()

    def _prepared(self, key):
        value = self._read(key["request"]["id"] + ".prepared.json")
        if value is None:
            return None
        prepared = validate_prepared(value, key)
        claim = self._read("inner-" + prepared["innerRequest"]["id"] + ".claim.json")
        require(claim == {"binding": key["binding"], "requestSha256": prepared["requestSha256"]},
                "inner-id-claim-mismatch")
        return prepared

    def _response(self, key):
        recovered = self._read(key["request"]["id"] + ".recovery.json")
        if recovered is not None:
            require(recovered.get("state") == "settled" and type(recovered.get("recovery")) is dict,
                    "invalid-recovery-record-state")
        response = recovered if recovered is not None else super()._response(key)
        if response is not None and response.get("state") == "settled":
            validate_prepared_result(response, key["request"], OwnerContext(**key["owner"]), self.steps)
            require(encode(response.get("prepared")) == encode(self._prepared(key)), "stored-prepared-mismatch")
        return response

    def execute(self, request, owner, dispatch):
        key = binding(request, owner, self.steps)
        identity = request["id"]
        try:
            with self._lock():
                self._owner(owner)
                _directory(self.legacy)
                require(_regular_if_present(self.legacy / (identity + ".json")) is None,
                        "legacy-unbound-response")
                saved = self._read(identity + ".intent.json")
                if saved is not None:
                    self._intent(saved)
                    require(encode(saved) == encode(key), "request-binding-mismatch")
                    response = self._response(key)
                    return ({**response, "replayed": True} if response is not None else
                            {**key, "state": "unknown", "reason": "intent-without-response", "response": None})
                for suffix in (".response.json", ".prepared.json", ".recovery.json"):
                    require(self._read(identity + suffix) is None, "record-without-intent")
                self._clear_settled_active()
                self._new("active.json", key)
                self._checkpoint("after-active")
                self._new(identity + ".intent.json", key)
                self._checkpoint("after-intent")
                open_window, called = True, False

                def prepare(raw, heartbeat):
                    nonlocal called
                    require(open_window and not called, "prepared-callback-not-single-use")
                    called = True
                    # Freeze the original admission clock before a caller or owner probe can reuse its dictionary.
                    require(type(heartbeat) is dict, "missing-heartbeat")
                    heartbeat = json.loads(encode(heartbeat))
                    self._owner(owner)
                    heartbeat_matches(heartbeat, key, key["request"]["frame"], self.clock_ms())
                    prepared = prepared_record(raw, key)
                    require(self._read("active.json") == key, "active-marker-changed")
                    self._checkpoint("before-prepared")
                    claim_name = "inner-" + prepared["innerRequest"]["id"] + ".claim.json"
                    require(self._read(claim_name) is None, "inner-id-already-prepared")
                    self._new(claim_name, {"binding": key["binding"], "requestSha256": prepared["requestSha256"]})
                    self._checkpoint("after-inner-claim")
                    self._new(identity + ".prepared.json", prepared)
                    self._checkpoint("after-prepared")
                    require(encode(self._prepared(key)) == encode(prepared), "prepared-readback-mismatch")
                    self._owner(owner)
                    heartbeat_matches(heartbeat, key, key["request"]["frame"], self.clock_ms())

                    def revalidate(current_heartbeat):
                        require(open_window and called, "submission-window-closed")
                        require(self._read("active.json") == key, "active-marker-changed")
                        require(encode(self._prepared(key)) == encode(prepared), "prepared-readback-mismatch")
                        # The owner adapter must authenticate native status anew and
                        # compare its admission fields to this freshly read heartbeat.
                        self._owner(owner, current_heartbeat)
                        heartbeat_matches(heartbeat, key, key["request"]["frame"], self.clock_ms())
                        heartbeat_matches(current_heartbeat, key, key["request"]["frame"], self.clock_ms())

                    return {"requestId": prepared["innerRequest"]["id"],
                            "requestSha256": prepared["requestSha256"], "binding": key["binding"],
                            "durable": True, "revalidate": revalidate}

                try:
                    response = dispatch(dict(key["request"]), owner, prepare)
                except Exception as exc:
                    response = {"id": identity, "code": 1, "error": "dispatch-" + type(exc).__name__,
                                "result": None, "output": None}
                finally:
                    open_window = False
                self._checkpoint("after-dispatch")
                self._owner(owner)
                envelope = {**key, "preparedSchema": "prepared-v1", "prepared": self._prepared(key),
                            "state": "settled" if _settled(response, key) else "unknown", "response": response}
                if envelope["state"] == "settled":
                    validate_prepared_result(envelope, request, owner, self.steps)
                self._new(identity + ".response.json", envelope)
                self._checkpoint("after-response")
                if envelope["state"] == "settled":
                    self._clear_settled_active()
                return {**envelope, "replayed": False}
        except Held as exc:
            return self._held(key, str(exc))
        except (OSError, TypeError, ValueError):
            return self._held(key, "storage-or-response-error")

    def reconcile(self, request, owner, collect_proof):
        key = binding(request, owner, self.steps)
        identity = request["id"]
        try:
            with self._lock():
                self._owner(owner)
                require(encode(self._read(identity + ".intent.json")) == encode(key), "no-matching-intent")
                previous = self._response(key)
                if previous is not None and previous.get("state") == "settled":
                    return {**previous, "replayed": True}
                require(encode(self._read("active.json")) == encode(key), "matching-active-intent-required")
                prepared = self._prepared(key)
                require(prepared is not None, "missing-prepared-request")
                self._checkpoint("before-recovery-read")
                proof = json.loads(encode(collect_proof(json.loads(encode(prepared)))))
                self._owner(owner)
                verified_at = self.clock_ms()
                response = recovery_response(key, prepared, proof, verified_at)
                envelope = {**key, "preparedSchema": "prepared-v1", "prepared": prepared, "state": "settled",
                            "response": response, "recovery": {"proof": proof, "verifiedAtMs": verified_at,
                                                               "proofSha256": sha(proof)}}
                validate_prepared_result(envelope, request, owner, self.steps)
                self._new(identity + ".recovery.json", envelope)
                self._checkpoint("after-recovery")
                self._clear_settled_active()
                return {**envelope, "replayed": True}
        except Held as exc:
            return self._held(key, str(exc))
        except Exception:
            return self._held(key, "recovery-read-or-storage-error")

    def read_result(self, request, owner):
        key = binding(request, owner, self.steps)
        with self._lock():
            self._owner(owner)
            require(encode(self._read(request["id"] + ".intent.json")) == encode(key), "no-matching-intent")
            response = self._response(key)
            require(response is not None, "intent-without-response")
            validate_prepared_result(response, request, owner, self.steps)
            self._owner(owner)
            return {**response, "replayed": True}
