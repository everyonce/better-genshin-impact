const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const session='mv4az8yh-yut7shb9ofd';
const witnessTime=1791758005937, now=1791758111000;
const row=(text,x,y,width=80,height=24)=>({text,x,y,width,height});
// Sanitized relevant rows and HUD fields copied from saved frame 344, which was
// the terminal observation of the failed pause receipt -35.
const witness={session,frameId:344,timestamp:witnessTime,map:null,ocr:[
  row('Space',657,193,96,44),row('Tap Space twice in a wind current to',780,186,455,29),row('ride it up',946,216,121,29),
  row('Trial',1796,463,49,24),row('Kaeya',1663,484,92,41)],
  hud:{auto:false,climbing:false,groundControls:true,enemyBars:[],dialogueReady:false,choice:false,journal:false,bigMap:false,
    objectiveChanged:false,health:{current:1063,max:1427},world:false,interact:false,tutorialStep:null}};
// Sanitized frame 349 shape: notably the live observer omits loading and
// unknownHud properties, so the predicate must reject true flags, not absence.
const active={session,frameId:349,timestamp:1791758108950,map:null,ocr:[row('Trial',1798,463,47,24),row('Kaeya',1663,484,92,41),
  row('1063/1427',906,1001,104,21),row('E',1689,1027,19,21),row('Q',1808,1028,19,21)],
  hud:{foodQuantity:null,auto:false,climbing:false,groundControls:true,enemyBars:[],tutorialStep:null,dialogueReady:false,choice:false,
    journal:false,bigMap:false,objectiveChanged:false,health:{current:1063,max:1427},world:false,interact:false}};
const party={session,mission:'questStep',status:'completed',timestamp:1791757000000,id:'party-1',details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},
  inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:20,x:1705,y:1019,startedAt:1791756999000}]}};
function history({laterMove=false,unknownInput=false,wrongLook=false,duplicateWitness=false}={}) {
  const forward={session,mission:'questStep',status:'completed',timestamp:1791758003264,frameId:341,id:'forward-1',details:{result:{step:'wolfForward',frameId:341},
    inputEvents:[{type:'controllerRevision',startedAt:1791758001916},{type:'key',key:'VK_W',durationMs:800,startedAt:1791758001944,finishedAt:1791758002759}]}};
  const failedPause={session,mission:'questStep',status:'stopped',timestamp:1791758005957,frameId:344,id:'pause-failed',details:{result:{step:'wolfPause',pauseVerified:false,frameId:344},
    inputEvents:[{type:'controllerRevision',startedAt:1791758003324},{type:'key',key:'VK_ESCAPE',durationMs:60,startedAt:1791758003356,finishedAt:1791758003417}]}};
  const pause346={session,mission:'questStep',status:'completed',timestamp:1791758039373,frameId:346,id:'pause-346',details:{result:{step:'wolfPause',pauseVerified:true,frameId:346},
    inputEvents:[{type:'controllerRevision',startedAt:1791758038389},{type:'key',key:'VK_ESCAPE',durationMs:60,startedAt:1791758038416,finishedAt:1791758038481}]}};
  const continued={session,mission:'questStep',status:'completed',timestamp:1791758108283,frameId:348,id:'continue-348',details:{result:{step:'wolfContinue',frameId:348},
    inputEvents:[{type:'controllerRevision',startedAt:1791758107333},{type:'wolfContinue',frameId:347,startedAt:1791758107357}]}};
  const look={session,mission:'questStep',status:'completed',timestamp:1791758108958,frameId:349,id:'look-349',details:{result:{step:'wolfLookDown',frameId:349},
    inputEvents:[{type:'controllerRevision',startedAt:1791758108362},{type:'rotate',dx:0,dy:16,startedAt:1791758108382}]}};
  const pause350={session,mission:'questStep',status:'completed',timestamp:1791758110080,frameId:350,id:'pause-350',details:{result:{step:'wolfPause',pauseVerified:true,frameId:350},
    inputEvents:[{type:'controllerRevision',startedAt:1791758109016},{type:'key',key:'VK_ESCAPE',durationMs:60,startedAt:1791758109037,finishedAt:1791758109102}]}};
  const resumeProof={session,mission:'questStep',status:'completed',timestamp:1791757999000,frameId:340,id:'resume-proof',
    details:{result:{step:'wolfResume'},inputEvents:[{type:'wolfResumeProof',verified:true,fromSession:'previous-session',toSession:session}]}};
  const rows=[party,resumeProof,forward,failedPause,pause346,continued,look,pause350];
  if(laterMove) rows.push({session,mission:'questStep',status:'completed',timestamp:1791758110500,frameId:351,id:'move-after-witness',details:{result:{step:'wolfForward',frameId:351},inputEvents:[{type:'key',key:'VK_W',durationMs:100,startedAt:1791758110200,finishedAt:1791758110300}]}});
  if(unknownInput) rows.push({session,mission:'questStep',status:'completed',timestamp:1791758109500,frameId:350,id:'unknown-input',details:{result:{step:'unknown'},inputEvents:[{type:'key',key:'VK_SPACE',durationMs:60,startedAt:1791758109400,finishedAt:1791758109460}]}});
  if(wrongLook) look.details.inputEvents[1].dy=600;
  if(duplicateWitness) rows.push({...failedPause,id:'pause-failed-copy'});
  return rows;
}
function pauseFrame(t=1791758111000){return {session,frameId:350,timestamp:t,map:null,ocr:[row('Continue Challenge',831,399,287,40),row('Leave Domain?',864,640,221,36)],
  hud:{world:false,auto:false,climbing:false,journal:false,bigMap:false,dialogueReady:false,choice:false,loading:false,unknownHud:false,objectiveChanged:false}};}

