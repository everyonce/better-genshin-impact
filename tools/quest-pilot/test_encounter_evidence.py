"""Inert pair fixtures for real public worker waits, provenance rejection and shared evidence budgets."""
import hashlib
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from test_run_rdp_route import Fixture, launcher, load


def pixel(value):
    """One decodable PNG pixel with distinct bytes per simulated capture."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes([0, value]))) + chunk(b'IEND', b''))


def encounter(fixture, start=3, dialogue=False):
    """Publish an immutable receipt with exact source captures and return a matching report record."""
    pilot = fixture.pilot
    sid = 'new-owned'
    rid = 'mission-' + f'{start:032x}'
    req = dict(session=sid, id=rid, mission='dialogue' if dialogue else 'questStep', expectedFrameId=start - 1)
    if dialogue:
        req['talkTo'] = 'Cyrus'
        actions = dict(talkTo='Cyrus', interactionFrameId=start, greetingFrameId=start+1, menuFrameId=start+1,
                       farewellFrameId=start+1, worldFrameId=start+2)
    else:
        req['step'] = 'actTwoFieldCombat'
        actions = dict(nativeAttempted=True, beforeFrameId=start, afterFrameId=start+2,
                       chunks=[dict(nativeReturned=True, actionId=rid+':rotation:0', beforeFrameId=start, afterFrameId=start+1)])
    receipt = dict(session=sid, id=rid, mission=req['mission'], status='completed' if dialogue else 'stopped',
                   frameId=start+3, details=dict(result=actions))
    command = load(Path(launcher.__file__).with_name('act-one-command.py'), '_test_enc_command')
    native = command.request_receipt_path(pilot, sid, rid)
    native.parent.mkdir(parents=True, exist_ok=True)
    native.write_bytes(json.dumps(receipt, indent=1).encode())
    sources = []
    for frame in range(start, start+4):
        path = command.observation_path(pilot, sid, frame)
        path.parent.mkdir(parents=True, exist_ok=True)
        image = path.with_suffix('.png')
        obj = dict(session=sid, frameId=frame, screenshotPath=image.relative_to(pilot).as_posix(),
                   ocr=[dict(text='Character EXP 15', x=204, y=460)] if frame == start+3 else [],
                   hud=dict(captureStamp=dict(session=sid, frameId=frame, source='game-capture-start')))
        path.write_bytes(b'\xef\xbb\xbf' + json.dumps(obj, indent=1).encode() + b'\r\n')
        image.write_bytes(pixel(frame))
        sources.append((path, image))
    return dict(request=req, receipt=receipt, observation=obj), sources


class EncounterEvidenceTests(unittest.TestCase):
    """Use real temporary files on both sides of the current-leg archive boundary."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = Fixture(Path(self.temp.name), 2)
        self.command = load(Path(launcher.__file__).with_name('act-one-command.py'), '_test_capture_command')
        evidence = load(Path(launcher.__file__).with_name('encounter_evidence.py'), '_test_evidence')
        self.archive = evidence.EncounterArchive(self.fixture.pilot, self.fixture.output, self.command, launcher.save)

    def test_worker_copies_during_running_leg_and_preserves_failed_second_leg(self):
        f = self.fixture
        f.config['saveEncounterFrames'] = True
        previous = f.execute
        originals = {}
        def run(argv, folder, timeout, *, on_progress):
            number = len(f.calls) + 1
            if number == 2:
                f.route_status = 'stopped'
            rc = previous(argv, folder, timeout)
            progress = Path(argv[argv.index('--progress')+1])
            result = launcher.read(progress)
            record, pairs = encounter(f, number*5, dialogue=number == 2)
            result['records'].append(record)
            launcher.save(progress, dict(result, status='running'))
            on_progress()
            # The reward is a later canonical publication for an already settled request.
            if number == 1:
                result['fieldCombatRewards'] = [dict(requestId=record['request']['id'], rewardFrameId=number*5+3,
                                                      attackFrameId=number*5, rewardText='Character EXP 15')]
            launcher.save(progress, result)
            on_progress()
            manifest = launcher.read(f.output / 'encounter-evidence.json')
            self.assertTrue(manifest['frames'])
            for path, image in pairs:
                originals[int(path.stem.split('-')[1])] = (path.read_bytes(), image.read_bytes())
                path.unlink()
                image.unlink()
            return rc
        f.execute = run
        outcome = f.worker()
        self.assertEqual((outcome['status'], outcome['legs'][1]['status']), ('failed', 'stopped'))
        summary = outcome['encounterEvidence']
        self.assertEqual(summary['issues'], [])
        self.assertEqual([e['frameId'] for e in summary['frames']], [5,7,6,8,10,11,12])
        roles = set()
        for entry in summary['frames']:
            data, image = originals[entry['frameId']]
            self.assertEqual((f.output / entry['json']).read_bytes(), data)
            self.assertEqual((f.output / entry['png']).read_bytes(), image)
            self.assertEqual((entry['jsonSha256'], entry['pngSha256']),
                             (hashlib.sha256(data).hexdigest(), hashlib.sha256(image).hexdigest()))
            for use in entry['uses']:
                native = self.command.request_receipt_path(f.pilot, entry['session'], use['requestId'])
                self.assertEqual(hashlib.sha256(native.read_bytes()).hexdigest(), use['receiptSha256'])
                roles.add(use['role'])
        self.assertTrue({'combat-reward','combat-before','combat-after','npc-selected','npc-greeting','npc-menu','npc-farewell','npc-world-return'} <= roles)
        self.assertEqual(summary, launcher.read(f.output / 'encounter-evidence.json'))

    def test_rejects_path_stamp_receipt_and_png_mismatches_and_expired_files(self):
        f = self.fixture
        record, pairs = encounter(f)
        one, two, three = pairs[:3]
        first = launcher.read(one[0])
        first['screenshotPath'] = '../../outside.png'
        launcher.save(one[0], first)
        second = launcher.read(two[0])
        second['hud']['captureStamp']['frameId'] += 1
        launcher.save(two[0], second)
        damaged = bytearray(three[1].read_bytes())
        damaged[28] ^= 1
        three[1].write_bytes(damaged)
        foreign, _ = encounter(f, 20, True)
        foreign['receipt']['details']['result']['greetingFrameId'] -= 1
        missing, absent = encounter(f, 40, True)
        for path, _ in absent:
            path.unlink()
        forged = dict(record, request=dict(record['request'], id='../outside'))
        self.archive.capture_leg(dict(session='new-owned', records=[record,foreign,missing,forged]), 'new-owned', 1)
        summary = self.archive.summary
        self.assertEqual(summary['frames'], [])
        self.assertGreaterEqual(summary['skipped'], 8)
        reasons = ' '.join(row['reason'] for row in summary['issues'])
        for phrase in ['screenshot path mismatch', 'invalid PNG', 'immutable native receipt', 'valid generated']:
            self.assertIn(phrase, reasons)
        self.assertFalse((f.output / 'encounters').exists())

    def test_frame_and_byte_caps_span_legs_and_default_has_no_archive(self):
        f = self.fixture
        self.assertNotIn('encounterEvidence', f.worker())
        self.assertFalse((f.output / 'encounters').exists())
        for cap in ['maxBytes', 'maxFrames']:
            with self.subTest(cap=cap):
                output = f.root / cap
                output.mkdir()
                archive = type(self.archive)(f.pilot, output, self.command, launcher.save)
                record, pairs = encounter(f, 3)
                archive.summary[cap] = (sum(p.stat().st_size for n in [0,2] for p in pairs[n]) if cap=='maxBytes' else 2)
                archive.capture_leg(dict(session='new-owned',records=[record]), 'new-owned', 1)
                second, _ = encounter(f, 20, True)
                archive.capture_leg(dict(session='new-owned',records=[second]), 'new-owned', 2)
                self.assertEqual([r['frameId'] for r in archive.summary['frames']], [3,5])
                self.assertGreater(archive.summary['skipped'], 0)
                self.assertLessEqual(archive.summary['bytes'], archive.summary['maxBytes'])
                self.assertEqual(len(list((output/'encounters'/'new-owned').iterdir())), 2)

    def test_public_cli_flag(self):
        args = ['--route','city.json','--progress','route.json','--expected-uid','123456789']
        self.assertFalse(launcher.parse_args(args).save_encounter_frames)
        self.assertTrue(launcher.parse_args(args+['--save-encounter-frames']).save_encounter_frames)


if __name__ == '__main__':
    unittest.main()
