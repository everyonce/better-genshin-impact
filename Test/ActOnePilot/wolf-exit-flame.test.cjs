const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const session='mv4az8yh-yut7shb9ofd';
const row=(text,x,y,width=80,height=24)=>({text,x,y,width,height});
const priorActive={session,frameId:334,timestamp:1791757450746,screenshotPath:'observations/'+session+'/frame-0334.png',map:null,
  ocr:[row('Kaeya',1662,487,92,36),row('Trial',1796,463,49,24)],
  hud:{auto:false,climbing:false,groundControls:true,enemyBars:[],dialogueReady:false,choice:false,journal:false,bigMap:false,
    objectiveChanged:false,health:{current:1063,max:1427},world:false,interact:false,tutorialStep:null}};
const party={session,mission:'questStep',status:'completed',timestamp:1791757000000,id:'party-1',
  details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[
    {type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:20,x:1705,y:1019,startedAt:1791756999000} ]}};
function history({extraInput=false,duplicatePause=false,withoutParty=false,wrongPause=false}={}) {
  const move={session,mission:'questStep',status:'completed',timestamp:1791757450754,frameId:334,id:'move-1',details:{result:{status:'completed',step:'wolfForward',reason:'Bounded Wolf domain action',frameId:334},inputEvents:[
    {type:'controllerRevision',startedAt:1791757449176},{type:'key',key:'VK_W',durationMs:800,startedAt:1791757449202,finishedAt:1791757450024}]}};
  const pause={session,mission:'questStep',status:'completed',timestamp:1791757451776,frameId:335,id:'pause-1',details:{result:{status:'completed',step:'wolfPause',pauseVerified:true,frameId:335},inputEvents:[
    {type:'controllerRevision',startedAt:1791757450828},{type:'key',key:'VK_ESCAPE',durationMs:60,startedAt:1791757450852,finishedAt:1791757450925}]}};
  const reports=[...(withoutParty?[]:[party]),move,pause];
  if(extraInput)reports.push({session,mission:'questStep',status:'completed',timestamp:1791757452000,frameId:335,details:{result:{step:'wolfLookRight'},inputEvents:[{type:'rotate',dx:80,startedAt:1791757451900}]}});
  if(duplicatePause)reports.push({...pause,id:'pause-2',timestamp:1791757452500,frameId:335,details:{result:{...pause.details.result,frameId:336},inputEvents:[{type:'key',key:'VK_ESCAPE',startedAt:1791757452100,finishedAt:1791757452170}]}});
  if(wrongPause)pause.details.result.pauseVerified=false;
  return reports;
}
function pauseObservation({timestamp=1791757452500,frameId=336,leave=true,auto=false}={}) {
  return {session,frameId,timestamp,map:null,ocr:[row('Continue Challenge',831,399,287,40),...(leave?[row('Leave Domain?',862,641,223,35)]:[])],
    hud:{world:false,auto,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false,loading:false,unknownHud:false,objectiveChanged:false}};
}
function fixture({reports=history(),active=priorActive,current=pauseObservation(),foreground=true}={}) {
  let now=1791757452500,captures=0;const clicks=[],keys=[],calls=[];
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:foreground,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='reports/'+session+'.json'||p==='observations/'+session+'/frame-0334.json',
      readTextSync:p=>p==='reports/'+session+'.json'?JSON.stringify(reports):p==='observations/'+session+'/frame-0334.json'?JSON.stringify(active):fs.readFileSync(path.join(root,p),'utf8'),
      writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(){this.width=1920;this.height=1080;}findMulti(){const a=current.ocr.map(x=>({...x}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>{captures++;return {width:1920,height:1080,srcMat:{},findMulti:()=>{const a=current.ocr.map(x=>({...x}));a.count=a.length;return a;},deriveCrop:()=>({srcMat:{resize:()=>({}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}};},
    click:(x,y)=>{clicks.push([x,y]);calls.push('continue');},keyDown:k=>{keys.push(['down',k,now]);calls.push('down:'+k);},keyUp:k=>{keys.push(['up',k,now]);calls.push('up:'+k);},
    sleep:async ms=>{calls.push('sleep:'+ms);now+=ms;},moveMouseBy(){throw Error('No rotation permitted');},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission:'questStep',step:'wolfExitFlame',session,createdAt:now});
  const observe=async()=>adapter.observe(session,Math.max(337,captures+336));
  const api={now:()=>adapter.now(),checkStop:()=>adapter.checkStop(),sleep:ms=>adapter.sleep(ms),
    wolfExitFlameReady:o=>adapter.wolfExitFlameReady(o),wolfExitFlame:()=>adapter.wolfExitFlame()};
  return {adapter,api,observe,clicks,keys,calls,getCaptures:()=>captures,now:()=>now,advance:ms=>{now+=ms;},setForeground:v=>{context.genshin.isGameForeground=v;}};
}

test('saved active frame plus one completed forward and later verified pause form a narrow exit proof',()=>{
  const proof=bgi.wolfExitFlameProof(history(),priorActive,session,1791757452500);
  assert.deepEqual(proof,{movementId:'move-1',activeFrameId:334,pauseId:'pause-1',pauseFrameId:335,pauseTimestamp:1791757451776,
    health:{current:1063,max:1427},continuedAt:1791757450852});
  for(const bad of [history({withoutParty:true}),history({extraInput:true}),history({duplicatePause:true}),history({wrongPause:true})])
    assert.equal(bgi.wolfExitFlameProof(bad,priorActive,session,1791757452500),null);
  const mismatchedMoveFrame=history();mismatchedMoveFrame[1].frameId=333;
  assert.equal(bgi.wolfExitFlameProof(mismatchedMoveFrame,priorActive,session,1791757452500),null);
  assert.equal(bgi.wolfExitFlameProof(history(),{...priorActive,hud:{...priorActive.hud,health:{current:800,max:1427}}},session,1791757452500),null);
  assert.equal(bgi.wolfExitFlameProof(history(),{...priorActive,ocr:priorActive.ocr.filter(x=>x.text!=='Kaeya')},session,1791757452500),null);
  assert.equal(bgi.wolfExitFlameProof(history(),{...priorActive,hud:{...priorActive.hud,groundControls:false}},session,1791757452500),null);
});

test('adapter continues once, sends only W300 with guaranteed release, and does not capture between inputs',async()=>{
  const h=fixture();const paused=await h.observe();
  assert.equal(h.adapter.wolfExitFlameReady(paused),true);
  const before=h.getCaptures();await h.adapter.wolfExitFlame();
  assert.equal(h.getCaptures(),before,'the active-screen OCR capture is deferred until after the bounded W');
  assert.deepEqual(h.clicks,[[975,419]]);
  assert.deepEqual(h.keys.map(x=>x.slice(0,2)),[['down','VK_W'],['up','VK_W']]);
  assert.equal(h.keys[1][2]-h.keys[0][2],300);
  await assert.rejects(h.adapter.wolfExitFlame(),/required/);
  assert.equal(h.clicks.length,1);assert.equal(h.keys.length,2);
});

test('a minutes-old move-to-pause chain remains usable with a newly captured exact pause menu',async()=>{
  const h=fixture();h.advance(5*60*1000);const paused=await h.observe();
  assert.equal(h.adapter.wolfExitFlameReady(paused),true);
  await h.adapter.wolfExitFlame();
  assert.deepEqual(h.clicks,[[975,419]]);
  assert.deepEqual(h.keys.map(x=>x.slice(0,2)),[['down','VK_W'],['up','VK_W']]);
});

test('mission performs its single terminal observation after Continue and W, without claiming the flame cleared',async()=>{
  const h=fixture();const paused=await h.observe();let terminalReads=0;
  const result=await mission.runQuestStep('wolfExitFlame',paused,h.api,async()=>{terminalReads++;return {...paused,frameId:337,timestamp:h.now()+1};});
  assert.equal(result.status,'stopped');assert.equal(result.forwardMs,300);assert.equal(result.targetCleared,false);assert.equal(terminalReads,1);
  assert.deepEqual(h.clicks,[[975,419]]);assert.deepEqual(h.keys.map(x=>x.slice(0,2)),[['down','VK_W'],['up','VK_W']]);
  assert.deepEqual(h.calls.slice(0,3),['continue','sleep:120','down:VK_W']);
});

test('stale or weak provenance, unsafe saved frame, invalid pause menu, and lost focus refuse Continue and W',async()=>{
  const badReports=[history({withoutParty:true}),history({extraInput:true}),history({duplicatePause:true}),history({wrongPause:true})];
  for(const reports of badReports){const h=fixture({reports});const o=await h.observe();assert.equal(h.adapter.wolfExitFlameReady(o),false);await assert.rejects(h.adapter.wolfExitFlame(),/required/);assert.deepEqual(h.clicks,[]);assert.deepEqual(h.keys,[]);}
  for(const active of [
    {...priorActive,timestamp:1791757450000},
    {...priorActive,hud:{...priorActive.hud,health:{current:800,max:1427}}},
    {...priorActive,hud:{...priorActive.hud,world:true}},
    {...priorActive,hud:{...priorActive.hud,groundControls:false}},
    {...priorActive,hud:{...priorActive.hud,interact:true}},
    {...priorActive,hud:{...priorActive.hud,enemyBars:[{}]}}
  ]) {const h=fixture({active}),o=await h.observe();assert.equal(h.adapter.wolfExitFlameReady(o),false,JSON.stringify(active));assert.deepEqual(h.clicks,[]);assert.deepEqual(h.keys,[]);}
  for(const current of [pauseObservation({leave:false})]) {
    const h=fixture({current}),o=await h.observe();assert.equal(h.adapter.wolfExitFlameReady(o),false);assert.deepEqual(h.clicks,[]);assert.deepEqual(h.keys,[]);
  }
  const stale=fixture();const old=await stale.observe();stale.advance(1001);assert.equal(stale.adapter.wolfExitFlameReady(old),false);assert.deepEqual(stale.clicks,[]);assert.deepEqual(stale.keys,[]);
  const unfocused=fixture();const o=await unfocused.observe();unfocused.setForeground(false);assert.throws(()=>unfocused.adapter.wolfExitFlameReady(o),/foreground/);assert.deepEqual(unfocused.clicks,[]);assert.deepEqual(unfocused.keys,[]);
});
