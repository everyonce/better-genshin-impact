const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');
const edge=require('./act-two-hideout-windmill-edge.fixture.json'),falling=require('./act-two-hideout-windmill-falling.fixture.json'),fallen=require('./act-two-hideout-windmill-fallen.fixture.json');
test('recorded ladder crossing is rejected before forward input despite ground controls',()=>{
 const action={type:'key',key:'VK_W',ms:600};assert(g.retiredWindmillCrossing(edge,action));
 assert.equal(g.originalWitnessFailure(edge,{witnessFrameId:edge.frameId,frameId:edge.frameId+2,mode:'actions',actions:[action]},{session:edge.session},edge.timestamp),'retired_windmill_ladder_crossing');
 assert.equal(g.retiredWindmillCrossing(edge,{type:'look',dx:750,dy:0}),false);
 const turned=structuredClone(edge);turned.map.cameraAngle=90;assert.equal(g.retiredWindmillCrossing(turned,action),false);
});
test('recorded falling E/Q controls are not stable ground or a safe landing',()=>{
 assert.equal(falling.hud.groundControls,true);
 assert.equal(g.windmillGroundStable(edge,falling),false);
 assert.equal(g.windmillGroundStable(falling,fallen),false);
});
test('settled ground needs delayed distinct frames, exact health, location, height and session',()=>{
 const a=require('./act-two-hideout-riddle-ground.fixture.json'),b=structuredClone(a);b.timestamp+=1000;b.frameId++;
 assert(g.windmillGroundStable(a,b));
 for(const mutate of [v=>v.timestamp=a.timestamp+699,v=>v.frameId=a.frameId,v=>v.session='other',v=>v.hud.health.current--,v=>v.map.x++,v=>v.hud.objectives=['Look for the location in the riddle','Higher 28m'],v=>v.hud.climbing=true]){const c=structuredClone(b);mutate(c);assert.equal(g.windmillGroundStable(a,c),false);}
});
test('recorded post-action OCR punctuation cannot skip settling or allow the next movement',async()=>{
 const recorded=require('./act-two-hideout-windmill-ocr.fixture.json');
 const initial=structuredClone(recorded);initial.timestamp=1000;initial.hud.objectives=['Look for the location in the riddle','Higher 8m'];
 let now=1000,actions=0,released=0,reads=0;const waits=[];
 const api={now:()=>now,checkStop(){},action:async()=>actions++,sleep:async n=>{waits.push(n);now+=n;},release:async()=>released++};
 const observe=async()=>{const o=structuredClone(recorded);o.timestamp=now;o.frameId+=++reads;return o;};
 const result=await g.run(initial,initial,{mode:'actions',actions:[{type:'key',key:'VK_W',ms:250},{type:'key',key:'VK_W',ms:250}]},api,observe);
 assert.equal(actions,1);assert(waits.includes(800));assert.equal(result.groundSettled,false);assert.match(result.reason,/did not settle safely/);assert.equal(released,1);
});
