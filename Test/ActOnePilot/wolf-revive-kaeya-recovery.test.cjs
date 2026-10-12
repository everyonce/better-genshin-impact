const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const bgi=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js');
const recovery=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/recovery.js');
const root=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const row=(text,x,y,width=70,height=24)=>({text,x,y,width,height});

function deadTrial({timestamp=4000000,session='wolf',flags={}}={}) {
  return {session,frameId:35,timestamp,map:null,ocr:[row('Kaeya',1690,479,78,36),row('Amber',1664,401,87,23),
    row('E',1778,1025),row('Q',1840,1025),row('633/1055',906,1002,100,20)],
    hud:{world:false,groundControls:true,climbing:false,journal:false,bigMap:false,dialogueReady:false,choice:false,
      tutorialStep:null,auto:false,loading:false,unknownHud:false,objectiveChanged:false,interact:false,enemyBars:[],health:{current:633,max:1055},...flags}};
}
function modalRows({item='Teyvat Fried Egg',count='9'}={}) {
  return [row('Use revival item',793,223,329,50),row(count,950,435,17,21),row(item,831,476,255,47),
    row('Revives a character and restores 100 HP.',682,536,551,29),row('Cancel',692,779,112,43),row('Confirm',1140,784,129,37),
    row('Kaeya',1690,479,78,36),row('Trial',1813,459,48,32),row('Amber',1664,401,87,23),row('633/1055',906,1002,100,20)];
}
function activeRows(kind) {
  if(kind==='amber')return deadTrial().ocr;
  return [row('Kaeya',1690,479,78,36),row('Trial',1813,459,48,32),row('Amber',1664,401,87,23),
    row('E',1778,1025),row('Q',1840,1025),row('100/1427',906,1002,100,20)];
}
function harness({permit='valid',prefix=true,entry=true,modal='valid',outcome='revived',foreground=true,continuation=false}={}) {
  let now=4000000,frame=continuation?38:34,phase=continuation?'modal':'amber',currentRows=null,focus=foreground;
  const keys=[],clicks=[];
  let permitData=permit==='valid'?{kind:'reviveTrialKaeyaRecovery',session:'wolf',frameId:34,createdAt:now-500}:null;
  if(permit==='used')permitData={kind:'reviveTrialKaeyaRecovery',session:'wolf',frameId:34,createdAt:now-500,usedAt:now-1};
  if(permit==='wrongKind')permitData={kind:'reviveTrialKaeya',session:'wolf',frameId:34,createdAt:now-500};
  if(permit==='wrongFrame')permitData={kind:'reviveTrialKaeyaRecovery',session:'wolf',frameId:33,createdAt:now-500};
  if(permit==='wrongSession')permitData={kind:'reviveTrialKaeyaRecovery',session:'other',frameId:34,createdAt:now-500};
  if(permit==='expired')permitData={kind:'reviveTrialKaeyaRecovery',session:'wolf',frameId:34,createdAt:now-120001};
  const entryReceipt={id:'entry-1',session:'wolf',mission:'questStep',status:'completed',timestamp:now-3000,
    details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},
      inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',frameId:2,startedAt:now-3100}]}};
  const prefixReceipt={id:'revive-prefix',session:'wolf',mission:'questStep',status:'stopped',timestamp:now-500,frameId:31,
    details:{result:{step:'wolfReviveKaeyaPrompt',continueAttempts:1,selectionAttempts:1,promptRequested:true,questComplete:false,frameId:31},inputEvents:[
      {type:'wolfReviveKaeyaContinue',frameId:28,startedAt:now-900,finishedAt:now-890},
      {type:'wolfReviveKaeyaSelect',key:'VK_3',frameId:29,startedAt:now-810,finishedAt:now-730},
      {type:'key',key:'VK_3',durationMs:60,frameId:29,startedAt:now-800,finishedAt:now-740}]}};
  let reports=[...(entry?[entryReceipt]:[]),...(prefix?[prefixReceipt]:[])];
  const failedRecovery={id:'failed-recover',session:'wolf',mission:'recover',status:'failed',timestamp:now-100,frameId:38,
    details:{result:{reviveSelectionAttempts:1,reviveConfirmAttempts:0,reviveModalVerified:false,questComplete:false,sourceFrameId:35,frameId:38},inputEvents:[
      {type:'wolfReviveKaeyaRecoverySelect',key:'VK_3',frameId:35,startedAt:now-1900,finishedAt:now-1820},
      {type:'key',key:'VK_3',durationMs:60,frameId:35,startedAt:now-1880,finishedAt:now-1820}]}};
  let selectionReceipt=continuation?{...failedRecovery,details:JSON.parse(JSON.stringify(failedRecovery.details))}:null;
  if(continuation){permitData={kind:'reviveTrialKaeyaRecovery',session:'wolf',frameId:34,createdAt:now-3000,usedAt:now-2000,requestId:'failed-recover'};reports.push(failedRecovery);}
  function rows(){if(phase==='amber')return deadTrial().ocr;if(phase==='modal')return modalRows(modal);return activeRows(phase);}
  const context={Date:class extends Date{static now(){return now;}},genshin:{isRemoteDesktopSession:true,windowsSessionId:7,isGameForeground:focus,getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='wolf-revive-kaeya-recovery.json'?permitData!==null:p==='receipts/wolf/failed-recover.json'?!!selectionReceipt:false,
      readTextSync:p=>p==='wolf-revive-kaeya-recovery.json'?JSON.stringify(permitData):p==='reports/wolf.json'?JSON.stringify(reports):p==='receipts/wolf/failed-recover.json'?JSON.stringify(selectionReceipt):fs.readFileSync(path.join(root,p),'utf8'),
      writeTextSync:(p,v)=>{if(p==='wolf-revive-kaeya-recovery.json')permitData=JSON.parse(v);return true;},writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},ImageRegion:class{constructor(mat){this.mat=mat;this.width=1920;this.height=1080;}findMulti(){const a=this.mat&&this.mat.cropKey==='health'?[row(phase==='revived'?'100/1427':'633/1055',5,5,280,50)]:[];a.count=a.length;return a;}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}},Scalar:class{},RetrievalModes:{External:0},ContourApproximationModes:{ApproxSimple:0},Cv2:{boundingRect:x=>x,contourArea:()=>0}}},
    captureGameRegion:()=>({width:1920,height:1080,srcMat:{},findMulti:()=>{const a=rows().map(x=>({...x}));a.count=a.length;return a;},deriveCrop:x=>({srcMat:{resize:()=>({cropKey:x===900?'health':'other'})},dispose(){}}),dispose(){}}),
    keyDown:k=>{keys.push(['down',k]);if(k==='VK_3')phase='modal';},keyUp:k=>keys.push(['up',k]),
    click:(x,y)=>{clicks.push([x,y]);phase=outcome==='revived'?'revived':outcome==='amber'?'amber':'unknown';},moveMouseBy(){},sleep:async ms=>{now+=ms;},log:{info(){}}};
  if(modal==='wrongItem'||modal==='wrongCount') {
    const savedRows=rows;
    currentRows=modalRows(modal==='wrongItem'?{item:'Sweet Madame'}:{count:'8'});
    // Keep the per-frame fixture switch explicit and deterministic.
    Object.defineProperty(context,'_modalRows',{value:currentRows});
    if(modal==='wrongItem'||modal==='wrongCount') phase='amber';
  }
  const originalCapture=context.captureGameRegion;
  context.captureGameRegion=()=>{
    const img=originalCapture();
    const find=img.findMulti;
    img.findMulti=ro=>{const a=(phase==='modal'&&context._modalRows?context._modalRows:rows()).map(x=>({...x}));a.count=a.length;return a;};
    return img;
  };
  vm.runInNewContext(fs.readFileSync(path.join(root,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(7);
  adapter.beginMission({mission:'recover',session:'wolf',id:continuation?'recover-continuation':'recover-1',createdAt:now-10,expectedFrameId:continuation?38:34});
  async function observe(){frame++;return adapter.observe('wolf',frame);}
  return {adapter,observe,keys,clicks,permit:()=>permitData,now:()=>now,setNow:v=>now=v,setFocus:v=>{focus=v;context.genshin.isGameForeground=v;},
    initial:async()=>observe(),setReports:v=>{reports=v;},addReport:v=>{reports.push(v);},setReceipt:v=>{selectionReceipt=v;}};
}

test('modal witness requires unique exact egg, count nine, description, and button geometry',()=>{
  const o={...deadTrial(),frameId:40,ocr:modalRows()};
  assert.deepEqual(bgi.wolfReviveEggTarget(o,4000000),{x:1205,y:803,label:'Teyvat Fried Egg',quantity:9});
  for(const bad of [
    {...o,ocr:modalRows({item:'Sweet Madame'})},{...o,ocr:modalRows({count:'8'})},
    {...o,ocr:[...o.ocr,row('Confirm',1145,784,129,37)]},
    {...o,ocr:o.ocr.filter(r=>r.text!=='Teyvat Fried Egg')},
    {...o,ocr:[...o.ocr,row('Confirm',1200,900,129,37)]}
  ])assert.equal(bgi.wolfReviveEggTarget(bad,4000000),null);
  assert.equal(bgi.wolfReviveItemModalVisible(o),true);
  assert.equal(bgi.wolfDomainHud({...o,hud:{...o.hud,health:{current:900,max:1427}}},4000000,0),false);
  assert.equal(bgi.wolfPauseOnlyHud({...o,hud:{...o.hud,health:{current:900,max:1427}}},4000000),false);
  assert.equal(bgi.wolfDeadTrialPauseOnlyHud(o,4000000,'wolf'),false);
});

test('recovery confirms one exact witnessed egg and stops on fresh revived Kaeya without Escape',async()=>{
  const h=harness(),initial=await h.initial();
  const result=await recovery.run(initial,h.adapter,h.observe);
  assert.equal(result.status,'completed',JSON.stringify(result));assert.equal(result.reviveSelectionAttempts,1);assert.equal(result.reviveConfirmAttempts,1);
  assert.equal(result.revivalVerified,true);assert.equal(result.questComplete,false);
  assert.deepEqual(h.keys,[['down','VK_3'],['up','VK_3']]);assert.deepEqual(h.clicks,[[1205,803]]);
  assert.equal(h.permit().usedAt!==undefined,true);
  assert.ok(h.adapter.events().some(e=>e.type==='wolfReviveKaeyaRecoveryConfirm'&&e.quantity===9));
});

test('already-open exact modal resumes from immutable failed selection receipt and persists one confirm marker',async()=>{
  const h=harness({continuation:true}),initial=await h.initial();
  assert.equal(initial.hud.groundControls,false,'modal fixture must model occluded ground controls');
  assert.equal(h.adapter.wolfReviveRecoveryConfirmOnlyReady(initial),true);
  const result=await recovery.run(initial,h.adapter,h.observe);
  assert.equal(result.status,'completed',JSON.stringify(result));assert.equal(result.reviveSelectionAttempts,0);assert.equal(result.reviveConfirmAttempts,1);
  assert.deepEqual(h.keys,[]);assert.deepEqual(h.clicks,[[1205,803]]);
  assert.equal(h.permit().confirmationRequestId,'recover-continuation');assert.equal(Number.isFinite(h.permit().confirmationAttemptedAt),true);
});

test('confirm-only continuation rejects missing entry or prefix, receipt mismatch, and any later session input',async()=>{
  for(const options of [{entry:false},{prefix:false}]) {
    const missing=harness({continuation:true,...options}),missingFrame=await missing.initial();
    assert.equal(missing.adapter.wolfReviveRecoveryConfirmOnlyReady(missingFrame),false);
    assert.deepEqual(missing.clicks,[]);assert.deepEqual(missing.keys,[]);
  }
  const mismatch=harness({continuation:true}),mismatchFrame=await mismatch.initial();
  mismatch.setReceipt({...mismatchFrame,details:{result:{reviveSelectionAttempts:1,reviveConfirmAttempts:0,reviveModalVerified:false,questComplete:false}}});
  assert.equal(mismatch.adapter.wolfReviveRecoveryConfirmOnlyReady(mismatchFrame),false);
  assert.deepEqual(mismatch.clicks,[]);
  const later=harness({continuation:true}),laterFrame=await later.initial();
  later.addReport({id:'later-input',session:'wolf',mission:'questStep',status:'stopped',timestamp:later.now()+100,
    details:{inputEvents:[{type:'key',key:'VK_W',startedAt:later.now()+50}]}});
  assert.equal(later.adapter.wolfReviveRecoveryConfirmOnlyReady(laterFrame),false);
  assert.deepEqual(later.clicks,[]);
});

test('missing, reused, expired, wrong-kind, wrong-frame, or wrong-session permit sends no input',async()=>{
  for(const permit of ['missing','used','expired','wrongKind','wrongFrame','wrongSession']) {
    const h=harness({permit}),initial=await h.initial();
    const result=await recovery.run(initial,h.adapter,h.observe);
    assert.deepEqual(h.keys,[],permit);assert.deepEqual(h.clicks,[],permit);
    assert.notEqual(result.reviveConfirmAttempts,1,permit);
  }
});

test('recovery requires authoritative entry and a real bounded VK_3 prefix receipt',async()=>{
  for(const options of [{entry:false},{prefix:false}]) {
    const h=harness(options),initial=await h.initial();
    await recovery.run(initial,h.adapter,h.observe);
    assert.deepEqual(h.keys,[]);assert.deepEqual(h.clicks,[]);
  }
  const malformed=harness(),initial=await malformed.initial();
  malformed.setReports([{id:'entry-1',session:'wolf',mission:'questStep',status:'completed',timestamp:3997000,
    details:{result:{step:'wolfPartyStart',label:'Deep Within the Temple of the Wolf'},inputEvents:[{type:'wolfPartyStart',label:'Deep Within the Temple of the Wolf',startedAt:3996900}]}},
    {id:'revive-prefix',session:'wolf',mission:'questStep',status:'stopped',timestamp:3999500,frameId:31,
      details:{result:{step:'wolfReviveKaeyaPrompt',continueAttempts:1,selectionAttempts:1,promptRequested:true,questComplete:false,frameId:31},
        inputEvents:[{type:'wolfReviveKaeyaContinue',frameId:28,startedAt:3999100},{type:'wolfReviveKaeyaSelect',key:'VK_3',frameId:29,startedAt:3999190,finishedAt:3999270}]}}]);
  await recovery.run(initial,malformed.adapter,malformed.observe);
  assert.deepEqual(malformed.keys,[]);assert.deepEqual(malformed.clicks,[]);
});

test('wrong modal item or quantity and stale/focus loss never reach Confirm',async()=>{
  for(const modal of ['wrongItem','wrongCount']) {
    const h=harness({modal}),initial=await h.initial();
    const result=await recovery.run(initial,h.adapter,h.observe);
    assert.equal(result.reviveConfirmAttempts,0);assert.deepEqual(h.clicks,[]);
    assert.deepEqual(h.keys,[['down','VK_3'],['up','VK_3']]);
  }
  const stale=harness(),old=await stale.initial();stale.setNow(stale.now()+1001);
  assert.equal(stale.adapter.wolfReviveRecoveryReady(old),false);assert.deepEqual(stale.keys,[]);
  const unfocused=harness();unfocused.setFocus(false);
  await assert.rejects(unfocused.initial(),/foreground focus/);assert.deepEqual(unfocused.keys,[]);assert.deepEqual(unfocused.clicks,[]);
});

test('Amber remaining active after Confirm is not reported as Kaeya revival',async()=>{
  const h=harness({outcome:'amber'}),initial=await h.initial();
  const result=await recovery.run(initial,h.adapter,h.observe);
  assert.equal(result.status,'stopped');assert.equal(result.revivalVerified,false);assert.equal(result.activeAmberSafe,true);
  assert.equal(result.questComplete,false);assert.deepEqual(h.keys,[['down','VK_3'],['up','VK_3']]);
  assert.equal(h.clicks.length,1);
});
