const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const g=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-field.js');
const low=require('./act-two-hq-health-fade.fixture.json');
const healthy=()=>({...structuredClone(low),hud:{...structuredClone(low.hud),health:{current:4015,max:4015}}});
const p={mode:'actions',actions:[{type:'look',dx:0,dy:100}]};
test('recorded roof fade permits measurement but never accepts low health',()=>{
 const w=healthy();assert.equal(g.healthReread(low,w,p,1000,low.session),true);
 assert.equal(g.ready(low,w,1000,low.session,false,false,true),false);
 for(const mutate of [o=>o.hud.enemyBars=[{}],o=>o.hud.climbing=true,o=>o.map.x+=3,o=>o.session='other',o=>o.timestamp=-1]){
  const o=structuredClone(low);mutate(o);assert.equal(g.healthReread(o,w,p,1000,low.session),false);
 }
 assert.equal(g.healthReread(low,w,{mode:'actions',actions:[{type:'key',key:'VK_W',ms:600}]},1000,low.session),false);
});
async function polling(samples){
 const source=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8');
 const body=source.slice(source.indexOf('runActTwoField: async'),source.indexOf('runActTwoWindriseSlime: async'));
 const loop=body.match(/for\(var poll=0;poll<5;poll\+\+\)\{.*\}/)[0];
 let reads=0,releases=0;const events=[];
 const run=new Function('guard','witness','request','p','sleep','observe','Date','release','return (async()=>{let current;const fieldReady=o=>guard.ready(o,witness,Date.now(),request.session,false,false,true);'+loop+';return current;})()');
 let error;try{await run(g,healthy(),{session:low.session},p,async ms=>events.push(['wait',ms]),async()=>{reads++;events.push(['read']);return samples.shift();},{now:()=>1000},()=>{releases++;events.push(['release']);});}catch(e){error=e;}
 return {reads,releases,events,error};
}
test('first low value releases before one stationary reread; healthy reread may resume',async()=>{
 const r=await polling([low,healthy()]);assert.equal(r.error,undefined);assert.equal(r.reads,2);assert.equal(r.releases,1);
 assert.deepEqual(r.events,[['wait',450],['read'],['release'],['wait',150],['read']]);
});
test('second low reading stops without any further retry',async()=>{
 const r=await polling([low,low,healthy()]);assert.match(r.error.message,/health_below_minimum/);assert.equal(r.reads,2);assert.equal(r.releases,2);
});
