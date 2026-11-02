'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const retreat=require(path.join(dir,'combat-statue-retreat.js'));
// Exact historical frame9 from R69 retreat01; its original completion clock is used only for replay.
const recordedEntry=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/combat-statue-retreat-r69-entry.fixture.json'),'utf8'));
const row=(text,x,y,width=90,height=28)=>({text,x,y,width,height});
const uid=()=>row('UID: 693306810',1690,1050,190,24);
const party=()=>[row('Lumina',1678,255),row('Amber',1690,349),row('Kaeya',1698,443),row('Lisa',1691,537)];

function frame(id=1,at=1000,kind='world'){
  return {session:'retreat-test',frameId:id,timestamp:at,kind,map:kind==='world'?{map:'Teyvat',x:-1323.474,y:2566.115}:null,
    ocr:[uid(),...party()],hud:{captureStamp:{session:'retreat-test',frameId:id,capturedAt:at,source:'game-capture-start'},
      world:kind==='world',groundControls:true,climbing:false,auto:false,journal:false,bigMap:kind==='map',choice:false,
      dialogueReady:false,objectiveChanged:false,health:{current:797,max:1001},healthOcr:['797/1001'],
      enemyBars:[],enemyBarDiagnostic:{level:'any',candidates:0}}};
}

test('current-party world and fixed arrival need no obsolete Lisa quest',()=>{
  const o=frame();o.hud.objectives=['LY.'];
  assert.equal(retreat.worldReady(o,1000,o.session,true),true);
  assert.equal(retreat.atStatue(o,1000,o.session),true);
});
for(const [name,change] of [
  ['missing capture stamp',o=>delete o.hud.captureStamp],
  ['wrong capture session',o=>o.hud.captureStamp.session='foreign'],
  ['wrong capture frame',o=>o.hud.captureStamp.frameId++],
  ['publication time substituted',o=>o.hud.captureStamp.source='published'],
  ['future capture',o=>o.hud.captureStamp.capturedAt=1001],
  ['wrong UID',o=>o.ocr[0].text='UID: 693306811'],
  ['duplicate UID',o=>o.ocr.push(uid())],
  ['conflicting complete UID elsewhere',o=>o.ocr.push(row('UID: 693306811',20,20))],
  ['zero capture start',o=>o.hud.captureStamp.capturedAt=0],
  ['zero frame identity',o=>{o.frameId=0;o.hud.captureStamp.frameId=0;}],
  ['missing UID',o=>o.ocr.shift()],
  ['wrong maximum',o=>{o.hud.health.max=4015;o.hud.healthOcr=['797/4015'];}],
  ['zero health',o=>{o.hud.health.current=0;o.hud.healthOcr=['0/1001'];}],
  ['conflicting health OCR',o=>o.hud.healthOcr.push('796/1001')],
  ['wrong ordered roster',o=>o.ocr.find(r=>r.text==='Lisa').y=443],
  ['duplicate name',o=>o.ocr.push(row('Lisa',1700,540))],
  ['missing candidate recognition',o=>delete o.hud.enemyBarDiagnostic],
  ['negative raw candidate count',o=>o.hud.enemyBarDiagnostic.candidates=-1],
  ['missing raw candidate count',o=>delete o.hud.enemyBarDiagnostic.candidates],
  ['nonfinite raw candidate count',o=>o.hud.enemyBarDiagnostic.candidates=Infinity],
  ['fractional raw candidate count',o=>o.hud.enemyBarDiagnostic.candidates=1.5],
  ['boolean raw candidate count',o=>o.hud.enemyBarDiagnostic.candidates=true],
  ['string raw candidate count',o=>o.hud.enemyBarDiagnostic.candidates='5'],
  ['unqualified candidate mode',o=>o.hud.enemyBarDiagnostic.level=1],
  ['climbing',o=>o.hud.climbing=true],
  ['unrelated menu',o=>o.hud.journal=true],
])test(name+' refuses world authority',()=>{
  const o=frame();change(o);assert.equal(retreat.worldReady(o,1000,o.session,false),false);
});
test('the original1000ms source limit is inclusive and completion cannot renew it',()=>{
  const o=frame();o.timestamp=2000;
  assert.equal(retreat.fresh(o,2000,o.session,0),true);
  assert.equal(retreat.fresh(o,2001,o.session,0),false);
});
test('arrival rejects any raw enemy candidate and position outside fixed20-unit radius',()=>{
  const o=frame();o.hud.enemyBarDiagnostic.candidates=1;
  assert.equal(retreat.worldReady(o,1000,o.session,false),true);
  assert.equal(retreat.atStatue(o,1000,o.session),false);
  o.hud.enemyBarDiagnostic.candidates=0;o.map.x+=20.01;
  assert.equal(retreat.atStatue(o,1000,o.session),false);
});

