"""Deterministic injected-adapter tests; never imports a live controller module."""
import copy
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from receipt_rollover import (Coordinator, Evidence, FileStore, Held, Identity, MenuContinuity, Reconciliation,
                      Snapshot, digest, encoded, startup_contract, _journal_lock)


OLD = "oldnative-listener-r3"
NEW = "newnative-listener"
IDENTITY = Identity(4242, 2, "123456789", "a" * 64)
SCRATCH = Path(os.environ.get("BETTERGI_TEST_TMP", tempfile.gettempdir())) / "receipt-rollover-tests"


class Clock:
    def __init__(self):
        self.now = 1_000_000

    def __call__(self):
        return self.now


def evidence(session, frame, now, *, number=1, mission="observe", status="completed", created=None):
    request = {"id": "mission-" + format(number, "032x"), "session": session,
               "expectedFrameId": frame - 1, "createdAt": now - 2000 if created is None else created,
               "mission": mission}
    observation = {"session": session, "frameId": frame, "timestamp": now - 1000,
                   "hud": {"world": False, "health": None,
                           "captureStamp": {"session": session, "frameId": frame,
                                            "capturedAt": now - 1100, "source": "game-capture-start"}},
                   "ocr": [{"text": "Food", "x": 140, "y": 32},
                           {"text": "Inventory capacity 487/2600", "x": 1476, "y": 34},
                           {"text": "UID: 123456789", "x": 1688, "y": 1048}]}
    receipt = {"session": session, "id": request["id"], "mission": mission,
               "status": status, "timestamp": now - 500, "frameId": frame,
               "details": {"inputEvents": [{"type": "controllerRevision"}], "result": None}}
    raw_obs = encoded(observation)
    return Evidence(encoded(request), encoded(receipt), raw_obs, raw_obs)


def initial(clock, **changes):
    value = Snapshot(IDENTITY, True, clock(), True, OLD, 100, "idle", True, True,
                     None, None, clock() - 20, evidence(OLD, 100, clock()),
                     3000, 2_000_000, True, True, True, True)
    return replace(value, **changes)


class MemoryStore:
    def __init__(self):
        self.value = None
        self.fail_phase = None
        self.fail_intent = False
        self.owned = False

    @contextlib.contextmanager
    def exclusive(self):
        if self.owned:
            raise Held("Another coordinator holds the OS lock")
        self.owned = True
        try:
            yield
        finally:
            self.owned = False

    def load(self):
        return copy.deepcopy(self.value)

    def commit(self, value, expected_revision):
        actual = None if self.value is None else self.value["revision"]
        if actual != expected_revision:
            raise Held("Journal revision changed")
        if self.fail_intent and value.get("pending"):
            raise OSError("fixture journal write failure")
        if self.fail_phase == value["phase"] and value.get("pending") is None:
            self.fail_phase = None
            raise SimulatedCrash("effect happened; confirmation was not committed")
        self.value = copy.deepcopy(value)


class SimulatedCrash(BaseException):
    pass


