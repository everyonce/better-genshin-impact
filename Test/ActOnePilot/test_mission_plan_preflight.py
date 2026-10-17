import importlib.util,json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('mission_cli_preflight',ROOT/'tools/quest-pilot/act-one-command.py'); cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
class MissionPlanPreflightTests(unittest.TestCase):
 def test_navigation_limit_and_finite_coordinates(self):
  p={'map':'Teyvat','x':-1120,'y':2190};r={'objective':'Explore for Adventure Rank','waypoints':[p]*4}
  cli.validate_navigation_plan(r,45000)
  for bad,deadline in [({**r,'waypoints':[p]*5},40000),(r,45001),(r,True),({**r,'waypoints':[]},1000),({**r,'waypoints':[{**p,'x':float('nan')}]},1000),({**r,'waypoints':[{**p,'y':True}]},1000)]:
   with self.assertRaises(ValueError):cli.validate_navigation_plan(bad,deadline)
 def test_missing_field_diagnostics_never_writes_plan(self):
  with tempfile.TemporaryDirectory() as t:
   app=Path(t);root=app/'User/JsScript/ActOnePilot';obs=root/'observations/s';obs.mkdir(parents=True)
   (root/'controller-status.json').write_text(json.dumps({'state':'idle','frameId':2,'session':'s'}))
   witness=obs/'frame-0001.json';witness.write_text(json.dumps({'session':'s','frameId':1,'hud':{'world':True}}))
   cmd=[sys.executable,str(ROOT/'tools/quest-pilot/act-two-field-plan.py'),'--frame','2','--witness','1','--actions','[{"type":"look","dx":100,"dy":0}]']
   env={**os.environ,'BETTERGI_PILOT_APP_DIR':str(app)}
   failed=subprocess.run(cmd,env=env,capture_output=True,text=True)
   self.assertNotEqual(failed.returncode,0);self.assertIn('enemy-scan diagnostics',failed.stderr);self.assertFalse((root/'act-two-field-request.json').exists())
   (root/'act-two-field.js').write_bytes((ROOT/'BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js').read_bytes())
   witness.write_text(json.dumps({'session':'s','frameId':1,'timestamp':int(time.time()*1000),'hud':{'enemyBarDiagnostic':{'candidates':0}}}))
   rejected=subprocess.run(cmd,env=env,capture_output=True,text=True);self.assertNotEqual(rejected.returncode,0);self.assertIn('witness_not_verified_world',rejected.stderr);self.assertFalse((root/'act-two-field-request.json').exists())
if __name__=='__main__':unittest.main()
