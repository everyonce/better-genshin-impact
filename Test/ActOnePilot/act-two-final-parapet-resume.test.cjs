const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-final-trial.js'),o=require('./act-two-final-parapet-resume.fixture.json');
test('new recorded standing parapet is an exact resume location; neighboring wall is not',()=>{assert(g.resumePosition(o.map));assert(!g.resumePosition({...o.map,x:o.map.x+.3}));assert(!g.resumePosition({...o.map,map:'domain'}));});
test('recorded healthy47-second parapet reaches proven point with one released short step',async()=>{
 let released=0,launches=0,keys=[];const r=await g.run(o,{resume:true,now:()=>1000,check(){},sleep:async()=>{},release:()=>released++,look:async()=>{},observe:async()=>({...o,map:{...o.map,x:-777.990234375,y:2240.7216796875}}),launch:async()=>{launches++;return{opened:false};},key:async(k,ms)=>keys.push([k,ms]),wallJump:async()=>assert.fail('no wall jump allowed')});
 assert.deepEqual(keys,[['VK_W',150]]);
 assert.equal(launches,1);assert.equal(r.wallJumps,0);assert.equal(r.climbHolds,0);assert.match(r.reason,/Glider not positively verified/);assert.equal(released,1);
});
test('short step that stays adjacent or loses ground never deploys',async()=>{
 for(const after of [o,{...o,hud:{...o.hud,groundControls:false,climbing:true}}]){
 let keys=0,released=0;const r=await g.run(o,{resume:true,now:()=>1000,check(){},sleep:async()=>{},release:()=>released++,look:async()=>{},observe:async()=>after,key:async()=>keys++,launch:async()=>assert.fail('unverified clearance')});
 assert.equal(keys,1);assert.equal(released,1);assert.match(r.reason,/proven launch position|Fresh healthy/);
 }
});
