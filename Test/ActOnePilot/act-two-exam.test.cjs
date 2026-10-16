const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam.js');
test('recorded marker-relative crops include top-edge course target and reject image overflow',()=>{for(const sample of [{marker:{x:935.5,y:458.5},box:{x:901,y:477,width:70,height:32},text:'25m',distance:25},{marker:{x:930,y:178},box:{x:895,y:196,width:70,height:32},text:'20m',distance:20}]){assert.deepEqual(g.distanceCrop(sample.marker),sample.box);assert.equal(g.distance([{text:sample.text}]),sample.distance);}for(const marker of [null,{x:NaN,y:100},{x:15,y:100},{x:1900,y:100},{x:900,y:1040}])assert.equal(g.distanceCrop(marker),null);});
test('distance accepts recorded tight crop but rejects incomplete or conflicting OCR',()=>{assert.equal(g.distance([{text:'25m'}]),25);assert.equal(g.distance([{text:'2 5 m'}]),25);for(const rows of [[],[{text:'39'}],[{text:'25m'},{text:'26m'}],[{text:'101m'}]])assert.equal(g.distance(rows),null);});
const o=JSON.parse(fs.readFileSync(__dirname+'/act-two-exam-start.fixture.json','utf8'));
test('fresh airborne inspection refreshes evidence without movement or camera input',async()=>{const air={...o,hud:{...o.hud,groundControls:false},ocr:[...o.ocr,{text:'Space',x:1700,y:1020}]};let releases=0;const forbidden=()=>assert.fail('Inspection emitted gameplay input');const r=await g.run(air,{mode:'inspect',holds:0,dx:0,dy:0},{now:()=>o.timestamp,check(){},release:()=>releases++,key:forbidden,look:forbidden,fly:forbidden},async()=>air);assert.equal(r.phase.kind,'airborne');assert.equal(r.moves,0);assert.equal(releases,1);});
test('lateral correction cannot combine directions or escape verified flight plans',()=>{const r={session:o.session,expectedFrameId:10},p={reviewed:true,session:o.session,frameId:10,witnessFrameId:9,createdAt:1000,mode:'flight',dx:0,dy:0,holds:2,left:true};assert.ok(g.plan(p,r,1000));for(const patch of [{mode:'ground'},{mode:'course'},{stationary:true},{backward:true},{left:'VK_A'},{holds:5},{usedAt:1000}])assert.equal(g.plan({...p,...patch},r,1000),false);});
test('fast flight delegates bounded direction once and does not replay per-hold inputs',async()=>{const air={...o,hud:{...o.hud,groundControls:false},ocr:[...o.ocr,{text:'Space',x:1700,y:1020}]};let calls=[],keys=0;const r=await g.run(air,{mode:'flight',holds:4,backward:true,dx:0,dy:0},{now:()=>o.timestamp,check(){},release(){},fly:async(k,ms)=>{calls.push([k,ms]);return{opened:true}},key:async()=>keys++},async()=>air);assert.deepEqual(calls,[['VK_S',2400]]);assert.equal(keys,0);assert.equal(r.phase.kind,'airborne');});
test('recorded exam start requires exact timer, account, health and objective',()=>{
 assert.deepEqual(g.state(o,o.timestamp,o.session),{kind:'groundOrFalling',timer:180});
 for(const patch of [{session:'wrong'},{timestamp:o.timestamp-1001},{hud:{...o.hud,health:{max:4015,current:3000}}},{hud:{...o.hud,climbing:true}},{ocr:o.ocr.filter(r=>!r.text.includes('03:00'))},{ocr:o.ocr.filter(r=>!r.text.includes('693306810'))}])assert.equal(g.state({...o,...patch},o.timestamp,o.session),null);
});
test('finite plans reject repeated launch and excessive inputs',()=>{
 const r={session:o.session,expectedFrameId:10},p={reviewed:true,session:o.session,frameId:10,witnessFrameId:9,createdAt:1000,mode:'inspect',dx:0,dy:0,holds:0};
 assert.equal(g.plan(p,r,1000),true);
 for(const patch of [{usedAt:1},{holds:5},{mode:'inspect',holds:1},{dx:1},{dy:1},{dx:751},{session:'other'}])assert.equal(g.plan({...p,...patch},r,1000),false);
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
test('fast course entry requires fresh sample controls health full objective timer and UID',()=>{const f=require('./act-two-exam-period.fixture.json'),s={space:true,health:f.hud.health};assert.equal(g.fastState(s,f.ocr),true);for(const rows of [f.ocr.filter(r=>!r.text.includes('693306810')),f.ocr.filter(r=>!r.text.startsWith('Reach')),f.ocr.filter(r=>!r.text.includes(':44')),f.ocr.map(r=>r.text.includes(':44')?{...r,text:'00:10'}:r)])assert.equal(g.fastState(s,rows),false);assert.equal(g.fastState({...s,space:false},f.ocr),false);assert.equal(g.fastState({...s,health:{max:4015,current:3000}},f.ocr),false);});
