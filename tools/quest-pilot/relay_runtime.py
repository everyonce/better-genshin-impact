"""Root-owned line-loop, guarded CLI adapter and bound historical result reader."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from owner_adapter import OwnerProvider, ReadOnlyCollector, read_regular_utf8
from relay_prepared import PreparedRelayJournal, raw_object, recovery_response, validate_prepared_result
from relay_reliability import Held, OUTER_ID, OwnerContext, binding, encode, parse_request, require


def consume(directory, request, owner, steps):
    """Validate persisted output against the exact caller request and owner pin.

    This is a historical reader. It neither queries native state nor grants an
    input lease; the next action must pass the ordinary guarded CLI anew.
    """
    directory = Path(directory)
    key = binding(request, owner, steps)
    identity = request["id"]
    intent = raw_object(read_regular_utf8(directory / (identity + ".intent.json")))
    require(encode(intent) == encode(key), "consumer-intent-mismatch")
    try:
        envelope = raw_object(read_regular_utf8(directory / (identity + ".recovery.json")))
    except FileNotFoundError:
        envelope = raw_object(read_regular_utf8(directory / (identity + ".response.json")))
    response = validate_prepared_result(envelope, request, owner, steps)
    if envelope.get("prepared") is not None:
        prepared = raw_object(read_regular_utf8(directory / (identity + ".prepared.json")))
        require(encode(prepared) == encode(envelope["prepared"]), "consumer-prepared-mismatch")
        inner = prepared["innerRequest"]["id"]
        claim = raw_object(read_regular_utf8(directory / ("inner-" + inner + ".claim.json")))
        require(claim == {"binding": key["binding"], "requestSha256": prepared["requestSha256"]},
                "consumer-inner-claim-mismatch")
    return {**response, "boundResult": True, "historicalRead": True, "replayed": True, "binding": key["binding"],
            "boundRequest": request, "owner": asdict(owner)}


class ControllerRelay:
    def __init__(self, command, command_path, journal, owner, steps, collector=None):
        self.command = command
        self.command_path = str(command_path)
        self.journal = journal
        self.owner = owner
        self.steps = frozenset(steps)
        self.collector = collector

    def dispatch(self, request, owner, prepare):
        argv = [self.command_path, request["kind"], "--frame", str(request["frame"]),
                "--session", owner.session, "--expected-windows-session-id", str(owner.windows_session_id),
                "--compact", "--wait-seconds", "300"]
        if request["kind"] == "questStep":
            argv += ["--step", request["step"]]
        saved, captured, code, error = sys.argv, io.StringIO(), 0, None
        try:
            sys.argv = argv
            with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                self.command.main(before_request_write=prepare)
        except SystemExit as exc:
            code = exc.code if type(exc.code) is int else 1
            if exc.code not in (None, 0):
                error = "guarded-cli-exit"
        except Exception as exc:
            code, error = 1, "guarded-cli-" + type(exc).__name__
        finally:
            sys.argv = saved
        candidates = []
        for line in captured.getvalue().splitlines():
            try:
                value = json.loads(line)
                if type(value) is dict and "status" in value and "frameId" in value:
                    candidates.append(value)
            except (ValueError, TypeError):
                pass
        require(len(candidates) <= 1, "ambiguous-guarded-cli-result")
        result = candidates[0] if candidates else None
        return {"id": request["id"], "code": code, "error": error, "result": result,
                "output": captured.getvalue()[-3000:] if result is None else None}

    def loop(self, lines, emit):
        for raw in lines:
            identity = None
            try:
                message = parse_request(raw)
                if message.get("kind") == "close":
                    require(set(message) == {"id", "kind"} and type(message["id"]) is str
                            and OUTER_ID.fullmatch(message["id"]), "invalid-close-envelope")
                    emit({"relayDone": message["id"], "code": 0, "closed": True})
                    break
                control = message.get("control")
                if control is not None:
                    require(set(message) == {"control", "request"}
                            and control in {"readResult", "reconcile"}, "invalid-relay-control")
                    request = message["request"]
                else:
                    request = message
                binding(request, self.owner, self.steps)
                identity = request["id"]
                emit({"relayAccepted": identity, "control": control})
                if control == "readResult":
                    envelope = self.journal.read_result(request, self.owner)
                elif control == "reconcile":
                    require(self.collector is not None, "read-only-collector-unavailable")
                    envelope = self.journal.reconcile(request, self.owner, self.collector)
                else:
                    envelope = self.journal.execute(request, self.owner, self.dispatch)
                if envelope.get("state") == "settled":
                    result = validate_prepared_result(envelope, request, self.owner, self.steps)
                    emit({"relayDone": identity, "code": result["code"], "state": "settled",
                          "binding": envelope["binding"], "replayed": envelope.get("replayed", False)})
                else:
                    emit({"relayDone": identity, "code": 1, "state": envelope.get("state", "held"),
                          "reason": envelope.get("reason", "unsettled-command"),
                          "binding": envelope.get("binding")})
            except Exception as exc:
                emit({"relayDone": identity, "code": 1, "state": "held",
                      "reason": str(exc) if isinstance(exc, Held) else type(exc).__name__})


def build(config, owner, command):
    command_path = Path(config["commandPath"])
    require(Path(command.ROOT).absolute() == Path(config["pilotRoot"]).absolute(),
            "guarded-cli-root-mismatch")
    provider = OwnerProvider(command.query_verified_service_status, owner, config["appDirectory"])
    journal = PreparedRelayJournal(config["journalDirectory"], config["steps"],
                                   owner_probe=provider, legacy_responses=config["legacyResponses"])
    collector = (ReadOnlyCollector(command.ROOT, provider, command.request_receipt_path,
                                   command.observation_path)
                 if config.get("recoveryEnabled") is True else None)
    return ControllerRelay(command, command_path, journal, owner, config["steps"], collector), provider


def run(args, config, command, source_verification):
    owner = OwnerContext(**config["owner"])
    owner.validate()
    if args.mode == "consume":
        require(args.request_file is not None, "exact-caller-request-required")
        request = parse_request(read_regular_utf8(args.request_file))
        print(json.dumps({**consume(config["journalDirectory"], request, owner, config["steps"]),
                          "sourceVerification": source_verification}), flush=True)
        return
    relay, provider = build(config, owner, command)
    provider()
    if args.mode == "qualify-recovery":
        require(args.request_file is not None, "exact-caller-request-required")
        request = parse_request(read_regular_utf8(args.request_file))
        consume(config["journalDirectory"], request, owner, config["steps"])
        prepared = raw_object(read_regular_utf8(Path(config["journalDirectory"]) /
                                               (request["id"] + ".prepared.json")))
        collector = ReadOnlyCollector(relay.command.ROOT, provider,
                                      relay.command.request_receipt_path, relay.command.observation_path)
        proof = collector(prepared)
        result = recovery_response(binding(request, owner, config["steps"]), prepared, proof,
                                   int(time.time() * 1000))["result"]
        print(json.dumps({"sourceVerification": source_verification, "recoveryQualified": True, "owner": asdict(owner),
                          "outerId": request["id"], "innerId": result["submittedId"],
                          "frame": result["frameId"], "samples": 2,
                          "quiescenceMs": proof["samples"][1]["monotonicMs"] - proof["samples"][0]["monotonicMs"],
                          "originalRequestCreatedAt": result["originalRequestCreatedAt"],
                          "observationTimestamp": result["observationTimestamp"],
                          "receiptTimestamp": result["receiptTimestamp"]}), flush=True)
        return
    if args.mode == "verify-owner":
        current = relay.command.read(relay.command.ROOT / "observation.json")
        admission = relay.command.require_live_controller(
            relay.command.ROOT, owner.session, current["frameId"], owner.windows_session_id)
        provider(current_admission=admission)
        print(json.dumps({"sourceVerification": source_verification, "ownerVerified": True, "owner": asdict(owner), "frame": current["frameId"]}), flush=True)
        return
    def emit(value):
        print(json.dumps(value, separators=(",", ":")), flush=True)
    emit({"sourceVerification": source_verification, "relayReady": True, "session": owner.session, "windowsSessionId": owner.windows_session_id,
          "ownerLifetimeBinding": owner.owner_lifetime_binding, "preparedProtocol": 2})
    relay.loop(sys.stdin, emit)

