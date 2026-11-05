const test=require('node:test');
const assert=require('node:assert/strict');
const native=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-native-combat.js');
function frame(){return {session:'test',timestamp:1000,map:{map:'Teyvat',x:-1420,y:1660,cameraAngle:0},ocr:[{text:'Kaeya',x:1664,y:445}],hud:{world:true,groundControls:true,health:{current:2200,max:2313},enemyBars:[{x:960,y:450,width:70,height:6,rectangularity:1}]}};}
test('settled world with absent targets ends entry polling immediately',()=>{
 const o=frame();o.hud.health={current:2480,max:2635};o.hud.enemyBars=[];
 assert.equal(native.entrySettled(o),true);
 assert.equal(native.encounter(o,1000,'test',()=>true,true),false);
});
test('menu transition can settle, but low health and airborne world cannot prolong entry',()=>{
 assert.equal(native.entrySettled({hud:{world:false,health:null}}),false);
 const o=frame();o.hud.health.current=1;o.hud.groundControls=false;
 assert.equal(native.entrySettled(o),true);
 assert.equal(native.encounter(o,1000,'test',()=>true),false);
});
test('native encounter accepts fresh ordinary target without any level OCR',()=>assert.equal(native.encounter(frame(),1000,'test',()=>true),true));
test('field approach remeasures camera and forward steps against a visible target',async()=>{
 const acq=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-combat-acquisition.js');
 const make=(id,x,y,h)=>{const o=frame();o.frameId=id;Object.assign(o.hud.enemyBars[0],{x,y,height:h});return o;};
 const frames=[make(51,1080,440,5),make(52,1040,590,6),make(53,990,630,8)];
 const actions=[],api={now:()=>1000,checkStop(){},eligible:o=>native.encounter(o,1000,'test',()=>true),
  cameraDelta:acq.cameraDelta,turn:async(dx,o)=>actions.push(['turn',dx,o.frameId]),
  forward:async o=>actions.push(['forward',o.frameId]),sleep:async()=>{},observe:async()=>frames.shift()};
 const last=await native.approachFieldTarget(make(50,1424.5,463.5,5),api);
 assert.equal(last.frameId,53);assert.deepEqual(actions,[['turn',200,50],['forward',51],['forward',52]]);
 const lost=make(61,1080,440,5);lost.hud.enemyBars=[];
 await assert.rejects(native.approachFieldTarget(make(60,1060,440,5),{...api,observe:async()=>lost}),/target or grounded health/);
 const old=make(62,1060,440,5);await assert.rejects(native.approachFieldTarget(old,{...api,observe:async()=>old}),/new observation/);
});
test('camera shift and changed target count are unknown rather than no damage',()=>{
 const a=frame(),b=frame();b.map.cameraAngle=74;
 assert.equal(native.assessProgress(a,b).status,'target_association_unknown');
 b.map.cameraAngle=0;b.hud.enemyBars.push({...b.hud.enemyBars[0],x:1200});
 assert.equal(native.assessProgress(a,b).status,'target_association_unknown');
});
test('target switch and missing orientation cannot associate a smaller bar',()=>{
 const a=frame(),b=frame();b.hud.enemyBars[0].x=1100;b.hud.enemyBars[0].width=30;
 assert.equal(native.assessProgress(a,b).status,'target_association_unknown');
 b.hud.enemyBars[0].x=940;delete b.map.cameraAngle;
 assert.equal(native.assessProgress(a,b).status,'target_association_unknown');
});
test('unchanged associated bar differs from stable-edge damage evidence',()=>{
 const a=frame(),b=frame();assert.equal(native.assessProgress(a,b).status,'no_visible_bar_reduction');
 b.hud.enemyBars[0].width=50;b.hud.enemyBars[0].x=950;
 assert.deepEqual(native.assessProgress(a,b),{status:'comparable_bar_reduction',evidence:'bar_reduced'});
});
test('bounded native sampling runs once and preserves release',async()=>{
 let samples=0;const h=harness(()=>new Promise(r=>setTimeout(r,130)));
 await native.chunk(h.adapter,()=>{},{now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms)),sampleAfterMs:1,sample:async()=>samples++});
 assert.equal(samples,1);assert.deepEqual(h.calls,['run','cancel','release','dispose']);
});
test('failed sample cancels native work and waits for release',async()=>{
 let finish;const h=harness(()=>new Promise(r=>finish=r));h.adapter.createCancellation=()=>({Token:'token',Cancel(){h.calls.push('cancel');finish();},Dispose(){h.calls.push('dispose');}});
 await assert.rejects(native.chunk(h.adapter,()=>{},{now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms)),sampleAfterMs:1,sample:async()=>{throw Error('health');}}),/health/);
 assert.deepEqual(h.calls,['run','cancel','release','dispose']);
});
test('sample failure is preserved when native returns during the observation',async()=>{
 const h=harness(()=>new Promise(r=>setTimeout(r,70)));
 await assert.rejects(native.chunk(h.adapter,()=>{},{now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms)),sampleAfterMs:1,sample:async()=>{await new Promise(r=>setTimeout(r,60));throw Error('late health');}}),/late health/);
 assert.deepEqual(h.calls,['run','cancel','release','dispose']);
});
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

