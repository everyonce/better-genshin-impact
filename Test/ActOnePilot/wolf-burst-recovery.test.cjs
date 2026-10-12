const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=50,height=20)=>({text,x,y,width,height});
const entry=[
  {session:'wolf',mission:'questStep',status:'completed',timestamp:1000,
    details:{result:{step:'wolfStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[
      {type:'wolfDomainStart',label:'Deep Within the Temple of the Wolf',startedAt:900}]}},
  {session:'wolf',mission:'questStep',status:'completed',timestamp:1500,
    details:{result:{step:'wolfPartyStart'},inputEvents:[
      {type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:2,x:1700,y:1019,startedAt:1400}]}}
];

function croppedAdapter({priorQ=false,throwQ=false,withQ=true,foreground=true,health='775/1427',dropActiveParty=false,historyRows=null,markers=new Map(),failMarkerWrite=false}={}) {
  let now=2000,frame=0,phase='pause',focus=foreground;const inputs=[],clicks=[],controlCrops=[],partyCrops=[];
  let history=historyRows|| (priorQ?[...entry,{session:'wolf',mission:'questStep',status:'stopped',timestamp:1800,
    details:{result:{step:'wolfBurstRecovery',burstAttempted:true},inputEvents:[{type:'wolfBurstRecoveryQAttempt',key:'VK_Q',startedAt:1700}]}}]:entry);
  function rows() {
    const values=phase==='pause'?[]:dropActiveParty?[]:[row('Kaeya',1664,485,90,38),row('Trial',1802,463,43,22)];
    if(phase!=='pause') values.push(row(health,910,1002,100,18));
    if(phase==='pause') values.push(row('Continue Challenge',831,399,287,40),row('Lower Difficulty',849,518,251,42),row('Leave Domain?',864,640,221,36));
    return values;
  }
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:focus,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>markers.has(p),readTextSync:p=>p==='reports/wolf.json'?JSON.stringify(history):markers.has(p)?markers.get(p):fs.readFileSync(path.join(root,p),'utf8'),
      writeTextSync:(p,s)=>{if(p==='reports/wolf.wolfBurstRecoveryQAttempt.json'&&failMarkerWrite)return false;if(p==='reports/wolf.wolfBurstRecoveryQAttempt.json')markers.set(p,s);return true;},writeImageSync:()=>true},RecognitionObject:{Ocr:()=>({})},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},
      RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x}}},
    ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=(this.mat.rows||[]).map(x=>({...x}));a.count=a.length;return a;}dispose(){}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows().map(x=>({...x}));a.count=a.length;return a;},
      deriveCrop:(x,y,w,h)=>{
        if(x===1520&&y===985){controlCrops.push({x,y,w,h});const local=withQ?[{text:'Q',x:(1802.333-1520)*3,y:(1026.333-985)*3,width:28.333*3,height:26.333*3}]:[];
          return {srcMat:{resize:()=>({rows:local})},dispose(){}};}
        if(x===1630&&y===330){partyCrops.push({x,y,w,h});const local=[row('Kaeya',(1664-1630)*3,(487-330)*3),row('Trial',(1796-1630)*3,(463-330)*3)];
          return {srcMat:{resize:()=>({rows:local})},dispose(){}};}
        if(x===900&&y===990){const local=phase==='pause'?[]:[{text:health,x:20,y:20,width:250,height:45}];return {srcMat:{resize:()=>({rows:local})},dispose(){}};}
        if(x===893&&y===998||x===967&&y===998)return {srcMat:{resize:()=>({rows:[]})},dispose(){}};
        return {srcMat:{inRange:()=>({findContoursAsArray:()=>[],dispose(){}})},dispose(){}};
      },dispose(){}}),
    keyDown:key=>{inputs.push(['down',key,now]);if(key==='VK_Q'&&throwQ)throw new Error('simulated keyDown failure');
      if(key==='VK_ESCAPE')phase='pause';},
    keyUp:key=>inputs.push(['up',key,now]),click:(x,y)=>{clicks.push([x,y,now]);phase='active';},
    moveMouseBy(){},sleep:async ms=>{now+=ms;},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission:'questStep',step:'wolfBurstRecovery',session:'wolf',createdAt:1900});
  async function observe(){frame++;return adapter.observe('wolf',frame);}
  return {adapter,observe,inputs,clicks,controlCrops,partyCrops,markers,context,setFocus:value=>{focus=value;context.genshin.isGameForeground=value;},setPhase:value=>{phase=value;},now:()=>now};
}

