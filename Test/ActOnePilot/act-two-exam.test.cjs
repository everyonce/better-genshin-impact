const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam.js');
const o=JSON.parse(fs.readFileSync(__dirname+'/act-two-exam-start.fixture.json','utf8'));
test('fast flight delegates bounded direction once and does not replay per-hold inputs',async()=>{const air={...o,hud:{...o.hud,groundControls:false},ocr:[...o.ocr,{text:'Space',x:1700,y:1020}]};let calls=[],keys=0;const r=await g.run(air,{mode:'flight',holds:4,backward:true,dx:0,dy:0},{now:()=>o.timestamp,check(){},release(){},fly:async(k,ms)=>{calls.push([k,ms]);return{opened:true}},key:async()=>keys++},async()=>air);assert.deepEqual(calls,[['VK_S',2400]]);assert.equal(keys,0);assert.equal(r.phase.kind,'airborne');});
test('recorded exam start requires exact timer, account, health and objective',()=>{
 assert.deepEqual(g.state(o,o.timestamp,o.session),{kind:'groundOrFalling',timer:180});
 for(const patch of [{session:'wrong'},{timestamp:o.timestamp-1001},{hud:{...o.hud,health:{max:4015,current:3000}}},{hud:{...o.hud,climbing:true}},{ocr:o.ocr.filter(r=>!r.text.includes('03:00'))},{ocr:o.ocr.filter(r=>!r.text.includes('693306810'))}])assert.equal(g.state({...o,...patch},o.timestamp,o.session),null);
});
test('finite plans reject repeated launch and excessive inputs',()=>{
 const r={session:o.session,expectedFrameId:10},p={reviewed:true,session:o.session,frameId:10,witnessFrameId:9,createdAt:1000,mode:'inspect',dx:500,dy:100,holds:0};
 assert.equal(g.plan(p,r,1000),true);
 for(const patch of [{usedAt:1},{holds:5},{mode:'inspect',holds:1},{dx:751},{session:'other'}])assert.equal(g.plan({...p,...patch},r,1000),false);
});
test('phase loss stops next movement and releases keys',async()=>{
 let moves=0,released=0;const p={mode:'ground',dx:0,dy:0,holds:4};
 const result=await g.run(o,p,{now:()=>o.timestamp,check:()=>{},release:()=>released++,sleep:async()=>{},key:async()=>moves++},async()=>({...o,hud:{...o.hud,groundControls:false}}));
 assert.equal(moves,1);assert.equal(released,1);assert.match(result.reason,/phase/);
});
test('active challenge replaces the introductory quest toast',()=>{
 const active=JSON.parse(fs.readFileSync(__dirname+'/act-two-exam-active.fixture.json','utf8'));
 assert.deepEqual(g.state(active,active.timestamp,active.session),{kind:'groundOrFalling',timer:175});
});
test('airborne marker steering stays bounded and landing stops remaining holds',async()=>{
 const air={...o,hud:{...o.hud,groundControls:false,worldMarker:{x:1200,y:400}},ocr:[...o.ocr,{text:'Space',x:1700,y:1020}]};
 let moves=0,look=[],releases=0,reads=0;
 const r=await g.run(air,{mode:'flight',dx:0,dy:0,holds:4},{now:()=>o.timestamp,check:()=>{},release:()=>releases++,sleep:async()=>{},look:async x=>look.push(x),key:async()=>moves++},async()=>++reads===1?{...air,hud:{...air.hud,worldMarker:{x:960,y:400}}}:o);
 assert.deepEqual(look,[100]);assert.equal(moves,1);assert.equal(releases,1);assert.equal(r.phase.kind,'groundOrFalling');
});
test('recovery confirms only exact recorded challenge modal',()=>{
 const m=JSON.parse(fs.readFileSync(__dirname+'/act-two-exam-abandon.fixture.json','utf8'));
 assert.ok(g.recoveryTarget(m,m.timestamp,m.session));
 for(const text of ['Abandon Challenge','Abandon Challenge?','Cancel','Confirm'])assert.equal(g.recoveryTarget({...m,ocr:m.ocr.filter(r=>r.text!==text)},m.timestamp,m.session),null);
 assert.equal(g.recoveryTarget(m,m.timestamp+1001,m.session),null);
});
test('recorded living Kaeya challenge modal permits bounded recovery only',()=>{
 const m=JSON.parse(fs.readFileSync(__dirname+'/act-two-exam-kaeya-modal.fixture.json','utf8'));
 assert.ok(g.recoveryTarget(m,m.timestamp,m.session));
 for(const health of [{max:4015,current:3000},{max:4015,current:4016},{max:1186,current:1186}])assert.equal(g.recoveryTarget({...m,hud:{...m.hud,health}},m.timestamp,m.session),null);
 assert.equal(g.recoveryTarget({...m,ocr:m.ocr.filter(r=>r.text!=='Confirm')},m.timestamp,m.session),null);
});
test('stationary plans are limited to launch or flight and cannot request backward',()=>{const r={session:o.session,expectedFrameId:10},p={reviewed:true,session:o.session,frameId:10,witnessFrameId:9,createdAt:1000,mode:'launch',stationary:true,dx:0,dy:0,holds:0};assert.ok(g.plan(p,r,1000));assert.ok(g.plan({...p,mode:'flight',holds:4},r,1000));assert.equal(g.plan({...p,mode:'ground'},r,1000),false);assert.equal(g.plan({...p,mode:'flight',backward:true},r,1000),false);});
test('recorded airborne objective accepts OCR trailing period while preserving full text',()=>{const f=require('./act-two-exam-period.fixture.json');assert.deepEqual(g.state(f,f.timestamp,f.session),{kind:'airborne',timer:164});assert.equal(g.state({...f,ocr:f.ocr.map(r=>r.text.startsWith('Reach the target')?{...r,text:'Reach the target'}:r)},f.timestamp,f.session),null);});
