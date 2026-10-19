import copy
import unittest
import json
from pathlib import Path
from act_two_hideout_return import SEGMENTS, validate_entry, finish_first_road, validate_terrain_anchor


class ReturnCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.o = dict(session='s', frameId=100, timestamp=1000,
            hud=dict(world=True, groundControls=True, climbing=False, flying=False, swimming=False,
                     enemyBars=[], health=dict(current=4015, max=4015), compassAngle=142.5,
                     objectives=["Enter Raptor's Hideout", '109m']))
        self.previous = dict(segment=2, session='s', worldFrame=100, exitPassed=True)
        self.review = 'Visible dry ground corridor; road remains left and low rock edge stays right of the clear path.'

    def test_success_preserves_heading_instead_of_early_turn(self):
        spec = validate_entry(self.o, 3, self.review, self.previous, 2000)
        self.assertEqual(spec['actions'], [dict(type='key', key='VK_W', ms=800)] * 6)

    def test_fourth_attempt_overshoot_cannot_start_first_bend(self):
        self.o['hud'].update(compassAngle=172.5, objectives=["Enter Raptor's Hideout", '128m'])
        with self.assertRaisesRegex(ValueError, 'distance'):
            validate_entry(self.o, 2, self.review, self.previous, 2000)

    def test_same_distance_cannot_skip_predecessor(self):
        with self.assertRaisesRegex(ValueError, 'predecessor'):
            validate_entry(self.o, 3, self.review, None, 2000)

    def test_early_turn_rejected_even_with_matching_distance(self):
        self.o['hud']['compassAngle'] = 99
        with self.assertRaisesRegex(ValueError, 'heading'):
            validate_entry(self.o, 3, self.review, self.previous, 2000)

    def test_stale_or_no_terrain_review_rejected(self):
        for review, now in [(self.review, 122000), ('109m looks good', 2000)]:
            with self.assertRaises(ValueError):
                validate_entry(self.o, 3, review, self.previous, now)

    def test_climb_or_damage_rejected(self):
        for change in [dict(climbing=True), dict(health=dict(current=4000, max=4015))]:
            o = copy.deepcopy(self.o)
            o['hud'].update(change)
            with self.assertRaises(ValueError):
                validate_entry(o, 3, self.review, self.previous, 2000)

    def test_waypoint_phase_keeps_original_three_second_walk(self):
        self.assertEqual(sum(a.get('ms', 0) for a in SEGMENTS[0]['actions']), 3000)
        self.assertEqual(sum(a.get('ms', 0) for a in SEGMENTS[1]['actions']), 6400)

    def test_one_signpost_completion_rejects_repetition_and_overshoot(self):
        self.o['hud'].update(compassAngle=174, objectives=["Enter Raptor's Hideout", '141m'])
        previous = dict(segment=1, session='s', worldFrame=100, exitPassed=False)
        review = self.review + ' Signpost immediately right; clear grass ahead.'
        self.assertEqual(sum(a['ms'] for a in finish_first_road(self.o, previous, review, 2000)['actions']), 1200)
        previous['completionStep'] = True
        with self.assertRaises(ValueError):
            finish_first_road(self.o, previous, review, 2000)
        previous['completionStep'] = False
        self.o['hud']['objectives'][-1] = '128m'
        with self.assertRaises(ValueError):
            finish_first_road(self.o, previous, review, 2000)

    def test_recorded_bend_requires_preserved_heading_and_predecessor(self):
        path = Path(__file__).resolve().parents[2] / 'Test/ActOnePilot/fixtures/hideout-return/checkpoint-3.json'
        o = json.loads(path.read_text(encoding='utf-8'))
        previous = dict(segment=2, session=o['session'], worldFrame=o['frameId'], exitPassed=True)
        self.assertEqual(validate_entry(o, 3, self.review, previous, o['timestamp'])['actions'],
                         [dict(type='key', key='VK_W', ms=800)] * 6)
        o['hud']['compassAngle'] = 99
        with self.assertRaisesRegex(ValueError, 'heading'):
            validate_entry(o, 3, self.review, previous, o['timestamp'])

    def test_entry_terrain_requires_positive_read_only_comparison(self):
        root = Path(__file__).resolve().parents[2]
        fixture = root / 'Test/ActOnePilot/fixtures/hideout-return/checkpoint-0'
        o = json.loads(fixture.with_suffix('.json').read_text(encoding='utf-8'))
        image = fixture.with_suffix('.jpg')
        runtime = root / 'artifacts/release-r18/BetterGI-English-win-x64'
        evidence = validate_terrain_anchor(0, o, image, runtime)
        self.assertGreaterEqual(evidence['inliers'], 20)
        self.assertLessEqual(evidence['headingDelta'], 8)
        wrong = root / 'Test/ActOnePilot/fixtures/hideout-return/checkpoint-7.jpg'
        with self.assertRaisesRegex(ValueError, 'differs'):
            validate_terrain_anchor(0, o, wrong, runtime)

    def test_entry_terrain_fails_closed_on_missing_image_or_heading(self):
        root = Path(__file__).resolve().parents[2]
        fixture = root / 'Test/ActOnePilot/fixtures/hideout-return/checkpoint-0'
        o = json.loads(fixture.with_suffix('.json').read_text(encoding='utf-8'))
        runtime = root / 'artifacts/release-r18/BetterGI-English-win-x64'
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            validate_terrain_anchor(0, o, fixture.with_suffix('.missing'), runtime)
        del o['hud']['compassAngle']
        with self.assertRaisesRegex(ValueError, 'heading'):
            validate_terrain_anchor(0, o, fixture.with_suffix('.jpg'), runtime)


if __name__ == '__main__':
    unittest.main()
