const test=require('node:test'),assert=require('node:assert/strict');
const mount=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-riddle-mount.js');
const progress=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/field-progress.js');
const ground=require('./act-two-riddle-stone-520.fixture.json');
const before=require('./act-two-riddle-stone-515.fixture.json');
const inventory=require('./act-two-riddle-inventory-521.fixture.json');
const history=require('./act-two-riddle-stalled-history.fixture.json');
const attached=require('./act-two-hideout-riddle-mounted.fixture.json');
const settled=require('./act-two-hideout-riddle-settled.fixture.json');
const ascent=require('./act-two-lower-climb-recorded.fixture.json').phases[0].initial;
const clone=x=>JSON.parse(JSON.stringify(x));
function harness(samples=[],prior=history,options={}){
 let now=ground.timestamp,frame=ground.frameId,releases=0,inputs=[];
 const initial=clone(ground),pending=samples.map(clone);
 const api={now:()=>now,check(){if(options.cancel)throw Error('cancelled');},sleep:async ms=>{now+=ms;},release:async()=>{releases++;},
  key:async(k,ms)=>{inputs.push(['key',k,ms]);if(options.failKey)throw Error('key_failed');},
  observe:async()=>{const o=pending.shift();if(!o)throw Error('missing_sample');o.session=initial.session;o.frameId=++frame;o.timestamp=now;if(options.badSession)o.session='wrong';return o;}};
 return {initial,run:()=>mount.run(initial,prior,progress,api),counts:()=>({inputs,releases})};
}
test('saved bare-stone survey differs from old door-facing approach',()=>{
 assert.equal(before.map.cameraAngle,293.5);assert.equal(ground.map.cameraAngle,314.5);
 assert.equal(before.map.x,ground.map.x);assert.equal(before.map.y,ground.map.y);
 assert(mount.entry(ground,ground.session,ground.timestamp));assert(!mount.entry(before,before.session,before.timestamp));
});
test('dispatcher permit is fresh, frame bound, and consumed only once',()=>{
 const now=inventory.timestamp+1000,request={step:'actTwoRiddleMount',session:inventory.session,expectedFrameId:inventory.frameId};
 const p={session:inventory.session,frameId:inventory.frameId,witnessFrameId:520,witnessSession:ground.session,createdAt:now,mountReview:mount.plan().mountReview};
 assert(mount.permit(p,request,inventory,ground,now));
 assert(mount.permit(p,request,{...inventory,frameId:inventory.frameId+1},ground,now));
 assert(!mount.permit(p,request,{...inventory,frameId:inventory.frameId+2},ground,now));
 for(const changed of [{...p,usedAt:now},{...p,createdAt:now-120001},{...p,frameId:520},{...p,mountReview:{...p.mountReview,target:'wooden door'}}])assert(!mount.permit(changed,request,inventory,ground,now));
 assert(!mount.permit(p,{...request,expectedFrameId:522},inventory,ground,now));
 assert(!mount.permit(p,request,inventory,{...ground,session:'foreign'},now));
});
test('narrow first-contact review passes saved stall history once',()=>{
 const p=mount.plan();assert.equal(progress.rejection(history,p,ground),null);
 assert.match(progress.rejection(progress.begin(history,p,ground,'probe-one'),p,ground),/already attempted/);
 for(const altered of [
  {...p,mountReview:{...p.mountReview,scene:[...p.mountReview.scene.slice(0,2),{...p.mountReview.scene[2],sha256:'0'.repeat(64)}]}},
  {...p,actions:[{type:'key',key:'VK_W',ms:800}]},
 ])assert.match(progress.rejection(history,altered,ground),/unavailable/);
 for(const altered of [{...ground,map:{...ground.map,cameraAngle:290}},{...ground,map:{...ground.map,x:ground.map.x+.5}},{...ground,hud:{...ground.hud,health:{current:4014,max:4015}}},{...ground,hud:{...ground.hud,enemyBars:[{}]}}])assert.match(progress.rejection(history,p,altered),/unavailable/);
 assert.match(progress.rejection(history,p,{...ground,timestamp:history.entries.at(-1).start.timestamp-1}),/unavailable/);
 const restarted={...ground,session:'new-r18-session',frameId:3,timestamp:ground.timestamp+10000};
 assert.equal(progress.rejection(history,p,restarted),null);
 assert.match(progress.rejection(progress.begin(history,p,restarted,'first-new-session'),p,{...restarted,session:'another-session',frameId:3,timestamp:restarted.timestamp+10000}),/already attempted/);
 assert.match(progress.rejection({version:1,entries:history.entries.slice(0,2)},p,ground),/unavailable/);
 const sameContact={...history.entries.at(-1),requestId:'earlier-contact',start:{...progress.snapshot(ground),frameId:510,timestamp:ground.timestamp-1000},actions:[{type:'key',key:'VK_W',ms:600}]};
 assert.match(progress.rejection({version:1,entries:[...history.entries,sameContact]},p,ground),/unavailable/);
});
test('first forward pulse verifies climb without inventing stamina',async()=>{
 const h=harness([attached,settled]),r=await h.run();
 assert.equal(r.inputs,1);assert.equal(r.reads,2);assert.equal(r.mounted,false);assert.equal(r.climbingObserved,true);assert.equal(r.staminaVerified,false);
 assert.match(r.reason,/positive stamina is unverified/);assert.deepEqual(h.counts().inputs,[['key','VK_W',600]]);assert(h.counts().releases>=2);
});
test('positive same-frame arc stops at first foothold',async()=>{
 const positive=clone(attached);positive.hud.climbStamina=clone(ascent.hud.climbStamina);
 const h=harness([positive]),r=await h.run();assert.equal(r.mounted,true);assert.equal(r.staminaVerified,true);assert.equal(r.inputs,1);assert.match(r.reason,/stop for ledge review/);
});
test('wooden-door or other non-climbable contact stays on ground and consumes only one pulse',async()=>{
 const h=harness([{...ground,map:{...ground.map,x:ground.map.x+.04}}]),r=await h.run();
 assert.equal(r.climbingObserved,false);assert.equal(r.mounted,false);assert.equal(r.inputs,1);assert.match(r.reason,/safe ground verified/);
 assert.deepEqual(h.counts().inputs,[['key','VK_W',600]]);assert(h.counts().releases>=2);
 const consumed=progress.begin(history,mount.plan(),ground,'door-contact');
 assert.match(progress.rejection(consumed,mount.plan(),ground),/already attempted/);
});
test('failed input, cancellation, or observation mismatch releases and never repeats',async()=>{
 for(const options of [{cancel:true},{failKey:true},{badSession:true}]){
  const h=harness([attached],history,options),r=await h.run();assert.equal(r.mounted,false);assert(h.counts().releases>0);assert(h.counts().inputs.length<=1);
 }
});
