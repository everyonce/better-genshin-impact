import argparse,json,os,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--frame',type=int,required=True);p.add_argument('--witness',type=int);p.add_argument('--action',choices=['attributes','weapons','artifacts','talents','level','fastEquip','equip','back','close'],required=True);a=p.parse_args()
root=Path(os.environ['BETTERGI_PILOT_APP_DIR'])/'User/JsScript/ActOnePilot'
s=json.loads((root/'controller-status.json').read_text(encoding='utf-8-sig'))
if s['state']!='idle' or s['frameId']!=a.frame:raise SystemExit('Controller changed')
plan={'session':s['session'],'frameId':a.frame,'reviewed':True,'createdAt':int(time.time()*1000),'action':a.action}
if a.witness:plan['witnessFrameId']=a.witness
pending=root/'act-two-team-request.pending.json';pending.write_text(json.dumps(plan));os.replace(pending,root/'act-two-team-request.json')
print(json.dumps({'planWritten':True,'frame':a.frame,'action':a.action}))
