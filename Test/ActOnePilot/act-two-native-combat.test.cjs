const test=require('node:test');
const assert=require('node:assert/strict');
const native=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-native-combat.js');
function frame(){return {session:'test',timestamp:1000,map:{map:'Teyvat',x:-1420,y:1660},ocr:[{text:'Kaeya',x:1664,y:445}],hud:{world:true,groundControls:true,health:{current:2200,max:2313},enemyBars:[{x:960,y:450,width:70,height:6,rectangularity:1}]}};}
test('native encounter accepts fresh ordinary target without any level OCR',()=>assert.equal(native.encounter(frame(),1000,'test',()=>true),true));
for(const [name,edit] of Object.entries({nongame:o=>o.hud.world=false,menu:o=>o.hud.bigMap=true,noEnemy:o=>o.hud.enemyBars=[],climbing:o=>o.hud.climbing=true,lowHealth:o=>o.hud.health.current=1700,missingHealth:o=>o.hud.health=null,ambiguous:o=>o.hud.enemyBars.push({...o.hud.enemyBars[0]}),irregularRed:o=>o.hud.enemyBars[0].rectangularity=.3,tinyRed:o=>o.hud.enemyBars[0].height=2,wrongCharacter:o=>o.hud.health.max=1363,unknownPosition:o=>o.map=null}))test('rejects '+name,()=>{let o=frame();edit(o);assert.equal(native.encounter(o,1000,'test',()=>true),false);});
test('rejects wrong UID, session and stale frame',()=>{assert.equal(native.encounter(frame(),1000,'test',()=>false),false);assert.equal(native.encounter(frame(),1000,'other',()=>true),false);assert.equal(native.encounter(frame(),2001,'test',()=>true),false);});
function harness(run){let calls=[];return {calls,adapter:{createCancellation:()=>({Token:'token',Cancel:()=>calls.push('cancel'),Dispose:()=>calls.push('dispose')}),run:async(s,t)=>{calls.push('run');assert.equal(s,native.strategy);assert.equal(t,'token');return run&&run();},release:()=>calls.push('release')}};}
test('one native chunk returns unconfirmed outcome and releases',async()=>{const h=harness();const r=await native.chunk(h.adapter,()=>{}, {now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms))});assert.equal(r.nativeReturned,true);assert.equal(r.damageConfirmed,false);assert.equal(r.defeatConfirmed,false);assert.deepEqual(h.calls,['run','cancel','release','dispose']);});
test('guard refusal never starts native code',async()=>{const h=harness();await assert.rejects(native.chunk(h.adapter,()=>{throw Error('focus');},{now:Date.now,sleep:async()=>{}}),/focus/);assert.deepEqual(h.calls,[]);});
test('deadline cancels then waits for unwind before release',async()=>{let calls=[],finish;const h={createCancellation:()=>({Token:'t',Cancel:()=>{calls.push('cancel');finish();},Dispose:()=>calls.push('dispose')}),run:()=>new Promise(r=>{finish=()=>{calls.push('unwind');r();};}),release:()=>calls.push('release')};await assert.rejects(native.chunk(h,()=>{}, {now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms)),timeoutMs:10}),/deadline/);assert.deepEqual(calls,['cancel','unwind','release','dispose']);});
test('focus loss cancels native work and guarantees release',async()=>{let count=0,finish;const h=harness(()=>new Promise(r=>finish=r));h.adapter.createCancellation=()=>({Token:'token',Cancel:()=>{h.calls.push('cancel');finish();},Dispose:()=>h.calls.push('dispose')});await assert.rejects(native.chunk(h.adapter,()=>{if(++count>2)throw Error('focus');},{now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms))}),/focus/);assert.deepEqual(h.calls,['run','cancel','release','dispose']);});

test('missing English party-name OCR does not block native canonical party recognition',()=>{const o=frame();o.ocr=[];assert.equal(native.encounter(o,1000,'test',()=>true),true);});

test("observed jumping-slime geometry remains eligible without level OCR",()=>{const o=frame();o.hud.enemyBars=[{x:1123.5,y:436,width:63,height:4,rectangularity:.965}];assert.equal(native.encounter(o,1000,"test",()=>true),true);});

test('separate small-group entry requires explicit Cyrus quest area and higher health',()=>{
 const o=frame();o.hud.enemyBars.push({...o.hud.enemyBars[0],x:1020});
 assert.equal(native.encounter(o,1000,'test',()=>true),false);
 assert.equal(native.encounter(o,1000,'test',()=>true,true),false);
 o.map={map:'Teyvat',x:-1125,y:2230};o.hud.objectives=['(0/3)','Quest area-reached'];
 assert.equal(native.encounter(o,1000,'test',()=>true,true),true);
 o.hud.health.current=2000;assert.equal(native.encounter(o,1000,'test',()=>true,true),false);
 o.hud.health.current=2300;o.hud.enemyBars.push({...o.hud.enemyBars[0],x:1080},{...o.hud.enemyBars[0],x:1140});
 assert.equal(native.encounter(o,1000,'test',()=>true,true),false);
});

test('one finishing chunk requires a paused successful prior native encounter and rejects replay or unrelated frames',()=>{
 const o=frame();o.map={map:'Teyvat',x:-1135,y:2247};o.hud.enemyBars=[];o.hud.objectives=['(0/3)'];
 const w={...o,frameId:90},p={reviewed:true,session:'test',frameId:95,priorId:'prior',createdAt:1000},r={session:'test',expectedFrameId:95},v={nativeGroup:true,nativeReturned:true,pauseVerified:true,beforeBars:[{}],afterBars:[],afterFrameId:90},receipt={id:'prior',session:'test',frameId:95,status:'stopped',details:{result:v}};
 assert.equal(native.finish(o,w,receipt,p,r,1000,()=>true),true);
 for(const patch of [{usedAt:1001},{frameId:94},{priorId:'other'},{reviewed:false},{createdAt:-130000}])assert.equal(native.finish(o,w,receipt,{...p,...patch},r,1000,()=>true),false);
 for(const patch of [{nativeReturned:false},{pauseVerified:false},{beforeBars:[]},{afterFrameId:89}])assert.equal(native.finish(o,w,{...receipt,details:{result:{...v,...patch}}},p,r,1000,()=>true),false);
 assert.equal(native.finish({...o,map:{...o.map,x:-1100}},w,receipt,p,r,1000,()=>true),false);
 assert.equal(native.encounter(o,1000,'test',()=>true,true),false);
});
test('verified level twenty Kaeya preserves ratio guards',()=>{const o=frame();o.hud.health={current:2635,max:2635};assert.equal(native.encounter(o,1000,'test',()=>true),true);o.hud.health.current=2000;assert.equal(native.encounter(o,1000,'test',()=>true),false);});
