'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const dialogue=require(path.join(dir,'statue-dialogue.js'));
const recorded=JSON.parse(fs.readFileSync(path.join(__dirname,'combat-statue-dialogue.fixture.json'),'utf8'));
const copy=o=>JSON.parse(JSON.stringify(o));
const state=o=>({session:o.session,purpose:'inventory-protection',lastInputFrame:-1,afterInputAt:null,advanceAttempted:false,leaveAttempted:false});

test('original recorded intro matches only its original capture clock and visible account',()=>{
  const o=copy(recorded.observation),s=state(o);
  assert.equal(dialogue.recoveryAction(o,o.timestamp,o.session,s).kind,'advance');
  assert.equal(dialogue.recoveryAction(o,o.hud.captureStamp.capturedAt+1001,o.session,s),null);
});
for(const [name,mutate] of [
  ['foreign UID',o=>o.ocr.find(r=>r.text.startsWith('UID')).text='UID:693306811'],
  ['missing UID',o=>o.ocr=o.ocr.filter(r=>!r.text.startsWith('UID'))],
  ['conflicting complete UID',o=>o.ocr.push({text:'UID:693306811',x:500,y:400,width:175,height:21})],
  ['wrong speaker',o=>o.ocr.find(r=>r.text==='Statue of The Seven').text='Kaeya'],
  ['stale capture fresh completion',o=>o.hud.captureStamp.capturedAt=o.timestamp-1001],
  ['foreign capture session',o=>o.hud.captureStamp.session='other'],
  ['reused capture frame',o=>o.hud.captureStamp.frameId--],
  ['world UI',o=>o.hud.world=true],['ground UI',o=>o.hud.groundControls=true],
  ['visible health',o=>o.hud.health={current:719,max:1001}],
  ['offering choice residue',o=>o.ocr.push({text:'Offer',x:1300,y:600,width:100,height:30})]
])test('new pure recovery refuses '+name,()=>{
  const o=copy(recorded.observation);mutate(o);assert.equal(dialogue.recoveryAction(o,o.timestamp,o.session,state(o)),null);
});
test('choice cleanup selects only unique Leave and normal healing cannot invoke this choice action',()=>{
  const o=copy(recorded.observation);o.hud.choice=true;o.hud.dialogueReady=false;
  o.ocr.push({text:"Statue's Blessing",x:1260,y:570,width:301,height:35},{text:'Leave',x:1324,y:640,width:100,height:35});
  const s=state(o);assert.deepEqual(dialogue.recoveryAction(o,o.timestamp,o.session,s),{kind:'leave',x:1374,y:657.5});
  s.purpose='healer-intro';assert.equal(dialogue.recoveryAction(o,o.timestamp,o.session,s),null);
  s.purpose='inventory-protection';s.leaveAttempted=true;assert.equal(dialogue.recoveryAction(o,o.timestamp,o.session,s),null);
  s.leaveAttempted=false;o.ocr.push({text:'Leave',x:1324,y:700,width:100,height:35});
  assert.equal(dialogue.recoveryAction(o,o.timestamp,o.session,s),null);
});
test('post-input frames must be distinct and captured strictly after the previous input finished',()=>{
  const o=copy(recorded.observation),s=state(o);s.lastInputFrame=o.frameId;
  assert.equal(dialogue.recoveryAction(o,o.timestamp,o.session,s),null);
  s.lastInputFrame--;s.afterInputAt=o.hud.captureStamp.capturedAt;
  assert.equal(dialogue.recoveryAction(o,o.timestamp,o.session,s),null);
  s.afterInputAt--;s.advanceAttempted=true;
  assert.equal(dialogue.recoveryAction(o,o.timestamp,o.session,s),null);
});

