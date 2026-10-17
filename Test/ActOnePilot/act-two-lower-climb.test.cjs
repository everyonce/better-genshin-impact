const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-lower-climb.js');
const field=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');
const recorded=require('./act-two-lower-climb-recorded.fixture.json');
const clone=v=>JSON.parse(JSON.stringify(v));
function harness(options={}){
 let now=1000,frame=1,reads=0,checks=0,releases=0,held=false,actions=[];
 const samples=recorded.phases.flatMap(p=>p.afterActions).map(clone),initial=clone(recorded.phases[0].initial);initial.timestamp=now;initial.frameId=frame;
 let insert=null;
 const api={now:()=>now,check(){checks++;if(options.focusFail&&actions.length>=options.focusFail)throw Error('focus_lost');if(options.cancel)throw Error('cancelled');},safe:o=>field.ready(o,initial,now,initial.session,true,false,false),sleep:async n=>{now+=n;if(options.deadline)now+=90000;},release:async()=>{held=false;releases++;},event(){},
 action:async(a,o)=>{assert.equal(held,false);assert(api.safe(o));held=true;actions.push(clone(a));if(options.inputFailure)throw Error('input_failed');now+=a.ms||0;},
 observe:async()=>{assert.equal(held,false);reads++;now+=80;let o=insert||samples.shift();insert=null;if(!o)throw Error('unexpected_observation');o=clone(o);o.timestamp=now;o.frameId=++frame;
  if(options.ambiguity&&reads===1){insert=clone(o);o.hud.climbStamina=clone(recorded.ambiguousStamina.hud.climbStamina);}
  if(options.ambiguity==='persistent'&&reads===2)o.hud.climbStamina=clone(recorded.ambiguousStamina.hud.climbStamina);
  if(options.mutate)options.mutate(o,reads,now);
  return o;
 }};
 return {initial,api,actions,counts:()=>({reads,releases,held,checks}),run:()=>g.run(initial,initial,api)};
}
test('all seven recorded phases run exactly21 fixed actions and stop before landing review',async()=>{
 const h=harness(),r=await h.run();assert.equal(r.reason,'fresh_visual_landing_review_required');assert.equal(r.actions,21);assert.equal(r.phases.length,7);assert.equal(h.counts().reads,21);assert.equal(h.counts().held,false);
 const recipe=JSON.parse(fs.readFileSync(path.join(__dirname,'../../tools/quest-pilot/act-two-windmill-transition.json'))).ascent.slice(3,10);
 assert.deepEqual(h.actions,recipe.flatMap(p=>p.actions));assert(!h.actions.some(a=>['VK_X','VK_SPACE','VK_F'].includes(a.key)));assert.equal(r.phases.at(-1).name,'balcony-align');
 for(const reason of ['input','input_settle','recognition','local_phase_transition','visual_review_required'])assert(r.timings.some(e=>e.waitReason===reason));
});
test('real stray-contour ambiguity permits one stationary reread and preserves action count',async()=>{
 const h=harness({ambiguity:true}),r=await h.run();assert.equal(r.reason,'fresh_visual_landing_review_required');assert.equal(r.rereads,1);assert.equal(r.actions,21);assert.equal(h.counts().reads,22);
});
test('second ambiguous read stops without replaying the completed pulse',async()=>{
 const h=harness({ambiguity:'persistent'}),r=await h.run();assert.equal(r.actions,1);assert.equal(r.rereads,1);assert.equal(h.counts().reads,2);assert.equal(r.reason,'stamina_or_field_guard');assert(r.failureEvidence.screenshotPath);assert.equal(h.counts().held,false);
});
for(const [name,mutate] of Object.entries({health:o=>o.hud.health.current--,session:o=>o.session='other',position:o=>o.map.x+=2,objective:o=>o.hud.objectives=['Different quest'],stamina:o=>o.hud.climbStamina.boxes=[{x:70,y:90,width:10,height:20}],stale:(o,n,now)=>o.timestamp=now-1001,ground:o=>{o.hud.climbing=false;o.hud.groundControls=true;}}))test(name+' failure after a pulse prevents the next input',async()=>{
 const h=harness({mutate:(o,n,t)=>{if(n===1)mutate(o,n,t);}}),r=await h.run();assert.equal(r.actions,1);assert.equal(r.rereads,0);assert.equal(h.counts().held,false);assert(r.failureEvidence);
});
test('changed pose on stationary reread stops; no later action',async()=>{const h=harness({ambiguity:true,mutate:(o,n)=>{if(n===2)o.map.x+=.3;}}),r=await h.run();assert.equal(r.reason,'reread_continuity');assert.equal(r.actions,1);});
test('focus loss, cancellation, deadline and failed input always release keys',async()=>{
 for(const options of [{focusFail:1},{cancel:true},{deadline:true},{inputFailure:true}]){const h=harness(options),r=await h.run();assert.notEqual(r.reason,'fresh_visual_landing_review_required');assert.equal(h.counts().held,false);assert(h.counts().releases>0);assert(h.actions.length<=1);}
});
test('phase entry floor remains stronger than the general corridor floor',async()=>{const h=harness();h.initial.hud.climbStamina.boxes=[{x:70,y:90,width:10,height:55}];const r=await h.run();assert.equal(r.actions,0);assert.equal(r.rereads,0);});
test('completed input with failed capture records unverified outcome without replay',async()=>{const h=harness();h.api.observe=async()=>{throw Error('capture_failed');};const r=await h.run();assert.equal(r.actions,1);assert.equal(r.failureEvidence.uncertainAction,false);assert.equal(r.failureEvidence.outcomeUnverified,true);assert.equal(h.counts().held,false);});
test('unchanged height cannot silently advance past a phase endpoint',async()=>{const h=harness({mutate:o=>o.hud.objectives=['Look for the location in the riddle','Higher23m']}),r=await h.run();assert.equal(r.actions,4);assert.equal(r.phases.length,0);assert.equal(r.reason,'phase_or_field_guard');});
test('one-use plan rejects actions, arbitrary phases, stale time and consumed requests',()=>{
 const p={recipe:'lower-climb-seven-v1',reviewed:true,session:'s',frameId:10,witnessFrameId:8,createdAt:1000},r={step:'actTwoLowerClimb',session:'s',expectedFrameId:10};assert(g.plan(p,r,1000));
 for(const edit of [{actions:[]},{fromPhase:'balcony-align'},{recipe:'other'},{usedAt:1001},{session:'x'},{createdAt:1001},{witnessFrameId:10},{createdAt:-120000}])assert.equal(g.plan({...p,...edit},r,1000),false);
});
test('upper wall and current blocked ladder position cannot enter the lower-climb mission',()=>{
 for(const name of ['act-two-hideout-upper-mount.fixture.json','act-two-hideout-upper-return.fixture.json','act-two-hideout-windmill-edge.fixture.json']){const o=require('./'+name);assert.equal(g.entry(o,o.timestamp,o.session),false);}
});
