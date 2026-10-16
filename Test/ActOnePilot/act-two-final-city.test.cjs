const test=require('node:test'),assert=require('node:assert/strict');
const exam=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam.js');
const o=require('./act-two-final-city-start.fixture.json');
test('recorded 60-second final course requires fresh timer health account and city region',()=>{
 assert.deepEqual(exam.state(o,o.timestamp,o.session),{kind:'groundOrFalling',timer:58});
 for(const bad of [{...o,map:{...o.map,x:0}},{...o,ocr:o.ocr.filter(r=>r.text!=='00:58')},{...o,session:'other'},{...o,timestamp:o.timestamp-1001}])assert.equal(exam.state(bad,o.timestamp,o.session),null);
 assert.equal(exam.fastState({space:true,health:o.hud.health},o.ocr),true);
});
test('final rooftop launch is bounded and requires recorded anchor',async()=>{
 let clock=o.timestamp,launched=0;const api={now:()=>clock,check(){},release(){},launch:async stationary=>{assert.equal(stationary,false);launched++;return {opened:true};}};
 const p={mode:'stepDown',holds:0,dx:0,dy:0};
 await exam.run(o,p,api,async()=>o);assert.equal(launched,1);
 await exam.run({...o,map:{...o.map,x:o.map.x-10}},p,api,async()=>o);assert.equal(launched,1);
});
test('saturated vertical markers stop after two ineffective corrections without advancing',async()=>{
 const launch=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam-launch.js');
 for(const y of [190,800,900]){
  let clock=0,forward=0,looks=[];
  const r=await launch.course({now:()=>clock,check(){},release(){},pause:async()=>{},sleep:async ms=>{clock+=ms;},look:async(x,dy)=>looks.push([x,dy]),forwardDown:()=>forward++,sample:async()=>({valid:true,space:true,health:{current:3953,max:4015},marker:{x:960,y},distance:20})});
  assert.equal(forward,0);assert.equal(r.pitchMoves,2);assert.match(r.reason,/did not improve twice/);assert(looks.every(([x,dy])=>x===0&&Math.abs(dy)<=250&&Math.sign(dy)===Math.sign(y-450)));
 }
});
test('final-stage short timer accepts five seconds but rejects four and over sixty',()=>{
 for(const [text,ok]of [['00:05',true],['00:04',false],['01:01',false]])assert.equal(exam.fastState({space:true,health:o.hud.health},o.ocr.map(r=>r.text==='00:58'?{...r,text}:r)),ok);
});
test('tower-side takeoff requires the reviewed clearance heading and rejects the overhang direction',async()=>{
 let launched=0;const base={...o,map:{map:'Teyvat',x:-777.359375,y:2240.9375,cameraAngle:346}};
 const api={now:()=>o.timestamp,check(){},release(){},launch:async()=>{launched++;return {opened:true};}};
 const p={mode:'stepDown',holds:0,dx:0,dy:0};await exam.run(base,p,api,async()=>base);assert.equal(launched,1);
 for(const patch of [{cameraAngle:10},{x:-780}])await exam.run({...base,map:{...base.map,...patch}},p,api,async()=>base);
 assert.equal(launched,1);
});
test('recorded final parapet climbing remains safe across camera orientation and trimmed timer',()=>{
 const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-town-recovery.js');
 const c=require('./act-two-final-city-11313.fixture.json');assert.equal(g.wallReady(c,c.timestamp,c.session),true);
 assert.equal(g.wallReady({...c,map:{...c.map,cameraAngle:35.5}},c.timestamp,c.session),true);
 assert.equal(g.wallReady({...c,map:{...c.map,x:-780}},c.timestamp,c.session),false);
 assert.equal(g.wallReady({...c,hud:{...c.hud,climbing:false}},c.timestamp,c.session),false);
});
test('recorded duplicate 60-second countdown objective preserves a separate valid field witness',()=>{
 const c=require('./act-two-final-city-11269.fixture.json');assert.equal(exam.state(c,c.timestamp,c.session).timer,57);
});
