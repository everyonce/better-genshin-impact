'use strict';
// All native, image, clock, filesystem-output and input boundaries below are inert.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const candidate=path.resolve(__dirname,'../..');
const root=process.env.BETTERGI_REPOSITORY_ROOT||candidate;
const packageDir=path.join(candidate,'BetterGenshinImpact/User/JsScript/ActOnePilot');
const read=name=>fs.readFileSync(path.join(packageDir,name),'utf8');
const source=read('bgi.js');
const engine=require(path.join(packageDir,'engine.js'));
const context={};
vm.runInNewContext(source,context);
const clone=value=>JSON.parse(JSON.stringify(value));
const row=(text,x,y,width=80,height=24)=>({text,x,y,width,height});
const diagnostic={reason:'Inventory UI-only v1: map and orientation deliberately omitted',mode:'inventory-ui-only-v1'};
function world(){
 return {session:'ui',frameId:3,timestamp:1000,map:null,
  uiObservation:{version:1,kind:'inventory-ui-only-v1',mapOmitted:true,orientationOmitted:true,observationStartedAtUnixMs:980},
  timings:{mapDiagnostic:diagnostic},
  hud:{world:true,groundControls:true,climbing:false,auto:false,journal:false,bigMap:false,dialogueReady:false,choice:false,
   loading:false,unknownHud:false,tutorialStep:null,characterAcquired:null,health:{current:2211,max:4015},
   healthOcr:['2211/4015'],healthDiagnostic:{decision:'primary-scaled-readable'}},
  ocr:[row('Amber',1680,350),row('Kaeya',1680,450),row('E',1690,1020,20,25),row('Q',1800,1020,20,25),
   row('UID: 693306810',1680,1050,180,25)]};
}
const visible=o=>context.actOneInventoryUiWorldEvidence(o.ocr,o.hud);

test('same-capture HUD qualifies without coordinates and without raising the existing health policy',()=>{
 const o=world(),before=JSON.stringify(o);assert.equal(visible(o),true);assert.equal(o.hud.health.current/o.hud.health.max<.6,true);
 assert.equal(JSON.stringify(o),before);assert.equal(context.actOneWorldInventoryPauseReady(o,1000),false);
 const positioned={...o,map:{map:'Teyvat',x:-1266,y:1934}};
 assert.equal(context.actOneWorldInventoryPauseReady(positioned,1000),true);
});
test('missing health, ground, identity, distinct party or positive layout cannot qualify world',()=>{
 const mutations=[o=>o.hud.health=null,o=>o.hud.health.current=0,o=>o.hud.health.current=NaN,
  o=>o.hud.health.current=o.hud.health.max+1,o=>o.hud.health.current=2200,
  o=>o.hud.healthOcr=[],o=>o.hud.healthDiagnostic.decision='conflict-halves-disagree-or-missing',o=>o.hud.groundControls=false,
  o=>o.ocr=o.ocr.filter(r=>!['E','Q'].includes(r.text)),o=>o.ocr.push(row('Space',1700,1020)),
  o=>o.ocr=o.ocr.filter(r=>!r.text.startsWith('UID')),o=>o.ocr.find(r=>r.text.startsWith('UID')).text='UID: 693306811',
  o=>o.ocr.find(r=>r.text==='Kaeya').text='Amber',o=>o.ocr.find(r=>r.text==='Kaeya').x=100,
  o=>o.ocr.find(r=>r.text==='Kaeya').width=NaN,
  ...['climbing','auto','journal','bigMap','dialogueReady','choice','loading','unknownHud','tutorialStep','characterAcquired'].map(k=>o=>o.hud[k]=true)];
 for(const mutate of mutations){const o=world();mutate(o);assert.equal(visible(o),false,mutate.toString());}
});
test('ambient Starfell Valley text is not a map; positive map bands and menus always block world',()=>{
 const ambient=world();ambient.ocr.push(row('Starfell Valley',80,250,250));assert.equal(visible(ambient),true);
 assert.equal(context.actOneInventoryUiBigMap(ambient.ocr),false);
 for(const r of [row('Starfell Valley',1600,985,250),row('Exploration Progress: 0%',1505,1016,290),
  row('200/200',1624,32,120),row('Teyvat',1600,990),row('Confirm',850,550),row('Food',140,32),
  row('Inventory capacity 9/2600',1504,34,295),row('Loading',850,550),row('Login',850,550),row('Party Setup',120,80)]){
  const o=world();o.ocr.push(r);assert.equal(visible(o),false,r.text);
 }
});
test('retained R65 world passes, transition frame3 and inventory fail without importing their old map',()=>{
 const recorded=require('./fixtures/inventory-ui-only-r65.fixture.json');
 const good=clone(recorded.world.observation);
 good.map=null;good.hud.loading=false;good.hud.unknownHud=false;assert.equal(visible(good),true);
 for(const record of recorded.transitions){
  const bad=clone(record.observation);
  bad.map=null;bad.hud.loading=false;bad.hud.unknownHud=false;assert.equal(visible(bad),false);
 }
 const inventory=clone(recorded.inventory.observation);
 assert.equal(visible(inventory),false);
});
test('UI input freshness uses the retained original observation start and cannot inherit publication age',()=>{
 const o=world();assert.equal(context.actOneInventoryUiInputFresh(o,1980,'ui'),true);
 assert.equal(context.actOneInventoryUiInputFresh(o,1981,'ui'),false);
 for(const mutate of [v=>v.uiObservation.observationStartedAtUnixMs=1001,v=>v.uiObservation.mapOmitted=false,
  v=>v.map={x:0,y:0},v=>v.session='foreign',v=>v.frameId=0]){
  const bad=world();mutate(bad);assert.equal(context.actOneInventoryUiInputFresh(bad,1000,'ui'),false);
 }
});