class FakeAdapter:
    def __init__(self, clock, store):
        self.clock, self.store = clock, store
        self.current = initial(clock)
        self.calls, self.reconciliations, self.outcomes = [], [], {}
        self.mode = {}
        self.inspect_delay = 0
        self.provide_continuity = True
        self.continuity_changes = {}

    def inspect(self, plan):
        self.clock.now += self.inspect_delay
        self.current = replace(self.current, observed_at=self.clock())
        record = self.store.load()
        if (self.provide_continuity and record and record["phase"] == "stop-confirmed"
                and self.current.script_state == "stopped"):
            source = record["proofs"]["stop"]["evidence"]
            guard = MenuContinuity(plan["id"], self.current.identity,
                source["observation"]["sha256"], source["request"]["sha256"],
                source["final_receipt"]["sha256"], self.clock(), plan["expiresAt"],
                True, True, True, True)
            self.current = replace(self.current, menu_continuity=replace(guard, **self.continuity_changes))
        elif not self.provide_continuity:
            self.current = replace(self.current, menu_continuity=None)
        return self.current

    def dispatch(self, operation, key, plan, expected, contract):
        durable = self.store.load()
        assert durable["pending"]["key"] == key
        assert durable["pending"]["operation"] == operation
        self.calls.append((operation, key))
        mode = self.mode.get(operation)
        if mode == "not-submitted":
            self.outcomes[key] = Reconciliation("not-submitted", key, durable_proof=True)
            raise TimeoutError("fixture: proved not sent by durable owner record")
        if mode in ("unknown", "in-flight", "failed"):
            self.outcomes[key] = Reconciliation(mode, key, reason="fixture outcome", durable_proof=True)
            return
        dispatched = self.clock()
        self.clock.now += 2000
        now = self.clock()
        if operation == "stop":
            self.current = replace(self.current, observed_at=now, heartbeat_at=now - 20,
                script_state="stopped", task_running=False, service_owns_pilot=False,
                frame=self.current.frame + 1, receipt_count=self.current.receipt_count + 1,
                receipt_bytes=self.current.receipt_bytes + 1024,
                evidence=evidence(OLD, self.current.frame + 1, now, number=2,
                                  mission="stop", status="stopped", created=dispatched))
            rid = json.loads(self.current.evidence.request)["id"]
        elif operation == "start":
            assert contract["stopEvidence"]["request"]["sha256"] == digest(expected.evidence.request)
            fresh = evidence(NEW, self.current.frame + 1, now)
            self.current = replace(self.current, observed_at=now, heartbeat_at=now - 20,
                session=NEW, script_state="idle", task_running=True, service_owns_pilot=True,
                frame=self.current.frame + 1, successor_unused=False,
                evidence=Evidence(self.current.evidence.request, self.current.evidence.final_receipt,
                                  fresh.observation, fresh.immutable_observation),
                transition_id=plan["id"], suppressed_request_sha256=digest(expected.evidence.request))
            rid = None
        else:
            self.current = replace(self.current, observed_at=now, heartbeat_at=now - 20,
                frame=self.current.frame + 1, receipt_count=self.current.receipt_count + 1,
                receipt_bytes=self.current.receipt_bytes + 1024,
                evidence=evidence(NEW, self.current.frame + 1, now, number=3, created=dispatched))
            rid = json.loads(self.current.evidence.request)["id"]
        self.outcomes[key] = Reconciliation("succeeded", key, self.current, rid, durable_proof=True)
        if mode == "crash-after-effect":
            raise SimulatedCrash(operation)
        if mode == "timeout-after-effect":
            raise TimeoutError(operation)

    def reconcile(self, operation, key, plan):
        self.reconciliations.append((operation, key))
        outcome = self.outcomes.get(key, Reconciliation("unknown", key))
        if outcome.snapshot is not None:
            # Authentication/status is fresh; original evidence timestamps stay intact.
            outcome = replace(outcome, snapshot=replace(outcome.snapshot, observed_at=self.clock()))
        return outcome


class RolloverTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = MemoryStore()
        self.adapter = FakeAdapter(self.clock, self.store)
        self.coordinator = Coordinator(self.store, self.adapter, self.clock)

    def prepare(self, snapshot=None):
        value = snapshot or self.adapter.current
        self.adapter.current = value
        return self.coordinator.prepare(value, NEW, self.clock() + 120_000)

    def to_phase(self, phase):
        if self.store.load() is None:
            self.prepare()
        for _ in range(8):
            if self.store.load()["phase"] == phase:
                return self.store.load()
            self.coordinator.step()
        self.fail("fixture did not reach " + phase)

    def test_complete_transition_preserves_original_and_stop_evidence_without_archive(self):
        original = self.prepare()["plan"]["originalEvidence"]
        final = self.to_phase("archive-eligible")
        self.assertEqual([op for op, _ in self.adapter.calls], ["stop", "start", "observe"])
        self.assertEqual(final["plan"]["originalEvidence"], original)
        self.assertEqual(final["proofs"]["start"]["evidence"]["request"],
                         final["proofs"]["stop"]["evidence"]["request"])
        self.assertFalse(final["lastOutcome"]["archiveExecuted"])
        self.assertEqual(self.coordinator.step(), final)
        self.assertEqual(len(self.adapter.calls), 3)

    def test_no_effect_before_durable_intent(self):
        self.prepare()
        self.store.fail_intent = True
        with self.assertRaises(OSError):
            self.coordinator.step()
        self.assertEqual(self.adapter.calls, [])

    def test_future_created_transition_holds_even_with_fresh_status(self):
        prepared = self.prepare()
        self.clock.now -= 250
        self.adapter.current = replace(self.adapter.current,
            observed_at=self.clock(), heartbeat_at=self.clock() - 20)
        self.assertGreater(prepared["plan"]["createdAt"], self.clock())
        self.assertLessEqual(json.loads(self.adapter.current.evidence.final_receipt)["timestamp"],
                             self.clock())
        with self.assertRaisesRegex(Held, "future-dated"):
            self.coordinator.step()
        self.assertEqual(self.adapter.calls, [])
        self.assertIsNone(self.store.load()["pending"])

    def test_expiry_stays_closed_after_rollback_and_coordinator_reload(self):
        """An observed expiry is permanent for new effects, even after restart and clock recovery."""
        self.to_phase("stop-confirmed")
        expiry = self.store.load()["plan"]["expiresAt"]
        self.clock.now = expiry + 1
        with self.assertRaisesRegex(Held, "expired"):
            self.coordinator.step()
        self.assertEqual(self.store.load()["dispatchClosedReason"], "expired")
        self.assertEqual(self.store.load()["clockHighWaterAt"], expiry + 1)
        self.coordinator = Coordinator(self.store, self.adapter, self.clock)
        self.clock.now = expiry - 1000
        with self.assertRaisesRegex(Held, "expired"):
            self.coordinator.step()
        self.assertEqual([op for op, _ in self.adapter.calls], ["stop"])
        self.assertIsNone(self.store.load()["pending"])
        self.assertEqual(self.store.load()["plan"]["expiresAt"], expiry)

    def test_clock_high_water_survives_refusal_reload_and_forward_recovery(self):
        """A backward sample within the original TTL cannot regain dispatch permission later."""
        self.to_phase("stop-confirmed")
        self.clock.now += 100
        high_water = self.clock()
        self.adapter.provide_continuity = False
        with self.assertRaisesRegex(Held, "continuity"):
            self.coordinator.step()
        self.assertEqual(self.store.load()["clockHighWaterAt"], high_water)
        self.coordinator = Coordinator(self.store, self.adapter, self.clock)
        self.adapter.provide_continuity = True
        self.clock.now -= 50
        with self.assertRaisesRegex(Held, "backwards"):
            self.coordinator.step()
        self.assertEqual(self.store.load()["dispatchClosedReason"], "clock-rollback")
        self.clock.now = high_water + 1
        with self.assertRaisesRegex(Held, "backwards"):
            Coordinator(self.store, self.adapter, self.clock).step()
        self.assertEqual([op for op, _ in self.adapter.calls], ["stop"])

    def test_pending_effect_reconciles_after_expiry_and_rollback_without_new_effect(self):
        """The clock latch must not suppress read-only accounting for an already submitted stop."""
        self.prepare()
        pending = self.coordinator.step()["pending"]
        success = self.adapter.outcomes[pending["key"]]
        self.adapter.outcomes[pending["key"]] = Reconciliation("in-flight", pending["key"])
        expiry = self.store.load()["plan"]["expiresAt"]
        self.clock.now = expiry + 1
        self.assertIsNotNone(self.coordinator.step()["pending"])
        self.adapter.outcomes[pending["key"]] = success
        self.clock.now = expiry - 1000
        restored = Coordinator(self.store, self.adapter, self.clock)
        record = restored.step()
        self.assertEqual(record["phase"], "stop-confirmed")
        self.assertEqual(record["dispatchClosedReason"], "expired")
        self.assertEqual(record["proofs"]["stop"]["operationKey"], pending["key"])
        self.assertIsNone(record["pending"])
        with self.assertRaisesRegex(Held, "expired"):
            restored.step()
        self.assertEqual([op for op, _ in self.adapter.calls], ["stop"])

    def test_final_pre_dispatch_clock_rollback_is_durably_closed(self):
        """A rollback during intent storage closes dispatch before the adapter receives any effect."""
        prepared = self.prepare()
        original_commit = self.store.commit
        def rollback_after_intent(value, expected):
            original_commit(value, expected)
            if value.get("pending"):
                self.clock.now = prepared["plan"]["createdAt"] - 1
        self.store.commit = rollback_after_intent
        record = self.coordinator.step()
        self.assertEqual(record["lastOutcome"]["proof"], "local-pre-dispatch-gate")
        self.assertEqual(self.store.load()["dispatchClosedReason"], "clock-rollback")
        self.assertIsNone(self.store.load()["pending"])
        self.assertEqual(self.adapter.calls, [])
        self.clock.now = prepared["plan"]["createdAt"] + 1
        with self.assertRaisesRegex(Held, "backwards"):
            Coordinator(self.store, self.adapter, self.clock).step()
        self.assertEqual(self.adapter.calls, [])

    def test_transition_created_at_current_time_allows_stop(self):
        prepared = self.prepare()
        self.assertEqual(prepared["plan"]["createdAt"], self.clock())
        record = self.coordinator.step()
        self.assertEqual([op for op, _ in self.adapter.calls], ["stop"])
        self.assertEqual(record["pending"]["createdAt"], prepared["plan"]["createdAt"])

    def test_other_coordinator_cannot_clear_intent_while_sender_is_active(self):
        self.prepare()
        original = self.adapter.dispatch
        def dispatch(operation, key, plan, expected, contract):
            # At this exact point intent exists but effect is not sent yet.
            # A second worker must not reconcile apparent non-submission.
            competing = Coordinator(self.store, self.adapter, self.clock)
            with self.assertRaisesRegex(Held, "OS lock"):
                competing.step()
            return original(operation, key, plan, expected, contract)
        self.adapter.dispatch = dispatch
        self.coordinator.step()
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertEqual(self.adapter.reconciliations, [])

    def test_file_store_coordinator_guard_blocks_another_instance(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rollover-owner-", dir=SCRATCH) as directory:
            path = Path(directory) / "journal.json"
            first, second = FileStore(path), FileStore(path)
            with first.exclusive():
                with self.assertRaisesRegex(Held, "OS lock"):
                    with second.exclusive():
                        self.fail("concurrent coordinator entered")
            with second.exclusive():
                self.assertTrue(path.with_name(path.name + ".coordinator.lock").exists())

    def test_each_effect_then_process_crash_reconciles_without_duplicate(self):
        for operation, before, after in (("stop", "prepared", "stop-confirmed"),
                                        ("start", "stop-confirmed", "start-confirmed"),
                                        ("observe", "start-confirmed", "fresh-observe-confirmed")):
            with self.subTest(operation=operation):
                self.setUp()
                self.to_phase(before)
                self.adapter.mode[operation] = "crash-after-effect"
                with self.assertRaises(SimulatedCrash):
                    self.coordinator.step()
                pending = self.store.load()["pending"]
                count = len(self.adapter.calls)
                restored = Coordinator(self.store, self.adapter, self.clock)
                self.assertEqual(restored.step()["phase"], after)
                self.assertEqual(len(self.adapter.calls), count)
                self.assertEqual(self.adapter.reconciliations[-1][1], pending["key"])

    def test_each_effect_then_confirmation_commit_crash_reconciles_same_key(self):
        for operation, before, after in (("stop", "prepared", "stop-confirmed"),
                                        ("start", "stop-confirmed", "start-confirmed"),
                                        ("observe", "start-confirmed", "fresh-observe-confirmed")):
            with self.subTest(operation=operation):
                self.setUp()
                self.to_phase(before)
                self.coordinator.step()
                pending = self.store.load()["pending"]
                self.store.fail_phase = after
                with self.assertRaises(SimulatedCrash):
                    self.coordinator.step()
                count = len(self.adapter.calls)
                self.assertEqual(self.coordinator.step()["phase"], after)
                self.assertEqual(len(self.adapter.calls), count)
                self.assertEqual(self.adapter.reconciliations[-1][1], pending["key"])

    def test_timeout_after_effect_preserves_pending_until_reconciled(self):
        self.prepare()
        self.adapter.mode["stop"] = "timeout-after-effect"
        value = self.coordinator.step()
        self.assertEqual(value["lastOutcome"]["status"], "unknown")
        self.assertIsNotNone(value["pending"])
        self.assertEqual(self.coordinator.step()["phase"], "stop-confirmed")
        self.assertEqual(len(self.adapter.calls), 1)

    def test_unknown_inflight_and_failed_stop_never_repeat_from_running_task(self):
        for status in ("unknown", "in-flight", "failed"):
            with self.subTest(status=status):
                self.setUp()
                self.prepare()
                self.adapter.mode["stop"] = status
                self.coordinator.step()
                for _ in range(3):
                    record = self.coordinator.step()
                    self.assertEqual(record["lastOutcome"]["status"], status)
                    self.assertEqual(record["phase"], "prepared")
                self.assertTrue(self.adapter.current.task_running)
                self.assertEqual(len(self.adapter.calls), 1)

    def test_start_failure_does_not_restart_or_advance(self):
        self.to_phase("stop-confirmed")
        self.adapter.mode["start"] = "failed"
        self.coordinator.step()
        self.coordinator.step()
        self.coordinator.step()
        self.assertEqual(self.store.load()["phase"], "stop-confirmed")
        self.assertEqual([x[0] for x in self.adapter.calls], ["stop", "start"])

    def test_explicit_non_submission_allows_separate_revalidated_bounded_retry(self):
        self.prepare()
        self.adapter.mode["stop"] = "not-submitted"
        keys = []
        for _ in range(3):
            keys.append(self.coordinator.step()["pending"]["key"])
            self.assertIsNone(self.coordinator.step()["pending"])
        self.assertEqual(len(set(keys)), 3)
        with self.assertRaisesRegex(Held, "attempts exhausted"):
            self.coordinator.step()
        self.assertEqual(len(self.adapter.calls), 3)

    def test_non_submission_without_durable_proof_cannot_clear_intent(self):
        self.prepare()
        self.adapter.mode["stop"] = "unknown"
        key = self.coordinator.step()["pending"]["key"]
        self.adapter.outcomes[key] = Reconciliation("not-submitted", key)
        with self.assertRaisesRegex(Held, "durable proof"):
            self.coordinator.step()
        self.assertEqual(self.store.load()["pending"]["key"], key)

    def test_reconciliation_wrong_key_or_unproven_success_holds(self):
        for change in ({"operation_key": "b" * 64}, {"durable_proof": False}, {"request_id": "mission-" + "f" * 32}):
            with self.subTest(change=change):
                self.setUp()
                self.prepare()
                key = self.coordinator.step()["pending"]["key"]
                self.adapter.outcomes[key] = replace(self.adapter.outcomes[key], **change)
                with self.assertRaises(Held):
                    self.coordinator.step()
                self.assertEqual(self.store.load()["phase"], "prepared")

    def test_incomplete_termination_does_not_confirm_stop_or_start(self):
        self.prepare()
        key = self.coordinator.step()["pending"]["key"]
        outcome = self.adapter.outcomes[key]
        self.adapter.outcomes[key] = replace(outcome, snapshot=replace(outcome.snapshot, task_running=True))
        with self.assertRaisesRegex(Held, "termination"):
            self.coordinator.step()
        self.assertEqual(len(self.adapter.calls), 1)

    def test_prepare_rejects_wrong_busy_stale_and_unverified_state(self):
        variants = ({"authenticated": False}, {"process_alive": False}, {"task_running": False},
                    {"service_owns_pilot": False}, {"active_request_id": "pending"}, {"error": "fault"},
                    {"observed_at": self.clock() - 5001}, {"heartbeat_at": self.clock() - 5001},
                    {"menu_guard_verified": False}, {"output_reserve_verified": False},
                    {"no_pending_archive": False}, {"successor_unused": False},
                    {"session": "wrong-session"}, {"frame": 999})
        for change in variants:
            with self.subTest(change=change):
                with self.assertRaises(Held):
                    self.prepare(initial(self.clock, **change))
                self.assertIsNone(self.store.load())
                self.assertEqual(self.adapter.calls, [])

    def test_changed_pid_wts_uid_lifetime_or_nonce_binding_holds_before_dispatch(self):
        identities = (replace(IDENTITY, process_id=35000), replace(IDENTITY, windows_session_id=3),
                      replace(IDENTITY, uid="123456788"),
                      replace(IDENTITY, owner_lifetime_binding=digest(b"changed-process-lifetime")),
                      replace(IDENTITY, owner_lifetime_binding=digest(b"changed-instance-nonce")))
        for identity in identities:
            with self.subTest(identity=identity):
                self.setUp()
                self.prepare()
                self.adapter.current = replace(self.adapter.current, identity=identity)
                with self.assertRaisesRegex(Held, "changed"):
                    self.coordinator.step()
                self.assertEqual(self.adapter.calls, [])

    def test_wrong_identity_in_reconciled_success_never_advances(self):
        self.prepare()
        key = self.coordinator.step()["pending"]["key"]
        outcome = self.adapter.outcomes[key]
        self.adapter.outcomes[key] = replace(outcome, snapshot=replace(outcome.snapshot,
            identity=replace(IDENTITY, owner_lifetime_binding="b" * 64)))
        with self.assertRaises(Held):
            self.coordinator.step()
        self.assertEqual(self.store.load()["phase"], "prepared")

    def test_capacity_stop_and_observe_exact_boundaries(self):
        self.prepare(initial(self.clock, receipt_count=4092, receipt_bytes=33_423_360))
        self.to_phase("archive-eligible")
        self.assertEqual(self.adapter.current.receipt_count, 4094)
        for changes in ({"receipt_count": 4093}, {"receipt_bytes": 33_423_361}):
            with self.subTest(changes=changes):
                self.setUp()
                with self.assertRaisesRegex(Held, "reserve"):
                    self.prepare(initial(self.clock, **changes))
        for changes in ({"receipt_count": 4094}, {"receipt_bytes": 50_200_577}):
            with self.subTest(changes=changes):
                self.setUp()
                self.to_phase("stop-confirmed")
                self.adapter.current = replace(self.adapter.current, **changes)
                with self.assertRaisesRegex(Held, "reserve"):
                    self.coordinator.step()
                self.assertEqual(len(self.adapter.calls), 1)

    def test_expired_or_repeated_transition_never_dispatches(self):
        self.prepare()
        with self.assertRaisesRegex(Held, "already exists"):
            self.prepare()
        self.clock.now += 120_001
        self.adapter.current = replace(self.adapter.current, observed_at=self.clock())
        with self.assertRaisesRegex(Held, "expired"):
            self.coordinator.step()
        self.assertEqual(self.adapter.calls, [])

    def test_completed_effect_can_reconcile_after_expiry_but_no_next_effect(self):
        self.prepare()
        self.coordinator.step()
        self.clock.now += 120_001
        self.assertEqual(self.coordinator.step()["phase"], "stop-confirmed")
        with self.assertRaisesRegex(Held, "expired"):
            self.coordinator.step()
        self.assertEqual(len(self.adapter.calls), 1)

    def test_source_freshness_is_not_renewed_by_fresh_status(self):
        self.prepare()
        self.clock.now += 4001  # initial source was already 1100 ms old
        self.adapter.current = replace(self.adapter.current, observed_at=self.clock(), heartbeat_at=self.clock())
        with self.assertRaisesRegex(Held, "five seconds"):
            self.coordinator.step()
        self.assertEqual(self.adapter.calls, [])

    def test_changed_request_receipt_or_immutable_observation_holds(self):
        for name in ("request", "final_receipt", "observation", "immutable_observation"):
            with self.subTest(name=name):
                self.setUp()
                self.prepare()
                ev = self.adapter.current.evidence
                changed = getattr(ev, name) + b" "
                self.adapter.current = replace(self.adapter.current, evidence=replace(ev, **{name: changed}))
                with self.assertRaises(Held):
                    self.coordinator.step()
                self.assertEqual(self.adapter.calls, [])

    def test_wrong_inventory_uid_world_or_capture_stamp_holds(self):
        for mutation in ("uid", "world", "stamp", "food", "capacity"):
            with self.subTest(mutation=mutation):
                ev = initial(self.clock).evidence
                obs = json.loads(ev.observation)
                if mutation == "uid": obs["ocr"][2]["text"] = "UID: 999999999"
                if mutation == "world": obs["hud"]["world"] = True
                if mutation == "stamp": obs["hud"]["captureStamp"]["source"] = "renewed"
                if mutation == "food": obs["ocr"][0]["x"] = 1400
                if mutation == "capacity": obs["ocr"][1]["text"] = "Inventory capacity unknown"
                raw = encoded(obs)
                with self.assertRaises(Held):
                    self.prepare(initial(self.clock, evidence=replace(ev, observation=raw, immutable_observation=raw)))

    def test_wrong_start_session_consumption_or_suppression_holds(self):
        for changes in ({"session": OLD}, {"transition_id": "b" * 64},
                        {"suppressed_request_sha256": "b" * 64}, {"frame": 1}):
            with self.subTest(changes=changes):
                self.setUp()
                self.to_phase("stop-confirmed")
                key = self.coordinator.step()["pending"]["key"]
                outcome = self.adapter.outcomes[key]
                self.adapter.outcomes[key] = replace(outcome, snapshot=replace(outcome.snapshot, **changes))
                with self.assertRaises(Held):
                    self.coordinator.step()
                self.assertEqual(self.store.load()["phase"], "stop-confirmed")

    def test_successor_grammar_and_used_target_are_not_relaxed(self):
        for value in (OLD, "native-next-r4", "../escape", "Upper-next", "native-", "native-next/child"):
            with self.subTest(value=value):
                with self.assertRaises(Held):
                    self.coordinator.prepare(initial(self.clock), value, self.clock() + 120000)
        self.assertEqual(self.adapter.calls, [])

    def test_startup_contract_preserves_exact_stop_and_original_source(self):
        record = self.to_phase("stop-confirmed")
        contract = startup_contract(record)
        self.assertEqual(contract["stopEvidence"], record["proofs"]["stop"]["evidence"])
        self.assertEqual(contract["originalEvidence"], record["plan"]["originalEvidence"])
        self.assertNotIn("nonce", encoded(contract).decode().lower())
        self.assertEqual(contract["oldFrame"], record["proofs"]["stop"]["frame"])

    def test_status_collection_time_is_checked_after_inspection(self):
        self.prepare()
        self.adapter.inspect_delay = 100
        self.assertIsNotNone(self.coordinator.step()["pending"])

    def test_slow_stop_can_start_with_independent_continuity_without_renewing_source(self):
        self.prepare()
        self.coordinator.step()
        source_before = self.adapter.current.evidence.saved()
        self.clock.now += 7000  # completed stop/termination acknowledgement exceeded five seconds
        self.assertEqual(self.coordinator.step()["phase"], "stop-confirmed")
        self.coordinator.step()
        self.assertEqual([op for op, _ in self.adapter.calls], ["stop", "start"])
        pending = self.store.load()["pending"]
        self.assertEqual(pending["menuContinuity"]["inventory_sha256"], source_before["observation"]["sha256"])
        self.assertEqual(self.store.load()["proofs"]["stop"]["evidence"], source_before)
        self.assertEqual(self.coordinator.step()["phase"], "start-confirmed")
        self.to_phase("archive-eligible")

    def test_start_cannot_infer_continuity_from_idle_old_picture_or_missing_guard(self):
        self.to_phase("stop-confirmed")
        self.adapter.provide_continuity = False
        self.clock.now += 7000
        with self.assertRaisesRegex(Held, "continuity evidence is unavailable"):
            self.coordinator.step()
        self.assertEqual([op for op, _ in self.adapter.calls], ["stop"])

    def test_start_continuity_binds_identity_sources_ttl_and_menu_hold(self):
        variants = ({"identity": replace(IDENTITY, owner_lifetime_binding="c" * 64)},
                    {"inventory_sha256": "b" * 64}, {"stop_request_sha256": "b" * 64},
                    {"stop_receipt_sha256": "b" * 64}, {"transition_id": "b" * 64},
                    {"same_game_verified": False}, {"held_through_exit": False},
                    {"native_trigger_menu_hold": False}, {"startup_menu_hold": False},
                    {"source": "old-screenshot"}, {"verified_at": 0}, {"expires_at": 0},
                    {"expires_at": 999999999})
        for changes in variants:
            with self.subTest(changes=changes):
                self.setUp()
                self.to_phase("stop-confirmed")
                self.adapter.continuity_changes = changes
                with self.assertRaises(Held):
                    self.coordinator.step()
                self.assertEqual([op for op, _ in self.adapter.calls], ["stop"])

    def test_journal_latency_cannot_relax_original_source_limit(self):
        self.prepare()
        original_commit = self.store.commit
        def slow_commit(value, expected):
            original_commit(value, expected)
            if value.get("pending"):
                self.clock.now += 6000
        self.store.commit = slow_commit
        value = self.coordinator.step()
        self.assertEqual(value["lastOutcome"]["proof"], "local-pre-dispatch-gate")
        self.assertIsNone(value["pending"])
        self.assertEqual(self.adapter.calls, [])

    def test_stop_receipt_must_bind_dispatched_frame(self):
        self.prepare()
        key = self.coordinator.step()["pending"]["key"]
        outcome = self.adapter.outcomes[key]
        request = json.loads(outcome.snapshot.evidence.request)
        request["expectedFrameId"] -= 1
        changed = replace(outcome.snapshot.evidence, request=encoded(request))
        self.adapter.outcomes[key] = replace(outcome, snapshot=replace(outcome.snapshot, evidence=changed))
        with self.assertRaisesRegex(Held, "newly submitted"):
            self.coordinator.step()

    def test_observe_cannot_reuse_capture_before_its_real_request(self):
        self.to_phase("start-confirmed")
        key = self.coordinator.step()["pending"]["key"]
        outcome = self.adapter.outcomes[key]
        observation = json.loads(outcome.snapshot.evidence.observation)
        request = json.loads(outcome.snapshot.evidence.request)
        observation["hud"]["captureStamp"]["capturedAt"] = request["createdAt"] - 1
        raw = encoded(observation)
        changed = replace(outcome.snapshot.evidence, observation=raw, immutable_observation=raw)
        self.adapter.outcomes[key] = replace(outcome, snapshot=replace(outcome.snapshot, evidence=changed))
        with self.assertRaisesRegex(Held, "newly submitted"):
            self.coordinator.step()

    def test_final_receipt_cannot_precede_its_observation(self):
        value = initial(self.clock)
        receipt = json.loads(value.evidence.final_receipt)
        receipt["timestamp"] = self.clock() - 1500
        with self.assertRaisesRegex(Held, "predates"):
            self.prepare(replace(value, evidence=replace(value.evidence, final_receipt=encoded(receipt))))

    def test_file_store_roundtrip_integrity_revision_and_lock(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rollover-", dir=SCRATCH) as directory:
            path = Path(directory) / "journal.json"
            store = FileStore(path)
            adapter = FakeAdapter(self.clock, store)
            coordinator = Coordinator(store, adapter, self.clock)
            coordinator.prepare(adapter.current, NEW, self.clock() + 120000)
            coordinator.step()
            restored = Coordinator(FileStore(path), adapter, self.clock)
            self.assertEqual(restored.step()["phase"], "stop-confirmed")
            with self.assertRaisesRegex(Held, "revision"):
                store.commit({"revision": 1}, 0)
            lock = path.with_name(path.name + ".lock")
            with _journal_lock(lock):
                with self.assertRaisesRegex(Held, "OS lock"):
                    restored.step()
            wrapper = json.loads(path.read_bytes())
            wrapper["record"]["plan"]["oldFrame"] += 1
            path.write_bytes(encoded(wrapper))
            with self.assertRaisesRegex(Held, "integrity"):
                store.load()

    def test_real_fixture_process_mutex_and_crash_release_without_lock_deletion(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rollover-lock-", dir=SCRATCH) as directory:
            root = Path(directory).resolve()
            self.assertTrue(root.is_relative_to(SCRATCH.resolve()))
            path, ready = root / "journal.json", root / "ready.txt"
            lock = path.with_name(path.name + ".lock")
            store = FileStore(path)
            store.commit({"revision": 0, "preserved": "original evidence"}, None)
            process = subprocess.Popen([sys.executable, "-B", "-X", "utf8", str(Path(__file__).resolve()),
                                        "--hold-fixture-lock", str(lock), str(ready)],
                                       stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists(), "isolated fixture did not acquire its lock")
                with self.assertRaisesRegex(Held, "OS lock"):
                    store.commit({"revision": 1, "preserved": "original evidence"}, 0)
                self.assertEqual(store.load()["revision"], 0)
                # Windows venv python.exe can be a launcher. Crash the actual
                # lock-holding worker, not merely the launcher's Popen PID.
                process.communicate(input=b"crash\n", timeout=5)
                self.assertEqual(process.returncode, 23)
                self.assertTrue(lock.exists())
                store.commit({"revision": 1, "preserved": "original evidence"}, 0)
                self.assertEqual(store.load(), {"revision": 1, "preserved": "original evidence"})
            finally:
                if process.poll() is None:
                    process.terminate()
                process.communicate(timeout=5)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--hold-fixture-lock":
        lock, ready = Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
        if not all(path.is_relative_to(SCRATCH.resolve()) for path in (lock, ready)):
            raise SystemExit("Fixture paths must stay inside the designated scratch directory")
        with _journal_lock(lock):
            ready.write_text("locked", encoding="utf-8")
            if sys.stdin.readline().strip() == "crash":
                os._exit(23)  # Fixture hard exit: no Python finally/unlock runs.
    else:
        unittest.main(verbosity=2)
