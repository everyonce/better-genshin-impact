import json
import sys
import tempfile
import unittest
from pathlib import Path

from owner_adapter import OwnerProvider, ReadOnlyCollector, native_owner
from relay_runtime import ControllerRelay, consume
from relay_prepared import PreparedRelayJournal, prepared_record, recovery_response
from relay_reliability import Held, binding
from test_owner_adapter import heartbeat, status


OWNER = native_owner(status())
OUTER = {"id": "r-adapter-test-0001", "kind": "questStep", "step": "safeStep", "frame": 10}
STEPS = {"safeStep"}


class FakeCommand:
    def __init__(self):
        self.effects = 0
        self.fail_after_effect = False

    def main(self, *, before_request_write):
        request = {"id": "mission-" + "1" * 32, "session": OWNER.session,
                   "mission": sys.argv[1], "createdAt": 100000, "expectedFrameId": 10}
        if request["mission"] == "questStep": request["step"] = "safeStep"
        ack = before_request_write(json.dumps(request).encode(), heartbeat())
        ack["revalidate"](heartbeat())
        self.effects += 1
        if self.fail_after_effect: raise RuntimeError("synthetic lost reply")
        print(json.dumps({"status": "completed", "session": OWNER.session, "frameId": 11,
                          "submittedId": request["id"], "terminalId": request["id"],
                          "controllerQuiescent": True}))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.here = Path(__file__).resolve().parent
        self.temp = tempfile.TemporaryDirectory(prefix="adapter-test-", dir=self.here)
        self.root = Path(self.temp.name).resolve()
        self.assertEqual(self.root.parent, self.here)
        for name in ["journal", "legacy", "native"]: (self.root / name).mkdir()

    def tearDown(self):
        self.assertEqual(Path(self.temp.name).resolve().parent, self.here)
        self.temp.cleanup()


class DriverTests(Fixture):
    def setUp(self):
        super().setUp()
        self.command = FakeCommand()
        self.journal = PreparedRelayJournal(self.root / "journal", STEPS,
                                            owner_probe=lambda **_: OWNER,
                                            legacy_responses=self.root / "legacy",
                                            clock_ms=lambda: 100100)
        self.relay = ControllerRelay(self.command, "synthetic.py", self.journal, OWNER, STEPS)

    def run_messages(self, *messages):
        output = []
        self.relay.loop([json.dumps(message) for message in messages], output.append)
        return output

    def test_duplicate_line_is_cached_without_second_dispatch(self):
        output = self.run_messages(OUTER, OUTER)
        self.assertEqual(self.command.effects, 1)
        self.assertTrue(output[-1]["replayed"])
        result = consume(self.root / "journal", OUTER, OWNER, STEPS)
        self.assertTrue(result["boundResult"])
        self.assertTrue(result["historicalRead"])
        self.assertTrue(result["replayed"])
        self.assertEqual(result["boundRequest"], OUTER)
        self.assertFalse((self.root / "journal" / "active.json").exists())

    def test_unknown_outcome_holds_new_request_and_replay(self):
        self.command.fail_after_effect = True
        output = self.run_messages(OUTER, {**OUTER, "id": "r-adapter-test-0002"}, OUTER)
        self.assertEqual(self.command.effects, 1)
        self.assertEqual(output[-1]["state"], "unknown")
        self.assertTrue((self.root / "journal" / "active.json").exists())
        with self.assertRaises(Held): consume(self.root / "journal", OUTER, OWNER, STEPS)

    def test_close_does_not_dispatch_or_clear_unknown_evidence(self):
        self.command.fail_after_effect = True
        self.run_messages(OUTER)
        output = self.run_messages({"id": "r-close-test-0001", "kind": "close"}, OUTER)
        self.assertTrue(output[-1]["closed"])
        self.assertEqual(self.command.effects, 1)
        self.assertTrue((self.root / "journal" / "active.json").exists())

    def test_unlisted_request_does_not_reach_cli(self):
        output = self.run_messages({**OUTER, "step": "unreviewed"})
        self.assertEqual(output[-1]["state"], "held")
        self.assertEqual(self.command.effects, 0)

    def test_consumer_rejects_same_id_different_request_or_owner(self):
        self.run_messages(OUTER)
        with self.assertRaises(Held):
            consume(self.root / "journal", {**OUTER, "frame": 11}, OWNER, STEPS)
        foreign = native_owner({**status(), "instanceNonce": "0" * 32})
        with self.assertRaises(Held): consume(self.root / "journal", OUTER, foreign, STEPS)

    def test_consumer_rejects_changed_inner_claim(self):
        self.run_messages(OUTER)
        claim = self.root / "journal" / ("inner-mission-" + "1" * 32 + ".claim.json")
        claim.write_text('{"binding":"changed"}', encoding="utf-8")
        with self.assertRaises(Held): consume(self.root / "journal", OUTER, OWNER, STEPS)

    def test_read_control_has_no_dispatch_and_recovery_stays_disabled(self):
        self.run_messages(OUTER)
        output = self.run_messages({"control": "readResult", "request": OUTER})
        self.assertEqual(output[-1]["state"], "settled")
        self.assertEqual(self.command.effects, 1)
        output = self.run_messages({"control": "reconcile", "request": OUTER})
        self.assertEqual(output[-1]["reason"], "read-only-collector-unavailable")
        self.assertEqual(self.command.effects, 1)