function pure(options={}){
  let now=1000,id=1,screen=options.map?'map':'inventory',maps=0,teleported=false;
  const calls=[];const initial=frame(id,now,screen);
  const api={now:()=>now,checkStop(){if(options.stop)throw Error('original STOP');},combatRetreatDeadline:()=>90000,
    sleep:async ms=>{now+=ms;},release:async()=>{calls.push('release');if(options.releaseFailure)throw Error('release failed');},
    combatRetreatInitialMapReady:o=>o.kind==='map',combatRetreatInventoryReady:o=>o.kind==='inventory',
    combatRetreatPrepareNavigation:async()=>{calls.push('warm');},
    combatRetreatAdoptMap:async()=>calls.push('adopt'),
    combatRetreatCloseInventory:async()=>{calls.push('Escape');screen='world';if(options.stopAfterClose)options.stop=true;},
    combatRetreatFieldReady:o=>o.kind==='world'&&retreat.worldReady(o,now,o.session,false),
    combatRetreatOpenMap:async()=>{calls.push('M');maps++;if(maps>=(options.ignoreMaps||0)+1)screen='map';},
    combatRetreatMapReady:o=>o.kind==='map',
    combatRetreatTeleport:async()=>{calls.push('tp');teleported=true;screen='world';if(options.tpFailure)throw Error('tp failed');if(options.expireAfterTp)now=90000;},
    combatRetreatAtStatue:o=>teleported&&retreat.atStatue(o,now,o.session)};
  if(options.reusedCompletion)initial.hud.captureStamp.capturedAt=900;
  const observe=async()=>{if(!options.repeat)id++;const o=frame(id,now,screen);
    if(options.threatenedEntry&&!teleported&&screen==='world'){o.hud.enemyBars=recordedEntry.hud.enemyBars.map(b=>({...b}));o.hud.enemyBarDiagnostic={...recordedEntry.hud.enemyBarDiagnostic};}
    if(options.reusedStart)o.hud.captureStamp.capturedAt=initial.hud.captureStamp.capturedAt;
    if(options.reusedCompletion){o.timestamp=initial.timestamp;o.hud.captureStamp.capturedAt=950;}
    return o;};
  return {calls,api,run:()=>retreat.run(initial,api,observe)};
}
test('runner has oneEscape, three new-world M attempts, one tp and explicit unverified healing',async()=>{
  const f=pure({ignoreMaps:2}),r=await f.run();
  assert.deepEqual(f.calls,['warm','Escape','M','M','M','tp','release']);
  assert.equal(r.arrived,true);assert.equal(r.healingVerified,false);assert.equal(r.health.current,797);
});
test('a qualified paused map performs no inventory close or map key',async()=>{
  const f=pure({map:true}),r=await f.run();
  assert.deepEqual(f.calls,['warm','adopt','tp','release']);assert.equal(r.arrived,true);
});
test('duplicate observation cannot authorize another key',async()=>{
  const f=pure({repeat:true}),r=await f.run();
  assert.deepEqual(f.calls,['warm','release']);assert.equal(r.status,'stopped');assert.match(r.reason,/non-advancing/);
});
test('STOP after Escape releases without map or teleport',async()=>{
  const f=pure({stopAfterClose:true}),r=await f.run();
  assert.deepEqual(f.calls,['warm','Escape','release']);assert.match(r.reason,/original STOP/);
});
test('teleport and release failures remain separately visible',async()=>{
  const f=pure({tpFailure:true,releaseFailure:true}),r=await f.run();
  assert.equal(r.status,'stopped');assert.match(r.reason,/tp failed/);assert.deepEqual(r.cleanupErrors,['release failed']);
  assert.equal(f.calls.filter(x=>x==='tp').length,1);
});
test('a blocking tp return cannot renew the original operation deadline',async()=>{
  const f=pure({expireAfterTp:true}),r=await f.run();
  assert.equal(r.arrived,false);assert.match(r.reason,/deadline/);assert.equal(r.polls,3);
});

