const test=require('node:test'),assert=require('node:assert/strict'),m=require(process.env.MISSION_MODULE||'../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js'),o=require('./act-two-windrise-amber.fixture.json');
test('recorded injured Amber can select Kaeya only at the safe Windrise recovery position',async()=>{
 for(const patch of [{},{map:{...o.map,x:o.map.x+20}},{hud:{...o.hud,health:{current:1275,max:1741}}},{ocr:o.ocr.filter(r=>r.text!=='Kaeya')}]){
  let keys=[];const field={...o,...patch},api={runActTwoNavigationWithPause:async(_,observe,f)=>f(field),keyPress:async k=>keys.push(k),sleep:async()=>{}},after={...o,hud:{...o.hud,health:{current:3627,max:4015}}};
  await m.runQuestStep('actTwoStatueSelectKaeya',{},api,async()=>after);assert.deepEqual(keys,Object.keys(patch).length?[]:['VK_3']);
 }
});
