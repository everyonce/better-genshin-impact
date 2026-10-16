const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam.js'),o=require('./act-two-city-exam-start.fixture.json');
test('recorded city countdown overlay retains exact active trial timer and guarded region',()=>{
 assert.deepEqual(g.state(o,o.timestamp,o.session),{kind:'groundOrFalling',timer:177});
 for(const patch of [{map:{...o.map,x:-650}},{map:{...o.map,y:2400}},{map:{...o.map,x:-950}},{hud:{...o.hud,health:{current:3000,max:4015}}},{ocr:o.ocr.filter(r=>!r.text.includes('02:57'))},{ocr:o.ocr.filter(r=>!r.text.includes('693306810'))},{ocr:o.ocr.map(r=>r.text.startsWith('Reach')?{...r,text:'Reach the target location'}:r)}])assert.equal(g.state({...o,...patch},o.timestamp,o.session),null);
 assert.equal(g.state(o,o.timestamp+1001,o.session),null);
});
test('city takeoff uses existing bounded deployment only at the visually verified wind current',async()=>{
 const o=require('./act-two-city-current.fixture.json');
 let launches=0,releases=0;const api={now:()=>o.timestamp,check(){},release(){releases++;},launch:async stationary=>{assert.equal(stationary,true);launches++;return {opened:true};}};
 const p={mode:'launch',stationary:true,holds:0,dx:0,dy:0};await g.run(o,p,api,async()=>o);assert.equal(launches,1);assert.equal(releases,1);
 const r=await g.run({...o,map:{...o.map,x:o.map.x+4}},p,api,async()=>o);assert.match(r.reason,/Reviewed exam start platform/);assert.equal(launches,1);
 const old=require('./act-two-city-exam-start.fixture.json');const retired=await g.run(old,p,{...api,now:()=>old.timestamp},async()=>old);assert.match(retired.reason,/Reviewed exam start platform/);assert.equal(launches,1);
});