class CollectorTests(Fixture):
    def setUp(self):
        super().setUp()
        self.native = self.root / "native"
        self.now = 100100
        self.live = {**status(), "frameId": 11, "heartbeatAtUnixMs": 100100}
        self.calls = 0
        def query(*_):
            self.calls += 1
            return dict(self.live)
        self.provider = OwnerProvider(query, OWNER, self.live["appDirectory"], lambda: self.now)
        self.inner = {"id": "mission-" + "1" * 32, "session": OWNER.session,
                      "mission": "questStep", "step": "safeStep", "createdAt": 100000, "expectedFrameId": 10}
        self.key = binding(OUTER, OWNER, STEPS)
        self.prepared = prepared_record(json.dumps(self.inner).encode(), self.key)
        files = {"request.json": self.inner,
                 "receipt.json": {"id": self.inner["id"], "session": OWNER.session,
                                  "mission": "questStep", "status": "completed", "frameId": 11, "timestamp": 100050},
                 "frame-11.json": {"session": OWNER.session, "frameId": 11, "timestamp": 100025},
                 "observation.json": {"session": OWNER.session, "frameId": 11, "timestamp": 100025},
                 "controller-status.json": {**heartbeat(), "frameId": 11, "heartbeatAt": 100100}}
        for name, value in files.items(): (self.native / name).write_text(json.dumps(value), encoding="utf-8")
        def advance(seconds): self.now += round(seconds * 1000)
        self.collector = ReadOnlyCollector(self.native, self.provider,
                                           lambda root, session, identity: root / "receipt.json",
                                           lambda root, session, frame: root / f"frame-{frame}.json",
                                           clock_ms=lambda: self.now, monotonic_ms=lambda: self.now,
                                           sleep=advance)

    def test_two_samples_qualify_without_writing_or_submitting(self):
        before = {p.name: p.read_bytes() for p in self.native.iterdir()}
        proof = self.collector(self.prepared)
        response = recovery_response(self.key, self.prepared, proof, self.now)
        self.assertEqual(response["result"]["status"], "completed")
        self.assertTrue(response["result"]["historicalOutcome"])
        self.assertEqual(self.calls, 4)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.native.iterdir()})

    def test_post_read_native_busy_frame_and_active_request_are_rejected(self):
        for field, value in [("scriptState", "running"), ("frameId", 12),
                             ("activeRequestId", "mission-" + "2" * 32)]:
            with self.subTest(field=field):
                self.live = {**status(), "frameId": 11, "heartbeatAtUnixMs": 100100, field: value}
                with self.assertRaises(Held): self.collector(self.prepared)

    def test_missing_immutable_observation_never_proves_completion(self):
        (self.native / "frame-11.json").unlink()
        with self.assertRaises(FileNotFoundError): self.collector(self.prepared)


if __name__ == "__main__": unittest.main()
