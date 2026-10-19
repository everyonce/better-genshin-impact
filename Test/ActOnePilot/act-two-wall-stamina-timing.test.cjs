const test=require('node:test'),assert=require('node:assert/strict');
const timing=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-wall-stamina-timing.js');
const gate=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/world-inventory.js').worldInventoryClosePermission;
const ground=require('./act-two-wall-stamina-ground.fixture.json');
const climbing=require('./act-two-riddle-broad-wall-settled.fixture.json');
const clone=x=>JSON.parse(JSON.stringify(x));
function harness(samples,options={}){let now=ground.timestamp,frame=ground.frameId,downAt=null,keys=[],releases=0;const queue=samples.map(clone);
 const api={now:()=>now,check(){if(options.focusLost)throw Error('focus lost');},sleep:async ms=>{now+=ms;},release:async()=>{releases++;downAt=null;},down:async()=>{keys.push(['VK_W','down']);downAt=now;},key:async(k,ms)=>{keys.push([k,ms]);},sample:async label=>{if(options.sampleError)throw Error('capture failed');return {valid:true,capturedAt:now,stamina:{kind:options.signal?'usable':'absent',pixels:options.signal?320:null,height:options.signal?54:null},label};},observe:async()=>{let o=queue.shift();if(!o)throw Error('missing observation');o.session=ground.session;o.frameId=++frame;o.timestamp=now;return o;}};
 return {run:()=>timing.run(ground,api),counts:()=>({keys,releases,downAt})};}
test('real safe wall pose permits a distinct timing review',()=>{
 assert(timing.entry(ground,ground.session,ground.timestamp));
 assert(timing.attached(climbing,climbing.session,climbing.timestamp));
 for(const mutate of [o=>o.map.x+=.3,o=>o.map.cameraAngle=310,o=>o.hud.health.current--,o=>o.hud.objectives=['Higher 25m']]){const o=clone(ground);mutate(o);assert(!timing.entry(o,o.session,o.timestamp));}
});
test('one short W hold, timed captures and one X release return to verified ground',async()=>{
 const h=harness([climbing,ground]),r=await h.run();assert.equal(r.groundRecovered,true);assert.equal(r.inputs,2);assert(r.forwardHoldMs<=250);assert.deepEqual(r.fastSamples.map(s=>[s.label,s.relativeHoldMs]),[['held-early',80],['held-late',210],['after-forward-release',210]]);assert.deepEqual(h.counts().keys,[['VK_W','down'],['VK_X',60]]);assert(h.counts().releases>=3);
});
test('yellow candidate cannot become verified stamina without visual confirmation',async()=>{
 const h=harness([climbing,ground],{signal:true}),r=await h.run();assert.equal(r.staminaCandidate,true);assert.equal(r.staminaVerified,false);assert.equal(r.groundRecovered,true);
});
test('short forward contact that stays grounded never sends X or claims climb',async()=>{
 const h=harness([ground]),r=await h.run();assert.equal(r.climbingObserved,undefined);assert.equal(r.groundRecovered,true);assert.equal(r.inputs,1);assert.deepEqual(h.counts().keys,[['VK_W','down']]);
});
test('capture failure releases W and uses one fresh guarded X recovery',async()=>{
 const h=harness([climbing,ground],{sampleError:true}),r=await h.run();assert.equal(r.recoveredAfterFailure,true);assert.equal(r.groundRecovered,true);assert.deepEqual(h.counts().keys,[['VK_W','down'],['VK_X',60]]);assert(h.counts().releases>=2);
});
test('changed ground pose never starts W',async()=>{
 const o=clone(ground);o.map.x+=1;let keys=0,releases=0;const r=await timing.run(o,{now:()=>o.timestamp,check(){},release:async()=>releases++,down:async()=>keys++,sample:async()=>{throw Error('unexpected');},observe:async()=>{throw Error('unexpected');}});assert.equal(keys,0);assert.equal(r.inputs,0);assert(releases>0);
});