test('one typed Continue, Q60 and explicit Escape yield a fresh canonical pause without claiming success',async()=>{
  const f=croppedAdapter();const initial=await f.observe();
  assert.equal(initial.hud.health,null);assert.equal(initial.hud.groundControls,false);
  assert.deepEqual(Array.from(initial.ocr,r=>r.text),['Continue Challenge','Lower Difficulty','Leave Domain?']);
  assert.equal(f.adapter.wolfBurstContinueReady(initial),true);
  const result=await mission.runQuestStep('wolfBurstRecovery',initial,f.adapter,f.observe);
  assert.equal(result.status,'stopped');assert.equal(result.continueAttempts,1);assert.equal(result.burstAttempts,1,result.reason);
  assert.equal(result.pauseAttempts,1);assert.equal(result.pauseVerified,true);
  assert.equal(result.burstEffectVerified,false);assert.equal(result.combatComplete,false);assert.equal(result.questComplete,false);
  assert.deepEqual(f.clicks.map(x=>x.slice(0,2)),[[975,419]]);
  assert.deepEqual(f.inputs.map(x=>x.slice(0,2)),[['down','VK_Q'],['up','VK_Q'],['down','VK_ESCAPE'],['up','VK_ESCAPE']]);
  assert.ok(f.controlCrops.length>=1,'Q is recovered through the scaled bottom-control OCR crop');
  assert.ok(f.markers.has('reports/wolf.wolfBurstRecoveryQAttempt.json'),'Q attempt is durably recorded before input');
  assert.ok(result.inputMs>=120);assert.ok(result.elapsedMs<=8000);
});

test('prior durable same-session Q receipt blocks Continue and any Q replay',async()=>{
  const f=croppedAdapter({priorQ:true});const initial=await f.observe();
  assert.equal(f.adapter.wolfBurstContinueReady(initial),false);
  const result=await mission.runQuestStep('wolfBurstRecovery',initial,f.adapter,f.observe);
  assert.equal(result.continueAttempts,0);assert.equal(result.burstAttempted,false);
  assert.deepEqual(f.clicks,[]);assert.deepEqual(f.inputs,[]);
});

test('failed result with Q-attempt event blocks replay; durable marker survives report rolloff',async()=>{
  const failed=[...entry,{session:'wolf',mission:'questStep',status:'stopped',timestamp:1800,
    details:{result:null,inputEvents:[{type:'wolfBurstRecoveryQAttempt',key:'VK_Q',startedAt:1700}]}}];
  const failedReceipt=croppedAdapter({historyRows:failed});const failedPause=await failedReceipt.observe();
  assert.equal(failedReceipt.adapter.wolfBurstContinueReady(failedPause),false);

  const attempted=croppedAdapter();const initial=await attempted.observe();
  await attempted.adapter.wolfBurstRecoveryContinue();await attempted.adapter.sleep(450);const active=await attempted.observe();
  assert.equal(attempted.adapter.wolfBurstRecoveryQReady(active),true);
  await attempted.adapter.wolfBurstRecoveryQ();
  const rolledOff=croppedAdapter({historyRows:entry,markers:attempted.markers});const rolledPause=await rolledOff.observe();
  assert.equal(rolledOff.adapter.wolfBurstContinueReady(rolledPause),false);
  assert.deepEqual(rolledOff.clicks,[]);assert.deepEqual(rolledOff.inputs,[]);
});

test('failed durable marker write sends no Q and consumes this request only',async()=>{
  const f=croppedAdapter({failMarkerWrite:true});const initial=await f.observe();
  await f.adapter.wolfBurstRecoveryContinue();await f.adapter.sleep(450);const active=await f.observe();
  assert.equal(f.adapter.wolfBurstRecoveryQReady(active),true);
  await assert.rejects(f.adapter.wolfBurstRecoveryQ(),/no Q input sent/);
  assert.deepEqual(f.inputs,[]);assert.equal(f.markers.size,0);
  await assert.rejects(f.adapter.wolfBurstRecoveryQ(),/one-shot/);
});

test('one same-frame party OCR crop can recover Kaeya and Trial before Q authorization',async()=>{
  const f=croppedAdapter({dropActiveParty:true});const initial=await f.observe();
  const result=await mission.runQuestStep('wolfBurstRecovery',initial,f.adapter,f.observe);
  assert.equal(result.burstAttempts,1,result.reason);assert.equal(result.pauseVerified,true);
  assert.equal(f.partyCrops.length,2,'each fresh active observation must restore the missing party labels');assert.equal(result.partyReadRetries,0);
});

test('Q keyDown failure still releases Q and permanently consumes this request attempt',async()=>{
  const f=croppedAdapter({throwQ:true});const initial=await f.observe();
  await f.adapter.wolfBurstRecoveryContinue();await f.adapter.sleep(450);const active=await f.observe();
  assert.equal(f.adapter.wolfBurstRecoveryQReady(active),true,JSON.stringify({hud:active.hud,ocr:active.ocr,base:f.context.actOneWolfBurstRecoveryBase(active,f.now(),.3),q:f.context.actOneWolfBurstRecoveryQHud(active,f.now(),.3),retry:f.adapter.wolfBurstRecoveryRetrySafe(active)}));
  await assert.rejects(f.adapter.wolfBurstRecoveryQ(),/simulated keyDown failure/);
  assert.deepEqual(f.inputs.map(x=>x.slice(0,2)),[['down','VK_Q'],['up','VK_Q']]);
  assert.equal(f.adapter.events().filter(e=>e.type==='wolfBurstRecoveryQAttempt').length,1);
  await assert.rejects(f.adapter.wolfBurstRecoveryQ(),/one-shot/);
});