// Reuse the real adapter fixture, substituting only the isolated candidate source.
function actual(options={}){
 const fixtureFile=path.join(root,'Test/ActOnePilot/lion-field-combat-adapter.test.cjs');
 let text=fs.readFileSync(fixtureFile,'utf8'),cut=text.indexOf('\nfunction assertPauseProof');assert(cut>0);text=text.slice(0,cut);
 const directoryLine="const dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');";
 assert(text.includes(directoryLine));text=text.replace(directoryLine,'const dir='+JSON.stringify(packageDir)+';');
 const createLine='const adapter=context.createActOneAdapter(5);';assert(text.includes(createLine));
 text=text.replace(createLine,'const adapter=context.createActOneAdapter(5,{inventoryUiOnlyV1:options.inventoryUiOnlyV1===true});');
 const box={require,module:{exports:{}},__dirname:path.dirname(fixtureFile),setImmediate};
 vm.runInNewContext(text+'\nmodule.exports={fixture,row};',box,{filename:'inert-inventory-ui-adapter-fixture.cjs'});
 const result=box.module.exports.fixture({inventoryUiOnlyV1:true,step:'worldInventoryClose',noEnemy:true,
  extra:[row('UID: 693306810',1680,1050,180,25)],...options});
 result.context.file.pinCaptureEvidence=()=>{};
 return result;
}
test('actual initial and post-Escape observations invoke neither map nor orientation',async()=>{
 const f=actual({throwGps:true});
 const initialAdapter=f.context.createActOneAdapter(5,{inventoryUiOnlyV1:true});
 const initial=await initialAdapter.observe('initial',1);assert.equal(initial.map,null);assert.equal(initial.hud.world,false);
 f.setScreen('field');
 const initialWorld=await initialAdapter.observe('initial',2);assert.equal(initialWorld.map,null);assert.equal(initialWorld.hud.world,true);
 f.setScreen('inventory');
 const before=await f.adapter.observe('lion-adapter-test',1);assert.equal(f.adapter.worldInventoryCloseReady(before),true);
 await f.adapter.closeWorldInventory();
 const after=await f.observe();assert.equal(after.hud.world,true);assert.equal(after.map,null);
 assert.equal(after.uiObservation.kind,'inventory-ui-only-v1');
 assert.equal(f.metrics.mapCalls,0);assert.equal(f.metrics.orientationCalls,0);
 assert.deepEqual(clone(f.inputs.filter(e=>e.kind==='down').map(e=>e.key)),['VK_ESCAPE']);
 assert.equal(f.adapter.worldInventoryCloseReady(after),false);
});
test('actual UI-only pause names its exact input frame and retains one bounded B',async()=>{
 const f=actual({step:'worldInventory',initialScreen:'field',throwGps:true});
 const before=await f.adapter.observe('lion-adapter-test',1);assert.equal(before.hud.world,true);
 f.adapter.beginMission({id:'pause-direct',mission:'questStep',step:'worldInventory',session:'lion-adapter-test',
  expectedFrameId:1,createdAt:f.getNow()},before);
 await f.adapter.observe('lion-adapter-test',2);
 assert.equal(await f.adapter.pauseWorldInventory(),true);
 assert.equal(await f.adapter.pauseWorldInventory(),false);
 const after=await f.adapter.observe('lion-adapter-test',3);assert.equal(after.map,null);assert.equal(after.hud.world,false);
 const event=f.adapter.events().find(e=>e.type==='key');assert.equal(event.key,'VK_B');assert.equal(event.durationMs,60);assert.equal(event.frameId,2);
 assert.equal(f.metrics.mapCalls,0);assert.equal(f.metrics.orientationCalls,0);
 assert.deepEqual(clone(f.inputs.filter(e=>e.kind==='down').map(e=>e.key)),['VK_B']);
});
test('actual passive observe with Lisa objective cannot take the late compass path',async()=>{
 const f=actual({initialScreen:'field',throwGps:true});
 f.adapter.beginMission({mission:'observe',session:'lion-adapter-test',id:'observe-ui',expectedFrameId:1,createdAt:9000});
 const o=await f.adapter.observe('lion-adapter-test',1);
 assert.equal(o.hud.world,true);assert.equal(f.metrics.mapCalls,0);assert.equal(f.metrics.orientationCalls,0);
 assert.equal('compassAngle' in o.hud,false);
});
test('actual mission and engine retain early false-world hint then a fresh terminal world without another Escape',async()=>{
 const inventoryRows=[row('Food',140,32,67,31),row('Inventory capacity 9/2600',1504,34,295,27),
  row('Teyvat Fried Egg',1329,119,297,57),row('Food',1374,187,63,30),row('Use',1670,999,63,38)];
 const fieldRows=[...world().ocr,row('1186/1186',900,1002,120,24)];
 const f=actual({throwGps:true,fieldRowsSequence:[inventoryRows,fieldRows]});
 const runner=engine.create(f.adapter,{session:'lion-adapter-test',enableInput:true,inventoryUiOnlyV1:true});
 await runner.observe();
 const request={id:'whole-resume',mission:'questStep',step:'worldInventoryClose',
  session:'lion-adapter-test',expectedFrameId:1,createdAt:f.getNow()};
 const mission=require(path.join(packageDir,'mission.js'));
 assert.equal(await runner.process(request,()=>mission),'completed');
 const receipt=JSON.parse(f.getVirtualFiles().get('receipts/lion-adapter-test/whole-resume.json'));
 const terminal=JSON.parse(f.getVirtualFiles().get('observation.json'));
 assert.equal(receipt.details.result.worldVisible,false);assert.equal(receipt.details.result.frameId,3);
 assert.equal(receipt.frameId,4);assert.equal(terminal.frameId,4);assert.equal(terminal.hud.world,true,JSON.stringify(terminal.hud));
 assert.equal(terminal.uiObservation.kind,'inventory-ui-only-v1');assert.equal(terminal.map,null);
 assert.deepEqual(receipt.details.inputEvents.map(e=>e.type),['controllerRevision','worldInventoryClose','key']);
 const key=receipt.details.inputEvents.at(-1);assert.equal(key.key,'VK_ESCAPE');assert.equal(key.durationMs,60);assert.equal(key.frameId,2);
 assert.deepEqual(clone(f.inputs.filter(e=>e.kind==='down').map(e=>e.key)),['VK_ESCAPE']);
 assert.equal(f.metrics.mapCalls,0);assert.equal(f.metrics.orientationCalls,0);
});
test('actual pause mission and engine preserve source-frame receipt and terminal inventory',async()=>{
 const f=actual({step:'worldInventory',initialScreen:'field',throwGps:true});
 const runner=engine.create(f.adapter,{session:'lion-adapter-test',enableInput:true,inventoryUiOnlyV1:true});
 await runner.observe();
 const request={id:'whole-pause',mission:'questStep',step:'worldInventory',
  session:'lion-adapter-test',expectedFrameId:1,createdAt:f.getNow()};
 assert.equal(await runner.process(request,()=>require(path.join(packageDir,'mission.js'))),'completed');
 const receipt=JSON.parse(f.getVirtualFiles().get('receipts/lion-adapter-test/whole-pause.json'));
 const terminal=JSON.parse(f.getVirtualFiles().get('observation.json'));
 assert.equal(receipt.details.result.pausedInventory,true);assert.equal(terminal.hud.world,false);
 assert.equal(receipt.details.inputEvents.at(-1).frameId,2);
 assert.deepEqual(receipt.details.inputEvents.map(e=>e.type),['controllerRevision','key']);
 assert.equal(f.metrics.mapCalls,0);assert.equal(f.metrics.orientationCalls,0);
});
test('actual input gate rejects old capture start even when publication time is freshly replaced',async()=>{
 const f=actual();const before=await f.adapter.observe('lion-adapter-test',1);
 f.context.Date.now=()=>11001;before.timestamp=11001;
 assert.equal(f.adapter.worldInventoryCloseReady(before),false);
 await assert.rejects(f.adapter.closeWorldInventory(),/Fresh exact ordinary inventory/);
 assert.equal(f.inputs.length,0);
});
test('an unresolved initial health read does not become UI world or qualify B before-frame authority',async()=>{
 const f=actual({step:'worldInventory',initialScreen:'field',throwGps:true,
  fieldRowsSequence:[[...world().ocr,row('2211/4015',900,1002,120,24)]]});
 const observation=await f.adapter.observe('lion-adapter-test',1);
 assert.equal(observation.hud.health,null);assert.equal(observation.hud.world,false);
 assert.equal(await f.adapter.pauseWorldInventory(),false);assert.equal(f.inputs.length,0);
 assert.equal(f.metrics.mapCalls,0);
});

