'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const shore=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-starfell-shore.js');
const clone=value=>JSON.parse(JSON.stringify(value));

// The unknown-stamina swimming state matches retained shore attempt 01, frame 15.
function swimming(frameId=15,timestamp=10000){
 return {session:'shore-camera',frameId,timestamp,map:{map:'Teyvat',x:-1324.044921875,y:2558.1630859375,cameraAngle:137.49998474121094},
  hud:{world:true,groundControls:false,climbing:false,auto:false,dialogueReady:false,choice:false,journal:false,bigMap:false,
   health:{current:4015,max:4015},enemyBars:[],enemyBarDiagnostic:{level:'any',candidates:0,localReads:[],greenMask:null},objectives:[],
   starfellSwim:{source:'same-frame-swim-control',pixels:40,confirmed:true},swimStamina:{source:'same-frame-swim-stamina',pixels:0,boxes:[],height:null}},
  ocr:[{text:'UID 693306810',x:1682,y:1052,width:215,height:28}]};
}

// Pure tests fail if this inspection ever requests a movement or horizontal camera API.
function harness(initial=swimming(),change=()=>{}){
 let now=initial.timestamp,releases=0,observations=0;const pitches=[],sleeps=[];
 const api={session:initial.session,now:()=>now,release:()=>{releases++;},pitch:async(dy,o)=>{pitches.push({dy,frameId:o.frameId});},
  sleep:async ms=>{sleeps.push(ms);now+=ms;},observe:async()=>{observations++;const next=clone(initial);next.frameId++;next.timestamp=now;change(next);return next;},
  key:async()=>assert.fail('No movement key may be requested'),look:async()=>assert.fail('No yaw may be requested')};
 return {api,pitches,sleeps,releases:()=>releases,observations:()=>observations};
}

test('recorded unknown stamina permits one stationary inspection but still forbids continuation',async()=>{
 const initial=swimming(),f=harness(initial);assert.equal(shore.start(initial,10000,initial.session,true),false);
 const result=await shore.inspectCamera(initial,f.api);
 assert.equal(result.status,'stopped');assert.equal(result.stationaryVerified,true);assert.equal(result.actions,0);assert.equal(result.inputMs,0);
 assert.equal(result.cameraAdjustments,1);assert.equal(result.cameraDy,500);assert.equal(result.sourceFrameId,15);assert.equal(result.fieldFrameId,16);
 assert.equal(result.positionDelta,0);assert.deepEqual(result.health,{current:4015,max:4015});assert.equal(result.swimStamina.height,null);
 assert.equal(result.reason,'One stationary shore camera inspection; inspect stamina before continuation');
 assert.deepEqual(f.pitches,[{dy:500,frameId:15}]);assert.deepEqual(f.sleeps,[350]);assert.equal(f.observations(),1);assert.equal(f.releases(),1);
});

test('camera admission refuses stale, foreign, damaged, threatened and out-of-lane evidence without camera input',async()=>{
 const mutations=[o=>o.timestamp-=1001,o=>o.session='foreign',o=>o.hud.health.current=4014,o=>o.hud.health.max=4016,
  o=>o.hud.enemyBars.push({x:1}),o=>delete o.hud.enemyBarDiagnostic,o=>o.hud.objectives.push('A quest'),o=>o.hud.groundControls=true,
  o=>o.hud.starfellSwim.confirmed=false,o=>o.hud.starfellSwim.source='other',o=>o.hud.climbing=true,o=>o.hud.journal=true,
  o=>o.map.x+=5,o=>o.map.y=2580,o=>o.ocr=[],o=>o.frameId=null];
 for(const mutate of mutations){const initial=swimming(),f=harness(initial);mutate(initial);f.api.session='shore-camera';
  const result=await shore.inspectCamera(initial,f.api);assert.equal(result.cameraAdjustments,0);assert.equal(result.stationaryVerified,false);
  assert.equal(f.pitches.length,0);assert.equal(f.observations(),0);assert.equal(f.releases(),1);}
});

