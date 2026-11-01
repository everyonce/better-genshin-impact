"""Exercise the real passive probe with inert native files and an input-free transport."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import combat_trial as trial
import combat_pause_probe as probe
from combat_pause_probe import probe_inventory
from combat_pause_proof import CORE_REVISIONS, revision
import test_combat_trial as fixtures


class NativeFiles:
    """Implement only owned pilot start/stop and one file-backed native observation."""
    def __init__(self, fixture, *, mutation=None):
        """Attach the original fixture owner to a uniquely identified, passive script session."""
        self.fixture, self.lifecycle, self.mutation = fixture, fixture.lifecycle, mutation
        self.session, self.commands, self.requests = 'passive-fixture', [], []
        self.app = fixture.root / 'artifacts/release/BetterGI-English-win-x64'
        self.pilot = self.app / 'User/JsScript/ActOnePilot'
        (self.app / 'User/ScriptGroup').mkdir(parents=True)
        cleanup = json.loads((fixture.pause_folder / 'owner-after-stop.json').read_bytes())
        self.lifecycle.root.update(cleanup['root'])
        self.lifecycle.child.update(cleanup['child'], pilotState='idle')
        self.old_discover = self.lifecycle.discover
        self.lifecycle.discover = self.discover
        self.lifecycle.transport = SimpleNamespace(exchange=self.exchange)
        self.pending_start = False
        self.start_polls = 0
        self.monotonic_offset = 0

    def publish_started(self, process_id, session_id):
        """Finish only this fixture's acknowledged startup and emit its native heartbeat."""
        self.lifecycle.child.update(serviceOwnsPilot=True, taskRunning=True, pilotState='idle', scriptSession=self.session)
        self.fixture.clock_offset += 500_000_000
        now = trial.time.time_ns() // 1_000_000
        stamp = now - (2000 if self.mutation == 'stale' else 20)
        self.frame(1, stamp)
        heartbeat = dict(version=1, session=self.session, processId=process_id, windowsSessionId=session_id,
            remoteDesktop=True, state='idle', heartbeatAt=now, frameId=1, activeRequestId=None, error=None)
        if self.mutation == 'startup-old-session':
            heartbeat['session'] = self.lifecycle.child['scriptSession'] = self.prior_session
        elif self.mutation == 'startup-replaced-session':
            heartbeat['session'] = self.lifecycle.child['scriptSession'] = 'foreign-start'
        elif self.mutation == 'startup-stale-heartbeat':
            heartbeat['heartbeatAt'] -= 2000
        elif self.mutation == 'startup-active-request':
            heartbeat['activeRequestId'] = 'foreign-request'
        elif self.mutation == 'startup-foreign-owner':
            self.lifecycle.child['instanceNonce'] = 'foreign-owner'
        elif self.mutation == 'startup-group-change':
            path = self.app / 'User/ScriptGroup/ActOneRun.json'
            value = json.loads(path.read_bytes())
            value['config']['pathingConfig']['autoRunEnabled'] = True
            path.write_bytes(trial.canonical(value))
        elif self.mutation == 'startup-source-change':
            (self.pilot / 'main.js').write_bytes(b'changed during startup')
        elif self.mutation == 'startup-request-file':
            (self.pilot / 'request.json').write_bytes(trial.canonical(dict(id='foreign')))
        self.lifecycle.child.update(frameId=1, heartbeatAtUnixMs=heartbeat['heartbeatAt'], heartbeatFresh=True)
        (self.pilot / 'controller-status.json').write_bytes(trial.canonical(heartbeat))

    def frame(self, index, stamp):
        """Publish an exact original full PNG and its matching native JSON."""
        value = json.loads((self.fixture.pause_folder / 'after.json').read_bytes())
        value.update(session=self.session, frameId=index, timestamp=stamp,
            screenshotPath=f'observations/{self.session}/frame-{index:04d}.png')
        if self.mutation == 'world':
            value['hud']['world'] = True
        source = self.pilot / value['screenshotPath']
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((self.fixture.pause_folder / 'after.png').read_bytes())
        source.with_suffix('.json').write_bytes(trial.canonical(value))
        (self.pilot / 'observation.json').write_bytes(trial.canonical(value))
        return value

    def exchange(self, request, process_id, session_id):
        """Refuse every command except this fixture's bounded pilot lifecycle."""
        name = request['command']
        self.commands.append(name)
        if name == 'startPilot':
            if self.mutation and self.mutation.startswith('startup-'):
                self.prior_session = self.lifecycle.child['scriptSession']
                self.pending_start = True
                self.lifecycle.child.update(serviceOwnsPilot=True, taskRunning=True, pilotState='starting')
                if self.mutation == 'startup-replaced-session':
                    self.lifecycle.child['scriptSession'] = self.session
                (self.fixture.folder / 'STOP').write_text('stop while native startup is pending')
                return copy.deepcopy(self.lifecycle.child)
            self.lifecycle.child.update(serviceOwnsPilot=True, taskRunning=True, pilotState='idle', scriptSession=self.session)
            if self.mutation == 'unknown-start':
                raise RuntimeError('lost start acknowledgement')
            self.publish_started(process_id, session_id)
        elif name == 'stopPilot':
            self.lifecycle.child.update(serviceOwnsPilot=False, taskRunning=False, pilotState='stopped')
        else:
            raise AssertionError('Unexpected native command: ' + name)
        return copy.deepcopy(self.lifecycle.child)

    def discover(self):
        """Turn the one observe request into a retained native receipt without executing JS or input."""
        if self.pending_start:
            self.start_polls += 1
            if self.mutation == 'startup-timeout':
                self.monotonic_offset += 1
            elif self.start_polls >= 3:
                self.pending_start = False
                self.publish_started(self.lifecycle.child['processId'], self.lifecycle.child['windowsSessionId'])
        request_path = self.pilot / 'request.json'
        if request_path.exists() and not self.requests and not (self.mutation or '').startswith('startup-'):
            request = json.loads(request_path.read_bytes())
            self.requests.append(request)
            self.fixture.clock_offset += 100_000_000
            after = self.frame(2, trial.time.time_ns() // 1_000_000 - 20)
            events = [dict(type='controllerRevision', startedAt=request['createdAt'] + 1,
                files={name: revision((self.pilot / name).read_bytes()) for name in CORE_REVISIONS})]
            if self.mutation == 'input':
                events.append(dict(type='key', key='VK_B', durationMs=60))
            if self.mutation == 'owner':
                self.lifecycle.child['instanceNonce'] = 'different'
            if self.mutation in ('group-change', 'group-delete'):
                group_path = self.app / 'User/ScriptGroup/ActOneRun.json'
                if self.mutation == 'group-delete':
                    group_path.unlink()
                else:
                    group = json.loads(group_path.read_bytes())
                    group['config']['pathingConfig']['autoRunEnabled'] = True
                    group_path.write_bytes(trial.canonical(group))
            receipt = dict(id=request['id'], session=self.session, mission='observe', status='completed',
                frameId=2, timestamp=after['timestamp'] + 1, details=dict(inputEvents=events))
            destination = self.pilot / 'receipts' / self.session / (request['id'] + '.json')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(trial.canonical(receipt))
        return self.old_discover()


class CombatPauseProbeTests(unittest.TestCase):
    """The actual probe must remain passive and preserve failures without replay."""
    def fixture(self, mutation=None):
        """Create an isolated inert worker and one native-file adapter."""
        fixture = fixtures.CombatPreparedTrialTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.begin()
        return fixture, NativeFiles(fixture, mutation=mutation)

    def run_probe(self, fixture):
        """Retire after successful prewarm so no combat arm or native listener is requested."""
        return fixture.worker(lambda ready: trial.request_stop(fixture.folder, fixture.preparation, 'testStop'),
                              pause_probe=probe_inventory)

    def test_real_probe_loop_one_observe_no_keys_and_released_owner(self):
        """Fresh original pixels, revision ledger and owned cleanup qualify exactly one prewarm."""
        fixture, native = self.fixture()
        self.assertEqual(self.run_probe(fixture), 1)
        report = fixture.report()
        self.assertEqual((fixture.loads, fixture.lifecycle.starts), (1, 0), report)
        self.assertEqual(native.commands, ['startPilot', 'stopPilot'])
        self.assertEqual([row['mission'] for row in native.requests], ['observe'])
        self.assertTrue(report['inventoryProbeResult']['inventoryVerified'])
        self.assertTrue(report['cleanupVerified'])
        self.assertFalse((native.app / 'User/ScriptGroup/ActOneRun.json').exists())
        self.assertFalse((native.pilot / 'request.json').exists())

    def test_wrong_menu_stale_source_and_input_receipt_never_load(self):
        """Each invalid scene/evidence condition stops once and retires only the owned script."""
        for mutation in ('world', 'stale', 'input'):
            with self.subTest(mutation=mutation):
                fixture, native = self.fixture(mutation)
                self.assertEqual(self.run_probe(fixture), 1)
                self.assertEqual((fixture.loads, fixture.lifecycle.starts), (0, 0))
                self.assertEqual(native.commands, ['startPilot', 'stopPilot'])
                self.assertLessEqual(len(native.requests), 1)
                self.assertTrue((fixture.folder / 'loading-pause-probe/result.json').exists())

    def test_unknown_start_never_stops_or_removes_a_foreign_pilot(self):
        """A missing exact script identity preserves unresolved cleanup and cannot trigger retry."""
        fixture, native = self.fixture('unknown-start')
        with patch.object(trial, 'await_idle', side_effect=RuntimeError('unresolved owned start')):
            self.assertEqual(self.run_probe(fixture), 1)
        self.assertEqual(native.commands, ['startPilot'])
        self.assertEqual((fixture.loads, fixture.lifecycle.starts), (0, 0))
        self.assertEqual(fixture.report()['status'], 'unresolved')
        self.assertTrue((native.app / 'User/ScriptGroup/ActOneRun.json').exists())

    def test_owner_change_never_receives_cleanup_or_load_authority(self):
        """The old script cannot stop a replacement instance even after its observe receipt arrived."""
        fixture, native = self.fixture('owner')
        with patch.object(trial, 'await_idle', side_effect=RuntimeError('owner changed')):
            self.assertEqual(self.run_probe(fixture), 1)
        self.assertEqual(native.commands, ['startPilot'])
        self.assertEqual((fixture.loads, fixture.lifecycle.starts), (0, 0))
        self.assertEqual(fixture.report()['status'], 'unresolved')

    def test_changed_or_deleted_group_still_stops_the_confirmed_owned_session(self):
        """An integrity failure survives cleanup without preventing exact-session retirement."""
        for mutation in ('group-change', 'group-delete'):
            with self.subTest(mutation=mutation):
                fixture, native = self.fixture(mutation)
                self.assertEqual(self.run_probe(fixture), 1)
                self.assertEqual(native.commands, ['startPilot', 'stopPilot'])
                self.assertEqual((fixture.loads, fixture.lifecycle.starts), (0, 0))
                self.assertFalse(native.lifecycle.child['serviceOwnsPilot'])
                report = fixture.report()['inventoryProbeResult']
                self.assertTrue(report['ownerIdleMinimizedAfter'])
                self.assertIn('error', report)
                self.assertIn('cleanupError', report)

    def test_stop_control_or_deadline_during_discovery_prevents_any_start(self):
        """A blocking owner query cannot turn an expired observation into launch authority."""
        for mutation in ('stop', 'control', 'deadline'):
            with self.subTest(mutation=mutation):
                fixture, native = self.fixture()
                clock, offset = probe.time.monotonic, [0]
                def discover():
                    """Return the original idle owner only after a concurrent terminal change."""
                    value = native.discover()
                    if (native.app / 'User/ScriptGroup/ActOneRun.json').exists() and not native.commands:
                        if mutation == 'stop':
                            (fixture.folder / 'STOP').write_text('operator stop')
                        elif mutation == 'control':
                            trial.runtime.atomic_json(fixture.folder / 'patrol.json.control.json',
                                dict(version=1, runId=fixture.preparation['runId'], command='pause'))
                        else:
                            offset[0] = 21
                    return value
                with patch.object(native.lifecycle, 'discover', side_effect=discover), \
                     patch.object(probe.time, 'monotonic', side_effect=lambda: clock() + offset[0]):
                    self.assertEqual(self.run_probe(fixture), 1)
                self.assertEqual(native.commands, [])
                self.assertEqual((fixture.loads, fixture.lifecycle.starts), (0, 0))
                result = fixture.report()['inventoryProbeResult']
                self.assertFalse(result['pilotStartAttempted'])
                self.assertEqual(result['pilotStartOutcome'], 'notAttempted')
                self.assertTrue(result['ownerIdleMinimizedAfter'])

    def test_starting_cancellation_learns_fresh_session_only_to_retire_it(self):
        """One acknowledged idle-to-start transition can drain after STOP without observing or loading."""
        fixture, native = self.fixture('startup-stop')
        self.assertEqual(self.run_probe(fixture), 1)
        self.assertEqual(native.commands, ['startPilot', 'stopPilot'])
        self.assertEqual(native.requests, [])
        self.assertEqual((fixture.loads, fixture.lifecycle.starts), (0, 0))
        report = fixture.report()
        self.assertEqual(report['status'], 'failed')
        self.assertTrue(report['cleanupVerified'])
        self.assertNotIn('inventoryProbeCleanupError', report)
        result = report['inventoryProbeResult']
        self.assertEqual(result['error'], 'seriesOperatorStop')
        self.assertEqual(result['confirmationPhase'], 'cleanupOnly')
        self.assertTrue(result['startupCleanup']['confirmed'])
        self.assertFalse(result['startupCleanup']['atomicStartCorrelation'])
        self.assertFalse(result['inventoryVerified'])
        self.assertTrue(result['temporaryGroupRemoved'])
        self.assertNotEqual(result['scriptSession'], result['startEvidence']['priorSession'])
        self.assertEqual(result['startEvidence']['ownerBefore']['child']['serviceOwnsPilot'], False)

    def test_startup_cleanup_refuses_foreign_replaced_or_unqualified_identity(self):
        """No stale heartbeat, request, ownership replacement or changed source can authorize stop."""
        cases = ('old-session', 'replaced-session', 'stale-heartbeat', 'active-request',
                 'foreign-owner', 'group-change', 'source-change', 'request-file')
        for value in cases:
            with self.subTest(mutation=value):
                fixture, native = self.fixture('startup-' + value)
                with patch.object(trial, 'await_idle', side_effect=RuntimeError('unresolved startup')):
                    self.assertEqual(self.run_probe(fixture), 1)
                self.assertEqual(native.commands, ['startPilot'])
                self.assertEqual((fixture.loads, fixture.lifecycle.starts), (0, 0))
                self.assertEqual(fixture.report()['status'], 'unresolved')
                self.assertTrue((native.app / 'User/ScriptGroup/ActOneRun.json').exists())

    def test_startup_cleanup_poll_is_bounded_and_never_restarts(self):
        """An acknowledged start that never identifies itself remains unresolved after the cleanup bound."""
        fixture, native = self.fixture('startup-timeout')
        original = probe.time.monotonic
        with patch.object(probe.time, 'monotonic', side_effect=lambda: original() + native.monotonic_offset), \
             patch.object(trial, 'await_idle', side_effect=RuntimeError('unresolved startup')):
            self.assertEqual(self.run_probe(fixture), 1)
        self.assertEqual(native.commands, ['startPilot'])
        result = fixture.report()['inventoryProbeResult']
        self.assertIn('timed out', result['cleanupError'])
        self.assertLessEqual(result['startupCleanup']['polls'], 4)
        self.assertFalse(result['startupCleanup']['confirmed'])
        self.assertEqual(fixture.loads, 0)

    def test_cleanup_heartbeat_publication_race_never_grants_work_authority(self):
        """CRT sharing or partial JSON may settle only into a fresh cleanup-only identity."""
        for mode in ('sharing', 'partial', 'missing'):
            with self.subTest(mode=mode):
                fixture, native = self.fixture('startup-stop')
                original, reads = trial.read_bytes, []
                def reading(path, *args, **kwargs):
                    """Model a temporary status-file publication race before its valid final bytes."""
                    if Path(path).name == 'controller-status.json':
                        reads.append(1)
                        if len(reads) == 1:
                            if mode == 'sharing':
                                raise PermissionError(13, 'Permission denied', str(path))
                            if mode == 'missing':
                                raise FileNotFoundError(str(path))
                            return b'{'
                    return original(path, *args, **kwargs)
                with patch.object(trial, 'read_bytes', side_effect=reading):
                    self.assertEqual(self.run_probe(fixture), 1)
                self.assertEqual(native.commands, ['startPilot', 'stopPilot'])
                self.assertEqual((fixture.loads, native.requests), (0, []))
                self.assertEqual(len(reads), 2)
                result = fixture.report()['inventoryProbeResult']
                self.assertTrue(result['startupCleanup']['confirmed'])
                self.assertFalse(result['inventoryVerified'])

    def test_unreadable_or_malformed_heartbeat_expires_without_adoption(self):
        """A permanently unreadable or malformed heartbeat leaves startup unresolved at three seconds."""
        for mode in ('sharing', 'partial'):
            with self.subTest(mode=mode):
                fixture, native = self.fixture('startup-stop')
                original, clock = trial.read_bytes, probe.time.monotonic
                offset, reads = [0], []
                def reading(path, *args, **kwargs):
                    """Move the synthetic cleanup clock while preserving every rejected status byte."""
                    if Path(path).name == 'controller-status.json':
                        reads.append(1)
                        offset[0] += 1
                        if mode == 'sharing':
                            raise PermissionError(13, 'Permission denied', str(path))
                        return b'{'
                    return original(path, *args, **kwargs)
                with patch.object(trial, 'read_bytes', side_effect=reading), \
                     patch.object(probe.time, 'monotonic', side_effect=lambda: clock() + offset[0]), \
                     patch.object(trial, 'await_idle', side_effect=RuntimeError('unresolved startup')):
                    self.assertEqual(self.run_probe(fixture), 1)
                self.assertEqual(native.commands, ['startPilot'])
                self.assertEqual(fixture.loads, 0)
                self.assertLessEqual(len(reads), 3)
                result = fixture.report()['inventoryProbeResult']
                self.assertFalse(result['startupCleanup']['confirmed'])
                self.assertIn('timed out', result['cleanupError'])


if __name__ == '__main__':
    unittest.main()