// Reuse only the real adapter fixture definitions, not the unrelated Lion tests.
const fixtureSource=fs.readFileSync(path.join(__dirname,'lion-field-combat-adapter.test.cjs'),'utf8');
const cut=fixtureSource.indexOf('\nfunction assertPauseProof');
assert.ok(cut>0);
const mask='rect&&rect.x===350&&rect.y===100&&rect.w===1250&&rect.h===800';
assert.equal(fixtureSource.split(mask).length,2);
const fixtureText=fixtureSource.slice(0,cut).replace(mask,
  'rect&&((rect.x===350&&rect.y===100&&rect.w===1250&&rect.h===800)||(rect.x===0&&rect.y===30&&rect.w===1920&&rect.h===870))');
const sandbox={require,module:{exports:{}},__dirname,setImmediate};
vm.runInNewContext(fixtureText+'\nmodule.exports={fixture,row};',sandbox,{filename:'retreat-existing-adapter.fixture.cjs'});
const fixture=sandbox.module.exports.fixture;

function actual(options={}){
  const max=options.max||1001,health=options.health===undefined?797:options.health;
  const worldRows=[row('LY.',80,250,50,25),row('E',1550,1005,25,25),row('Q',1660,1005,25,25),
    row(`${health}/${max}`,900,1002,120,24),...party()];
  const f=fixture({step:'combatStatueRetreat',noEnemy:!options.enemy,healthText:`${health}/${max}`,
    initialScreen:options.map?'map':'inventory',fieldRowsSequence:[worldRows],
    mapPosition:options.badPosition?{x:0,y:0}:{x:-1323.474,y:2566.115},...options.fixture});
  // Model only the existing lazy cache initialization: no game capture or input in this getter.
  let warm=0,offset=0,preparedCapture=false;const warmScreens=[],clock=f.context.Date.now.bind(f.context.Date);
  f.context.Date.now=()=>clock()+offset;
  Object.defineProperty(f.context.genshin,'LazyNavigationInstance',{configurable:true,get(){return {get Value(){
    warm++;warmScreens.push(f.getScreen());offset+=options.warmMs||0;
    if(options.warmFailure)throw Error('retained warm failure');
    if(options.stopDuringWarm)f.getVirtualFiles().set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:f.context.Date.now()}));
    if(options.changeDuringWarm)f.setScreen(options.changeDuringWarm);
    return {};
  }};}});
  const position=f.context.genshin.getPositionFromMap;
  f.context.genshin.getPositionFromMap=function(...args){if(!warm)offset+=options.coldMapMs||0;return position.apply(this,args);};
  // Preserve source-image OCR geometry while supplying the original UID to the sanitized fixture.
  const capture=f.context.captureGameRegion;
  f.context.captureGameRegion=()=>{
    const image=capture(),find=image.findMulti.bind(image);
    if(options.stalePrepared&&warm&&!preparedCapture){preparedCapture=true;offset+=1001;}
    image.findMulti=ro=>{const rows=Array.from(find(ro));
      const ids=options.uid===false?[]:[row(options.uid||'UID: 693306810',1690,1050,190,24)];
      if(options.duplicateUid)ids.push(uid());
      for(const r of ids)if(r.x>=ro.x&&r.x<ro.x+ro.w&&r.y>=ro.y&&r.y<ro.y+ro.h)rows.push(r);
      rows.count=rows.length;return rows;};
    return image;
  };
  let mapInputs=0;const keyDown=f.context.keyDown;
  f.context.keyDown=key=>{keyDown(key);if(key==='VK_M'&&++mapInputs>(options.ignoreMaps||0))f.setScreen('map');};
  f.context.genshin.tp=async(x,y,force)=>{
    f.nativeCalls.push({kind:'tp',x,y,force});
    if(options.tpFailure)throw Error('retained tp failure');
    f.setScreen('field');
  };
  f.context.file.pinCaptureEvidence=()=>{};
  const initial=()=>f.adapter.observe('lion-adapter-test',1);
  return {...f,initial,warmScreens,getWarm:()=>warm,run:async()=>f.adapter.runCombatStatueRetreat(await initial(),f.observe)};
}
const downs=f=>Array.from(f.inputs).filter(e=>e.kind==='down').map(e=>e.key);
test('real adapter retreats and protects once, with map lookup only after teleport',async()=>{
  const f=actual(),r=await f.run();
  assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(r.arrived,true);assert.equal(r.healingVerified,false);
  assert.equal(r.pauseVerified,true);assert.equal(f.getScreen(),'inventory');
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_M','VK_B']);
  assert.equal(f.nativeCalls.filter(c=>c.kind==='tp').length,1);
  assert.equal(f.metrics.mapCalls,1);assert.equal(f.metrics.orientationCalls,0);
  assert.ok(f.mapQueries.every(q=>q[1]===-1323.474&&q[2]===2566.115));
  assert.match(JSON.stringify(f.adapter.events()),/combat-statue-retreat\.js/);
});
test('real paused-map adoption is UID-qualified and never sends Escape/M',async()=>{
  const f=actual({map:true}),r=await f.run();assert.equal(r.arrived,true,JSON.stringify(r));
  assert.deepEqual(downs(f),['VK_B']);
});
for(const [name,opt] of [['foreign UID',{uid:'UID: 693306811'}],['missing UID',{uid:false}],['duplicate UID',{duplicateUid:true}]])
test('real '+name+' initial inventory sends no key or tp',async()=>{
  const f=actual(opt),r=await f.run();assert.equal(r.status,'stopped');assert.deepEqual(downs(f),[]);assert.equal(f.nativeCalls.length,0);
});
test('real different character maximum is protected, without opening map or teleport',async()=>{
  const f=actual({max:4015}),r=await f.run();assert.equal(r.status,'stopped');assert.equal(r.pauseVerified,true);
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_B']);assert.equal(f.nativeCalls.length,0);
});
test('real visible enemy candidates prevent arrival even when the quest objective is unrelated',async()=>{
  const f=actual({enemy:true}),r=await f.run();assert.equal(r.arrived,false);assert.equal(r.pauseVerified,true);
  assert.equal(f.nativeCalls.filter(c=>c.kind==='tp').length,1);assert.equal(f.metrics.mapCalls,0);
  assert.ok(f.observations.some(o=>o.hud.enemyBarDiagnostic.candidates>0));
});
test('real map failure preserves primary failure and obtains qualified pause',async()=>{
  const f=actual({tpFailure:true}),r=await f.run();assert.equal(r.arrived,false);assert.match(r.reason,/retained tp failure/);
  assert.equal(r.pauseVerified,true);assert.equal(f.nativeCalls.filter(c=>c.kind==='tp').length,1);
});
test('real source seal rejects mutated initial evidence',async()=>{
  const f=actual(),initial=await f.initial();initial.hud.captureStamp.capturedAt--;
  assert.equal(f.adapter.combatRetreatInventoryReady(initial),false);assert.deepEqual(downs(f),[]);
});
test('source aging during pre-key stop check is rechecked before Escape',async()=>{
  const f=actual(),initial=await f.initial();await f.adapter.combatRetreatPrepareNavigation(initial);let checks=0;const now=f.context.Date.now;
  f.adapter.setHeartbeat(()=>{if(++checks===2)f.context.Date.now=()=>now()+1001;});
  await assert.rejects(f.adapter.combatRetreatCloseInventory(initial),/source changed|Fresh original-account inventory required/);
  assert.deepEqual(downs(f),[]);assert.equal(f.getScreen(),'inventory');
});
test('STOP delivered during final pre-key check prevents Escape',async()=>{
  const f=actual(),initial=await f.initial();await f.adapter.combatRetreatPrepareNavigation(initial);let checks=0;
  f.adapter.setHeartbeat(()=>{if(++checks===2)f.getVirtualFiles().set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:10000}));});
  await assert.rejects(f.adapter.combatRetreatCloseInventory(initial),/Stop requested/);assert.deepEqual(downs(f),[]);
});
test('real receipt flow through Engine/mission preserves arrival, sources, release and final pause',async()=>{
  const f=actual({warmMs:12300,coldMapMs:12300});vm.runInNewContext(fs.readFileSync(path.join(dir,'engine.js'),'utf8'),f.context);
  vm.runInNewContext(fs.readFileSync(path.join(dir,'mission.js'),'utf8'),f.context);
  const runner=f.context.ActOnePilot.create(f.adapter,{session:'lion-adapter-test',enableInput:true});
  const initial=await runner.observe();
  const req={id:'retreat-engine-1',session:'lion-adapter-test',mission:'questStep',step:'combatStatueRetreat',createdAt:f.getNow(),expectedFrameId:initial.frameId};
  assert.equal(await runner.process(req,()=>f.context.ActOneMission),'completed');
  const receipt=JSON.parse(f.getVirtualFiles().get('receipts/lion-adapter-test/retreat-engine-1.json'));
  assert.equal(receipt.details.result.arrived,true);assert.equal(receipt.details.result.healingVerified,false);
  assert.equal(receipt.details.result.pauseVerified,true);assert.equal(receipt.frameId,runner.getFrame());
  assert.deepEqual(downs(f),['VK_ESCAPE','VK_M','VK_B']);
  assert.match(JSON.stringify(receipt.details.inputEvents),/combat-statue-retreat\.js/);
  assert.equal(f.getOverlappingKeyDowns().length,0);
  const preparation=receipt.details.inputEvents.filter(e=>e.type==='combatStatueRetreatNavigationPreparation');
  assert.equal(preparation.length,1);assert.equal(preparation[0].inputSent,false);assert.equal(preparation[0].completed,true);
  const firstKey=receipt.details.inputEvents.find(e=>e.type==='key');
  assert.ok(firstKey.frameId>preparation[0].frameId&&firstKey.startedAt>preparation[0].finishedAt);
});
test('inventory UI-only adapter still rejects the new retreat operation',()=>{
  const f=actual(),adapter=f.context.createActOneAdapter(5,{inventoryUiOnlyV1:true});
  assert.throws(()=>adapter.beginMission({id:'x',session:'lion-adapter-test',createdAt:10000,mission:'questStep',step:'combatStatueRetreat'}),/Inventory UI-only/);
  assert.deepEqual(downs(f),[]);
});

