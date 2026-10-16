const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam-launch.js');
function harness(failure){
 let now=0,held=false,start=0,maxHold=0,reads=0,cancelled=false;
 const api={now:()=>now,check(){if(cancelled)throw Error('cancelled');},forwardDown(){assert.equal(held,false);held=true;start=now;},pressSpace:async()=>{now+=60;},sleep:async n=>{now+=n;},release(){if(held)maxHold=Math.max(maxHold,now-start);held=false;},pause:async()=>{},look:async()=>{},sample:async()=>{assert.equal(held,false,'recognition started with a held movement key');reads++;now+=2500;if(failure==='throw')throw Error('OCR failed');if(failure==='cancel'){cancelled=true;throw Error('cancelled');}return {valid:true,space:true,health:{max:4015,current:4015},marker:{x:960,y:400},distance:30};}};
 return {api,state:()=>({held,maxHold,reads})};
}
test('launch releases within 770ms before delayed or failed OCR',async()=>{
 for(const failure of [null,'throw','cancel']){const h=harness(failure);if(failure==='cancel')await assert.rejects(g.run(h.api),/cancelled/);else await g.run(h.api);assert.equal(h.state().held,false);assert.equal(h.state().maxHold,770);assert.equal(h.state().reads,1);}
});
test('all flight observation paths release before OCR and each movement pulse is at most 400ms',async()=>{
 for(const method of ['fly','course','segment'])for(const failure of [null,'throw','cancel']){const h=harness(failure);const args=method==='fly'?2400:method==='segment'?{holds:2,dx:0,dy:0}:undefined;const run=()=>g[method](h.api,args);if(failure==='cancel')await assert.rejects(run(),/cancelled/);else await run();assert.equal(h.state().held,false);assert.ok(h.state().maxHold<=400);assert.ok(h.state().reads>=1);}
});
test('cancellation during a bounded movement wait releases before propagating',async()=>{
 const h=harness();h.api.sleep=async()=>{throw Error('cancelled during sleep');};const r=await g.run(h.api);assert.match(r.reason,/cancelled/);assert.equal(h.state().held,false);assert.equal(h.state().reads,0);
});