test('missing Q OCR, low HP, wrong max HP, stale pause, and lost focus stop before input',async t=>{
  const cases=[
    {name:'missing bottom-row Q',options:{withQ:false}},
    {name:'below thirty percent',options:{health:'400/1427'}},
    {name:'wrong captured max HP',options:{health:'775/1500'}},
    {name:'prior Q attempt',options:{priorQ:true}}
  ];
  for(const scenario of cases) await t.test(scenario.name,async()=>{
    const f=croppedAdapter(scenario.options),initial=await f.observe();
    const result=await mission.runQuestStep('wolfBurstRecovery',initial,f.adapter,f.observe);
    assert.equal(result.burstAttempts,0);assert.deepEqual(f.inputs,[]);
  });
  const stale=croppedAdapter();const pause=await stale.observe();pause.timestamp-=1001;
  const staleResult=await mission.runQuestStep('wolfBurstRecovery',pause,stale.adapter,stale.observe);
  assert.equal(staleResult.continueAttempts,0);assert.deepEqual(stale.clicks,[]);
  const unfocused=croppedAdapter();const current=await unfocused.observe();unfocused.setFocus(false);
  assert.throws(()=>unfocused.adapter.wolfBurstContinueReady(current),/foreground/);
  assert.deepEqual(unfocused.clicks,[]);
});

test('party OCR retries at most twice only while safe and within five-second pre-Q bound',async()=>{
  let now=1000,reads=0,q=0,continueCount=0,escape=0;const session='wolf';
  const pause={session,frameId:1,timestamp:now,map:null,hud:{health:{current:775,max:1427}}};
  function active(frameId,patch={}) {return {session,frameId,timestamp:now,map:null,hud:{health:{current:775,max:1427}},...patch};}
  const api={now:()=>now,checkStop(){},sleep:async ms=>{now+=ms;},wolfBurstContinueReady:()=>true,
    wolfBurstRecoveryContinue:()=>{continueCount++;},wolfBurstRecoveryQReady:()=>false,
    wolfBurstRecoveryRetrySafe:()=>true,wolfBurstRecoveryQ:async()=>{q++;},wolfBurstRecoveryPauseReady:()=>true,
    wolfBurstRecoveryEscape:async()=>{escape++;},wolfBurstRecoveryPauseVerified:()=>true};
  const retryResult=await mission.runQuestStep('wolfBurstRecovery',pause,api,async()=>{reads++;return active(reads+1);});
  assert.equal(retryResult.partyReadRetries,2);assert.equal(retryResult.burstAttempts,0);
  assert.equal(continueCount,1);assert.equal(q,0);assert.equal(escape,0);assert.equal(reads,3);

  now=1000;reads=0;const slowApi={...api,now:()=>now,sleep:async ms=>{now+=ms;},wolfBurstRecoveryContinue:()=>{},
    wolfBurstRecoveryRetrySafe:()=>true,wolfBurstRecoveryQReady:()=>false};
  const slow=await mission.runQuestStep('wolfBurstRecovery',pause,slowApi,async()=>{reads++;now+=1800;return active(reads+1);});
  assert.equal(slow.burstAttempts,0);assert.match(slow.reason,/deadline/);assert.equal(reads,3);
});

test('ambiguous HUD after Q stops without Escape and leaves pause unverified',async()=>{
  let now=1000,reads=0,escape=0;const session='wolf';
  const pause={session,frameId:1,timestamp:now};
  const active={session,frameId:2,timestamp:now,hud:{health:{current:800,max:1427}}};
  const api={now:()=>now,checkStop(){},sleep:async ms=>{now+=ms;},wolfBurstContinueReady:()=>true,wolfBurstRecoveryContinue:()=>{},
    wolfBurstRecoveryQReady:()=>true,wolfBurstRecoveryQ:async()=>{},wolfBurstRecoveryPauseReady:()=>false,
    wolfBurstRecoveryEscape:async()=>{escape++;},wolfBurstRecoveryPauseVerified:()=>false};
  const result=await mission.runQuestStep('wolfBurstRecovery',pause,api,async()=>{reads++;return {...active,frameId:reads+1,timestamp:now};});
  assert.equal(result.burstAttempts,1);assert.equal(result.pauseAttempts,0);assert.equal(result.pauseVerified,false);
  assert.equal(escape,0);assert.match(result.reason,/ambiguous.*no further input/);
});