for(const options of [{reusedStart:true},{reusedCompletion:true}])test('new frame cannot renew prior capture clock '+JSON.stringify(options),async()=>{
  const f=pure(options),r=await f.run();assert.deepEqual(f.calls,['warm','release']);
  assert.equal(r.status,'stopped');assert.match(r.reason,/non-advancing/);
});

for(const mode of ['age','stop'])test('final inventory helper read cannot hide '+mode,async()=>{
  const f=actual();let offset=0,reads=0;
  const clock=f.context.Date.now.bind(f.context.Date),capture=f.context.captureGameRegion;
  f.context.Date.now=()=>clock()+offset;
  f.context.captureGameRegion=()=>{const image=capture();offset+=500;return image;};
  const initial=await f.initial();await f.adapter.combatRetreatPrepareNavigation(initial);const read=f.context.file.readTextSync;
  f.context.file.readTextSync=p=>{const data=read(p);if(p==='world-inventory.js'&&++reads===2){
    if(mode==='age')offset+=501;
    else f.getVirtualFiles().set('stop.json',JSON.stringify({session:'lion-adapter-test',createdAt:f.getNow()}));
  }return data;};
  assert.equal(initial.timestamp-initial.hud.captureStamp.capturedAt,500);
  await assert.rejects(f.adapter.combatRetreatCloseInventory(initial),mode==='age'?/source changed/:/Stop requested/);
  assert.equal(reads,2);assert.deepEqual(downs(f),[]);assert.equal(f.getScreen(),'inventory');
});


