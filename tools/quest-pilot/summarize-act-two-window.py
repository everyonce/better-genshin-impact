"""Summarize a receipt-bounded window from the durable ledger; no gameplay input."""
import argparse,json,collections
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--start-id',required=True);p.add_argument('--end-id',required=True);p.add_argument('--session',default='mvcuzen8-drrh7eb3gqe');p.add_argument('--output',required=True);a=p.parse_args()
receipts={};observations={}
for line in Path('artifacts/act-two-events.jsonl').open(encoding='utf-8-sig'):
 e=json.loads(line)
 if e.get('session')!=a.session:continue
 d=e.get('data') or {}
 if not isinstance(d,dict):continue
 if e.get('type')=='receipt':receipts[d.get('id')]=d
 if e.get('type')=='observation':observations[d.get('frameId')]=d
start,end=receipts[a.start_id],receipts[a.end_id]
lo=start['timestamp']-(start.get('details') or {}).get('elapsedMs',0);hi=end['timestamp']
if hi<lo:raise SystemExit('Reversed receipt window')
rows=sorted((r for r in receipts.values() if start['timestamp']<=r.get('timestamp',0)<=hi),key=lambda r:r['timestamp'])
obs=[o for o in observations.values() if lo<=o.get('timestamp',0)<=hi]
types=collections.Counter();keys=collections.Counter();missions=collections.Counter();holds=observedKey=mountDeclared=gap=0
pauseKnown=False
for i,r in enumerate(rows):
 d=r.get('details') or {};missions[r.get('mission','unknown')]+=1
 for event in d.get('inputEvents') or []:
  kind=event.get('type','unknown');types[kind]+=1
  if kind=='key':
   keys[event.get('key','unknown')]+=1;holds+=event.get('durationMs') or 0
   if isinstance(event.get('finishedAt'),(int,float)) and isinstance(event.get('startedAt'),(int,float)):observedKey+=max(0,event['finishedAt']-event['startedAt'])
  if kind=='actTwoBoundedMount':mountDeclared+=event.get('durationMs') or 0
 result=d.get('result') or {};proof=result.get('pauseProof') or {}
 if result.get('pauseVerified') and proof.get('verified') and proof.get('kind')=='inventory' and proof.get('session')==a.session:pauseKnown=True
 elif not (r.get('mission')=='observe' or result.get('replayOnly') is True and result.get('inputMs')==0):pauseKnown=False
 if i+1<len(rows):
  nxt=rows[i+1];nextStart=nxt['timestamp']-(nxt.get('details') or {}).get('elapsedMs',0)
  if pauseKnown:gap+=max(0,nextStart-r['timestamp'])
timing=collections.Counter()
for o in obs:
 for k in ['totalMs','captureMs','ocrMs','pngWriteMs','mapMs']:
  v=(o.get('timings') or {}).get(k)
  if isinstance(v,(int,float)):timing[k]+=v
world_span=0
world_by_mission=collections.Counter()
for r in rows:
 begin=r['timestamp']-(r.get('details') or {}).get('elapsedMs',0)
 samples=sorted((o for o in obs if begin<=o.get('timestamp',0)<=r['timestamp']),key=lambda o:o['timestamp'])
 for left,right in zip(samples,samples[1:]):
  if all((v.get('hud') or {}).get('world') and not any((v.get('hud') or {}).get(k) for k in ['bigMap','journal','dialogueReady','choice','auto']) for v in [left,right]):
   span=right['timestamp']-left['timestamp'];world_span+=span;world_by_mission[r.get('mission','unknown')]+=span
request=sum((r.get('details') or {}).get('elapsedMs',0) for r in rows)
out={'session':a.session,'startReceipt':a.start_id,'endReceipt':a.end_id,'windowStartUnixMs':lo,'windowEndUnixMs':hi,'wallMs':hi-lo,'controllerMissionRequests':len(rows),'missions':dict(missions),'terminalRequestMs':request,'verifiedInventoryGapLowerBoundMs':gap,'unattributedWallMs':max(0,hi-lo-request-gap),'declaredKeyHoldsMs':holds,'observedKeyCallMs':observedKey,'declaredCombinedMountMs':mountDeclared,'inputEventCounts':dict(types),'keyCounts':dict(keys),'observations':len(obs),'recordedObservationTimingMs':dict(timing),'unmeasuredCategories':{'productiveGameplayMs':None,'modelDecisionMs':None,'waitingLoadingMs':None,'buildTestRestartMs':None,'blockedMs':None,'manualVsLocalSubmissionSplit':None},'notes':['Request and observation timings overlap; do not add them.','Inventory gaps require an explicit Inventory proof, carried only across read-only observe/replay requests. Within-request pause time is excluded; this is a lower bound.','Mission requests include bounded local helper stages and are not a count of model turns or human interventions.','Key events include menu/recovery inputs; combined mount is separate to avoid losing simultaneous input accounting.','Recorded fast-observation total may exclude later vision work; it is not end-to-end capture/vision time.','Unattributed wall time is not automatically productive gameplay or decision time.']}
out['observedWorldSampleSpanMs']=world_span
out['observedWorldSampleSpanByMissionMs']=dict(world_by_mission)
out['notes'].append('World sample spans sum only consecutive world observations within a request, excluding recorded menus/dialogue. They measure sampled exposure/travel/combat time, not useful objective progress, and overlap request time.')
Path(a.output).write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps({k:out[k] for k in ['wallMs','controllerMissionRequests','terminalRequestMs','verifiedInventoryGapLowerBoundMs','unattributedWallMs','declaredKeyHoldsMs','observedWorldSampleSpanMs','observations']}))
