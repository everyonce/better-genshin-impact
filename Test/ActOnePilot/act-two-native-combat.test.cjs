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
test('native auto targeting accepts the recorded close lateral survivor, retaining geometry checks',()=>{const o=frame();o.hud.enemyBars=[{x:553.5,y:417,width:41,height:6,rectangularity:.9525}];assert.equal(native.encounter(o,1000,'test',()=>true),true);o.hud.enemyBars[0].x=300;assert.equal(native.encounter(o,1000,'test',()=>true),false);});
test('verified eastern Cyrus camp uses the same small-group guard',()=>{const o=frame();o.map={map:'Teyvat',x:-1419.926,y:2392.265};o.hud.health={current:2612,max:2635};o.hud.objectives=['(1/3)','Quest area reached'];o.hud.enemyBars.push({...o.hud.enemyBars[0],x:1052});assert.equal(native.encounter(o,1000,'test',()=>true,true),true);assert.equal(native.encounter({...o,map:{...o.map,y:2450}},1000,'test',()=>true,true),false);});
test('group rotation uses the existing starter burst script through the same cancellation path',async()=>{let script;const n={createCancellation:()=>({Token:'t',Cancel(){},Dispose(){}}),run:async s=>script=s,release(){}};await native.chunk(n,()=>{},{now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms)),strategy:native.groupStrategy});assert.equal(script,'凯亚 e(fast), q, attack(1)');});

test('bounded local sequence continues only after fresh comparable damage and stops at four chunks',async()=>{let n=0;const initial=frame();initial.frameId=1;const result=await native.sequence(initial,{now:()=>1000,sleep:async()=>{},eligible:()=>true,run:async()=>({nativeReturned:true,nativeMs:1}),observe:async()=>{n++;const o=frame();o.frameId=n+1;o.hud.enemyBars[0].width=70*Math.pow(.8,n);return o;}});assert.equal(result.turns.length,4);assert.equal(result.reason,'chunk_limit');});
test('sequence stops promptly without measured damage or when health or enemy evidence fails',async()=>{for(const unsafe of [false,true]){let calls=0;const o=frame();const result=await native.sequence(o,{now:()=>1000,sleep:async()=>{},eligible:()=>!unsafe||calls===0,run:async()=>{calls++;return {nativeReturned:true};},observe:async()=>o});assert.equal(calls,1);assert.equal(result.reason,unsafe?'encounter_or_health_guard':'no_damage_progress');}});
test('vanished bars alone do not demonstrate progress and a quest increment stops immediately',()=>{const a=frame(),b=frame();b.hud.enemyBars=[];assert.equal(native.progress(a,b),null);a.hud.objectives=['(1/3)'];b.hud.objectives=['(2/3)'];assert.equal(native.progress(a,b),'quest_increment');});
test('sequence deadline prevents further native invocation',async()=>{let t=0,calls=0;const result=await native.sequence(frame(),{now:()=>t++?16000:0,eligible:()=>true,run:async()=>calls++});assert.equal(result.reason,'sequence_deadline');assert.equal(calls,0);});

test('five-enemy scope is restricted to the freshly verified final Cyrus camp',()=>{const o=frame();o.map={map:'Teyvat',x:-1229.48,y:2318.79};o.hud.health={current:2635,max:2635};o.hud.objectives=['(2/3)','Quest area reached'];o.hud.enemyBars=Array.from({length:5},(_,i)=>({...o.hud.enemyBars[0],x:600+i*120}));assert.equal(native.encounter(o,1000,'test',()=>true,true),true);o.hud.objectives[0]='(1/3)';assert.equal(native.encounter(o,1000,'test',()=>true,true),false);o.hud.objectives[0]='(2/3)';o.map.x=-1415;assert.equal(native.encounter(o,1000,'test',()=>true,true),false);});

test('verified attacking-monsters stage is restricted to the final camp',()=>{const o=frame();o.map={map:'Teyvat',x:-1218.31,y:2317.84};o.hud.health={current:2635,max:2635};o.hud.objectives=['Defeat the attacking monsters'];assert.equal(native.encounter(o,1000,'test',()=>true,true),true);o.map.x=-1415;assert.equal(native.encounter(o,1000,'test',()=>true,true),false);});

test('ambush native current-character rotation avoids switch retry and remains cancellable',async()=>{let script,released=false;const n={createCancellation:()=>({Token:'t',Cancel(){},Dispose(){}}),run:async s=>script=s,release:()=>released=true};await native.chunk(n,()=>{},{now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms)),strategy:native.ambushStrategy});assert.equal(script,'e,attack(1)');assert.equal(released,true);});

test('native cancellation timer is armed before entering a potentially synchronous executor',async()=>{let order=[];const n={createCancellation:()=>({Token:'t',CancelAfter:n=>order.push(n),Cancel(){},Dispose(){}}),run:async()=>order.push('run'),release(){}};await native.chunk(n,()=>{},{now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms)),timeoutMs:4000});assert.deepEqual(order,[4000,'run']);});

test('deadline-arm failure still releases and disposes without entering native code',async()=>{let calls=[];const a={createCancellation:()=>({Cancel:()=>calls.push('cancel'),Dispose:()=>calls.push('dispose')}),armDeadline(){throw Error('timer');},run:()=>calls.push('run'),release:()=>calls.push('release')};await assert.rejects(native.chunk(a,()=>{},{now:Date.now,sleep:async()=>{}}),/timer/);assert.deepEqual(calls,['cancel','release','dispose']);});
test('native cancellation swallowed by executor cannot report a successful return',async()=>{let t={Token:'t',IsCancellationRequested:false,Cancel(){},Dispose(){}};const a={createCancellation:()=>t,armDeadline(){},run:async()=>{t.IsCancellationRequested=true;},release(){}};await assert.rejects(native.chunk(a,()=>{},{now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms))}),/deadline/);});

test('no-input deadline probe requires full health and safe Windrise ground',()=>{const o=frame();o.map={map:'Teyvat',x:-1265.9,y:1930};o.hud.health={current:2635,max:2635};o.hud.enemyBars=[];assert.equal(native.deadlineProbe(o,1000,'test',()=>true),true);o.hud.health.current=2634;assert.equal(native.deadlineProbe(o,1000,'test',()=>true),false);o.hud.health.current=2635;o.map.x=-1220;assert.equal(native.deadlineProbe(o,1000,'test',()=>true),false);});
