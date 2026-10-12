const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=70,height=24)=>({text,x,y,width,height});

function harness({entry=true,permit='valid',active='safe',foreground=true,seed=true}={}) {
  let now=3000000,frame=60,phase='pause',focus=foreground;
  const clicks=[],keys=[];
  let permitData=permit==='valid'?{kind:'reviveTrialKaeya',session:'wolf',frameId:60,createdAt:now-1000}:null;
  if(permit==='wrongKind')permitData={kind:'other',session:'wolf',frameId:60,createdAt:now-1000};
  if(permit==='expired')permitData={kind:'reviveTrialKaeya',session:'wolf',frameId:60,createdAt:now-120001};
  if(permit==='wrongFrame')permitData={kind:'reviveTrialKaeya',session:'wolf',frameId:59,createdAt:now-1000};
  if(permit==='used')permitData={kind:'reviveTrialKaeya',session:'wolf',frameId:60,createdAt:now-1000,usedAt:0};
  const entryReceipt={id:'entry-1',session:'wolf',mission:'questStep',status:'completed',timestamp:now-500,
    details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},
      inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:2,startedAt:now-600}]}};
  function rows() {
    if(phase==='pause')return [row('Continue Challenge',831,399,287,40),row('Leave Domain?',864,640,221,36)];
    const out=[row('Kaeya',1664,401),row('Amber',1664,485),row('E',1778,1025),row('Q',1840,1025),row('739/1055',906,1002,100,20)];
    if(active==='wrongParty')out.splice(0,1);
    if(active==='dialogue')out.push(row('Auto',50,40),row('Talk to Kaeya about the next challenge',700,900,400,30));
    return out;
  }
  const context={Date:class extends Date{static now(){return now;}},
    genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:focus,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='wolf-revive-kaeya.json'?permitData!==null:false,
      readTextSync:p=>p==='wolf-revive-kaeya.json'?JSON.stringify(permitData):p==='reports/wolf.json'?JSON.stringify(entry?[entryReceipt]:[]):fs.readFileSync(path.join(root,p),'utf8'),
      writeTextSync:(p,value)=>{if(p==='wolf-revive-kaeya.json')permitData=JSON.parse(value);return true;},writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=[];a.count=0;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},
      RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows().map(x=>({...x}));a.count=a.length;return a;},
      deriveCrop:()=>({srcMat:{resize:()=>({})},dispose(){}}),dispose(){}}),
    keyDown:k=>keys.push(['down',k]),keyUp:k=>keys.push(['up',k]),
    click:(x,y)=>{clicks.push([x,y]);phase='active';},moveMouseBy(){},sleep:async ms=>{now+=ms;},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission:'questStep',step:'wolfReviveKaeyaPrompt',session:'wolf',id:'revive-1',createdAt:now-10,expectedFrameId:60});
  let pause={session:'wolf',frameId:60,timestamp:now,map:null,ocr:[row('Continue Challenge',831,399,287,40),row('Leave Domain?',864,640,221,36)],
    hud:{world:false,auto:false,dialogueReady:false,choice:false,climbing:false,loading:false,unknownHud:false,objectiveChanged:false,
      journal:false,bigMap:false,tutorialStep:null,health:null}};
  let seedError=null;
  if(seed) {try{adapter.seedObservation(pause);}catch(e){seedError=e;}}
  else {frame++;pause=adapter.observe('wolf',frame);}
  async function observe(){frame++;const o=await adapter.observe('wolf',frame);return active==='wrongSession'&&phase==='active'?{...o,session:'other'}:o;}
  return {adapter,clicks,keys,observe,pause,permit:()=>permitData,seedError,now:()=>now,setNow:v=>now=v,setFocus:v=>{focus=v;context.genshin.isGameForeground=v;}};
}

