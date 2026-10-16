import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('cycle',Path(__file__).resolve().parents[2]/'tools/quest-pilot/act-two-native-cycle.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class CycleTests(unittest.TestCase):
 def setUp(self):
  self.r={'nativeReturned':True,'pauseVerified':True}
  self.o={'hud':{'world':True,'groundControls':True,'health':{'current':2248,'max':2635},'objectives':['Defeat all opponents 2/7'],'enemyBars':[{}]}}
  self.b={'current':2248,'max':2635}
 def reason(self):return m.continuation_reason(self.r,self.o,self.b,0)
 def test_active_counter(self):
  self.assertEqual(m.counter(self.o),2);self.assertIsNone(self.reason())
  self.o['hud']['objectives']=['Defeat all opponents 7/7'];self.assertIn('completed',self.reason())
 def test_no_progress(self):self.assertIn('Two rotations',m.continuation_reason(self.r,self.o,self.b,2))
 def test_pause_and_return(self):
  for key in self.r:
   r={**self.r,key:False};self.assertIsNotNone(m.continuation_reason(r,self.o,self.b,0))
 def test_health_and_world(self):
  for patch in [{'health':{'current':1800,'max':2635}},{'health':{'current':2248,'max':3000}},{'world':False},{'climbing':True},{'groundControls':False}]:
   self.assertIsNotNone(m.continuation_reason(self.r,{'hud':{**self.o['hud'],**patch}},self.b,0))
 def test_lost_event(self):
  self.o['hud'].update(objectives=[],enemyBars=[]);self.assertIn('No current',self.reason())
  self.o['hud']['objectives']=['Lv. 13'];self.assertIsNone(m.counter(self.o))
if __name__=='__main__':unittest.main()