test('recorded R69 world permits retreat entry despite five raw candidates',()=>{
  const o=recordedEntry;
  assert.equal(o.frameId,9);assert.equal(o.hud.enemyBars.length,4);assert.equal(o.hud.enemyBarDiagnostic.candidates,5);
  assert.equal(retreat.worldReady(o,o.timestamp,o.session,false),true);
  assert.equal(retreat.worldReady(o,o.hud.captureStamp.capturedAt+1001,o.session,false),false);
});
test('well-formed larger final-bar counts do not block retreat entry',()=>{
  const o=JSON.parse(JSON.stringify(recordedEntry));o.hud.enemyBars.push({...o.hud.enemyBars[0],x:500});o.hud.enemyBarDiagnostic.candidates=6;
  assert.equal(retreat.worldReady(o,o.timestamp,o.session,false),true);
  assert.equal(retreat.worldReady(o,o.timestamp,o.session,true),false);
});
test('recorded threats cannot qualify arrival or the healing world gate',()=>{
  const o=JSON.parse(JSON.stringify(recordedEntry));
  // This synthetic position isolates the unchanged no-enemy arrival gate; it is not an arrival claim.
  o.map={map:'Teyvat',x:-1323.474,y:2566.115};
  assert.equal(retreat.atStatue(o,o.timestamp,o.session),false);
  o.hud.enemyBars=[];assert.equal(retreat.atStatue(o,o.timestamp,o.session),false);
  assert.equal(retreat.worldReady(o,o.timestamp,o.session,true),false);
  o.hud.enemyBarDiagnostic.candidates=0;o.hud.enemyBars=[{...recordedEntry.hud.enemyBars[0]}];
  assert.equal(retreat.atStatue(o,o.timestamp,o.session),false);
  o.hud.enemyBars=[];assert.equal(retreat.atStatue(o,o.timestamp,o.session),true);
  assert.equal(retreat.worldReady(o,o.timestamp,o.session,true),true);
});
test('runner opens the map from the threatened entry and still requires clear arrival',async()=>{
  const f=pure({threatenedEntry:true}),r=await f.run();
  assert.deepEqual(f.calls,['warm','Escape','M','tp','release']);assert.equal(r.arrived,true);assert.equal(r.healingVerified,false);
});


