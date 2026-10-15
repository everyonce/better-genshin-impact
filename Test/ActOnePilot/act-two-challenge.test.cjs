const test=require('node:test'),assert=require('node:assert/strict'),m=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('northern challenge activation requires exact pedestal, full field guards and selected interaction',async()=>{
 const o={map:{map:'Teyvat',x:-1407.49,y:2339.86},hud:{world:true,groundControls:true,health:{current:2136,max:2313},enemyBars:[],objectives:[]},ocr:[{text:'F',x:1100,y:520},{text:'Start Challenge',x:1220,y:520}]};
 for(const [p,ok] of [[{},true],[{map:{map:'Teyvat',x:-1300,y:2300}},false],[{hud:{...o.hud,enemyBars:[{}]}},false],[{hud:{...o.hud,health:{current:1600,max:2313}}},false],[{ocr:[]},false]]){
  let keys=[];const f={...o,...p},api={runActTwoNavigationWithPause:async(a,b,cb)=>cb(f),keyPress:async k=>keys.push(k),sleep:async()=>{}};
  await m.runQuestStep('actTwoChallengeStart',f,api,async()=>({...f,frameId:3}));assert.deepEqual(keys,ok?['VK_F']:[]);
 }
});
