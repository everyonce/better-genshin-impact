const test=require('node:test'),assert=require('node:assert/strict'),g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam-launch.js');
function harness(failure){
 let now=0,held=false,start=0,maxHold=0,reads=0,cancelled=false;
 const api={now:()=>now,check(){if(cancelled)throw Error('cancelled');},forwardDown(){assert.equal(held,false);held=true;start=now;},pressSpace:async()=>{now+=60;},sleep:async n=>{now+=n;},release(){if(held)maxHold=Math.max(maxHold,now-start);held=false;},pause:async()=>{},look:async()=>{},sample:async()=>{assert.equal(held,false,'recognition started with a held movement key');reads++;now+=2500;if(failure==='throw')throw Error('OCR failed');if(failure==='cancel'){cancelled=true;throw Error('cancelled');}return {valid:true,space:true,health:{max:4015,current:4015},marker:{x:960,y:400},distance:30};}};
 return {api,state:()=>({held,maxHold,reads})};
}
test('already-open preflight never presses Space or starts movement',async()=>{
 const h=harness();let presses=0;h.api.pressSpace=async()=>presses++;const r=await g.run(h.api);assert.equal(r.alreadyOpen,true);assert.equal(presses,0);assert.deepEqual(h.state(),{held:false,maxHold:0,reads:1});
});
test('launch releases before delayed or failed first-press recognition',async()=>{
 for(const failure of [null,'throw','cancel']){const h=harness(failure),sample=h.api.sample;let preflight=true,presses=0;const press=h.api.pressSpace;
 h.api.sample=async()=>{if(preflight){preflight=false;return {valid:true,space:false,groundControls:true};}return sample();};h.api.pressSpace=async()=>{presses++;await press();};
 if(failure==='cancel')await assert.rejects(g.run(h.api),/cancelled/);else await g.run(h.api);assert.equal(h.state().held,false);assert.equal(h.state().maxHold,160);assert.equal(h.state().reads,1);assert.equal(presses,1);}
});
test('all flight observation paths release before OCR and each movement pulse is at most 400ms',async()=>{
 for(const method of ['fly','course','segment'])for(const failure of [null,'throw','cancel']){const h=harness(failure);const args=method==='fly'?2400:method==='segment'?{holds:2,dx:0,dy:0}:undefined;const run=()=>g[method](h.api,args);if(failure==='cancel')await assert.rejects(run(),/cancelled/);else await run();assert.equal(h.state().held,false);assert.ok(h.state().maxHold<=400);assert.ok(h.state().reads>=1);}
});
test('cancellation during a bounded movement wait releases before propagating',async()=>{
 const h=harness();h.api.sample=async()=>({valid:true,space:false,groundControls:true});h.api.sleep=async()=>{throw Error('cancelled during sleep');};const r=await g.run(h.api);assert.match(r.reason,/cancelled/);assert.equal(h.state().held,false);assert.equal(h.state().reads,0);
});
test('repeated key release cannot extend recorded hold time through later OCR',()=>{
 const fs=require('node:fs'),source=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8');
 const line=source.split('\n').find(s=>s.includes('function releaseLaunch()'));let now=770,releases=0;const event={startedAt:0};
 const release=new Function('Date','keyUp','release','forwardEvent',line+';return releaseLaunch;')({now:()=>now},()=>{},()=>releases++,event);
 release();now+=2500;release();assert.equal(event.finishedAt,770);assert.equal(releases,2);
});
