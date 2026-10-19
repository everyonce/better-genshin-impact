const test=require('node:test'),assert=require('node:assert/strict');
const wall=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-riddle-wall-mount.js');
const progress=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/field-progress.js');
const initial=require('./act-two-riddle-broad-wall.fixture.json');
const joined=require('./act-two-riddle-broad-wall-joined-title.fixture.json');
const history=require('./act-two-riddle-lateral-history.fixture.json');
const climbing=require('./act-two-hideout-riddle-mounted.fixture.json');
const liveMounted=require('./act-two-riddle-broad-wall-mounted.fixture.json');
const liveSettled=require('./act-two-riddle-broad-wall-settled.fixture.json');
const arc=require('./act-two-lower-climb-recorded.fixture.json').phases[0].initial.hud.climbStamina;
const clone=x=>JSON.parse(JSON.stringify(x));
function harness(samples,options={}){
 let now=initial.timestamp,frame=initial.frameId,releases=0,inputs=[];
 const queue=samples.map(clone),api={now:()=>now,check(){if(options.cancel)throw Error('cancelled');},sleep:async ms=>{now+=ms;},release:async()=>{releases++;},
  key:async(k,ms)=>{inputs.push([k,ms]);if(options.failKey)throw Error('key_failed');},
  observe:async()=>{let o=queue.shift();if(!o)throw Error('missing_sample');o.session=options.badSession?'other':initial.session;o.frameId=++frame;o.timestamp=now;return o;}};
 return {run:()=>wall.run(initial,history,progress,api),counts:()=>({inputs,releases})};
}
test('real lateral displacement and broad-wall image allow exactly one W600',()=>{
 const plan=wall.plan();assert(wall.entry(initial,initial.session,initial.timestamp));assert.equal(progress.rejection(history,plan,initial),null);
 assert.match(progress.rejection(progress.begin(history,plan,initial,'once'),plan,initial),/already attempted/);
 for(const bad of [{...initial,map:{...initial.map,x:initial.map.x+.25}},{...initial,map:{...initial.map,cameraAngle:300}},{...initial,hud:{...initial.hud,health:{current:4014,max:4015}}}])assert.match(progress.rejection(history,plan,bad),/unavailable/);
 assert.match(progress.rejection(history,{...plan,actions:[{type:'key',key:'VK_W',ms:800}]},initial),/unavailable/);
 assert(wall.entry(joined,joined.session,joined.timestamp));assert.equal(progress.rejection(history,plan,joined),null);
});
test('a ground obstruction stops after one pulse with key release',async()=>{
 const h=harness([initial]),r=await h.run();assert.equal(r.climbingObserved,false);assert.equal(r.groundRecovered,false);assert.equal(r.inputs,1);assert.match(r.reason,/safe ground verified/);assert.deepEqual(h.counts().inputs,[['VK_W',600]]);assert(h.counts().releases>=2);
});
test('live broad-wall frames show climbing and one metre gained, but no reliable stamina arc',()=>{
 assert(wall.attached(liveMounted,liveMounted.session,liveMounted.timestamp));
 assert(wall.attached(liveSettled,liveSettled.session,liveSettled.timestamp));
 assert.equal(liveMounted.hud.objectives.at(-1),'Higher 27m');
 assert.equal(liveSettled.hud.objectives.at(-1),'Higher26m');
 assert.equal(wall.stamina(liveMounted),false);assert.equal(wall.stamina(liveSettled),false);
});
test('positive same-frame stamina is verified before a low X release and safe ground',async()=>{
 const attached=clone(climbing);attached.hud.climbStamina=clone(arc);const h=harness([attached,initial]),r=await h.run();
 assert.equal(r.climbingObserved,true);assert.equal(r.staminaVerified,true);assert.equal(r.groundRecovered,true);assert.equal(r.footholdVerified,true);assert.deepEqual(h.counts().inputs,[['VK_W',600],['VK_X',60]]);assert(h.counts().releases>=3);
});
test('ambiguous stamina permits one stationary reread then safe release without a foothold claim',async()=>{
 const h=harness([climbing,climbing,initial]),r=await h.run();assert.equal(r.climbingObserved,true);assert.equal(r.staminaVerified,false);assert.equal(r.footholdVerified,false);assert.equal(r.groundRecovered,true);assert.equal(r.inputs,2);assert.equal(r.reads,3);
});
test('failure and focus loss release keys without repeating the forward pulse',async()=>{
 for(const options of [{cancel:true},{failKey:true},{badSession:true}]){const h=harness([climbing],options),r=await h.run();assert.equal(r.footholdVerified,false);assert(h.counts().inputs.filter(x=>x[0]==='VK_W').length<=1);assert(h.counts().releases>0);}
});
