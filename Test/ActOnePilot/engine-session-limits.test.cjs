const test=require('node:test');
const assert=require('node:assert/strict');
const engine=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/engine.js');

function harness() {
  let now=100000,frame=0;const writes=[];
  const api={now:()=>now,observe:async(_,n)=>({timestamp:now,screenshotPath:`frame-${n}.png`,ocr:[],map:null,hud:{world:false}}),
    write:(path,value)=>writes.push([path,value]),beginMission:()=>{},events:()=>[],release:()=>{},
    checkStop:()=>{},sleep:async ms=>{now+=ms;}};
  const runner=engine.create(api,{session:'clock-session',enableInput:false});
  async function requestObservation() {
    const req={session:'clock-session',id:`observe-${++frame}`,createdAt:now,expectedFrameId:runner.getFrame(),mission:'observe'};
    assert.equal(await runner.process(req,()=>({})), 'completed');
  }
  return {runner,requestObservation,advance:ms=>{now+=ms;},get now(){return now;}};
}

test('controller remains available beyond two hours and prolonged idle without renewal or restart',async()=>{
  const h=harness();await h.runner.observe();
  const started=h.now;
  async function keepActiveUntil(target) {
    while(h.now<target) {
      const step=Math.min(9*60*1000,target-h.now);
      h.advance(step);
      await h.requestObservation();
    }
  }
  await keepActiveUntil(started+60*60*1000);
  assert.equal(h.runner.stopped(),false,'the listener remains available through hour one');
  await keepActiveUntil(started+119*60*1000);
  assert.equal(h.runner.stopped(),false,'the listener remains available before the former two-hour cap');
  h.advance(60*1000);
  assert.equal(h.now-started,7200000);
  assert.equal(h.runner.stopped(),false,'two hours is not a listener lifetime limit');
  h.advance(30*24*60*60*1000);
  assert.equal(h.runner.stopped(),false,'a month idle does not end the listener');
  await h.requestObservation();
});

test('controller accepts a fresh request after ten minutes without activity',async()=>{
  const h=harness();await h.runner.observe();
  h.advance(600000);
  assert.equal(h.runner.stopped(),false);
  await h.requestObservation();
});
