'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const dialogue=require(path.join(dir,'statue-dialogue.js'));
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'combat-statue-worship.fixture.json'),'utf8'));
const intro=JSON.parse(fs.readFileSync(path.join(__dirname,'combat-statue-dialogue.fixture.json'),'utf8')).observation;
const copy=o=>JSON.parse(JSON.stringify(o));
const state=o=>({session:o.session,purpose:'inventory-protection',lastInputFrame:-1,afterInputAt:null,advanceAttempted:false,leaveAttempted:false,worshipCloseAttempted:false});

test('retained actual Worship frame has exact original-time close permission without fabricated HUD fields',()=>{
  const o=copy(fixture.observation);assert.equal(o.hud.loading,undefined);assert.equal(o.hud.unknownHud,undefined);
  assert.deepEqual(dialogue.recoveryAction(o,o.timestamp,o.session,state(o)),{kind:'worship-close',key:'VK_ESCAPE',durationMs:60});
  assert.equal(dialogue.recoveryAction(o,o.hud.captureStamp.capturedAt+1001,o.session,state(o)),null);
  assert.equal(dialogue.action(o,o.timestamp,o.session,{...state(o),armed:true,interactionAttempted:true,lastInputFrame:0}),null);
});
for(const [name,change] of [
  ['legacy bare zero',o=>o.ocr.find(r=>r.text==='x 0').text='0'],
  ['positive owned count',o=>o.ocr.find(r=>r.text==='x 0').text='x 1'],
  ['different level',o=>o.ocr.find(r=>r.text==='3').text='2'],
  ['different offering requirement',o=>o.ocr.find(r=>r.text==='Anemoculus 0/4').text='Anemoculus 0/2'],
  ['different stamina',o=>o.ocr.find(r=>r.text==='Current Stamina Limit: 114/240').text='Current Stamina Limit: 107/240'],
  ['missing required label',o=>o.ocr=o.ocr.filter(r=>r.text!=='Required Anemoculus')],
  ['missing panel title',o=>o.ocr=o.ocr.filter(r=>r.text!=='Worship Statue')],
  ['duplicate panel title',o=>o.ocr.push(copy(o.ocr.find(r=>r.text==='Worship Statue')))],
  ['misplaced zero',o=>o.ocr.find(r=>r.text==='x 0').x=700],
  ['foreign account',o=>o.ocr.find(r=>r.text.startsWith('UID')).text='UID: 693306811'],
  ['missing account',o=>o.ocr=o.ocr.filter(r=>!r.text.startsWith('UID'))],
  ['conflicting complete account',o=>o.ocr.push({text:'UID: 693306811',x:500,y:400,width:180,height:25})],
  ['foreign capture session',o=>o.hud.captureStamp.session='foreign'],
  ['wrong capture frame',o=>o.hud.captureStamp.frameId++],
  ['wrong capture source',o=>o.hud.captureStamp.source='publication'],
  ['fresh publication with stale capture',o=>o.hud.captureStamp.capturedAt=o.timestamp-1001],
  ['visible health',o=>o.hud.health={current:719,max:1001}],
  ['world controls',o=>o.hud.groundControls=true],
  ['map',o=>o.map={x:1,y:2}],
  ['confirmation text',o=>o.ocr.push({text:'Confirm',x:700,y:500,width:100,height:30})],
  ['loading',o=>o.hud.loading=true],['malformed loading',o=>o.hud.loading='false'],
  ['unknown HUD',o=>o.hud.unknownHud=true],['malformed unknown HUD',o=>o.hud.unknownHud=0]
])test('pure Worship close refuses '+name,()=>{const o=copy(fixture.observation);change(o);assert.equal(dialogue.recoveryAction(o,o.timestamp,o.session,state(o)),null);});
test('Worship action requires cleanup purpose, explicit unused latch and post-input source',()=>{
  const o=copy(fixture.observation),s=state(o);
  for(const mutation of [v=>v.purpose='healer-intro',v=>v.worshipCloseAttempted=true,v=>delete v.worshipCloseAttempted,v=>v.lastInputFrame=o.frameId,v=>v.afterInputAt=o.hud.captureStamp.capturedAt]){
    const v={...s};mutation(v);assert.equal(dialogue.recoveryAction(o,o.timestamp,o.session,v),null);
  }
});