test('post-camera drift, health loss, repeated source, changed session and loss of swimming stay stopped',async()=>{
 const mutations=[o=>o.map.x+=0.501,o=>o.hud.health.current=4014,o=>o.frameId=15,o=>o.timestamp=10000,
  o=>o.session='foreign',o=>o.hud.starfellSwim.confirmed=false,o=>o.hud.groundControls=true,o=>o.hud.enemyBars.push({x:1})];
 for(const mutate of mutations){const initial=swimming(),f=harness(initial,mutate),result=await shore.inspectCamera(initial,f.api);
  assert.equal(result.cameraAdjustments,1);assert.equal(result.stationaryVerified,false);assert.equal(result.status,'stopped');
  assert.equal(f.pitches.length,1);assert.equal(f.releases(),1);}
});

test('half-unit drift is admitted and measured stamina is retained without movement',async()=>{
 const initial=swimming(),f=harness(initial,o=>{o.map.x+=0.5;o.hud.swimStamina={source:'same-frame-swim-stamina',pixels:200,boxes:[{x:1,y:1,width:4,height:50}],height:50};});
 const result=await shore.inspectCamera(initial,f.api);assert.equal(result.stationaryVerified,true);assert.equal(result.positionDelta,0.5);assert.equal(result.swimStamina.height,50);assert.equal(result.status,'stopped');
});

test('capture failure retains the returned camera call and always releases',async()=>{
 const initial=swimming(),f=harness(initial);f.api.observe=async()=>{throw Error('capture failed');};
 await assert.rejects(shore.inspectCamera(initial,f.api),error=>{assert.equal(error.message,'capture failed');assert.equal(error.fieldResult.cameraAdjustments,1);assert.equal(error.fieldResult.stationaryVerified,false);return true;});
 assert.equal(f.pitches.length,1);assert.equal(f.releases(),1);
});

// Reuse the inert real-adapter harness without registering its unrelated combat tests.
function adapterFixture(options={}){
 const source=fs.readFileSync(path.join(__dirname,'lion-field-combat-adapter.test.cjs'),'utf8');
 const sandbox={require,module:{exports:{}},__dirname,setImmediate};
 vm.runInNewContext(source.slice(0,source.indexOf('\nfunction assertPauseProof'))+'\nmodule.exports={fixture,row};',sandbox);
 const {fixture,row}=sandbox.module.exports;
 const rows=[row('4015/4015',900,1002,120,24),row('UID 693306810',1682,1052,215,28),row('Space',1680,1024,69,31)];
 const f=fixture({step:'actTwoStarfellShoreCamera',noEnemy:true,mapPosition:{map:'Teyvat',x:-1324.044921875,y:2558.1630859375},fieldRowsSequence:[rows],...options});
 const position=f.context.genshin.getPositionFromMap;
 f.context.genshin.getPositionFromMap=(...args)=>{if(f.getScreen()!=='field')throw Error('Inventory has no minimap');return position(...args);};
 const capture=f.context.captureGameRegion,moves=[];
 f.context.captureGameRegion=function(){const image=capture(),derive=image.deriveCrop;image.deriveCrop=function(x,y,w,h){const crop=derive(x,y,w,h);
  if(x===1819&&y===1028||x===1060&&y===560){crop.srcMat.cvtColor=function(){return {inRange(){return {samplePixels:x===1819?40:0,findContoursAsArray(){return [];},dispose(){}};},dispose(){}};};}
  return crop;};return image;};
 f.context.OpenCvSharp.OpenCvSharp.Cv2.countNonZero=mask=>mask.samplePixels||0;
 f.context.moveMouseBy=(dx,dy)=>{moves.push([dx,dy]);if(options.throwCamera)throw Error('camera call failed');};
 return {...f,moves,async runCamera(){const initial=await f.adapter.observe('lion-adapter-test',1);if(options.changeInitial)options.changeInitial(initial);return f.adapter.runActTwoStarfellShore(initial,f.observe);}};
}

