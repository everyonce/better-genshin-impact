const test=require('node:test'),assert=require('node:assert/strict'),m=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('statue recovery switches only a healthy Traveler in the verified safe location',async()=>{
 const o={map:{map:'Teyvat',x:-1265.917,y:1928.381},hud:{world:true,groundControls:true,health:{current:1363,max:1363},enemyBars:[],objectives:[]},ocr:[{text:'Kaeya',x:1690,y:440}]};
 for(const [p,ok] of [[{},true],[{map:{map:'Teyvat',x:-1300,y:2300}},false],[{hud:{...o.hud,enemyBars:[{}]}},false],[{hud:{...o.hud,health:{current:600,max:1363}}},false],[{ocr:[]},false]]){
  let keys=[];const f={...o,...p},api={runActTwoNavigationWithPause:async(a,b,cb)=>cb(f),keyPress:async k=>keys.push(k),sleep:async()=>{}};
  await m.runQuestStep('actTwoStatueSelectKaeya',f,api,async()=>({...f,frameId:3}));assert.deepEqual(keys,ok?['VK_3']:[]);
 }
});