test('one permitted canonical Continue then one released VK_3 stops for live revival-prompt inspection',async()=>{
  const h=harness();
  const result=await mission.runQuestStep('wolfReviveKaeyaPrompt',h.pause,h.adapter,h.observe);
  assert.equal(result.status,'stopped');assert.equal(result.continueAttempts,1);assert.equal(result.selectionAttempts,1);
  assert.equal(result.promptRequested,true);assert.equal(result.questComplete,false);
  assert.deepEqual(h.clicks,[[975,419]]);
  assert.deepEqual(h.keys,[['down','VK_3'],['up','VK_3']]);
  assert.equal(h.permit().usedAt!==undefined,true);
  assert.ok(h.adapter.events().some(e=>e.type==='wolfReviveKaeyaContinue'));
  assert.ok(h.adapter.events().some(e=>e.type==='wolfReviveKaeyaSelect'));
});

test('ordinary quest capture at expectedFrameId plus one is accepted without seedObservation; older frames are rejected',async()=>{
  const fresh=harness({seed:false});
  const observedPause=await fresh.pause;
  assert.equal(observedPause.frameId,61);
  const result=await mission.runQuestStep('wolfReviveKaeyaPrompt',observedPause,fresh.adapter,fresh.observe);
  assert.equal(result.continueAttempts,1);assert.equal(result.selectionAttempts,1);assert.equal(result.questComplete,false);
  assert.deepEqual(fresh.keys,[['down','VK_3'],['up','VK_3']]);
  const older=harness();
  assert.equal(older.adapter.wolfRevivePromptContinueReady({...older.pause,frameId:59}),false);
  assert.deepEqual(older.clicks,[]);assert.equal(older.permit().usedAt,undefined);
});

test('missing, wrong-kind, expired, and wrong-frame permits block before Continue',async()=>{
  for(const permit of ['missing','wrongKind','expired','wrongFrame','used']) {
    const h=harness({permit});
    assert.match(String(h.seedError),/revival permit/);
    assert.deepEqual(h.clicks,[]);assert.deepEqual(h.keys,[]);
  }
});

test('same-session Wolf entry proof is required before the permit can be consumed',async()=>{
  const h=harness({entry:false});
  assert.match(String(h.seedError),/entry required/);
  assert.equal(h.permit().usedAt,undefined);assert.deepEqual(h.clicks,[]);
});

test('fresh post-Continue frame needs living Amber, both party anchors, and positive grounded controls',async()=>{
  const h=harness({active:'wrongParty'});
  const result=await mission.runQuestStep('wolfReviveKaeyaPrompt',h.pause,h.adapter,h.observe);
  assert.equal(result.status,'stopped');assert.equal(result.continueAttempts,1);assert.equal(result.selectionAttempts,0);
  assert.equal(result.promptRequested,false);assert.deepEqual(h.keys,[]);assert.equal(h.clicks.length,1);
  const dialogue=harness({active:'dialogue'});
  const blocked=await mission.runQuestStep('wolfReviveKaeyaPrompt',dialogue.pause,dialogue.adapter,dialogue.observe);
  assert.equal(blocked.selectionAttempts,0);assert.deepEqual(dialogue.keys,[]);
  const wrongSession=harness({active:'wrongSession'});
  const foreign=await mission.runQuestStep('wolfReviveKaeyaPrompt',wrongSession.pause,wrongSession.adapter,wrongSession.observe);
  assert.equal(foreign.selectionAttempts,0);assert.equal(foreign.promptRequested,false);assert.deepEqual(wrongSession.keys,[]);
});

test('stale initial pause and lost foreground prevent Continue or selection',async()=>{
  const stale=harness();stale.pause.timestamp-=1001;
  const staleResult=await mission.runQuestStep('wolfReviveKaeyaPrompt',stale.pause,stale.adapter,stale.observe);
  assert.equal(staleResult.continueAttempts,0);assert.deepEqual(stale.clicks,[]);
  const unfocused=harness();unfocused.setFocus(false);
  await assert.rejects(mission.runQuestStep('wolfReviveKaeyaPrompt',unfocused.pause,unfocused.adapter,unfocused.observe),/foreground focus/);
  assert.deepEqual(unfocused.clicks,[]);assert.deepEqual(unfocused.keys,[]);
});
