const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam.js'),o=require('./act-two-city-exam-start.fixture.json');

test('recorded city completion grants only bounded airborne Talk to Amber continuation',()=>{
 const f=require('./act-two-city-trial-finish.fixture.json');assert.equal(g.afterTrial(f,f.timestamp,f.session),true);assert.equal(g.state(f,f.timestamp,f.session),null);
 for(const patch of [{session:'other'},{map:{...f.map,x:-650}},{hud:{...f.hud,groundControls:true}},{hud:{...f.hud,health:{current:3000,max:4015}}},{ocr:f.ocr.filter(r=>r.text!=='Talk to Amber')},{ocr:[...f.ocr,{text:'01:30',x:930,y:45}]},{ocr:f.ocr.filter(r=>!r.text.endsWith('693306810'))}])assert.equal(g.afterTrial({...f,...patch},f.timestamp,f.session),false);
 assert.equal(g.afterTrial(f,f.timestamp+1001,f.session),false);
 const sample={space:true,health:{max:4015,current:3953}};assert.equal(g.fastState(sample,f.ocr,true),true);assert.equal(g.fastState(sample,f.ocr,false),false);assert.equal(g.fastState(sample,[...f.ocr,{text:'01:30',x:930,y:45}],true),false);
 const p={reviewed:true,session:'s',frameId:2,witnessFrameId:1,createdAt:1,mode:'flight',holds:4,dx:0,dy:0,afterTrial:true};assert.equal(g.plan(p,{session:'s',expectedFrameId:2},2),true);assert.equal(g.plan({...p,mode:'launch'},{session:'s',expectedFrameId:2},2),false);assert.equal(g.plan({...p,mode:'course'},{session:'s',expectedFrameId:2},2),false);
});