test('bounded local sequence continues only after fresh comparable damage and stops at four chunks',async()=>{let n=0;const initial=frame();initial.frameId=1;const result=await native.sequence(initial,{now:()=>1000,sleep:async()=>{},eligible:()=>true,run:async()=>({nativeReturned:true,nativeMs:1}),observe:async()=>{n++;const o=frame();o.frameId=n+1;o.hud.enemyBars[0].width=70*Math.pow(.8,n);o.hud.enemyBars[0].x=925+o.hud.enemyBars[0].width/2;return o;}});assert.equal(result.turns.length,4);assert.equal(result.reason,'chunk_limit');});
test('sequence stops promptly without measured damage or when health or enemy evidence fails',async()=>{for(const unsafe of [false,true]){let calls=0;const o=frame();const result=await native.sequence(o,{now:()=>1000,sleep:async()=>{},eligible:()=>!unsafe||calls===0,run:async()=>{calls++;return {nativeReturned:true};},observe:async()=>o});assert.equal(calls,1);assert.equal(result.reason,unsafe?'encounter_or_health_guard':'no_visible_bar_reduction');}});
test('vanished bars alone do not demonstrate progress and a quest increment stops immediately',()=>{const a=frame(),b=frame();b.hud.enemyBars=[];assert.equal(native.progress(a,b),null);a.hud.objectives=['(1/3)'];b.hud.objectives=['(2/3)'];assert.equal(native.progress(a,b),'quest_increment');});
test('sequence deadline prevents further native invocation',async()=>{let t=0,calls=0;const result=await native.sequence(frame(),{now:()=>t++?16000:0,eligible:()=>true,run:async()=>calls++});assert.equal(result.reason,'sequence_deadline');assert.equal(calls,0);});

test('five-enemy scope is restricted to the freshly verified final Cyrus camp',()=>{const o=frame();o.map={map:'Teyvat',x:-1229.48,y:2318.79};o.hud.health={current:2635,max:2635};o.hud.objectives=['(2/3)','Quest area reached'];o.hud.enemyBars=Array.from({length:5},(_,i)=>({...o.hud.enemyBars[0],x:600+i*120}));assert.equal(native.encounter(o,1000,'test',()=>true,true),true);o.hud.objectives[0]='(1/3)';assert.equal(native.encounter(o,1000,'test',()=>true,true),false);o.hud.objectives[0]='(2/3)';o.map.x=-1415;assert.equal(native.encounter(o,1000,'test',()=>true,true),false);});

test('verified attacking-monsters stage is restricted to the final camp',()=>{const o=frame();o.map={map:'Teyvat',x:-1218.31,y:2317.84};o.hud.health={current:2635,max:2635};o.hud.objectives=['Defeat the attacking monsters'];assert.equal(native.encounter(o,1000,'test',()=>true,true),true);o.map.x=-1415;assert.equal(native.encounter(o,1000,'test',()=>true,true),false);});

test('ambush native current-character rotation avoids switch retry and remains cancellable',async()=>{let script,released=false;const n={createCancellation:()=>({Token:'t',Cancel(){},Dispose(){}}),run:async s=>script=s,release:()=>released=true};await native.chunk(n,()=>{},{now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms)),strategy:native.ambushStrategy});assert.equal(script,'e,attack(1)');assert.equal(released,true);});

test('native cancellation timer is armed before entering a potentially synchronous executor',async()=>{let order=[];const n={createCancellation:()=>({Token:'t',CancelAfter:n=>order.push(n),Cancel(){},Dispose(){}}),run:async()=>order.push('run'),release(){}};await native.chunk(n,()=>{},{now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms)),timeoutMs:4000});assert.deepEqual(order,[4000,'run']);});

test('deadline-arm failure still releases and disposes without entering native code',async()=>{let calls=[];const a={createCancellation:()=>({Cancel:()=>calls.push('cancel'),Dispose:()=>calls.push('dispose')}),armDeadline(){throw Error('timer');},run:()=>calls.push('run'),release:()=>calls.push('release')};await assert.rejects(native.chunk(a,()=>{},{now:Date.now,sleep:async()=>{}}),/timer/);assert.deepEqual(calls,['cancel','release','dispose']);});
test('native cancellation swallowed by executor cannot report a successful return',async()=>{let t={Token:'t',IsCancellationRequested:false,Cancel(){},Dispose(){}};const a={createCancellation:()=>t,armDeadline(){},run:async()=>{t.IsCancellationRequested=true;},release(){}};await assert.rejects(native.chunk(a,()=>{},{now:Date.now,sleep:ms=>new Promise(r=>setTimeout(r,ms))}),/deadline/);});

