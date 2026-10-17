const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-launch-practice.js');
const o={session:'test',timestamp:1000,map:{map:'Teyvat',x:-1266.35,y:1934.03},hud:{world:true,groundControls:true,health:{current:4015,max:4015},enemyBars:[],objectives:['Follow the route and fly to the finish line in time']},ocr:[{text:'UID: 693306810',x:1700,y:1050}]};
test('retired eastern root is rejected even when its camera matches the successful pose',()=>{
 const t=require('./act-two-launch-trunk.fixture.json'),field=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');assert(!g.ready(t,t.timestamp,t.session));assert(!g.ready({...t,map:{...t.map,cameraAngle:202}},t.timestamp,t.session));assert(!field.ready(t,t,t.timestamp,t.session,true,false,false,false,null,false,false,true));
});
test('stationary launch practice is confined to reviewed flat Windrise paving',()=>{
 assert.equal(g.ready(o,1000,'test'),true);
 for(const patch of [{session:'other'},{timestamp:-1},{map:{...o.map,x:-778}},{hud:{...o.hud,health:{current:3212,max:4015}}},{hud:{...o.hud,climbing:true}},{hud:{...o.hud,enemyBars:[{}]}},{hud:{...o.hud,groundControls:false}},{hud:{...o.hud,objectives:['Talk to Amber']}},{ocr:[]}])assert.equal(g.ready({...o,...patch},1000,'test'),false);
});
test('known low trunk allows the current final objective only with both climbing bindings',()=>{
 const t={...o,map:{...o.map,x:-1266.30078,y:1892.93359,cameraAngle:202},hud:{...o.hud,groundControls:false,climbing:true},ocr:[...o.ocr,{text:'X',x:1600,y:1000},{text:'Space',x:1700,y:1000}]};assert(g.ready(t,1000,'test'));assert(!g.ready({...t,ocr:t.ocr.filter(r=>r.text!=='X')},1000,'test'));
});
test('drop uses actual launch routine then only released observation through landing',async()=>{
 const launch=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam-launch.js');let now=0,keys=[],reads=0,releases=0;
 const r=await g.run({now:()=>now,check(){},drop:async()=>{keys.push('X');now+=60},pressSpace:async()=>{keys.push('Space');now+=60},forwardDown(){assert.fail('stationary')},sleep:async n=>now+=n,release:()=>releases++,sample:async()=>{reads++;return {valid:true,space:reads>=2&&reads<=4,groundControls:reads===1||reads>=5}},pause:async()=>assert.fail('open')},launch,true);
 assert.deepEqual(keys,['X','Space']);assert.equal(r.deployment.opened,true);assert.equal(r.deployment.deployPresses,1);assert.equal(r.groundControlsConfirmed,true);assert.equal(reads,6);assert(releases>=6);
});
test('recorded successful drop preserves one-press deployment and five flight observations',async()=>{
 const trace=require('./act-two-single-press-trace.fixture.json'),setup=require('./act-two-original-trunk.fixture.json'),launch=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam-launch.js');
 assert(g.ready(setup,setup.timestamp,setup.session));const samples=[...trace.deployment.samples,...trace.landingSamples];let now=0,keys=[],index=0;
 const result=await g.run({now:()=>now,check(){},drop:async()=>keys.push('X'),pressSpace:async()=>keys.push('Space'),sleep:async n=>now+=n,release(){},sample:async()=>samples[index++],pause:async()=>assert.fail('recorded positive')},launch,true);
 assert.deepEqual(keys,['X','Space']);assert(result.deployment.opened);assert(result.groundControlsConfirmed);assert.equal(samples.filter(s=>s.space).length,5);
});