// Reuse the established real adapter fixture; only native host I/O is inert.
const box={require:n=>n==='node:test'?()=>{}:require(n),module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'combat-statue-retreat.test.cjs'),'utf8')+'\nmodule.exports={actual,row,party};',box);
const row=box.module.exports.row,party=box.module.exports.party;
const panelRows=JSON.parse(fs.readFileSync(path.join(__dirname,'combat-statue-panel.fixture.json'),'utf8')).panel.ocr;
function actual(options={}){
  const hp=row('719/1001',900,1002,120,24),world=[row('LY.',80,250),row('E',1550,1005,25,25),row('Q',1660,1005,25,25),hp,...party(),row('Statue of The Seven',1200,550,280,30)];
  const f=box.module.exports.actual({fixture:{step:'combatStatueHeal',blockPauseB:!!options.blockInventory,mapPosition:{x:-1321.474,y:2566.115},fieldRowsSequence:[world]}});
  let phase=options.entry||'inventory',offset=0,portraits=0,warm=0;
  const clicks=[],clock=f.context.Date.now.bind(f.context.Date),capture=f.context.captureGameRegion,down=f.context.keyDown;
  f.context.Date.now=()=>clock()+offset;
  if(options.entry)f.setScreen('field');
  Object.defineProperty(f.context.genshin,'LazyNavigationInstance',{get(){warm++;return {Value:{}};}});
  f.context.captureGameRegion=()=>{
    const image=capture();
    if(['intro','choices','panel'].includes(phase)){
      let rows=(phase==='panel'?panelRows:recorded.observation.ocr).map(r=>({...r}));
      if(phase==='choices')rows.push(row("Statue's Blessing",1260,570,301,35),row('Leave',1324,640,100,35));
      if(options.foreignUid)rows.find(r=>String(r.text).startsWith('UID')).text='UID:693306811';
      if(options.missingUid)rows=rows.filter(r=>!String(r.text).startsWith('UID'));
      if(options.extraChoice)rows.push(row('Offer',1350,720,100,35));
      image.findMulti=ro=>{const found=rows.filter(r=>r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h);found.count=found.length;return found;};
    }
    return image;
  };
  f.context.keyDown=key=>{
    down(key);
    if(key==='VK_ESCAPE'&&(phase==='inventory'||phase==='panel')){phase='world';f.setScreen('field');}
    else if(key==='VK_F'){phase='intro';f.setScreen('field');}
    else if(key==='VK_SPACE'){
      if(!options.stayIntro)phase='choices';
      if(options.stopAfterSpace)f.getVirtualFiles().set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:f.context.Date.now()}));
      if(options.expireAfterSpace)offset+=90000;
    }else if(key==='VK_B'&&!options.blockInventory){phase='inventory';f.setScreen('inventory');}
  };
  f.context.click=(x,y)=>{
    clicks.push({x,y,phase,at:f.context.Date.now()});
    if(phase==='choices'&&y>630){phase='world';f.setScreen('field');}
    else if(phase==='choices'){phase='panel';f.setScreen('field');}
    else if(phase==='panel'&&x===658&&y===160){if(++portraits===3)hp.text='1001/1001';}
    else throw Error('Unexpected exact dialogue click');
  };
  f.context.genshin.getCameraOrientation=()=>0;
  const ownedIntro=async()=>{
    const initial=await f.initial();await f.adapter.combatHealPrepareNavigation(initial);
    await f.adapter.combatHealCloseInventory(await f.observe());await f.adapter.combatHealInteract(await f.observe());
    return f.observe();
  };
  const engineRun=async()=>{
    vm.runInNewContext(fs.readFileSync(path.join(dir,'engine.js'),'utf8'),f.context);
    vm.runInNewContext(fs.readFileSync(path.join(dir,'mission.js'),'utf8'),f.context);
    const engine=f.context.ActOnePilot.create(f.adapter,{session:'lion-adapter-test',enableInput:true});await engine.observe();
    const id='dialogue-engine-1';await engine.process({id,session:'lion-adapter-test',mission:'questStep',step:'combatStatueHeal',createdAt:f.context.Date.now(),expectedFrameId:engine.getFrame()},()=>f.context.ActOneMission);
    return JSON.parse(f.getVirtualFiles().get(`receipts/lion-adapter-test/${id}.json`));
  };
  return {...f,clicks,ownedIntro,engineRun,getWarm:()=>warm,getPortraits:()=>portraits,getPhase:()=>phase,age:ms=>{offset+=ms;},
    run:async()=>f.adapter.runCombatStatueHeal(await f.initial(),f.observe)};
}
const downs=f=>Array.from(f.inputs).filter(e=>e.kind==='down').map(e=>e.key);
test('real Engine normal same-request F/intro/choice/Lisa panel succeeds and records12 revisions',async()=>{
  const f=actual(),r=await f.engineRun();assert.equal(r.status,'completed',JSON.stringify(r));
  assert.equal(r.details.result.healthVerified,true);assert.equal(r.details.result.pauseVerified,true);
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_F','VK_SPACE','VK_ESCAPE','VK_B']);
  const e=r.details.inputEvents,a=e.find(e=>e.type==='combatStatueHealIntroAdvance');
  assert.equal(a.authority,'owned-healer');assert.equal(a.entryFrameId,null);assert.ok(a.worldFrameId<a.frameId);
  assert.ok(a.startedAt-a.sourceCapturedAt<=1000);assert.equal(a.durationMs,60);
  assert.equal(Object.keys(e.find(e=>e.type==='controllerRevision').files).length,12);assert.equal(f.getPortraits(),3);
});
for(const entry of ['intro','choices'])test('real Engine '+entry+' entry only leaves and protects, never starts healing',async()=>{
  const f=actual({entry}),r=await f.engineRun(),v=r.details.result;
  assert.equal(r.status,'stopped',JSON.stringify(r));assert.equal(v.reason,'entry-dialogue-recovered');
  assert.equal(v.healthVerified,false);assert.equal(v.health,null);assert.equal(v.entryDialogueRecovered,true);assert.equal(v.pauseVerified,true);
  assert.deepEqual(downs(f),entry==='intro'?['VK_SPACE','VK_B']:['VK_B']);assert.equal(f.getWarm(),0);assert.equal(f.getPortraits(),0);
  assert.deepEqual(f.clicks.map(c=>[c.x,c.y]),[[1374,657.5]]);assert.equal(f.metrics.mapCalls,0);assert.equal(f.nativeCalls.length,0);
  const e=r.details.inputEvents,leave=e.find(e=>e.type==='combatStatueHealDialogueLeave'),start=e.find(e=>e.type==='combatStatueHealEntryDialogue');
  assert.equal(leave.authority,'entry-cleanup');assert.equal(leave.worldFrameId,null);assert.equal(leave.entryFrameId,start.source.frameId);
  assert.ok(!e.some(e=>/OwnedWorld|BlessingChoice|LisaPortrait/.test(e.type)));assert.equal(f.getPhase(),'inventory');
});
test('normal STOP after one Space shares consumption with guardian: exact Leave then inventory, no second advance',async()=>{
  const f=actual({stopAfterSpace:true}),r=await f.run();assert.equal(r.status,'stopped');assert.equal(r.healthVerified,false);assert.equal(r.pauseVerified,true);
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_F','VK_SPACE','VK_B']);assert.deepEqual(f.clicks.map(c=>[c.x,c.y]),[[1374,657.5]]);
  assert.equal(f.adapter.events().filter(e=>e.type==='combatStatueHealIntroAdvance').length,1);assert.equal(f.getPortraits(),0);
});
test('expired normal90s lease never resumes healing, while existing cleanup window may leave/protect',async()=>{
  const f=actual({expireAfterSpace:true}),r=await f.run();assert.equal(r.status,'stopped');assert.equal(r.healthVerified,false);assert.equal(r.pauseVerified,true);
  assert.match(r.reason,/deadline/);assert.deepEqual(downs(f),['VK_ESCAPE','VK_F','VK_SPACE','VK_B']);assert.equal(f.getPortraits(),0);
});
for(const [name,options] of [['foreign UID',{foreignUid:true}],['missing UID',{missingUid:true}],['offering residue',{extraChoice:true}]])
test('real '+name+' entry has no new input or invented owned-world witness',async()=>{
  const f=actual({entry:'intro',...options}),r=await f.run();assert.equal(r.status,'stopped');assert.equal(r.healthVerified,false);
  assert.deepEqual(downs(f),[]);assert.equal(f.clicks.length,0);assert.ok(!f.adapter.events().some(e=>e.type==='combatStatueHealEntryDialogue'));
});
test('stale real entry cannot acquire cleanup authority',async()=>{
  const f=actual({entry:'intro'}),o=await f.initial();f.age(1001);
  const r=await f.adapter.runCombatStatueHeal(o,f.observe);assert.equal(r.status,'stopped');assert.deepEqual(downs(f),[]);
});
test('fresh intro without this request F cannot call the normal advance API',async()=>{
  const f=actual({entry:'intro'}),o=await f.initial();assert.equal(f.adapter.combatHealIntroReady(o),false);
  await assert.rejects(f.adapter.combatHealAdvanceIntro(o),/owned Statue/);assert.deepEqual(downs(f),[]);
});
for(const mode of ['read-age','read-stop','persist-age','persist-fail'])test('final '+mode+' refuses Space and consumes its one allowance',async()=>{
  const f=actual(),o=await f.ownedIntro();assert.equal(f.adapter.combatHealIntroReady(o),true);
  const read=f.context.file.readTextSync,write=f.context.file.writeTextSync;let reads=0;
  f.context.file.readTextSync=p=>{const text=read(p);if(p==='statue-dialogue.js'&&++reads===2){
    if(mode==='read-age')f.age(1001);
    if(mode==='read-stop')f.getVirtualFiles().set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:f.context.Date.now()}));
  }return text;};
  f.context.file.writeTextSync=(p,text)=>{
    if(String(p).includes('.statue-dialogue-advance.json')){
      if(mode==='persist-fail')return false;
      if(mode==='persist-age')f.age(1001);
    }return write(p,text);
  };
  await assert.rejects(f.adapter.combatHealAdvanceIntro(o),/expired|Stop requested|persistence/);
  f.context.file.readTextSync=read;f.context.file.writeTextSync=write;f.getVirtualFiles().delete('stop.json');
  assert.equal(f.adapter.combatHealIntroReady(await f.observe()),false);
  await assert.rejects(f.adapter.combatHealAdvanceIntro(await f.observe()),/owned Statue/);
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_F']);assert.equal(f.adapter.events().filter(e=>e.type==='combatStatueHealDialogueAttempt').length,1);
});
test('mutated public intro snapshot cannot match private source seal',async()=>{
  const f=actual(),o=await f.ownedIntro(),changed=copy(o);changed.hud.captureStamp.capturedAt--;
  assert.equal(f.adapter.combatHealIntroReady(changed),false);await assert.rejects(f.adapter.combatHealAdvanceIntro(changed));
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_F']);
});
test('one already-consumed Space cannot be retried by protection when intro remains unchanged',async()=>{
  const f=actual({stayIntro:true});await assert.rejects(f.run(),/Pause protection exhausted/);
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_F','VK_SPACE']);assert.equal(f.clicks.length,0);assert.equal(f.getOverlappingKeyDowns().length,0);
});
test('inventory-only adapter still rejects the entire healer command',()=>{
  const f=actual(),a=f.context.createActOneAdapter(5,{inventoryUiOnlyV1:true});
  assert.throws(()=>a.beginMission({mission:'questStep',step:'combatStatueHeal',id:'x',session:'lion-adapter-test',createdAt:9000,expectedFrameId:1}),/rejects unrelated/);
});
test('guardian Leave rechecks capture age after persistence and cannot retry its spent allowance',async()=>{
  const f=actual({entry:'choices'}),write=f.context.file.writeTextSync;
  f.context.file.writeTextSync=(p,text)=>{const result=write(p,text);if(String(p).includes('.statue-dialogue-leave.json'))f.age(1001);return result;};
  await assert.rejects(f.run(),/Pause protection exhausted/);
  assert.deepEqual(downs(f),[]);assert.equal(f.clicks.length,0);
  const attempts=f.adapter.events().filter(e=>e.type==='combatStatueHealDialogueAttempt');assert.equal(attempts.length,1);assert.equal(attempts[0].kind,'leave');
});
test('new choice frame with reused Space completion clock cannot authorize Blessing',async()=>{
  const f=actual(),o=await f.ownedIntro();await f.adapter.combatHealAdvanceIntro(o);
  const finished=f.context.Date.now();f.context.Date.now=()=>finished;
  const next=await f.observe();assert.ok(next.frameId>o.frameId);assert.equal(next.hud.captureStamp.capturedAt,finished);
  assert.equal(f.adapter.combatHealBlessingReady(next),false);
  await assert.rejects(f.adapter.combatHealChooseBlessing(next),/Fresh owned Statue Blessing/);assert.equal(f.clicks.length,0);
});
test('a new request cannot borrow the previous request completed F for normal intro advance',async()=>{
  const f=actual();await f.ownedIntro();
  f.adapter.beginMission({id:'new-request',session:'lion-adapter-test',mission:'questStep',step:'combatStatueHeal',createdAt:f.context.Date.now(),expectedFrameId:1});
  const next=await f.observe();assert.equal(f.adapter.combatHealIntroReady(next),false);
  await assert.rejects(f.adapter.combatHealAdvanceIntro(next),/owned Statue/);assert.deepEqual(downs(f),['VK_ESCAPE','VK_F']);
});

test('qualified journal fallback remains truthful protection without claiming recovered inventory',async()=>{
  const f=actual({entry:'intro',blockInventory:true}),r=await f.engineRun(),v=r.details.result;
  assert.equal(r.status,'stopped',JSON.stringify(r));assert.equal(v.healthVerified,false);assert.equal(v.pauseVerified,true);
  assert.equal(v.pauseProof.kind,'journal');assert.equal(v.entryDialogueRecovered,false);
  assert.equal(v.reason,'entry-dialogue-protected-without-inventory');assert.equal(v.health,null);
  assert.deepEqual(downs(f),['VK_SPACE','VK_B','VK_J']);assert.equal(f.getScreen(),'journal');
  assert.equal(f.getPortraits(),0);assert.equal(f.getWarm(),0);assert.equal(f.clicks.length,1);
});