test('real frame 344 wind witness and actual saved-style reports link through a later pause despite elapsed idle time',()=>{
  assert.equal(bgi.wolfWindCue(witness.ocr),true);
  const proof=bgi.wolfWindWitnessProof(history(),witness,session,now);
  assert.deepEqual(proof,{witnessFrameId:344,failedPauseId:'pause-failed',latestPauseId:'pause-350',latestPauseFrameId:350,health:{current:1063,max:1427}});
});

test('witness proof rejects changed cue, duplicates, unbounded history input, and any later movement',()=>{
  for(const reports of [history({laterMove:true}),history({unknownInput:true}),history({wrongLook:true}),history({duplicateWitness:true})])
    assert.equal(bgi.wolfWindWitnessProof(reports,witness,session,now),null);
  for(const bad of [
    {...witness,ocr:witness.ocr.filter(r=>r.text!=='ride it up')},
    {...witness,ocr:[...witness.ocr,row('ride it up',1100,300)]},
    {...witness,ocr:witness.ocr.map(r=>r.text==='Space'?{...r,x:900}:r)},
    {...witness,hud:{...witness.hud,health:{current:700,max:1427}}},
    {...witness,hud:{...witness.hud,groundControls:false}},
  ]) assert.equal(bgi.wolfWindWitnessProof(history(),bad,session,now),null);
});

test('saved frame 349 active HUD remains valid when un-emitted loading and unknownHud fields are absent',()=>{
  assert.equal(bgi.wolfWindActiveState(active,active.timestamp+100),true);
  for(const patch of [
    {hud:{...active.hud,health:{current:800,max:1427}}},
    {hud:{...active.hud,dialogueReady:true}},
    {hud:{...active.hud,loading:true}},
    {hud:{...active.hud,unknownHud:true}},
    {hud:{...active.hud,enemyBars:[{}]}},
    {ocr:active.ocr.filter(r=>r.text!=='Trial')},
  ]) assert.equal(bgi.wolfWindActiveState({...active,...patch},active.timestamp+100),false);
});

