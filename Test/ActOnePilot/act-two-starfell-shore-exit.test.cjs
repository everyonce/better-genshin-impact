'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const shore=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-starfell-shore.js');
const clone=value=>JSON.parse(JSON.stringify(value));
const landmark={x:-1313.8046875,y:2547.23046875};

// Retained continuation 03 frame 3: full Kaeya, positive swimming and a 37-pixel measured arc.
function endpoint(){return {session:'shore-exit',frameId:3,timestamp:10000,map:{map:'Teyvat',x:-1316.60546875,y:2550.9169921875,cameraAngle:137.49998474121094},
 hud:{world:true,groundControls:false,climbing:false,auto:false,dialogueReady:false,choice:false,journal:false,bigMap:false,
  health:{current:4015,max:4015},enemyBars:[],enemyBarDiagnostic:{level:'any',candidates:0,localReads:[],greenMask:null},objectives:[],
  starfellSwim:{source:'same-frame-swim-control',pixels:40,confirmed:true},swimStamina:{source:'same-frame-swim-stamina',pixels:199,boxes:[{x:3,y:32,width:10,height:37}],height:37}},
 ocr:[{text:'UID 693306810',x:1682,y:1052,width:215,height:28}]};}

// Inert movement advances toward the fixed landmark; callbacks can inject changed fresh evidence.
function harness(initial=endpoint(),change=()=>{}){
 let now=10000,current=clone(initial),releases=0,observations=0,lastAction=null;const keys=[],looks=[],sleeps=[];
 const api={now:()=>now,session:'shore-exit',release:()=>{releases++;},sleep:async ms=>{sleeps.push(ms);now+=ms;},pitch:async()=>assert.fail('Exit must never pitch'),
  key:async(k,ms,o)=>{keys.push({k,ms,frameId:o.frameId});lastAction='key';now+=ms;},look:async(dx,o)=>{looks.push({dx,frameId:o.frameId});lastAction='look';},
  observe:async()=>{observations++;current=clone(current);current.frameId++;current.timestamp=now;
   if(lastAction==='key'){current.map.x+=(landmark.x-initial.map.x)/8;current.map.y+=(landmark.y-initial.map.y)/8;}
   if(lastAction==='look')current.map.cameraAngle=(Math.atan2(current.map.y-landmark.y,current.map.x-landmark.x)*180/Math.PI+360)%360;
   change(current,{keys:keys.length,looks:looks.length,lastAction});return current;}};
 return {api,keys,looks,sleeps,releases:()=>releases,observations:()=>observations};
}

test('retained 37-pixel endpoint admits only the distinct near-shore exit',async()=>{
 const o=endpoint();assert.equal(shore.start(o,10000,o.session,true),false);assert.equal(shore.exitReady(o,10000,o.session,false),true);
 const f=harness(o),result=await shore.runExit(o,f.api);
 assert.equal(result.status,'stopped');assert.equal(result.actions,6);assert.equal(result.inputMs,3600);assert.equal(result.pitchAdjustments,0);
 assert.equal(result.turns,0);assert.equal(result.swimmingObserved,true);assert.deepEqual(result.target,landmark);assert.equal(result.positions.length,6);
 assert.ok(f.keys.every(k=>k.k==='VK_W'&&k.ms===600));assert.equal(f.releases(),1);assert.match(result.reason,/Bounded near-shore exit/);
});

test('entry threshold is35 and movement floor remains25',async()=>{
 for(const height of [34,35,37,40]){const o=endpoint();o.hud.swimStamina.height=height;assert.equal(shore.exitReady(o,10000,o.session,false),height>=35);}
 for(const height of [24,25,26]){const o=endpoint();o.hud.swimStamina.height=height;assert.equal(shore.exitReady(o,10000,o.session,true),height>=25);}
 const o=endpoint(),f=harness(o,(next,{keys})=>{next.hud.swimStamina.height=keys===1?25:24;}),result=await shore.runExit(o,f.api);
 assert.equal(result.actions,2);assert.equal(result.staminaEvidence.height,24);assert.equal(result.status,'stopped');assert.equal(f.keys.length,2);
});

