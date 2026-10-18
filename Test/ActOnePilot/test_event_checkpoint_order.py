import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('events',Path(__file__).resolve().parents[2]/'tools/quest-pilot/record-act-two-events.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CheckpointOrderTests(unittest.TestCase):
    def test_actual_synthetic_id_shape_cannot_override_later_normal_world_capture(self):
        old={'frameId':260071843,'timestamp':1792332307879,'hud':{'world':True,'health':{'current':3845,'max':4015}}}
        fresh={'frameId':7490,'timestamp':1792337310000,'hud':{'world':True,'health':{'current':4015,'max':4015}}}
        self.assertIs(module.latest_world_observation(old,fresh),fresh)
        self.assertIs(module.latest_world_observation(fresh,old),fresh)
        self.assertIs(module.latest_world_observation(fresh,dict(fresh,timestamp=1792337320000,hud={'world':False})),fresh)

if __name__=='__main__':unittest.main()