test('recorded post-trial roof ground permits finite walking but stops on loss of ground',async()=>{
 const f=require('./act-two-city-roof-ground.fixture.json');assert.equal(g.afterTrial(f,f.timestamp,f.session,true),true);assert.equal(g.afterTrial(f,f.timestamp,f.session,false),false);
 const landed=require('./act-two-city-roof-landed.fixture.json');assert.equal(g.afterTrial(landed,landed.timestamp,landed.session,true),true);
 let n=0;const api={now:()=>f.timestamp,check(){},release(){},key:async()=>n++,sleep:async()=>{}};
 const r=await g.run(f,{mode:'ground',afterTrial:true,dx:0,dy:0,holds:4},api,async()=>({...f,hud:{...f.hud,groundControls:false}}));assert.equal(n,1);assert.match(r.reason,/phase/);
 assert.equal(g.afterTrial({...f,ocr:[...f.ocr,{text:'01:30',x:930,y:45}]},f.timestamp,f.session,true),false);
});
test('recorded city countdown overlay retains exact active trial timer and guarded region',()=>{
 assert.deepEqual(g.state(o,o.timestamp,o.session),{kind:'groundOrFalling',timer:177});
 for(const patch of [{map:{...o.map,x:-650}},{map:{...o.map,y:2400}},{map:{...o.map,x:-950}},{hud:{...o.hud,health:{current:3000,max:4015}}},{ocr:o.ocr.filter(r=>!r.text.includes('02:57'))},{ocr:o.ocr.filter(r=>!r.text.includes('693306810'))},{ocr:o.ocr.map(r=>r.text.startsWith('Reach')?{...r,text:'Reach the target location'}:r)}])assert.equal(g.state({...o,...patch},o.timestamp,o.session),null);
 assert.equal(g.state(o,o.timestamp+1001,o.session),null);
});
test('reviewed low cathedral crossing is separate from wind-current launch and cannot chain holds',async()=>{
 const initial={...o,map:{...o.map,x:-701.28516,y:2347.00391}};let launches=0;
 const api={now:()=>initial.timestamp,check(){},release(){},launch:async stationary=>{assert.equal(stationary,false);launches++;return{opened:false};}};
 const r=await g.run(initial,{mode:'stepDown',holds:0,dx:0,dy:0},api,async()=>initial);assert.equal(launches,1);assert.match(r.reason,/low cathedral railing/);
 await g.run({...initial,map:{...initial.map,x:-710}},{mode:'stepDown',holds:0,dx:0,dy:0},api,async()=>initial);assert.equal(launches,1);
 const p={reviewed:true,session:'s',frameId:2,witnessFrameId:1,createdAt:1,mode:'stepDown',holds:1,dx:0,dy:0};assert.equal(g.plan(p,{session:'s',expectedFrameId:2},2),false);
});
test('recorded city ping misread as 27 m is outside the marker distance crop',()=>{
 const o=require('./act-two-city-ping.fixture.json'),ping=o.ocr.find(r=>r.text==='27 m'),m=o.hud.worldMarker,c=g.distanceCrop(m);
 assert.equal(ping.x,1828);assert.equal(ping.y,79);assert.ok(ping.x>c.x+c.width||ping.y<c.y);
 const local=o.ocr.filter(r=>r.x>=c.x&&r.x+r.width<=c.x+c.width&&r.y>=c.y&&r.y+r.height<=c.y+c.height);
 assert.equal(g.distance(local),null);
});
test('city off-axis marker aligns camera before distance is available and never moves on missing distance',async()=>{
 const launch=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam-launch.js');let now=0,n=0,looks=0,moves=0;
 const r=await launch.course({now:()=>now,check(){},sample:async()=>({valid:true,space:true,health:{max:4015,current:3953},marker:{x:[1435,1300,1100,960][Math.min(n++,3)],y:299},distance:null}),look:async()=>looks++,forwardDown(){moves++},sleep:async ms=>now+=ms,release(){},pause:async()=>{}});
 assert.equal(looks,3);assert.equal(moves,0);assert.equal(r.alignmentMoves,3);assert.match(r.reason,/Target unavailable/);
});
test('unchanged off-axis city marker stops after two ineffective camera corrections without forward',async()=>{
 const launch=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam-launch.js');let now=0,looks=0;
 const r=await launch.course({now:()=>now,check(){},sample:async()=>({valid:true,space:true,health:{max:4015,current:3953},marker:{x:1435,y:299},distance:null}),look:async()=>looks++,forwardDown(){throw Error('no forward')},sleep:async ms=>now+=ms,release(){},pause:async()=>{}});
 assert.equal(looks,2);assert.match(r.reason,/did not improve twice/);
});
test('low off-axis ground target centers horizontally before additional downward pitch',async()=>{
 const launch=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam-launch.js');let now=0,n=0,looks=[];
 const r=await launch.course({now:()=>now,check(){},sample:async()=>({valid:true,space:true,health:{max:4015,current:3953},marker:{x:++n<3?853:960,y:830},distance:null}),look:async(x,y)=>looks.push([x,y]),forwardDown(){throw Error('no distance')},sleep:async ms=>now+=ms,release(){},pause:async()=>{}});
 assert.deepEqual(looks.slice(0,2),[[-37,0],[-37,0]]);assert.equal(r.moves,0);assert.equal(r.alignmentMoves,2);
});
test('city takeoff uses existing bounded deployment only at the visually verified wind current',async()=>{
 const o=require('./act-two-city-current.fixture.json');
 let launches=0,releases=0;const api={now:()=>o.timestamp,check(){},release(){releases++;},launch:async stationary=>{assert.equal(stationary,true);launches++;return {opened:true};}};
 const p={mode:'launch',stationary:true,holds:0,dx:0,dy:0};await g.run(o,p,api,async()=>o);assert.equal(launches,1);assert.equal(releases,1);
 const r=await g.run({...o,map:{...o.map,x:o.map.x+4}},p,api,async()=>o);assert.match(r.reason,/Reviewed exam start platform/);assert.equal(launches,1);
 const old=require('./act-two-city-exam-start.fixture.json');const retired=await g.run(old,p,{...api,now:()=>old.timestamp},async()=>old);assert.match(retired.reason,/Reviewed exam start platform/);assert.equal(launches,1);
});
