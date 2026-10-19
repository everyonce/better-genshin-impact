const test=require('node:test'),assert=require('node:assert/strict');
const micro=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-wall-micro-ascent.js');
const ground=require('./act-two-wall-micro-ground.fixture.json'),climb=require('./act-two-wall-micro-attached.fixture.json'),landed=require('./act-two-wall-micro-landed.fixture.json');
const clone=x=>JSON.parse(JSON.stringify(x));
const nextHeight=(o,n)=>{o.hud.objectives=o.hud.objectives.map(t=>/^\s*Higher\s*\d+m$/.test(t)?`Higher ${n}m`:t);return o;};
function harness(initial,observations,options={}){let now=initial.timestamp,frame=initial.frameId,keys=[],releases=0;const queue=observations.map(clone);
 const api={now:()=>now,check(){if(options.focusLost)throw Error('focus lost');},sleep:async ms=>{now+=ms;},release:async()=>{releases++;},key:async(k,ms)=>{keys.push([k,ms]);now+=ms;if(options.failW200&&k==='VK_W'&&ms===200)throw Error('input failed');},sample:async()=>({valid:true,stamina:{kind:'absent',pixels:null},rawPixels:0}),observe:async()=>{const o=queue.shift();if(!o)throw Error('observation missing');o.session=initial.session;o.frameId=++frame;o.timestamp=now;return o;}};
 return {run:()=>micro.run(clone(initial),api),counts:()=>({keys,releases})};}
test('recorded bare-wall pose and low attachment are within the reviewed envelope',()=>{
 assert(micro.entry(ground,ground.session,ground.timestamp));assert(micro.attached(climb,climb.session,climb.timestamp));assert(micro.grounded(landed,landed.session,landed.timestamp));
});
test('one W600 mount, one W200 upward pulse, then X60 returns to verified ground',async()=>{
 const up=nextHeight(clone(climb),25),h=harness(ground,[climb,up,landed]),r=await h.run();
 assert.deepEqual(h.counts().keys,[['VK_W',600],['VK_W',200],['VK_X',60]]);assert.equal(r.totalForwardBudgetMs,800);assert.equal(r.mountVerified,true);assert.equal(r.afterAscentHeight,25);assert.equal(r.heightBoundKept,true);assert.equal(r.staminaVerified,false);assert.equal(r.groundRecovered,true);assert(h.counts().releases>=4);
});
test('unattached W600 stops before upward input',async()=>{const h=harness(ground,[ground]),r=await h.run();assert.equal(r.groundRecovered,true);assert.deepEqual(h.counts().keys,[['VK_W',600]]);});
test('changed account or pose refuses all gameplay input',async()=>{const bad=clone(ground);bad.map.x+=.5;const h=harness(bad,[]),r=await h.run();assert.equal(r.inputs,0);assert.deepEqual(h.counts().keys,[]);});
test('W200 failure releases key and uses low X recovery',async()=>{const h=harness(ground,[climb,landed],{failW200:true}),r=await h.run();assert.equal(r.recoveredAfterFailure,true);assert.equal(r.groundRecovered,true);assert.deepEqual(h.counts().keys,[['VK_W',600],['VK_W',200],['VK_X',60]]);assert(h.counts().releases>=3);});
test('unexpected Higher 24m is flagged while emergency X still lands',async()=>{const high=nextHeight(clone(climb),24),h=harness(ground,[climb,high,landed]),r=await h.run();assert.equal(r.heightBoundKept,false);assert.equal(r.groundRecovered,true);assert.deepEqual(h.counts().keys,[['VK_W',600],['VK_W',200],['VK_X',60]]);});
