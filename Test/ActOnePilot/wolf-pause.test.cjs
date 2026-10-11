const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const mission = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
const context = {};
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8'),context);

function trial(hp=626) {
  return {timestamp:1000,frameId:66,map:null,
    ocr:[{text:'Kaeya',x:1668,y:490},{text:'Trial',x:1798,y:463}],
    hud:{world:false,groundControls:true,health:{current:hp,max:1427}}};
}

test('low-health Wolf pause remains available while movement and combat are refused',()=>{
  const frame=trial();
  assert.equal(context.actOneWolfDomainHud(frame,1000),false);
  assert.equal(context.actOneWolfPauseHud(frame,1000),true);
  assert.equal(context.actOneWolfPauseHud(trial(1),1000),true);
  assert.equal(context.actOneWolfPauseHud(trial(0),1000),false);
});

test('emergency pause cannot act on a stale, unknown, dead, overworld or menu scene',()=>{
  const good=trial();
  for(const bad of [
    {...good,timestamp:-1}, {...good,timestamp:1001},
    {...good,map:{map:'Teyvat',x:0,y:0}}, {...good,ocr:[]},
    ...['climbing','journal','bigMap','dialogueReady','choice'].map(flag=>({...good,hud:{...good.hud,[flag]:true}})),
    {...good,hud:{...good.hud,tutorialStep:'wolfInfo'}},
    {...good,hud:{...good.hud,health:null}},
    {...good,hud:{...good.hud,health:{current:NaN,max:1427}}}
  ]) assert.equal(context.actOneWolfPauseHud(bad,1000),false);
});

test('pause-only OCR fallback accepts exact Trial and captured Kaeya max HP without a reliable Kaeya name',()=>{
  const miss={...trial(),ocr:[{text:'Kaea',x:1665,y:489,width:64,height:27},{text:'Trial',x:1802,y:463,width:60,height:30}]};
  assert.equal(context.actOneWolfDomainHud(miss,1000),false,'movement still requires exact Kaeya');
  assert.equal(context.actOneWolfPauseOnlyHud(miss,1000),true);
  assert.equal(context.actOneWolfPauseHud(miss,1000),true);
  for(const bad of [
    {...miss,timestamp:-1},{...miss,timestamp:1001},{...miss,map:{map:'Teyvat',x:0,y:0}},
    {...miss,ocr:[{text:'Trial',x:1500,y:490,width:60,height:30}]},
    {...miss,ocr:[{text:'Trial',x:1802,y:250,width:60,height:30}]},
    {...miss,hud:{...miss.hud,health:{current:0,max:1427}}},
    {...miss,hud:{...miss.hud,health:{current:1000,max:1055}}},
    ...['groundControls','climbing','journal','bigMap','dialogueReady','choice','auto','loading','unknownHud'].map(flag=>({...miss,hud:{...miss.hud,[flag]:flag==='groundControls'?false:true}})),
    {...miss,hud:{...miss.hud,tutorialStep:'wolfInfo'}}
  ]) assert.equal(context.actOneWolfPauseOnlyHud(bad,1000),false);
});

test('Wolf pause only reports success after both domain pause labels are observed',async()=>{
  for(const labels of [['Continue Challenge','Leave Domain?'],['Continue Challenge'],[]]) {
    let presses=0;
    const result=await mission.runQuestStep('wolfPause',trial(),{
      wolfDomainAction:async()=>{presses++;},sleep:async()=>{}
    },async()=>({frameId:67,ocr:labels.map(text=>({text}))}));
    assert.equal(presses,1);
    assert.equal(result.pauseVerified,labels.length===2);
    assert.equal(result.status,labels.length===2?'completed':'stopped');
  }
});
test('a delayed second pause-menu label is verified without another Escape',async()=>{
  let presses=0,observes=0;
  const result=await mission.runQuestStep('wolfPause',trial(),{
    wolfDomainAction:async()=>{presses++;},sleep:async()=>{}
  },async()=>({frameId:67+(observes++),ocr:(observes===1?['Continue Challenge']:['Continue Challenge','Leave Domain?']).map(text=>({text}))}));
  assert.equal(result.status,'completed');
  assert.equal(result.pauseVerified,true);
  assert.equal(result.polls,2);
  assert.equal(presses,1);
});