test('no-input deadline probe requires full health and safe Windrise ground',()=>{const o=frame();o.map={map:'Teyvat',x:-1265.9,y:1930};o.hud.health={current:2635,max:2635};o.hud.enemyBars=[];assert.equal(native.deadlineProbe(o,1000,'test',()=>true),true);o.hud.health.current=2634;assert.equal(native.deadlineProbe(o,1000,'test',()=>true),false);o.hud.health.current=2635;o.map.x=-1220;assert.equal(native.deadlineProbe(o,1000,'test',()=>true),false);});

test('native defensive task enables stock targeting and suppresses postfight side effects',()=>{const p={Timeout:120,PickDropsAfterFightEnabled:true,KazuhaPickupEnabled:true,ExpBasedPickupEnabled:true,GuardianAvatar:'4',FinishDetectConfig:{RotateFindEnemyEnabled:true}};assert.equal(native.targetingParam(p),p);assert.equal(p.Timeout,2);assert.equal(p.EnableCombatTargeting,true);assert.equal(p.TargetingDetectionInterval,50);assert.equal(p.PickDropsAfterFightEnabled,false);assert.equal(p.KazuhaPickupEnabled,false);assert.equal(p.ExpBasedPickupEnabled,false);assert.equal(p.GuardianAvatar,'');assert.equal(p.FinishDetectConfig.RotateFindEnemyEnabled,false);assert.equal(p.FightFinishDetectEnabled,false);});

