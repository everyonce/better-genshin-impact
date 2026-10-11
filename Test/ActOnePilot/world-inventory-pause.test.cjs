const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const context={};
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8'),context);
function frame(){return {timestamp:1000,map:{map:'Teyvat',x:-1329,y:2564},
  hud:{world:false,groundControls:true,health:null},ocr:[{text:'369/1055',x:906,y:1001,width:101,height:20}]};}
test('opening inventory can pause a verified world HUD despite unresolved low-health OCR',()=>{
  assert.equal(context.actOneWorldInventoryPauseReady(frame(),1000),true);
  assert.equal(context.actOneWolfDomainHud(frame(),1000),false);
});
test('inventory pause fallback rejects stale or unknown scenes and invalid or duplicated health rows',()=>{
  const good=frame();
  for(const bad of [
    {...good,timestamp:-1}, {...good,timestamp:1001}, {...good,map:null}, {...good,ocr:[]},
    {...good,ocr:[...good.ocr,...good.ocr]},
    {...good,ocr:[{...good.ocr[0],text:'0/1055'}]},
    {...good,ocr:[{...good.ocr[0],text:'3691/1055'}]},
    {...good,ocr:[{...good.ocr[0],x:100}]},
    ...['auto','climbing','journal','bigMap','dialogueReady','choice'].map(flag=>({...good,hud:{...good.hud,[flag]:true}})),
    {...good,hud:{...good.hud,groundControls:false}},
    {...good,hud:{...good.hud,tutorialStep:'wolfInfo'}}
  ]) assert.equal(context.actOneWorldInventoryPauseReady(bad,1000),false);
});