test('actual adapter captures swim and threat sensors, sends one vertical camera call and verifies inventory pause',async()=>{
 const f=adapterFixture(),result=await f.runCamera();
 assert.equal(result.status,'stopped');assert.equal(result.stationaryVerified,true);assert.equal(result.cameraAdjustments,1);assert.equal(result.pauseVerified,true,JSON.stringify(result));
 assert.equal(result.pauseProof.kind,'inventory');assert.equal(f.getScreen(),'inventory');assert.deepEqual(f.moves,[[0,500]]);
 assert.deepEqual(clone(f.inputs.filter(x=>x.kind==='down').map(x=>x.key)),['VK_ESCAPE','VK_B']);assert.equal(f.nativeCalls.length,0);
 assert.ok(f.observations.some(o=>o.hud.starfellSwim&&o.hud.starfellSwim.confirmed&&o.hud.enemyBarDiagnostic&&o.hud.swimStamina.height===null));
 const events=f.adapter.events(),camera=events.filter(e=>e.type==='starfellShoreCamera');assert.equal(camera.length,1);
 assert.equal(camera[0].dx,0);assert.equal(camera[0].dy,500);assert.equal(camera[0].frameId,result.sourceFrameId);
 assert.ok(Number.isFinite(camera[0].startedAt)&&camera[0].finishedAt>=camera[0].startedAt);
 assert.ok(events.every(e=>['controllerRevision','key','starfellShoreCamera','pauseProtectionKey','pauseProtectionStarted','pauseProtectionVerified','pauseHostLatency'].includes(e.type)));
});

test('actual adapter rejects fresh damaged swimming before camera and still verifies inventory pause',async()=>{
 const rows=[{text:'4014/4015',x:900,y:1002,width:120,height:24},{text:'UID 693306810',x:1682,y:1052,width:215,height:28},{text:'Space',x:1680,y:1024,width:69,height:31}];
 const f=adapterFixture({fieldRowsSequence:[rows]}),result=await f.runCamera();
 assert.equal(result.cameraAdjustments,0);assert.equal(result.stationaryVerified,false);assert.equal(result.pauseVerified,true);assert.equal(f.moves.length,0);
 assert.deepEqual(clone(f.inputs.filter(x=>x.kind==='down').map(x=>x.key)),['VK_ESCAPE','VK_B']);
});

test('actual adapter retains camera failure, releases and returns to verified inventory without retry',async()=>{
 const f=adapterFixture({throwCamera:true}),result=await f.runCamera();
 assert.equal(result.status,'stopped');assert.equal(result.stationaryVerified,false);assert.match(result.reason,/camera call failed/);assert.equal(result.pauseVerified,true);
 assert.deepEqual(f.moves,[[0,500]]);assert.deepEqual(clone(f.inputs.filter(x=>x.kind==='down').map(x=>x.key)),['VK_ESCAPE','VK_B']);
});

test('actual adapter STOP after inventory close prevents camera input',async()=>{
 const f=adapterFixture({stopAfterClose:true});
 const result=await f.runCamera();assert.match(result.reason,/stop/i);assert.equal(result.pauseVerified,true);assert.equal(f.moves.length,0);assert.ok(!f.inputs.some(x=>x.kind==='down'&&x.key==='VK_W'));
});

test('actual adapter refuses stale, foreign or incomplete inventory before Escape',async()=>{
 for(const changeInitial of [o=>o.timestamp-=1001,o=>o.session='foreign',o=>o.ocr=o.ocr.filter(r=>r.text!=='Teyvat Fried Egg')]){
  const f=adapterFixture({changeInitial});await assert.rejects(f.runCamera(),/Fresh Inventory/);assert.equal(f.moves.length,0);assert.equal(f.inputs.length,0);
 }
});

test('actual adapter post-camera capture failure retains one attempt and still pauses from a subsequent fresh field',async()=>{
 const f=adapterFixture();let observed=0;
 const initial=await f.adapter.observe('lion-adapter-test',1),result=await f.adapter.runActTwoStarfellShore(initial,async()=>{
  if(++observed===2)throw Error('post-camera capture failed');return f.observe();
 });
 assert.equal(result.status,'stopped');assert.equal(result.cameraAdjustments,1);assert.equal(result.stationaryVerified,false);assert.match(result.reason,/post-camera capture failed/);
 assert.equal(result.pauseVerified,true);assert.deepEqual(f.moves,[[0,500]]);assert.deepEqual(clone(f.inputs.filter(x=>x.kind==='down').map(x=>x.key)),['VK_ESCAPE','VK_B']);
});

test('mission routes only the explicit camera step through the existing inventory wrapper',async()=>{
 const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js'),initial=swimming(),observe=async()=>{};
 let calls=0;const expected={status:'stopped',stationaryVerified:true};
 const result=await mission.runQuestStep('actTwoStarfellShoreCamera',initial,{runActTwoStarfellShore:async(o,reader)=>{
  calls++;assert.equal(o,initial);assert.equal(reader,observe);return expected;
 }},observe);
 assert.equal(calls,1);assert.equal(result,expected);
});