test('adapter-local observation cannot replace the engine completed-publication handoff',async()=>{
 const f=actual({step:'worldInventory',initialScreen:'field',throwGps:true});
 const before=await f.adapter.observe('lion-adapter-test',1);assert.equal(before.hud.world,true);
 f.adapter.beginMission({id:'no-engine-handoff',mission:'questStep',step:'worldInventory',
  session:'lion-adapter-test',expectedFrameId:1,createdAt:f.getNow()});
 await f.adapter.observe('lion-adapter-test',2);
 assert.equal(await f.adapter.pauseWorldInventory(),false);assert.equal(f.inputs.length,0);
});

test('legacy and UI-only missions preserve the B fallback across the real per-request adapter refresh',async()=>{
 for(const mode of [false,true]){
  const rows=world().ocr;
  const f=actual({inventoryUiOnlyV1:mode,step:'worldInventory',initialScreen:'field',throwGps:mode,
   fieldRowsSequence:[[...rows,row('1186/1186',900,1002,120,24)],[...rows,row('2211/4015',900,1002,120,24)]]});
  const runner=engine.create(f.adapter,{session:'lion-adapter-test',enableInput:true,inventoryUiOnlyV1:mode});
  const before=await runner.observe();assert.equal(before.hud.world,true);
  // This is main's actual refresh shape; the new adapter has no local previous observation.
  Object.assign(f.adapter,f.context.createActOneAdapter(5,{inventoryUiOnlyV1:mode}));
  const observed=[],original=f.adapter.observe;
  f.adapter.observe=async(...args)=>{const value=await original(...args);observed.push(value);return value;};
  // Caller mutation cannot change the engine's private completed before-frame.
  before.hud.health=null;before.hud.world=false;
  const request={id:'pause-health-fallback',mission:'questStep',step:'worldInventory',
   session:'lion-adapter-test',expectedFrameId:1,createdAt:f.getNow()};
  assert.equal(await runner.process(request,()=>require(path.join(packageDir,'mission.js'))),'completed');
  const input=observed.find(o=>o.frameId===2);
  assert.equal(input.hud.health,null);assert.equal(input.hud.world,false);
  assert.equal(input.hud.healthDiagnostic.decision,'conflict-halves-disagree-or-missing');
  const receipt=JSON.parse(f.getVirtualFiles().get('receipts/lion-adapter-test/pause-health-fallback.json'));
  assert.equal(receipt.details.result.pausedInventory,true);
  assert.deepEqual(receipt.details.inputEvents.map(e=>e.type),['controllerRevision','key']);
  assert.equal(receipt.details.inputEvents.at(-1).durationMs,60);
  assert.deepEqual(clone(f.inputs.filter(e=>e.kind==='down').map(e=>e.key)),['VK_B']);
  assert.equal(await f.adapter.pauseWorldInventory(),false);
  if(mode){assert.equal(receipt.details.inputEvents.at(-1).frameId,2);assert.equal(input.map,null);
   assert.equal(f.metrics.mapCalls,0);assert.equal(f.metrics.orientationCalls,0);}
 }
});