for(const map of [false,true])test('real cold navigation warms while '+(map?'map':'inventory')+' is paused, then uses a fresh source',async()=>{
  const f=actual({map,warmMs:12300,coldMapMs:12300}),r=await f.run();
  assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(r.pauseVerified,true);
  assert.deepEqual(f.warmScreens,[map?'map':'inventory']);assert.equal(f.getWarm(),1);
  assert.deepEqual(downs(f),map?['VK_B']:['VK_ESCAPE','VK_M','VK_B']);
  assert.equal(f.nativeCalls.filter(c=>c.kind==='tp').length,1);
  const e=Array.from(f.adapter.events()).find(e=>e.type==='combatStatueRetreatNavigationPreparation');
  assert.equal(e.inputSent,false);assert.equal(e.completed,true);assert.equal(e.entryKind,map?'map':'inventory');
  assert.equal(e.finishedAt-e.startedAt,12300);
  const next=f.observations.find(o=>o.frameId>e.frameId);
  assert.ok(next.hud.captureStamp.capturedAt>e.finishedAt);assert.ok(next.timestamp-next.hud.captureStamp.capturedAt<=1000);
});
for(const map of [false,true])test('stale after-preparation '+(map?'map':'inventory')+' recapture refuses all input',async()=>{
  const f=actual({map,warmMs:12300,stalePrepared:true}),r=await f.run();
  assert.equal(r.status,'stopped');assert.match(r.reason,/stale|non-advancing/);
  assert.equal(f.getWarm(),1);assert.deepEqual(downs(f),[]);assert.equal(f.nativeCalls.length,0);
});
for(const [name,options] of [['original deadline',{warmMs:90000}],['STOP',{warmMs:12300,stopDuringWarm:true}],['load failure',{warmFailure:true}]])
test('preparation '+name+' cannot lead to Escape or teleport',async()=>{
  const f=actual(options),r=await f.run();assert.equal(r.status,'stopped');
  assert.equal(f.getWarm(),1);assert.deepEqual(downs(f),[]);assert.equal(f.nativeCalls.length,0);assert.equal(f.getScreen(),'inventory');
});
for(const map of [false,true])test('changed paused entry after preparation is refused '+map,async()=>{
  const f=actual({map,changeDuringWarm:map?'inventory':'map'}),r=await f.run();
  assert.equal(r.status,'stopped');assert.match(r.reason,/changed during navigation preparation/);
  assert.deepEqual(downs(f),[]);assert.equal(f.nativeCalls.length,0);
});
test('missing preparation API refuses before input',async()=>{
  const f=pure();delete f.api.combatRetreatPrepareNavigation;const r=await f.run();
  assert.equal(r.status,'stopped');assert.deepEqual(f.calls,['release']);
});
test('real direct inventory close cannot bypass preparation',async()=>{
  const f=actual(),o=await f.initial();
  await assert.rejects(f.adapter.combatRetreatCloseInventory(o),/inventory required/);
  assert.deepEqual(downs(f),[]);assert.equal(f.getWarm(),0);
});
test('real preparation is consumed once without another warm-up or input',async()=>{
  const f=actual(),o=await f.initial();await f.adapter.combatRetreatPrepareNavigation(o);
  await assert.rejects(f.adapter.combatRetreatPrepareNavigation(o),/already consumed/);
  assert.equal(f.getWarm(),1);assert.deepEqual(downs(f),[]);
});
