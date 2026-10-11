const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');

function adapterHarness({focused=false, sessionId=6, remote=true, expectedSession=6, stop=false, focusThrows=false}={}) {
  const packageDir=path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot');
  const counts={focus:0,capture:0};
  let foreground=focused;
  const context={Date,
    genshin:{isRemoteDesktopSession:remote,windowsSessionId:sessionId,get isGameForeground(){return foreground;},
      focusGame:async()=>{counts.focus++;if(focusThrows)throw Error('native focus failure');foreground=true;},
      getPositionFromMap:()=>null,getCameraOrientation:()=>0},
    file:{isExists:p=>p==='stop.json'&&stop,readTextSync:p=>p==='stop.json'?JSON.stringify({session:'focus-session',createdAt:2000000}):fs.readFileSync(path.join(packageDir,p),'utf8'),
      writeTextSync:()=>true,writeImageSync:()=>true},
    RecognitionObject:{Ocr:()=>({})},
    ImageRegion:class{constructor(){this.width=1920;this.height=1080;this.findMulti=()=>{const a=[];a.count=0;return a;};}dispose(){}},
    OpenCvSharp:{OpenCvSharp:{Size:class{constructor(w,h){this.width=w;this.height=h;}}}},
    captureGameRegion:()=>{counts.capture++;return {width:1920,height:1080,srcMat:{},findMulti:()=>{const a=[];a.count=0;return a;},deriveCrop:()=>({srcMat:{resize:()=>({})},dispose(){}}),dispose(){}};},
    sleep:async()=>{},click(){},log:{info(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(packageDir,'bgi.js'),'utf8'),context);
  const adapter=context.createActOneAdapter(expectedSession);
  adapter.beginMission({mission:'questStep',step:'focusGame',session:'focus-session',createdAt:2000000});
  return {adapter,counts};
}

test('explicit focus request focuses once and captures fresh observations',async()=>{
  const h=adapterHarness();
  const first=await h.adapter.observe('focus-session',1);
  const second=await h.adapter.observe('focus-session',2);
  assert.equal(first.frameId,1);
  assert.equal(second.frameId,2);
  assert.deepEqual(h.counts,{focus:1,capture:2});
  const events=h.adapter.events().filter(e=>e.type==='focusGameRecovery');
  assert.equal(events.length,1);
  assert.equal(events[0].resultingFocus,true);
  assert.equal(events[0].ready,true);
  assert.ok(events[0].finishedAt>=events[0].startedAt);
});

test('session 6 is accepted only with matching remote-desktop proof; console and mismatch fail before capture',async()=>{
  const allowed=adapterHarness();
  await allowed.adapter.observe('focus-session',1);
  assert.equal(allowed.counts.capture,1);
  for(const options of [{remote:false},{sessionId:1},{expectedSession:5}]) {
    const h=adapterHarness(options);
    await assert.rejects(()=>h.adapter.observe('focus-session',1),/pinned verified RDP child session/);
    assert.deepEqual(h.counts,{focus:0,capture:0});
  }
});

test('ordinary observe never refocuses a background game',async()=>{
  const h=adapterHarness({focused:false});
  h.adapter.beginMission({mission:'observe',session:'focus-session',createdAt:2000000});
  await assert.rejects(()=>h.adapter.observe('focus-session',1),/Game lost foreground focus/);
  assert.deepEqual(h.counts,{focus:0,capture:0});
});

test('failed focus prevents capture and records the resulting foreground state',async()=>{
  const h=adapterHarness({focusThrows:true});
  await assert.rejects(()=>h.adapter.observe('focus-session',1),/native focus failure/);
  assert.deepEqual(h.counts,{focus:1,capture:0});
  const event=h.adapter.events().find(e=>e.type==='focusGameRecovery');
  assert.equal(event.resultingFocus,false);
  assert.equal(event.ready,false);
  assert.match(event.error,/native focus failure/);
});

test('stop request is honored before any focus attempt',async()=>{
  const h=adapterHarness({stop:true});
  await assert.rejects(()=>h.adapter.observe('focus-session',1),/Stop requested/);
  assert.deepEqual(h.counts,{focus:0,capture:0});
});

test('focusGame quest step returns the observed frame without another input action',async()=>{
  let inputs=0;
  const result=await mission.runQuestStep('focusGame',{frameId:7},{},async()=>{inputs++;});
  assert.deepEqual(result,{status:'completed',step:'focusGame',reason:'Game focus recovered; inspect fresh scene',frameId:7});
  assert.equal(inputs,0);
});