test('B fallback requires a positive admitted before-frame and exactly the old bounded HP-row evidence',()=>{
 const before=world(),input=world();input.frameId=4;input.timestamp=1020;input.uiObservation.observationStartedAtUnixMs=1010;
 input.hud.world=false;input.hud.health=null;input.hud.healthOcr=[];input.hud.healthDiagnostic.decision='conflict-halves-disagree-or-missing';
 input.ocr.push(row('2211/4015',900,1002,120,24));
 const fallback=(source=input,prior=before,admitted=1005)=>context.actOneInventoryUiPauseFallback(source,1020,'ui',prior,admitted);
 const originals=JSON.stringify([before,input]);
 assert.equal(fallback(),true);assert.equal(visible(input),false);assert.equal(context.actOneWorldInventoryPauseReady(input,1020),false);
 assert.equal(JSON.stringify([before,input]),originals);
 const mutations=[o=>o.ocr=o.ocr.filter(r=>r.text!=='2211/4015'),
  o=>o.ocr.push(row('2211/4015',901,1002,120,24)),o=>o.ocr.at(-1).x=879,o=>o.ocr.at(-1).x=1051,
  o=>o.ocr.at(-1).y=989,o=>o.ocr.at(-1).y=1031,o=>o.ocr.at(-1).text='0/4015',
  o=>o.ocr.at(-1).text='2211/0',o=>o.ocr.at(-1).text='4016/4015',o=>o.ocr.at(-1).text='2211 of 4015',
  o=>o.hud.health={current:2211,max:4015},o=>delete o.hud.health,o=>o.hud.world=true,
  o=>o.hud.groundControls=false,o=>o.hud.loading=true,o=>o.hud.unknownHud=true,
  o=>o.ocr=o.ocr.filter(r=>!r.text.startsWith('UID')),o=>o.ocr.push(row('Confirm',850,550)),
  o=>o.frameId=before.frameId,o=>o.uiObservation.observationStartedAtUnixMs=1004];
 for(const mutate of mutations){const value=clone(input);mutate(value);assert.equal(fallback(value),false,mutate.toString());}
 for(const mutate of [o=>o.hud.world=false,o=>o.hud.health=null,o=>o.session='foreign',
  o=>o.uiObservation.observationStartedAtUnixMs=4]){
  const prior=clone(before);mutate(prior);assert.equal(fallback(input,prior),false,mutate.toString());
 }
 assert.equal(fallback(input,before,1021),false);
});