test('unknown stamina, wrong source and changed entry identity or scope cause zero inputs without rereads',async()=>{
 const changes=[o=>o.hud.swimStamina.height=null,o=>delete o.hud.swimStamina,o=>o.hud.swimStamina.source='other',o=>o.hud.starfellSwim.confirmed=false,
  o=>o.hud.starfellSwim.source='other',o=>o.hud.groundControls=true,o=>o.hud.health.current=4014,o=>o.hud.enemyBars.push({x:1}),o=>delete o.hud.enemyBarDiagnostic,
  o=>o.hud.objectives.push('Quest'),o=>o.session='foreign',o=>o.timestamp=8999,o=>o.map.y=2575,o=>o.map.x-=5,
  o=>{o.map.x=landmark.x-1;o.map.y=landmark.y;},o=>o.map.x=String(o.map.x),o=>o.ocr=[]];
 for(const change of changes){const o=endpoint();change(o);const f=harness(o),result=await shore.runExit(o,f.api);
  assert.equal(result.actions,0,change.toString());assert.equal(f.keys.length,0);assert.equal(f.looks.length,0);assert.equal(f.observations(),0);assert.equal(f.sleeps.length,0);assert.equal(f.releases(),1);}
});

test('distance bound includes6units and excludes any farther source',()=>{
 const o=endpoint(),dx=o.map.x-landmark.x,dy=o.map.y-landmark.y,d=Math.hypot(dx,dy);
 for(const radius of [5.999,6.001]){const p=clone(o);p.map.x=landmark.x+dx/d*radius;p.map.y=landmark.y+dy/d*radius;
  assert.equal(shore.exitReady(p,10000,p.session,false),radius<6);}
});

test('ground recognition after the first or sixth hold completes immediately without another input',async()=>{
 for(const landAfter of [1,6]){const o=endpoint(),f=harness(o,(next,{keys})=>{if(keys===landAfter){next.hud.groundControls=true;next.hud.starfellSwim.confirmed=false;next.hud.swimStamina.height=null;}}),result=await shore.runExit(o,f.api);
  assert.equal(result.status,'completed');assert.equal(result.actions,landAfter);assert.equal(f.keys.length,landAfter);assert.equal(result.reason,'Ground controls regained after verified swim');assert.equal(f.releases(),1);}
});

test('unknown, low stamina, health loss and scope changes after a turn prevent W',async()=>{
 const changes=[o=>o.hud.swimStamina.height=null,o=>o.hud.swimStamina.height=24,o=>o.hud.health.current=4014,o=>o.hud.enemyBars.push({x:1}),o=>o.map.x-=8,o=>o.map.y+=5,o=>o.timestamp-=1001];
 for(const change of changes){const o=endpoint();o.map.cameraAngle=0;const f=harness(o,change);let result;
  try{result=await shore.runExit(o,f.api);}catch(error){result=error.fieldResult;}
  assert.equal(result.status,'stopped');assert.equal(result.actions,0);assert.equal(f.looks.length,1);assert.equal(f.keys.length,0);assert.equal(f.releases(),1);}
});

test('ground recognition after a turn stops without a W hold',async()=>{
 const o=endpoint();o.map.cameraAngle=0;const f=harness(o,next=>{next.hud.groundControls=true;next.hud.starfellSwim.confirmed=false;}),result=await shore.runExit(o,f.api);
 assert.equal(result.status,'completed');assert.equal(result.actions,0);assert.equal(result.turns,1);assert.equal(f.keys.length,0);
});

test('post-hold sensor changes stop before another hold and retain the hazardous frame',async()=>{
 for(const change of [o=>o.hud.swimStamina.height=null,o=>o.hud.health.current=4014,o=>o.hud.enemyBars.push({x:1}),o=>o.map.x-=8]){
  const initial=endpoint(),f=harness(initial,change),result=await shore.runExit(initial,f.api);
  assert.equal(result.status,'stopped');assert.equal(result.actions,1);assert.equal(result.fieldFrameId,4);assert.equal(f.keys.length,1);assert.equal(f.releases(),1);
 }
});

test('repeated source and capture exceptions retain admitted holds and release',async()=>{
 for(const fail of ['repeated','capture']){const o=endpoint(),f=harness(o,next=>{next.frameId=o.frameId;});if(fail==='capture')f.api.observe=async()=>{throw Error('capture failed');};
  await assert.rejects(shore.runExit(o,f.api),error=>{assert.equal(error.fieldResult.actions,1);assert.equal(error.fieldResult.inputMs,600);return true;});assert.equal(f.keys.length,1);assert.equal(f.releases(),1);}
});

