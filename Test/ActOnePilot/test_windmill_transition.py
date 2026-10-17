import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('windmill',ROOT/'tools/quest-pilot/act-two-windmill-transition.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class WindmillTransition(unittest.TestCase):
 def test_recorded_release_and_pose_changes(self):
  recipe=json.loads((ROOT/'tools/quest-pilot/act-two-windmill-transition.json').read_text());expected=recipe['landing'][0]['before'];o=json.loads((ROOT/'Test/ActOnePilot/act-two-hideout-riddle-landing.fixture.json').read_text());self.assertTrue(m.matches(o,expected))
  for path,value in [('health',4000),('height',28),('heading',180),('x',20)]:
   c=json.loads(json.dumps(o))
   if path=='health':c['hud']['health']['current']=value
   elif path=='height':c['hud']['objectives']=['Look for the location in the riddle','Higher 28m']
   elif path=='heading':c['map']['cameraAngle']=value
   else:c['map']['x']+=value
   self.assertFalse(m.matches(c,expected))
 def test_recipe_excludes_failed_balcony_navigation(self):
  recipe=json.loads((ROOT/'tools/quest-pilot/act-two-windmill-transition.json').read_text());self.assertTrue(recipe['requiresFreshVisualReviewBeforeRelease']);self.assertEqual(recipe['ascent'][-1]['name'],'landing-survey');self.assertEqual(len(recipe['landing']),1)

if __name__=='__main__':unittest.main()
