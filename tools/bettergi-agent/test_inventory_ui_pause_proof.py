"""Inert replay of explicit UI-only transitions; no live/native/controller imports are executed."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPOSITORY = Path(os.environ.get('BETTERGI_REPOSITORY_ROOT', Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(REPOSITORY / 'tools/bettergi-agent'))
from test_combat_trial import OWNER, ui_transition_fixture, trial

spec = importlib.util.spec_from_file_location('staged_inventory_ui_proof', Path(__file__).with_name('combat_pause_proof.py'))
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


def encoded(value):
    """Preserve exact JSON joins while exercising a semantic mutation."""
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def row(text, x, y, width=80, height=24):
    """Construct one bounded inert OCR row."""
    return dict(text=text, x=x, y=y, width=width, height=height)


def world_rows():
    """Use independent ground, party and original-account UI bands."""
    return [row('Amber', 1680, 350), row('Kaeya', 1680, 450), row('E', 1690, 1020, 20, 25),
            row('Q', 1800, 1020, 20, 25), row('UID: 693306810', 1680, 1050, 180, 25)]


def add_mode(observation):
    """Declare omission and qualify a synthetic world only from its own fields."""
    observation['map'] = None
    observation['uiObservation'] = dict(version=1, kind='inventory-ui-only-v1', mapOmitted=True,
        orientationOmitted=True, observationStartedAtUnixMs=observation['timestamp'] - 1)
    observation.setdefault('timings', {})['mapDiagnostic'] = {
        'reason': 'Inventory UI-only v1: map and orientation deliberately omitted', 'mode': 'inventory-ui-only-v1'}
    hud = observation['hud']
    hud.update(loading=False, unknownHud=False, groundControls=hud['world'])
    if hud['world']:
        hud.update(health=dict(current=2211, max=4015), healthOcr=['2211/4015'],
                   healthDiagnostic=dict(decision='primary-scaled-readable'), tutorialStep=None, characterAcquired=None)
        observation['ocr'] = world_rows()
    return observation


class InventoryUiProofTests(unittest.TestCase):
    """Proof version two is opt-in; changed source/owner/image joins stay authoritative."""
    def setUp(self):
        """Allocate only a disposable test tree inside the explicitly selected TEMP."""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.live = self.root / 'artifacts/live'
        self.live.mkdir(parents=True)
        self.harness = SimpleNamespace(root=self.root, live=self.live)
        self.case_number = 0

    def fixture(self, operation):
        """Upgrade a legacy inert fixture into a fully joined UI-only transition."""
        self.case_number += 1
        folder = ui_transition_fixture(self.harness, operation, suffix='-ui-' + str(self.case_number))
        report = json.loads((folder / 'result.json').read_bytes())
        owner = json.loads((folder / 'owner-after-stop.json').read_bytes())
        pilot = Path(owner['child']['appDirectory']) / 'User/JsScript/ActOnePilot'
        plan = json.loads((folder / 'plan.json').read_bytes())
        plan['inventoryUiOnlyV1'] = True
        group = json.loads((folder / 'group.json').read_bytes())
        group['projects'][0]['jsScriptSettingsObject']['inventoryUiOnlyV1'] = True
        for name in ('group.json', 'group-after-stop.json'):
            (folder / name).write_bytes(encoded(group))
        plan['groupSha256'] = hashlib.sha256(encoded(group)).hexdigest()
        (folder / 'plan.json').write_bytes(encoded(plan))
        for retained in report['observations']:
            observation = add_mode(json.loads((folder / (retained['label'] + '.json')).read_bytes()))
            (folder / (retained['label'] + '.json')).write_bytes(encoded(observation))
            retained['jsonSha256'] = hashlib.sha256(encoded(observation)).hexdigest()
            (pilot / observation['screenshotPath']).with_suffix('.json').write_bytes(encoded(observation))
        before = json.loads((folder / 'before.json').read_bytes())
        frame = copy.deepcopy(before)
        frame.update(frameId=2, timestamp=before['timestamp'] + 15,
                     screenshotPath='observations/' + report['scriptSession'] + '/frame-0002.png')
        add_mode(frame)
        (pilot / frame['screenshotPath']).write_bytes((folder / 'before.png').read_bytes())
        (pilot / frame['screenshotPath']).with_suffix('.json').write_bytes(encoded(frame))
        if operation == 'pause':
            receipt = report['requests'][0]['receipt']
            receipt['details']['inputEvents'][-1]['frameId'] = 2
            receipt['details']['result']['frameId'] = 3
            (folder / (receipt['id'] + '.receipt.json')).write_bytes(encoded(receipt))
        (folder / 'result.json').write_bytes(encoded(report))
        return folder, pilot

    def inspect(self, folder, operation):
        """Run the real candidate proof reader over retained files only."""
        return proof.inspect_transition(folder, OWNER, operation, root=self.root)

    def legacy_fixture(self, operation):
        """Keep legacy fixture paths distinct across provenance mutations."""
        self.case_number += 1
        folder = ui_transition_fixture(self.harness, operation, suffix='-legacy-' + str(self.case_number))
        owner = json.loads((folder / 'owner-after-stop.json').read_bytes())
        return folder, Path(owner['child']['appDirectory']) / 'User/JsScript/ActOnePilot'

    def fallback_input(self, folder, pilot):
        """Retain the exact later unknown-health B source without modifying its positive before-frame."""
        report = json.loads((folder / 'result.json').read_bytes())
        target = pilot / 'observations' / report['scriptSession'] / 'frame-0002.json'
        source = json.loads(target.read_bytes())
        source['hud'].update(world=False, health=None, healthOcr=[],
            healthDiagnostic=dict(decision='conflict-halves-disagree-or-missing'))
        source['ocr'].append(row('2211/4015', 900, 1002, 120, 24))
        target.write_bytes(encoded(source))
        return target, source

    def mutate_frame(self, folder, pilot, label, mutate):
        """Reseal metadata joins so a semantic assertion, rather than a stale checksum, must fail."""
        report = json.loads((folder / 'result.json').read_bytes())
        observation = json.loads((folder / (label + '.json')).read_bytes())
        mutate(observation)
        (folder / (label + '.json')).write_bytes(encoded(observation))
        (pilot / observation['screenshotPath']).with_suffix('.json').write_bytes(encoded(observation))
        for retained in report['observations']:
            if retained['label'] == label:
                retained['jsonSha256'] = hashlib.sha256(encoded(observation)).hexdigest()
        (folder / 'result.json').write_bytes(encoded(report))

    def test_pause_and_resume_are_explicit_version_two_with_exact_input_frame(self):
        """Both operations retain their sole key, explicit omission, original owner and exact source."""
        for operation in ('pause', 'resume'):
            with self.subTest(operation=operation):
                folder, _ = self.fixture(operation)
                result = self.inspect(folder, operation)
                self.assertEqual((result['version'], result['kind']),
                                 (2, 'native-inventory-ui-transition-proof-v2'))
                self.assertEqual(result['transition']['inputSourceFrameId'], 2)
                self.assertFalse(result['physicalInputDeliveryVerified'])

    def test_legacy_fixture_stays_version_one_without_new_settings_or_observation_fields(self):
        """The original proof format remains supported on its original byte and group contract."""
        for operation in ('pause', 'resume'):
            for ordinary_diagnostic in (False, True):
                folder, pilot = self.legacy_fixture(operation)
                if ordinary_diagnostic:
                    for label in ('before', 'after'):
                        self.mutate_frame(folder, pilot, label, lambda o: o.update(timings={
                            'mapDiagnostic': {'mode': 'local', 'reason': 'local_position_unrecognized'}}))
                result = self.inspect(folder, operation)
                self.assertEqual((result['version'], result['kind']), (1, 'native-inventory-transition-proof-v1'))

    def test_legacy_retained_frames_refuse_ui_only_omission_or_version_remnants(self):
        """A residual marker is not made legacy by omitting plan/group/uiObservation declarations."""
        mutations = [
            lambda o: o.update(uiObservation=None),
            lambda o: o.update(timings={'mapDiagnostic': {'mode': 'inventory-ui-only-v1'}}),
            lambda o: o.update(timings={'mapDiagnostic': {
                'reason': 'Inventory UI-only v1: map and orientation deliberately omitted'}}),
            lambda o: o.update(timings={'mapDiagnostic': {'mode': 'inventory-ui-only-v2'}})]
        for operation in ('pause', 'resume'):
            for label in ('before', 'after'):
                for mutate in mutations:
                    folder, pilot = self.legacy_fixture(operation)
                    self.mutate_frame(folder, pilot, label, mutate)
                    with self.subTest(operation=operation, label=label, mutation=str(mutate)):
                        with self.assertRaisesRegex(ValueError, 'Legacy UI proof'):
                            self.inspect(folder, operation)

    def test_stripped_ui_declarations_cannot_downgrade_the_original_omission_diagnostic(self):
        """Even consistently resealed plan/group/frame copies retain their explicit new-mode provenance."""
        for operation in ('pause', 'resume'):
            folder, pilot = self.fixture(operation)
            plan = json.loads((folder / 'plan.json').read_bytes())
            plan.pop('inventoryUiOnlyV1')
            for name in ('group.json', 'group-after-stop.json'):
                group = json.loads((folder / name).read_bytes())
                group['projects'][0]['jsScriptSettingsObject'].pop('inventoryUiOnlyV1')
                (folder / name).write_bytes(encoded(group))
            plan['groupSha256'] = hashlib.sha256((folder / 'group.json').read_bytes()).hexdigest()
            (folder / 'plan.json').write_bytes(encoded(plan))
            for label in ('before', 'after'):
                self.mutate_frame(folder, pilot, label, lambda o: o.pop('uiObservation'))
            report = json.loads((folder / 'result.json').read_bytes())
            target = pilot / 'observations' / report['scriptSession'] / 'frame-0002.json'
            source = json.loads(target.read_bytes())
            source.pop('uiObservation')
            target.write_bytes(encoded(source))
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, 'Legacy UI proof'):
                self.inspect(folder, operation)

    def test_legacy_escape_raw_input_frame_also_refuses_residual_ui_only_provenance(self):
        """The unlabelled native Escape source cannot bypass the retained-frame version boundary."""
        mutations = [
            lambda o: o.update(uiObservation=None),
            lambda o: o.update(timings={'mapDiagnostic': {'mode': 'inventory-ui-only-v1'}}),
            lambda o: o.update(timings={'mapDiagnostic': {
                'reason': 'Inventory UI-only v1: map and orientation deliberately omitted'}})]
        for mutate in mutations:
            folder, pilot = self.legacy_fixture('resume')
            report = json.loads((folder / 'result.json').read_bytes())
            target = pilot / 'observations' / report['scriptSession'] / 'frame-0002.json'
            source = json.loads(target.read_bytes())
            mutate(source)
            target.write_bytes(encoded(source))
            with self.subTest(mutation=str(mutate)), self.assertRaisesRegex(ValueError, 'Legacy UI proof'):
                self.inspect(folder, 'resume')

    def test_missing_or_nonliteral_mode_cannot_silently_switch_proof_format(self):
        """A group with the opt-in bit cannot qualify through the legacy path."""
        for value in (None, False, 1, 'true'):
            folder, _ = self.fixture('resume')
            plan = json.loads((folder / 'plan.json').read_bytes())
            if value is None:
                plan.pop('inventoryUiOnlyV1')
            else:
                plan['inventoryUiOnlyV1'] = value
            (folder / 'plan.json').write_bytes(encoded(plan))
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.inspect(folder, 'resume')

    def test_omitted_map_and_orientation_provenance_is_required_even_when_hud_is_positive(self):
        """A reintroduced pose, yaw or missing mode cannot inherit UI-only authority."""
        mutations = [
            lambda o: o.pop('uiObservation'),
            lambda o: o['uiObservation'].update(mapOmitted=False),
            lambda o: o['uiObservation'].update(orientationOmitted=1),
            lambda o: o.update(map=dict(x=-1266, y=1934)),
            lambda o: o['hud'].update(compassAngle=0),
            lambda o: o['timings'].update(mapDiagnostic=None)]
        for mutate in mutations:
            folder, pilot = self.fixture('resume')
            self.mutate_frame(folder, pilot, 'after', mutate)
            with self.subTest(mutation=str(mutate)), self.assertRaises(ValueError):
                self.inspect(folder, 'resume')

    def test_positive_world_must_replay_all_independent_same_capture_evidence(self):
        """Resealed positive flags cannot conceal a missing or contradictory source signal."""
        mutations = [
            lambda o: o['hud'].update(health=None),
            lambda o: o['hud'].update(healthOcr=[]),
            lambda o: o['hud']['health'].update(current=2200),
            lambda o: o['hud']['healthDiagnostic'].update(decision='conflict-halves-disagree-or-missing'),
            lambda o: o['hud'].update(groundControls=False),
            lambda o: o['ocr'].__setitem__(1, row('Amber', 1680, 450)),
            lambda o: o['ocr'].pop(),
            lambda o: o['ocr'].append(row('Confirm', 850, 550)),
            lambda o: o['ocr'].append(row('Exploration Progress: 0%', 1505, 1016, 290)),
            lambda o: o['ocr'].append(row('200/200', 1624, 32)),
            lambda o: o['hud'].update(loading=True),
            lambda o: o['hud']['health'].update(current=0)]
        for mutate in mutations:
            folder, pilot = self.fixture('resume')
            self.mutate_frame(folder, pilot, 'after', mutate)
            with self.subTest(mutation=str(mutate)), self.assertRaises(ValueError):
                self.inspect(folder, 'resume')

    def test_ambient_place_label_cannot_become_a_full_map_due_to_deliberate_omission(self):
        """An objective/location name outside map UI bands preserves a fully positive world."""
        folder, pilot = self.fixture('resume')
        self.mutate_frame(folder, pilot, 'after', lambda o: o['ocr'].append(row('Starfell Valley', 80, 250, 250)))
        self.assertEqual(self.inspect(folder, 'resume')['version'], 2)

    def test_fresh_publication_cannot_hide_an_expired_input_capture_start(self):
        """UI input uses the original observation start; no new timestamp renews it."""
        folder, pilot = self.fixture('pause')
        report = json.loads((folder / 'result.json').read_bytes())
        frame = pilot / 'observations' / report['scriptSession'] / 'frame-0002.json'
        source = json.loads(frame.read_bytes())
        source['uiObservation']['observationStartedAtUnixMs'] = report['requests'][0]['receipt']['details']['inputEvents'][-1]['startedAt'] - 1001
        frame.write_bytes(encoded(source))
        with self.assertRaisesRegex(ValueError, 'stale or ambiguous'):
            self.inspect(folder, 'pause')

    def test_terminal_observation_must_begin_strictly_after_the_sole_key_finishes(self):
        """A later publication of an earlier image is not a fresh resume confirmation."""
        folder, pilot = self.fixture('resume')
        report = json.loads((folder / 'result.json').read_bytes())
        finished = report['requests'][0]['receipt']['details']['inputEvents'][-1]['finishedAt']
        self.mutate_frame(folder, pilot, 'after', lambda o: o['uiObservation'].update(observationStartedAtUnixMs=finished))
        with self.assertRaisesRegex(ValueError, 'begin after input'):
            self.inspect(folder, 'resume')

    def test_pause_reads_and_qualifies_the_raw_input_frame_not_only_the_before_label(self):
        """A healthy initial observation cannot excuse an ambiguous actual B source."""
        folder, pilot = self.fixture('pause')
        report = json.loads((folder / 'result.json').read_bytes())
        frame = pilot / 'observations' / report['scriptSession'] / 'frame-0002.json'
        source = json.loads(frame.read_bytes())
        source['hud']['health']['current'] = 0
        frame.write_bytes(encoded(source))
        with self.assertRaisesRegex(ValueError, 'pause input lacks'):
            self.inspect(folder, 'pause')

    def test_unknown_health_input_fallback_remains_pause_only(self):
        """A bounded positive raw row permits only B; parsed health and world remain unknown."""
        folder, pilot = self.fixture('pause')
        target, source = self.fallback_input(folder, pilot)
        original = target.read_bytes()
        result = self.inspect(folder, 'pause')
        witness = result['transition']['pauseInputEvidence']
        self.assertEqual(witness['authority'], 'positive-full-frame-health-row-pause-only')
        self.assertEqual((witness['beforeFrameId'], witness['inputSourceFrameId']), (1, 2))
        self.assertEqual(witness['healthRow'], row('2211/4015', 900, 1002, 120, 24))
        self.assertFalse(witness['healthReadinessPromoted'])
        self.assertFalse(witness['worldReadinessPromoted'])
        self.assertFalse(proof.inventory_ui_world_visible(source))
        self.assertEqual(target.read_bytes(), original)
        self.assertIn(str(target), result['files'])

    def test_legacy_proof_did_allow_the_same_unknown_source_prefix(self):
        """The existing V1 proof accepted a healthy before-frame without promoting its later B source."""
        folder = ui_transition_fixture(self.harness, 'pause', suffix='-legacy-fallback')
        owner = json.loads((folder / 'owner-after-stop.json').read_bytes())
        pilot = Path(owner['child']['appDirectory']) / 'User/JsScript/ActOnePilot'
        def positive_before(observation):
            """Make the existing synthetic before-frame explicitly positive as in a qualified helper."""
            observation['map'] = dict(map='Teyvat', x=-1217, y=2508)
            observation['hud'].update(health=dict(current=2211, max=4015), groundControls=True,
                healthOcr=['2211/4015'], healthDiagnostic=None)
            observation['ocr'] = world_rows()
        self.mutate_frame(folder, pilot, 'before', positive_before)
        before = json.loads((folder / 'before.json').read_bytes())
        source = copy.deepcopy(before)
        source.update(frameId=2, timestamp=before['timestamp'] + 15,
            screenshotPath='observations/' + before['session'] + '/frame-0002.png')
        source['hud'].update(world=False, health=None, healthOcr=[],
            healthDiagnostic=dict(decision='conflict-halves-disagree-or-missing'))
        source['ocr'].append(row('2211/4015', 900, 1002, 120, 24))
        (pilot / source['screenshotPath']).write_bytes((folder / 'before.png').read_bytes())
        (pilot / source['screenshotPath']).with_suffix('.json').write_bytes(encoded(source))
        result = self.inspect(folder, 'pause')
        self.assertEqual(result['version'], 1)
        self.assertNotIn('pauseInputEvidence', result['transition'])
        self.assertIsNone(source['hud']['health'])
        self.assertFalse(source['hud']['world'])

    def test_pause_fallback_refuses_missing_ambiguous_or_unqualified_evidence(self):
        """No stale before-frame, duplicate/unbounded HP row or missing ground/identity may authorize B."""
        mutations = [
            lambda o: o['ocr'].pop(),
            lambda o: o['ocr'].append(copy.deepcopy(o['ocr'][-1])),
            lambda o: o['ocr'][-1].update(x=879),
            lambda o: o['ocr'][-1].update(x=1051),
            lambda o: o['ocr'][-1].update(y=989),
            lambda o: o['ocr'][-1].update(y=1031),
            lambda o: o['ocr'][-1].update(text='0/4015'),
            lambda o: o['ocr'][-1].update(text='4016/4015'),
            lambda o: o['ocr'][-1].update(text='2211/0'),
            lambda o: o['ocr'][-1].update(text='2211 of 4015'),
            lambda o: o['hud'].pop('health'),
            lambda o: o['hud'].update(world=True),
            lambda o: o['hud'].update(groundControls=False),
            lambda o: o['hud'].update(loading=True),
            lambda o: o['ocr'].pop(4),
            lambda o: o['ocr'].append(row('Confirm', 850, 550)),
            lambda o: o['uiObservation'].update(observationStartedAtUnixMs=o['timestamp'] - 14),
        ]
        for mutate in mutations:
            folder, pilot = self.fixture('pause')
            target, source = self.fallback_input(folder, pilot)
            mutate(source)
            target.write_bytes(encoded(source))
            with self.subTest(mutation=str(mutate)), self.assertRaises(ValueError):
                self.inspect(folder, 'pause')
        for mutate in (
                lambda o: o['hud'].update(world=False, health=None),
                lambda o: o['uiObservation'].update(observationStartedAtUnixMs=o['timestamp'] - 1001)):
            folder, pilot = self.fixture('pause')
            self.fallback_input(folder, pilot)
            self.mutate_frame(folder, pilot, 'before', mutate)
            with self.subTest(before=str(mutate)), self.assertRaises(ValueError):
                self.inspect(folder, 'pause')

    def test_unknown_health_fallback_never_qualifies_resume(self):
        """Even a positive bounded HP row cannot substitute for a positive terminal world."""
        for world in (False, True):
            folder, pilot = self.fixture('resume')
            def unknown(observation):
                """Retain contradictory health instead of silently promoting the row to parsed HP."""
                observation['hud'].update(world=world, health=None, healthOcr=[],
                    healthDiagnostic=dict(decision='conflict-halves-disagree-or-missing'))
                observation['ocr'].append(row('2211/4015', 900, 1002, 120, 24))
            self.mutate_frame(folder, pilot, 'after', unknown)
            with self.subTest(world=world), self.assertRaises(ValueError):
                self.inspect(folder, 'resume')

    def test_source_owner_and_release_evidence_are_still_mandatory(self):
        """The new recognition mode adds no exception to existing source/owner cleanup validation."""
        for kind in ('source', 'owner', 'busy', 'image'):
            folder, pilot = self.fixture('resume')
            if kind == 'source':
                with (pilot / 'bgi.js').open('ab') as stream:
                    stream.write(b' changed')
            elif kind == 'image':
                with (folder / 'after.png').open('ab') as stream:
                    stream.write(b' changed')
            else:
                value = json.loads((folder / 'owner-after-stop.json').read_bytes())
                value['child']['processId' if kind == 'owner' else 'taskRunning'] = -1 if kind == 'owner' else True
                (folder / 'owner-after-stop.json').write_bytes(encoded(value))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.inspect(folder, 'resume')

    def test_passive_verification_is_not_silently_added_to_the_new_transition_mode(self):
        """The requested scope remains exactly the two existing inventory operations."""
        folder, _ = self.fixture('resume')
        with self.assertRaisesRegex(ValueError, 'limited to inventory transitions'):
            self.inspect(folder, 'verify')

    def test_existing_retention_and_archive_only_replay_preserve_version_two(self):
        """The combat proof boundary retains new evidence without altering any live protocol."""
        for operation, fallback in (('pause', False), ('resume', False), ('pause', True)):
            source, pilot = self.fixture(operation)
            if fallback:
                self.fallback_input(source, pilot)
            retained = self.live / ('retained-' + operation + ('-fallback' if fallback else ''))
            retained.mkdir()
            with patch.dict(sys.modules, {'combat_pause_proof': proof}), \
                    patch.object(trial, 'ROOT', self.root), patch.object(trial, 'LIVE', self.live):
                record = trial.retain_ui_proof(retained, source, OWNER, operation)
                self.assertEqual(trial.verify_ui_proof(record, OWNER, operation, retained)['version'], 2)
                with (pilot / 'bgi.js').open('ab') as stream:
                    stream.write(b' changed-after-retention')
                with self.assertRaises((RuntimeError, ValueError)):
                    trial.verify_ui_proof(record, OWNER, operation, retained)
                historical = trial.verify_ui_proof(record, OWNER, operation, retained, originals=False)
                self.assertEqual(historical, record['proof'])


if __name__ == '__main__':
    unittest.main()