function adapterHarness(reports=history()) {
  let clock=now,rows=pauseFrame().ocr,captures=0;
  const calls=[],clicks=[],keys=[];
  const context={Date:class extends Date{static now(){return clock;}},genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='reports/'+session+'.json'||p==='observations/'+session+'/frame-0344.json',
      readTextSync:p=>p==='reports/'+session+'.json'?JSON.stringify(reports):p==='observations/'+session+'/frame-0344.json'?JSON.stringify(witness):fs.readFileSync(path.join(root,p),'utf8'),
      writeTextSync:()=>true,writeImageSync:()=>true},RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(){this.width=1920;this.height=1080;}findMulti(){const a=rows.map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>{captures++;calls.push('capture');return {width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows.map(r=>({...r}));a.count=a.length;return a;},deriveCrop:()=>({srcMat:{resize:()=>({}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}};},
    click:(x,y)=>{clicks.push([x,y]);calls.push('continue');},keyDown:k=>{keys.push(['down',k,clock]);calls.push('down:'+k);},keyUp:k=>{keys.push(['up',k,clock]);calls.push('up:'+k);},
    sleep:async ms=>{calls.push('sleep:'+ms);clock+=ms;},moveMouseBy(){throw Error('No camera movement permitted');},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);adapter.beginMission({mission:'questStep',step:'wolfWindTakeoff',session,createdAt:clock});
  const observe=async frame=>adapter.observe(session,frame);
  const api={now:()=>adapter.now(),checkStop:()=>adapter.checkStop(),sleep:ms=>adapter.sleep(ms),wolfWindTakeoffReady:o=>adapter.wolfWindTakeoffReady(o),
    wolfWindTakeoffContinue:()=>adapter.wolfWindTakeoffContinue(),wolfWindTakeoffActiveReady:o=>adapter.wolfWindTakeoffActiveReady(o),
    wolfWindTakeoffPulses:o=>adapter.wolfWindTakeoffPulses(o)};
  return {adapter,api,observe,calls,clicks,keys,get captures(){return captures;},setRows:value=>{rows=value;},get clock(){return clock;},advance:ms=>{clock+=ms;}};
}

test('adapter-backed mission continues once, captures grounded HUD, sends two released Space pulses, and does not claim ascent',async()=>{
  const h=adapterHarness();const initial=await h.observe(350);assert.equal(h.adapter.wolfWindTakeoffReady(initial),true);
  let reads=0;
  const result=await mission.runQuestStep('wolfWindTakeoff',initial,h.api,async()=>{
    reads++;
    h.setRows(active.ocr);
    return h.observe(350+reads);
  });
  assert.equal(result.status,'stopped');assert.equal(result.continueAttempts,1);assert.equal(result.spacePulses,2);
  assert.equal(result.takeoffVerified,false);assert.equal(result.glideAttempts,0);assert.equal(reads,2);
  assert.deepEqual(h.clicks,[[975,419]]);
  assert.deepEqual(h.keys.map(k=>k.slice(0,2)),[['down','VK_SPACE'],['up','VK_SPACE'],['down','VK_SPACE'],['up','VK_SPACE']]);
  assert.equal(h.keys[1][2]-h.keys[0][2],60);assert.equal(h.keys[2][2]-h.keys[1][2],220);assert.equal(h.keys[3][2]-h.keys[2][2],60);
  assert.deepEqual(h.calls.filter(c=>c==='continue'||c==='capture'||c==='down:VK_SPACE'||c==='up:VK_SPACE'),
    ['capture','continue','capture','down:VK_SPACE','up:VK_SPACE','down:VK_SPACE','up:VK_SPACE','capture']);
  assert.equal(h.calls.includes('down:VK_W'),false);assert.equal(h.calls.includes('down:VK_E'),false);
  assert.throws(()=>h.adapter.wolfWindTakeoffContinue(),/required/);
  assert.equal(h.clicks.length,1);assert.equal(h.keys.length,4);
});

test('adapter refuses stale pause, moved history, weak witness, and unsafe resumed HUD before Space',async()=>{
  for(const reports of [history({laterMove:true}),history({unknownInput:true}),history({duplicateWitness:true})]) {
    const h=adapterHarness(reports),o=await h.observe(350);assert.equal(h.adapter.wolfWindTakeoffReady(o),false);assert.deepEqual(h.clicks,[]);assert.deepEqual(h.keys,[]);
  }
  const stale=adapterHarness(),old=await stale.observe(350);stale.advance(-1100);
  assert.equal(stale.adapter.wolfWindTakeoffReady(old),false);assert.deepEqual(stale.clicks,[]);
  const h=adapterHarness(),pause=await h.observe(350);assert.equal(h.adapter.wolfWindTakeoffReady(pause),true);
  h.adapter.wolfWindTakeoffContinue();
  h.setRows(active.ocr.filter(r=>r.text!=='Trial'));
  const unsafe=await h.observe(351);assert.equal(h.adapter.wolfWindTakeoffActiveReady(unsafe),false);
  assert.deepEqual(h.keys,[]);assert.equal(h.clicks.length,1);
});
