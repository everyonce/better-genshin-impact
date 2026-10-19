const test=require('node:test'),assert=require('node:assert/strict');
const mount=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-riddle-mount.js');
const progress=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/field-progress.js');
const ground=require('./act-two-riddle-ground-reconnect.fixture.json');
const history=require('./act-two-riddle-stalled-history.fixture.json');
const attached=require('./act-two-hideout-riddle-mounted.fixture.json');
const settled=require('./act-two-hideout-riddle-settled.fixture.json');
const reserve=require('./act-two-hideout-riddle-reserve.fixture.json');
const ascent=require('./act-two-lower-climb-recorded.fixture.json').phases[0].initial;
const ledge=require('./act-two-hideout-riddle-ground.fixture.json');
const clone=x=>JSON.parse(JSON.stringify(x));
function harness(samples=[],prior=history,options={}){
 let now=ground.timestamp,frame=ground.frameId,releases=0,inputs=[];
 const initial=clone(ground),pending=samples.map(clone);
 const api={now:()=>now,check(){if(options.cancel)throw Error('cancelled');},sleep:async ms=>{now+=ms;},release:async()=>{releases++;},
  look:async(dx,dy)=>{inputs.push(['look',dx,dy]);if(options.failLook)throw Error('look_failed');},
  key:async(k,ms)=>{inputs.push(['key',k,ms]);if(options.failKey)throw Error('key_failed');},
  observe:async()=>{const o=pending.shift();if(!o)throw Error('missing_sample');o.session=initial.session;o.frameId=++frame;o.timestamp=now;if(options.badSession&&frame===initial.frameId+2)o.session='wrong';return o;}};
 return {initial,run:()=>mount.run(initial,prior,progress,api),counts:()=>({inputs,releases})};
}
const afterLook=()=>({...clone(ground),map:{...ground.map,cameraAngle:314.5}});
test('fresh reconnect frame is a grounded riddle mount candidate, not a climb witness',()=>{
 assert(mount.entry(ground,ground.session,ground.timestamp));assert(!mount.attached(ground,ground.session,ground.timestamp));
 for(const patch of [{session:'other'},{timestamp:ground.timestamp-1001},{map:{...ground.map,cameraAngle:290}},{hud:{...ground.hud,health:{current:4014,max:4015}}},{hud:{...ground.hud,enemyBars:[{}]}}])assert(!mount.entry({...ground,...patch},ground.session,ground.timestamp));
});
test('recorded stalled-ground history refuses the first mount before any input',async()=>{
 const h=harness(),r=await h.run();assert.match(r.reason,/Ground progress stalled/);assert.equal(r.inputs,0);assert.deepEqual(h.counts().inputs,[]);assert(h.counts().releases>0);
});
test('historical mount and stationary reread establish climb but do not invent positive stamina',async()=>{
 const h=harness([afterLook(),attached,settled],{version:1,entries:[]}),r=await h.run();
 assert.match(r.reason,/positive stamina is unverified/);assert.equal(r.inputs,2);assert.equal(r.reads,3);assert.equal(r.mounted,false);assert.equal(r.staminaVerified,false);
 assert.deepEqual(h.counts().inputs,[['look',350,500],['key','VK_W',600]]);assert(h.counts().releases>=3);
});
test('positive same-frame reserve is accepted only with a continuous full-health climbing pose',()=>{
 assert(mount.stamina(ascent));assert(!mount.stamina(reserve));assert(!mount.stamina(attached));assert(!mount.stamina(settled));
 assert(!mount.stamina({...ascent,hud:{...ascent.hud,climbStamina:{...ascent.hud.climbStamina,pixels:179}}}));
 assert(mount.attached(attached,attached.session,attached.timestamp));assert(!mount.safeGround(attached,attached.session,attached.timestamp));
 assert(mount.safeGround(ground,ground.session,ground.timestamp));
 const second={...ledge,frameId:ledge.frameId+1,timestamp:ledge.timestamp+800};assert(mount.safeLedge(ledge,second,ledge.session,second.timestamp));
 assert(!mount.safeLedge(ledge,{...second,map:{...second.map,x:second.map.x+1}},ledge.session,second.timestamp));
});
test('a hypothetical positive arc stops at the first foothold without ledge movement',async()=>{
 const positive=clone(attached);positive.hud.climbStamina=clone(ascent.hud.climbStamina);
 const h=harness([afterLook(),positive],{version:1,entries:[]}),r=await h.run();
 assert.equal(r.mounted,true);assert.equal(r.staminaVerified,true);assert.equal(r.inputs,2);assert.match(r.reason,/stop for ledge review/);
});
test('focus, input, and observation failures release keys and never replay the forward pulse',async()=>{
 for(const options of [{cancel:true},{failLook:true},{failKey:true}]){const h=harness([afterLook(),attached],{version:1,entries:[]},options),r=await h.run();assert.equal(r.mounted,false);assert(h.counts().releases>0);assert(h.counts().inputs.filter(v=>v[0]==='key').length<=1);}
 const h=harness([afterLook(),attached],{version:1,entries:[]},{badSession:true}),r=await h.run();assert.match(r.reason,/continuity/);assert.equal(r.uncertainInput,true);assert.equal(h.counts().inputs.filter(v=>v[0]==='key').length,1);assert(h.counts().releases>0);
});
