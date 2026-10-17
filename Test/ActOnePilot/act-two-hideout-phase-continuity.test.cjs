const test=require('node:test'),assert=require('node:assert/strict');
const reader=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat-target-state.js'),reactor=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat-phase-reactor.js');
const actual=require('./act-two-hideout-phase-continuity.fixture.json');
test('recorded edge label remains eligible after camera zoom; another exact enemy is ambiguous',()=>{
 const rows=actual['18415'].ocr,labels=reader.labels(rows,13);assert.equal(labels.length,1);assert.equal(labels[0].x,181);
 assert.equal(reader.labels(rows.concat([{...labels[0],x:900}]),13).length,2);
});
test('fresh unique target continuity accepts measured camera zoom and rejects jumps,stale and wrong identity',()=>{
 const before=structuredClone(actual['18414']),after=structuredClone(actual['18415']);after.hud.combatTargetState=require('./act-two-hideout-phase-continuity-result.fixture.json').frames[1].targetState;
 assert(reactor.sameTarget(before,after));
 for(const mutate of [o=>o.session='other',o=>o.frameId=before.frameId,o=>o.timestamp=before.timestamp+3501,o=>o.hud.combatTargetState.level=12,o=>o.hud.combatTargetState.tracking='ambiguous',o=>o.hud.combatTargetState.target.x=1500,o=>o.hud.combatTargetState.target.width=300]){const o=structuredClone(after);mutate(o);assert.equal(reactor.sameTarget(before,o),false);}
});
test('no-charge and missing-target are separate; absence never grants movement or a cast',async()=>{
 let now=1000,reads=0,inputs=0,releases=0;const o={session:'s',timestamp:now,frameId:1,ocr:[{text:'693306810',x:1700,y:1050}],hud:{world:true,groundControls:true,health:{current:4015,max:4015},objectives:['Defeat all opponents 6/7'],combatTargetState:{level:13,tracking:'tracked',charge:'absent',phase:'unknown',target:{x:960,y:400,width:70,height:6}}}};
 const api={now:()=>now,checkStop:()=>{},safe:()=>true,sleep:async n=>now+=n,release:()=>releases++,look:async()=>inputs++,avoid:async()=>inputs++,cast:async()=>{inputs++;return{}},observe:async()=>{now+=700;reads++;return {...o,timestamp:now,frameId:1+reads};}};
 const r=await reactor.run(o,api);assert.equal(inputs,0);assert.equal(reads,2);assert.equal(r.reason,'phase_reactor_no_charge_observed');assert.equal(releases,1);
});

test('actual replay recovers enlarged edge charge without changing the prior absent-charge frame',()=>{const v=require('./act-two-hideout-phase-continuity-result.fixture.json');assert.equal(v.inputs,0);assert.deepEqual(v.frames.map(x=>[x.targetState.tracking,x.targetState.charge]),[['tracked','absent'],['tracked','present']]);assert.equal(v.frames[1].targetState.phase,'charging-shield');});
test('recorded non-converging camera correction retains identity but stops further input',async()=>{
 const before=structuredClone(actual['18414']),after=structuredClone(actual['18415']);const replay=require('./act-two-hideout-phase-continuity-result.fixture.json');before.hud.combatTargetState=replay.frames[0].targetState;after.hud.combatTargetState=replay.frames[1].targetState;
 let now=before.timestamp,looks=0,casts=0,releases=0;after.timestamp=now+1200;
 const api={now:()=>now,checkStop:()=>{},safe:()=>true,sleep:async n=>now+=n,release:()=>releases++,look:async()=>looks++,cast:async()=>casts++,observe:async()=>{now=after.timestamp;return after;}};
 const r=await reactor.run(before,api);assert.equal(looks,1);assert.equal(casts,0);assert.equal(r.reacquisitions,1);assert.equal(r.reason,'phase_reactor_camera_not_converging');assert.equal(releases,1);
});