// Reuse real adapter/Engine code; only platform image, time and input I/O are inert.
const box={require:n=>n==='node:test'?()=>{}:require(n),module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'combat-statue-retreat.test.cjs'),'utf8')+'\nmodule.exports={actual,row,party};',box);
const row=box.module.exports.row,party=box.module.exports.party;
function actual(options={}){
  const world=[row('LY.',80,250),row('E',1550,1005,25,25),row('Q',1660,1005,25,25),row('719/1001',900,1002,120,24),...party(),row('Statue of The Seven',1200,550,280,30)];
  const f=box.module.exports.actual({fixture:{step:'combatStatueHeal',blockPauseB:!!options.blockInventory,mapPosition:{x:-1321.474,y:2566.115},fieldRowsSequence:[world]}});
  let phase=options.owned?'inventory':'worship',offset=0,warm=0,request=null;
  const clicks=[],clock=f.context.Date.now.bind(f.context.Date),capture=f.context.captureGameRegion,down=f.context.keyDown;
  f.context.Date.now=()=>clock()+offset;
  if(!options.owned)f.setScreen('field');
  Object.defineProperty(f.context.genshin,'LazyNavigationInstance',{configurable:true,get(){warm++;return {Value:{}};}});
  f.context.captureGameRegion=()=>{
    const image=capture();offset+=25;
    if(['worship','intro','choices'].includes(phase)){
      let rows=(phase==='worship'?fixture.observation.ocr:intro.ocr).map(r=>({...r}));
      if(phase==='choices')rows.push(row("Statue's Blessing",1260,570,301,35),row('Leave',1324,640,100,35));
      if(options.mutateRows)rows=options.mutateRows(rows,phase);
      image.findMulti=ro=>{const found=rows.filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h);found.count=found.length;return found;};
    }
    return image;
  };
  f.context.keyDown=key=>{
    down(key);
    if(key==='VK_ESCAPE'){
      if(phase==='inventory'){phase='world';f.setScreen('field');}
      else if(phase==='worship'&&!options.stayWorship){phase=options.closeTo||'intro';f.setScreen('field');}
    }else if(key==='VK_F'){phase='worship';f.setScreen('field');}
    else if(key==='VK_SPACE'){phase='choices';f.setScreen('field');}
    else if(key==='VK_B'&&!options.blockInventory){phase='inventory';f.setScreen('inventory');}
  };
  f.context.click=(x,y)=>{
    clicks.push({x,y,phase,at:f.context.Date.now()});
    if(phase!=='choices'||x!==1374||y!==657.5)throw Error('Only exact Leave is implemented by the inert test');
    phase='world';f.setScreen('field');
  };
  f.context.genshin.getCameraOrientation=()=>0;
  const engineRun=async()=>{
    vm.runInNewContext(fs.readFileSync(path.join(dir,'engine.js'),'utf8'),f.context);
    vm.runInNewContext(fs.readFileSync(path.join(dir,'mission.js'),'utf8'),f.context);
    const engine=f.context.ActOnePilot.create(f.adapter,{session:'lion-adapter-test',enableInput:true});await engine.observe();
    request={id:'worship-engine-1',session:'lion-adapter-test',mission:'questStep',step:'combatStatueHeal',createdAt:f.context.Date.now(),expectedFrameId:engine.getFrame()};
    await engine.process(request,()=>f.context.ActOneMission);
    return JSON.parse(f.getVirtualFiles().get(`receipts/lion-adapter-test/${request.id}.json`));
  };
  return {...f,clicks,engineRun,getRequest:()=>copy(request),getWarm:()=>warm,getPhase:()=>phase,setPhase:value=>{phase=value;f.setScreen(value==='inventory'?'inventory':'field');},age:ms=>{offset+=ms;},run:async()=>f.adapter.runCombatStatueHeal(await f.initial(),f.observe)};
}
const downs=f=>Array.from(f.inputs).filter(e=>e.kind==='down').map(e=>e.key);
for(const closeTo of ['intro','choices','world'])test('real Engine Worship entry closes once to '+closeTo+' then protects without healing',async()=>{
  const f=actual({closeTo}),r=await f.engineRun(),v=r.details.result,e=r.details.inputEvents;
  assert.equal(r.status,'stopped',JSON.stringify(r));assert.equal(v.reason,'entry-worship-panel-recovered');
  assert.equal(v.entryWorshipPanelCleanupOnly,true);assert.equal(v.entryDialogueCleanupOnly,true);assert.equal(v.entryDialogueRecovered,true);
  assert.equal(v.healthVerified,false);assert.equal(v.health,null);assert.equal(v.questComplete,false);assert.equal(v.pauseProof.kind,'inventory');
  assert.equal(v.approach.worshipCloseAttempted,true);assert.equal(f.getWarm(),0);assert.equal(f.metrics.mapCalls,0);assert.equal(f.nativeCalls.length,0);
  assert.deepEqual(downs(f),closeTo==='intro'?['VK_ESCAPE','VK_SPACE','VK_B']:['VK_ESCAPE','VK_B']);
  assert.equal(f.clicks.length,closeTo==='world'?0:1);
  const entry=e.find(x=>x.type==='combatStatueHealEntryWorship'),attempt=e.find(x=>x.type==='combatStatueHealDialogueAttempt'&&x.kind==='worship-close'),event=e.find(x=>x.type==='combatStatueHealWorshipClose'),protect=e.find(x=>x.type==='pauseProtectionStarted');
  assert.ok(entry&&attempt&&event&&protect);assert.equal(attempt.worshipCloseAttempted,true);assert.equal(event.authority,'entry-cleanup');assert.equal(event.worldFrameId,null);assert.equal(event.entryFrameId,entry.source.frameId);
  assert.ok(e.indexOf(protect)<e.indexOf(attempt)&&e.indexOf(attempt)<e.indexOf(event));assert.ok(event.startedAt>=protect.startedAt&&event.startedAt<protect.startedAt+18000);
  assert.ok(event.startedAt-event.sourceCapturedAt<=1000);assert.equal(event.key,'VK_ESCAPE');assert.equal(event.durationMs,60);
  assert.equal(e.filter(x=>x.type==='key'&&x.key==='VK_ESCAPE').length,1);
  assert.ok(!e.some(x=>/OwnedWorld|BlessingChoice|LisaPortrait|HealPrepareNavigation|HealForward|HealTurn/.test(x.type)));
  const source=JSON.parse(f.getVirtualFiles().get(`observations/lion-adapter-test/frame-${String(event.frameId).padStart(4,'0')}.json`));
  assert.equal(source.hud.captureStamp.capturedAt,event.sourceCapturedAt);assert.equal(source.timestamp,event.sourceTimestamp);assert.ok(source.ocr.some(x=>x.text==='x 0'));
  for(const x of e.filter(x=>x.type==='combatStatueHealIntroAdvance'||x.type==='combatStatueHealDialogueLeave'))assert.ok(x.sourceCapturedAt>event.finishedAt);
});
test('real owned-F healer may close unexpected Worship only in its guardian and never reports healing',async()=>{
  const f=actual({owned:true,closeTo:'world'}),r=await f.engineRun(),v=r.details.result,e=r.details.inputEvents;
  assert.equal(r.status,'stopped',JSON.stringify(r));assert.equal(v.healthVerified,false);assert.equal(v.pauseProof.kind,'inventory');
  assert.equal(v.approach.worshipCloseAttempted,true);assert.equal(v.entryWorshipPanelCleanupOnly,undefined);
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_F','VK_ESCAPE','VK_B']);
  const close=e.find(x=>x.type==='combatStatueHealWorshipClose');assert.equal(close.authority,'owned-healer');assert.ok(close.worldFrameId<close.frameId);assert.equal(close.entryFrameId,null);
  assert.ok(e.indexOf(e.find(x=>x.type==='pauseProtectionStarted'))<e.indexOf(close));assert.equal(f.clicks.length,0);
});
test('unchanged Worship after Escape cannot repeat the close or spend a second guardian Escape',async()=>{
  const f=actual({stayWorship:true});await assert.rejects(f.run(),/Pause protection exhausted/);
  assert.deepEqual(downs(f),['VK_ESCAPE']);assert.equal(f.adapter.events().filter(e=>e.type==='combatStatueHealDialogueAttempt').length,1);
});
for(const mode of ['write-fail','write-age','final-read-age','protector-deadline'])test('consumed Worship '+mode+' refuses input and cannot retry',async()=>{
  const f=actual(),read=f.context.file.readTextSync,write=f.context.file.writeTextSync;let persisted=false,delayed=false;
  f.context.file.writeTextSync=(p,text)=>{if(String(p).endsWith('.statue-dialogue-worship-close.json')){
    if(mode==='write-fail')return false;persisted=true;
    if(mode==='write-age')f.age(1001);if(mode==='protector-deadline')f.age(18000);
  }return write(p,text);};
  f.context.file.readTextSync=p=>{const text=read(p);if(p==='statue-dialogue.js'&&persisted&&!delayed&&mode==='final-read-age'){delayed=true;f.age(1001);}return text;};
  await assert.rejects(f.run(),/Pause protection exhausted/);assert.deepEqual(downs(f),[]);assert.equal(f.clicks.length,0);
  const attempts=f.adapter.events().filter(e=>e.type==='combatStatueHealDialogueAttempt');assert.equal(attempts.length,1);assert.equal(attempts[0].worshipCloseAttempted,true);
});
for(const [name,mutate] of [['foreign UID',rows=>rows.map(r=>String(r.text).startsWith('UID')?{...r,text:'UID: 693306811'}:r)],['positive owned count',rows=>rows.map(r=>r.text==='x 0'?{...r,text:'x 1'}:r)]])
test('actual '+name+' cannot acquire entry cleanup authority',async()=>{
  const f=actual({mutateRows:mutate}),r=await f.run();assert.equal(r.status,'stopped');assert.equal(r.healthVerified,false);assert.deepEqual(downs(f),[]);assert.equal(f.clicks.length,0);
});
test('stale public Worship source and modified private source both refuse entry',async()=>{
  for(const mutate of [o=>o.hud.captureStamp.capturedAt--,o=>{o.ocr.find(r=>r.text==='x 0').text='x 1';}]){
    const f=actual(),o=await f.initial();mutate(o);const r=await f.adapter.runCombatStatueHeal(o,f.observe);assert.equal(r.status,'stopped');assert.deepEqual(downs(f),[]);
  }
  const f=actual(),o=await f.initial();f.age(1001);const r=await f.adapter.runCombatStatueHeal(o,f.observe);assert.equal(r.status,'stopped');assert.deepEqual(downs(f),[]);
});
test('qualified journal fallback stays stopped and is never labelled inventory recovered',async()=>{
  const f=actual({closeTo:'world',blockInventory:true}),r=await f.run();assert.equal(r.status,'stopped');assert.equal(r.healthVerified,false);
  assert.equal(r.entryWorshipPanelCleanupOnly,true);assert.equal(r.entryDialogueRecovered,false);assert.equal(r.pauseProof.kind,'journal');
  assert.equal(r.reason,'entry-worship-panel-protected-without-inventory');assert.equal(downs(f).filter(k=>k==='VK_ESCAPE').length,1);
});
test('inventory-only mode still rejects Worship cleanup through the healer request',()=>{
  const f=actual(),a=f.context.createActOneAdapter(5,{inventoryUiOnlyV1:true});
  assert.throws(()=>a.beginMission({mission:'questStep',step:'combatStatueHeal',id:'x',session:'lion-adapter-test',createdAt:9000,expectedFrameId:1}),/rejects unrelated/);
});

// A pre-existing protector Escape also spends the shared key budget; a later Worship frame cannot renew it.
test('already-spent protector Escape cannot be followed by a Worship Escape',async()=>{
  const f=actual({owned:true}),resolve=f.adapter.pauseResolveKnownUi.bind(f.adapter);let injected=false;
  f.adapter.pauseResolveKnownUi=async o=>{
    if(!injected){injected=true;f.setPhase('world');await f.adapter.pauseKey(await f.observe(),'VK_ESCAPE');f.setPhase('worship');return resolve(await f.observe());}
    return resolve(o);
  };
  await assert.rejects(f.run(),/Pause protection exhausted/);
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_F','VK_ESCAPE']);
  assert.ok(!f.adapter.events().some(e=>e.type==='combatStatueHealWorshipClose'||e.kind==='worship-close'));
});