test('a later positive source cannot manufacture a missing healthy before-frame for UI-only B',async()=>{
 const f=actual({step:'worldInventory',initialScreen:'field',throwGps:true,
  fieldRowsSequence:[[...world().ocr,row('2211/4015',900,1002,120,24)],[...world().ocr,row('1186/1186',900,1002,120,24)]]});
 const runner=engine.create(f.adapter,{session:'lion-adapter-test',enableInput:true,inventoryUiOnlyV1:true});
 const before=await runner.observe();assert.equal(before.hud.world,false);
 Object.assign(f.adapter,f.context.createActOneAdapter(5,{inventoryUiOnlyV1:true}));
 // A forged caller copy must not promote the original unknown observation.
 before.hud={...world().hud};before.ocr=world().ocr;
 await runner.process({id:'unqualified-before',mission:'questStep',step:'worldInventory',
  session:'lion-adapter-test',expectedFrameId:1,createdAt:f.getNow()},()=>require(path.join(packageDir,'mission.js')));
 assert.equal(f.inputs.filter(e=>e.kind==='down').length,0);
});

test('the21 separately qualified local-pause conflict frames gain no UI inventory/world authority',()=>{
 const fixture=require(path.join(root,'Test/ActOnePilot/fixtures/pause-eq-health-conflict.json'));
 for(const raw of fixture.conflictFrames){
  const input={...clone(raw),session:'ui',map:null,hud:clone(fixture.conflictHud)},before=world();
  before.frameId=input.frameId-1;before.timestamp=input.timestamp-20;
  before.uiObservation.observationStartedAtUnixMs=input.timestamp-30;
  input.uiObservation={...before.uiObservation,observationStartedAtUnixMs:input.timestamp-5};
  assert.equal(context.actOneLocalPauseInputReady(input,input.timestamp,'ui'),true);
  assert.equal(context.actOneInventoryUiPauseFallback(input,input.timestamp,'ui',before,input.timestamp-10),false);
  assert.equal(visible(input),false);assert.equal(input.hud.health,null);assert.equal(input.hud.groundControls,false);
 }
});
test('map-only initial scene and same-capture lowercase-control repair remain distinct',async()=>{
 const map=actual({initialScreen:'map',throwGps:true});
 const o=await map.adapter.observe('lion-adapter-test',1);assert.equal(o.hud.bigMap,true);assert.equal(o.hud.world,false);
 assert.equal(map.adapter.worldInventoryCloseReady(o),false);assert.equal(map.metrics.mapCalls,0);
 const field=actual({initialScreen:'field',omitControls:true,controlCropRows:[row('E',520,120,40,60)]});
 const repaired=await field.adapter.observe('lion-adapter-test',1);
 assert.equal(field.metrics.controlCropCalls,1);assert.equal(repaired.hud.groundControls,true);assert.equal(repaired.hud.world,true);
});
test('legacy adapter still performs localization and emits no UI-only metadata',async()=>{
 const f=actual({inventoryUiOnlyV1:false,initialScreen:'field'});
 const o=await f.adapter.observe('lion-adapter-test',1);
 assert.equal(o.hud.world,true);assert.notEqual(o.map,null);assert(f.metrics.mapCalls>0);assert(f.metrics.orientationCalls>0);
 assert.equal('uiObservation' in o,false);
});
test('actual STOP after Escape retains release and never creates a second key down',async()=>{
 const f=actual({stopAfterClose:true});await f.adapter.observe('lion-adapter-test',1);
 await assert.rejects(f.adapter.closeWorldInventory());f.adapter.release();
 assert.deepEqual(clone(f.inputs.filter(e=>e.kind==='down').map(e=>e.key)),['VK_ESCAPE']);
 assert(f.inputs.some(e=>e.kind==='up'&&e.key==='VK_ESCAPE'));
});
test('engine and adapter reject every unrelated authority class',async()=>{
 for(const request of [{mission:'navigation'},{mission:'combat'},{mission:'recover'},{mission:'dialogue'},
  {mission:'questStep',step:'wolfCombat'},{mission:'questStep',step:'actTwoWorldMap'}]){
  assert.equal(engine.inventoryUiRequestAllowed(request),false);
  const f=actual();assert.throws(()=>f.adapter.beginMission(request),/rejects unrelated/);assert.equal(f.inputs.length,0);
 }
 for(const request of [{mission:'observe'},{mission:'stop'},{mission:'questStep',step:'worldInventory'},
  {mission:'questStep',step:'worldInventoryClose'}])assert.equal(engine.inventoryUiRequestAllowed(request),true);
});
test('real engine persists provenance and refuses a mode-losing adapter refresh',async()=>{
 const writes=new Map(),o=world();let selected=true;
 const api={now:()=>1000,inventoryUiOnlyV1:()=>selected,observe:async()=>o,write:(p,v)=>writes.set(p,v)};
 const runner=engine.create(api,{session:'ui',enableInput:true,inventoryUiOnlyV1:true});
 const frame=await runner.observe();assert.deepEqual(frame.uiObservation,o.uiObservation);
 assert.deepEqual(JSON.parse(writes.get('observation.json')).uiObservation,o.uiObservation);
 selected=false;await assert.rejects(runner.observe(),/mode changed/);
});

