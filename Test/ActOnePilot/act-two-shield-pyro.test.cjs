const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-shield-pyro.js');
function frame(max=4015,aim=false){return {session:'test',timestamp:1000,frameId:10,map:{map:'Teyvat',x:-1265.917,y:1928.381},hud:{health:{current:max,max},groundControls:!aim,enemyBars:[],objectives:[]},ocr:[{text:'UID: 693306810',x:1700,y:1040},{text:'Amber',x:1690,y:350},{text:'Kaeya',x:1690,y:440},...(aim?[{text:'R',x:1720,y:1025}]:[])]};}
test('one-use plan rejects wrong frame/session, replay and unreviewed fire',()=>{const p={reviewed:true,session:'test',frameId:12,createdAt:1000,mode:'practice',offset:{dx:0,dy:0}},r={session:'test',expectedFrameId:12};assert(g.plan(p,r,1000));for(const patch of [{usedAt:1},{session:'other'},{frameId:11},{createdAt:1001},{offset:{dx:201,dy:0}},{mode:'fire'}])assert(!g.plan({...p,...patch},r,1000));});
test('practice is scoped to healed Statue; threat, account, stale and frozen evidence fail',()=>{const o=frame(),p={mode:'practice'};assert(g.scope(o,p));assert(g.base(o,1000,'test'));assert(!g.scope({...o,map:{...o.map,x:0}},p));assert(!g.scope({...o,hud:{...o.hud,enemyBars:[{}]}},p));assert(!g.base(o,2001,'test'));assert(!g.base({...o,ocr:[]},1000,'test'));assert(!g.base({...o,ocr:[...o.ocr,{text:'Frozen'}]},1000,'test'));});
async function run(mode,damage){let now=1000,id=10,max=4015,aim=false,releases=0;const keys=[];const p={mode,offset:{dx:0,dy:0}};const initial=frame();if(mode!=='practice'){initial.map={map:'Teyvat',x:-1476.6,y:2314.4};initial.hud.objectives=['Defeat all opponents 4/9'];}
 const api={now:()=>now,sleep:async ms=>now+=ms,release:async()=>releases++,key:async k=>{keys.push(k);if(k==='VK_2')max=1733;if(k==='VK_3')max=4015;if(k==='VK_R')aim=!aim;},observe:async()=>{const o=frame(max,aim);o.timestamp=now;o.frameId=++id;o.map=initial.map;o.hud.objectives=initial.hud.objectives;if(damage&&aim)o.hud.health.current=1600;return o;}};return {result:await g.run(initial,p,api),keys,releases};}
test('practice exercises switch/aim/exit/return without shooting',async()=>{const r=await run('practice');assert.equal(r.result.shots,0);assert.equal(r.result.returnedKaeya,true);assert.deepEqual(r.keys,['VK_2','VK_R','VK_R','VK_3']);assert.equal(r.releases,2);});
test('single charged arrow releases and returns to damage dealer',async()=>{const r=await run('fire');assert.equal(r.result.shots,1);assert.equal(r.keys.filter(k=>k==='VK_LBUTTON').length,1);assert(r.result.returnedKaeya);assert.equal(r.releases,2);});
test('health loss prevents firing but permits recovery',async()=>{const r=await run('fire',true);assert.equal(r.result.shots,0);assert(!r.keys.includes('VK_LBUTTON'));assert.equal(r.releases,2);});
test('recorded live upgraded Amber aim and Kaeya return pass exact identity and health checks',()=>{const aim=require('./act-two-shield-6314.fixture.json'),returned=require('./act-two-shield-6316.fixture.json');assert(g.aim(aim,aim.timestamp,aim.session));assert(g.scope(aim,{mode:'practice'}));assert(g.ground(returned,returned.timestamp,returned.session,4015));assert(!g.aim({...aim,hud:{...aim.hud,health:{current:1186,max:1186}}},aim.timestamp,aim.session));});
test('interrupted recorded encounter is grounded and cannot qualify as healthy aim',()=>{const o=require('./act-two-shield-6385.fixture.json');assert(g.ground(o,o.timestamp,o.session,1733));assert(!g.aim(o,o.timestamp,o.session));assert.equal(o.hud.health.current,1453);});
test('earlier rock scope excludes the known close bank; Statue noise never opens encounter scope',()=>{const o=frame();o.map={map:'Teyvat',x:-1476.6,y:2314.4};o.hud.objectives=['Defeat all opponents 4/9'];assert(g.scope(o,{mode:'inspect'}));assert(!g.scope({...o,map:{...o.map,x:-1465.89}},{mode:'inspect'}));const statue=frame();statue.hud.objectives=['TO'];assert(g.scope(statue,{mode:'practice'}));assert(!g.scope(statue,{mode:'inspect'}));statue.hud.objectives=['Defeat all opponents 4/9'];assert(!g.scope(statue,{mode:'practice'}));});
async function burst(practice, allow, damaged) {
 let now=1000,max=4015,id=10;const keys=[],initial=frame();
 const p={mode:practice?'practice':'burst',primitive:'burst',offset:{dx:0,dy:0}};
 if(!practice){initial.map={map:'Teyvat',x:-1476.6,y:2314.4};initial.hud.objectives=['Defeat all opponents 4/9'];}
 const api={now:()=>now,sleep:async ms=>now+=ms,release:async()=>{},
  key:async k=>{keys.push(k);if(k==='VK_2')max=1733;if(k==='VK_3')max=4015;},
  shieldDecision:()=>({action:allow?'apply-element':'retreat',capability:'Amber.Q',reason:'Unknown target'}),
  observe:async()=>{const o=frame(max);Object.assign(o,{timestamp:now,frameId:++id,map:initial.map,shieldVision:{amberBurstReady:true}});o.hud.objectives=initial.hud.objectives;if(damaged&&max===1733)o.hud.health.current=1453;return o;}};
 return {keys,result:await g.run(initial,p,api)};
}
test('safe burst-readiness practice consumes no energy and returns a current observation',async()=>{
 const r=await burst(true,true);assert.deepEqual(r.keys,['VK_2','VK_3']);assert(r.result.burstReadiness);assert(r.result.returnedKaeya);assert(r.result.current);});
