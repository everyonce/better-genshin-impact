import copy
import unittest
from unittest.mock import Mock

from owner_adapter import OwnerProvider, native_owner, normalized_app_directory
from relay_reliability import Held


def status():
    return {"processId": 1234, "windowsSessionId": 2, "scriptSession": "sample-one-r3",
            "appDirectory": "D:\\Games\\BetterGI\\", "instanceType": "ChildSession",
            "instanceNonce": "00000000000000000000000000000001", "remoteDesktop": True,
            "serviceOwnsPilot": True, "heartbeatFresh": True, "heartbeatAtUnixMs": 100000,
            "scriptState": "idle", "pilotState": "idle", "frameId": 10}


def heartbeat():
    return {"version": 1, "session": "sample-one-r3", "processId": 1234,
            "windowsSessionId": 2, "remoteDesktop": True, "heartbeatAt": 100000,
            "state": "idle", "frameId": 10, "activeRequestId": None}


class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.live = status()
        self.query = Mock(side_effect=lambda *_: copy.deepcopy(self.live))
        self.expected = native_owner(self.live)
        self.provider = OwnerProvider(self.query, self.expected, self.live["appDirectory"], lambda: 100100)

    def test_powershell_v1_cross_language_fixture(self):
        self.assertEqual(self.expected.owner_lifetime_binding,
                         "cc886fe1124019dcbc539135aa0284f2493d6af3080e193eeaecb8f6724224b9")

    def test_every_call_queries_authenticated_provider(self):
        self.assertEqual(self.provider(), self.expected)
        self.assertEqual(self.provider(current_admission=heartbeat()), self.expected)
        self.assertEqual(self.query.call_count, 2)
        self.query.assert_called_with(1234, 2)

    def test_changed_nonce_rejected(self):
        self.live["instanceNonce"] = "0" * 32
        with self.assertRaises(Held): self.provider()

    def test_identity_reads_allow_advanced_frame(self):
        self.live["frameId"] = 11
        self.assertEqual(self.provider(), self.expected)
        with self.assertRaises(Held): self.provider(current_admission=heartbeat())

    def test_busy_native_rejected_at_submission(self):
        for field, value in [("scriptState", "running"), ("pilotState", "running"),
                             ("activeRequestId", "mission-" + "2" * 32)]:
            with self.subTest(field=field):
                self.live = {**status(), field: value}
                with self.assertRaises(Held): self.provider(current_admission=heartbeat())

    def test_busy_file_heartbeat_rejected(self):
        with self.assertRaises(Held): self.provider(current_admission={**heartbeat(), "state": "running"})

    def test_stale_future_or_unowned_native_rejected(self):
        for field, value in [("heartbeatAtUnixMs", 94000), ("heartbeatAtUnixMs", 100200),
                             ("heartbeatFresh", False), ("serviceOwnsPilot", False)]:
            with self.subTest(field=field, value=value):
                self.live = {**status(), field: value}
                with self.assertRaises(Held): self.provider()

    def test_foreign_native_identity_rejected(self):
        for field, value in [("processId", 1235), ("windowsSessionId", 3),
                             ("scriptSession", "sample-two-r3"), ("appDirectory", "D:\\Other"),
                             ("remoteDesktop", False), ("instanceType", "Root")]:
            with self.subTest(field=field):
                self.live = {**status(), field: value}
                with self.assertRaises(Held): self.provider()

    def test_unavailable_status_does_not_expose_exception(self):
        self.query.side_effect = RuntimeError("private data")
        with self.assertRaisesRegex(Held, "^authenticated-native-status-unavailable$"):
            self.provider()

    def test_invalid_and_ambiguous_paths_rejected(self):
        for path in ["relative", "D:relative", "\\\\server\\share", "D:\\bad.\\folder", "D:\\bad ", "D:\\unicode-é"]:
            with self.subTest(path=path), self.assertRaises(Held): normalized_app_directory(path)

    def test_path_normalization(self):
        self.assertEqual(normalized_app_directory("D:/Games/Child/../BetterGI/"), "d:\\games\\bettergi")


if __name__ == "__main__":
    unittest.main()
