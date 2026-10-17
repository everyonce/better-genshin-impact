import importlib.util,json,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('road_chain',Path(__file__).parents[2]/'tools/quest-pilot/act-two-road-chain.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class RoadChainTests(unittest.TestCase):
 def test_recorded_encounter(self):
  o=json.loads(Path(__file__).with_name('act-two-dadaupa-slimes.fixture.json').read_text());self.assertTrue(m.defense_candidate(o))
  for update in [{'climbing':True},{'enemyBars':[]},{'health':{'current':3000,'max':4015}},{'objectives':['Other']}]:self.assertFalse(m.defense_candidate({**o,'hud':{**o['hud'],**update}}))
  self.assertFalse(m.defense_candidate({**o,'map':{**o['map'],'x':-1500}}))
if __name__=='__main__':unittest.main()
