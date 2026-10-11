const test=require('node:test');
const assert=require('node:assert/strict');
const engine=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/engine.js');

function harness(){
  let now=100000,observations=0,releases=0;const files=new Map(),archive=[];
  const api={now:()=>now,write:(p,t)=>files.set(p,t),append:(_,t)=>archive.push(JSON.parse(t)),wasSeen:(s,id)=>files.has(`receipts/${s}/${id}.json`),
    observe:async()=>{observations++;return {timestamp:now,screenshotPath:'test.png',hud:{world:false},map:null};},
    beginMission:()=>{},requireInputReady:()=>{},events:()=>[],release:()=>{releases++;}};
  const runner=engine.create(api,{session:'persist',enableInput:true});
  const req=(id,mission='observe',extra={})=>({session:'persist',id,createdAt:now,expectedFrameId:runner.getFrame(),mission,...extra});
  return {files,archive,api,runner,req,advance:ms=>{now+=ms;},get observations(){return observations;},get releases(){return releases;}};
}

test('bounded report index retains domain provenance and complete append-only history',async()=>{
  const h=harness();await h.runner.observe();
  await h.runner.process(h.req('entry','questStep',{step:'wolfStart'}),()=>({runQuestStep:async()=>({status:'completed',step:'wolfStart',label:'Deep Within the Temple of the Wolf'})}));
  for(let n=0;n<250;n++)await h.runner.process(h.req(`observe-${n}`),()=>({}));
  const index=JSON.parse(h.files.get('reports/persist.json'));
  assert.equal(h.archive.length,502);assert.ok(index.length<=211);
  assert.ok(index.some(r=>r.id==='entry'&&r.status==='completed'));
  assert.equal(JSON.parse(h.files.get('receipts/persist/entry.json')).status,'completed');
  assert.equal(h.releases,251);
});

test('evicting replay IDs from RAM does not permit replay or overwrite the original receipt',async()=>{
  const h=harness();await h.runner.observe();
  await h.runner.process(h.req('first'),()=>({}));
  const original=h.files.get('receipts/persist/first.json');
  for(let n=0;n<4096;n++)await h.runner.process(h.req(`later-${n}`),()=>({}));
  const before=h.observations;
  assert.equal(await h.runner.process(h.req('first'),()=>({})),'rejected');
  assert.equal(h.observations,before);assert.equal(h.files.get('receipts/persist/first.json'),original);
  assert.equal(h.archive.at(-1).details.reason,'Duplicate id');
});

test('long idle never replays an old request and a fresh request still requires current frame',async()=>{
  const h=harness();await h.runner.observe();const old=h.req('old');h.advance(86400000*30);
  assert.equal(await h.runner.process(old,()=>({})),'rejected');
  assert.equal(h.observations,1);assert.equal(h.runner.stopped(),false);
  assert.equal(await h.runner.process(h.req('fresh'),()=>({})),'completed');
  assert.equal(await h.runner.process({...h.req('stale'),expectedFrameId:0},()=>({})),'rejected');
});
