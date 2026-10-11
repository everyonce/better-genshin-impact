const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const session='wind-ride-session',t=50000;
const row=(text,x,y,width=80,height=24)=>({text,x,y,width,height});
const active={session,frameId:396,timestamp:t,map:null,ocr:[row('Kaeya',1660,484,92,41),row('Trial',1790,463,49,24)],
  hud:{world:false,groundControls:true,climbing:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,
    objectiveChanged:false,interact:false,enemyBars:[],health:{current:1063,max:1427}}};
function fixture({laterMotion=false,wrongFrame=false,duplicatePause=false,escapeBeforeLaterWalkFinish=false,missingPauseTimestamp=false}={}) {
  const party={session,mission:'questStep',status:'completed',timestamp:t-10000,id:'party',details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},
    inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',startedAt:t-11000,frameId:20,x:1700,y:1019}]}};
  const move={session,mission:'questStep',status:'completed',timestamp:t+40,frameId:wrongFrame?395:396,id:'move',details:{result:{step:'wolfAdvance',frameId:wrongFrame?395:396},
    inputEvents:[{type:'controllerRevision',startedAt:t-100},{type:'key',key:'VK_W',durationMs:500,startedAt:t-80,finishedAt:t+420},
      {type:'key',key:'VK_W',durationMs:500,startedAt:t+430,finishedAt:t+930}]}};
  const pause={session,mission:'questStep',status:'completed',timestamp:missingPauseTimestamp?undefined:t+1200,frameId:397,id:'pause',details:{result:{step:'wolfPause',pauseVerified:true,frameId:397},
    inputEvents:[{type:'controllerRevision',startedAt:t+950},{type:'key',key:'VK_ESCAPE',durationMs:60,
      startedAt:escapeBeforeLaterWalkFinish?t+800:t+970,finishedAt:escapeBeforeLaterWalkFinish?t+860:t+1030}]}};
  const r=[party,move,pause];
  if(laterMotion)r.push({session,mission:'questStep',status:'completed',timestamp:t+1500,frameId:398,id:'later',details:{result:{step:'wolfForward',frameId:398},
    inputEvents:[{type:'key',key:'VK_W',durationMs:100,startedAt:t+1300,finishedAt:t+1400}]}});
  if(duplicatePause)r.push({...pause,id:'pause-copy'});
  return r;
}
const pauseFrame={session,frameId:397,timestamp:t+1300,map:null,ocr:[row('Continue Challenge',831,399,287,40),row('Leave Domain?',864,640,221,36)],
  hud:{world:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,climbing:false,loading:false,unknownHud:false,objectiveChanged:false}};
const airborne={session,frameId:402,timestamp:t+2100,map:null,ocr:[row('Kaeya',1660,484,92,41),row('Trial',1790,463,49,24),row('Space',1695,1010,81,28)],
  hud:{...active.hud,groundControls:false,health:{current:1063,max:1427}}};

test('fresh grounded wind-base frame links only to one safe move and its later canonical pause',()=>{
  assert.equal(bgi.wolfWindRideGroundState(active),true);
  assert.deepEqual(bgi.wolfWindRideProof(fixture(),active,session),{activeFrameId:396,moveId:'move',pauseId:'pause',pauseFrameId:397,health:{current:1063,max:1427}});
  for(const reports of [fixture({laterMotion:true}),fixture({wrongFrame:true}),fixture({duplicatePause:true})])
    assert.equal(bgi.wolfWindRideProof(reports,active,session),null);
  for(const bad of [
    {...active,hud:{...active.hud,health:{current:800,max:1427}}},
    {...active,hud:{...active.hud,groundControls:false}},
    {...active,hud:{...active.hud,enemyBars:[{}]}},
    {...active,ocr:active.ocr.filter(r=>r.text!=='Trial')},
    {...active,hud:{...active.hud,dialogueReady:true}},
  ]) assert.equal(bgi.wolfWindRideGroundState(bad),false);
});

test('wind checkpoint requires Escape after every W hold and a finite pause receipt timestamp',()=>{
  assert.equal(bgi.wolfWindRideProof(fixture({escapeBeforeLaterWalkFinish:true}),active,session),null,
    'an Escape begun before the final W release cannot prove a canonical pause after the move');
  assert.equal(bgi.wolfWindRideProof(fixture({missingPauseTimestamp:true}),active,session),null,
    'missing receipt timestamp cannot establish Escape-to-pause chronology');
});