test('native stationary alignment holds no movement during skill',()=>{
 const fs=require('node:fs'),line=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/AutoFight/English Cyrus Defense.txt'),'utf8').split('\n').find(l=>!l.startsWith('//')&&l.trim());
 const commands=line.slice(line.indexOf(' ')+1).split(',').map(x=>x.trim()),held=new Set();let t=0,forwardStart,forwardEnd;
 for(const command of commands){
  const [,kind,arg]=/^(\w+)\(([^)]*)\)$/.exec(command);
  if(kind==='keydown'){assert.equal(held.has(arg),false);held.add(arg);if(arg==='w'){assert.equal(held.has('d'),false);forwardStart=t;}}
  if(kind==='wait')t+=Number(arg)*1000;
  if(kind==='keyup'){assert.equal(held.delete(arg),true);if(arg==='w')forwardEnd=t;}
  if(kind==='keypress'&&arg==='e'){assert.equal(held.size,0);assert.equal(forwardStart,undefined);assert.ok(t>=150);}
 }
 assert.equal(held.size,0);
});
test('stationary strategy uses native no-switch primitives and short waits',()=>{const fs=require('node:fs'),s=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/AutoFight/English Cyrus Defense.txt'),'utf8').split('\n').find(l=>!l.startsWith('//')&&l.trim());assert.ok(s.startsWith('\u51ef\u4e9a '));const commands=s.slice(s.indexOf(' ')+1).split(',').map(s=>s.trim());assert.equal(commands[0],'click(left)');assert.equal(commands.includes('keydown(d)'),false);assert.equal(commands.some(c=>/^(keydown|keyup)/.test(c)),false);assert.ok(commands.indexOf('click(left)')<commands.indexOf('keypress(e)'));for(const c of commands)assert.match(c,/^(keydown|keyup|keypress|click|wait)\(/);for(const c of commands.filter(c=>c.startsWith('wait')))assert.ok(Number(c.match(/[\d.]+/)[0])<=.2);});

test('merged ambush OCR retains native location and health bounds',()=>{const o=frame();o.map={map:'Teyvat',x:-1220,y:2315};o.hud.health={current:2635,max:2635};o.hud.objectives=['Defeat theattacking monsters'];assert.equal(native.encounter(o,1000,'test',()=>true,true),true);o.hud.health.current=2300;assert.equal(native.encounter(o,1000,'test',()=>true,true),false);});
test('local camera ownership disables the native seek loop and its final camera reset',()=>{
 const p=native.targetingParam({FinishDetectConfig:{}},true);
 assert.equal(p.EnableCombatTargeting,false);assert.equal(p.Timeout,2);
 assert.equal(p.FinishDetectConfig.RotateFindEnemyEnabled,false);assert.equal(p.PickDropsAfterFightEnabled,false);
});

test('ambush post-native targets reuse acquisition vertical bounds only in the verified camp',()=>{const o=frame();o.map={map:'Teyvat',x:-1220,y:2315};o.hud.health={current:2635,max:2635};o.hud.objectives=['Defeat theattacking monsters'];o.hud.enemyBars[0].y=167.5;assert.equal(native.targets(o).length,1);assert.equal(native.encounter(o,1000,'test',()=>true,true),true);o.map.x=-1415;assert.equal(native.targets(o).length,0);o.map.x=-1220;o.hud.objectives=['Other quest'];assert.equal(native.targets(o).length,0);});

// The verified 4015-HP Kaeya baseline opts in only to ordinary single-target combat.
test('ordinary native combat accepts numeric healthy 4015 Kaeya at the original 85 percent floor',()=>{
 for(const current of [4015,3413]){
  const o=frame();o.hud.health={current,max:4015};
  assert.equal(native.encounter(o,1000,'test',()=>true),true);
 }
});
test('ordinary 4015 entry rejects invalid or insufficient numeric health',()=>{
 for(const health of [{current:3412,max:4015},{current:0,max:4015},{current:-1,max:4015},
  {current:4016,max:4015},{current:'4015',max:4015},{current:true,max:4015},
  {current:NaN,max:4015},{current:Infinity,max:4015},{current:4015,max:'4015'},
  {current:4015,max:Infinity},{current:4015,max:0},{current:4015,max:2764},{}]){
  const o=frame();o.hud.health=health;
  assert.equal(native.encounter(o,1000,'test',()=>true),false,JSON.stringify(health));
 }
});
test('4015 entry retains account session freshness ground and single-target requirements',()=>{
 const valid=()=>{const o=frame();o.hud.health={current:4015,max:4015};return o;};
 assert.equal(native.encounter(valid(),1000,'test',()=>false),false);
 assert.equal(native.encounter(valid(),1000,'foreign',()=>true),false);
 assert.equal(native.encounter(valid(),2001,'test',()=>true),false);
 for(const change of [o=>o.hud.groundControls=false,o=>o.hud.climbing=true,
  o=>o.hud.bigMap=true,o=>o.map.map='Other',o=>o.map.x=-1601,
  o=>o.hud.enemyBars=[],o=>o.hud.enemyBars.push({...o.hud.enemyBars[0]})]){
  const o=valid();change(o);assert.equal(native.encounter(o,1000,'test',()=>true),false);
 }
});
test('4015 ordinary admission does not widen legacy group probe or finishing field profiles',()=>{
 for(const max of [2313,2635,4015]){
  const o=frame();o.hud.health={current:max,max};o.map.x=-1125;o.map.y=2230;
  o.hud.objectives=['(0/3)','Quest area reached'];
  assert.equal(native.encounter(o,1000,'test',()=>true,false),true);
  assert.equal(native.encounter(o,1000,'test',()=>true,true),max!==4015);
  assert.equal(native.field(o,1000,'test',()=>true),max!==4015);
  o.map.x=-1265.917;o.map.y=1928.381;o.hud.enemyBars=[];
  assert.equal(native.deadlineProbe(o,1000,'test',()=>true),max!==4015);
 }
});
const fs=require('node:fs');
// Replay the exact ordinary post-Escape loop with inert observations and sleeps.
async function replayEntry(sources){
 const text=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8');
 const line=text.split('\n').find(x=>x.includes('else for(var poll=0;poll<3;poll++)'));
 const body=line.slice(line.indexOf('for(var poll=0')).replaceAll('Date.now()','now()');
 const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
 let calls=0,clock=1000;const waits=[];const original=o=>o.ocr.some(r=>r.text==='UID: 693306810');
 const eligible=o=>native.encounter(o,clock,'test',original,false);
 const current=await new AsyncFunction('native','eligible','observe','sleep','now','request','original','group','probing','pack','let current;'+body+';return current;')
  (native,eligible,async()=>{const o=structuredClone(sources[Math.min(calls++,sources.length-1)]);clock=o.timestamp;return o;},async ms=>waits.push(ms),()=>clock,{session:'test'},original,false,false,false);
 return {current,eligible:eligible(current),calls,waits};
}
// Frame65 had a fading inventory HUD: exact UID and positive health, no ground glyph.
function fadingFrame(){
 const o=frame();o.hud.health={current:4015,max:4015};o.hud.groundControls=false;
 o.ocr=[{text:'UID: 693306810',x:1680,y:1050,width:181,height:27}];
 o.map={map:'Teyvat',x:-1380.650390625,y:1644.0625,cameraAngle:166.49998474121094};
 o.hud.enemyBars=[{x:1486.5,y:439,width:67,height:4,rectangularity:0.9848484848484849}];return o;
}
test('ordinary fading inventory HUD may use only existing passive entry polls',async()=>{
 const a=fadingFrame(),b=structuredClone(a);b.timestamp=1372;b.hud.groundControls=true;b.hud.enemyBars[0].x=1495;
 assert.equal(native.encounter(a,1000,'test',()=>true,false),false);
 const r=await replayEntry([a,b]);assert.equal(r.calls,2);assert.deepEqual(r.waits,[450,150]);assert.equal(r.eligible,true);assert.equal(r.current.hud.groundControls,true);
});
test('missing ground remains bounded to three observations and never grants combat',async()=>{
 const r=await replayEntry([fadingFrame()]);assert.equal(r.calls,3);assert.deepEqual(r.waits,[450,150,150]);assert.equal(r.eligible,false);
});
test('fading HUD wait refuses every other failed combat guard and preserves old scopes',()=>{
 const changes=[o=>o.session='foreign',o=>o.timestamp=0,o=>o.hud.health.current=1,
  o=>o.hud.health.current=4016,o=>o.hud.health.current='4015',o=>o.hud.health.max=2764,
  o=>o.hud.climbing=true,o=>o.hud.auto=true,o=>o.hud.bigMap=true,o=>o.hud.dialogueReady=true,
  o=>o.hud.choice=true,o=>o.hud.journal=true,o=>o.hud.tutorialStep='x',o=>o.map=null,
  o=>o.map.map='Other',o=>o.map.x=-1601,o=>o.hud.enemyBars=[],o=>o.hud.enemyBars.push({...o.hud.enemyBars[0]})];
 for(const mutate of changes){const o=fadingFrame();mutate(o);assert.equal(native.entrySettled(o,1001,'test',()=>true,true),native.entrySettled(o));}
 assert.equal(native.entrySettled(fadingFrame(),1000,'test',()=>false,true),true);
 assert.equal(native.entrySettled(fadingFrame(),1000,'test',()=>true,false),true);
 assert.equal(native.entrySettled(fadingFrame()),true);
});
test('unsafe field during ordinary entry stops before later good frame can mask it',async()=>{
 const bad=fadingFrame();bad.hud.climbing=true;const good=fadingFrame();good.hud.groundControls=true;
 const r=await replayEntry([bad,good]);assert.equal(r.calls,1);assert.equal(r.eligible,false);
});
// Explicit field-pack fixtures retain the existing ordinary health and location guards.
function packFrame(count=2){
 const o=frame();o.frameId=10;o.hud.health={current:4015,max:4015};o.hud.objectives=[];
 o.hud.enemyBars=Array.from({length:count},(_,i)=>({x:960+i*60,y:450,width:64,height:8,rectangularity:.95}));return o;
}
test('explicit field pack accepts one to three qualified bars while legacy stays single target',()=>{
 for(let n=1;n<=3;n++){const o=packFrame(n);assert.equal(native.encounter(o,1000,'test',()=>true,false,true),true);assert.equal(native.encounter(o,1000,'test',()=>true,false),n===1);}
 for(const n of [0,4])assert.equal(native.encounter(packFrame(n),1000,'test',()=>true,false,true),false);
});
test('field pack rejects extra filtered bars tracked objectives and unchanged safety failures',()=>{
 const changes=[o=>o.hud.enemyBars.push({...o.hud.enemyBars[0],width:2}),o=>o.hud.objectives=['Other quest'],o=>delete o.hud.objectives,
  o=>o.hud.health.current=3412,o=>o.hud.health.current=4016,o=>o.hud.groundControls=false,o=>o.hud.climbing=true,
  o=>o.hud.auto=true,o=>o.hud.dialogueReady=true,o=>o.hud.choice=true,o=>o.hud.bigMap=true,o=>o.hud.journal=true,
  o=>o.map.map='Other',o=>o.map.x=-1700];
 for(const change of changes){const o=packFrame();change(o);assert.equal(native.encounter(o,1000,'test',()=>true,false,true),false);}
 assert.equal(native.encounter(packFrame(),2001,'test',()=>true,false,true),false);
 assert.equal(native.encounter(packFrame(),1000,'foreign',()=>true,false,true),false);
 assert.equal(native.encounter(packFrame(),1000,'test',()=>false,false,true),false);
});
test('field pack transition wait retains one to three scope without broadening legacy entry',()=>{
 const o=packFrame();o.hud.groundControls=false;
 assert.equal(native.entrySettled(o,1000,'test',()=>true,true,true),false);
 assert.equal(native.entrySettled(o,1000,'test',()=>true,true),true);
 o.hud.enemyBars=packFrame(4).hud.enemyBars;assert.equal(native.entrySettled(o,1000,'test',()=>true,true,true),true);
});
test('pack target priority is deterministic by rendered height then center and never red width',()=>{
 const o=packFrame(3);o.hud.enemyBars=[{x:1300,y:450,width:64,height:8,rectangularity:1},{x:1030,y:440,width:40,height:4,rectangularity:1},{x:970,y:450,width:64,height:8,rectangularity:1}];
 assert.equal(native.fieldTarget(o,true).x,970);assert.equal(native.fieldTarget(o).x,1300);
 o.hud.enemyBars.reverse();assert.equal(native.fieldTarget(o,true).x,970);
 o.hud.enemyBars.find(b=>b.x===970).width=32;assert.equal(native.fieldTarget(o,true).x,970);
});
test('pack approach follows fresh one to three targets but stops immediately on a fourth',async()=>{
 const acq=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-combat-acquisition.js');
 const a=packFrame(1);a.hud.enemyBars[0].height=5;const b=packFrame(2);b.frameId=11;b.hud.enemyBars.forEach(x=>x.height=5);const c=packFrame(4);c.frameId=12;
 const frames=[b,c],actions=[];
 await assert.rejects(native.approachFieldTarget(a,{pack:true,now:()=>1000,checkStop(){},eligible:o=>native.encounter(o,1000,'test',()=>true,false,true),cameraDelta:acq.cameraDelta,
  turn:async()=>actions.push('turn'),forward:async()=>actions.push('forward'),sleep:async()=>{},observe:async()=>frames.shift()}),/target or grounded health/);
 assert.deepEqual(actions,['forward','forward']);
});
test('new named quest step keeps existing strict request schema and mission delegation',async()=>{
 const engine=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/engine.js'),mission=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
 const request={id:'field-pack',session:'test',expectedFrameId:1,createdAt:1000,mission:'questStep',step:'actTwoFieldCombat'};
 assert.equal(engine.validate(request,'test',1,{},1000),null);assert.ok(engine.validate({...request,maximumTargets:9},'test',1,{},1000));
 const source={frameId:1},observe=()=>{},calls=[];
 const result=await mission.runQuestStep(request.step,source,{runActTwoNativeCombat:async(o,fn)=>{calls.push([o,fn]);return {bounded:true};}},observe);
 assert.equal(result.bounded,true);assert.deepEqual(calls,[[source,observe]]);
});
// Execute the real adapter method with inert native execution and pause boundaries.
async function packAdapter(step,count,options={}){
 const path=require('node:path'),vm=require('node:vm'),dir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
 const bgi=fs.readFileSync(path.join(dir,'bgi.js'),'utf8');const start=bgi.indexOf('runActTwoNativeCombat: async function('),end=bgi.indexOf('\n        runActTwoPauseProbe:',start);
 const member=bgi.slice(start,end).trim().replace(/,$/,'');let time=1000,id=1;const calls=[];
 const initial={session:'test',frameId:1,timestamp:1000,map:null,hud:{world:false,dialogueReady:false,choice:false,journal:false,bigMap:false,climbing:false,auto:false},ocr:[
  {text:'Weapons',x:136,y:28,width:122,height:40},{text:'Weapons 13/2000',x:1602,y:34,width:199,height:27},{text:"Traveler's Handy Sword",x:1331,y:125,width:417,height:45},{text:'UID: 693306810',x:1680,y:1050,width:181,height:27}]};
 const box={request:{id:'pack-test',step,session:'test'},Date:{now:()=>time},file:{readTextSync:n=>fs.readFileSync(path.join(dir,n),'utf8')},events:[],lastObservation:initial,
  actTwoOriginalAccount:rows=>rows.some(r=>r.text==='UID: 693306810'),checkStop(){},ready(){},release(){calls.push('release');},dispose(){},
  boundedKey:async k=>calls.push(k),sleep:async ms=>{time+=ms;},keyUp(){},leftButtonUp(){},rightButtonUp(){},moveMouseBy(){calls.push('turn');},
  dispatcher:{GetLinkedCancellationTokenSource:()=>({Token:{},CancelAfter(){},Cancel(){},Dispose(){}}),RunCombatScript:async()=>{calls.push('native');if(options.failAt===calls.filter(x=>x==='native').length)throw Error('native rejected');}},
  loadLocalPause:()=>({}),finishWithLocalPause:async(_p,_a,_i,_o,_f,result,error)=>{calls.push('protect');return {...result,pauseVerified:true,error};}};
 const adapter=vm.runInNewContext('({'+member+'})',box);const observe=async()=>{const o=packFrame(count);o.timestamp=time;o.frameId=++id;o.ocr=initial.ocr.slice(-1);box.lastObservation=o;return o;};
 return {result:await adapter.runActTwoNativeCombat(initial,observe),calls};
}
test('actual adapter new step runs a bounded sequence and protects while old step refuses two bars',async()=>{
 const pack=await packAdapter('actTwoFieldCombat',2);assert.equal(pack.result.nativeGroup,false);assert.equal(pack.result.nativeAttempted,true);assert.equal(pack.result.nativeReturned,true);assert.equal(pack.result.damageConfirmed,false);assert.equal(pack.result.defeatConfirmed,false);assert.equal(pack.calls.filter(x=>x==='native').length,3);assert.equal(pack.result.completedRotations,3);assert.deepEqual(Array.from(pack.result.chunks,t=>t.actionId),['pack-test:rotation:0','pack-test:rotation:1','pack-test:rotation:2']);assert.equal(pack.calls.filter(x=>x==='protect').length,1);assert.equal(pack.calls.at(-1),'protect');
 const legacy=await packAdapter('actTwoNativeCombat',2);assert.equal(legacy.result.nativeAttempted,false);assert.equal(legacy.calls.includes('native'),false);assert.equal(legacy.calls.at(-1),'protect');
 const four=await packAdapter('actTwoFieldCombat',4);assert.equal(four.result.nativeAttempted,false);assert.equal(four.calls.includes('native'),false);assert.equal(four.calls.at(-1),'protect');
});
// Deterministic in-world sequence fixture; native inputs and capture latency are inert.
function sequenceHarness(options={}){
 let clock=1000,id=10,runs=0,observations=0;const actions=[];const initial=packFrame();
 const fieldReady=o=>native.field(o,clock,'test',()=>true,true);
 const api={now:()=>clock,checkStop(){if(options.stop&&options.stop(runs,observations))throw Error('STOP');},
  actionId:i=>'request:rotation:'+i,eligible:o=>native.encounter(o,clock,'test',()=>true,false,true),fieldReady,
  emptyField:o=>native.emptyField(o,clock,'test',()=>true),cameraDelta:()=>0,
  turn:async()=>actions.push('turn'),forward:async()=>{actions.push('forward');clock+=400;},
  sleep:async ms=>{clock+=ms;},observe:async()=>{observations++;clock+=options.captureMs||25;const o=packFrame();o.frameId=++id;o.timestamp=clock;if(options.observation)options.observation(o,runs,observations);return o;},
  run:async(o,index)=>{runs++;actions.push('rotation');clock+=options.nativeMs||2000;if(options.failAt===runs)throw Error('native failure');return {nativeReturned:true,nativeMs:options.nativeMs||2000};}};
 return {initial,api,actions,get runs(){return runs;},get observations(){return observations;}};
}
test('field sequence records three distinct rotation joins and new visible reward rows',async()=>{
 const h=sequenceHarness({observation(o,n){if(n===1)o.ocr.push({text:'Mora 16',x:100,y:500,width:100,height:25});}});
 const r=await native.fieldSequence(h.initial,h.api);assert.equal(r.turns.length,3);assert.equal(r.nativeReturned,true);assert.equal(r.reason,'rotation_limit');
 assert.deepEqual(r.turns.map(t=>t.actionId),['request:rotation:0','request:rotation:1','request:rotation:2']);
 for(const t of r.turns){assert.ok(t.afterFrameId>t.beforeFrameId);assert.equal(t.nativeReturned,true);assert.ok(t.finishedAt>=t.startedAt);}
 assert.equal(r.turns[0].visibleRewardRows[0].text,'Mora 16');assert.equal(r.turns[0].assessment.evidence,'new_reward');assert.ok(r.finishedAt-r.startedAt<15000);
});
test('later target loss preserves prior returned rotation and uses only two passive captures',async()=>{
 const h=sequenceHarness({observation:o=>o.hud.enemyBars=[]});const r=await native.fieldSequence(h.initial,h.api);
 assert.equal(h.runs,1);assert.equal(r.turns.length,1);assert.equal(r.turns[0].nativeReturned,true);assert.equal(r.nativeReturned,true);assert.equal(r.reason,'encounter_or_health_guard');
 assert.equal(r.reacquisition.frames.length,2);assert.equal(r.reacquisition.remaining,0);assert.deepEqual(h.actions,['rotation']);
});
test('later unhealthy evidence stops immediately without passive retry and retains completed evidence',async()=>{
 const h=sequenceHarness({observation:o=>o.hud.health.current=2000});const r=await native.fieldSequence(h.initial,h.api);
 assert.equal(h.runs,1);assert.equal(r.turns[0].afterHealth.current,2000);assert.equal(r.reason,'encounter_or_health_guard');assert.equal(r.reacquisition.frames.length,0);
});
test('a failed later native attempt cannot erase the first rotation or report all returned',async()=>{
 const h=sequenceHarness({failAt:2});const r=await native.fieldSequence(h.initial,h.api);
 assert.equal(r.turns.length,2);assert.equal(r.turns[0].nativeReturned,true);assert.equal(r.turns[1].nativeReturned,false);assert.equal(r.turns[1].error,'native failure');assert.equal(r.nativeReturned,false);assert.equal(r.error,'native failure');
});
test('original sequence deadline reserves native headroom and STOP prevents another rotation',async()=>{
 const h=sequenceHarness({nativeMs:4000,captureMs:1500});const r=await native.fieldSequence(h.initial,h.api);
 assert.equal(h.runs,2);assert.equal(r.reason,'native_drain_headroom');assert.equal(r.deadline-r.startedAt,15000);
 const stop=sequenceHarness({stop:(runs,observations)=>runs===1&&observations===1});const s=await native.fieldSequence(stop.initial,stop.api);
 assert.equal(stop.runs,1);assert.equal(s.turns[0].nativeReturned,true);assert.equal(s.error,'STOP');
});
test('stationary empty-bar recovery requires the same fresh pose and never moves on empty input',async()=>{
 const h=sequenceHarness(),o=packFrame();o.hud.enemyBars=[];const api={...h.api,pack:true,deadline:9500,reacquisition:{remaining:2,frames:[]}};
 const returned=await native.reacquireFieldTarget(o,api);assert.equal(returned.hud.enemyBars.length,2);assert.equal(api.reacquisition.remaining,1);assert.deepEqual(h.actions,[]);
 for(const change of [x=>x.map.x+=.36,x=>x.map.cameraAngle+=4,x=>x.session='foreign',x=>x.frameId=10,x=>x.timestamp=1000]){
  const q=sequenceHarness({observation:change}),empty=packFrame();empty.hud.enemyBars=[];
  await assert.rejects(native.reacquireFieldTarget(empty,{...q.api,pack:true,deadline:9500,reacquisition:{remaining:2,frames:[]}}),/changed source, pose or deadline/);assert.deepEqual(q.actions,[]);
 }
});
test('empty-bar retries share one request budget and do not renew the original deadline',async()=>{
 const h=sequenceHarness({observation(o,_runs,n){if([1,3,5].includes(n))o.hud.enemyBars=[];}});const r=await native.fieldSequence(h.initial,h.api);
 assert.equal(h.runs,3);assert.equal(r.reacquisition.frames.length,2);assert.equal(r.reacquisition.remaining,0);assert.equal(r.deadline-r.startedAt,15000);
 const q=sequenceHarness(),empty=packFrame();empty.hud.enemyBars=[];
 assert.equal(await native.reacquireFieldTarget(empty,{...q.api,pack:true,deadline:1100,reacquisition:{remaining:2,frames:[]}}),empty);assert.equal(q.observations,0);
});
test('pack sequence shares movement budget and origin across all rotation approaches',async()=>{
 const h=sequenceHarness({observation:o=>o.hud.enemyBars.forEach(b=>b.height=4)});h.initial.hud.enemyBars.forEach(b=>b.height=4);
 const r=await native.fieldSequence(h.initial,h.api);assert.equal(h.actions.filter(x=>x==='forward').length,4);assert.equal(r.approachBudget.steps,4);assert.equal(h.runs,3);
 const outside=sequenceHarness({observation:o=>o.map.x+=13});const s=await native.fieldSequence(outside.initial,outside.api);
 assert.equal(outside.runs,1);assert.match(s.error,/travel budget/);assert.equal(s.turns[0].nativeReturned,true);
});
test('actual adapter preserves first success and a later failed rotation then protects once',async()=>{
 const r=await packAdapter('actTwoFieldCombat',2,{failAt:2});assert.equal(r.result.completedRotations,1);assert.equal(r.result.nativeReturned,false);assert.equal(r.result.chunks.length,2);assert.equal(r.result.chunks[0].nativeReturned,true);assert.equal(r.result.chunks[1].nativeReturned,false);assert.equal(r.result.chunks[1].afterFrameId,undefined);assert.match(r.result.reason,/native rejected/);assert.equal(r.calls.filter(x=>x==='protect').length,1);assert.equal(r.calls.filter(x=>x==='VK_ESCAPE').length,1);
});

test('centered recent damage continues to a finishing rotation without walking or comparing gold as remaining HP',async()=>{
 const gold={x:1025,y:568.5,width:62,height:5,rectangularity:1,damageTrail:{actionId:'request:rotation:1',
  remainingRed:{x:991,y:569,width:4,height:8,rectangularity:8/21}}};
 const h=sequenceHarness({observation(o,runs){
  if(runs===2){o.hud.enemyBars=[gold];o.map.cameraAngle=125.5;}
 }});
 const result=await native.fieldSequence(h.initial,h.api);
 assert.equal(result.turns.length,3);assert.equal(result.reason,'rotation_limit');
 assert.deepEqual(h.actions,['rotation','rotation','rotation']);
 assert.equal(result.turns[1].assessment.evidence,'post_hit_damage_trail');
 assert.equal(result.turns[2].beforeBars[0].damageTrail.remainingRed.width,4);
 const after=packFrame();after.hud.enemyBars=[gold];
 assert.equal(native.assessProgress(after,h.initial).evidence,null);
});
