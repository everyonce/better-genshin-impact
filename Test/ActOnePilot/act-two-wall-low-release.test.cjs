const test=require('node:test'),assert=require('node:assert/strict');
const guard=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-wall-low-release.js');
const mounted=require('./act-two-riddle-broad-wall-settled.fixture.json');
const ground=require('./act-two-riddle-broad-wall.fixture.json');
const copy=x=>JSON.parse(JSON.stringify(x));
function harness(start,samples){let now=start.timestamp,frame=start.frameId,keys=[],releases=0;const queue=samples.map(copy);
 const api={now:()=>now,check(){},sleep:async n=>{now+=n;},release:async()=>{releases++;},key:async(k,ms)=>keys.push([k,ms]),observe:async()=>{const o=queue.shift();if(!o)throw Error('missing sample');o.session=start.session;o.frameId=++frame;o.timestamp=now;return o;}};
 return {run:()=>guard.run(start,api),counts:()=>({keys,releases})};}
test('recorded low broad-wall attachment permits one X60 and verifies ground',async()=>{
 assert(guard.attached(mounted,mounted.session,mounted.timestamp));
 const h=harness(mounted,[ground]),r=await h.run();assert.equal(r.groundRecovered,true);assert.equal(r.inputs,1);assert.deepEqual(h.counts().keys,[['VK_X',60]]);assert(h.counts().releases>=2);
});
test('changed pose or health refuses release with no input',async()=>{
 for(const change of [o=>o.map.x+=.5,o=>o.hud.health.current--,o=>o.hud.climbing=false,o=>o.hud.objectives=['Higher 20m']]){
  const o=copy(mounted);change(o);const h=harness(o,[]),r=await h.run();assert.equal(r.inputs,0);assert.equal(r.groundRecovered,false);assert.deepEqual(h.counts().keys,[]);assert(h.counts().releases>0);
 }
});
test('uncertain landing stops after single release without claiming ground',async()=>{
 const h=harness(mounted,[mounted,mounted]),r=await h.run();assert.equal(r.inputs,1);assert.equal(r.groundRecovered,false);assert.deepEqual(h.counts().keys,[['VK_X',60]]);
});