test('bounded burst uses one Q only after policy approval and never enters aim',async()=>{
 const r=await burst(false,true);assert.deepEqual(r.keys,['VK_2','VK_Q','VK_3']);assert.equal(r.result.bursts,1);assert.equal(r.result.current.hud.health.max,4015);});
test('unknown target or actual recorded-level damage aborts before burst',async()=>{
 for(const args of [[false,false,false],[false,true,true]]){const r=await burst(...args);assert(!r.keys.includes('VK_Q'));assert(r.result.current);}});
test('recovery-only mode exits fresh Amber aim and returns Kaeya without offensive inputs',async()=>{
 let now=1000,max=1733,aiming=true;const keys=[],initial=frame(max,true);initial.map={map:'Teyvat',x:-1476.6,y:2314.4};initial.hud.objectives=['Defeat all opponents 4/9'];
 const sample=async()=>{const o=frame(max,aiming);Object.assign(o,{timestamp:now,map:initial.map});o.hud.objectives=initial.hud.objectives;return o;};
 const r=await g.run(initial,{mode:'recover',offset:{dx:0,dy:0}},{now:()=>now,sleep:async ms=>now+=ms,release:async()=>{},observe:sample,observeRecovery:sample,key:async k=>{keys.push(k);if(k==='VK_R')aiming=false;if(k==='VK_3')max=4015;}});
 assert.deepEqual(keys,['VK_R','VK_3']);assert(r.returnedKaeya);assert.equal(r.shots,0);assert.equal(r.health.current,4015);
});
test('decoy practice uses one E without aim, charged shot or Q and cannot be selected as a field primitive',async()=>{let now=1000,max=4015;const keys=[],initial=frame(),p={mode:'practice',primitive:'decoy',offset:{dx:0,dy:0}};const result=await g.run(initial,p,{now:()=>now,sleep:async ms=>now+=ms,release:async()=>{},key:async k=>{keys.push(k);if(k==='VK_2')max=1733;if(k==='VK_3')max=4015;},observe:async()=>{const o=frame(max);o.timestamp=now;return o;}});assert.deepEqual(keys,['VK_2','VK_E','VK_3']);assert.equal(result.decoys,1);assert.equal(result.shots,0);assert(result.returnedKaeya);const plan={...p,reviewed:true,session:'test',frameId:12,createdAt:1000};assert(g.plan(plan,{session:'test',expectedFrameId:12},1000));assert(!g.plan({...plan,mode:'inspect'},{session:'test',expectedFrameId:12},1000));});
test('field decoy plan requires independent deployment, current encounter and facing reviews',()=>{
 const p={reviewed:true,session:'test',frameId:12,createdAt:1000,mode:'decoy',vision:true,decoyDeploymentReviewed:true,encounterReviewed:true,facingReviewed:true,offset:{dx:0,dy:0}},r={session:'test',expectedFrameId:12};
 assert(g.plan(p,r,1000));for(const key of ['vision','decoyDeploymentReviewed','encounterReviewed','facingReviewed'])assert(!g.plan({...p,[key]:false},r,1000));
 assert(!g.plan({...p,primitive:'decoy'},r,1000));
});
test('field decoy uses one ready E and returns Kaeya; unknown readiness or damage aborts before E',async()=>{
 for(const [ready,damaged] of [[true,false],[false,false],[true,true]]){
  let now=1000,max=4015,releases=0;const keys=[],initial=frame();initial.map={map:'Teyvat',x:-1476.6,y:2314.4};initial.hud.objectives=['Defeat all opponents 4/9'];
  const result=await g.run(initial,{mode:'decoy',offset:{dx:0,dy:0}},{now:()=>now,sleep:async ms=>now+=ms,release:async()=>releases++,key:async k=>{keys.push(k);if(k==='VK_2')max=1733;if(k==='VK_3')max=4015;},observe:async()=>{const o=frame(max);Object.assign(o,{timestamp:now,map:initial.map,shieldVision:{amberSkillReady:ready}});o.hud.objectives=initial.hud.objectives;if(damaged&&max===1733)o.hud.health.current=1600;return o;}});
  assert.equal(keys.includes('VK_E'),ready&&!damaged);assert(!keys.some(k=>['VK_Q','VK_R','VK_LBUTTON'].includes(k)));assert(result.returnedKaeya);assert.equal(releases,2);assert.equal(result.shots,0);
 }
});
