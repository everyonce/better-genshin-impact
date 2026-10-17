import importlib.util,unittest,json,tempfile
from pathlib import Path
s=importlib.util.spec_from_file_location('progress',Path(__file__).parents[2]/'tools/quest-pilot/act_two_hq_progress.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class ProgressTests(unittest.TestCase):
 def sample(self,n,d):return dict(frameId=n,session='s',map=dict(map='Teyvat',x=-775,y=2243),hud=dict(world=True,groundControls=True,objectives=['Lower '+str(d)+'m']),ocr=[])
 def test_persistent_elevation_changes_mode(self):
  r=m.assess([self.sample(1,21),self.sample(2,19),self.sample(3,19)])
  self.assertEqual(r['mode'],'ground_level_hq_approach');self.assertTrue(r['stopHorizontalContinuation']);self.assertFalse(r['horizontalArrivalIsObjectiveProgress'])
 def test_progress_unknown_and_duplicate_are_not_stall_proof(self):
  for f in [[self.sample(1,30),self.sample(2,20),self.sample(3,10)],[self.sample(1,19)]*3,[]]:self.assertFalse(m.assess(f)['stopHorizontalContinuation'])
 def test_entrance_prompt_changes_to_interaction(self):
  o=self.sample(3,19);o['ocr']=[dict(text='F',x=1100,y=522),dict(text='Knights of Favonius Headquarters',x=1210,y=522)]
  self.assertEqual(m.assess([o])['mode'],'verify_and_interact_with_hq_entrance')
 def test_quest_distance_regression_and_oscillation_stop_continuation(self):
  for distances,expected in [([34,43,44],True),([44,34,44],True),([71,60,45],False)]:
   frames=[self.sample(n,d) for n,d in enumerate(distances)]
   for o,d in zip(frames,distances):
    o['map']['x']=-750
    o['hud']['objectives']=['Solve the mystery (Go to Kaeya at the Knights of Favonius','HQ for a hint)',str(d)+'m']
   self.assertEqual(m.assess(frames)['stopHorizontalContinuation'],expected)
 def test_receipt_history_is_bounded_and_deduplicated(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); (root/'observations/s').mkdir(parents=True); output=root/'history.json'
   for n in range(1,5):
    o=self.sample(n,19);o['timestamp']=n*1000
    (root/f'observations/s/frame-{n:04}.json').write_text(json.dumps(o))
    q={'result':{'pauseProof':{'verified':True,'sourceFrameId':n,'session':'s'}}}
    result=m.record_terminal(root,q,output)
   self.assertTrue(result['stopHorizontalContinuation'])
   m.record_terminal(root,q,output)
   self.assertEqual([o['frameId'] for o in json.loads(output.read_text())['endpoints']],[2,3,4])
   self.assertIsNone(m.record_terminal(root,{},output))
   q['result']['pauseProof'].update(sourceFrameId=1,pauseFrameId=5)
   m.record_terminal(root,q,output)
   self.assertEqual(json.loads(output.read_text())['endpoints'][-1]['frameId'],4)
if __name__=='__main__':unittest.main()