test('a later verified move and pause form a new one-shot checkpoint after an earlier attempt',()=>{
  const reports=fixture(),oldAttempt={session,mission:'questStep',status:'stopped',timestamp:t+1400,frameId:397,id:'old-ride',details:{result:{step:'wolfWindRide'},
    inputEvents:[{type:'wolfWindRideContinue',frameId:397,moveId:'move',activeFrameId:396,pauseFrameId:397,startedAt:t+1300}]}};
  const next={...active,frameId:400,timestamp:t+2500};
  reports.push(oldAttempt,
    {session,mission:'questStep',status:'completed',timestamp:t+2200,frameId:400,id:'move-next',details:{result:{step:'wolfAdvance',frameId:400},
      inputEvents:[{type:'key',key:'VK_W',durationMs:500,startedAt:t+1600,finishedAt:t+2100}]}},
    {session,mission:'questStep',status:'completed',timestamp:t+2400,frameId:401,id:'pause-next',details:{result:{step:'wolfPause',pauseVerified:true,frameId:401},
      inputEvents:[{type:'key',key:'VK_ESCAPE',durationMs:60,startedAt:t+2250,finishedAt:t+2310}]}});
  assert.equal(bgi.wolfWindRideProof(reports,next,session).moveId,'move-next');
});

test('wolfWindRide uses one Continue and two released Space pulses, polls only, and never claims landing',async()=>{
  let now=t+1300,continueCount=0,jumps=0,reads=0,air=false;
  const calls=[];
  const api={now:()=>now,checkStop(){},sleep:async ms=>{now+=ms;calls.push('sleep:'+ms);},
    wolfWindRideReady:()=>true,wolfWindRideContinue:()=>{continueCount++;calls.push('continue');},
    wolfWindRideActiveReady:()=>true,wolfWindRideJump:async()=>{jumps++;calls.push('space-pulses');},
    wolfWindRideAirborne:o=>air&&o.frameId>=402};
  const result=await mission.runQuestStep('wolfWindRide',pauseFrame,api,async()=>{
    reads++;now+=200;calls.push('observe');if(reads>=3)air=true;return reads<3?{...active,frameId:397+reads,timestamp:now}:{...airborne,timestamp:now};
  });
  assert.equal(result.status,'stopped');assert.equal(result.continueAttempts,1);assert.equal(result.spacePulses,2);
  assert.equal(result.takeoffVerified,true);assert.equal(result.airborneCueVerified,true);assert.equal(result.landingVerified,false);
  assert.equal(result.polls,3);assert.equal(continueCount,1);assert.equal(jumps,1);assert.equal(reads,3);
  assert.deepEqual(calls.filter(x=>x==='continue'||x==='space-pulses'),['continue','space-pulses']);
});