// Execute the actual main loop and engine with an inert adapter to exercise
// startup validation, pre-dispatch filtering and request-refresh option binding.
async function runMain(overrides={}){
 let now=10000,index=0;const calls=[],writes=new Map(),released=[];
 const requests=[{id:'bad',mission:'questStep',step:'wolfForward'},{id:'good',mission:'observe'},{id:'stop',mission:'stop'}];
 const adapterFactory=(sessionId,options)=>{
  let callback=null;
  calls.push(clone(options));
  return {inventoryUiOnlyV1:()=>options.inventoryUiOnlyV1===true,now:()=>now,setHeartbeat:value=>{callback=value;},
   heartbeat:(_,force)=>{if(callback)callback(force);},focusGame:async()=>{},
   checkStop(){},beginMission(){},events:()=>[],release:()=>released.push(true),write:(p,v)=>writes.set(p,v),
   observe:async(session,frame)=>({...world(),session,frameId:frame,timestamp:now,
    uiObservation:{...world().uiObservation,observationStartedAtUnixMs:now-1}})};
 };
 const box={Date:class extends Date{static now(){return now;}},Math,settings:{enableInput:true,autoEnterGame:false,inventoryUiOnlyV1:true,...overrides},
  adapterFactory,genshin:{isRemoteDesktopSession:true,windowsSessionId:5,betterGiProcessId:123,width:1920,height:1080},
  dispatcher:{clearAllTriggers(){}},getGameMetrics:()=>[1920,1080,1],setGameMetrics(){},log:{info(){}},
  sleep:async ms=>{now+=ms;if(now>20000)throw new Error('inert loop did not finish');},
  file:{captureStorageVersion:1,createDirectory:()=>true,writeTextSync:(p,v)=>{writes.set(p,v);return true;},
   isExists:p=>p==='request.json'||writes.has(p),
   readTextSync:p=>{
    if(p==='engine.js')return read(p);
    if(p==='bgi.js')return source+'\ncreateActOneAdapter=adapterFactory;';
    if(p==='mission.js')return 'var ActOneMission={};';
    if(p==='combat.js')return 'var ActOneCombat={};';
    if(p==='recovery.js')return 'var ActOneRecovery={};';
    if(p==='request.json'){const request=requests[index++];assert(request);const status=JSON.parse(writes.get('controller-status.json'));
     return JSON.stringify({...request,session:status.session,expectedFrameId:status.frameId,createdAt:now});}
    if(writes.has(p))return writes.get(p);throw new Error('Unexpected inert read '+p);
   }}};
 await vm.runInNewContext(read('main.js'),box,{filename:'actual-main-inert-ui-only.js'});
 return {calls,writes,released};
}
test('actual main rejects Wolf preprocessing and retains UI mode across valid refreshes',async()=>{
 const result=await runMain();
 assert.equal(result.calls.length,3);assert(result.calls.every(o=>o.inventoryUiOnlyV1===true));
 const bad=[...result.writes].find(([p])=>p.endsWith('/bad.json'));
 assert(bad);assert.equal(JSON.parse(bad[1]).status,'rejected');assert.match(JSON.parse(bad[1]).details.reason,/UI-only/);
 assert(result.released.length>0);
});
test('actual main refuses incompatible automatic entry before adapter construction',async()=>{
 await assert.rejects(runMain({autoEnterGame:true}),/requires autoEnterGame=false/);
 await assert.rejects(runMain({inventoryUiOnlyV1:'true'}),/must be a boolean/);
});
