import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('travel', Path(__file__).resolve().parents[2]/'tools/quest-pilot/act-two-travel.py')
travel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(travel)

class TravelTests(unittest.TestCase):
    def run_case(self, pending=False):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/'artifacts') as directory:
            root=Path(directory)/'User/JsScript/ActOnePilot'
            (root/'receipts/test').mkdir(parents=True)
            (root/'observations/test').mkdir(parents=True)
            state=dict(session='test',windowsSessionId=7,state='idle',activeRequestId=None,error=None,frameId=1)
            def save(path,value): path.write_text(json.dumps(value),encoding='utf-8')
            save(root/'controller-status.json',state)
            calls=[]
            def execute(command,**kwargs):
                calls.append(command)
                identifier='request'+str(len(calls))
                if pending:
                    return SimpleNamespace(returncode=0,stderr='',stdout=json.dumps({'submitted':identifier})+'\n'+json.dumps({'pending':identifier}))
                action=None if len(calls)==1 else read_plan()['action']
                state['frameId']+=1
                outcome={'action':action,'pauseVerified':action=='teleport'}
                receipt=dict(id=identifier,session='test',status='stopped' if action else 'completed',frameId=state['frameId'],details={'result':outcome})
                save(root/'receipts/test'/f'{identifier}.json',receipt)
                save(root/'observations/test'/f"frame-{state['frameId']}.json",{'hud':{'bigMap':True},'ocr':[{'text':'Teleport Waypoint'},{'text':'Teleport'},{'text':'Mondstadt','width':127}]})
                save(root/'controller-status.json',state)
                return SimpleNamespace(returncode=0,stderr='',stdout=json.dumps({'submitted':identifier}))
            def read_plan(): return travel.read(root/'act-two-map-request.json')
            with patch.dict(os.environ,{'BETTERGI_PILOT_APP_DIR':directory}),patch('sys.argv',['travel','--session','test','--expected-windows-session-id','7','--destination','city']),patch.object(travel.subprocess,'run',side_effect=execute),patch('builtins.print'):
                if pending:
                    with self.assertRaisesRegex(RuntimeError,'pending'): travel.main()
                    self.assertEqual(len(calls),1)
                else:
                    travel.main()
                    self.assertEqual(len(calls),4)
                    self.assertEqual(read_plan()['action'],'teleport')
    def test_four_guarded_stages(self): self.run_case()
    def test_pending_never_replayed(self): self.run_case(True)

if __name__=='__main__': unittest.main()