test('two fresh no-progress holds stop without a third W',async()=>{
 const initial=endpoint(),f=harness(initial,next=>{next.map.x=initial.map.x;next.map.y=initial.map.y;}),result=await shore.runExit(initial,f.api);
 assert.equal(result.status,'stopped');assert.equal(result.actions,2);assert.equal(result.inputMs,1200);assert.equal(result.positions.length,2);
 assert.equal(f.keys.length,2);assert.equal(f.observations(),2);assert.equal(result.reason,'Two near-shore steps made no progress');assert.equal(f.releases(),1);
});

test('three unsettled yaw corrections stop with zero W',async()=>{
 const initial=endpoint();initial.map.cameraAngle=0;
 const f=harness(initial,next=>{next.map.cameraAngle=0;}),result=await shore.runExit(initial,f.api);
 assert.equal(result.status,'stopped');assert.equal(result.actions,0);assert.equal(result.inputMs,0);assert.equal(result.turns,3);
 assert.equal(f.looks.length,3);assert.ok(f.looks.every(turn=>Math.abs(turn.dx)<=600));assert.equal(f.keys.length,0);assert.equal(f.observations(),3);
 assert.equal(result.reason,'Near-shore heading did not settle');assert.equal(f.releases(),1);
});

// Reuse the actual adapter harness while suppressing registration of the camera test cases.
function actualExitFixture(){
 const file=path.join(__dirname,'act-two-starfell-shore-camera.test.cjs'),context={require:name=>name==='node:test'?()=>{}:require(name),module:{exports:{}},__dirname,setImmediate};
 vm.runInNewContext(fs.readFileSync(file,'utf8')+'\nmodule.exports={adapterFixture};',context);
 const original=endpoint(),f=context.module.exports.adapterFixture({step:'actTwoStarfellShoreExit',mapPosition:original.map});
 let holds=0;const down=f.context.keyDown,capture=f.context.captureGameRegion;
 f.context.keyDown=key=>{if(key==='VK_W')holds++;return down(key);};
 f.context.genshin.getCameraOrientation=()=>137.49998474121094;
 f.context.captureGameRegion=()=>{const image=capture(),derive=image.deriveCrop;image.deriveCrop=(x,y,w,h)=>{const crop=derive(x,y,w,h);if(x===1060&&y===560)crop.srcMat.cvtColor=()=>({inRange:()=>({samplePixels:199,findContoursAsArray:()=>[{x:3,y:32,width:10,height:holds?24:37}],dispose(){}}),dispose(){}});return crop;};return image;};
 return f;
}

test('actual adapter captures measured37, dispatches one W600, then stops on a sub25 unknown arc and verifies inventory pause',async()=>{
 const f=actualExitFixture(),result=await f.runCamera();
 assert.equal(result.status,'stopped');assert.equal(result.actions,1);assert.equal(result.inputMs,600);assert.equal(result.staminaEvidence.height,null);assert.equal(result.staminaEvidence.boxes[0].height,24);assert.equal(result.pauseVerified,true);assert.equal(result.pauseProof.kind,'inventory');
 assert.deepEqual(clone(f.inputs.filter(x=>x.kind==='down').map(x=>x.key)),['VK_ESCAPE','VK_W','VK_B']);assert.equal(f.moves.length,0);
 const movement=f.adapter.events().filter(e=>e.type==='key'&&e.key==='VK_W');assert.equal(movement.length,1);assert.equal(movement[0].durationMs,600);
 assert.ok(f.observations.some(o=>o.hud.swimStamina&&o.hud.swimStamina.height===37&&o.hud.enemyBarDiagnostic));
});

test('mission routes the separately named exit through the inventory wrapper',async()=>{
 const mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js'),initial=endpoint(),observe=async()=>{};let calls=0;
 const result=await mission.runQuestStep('actTwoStarfellShoreExit',initial,{runActTwoStarfellShore:async(o,reader)=>{calls++;assert.equal(o,initial);assert.equal(reader,observe);return {status:'stopped'};}},observe);
 assert.equal(calls,1);assert.equal(result.status,'stopped');
});