test('actual adapter lets safe post-jump ground polling continue until the fresh airborne cue appears',async()=>{
  const reports=fixture();let now=t+1300,rows=pauseFrame.ocr,cropRows=[],frame=397,lastSeen=null;
  const keys=[],clicks=[];
  const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
  const context={Date:class extends Date{static now(){return now;}},genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:true,
    getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='reports/'+session+'.json'||p==='observations/'+session+'/frame-0396.json',
      readTextSync:p=>p==='reports/'+session+'.json'?JSON.stringify(reports):p==='observations/'+session+'/frame-0396.json'?JSON.stringify(active):fs.readFileSync(path.join(root,p),'utf8'),
      writeTextSync:()=>true,writeImageSync:()=>true},RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(mat){this.width=1920;this.height=1080;this.rows=mat&&mat.rows||[];}findMulti(){const a=this.rows.map(r=>({...r}));a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows.map(r=>({...r}));a.count=a.length;return a;},
      deriveCrop:()=>({srcMat:{resize:()=>({rows:cropRows.map(r=>({text:r.text,x:(r.x-1520)*3,y:(r.y-985)*3,width:r.width*3,height:r.height*3}))}),inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}}),dispose(){}}),
    click:(x,y)=>clicks.push([x,y]),keyDown:k=>keys.push(['down',k,now]),keyUp:k=>keys.push(['up',k,now]),
    sleep:async ms=>{now+=ms;},moveMouseBy(){throw Error('No camera or cursor movement permitted');},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);adapter.beginMission({mission:'questStep',step:'wolfWindRide',session,createdAt:now});
  const paused=await adapter.observe(session,frame++),groundRows=[...active.ocr,row('1063/1427',906,1001,104,21),row('E',1689,1027,19,21),row('Q',1808,1028,19,21)],
    airRows=[row('Kaeya',1660,484,92,41),row('Trial',1790,463,49,24),row('1063/1427',906,1001,104,21)];
  const api={now:()=>adapter.now(),checkStop:()=>adapter.checkStop(),sleep:ms=>adapter.sleep(ms),wolfWindRideReady:o=>adapter.wolfWindRideReady(o),
    wolfWindRideContinue:()=>adapter.wolfWindRideContinue(),wolfWindRideActiveReady:o=>adapter.wolfWindRideActiveReady(o),
    wolfWindRideJump:o=>adapter.wolfWindRideJump(o),wolfWindRideAirborne:o=>adapter.wolfWindRideAirborne(o)};
  const result=await mission.runQuestStep('wolfWindRide',paused,api,async()=>{
    if(frame<400){rows=groundRows;cropRows=[];}else{rows=airRows;cropRows=[row('Space',1695,1010,81,28)];}
    lastSeen=await adapter.observe(session,frame++);return lastSeen;
  });
  assert.equal(adapter.wolfWindRideAirborne(lastSeen),true,JSON.stringify({hud:lastSeen.hud,ocr:lastSeen.ocr}));
  assert.equal(result.status,'stopped');assert.equal(result.takeoffVerified,true,JSON.stringify(result));assert.equal(result.airborneCueVerified,true);
  assert.equal(result.landingVerified,false);assert.equal(result.polls,3);assert.deepEqual(clicks,[[975,419]]);
  assert.deepEqual(keys.map(e=>e.slice(0,2)),[['down','VK_SPACE'],['up','VK_SPACE'],['down','VK_SPACE'],['up','VK_SPACE']]);
  assert.equal(keys[1][2]-keys[0][2],60);assert.equal(keys[2][2]-keys[1][2],220);assert.equal(keys[3][2]-keys[2][2],60);
  assert.equal(adapter.events().filter(e=>e.type==='wolfWindRideSpace').length,2);
  assert.equal(keys.some(e=>e[1]==='VK_W'||e[1]==='VK_E'),false);
  await assert.rejects(adapter.wolfWindRideJump(paused),/Fresh grounded/);
});

test('wolfObserveBurst performs exactly four same-session observations without game input and reports timing',async()=>{
  let now=20000,reads=0;
  const start={session,frameId:1,timestamp:now,timings:{totalMs:9}};
  const result=await mission.runQuestStep('wolfObserveBurst',start,{now:()=>now,checkStop(){},sleep:async()=>{}},async()=>{
    reads++;now+=10;return {session,frameId:reads+1,timestamp:now,timings:{totalMs:8}};
  });
  assert.equal(result.status,'completed');assert.equal(result.observationCount,4);assert.equal(result.frameId,4);assert.deepEqual(result.frameIds,[1,2,3,4]);
  assert.equal(reads,3);assert.equal(result.meanObservationMs,10);assert.equal(result.totalElapsedMs,30);
});

test('wolfObserveBurst stops on stop request and on stale, foreign, or repeated frames',async()=>{
  let now=20000;
  const initial={session,frameId:1,timestamp:now};
  let calls=0;
  const api={now:()=>now,checkStop(){if(calls>0)throw Error('stop');}};
  await assert.rejects(mission.runQuestStep('wolfObserveBurst',initial,api,async()=>{calls++;now++;return {session,frameId:2,timestamp:now};}),/stop/);
  for(const next of [{session:'foreign',frameId:2,timestamp:now+1},{session,frameId:1,timestamp:now+1},{session,frameId:2,timestamp:now-2000}]) {
    const result=await mission.runQuestStep('wolfObserveBurst',initial,{now:()=>now,checkStop(){}},async()=>next);
    assert.equal(result.status,'stopped');assert.equal(result.observationCount,1);
  }
  assert.equal((await mission.runQuestStep('wolfObserveBurst',null,{now:()=>now,checkStop(){}},async()=>{})).status,'stopped');
});
