const test=require('node:test'),assert=require('node:assert/strict'),m=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('Mondstadt Glider journal closes only with its exact title in the journal header',async()=>{
 const o={hud:{journal:true},ocr:[{text:'Mondstadt Glider',x:1000,y:120}]};
 for(const [patch,allowed] of [[{},true],[{hud:{journal:false}},false],[{ocr:[{text:'Other quest',x:1000,y:120}]},false],[{ocr:[{text:'Mondstadt Glider',x:100,y:250}]},false]]){
  let keys=[];await m.runQuestStep('actTwoJournalClose',{...o,...patch},{keyPress:async k=>keys.push(k),sleep:async()=>{},finishActTwoDialogue:async()=>({})},async()=>({}));assert.deepEqual(keys,allowed?['VK_ESCAPE']:[]);
 }
});
